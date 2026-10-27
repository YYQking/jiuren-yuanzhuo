"""The table must sound like people talking, not one template filled in N times."""

import unittest

from brainstorm.models import DiscussionSession, Role, Utterance, ViewpointKind
from brainstorm.roles import DEFAULT_ROLES, EVENT_ROLES
from brainstorm.turn_planner import LENGTH_CYCLE, TurnPlan, assign_length
from brainstorm.voice import (
    ANTI_TEMPLATE_RULES,
    LENGTH_TARGETS,
    find_template_markers,
    find_template_opening,
    length_instruction,
    looks_templated,
)


ROLES = [
    Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化是否真实。"),
    Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
]


def say(speaker_id, speaker_name, content, phase="动态交锋", intent="elaborate"):
    return Utterance(
        speaker_id, speaker_name, content, ViewpointKind.ASSUMPTION, phase, intent=intent,
    )


def build(*utterances):
    session = DiscussionSession(topic="社区养老", selected_role_ids=[role.id for role in ROLES])
    for item in utterances:
        session.append_utterance(item)
    return session


class LengthInstructionTests(unittest.TestCase):
    def test_every_hint_has_its_own_sentence(self):
        sentences = {length_instruction(hint) for hint in LENGTH_TARGETS}
        self.assertEqual(len(sentences), len(LENGTH_TARGETS))
        # 短打必须明显短于长篇，否则“每条都差不多长”的观感修不掉
        self.assertIn("30–70", length_instruction("short"))
        self.assertIn("180–240", length_instruction("long"))

    def test_unknown_hint_falls_back_instead_of_crashing(self):
        self.assertEqual(length_instruction(""), LENGTH_TARGETS["normal"])
        self.assertEqual(length_instruction("whatever"), LENGTH_TARGETS["normal"])

    def test_anti_template_rules_forbid_the_measured_tells(self):
        for phrase in ("我先说", "我先开个头", "说白了", "第一/第二/第三", "骨架"):
            self.assertIn(phrase, ANTI_TEMPLATE_RULES)


class TemplateDetectionTests(unittest.TestCase):
    def test_catches_the_stock_openings_measured_in_the_real_transcript(self):
        self.assertEqual(find_template_opening("我先说一句，这事最让我冒火"), "我先说")
        self.assertEqual(find_template_opening("我先开个头啊，这事网上吵得挺凶"), "我先开个头")
        self.assertEqual(find_template_opening("实话实说，这店到底脏不脏"), "实话实说")
        self.assertTrue(looks_templated("说白了，两边都只有嘴"))

    def test_leaves_a_normal_opening_alone(self):
        self.assertEqual(looks_templated("地姐你这一问，我得先接住"), "")
        self.assertEqual(looks_templated("这我不信，凭啥"), "")

    def test_only_the_head_is_checked(self):
        # 半句之后说「说白了」是人话，不算套话开场
        self.assertEqual(find_template_opening("这店评分不低，说白了就是会做营销"), "")

    def test_counts_structural_markers(self):
        markers = find_template_markers("第一，成本；其次，周期；最后，没人买")
        self.assertIn("最后，", markers)
        self.assertGreaterEqual(len(markers), 2)


class LengthPlanningTests(unittest.TestCase):
    def _plan(self, **kwargs):
        base = dict(
            speaker_id="trend", speaker_name="趋势分析师", phase="动态交锋",
            intent="elaborate", reason="补充已有观点",
        )
        base.update(kwargs)
        return TurnPlan(**base)

    def test_moderator_gets_the_host_budget(self):
        plan = assign_length(self._plan(speaker_id="moderator", moderator=True), build())
        self.assertEqual(plan.length_hint, "host")

    def test_synthesis_gets_room(self):
        plan = assign_length(self._plan(intent="synthesize"), build())
        self.assertEqual(plan.length_hint, "long")

    def test_a_seat_first_turn_is_normal(self):
        plan = assign_length(self._plan(), build())
        self.assertEqual(plan.length_hint, "normal")

    def test_repeat_turns_cycle_through_mostly_short(self):
        history = [say("trend", "趋势分析师", "我上次说过一句")]
        plan = assign_length(self._plan(), build(*history))
        self.assertEqual(plan.length_hint, LENGTH_CYCLE[1])

    def test_an_orchestrator_choice_is_respected(self):
        plan = assign_length(self._plan(length_hint="short"), build())
        self.assertEqual(plan.length_hint, "short")


class SeatVoiceTests(unittest.TestCase):
    def test_every_seat_has_a_voice(self):
        for role in list(DEFAULT_ROLES) + list(EVENT_ROLES):
            with self.subTest(role=role.id):
                self.assertTrue(role.voice.strip(), f"{role.name} 没有说话习惯")

    def test_no_two_seats_talk_the_same_way(self):
        voices = [role.voice for role in list(DEFAULT_ROLES) + list(EVENT_ROLES)]
        self.assertEqual(len(voices), len(set(voices)))

    def test_voice_is_separate_from_duty(self):
        for role in list(DEFAULT_ROLES) + list(EVENT_ROLES):
            with self.subTest(role=role.id):
                self.assertNotEqual(role.voice.strip(), role.duty.strip())


if __name__ == "__main__":
    unittest.main()
