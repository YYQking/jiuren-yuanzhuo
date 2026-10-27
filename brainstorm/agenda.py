"""分层议题：一场讨论不是把所有话一次说完，而是一层一层往下挖。

一层聊够了（默认 6 条）才换下一层；层与层之间是"往深里走"，不是并列的清单。
这解决"20 轮就到头"的问题：讨论的上限由层的数量决定，而不是由轮次表决定。
"""

from __future__ import annotations

from .models import Utterance

LAYER_TURNS = 6

BUSINESS_LAYERS = (
    "现象",
    "原因",
    "谁受益谁付代价",
    "现有做法为什么不够",
    "可下手的切口与前提",
)

EVENT_LAYERS = (
    "到底发生了什么",
    "谁受损、谁得利",
    "各方说法和背后的动机",
    "怎么处理的、代价值不值",
    "这事该怎么收场",
)

LAYER_QUESTIONS = {
    "现象": "把看到的现象说具体：什么场景、什么频率、谁在做。",
    "原因": "往下追一层：为什么会这样，机制是什么。",
    "谁受益谁付代价": "这件事谁得利、谁承担成本和麻烦。",
    "现有做法为什么不够": "现在已有的做法是什么，卡在哪里。",
    "可下手的切口与前提": "最小能试的切口是什么，成立需要什么前提。",
    "到底发生了什么": "把事实和传话分开：谁在场、什么时候、原话是什么。",
    "谁受损、谁得利": "这件事谁吃亏、谁占便宜，代价落在谁身上。",
    "各方说法和背后的动机": "各方为什么这么说，说这话对他有什么好处。",
    "怎么处理的、代价值不值": "已经怎么处理了，这个处理方式的代价是什么。",
    "这事该怎么收场": "最可能的收场方式是什么，还能补救什么。",
}


def layer_names(mode: str) -> tuple[str, ...]:
    return EVENT_LAYERS if mode == "event" else BUSINESS_LAYERS


def spoken_turns(history: list[Utterance]) -> int:
    """主持人和用户的插话不算推进层数的发言。"""
    return sum(1 for item in history if item.speaker_id not in {"moderator", "user"})


def layer_index(history: list[Utterance], mode: str) -> int:
    names = layer_names(mode)
    if not names:
        return 0
    return min(spoken_turns(history) // LAYER_TURNS, len(names) - 1)


def layer_for(history: list[Utterance], mode: str) -> str:
    return layer_names(mode)[layer_index(history, mode)]


def layer_context(history: list[Utterance], mode: str) -> str:
    """What the speaker should be digging into on this turn."""
    name = layer_for(history, mode)
    names = layer_names(mode)
    index = layer_names(mode).index(name)
    question = LAYER_QUESTIONS.get(name, "")
    position = spoken_turns(history) % LAYER_TURNS + 1
    if index == 0 and position <= 2:
        return ""  # 刚开场，先把话说清，不必催人往深里挖
    return (
        f"这一层在聊：{name}（第 {index + 1}/{len(names)} 层，本层第 {position} 条）。"
        f"{question}"
        " 一层没聊透就别急着换层；换层时把上一层留下的结论一句话带过。\n"
    )


def layer_target_reached(history: list[Utterance], mode: str) -> bool:
    """True once the last layer has had its share of turns."""
    return layer_index(history, mode) == len(layer_names(mode)) - 1
