import unittest

from brainstorm.models import DiscussionSession, DiscussionState, Role, StanceChange, Utterance, ViewpointKind
from brainstorm.turn_planner import TurnPlan, detect_intervention, plan_turn


ROLES = [
    Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化是否真实。"),
    Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
    Role("skeptic", "怀疑者", "寻找伪需求", "#dc2626", "主动寻找反例。"),
]


def build(*utterances):
    session = DiscussionSession(topic="社区养老", selected_role_ids=[role.id for role in ROLES])
    for item in utterances:
        session.append_utterance(item)
    return session


def say(speaker_id, speaker_name, content, kind=ViewpointKind.ASSUMPTION, phase="动态交锋",
        intent="initial", replies_to=None):
    return Utterance(
        speaker_id, speaker_name, content, kind, phase,
        replies_to=replies_to, origin="model", intent=intent,
    )


class TurnPlannerTests(unittest.TestCase):
    def test_user_interjection_is_answered_first(self):
        session = build(
            say("trend", "趋势分析师", "开场观点"),
            say("user", "用户", "先讨论无障碍体验", intent="user_instruction"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.reason, "你刚才插话，优先回应")
        self.assertEqual(plan.reply_to_event_id, session.utterances[-1].event_id)
        self.assertNotEqual(plan.speaker_id, "user")

    def test_interjection_is_not_repeated_once_answered(self):
        session = build(
            say("user", "用户", "先讨论无障碍体验", intent="user_instruction"),
            say("trend", "趋势分析师", "我先回应插话", intent="elaborate", replies_to="event-000000"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertNotEqual(plan.reason, "你刚才插话，优先回应")

    def test_unanswered_question_is_routed_to_another_role(self):
        session = build(
            say("trend", "趋势分析师", "现有观点"),
            say("skeptic", "怀疑者", "第一批用户为什么不用现成的？", phase="回应", intent="question", replies_to="event-000000"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertIn("提问还没有人回答", plan.reason)
        self.assertEqual(plan.reply_to_event_id, session.utterances[-1].event_id)
        self.assertNotEqual(plan.speaker_id, "skeptic")

    def test_challenged_role_that_has_not_replied_speaks_next(self):
        session = build(
            say("builder", "创业实践者", "先做小范围试点"),
            say("skeptic", "怀疑者", "没有和现有替代方案比较", intent="challenge", replies_to="event-000000"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.speaker_id, "builder")
        self.assertEqual(plan.reply_to_event_id, session.utterances[-1].event_id)
        self.assertIn("质疑尚未回应", plan.reason)

    def test_role_is_not_reused_when_it_already_replied(self):
        session = build(
            say("builder", "创业实践者", "先做小范围试点"),
            say("skeptic", "怀疑者", "没有和现有替代方案比较", intent="challenge", replies_to="event-000000"),
            say("builder", "创业实践者", "我补充对比数据", phase="正面反驳", intent="challenge", replies_to="event-000001"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertNotEqual(plan.speaker_id, "builder")

    def test_silent_role_is_brought_back(self):
        session = build(
            say("skeptic", "怀疑者", "质疑一"),
            say("skeptic", "怀疑者", "质疑二"),
            say("trend", "趋势分析师", "我只说一次"),
            say("builder", "创业实践者", "二"),
            say("builder", "创业实践者", "三"),
            say("builder", "创业实践者", "四"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.speaker_id, "trend")
        self.assertIn("加入交锋", plan.reason)

    def test_same_speaker_never_exceeds_two_consecutive_turns(self):
        # Only two seats, and the last two turns are the same role, so the
        # fairness guard is the only thing that can stop a third turn in a row.
        two = [role for role in ROLES if role.id in {"trend", "builder"}]
        session = build(
            say("builder", "创业实践者", "一"),
            say("builder", "创业实践者", "二"),
            say("builder", "创业实践者", "三"),
            say("trend", "趋势分析师", "四"),
            say("trend", "趋势分析师", "五"),
        )
        plan = plan_turn(session, two, DiscussionState())
        self.assertNotEqual(plan.speaker_id, "trend")
        self.assertIn("避免同一角色连续发言", plan.reason)

    def test_plan_is_produced_without_any_history(self):
        session = build()
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertIn(plan.speaker_id, {role.id for role in ROLES})
        self.assertEqual(plan.reason, "补充已有观点")

    def test_roles_are_recovered_from_history_when_none_are_passed(self):
        session = build(say("trend", "趋势分析师", "一"))
        plan = plan_turn(session, [], DiscussionState())
        self.assertEqual(plan.speaker_id, "trend")
        self.assertEqual(plan.speaker_name, "趋势分析师")


if __name__ == "__main__":
    unittest.main()
