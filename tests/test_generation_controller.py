import shutil
import time
import unittest
from pathlib import Path

_IMPORT_ERROR = None
try:
    from PySide6.QtWidgets import QApplication as QCoreApplication
    from brainstorm.engine import MockDiscussionProvider
    from brainstorm.llm import ProviderFailure
    from brainstorm.models import DiscussionSession, OpportunityCard, Role, TrendSource, Utterance, ViewpointKind
    from brainstorm.news import NewsFetchResult
    from brainstorm.providers import IntegrationStatus
    from brainstorm.session_controller import SessionController
    from brainstorm.storage import SessionStore
    from brainstorm.turn_planner import detect_intervention
except ModuleNotFoundError as exc:  # The source test suite also runs without Qt installed.
    QCoreApplication = None
    _IMPORT_ERROR = exc


if QCoreApplication is not None:
    APP = QCoreApplication.instance() or QCoreApplication([])
    ROLE = Role("test", "测试角色", "测试", "#fff", "测试")
else:
    APP = None
    ROLE = None


class SlowProvider:
    def __init__(self):
        self.started = False
        self.cancel_seen = False

    def discuss(self, topic, roles, source_note="", *, cancel_event=None):
        self.started = True
        for _ in range(100):
            if cancel_event and cancel_event.is_set():
                self.cancel_seen = True
                raise ProviderFailure("cancelled", "模型生成已取消")
            time.sleep(0.002)
        return MockDiscussionProvider().discuss(topic, roles, source_note)


class FailingProvider:
    def discuss(self, topic, roles, source_note=""):
        raise ProviderFailure("request_failed", "真实模型请求失败；已回退到离线模拟")


class IgnoresCancelProvider:
    """A provider that returns after cancellation, exercising stale-result guards."""

    def __init__(self):
        self.calls = []

    def discuss(self, topic, roles, source_note="", *, cancel_event=None):
        self.calls.append(topic)
        time.sleep(0.08)
        return MockDiscussionProvider().discuss(topic, roles, source_note)


class ModelContinuationProvider:
    provider_name = "anthropic"

    def discuss(self, topic, roles, source_note=""):
        session = MockDiscussionProvider().discuss(topic, roles, source_note)
        session.effective_provider = "anthropic"
        session.provider_mode = "llm"
        return session

    def extend_batch(self, session, state, *, roles=(), cancel_event=None, on_partial=None):
        if cancel_event and cancel_event.is_set():
            raise ProviderFailure("cancelled", "模型生成已取消")
        role = next(iter(roles), ROLE)
        item = Utterance(role.id, role.name, "模型后台续批观点", ViewpointKind.ASSUMPTION, "动态交锋", session.utterances[-1].event_id, origin="model", intent="challenge")
        if on_partial:
            on_partial(role.name, item.content)
        return [item]


class LateModelContinuationProvider(ModelContinuationProvider):
    def extend_batch(self, session, state, *, roles=(), cancel_event=None, on_partial=None):
        time.sleep(0.08)
        return super().extend_batch(session, state, roles=roles, cancel_event=cancel_event, on_partial=on_partial)


class FastNewsProvider:
    def fetch_with_status(self, topic):
        return NewsFetchResult([], attempted=True, success=False, message="测试 RSS 完成")


def process_until(predicate, timeout=1500):
    deadline = time.time() + timeout / 1000
    while time.time() < deadline and not predicate():
        APP.processEvents()
        time.sleep(0.005)
    APP.processEvents()


class ProgressiveProvider:
    """Emits turns one at a time, the way the real model path does.

    The opening batch is 14 sequential requests, so waiting for all of them means
    staring at a status label for most of a minute.  This fake lets the tests
    check that the first turn reaches the screen long before the batch is done.
    """

    provider_name = "progressive-test"

    def __init__(self, turns: int = 4, delay: float = 0.06) -> None:
        self.turns = turns
        self.delay = delay
        self.finished = False

    def discuss(self, topic, roles, source_note="", *, sources=(), on_partial=None,
                cancel_event=None, on_turn=None):
        session = DiscussionSession(topic=topic, selected_role_ids=[role.id for role in roles])
        for index in range(self.turns):
            time.sleep(self.delay)
            utterance = Utterance("trend", "趋势分析师", f"第{index + 1}条观点",
                                  ViewpointKind.ASSUMPTION, "独立观点", origin="model")
            session.append_utterance(utterance)
            if on_turn is not None:
                on_turn(utterance, index + 1, self.turns)
        session.opportunity = OpportunityCard("测试机会", "测试用户")
        session.provider_mode = "llm"
        session.effective_provider = self.provider_name
        session.model_name = "progressive-model"
        self.finished = True
        return session


