#!/usr/bin/env python3
"""
DeepScribe GUI — 启动入口。
用法: python -m gui.main  或  python gui/main.py
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from qt_material import apply_stylesheet

from gui.styles import CUSTOM_STYLESHEET
from gui.main_window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DeepScribe")
    app.setOrganizationName("DeepScribe")

    # qt-material 深色主题 + 自定义主色
    extra = {
        "primary_color": "#6366f1",
        "primary_light_color": "#818cf8",
        "secondary_color": "#4b5563",
        "secondary_light_color": "#6b7280",
    }
    apply_stylesheet(app, theme="dark_blue.xml", extra=extra)

    # 叠加：修背景色 + 自定义控件（侧边栏/拖放区等）
    app.setStyleSheet(app.styleSheet() + CUSTOM_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
