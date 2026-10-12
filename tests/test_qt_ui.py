import os
import unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_IMPORT_ERROR = None
try:
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtCore import QCoreApplication, QEvent
    from brainstorm.engine import MockDiscussionProvider
    from brainstorm.models import DiscussionSession, Utterance, ViewpointKind
    from brainstorm.qt_app import LobbyPage, MainWindow, RoundtablePage, SummaryPage
    from brainstorm.roles import DEFAULT_ROLES
    from brainstorm.session_controller import SessionController
    from brainstorm.storage import SessionStore
    from brainstorm.qt_theme import app_stylesheet
except ModuleNotFoundError as exc:
    QApplication = None
    _IMPORT_ERROR = exc


APP = QApplication.instance() if QApplication is not None else None
if QApplication is not None:
    APP = APP or QApplication([])
    windows_font = Path("C:/Windows/Fonts/msyh.ttc")
    if windows_font.is_file():
        QFontDatabase.addApplicationFont(str(windows_font))


@unittest.skipIf(QApplication is None, f"PySide6 unavailable: {_IMPORT_ERROR}")
class QtUiTests(unittest.TestCase):
    def setUp(self):
        self._existing_widgets = set(APP.topLevelWidgets())
        self.history_dir = Path("tests/.tmp-qt-history")
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.store = SessionStore(self.history_dir)
        self.controller = SessionController(provider=MockDiscussionProvider(), store=self.store)

    def tearDown(self):
        self.controller.shutdown()
        self.controller.timer.stop()
        for widget in set(APP.topLevelWidgets()) - self._existing_widgets:
            widget.close()
            widget.deleteLater()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        for child in self.history_dir.glob("*"):
            child.unlink()
        self.history_dir.rmdir()

    def test_lobby_has_explicit_window_and_exit_controls(self):
        lobby = LobbyPage(self.store)
        labels = {button.text() for button in lobby.findChildren(QPushButton)}
        self.assertIn("退出", labels)
        self.assertTrue(any("窗口" in label or "全屏" in label for label in labels))

    def test_lobby_exposes_social_hotspots_page(self):
        lobby = LobbyPage(self.store)
        labels = {button.text() for button in lobby.findChildren(QPushButton)}
        self.assertIn("社会热点雷达", labels)

    def test_lobby_exposes_ai_settings(self):
        lobby = LobbyPage(self.store)
        self.assertIn("AI 设置", {button.text() for button in lobby.findChildren(QPushButton)})

    def test_generation_progress_never_displays_raw_model_payload(self):
        page = RoundtablePage(self.controller)
        page._generation_partial("行业从业者", '{"content":"观点","kind":"风险"}')
        self.assertNotIn('"content"', page.bubble.text())
        self.assertIn("正在准备", page.bubble.text())

    def test_manual_generation_keeps_current_argument_visible(self):
        page = RoundtablePage(self.controller)
        page.bubble.setText("我正在阅读的观点")
        page._generation_partial("行业从业者", '{"content":"下一条"}')
        self.assertEqual(page.bubble.text(), "我正在阅读的观点")

    def test_current_utterance_is_displayed_once(self):
        """The bottom row is a hint for the interjection box, not a second copy."""
        page = RoundtablePage(self.controller)
        utterance = Utterance("industry", "行业从业者", "这是一条完整的观点内容", ViewpointKind.RISK, "独立观点")
        page._show_current_text(utterance)
        self.assertIn("这是一条完整的观点内容", page.bubble.text())
        self.assertNotIn("这是一条完整的观点内容", page.interjection_hint.text())
        self.assertIn("插话", page.interjection_hint.text())
        self.assertEqual(page.interjection_hint.toolTip(), "")

    def test_viewpoint_kind_is_explained_in_plain_language(self):
        page = RoundtablePage(self.controller)
        page._show_current_text(Utterance("moderator", "主持人", "阶段归纳内容", ViewpointKind.ASSUMPTION, "阶段总结"))
        self.assertIn("假设", page.bubble.text())
        self.assertIn("还没证据的推测", page.bubble.text())
        self.assertIn("这一条是什么类型", page.bubble.toolTip())
        for kind in ("机会", "风险", "待验证", "总结"):
            self.assertIn(kind, page.bubble.toolTip())

    def test_status_message_does_not_keep_the_kind_legend(self):
        """The legend explains a turn; it must not linger over status text."""
        page = RoundtablePage(self.controller)
        page._show_current_text(Utterance("industry", "行业从业者", "观点", ViewpointKind.RISK, "独立观点"))
        self.assertIn("这一条是什么类型", page.bubble.toolTip())
        page._generation_state("running")
        self.assertEqual(page.bubble.toolTip(), "")
        self.assertIn("正在准备", page.bubble.text())

    def test_hotspot_page_separates_related_and_general_and_filters_region(self):
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage
        from datetime import datetime, timezone

        page = HotspotPage(network_allowed=False)
        page.set_context("社区养老")
        page.set_result(HotspotFetchResult([
            HotspotItem("相关国内政策", publisher="国内媒体", region="domestic", category="政策", related=True,
                        published_at=datetime(2026, 10, 11, tzinfo=timezone.utc)),
            HotspotItem("国际科技动态", publisher="国际媒体", region="international", category="科技"),
        ], message="已加载缓存", used_cache=True, last_success_at=datetime(2026, 10, 10, tzinfo=timezone.utc)))

        related_text = "\n".join(label.text() for label in page.related_section.findChildren(type(page.status_label)))
        general_text = "\n".join(label.text() for label in page.general_section.findChildren(type(page.status_label)))
        self.assertIn("相关国内政策", related_text)
        self.assertIn("国际科技动态", general_text)
        self.assertIn("缓存", page.status_label.text())
        page.region_buttons["domestic"].click()
        self.assertEqual([item.title for item in page.visible_items], ["相关国内政策"])

    def test_hotspots_filters_categories_and_exposes_original_links(self):
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage
        page = HotspotPage(network_allowed=False)
        page.set_result(HotspotFetchResult([
            HotspotItem("科技消息", url="https://example.test/a", category="科技"),
            HotspotItem("政策消息", category="政策"),
        ]))
        page.category_buttons["科技"].click()
        self.assertEqual([item.title for item in page.visible_items], ["科技消息"])
        labels = {button.text() for button in page.general_section.findChildren(QPushButton)}
        self.assertIn("打开原文 ↗", labels)

    def test_hotspot_page_labels_real_news_and_ai_recall_separately(self):
        from datetime import datetime, timezone
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage

        page = HotspotPage(network_allowed=False)
        page.set_result(HotspotFetchResult([
            HotspotItem("真实新闻标题", publisher="中新网", region="domestic", category="社会",
                        source_kind="rss", published_at=datetime(2026, 10, 12, tzinfo=timezone.utc)),
            HotspotItem("模型回忆标题", publisher="模型生成", region="international", category="社会",
                        source_kind="model",
                        time_note="时间：2024年8月 · 来源：路透社（均为模型自述，未核验）"),
        ], message="真实新闻 1 条（未核验）；AI 回忆 1 条（时间与来源为模型自述，可能过时）"))

        text = "\n".join(label.text() for label in page.general_section.findChildren(type(page.status_label)))
        self.assertIn("真实新闻标题", text)
        self.assertIn("模型回忆标题", text)
        self.assertIn("真实新闻源", text)
        self.assertIn("AI 回忆", text)
        # 每条都要能看到时间与来源
        self.assertIn("2024年8月", text)
        self.assertIn("路透社", text)
        self.assertIn("模型自述", page.status_label.text())

    def test_offline_hotspot_page_reads_cache_without_fetching(self):
        from brainstorm.hotspots import HotspotCache, HotspotItem, HotspotProvider
        from brainstorm.qt_app import HotspotPage
        from datetime import datetime, timezone
        cache = HotspotCache(self.history_dir / "hotspots-cache.json")
        cache.save([HotspotItem("旧的政策消息", related=True)], datetime(2026, 10, 10, tzinfo=timezone.utc), topic="养老")
        reads = []
        provider = HotspotProvider([], cache=cache, transport=lambda url, _timeout: reads.append(url))
        page = HotspotPage(provider, network_allowed=False)
        page.set_context("养老")
        self.assertEqual(reads, [])
        self.assertEqual([item.title for item in page.visible_items], ["旧的政策消息"])
        self.assertIn("缓存", page.status_label.text())
        self.assertIn("离线", page.status_label.text())

    def test_hotspot_refresh_is_async_and_can_be_cancelled_without_late_result(self):
        import time
        from threading import Event
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage

        entered = Event()
        released = Event()
        class SlowProvider:
            def cached(self, topic):
                return HotspotFetchResult([])
            def fetch(self, topic, *, cancel_event=None):
                entered.set()
                released.wait(2)
                return HotspotFetchResult([HotspotItem(topic)])
        page = HotspotPage(SlowProvider())
        page.set_context("旧主题")
        self.assertTrue(entered.wait(1))
        start = time.monotonic()
        page.cancel_refresh()
        self.assertLess(time.monotonic() - start, 0.3)
        page.set_context("新主题", auto_refresh=False)
        released.set()
        for _ in range(20):
            APP.processEvents()
            time.sleep(0.01)
        self.assertEqual(page.visible_items, [])
        self.assertTrue(page.refresh_button.isEnabled())

    def test_main_window_registers_hotspot_page(self):
        with patch("brainstorm.qt_app.SessionStore", return_value=self.store):
            window = MainWindow()
        try:
            self.assertIsNotNone(window.hotspots)
            self.assertGreaterEqual(window.stack.count(), 4)
        finally:
            window.close()

    def test_hotspot_card_can_start_a_discussion_and_keeps_its_provenance(self):
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage

        page = HotspotPage(network_allowed=False)
        requests = []
        page.discuss_requested.connect(lambda topic, note: requests.append((topic, note)))
        page.set_result(HotspotFetchResult([
            HotspotItem("AI 换脸诈骗案频发引监管关注", publisher="模型生成", region="domestic", category="科技",
                        source_kind="model", summary="多起冒充亲友的案子被曝光。",
                        time_note="时间：2025年1月 · 来源：来源不确定（均为模型自述，未核验）"),
        ]))

        page.general_section.cards[0].discuss_button.click()

        self.assertEqual(len(requests), 1)
        topic, note = requests[0]
        self.assertEqual(topic, "AI 换脸诈骗案频发引监管关注")
        # 来源与时间必须跟着材料走，否则角色会把旧回忆当成今天的新闻
        self.assertIn("AI 回忆", note)
        self.assertIn("2025年1月", note)
        self.assertIn("未核验", note)
        self.assertIn("多起冒充亲友的案子被曝光。", note)

    def test_real_news_card_keeps_outlet_and_publication_time(self):
        from datetime import datetime, timezone
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage

        page = HotspotPage(network_allowed=False)
        requests = []
        page.discuss_requested.connect(lambda topic, note: requests.append((topic, note)))
        page.set_result(HotspotFetchResult([
            HotspotItem("某地出台新政策", publisher="中新网", region="domestic", category="社会",
                        source_kind="rss", published_at=datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)),
        ]))
        page.general_section.cards[0].discuss_button.click()
        _, note = requests[0]
        self.assertIn("真实新闻源", note)
        self.assertIn("中新网", note)
        self.assertIn("2026-10-12", note)

    def test_clicking_the_card_body_also_starts_the_discussion(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage

        page = HotspotPage(network_allowed=False)
        requests = []
        page.discuss_requested.connect(lambda topic, note: requests.append(topic))
        page.set_result(HotspotFetchResult([HotspotItem("点卡片也能开讨论")]))
        card = page.general_section.cards[0]
        event = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(5, 5), QPointF(5, 5),
                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        card.mouseReleaseEvent(event)
        self.assertEqual(requests, ["点卡片也能开讨论"])

    def test_main_window_starts_a_discussion_from_a_hotspot_card(self):
        with patch("brainstorm.qt_app.SessionStore", return_value=self.store):
            window = MainWindow()
        try:
            started = []
            window._start = lambda topic, roles, note, fetch_news=False: started.append((topic, roles, note, fetch_news))
            window._discuss_hotspot("某热点事件", "来自社会热点雷达的 AI 回忆条目：某热点事件。")
            self.assertEqual(len(started), 1)
            topic, roles, note, fetch_news = started[0]
            self.assertEqual(topic, "某热点事件")
            self.assertIn("AI 回忆", note)
            self.assertTrue(roles, "没有勾选角色时应当回退到全部九个，而不是开一场空圆桌")
            self.assertFalse(fetch_news)
            self.assertEqual(window.lobby.topic.text(), "某热点事件")
        finally:
            window.close()

    def test_main_window_keeps_cache_provider_in_offline_mode(self):
        with patch.dict("os.environ", {"BRAINSTORM_MODE": "offline"}, clear=True), patch("brainstorm.qt_app.SessionStore", return_value=self.store):
            window = MainWindow()
        try:
            self.assertIsNotNone(window.hotspots.provider)
            self.assertFalse(window.hotspots.network_allowed)
        finally:
            window.close()

    def test_hotspots_uses_current_lobby_topic_instead_of_previous_discussion(self):
        with patch("brainstorm.qt_app.SessionStore", return_value=self.store):
            window = MainWindow()
        try:
            window.roundtable.session = MockDiscussionProvider().discuss("旧主题", DEFAULT_ROLES)
            window.lobby.topic.setText("新主题")
            with patch.object(window.hotspots, "set_context") as context:
                window._show_hotspots()
                context.assert_called_once_with("新主题", auto_refresh=True)
        finally:
            window.close()

    def test_malformed_news_link_disables_action_without_breaking_page(self):
        from brainstorm.hotspots import HotspotFetchResult, HotspotItem
        from brainstorm.qt_app import HotspotPage
        page = HotspotPage(network_allowed=False)
        page.set_result(HotspotFetchResult([HotspotItem("坏链接", url="https://[invalid")]))
        self.assertEqual([item.title for item in page.visible_items], ["坏链接"])
        self.assertFalse(page.general_section.cards[0].open_button.isEnabled())

    def test_lobby_defaults_to_fetching_news_and_badge_tracks_checkbox(self):
        with patch.dict("os.environ", {}, clear=True):
            lobby = LobbyPage(self.store)
        self.assertTrue(lobby.rss_opt_in.isEnabled())
        self.assertTrue(lobby.rss_opt_in.isChecked())
        self.assertIn("联网", lobby.source_badge.text())
        lobby.rss_opt_in.setChecked(False)
        self.assertIn("不获取", lobby.source_badge.text())

    def test_offline_lobby_disables_news_despite_default_feeds(self):
        with patch.dict("os.environ", {"BRAINSTORM_MODE": "offline"}, clear=True):
            lobby = LobbyPage(self.store)
        self.assertFalse(lobby.rss_opt_in.isEnabled())
        self.assertFalse(lobby.rss_opt_in.isChecked())
        self.assertIn("离线", lobby.network_note.text())

    def test_evidence_explains_template_viewpoints_and_keeps_news_separate(self):
        from brainstorm.models import TrendSource
        session = MockDiscussionProvider().discuss("社区养老", DEFAULT_ROLES)
        session.sources = [TrendSource("养老政策", source_type="rss")]
        page = RoundtablePage(self.controller)
        page.load_session(session)
        evidence = page.evidence.toPlainText()
        self.assertIn("模板", evidence)
        self.assertIn("九个独立", evidence)
        self.assertIn("养老政策", evidence)
        self.assertIn("新闻原文", evidence)

    def test_summary_page_shows_complete_opportunity_sections(self):
        session = MockDiscussionProvider().discuss("测试主题", DEFAULT_ROLES)
        summary = SummaryPage(session)
        rendered = "\n".join(label.text() for label in summary.findChildren(type(summary.title_label)))
        self.assertIn("机会档案", rendered)
        self.assertIn("待验证假设", rendered)
        self.assertIn("下一步行动", rendered)
        self.assertIn("观点分布", rendered)

    def test_roundtable_shows_live_discussion_state(self):
        session = MockDiscussionProvider().discuss("社区养老", DEFAULT_ROLES)
        page = RoundtablePage(self.controller)
        page.load_session(session)
        label = page.findChild(type(page.phase_label), "discussionStateLabel")
        self.assertIsNotNone(label)
        self.assertIn("共识", label.text())

    def test_summary_page_shows_unresolved_conflicts_and_stance_changes(self):
        session = MockDiscussionProvider().discuss("社区养老", DEFAULT_ROLES)
        MockDiscussionProvider().extend(session, 1)
        page = SummaryPage(session)
        text = "\n".join(label.text() for label in page.findChildren(type(page.title_label)))
        self.assertIn("未解决分歧", text)
        self.assertIn("立场轨迹", text)

    def test_roundtable_has_manual_finish_action(self):
        page = RoundtablePage(self.controller)
        labels = {button.text() for button in page.findChildren(QPushButton)}
        self.assertIn("结束并总结", labels)

    def test_roundtable_fits_standard_desktop_width(self):
        APP.setStyleSheet(app_stylesheet())
        page = RoundtablePage(self.controller)
        session = MockDiscussionProvider().discuss("社区里的银发人群如何更容易使用数字服务？", DEFAULT_ROLES)
        self.controller.load(session)
        page.resize(1366, 768)
        page.show()
        APP.processEvents()
        actual = page.width()
        actual_height = page.height()
        page.close()
        self.assertLessEqual(actual, 1366)
        self.assertLessEqual(actual_height, 768)

    def test_roundtable_fits_compact_scaled_window(self):
        APP.setStyleSheet(app_stylesheet())
        page = RoundtablePage(self.controller)
        session = MockDiscussionProvider().discuss("小屏幕主题", DEFAULT_ROLES)
        self.controller.load(session)
        page.resize(1024, 640)
        page.show()
        APP.processEvents()
        actual = page.size()
        page.close()
        self.assertLessEqual(actual.width(), 1024)
        self.assertLessEqual(actual.height(), 640)

    def test_early_finish_opens_summary_with_empty_viewpoint_lists(self):
        page = RoundtablePage(self.controller)
        self.controller.manual_advance = True
        session = MockDiscussionProvider().discuss("提前结束主题", DEFAULT_ROLES)
        self.controller.playback.start(session)
        self.controller.session_ready.emit(session)
        self.controller._emit_current()
        opened = []
        page.summary_requested.connect(opened.append)
        self.controller.finish_discussion()
        self.assertEqual(opened, [session])
        self.assertIn("讨论已结束", page.bubble.text())

    def test_transcript_and_summary_identify_mixed_content(self):
        page = RoundtablePage(self.controller)
        session = MockDiscussionProvider().discuss("混合来源", DEFAULT_ROLES)
        session.effective_provider = "anthropic"
        session.utterances[1] = replace(session.utterances[1], origin="model")
        self.controller.load(session)
        self.assertIn("模型生成", page.transcript.toPlainText())
        self.assertIn("离线模拟", page.transcript.toPlainText())
        summary = SummaryPage(session)
        self.assertIn("模型生成 + 离线模拟", summary.summary_meta.text())

    def test_live_transcript_shows_reply_target_and_intervention_reason(self):
        page = RoundtablePage(self.controller)
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        session.append_utterance(Utterance("skeptic", "怀疑者", "没和替代方案比", ViewpointKind.RISK, "动态交锋",
                                          replies_to="event-000000", origin="model", intent="challenge"))
        self.controller.load(session)
        page._utterance(session.utterances[1], 1, 2)
        self.assertIn("回应 创业实践者", page.transcript.toPlainText())

        session.discussion_state.host_intervention_reason = "发言集中在少数角色，讨论冷场"
        moderator = session.append_utterance(Utterance(
            "moderator", "主持人", "本阶段整理", ViewpointKind.SUMMARY, "状态整理", origin="model", intent="synthesize",
        ))
        page._utterance(moderator, 2, 3)
        self.assertIn("介入原因：发言集中在少数角色，讨论冷场", page.transcript.toPlainText())

    def test_history_transcript_shows_reply_target_and_intent(self):
        page = RoundtablePage(self.controller)
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        session.append_utterance(Utterance("skeptic", "怀疑者", "没和替代方案比", ViewpointKind.RISK, "动态交锋",
                                          replies_to="event-000000", origin="model", intent="challenge"))
        self.controller.load(session)
        text = page.transcript.toPlainText()
        self.assertIn("回应 创业实践者", text)
        self.assertIn("challenge", text)

    def test_interjection_is_recorded_once_at_the_time_it_happens(self):
        page = RoundtablePage(self.controller)
        self.controller.manual_advance = True
        session = MockDiscussionProvider().discuss("插话顺序", DEFAULT_ROLES)
        next_role_utterance = session.utterances[1]
        self.controller.playback.start(session)
        self.controller.session_ready.emit(session)
        self.controller._emit_current()

        self.controller.add_interjection("请讨论无障碍体验")
        self.assertEqual(session.utterances[1].speaker_id, "user")
        self.assertEqual(self.controller.playback.current.speaker_id, "user")
        self.assertEqual(page.transcript.toPlainText().count("请讨论无障碍体验"), 1)

        self.controller.next_step()
        self.assertIs(self.controller.playback.current, next_role_utterance)
        self.assertEqual(page.transcript.toPlainText().count("请讨论无障碍体验"), 1)
        self.controller.finish_discussion()
        self.assertEqual([item.speaker_id for item in session.utterances], ["moderator", "user", next_role_utterance.speaker_id])

    def test_history_opens_summary_without_starting_discussion(self):
        session = MockDiscussionProvider().discuss("历史主题", DEFAULT_ROLES)
        original = list(session.utterances)
        with patch("brainstorm.qt_app.SessionStore", return_value=self.store):
            window = MainWindow()
        try:
            window._open_history(session)
            self.assertIs(window.stack.currentWidget(), window.summary)
            self.assertFalse(window.controller.timer.isActive())
            self.assertEqual(session.utterances, original)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
