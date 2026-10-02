# 回给 Godot4GUI 模板的问题报告

本文记录在 DeepScribe 上用模板控件库时发现的问题与建议。

- **第一批（2026-09-22）**：4 条，**已全部回搬到模板**。保留作为记录 ——
  尤其是第 4 条那次**误报的更正**，它比问题本身更有价值。
- **第二批（2026-10-02）**：6 条，**待模板作者处理**。这一批**没有一条是模板的缺陷**：
  第 5 条是引擎事实（建议进 `docs/godot-facts-verified.md`），6~9 是控件能力的缺口，
  第 10 条是小事。

日期：2026-09-22（一批）｜ 2026-10-02（二批） ｜ Godot 4.7.2 stable ｜ Windows 11（`chcp` 936）

## 第一批（已修）

| # | 项 | 状态 |
|---|---|---|
| 1 | 拖拽列宽时行内按钮不跟随 | **已修**（模板采用 `_on_widths_changed()` 拆法，比本文的补丁更清晰） |
| 2 | `_on_columns_changed()` 名不副实 | **已修**（补上重绘，成为真正的统一入口） |
| 3 | 窗口标题去不掉 ` (DEBUG)` | **已修**（封装为 `AppShell.set_window_title()`） |
| 4 | ~~`stretch_ratio` 会泄漏对象~~ | **误报，已撤回** —— 见第 4 条，含踩坑复盘 |

## 第二批（待处理）

| # | 项 | 类型 | 我们的现状 |
|---|---|---|---|
| 5 | `popup_on_parent()` 要全局坐标，不是父控件的局部坐标 | **引擎事实** | 已按正确写法实现，附实测 |
| 6 | `ColumnTable` 缺「哪一列吸收剩余宽度」的开关 | 能力缺口 | 已实现 `set_flex_column()`，含拖拽方向推导 |
| 7 | `TreeTable` 缺右键 / 上下文菜单钩子 | 能力缺口 | 已加 `item_context_menu` 信号 |
| 8 | `TreeTableItem` 缺逐单元格配色与 tooltip | 能力缺口 | 已加 `set_cell_color()` / `set_cell_tooltip()` |
| 9 | `FileDropBox` 只收一个路径 | 能力缺口 | 另写了 `FileDropZone`（291 行，可整体给） |
| 10 | `LogView` 缺 `debug` 级别 | 小 | 已加一档 |

> 滚动条样式盒 `content_margin=0`（给 0 就没有滚动条）那条是**模板先修的**
> （`6d4832c`，见其 `docs/godot-facts-verified.md` 的 1b），我们是同步方，不在本报告里。

---

## 1【Bug，已修】拖拽列宽时，行内按钮不跟着走

**文件**：`scripts/ui/column_table.gd` — `_gui_input()` 的列宽拖拽分支

**症状**：表头分隔线跟着鼠标动，但**行内按钮钉在原地**；松手后也不归位。
改窗口大小触发的重排是正常的 —— 所以只有拖拽时能看见。

**根因**：按钮的 x 是算出来的 —— `_place_action_cell()` 用 `_sep_x(col - 1)` 定位，
而 `_col_w()` 对**最后一列**返回「表宽 − 其它列之和」。于是拖任何一条分隔线都会
改变按钮该在的位置。但拖拽分支只重绘了、没有重摆按钮：

```gdscript
elif event is InputEventMouseMotion and _drag_col >= 0:
    ...
    _widths[_drag_col] = clampf(_drag_start_w + (event.position.x - _drag_start_x), lo, hi)
    queue_redraw()          # ← 只有重绘
    accept_event()
```

对照 `_on_resized()`（容器尺寸变化那条路），它一直是两件事都做的。
一个 `queue_redraw()`、一个没写，就是这个 bug。

**最终修法**（模板采用，比"就地补两句"更干净）：把「只是列宽变了」抽成
`_on_widths_changed()` = 重摆按钮 + 重绘，且**刻意不调 `update_minimum_size()`**
（拖拽每秒上百个 motion，每次让容器重算最小尺寸是白费，行高不会因拖列宽而变）；
`_on_columns_changed()` = `update_minimum_size()` + `_on_widths_changed()`，
成为名副其实的统一入口。三条调用路径（`set_columns` / `_on_resized` / 拖拽）
各取所需，不会再各缺一半。

**复现/回归**：模板的 `tools/checks/table_actions.gd`（14 条断言，含这条）。
反向验证过：把补丁退回去 → `[check] FAIL`、退出码 1、打印实际位移 0.0；补丁回来 → PASS。

> 写检查脚本时踩到的坑：判断按钮位置**不能用 `button.position`** —— 按钮是
> `HBoxContainer` 的子节点，在 HBox 里恒为第 0 个（x 永远是 0）；
> 真正被移动的是那个 HBox，要用 `global_position`。

