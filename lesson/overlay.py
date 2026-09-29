"""Stamp the lesson plan's steps onto the score PDF: a translucent circled label (A1, A2 ...) on the staff of the
part(s) that step teaches, at the bar where it starts, with the play counts beside it."""
import io, os, re, sys
from fractions import Fraction as F
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
        self.hide = {}       # page -> [(x0, x1, y0, y1)] where badges sit: counts under them are left out

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
            counted = (bar, k) in getattr(self, 'count_y', {}) and lift < 6
            if cap and counted and clear(x - capw - 8, x - 1.5) and x - capw - 8 > self.r.pms[b['page']].systems[b['sys']][k]['x0']:
                side = 'left'          # the count runs along the right: the caption goes back into the bar before
            elif cap and not clear(x + span + 1.5, x + span + capw + 8):
                side = 'left' if clear(x - capw - 8, x - 1.5) else 'above'
            circles = []
            for m, (lab, c, col) in enumerate(bs):
                circles.append((x + r + m * (2 * r + 1.5), lab, col))
            self.marks.setdefault(b['page'], []).append(('group', circles, cy, r, cap, side, bs[0][2], pm.H))
            # a count written over this bar gives way to the badge: the badge says where to start
            x_lo = x - 2 if side != 'left' else x - capw - 10
            x_hi = x + span + (capw + 10 if cap and side == 'right' else 2)
            self.hide.setdefault(b['page'], []).append((x_lo, x_hi, cy - r - 0.5, cy + r + 0.5))
            why = getattr(self, 'whys', {}).get((bar, k))
            if why and lift < 6:
                ww = text_w(why, 'Sans-Oblique', 5.8) + 8
                xa_ = (x + span + capw + 10) if (cap and side == 'right') else x + span + 3
                if xa_ + ww > pw - 8 and x - 4 - ww >= 30:
                    xa_, cyw = x - 4 - ww, cy                  # no room to the right: to the left of the badge
                elif xa_ + ww > pw - 8:
                    xa_, cyw = min(x, pw - 8 - ww), cy - 2 * r - 3          # a row above, kept on the page
                else:
                    cyw = cy
                self.marks[b['page']].append(('why', xa_, cyw, why, pm.H))

    def split_line(self, bar, label, parts=None, pu=None):
        """the dashed line where a letter's second half starts: through all four staves, or, for parts whose
        second half starts elsewhere, through theirs only, just before their pickup note when they have one"""
        if pu is not None:
            bar -= 1
        b = self.r.bars[bar - 1]
        pm = self.r.pms[b['page']]
        sy = pm.systems[b['sys']]
        xa = b['xa']
        if b['first_in_system']:
            # a system's first bar begins with clef and key: the line goes just before the first note or rest
            xs = [it['x'] for sb in b['staves'][:4] for it in sb['items']]
            if xs: xa = min(xs) - 6
        if parts is None:
            self.marks.setdefault(b['page'], []).append(('split', xa, sy[0]['top'] - 14, sy[3]['bot'] + 4, label, pm.H))
            return
        for i, p in enumerate(sorted(parts, key=PART_K.get)):
            k = PART_K[p]
            s = sy[k]
            x = xa
            if pu is not None:
                at = [it['x'] for it in b['staves'][k]['items'] if it.get('on') == pu]
                x = (min(at) if at else b['xa'] + (b['xb'] - b['xa']) * float(pu) / float(self.barlen)) - 4
            self.marks.setdefault(b['page'], []).append(('split', x, s['top'] - 1.6 * s['sp'], s['bot'] + 1.6 * s['sp'], label if i == 0 else '', pm.H))

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
                hide = self.hide.get(i, [])
                for op in sorted(ops, key=lambda op: op[0] != 'rect'):
                    if op[0] == 'count' and any(x0 - 3 <= op[1] <= x1 + 3 and op[2] - 5.6 < y1 - 1.5 and op[2] > y0 + 1.5 for x0, x1, y0, y1 in hide):
                        continue
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

    def beat_lines(self, bar, parts):
        """dashed beat lines through a tricky bar, on the staves of the parts it is tricky for: like bar lines,
        just before the first note on each beat (between notes where no note starts on it)"""
        b = self.r.bars[bar - 1]
        pm = self.r.pms[b['page']]
        sy = pm.systems[b['sys']]
        known = sorted({(it['on'], it['x']) for sb in b['staves'] for it in sb['items'] if 'on' in it})
        if not known: return
        barlen = self.barlen
        pts = [(it_on, x) for it_on, x in known]
        firsts = {}
        for on, x in pts: firsts[on] = min(x, firsts.get(on, x))
        xs = sorted(firsts.items())
        end = (barlen, b['xb'])
        for t in range(1, int(barlen)):
            if t in firsts:
                x = firsts[t] - 2.2
            else:
                before = [q for q in xs if q[0] < t] or [(0, b['xa'])]
                after = [q for q in xs if q[0] > t] or [end]
                (t0, x0), (t1, x1) = before[-1], after[0]
                x = x0 + (x1 - x0) * float((t - t0) / (t1 - t0)) - 1
            for p in parts:
                s = sy[PART_K[p]]
                self.marks.setdefault(b['page'], []).append(('beat', x, s['top'] - 0.4 * s['sp'], s['bot'] + 0.4 * s['sp'], pm.H))

    def counts(self, bar, parts, sub):
        """the count to speak, written over each affected staff: '1 & 2 &' (sub=2) or '1 e & a 2 e & a' (sub=4),
        each syllable over the moment it names"""
        b = self.r.bars[bar - 1]
        pm = self.r.pms[b['page']]
        sy = pm.systems[b['sys']]
        names = {2: ['&'], 4: ['e', '&', 'a']}[sub]
        for i, p in enumerate(sorted(parts, key=PART_K.get)):
            k = PART_K[p]
            s = sy[k]
            own = {}
            for it in b['staves'][k]['items']:
                if 'on' in it: own[it['on']] = min(it['x'], own.get(it['on'], it['x']))
            every = {}
            for sb in b['staves']:
                for it in sb['items']:
                    if 'on' in it: every[it['on']] = min(it['x'], every.get(it['on'], it['x']))
            pts = sorted({**every, **own}.items())
            first_x = min(own.values()) if own else b['xa'] + 4
            if not pts: continue
            def xat(t):
                if t in own: return own[t]
                if t in every: return every[t]
                before = [q for q in pts if q[0] < t] or [(0, first_x)]
                after = [q for q in pts if q[0] > t] or [(self.barlen, b['xb'] - 4)]
                (t0, x0), (t1, x1) = before[-1], after[0]
                return x0 + (x1 - x0) * float((t - t0) / (t1 - t0))
            # 'e' and 'a' only in beats where this part has a note on one: a beat of 8ths reads '2 &'
            starts = {e_on for e_on in own}
            labs = []
            for beat in range(int(self.barlen)):
                labs.append((F(beat), str(beat + 1), True))
                busy = sub == 4 and any(F(beat) + F(m, 4) in starts for m in (1, 3))
                for m, nm in enumerate(names, 1):
                    if sub == 4 and nm != '&' and not busy: continue
                    labs.append((F(beat) + F(m, sub), nm, False))
            # above the staff, and above any note that climbs over it
            heads = [h.y for it in b['staves'][k]['items'] if it['kind'] == 'chord' for h in it['heads']]
            y = min([s['top'] - 1.15 * s['sp']] + [hy - 1.6 * s['sp'] for hy in heads])
            self.count_y = getattr(self, 'count_y', {})
            self.count_y[(bar, k)] = y
            for t, lab, strong in labs:
                self.marks.setdefault(b['page'], []).append(('count', xat(t) + 2.2, y, lab, strong, pm.H))

    def _count(self, c, x, y, lab, strong, H, page=None):
        c.saveState()
        font = 'Sans-Bold' if strong else 'Sans'
        size = 6.4 if strong else 5.6
        w = text_w(lab, font, size)
        c.setFillColor(colors.white); c.setFillAlpha(0.75)
        c.rect(x - w / 2 - 0.6, H - y - 1.6, w + 1.2, size + 0.6, stroke=0, fill=1)
        c.setFillAlpha(1); c.setFillColor(colors.HexColor('#C0392B'))
        c.setFont(font, size)
        c.drawCentredString(x, H - y, lab)
        c.restoreState()

    def _beat(self, c, x, top, bot, H):
        c.saveState()
        c.setStrokeColor(colors.HexColor('#C0392B')); c.setStrokeAlpha(0.85); c.setLineWidth(0.9)
        c.setDash(2.4, 1.8)
        c.line(x, H - top, x, H - bot)
        c.restoreState()

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


