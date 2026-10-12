"""Qt session orchestration around discussion, optional news, and playback."""

from __future__ import annotations

import inspect
import threading

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from .engine import DiscussionProvider, MockDiscussionProvider
from .llm import GenerationCancelled, ProviderFailure
from .models import DiscussionSession, Role, TrendSource, Utterance, ViewpointKind
from .news import NewsFetchResult, NewsProvider, OfflineNewsProvider
from .playback import DiscussionPlayback, PlaybackState
from .providers import IntegrationStatus
from .storage import SessionStore
from .turn_planner import detect_intervention, mark_duplicates


class _NewsWorker(QObject):
    finished = Signal(object)

    def __init__(self, provider: NewsProvider, topic: str) -> None:
        super().__init__()
        self.provider, self.topic = provider, topic

    @Slot()
    def run(self) -> None:
        try:
            result = self.provider.fetch_with_status(self.topic)
        except Exception as exc:  # network failures must not fail discussion generation
            result = NewsFetchResult([], True, False, f"RSS 获取失败：{type(exc).__name__}", False, False)
        self.finished.emit(result)


class _GenerationWorker(QObject):
    """Run a discussion provider away from the Qt GUI thread."""

    finished = Signal(object, int)
    failed = Signal(object, int)
    partial = Signal(str, str)

    def __init__(self, provider: DiscussionProvider, topic: str, roles: list[Role], source_note: str, token: int, sources: list[TrendSource] | None = None) -> None:
        super().__init__()
        self.provider = provider
        self.topic = topic
        self.roles = roles
        self.source_note = source_note
        self.sources = list(sources or [])
        self.token = token
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            kwargs = {}
            try:
                parameters = inspect.signature(self.provider.discuss).parameters
            except (TypeError, ValueError):
                parameters = {}
            if "cancel_event" in parameters:
                kwargs["cancel_event"] = self.cancel_event
            if "on_partial" in parameters:
                kwargs["on_partial"] = lambda speaker, text: self.partial.emit(str(speaker), str(text))
            if "sources" in parameters:
                kwargs["sources"] = list(self.sources)
            result = self.provider.discuss(self.topic, self.roles, self.source_note, **kwargs)
            if self.cancel_event.is_set():
                raise GenerationCancelled()
            self.finished.emit(result, self.token)
        except BaseException as exc:
            self.failed.emit(exc, self.token)


class _BatchWorker(QObject):
    """Generate one continuation turn away from the GUI thread."""

    finished = Signal(object, int)
    failed = Signal(object, int)
    partial = Signal(str, str)

    def __init__(self, provider, session: DiscussionSession, state, roles: list[Role], token: int) -> None:
        super().__init__()
        self.provider = provider
        self.session = session
        self.state = state
        self.roles = roles
        self.token = token
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self.provider.extend_batch(
                self.session,
                self.state,
                roles=self.roles,
                cancel_event=self.cancel_event,
                on_partial=lambda speaker, text: self.partial.emit(str(speaker), str(text)),
            )
            if self.cancel_event.is_set():
                raise GenerationCancelled()
            self.finished.emit(result, self.token)
        except BaseException as exc:
            self.failed.emit(exc, self.token)


