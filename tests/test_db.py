import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import TranslationDB


class TestTranslationDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = TranslationDB(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_store_and_mark_done(self):
        self.db.store_paragraphs([(0, "en0"), (1, "en1")])
        self.db.mark_many_done({0: "zh0"})
        self.assertEqual(self.db.get_all_translations(), {0: "zh0"})
        self.assertEqual(self.db.get_pending_paragraphs(), [(1, "en1")])

    def test_mark_done_single(self):
        self.db.store_paragraphs([(0, "en0")])
        self.db.mark_done(0, "zh0")
        self.assertEqual(self.db.get_translation(0), "zh0")

    def test_upsert_same_content_keeps_done(self):
        self.db.store_paragraphs([(0, "en0")])
        self.db.mark_many_done({0: "zh0"})
        self.db.store_paragraphs([(0, "en0")])  # 内容未变 → is_done 保留
        self.assertEqual(self.db.get_all_translations(), {0: "zh0"})
        self.assertEqual(self.db.get_pending_paragraphs(), [])

    def test_upsert_changed_content_resets_done(self):
        self.db.store_paragraphs([(0, "en0")])
        self.db.mark_many_done({0: "zh0"})
        self.db.store_paragraphs([(0, "en0-changed")])  # 内容变化 → is_done 重置
        self.assertEqual(self.db.get_all_translations(), {})
        self.assertEqual(self.db.get_pending_paragraphs(), [(0, "en0-changed")])

    def test_prune_removes_deleted(self):
        self.db.store_paragraphs([(0, "en0"), (1, "en1"), (2, "en2")])
        self.db.prune({0, 2})
        pending = {idx for idx, _ in self.db.get_pending_paragraphs()}
        self.assertEqual(pending, {0, 2})

    def test_prune_all(self):
        self.db.store_paragraphs([(0, "en0"), (1, "en1")])
        self.db.prune(set())
        self.assertEqual(self.db.get_pending_paragraphs(), [])

    def test_resume_consistency(self):
        # 模拟断点续传：已完成段落重入后保留译文，未完成段落仍在 pending
        self.db.store_paragraphs([(0, "en0"), (1, "en1")])
        self.db.mark_many_done({0: "zh0"})
        self.db.store_paragraphs([(0, "en0"), (1, "en1")])
        self.assertEqual(self.db.get_all_translations(), {0: "zh0"})
        self.assertEqual(self.db.get_pending_paragraphs(), [(1, "en1")])

    def test_is_all_done(self):
        self.db.store_paragraphs([(0, "en0")])
        self.assertFalse(self.db.is_all_done())
        self.db.mark_many_done({0: "zh0"})
        self.assertTrue(self.db.is_all_done())

    def test_reset_paragraphs(self):
        self.db.store_paragraphs([(0, "en0"), (1, "en1"), (2, "en2")])
        self.db.mark_many_done({0: "zh0", 1: "zh1", 2: "zh2"})
        self.assertEqual(self.db.get_pending_paragraphs(), [])
        # 重置索引 0 和 2
        self.db.reset_paragraphs({0, 2})
        pending = {idx for idx, _ in self.db.get_pending_paragraphs()}
        self.assertEqual(pending, {0, 2})
        # 索引 1 仍为已完成
        self.assertEqual(self.db.get_translation(1), "zh1")

    def test_reset_paragraphs_empty(self):
        self.db.store_paragraphs([(0, "en0")])
        self.db.mark_many_done({0: "zh0"})
        self.db.reset_paragraphs(set())  # 空集合无操作
        self.assertEqual(self.db.get_pending_paragraphs(), [])


if __name__ == "__main__":
    unittest.main()
