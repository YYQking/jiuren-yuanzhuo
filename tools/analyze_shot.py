"""看一眼截图到底画出了什么（不做审美判断，只做像素事实核对）。

用来防止"页面是白屏/全黑但文件很大"这种自欺：直接数颜色。
用法：python tools/analyze_shot.py artifacts/shot-casino-6.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def pct(count: int, total: int) -> float:
    return round(count * 100.0 / max(1, total), 2)


def main() -> int:
    path = Path(sys.argv[1])
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    total = w * h
    green = gold = dark = bright = 0

    # 只看桌面所在的中间区域，避免顶栏/卡片干扰
    x0, x1 = int(w * 0.28), int(w * 0.72)
    y0, y1 = int(h * 0.18), int(h * 0.68)
    center_total = (x1 - x0) * (y1 - y0)
    center_green = 0

    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if g > r + 12 and g > b + 12 and g > 45:
                green += 1
                if x0 <= x < x1 and y0 <= y < y1:
                    center_green += 1
            if r > 150 and g > 110 and b < 120 and r > b + 40:
                gold += 1
            if r + g + b < 70:
                dark += 1
            if r + g + b > 460:
                bright += 1

    # 中央区域应有一块明显的绿绒
    cx, cy = w // 2, int(h * 0.43)
    print(f"size: {w}x{h}")
    print(f"center pixel: {px[cx, cy]}")
    print(f"green(整图): {pct(green, total)}%   绿绒(中央区域): {pct(center_green, center_total)}%")
    print(f"gold(整图): {pct(gold, total)}%    dark(整图): {pct(dark, total)}%    bright: {pct(bright, total)}%")

    ok = center_green / max(1, center_total) > 0.18 and gold > 400
    print("VERDICT:", "绿绒与金边都画出来了" if ok else "中央没看到足够绿绒，或金边缺失——需要看截图")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
