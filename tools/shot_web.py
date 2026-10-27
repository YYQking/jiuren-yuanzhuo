"""把 web-preview/index.html 用 QtWebEngine 渲染成 PNG，用来肉眼验收网页原型。

只做截图，不联网（页面自己读本地 data.js）。
用法：python artifacts/shot_web.py web-preview/index.html artifacts/shot-s1.png [--clicks N]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView


def main() -> int:
    page = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    clicks = 0
    if "--clicks" in sys.argv:
        clicks = int(sys.argv[sys.argv.index("--clicks") + 1])

    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.resize(1600, 1000)
    view.show()

    js = "document.body.click();" * 0

    def grab() -> None:
        # 点 N 次（模拟用户一条一条往前翻），再截。
        for _ in range(clicks):
            view.page().runJavaScript("document.body.click();")
        QTimer.singleShot(900, save)

    def save() -> None:
        view.grab().save(str(out))
        print(f"saved {out} ({out.stat().st_size} bytes)")
        app.quit()

    view.loadFinished.connect(lambda ok: QTimer.singleShot(1200, grab) if ok else (print("load failed"), app.quit()))
    view.load(QUrl.fromLocalFile(str(page)))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
