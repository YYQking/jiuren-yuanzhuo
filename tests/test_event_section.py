"""The event section: trigram seats, archive wording, and storage round-trip."""

import json
import tempfile
import unittest
from pathlib import Path

from brainstorm.engine import MockDiscussionProvider
from brainstorm.export import export_markdown
from brainstorm.llm import resolve_face
from brainstorm.models import DiscussionSession, OpportunityCard, Reaction, Utterance, ViewpointKind
from brainstorm.roles import (
    DEFAULT_ROLES,
    EVENT_ROLES,
    EVENT_ROLE_IDS,
    SECTION_TEXT,
    default_roles_for,
    face_label,
    mode_for_roles,
)
from brainstorm.storage import SessionStore, session_from_dict, session_to_dict

TRIGRAMS = {
    "乾·天", "坤·地", "震·雷", "巽·风", "坎·水", "离·火", "艮·山", "兑·泽",
}


class SectionRosterTests(unittest.TestCase):
    def test_each_section_has_its_own_seats(self):
        self.assertEqual(len(DEFAULT_ROLES), 9)
        self.assertEqual(len(EVENT_ROLES), 8)
        self.assertEqual({role.id for role in DEFAULT_ROLES} & EVENT_ROLE_IDS, set())
        self.assertEqual({role.trigram for role in EVENT_ROLES}, TRIGRAMS)

    def test_every_event_seat_states_both_faces(self):
        for role in EVENT_ROLES:
            self.assertTrue(role.yang, role.id)
            self.assertTrue(role.yin, role.id)
            self.assertIn(role.yang, role.prompt)
            self.assertIn(role.yin, role.prompt)
            # The prompt has to say out loud that this is not psychology, or the
            # model will present a trigram as a personality test result.
            self.assertIn("不是心理学结论", role.prompt)

    def test_business_seats_carry_no_trigram_material(self):
        for role in DEFAULT_ROLES:
            self.assertEqual(role.trigram, "", role.id)
            self.assertEqual(role.yang, "", role.id)
            self.assertEqual(role.yin, "", role.id)

    def test_mode_is_inferred_from_seats(self):
        self.assertEqual(mode_for_roles(DEFAULT_ROLES), "business")
        self.assertEqual(mode_for_roles(EVENT_ROLES), "event")
        self.assertEqual(mode_for_roles([EVENT_ROLES[0], EVENT_ROLES[3]]), "event")
        self.assertEqual(mode_for_roles([]), "business")
        self.assertEqual([role.id for role in default_roles_for("event")], [role.id for role in EVENT_ROLES])
        self.assertEqual([role.id for role in default_roles_for("business")], [role.id for role in DEFAULT_ROLES])
        self.assertEqual([role.id for role in default_roles_for("nonsense")], [role.id for role in DEFAULT_ROLES])

    def test_face_label_is_plain_words(self):
        self.assertEqual(face_label("yang"), "阳面")
        self.assertEqual(face_label("yin"), "阴面")
        self.assertEqual(face_label(""), "")

    def test_archive_wording_differs_per_section(self):
        business = SECTION_TEXT["business"]
        event = SECTION_TEXT["event"]
        self.assertEqual(business["archive_title"], "机会档案")
        self.assertEqual(event["archive_title"], "吃瓜纪要")
        for key in ("field_title", "field_audience", "label_support", "label_risks",
                    "label_assumptions", "label_next_steps", "archive_empty"):
            self.assertNotEqual(business[key], event[key], key)
        self.assertEqual(set(business), set(event))


