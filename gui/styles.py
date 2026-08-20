"""
DeepScribe GUI — 自定义样式（深色）。
自写完整 QSS：全局背景色 + 自定义控件 + 多种强调色按钮。
"""
from pathlib import Path

from PyQt5.QtCore import Qt, QObject, QEvent
from PyQt5.QtWidgets import QStyledItemDelegate, QStyle

# ---- 色值 ----
COLORS = {
    "sidebar_bg": "#2b2d30",
    "sidebar_hover": "#3a3d40",
    "sidebar_active": "rgba(255,255,255,0.08)",
    "drop_border": "#6366f1",
    "drop_bg": "rgba(99, 102, 241, 0.05)",
    "success": "#4caf50",
    "warning": "#ff9800",
    "error": "#f44336",
    "info": "#6366f1",
    "text": "#ffffff",
    "text_secondary": "#b0b0b0",
    "text_dim": "#808080",
    "primary": "#6366f1",
    "primary_hover": "#818cf8",
    "border": "#4a4d50",
    "bg": "#1e1e1e",
    "surface": "#2d2f31",
}

CUSTOM_STYLESHEET = f"""
/* ===== [1] 全局背景 & 文本色 ===== */

QLabel {{
    color: #ffffff;
}}

QTreeView, QTableView, QTreeWidget, QTableWidget {{
    color: #ffffff;
}}

QHeaderView::section {{
    color: #ffffff;
}}

QTextEdit, QPlainTextEdit {{
    color: #ffffff;
}}

QMainWindow > QWidget {{
    background-color: {COLORS["bg"]};
}}

QStackedWidget {{
    background-color: {COLORS["bg"]};
}}

QScrollArea > QWidget > QWidget {{
    background-color: {COLORS["bg"]};
}}

QScrollArea {{
    background-color: {COLORS["bg"]};
}}

/* 选中项：靛蓝底白字 */
QComboBox::item:selected,
QComboBox QAbstractItemView::item:selected,
QListView::item:selected,
QTreeView::item:selected,
QTableView::item:selected {{
    background-color: {COLORS["primary"]};
    color: #ffffff;
}}

/* 悬停项：深灰底，文字不变 */
QComboBox::item:hover,
QComboBox::item:!selected:hover,
QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:!selected:hover,
QListView::item:hover,
QListView::item:!selected:hover,
QTreeView::item:hover,
QTreeView::item:!selected:hover {{
    background-color: #3a3d40;
    color: {COLORS["text"]};
}}

/* 下拉框文字：左对齐 + 合理左右内边距（避免文字被截断/左 padding 过大）。
   注意：不要用 QComboBox::item 加 padding——该选择器同时匹配弹出列表的每一项，
   QSS 会把行高计算成约整屏高（视觉上 popup 纵向占满屏幕）。 */
QComboBox {{
    padding: 4px 8px;
    text-align: left;
}}
QComboBox::drop-down {{
    subcontrol-position: right center;
    width: 20px;
    padding: 0;
    margin: 0;
}}
QComboBox QAbstractItemView {{
    padding: 0;
    margin: 0;
    outline: none;
    background-color: #2d2f31;
    color: #ffffff;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    margin: 0;
    text-align: left;
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {COLORS["primary"]};
}}

/* ===== [2] 侧边栏 ===== */
QWidget#sidebar {{
    background-color: {COLORS["sidebar_bg"]};
}}

QPushButton#navBtn {{
    color: #9e9e9e;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    text-align: left;
    font-size: 14px;
    background: transparent;
}}
QPushButton#navBtn:hover {{
    background: {COLORS["sidebar_hover"]};
    color: #cccccc;
}}
QPushButton#navBtn:checked {{
    background: {COLORS["sidebar_active"]};
    color: #cccccc;
    font-weight: 600;
}}

/* ===== [3] 多种强调色按钮（#id 高优先级）===== */

QPushButton#saveBtn {{
    background-color: transparent;
    color: #81c784;
    border: 1px solid #81c784;
    border-radius: 6px;
    padding: 10px 24px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#saveBtn:hover {{
    background-color: #253528;
}}

QPushButton#restoreBtn {{
    background-color: transparent;
    color: #ef9a9a;
    border: 1px solid #ef9a9a;
    border-radius: 6px;
    padding: 10px 24px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#restoreBtn:hover {{
    background-color: #332222;
}}

/* ---- 所有自定义按钮：透明底 + 悬停高亮 ---- */

QPushButton#actionBtn {{
    background-color: transparent;
    color: {COLORS["text_secondary"]};
    border: none;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#actionBtn:hover {{
    background-color: #4a4d52;
    color: {COLORS["text"]};
}}

QPushButton#linkBtn {{
    background-color: transparent;
    color: {COLORS["text_secondary"]};
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton#linkBtn:hover {{
    background-color: #4a4d52;
    color: {COLORS["text"]};
}}

QPushButton#batchStart {{
    background-color: transparent;
    color: #81c784;
    border: 1px solid #81c784;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 600;
}}
QPushButton#batchStart:hover {{
    background-color: #2d4a30;
}}

QPushButton#batchStop {{
    background-color: transparent;
    color: #ffb74d;
    border: 1px solid #ffb74d;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 600;
}}
QPushButton#batchStop:hover {{
    background-color: #4a3d28;
}}

QPushButton#batchClear {{
    background-color: transparent;
    color: #ef9a9a;
    border: 1px solid #ef9a9a;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 600;
}}
QPushButton#batchClear:hover {{
    background-color: #4a2828;
}}

/* ===== [4] 拖放区 ===== */
QWidget#dropZone {{
    border: 2px dashed #6b6d70;
    border-radius: 12px;
    background-color: rgba(255,255,255,0.02);
}}

/* ===== [5] GroupBox 标题（放框内，无衬底）===== */
QGroupBox {{
    border: 2px solid #448aff;
    border-radius: 8px;
    padding-top: 24px;
    padding-bottom: 14px;
    padding-left: 16px;
    padding-right: 16px;
    background-color: transparent;
}}
QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 14px;
    top: 8px;
    padding: 0 4px;
    color: #ffffff;
    background-color: transparent;
    font-size: 14px;
}}

/* ===== [6] 基础控件（qt-material 移除后补齐，保证深色页面可读性）===== */

/* 通用按钮（弹窗/文件对话框等无 #id 的按钮） */
QPushButton {{
    background-color: #2d2f31;
    color: #ffffff;
    border: 1px solid #4a4d50;
    border-radius: 4px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: #3a3d40;
}}
QPushButton:pressed {{
    background-color: {COLORS["primary"]};
}}

/* 输入类控件：深色底白字（避免默认白底与深色页面割裂） */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: #2d2f31;
    color: #ffffff;
    border: 1px solid #4a4d50;
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {COLORS["primary"]};
    selection-color: #ffffff;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {COLORS["primary"]};
}}

QComboBox {{
    background-color: #2d2f31;
    color: #ffffff;
    border: 1px solid #4a4d50;
    border-radius: 4px;
}}

/* 日志/文本区：必须给背景色，否则白底白字不可见 */
QTextEdit, QPlainTextEdit {{
    background-color: #2d2f31;
    border: 1px solid #4a4d50;
    border-radius: 4px;
}}

/* 勾选/单选：白字，避免深色页面上的黑字不可读 */
QCheckBox, QRadioButton {{
    color: #ffffff;
    background: transparent;
}}

/* 表头：白字配深色底（原来由 qt-material 提供） */
QHeaderView::section {{
    background-color: #2d2f31;
    border: none;
    border-bottom: 1px solid #4a4d50;
    border-right: 1px solid #3a3d40;
    padding: 6px 8px;
}}

/* 弹窗 / 菜单 / 提示 */
QMessageBox {{
    background-color: #2d2f31;
}}
QMenu {{
    background-color: #2d2f31;
    color: #ffffff;
    border: 1px solid #4a4d50;
}}
QMenu::item {{
    padding: 6px 24px;
    background: transparent;
}}
QMenu::item:selected {{
    background-color: {COLORS["primary"]};
    color: #ffffff;
}}
QToolTip {{
    background-color: #2d2f31;
    color: #ffffff;
    border: 1px solid #4a4d50;
    font-size: 12px;
}}

/* 滚动条 */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #4a4d50;
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS["primary"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #4a4d50;
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {COLORS["primary"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ===== [7] 树控件 / 文件列表：深色底（避免白底白字）===== */
QTreeWidget, QTreeView, QTableView, QTableWidget {{
    background-color: {COLORS["bg"]};
    alternate-background-color: {COLORS["bg"]};
    color: #ffffff;
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
}}
QTreeWidget::item, QTreeView::item {{
    padding: 0px 4px;
    color: #ffffff;
}}
QTreeWidget::item:hover, QTreeView::item:hover {{
    background-color: #3a3d40;
}}

/* ===== [8] 数字控件增减按钮（被 QSS 隐藏，显式绘制）===== */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border: none;
    border-top-right-radius: 3px;
    background-color: #3a3d40;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border: none;
    border-bottom-right-radius: 3px;
    background-color: #3a3d40;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {COLORS["primary"]};
}}

/* ===== [9] 基准字号统一（正文 13px；标题/提示由各自规则覆盖）===== */
QLabel, QCheckBox, QRadioButton, QGroupBox, QComboBox, QLineEdit,
QSpinBox, QDoubleSpinBox, QPushButton, QTreeWidget, QTreeView,
QTextEdit, QPlainTextEdit, QMenu, QMessageBox {{
    font-size: 13px;
}}
"""


