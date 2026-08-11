"""
DeepScribe GUI — 跨进程 MinerU 全局并发限制（GPU 显存保护）。

多个文件同时处理时，每个文件都可能运行 MinerU（GPU 密集型）。若并发数
超过显存预算会 OOM。本模块提供基于文件锁的计数信号量：在临时目录创建
MAX_PARALLEL_MINERU 个槽位文件，任何进程运行 MinerU 前必须先占用一个空闲
槽位。进程崩溃/退出时操作系统自动释放文件锁，不会留下死锁。

仅 Windows（使用 msvcrt）。其他平台由调用方（gui._runner）降级为无锁。
"""
import msvcrt
import time
from pathlib import Path


class _Slot:
    """已占用的槽位。退出 with 块或 release() 时释放锁。"""

    def __init__(self, fh):
        self._fh = fh

    def release(self):
        try:
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False


class MineruSlotPool:
    """跨进程计数信号量：slots_dir 下 N 个槽位文件，占用任一即可运行 MinerU。"""

    def __init__(self, slots_dir: Path, count: int):
        self._slots_dir = Path(slots_dir)
        self._count = max(1, int(count))
        self._slots_dir.mkdir(parents=True, exist_ok=True)
        for i in range(self._count):
            (self._slots_dir / f"slot{i}.lock").touch(exist_ok=True)

    def acquire(self, poll: float = 0.5):
        """阻塞直到获得一个槽位，返回 _Slot（可用作上下文管理器）。"""
        while True:
            for i in range(self._count):
                slot = self._try_lock(i)
                if slot is not None:
                    return slot
            time.sleep(poll)

    def _try_lock(self, i: int):
        path = self._slots_dir / f"slot{i}.lock"
        try:
            fh = open(path, "r+b")
        except OSError:
            return None
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            fh.close()
            return None
        return _Slot(fh)
