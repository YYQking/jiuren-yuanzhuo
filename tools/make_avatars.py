"""画八个事件席位的头像（128×128 SVG）。

不是照岗位画，是照"这个人"画：乾明是老派长辈、坤兰是记事的阿姨、
震山是火气大的长子、巽竹是消息灵通的姐姐、坎川是抽着烟挑毛病的二儿子、
离霞是场子里最抢眼的二女儿、艮石是不爱说话的小儿子、兑溪是一开口就撒娇的小女儿。

一致的地方：同一块深色圆底、同一个头肩比例、同一套眼睛和嘴的画法。
不一样的地方：脸型、发型、眉眼角度、衣服、随身的小东西。
"""

from __future__ import annotations

from pathlib import Path

PLATE = "#141a22"
INK = "#241f1c"

# 脸的位置：一圈头肩像，头略偏上
HEAD_CY = 53
HEAD_RX = 22
HEAD_RY = 25


def svg(body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" '
        'role="img" aria-hidden="true">\n'
        "<defs>\n"
        '<radialGradient id="bg" cx="50%" cy="32%" r="74%">\n'
        '<stop offset="0%" stop-color="#27323f"/><stop offset="100%" stop-color="' + PLATE + '"/>\n'
        "</radialGradient>\n"
        '<linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">\n'
        '<stop offset="0%" stop-color="#000" stop-opacity="0.05"/>\n'
        '<stop offset="100%" stop-color="#000" stop-opacity="0.34"/>\n'
        "</linearGradient>\n"
        '<radialGradient id="warm" cx="50%" cy="50%" r="50%">\n'
        '<stop offset="0%" stop-color="#f0d9a6" stop-opacity="0.20"/>\n'
        '<stop offset="100%" stop-color="#f0d9a6" stop-opacity="0"/>\n'
        "</radialGradient>\n"
        "</defs>\n"
        '<circle cx="64" cy="64" r="63" fill="url(#bg)"/>\n'
        '<circle cx="64" cy="58" r="46" fill="url(#warm)"/>\n'
        '<circle cx="64" cy="64" r="62.2" fill="none" stroke="#c9a45c" stroke-opacity="0.26"/>\n'
        f"{body}\n"
        "</svg>\n"
    )


