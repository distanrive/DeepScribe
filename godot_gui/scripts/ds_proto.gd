class_name DsProto
extends RefCounted
## DeepScribe Godot 前端与后端之间的协议常量（对应 `godot_gui/backend/main.py`）。
##
## 页面代码一律走这里的常量，不要在业务脚本里手写字符串 —— 改协议时只改这一处，
## 漏改的地方会直接报「标识符未声明」而不是静默不生效。

# ---------- 前端 → 后端 ----------
const CMD_CONFIG_GET := "config_get"
const CMD_CONFIG_SET := "config_set"
const CMD_CONFIG_SET_API_KEY := "config_set_api_key"
const CMD_CONFIG_RESTORE := "config_restore"
const CMD_JOB_START := "job_start"
const CMD_JOB_STOP := "job_stop"
const CMD_JOB_STOP_ALL := "job_stop_all"
const CMD_ENV_PROBE := "env_probe"

# ---------- 后端 → 前端 ----------
const MSG_HELLO_ACK := "hello_ack"
const MSG_ACK := "ack"
const MSG_ERROR := "error"
const MSG_CONFIG_DATA := "config_data"
const MSG_ENV_INFO := "env_info"
const MSG_JOB_STATUS := "job_status"
const MSG_CHAPTER_STATUS := "chapter_status"
const MSG_LOG := "log"
const MSG_JOB_FINISHED := "job_finished"

# ---------- 状态 ----------
# 与 main.py 的 progress_callback 取值一一对应（只有这 5 个来自后端）：
#   queued / parsing / translating / done / error
# 另外三个是前端自己推导的：
#   working —— 文件行有章节子行时，父行不泄漏具体阶段，统一显示「工作中」
#   partial —— 有章节失败时，父行由 done 降级
#   cancelled —— 用户点了停止（后端在 job_status 里回这个值）
const STATUS_QUEUED := "queued"
const STATUS_PARSING := "parsing"
const STATUS_TRANSLATING := "translating"
const STATUS_DONE := "done"
const STATUS_ERROR := "error"
const STATUS_CANCELLED := "cancelled"
const STATUS_WORKING := "working"
const STATUS_PARTIAL := "partial"

const STATUS_TEXT := {
	STATUS_QUEUED: "等待中",
	STATUS_PARSING: "解析中",
	STATUS_TRANSLATING: "翻译中",
	STATUS_DONE: "完成",
	STATUS_ERROR: "失败",
	STATUS_CANCELLED: "已取消",
	STATUS_WORKING: "工作中",
	STATUS_PARTIAL: "部分失败",
}

## 状态 → 文字色。TreeTable 的每个单元格可以单独上色（见 set_cell_color），
## 这里给出配色；颜色值本身仍取自 ThemePalette（唯一可调来源）。
static func status_color(status: String) -> Color:
	match status:
		STATUS_DONE:
			return ThemePalette.SUCCESS
		STATUS_PARTIAL, STATUS_TRANSLATING, STATUS_PARSING:
			return ThemePalette.WARNING
		STATUS_ERROR:
			return ThemePalette.DANGER
		_:
			return ThemePalette.TEXT_SEC


static func status_text(status: String) -> String:
	return STATUS_TEXT.get(status, status)


## 终态：不会再变的状态（父行汇总与按钮可用性判断用）。
static func is_terminal(status: String) -> bool:
	return status in [STATUS_DONE, STATUS_ERROR, STATUS_CANCELLED, STATUS_PARTIAL]


## 日志级别 → 文字色（后端把子进程日志解析成 level 后发过来）。
static func level_color(level: String) -> Color:
	match level:
		"ERROR", "CRITICAL":
			return ThemePalette.DANGER
		"WARNING":
			return ThemePalette.WARNING
		"DEBUG":
			return ThemePalette.TEXT_DIS
		_:
			return ThemePalette.TEXT_SEC
