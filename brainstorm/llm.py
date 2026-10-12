"""Optional Anthropic-backed discussion provider with an honest offline seam.

The SDK is imported lazily so the application remains fully usable offline when
Anthropic is not installed.  The provider never persists its API key.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import threading
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .jsonutil import strip_code_fence
from .models import (
    DiscussionSession,
    DiscussionState,
    OpportunityCard,
    Role,
    StanceChange,
    TrendSource,
    Utterance,
    ViewpointKind,
)
from .turn_planner import TurnPlan, plan_turn


class ProviderFailure(RuntimeError):
    """A safe, user-facing provider failure with no secret-bearing details."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


class GenerationCancelled(ProviderFailure):
    def __init__(self) -> None:
        super().__init__("cancelled", "模型生成已取消")


@dataclass(frozen=True)
class TurnSpec:
    speaker_id: str
    speaker_name: str
    phase: str
    kind_hint: str = "假设"
    final: bool = False


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.requests + other.requests,
        )


@dataclass(frozen=True)
class TurnResult:
    utterance: Utterance
    opportunity: OpportunityCard | None = None
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class _Response:
    text: str
    usage: Usage


class AnthropicDiscussionProvider:
    """Generate staged, structured discussion turns through an Anthropic client.

    ``client`` is injectable for tests and must expose either the modern
    ``messages.stream`` API or a compatible fake.  The real SDK is never
    imported at module import time.
    """

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-opus-5-5",
        timeout: float = 30.0,
        max_retries: int = 1,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.timeout = max(3.0, float(timeout))
        self.max_retries = max(0, min(int(max_retries), 3))
        self._client = client
        self.last_usage = Usage()

    @property
    def configured(self) -> bool:
        return bool(self._api_key or self._client is not None) and bool(self.model)

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderFailure("missing_key", "未配置真实模型 API Key；已回退到离线模拟")
        try:
            from anthropic import Anthropic  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderFailure("missing_sdk", "未安装真实模型 SDK；已回退到离线模拟") from exc
        try:
            self._client = Anthropic(api_key=self._api_key, timeout=self.timeout)
        except Exception as exc:
            raise ProviderFailure("client_init", "真实模型客户端初始化失败；已回退到离线模拟") from exc
        return self._client

    @staticmethod
    def plan(roles: Iterable[Role]) -> list[TurnSpec]:
        selected = list(roles)
        turns = [TurnSpec("moderator", "主持人", "开场", "总结")]
        turns.extend(TurnSpec(role.id, role.name, "独立观点", "假设") for role in selected)
        turns.extend(TurnSpec(role.id, role.name, "正反交锋", "风险") for role in selected[: min(3, len(selected))])
        turns.append(TurnSpec("moderator", "主持人", "阶段总结", "总结", final=True))
        return turns

    def discuss(
        self,
        topic: str,
        roles: Iterable[Role],
        source_note: str = "",
        *,
        sources: Sequence[TrendSource] = (),
        on_partial: Callable[[str, str], None] | None = None,
        cancel_event: threading.Event | None = None,
        on_turn: Callable[[Utterance, int, int], None] | None = None,
    ) -> Any:
        """Compatibility entry point returning a fully generated session."""
        from .models import DiscussionSession

        selected = list(roles)
        if not topic.strip():
            raise ValueError("请输入一个讨论主题。")
        if not selected:
            raise ValueError("至少选择一位参与者。")
        self.last_usage = Usage()
        source_items = list(sources)
        if source_note.strip():
            source_items.insert(0, TrendSource("用户提供的前沿线索", note=source_note.strip(), source_type="user"))
        session = DiscussionSession(topic=topic.strip(), sources=source_items, source=source_items[0] if source_items else None, selected_role_ids=[r.id for r in selected])
        history: list[Utterance] = []
        plans = self.plan(selected)
        opening = plans[:1]
        # The protocol calls this phase 独立观点: each role gives its own initial
        # stance. They are genuinely independent, so running them one after
        # another both wasted most of the wait and let later roles read earlier
        # ones, which is not what an independent first round means.
        independent = plans[1:1 + len(selected)]
        rest = plans[1 + len(selected):]

        def emit(result: TurnResult, spec: TurnSpec, index: int) -> None:
            history.append(result.utterance)
            appended = session.append_utterance(result.utterance)
            if result.opportunity is not None:
                session.opportunity = result.opportunity
            if on_turn is not None:
                # Hand each finished turn over immediately: the UI can show the
                # opening long before the whole batch exists.
                on_turn(appended, index, len(plans))

        for spec in opening:
            emit(self.generate_turn(
                topic, selected, source_items, history, spec,
                on_partial=(lambda text, name=spec.speaker_name: on_partial(name, text)) if on_partial else None,
                cancel_event=cancel_event,
            ), spec, len(history) + 1)

        if independent:
            snapshot = list(history)
            with ThreadPoolExecutor(max_workers=min(4, len(independent))) as pool:
                futures = [
                    pool.submit(self._generate_turn_result, topic, selected, source_items, snapshot, spec,
                                cancel_event=cancel_event)
                    for spec in independent
                ]
                results = [future.result() for future in futures]
            usage = Usage()
            for result in results:
                usage = usage.add(result.usage)
            self.last_usage = self.last_usage.add(usage)
            for spec, result in zip(independent, results):
                emit(result, spec, len(history) + 1)

        for spec in rest:
            emit(self.generate_turn(
                topic, selected, source_items, history, spec,
                on_partial=(lambda text, name=spec.speaker_name: on_partial(name, text)) if on_partial else None,
                cancel_event=cancel_event,
            ), spec, len(history) + 1)
        session.provider_mode = "llm"
        session.effective_provider = self.provider_name
        session.request_mode = "llm"
        session.status_message = "真实模型生成；观点与来源仍需核验"
        session.model_name = self.model
        session.generation_status = "completed"
        session.rebuild_state()
        session.usage_input_tokens = self.last_usage.input_tokens
        session.usage_output_tokens = self.last_usage.output_tokens
        session.usage_requests = self.last_usage.requests
        return session

    def complete(self, prompt: str, *, cancel_event: threading.Event | None = None,
                 max_tokens: int = 2600) -> str:
        """One plain request returning raw text.

        Used by callers that only need text back (for example the model-backed
        social hotspot lookup), so they can reuse the very same configured API
        without going through the discussion turn parser.  ``max_tokens`` is
        generous by default because such callers ask for long structured output
        (a pool of hotspots), unlike a single discussion turn.
        """
        return self._request(prompt, on_partial=None, cancel_event=cancel_event,
                             max_tokens=max_tokens).text

    def extend_batch(
        self,
        session: DiscussionSession,
        state: DiscussionState,
        *,
        roles: Iterable[Role] = (),
        cancel_event: threading.Event | None = None,
        on_partial: Callable[[str, str], None] | None = None,
    ) -> list[Utterance]:
        selected = list(roles)
        plan = plan_turn(session, selected, state)
        speaker = next((role for role in selected if role.id == plan.speaker_id), None)
        if speaker is None:
            speaker = Role(plan.speaker_id, plan.speaker_name, "编排、收敛和标记不确定性", "#b08d50", "整理当前讨论")
        result = self.generate_turn(
            session.topic,
            selected,
            list(session.sources),
            list(session.utterances),
            TurnSpec(plan.speaker_id, plan.speaker_name, plan.phase, plan.kind_hint),
            on_partial=(lambda text: on_partial(speaker.name, text)) if on_partial else None,
            cancel_event=cancel_event,
            state=state,
            plan=plan,
        )
        return [result.utterance]

    def generate_turn(
        self,
        topic: str,
        roles: Sequence[Role],
        sources: Sequence[TrendSource],
        history: Sequence[Utterance],
        spec: TurnSpec,
        *,
        on_partial: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
        state: DiscussionState | None = None,
        plan: TurnPlan | None = None,
    ) -> TurnResult:
        result = self._generate_turn_result(
            topic, roles, sources, history, spec,
            on_partial=on_partial, cancel_event=cancel_event, state=state, plan=plan,
        )
        self.last_usage = self.last_usage.add(result.usage)
        return result

    def _generate_turn_result(
        self,
        topic: str,
        roles: Sequence[Role],
        sources: Sequence[TrendSource],
        history: Sequence[Utterance],
        spec: TurnSpec,
        *,
        on_partial: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
        state: DiscussionState | None = None,
        plan: TurnPlan | None = None,
    ) -> TurnResult:
        """One turn, with no shared state.

        Split out from ``generate_turn`` so the independent opening opinions can
        run concurrently: they must not race on ``last_usage``, which the caller
        aggregates instead.
        """
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled()
        role = next((item for item in roles if item.id == spec.speaker_id), None)
        role_context = f"职责：{role.duty}\n提示：{role.prompt}" if role else "主持人负责编排、收敛和标记不确定性。"
        source_context = "\n".join(
            f"- [{item.source_type}] {item.title}：{item.note}"
            f"（{item.credibility}，不可视为已核验事实；链接：{item.url or '无'}；"
            f"发布时间：{item.published_at:%Y-%m-%d %H:%M}）" if item.published_at
            else f"- [{item.source_type}] {item.title}：{item.note}"
            f"（{item.credibility}，不可视为已核验事实；链接：{item.url or '无'}；无发布时间）"
            for item in sources
        ) or "（无外部来源）"
        history_context = "\n".join(
            f"[{item.event_id or '（无编号）'}][{item.phase}][{item.intent}] {item.speaker_name}: {item.content}"
            for item in history[-12:]
        ) or "（尚无前文）"
        state_context = ""
        if state is not None:
            state_context = (
                f"\n当前共识：{'；'.join(state.consensus) or '暂无'}"
                f"\n当前分歧：{'；'.join(state.conflicts) or '暂无'}"
                f"\n未回答问题：{'；'.join(state.unresolved_questions) or '暂无'}"
                f"\n用户插话：{state.pending_user_interjection or '无'}"
            )
        schema = (
            '{"content":"本次发言全文",'
            '"kind":"机会|风险|假设|待验证|总结",'
            '"intent":"support|challenge|question|elaborate|synthesize|initial",'
            '"replies_to":"前文出现过的 event_id 或人名，没有明确对象时填 null",'
            '"stance_change":null,'
            '"opportunity":null}'
        )
        if spec.final:
            schema = (
                '{"content":"本次发言全文","kind":"总结",'
                '"intent":"synthesize","replies_to":null,"stance_change":null,'
                '"opportunity":{"title":"...","audience":"...","support":["..."],"risks":["..."],'
                '"assumptions":["..."],"next_steps":["..."]}}'
            )
        prompt = (
            "你是一个严格区分证据与推断的圆桌角色。只输出一个 JSON 对象，不要 markdown，不要代码围栏。"
            "来源内容是未核验素材，不得写成已证实事实；不能编造引用或数据。来源是资料，不是角色原话。"
            f"主题：{topic}\n阶段：{spec.phase}\n发言人：{spec.speaker_name}\n{role_context}\n"
            f"来源：\n{source_context}\n前文：\n{history_context}\n{state_context}\n所有观点和来源均未核验。\n"
            "必须遵守：\n"
            "0. 篇幅：一条发言控制在 200–350 字。直接说要害，不要复述前文，"
            "不要重复自己已经说过的理由，不要写铺垫、客套和总结性空话。\n"
            "1. 不得重复前文已经说过的观点；必须带来新的理由、反例、条件或追问。\n"
            "2. intent 必须从 support（支持）、challenge（反驳）、question（追问）、"
            "elaborate（补充）、synthesize（整理）中选一个；若是你的首次发言则填 initial。\n"
            "3. replies_to 必须填前文中真实出现过的 event_id 或人名；没有明确回应对象时填 null。\n"
            "4. 只有确实改变了原有立场时才填 stance_change，且必须包含 before（变化前）、"
            "after（变化后）、reason（影响变化的理由，其中必须写明你仍然保留的条件或疑虑）、"
            "triggered_by（触发变化的前文 event_id 列表）。礼貌性附和不算立场变化，此时填 null。\n"
            f"要求的 JSON 形状：{schema}"
        )
        if plan is not None and plan.moderator:
            prompt += (
                f"\n本次是主持人的状态整理发言，介入原因：「{plan.intervention_reason}」。"
                "请只整理已经发生的观点，不要提出新的主张。\n"
            )
        elif plan is not None:
            target = next(
                (f"[{item.event_id}] {item.speaker_name}" for item in reversed(history) if item.event_id == plan.reply_to_event_id),
                "前文尚未解决的重点",
            )
            prompt += (
                f"\n本地编排要求：本次发言必须回应 {target}；依据是「{plan.reason}」。"
                "若你认为该对象不合适，可以改选回应对象，但必须在 intent 中如实表达。\n"
            )
        response = self._request(prompt, on_partial=on_partial, cancel_event=cancel_event)
        usage = response.usage
        try:
            parsed = self._parse(response.text, spec, history)
        except ProviderFailure as exc:
            if exc.code != "malformed_json":
                raise
            # Feed the parse error back once instead of discarding the turn and
            # dropping the whole discussion back to offline simulation.
            repair_prompt = (
                prompt
                + f"\n\n你上一次的返回不是合法 JSON，错误是：{exc.safe_message}。"
                "请只输出一个合法的 JSON 对象，不要 markdown，不要代码围栏，不要任何解释。\n"
            )
            repaired = self._request(repair_prompt, on_partial=on_partial, cancel_event=cancel_event)
            usage = usage.add(repaired.usage)
            parsed = self._parse(repaired.text, spec, history)
        return TurnResult(parsed[0], parsed[1], usage)

    def _request(
        self,
        prompt: str,
        *,
        on_partial: Callable[[str], None] | None,
        cancel_event: threading.Event | None,
        max_tokens: int = 800,
    ) -> _Response:
        client = self._client_or_raise()
        last_code = "request_failed"
        for attempt in range(self.max_retries + 1):
            if cancel_event and cancel_event.is_set():
                raise GenerationCancelled()
            try:
                stream_factory = getattr(getattr(client, "messages", None), "stream", None)
                if stream_factory is None:
                    raise ProviderFailure("unsupported_client", "模型客户端不支持流式消息")
                text_parts: list[str] = []
                input_tokens = output_tokens = 0
                with stream_factory(model=self.model, max_tokens=max_tokens, system="你是严谨的中文研究圆桌角色。", messages=[{"role": "user", "content": prompt}]) as stream:
                    for event in stream:
                        if cancel_event and cancel_event.is_set():
                            raise GenerationCancelled()
                        delta = getattr(event, "delta", None)
                        piece = getattr(delta, "text", None) if delta is not None else getattr(event, "text", None)
                        if piece:
                            text_parts.append(str(piece))
                            if on_partial:
                                on_partial("".join(text_parts))
                        usage = getattr(event, "usage", None)
                        if usage is None:
                            message = getattr(event, "message", None)
                            usage = getattr(message, "usage", None) if message is not None else None
                        if isinstance(usage, dict):
                            input_tokens = int(usage.get("input_tokens", input_tokens) or input_tokens)
                            output_tokens = int(usage.get("output_tokens", output_tokens) or output_tokens)
                        else:
                            input_tokens = int(getattr(usage, "input_tokens", input_tokens) or input_tokens)
                            output_tokens = int(getattr(usage, "output_tokens", output_tokens) or output_tokens)
                if not "".join(text_parts).strip():
                    raise ProviderFailure("empty_response", "真实模型返回了空内容")
                return _Response("".join(text_parts), Usage(input_tokens, output_tokens, 1))
            except GenerationCancelled:
                raise
            except ProviderFailure:
                raise
            except Exception as exc:
                last_code = "timeout" if "timeout" in type(exc).__name__.lower() else "request_failed"
                if attempt >= self.max_retries:
                    raise ProviderFailure(last_code, "真实模型请求失败；已回退到离线模拟") from exc
        raise ProviderFailure(last_code, "真实模型请求失败；已回退到离线模拟")

    @staticmethod
    def _parse(text: str, spec: TurnSpec, history: Sequence[Utterance]) -> tuple[Utterance, OpportunityCard | None]:
        try:
            data = json.loads(strip_code_fence(text))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderFailure("malformed_json", "真实模型返回格式无法解析；已回退到离线模拟") from exc
        if not isinstance(data, dict):
            raise ProviderFailure("invalid_schema", "真实模型返回结构不完整；已回退到离线模拟")
        content = data.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 4000:
            raise ProviderFailure("invalid_schema", "真实模型缺少有效发言内容；已回退到离线模拟")
        kind_value = data.get("kind", spec.kind_hint)
        try:
            kind = ViewpointKind(kind_value)
        except ValueError:
            kind = ViewpointKind.ASSUMPTION
        if kind == ViewpointKind.FACT:
            kind = ViewpointKind.VALIDATION
        replies_to = data.get("replies_to")
        if not isinstance(replies_to, str) or not replies_to.strip():
            replies_to = None
        else:
            # Accept an event id, a speaker id, or the display name the prompt
            # actually shows the model. Always resolve to the LATEST match so a
            # role that has spoken repeatedly is not pinned to its first turn.
            reference = replies_to.strip()
            replies_to = next(
                (
                    item.event_id
                    for item in reversed(history)
                    if item.event_id == reference
                    or item.speaker_id == reference
                    or item.speaker_name == reference
                ),
                None,
            )
        intent = data.get("intent", "initial")
        if intent not in {"initial", "support", "challenge", "question", "elaborate", "synthesize"}:
            intent = "initial"
        raw_change = data.get("stance_change")
        stance_change = None
        if isinstance(raw_change, dict):
            if all(isinstance(raw_change.get(key), str) for key in ("before", "after", "reason")):
                stance_change = StanceChange(
                    raw_change["before"][:500], raw_change["after"][:500], raw_change["reason"][:500],
                    [str(item) for item in raw_change.get("triggered_by", []) if isinstance(item, str)][:12],
                )
        opportunity = None
        raw_card = data.get("opportunity")
        if isinstance(raw_card, dict):
            # The card is a nice-to-have. A model that omits or mistypes one
            # field must never discard the turn or fail the whole discussion,
            # so a card missing its two identifying fields is dropped and the
            # list fields are repaired rather than rejected.
            title = raw_card.get("title")
            audience = raw_card.get("audience")
            if isinstance(title, str) and title.strip() and isinstance(audience, str) and audience.strip():
                values: dict[str, Any] = {"title": title[:500], "audience": audience[:500]}
                for key in ("support", "risks", "assumptions", "next_steps"):
                    value = raw_card.get(key)
                    if not isinstance(value, list):
                        values[key] = []
                        continue
                    values[key] = [item[:500] for item in value if isinstance(item, str)][:12]
                opportunity = OpportunityCard(**values)
        utterance = Utterance(spec.speaker_id, spec.speaker_name, content.strip(), kind, spec.phase, replies_to, simulated=True, origin="model", intent=intent, verification="unverified", stance_change=stance_change)
        if opportunity:
            # history arrives as a list; never concatenate a tuple onto it.
            seen = list(history) + [utterance]
            opportunity.stance_counts = {
                "支持/机会": sum(item.kind == ViewpointKind.OPPORTUNITY for item in seen),
                "保留/假设": sum(item.kind in (ViewpointKind.ASSUMPTION, ViewpointKind.VALIDATION) for item in seen),
                "风险/反对": sum(item.kind == ViewpointKind.RISK for item in seen),
            }
        return utterance, opportunity