def _dark(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def shoulders(color: str, collar: str | None = None) -> str:
    """肩膀 + 领口：所有角色共用这个轮廓，靠颜色区分。"""
    out = [
        f'<path d="M12 128c3-31 25-46 52-46s49 15 52 46z" fill="{color}"/>',
        f'<path d="M12 128c3-31 25-46 52-46s49 15 52 46z" fill="url(#shade)"/>',
    ]
    if collar:
        out.append(f'<path d="M52 84l12 17 12-17-12-4z" fill="{collar}"/>')
    return "\n".join(out)


def neck(skin: str) -> str:
    return f'<path d="M55 74h18v15a9 9 0 0 1-18 0z" fill="{_dark(skin, 0.86)}"/>'


def head(skin: str) -> str:
    """脸 + 耳朵 + 一点腮红和下巴阴影，别做成一张白纸。"""
    cy = HEAD_CY
    return "\n".join(
        [
            f'<circle cx="{64 - HEAD_RX}" cy="{cy + 3}" r="4.6" fill="{_dark(skin, 0.94)}"/>',
            f'<circle cx="{64 + HEAD_RX}" cy="{cy + 3}" r="4.6" fill="{_dark(skin, 0.94)}"/>',
            f'<ellipse cx="64" cy="{cy}" rx="{HEAD_RX}" ry="{HEAD_RY}" fill="{skin}"/>',
            f'<ellipse cx="52" cy="{cy + 9}" rx="6.5" ry="4" fill="{_dark(skin, 0.93)}" opacity="0.55"/>',
            f'<ellipse cx="76" cy="{cy + 9}" rx="6.5" ry="4" fill="{_dark(skin, 0.93)}" opacity="0.55"/>',
            f'<ellipse cx="64" cy="{cy + 17}" rx="12" ry="4.5" fill="#000" opacity="0.10"/>',
        ]
    )


def eye(cx: int, cy: int = 51, wide: bool = False, closed_smile: bool = False) -> str:
    if closed_smile:
        return (
            f'<path d="M{cx - 6} {cy + 1.6}q6-7 12 0" fill="none" stroke="{INK}" '
            'stroke-width="2.3" stroke-linecap="round"/>'
        )
    rx, ry = (5.2, 4.9) if wide else (4.6, 4.4)
    return (
        f'<path d="M{cx - rx - 1.4} {cy - ry * 0.9}q{rx + 1.4} -2.4 {rx * 2 + 2.8} 0" '
        f'fill="none" stroke="{INK}" stroke-width="1.6" stroke-linecap="round" stroke-opacity="0.75"/>'
        f'<ellipse cx="{cx}" cy="{cy + 0.6}" rx="{rx}" ry="{ry}" fill="{INK}"/>'
        f'<circle cx="{cx + 1.2}" cy="{cy - 1.2}" r="1.1" fill="#fff" fill-opacity="0.92"/>'
    )


def brows(tilt: float = 0.0, thin: bool = False, color: str = "#2a2320") -> str:
    """tilt > 0 内端压低（凶），tilt < 0 内端抬起（苦相）。"""
    w = 1.7 if thin else 2.4
    return (
        f'<path d="M49 {43.5 + tilt}L59 {43.5 - tilt * 0.6}" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>'
        f'<path d="M69 {43.5 - tilt * 0.6}L79 {43.5 + tilt}" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>'
    )


def nose(shade: str = "#a9705c") -> str:
    return (
        f'<path d="M64 55v5.5l-2.2 1.8" fill="none" stroke="{shade}" stroke-width="1.5" '
        'stroke-linecap="round" stroke-opacity="0.9"/>'
    )


def mouth(width: float = 7.0, curve: float = 2.4, color: str = "#8e594c", weight: float = 2.4) -> str:
    return (
        f'<path d="M{64 - width} 63.5q{width} {curve} {width * 2} 0" fill="none" stroke="{color}" '
        f'stroke-width="{weight}" stroke-linecap="round"/>'
    )


def lipstick(width: float = 6.4) -> str:
    return (
        f'<path d="M{64 - width} 63q{width} 4.6 {width * 2} 0q-{width} -1.6 -{width * 2} 0z" fill="#a83b3b"/>'
        f'<path d="M{64 - width} 63q{width} -1.6 {width * 2} 0" fill="none" stroke="#7d2a2a" '
        'stroke-width="1.2" stroke-linecap="round"/>'
    )


def glasses(lens: str = "#d8cdb4") -> str:
    return (
        f'<g fill="none" stroke="{lens}" stroke-width="1.7" stroke-opacity="0.92">'
        '<circle cx="54" cy="51" r="8.2"/><circle cx="74" cy="51" r="8.2"/>'
        '<path d="M62.2 51h3.6"/><path d="M45.8 49.4l-6.4-2"/><path d="M82.2 49.4l6.4-2"/>'
        "</g>"
        '<g fill="#cfe3f0" fill-opacity="0.10"><circle cx="54" cy="51" r="8.2"/><circle cx="74" cy="51" r="8.2"/></g>'
    )


def earrings(color: str = "#c9a45c") -> str:
    return (
        f'<circle cx="41.5" cy="61" r="2.4" fill="{color}"/>'
        f'<circle cx="86.5" cy="61" r="2.4" fill="{color}"/>'
    )


# ── 发型 ────────────────────────────────────────────────────────────


def hair_slicked(color: str) -> str:
    """往后梳的背头：额角退了一点，中间一道分缝。"""
    return "\n".join(
        [
            f'<path d="M40 52c0-18 5-29 24-29 17 0 25 9 24 26-2-5-5-8-8-9-4 3-9 3-14 1-4-2-7-2-10 0-4 2-8 3-10 7-1 1-3 2-6 4z" fill="{color}"/>',
            f'<path d="M64 24c-7 2-14 9-19 20" fill="none" stroke="#000" stroke-opacity="0.18" stroke-width="1.8"/>',
            f'<path d="M49 31c8-6 26-7 34 1" fill="none" stroke="#ffffff" stroke-opacity="0.28" stroke-width="1.8"/>',
            f'<path d="M41 46c3-9 7-13 11-15" fill="none" stroke="#ffffff" stroke-opacity="0.18" stroke-width="1.4"/>',
        ]
    )


def hair_bun_up(color: str, tie: str = "#c9a45c") -> str:
    return "\n".join(
        [
            f'<circle cx="64" cy="19" r="8.4" fill="{color}"/>',
            f'<ellipse cx="64" cy="26.4" rx="7" ry="2.6" fill="{tie}" fill-opacity="0.55"/>',
            f'<path d="M41 50c0-16 9-25 23-25s23 9 23 25c-3-9-10-14-23-14s-20 5-23 14z" fill="{color}"/>',
            f'<path d="M47 31c7-5 27-6 34 1" fill="none" stroke="#ffffff" stroke-opacity="0.2" stroke-width="1.8"/>',
        ]
    )


def hair_crop(color: str, spike: bool = False) -> str:
    out = [
        f'<path d="M41 49c0-16 9-26 23-26s23 10 23 26c-3-9-10-14-23-14s-20 5-23 14z" fill="{color}"/>'
    ]
    if spike:
        out.append(
            f'<path d="M45 30l3-7 3 6 3-8 3 7 4-8 3 8 3-7 3 7 4-6 3 7 3-5 2 8z" fill="{color}"/>'
        )
    return "\n".join(out)


def hair_ponytail(color: str) -> str:
    return "\n".join(
        [
            # 马尾 + 垂在脸两侧的长发，都画在头后面
            f'<path d="M84 44c11 3 16 13 14 26-1 8-5 14-10 18 2-12 1-22-4-30-3-6-3-10 0-14z" fill="{color}"/>',
            f'<path d="M40 46c-2 14-1 26 2 38 3 9 6 14 9 17-5-13-6-30-4-44z" fill="{color}"/>',
            f'<path d="M88 46c2 14 1 26-2 38-3 9-6 14-9 17 5-13 6-30 4-44z" fill="{color}"/>',
            f'<path d="M41 50c0-16 9-26 23-26s23 10 23 26c-4-10-11-15-23-15s-19 5-23 15z" fill="{color}"/>',
            f'<path d="M47 32c8-6 26-7 33 1" fill="none" stroke="#ffffff" stroke-opacity="0.18" stroke-width="1.8"/>',
            f'<path d="M41 47c3-8 6-12 10-14" fill="none" stroke="#000" stroke-opacity="0.12" stroke-width="2"/>',
        ]
    )


def hair_bob(color: str) -> str:
    """齐下巴的短发，侧分，一边垂下来。"""
    return "\n".join(
        [
            f'<path d="M39 62c-3-24 9-38 25-38s28 14 25 38c-1 5-4 7-7 7 2-13 0-23-6-28-9 6-24 6-31-1-5 6-7 16-5 29-2 0-5-2-6-7z" fill="{color}"/>',
            f'<path d="M46 30c8-5 24-6 31 1" fill="none" stroke="#ffffff" stroke-opacity="0.16" stroke-width="1.8"/>',
        ]
    )


def hair_messy_hood(collar: str) -> str:
    """帽子放下来堆在肩上，头发乱。"""
    return "\n".join(
        [
            f'<path d="M34 100c2-14 13-21 30-21s28 7 30 21z" fill="{collar}"/>',
            f'<path d="M39 106c0-10 9-15 25-15s25 5 25 15" fill="none" stroke="{_dark(collar, 0.72)}" stroke-width="3"/>',
            '<path d="M43 47c0-15 9-24 21-24s21 9 21 24c-2-6-5-9-8-9-3 3-7 3-11 1-4-2-8-2-11 0s-8 4-12 8z" fill="#26221e"/>',
            '<path d="M47 26l-3 8 5-2 2 7 4-8 3 7 3-7 4 7 3-7 4 6 3-6 2 8" fill="none" stroke="#26221e" stroke-width="3" stroke-linejoin="round"/>',
        ]
    )


def hood_rim(color: str) -> str:
    """帽子开口的两道边，只压在脸两侧，不挡嘴。"""
    light = _dark(color, 1.35)
    return (
        f'<path d="M42 60c-4 8-4 18 1 24" fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round"/>'
        f'<path d="M86 60c4 8 4 18-1 24" fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round"/>'
        f'<path d="M43 62c-3 7-3 14 0 19" fill="none" stroke="{light}" stroke-width="1.6" stroke-linecap="round" stroke-opacity="0.6"/>'
        f'<path d="M85 62c3 7 3 14 0 19" fill="none" stroke="{light}" stroke-width="1.6" stroke-linecap="round" stroke-opacity="0.6"/>'
    )


def hair_twintails(color: str, tie: str = "#c9a45c") -> str:
    return "\n".join(
        [
            # 两条低马尾：从耳后垂下来，越往下越细
            f'<path d="M38 58c-6 10-8 20-6 28 2 7 5 11 8 13-3-10-3-22 0-33-2-3-3-6-2-8z" fill="{color}"/>',
            f'<path d="M90 58c6 10 8 20 6 28-2 7-5 11-8 13 3-10 3-22 0-33 2-3 3-6 2-8z" fill="{color}"/>',
            f'<circle cx="37" cy="57" r="3" fill="{tie}"/>',
            f'<circle cx="91" cy="57" r="3" fill="{tie}"/>',
            f'<path d="M41 50c0-16 9-26 23-26s23 10 23 26c-4-10-11-15-23-15s-19 5-23 15z" fill="{color}"/>',
            f'<path d="M50 25q14-7 28 0" fill="none" stroke="#ffffff" stroke-opacity="0.2" stroke-width="2"/>',
            f'<path d="M64 27c-6 3-11 8-14 14" fill="none" stroke="#000" stroke-opacity="0.10" stroke-width="2"/>',
        ]
    )


def cap(color: str, brim: str) -> str:
    return "\n".join(
        [
            f'<path d="M40 42c0-14 10-22 24-22s24 8 24 22z" fill="{color}"/>',
            f'<path d="M40 42h48" stroke="{brim}" stroke-width="2.6"/>',
            f'<path d="M84 39q13 2 14 7H84z" fill="{brim}"/>',
            f'<path d="M64 20v22" stroke="#000" stroke-opacity="0.16" stroke-width="1.4"/>',
            f'<circle cx="64" cy="20" r="1.8" fill="{brim}"/>',
            f'<path d="M46 30c4-7 10-10 18-10s14 3 18 10" fill="none" stroke="#ffffff" stroke-opacity="0.14" stroke-width="2"/>',
        ]
    )


def earbuds(color: str = "#8d8a84") -> str:
    return (
        f'<g fill="{color}">'
        '<circle cx="42" cy="60" r="2.6"/><circle cx="86" cy="60" r="2.6"/></g>'
        f'<path d="M43 63c1 7 3 10 6 12" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>'
        f'<path d="M85 63c-1 7-3 10-6 12" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>'
    )


# ── 八个人 ──────────────────────────────────────────────────────────


def build() -> dict[str, str]:
    people: dict[str, str] = {}

    # 乾明 · 乾 · 天 —— 老派长辈：银发背头、山羊胡、深蓝西装、金领针
    people["qian"] = svg(
        "\n".join(
            [
                shoulders("#26456b", "#1b3050"),
                '<path d="M58 88l6 12 6-12" fill="#c9a45c" fill-opacity="0.9"/>',
                neck("#e2b393"),
                head("#e2b393"),
                hair_slicked("#d3cfc7"),
                brows(-1.5, thin=True, color="#8f8a80"),
                '<g stroke="#a9705c" stroke-width="1.1" stroke-linecap="round" fill="none" stroke-opacity="0.6">'
                '<path d="M45 47l-3.6-1.6"/><path d="M45 50l-3.6 1.4"/>'
                '<path d="M83 47l3.6-1.6"/><path d="M83 50l3.6 1.4"/></g>',
                eye(54),
                eye(74),
                nose(),
                '<path d="M59 62q5-2 10 0" fill="none" stroke="#b9b3aa" stroke-width="2" stroke-linecap="round"/>',
                '<path d="M60 69q4 7 8 0q-2 7-4 8-2-1-4-8z" fill="#b9b3aa"/>',
                mouth(6.4, 2.2),
            ]
        )
    )

    # 坤兰 · 坤 · 地 —— 记事的阿姨：盘发、老花镜、披肩、笑纹
    people["kun"] = svg(
        "\n".join(
            [
                shoulders("#6b5232", "#4a3922"),
                '<path d="M40 86c7-6 15-9 24-9s17 3 24 9l-7 13H47z" fill="#8a6a3a"/>',
                '<path d="M40 86c7-6 15-9 24-9s17 3 24 9" fill="none" stroke="#a98a52" stroke-width="1.6" stroke-opacity="0.7"/>',
                neck("#e6bb9d"),
                head("#e6bb9d"),
                hair_bun_up("#c1bbb2"),
                brows(-2.5, thin=True, color="#8f8a80"),
                eye(54, closed_smile=False),
                eye(74, closed_smile=False),
                glasses(),
                nose(),
                '<g stroke="#a9705c" stroke-width="1.1" stroke-linecap="round" fill="none" stroke-opacity="0.55">'
                '<path d="M49 62l-2 5"/><path d="M79 62l2 5"/></g>',
                mouth(6.6, 3.2, color="#96574a"),
            ]
        )
    )

    # 震山 · 震 · 雷 —— 火气大的长子：寸头翘着、立眉、运动外套
    people["zhen"] = svg(
        "\n".join(
            [
                shoulders("#2f7a55", "#235c42"),
                '<path d="M64 84v44" stroke="#f0e6d2" stroke-opacity="0.45" stroke-width="1.6"/>',
                '<g fill="#d8cdb4" fill-opacity="0.55">'
                '<rect x="61.4" y="92" width="5.2" height="2" rx="1"/>'
                '<rect x="61.4" y="98" width="5.2" height="2" rx="1"/>'
                '<rect x="61.4" y="104" width="5.2" height="2" rx="1"/></g>',
                neck("#dcae87"),
                head("#dcae87"),
                hair_crop("#2b2622", spike=True),
                brows(2.4),
                eye(54, wide=True),
                eye(74, wide=True),
                nose(),
                mouth(6.2, 0.6, weight=2.6),
            ]
        )
    )

    # 巽竹 · 巽 · 风 —— 消息最灵：侧分长发、马尾、耳坠
    people["xun"] = svg(
        "\n".join(
            [
                shoulders("#2f6f72", "#23575a"),
                neck("#e8c4a6"),
                head("#e8c4a6"),
                hair_ponytail("#33291f"),
                brows(-2),
                eye(54),
                eye(74),
                nose(),
                mouth(6.4, 2.6),
                earrings(),
            ]
        )
    )

    # 坎川 · 坎 · 水 —— 挑毛病的二儿子：帽子垂在肩上、头发乱、胡茬、苦相
    people["kan"] = svg(
        "\n".join(
            [
                shoulders("#2f4a7a", "#22395e"),
                hair_messy_hood("#1d2f4c"),
                neck("#d3a583"),
                head("#d3a583"),
                '<path d="M43 47c0-15 9-24 21-24s21 9 21 24c-2-6-5-9-8-9-3 3-7 3-11 1-4-2-8-2-11 0s-8 4-12 8z" fill="#26221e"/>',
                '<path d="M47 26l-3 8 5-2 2 7 4-8 3 7 3-7 4 7 3-7 4 6 3-6 2 8" fill="none" stroke="#26221e" stroke-width="3" stroke-linejoin="round"/>',
                '<path d="M50 62c1 8 5 13 14 13s13-5 14-13c-2 6-7 9-14 9s-12-3-14-9z" fill="#3b2f28" opacity="0.35"/>',
                brows(-2.6),
                eye(54, wide=False),
                eye(74, wide=False),
                nose(),
                mouth(6.2, -0.8, weight=2.3),
            ]
        )
    )

    # 离霞 · 离 · 火 —— 最抢眼的二女儿：红棕短发、浓唇、大耳环
    people["li"] = svg(
        "\n".join(
            [
                shoulders("#8a3a3a", "#682b2b"),
                '<path d="M52 86l12 14 12-14-12-3z" fill="#f0e6d2" fill-opacity="0.25"/>',
                neck("#eec6a8"),
                head("#eec6a8"),
                hair_bob("#4a2b22"),
                brows(-2.2),
                eye(54),
                eye(74),
                nose(),
                lipstick(),
                earrings(),
            ]
        )
    )

    # 艮石 · 艮 · 山 —— 不爱说话的小儿子：棒球帽、脖子上挂耳机
    people["gen"] = svg(
        "\n".join(
            [
                shoulders("#4a4a52", "#36363d"),
                '<path d="M55 85h18v9a9 9 0 0 1-18 0z" fill="#2d2d33"/>',
                neck("#e3b795"),
                head("#e3b795"),
                cap("#4c5560", "#39414a"),
                '<path d="M43 47c2-6 6-10 11-12 6-2 14-2 20 0 5 2 9 6 11 12-8-5-14-6-21-6s-13 1-21 6z" fill="#2b2622"/>',
                brows(-2),
                eye(54),
                eye(74),
                nose(),
                mouth(5.8, 1.6, weight=2.2),
                earbuds(),
            ]
        )
    )

    # 兑溪 · 兑 · 泽 —— 一开口就撒娇的小女儿：双马尾、笑眼、发圈
    people["dui"] = svg(
        "\n".join(
            [
                shoulders("#7a3a6a", "#5d2b51"),
                neck("#f0cbaa"),
                head("#f0cbaa"),
                hair_twintails("#3a2a24"),
                brows(-2.6, thin=True, color="#4a3a30"),
                eye(54, closed_smile=True),
                eye(74, closed_smile=True),
                nose(),
                '<path d="M57 63.5q7 6.5 14 0q-7 2.4-14 0z" fill="#c9736a"/>',
                '<path d="M57 63.5q7 1.4 14 0" fill="none" stroke="#a85a52" stroke-width="1.2"/>',
            ]
        )
    )

    return people


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "assets" / "avatars"
    out.mkdir(parents=True, exist_ok=True)
    people = build()
    for key, content in people.items():
        (out / f"{key}.svg").write_text(content, encoding="utf-8")
    print(f"wrote {len(people)} avatars to {out}")


if __name__ == "__main__":
    main()
