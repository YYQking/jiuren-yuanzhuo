"""把一场真实跑测的讨论导出成网页原型用的假数据（web-preview/data.js）。

原型只做交互演示：不联网、不调用模型、不带任何密钥。数据来源是本地已经存在的
artifacts/real-event-3 记录，旧席位名会在导出时换成现在的新名字。

用法：
    python tools/build_web_demo_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brainstorm.roles import EVENT_ROLES, face_label  # noqa: E402

SOURCE = ROOT / "artifacts" / "real-event-3" / "real-20261027-001850.json"
OUTPUT = ROOT / "web-preview" / "data.js"

# 2026-10-26 那场跑测用的是旧绰号，导出时换成现在的名字。
OLD_TO_NEW = {
    "天哥": "乾明",
    "地姐": "坤兰",
    "雷子": "震山",
    "风姐": "巽竹",
    "水哥": "坎川",
    "火姐": "离霞",
    "山哥": "艮石",
    "泽妹": "兑溪",
}


def build(record: dict) -> dict:
    seats = [
        {
            "id": role.id,
            "name": role.name,
            "trigram": role.trigram,
            "duty": role.duty,
            "color": role.color,
            "yang": role.yang,
            "yin": role.yin,
        }
        for role in EVENT_ROLES
    ]
    turns = []
    for index, item in enumerate(record.get("utterances", [])):
        name = OLD_TO_NEW.get(item.get("speaker_name", ""), item.get("speaker_name", ""))
        turns.append(
            {
                "index": index,
                "speaker_id": item.get("speaker_id", ""),
                "speaker_name": name,
                "face": item.get("face") or "",
                "intent": item.get("intent") or "",
                "phase": item.get("phase") or "",
                "kind": item.get("kind") or "",
                "content": (item.get("content") or "").strip(),
                "replies_to": item.get("replies_to"),
                "stance_change": bool(item.get("stance_change")),
            }
        )
    return {
        "topic": record.get("topic", ""),
        "section": "event",
        "section_label": "八卦桌 · 事件讨论",
        "seats": seats,
        "turns": turns,
        "face_labels": {"yang": face_label("yang"), "yin": face_label("yin")},
    }


def main() -> int:
    record = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload = build(record)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    OUTPUT.write_text(
        "// 由 tools/build_web_demo_data.py 生成，别手改。\n"
        "// 数据来自一场真实跑测，只用于网页原型的交互演示。\n"
        f"window.DEMO = {body};\n",
        encoding="utf-8",
    )
    print(f"写出 {OUTPUT.relative_to(ROOT)}：{len(payload['turns'])} 条发言，{len(payload['seats'])} 个席位")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
