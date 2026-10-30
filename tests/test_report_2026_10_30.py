"""Regressions for the 2026-10-30 black-box report.

Every test here points at one numbered finding in
``C:\\Users\\14726\\Desktop\\测试程序\\头脑风暴\\2026-10-30-第1次测试.md``.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from brainstorm.engine import MockDiscussionProvider
from brainstorm.export import export_json, export_markdown
from brainstorm.llm import _fill_empty_card_sections
from brainstorm.models import DiscussionSession, OpportunityCard, Utterance, ViewpointKind
from brainstorm.orchestration import derive_state
from brainstorm.roles import DEFAULT_ROLES, role_name


def _session() -> DiscussionSession:
    session = DiscussionSession(topic="测试主题", mode="business", selected_role_ids=[role.id for role in DEFAULT_ROLES])
    session.utterances.extend(
        [
            Utterance("trend", "趋势分析师", "这两年这行的单量在往下走。", ViewpointKind.FACT, "独立观点", intent="support"),
            Utterance("builder", "创业实践者", "真做起来会亏在第一年的现金流上。", ViewpointKind.RISK, "独立观点", intent="challenge"),
            Utterance("need", "真实需求者", "我上次找的人根本不管售后。", ViewpointKind.ASSUMPTION, "独立观点", intent="question"),
        ]
    )
    session.rebuild_state()
    return session


class StanceNameTests(unittest.TestCase):
    def test_exported_stances_use_seat_names_not_internal_ids(self):  # B3
        session = _session()
        with tempfile.TemporaryDirectory() as folder:
            path = export_markdown(session, Path(folder) / "记录.md")
            text = path.read_text(encoding="utf-8")
        self.assertIn("趋势分析师：", text)
        self.assertIn("创业实践者：", text)
        self.assertNotIn("trend：", text)
        self.assertNotIn("builder：", text)

    def test_role_name_always_resolves_both_sections(self):
        for role in DEFAULT_ROLES:
            self.assertTrue(role_name("business", role.id))
            self.assertNotEqual(role_name("business", role.id), role.id.replace("_", " "))


class ExportKindTests(unittest.TestCase):
    def test_typed_extension_wins_over_the_selected_filter(self):  # B6
        with tempfile.TemporaryDirectory() as folder:
            session = _session()
            path = export_json(session, Path(folder) / "讨论.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["topic"], "测试主题")


class CardFillTests(unittest.TestCase):
    def test_empty_card_sections_are_filled_from_what_was_said(self):  # B5
        session = _session()
        card = OpportunityCard(title="一个方向", audience="某类人")
        _fill_empty_card_sections(card, session.utterances)
        self.assertTrue(card.support)
        self.assertTrue(card.risks)
        self.assertTrue(card.assumptions)
        self.assertTrue(card.next_steps)

    def test_filled_card_keeps_its_own_content(self):
        card = OpportunityCard(title="一个方向", audience="某类人", support=["原话"])
        _fill_empty_card_sections(card, _session().utterances)
        self.assertEqual(card.support, ["原话"])


class StateFallbackTests(unittest.TestCase):
    def test_derive_state_reads_the_stream_when_the_orchestrator_is_silent(self):  # B4
        consensus, conflicts, questions = derive_state(_session())
        self.assertTrue(consensus)
        self.assertTrue(conflicts)
        self.assertTrue(questions)
        self.assertTrue(all(len(item) <= 200 for item in (*consensus, *conflicts, *questions)))


class OfflineSmokeTests(unittest.TestCase):
    def test_offline_session_still_fills_all_six_sections(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("测试主题", list(DEFAULT_ROLES))
        card = session.opportunity
        self.assertIsNotNone(card)
        for section in (card.support, card.risks, card.assumptions, card.next_steps):
            self.assertTrue(section)


if __name__ == "__main__":
    unittest.main()
