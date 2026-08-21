"""
工作页面：文件拖放 → 状态表格(树) → 批量操作 → 日志
"""
import html
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QTextEdit,
    QFileDialog, QAbstractItemView, QCheckBox,
)

from gui.styles import COLORS, install_hover_highlights
from gui.workers import ProcessWorker

COL_FILE = 0
COL_STATUS = 1
COL_ACTION = 2

# 子节点状态枚举存储角色（与列 0 的 UserRole 存放 chapter order 区分开），
# 用于 _has_child_error 判定，避免依赖显示文案（改文案即失效）。
ROLE_STATUS = Qt.UserRole + 1

STATUS_LABELS = {
    "queued":      ("等待中", "#b0b0b0"),
    "parsing":     ("解析中", COLORS["info"]),
    "translating": ("翻译中", COLORS["warning"]),
    "done":        ("✅ 完成", COLORS["success"]),
    "error":       ("❌ 失败", COLORS["error"]),
    "cancelled":   ("⏸ 已取消", "#808080"),
    "partial":     ("⚠️ 部分失败", COLORS["warning"]),
    "working":     ("工作中", COLORS["info"]),
}


class _CenteredHeader(QHeaderView):
    """表头：指定列标题单元格内居中，其余列保持左对齐。"""

    def __init__(self, orientation, parent=None, centered_cols=()):
        super().__init__(orientation, parent)
        self._centered_cols = set(centered_cols)

    def paintSection(self, painter, rect, logicalIndex):
        old = self.defaultAlignment()
        if logicalIndex in self._centered_cols:
            self.setDefaultAlignment(Qt.AlignCenter)
        else:
            self.setDefaultAlignment(
                Qt.AlignLeft | Qt.AlignVCenter)
        super().paintSection(painter, rect, logicalIndex)
        self.setDefaultAlignment(old)


