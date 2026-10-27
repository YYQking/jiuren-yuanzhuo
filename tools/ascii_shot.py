"""把截图变成字符画，让我（看不了图片的模型）也能"看见"大致构图。

按亮度出字符，再按色相打标记：
  Y = 偏金   R = 偏红   G = 偏绿绒   （无色相可判时只出亮度字符）
用法：python tools/ascii_shot.py artifacts/shot-casino-6.png [宽]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

RAMP = " .:-=+*#%@"


def main() -> int:
    path = Path(sys.argv[1])
    cols = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 110
    img = Image.open(path).convert("RGB")
    crop = None
    for arg in sys.argv[2:]:
        if arg.startswith("--box"):
            crop = [int(v) for v in arg.split("=", 1)[1].split(",")]
    if crop:
        img = img.crop(tuple(crop))
    w, h = img.size
    rows = max(1, int(cols * h / w * 0.5))  # 字符高宽比约 2:1

    px = img.load()
    out = []
    for ry in range(rows):
        line = []
        for rx in range(cols):
            x0 = int(rx * w / cols)
            x1 = max(x0 + 1, int((rx + 1) * w / cols))
            y0 = int(ry * h / rows)
            y1 = max(y0 + 1, int((ry + 1) * h / rows))
            rs = gs = bs = n = 0
            for y in range(y0, y1, max(1, (y1 - y0) // 3 or 1)):
                for x in range(x0, x1, max(1, (x1 - x0) // 3 or 1)):
                    r, g, b = px[x, y]
                    rs += r; gs += g; bs += b; n += 1
            r, g, b = rs / n, gs / n, bs / n
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            ch = RAMP[min(len(RAMP) - 1, int(lum / 255 * len(RAMP)))]
            if lum > 120 and r > 140 and r > b + 30 and g > 95:
                ch = "Y"
            elif r > 80 and r > g + 35 and r > b + 30:
                ch = "R"
            elif g > r + 14 and g > b + 8:
                ch = "G" if lum < 110 else "g"
            line.append(ch)
        out.append("".join(line))

    print(f"# {path.name}  {w}x{h}  ({cols}x{rows})")
    for i, line in enumerate(out):
        print(f"{i:02d}|{line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
