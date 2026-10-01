class_name WorkPage
extends MarginContainer
## 工作页：加文件 → 起任务 → 看进度与日志。
##
## 数据流与后端（`godot_gui/backend/main.py`）严格对应：
##   job_status     改文件行状态
##   chapter_status 建/改「第 N 章」子行（仅并行模式）
##   log            追加到日志面板
##   job_finished   收尾（成功/失败/取消）并刷新按钮
##
## 父行状态是**推导**出来的，不是后端直接给的：有子行时父行只说
## 等待中 / 工作中 / 完成 / 部分失败，具体阶段只在子行显示 —— 否则父行会随
## 每一章在「解析中」「翻译中」之间反复横跳，读起来像抽风。

const COL_NAME := 0
const COL_STATUS := 1
const COL_ACTION := 2

## 右键菜单的项 id。
const MENU_FOLLOW := 0
const MENU_FORCE := 1
const MENU_PARALLEL := 2
const MENU_PARSE_ONLY := 3
const MENU_WARNINGS := 4
const MENU_CHAPTERS := 5

## 五个「逐次运行开关」在字典里的键（与 job_start 的参数名一一对应）。
const OPT_KEYS := ["force", "parallel", "parse_only", "warnings", "chapters"]

var _table: TreeTable
var _log: LogView
var _drop: FileDropZone
var _summary: Label
var _menu: PopupMenu

var _btn_start_all: Button
var _btn_stop_all: Button
var _btn_clear_all: Button
var _chk_force: CheckBox
var _chk_parallel: CheckBox
var _chk_parse_only: CheckBox
var _chk_warnings: CheckBox
var _chk_chapters: CheckBox

## path -> {item: TreeTableItem, status: String, running: bool, parts: Dictionary,
##          opts: Dictionary}
## `opts` 是**单文件覆盖**：空字典 = 跟随工具栏上的全局勾选；非空 = 这一行已由右键菜单
## 单独设定（见 `_effective_opts()`）。
var _files: Dictionary = {}
## 右键菜单当前作用在哪一行（空串 = 还没弹过）。
var _menu_path := ""
## 「并行翻译」被用户在本窗口手动动过 —— 之后不再用后端配置的默认值盖掉它。
var _parallel_user_locked := false
## 正在程序性地写勾选框（此时 `toggled` 回调不该记成「用户手动改的」）。
var _setting_checks := false


func _init() -> void:
	# 页面在 _init 里建好（与模板里复合控件的约定一致），new() 之后即可用
	_build_ui()


func _ready() -> void:
	NetClient.data_received.connect(_on_backend_message)
	# 页面是在 app.gd 的 _ready 里建的，那一刻 WebSocket 还没连上（连接是异步的，
	# 而且后端可能是刚被拉起来的）—— 直接发命令会被 NetClient 丢弃。
	# 所以「连上之后再请求」：connected 每次重连都会再发一次，正好覆盖后端重启。
	NetClient.connected.connect(_sync_config)
	_refresh_buttons()
	_refresh_chapter_enabled()
	_sync_config()


## 把「并行翻译」的默认值对齐后端配置（config.py 是唯一默认值源，前端不硬编码）。
##
## 何时调：连上后端时、以及**每次真正下发任务之前** —— 多开窗口时配置可能已被别的
## 前端改过，执行前对齐一次才不会拿旧值跑。用户在本窗口手动动过这个勾选框就不再覆盖。
func _sync_config() -> void:
	if not NetClient.is_open():
		return          # 没连上就别发：NetClient 会丢弃并打一条警告，由 connected 再触发
	NetClient.send_command(DsProto.CMD_CONFIG_GET, {})


