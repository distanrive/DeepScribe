import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as M
from main import TranslationDB


class FakeTranslator:
    """translate_numbered 的替身；fail 集合中的索引不译（模拟失败）。"""

    def __init__(self, fail=(), always_fail=False):
        self.fail = set(fail)
        self.always_fail = always_fail
        self.calls = 0

    def translate_numbered(self, chunk, label="") -> dict[int, str]:
        self.calls += 1
        out = {}
        for idx, text in chunk:
            if self.always_fail or idx in self.fail:
                continue
            out[idx] = f"译文{idx}"
        return out


class TestTranslateBlocks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = TranslationDB(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _blocks(self, *texts):
        return [{'type': 'text', 'index': i, 'content': t}
                for i, t in enumerate(texts)]

    def test_all_success(self):
        res = M.translate_blocks(self._blocks("a", "b"), self.db, FakeTranslator())
        self.assertEqual(res, {0: "译文0", 1: "译文1"})
        self.assertEqual(self.db.get_pending_paragraphs(), [])

    def test_persistent_failure_falls_back_after_retries(self):
        # M2: 单个段落持续失败时，重试达 MAX_FAILED_ATTEMPTS 上限后用原文兜底
        # 并标记完成、告警（不再静默留 pending 导致重跑无限重试）。
        res = M.translate_blocks(self._blocks("a", "bad", "c"),
                                 self.db, FakeTranslator(fail=(1,)))
        self.assertEqual(res, {0: "译文0", 1: "bad", 2: "译文2"})
        self.assertEqual(self.db.get_pending_paragraphs(), [])

    def test_full_failure_falls_back_with_warning(self):
        # M2: API 整体故障时，不再静默回退原文，而是重试达上限后
        # 用原文兜底 + 标记完成（告警见日志），保证「遗漏段落有人工检查提示」。
        res = M.translate_blocks(self._blocks("a", "b", "c"),
                                 self.db, FakeTranslator(always_fail=True))
        self.assertEqual(res, {0: "a", 1: "b", 2: "c"})
        self.assertEqual(self.db.get_all_translations(), {0: "a", 1: "b", 2: "c"})
        self.assertEqual(self.db.get_pending_paragraphs(), [])

    def test_max_failed_attempts_forces_fallback(self):
        old = M.MAX_FAILED_ATTEMPTS
        M.MAX_FAILED_ATTEMPTS = 1
        self.addCleanup(lambda: setattr(M, "MAX_FAILED_ATTEMPTS", old))
        res = M.translate_blocks(self._blocks("a", "bad", "c"),
                                 self.db, FakeTranslator(fail=(1,)))
        # 失败 1 次即达阈值 → 用原文兜底并标记完成、告警
        self.assertEqual(res[1], "bad")
        self.assertEqual(self.db.get_all_translations(),
                         {0: "译文0", 1: "bad", 2: "译文2"})

    def test_transient_failure_recovers(self):
        class Flaky:
            def __init__(self):
                self.calls = 0

            def translate_numbered(self, chunk, label="") -> dict[int, str]:
                self.calls += 1
                out = {}
                for idx, text in chunk:
                    if idx == 1 and self.calls == 1:
                        continue  # 首次失败，之后恢复
                    out[idx] = f"译文{idx}"
                return out

        res = M.translate_blocks(self._blocks("a", "bad", "c"), self.db, Flaky())
        self.assertEqual(res, {0: "译文0", 1: "译文1", 2: "译文2"})
        self.assertEqual(self.db.get_pending_paragraphs(), [])


if __name__ == "__main__":
    unittest.main()
