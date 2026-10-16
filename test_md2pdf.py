"""Focused layout/content regression checks; no output files are written.

Run: python3 -B -m unittest -v test_md2pdf
"""
import io
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
from unittest.mock import mock_open, patch

sys.path.insert(0, str(Path(__file__).resolve().parent / '.md2pdf-lib'))
import md2pdf as md


class RecordingDocument(md.MarkdownDocTemplate):
    def __init__(self, output):
        super().__init__(output, pagesize=md.A4)
        self.records = []
        frame = md.Frame(md.LEFT, md.BOTTOM, md.CONTENT_W,
                         md.PAGE_H-md.TOP-md.BOTTOM, id='test',
                         leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([md.PageTemplate(id='test', frames=frame)])

    def afterFlowable(self, item):
        super().afterFlowable(item)
        if isinstance(item, (md.Paragraph, md.CodeBlock, md.Table)):
            self.records.append((item, self.page, self.frame._y))


class LayoutTests(unittest.TestCase):
    def render(self, source):
        output = io.BytesIO()
        with patch.object(md, 'open', mock_open(read_data=source), create=True):
            md.build('fixture.md', output)
        return output.getvalue()

    def test_code_frame_has_real_outer_spacing_and_inner_padding(self):
        before = md.Paragraph('Before', md.body)
        block = md.CodeBlock('    x = 1\n\n    y = 2', 'python')
        after = md.Paragraph('After', md.body)
        doc = RecordingDocument(io.BytesIO())
        doc.build([before, block, after])
        first, middle, last = doc.records
        self.assertEqual([r[1] for r in doc.records], [1, 1, 1])
        # Frame._y already includes each flowable's trailing space.
        before_bottom = first[2] + before.getSpaceAfter()
        block_bottom = middle[2] + block.getSpaceAfter()
        after_top = last[2] + after.getSpaceAfter() + after.height
        self.assertAlmostEqual(before_bottom - (block_bottom + block.height), md.CODE_SPACE_BEFORE)
        self.assertAlmostEqual(block_bottom - after_top, md.CODE_SPACE_AFTER)
        self.assertAlmostEqual(block.height - block.paragraph.height, 2*md.CODE_PADDING)
        self.assertAlmostEqual(block.width, md.CONTENT_W)
        self.assertEqual(len(block.paragraph.blPara.lines), 3)

    def test_short_example_moves_intact_to_next_page(self):
        block = md.CodeBlock('\n'.join(f'line_{i}' for i in range(10)))
        doc = RecordingDocument(io.BytesIO())
        doc.build([md.Spacer(1, 650), block])
        self.assertEqual([(r[0], r[1]) for r in doc.records], [(block, 2)])

    def test_heading_and_intro_move_with_a_short_example(self):
        heading = md.Paragraph('Example', md.h3)
        intro = md.Paragraph('The following example:', md.code_intro_style)
        block = md.CodeBlock('\n'.join(f'line_{i}' for i in range(10)))
        doc = RecordingDocument(io.BytesIO())
        doc.build([md.Spacer(1, 650), heading, intro, block])
        self.assertEqual([r[1] for r in doc.records], [2, 2, 2])

    def test_intro_keeps_long_code_start_without_moving_whole_program(self):
        heading = md.Paragraph('Example', md.h3)
        intro = md.Paragraph('The following program:', md.code_intro_style)
        block = md.CodeBlock('\n'.join(f'marker_{i:03d}' for i in range(60)))
        doc = RecordingDocument(io.BytesIO())
        doc.build([md.Spacer(1, 500), heading, intro, block])
        self.assertEqual([r[1] for r in doc.records[:3]], [1, 1, 1])
        fragments = [(item, page) for item, page, _ in doc.records
                     if isinstance(item, md.CodeBlock)]
        self.assertEqual([page for _, page in fragments], [1, 2])
        self.assertGreaterEqual(len(fragments[0][0].paragraph.blPara.lines), 4)
        markers = [marker for item, _ in fragments
                   for marker in re.findall(r'marker_\d{3}', item.paragraph.getPlainText())]
        self.assertEqual(markers, [f'marker_{i:03d}' for i in range(60)])

    def test_intro_moves_when_code_start_has_insufficient_space(self):
        heading = md.Paragraph('Example', md.h3)
        intro = md.Paragraph('The following program:', md.code_intro_style)
        block = md.CodeBlock('\n'.join(f'line_{i}' for i in range(60)))
        doc = RecordingDocument(io.BytesIO())
        doc.build([md.Spacer(1, 650), heading, intro, block])
        self.assertEqual([r[1] for r in doc.records], [2, 2, 2])

    @unittest.skipUnless(shutil.which('pdftotext'), 'Poppler is needed for content checks')
    def test_long_program_keeps_every_line_once_across_pages(self):
        code = '\n'.join(f'    marker_{i:03d} = "<&> {i}"' for i in range(180))
        pdf = self.render('Before\n\n```python\n' + code + '\n```\n\nAfter\n')
        text = subprocess.run(['pdftotext', '-layout', '-', '-'], input=pdf,
                              capture_output=True, check=True).stdout.decode()
        self.assertEqual(re.findall(r'marker_\d{3}', text), [f'marker_{i:03d}' for i in range(180)])
        self.assertIn('<&> 179', text)
        self.assertGreaterEqual(text.count('续'), 2)
        self.assertIn('Before', text)
        self.assertIn('After', text)

    def test_long_code_line_wraps_inside_padding(self):
        block = md.CodeBlock('x' * 220)
        block.wrap(md.CONTENT_W, 1000)
        self.assertGreater(len(block.paragraph.blPara.lines), 1)
        self.assertAlmostEqual(block.paragraph.width, md.CONTENT_W - 2*md.CODE_PADDING)

    def test_code_preserves_tabs_symbols_and_blank_lines(self):
        markup = md.code_markup('\t<&>\n\n中文\u2011字符')
        self.assertIn('&#160;'*4, markup)
        self.assertIn('&lt;&amp;&gt;', markup)
        self.assertEqual(markup.count('<br/>'), 2)
        self.assertIn('\u2011', markup)

    def test_hard_breaks_and_quotes_keep_markdown_meaning(self):
        flow = md.parse_markdown(['one  \n', 'two\n', 'three\n', '\n', '> quote\n'])
        self.assertEqual(md.inline_markup(flow[0][1]), 'one<br/>two three')
        self.assertEqual(flow[1], ('quote', 'quote'))
        self.assertEqual(md.inline_markup('a\\\nb'), 'a<br/>b')

    def test_ordered_list_keeps_start_number(self):
        self.assertEqual(md.parse_markdown(['7. seven', '8. eight']),
                         [('ol', ['seven', 'eight'], 7)])

    def test_nested_fence_does_not_close_a_longer_fence(self):
        source = ['````python', 'print("```")', '```', '````', '~~~text', 'x', '~~~']
        self.assertEqual(md.parse_markdown(source),
                         [('code', 'print("```")\n```', 'python'), ('code', 'x', 'text')])

    def test_table_does_not_split_escaped_or_code_pipes(self):
        self.assertEqual(md.split_table_row(r'| a\|b | `x|y` | ``x`|y`` |'),
                         ['a|b', '`x|y`', '``x`|y``'])

    def test_table_reserves_more_space_for_long_prose(self):
        widths = md.table_column_widths(['Question', 'Explanation', 'Ref'],
                                        [['短问题', '详细解释内容'*10, 'S01']]*3)
        self.assertAlmostEqual(sum(widths), md.CONTENT_W)
        self.assertGreater(widths[1], widths[0])
        self.assertGreater(widths[1], widths[2])
        self.assertGreaterEqual(min(widths), 75)

    def test_table_keeps_final_two_rows_across_multiple_splits(self):
        table = md.make_table(['Term', 'Meaning'],
                              [[f'row_{i:03d}', 'Definition'] for i in range(69)])
        doc = RecordingDocument(io.BytesIO())
        doc.build([table])
        fragments = [item for item, _, _ in doc.records if isinstance(item, md.Table)]
        self.assertGreaterEqual(len(fragments), 3)
        self.assertTrue(all(len(item._cellvalues) >= 3 for item in fragments))
        terms = []
        for item in fragments:
            self.assertEqual(item._cellvalues[0][0][0].getPlainText(), 'Term')
            terms.extend(row[0][0].getPlainText() for row in item._cellvalues[1:])
        self.assertEqual(terms, [f'row_{i:03d}' for i in range(69)])

    def test_table_allows_tall_final_rows_to_use_separate_pages(self):
        table = md.make_table(['Term', 'Meaning'],
                              [['short', 'Definition'], ['tall_1', 'Long text '*350],
                               ['tall_2', 'Long text '*350]])
        doc = RecordingDocument(io.BytesIO())
        doc.build([table])
        fragments = [item for item, _, _ in doc.records if isinstance(item, md.Table)]
        self.assertGreater(len(fragments), 1)
        terms = [row[0][0].getPlainText() for item in fragments
                 for row in item._cellvalues[1:]]
        self.assertEqual(terms, ['short', 'tall_1', 'tall_2'])

    def test_links_keep_emphasis_code_and_parentheses(self):
        markup = md.inline_markup('[**Docs** `fn`](https://example.org/a_(b)?x=1&y=2)')
        self.assertIn('href="https://example.org/a_(b)?x=1&amp;y=2"', markup)
        self.assertIn('<b>Docs</b>', markup)
        self.assertIn('name="Courier">fn', markup)
        self.assertNotIn('\x00', markup)

    @unittest.skipUnless(shutil.which('pdfinfo'), 'Poppler is needed for navigation checks')
    def test_internal_and_external_destinations_survive_export(self):
        source = ('# Title\n\n[Chapter](#chapter) [Website](https://example.org/)\n\n'
                  '<a id="chapter"></a>\n## Chapter\n\nBody\n')
        pdf = self.render(source)
        urls = subprocess.run(['pdfinfo', '-url', '-'], input=pdf,
                              capture_output=True, check=True).stdout.decode()
        # ReportLab resolves named anchors into explicit page destinations.
        # pdfinfo -dests only lists the optional named-destination dictionary.
        self.assertRegex(pdf, br'/Dest\s*\[\s*\d+\s+\d+\s+R\s+/Fit\s*\]')
        self.assertIn(b'/Type /Outlines', pdf)
        self.assertIn('https://example.org/', urls)


if __name__ == '__main__':
    unittest.main()
