import logging
import os
import sys
from pathlib import Path


def _force_utf8_stdio():
    """强制 stdout/stderr 使用 UTF-8（A3）。

    Windows 控制台默认 GBK 编码，且子进程 stdout 被 GUI 以 UTF-8 读取；
    两者不一致会导致中文日志乱码。统一为 UTF-8 后消除乱码。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


_force_utf8_stdio()

_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# 本地持久化日志文件路径（环境变量 DEEPSCRIBE_LOG_FILE 指定）。
# 设置后，所有模块日志除 stdout 外还会同时写入该文件（每条记录即时 flush），
# 用于 GUI 闪退 / 远控断连后排查问题。CLI 与 GUI 子进程默认不设置，
# 仅在需要落地日志时注入（见 gui/_runner.py 与 gui/main.py）。


def _file_handler() -> logging.Handler | None:
    path_str = os.getenv("DEEPSCRIBE_LOG_FILE")
    if not path_str:
        return None
    try:
        path = Path(path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        return handler
    except (OSError, ValueError):
        return None


_file_handler_attached = False


def _attach_file_handler_once() -> None:
    """把文件日志 handler 附加到 root logger（幂等，仅一次）。

    各模块 logger 默认 propagate=True，日志经各自 stdout handler 输出后
    会继续冒泡到 root，由这里的 FileHandler 统一写盘，避免每个模块
    logger 各挂一个文件 handler 造成重复行。
    """
    global _file_handler_attached
    if _file_handler_attached:
        return
    _file_handler_attached = True
    fh = _file_handler()
    if fh is not None:
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(fh)


def setup_logger(name=__name__):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(_LOG_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    _attach_file_handler_once()
    return logger