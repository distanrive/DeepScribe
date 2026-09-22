class_name ConfigPage
extends MarginContainer
## 配置页：改 config.json 里的各项参数（API Key 仍由后端 DPAPI 加密保存）。
##
## 所有值都**经后端**读写，前端不碰 config.json：
##   config_get → config_data 填充控件
##   config_set / config_set_api_key / config_restore → 后端落盘后再回一份 config_data
##
## API Key 单向：后端从不回传明文，输入框留空 = 不改动已保存的 Key。

const MODEL_ITEMS := ["deepseek-v4-pro", "deepseek-flash"]
const MODEL_CUSTOM := "自定义…"
const EFFORT_ITEMS := ["off", "low", "high", "max"]
const BACKEND_ITEMS := ["pipeline", "hybrid-engine", "vlm-engine"]
const PARSER_EFFORT_ITEMS := ["medium", "high"]

const LABEL_W := 132.0

var _key_edit: LineEdit
var _key_hint: Label
var _model_combo: OptionButton
var _model_custom: LineEdit
var _effort_combo: OptionButton
var _thinking_check: CheckBox
var _backend_combo: OptionButton
var _parser_effort_combo: OptionButton
var _timeout_spin: SpinBox
var _workers_spin: SpinBox
var _mineru_spin: SpinBox
var _chapter_pages_spin: SpinBox
var _chapter_pages_hint: Label
var _max_tokens_spin: SpinBox
var _temp_spin: SpinBox
var _target_tokens_spin: SpinBox
var _max_paras_spin: SpinBox
var _marker_spin: SpinBox
var _integrity_check: CheckBox
var _status: Label

## 已保存的模型名（含未知值），用于「自定义…」哨兵项
var _known_models: PackedStringArray = PackedStringArray()
var _loading := false


func _init() -> void:
	_build_ui()


func _ready() -> void:
	NetClient.data_received.connect(_on_backend_message)
	# 建页面时 WebSocket 还没连上（连接是异步的），直接发会被丢弃 —— 连上再取，
	# 且每次重连都取一次，保证后端重启后表单仍与 config.json 一致。
	NetClient.connected.connect(_request_config)
	_request_config()


# ================================================================ 界面
func _build_ui() -> void:
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)

	var root := VBoxContainer.new()
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_theme_constant_override("separation", ThemePalette.SEP_BOX)
	scroll.add_child(root)

	var title := Label.new()
	title.text = "配置"
	title.theme_type_variation = "PageTitle"
	root.add_child(title)

	var sub := Label.new()
	sub.text = "改动保存后立即生效（每个文件以独立子进程运行，启动时读最新配置）"
	sub.theme_type_variation = "Subtitle"
	root.add_child(sub)

	root.add_child(_build_api_group())
	root.add_child(_build_parser_group())
	root.add_child(_build_parallel_group())
	root.add_child(_build_advanced_group())

	# ---- 底部按钮 + 状态 ----
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 14)
	root.add_child(row)

	var restore := Button.new()
	restore.text = "恢复默认设置"
	restore.theme_type_variation = "GhostButton"
	restore.custom_minimum_size = Vector2(150, 36)
	restore.tooltip_text = "放弃当前所有配置，恢复为 config.py 里的默认值"
	restore.pressed.connect(_on_restore)
	row.add_child(restore)

	var save := Button.new()
	save.text = "保存配置"
	save.theme_type_variation = "AccentButton"
	save.custom_minimum_size = Vector2(150, 36)
	save.pressed.connect(_on_save)
	row.add_child(save)

	_status = Label.new()
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status.theme_type_variation = "Caption"
	root.add_child(_status)


func _build_api_group() -> TitledGroup:
	var g := TitledGroup.new()
	g.title = "API 设置"
	var box := _rows(g)

	# API Key
	var key_row := HBoxContainer.new()
	key_row.add_child(_label("API Key"))
	_key_edit = LineEdit.new()
	_key_edit.secret = true
	_key_edit.placeholder_text = "输入 DeepSeek API Key"
	_key_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	key_row.add_child(_key_edit)
	box.add_child(key_row)

	_key_hint = Label.new()
	_key_hint.theme_type_variation = "Caption"
	box.add_child(_key_hint)

	# 模型：已知项 + 「自定义…」哨兵
	var model_row := HBoxContainer.new()
	model_row.add_child(_label("模型"))
	_model_combo = OptionButton.new()
	_model_combo.custom_minimum_size.x = 220
	_model_combo.item_selected.connect(_on_model_selected)
	model_row.add_child(_model_combo)
	_model_custom = LineEdit.new()
	_model_custom.placeholder_text = "自定义模型名"
	_model_custom.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_model_custom.visible = false
	model_row.add_child(_model_custom)
	model_row.add_child(_stretch())
	box.add_child(model_row)

	# 推理强度 + 思考模式
	var effort_row := HBoxContainer.new()
	effort_row.add_child(_label("推理强度"))
	_effort_combo = OptionButton.new()
	_fill_combo(_effort_combo, EFFORT_ITEMS)
	_effort_combo.custom_minimum_size.x = 120
	effort_row.add_child(_effort_combo)
	effort_row.add_child(_gap(20))
	effort_row.add_child(_label("思考模式"))
	_thinking_check = CheckBox.new()
	_thinking_check.text = "启用思考模式"
	_thinking_check.tooltip_text = "额外消耗 token，但可提高翻译质量"
	effort_row.add_child(_thinking_check)
	effort_row.add_child(_stretch())
	box.add_child(effort_row)

	return g


