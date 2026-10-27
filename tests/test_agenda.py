import unittest

from brainstorm.agenda import (
    BUSINESS_LAYERS,
    EVENT_LAYERS,
    LAYER_TURNS,
    layer_context,
    layer_for,
    layer_index,
    layer_names,
    layer_target_reached,
    spoken_turns,
)
from brainstorm.llm import AnthropicDiscussionProvider, TurnSpec
from brainstorm.models import DiscussionSession, Role, Utterance, ViewpointKind
from brainstorm.turn_planner import TurnPlan


def history_of(count: int, host_turns: int = 0, seat: str = "builder") -> list[Utterance]:
    items = [
        Utterance(seat, "创业实践者", f"第{index}条", ViewpointKind.FACT, "动态交锋")
        for index in range(count)
    ]
    items.extend(
        Utterance("moderator", "主持人", f"主持人第{index}条", ViewpointKind.SUMMARY, "状态整理")
        for index in range(host_turns)
    )
    return items


class PromptRecordingProvider(AnthropicDiscussionProvider):
    """Captures the prompt so the test can assert on what the model is told."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompts: list[str] = []

    def _request(self, prompt, **kwargs):  # type: ignore[override]
        self.prompts.append(prompt)
        from brainstorm.llm import Usage, _Response

        payload = (
            '{"content":"这条发言有内容","kind":"事实","intent":"challenge",'
            '"confidence":"know","reactions":[]}'
        )
        return _Response(payload, Usage(1, 1, 1))


class AgendaTests(unittest.TestCase):
    def test_business_and_event_layers_are_both_deep(self):
        self.assertGreaterEqual(len(BUSINESS_LAYERS), 5)
        self.assertGreaterEqual(len(EVENT_LAYERS), 5)
        self.assertEqual(layer_names("business"), BUSINESS_LAYERS)
        self.assertEqual(layer_names("event"), EVENT_LAYERS)

    def test_a_layer_takes_several_turns_before_the_next_one(self):
        self.assertEqual(layer_for(history_of(0), "business"), BUSINESS_LAYERS[0])
        self.assertEqual(layer_for(history_of(LAYER_TURNS - 1), "business"), BUSINESS_LAYERS[0])
        self.assertEqual(layer_for(history_of(LAYER_TURNS), "business"), BUSINESS_LAYERS[1])
        self.assertEqual(layer_for(history_of(LAYER_TURNS * 2), "business"), BUSINESS_LAYERS[2])

    def test_the_last_layer_keeps_the_floor_instead_of_running_out(self):
        long_history = history_of(LAYER_TURNS * 20)
        self.assertEqual(layer_for(long_history, "business"), BUSINESS_LAYERS[-1])
        self.assertTrue(layer_target_reached(long_history, "business"))

    def test_host_and_user_turns_do_not_advance_the_layer(self):
        self.assertEqual(spoken_turns(history_of(3, host_turns=4)), 3)
        self.assertEqual(layer_index(history_of(3, host_turns=4), "business"), 0)
        self.assertEqual(layer_index(history_of(LAYER_TURNS, host_turns=9), "business"), 1)

    def test_context_names_the_layer_and_what_to_dig_into(self):
        context = layer_context(history_of(LAYER_TURNS + 1), "business")
        self.assertIn(BUSINESS_LAYERS[1], context)
        self.assertIn("别急着换层", context)

    def test_the_opening_does_not_nag_about_layers(self):
        self.assertEqual(layer_context(history_of(1), "business"), "")

    def test_turn_prompt_carries_the_layer(self):
        provider = PromptRecordingProvider(model="test-model")
        provider.complete = provider.complete  # keep the recorded version
        roles = [Role("builder", "创业实践者", "先算钱", "#fff", "提示")]
        plan = TurnPlan(
            speaker_id="builder",
            speaker_name="创业实践者",
            phase="动态交锋",
            intent="challenge",
            kind_hint="事实",
            reply_to_event_id=history_of(LAYER_TURNS)[-1].event_id,
            reason="该他说话",
        )
        provider.generate_turn(
            "停车位吵起来了",
            roles,
            [],
            history_of(LAYER_TURNS + 2),
            TurnSpec("builder", "创业实践者", "动态交锋", "事实"),
            plan=plan,
        )
        self.assertTrue(provider.prompts)
        expected_layer = layer_for(history_of(LAYER_TURNS + 2), "business")
        self.assertIn(f"这一层在聊：{expected_layer}", provider.prompts[-1])

    def test_moderator_is_told_not_to_close_the_whole_table_early(self):
        provider = PromptRecordingProvider(model="test-model")
        roles = [Role("builder", "创业实践者", "先算钱", "#fff", "提示")]
        early = TurnPlan(
            speaker_id="moderator",
            speaker_name="主持人",
            phase="状态整理",
            intent="synthesize",
            kind_hint="总结",
            reason="该收了",
            moderator=True,
            intervention_reason="有人在绕",
        )
        provider.generate_turn(
            "停车位吵起来了",
            roles,
            [],
            history_of(3),
            TurnSpec("moderator", "主持人", "状态整理", "总结"),
            plan=early,
        )
        self.assertIn("不要做整场总结", provider.prompts[-1])

        late = TurnPlan(
            speaker_id="moderator",
            speaker_name="主持人",
            phase="状态整理",
            intent="synthesize",
            kind_hint="总结",
            reason="该收了",
            moderator=True,
            intervention_reason="最后一层聊完了",
        )
        provider.generate_turn(
            "停车位吵起来了",
            roles,
            [],
            history_of(LAYER_TURNS * len(BUSINESS_LAYERS)),
            TurnSpec("moderator", "主持人", "状态整理", "总结"),
            plan=late,
        )
        self.assertNotIn("不要做整场总结", provider.prompts[-1])

    def test_event_parse_accepts_reactions_without_crashing(self):
        """回归：`_parse` 曾经引用不存在的 `roles`，事件模式每条发言都会 NameError。"""
        provider = PromptRecordingProvider(model="test-model")
        seats = [Role("qian", "乾明", "定调子", "#fff", "提示")]
        history = [Utterance("kun", "坤兰", "我先听着", ViewpointKind.FACT, "动态交锋")]
        utterance, _card = provider._parse(
            '{"content":"你这话我不服","kind":"风险","intent":"challenge",'
            '"confidence":"guess","reactions":[{"seat":"kun","delta":-1,"why":"这行被说没用"}]}',
            TurnSpec("qian", "乾明", "动态交锋", "风险"),
            history,
            event=True,
        )
        self.assertEqual(utterance.content, "你这话我不服")
        self.assertEqual(len(utterance.reactions), 1)
        self.assertEqual(utterance.reactions[0].seat_id, "kun")
        self.assertEqual(utterance.reactions[0].delta, -1)


if __name__ == "__main__":
    unittest.main()
