from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CameraRuntimeState:
    """Mutable runtime state for MainWindow camera lifecycle."""

    active: bool = False

    def mark_active(self) -> None:
        self.active = True

    def mark_inactive(self) -> None:
        self.active = False
