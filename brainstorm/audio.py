"""Silent-by-default audio controls; assets can be added without changing views."""

from PySide6.QtCore import QObject, Signal


class AudioController(QObject):
    changed = Signal(bool, bool)

    def __init__(self) -> None:
        super().__init__()
        self.ambient_enabled = False
        self.effects_enabled = False

    def set_ambient(self, enabled: bool) -> None:
        self.ambient_enabled = enabled
        self.changed.emit(self.ambient_enabled, self.effects_enabled)

    def set_effects(self, enabled: bool) -> None:
        self.effects_enabled = enabled
        self.changed.emit(self.ambient_enabled, self.effects_enabled)
