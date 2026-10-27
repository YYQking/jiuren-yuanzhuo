"""Small local persistence layer for roundtable sessions."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import DiscussionSession, DiscussionState, OpportunityCard, Reaction, StanceChange, TrendSource, Utterance, ViewpointKind
from .roles import MODE_LABELS, mode_for_roles

SCHEMA_VERSION = 6


def _reactions_from_data(raw: Any) -> tuple[Reaction, ...]:
    """Read temper-ledger notes; junk entries are skipped, never fatal."""
    if not isinstance(raw, list):
        return ()
    notes: list[Reaction] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        seat = str(entry.get("seat_id") or entry.get("seat") or "").strip()
        try:
            delta = int(entry.get("delta"))
        except (TypeError, ValueError):
            continue
        why = str(entry.get("why") or "").strip()
        if not seat or not why:
            continue
        notes.append(Reaction(seat_id=seat, delta=delta, why=why))
    return tuple(notes)


def _default_dir() -> Path:
    base = Path.home() / "九人圆桌"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _source_to_dict(source: TrendSource) -> dict[str, Any]:
    data = asdict(source)
    for key in ("fetched_at", "published_at"):
        if isinstance(data.get(key), datetime):
            data[key] = data[key].isoformat()
    return data


def _source_from_dict(data: dict[str, Any]) -> TrendSource:
    values = dict(data)
    for key in ("fetched_at", "published_at"):
        value = values.get(key)
        if isinstance(value, str):
            try:
                values[key] = datetime.fromisoformat(value)
            except ValueError:
                values[key] = None
    return TrendSource(**values)


def session_to_dict(session: DiscussionSession) -> dict[str, Any]:
    source = _source_to_dict(session.source) if session.source else None
    return {
        "schema_version": SCHEMA_VERSION,
        "topic": session.topic,
        "source": source,
        "sources": [_source_to_dict(item) for item in session.sources],
        "viewpoint_source_description": session.viewpoint_source_description,
        "provider_mode": session.provider_mode,
        "fallback_reason": session.fallback_reason,
        "request_mode": session.request_mode,
        "effective_provider": session.effective_provider,
        "news_provider": session.news_provider,
        "network_used": session.network_used,
        "news_attempted": session.news_attempted,
        "news_success": session.news_success,
        "news_matched": session.news_matched,
        "news_partial_failure": session.news_partial_failure,
        "status_message": session.status_message,
        "model_name": session.model_name,
        "generation_status": session.generation_status,
        "generation_stage": session.generation_stage,
        "generation_streamed": session.generation_streamed,
        "usage_input_tokens": session.usage_input_tokens,
        "usage_output_tokens": session.usage_output_tokens,
        "usage_requests": session.usage_requests,
        "selected_role_ids": session.selected_role_ids,
        "mode": session.mode,
        "phase": session.phase,
        "run_state": session.run_state,
        "discussion_state": {
            "consensus": list(session.discussion_state.consensus),
            "conflicts": list(session.discussion_state.conflicts),
            "unresolved_questions": list(session.discussion_state.unresolved_questions),
            "duplicate_count": session.discussion_state.duplicate_count,
            "new_information_density": session.discussion_state.new_information_density,
            "active_thread": session.discussion_state.active_thread,
            "host_intervention_reason": session.discussion_state.host_intervention_reason,
            "role_stances": dict(session.discussion_state.role_stances),
            "pending_user_interjection": session.discussion_state.pending_user_interjection,
        },
        "created_at": session.created_at.isoformat(),
        "utterances": [
            {
                "speaker_id": item.speaker_id,
                "speaker_name": item.speaker_name,
                "content": item.content,
                "kind": item.kind.value,
                "phase": item.phase,
                "replies_to": item.replies_to,
                "simulated": item.simulated,
                "origin": item.origin,
                "event_id": item.event_id,
                "face": item.face,
                "sequence": item.sequence,
                "intent": item.intent,
                "verification": item.verification,
                "stance_change": {
                    "before": item.stance_change.before,
                    "after": item.stance_change.after,
                    "reason": item.stance_change.reason,
                    "triggered_by": list(item.stance_change.triggered_by),
                } if item.stance_change else None,
                "duplicate": item.duplicate,
                "review_note": item.review_note,
                "reactions": [
                    {"seat_id": note.seat_id, "delta": note.delta, "why": note.why}
                    for note in item.reactions
                ],
            }
            for item in session.utterances
        ],
        "opportunity": asdict(session.opportunity) if session.opportunity else None,
    }


def session_from_dict(data: dict[str, Any]) -> DiscussionSession:
    if not isinstance(data, dict):
        raise TypeError("session data must be an object")
    schema_version = data.get("schema_version", 1)
    try:
        schema_version = int(schema_version)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid schema_version") from exc
    if schema_version > SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    topic = str(data.get("topic", "")).strip()
    if not topic:
        raise ValueError("session topic is required")
    source_data = data.get("source")
    source = _source_from_dict(source_data) if isinstance(source_data, dict) else None
    sources = [_source_from_dict(item) for item in data.get("sources", []) if isinstance(item, dict)]
    opportunity_data = data.get("opportunity")
    if isinstance(opportunity_data, dict):
        try:
            opportunity = OpportunityCard(
                title=str(opportunity_data["title"]),
                audience=str(opportunity_data["audience"]),
                support=[str(item) for item in opportunity_data.get("support", [])],
                risks=[str(item) for item in opportunity_data.get("risks", [])],
                assumptions=[str(item) for item in opportunity_data.get("assumptions", [])],
                next_steps=[str(item) for item in opportunity_data.get("next_steps", [])],
                stance_counts={str(key): int(value) for key, value in opportunity_data.get("stance_counts", {}).items()},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid opportunity") from exc
    else:
        opportunity = None
    utterances = []
    for sequence, item in enumerate(data.get("utterances", [])):
        if not isinstance(item, dict):
            continue
        try:
            kind = ViewpointKind(item["kind"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("invalid utterance kind") from exc
        try:
            raw_change = item.get("stance_change")
            stance_change = StanceChange(
                before=str(raw_change.get("before", "")),
                after=str(raw_change.get("after", "")),
                reason=str(raw_change.get("reason", "")),
                triggered_by=[str(value) for value in raw_change.get("triggered_by", [])],
            ) if isinstance(raw_change, dict) else None
            utterances.append(Utterance(
                speaker_id=str(item["speaker_id"]),
                speaker_name=str(item["speaker_name"]),
                content=str(item["content"]),
                kind=kind,
                phase=str(item["phase"]),
                replies_to=item.get("replies_to"),
                simulated=bool(item.get("simulated", True)),
                origin=str(item.get("origin", "")),
                event_id=str(item.get("event_id", "") or f"event-{sequence:06d}"),
                face=str(item.get("face", "")),
                sequence=int(item.get("sequence", sequence)),
                intent=str(item.get("intent", "initial")),
                verification=str(item.get("verification", "unverified")),
                stance_change=stance_change,
                duplicate=bool(item.get("duplicate", False)),
                review_note=str(item.get("review_note", "")),
                reactions=_reactions_from_data(item.get("reactions")),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid utterance") from exc
    state_data = data.get("discussion_state")
    if not isinstance(state_data, dict):
        state_data = {}
    discussion_state = DiscussionState(
        consensus=[str(value) for value in state_data.get("consensus", [])],
        conflicts=[str(value) for value in state_data.get("conflicts", [])],
        unresolved_questions=[str(value) for value in state_data.get("unresolved_questions", [])],
        duplicate_count=max(0, int(state_data.get("duplicate_count", 0) or 0)),
        new_information_density=float(state_data.get("new_information_density", 1.0) or 0.0),
        active_thread=str(state_data.get("active_thread", "")),
        host_intervention_reason=str(state_data.get("host_intervention_reason", "")),
        role_stances={str(key): str(value) for key, value in state_data.get("role_stances", {}).items()},
        pending_user_interjection=str(state_data.get("pending_user_interjection", "")),
    )
    try:
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid created_at") from exc
    selected = data.get("selected_role_ids", [])
    selected_ids = [str(item) for item in selected] if isinstance(selected, list) else []
    stored_mode = str(data.get("mode", "") or "")
    if stored_mode not in MODE_LABELS:
        # Pre-mode archives: an event session is the one whose seats are trigrams.
        stored_mode = mode_for_roles(selected_ids) if selected_ids else "business"
    return DiscussionSession(mode=stored_mode,
        topic=topic,
        source=source,
        sources=sources,
        utterances=utterances,
        opportunity=opportunity,
        created_at=created_at,
        selected_role_ids=selected_ids,
        provider_mode=str(data.get("provider_mode", "offline")),
        fallback_reason=str(data.get("fallback_reason", "")),
        request_mode=str(data.get("request_mode", data.get("provider_mode", "offline"))),
        effective_provider=str(data.get("effective_provider", "mock")),
        news_provider=str(data.get("news_provider", "offline")),
        network_used=bool(data.get("network_used", False)),
        news_attempted=bool(data.get("news_attempted", False)),
        news_success=bool(data.get("news_success", True)),
        news_matched=bool(data.get("news_matched", bool(sources))),
        news_partial_failure=bool(data.get("news_partial_failure", False)),
        status_message=str(data.get("status_message", "离线模拟；未使用网络")),
        model_name=str(data.get("model_name", "")),
        generation_status=str(data.get("generation_status", "offline")),
        generation_stage=str(data.get("generation_stage", "")),
        generation_streamed=bool(data.get("generation_streamed", False)),
        usage_input_tokens=max(0, int(data.get("usage_input_tokens", 0) or 0)),
        usage_output_tokens=max(0, int(data.get("usage_output_tokens", 0) or 0)),
        usage_requests=max(0, int(data.get("usage_requests", 0) or 0)),
        phase=str(data.get("phase", "开题")),
        run_state=str(data.get("run_state", "live")),
        discussion_state=discussion_state,
    )


class SessionStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _default_dir()
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, session: DiscussionSession) -> Path:
        stamp = session.created_at.strftime("%Y%m%d-%H%M%S-%f")
        path = self.directory / f"{stamp}.json"
        # Replace atomically so a crash cannot leave a truncated history entry.
        fd, temporary = tempfile.mkstemp(prefix=f".{stamp}-", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(session_to_dict(session), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path

    def list_paths(self) -> list[Path]:
        return sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)

    def list_sessions(self) -> list[DiscussionSession]:
        sessions: list[DiscussionSession] = []
        for path in self.list_paths():
            try:
                sessions.append(session_from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return sessions

    def load(self, path: Path) -> DiscussionSession:
        return session_from_dict(json.loads(path.read_text(encoding="utf-8")))
