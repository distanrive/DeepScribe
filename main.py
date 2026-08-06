import argparse
import hashlib
import re
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore
from config import (
    MINERU_BACKEND, TARGET_TOKENS_PER_CALL, MAX_PARAS_PER_CALL,
    MIN_MARKER_RETENTION, ENABLE_PARALLEL, MAX_PARALLEL_WORKERS,
    MAX_PARALLEL_MINERU, MAX_TOKENS,
    ENABLE_INTEGRITY,
)
from utils import setup_logger
from pdf_parser import run_mineru
from db import TranslationDB
from translator import DeepSeekTranslator
from integrity import verify_block
from bookmark_utils import (
    extract_bookmarks, split_pdf_by_bookmarks,
)

logger = setup_logger(__name__)

# ---------- text normalization ----------

# 异常 Unicode 换行/分段符 → 普通 \n
_UNICODE_LINEBREAKS = {
    '\u2028': '\n',   # LINE SEPARATOR
    '\u2029': '\n\n', # PARAGRAPH SEPARATOR
    '\u000B': '\n',   # VERTICAL TAB
}

# LaTeX 笔误：直接在原文中替换（比依赖 LLM 更可靠）
# 使用 (?![a-zA-Z]) 确保命令边界 —— 避免 \dag 匹配到 \dagger 的前缀
_LATEX_FIXES = [
    (re.compile(r'\\dag(?![a-zA-Z])'),      r'\\dagger'),
    (re.compile(r'\\ddag(?![a-zA-Z])'),     r'\\ddagger'),
    (re.compile(r'\\lamba(?![a-zA-Z])'),    r'\\lambda'),
    (re.compile(r'\\Rho(?![a-zA-Z])'),      r'\\rho'),
    (re.compile(r'\\Bbb(?![a-zA-Z])'),      r'\\mathbb'),
]


def normalize_md(text: str) -> str:
    """翻译前对 MD 文本做规范化处理"""
    # 1. Unicode 换行符归一化
    for bad, good in _UNICODE_LINEBREAKS.items():
        text = text.replace(bad, good)

    # 2. LaTeX 笔误修正（公式内外都修，安全无副作用）
    for pat, repl in _LATEX_FIXES:
        text = pat.sub(repl, text)

    # 3. 修复 $ 周围的空格（$ 后有空格或 $ 前有空格会阻止 MathJax 渲染）
    #   学术文本中 $ 始终是公式分隔符，激进清理无副作用
    text = re.sub(r'\$ +', '$', text)
    text = re.sub(r' +\$', '$', text)

    # 4. 公式内多个连续 \tag{...} → 仅保留最后一个
    #   运行两遍处理三个及以上连续 tag 的情况
    for _ in range(2):
        text = re.sub(
            r'\\tag\s*\{[^}]*}\s*(?=\\tag\s*\{[^}]*})',
            '', text
        )

    return text


# ---------- token estimation & chunking ----------