def annotate(pdf, pages, plan, steps, dst, mode='drill', score=None, nstaves=6, plan_obj=None):
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
    # beat lines through the bars flagged as rhythmically tricky, whether the plan drills them or slows them down
    st.barlen = 4
    if score is not None:
        from . import analyze as _an
        lens = _an.bar_lengths(score)
    flagged = getattr(plan_obj, 'flagged', {})
    for n, ps in sorted(flagged.items()):
        if score is not None: st.barlen = lens[n]
        st.beat_lines(n, sorted(ps, key=lambda p: PART_K[p]))
    # the count to speak over the same staves: 1 e & a where the passage has 16ths, else 1 &,
    # decided per part over each run of flagged bars so one passage reads one way
    if score is not None:
        for p in PART_K:
            bars = sorted(n for n, ps in flagged.items() if p in ps)
            runs_ = []
            for n in bars:
                if runs_ and runs_[-1][-1] == n - 1: runs_[-1].append(n)
                else: runs_.append([n])
            for run in runs_:
                # 16th-level if any note of this part starts or ends off the 8th grid in the run
                fine = any(e['midi'] is not None and (e['on'].denominator == 4 or (e['on'] + e['dur']).denominator == 4)
                           for n in run for e in score.bars[p].get(n, []))
                for n in run:
                    st.barlen = lens[n]
                    st.counts(n, [p], 4 if fine else 2)
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
        its = [it for it in sec['items'] if it.get('split')]
        if not its: continue
        main = max({it['split'] for it in its if it.get('split_pu') is None} or {its[0]['split']},
                   key=lambda c: sum(len(it['parts']) for it in its if it['split'] == c and it.get('split_pu') is None))
        own = [it for it in its if it['split'] != main or it.get('split_pu') is not None]
        if not own:
            st.split_line(main, f"{sec['letter']} 2nd half")
            continue
        # the parts' second halves start in different places: a line through each part's own staff
        rest = [p for it in its if it not in own for p in it['parts']]
        if rest: st.split_line(main, f"{sec['letter']} 2nd half", parts=rest)
        for it in own:
            st.split_line(it['split'], f"{sec['letter']} 2nd half" if not rest else f"{'+'.join(planmod.ABBR[p] for p in it['parts'])} 2nd half",
                          parts=it['parts'], pu=it.get('split_pu'))
    st.layout()
    st.draw(pdf, dst, 'A1, A2 … = teaching order within each letter.   P = play (listen)   S = play and sing   '
            + ('Rh m24 = slow rhythm work on bar 24' if mode == 'drill' else '↓ = down tempo'))
