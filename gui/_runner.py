"""
DeepScribe GUI — 子进程流水线运行器。

由 gui.workers.ProcessWorker 以独立 Python 进程启动，隔离环境变量与模块
缓存，保证每次处理都读取最新 GUI 配置；同时通过 stdout 上的 JSON 标记行
回传并行章节进度，其余输出作为日志转发到 GUI。

本地日志：每次运行在项目根 logs/ 下写一份带时间戳的日志文件
（run_{stem}_{时间戳}.log），即使 GUI 闪退 / 远控断连也能留存排查。

用法: python -m gui._runner <pdf_path> [output_dir] [--force]
"""
import json
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

# 进度标记前缀（与 gui.workers._PROGRESS_PREFIX 保持一致）
PROGRESS_PREFIX = "@@DS_PROGRESS@@ "

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _log_file(pdf_path: Path) -> Path:
    """每个 PDF 一份带时间戳的本地日志，写到项目根 logs/ 目录。"""
    log_dir = _PROJECT_ROOT / "logs"
    ts = time.strftime("%Y%m%d_%H%M%S")
    return log_dir / f"run_{pdf_path.stem}_{ts}.log"


def _progress_callback(order, status, title):
    line = PROGRESS_PREFIX + json.dumps(
        {"order": order, "status": status, "title": title},
        ensure_ascii=False,
    )
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        # GUI 进程已退出（如远控断连），stdout 管道断开。进度改走本地日志，
        # 不中断流水线 —— 避免 BrokenPipeError 让整个翻译中途崩溃。
        logging.getLogger(__name__).info("进度 #%s %s: %s", order, status, title)


def _install_excepthook():
    """未捕获异常统一落到本地日志（+ 尽力回写 stderr 让 GUI 也能看到）。"""

    def _hook(tp, val, tb):
        text = "".join(traceback.format_exception(tp, val, tb))
        logging.getLogger("gui._runner").error("未捕获异常:\n%s", text)
        try:
            sys.stderr.write("未捕获异常:\n" + text)
            sys.stderr.flush()
        except (OSError, ValueError):
            pass

    sys.excepthook = _hook


def _make_mineru_lock():
    """跨进程 MinerU 全局并发限制；非 Windows 平台降级为无锁。"""
    try:
        from gui._gpu_lock import MineruSlotPool
    except ImportError:
        return None
    try:
        count = int(os.environ.get("MAX_PARALLEL_MINERU", "1"))
    except ValueError:
        count = 1
    slots_dir = Path(tempfile.gettempdir()) / "DeepScribe" / "mineru_slots"
    pool = MineruSlotPool(slots_dir, count)
    return pool.acquire


def main():
    pdf_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else pdf_path.parent
    force = "--force" in sys.argv
    parse_only = "--parse-only" in sys.argv

    # 本地持久化日志：必须在导入 main（其模块级 logger 初始化）之前注入，
    # utils._file_handler 才会读到该环境变量并挂载文件 handler。
    os.environ["DEEPSCRIBE_LOG_FILE"] = str(_log_file(pdf_path))

    # 子进程 sys.path 已含项目根（由 workers 设置 PYTHONPATH）
    import main as pipeline  # noqa: F401  # 项目根 main.py
    from utils import setup_logger

    _install_excepthook()
    logger = setup_logger("gui._runner")  # stdout（→ GUI）+ 文件（→ 本地日志）
    logger.info("流水线启动: %s (本地日志: %s)", pdf_path,
                os.environ["DEEPSCRIBE_LOG_FILE"])

    parallel = os.environ.get("ENABLE_PARALLEL", "false").lower() in ("true", "1", "yes")

    pipeline.process_pdf(
        pdf_path,
        output_dir,
        force=force,
        parallel=parallel,
        progress_callback=_progress_callback,
        mineru_lock=_make_mineru_lock(),
        parse_only=parse_only,
    )

    logger.info("流水线结束: %s", pdf_path)


if __name__ == "__main__":
    main()
