"""Godot GUI 侧的「约定」测试。

这些都是**产品要求**，不是实现细节 —— 违反了就是需求没做到，但 Godot 跑不起来
时人眼很容易漏掉（比如某个按钮顺手写成了 emoji、下拉项忘了改）。
用 Python 直接读 GDScript 源码来钉住，跑测试就行，不需要开 Godot。
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GUI = Path(__file__).resolve().parent.parent / "godot_gui"
SCRIPTS = GUI / "scripts"


def read(rel: str) -> str:
    return (GUI / rel).read_text(encoding="utf-8")


def all_gd_files() -> list[Path]:
    return sorted(SCRIPTS.rglob("*.gd"))


def _func_body(src: str, name: str) -> str:
    """取某个函数的函数体（顶格的 `func <name>(` 到下一个顶格 `func` 之间）。

    粗切即可：GDScript 的函数体一律缩进，所以按顶格 `func ` 切是可靠的。
    找不到时返回空串（调用方 assertIn 会直接报错，比抛异常更好读）。
    """
    for part in re.split(r"\n(?=func )", src):
        if re.match(rf"func {re.escape(name)}\(", part):
            return part
    return ""


# emoji / 装饰性图形符号区段（要求：界面不许用表情图标）。
#
# 刻意**不含** 0x2190-0x21FF（← ↑ → ↓）与 0x2018-0x201F 这类：它们是中文排版里的
# 普通箭头与引号，注释和正文里到处都在用，不是「表情图标」。这里只盯旧 PyQt 界面
# 当图标用的那几类：✅❌⚠（dingbats）、▶◀■（几何图形）、⏹⏸（媒体控制）、
# 📂🗑💾🔗（emoji）。
_EMOJI_RANGES = (
    (0x23E9, 0x23FA),    # ⏹ ⏸ ⏺ 等媒体控制符
    (0x25A0, 0x25FF),    # ■ ▶ ◀ ● 等几何图形
    (0x2600, 0x27BF),    # ☀ ⚠ ✅ ❌ ➜ 等杂项符号与 dingbats
    (0x2B00, 0x2BFF),    # ⬅ ⬆ ⭐ 等
    (0x1F000, 0x1FAFF),  # 表情 / 图标 / 补充符号
    (0xFE0F, 0xFE0F),    # 变体选择符（强制 emoji 呈现）
)


def strip_comment(line: str) -> str:
    """去掉行尾注释，但**不碰字符串里的 `#`**（如 `"[color=#4a90d9]..."`）。

    为什么要这一步：模板文件里有把 ✅/❌ 写进**文档注释的表格**里的（说明性文字），
    那不是界面图标。本测试只管「代码与字符串里有没有 emoji」。
    """
    in_str = ""
    for i, ch in enumerate(line):
        if in_str:
            if ch == in_str:
                in_str = ""
        elif ch in "\"'":
            in_str = ch
        elif ch == "#":
            return line[:i]
    return line


def find_emoji(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        code = strip_comment(line)
        for ch in code:
            cp = ord(ch)
            if any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES):
                out.append(f"{ch!r} (U+{cp:04X}) 于: {line.strip()[:60]}")
                break
    return out


class TestNoEmojiIcons(unittest.TestCase):
    """界面源码里不允许出现 emoji / 装饰性图形符号。

    旧 PyQt 界面用的是 ▶ ⏹ 🗑 📂 ✅ ❌ ⚠️ ⏸ 🔒 ↻ 💾 🔗 这类字符，迁移时明确要求
    全部去掉，改用纯文字或 themes/icons 下的 SVG。
    """

    def test_no_emoji_in_scripts(self):
        offenders = {}
        for path in all_gd_files():
            hits = find_emoji(path.read_text(encoding="utf-8"))
            if hits:
                offenders[path.relative_to(GUI).as_posix()] = hits
        self.assertEqual(
            offenders, {},
            "界面脚本里出现了 emoji / 装饰性符号，请改用纯文字或 SVG 图标：\n"
            + "\n".join(f"  {k}: {v}" for k, v in offenders.items()))


class TestConfigPageOptions(unittest.TestCase):
    """配置页的待选项必须是需求里点名的那些。"""

    def setUp(self):
        self.src = read("scripts/pages/config_page.gd")

    def test_model_options(self):
        self.assertIn('const MODEL_ITEMS := ["deepseek-v4-pro", "deepseek-flash"]', self.src)

    def test_effort_options(self):
        self.assertIn('const EFFORT_ITEMS := ["off", "low", "high", "max"]', self.src)

    def test_unknown_saved_model_is_kept(self):
        # config.json 里可能是别的模型名（手改的、或旧版本留下的）：必须作为附加项
        # 显示出来，不能让它被下拉第一项顶掉后静默覆盖掉用户的设置。
        self.assertIn("MODEL_CUSTOM", self.src)
        self.assertIn("items.append(current)", self.src)


class TestRenamedLabels(unittest.TestCase):
    """需求点名的几处文案改动。"""

    def test_work_page_labels(self):
        src = read("scripts/pages/work_page.gd")
        self.assertIn('"强制重解析"', src)
        self.assertIn('"自动分章"', src)
        self.assertIn('"仅解析"', src)
        self.assertIn('"输出warning"', src)
        self.assertIn('"分章输出"', src)
        # 旧文案不许再出现
        self.assertNotIn("强制重新解析", src)
        self.assertNotIn("启用并行翻译", src)
        # 「并行翻译」这个叫法是错的：这一项控制的是**按书签切章**，
        # 翻译本来就是并发的（「最大翻译并发」），解析并发是「最大解析并发」。
        # 它在工具栏和右键菜单里都得叫「自动分章」。
        self.assertNotIn('"并行翻译"', src)

    def test_config_page_labels(self):
        src = read("scripts/pages/config_page.gd")
        self.assertIn('g.title = "并行设置"', src)
        self.assertIn('"最大翻译并发"', src)
        self.assertIn('"最大解析并发"', src)
        self.assertNotIn("并行翻译设置", src)
        self.assertNotIn("最大并发线程数", src)
        self.assertNotIn('"解析最大并发"', src)

    def test_about_page_license_and_stack(self):
        src = read("scripts/pages/about_page.gd")
        self.assertIn("MIT License", src)
        self.assertNotIn("GPL", src)
        self.assertIn("Godot 4", src)
        self.assertNotIn("PyQt5", src)


class TestWorkPageDetails(unittest.TestCase):
    """工作页的几条硬性要求（靠读源码钉住，不必开 Godot）。"""

    def setUp(self):
        self.src = read("scripts/pages/work_page.gd")

    def test_start_all_is_green(self):
        # 「全部开始」要和行内那个绿色的「开始」同色系
        self.assertIn('_make_button("全部开始", "SuccessButton"', self.src)

    def test_chapters_follow_auto_split(self):
        # 「自动分章」没勾时「分章输出」必须不可选：没切章就没有「每一章」可输出。
        self.assertIn("_chk_parallel.toggled.connect", self.src)
        self.assertIn("_chk_chapters.disabled = not auto_split", self.src)

    def test_toolbar_switch_order(self):
        """第二行开关的顺序是需求点名的：强制重解析 → 仅解析 → 自动分章 → 分章输出 → 输出warning。"""
        rows = re.findall(r"_toolbar_row\(\[([^\]]*)\]\)", self.src, re.S)
        with_checks = [r for r in rows if "_chk_" in r]
        self.assertEqual(len(with_checks), 1, "没找到那唯一一行勾选框，或匹配到了别的行")
        order = re.findall(r"_chk_\w+", with_checks[0])
        self.assertEqual(
            order,
            ["_chk_force", "_chk_parse_only", "_chk_parallel",
             "_chk_chapters", "_chk_warnings"],
            "工作页开关的顺序变了（需求：强制重解析 / 仅解析 / 自动分章 / 分章输出 / 输出warning）")

    def test_completed_rows_cannot_restart(self):
        """已完成的任务，「开始」与「停止」都不可选。

        关键在**判据只有一处**：行内按钮和「全部开始」都走 `_can_start()`，
        否则会出现「按钮灰着、但点「全部开始」还是把它带上」这种自相矛盾。
        （失败 / 部分失败 / 已取消**不锁** —— 那些正是最需要重跑的行。）
        """
        self.assertIn("DsProto.STATUS_DONE", self.src)
        self.assertIn("func _can_start(", self.src, "判据本身没了")

        # 判据只有一处（_can_start），两个消费方各自从它出发：
        #   行内按钮 → _can_start()
        #   「全部开始」→ _startable_paths() → _can_start()
        self.assertIn("_can_start(", _func_body(self.src, "_set_row_actions"),
                      "行内按钮没用 _can_start() 判可用性")
        self.assertIn("_startable_paths()", _func_body(self.src, "_on_start_all"),
                      "「全部开始」没走 _startable_paths()")
        self.assertIn("_can_start(", _func_body(self.src, "_startable_paths"),
                      "_startable_paths() 绕过了 _can_start()")

    def test_row_actions_refreshed_after_status(self):
        """按钮要在**状态落定之后**再配。

        这条差点就写错了：`_on_job_finished()` 原本先 `_set_row_actions()` 再
        `_set_status()`，而 `_can_start()` 判的是状态 —— 于是任务成功结束后，
        「开始」仍然亮着，而且再没有任何时机去刷新它（`_set_status()` 不碰按钮，
        每次进度都重建按钮又太浪费）。顺序反了就静默出错，所以钉住。
        """
        body = _func_body(self.src, "_on_job_finished")
        i_status = body.find("_set_status(")
        i_actions = body.find("_set_row_actions(")
        self.assertNotEqual(i_status, -1, "_on_job_finished 里没有 _set_status()")
        self.assertNotEqual(i_actions, -1, "_on_job_finished 里没有 _set_row_actions()")
        self.assertLess(
            i_status, i_actions,
            "先配按钮、后定状态 —— 会配出「已完成但『开始』还亮着」的行")

    def test_rows_have_per_file_options(self):
        # 右键菜单改的是**单个文件**的运行选项，执行时要按行取，而不是读全局勾选框。
        self.assertIn("_effective_opts(path)", self.src)
        self.assertIn("set_flex_column", self.src)

    def test_log_uses_template_log_view(self):
        # 日志改用模板控件后，自己那套「_[lb]转义 + 手工裁剪」必须一起删掉，
        # 否则二次转义会把 [BLK:0] 渲染成字面的 [lb]BLK:0]。
        self.assertIn("LogView.new()", self.src)
        self.assertNotIn("func _esc(", self.src)
        self.assertNotIn("append_text", self.src)


class TestAboutPageNoBullets(unittest.TestCase):
    """关于页每行前面不再顶一个「·」。"""

    def test_no_leading_dot(self):
        src = read("scripts/pages/about_page.gd")
        self.assertNotIn('"· " +', src)


class TestScrollBarTheme(unittest.TestCase):
    """滚动条必须真的画得出来。

    `ScrollBar` 的粗细就是样式盒的最小尺寸（content_margin 之和）；给 0 的话
    `VScrollBar.get_combined_minimum_size()` 是 `(0, 0)`，整条滚动条只剩贴着右缘
    一条抓不住的细痕（这个 bug 上游与 DeepScribe 都踩过，别再退回去）。
    """

    def test_token_exists(self):
        self.assertIn("SCROLLBAR_W", read("scripts/theme/theme_palette.gd"))

    def test_styleboxes_have_padding(self):
        src = read("scripts/theme/theme_factory.gd")
        for name in ["scroll", "scroll_focus", "grabber", "grabber_highlight", "grabber_pressed"]:
            self.assertIn(f'"{name}", "ScrollBar"', src,
                          f"ScrollBar 少了 {name} 样式盒")

    def test_log_view_colors_registered(self):
        src = read("scripts/theme/theme_factory.gd")
        for name in ["info_color", "ok_color", "warn_color", "error_color", "debug_color"]:
            self.assertIn(f'"{name}", "LogView"', src)


class TestPageRequestsRetryOnConnect(unittest.TestCase):
    """页面自己发起的请求必须挂到 `NetClient.connected` 上重试。

    为什么这是**产品要求**而不是实现细节：后端是前端自己拉起来的，要 1~3 秒才就绪；
    而每个发命令的地方都要先 `if not NetClient.is_open(): return`。两者一叠加，
    **启动后一两秒内发出的那一次必然被丢掉** —— 只靠 `_ready()` 里调一次是不够的，
    必须让 `connected` 每次（重）连再发一遍。

    漏挂的症状是「界面某一行永远停在占位文字」，而且**不报任何错**：配置页的缓存占用
    就漏过一次（`_request_cache_info`），表现出来是「切到配置页要等好几秒才出数字」，
    实际是请求压根没发出去。

    约定：这类函数命名以 `_request*` / `_sync*` 开头。若某个确实不该在重连时重发，
    换个名字（测试只看这两类前缀）。
    """

    def _functions(self, src: str) -> dict[str, str]:
        """粗切函数块：按顶格的 `func ` 切分（GDScript 的函数体一律缩进）。"""
        out = {}
        for part in re.split(r"\n(?=func )", src):
            m = re.match(r"func (\w+)\(", part)
            if m:
                out[m.group(1)] = part
        return out

    def test_every_request_helper_is_reconnected(self):
        offenders = []
        for path in sorted((SCRIPTS / "pages").glob("*.gd")):
            src = path.read_text(encoding="utf-8")
            connected = set(re.findall(r"NetClient\.connected\.connect\((\w+)\)", src))
            for name, body in self._functions(src).items():
                if not re.fullmatch(r"_(request|sync)\w*", name):
                    continue
                if "send_command(" not in body or name in connected:
                    continue
                offenders.append(f"{path.name}::{name}()")
        self.assertEqual(
            offenders, [],
            "这些函数会发命令、但没挂到 NetClient.connected 上 —— 启动早期那一次请求"
            "会被静默丢掉（不报错，界面只停占位文字）：\n  " + "\n  ".join(offenders))


class TestMultiFrontendContract(unittest.TestCase):
    """多前端：在线数广播 + 只有最后一个前端才收后端进程。"""

    def test_backend_broadcasts_client_count(self):
        backend = (GUI / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"type": "clients"', backend)
        self.assertIn('"clients": self.hub.count', backend)

    def test_launcher_respects_last_client(self):
        src = read("scripts/autoload/backend_launcher.gd")
        self.assertIn("_clients > 1", src)
        self.assertIn('"--exit-with-last-client"', src)


class TestNoSlotWaitNoise(unittest.TestCase):
    """日志里不再报「等待 MinerU 槽位多久」。"""

    def test_no_slot_wait_warning(self):
        path = Path(__file__).resolve().parent.parent / "dsctl" / "gpu_lock.py"
        src = path.read_text(encoding="utf-8")
        self.assertNotIn("等待 MinerU 槽位", src)


class TestBatEncoding(unittest.TestCase):
    """`.bat` 必须是 **GBK + CRLF + 无 BOM**。

    这是 Windows 命令行读批处理的实际规则，踩过的坑：

    * cmd.exe 按**当前控制台代码页**读 bat 文件（本机 `chcp` = 936），
      所以文件里的中文必须是 GBK 字节，UTF-8 会显示成乱码；
    * **带 UTF-8 BOM 的 bat 直接坏掉** —— cmd 把开头当成 `﻿@echo`，
      报「不是内部或外部命令」，连 `@echo off` 都没生效；
    * 裸 LF 换行在 `goto` / 标签 / 多行结构上会出问题，统一 CRLF。

    注意：用编辑器/工具改 bat 时容易顺手存成 UTF-8，所以这里钉住。
    （`tests/` 里的 Python 源文件是 UTF-8，不受这条约束。）
    """

    def _bats(self) -> list[Path]:
        return sorted(Path(__file__).resolve().parent.parent.glob("*.bat"))

    def test_files_exist(self):
        self.assertTrue(self._bats(), "仓库根一个 .bat 都没有？")

    def test_no_bom(self):
        bad = [p.name for p in self._bats() if p.read_bytes().startswith(b"\xef\xbb\xbf")]
        self.assertEqual(bad, [], f"这些 bat 带 UTF-8 BOM，cmd 会直接报错：{bad}")

    def test_valid_gbk(self):
        bad = []
        for p in self._bats():
            try:
                p.read_bytes().decode("gbk")
            except UnicodeDecodeError as exc:
                bad.append(f"{p.name} ({exc})")
        self.assertEqual(bad, [], f"这些 bat 不是合法 GBK，控制台里会乱码：{bad}")

    def test_crlf_only(self):
        bad = []
        for p in self._bats():
            raw = p.read_bytes()
            if raw.count(b"\n") != raw.count(b"\r\n"):
                bad.append(p.name)
        self.assertEqual(bad, [], f"这些 bat 里有裸 LF（应为 CRLF）：{bad}")


class TestProtocolConstants(unittest.TestCase):
    """前端协议常量必须与后端 `Session._dispatch` 的命令名一致。

    两边对不上时的症状是「点了没反应」，不会报错，所以值得钉一下。
    """

    def setUp(self):
        self.proto = read("scripts/ds_proto.gd")
        self.backend = (GUI / "backend" / "main.py").read_text(encoding="utf-8")

    def test_commands_match_backend(self):
        cmds = re.findall(r'const CMD_[A-Z_]+ := "([a-z_]+)"', self.proto)
        self.assertTrue(cmds, "没解析到 CMD_* 常量")
        for cmd in cmds:
            self.assertIn(f'cmd == "{cmd}"', self.backend,
                          f"前端有 {cmd}，但后端 _dispatch 里没有对应的分支")

    def test_message_types_match_backend(self):
        # 后端会发出的 type 值（send 时写死的字符串）
        emitted = set(re.findall(r'"type": "([a-z_]+)"', self.backend))
        declared = set(re.findall(r'const MSG_[A-Z_]+ := "([a-z_]+)"', self.proto))
        missing = emitted - declared
        self.assertEqual(missing, set(),
                         f"后端会发这些 type，但前端 ds_proto.gd 没声明：{sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