def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量（基于 DeepSeek 官方比例）。

    - 1 个英文字符 ≈ 0.3 个 token
    - 1 个中文字符 ≈ 0.6 个 token
    - 其他字符（空格、标点、LaTeX、数字）≈ 0.25 个 token

    实际 token 数以 API 返回的 usage 字段为准，此处仅用于分块决策。
    """
    en_chars = len(re.findall(r'[a-zA-Z]', text))
    zh_chars = len(re.findall(r'[一-鿿㐀-䶿豈-﫿]', text))
    other = len(text) - en_chars - zh_chars
    return int(en_chars * 0.3 + zh_chars * 0.6 + other * 0.25)


def _find_semantic_split_point(cur_chunk: list[tuple[int, str]],
                                lookback: int = 10) -> int:
    """
    在 cur_chunk 尾部寻找最佳切分点。

    优先级：标题行（# 开头）> 水平线（---）> 原位置。

    Returns:
        切分后前一半应保留的条目数（即 cur_chunk[:result] 作为前一个 chunk）
    """
    if len(cur_chunk) <= 1:
        return len(cur_chunk)

    start = max(0, len(cur_chunk) - lookback)
    for j in range(len(cur_chunk) - 1, start - 1, -1):
        text = cur_chunk[j][1].strip()
        # 优先在标题行之前切（标题归入下一个 chunk）
        if re.match(r'^#{1,6}\s', text) and j > 0:
            return j
        # 水平线之后切
        if text == '---' and j + 1 < len(cur_chunk):
            return j + 1

    return len(cur_chunk)


def _build_chunks(pending: list[tuple[int, str]],
                   target_tokens: int,
                   max_paras: int) -> list[list[tuple[int, str]]]:
    """
    将待翻译段落按 token 目标 + 段落上限拆分为多个 chunk。

    Args:
        pending: [(para_index, text), ...]
        target_tokens: 每个 chunk 的目标 token 数
        max_paras: 每个 chunk 的最大段落数

    Returns:
        [[(para_index, text), ...], ...]
    """
    chunks = []
    cur_chunk = []
    cur_token_list = []  # B3: 与 cur_chunk 同步的逐段 token 估算
    cur_tokens = 0

    for idx, text in pending:
        t = estimate_tokens(text)

        # 单段超过目标 → 自成一个 chunk（无法再拆分）
        if not cur_chunk and t > target_tokens:
            chunks.append([(idx, text)])
            logger.warning(
                f"超长段落 #{idx} ({len(text):,} 字符, ~{t:,} tokens)，单独翻译"
            )
            continue

        too_many = len(cur_chunk) >= max_paras
        too_big = cur_chunk and cur_tokens + t > target_tokens

        if cur_chunk and (too_many or too_big):
            split_at = _find_semantic_split_point(cur_chunk)
            if 0 < split_at < len(cur_chunk):
                chunks.append(cur_chunk[:split_at])
                cur_chunk = cur_chunk[split_at:]
                cur_token_list = cur_token_list[split_at:]
                # B3: 仅重算尾部（≤ lookback=10 段），非全量重算
                cur_tokens = sum(cur_token_list)
            else:
                chunks.append(cur_chunk)
                cur_chunk = []
                cur_token_list = []
                cur_tokens = 0

        cur_chunk.append((idx, text))
        cur_token_list.append(t)
        cur_tokens += t

    if cur_chunk:
        chunks.append(cur_chunk)

    return chunks


# 匹配标题行：数字编号 (1, 1.1, 1.2.3) 或混合编号 (1.A, 1.A.1)
_HEADING_PAT = re.compile(r'^(#{1,6})\s+(\d+(?:\.\w+)*)(?:\s|$)')


_CLOSE_KEYWORDS = re.compile(
    r'problem|exercise|reference|bibliography|appendix|'
    r'习题|作业|参考|附录|书目',
    re.IGNORECASE,
)


def _process_headings(lines: list[str], track_chapter: bool) -> tuple[list[str], list[str]]:
    """
    标题修正的公共核心，fix_headings（串行）与 fix_headings_parallel（并行）共用。

    对每个标题行依次执行：
    1. `#` 深度修正（按编号点数：1 → #, 1.1 → ##, 1.1.1 → ###）
    2. 纯数字编号字典序倒退检测（≤ 上一编号 → 降为正文）
    3. 章节关闭：非标准编号（1.A）或关键词标题（Problems/References 等）
       → 关闭后同章后续编号标题全部降为正文
    串行版（track_chapter=True）额外：章号递增 1→2 时重置，章号倒退 3→2 时降为正文。

    Args:
        lines: MD 文本按行切分（原地修改后返回）
        track_chapter: 是否追踪章号（串行整篇为 True，并行单章为 False）
    """
    warnings = []
    max_parts = ()
    current_chapter = None
    closed = False  # 当前章正文已结束

    for i, line in enumerate(lines):
        m = _HEADING_PAT.match(line)
        if not m:
            # 无编号标题 → 仅关键词触发章节关闭（该标题自身保留 #）
            # 串行版需已建立编号章才关闭；并行版无条件关闭
            nm = re.match(r'^(#{1,6})\s+(\S.*)', line)
            if nm and (not track_chapter or current_chapter is not None):
                title = nm.group(2).strip()
                if _CLOSE_KEYWORDS.search(title):
                    closed = True
                    if track_chapter:
                        msg = (f"检测到章节边界 ({title})，"
                               f"后续 {current_chapter}.x 标题降为正文")
                    else:
                        msg = f"检测到章节边界 ({title})，后续标题降为正文"
                    warnings.append(msg)
                    logger.warning(msg)
            continue

        num_str = m.group(2)
        parts_raw = num_str.split('.')
        depth = len(parts_raw)
        old_prefix = m.group(1)
        first_num = int(parts_raw[0]) if parts_raw[0].isdigit() else None

        # 章号切换（仅串行整篇模式）
        if track_chapter and first_num is not None:
            if current_chapter is not None and first_num != current_chapter:
                if first_num > current_chapter:
                    current_chapter = first_num
                    max_parts = ()
                    closed = False
                else:
                    # 旧章号回溯 → 降为正文
                    line = re.sub(r'^#+\s*', '', line)
                    lines[i] = line
                    continue
            elif current_chapter is None:
                current_chapter = first_num

        # 当前章已关闭 → 降为正文
        if closed:
            line = re.sub(r'^#+\s*', '', line)
            lines[i] = line
            continue

        # 非全数字编号 (如 1.A) → 关闭章节，自身保留标题（修正深度）
        if not all(p.isdigit() for p in parts_raw):
            closed = True
            correct_prefix = '#' * depth
            if old_prefix != correct_prefix:
                line = correct_prefix + line[len(old_prefix):]
            lines[i] = line
            msg = f"非标准编号，章节关闭: {old_prefix} {num_str}"
            warnings.append(msg)
            logger.warning(msg)
            continue

        # 1. 修正 # 数量
        correct_prefix = '#' * depth
        if old_prefix != correct_prefix:
            line = correct_prefix + line[len(old_prefix):]

        # 2. 纯数字排序检测
        parts = tuple(int(p) for p in parts_raw)
        if parts <= max_parts:
            line = re.sub(r'^#+\s*', '', line)
            lines[i] = line
            msg = f"疑似误判标题，已降为正文: {old_prefix} {num_str}"
            warnings.append(msg)
            logger.warning(msg)
            continue

        max_parts = parts
        lines[i] = line

    return lines, warnings


def fix_headings(md_text: str) -> tuple[str, list[str]]:
    """
    串行版标题修正（整篇 MD，含章号递增检测）。

    1. 根据编号层级修正 # 数量（1.x.y → ###）
    2. 章节内部纯数字标题按字典序检测倒退
    3. 遇到非标准编号（1.A）或关键词标题（Problems 等）→ 关闭当前章，
       后续同章号全部降为正文
    4. 章号递增（1→2）→ 新章重置
    """
    lines, warnings = _process_headings(md_text.split('\n'), track_chapter=True)
    return '\n'.join(lines), warnings


def fix_headings_parallel(md_text: str) -> tuple[str, list[str]]:
    """
    并行模式专用标题修正（单章内部，不做章号递增检测）。

    与串行版 fix_headings 的区别：
    1. 不做章号递增检测（每个 fragment 只含一章）
    2. 遇到 1.A → 关闭章节，自身保留 #
    3. 遇到 Problems/References → 关闭章节，自身保留 #（与 1.A 一致）
    4. 章节关闭后，同章号标题降为正文
    5. 章节内部纯数字标题按字典序检测倒退
    """
    lines, warnings = _process_headings(md_text.split('\n'), track_chapter=False)
    return '\n'.join(lines), warnings


def write_warnings_file(output_dir: Path, _stem: str,
                        warnings: list[str]) -> Path | None:
    """将标题修正警告写入独立日志文件，不污染 zh/en 输出文件。

    Returns:
        写入的日志文件路径；无警告时返回 None。
    """
    if not warnings:
        return None
    path = output_dir / f"{_stem}_warnings.md"
    lines = [f"# 标题修正警告 — {_stem}", ""]
    lines += [f"- {w}" for w in warnings]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info(f"标题修正警告已写入: {path} ({len(warnings)} 条)")
    return path


def write_failure_report(output_dir: Path, _stem: str,
                         failures: list[dict]) -> Path | None:
    """将失败的文件/章节写入独立报告文件，便于事后排查。无失败返回 None。"""
    if not failures:
        return None
    path = output_dir / f"{_stem}_failed.md"
    lines = [f"# 失败报告 — {_stem}", ""]
    for f in failures:
        kind = f.get("kind", "未知")
        name = f.get("name", _stem)
        err = f.get("error", "未知错误")
        lines.append(f"- [{kind}] {name}: {err}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.error(f"失败报告已写入: {path} ({len(failures)} 条)")
    return path


# ---------- table rendering fix ----------

def fix_table_rendering(md_text: str) -> str:
    """修复 HTML 表格在 Markdown 中的渲染问题（仅处理 <td> 内部）"""
    def _fix_td(m):
        open_tag = m.group(1)
        inner = m.group(2)
        close_tag = m.group(3)
        inner = re.sub(
            r'!\[(.*?)]\(([^)]+)\)',
            r'<img src="\2" style="max-height:40px;display:inline-block;" alt="\1">',
            inner
        )
        return open_tag + inner + close_tag

    text = re.sub(r'(<td[^>]*>)(.*?)(</td>)', _fix_td, md_text, flags=re.DOTALL)

    # 3. 删除 rowspan="1" / colspan="1"（默认值，冗余）
    text = re.sub(r'\s*rowspan\s*=\s*["\']?1["\']?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*colspan\s*=\s*["\']?1["\']?', '', text, flags=re.IGNORECASE)

    return text


def normalize_output(text: str) -> str:
    """输出侧轻量归一化：清理 LLM 可能引入的控制字符。

    软换行合并仅对连续正文行生效；fenced code 块（```）与
    $$ 显示公式内部的行原样保留、不做合并，避免破坏代码与 LaTeX 公式。
    """
    # 清除各类异常 Unicode 控制符，保留 \n \r \t
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f'
                  r'\u2028\u2029\ufeff\ufff0-\uffff]+', '', text)

    lines = text.split('\n')
    result = []
    i = 0
    in_code = False   # fenced code block 内部
    in_math = False   # 多行 $$...$$ 显示公式内部

    _BLOCK_PREFIXES = ('#', '```', '$$', '|', '- ', '* ', '> ', '<',
                       '<!--', '[BLK:', '![')

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # --- fenced code block：以 ``` 行切换状态 ---
        if stripped.startswith('```'):
            in_code = not in_code
            result.append(line)
            i += 1
            continue

        # 代码块内部：原样保留
        if in_code:
            result.append(line)
            i += 1
            continue

        # --- 显示公式块 ---
        # 单行 $$...$$（非 `$$` 单独成行）无需进入状态；
        # `$$` 单独成行或行首 $$ 未闭合 → 视为多行公式开头
        if not in_math and stripped.startswith('$$'):
            in_math = stripped == '$$' or not stripped.endswith('$$')
            result.append(line)
            i += 1
            continue
        if in_math:
            result.append(line)
            i += 1
            if stripped.endswith('$$'):
                in_math = False
            continue

        # --- 常规行：软换行合并 ---
        stripped_l = line.lstrip()
        is_block = (
            not stripped_l or
            stripped_l.startswith(_BLOCK_PREFIXES)
        )
        if is_block:
            result.append(line)
            i += 1
        else:
            merged = [line]
            i += 1
            while i < len(lines):
                nxt_s = lines[i].lstrip()
                if not nxt_s or nxt_s.startswith(_BLOCK_PREFIXES):
                    break
                prev_end = merged[-1].rstrip()[-1:] if merged[-1].rstrip() else ''
                if not (prev_end and re.match(r'[一-鿿\w]', prev_end)):
                    break
                merged.append(lines[i])
                i += 1
            result.append(' '.join(merged))
    return '\n'.join(result)
def html_tables_to_md(text: str) -> str:
    """将所有 HTML 表格转为 Markdown 表格。
       rowspan/colspan 单元格通过重复内容展开，确保公式能在 MD 中渲染。"""
    def _convert(m):
        html = m.group(0)
        rows_html = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
        if len(rows_html) < 2:
            return html

        # 解析每个单元格，跟踪被 rowspan 占用的位置
        cells = []
        occupied = set()  # (row, col) 已被 rowspan 占用
        for ri, row_h in enumerate(rows_html):
            tds = re.findall(r'<t[dh]([^>]*)>(.*?)</t[dh]>', row_h, re.DOTALL | re.IGNORECASE)
            ci = 0
            for attrs, content in tds:
                while (ri, ci) in occupied:
                    ci += 1  # 跳过被上方 rowspan 占用的列
                rs = re.search(r'rowspan\s*=\s*"?(\d+)"?', attrs, re.IGNORECASE)
                cs = re.search(r'colspan\s*=\s*"?(\d+)"?', attrs, re.IGNORECASE)
                rowspan = int(rs.group(1)) if rs else 1
                colspan = int(cs.group(1)) if cs else 1
                for dr in range(rowspan):
                    for dc in range(colspan):
                        occupied.add((ri + dr, ci + dc))
                cells.append((ri, ci, rowspan, colspan, content.strip()))
                ci += colspan

        # 构建最大行列范围
        max_row = max(ri + rs for ri, _, rs, _, _ in cells)
        max_col = max(ci + cs for _, ci, _, cs, _ in cells)
        grid = [[''] * max_col for _ in range(max_row)]

        for ri, ci, rs, cs, content in cells:
            for dr in range(rs):
                for dc in range(cs):
                    grid[ri + dr][ci + dc] = content

        # 输出 Markdown 表格
        md_rows = []
        for ri, row in enumerate(grid):
            md_rows.append('| ' + ' | '.join(row) + ' |')
            if ri == 0:
                md_rows.append('| ' + ' | '.join(['---'] * max_col) + ' |')
        return '\n'.join(md_rows)

    return re.sub(r'<table[^>]*>.*?</table>', _convert, text,
                  flags=re.DOTALL | re.IGNORECASE)


