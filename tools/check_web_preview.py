"""静态校验网页原型：数据能解析、头像齐、DOM 引用对得上。"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "web-preview"


def main() -> int:
    raw = (PREVIEW / "data.js").read_text(encoding="utf-8")
    data = json.loads(raw.split("=", 1)[1].strip().rstrip(";").strip())
    seats = data["seats"]
    turns = data["turns"]
    print("seats:", len(seats), [s["name"] for s in seats])
    print("turns:", len(turns))
    print("faces:", sorted({t.get("face") for t in turns if t.get("face")}))
    print("phases:", [t["phase"] for t in turns])
    print("speakers:", len({t["speaker_name"] for t in turns}))

    missing_avatars = [s["id"] for s in seats
                       if not (ROOT / "assets" / "avatars" / f"{s['id']}.svg").exists()]
    print("missing avatars:", missing_avatars or "none")

    for name in ("index.html", "style.css", "stage.js", "data.js"):
        path = PREVIEW / name
        print(f"{name}: {path.stat().st_size} bytes")

    html = (PREVIEW / "index.html").read_text(encoding="utf-8")
    script = (PREVIEW / "stage.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    wanted = {m.strip("\"'") for m in re.findall(r"""getElementById\((['"][^'"]+['"])\)""", script)}
    print("dom ids referenced:", len(wanted), "in html:", len(ids))
    print("missing dom ids:", sorted(wanted - ids) or "none")
    print("unused dom ids:", sorted(ids - wanted) or "none")

    # 引用完整性：index.html 里出现的本地文件都得存在
    refs = set(re.findall(r'(?:src|href)="\.\./([^"]+)"', html)) | set(
        re.findall(r'(?:src|href)="([^"]+)"', html))
    refs = {r for r in refs if not r.startswith(("http", "#", "data:"))}
    missing_refs = [r for r in refs if not (PREVIEW / r).exists()]
    print("missing refs:", missing_refs or "none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
