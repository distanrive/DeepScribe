import logging
import sys


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


def setup_logger(name=__name__):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger