"""Stamp the lesson plan's steps onto the score PDF: a translucent circled label (A1, A2 ...) on the staff of the
part(s) that step teaches, at the bar where it starts, with the play counts beside it."""
import io, os, re, sys
from reportlab.pdfgen import canvas as rlcanvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from pypdf import PdfReader, PdfWriter
from . import render      # registers the fonts
from . import plan as planmod
from . import unison

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dorico_reader as dex

PART_K = {'Soprano': 0, 'Alto': 1, 'Tenor': 2, 'Bass': 3}
UNI = '#E0A100'      # unison shading: amber, apart from the part colours
COL = {'Soprano': '#D55E00', 'Alto': '#B8860B', 'Tenor': '#009E73', 'Bass': '#0072B2', 'all': '#7B3FA0'}


def text_w(t, font, size):
    return pdfmetrics.stringWidth(t, font, size)


class Stamper:
    def __init__(self, reader):
        self.r = reader
        self.marks = {}      # page index -> [draw ops]
        self.used = {}       # (page, sys, staff, bar) -> x already taken

    def geom(self, bar, k):
        b = self.r.bars[bar - 1]
        pm = self.r.pms[b['page']]
        s = pm.systems[b['sys']][k]
        items = [it for it in b['staves'][k]['items']]
        x_first = min([it['x'] for it in items], default=b['xa'] + 6)
        # at the start of a system the bar begins with clef and key: start by the first note instead
        x = max(b['xa'] + 3, x_first - 10) if b['first_in_system'] else b['xa'] + 3
        return b, pm, s, x

    def badge(self, bar, k, label, cap, color, lift=4.4, dx=0):
        """queue a badge; badges on the same staff and bar are laid out together"""
        self.queue = getattr(self, 'queue', {})
        self.queue.setdefault((bar, k, lift, dx), []).append((label, cap, color))

    def layout(self):
        for (bar, k, lift, dx), bs in self.queue.items():
            b, pm, s, x = self.geom(bar, k)
            x += dx
            if k == 0 and lift < 6 and bar in self.letter_bars:
                x += 15          # clear the boxed rehearsal letter
            r = 6.3
            sp = s['sp']
            cy = s['top'] - lift * sp
            if lift < 6 and k > 0:
                # stay below the words of the staff above: the middle of the gap between them and this staff
                above = [c['bottom'] for c in pm.text if s['top'] - 14 * sp < c['bottom'] < s['top'] - 2
                         and x - 30 < c['x0'] < x + 90]
                if above:
                    cy = max(cy, (max(above) + s['top']) / 2 - 1)
            pw = float(pm.page.width)
            dyn = [g for g in pm.glyphs if g.staff is s and g.code in dex.DYN and g.y < s['top'] and abs(g.y - 4 - cy) < r + 6]
            n = len(bs)
            span = n * 2 * r + (n - 1) * 1.5
            # the circles stay at the bar; they only step past a dynamic sitting right under them
            for g in dyn:
                if x - 1 <= g.x1 and g.x0 <= x + span + 1:
                    x = g.x1 + 2
            caps = [c for _, c, _ in bs if c]
            if n == 1:
                cap = caps[0] if caps else ''
            else:
                cap = '  ·  '.join(f"{lab}: {c}" for lab, c, _ in bs if c)
            capw = text_w(cap, 'Sans', 5.6) if cap else 0
            def clear(a0, a1):
                return a0 > 8 and a1 < pw - 8 and all(g.x1 < a0 or g.x0 > a1 for g in dyn)
            side = 'right'
            if cap and not clear(x + span + 1.5, x + span + capw + 8):
                side = 'left' if clear(x - capw - 8, x - 1.5) else 'above'
            circles = []
            for m, (lab, c, col) in enumerate(bs):
                circles.append((x + r + m * (2 * r + 1.5), lab, col))
            self.marks.setdefault(b['page'], []).append(('group', circles, cy, r, cap, side, bs[0][2], pm.H))
            why = getattr(self, 'whys', {}).get((bar, k))
            if why and lift < 6:
                ww = text_w(why, 'Sans-Oblique', 5.8) + 8
                xa_ = (x + span + capw + 10) if (cap and side == 'right') else x + span + 3
                if xa_ + ww > pw - 8:
                    xa_, cyw = x, cy - 2 * r - 3          # a row above
                else:
                    cyw = cy
                self.marks[b['page']].append(('why', xa_, cyw, why, pm.H))

    def split_line(self, bar, label):
        b = self.r.bars[bar - 1]
        pm = self.r.pms[b['page']]
        sy = pm.systems[b['sys']]
        self.marks.setdefault(b['page'], []).append(('split', b['xa'], sy[0]['top'] - 14, sy[3]['bot'] + 4, label, pm.H))

    def flag(self, bar, text):
        b = self.r.bars[bar - 1]
        pm = self.r.pms[b['page']]
        s = pm.systems[b['sys']][0]
        self.marks.setdefault(b['page'], []).append(('flag', b['xa'] + 20, s['top'] - 26, text, pm.H))

    def draw(self, src, dst, legend):
        rd = PdfReader(src)
        wr = PdfWriter()
        for i, page in enumerate(rd.pages):
            ops = self.marks.get(i, [])
            if ops or i == 0:
                w, h = float(page.mediabox.width), float(page.mediabox.height)
                buf = io.BytesIO()
                c = rlcanvas.Canvas(buf, pagesize=(w, h))
                if i == 0:
                    c.setFont('Sans-Oblique', 6.5); c.setFillColor(colors.HexColor('#666666'))
                    c.drawRightString(w - 30, h - 16, legend)
                for op in sorted(ops, key=lambda op: op[0] != 'rect'):
                    getattr(self, '_' + op[0])(c, *op[1:])
                c.save()
                buf.seek(0)
                page.merge_page(PdfReader(buf).pages[0])
            wr.add_page(page)
        with open(dst, 'wb') as f:
            wr.write(f)

    def _group(self, c, circles, cy, r, cap, side, capcol, H):
        for m, (cx, lab, col) in enumerate(circles):
            self._badge(c, cx, cy, r, lab, None, col, H)
        if cap:
            x0 = circles[0][0] - r; x1 = circles[-1][0] + r
            self._caption(c, x0, x1, cy, r, cap, side, capcol, H)

    def _caption(self, c, x0, x1, cy, r, cap, side, color, H):
        y = H - cy
        col = colors.HexColor(color)
        tw = text_w(cap, 'Sans', 5.6)
        if side == 'right': bx, by = x1 + 1.5, y - 4
        elif side == 'left': bx, by = x0 - 1.5 - (tw + 5), y - 4
        else: bx, by = (x0 + x1) / 2 - (tw + 5) / 2, y + r + 1
        c.saveState()
        c.setFillColor(colors.white); c.setFillAlpha(0.8)
        c.roundRect(bx, by, tw + 5, 8, 2.5, stroke=0, fill=1)
        c.setFillAlpha(1); c.setFillColor(col)
        c.setFont('Sans', 5.6)
        c.drawString(bx + 2.5, by + 2, cap)
        c.restoreState()

    def _badge(self, c, cx, cy, r, label, cap, color, H, side='right'):
        y = H - cy
        col = colors.HexColor(color)
        c.saveState()
        c.setFillColor(col); c.setFillAlpha(0.22)
        c.setStrokeColor(col); c.setStrokeAlpha(0.85); c.setLineWidth(0.9)
        c.circle(cx, y, r, stroke=1, fill=1)
        c.setFillAlpha(1); c.setFillColor(colors.HexColor('#1a1a1a'))
        fs = 6.6 if len(label) <= 2 else 5.6 if len(label) == 3 else 4.8
        c.setFont('Sans-Bold', fs)
        c.drawCentredString(cx, y - fs * 0.36, label)
        if cap:
            tw = text_w(cap, 'Sans', 5.6)
            if side == 'right': bx, by = cx + r + 1.5, y - 4
            elif side == 'left': bx, by = cx - r - 1.5 - (tw + 5), y - 4
            else: bx, by = cx - (tw + 5) / 2, y + r + 1
            c.setFillColor(colors.white); c.setFillAlpha(0.8)
            c.roundRect(bx, by, tw + 5, 8, 2.5, stroke=0, fill=1)
            c.setFillAlpha(1); c.setFillColor(col)
            c.setFont('Sans', 5.6)
            c.drawString(bx + 2.5, by + 2, cap)
        c.restoreState()

    def _split(self, c, x, top, bot, label, H):
        c.saveState()
        c.setStrokeColor(colors.HexColor(COL['all'])); c.setStrokeAlpha(0.55); c.setLineWidth(1.1)
        c.setDash(3, 2.5)
        c.line(x, H - top, x, H - bot)
        c.setFillColor(colors.HexColor(COL['all'])); c.setFont('Sans-Bold', 6.5)
        c.drawString(x + 2, H - top + 12, label)
        c.restoreState()

    def _why(self, c, x, cy, text, H):
        c.saveState()
        tw = text_w(text, 'Sans-Oblique', 5.8)
        y = H - cy
        c.setFillColor(colors.HexColor('#fff1b8')); c.setFillAlpha(0.9)
        c.roundRect(x, y - 4.2, tw + 7, 8.4, 2.5, stroke=0, fill=1)
        c.setFillAlpha(1); c.setFillColor(colors.HexColor('#5a4500')); c.setFont('Sans-Oblique', 5.8)
        c.drawString(x + 3.5, y - 2, text)
        c.restoreState()

    def shade(self, bars, parts, dashed):
        """a translucent box over these bars on these parts' staves, one box per system and run of adjacent staves"""
        ks = sorted(PART_K[p] for p in parts)
        blocks = []
        for k in ks:
            if blocks and blocks[-1][-1] == k - 1: blocks[-1].append(k)
            else: blocks.append([k])
        bysys = {}
        for n in bars:
            b = self.r.bars[n - 1]
            bysys.setdefault((b['page'], b['sys']), []).append(b)
        for (pi, si), bs in bysys.items():
            pm = self.r.pms[pi]
            sy = pm.systems[si]
            for blk in blocks:
                top, bot = sy[blk[0]], sy[blk[-1]]
                sp = top['sp']
                # from the first sung note to the last, not over rests that lead in or trail off
                first = [it for k in blk for it in bs[0]['staves'][k]['items'] if it['kind'] == 'chord']
                last = [it for k in blk for it in bs[-1]['staves'][k]['items'] if it['kind'] == 'chord']
                x0 = bs[0]['xa'] + 1
                lead = [it for k in blk for it in bs[0]['staves'][k]['items']]
                if first and (bs[0]['first_in_system'] or min(lead, key=lambda it: it['x'])['kind'] == 'rest'):
                    x0 = min(it['x'] for it in first) - 5
                x1 = bs[-1]['xb'] - 1
                tail = [it for k in blk for it in bs[-1]['staves'][k]['items']]
                if last and max(tail, key=lambda it: it['x'])['kind'] == 'rest':
                    x1 = max(it['xr'] for it in last) + 7
                self.marks.setdefault(pi, []).append(('rect', x0, top['top'] - 1.3 * sp, x1, bot['bot'] + 1.3 * sp, dashed, pm.H))

    def _rect(self, c, x0, y0, x1, y1, dashed, H):
        col = colors.HexColor(UNI)
        c.saveState()
        c.setFillColor(col); c.setStrokeColor(col)
        if dashed:
            c.setFillAlpha(0.07); c.setStrokeAlpha(0.9); c.setLineWidth(1.0); c.setDash(4, 2.5)
        else:
            c.setFillAlpha(0.2); c.setStrokeAlpha(0.6); c.setLineWidth(0.6)
        c.roundRect(x0, H - y1, x1 - x0, y1 - y0, 3, stroke=1, fill=1)
        c.restoreState()

    def _flag(self, c, x, y, text, H):
        c.saveState()
        tw = text_w(text, 'Sans-Oblique', 6.5)
        c.setFillColor(colors.HexColor('#fff4c2')); c.setFillAlpha(0.85)
        c.roundRect(x - 2, H - y - 3, tw + 6, 10, 2.5, stroke=0, fill=1)
        c.setFillAlpha(1); c.setFillColor(colors.HexColor('#5a4500')); c.setFont('Sans-Oblique', 6.5)
        c.drawString(x + 1, H - y, text)
        c.restoreState()


