"""截 Qt 大厅（发牌式）的图，验证版式与卡片位置。

用法：
    python tools/shot_lobby.py artifacts/shot-lobby-qt-1.png
    python tools/shot_lobby.py artifacts/shot-lobby-qt-2.png --dealt --section event
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from brainstorm.qt_app import MainWindow  # noqa: E402
from brainstorm.qt_theme import app_stylesheet  # noqa: E402
from brainstorm.storage import SessionStore  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/shot-lobby-qt.png")
    dealt = "--dealt" in sys.argv
    section = "business"
    if "--section" in sys.argv:
        section = sys.argv[sys.argv.index("--section") + 1]
    width, height = 1536, 864
    if "--size" in sys.argv:
        w, h = sys.argv[sys.argv.index("--size") + 1].lower().split("x")
        width, height = int(w), int(h)

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(app_stylesheet())
    window = MainWindow()
    window.store = SessionStore(Path("artifacts/shot-lobby-store") / "sessions.json")
    window.showNormal()
    window.resize(width, height)
    window.show()
    app.processEvents()

    lobby = window.lobby
    lobby.set_mode(section)
    app.processEvents()
    if dealt:
        lobby._deal()
        app.processEvents()
        # 让发牌动画走完
        for _ in range(400):
            app.processEvents()
            if not lobby._animations:
                break
            QApplication.instance().thread().msleep(10)

    app.processEvents()
    window.grab().save(str(out))
    print("saved", out, window.size())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
