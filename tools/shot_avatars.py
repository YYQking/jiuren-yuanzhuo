"""把八个头像拼成一张对照图，方便一次看全。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
ORDER = ["qian", "kun", "zhen", "xun", "kan", "li", "gen", "dui"]
NAMES = {
    "qian": ("乾明", "乾 · 天"),
    "kun": ("坤兰", "坤 · 地"),
    "zhen": ("震山", "震 · 雷"),
    "xun": ("巽竹", "巽 · 风"),
    "kan": ("坎川", "坎 · 水"),
    "li": ("离霞", "离 · 火"),
    "gen": ("艮石", "艮 · 山"),
    "dui": ("兑溪", "兑 · 泽"),
}


def build_html() -> str:
    cells = []
    for key in ORDER:
        name, gua = NAMES[key]
        cells.append(
            f'<figure><img src="../assets/avatars/{key}.svg" alt="{name}">'
            f"<figcaption><b>{name}</b><span>{gua}</span></figcaption></figure>"
        )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{{margin:0;height:100%;background:#0b0a08;
      font-family:"PingFang SC","Microsoft YaHei",sans-serif;}}
    .wrap{{display:grid;grid-template-columns:repeat(4,1fr);gap:26px;padding:34px;}}
    figure{{margin:0;display:flex;flex-direction:column;align-items:center;gap:12px;}}
    img{{width:150px;height:150px;border-radius:50%;
      box-shadow:0 12px 30px rgba(0,0,0,.6),0 0 0 1px rgba(201,164,92,.22);}}
    figcaption{{display:flex;flex-direction:column;align-items:center;gap:3px;}}
    b{{font-family:"Songti SC","SimSun",serif;font-weight:400;font-size:16px;color:#efe7d7;}}
    span{{font-size:10px;letter-spacing:.14em;color:rgba(201,164,92,.7);}}
    </style></head><body><div class="wrap">{''.join(cells)}</div></body></html>"""


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "artifacts" / "avatars.png")
    page = ROOT / "artifacts" / "_avatars_preview.html"
    page.write_text(build_html(), encoding="utf-8")

    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.resize(QSize(760, 480))
    view.show()

    def shoot() -> None:
        view.grab().save(str(out))
        print(f"saved {out}")
        app.quit()

    view.loadFinished.connect(lambda ok: QTimer.singleShot(900, shoot))
    view.load(QUrl.fromLocalFile(str(page)))
    app.exec()


if __name__ == "__main__":
    main()
