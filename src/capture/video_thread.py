"""QThread that captures camera frames and emits preview pixmaps."""
import time
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtGui import QImage, QPixmap


def _frame_to_qpixmap(frame: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
    return QPixmap.fromImage(img)


class VideoThread(QThread):
    frame_ready = pyqtSignal(QPixmap)

    def __init__(self, device_index: int = 0):
        super().__init__()
        self._device_index = device_index
        self._running = False
        self._mutex = QMutex()
        self._last_frame: "np.ndarray | None" = None

    def set_device(self, index: int) -> None:
        self._device_index = index

    def stop(self) -> None:
        self._running = False
        self.wait()

    def run(self) -> None:
        self._running = True
        cap = cv2.VideoCapture(self._device_index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        if not cap.isOpened():
            self._running = False
            return

        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.033)
                continue

            # Ensure 1280x720
            if frame.shape[:2] != (720, 1280):
                frame = cv2.resize(frame, (1280, 720))

            locker = QMutexLocker(self._mutex)
            self._last_frame = frame.copy()
            del locker

            # Emit preview frame (scaled down for UI)
            preview = cv2.resize(frame, (640, 360))
            self.frame_ready.emit(_frame_to_qpixmap(preview))
            time.sleep(0.01)

        cap.release()

    def get_last_frame(self) -> "np.ndarray | None":
        locker = QMutexLocker(self._mutex)
        if self._last_frame is None:
            return None
        frame = self._last_frame.copy()
        del locker
        return frame

    @staticmethod
    def list_cameras(max_index: int = 10) -> list[tuple[int, str]]:
        """Returns list of (index, label) for available cameras."""
        import os
        cameras = []
        old_val = os.environ.get("OPENCV_LOG_LEVEL")
        os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
        for i in range(max_index):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                cameras.append((i, f"Camera {i}"))
                cap.release()
        if old_val is None:
            os.environ.pop("OPENCV_LOG_LEVEL", None)
        else:
            os.environ["OPENCV_LOG_LEVEL"] = old_val
        return cameras
