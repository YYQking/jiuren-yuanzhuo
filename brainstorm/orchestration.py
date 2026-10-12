"""Model-driven orchestration and quality control around each generated turn.

The local planner answers structural questions exactly -- who owes a reply,
which question is unanswered, who has been silent -- but it cannot judge what the
discussion is actually about.  That is the difference between a roundtable that
rotates speakers and one that advances a question.

This module adds the two model calls that can:

* ``build_orchestration_prompt`` / ``parse_orchestration`` read the whole stream,
  decide the single most important open question, pick who speaks next, say what
  that turn must answer, list what it must not repeat, and refresh the discussion
  state -- all in one request.
* ``build_review_prompt`` / ``parse_review`` judge whether the turn that came back
  actually advanced the discussion, and produce a concrete criticism when it did
  not, so the caller can ask for one rewrite.

Both halves are pure prompt-builders and parsers; the provider performs the
request.  Every parse failure raises ``ValueError`` so the caller can fall back to
the local plan rather than losing the turn.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from .jsonutil import load_json_object
from .models import DiscussionSession, DiscussionState, Role, Utterance
from .turn_planner import MODERATOR_ID, TurnPlan

HISTORY_LIMIT = 24
MAX_LIST_ITEMS = 4
MAX_AVOID_ITEMS = 3


@dataclass(frozen=True)
class OrchestrationRefresh:
    """The state the orchestrator reads out of the stream in the same request."""

    consensus: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True)
class Review:
    passed: bool
    repeats: str = ""
    avoided: str = ""
    fabricated: str = ""

    @property
    def criticism(self) -> str:
        return "；".join(part for part in (self.repeats, self.avoided, self.fabricated) if part)


def render_event_stream(session: DiscussionSession, *, limit: int = HISTORY_LIMIT) -> str:
    rendered = []
    for item in session.utterances[-limit:]:
        target = f" →{item.replies_to}" if item.replies_to else ""
        rendered.append(
            f"[{item.event_id or '（无编号）'}][{item.phase}][{item.intent}]{target} "
            f"{item.speaker_name}: {item.content}"
        )
    return "\n".join(rendered) or "（尚无前文）"


def render_local_facts(plan: TurnPlan) -> str:
    return f"发言人={plan.speaker_name}({plan.speaker_id})；阶段={plan.phase}；理由={plan.reason}"


def _render_roster(roles: Sequence[Role]) -> str:
    listed = [f"- {role.id}｜{role.name}：{role.duty}" for role in roles if role.id != MODERATOR_ID]
    return "\n".join(listed) or "（无）"


def build_orchestration_prompt(session: DiscussionSession, roles: Sequence[Role], local: TurnPlan,
                               state: DiscussionState | None = None) -> str:
    state_note = ""
    if state is not None and (state.consensus or state.conflicts or state.unresolved_questions):
        state_note = (
            f"\n上一轮记录的状态（可能过时，请以事件流为准）："
            f"共识={'；'.join(state.consensus) or '无'}；"
            f"分歧={'；'.join(state.conflicts) or '无'}；"
            f"未解决={'；'.join(state.unresolved_questions) or '无'}"
        )
    return (
        "你是这场九人圆桌讨论的编排者。你的任务不是发表观点，而是读完事件流后做出编排决定。\n"
        "只输出一个 JSON 对象，不要 markdown，不要代码围栏，不要解释。\n"
        f"主题：{session.topic}\n"
        f"可选角色：\n{_render_roster(roles)}\n"
        f"事件流：\n{render_event_stream(session)}\n"
        f"本地结构分析的建议（仅供参考，你可以推翻）：{render_local_facts(local)}{state_note}\n"
        "事件流里的所有观点和外部素材都是未核验内容，不能当成已证实事实。\n"
        "必须遵守：\n"
        "1. key_question 只写一个当前最关键、尚未解决的问题，要具体到可回答。\n"
        "2. speaker_id 必须从上面的角色 id 里选；只有需要做状态整理时才填 moderator。\n"
        "3. must_answer 要明确写出这一条发言必须回答什么，不能写泛泛的方向。\n"
        f"4. avoid 列出这条发言必须避免重复的已有点，最多 {MAX_AVOID_ITEMS} 条。\n"
        "5. 只有命中以下情况才把 speaker_id 填成 moderator 并把 intervene 设为 true："
        "已出现重要共识、重复观点明显增加、讨论冷场、某个分歧已充分交锋、新观点明显减少。"
        "此时 intervention_reason 必须写明是这五种里的哪一种。\n"
        f"6. consensus／conflicts／unresolved 各最多 {MAX_LIST_ITEMS} 条，"
        "只能写事件流里真实出现过的内容，不得编造；没有就写空数组。\n"
        "JSON 形状："
        '{"key_question":"...","speaker_id":"trend","must_answer":"...","avoid":["..."],'
        '"intervene":false,"intervention_reason":"","consensus":["..."],"conflicts":["..."],"unresolved":["..."]}'
    )


def _clean_list(value: object, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item)[:500] for item in value if isinstance(item, str) and item.strip())[:limit]


def parse_orchestration(text: str, session: DiscussionSession, roles: Sequence[Role],
                        local: TurnPlan) -> tuple[TurnPlan, OrchestrationRefresh]:
    """Turn the model's decision into a plan. Raises ValueError when unusable."""
    data = load_json_object(text)

    speaker_id = data.get("speaker_id")
    if not isinstance(speaker_id, str) or not speaker_id.strip():
        raise ValueError("编排结果缺少 speaker_id")
    speaker_id = speaker_id.strip()
    known = {role.id for role in roles}
    if speaker_id != MODERATOR_ID and speaker_id not in known:
        raise ValueError(f"编排结果给出了不存在的角色：{speaker_id}")

    must_answer = data.get("must_answer")
    if not isinstance(must_answer, str) or not must_answer.strip():
        raise ValueError("编排结果缺少 must_answer")
    key_question = data.get("key_question")
    key_question = key_question.strip()[:500] if isinstance(key_question, str) else ""

    reason = data.get("intervention_reason")
    reason = reason.strip() if isinstance(reason, str) else ""

    if speaker_id == MODERATOR_ID:
        if not reason:
            reason = "需要主持人整理当前讨论"
        plan = replace(
            local,
            speaker_id=MODERATOR_ID,
            speaker_name="主持人",
            phase="状态整理",
            intent="synthesize",
            kind_hint="总结",
            moderator=True,
            intervention_reason=reason,
            must_answer=must_answer.strip()[:500],
            key_question=key_question,
            reason=reason,
            source="model",
        )
    else:
        speaker = next(role for role in roles if role.id == speaker_id)
        plan = replace(
            local,
            speaker_id=speaker.id,
            speaker_name=speaker.name,
            moderator=False,
            intervention_reason="",
            must_answer=must_answer.strip()[:500],
            key_question=key_question,
            avoid=_clean_list(data.get("avoid"), MAX_AVOID_ITEMS),
            source="model",
        )

    refresh = OrchestrationRefresh(
        consensus=_clean_list(data.get("consensus"), MAX_LIST_ITEMS),
        conflicts=_clean_list(data.get("conflicts"), MAX_LIST_ITEMS),
        unresolved=_clean_list(data.get("unresolved"), MAX_LIST_ITEMS),
    )
    return plan, refresh


