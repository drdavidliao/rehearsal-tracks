"""Printable lesson-plan checklist (US Letter PDF) from a Planner's plan."""
import os
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, KeepTogether, Table, TableStyle)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape as E

def _font_dir():
    """DejaVu has the ☐ ▶ ↓ ♭ ♯ glyphs the plan uses: the system copy, or the one matplotlib ships"""
    import glob as _g
    for d in ('/usr/share/fonts/truetype/dejavu/', '/Library/Fonts/', os.path.expanduser('~/Library/Fonts/')):
        if os.path.exists(os.path.join(d, 'DejaVuSans.ttf')): return d
    try:
        import matplotlib
        return os.path.join(matplotlib.get_data_path(), 'fonts', 'ttf') + '/'
    except ImportError:
        raise SystemExit('needs the DejaVu fonts: pip install matplotlib, or install fonts-dejavu')


FD = _font_dir()
pdfmetrics.registerFont(TTFont('Sans', FD + 'DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('Sans-Bold', FD + 'DejaVuSans-Bold.ttf'))
pdfmetrics.registerFont(TTFont('Sans-Oblique', FD + 'DejaVuSans-Oblique.ttf'))
pdfmetrics.registerFont(TTFont('Sans-BoldOblique', FD + 'DejaVuSans-BoldOblique.ttf'))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily('Sans', normal='Sans', bold='Sans-Bold', italic='Sans-Oblique', boldItalic='Sans-BoldOblique')

INK = colors.HexColor('#1a1a1a')
GREY = colors.HexColor('#5a5a5a')
RULE = colors.HexColor('#bbbbbb')
TINT = colors.HexColor('#eeeeee')

BOX = '☐'


def st(name, size=9.5, lead=None, indent=0, font='Sans', color=INK, before=0, after=0, first=None):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=lead or size * 1.3, leftIndent=indent,
                          firstLineIndent=(-first if first else 0), textColor=color, spaceBefore=before, spaceAfter=after)


TITLE = st('title', 15, font='Sans-Bold', after=2)
SUB = st('sub', 8.5, color=GREY, after=8)
H = st('h', 10.5, font='Sans-Bold', before=9, after=1, indent=14, first=14)
NOTE = st('note', 7.5, color=GREY, indent=26)
NOTE2 = st('note2', 7.5, color=GREY, indent=40)
L1 = st('l1', 8.5, indent=28, first=13, before=2)
L2 = st('l2', 8, indent=44, first=12)
L3 = st('l3', 8, indent=60, first=12)
SMALL = st('small', 7.5, color=GREY)
SAY = st('say', 8, font='Sans-Oblique', color=INK, indent=26, after=1)
SAY2 = st('say2', 7.5, font='Sans-Oblique', color=INK, indent=44)
SAY3 = st('say3', 7.5, font='Sans-Oblique', color=INK, indent=60)
CELL = st('cell', 7.5, lead=9.3)
CELLB = st('cellb', 7.5, lead=9.3, font='Sans-Bold')


def cue(c):
    if not c: return ''
    at = c[2] if len(c) > 2 else c[0]
    s = f'&nbsp;&nbsp;<font color="#444444"><b>&#9654;&nbsp;/{at}</b></font>'
    if len(c) > 2 and str(c[2]) != str(c[0]):
        s += f'<font color="#444444" size="7"> (printed m{c[0]})</font>'
    if c[1]: s += f'<font color="#444444" size="7"> in on beat {c[1]}</font>'
    return s


LCOL = {'Soprano': '#D55E00', 'Alto': '#B8860B', 'Tenor': '#009E73', 'Bass': '#0072B2'}


def lab(it):
    if not it.get('label'): return ''
    ps = it.get('parts') or []
    col = LCOL.get(ps[0], '#7B3FA0') if len(ps) == 1 else '#7B3FA0'
    return f'<font color="{col}"><b>{it["label"]}</b></font>&nbsp;&nbsp;'


def short(it):
    from . import plan as _p
    segs = _p.notation(it, cues=True)
    return ' <font color="#5a5a5a">·</font> '.join(f'<b>{E(t_)}</b>' + (cue(c_) if c_ else '') for t_, c_ in segs)


def say(text, style):
    return Paragraph(f'<font color="#777777">Say:</font> \u201c{E(text)}\u201d', style)


def item(style, text, c=None):
    return Paragraph(f'{BOX}&nbsp;&nbsp;{text}{cue(c)}', style)


def section_flow(sec):
    chunks = [[]]
    fl = chunks[0]
    kind = {'new': '', 'near': 'nearly a repeat', 'repeat': 'repeat', 'skip': 'piano only'}.get(sec['kind'], '')
    tag = f'&nbsp;&nbsp;<font size="7.5" color="#5a5a5a">{kind}</font>' if kind else ''
    fl.append(Paragraph(f'{BOX}&nbsp;&nbsp;<b>{E(sec["letter"])}</b>&nbsp;&nbsp;m{sec["a"]}–{sec["b"]}'
                        f'{cue(sec["cue"]) if sec["kind"] != "skip" else ""}{tag}', H))
    for n in sec['notes']:
        fl.append(Paragraph(E(n), NOTE))
    if sec.get('say'):
        fl.append(say(sec['say'].strip(), SAY))
    for idx, it in enumerate(sec['items']):
        if idx > 0:
            chunks.append([]); fl = chunks[-1]
        if it['kind'] == 'part':
            nt = f' <font color="#5a5a5a" size="7.5">({E(it["note"])})</font>' if it['note'] else ''
            fl.append(item(L1, f'{lab(it)}<b>{E(it["who"])}</b>&nbsp;&nbsp;{short(it)}{nt}'))
            if it.get('say'): fl.append(say(it['say'], SAY2))
        elif it['kind'] == 'block':
            fl.append(item(L1, f'<b>{E(it["text"])}</b>', it['cue']))
            if it.get('why'):
                fl.append(Paragraph(f'<font color="#7a5c00">Why: {E(it["why"])}</font>', NOTE2))
            for jn, jt in enumerate(it['items']):
                if jn > 0:
                    chunks.append([]); fl = chunks[-1]
                if jt['kind'] == 'part':
                    nt = f' <font color="#5a5a5a" size="7.5">({E(jt["note"])})</font>' if jt['note'] else ''
                    fl.append(item(L2, f'{lab(jt)}<b>{E(jt["who"])}</b>&nbsp;&nbsp;{short(jt)}{nt}'))
                    if jt.get('say'): fl.append(say(jt['say'], SAY3))
                else:
                    fl.append(item(L2, E(jt['text']), jt.get('cue')))
        elif it['kind'] == 'rhythm':
            who_ = 'Everyone' if len(it['parts']) == 4 else '+'.join(it['parts'])
            fl.append(item(L1, f'{lab(it)}<b>{E(who_)}</b>&nbsp;&nbsp;{short(it)}', it.get('cue')))
            if it.get('say'): fl.append(say(it['say'], SAY2))
        else:
            top = ' from the top' if 'top' in it['text'] else ''
            fl.append(item(L1, f'{lab(it)}<b>Everyone{top}</b>&nbsp;&nbsp;<b>{"S↓+S" if it.get("slow") else "S"}</b>' + (' <font size="7" color="#5a5a5a">(new key: give starting pitches)</font>' if 'new key' in it['text'] else ''), it.get('cue')))
            if it.get('say'): fl.append(say(it['say'], SAY2))
    return chunks


def overview(plan):
    rows = [[Paragraph('Ltr', CELLB), Paragraph('Bars', CELLB), Paragraph('Cue', CELLB), Paragraph('What it is', CELLB)]]
    for s in plan:
        what = {'skip': 'Piano only', 'repeat': s['notes'][0] if s['notes'] else 'Repeat',
                'near': s['notes'][0] if s['notes'] else 'Nearly a repeat'}.get(s['kind'])
        if s['kind'] == 'new':
            what = 'New. ' + s['notes'][0]
            if any(n.startswith('Long or hard') for n in s['notes']): what += ' In halves.'
        c = s['cue']
        cs = '' if s['kind'] == 'skip' else f'/{c[2] if len(c) > 2 else c[0]}' + (f' (in beat {c[1]})' if c[1] else '')
        rows.append([Paragraph(f'<b>{E(s["letter"])}</b>', CELL), Paragraph(f'{s["a"]}–{s["b"]}', CELL),
                     Paragraph(cs, CELL), Paragraph(E(what), CELL)])
    t = Table(rows, colWidths=[0.52 * inch, 0.75 * inch, 1.0 * inch, 2.53 * inch], repeatRows=1)
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 0.8, INK), ('LINEBELOW', (0, 1), (-1, -1), 0.25, RULE),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 2),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 2), ('LEFTPADDING', (0, 0), (-1, -1), 3)]))
    return t


