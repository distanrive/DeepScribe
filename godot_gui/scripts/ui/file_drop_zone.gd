class_name FileDropZone
extends Control
## 多文件拖放区：拖入**一批** PDF（或文件夹）→ 发出 `files_added`。
##
## 为什么不用 `FileDropBox`：那个控件的契约是「一个路径」（拖入多个只取第一个），
## 而 DeepScribe 是批处理工具，一次加一章/一摞文献是常态。
##
## 为什么有三个入口：**Godot 的 `FileDialog` 不支持多选文件**（`file_mode` 只有
## OPEN_FILE / OPEN_FILES? 没有 —— 只有单文件与目录）。所以：
##
##   1. 拖放一批文件 / 文件夹（主路径，能一次加多个）
##   2. 「添加文件…」—— 一次一个，可重复点
##   3. 「添加文件夹…」—— 递归扫 `*.pdf`，对齐 CLI 的输入发现规则
##
## 外观（虚线圆角框）复用 `FileDropBox.round_rect_perimeter()`，配色走主题类型
## "FileDropZone"（与 FileDropBox 同一组值，见 theme_factory.gd）。

## 用户加入了一批 PDF（已去重、已按路径排序，绝对路径）。
signal files_added(paths: PackedStringArray)

@export var hint_text := "把 PDF 文件或文件夹拖到这里" :
	set(v):
		hint_text = v
		if _hint != null:
			_hint.text = v

## 只收这个后缀（大小写不敏感）。
@export var extensions := PackedStringArray([".pdf"])

var _hint: Label
var _count: Label
var _file_dialog: FileDialog
var _dir_dialog: FileDialog

var _hovered := false
var _drag_over := false
var _last_drop_msec := -100000


func _init() -> void:
	# 子节点在 _init 里构建，保证 new() 之后即可访问（与 FileDropBox/TitledGroup 一致）
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	var vb := VBoxContainer.new()
	vb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vb.add_theme_constant_override("separation", 6)
	center.add_child(vb)

	_hint = Label.new()
	_hint.text = hint_text
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hint.theme_type_variation = "DropHint"
	vb.add_child(_hint)

	var row := CenterContainer.new()
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vb.add_child(row)

	var buttons := HBoxContainer.new()
	buttons.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(buttons)

	var add_files := Button.new()
	add_files.text = "添加文件…"
	add_files.theme_type_variation = "AccentButton"
	add_files.tooltip_text = "选择一个 PDF（可重复点击继续添加；批量请直接用拖放）"
	add_files.pressed.connect(_pick_files)
	buttons.add_child(add_files)

	var add_dir := Button.new()
	add_dir.text = "添加文件夹…"
	add_dir.theme_type_variation = "Button"
	add_dir.tooltip_text = "把文件夹里（含子目录）的所有 PDF 一次加入"
	add_dir.pressed.connect(_pick_dir)
	buttons.add_child(add_dir)

	_count = Label.new()
	_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_count.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_count.theme_type_variation = "Caption"
	vb.add_child(_count)


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	custom_minimum_size.y = maxf(custom_minimum_size.y, ThemePalette.DROPBOX_MIN_H)
	resized.connect(queue_redraw)
	mouse_entered.connect(func(): _set_hovered(true))
	mouse_exited.connect(func(): _set_hovered(false))
	tooltip_text = "拖入 PDF 文件或文件夹"
	_refresh()

	# 兜底通道：部分平台/嵌入窗口下系统拖放只发 Window.files_dropped（不带落点），
	# 鼠标正好在本框内时接住，保证拖放一定可用（GUI 通道已处理时按时间戳去重）。
	var win := get_window()
	if win != null and not win.files_dropped.is_connected(_on_window_files_dropped):
		win.files_dropped.connect(_on_window_files_dropped)


# ---------------------------------------------------------------- 对外接口

## 把一批路径（文件或目录）展开成 PDF 列表并广播。返回新增的文件数。
func add_paths(paths: PackedStringArray) -> int:
	var found := PackedStringArray()
	for p in paths:
		_collect_from(p, found)

	# 去重 + 排序：拖入文件夹时 DirAccess 的枚举顺序不保证，先定下来
	var seen := {}
	var unique := PackedStringArray()
	for f in found:
		if not seen.has(f):
			seen[f] = true
			unique.append(f)
	unique.sort()
	if unique.is_empty():
		_refresh("没有找到 PDF 文件")
		return 0
	_refresh()
	files_added.emit(unique)
	return unique.size()


## 只把后缀符合的文件收进来（供外部判断用）。
func accepts(path: String) -> bool:
	var ext := path.get_extension().to_lower()
	return ("." + ext) in extensions


# ---------------------------------------------------------------- 选择文件

func _pick_files() -> void:
	if _file_dialog == null:
		_file_dialog = _make_dialog("选择 PDF 文件", FileDialog.FILE_MODE_OPEN_FILE)
		_file_dialog.file_selected.connect(func(p: String): add_paths([p]))
	_file_dialog.popup_centered_ratio(0.55)