def build_review_prompt(session: DiscussionSession, plan: TurnPlan, utterance: Utterance) -> str:
    required = plan.must_answer or "推进当前尚未解决的关键问题"
    avoid = "；".join(plan.avoid) if plan.avoid else "无"
    return (
        "你是这场圆桌讨论的质检者。判断下面这一条刚生成的发言是否真的推进了讨论。\n"
        "只输出一个 JSON 对象，不要 markdown，不要代码围栏，不要解释。\n"
        f"主题：{session.topic}\n"
        f"本次被指派必须回答：{required}\n"
        f"本次必须避免重复：{avoid}\n"
        f"事件流：\n{render_event_stream(session)}\n"
        f"刚生成的发言（发言人：{utterance.speaker_name}）：\n{utterance.content}\n"
        "逐项检查并给出具体证据，不要写空泛评语：\n"
        "1. repeats：是否只是重复前文已有观点？是则指出重复的是哪个 event_id 或哪一句，否则留空。\n"
        "2. avoided：是否回避了本次被指派必须回答的内容？是则指出回避了什么，否则留空。\n"
        "3. fabricated：是否编造了来源材料中不存在的数据、引用或事实？是则指出编造了什么，否则留空。\n"
        "任意一项非空即视为不合格，passed 必须为 false。\n"
        'JSON 形状：{"passed":true,"repeats":"","avoided":"","fabricated":""}'
    )


def parse_review(text: str) -> Review:
    data = load_json_object(text)
    if "passed" not in data:
        raise ValueError("质检结果缺少 passed")

    def field(name: str) -> str:
        value = data.get(name)
        return value.strip()[:500] if isinstance(value, str) else ""

    repeats, avoided, fabricated = field("repeats"), field("avoided"), field("fabricated")
    # A model that reports a concrete problem has failed the review whatever it
    # wrote in passed; the concrete finding is worth more than the verdict.
    passed = bool(data.get("passed")) and not (repeats or avoided or fabricated)
    return Review(passed=passed, repeats=repeats, avoided=avoided, fabricated=fabricated)
