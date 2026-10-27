"""Keep the table sounding like people talking, not one template rendered N times.

Measured on a real 20-turn event discussion (``artifacts/real-event-3``): every
single turn was 154-257 characters long, six of eight opening turns began with
「我先说…」, and nine turns ended with 「最后…」.  Nothing in that transcript was
wrong, but the shape was identical every time, which is exactly what makes a
roundtable read as a template.

This module only holds the wording and the detection.  The planner decides how
long a turn should be; the provider puts the rules in the prompt and re-asks once
when a turn opens with a stock phrase.
"""

from __future__ import annotations

import re

#: Stock openings that make every seat sound like the same person clearing their
#: throat.  Checked against the head of the utterance only.
TEMPLATE_OPENINGS = (
    "我先说",
    "我先讲",
    "我先开个头",
    "我先表个态",
    "我就说一句",
    "我就说一嘴",
    "我先说一嘴",
    "我先说一句",
    "我先说句",
    "我先表个",
    "实话实说",
    "说句实在话",
    "说句实话",
    "说白了",
    "作为一个",
    "站在我的角度",
    "从我的角度",
    "首先",
    "第一，",
    "第一点",
)

#: Structural markers that turn a turn into a five-part essay.
TEMPLATE_MARKERS = (
    "综上所述",
    "总的来说",
    "总而言之",
    "首先",
    "其次",
    "再次",
    "第一，",
    "第二，",
    "第三，",
    "最后，",
)

#: How many characters of the head are examined for a stock opening.
OPENING_WINDOW = 16

#: Length targets, chosen by the planner.  Real conversation is mostly short;
#: the uniform 150-250 character block was the single loudest tell.
LENGTH_TARGETS = {
    "short": "这一条只写 30–70 字，一两句话，像抢话；说完就停，不解释。",
    "normal": "这一条写 80–140 字，把一件事说完就行。",
    "long": "这一条可以写到 180–240 字，但只在你确实有话要说的时候。",
    "host": "这一条 120–200 字：点名、逼一个回答，不要自己替大家说。",
}

ANTI_TEMPLATE_RULES = (
    "「怎么说」比说什么更要紧：\n"
    "- 别把每一条都写成同一副骨架（接话→表态→但是→条件→反问）。"
    "每一条只做一件事：接一句、顶一句、补一个事实、问一句、认个错、换个角度；做完就停。\n"
    "- 不许用这些开场：我先说、我就说一句、我先开个头、我先表个态、实话实说、说白了、作为一个……；"
    "第一句就得是你自己的东西。\n"
    "- 不许分点，不许用「第一/第二/第三」「首先/其次/最后」，不许写「总的来说」「综上所述」。\n"
    "- 不许复述主题，也不许把别人刚说的话重复一遍再表态。\n"
    "- 不写铺垫、客套和总结性空话。\n"
    "- 有人可以接的时候，第一句就点他的名（「坎川你…」「地姐这话…」）；不要对着空气说话。\n"
    "- 不许沿用上一位的开场句式或口头禅，换自己的说法。\n"
    "- 准许半句话、打断、插一句、说错再改口；准许只回一句「我不信，凭啥」。\n"
)


def length_instruction(hint: str) -> str:
    """Return the length sentence for a planner hint (unknown hints fall back)."""
    return LENGTH_TARGETS.get(str(hint or ""), LENGTH_TARGETS["normal"])


def find_template_opening(text: str) -> str:
    """Return the stock phrase a turn opens with, or ``""``.

    Only the head is inspected: 「说白了」 halfway through a sentence is a normal
    thing for a person to say, while 「老实说，我先说一句」 as the opening is the
    tell.
    """
    head = re.sub(r"^[\s「『\"'（(]+", "", str(text or ""))
    head = head[:OPENING_WINDOW]
    for phrase in TEMPLATE_OPENINGS:
        if head.startswith(phrase):
            return phrase
    return ""


def find_template_markers(text: str) -> list[str]:
    """Return every structural marker present, for diagnostics and tests."""
    body = str(text or "")
    return [marker for marker in TEMPLATE_MARKERS if marker in body]


def looks_templated(text: str) -> str:
    """Return a short reason when a turn reads as a template, else ``""``."""
    opening = find_template_opening(text)
    if opening:
        return f"开头是套话「{opening}」"
    return ""
