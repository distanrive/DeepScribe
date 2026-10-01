"""DeepScribe 的缓存目录（可安全删除的中间产物）。

位置 = **系统临时目录**下的 `DeepScribe/`：

    Windows   %TEMP%\\DeepScribe      —— 通常 C:\\Users\\<用户>\\AppData\\Local\\Temp\\DeepScribe
    Linux     $TMPDIR/DeepScribe      —— 通常 /tmp/DeepScribe
    macOS     $TMPDIR/DeepScribe

取法只有一种正确写法：**`tempfile.gettempdir()`**。不要自己拼 `%TEMP%` 或 `/tmp` ——
它会依次看 `TMPDIR` / `TEMP` / `TMP` 环境变量，都没有才用平台默认值，而且每个平台
的默认值还不一样；自己拼迟早会和它不一致。CLI（`main.py`）与 GUI 后端都从这里取，
避免两处写法漂移。

里面有什么（**都是可重新生成的中间产物**，删掉只损失时间、不损失已产出的结果）：

    {短名}_mineru/             MinerU 解析输出（md + 图片），单个可达上百 MB，是体积大头
    {短名}_ch{N}_mineru/       并行模式下各章的 MinerU 输出
    {短名}_translate.db        翻译断点续传缓存 —— **删了要重新调 API 翻译（花钱）**
    {短名}_ch{N}_translate.db  并行模式各章的翻译缓存
    {短名}_parts/              按书签拆出的子 PDF
    {短名}_merged_img/         合并阶段的图片暂存
    {短名}_decrypted.pdf       加密 PDF 的解密副本（仅原文件加密时才有）
    part/                      分章输出暂存

短名 = `_` + 完整路径的 SHA256 前 12 位（见 `main.py` 的「内部短名机制」）。

**刻意不在清除范围内**：`mineru_slots/`。那是跨进程并发锁（`gpu_lock.py`）的槽位文件，
不是缓存 —— 删掉一个正被别的进程占用的槽位文件，会让新进程重新 `open()` 出一个**新的**
文件并加锁成功，于是实际并发数超过 `MAX_PARALLEL_MINERU`，8 GB 显存上直接 OOM。
它们本身是几个 0 字节的空文件，留着不占地方。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

## 缓存根目录。全项目**唯一**的取法（CLI 与 GUI 后端都引这个）。
CACHE_ROOT = Path(tempfile.gettempdir()) / "DeepScribe"

## 并发锁槽位目录名 —— 在 `CACHE_ROOT` 下，但**不算缓存**（见模块文档）。
SLOTS_DIRNAME = "mineru_slots"


def cache_size() -> tuple[int, int]:
    """统计缓存占用，返回 `(字节数, 文件数)`。

    槽位锁表不计入（几个 0 字节的空文件）。统计过程中**不抛异常** ——
    正在跑的 MinerU 会不停新建/删除文件，`stat()` 撞上「刚被删掉」是常态，
    跳过即可，不该让「看一眼占用」这种事失败。
    """
    total = 0
    files = 0
    for entry in _entries():
        size, count = _measure(entry)
        total += size
        files += count
    return total, files


def clear_cache() -> tuple[int, list[str]]:
    """删除缓存内容，返回 `(释放的字节数, 失败项说明)`。

    **保留 `CACHE_ROOT` 本身**（下次运行会自己重建），只是把里面清空。

    在 Windows 上删不掉正在被占用的文件（有任务在跑）是正常的，那种情况下会出现在
    第二个返回值里 —— 调用方应当把它展示出来，而不是假装清干净了。
    """
    freed = 0
    errors: list[str] = []
    for entry in _entries():
        size, _ = _measure(entry)
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            freed += size
        except OSError as exc:
            errors.append(f"{entry.name}（{exc.strerror or exc}）")
    return freed, errors


# ---------------------------------------------------------------- 内部


def _entries():
    """缓存根下的条目（跳过槽位锁表；根目录不存在时返回空）。"""
    if not CACHE_ROOT.is_dir():
        return []
    return [e for e in sorted(CACHE_ROOT.iterdir()) if e.name != SLOTS_DIRNAME]


def _measure(path: Path) -> tuple[int, int]:
    """`(字节数, 文件数)`；读不到的条目按 0 计（可能正被别的进程删掉）。"""
    try:
        if path.is_dir():
            return _measure_dir(path)
        if path.is_file():
            return path.stat().st_size, 1
    except OSError:
        pass
    return 0, 0


def _measure_dir(root: Path) -> tuple[int, int]:
    """递归统计一个目录，返回 `(字节数, 文件数)`。

    **用 `os.scandir` 而不是 `Path.rglob("*")`** —— 这不是风格问题，是数量级差距：

      * `Path.rglob()` + `Path.stat()` 对**每个文件**都要单独发一次 `stat` 系统调用；
      * `os.scandir()` 的 `DirEntry.stat()` 在 Windows 上直接返回目录枚举
        （`FindNextFile`）里已经带回来的大小，**一个文件都不用再打开**。

    实测（2610 个文件）：`rglob` 94ms、`os.walk` 45ms、`os.scandir` 9ms。
    更重要的是在**冷缓存 + 杀软实时扫描**的真实临时目录里：前者每个文件都要
    「打开一次」给过滤驱动过一遍，几千个文件就是几秒；后者只有目录级调用。
    这个功能曾经在用户那里「统计要等好几秒」，换掉 rglob 就是针对它的。

    用显式栈而不是递归：目录树可能很深（MinerU 输出嵌套），别撞递归上限。
    """
    total = 0
    count = 0
    stack = [root]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    try:
                        # follow_symlinks=False：不跟进符号链接/目录联接，
                        # 免得统计到缓存目录之外（也更省一次系统调用）
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            count += 1
                    except OSError:
                        continue        # 刚被别的进程删掉 / 没权限：跳过，别打断统计
        except OSError:
            continue
    return total, count
