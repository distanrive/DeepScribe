import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as M


class TestDedupAdjacentImages(unittest.TestCase):
    def test_adjacent(self):
        self.assertEqual(M.dedup_adjacent_images("a\n![x](i1)\n![](i1)\nb"),
                         "a\n![x](i1)\nb")

    def test_across_blank_line(self):
        self.assertEqual(M.dedup_adjacent_images("a\n![x](i1)\n\n![](i1)\nb"),
                         "a\n![x](i1)\n\nb")

    def test_keep_one_with_alt(self):
        self.assertEqual(M.dedup_adjacent_images("![](i1)\n\n![x](i1)\nb"),
                         "![x](i1)\n\nb")

    def test_not_dedup_with_body_between(self):
        inp = "a\n![x](i1)\n\n正文\n\n![](i1)\nb"
        self.assertEqual(M.dedup_adjacent_images(inp), inp)

    def test_different_images_kept(self):
        inp = "![a](i1)\n\n![b](i2)"
        self.assertEqual(M.dedup_adjacent_images(inp), inp)

    def test_caption_on_same_line_survives_dedup(self):
        # 回归：MinerU 会把图注和图片排在同一行，整行丢弃会把图注一起吃掉。
        # 去重只该丢图片引用，剩下的文字要留下。
        out = M.dedup_adjacent_images("![](i1)\n![](i1) Figure 3: 能级图")
        self.assertEqual(out, "![](i1)\nFigure 3: 能级图")

    def test_caption_survives_when_keeping_current(self):
        # 前一条无 alt、当前有 alt 且有图注：保留前一条图片 + 当前行的图注
        out = M.dedup_adjacent_images("![](i1)\n![x](i1) 图 2")
        self.assertEqual(out, "![](i1)\n图 2")


class TestProcessImages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.images_dir = self.root / "images"
        self.images_dir.mkdir()
        (self.images_dir / "fig1.png").write_bytes(b"png1")
        (self.images_dir / "fig2.jpg").write_bytes(b"jpg2")
        self.output_dir = self.root / "out"
        self.output_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_rename_and_copy(self):
        md = "![a](fig1.png)\n\n![b](fig2.jpg)"
        new_md, assets = M.process_images(md, self.images_dir, self.output_dir, "doc")
        self.assertIn("![a](doc_zh.assets/image-1.png)", new_md)
        self.assertIn("![b](doc_zh.assets/image-2.jpg)", new_md)
        self.assertTrue((assets / "image-1.png").exists())
        self.assertTrue((assets / "image-2.jpg").exists())

    def test_external_url_skipped(self):
        md = "![x](https://example.com/a.png)"
        new_md, _ = M.process_images(md, self.images_dir, self.output_dir, "doc")
        self.assertIn("https://example.com/a.png", new_md)
        self.assertNotIn("doc_zh.assets", new_md)

    def test_missing_image_renamed_but_not_copied(self):
        md = "![x](missing.png)"
        new_md, assets = M.process_images(md, self.images_dir, self.output_dir, "doc")
        self.assertIn("doc_zh.assets/image-1.png", new_md)
        self.assertFalse((assets / "image-1.png").exists())

    def test_dedup_same_basename(self):
        md = "![a](sub/fig1.png)\n\n![b](fig1.png)"
        new_md, assets = M.process_images(md, self.images_dir, self.output_dir, "doc")
        self.assertIn("doc_zh.assets/image-1.png", new_md)
        self.assertEqual(len(list(assets.glob("*.png"))), 1)

    def test_no_images_creates_assets_dir(self):
        md = "no images here"
        new_md, assets = M.process_images(md, self.images_dir, self.output_dir, "doc")
        self.assertEqual(new_md, md)
        self.assertTrue(assets.is_dir())

    def test_shared_mapping_keeps_both_languages_aligned(self):
        # 回归：并行合并时 zh/en 各调一次 process_images 写同一个 assets 目录。
        # 译文漏掉一张图会让两次调用的编号错开 —— en 的 image-1 指向 zh 的第一张。
        # 共用一份 mapping 后，同一个 image-N 必须是同一张源图。
        zh_src = "![b](fig2.jpg)"                       # 译文漏掉了 fig1（顺序变了）
        en_src = "![a](fig1.png)\n\n![b](fig2.jpg)"
        shared: dict[str, int] = {}
        zh_md, assets = M.process_images(
            zh_src, self.images_dir, self.output_dir, "doc", mapping=shared)
        en_md, _ = M.process_images(
            en_src, self.images_dir, self.output_dir, "doc", quiet=True, mapping=shared)

        # 两份文本里 image-N 的含义一致
        self.assertEqual(shared, {"fig2.jpg": 1, "fig1.png": 2})
        self.assertIn("doc_zh.assets/image-1.jpg", zh_md)
        self.assertIn("doc_zh.assets/image-1.jpg", en_md)   # en 的 b 也是 image-1
        self.assertIn("doc_zh.assets/image-2.png", en_md)   # en 的 a 是 image-2
        # 且磁盘上 image-1 确实是 jpg2、image-2 确实是 png1（内容没串）
        self.assertEqual((assets / "image-1.jpg").read_bytes(), b"jpg2")
        self.assertEqual((assets / "image-2.png").read_bytes(), b"png1")

    def test_mapping_none_keeps_per_call_numbering(self):
        # 不传 mapping 时行为不变（单语言调用：串行路径、仅解析路径都走这条）
        md, _ = M.process_images("![a](fig1.png)", self.images_dir,
                                 self.output_dir, "doc")
        self.assertIn("doc_zh.assets/image-1.png", md)


if __name__ == "__main__":
    unittest.main()
