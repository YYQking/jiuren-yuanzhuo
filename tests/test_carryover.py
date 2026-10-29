"""「接着再聊」的底稿：只留结论、分歧和规矩，别把整场记录再喂一遍。"""

from __future__ import annotations

import unittest
from datetime import datetime

from brainstorm.carryover import (
    DISPUTE_LIMIT,
    TOTAL_LIMIT,
    carry_note,
    open_disputes,
)
from brainstorm.models import DiscussionSession, OpportunityCard, Utterance, ViewpointKind


def _say(name: str, content: str, intent: str = "elaborate") -> Utterance:
    return Utterance(
        speaker_id="x",
        speaker_name=name,
        content=content,
        kind=ViewpointKind.OPINION if hasattr(ViewpointKind, "OPINION") else ViewpointKind.FACT,
        phase="正反交锋",
        intent=intent,
    )


def _session(mode: str = "business") -> DiscussionSession:
    card = OpportunityCard(
        title="给县城小店做代收快递",
        audience="没空去镇上的店主",
        support=["快递点太少，确实要跑二十公里"],
        risks=["抽成谈不下来就一直亏"],
        assumptions=["店主愿意为省跑腿付钱"],
        next_steps=["先问十家店愿不愿意按件付"],
    )
    session = DiscussionSession(
        topic="小县城快递代收能不能做成生意",
        mode=mode,
        created_at=datetime(2026, 10, 30, 1, 20),
        selected_role_ids=["trend", "builder"],
        opportunity=card,
    )
    session.utterances = [
        _say("趋势分析师", "这个方向我看好，因为政策在推", "support"),
        _say("创业实践者", "先说钱：一单抽两块，跑一天不够油钱", "challenge"),
        _say("数据员", "你这十家店是哪个县城？", "question"),
        _say("怀疑者", "凭啥觉得店主愿意按件付？", "challenge"),
        _say("主持人", "先把分歧记下来", "synthesize"),
    ]
    return session


class CarryNoteTests(unittest.TestCase):
    def test_note_carries_topic_and_the_last_archive(self):
        note = carry_note(_session())
        self.assertIn("小县城快递代收能不能做成生意", note)
        self.assertIn("机会档案", note)
        self.assertIn("给县城小店做代收快递", note)
        self.assertIn("没空去镇上的店主", note)

    def test_note_says_loudly_it_is_not_external_evidence(self):
        note = carry_note(_session())
        self.assertIn("不是外部事实", note)
        self.assertIn("不能当成已经证实的情报引用", note)

    def test_note_forbids_repeating_what_was_already_said(self):
        note = carry_note(_session())
        self.assertIn("不要复述上面已经说过的内容", note)
        self.assertIn("我猜", note)

    def test_note_keeps_the_unfinished_disputes(self):
        note = carry_note(_session())
        self.assertIn("上次没吵完的地方", note)
        self.assertIn("创业实践者", note)
        self.assertIn("数据员", note)
        # 已经收束的那句合成发言不算分歧
        self.assertNotIn("先把分歧记下来", note)

    def test_disputes_are_chronological_and_capped(self):
        session = _session()
        session.utterances = [
            _say("甲", "一", "challenge"),
            _say("乙", "二", "question"),
            _say("丙", "三", "challenge"),
            _say("丁", "四", "challenge"),
        ]
        disputes = open_disputes(session)
        self.assertEqual(len(disputes), DISPUTE_LIMIT)
        self.assertTrue(disputes[0].startswith("乙"))
        self.assertTrue(disputes[-1].startswith("丁"))

    def test_event_section_uses_its_own_wording(self):
        note = carry_note(_session("event"))
        self.assertIn("吃瓜纪要", note)
        self.assertNotIn("机会档案", note)

    def test_claim_section_uses_its_own_wording(self):
        note = carry_note(_session("claim"))
        self.assertIn("说法体检单", note)

    def test_bare_session_still_gives_a_usable_note(self):
        session = DiscussionSession(topic="一个还没聊完的问题", mode="event")
        session.utterances = [_say("雷子", "我先说两句", "initial")]
        note = carry_note(session)
        self.assertIn("一个还没聊完的问题", note)
        self.assertIn("这次的规矩", note)

    def test_note_length_is_bounded(self):
        session = _session()
        session.opportunity = OpportunityCard(
            title="标题" * 40,
            audience="用户" * 40,
            support=["理由" * 60 for _ in range(6)],
            risks=["风险" * 60 for _ in range(6)],
            assumptions=["假设" * 60 for _ in range(6)],
            next_steps=["下一步" * 60 for _ in range(6)],
        )
        session.utterances = [_say(f"人{i}", "很长的话" * 30, "challenge") for i in range(8)]
        self.assertLessEqual(len(carry_note(session)), TOTAL_LIMIT)


if __name__ == "__main__":
    unittest.main()
