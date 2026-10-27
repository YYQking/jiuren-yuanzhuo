"""Domain models for the offline brainstorming prototype."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Optional


class Participation(str, Enum):
    ACTIVE = "参与"
    OBSERVER = "旁听"
    PAUSED = "暂停"


class ViewpointKind(str, Enum):
    FACT = "事实"
    ASSUMPTION = "假设"
    OPPORTUNITY = "机会"
    RISK = "风险"
    VALIDATION = "待验证"
    SUMMARY = "总结"


# How long a user interjection keeps steering the discussion, in utterances.
# Lives here because both the scheduler (rule 1) and the prompt-building state
# derivation must agree on it; when they disagreed, an interjection the planner
# had already expired was still being fed to every later turn as a live
# instruction.
USER_INTERJECTION_WINDOW = 6


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    duty: str
    color: str
    prompt: str
    # Only the event-discussion seats carry trigram material; the business seats
    # leave these empty so their prompts stay exactly as they were.
    trigram: str = ""
    yang: str = ""
    yin: str = ""
    # How this seat talks, as opposed to what it is responsible for.  Without it
    # every seat produced the same four-beat paragraph (pick up the thread, take
    # a side, add a "but", ask a question), which is what made a table of nine
    # people read like nine copies of one template.
    voice: str = ""


@dataclass(frozen=True)
class TrendSource:
    title: str
    url: str = ""
    note: str = ""
    credibility: str = "未核验"
    source_type: str = "unknown"
    fetched_at: Optional[datetime] = None
    published_at: Optional[datetime] = None


@dataclass(frozen=True)
class StanceChange:
    before: str
    after: str
    reason: str
    triggered_by: list[str] = field(default_factory=list)


@dataclass
class DiscussionState:
    consensus: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    duplicate_count: int = 0
    new_information_density: float = 1.0
    active_thread: str = ""
    host_intervention_reason: str = ""
    role_stances: dict[str, str] = field(default_factory=dict)
    pending_user_interjection: str = ""


@dataclass(frozen=True)
class Reaction:
    """One note in the temper ledger: this sentence landed on somebody.

    ``delta`` is a small step (-2..2), ``why`` is the model's own reason in
    plain words.  Notes live on the utterance that caused them, so the ledger
    is a pure function of the transcript.
    """

    seat_id: str
    delta: int
    why: str


@dataclass(frozen=True)
class Utterance:
    speaker_id: str
    speaker_name: str
    content: str
    kind: ViewpointKind
    phase: str
    replies_to: Optional[str] = None
    simulated: bool = True
    origin: str = ""
    event_id: str = ""
    sequence: int = -1
    intent: str = "initial"
    verification: str = "unverified"
    stance_change: StanceChange | None = None
    duplicate: bool = False
    # Set when the quality review sent this turn back for one rewrite, so the
    # record shows that the review ran instead of hiding it.
    review_note: str = ""
    # Event section only: which side of the five-element/trigram pair is showing.
    # ``yang`` / ``yin`` / "" (unknown, treat as whatever the speaker showed last).
    face: str = ""
    # Temper ledger entries this sentence caused (see ``brainstorm.mood``).
    reactions: tuple[Reaction, ...] = field(default_factory=tuple)


@dataclass
class OpportunityCard:
    title: str
    audience: str
    support: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    stance_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class DiscussionSession:
    topic: str
    source: Optional[TrendSource] = None
    sources: list[TrendSource] = field(default_factory=list)
    utterances: list[Utterance] = field(default_factory=list)
    opportunity: Optional[OpportunityCard] = None
    created_at: datetime = field(default_factory=datetime.now)
    selected_role_ids: list[str] = field(default_factory=list)
    # "business" (nine occupational seats) or "event" (eight trigram people).
    # Old archives have no such key and must keep reading as business.
    mode: str = "business"
    # provider_mode is retained for v1/v2 compatibility.  It describes the
    # effective discussion provider, not merely what the user requested.
    provider_mode: str = "offline"
    fallback_reason: str = ""
    request_mode: str = "offline"
    effective_provider: str = "mock"
    news_provider: str = "offline"
    network_used: bool = False
    news_attempted: bool = False
    news_success: bool = True
    news_matched: bool = False
    news_partial_failure: bool = False
    status_message: str = "离线模拟；未使用网络"
    model_name: str = ""
    generation_status: str = "offline"
    generation_stage: str = ""
    generation_streamed: bool = False
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0
    usage_requests: int = 0
    phase: str = "开题"
    run_state: str = "live"
    discussion_state: DiscussionState = field(default_factory=DiscussionState)

    def next_sequence(self) -> int:
        return max((item.sequence for item in self.utterances), default=-1) + 1

    def append_utterance(self, item: Utterance) -> Utterance:
        sequence = self.next_sequence() if item.sequence < 0 else item.sequence
        event_id = item.event_id or f"event-{sequence:06d}"
        item = replace(item, event_id=event_id, sequence=sequence)
        self.utterances.append(item)
        self.phase = self._phase_for(item.phase)
        return item

    def pending_interjection(self, window: int = 0) -> Optional[Utterance]:
        """The user interjection that is still steering this discussion.

        An interjection stops being pending once a later turn replies to it, and
        expires after ``window`` further utterances have been recorded.  ``window``
        of 0 means "no expiry".
        """
        replied = {item.replies_to for item in self.utterances if item.replies_to}
        for index in range(len(self.utterances) - 1, -1, -1):
            item = self.utterances[index]
            if item.speaker_id != "user" or item.intent != "user_instruction":
                continue
            if item.event_id in replied:
                return None
            if window and len(self.utterances) - 1 - index >= window:
                return None
            return item
        return None

    def rebuild_state(self) -> DiscussionState:
        """Rebuild the cheap persisted snapshot; providers may enrich it."""
        self.discussion_state.role_stances = {
            item.speaker_id: item.content
            for item in self.utterances
            if item.speaker_id not in {"moderator", "user"}
        }
        interjection = self.pending_interjection(USER_INTERJECTION_WINDOW)
        self.discussion_state.pending_user_interjection = interjection.content if interjection else ""
        if self.utterances:
            self.phase = self._phase_for(self.utterances[-1].phase)
        return self.discussion_state

    @staticmethod
    def _phase_for(phase: str) -> str:
        if phase in {"开场", "主持人开题"}:
            return "开题"
        if phase in {"独立观点", "首轮观点"}:
            return "首轮观点"
        if phase in {"阶段总结", "阶段收束", "状态整理"}:
            return "状态整理"
        if phase:
            return "动态交锋"
        return "开题"

    def utterance_source(self, item: Utterance) -> str:
        if item.speaker_id == "user":
            return "用户内容"
        origin = item.origin or ("offline" if self.effective_provider == "mock" else "model")
        return "离线模拟" if origin == "offline" else "模型生成"

    @property
    def content_label(self) -> str:
        origins = {self.utterance_source(item) for item in self.utterances if item.speaker_id != "user"}
        if {"离线模拟", "模型生成"} <= origins:
            return "模型生成 + 离线模拟 · 仍需核验"
        return f"{'模型生成' if '模型生成' in origins else '离线模拟'} · 仍需核验"

    @property
    def viewpoint_source_description(self) -> str:
        """Explain how role language was produced without presenting inference as news."""
        origins = {self.utterance_source(item) for item in self.utterances if item.speaker_id != "user"}
        if self.mode == "event":
            lines = ["八个席位是同一模型扮演的八种说话方式，并非八个独立的真实 AI。"]
            lines.append("席位性格来自八卦的传统引申（说卦传的性与类象），不是心理学测评，也不能拿来判断真人。")
        elif self.mode == "claim":
            lines = ["八个席位是同一模型扮演的八种拆解位置，并非八个独立的真实 AI。"]
            lines.append("他们站在同一个说法的不同位置上：有人替它说话，有人找反例，不是八个人的真实意见。")
        else:
            lines = ["九个角色代表不同职责视角，并非九个独立的真实 AI。"]
        if "模型生成" in origins:
            lines.append("模型发言由同一模型服务按角色职责、提示词、主题、前文、用户插话和提供的素材生成。")
        if "离线模拟" in origins or not origins:
            lines.append("离线发言来自程序内的预设角色模板：首轮套用主题，续轮结合前文和用户插话组织回应。")
        if any(item.source_type == "rss" for item in self.sources):
            lines.append("RSS 是单独保存的外部新闻线索；模板模式只展示素材，不进行新闻语义分析。")
        lines.append("角色观点不是新闻原文，也不是已核验事实；来源列表不代表每条发言都有对应新闻证据。")
        return "\n".join(lines)
