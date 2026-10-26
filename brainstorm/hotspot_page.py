"""Readable social news cards and a cancellable, nonblocking refresh."""

from __future__ import annotations

from datetime import datetime
from queue import Empty, Queue
from threading import Event, Thread
from urllib.parse import urlsplit

from PySide6.QtCore import QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .hotspots import HotspotFetchResult, HotspotItem, HotspotProvider
from .qt_theme import COLORS, title_font


def _plain_label(text: str, *, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def _stamp(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M") if value else "时间未提供"


class HotspotCard(QFrame):
    discuss_requested = Signal()

    def __init__(self, item: HotspotItem, parent=None) -> None:
        super().__init__(parent)
        self.item = item
        self.setObjectName("hotspotCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        tags = QHBoxLayout()
        region = "国内" if item.region == "domestic" else "国际"
        tag = _plain_label(f"{region}  ·  {item.category}")
        tag.setStyleSheet(f"color: {COLORS['gold']}; font-size: 12px;")
        tags.addWidget(tag, 1)
        kind = "AI 回忆" if item.source_kind == "model" else "真实新闻源"
        trust = QLabel(f"{kind} · " + ("缓存 · 未核验" if item.cached else "未核验"))
        trust.setStyleSheet(f"color: {COLORS['muted']}; font-size: 11px;")
        tags.addWidget(trust)
        layout.addLayout(tags)

        self.headline = _plain_label(item.title)
        self.headline.setStyleSheet(f"color: {COLORS['cream']}; font-size: 17px; font-weight: 600;")
        self.headline.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.headline)
        published = f"发布于 {_stamp(item.published_at)}" if item.published_at else f"获取于 {_stamp(item.fetched_at)}"
        provenance_lines = [item.publisher or "来源未提供"]
        if item.time_note:
            provenance_lines.append(item.time_note)
        provenance_lines.append(published)
        self.provenance = _plain_label("\n".join(provenance_lines))
        self.provenance.setStyleSheet(f"color: {COLORS['muted']}; font-size: 12px;")
        layout.addWidget(self.provenance)

        summary = item.summary or "该条目没有摘要。"
        short_summary = summary if len(summary) <= 160 else summary[:160].rstrip() + "…"
        self.summary = _plain_label(short_summary)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary.setStyleSheet(f"color: {COLORS['muted']}; font-size: 13px;")
        self.summary.setToolTip(summary)
        layout.addWidget(self.summary)
        layout.addStretch()

        actions = QHBoxLayout()
        if item.coverage_count > 1:
            coverage = _plain_label(f"{item.coverage_count} 个订阅源收录")
            coverage.setStyleSheet(f"color: {COLORS['dim']}; font-size: 11px;")
            coverage.setToolTip("重复收录不代表独立核验，也不代表真实热度。")
            actions.addWidget(coverage, 1)
        else:
            actions.addStretch()
        if len(summary) > 160:
            expand = QPushButton("完整摘要")
            expand.setCheckable(True)
            expand.clicked.connect(lambda checked: self.summary.setText(summary if checked else short_summary))
            actions.addWidget(expand)
        self.open_button = QPushButton("打开原文 ↗")
        try:
            parsed = urlsplit(item.url)
        except ValueError:
            parsed = None
        self.open_button.setEnabled(bool(parsed and parsed.scheme in {"https", "http"} and parsed.netloc))
        self.open_button.setToolTip(item.url or "来源未提供原文链接")
        self.open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(item.url)))
        actions.addWidget(self.open_button)

        self.discuss_button = QPushButton("就这个话题讨论")
        self.discuss_button.setToolTip("以这条热点为题开一场讨论（进入事件讨论分区）；条目本身会作为讨论线索，并保留它的来源与时间标注。")
        self.discuss_button.clicked.connect(self.discuss_requested)
        actions.addWidget(self.discuss_button)
        layout.addLayout(actions)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        """Clicking anywhere on the card starts the discussion.

        Child buttons consume their own clicks, so 打开原文 and the expand button
        keep working without also firing this.
        """
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.discuss_requested.emit()
        super().mouseReleaseEvent(event)