---

## 2【隐患，已修】`_on_columns_changed()` 名不副实

它被注释成「列数 / 列宽 / 行数变化后的**统一入口**」，实现却只有最小尺寸 + 重摆按钮，
**没有 `queue_redraw()`**。唯一调用方 `set_columns()` 自己补了一句才没露馅 ——
于是任何人想复用它都会踩同一个坑（第 1 条的原始 bug 就是这么来的）。
现在重绘已经收进这条路径，调用方不用再记「要调几个函数」。

---

## 3【行为，已修】窗口标题怎么去掉 " (DEBUG)"

**症状**：直接用编辑器那套二进制跑工程时，窗口标题是 `项目名 (DEBUG)`，
看着像没编译完。

**根因**（实测，逐帧打点 + ctypes 读 OS 标题）：

| 做法 | OS 标题实际变成 |
|---|---|
| `get_window().title = "X"` | `X (DEBUG)` ← **`Window.title` 的 setter 会把后缀加回去** |
| `DisplayServer.window_set_title("X")` 写在 `_ready()` 里 | `项目名 (DEBUG)` ← **被引擎盖掉** |
| `DisplayServer.window_set_title("X")` 等 1 帧后再调 | `X` ✅ |

两件事都要做对：用 `DisplayServer`（别用 `Window.title`）、且等一帧
（引擎是在**窗口首帧显示时**才写那次默认标题的，晚于 `_ready()`）。
实测等 0 帧被盖掉、等 1 帧起稳定生效。

现已封装成 `AppShell.set_window_title()`，调用方不可能写错。

---

## 4【误报，已撤回】~~`stretch_ratio` 在 4.7.2 上会泄漏对象~~

**这条是错的，撤回。** 记全过程，因为它是一份很典型的「实验做坏了」的样本。

**当初的"复现"长这样**：4 次 `add_child(p); p.free()`，其中给控件设
`c.stretch_ratio = 3.0`，对比「设过」与「没设过」两种情况的
`ObjectDB instances were leaked` 计数 —— 得到「设过 60、没设 0」，
于是当成「`stretch_ratio` 导致泄漏」写进了报告。

**三个错误叠在一起**：

1. **属性名就是错的**。`Control` 上**没有** `stretch_ratio`，正确的是
   `size_flags_stretch_ratio`（`ClassDB.class_get_property_list("Control")` 里
   只有后者）。所以那行赋值**当场报错**：
   `Invalid assignment of property or key 'stretch_ratio' on a base object of type 'Control'`。
2. **报错让脚本中途中止**，后面的 `add_child` 全都没执行 —— 于是"设过"那组
   根本没建出对象，"没设过"那组建了。**两组的差异不是属性，是"脚本跑没跑完"**。
3. **判据是收尾噪声**。脚本中途死掉、headless 下的引擎收尾，本来就会打出
   `ObjectDB instances were leaked at exit`；把它当成被测代码的罪证，就成了自洽的假象
   ——「去掉那一行就不漏了」，其实只是「去掉那一行脚本才能跑完」。

**用正确属性名重测的结果**：

```
baseline             跑到底=1  报错=0  无泄漏报告
stretch_ratio        跑到底=0  报错=1  无泄漏报告   ← 那行报错，脚本中止
size_flags_stretch   跑到底=1  报错=0  无泄漏报告   ← 正确属性名，不泄漏
expand_fill          跑到底=1  报错=0  无泄漏报告
```

**结论**：不存在这个泄漏。项目里可以正常使用 `size_flags_stretch_ratio`
（DeepScribe 的表格/日志高度分配就改回了 3:2 的这个属性）。

**方法论（已写进模板「关键注意」）**：

- 报「泄漏 / 崩溃 / 行为异常」之前，**先跑一个什么都不建的空基线**
  （`--script` 起个空脚本、跑同样的帧数），看基线自己是不是也打同样的消息；
- **确认脚本跑到底了**（末尾 `print` 一句），并**断言零脚本错误** ——
  一旦中途报错中止，A/B 两组比的就不是你以为的那个变量；
- 「注释掉某一行就好了」不是结论，只是线索。

**顺带一提**：`--headless` 下脚本出错、或 `--quit-after` 给得很大，都会在退出时
打出 `ObjectDB instances were leaked at exit` —— 看到这行先怀疑收尾，别急着怀疑代码。

---

# 第二批（2026-10-02，待处理）

## 5【引擎事实，建议进 `docs/godot-facts-verified.md`】`popup_on_parent()` 要的是全局坐标

**症状**：给 `TreeTable` 加行级右键菜单时，把 `PopupMenu` 挂成表格的子节点、
按「父控件局部坐标」弹出，菜单整体**往左上偏**，偏差正好等于表格的全局 x
（我们的界面左侧有 196px 侧边栏 + 16px 页边距，于是菜单偏出去 244px）。

