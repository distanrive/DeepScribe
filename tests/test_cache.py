"""`dsctl/cache.py` 的单元测试。

**每个用例都把缓存根顶替成自己的临时目录**（`mock.patch.object`），绝不碰真实缓存
——真缓存里装着用户几百 MB 的解析结果和翻译进度，删了就白花钱重跑。
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dsctl import cache


class _CacheTestCase(unittest.TestCase):
    """把 `cache.CACHE_ROOT` 指到一个空的临时目录上。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "DeepScribe"
        self.root.mkdir()
        patcher = mock.patch.object(cache, "CACHE_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, rel: str, content: bytes = b"x") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path


class TestCacheSize(_CacheTestCase):
    def test_counts_nested_files(self):
        self._write("_abc_mineru/auto/_abc.md", b"12345")       # 5 字节
        self._write("_abc_translate.db", b"123")                 # 3 字节
        self.assertEqual(cache.cache_size(), (8, 2))

    def test_empty_root(self):
        self.assertEqual(cache.cache_size(), (0, 0))

    def test_missing_root(self):
        # 缓存目录还不存在（一次都没跑过）——不该报错，报 0 就行
        with mock.patch.object(cache, "CACHE_ROOT", self.root / "not_there"):
            self.assertEqual(cache.cache_size(), (0, 0))

    def test_slots_dir_is_not_cache(self):
        """并发锁槽位不算缓存：它是锁表不是中间产物，删了会让并发上限失效。"""
        self._write("_abc_translate.db", b"123")
        self._write(f"{cache.SLOTS_DIRNAME}/slot0.lock", b"")
        self.assertEqual(cache.cache_size(), (3, 1))


class TestClearCache(_CacheTestCase):
    def test_clears_entries_and_keeps_root(self):
        self._write("_abc_mineru/auto/_abc.md", b"12345")
        self._write("_abc_translate.db", b"123")
        freed, errors = cache.clear_cache()
        self.assertEqual(errors, [])
        self.assertEqual(freed, 8)
        self.assertTrue(self.root.is_dir(), "缓存根目录本身要留着（下次运行会自己重建）")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_keeps_slots_dir(self):
        self._write(f"{cache.SLOTS_DIRNAME}/slot0.lock", b"")
        self._write("_abc_translate.db", b"123")
        freed, _ = cache.clear_cache()
        self.assertEqual(freed, 3)
        self.assertTrue((self.root / cache.SLOTS_DIRNAME).is_dir(),
                        "槽位锁表必须留着 —— 删掉正在用的槽位文件会让并发限制失效")

    def test_missing_root(self):
        with mock.patch.object(cache, "CACHE_ROOT", self.root / "not_there"):
            self.assertEqual(cache.clear_cache(), (0, []))

    def test_reports_items_it_could_not_delete(self):
        """删不掉的条目要**报出来**（Windows 上文件被占用是常态），不能假装清干净了。"""
        self._write("_locked_mineru/a.md", b"12")
        real_rmtree = shutil.rmtree

        def _boom(path, *a, **kw):
            if Path(path).name == "_locked_mineru":
                raise PermissionError(13, "另一个进程正在使用此文件")
            return real_rmtree(path, *a, **kw)

        with mock.patch.object(cache.shutil, "rmtree", _boom):
            freed, errors = cache.clear_cache()
        self.assertEqual(freed, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("_locked_mineru", errors[0])
        self.assertIn("另一个进程正在使用", errors[0])
        self.assertTrue((self.root / "_locked_mineru").is_dir(), "没删掉的目录要原样留着")


class TestMeasureIsNotPerFile(_CacheTestCase):
    """统计**不许**对每个文件单独 `Path.stat()`。

    这是性能要求，不是风格洁癖：`Path.rglob()` + `Path.stat()` 对每个文件都要单独发
    一次系统调用，而缓存目录在 Windows 的 `%TEMP%` 下 —— 那个目录有杀软实时扫描，
    每个文件的「打开一次」都要过一遍过滤驱动，几千个文件就是好几秒（用户报过
    「统计要等好几秒才出结果」）。`os.scandir()` 的 `DirEntry.stat()` 在 Windows 上
    直接返回目录枚举（`FindNextFile`）里已经带回来的大小，**一个文件都不用打开**。

    实测（2610 个文件）：rglob 94ms / os.walk 45ms / os.scandir 9ms。

    断言方式：数 `Path.stat` 的调用次数 —— 它应当只跟**顶层条目数**有关，
    跟树里的文件总数无关。
    """

    def _stat_calls(self, n_files: int) -> int:
        """同样的目录结构、只改图片数量，返回本次统计里 `Path.stat` 的调用次数。

        注意 Python 3.10 的 `Path.is_dir()` / `is_file()` 内部就是 `self.stat()`，
        所以它们也会被计进来 —— 没关系，那部分是**每个顶层条目**几次，与文件数无关。
        """
        self._write("_top.db", b"x")
        for i in range(n_files):
            self._write(f"_big_mineru/images/image-{i}.jpg", b"x" * 10)
        calls: list[int] = []
        real_stat = Path.stat

        def counting_stat(path_self, *a, **kw):
            calls.append(1)
            return real_stat(path_self, *a, **kw)

        with mock.patch.object(Path, "stat", counting_stat):
            cache.cache_size()
        shutil.rmtree(self.root / "_big_mineru")
        return len(calls)

    def test_stat_calls_do_not_grow_with_file_count(self):
        few = self._stat_calls(10)
        many = self._stat_calls(60)
        self.assertEqual(
            few, many,
            f"文件数 10 → 60 时 Path.stat 调用从 {few} 涨到 {many}：说明统计是「每个文件"
            "一次系统调用」。Windows 的 %TEMP% 有杀软实时扫描，每个文件都要过一遍过滤"
            "驱动，几千个文件就是好几秒。应当换回 os.scandir（大小直接来自目录枚举）。")
        self.assertLess(few, 10, f"顶层才 2 个条目，却调了 {few} 次 stat")

    def test_nested_dirs_are_counted(self):
        self._write("_a_mineru/x/y/z/deep.md", b"12345")
        self.assertEqual(cache.cache_size(), (5, 1), "深层嵌套的目录也要算进去")


class TestCacheRootLocation(unittest.TestCase):
    """缓存根 = **系统临时目录**下的 `DeepScribe/`。

    钉住「用 `tempfile.gettempdir()` 而不是自己拼 `%TEMP%` / `/tmp`」这条约定 ——
    自己拼在换机器 / 换平台 / 用户改过 TEMP 时会静默跑到别的目录去，
    表现出来是「清了缓存但下一次仍然很快」这种查不出原因的怪事。
    """

    def test_under_system_temp_dir(self):
        self.assertEqual(cache.CACHE_ROOT, Path(tempfile.gettempdir()) / "DeepScribe")

    def test_not_hardcoded(self):
        # 路径里不许出现写死的盘符或 /tmp（只允许来自 gettempdir()）
        text = (Path(__file__).resolve().parent.parent / "dsctl" / "cache.py").read_text(
            encoding="utf-8")
        for bad in ('"C:\\\\', "'C:\\\\", '"/tmp', "'/tmp"):
            self.assertNotIn(bad, text, "缓存路径被写死了，应该只用 tempfile.gettempdir()")


if __name__ == "__main__":
    unittest.main()
