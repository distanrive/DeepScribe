extends Control
## DeepScribe 主界面外壳：左侧导航 + 右侧页面栈 + 底部状态条。
##
## 这里只做「壳」该做的事：建页面、切页面、显示后端连接状态。
## 业务逻辑全在 `scripts/pages/*.gd`，配置读写全在 Python 后端。

const NAV_ITEMS := [
	{"key": "work", "text": "工作"},
	{"key": "config", "text": "配置"},
	{"key": "about", "text": "关于"},
]

const VERSION_FALLBACK := "v0.0.0"
const WINDOW_TITLE := "DeepScribe — PDF 学术翻译"

var _stack: StackedContainer
var _nav_buttons: Dictionary = {}      # key -> Button
var _pages: Dictionary = {}            # key -> Control
var _backend_label: Label
var _retry_button: Button


func _ready() -> void:
	_build_ui()

	BackendLauncher.status_changed.connect(_on_backend_status)
	BackendLauncher.launch_failed.connect(_on_backend_failed)
	NetClient.connected.connect(_on_connected)
	NetClient.disconnected.connect(_on_disconnected)

	# 表达「我要连后端」的意图 —— BackendLauncher 据此决定是否自动拉起
	NetClient.connect_to()
	_show_page("work")
	_refresh_backend_label(BackendLauncher.status_text(), BackendLauncher.status_level())

	# 窗口标题交给 AppShell —— 「等一帧 + 用 DisplayServer」两步都在它里面，
	# 自己写 `Window.title` 会被引擎把 " (DEBUG)" 后缀加回去。
	# 放最后：它是协程（内部 await 一帧），别把上面的初始化拖到下一帧。
	await AppShell.set_window_title(WINDOW_TITLE)


func _build_ui() -> void:
	var root := HBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 0)
	add_child(root)

	root.add_child(_build_sidebar())

	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 0)
	root.add_child(right)

	# 页面栈在 _ready 里一次性建好（不是切到才建）：工作页要持续接收后端的
	# 进度与日志消息，晚建一会儿就会漏掉前面的事件。
	_stack = StackedContainer.new()
	_stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_stack.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(_stack)

	var only := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--only="):
			only = a.substr("--only=".length())
	var work := WorkPage.new()
	var config := ConfigPage.new()
	var about := AboutPage.new()
	if only.is_empty() or only == "work":
		_pages["work"] = work
	if only.is_empty() or only == "config":
		_pages["config"] = config
	if only.is_empty() or only == "about":
		_pages["about"] = about
	for key in ["work", "config", "about"]:
		if _pages.has(key):
			_stack.add_page(_pages[key])

	right.add_child(_build_status_bar())


func _build_sidebar() -> PanelContainer:
	var panel := PanelContainer.new()
	panel.theme_type_variation = "SidebarPanel"
	panel.custom_minimum_size.x = ThemePalette.NAV_W

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", ThemePalette.NAV_SEP)
	panel.add_child(box)

	var brand := Label.new()
	brand.text = "DeepScribe"
	brand.theme_type_variation = "SectionTitle"
	brand.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(brand)

	var sub := Label.new()
	sub.text = "PDF 学术翻译"
	sub.theme_type_variation = "Caption"
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(sub)

	box.add_child(HSeparator.new())

	# 导航项：toggle_mode + ButtonGroup，靠「按下态」表达当前在哪一页
	var group := ButtonGroup.new()
	for item in NAV_ITEMS:
		var b := Button.new()
		b.text = str(item["text"])
		b.theme_type_variation = "NavButton"
		b.toggle_mode = true
		b.button_group = group
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.custom_minimum_size.y = 38
		b.focus_mode = Control.FOCUS_NONE      # 导航项不需要焦点框
		b.pressed.connect(_show_page.bind(str(item["key"])))
		_nav_buttons[item["key"]] = b
		box.add_child(b)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(spacer)

	box.add_child(HSeparator.new())

	# 界面缩放：模板的 AppShell 负责生效与记忆，这里只放一个选择器
	var scale_label := Label.new()
	scale_label.text = "界面缩放"
	scale_label.theme_type_variation = "Caption"
	box.add_child(scale_label)
	box.add_child(UiScaleOption.new())

	var ver := Label.new()
	ver.text = _read_version()
	ver.theme_type_variation = "Caption"
	ver.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(ver)

	return panel


