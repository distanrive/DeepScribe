"""
DeepScribe GUI — 子进程流水线运行器。

由 gui.workers.ProcessWorker 以独立 Python 进程启动，隔离环境变量与模块
缓存，保证每次处理都读取最新 GUI 配置；同时通过 stdout 上的 JSON 标记行
回传并行章节进度，其余输出作为日志转发到 GUI。

用法: python -m gui._runner <pdf_path> [output_dir] [--force]
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# 进度标记前缀（与 gui.workers._PROGRESS_PREFIX 保持一致）
PROGRESS_PREFIX = "@@DS_PROGRESS@@ "


def _progress_callback(order, status, title):
    print(PROGRESS_PREFIX + json.dumps(
        {"order": order, "status": status, "title": title},
        ensure_ascii=False,
    ), flush=True)


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
    # 子进程 sys.path 已含项目根（由 workers 设置 PYTHONPATH）
    import main as pipeline  # noqa: F401  # 项目根 main.py

    pdf_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else pdf_path.parent
    force = "--force" in sys.argv

    parallel = os.environ.get("ENABLE_PARALLEL", "false").lower() in ("true", "1", "yes")

    pipeline.process_pdf(
        pdf_path,
        output_dir,
        force=force,
        parallel=parallel,
        progress_callback=_progress_callback,
        mineru_lock=_make_mineru_lock(),
    )


if __name__ == "__main__":
    main()
