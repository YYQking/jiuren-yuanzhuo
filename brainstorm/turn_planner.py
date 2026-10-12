"""Local, network-free structural analysis for speaker scheduling.

This module answers only what the recorded event stream can answer exactly:
who owes a reply, which question is still unanswered, who has been silent too
long.  It deliberately does NOT judge semantic relevance -- deciding who is
best placed to answer belongs to the model-driven orchestrator.  Its output is
therefore both an input to that orchestrator and the fallback plan used when
the model is unavailable or suggests an impossible speaker.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .models import DiscussionSession, DiscussionState, Role, Utterance

MODERATOR_ID = "moderator"
USER_ID = "user"

# Bounds keep every rule local and cheap: a stale interjection or a very old
# question must not steer the discussion forever.
USER_WINDOW = 6
QUESTION_WINDOW = 12
MAX_SILENT_TURNS = 3
MAX_CONSECUTIVE_SAME_SPEAKER = 2


@dataclass(frozen=True)
class TurnPlan:
    """One scheduled turn. ``reason`` is always a real local trigger, never text."""

    speaker_id: str
    speaker_name: str
    phase: str
    intent: str
    kind_hint: str = "假设"
    reply_to_event_id: str | None = None
    reason: str = ""
    moderator: bool = False
    intervention_reason: str = ""
    source: str = "local"


def _role_utterances(session: DiscussionSession) -> list[Utterance]:
    return [item for item in session.utterances if item.speaker_id not in {MODERATOR_ID, USER_ID}]


def _replied_ids(session: DiscussionSession) -> set[str]:
    return {item.replies_to for item in _role_utterances(session) if item.replies_to}


def _speaker_counts(session: DiscussionSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _role_utterances(session):
        counts[item.speaker_id] = counts.get(item.speaker_id, 0) + 1
    return counts


def _last_index(session: DiscussionSession, speaker_id: str) -> int:
    for index in range(len(session.utterances) - 1, -1, -1):
        if session.utterances[index].speaker_id == speaker_id:
            return index
    return -1


def _turns_since_spoke(session: DiscussionSession, speaker_id: str) -> int:
    last = _last_index(session, speaker_id)
    if last < 0:
        return len(session.utterances) + 1
    return sum(1 for item in session.utterances[last + 1:] if item.speaker_id not in {MODERATOR_ID, USER_ID})


def _least_spoken(candidates: Sequence[Role], session: DiscussionSession, exclude: Sequence[str] = ()) -> Role | None:
    """Fewest utterances first; ties broken by who spoke longest ago."""
    blocked = set(exclude)
    pool = [role for role in candidates if role.id not in blocked]
    if not pool:
        return None
    counts = _speaker_counts(session)
    return min(pool, key=lambda role: (counts.get(role.id, 0), _last_index(session, role.id)))


def _role_by_reference(candidates: Sequence[Role], session: DiscussionSession, reference: str | None) -> Role | None:
    """Accept an event_id, a speaker_id or a display name."""
    if not reference:
        return None
    speaker_id = next((item.speaker_id for item in session.utterances if item.event_id == reference), None)
    if speaker_id is None:
        speaker_id = next(
            (
                item.speaker_id
                for item in session.utterances
                if item.speaker_id == reference or item.speaker_name == reference
            ),
            None,
        )
    return next((role for role in candidates if role.id == speaker_id), None)


def _roles_from_history(session: DiscussionSession) -> list[Role]:
    found: dict[str, str] = {}
    for item in session.utterances:
        if item.speaker_id in {MODERATOR_ID, USER_ID}:
            continue
        found.setdefault(item.speaker_id, item.speaker_name)
    return [Role(role_id, name, "", "#b08d50", "") for role_id, name in found.items()]


def mark_duplicates(session: DiscussionSession) -> int:
    """Flag repeats of an earlier role turn. Never deletes anything.

    The protocol requires repeated content to stay in the record with only a
    marker added.  Comparison is deliberately blunt -- whitespace-stripped exact
    match -- so the marker is explainable rather than a similarity guess.
    """
    seen: set[str] = set()
    marked = 0
    for index, item in enumerate(session.utterances):
        if item.speaker_id in {MODERATOR_ID, USER_ID}:
            continue
        normalized = re.sub(r"\s+", "", item.content)
        if normalized in seen:
            if not item.duplicate:
                session.utterances[index] = replace(item, duplicate=True)
            marked += 1
        else:
            seen.add(normalized)
    return marked


def detect_intervention(session: DiscussionSession, recent: int = 6) -> tuple[bool, str]:
    """Decide whether the host should summarize, from structural evidence only.

    The reasons mirror the approved protocol: a disagreement that has been fully
    argued, an important consensus, rising repetition, a stalled discussion, or
    a falling rate of new points.
    """
    recent_items = _role_utterances(session)[-recent:]
    if len(recent_items) < recent:
        return False, ""
    challenged = [item.replies_to for item in recent_items if item.intent == "challenge" and item.replies_to]
    if any(challenged.count(target) >= 3 for target in set(challenged)) and any(item.stance_change for item in recent_items):
        return True, "关键分歧已经充分交锋，需要主持人收束"
    supported = [item.replies_to for item in recent_items if item.intent == "support" and item.replies_to]
    if any(supported.count(target) >= 3 for target in set(supported)):
        return True, "已出现重要共识，需要主持人确认"
    if sum(1 for item in recent_items if item.duplicate) >= 2:
        return True, "重复观点增加，需要主持人整理"
    if len({item.speaker_id for item in recent_items}) <= 2:
        return True, "发言集中在少数角色，讨论冷场"
    # Content-based, so this trigger works today -- before duplicate detection
    # starts setting the flag.  The flag-based check above only becomes live
    # once that exists, and the two stay independently reachable.
    if len({item.content.strip() for item in recent_items}) <= len(recent_items) - 2:
        return True, "新观点减少，需要主持人整理"
    return False, ""


def plan_turn(
    session: DiscussionSession,
    roles: Sequence[Role],
    state: DiscussionState | None = None,
) -> TurnPlan:
    """Return the next turn to generate, using local structure only.

    ``state`` is accepted so the orchestrator (phase 3) can hand over the
    snapshot it works from.  The local rules deliberately read the event stream
    instead: the snapshot is derived data and may be stale, while the event
    stream is the source of truth.
    """
    candidates = [role for role in roles if role.id != MODERATOR_ID]
    if not candidates:
        candidates = _roles_from_history(session)
    if not candidates:
        return TurnPlan(
            MODERATOR_ID, "主持人", "阶段总结", "synthesize", "总结",
            reason="尚无可发言的角色", moderator=True,
        )

    should_intervene, intervention_reason = detect_intervention(session)
    if should_intervene:
        return TurnPlan(
            MODERATOR_ID, "主持人", "状态整理", "synthesize", "总结",
            reason=intervention_reason, moderator=True, intervention_reason=intervention_reason,
        )

    replied = _replied_ids(session)

    # Rule 1: an unanswered user interjection outranks everything else.
    interjection = next(
        (item for item in reversed(session.utterances[-USER_WINDOW:]) if item.speaker_id == USER_ID),
        None,
    )
    if interjection is not None and interjection.event_id not in replied:
        speaker = _least_spoken(candidates, session)
        if speaker is not None:
            return _guard(TurnPlan(
                speaker.id, speaker.name, "回应插话", "elaborate", "假设",
                reply_to_event_id=interjection.event_id,
                reason="你刚才插话，优先回应",
            ), session, candidates)

    # Rule 2: a question nobody answered.
    questions = [
        item for item in _role_utterances(session)[-QUESTION_WINDOW:]
        if item.intent == "question" and item.event_id not in replied
    ]
    if questions:
        question = questions[-1]
        speaker = _role_by_reference(candidates, session, question.replies_to) or _least_spoken(
            candidates, session, exclude=[question.speaker_id]
        )
        if speaker is not None:
            return _guard(TurnPlan(
                speaker.id, speaker.name, "回答提问", "elaborate", "待验证",
                reply_to_event_id=question.event_id,
                reason=f"{question.speaker_name}的提问还没有人回答",
            ), session, candidates)

    # Rule 3: somebody was challenged and has not spoken since.
    owed: list[tuple[Utterance, Role]] = []
    for index, item in enumerate(session.utterances):
        if item.intent != "challenge" or not item.replies_to:
            continue
        target = _role_by_reference(candidates, session, item.replies_to)
        if target is None or target.id == item.speaker_id:
            continue
        if not any(later.speaker_id == target.id for later in session.utterances[index + 1:]):
            owed.append((item, target))
    if owed:
        challenge, target = owed[-1]
        return _guard(TurnPlan(
            target.id, target.name, "正面反驳", "challenge", "风险",
            reply_to_event_id=challenge.event_id,
            reason=f"{challenge.speaker_name}的质疑尚未回应",
        ), session, candidates)

    # Rule 4: bring back whoever has been silent longest.
    silent = [role for role in candidates if _turns_since_spoke(session, role.id) >= MAX_SILENT_TURNS]
    if silent:
        speaker = _least_spoken(silent, session)
        if speaker is not None:
            return _guard(TurnPlan(
                speaker.id, speaker.name, "补充观点", "elaborate", "假设",
                reason=f"让 {speaker.name} 加入交锋",
            ), session, candidates)

    # Rule 5: fallback -- fewest turns, then longest silent.
    speaker = _least_spoken(candidates, session)
    if speaker is None:
        return TurnPlan(
            MODERATOR_ID, "主持人", "阶段总结", "synthesize", "总结",
            reason="尚无可发言的角色", moderator=True,
        )
    return _guard(TurnPlan(
        speaker.id, speaker.name, "回应", "elaborate", "假设",
        reason="补充已有观点",
    ), session, candidates)


def _guard(plan: TurnPlan, session: DiscussionSession, candidates: Sequence[Role]) -> TurnPlan:
    """Never let one role take three turns in a row."""
    recent = [item.speaker_id for item in _role_utterances(session)][-MAX_CONSECUTIVE_SAME_SPEAKER:]
    if len(recent) == MAX_CONSECUTIVE_SAME_SPEAKER and all(speaker_id == plan.speaker_id for speaker_id in recent):
        alternative = _least_spoken(candidates, session, exclude=[plan.speaker_id])
        if alternative is not None:
            return replace(
                plan,
                speaker_id=alternative.id,
                speaker_name=alternative.name,
                reason=f"{plan.reason}（避免同一角色连续发言）",
            )
    return plan