def dedup_adjacent_images(text: str) -> str:
    """相邻（中间只有空行）的重复图片引用去重，保留有 alt 文本的那条。

    仅当两条引用之间没有其他内容行（可含空行）时才视为相邻；
    中间夹了正文或其他图片则视为正常多次引用，不去重。
    """
    lines = text.split('\n')
    result = []
    prev_src = None
    last_img_idx = -1  # result 中最近一条图片行的下标
    for line in lines:
        if not line.strip():
            result.append(line)  # 空行原样保留，不打断相邻判定
            continue
        m = re.search(r'!\[(.*?)]\(([^)]+)\)', line)
        cur_src = m.group(2) if m else None
        cur_alt = m.group(1) if m else ''
        if cur_src and cur_src == prev_src:
            # 重复图片：保留有 alt 的（中间只有空行）
            prev_m = re.search(r'!\[(.*?)]\(([^)]+)\)', result[last_img_idx])
            prev_alt = prev_m.group(1) if prev_m else ''
            if prev_alt and not cur_alt:
                pass  # 前一条更好，跳过当前
            elif cur_alt and not prev_alt:
                result[last_img_idx] = line  # 当前更好，替换前一条
            # 两条都有或都没有 alt → 保留前一条
            continue
        prev_src = cur_src
        result.append(line)
        if cur_src:
            last_img_idx = len(result) - 1
    return '\n'.join(result)


# ---------- image processing ----------

# 匹配 ![...](path) 和 <img src="path"/>
_IMG_MD_PAT = re.compile(r'!\[(.*?)]\(([^)]+)\)')
_IMG_HTML_PAT = re.compile(r'<img\s+[^>]*?src="([^"]+)"[^>]*/?>', re.IGNORECASE)


def _find_image_file(filename: str, images_dir: Path) -> Path | None:
    """在 images_dir 下递归搜索 filename，返回第一个匹配，找不到返回 None"""
    if not images_dir.is_dir():
        return None
    matches = list(images_dir.rglob(filename))
    return matches[0] if matches else None


def _is_url(path: str) -> bool:
    """是否为外部图片 URL（此类图片跳过重命名，保留原引用）"""
    return path.lower().startswith(("http://", "https://"))


def process_images(md_text: str, images_dir: Path, output_dir: Path,
                   doc_stem: str, quiet: bool = False) -> tuple[str, Path]:
    """
    处理 MD 中所有图片引用（![](...) 和 <img src="..."/>）：
    1. 按出现顺序去重，编号 image-1, image-2, ...
    2. 从 images_dir 递归查找原图，复制到 {doc_stem}_zh.assets/
    3. 替换 MD 中的引用为 Markdown ![]() 格式
    """
    # 收集所有图片引用：(![](...) 格式)
    md_refs = [(m.group(1), m.group(2), m.span()) for m in _IMG_MD_PAT.finditer(md_text)]
    # <img> 格式 —— alt 为空，避免把路径当作文本
    html_refs = [('', m.group(1), m.span()) for m in _IMG_HTML_PAT.finditer(md_text)]
    # 合并，按原文出现顺序排列
    all_refs = sorted(md_refs + html_refs, key=lambda x: x[2][0])

    if not all_refs:
        assets_dir = output_dir / f"{doc_stem}_zh.assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        return md_text, assets_dir

    # 去重（保持首次出现顺序）
    seen = {}          # old_filename -> order_number
    for _, img_path, _pos in all_refs:
        if _is_url(img_path):
            continue  # 外部图片 URL 不重命名
        old_name = Path(img_path).name
        if old_name not in seen:
            seen[old_name] = len(seen) + 1

    if not seen:
        assets_dir = output_dir / f"{doc_stem}_zh.assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        return md_text, assets_dir

    # 复制并重命名
    assets_dir = output_dir / f"{doc_stem}_zh.assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # B1: 构建 {basename: Path} 索引（一次遍历，替代每张图的 rglob）
    image_index = {}
    if images_dir and images_dir.is_dir():
        for f in images_dir.rglob("*"):
            if f.is_file():
                image_index[f.name] = f

    renamed = {}
    for old_name, order in seen.items():
        ext = Path(old_name).suffix
        new_name = f"image-{order}{ext}"
        renamed[old_name] = new_name
        src = image_index.get(old_name)
        if src is None:
            src = _find_image_file(old_name, images_dir)  # 回退
        if src:
            dst = assets_dir / new_name
            if not dst.exists():
                shutil.copy2(src, dst)
        else:
            logger.warning(f"图片未找到: {old_name} (搜索于 {images_dir})")

    # 替换：从后往前替换（避免位置偏移）
    result = list(md_text)
    for alt, old_path, (start, end) in reversed(all_refs):
        if _is_url(old_path):
            continue  # 外部图片 URL 保留原引用
        old_name = Path(old_path).name
        mapped = renamed.get(old_name)
        if mapped:
            new_ref = f"![{alt}]({doc_stem}_zh.assets/{mapped})"
            result[start:end] = new_ref

    new_md = ''.join(result)
    if not quiet:
        logger.info(f"图片处理完成: {len(seen)} 张图片重编号，assets -> {assets_dir}")
    return new_md, assets_dir


# ---------- MD splitting ----------

def split_md_blocks(md_text: str) -> list[dict]:
    """
    按空行将 MD 文本切分为块，每块标记类型：
    - 'latex': 纯 $$...$$ 公式块，不翻译
    - 'text':  需要翻译的块（标题、段落、列表、带图片的说明文字等）

    块索引为稳定的递增序号（text/latex 共用，作为翻译缓存的键）。
    公式块（$$ 开头）若其后在同一块内跟有需翻译的正文（如公式下方图注），
    会自动拆成 latex 块 + text 块，避免尾部正文漏译。
    """
    raw = re.split(r'\n{2,}', md_text.strip())
    blocks = []
    next_index = 0
    for para in raw:
        content = para.strip()
        if not content:
            continue

        # 判断是否为显示公式块，并检查闭合 $$ 后是否还有正文
        if content.startswith('$$'):
            m = re.search(r'\$\$', content[2:])
            if m:
                close_end = m.end() + 2  # 闭合 $$ 之后的位置
                trailing = content[close_end:].strip()
                if trailing:
                    # 公式 + 尾部正文 → 拆成 latex 块 + text 块
                    blocks.append({'type': 'latex', 'index': next_index,
                                   'content': content[:close_end].rstrip()})
                    next_index += 1
                    blocks.append({'type': 'text', 'index': next_index,
                                   'content': trailing})
                    next_index += 1
                    continue
            # 无尾部正文（或未闭合）→ 整块视为公式
            blocks.append({'type': 'latex', 'index': next_index,
                           'content': content})
            next_index += 1
            continue

        blocks.append({'type': 'text', 'index': next_index, 'content': content})
        next_index += 1

    return blocks


