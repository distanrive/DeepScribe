class_name AboutPage
extends MarginContainer
## 关于页：项目信息、技术栈、开源协议、依赖。
##
## 版本号取自仓库根的 `version` 文件（`godot_gui/` 的上一级）—— 与 PyQt 版、
## CLI 共用同一个来源，不在这里另写一份。

const REPO_URL := "https://github.com/distanrive/DeepScribe"

const TECH_STACK := [
	"MinerU — PDF 解析与公式提取",
	"DeepSeek API — 批量翻译（[BLK:N] 标记机制）",
	"Godot 4 + GDScript — 图形界面",
	"SQLite — 断点续传缓存",
	"PyMuPDF — PDF 书签提取与拆分",
]

const FEATURES := [
	"Token 感知自适应分块，避免 API 截断",
	"[BLK:N] 标记批量翻译 + 逐段回退兜底",
	"G2 完整性校验：译文行内公式/代码损坏自动回填",
	"并行模式：按 PDF 书签拆章，解析与翻译流水线并行",
	"大章二级书签自动拆分",
	"SQLite 断点续传，中断不丢进度",
	"Windows DPAPI 加密 API Key",
]

const LICENSE_TEXT := "MIT License — 自由使用、修改、分发"

const PY_DEPS := "openai  ·  python-dotenv  ·  mineru  ·  PyMuPDF  ·  websockets"

var _env_label: Label


func _init() -> void:
	_build_ui()


func _ready() -> void:
	NetClient.data_received.connect(_on_backend_message)
	# 环境信息（实际用的解释器 / mineru 路径）由后端探，前端不猜。
	# 建页面时还没连上（连接是异步的），连上再问。
	NetClient.connected.connect(_request_env)
	_request_env()


func _request_env() -> void:
	if not NetClient.is_open():
		return          # 没连上就别发（NetClient 丢弃并告警），connected 会再触发一次
	NetClient.send_command(DsProto.CMD_ENV_PROBE, {})


func _build_ui() -> void:
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)

	var root := VBoxContainer.new()
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_theme_constant_override("separation", 10)
	scroll.add_child(root)

	var title := Label.new()
	title.text = "DeepScribe"
	title.theme_type_variation = "PageTitle"
	root.add_child(title)

	var sub := Label.new()
	sub.text = "PDF 学术论文英文 → 中文 Markdown 翻译流水线"
	sub.theme_type_variation = "Subtitle"
	root.add_child(sub)

	root.add_child(HSeparator.new())

	_add_section(root, "技术栈", TECH_STACK)
	_add_section(root, "核心特性", FEATURES)
	_add_section(root, "开源协议", [LICENSE_TEXT])

	# 项目地址
	var link_title := Label.new()
	link_title.text = "项目地址"
	link_title.theme_type_variation = "CardTitle"
	root.add_child(link_title)
	var link := Button.new()
	link.text = "github.com/distanrive/DeepScribe"
	link.theme_type_variation = "GhostButton"
	link.alignment = HORIZONTAL_ALIGNMENT_LEFT
	link.pressed.connect(func(): OS.shell_open(REPO_URL))
	root.add_child(link)

	_add_section(root, "Python 依赖", [PY_DEPS])

	# 运行环境（后端探测结果）
	var env_title := Label.new()
	env_title.text = "运行环境"
	env_title.theme_type_variation = "CardTitle"
	root.add_child(env_title)
	_env_label = Label.new()
	_env_label.theme_type_variation = "PathLabel"
	_env_label.text = "正在探测…"
	_env_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(_env_label)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(spacer)

	var ver := Label.new()
	ver.text = "DeepScribe %s  |  Godot Edition" % _read_version()
	ver.theme_type_variation = "Caption"
	ver.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	root.add_child(ver)


func _add_section(parent: VBoxContainer, heading: String, lines: Array) -> void:
	var h := Label.new()
	h.text = heading
	h.theme_type_variation = "CardTitle"
	parent.add_child(h)
	for line in lines:
		var l := Label.new()
		l.text = "· " + str(line)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		parent.add_child(l)


## 版本号读仓库根的 `version`（`res://` 是 godot_gui/，往上一级就是仓库根）。
## 导出成可执行文件后 res:// 在 pck 里、旁边没有源码树，这时回退到「可执行文件
## 旁边」再找一次，都没有就用占位版本号。
func _read_version() -> String:
	var candidates: Array[String] = [
		ProjectSettings.globalize_path("res://").path_join("../version"),
		OS.get_executable_path().get_base_dir().path_join("version"),
	]
	for path in candidates:
		var text := FileAccess.get_file_as_string(path)
		if not text.is_empty():
			return text.strip_edges()
	return "v0.0.0"


func _on_backend_message(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var msg: Dictionary = payload
	if str(msg.get("type", "")) == DsProto.MSG_ENV_INFO:
		_env_label.text = "Python：%s（%s）\nMinerU：%s（%s）" % [
			str(msg.get("python", "?")),
			"存在" if bool(msg.get("python_exists", false)) else "**未找到**",
			str(msg.get("mineru", "?")),
			"存在" if bool(msg.get("mineru_exists", false)) else "**未找到**",
		]
