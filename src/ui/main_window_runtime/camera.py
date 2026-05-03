from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import cv2
from PyQt5.QtWidgets import QMessageBox

from src.capture.video_thread import VideoThread


@dataclass
class CameraManager:
    """Coordinate MainWindow camera lifecycle operations."""

    def refresh_cameras(self, window: Any) -> None:
        window._cam_combo.clear()
        cameras = VideoThread.list_cameras()
        for idx, name in cameras:
            window._cam_combo.addItem(name, idx)
        if not cameras:
            window._cam_combo.addItem("カメラなし", -1)

    def toggle_camera(self, window: Any, stop_video_thread: Callable[[Any], None]) -> None:
        window._connect_btn.setEnabled(False)
        try:
            if window._camera_state.active and window._video_thread and window._video_thread.isRunning():
                window._stop_live_battle_tracking(show_message=False, write_log=False)
                window._stop_opponent_party_auto_detect(show_message=False, write_log=False)
                stop_video_thread(window)
                window._connect_btn.setText("接続")
                window._preview_lbl.setText("カメラ未接続")
                window._log("カメラ切断")
                return

            if window._video_thread is not None:
                stop_video_thread(window)

            idx = window._cam_combo.currentData()
            if idx is None or idx < 0:
                return

            window._video_thread = VideoThread(idx)
            window._video_thread.frame_ready.connect(window._on_frame)
            window._video_thread.start()
            window._camera_state.mark_active()
            window._connect_btn.setText("切断")
            window._log("カメラ接続: インデックス {}".format(idx))
            window._save_settings(last_camera_index=idx)
        finally:
            window._connect_btn.setEnabled(True)

    def save_screenshot(self, window: Any) -> None:
        if not window._video_thread or not window._video_thread.isRunning():
            QMessageBox.information(window, "情報", "カメラを接続してください")
            return

        frame = window._video_thread.get_last_frame()
        if frame is None or frame.size == 0:
            QMessageBox.information(window, "情報", "保存できるフレームがありません")
            return

        captures_dir = Path.cwd() / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = captures_dir / "{}.png".format(ts)

        if not cv2.imwrite(str(out_path), frame):
            QMessageBox.warning(window, "エラー", "スクリーンショット保存に失敗しました")
            return

        window._status_bar.showMessage("保存: {}".format(out_path.name), 5000)
        window._log("スクリーンショット保存: {}".format(out_path))
