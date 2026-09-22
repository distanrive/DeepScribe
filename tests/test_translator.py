import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from translator import DeepSeekTranslator


class _FakeErr(Exception):
    """模拟 openai SDK 异常，仅暴露 status_code / headers 供退避逻辑读取。"""

    def __init__(self, status_code=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeTranslator(DeepSeekTranslator):
    """绕过 OpenAI 构造，用队列提供预设的 _call_api 返回值/异常。"""

    def __init__(self, responses):
        self._system_prompt = "SYS"
        self._responses = list(responses)
        self.calls = []

    def _call_api(self, system, user, retries=3, timeout=300):
        self.calls.append(user)
        if not self._responses:
            raise RuntimeError("模拟 API 无响应")
        r = self._responses.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r


class TestTranslateNumbered(unittest.TestCase):
    def test_split_by_markers(self):
        t = _FakeTranslator(["[BLK:0]\n译文0\n\n[BLK:1]\n译文1\n\n[BLK:2]\n译文2"])
        res = t.translate_numbered([(0, "a"), (1, "b"), (2, "c")])
        self.assertEqual(res, {0: "译文0", 1: "译文1", 2: "译文2"})

    def test_missing_marker_falls_back_per_block(self):
        # 首轮只返回 BLK:0，遗漏 1/2 → 逐段补译
        t = _FakeTranslator(["[BLK:0]\n译文0", "译文1", "译文2"])
        res = t.translate_numbered([(0, "a"), (1, "b"), (2, "c")])
        self.assertEqual(res, {0: "译文0", 1: "译文1", 2: "译文2"})

    def test_duplicate_marker_keeps_first(self):
        # L11: 重复 BLK 标记保留首次
        t = _FakeTranslator(["[BLK:0]\nfirst\n\n[BLK:0]\nsecond"])
        res = t.translate_numbered([(0, "a")])
        self.assertEqual(res, {0: "first"})

    def test_batch_failure_falls_back_per_block(self):
        # 全文一次调用失败 → 回退逐段翻译
        t = _FakeTranslator([RuntimeError("down"), "译文0", "译文1"])
        res = t.translate_numbered([(0, "a"), (1, "b")])
        self.assertEqual(res, {0: "译文0", 1: "译文1"})

    def test_persistent_failure_skips(self):
        # 全文失败且逐段也失败 → 跳过（保持未完成）
        t = _FakeTranslator([RuntimeError("down"), RuntimeError("down"), RuntimeError("down")])
        res = t.translate_numbered([(0, "a"), (1, "b")])
        self.assertEqual(res, {})

    def test_empty_translation_treated_as_missed(self):
        # 回归：标记后面什么都没有（模型漏写 / 被 max_tokens 截断）时，
        # 原实现把 '' 当成成功译文存下来 —— 那一段在 _zh.md 里变成空白，
        # 在 DB 里被标成 done，连 --force 都不会重译，原文段落静默消失。
        # 现在应当按遗漏处理，走逐段补译。
        t = _FakeTranslator(["[BLK:0]\n译文0\n\n[BLK:1]\n\n[BLK:2]\n译文2",
                             "补译1"])
        res = t.translate_numbered([(0, "a"), (1, "b"), (2, "c")])
        self.assertEqual(res, {0: "译文0", 1: "补译1", 2: "译文2"})

    def test_all_empty_translations_fall_back(self):
        # 全文每个标记后面都是空的 → 全部按遗漏走逐段补译
        t = _FakeTranslator(["[BLK:0]\n\n[BLK:1]\n", "补译0", "补译1"])
        res = t.translate_numbered([(0, "a"), (1, "b")])
        self.assertEqual(res, {0: "补译0", 1: "补译1"})

    def test_empty_single_block_response_retried(self):
        # 单段回退拿到空响应：抛 RuntimeError 并保持未完成（而不是记成空译文）
        t = _FakeTranslator([RuntimeError("full fail"), "", "重试后译文"])
        res = t.translate_numbered([(0, "a")])
        self.assertEqual(res, {})


class TestBackoff(unittest.TestCase):
    def test_retry_after_header(self):
        err = _FakeErr(status_code=429, headers={"Retry-After": "3"})
        self.assertEqual(DeepSeekTranslator._backoff_seconds(err, 0), 3.0)

    def test_rate_limit_exponential(self):
        self.assertEqual(DeepSeekTranslator._backoff_seconds(_FakeErr(status_code=429), 0), 10.0)
        self.assertEqual(DeepSeekTranslator._backoff_seconds(_FakeErr(status_code=429), 1), 20.0)

    def test_server_error_base(self):
        self.assertEqual(DeepSeekTranslator._backoff_seconds(_FakeErr(status_code=500), 0), 5.0)
        self.assertEqual(DeepSeekTranslator._backoff_seconds(_FakeErr(), 1), 10.0)


if __name__ == "__main__":
    unittest.main()
