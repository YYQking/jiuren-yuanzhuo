"""PySide6 application shell for the immersive roundtable."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QLayout,
)

from .audio import AudioController
from .ai_settings import AISettingsDialog, AISettingsStore
from .export import export_json, export_markdown
from .config import AppConfig
from .models import DiscussionSession, Role, Utterance, ViewpointKind
from .hotspot_page import HotspotPage
from .hotspots import HotspotCache, HotspotProvider, default_hotspot_feeds
from .model_hotspots import HybridHotspotProvider, ModelHotspotProvider
from .providers import resolve_providers
from .qt_theme import COLORS, app_stylesheet, title_font
from .roles import DEFAULT_ROLES, ROLES_BY_MODE, SECTION_TEXT, default_roles_for, face_label
from .roundtable import RoundtableCanvas
from .session_controller import SessionController
from .storage import SessionStore


def avatar_pixmap(role_id: str, size: int) -> QPixmap:
    """把头像 SVG 画成圆形位图。

    Qt 的 SVG 渲染器不认 clipPath，直接显示会是一个方块色块；
    所以在外面套一层圆形裁剪，顺带按 2x 出图避免糊。
    """

    ratio = 2
    side = max(8, int(size)) * ratio
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    root = (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    )
    renderer = QSvgRenderer(str(root / "assets" / "avatars" / f"{role_id}.svg"))
    if not renderer.isValid():
        return pixmap
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    circle = QPainterPath()
    circle.addEllipse(0.0, 0.0, float(side), float(side))
    painter.setClipPath(circle)
    renderer.render(painter, QRectF(0.0, 0.0, float(side), float(side)))
    painter.end()
    pixmap.setDevicePixelRatio(float(ratio))
    return pixmap


# 所以在发言卡片上直接用一句人话解释，而不是让人去猜或去翻说明。
KIND_IN_PLAIN_WORDS = {
    ViewpointKind.FACT.value: "已经确认的情况",
    ViewpointKind.ASSUMPTION.value: "还没证据的推测",
    ViewpointKind.OPPORTUNITY.value: "值得做的方向",
    ViewpointKind.RISK.value: "担心会出问题的地方",
    ViewpointKind.VALIDATION.value: "需要去证实的",
    ViewpointKind.SUMMARY.value: "阶段性归纳",
}


def kind_label(kind: ViewpointKind | str) -> str:
    """Render one viewpoint kind as `假设（还没证据的推测）`."""
    value = kind.value if isinstance(kind, ViewpointKind) else str(kind)
    gloss = KIND_IN_PLAIN_WORDS.get(value)
    return f"{value}（{gloss}）" if gloss else value


def kind_legend() -> str:
    lines = ["这一条是什么类型（由模型自己判断，可能不准）："]
    lines.extend(f"· {value}：{gloss}" for value, gloss in KIND_IN_PLAIN_WORDS.items())
    return "\n".join(lines)


def card_name(name: str) -> str:
    """长名字在牌面上断成两行，别让最后孤零零掉一个字下来。"""
    if " / " in name:
        return name.replace(" / ", "\n")
    if len(name) > 6:
        return name[:4] + "\n" + name[4:]
    return name


def role_tooltip(role: Role) -> str:
    """Hover text for a seat: business seats show their lens, event seats both faces."""
    yang = getattr(role, "yang", "")
    yin = getattr(role, "yin", "")
    if not yang or not yin:
        return role.duty
    trigram = getattr(role, "trigram", "")
    return f"{role.name}（{trigram}）\n阳面：{yang}\n阴面：{yin}\n\n{role.duty}"


class RoleChip(QPushButton):
    def __init__(self, role: Role, parent=None) -> None:
        super().__init__(parent)
        self.role = role
        self.setObjectName("roleChip")
        self.setCheckable(True)
        self.setAccessibleName(f"{role.name}，{role.duty}")
        self.setToolTip(role_tooltip(role))
        self.setMinimumHeight(72)
        self.setMinimumWidth(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
        icon = QIcon(str(root / "assets" / "avatars" / f"{role.id}.svg"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        portrait = QLabel()
        portrait.setFixedSize(40, 40)
        rounded = avatar_pixmap(role.id, 40)
        if not rounded.isNull():
            portrait.setPixmap(rounded)
        elif not icon.isNull():
            portrait.setPixmap(icon.pixmap(QSize(40, 40)))
        else:
            portrait.setText(role.name[:1])
        portrait.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(portrait)
        text = QVBoxLayout()
        text.setSpacing(3)
        name = QLabel(role.name)
        name.setStyleSheet("font-size: 14px; font-weight: 600;")
        name.setWordWrap(True)
        trigram = getattr(role, "trigram", "")
        duty = QLabel(f"{trigram} · {role.duty}" if trigram else role.duty)
        duty.setStyleSheet(f"font-size: 11px; color: {COLORS['muted']};")
        duty.setWordWrap(True)
        for label in (name, duty):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            text.addWidget(label)
        layout.addLayout(text, 1)
        self.marker = QLabel("●")
        self.marker.setStyleSheet(f"color: {COLORS['gold']};")
        self.marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.marker)
        self.toggled.connect(lambda checked: self.marker.setText("●" if checked else "○"))
        self.setChecked(True)


class FeltTable(QWidget):
    """赌桌的台面：只画那块绿绒椭圆、铜边和头顶打下来的光。卡片是它的子控件。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(26, 14, self.width() - 52, self.height() - 40)
        if rect.width() < 40 or rect.height() < 40:
            painter.end()
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 110))
        painter.drawEllipse(rect.translated(0, 14))

        felt = QRadialGradient(rect.center(), rect.width() * 0.62)
        felt.setColorAt(0.0, QColor("#35634c"))
        felt.setColorAt(0.55, QColor("#22422f"))
        felt.setColorAt(1.0, QColor("#13241a"))
        painter.setBrush(QBrush(felt))
        painter.drawEllipse(rect)

        lamp = QRadialGradient(rect.center().x(), rect.top() + rect.height() * 0.20,
                               rect.width() * 0.34)
        lamp.setColorAt(0.0, QColor(240, 217, 166, 44))
        lamp.setColorAt(1.0, QColor(240, 217, 166, 0))
        painter.setBrush(QBrush(lamp))
        painter.drawEllipse(rect)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(201, 164, 92, 130), 2))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor(201, 164, 92, 58), 1))
        painter.drawEllipse(rect.adjusted(10, 8, -10, -8))
        painter.end()


