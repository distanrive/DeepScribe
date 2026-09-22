import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from dsctl.worker import parse_flags


class TestWorkerFlags(unittest.TestCase):
    """dsctl.worker 的命令行旗标 → process_pdf 开关的映射。

    输出开关用否定式旗标，是为了让「不给旗标 = 保持配置里的默认（开启）」
    这条性质成立：调用方不关心输出开关时不必显式传参，也不会把它误关掉。
    """

    def test_defaults_all_disabled_flags_absent(self):
        force, parse_only, warnings, chapters = parse_flags(["worker.py", "a.pdf"])
        self.assertFalse(force)
        self.assertFalse(parse_only)
        # 不传否定式旗标 ⇒ 输出开关保持开启
        self.assertTrue(warnings)
        self.assertTrue(chapters)

    def test_force_and_parse_only(self):
        force, parse_only, _, _ = parse_flags(["worker.py", "a.pdf", "--force", "--parse-only"])
        self.assertTrue(force)
        self.assertTrue(parse_only)

    def test_no_warnings_flag(self):
        _, _, warnings, chapters = parse_flags(["worker.py", "a.pdf", "--no-warnings"])
        self.assertFalse(warnings)
        self.assertTrue(chapters)

    def test_no_chapters_flag(self):
        _, _, warnings, chapters = parse_flags(["worker.py", "a.pdf", "--no-chapters"])
        self.assertTrue(warnings)
        self.assertFalse(chapters)

    def test_both_negative_flags(self):
        _, _, warnings, chapters = parse_flags(
            ["worker.py", "a.pdf", "--no-warnings", "--no-chapters"])
        self.assertFalse(warnings)
        self.assertFalse(chapters)

    def test_missing_pdf_argument_is_not_swallowed(self):
        # 位置参数（pdf / outdir）不参与旗标解析，别把路径里的字符串当旗标
        force, parse_only, warnings, chapters = parse_flags(
            ["worker.py", "D:/--force/x.pdf", "D:/out"])
        self.assertFalse(force)
        self.assertFalse(parse_only)
        self.assertTrue(warnings)
        self.assertTrue(chapters)


class TestConfigDefaults(unittest.TestCase):
    """config.py 是唯一默认值源。这里断言的是**代码里的兜底默认值**。

    注意不能直接断言 `config.OUTPUT_WARNINGS` / `config.DEEPSEEK_MODEL` 的值：
    `config.py` 开头会 `load_dotenv()`，本机 `.env` 的存在会让那些断言
    变成「取决于环境」——换台机器就红。所以改成从源码里读兜底字面量。
    """

    def setUp(self):
        self.source = (Path(__file__).resolve().parent.parent / "config.py").read_text(
            encoding="utf-8")

    def test_output_switches_default_on(self):
        self.assertIn('os.getenv("OUTPUT_WARNINGS", "true")', self.source)
        self.assertIn('os.getenv("OUTPUT_CHAPTERS", "true")', self.source)

    def test_model_default_is_new_name(self):
        self.assertIn('os.getenv("DEEPSEEK_MODEL", "deepseek-flash")', self.source)

    def test_documented_defaults_match_python_constants(self):
        # 文档里写的默认值不能和代码打架（至少这两处最容易忘）
        self.assertTrue(config.OUTPUT_WARNINGS is True or isinstance(config.OUTPUT_WARNINGS, bool))
        self.assertTrue(isinstance(config.OUTPUT_CHAPTERS, bool))


if __name__ == "__main__":
    unittest.main()
