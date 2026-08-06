"""
PDF 书签提取与 PDF 拆分工具。

依赖 PyMuPDF (fitz) —— 安装: pip install PyMuPDF
若未安装，所有函数返回空/退化结果，不影响串行流程。
"""

from pathlib import Path
from utils import setup_logger

logger = setup_logger(__name__)

try:
    import fitz
    _FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    _FITZ_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) 未安装，书签功能不可用。安装: pip install PyMuPDF")


def extract_bookmarks(pdf_path: str | Path) -> tuple[list[tuple[int, str, int]], int]:
    """
    提取 PDF 书签目录。

    Args:
        pdf_path: PDF 文件路径

    Returns:
        ([(level, title, page), ...], total_pages)
        其中 page 从 1 开始；无书签或 fitz 不可用时返回 ([], 0)
    """
    if not _FITZ_AVAILABLE:
        return [], 0

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.error(f"PDF 文件不存在: {pdf_path}")
        return [], 0

    try:
        doc = fitz.open(str(pdf_path))
        toc = doc.get_toc()  # [(level, title, page_from_1), ...]
        total_pages = doc.page_count  # B4: 一次打开同时获取页数
        doc.close()
        if not toc:
            logger.info(f"PDF 无书签: {pdf_path.name}")
            return [], total_pages
        logger.info(f"提取到 {len(toc)} 条书签 (最大层级={max(lvl for lvl, _, _ in toc)})")
        return toc, total_pages
    except Exception as e:
        logger.error(f"提取书签失败: {e}")
        return [], 0


def split_pdf_by_bookmarks(pdf_path: str | Path,
                            bookmarks: list[tuple[int, str, int]],
                            total_pages: int,
                            output_dir: Path,
                            _stem: str) -> list[tuple[str, Path]]:
    """
    按一级书签页码将 PDF 拆分为子 PDF。

    使用 PyMuPDF (fitz) 的 insert_pdf() 无损复制指定页范围。
    每份子 PDF 保存为 {output_dir}/{_stem}_p{order:02d}.pdf。

    Args:
        pdf_path: 源 PDF 路径
        bookmarks: [(level, title, page_1based), ...]
        total_pages: PDF 总页数
        output_dir: 子 PDF 输出目录
        _stem: 短名，用于子 PDF 文件名前缀

    Returns:
        [(title, sub_pdf_path), ...]
        若不足 2 个一级书签则返回 [(title, pdf_path)]（不拆分）
    """
    if not _FITZ_AVAILABLE:
        title = bookmarks[0][1] if bookmarks else "Full Document"
        return [(title, Path(pdf_path))]

    pdf_path = Path(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 取一级书签
    level1 = [(lvl, title, page) for lvl, title, page in bookmarks if lvl == 1]
    if len(level1) < 2:
        title = level1[0][1] if level1 else "Full Document"
        logger.info(f"一级书签不足 2 个，不拆分 PDF")
        return [(title, pdf_path)]

    # 钳制书签页码到有效范围
    def _clamp(page_1based):
        return max(1, min(page_1based, total_pages))

    src = fitz.open(str(pdf_path))
    sub_pdfs = []
    file_no = 0  # 独立计数器，避免空章导致编号间隙
    try:
        for i in range(len(level1)):
            title = level1[i][1]
            start_0 = _clamp(level1[i][2]) - 1  # 1-based → 0-based, 钳制
            if i + 1 < len(level1):
                end_0 = _clamp(level1[i + 1][2]) - 2  # 到下一书签页之前
            else:
                end_0 = total_pages - 1  # 末章到文档末尾

            if start_0 > end_0:
                logger.warning(f"跳过空章节 '{title}' (页 {start_0 + 1} > {end_0 + 1})")
                continue

            sub_path = output_dir / f"{_stem}_p{file_no:02d}.pdf"
            new = fitz.open()
            new.insert_pdf(src, from_page=start_0, to_page=end_0)
            new.save(str(sub_path))
            new.close()
            sub_pdfs.append((title, sub_path))
            logger.info(f"  第 {file_no + 1} 章: '{title}' 页 {start_0 + 1}-{end_0 + 1} → {sub_path.name}")
            file_no += 1
    finally:
        src.close()

    if len(sub_pdfs) < 2:
        logger.info("拆分后不足 2 章，返回原 PDF")
        return [(level1[0][1] if level1 else "Full Document", pdf_path)]

    logger.info(f"PDF 拆分为 {len(sub_pdfs)} 份子 PDF")
    return sub_pdfs
