from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt5.QtWidgets import QMessageBox

from src.capture.ocr_engine import OcrInitThread


@dataclass
class OcrInitManager:
    """Manage OCR initialization lifecycle for MainWindow."""

    def start(self, window: Any) -> None:
        existing = window._ocr_thread
        if existing is not None and existing.isRunning():
            return
        window._ocr_thread = OcrInitThread(use_gpu=False)
        window._ocr_thread.finished.connect(window._on_ocr_ready)
        window._ocr_thread.start()

    def on_ready(self, window: Any, ok: bool, err: str) -> None:
        if ok:
            window._ocr_retry_manager.reset()
            if window._ocr_retry_timer.isActive():
                window._ocr_retry_timer.stop()
            window._status_bar.showMessage("OCR 初期化完了")
            window._log("OCR 初期化完了")
            return
        self.handle_failure(window, err)

    def handle_failure(self, window: Any, err: str) -> None:
        message = "OCR 初期化失敗: {}".format(err)
        window._log("[ERROR] {}".format(message))
        QMessageBox.warning(window, "OCR 初期化エラー", message)
        self.schedule_retry_if_available(window)

    def schedule_retry_if_available(self, window: Any) -> None:
        retry_count = window._ocr_retry_manager.next_retry()
        if retry_count is None:
            return
        window._log(
            "OCR 初期化を再試行します ({}/{})".format(
                retry_count,
                window._ocr_retry_manager.max_retries,
            )
        )
        window._ocr_retry_timer.start(window._ocr_retry_manager.retry_delay_ms)