# ================================================================ 界面
func _build_ui() -> void:
	# 页面边距由 MarginContainer 的主题默认值统一给（theme_palette.PAGE_MARGIN），
	# 这里不要加 per-control 的 margin 覆盖
	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", ThemePalette.SEP_BOX)
	add_child(root)

	# ---- 拖放区 ----
	_drop = FileDropZone.new()
	_drop.custom_minimum_size.y = 132.0
	_drop.files_added.connect(_on_files_added)
	root.add_child(_drop)

	# ---- 文件列表标题行 ----
	var head := HBoxContainer.new()
	root.add_child(head)
	var title := Label.new()
	title.text = "文件列表"
	title.theme_type_variation = "SectionTitle"
	head.add_child(title)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(spacer)
	_summary = Label.new()
	_summary.theme_type_variation = "Caption"
	head.add_child(_summary)

	# ---- 表格 ----
	# 表格与日志的高度按 3:2 分剩余空间（`size_flags_stretch_ratio` 只在
	# 该方向有 SIZE_EXPAND 时才起作用，所以两句都要写）。
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.size_flags_stretch_ratio = 3.0
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	root.add_child(scroll)

	_table = TreeTable.new()
	_table.set_columns(
		PackedStringArray(["文件名", "状态", "操作"]),
		PackedFloat32Array([0.0, 100.0, 178.0]))
	# 文件名列吸收剩余宽度（首项宽度被忽略），状态/操作保持小固定宽度 —— 否则窗口一宽，
	# 最后一列会变成几百像素的空档，而文件名反而最窄。
	# 注意：横向滚动是关掉的，表格宽度恒等于可视宽度，所以「谁吸收剩余」只能靠 flex 列。
	_table.set_flex_column(COL_NAME)
	# 「操作」列放三个按钮，需要 178px（约 140px 按钮 + 左右留白）；文件名列至少 300 才好认。
	# 高度不用管，TreeTable 自己按行数上报（别去写 custom_minimum_size.y）。
	_table.set_min_width(580.0)
	_table.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_table.cell_action_pressed.connect(_on_row_action)
	_table.item_context_menu.connect(_on_row_context_menu)
	scroll.add_child(_table)

	# 右键菜单挂在表格底下（`Window` 不参与容器排版，放哪儿都不影响布局），
	# 但**弹出坐标是全局的**，要自己换算 —— 见 `_on_row_context_menu()`。
	_menu = _build_row_menu()
	_table.add_child(_menu)

	# ---- 工具栏第一行：批量操作 ----
	# 「全部开始」用绿色（SuccessButton），与行内那个绿色的「开始」同色系
	_btn_start_all = _make_button("全部开始", "SuccessButton", _on_start_all)
	_btn_stop_all = _make_button("全部停止", "DangerButton", _on_stop_all)
	_btn_clear_all = _make_button("全部删除", "Button", _on_clear_all)
	root.add_child(_toolbar_row([_btn_start_all, _btn_stop_all, _btn_clear_all]))

	# ---- 工具栏第二行：逐次运行的开关 ----
	_chk_force = _make_check("强制重解析",
			"重新运行 MinerU 解析，忽略已缓存结果。\n切换解析后端（如 pipeline→hybrid-engine）后需勾选。")
	_chk_parallel = _make_check("并行翻译",
			"PDF 含书签时按章节并行翻译；无书签自动退回串行")
	_chk_parse_only = _make_check("仅解析",
			"只运行 MinerU 解析并输出 {文件名}_parsed.md，跳过翻译（省 API 费用）")
	_chk_warnings = _make_check("输出warning",
			"输出 {文件名}_warnings.md（标题修正 / 完整性校验的告警清单）")
	_chk_warnings.button_pressed = true
	_chk_chapters = _make_check("分章输出",
			"并行模式下额外把每一章写成 output/part/{序号}_{标题}.md")
	_chk_chapters.button_pressed = true
	# 「分章输出」只在并行模式下有意义：串行模式没有分章概念，勾了也不生效
	_chk_parallel.toggled.connect(_on_parallel_toggled)
	root.add_child(_toolbar_row([
		_chk_force, _chk_parallel, _chk_parse_only, _chk_warnings, _chk_chapters,
	]))

	# ---- 日志 ----
	var log_head := HBoxContainer.new()
	root.add_child(log_head)
	var log_title := Label.new()
	log_title.text = "日志"
	log_title.theme_type_variation = "SectionTitle"
	log_head.add_child(log_title)
	var log_spacer := Control.new()
	log_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	log_head.add_child(log_spacer)
	# 日志行数不多但很想知道「有没有东西在动」，给个清空入口
	var btn_clear_log := Button.new()
	btn_clear_log.text = "清空日志"
	btn_clear_log.theme_type_variation = "GhostButton"
	btn_clear_log.pressed.connect(_clear_log)
	log_head.add_child(btn_clear_log)

	# 滚动日志控件（模板的 LogView：级别配色 + 行数上限 + 贴底才跟随 + 可选中复制）。
	# 它自己就是 PanelContainer，不用再套一层。
	_log = LogView.new()
	_log.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_log.size_flags_stretch_ratio = 2.0
	_log.custom_minimum_size.y = ThemePalette.LOG_MIN_H
	_log.show_timestamp = false           # 保持本项目一贯的「文件名 + 正文」格式
	_log.follow = true                    # 自动跟到最新一行
	root.add_child(_log)