class HotspotSection(QWidget):
    discuss_requested = Signal(object)

    def __init__(self, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        header = QHBoxLayout()
        label = QLabel(title)
        label.setFont(title_font(19))
        label.setStyleSheet(f"color: {COLORS['gold_bright']};")
        header.addWidget(label)
        self.count = QLabel("0 条")
        self.count.setStyleSheet(f"color: {COLORS['dim']};")
        header.addWidget(self.count)
        header.addStretch()
        layout.addLayout(header)
        self.description = _plain_label(subtitle)
        self.description.setStyleSheet(f"color: {COLORS['muted']}; font-size: 12px;")
        layout.addWidget(self.description)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(14)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        layout.addLayout(self.grid)
        self.cards: list[HotspotCard] = []
        self.empty_label: QLabel | None = None
        self._columns = 2

    def set_items(self, items: list[HotspotItem], empty_message: str) -> None:
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.cards = [HotspotCard(item, self) for item in items]
        for card in self.cards:
            card.discuss_requested.connect(lambda item=card.item: self.discuss_requested.emit(item))
        self.empty_label = None
        self.count.setText(f"{len(items)} 条")
        if self.cards:
            self._arrange()
        else:
            label = _plain_label(empty_message)
            self.empty_label = label
            label.setStyleSheet(f"color: {COLORS['dim']}; background: {COLORS['panel']}; border-radius: 12px; padding: 20px;")
            self.grid.addWidget(label, 0, 0, 1, self._columns)

    def _arrange(self) -> None:
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // self._columns, index % self._columns)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        columns = 1 if self.width() < 790 else 2
        if columns != self._columns:
            self._columns = columns
            self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
            for card in self.cards:
                self.grid.removeWidget(card)
            self._arrange()
            if self.empty_label is not None:
                self.grid.removeWidget(self.empty_label)
                self.grid.addWidget(self.empty_label, 0, 0, 1, columns)


class HotspotPage(QWidget):
    back_requested = Signal()
    window_mode_requested = Signal()
    exit_requested = Signal()
    discuss_requested = Signal(str, str)

    def __init__(self, provider: HotspotProvider | None = None, network_allowed: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.network_allowed = network_allowed
        self.topic = ""
        self._region = "all"
        self._category = "all"
        self._last_result = HotspotFetchResult([])
        self.visible_items: list[HotspotItem] = []
        self._refresh_token = 0
        self._cancel_event: Event | None = None
        self._pending: Queue | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(80)
        self._poll_timer.timeout.connect(self._poll_result)
        self._build()
        self._render()

    def _build(self) -> None:
        self.setObjectName("hotspotPage")
        root = QVBoxLayout(self)
        root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        root.setContentsMargins(44, 28, 44, 26)
        root.setSpacing(15)
        header = QHBoxLayout()
        self.title_label = QLabel("社会热点雷达")
        self.title_label.setFont(title_font(28))
        self.title_label.setStyleSheet(f"color: {COLORS['gold_bright']};")
        header.addWidget(self.title_label)
        header.addStretch()
        back = QPushButton("返回大厅")
        back.clicked.connect(self._back)
        header.addWidget(back)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setProperty("primary", True)
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        window = QPushButton("窗口化")
        window.clicked.connect(self.window_mode_requested)
        header.addWidget(window)
        exit_button = QPushButton("退出")
        exit_button.clicked.connect(self.exit_requested)
        header.addWidget(exit_button)
        root.addLayout(header)
        self.topic_label = _plain_label("当前未指定主题 · 可先浏览社会热点")
        self.topic_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 14px;")
        root.addWidget(self.topic_label)
        self.status_label = _plain_label("打开时更新一次，也可手动刷新。")
        self.status_label.setObjectName("hotspotStatus")
        root.addWidget(self.status_label)

        self.region_buttons = self._filter_row(root, "范围", (("all", "全部"), ("domestic", "国内"), ("international", "国际")), self._set_region)
        self.category_buttons = self._filter_row(root, "分类", tuple((value, value) for value in ("all", "社会", "科技", "商业", "政策", "科学")), self._set_category)
        self.category_buttons["all"].setText("全部")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 8, 10, 0)
        body.setSpacing(28)
        self.related_section = HotspotSection("与你的主题相关", "主题检索和标题、摘要匹配的新闻线索。")
        self.general_section = HotspotSection("社会热点广场", "公开新闻按发布时间展示；国内、国际尽量均衡，不代表热度排名。")
        for section in (self.related_section, self.general_section):
            section.discuss_requested.connect(self._request_discussion)
        body.addWidget(self.related_section)
        body.addWidget(self.general_section)
        body.addStretch()
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)
        footer = _plain_label("条目由模型凭记忆生成，没有实时新闻能力；每条的时间与来源均为模型自述、未核验，可能已经过时。桌上观点由角色模板或已配置的模型生成，与热点条目分别展示。")
        footer.setStyleSheet(f"color: {COLORS['dim']}; font-size: 11px;")
        root.addWidget(footer)

    def _filter_row(self, root, label, choices, callback) -> dict[str, QPushButton]:
        row = QHBoxLayout()
        row.setSpacing(8)
        caption = QLabel(label)
        caption.setFixedWidth(38)
        caption.setStyleSheet(f"color: {COLORS['dim']};")
        row.addWidget(caption)
        buttons = {}
        for key, text in choices:
            button = QPushButton(text)
            button.setObjectName("hotspotFilter")
            button.setCheckable(True)
            button.setChecked(key == "all")
            button.clicked.connect(lambda _checked=False, value=key: callback(value))
            row.addWidget(button)
            buttons[key] = button
        row.addStretch()
        root.addLayout(row)
        return buttons

    @staticmethod
    def _discussion_material(item: HotspotItem) -> tuple[str, str]:
        """Topic plus the material block handed to the roundtable.

        The provenance travels with the item: an AI-recalled entry must never
        arrive in the discussion looking like a verified news report, because the
        roles would then treat a two-year-old memory as today's fact.
        """
        topic = item.title.strip()
        if item.source_kind == "model":
            where = f"来自社会热点雷达的 AI 回忆条目（{item.time_note or '模型自述时间未提供'}）"
        else:
            stamp = _stamp(item.published_at) if item.published_at else "发布时间未提供"
            where = f"来自社会热点雷达的真实新闻源条目（{item.publisher or '来源未标明'}，发布于 {stamp}）"
        note = (
            f"{where}：{topic}。"
            f"摘要：{item.summary or '无'}。"
            "该条目未核验，可能已经过时，只能当作讨论线索，不是已证实事实。"
        )
        return topic, note

    def _request_discussion(self, item: HotspotItem) -> None:
        topic, note = self._discussion_material(item)
        if not topic:
            return
        self.discuss_requested.emit(topic, note)

    def set_context(self, topic: str, auto_refresh: bool = True) -> None:
        self.cancel_refresh()
        self.topic = topic.strip()
        self.topic_label.setText(f"当前主题：{self.topic}" if self.topic else "当前未指定主题 · 可先浏览社会热点")
        if self.provider is not None:
            self.set_result(self.provider.cached(self.topic))
        else:
            self.set_result(HotspotFetchResult([]))
        if auto_refresh:
            self.refresh()

    def refresh(self) -> None:
        if self._cancel_event is not None:
            return
        if not self.network_allowed or self.provider is None:
            cached = self.provider.cached(self.topic) if self.provider else self._last_result
            self.set_result(HotspotFetchResult(cached.items, success=True, used_cache=bool(cached.items),
                message="当前为离线模式，未联网；仅显示已有缓存" if cached.items else "当前为离线模式，未联网；暂无缓存",
                last_success_at=cached.last_success_at))
            return
        self._refresh_token += 1
        token = self._refresh_token
        self._cancel_event = cancelled = Event()
        self._pending = pending = Queue()
        provider, topic = self.provider, self.topic
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("刷新中…")
        self.status_label.setText("正在更新热点……已有内容保留。")

        def fetch():
            try:
                result = provider.fetch(topic, cancel_event=cancelled)
            except Exception:
                cached = provider.cached(topic)
                result = HotspotFetchResult(cached.items, attempted=True, success=False,
                    used_cache=bool(cached.items), message="刷新失败，请稍后重试" + ("；已保留缓存" if cached.items else ""),
                    last_success_at=cached.last_success_at)
            if not cancelled.is_set():
                pending.put((token, result))

        # Only immutable context and a Python queue are captured by the daemon;
        # it never touches a QWidget or owns a Qt thread during window teardown.
        Thread(target=fetch, daemon=True).start()
        self._poll_timer.start()

    def _poll_result(self) -> None:
        if self._pending is None:
            return
        try:
            token, result = self._pending.get_nowait()
        except Empty:
            return
        if token != self._refresh_token:
            return
        self._poll_timer.stop()
        self._cancel_event = None
        self._pending = None
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("刷新")
        self.set_result(result)

    def cancel_refresh(self) -> None:
        self._refresh_token += 1
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_event = None
        self._pending = None
        self._poll_timer.stop()
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("刷新")

    def set_result(self, result: HotspotFetchResult) -> None:
        self._last_result = result
        message = result.message
        if result.used_cache and result.last_success_at:
            message += f" · 上次成功更新于 {_stamp(result.last_success_at)}"
        elif result.fetched_at:
            message += f" · 更新于 {_stamp(result.fetched_at)}"
        self.status_label.setText(message)
        color = COLORS["gold"] if result.used_cache or not result.success else COLORS["muted"]
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._render()

    def _set_region(self, region: str) -> None:
        self._region = region
        for key, button in self.region_buttons.items():
            button.setChecked(key == region)
        self._render()

    def _set_category(self, category: str) -> None:
        self._category = category
        for key, button in self.category_buttons.items():
            button.setChecked(key == category)
        self._render()

    def _render(self) -> None:
        items = self._last_result.display_items(self._region)
        self.visible_items = [item for item in items if self._category == "all" or item.category == self._category]
        related = [item for item in self.visible_items if item.related]
        general = [item for item in self.visible_items if not item.related]
        related_empty = "先在大厅输入一个主题，再打开雷达查找相关线索。" if not self.topic else "当前筛选下没有直接相关的新闻，可切换范围或刷新。"
        self.related_section.set_items(related, related_empty)
        self.general_section.set_items(general, "当前筛选下暂无新闻。可切换范围或刷新；失败时保留已有缓存。")

    def _back(self) -> None:
        self.cancel_refresh()
        self.back_requested.emit()

    def hideEvent(self, event) -> None:
        self.cancel_refresh()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.cancel_refresh()
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 1100 or self.height() < 700
        self.layout().setContentsMargins(*((22, 16, 22, 18) if compact else (44, 28, 44, 26)))
        self.title_label.setFont(title_font(21 if compact else 28))

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(600, 400)