class EventEngineTests(unittest.TestCase):
    def test_offline_event_discussion_keeps_both_faces_in_play(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("小区业主群为停车位吵起来", EVENT_ROLES)
        self.assertEqual(session.mode, "event")
        self.assertEqual(session.utterances[0].speaker_id, "moderator")
        faces = {item.face for item in session.utterances if item.face}
        self.assertEqual(faces, {"yang", "yin"})
        speakers = {item.speaker_id for item in session.utterances}
        self.assertTrue(speakers <= {"moderator"} | EVENT_ROLE_IDS)
        self.assertGreater(len({item.speaker_id for item in session.utterances}), 4)

    def test_offline_business_discussion_stays_unchanged(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("社区里的银发人群如何更容易使用数字服务", DEFAULT_ROLES)
        self.assertEqual(session.mode, "business")
        self.assertTrue(all(not item.face for item in session.utterances))


class EventStorageTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self._dir.name))

    def tearDown(self):
        self._dir.cleanup()

    def _event_session(self) -> DiscussionSession:
        session = DiscussionSession(
            topic="小区业主群为停车位吵起来",
            selected_role_ids=[role.id for role in EVENT_ROLES[:4]],
            mode="event",
        )
        session.append_utterance(Utterance("moderator", "主持人", "这事儿先听各位说。", ViewpointKind.SUMMARY, "开场"))
        session.append_utterance(
            Utterance(EVENT_ROLES[0].id, EVENT_ROLES[0].name, "我先定个调子。", ViewpointKind.ASSUMPTION, "独立观点", face="yang")
        )
        session.append_utterance(
            Utterance(EVENT_ROLES[2].id, EVENT_ROLES[2].name, "这事不能就这么算了。", ViewpointKind.ASSUMPTION, "独立观点", face="yin")
        )
        return session

    def test_mode_and_face_survive_a_save_and_reload(self):
        session = self._event_session()
        path = self.store.save(session)
        restored = self.store.load(path)
        self.assertEqual(restored.mode, "event")
        self.assertEqual([item.face for item in restored.utterances], ["", "yang", "yin"])

    def test_archive_without_mode_is_inferred_from_the_seats(self):
        payload = json.loads(json.dumps(session_to_dict(self._event_session())))
        payload.pop("mode", None)
        self.assertEqual(session_from_dict(payload).mode, "event")

        business = DiscussionSession(
            topic="银发人群用数字服务", selected_role_ids=[role.id for role in DEFAULT_ROLES[:3]]
        )
        payload = json.loads(json.dumps(session_to_dict(business)))
        payload.pop("mode", None)
        self.assertEqual(session_from_dict(payload).mode, "business")


class EventExportTests(unittest.TestCase):
    def test_markdown_uses_the_section_vocabulary(self):
        session = DiscussionSession(
            topic="小区业主群为停车位吵起来",
            selected_role_ids=[role.id for role in EVENT_ROLES[:3]],
            mode="event",
        )
        session.opportunity = OpportunityCard(
            title="物业和业主都没把规则说清",
            audience="业主、物业、街道",
            support=["群里贴出了当年的车位分配表"],
            risks=["有人把两年前的事当成刚发生的"],
            assumptions=["没人核对过那张表是不是最新的"],
            next_steps=["等物业把分配规则贴出来"],
        )
        session.append_utterance(
            Utterance(EVENT_ROLES[4].id, EVENT_ROLES[4].name, "先说说不通的地方。", ViewpointKind.ASSUMPTION, "独立观点", face="yin")
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = export_markdown(session, Path(tmp) / "纪要.md")
            text = path.read_text(encoding="utf-8")
        self.assertIn("## 吃瓜纪要", text)
        self.assertIn("**这事儿算什么：**", text)
        self.assertIn("### 有实锤的部分", text)
        self.assertIn("### 接下来看什么", text)
        self.assertIn("阴面", text)
        self.assertNotIn("## 机会档案", text)


class FaceFlipTests(unittest.TestCase):
    """A seat only turns sour when something in the transcript landed on it.

    The old rule alternated faces on a timer, which made people change
    personality on schedule; the model itself never asked to flip.
    """

    def _seat(self, speaker_id: str, face: str, content: str = "一句", reactions=()) -> Utterance:
        name = {role.id: role.name for role in EVENT_ROLES}[speaker_id]
        return Utterance(
            speaker_id, name, content, ViewpointKind.ASSUMPTION, "交锋",
            face=face, reactions=tuple(reactions),
        )

    def _filler(self, index: int) -> Utterance:
        return Utterance("moderator", "主持人", f"第 {index} 段", ViewpointKind.SUMMARY, "状态整理")

    def test_nothing_landed_so_the_face_does_not_move(self):
        history = [self._seat("qian", "yang")] + [self._filler(i) for i in range(6)]
        self.assertEqual(resolve_face(history, "qian", "yang"), "yang")

    def test_a_note_that_landed_turns_the_face(self):
        history = [
            self._seat("qian", "yang"),
            self._seat("zhen", "yang", "这事没什么大不了的", [Reaction("qian", -1, "你说这事没什么大不了")]),
        ]
        self.assertEqual(resolve_face(history, "qian", "yang"), "yin")

    def test_being_pleased_turns_it_back(self):
        history = [
            self._seat("qian", "yang"),
            self._seat("zhen", "yang", "有事你说", [Reaction("qian", -1, "踩到他了")]),
            self._seat("kun", "yang", "你这话在理", [Reaction("qian", 1, "他认了你的说法")]),
        ]
        self.assertEqual(resolve_face(history, "qian", "yin"), "yang")


if __name__ == "__main__":
    unittest.main()
