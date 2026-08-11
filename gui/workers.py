"""
DeepScribe GUI — 后台工作线程。

每个文件以独立 Python 子进程运行流水线，环境变量与模块缓存完全隔离，
保证每次处理都读取最新 GUI 配置（不再依赖 importlib.reload 共享模块，
避免多文件并发互相污染）。

- 日志：子进程 stdout 逐行转发为 log 信号
- 进度：子进程 stdout 上的 JSON 标记行解析为 part_status 信号
- 取消：终止子进程树（taskkill /T），会真正停止 MinerU 与翻译，
  不再使用危险的 QThread.terminate()
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QObject

# 项目根（子进程 cwd / PYTHONPATH）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 子进程进度标记前缀（与 gui._runner.PROGRESS_PREFIX 保持一致）
_PROGRESS_PREFIX = "@@DS_PROGRESS@@ "


class Signals(QObject):
    file_status = Signal(str, str, object)
    part_status = Signal(str, int, str, object)
    log = Signal(str, str)
    finished = Signal(str, bool, str)


class ProcessWorker(QThread):
    """单文件处理线程：以子进程运行流水线。"""

    def __init__(self, pdf_path: Path, env: dict[str, str],
                 force: bool = False, parent=None):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)
        self.env = env
        self.force = force
        self.signals = Signals()
        self._cancel = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()

    # ============================================================
    # 取消
    # ============================================================
    def cancel(self):
        """请求取消：终止流水线子进程树（安全，会真正停止 MinerU/翻译）。

        非阻塞：taskkill / proc.wait 放到后台守护线程执行，避免 GUI 线程
        在"全部停止"多个文件时被同步阻塞。run() 线程在 stdout 读循环结束后
        自然退出并发送 finished 信号。
        """
        self._cancel.set()
        threading.Thread(target=self._kill_proc, daemon=True).start()

    def _kill_proc(self):
        # cancel 可能发生在子进程 spawn 之前：轮询等待 _proc 出现，
        # 避免 kill 线程在 proc 尚未赋值时误以为无需终止而漏杀。
        deadline = time.monotonic() + 5
        while True:
            with self._proc_lock:
                proc = self._proc
                if proc is not None:
                    self._proc = None
            if proc is not None or time.monotonic() > deadline:
                break
            time.sleep(0.05)
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=15,
                )
            else:
                proc.terminate()
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            proc.wait(timeout=10)
        except (OSError, subprocess.SubprocessError):
            proc.kill()

    def is_running(self) -> bool:
        # 用 QThread.isRunning() 而非自定义标志：start() 同步置位，避免
        # start() 返回后、run() 开始前 `_update_batch_buttons` 误判为未运行，
        # 导致"全部停止"按钮在任务运行期间保持禁用。
        return self.isRunning()

    # ============================================================
    # 线程主体
    # ============================================================
    def run(self):
        fp = str(self.pdf_path)
        try:
            # 子进程环境：继承当前 + 注入 GUI 配置（新进程天然拿到全部设置）
            env = os.environ.copy()
            env.update(self.env)
            root = _PROJECT_ROOT
            env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")

            cmd = [sys.executable, "-m", "gui._runner", fp, str(self.pdf_path.parent)]
            if self.force:
                cmd.append("--force")

            self.signals.file_status.emit(fp, "status", "parsing")
            self.signals.log.emit(fp, f"开始处理: {self.pdf_path.name}")

            if self._cancel.is_set():
                self.signals.file_status.emit(fp, "status", "cancelled")
                self.signals.log.emit(fp, "用户取消")
                self.signals.finished.emit(fp, False, "cancelled")
                return

            proc = subprocess.Popen(
                cmd,
                cwd=str(root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            with self._proc_lock:
                self._proc = proc

            # 逐行读取：进度标记 → part_status；其余 → 日志
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                if not line:
                    continue
                if line.startswith(_PROGRESS_PREFIX):
                    try:
                        data = json.loads(line[len(_PROGRESS_PREFIX):])
                        order = int(data.get("order", -1))
                        self.signals.part_status.emit(
                            fp, order, "title", data.get("title", ""))
                        self.signals.part_status.emit(
                            fp, order, "status", data.get("status", ""))
                    except (ValueError, TypeError, KeyError):
                        continue
                else:
                    self.signals.log.emit(fp, line)

            code = proc.wait()
            with self._proc_lock:
                if self._proc is proc:
                    self._proc = None

            if self._cancel.is_set():
                self.signals.file_status.emit(fp, "status", "cancelled")
                self.signals.log.emit(fp, "用户取消")
                self.signals.finished.emit(fp, False, "cancelled")
                return

            if code != 0:
                # 顶层异常已在 stdout 留下 traceback（stderr 合并到 stdout）
                self.signals.file_status.emit(fp, "status", "error")
                self.signals.log.emit(fp, f"处理失败（退出码 {code}），详见上方日志")
                self.signals.finished.emit(fp, False, f"流水线退出码 {code}")
                return

            self.signals.file_status.emit(fp, "status", "done")
            self.signals.log.emit(fp, f"处理完成: {self.pdf_path.stem}")
            self.signals.finished.emit(fp, True, "")

        except Exception as e:
            tb = traceback.format_exc()
            self.signals.log.emit(fp, f"错误:\n{tb}")
            self.signals.file_status.emit(fp, "status", "error")
            self.signals.finished.emit(fp, False, str(e))