def render(path, title, facts, plan, logic_note):
    PAGE = landscape(letter)
    M, GAP = 0.5 * inch, 0.35 * inch
    doc = BaseDocTemplate(path, pagesize=PAGE, leftMargin=M, rightMargin=M, topMargin=0.45 * inch,
                          bottomMargin=0.55 * inch, title=f'{title} — lesson plan')
    fw = (PAGE[0] - 2 * M - GAP) / 2
    fh = PAGE[1] - 0.45 * inch - 0.55 * inch
    frames = [Frame(M, 0.55 * inch, fw, fh, id='c1', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
              Frame(M + fw + GAP, 0.55 * inch, fw, fh, id='c2', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)]

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont('Sans', 7.5); canvas.setFillColor(GREY)
        canvas.drawString(M, 0.3 * inch, f'{title} — note-learning plan')
        canvas.drawRightString(PAGE[0] - M, 0.3 * inch, f'page {d.page}')
        canvas.setStrokeColor(RULE); canvas.setLineWidth(0.4)
        canvas.line(M + fw + GAP / 2, 0.55 * inch, M + fw + GAP / 2, PAGE[1] - 0.45 * inch)
        canvas.restoreState()

    fl = [Paragraph(E(title), TITLE), Paragraph(E(facts), SUB)]
    box = Table([[Paragraph(logic_note, SMALL)]], colWidths=[fw])
    box.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), TINT), ('LEFTPADDING', (0, 0), (-1, -1), 7),
                             ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 5),
                             ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    fl += [box, Spacer(1, 8), overview(plan), Spacer(1, 4)]
    for sec in plan:
        for ch in section_flow(sec):
            fl.append(KeepTogether(ch))
    doc.addPageTemplates([PageTemplate(id='two', frames=frames, onPage=footer)])
    doc.build(fl)