func _build_parser_group() -> TitledGroup:
	var g := TitledGroup.new()
	g.title = "解析设置"
	var box := _rows(g)

	var row := HBoxContainer.new()
	row.add_child(_label("解析后端"))
	_backend_combo = OptionButton.new()
	_fill_combo(_backend_combo, BACKEND_ITEMS)
	_backend_combo.custom_minimum_size.x = 150
	_backend_combo.tooltip_text = ("pipeline: 快速稳定，CPU/GPU 均可\n"
			+ "hybrid-engine: 高精度，需 GPU ≥ 8 GB\n"
			+ "vlm-engine: 纯 VLM 引擎，需 GPU")
	row.add_child(_backend_combo)
	row.add_child(_gap(20))

	row.add_child(_label("解析强度"))
	_parser_effort_combo = OptionButton.new()
	_fill_combo(_parser_effort_combo, PARSER_EFFORT_ITEMS)
	_parser_effort_combo.custom_minimum_size.x = 110
	_parser_effort_combo.tooltip_text = "medium: 更快 | high: 更准（含 image analysis）"
	row.add_child(_parser_effort_combo)
	row.add_child(_gap(20))

	row.add_child(_label("超时（秒）"))
	_timeout_spin = _spin(60, 7200, 1)
	_timeout_spin.tooltip_text = "单次 MinerU 运行的超时时间"
	row.add_child(_timeout_spin)
	row.add_child(_stretch())
	box.add_child(row)

	return g


func _build_parallel_group() -> TitledGroup:
	var g := TitledGroup.new()
	g.title = "并行设置"
	var box := _rows(g)

	var row := HBoxContainer.new()
	row.add_child(_label("最大翻译并发"))
	_workers_spin = _spin(1, 256, 1)
	_workers_spin.tooltip_text = "翻译阶段的线程数，受 API rate limit 约束"
	row.add_child(_workers_spin)
	row.add_child(_gap(20))

	row.add_child(_label("解析最大并发"))
	_mineru_spin = _spin(1, 8, 1)
	_mineru_spin.tooltip_text = ("同时跑几个 MinerU（跨文件全局限制）\n"
			+ "1 = 串行（安全稳定）\n"
			+ "hybrid-engine 每实例约 2-3 GB 显存，8 GB 显卡建议 ≤ 2")
	row.add_child(_mineru_spin)
	row.add_child(_gap(20))

	row.add_child(_label("大章拆分阈值（页）"))
	_chapter_pages_spin = _spin(0, 9999, 1)
	_chapter_pages_spin.tooltip_text = "某章超过此页数时自动用二级书签拆分；0 = 禁用"
	_chapter_pages_spin.value_changed.connect(func(_v): _refresh_chapter_hint())
	row.add_child(_chapter_pages_spin)
	_chapter_pages_hint = Label.new()
	_chapter_pages_hint.theme_type_variation = "Caption"
	row.add_child(_chapter_pages_hint)
	row.add_child(_stretch())
	box.add_child(row)

	return g


