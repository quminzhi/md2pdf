import argparse
import re
import html
from math import ceil
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Flowable, HRFlowable, KeepTogether
)

HEADER_TEXT = 'Markdown PDF'
ANCHOR_TARGETS = set()

# Bundle static instances of Source Han Sans CN so PDFs do not depend on
# platform-specific system fonts. See fonts/README.md for provenance.
FONT_DIR = Path(__file__).resolve().parent / 'fonts'
for font_name, weight in [('BodySans', 'Regular'),
                          ('BodySansMedium', 'Medium'),
                          ('BodySansBold', 'Bold')]:
    pdfmetrics.registerFont(TTFont(font_name, str(FONT_DIR / f'Md2pdfSansCN-{weight}.ttf')))
pdfmetrics.registerFontFamily('BodySans', normal='BodySans', bold='BodySansBold',
                             italic='BodySans', boldItalic='BodySansBold')
pdfmetrics.registerFontFamily('BodySansMedium', normal='BodySansMedium', bold='BodySansBold',
                             italic='BodySansMedium', boldItalic='BodySansBold')

PAGE_W, PAGE_H = A4
LEFT = 19*mm
RIGHT = 19*mm
TOP = 18*mm
BOTTOM = 17*mm
CONTENT_W = PAGE_W - LEFT - RIGHT

styles = getSampleStyleSheet()
body = ParagraphStyle('BodyCN', parent=styles['BodyText'], fontName='BodySans', fontSize=9.4,
                      leading=14.2, textColor=colors.HexColor('#2B2B2B'), spaceAfter=5.2,
                      alignment=TA_LEFT, splitLongWords=True, wordWrap='CJK',
                      allowWidows=False, allowOrphans=False)
small = ParagraphStyle('SmallCN', parent=body, fontSize=8.1, leading=11.2, textColor=colors.HexColor('#555555'))
h1 = ParagraphStyle('H1CN', parent=body, fontName='BodySansBold', fontSize=19, leading=25,
                    textColor=colors.HexColor('#222222'), spaceBefore=0, spaceAfter=12)
h2 = ParagraphStyle('H2CN', parent=body, fontName='BodySansBold', fontSize=14.2, leading=19,
                    textColor=colors.HexColor('#333333'), spaceBefore=13, spaceAfter=6,
                    keepWithNext=True)
h3 = ParagraphStyle('H3CN', parent=body, fontName='BodySansMedium', fontSize=11.4, leading=16,
                    textColor=colors.HexColor('#444444'), spaceBefore=9, spaceAfter=4,
                    keepWithNext=True)
h4 = ParagraphStyle('H4CN', parent=body, fontName='BodySansMedium', fontSize=10, leading=14,
                    textColor=colors.HexColor('#444444'), spaceBefore=7, spaceAfter=3,
                    keepWithNext=True)
list_style = ParagraphStyle('ListCN', parent=body, leftIndent=13, firstLineIndent=-9,
                            bulletIndent=0, spaceAfter=2.5, leading=13.5)
toc_section_style = ParagraphStyle('TocSectionCN', parent=h3, fontSize=10.2,
                                   leading=13, spaceBefore=6, spaceAfter=1,
                                   keepWithNext=True)
toc_list_style = ParagraphStyle('TocListCN', parent=list_style, fontSize=8.65,
                                leading=11.25, spaceAfter=0.8)
code_style = ParagraphStyle('CodeCN', parent=body, fontName='Courier', fontSize=8,
                            leading=11, textColor=colors.HexColor('#2B2B2B'),
                            spaceBefore=0, spaceAfter=0,
                            wordWrap='CJK', splitLongWords=True)
quote_style = ParagraphStyle('QuoteCN', parent=body, leftIndent=12, rightIndent=6,
                             textColor=colors.HexColor('#555555'),
                             spaceBefore=6, spaceAfter=8)
code_intro_style = ParagraphStyle('CodeIntroCN', parent=body, keepWithNext=True)
table_head_style = ParagraphStyle('TableHeadCN', parent=small, textColor=colors.white, fontName='BodySansMedium')

# These are distances from the visible frame, independent of inner padding.
CODE_PADDING = 9
CODE_SPACE_BEFORE = 10
CODE_SPACE_AFTER = 12


def normalize_chars(text):
    return text.replace('\u2011', '-')


