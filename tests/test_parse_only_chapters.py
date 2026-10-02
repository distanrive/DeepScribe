"""仅解析 + 分章输出：必须真的产出 `output/part/`。

这条曾经**静默失效**：`_parse_only_parallel()` 从不写 `output/part/`，而且
`process_pdf()` 压根没把 `output_chapters` 传进 `_parse_only()` —— 勾上「分章输出」
什么也不发生，不报错、日志里也没有痕迹，只有去 output 目录里翻才发现没有 part/。

MinerU 不能真跑，所以把三处外部依赖换成假的：书签拆分、`run_mineru`、
`process_images`。假 `process_images` 会**按真实命名规则建出资产目录**，
因为待测代码随后要靠这些目录把它们搬去 `output/part/` —— 不建目录就测不到搬移那一段。
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as M  # noqa: E402

_TITLES = ("第一章 引言", "第二章 方法: 绪论")     # 第二个带 Windows 非法字符「:」


def _fake_split_pdf_by_bookmarks(pdf_path, bookmarks, total_pages, out_dir, stem,
                                 max_chapter_pages=0):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, title in enumerate(_TITLES):
        sub = out_dir / f"{stem}_p{i:02d}.pdf"
        sub.write_bytes(b"%PDF-1.4\n")
        parts.append((title, sub))
    return parts


## 章节正文里塞一张 HTML 表格：后处理（`_postprocess_md`）会把它转成 Markdown 表格，
## 所以「输出里还有没有 `<table>`」就是「后处理跑没跑」的判据。
_HTML_TABLE = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"


def _fake_run_mineru(pdf_path, out_dir, backend="pipeline", short_stem=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{Path(pdf_path).stem}.md"
    md.write_text(f"# {Path(pdf_path).stem}\n\n{_HTML_TABLE}\n", encoding="utf-8")
    images = out_dir / "images"
    images.mkdir(exist_ok=True)
    (images / "image-1.jpg").write_bytes(b"jpg")
    return md, images


def _fake_process_images(md_text, images_dir, out_dir, prefix="", quiet=False,
                         asset_suffix=""):
    # 真实实现的资产目录名就是 `{prefix}{asset_suffix}.assets`
    assets = Path(out_dir) / f"{prefix}{asset_suffix}.assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "image-1.jpg").write_bytes(b"jpg")
    return md_text, assets


class _ParseOnlyCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ds_parse_only_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.output_dir = self.tmp / "out"
        self.output_dir.mkdir()
        self.temp_dir = self.tmp / "tmp"
        self.temp_dir.mkdir()
        self.pdf = self.tmp / "book.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")
        self._stem = "_deadbeefcafe"

        for name, fake in (
            ("split_pdf_by_bookmarks", _fake_split_pdf_by_bookmarks),
            ("run_mineru", _fake_run_mineru),
            ("process_images", _fake_process_images),
            ("extract_bookmarks", lambda p: ([{"level": 1, "title": "第一章", "page": 1}], 10)),
        ):
            patcher = mock.patch.object(M, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, output_chapters: bool) -> None:
        M._parse_only(self.pdf, self.output_dir, self.temp_dir, self._stem,
                      force=False, mineru_lock=None, progress_callback=None,
                      parallel=True, output_chapters=output_chapters)


class TestParseOnlyChapterOutput(_ParseOnlyCase):
    def test_writes_one_md_per_chapter(self):
        self._run(output_chapters=True)
        part_dir = self.output_dir / "part"
        self.assertTrue(part_dir.is_dir(), "勾了分章输出，output/part/ 却没建出来")
        written = sorted(p.name for p in part_dir.glob("*.md"))
        self.assertEqual(
            written,
            ["00_第一章 引言.md", "01_第二章 方法_ 绪论.md"],
            "分章文件命名应当是 {NN}_{标题}.md，且标题里的 Windows 非法字符要替换掉")

    def test_chapter_md_matches_the_merged_file(self):
        """分章文件与合并版必须是同一份文本，否则读者会看到两个版本。"""
        self._run(output_chapters=True)
        merged = (self.output_dir / "book_parsed.md").read_text(encoding="utf-8")
        for p in sorted((self.output_dir / "part").glob("*.md")):
            text = p.read_text(encoding="utf-8")
            self.assertIn(text.strip(), merged,
                          f"{p.name} 的内容不在合并版里 —— 两份输出对不上")
            self.assertTrue(text.strip(), f"{p.name} 是空的")

    def test_chapter_assets_are_moved_next_to_the_md(self):
        """各章 md 引用的 `{_stem}_ch{i}_parsed.assets/` 必须搬过去，否则图全是死链。"""
        self._run(output_chapters=True)
        part_dir = self.output_dir / "part"
        for i in range(len(_TITLES)):
            self.assertTrue(
                (part_dir / f"{self._stem}_ch{i}_parsed.assets").is_dir(),
                f"第 {i} 章的图片目录没搬进 output/part/ —— 那个 md 里的图会全是死链")

    def test_merged_assets_still_written(self):
        self._run(output_chapters=True)
        self.assertTrue((self.output_dir / "book_parsed.assets").is_dir(),
                        "合并版的资产目录不能因为开了分章输出就丢掉")

    def test_temp_part_dir_is_cleaned(self):
        self._run(output_chapters=True)
        self.assertFalse((self.temp_dir / "part").exists(),
                         "temp 里的 part 目录是中间产物，搬完该清掉")

    def test_off_writes_nothing(self):
        self._run(output_chapters=False)
        self.assertFalse((self.output_dir / "part").exists(),
                         "没勾分章输出却建了 output/part/")


class TestParseOnlyIsPostprocessed(_ParseOnlyCase):
    """仅解析的产出也要过输出侧后处理 —— 它**也是正式产出**。

    以前只有翻译模式做这一步（表格渲染修复 / HTML 表格转 MD / 归一化 / 相邻图片去重），
    仅解析出来的 md 里 `<table>` 原样留着：同一份 PDF，翻不翻译得到两种质量的东西。
    """

    def test_parallel_merged_output(self):
        self._run(output_chapters=True)
        merged = (self.output_dir / "book_parsed.md").read_text(encoding="utf-8")
        self.assertNotIn("<table>", merged, "并行仅解析的合并版没做后处理")
        self.assertIn("| A | B |", merged)

    def test_parallel_chapter_output(self):
        self._run(output_chapters=True)
        parts = sorted((self.output_dir / "part").glob("*.md"))
        self.assertEqual(len(parts), len(_TITLES))
        for p in parts:
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("<table>", text, f"{p.name} 没做后处理")
            self.assertIn("| A | B |", text)

    def test_serial_output(self):
        """串行那条路（无书签 / 关掉自动分章）同样要过一遍。"""

        def fake_parse(pdf_path, output_dir, temp_dir, stem, force, lock, cb,
                       asset_suffix=""):
            assets = Path(output_dir) / f"book{asset_suffix}.assets"
            assets.mkdir(parents=True, exist_ok=True)
            return _HTML_TABLE, assets

        with mock.patch.object(M, "_parse_pdf_to_md", fake_parse):
            M._parse_only(self.pdf, self.output_dir, self.temp_dir, self._stem,
                          force=False, mineru_lock=None, progress_callback=None,
                          parallel=False, output_chapters=True)
        text = (self.output_dir / "book_parsed.md").read_text(encoding="utf-8")
        self.assertNotIn("<table>", text, "串行仅解析没做后处理")
        self.assertIn("| A | B |", text)


class TestProcessPdfForwardsTheSwitch(unittest.TestCase):
    """`process_pdf()` 必须把 `output_chapters` 转到仅解析那条路上。

    这正是当初漏掉的一环：`_parse_only()` 自己支持了参数，但 `process_pdf()` 的
    调用点没传 —— 于是 GUI 传下来的开关在仅解析模式下被判死刑。
    """

    def test_forwarded(self):
        src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        start = src.index("if parse_only:")
        call = src[start:src.index("return", start)]
        self.assertIn("_parse_only(", call)
        self.assertIn("output_chapters", call,
                      "process_pdf 没把 output_chapters 传给 _parse_only()")


if __name__ == "__main__":
    unittest.main()
