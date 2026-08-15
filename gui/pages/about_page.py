"""
关于页面：项目信息、开源协议、依赖
"""
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea,
)
from PyQt5.QtCore import QUrl

from gui.styles import COLORS, install_hover_highlights


def _read_version() -> str:
    version_path = Path(__file__).resolve().parent.parent.parent / "version"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "v0.0.0"


class AboutPage(QWidget):
    """关于页面，内容可滚动。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._setup_ui()
        install_hover_highlights(self)

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(14)

        # 大标题
        title = QLabel("DeepScribe")
        title.setStyleSheet(f"""
            font-size: 20px; font-weight: 800; color: {COLORS['primary']};
            background: transparent;
        """)
        layout.addWidget(title)

        subtitle = QLabel("PDF 学术论文英文 → 中文 Markdown 翻译流水线")
        subtitle.setStyleSheet("""
            font-size: 14px; padding-bottom: 4px; background: transparent;
        """)
        layout.addWidget(subtitle)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: transparent;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ---- 技术栈 ----
        layout.addWidget(self._section("技术栈"))
        layout.addWidget(self._body(
            "• MinerU — PDF 解析与公式提取\n"
            "• DeepSeek API — 批量翻译（[BLK:N] 标记机制）\n"
            "• PyQt5 — 图形界面\n"
            "• SQLite — 断点续传缓存\n"
            "• PyMuPDF — PDF 书签提取与拆分"
        ))

        # ---- 核心特性 ----
        layout.addWidget(self._section("核心特性"))
        layout.addWidget(self._body(
            "• Token 感知自适应分块，避免 API 截断\n"
            "• [BLK:N] 标记批量翻译 + 逐段回退兜底\n"
            "• G2 完整性校验：译文行内公式/代码损坏自动回填\n"
            "• 并行模式：按 PDF 书签拆章，多线程并发翻译\n"
            "• 大章二级书签自动拆分\n"
            "• SQLite 断点续传，中断不丢进度\n"
            "• Windows DPAPI 加密 API Key"
        ))

        # ---- 开源协议 ----
        layout.addWidget(self._section("开源协议"))
        layout.addWidget(self._body("MIT License — 自由使用、修改、分发"))

        # ---- GitHub ----
        layout.addWidget(self._section("项目地址"))
        gh_btn = QPushButton("🔗  github.com/distanrive/DeepScribe")
        gh_btn.setObjectName("linkBtn")
        gh_btn.setCursor(Qt.PointingHandCursor)
        gh_btn.setMinimumHeight(36)
        gh_btn.setMaximumWidth(340)
        gh_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/distanrive/DeepScribe"))
        )
        layout.addWidget(gh_btn)

        # ---- 依赖 ----
        layout.addWidget(self._section("Python 依赖"))
        layout.addWidget(self._body(
            "openai  ·  python-dotenv  ·  mineru  ·  PyMuPDF  ·  PyQt5"
        ))

        layout.addStretch()

        # 版本
        ver = QLabel(f"DeepScribe {_read_version()}  |  GUI Edition")
        ver.setStyleSheet("font-size: 12px; background: transparent;")
        ver.setAlignment(Qt.AlignRight)
        layout.addWidget(ver)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("""
            font-size: 14px; font-weight: 700;
            padding-top: 6px; background: transparent;
        """)
        return lbl

    @staticmethod
    def _body(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("""
            font-size: 13px;
            padding-left: 4px; background: transparent;
        """)
        return lbl
