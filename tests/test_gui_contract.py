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
        self.assertIn('"并行翻译"', src)
        self.assertIn('"仅解析"', src)
        self.assertIn('"输出warning"', src)
        self.assertIn('"分章输出"', src)
        # 旧文案不许再出现
        self.assertNotIn("强制重新解析", src)
        self.assertNotIn("启用并行翻译", src)

    def test_config_page_labels(self):
        src = read("scripts/pages/config_page.gd")
        self.assertIn('g.title = "并行设置"', src)
        self.assertIn('"最大翻译并发"', src)
        self.assertIn('"解析最大并发"', src)
        self.assertNotIn("并行翻译设置", src)
        self.assertNotIn("最大并发线程数", src)

    def test_about_page_license_and_stack(self):
        src = read("scripts/pages/about_page.gd")
        self.assertIn("MIT License", src)
        self.assertNotIn("GPL", src)
        self.assertIn("Godot 4", src)
        self.assertNotIn("PyQt5", src)


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
