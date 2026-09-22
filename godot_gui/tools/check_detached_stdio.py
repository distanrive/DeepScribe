#!/usr/bin/env python3
"""复现并验证「脱离进程」场景下的 stdio 问题（不需要开 Godot）。

## 背景

Godot 的 `OS.create_process()` 起进程时不给子进程可用的 stdio 句柄。
上一次迁移尝试报告过：在这种状态下 Python 导入 `ssl`（`websockets` 会连带导入）
会**永久挂起**，表现为「后端已拉起、端口却永远不监听」。

**实测结论（Python 3.10.20 / 本机，2026-09-22）：未能复现该挂起。**
对照 A 用的是 ctypes 按 Godot 的方式（`STARTF_USESTDHANDLES` + 三个 NULL 句柄）
起进程，`import ssl` 在 0.2s 内就完成了；另外用 `pythonw.exe` 起中间进程、让它
把无效句柄继承给子进程，同样不挂。触发条件仍不明确（可能与具体 Godot / Python /
驱动版本有关），所以后端的 stdio 自导**保留**（代价为零，且日志文件本身就是硬需求），
但不再声称「它修的是那个挂起」。

本脚本跑两个对照，作为回归基线：

    A) 裸脚本 `import ssl` 在 NULL 句柄下     -> 本机预期**不超时**（返回码 1）
    B) `backend/main.py` 在 NULL 句柄下启动   -> 预期**端口能连上**（这条才是关键）

对照 B 是真正要守住的那条：无论挂起是不是真的存在，脱离进程都必须能把后端拉起来。

## 用法

    python godot_gui/tools/check_detached_stdio.py            # 两个对照都跑
    python godot_gui/tools/check_detached_stdio.py --only a   # 只跑对照 A
    python godot_gui/tools/check_detached_stdio.py --only b

Windows 专用（ctypes 走 kernel32）。
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GODOT_GUI = HERE.parent
BACKEND = GODOT_GUI / "backend" / "main.py"

CREATE_NO_WINDOW = 0x08000000
STARTF_USESTDHANDLES = 0x00000100
PORT = 8791


class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR),
        ("lpTitle", wt.LPWSTR), ("dwX", wt.DWORD), ("dwY", wt.DWORD),
        ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
        ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD),
        ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
        ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
        ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
    ]


def spawn_detached(argv: list[str], cwd: Path) -> int:
    """按 Godot 的方式起进程：STARTF_USESTDHANDLES + 三个 NULL 句柄。"""
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.dwFlags = STARTF_USESTDHANDLES
    si.hStdInput = None
    si.hStdOutput = None
    si.hStdError = None
    pi = PROCESS_INFORMATION()

    cmdline = subprocess.list2cmdline(argv)
    ok = ctypes.windll.kernel32.CreateProcessW(
        None, ctypes.c_wchar_p(cmdline), None, None, True,
        CREATE_NO_WINDOW, None, ctypes.c_wchar_p(str(cwd)),
        ctypes.byref(si), ctypes.byref(pi),
    )
    if not ok:
        raise OSError(f"CreateProcessW 失败：{ctypes.get_last_error()}")
    ctypes.windll.kernel32.CloseHandle(pi.hThread)
    ctypes.windll.kernel32.CloseHandle(pi.hProcess)
    return int(pi.dwProcessId)


def kill(pid: int) -> None:
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_port(port: int, timeout: float) -> float | None:
    """等端口监听上；返回耗时秒数，超时返回 None。"""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if port_open(port):
            return time.monotonic() - t0
        time.sleep(0.2)
    return None


def check_a(timeout: float = 12.0, python: str = sys.executable) -> bool:
    """对照 A：裸 import ssl。预期超时（说明问题真实存在）。"""
    print("\n=== 对照 A：NULL std 句柄下 `import ssl` ===")
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "ssl_ok.txt"
        script = Path(tmp) / "probe.py"
        script.write_text(
            "import ssl, sys\n"
            f"open(r'{marker}', 'w').write('ok')\n"
            "print('ssl imported')\n",
            encoding="utf-8")
        pid = spawn_detached([python, str(script)], Path(tmp))
        print(f"  已拉起 pid={pid}，最多等 {timeout:.0f}s …")
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if marker.exists():
                elapsed = time.monotonic() - t0
                print(f"  -> import ssl 完成（{elapsed:.1f}s）。此环境不触发该问题。")
                kill(pid)
                return False
            time.sleep(0.2)
        print(f"  -> {timeout:.0f}s 内未完成，判定为**挂起**。")
        kill(pid)
        print("  => 问题可复现：stdio 自导这一段是必要的。")
        return True


def check_b(timeout: float = 25.0, python: str = sys.executable) -> bool:
    """对照 B：后端带 stdio 自导启动。预期端口能连上。"""
    print("\n=== 对照 B：后端（带 stdio 自导）能否监听端口 ===")
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "backend.log"
        pid = spawn_detached(
            [python, str(BACKEND), "--port", str(PORT), "--log-file", str(log_path)],
            GODOT_GUI)
        print(f"  已拉起 pid={pid}，最多等 {timeout:.0f}s …")
        elapsed = wait_port(PORT, timeout)
        kill(pid)
        text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        tail = "\n".join("    " + ln for ln in text.strip().splitlines()[-12:])
        if elapsed is None:
            print(f"  -> {timeout:.0f}s 内端口未监听。后端日志尾部：\n{tail or '    （日志为空）'}")
            return False
        print(f"  -> ws://127.0.0.1:{PORT} 在 {elapsed:.1f}s 后开始监听。")
        print("  => stdio 自导有效，脱离进程能正常起后端。")
        return True


def main() -> int:
    if sys.platform != "win32":
        print("本脚本依赖 Windows 的 CreateProcessW，无法在当前平台运行。")
        return 2

    ap = argparse.ArgumentParser(description="验证脱离进程的 stdio 行为")
    ap.add_argument("--only", choices=["a", "b"], help="只跑其中一个对照")
    ap.add_argument("--python", default=sys.executable, help="跑对照用的解释器")
    args = ap.parse_args()

    print(f"解释器：{args.python}")
    print(f"后端：  {BACKEND}")

    hung = False
    backend_ok = True
    if args.only != "b":
        hung = check_a(python=args.python)
    if args.only != "a":
        backend_ok = check_b(python=args.python)

    print("\n=== 结论 ===")
    if args.only == "a":
        return 0 if hung else 1
    if args.only == "b":
        return 0 if backend_ok else 1
    print(f"  对照 A（裸 import ssl 挂起）：{'是' if hung else '否'}")
    print(f"  对照 B（后端能监听端口）：    {'是' if backend_ok else '否'}")
    return 0 if backend_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