func _make_button(text: String, variation: String, handler: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = variation
	b.custom_minimum_size = Vector2(120, 34)
	b.pressed.connect(handler)
	return b


func _make_check(text: String, tip: String) -> CheckBox:
	var c := CheckBox.new()
	c.text = text
	c.tooltip_text = tip
	return c


## 一行居中的水平工具栏（按钮行与勾选行都走它，保证两行间距与居中方式一致）。
func _toolbar_row(children: Array) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 14)
	for c in children:
		row.add_child(c)
	return row


## 单文件右键菜单：改这一行自己的逐次运行开关。
##
## 勾选态显示的是**当前生效值**（没覆盖时就是工具栏全局值），用户翻任何一项就把五项一起
## 快照成这一行的独立设置；选「跟随全局设置」再退回跟随。
func _build_row_menu() -> PopupMenu:
	var menu := PopupMenu.new()
	menu.add_check_item("跟随全局设置", MENU_FOLLOW)
	menu.set_item_tooltip(0, "清除本文件的单独设置，重新跟随工具栏上的勾选")
	menu.add_separator()
	menu.add_check_item("强制重解析", MENU_FORCE)
	menu.add_check_item("并行翻译", MENU_PARALLEL)
	menu.add_check_item("仅解析", MENU_PARSE_ONLY)
	menu.add_check_item("输出warning", MENU_WARNINGS)
	menu.add_check_item("分章输出", MENU_CHAPTERS)
	# 勾选态与置灰状态每次弹出前重算（见 _refresh_row_menu）——数据变了，菜单不会自己跟着走
	menu.about_to_popup.connect(_refresh_row_menu)
	menu.id_pressed.connect(_on_menu_pressed)
	return menu


func _on_parallel_toggled(_pressed: bool) -> void:
	if not _setting_checks:
		# 用户在本窗口手动动过 —— 之后后端配置的默认值不再盖掉它（见 _sync_config）
		_parallel_user_locked = true
	_refresh_chapter_enabled()


## 「并行翻译」没勾时「分章输出」不可选：串行模式没有分章这一步，勾了也不生效。
func _refresh_chapter_enabled() -> void:
	var parallel := _chk_parallel.button_pressed
	_chk_chapters.disabled = not parallel
	_chk_chapters.tooltip_text = ("并行模式下额外把每一章写成 output/part/{序号}_{标题}.md"
			if parallel else "需先勾选「并行翻译」——串行模式没有分章这一步")


# ================================================================ 单文件选项
## 这一行实际会用的五个开关：有单文件覆盖就用它，否则用工具栏上的全局勾选。
func _effective_opts(path: String) -> Dictionary:
	var info: Dictionary = _files.get(path, {})
	var override: Dictionary = info.get("opts", {})
	var out := {}
	for key in OPT_KEYS:
		out[key] = bool(override[key]) if override.has(key) else _global_opt(key)
	return out


