import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as M


class TestHtmlTablesToMD(unittest.TestCase):
    def test_simple_table(self):
        html = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"
        expected = "| A | B |\n| --- | --- |\n| C | D |"
        self.assertEqual(M.html_tables_to_md(html), expected)

    def test_rowspan_expansion(self):
        html = ('<table><tr><td rowspan="2">A</td><td>B</td></tr>'
                '<tr><td>C</td></tr></table>')
        expected = "| A | B |\n| --- | --- |\n| A | C |"
        self.assertEqual(M.html_tables_to_md(html), expected)

    def test_colspan_expansion(self):
        html = ('<table><tr><td colspan="2">A</td></tr>'
                '<tr><td>B</td><td>C</td></tr></table>')
        expected = "| A | A |\n| --- | --- |\n| B | C |"
        self.assertEqual(M.html_tables_to_md(html), expected)

    def test_single_row_kept_as_html(self):
        html = "<table><tr><td>A</td></tr></table>"
        self.assertEqual(M.html_tables_to_md(html), html)

    def test_whitespace_tolerant(self):
        html = ("<table>\n  <tr><td>A</td><td>B</td></tr>\n"
                "  <tr><td>C</td><td>D</td></tr>\n</table>")
        expected = "| A | B |\n| --- | --- |\n| C | D |"
        self.assertEqual(M.html_tables_to_md(html), expected)


class TestFixTableRendering(unittest.TestCase):
    def test_img_inline_in_td(self):
        md = '<td>![alt](assets/image-1.png)</td>'
        out = M.fix_table_rendering(md)
        self.assertIn('<img src="assets/image-1.png"', out)
        self.assertIn('alt="alt"', out)
        self.assertNotIn('![', out)

    def test_redundant_rowspan_colspan_removed(self):
        md = '<td rowspan="1" colspan="1">x</td>'
        self.assertEqual(M.fix_table_rendering(md), '<td>x</td>')

    def test_keeps_non_image_td_untouched(self):
        md = '<td>plain text</td>'
        self.assertEqual(M.fix_table_rendering(md), '<td>plain text</td>')


if __name__ == "__main__":
    unittest.main()
