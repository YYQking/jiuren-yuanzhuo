"""Render ``docs/使用说明-详细版.md`` into the plain-text manual shipped in the package.

Windows 记事本把没有 BOM 的 UTF-8 当成 ANSI，中文会变乱码，所以输出始终带 BOM。
表格转成"单元格 · 单元格"一行，避免纯文本里出现一堆竖线。

用法：python tools/build_manual_txt.py [输出路径]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "使用说明-详细版.md"
DEFAULT_TARGET = Path(r"C:\Users\14726\Desktop\九人圆桌热点版") / "使用说明.txt"
WRAP = 44


def _inline(text: str) -> str:
    text = text.replace("`", "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1（\2）", text)
    return text.strip()


NO_LINE_START = "，。、；：！？）】」』’”…%"


def _wrap(text: str, width: int = WRAP) -> list[str]:
    """Wrap a Chinese paragraph by characters, never starting a line with punctuation."""
    text = text.strip()
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        if len(current) >= width and char not in NO_LINE_START:
            lines.append(current.rstrip())
            current = char
        else:
            current += char
    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


def render(markdown: str) -> str:
    blocks: list[str] = []
    table_rows: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.extend(_wrap(_inline("".join(paragraph))))
            paragraph.clear()

    def flush_table() -> None:
        if table_rows:
            for row in table_rows:
                cells = [_inline(cell) for cell in row.strip().strip("|").split("|")]
                blocks.append(" · ".join(cell for cell in cells if cell))
            table_rows.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            flush_paragraph()
            if set(line.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
                continue
            table_rows.append(line)
            continue
        flush_table()
        if not line.strip():
            flush_paragraph()
            blocks.append("")
            continue
        if line.startswith("# "):
            flush_paragraph()
            blocks.append(_inline(line[2:]))
            blocks.append("=" * 60)
            continue
        if line.startswith("## "):
            flush_paragraph()
            blocks.append("")
            blocks.append("=" * 60)
            blocks.append(_inline(line[3:]))
            blocks.append("=" * 60)
            continue
        if line.startswith("### "):
            flush_paragraph()
            blocks.append("")
            blocks.append(_inline(line[4:]))
            blocks.append("-" * 60)
            continue
        if line.startswith("---"):
            flush_paragraph()
            continue
        ordered = re.match(r"^(\s*)(\d+)[.、)]\s+(.*)$", line)
        if ordered:
            flush_paragraph()
            depth = len(ordered.group(1)) // 2
            prefix = "  " * depth
            head = f"{ordered.group(2)}. "
            wrapped = _wrap(_inline(ordered.group(3)), WRAP - len(prefix) - len(head))
            blocks.append(prefix + head + wrapped[0])
            blocks.extend(prefix + " " * len(head) + extra for extra in wrapped[1:])
            continue
        bullet = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if bullet:
            flush_paragraph()
            depth = len(bullet.group(1)) // 2
            prefix = "  " * depth
            wrapped = _wrap(_inline(bullet.group(2)), WRAP - len(prefix))
            blocks.append(prefix + "· " + wrapped[0])
            blocks.extend(prefix + "  " + extra for extra in wrapped[1:])
            continue
        paragraph.append(line.strip())

    flush_paragraph()
    flush_table()

    while blocks and not blocks[-1].strip():
        blocks.pop()
    return "\n".join(blocks) + "\n"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET
    markdown = SOURCE.read_text(encoding="utf-8")
    text = render(markdown)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8-sig", newline="\r\n") as handle:
        handle.write(text)
    print(f"wrote {target} ({len(text.encode('utf-8'))} bytes, BOM yes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