func _global_opt(key: String) -> bool:
	match key:
		"force":
			return _chk_force.button_pressed
		"parallel":
			return _chk_parallel.button_pressed
		"parse_only":
			return _chk_parse_only.button_pressed
		"warnings":
			return _chk_warnings.button_pressed
		_:
			return _chk_chapters.button_pressed


func _on_row_context_menu(item: TreeTableItem, at_position: Vector2) -> void:
	if typeof(item.get_metadata()) != TYPE_STRING:
		return          # 章节子行没有单文件选项
	var path := str(item.get_metadata())
	var info: Dictionary = _files.get(path, {})
	if info.is_empty() or info["running"]:
		# 运行中的文件不给改：改了也来不及生效，只是让用户以为生效了
		return
	_menu_path = path
	# **坐标必须是全局的**：`popup_on_parent()` 在嵌入子窗口模式下等价于 `popup()`，
	# 而 `popup()` 的 rect 是「相对主窗口左上角」的全局坐标（Godot 文档原话：
	# "rect must be in global coordinates"）。只传表内坐标的话，菜单会整体
	# 少掉表格自身的全局偏移 —— 表现为「弹出位置跑到鼠标左边一大截」（踩过）。
	# 表格的输入事件坐标是控件局部的，所以要加上表格的全局位置。
	_menu.popup_on_parent(Rect2(_table.get_global_position() + at_position, Vector2.ZERO))


func _refresh_row_menu() -> void:
	var info: Dictionary = _files.get(_menu_path, {})
	if info.is_empty():
		return
	var opts := _effective_opts(_menu_path)
	_menu.set_item_checked(_menu.get_item_index(MENU_FOLLOW), info.get("opts", {}).is_empty())
	_menu.set_item_checked(_menu.get_item_index(MENU_FORCE), bool(opts["force"]))
	_menu.set_item_checked(_menu.get_item_index(MENU_PARALLEL), bool(opts["parallel"]))
	_menu.set_item_checked(_menu.get_item_index(MENU_PARSE_ONLY), bool(opts["parse_only"]))
	_menu.set_item_checked(_menu.get_item_index(MENU_WARNINGS), bool(opts["warnings"]))
	var chapters := _menu.get_item_index(MENU_CHAPTERS)
	_menu.set_item_checked(chapters, bool(opts["chapters"]))
	# 「分章输出」在没有并行时无意义 —— 与工具栏上的联动规则保持一致
	_menu.set_item_disabled(chapters, not bool(opts["parallel"]))


func _on_menu_pressed(id: int) -> void:
	var info: Dictionary = _files.get(_menu_path, {})
	if info.is_empty():
		return
	if id == MENU_FOLLOW:
		info["opts"] = {}          # 退回跟随全局
		return
	var key := ""
	match id:
		MENU_FORCE:
			key = "force"
		MENU_PARALLEL:
			key = "parallel"
		MENU_PARSE_ONLY:
			key = "parse_only"
		MENU_WARNINGS:
			key = "warnings"
		MENU_CHAPTERS:
			key = "chapters"
		_:
			return
	# 第一次改任何一项：把当前生效值整体快照下来，这一行从此独立于工具栏
	var opts: Dictionary = info.get("opts", {})
	if opts.is_empty():
		opts = _effective_opts(_menu_path)
	opts[key] = not bool(opts[key])
	info["opts"] = opts


# ================================================================ 文件行
func _on_files_added(paths: PackedStringArray) -> void:
	var added := 0
	for path in paths:
		if _files.has(path):
			continue
		_create_file_row(path)
		added += 1
		_append_log("system", "INFO", "已添加: %s" % path.get_file())
	if added > 0:
		_table.set_all_expanded(true)
	_refresh_buttons()
	_refresh_summary()


func _create_file_row(path: String) -> void:
	var item := _table.create_item()
	item.set_cells(PackedStringArray([path.get_file(), DsProto.status_text(DsProto.STATUS_QUEUED), ""]))
	item.set_metadata(path)
	# 文件名列只显示 basename，悬停给完整路径（表宽有限，长路径会被截断）
	item.set_cell_tooltip(COL_NAME, path)
	_files[path] = {
		"item": item,
		"status": DsProto.STATUS_QUEUED,
		"running": false,
		"parts": {},
		"opts": {},          # 空 = 跟随工具栏上的全局勾选（右键菜单可单独设定）
	}
	_set_row_actions(path)


