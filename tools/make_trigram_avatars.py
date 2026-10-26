import pathlib

# The eight trigram seats need avatars like the nine occupations have.  They reuse
# the illustration family (round portrait, shoulders, head) so the two sections look
# like one product, and carry the trigram glyph as a small corner mark: three bars,
# solid for yang, split for yin, top bar = the sixth line.
SEATS = {
    "qian": ("#172c47", "#3b82f6", "#2f2a26", ("yang", "yang", "yang")),
    "kun": ("#3a2a10", "#a16207", "#4a3323", ("yin", "yin", "yin")),
    "zhen": ("#123a20", "#22c55e", "#2f2a26", ("yin", "yin", "yang")),
    "xun": ("#0f3330", "#14b8a6", "#4a3323", ("yang", "yang", "yin")),
    "kan": ("#1c2145", "#6366f1", "#2f2a26", ("yin", "yang", "yin")),
    "li": ("#401414", "#ef4444", "#4a3323", ("yang", "yin", "yang")),
    "gen": ("#2a2724", "#78716c", "#2f2a26", ("yang", "yin", "yin")),
    "dui": ("#3d1229", "#ec4899", "#4a3323", ("yin", "yang", "yang")),
}

MALE_HAIR = "M39 46c3-24 46-29 52 1-10-8-28-10-52-1z"
FEMALE_HAIR = "M38 44c4-26 48-28 52 2 2 12-1 24-5 31-3-18-9-26-21-26s-19 8-22 26c-4-7-6-20-4-33z"


def glyph(lines) -> str:
    out = []
    for index, kind in enumerate(lines):
        y = 74 + index * 9
        if kind == "yang":
            out.append(f'<rect x="90" y="{y}" width="26" height="5" rx="2.5" fill="#f5e6c8" fill-opacity="0.82"/>')
        else:
            out.append(f'<rect x="90" y="{y}" width="11" height="5" rx="2.5" fill="#f5e6c8" fill-opacity="0.82"/>')
            out.append(f'<rect x="105" y="{y}" width="11" height="5" rx="2.5" fill="#f5e6c8" fill-opacity="0.82"/>')
    return "".join(out)


template = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
    '<circle cx="64" cy="64" r="62" fill="{bg}"/>'
    '<path d="M24 108c5-24 19-35 40-35s35 11 40 35" fill="{color}" fill-opacity="0.55"/>'
    '<circle cx="64" cy="49" r="24" fill="#d9a98e"/>'
    '<path d="{hair}" fill="{hair_color}"/>'
    '<path d="M43 111h42l-7-27H50z" fill="{color}"/>'
    '<circle cx="55" cy="50" r="3" fill="#172c47"/>'
    '<circle cx="73" cy="50" r="3" fill="#172c47"/>'
    '<path d="M56 62q8 6 16 0" fill="none" stroke="#8e594c" stroke-width="3"/>'
    "{glyph}"
    "</svg>"
)

target = pathlib.Path("assets/avatars")
for seat_id, (bg, color, hair_color, lines) in SEATS.items():
    female = seat_id in {"kun", "xun", "li", "dui"}
    svg = template.format(
        bg=bg,
        color=color,
        hair=FEMALE_HAIR if female else MALE_HAIR,
        hair_color=hair_color,
        glyph=glyph(lines),
    )
    (target / f"{seat_id}.svg").write_text(svg + "\n", encoding="utf-8")
    print("wrote", seat_id)