def annotate(pdf, pages, plan, steps, dst, mode='drill', score=None, nstaves=6):
    rd = dex.Reader(pdf, pages, nstaves=nstaves).read().voices()
    st = Stamper(rd)
    st.letter_bars = {sec['a'] for sec in plan if sec['letter'] != 'Intro'}
    for sec in plan:
        if sec['kind'] == 'repeat':
            m = re.match(r"Same notes as (\S+) \(m\d+\)(, a (?:half|whole) step (?:higher|lower))?", sec['notes'][0])
            if m:
                sec['items'][-1]['near_cap'] = f"= {m.group(1)}" + (' in a new key' if m.group(2) else '') + ' · all S'
        if sec['kind'] == 'near':
            first = next(it for it in sec['items'] if it['kind'] == 'block')
            last = sec['items'][-1]
            last['near_cap'] = f"after {first['items'][0]['label']}–{first['items'][-1]['label']} (m{first['bar']}): all S from here"
    # unison passages: a solid box over the parts singing the very same notes, dashed over parts doubling at the octave
    for n0, n1, uni, octv in unison.passages(score):
        if len(uni) < 2 and n1 == n0: continue          # a lone bar of octave doubling is not worth a box
        bars = list(range(n0, n1 + 1))
        if len(uni) >= 2:
            st.shade(bars, uni, dashed=False)
            if octv: st.shade(bars, octv, dashed=True)
        else:
            st.shade(bars, uni + octv, dashed=True)
    st.whys = {}
    for sec in plan:
        for blk in sec['items']:
            if blk['kind'] == 'block' and blk.get('why') and blk['items']:
                # on the highest staff the block touches, where there is most room above
                k0 = min(PART_K[p] for jt in blk['items'] for p in jt['parts'])
                st.whys[(blk['items'][0]['bar'], k0)] = 'why: ' + blk['why']
    for it in steps:
        cap = it.get('near_cap') or planmod.caption(it)
        if it['kind'] == 'rhythm' and len(it['parts']) == 4:
            # the whole choir speaks the rhythm: one badge for everyone, first thing in the letter
            st.badge(it['bar'], 0, it['label'], cap, COL['all'], lift=9.6, dx=24)
            continue
        if it['kind'] == 'all':
            st.badge(it['bar'], 0, it['label'], cap, COL['all'], lift=9.6, dx=24)
            continue
        for p in it['parts']:
            st.badge(it['bar'], PART_K[p], it['label'], cap, COL[p] if len(it['parts']) < 4 else COL['all'])
        if it.get('split'):
            pass
        # rhythm spots inside a part's steps: a small marker at that bar
        for t, c in it.get('sub', []):
            if t.startswith('Rhythm') and c:
                for p in it['parts']:
                    st.badge(int(re.search(r'\bm(\d+)', t).group(1)), PART_K[p], 'Rh', '', COL[p])
    for sec in plan:
        for it in sec['items']:
            if it.get('split'):
                st.split_line(it['split'], f"{sec['letter']} 2nd half")
                break
    st.layout()
    st.draw(pdf, dst, 'A1, A2 … = teaching order within each letter.   P = play (listen)   S = play and sing   '
            + ('Rh m24 = slow rhythm work on bar 24' if mode == 'drill' else '↓ = down tempo'))