## 行内按钮配置。**每次状态变化都要重配** —— 按钮只认 uid，不会跟着行数据走。
func _set_row_actions(path: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty():
		return
	var running: bool = info["running"]
	_table.set_item_actions(info["item"], COL_ACTION, [
		{"text": "开始", "action": "start", "variation": "CellSuccessButton",
			"disabled": running, "tooltip": "开始处理这个 PDF"},
		{"text": "停止", "action": "stop", "variation": "CellDangerButton",
			"disabled": not running, "tooltip": "终止这个文件的流水线（连同 MinerU 子进程）"},
		{"text": "删除", "action": "remove", "variation": "CellButton",
			"tooltip": "从列表里移除（运行中会先停止）"},
	])


func _set_status(path: String, status: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty():
		return
	info["status"] = status
	var item: TreeTableItem = info["item"]
	item.set_text(COL_STATUS, DsProto.status_text(status))
	item.set_cell_color(COL_STATUS, DsProto.status_color(status))
	_refresh_summary()


func _on_row_action(uid: int, _index: int, action: String) -> void:
	var item := _table.get_item_by_uid(uid)
	if item == null or typeof(item.get_metadata()) != TYPE_STRING:
		return          # 章节子行没有行内按钮（metadata 是章节序号，不是路径）
	var path := str(item.get_metadata())
	if path.is_empty():
		return
	match action:
		"start":
			_sync_config()          # 执行前对齐一次配置（见 _sync_config）
			_start_file(path)
		"stop":
			_stop_file(path)
		"remove":
			_remove_file(path)


# ================================================================ 起停
func _start_file(path: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty() or info["running"]:
		return
	info["running"] = true
	info["parts"] = {}
	# 上次跑剩的章节子行要清掉，否则新一轮会在旧行上改状态
	for child in info["item"].get_children():
		child.remove()
	_set_status(path, DsProto.STATUS_QUEUED)
	_set_row_actions(path)

	var opts := _effective_opts(path)
	NetClient.send_command(DsProto.CMD_JOB_START, {
		"path": path,
		"force": opts["force"],
		"parse_only": opts["parse_only"],
		"parallel": opts["parallel"],
		"output_warnings": opts["warnings"],
		"output_chapters": opts["chapters"],
	})
	_refresh_buttons()


func _stop_file(path: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty() or not info["running"]:
		return
	NetClient.send_command(DsProto.CMD_JOB_STOP, {"path": path})
	_append_log(path, "INFO", "已请求停止")


func _remove_file(path: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty():
		return
	if info["running"]:
		NetClient.send_command(DsProto.CMD_JOB_STOP, {"path": path})
	info["item"].remove()
	_files.erase(path)
	_refresh_buttons()
	_refresh_summary()


func _on_start_all() -> void:
	_sync_config()          # 执行前对齐一次配置（见 _sync_config）—— 整批只发一次
	for path in _files.keys():
		if not _files[path]["running"]:
			_start_file(path)


func _on_stop_all() -> void:
	NetClient.send_command(DsProto.CMD_JOB_STOP_ALL, {})
	for path in _files.keys():
		if _files[path]["running"]:
			_set_status(path, DsProto.STATUS_CANCELLED)
	_append_log("system", "INFO", "已请求停止全部任务")


func _on_clear_all() -> void:
	NetClient.send_command(DsProto.CMD_JOB_STOP_ALL, {})
	for path in _files.keys():
		_files[path]["item"].remove()
	_files.clear()
	_clear_log()
	_refresh_buttons()
	_refresh_summary()


## 应用退出时叫停所有任务（由 app.gd 调）——不然 MinerU 会变成孤儿进程继续吃 GPU。
func shutdown() -> void:
	if _files.is_empty():
		return
	NetClient.send_command(DsProto.CMD_JOB_STOP_ALL, {})


# ================================================================ 后端事件
func _on_backend_message(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var msg: Dictionary = payload
	match str(msg.get("type", "")):
		DsProto.MSG_JOB_STATUS:
			_on_job_status(str(msg.get("path", "")), str(msg.get("status", "")))
		DsProto.MSG_CHAPTER_STATUS:
			_on_chapter_status(
				str(msg.get("path", "")), int(msg.get("order", -1)),
				str(msg.get("status", "")), str(msg.get("title", "")))
		DsProto.MSG_LOG:
			_append_log(str(msg.get("path", "")), str(msg.get("level", "INFO")),
					str(msg.get("line", "")))
		DsProto.MSG_JOB_FINISHED:
			_on_job_finished(str(msg.get("path", "")), bool(msg.get("ok", false)),
					bool(msg.get("cancelled", false)))
		DsProto.MSG_CONFIG_DATA:
			_apply_config_defaults(msg)
		DsProto.MSG_ERROR:
			_append_log("system", "ERROR", str(msg.get("message", "")))


## 用后端配置里的 `parallel.enable` 对齐「并行翻译」勾选框（后端配置是唯一默认值源）。
##
## 连接时、每次执行前都会各推一份，所以多开窗口时这里是跟随最新配置的；
## 但用户在本窗口手动动过这个勾选框之后就不再覆盖（`_parallel_user_locked`）。
func _apply_config_defaults(msg: Dictionary) -> void:
	if _parallel_user_locked:
		return
	var parallel: Dictionary = msg.get("config", {}).get("parallel", {})
	_setting_checks = true
	_chk_parallel.button_pressed = bool(parallel.get("enable", true))
	_setting_checks = false
	_refresh_chapter_enabled()


func _on_job_status(path: String, status: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty() or status.is_empty():
		return
	if status == DsProto.STATUS_DONE and _has_child_error(info):
		_set_status(path, DsProto.STATUS_PARTIAL)
		return
	# 有子行时父行不泄漏具体阶段（子行才有解析中/翻译中）
	if info["item"].get_child_count() > 0 and status in [DsProto.STATUS_PARSING, DsProto.STATUS_TRANSLATING]:
		_set_status(path, DsProto.STATUS_WORKING)
		return
	_set_status(path, status)


func _on_chapter_status(path: String, order: int, status: String, title: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty():
		return
	if order < 0:
		# 串行模式的文件级阶段通知
		if not status.is_empty():
			_set_status(path, status)
		return

	var parent: TreeTableItem = info["item"]
	var child := _find_child(parent, order)
	if child == null:
		child = _table.create_item(parent)
		child.set_cells(PackedStringArray(["第 %d 章" % (order + 1), "", ""]))
		child.set_metadata(order)      # 子行的 metadata 是章节序号（父行是路径）
		parent.set_expanded(true)
	if not title.is_empty():
		child.set_text(COL_NAME, "第 %d 章: %s" % [order + 1, title])
	if status.is_empty():
		return
	child.set_text(COL_STATUS, DsProto.status_text(status))
	child.set_cell_color(COL_STATUS, DsProto.status_color(status))
	info["parts"][order] = status
	_refresh_file_phase(path)


func _find_child(parent: TreeTableItem, order: int) -> TreeTableItem:
	# 靠 metadata 里的章节序号找，**不要**去匹配「第 N 章」这个文案 ——
	# 文案会带标题，也会随改词而失效。
	for i in range(parent.get_child_count()):
		var c := parent.get_child(i)
		if typeof(c.get_metadata()) == TYPE_INT and int(c.get_metadata()) == order:
			return c
	return null


## 由各章状态推导文件行阶段：有子行时父行只用通用状态。
func _refresh_file_phase(path: String) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty():
		return
	var parts: Dictionary = info["parts"]
	if parts.is_empty():
		return
	var any_active := false
	var any_queued := false
	var any_error := false
	for status in parts.values():
		if status in [DsProto.STATUS_PARSING, DsProto.STATUS_TRANSLATING]:
			any_active = true
		elif status == DsProto.STATUS_QUEUED:
			any_queued = true
		elif status == DsProto.STATUS_ERROR:
			any_error = true
	if any_active:
		_set_status(path, DsProto.STATUS_WORKING)
	elif any_queued:
		_set_status(path, DsProto.STATUS_QUEUED)
	elif any_error:
		_set_status(path, DsProto.STATUS_PARTIAL)
	else:
		_set_status(path, DsProto.STATUS_DONE)


func _has_child_error(info: Dictionary) -> bool:
	return info["parts"].values().has(DsProto.STATUS_ERROR)


func _on_job_finished(path: String, ok: bool, cancelled: bool) -> void:
	var info: Dictionary = _files.get(path, {})
	if info.is_empty():
		return          # 已经被「删除」移出列表了
	info["running"] = false
	_set_row_actions(path)
	_refresh_buttons()
	if cancelled:
		_set_status(path, DsProto.STATUS_CANCELLED)
		_append_log(path, "INFO", "已停止")
	elif ok and _has_child_error(info):
		_set_status(path, DsProto.STATUS_PARTIAL)
		_append_log(path, "WARNING", "处理完成（部分章节失败，详见上方章节状态）")
	elif ok:
		_set_status(path, DsProto.STATUS_DONE)
		_append_log(path, "INFO", "处理成功")
	else:
		_set_status(path, DsProto.STATUS_ERROR)
		_append_log(path, "ERROR", "处理失败，详见上方日志")


# ================================================================ 日志
func _append_log(path: String, level: String, line: String) -> void:
	var name := ""
	if path != "system" and not path.is_empty():
		name = path.get_file()
	# 日志文本里的 `[`（`[BLK:0]`、`[章节名]`）由 LogView 自己转义，这里**不要再转一次**
	# —— 转两次会把 `[BLK:0]` 渲染成字面的 `[lb]BLK:0]`。
	_log.append(line, _log_level(level), name)


## 后端的 Python 日志级别 → LogView 的级别名。
##
## **必须映射**：LogView 认的是小写 `info/ok/warn/error/debug/system`，大写传进去会落到
## 默认分支，红/橙/灰全丢（而且主题里注册的 `LogView` 颜色也命中不了）。
func _log_level(level: String) -> String:
	match level.to_upper():
		"ERROR", "CRITICAL":
			return "error"
		"WARNING":
			return "warn"
		"DEBUG":
			return "debug"
		_:
			return "info"


func _clear_log() -> void:
	_log.clear()


## 供外壳（app.gd）把后端层面的错误写进日志面板 —— 状态条只有一行，
## 完整原因放这里才能选中复制。
func append_external_log(level: String, text: String) -> void:
	_append_log("system", level, text)


# ================================================================ 刷新
func _refresh_buttons() -> void:
	var total := _files.size()
	var running := 0
	var idle := 0
	for info in _files.values():
		if info["running"]:
			running += 1
		else:
			idle += 1
	_btn_start_all.disabled = idle == 0
	_btn_stop_all.disabled = running == 0
	_btn_clear_all.disabled = total == 0


func _refresh_summary() -> void:
	var counts := {}
	for info in _files.values():
		var s: String = info["status"]
		counts[s] = int(counts.get(s, 0)) + 1
	var parts := PackedStringArray()
	for key in [DsProto.STATUS_QUEUED, DsProto.STATUS_WORKING, DsProto.STATUS_PARSING,
			DsProto.STATUS_TRANSLATING, DsProto.STATUS_DONE, DsProto.STATUS_PARTIAL,
			DsProto.STATUS_ERROR, DsProto.STATUS_CANCELLED]:
		if counts.has(key):
			parts.append("%s %d" % [DsProto.status_text(key), counts[key]])
	if parts.is_empty():
		_summary.text = "还没有文件"
	else:
		_summary.text = "共 %d 个文件 · %s" % [_files.size(), " · ".join(parts)]