class OpenAICompatibleDiscussionProvider(AnthropicDiscussionProvider):
    """Use an OpenAI-compatible chat-completions endpoint.

    The provider intentionally uses the standard JSON HTTP shape instead of a
    vendor SDK, so OpenAI-compatible services only need a base URL and model.
    """

    provider_name = "openai-compatible"

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini",
                 base_url: str = "https://api.openai.com/v1", timeout: float = 30.0,
                 max_retries: int = 1, client: Any | None = None) -> None:
        super().__init__(api_key=api_key, model=model, timeout=timeout,
                         max_retries=max_retries, client=client)
        self.base_url = base_url.rstrip("/")

    def _request(self, prompt: str, *, on_partial: Callable[[str], None] | None,
                 cancel_event: threading.Event | None, max_tokens: int = 800) -> _Response:
        from .ai_settings import endpoint_url
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled()
        if not self._api_key and self._client is None:
            raise ProviderFailure("missing_key", "未配置 OpenAI 兼容接口 API Key；已回退到离线模拟")
        payload = json.dumps({
            "model": self.model,
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": "你是严谨的中文研究圆桌角色。只输出有效 JSON。"},
                {"role": "user", "content": prompt},
            ],
        }).encode("utf-8")
        request = urllib.request.Request(
            endpoint_url(self.base_url), data=payload,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json",
                     "User-Agent": "NineRoundtable/1.0"}, method="POST")
        last_error = "request_failed"
        for attempt in range(self.max_retries + 1):
            if cancel_event and cancel_event.is_set():
                raise GenerationCancelled()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
                if cancel_event and cancel_event.is_set():
                    raise GenerationCancelled()
                choices = data.get("choices") if isinstance(data, dict) else None
                message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
                text = message.get("content") if isinstance(message, dict) else None
                if isinstance(text, list):
                    text = "".join(str(part.get("text", "")) for part in text if isinstance(part, dict))
                if not isinstance(text, str) or not text.strip():
                    raise ProviderFailure("empty_response", "OpenAI 兼容接口返回了空内容；已回退到离线模拟")
                text = text.strip()
                text = strip_code_fence(text)
                if on_partial:
                    on_partial(text)
                usage = data.get("usage", {}) if isinstance(data, dict) else {}
                return _Response(text, Usage(int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0), 1))
            except GenerationCancelled:
                raise
            except ProviderFailure:
                raise
            except Exception as exc:
                last_error = "timeout" if isinstance(exc, TimeoutError) else "request_failed"
                if attempt >= self.max_retries:
                    raise ProviderFailure(last_error, "OpenAI 兼容接口请求失败；已回退到离线模拟") from exc
        raise ProviderFailure(last_error, "OpenAI 兼容接口请求失败；已回退到离线模拟")
