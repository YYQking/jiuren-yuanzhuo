"""Provider seams and the deterministic offline discussion engine."""

from collections.abc import Iterable, Sequence
import re
from dataclasses import dataclass
from typing import Protocol

from .models import DiscussionSession, OpportunityCard, Participation, Role, StanceChange, TrendSource, Utterance, ViewpointKind


class DiscussionProvider(Protocol):
    def discuss(self, topic: str, roles: Iterable[Role], source_note: str = "", *, sources: Sequence[TrendSource] = ()) -> DiscussionSession:
        ...


@dataclass
class MockDiscussionProvider:
    """Generate useful, clearly simulated turns without network access."""

    def discuss(self, topic: str, roles: Iterable[Role], source_note: str = "", *, sources: Sequence[TrendSource] = ()) -> DiscussionSession:
        selected = list(roles)
        if not topic.strip():
            raise ValueError("请输入一个讨论主题。")
        if not selected:
            raise ValueError("至少选择一位参与者。")

        session = DiscussionSession(topic=topic.strip(), selected_role_ids=[role.id for role in selected])
        if source_note.strip():
            session.source = TrendSource(title="用户提供的前沿线索", note=source_note.strip(), source_type="user")
            session.sources.append(session.source)
        for item in sources:
            if (item.title.casefold(), item.url.casefold()) not in {(source.title.casefold(), source.url.casefold()) for source in session.sources}:
                session.sources.append(item)
                session.source = session.source or item
        by_id = {role.id: role for role in selected}
        active = [role for role in selected]

        self._add(session, "moderator", "主持人", f"我们围绕“{topic.strip()}”开始圆桌讨论。本轮内容是离线 AI 模拟观点，不能替代真实调研。", ViewpointKind.SUMMARY, "开场")
        if source_note.strip():
            self._add(session, "moderator", "主持人", f"用户提供的前沿素材是：“{source_note.strip()}”。它将作为讨论线索，而不是已核验事实。", ViewpointKind.FACT, "前沿线索")
        rss_sources = [item for item in session.sources if item.source_type == "rss"]
        if rss_sources:
            titles = "、".join(item.title for item in rss_sources[:3])
            self._add(session, "moderator", "主持人", f"本次参考了 RSS 外部素材（{titles}），它们只是未核验资料，不是角色原话或已证实事实。", ViewpointKind.FACT, "前沿线索")

        templates = {
            "trend": (ViewpointKind.FACT, f"从趋势角度看，“{topic}”值得关注的关键，不只是热点本身，而是它背后可能持续改变人们行为的一组变化。需要继续核对时间线、来源和影响范围。"),
            "industry": (ViewpointKind.ASSUMPTION, f"从业者会先问：{topic}是否能嵌入现有流程？如果需要用户、企业或平台大幅改变习惯，落地阻力可能比想象中更大。"),
            "builder": (ViewpointKind.OPPORTUNITY, f"如果把“{topic}”做成产品，我会先缩小到一个高频场景，找到一类愿意立即尝试的人，用最小版本验证，而不是一开始解决所有问题。"),
            "technology": (ViewpointKind.ASSUMPTION, f"技术上可以先做一个轻量原型验证“{topic}”是否有价值，优先复用成熟能力，避免把技术复杂度误认为用户价值。"),
            "need": (ViewpointKind.OPPORTUNITY, f"作为可能真正遇到这个问题的人，我不会因为概念新就使用。我需要先看到它能节省时间、减少损失，或明显改善一个具体场景。"),
            "bystander": (ViewpointKind.RISK, f"普通人第一次听到“{topic}”可能无法马上理解。如果还要学习复杂流程，我大概率不会主动尝试，除非价值能在几句话内说清楚。"),
            "researcher": (ViewpointKind.VALIDATION, f"不能笼统地说“大家都有需求”。应该拆出最可能受影响的人群，分别验证痛点频率、现有替代方案和付费意愿。"),
            "creative": (ViewpointKind.OPPORTUNITY, f"可以把“{topic}”和另一个相邻场景连接起来：不只提供一个工具，也提供持续反馈、协作或服务，让它形成新的使用习惯。"),
            "skeptic": (ViewpointKind.RISK, f"我最担心的是把讨论热度误判成真实需求。用户为什么今天就要解决？现有方案哪里真的不够？如果回答不了，方向可能只是漂亮的假设。"),
        }
        for role in active:
            kind, text = templates.get(
                role.id,
                (ViewpointKind.ASSUMPTION, f"从{role.duty}的角度看，“{topic}”需要先验证真实场景、使用阻力和可持续价值。"),
            )
            self._add(session, role.id, role.name, text, kind, "独立观点")

        if "need" in by_id and "builder" in by_id:
            self._add(session, "need", by_id["need"].name, "我补充一点：只有当产品进入我原本就会发生的场景，而不是要求我长期学习，它才可能从“有趣”变成“有用”。", ViewpointKind.OPPORTUNITY, "需求验证", "builder")
        if "skeptic" in by_id and "builder" in by_id:
            self._add(session, "skeptic", by_id["skeptic"].name, "回应创业实践者：缩小场景是必要条件，但还不够；请明确第一批用户为什么不用现有替代方案。", ViewpointKind.RISK, "正反交锋", "builder")
        if "industry" in by_id and "technology" in by_id:
            self._add(session, "industry", by_id["industry"].name, "技术顾问说得通，但行业流程、合规和采购关系也要一起验证，不能只证明“能做出来”。", ViewpointKind.ASSUMPTION, "落地检验", "technology")
        if "creative" in by_id and "researcher" in by_id:
            self._add(session, "creative", by_id["creative"].name, "我把方案再换一个角度：先服务一个细分人群，再把验证中出现的相邻需求连接起来。", ViewpointKind.OPPORTUNITY, "方案重构", "researcher")

        active_names = "、".join(role.name for role in active)
        self._add(session, "moderator", "主持人", f"当前参与者：{active_names}。初步共识是先从具体场景和小范围用户开始；主要分歧是需求强度、行业阻力和差异化是否足够。", ViewpointKind.SUMMARY, "阶段总结")
        session.opportunity = OpportunityCard(
            title=f"围绕“{topic}”的窄场景机会",
            audience="需要频繁处理该问题、且现有替代方案明显不便的一类细分用户",
            support=["社会变化可能带来新的行为或约束", "可先从单一高频场景做轻量验证", "多角色讨论发现了需求、行业与技术的交叉点"],
            risks=["讨论中的需求强度尚未通过真实访谈验证", "现有方案和竞争格局仍不清楚", "普通用户可能感知不到足够价值"],
            assumptions=["目标用户愿意改变现有习惯", "第一版能在较低成本下交付核心价值", "前沿素材中的变化具有持续性"],
            next_steps=["访谈 5—10 位明确目标用户", "记录他们目前的替代方案和真实成本", "制作一个只解决单一场景的原型并观察使用行为"],
            stance_counts={"支持/机会": sum(1 for u in session.utterances if u.kind == ViewpointKind.OPPORTUNITY), "保留/假设": sum(1 for u in session.utterances if u.kind in (ViewpointKind.ASSUMPTION, ViewpointKind.FACT)), "风险/反对": sum(1 for u in session.utterances if u.kind == ViewpointKind.RISK)},
        )
        session.phase = "首轮观点"
        return session

    def extend(self, session: DiscussionSession, batch_index: int = 1) -> list[Utterance]:
        """Append another conversational batch to an existing live session.

        The offline provider deliberately uses the recorded speakers as its
        context, so historical sessions and custom roles can continue without
        storing a second copy of the role definitions.  A batch has no
        relationship to a fixed total round count; callers may request it as
        many times as the user wants.
        """
        if not session.topic.strip():
            raise ValueError("请输入一个讨论主题。")
        state = self.analyze_state(session)
        participants: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in session.utterances:
            if item.speaker_id in {"moderator", "user"} or item.speaker_id in seen:
                continue
            seen.add(item.speaker_id)
            participants.append((item.speaker_id, item.speaker_name))
        if not participants:
            participants = [("moderator", "主持人")]

        anchor = next(
            (item for item in reversed(session.utterances) if item.speaker_id not in {"moderator", "user"}),
            session.utterances[-1] if session.utterances else None,
        )
        anchor_speaker = anchor.speaker_name if anchor else "上一条观点"
        anchor_id = anchor.speaker_id if anchor else "moderator"
        # Rotate the focus so every selected role keeps participating. User
        # input guides the templates but is never spoken on the user's behalf.
        offset = (max(1, batch_index) - 1) * 2 % len(participants)
        participants = participants[offset:] + participants[:offset]
        first = participants[0]
        second = participants[1 % len(participants)]
        third = participants[2 % len(participants)]
        fourth = participants[3 % len(participants)]
        intervene, intervention_reason = self.should_intervene(
            state, session.utterances[-12:], batch_index=max(1, batch_index)
        )
        if intervene:
            sequence = [("moderator", "主持人"), first, second, first, third, fourth, second, ("moderator", "主持人")]
        else:
            # Keep a full, readable batch while letting the roles carry the
            # conversation until a state change actually needs a host recap.
            sequence = [first, second, first, third, fourth, second, third, first]
        focus_points = ["需求频率", "现有替代方案", "使用门槛", "交付成本", "付费意愿", "试点范围", "持续使用", "行业流程", "退出条件"]
        focus = focus_points[(max(1, batch_index) - 1) % len(focus_points)]
        user_input = next((item.content for item in reversed(session.utterances) if item.speaker_id == "user"), "")
        user_context = f"用户刚才提醒：{user_input[:160]}。" if user_input else ""
        anchor_content = anchor.content[:100] if anchor else session.topic[:100]
        kinds = [
            ViewpointKind.SUMMARY,
            ViewpointKind.ASSUMPTION,
            ViewpointKind.OPPORTUNITY,
            ViewpointKind.RISK,
            ViewpointKind.VALIDATION,
            ViewpointKind.OPPORTUNITY,
            ViewpointKind.RISK,
            ViewpointKind.SUMMARY,
        ]
        intents = ["synthesize", "question", "support", "challenge", "question", "elaborate", "challenge", "synthesize"]
        phases = (["主持人追问", "回应", "补充", "正面反驳", "验证追问", "方案修正", "风险反驳", "阶段收束"]
                  if intervene else ["回应", "补充", "正面反驳", "验证追问", "方案修正", "风险反驳", "继续追问", "补充"])
        templates = [
            f"继续讨论{focus}。{anchor_speaker}刚才说：“{anchor_content}”。哪些前提需要进一步检验？{user_context}",
            f"我回应{anchor_speaker}，从{focus}看，我们还缺少真实行为记录。{user_context}建议先记录目标人群怎样处理这个问题。",
            f"我补充一个方向：针对{focus}安排一个小规模试点，观察用户是否主动选择我们的方案，而不是只问他们喜不喜欢。",
            f"我不同意直接把当前共识当成结论。关于{focus}，如果没有和现有替代方案比较，就无法判断改变是否值得。",
            f"可以把{focus}变成可证伪的假设：明确一类用户、一个具体场景和一个观察周期；如果行为没有改变，就调整方向。",
            f"听了反对意见，我修改方案：把{focus}的验证范围缩到最小，先降低用户切换成本，再考虑扩大。",
            f"我仍保留意见：即便{focus}试点成功，也要检查是否依赖额外补贴或人工服务；这些成本可能无法长期维持。",
            f"本批围绕{focus}形成了待检验的方案与分歧。下一批继续讨论，所有结论仍是离线模拟观点；你可随时结束并总结。",
        ]
        added: list[Utterance] = []
        for index, (speaker_id, speaker_name) in enumerate(sequence):
            content = templates[index]
            if state.pending_user_interjection and index == (1 if intervene else 0):
                content = f"针对用户插话“{state.pending_user_interjection[:160]}”，我先回应：这应成为本批最高优先级的验证问题。{content}"
            replies_to = anchor_id if index == 0 else added[-1].event_id
            item = Utterance(
                speaker_id,
                speaker_name,
                content,
                kinds[index],
                phases[index],
                replies_to,
                origin="offline",
                intent=intents[index],
                stance_change=(StanceChange(
                    before="坚持原方案",
                    after="缩小方案并先验证",
                    reason="回应前文关于用户切换成本的反驳",
                    triggered_by=[anchor.event_id] if anchor else [],
                ) if index == 5 else None),
            )
            item = session.append_utterance(item)
            added.append(item)
        session.rebuild_state()
        session.discussion_state.pending_user_interjection = ""
        session.discussion_state.host_intervention_reason = intervention_reason if intervene else ""
        session.phase = "状态整理" if intervene else "动态交锋"
        self._refresh_opportunity(session)
        return added

    @staticmethod
    def should_intervene(state, recent_events: list[Utterance], *, batch_index: int = 1) -> tuple[bool, str]:
        """Decide whether the host should summarize this batch.

        The first live batch keeps a short host framing turn. Later batches
        stay role-led unless there is evidence that a recap will help: a
        repeated point, a marked duplicate, or a conflict that has just been
        explicitly challenged.
        """
        if batch_index <= 1:
            return True, "首轮交锋需要主持人建立讨论上下文"
        role_events = [item for item in recent_events if item.speaker_id not in {"moderator", "user"}]
        if any(item.duplicate for item in role_events) and state.conflicts:
            return True, "重复观点与分歧同时出现，需要主持人整理"
        normalized = [re.sub(r"\s+", "", item.content)[:80] for item in role_events]
        if len(normalized) >= 4 and len(normalized) - len(set(normalized)) >= 2 and state.conflicts:
            return True, "重复观点增多且分歧未收敛，需要主持人整理"
        challenged = [item for item in role_events[-6:] if item.intent == "challenge"]
        if len(challenged) >= 3 and state.conflicts and any(item.stance_change for item in role_events[-6:]):
            return True, "关键分歧已完成多次交锋，需要主持人收束"
        return False, ""

    @staticmethod
    def analyze_state(session: DiscussionSession):
        """Derive a conservative, explainable snapshot from recorded turns."""
        state = session.discussion_state
        role_items = [item for item in session.utterances if item.speaker_id not in {"moderator", "user"}]
        normalized = [re.sub(r"\s+", "", item.content)[:80] for item in role_items]
        state.duplicate_count = max(0, len(normalized) - len(set(normalized)))
        state.new_information_density = 1.0 if not normalized else len(set(normalized)) / len(normalized)
        opportunity = session.opportunity
        state.consensus = list(dict.fromkeys(opportunity.support[:4] if opportunity else []))
        state.conflicts = list(dict.fromkeys(opportunity.risks[:4] if opportunity else []))
        state.unresolved_questions = list(dict.fromkeys(
            (opportunity.assumptions[:3] if opportunity else []) +
            (opportunity.next_steps[:3] if opportunity else [])
        ))
        state.role_stances = {item.speaker_id: item.content for item in role_items[-len(set(i.speaker_id for i in role_items)):] } if role_items else {}
        state.active_thread = state.unresolved_questions[0] if state.unresolved_questions else (state.conflicts[0] if state.conflicts else "")
        state.pending_user_interjection = next(
            (item.content for item in reversed(session.utterances) if item.speaker_id == "user" and item.intent in {"initial", "user_instruction"}),
            "",
        )
        return state

    @staticmethod
    def _refresh_opportunity(session: DiscussionSession) -> None:
        if session.opportunity is None:
            return
        items = [item for item in session.utterances if item.speaker_id not in {"user", "moderator"}]
        session.opportunity.stance_counts = {
            "支持/机会": sum(item.kind == ViewpointKind.OPPORTUNITY for item in items),
            "保留/假设": sum(item.kind in (ViewpointKind.ASSUMPTION, ViewpointKind.FACT) for item in items),
            "风险/反对": sum(item.kind == ViewpointKind.RISK for item in items),
            "验证建议": sum(item.kind == ViewpointKind.VALIDATION for item in items),
        }
        def points(kinds):
            return list(dict.fromkeys(f"{item.speaker_name}：{item.content}" for item in items if item.kind in kinds))[-12:]
        session.opportunity.support = points({ViewpointKind.OPPORTUNITY})
        session.opportunity.risks = points({ViewpointKind.RISK})
        session.opportunity.assumptions = points({ViewpointKind.ASSUMPTION, ViewpointKind.FACT})
        validation = points({ViewpointKind.VALIDATION})
        session.opportunity.next_steps = validation or ["先明确目标人群并安排访谈，核对讨论中的前提", "对比现有替代方案，制作单一场景原型进行验证"]

    @staticmethod
    def _add(session: DiscussionSession, speaker_id: str, speaker_name: str, content: str, kind: ViewpointKind, phase: str, replies_to: str | None = None) -> None:
        session.append_utterance(Utterance(speaker_id, speaker_name, content, kind, phase, replies_to, origin="offline"))
