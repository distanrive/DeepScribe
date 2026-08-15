"""
配置页面：API 设置 / 解析设置 / 并行翻译 / 高级配置
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QGroupBox, QScrollArea, QFrame,
    QMessageBox,
)

from gui.styles import install_scroll_blockers, fix_combo_hover_colors, install_hover_highlights


class ConfigPage(QWidget):
    """配置页面，含 API / 解析 / 并行 / 高级四个分组。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._cfg = config
        self._api_key_field: QLineEdit | None = None
        self._setup_ui()
        self._load_config()
        # 禁止滚轮改变下拉框/数字框的值
        install_scroll_blockers(self)
        # 修复下拉悬停蓝底白字看不清的问题
        fix_combo_hover_colors(self)
        # 按钮悬停高亮
        install_hover_highlights(self)

    # ============================================================
    # UI 构建
    # ============================================================
    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 24, 32, 32)
        layout.setSpacing(16)

        # 页面标题
        title = QLabel("配置")
        title.setStyleSheet("""
            font-size: 18px; font-weight: 800;
            padding-bottom: 8px; background: transparent;
        """)
        layout.addWidget(title)

        # ---- 各配置分组 ----
        layout.addWidget(self._build_api_group())
        layout.addWidget(self._build_parser_group())
        layout.addWidget(self._build_parallel_group())
        layout.addWidget(self._build_advanced_group())

        # ---- 按钮行（居中）----
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        btn_row.setSpacing(16)

        self._restore_btn = QPushButton("↻  恢复默认设置")
        self._restore_btn.setObjectName("restoreBtn")
        self._restore_btn.setMinimumSize(170, 42)
        self._restore_btn.clicked.connect(self._restore_defaults)
        btn_row.addWidget(self._restore_btn)

        self._save_btn = QPushButton("💾  保存配置")
        self._save_btn.setObjectName("saveBtn")
        self._save_btn.setMinimumSize(170, 42)
        self._save_btn.clicked.connect(self._save_config)
        btn_row.addWidget(self._save_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ============================================================
    # 分组：API 设置
    # ============================================================
    def _build_api_group(self) -> QGroupBox:
        g = QGroupBox("API 设置")
        layout = QVBoxLayout(g)
        layout.setSpacing(12)

        # API Key
        row1 = QHBoxLayout()
        row1.addWidget(self._label("API Key"))
        self._api_key_field = QLineEdit()
        self._api_key_field.setEchoMode(QLineEdit.Password)
        self._api_key_field.setPlaceholderText("输入 DeepSeek API Key")
        self._api_key_field.setMinimumWidth(360)
        row1.addWidget(self._api_key_field, 1)

        hint = QLabel("🔒 使用 Windows DPAPI 加密存储，仅当前用户可解密")
        hint.setStyleSheet("font-size: 12px; background: transparent;")
        row1.addWidget(hint)
        layout.addLayout(row1)

        # 模型
        row2 = QHBoxLayout()
        row2.addWidget(self._label("模型"))
        self._model_combo = QComboBox()
        self._model_combo.addItems(["deepseek-v4-pro", "deepseek-v4-flash"])
        # L7: 可编辑——config.json 中其他模型名能正确显示，且不会被下拉默认值静默覆盖
        self._model_combo.setEditable(True)
        row2.addWidget(self._model_combo, 1)
        row2.addStretch(2)
        layout.addLayout(row2)

        # 强度 + 思考模式
        row3 = QHBoxLayout()
        row3.addWidget(self._label("推理强度"))
        self._effort_combo = QComboBox()
        self._effort_combo.addItems(["low", "medium", "high", "max"])
        row3.addWidget(self._effort_combo)

        row3.addSpacing(24)
        row3.addWidget(self._label("思考模式"))
        self._thinking_check = QCheckBox("启用思考模式")
        self._thinking_check.setToolTip("额外消耗 token，但可提高翻译质量")
        row3.addWidget(self._thinking_check)
        row3.addStretch()
        layout.addLayout(row3)

        return g

    # ============================================================
    # 分组：解析设置
    # ============================================================
    def _build_parser_group(self) -> QGroupBox:
        g = QGroupBox("解析设置")
        layout = QVBoxLayout(g)
        layout.setSpacing(12)

        row1 = QHBoxLayout()
        row1.addWidget(self._label("解析后端"))
        self._backend_combo = QComboBox()
        self._backend_combo.addItems(["pipeline", "hybrid-engine", "vlm-engine"])
        self._backend_combo.setToolTip(
            "pipeline: 快速稳定，CPU/GPU 均可\n"
            "hybrid-engine: 高精度，需 GPU ≥ 8 GB\n"
            "vlm-engine: 纯 VLM 引擎，需 GPU"
        )
        row1.addWidget(self._backend_combo)

        row1.addSpacing(16)
        row1.addWidget(self._label("解析强度"))
        self._parser_effort_combo = QComboBox()
        self._parser_effort_combo.addItems(["medium", "high"])
        self._parser_effort_combo.setToolTip("medium: 更快 | high: 更准（含 image analysis）")
        row1.addWidget(self._parser_effort_combo)

        row1.addSpacing(16)
        row1.addWidget(self._label("超时（秒）"))
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(60, 7200)
        self._timeout_spin.setSuffix(" 秒")
        row1.addWidget(self._timeout_spin)
        row1.addStretch()
        layout.addLayout(row1)

        return g

    # ============================================================
    # 分组：并行翻译
    # ============================================================
    def _build_parallel_group(self) -> QGroupBox:
        g = QGroupBox("并行翻译设置")
        layout = QVBoxLayout(g)
        layout.setSpacing(12)

        row1 = QHBoxLayout()
        self._parallel_check = QCheckBox("启用并行翻译")
        self._parallel_check.setToolTip("PDF 含书签时按章节并行翻译；无书签自动退回串行")
        row1.addWidget(self._parallel_check)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._label("最大并发线程数"))
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 256)
        self._workers_spin.setToolTip("受 API rate limit 约束")
        row2.addWidget(self._workers_spin)

        row2.addSpacing(16)
        row2.addWidget(self._label("MinerU 最大并发"))
        self._mineru_spin = QSpinBox()
        self._mineru_spin.setRange(1, 8)
        self._mineru_spin.setToolTip(
            "1=串行（安全稳定）\n"
            "hybrid-engine 每实例约 2-3 GB 显存\n"
            "8 GB 显卡建议 ≤ 2"
        )
        row2.addWidget(self._mineru_spin)

        row2.addSpacing(16)
        row2.addWidget(self._label("大章拆分阈值（页）"))
        self._chapter_pages_spin = QSpinBox()
        self._chapter_pages_spin.setRange(0, 9999)
        self._chapter_pages_spin.setSpecialValueText("禁用")
        self._chapter_pages_spin.setToolTip("某章超过此页数时自动用二级书签拆分；0=禁用")
        row2.addWidget(self._chapter_pages_spin)
        row2.addStretch()
        layout.addLayout(row2)

        return g

    # ============================================================
    # 分组：高级配置
    # ============================================================
    def _build_advanced_group(self) -> QGroupBox:
        g = QGroupBox("高级配置")
        layout = QVBoxLayout(g)
        layout.setSpacing(12)

        row1 = QHBoxLayout()
        row1.addWidget(self._label("Max Tokens (输出)"))
        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(1024, 131072)
        self._max_tokens_spin.setToolTip("API 响应 max_tokens；设太高可能超出模型输出限制")
        row1.addWidget(self._max_tokens_spin)

        row1.addSpacing(16)
        row1.addWidget(self._label("温度"))
        self._temp_spin = QDoubleSpinBox()
        self._temp_spin.setRange(0.0, 2.0)
        self._temp_spin.setSingleStep(0.1)
        self._temp_spin.setToolTip("学术翻译建议 0.3")
        row1.addWidget(self._temp_spin)

        row1.addSpacing(16)
        row1.addWidget(self._label("目标 Token/次"))
        self._target_tokens_spin = QSpinBox()
        self._target_tokens_spin.setRange(1000, 100000)
        self._target_tokens_spin.setToolTip("每次 API 调用目标 token 数（输入侧），实际受 MAX_TOKENS//2 钳制")
        row1.addWidget(self._target_tokens_spin)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._label("段落硬上限"))
        self._max_paras_spin = QSpinBox()
        self._max_paras_spin.setRange(10, 500)
        row2.addWidget(self._max_paras_spin)

        row2.addSpacing(16)
        row2.addWidget(self._label("Marker 保留率阈值"))
        self._marker_spin = QDoubleSpinBox()
        self._marker_spin.setRange(0.0, 1.0)
        self._marker_spin.setSingleStep(0.05)
        self._marker_spin.setToolTip("低于此值自动缩小分块；设为 1.0 禁用自适应")
        row2.addWidget(self._marker_spin)

        row2.addSpacing(16)
        self._integrity_check = QCheckBox("启用完整性校验")
        self._integrity_check.setToolTip("检测译文行内公式/代码是否被 LLM 损坏，损坏则回填原文（零额外 API）")
        row2.addWidget(self._integrity_check)
        row2.addStretch()
        layout.addLayout(row2)

        return g

    # ============================================================
    # 加载 / 保存 / 恢复默认
    # ============================================================
    def _load_config(self):
        """从配置管理器加载到 UI 控件。"""
        self._api_key_field.setText(self._cfg.get_api_key())
        self._model_combo.setCurrentText(self._cfg.get("api", "model"))
        self._effort_combo.setCurrentText(self._cfg.get("api", "reasoning_effort"))
        self._thinking_check.setChecked(self._cfg.get("api", "use_thinking"))

        self._backend_combo.setCurrentText(self._cfg.get("parser", "backend"))
        self._parser_effort_combo.setCurrentText(self._cfg.get("parser", "effort"))
        self._timeout_spin.setValue(self._cfg.get("parser", "timeout"))

        self._parallel_check.setChecked(self._cfg.get("parallel", "enable"))
        self._workers_spin.setValue(self._cfg.get("parallel", "max_workers"))
        self._mineru_spin.setValue(self._cfg.get("parallel", "max_mineru"))
        self._chapter_pages_spin.setValue(self._cfg.get("parallel", "max_chapter_pages"))

        self._max_tokens_spin.setValue(self._cfg.get("translation", "max_tokens"))
        self._temp_spin.setValue(self._cfg.get("translation", "temperature"))
        self._target_tokens_spin.setValue(self._cfg.get("translation", "target_tokens_per_call"))
        self._max_paras_spin.setValue(self._cfg.get("translation", "max_paras_per_call"))
        self._marker_spin.setValue(self._cfg.get("translation", "min_marker_retention"))
        self._integrity_check.setChecked(self._cfg.get("translation", "enable_integrity"))

        # 已保存的 Key 无法解密（DPAPI 密钥失效/换机器）→ 提醒重新输入
        ok, msg = self._cfg.api_key_status()
        if not ok:
            QMessageBox.warning(
                self, "API Key 解密失败",
                f"{msg}\n\n请重新输入并保存 API Key。")

    def _save_config(self):
        """从 UI 控件保存到配置管理器。"""
        try:
            self._cfg.set_api_key(self._api_key_field.text().strip())
        except OSError as e:
            QMessageBox.critical(
                self, "保存失败",
                f"API Key 加密失败：{e}\n\n其余配置未保存。")
            return
        self._cfg.set("api", "model", value=self._model_combo.currentText())
        self._cfg.set("api", "reasoning_effort", value=self._effort_combo.currentText())
        self._cfg.set("api", "use_thinking", value=self._thinking_check.isChecked())

        self._cfg.set("parser", "backend", value=self._backend_combo.currentText())
        self._cfg.set("parser", "effort", value=self._parser_effort_combo.currentText())
        self._cfg.set("parser", "timeout", value=self._timeout_spin.value())

        self._cfg.set("parallel", "enable", value=self._parallel_check.isChecked())
        self._cfg.set("parallel", "max_workers", value=self._workers_spin.value())
        self._cfg.set("parallel", "max_mineru", value=self._mineru_spin.value())
        self._cfg.set("parallel", "max_chapter_pages", value=self._chapter_pages_spin.value())

        self._cfg.set("translation", "max_tokens", value=self._max_tokens_spin.value())
        self._cfg.set("translation", "temperature", value=self._temp_spin.value())
        self._cfg.set("translation", "target_tokens_per_call", value=self._target_tokens_spin.value())
        self._cfg.set("translation", "max_paras_per_call", value=self._max_paras_spin.value())
        self._cfg.set("translation", "min_marker_retention", value=self._marker_spin.value())
        self._cfg.set("translation", "enable_integrity", value=self._integrity_check.isChecked())

        self._cfg.save()
        QMessageBox.information(self, "保存成功", "配置已保存到 config.json")

    def _restore_defaults(self):
        """恢复为代码内嵌的默认配置。"""
        reply = QMessageBox.question(
            self, "确认恢复",
            "将放弃当前所有配置，恢复为默认设置。\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # 用公开方法恢复默认（不再直接触碰 ConfigManager 私有成员）
        self._cfg.restore_defaults()
        self._load_config()
        QMessageBox.information(self, "已恢复", "配置已恢复为默认值并保存。")

    # ============================================================
    # 样式辅助
    # ============================================================
    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("""
            font-size: 13px;
            background: transparent;
            min-width: 80px;
        """)
        return lbl
