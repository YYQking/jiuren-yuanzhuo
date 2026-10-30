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
from .orchestration import derive_state
from .roles import mode_for_roles
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
    turn_ready = Signal(object, int, int, int)

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
            if "on_turn" in parameters:
                # The opening batch is many sequential requests. Handing each
                # finished turn straight to the GUI thread lets the roundtable
                # appear after the first one instead of after all of them.
                kwargs["on_turn"] = lambda utterance, done, total: self.turn_ready.emit(
                    utterance, int(done), int(total), self.token
                )
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
    generation_progress = Signal(int, int)
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
        # Set while the opening batch is still streaming turns in. Owned by the
        # GUI thread: the worker sends finished turns over, it never touches this.
        self._live_session: DiscussionSession | None = None
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
        self._live_session = None
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
        self._live_session = self._new_live_session(topic, roles, source_note, news_result)
        self._generation_worker.moveToThread(self._generation_thread)
        self._generation_thread.started.connect(self._generation_worker.run)
        self._generation_worker.finished.connect(self._generation_finished)
        self._generation_worker.failed.connect(self._generation_failed)
        self._generation_worker.partial.connect(lambda speaker, text, worker_token=token: self._emit_generation_partial(worker_token, speaker, text))
        self._generation_worker.turn_ready.connect(self._generation_turn)
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

    def _new_live_session(self, topic: str, roles: list[Role], source_note: str,
                          news_result: NewsFetchResult | None) -> DiscussionSession | None:
        """The session the GUI shows while the opening batch is still arriving.

        Only created when the provider can report turns as they finish; otherwise
        the old behaviour (show everything once, at the end) is kept.
        """
        try:
            parameters = inspect.signature(self.provider.discuss).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "on_turn" not in parameters:
            return None
        sources = list(news_result.sources) if news_result else []
        if source_note.strip():
            sources.insert(0, TrendSource("用户提供的前沿线索", note=source_note.strip(), source_type="user"))
        return DiscussionSession(
            topic=topic.strip(),
            sources=sources,
            source=sources[0] if sources else None,
            selected_role_ids=[role.id for role in roles],
            mode=mode_for_roles(roles),
        )

    def _generation_turn(self, utterance: Utterance, done: int, total: int, token: int) -> None:
        """Receive one finished turn from the worker and put it on screen."""
        if token != self._start_token:
            return
        live = self._live_session
        if live is None:
            return
        live.append_utterance(utterance)
        first = len(live.utterances) == 1
        if first:
            self.playback.live = True
            self.playback.start(live)
            self.session_ready.emit(live)
            self.phase_changed.emit(live.phase)
        self.discussion_state_changed.emit(live.discussion_state)
        self.generation_progress.emit(done, total)
        self.store.save(live)
        # Never advance on the user's behalf: a turn arriving in the background is
        # preparation, not playback. The reader moves when they click 下一步.
        if first:
            self._emit_current()

    @staticmethod
    def _adopt_metadata(live: DiscussionSession, finished: DiscussionSession) -> None:
        """Copy the fields the provider only fills in once the whole batch is done."""
        live.opportunity = finished.opportunity
        live.usage_input_tokens = finished.usage_input_tokens
        live.usage_output_tokens = finished.usage_output_tokens
        live.usage_requests = finished.usage_requests
        if live.usage_requests > 0:
            live.network_used = True
        live.model_name = finished.model_name
        live.generation_status = finished.generation_status
        live.generation_stage = finished.generation_stage
        live.generation_streamed = finished.generation_streamed
        if finished.sources:
            live.sources = list(finished.sources)
            live.source = finished.source or live.source
        live.rebuild_state()

    def _generation_finished(self, session: DiscussionSession, token: int) -> None:
        if token != self._start_token:
            return
        live = self._live_session
        self._live_session = None
        if live is not None:
            self._adopt_metadata(live, session)
            self._generation_state(live, self._generation_news_result, provider_failed=False,
                                   already_started=True)
            return
        self._generation_state(session, self._generation_news_result, provider_failed=False)

    def _generation_failed(self, exc: BaseException, token: int) -> None:
        if token != self._start_token:
            return
        self._live_session = None
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

    def _generation_state(self, session: DiscussionSession, news_result: NewsFetchResult | None, *,
                          provider_failed: bool, already_started: bool = False) -> None:
        if news_result and news_result.sources:
            existing = {(item.title.casefold(), item.url.casefold()) for item in session.sources}
            session.sources.extend(item for item in news_result.sources if (item.title.casefold(), item.url.casefold()) not in existing)
            session.source = session.source or session.sources[0]
        session.request_mode = self.integration_status.requested_mode
        session.effective_provider = "mock" if provider_failed else self.integration_status.discussion_provider
        session.provider_mode = "offline" if provider_failed else self.integration_status.effective_mode
        session.news_provider = self.integration_status.news_provider
        # Network use means the discussion actually talked to something outside
        # this machine: matched RSS material, or model requests. The report's C1
        # showed three real-model sessions labelled 未使用网络 while the same
        # session recorded 13 requests.
        session.network_used = bool(news_result and news_result.matched) or session.usage_requests > 0
        session.news_attempted = bool(news_result and news_result.attempted)
        session.news_success = bool(news_result is None or news_result.success)
        session.news_matched = bool(news_result and news_result.matched)
        session.news_partial_failure = bool(news_result and news_result.partial_failure)
        session.status_message = (
            session.fallback_reason
            or (news_result.message if news_result else self.integration_status.describe())
        )
        # C2：只有真的抓过素材、并且抓失败到没有可用来源时，才算“回退原因”。
        # 没勾 RSS 的那一场不该背着上一次的失败信息。
        if news_result and news_result.attempted and not news_result.success and not news_result.sources:
            session.fallback_reason = news_result.message
        elif not (news_result and news_result.attempted):
            session.fallback_reason = ""
        self._discussion_batch = 0
        self.playback.live = True
        if already_started:
            # The batch streamed in and the reader is already somewhere inside it:
            # keep their position, only refresh the surrounding state.
            self.discussion_state_changed.emit(session.discussion_state)
            self.phase_changed.emit(session.phase)
        else:
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
        self._live_session = None
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
                if self._live_session is not None:
                    # The opening batch is still streaming in, so the next turn is
                    # already on its way. Queueing a continuation here would ask
                    # the model for a turn the batch is about to deliver anyway.
                    self.generation_state_changed.emit("running")
                    return
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
        # The orchestrator refreshes the state inside its own request, so tracking
        # it costs no extra call. The worker only sets the attribute; applying it
        # to the session happens here, on the GUI thread.
        refresh = getattr(self.provider, "last_state_refresh", None)
        state = self.session.discussion_state
        if refresh is not None:
            state.consensus = list(refresh.consensus)
            state.conflicts = list(refresh.conflicts)
            state.unresolved_questions = list(refresh.unresolved)
            self.provider.last_state_refresh = None
        # 模型经常整段留空，档案就读成「暂无记录」。空着的用桌上的原话补，
        # 模型自己读出来的内容一律不动。
        consensus, conflicts, questions = derive_state(self.session)
        state.consensus = state.consensus or consensus
        state.conflicts = state.conflicts or conflicts
        state.unresolved_questions = state.unresolved_questions or questions
        # 同一件事：模型写不全的档案小节，用桌上已有的观点补齐。
        MockDiscussionProvider._refresh_opportunity(self.session, fill_missing=True)
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
        # 提前结束时先掐掉后台还在生成的发言：否则档案记 8 条、回头打开变 13 条。
        self._cancel_batch(emit_state=False)
        # 已经生成好的发言一律保留。以前按播放游标截断，用户提前结束时
        # 刚轮到的那几条会被删掉，档案里却留着它们的立场，数据对不上。
        self.session.rebuild_state()
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
