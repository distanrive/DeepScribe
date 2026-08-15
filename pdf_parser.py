import hashlib
import shutil
import subprocess
from pathlib import Path
from utils import setup_logger
from config import MINERU_TIMEOUT, MINERU_EFFORT

logger = setup_logger(__name__)


def _log_tail(path: Path, max_lines: int = 40):
    """记录日志文件末尾 max_lines 行（用于 MinerU 失败时诊断）"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return
    for ln in lines[-max_lines:]:
        logger.error(ln.rstrip())


def run_mineru(pdf_path: Path, output_dir: Path, backend: str = "pipeline") -> tuple[Path, Path]:
    """
    运行 MinerU，返回 (md_path, images_dir)。

    MinerU 内部分析文件名创建深层目录结构，长文件名可能触发 Windows
    MAX_PATH (260) 限制。始终用短名副本传给 MinerU，调用完毕后自动清理。

    MinerU 输出结构：
        output_dir/<short_stem>/auto/<short_stem>.md
        output_dir/<short_stem>/auto/images/

    stdout/stderr 重定向到 {output_dir}/mineru_{short_stem}.log。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 始终用短名副本：SHA256 前 12 位 hex，~15 字符，远低于 MAX_PATH
    # 哈希输入含完整路径：不同目录下同名 PDF 互不踩踏临时副本 / 输出目录
    short_stem = "_" + hashlib.sha256(str(pdf_path.resolve()).encode()).hexdigest()[:12]
    temp_pdf = output_dir / f"{short_stem}.pdf"
    shutil.copy2(pdf_path, temp_pdf)
    logger.info(f"临时副本: {temp_pdf}  ← {pdf_path}")

    log_path = output_dir / f"mineru_{short_stem}.log"
    cmd = [
        "mineru",
        "-p", str(temp_pdf),
        "-o", str(output_dir),
        "-b", backend,
    ]
    if backend.startswith("hybrid"):
        cmd += ["--effort", MINERU_EFFORT]
    logger.info(f"Running MinerU: {' '.join(cmd)}")
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as logf:
            subprocess.run(
                cmd,
                check=True,
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=MINERU_TIMEOUT,
            )
    except subprocess.TimeoutExpired as e:
        logger.error(f"MinerU 超时（>{MINERU_TIMEOUT}s）: {e}")
        _log_tail(log_path)
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"MinerU failed with return code {e.returncode}")
        _log_tail(log_path)
        raise
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
