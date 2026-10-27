"""用 document.title 当回传通道：runJavaScript 的回调在这套环境里不稳，
但 titleChanged 是 Qt 信号，稳。JS 把测量结果写进 title，Python 收到就打印。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

JS = r"""
(() => {
  const out = {};
  const el = document.getElementById('platePhase');
  const box = (n) => { if (!n) return null; const b = n.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
  out.text = el ? JSON.stringify(el.textContent) : null;
  out.spanBox = box(el);
  out.plaqueBox = box(document.querySelector('.plaque'));
  out.sealBox = box(document.querySelector('.seal'));
  out.potBox = box(document.querySelector('.pot'));
  out.tableBox = box(document.querySelector('.table'));
  if (el) {
    const s = getComputedStyle(el);
    out.style = { color: s.color, display: s.display, fontSize: s.fontSize,
                  opacity: s.opacity, visibility: s.visibility,
                  background: s.backgroundImage.slice(0, 24), fill: s.webkitTextFillColor };
  }
  out.speechBox = box(document.querySelector('.speech'));
  out.seatCount = document.querySelectorAll('.seat').length;
  out.chipCount = document.querySelectorAll('.pot-chips i').length;
  document.title = 'PROBE:' + JSON.stringify(out);
  return 1;
})()
"""


def main() -> int:
    page_path = Path(sys.argv[1]).resolve()
    clicks = int(sys.argv[sys.argv.index("--clicks") + 1]) if "--clicks" in sys.argv else 6

    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.resize(1600, 1000)
    view.show()

    got = {"n": 0}

    def on_title(title: str) -> None:
        if title.startswith("PROBE:"):
            got["n"] += 1
            print(title[6:])
            if got["n"] >= 1:
                QTimer.singleShot(200, app.quit)

    view.page().titleChanged.connect(on_title)

    def after_load(ok: bool) -> None:
        if not ok:
            print("LOAD FAILED")
            app.quit()
            return
        QTimer.singleShot(600, click_some)

    def click_some() -> None:
        def loop(i: int) -> None:
            view.page().runJavaScript("document.body.click();")
            if i + 1 < clicks:
                QTimer.singleShot(140, lambda: loop(i + 1))
            else:
                QTimer.singleShot(500, lambda: view.page().runJavaScript(JS))
        loop(0)

    view.loadFinished.connect(after_load)
    view.load(QUrl.fromLocalFile(str(page_path)))
    QTimer.singleShot(15000, lambda: (print("TIMEOUT"), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
