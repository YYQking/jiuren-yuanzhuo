"""第三个分区：拆一个说法（说法体检单）。"""

import unittest

from brainstorm.agenda import CLAIM_LAYERS, LAYER_TURNS, layer_for, layer_names, layer_target_reached
from brainstorm.engine import MockDiscussionProvider
from brainstorm.llm import AnthropicDiscussionProvider, _Response, TurnSpec, Usage
from brainstorm.roles import (
    CLAIM_ROLES,
    DEFAULT_ROLES,
    EVENT_ROLES,
    MODE_LABELS,
    SECTION_TEXT,
    mode_for_roles,
)
from brainstorm.storage import SessionStore


def _seats():
    return list(CLAIM_ROLES)


RECORDED_PROMPT = (
    '{"content":"这条发言有内容","kind":"假设","intent":"challenge",'
    '"confidence":"know","reactions":[]}'
)


class PromptRecorder(AnthropicDiscussionProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompts = []

    def _request(self, prompt, **kwargs):  # type: ignore[override]
        self.prompts.append(prompt)
        return _Response(RECORDED_PROMPT, Usage(1, 1, 1))


class ClaimRoleTests(unittest.TestCase):
    def test_eight_seats_with_their_own_voices(self):
        self.assertEqual(len(CLAIM_ROLES), 8)
        self.assertEqual(len({role.id for role in CLAIM_ROLES}), 8)
        self.assertEqual(len({role.name for role in CLAIM_ROLES}), 8)
        for role in CLAIM_ROLES:
            self.assertTrue(role.duty.strip(), role.id)
            self.assertTrue(role.voice.strip(), role.id)
            self.assertTrue(role.id.startswith("claim_"), role.id)

    def test_names_do_not_repeat_other_sections(self):
        taken = {role.name for role in DEFAULT_ROLES} | {role.name for role in EVENT_ROLES}
        self.assertFalse(taken & {role.name for role in CLAIM_ROLES})

    def test_selected_seats_decide_the_section(self):
        self.assertEqual(mode_for_roles([role.id for role in CLAIM_ROLES]), "claim")
        self.assertEqual(mode_for_roles(["claim_skeptic", "claim_data"]), "claim")
        self.assertEqual(mode_for_roles(["builder"]), "business")
        self.assertEqual(mode_for_roles(["qian"]), "event")
        self.assertEqual(MODE_LABELS["claim"], "观点讨论")

    def test_section_text_covers_every_key_the_lobby_needs(self):
        business = set(SECTION_TEXT["business"])
        claim = set(SECTION_TEXT["claim"])
        self.assertEqual(business - claim, set())
        self.assertEqual(SECTION_TEXT["claim"]["archive_title"], "说法体检单")
        self.assertEqual(SECTION_TEXT["claim"]["archive_empty"], "讨论结束后，这里会显示说法体检单")


class ClaimAgendaTests(unittest.TestCase):
    def test_layers_walk_down_a_claim(self):
        self.assertEqual(len(CLAIM_LAYERS), 5)
        self.assertEqual(layer_names("claim"), CLAIM_LAYERS)
        self.assertEqual(layer_names("business")[0], "现象")

    def test_a_layer_takes_several_turns(self):
        from brainstorm.models import Utterance, ViewpointKind

        def history(count):
            return [
                Utterance("claim_data", "数据员", f"第{index}条", ViewpointKind.FACT, "动态交锋")
                for index in range(count)
            ]

        self.assertEqual(layer_for(history(0), "claim"), CLAIM_LAYERS[0])
        self.assertEqual(layer_for(history(LAYER_TURNS), "claim"), CLAIM_LAYERS[1])
        self.assertFalse(layer_target_reached(history(0), "claim"))


class ClaimOfflineTests(unittest.TestCase):
    def test_opening_states_the_claim_at_its_best_then_cracks_it(self):
        session = MockDiscussionProvider().discuss(
            "「加班越多产出越高」这个说法靠谱吗", _seats()
        )
        self.assertEqual(session.mode, "claim")
        self.assertGreaterEqual(len(session.utterances), 12)
        self.assertIn("说法", session.opportunity.title)
        self.assertEqual(set(session.selected_role_ids), {role.id for role in CLAIM_ROLES})
        body = "\n".join(item.content for item in session.utterances)
        self.assertIn("反例", body)
        self.assertIn("说法", body)

    def test_offline_card_is_not_the_business_card(self):
        session = MockDiscussionProvider().discuss("「学历越高越会赚钱」", _seats())
        card = session.opportunity
        self.assertIn("说法", card.title)
        self.assertNotIn("目标用户", "\n".join(card.next_steps))
        self.assertTrue(card.risks and card.assumptions)

    def test_extending_stays_in_the_claim_section(self):
        provider = MockDiscussionProvider()
        session = provider.discuss("「远程办公效率更低」这个说法", _seats())
        batch = provider.extend(session, 2)
        self.assertEqual(len(batch), 8)
        self.assertEqual(session.mode, "claim")
        self.assertEqual(session.phase, "继续拆")


class ClaimPromptTests(unittest.TestCase):
    def _provider(self):
        return PromptRecorder(client=None, model="test-model")

    def test_prompt_teaches_how_to_take_a_claim_apart(self):
        provider = self._provider()
        provider._generate_turn_result(
            "「年轻人不买房是因为穷」",
            _seats(),
            (),
            (),
            TurnSpec("claim_skeptic", "挑刺者", "动态交锋"),
        )
        prompt = provider.prompts[0]
        self.assertIn("拆说法的桌上", prompt)
        self.assertIn("不许编", prompt)
        self.assertIn("反例", prompt)
        self.assertIn("挑刺者", prompt)
        self.assertNotIn("吃瓜纪要", prompt)
        self.assertNotIn("目标用户", prompt)

    def test_final_turn_asks_for_the_claim_report(self):
        provider = self._provider()
        provider._generate_turn_result(
            "「年轻人不买房是因为穷」",
            _seats(),
            (),
            (),
            TurnSpec("claim_advocate", "主张者", "阶段总结", final=True),
        )
        prompt = provider.prompts[0]
        self.assertIn("说法体检单", prompt)
        self.assertIn("缺什么证据", prompt)


class ClaimStorageTests(unittest.TestCase):
    def test_a_claim_session_survives_a_save_and_load(self):
        import tempfile
        from pathlib import Path

        session = MockDiscussionProvider().discuss("「会议越多决策越慢」", _seats())
        with tempfile.TemporaryDirectory() as folder:
            store = SessionStore(Path(folder))
            path = store.save(session)
            loaded = store.load(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.mode, "claim")
        self.assertEqual(len(loaded.utterances), len(session.utterances))


if __name__ == "__main__":
    unittest.main()
