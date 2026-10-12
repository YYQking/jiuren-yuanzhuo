"""Render the real Qt pages without relying on Windows screen capture."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QFontDatabase
from brainstorm.engine import MockDiscussionProvider
from brainstorm.qt_app import LobbyPage, RoundtablePage, SummaryPage
from brainstorm.qt_theme import app_stylesheet
from brainstorm.hotspot_page import HotspotPage
from brainstorm.hotspots import HotspotFetchResult, HotspotItem
from brainstorm.roles import DEFAULT_ROLES
from brainstorm.session_controller import SessionController
from brainstorm.storage import SessionStore


def main():
    app = QApplication.instance() or QApplication([])
    # Qt's offscreen platform does not always enumerate Windows' installed
    # fonts. Register the existing system font for reliable Chinese QA
    # screenshots; this does not bundle or modify the font in the app.
    windows_font = Path("C:/Windows/Fonts/msyh.ttc")
    if windows_font.is_file():
        QFontDatabase.addApplicationFont(str(windows_font))
    app.setStyleSheet(app_stylesheet())
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/ui-verification")
    output.mkdir(parents=True, exist_ok=True)
    store = SessionStore(output / "history")
    report = []
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    for physical_width, physical_height in [(1366, 768), (1536, 864), (1920, 1080), (1024, 640)]:
        width, height = round(physical_width / scale), round(physical_height / scale)
        session = MockDiscussionProvider().discuss("社区里的银发人群如何更容易使用数字服务？", DEFAULT_ROLES)
        controller = SessionController(store=store)
        radar = HotspotPage(network_allowed=False)
        radar.set_context(session.topic, auto_refresh=False)
        stamp = datetime(2026, 10, 11, 10, 30, tzinfo=timezone.utc)
        # Synthetic layout fixtures, never published as live news or user cache.
        radar.set_result(HotspotFetchResult([
            HotspotItem("【排版样例】社区数字服务的适老化改造", url="https://example.test/a", publisher="样例媒体（非真实新闻）", region="domestic", category="政策", summary="用于界面检查的模拟摘要：观察新闻标题、来源、时间、筛选与原文入口在不同屏幕下的显示。", published_at=stamp, fetched_at=stamp, related=True),
            HotspotItem("【排版样例】Accessible digital services for older adults", url="https://example.test/b", publisher="Layout fixture only", region="international", category="科技", summary="Synthetic content for layout verification, not a real headline. It tests wrapping of international news alongside domestic news.", published_at=stamp, fetched_at=stamp, related=True),
            HotspotItem("【排版样例】科技团队发布公共服务研究", url="https://example.test/c", publisher="样例科技栏目", region="domestic", category="科技", summary="测试社会热点广场与主题相关区的上下分区。", published_at=stamp, fetched_at=stamp),
            HotspotItem("【排版样例】Global science and business briefing", url="https://example.test/d", publisher="Sample international source", region="international", category="科学", summary="Layout fixture for the general news section.", published_at=stamp, fetched_at=stamp),
        ], message="界面排版样例 · 非真实新闻", fetched_at=stamp))
        pages = {"lobby": LobbyPage(store), "roundtable": RoundtablePage(controller), "summary": SummaryPage(session), "hotspots": radar}
        controller.load(session)
        for name, page in pages.items():
            if name == "roundtable":
                controller.playback.live = True
                controller.playback.start(session)
                controller.next_step()
            page.resize(width, height)
            page.show()
            for _ in range(4):
                app.processEvents()
            image = output / f"{name}-{physical_width}x{physical_height}.png"
            assert page.grab().save(str(image)), str(image)
            if name == "hotspots":
                page.scroll.verticalScrollBar().setValue(page.scroll.verticalScrollBar().maximum())
                app.processEvents()
                assert page.grab().save(str(output / f"hotspots-general-{physical_width}x{physical_height}.png"))
                page.scroll.verticalScrollBar().setValue(0)
            buttons = []
            for button in page.findChildren(QPushButton):
                if button.isVisible():
                    rect = button.geometry()
                    position = button.mapTo(page, rect.topLeft() - rect.topLeft())
                    buttons.append({"text": button.text(), "x": position.x(), "y": position.y(), "w": rect.width(), "h": rect.height()})
            report.append({"page": name, "physical_screen": [physical_width, physical_height], "scale": scale, "requested": [width, height], "actual": [page.width(), page.height()], "buttons": buttons})
            page.hide()
            page.deleteLater()
        controller.shutdown()
        app.processEvents()
    (output / "layout.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([{key: row[key] for key in ("page", "requested", "actual")} for row in report], ensure_ascii=False))


if __name__ == "__main__":
    main()