class DropZone(QWidget):
    files_selected = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(130)
        self.setMaximumHeight(150)
        self.setObjectName("dropZone")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._setup_ui()
        self._update_border(False)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        icon_lbl = QLabel("📂")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 32px; background: transparent;")
        layout.addWidget(icon_lbl)
        hint = QLabel("拖放 PDF 文件到此处，或点击下方按钮选择")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 13px; background: transparent;")
        layout.addWidget(hint)
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        self._btn = QPushButton("选择 PDF 文件")
        self._btn.setObjectName("actionBtn")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._on_click)
        btn_row.addWidget(self._btn)
        layout.addLayout(btn_row)

    def _on_click(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF 文件", "", "PDF Files (*.pdf);;All Files (*)")
        if files:
            self.files_selected.emit(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._update_border(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._update_border(False)

    def dropEvent(self, event: QDropEvent):
        self._update_border(False)
        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if url.toLocalFile().lower().endswith(".pdf")]
        if paths:
            self.files_selected.emit(paths)

    def _update_border(self, active: bool):
        color = COLORS["drop_border"] if active else "#7a7c80"
        bg = COLORS["drop_bg"] if active else "rgba(255,255,255,0.03)"
        self.setStyleSheet(f"""#dropZone {{
            border: 2px dashed {color}; border-radius: 12px; background-color: {bg}; }}""")


class WorkPage(QWidget):

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._workers: dict[str, ProcessWorker] = {}
        self._file_items: dict[str, QTreeWidgetItem] = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._flush_logs)
        self._timer.start(250)
        self._log_queue: list[tuple[str, str]] = []
        self._parts_status: dict[str, dict[int, str]] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.drop_zone = DropZone()
        self.drop_zone.files_selected.connect(self._add_files)
        layout.addWidget(self.drop_zone)

        layout.addWidget(self._hdr("文件列表"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["文件名", "状态", "操作"])
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.setFocusPolicy(Qt.NoFocus)
        self.tree.setIndentation(24)
        self.tree.setAnimated(True)
        hdr = _CenteredHeader(Qt.Horizontal, self.tree,
                              centered_cols=(COL_STATUS, COL_ACTION))
        self.tree.setHeader(hdr)
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(COL_FILE, QHeaderView.Stretch)
        for c in (COL_STATUS, COL_ACTION):
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
        self.tree.setColumnWidth(COL_STATUS, 110)
        self.tree.setColumnWidth(COL_ACTION, 180)
        layout.addWidget(self.tree, 3)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        btn_row.setSpacing(16)
        self._force_check = QCheckBox("强制重新解析 (MinerU)")
        self._force_check.setToolTip(
            "重新运行 MinerU 解析，忽略已缓存结果。\n切换解析后端（如 pipeline→hybrid-engine）后需勾选。")
        btn_row.addWidget(self._force_check)
        self._parallel_check = QCheckBox("启用并行翻译")
        self._parallel_check.setToolTip("PDF 含书签时按章节并行翻译；无书签自动退回串行")
        self._parallel_check.setChecked(bool(self._config.get("parallel", "enable")))
        btn_row.addWidget(self._parallel_check)
        btn_row.addSpacing(8)
        self._btn_all_start = self._batch_btn("▶  全部开始", "batchStart", self._start_all)
        self._btn_all_stop  = self._batch_btn("⏹  全部停止", "batchStop", self._stop_all)
        self._btn_all_clear = self._batch_btn("🗑  全部删除", "batchClear", self._clear_all)
        btn_row.addWidget(self._btn_all_start)
        btn_row.addWidget(self._btn_all_stop)
        btn_row.addWidget(self._btn_all_clear)
        btn_row.addSpacing(8)
        self._parse_only_check = QCheckBox("仅解析")
        self._parse_only_check.setToolTip(
            "只运行 MinerU 解析并输出 {文件名}_parsed.md，跳过翻译（省 API 费用）")
        btn_row.addWidget(self._parse_only_check)
        layout.addLayout(btn_row)

        layout.addWidget(self._hdr("日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(2000)
        layout.addWidget(self.log_view, 2)

        self._update_batch_buttons()
        install_hover_highlights(self)

    @staticmethod
    def _hdr(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("font-size:14px; font-weight:700; padding-top:4px; background:transparent;")
        return l

    @staticmethod
    def _batch_btn(text: str, name: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(name)
        btn.setMinimumSize(140, 38)
        btn.clicked.connect(slot)
        return btn

    # ============================================================
    def _add_files(self, paths: list[str]):
        for p in paths:
            p = str(Path(p).resolve())
            if p in self._file_items:
                continue
            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, p)
            item.setText(COL_FILE, Path(p).name)
            item.setToolTip(COL_FILE, p)
            self._set_item_texts(item, "等待中", "#b0b0b0")
            self._file_items[p] = item
            self.tree.addTopLevelItem(item)
            self.tree.setItemWidget(item, COL_ACTION, self._action_btns(p))
            self._log_queue.append((p, f"📄 已添加: {Path(p).name}"))
        self._update_batch_buttons()

    def _set_item_texts(self, item: QTreeWidgetItem, status_t: str, status_c: str):
        item.setText(COL_STATUS, status_t)
        item.setTextAlignment(COL_STATUS, Qt.AlignCenter)
        item.setForeground(COL_STATUS, QColor(status_c))

    def _action_btns(self, file_path: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lo = QHBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(6)
        fp = file_path  # 捕获到局部变量
        for text, callback in [("开始", self._start_file),
                                ("停止", self._stop_file),
                                ("删除", self._remove_file)]:
            btn = QPushButton(text)
            btn.setObjectName("actionBtn")
            btn.setFixedSize(44, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, cb=callback, p=fp: cb(p))
            lo.addWidget(btn, 0, Qt.AlignVCenter)
        return w

    # ============================================================
    def _start_file(self, file_path: str):
        if file_path in self._workers and self._workers[file_path].is_running():
            return
        env = self._config.export_env()
        # 工作区「启用并行翻译」复选框覆盖 config 的 parallel.enable（每次运行即时生效）
        env["ENABLE_PARALLEL"] = "true" if self._parallel_check.isChecked() else "false"
        worker = ProcessWorker(Path(file_path), env,
                               force=self._force_check.isChecked(),
                               parse_only=self._parse_only_check.isChecked())
        worker.signals.file_status.connect(self._on_file_status)
        worker.signals.log.connect(self._on_worker_log)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.part_status.connect(self._on_part_status)
        self._workers[file_path] = worker
        self._set_item_status(file_path, "queued")
        self._log_queue.append((file_path, "▶ 开始处理"))
        worker.start()
        self._update_batch_buttons()

    def _stop_file(self, file_path: str):
        w = self._workers.get(file_path)
        if w and w.is_running():
            w.cancel()  # 异步杀子进程树；worker 退出后由 _on_finished 清理
            self._set_item_status(file_path, "cancelled")
            self._log_queue.append((file_path, "⏸ 已停止"))
            self._update_batch_buttons()

    def _remove_file(self, file_path: str):
        self._stop_file(file_path)
        item = self._file_items.pop(file_path, None)
        if item:
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
        self._workers.pop(file_path, None)
        self._parts_status.pop(file_path, None)
        self._log_queue.append((file_path, "🗑 已删除"))
        self._update_batch_buttons()

    def _start_all(self):
        for fp in list(self._file_items):
            if fp not in self._workers or not self._workers[fp].is_running():
                self._start_file(fp)

    def _stop_all(self):
        # 迭代副本：cancel 可能触发 _on_finished 弹出 worker，避免遍历时改 dict
        for fp, w in list(self._workers.items()):
            if w.is_running():
                w.cancel()  # 杀子进程树，任务会真正停止
                self._set_item_status(fp, "cancelled")
        self._log_queue.append(("_system", "⏸ 已请求停止全部任务"))
        self._update_batch_buttons()

    def _clear_all(self):
        for fp in list(self._file_items):
            self._remove_file(fp)
        self.log_view.clear()
        self._log_queue.append(("_system", "🗑 已清空全部文件"))

    def shutdown(self):
        """应用退出时取消所有运行中的任务并等待线程结束。"""
        for fp in list(self._workers):
            w = self._workers[fp]
            if w.is_running():
                w.cancel()
                w.wait(3000)
        self._workers.clear()

    # ============================================================
    def _on_file_status(self, file_path: str, field: str, value):
        item = self._file_items.get(file_path)
        if not item:
            return
        if field == "status":
            if value == "done" and self._has_child_error(item):
                self._set_item_status(file_path, "partial")
                return
            # 有子章节时，父行不显示解析中/翻译中（子行有具体阶段）
            if item.childCount() > 0 and value in ("parsing", "translating"):
                self._set_item_status(file_path, "working")
                return
            self._set_item_status(file_path, value)

    @staticmethod
    def _has_child_error(item: QTreeWidgetItem) -> bool:
        """检查 item 的所有子节点是否有 error 状态（按状态枚举，不依赖显示文案）。"""
        for i in range(item.childCount()):
            if item.child(i).data(0, ROLE_STATUS) == "error":
                return True
        return False

    def _on_part_status(self, file_path: str, part_order: int, field: str, value):
        """并行模式子章节状态；order<0 表示串行模式的文件级阶段通知。"""
        item = self._file_items.get(file_path)
        if not item:
            return
        if part_order < 0:
            # 串行模式：直接更新文件行阶段
            if field == "status":
                self._set_item_status(file_path, value)
            return
        # 按 order 查找或创建子项
        child = None
        for i in range(item.childCount()):
            c = item.child(i)
            if c.data(0, Qt.UserRole) == part_order:
                child = c
                break
        if child is None:
            child = QTreeWidgetItem()
            child.setData(0, Qt.UserRole, part_order)
            child.setData(0, ROLE_STATUS, "queued")
            child.setText(COL_FILE, f"第 {part_order + 1} 章")
            self._set_item_texts(child, "等待中", "#b0b0b0")
            item.addChild(child)
            item.setExpanded(True)
        if field == "title":
            child.setText(COL_FILE, f"第 {part_order + 1} 章: {value}")
        elif field == "status":
            child.setData(0, ROLE_STATUS, value)
            label, color = STATUS_LABELS.get(value, (value, "#b0b0b0"))
            child.setText(COL_STATUS, label)
            child.setForeground(COL_STATUS, QColor(color))
            # 汇总到文件行：任一章节翻译中 → 翻译中；否则有解析中 → 解析中
            self._parts_status.setdefault(file_path, {})[part_order] = value
            self._refresh_file_phase(file_path)

    def _refresh_file_phase(self, file_path: str):
        """由各章状态推导文件行阶段。
        有子章节时父行只用通用状态：等待中 → 工作中 → ✅/⚠️；
        具体阶段（解析中/翻译中）仅在子行显示。"""
        parts = self._parts_status.get(file_path, {})
        if any(v in ("translating", "parsing") for v in parts.values()):
            self._set_item_status(file_path, "working")
        elif any(v == "queued" for v in parts.values()):
            self._set_item_status(file_path, "queued")
        elif parts:
            # 所有章节都到达终态（done/error/cancelled）
            if any(v == "error" for v in parts.values()):
                self._set_item_status(file_path, "partial")
            else:
                self._set_item_status(file_path, "done")

    def _on_worker_log(self, file_path: str, message: str):
        self._log_queue.append((file_path, message))

    def _on_finished(self, file_path: str, success: bool, error_msg: str):
        # M6: 竞态防护——旧 worker 的 finished 信号可能在用户重开后被延迟处理，
        # 此时 _workers 已被新 worker 覆盖。比对信号发出者身份，避免误删新 worker，
        # 否则「全部停止」/「停止」将找不到正在运行的新任务。
        current = self._workers.get(file_path)
        if current is not None and self.sender() is not current.signals:
            return
        self._workers.pop(file_path, None)
        self._parts_status.pop(file_path, None)
        self._update_batch_buttons()
        if error_msg == "cancelled":
            return  # 取消路径已由 _stop_file / worker 记录日志
        item = self._file_items.get(file_path)
        has_child_error = item is not None and self._has_child_error(item)
        if success and not has_child_error:
            self._log_queue.append((file_path, "✅ 处理成功"))
        elif has_child_error:
            self._log_queue.append((file_path, "⚠️ 处理完成（部分章节失败，详见下方章节状态）"))
        else:
            self._log_queue.append((file_path, f"❌ 处理失败: {error_msg}"))

    # ============================================================
    def _set_item_status(self, file_path: str, status: str):
        item = self._file_items.get(file_path)
        if not item:
            return
        label, color = STATUS_LABELS.get(status, (status, "#b0b0b0"))
        item.setText(COL_STATUS, label)
        item.setForeground(COL_STATUS, QColor(color))

    def _flush_logs(self):
        if not self._log_queue:
            return
        batch = self._log_queue[:]
        self._log_queue.clear()
        for fp, msg in batch:
            prefix = Path(fp).name if fp != "_system" else ""
            # L6: 日志以 HTML 拼进 QTextEdit，转义 < > & 防止章节标题等破坏渲染
            if prefix:
                self.log_view.append(
                    f"<span style='color:{COLORS['primary']}'><b>[{html.escape(prefix)}]</b></span> "
                    f"{html.escape(msg)}")
            else:
                self.log_view.append(
                    f"<span style='color:{COLORS['text_dim']}'>{html.escape(msg)}</span>")
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum())

    def _update_batch_buttons(self):
        has = bool(self._file_items)
        running = any(w.is_running() for w in self._workers.values())
        self._btn_all_start.setEnabled(has)
        self._btn_all_stop.setEnabled(running)
        self._btn_all_clear.setEnabled(has)
