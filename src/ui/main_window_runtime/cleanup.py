from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeCleanupManager:
    """Manage MainWindow runtime cleanup and teardown flow."""

    def disconnect_damage_panel_signals(self, window: Any) -> None:
        try:
            window._damage_panel.attacker_changed.disconnect()
            window._damage_panel.defender_changed.disconnect()
            window._damage_panel.registry_maybe_changed.disconnect()
            window._damage_panel.bridge_payload_logged.disconnect()
        except RuntimeError:
            pass

    def stop_and_disconnect_timers(self, window: Any) -> None:
        window._live_battle_timer.stop()
        window._live_battle_timer.timeout.disconnect()
        window._opp_auto_detect_timer.stop()
        window._opp_auto_detect_timer.timeout.disconnect()

    def stop_video_thread_if_present(self, window: Any, wait_timeout_ms: int = 3000) -> None:
        if window._video_thread is None:
            window._camera_state.mark_inactive()
            return
        window._video_thread.stop()
        window._video_thread.wait(wait_timeout_ms)
        window._video_thread = None
        window._camera_state.mark_inactive()

    def cleanup_runtime_resources(self, window: Any) -> None:
        self.stop_and_disconnect_timers(window)
        self.disconnect_damage_panel_signals(window)
        window._stop_live_battle_tracking(show_message=False, write_log=False)
        window._stop_opponent_party_auto_detect(show_message=False, write_log=False)
        self.stop_video_thread_if_present(window)
