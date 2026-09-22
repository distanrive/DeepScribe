# DeepScribe — Godot 图形界面

DeepScribe 的图形界面：**Godot 4 做前端，Python 做后端**，两者用本地
WebSocket + JSON 通信。后端负责持有配置、拉起流水线子进程、转发进度与日志。

> 这是 DeepScribe 唯一的图形界面。早期那套 PyQt5 界面（仓库根的 `gui/`）
> 已于 2026-09-22 删除。

## 跑起来

```bash
# 1) 装后端依赖（只有 websockets；流水线依赖见仓库根 README）
pip install -r backend/requirements.txt

# 2) 用 Godot 4.7 打开本目录，按 F5
```

**不用手动开后端**：`BackendLauncher` 发现连不上就会按 `project.godot` 的
`[backend]` 段把它拉起来，窗口底部状态条会显示「已连接后端（本次自动拉起，pid=…）」。

> 换机器时改 `project.godot` 的 `[backend] python`（指向装了 mineru 的那个
> 解释器）和 `run_godot_gui_example.bat` 里的 Godot 路径。
> 不要改成「扫 PATH 找 python」——多版本 Python 是常态，静默挑错解释器只会让
> 后端悄无声息地起不来。

只逛控件不看业务：运行 `scenes/gallery.tscn`（模板的控件总览，开发期当参照手册用）。

## 三个页面

| 页面 | 干什么 |
|---|---|
| 工作 | 拖入 PDF / 文件夹 → 全部开始 → 看每章子行状态与实时日志 |
| 配置 | 改 API、解析、并行、高级参数（存 `config.json`，API Key 走 DPAPI 加密） |
| 关于 | 版本、技术栈、协议、运行环境（解释器与 mineru 的实际路径由后端探测） |

工具栏分两行：第一行是**批量动作**（全部开始 / 全部停止 / 全部删除），
第二行是**逐次运行的开关**（强制重解析 / 并行翻译 / 仅解析 / 输出warning / 分章输出）。
第二行的开关只影响这一次运行，覆盖 `config.json` 里的同名项，不写回配置文件。

## 目录结构

```
godot_gui/
├── project.godot                 # autoload + [backend]（python / script / probe）
├── scenes/app.tscn               # 主场景（挂 scripts/app.gd）
├── scenes/gallery.tscn           # 控件总览（开发期参照，可删）
├── scripts/
│   ├── app.gd                    # 外壳：侧边栏导航 + 页面栈 + 底部状态条
│   ├── ds_proto.gd               # 协议常量 + 状态→文案/配色（改协议只改这一处）
│   ├── pages/work_page.gd        # 工作页（文件表 + 工具栏 + 日志）
│   ├── pages/config_page.gd      # 配置页
│   ├── pages/about_page.gd       # 关于页
│   ├── ui/                       # 可复用控件（模板库 + FileDropZone）
│   ├── autoload/                 # NetClient / BackendLauncher / AppShell / ThemeManager
│   ├── theme/                    # 设计令牌 + 主题工厂（样式唯一来源）
│   └── util/                     # 数字格式化
├── themes/                       # 图标 SVG + 着色器
├── backend/
│   ├── main.py                   # WebSocket 服务：配置 + 作业管理 + 事件广播
│   └── requirements.txt
├── tools/
│   ├── ws_client.py              # 协议调试客户端（不开 Godot 也能测后端）
│   └── check_detached_stdio.py   # 脱离进程 stdio 行为的回归脚本
└── docs/gdscript-only-guide.md   # 模板附带的 GDScript 参考
```

## 协议

前端 → 后端（`{"type":"command","id":N,"cmd":"...","args":{...}}`）：

| cmd | args | 说明 |
|---|---|---|
| `config_get` | — | 取配置（**API Key 明文不回传**，只回「有没有/能不能解密」） |
| `config_set` | `{config:{api,parser,parallel,translation}}` | 按白名单写 config.json |
| `config_set_api_key` | `{key}` | 单独存 Key（DPAPI 加密） |
| `config_restore` | — | 恢复 `config.py` 里的默认值 |
| `job_start` | `{path, force, parse_only, parallel, output_warnings, output_chapters}` | 起一个作业 |
| `job_stop` / `job_stop_all` | `{path}` / — | 杀进程树（连 MinerU 一起） |
| `env_probe` | — | 探测实际用的解释器与 mineru 路径 |

后端 → 前端：

| type | 说明 |
|---|---|
| `hello_ack` | 对 `hello` 的应答（确认端口上是我们的后端） |
| `config_data` | 配置快照 |
| `job_status` | `{path, status}`，status ∈ queued/parsing/translating/done/error/cancelled |
| `chapter_status` | `{path, order, status, title}` —— 并行模式的每章进度 |
| `log` | `{path, level, line}` |
| `job_finished` | `{path, ok, code, cancelled}` |
| `ack` / `error` | 回执 / 错误 |

## 改东西时从哪下手

| 想改 | 改哪 |
|---|---|
| 配色 / 字号 / 间距 / 圆角 | `scripts/theme/theme_palette.gd`（**只改这一个文件**，全局生效） |
| 某个控件的语义样式 | `scripts/theme/theme_factory.gd` 加类型变体，**不要** per-control 打补丁 |
| 界面布局 | `scripts/pages/*.gd`（全部代码建 UI） |
| 协议字段 / 状态文案 | `scripts/ds_proto.gd` **和** `backend/main.py` 一起改 |
| 加后端命令 | `backend/main.py` 的 `Session._dispatch()` 里加一个 `elif` |

## 已知的引擎坑

- **报「引擎泄漏」之前先跑空基线**。我们在这一条上栽过：曾以为 `stretch_ratio`
  会让对象泄漏并写进了文档，其实是探测脚本用错了属性名（`Control` 上是
  `size_flags_stretch_ratio`，没有 `stretch_ratio`），那行报错让脚本中途中止，
  而 `ObjectDB instances were leaked at exit` 是 headless 收尾自带的噪声。
  判据：先跑一个什么都不建、同样帧数的脚本当基线，并确认被测脚本**跑到底**。
- 主题只在「Control 的父链全是 Control/Window」时才生效。写测试/验收脚本
  包场景时，根节点要用 `Control`，中间别夹普通 `Node`，否则控件会退回引擎默认样式。
- `OS.create_process()` 起的进程**不随 Godot 退出而结束**。`BackendLauncher`
  在 `_exit_tree` 里 `OS.kill`（先 `is_process_running` 再杀，pid 会被系统复用）。
- 后端的 stdio 可能不可用（Godot 起进程时不给有效句柄）。`backend/main.py`
  开头有一段**先于任何第三方 import** 的 stdio 自导，别把它挪到后面；
  详见该文件头部注释与 `tools/check_detached_stdio.py`。
