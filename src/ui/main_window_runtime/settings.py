from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SettingsStore:
    """Persistent settings storage for MainWindow."""

    path: Path

    @classmethod
    def default(cls) -> "SettingsStore":
        return cls(path=Path.home() / ".pokemon_damage_calc" / "settings.json")

    def load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    return loaded
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        return {}

    def save(self, **kwargs: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = self.load()
        current.update(kwargs)
        self.path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