class SessionController(QObject):
    session_ready = Signal(object)
    utterance_changed = Signal(object, int, int)
    playback_state_changed = Signal(str)
    completed = Signal(object)
    error = Signal(str)
    interjection_added = Signal(str)
    news_status_changed = Signal(str)
    news_started = Signal()
    news_finished = Signal(object)
    generation_started = Signal()
    generation_state_changed = Signal(str)
    generation_partial = Signal(str, str)
    discussion_state_changed = Signal(object)
    phase_changed = Signal(str)

    def __init__(self, provider: DiscussionProvider | None = None, store: SessionStore | None = None, news_provider: NewsProvider | None = None, integration_status: IntegrationStatus | None = None) -> None:
        super().__init__()
        self.provider = provider or MockDiscussionProvider()
        self.news_provider = news_provider or OfflineNewsProvider()
        self.integration_status = integration_status or IntegrationStatus()
        self.store = store or SessionStore()
        self.playback = DiscussionPlayback(live=True)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._next)
        self._delay_ms = 2100
        self.manual_advance = True
        self._news_thread: QThread | None = None
        self._news_worker: _NewsWorker | None = None
        self._pending_start: tuple[str, list[Role], str, int] | None = None
        self._start_token = 0
        self._generation_thread: QThread | None = None
        self._generation_worker: _GenerationWorker | None = None
        self._generation_news_result: NewsFetchResult | None = None
        self._generation_topic = ""
        self._generation_roles: list[Role] = []
        self._generation_source_note = ""
        self._discussion_batch = 0
        self._batch_thread: QThread | None = None
        self._batch_worker: _BatchWorker | None = None
        self._batch_token = 0

    @property
    def session(self) -> DiscussionSession | None:
        return self.playback.session

    def start(self, topic: str, roles: list[Role], source_note: str = "", *, fetch_news: bool = False) -> None:
        self._start_token += 1
        token = self._start_token
        self.timer.stop()
        self._pending_start = None
        self.cancel_generation(emit_state=False, invalidate_token=False)
        # A continuation worker belongs to the previous live session. Its
        # token must be invalidated even when the initial generation worker is
        # still in Qt cleanup, otherwise a late model result could land in the
        # newly started topic.
        self._cancel_batch(emit_state=False, invalidate_token=True)
        self._cancel_news_worker()
        if fetch_news and self.integration_status.network_allowed and self.integration_status.news_provider == "rss":
            self._pending_start = (topic, list(roles), source_note, token)
            self._fetch_news_async(topic, token)
            return
        self._start_generation(topic, roles, source_note, token, None)

    def _start_generation(
        self,
        topic: str,
        roles: list[Role],
        source_note: str,
        token: int,
        news_result: NewsFetchResult | None,
    ) -> None:
        if token != self._start_token:
            return
        self.generation_started.emit()
        self.generation_state_changed.emit("running")
        self._generation_thread = QThread(self)
        self._generation_worker = _GenerationWorker(
            self.provider, topic, list(roles), source_note, token,
            list(news_result.sources) if news_result else [],
        )
        self._generation_news_result = news_result
        self._generation_topic = topic
        self._generation_roles = list(roles)
        self._generation_source_note = source_note
        self._generation_worker.moveToThread(self._generation_thread)
        self._generation_thread.started.connect(self._generation_worker.run)
        self._generation_worker.finished.connect(self._generation_finished)
        self._generation_worker.failed.connect(self._generation_failed)
        self._generation_worker.partial.connect(lambda speaker, text, worker_token=token: self._emit_generation_partial(worker_token, speaker, text))
        self._generation_worker.finished.connect(self._generation_thread.quit)
        self._generation_worker.failed.connect(self._generation_thread.quit)
        worker = self._generation_worker
        thread = self._generation_thread
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        # Clear Python references before Qt destroys the C++ thread object.
        thread.finished.connect(lambda: self._generation_cleanup(worker, thread))
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _generation_finished(self, session: DiscussionSession, token: int) -> None:
        if token != self._start_token:
            return
        self._generation_state(session, self._generation_news_result, provider_failed=False)

    def _generation_failed(self, exc: BaseException, token: int) -> None:
        if token != self._start_token:
            return
        if isinstance(exc, GenerationCancelled) or (isinstance(exc, ProviderFailure) and exc.code == "cancelled"):
            self.generation_state_changed.emit("cancelled")
            return
        if isinstance(exc, ValueError):
            self.error.emit(str(exc))
            self.generation_state_changed.emit("error")
            return
        if not isinstance(exc, ProviderFailure):
            self.error.emit("讨论生成失败；请稍后重试")
            self.generation_state_changed.emit("error")
            return
        try:
            session = MockDiscussionProvider().discuss(
                self._generation_topic,
                self._generation_roles,
                self._generation_source_note,
                sources=list(self._generation_news_result.sources) if self._generation_news_result else (),
            )
        except ValueError as validation_error:
            self.error.emit(str(validation_error))
            self.generation_state_changed.emit("error")
            return
        session.fallback_reason = exc.safe_message
        session.generation_status = "fallback"
        self._generation_state(session, self._generation_news_result, provider_failed=True)

    def _generation_state(self, session: DiscussionSession, news_result: NewsFetchResult | None, *, provider_failed: bool) -> None:
        if news_result and news_result.sources:
            existing = {(item.title.casefold(), item.url.casefold()) for item in session.sources}
            session.sources.extend(item for item in news_result.sources if (item.title.casefold(), item.url.casefold()) not in existing)
            session.source = session.source or session.sources[0]
        session.request_mode = self.integration_status.requested_mode
        session.effective_provider = "mock" if provider_failed else self.integration_status.discussion_provider
        session.provider_mode = "offline" if provider_failed else self.integration_status.effective_mode
        session.news_provider = self.integration_status.news_provider
        # Network use means matched RSS material was actually adopted. A
        # partial feed failure can still provide usable sources.
        session.network_used = bool(news_result and news_result.matched)
        session.news_attempted = bool(news_result and news_result.attempted)
        session.news_success = bool(news_result is None or news_result.success)
        session.news_matched = bool(news_result and news_result.matched)
        session.news_partial_failure = bool(news_result and news_result.partial_failure)
        session.status_message = (
            session.fallback_reason
            or (news_result.message if news_result else self.integration_status.describe())
        )
        if news_result and not news_result.success:
            session.fallback_reason = news_result.message
        self._discussion_batch = 0
        self.playback.live = True
        self.playback.start(session)
        self.session_ready.emit(session)
        self.discussion_state_changed.emit(session.discussion_state)
        self.phase_changed.emit(session.phase)
        self._emit_current()
        if news_result is not None:
            self.news_finished.emit(news_result)
        self.generation_state_changed.emit("completed" if not provider_failed else "fallback")

    def cancel_generation(self, *, emit_state: bool = True, invalidate_token: bool = True) -> None:
        if invalidate_token:
            # Invalidate first so a provider that ignores cancel_event cannot
            # publish a late session into the current UI state.
            self._start_token += 1
            self._pending_start = None
        worker = self._generation_worker
        if worker is None:
            self._cancel_batch(emit_state=emit_state, invalidate_token=invalidate_token)
            return
        worker.cancel()
        if emit_state:
            self.generation_state_changed.emit("cancelling")
            self.generation_state_changed.emit("cancelled")

    def _cancel_batch(self, *, emit_state: bool = True, invalidate_token: bool = True) -> None:
        if invalidate_token:
            self._batch_token += 1
        worker = self._batch_worker
        if worker is None:
            return
        worker.cancel()
        if emit_state:
            self.generation_state_changed.emit("cancelling")
            self.generation_state_changed.emit("cancelled")

    @Slot()
    def _generation_cleanup(self, worker: _GenerationWorker, thread: QThread) -> None:
        if self._generation_worker is worker:
            self._generation_worker = None
        if self._generation_thread is thread:
            self._generation_thread = None

    def _emit_generation_partial(self, token: int, speaker: str, text: str) -> None:
        if token == self._start_token:
            self.generation_partial.emit(speaker, text)

    def _fetch_news_async(self, topic: str, token: int) -> None:
        self.news_started.emit()
        self.news_status_changed.emit("正在获取 RSS（来源仍未核验）…")
        self._news_thread = QThread(self)
        self._news_worker = _NewsWorker(self.news_provider, topic)
        self._news_worker.moveToThread(self._news_thread)
        self._news_thread.started.connect(self._news_worker.run)
        self._news_worker.finished.connect(lambda result: self._news_finished(result, token))
        self._news_worker.finished.connect(self._news_thread.quit)
        worker = self._news_worker
        thread = self._news_thread
        worker.finished.connect(worker.deleteLater)
        # Clear Python references before Qt destroys the C++ thread object.
        self._news_thread.finished.connect(lambda: self._news_cleanup(worker, thread))
        self._news_thread.finished.connect(self._news_thread.deleteLater)
        self._news_thread.start()

    def _cancel_news_worker(self) -> None:
        thread = self._news_thread
        self._pending_start = None
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.quit()

    def shutdown(self) -> None:
        """Cancel background work and wait briefly for Qt thread ownership to end."""
        self._start_token += 1
        self._pending_start = None
        self.cancel_generation(emit_state=True, invalidate_token=False)
        self._cancel_batch(emit_state=True, invalidate_token=False)
        self._cancel_news_worker()
        thread = self._generation_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(1500)
        news_thread = self._news_thread
        if news_thread is not None and news_thread.isRunning():
            news_thread.quit()
            news_thread.wait(1500)
        batch_thread = self._batch_thread
        if batch_thread is not None and batch_thread.isRunning():
            batch_thread.quit()
            batch_thread.wait(1500)

    def _news_finished(self, result: NewsFetchResult, token: int) -> None:
        if token != self._start_token or self._pending_start is None:
            return
        topic, roles, source_note, _ = self._pending_start
        self._pending_start = None
        self._start_generation(topic, roles, source_note, token, result)
        self.news_status_changed.emit(result.message)

    @Slot()
    def _news_cleanup(self, worker: _NewsWorker, thread: QThread) -> None:
        if self._news_worker is worker:
            self._news_worker = None
        if self._news_thread is thread:
            self._news_thread = None

    def pause_or_resume(self) -> None:
        if self.playback.state == PlaybackState.PLAYING:
            self.timer.stop(); self.playback.pause()
        elif self.playback.state == PlaybackState.PAUSED:
            self.playback.resume()
            if not self.manual_advance: self._schedule()
        self.playback_state_changed.emit(self.playback.state.value)

    def load(self, session: DiscussionSession, *, replay: bool = False) -> None:
        self._start_token += 1
        self._pending_start = None
        self.cancel_generation(emit_state=False)
        self._cancel_batch(emit_state=False)
        self._cancel_news_worker()
        self.timer.stop(); self.playback.live = False; self.playback.load(session, completed=not replay)
        self.session_ready.emit(session); self.playback_state_changed.emit(self.playback.state.value)
        if replay: self._emit_current()

    def next_step(self) -> None:
        if self.playback.state in (PlaybackState.PLAYING, PlaybackState.PAUSED):
            self.timer.stop()
            if self.playback.live and self.playback.current is not None and self.playback.index >= len(self.playback.session.utterances) - 1:
                self.extend_discussion()
            else:
                was_paused = self.playback.state == PlaybackState.PAUSED
                self.playback.next_step()
                if was_paused:
                    self.playback.pause()
                self._emit_current()

    def skip(self) -> None:
        self.next_step()

    def extend_discussion(self) -> None:
        if self.session is None or self.playback.state == PlaybackState.COMPLETED:
            return
        self._discussion_batch += 1
        if self._batch_worker is not None:
            return
        extender_batch = getattr(self.provider, "extend_batch", None)
        if callable(extender_batch) and self.session.effective_provider != "mock":
            self._start_batch_worker()
            return
        extender = getattr(self.provider, "extend", None)
        if extender is None:
            extender = MockDiscussionProvider().extend
        try:
            extender(self.session, self._discussion_batch)
        except Exception as exc:
            self.error.emit(f"无法继续追加讨论：{type(exc).__name__}")
            return
        if self.session.effective_provider != "mock" and any(item.origin == "offline" for item in self.session.utterances):
            self.session.provider_mode = "mixed"
            self.session.status_message = "首批由模型生成；后续为离线模拟追加，均需核验"
        self.generation_state_changed.emit("continuing")
        self.store.save(self.session)
        self.discussion_state_changed.emit(self.session.discussion_state)
        self.phase_changed.emit(self.session.phase)
        was_paused = self.playback.state == PlaybackState.PAUSED
        self.playback.next_step()
        if was_paused:
            self.playback.pause()
        self._emit_current()

    def _start_batch_worker(self) -> None:
        if self.session is None:
            return
        self._batch_token += 1
        token = self._batch_token
        self.generation_state_changed.emit("continuing")
        self._batch_thread = QThread(self)
        self._batch_worker = _BatchWorker(
            self.provider,
            self.session,
            self.session.discussion_state,
            list(self._generation_roles),
            token,
        )
        self._batch_worker.moveToThread(self._batch_thread)
        self._batch_thread.started.connect(self._batch_worker.run)
        self._batch_worker.finished.connect(self._batch_finished)
        self._batch_worker.failed.connect(self._batch_failed)
        self._batch_worker.partial.connect(lambda speaker, text, batch_token=token: self._emit_batch_partial(batch_token, speaker, text))
        self._batch_worker.finished.connect(self._batch_thread.quit)
        self._batch_worker.failed.connect(self._batch_thread.quit)
        worker = self._batch_worker
        thread = self._batch_thread
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._batch_cleanup(worker, thread))
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _batch_finished(self, items, token: int) -> None:
        if token != self._batch_token or self.session is None:
            return
        self._apply_batch(list(items or []))

    def _batch_failed(self, exc: BaseException, token: int) -> None:
        if token != self._batch_token:
            return
        if isinstance(exc, GenerationCancelled) or (isinstance(exc, ProviderFailure) and exc.code == "cancelled"):
            self.generation_state_changed.emit("cancelled")
            return
        if self.session is not None:
            MockDiscussionProvider().extend(self.session, self._discussion_batch)
            self.session.provider_mode = "mixed"
            self.session.status_message = "模型追加失败；已回退到离线模拟，仍需核验"
            self.session.rebuild_state()
            self.store.save(self.session)
            self.discussion_state_changed.emit(self.session.discussion_state)
            self.phase_changed.emit(self.session.phase)
            was_paused = self.playback.state == PlaybackState.PAUSED
            self.playback.next_step()
            if was_paused:
                self.playback.pause()
            self._emit_current()
            self.error.emit("模型追加失败，已回退到离线模拟")

    def _apply_batch(self, items: list[Utterance]) -> None:
        if self.session is None or not items:
            return
        for item in items:
            self.session.append_utterance(item)
            self.store.save(self.session)
        self.session.rebuild_state()
        mark_duplicates(self.session)
        if any(item.speaker_id == "moderator" and item.phase == "状态整理" for item in items):
            self.session.discussion_state.host_intervention_reason = detect_intervention(self.session)[1]
        elif any(item.speaker_id != "moderator" for item in items):
            self.session.discussion_state.host_intervention_reason = ""
        self.store.save(self.session)
        if self.session.effective_provider != "mock" and any(item.origin == "offline" for item in items):
            self.session.provider_mode = "mixed"
            self.session.status_message = "首批由模型生成；后续含离线模拟追加，均需核验"
        self.discussion_state_changed.emit(self.session.discussion_state)
        self.phase_changed.emit(self.session.phase)
        was_paused = self.playback.state == PlaybackState.PAUSED
        self.playback.next_step()
        if was_paused:
            self.playback.pause()
        self._emit_current()

    def _emit_batch_partial(self, token: int, speaker: str, text: str) -> None:
        if token == self._batch_token:
            self.generation_partial.emit(speaker, text)

    @Slot()
    def _batch_cleanup(self, worker: _BatchWorker, thread: QThread) -> None:
        if self._batch_worker is worker:
            self._batch_worker = None
        if self._batch_thread is thread:
            self._batch_thread = None

    def finish_discussion(self) -> None:
        if self.session is None or self.playback.state == PlaybackState.COMPLETED:
            return
        self.timer.stop()
        self.session.utterances[:] = [
            item for index, item in enumerate(self.session.utterances)
            if index <= self.playback.index or item.speaker_id == "user"
        ]
        MockDiscussionProvider._refresh_opportunity(self.session)
        self.session.generation_status = "user_finished"
        self.playback.finish()
        self.store.save(self.session)
        self.playback_state_changed.emit(self.playback.state.value)
        self.completed.emit(self.session)

    def add_interjection(self, text: str) -> None:
        cleaned = " ".join(text.split())
        if not cleaned or self.session is None or self.playback.state == PlaybackState.COMPLETED: return
        position = self.playback.index + 1
        item = Utterance("user", "用户", cleaned, ViewpointKind.ASSUMPTION, "用户插话", simulated=False, origin="user", intent="user_instruction")
        # Allocate from the session's monotonic event allocator before
        # inserting into the playback order. Existing objects and identifiers
        # remain stable, so an active playback cursor can safely point at them.
        item = self.session.append_utterance(item)
        self.session.utterances.pop()
        self.session.utterances.insert(min(position, len(self.session.utterances)), item)
        self.session.rebuild_state()
        self.store.save(self.session)
        self.discussion_state_changed.emit(self.session.discussion_state)
        self.phase_changed.emit(self.session.phase)
        # Record this intervention immediately, between the utterances that
        # have already happened and those still waiting to be presented.
        self.timer.stop()
        self.playback.index = position
        self._emit_current()
        self.interjection_added.emit(cleaned)

    def save(self) -> None:
        if self.session is not None: self.store.save(self.session)

    def _next(self) -> None:
        if self.playback.state != PlaybackState.PLAYING:
            return
        self.next_step()

    def _emit_current(self) -> None:
        current = self.playback.current
        if current is None:
            if self.playback.state == PlaybackState.COMPLETED and self.session:
                self.store.save(self.session); self.completed.emit(self.session)
            self.playback_state_changed.emit(self.playback.state.value); return
        self.utterance_changed.emit(current, self.playback.index, len(self.session.utterances))
        self.playback_state_changed.emit(self.playback.state.value)
        if not self.manual_advance: self._schedule()

    def _schedule(self) -> None:
        if self.playback.state == PlaybackState.PLAYING:
            current = self.playback.current
            # Give long Chinese arguments enough time to be read.
            delay = max(self._delay_ms, min(18000, 1600 + len(current.content) * 95)) if current else self._delay_ms
            self.timer.start(delay)
