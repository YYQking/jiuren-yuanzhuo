"""确认桌面正中的烫金字真的画出来了。

判定方式：比较"桌面正中那块椭圆"和"外圈一圈绿绒"的平均亮度。
字是亮的、绒面是暗的，字画出来时中心区明显更亮（而且金色像素更多）。
只看单个像素的亮度阈值不可靠——22px 的细宋体笔画大量是抗锯齿的半亮像素。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def lum(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def mean_lum(px, box) -> float:
    total = n = 0
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            total += lum(px[x, y])
            n += 1
    return total / max(1, n)


def gold_ratio(px, box) -> float:
    hit = n = 0
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            r, g, b = px[x, y]
            n += 1
            if r > 150 and g > 120 and (r - b) > 35 and g > b:
                hit += 1
    return hit / max(1, n)


def main() -> int:
    path = Path(sys.argv[1])
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    # 桌面中心：竖排题款 + 印章都落在正中一小块方区里
    cx = w // 2
    cy = int(h * 0.40)
    inner = (cx - 44, cy - 38, cx + 44, cy + 34)
    # 外圈同一高度、偏左偏右的绿绒（避开字）
    left = (cx - 300, cy - 38, cx - 220, cy + 34)
    right = (cx + 220, cy - 38, cx + 300, cy + 34)

    mi = mean_lum(px, inner)
    mb = (mean_lum(px, left) + mean_lum(px, right)) / 2
    gi = gold_ratio(px, inner)
    gb = (gold_ratio(px, left) + gold_ratio(px, right)) / 2

    print(f"中心区: 平均亮度 {mi:.1f}  金色占比 {gi * 100:.2f}%")
    print(f"绿绒基线: 平均亮度 {mb:.1f}  金色占比 {gb * 100:.2f}%")
    print(f"亮度差 {mi - mb:+.1f}   金色占比差 {(gi - gb) * 100:+.2f} 个百分点")

    ok = (mi - mb) > 6 and (gi - gb) > 0.004
    print("VERDICT:", "中心有烫金字" if ok else "中心看不出字——要么没渲染，要么太暗")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