# ============================================================
# 数字控件增减箭头图标（QSS 无法原生绘制，需 image）
# ============================================================
def spin_arrow_stylesheet() -> str:
    """为 QSpinBox/QDoubleSpinBox 生成 ▲▼ 箭头 PNG，返回对应 QSS。

    QSS 一旦命中 QSpinBox 就会接管绘制、隐藏原生增减箭头；要显示箭头
    必须给 ::up-arrow / ::down-arrow 提供 image。这里用 QPainter 画两个
    三角保存到临时目录（已存在则复用），再拼出 QSS 供 main.py 追加。
    """
    import tempfile
    from PyQt5.QtGui import QPixmap, QPainter, QPolygon, QColor
    from PyQt5.QtCore import QPoint

    icons_dir = Path(tempfile.gettempdir()) / "DeepScribe" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    up_path = icons_dir / "spin_up.png"
    down_path = icons_dir / "spin_down.png"

    def _draw(path: Path, up: bool):
        pm = QPixmap(12, 12)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.NoPen)
        pts = QPolygon(
            [QPoint(6, 2), QPoint(11, 9), QPoint(1, 9)]
            if up else
            [QPoint(6, 10), QPoint(11, 3), QPoint(1, 3)]
        )
        p.drawPolygon(pts)
        p.end()
        pm.save(str(path), "PNG")

    if not up_path.exists():
        _draw(up_path, True)
    if not down_path.exists():
        _draw(down_path, False)

    def _url(p: Path) -> str:
        return str(p).replace("\\", "/")

    return f"""
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_url(up_path)}");
    width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_url(down_path)}");
    width: 9px; height: 9px;
}}
"""


