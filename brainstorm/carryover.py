"""把上一场讨论压成一页底稿，供下一场接着聊。

「接着再聊」如果直接把整场记录塞进提示词，模型会把已经说过的结论再讲一遍，
一场就等于重播。这里只留三样东西：结论、没吵完的地方、这一场的规矩——
目的是让新的讨论从分歧处往下问，而不是从开场白重新开始。

注意：底稿是**上一场自己聊出来的**，不是外部事实。写进底稿时必须反复说明
这一点，否则席位会把它当已核实的资料引用（真实跑测里模型就干过这种事）。
"""

from __future__ import annotations

from .models import DiscussionSession
from .roles import SECTION_TEXT, mode_label

# 一条底稿控制在 1500 字以内：再长就会挤掉这一场自己的历史上下文，
# 模型反而会围着旧结论打转。
TOTAL_LIMIT = 1500
ITEM_LIMIT = 70
SUPPORT_LIMIT = 3
DISPUTE_LIMIT = 3

DISPUTE_INTENTS = ("challenge", "question", "反驳", "质疑")


def _clip(text: str, limit: int = ITEM_LIMIT) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _bullets(items, limit: int = SUPPORT_LIMIT) -> list[str]:
    lines: list[str] = []
    for item in list(items or [])[:limit]:
        text = _clip(item)
        if text:
            lines.append(f"  - {text}")
    return lines


def _labels(session: DiscussionSession) -> dict[str, str]:
    return SECTION_TEXT.get(session.mode, SECTION_TEXT["business"])


def open_disputes(session: DiscussionSession, limit: int = DISPUTE_LIMIT) -> list[str]:
    """上一场最后那几条「不服」和「追问」——最该接着答的地方。"""

    picked: list[str] = []
    for item in reversed(session.utterances):
        if str(item.intent or "") not in DISPUTE_INTENTS:
            continue
        picked.append(f"{item.speaker_name}：{_clip(item.content, 90)}")
        if len(picked) >= limit:
            break
    picked.reverse()
    return picked


def carry_note(session: DiscussionSession) -> str:
    """接着再聊时放进「补充材料」的那段话。"""

    text = _labels(session)
    lines = [
        f"【上一场的底稿 · {session.created_at:%Y-%m-%d %H:%M} · {mode_label(session.mode)}】",
        "以下是上一次讨论自己聊出来的内容，只用来避免重复、接着往下问。",
        "它不是外部事实，也不能当成已经证实的情报引用。",
        "",
        f"上次的题目：{_clip(session.topic, 120)}",
    ]
    card = session.opportunity
    if card is not None:
        lines.extend(["", f"上次收出来的{text['archive_title']}："])
        if card.title:
            lines.append(f"  - {text['field_title']}：{_clip(card.title)}")
        if card.audience:
            lines.append(f"  - {text['field_audience']}：{_clip(card.audience)}")
        for label, values in (
            (text["label_support"], card.support),
            (text["label_risks"], card.risks),
            (text["label_assumptions"], card.assumptions),
            (text["label_next_steps"], card.next_steps),
        ):
            bullets = _bullets(values)
            if bullets:
                lines.append(f"  - {label}：")
                lines.extend("  " + row for row in bullets)
    disputes = open_disputes(session)
    if disputes:
        lines.extend(["", "上次没吵完的地方（这次从这儿接着问）："])
        lines.extend(f"  - {row}" for row in disputes)
    lines.extend(
        [
            "",
            "这次的规矩：不要复述上面已经说过的内容；谁要再提旧结论，必须说清这次为什么还成立。",
            "没人说过的部分，用「我猜」「我听说」标出来，别直接当事实讲。",
        ]
    )
    note = "\n".join(lines)
    if len(note) > TOTAL_LIMIT:
        note = note[: TOTAL_LIMIT - 1].rstrip() + "…"
    return note
