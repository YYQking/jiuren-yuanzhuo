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
from dataclasses import dataclass, field, replace
from typing import Any

from .jsonutil import strip_code_fence
from .orchestration import (
    OrchestrationRefresh,
    Review,
    build_orchestration_prompt,
    build_review_prompt,
    parse_orchestration,
    parse_review,
)
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
from .turn_planner import MODERATOR_ID, TurnPlan, enforce_fairness, plan_turn
from .roles import mode_for_roles
from .voice import ANTI_TEMPLATE_RULES, length_instruction, looks_templated

# How much of the discussion a single turn may read.  Full text for the recent
# window, plus one line per role for the opening positions, so a long discussion
# does not silently lose the question it started from.
RECENT_TURNS = 12
TARGET_QUOTE_LIMIT = 240
OPENING_QUOTE_LIMIT = 120
MAX_OPENING_POSITIONS = 9

# Event section: how many utterances a seat must stay on one face before it may
# flip again.  Without this the same seat oscillates every turn.
FACE_COOLDOWN = 3


def _render_opening_positions(history: Sequence[Utterance], *, exclude_event_id: str | None = None) -> str:
    """One line per role: the position it opened with.

    Only the first turn of each role, and only when it has already dropped out of
    the recent window -- otherwise the same text would appear twice in one prompt.
    ``exclude_event_id`` drops the utterance the turn directive already quotes.
    """
    recent_ids = {item.event_id for item in history[-RECENT_TURNS:]}
    seen: set[str] = set()
    lines: list[str] = []
    for item in history:
        if item.speaker_id in {"moderator", "user"} or item.speaker_id in seen:
            continue
        seen.add(item.speaker_id)
        if item.event_id in recent_ids or item.event_id == exclude_event_id:
            continue
        lines.append(f"[{item.event_id}] {item.speaker_name}：{item.content[:OPENING_QUOTE_LIMIT]}")
        if len(lines) >= MAX_OPENING_POSITIONS:
            break
    if not lines:
        return ""
    return "各角色最初立场（讨论早期，可能已被后文修正）：\n" + "\n".join(lines) + "\n"


def current_face(history: Sequence[Utterance], speaker_id: str) -> str:
    """The face this seat is showing, or "" if it has not spoken yet."""
    for item in reversed(history):
        if item.speaker_id == speaker_id and item.face in {"yang", "yin"}:
            return item.face
    return ""


def resolve_face(history: Sequence[Utterance], speaker_id: str, requested: object) -> str:
    """Decide which face this turn actually shows.

    The program owns this rule, because the real model never asked to flip (19
    turns of a live run were 19 阳面).  A seat opens on its 阳面 and then
    alternates every time it comes back after ``FACE_COOLDOWN`` utterances have
    passed since its own previous turn; inside the cooldown it keeps the face it
    had.  ``requested`` is accepted so the call site stays uniform, but it does
    not get to freeze a seat on one face.

    Returning "" would lose the state, so the opener of a seat always gets an
    explicit "yang".
    """
    current = current_face(history, speaker_id)
    if not current:
        return "yang"
    indices = [index for index, item in enumerate(history) if item.speaker_id == speaker_id]
    if not indices:
        return current
    if len(history) - 1 - indices[-1] < FACE_COOLDOWN:
        return current
    return "yin" if current == "yang" else "yang"


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