**根因**（Godot 4.7 文档原话）：

> Popups the Window with a position shifted by parent **Window's** position.
> If the Window is embedded, has the same effect as `popup()`.

而 `popup()` 的说明写着 "rect must be in global coordinates"（单窗口模式下，
坐标相对**主窗口左上角**）。所以：

- **把 `PopupMenu` 挂成某个 `Control` 的子节点，并不会让坐标变成控件局部的** ——
  「父亲是 Control」和「坐标相对谁」是两回事，这是最容易想当然的地方；
- 嵌入式弹窗的「主窗口左上角」正好等于 `Control.get_global_position()` 的原点，
  所以 `Rect2(host.get_global_position() + local_pos, Vector2.ZERO)` 在
  嵌入 / 非嵌入两种模式下都对（非嵌入时 `popup_on_parent` 会补上父窗口的位置）。

**实测**（宿主控件放在 220px 占位 + 16px 页边距之后，模拟「左边有侧边栏」；
点击位置 `local_pos = (320, 75)`）：

| 传什么 | 菜单实际落在 | 偏差 |
|---|---|---|
| `Rect2(local_pos, Vector2.ZERO)` | `(320, 75)` | **向左偏 244px**（= 宿主全局 x） |
| `Rect2(host.get_global_position() + local_pos, Vector2.ZERO)` | `(564, 99)` | **0, 0** ✅ |

**顺带一条**：嵌入弹窗会被引擎**自动收进视口**，靠边时不用自己做 clamp ——
请求 `(1590, 1190)` → 实际 `(1516, 996)`，右下边缘恰好贴住 1600×1200 视口。

**复现**：起一个带非零全局偏移的 `Control`，把一个有几项的 `PopupMenu` 挂上去，
按上面两种写法各弹一次，读 `menu.position` 即可。**注意宿主必须有非零偏移** ——
贴着原点摆的话，错的写法也会碰巧通过。

---

## 6【建议】`ColumnTable` 缺「哪一列吸收剩余宽度」的开关

**现状**：`_col_w()` 把「**最后一列**自动填满剩余宽度」写死（`widths.size() - 1`）。
这对「操作列放按钮」的表格是对的，但一旦你要的是「第一列最宽」，最后一列就会
变成几百像素的空档 —— 而最该宽的那一列反而被挤到最窄。

**动机场景**：文件列表是 `[文件名, 状态, 操作]`，理想是文件名吃掉剩余宽度、
状态/操作保持小固定宽度。宽度串 `[280, 100, 178]` 在 1400px 窗口下会让
「操作」列拿到 1020px。

**建议做法**：加 `set_flex_column(index)`，`-1`（默认）= 最后一列 —— 
**保持现有行为逐像素不变**，这样 `DataTable` 和 gallery 里的用法都不用动。
`_flex_index()` 要做越界回退到最后一列，保证「总有且只有一列」吸收剩余宽度，
否则列宽之和会小于表宽、表格右侧留一条空白（不报错的那种难看）。

### 精华在这里：拖拽方向要按 flex 位置分段

把 flex 列从最右挪走之后，`_gui_input()` 里那条**「拖分隔线 = 改左边那列」的
隐含假设就失效了**。第一版我们就是这么写的，被 review 逮住 ——

设 flex 下标为 `f`、三列 `[文件名(flex), 状态, 操作]`：

```
sep(0) = 表宽 − w₁ − w₂        ← 文件名|状态
sep(1) = 表宽 − w₂             ← 状态|操作，**跟 w₁ 完全无关**
```

于是用户抓住「状态|操作」那条线拖，`w₁` 是在变，但**那条线纹丝不动、
反而是隔壁那条在跑** —— 「抓住的线不跟手」，这是最难受的一种交互。

正确规则是「**哪一列决定这条线的位置**就改哪一列」：

| 条件 | 改哪一列 | 位移映射 | 理由 |
|---|---|---|---|
| `line < f` | 分隔线**左边**那列 | `w_line += delta` | 位置 = 左侧各固定列之和 |
| `line >= f` | 分隔线**右边**那列 | `w_line+1 -= delta` | 位置 = 表宽 − 右侧各列之和 |

两段都保证**被拖的那条线严格跟着鼠标走**，差值由 flex 列吸收。
`f == 最后一列`（默认）时第一段覆盖所有分隔线，退化成老实现。

**上限钳制**统一写成「让 flex 列不小于 `TABLE_MIN_COL`」：

```gdscript
var other := 0.0
for k in range(_widths.size()):
    if k != _flex_index() and k != _drag_target:
        other += _widths[k]
var hi := maxf(size.x - other - ThemePalette.TABLE_MIN_COL, lo)
```

