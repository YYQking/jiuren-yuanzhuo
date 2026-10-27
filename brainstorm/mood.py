"""The temper ledger: who got rubbed the wrong way, and why.

People do not flip a switch.  Somebody says something that lands badly, it gets
remembered, and the next time that person opens their mouth it shows in their
tone; after a while the soreness fades.  This module keeps that bookkeeping and
nothing else.

It never decides *when* a seat should change.  The model writes each note with
its own reason ("雷子 -1：你把这事说成没什么大不了"), and the program only:

* validates the note (known seat, small integer, a reason, not about yourself),
* stops one seat churning every turn (``CHANGE_COOLDOWN``),
* lets old notes fade toward calm (``FADE_EVERY``).

Because the ledger is folded straight out of the transcript, reloading a saved
discussion reproduces the same moods without any extra state.
"""

from __future__ import annotations

from typing import Sequence

from .models import Reaction, Utterance

MOOD_MIN = -2
MOOD_MAX = 2
MOOD_WORDS = {-2: "很不痛快", -1: "憋着点火", 0: "正常", 1: "心情不错", 2: "很受用"}

# A seat may change at most once per this many seat turns, so one sentence
# cannot send somebody through four moods in a row.
CHANGE_COOLDOWN = 3
# Every this many seat turns an old note fades one step toward calm.
FADE_EVERY = 4
MAX_NOTES_PER_TURN = 2
MAX_WHY_CHARS = 40
NON_SEAT_IDS = frozenset({"moderator", "user"})


def mood_label(mood: int) -> str:
    """A plain-language name for a mood value."""
    return MOOD_WORDS.get(max(MOOD_MIN, min(MOOD_MAX, int(mood))), "正常")


def mood_of(history: Sequence[Utterance], seat_id: str) -> int:
    """The mood ``seat_id`` is in right now, folded out of the transcript."""
    total = 0
    age = 0
    for item in reversed(history):
        if item.speaker_id in NON_SEAT_IDS:
            continue
        for note in item.reactions:
            if note.seat_id != seat_id:
                continue
            strength = abs(note.delta) - age // FADE_EVERY
            if strength <= 0:
                continue
            total += strength if note.delta > 0 else -strength
        age += 1
    return max(MOOD_MIN, min(MOOD_MAX, total))


def mood_notes(history: Sequence[Utterance], seat_id: str) -> list[Reaction]:
    """Notes still strong enough to matter, newest first."""
    found: list[Reaction] = []
    age = 0
    for item in reversed(history):
        if item.speaker_id in NON_SEAT_IDS:
            continue
        for note in item.reactions:
            if note.seat_id == seat_id and abs(note.delta) - age // FADE_EVERY > 0:
                found.append(note)
        age += 1
    found.reverse()
    return found


def face_for_mood(mood: int) -> str:
    """Which side of the persona a mood belongs to, or "" for the middle."""
    if mood >= 1:
        return "yang"
    if mood <= -1:
        return "yin"
    return ""


def last_face(history: Sequence[Utterance], seat_id: str) -> str:
    """The side this seat showed most recently, or "" if it never spoke."""
    for item in reversed(history):
        if item.speaker_id == seat_id and item.face in {"yang", "yin"}:
            return item.face
    return ""


def resolve_face(history: Sequence[Utterance], seat_id: str) -> str:
    """The side this seat shows now: the ledger decides, the past breaks ties."""
    return face_for_mood(mood_of(history, seat_id)) or last_face(history, seat_id) or "yang"


def can_change(history: Sequence[Utterance], seat_id: str) -> bool:
    """False while a fresh note about this seat is still cooling down."""
    age = 0
    for item in reversed(history):
        if item.speaker_id in NON_SEAT_IDS:
            continue
        if age >= CHANGE_COOLDOWN:
            return True
        if any(note.seat_id == seat_id for note in item.reactions):
            return False
        age += 1
    return True


def validate_notes(
    raw: object,
    *,
    history: Sequence[Utterance],
    seat_ids: set[str],
    speaker_id: str,
) -> list[Reaction]:
    """Keep the notes the program can trust, drop the rest.  Never raises."""
    if not isinstance(raw, (list, tuple)):
        return []
    accepted: list[Reaction] = []
    for entry in raw:
        if len(accepted) >= MAX_NOTES_PER_TURN:
            break
        if not isinstance(entry, dict):
            continue
        seat = str(entry.get("seat") or entry.get("seat_id") or "").strip()
        if seat not in seat_ids or seat == speaker_id:
            continue
        try:
            delta = int(entry.get("delta"))
        except (TypeError, ValueError):
            continue
        if delta == 0:
            continue
        delta = max(MOOD_MIN, min(MOOD_MAX, delta))
        why = " ".join(str(entry.get("why") or "").split())
        if not why:
            continue
        if not can_change(history, seat):
            continue
        accepted.append(Reaction(seat_id=seat, delta=delta, why=why[:MAX_WHY_CHARS]))
    return accepted


def mood_context(history: Sequence[Utterance], seat_id: str, speaker_name: str = "") -> str:
    """What this seat is carrying into its next turn, for the prompt."""
    mood = mood_of(history, seat_id)
    if mood == 0:
        return ""
    notes = mood_notes(history, seat_id)
    reason = notes[-1].why if notes else ""
    face = face_for_mood(mood)
    tone = "比平时热络，愿意给人台阶" if face == "yang" else "比平时冲，容易翻旧账"
    name = f"{speaker_name}（你）" if speaker_name else "你"
    line = f"{name}现在的脸色：{mood_label(mood)}（{mood:+d}），{tone}。"
    if reason:
        line += f"\n缘由：{reason}"
    line += (
        "\n按这个脸色说话，但不要解释自己的情绪，也不许写成另一个人——"
        "还是你自己的脾气，只是没那么客气了。"
    )
    return line + "\n"

QUIET_LOOKBACK = 5


def quiet_seats(utterances, seats, lookback: int = QUIET_LOOKBACK) -> set[str]:
    """最近几条里既没说话、也没人接他话的座位——桌上被晾着的那几个。"""
    recent = list(utterances)[-lookback:]
    if not recent:
        return set()
    speaker_of = {item.event_id: item.speaker_id for item in utterances}
    quiet: set[str] = set()
    for seat_id in seats:
        spoke = any(item.speaker_id == seat_id for item in recent)
        if spoke:
            continue
        touched = False
        for item in recent:
            if item.speaker_id == seat_id:
                touched = True
                break
            if speaker_of.get(item.replies_to or "", None) == seat_id:
                touched = True
                break
            if any(note.seat_id == seat_id for note in item.reactions):
                touched = True
                break
        if not touched:
            quiet.add(seat_id)
    return quiet