# ---------- translation ----------

# 单段连续翻译失败达到该次数后，用原文兜底并告警（避免无限重试）
MAX_FAILED_ATTEMPTS = 3


def translate_blocks(blocks: list[dict], db: TranslationDB,
                     translator: DeepSeekTranslator,
                     label: str = "") -> dict[int, str]:
    """
    翻译所有 text 类型的块。
    1. 将所有 text 块写入 DB（断点续传）
    2. 全文一次提交，用 [BLK:N] 标记分段
    3. 解析结果，遗漏段落逐段补译
    4. 返回 {block_index: zh_content}
    """
    _pre = f"[{label}] " if label else ""
    # 收集所有 text 块
    text_entries = []
    for b in blocks:
        if b['type'] == 'text' and b['content'].strip():
            text_entries.append((b['index'], b['content']))

    if not text_entries:
        logger.info("无可翻译文本块")
        return {}

    # 与当前源对齐后写入 DB（移除已删除段落，内容变化自动失效旧译文）
    text_indices = {idx for idx, _ in text_entries}
    db.prune(text_indices)
    db.store_paragraphs(text_entries)

    # 仅翻译未完成的段落
    pending = db.get_pending_paragraphs()
    if not pending:
        logger.info("所有段落均已翻译完成")
        return db.get_all_translations()

    total_chars = sum(len(t) for _, t in pending)
    total_tokens = estimate_tokens('\n\n'.join(t for _, t in pending))
    logger.info(f"{_pre}待翻译段落: {len(pending)} 段 "
                f"({total_chars:,} 字符, ~{total_tokens:,} tokens)")

    # Token 感知分块 + 自适应调节。
    # 一批内顺序消费构建出的 chunks（避免每轮全量重建的 O(n²)）；
    # 仅当某 chunk marker 保留率过低时，才用更小目标重建剩余待译段落。
    # 输入侧目标同时受输出上限钳制，避免首轮截断。
    target_tokens = min(TARGET_TOKENS_PER_CALL, MAX_TOKENS // 2)
    trans_map = {}
    chunk_no = 0
    failed_attempts = {}  # para_index -> 连续失败次数（仅本次运行内存态，不跨运行持久化）

    while pending:
        chunks = _build_chunks(pending, target_tokens, MAX_PARAS_PER_CALL)

        for ci, chunk in enumerate(chunks):
            chunk_no += 1
            chunk_tokens = sum(estimate_tokens(t) for _, t in chunk)

            if len(chunks) > 1:
                logger.info(f"{_pre}翻译第 {chunk_no} 部分 "
                            f"({len(chunk)} 段, ~{chunk_tokens:,} tokens, "
                            f"本批 {ci + 1}/{len(chunks)}, "
                            f"目标 {target_tokens:,} tokens/次)")

            result = translator.translate_numbered(chunk, label=label)
            trans_map.update(result)
            # 整批标记完成（单事务），支持中断续传
            db.mark_many_done(result)

            # 连续失败段落：累计尝试次数，超过阈值用原文兜底并告警（避免无限重试）
            for idx, text in chunk:
                if idx in result:
                    failed_attempts.pop(idx, None)
                else:
                    failed_attempts[idx] = failed_attempts.get(idx, 0) + 1
                    if failed_attempts[idx] >= MAX_FAILED_ATTEMPTS:
                        logger.error(
                            f"段落 #{idx} 连续 {failed_attempts[idx]} 次翻译失败，"
                            "已用原文兜底（请人工检查该段译文）")
                        db.mark_many_done({idx: text})
                        trans_map[idx] = text

            # 自适应反馈：根据 marker 保留率调整后续目标 token 数
            if MIN_MARKER_RETENTION < 1.0:
                sent = len(chunk)
                recovered = len(result)
                retention = recovered / sent if sent > 0 else 1.0

                if retention < MIN_MARKER_RETENTION and sent > 5:
                    # 遗漏较多，缩小目标，用更小 chunk 重建剩余段落
                    old_target = target_tokens
                    target_tokens = max(20000, int(target_tokens * 0.7))
                    logger.warning(
                        f"marker 保留率 {retention:.0%} < {MIN_MARKER_RETENTION:.0%}, "
                        f"目标 token 数: {old_target:,} → {target_tokens:,}"
                    )
                    break
                elif retention > 0.99 and sent >= MAX_PARAS_PER_CALL * 0.8:
                    # 接近满载且保留率很好，尝试逐步放大（仍受输出上限钳制）
                    old_target = target_tokens
                    new_target = min(MAX_TOKENS // 2, int(target_tokens * 1.1))
                    if new_target != old_target:
                        target_tokens = new_target
                        logger.info(
                            f"marker 保留率 {retention:.0%}, "
                            f"目标 token 数: {old_target:,} → {target_tokens:,}"
                        )

        prev_pending = len(pending)
        pending = db.get_pending_paragraphs()
        if pending and len(pending) >= prev_pending:
            logger.error("翻译循环未取得进展，中止以避免死循环")
            break

    # 补充 DB 中已有的翻译 + 本次结果
    all_trans = db.get_all_translations()
    all_trans.update(trans_map)
    return all_trans


# ---------- parallel translation helpers ----------

def _cleanup_chapter_db(db_path: Path) -> None:
    """删除章节翻译的临时 DB 文件（文件不存在或删除失败时静默）。"""
    if not db_path.exists():
        return
    try:
        db_path.unlink()
    except OSError:
        logger.warning(f"章节翻译 DB 清理失败: {db_path}")


def _process_chapter_pdf(order: int, title: str, pdf_path: Path | None,
                          output_dir: Path, _stem: str,
                          md_text: str | None = None) -> dict[str, object]:
    """
    处理单个章节 PDF：MinerU 解析（或跳过）→ 翻译 → 组装。

    若传入 md_text（已预处理含图片引用），则跳过 MinerU 步骤直接翻译。
    用于流式流水线中每章 Semaphore 保护 MinerU + 独立图片处理后调用。

    Args:
        order: 章节序号
        title: 章节标题
        pdf_path: 子 PDF 路径（仅 md_text=None 时使用）
        output_dir: 输出目录
        _stem: 内部短名
        md_text: 已预处理的 MD 文本（可选，跳过 MinerU）

    Returns:
        dict 含 order, title, zh_text, en_text, warnings, blocks, trans_map
    """
    if md_text is None:
        # --- MinerU 模式（兼容直接调用）---
        if pdf_path is None:
            raise ValueError("md_text 为 None 时必须提供 pdf_path")
        logger.info(f"[{title}] MinerU 解析中...")
        chapter_mineru_out = output_dir / f"{_stem}_ch{order}_mineru"
        md_path, images_dir = run_mineru(pdf_path, chapter_mineru_out,
                                          backend=MINERU_BACKEND)
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()
        md_text = normalize_md(md_text)
        md_text, _ = process_images(md_text, images_dir, output_dir,
                                     f"{_stem}_ch{order}", quiet=True)
    else:
        logger.info(f"[{title}] 使用预处理 MD，开始翻译")

    # --- 翻译 + 组装（两种模式共用）---
    blocks = split_md_blocks(md_text)
    text_count = sum(1 for b in blocks if b['type'] == 'text')
    logger.info(f"[{title}] 切分为 {len(blocks)} 块 (文本 {text_count})")

    db_path = output_dir / f"{_stem}_ch{order}_translate.db"
    db = TranslationDB(db_path)
    try:
        translator = DeepSeekTranslator()
        trans_map = translate_blocks(blocks, db, translator, label=title)
    finally:
        db.close()
        _cleanup_chapter_db(db_path)

    zh_lines = []
    en_lines = []
    g2_warnings = []
    for b in blocks:
        content = b['content']
        if b['type'] == 'latex':
            zh_lines.append(content)
            en_lines.append(content)
        else:
            zh = trans_map.get(b['index'], content)
            if ENABLE_INTEGRITY:
                zh, iv_warnings = verify_block(content, zh)
                g2_warnings.extend(iv_warnings)
            zh_lines.append(zh)
            en_lines.append(content)

    zh_text = '\n\n'.join(zh_lines)
    en_text = '\n\n'.join(en_lines)
    zh_text, zh_warnings = fix_headings_parallel(zh_text)
    zh_warnings = g2_warnings + zh_warnings
    if zh_warnings:
        logger.info(f"[{title}] 标题修正: {len(zh_warnings)} 处")

    logger.info(f"[{title}] 处理完成")
    return {
        'order': order, 'title': title,
        'zh_text': zh_text, 'en_text': en_text,
        'warnings': zh_warnings, 'blocks': blocks,
        'trans_map': trans_map,
    }


def _process_pdf_parallel(output_dir: Path, pdf_path: Path, _stem: str,
                          bookmarks: list[tuple[int, str, int]], total_pages: int,
                          label: str = "") -> None:
    """
    并行翻译流程：按书签页码拆分 PDF → 各章独立 MinerU + 翻译 → 合并 → 后处理。

    与旧版不同：不再依赖 MD 文本中的标题模糊匹配来切分，
    而是直接用 PyMuPDF 按页范围拆分子 PDF，每章独立送 MinerU，
    从根本上解决切分不准的问题。

    Args:
        output_dir: 输出目录
        pdf_path: 源 PDF 路径
        _stem: 内部短名（DB、中间文件路径用）
        bookmarks: [(level, title, page), ...]
        total_pages: PDF 总页数
        label: 输出文件名前缀（zh/en.md 用）；默认回退到 _stem
    """
    _out = label or _stem

    # 1. 按书签页码拆分 PDF → 子 PDF
    sub_pdfs_dir = output_dir / f"{_stem}_parts"
    sub_pdfs = split_pdf_by_bookmarks(pdf_path, bookmarks, total_pages,
                                       sub_pdfs_dir, _stem)
    if len(sub_pdfs) < 2:
        logger.info("PDF 拆分后仅 1 份，退回串行处理")
        raise ValueError("无法拆分为多章节")

    # 2. 流式处理：MinerU (Semaphore) → process_images (每章独立 assets) → 翻译
    chapter_results = []
    failures = []
    mineru_sem = Semaphore(MAX_PARALLEL_MINERU)

    def _do_chapter(_i: int, _title: str, _sub_pdf_path: Path) -> dict:
        """单个章节：Semaphore 保护 MinerU → 独立图片 assets → 翻译。"""
        with mineru_sem:
            _chapter_mineru_out = output_dir / f"{_stem}_ch{_i}_mineru"
            _md_path, _images_dir = run_mineru(_sub_pdf_path, _chapter_mineru_out,
                                                backend=MINERU_BACKEND)
            with open(_md_path, "r", encoding="utf-8") as _f:
                _md_text = _f.read()
            _md_text = normalize_md(_md_text)

            # 每章独立图片处理：生成 part/{_stem}_ch{order}_zh.assets/
            _part_dir = output_dir / "part"
            _part_dir.mkdir(parents=True, exist_ok=True)
            _md_text, _ch_assets = process_images(
                _md_text, _images_dir, _part_dir,
                f"{_stem}_ch{_i}", quiet=True
            )
            logger.info(f"  [{_title}] MinerU 完成 ({len(_md_text):,} 字符)")

        # 翻译 (信号量外，无限制并发)
        return _process_chapter_pdf(_i, _title, None, output_dir,
                                     _stem, md_text=_md_text)

    logger.info(f"流式处理: {len(sub_pdfs)} 章, "
                f"MinerU并发={MAX_PARALLEL_MINERU}, 翻译并发={MAX_PARALLEL_WORKERS}")
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        _futures = {}
        for i, (title, sub_pdf_path) in enumerate(sub_pdfs):
            f = executor.submit(_do_chapter, i, title, sub_pdf_path)
            _futures[f] = (i, title)

        for f in as_completed(_futures):
            i, title = _futures[f]
            try:
                result = f.result()
                chapter_results.append(result)
            except Exception as e:
                logger.error(f"第 {i + 1} 章 [{title}] 处理失败: {e}")
                chapter_results.append({
                    'order': i, 'title': title,
                    'zh_text': f"<!-- ⚠️ 本章处理失败 -->\n{title}",
                    'en_text': title, 'failed': True,
                })
                failures.append({"kind": "章节", "name": title, "error": str(e)})

    # 4. 按章节顺序合并
    chapter_results.sort(key=lambda x: x['order'])

    zh_parts = []
    en_parts = []
    for cr in chapter_results:
        zh_parts.append(cr['zh_text'])
        en_parts.append(cr['en_text'])
    zh_text = '\n\n'.join(zh_parts)
    en_text = '\n\n'.join(en_parts)

    # 5. 统一图片处理：收集各章 assets（加章前缀防冲突）→ 合并处理 → 只记一次日志
    _merged_img_dir = output_dir / f"{_stem}_merged_img"
    _merged_img_dir.mkdir(parents=True, exist_ok=True)
    for _i in range(len(sub_pdfs)):
        _ch_assets = output_dir / "part" / f"{_stem}_ch{_i}_zh.assets"
        _ch_prefix = f"{_stem}_ch{_i}_zh.assets"
        if _ch_assets.is_dir():
            for _img in _ch_assets.iterdir():
                if _img.is_file():
                    shutil.copy2(_img, _merged_img_dir / f"{_i:02d}_{_img.name}")
        # 正则替换图片引用路径（宽容 LLM 引入的空格/格式变化）
        _esc = re.escape(_ch_prefix)
        _pat = re.compile(
            rf'(\(|<img\b[^>]*\bsrc=["\'])\s*{_esc}/([^)"\']+)',
        )
        _repl = rf'\g<1>{_i:02d}_\g<2>'
        zh_text = _pat.sub(_repl, zh_text)
        en_text = _pat.sub(_repl, en_text)
    if any(_merged_img_dir.iterdir()):
        zh_text, assets_dir = process_images(
            zh_text, _merged_img_dir, output_dir, _out
        )
        en_text, _ = process_images(
            en_text, _merged_img_dir, output_dir, _out, quiet=True
        )
    else:
        assets_dir = output_dir / f"{_out}_zh.assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

    # 6. 清理临时文件
    try:
        shutil.rmtree(_merged_img_dir)
    except OSError:
        pass
    try:
        shutil.rmtree(sub_pdfs_dir)
    except OSError:
        pass
    for _i in range(len(sub_pdfs)):
        _ch_mu = output_dir / f"{_stem}_ch{_i}_mineru"
        try:
            shutil.rmtree(_ch_mu)
        except OSError:
            pass

    # 7. 后处理（在合并结果上）
    zh_text = fix_table_rendering(zh_text)
    en_text = fix_table_rendering(en_text)
    zh_text = html_tables_to_md(zh_text)
    en_text = html_tables_to_md(en_text)
    zh_text = normalize_output(zh_text)
    en_text = normalize_output(en_text)
    zh_text = dedup_adjacent_images(zh_text)
    en_text = dedup_adjacent_images(en_text)

    # 8. 分章输出
    _part_dir = output_dir / "part"
    _part_dir.mkdir(parents=True, exist_ok=True)
    for cr in chapter_results:
        safe = re.sub(r'[\\/:*?"<>|]', '_', cr['title']).strip()
        part_path = _part_dir / f"{cr['order']:02d}_{safe}.md"
        with open(part_path, "w", encoding="utf-8") as pf:
            pf.write(cr['zh_text'])
    logger.info(f"分章输出: {len(chapter_results)} 章 → {_part_dir}")

    # 9. 收集警告 + 失败报告
    all_warnings = []
    for cr in chapter_results:
        for w in cr.get('warnings', []):
            all_warnings.append(f"[{cr['title']}] {w}")
    write_warnings_file(output_dir, _stem, all_warnings)
    write_failure_report(output_dir, _stem, failures)

    # 10. 写入最终文件
    zh_md_path = output_dir / f"{_out}_zh.md"
    en_md_path = output_dir / f"{_out}_en.md"
    with open(zh_md_path, "w", encoding="utf-8") as f:
        f.write(zh_text)
    with open(en_md_path, "w", encoding="utf-8") as f:
        f.write(en_text)

    logger.info(f"并行翻译完成! 中文版: {zh_md_path}")
    logger.info(f"英文版: {en_md_path}")


# ---------- main pipeline ----------

def process_pdf(pdf_path: Path, output_dir: Path, force: bool = False,
                 parallel: bool = None):
    """处理单个 PDF：MinerU 解析 → 图片处理 → 翻译 → 输出

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        force: 强制重新运行 MinerU
        parallel: 是否启用并行模式（None=使用 ENABLE_PARALLEL 配置）
    """
    if parallel is None:
        parallel = ENABLE_PARALLEL

    pdf_stem = pdf_path.stem  # 原始名，仅用于日志
    _stem = "_" + hashlib.sha256(pdf_stem.encode()).hexdigest()[:12]  # 内部短名
    logger.info(f"短名 {_stem} ← {pdf_stem}")

    # --- 并行模式检测（先于完整 PDF 的 MinerU，避免浪费）---
    if parallel:
        bookmarks, total_pages = extract_bookmarks(pdf_path)
        if bookmarks:
            try:
                _process_pdf_parallel(
                    output_dir, pdf_path, _stem,
                    bookmarks, total_pages, label=pdf_stem
                )
                return  # 并行模式完成
            except Exception as e:
                logger.warning(f"并行模式失败 ({e})，退回串行处理")
        else:
            logger.info("PDF 无书签，退回串行模式")

    # --- 串行模式（完整 PDF → MinerU → 翻译）---

    mineru_out = output_dir / f"{_stem}_mineru"

    # 1. MinerU 解析 PDF → MD + images（兼容 pipeline: auto/ 和 hybrid: hybrid_auto/）
    md_path = mineru_out / _stem / "auto" / f"{_stem}.md"
    hybrid_md_path = mineru_out / _stem / "hybrid_auto" / f"{_stem}.md"
    if hybrid_md_path.exists():
        md_path = hybrid_md_path
    if force or not md_path.exists():
        md_path, images_dir = run_mineru(pdf_path, mineru_out, backend=MINERU_BACKEND)
    else:
        images_dir = md_path.parent / "images"
        if not images_dir.is_dir():
            images_dir = md_path.parent
        logger.info(f"使用已有 MinerU 输出: {md_path}")

    # 2. 读取 MD 原文
    with open(md_path, "r", encoding="utf-8") as f:
        raw_md = f.read()
    logger.info(f"MD 文件大小: {len(raw_md):,} 字符")

    # 2.5 文本规范化
    raw_md = normalize_md(raw_md)

    # 3. 处理图片
    new_md, assets_dir = process_images(raw_md, images_dir, output_dir, pdf_stem)

    # 4. 切分 MD 为块
    blocks = split_md_blocks(new_md)
    text_count = sum(1 for b in blocks if b['type'] == 'text')
    latex_count = sum(1 for b in blocks if b['type'] == 'latex')
    logger.info(f"文档切分: {len(blocks)} 块 (文本 {text_count}, 公式 {latex_count})")

    # 5. 翻译
    db_path = output_dir / f"{_stem}_translate.db"
    db = TranslationDB(db_path)

    translator = DeepSeekTranslator()
    trans_map = translate_blocks(blocks, db, translator)

    # 6. 组装中文/英文 MD（G2 完整性校验：text 块内嵌行内公式/代码损坏则回填）
    zh_lines = []
    en_lines = []
    g2_warnings = []
    for b in blocks:
        content = b['content']
        if b['type'] == 'latex':
            zh_lines.append(content)
            en_lines.append(content)
        else:
            zh = trans_map.get(b['index'], content)
            if ENABLE_INTEGRITY:
                zh, iv_warnings = verify_block(content, zh)
                g2_warnings.extend(iv_warnings)
            zh_lines.append(zh)
            en_lines.append(content)

    zh_md_path = output_dir / f"{pdf_stem}_zh.md"
    en_md_path = output_dir / f"{pdf_stem}_en.md"

    zh_text = "\n\n".join(zh_lines)
    en_text = "\n\n".join(en_lines)

    # 标题层级修正（串行版 fix_headings）—— 仅用于中文版；
    # EN 版保持原文结构，与并行模式一致，不做标题修正
    zh_text, zh_warnings = fix_headings(zh_text)
    if zh_warnings:
        logger.info(f"中文版标题修正: {len(zh_warnings)} 处")

    # 标题修正/G2 完整性警告写入独立日志文件（不污染 zh/en 输出）
    write_warnings_file(output_dir, _stem, g2_warnings + zh_warnings)

    # 表格渲染修复（<img> 行内化 + 冗余属性清理）
    zh_text = fix_table_rendering(zh_text)
    en_text = fix_table_rendering(en_text)
    # HTML 表格 → Markdown 表格（简单表格，公式可渲染）
    zh_text = html_tables_to_md(zh_text)
    en_text = html_tables_to_md(en_text)

    # 输出侧再次归一化（LLM 可能引入异常换行符）
    zh_text = normalize_output(zh_text)
    en_text = normalize_output(en_text)
    # 去重：LLM 可能复读图片引用
    zh_text = dedup_adjacent_images(zh_text)
    en_text = dedup_adjacent_images(en_text)

    with open(zh_md_path, "w", encoding="utf-8") as f:
        f.write(zh_text)
    with open(en_md_path, "w", encoding="utf-8") as f:
        f.write(en_text)

    logger.info(f"翻译完成! 中文版: {zh_md_path}")
    logger.info(f"英文版: {en_md_path}")

    # 7. 清理
    db.close()
    if db_path.exists():
        db_path.unlink()
    # if mineru_out.exists():
    #     shutil.rmtree(mineru_out)
    #     logger.info("临时文件已清理")
    logger.info(f"MinerU 输出保留: {mineru_out}")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="DeepScribe — PDF to Translated Markdown (MD-first pipeline)"
    )
    parser.add_argument("-i", "--input", type=str, default="./input",
                        help="PDF 文件或目录路径 (默认 ./input)")
    parser.add_argument("-o", "--output", type=str, default="./output",
                        help="输出目录 (默认 ./output)")
    parser.add_argument("--force", action="store_true",
                        help="强制重新运行 MinerU 解析")
    parser.add_argument("--parallel", dest="parallel", action="store_true",
                        default=None,
                        help="启用并行翻译模式（需 PDF 含多级书签）")
    parser.add_argument("--no-parallel", dest="parallel", action="store_false",
                        help="禁用并行翻译模式（强制串行）")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        logger.error(f"输入路径不存在: {input_path}")
        return

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        tasks = [(input_path, output_dir)]
    elif input_path.is_dir():
        # 递归发现所有 PDF，并按相对目录镜像输出，避免同 stem 文件互相覆盖
        tasks = []
        for pdf in sorted(input_path.rglob("*.pdf")):
            rel = pdf.parent.relative_to(input_path)
            file_out = output_dir / rel if str(rel) != "." else output_dir
            tasks.append((pdf, file_out))
        if not tasks:
            logger.warning(f"未找到 PDF 文件于 {input_path}")
            return
    else:
        logger.error("输入无效：需为 .pdf 文件或包含 .pdf 的目录")
        return

    failed_files = []
    for pdf, file_out in tasks:
        logger.info(f"--- 开始处理: {pdf} ---")
        file_out.mkdir(parents=True, exist_ok=True)
        try:
            process_pdf(pdf, file_out, args.force, parallel=args.parallel)
        except Exception as e:
            logger.error(f"处理失败: {pdf.name}: {e}", exc_info=True)
            _stem = "_" + hashlib.sha256(pdf.stem.encode()).hexdigest()[:12]
            write_failure_report(file_out, _stem,
                                 [{"kind": "文件", "name": pdf.name, "error": str(e)}])
            failed_files.append((str(pdf), str(e)))

    if failed_files:
        logger.error(f"批处理完成，{len(failed_files)}/{len(tasks)} 个文件失败")
        for name, err in failed_files:
            logger.error(f"  - {name}: {err}")
    else:
        logger.info(f"所有 {len(tasks)} 个文件处理完成")


if __name__ == "__main__":
    main()
