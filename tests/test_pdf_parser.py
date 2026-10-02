"""`pdf_parser.py` 里两处与「MinerU 失败/超时」有关的修复的回归测试。

两件事都是用户报回来的：

1. **错误报告没法看** —— MinerU 崩了以后日志面板被几十行 tqdm 进度条刷屏，
   真正的那一行 `[TM][FATAL] core\\buffer.h(69): 'data_' Must be non NULL` 埋在中间。
2. **点了停止，「进程」还在跑** —— 超时用的是 `subprocess.run(timeout=…)`，
   它只 `TerminateProcess` 掉 `mineru.exe` 一个进程，**不会执行 MinerU 的 atexit**，
   于是 MinerU 自己拉起的 FastAPI 推理服务成了孤儿继续占显存；后续每次 MinerU
   都撞上它，表现为 `[TM][FATAL]` 连环失败。只有 `taskkill /T` 能沿着父子链收掉。
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdf_parser  # noqa: E402

# 一份逼真的 MinerU 日志：进度条与库 INFO 为主，中间夹着真正有用的那几行
_MINERU_LOG = "\n".join([
    "INFO:     Application startup complete.",
    "INFO:     Uvicorn running on http://127.0.0.1:10896 (Press CTRL+C to quit)",
    "Start MinerU FastAPI Service: http://127.0.0.1:10896",
    "Add dll path C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.6\\bin",
    "",
    "External Layout Extraction:  97%|\u2588\u2588| 432/447 [01:36<00:03,  4.13it/s]",
    "External Layout Extraction:  98%|\u2588\u2588| 439/447 [01:38<00:01,  3.92it/s]",
    "External Layout Extraction: 100%|\u2588\u2588| 447/447 [01:40<00:00,  4.47it/s]",
    "MFR Predict:  10%|\u2588\u2588        | 48/460 [04:27<39:16,  5.72s/it]",
    "MFR Predict:  66%|\u2588\u2588\u2588\u2588\u2588\u2588| 304/460 [21:18<08:13,  3.16s/it]",
    "[TM][FATAL] core\\buffer.h(69): 'data_' Must be non NULL",
    "Error: 1 task(s) failed while processing documents:",
]) + "\n"


class _FakeProc:
    """假 Popen：先抛若干次 TimeoutExpired，之后返回 returncode。"""

    def __init__(self, exits_after: int, returncode: int = 0):
        self.pid = 424242
        self.returncode = returncode
        self.calls = 0
        self._exits_after = exits_after

    def wait(self, timeout=None):
        self.calls += 1
        if timeout is None:
            return self.returncode                  # 禁用停滞检测时走的是这条
        if self.calls > self._exits_after:
            return self.returncode
        # **必须真的睡够**：真 Popen.wait(timeout=…) 是阻塞的，循环按 poll 计时才成立。
        # 立即抛异常会让循环空转，`idle` 涨得比写日志还快 —— 测试桩自己制造出假停滞。
        time.sleep(min(timeout, 0.05))
        raise subprocess.TimeoutExpired(cmd="mineru", timeout=timeout)


class TestStallTimeout(unittest.TestCase):
    """超时要量「有没有新输出」，不是量「总用时」。

    用户报回来的原话是「超时时间设置的意义在哪里」—— 现场日志显示那一章
    **所有阶段都跑到 100%** 了（MFR Predict 460/460、OCR-rec 68/68），
    只差最后落盘就被 1800 秒的墙钟上限杀掉，白烧半小时 GPU。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "mineru.log"
        self.log_path.write_text("start\n", encoding="utf-8")

    def test_disabled_waits_forever(self):
        proc = _FakeProc(exits_after=0)
        self.assertEqual(pdf_parser._wait_for_mineru(proc, self.log_path, 0), 0)
        self.assertEqual(proc.calls, 1, "0 = 禁用时应当只调一次无超时的 wait()")

    def test_exits_normally(self):
        proc = _FakeProc(exits_after=2)
        self.assertEqual(
            pdf_parser._wait_for_mineru(proc, self.log_path, 60, poll=0.01), 0)

    def test_stalls_when_nothing_is_written(self):
        proc = _FakeProc(exits_after=10_000)
        with self.assertRaises(pdf_parser.MineruStalledError):
            pdf_parser._wait_for_mineru(proc, self.log_path, 0.2, poll=0.02)

    def test_progress_keeps_it_alive(self):
        """仍在吐进度就绝不判卡死 —— 哪怕已经跑了很久（慢 ≠ 卡）。"""
        stop = threading.Event()

        def writer():
            while not stop.is_set():
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write("MFR Predict: 10%|##| 46/460\r")
                time.sleep(0.005)

        t = threading.Thread(target=writer, daemon=True)
        t.start()
        try:
            # stall=0.2 / poll=0.02：若按「有没有新输出」判，永远不会触发；
            # 若误按「总用时」判，跑到第 11 次 wait 就会被杀掉。
            proc = _FakeProc(exits_after=40)
            self.assertEqual(
                pdf_parser._wait_for_mineru(proc, self.log_path, 0.2, poll=0.02), 0)
        finally:
            stop.set()
            t.join(timeout=5)

    def test_transient_read_error_does_not_trip(self):
        """偶发读不到日志（杀软占用之类）不该被判成卡死。"""
        stop = threading.Event()

        def churn():
            i = 0
            while not stop.is_set():
                try:
                    self.log_path.write_text("x" * (10 + i), encoding="utf-8")
                    i += 1
                except OSError:
                    pass
                time.sleep(0.01)

        t = threading.Thread(target=churn, daemon=True)
        t.start()
        try:
            proc = _FakeProc(exits_after=8)
            self.assertEqual(
                pdf_parser._wait_for_mineru(proc, self.log_path, 0.2, poll=0.02), 0)
        finally:
            stop.set()
            t.join(timeout=5)


