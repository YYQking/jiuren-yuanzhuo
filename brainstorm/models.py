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


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    duty: str
    color: str
    prompt: str


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

    def rebuild_state(self) -> DiscussionState:
        """Rebuild the cheap persisted snapshot; providers may enrich it."""
        self.discussion_state.role_stances = {
            item.speaker_id: item.content
            for item in self.utterances
            if item.speaker_id not in {"moderator", "user"}
        }
        self.discussion_state.pending_user_interjection = next(
            (item.content for item in reversed(self.utterances)
             if item.speaker_id == "user" and item.intent == "user_instruction"),
            "",
        )
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
        lines = ["九个角色代表不同职责视角，并非九个独立的真实 AI。"]
        if "模型生成" in origins:
            lines.append("模型发言由同一模型服务按角色职责、提示词、主题、前文、用户插话和提供的素材生成。")
        if "离线模拟" in origins or not origins:
            lines.append("离线发言来自程序内的预设角色模板：首轮套用主题，续轮结合前文和用户插话组织回应。")
        if any(item.source_type == "rss" for item in self.sources):
            lines.append("RSS 是单独保存的外部新闻线索；模板模式只展示素材，不进行新闻语义分析。")
        lines.append("角色观点不是新闻原文，也不是已核验事实；来源列表不代表每条发言都有对应新闻证据。")
        return "\n".join(lines)
