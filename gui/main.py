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

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from gui.styles import (
    CUSTOM_STYLESHEET,
    spin_arrow_stylesheet,
    check_indicator_stylesheet,
)
from gui.main_window import MainWindow


def main():
    # PyQt5(Qt5) 默认不启用高分屏缩放，须在 QApplication 创建前设置；
    # 否则迁移自 PySide6(Qt6) 后界面在高分屏上会模糊。
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DeepScribe")
    app.setOrganizationName("DeepScribe")

    # 全局字体：黑体（SimHei），未显式设 font-size 的控件统一走此基准
    app.setFont(QFont("SimHei", 10))

    # Fusion 风格 + 自写 CUSTOM_STYLESHEET（不再依赖 qt-material）。
    # spin_arrow / check_indicator 为运行期生成的箭头/勾/圆点 PNG 图标 QSS
    app.setStyle("Fusion")
    app.setStyleSheet(
        CUSTOM_STYLESHEET
        + spin_arrow_stylesheet()
        + check_indicator_stylesheet()
    )

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
