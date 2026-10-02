import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from utils import setup_logger
from config import MINERU_STALL_TIMEOUT, MINERU_EFFORT

logger = setup_logger(__name__)

# Windows 下阻止 mineru.exe（控制台程序）在 GUI 中弹出命令行窗口；
# 其他平台无此常量，回退为 0（无副作用）。
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# tqdm 进度条：`External Layout Extraction:  97%|████ | 432/447 [01:36<00:03]`
_PROGRESS_RE = re.compile(r"\d+%\|")
# 值得单独报出来的行（真正的崩溃/报错线索）
_ERROR_HINT_RE = re.compile(
    r"fatal|error|traceback|exception|failed|failure|"
    r"失败|cannot|can't|no such|not found|must be|out of memory|\boom\b",
    re.I)
_MAX_LINE_CHARS = 300       # 单行截断长度：有些库会把整段堆栈塞进一行


class MineruStalledError(RuntimeError):
    """MinerU 长时间没有任何新输出（判定卡死），其进程树已被终止。"""


def _wait_for_mineru(proc: subprocess.Popen, log_path: Path,
                     stall_seconds: int, poll: float = 10.0) -> int:
    """等 MinerU 结束；**只在「连续 stall_seconds 秒没有任何新输出」时判定卡死**。

    为什么不是「总用时超过 N 秒就杀」：那个数字分不清「卡死」和「就是慢」。
    实测一本 480 页的书里各章耗时 3 分钟 ~ 30+ 分钟不等，任何固定墙钟上限对某些章
    都必然是错的 —— 而误杀的代价是白烧半小时 GPU，还会留下占着内存的孤儿进程。
    反之，MinerU 只要在干活就一直在吐进度（一章能刷 400 多次），所以「长时间完全
    没有输出」才是可靠的卡死信号。

    `stall_seconds <= 0` = 禁用，一直等到进程自己退出。
    """
    if stall_seconds <= 0:
        return proc.wait()

    def _size() -> int:
        try:
            return log_path.stat().st_size
        except OSError:
            # 读不到时返回 -1：与上次的正数不同 ⇒ 当成「有变化」重置计时（偶发的
            # 杀软占用不该被判成卡死）；**一直**读不到（文件被删/损坏）则 -1 == -1，
            # 会累计成停滞 —— 那种情况下确实没有「在干活」的证据，杀掉是对的。
            return -1

    last = _size()
    idle = 0.0
    while True:
        try:
            return proc.wait(timeout=poll)
        except subprocess.TimeoutExpired:
            pass
        current = _size()
        if current != last:
            last = current
            idle = 0.0
            continue
        idle += poll
        if idle >= stall_seconds:
            raise MineruStalledError(
                f"MinerU 连续 {stall_seconds:g}s 没有任何新输出，判定卡死"
                f"（日志: {log_path}）")


def _kill_process_tree(pid: int) -> None:
    """杀掉一棵进程树。

    **为什么不能只 kill 直接子进程**：MinerU 的客户端会把它的 FastAPI 推理服务作为
    **独立子进程**拉起来（`mineru/cli/api_client.py`：`subprocess.Popen` +
    `CREATE_NEW_PROCESS_GROUP`），并靠 `atexit` 收尾。而 `TerminateProcess`
    （`Popen.kill()`，也就是 `subprocess.run(timeout=…)` 超时后干的事）**不会执行
    atexit** —— 那个服务就成了孤儿，继续占着显存。后续每次 MinerU 都会撞上它，
    表现为 `[TM][FATAL] core\\buffer.h(69): 'data_' Must be non NULL` 连环失败，
    以及用户看到的「点了停止，显存还在跑，只能手动删进程」。

    只有 `taskkill /T` 才沿着父子链把它一起收掉。（后端杀 worker 时用的也是
    `/T`，所以那条路径没问题；**会漏的只有这里的超时路径**。）
    """
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW, timeout=30)
        else:
            os.killpg(os.getpgid(pid), 15)
    except (OSError, subprocess.SubprocessError):
        pass                    # 尽力而为：进程可能已经自己退了


def _find_mineru_exe() -> str:
    """定位 mineru 可执行文件。

    优先用 PATH 查找（CLI 在已激活的 conda 环境中运行）。GUI 子进程以
    pythonw.exe 直接启动时 PATH 不含 env 的 Scripts 目录，此时兜底到与
    当前 Python 同一 conda 环境下的 Scripts/mineru.exe。
    """
    exe = shutil.which("mineru")
    if exe:
        return exe
    candidate = Path(sys.executable).resolve().parent / "Scripts" / "mineru.exe"
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError(
        "未找到 mineru 可执行文件。请确认已安装 mineru，并通过 "
        "`conda activate deepscribe` 激活环境后运行。"
    )