class SeatCard(QPushButton):
    """一张座位牌：上半是头像，下面是名字和这一位是干什么的。

    勾上 = 在桌上，按掉 = 牌翻过去、不上桌。
    """

    CARD_WIDTH = 118
    CARD_HEIGHT = 196

    def __init__(self, role: Role, parent=None) -> None:
        super().__init__(parent)
        self.role = role
        self.setObjectName("seatCard")
        self.setCheckable(True)
        self.setChecked(True)
        self.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(role_tooltip(role))
        self.setAccessibleName(f"{role.name}，{role.duty}")
        self._scale = 1.0
        self.setProperty("down", False)

        root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
        icon = QIcon(str(root / "assets" / "avatars" / f"{role.id}.svg"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 12, 9, 9)
        layout.setSpacing(3)
        layout.addStretch(1)

        portrait = QLabel()
        portrait.setFixedSize(72, 72)
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rounded = avatar_pixmap(role.id, 72)
        if not rounded.isNull():
            portrait.setPixmap(rounded)
        elif not icon.isNull():
            portrait.setPixmap(icon.pixmap(QSize(72, 72)))
        else:
            portrait.setText(role.name[:1])
            portrait.setStyleSheet("font-size: 26px; color: #2b2417;")
        portrait.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(portrait, 0, Qt.AlignmentFlag.AlignHCenter)

        self.name_label = QLabel(card_name(role.name))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.name_label.setStyleSheet(
            "font-family: 'Songti SC', 'SimSun', serif; font-size: 15px; color: #2b2417;"
        )
        layout.addWidget(self.name_label)

        trigram = getattr(role, "trigram", "")
        self.tag_label = QLabel(f"{trigram} · {role.duty}" if trigram else role.duty)
        self.tag_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        self.tag_label.setWordWrap(True)
        self.tag_label.setFixedHeight(40)
        self.tag_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.tag_label.setStyleSheet("font-size: 9px; color: #7d6c50;")
        layout.addWidget(self.tag_label)
        layout.addStretch(1)

        self.mark = QLabel("阳")
        self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mark.setFixedSize(22, 17)
        self.mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.mark.setStyleSheet(
            "font-size: 9px; color: #f6ecd8; background: #96302c; border-radius: 3px;"
        )
        mark_row = QHBoxLayout()
        mark_row.setContentsMargins(0, 0, 0, 0)
        mark_row.addStretch(1)
        mark_row.addWidget(self.mark)
        layout.addLayout(mark_row)

        # 牌还没发的时候盖一张牌背：中间压一个「九」字
        self.back = QLabel("九", self)
        self.back.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.back.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.back.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #4a3a28, stop:0.5 #2a2118, stop:1 #3d3021);"
            " border: 1px solid #7a6136; border-radius: 10px;"
            " font-family: 'Songti SC', 'SimSun', serif; font-size: 26px;"
            " color: #caa96a;"
        )
        self.back.setGeometry(0, 0, self.CARD_WIDTH, self.CARD_HEIGHT)
        self.back.hide()

    def set_face_down(self, face_down: bool) -> None:
        """没发牌时整张牌盖上牌背，看不出是谁。"""
        if face_down:
            self.back.setGeometry(0, 0, self.width(), self.height())
            self.back.show()
            self.back.raise_()
        else:
            self.back.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.back.setGeometry(0, 0, self.width(), self.height())

    def set_down_style(self, down: bool) -> None:
        """牌翻过去：底变暗、字变灰，跟“还在桌上”的牌一眼分得开。"""
        self.setProperty("down", down)
        name_size = max(11, round(15 * self._scale))
        tag_size = max(8, round(9 * self._scale))
        name_color = "#6c6455" if down else "#2b2417"
        tag_color = "#554f45" if down else "#7d6c50"
        self.name_label.setStyleSheet(
            "font-family: 'Songti SC', 'SimSun', serif;"
            f" font-size: {name_size}px; color: {name_color};"
        )
        self.tag_label.setStyleSheet(f"font-size: {tag_size}px; color: {tag_color};")
        self.mark.setText("翻" if down else "阳")
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def apply_scale(self, factor: float) -> None:
        """牌被缩小的时候，字也要跟着缩，不然名字会被牌边切掉。"""
        if abs(factor - self._scale) < 0.01:
            return
        self._scale = factor
        self.name_label.setFixedHeight(max(20, round(34 * factor)))
        self.tag_label.setFixedHeight(max(20, round(40 * factor)))
        self.set_down_style(bool(self.property("down")))


