"""
DeepScribe GUI — 自定义样式。
基础主题由 qt-material (dark_blue.xml) 提供。
本文件覆盖背景色 + 自定义控件 + 多种强调色按钮。
"""
from PySide6.QtCore import Qt, QObject, QEvent

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

/* 悬停项：深灰底，文字不变 —— 必须压过 qt-material */
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

/* 修复下拉框文字被截断：qt-material 在 QComboBox::item 上加了巨大的
   padding-left（为勾选指示器留空间），这里重置为合理值 */
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
    min-width: 240px;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    margin: 0;
    text-align: left;
}}
QComboBox::item {{
    padding: 6px 10px;
    margin: 0;
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

/* ===== [3] 多种强调色按钮（#id 高优先级覆写 qt-material）===== */

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
    font-size: 12px;
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
}}
"""


# ============================================================
# 滚轮拦截器
# ============================================================
class ScrollBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return super().eventFilter(obj, event)


def install_scroll_blockers(parent_widget):
    from PySide6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox
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
        from PySide6.QtWidgets import QPushButton
        if isinstance(obj, QPushButton):
            name = obj.objectName()
            if name in _HOVER_COLORS:
                bg, fg = _HOVER_COLORS[name]
                oid = id(obj)
                if event.type() == QEvent.Type.Enter:
                    self._base_sheets[oid] = obj.styleSheet()
                    extra = f"QPushButton {{ background-color: {bg};"
                    if fg:
                        extra += f" color: {fg};"
                    extra += "}"
                    obj.setStyleSheet(self._base_sheets[oid] + extra)
                elif event.type() == QEvent.Type.Leave:
                    base = self._base_sheets.pop(oid, "")
                    obj.setStyleSheet(base)
        return super().eventFilter(obj, event)


def install_hover_highlights(parent_widget):
    """给 parent 下所有自定义按钮安装悬停高亮。"""
    from PySide6.QtWidgets import QPushButton
    highlighter = HoverHighlighter(parent_widget)
    for btn in parent_widget.findChildren(QPushButton):
        if btn.objectName() in _HOVER_NAMES:
            btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            btn.installEventFilter(highlighter)


def fix_combo_hover_colors(parent_widget):
    """往 QComboBox 的下拉 view 上直接挂内联样式，并重置被 qt-material 撑大的左内边距。"""
    from PySide6.QtWidgets import QComboBox
    for combo in parent_widget.findChildren(QComboBox):
        # 下拉视图宽度自适应内容，避免选项文字被截断
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        view = combo.view()
        if view is None:
            continue
        view.setStyleSheet("""
            QAbstractItemView {
                min-width: 200px;
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
        # 重置 qt-material 在 combo 本身上设置的大左内边距
        combo.setStyleSheet(combo.styleSheet() + """
            QComboBox {
                padding: 4px 8px;
            }
            QComboBox::item {
                padding: 6px 10px;
            }
        """)
