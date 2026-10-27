"""Provider seams and the deterministic offline discussion engine."""

from collections.abc import Iterable, Sequence
import re
from dataclasses import dataclass
from typing import Protocol

from .models import DiscussionSession, OpportunityCard, Participation, Reaction, Role, StanceChange, TrendSource, Utterance, ViewpointKind
from .mood import resolve_face
from .roles import mode_for_roles


def _face_after(history: Sequence[Utterance], speaker_id: str) -> str:
    """The face a seat shows next in an offline event discussion.

    Same rule as the live model: the side follows the temper ledger, so a seat
    only turns sour after something in the transcript actually landed on it.
    """
    return resolve_face(history, speaker_id)



# How a purely offline discussion keeps tempers moving: every few turns one
# sentence lands on the next speaker.  ``None`` means "this one landed softly".
_EXTEND_NOTES: tuple[tuple[int, str] | None, ...] = (
    None,
    (-1, "他刚才那句顶到你了"),
    None,
    (1, "他替你把话接过去了，你觉得还行"),
    None,
    (-1, "他一直在打断你，你烦了"),
)


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

        session = DiscussionSession(topic=topic.strip(), selected_role_ids=[role.id for role in selected],
                                   mode=mode_for_roles(selected))
        if source_note.strip():
            session.source = TrendSource(title="用户提供的前沿线索", note=source_note.strip(), source_type="user")
            session.sources.append(session.source)
        for item in sources:
            if (item.title.casefold(), item.url.casefold()) not in {(source.title.casefold(), source.url.casefold()) for source in session.sources}:
                session.sources.append(item)
                session.source = session.source or item
        if session.mode == "event":
            self._event_opening(session, selected)
            return session
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

    _EVENT_INTENT = {
        ViewpointKind.RISK: "challenge",
        ViewpointKind.VALIDATION: "question",
        ViewpointKind.OPPORTUNITY: "elaborate",
        ViewpointKind.ASSUMPTION: "elaborate",
        ViewpointKind.FACT: "elaborate",
        ViewpointKind.SUMMARY: "synthesize",
    }

    def _event_opening(self, session: DiscussionSession, selected: Sequence[Role]) -> None:
        """Offline event opening: many voices, a visible flip, honest ignorance.

        Nothing here claims a real source.  Offline mode has to show the *shape*
        of the conversation -- several people talking over each other, a seat
        turning its 阴面, speakers saying plainly what they do not know -- and
        must never invent news.
        """
        topic = session.topic
        self._add(
            session, "moderator", "主持人",
            f"今天聊一件事：“{topic}”。桌上八个人，谁也不是当事人。"
            "规矩先讲清楚：我确定的就说“我知道”，听来的就说“听说”，瞎猜的就说“我猜”。"
            "（离线演示，下面这些话没有真实来源）",
            ViewpointKind.SUMMARY, "开题",
        )
        if session.source is not None:
            material = session.source.note or session.source.title
            self._add(
                session, "moderator", "主持人",
                f"桌上还有份材料：“{material[:200]}”。当它是线索，别当它是真相。",
                ViewpointKind.ASSUMPTION, "开题",
            )
        openers = {
            "qian": (ViewpointKind.OPPORTUNITY, "开头我先给个态度：“{topic}”这事不是小事，别急着站队。我知道的就是公开那几条，听说的比知道的多。真要出事，多半出在没人愿意先开口的那一环。"),
            "kun": (ViewpointKind.ASSUMPTION, "我不爱把话说死。听说的情况是：当事人身边的人都不好受，可谁也不想先出头。要我说，先把人照顾好，再论谁对谁错。"),
            "zhen": (ViewpointKind.RISK, "我一听就来气。“{topic}”要是真像传的那样，那就不是小事。不过话我先说在前面：我这是听说，别拿它当实锤再往外传。"),
            "xun": (ViewpointKind.ASSUMPTION, "我这儿版本多一点，可我不敢打包票。有说这样的，有说那样的，两个说法差得挺远。我猜中间还有一段没人讲。"),
            "kan": (ViewpointKind.VALIDATION, "先泼盆冷水。现在桌上说的，一半是猜的。真要判断，得看时间、看谁先说的、看有没有第二个人能对上。"),
            "li": (ViewpointKind.OPPORTUNITY, "我站当事人那边说一句：不管最后怎么定性，被人这么议论本身就够伤的。"),
            "gen": (ViewpointKind.VALIDATION, "我不太掺和。就一句：没核实的事，别往外传。"),
            "dui": (ViewpointKind.ASSUMPTION, "这事要让我讲，能讲成段子。但段子归段子，我其实知道得不多，听说的居多。"),
        }
        for role in selected:
            kind, text = openers.get(
                role.id,
                (ViewpointKind.ASSUMPTION, "对“{topic}”这事，我知道的不多，只能说说听来的那部分。"),
            )
            self._add_face(session, role.id, role.name, text.format(topic=topic), kind, "各自开口", "yang")
        by_id = {role.id: role for role in selected}
        # Each entry is (seat, kind, words, reply_to, note).  The note records who
        # *this* sentence landed on, so the next speaker walks in already annoyed
        # -- the offline demo has to show the ledger working, not just four
        # characters labelled 阴面.
        exchanges: list[tuple[str, ViewpointKind, str, str | None, tuple[str, int, str] | None]] = [
            ("kun", ViewpointKind.ASSUMPTION, "我说句软话：不管最后怎么说，现在就有人吃不下睡不着。先把人顾住，再论对错。", None, None),
            ("qian", ViewpointKind.SUMMARY, "我拍个板：在有人拿出第二份说法之前，谁也别替当事人定性。传出去就说是桌上瞎聊的。", "kun",
             ("zhen", -1, "他一句“谁也别替当事人定性”，你听着像在压着人不让说")),
            ("gen", ViewpointKind.VALIDATION, "我就一句：没核实的事别往外传。你们吵归吵，这条别破。", "qian",
             ("dui", -1, "他张口就是“别往外传”，你觉得这人真没劲")),
            ("zhen", ViewpointKind.RISK, "我刚听说一版特别难听的，越听越来气——当然我没证实，谁证实了跟我说一声。", "gen",
             ("kan", -1, "他专挑最坏那种可能说，你听着像在拿没影的事吓人")),
            ("kan", ViewpointKind.RISK, "你要我说，最坏的那种可能还没人提。真走到那一步，今天在这儿替人说话的一个都跑不掉。", "zhen",
             ("li", -1, "他说替人说话的“一个都跑不掉”，你听着像在怪你")),
            ("li", ViewpointKind.RISK, "刚才是谁说我想多了？行，那我就不客气了。", "kan",
             ("kun", -1, "她翻脸那一下，你觉得这张桌要炸")),
            ("dui", ViewpointKind.ASSUMPTION, "我补一句：传得最快的那版，恰恰是没人核过的那版。", "li",
             ("gen", -1, "他把这事当段子讲，你最听不得有人不拿它当回事")),
        ]
        recent_reply = ""
        for seat, kind, text, reply_to, note in exchanges:
            role = by_id.get(seat)
            if role is None:
                continue
            face = _face_after(session.utterances, seat)
            reactions = (Reaction(*note),) if note else ()
            added = self._add_face(
                session, role.id, role.name, text, kind, "各说各话", face,
                reply_to or recent_reply or None, reactions,
            )
            recent_reply = added.event_id
        self._add(
            session, "moderator", "主持人",
            "先停一下。有人先护着人说话，也有人已经往最坏处想了。"
            "现在能确认的没几条，谁也别说自己手里是实锤。",
            ViewpointKind.SUMMARY, "阶段整理",
        )
        session.opportunity = OpportunityCard(
            title=f"“{topic}”到底算什么",
            audience="当事人（化名）和围着这件事说话的人（离线演示）",
            support=["（离线演示）大家嘴上认的那部分事实，其实没几个人说得清"],
            risks=["几个版本互相打架，谁也没有第二个人能对上", "吵到后面已经从事情本身吵到人的品行"],
            assumptions=["传得最凶的那一版还没人证实", "当事人到现在没有公开回应"],
            next_steps=["等一个能对上时间的公开说法", "看当事人或相关方会不会回应"],
            stance_counts={},
        )
        session.phase = "首轮观点"

    def _event_extend(self, session: DiscussionSession, batch_index: int) -> list[Utterance]:
        seats: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in session.utterances:
            if item.speaker_id in {"moderator", "user"} or item.speaker_id in seen:
                continue
            seen.add(item.speaker_id)
            seats.append((item.speaker_id, item.speaker_name))
        if not seats:
            return []
        index = max(1, batch_index) - 1
        seats = seats[(index * 2) % len(seats):] + seats[:(index * 2) % len(seats)]
        pool = [
            (ViewpointKind.ASSUMPTION, "接着聊", "我这边又听到一个新说法，跟前面那个对不上。我不敢保证，但这条要是真的，前面的判断就得改。"),
            (ViewpointKind.RISK, "互怼", "我就是不信这么快就有结论。谁先说的？谁证明的？说不出来就别急着站队。"),
            (ViewpointKind.VALIDATION, "追问", "先别急着骂人。把时间捋一遍：什么时候、谁在场、谁说给谁的；对不上就先搁着。"),
            (ViewpointKind.OPPORTUNITY, "转向", "我倒是觉得，这事最后怎么收场，比谁对谁错更值得看。"),
            (ViewpointKind.ASSUMPTION, "翻旧账", "我记得前面有人拍过胸脯保证过什么，现在这个说法一出来，那句话还算数吗？"),
            (ViewpointKind.SUMMARY, "收一收", "先归拢一下：现在能对上的只有一条，剩下的都还是听说的。"),
            (ViewpointKind.RISK, "换个角度", "就算这事最后证明是真的，我也想知道：是谁先把它捅出来的，图什么。"),
            (ViewpointKind.VALIDATION, "留个尾巴", "我只有一句：别今天吵完就散了，过两天有新说法，记得回来对一遍。"),
        ]
        added: list[Utterance] = []
        previous_id = ""
        for offset, (speaker_id, speaker_name) in enumerate(seats):
            kind, phase, text = pool[(offset + index) % len(pool)]
            face = _face_after(session.utterances, speaker_id)
            # Every few turns one sentence lands on the next speaker, so a purely
            # offline discussion still shows tempers drifting.
            drift = _EXTEND_NOTES[(offset + index) % len(_EXTEND_NOTES)]
            reactions: tuple[Reaction, ...] = ()
            if drift is not None:
                target = seats[(offset + 1) % len(seats)][0]
                reactions = (Reaction(target, drift[0], drift[1]),)
            item = self._add_face(
                session, speaker_id, speaker_name, text, kind, phase, face,
                previous_id or None, reactions,
            )
            previous_id = item.event_id
            added.append(item)
        self._refresh_opportunity(session)
        session.rebuild_state()
        session.phase = "各说各话"
        return added

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
        if session.mode == "event":
            return self._event_extend(session, batch_index)
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
    def _add(session: DiscussionSession, speaker_id: str, speaker_name: str, content: str, kind: ViewpointKind, phase: str, replies_to: str | None = None) -> Utterance:
        return session.append_utterance(Utterance(speaker_id, speaker_name, content, kind, phase, replies_to, origin="offline"))

    @classmethod
    def _add_face(cls, session: DiscussionSession, speaker_id: str, speaker_name: str, content: str,
                  kind: ViewpointKind, phase: str, face: str, replies_to: str | None = None,
                  reactions: tuple[Reaction, ...] = ()) -> Utterance:
        """An offline event turn, carrying the face it was spoken in."""
        return session.append_utterance(Utterance(
            speaker_id, speaker_name, content, kind, phase, replies_to,
            origin="offline", face=face, intent=cls._EVENT_INTENT.get(kind, "elaborate"),
            reactions=reactions,
        ))
