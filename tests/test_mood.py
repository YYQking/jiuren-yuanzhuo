"""Tempers move because of what was said, not because a timer ran out."""

import json
import unittest

from brainstorm.models import DiscussionSession, Reaction, Utterance, ViewpointKind
from brainstorm import mood as mood_module
from brainstorm.mood import (
    CHANGE_COOLDOWN,
    FADE_EVERY,
    MAX_NOTES_PER_TURN,
    face_for_mood,
    can_change,
    mood_context,
    mood_label,
    mood_of,
    resolve_face,
    validate_notes,
)


SEATS = {"qian", "kun", "zhen"}


def say(speaker_id, content="随便说一句", reactions=()):
    if isinstance(reactions, Reaction):
        reactions = (reactions,)
    return Utterance(
        speaker_id, speaker_id, content, ViewpointKind.ASSUMPTION, "各说各话",
        reactions=tuple(reactions),
    )


def filler(count, speaker_id="zhen"):
    return [say(speaker_id) for _ in range(count)]


class MoodFoldTests(unittest.TestCase):
    def test_someone_who_was_never_touched_is_calm(self):
        history = filler(6)
        self.assertEqual(mood_of(history, "qian"), 0)
        # 平静的座位沿用上一次的脸，第一次开口默认阳面
        self.assertEqual(resolve_face(history, "qian"), "yang")

    def test_a_note_that_landed_sours_the_next_turn(self):
        history = [say("zhen", "这事没那么严重", (Reaction("qian", -1, "你说这事没什么大不了"),))]
        self.assertEqual(mood_of(history, "qian"), -1)
        self.assertEqual(resolve_face(history, "qian"), "yin")

    def test_being_pleased_brings_the_face_back(self):
        history = [
            say("zhen", "你这话在理", (Reaction("qian", 1, "他认了你的说法"),)),
        ]
        self.assertEqual(resolve_face(history, "qian"), "yang")
        self.assertEqual(mood_label(mood_of(history, "qian")), "心情不错")

    def test_soreness_fades_when_nothing_keeps_poking_it(self):
        history = [say("zhen", "x", (Reaction("qian", -1, "踩到他了")))] + filler(FADE_EVERY, "kun")
        self.assertEqual(mood_of(history, "qian"), 0)
        self.assertEqual(resolve_face(history, "qian"), "yang")

    def test_mood_never_exceeds_the_floor_or_ceiling(self):
        history = [say("zhen", "x", (Reaction("qian", -2, "很过分")))] + [
            say("kun", "y", (Reaction("qian", -2, "又来一次")))
            for _ in range(CHANGE_COOLDOWN + FADE_EVERY)
        ]
        self.assertEqual(mood_of(history, "qian"), mood_module.MOOD_MIN)

    def test_face_for_middle_is_empty_so_the_last_face_survives(self):
        self.assertEqual(face_for_mood(0), "")
        self.assertEqual(face_for_mood(2), "yang")
        self.assertEqual(face_for_mood(-2), "yin")

    def test_moderator_and_user_turns_do_not_age_the_ledger(self):
        history = [
            say("zhen", "x", (Reaction("qian", -1, "踩到他了"))),
            Utterance("moderator", "主持人", "停一下", ViewpointKind.SUMMARY, "阶段整理"),
            Utterance("user", "你", "我插一句", ViewpointKind.ASSUMPTION, "用户"),
        ]
        self.assertEqual(mood_of(history, "qian"), -1)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.history = [say("kun")]

    def run_validate(self, raw, history=None, speaker_id="kun"):
        return validate_notes(
            raw,
            history=list(self.history if history is None else history),
            seat_ids=SEATS,
            speaker_id=speaker_id,
        )

    def test_a_well_formed_note_is_kept(self):
        notes = self.run_validate([{"seat": "qian", "delta": -1, "why": "他说得太轻巧"}])
        self.assertEqual(len(notes), 1)
        self.assertEqual((notes[0].seat_id, notes[0].delta), ("qian", -1))

    def test_nobody_writes_notes_about_themselves(self):
        self.assertEqual(self.run_validate([{"seat": "kun", "delta": -1, "why": "我自己"}] ), [])

    def test_unknown_seat_is_dropped(self):
        self.assertEqual(self.run_validate([{"seat": "陌生人", "delta": -1, "why": "谁"}]), [])

    def test_zero_delta_and_missing_reason_are_dropped(self):
        self.assertEqual(self.run_validate([{"seat": "qian", "delta": 0, "why": "没变"}]), [])
        self.assertEqual(self.run_validate([{"seat": "qian", "delta": -1, "why": "   "}]), [])

    def test_garbage_input_cannot_raise(self):
        for raw in (None, "字符串", 5, [None, 3, "x"], [{"seat": "qian", "delta": "狠"}]):
            self.assertEqual(self.run_validate(raw), [])

    def test_at_most_two_notes_per_turn(self):
        raw = [
            {"seat": "qian", "delta": -1, "why": "一"},
            {"seat": "kun", "delta": -1, "why": "二"},
            {"seat": "li", "delta": 1, "why": "三"},
        ]
        notes = validate_notes(
            raw, history=[say("zhen")], seat_ids=SEATS | {"li"}, speaker_id="zhen"
        )
        self.assertEqual(len(notes), MAX_NOTES_PER_TURN)

    def test_one_seat_cannot_churn_every_turn(self):
        history = [
            say("zhen", "x", (Reaction("qian", -1, "刚被踩了"))),
            say("kun", "y"),
        ]
        notes = self.run_validate(
            [{"seat": "qian", "delta": -1, "why": "又来"}], history=history
        )
        self.assertEqual(notes, [])
        self.assertFalse(can_change(history, "qian"))

    def test_cooldown_lifts_when_enough_turns_pass(self):
        history = [say("zhen", "x", (Reaction("qian", -1, "刚被踩了")))] + filler(
            CHANGE_COOLDOWN, "kun"
        )
        self.assertTrue(can_change(history, "qian"))
        notes = self.run_validate([{"seat": "qian", "delta": 1, "why": "给了台阶"}], history=history)
        self.assertEqual(len(notes), 1)


