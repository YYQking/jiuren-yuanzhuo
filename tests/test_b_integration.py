import unittest
from datetime import datetime
from unittest.mock import patch

from brainstorm.models import TrendSource
from brainstorm.news import RssNewsProvider
from brainstorm.providers import IntegrationStatus, resolve_providers
from brainstorm.config import AppConfig
from brainstorm.llm import AnthropicDiscussionProvider, OpenAICompatibleDiscussionProvider, ProviderFailure, TurnSpec
from brainstorm.models import DiscussionSession, DiscussionState, Role, Utterance, ViewpointKind


class BIntegrationTests(unittest.TestCase):
    def test_environment_defaults_to_network_ready_rss_mode(self):
        with patch.dict("os.environ", {}, clear=True):
            config = AppConfig.from_environment()
        self.assertEqual(config.mode, "auto")
        self.assertTrue(config.allow_network)
        self.assertTrue(config.news_enabled)
        self.assertGreaterEqual(len(config.news_feed_urls), 4)

    def test_explicit_offline_environment_remains_a_hard_boundary(self):
        with patch.dict("os.environ", {"BRAINSTORM_MODE": "offline"}, clear=True):
            config = AppConfig.from_environment()
        self.assertEqual(config.mode, "offline")
        self.assertTrue(config.allow_network)
        self.assertTrue(config.news_enabled)
        _, _, status = resolve_providers(config)
        self.assertEqual(status.effective_mode, "offline")
        self.assertEqual(status.news_provider, "offline")

    def test_openai_compatible_provider_parses_chat_completion(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, _size):
                return '{"choices":[{"message":{"content":"{\\"content\\":\\"兼容接口观点\\",\\"kind\\":\\"假设\\"}"}}],"usage":{"prompt_tokens":3,"completion_tokens":4}}'.encode("utf-8")
        provider = OpenAICompatibleDiscussionProvider(api_key="key", model="test", base_url="https://example.test/v1")
        with patch("brainstorm.llm.urllib.request.urlopen", return_value=Response()):
            result = provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(result.utterance.content, "兼容接口观点")
        self.assertEqual(result.usage.requests, 1)
    def test_anthropic_discuss_assigns_event_metadata_to_initial_history(self):
        class Event:
            text = '{"content":"开场"}'
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])
        class Messages:
            def stream(self, **_): return Stream()
        class Client:
            messages = Messages()
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = provider.discuss("主题", [Role("r", "角色", "职责", "#fff", "提示")])
        self.assertTrue(session.utterances)
        self.assertEqual(session.utterances[0].event_id, "event-000000")
        self.assertEqual(session.utterances[0].sequence, 0)

    def test_incomplete_opportunity_card_does_not_discard_the_turn(self):
        spec = TurnSpec("moderator", "主持人", "阶段总结", "总结", final=True)
        payload = '{"content":"总结","kind":"总结","intent":"synthesize","opportunity":{"title":"方向"}}'
        utterance, opportunity = AnthropicDiscussionProvider._parse(payload, spec, [])
        self.assertEqual(utterance.content, "总结")
        self.assertIsNone(opportunity)

    def test_partial_opportunity_card_is_repaired_not_dropped(self):
        spec = TurnSpec("moderator", "主持人", "阶段总结", "总结", final=True)
        payload = (
            '{"content":"总结","kind":"总结","intent":"synthesize","opportunity":'
            '{"title":"窄场景机会","audience":"高频用户","support":["理由一",123],'
            '"risks":[],"next_steps":["访谈五人"]}}'
        )
        utterance, opportunity = AnthropicDiscussionProvider._parse(payload, spec, [])
        self.assertEqual(utterance.content, "总结")
        self.assertIsNotNone(opportunity)
        self.assertEqual(opportunity.title, "窄场景机会")
        self.assertEqual(opportunity.audience, "高频用户")
        self.assertEqual(opportunity.support, ["理由一"])
        self.assertEqual(opportunity.assumptions, [])
        self.assertEqual(opportunity.next_steps, ["访谈五人"])

    def test_missing_opportunity_card_is_not_an_error(self):
        spec = TurnSpec("moderator", "主持人", "阶段总结", "总结", final=True)
        payload = '{"content":"总结","kind":"总结","intent":"synthesize"}'
        utterance, opportunity = AnthropicDiscussionProvider._parse(payload, spec, [])
        self.assertEqual(utterance.content, "总结")
        self.assertIsNone(opportunity)

    def test_independent_opinions_are_generated_concurrently(self):
        import threading
        import time

        probe = {"active": 0, "max": 0, "calls": 0}
        lock = threading.Lock()

        class Event:
            text = '{"content":"观点"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **_):
                with lock:
                    probe["active"] += 1
                    probe["calls"] += 1
                    probe["max"] = max(probe["max"], probe["active"])
                time.sleep(0.05)
                with lock:
                    probe["active"] -= 1
                return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        roles = [Role(f"r{index}", f"角色{index}", "职责", "#fff", "提示") for index in range(9)]
        session = provider.discuss("主题", roles)

        self.assertEqual(len(session.utterances), 14)
        self.assertGreaterEqual(probe["max"], 2, "九个独立观点属于同一阶段，应当并发生成")
        # 并发之后仍然要按名册顺序落盘，不能变成谁先返回谁排前面
        self.assertEqual([item.speaker_name for item in session.utterances[1:10]], [role.name for role in roles])
        self.assertEqual(session.utterances[0].speaker_name, "主持人")
        self.assertEqual(session.utterances[-1].speaker_name, "主持人")

    def test_independent_opinions_do_not_see_each_other(self):
        prompts = []

        class Event:
            text = '{"content":"观点"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **kwargs):
                prompts.append(kwargs["messages"][0]["content"])
                return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        roles = [Role(f"r{index}", f"独特角色{index}", "职责", "#fff", "提示") for index in range(3)]
        provider.discuss("主题", roles)
        # 前 4 次请求 = 开场 + 三个独立观点；它们之间不应看到彼此的发言
        independent_prompts = prompts[1:4]
        for index, prompt in enumerate(independent_prompts):
            for other in range(3):
                if other == index:
                    continue
                self.assertNotIn(f"独特角色{other}: 观点", prompt)

    def test_hotspot_material_reaches_the_model_prompt(self):
        captured = []

        class Event:
            text = '{"content":"我回应这条线索"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **kwargs):
                captured.append(kwargs["messages"][0]["content"])
                return Stream()

        class Client:
            messages = Messages()

        note = ("来自社会热点雷达的 AI 回忆条目（时间：2025年1月 · 来源：来源不确定，均为模型自述，未核验）："
                "AI 换脸诈骗案频发引监管关注。摘要：多起冒充亲友的案子被曝光。"
                "该条目未核验，可能已经过时，只能当作讨论线索，不是已证实事实。")
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        provider.discuss("AI 换脸诈骗案频发引监管关注", [Role("r", "角色", "职责", "#fff", "提示")], note)
        prompt = captured[0]
        self.assertIn("AI 换脸诈骗案频发引监管关注", prompt)
        self.assertIn("2025年1月", prompt)
        # 来源标注必须一路带到提示词里，不能被当成已核验事实
        self.assertIn("未核验", prompt)

    def test_anthropic_parse_preserves_discussion_metadata(self):
        spec = TurnSpec("r", "角色", "动态交锋")
        prior = [Utterance("other", "另一角色", "原始观点", ViewpointKind.OPPORTUNITY, "首轮观点", event_id="event-000001", sequence=1)]
        payload = '{"content":"我改变了看法","kind":"机会","intent":"support","replies_to":"event-000001","stance_change":{"before":"保守","after":"先做小范围试点","reason":"被原始观点说服"}}'
        utterance, _ = AnthropicDiscussionProvider._parse(payload, spec, prior)
        self.assertEqual(utterance.intent, "support")
        self.assertEqual(utterance.replies_to, "event-000001")
        self.assertEqual(utterance.stance_change.after, "先做小范围试点")
        self.assertEqual(utterance.verification, "unverified")

    def test_unknown_kind_falls_back_to_the_kind_the_plan_asked_for(self):
        """A moderator summary must not be relabelled 假设 just because the model
        answered with a kind word we do not know."""
        spec = TurnSpec("moderator", "主持人", "阶段总结", "总结")
        utterance, _ = AnthropicDiscussionProvider._parse('{"content":"本轮归纳","kind":"总结性发言"}', spec, [])
        self.assertEqual(utterance.kind, ViewpointKind.SUMMARY)

    def test_unknown_kind_without_a_usable_hint_lands_on_assumption(self):
        spec = TurnSpec("r", "角色", "动态交锋", "模型乱写的类型")
        utterance, _ = AnthropicDiscussionProvider._parse('{"content":"我的看法","kind":"不存在"}', spec, [])
        self.assertEqual(utterance.kind, ViewpointKind.ASSUMPTION)

    def test_prompt_requests_intent_stance_and_event_ids(self):
        captured = []

        class Event:
            text = '{"content":"回应","intent":"challenge"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **kwargs):
                captured.append(kwargs["messages"][0]["content"])
                return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="数字服务", selected_role_ids=["r"])
        prior = session.append_utterance(Utterance("other", "另一角色", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model", intent="support"))
        provider.extend_batch(session, DiscussionState(), roles=[Role("r", "角色", "职责", "#fff", "提示")])
        # 第一次请求现在是编排调用，生成提示词要用它的 JSON 形状来定位
        prompt = next(item for item in captured if "stance_change" in item)
        # 提示词必须索要意图、立场变化，并把 event_id 交给模型
        self.assertIn("intent", prompt)
        self.assertIn("stance_change", prompt)
        self.assertIn(prior.event_id, prompt)
        self.assertIn("support", prompt)
        self.assertIn("challenge", prompt)
        # 立场变化必须写明仍然保留的条件或疑虑（协议 §2.3 的第四项）
        self.assertIn("仍然保留的条件", prompt)
        # 必须明确禁止重复前文
        self.assertIn("不得重复", prompt)
        # 必须给出篇幅上限，否则模型会写成长篇
        self.assertIn("200–350 字", prompt)

    def test_anthropic_parse_converts_speaker_reply_reference_to_event_id(self):
        spec = TurnSpec("r", "角色", "动态交锋")
        prior = [Utterance("other", "另一角色", "原始观点", ViewpointKind.OPPORTUNITY, "首轮观点", event_id="event-000001", sequence=1)]
        payload = '{"content":"回应","replies_to":"other","intent":"challenge"}'
        utterance, _ = AnthropicDiscussionProvider._parse(payload, spec, prior)
        self.assertEqual(utterance.replies_to, "event-000001")

    def test_speaker_reply_reference_resolves_to_latest_utterance(self):
        spec = TurnSpec("r", "角色", "动态交锋")
        prior = [
            Utterance("other", "另一角色", "第一次发言", ViewpointKind.OPPORTUNITY, "独立观点", event_id="event-000001", sequence=1),
            Utterance("other", "另一角色", "第二次发言", ViewpointKind.RISK, "动态交锋", event_id="event-000002", sequence=2),
        ]
        # 人名回指（提示词就是这样引导模型的）必须落到最新一条，而不是最早一条
        by_name, _ = AnthropicDiscussionProvider._parse(
            '{"content":"回应","replies_to":"另一角色","intent":"challenge"}', spec, prior)
        self.assertEqual(by_name.replies_to, "event-000002")
        # speaker_id 回指同样落到最新一条
        by_id, _ = AnthropicDiscussionProvider._parse(
            '{"content":"回应","replies_to":"other","intent":"challenge"}', spec, prior)
        self.assertEqual(by_id.replies_to, "event-000002")
        # event_id 精确回指不受"取最新"影响
        by_event, _ = AnthropicDiscussionProvider._parse(
            '{"content":"回应","replies_to":"event-000001","intent":"challenge"}', spec, prior)
        self.assertEqual(by_event.replies_to, "event-000001")
        # 前文不存在的引用一律置空，不能凭空指向
        unknown, _ = AnthropicDiscussionProvider._parse(
            '{"content":"回应","replies_to":"前文没有的人","intent":"challenge"}', spec, prior)
        self.assertIsNone(unknown.replies_to)

    def test_parse_strips_markdown_code_fence(self):
        spec = TurnSpec("r", "角色", "动态交锋")
        payload = '```json\n{"content":"围栏内的观点","kind":"机会","intent":"support"}\n```'
        utterance, _ = AnthropicDiscussionProvider._parse(payload, spec, [])
        self.assertEqual(utterance.content, "围栏内的观点")
        self.assertEqual(utterance.intent, "support")

    def test_extend_batch_picks_the_challenged_role(self):
        captured = []

        class Event:
            text = '{"content":"我回应质疑","intent":"challenge"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **kwargs):
                captured.append(kwargs["messages"][0]["content"])
                return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        session.append_utterance(Utterance("skeptic", "怀疑者", "没和现有替代方案比", ViewpointKind.RISK, "动态交锋",
                                          replies_to="event-000000", origin="model", intent="challenge"))
        roles = [
            Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
            Role("skeptic", "怀疑者", "寻找伪需求", "#dc2626", "主动寻找反例。"),
        ]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].speaker_id, "builder")
        self.assertIn("创业实践者", captured[0])
        self.assertIn("质疑尚未回应", captured[0])

    def test_extend_batch_inserts_moderator_when_intervention_triggers(self):
        class Event:
            text = '{"content":"本阶段整理","kind":"总结","intent":"synthesize"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **_): return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend", "builder"])
        for index in range(6):
            session.append_utterance(Utterance(
                "trend" if index % 2 == 0 else "builder",
                "趋势分析师" if index % 2 == 0 else "创业实践者",
                f"第{index}条", ViewpointKind.ASSUMPTION, "动态交锋", origin="model",
            ))
        roles = [
            Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化。"),
            Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
        ]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        self.assertEqual(added[0].speaker_id, "moderator")
        self.assertEqual(added[0].phase, "状态整理")

    def _orchestrated_provider(self, replies):
        """A fake client that answers each call with the next canned reply."""
        prompts = []

        class Event:
            def __init__(self, text): self.text = text

        class Stream:
            def __init__(self, text): self._text = text
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event(self._text)])

        class Messages:
            def __init__(self): self.calls = 0
            def stream(self, **kwargs):
                index = min(self.calls, len(replies) - 1)
                self.calls += 1
                prompts.append(kwargs["messages"][0]["content"])
                return Stream(replies[index])

        class Client:
            def __init__(self): self.messages = Messages()

        client = Client()
        provider = AnthropicDiscussionProvider(client=client, model="test-model")
        return provider, client, prompts

    ORCHESTRATION_OK = (
        '{"key_question":"第一批用户为什么不用现成的？","speaker_id":"skeptic",'
        '"must_answer":"说明第一批用户为什么今天就要解决","avoid":["重复讲趋势"],'
        '"intervene":false,"intervention_reason":"",'
        '"consensus":["先做小范围试点"],"conflicts":["需求强度未验证"],"unresolved":["付费意愿"]}'
    )
    REVIEW_OK = '{"passed":true,"repeats":"","avoided":"","fabricated":""}'

    def _two_role_session(self):
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        return session

    def _two_roles(self):
        return [
            Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
            Role("skeptic", "怀疑者", "寻找伪需求", "#dc2626", "主动寻找反例。"),
        ]

    def test_orchestrator_decision_overrides_the_local_plan(self):
        provider, client, prompts = self._orchestrated_provider([
            self.ORCHESTRATION_OK,
            '{"content":"我来说明付费动机","kind":"风险","intent":"challenge"}',
            self.REVIEW_OK,
        ])
        added = provider.extend_batch(self._two_role_session(), DiscussionState(), roles=self._two_roles())
        self.assertEqual(added[0].speaker_id, "skeptic")
        self.assertEqual(added[0].speaker_name, "怀疑者")
        self.assertIsNotNone(provider.last_state_refresh)
        self.assertEqual(provider.last_state_refresh.consensus, ("先做小范围试点",))
        # 生成提示词必须带上"必须回答"和"必须避免"
        self.assertIn("第一批用户为什么今天就要解决", prompts[1])
        self.assertIn("重复讲趋势", prompts[1])
        self.assertEqual(client.messages.calls, 3)

    def test_orchestration_failure_falls_back_to_the_local_plan(self):
        # 假客户端对每次请求都返回发言人内容，编排结果无法解析，必须退回本地计划
        provider, _, _ = self._orchestrated_provider([
            '{"content":"我回应质疑","intent":"challenge"}',
        ])
        session = self._two_role_session()
        session.append_utterance(Utterance("skeptic", "怀疑者", "没和替代方案比", ViewpointKind.RISK, "动态交锋",
                                          replies_to="event-000000", origin="model", intent="challenge"))
        added = provider.extend_batch(session, DiscussionState(), roles=self._two_roles())
        self.assertEqual(added[0].speaker_id, "builder")
        self.assertIsNone(provider.last_state_refresh)

    def test_failing_review_triggers_exactly_one_rewrite(self):
        provider, client, prompts = self._orchestrated_provider([
            self.ORCHESTRATION_OK,
            '{"content":"第一版发言","kind":"机会","intent":"support"}',
            '{"passed":false,"repeats":"重复了 event-000000","avoided":"回避了付费动机","fabricated":""}',
            '{"content":"第二版发言","kind":"机会","intent":"support"}',
        ])
        added = provider.extend_batch(self._two_role_session(), DiscussionState(), roles=self._two_roles())
        self.assertEqual(added[0].content, "第二版发言")
        self.assertEqual(client.messages.calls, 4)
        # 回炉请求必须把具体批评带回去
        self.assertIn("重复了 event-000000", prompts[3])
        self.assertIn("回避了付费动机", prompts[3])

    def test_review_failure_keeps_the_turn_and_does_not_retry(self):
        provider, client, _ = self._orchestrated_provider([
            self.ORCHESTRATION_OK,
            '{"content":"唯一一版","kind":"机会","intent":"support"}',
            '这不是 JSON',
        ])
        added = provider.extend_batch(self._two_role_session(), DiscussionState(), roles=self._two_roles())
        self.assertEqual(added[0].content, "唯一一版")
        self.assertEqual(client.messages.calls, 3)
        self.assertIsNone(provider.last_review)

    def test_malformed_json_is_retried_once_with_the_error(self):
        prompts = []

        class Event:
            def __init__(self, text): self.text = text

        class Stream:
            def __init__(self, text): self._text = text
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event(self._text)])

        class Messages:
            def __init__(self): self.calls = 0
            def stream(self, **kwargs):
                self.calls += 1
                prompts.append(kwargs["messages"][0]["content"])
                # 第一次返回坏 JSON，第二次返回合法内容
                return Stream('{"content": ' if self.calls == 1 else '{"content":"修正后的观点","kind":"机会"}')

        class Client:
            def __init__(self): self.messages = Messages()

        client = Client()
        provider = AnthropicDiscussionProvider(client=client, model="test-model")
        result = provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(result.utterance.content, "修正后的观点")
        self.assertEqual(client.messages.calls, 2)
        # 第二次请求必须把错误回灌给模型
        self.assertIn("不是合法 JSON", prompts[1])

    def test_malformed_json_twice_still_falls_back_honestly(self):
        class Event:
            text = '{"content": '

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **_): return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        with self.assertRaises(ProviderFailure) as ctx:
            provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(ctx.exception.code, "malformed_json")

    def test_anthropic_extend_batch_prompt_contains_state_and_user_instruction(self):
        captured = []
        class Event:
            text = '{"content":"围绕无障碍体验继续","kind":"待验证","intent":"question"}'
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])
        class Messages:
            def stream(self, **kwargs):
                captured.append(kwargs["messages"][0]["content"])
                return Stream()
        class Client:
            messages = Messages()
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="数字服务", selected_role_ids=["r"])
        session.append_utterance(Utterance("user", "用户", "优先讨论无障碍体验", ViewpointKind.ASSUMPTION, "用户插话", origin="user", intent="user_instruction"))
        added = provider.extend_batch(session, DiscussionState(pending_user_interjection="优先讨论无障碍体验"), roles=[Role("r", "角色", "职责", "#fff", "提示")])
        self.assertEqual(len(added), 1)
        self.assertIn("优先讨论无障碍体验", captured[0])
        self.assertIn("未核验", captured[0])

    def test_model_prompt_preserves_news_link_date_and_source_type(self):
        captured = []
        class Event:
            text = '{"content":"需要验证政策影响"}'
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])
        class Messages:
            def stream(self, **kwargs):
                captured.append(kwargs["messages"][0]["content"])
                return Stream()
        class Client:
            messages = Messages()
        news = TrendSource("养老政策", "https://news.test/policy", "政策摘要", source_type="rss", published_at=datetime(2026, 10, 11))
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = provider.discuss("社区养老", [Role("r", "角色", "职责", "#fff", "提示")], sources=[news])
        self.assertEqual(session.sources, [news])
        self.assertIn(news.url, captured[0])
        self.assertIn("2026-10-11", captured[0])
        self.assertIn("rss", captured[0])
        self.assertIn("资料", captured[0])
    def test_rss_fetch_supports_atom_and_deduplicates(self):
        payload = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>AI city</title><link href="/a"/><summary>summary</summary><published>Tue, 01 Jan 2030 00:00:00 GMT</published></entry><entry><title>AI city</title><link href="https://feed.test/a"/></entry></feed>'''
        result = RssNewsProvider(["https://feed.test/rss"], transport=lambda _url, _timeout: payload).fetch_with_status("AI")
        self.assertTrue(result.success)
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(result.sources[0].source_type, "rss")
        self.assertIsInstance(result.sources[0].published_at, datetime)

    def test_rss_fetch_matches_relevant_topic_terms_and_returns_latest_first(self):
        payload = '''<rss><channel>
        <item><title>Older养老服务</title><description>社区服务</description><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
        <item><title>最新社区养老政策</title><description>养老服务正在调整</description><pubDate>Mon, 01 Jan 2030 00:00:00 GMT</pubDate></item>
        </channel></rss>'''.encode()
        result = RssNewsProvider(["https://feed.test/rss"], transport=lambda _url, _timeout: payload).fetch_with_status("社区养老")
        self.assertTrue(result.matched)
        self.assertEqual(result.sources[0].title, "最新社区养老政策")

    def test_rss_fetch_matches_chinese_topic_terms_without_exact_phrase(self):
        payload = '''<rss><channel>
        <item><title>社区照护新政</title><description>养老服务正在调整</description><pubDate>Mon, 01 Jan 2030 00:00:00 GMT</pubDate></item>
        </channel></rss>'''.encode()
        result = RssNewsProvider(["https://feed.test/rss"], transport=lambda _url, _timeout: payload).fetch_with_status("社区养老服务")
        self.assertTrue(result.matched)
        self.assertEqual(result.sources[0].title, "社区照护新政")

    def test_rss_fetch_sorts_all_feeds_before_limiting(self):
        older = '''<rss><channel><item><title>AI old</title><description>AI</description><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item></channel></rss>'''.encode()
        newer = '''<rss><channel><item><title>AI new</title><description>AI</description><pubDate>Mon, 01 Jan 2030 00:00:00 GMT</pubDate></item></channel></rss>'''.encode()
        def transport(url, _timeout):
            return newer if url.endswith("new") else older
        result = RssNewsProvider(["https://feed.test/old", "https://feed.test/new"], max_items=1, transport=transport).fetch_with_status("AI")
        self.assertEqual([item.title for item in result.sources], ["AI new"])

    def test_rss_failure_is_explicit(self):
        result = RssNewsProvider(["https://feed.test/rss"], transport=lambda *_: (_ for _ in ()).throw(TimeoutError())).fetch_with_status("x")
        self.assertFalse(result.success)
        self.assertTrue(result.attempted)
        self.assertFalse(result.matched)
        self.assertFalse(result.partial_failure)
        self.assertIn("失败", result.message)

    def test_rss_request_without_match_is_successful_but_unmatched(self):
        payload = '''<rss><channel><item><title>unrelated</title><description>other topic</description></item></channel></rss>'''.encode()
        result = RssNewsProvider(["https://feed.test/rss"], transport=lambda *_: payload).fetch_with_status("目标主题")
        self.assertTrue(result.attempted)
        self.assertTrue(result.success)
        self.assertFalse(result.matched)
        self.assertFalse(result.partial_failure)
        self.assertIn("未找到匹配", result.message)

    def test_rss_partial_failure_is_distinct_from_no_match(self):
        payload = '''<rss><channel><item><title>AI city</title><description>AI city summary</description><link>https://feed.test/a</link></item></channel></rss>'''.encode()
        def transport(url, _timeout):
            if url.endswith("bad"):
                raise TimeoutError()
            return payload
        result = RssNewsProvider(["https://feed.test/good", "https://feed.test/bad"], transport=transport).fetch_with_status("AI")
        self.assertTrue(result.attempted)
        self.assertFalse(result.success)
        self.assertTrue(result.matched)
        self.assertTrue(result.partial_failure)
        self.assertIn("部分", result.message)

    def test_rss_missing_link_does_not_use_feed_url_as_story_url(self):
        payload = '''<rss><channel><item><title>AI city</title><description>AI city summary</description></item></channel></rss>'''.encode()
        result = RssNewsProvider(["https://feed.test/rss"], transport=lambda *_: payload).fetch_with_status("AI")
        self.assertEqual(result.sources[0].url, "")

    def test_resolver_llm_is_honest_fallback(self):
        _, _, status = resolve_providers(AppConfig(mode="llm"))
        self.assertEqual(status.discussion_provider, "mock")
        self.assertIn("回退", status.fallback_reason)

    def test_resolver_reports_missing_model(self):
        _, _, status = resolve_providers(AppConfig(mode="llm", allow_network=True, allow_llm=True, llm_api_key="key", llm_model=""))
        self.assertIn("未配置模型", status.fallback_reason)

    def test_status_compatibility_alias(self):
        self.assertEqual(IntegrationStatus().mode, "offline")

    def test_rss_atom_iso_time_alternate_link_and_summary_match(self):
        payload = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Unrelated title</title><link rel="self" href="https://feed.test/self"/><link rel="alternate" href="/story"/><summary>AI city changes daily life</summary><updated>2030-01-01T12:30:00Z</updated></entry></feed>'''
        result = RssNewsProvider(["https://feed.test/rss"], transport=lambda _url, _timeout: payload).fetch_with_status("AI city")
        self.assertTrue(result.success)
        self.assertEqual(result.sources[0].url, "https://feed.test/story")
        self.assertEqual(result.sources[0].published_at.year, 2030)

    def test_anthropic_streaming_fake_collects_partial_and_usage(self):
        class Delta:
            def __init__(self, text): self.text = text
        class Usage:
            input_tokens = 11
            output_tokens = 7
        class Event:
            def __init__(self, text): self.delta = Delta(text); self.usage = Usage()
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event('{"content":"观点'), Event('内容","kind":"机会"}')])
        class Messages:
            def stream(self, **_): return Stream()
        class Client:
            messages = Messages()
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        partials = []
        result = provider.generate_turn("主题", [Role("r", "角色", "职责", "#fff", "提示")], [], [], TurnSpec("r", "角色", "独立观点"), on_partial=partials.append)
        self.assertEqual(result.utterance.kind, ViewpointKind.OPPORTUNITY)
        self.assertEqual(partials, ['{"content":"观点', '{"content":"观点内容","kind":"机会"}'])
        self.assertEqual(result.usage.input_tokens, 11)
        self.assertEqual(result.usage.output_tokens, 7)

    def test_anthropic_empty_stream_is_safe_failure(self):
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([])
        class Messages:
            def stream(self, **_): return Stream()
        class Client:
            messages = Messages()
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model", max_retries=0)
        with self.assertRaises(ProviderFailure) as ctx:
            provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(ctx.exception.code, "empty_response")

    def test_anthropic_whitespace_stream_is_empty_response(self):
        class Event:
            text = "   "
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])
        class Messages:
            def stream(self, **_): return Stream()
        class Client:
            messages = Messages()
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model", max_retries=0)
        with self.assertRaises(ProviderFailure) as ctx:
            provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(ctx.exception.code, "empty_response")

    def test_anthropic_reads_nested_message_usage(self):
        class Delta:
            text = '{"content":"完成"}'
        class Usage:
            input_tokens = 13
            output_tokens = 5
        class Message:
            usage = Usage()
        class Event:
            delta = Delta()
            message = Message()
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])
        class Messages:
            def stream(self, **_): return Stream()
        class Client:
            messages = Messages()
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        result = provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(result.usage.input_tokens, 13)
        self.assertEqual(result.usage.output_tokens, 5)

    def test_anthropic_turn_remains_marked_as_unverified_simulation(self):
        class Event:
            text = '{"content":"模型观点","kind":"假设"}'
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])
        class Messages:
            def stream(self, **_): return Stream()
        class Client:
            messages = Messages()
        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        result = provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertTrue(result.utterance.simulated)

    def test_anthropic_retries_transient_stream_failure(self):
        class Delta:
            text = '{"content":"重试后成功"}'
        class Event:
            delta = Delta()
        class Stream:
            def __init__(self, fail): self.fail = fail
            def __enter__(self):
                if self.fail: raise TimeoutError("temporary")
                return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])
        class Messages:
            def __init__(self): self.calls = 0
            def stream(self, **_):
                self.calls += 1
                return Stream(self.calls == 1)
        class Client:
            def __init__(self): self.messages = Messages()
        client = Client()
        provider = AnthropicDiscussionProvider(client=client, model="test-model", max_retries=1)
        result = provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(result.utterance.content, "重试后成功")
        self.assertEqual(client.messages.calls, 2)


if __name__ == "__main__":
    unittest.main()
