# 回给 Godot4GUI 模板的问题报告

本文记录在 DeepScribe 上用模板控件库时发现的问题与建议。**都已回搬到模板**
（2026-09-22，由模板作者处理），这里保留作为记录 —— 尤其是第 4 条那次**误报的更正**，
它比问题本身更有价值。

日期：2026-09-22 ｜ Godot 4.7.2 stable ｜ Windows 11（`chcp` 936）

| # | 项 | 状态 |
|---|---|---|
| 1 | 拖拽列宽时行内按钮不跟随 | **已修**（模板采用 `_on_widths_changed()` 拆法，比本文的补丁更清晰） |
| 2 | `_on_columns_changed()` 名不副实 | **已修**（补上重绘，成为真正的统一入口） |
| 3 | 窗口标题去不掉 ` (DEBUG)` | **已修**（封装为 `AppShell.set_window_title()`） |
| 4 | ~~`stretch_ratio` 会泄漏对象~~ | **误报，已撤回** —— 见第 4 条，含踩坑复盘 |

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
