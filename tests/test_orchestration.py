import unittest

from brainstorm.models import DiscussionSession, DiscussionState, Role, Utterance, ViewpointKind
from brainstorm.orchestration import (
    build_orchestration_prompt,
    build_review_prompt,
    parse_orchestration,
    parse_review,
)
from brainstorm.turn_planner import TurnPlan


ROLES = [
    Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化是否真实。"),
    Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
]


def session_with(*utterances):
    session = DiscussionSession(topic="社区养老", selected_role_ids=["trend", "builder"])
    for item in utterances:
        session.append_utterance(item)
    return session


def local_plan():
    return TurnPlan("trend", "趋势分析师", "回应", "elaborate", reason="趋势分析师的疑问尚未回应")


class OrchestrationPromptTests(unittest.TestCase):
    def test_prompt_includes_roster_event_ids_and_local_facts(self):
        session = session_with(Utterance("trend", "趋势分析师", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        prompt = build_orchestration_prompt(session, ROLES, local_plan())
        self.assertIn("社区养老", prompt)
        self.assertIn("trend", prompt)
        self.assertIn("builder", prompt)
        self.assertIn("event-000000", prompt)
        self.assertIn("疑问尚未回应", prompt)
        self.assertIn("consensus", prompt)
        self.assertIn("moderator", prompt)

    def test_prompt_states_sources_are_unverified(self):
        prompt = build_orchestration_prompt(session_with(), ROLES, local_plan())
        self.assertIn("未核验", prompt)

    def test_prompt_states_the_fairness_caps_and_recent_speakers(self):
        """The model must be told the floor-sharing rule, otherwise the local
        guard has to overrule it after the fact."""
        turns = []
        for index in range(6):
            speaker_id = "trend" if index % 2 == 0 else "builder"
            turns.append(Utterance(speaker_id, speaker_id, f"第{index}条", ViewpointKind.ASSUMPTION, "动态交锋"))
        prompt = build_orchestration_prompt(session_with(*turns), ROLES, local_plan())
        self.assertIn("连续", prompt)
        self.assertIn("最近", prompt)
        self.assertIn("趋势分析师", prompt)


class OrchestrationParseTests(unittest.TestCase):
    def test_parses_plan_and_state_refresh(self):
        session = session_with(Utterance("trend", "趋势分析师", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        payload = (
            '{"key_question":"第一批用户为什么不用现成的？","speaker_id":"builder",'
            '"must_answer":"给出与现有替代方案的对比","avoid":["重复讲趋势"],'
            '"intervene":false,"intervention_reason":"",'
            '"consensus":["先做小范围试点"],"conflicts":["需求强度未验证"],"unresolved":["付费意愿"]}'
        )
        plan, refresh = parse_orchestration(payload, session, ROLES, local_plan())
        self.assertEqual(plan.speaker_id, "builder")
        self.assertEqual(plan.speaker_name, "创业实践者")
        self.assertEqual(plan.source, "model")
        self.assertEqual(plan.must_answer, "给出与现有替代方案的对比")
        self.assertEqual(plan.avoid, ("重复讲趋势",))
        self.assertEqual(plan.key_question, "第一批用户为什么不用现成的？")
        self.assertEqual(refresh.consensus, ("先做小范围试点",))
        self.assertEqual(refresh.conflicts, ("需求强度未验证",))
        self.assertEqual(refresh.unresolved, ("付费意愿",))

    def test_moderator_decision_produces_an_intervention_plan(self):
        payload = (
            '{"key_question":"是否已有共识？","speaker_id":"moderator","must_answer":"整理共识",'
            '"avoid":[],"intervene":true,"intervention_reason":"已出现重要共识",'
            '"consensus":[],"conflicts":[],"unresolved":[]}'
        )
        plan, _ = parse_orchestration(payload, session_with(), ROLES, local_plan())
        self.assertTrue(plan.moderator)
        self.assertEqual(plan.phase, "状态整理")
        self.assertEqual(plan.intervention_reason, "已出现重要共识")

    def test_moderator_decision_is_rejected_while_the_host_is_in_cooldown(self):
        """A model that keeps asking for the host must not be able to park the
        roundtable on the host; rejecting makes the caller fall back to the local
        role plan."""
        turns = []
        for index in range(6):
            speaker_id = "trend" if index % 2 == 0 else "builder"
            turns.append(Utterance(speaker_id, speaker_id, f"第{index}条", ViewpointKind.ASSUMPTION, "动态交锋"))
        turns.append(Utterance("moderator", "主持人", "本阶段整理", ViewpointKind.SUMMARY, "状态整理"))
        session = session_with(*turns)
        payload = (
            '{"key_question":"是否已有共识？","speaker_id":"moderator","must_answer":"整理共识",'
            '"avoid":[],"intervene":true,"intervention_reason":"已出现重要共识",'
            '"consensus":[],"conflicts":[],"unresolved":[]}'
        )
        with self.assertRaises(ValueError):
            parse_orchestration(payload, session, ROLES, local_plan())

    def test_moderator_decision_is_accepted_when_the_host_has_not_just_spoken(self):
        turns = []
        for index in range(6):
            speaker_id = "trend" if index % 2 == 0 else "builder"
            turns.append(Utterance(speaker_id, speaker_id, f"第{index}条", ViewpointKind.ASSUMPTION, "动态交锋"))
        payload = (
            '{"key_question":"是否已有共识？","speaker_id":"moderator","must_answer":"整理共识",'
            '"avoid":[],"intervene":true,"intervention_reason":"已出现重要共识",'
            '"consensus":[],"conflicts":[],"unresolved":[]}'
        )
        plan, _ = parse_orchestration(payload, session_with(*turns), ROLES, local_plan())
        self.assertTrue(plan.moderator)

    def test_unknown_speaker_raises_so_the_caller_can_fall_back(self):
        payload = ('{"key_question":"x","speaker_id":"nobody","must_answer":"y","avoid":[],'
                   '"intervene":false,"intervention_reason":"","consensus":[],"conflicts":[],"unresolved":[]}')
        with self.assertRaises(ValueError):
            parse_orchestration(payload, session_with(), ROLES, local_plan())

    def test_overriding_the_host_with_a_role_also_resets_the_host_phase(self):
        """Measured before the fix: a role turn kept phase 状态整理 / kind 总结 /
        intent synthesize from the host plan it replaced."""
        host_plan = TurnPlan("moderator", "主持人", "状态整理", "synthesize", "总结",
                            reason="发言集中在少数角色，讨论冷场", moderator=True,
                            intervention_reason="发言集中在少数角色，讨论冷场")
        payload = ('{"key_question":"x","speaker_id":"builder","must_answer":"说明谁付钱",'
                   '"avoid":[],"intervene":false,"intervention_reason":"",'
                   '"consensus":[],"conflicts":[],"unresolved":[]}')
        plan, _ = parse_orchestration(payload, session_with(), ROLES, host_plan)
        self.assertEqual(plan.speaker_id, "builder")
        self.assertFalse(plan.moderator)
        self.assertEqual(plan.intervention_reason, "")
        self.assertEqual(plan.phase, "动态交锋")
        self.assertEqual(plan.kind_hint, "假设")
        self.assertEqual(plan.intent, "elaborate")

    def test_a_role_plan_keeps_its_own_phase_when_the_speaker_changes(self):
        local = TurnPlan("trend", "趋势分析师", "正面反驳", "challenge", "风险", reason="质疑尚未回应")
        payload = ('{"key_question":"x","speaker_id":"builder","must_answer":"说明谁付钱",'
                   '"avoid":[],"intervene":false,"intervention_reason":"",'
                   '"consensus":[],"conflicts":[],"unresolved":[]}')
        plan, _ = parse_orchestration(payload, session_with(), ROLES, local)
        self.assertEqual(plan.phase, "正面反驳")
        self.assertEqual(plan.kind_hint, "风险")
        self.assertEqual(plan.intent, "challenge")

    def test_missing_must_answer_keeps_the_speaker_and_the_state_refresh(self):
        """One sloppy field used to discard the model's speaker choice and the
        state refresh together.  The turn prompt already falls back to the local
        reason, so a usable decision must survive."""
        payload = ('{"key_question":"x","speaker_id":"builder","avoid":["重复讲趋势"],'
                   '"intervene":false,"intervention_reason":"",'
                   '"consensus":["先做小范围试点"],"conflicts":[],"unresolved":["付费意愿"]}')
        plan, refresh = parse_orchestration(payload, session_with(), ROLES, local_plan())
        self.assertEqual(plan.speaker_id, "builder")
        self.assertEqual(plan.must_answer, "")
        self.assertEqual(plan.avoid, ("重复讲趋势",))
        self.assertEqual(refresh.consensus, ("先做小范围试点",))
        self.assertEqual(refresh.unresolved, ("付费意愿",))

    def test_malformed_payload_raises(self):
        with self.assertRaises(ValueError):
            parse_orchestration('{"key_question": ', session_with(), ROLES, local_plan())

    def test_state_refresh_is_trimmed_and_type_checked(self):
        payload = (
            '{"key_question":"x","speaker_id":"trend","must_answer":"y","avoid":["a", 5],'
            '"intervene":false,"intervention_reason":"",'
            '"consensus":["一", "二", "三", "四", "五", "六"],"conflicts":"不是列表","unresolved":[1, 2]}'
        )
        _, refresh = parse_orchestration(payload, session_with(), ROLES, local_plan())
        self.assertEqual(refresh.consensus, ("一", "二", "三", "四"))
        self.assertEqual(refresh.conflicts, ())
        self.assertEqual(refresh.unresolved, ())


class ReviewTests(unittest.TestCase):
    def test_review_prompt_contains_target_and_content(self):
        session = session_with(Utterance("trend", "趋势分析师", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        plan = TurnPlan("builder", "创业实践者", "正面反驳", "challenge", must_answer="给出对比数据", reason="x")
        utterance = Utterance("builder", "创业实践者", "我给出对比", ViewpointKind.RISK, "正面反驳", origin="model")
        prompt = build_review_prompt(session, plan, utterance)
        self.assertIn("给出对比数据", prompt)
        self.assertIn("我给出对比", prompt)

    def test_passing_review_has_no_criticism(self):
        review = parse_review('{"passed":true,"repeats":"","avoided":"","fabricated":""}')
        self.assertTrue(review.passed)
        self.assertEqual(review.criticism, "")

    def test_failing_review_builds_a_concrete_criticism(self):
        review = parse_review(
            '{"passed":false,"repeats":"重复了 event-000000 的趋势判断",'
            '"avoided":"回避了被要求的对比数据","fabricated":"引用了来源里没有的数字"}'
        )
        self.assertFalse(review.passed)
        self.assertIn("重复了 event-000000 的趋势判断", review.criticism)
        self.assertIn("回避了被要求的对比数据", review.criticism)
        self.assertIn("引用了来源里没有的数字", review.criticism)

    def test_a_pass_claiming_problems_is_treated_as_a_failure(self):
        review = parse_review('{"passed":true,"repeats":"其实重复了前文","avoided":"","fabricated":""}')
        self.assertFalse(review.passed)

    def test_an_incomplete_answer_does_not_send_the_turn_back(self):
        """人说话不会把每个问题答完；只有重复和编造才值得重写。"""
        review = parse_review(
            '{"passed":false,"repeats":"","avoided":"没把被要求的三个步骤都写完","fabricated":""}'
        )
        self.assertTrue(review.passed)
        self.assertIn("没把被要求的三个步骤都写完", review.criticism)

    def test_fabrication_alone_sends_the_turn_back(self):
        review = parse_review(
            '{"passed":true,"repeats":"","avoided":"","fabricated":"编了一句来源里没有的原话"}'
        )
        self.assertFalse(review.passed)

    def test_malformed_review_raises(self):
        with self.assertRaises(ValueError):
            parse_review("not json")


if __name__ == "__main__":
    unittest.main()