# ============================================================
# 勾选框/单选按钮指示器图标（QSS 接管绘制后不自带勾/圆点，需 image）
# ============================================================
def check_indicator_stylesheet() -> str:
    """为 QCheckBox/QRadioButton 生成可见的指示器框 + 勾/圆点 PNG，返回对应 QSS。

    给 QCheckBox 应用 QSS 后，原生指示器框在深色底上几乎不可见（只有勾）。
    这里显式定义 ::indicator 子控件（16px 深色底 + 灰边框），并用 QPainter
    绘制白色勾 ✓（勾选框）与白色圆点（单选钮）保存到临时目录，再以
    image: url(...) 引用。与 spin_arrow_stylesheet 同机制。
    """
    import tempfile
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor
    from PyQt5.QtCore import QPoint

    icons_dir = Path(tempfile.gettempdir()) / "DeepScribe" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    check_path = icons_dir / "check_white.png"
    dot_path = icons_dir / "radio_dot.png"

    def _draw_check(path: Path):
        pm = QPixmap(14, 14)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#ffffff"), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPoint(3, 7), QPoint(6, 10), QPoint(11, 3)])
        p.end()
        pm.save(str(path), "PNG")

    def _draw_dot(path: Path):
        pm = QPixmap(14, 14)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(3, 3, 8, 8)
        p.end()
        pm.save(str(path), "PNG")

    if not check_path.exists():
        _draw_check(check_path)
    if not dot_path.exists():
        _draw_dot(dot_path)

    def _url(p: Path) -> str:
        return str(p).replace("\\", "/")

    return f"""
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid #7a7c80;
    border-radius: 3px;
    background-color: #2d2f31;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: #a0a3a8;
}}
QCheckBox::indicator:checked {{
    background-color: #6366f1;
    border-color: #6366f1;
    image: url("{_url(check_path)}");
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QRadioButton::indicator:checked {{
    background-color: #6366f1;
    border-color: #6366f1;
    image: url("{_url(dot_path)}");
}}
"""