func _pick_dir() -> void:
	if _dir_dialog == null:
		_dir_dialog = _make_dialog("选择包含 PDF 的文件夹", FileDialog.FILE_MODE_OPEN_DIR)
		# 原生目录选择器在 Windows 上会发 dir_selected；Godot 内置对话框两者都可能发，
		# 一起接住并去重，省得挑平台。
		_dir_dialog.dir_selected.connect(func(p: String): add_paths([p]))
		_dir_dialog.file_selected.connect(func(p: String): add_paths([p]))
	_dir_dialog.popup_centered_ratio(0.55)


func _make_dialog(title: String, mode: int) -> FileDialog:
	var d := FileDialog.new()
	d.access = FileDialog.ACCESS_FILESYSTEM
	d.file_mode = mode              # 默认是 SAVE_FILE，必须显式改
	d.title = title
	d.use_native_dialog = true
	d.filters = PackedStringArray(["*.pdf ; PDF 文件", "* ; 所有文件"])
	add_child(d)
	return d


# ---------------------------------------------------------------- 拖放

func _notification(what: int) -> void:
	if what == NOTIFICATION_DRAG_END:
		_set_drag_over(false)


func _can_drop_data(at_position: Vector2, data: Variant) -> bool:
	var ok := not FileDropBox.extract_files(data).is_empty()
	_set_drag_over(ok and Rect2(Vector2.ZERO, size).has_point(at_position))
	return ok


func _drop_data(_at_position: Vector2, data: Variant) -> void:
	_set_drag_over(false)
	var files := FileDropBox.extract_files(data)
	if files.is_empty():
		return
	_last_drop_msec = Time.get_ticks_msec()
	add_paths(files)


func _on_window_files_dropped(files: PackedStringArray) -> void:
	if Time.get_ticks_msec() - _last_drop_msec < 300:
		return   # GUI 拖放通道已经处理过，避免同一份文件被加两次
	if not get_global_rect().has_point(get_global_mouse_position()):
		return   # 界面上有多个拖放框时，只接住鼠标所在的那一个
	_last_drop_msec = Time.get_ticks_msec()
	add_paths(files)


# ---------------------------------------------------------------- 内部

## 把 `path` 展开成 PDF 路径追加到 `out`：文件按后缀筛，目录递归找。
func _collect_from(path: String, out: PackedStringArray) -> void:
	if path.is_empty():
		return
	if DirAccess.dir_exists_absolute(path):
		_scan_dir(path, out)
	elif FileAccess.file_exists(path):
		if accepts(path):
			out.append(path)


func _scan_dir(dir_path: String, out: PackedStringArray) -> void:
	var d := DirAccess.open(dir_path)
	if d == null:
		return
	d.list_dir_begin()
	var name := d.get_next()
	while name != "":
		if d.current_is_dir():
			if not name.begins_with("."):     # 跳过隐藏目录（含 .git 之类）
				_scan_dir(dir_path.path_join(name), out)
		elif accepts(name):
			out.append(dir_path.path_join(name))
		name = d.get_next()
	d.list_dir_end()


func _set_hovered(v: bool) -> void:
	if _hovered == v:
		return
	_hovered = v
	queue_redraw()


func _set_drag_over(v: bool) -> void:
	if _drag_over == v:
		return
	_drag_over = v
	queue_redraw()


func _refresh(message := "") -> void:
	if _count == null:
		return
	_count.text = message


# ---------------------------------------------------------------- 绘制

func _theme_color(name: StringName, fallback: Color) -> Color:
	var t := &"FileDropZone"
	return get_theme_color(name, t) if has_theme_color(name, t) else fallback


func _draw() -> void:
	var bg := _theme_color(&"bg_color", ThemePalette.SURFACE)
	var border := _theme_color(&"border_color", ThemePalette.BORDER_STRONG)
	if _drag_over:
		bg = _theme_color(&"bg_drop_color", ThemePalette.ACCENT_SOFT_HOVER)
		border = _theme_color(&"border_drop_color", ThemePalette.ACCENT)
	elif _hovered:
		bg = _theme_color(&"bg_hover_color", ThemePalette.SURFACE_ALT)
		border = _theme_color(&"border_hover_color", ThemePalette.ACCENT)

	# 半像素内缩，避免描边被控件边界裁掉一半
	var rect := Rect2(Vector2.ONE * ThemePalette.DROPBOX_BORDER_W * 0.5,
			size - Vector2.ONE * ThemePalette.DROPBOX_BORDER_W)
	var radius := float(ThemePalette.RADIUS_LG)

	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.set_corner_radius_all(radius)
	draw_style_box(sb, rect)

	# 虚线圆角矩形：复用 FileDropBox 的周长采样（同一套虚线段长/间隙令牌）
	var pts := FileDropBox.round_rect_perimeter(rect, radius)
	var on := true
	var left := ThemePalette.DROPBOX_DASH
	for i in range(pts.size() - 1):
		var a := pts[i]
		var b := pts[i + 1]
		var seg := a.distance_to(b)
		if seg <= 0.0001:
			continue
		var t := 0.0
		while t < seg:
			var step := minf(left, seg - t)
			if on and step > 0.0001:
				draw_line(a.lerp(b, t / seg), a.lerp(b, (t + step) / seg),
						border, ThemePalette.DROPBOX_BORDER_W, true)
			t += step
			left -= step
			if left <= 0.0001:
				on = not on
				left = ThemePalette.DROPBOX_DASH if on else ThemePalette.DROPBOX_GAP
