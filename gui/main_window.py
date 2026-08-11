"""
DeepScribe GUI — 主窗口。
侧边栏导航 + 页面区域。
主题由 qt-material (dark_blue.xml) + CUSTOM_STYLESHEET 提供。
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QSizePolicy, QFrame,
)

from gui.styles import COLORS
from gui.config_manager import ConfigManager
from gui.pages.work_page import WorkPage
from gui.pages.config_page import ConfigPage
from gui.pages.about_page import AboutPage

NAV_ITEMS = [
    ("work", "📄  工作", WorkPage),
    ("config", "⚙️  配置", ConfigPage),
    ("about", "ℹ️  关于", AboutPage),
]


def _read_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "version"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "v0.0.0"


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepScribe — PDF 学术翻译")
        self.resize(1200, 800)
        self.setMinimumSize(960, 640)

        self.config = ConfigManager()
        self._version = _read_version()

        self._pages: dict[str, QWidget | None] = {key: None for key, _, _ in NAV_ITEMS}
        self._nav_buttons: dict[str, QPushButton] = {}
        self.stack = QStackedWidget()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QWidget()
        right.setObjectName("contentArea")
        right.setStyleSheet(f"QWidget#contentArea {{ background-color: {COLORS['bg']}; }}")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.stack)
        root.addWidget(right, 1)

        self._show_page("work")

    # ============================================================
    # 侧边栏
    # ============================================================
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(4)

        # 标题（Expanding 使标签占满侧边栏宽度，AlignCenter 才真正把文字居中）
        title = QLabel("DeepScribe")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["primary"]};
                font-size: 22px;
                font-weight: 800;
                padding: 8px 12px 16px 12px;
                background: transparent;
            }}
        """)
        layout.addWidget(title)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.08); background: transparent;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)
        layout.addSpacing(8)

        # 导航
        for key, text, _ in NAV_ITEMS:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(42)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked, k=key: self._show_page(k))
            self._nav_buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # 版本
        ver = QLabel(self._version)
        ver.setStyleSheet("""
            QLabel {
                color: rgba(255,255,255,0.25);
                font-size: 11px;
                padding: 8px 12px;
                background: transparent;
            }
        """)
        layout.addWidget(ver)

        return sidebar

    # ============================================================
    # 页面切换
    # ============================================================
    def _show_page(self, key: str):
        for nk, btn in self._nav_buttons.items():
            btn.setChecked(nk == key)

        if self._pages[key] is None:
            for nk, _, cls in NAV_ITEMS:
                if nk == key:
                    self._pages[key] = cls(self.config, self)
                    self.stack.addWidget(self._pages[key])
                    break

        self.stack.setCurrentWidget(self._pages[key])

    # ============================================================
    # 窗口关闭
    # ============================================================
    def closeEvent(self, event):
        """关闭窗口时取消所有运行中的任务，避免留下孤儿 MinerU 子进程。"""
        work_page = self._pages.get("work")
        if work_page is not None:
            work_page.shutdown()
        event.accept()
