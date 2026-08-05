import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as M


class TestSplitMDBlocks(unittest.TestCase):
    def test_basic(self):
        blocks = M.split_md_blocks("para1\n\npara2")
        self.assertEqual(
            [(b['type'], b['index'], b['content']) for b in blocks],
            [('text', 0, 'para1'), ('text', 1, 'para2')],
        )

    def test_formula_trailing_caption_split(self):
        # $$ 公式块后同块内跟正文（图注）→ 自动拆 latex + text，避免漏译
        blocks = M.split_md_blocks("para\n\n$$formula$$\n图注\n\npara2")
        self.assertEqual(
            [(b['type'], b['index']) for b in blocks],
            [('text', 0), ('latex', 1), ('text', 2), ('text', 3)],
        )
        self.assertEqual(blocks[1]['content'], "$$formula$$")
        self.assertEqual(blocks[2]['content'], "图注")

    def test_inline_formula_is_latex(self):
        blocks = M.split_md_blocks("$$x$$")
        self.assertEqual(blocks, [{'type': 'latex', 'index': 0, 'content': '$$x$$'}])

    def test_unclosed_formula_is_latex(self):
        blocks = M.split_md_blocks("$$unclosed")
        self.assertEqual(blocks[0]['type'], 'latex')
        self.assertEqual(blocks[0]['content'], "$$unclosed")

    def test_empty_input(self):
        self.assertEqual(M.split_md_blocks(""), [])
        self.assertEqual(M.split_md_blocks("  \n\n  "), [])

    def test_indices_monotonic_across_types(self):
        blocks = M.split_md_blocks("t0\n\n$$f$$\n\n$$g$$\n\nt1")
        indices = [b['index'] for b in blocks]
        self.assertEqual(indices, sorted(indices))


if __name__ == "__main__":
    unittest.main()
