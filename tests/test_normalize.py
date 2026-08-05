import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as M


class TestNormalizeMD(unittest.TestCase):
    def test_unicode_linebreaks(self):
        self.assertEqual(M.normalize_md("a" + chr(0x2028) + "b"), "a\nb")      # LINE SEPARATOR
        self.assertEqual(M.normalize_md("a" + chr(0x2029) + "b"), "a\n\nb")    # PARAGRAPH SEPARATOR
        self.assertEqual(M.normalize_md("a" + chr(0x000B) + "b"), "a\nb")      # VERTICAL TAB

    def test_latex_fixes(self):
        self.assertEqual(M.normalize_md(r"\dag"), r"\dagger")
        self.assertEqual(M.normalize_md(r"\ddag"), r"\ddagger")
        self.assertEqual(M.normalize_md(r"\lamba"), r"\lambda")
        self.assertEqual(M.normalize_md(r"\Rho"), r"\rho")
        self.assertEqual(M.normalize_md(r"\Bbb{R}"), r"\mathbb{R}")

    def test_latex_boundary_no_false_positive(self):
        # \dag 规则带 (?![a-zA-Z]) 边界，不能误伤 \dagger
        self.assertEqual(M.normalize_md(r"\dagger"), r"\dagger")
        self.assertEqual(M.normalize_md(r"\lambda"), r"\lambda")

    def test_dollar_spaces_cleaned(self):
        self.assertEqual(M.normalize_md("$ x $"), "$x$")
        self.assertEqual(M.normalize_md("$x $"), "$x$")
        self.assertEqual(M.normalize_md("$ x$"), "$x$")


class TestNormalizeOutput(unittest.TestCase):
    def test_strip_control_chars(self):
        inp = ("a" + chr(0x0000) + "b" + chr(0x001F) + "c"
               + chr(0x200B) + "d" + chr(0xFEFF))
        self.assertEqual(M.normalize_output(inp), "abcd")

    def test_code_block_internal_lines_preserved(self):
        inp = "```\ncode line 1\ncode line 2\n```\nnext"
        out = M.normalize_output(inp)
        self.assertIn("code line 1\ncode line 2", out)

    def test_math_block_internal_lines_preserved(self):
        inp = "$$\na + b\n= c\n$$\nnext"
        out = M.normalize_output(inp)
        self.assertIn("a + b\n= c", out)

    def test_soft_newline_merge_cjk(self):
        self.assertEqual(M.normalize_output("这是第一行\n继续的内容"),
                         "这是第一行 继续的内容")

    def test_soft_newline_merge_english(self):
        self.assertEqual(M.normalize_output("This is a line\ncontinued here"),
                         "This is a line continued here")

    def test_no_merge_after_cjk_punctuation(self):
        out = M.normalize_output("句子结束。\n新的一句")
        self.assertEqual(out, "句子结束。\n新的一句")

    def test_no_merge_before_block_prefix(self):
        self.assertEqual(M.normalize_output("正文行\n# 标题"), "正文行\n# 标题")
        self.assertEqual(M.normalize_output("正文行\n- 列表项"), "正文行\n- 列表项")


class TestEstimateTokens(unittest.TestCase):
    def test_english(self):
        self.assertEqual(M.estimate_tokens("hello world"), 3)  # 10*0.3 + 1*0.25

    def test_chinese(self):
        self.assertEqual(M.estimate_tokens("你好世界"), 2)  # 4*0.6

    def test_returns_int(self):
        self.assertIsInstance(M.estimate_tokens("some text with tokens"), int)


if __name__ == "__main__":
    unittest.main()
