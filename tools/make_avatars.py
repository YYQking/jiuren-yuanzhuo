"""画八个事件席位的头像：单色版画的路子（墨线 + 平涂，不做写实肤色渐变）。

第一版是“圆脸 + 平直五官”，小尺寸下很像蜡像；这一版把重点放在：
头略微歪一点、眉一高一低、眼有眼睑线和高光、鼻子有明暗、头发有鬓角，
宁可“像木刻”也不“像照片”。
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "avatars"

INK = "#221a15"
PAPER = "#f2d7b6"        # 面（暖纸色，不用冷白）
PAPER_DARK = "#d9b58d"   # 面暗部
BLUSH = "#c9604f"
SCLERA = "#fdf6e8"

SEATS = [
    dict(
        role="qian", eye_gap=8.0, eye_size=4.4, jaw=0.92, base="#1e2d3c", robe="#2f4a63", trim="#c9a45c",
        hair="#e6e1d3", skin=PAPER, tilt=-3,
        brows=(-10, -4), eye=(0.92, 0.92), mouth=0.30, face=(1.02, 1.06),
        extra="beard_short", hairline=0.14,
    ),
    dict(
        role="kun", eye_gap=8.8, eye_size=4.9, jaw=1.08, base="#282820", robe="#7a5c3a", trim="#d8c49a",
        hair="#dcd6c8", skin=PAPER, tilt=2,
        brows=(-2, 2), eye=(0.88, 0.95), mouth=0.42, face=(1.06, 1.0),
        extra="bun_low", hairline=0.10,
    ),
    dict(
        role="zhen", eye_gap=8.2, eye_size=4.6, jaw=1.14, base="#1b2c24", robe="#2f6b45", trim="#a8c98f",
        hair="#1a1411", skin="#ecc79c", tilt=-2,
        brows=(16, 11), eye=(1.04, 1.04), mouth=-0.10, face=(1.0, 1.0),
        extra="hair_spike", hairline=0.12,
    ),
    dict(
        role="xun", eye_gap=7.6, eye_size=4.5, jaw=0.90, base="#1c2c30", robe="#2c7a72", trim="#9fd6c8",
        hair="#1c1611", skin="#efcca2", tilt=3,
        brows=(-8, 12), eye=(0.62, 0.98), mouth=0.52, face=(0.96, 1.0),
        extra="hair_swept", hairline=0.08,
    ),
    dict(
        role="kan", eye_gap=8.6, eye_size=4.2, jaw=0.86, base="#192236", robe="#243b5c", trim="#7f9dc4",
        hair="#16120f", skin="#d8b189", tilt=-1,
        brows=(12, 9), eye=(0.58, 0.58), mouth=-0.34, face=(0.98, 1.02),
        extra="hood", hairline=0.14,
    ),
    dict(
        role="li", eye_gap=8.6, eye_size=5.0, jaw=0.94, base="#381e23", robe="#8d2f3c", trim="#e6b96a",
        hair="#3a2118", skin="#f6d5b0", tilt=2,
        brows=(-13, -9), eye=(1.08, 1.08), mouth=0.26, face=(0.98, 1.02),
        extra="hair_up", hairline=0.02,
    ),
    dict(
        role="gen", eye_gap=9.2, eye_size=4.3, jaw=1.18, base="#242428", robe="#4a4a50", trim="#b9b2a2",
        hair="#1f1b17", skin="#e4bf95", tilt=-2,
        brows=(3, 3), eye=(0.80, 0.80), mouth=0.02, face=(1.14, 1.0),
        extra="cap", hairline=0.12,
    ),
    dict(
        role="dui", eye_gap=7.8, eye_size=5.1, jaw=1.02, base="#31223a", robe="#6d4a86", trim="#e0c07a",
        hair="#2a1a16", skin="#f8d9b6", tilt=1,
        brows=(-7, -5), eye=(1.14, 1.14), mouth=0.64, face=(1.06, 0.98),
        extra="twintail", hairline=0.06,
    ),
]


def _p(x: float, y: float) -> str:
    return f"{x:.1f} {y:.1f}"


def _eye(cx, cy, rx, ry, tilt, toward, lash) -> str:
    """眼：眼白 + 黑瞳 + 高光 + 上眼睑一道粗线，这是“有神”的关键。"""
    return "".join(
        [
            f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({tilt})">',
            f'<ellipse rx="{rx:.1f}" ry="{ry:.1f}" fill="{SCLERA}"/>',
            f'<ellipse cx="{toward * rx * 0.16:.1f}" cy="{ry * 0.1:.2f}" rx="{rx * 0.44:.1f}" ry="{ry * 0.78:.1f}" fill="{INK}"/>',
            f'<circle cx="{toward * rx * 0.16 + rx * 0.16:.2f}" cy="{-ry * 0.42:.2f}" r="{max(1.05, rx * 0.15):.1f}" fill="#ffffff" opacity="0.95"/>',
            f'<ellipse rx="{rx:.1f}" ry="{ry:.1f}" fill="none" stroke="{INK}" stroke-width="1.1"/>',
            f'<path d="M{-rx * 1.02:.1f} {-ry * 0.55:.1f} Q0 {-ry * 1.35:.1f} {rx * 1.02:.1f} {-ry * 0.62:.1f}" '
            f'fill="none" stroke="{INK}" stroke-width="{lash:.1f}" stroke-linecap="round"/>',
            "</g>",
        ]
    )


def _brow(cx, cy, length, angle, weight, color) -> str:
    half = length / 2
    x1, y1 = cx - half, cy + math.tan(math.radians(angle)) * half
    x2, y2 = cx + half, cy - math.tan(math.radians(angle)) * half
    mid = cy + abs(math.tan(math.radians(angle))) * half * 0.15
    return (
        f'<path d="M{_p(x1, y1)} Q{_p(cx, mid - 2.2)} {_p(x2, y2)}" fill="none" '
        f'stroke="{color}" stroke-width="{weight:.1f}" stroke-linecap="round"/>'
    )


def _mouth(cx, cy, width, curl) -> str:
    half = width / 2
    lift = curl * half * 0.42
    if curl >= 0:
        d = f"M{_p(cx - half, cy - lift * 0.5)} Q{_p(cx, cy + lift)} {_p(cx + half, cy - lift * 0.5)}"
    else:
        d = (
            f"M{_p(cx - half, cy + abs(lift) * 0.5)} "
            f"Q{_p(cx, cy - abs(lift))} {_p(cx + half, cy + abs(lift) * 0.5)}"
        )
    return (
        f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<path d="{_mouth_shadow(cx, cy, width, curl)}" fill="none" stroke="{PAPER_DARK}" '
        f'stroke-width="1" opacity="0.55" stroke-linecap="round"/>'
    )


def _mouth_shadow(cx, cy, width, curl) -> str:
    half = width / 2 * 0.8
    lift = curl * half * 0.32
    return f"M{_p(cx - half, cy + 2.0 + lift * 0.2)} Q{_p(cx, cy + 3.2 + lift)} {_p(cx + half, cy + 2.0 + lift * 0.2)}"


def _hair(style, color, fx, fy, hairline) -> str:
    """头发：有鬓角、有不齐的额发线，不要一整块“泳帽”。"""
    top = 62 - 26 * fy
    hair_y = top + 26 * hairline
    strands = []
    for i in range(5):
        t = -1 + 2 * i / 4
        strands.append(
            f'<path d="M{64 + t * 18 * fx:.1f} {hair_y:.1f} l{t * 2.2:.1f} 6.5" stroke="{INK}" '
            f'stroke-width="0.9" opacity="0.35" fill="none"/>'
        )
    cap = (
        f'<path d="M{64 - 25 * fx:.1f} {60:.1f} '
        f"Q{64 - 28 * fx:.1f} {top + 2:.1f} {64:.1f} {top - 2:.1f} "
        f"Q{64 + 28 * fx:.1f} {top + 2:.1f} {64 + 25 * fx:.1f} {60:.1f} "
        f"L{64 + 23 * fx:.1f} {hair_y + 2:.1f} "
        f"Q{64 + 8 * fx:.1f} {hair_y + 6.5:.1f} {64:.1f} {hair_y + 1.5:.1f} "
        f'Q{64 - 8 * fx:.1f} {hair_y + 6.5:.1f} {64 - 23 * fx:.1f} {hair_y + 2:.1f} Z" '
        f'fill="{color}" stroke="{INK}" stroke-width="1.5"/>'
    )
    sideburns = (
        f'<path d="M{64 - 25 * fx:.1f} 56 Q{64 - 28 * fx:.1f} 64 {64 - 22.5 * fx:.1f} 68" '
        f'fill="{color}" stroke="{INK}" stroke-width="1.3"/>'
        f'<path d="M{64 + 25 * fx:.1f} 56 Q{64 + 28 * fx:.1f} 64 {64 + 22.5 * fx:.1f} 68" '
        f'fill="{color}" stroke="{INK}" stroke-width="1.3"/>'
    )
    if style == "elder_male":
        return cap + sideburns + "".join(strands)
    if style == "elder_female":
        return cap + sideburns + "".join(strands)
    if style == "male":
        return cap + sideburns + "".join(strands)
    return cap + sideburns + "".join(strands)


def _extra(kind, color, trim, fx, fy) -> str:
    top = 62 - 26 * fy
    if kind == "bun_low":
        return (
            f'<ellipse cx="64" cy="{top + 2:.1f}" rx="10" ry="6.4" fill="{color}" '
            f'stroke="{INK}" stroke-width="1.2"/>'
            f'<circle cx="64" cy="{top - 6:.1f}" r="8.4" fill="{color}" '
            f'stroke="{INK}" stroke-width="1.3"/>'
            f'<path d="M57 {top - 5:.1f} q7 -5 14 0" fill="none" stroke="{trim}" '
            f'stroke-width="1.2" opacity="0.6"/>'
        )
    if kind == "hair_spike":
        pts = " ".join(
            f"{64 + (-1 + 2 * i / 6) * 22 * fx:.1f} {top + 2 - (3 if i % 2 == 0 else -1):.1f}" for i in range(7)
        )
        return (
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="4.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if kind == "hair_swept":
        return (
            f'<path d="M{64 - 24 * fx:.1f} {top + 12:.1f} Q{64 - 4:.1f} {top - 4:.1f} {64 + 24 * fx:.1f} {top + 8:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="4.2" stroke-linecap="round"/>'
        )
    if kind == "hood":
        # 兜帽只留肩上一圈领子，别把整个头罩成一头长发
        return (
            f'<path d="M{64 - 30 * fx:.1f} 104 Q{64 - 26 * fx:.1f} 88 {64:.1f} 87 '
            f'Q{64 + 26 * fx:.1f} 88 {64 + 30 * fx:.1f} 104 Z" fill="#1b2534" '
            f'stroke="{INK}" stroke-width="1.4"/>'
            f'<path d="M{64 - 26 * fx:.1f} 96 Q{64:.1f} 104 {64 + 26 * fx:.1f} 96" fill="none" '
            f'stroke="{trim}" stroke-width="1.6" opacity="0.7"/>'
        )
    if kind == "hair_up":
        return (
            f'<ellipse cx="64" cy="{top - 8:.1f}" rx="16" ry="9.5" fill="{color}" stroke="{INK}" stroke-width="1.4"/>'
            f'<path d="M{_p(51, top - 10)} L{_p(64, top - 24)} L{_p(77, top - 10)} Z" fill="{color}" '
            f'stroke="{INK}" stroke-width="1.3"/>'
            f'<path d="M{_p(64, top - 22)} L{_p(64, top - 12)}" stroke="{trim}" stroke-width="1.6" stroke-linecap="round"/>'
        )
    if kind == "cap":
        return (
            f'<path d="M{64 - 27 * fx:.1f} 52 Q{64 - 27 * fx:.1f} {top - 8:.1f} {64:.1f} {top - 10:.1f} '
            f'Q{64 + 27 * fx:.1f} {top - 8:.1f} {64 + 27 * fx:.1f} 52 Z" fill="{color}" '
            f'stroke="{INK}" stroke-width="1.5"/>'
            f'<path d="M{64 - 30 * fx:.1f} 50 h{60 * fx:.1f} v5.5 h{-60 * fx:.1f} Z" fill="{color}" '
            f'stroke="{INK}" stroke-width="1.4"/>'
            f'<path d="M{64 - 6:.1f} {top - 8:.1f} q6 -3 12 0" fill="none" stroke="{trim}" stroke-width="1.4"/>'
        )
    if kind == "twintail":
        return (
            f'<circle cx="{64 - 27 * fx:.1f}" cy="66" r="8.6" fill="{color}" stroke="{INK}" stroke-width="1.3"/>'
            f'<circle cx="{64 + 27 * fx:.1f}" cy="66" r="8.6" fill="{color}" stroke="{INK}" stroke-width="1.3"/>'
            f'<circle cx="{64 - 27 * fx:.1f}" cy="66" r="3.2" fill="{trim}" opacity="0.5"/>'
            f'<circle cx="{64 + 27 * fx:.1f}" cy="66" r="3.2" fill="{trim}" opacity="0.5"/>'
        )
    if kind == "beard_short":
        return (
            f'<path d="M{64 - 15:.1f} 85 Q{64 - 11:.1f} 92 {64:.1f} 92.5 '
            f'Q{64 + 11:.1f} 92 {64 + 15:.1f} 85" fill="{color}" opacity="0.95" '
            f'stroke="{INK}" stroke-width="0.7"/>'
            f'<path d="M{64 - 15:.1f} 85 q4 -1.6 8 0 M{64 + 7:.1f} 85 q4 -1.6 8 0" fill="none" '
            f'stroke="{INK}" stroke-width="1" opacity="0.5"/>'
        )
    return ""


def build_svg(seat: dict) -> str:
    fx, fy = seat["face"]
    skin = seat["skin"]
    hair_color = seat["hair"]
    robe, trim, base = seat["robe"], seat["trim"], seat["base"]
    eye_l, eye_r = seat["eye"]
    brow_l, brow_r = seat["brows"]
    style = seat["style_label"] if "style_label" in seat else (
        "elder_male" if seat["role"] == "qian" else
        "elder_female" if seat["role"] == "kun" else
        "female" if seat["role"] in {"li", "dui"} else "male"
    )
    tilt = seat["tilt"]
    jaw = seat.get("jaw", 1.0)

    head_cx, head_cy = 64.0, 67.0
    head_rx, head_ry = 22.0 * fx, 25.5 * fy
    eye_y = head_cy - 3.0
    eye_dx = seat["eye_gap"] * fx
    eye_rx = seat["eye_size"]
    eye_ry_l = eye_rx * 0.66 * eye_l
    eye_ry_r = eye_rx * 0.66 * eye_r

    hatch = "".join(
        f'<line x1="{-40 + i * 12}" y1="0" x2="{-40 + i * 12 + 160}" y2="160" '
        f'stroke="#ffffff" stroke-width="1" opacity="0.03"/>'
        for i in range(16)
    )

    # 帽子把头遮住的那位，就不再画头发了，否则一坨黑压到眉毛上
    hat = seat["extra"] == "cap"
    behind = []

    head = [
        *behind,
        # 脖子
        f'<path d="M54 82 L54 96 Q64 101 74 96 L74 82 Z" fill="{PAPER_DARK}" stroke="{INK}" stroke-width="1.3"/>',
        # 耳
        f'<ellipse cx="{64 - head_rx - 1:.1f}" cy="{head_cy + 2:.1f}" rx="3.2" ry="5.0" fill="{skin}" stroke="{INK}" stroke-width="1.3"/>',
        f'<ellipse cx="{64 + head_rx + 1:.1f}" cy="{head_cy + 2:.1f}" rx="3.2" ry="5.0" fill="{skin}" stroke="{INK}" stroke-width="1.3"/>',
        # 脸
        (
            f'<path d="M{64 - head_rx:.1f} {head_cy - 11:.1f} '
            f"Q{64 - head_rx * jaw:.1f} {head_cy + head_ry * 0.66:.1f} {head_cx:.1f} {head_cy + head_ry:.1f} "
            f"Q{64 + head_rx * jaw:.1f} {head_cy + head_ry * 0.66:.1f} {64 + head_rx:.1f} {head_cy - 11:.1f} "
            f"Q{64 + head_rx * 0.92:.1f} {head_cy - head_ry:.1f} {head_cx:.1f} {head_cy - head_ry - 1:.1f} "
            f'Q{64 - head_rx * 0.92:.1f} {head_cy - head_ry:.1f} {64 - head_rx:.1f} {head_cy - 11:.1f} Z" '
            f'fill="{skin}" stroke="{INK}" stroke-width="1.7"/>'
        ),
        # 一侧脸暗部（光从左上来）
        f'<path d="M{64 + head_rx * 0.55:.1f} {head_cy - head_ry * 0.55:.1f} '
        f'Q{64 + head_rx:.1f} {head_cy + head_ry * 0.2:.1f} {64 + head_rx * 0.35:.1f} {head_cy + head_ry * 0.92:.1f}" '
        f'fill="{PAPER_DARK}" opacity="0.28"/>',
        # 腮红
        f'<ellipse cx="{64 - 12.5 * fx:.1f}" cy="{head_cy + 7:.1f}" rx="6.0" ry="3.8" fill="{BLUSH}" opacity="0.26"/>',
        f'<ellipse cx="{64 + 12.5 * fx:.1f}" cy="{head_cy + 7:.1f}" rx="6.0" ry="3.8" fill="{BLUSH}" opacity="0.30"/>',
        _eye(64 - eye_dx, eye_y, eye_rx, eye_ry_l, -5, -1, 1.6 if style != "female" else 1.9),
        _eye(64 + eye_dx, eye_y, eye_rx, eye_ry_r, 5, 1, 1.7 if style != "female" else 2.0),
        _brow(64 - eye_dx, eye_y - eye_ry_l - 5.4, 11.0 * fx, brow_l, 2.5, hair_color),
        _brow(64 + eye_dx, eye_y - eye_ry_r - 5.4, 11.0 * fx, brow_r, 2.5, hair_color),
        # 鼻：一笔竖线 + 一点鼻翼阴影
        f'<path d="M{64 - 0.6:.1f} {head_cy + 1:.1f} q2.2 4.4 -0.8 5.6" fill="none" stroke="{PAPER_DARK}" '
        f'stroke-width="1.7" stroke-linecap="round"/>',
        f'<ellipse cx="{64 - 2.6:.1f}" cy="{head_cy + 6.6:.1f}" rx="1.5" ry="0.9" fill="{PAPER_DARK}" opacity="0.7"/>',
        *([_extra("beard_short", hair_color, trim, fx, fy)] if seat["extra"] == "beard_short" else []),
        _mouth(64, head_cy + 13.6, 10.0, seat["mouth"]),
        # 下巴一点线
        f'<path d="M{64 - 5:.1f} {head_cy + head_ry - 3:.1f} q5 2.6 10 0" fill="none" stroke="{PAPER_DARK}" '
        f'stroke-width="1" opacity="0.45"/>',
        *([] if hat else [_hair(style, hair_color, fx, fy, seat["hairline"])]),
        *([] if seat["extra"] in {"hood", "beard_short"} else [_extra(seat["extra"], hair_color, trim, fx, fy)]),
    ]

    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="256" height="256">',
            "<defs>",
            '<clipPath id="round"><circle cx="64" cy="64" r="64"/></clipPath>',
            "</defs>",
            '<g clip-path="url(#round)">',
            f'<rect width="128" height="128" fill="{base}"/>',
            hatch,
            f'<circle cx="64" cy="74" r="54" fill="#000000" opacity="0.20"/>',
            # 肩与衣
            f'<path d="M2 128 Q16 96 45 89 L83 89 Q114 96 126 128 Z" fill="{robe}" stroke="{INK}" stroke-width="1.7"/>',
            f'<path d="M45 89 L64 104 L83 89" fill="none" stroke="{trim}" stroke-width="2.6"/>',
            f'<path d="M52 91 Q64 99 76 91" fill="none" stroke="{INK}" stroke-width="1" opacity="0.45"/>',
            f'<g transform="rotate({tilt:.1f} 64 78)">',
            *head,
            "</g>",
            "</g>",
            "</svg>",
        ]
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for seat in SEATS:
        (OUT / f"{seat['role']}.svg").write_text(build_svg(seat), encoding="utf-8")
    print(f"wrote {len(SEATS)} avatars to {OUT}")


if __name__ == "__main__":
    main()
