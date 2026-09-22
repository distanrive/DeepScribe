#!/usr/bin/env python3
"""后端协议调试客户端（不开 Godot 也能测通整条链路）。

前端是 Godot，调试协议时每次都要开窗口太慢 —— 这个脚本直接连后端的
WebSocket，把收到的每条消息按 `type` 打印出来，并允许手敲命令。

用法：

    # 1) 先起后端（另开一个终端）
    python godot_gui/backend/main.py --log-file %TEMP%/ds_backend.log

    # 2) 连上并握手
    python godot_gui/tools/ws_client.py probe

    # 3) 起一个作业（仅解析最省钱，不调 API）
    python godot_gui/tools/ws_client.py job_start "{\\"path\\": \\"D:/x/a.pdf\\", \\"parse_only\\": true}"

    # 4) 交互模式（回车发命令，Ctrl+C 退出）
    python godot_gui/tools/ws_client.py

交互模式下每行按 `命令名 {JSON 参数}` 解析，例如：

    config_get
    job_start {"path": "D:/x/a.pdf", "parse_only": true, "output_chapters": false}
    job_stop {"path": "D:/x/a.pdf"}
    job_stop_all

单发模式下脚本发完命令后会**继续收 20 秒**（默认），把后续事件都打出来 ——
作业类命令的反馈是异步的，发完立刻退出就什么都看不到。用 `--listen` 调时长。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import websockets

DEFAULT_URL = "ws://127.0.0.1:8765"

# 这些命令会持续推事件，发完要多听一会儿
_STREAMING = {"job_start"}


def _fmt(payload: dict) -> str:
    kind = payload.get("type", "?")
    if kind == "log":
        return f"[log/{payload.get('level')}] {payload.get('line')}"
    if kind == "chapter_status":
        return (f"[chapter] order={payload.get('order')} "
                f"{payload.get('status')} {payload.get('title')}")
    if kind == "config_data":
        cfg = payload.get("config", {})
        return (f"[config] {json.dumps(cfg, ensure_ascii=False)} "
                f"has_key={payload.get('has_key')} key_ok={payload.get('key_ok')}")
    return f"[{kind}] {json.dumps(payload, ensure_ascii=False)}"


class Client:
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws = None
        self.msg_id = 0

    async def connect(self) -> None:
        self.ws = await websockets.connect(self.url)
        await self.send({"type": "hello"})

    async def send(self, payload: dict) -> None:
        await self.ws.send(json.dumps(payload, ensure_ascii=False))

    async def send_command(self, cmd: str, args: dict) -> None:
        self.msg_id += 1
        await self.send({"type": "command", "id": self.msg_id, "cmd": cmd, "args": args})

    async def listen(self, seconds: float) -> None:
        """收消息，直到超时或连接断开。"""
        deadline = time.monotonic() + seconds
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=left)
            except asyncio.TimeoutError:
                return
            except websockets.ConnectionClosed:
                print("（连接已断开）")
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[raw] {raw}")
                continue
            print(_fmt(payload))


def parse_line(line: str) -> tuple[str, dict]:
    """`cmd {json}` -> (cmd, args)。"""
    line = line.strip()
    if not line:
        return "", {}
    if " " not in line:
        return line, {}
    cmd, _, rest = line.partition(" ")
    rest = rest.strip()
    if not rest:
        return cmd, {}
    try:
        args = json.loads(rest)
    except json.JSONDecodeError as exc:
        print(f"  参数不是合法 JSON（{exc}），已当作空参数")
        return cmd, {}
    return cmd, (args if isinstance(args, dict) else {})


async def run_once(url: str, cmd: str, args: dict, listen: float) -> int:
    client = Client(url)
    try:
        await client.connect()
    except OSError as exc:
        print(f"连不上 {url}：{exc}\n后端起了吗？先跑 python godot_gui/backend/main.py")
        return 2
    await client.send_command(cmd, args)
    print(f"> {cmd} {json.dumps(args, ensure_ascii=False)}")
    await client.listen(listen if cmd in _STREAMING else min(listen, 5.0))
    await client.ws.close()
    return 0


async def repl(url: str, listen: float) -> int:
    client = Client(url)
    try:
        await client.connect()
    except OSError as exc:
        print(f"连不上 {url}：{exc}\n后端起了吗？先跑 python godot_gui/backend/main.py")
        return 2
    print(f"已连接 {url}。敲 `命令名 {{JSON}}`，空行退出。")
    await client.listen(1.0)

    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, input, "> ")
        except EOFError:
            break
        if not line.strip():
            break
        cmd, args = parse_line(line)
        if not cmd:
            continue
        if cmd == "probe":
            for c in ("config_get", "env_probe"):
                await client.send_command(c, {})
        else:
            await client.send_command(cmd, args)
        await client.listen(listen if cmd in _STREAMING else 3.0)
    await client.ws.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="DeepScribe 后端协议调试客户端")
    ap.add_argument("command", nargs="?", help="命令名（省略则进交互模式）")
    ap.add_argument("args", nargs="?", default="{}", help="命令参数（JSON）")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"后端地址（默认 {DEFAULT_URL}）")
    ap.add_argument("--listen", type=float, default=20.0, help="单发模式下收消息的秒数")
    args = ap.parse_args()

    if not args.command:
        return asyncio.run(repl(args.url, args.listen))
    if args.command == "probe":
        cmd, payload = "config_get", {}
    else:
        cmd, payload = args.command, json.loads(args.args)
    return asyncio.run(run_once(args.url, cmd, payload, args.listen))


if __name__ == "__main__":
    sys.exit(main())