def format_code(text, preserve_spaces=False):
    """Use Courier for ASCII code and the bundled font for Chinese/symbols."""
    rendered = []
    for part in re.split(r'([^\x00-\x7f]+)', text):
        if not part:
            continue
        safe = html.escape(part, quote=False)
        if preserve_spaces:
            safe = safe.replace(' ', '&#160;')
        font = 'Courier' if part.isascii() else 'BodySans'
        rendered.append(f'<font name="{font}">{safe}</font>')
    return ''.join(rendered)

def inline_markup(text):
    # Protect code and links before interpreting emphasis or escaping HTML.
    text = normalize_chars(text)
    code_tokens = []
    def stash_code(m):
        code_tokens.append(m.group(2))
        return f'\x00C{len(code_tokens)-1}\x00'
    s = re.sub(r'(`+)(.+?)\1(?!`)', stash_code, text)
    link_tokens = []
    def stash_link(m):
        label, target = m.group(1), m.group(2)
        rendered = inline_markup(label)
        if (target.startswith('#') and target[1:] in ANCHOR_TARGETS) or \
           re.match(r'^(?:https?://|mailto:)', target, re.I):
            rendered = (f'<a href="{html.escape(target, quote=True)}" '
                        f'color="#444444" underline="1">{rendered}</a>')
        link_tokens.append(rendered)
        return f'\x00L{len(link_tokens)-1}\x00'
    s = re.sub(r'\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^\s()]*(?:\([^()]*\)[^\s()]*)*)\)',
               stash_link, s)
    # Two trailing spaces or a backslash mean a hard break; ordinary source
    # newlines remain soft so wrapped Markdown paragraphs are joined normally.
    s = re.sub(r'(?: {2,}|\\)\n', '\x00BR\x00', s)
    s = html.escape(s.replace('\n', ' '), quote=False)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'__([^_]+)__', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', s)
    s = s.replace('\x00BR\x00', '<br/>')
    for i, value in enumerate(link_tokens):
        s = s.replace(f'\x00L{i}\x00', value)
    for i, value in enumerate(code_tokens):
        s = s.replace(f'\x00C{i}\x00', format_code(value))
    return s


def is_table_start(lines, i):
    if i+1 >= len(lines): return False
    a, b = lines[i].strip(), lines[i+1].strip()
    return ('|' in a and re.match(r'^\s*\|?\s*:?-{3,}', b) is not None and '|' in b)


def split_table_row(line):
    s = line.strip()
    if s.startswith('|'): s = s[1:]
    if s.endswith('|'): s = s[:-1]
    # A pipe in a code span or an escaped pipe is part of a cell.
    cells, cell, fence = [], [], ''
    for token in re.findall(r'\\.|`+|[^\\`|]+|[|\\]', s):
        if token.startswith('`'):
            if not fence:
                fence = token
            elif token == fence:
                fence = ''
        if token == '|' and not fence:
            cells.append(''.join(cell).strip()); cell = []
        else:
            cell.append('|' if token == '\\|' else token)
    cells.append(''.join(cell).strip())
    return cells


