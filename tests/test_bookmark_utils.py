import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bookmark_utils as B


class TestSplitLargeChapters(unittest.TestCase):
    """_split_large_chapters 是纯函数，无需 fitz 即可测试。"""

    def _bookmarks(self):
        # [(level, title, page_1based)]
        return [
            (1, "Ch1", 1),
            (1, "Ch2", 11),
            (2, "S2.1", 11),
            (2, "S2.2", 60),
            (2, "S2.3", 120),
            (1, "Ch3", 151),
        ]

    def test_small_chapters_unchanged(self):
        chapters = [("Ch1", 0, 9), ("Ch2", 10, 149), ("Ch3", 150, 159)]
        result = B._split_large_chapters(chapters, self._bookmarks(), max_chapter_pages=100)
        titles = [t for t, _, _ in result]
        self.assertIn("Ch1", titles)
        self.assertIn("Ch3", titles)
        # Ch2 (140 页) 被拆成 3 段，总数 5
        self.assertEqual(len(result), 5)

    def test_large_chapter_split_by_level2(self):
        chapters = [("Ch2", 10, 149)]
        result = B._split_large_chapters(chapters, self._bookmarks(), max_chapter_pages=100)
        # 二级书签页(1-based)=11/60/120 → 0-based=10/59/119
        self.assertEqual(result, [
            ("Ch2 — S2.1", 10, 58),
            ("Ch2 — S2.2", 59, 118),
            ("Ch2 — S2.3", 119, 149),
        ])

    def test_large_chapter_without_level2_unchanged(self):
        chapters = [("Ch2", 10, 149)]
        bookmarks = [(1, "Ch2", 11)]  # 无二级书签
        result = B._split_large_chapters(chapters, bookmarks, max_chapter_pages=100)
        self.assertEqual(result, [("Ch2", 10, 149)])

    def test_empty_subchapter_skipped(self):
        # 两个二级书签同页(1-based)=20 → 0-based=19，产生空子章，应被跳过
        chapters = [("Ch", 5, 100)]
        bookmarks = [(1, "Ch", 1), (2, "S1", 10), (2, "S2", 20), (2, "S3", 20)]
        result = B._split_large_chapters(chapters, bookmarks, max_chapter_pages=50)
        self.assertEqual(result, [
            ("Ch — S1", 5, 18),
            ("Ch — S3", 19, 100),
        ])


class TestBuildChapterRanges(unittest.TestCase):
    """L3: 首个一级书签之前的页作为前置章节。"""

    def test_front_matter_added_when_first_bookmark_after_page1(self):
        level1 = [(1, "Ch1", 5), (1, "Ch2", 20)]
        result = B._build_chapter_ranges(level1, total_pages=30)
        self.assertEqual(result, [
            ("封面与目录", 0, 3),   # 页 1-4（封面/目录）
            ("Ch1", 4, 18),         # 页 5-19
            ("Ch2", 19, 29),        # 页 20-30
        ])

    def test_no_front_matter_when_first_bookmark_at_page1(self):
        level1 = [(1, "Ch1", 1), (1, "Ch2", 20)]
        result = B._build_chapter_ranges(level1, total_pages=30)
        self.assertEqual(result, [
            ("Ch1", 0, 18),
            ("Ch2", 19, 29),
        ])


class TestDegradedMode(unittest.TestCase):
    """fitz 不可用时的降级路径。"""

    def test_extract_bookmarks_degraded(self):
        old = B._FITZ_AVAILABLE
        B._FITZ_AVAILABLE = False
        try:
            bookmarks, total = B.extract_bookmarks(Path("nonexistent.pdf"))
            self.assertEqual(bookmarks, [])
            self.assertEqual(total, 0)
        finally:
            B._FITZ_AVAILABLE = old

    def test_split_pdf_degraded(self):
        old = B._FITZ_AVAILABLE
        B._FITZ_AVAILABLE = False
        try:
            result = B.split_pdf_by_bookmarks(
                Path("x.pdf"), [(1, "T", 1)], 10, Path("."), "s")
            self.assertEqual(result, [("T", Path("x.pdf"))])
        finally:
            B._FITZ_AVAILABLE = old


if __name__ == "__main__":
    unittest.main()