# ============================================================
# 滚轮拦截器
# ============================================================
class ScrollBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            return True
        return super().eventFilter(obj, event)


def install_scroll_blockers(parent_widget):
    from PyQt5.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox
    blocker = ScrollBlocker(parent_widget)
    for typ in (QComboBox, QSpinBox, QDoubleSpinBox):
        for w in parent_widget.findChildren(typ):
            w.installEventFilter(blocker)


_HOVER_COLORS = {
    "actionBtn":   ("#4a4d52", "#cccccc"),
    "linkBtn":     ("#4a4d52", "#cccccc"),
    "batchStart":  ("#2d4a30", None),
    "batchStop":   ("#4a3d28", None),
    "batchClear":  ("#4a2828", None),
    "saveBtn":     ("#2d4a30", None),
    "restoreBtn":  ("#4a2828", None),
}

_HOVER_NAMES = set(_HOVER_COLORS.keys())


class HoverHighlighter(QObject):
    """事件过滤器：Enter 设悬停背景，Leave 恢复透明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_sheets: dict[int, str] = {}

    def eventFilter(self, obj, event):
        from PyQt5.QtWidgets import QPushButton
        if isinstance(obj, QPushButton):
            name = obj.objectName()
            if name in _HOVER_COLORS:
                bg, fg = _HOVER_COLORS[name]
                oid = id(obj)
                if event.type() == QEvent.Enter:
                    self._base_sheets[oid] = obj.styleSheet()
                    extra = f"QPushButton {{ background-color: {bg};"
                    if fg:
                        extra += f" color: {fg};"
                    extra += "}"
                    obj.setStyleSheet(self._base_sheets[oid] + extra)
                elif event.type() == QEvent.Leave:
                    base = self._base_sheets.pop(oid, "")
                    obj.setStyleSheet(base)
        return super().eventFilter(obj, event)


def install_hover_highlights(parent_widget):
    """给 parent 下所有自定义按钮安装悬停高亮。"""
    from PyQt5.QtWidgets import QPushButton
    highlighter = HoverHighlighter(parent_widget)
    for btn in parent_widget.findChildren(QPushButton):
        if btn.objectName() in _HOVER_NAMES:
            btn.setAttribute(Qt.WA_Hover, True)
            btn.installEventFilter(highlighter)


class _NoCheckComboDelegate(QStyledItemDelegate):
    """去掉下拉弹出列表当前选中项前面的勾。

    QComboBoxListView 对当前项同时设置 State_Selected 与 State_On，
    Fusion 会对 State_On 项画一个选中勾。在 initStyleOption 中清除
    State_On 即可去掉勾，同时保留 State_Selected 的选中高亮背景。
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.state &= ~QStyle.State_On


def fix_combo_hover_colors(parent_widget):
    """往 QComboBox 的下拉 view 上直接挂内联样式，并重置下拉框左内边距。"""
    from PyQt5.QtWidgets import QComboBox
    for combo in parent_widget.findChildren(QComboBox):
        # 下拉视图宽度自适应内容，避免选项文字被截断
        combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        view = combo.view()
        if view is None:
            continue
        # 去掉当前选中项前的勾（Fusion 由 State_On 绘制）
        view.setItemDelegate(_NoCheckComboDelegate(view))
        view.setStyleSheet("""
            QAbstractItemView {
                padding: 0;
                margin: 0;
            }
            QAbstractItemView::item {
                padding: 6px 10px;
                margin: 0;
            }
            QAbstractItemView::item:hover {
                background-color: #3a3d40;
                color: #cccccc;
            }
            QAbstractItemView::item:selected {
                background-color: #6366f1;
                color: #ffffff;
            }
        """)
        # 重置下拉框本身过大的左内边距（仅 QComboBox 自身，勿用 ::item——
        # 它同时作用于弹出列表项，会把行高撑成整屏高）
        combo.setStyleSheet(combo.styleSheet() + """
            QComboBox {
                padding: 4px 8px;
            }
        """)