def _viewpoint_kind(value: object, hint: str = "") -> ViewpointKind:
    """Map the model's kind word to a known kind, else to the planned one.

    A model answering with a word we do not know used to be relabelled 假设, so
    the moderator's closing summary showed up as "主持人 · 假设" on screen.  The
    local plan already knows what this turn is; use it before guessing.
    """
    for candidate in (value, hint):
        if isinstance(candidate, ViewpointKind):
            return candidate
        try:
            return ViewpointKind(str(candidate))
        except ValueError:
            continue
    return ViewpointKind.ASSUMPTION


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
        # Set by the last extend_batch call. The controller reads these on the GUI
        # thread rather than letting the worker touch the shared session.
        self.last_state_refresh: OrchestrationRefresh | None = None
        self.last_review: Review | None = None

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
        session = DiscussionSession(topic=topic.strip(), sources=source_items, source=source_items[0] if source_items else None, selected_role_ids=[r.id for r in selected], mode=mode_for_roles(selected))
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

    def orchestrate(
        self,
        session: DiscussionSession,
        roles: Sequence[Role],
        local: TurnPlan,
        state: DiscussionState | None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> tuple[TurnPlan, OrchestrationRefresh]:
        """Let the model decide the turn, and refresh the state in the same call."""
        prompt = build_orchestration_prompt(session, roles, local, state)
        response = self._request(prompt, on_partial=None, cancel_event=cancel_event)
        self.last_usage = self.last_usage.add(response.usage)
        return parse_orchestration(response.text, session, roles, local)

    def review_turn(
        self,
        session: DiscussionSession,
        plan: TurnPlan,
        utterance: Utterance,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Review:
        """Judge whether the turn that just came back actually advanced things."""
        prompt = build_review_prompt(session, plan, utterance)
        response = self._request(prompt, on_partial=None, cancel_event=cancel_event)
        self.last_usage = self.last_usage.add(response.usage)
        return parse_review(response.text)

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
        local = plan_turn(session, selected, state)
        self.last_state_refresh = None
        self.last_review = None
        plan = local
        try:
            # The local planner supplies exact structural facts (who owes a reply,
            # which question is unanswered); the model decides what actually
            # matters and what this turn must answer.
            plan, refresh = self.orchestrate(session, selected, local, state, cancel_event=cancel_event)
            self.last_state_refresh = refresh
            if not plan.moderator:
                # The model chooses who is best placed to answer; the local caps
                # still decide whether that role has held the floor too long.
                plan = enforce_fairness(plan, session, selected)
        except (ProviderFailure, ValueError):
            # Honest fallback: keep the structural plan instead of dropping the turn.
            plan = local

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
        # Review the host's summary exactly like a role turn: it is the turn most
        # likely to be a bland restatement, so it must not be the one turn that
        # skips the check.
        try:
            review = self.review_turn(session, plan, result.utterance, cancel_event=cancel_event)
        except (ProviderFailure, ValueError):
            # A failed review must never block the discussion; the turn stands.
            return [result.utterance]
        self.last_review = review
        if review.passed:
            return [result.utterance]

        # Ask for one rewrite, carrying the concrete criticism back to the model.
        # A dedicated directive, not the review prompt: that one asks for a
        # different JSON shape and would fight with the turn schema above.
        rewrite_prompt = (
            f"\n质检判定这条发言不合格，具体批评是：{review.criticism}。\n"
            f"你上一次的发言是：「{result.utterance.content[:400]}」\n"
            "请重写这一条发言：直接解决上述批评，不要重复批评里指出的内容，"
            "必须回答被指派的问题，不要编造来源材料里没有的数据。\n"
        )
        try:
            rewritten = self._generate_turn_result(
                session.topic,
                selected,
                list(session.sources),
                list(session.utterances),
                TurnSpec(plan.speaker_id, plan.speaker_name, plan.phase, plan.kind_hint),
                on_partial=(lambda text: on_partial(speaker.name, text)) if on_partial else None,
                cancel_event=cancel_event,
                state=state,
                plan=plan,
                extra_prompt=rewrite_prompt,
            )
        except (ProviderFailure, ValueError):
            return [result.utterance]
        self.last_usage = self.last_usage.add(rewritten.usage)
        # Record that this turn was sent back, and why.  Without it nothing in the
        # app can show whether the rewrite path ever runs.
        return [replace(rewritten.utterance, review_note=review.criticism[:500])]

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
        extra_prompt: str = "",
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
            for item in history[-RECENT_TURNS:]
        ) or "（尚无前文）"
        opening_context = _render_opening_positions(
            history, exclude_event_id=plan.reply_to_event_id if plan is not None else None
        )
        state_context = ""
        if state is not None:
            state_context = (
                f"\n当前共识：{'；'.join(state.consensus) or '暂无'}"
                f"\n当前分歧：{'；'.join(state.conflicts) or '暂无'}"
                f"\n未回答问题：{'；'.join(state.unresolved_questions) or '暂无'}"
                f"\n用户插话：{state.pending_user_interjection or '无'}"
            )
        mode = mode_for_roles(roles)
        event = mode == "event"
        face_context = ""
        if event and spec.speaker_id != "moderator":
            shown = current_face(history, spec.speaker_id)
            face = resolve_face(history, spec.speaker_id, None)
            label = "阳面" if face == "yang" else "阴面"
            material = ""
            if role is not None:
                material = role.yang if face == "yang" else role.yin
            if not shown:
                face_context = f"\n这是你在这张桌上第一次开口。这一条你在{label}（{material}）。\n"
            else:
                face_context = (
                    f"\n这一条你在{label}（{material}）。"
                    f"你上一次用的是{'阳面' if shown == 'yang' else '阴面'}；"
                    "翻了面就直接按这一面说话，不要解释自己为什么变脸。\n"
                )
        schema = (
            '{"content":"本次发言全文",'
            '"kind":"机会|风险|假设|待验证|总结",'
            '"intent":"support|challenge|question|elaborate|synthesize|initial",'
            '"replies_to":"前文出现过的 event_id 或人名，没有明确对象时填 null",'
            + ('"face":"yang|yin",' if event else "")
            + '"stance_change":null,'
            '"opportunity":null}'
        )
        if spec.final:
            schema = (
                '{"content":"本次发言全文","kind":"总结",'
                '"intent":"synthesize","replies_to":null,'
                + ('"face":null,' if event else "")
                + '"stance_change":null,'
                '"opportunity":{"title":"...","audience":"...","support":["..."],"risks":["..."],'
                '"assumptions":["..."],"next_steps":["..."]}}'
            )
        if event:
            rules = (
                "口语，可以带情绪，像在饭桌上说话；不要写成发言稿，不要打官腔。\n"
                "1. 可信度只说一种：你确认的写「我知道」并说出公开出处；听来的写「听说」；"
                "自己推断的写「我猜」。三者不能混，听说的绝不能写成确认的。"
                "但不要在每条发言里把三种按顺序摆一遍——一条通常只用一种，够用就停。\n"
                "2. 可以刻薄，不许造谣：不编造私生活细节，不编造没有出处的实锤，不给真实普通人扣帽子。\n"
                "3. kind 用八卦口径：机会=看好这事、风险=觉得要出事、假设=听说的、待验证=还没证实、"
                "事实=已确认、总结=归纳。没被证实的说法一律不要填「事实」。\n"
                "4. 这一条用哪一面由程序决定，已经写在给你的「这一条你在X面」里，照它说就行："
                "阳面是体面、讲道理那面；阴面是刻薄、多疑、翻旧账那面。"
                "换了面就直接按这一面说话，不用解释自己为什么变脸，也别声明「我现在是阴面」。\n"
                "5. 不得重复前文说过的观点；要带来新消息、新角度或新反例。\n"
                "6. intent 从 support（认同）、challenge（反对）、question（追问）、"
                "elaborate（补充）、synthesize（归纳）里选；首次发言填 initial。\n"
                "7. replies_to 必须填前文真实出现过的 event_id 或人名；没有明确对象填 null。\n"
                "8. 只有真的改变判断时才填 stance_change（before/after/reason/triggered_by）；嘴硬或附和不算。\n"
                "9. 不要给建议，不要写「下一步行动」和「目标用户」；你是在聊这件事，不是在交付方案。\n"
            )
            persona = "你是中文熟人饭桌上的一位，正在聊一件社会上发生的事。"
        else:
            rules = (
                "1. 不得重复前文已经说过的观点；必须带来新的理由、反例、条件或追问。\n"
                "2. intent 必须从 support（支持）、challenge（反驳）、question（追问）、"
                "elaborate（补充）、synthesize（整理）中选一个；若是你的首次发言则填 initial。\n"
                "3. replies_to 必须填前文中真实出现过的 event_id 或人名；没有明确回应对象时填 null。\n"
                "4. 只有确实改变了原有立场时才填 stance_change，且必须包含 before（变化前）、"
                "after（变化后）、reason（影响变化的理由，其中必须写明你仍然保留的条件或疑虑）、"
                "triggered_by（触发变化的前文 event_id 列表）。礼貌性附和不算立场变化，此时填 null。\n"
            )
            persona = "你是一个严格区分证据与推断的圆桌角色。"
        length_hint = plan.length_hint if plan is not None else "normal"
        length_rule = f"0. 篇幅：{length_instruction(length_hint)}\n"
        voice_context = ""
        if role is not None and role.voice:
            voice_context = f"你说话的习惯：{role.voice}\n"
        prompt = (
            f"{persona}只输出一个 JSON 对象，不要 markdown，不要代码围栏。"
            "来源内容是未核验素材，不得写成已证实事实；不能编造引用或数据。来源是资料，不是角色原话。"
            f"主题：{topic}\n阶段：{spec.phase}\n发言人：{spec.speaker_name}\n{role_context}\n{voice_context}"
            f"来源：\n{source_context}\n前文：\n{history_context}\n{opening_context}{state_context}{face_context}\n所有观点和来源均未核验。\n"
            "必须遵守：\n"
            f"{length_rule}{rules}"
            f"{ANTI_TEMPLATE_RULES}"
            f"要求的 JSON 形状：{schema}"
        )
        if event and spec.final:
            prompt += (
                "\n最后的整理仍用同一个 JSON 的 opportunity 字段装成「吃瓜纪要」："
                "title=这事儿到底算什么，audience=牵扯到谁（用化名，不要写真实普通人的姓名），"
                "support=有实锤的部分，risks=吵得最凶的点，assumptions=还只是传言，"
                "next_steps=接下来看什么。\n"
            )
        if plan is not None and plan.moderator:
            prompt += (
                f"\n本次是主持人的状态整理发言，介入原因：「{plan.intervention_reason}」。"
                "请只整理已经发生的观点，不要提出新的主张。\n"
                "说法要像饭桌上有人出来压一句：直接点名一个还没被回答的人，逼他回一个具体问题；"
                "先给一句你自己的判断（谁在绕、哪句没接住），再点人。不要复述观点清单，"
                "不要用「首先/其次/最后」分条。\n"
            )
        elif plan is not None:
            target_item = next(
                (item for item in reversed(history) if item.event_id == plan.reply_to_event_id),
                None,
            )
            # The reply target can be far older than the rendered window, and a
            # role cannot answer an utterance it cannot read: measured with a
            # 21-turn history, the directive named [event-000000] while its text
            # was nowhere in the prompt.
            target = (
                f"[{target_item.event_id}] {target_item.speaker_name}：「{target_item.content[:TARGET_QUOTE_LIMIT]}」"
                if target_item is not None
                else "前文尚未解决的重点"
            )
            required = plan.must_answer or plan.reason
            avoid = f"必须避免重复：{'；'.join(plan.avoid)}。\n" if plan.avoid else ""
            source_note = "编排要求" if plan.source == "model" else "本地编排要求"
            prompt += (
                f"\n{source_note}：本次发言必须回应 {target}，并且必须回答：{required}。"
                f"{avoid}"
                "第一句就点出你要回应的那个人的名字，不要对着空气说话。"
                "若你认为回应对象不合适，可以改选，但必须在 intent 中如实表达。\n"
            )
        if extra_prompt:
            prompt += extra_prompt
        response = self._request(
            prompt, on_partial=on_partial, cancel_event=cancel_event,
            system=self._system_prompt(event),
        )
        usage = response.usage
        try:
            parsed = self._parse(response.text, spec, history, event=event)
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
            repaired = self._request(
                repair_prompt, on_partial=on_partial, cancel_event=cancel_event,
                system=self._system_prompt(event),
            )
            usage = usage.add(repaired.usage)
            parsed = self._parse(repaired.text, spec, history, event=event)
        utterance = parsed[0]
        # One re-ask when the turn opens with a stock phrase.  Measured on a real
        # transcript: six of eight opening turns began with 「我先说…」, which is
        # what made the table sound like one template being filled in.
        complaint = looks_templated(utterance.content)
        if complaint and spec.speaker_id != MODERATOR_ID:
            retry_prompt = (
                prompt
                + f"\n\n你上一次的发言{complaint}。请重写这一条：删掉开头的套话，"
                "第一句直接说内容，篇幅按上面的要求，只做一件事。\n"
            )
            retried = self._request(
                retry_prompt, on_partial=on_partial, cancel_event=cancel_event,
                system=self._system_prompt(event),
            )
            usage = usage.add(retried.usage)
            try:
                parsed = self._parse(retried.text, spec, history, event=event)
            except ProviderFailure:
                # Keep the first answer rather than losing the turn over style.
                parsed = (utterance, parsed[1])
            else:
                utterance = parsed[0]
        return TurnResult(utterance, parsed[1], usage)

    @staticmethod
    def _system_prompt(event: bool) -> str:
        """System message for this turn.  The event section deliberately stops
        claiming to be a research roundtable: it is a table of ordinary people."""
        if event:
            return "你是中文熟人饭桌上的一个普通人，正在聊一件社会上的事。只输出有效 JSON。"
        return "你是严谨的中文研究圆桌角色。只输出有效 JSON。"

    def _request(
        self,
        prompt: str,
        *,
        on_partial: Callable[[str], None] | None,
        cancel_event: threading.Event | None,
        max_tokens: int = 800,
        system: str = "",
    ) -> _Response:
        system_text = system or "你是严谨的中文研究圆桌角色。"
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
                with stream_factory(model=self.model, max_tokens=max_tokens, system=system_text, messages=[{"role": "user", "content": prompt}]) as stream:
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
    def _parse(text: str, spec: TurnSpec, history: Sequence[Utterance],
               *, event: bool = False) -> tuple[Utterance, OpportunityCard | None]:
        try:
            data = json.loads(strip_code_fence(text))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderFailure("malformed_json", "真实模型返回格式无法解析；已回退到离线模拟") from exc
        if not isinstance(data, dict):
            raise ProviderFailure("invalid_schema", "真实模型返回结构不完整；已回退到离线模拟")
        content = data.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 4000:
            raise ProviderFailure("invalid_schema", "真实模型缺少有效发言内容；已回退到离线模拟")
        kind = _viewpoint_kind(data.get("kind", spec.kind_hint), spec.kind_hint)
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
        face = ""
        if event and spec.speaker_id != "moderator":
            face = resolve_face(history, spec.speaker_id, data.get("face"))
        utterance = Utterance(spec.speaker_id, spec.speaker_name, content.strip(), kind, spec.phase, replies_to, simulated=True, origin="model", intent=intent, verification="unverified", stance_change=stance_change, face=face)
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
                 cancel_event: threading.Event | None, max_tokens: int = 800,
                 system: str = "") -> _Response:
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
                {"role": "system", "content": system or "你是严谨的中文研究圆桌角色。只输出有效 JSON。"},
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