def _log_tail(path: Path, max_lines: int = 12):
    """把 MinerU 日志里**有用的那几行**挑出来报一次，并给出完整日志路径。

    **直接 tail 末尾 N 行是不行的**，两个毛病：

    1. MinerU 的输出里绝大多数是 tqdm 进度条和第三方库的 INFO，真正的崩溃行
       （例如 `[TM][FATAL] core\\buffer.h(69): 'data_' Must be non NULL`）会被埋掉
       —— 而那一行才是唯一有用的信息；
    2. 这些行是**逐行** `logger.error()` 出去的，一次失败就变成几十条 ERROR 刷进
       日志面板（每条还会被后端当成独立事件广播一次），把界面冲得看不见别的。

    所以：按 `\\r` 和 `\\n` 都切开（tqdm 用 `\\r` 原地刷新，整条进度可能只由
    一个 `\\n` 分隔），丢掉进度条与空行，**优先保留像报错的那几行**；
    一行都挑不出来时才退回最后几行正文。末尾一定附上完整日志路径 ——
    要看全的就去看文件，别把几千行刷进界面。
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    segments = [s.strip() for s in re.split(r"[\r\n]+", raw)]
    lines = [s for s in segments if s and not _PROGRESS_RE.search(s)]

    picked = [ln for ln in lines if _ERROR_HINT_RE.search(ln)][-max_lines:]
    if not picked:
        picked = lines[-max_lines:]

    # 去重（保留靠后的、也就是更接近崩溃现场的那次），再按时间顺序打出来
    unique: list[str] = []
    for ln in reversed(picked):
        if ln not in unique:
            unique.append(ln)
    for ln in reversed(unique):
        logger.error(ln[:_MAX_LINE_CHARS])
    logger.error(f"MinerU 完整日志: {path}")


def run_mineru(pdf_path: Path, output_dir: Path, backend: str = "pipeline",
               short_stem: str | None = None) -> tuple[Path, Path]:
    """
    运行 MinerU，返回 (md_path, images_dir)。

    MinerU 内部分析文件名创建深层目录结构，长文件名可能触发 Windows
    MAX_PATH (260) 限制。始终用短名副本传给 MinerU，调用完毕后自动清理。

    MinerU 输出结构：
        output_dir/<short_stem>/auto/<short_stem>.md
        output_dir/<short_stem>/auto/images/

    short_stem: 覆盖默认短名。**调用方必须传这个值**，只要 pdf_path 不是
    原始 PDF 本身（例如加密 PDF 解密后的副本）—— 默认短名取自
    `pdf_path.resolve()`，传副本进来算出的短名与上层 `_stem` 不一致，
    上层按 `_stem` 探测 MinerU 缓存就会永远落空，每次运行都重解析。
    None 时按 pdf_path 计算（与上层 `_stem` 同源的普通情形）。

    stdout/stderr 重定向到 {output_dir}/mineru_{short_stem}.log。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 始终用短名副本：SHA256 前 12 位 hex，~15 字符，远低于 MAX_PATH
    # 哈希输入含完整路径：不同目录下同名 PDF 互不踩踏临时副本 / 输出目录
    if short_stem is None:
        short_stem = "_" + hashlib.sha256(str(pdf_path.resolve()).encode()).hexdigest()[:12]
    temp_pdf = output_dir / f"{short_stem}.pdf"
    shutil.copy2(pdf_path, temp_pdf)
    logger.info(f"临时副本: {temp_pdf}  ← {pdf_path}")

    log_path = output_dir / f"mineru_{short_stem}.log"
    cmd = [
        _find_mineru_exe(),
        "-p", str(temp_pdf),
        "-o", str(output_dir),
        "-b", backend,
    ]
    if backend.startswith("hybrid"):
        cmd += ["--effort", MINERU_EFFORT]
    logger.info(f"Running MinerU: {' '.join(cmd)}")
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as logf:
            # 用 Popen 而不是 subprocess.run：**超时时必须拿到 pid 才能杀整棵进程树**，
            # 而 TimeoutExpired 不带 pid（run() 内部已经用 TerminateProcess 杀过
            # mineru.exe 了，那一下恰恰会漏掉它拉起的推理服务，见 _kill_process_tree）。
            proc = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_CREATE_NO_WINDOW,
                start_new_session=True,      # 非 Windows 上让 killpg 只打到 MinerU 这棵树
            )
            try:
                returncode = _wait_for_mineru(proc, log_path, MINERU_STALL_TIMEOUT)
            except MineruStalledError as exc:
                logger.error(f"{exc}；终止整棵进程树 pid={proc.pid}")
                _kill_process_tree(proc.pid)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    logger.error(f"进程树 pid={proc.pid} 仍未退出")
                _log_tail(log_path)
                raise
        if returncode != 0:
            logger.error(f"MinerU failed with return code {returncode}")
            _log_tail(log_path)
            raise subprocess.CalledProcessError(returncode, cmd)
    finally:
        try:
            temp_pdf.unlink()
        except OSError:
            pass

    # 查找 MD：pipeline 输出在 auto/，hybrid-engine 输出在 hybrid_auto/
    md_path = output_dir / short_stem / "auto" / f"{short_stem}.md"
    hybrid_md_path = output_dir / short_stem / "hybrid_auto" / f"{short_stem}.md"
    if not md_path.exists() and not hybrid_md_path.exists():
        stem_dir = output_dir / short_stem
        candidates = sorted(stem_dir.rglob("*.md")) if stem_dir.is_dir() else []
        if not candidates:
            candidates = sorted(output_dir.rglob("*.md"))
        if candidates:
            md_path = candidates[0]
        else:
            raise FileNotFoundError(f"MinerU 未生成 .md 文件于 {output_dir}")
    elif hybrid_md_path.exists():
        md_path = hybrid_md_path
    # else: md_path already points to auto variant

    # 查找 images 目录
    images_dir = md_path.parent / "images"
    if not images_dir.is_dir():
        candidates = sorted(output_dir.rglob("images"))
        images_dir = candidates[0] if candidates else md_path.parent

    logger.info(f"MinerU 输出: md={md_path}, images={images_dir}")
    return md_path, images_dir
