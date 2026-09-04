#!/usr/bin/env python3
"""
DeepScribe GUI — 启动入口。
用法: python -m gui.main  或  python gui/main.py
"""
import sys
import time
import traceback
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QtMsgType, qInstallMessageHandler

from gui.styles import (
    CUSTOM_STYLESHEET,
    spin_arrow_stylesheet,
    check_indicator_stylesheet,
)
from gui.main_window import MainWindow


def _setup_crash_log() -> Path | None:
    """GUI 侧崩溃日志：把未捕获异常与 Qt 消息落到 logs/gui_{时间戳}.log。

    GUI 由 pythonw.exe 启动无控制台，闪退（含远控断连导致进程被杀）时
    没有任何输出可查。这里兜底把启动信息 / 未捕获异常 / Qt 告警写盘。
    返回日志路径；目录不可写时返回 None（不影响 GUI 启动）。
    """
    try:
        log_dir = _project_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"gui_{time.strftime('%Y%m%d_%H%M%S')}.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - INFO - "
                    f"GUI 启动 (Python {sys.version.split()[0]}, "
                    f"exe={sys.executable})\n")
    except OSError:
        return None

    def _append(text: str) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {text}\n")
        except OSError:
            pass

    def _excepthook(tp, val, tb):
        _append("CRITICAL - 未捕获异常:\n" +
                "".join(traceback.format_exception(tp, val, tb)).rstrip())
        sys.__excepthook__(tp, val, tb)

    sys.excepthook = _excepthook

    _QT_LEVELS = {
        QtMsgType.QtDebugMsg: "Debug",
        QtMsgType.QtInfoMsg: "Info",
        QtMsgType.QtWarningMsg: "Warning",
        QtMsgType.QtCriticalMsg: "Critical",
        QtMsgType.QtFatalMsg: "Fatal",
    }

    def _qt_message_handler(mode, context, message):
        # 只记录 warning 及以上，避免刷屏；Qt 告警常是闪退前兆
        if mode >= QtMsgType.QtWarningMsg:
            level = _QT_LEVELS.get(mode, f"Qt{mode}")
            _append(f"WARNING - [Qt {level}] {message}")

    qInstallMessageHandler(_qt_message_handler)
    return log_path


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

    # GUI 崩溃日志（未捕获异常 + Qt 告警 → logs/gui_*.log）
    _setup_crash_log()

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
