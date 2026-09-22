"""DeepScribe Godot GUI — WebSocket 后端。

与 Godot 前端（`scripts/autoload/net_client.gd` 单例 NetClient）通过 JSON 文本帧通信。
本进程**只做三件事**，不亲自跑流水线：

    1) 是 config.json（含 DPAPI 加密的 API Key）的唯一持有者；
    2) 每个 PDF 拉起一个 `dsctl.worker` **子进程**跑流水线，把它的 stdout 转成事件广播出去；
    3) 转发取消命令（`taskkill /T /F` 杀整棵进程树，MinerU 一起停）。

为什么不用线程在进程内跑流水线：`translator.py` / `pdf_parser.py` 在**模块级**
绑定 config 常量，同进程里多文件并发会互相污染；而且 `dsctl/gpu_lock.py` 是
跨进程文件信号量、`taskkill /T` 也只能作用在真进程树上。子进程隔离三样全都解决。

启动：
    python backend/main.py                     # 默认 127.0.0.1:8765
    python backend/main.py --port 9000         # 换端口
    python backend/main.py --log-file x.log    # 日志另存一份

通常**不用手动启动**：前端连不上会由 `BackendLauncher` 自动拉起本文件，
并传 `--host/--port/--log-file` —— 这三个参数别删（argparse 会报 unrecognized arguments）。

## 关于开头这段 stdio 自导

Godot 的 `OS.create_process()` 起进程时**不给子进程可用的 stdio 句柄**。上一次
迁移尝试报告过：在这种状态下 Python 导入 `ssl`（`websockets` 会连带导入）会
**永久挂起**，表现为「后端已拉起、端口却永远不监听」。

> 实测记录（Python 3.10.20 / 本机）：用 ctypes 按 `STARTF_USESTDHANDLES` + 三个
> NULL 句柄起进程，以及用 pythonw 起进程让它继承无效句柄，**两种情况下 `import ssl`
> 都不挂** —— 也就是说这个挂起在本机没能复现，触发条件仍不明确（可能与具体
> Godot / Python / 驱动版本有关）。见 `tools/check_detached_stdio.py`。

即便如此这段保留，理由有二，都与「挂起」无关地成立：

1. **代价为零**：几十行、只在 stdio 不可用时生效；
2. **日志文件是硬需求**：脱离进程的 stdout 没人接，出问题时前端只能靠读
   `--log-file` 的尾部才能告诉用户「后端为什么没起来」。自导之后 fd 1 就是那个
   文件，等于把「起不来」的第一现场钉死。

所以：`_redirect_stdio_early()` 仍是本模块**第一段可执行代码**，早于任何第三方
import（`import websockets` 尤其不能在它前面）；判定用「实际可用性」而不是猜句柄
状态（见 `_stdio_seems_usable`），并且 `log()` 自己永不抛异常兜底。

回归验证（不需要开 Godot）：`python godot_gui/tools/check_detached_stdio.py`
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------- 1. stdio 自导
# 这一段只能用到 os / sys —— 它们在解释器启动时就已经加载，不会触发任何 import 机制。


def _flag_value(name: str) -> str:
    """从 argv 里取 `--name=value` 或 `--name value`。不 import argparse（保持极简）。"""
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg.startswith(name + "="):
            return arg[len(name) + 1:]
        if arg == name and i + 1 < len(argv):
            return argv[i + 1]
    return ""


def _fd_alive(fd: int) -> bool:
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False


def _stdio_seems_usable() -> bool:
    """stdio 能不能用：三个信号全都过才算可用。

    单看 `sys.stdout is None` 是不够的 —— 句柄可能是「非 NULL 但指向一个坏掉的
    管道/无效内核对象」，那种情况下 `sys.stdout` 存在、`print` 才在第一次 flush
    时炸。所以这里补一个**真写一次**的功能测试。
    """
    if sys.stdout is None or sys.stderr is None:
        return False
    if not _fd_alive(1) or not _fd_alive(2):
        return False
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        return True
    except (OSError, ValueError):
        return False


def _redirect_stdio_early(log_path: str) -> bool:
    """把 fd 0/1/2 接到日志文件上，返回是否真的接管了。

    只在 stdio **不可用**时接管；从终端手动运行时不动它（否则用户在终端里
    什么都看不到），那种情况下日志由 `log()` 的 `_log_handle` 落到文件 ——
    两条路径都保证日志文件一定有内容。
    """
    if not log_path:
        return False
    if _stdio_seems_usable():
        return False
    try:
        parent = os.path.dirname(os.path.abspath(log_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        # 追加，不是覆盖：前端反复重启后端时日志要连着看
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        os.close(fd)
        # stdin 接到空设备：句柄无效时任何 input()/读 stdin 都会直接报错或卡住
        os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
        sys.stdin = open(0, "r", encoding="utf-8", errors="replace")
        sys.stdout = open(1, "w", encoding="utf-8", errors="replace", buffering=1)
        sys.stderr = open(2, "w", encoding="utf-8", errors="replace", buffering=1)
        return True
    except OSError:
        return False


_LOG_PATH = _flag_value("--log-file")
_STDIO_TAKEN_OVER = _redirect_stdio_early(_LOG_PATH)

# ---------------------------------------------------------------- 2. 常规 import
# 到这里 stdio 已经安全，再导入 websockets（→ ssl）就不会挂起。

import argparse  # noqa: E402
import asyncio  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import websockets  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dsctl.config_store import ConfigManager  # noqa: E402
from dsctl.worker import PROGRESS_PREFIX  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SERVER_NAME = "deepscribe-backend"
BACKEND_VERSION = "1.0"
MAX_LOG_BYTES = 2 * 1024 * 1024
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# utils.py 的日志格式；子进程 stdout 上的日志行按它解析级别
_LOG_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} [\d,:]+ - (\w+) - (.*)$", re.S)

_log_handle = None


# ---------------------------------------------------------------- 日志

def log(message: str = "") -> None:
    """写一行日志。

    **这个函数不允许抛异常**：stdio 判断再保守也可能在古怪环境下判错，
    而日志写不进去绝不该让后端崩掉。写终端和写文件各包一层。
    """
    try:
        print(message, flush=True)
    except (OSError, ValueError, AttributeError):
        pass
    if _log_handle is not None:
        try:
            _log_handle.write(message + "\n")
            _log_handle.flush()
        except OSError:
            pass


def open_log_file(path: str) -> None:
    """stdio 没被接管时，自己开一个日志文件句柄。"""
    global _log_handle
    if not path or _STDIO_TAKEN_OVER:
        return
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.isfile(path) and os.path.getsize(path) > MAX_LOG_BYTES:
            os.replace(path, path + ".old")
        _log_handle = open(path, "a", encoding="utf-8", buffering=1)
    except OSError as exc:
        print(f"[backend] 无法写入日志文件 {path}：{exc}", file=sys.stderr)


def close_log_file() -> None:
    global _log_handle
    if _log_handle is not None:
        try:
            _log_handle.close()
        except OSError:
            pass
        _log_handle = None


def read_version() -> str:
    try:
        return (PROJECT_ROOT / "version").read_text(encoding="utf-8").strip()
    except OSError:
        return "v0.0.0"


# ---------------------------------------------------------------- 配置
# 白名单：前端只能改这些键，且值类型由这里定。挡住「GUI 手滑把 config.json 写坏」
# 这类事故 —— 配置文件是 CLI 与 GUI 共用的。

_CONFIG_SCHEMA: dict[str, tuple[str, type]] = {
    "api.model": ("api", str),
    "api.reasoning_effort": ("api", str),
    "api.use_thinking": ("api", bool),
    "api.base_url": ("api", str),
    "parser.backend": ("parser", str),
    "parser.effort": ("parser", str),
    "parser.timeout": ("parser", int),
    "parallel.enable": ("parallel", bool),
    "parallel.max_workers": ("parallel", int),
    "parallel.max_mineru": ("parallel", int),
    "parallel.max_chapter_pages": ("parallel", int),
    "translation.max_tokens": ("translation", int),
    "translation.temperature": ("translation", float),
    "translation.target_tokens_per_call": ("translation", int),
    "translation.max_paras_per_call": ("translation", int),
    "translation.min_marker_retention": ("translation", float),
    "translation.enable_integrity": ("translation", bool),
}


def coerce(kind: type, value):
    """按 schema 的类型转换；转不动就抛 ValueError（由调用方报给前端）。"""
    if kind is bool:
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "on")
        return bool(value)
    if kind is int:
        return int(value)
    if kind is float:
        return float(value)
    return str(value)


def load_config() -> ConfigManager:
    """每次现读一份 —— 用户可能刚在 Godot 界面上保存过，也可能是外部改的。"""
    return ConfigManager(PROJECT_ROOT / "config.json")


def config_payload(cfg: ConfigManager) -> dict:
    """给前端的配置快照。**API Key 明文永不出后端**，只回「有没有 / 能不能解密」。"""
    data = {}
    for key, (section, _kind) in _CONFIG_SCHEMA.items():
        _, field = key.split(".", 1)
        data.setdefault(section, {})[field] = cfg.get(section, field)
    ok, msg = cfg.api_key_status()
    return {
        "config": data,
        "has_key": bool(cfg.get_api_key()),
        "key_ok": ok,
        "key_msg": msg,
        "config_path": str(cfg.path),
    }


# ---------------------------------------------------------------- 作业

class Job:
    """一个 PDF 的一次处理。持有子进程句柄与最近一次状态。"""

    def __init__(self, path: str, proc: asyncio.subprocess.Process):
        self.path = path
        self.proc = proc
        self.status = "queued"
        self.cancelled = False
        self.started = time.time()

    @property
    def pid(self) -> int:
        return self.proc.pid or 0


class Hub:
    """所有已连接前端的广播出口（多开窗口时都要收到同一份事件）。"""

    def __init__(self) -> None:
        self._clients: set = set()

    def add(self, ws) -> None:
        self._clients.add(ws)

    def remove(self, ws) -> None:
        self._clients.discard(ws)

    @property
    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        text = json.dumps(payload, ensure_ascii=False)
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send(text)
            except Exception:               # noqa: BLE001 —— 单个连接坏了不该拖垮广播
                dead.append(ws)
        for ws in dead:
            self.remove(ws)


class JobManager:
    """按 PDF 路径索引的子进程表。"""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub
        self._jobs: dict[str, Job] = {}
        self._closed = False

    def is_running(self, path: str) -> bool:
        job = self._jobs.get(path)
        return job is not None and job.proc.returncode is None

    # ---------- 启动 ----------

    async def start(self, path: str, opts: dict) -> str:
        """拉起一个 worker 子进程。返回错误串（空串 = 已启动）。"""
        if self._closed:
            return "后端正在退出"
        pdf = Path(path)
        if not pdf.is_file():
            return f"文件不存在：{path}"
        if self.is_running(path):
            return "该文件已在处理中"

        env = os.environ.copy()
        try:
            env.update(load_config().export_env())
        except Exception as exc:            # noqa: BLE001 —— 配置坏了也得让用户看到原因
            return f"读取配置失败：{type(exc).__name__}: {exc}"
        # 工作页的逐次运行开关覆盖 config.json（不落盘，只影响这一次）
        env["ENABLE_PARALLEL"] = "true" if opts.get("parallel") else "false"

        flags = []
        if opts.get("force"):
            flags.append("--force")
        if opts.get("parse_only"):
            flags.append("--parse-only")
        if opts.get("output_warnings") is False:
            flags.append("--no-warnings")
        if opts.get("output_chapters") is False:
            flags.append("--no-chapters")

        env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [sys.executable, "-m", "dsctl.worker", str(pdf), str(pdf.parent), *flags]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            return f"无法启动流水线进程：{exc}"

        job = Job(path, proc)
        self._jobs[path] = job
        log(f"[backend] 启动 {pdf.name}（pid={job.pid}）{' '.join(flags)}")
        await self._hub.broadcast({"type": "job_status", "path": path, "status": "queued"})
        await self._hub.broadcast({
            "type": "log", "path": path, "level": "INFO",
            "line": f"开始处理: {pdf.name}",
        })
        asyncio.create_task(self._pump(job))
        return ""

    async def _pump(self, job: Job) -> None:
        """读子进程 stdout 直到 EOF，把标记行转进度、其余行转日志。"""
        path = job.path
        try:
            while True:
                raw = await job.proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    continue
                if line.startswith(PROGRESS_PREFIX):
                    await self._on_progress(path, line[len(PROGRESS_PREFIX):])
                else:
                    await self._on_log(path, line)
            code = await job.proc.wait()
        except Exception as exc:            # noqa: BLE001 —— 读流失败也要给前端一个终态
            log(f"[backend] 读取 {path} 的输出失败：{type(exc).__name__}: {exc}")
            code = job.proc.returncode if job.proc.returncode is not None else -1

        self._jobs.pop(path, None)
        if job.cancelled:
            status, ok = "cancelled", False
        elif code == 0:
            status, ok = "done", True
        else:
            status, ok = "error", False

        log(f"[backend] {Path(path).name} 结束：status={status} code={code}")
        await self._hub.broadcast({"type": "job_status", "path": path, "status": status})
        await self._hub.broadcast({
            "type": "log", "path": path,
            "level": "INFO" if ok else "ERROR",
            "line": "处理完成" if ok else ("已取消" if job.cancelled else f"处理失败（退出码 {code}）"),
        })
        await self._hub.broadcast({
            "type": "job_finished", "path": path, "ok": ok,
            "code": code, "cancelled": job.cancelled,
        })

    async def _on_progress(self, path: str, payload: str) -> None:
        try:
            data = json.loads(payload)
            order = int(data.get("order", -1))
        except (ValueError, TypeError):
            return
        title = str(data.get("title", ""))
        status = str(data.get("status", ""))
        if order < 0:
            # 串行模式：文件级阶段直接改文件行
            await self._hub.broadcast({"type": "job_status", "path": path, "status": status})
            return
        await self._hub.broadcast({
            "type": "chapter_status", "path": path,
            "order": order, "status": status, "title": title,
        })

    async def _on_log(self, path: str, line: str) -> None:
        m = _LOG_LINE_RE.match(line)
        level = m.group(1) if m else "INFO"
        text = m.group(2) if m else line
        await self._hub.broadcast({
            "type": "log", "path": path, "level": level, "line": text,
        })

    # ---------- 停止 ----------

    async def stop(self, path: str) -> bool:
        job = self._jobs.get(path)
        if job is None or job.proc.returncode is not None:
            return False
        job.cancelled = True
        log(f"[backend] 停止 {Path(path).name}（pid={job.pid}）")
        await _kill_tree(job.pid)
        return True

    async def stop_all(self) -> int:
        paths = [p for p, j in list(self._jobs.items()) if j.proc.returncode is None]
        for path in paths:
            await self.stop(path)
        return len(paths)

    async def shutdown(self) -> None:
        self._closed = True
        await self.stop_all()


async def _kill_tree(pid: int) -> None:
    """杀掉整棵进程树（worker + MinerU + 任何它拉起的子进程）。

    只杀 worker 自己，MinerU 会变成孤儿进程继续吃 GPU —— 那是最难查的一种
    「点了停止但显存不释放」。
    """
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            await proc.wait()
        else:
            os.kill(pid, 15)
    except OSError as exc:
        log(f"[backend] 终止进程 {pid} 失败：{exc}")


# ---------------------------------------------------------------- 会话

class CommandError(Exception):
    """命令本身没执行成功（如文件不存在、配置写失败）。

    与「代码出 bug 抛异常」区分开：这两种都要 `ack.ok = false` + 一条 `error`，
    但 CommandError 的消息是**给用户看的**，不需要带上堆栈。
    """


class Session:
    """一个前端连接：命令分发。"""

    def __init__(self, ws, hub: Hub, jobs: JobManager) -> None:
        self.ws = ws
        self.hub = hub
        self.jobs = jobs

    async def send(self, payload: dict) -> None:
        await self.ws.send(json.dumps(payload, ensure_ascii=False))

    async def send_error(self, message: str) -> None:
        await self.send({"type": "error", "message": message})

    async def handle(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "hello":
            # 前端据此确认「端口上跑的确实是 DeepScribe 后端」，而不是撞上了别的程序
            log("[backend] 收到 hello")
            await self.send({"type": "hello_ack", "server": SERVER_NAME,
                             "version": read_version(), "backend_version": BACKEND_VERSION})
            return
        if kind != "command":
            return

        cmd = str(msg.get("cmd", ""))
        args = msg.get("args") or {}
        ok, error = True, ""
        try:
            await self._dispatch(cmd, args)
        except CommandError as exc:
            ok, error = False, str(exc)
            log(f"[backend] 命令 {cmd} 未完成：{error}")
            await self.send_error(error)
        except Exception as exc:            # noqa: BLE001 —— 报给前端而不是闷掉
            ok, error = False, f"{type(exc).__name__}: {exc}"
            log(f"[backend] 命令 {cmd} 出错：{error}")
            await self.send_error(error)
        await self.send({"type": "ack", "id": msg.get("id"), "cmd": cmd,
                         "ok": ok, "error": error})

    async def _dispatch(self, cmd: str, args: dict) -> None:
        if cmd == "config_get":
            await self.send({"type": "config_data", **config_payload(load_config())})

        elif cmd == "config_set":
            cfg = load_config()
            incoming = args.get("config") or {}
            for key, (section, kind) in _CONFIG_SCHEMA.items():
                _, field = key.split(".", 1)
                if not isinstance(incoming.get(section), dict):
                    continue
                if field not in incoming[section]:
                    continue
                cfg.set(section, field, value=coerce(kind, incoming[section][field]))
            cfg.save()
            log("[backend] 配置已保存")
            await self.send({"type": "config_data", **config_payload(load_config())})

        elif cmd == "config_set_api_key":
            cfg = load_config()
            cfg.set_api_key(str(args.get("key", "")).strip())
            log("[backend] API Key 已更新")
            await self.send({"type": "config_data", **config_payload(load_config())})

        elif cmd == "config_restore":
            cfg = load_config()
            cfg.restore_defaults()
            log("[backend] 配置已恢复默认")
            await self.send({"type": "config_data", **config_payload(load_config())})

        elif cmd == "job_start":
            path = str(args.get("path", ""))
            error = await self.jobs.start(path, args)
            if error:
                # 先让文件行落到「失败」，再把原因作为命令失败报出去（只报一次）
                await self.hub.broadcast(
                    {"type": "job_status", "path": path, "status": "error"})
                raise CommandError(error)

        elif cmd == "job_stop":
            await self.jobs.stop(str(args.get("path", "")))

        elif cmd == "job_stop_all":
            n = await self.jobs.stop_all()
            log(f"[backend] 已请求停止全部任务（{n} 个）")

        elif cmd == "env_probe":
            await self.send({"type": "env_info", **await _probe_env()})

        else:
            log(f"[backend] 未知命令：{cmd}")


async def _probe_env() -> dict:
    """探一眼运行环境，供「关于 / 诊断」展示（不阻塞事件循环）。"""
    loop = asyncio.get_running_loop()

    def _run() -> dict:
        import shutil
        mineru = shutil.which("mineru") or str(
            Path(sys.executable).resolve().parent / "Scripts" / "mineru.exe")
        return {
            "python": sys.executable,
            "python_exists": Path(sys.executable).is_file(),
            "mineru": mineru,
            "mineru_exists": Path(mineru).is_file(),
            "project_root": str(PROJECT_ROOT),
        }

    return await loop.run_in_executor(None, _run)


async def handler(ws, hub: Hub, jobs: JobManager) -> None:
    log(f"[backend] 客户端接入 {ws.remote_address}")
    hub.add(ws)
    session = Session(ws, hub, jobs)
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log(f"[backend] 收到非 JSON 消息：{raw[:120]!r}")
                continue
            if isinstance(msg, dict):
                await session.handle(msg)
    except ConnectionClosed:
        log("[backend] 客户端断开")
    finally:
        hub.remove(ws)


async def serve(host: str, port: int) -> None:
    hub = Hub()
    jobs = JobManager(hub)
    try:
        async with websockets.serve(
                lambda ws: handler(ws, hub, jobs), host, port):
            log(f"[backend] 监听 ws://{host}:{port}（Ctrl+C 停止）")
            await asyncio.Future()      # 一直运行
    except OSError as exc:
        # 端口被占用（Windows 常见 WinError 10048）等启动失败
        log(f"[backend] 启动失败：无法监听 ws://{host}:{port}（端口被占用）")
        log(f"        原始错误：{exc}")
        log()
        log("  排查与解决：")
        log("    1) 已有实例在跑 —— 找到并结束占用该端口的进程：")
        log(f"         netstat -ano | findstr :{port}     # 看最后一列 PID")
        log("         taskkill /F /PID <pid>            # 结束该进程")
        log("    2) 端口被其它程序占用 —— 换一个端口：")
        log(f"         python backend/main.py --port {port + 1}")
        log("    3) 刚关闭又立刻重启 —— 稍等几秒，等系统释放 TIME_WAIT 状态")
        raise SystemExit(1) from exc
    finally:
        await jobs.shutdown()
    log("[backend] 已停止")


def main() -> None:
    ap = argparse.ArgumentParser(description="DeepScribe Godot GUI 后端（WebSocket）")
    ap.add_argument("--host", default=HOST, help=f"监听地址（默认 {HOST}）")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"监听端口（默认 {DEFAULT_PORT}）")
    ap.add_argument("--log-file", default="", metavar="PATH",
                    help="把日志同时写进这个文件（前端自动拉起时会传）")
    args = ap.parse_args()

    open_log_file(args.log_file)
    log(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
        f"backend v{BACKEND_VERSION} 启动（pid={os.getpid()}）=====")
    log(f"[backend] stdio {'已自导到 ' + _LOG_PATH if _STDIO_TAKEN_OVER else '未接管（stdout 直接可用）'}")
    started = time.perf_counter()
    try:
        asyncio.run(serve(args.host, args.port))
    except KeyboardInterrupt:
        log(f"\n[backend] 收到 Ctrl+C，正在退出…（已运行 {time.perf_counter() - started:.1f}s）")
    finally:
        close_log_file()


if __name__ == "__main__":
    main()
