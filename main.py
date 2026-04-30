import sys
import os
import threading
import traceback
import ctypes
from datetime import datetime
from pathlib import Path

# Ensure the app directory is on sys.path for PyInstaller
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont, QIcon
from src.ui.main_window import MainWindow
from src.ui.styles import DARK_STYLE


def _resolve_app_icon_path() -> Path | None:
    """Resolve app icon path for both dev and PyInstaller builds."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "assets" / "app_icon.png")
        candidates.append(exe_dir / "_internal" / "assets" / "app_icon.png")
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if str(meipass):
            candidates.append(meipass / "assets" / "app_icon.png")
    else:
        root = Path(__file__).resolve().parent
        candidates.append(root / "assets" / "app_icon.png")
    for path in candidates:
        if path.exists():
            return path
    return None


def _error_log_path() -> Path:
    base = Path.home() / ".damage_calc"
    base.mkdir(parents=True, exist_ok=True)
    return base / "error.log"


def _append_error_log(title: str, exc_type, exc_value, exc_tb) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trace = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    body = f"[{ts}] {title}\n{trace}\n"
    try:
        with _error_log_path().open("a", encoding="utf-8") as f:
            f.write(body)
    except OSError:
        pass


def _install_global_exception_hooks() -> None:
    old_sys_hook = sys.excepthook

    def _sys_hook(exc_type, exc_value, exc_tb):
        _append_error_log("Unhandled exception (main thread)", exc_type, exc_value, exc_tb)
        old_sys_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _sys_hook

    old_thread_hook = getattr(threading, "excepthook", None)
    if old_thread_hook is not None:
        def _thread_hook(args):
            _append_error_log(
                "Unhandled exception (thread: {})".format(getattr(args.thread, "name", "?")),
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
            )
            old_thread_hook(args)

        threading.excepthook = _thread_hook


_SINGLE_INSTANCE_MUTEX: ctypes.c_void_p | None = None


def _acquire_single_instance() -> bool:
    """Return True if this is the first instance. Windows only."""
    if os.name != "nt":
        return True
    global _SINGLE_INSTANCE_MUTEX
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "DamageCalcSingleInstanceMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # Bring existing window to foreground
        HWND_BROADCAST = 0xFFFF
        WM_USER_FOCUS = 0x8001
        ctypes.windll.user32.PostMessageW(HWND_BROADCAST, WM_USER_FOCUS, 0, 0)
        return False
    _SINGLE_INSTANCE_MUTEX = mutex
    return True


def main() -> None:
    _install_global_exception_hooks()
    if not _acquire_single_instance():
        sys.exit(0)
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DamageCalc.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("DamageCalc")
    app.setApplicationVersion("0.1.1-alpha")
    icon_path = _resolve_app_icon_path()
    icon = QIcon(str(icon_path)) if icon_path else QIcon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    font = QFont("Yu Gothic UI", 10)
    app.setFont(font)
    app.setStyleSheet(DARK_STYLE)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
