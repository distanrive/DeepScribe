import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as M


class TestFixHeadingsSerial(unittest.TestCase):
    def test_chapter_flow_close_and_reset(self):
        md = (
            "# 1 Introduction\n"
            "## 1.1 Background\n"
            "### 1.1.1 Sub\n"
            "## 1.A 非标准\n"
            "## 1.2 After\n"
            "# 2 Methods\n"
            "## 2.1 M1\n"
            "# 3 Late\n"
            "## 2.5 backtrack\n"
            "# Problems\n"
            "# 4 X"
        )
        expected = (
            "# 1 Introduction\n"
            "## 1.1 Background\n"
            "### 1.1.1 Sub\n"
            "## 1.A 非标准\n"
            "1.2 After\n"
            "# 2 Methods\n"
            "## 2.1 M1\n"
            "# 3 Late\n"
            "2.5 backtrack\n"
            "# Problems\n"
            "# 4 X"
        )
        out, warnings = M.fix_headings(md)
        self.assertEqual(out, expected)
        self.assertEqual(len(warnings), 2)  # 1.A 关闭 + Problems 关闭

    def test_depth_correction_by_number_parts(self):
        md = "### 1.1 Introduction\n# 1.1.1 Sub\n## 1.1.1.1 Deep"
        out, _ = M.fix_headings(md)
        self.assertEqual(out, "## 1.1 Introduction\n### 1.1.1 Sub\n#### 1.1.1.1 Deep")

    def test_ordering_regression_downgraded(self):
        md = "## 1.1 A\n## 1.3 B\n### 1.2 C"
        out, warnings = M.fix_headings(md)
        self.assertEqual(out, "## 1.1 A\n## 1.3 B\n1.2 C")
        self.assertEqual(len(warnings), 1)

    def test_chapter_backtrack_downgraded(self):
        md = "# 3 Late\n## 2.5 backtrack"
        out, _ = M.fix_headings(md)
        self.assertEqual(out, "# 3 Late\n2.5 backtrack")

    def test_unchanged_when_no_numbering(self):
        md = "# Introduction\n\nSome text\n## Notes"
        out, _ = M.fix_headings(md)
        self.assertEqual(out, md)


class TestFixHeadingsParallel(unittest.TestCase):
    def test_single_chapter_close(self):
        md = (
            "## 1.1 Background\n"
            "### 1.1.1 Sub\n"
            "## 1.A 非标准\n"
            "## 1.2 After\n"
            "## 1.3 B\n"
            "# Problems\n"
            "## 1.4 C"
        )
        expected = (
            "## 1.1 Background\n"
            "### 1.1.1 Sub\n"
            "## 1.A 非标准\n"
            "1.2 After\n"
            "1.3 B\n"
            "# Problems\n"
            "1.4 C"
        )
        out, warnings = M.fix_headings_parallel(md)
        self.assertEqual(out, expected)
        self.assertEqual(len(warnings), 2)

    def test_no_chapter_increment_tracking(self):
        # 并行版单章内不做章号递增检测：2.x 出现在 1.x 后不会因章号倒退而降级
        md = "## 1.1 A\n## 2.1 B"
        out, _ = M.fix_headings_parallel(md)
        self.assertEqual(out, "## 1.1 A\n## 2.1 B")


class TestSerialParallelDrift(unittest.TestCase):
    """锁定串并行已知行为差异（E4 去重后仍应保持）：关键词关闭需先有编号章。"""

    def test_keyword_close_without_chapter(self):
        md = "# Preface\n# Problems\n## 1.1 A"
        serial_out, _ = M.fix_headings(md)
        self.assertEqual(serial_out, "# Preface\n# Problems\n## 1.1 A")
        parallel_out, _ = M.fix_headings_parallel(md)
        self.assertEqual(parallel_out, "# Preface\n# Problems\n1.1 A")


if __name__ == "__main__":
    unittest.main()
