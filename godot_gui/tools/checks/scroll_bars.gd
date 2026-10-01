extends SceneTree
## 滚动条 / 滚动日志（LogView）的回归检查（headless，不需要窗口、不需要后端）。
##
##   godot --headless --path . --script res://tools/checks/scroll_bars.gd
##   期望：输出 [check] PASS，退出码 0
##
## 为什么要有它：**滚动条的粗细完全由主题样式盒的最小尺寸决定**（= `content_margin`
## 左右之和），而 `_sb()` 的 pad 默认是 0。给 0 的后果是实测
## `VScrollBar.get_combined_minimum_size() == (0, 0)` —— 轨道和滑块都画不出来，
## 文档列表 / 日志 / 配置页 / 关于页的滚动条全成了贴着右缘、抓不住的细痕。
##
## 这是一条**改了主题就会悄悄复发**的缺陷：画面照样渲染、不报任何错，只有人眼能发现。
## 所以把「有没有实际宽度」钉成断言。
##
## 本文件对应上游 Godot4GUI 的 `tools/checks/scroll_bars.gd`；上游那份还查
## 「表格内建滚动（表头固定）」的四条线，本项目**没有采用**那套（文档列表仍由
## ScrollContainer 提供滚动），所以这里只保留两边共有的部分 + LogView。

var _fails := 0


func _initialize() -> void:
	# 主题要显式建一次：`--script` 跑的是自己的 SceneTree，autoload 那套不一定在。
	# （本工程实测 ThemeManager 会被加载，但这里不赌这一点。）
	if root.theme == null:
		root.theme = ThemeFactory.build()

	await _check_scrollbar_width()
	await _check_log_view()

	print("[check] %s" % ("PASS" if _fails == 0 else "FAIL（%d 项）" % _fails))
	quit(_fails)


# ---------------------------------------------------------------- 主题

func _check_scrollbar_width() -> void:
	var bar := VScrollBar.new()
	root.add_child(bar)
	await process_frame
	var w := bar.get_combined_minimum_size().x
	_ge(w, 1.0, "VScrollBar 有实际宽度（%.1fpx；0 就是那个「滚动条消失」的缺陷）" % w)
	_ge(w, ThemePalette.SCROLLBAR_W - 0.01,
			"VScrollBar 宽度不低于 SCROLLBAR_W 令牌（样式盒 content_margin 没被改回 0）")

	# 横向走的是同一套样式盒，但高度来自上下 margin，分开验一次
	var hbar := HScrollBar.new()
	root.add_child(hbar)
	await process_frame
	_ge(hbar.get_combined_minimum_size().y, ThemePalette.SCROLLBAR_W - 0.01,
			"HScrollBar 高度不低于 SCROLLBAR_W（两个方向共用同一条令牌）")
	bar.free()
	hbar.free()


# ---------------------------------------------------------------- 滚动日志

## LogView 的两条契约：**文本里的 `[` 要能被安全地当字面量显示**（流水线日志全是
## `[BLK:N]`、`[章节名]`），以及级别名必须真的命中主题里的配色。
func _check_log_view() -> void:
	var log := LogView.new()
	log.show_timestamp = false
	log.size = Vector2(600, 200)
	root.add_child(log)
	log.append("开始处理: [BLK:0] 章节[A]", "info", "a.pdf")
	log.append("出错了", "error")
	log.append("小心", "warn")
	log.append("调试", "debug")
	await process_frame

	var text := log.get_rich_text().get_parsed_text()
	_ok(text.contains("[BLK:0]"), "`[BLK:0]` 按字面显示（BBCode 转义生效）")
	_ok(not text.contains("[lb]"), "没有字面的 `[lb]`（调用方**没有**再转义一次）")
	_ok(text.contains("a.pdf"), "来源标签写进了正文")
	_eq(float(log.line_count()), 4.0, "四行都记下了")

	_ok(log.has_theme_color(&"error_color", &"LogView"),
			"主题里注册了 LogView 的级别配色（否则静默回退到硬编码值）")
	_eq(log._level_color_html("error"), ThemePalette.DANGER.to_html(false), "error → DANGER")
	_eq(log._level_color_html("warn"), ThemePalette.WARNING.to_html(false), "warn → WARNING")
	# 本项目比上游多一档 DEBUG
	_eq(log._level_color_html("debug"), ThemePalette.TEXT_DIS.to_html(false), "debug → TEXT_DIS")

	# 日志区自身也要有可抓的滚动条（用的是同一个 ScrollBar 样式盒）
	var inner := log.get_rich_text().get_v_scroll_bar()
	_ge(inner.get_combined_minimum_size().x, 1.0, "日志的滚动条也有实际宽度")
	log.free()


# ---------------------------------------------------------------- 断言工具

func _eq(got: Variant, want: Variant, what: String) -> void:
	if str(got) == str(want):
		print("  [ok]   %s" % what)
	else:
		_fails += 1
		print("  [FAIL] %s：期望 %s，实际 %s" % [what, want, got])


func _ge(got: float, want: float, what: String) -> void:
	if got >= want - 1e-4:
		print("  [ok]   %s" % what)
	else:
		_fails += 1
		print("  [FAIL] %s：期望 ≥ %s，实际 %s" % [what, want, got])


func _ok(cond: bool, what: String) -> void:
	if cond:
		print("  [ok]   %s" % what)
	else:
		_fails += 1
		print("  [FAIL] %s" % what)