class TestLogTailIsReadable(unittest.TestCase):
    """失败时要报的是「有用的那几行」，不是把进度条整个刷进界面。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "mineru_x.log"
        self.log_path.write_text(_MINERU_LOG, encoding="utf-8")
        patcher = mock.patch.object(pdf_parser.logger, "error")
        self.error = patcher.start()
        self.addCleanup(patcher.stop)

    def _lines(self) -> list[str]:
        return [c.args[0] for c in self.error.call_args_list if c.args]

    def test_keeps_the_actual_crash_line(self):
        pdf_parser._log_tail(self.log_path)
        self.assertTrue(
            any("'data_' Must be non NULL" in ln for ln in self._lines()),
            "真正有用的崩溃行没被报出来：\n" + "\n".join(self._lines()))

    def test_drops_progress_bars(self):
        pdf_parser._log_tail(self.log_path)
        offenders = [ln for ln in self._lines() if "%|" in ln]
        self.assertEqual(offenders, [],
                         "进度条被当成错误刷出来了（一次失败几十行红字）：\n"
                         + "\n".join(offenders))

    def test_stays_short(self):
        pdf_parser._log_tail(self.log_path)
        # max_lines(12) + 末尾那行「完整日志: …」
        self.assertLessEqual(len(self._lines()), 13,
                             "报出来的行数没有收敛")

    def test_points_at_the_full_log(self):
        pdf_parser._log_tail(self.log_path)
        self.assertTrue(any(str(self.log_path) in ln for ln in self._lines()),
                        "没给出完整日志路径 —— 要看全的就没地方看了")

    def test_handles_carriage_return_progress(self):
        """tqdm 用 `\\r` 原地刷新：整条进度可能只由一个 `\\n` 分隔。"""
        path = Path(self._tmp.name) / "cr.log"
        path.write_text(
            "MFR Predict:   0%|  | 0/460\rMFR Predict:  50%|**| 230/460\r"
            "MFR Predict: 100%|**| 460/460\nSomething failed: boom\n",
            encoding="utf-8")
        self.error.reset_mock()
        pdf_parser._log_tail(path)
        lines = self._lines()
        self.assertTrue(any("boom" in ln for ln in lines))
        self.assertFalse(any("%|" in ln for ln in lines))

    def test_falls_back_when_nothing_looks_like_an_error(self):
        path = Path(self._tmp.name) / "quiet.log"
        path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        self.error.reset_mock()
        pdf_parser._log_tail(path)
        self.assertEqual(self._lines()[:3], ["alpha", "beta", "gamma"])

    def test_missing_file_is_not_fatal(self):
        pdf_parser._log_tail(Path(self._tmp.name) / "nope.log")
        self.assertEqual(self._lines(), [])


@unittest.skipUnless(os.name == "nt", "taskkill /T 只在 Windows 上有意义")
class TestKillProcessTree(unittest.TestCase):
    """超时必须收掉整棵进程树，否则 MinerU 的推理服务会变孤儿继续占显存。"""

    def setUp(self):
        self._pids: list[int] = []

    def tearDown(self):
        for pid in self._pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True).stdout
        return str(pid) in out

    def test_kills_grandchild_like_mineru_service(self):
        # 父进程再拉起一个孙进程 —— 就是 mineru.exe → FastAPI 服务那层关系
        code = (
            "import subprocess, sys, time\n"
            "child = subprocess.Popen("
            "[sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(120)\n"
        )
        parent = subprocess.Popen([sys.executable, "-c", code],
                                  stdout=subprocess.PIPE, text=True)
        self.addCleanup(parent.stdout.close)
        self._pids.append(parent.pid)
        grandchild = int(parent.stdout.readline().strip())
        self._pids.append(grandchild)
        self.assertTrue(self._alive(grandchild), "孙进程没起来，测试前提不成立")

        pdf_parser._kill_process_tree(parent.pid)
        parent.wait(timeout=30)
        for _ in range(100):
            if not self._alive(grandchild):
                break
            time.sleep(0.1)
        self.assertFalse(
            self._alive(grandchild),
            "孙进程还活着 —— 说明没收整棵树（taskkill 少了 /T，或者退回了 "
            "Popen.kill()）。MinerU 的推理服务就是这么变成孤儿、继续占显存的。")

    def test_missing_pid_is_not_fatal(self):
        pdf_parser._kill_process_tree(0)        # 不该抛
        pdf_parser._kill_process_tree(999999)   # 不存在的 pid 也不该抛


if __name__ == "__main__":
    unittest.main()