class PromptTests(unittest.TestCase):
    def test_a_calm_seat_gets_no_extra_instructions(self):
        self.assertEqual(mood_context(filler(3), "qian"), "")

    def test_a_soured_seat_is_told_why_and_to_stay_in_character(self):
        history = [say("zhen", "这事没什么大不了的", (Reaction("qian", -1, "你说这事没什么大不了"),))]
        text = mood_context(history, "qian", "乾明")
        self.assertIn("憋着点火", text)
        self.assertIn("没什么大不了", text)
        self.assertIn("不要解释自己的情绪", text)
        self.assertIn("还是你自己的脾气", text)


class StorageTests(unittest.TestCase):
    def test_the_ledger_survives_saving_and_reloading(self):
        from brainstorm.storage import session_from_dict, session_to_dict

        session = DiscussionSession(topic="车位被转租", mode="event")
        session.append_utterance(say("zhen", "这事没什么大不了", (Reaction("qian", -1, "踩到他了"),)))
        restored = session_from_dict(json.loads(json.dumps(session_to_dict(session))))
        self.assertEqual(restored.utterances[-1].reactions[0].why, "踩到他了")
        self.assertEqual(mood_of(restored.utterances, "qian"), -1)
        self.assertEqual(resolve_face(restored.utterances, "qian"), "yin")

    def test_old_sessions_without_notes_still_load(self):
        from brainstorm.storage import session_from_dict

        restored = session_from_dict({
            "schema_version": 6,
            "topic": "旧记录",
            "utterances": [
                {
                    "speaker_id": "qian",
                    "speaker_name": "乾明",
                    "content": "说一句",
                    "kind": "假设",
                    "phase": "各说各话",
                }
            ],
        })
        self.assertEqual(restored.utterances[0].reactions, ())


if __name__ == "__main__":
    unittest.main()