**我们这边的实现**：`column_table.gd` 的 `set_flex_column()` / `_flex_index()`，
文件头写了完整推导。回归断言在 `tools/checks/table_actions.gd` 的两个函数
`_check_flex_column_layout()` / `_check_flex_column_drag()`（全表 28 条断言，
flex 相关 13 条，含「线严格跟手」「被拖列到下限」「flex 列到下限」三种边界）。
反向验证过：把拖拽分支退回「永远改左边那列」→ 断言立刻失败。

---

## 7【建议】`TreeTable` 缺右键 / 上下文菜单钩子

**现状**：只有 `item_selected` / `item_activated` / `item_toggled` 三个信号，
没有「在某一行上按了右键」。行级操作菜单（改这一行的运行参数、删除、重试…）
是这类表格的常见需求，缺了就只能自己去覆写 `_on_body_input()`。

**建议**：加一个 `item_context_menu(item: TreeTableItem, at_position: Vector2)`，
`at_position` 用**表格自身坐标**（调用方配合第 5 条那件事换算成全局坐标即可）。
几个要点：

- 非左键的事件**本来就会落到** `ColumnTable._gui_input()` 的 `else` 分支 →
  `_on_body_input()`，所以不用改基类的 `_gui_input()`；
- 只对**命中某一行**的情况发信号（`_row_at(...) >= 0`），表头/空白处不发；
- 顺带 `select()` 那一行，让用户看清菜单改的是哪一行。

**我们这边的实现**：`tree_table.gd` 的信号 + `_on_body_input()` 里的右键分支，
页面侧用 `menu.popup_on_parent(Rect2(...))` 弹出。

---

## 8【建议】`TreeTableItem` 缺逐单元格配色与 tooltip

**现状**：只有 `set_text()` / `set_cells()`，整行一个 `default_color`，
也没有逐格提示（`Control.tooltip_text` 只有一个，逐单元格得走
`Control._get_tooltip()` 回调）。

**动机场景**（两个都是刚需，不是锦上添花）：

- **状态列按语义上色**：等待中灰、解析中橙、完成绿、失败红 —— 一眼扫过去就知道
  哪个文件出事了，比逐行读文字快得多；
- **长路径悬停看全**：表格里只能显示 basename 或截断后的路径，
  鼠标停上去要能看到完整路径。

**建议**：`TreeTableItem.set_cell_color(col, color)` / `set_cell_tooltip(col, text)`，
配 `TreeTable` 侧三个私有钩子 `_cell_color()` / `_get_tooltip()` / `_col_at()`
（`_get_tooltip()` 覆写 `Control` 的回调，按 `(行长, 列)` 定位到具体单元格）。

> 「设过颜色」的判定我们用 `color.a > 0`（见 `set_cell_color` 的注释）——
> 用「有没有设过」的字典记录也可以，但那样每个单元格都要多存一份状态。

**我们这边的实现**：`tree_table_item.gd` 的 `set_cell_color()` / `set_cell_tooltip()`，
`tree_table.gd` 的 `_cell_color()` / `_get_tooltip()` / `_col_at()`。

---

## 9【建议】`FileDropBox` 只收一个路径

**现状**：控件语义是「一个文件」—— 信号是 `path_changed(path: String)`，
而 `accept_dropped_files()` 虽然有 `PackedStringArray` 的形状，实现里是
`set_path(files[0])`：**拖进来一批只会生效第一个，其余的静默丢掉**
（用户看不出来，会以为都在处理）。

**动机场景**：「拖一批 PDF 进来批量处理」是这类应用的第一个动作。

**我们另写的 `FileDropZone`**（`scripts/ui/file_drop_zone.gd`，291 行）：
多文件 + 文件夹递归扫描；三个入口（拖放一批 / 加单个文件 / 加文件夹），
因为 `FileDialog` **不支持多选文件**（这条模板的坑列表里也有）；配色复用
`_add_drop_colors()`，所以视觉上和 `FileDropBox` 是一套。要的话可以整个给。

---

## 10【小】`LogView` 缺 `debug` 级别

现在认 `ok` / `warn` / `error` / `system`。从 Python `logging` 过来的级别是
`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`，**一个都命不中**，
调用方得自己做映射（我们是在页面里加了一层 `_log_level()`）。
加一档 `debug`（配色走 `TEXT_DIS`）就不用映射了。

> 顺带记一条我们这边的坑：`LogView.append()` **内部已经做了一次 BBCode 转义**
> （`[` → `[lb]`），调用方**不要再转一次** —— 转两次会把 `[BLK:0]` 渲染成字面的
> `[lb]BLK:0]`。这条建议写进 `LogView` 的文档注释（我们那边已经写了）。