func _build_status_bar() -> PanelContainer:
	var panel := PanelContainer.new()
	# 状态条必须**恒为一行**：后端启动失败时 BackendLauncher 会把日志尾部一起塞进
	# reason（十几行），不掐住的话状态条会长到几百像素，把整列内容顶出窗口 ——
	# 表现出来是「侧边栏底部的缩放选择器和版本号不见了」。完整原因走日志面板 + tooltip。
	panel.custom_minimum_size.y = 30.0
	panel.clip_contents = true

	var box := HBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	panel.add_child(box)

	var caption := Label.new()
	caption.text = "后端"
	caption.theme_type_variation = "Caption"
	box.add_child(caption)

	_backend_label = Label.new()
	_backend_label.theme_type_variation = "StatusIdle"
	_backend_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_backend_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_backend_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	_backend_label.clip_text = true
	_backend_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	box.add_child(_backend_label)

	# 自动拉起失败时的手动重试入口（BackendLauncher 有重试上限，不会无限重拉）
	_retry_button = Button.new()
	_retry_button.text = "启动后端"
	_retry_button.theme_type_variation = "GhostButton"
	_retry_button.visible = false
	_retry_button.pressed.connect(func(): BackendLauncher.ensure_running(true))
	box.add_child(_retry_button)

	return panel


# ================================================================ 页面切换
func _show_page(key: String) -> void:
	if not _pages.has(key):
		return
	_stack.set_page_index(["work", "config", "about"].find(key))
	var button: Button = _nav_buttons[key]
	if not button.button_pressed:
		button.button_pressed = true     # 手动同步（点击本身已由 ButtonGroup 处理）


# ================================================================ 后端状态
func _on_backend_status(text: String, level: String) -> void:
	_refresh_backend_label(text, level)
	_retry_button.visible = level == "error"


func _on_backend_failed(reason: String) -> void:
	# reason 里带着后端日志尾部（多行）。状态条只放**第一行**，完整内容塞 tooltip，
	# 同时写进日志面板 —— 那里能选中复制，排查时比一行提示有用得多。
	var full := reason.strip_edges()
	var first_line := full.split("\n")[0].strip_edges()
	_refresh_backend_label("后端启动失败：%s" % first_line, "error")
	_backend_label.tooltip_text = full
	if _pages.has("work"):
		_pages["work"].append_external_log("ERROR", "后端启动失败：%s" % full)


func _on_connected() -> void:
	# 连上后立刻握手：后端用 hello_ack 确认「这个端口上跑的确实是我们的后端」
	NetClient.send_json({"type": "hello"})


func _on_disconnected() -> void:
	_refresh_backend_label("与后端断开，正在重连…", "warn")


func _refresh_backend_label(text: String, level: String) -> void:
	_backend_label.text = text
	match level:
		"ok":
			_backend_label.theme_type_variation = "StatusOk"
		"warn":
			_backend_label.theme_type_variation = "StatusWarn"
		"error":
			_backend_label.theme_type_variation = "StatusError"
		_:
			_backend_label.theme_type_variation = "StatusIdle"


func _read_version() -> String:
	var text := FileAccess.get_file_as_string(
			ProjectSettings.globalize_path("res://").path_join("../version"))
	return text.strip_edges() if not text.is_empty() else VERSION_FALLBACK


# ================================================================ 收尾
func _notification(what: int) -> void:
	# 关窗时叫停所有任务：OS.create_process 起的进程不会随本进程结束，
	# MinerU 留着就是一直占显存、还不报错。
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		if _pages.has("work"):
			_pages["work"].shutdown()
