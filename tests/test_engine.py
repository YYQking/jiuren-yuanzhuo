"""Core behavior tests for the offline discussion provider."""

import unittest

from brainstorm.engine import MockDiscussionProvider
from brainstorm.models import Role, Utterance, ViewpointKind
from brainstorm.roles import DEFAULT_ROLES


class MockDiscussionTests(unittest.TestCase):
    def test_new_discussion_metadata_round_trips(self):
        session = MockDiscussionProvider().discuss("无障碍服务", DEFAULT_ROLES[:3])
        item = session.utterances[1]
        self.assertTrue(item.event_id)
        self.assertEqual(item.sequence, 1)
        self.assertEqual(item.intent, "initial")
        self.assertEqual(item.verification, "unverified")
        self.assertEqual(session.phase, "首轮观点")
        self.assertEqual(session.discussion_state.unresolved_questions, [])

    def test_nine_default_roles_exist(self):
        self.assertEqual(len(DEFAULT_ROLES), 9)
        self.assertEqual(len({role.id for role in DEFAULT_ROLES}), 9)

    def test_disabled_roles_do_not_speak(self):
        roles = [role for role in DEFAULT_ROLES if role.id in {"need", "skeptic"}]
        session = MockDiscussionProvider().discuss("社区养老服务", roles)
        speakers = {utterance.speaker_id for utterance in session.utterances}
        self.assertTrue(speakers <= {"moderator", "need", "skeptic"})
        self.assertNotIn("trend", speakers)

    def test_output_contains_opportunity_and_risk(self):
        session = MockDiscussionProvider().discuss("个人信息管理", DEFAULT_ROLES)
        self.assertIsNotNone(session.opportunity)
        kinds = {utterance.kind for utterance in session.utterances}
        self.assertIn(ViewpointKind.OPPORTUNITY, kinds)
        self.assertIn(ViewpointKind.RISK, kinds)
        self.assertTrue(session.opportunity.next_steps)

    def test_topic_is_required(self):
        with self.assertRaises(ValueError):
            MockDiscussionProvider().discuss("   ", DEFAULT_ROLES)

    def test_custom_role_id_uses_safe_generic_template(self):
        role = Role("custom", "自定义角色", "观察主题", "#fff", "提出独立判断")
        session = MockDiscussionProvider().discuss("测试主题", [role])
        self.assertEqual(len(session.utterances), 3)
        self.assertEqual(session.utterances[1].speaker_name, "自定义角色")

    def test_extend_adds_replies_and_reuses_roles_without_fixed_round_limit(self):
        roles = [role for role in DEFAULT_ROLES if role.id in {"builder", "skeptic", "need"}]
        provider = MockDiscussionProvider()
        session = provider.discuss("社区养老服务", roles)
        original_count = len(session.utterances)

        first_batch = provider.extend(session, 1)
        second_batch = provider.extend(session, 2)

        self.assertEqual(len(first_batch), 8)
        self.assertEqual(len(second_batch), 8)
        self.assertEqual(len(session.utterances), original_count + 16)
        self.assertTrue(any(item.replies_to for item in first_batch))
        self.assertTrue(any(item.speaker_id == "skeptic" for item in first_batch))
        self.assertTrue(any(item.speaker_id == first_batch[0].speaker_id for item in first_batch[1:]))
        self.assertTrue({item.speaker_id for item in session.utterances} <= {"moderator", "builder", "skeptic", "need"})
        self.assertIsNotNone(session.opportunity)
        self.assertGreaterEqual(sum(session.opportunity.stance_counts.values()), original_count)

    def test_state_analyzer_tracks_consensus_conflict_and_unresolved_question(self):
        session = MockDiscussionProvider().discuss("社区养老", DEFAULT_ROLES)
        state = MockDiscussionProvider.analyze_state(session)
        self.assertTrue(state.consensus)
        self.assertTrue(state.conflicts)
        self.assertTrue(state.unresolved_questions)
        self.assertGreaterEqual(state.duplicate_count, 0)

    def test_extend_marks_reply_intent_and_can_change_stance(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("社区养老", DEFAULT_ROLES)
        added = provider.extend(session, 1)
        self.assertTrue(any(item.replies_to for item in added))
        self.assertTrue(any(item.intent in {"support", "challenge", "question", "elaborate"} for item in added))
        self.assertTrue(any(item.stance_change is not None for item in added))
        self.assertEqual(session.utterances[-1].speaker_id, "moderator")
        self.assertIn(session.phase, {"动态交锋", "状态整理"})

    def test_extend_keeps_user_interjection_as_highest_priority_context(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("数字服务", DEFAULT_ROLES[:4])
        session.append_utterance(Utterance("user", "用户", "优先讨论无障碍体验", ViewpointKind.ASSUMPTION, "用户插话", simulated=False, origin="user", intent="user_instruction"))
        added = provider.extend(session, 1)
        self.assertTrue(any("无障碍体验" in item.content for item in added))
        self.assertEqual(session.discussion_state.pending_user_interjection, "")

    def test_live_batches_rotate_all_roles_without_impersonating_user(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("养老服务", DEFAULT_ROLES)
        session.utterances.append(Utterance("user", "用户", "请关注行动不便的人群", ViewpointKind.ASSUMPTION, "用户插话", simulated=False))
        speakers = set()
        for batch in range(1, 10):
            added = provider.extend(session, batch)
            speakers.update(item.speaker_id for item in added)
            self.assertNotIn("user", {item.speaker_id for item in added})
        self.assertTrue({role.id for role in DEFAULT_ROLES} <= speakers)

    def test_state_trigger_does_not_intervene_after_a_clean_summary(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("连续讨论", DEFAULT_ROLES[:4])
        first = provider.extend(session, 1)
        self.assertEqual(first[-1].speaker_id, "moderator")
        second = provider.extend(session, 2)
        self.assertTrue(second)
        self.assertTrue(all(item.speaker_id != "moderator" for item in second))
        self.assertEqual(session.phase, "动态交锋")

    def test_intervention_is_triggered_by_repeated_conflicting_turns(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("重复分歧", DEFAULT_ROLES[:4])
        provider.extend(session, 1)
        target = session.utterances[-2]
        session.utterances[-2] = target.__class__(
            target.speaker_id,
            target.speaker_name,
            "重复观点：现有替代方案仍然足够",
            target.kind,
            target.phase,
            target.replies_to,
            target.simulated,
            target.origin,
            target.event_id,
            target.sequence,
            "challenge",
            target.verification,
            target.stance_change,
            True,
        )
        added = provider.extend(session, 2)
        self.assertEqual(added[-1].speaker_id, "moderator")
        self.assertTrue(session.discussion_state.host_intervention_reason)


if __name__ == "__main__":
    unittest.main()
