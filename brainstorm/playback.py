"""Qt-free discussion playback state machine."""

from __future__ import annotations

from enum import Enum

from .models import DiscussionSession, Utterance


class PlaybackState(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    COMPLETED = "completed"


class DiscussionPlayback:
    def __init__(self, *, live: bool = False) -> None:
        self.session: DiscussionSession | None = None
        self.index = -1
        self.state = PlaybackState.IDLE
        self.live = live

    @property
    def current(self) -> Utterance | None:
        if self.session and 0 <= self.index < len(self.session.utterances):
            return self.session.utterances[self.index]
        return None

    def start(self, session: DiscussionSession) -> Utterance | None:
        self.session = session
        self.index = -1
        self.state = PlaybackState.PLAYING
        return self.advance()

    def restart(self) -> Utterance | None:
        """Replay the attached session from its first utterance."""
        if self.session is None:
            return None
        return self.start(self.session)

    def load(self, session: DiscussionSession, *, completed: bool = True) -> Utterance | None:
        """Load a saved session without mutating its utterance list.

        Historical sessions are presented as a completed record by default;
        callers may request the first turn when they want replay controls.
        """
        self.session = session
        self.index = len(session.utterances) - 1 if completed else -1
        self.state = PlaybackState.COMPLETED if completed else PlaybackState.PLAYING
        return self.current

    def pause(self) -> None:
        if self.state == PlaybackState.PLAYING:
            self.state = PlaybackState.PAUSED

    def resume(self) -> Utterance | None:
        if self.state == PlaybackState.PAUSED:
            self.state = PlaybackState.PLAYING
        return self.current

    def advance(self) -> Utterance | None:
        if not self.session:
            self.state = PlaybackState.IDLE
            return None
        if self.live and self.index >= len(self.session.utterances) - 1:
            self.state = PlaybackState.PLAYING
            return self.current
        self.index += 1
        if self.index >= len(self.session.utterances):
            self.state = PlaybackState.COMPLETED
            return None
        self.state = PlaybackState.PLAYING
        return self.current

    def next_step(self) -> Utterance | None:
        """Advance exactly one utterance for user-controlled playback."""
        if self.state in (PlaybackState.IDLE, PlaybackState.COMPLETED):
            return None
        return self.advance()

    def finish(self) -> Utterance | None:
        """Explicitly finish a live discussion and keep the last turn visible."""
        if self.session is None:
            self.state = PlaybackState.IDLE
            return None
        if self.index < 0 and self.session.utterances:
            self.index = 0
        elif self.session.utterances:
            self.index = min(self.index, len(self.session.utterances) - 1)
        self.state = PlaybackState.COMPLETED
        return self.current

    def skip(self) -> Utterance | None:
        if self.state in (PlaybackState.IDLE, PlaybackState.COMPLETED):
            return None
        return self.advance()