class LobbyPage(QWidget):
    start_requested = Signal(str, list, str, bool)
    history_requested = Signal()
    hotspots_requested = Signal()
    ai_settings_requested = Signal()
    window_mode_requested = Signal()
    exit_requested = Signal()

    def __init__(self, store: SessionStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.role_chips: list[SeatCard] = []
        self.mode = "business"
        self._mode_chips: dict[str, list[SeatCard]] = {}
        self._cards: list[SeatCard] = []
        self._animations: list[QSequentialAnimationGroup] = []
        self._dealt = False
        self._compact = False
        self._pending_layout = QTimer(self)
        self._pending_layout.setSingleShot(True)
        self._pending_layout.timeout.connect(lambda: self._layout_cards(animate=False))
        self._build()
        self.set_mode("business")

    # ── 结构 ────────────────────────────────────────────────────────
    def _build(self) -> None:
        self.setObjectName("lobbyPage")
        outer = QVBoxLayout(self)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        outer.setContentsMargins(48, 26, 48, 22)
        outer.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.product_title = QLabel("九人圆桌")
        self.product_title.setFont(title_font(26))
        self.product_title.setStyleSheet(f"color: {COLORS['gold_bright']};")
        header.addWidget(self.product_title)
        self.tagline = QLabel("挑一张桌子坐进去。进去之前只有一件事：说清楚要聊什么。")
        self.tagline.setStyleSheet(f"color: {COLORS['dim']}; font-size: 12px;")
        header.addWidget(self.tagline, 1)
        self.source_badge = QLabel("本次不获取新闻 · 观点待核验")
        self.source_badge.setStyleSheet(
            f"color: {COLORS['muted']}; padding: 6px 12px;"
            " border: 1px solid #40584a; border-radius: 12px; font-size: 11px;"
        )
        header.addWidget(self.source_badge)
        self.history_button = QPushButton("最近讨论")
        self.history_button.clicked.connect(self.history_requested)
        header.addWidget(self.history_button)
        self.hotspots_button = QPushButton("社会热点雷达")
        self.hotspots_button.clicked.connect(self.hotspots_requested)
        header.addWidget(self.hotspots_button)
        self.ai_settings_button = QPushButton("AI 设置")
        self.ai_settings_button.clicked.connect(self.ai_settings_requested)
        header.addWidget(self.ai_settings_button)
        self.window_button = QPushButton("窗口化")
        self.window_button.clicked.connect(self.window_mode_requested)
        header.addWidget(self.window_button)
        self.exit_button = QPushButton("退出")
        self.exit_button.clicked.connect(self.exit_requested)
        header.addWidget(self.exit_button)
        outer.addLayout(header)

        # 两张桌：点哪张换哪张，位置就是整场的入口
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.mode_buttons: dict[str, QPushButton] = {}
        for key in ("event", "business"):
            tab = QPushButton(SECTION_TEXT[key]["tab_text"])
            tab.setObjectName("tableTab")
            tab.setCheckable(True)
            tab.setProperty("sectionTab", True)
            tab.setMinimumHeight(40)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setToolTip(SECTION_TEXT[key]["intro"])
            tab.clicked.connect(lambda _checked=False, target=key: self.set_mode(target))
            self.mode_buttons[key] = tab
            bar.addWidget(tab)
        self.intro = QLabel()
        self.intro.setStyleSheet(f"color: {COLORS['dim']}; font-size: 12px;")
        bar.addWidget(self.intro, 1)
        outer.addLayout(bar)

        self.felt = FeltTable()
        outer.addWidget(self.felt, 1)

        # 还没发牌时，桌面上给一句话：这叠牌是这一桌的人
        self.deck_hint = QLabel("这一桌的人就压在这副牌里 · 点下面「发 牌」", self.felt)
        self.deck_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.deck_hint.setStyleSheet(
            f"color: {COLORS['dim']}; font-size: 12px; letter-spacing: 1px;"
        )

        slip_row = QHBoxLayout()
        slip_row.setSpacing(10)
        slip = QFrame()
        slip.setObjectName("topicSlip")
        slip_layout = QVBoxLayout(slip)
        slip_layout.setContentsMargins(20, 10, 20, 8)
        slip_layout.setSpacing(2)
        self.topic_prompt = QLabel("这一桌聊什么")
        self.topic_prompt.setStyleSheet(
            f"color: {COLORS['gold']}; font-size: 10px; letter-spacing: 2px;"
        )
        slip_layout.addWidget(self.topic_prompt)
        self.topic = QLineEdit()
        self.topic.setObjectName("topicSlipInput")
        self.topic.setMinimumHeight(40)
        slip_layout.addWidget(self.topic)
        slip_row.addWidget(slip, 1)
        self.example_button = QPushButton("换一个")
        self.example_button.clicked.connect(
            lambda: self.topic.setText(SECTION_TEXT[self.mode]["example_topic"])
        )
        slip_row.addWidget(self.example_button, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(slip_row)

        material = QHBoxLayout()
        material.setSpacing(10)
        self.material_label = QLabel("补充材料（可选）")
        self.material_label.setStyleSheet(f"color: {COLORS['dim']}; font-size: 11px;")
        material.addWidget(self.material_label)
        self.source = QTextEdit()
        self.source.setFixedHeight(46)
        material.addWidget(self.source, 1)
        self.rss_opt_in = QCheckBox("允许获取 RSS 前沿信息")
        self.rss_opt_in.setToolTip(
            "开始讨论时获取公开新闻源的标题与摘要；关闭后本次不获取新闻。联网素材与桌上观点分开标记。"
        )
        self.rss_opt_in.setChecked(False)
        self.rss_opt_in.setEnabled(False)
        self.rss_opt_in.toggled.connect(self._update_network_badge)
        material.addWidget(self.rss_opt_in)
        outer.addLayout(material)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.deal_button = QPushButton("发 牌")
        self.deal_button.setObjectName("dealButton")
        self.deal_button.clicked.connect(self._deal)
        footer.addWidget(self.deal_button)
        self.start_button = QPushButton(SECTION_TEXT["business"]["start_button"])
        self.start_button.setProperty("primary", True)
        self.start_button.setMinimumHeight(46)
        self.start_button.clicked.connect(self._start)
        footer.addWidget(self.start_button)
        self.foot_note = QLabel("")
        self.foot_note.setStyleSheet(f"color: {COLORS['dim']}; font-size: 11px;")
        footer.addWidget(self.foot_note)
        footer.addStretch(1)
        outer.addLayout(footer)

        self.network_note = QLabel()
        self.network_note.setWordWrap(True)
        self.network_note.setStyleSheet(f"color: {COLORS['dim']}; font-size: 11px;")
        outer.addWidget(self.network_note)

        self.bottom_note = QLabel(SECTION_TEXT["business"]["note"])
        self.bottom_note.setWordWrap(True)
        self.bottom_note.setStyleSheet(f"color: {COLORS['dim']}; font-size: 11px;")
        outer.addWidget(self.bottom_note)

        self._refresh_network_option()

    # ── 牌桌 ────────────────────────────────────────────────────────
    def _build_deck(self) -> None:
        self._stop_animations()
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._dealt = False
        self.deal_button.setText("发 牌")
        roster = ROLES_BY_MODE[self.mode]
        for index, role in enumerate(roster):
            card = SeatCard(role, self.felt)
            card.toggled.connect(self._on_card_toggled)
            card.show()
            self._cards.append(card)
        self.role_chips = self._cards
        self._mode_chips[self.mode] = self._cards
        for card in self._cards:
            card.setChecked(True)
            card.set_down_style(False)
        self._layout_cards(animate=False)
        self._update_foot_note()

    def _card_size(self, count: int) -> tuple[int, int]:
        """按张数把牌缩放：九张牌也要在一张桌子上一字排开、互不压字。"""
        gap = 12
        avail = max(self.felt.width() * 0.86 - (count - 1) * gap, 260)
        width = int(min(SeatCard.CARD_WIDTH, avail / count))
        width = max(width, 88)
        # 桌子本身矮的时候（小屏幕），牌也不能高过台面
        max_height = max(self.felt.height() * 0.80, 96)
        width = min(width, int(max_height * SeatCard.CARD_WIDTH / SeatCard.CARD_HEIGHT))
        height = int(width * SeatCard.CARD_HEIGHT / SeatCard.CARD_WIDTH)
        return width, height

    def _stack_point(self, index: int, card_w: int, card_h: int) -> QPoint:
        center_x = self.felt.width() // 2 - card_w // 2
        center_y = self.felt.height() // 2 - card_h // 2
        return QPoint(center_x + index * 3 - 10, center_y - index * 3 + 16)

    def _fan_point(
        self, index: int, count: int, *, card_w: int, card_h: int, down: bool
    ) -> QPoint:
        gap = 12
        spread = (count - 1) * (card_w + gap)
        left = self.felt.width() / 2 - spread / 2 + index * (card_w + gap)
        position = 0.5 if count <= 1 else index / (count - 1)
        arc = (1 - 4 * (position - 0.5) ** 2) * -20
        top = self.felt.height() / 2 - card_h / 2 - 4 + arc
        if down:
            top += card_h * 0.34
        return QPoint(int(left), int(top))

    def _layout_cards(self, *, animate: bool) -> None:
        if not self._cards:
            return
        count = len(self._cards)
        card_w, card_h = self._card_size(count)
        for card in self._cards:
            if card.width() != card_w or card.height() != card_h:
                card.setFixedSize(card_w, card_h)
            card.apply_scale(card_w / SeatCard.CARD_WIDTH)
        targets: list[QPoint] = []
        for index, card in enumerate(self._cards):
            card.set_face_down(not self._dealt)
            target = (
                self._fan_point(
                    index, count, card_w=card_w, card_h=card_h, down=not card.isChecked()
                )
                if self._dealt
                else self._stack_point(index, card_w, card_h)
            )
            targets.append(target)
            card.raise_()
        self._stop_animations()
        self.deck_hint.setVisible(not self._dealt)
        if not self._dealt:
            self.deck_hint.setGeometry(
                0,
                int(self.felt.height() / 2 + card_h / 2 + 26),
                self.felt.width(),
                22,
            )
            self.deck_hint.raise_()
        if not animate:
            for card, target in zip(self._cards, targets):
                card.move(target)
            return
        for index, (card, target) in enumerate(zip(self._cards, targets)):
            if card.pos() == target:
                continue
            move = QPropertyAnimation(card, b"pos", self)
            move.setDuration(380)
            move.setStartValue(card.pos())
            move.setEndValue(target)
            move.setEasingCurve(QEasingCurve.Type.OutCubic)
            group = QSequentialAnimationGroup(self)
            if index:
                group.addPause(index * 42)
            group.addAnimation(move)
            group.start()
            self._animations.append(group)

    def _stop_animations(self) -> None:
        for animation in self._animations:
            animation.stop()
            animation.deleteLater()
        self._animations = []

    def _deal(self) -> None:
        if self._dealt:
            for card in self._cards:
                card.blockSignals(True)
                card.setChecked(True)
                card.blockSignals(False)
                card.set_down_style(False)
            self._dealt = False
            self.deal_button.setText("发 牌")
            self._layout_cards(animate=True)
            self._update_foot_note()
            return
        self._dealt = True
        self.deal_button.setText("重新发牌")
        self._layout_cards(animate=True)
        self._update_foot_note()

    def _on_card_toggled(self, checked: bool) -> None:
        card = self.sender()
        if not isinstance(card, SeatCard):
            return
        if not checked and sum(1 for item in self._cards if item.isChecked()) < 2:
            card.blockSignals(True)
            card.setChecked(True)
            card.blockSignals(False)
            card.set_down_style(False)
            self.foot_note.setText("至少留两个人，不然没人说话。")
            return
        card.set_down_style(not checked)
        if not self._dealt:
            # 没发牌就按：先把牌摊开，否则用户看不出这张牌去哪了
            self._dealt = True
            self.deal_button.setText("重新发牌")
        self._layout_cards(animate=True)
        self._update_foot_note()

    def _update_foot_note(self) -> None:
        on_table = sum(1 for card in self._cards if card.isChecked())
        if self._dealt:
            self.foot_note.setText(
                f"桌上 {on_table} 张 · 按下去 {len(self._cards) - on_table} 张"
            )
        else:
            self.foot_note.setText(f"牌堆 {len(self._cards)} 张")

    # ── 其它 ────────────────────────────────────────────────────────
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.height() < 720 or self.width() < 1180
        narrow = self.width() < 1260
        self._compact = compact
        self.layout().setContentsMargins(*((26, 14, 26, 14) if compact else (48, 26, 48, 22)))
        self.layout().setSpacing(10 if compact else 14)
        self.product_title.setFont(title_font(21 if compact else 26))
        # 窗口窄的时候，先把不必要的东西让出去，别把按钮挤出屏幕
        self.tagline.setVisible(self.width() >= 1420)
        self.intro.setVisible(self.width() >= 1180)
        self.source_badge.setVisible(self.width() >= 1120)
        self.material_label.setVisible(self.width() >= 1040)
        self.history_button.setText("历史" if narrow else "最近讨论")
        self.hotspots_button.setText("热点" if narrow else "社会热点雷达")
        self.ai_settings_button.setText("设置" if narrow else "AI 设置")
        self.window_button.setText("窗口" if narrow else "窗口化")
        self.source.setFixedHeight(34 if compact else 46)
        self.topic.setMinimumHeight(32 if compact else 40)
        self.network_note.setVisible(self.height() >= 700)
        self.bottom_note.setVisible(self.height() >= 660)
        self._layout_cards(animate=False)
        self._update_network_badge()
        self._pending_layout.start(0)
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        return QSize(720, 480)

    def _refresh_network_option(self) -> None:
        config = AppConfig.from_environment()
        enabled = (
            config.mode != "offline"
            and config.allow_network
            and config.news_enabled
            and bool(config.news_feed_urls)
        )
        self.rss_opt_in.setEnabled(enabled)
        self.rss_opt_in.setChecked(enabled)
        if enabled:
            model_note = (
                "已启用 OpenAI 兼容模型"
                if config.llm_provider == "openai" and config.allow_llm and config.llm_api_key
                else "真实模型需单独配置"
            )
            self.network_note.setText(f"开始时获取国内新闻源的相关素材，按发布时间排序。{model_note}。")
        elif config.mode == "offline":
            self.network_note.setText("当前已设置强制离线，新闻和模型均不会联网。")
        elif not config.allow_network:
            self.network_note.setText("当前未允许联网，讨论将使用离线模拟。")
        elif not config.news_feed_urls:
            self.network_note.setText("尚未配置 RSS feed，讨论将使用离线素材。")
        else:
            self.network_note.setText("RSS 未启用，讨论将使用离线素材。")
        self._update_network_badge()

    def _update_network_badge(self, _checked: bool = False) -> None:
        short = self.width() < 1260
        live = self.rss_opt_in.isEnabled() and self.rss_opt_in.isChecked()
        if short:
            text = "联网素材" if live else "不获取新闻"
        else:
            text = "联网素材可用 · 观点待核验" if live else "本次不获取新闻 · 观点待核验"
        self.source_badge.setText(text)
        self.source_badge.setToolTip(
            ("联网素材可用" if live else "本次不获取新闻")
            + " · 观点待核验；获取新闻与真实模型讨论是两项独立能力。"
        )

    def _quick(self) -> None:
        selected = (
            {"trend", "need", "builder", "skeptic"}
            if self.mode == "business"
            else {"qian", "li", "kan", "dui"}
        )
        for card in self._cards:
            card.setChecked(card.role.id in selected)
            card.set_down_style(card.role.id not in selected)
        self._layout_cards(animate=True)
        self._update_foot_note()

    def set_mode(self, mode: str) -> None:
        """Switch the lobby between the business table and the gossip table."""
        if mode not in ROLES_BY_MODE:
            mode = "business"
        self.mode = mode
        text = SECTION_TEXT[mode]
        for key, button in self.mode_buttons.items():
            button.setChecked(key == mode)
        self.intro.setText(text["intro"])
        self.topic_prompt.setText(text["topic_prompt"])
        self.topic.setPlaceholderText(text["topic_placeholder"])
        self.source.setPlaceholderText(text["source_placeholder"])
        self.bottom_note.setText(text["note"])
        self.start_button.setText(text["start_button"])
        self._build_deck()
        self.updateGeometry()

    def selected_roles(self) -> list[Role]:
        return [card.role for card in self._cards if card.isChecked()]

    def _start(self) -> None:
        roles = self.selected_roles()
        self.start_requested.emit(
            self.topic.text().strip(),
            roles,
            self.source.toPlainText().strip(),
            self.rss_opt_in.isChecked(),
        )


class HistoryDialog(QDialog):
    session_requested = Signal(object)

    def __init__(self, store: SessionStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("最近讨论")
        self.resize(700, 460)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        sessions = store.list_sessions()
        for session in sessions:
            item = QListWidgetItem(f"{session.created_at:%Y-%m-%d %H:%M}  ·  {session.topic}")
            item.setData(Qt.ItemDataRole.UserRole, session)
            self.list.addItem(item)
        layout.addWidget(self.list)
        self.list.itemDoubleClicked.connect(self._open_selected)
        open_button = QPushButton("打开选中")
        open_button.clicked.connect(self._open_selected)
        layout.addWidget(open_button)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _open_selected(self, _item=None) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.session_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        self.accept()


class RoundtablePage(QWidget):
    back_requested = Signal()
    summary_requested = Signal(object)
    window_mode_requested = Signal()
    exit_requested = Signal()

    def __init__(self, controller: SessionController, audio: AudioController | None = None, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.audio = audio
        self.session: DiscussionSession | None = None
        self._history: list[Utterance] = []
        self._selected_role_ids = {role.id for role in DEFAULT_ROLES}
        self._drawer_animation: QPropertyAnimation | None = None
        self._build()
        controller.session_ready.connect(self._session_ready)
        controller.utterance_changed.connect(self._utterance)
        controller.generation_progress.connect(self._generation_progress)
        controller.playback_state_changed.connect(self._state)
        controller.completed.connect(self._completed)
        controller.error.connect(self._error)
        controller.interjection_added.connect(self._interjection)
        controller.news_status_changed.connect(self._news_status)
        controller.news_finished.connect(self._news_finished)
        controller.generation_state_changed.connect(self._generation_state)
        controller.generation_partial.connect(self._generation_partial)
        controller.discussion_state_changed.connect(self._discussion_state_changed)
        controller.phase_changed.connect(self._phase_changed)

    def _build(self) -> None:
        self.setObjectName("roundtablePage")
        root = QVBoxLayout(self)
        root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        root.setContentsMargins(22, 16, 22, 20)
        root.setSpacing(12)
        header = QHBoxLayout()
        self.topic_label = QLabel("九人圆桌")
        self.topic_label.setFont(title_font(20))
        self.topic_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.topic_label.setMinimumWidth(100)
        header.addWidget(self.topic_label, 1)
        self.section_label = QLabel("")
        self.section_label.setStyleSheet(
            f"color: {COLORS['gold']}; font-size: 12px; padding: 3px 10px; "
            f"border: 1px solid #4c5f3d; border-radius: 10px;"
        )
        self.section_label.setVisible(False)
        header.addWidget(self.section_label)
        self.phase_label = QLabel("准备就绪")
        self.phase_label.setStyleSheet(f"color: {COLORS['gold']}; margin-left: 18px;")
        header.addWidget(self.phase_label)
        header.addStretch()
        window = QPushButton("窗口化")
        window.clicked.connect(self.window_mode_requested)
        header.addWidget(window)
        exit_button = QPushButton("退出")
        exit_button.clicked.connect(self.exit_requested)
        header.addWidget(exit_button)
        root.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.pause_button = QPushButton("暂停")
        self.pause_button.clicked.connect(self.controller.pause_or_resume)
        controls.addWidget(self.pause_button)
        self.cancel_button = QPushButton("取消生成")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(lambda: self.controller.cancel_generation())
        controls.addWidget(self.cancel_button)
        self.next_button = QPushButton("下一步  ›")
        self.next_button.setProperty("primary", True)
        self.next_button.clicked.connect(self.controller.next_step)
        controls.addWidget(self.next_button)
        skip = QPushButton("跳过")
        skip.clicked.connect(self.controller.skip)
        controls.addWidget(skip)
        self.skip_button = skip
        self.finish_button = QPushButton("结束并总结")
        self.finish_button.setProperty("primary", True)
        self.finish_button.clicked.connect(self.controller.finish_discussion)
        controls.addWidget(self.finish_button)
        records = QPushButton("完整记录")
        records.clicked.connect(self._toggle_drawer)
        controls.addWidget(records)
        self.records_button = records
        export = QPushButton("导出")
        export.clicked.connect(self._export)
        controls.addWidget(export)
        self.export_button = export
        self.sound_button = QPushButton("声音：静默")
        self.sound_button.setEnabled(False)
        self.sound_button.setToolTip("当前版本没有音频资源，保持静默")
        self.sound_button.clicked.connect(self._toggle_audio)
        controls.addWidget(self.sound_button)
        back = QPushButton("返回大厅")
        back.clicked.connect(self.back_requested)
        controls.addWidget(back)
        self.back_button = back
        controls.addStretch()
        root.addLayout(controls)
        self.integration_label = QLabel("离线模拟 · 未联网 · 观点待核验")
        self.integration_label.setWordWrap(True)
        self.integration_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 12px;")
        root.addWidget(self.integration_label)
        self.discussion_state_label = QLabel("共识：暂无\n分歧：暂无\n未回答：暂无")
        self.discussion_state_label.setObjectName("discussionStateLabel")
        self.discussion_state_label.setWordWrap(True)
        self.discussion_state_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 12px; padding: 4px 8px;")
        root.addWidget(self.discussion_state_label)

        self.canvas = RoundtableCanvas(list(DEFAULT_ROLES))
        self.canvas.role_clicked.connect(self._role_info)
        root.addWidget(self.canvas, 1)

        self.bubble = QLabel("主持人正在准备圆桌……")
        self.bubble.setWordWrap(True)
        self.bubble.setMinimumHeight(110)
        self.bubble.setStyleSheet(f"background: #1a2d24; border: 2px solid {COLORS['gold']}; border-radius: 18px; padding: 18px 22px; color: {COLORS['cream']}; font-size: 18px; line-height: 1.5;")
        root.addWidget(self.bubble)
        bottom = QHBoxLayout()
        # This row exists to host the interjection box.  It used to repeat the
        # whole current utterance, so the same text appeared twice on screen.
        self.interjection_hint = QLabel("插话会作为你的意见记录，并在下一批发言中得到回应")
        self.interjection_hint.setWordWrap(True)
        self.interjection_hint.setStyleSheet(f"color: {COLORS['muted']}; font-size: 13px; line-height: 1.4;")
        bottom.addWidget(self.interjection_hint, 1)
        self.interjection = QLineEdit()
        self.interjection.setPlaceholderText("插话给主持人……")
        self.interjection.returnPressed.connect(self._send_interjection)
        bottom.addWidget(self.interjection, 1)
        send = QPushButton("插话")
        send.clicked.connect(self._send_interjection)
        bottom.addWidget(send)
        root.addLayout(bottom)
        self.drawer = QFrame(self)
        self.drawer.setVisible(False)
        self.drawer.setObjectName("recordDrawer")
        self.drawer.setStyleSheet("QFrame#recordDrawer { background: #14221d; border: 1px solid #526a59; border-radius: 14px; }")
        drawer_layout = QVBoxLayout(self.drawer)
        drawer_title = QLabel("完整讨论记录")
        drawer_title.setToolTip(kind_legend())
        drawer_layout.addWidget(drawer_title)
        self.evidence = QTextEdit()
        self.evidence.setReadOnly(True)
        self.evidence.setMaximumHeight(210)
        self.evidence.setPlaceholderText("来源与证据将在这里显示；离线模拟观点不等于事实")
        drawer_layout.addWidget(self.evidence)
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        drawer_layout.addWidget(self.transcript)
        self.drawer.setMinimumWidth(320)
        self.drawer.setMaximumWidth(460)
        self.drawer.setGeometry(self.width() - 430, 70, 400, max(300, self.height() - 150))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.height() < 680 or self.width() < 900
        self._compact = compact
        self.layout().setContentsMargins(*( (12, 8, 12, 12) if compact else (22, 16, 22, 20) ))
        self.layout().setSpacing(6 if compact else 12)
        self.canvas.setMinimumSize(520 if compact else 620, 150 if compact else 260)
        self.bubble.setMinimumHeight(72 if compact else 110)
        self.bubble.setStyleSheet(f"background: #1a2d24; border: 2px solid {COLORS['gold']}; border-radius: 18px; padding: {'12px 16px' if compact else '18px 22px'}; color: {COLORS['cream']}; font-size: {'14px' if compact else '18px'};")
        self.interjection.setMinimumHeight(36 if compact else 42)
        self.skip_button.setVisible(not compact)
        self.export_button.setVisible(not compact)
        self.sound_button.setVisible(not compact)
        self.back_button.setVisible(True)
        self.records_button.setText("记录" if compact else "完整记录")
        current = self.controller.playback.current
        if current:
            self._show_current_text(current)
        self.updateGeometry()
        target = self._drawer_target_geometry()
        if self.drawer.isVisible() and not (self._drawer_animation and self._drawer_animation.state() == QPropertyAnimation.State.Running):
            self.drawer.setGeometry(target)

    def minimumSizeHint(self) -> QSize:
        return QSize(640, 400)

    def set_selected_roles(self, roles: list[Role]) -> None:
        self._selected_role_ids = {role.id for role in roles}
        if roles:
            self.canvas.set_roles(roles)
        self.canvas.set_selected(self._selected_role_ids)

    def load_session(self, session: DiscussionSession) -> None:
        self.canvas.set_roles(default_roles_for(session.mode))
        if session.selected_role_ids:
            self._selected_role_ids = set(session.selected_role_ids)
            self.canvas.set_selected(self._selected_role_ids)
        self.controller.load(session)

    def _section_text(self) -> dict[str, str]:
        mode = self.session.mode if self.session is not None else "business"
        return SECTION_TEXT.get(mode, SECTION_TEXT["business"])

    def _show_section_badge(self, session: DiscussionSession) -> None:
        """Say which table you are at, so the two sections are never ambiguous."""
        if session.mode == "event":
            self.section_label.setText("八卦桌 · 事件讨论")
            self.section_label.setVisible(True)
        else:
            self.section_label.setText("")
            self.section_label.setVisible(False)

    def _session_ready(self, session: DiscussionSession) -> None:
        self.session = session
        self._history.clear()
        self.transcript.clear()
        self.evidence.clear()
        self.topic_label.setText(QFontMetrics(self.topic_label.font()).elidedText(session.topic, Qt.TextElideMode.ElideMiddle, 440))
        self.topic_label.setToolTip(session.topic)
        self._show_section_badge(session)
        self._show_integration(session)
        self._show_evidence(session)
        self._discussion_state_changed(session.discussion_state)
        self.canvas.set_selected(self._selected_role_ids)
        self.canvas.set_state(session.topic, "已加载历史讨论" if self.controller.playback.state.value == "completed" else "讨论进行中", None)
        if self.controller.playback.state.value == "completed":
            self._history = list(session.utterances)
            self.transcript.setPlainText("\n\n".join(self._transcript_line(item) for item in self._history))
            self.phase_label.setText(f"已加载历史讨论 · 共 {len(self._history)} 条记录")
            if session.opportunity:
                self._completed(session)

    def _show_integration(self, session: DiscussionSession) -> None:
        network = "已使用网络" if session.network_used else "未使用网络"
        rss = f"来源 {len(session.sources)} 条 · 均未核验" if session.sources else "无外部线索"
        self.integration_label.setText(f"{session.content_label} · {network} · {rss}")
        self.integration_label.setToolTip(
            f"请求：{session.request_mode}；提供方：{session.effective_provider}/{session.provider_mode}\n"
            f"RSS：尝试={session.news_attempted}，命中={session.news_matched}，部分失败={session.news_partial_failure}\n"
            f"{session.status_message}"
        )

    def _show_evidence(self, session: DiscussionSession) -> None:
        explanation = "桌上观点从哪里来？\n" + session.viewpoint_source_description + "\n"
        if not session.sources:
            self.evidence.setPlainText(explanation + f"\n无外部来源；{session.content_label}。\n{session.status_message}")
            return
        lines = [explanation, f"来源 {len(session.sources)} 条（内容均未核验）："]
        for item in session.sources:
            when = item.published_at or item.fetched_at
            stamp = f" · {when:%Y-%m-%d %H:%M}" if when else ""
            lines.append(f"· {item.title} [{item.source_type}] · {item.credibility}{stamp}")
            if item.url:
                lines.append(f"  {item.url}")
            if item.note:
                lines.append(f"  {item.note}")
        self.evidence.setPlainText("\n".join(lines))

    def _news_status(self, message: str) -> None:
        if self.session is not None:
            self.integration_label.setText(f"{self.integration_label.text().split(' · 状态：')[0]} · 状态：{message}")
        else:
            self.integration_label.setText(message)
            self.phase_label.setText("正在获取新闻素材")
            self._set_bubble("正在查找与主题相关的新闻标题和摘要……\n新闻获取结束后开始讨论，来源和观点将分别标明。")

    def _news_finished(self, _result) -> None:
        if self.session is not None:
            self._show_integration(self.session)
            self._show_evidence(self.session)

    def _generation_state(self, state: str) -> None:
        running = state in {"running", "cancelling"}
        self.cancel_button.setVisible(running)
        self.cancel_button.setEnabled(state == "running")
        self.next_button.setEnabled(not running and self.controller.playback.state.value != "completed")
        self.finish_button.setEnabled(not running and self.controller.playback.state.value != "completed")
        if state == "running":
            self.phase_label.setText("正在生成讨论…")
            self._set_bubble("圆桌成员正在准备观点……")
        elif state == "continuing":
            self.phase_label.setText("正在延展讨论…")
        elif state == "cancelling":
            self.phase_label.setText("正在取消生成…")
        elif state == "cancelled":
            self.phase_label.setText("生成已取消")
        elif state == "fallback":
            self.phase_label.setText("已回退到离线模拟")
        elif state == "error":
            self.phase_label.setText("生成失败")

    def _generation_progress(self, done: int, total: int) -> None:
        """Show how much of the opening batch is already prepared.

        The first turn is on screen by now, so this is background progress rather
        than a blocking wait; it must not disturb the turn counter or the bubble.
        """
        self.phase_label.setText(f"正在后台准备后续发言…（{done}/{total} 条已就绪）")

    def _generation_partial(self, speaker: str, text: str) -> None:
        if text:
            self.phase_label.setText(f"{speaker} 正在生成…")

    def _reply_label(self, utterance: Utterance) -> str:
        if not utterance.replies_to or self.session is None:
            return ""
        target = next((item for item in self.session.utterances if item.event_id == utterance.replies_to), None)
        return f" · 回应 {target.speaker_name}" if target is not None else ""

    def _intervention_label(self, utterance: Utterance) -> str:
        if utterance.speaker_id != "moderator" or utterance.phase != "状态整理" or self.session is None:
            return ""
        reason = self.session.discussion_state.host_intervention_reason
        return f" · 介入原因：{reason}" if reason else ""

    def _review_label(self, utterance: Utterance) -> str:
        """Say so when the quality check sent this turn back for a rewrite."""
        if not utterance.review_note:
            return ""
        return f" · 质检重写：{utterance.review_note}"

    def _transcript_line(self, utterance: Utterance) -> str:
        """Render one recorded turn; live turns and reopened history use this same form."""
        source = self.session.utterance_source(utterance) if self.session else "未标记来源"
        intent = f" · {utterance.intent}" if utterance.intent and utterance.intent != "initial" else ""
        stance = " · 改变立场" if utterance.stance_change else ""
        face = f" · {face_label(utterance.face)}" if utterance.face else ""
        return (
            f"【{utterance.phase}】 {utterance.speaker_name}{face} · {utterance.kind.value}"
            f"{intent}{stance}{self._reply_label(utterance)}{self._intervention_label(utterance)} · {source}"
            f"{self._review_label(utterance)}"
            f"\n{utterance.content}"
        )

    def _utterance(self, utterance: Utterance, index: int, total: int) -> None:
        if self.session:
            self._show_integration(self.session)
        self._history.append(utterance)
        self.phase_label.setText(f"{utterance.phase}  ·  第 {index + 1} 条")
        self.canvas.set_state(status=f"{utterance.speaker_name} 正在发言", active_id=utterance.speaker_id if utterance.speaker_id != "moderator" else None)
        self._show_current_text(utterance)
        self.transcript.append(self._transcript_line(utterance))

    def _set_bubble(self, text: str, tooltip: str = "") -> None:
        """Write the current-turn card. The kind legend belongs only to a turn,
        so status messages must not inherit the tooltip from the previous one."""
        self.bubble.setText(text)
        self.bubble.setToolTip(tooltip)

    def _show_current_text(self, utterance: Utterance) -> None:
        compact = getattr(self, "_compact", False)
        source = self.session.utterance_source(utterance) if self.session else "未标记来源"
        content = utterance.content
        if compact and len(content) > 140:
            content = content[:140] + "…（全文见记录）"
        labels = f"{self._reply_label(utterance)}{self._intervention_label(utterance)}"
        face = f" · {face_label(utterance.face)}" if utterance.face else ""
        self._set_bubble(f"{utterance.speaker_name}{face}  ·  {kind_label(utterance.kind)}{labels}  ·  {source}\n{content}", kind_legend())

    def _state(self, state: str) -> None:
        self.pause_button.setText("继续" if state == "paused" else "暂停")
        self.pause_button.setEnabled(state in {"playing", "paused"})
        self.next_button.setEnabled(state != "completed")
        self.finish_button.setEnabled(state != "completed")
        if state == "completed":
            self.canvas.set_state(status=f"讨论完成，可查看{self._section_text()['archive_title']}", active_id=None)

    def _completed(self, session: DiscussionSession) -> None:
        if session.opportunity:
            card = session.opportunity
            support = card.support[0] if card.support else "当前还没有支持性观点"
            risk = card.risks[0] if card.risks else "当前还没有风险观点"
            text = SECTION_TEXT.get(session.mode, SECTION_TEXT["business"])
            self._set_bubble(
                f"讨论已结束 · {card.title}\n{text['field_audience']}：{card.audience}\n\n"
                f"{text['label_support']}：{support}\n{text['label_risks']}：{risk}\n\n"
                f"完整内容已进入{text['archive_title']}。"
            )
        self.summary_requested.emit(session)

    def _send_interjection(self) -> None:
        text = self.interjection.text().strip()
        if text:
            self.controller.add_interjection(text)
            self.interjection.clear()

    def _interjection(self, text: str) -> None:
        self._set_bubble(f"用户插话 · 已记录\n{text}\n已加入下一批回应队列，仍需核验。")

    def _discussion_state_changed(self, state) -> None:
        text = self._section_text()
        consensus = "；".join(state.consensus[:2]) or "暂无"
        conflicts = "；".join(state.conflicts[:2]) or "暂无"
        questions = "；".join(state.unresolved_questions[:2]) or "暂无"
        self.discussion_state_label.setText(
            f"{text['label_consensus']}：{consensus}\n"
            f"{text['label_conflict']}：{conflicts}\n"
            f"{text['label_unresolved']}：{questions}"
        )

    def _phase_changed(self, phase: str) -> None:
        if phase:
            self.phase_label.setText(phase)

    def _toggle_drawer(self) -> None:
        target = self._drawer_target_geometry()
        hidden = QRect(self.width() + 12, target.y(), target.width(), target.height())
        animation = QPropertyAnimation(self.drawer, b"geometry", self)
        animation.setDuration(220)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._drawer_animation = animation
        if self.drawer.isVisible():
            animation.setStartValue(self.drawer.geometry())
            animation.setEndValue(hidden)
            animation.finished.connect(self.drawer.hide)
        else:
            self.drawer.setGeometry(hidden)
            self.drawer.show()
            self.drawer.raise_()
            animation.setStartValue(hidden)
            animation.setEndValue(target)
        animation.start()

    def _drawer_target_geometry(self) -> QRect:
        width = min(460, max(320, self.width() // 3))
        return QRect(self.width() - width - 22, 70, width, max(300, self.height() - 150))

    def _toggle_audio(self) -> None:
        if self.audio is None:
            return
        enabled = not (self.audio.ambient_enabled or self.audio.effects_enabled)
        self.audio.set_ambient(enabled)
        self.audio.set_effects(enabled)
        self.sound_button.setText("声音：已启用" if enabled else "声音：静音")

    def _role_info(self, role: Role) -> None:
        QMessageBox.information(self, role.name, f"{role.duty}\n\n视角提示：{role.prompt}")

    def _export(self) -> None:
        if not self.session:
            return
        path, selected = QFileDialog.getSaveFileName(self, "导出讨论", str(Path.home()), "Markdown (*.md);;JSON (*.json)")
        if not path:
            return
        if selected.startswith("Markdown") or path.lower().endswith(".md"):
            export_markdown(self.session, Path(path))
        else:
            export_json(self.session, Path(path))

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "还需要一点信息", message)


class SummaryPage(QWidget):
    """A quiet, readable end state for the discussion."""

    back_requested = Signal()
    lobby_requested = Signal()
    window_mode_requested = Signal()
    exit_requested = Signal()

    def __init__(self, session: DiscussionSession | None = None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.title_label = QLabel("机会档案")
        self._build()
        if session is not None:
            self.set_session(session)

    def _build(self) -> None:
        self.setObjectName("summaryPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 36, 56, 42)
        root.setSpacing(18)
        header = QHBoxLayout()
        self.title_label.setFont(title_font(34))
        self.title_label.setStyleSheet(f"color: {COLORS['gold_bright']};")
        header.addWidget(self.title_label)
        self.summary_meta = QLabel("讨论结束后，这里会显示完整机会档案")
        self.summary_meta.setWordWrap(True)
        self.summary_meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.summary_meta.setMinimumWidth(100)
        self.summary_meta.setStyleSheet(f"color: {COLORS['muted']}; margin-left: 18px;")
        header.addWidget(self.summary_meta, 1)
        header.addStretch()
        window = QPushButton("窗口化")
        window.clicked.connect(self.window_mode_requested)
        header.addWidget(window)
        exit_button = QPushButton("退出")
        exit_button.clicked.connect(self.exit_requested)
        header.addWidget(exit_button)
        root.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 10, 0)
        self.content_layout.setSpacing(14)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        actions = QHBoxLayout()
        back = QPushButton("返回圆桌")
        back.clicked.connect(self.back_requested)
        actions.addWidget(back)
        lobby = QPushButton("回到主题大厅")
        lobby.clicked.connect(self.lobby_requested)
        actions.addWidget(lobby)
        actions.addStretch()
        self.export_button = QPushButton("导出档案")
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.export_button)
        root.addLayout(actions)

    def set_session(self, session: DiscussionSession) -> None:
        self.session = session
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        card = session.opportunity
        text = SECTION_TEXT.get(session.mode, SECTION_TEXT["business"])
        self.title_label.setText(text["archive_title"])
        self.summary_meta.setText(
            f"{session.topic}  ·  共 {len(session.utterances)} 条发言  ·  "
            f"{session.content_label}"
        )
        if card is None:
            self._add_section("讨论状态", f"本次讨论没有生成{text['archive_title']}。请返回圆桌继续讨论，或重新开始。")
            return
        self._add_section(text["field_title"], card.title, emphasized=True)
        self._add_section(text["field_audience"], card.audience)
        self._add_list_section(text["label_support"], card.support)
        self._add_list_section(text["label_risks"], card.risks)
        self._add_list_section(text["label_assumptions"], card.assumptions)
        self._add_list_section(text["label_next_steps"], card.next_steps)
        state = session.discussion_state
        self._add_list_section("当前共识", state.consensus)
        self._add_list_section("未解决分歧", state.conflicts)
        self._add_list_section("未回答问题", state.unresolved_questions)
        stance_lines = [
            f"{role_id}：{stance}" for role_id, stance in state.role_stances.items()
        ]
        self._add_list_section("立场轨迹", stance_lines)
        distribution = "\n".join(f"{key}：{value}" for key, value in card.stance_counts.items()) or "暂无统计"
        self._add_section("观点分布", distribution)
        self._add_section(
            "来源与生成状态",
            f"请求模式：{session.request_mode}\n实际提供方：{session.effective_provider}\n"
            f"新闻来源：{session.news_provider}\n网络使用：{'是' if session.network_used else '否'}\n"
            f"状态：{session.status_message or '无额外状态'}\n"
            "所有角色观点、RSS 素材和模型输出都需要在真实调研中继续核验。",
        )
        self._add_section("桌上观点从哪里来？", session.viewpoint_source_description)
        self.content_layout.addStretch()

    def _add_section(self, title: str, body: str, *, emphasized: bool = False) -> None:
        frame = QFrame()
        frame.setObjectName("summaryCard")
        frame.setStyleSheet(
            f"QFrame#summaryCard {{ background: {COLORS['panel']}; border: 1px solid #334d40; border-radius: 16px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 18, 22, 18)
        label = QLabel(title)
        label.setFont(title_font(18 if emphasized else 15))
        label.setStyleSheet(f"color: {COLORS['gold_bright'] if emphasized else COLORS['gold']};")
        layout.addWidget(label)
        text = QLabel(body)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setStyleSheet(f"color: {COLORS['cream']}; font-size: {'20px' if emphasized else '15px'}; line-height: 1.5;")
        layout.addWidget(text)
        self.content_layout.addWidget(frame)

    def _add_list_section(self, title: str, values: list[str]) -> None:
        self._add_section(title, "\n".join(f"• {value}" for value in values) or "暂无记录")

    def _export(self) -> None:
        if self.session is None:
            return
        path, selected = QFileDialog.getSaveFileName(self, "导出机会档案", str(Path.home()), "Markdown (*.md);;JSON (*.json)")
        if not path:
            return
        if selected.startswith("Markdown") or path.lower().endswith(".md"):
            export_markdown(self.session, Path(path))
        else:
            export_json(self.session, Path(path))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("九人圆桌")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.store = SessionStore()
        self.config = AISettingsStore().load(AppConfig.from_environment())
        provider, news_provider, integration_status = resolve_providers(self.config)
        self.controller = SessionController(provider=provider, news_provider=news_provider, integration_status=integration_status, store=self.store)
        self.audio = AudioController()
        feeds_cache = HotspotCache()
        # The feed and model providers must not share one cache file: each save
        # rewrites the whole file, so sharing would make them overwrite each other.
        model_cache = HotspotCache(feeds_cache.path.with_name("hotspots-model.json"))
        hotspot_network_allowed = self.config.allow_network and self.config.news_enabled and self.config.mode != "offline"
        feeds_provider = HotspotProvider(
            default_hotspot_feeds(self.config.news_feed_urls),
            timeout=self.config.timeout_seconds,
            max_items=max(12, self.config.max_news_items * 4),
            cache=feeds_cache,
        )
        if integration_status.discussion_provider in {"anthropic", "openai-compatible"}:
            # Real headlines first (they carry a real outlet and a real
            # publication time); the model only ever adds a clearly separated,
            # clearly labelled supplement, because it cannot see current events.
            hotspot_provider = HybridHotspotProvider(
                feeds=feeds_provider,
                model=ModelHotspotProvider(provider.complete, cache=model_cache),
            )
        else:
            hotspot_provider = feeds_provider
        self.stack = QStackedWidget()
        self.lobby = LobbyPage(self.store)
        self.roundtable = RoundtablePage(self.controller, self.audio)
        self.summary = SummaryPage()
        self.hotspots = HotspotPage(hotspot_provider, network_allowed=hotspot_network_allowed)
        self.stack.addWidget(self.lobby)
        self.stack.addWidget(self.roundtable)
        self.stack.addWidget(self.summary)
        self.stack.addWidget(self.hotspots)
        self.setCentralWidget(self.stack)
        self.lobby.start_requested.connect(self._start)
        self.lobby.history_requested.connect(self._history)
        self.lobby.hotspots_requested.connect(self._show_hotspots)
        self.lobby.ai_settings_requested.connect(self._ai_settings)
        self.lobby.window_mode_requested.connect(self._toggle_window_mode)
        self.lobby.exit_requested.connect(self.close)
        self.roundtable.back_requested.connect(self._back)
        self.roundtable.summary_requested.connect(self._show_summary)
        self.roundtable.window_mode_requested.connect(self._toggle_window_mode)
        self.roundtable.exit_requested.connect(self.close)
        self.summary.back_requested.connect(self._show_roundtable)
        self.summary.lobby_requested.connect(self._back_to_lobby)
        self.summary.window_mode_requested.connect(self._toggle_window_mode)
        self.summary.exit_requested.connect(self.close)
        self.hotspots.back_requested.connect(self._back_to_lobby)
        self.hotspots.discuss_requested.connect(self._discuss_hotspot)
        self.hotspots.window_mode_requested.connect(self._toggle_window_mode)
        self.hotspots.exit_requested.connect(self.close)
        self.showFullScreen()

    def _start(self, topic: str, roles: list[Role], source: str, fetch_news: bool = False) -> None:
        self.roundtable.set_selected_roles(roles)
        self.stack.setCurrentWidget(self.roundtable)
        self.controller.start(topic, roles, source, fetch_news=fetch_news)

    def _discuss_hotspot(self, topic: str, note: str) -> None:
        """Start a discussion straight from a hotspot card.

        The card's provenance travels in ``note`` so the seats cannot mistake a
        model-recalled item for today's verified news. A hotspot is an event, so
        it opens on the event roster: the business seats would turn it into a
        market opportunity instead of talking about what happened. If the user
        has ticked nothing on that roster we seat all eight rather than start an
        empty table.
        """
        topic = topic.strip()
        if not topic:
            return
        self.lobby.set_mode("event")
        roles = self.lobby.selected_roles() or default_roles_for("event")
        self.lobby.topic.setText(topic)
        self.lobby.source.setPlainText(note)
        self._start(topic, roles, note, fetch_news=False)

    def _ai_settings(self) -> None:
        dialog = AISettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.result_config
            provider, news, status = resolve_providers(self.config)
            self.controller.provider = provider
            self.controller.news_provider = news
            self.controller.integration_status = status
            self.lobby.network_note.setText("AI 配置已保存，用于下一次讨论；尚未验证服务连接。" if self.config.allow_llm else "AI 已关闭，使用离线角色模板。")

    def _history(self) -> None:
        dialog = HistoryDialog(self.store, self)
        dialog.session_requested.connect(self._open_history)
        dialog.exec()

    def _open_history(self, session: DiscussionSession) -> None:
        self.roundtable.load_session(session)
        self._show_summary(session)

    def _show_summary(self, session: DiscussionSession) -> None:
        self.summary.set_session(session)
        self.stack.setCurrentWidget(self.summary)

    def _show_hotspots(self) -> None:
        topic = self.lobby.topic.text().strip()
        self.stack.setCurrentWidget(self.hotspots)
        self.hotspots.set_context(topic, auto_refresh=True)

    def _show_roundtable(self) -> None:
        self.stack.setCurrentWidget(self.roundtable)

    def _back_to_lobby(self) -> None:
        self._back()

    def _back(self) -> None:
        self.controller.cancel_generation(emit_state=False)
        self.controller.timer.stop()
        self.controller.save()
        self.stack.setCurrentWidget(self.lobby)

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event) -> None:
        if not hasattr(self, "controller"):
            event.accept()
            return
        if hasattr(self, "hotspots"):
            self.hotspots.cancel_refresh()
        self.controller.shutdown()
        self.controller.timer.stop()
        self.controller.save()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
            return
        super().keyPressEvent(event)


def run() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("九人圆桌")
    app.setStyleSheet(app_stylesheet())
    window = MainWindow()
    window.show()
    return app.exec()
