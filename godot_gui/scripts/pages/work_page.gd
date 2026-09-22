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

## 日志最多保留多少行，超出后一次裁掉多少（避免每加一行就重建整段 BBCode）。
const LOG_MAX_LINES := 2000
const LOG_TRIM_LINES := 500

var _table: TreeTable
var _log: RichTextLabel
var _drop: FileDropZone
var _summary: Label
var _review: Label

var _btn_start_all: Button
var _btn_stop_all: Button
var _btn_clear_all: Button
var _chk_force: CheckBox
var _chk_parallel: CheckBox
var _chk_parse_only: CheckBox
var _chk_warnings: CheckBox
var _chk_chapters: CheckBox

## path -> {item: TreeTableItem, status: String, running: bool, parts: Dictionary}
var _files: Dictionary = {}
## 日志条目（与 RichTextLabel 内容同步），裁剪时用它重建
var _log_entries: Array = []
## 「并行翻译」的初值是否已从后端配置取回（只取一次，之后尊重用户的手动勾选）
var _parallel_initialized := false


func _init() -> void:
	# 页面在 _init 里建好（与模板里复合控件的约定一致），new() 之后即可用
	_build_ui()


func _ready() -> void:
	NetClient.data_received.connect(_on_backend_message)
	# 页面是在 app.gd 的 _ready 里建的，那一刻 WebSocket 还没连上（连接是异步的，
	# 而且后端可能是刚被拉起来的）—— 直接发命令会被 NetClient 丢弃。
	# 所以「连上之后再请求」：connected 每次重连都会再发一次，正好覆盖后端重启。
	NetClient.connected.connect(_request_parallel_default)
	_refresh_buttons()
	_request_parallel_default()


## 「并行翻译」的默认值由后端给（config.py 是唯一默认值源），前端不硬编码。
func _request_parallel_default() -> void:
	if _parallel_initialized or not NetClient.is_open():
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
		PackedFloat32Array([280.0, 100.0, 178.0]))
	# 宽度给够：操作列是最后一列（自动填满剩余宽度），三个按钮约需 140px。
	# 高度不用管，TreeTable 自己按行数上报（别去写 custom_minimum_size.y）。
	_table.set_min_width(580.0)
	_table.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_table.cell_action_pressed.connect(_on_row_action)
	scroll.add_child(_table)

	# ---- 工具栏第一行：批量操作 ----
	_btn_start_all = _make_button("全部开始", "AccentButton", _on_start_all)
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

	var log_panel := PanelContainer.new()
	log_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	log_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	log_panel.size_flags_stretch_ratio = 2.0
	root.add_child(log_panel)

	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_following = true          # 自动跟到最新一行
	_log.selection_enabled = true         # 允许选中复制日志（排查时很需要）
	_log.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	log_panel.add_child(_log)


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

	NetClient.send_command(DsProto.CMD_JOB_START, {
		"path": path,
		"force": _chk_force.button_pressed,
		"parse_only": _chk_parse_only.button_pressed,
		"parallel": _chk_parallel.button_pressed,
		"output_warnings": _chk_warnings.button_pressed,
		"output_chapters": _chk_chapters.button_pressed,
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
			_init_parallel_default(msg)
		DsProto.MSG_ERROR:
			_append_log("system", "ERROR", str(msg.get("message", "")))


## 用后端配置里的 parallel.enable 作「并行翻译」的初值。
## 只认第一次回包：配置页保存后后端也会推一份 config_data，那时不该把用户
## 在工作页上的手动勾选顶掉。
func _init_parallel_default(msg: Dictionary) -> void:
	if _parallel_initialized:
		return
	_parallel_initialized = true
	var parallel: Dictionary = msg.get("config", {}).get("parallel", {})
	_chk_parallel.button_pressed = bool(parallel.get("enable", true))


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
	if name.is_empty():
		_log.append_text("[color=#%s]%s[/color]\n" % [
			DsProto.level_color(level).to_html(false), _esc(line)])
	else:
		_log.append_text("[color=#%s][b]%s[/b][/color] [color=#%s]%s[/color]\n" % [
			ThemePalette.ACCENT.to_html(false), _esc(name),
			DsProto.level_color(level).to_html(false), _esc(line)])
	_log_entries.append([name, level, line])
	if _log_entries.size() > LOG_MAX_LINES:
		_log_entries = _log_entries.slice(LOG_TRIM_LINES)
		_rebuild_log()


func _rebuild_log() -> void:
	_log.clear()
	for entry in _log_entries:
		var name: String = entry[0]
		var color := DsProto.level_color(entry[1]).to_html(false)
		if name.is_empty():
			_log.append_text("[color=#%s]%s[/color]\n" % [color, _esc(entry[2])])
		else:
			_log.append_text("[color=#%s][b]%s[/b][/color] [color=#%s]%s[/color]\n" % [
				ThemePalette.ACCENT.to_html(false), _esc(name), color, _esc(entry[2])])


func _clear_log() -> void:
	_log.clear()
	_log_entries.clear()


## 供外壳（app.gd）把后端层面的错误写进日志面板 —— 状态条只有一行，
## 完整原因放这里才能选中复制。
func append_external_log(level: String, text: String) -> void:
	_append_log("system", level, text)


## RichTextLabel 的 BBCode 里 `[` 是标签开头 —— 流水线日志含大量 `[BLK:0]`、
## `[章节名]`，不转义会把后面的内容整段吃掉。
func _esc(s: String) -> String:
	return s.replace("[", "[lb]")


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