def parse_markdown(lines):
    flow = []
    i = 0
    para = []
    def flush_para():
        nonlocal para
        if para:
            txt = '\n'.join(para).strip()
            if txt:
                flow.append(('p', txt))
            para = []
    while i < len(lines):
        line = lines[i].rstrip('\n')
        fence = re.match(r'^\s{0,3}(`{3,}|~{3,})([^`]*)$', line)
        if fence:
            flush_para()
            marker, lang = fence.group(1), fence.group(2).strip()
            closing = re.compile(r'^\s{0,3}' + re.escape(marker[0]) +
                                 '{' + str(len(marker)) + r',}\s*$')
            i += 1; buf = []
            while i < len(lines) and not closing.match(lines[i].rstrip('\n')):
                buf.append(lines[i].rstrip('\n')); i += 1
            if i < len(lines): i += 1
            flow.append(('code', '\n'.join(buf), lang)); continue
        if not line.strip():
            flush_para(); i += 1; continue
        # Common Markdown horizontal rules are structural separators rather
        # than paragraph text.  Treat them explicitly so they render as a
        # rule instead of the literal ``---`` string.
        if re.match(r'^\s{0,3}(?:\*\s*){3,}$', line) or \
           re.match(r'^\s{0,3}(?:-\s*){3,}$', line) or \
           re.match(r'^\s{0,3}(?:_\s*){3,}$', line):
            flush_para(); flow.append(('hr',)); i += 1; continue
        anchor = re.match(r'^\s*<a\s+(?:id|name)=["\']([^"\']+)["\']\s*></a>\s*$', line, re.I)
        if anchor:
            flush_para(); flow.append(('anchor', anchor.group(1))); i += 1; continue
        if re.match(r'^\s{0,3}>', line):
            flush_para(); quoted = []
            while i < len(lines) and re.match(r'^\s{0,3}>', lines[i]):
                quoted.append(re.sub(r'^\s{0,3}> ?', '', lines[i].rstrip('\n')))
                i += 1
            flow.append(('quote', '\n'.join(quoted))); continue
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            flush_para(); flow.append(('h', len(m.group(1)), m.group(2).strip())); i += 1; continue
        if is_table_start(lines, i):
            flush_para()
            headers = split_table_row(lines[i]); i += 2; rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                rows.append(split_table_row(lines[i])); i += 1
            flow.append(('table', headers, rows)); continue
        m = re.match(r'^\s*([-*])\s+(.*)$', line)
        if m:
            flush_para(); items=[]
            while i < len(lines):
                mm = re.match(r'^\s*[-*]\s+(.*)$', lines[i].rstrip('\n'))
                if not mm: break
                items.append(mm.group(1)); i += 1
            flow.append(('ul', items)); continue
        m = re.match(r'^\s*(\d+)\.\s+(.*)$', line)
        if m:
            flush_para(); items=[]
            while i < len(lines):
                mm = re.match(r'^\s*(\d+)\.\s+(.*)$', lines[i].rstrip('\n'))
                if not mm: break
                items.append(mm.group(2)); i += 1
            flow.append(('ol', items, int(m.group(1)))); continue
        para.append(line); i += 1
    flush_para()
    return flow


def code_markup(code):
    # Preserve code indentation while allowing long lines to wrap within the page.
    chunks=[]
    for line in code.split('\n'):
        chunks.append(format_code(line.expandtabs(4), preserve_spaces=True) or '&#160;')
    return '<br/>'.join(chunks)


