"""Export complete roundtable sessions without UI dependencies."""

from __future__ import annotations

import json
from pathlib import Path

from .models import DiscussionSession
from .storage import session_to_dict


def export_json(session: DiscussionSession, path: Path) -> Path:
    path.write_text(json.dumps(session_to_dict(session), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_markdown(session: DiscussionSession, path: Path) -> Path:
    lines = [
        f"# {session.topic}",
        "",
        f"创建时间：{session.created_at:%Y-%m-%d %H:%M}",
        "",
        "## 来源与证据",
        "",
        f"- 请求模式：{session.request_mode}",
        f"- 实际讨论提供方：{session.effective_provider}",
        f"- 实际模式：{session.provider_mode}",
        f"- 内容来源：{session.content_label}",
        f"- 观点生成说明：{session.viewpoint_source_description.replace(chr(10), ' ')}",
        f"- 新闻提供方：{session.news_provider}",
        f"- RSS 尝试：{'是' if session.news_attempted else '否'}",
        f"- RSS 成功：{'是' if session.news_success else '否'}",
        f"- RSS 命中：{'是' if session.news_matched else '否'}",
        f"- RSS 部分失败：{'是' if session.news_partial_failure else '否'}",
        f"- 网络使用：{'是' if session.network_used else '否'}",
        f"- 状态：{session.status_message}",
        f"- 模型：{session.model_name or '未使用真实模型'}",
        f"- 生成状态：{session.generation_status}",
        f"- 生成阶段：{session.generation_stage or '无'}",
        f"- 流式完成：{'是' if session.generation_streamed else '否'}",
        f"- 使用量：输入 {session.usage_input_tokens} / 输出 {session.usage_output_tokens} tokens；请求 {session.usage_requests} 次",
        f"- 回退原因：{session.fallback_reason or '无'}",
    ]
    if session.sources:
        for item in session.sources:
            published = f"；发布时间：{item.published_at:%Y-%m-%d %H:%M}" if item.published_at else ""
            fetched = f"；获取时间：{item.fetched_at:%Y-%m-%d %H:%M}" if item.fetched_at else ""
            lines.extend([
                "",
                f"### {item.title}",
                f"- 类型：{item.source_type}",
                f"- 地址：{item.url or '用户提供'}",
                f"- 可信度：{item.credibility}{published}{fetched}",
                f"- 摘要：{item.note or '无摘要'}",
            ])
    else:
        lines.extend(["", f"- 无外部来源；{session.content_label}，不等于真实市场事实。"])
    lines.extend(["", "## 圆桌记录", ""])
    for item in session.utterances:
        intent = f" · 回应意图：{item.intent}" if item.intent else ""
        reply = f" · 回应事件：{item.replies_to}" if item.replies_to else ""
        stance = f" · 改变立场：{item.stance_change.before} → {item.stance_change.after}" if item.stance_change else ""
        lines.extend([f"### {item.speaker_name} · {item.phase} · {item.kind.value}{intent}{reply}{stance} · {session.utterance_source(item)}", item.content, ""])
    if session.opportunity:
        card = session.opportunity
        lines.extend(["## 机会档案", "", f"**机会方向：** {card.title}", f"**目标用户：** {card.audience}", ""])
        for title, values in (("支持理由", card.support), ("主要风险", card.risks), ("待验证假设", card.assumptions), ("建议下一步", card.next_steps)):
            lines.extend([f"### {title}", *[f"- {value}" for value in values], ""])
        lines.extend([f"**观点分布：** {card.stance_counts}", ""])
    state = session.discussion_state
    consensus = [f"- {value}" for value in state.consensus] or ["- 暂无记录"]
    conflicts = [f"- {value}" for value in state.conflicts] or ["- 暂无记录"]
    questions = [f"- {value}" for value in state.unresolved_questions] or ["- 暂无记录"]
    stances = [f"- {key}：{value}" for key, value in state.role_stances.items()] or ["- 暂无记录"]
    lines.extend(["## 讨论状态", "", "### 当前共识", *consensus, ""])
    lines.extend(["### 未解决分歧", *conflicts, ""])
    lines.extend(["### 未回答问题", *questions, ""])
    lines.extend(["### 立场轨迹", *stances, ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