func _build_advanced_group() -> TitledGroup:
	var g := TitledGroup.new()
	g.title = "高级配置"
	var box := _rows(g)

	var row1 := HBoxContainer.new()
	row1.add_child(_label("Max Tokens (输出)"))
	_max_tokens_spin = _spin(1024, 131072, 1024)
	_max_tokens_spin.tooltip_text = "API 响应 max_tokens；设太高可能超出模型输出限制"
	row1.add_child(_max_tokens_spin)
	row1.add_child(_gap(20))

	row1.add_child(_label("温度"))
	_temp_spin = _spin(0.0, 2.0, 0.1)
	_temp_spin.tooltip_text = "学术翻译建议 0.3"
	row1.add_child(_temp_spin)
	row1.add_child(_gap(20))

	row1.add_child(_label("目标 Token/次"))
	_target_tokens_spin = _spin(1000, 100000, 1000)
	_target_tokens_spin.tooltip_text = "每次 API 调用目标 token 数（输入侧），实际受 MAX_TOKENS//2 钳制"
	row1.add_child(_target_tokens_spin)
	row1.add_child(_stretch())
	box.add_child(row1)

	var row2 := HBoxContainer.new()
	row2.add_child(_label("段落硬上限"))
	_max_paras_spin = _spin(10, 500, 10)
	_max_paras_spin.tooltip_text = "单次 API 调用最多段落数（防止标记遗漏）"
	row2.add_child(_max_paras_spin)
	row2.add_child(_gap(20))

	row2.add_child(_label("Marker 保留率阈值"))
	_marker_spin = _spin(0.0, 1.0, 0.05)
	_marker_spin.tooltip_text = "低于此值自动缩小分块；设为 1.0 禁用自适应"
	row2.add_child(_marker_spin)
	row2.add_child(_gap(20))

	_integrity_check = CheckBox.new()
	_integrity_check.text = "启用完整性校验"
	_integrity_check.tooltip_text = "检测译文行内公式/代码是否被 LLM 损坏，损坏则回填原文（零额外 API）"
	row2.add_child(_integrity_check)
	row2.add_child(_stretch())
	box.add_child(row2)

	return g


# ================================================================ 控件工厂
func _rows(group: TitledGroup) -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	group.content.add_child(box)
	return box


