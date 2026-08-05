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


if __name__ == "__main__":
    unittest.main()
