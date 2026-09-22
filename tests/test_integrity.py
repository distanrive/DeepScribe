import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import integrity as IV


def _math_texts(text, codes=()):
    return [t for t, _, _ in IV.extract_math_spans(text, codes)]


class TestExtractMathSpans(unittest.TestCase):
    def test_inline_math(self):
        self.assertEqual(_math_texts("see $x$ here"), ["x"])

    def test_display_math_preferred(self):
        self.assertEqual(_math_texts("$$a$$ then $b$"), ["a", "b"])

    def test_multiline_display_math(self):
        self.assertEqual(_math_texts("$$\na+b\n$$\n"), ["\na+b\n"])

    def test_escaped_dollar_not_math(self):
        self.assertEqual(IV.extract_math_spans(r"\$5"), [])
        self.assertEqual(_math_texts(r"\$x$y$"), ["y"])


class TestExtractCodeSpans(unittest.TestCase):
    def test_inline_code(self):
        self.assertEqual(
            [t for t, _, _ in IV.extract_code_spans("use `foo` now")],
            ["foo"])

    def test_fenced_code_not_treated_as_inline(self):
        # CODE_PAT 只匹配单行反引号片段，fenced 块（含换行）不提取
        self.assertEqual(IV.extract_code_spans("```\nfoo\n```"), [])


class TestMasking(unittest.TestCase):
    def test_code_masked_before_math(self):
        text = "`$x$` outside"
        codes = IV.extract_code_spans(text)
        self.assertEqual([t for t, _, _ in codes], ["$x$"])
        # 掩码后，代码内的 $ 不会被误判为公式
        self.assertEqual(IV.extract_math_spans(text, codes), [])
        # 不掩码则会误判
        self.assertNotEqual(IV.extract_math_spans(text), [])


class TestCanonicalizeLatex(unittest.TestCase):
    def test_whitespace_removed(self):
        self.assertEqual(IV.canonicalize_latex("x + y"),
                         IV.canonicalize_latex("x+y"))

    def test_aliases_normalized(self):
        pairs = [
            (r"\dag", r"\dagger"),
            (r"\ddag", r"\ddagger"),
            (r"\lamba", r"\lambda"),
            (r"\Bbb{R}", r"\mathbb{R}"),
            (r"\Rho", r"\rho"),
            (r"\Epsilon", r"\epsilon"),
            (r"\bf{X}", r"\mathbf{X}"),
            (r"\rm X", r"\mathrm X"),
            (r"\it x", r"\textit x"),
            (r"\cal F", r"\mathcal F"),
        ]
        for a, b in pairs:
            self.assertEqual(IV.canonicalize_latex(a),
                             IV.canonicalize_latex(b), (a, b))

    def test_alias_with_trailing_word(self):
        # \dag 后跟字母（去空白前有空格分隔）也应归一，避免合法修正被误报
        self.assertEqual(IV.canonicalize_latex(r"a\dag b"),
                         IV.canonicalize_latex(r"a\dagger b"))

    def test_command_boundary_no_false_positive(self):
        self.assertEqual(IV.canonicalize_latex(r"\bfseries"), r"\bfseries")
        self.assertEqual(IV.canonicalize_latex(r"\rmfamily"), r"\rmfamily")
        self.assertEqual(IV.canonicalize_latex(r"\textit"), r"\textit")


class TestVerifyBlock(unittest.TestCase):
    def test_identical_passthrough(self):
        zh, warns = IV.verify_block("see $x$ here", "see $x$ here")
        self.assertEqual(zh, "see $x$ here")
        self.assertEqual(warns, [])

    def test_broken_inline_math_backfilled(self):
        zh, warns = IV.verify_block("see $x$ here", "see $y$ here")
        self.assertEqual(zh, "see $x$ here")
        self.assertEqual(len(warns), 1)

    def test_legal_latex_fix_not_flagged(self):
        # LLM 被 prompt 允许把 \dag 修正为 \dagger，不应误报也不应回填
        zh, warns = IV.verify_block(r"$a\dag b$", r"$a\dagger b$")
        self.assertEqual(zh, r"$a\dagger b$")
        self.assertEqual(warns, [])

    def test_broken_inline_code_backfilled(self):
        zh, warns = IV.verify_block("use `foo` now", "use `bar` now")
        self.assertEqual(zh, "use `foo` now")
        self.assertEqual(len(warns), 1)

    def test_second_formula_backfilled_only(self):
        zh, warns = IV.verify_block("a $x$ and $y$", "甲 $x$ 和 $z$")
        self.assertEqual(zh, "甲 $x$ 和 $y$")
        self.assertEqual(len(warns), 1)

    def test_math_count_mismatch_warns(self):
        # 数量不一致时不能按序号回填：序号配对只在数量相同时才成立，
        # 否则每一对都可能错位，回填等于把正确的公式换成另一个。
        # 这里只告警、不改写（原实现会把 $c$ 换成 $a$）。
        zh, warns = IV.verify_block("$a$ and $b$", "$c$")
        self.assertIn("数量不一致", " ".join(warns))
        self.assertIn("跳过回填", " ".join(warns))
        self.assertEqual(zh, "$c$")

    def test_code_count_mismatch_warns(self):
        zh, warns = IV.verify_block("`a` and `b`", "`c`")
        self.assertIn("数量不一致", " ".join(warns))
        self.assertIn("跳过回填", " ".join(warns))
        self.assertEqual(zh, "`c`")

    def test_extra_zh_code_span_not_misaligned(self):
        # 回归：译文比原文多一个行内代码片段时，按序号配对会把 en 的 `y` 回填到
        # 译文多出来的 `新` 上，产出「使用 `x`、`y` 和 `y`」——原文那个词消失。
        # 现在应当只告警、不改写。
        zh, warns = IV.verify_block("use `x` and `y`", "使用 `x`、`新` 和 `y`")
        self.assertEqual(zh, "使用 `x`、`新` 和 `y`")
        self.assertIn("数量不一致", " ".join(warns))

    def test_fewer_zh_spans_keeps_zh_intact(self):
        # 回归：原文 2 个公式、译文只剩后一个时，旧实现会把 $b$ 换成 $a$。
        zh, warns = IV.verify_block("$a$ and $b$", "和 $b$")
        self.assertEqual(zh, "和 $b$")
        self.assertIn("数量不一致", " ".join(warns))

    def test_mixed_math_and_code_backfill(self):
        zh, warns = IV.verify_block("$x$ in `foo`", "$y$ in `bar`")
        self.assertEqual(zh, "$x$ in `foo`")
        self.assertEqual(len(warns), 2)


if __name__ == "__main__":
    unittest.main()