func _label(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.custom_minimum_size.x = LABEL_W
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return l


func _gap(w: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size.x = w
	return c


func _stretch() -> Control:
	var c := Control.new()
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return c


## 数值框。显示的小数位数由 step 决定（0.05 → 两位），不用另外设。
func _spin(mn: float, mx: float, step: float) -> SpinBox:
	var s := SpinBox.new()
	s.min_value = mn
	s.max_value = mx
	s.step = step
	s.custom_minimum_size.x = 116
	s.allow_greater = false
	s.allow_lesser = false
	return s


func _fill_combo(combo: OptionButton, items: Array) -> void:
	combo.clear()
	for it in items:
		combo.add_item(str(it))


func _select_combo(combo: OptionButton, value: String) -> void:
	for i in range(combo.item_count):
		if combo.get_item_text(i) == value:
			combo.select(i)
			return


# ================================================================ 读写
func _request_config() -> void:
	if not NetClient.is_open():
		return          # 没连上就别发（NetClient 丢弃并告警），connected 会再触发一次
	NetClient.send_command(DsProto.CMD_CONFIG_GET, {})


func _on_backend_message(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var msg: Dictionary = payload
	match str(msg.get("type", "")):
		DsProto.MSG_CONFIG_DATA:
			_apply_config(msg)
		DsProto.MSG_ERROR:
			_set_status("后端出错：%s" % str(msg.get("message", "")), DsProto.STATUS_ERROR)


func _apply_config(msg: Dictionary) -> void:
	_loading = true         # 填充期间不要触发任何写回
	var cfg: Dictionary = msg.get("config", {})
	var api: Dictionary = cfg.get("api", {})
	var parser: Dictionary = cfg.get("parser", {})
	var parallel: Dictionary = cfg.get("parallel", {})
	var trans: Dictionary = cfg.get("translation", {})

	# API Key 只回「有没有 / 能不能解密」，不回明文
	var has_key := bool(msg.get("has_key", false))
	var key_ok := bool(msg.get("key_ok", true))
	_key_edit.text = ""
	if not key_ok:
		_key_hint.text = "已保存的 API Key 无法解密（%s）——请重新输入并保存" % str(msg.get("key_msg", ""))
		_key_hint.theme_type_variation = "CaptionError"
	elif has_key:
		_key_hint.text = "已保存（留空则不改动）。使用 Windows DPAPI 加密，仅当前用户可解密。"
		_key_hint.theme_type_variation = "Caption"
	else:
		_key_hint.text = "尚未保存 API Key —— 请填写后再开始翻译。"
		_key_hint.theme_type_variation = "CaptionWarn"

	_setup_model_combo(str(api.get("model", "")))
	_select_combo(_effort_combo, str(api.get("reasoning_effort", "")))
	_thinking_check.button_pressed = bool(api.get("use_thinking", false))

	_select_combo(_backend_combo, str(parser.get("backend", "")))
	_select_combo(_parser_effort_combo, str(parser.get("effort", "")))
	_timeout_spin.value = float(parser.get("timeout", 1800))

	_workers_spin.value = float(parallel.get("max_workers", 64))
	_mineru_spin.value = float(parallel.get("max_mineru", 1))
	_chapter_pages_spin.value = float(parallel.get("max_chapter_pages", 100))
	_refresh_chapter_hint()

	_max_tokens_spin.value = float(trans.get("max_tokens", 65536))
	_temp_spin.value = float(trans.get("temperature", 0.3))
	_target_tokens_spin.value = float(trans.get("target_tokens_per_call", 30000))
	_max_paras_spin.value = float(trans.get("max_paras_per_call", 200))
	_marker_spin.value = float(trans.get("min_marker_retention", 0.95))
	_integrity_check.button_pressed = bool(trans.get("enable_integrity", true))

	_loading = false


## 模型下拉：内置两项 + 「自定义…」哨兵。
## config.json 里可能是别的模型名（手改的、或旧版本留下的），把它作为附加项显示出来 ——
## 否则下拉会默默把它顶成第一项，用户一保存就把自己的模型名覆盖掉了。
func _setup_model_combo(current: String) -> void:
	var items := MODEL_ITEMS.duplicate()
	if not current.is_empty() and not items.has(current):
		items.append(current)
	items.append(MODEL_CUSTOM)
	_known_models = PackedStringArray(items)
	_fill_combo(_model_combo, items)
	_select_combo(_model_combo, current if not current.is_empty() else MODEL_ITEMS[1])
	_model_custom.visible = false
	_model_custom.text = ""


func _on_model_selected(index: int) -> void:
	var is_custom := _model_combo.get_item_text(index) == MODEL_CUSTOM
	_model_custom.visible = is_custom
	if is_custom:
		_model_custom.grab_focus()


func _current_model() -> String:
	var text := _model_combo.get_item_text(_model_combo.selected)
	if text == MODEL_CUSTOM:
		return _model_custom.text.strip_edges()
	return text


func _refresh_chapter_hint() -> void:
	_chapter_pages_hint.text = "禁用" if _chapter_pages_spin.value <= 0.0 else ""


# ================================================================ 动作
func _on_save() -> void:
	if _loading:
		return
	var model := _current_model()
	if model.is_empty():
		_set_status("模型名不能为空", DsProto.STATUS_ERROR)
		return

	# 先存 Key（单独一条命令：后端把它 DPAPI 加密后落盘，明文不回传）
	var key := _key_edit.text.strip_edges()
	if not key.is_empty():
		NetClient.send_command(DsProto.CMD_CONFIG_SET_API_KEY, {"key": key})

	NetClient.send_command(DsProto.CMD_CONFIG_SET, {"config": {
		"api": {
			"model": model,
			"reasoning_effort": _effort_combo.get_item_text(_effort_combo.selected),
			"use_thinking": _thinking_check.button_pressed,
		},
		"parser": {
			"backend": _backend_combo.get_item_text(_backend_combo.selected),
			"effort": _parser_effort_combo.get_item_text(_parser_effort_combo.selected),
			"timeout": int(_timeout_spin.value),
		},
		"parallel": {
			"max_workers": int(_workers_spin.value),
			"max_mineru": int(_mineru_spin.value),
			"max_chapter_pages": int(_chapter_pages_spin.value),
		},
		"translation": {
			"max_tokens": int(_max_tokens_spin.value),
			"temperature": float(_temp_spin.value),
			"target_tokens_per_call": int(_target_tokens_spin.value),
			"max_paras_per_call": int(_max_paras_spin.value),
			"min_marker_retention": float(_marker_spin.value),
			"enable_integrity": _integrity_check.button_pressed,
		},
	}})
	_set_status("配置已保存", DsProto.STATUS_DONE)


func _on_restore() -> void:
	var dlg := ConfirmationDialog.new()
	dlg.title = "恢复默认设置"
	dlg.dialog_text = "将放弃当前所有配置，恢复为 config.py 里的默认值。\n\n确定要继续吗？"
	dlg.ok_button_text = "恢复默认"
	dlg.cancel_button_text = "取消"
	dlg.confirmed.connect(func():
		NetClient.send_command(DsProto.CMD_CONFIG_RESTORE, {})
		_set_status("已恢复默认配置", DsProto.STATUS_DONE))
	# 两个出口都释放，避免反复点「恢复默认」在场景树里堆对话框
	dlg.confirmed.connect(dlg.queue_free)
	dlg.canceled.connect(dlg.queue_free)
	add_child(dlg)
	dlg.popup_centered()


## 状态行的语义色走主题变体（StatusOk/StatusWarn/…），不要 per-control 覆盖颜色。
func _set_status(text: String, status: String) -> void:
	_status.text = text
	match status:
		DsProto.STATUS_DONE:
			_status.theme_type_variation = "StatusOk"
		DsProto.STATUS_ERROR:
			_status.theme_type_variation = "StatusError"
		DsProto.STATUS_PARTIAL, DsProto.STATUS_TRANSLATING:
			_status.theme_type_variation = "StatusWarn"
		_:
			_status.theme_type_variation = "StatusIdle"