class CodeBlock(Flowable):
    """A frame whose padding participates in wrapping and page splitting."""
    def __init__(self, code=None, language='', paragraph=None, continued=False):
        super().__init__()
        self.paragraph = paragraph if paragraph is not None else Paragraph(code_markup(code), code_style)
        self.language = language
        self.continued = continued
        self.spaceBefore = CODE_SPACE_BEFORE
        self.spaceAfter = CODE_SPACE_AFTER

    @property
    def label_height(self):
        return 13 if self.continued else 0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        _, content_height = self.paragraph.wrap(availWidth - 2*CODE_PADDING,
                                                 max(0, availHeight - 2*CODE_PADDING - self.label_height))
        self.height = content_height + 2*CODE_PADDING + self.label_height
        return self.width, self.height

    def minimum_start_height(self):
        """Keep compact examples intact, or reserve four lines of long code."""
        if self.paragraph.height <= 16*code_style.leading:
            return self.height
        return 2*CODE_PADDING + self.label_height + 4*code_style.leading

    def split(self, availWidth, availHeight):
        self.wrap(availWidth, availHeight)
        if self.height <= availHeight:
            return [self]
        # Move compact examples intact; a long program may span several pages.
        if self.paragraph.height <= 16*code_style.leading:
            return []
        available = availHeight - 2*CODE_PADDING - self.label_height
        if available < 4*code_style.leading:
            return []
        # Leave at least three visual lines for the continuation page.
        line_count = len(self.paragraph.blPara.lines)
        split_lines = min(int(available // code_style.leading), line_count - 3)
        parts = self.paragraph.split(availWidth - 2*CODE_PADDING,
                                     split_lines*code_style.leading)
        if len(parts) < 2:
            return []
        return [CodeBlock(language=self.language, paragraph=parts[0], continued=self.continued),
                CodeBlock(language=self.language, paragraph=parts[1], continued=True)]

    def draw(self):
        canvas = self.canv
        canvas.setFillColor(colors.HexColor('#F2F2F2'))
        canvas.setStrokeColor(colors.HexColor('#D0D0D0'))
        canvas.setLineWidth(0.5)
        canvas.rect(0, 0, self.width, self.height, stroke=1, fill=1)
        if self.continued:
            label = {'python': 'Python', 'bash': 'Bash', 'text': '文本'}.get(self.language, '代码')
            canvas.setFont('BodySans', 7)
            canvas.setFillColor(colors.HexColor('#777777'))
            canvas.drawString(CODE_PADDING, self.height - CODE_PADDING - 7, label + '（续）')
        self.paragraph.drawOn(canvas, CODE_PADDING, CODE_PADDING)


class KeepCodeStartTogether(KeepTogether):
    """Keep a lead-in with the start of code without moving a whole program."""
    def wrap(self, availWidth, availHeight):
        size = super().wrap(availWidth, availHeight)
        last = self._content[-1]
        if isinstance(last, CodeBlock):
            # KeepTogether uses _H to decide whether to move to a new page,
            # then releases the original flowables for normal splitting.
            self._H -= last.height - last.minimum_start_height()
        return size


def table_column_widths(headers, rows):
    """Allocate space by the typical rendered text width in each column."""
    scores = []
    for col, header in enumerate(headers):
        widths = []
        for row in rows:
            cell = row[col] if col < len(row) else ''
            p = Paragraph(inline_markup(cell), small)
            text = p.getPlainText()
            widths.append(max((pdfmetrics.stringWidth(line, 'BodySans', small.fontSize)
                               for line in text.split('\n')), default=0))
        widths.sort()
        typical = widths[max(0, ceil(len(widths)*0.75) - 1)] if widths else 0
        title_width = pdfmetrics.stringWidth(Paragraph(inline_markup(header), table_head_style).getPlainText(),
                                             'BodySansMedium', small.fontSize)
        scores.append((max(typical, title_width) + 10)**0.85)
    minimum = min(75, CONTENT_W/len(headers)*0.5)
    widths = [0]*len(headers)
    free = set(range(len(headers)))
    remaining = CONTENT_W
    while free:
        total = sum(scores[j] for j in free)
        narrow = {j for j in free if remaining*scores[j]/total < minimum}
        if not narrow:
            for j in free:
                widths[j] = remaining*scores[j]/total
            break
        for j in narrow:
            widths[j] = minimum
            remaining -= minimum
        free -= narrow
    return widths


def make_table(headers, rows):
    ncols = max([len(headers)] + [len(r) for r in rows])
    headers = headers + ['']*(ncols-len(headers))
    data = [[Paragraph(inline_markup(c), table_head_style) for c in headers]]
    for r in rows:
        vals = r + ['']*(ncols-len(r))
        data.append([Paragraph(inline_markup(c), small) for c in vals[:ncols]])
    widths = table_column_widths(headers, rows)
    t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT',
              spaceBefore=6, spaceAfter=9)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#333333')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'BodySansMedium'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.35, colors.HexColor('#BDBDBD')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7F7F7')]),
        ('LEFTPADDING', (0,0), (-1,-1), 5), ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    if len(rows) >= 2:
        frame_height = PAGE_H - TOP - BOTTOM
        t.wrap(CONTENT_W, frame_height)
        # Keep the last two body rows together when they fit under a repeated
        # header. NOSPLIT survives ReportLab's subsequent table fragments.
        if t._rowHeights[0] + sum(t._rowHeights[-2:]) <= frame_height:
            t.setStyle(TableStyle([('NOSPLIT', (0,-2), (-1,-1))]))
    return t


def draw_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#D0D0D0'))
    canvas.setLineWidth(0.5)
    canvas.line(LEFT, PAGE_H-11*mm, PAGE_W-RIGHT, PAGE_H-11*mm)
    canvas.setFont('BodySans', 7.6)
    canvas.setFillColor(colors.HexColor('#666666'))
    canvas.drawString(LEFT, PAGE_H-8*mm, HEADER_TEXT)
    canvas.drawRightString(PAGE_W-RIGHT, 9*mm, f'{canvas.getPageNumber()}')
    canvas.line(LEFT, 12.5*mm, PAGE_W-RIGHT, 12.5*mm)
    canvas.restoreState()


class MarkdownDocTemplate(BaseDocTemplate):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('keepTogetherClass', KeepCodeStartTogether)
        super().__init__(*args, **kwargs)

    def afterFlowable(self, flowable):
        for name in getattr(flowable, '_anchor_names', ()):
            self.canv.bookmarkPage(name)
        if hasattr(flowable, '_outline'):
            title, key, level = flowable._outline
            # PDF outline levels must not skip a parent, even for Markdown
            # which starts at h2 or omits an intermediate heading level.
            previous = getattr(self, '_outline_level', -1)
            level = min(level, previous + 1)
            self.canv.addOutlineEntry(title, key, level=level, closed=level > 0)
            self._outline_level = level


def build(src, out):
    global HEADER_TEXT, ANCHOR_TARGETS
    with open(src, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    parsed = parse_markdown(lines)
    ANCHOR_TARGETS = {item[1] for item in parsed if item[0] == 'anchor'}
    doc_title = next((item[2] for item in parsed if item[0] == 'h' and item[1] == 1), Path(src).stem)
    HEADER_TEXT = doc_title
    story=[]
    pending_anchors = []
    in_toc = False
    def make_paragraph(text, style, extra_anchor=None):
        names = pending_anchors + ([extra_anchor] if extra_anchor else [])
        prefix = ''.join(f'<a name="{html.escape(name, quote=True)}"/>' for name in names)
        pending_anchors.clear()
        paragraph = Paragraph(prefix + inline_markup(text), style)
        paragraph._anchor_names = tuple(names)
        return paragraph

    for item_index, item in enumerate(parsed):
        typ = item[0]
        if typ == 'anchor':
            pending_anchors.append(item[1])
        elif typ == 'h':
            level, txt = item[1], item[2]
            if level == 2 and txt.strip() == '目录':
                in_toc = True
            elif in_toc and level == 2:
                in_toc = False
            style = h1 if level == 1 else h2 if level == 2 else \
                toc_section_style if in_toc and level == 3 else \
                h3 if level == 3 else h4
            plain = Paragraph(inline_markup(txt), style).getPlainText()
            title_width = pdfmetrics.stringWidth(plain, style.fontName, style.fontSize)
            if level == 1 and CONTENT_W < title_width <= CONTENT_W*1.12:
                size = style.fontSize*CONTENT_W/title_width*0.99
                style = ParagraphStyle('FittedH1CN', parent=style, fontSize=size)
            key = f'md2pdf-heading-{len(story)}'
            p = make_paragraph(txt, style, extra_anchor=key)
            p._outline = (plain, key, min(level-1, 3))
            story.append(p)
            if level == 1:
                story.append(HRFlowable(width='100%', thickness=1.2, color=colors.HexColor('#666666'), spaceAfter=8))
        elif typ == 'p':
            next_typ = parsed[item_index + 1][0] if item_index + 1 < len(parsed) else None
            style = code_intro_style if next_typ == 'code' else body
            story.append(make_paragraph(item[1], style))
        elif typ == 'quote':
            story.append(make_paragraph(item[1], quote_style))
        elif typ == 'code':
            story.append(CodeBlock(item[1], item[2]))
        elif typ == 'table':
            story.append(make_table(item[1], item[2]))
        elif typ == 'hr':
            in_toc = False
            story.append(HRFlowable(width='100%', thickness=0.6,
                                    color=colors.HexColor('#BDBDBD'),
                                    spaceBefore=3, spaceAfter=8))
        elif typ == 'ul':
            item_style = toc_list_style if in_toc else list_style
            for text in item[1]:
                story.append(make_paragraph('• ' + text, item_style))
            story.append(Spacer(1, 2))
        elif typ == 'ol':
            for idx, text in enumerate(item[1], item[2]):
                story.append(make_paragraph(f'{idx}. ' + text, list_style))
            story.append(Spacer(1, 2))
    frame = Frame(LEFT, BOTTOM, CONTENT_W, PAGE_H-TOP-BOTTOM, id='normal', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = MarkdownDocTemplate(out, pagesize=A4, leftMargin=LEFT, rightMargin=RIGHT, topMargin=TOP, bottomMargin=BOTTOM,
                          title=doc_title, author='Codex')
    doc.addPageTemplates([PageTemplate(id='main', frames=frame, onPage=draw_page)])
    doc.build(story)

def main():
    parser = argparse.ArgumentParser(description='将 Markdown 转换为简约黑白灰风格 PDF。')
    parser.add_argument('input', type=Path, help='输入 Markdown 文件')
    parser.add_argument('-o', '--output', type=Path, help='输出 PDF 路径；默认与输入文件同名')
    args = parser.parse_args()
    src = args.input.expanduser().resolve()
    if not src.is_file():
        parser.error(f'找不到输入文件: {src}')
    out = (args.output.expanduser() if args.output else src.with_suffix('.pdf')).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    build(str(src), str(out))
    print(out)

if __name__ == '__main__':
    main()
