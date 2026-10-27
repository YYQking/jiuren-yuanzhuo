"""把 web-preview/index.html 用 QtWebEngine 渲染成 PNG，用来肉眼验收网页原型。

只做截图，不联网（页面自己读本地 data.js）。
用法：python tools/shot_web.py web-preview/index.html artifacts/shot-s1.png [--clicks N]

截图前会关掉所有过渡/动画并等一帧，否则同一组点击在不同时刻截出来亮度都不一样，
像素检查就会误报。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

FREEZE = (
    "(() => { const s = document.createElement('style');"
    " s.textContent = '*,*::before,*::after{transition:none!important;animation:none!important}';"
    " document.head.appendChild(s); return 1; })()"
)


def main() -> int:
    page = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    clicks = 0
    if "--clicks" in sys.argv:
        clicks = int(sys.argv[sys.argv.index("--clicks") + 1])

    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    size = (1600, 1000)
    if "--size" in sys.argv:
        w, h = sys.argv[sys.argv.index("--size") + 1].lower().split("x")
        size = (int(w), int(h))
    view.resize(*size)
    view.show()

    def step(i: int) -> None:
        # 一次一次点，给每次点击留出过场时间，保证截到的是"停住"的那一帧
        if i >= clicks:
            QTimer.singleShot(1200, run_extra)
            return
        view.page().runJavaScript("document.body.click();")
        QTimer.singleShot(150, lambda: step(i + 1))

    def run_extra() -> None:
        # --js "..."：截图前先跑一段脚本（比如点一下「发牌」）
        if "--js" in sys.argv:
            view.page().runJavaScript(sys.argv[sys.argv.index("--js") + 1])
        QTimer.singleShot(1200, freeze)

    def freeze() -> None:
        view.page().runJavaScript(FREEZE)
        QTimer.singleShot(250, save)

    def save() -> None:
        view.grab().save(str(out))
        print(f"saved {out} ({out.stat().st_size} bytes)")
        app.quit()

    view.loadFinished.connect(lambda ok: QTimer.singleShot(1200, lambda: step(0)) if ok else (print("load failed"), app.quit()))
    view.load(QUrl.fromLocalFile(str(page)))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
