"""
PDF to Audiobook Converter - Main Entry Point
============================================
Launches the PyQt6 GUI application.
"""

import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.interface import MainWindow


def main():
    # High-DPI support
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("PDF Audiobook Converter")
    app.setOrganizationName("OfflineAudio")

    # Apply global stylesheet
    app.setStyleSheet(GLOBAL_STYLE)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


GLOBAL_STYLE = """
QMainWindow, QDialog {
    background-color: #0d0f14;
}
QWidget {
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    color: #e8eaf0;
}
QScrollBar:vertical {
    background: #1a1d26;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #3a3f56;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #f0722e;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QToolTip {
    background-color: #1e2130;
    color: #e8eaf0;
    border: 1px solid #f0722e;
    padding: 4px 8px;
    border-radius: 4px;
}
"""


if __name__ == "__main__":
    main()