@unittest.skipIf(QCoreApplication is None, f"PySide6 unavailable: {_IMPORT_ERROR}")
class GenerationControllerTests(unittest.TestCase):
    def setUp(self):
        self.controllers = []
        self._history_tmp = Path(__file__).resolve().parent / ".tmp-controller-history"
        shutil.rmtree(self._history_tmp, ignore_errors=True)
        self._history_tmp.mkdir(parents=True, exist_ok=True)

    def track(self, controller):
        self.controllers.append(controller)
        return controller

    def tearDown(self):
        for controller in self.controllers:
            controller.shutdown()
        for _ in range(10):
            APP.processEvents()
            time.sleep(0.005)
        shutil.rmtree(self._history_tmp, ignore_errors=True)

    def test_provider_runs_and_emits_session(self):
        controller = self.track(SessionController(
            provider=MockDiscussionProvider(),
            store=SessionStore(self._history_tmp),
        ))
        sessions = []
        controller.session_ready.connect(sessions.append)
        controller.start("测试主题", [ROLE])
        process_until(lambda: bool(sessions))
        self.assertEqual(len(sessions), 1)

    def test_moderator_batch_records_intervention_reason(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend", "builder"])
        for index in range(6):
            session.append_utterance(Utterance(
                "trend" if index % 2 == 0 else "builder",
                "趋势分析师" if index % 2 == 0 else "创业实践者",
                f"第{index}条", ViewpointKind.ASSUMPTION, "动态交锋", origin="model",
            ))
        controller.playback.live = True
        controller.playback.start(session)
        controller._apply_batch([Utterance(
            "moderator", "主持人", "本阶段整理", ViewpointKind.SUMMARY, "状态整理",
            origin="model", intent="synthesize",
        )])
        expected = detect_intervention(session)[1]
        self.assertTrue(expected)
        self.assertEqual(session.discussion_state.host_intervention_reason, expected)

    def test_role_batch_clears_stale_intervention_reason(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend"])
        session.append_utterance(Utterance("trend", "趋势分析师", "开场", ViewpointKind.ASSUMPTION, "独立观点", origin="model"))
        session.discussion_state.host_intervention_reason = "上一次介入"
        controller.playback.live = True
        controller.playback.start(session)
        controller._apply_batch([Utterance("trend", "趋势分析师", "继续", ViewpointKind.ASSUMPTION, "动态交锋", origin="model")])
        self.assertEqual(session.discussion_state.host_intervention_reason, "")

    def test_batch_marks_repeated_role_content(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend"])
        session.append_utterance(Utterance("trend", "趋势分析师", "先做小范围试点", ViewpointKind.ASSUMPTION, "动态交锋", origin="model"))
        controller.playback.live = True
        controller.playback.start(session)
        controller._apply_batch([Utterance("trend", "趋势分析师", "先 做 小范围 试点", ViewpointKind.ASSUMPTION, "动态交锋", origin="model")])
        self.assertTrue(session.utterances[-1].duplicate)
        self.assertEqual(len(session.utterances), 2)

    def test_first_turn_is_shown_before_the_batch_finishes(self):
        provider = ProgressiveProvider(turns=6, delay=0.08)
        controller = self.track(SessionController(provider=provider, store=SessionStore(self._history_tmp)))
        ready = []
        controller.session_ready.connect(ready.append)
        controller.start("测试主题", [ROLE])
        process_until(lambda: bool(ready))
        self.assertFalse(provider.finished, "首批还没生成完，界面就该已经显示第一条")
        self.assertIsNotNone(controller.playback.current)
        self.assertEqual(controller.playback.current.content, "第1条观点")

    def test_background_turns_never_advance_the_reader(self):
        provider = ProgressiveProvider(turns=5, delay=0.06)
        controller = self.track(SessionController(provider=provider, store=SessionStore(self._history_tmp)))
        states = []
        controller.generation_state_changed.connect(states.append)
        controller.start("测试主题", [ROLE])
        process_until(lambda: controller.playback.current is not None)
        first = controller.playback.current.content
        process_until(lambda: provider.finished and "completed" in states)
        self.assertEqual(controller.playback.current.content, first,
                         "用户没点下一步，后台到货不能自动翻页")

    def test_new_turns_are_available_without_another_request(self):
        provider = ProgressiveProvider(turns=4, delay=0.05)
        controller = self.track(SessionController(provider=provider, store=SessionStore(self._history_tmp)))
        controller.start("测试主题", [ROLE])
        process_until(lambda: controller.playback.current is not None)
        process_until(lambda: len(controller.session.utterances) >= 4)
        controller.next_step()
        self.assertEqual(controller.playback.current.content, "第2条观点")

    def test_finished_metadata_lands_on_the_displayed_session(self):
        provider = ProgressiveProvider(turns=3, delay=0.03)
        controller = self.track(SessionController(
            provider=provider,
            store=SessionStore(self._history_tmp),
            integration_status=IntegrationStatus(discussion_provider="progressive-test", effective_mode="llm"),
        ))
        states = []
        controller.generation_state_changed.connect(states.append)
        controller.start("测试主题", [ROLE])
        process_until(lambda: "completed" in states)
        session = controller.session
        self.assertEqual(len(session.utterances), 3)
        self.assertIsNotNone(session.opportunity)
        self.assertEqual(session.opportunity.title, "测试机会")
        self.assertEqual(session.effective_provider, "progressive-test")
        self.assertEqual(session.model_name, "progressive-model")

    def test_generation_reports_progress(self):
        provider = ProgressiveProvider(turns=4, delay=0.03)
        controller = self.track(SessionController(provider=provider, store=SessionStore(self._history_tmp)))
        progress = []
        controller.generation_progress.connect(lambda done, total: progress.append((done, total)))
        states = []
        controller.generation_state_changed.connect(states.append)
        controller.start("测试主题", [ROLE])
        process_until(lambda: "completed" in states)
        self.assertEqual([done for done, _ in progress], [1, 2, 3, 4])
        self.assertEqual(progress[-1], (4, 4))

    def test_batch_applies_the_model_state_refresh(self):
        from brainstorm.orchestration import OrchestrationRefresh

        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend"])
        session.append_utterance(Utterance("trend", "趋势分析师", "开场", ViewpointKind.ASSUMPTION, "独立观点", origin="model"))
        controller.playback.live = True
        controller.playback.start(session)
        controller.provider.last_state_refresh = OrchestrationRefresh(
            consensus=("先做小范围试点",), conflicts=("需求强度未验证",), unresolved=("付费意愿",),
        )
        controller._apply_batch([Utterance("trend", "趋势分析师", "继续", ViewpointKind.ASSUMPTION, "动态交锋", origin="model")])
        self.assertEqual(session.discussion_state.consensus, ["先做小范围试点"])
        self.assertEqual(session.discussion_state.conflicts, ["需求强度未验证"])
        self.assertEqual(session.discussion_state.unresolved_questions, ["付费意愿"])
        self.assertIsNone(controller.provider.last_state_refresh)

    def test_cancel_sets_provider_cancel_event(self):
        provider = SlowProvider()
        controller = self.track(SessionController(provider=provider))
        states = []
        controller.generation_state_changed.connect(states.append)
        controller.start("测试主题", [ROLE])
        process_until(lambda: provider.started)
        controller.cancel_generation()
        process_until(lambda: provider.cancel_seen)
        self.assertTrue(provider.cancel_seen)
        self.assertIn("cancelled", states)

    def test_provider_failure_falls_back_to_mock(self):
        controller = self.track(SessionController(provider=FailingProvider()))
        sessions = []
        controller.session_ready.connect(sessions.append)
        controller.start("测试主题", [ROLE])
        process_until(lambda: bool(sessions))
        self.assertEqual(sessions[0].effective_provider, "mock")
        self.assertEqual(sessions[0].generation_status, "fallback")

    def test_cancel_invalidates_provider_result_before_it_returns(self):
        provider = IgnoresCancelProvider()
        controller = self.track(SessionController(provider=provider))
        sessions = []
        states = []
        controller.session_ready.connect(sessions.append)
        controller.generation_state_changed.connect(states.append)

        controller.start("旧主题", [ROLE])
        process_until(lambda: provider.calls == ["旧主题"])
        controller.cancel_generation()
        controller.start("新主题", [ROLE])
        process_until(lambda: len(sessions) == 1, timeout=2000)

        self.assertEqual(sessions[0].topic, "新主题")
        self.assertIn("cancelled", states)

    def test_news_worker_is_released_after_fetch(self):
        controller = self.track(SessionController(
            provider=MockDiscussionProvider(),
            news_provider=FastNewsProvider(),
            integration_status=IntegrationStatus(network_allowed=True, news_provider="rss"),
        ))
        sessions = []
        controller.session_ready.connect(sessions.append)
        controller.start("测试主题", [ROLE], fetch_news=True)
        process_until(lambda: bool(sessions))
        process_until(lambda: controller._news_thread is None)
        self.assertIsNone(controller._news_thread)
        self.assertIsNone(controller._news_worker)

    def test_rss_material_is_not_mislabeled_as_user_input(self):
        news = TrendSource("最新养老政策", "https://news.test/policy", "养老照护服务调整", source_type="rss")
        class News:
            def fetch_with_status(self, topic):
                return NewsFetchResult([news], attempted=True, matched=True)
        controller = self.track(SessionController(
            provider=MockDiscussionProvider(), news_provider=News(),
            store=SessionStore(self._history_tmp),
            integration_status=IntegrationStatus(network_allowed=True, news_provider="rss"),
        ))
        controller.start("社区养老", [ROLE], "我的访谈线索", fetch_news=True)
        process_until(lambda: controller.session is not None)
        session = controller.session
        self.assertIsNotNone(session)
        user_sources = [item for item in session.sources if item.source_type == "user"]
        self.assertEqual([item.note for item in user_sources], ["我的访谈线索"])
        self.assertEqual([item for item in session.sources if item.source_type == "rss"], [news])
        self.assertFalse(any("用户提供" in item.content and "最新养老政策" in item.content for item in session.utterances))

    def test_shutdown_cancels_generation_and_invalidates_results(self):
        provider = IgnoresCancelProvider()
        controller = self.track(SessionController(provider=provider))
        states = []
        controller.generation_state_changed.connect(states.append)
        controller.start("关闭主题", [ROLE])
        process_until(lambda: provider.calls == ["关闭主题"])
        controller.shutdown()
        process_until(lambda: controller._generation_thread is None, timeout=2000)
        self.assertIn("cancelled", states)

    def test_extend_discussion_appends_live_batch_until_user_finishes(self):
        controller = self.track(SessionController(
            provider=MockDiscussionProvider(),
            store=SessionStore(self._history_tmp),
        ))
        sessions = []
        completed = []
        controller.session_ready.connect(sessions.append)
        controller.completed.connect(completed.append)
        controller.start("延展主题", [ROLE])
        process_until(lambda: bool(sessions))
        initial_count = len(sessions[0].utterances)

        controller.extend_discussion()
        self.assertGreater(len(controller.session.utterances), initial_count)
        self.assertFalse(completed)

        controller.finish_discussion()
        process_until(lambda: bool(completed))
        self.assertEqual(completed[0].topic, "延展主题")

    def test_model_continuation_runs_in_background_and_is_saved(self):
        controller = self.track(SessionController(
            provider=ModelContinuationProvider(),
            store=SessionStore(self._history_tmp),
            integration_status=IntegrationStatus(effective_mode="llm", discussion_provider="anthropic"),
        ))
        controller.start("模型续批", [ROLE])
        process_until(lambda: controller.session is not None)
        initial_count = len(controller.session.utterances)
        controller.extend_discussion()
        process_until(lambda: len(controller.session.utterances) > initial_count)
        self.assertEqual(controller.session.utterances[-1].content, "模型后台续批观点")
        restored = SessionStore(self._history_tmp).list_sessions()[0]
        self.assertEqual(restored.utterances[-1].event_id, controller.session.utterances[-1].event_id)

    def test_start_invalidates_late_model_continuation(self):
        controller = self.track(SessionController(
            provider=LateModelContinuationProvider(),
            store=SessionStore(self._history_tmp),
            integration_status=IntegrationStatus(effective_mode="llm", discussion_provider="anthropic"),
        ))
        controller.start("旧主题", [ROLE])
        process_until(lambda: controller.session is not None)
        controller.extend_discussion()
        controller.start("新主题", [ROLE])
        process_until(lambda: controller.session is not None and controller.session.topic == "新主题", timeout=2000)
        time.sleep(0.12)
        APP.processEvents()
        self.assertEqual(controller.session.topic, "新主题")
        self.assertFalse(any(item.content == "模型后台续批观点" for item in controller.session.utterances))

    def test_interjection_is_consumed_before_next_batch(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        controller.start("无障碍服务", [ROLE])
        process_until(lambda: controller.session is not None)
        controller.add_interjection("优先讨论低视力用户")
        controller.extend_discussion()
        self.assertTrue(any("低视力用户" in item.content for item in controller.session.utterances))

    def test_interjection_uses_unique_event_sequence_without_rebuilding_existing_items(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        controller.start("序号测试", [ROLE])
        process_until(lambda: controller.session is not None)
        original = list(controller.session.utterances)
        controller.playback.index = 0
        controller.add_interjection("优先回应")
        events = controller.session.utterances
        self.assertIs(events[0], original[0])
        self.assertEqual(len({item.event_id for item in events}), len(events))
        self.assertEqual(len({item.sequence for item in events}), len(events))

    def test_each_added_batch_is_persisted(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        controller.start("保存测试", [ROLE])
        process_until(lambda: controller.session is not None)
        before = len(list(self._history_tmp.glob("*.json")))
        controller.extend_discussion()
        after = len(list(self._history_tmp.glob("*.json")))
        self.assertGreaterEqual(after, before)
        restored = SessionStore(self._history_tmp).list_sessions()[0]
        self.assertEqual(restored.utterances[-1].event_id, controller.session.utterances[-1].event_id)

    def test_automatic_playback_extends_at_batch_boundary(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        controller.start("自动讨论", [ROLE])
        process_until(lambda: controller.session is not None)
        initial = len(controller.session.utterances)
        controller.playback.index = initial - 1
        controller._next()
        self.assertGreater(len(controller.session.utterances), initial)
        self.assertEqual(controller.playback.index, initial)

    def test_default_discussion_waits_for_click_without_timer(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        controller.start("手动阅读", [ROLE])
        process_until(lambda: controller.session is not None)
        self.assertTrue(controller.manual_advance)
        self.assertFalse(controller.timer.isActive())
        index = controller.playback.index
        controller.next_step()
        self.assertEqual(controller.playback.index, index + 1)
        self.assertFalse(controller.timer.isActive())

    def test_advancing_one_turn_while_paused_preserves_pause(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        controller.manual_advance = False
        controller.start("暂停讨论", [ROLE])
        process_until(lambda: controller.session is not None)
        controller.pause_or_resume()
        index = controller.playback.index
        controller.next_step()
        self.assertEqual(controller.playback.index, index + 1)
        self.assertEqual(controller.playback.state.value, "paused")
        self.assertFalse(controller.timer.isActive())

    def test_manual_finish_keeps_generated_turns_and_user_input(self):
        # 以前提前结束会按播放游标把已生成的发言截掉，档案里却留着它们的立场，
        # 报告里就变成「共 1 条发言」却有 8 条立场。生成过的东西不能因为没轮到就删。
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        controller.start("提前结束", [ROLE])
        process_until(lambda: controller.session is not None)
        generated = len(controller.session.utterances)
        self.assertGreater(generated, 1)
        controller.add_interjection("优先考虑老年人")
        controller.finish_discussion()
        self.assertGreaterEqual(len(controller.session.utterances), generated + 1)
        # 插话插在「已经演到的那一条」之后，不是追加到末尾；只要它在、且只出现一次。
        self.assertEqual(
            [item.speaker_id for item in controller.session.utterances].count("user"), 1
        )
        seats = [item for item in controller.session.utterances if item.speaker_id not in {"user", "moderator"}]
        # 立场必须与留下来的发言对得上，不能多也不能少。
        self.assertEqual(sum(controller.session.opportunity.stance_counts.values()), len(seats))
        self.assertEqual(set(controller.session.discussion_state.role_stances), {item.speaker_id for item in seats})



if __name__ == "__main__":
    unittest.main()
