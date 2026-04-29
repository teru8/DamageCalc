import sys
import os

# Ensure the app directory is on sys.path for PyInstaller
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from src.ui.main_window import MainWindow
from src.ui.styles import DARK_STYLE


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PokéDamageCalc")
    app.setApplicationVersion("1.0.0")

    font = QFont("Yu Gothic UI", 10)
    app.setFont(font)
    app.setStyleSheet(DARK_STYLE)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
