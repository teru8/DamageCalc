DARK_STYLE = """
QMainWindow, QDialog, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Yu Gothic UI", "Meiryo UI", "MS Gothic", sans-serif;
    font-size: 14px;
}

QLabel {
    color: #cdd6f4;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #89b4fa;
}

QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 5px 12px;
    color: #cdd6f4;
    min-height: 26px;
}

QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}

QPushButton:pressed {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QPushButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}

QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 36px 4px 8px;
    color: #cdd6f4;
    min-height: 26px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    background-color: #45475a;
    border: none;
    border-left: 1px solid #585b70;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
    width: 30px;
}

QComboBox::drop-down:hover {
    background-color: #585b70;
}

QComboBox::down-arrow {
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'><path d='M1 1 L6 6 L11 1' stroke='%23cdd6f4' stroke-width='2' fill='none' stroke-linecap='round'/></svg>");
    width: 12px;
    height: 8px;
}

QComboBox QAbstractItemView {
    background-color: #313244;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
    color: #cdd6f4;
}

QLineEdit, QSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd6f4;
    min-height: 24px;
}

QLineEdit:focus, QSpinBox:focus {
    border-color: #89b4fa;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #313244;
    border: 1px solid #45475a;
    padding: 6px 16px;
    color: #a6adc8;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #45475a;
    color: #cdd6f4;
    border-bottom-color: #45475a;
}

QTabBar::tab:hover {
    background-color: #45475a;
    color: #cdd6f4;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background: #313244;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #585b70;
    border-radius: 5px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #45475a;
}

QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
    height: 16px;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 3px;
}

QListWidget {
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
}

QListWidget::item:selected {
    background-color: #45475a;
}

QListWidget::item:hover {
    background-color: #313244;
}

QTextEdit {
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #a6adc8;
    font-family: "Consolas", "MS Gothic", monospace;
    font-size: 12px;
    padding: 4px;
}

QTableWidget {
    background-color: #181825;
    border: 1px solid #45475a;
    gridline-color: #313244;
    color: #cdd6f4;
}

QTableWidget::item:selected {
    background-color: #45475a;
}

QHeaderView::section {
    background-color: #313244;
    border: none;
    border-right: 1px solid #45475a;
    padding: 4px 8px;
    color: #89b4fa;
    font-weight: bold;
}

QCheckBox {
    color: #cdd6f4;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background-color: #313244;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
}

QSplitter::handle {
    background-color: #45475a;
    width: 3px;
}
"""

TYPE_BADGE_STYLE = """
    background-color: {color};
    color: white;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
    font-weight: bold;
"""

HP_BAR_STYLE = {
    "high":   "background-color: #a6e3a1; border-radius: 3px;",
    "medium": "background-color: #f9e2af; border-radius: 3px;",
    "low":    "background-color: #f38ba8; border-radius: 3px;",
    "empty":  "background-color: #45475a; border-radius: 3px;",
}
