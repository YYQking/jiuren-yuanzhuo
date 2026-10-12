import unittest

from brainstorm.models import (
    USER_INTERJECTION_WINDOW,
    DiscussionSession,
    DiscussionState,
    Role,
    StanceChange,
    Utterance,
    ViewpointKind,
)
from brainstorm.turn_planner import (
    MODERATOR_COOLDOWN_TURNS,
    USER_WINDOW,
    TurnPlan,
    detect_intervention,
    mark_duplicates,
    moderator_available,
    plan_turn,
)


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
        intent="initial", replies_to=None, duplicate=False, stance_change=None):
    return Utterance(
        speaker_id, speaker_name, content, kind, phase,
        replies_to=replies_to, origin="model", intent=intent,
        duplicate=duplicate, stance_change=stance_change,
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

    def test_two_role_duel_does_not_lock_out_the_other_roles(self):
        # 复现第一次真实跑测里的现象：第 15–20 轮只有两个角色互相挑战，
        # 其余 7 个角色再也没有机会发言。
        session = build(
            say("trend", "趋势分析师", "我先给一个背景"),
            say("builder", "创业实践者", "我提出一个机制", intent="support", replies_to="event-000000"),
            say("skeptic", "怀疑者", "我不信这个机制", intent="challenge", replies_to="event-000001"),
            say("builder", "创业实践者", "我回应你的质疑", intent="challenge", replies_to="event-000002"),
            say("skeptic", "怀疑者", "我再反驳一次", intent="challenge", replies_to="event-000003"),
            say("builder", "创业实践者", "我继续回应", intent="challenge", replies_to="event-000004"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.speaker_id, "trend",
                         "第三个角色必须有机会发言，不能两个人一直对轰")

    def test_user_interjection_is_answered_even_in_a_lopsided_history(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("user", "用户", "先讨论无障碍体验", intent="user_instruction"),
            say("builder", "创业实践者", "三"),
            say("skeptic", "怀疑者", "四"),
            say("trend", "趋势分析师", "五"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.reason, "你刚才插话，优先回应")
        self.assertEqual(plan.reply_to_event_id, "event-000002")

    def test_repeated_content_is_marked_without_being_deleted(self):
        session = build(
            say("trend", "趋势分析师", "先做小范围试点"),
            say("builder", "创业实践者", "先 做 小范围 试点"),
            say("skeptic", "怀疑者", "完全不同的观点"),
        )
        marked = mark_duplicates(session)
        self.assertEqual(marked, 1)
        self.assertEqual(len(session.utterances), 3)
        self.assertFalse(session.utterances[0].duplicate)
        self.assertTrue(session.utterances[1].duplicate)
        self.assertFalse(session.utterances[2].duplicate)

    def test_duplicate_marking_ignores_moderator_and_user_turns(self):
        session = build(
            say("moderator", "主持人", "本阶段整理"),
            say("moderator", "主持人", "本阶段整理"),
        )
        self.assertEqual(mark_duplicates(session), 0)


class InterventionTests(unittest.TestCase):
    """Each of the five protocol triggers must be reachable on its own."""

    def test_intervention_on_fully_argued_disagreement(self):
        session = build(
            say("builder", "创业实践者", "方案"),
            say("skeptic", "怀疑者", "反例一", intent="challenge", replies_to="event-000000"),
            say("skeptic", "怀疑者", "反例二", intent="challenge", replies_to="event-000000"),
            say("skeptic", "怀疑者", "反例三", intent="challenge", replies_to="event-000000"),
            say("builder", "创业实践者", "我缩小验证范围", kind=ViewpointKind.OPPORTUNITY, phase="正面反驳",
                intent="support", replies_to="event-000000",
                stance_change=StanceChange("坚持原方案", "缩小验证范围", "被反例说服，但仍保留成本疑虑")),
            say("trend", "趋势分析师", "我补充一个角度"),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "关键分歧已经充分交锋，需要主持人收束")

    def test_intervention_on_important_consensus(self):
        session = build(
            say("trend", "趋势分析师", "目标"),
            say("builder", "创业实践者", "同意一", intent="support", replies_to="event-000000"),
            say("skeptic", "怀疑者", "同意二", intent="support", replies_to="event-000000"),
            say("builder", "创业实践者", "同意三", intent="support", replies_to="event-000000"),
            say("skeptic", "怀疑者", "另一个角度"),
            say("trend", "趋势分析师", "再补充一点"),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "已出现重要共识，需要主持人确认")

    def test_intervention_on_rising_duplicates(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("skeptic", "怀疑者", "三"),
            say("trend", "趋势分析师", "四"),
            say("builder", "创业实践者", "五", duplicate=True),
            say("skeptic", "怀疑者", "六", duplicate=True),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "重复观点增加，需要主持人整理")

    def test_intervention_on_stalled_discussion(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("trend", "趋势分析师", "三"),
            say("builder", "创业实践者", "四"),
            say("trend", "趋势分析师", "五"),
            say("builder", "创业实践者", "六"),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "发言集中在少数角色，讨论冷场")

    def test_intervention_on_falling_new_information(self):
        # Duplicate flags are not set yet (phase 4 introduces them), so this
        # exercises the content-based branch: three distinct speakers, but only
        # four distinct things said across six turns.
        session = build(
            say("trend", "趋势分析师", "一"),
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("builder", "创业实践者", "二"),
            say("skeptic", "怀疑者", "三"),
            say("trend", "趋势分析师", "四"),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "新观点减少，需要主持人整理")

    def test_no_intervention_on_short_or_healthy_history(self):
        short = build(say("trend", "趋势分析师", "一"))
        self.assertEqual(detect_intervention(short), (False, ""))
        healthy = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "我反对这个前提", intent="challenge", replies_to="event-000000"),
            say("skeptic", "怀疑者", "我追问证据", intent="question", replies_to="event-000001"),
            say("trend", "趋势分析师", "我补充数据", intent="elaborate", replies_to="event-000002"),
            say("builder", "创业实践者", "我调整范围", phase="正面反驳", intent="support", replies_to="event-000002"),
            say("skeptic", "怀疑者", "我保留疑虑", intent="question"),
        )
        self.assertEqual(detect_intervention(healthy), (False, ""))

    def test_intervention_produces_a_moderator_plan(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("trend", "趋势分析师", "三"),
            say("builder", "创业实践者", "四"),
            say("trend", "趋势分析师", "五"),
            say("builder", "创业实践者", "六"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertTrue(plan.moderator)
        self.assertEqual(plan.speaker_id, "moderator")
        self.assertEqual(plan.phase, "状态整理")
        self.assertEqual(plan.intervention_reason, "发言集中在少数角色，讨论冷场")


class PendingInterjectionTests(unittest.TestCase):
    """The planner expires an interjection after USER_WINDOW utterances, but the
    prompt kept carrying it forever: measured at turn 10 the planner had stopped
    prioritising it while state.pending_user_interjection still held the text.
    Both now read one predicate."""

    def test_live_interjection_is_reported(self):
        session = build(
            say("trend", "趋势分析师", "开场观点"),
            say("user", "用户", "先讨论无障碍体验", intent="user_instruction"),
        )
        pending = session.pending_interjection(USER_WINDOW)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.content, "先讨论无障碍体验")
        session.rebuild_state()
        self.assertEqual(session.discussion_state.pending_user_interjection, "先讨论无障碍体验")

    def test_answered_interjection_stops_being_pending(self):
        session = build(
            say("user", "用户", "先讨论无障碍体验", intent="user_instruction"),
            say("trend", "趋势分析师", "我先回应插话", intent="elaborate", replies_to="event-000000"),
        )
        self.assertIsNone(session.pending_interjection(USER_WINDOW))
        session.rebuild_state()
        self.assertEqual(session.discussion_state.pending_user_interjection, "")

    def test_interjection_expires_after_the_window(self):
        utterances = [say("user", "用户", "先讨论无障碍体验", intent="user_instruction")]
        for index in range(USER_WINDOW):
            utterances.append(say("trend", "趋势分析师", f"后续{index}"))
        session = build(*utterances)
        self.assertIsNone(session.pending_interjection(USER_WINDOW))
        session.rebuild_state()
        self.assertEqual(session.discussion_state.pending_user_interjection, "")

    def test_planner_and_state_agree_on_expiry(self):
        utterances = [say("user", "用户", "先讨论无障碍体验", intent="user_instruction")]
        for index in range(USER_WINDOW):
            utterances.append(say("trend", "趋势分析师", f"后续{index}"))
        session = build(*utterances)
        plan = plan_turn(session, ROLES, DiscussionState())
        session.rebuild_state()
        self.assertNotEqual(plan.reason, "你刚才插话，优先回应")
        self.assertEqual(session.discussion_state.pending_user_interjection, "")


class ModeratorCooldownTests(unittest.TestCase):
    """The host's own turn is invisible to every trigger, so without a cooldown the
    same trigger fires again on the next click and the nine roles never get the
    floor back.  Measured before this test existed: three consecutive plan_turn
    calls returned moderator while the trigger stayed true."""

    def stalled(self):
        return build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("trend", "趋势分析师", "三"),
            say("builder", "创业实践者", "四"),
            say("trend", "趋势分析师", "五"),
            say("builder", "创业实践者", "六"),
        )

    def host_turn(self):
        return Utterance("moderator", "主持人", "本阶段整理", ViewpointKind.SUMMARY, "状态整理",
                         origin="model", intent="synthesize")

    def test_host_is_not_scheduled_twice_in_a_row(self):
        session = self.stalled()
        session.append_utterance(self.host_turn())
        self.assertFalse(moderator_available(session))
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertFalse(plan.moderator, "主持人整理完不能马上再整理一次")
        self.assertNotEqual(plan.speaker_id, "moderator")
        self.assertNotEqual(plan.reason, "发言集中在少数角色，讨论冷场")

    def test_trigger_still_reported_as_evidence_while_the_cooldown_holds(self):
        """The controller reads detect_intervention for the UI reason, so the
        evidence function must keep reporting what it sees."""
        session = self.stalled()
        session.append_utterance(self.host_turn())
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "发言集中在少数角色，讨论冷场")

    def test_host_returns_after_the_cooldown(self):
        session = self.stalled()
        session.append_utterance(self.host_turn())
        for index in range(MODERATOR_COOLDOWN_TURNS):
            speaker_id = "trend" if index % 2 == 0 else "builder"
            session.append_utterance(say(speaker_id, speaker_id, f"继续{index}"))
        self.assertTrue(moderator_available(session))
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertTrue(plan.moderator)

    def test_host_available_when_it_never_spoke(self):
        self.assertTrue(moderator_available(self.stalled()))


if __name__ == "__main__":
    unittest.main()
