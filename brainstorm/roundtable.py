"""Native-drawn roundtable scenery and role seats."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QToolTip, QWidget

from .models import Role
from .qt_theme import COLORS


class RoundtableCanvas(QWidget):
    role_clicked = Signal(object)
    role_hovered = Signal(object)

    def __init__(self, roles: list[Role], parent=None) -> None:
        super().__init__(parent)
        self.roles = roles
        self.selected_ids = {role.id for role in roles}
        self.active_id: str | None = None
        self.moods: dict[str, int] = {}
        self.quiet: set[str] = set()
        self.topic = "等待主题"
        self.status = "准备就绪"
        self.setMouseTracking(True)
        # Keep the tabletop readable on desktop while allowing the shell to
        # compress on 1024x640 displays and high-DPI scaled windows.
        self.setMinimumSize(620, 260)
        self._seat_regions: dict[str, QRectF] = {}
        if getattr(sys, "frozen", False):
            root = Path(sys._MEIPASS)
        else:
            root = Path(__file__).resolve().parent.parent
        self._avatar_dir = root / "assets" / "avatars"
        self._load_avatar_assets(roles)

    def _load_avatar_assets(self, roles: list[Role]) -> None:
        """按当前桌的席位重新读头像。

        以前只在构造时读一次，切分区后位图字典还留着上一桌的人，
        新席位找不到位图就退回木刻版 SVG——大厅是新头像、局内是旧木刻，
        两边对不上。所以每次换席位都要重读。
        """

        self._avatar_renderers = {
            role.id: QSvgRenderer(str(self._avatar_dir / f"{role.id}.svg"))
            for role in roles
        }
        # 有成品位图就用位图（生成/手绘的头像），没有才退回 SVG
        self._avatar_pixmaps = {
            role.id: QPixmap(str(self._avatar_dir / f"{role.id}.png"))
            for role in roles
            if (self._avatar_dir / f"{role.id}.png").exists()
        }

    def set_mood(self, seat_id: str, mood: int) -> None:
        if self.moods.get(seat_id) != mood:
            self.moods[seat_id] = mood
            self.update()

    def set_quiet(self, seat_ids) -> None:
        seats = set(seat_ids)
        if seats != self.quiet:
            self.quiet = seats
            self.update()

    def set_state(self, topic: str | None = None, status: str | None = None, active_id: str | None = None) -> None:
        if topic is not None:
            self.topic = topic
        if status is not None:
            self.status = status
        self.active_id = active_id
        self.update()

    def set_selected(self, role_ids: set[str]) -> None:
        self.selected_ids = role_ids
        self.update()

    def set_roles(self, roles: list[Role]) -> None:
        """Swap the seat roster when the section changes.

        The business section seats nine occupations, the event section seats the
        eight trigrams; the orbit radius and avatar set both depend on the roster,
        so a section change has to rebuild them instead of reusing nine seats.
        """
        self.roles = list(roles)
        self.selected_ids = {role.id for role in self.roles}
        self.active_id = None
        self._load_avatar_assets(self.roles)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(COLORS["night"]))
        glow = QRadialGradient(QPointF(w * 0.5, h * 0.48), max(w, h) * 0.62)
        glow.setColorAt(0, QColor("#203f31"))
        glow.setColorAt(1, QColor(COLORS["night"]))
        painter.fillRect(self.rect(), glow)
        compact = h < 320
        cx, cy = w * 0.5, h * (0.50 if compact else 0.46)
        rx, ry = min(w * 0.34, 430), min(h * 0.34, 250)
        table = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#17100c"))
        painter.drawEllipse(table.adjusted(-14, 18, 14, 26))
        painter.setBrush(QColor(COLORS["gold"]))
        painter.drawEllipse(table.adjusted(-8, -8, 8, 8))
        painter.setBrush(QColor(COLORS["felt"]))
        painter.drawEllipse(table.adjusted(-2, -2, 2, 2))
        painter.setPen(QPen(QColor("#3b8060"), 2))
        painter.setBrush(QColor(COLORS["felt_light"]))
        painter.drawEllipse(table.adjusted(25, 22, -25, -22))
        painter.setPen(QPen(QColor("#b08d50"), 1))
        painter.drawEllipse(table.adjusted(39, 35, -39, -35))

        if not compact:
            painter.setPen(QColor(COLORS["gold_bright"]))
            painter.setFont(QFont("Microsoft YaHei UI", 14, QFont.Weight.DemiBold))
            painter.drawText(QRectF(cx - 150, cy - 40, 300, 28), Qt.AlignmentFlag.AlignCenter, "主持人 · 圆桌中枢")
        painter.setPen(QColor(COLORS["cream"]))
        painter.setFont(QFont("Microsoft YaHei UI", 9 if compact else 12))
        topic_rect = QRectF(cx - min(rx * 0.7, 260), cy - 14 if compact else cy - 5, min(rx * 1.4, 520), 24 if compact else 42)
        topic = painter.fontMetrics().elidedText(self.topic, Qt.TextElideMode.ElideMiddle, int(topic_rect.width()))
        painter.drawText(topic_rect, Qt.AlignmentFlag.AlignCenter, topic)
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont("Microsoft YaHei UI", 8 if compact else 10))
        if not compact:
            painter.drawText(QRectF(cx - 150, cy + 37, 300, 24), Qt.AlignmentFlag.AlignCenter, self.status)

        self._seat_regions.clear()
        # Account for both the avatar above a seat and its two text rows below.
        # The old 42%-height orbit clipped names/status at the bottom edge.
        seat_rx = min(w * (0.46 if compact else 0.43), 560, cx - (30 if compact else 76), w - cx - (30 if compact else 76))
        seat_ry = min(h * (0.42 if compact else 0.38), 310, cy - (24 if compact else 40), h - cy - (30 if compact else 76))
        for index, role in enumerate(self.roles):
            angle = 2 * math.pi * index / len(self.roles) - math.pi / 2
            x, y = cx + math.cos(angle) * seat_rx, cy + math.sin(angle) * seat_ry
            active = role.id == self.active_id
            self._draw_seat(painter, role, QPointF(x, y), 1.0 if role.id in self.selected_ids else 0.34, active, compact)
            self._seat_regions[role.id] = QRectF(x - (28 if compact else 68), y - (28 if compact else 36), 56 if compact else 136, 64 if compact else 106)

    def _draw_seat(self, painter: QPainter, role: Role, point: QPointF, opacity: float, active: bool, compact: bool = False) -> None:
        painter.save()
        painter.setOpacity(opacity)
        radius = 20 if compact else 27
        if active:
            painter.setPen(QPen(QColor(COLORS["gold_bright"]), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            ring = radius + (5 if compact else 9)
            painter.drawEllipse(QRectF(point.x() - ring, point.y() - ring, ring * 2, ring * 2))
        painter.setPen(QPen(QColor("#d8c28b"), 1))
        painter.setBrush(QColor(role.color))
        avatar_rect = QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2)
        painter.drawEllipse(avatar_rect)
        avatar = self._avatar_pixmaps.get(role.id)
        renderer = self._avatar_renderers.get(role.id)
        if avatar is not None and not avatar.isNull():
            painter.save()
            painter.setClipPath(self._circle_path(point, radius))
            painter.drawPixmap(
                QRectF(avatar_rect).toRect(),
                avatar,
                avatar.rect(),
            )
            painter.restore()
        elif renderer and renderer.isValid():
            painter.save()
            painter.setClipPath(self._circle_path(point, radius))
            renderer.render(painter, avatar_rect)
            painter.restore()
        if compact and not active:
            painter.restore()
            return
        painter.setPen(QColor(COLORS["cream"]))
        painter.setFont(QFont("Microsoft YaHei UI", 8 if compact else 10, QFont.Weight.DemiBold))
        label_width = 88 if compact else 136
        painter.drawText(QRectF(point.x() - label_width / 2, point.y() + radius + 3, label_width, 18), Qt.AlignmentFlag.AlignCenter, role.name)
        if compact:
            painter.restore()
            return
        mood = self.moods.get(role.id)
        if mood is not None:
            # 三颗点表示脸色：越少越冷。不写字，免得桌上像在贴标签。
            filled = 1 if mood <= -2 else 2 if mood <= 0 else 3
            color = "#96302c" if mood < 0 else ("#caa96a" if mood > 0 else "#9a8b6d")
            for slot in range(3):
                dot = QPointF(point.x() - 8 + slot * 8, point.y() + radius + 26)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(color) if slot < filled else QColor("#3a3228"))
                painter.drawEllipse(dot, 2.6, 2.6)

        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        if active:
            note = "当前发言"
        elif role.id in self.quiet:
            note = "一直没人接他"
        else:
            note = "参与" if opacity > 0.5 else "未参与"
        painter.drawText(QRectF(point.x() - 68, point.y() + 52, 136, 18), Qt.AlignmentFlag.AlignCenter, note)
        painter.restore()

    @staticmethod
    def _circle_path(point: QPointF, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2))
        return path

    def mouseMoveEvent(self, event) -> None:
        role = self._role_at(event.position())
        if role:
            QToolTip.showText(event.globalPosition().toPoint(), f"{role.name}\n{role.duty}", self)
            self.role_hovered.emit(role)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            role = self._role_at(event.position())
            if role:
                self.role_clicked.emit(role)

    def _role_at(self, point: QPointF) -> Role | None:
        for role in self.roles:
            if self._seat_regions.get(role.id, QRectF()).contains(point):
                return role
        return None
