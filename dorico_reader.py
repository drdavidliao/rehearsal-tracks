#!/usr/bin/env python3
"""Dorico (Bravura / Academico) vector-PDF reader for an open SATB + piano score.

Reads the glyph stream (SKILL.md Step 2) into a per-staff, per-bar event model:
   bars[b]['staves'][k] = {'voices': {v: [event,...]}, ...}
Everything is measured from the page: staff lines, SP per staff, barlines, stems,
beams (rects + filled 4-point polygons), flags, dots, accidentals, ties/slurs
(filled crescents), lyrics (text layer), extension lines, dynamics, hairpins,
chord symbols, rehearsal marks, tempo.
"""
import sys, re, math, statistics, collections
from fractions import Fraction as F
import pdfplumber

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify      # staves_of() only

BLACK, HALF, WHOLE, XHEAD = 0xF4BE, 0xF4BD, 0xF4BC, 0xE0A9
HEADS = {BLACK: 'black', HALF: 'half', WHOLE: 'whole', XHEAD: 'x',
         0xE0A4: 'black', 0xE0A3: 'half', 0xE0A2: 'whole'}
RESTS = {0xE4E3: F(4), 0xE4E4: F(2), 0xE4E5: F(1), 0xE4E6: F(1, 2), 0xE4E7: F(1, 4)}
ACC = {0xE260: -1, 0xE261: 0, 0xE262: 1}
FLAGS = {0xE240: (1, 'up'), 0xE241: (1, 'down'), 0xE242: (2, 'up'), 0xE243: (2, 'down')}
DOT = 0xE1E7
CLEF = {0xE050: 'G', 0xE052: 'G8', 0xE062: 'F'}
TOPLINE = {'G': 5 * 7 + 3, 'G8': 4 * 7 + 3, 'F': 3 * 7 + 5}   # diatonic index of the top line, sounding
DYN = {0xE520: 'p', 0xE522: 'f', 0xE52B: 'pp', 0xE52C: 'mp', 0xE52D: 'mf', 0xE52F: 'ff', 0xE530: 'fff', 0xE52A: 'ppp'}
STACC = {0xE4A2, 0xE4A3}
ACCENT = {0xE4A0, 0xE4A1}
STEPS = 'CDEFGAB'
KEY_SHARPS = 'FCGDAEB'


class Glyph:
    __slots__ = ('code', 'x0', 'x1', 'y', 'size', 'font', 'staff', 'pos')

    def __init__(self, c, H):
        self.code = ord(c['text'][0]); self.x0 = c['x0']; self.x1 = c['x1']
        self.y = H - c['matrix'][5]; self.size = round(c['size'], 1); self.font = c['fontname']
        self.staff = None; self.pos = None

    @property
    def cx(self): return (self.x0 + self.x1) / 2


def cluster(xs, tol):
    out = []
    for x in sorted(xs):
        if out and x - out[-1][-1] <= tol: out[-1].append(x)
        else: out.append([x])
    return out


class PageModel:
    def __init__(self, page, nstaves):
        self.page = page
        H = self.H = page.height
        st = verify.staves_of(page)
        for s in st:
            s['sp'] = (s['lines'][4] - s['lines'][0]) / 4
            s['top'], s['bot'] = s['lines'][0], s['lines'][4]
        assert len(st) % nstaves == 0, (page.page_number, len(st))
        self.staves = st
        self.systems = [st[i:i + nstaves] for i in range(0, len(st), nstaves)]
        for si, sy in enumerate(self.systems):
            for k, s in enumerate(sy): s['sys'] = si; s['k'] = k
        self.glyphs = [Glyph(c, H) for c in page.chars if 'Bravura' in c['fontname']]
        self.text = [c for c in page.chars if 'Bravura' not in c['fontname']]
        for g in self.glyphs:
            s = self.nearest_staff(g.y)
            g.staff = s
            g.pos = round((g.y - s['top']) / (s['sp'] / 2))
        vl = [l for l in page.lines if abs(l['x0'] - l['x1']) < 0.3]
        self.stems = [dict(x=l['x0'], top=l['top'], bot=l['bottom']) for l in vl if l['linewidth'] < 0.55]
        self.bars_v = [l for l in vl if l['linewidth'] >= 0.55]
        stafflines = {round(y, 1) for s_ in st for y in s_['lines']}
        self.hlines = [l for l in page.lines if abs(l['y0'] - l['y1']) < 0.3 and not (round(l['top'], 1) in stafflines and l['x1'] - l['x0'] > 150)]
        # beams: filled rects of beam thickness and filled 4-point polygons
        self.beams = []
        for r in page.rects:
            if r['fill'] and 1.0 < r['height'] < 2.6 and r['width'] > 2:
                self.beams.append(dict(x0=r['x0'], x1=r['x1'], yl0=r['top'], yl1=r['bottom'], yr0=r['top'], yr1=r['bottom']))
        self.arcs, self.wedges = [], []
        for cv in page.curves:
            sig = ''.join(o[0] for o in cv['path'])
            if sig == 'mllllh' and cv['fill']:
                pts = [o[1] for o in cv['path'][:5]]
                xs = sorted({round(p[0], 2) for p in pts})
                xl, xr = min(p[0] for p in pts), max(p[0] for p in pts)
                L = sorted(p[1] for p in pts if abs(p[0] - xl) < 0.3)
                R = sorted(p[1] for p in pts if abs(p[0] - xr) < 0.3)
                if len(L) >= 2 and len(R) >= 2:
                    self.beams.append(dict(x0=xl, x1=xr, yl0=L[0], yl1=L[-1], yr0=R[0], yr1=R[-1]))
            elif sig == 'mclclh' and cv['fill']:
                p = cv['path']
                a, c1, c2, b = p[0][1], p[1][1], p[1][2], p[1][3]
                a2, b2 = p[2][1], p[0][1]
                (xl, yl), (xr, yr) = sorted([a, b])
                cy = (c1[1] + c2[1]) / 2
                over = cy < (yl + yr) / 2
                self.arcs.append(dict(xl=xl, yl=yl, xr=xr, yr=yr, over=over, top=cv['top'], bot=cv['bottom']))
            elif sig == 'mllllll':
                pts = [o[1] for o in cv['path']]
                tip = pts[0]
                other = [p for p in pts if abs(p[0] - tip[0]) > 1]
                kind = 'crescendo' if tip[0] < min(p[0] for p in other) else 'diminuendo'
                self.wedges.append(dict(x0=cv['x0'], x1=cv['x1'], y=(cv['top'] + cv['bottom']) / 2, kind=kind))
        self.barlines = [self.find_barlines(sy) for sy in self.systems]

    def nearest_staff(self, y):
        best = None
        for s in self.staves:
            d = 0 if s['top'] <= y <= s['bot'] else min(abs(y - s['top']), abs(y - s['bot']))
            if best is None or d < best[0]: best = (d, s)
        return best[1]

    def find_barlines(self, sy):
        cover = collections.defaultdict(set)
        for l in self.bars_v:
            for k, s in enumerate(sy):
                if l['top'] <= s['top'] + 0.6 and l['bottom'] >= s['bot'] - 0.6:
                    cover[round(l['x0'], 1)].add(k)
        xs = [x for x, ks in cover.items() if len(ks) >= min(3, len(sy))]
        groups = cluster(xs, 4.5)
        x_start = sy[0]['x0']
        out = []
        for g in groups:
            if g[0] < x_start + 2: continue      # the system's opening line
            out.append((g[0], g[-1], len(g)))
        return out   # [(left x, right x, n lines)]


# ------------------------------------------------------------------ chords and rests on a staff
def stem_claims(pm, heads, s):
    """group noteheads into chords by the stem that claims them"""
    sp = s['sp']
    stems = [t for t in pm.stems if t['bot'] > s['top'] - 12 * sp and t['top'] < s['bot'] + 12 * sp
             and t['bot'] - t['top'] > 1.5 * sp]
    chords = []
    used = set()
    for t in stems:
        members = []
        for i, h in enumerate(heads):
            if h.code == WHOLE: continue
            if not (abs(h.x1 - t['x']) < 0.9 or abs(h.x0 - t['x']) < 0.9): continue
            if not (t['top'] - 0.7 * sp <= h.y <= t['bot'] + 0.7 * sp): continue
            members.append(i)
        if not members: continue
        ys = [heads[i].y for i in members]
        # up stem: heads at the stem's bottom end
        direction = 'up' if abs(max(ys) - t['bot']) < abs(min(ys) - t['top']) else 'down'
        chords.append(dict(stem=t, dir=direction, idx=members))
    # a head claimed by two stems (unison of two voices): keep in both
    for c in chords: used |= set(c['idx'])
    loose = [i for i in range(len(heads)) if i not in used]
    return chords, loose


def beam_count(pm, t, direction, sp):
    n = 0
    ys = []
    for b in pm.beams:
        if not (b['x0'] - 0.6 <= t['x'] <= b['x1'] + 0.6): continue
        w = b['x1'] - b['x0']
        f = 0 if w < 1e-6 else min(max((t['x'] - b['x0']) / w, 0), 1)
        y0 = b['yl0'] + f * (b['yr0'] - b['yl0']); y1 = b['yl1'] + f * (b['yr1'] - b['yl1'])
        if y1 < t['top'] - 0.4 or y0 > t['bot'] + 0.4: continue
        ym = (y0 + y1) / 2
        if all(abs(ym - y) > 0.3 * sp for y in ys):
            ys.append(ym)
    return len(ys)


def dot_count(pm, heads, x_right, s, dots_all, taken):
    sp = s['sp']
    mine = []
    for j, d in enumerate(dots_all):
        if j in taken: continue
        if not (x_right + 0.1 * sp <= d.x0 <= x_right + 2.6 * sp): continue
        if any(abs(d.y - h.y) <= 0.75 * sp for h in heads):
            mine.append(j)
    if not mine: return 0, []
    cols = cluster([dots_all[j].x0 for j in mine], 0.5 * sp)
    # a second dot column must be close to the first (double dot): 0.5-1.2 SP
    n = 1
    if len(cols) > 1 and cols[1][0] - cols[0][-1] < 1.3 * sp: n = 2
    keep = [j for j in mine if dots_all[j].x0 <= cols[n - 1][-1] + 0.01]
    return n, keep


class Reader:
    def __init__(self, path, pages, nstaves=6, staff_names=None, lyric_font=None, lyric_size=None):
        self.pdf = pdfplumber.open(path)
        self.pms = [PageModel(self.pdf.pages[i], nstaves) for i in pages]
        self.nstaves = nstaves
        self.bars = []           # one dict per bar
        self.problems = []
        self.lyric_font, self.lyric_size = lyric_font, lyric_size

    # -------------------------------------------------------------- pass 1: bars and items
    def read(self):
        clef = {}
        key = None
        for pi, pm in enumerate(self.pms):
            for si, sy in enumerate(pm.systems):
                bls = pm.barlines[si]
                x0 = sy[0]['x0']
                edges = [(x0, None)] + [(b[1], b) for b in bls]
                for bi in range(len(bls)):
                    xa = edges[bi][0]; xb = bls[bi][0]
                    bar = dict(num=len(self.bars) + 1, page=pi, sys=si, xa=xa, xb=xb,
                               first_in_system=(bi == 0), barline=bls[bi], staves=[])
                    self.bars.append(bar)
                    for k, s in enumerate(sy):
                        gl = [g for g in pm.glyphs if g.staff is s and xa < g.cx < xb]
                        bar['staves'].append(self.read_staff_bar(pm, s, gl, bar, k))
                # the region after the last barline (courtesy key/clef) is ignored
        return self

    def read_staff_bar(self, pm, s, gl, bar, k):
        sp = s['sp']
        heads = [g for g in gl if g.code in HEADS]
        rests = [g for g in gl if g.code in RESTS]
        dots = [g for g in gl if g.code == DOT]
        flags = [g for g in gl if g.code in FLAGS]
        accs = [g for g in gl if g.code in ACC]
        clefs = [g for g in gl if g.code in CLEF]
        # dedupe identical glyphs
        def dd(lst):
            seen, out = set(), []
            for g in lst:
                key_ = (g.code, round(g.x0, 1), round(g.y, 1))
                if key_ in seen: continue
                seen.add(key_); out.append(g)
            return out
        heads, rests, dots, flags, accs = dd(heads), dd(rests), dd(dots), dd(flags), dd(accs)
        chords, loose = stem_claims(pm, heads, s)
        items = []
        taken = set()
        for c in chords:
            hs = [heads[i] for i in c['idx']]
            t = c['stem']
            types = {HEADS[h.code] for h in hs}
            if 'whole' in types: self.problems.append(f"bar {bar['num']} staff {k}: whole head on a stem")
            if types <= {'black', 'x'}:
                n = beam_count(pm, t, c['dir'], sp)
                fl = [f for f in flags if abs(f.x0 - t['x']) < 1.2 and (t['top'] - sp <= f.y <= t['bot'] + sp)]
                nf = max([FLAGS[f.code][0] for f in fl], default=0)
                if n and nf: self.problems.append(f"bar {bar['num']} staff {k}: beam and flag on one stem")
                base = F(1, 2 ** max(n, nf))
            elif types == {'half'}:
                base = F(2)
            else:
                self.problems.append(f"bar {bar['num']} staff {k}: mixed heads {types}"); base = F(1)
            xr = max(h.x1 for h in hs)
            nd, keep = dot_count(pm, hs, xr, s, dots, taken)
            taken |= set(keep)
            dur = base * (2 - F(1, 2 ** nd))
            items.append(dict(kind='chord', x=min(h.x0 for h in hs), xr=xr, heads=sorted(hs, key=lambda h: -h.y),
                              dir=c['dir'], stem=t, base=base, dots=nd, dur=dur,
                              xhead=any(h.code == XHEAD for h in hs)))
        # stemless heads (whole notes): group by x
        wl = sorted((heads[i] for i in loose), key=lambda h: h.x0)
        groups = []
        for h in wl:
            if h.code != WHOLE:
                self.problems.append(f"bar {bar['num']} staff {k}: {HEADS[h.code]} head at x{h.x0:.0f} has no stem")
            if groups and abs(h.x0 - groups[-1][0].x0) < 1.5 * sp: groups[-1].append(h)
            else: groups.append([h])
        for g in groups:
            xr = max(h.x1 for h in g)
            nd, keep = dot_count(pm, g, xr, s, dots, taken)
            taken |= set(keep)
            items.append(dict(kind='chord', x=min(h.x0 for h in g), xr=xr, heads=sorted(g, key=lambda h: -h.y),
                              dir=None, stem=None, base=F(4), dots=nd, dur=F(4) * (2 - F(1, 2 ** nd)), xhead=False))
        for r in rests:
            nd, keep = dot_count(pm, [r], r.x1, s, dots, taken)
            taken |= set(keep)
            base = RESTS[r.code]
            items.append(dict(kind='rest', x=r.x0, xr=r.x1, y=r.y, base=base, dots=nd,
                              dur=base * (2 - F(1, 2 ** nd)), glyph=r, whole=(r.code == 0xE4E3)))
        left = [d for j, d in enumerate(dots) if j not in taken]
        for d in left:
            self.problems.append(f"bar {bar['num']} staff {k}: unclaimed dot at x{d.x0:.0f}")
        items.sort(key=lambda it: it['x'])
        return dict(items=items, accs=accs, clefs=clefs, s=s, glyphs=gl)

    # -------------------------------------------------------------- pass 2: voices and onsets
    BAR = F(4)

    def voices(self):
        for bar in self.bars:
            barlen = self.BAR
            for k, sb in enumerate(bar['staves']):
                items = sb['items']
                sb['voices'] = self.split(items, sb['s'], barlen, bar, k)
            self.onsets(bar, barlen)
        return self

    def split(self, items, s, barlen, bar, k):
        if not items:
            return {}
        sp = s['sp']
        xs = cluster([it['x'] for it in items], 0.8)
        shared = any(len(c) > 1 for c in xs)
        total = sum(it['dur'] for it in items if not (it['kind'] == 'rest' and it['whole']))
        wholes = [it for it in items if it['kind'] == 'rest' and it['whole']]
        if len(items) == 1 and wholes:
            items[0]['dur'] = barlen
            return {1: items}
        if not shared and total == barlen and not wholes:
            return {1: items}
        # two voices: stems up -> 1, down -> 2; rests and stemless by height and company
        mid = s['top'] + 2 * sp
        v = {1: [], 2: []}
        for it in items:
            if it['kind'] == 'chord' and it['dir'] == 'up': v[1].append(it)
            elif it['kind'] == 'chord' and it['dir'] == 'down': v[2].append(it)
        for it in items:
            if it['kind'] == 'chord' and it['dir'] is None:
                col = [o for o in items if o is not it and abs(o['x'] - it['x']) < 1.5 * sp and o['kind'] == 'chord']
                if any(o['dir'] == 'up' for o in col): v[2].append(it)
                elif any(o['dir'] == 'down' for o in col): v[1].append(it)
                else:
                    # a stemless head alone: the voice with less in it
                    (v[1] if sum(o['dur'] for o in v[1]) <= sum(o['dur'] for o in v[2]) else v[2]).append(it)
            elif it['kind'] == 'rest':
                if it['whole'] and len(items) > 1:
                    # whole rest beside other material: the empty voice's bar rest
                    (v[2] if not v[2] else v[1]).append(it); it['dur'] = barlen
                else:
                    (v[1] if it['y'] < mid - 0.1 else v[2]).append(it)
        for n in v: v[n].sort(key=lambda it: it['x'])
        if not v[2]: return {1: v[1]}
        if not v[1]: return {1: v[2]}
        return v

    def onsets(self, bar, barlen):
        # columns: x -> onset, learned from complete voices
        known = []
        for sb in bar['staves']:
            for n, seq in sb['voices'].items():
                if sum(it['dur'] for it in seq) == barlen:
                    t = F(0)
                    for it in seq:
                        it['on'] = t; known.append((it['x'], t)); t += it['dur']
        known.sort()
        def lookup(x):
            best = None
            for kx, t in known:
                if abs(kx - x) < 1.2 and (best is None or abs(kx - x) < best[0]): best = (abs(kx - x), t)
            return None if best is None else best[1]
        for k, sb in enumerate(bar['staves']):
            for n, seq in sb['voices'].items():
                if sum(it['dur'] for it in seq) == barlen: continue
                t = F(0)
                for it in seq:
                    col = lookup(it['x'])
                    if col is not None and col > t: t = col
                    elif col is not None and col < t:
                        self.problems.append(f"bar {bar['num']} staff {k} voice {n}: item at x{it['x']:.0f} column onset {col} < running {t}")
                    it['on'] = t; t += it['dur']
                if t > barlen:
                    self.problems.append(f"bar {bar['num']} staff {k} voice {n}: {t} quarters > {barlen} " +
                                         ' '.join(f"{it['kind'][0]}{it['dur']}" for it in seq))

    # -------------------------------------------------------------- pass 3: clefs, keys, pitches
    def pitches(self):
        clef = {}
        key = 0
        self.keys = {}
        for bar in self.bars:
            # key signature: accidentals left of every rhythmic item by > 1 SP, on every staff
            ks = []
            for k, sb in enumerate(bar['staves']):
                sp = sb['s']['sp']
                first = min([it['x'] for it in sb['items']], default=bar['xb'])
                cl = [g for g in sb['clefs']]
                for g in cl:
                    pass
                kacc = [a for a in sb['accs'] if a.x1 < first - 0.9 * sp]
                sb['keyaccs'] = kacc
                ks.append(kacc)
            newkey = None
            if any(ks):
                sharps = sum(1 for a in ks[0] if ACC[a.code] == 1)
                flats = sum(1 for a in ks[0] if ACC[a.code] == -1)
                newkey = sharps - flats
                for k, kacc in enumerate(ks[1:], 1):
                    s2 = sum(1 for a in kacc if ACC[a.code] == 1) - sum(1 for a in kacc if ACC[a.code] == -1)
                    if s2 != newkey:
                        self.problems.append(f"bar {bar['num']}: key signature disagrees across staves ({newkey} vs {s2} on staff {k})")
            elif bar['num'] == 1:
                newkey = 0
            if newkey is not None and newkey != key or bar['num'] == 1:
                key = newkey if newkey is not None else key
                self.keys[bar['num']] = key
            bar['key'] = key
            kalter = {}
            for i in range(abs(key)):
                kalter[(KEY_SHARPS if key > 0 else KEY_SHARPS[::-1])[i]] = 1 if key > 0 else -1
            for k, sb in enumerate(bar['staves']):
                s = sb['s']; sp = s['sp']
                for g in sorted(sb['clefs'], key=lambda g: g.x0):
                    clef.setdefault(k, [])
                cl_here = sorted(sb['clefs'], key=lambda g: g.x0)
                if bar['num'] == 1 and not cl_here:
                    self.problems.append(f"bar 1 staff {k}: no clef")
                note_accs = [a for a in sb['accs'] if a not in sb['keyaccs']]
                heads = [(h, it) for it in sb['items'] if it['kind'] == 'chord' for h in it['heads']]
                # attach each accidental to the nearest head at its staff position to its right
                expl = {}
                for a in note_accs:
                    cand = [(h.x0 - a.x1, h) for h, it in heads if h.pos == a.pos and -0.3 * sp <= h.x0 - a.x1 <= 5 * sp]
                    if not cand:
                        self.problems.append(f"bar {bar['num']} staff {k}: accidental at x{a.x0:.0f} pos {a.pos} has no note")
                        continue
                    h = min(cand, key=lambda c: c[0])[1]
                    expl[id(h)] = ACC[a.code]
                memory = {}
                cur_clef = clef.get(k)
                seq = sorted(heads, key=lambda p: p[0].x0)
                clefs_x = cl_here
                for h, it in seq:
                    c = cur_clef
                    for g in clefs_x:
                        if g.x0 < h.x0: c = CLEF[g.code]
                    if c is None:
                        self.problems.append(f"bar {bar['num']} staff {k}: no clef in force"); c = 'G'
                    dia = TOPLINE[c] - h.pos
                    step = STEPS[dia % 7]; octv = dia // 7
                    if id(h) in expl:
                        alt = expl[id(h)]; memory[h.pos] = alt; h_acc = True
                    elif h.pos in memory:
                        alt = memory[h.pos]; h_acc = False
                    else:
                        alt = kalter.get(step, 0); h_acc = False
                    h.__class__  # noqa
                    it.setdefault('pitch', {})[id(h)] = dict(step=step, alter=alt, oct=octv, acc=id(h) in expl,
                                                              acc_val=expl.get(id(h)), pos=h.pos)
                for g in clefs_x:
                    cur_clef = CLEF[g.code]
                if cur_clef: clef[k] = cur_clef
                sb['clef_start'] = CLEF[clefs_x[0].code] if clefs_x and clefs_x[0].x0 < min([it['x'] for it in sb['items']], default=1e9) else None
        return self

    # -------------------------------------------------------------- pass 4: ties and slurs
    def system_heads(self):
        """{(page, sys, k): [(head, item, bar)]} sorted by x"""
        out = collections.defaultdict(list)
        for bar in self.bars:
            for k, sb in enumerate(bar['staves']):
                for it in sb['items']:
                    it['bar'] = bar['num']; it['k'] = k
                    if it['kind'] == 'chord':
                        for h in it['heads']:
                            out[(bar['page'], bar['sys'], k)].append((h, it, bar))
        for v in out.values(): v.sort(key=lambda p: p[0].x0)
        return out

    def ties_slurs(self):
        SH = self.system_heads()
        self.sh = SH
        pending = []     # arcs running off a system: (page, sys, k, arc, start head/item)
        for pi, pm in enumerate(self.pms):
            for arc in pm.arcs:
                s = pm.nearest_staff((arc['yl'] + arc['yr']) / 2)
                si, k = s['sys'], s['k']
                sp = s['sp']
                hs = SH.get((pi, si, k), [])
                sysr = s['x1']; sysl = pm.systems[si][0]['x0']
                firstx = hs[0][0].x0 if hs else 1e9
                A = [(h, it) for h, it, b in hs if h.x0 - 0.3 * sp <= arc['xl'] <= h.x1 + 3.2 * sp and abs(h.y - arc['yl']) < 2.2 * sp]
                B = [(h, it) for h, it, b in hs if h.x0 - 3.2 * sp <= arc['xr'] <= h.x1 + 0.3 * sp and abs(h.y - arc['yr']) < 2.2 * sp]
                incoming = arc['xl'] < firstx - 0.2 * sp
                outgoing = arc['xr'] > sysr - 1.5 * sp and not B
                # a tie: same staff position, nothing at that position between
                best = None
                if not incoming and not outgoing:
                    for ha, ia in A:
                        for hb, ib in B:
                            if hb.pos != ha.pos or hb.x0 <= ha.x1 or ia is ib: continue
                            between = [h for h, it, b in hs if h.pos == ha.pos and ha.x0 < h.x0 < hb.x0 and it is not ia and it is not ib]
                            if between: continue
                            # a tie joins a note to the next one in its voice: no chord of that voice in between
                            mid = [it for h, it, b in hs if ia['xr'] < it['x'] < ib['x'] - 0.5 and it is not ia and it is not ib
                                   and (ia['dir'] is None or it['dir'] is None or it['dir'] == ia['dir'] or ib['dir'] == it['dir'])]
                            if mid: continue
                            cost = abs(ha.y - arc['yl']) + abs(hb.y - arc['yr']) + 0.2 * (arc['xl'] - ha.x1) + 0.2 * (hb.x0 - arc['xr'])
                            if best is None or cost < best[0]: best = (cost, ha, ia, hb, ib)
                if best:
                    _, ha, ia, hb, ib = best
                    ia.setdefault('tie_start', set()).add(id(ha)); ib.setdefault('tie_stop', set()).add(id(hb))
                    ia.setdefault('tie_obj', {})[id(ha)] = arc['over']
                    continue
                if outgoing and A:
                    ha, ia = min(A, key=lambda p: abs(arc['xl'] - p[0].x1) + 0.3 * abs(p[0].y - arc['yl']))
                    pending.append(dict(pi=pi, si=si, k=k, arc=arc, h=ha, it=ia))
                    continue
                if incoming:
                    # matched later against the pending list
                    pending.append(dict(pi=pi, si=si, k=k, arc=arc, incoming=True, B=B))
                    continue
                # a slur
                ca = self.chord_near(hs, arc['xl'], arc['yl'], sp, left=True, over=arc['over'])
                cb = self.chord_near(hs, arc['xr'], arc['yr'], sp, left=False, over=arc['over'])
                if ca is None or cb is None or ca is cb:
                    self.problems.append(f"p{pm.page.page_number}: arc x{arc['xl']:.0f}-{arc['xr']:.0f} y{arc['yl']:.0f} matched no notes")
                    continue
                ca['slur_start'] = ca.get('slur_start', 0) + 1
                cb['slur_stop'] = cb.get('slur_stop', 0) + 1
        # pair arcs across system breaks
        outs = [p for p in pending if not p.get('incoming')]
        ins = [p for p in pending if p.get('incoming')]
        for o in outs:
            nxt = self.next_sys(o['pi'], o['si'])
            cand = [p for p in ins if (p['pi'], p['si']) == nxt and p['k'] == o['k'] and not p.get('used')]
            if not cand:
                self.problems.append(f"bar {o['it']['bar']} staff {o['k']}: arc runs off the system with no continuation")
                continue
            # the continuation at the same height order
            p = min(cand, key=lambda p: abs((p['arc']['yl'] - self.pms[p['pi']].systems[p['si']][p['k']]['top'])
                                            - (o['arc']['yr'] - self.pms[o['pi']].systems[o['si']][o['k']]['top'])))
            p['used'] = True
            hsn = self.sh.get((p['pi'], p['si'], p['k']), [])
            sp = self.pms[p['pi']].systems[p['si']][p['k']]['sp']
            ha, ia = o['h'], o['it']
            first_same = [(h, it) for h, it, b in hsn if h.pos == ha.pos]
            tie = None
            if first_same:
                hb, ib = first_same[0]
                if hb.x0 - 3.2 * sp <= p['arc']['xr'] <= hb.x1 + 0.3 * sp and abs(hb.y - p['arc']['yr']) < 2.2 * sp:
                    # and it is the first chord of that staff on the system
                    firstchord = min((it for h, it, b in hsn), key=lambda it: it['x'])
                    hso = self.sh.get((o['pi'], o['si'], o['k']), [])
                    lastchord = max((it for h, it, b in hso), key=lambda it: it['x'])
                    if ib is firstchord and ia is lastchord: tie = (hb, ib)
            if tie:
                hb, ib = tie
                ia.setdefault('tie_start', set()).add(id(ha)); ib.setdefault('tie_stop', set()).add(id(hb))
                ia.setdefault('tie_obj', {})[id(ha)] = o['arc']['over']
            else:
                ia['slur_start'] = ia.get('slur_start', 0) + 1
                cb = self.chord_near(hsn, p['arc']['xr'], p['arc']['yr'], sp, left=False, over=p['arc']['over'])
                if cb is None:
                    self.problems.append(f"bar {ia['bar']}: slur continuation matched no note")
                else:
                    cb['slur_stop'] = cb.get('slur_stop', 0) + 1
        for p in ins:
            if not p.get('used'):
                self.problems.append(f"page {p['pi']+1} system {p['si']+1} staff {p['k']}: incoming arc with no start")
        return self

    def next_sys(self, pi, si):
        if si + 1 < len(self.pms[pi].systems): return (pi, si + 1)
        return (pi + 1, 0)

    def chord_near(self, hs, x, y, sp, left, over):
        items = {id(it): it for h, it, b in hs}.values()
        best = None
        for it in items:
            if left:
                d = abs(x - (it['x'] + it['xr']) / 2)
            else:
                d = abs(x - (it['x'] + it['xr']) / 2)
            if d > 3.5 * sp: continue
            # the voice on the arc's side
            pen = 0
            if it['dir'] == 'down' and over: pen = 0.5 * sp
            if it['dir'] == 'up' and not over: pen = 0.5 * sp
            if best is None or d + pen < best[0]: best = (d + pen, it)
        return best[1] if best else None

    # -------------------------------------------------------------- pass 5: lyrics
    def lyrics(self, vocal_staves, font_re, size):
        self.lyric_size = size
        self.notes = getattr(self, 'notes', [])
        rows_by_staff = collections.defaultdict(list)    # k -> [(pi, si, row tokens)]
        for pi, pm in enumerate(self.pms):
            H = pm.H
            cs = [c for c in pm.text if re.search(font_re, c['fontname']) and abs(c['size'] - size) < 0.15]
            for si, sy in enumerate(pm.systems):
                for k in vocal_staves:
                    s = sy[k]; sp = s['sp']
                    lim = sy[k + 1]['top'] if k + 1 < len(sy) else s['bot'] + 14 * sp
                    band = [c for c in cs if s['bot'] < c['top'] < (s['bot'] + lim) / 2 and s['x0'] - 5 < c['x0'] < s['x1'] + 5]
                    rows = []
                    for c in sorted(band, key=lambda c: c['top']):
                        for r in rows:
                            if abs(r[0] - c['top']) < 1.0: r[1].append(c); break
                        else: rows.append([c['top'], [c]])
                    if len(rows) > 1:
                        self.problems.append(f"p{pi+1} sys {si+1} staff {k}: {len(rows)} lyric rows {[round(r[0]) for r in rows]}")
                    for top, chars in rows:
                        rows_by_staff[k].append((pi, si, top, self.tokens(chars)))
        self.lyric_rows = rows_by_staff
        for k in vocal_staves:
            depth = 0
            for bar in self.bars:
                for it in sorted((it for v in bar['staves'][k]['voices'].values() for it in v), key=lambda it: it['on']):
                    if it['kind'] != 'chord': continue
                    it['slurcont'] = depth > 0
                    depth += it.get('slur_start', 0) - it.get('slur_stop', 0)
                    depth = max(depth, 0)
        for k, rows in rows_by_staff.items():
            carry = None      # previous syllable waiting for a hyphen decision across a system break
            for pi, si, top, toks in rows:
                pm = self.pms[pi]; s = pm.systems[si][k]; sp = s['sp']
                syls = [t for t in toks if t['t'] != '-']
                # syllabic joins
                for i, t in enumerate(toks):
                    if t['t'] == '-':
                        prv = next((x for x in reversed(toks[:i]) if x['t'] != '-'), None)
                        nxt = next((x for x in toks[i + 1:] if x['t'] != '-'), None)
                        if prv is not None: prv['join_next'] = True
                        elif carry is not None: carry['join_next'] = True
                        if nxt is not None: nxt['join_prev'] = True
                        elif prv is not None: prv['join_next'] = True
                if carry is not None and carry.get('join_next') and syls:
                    syls[0]['join_prev'] = True
                # extension lines
                for t in syls:
                    hit = [l for l in pm.hlines if top + 0.35 * size <= l['top'] <= top + 1.5 * size
                           and l['x1'] - l['x0'] > 1.0 * sp and t['x1'] - 1 <= l['x0'] <= t['x1'] + 2.5 * sp]
                    t['extend'] = bool(hit)
                    t['runs_off'] = any(l['x1'] > s['x1'] - 3 for l in hit)
                # a leading segment at the start of this system continues the previous syllable
                lead = [l for l in pm.hlines if top + 0.35 * size <= l['top'] <= top + 1.5 * size
                        and l['x1'] - l['x0'] > 1.0 * sp and l['x0'] < s['x0'] + 15 * sp
                        and (not syls or l['x1'] < syls[0]['x0'])]
                if lead and carry is not None and not carry.get('extend'):
                    carry['extend'] = True
                # assign to notes
                hs = self.sh.get((pi, si, k), [])
                chords = []
                for h, it, b in hs:
                    if it not in chords: chords.append(it)
                chords.sort(key=lambda it: it['x'])
                cand = [it for it in chords if not (it.get('tie_stop') and len(it['tie_stop']) == len(it['heads']))]
                j = 0
                for t in syls:
                    pick = None
                    inspan = []
                    for q in range(j, len(cand)):
                        it = cand[q]
                        c = (it['x'] + it['xr']) / 2
                        if t['x0'] - 0.3 * sp <= c <= t['x1'] + 0.3 * sp: inspan.append(q)
                        if c > t['x1'] + 0.3 * sp: break
                    if inspan:
                        # a syllable begins at the start of the slur it is sung over, not inside it
                        free = [q for q in inspan if not cand[q].get('slurcont')]
                        pick = free[0] if free else inspan[0]
                        if free and free[0] != inspan[0]:
                            self.notes.append(f"bar {cand[pick]['bar']} staff {k}: {t['t']!r} spans a slurred note; put on the note after the slur")
                    if pick is None:
                        rest = [(abs((cand[q]['x'] + cand[q]['xr']) / 2 - (t['x0'] + t['x1']) / 2), q) for q in range(j, len(cand))]
                        if rest and min(rest)[0] < 4 * sp:
                            pick = min(rest)[1]
                            self.problems.append(f"bar {cand[pick]['bar']} staff {k}: syllable {t['t']!r} placed by nearest note ({min(rest)[0]/sp:.1f} SP)")
                        else:
                            self.problems.append(f"p{pi+1} sys {si+1} staff {k}: syllable {t['t']!r} at x{t['x0']:.0f} has no note")
                            continue
                    cand[pick]['lyric'] = t
                    j = pick + 1
                if syls: carry = syls[-1]
        # syllabic
        for k in rows_by_staff:
            seq = [t for pi, si, top, toks in rows_by_staff[k] for t in toks if t['t'] != '-']
            for t in seq:
                a, b = t.get('join_prev'), t.get('join_next')
                t['syllabic'] = {(False, False): 'single', (False, True): 'begin', (True, True): 'middle', (True, False): 'end'}[(bool(a), bool(b))]
        return self

    @staticmethod
    def tokens(chars):
        chars = sorted(chars, key=lambda c: c['x0'])
        toks = []
        for c in chars:
            if c['text'] == ' ': continue
            c = dict(c); c['text'] = LIGATURES.get(c['text'], c['text'])
            if toks and c['x0'] - toks[-1]['x1'] < 0.25 and c['text'] != '-' and toks[-1]['t'] != '-':
                toks[-1]['t'] += c['text']; toks[-1]['x1'] = c['x1']
            else:
                toks.append({'t': c['text'], 'x0': c['x0'], 'x1': c['x1']})
        return toks

    # -------------------------------------------------------------- pass 6: marks
    def locate(self, pi, si, k, x):
        """(bar dict, onset) of the item nearest x on staff k of that system; bar start if none"""
        bars = [b for b in self.bars if b['page'] == pi and b['sys'] == si]
        bar = None
        for b in bars:
            if b['xa'] - 2 <= x <= b['xb'] + 1: bar = b; break
        if bar is None:
            bar = bars[0] if x < bars[0]['xa'] else bars[-1]
        its = [it for it in bar['staves'][k]['items'] if 'on' in it]
        if not its:
            its = [it for sb in bar['staves'] for it in sb['items'] if 'on' in it]
        if not its: return bar, F(0)
        it = min(its, key=lambda it: abs(it['x'] - x))
        return bar, it['on']

    def marks(self, chord_staff=None, chord_font=None, chord_size=None):
        self.chord_staff = chord_staff
        self.dirs = collections.defaultdict(list)     # (bar num, k) -> [dict(on, kind, ...)]
        self.harm = collections.defaultdict(list)     # bar num -> [(on, root, alter, kind text, bass, bass alter)]
        for pi, pm in enumerate(self.pms):
            for g in pm.glyphs:
                s = g.staff; si, k = s['sys'], s['k']
                if g.code in DYN:
                    bar, on = self.locate(pi, si, k, g.x0)
                    place = 'above' if g.y < s['top'] else 'below'
                    self.dirs[(bar['num'], k)].append(dict(on=on, kind='dyn', val=DYN[g.code], place=place))
                elif g.code in STACC or g.code in ACCENT:
                    bar, _ = self.locate(pi, si, k, g.cx)
                    its = [it for it in bar['staves'][k]['items'] if it['kind'] == 'chord']
                    if not its:
                        self.problems.append(f"bar {bar['num']} staff {k}: articulation with no note"); continue
                    it = min(its, key=lambda it: abs((it['x'] + it['xr']) / 2 - g.cx))
                    it.setdefault('artic', []).append('staccato' if g.code in STACC else 'accent')
                elif g.code == 0xECA5:
                    pass
            for w in pm.wedges:
                s = pm.nearest_staff(w['y']); si, k = s['sys'], s['k']
                b0, on0 = self.locate(pi, si, k, w['x0'])
                b1, on1 = self.locate(pi, si, k, w['x1'])
                # the stop: the item at or just past the wedge's end
                place = 'above' if w['y'] < s['top'] else 'below'
                self.dirs[(b0['num'], k)].append(dict(on=on0, kind='wedge', val=w['kind'], place=place))
                end_on = self.end_onset(pi, si, k, w['x1'])
                self.dirs[(end_on[0]['num'], k)].append(dict(on=end_on[1], kind='wedge', val='stop', place=place))
            # text: rehearsal marks (bold letters), tempo, other words
            words = pm.page.extract_words(extra_attrs=['fontname', 'size'], x_tolerance=1.5)
            for wd in words:
                fn = wd['fontname']
                if 'Bravura' in fn: continue
                s = pm.nearest_staff(wd['bottom'])
                si, k = s['sys'], s['k']
                if s['top'] - wd['bottom'] > 14 * s['sp'] and not (si == 0 and k == 0): continue
                if 'Bold' in fn and re.fullmatch(r'[A-Z]', wd['text']) and wd['bottom'] < s['top'] and k == 0:
                    bar, _ = self.locate(pi, si, 0, wd['x0'] + 6)
                    bar['rehearsal'] = wd['text']
                elif 'Bold' in fn:
                    bar, on = self.locate(pi, si, k, wd['x0'])
                    self.dirs[(bar['num'], k)].append(dict(on=on, kind='words', val=wd['text'], bold=True,
                                                           place='above' if wd['bottom'] < s['top'] else 'below', x=wd['x0']))
        # merge adjacent bold words into one direction
        for key_, lst in self.dirs.items():
            ws = sorted([d for d in lst if d['kind'] == 'words'], key=lambda d: d['x'])
            if len(ws) > 1:
                for d in ws[1:]: ws[0]['val'] += ' ' + d['val']; lst.remove(d)
        # tempo
        pm = self.pms[0]
        met = [g for g in pm.glyphs if g.code == 0xECA5]
        if met:
            g = met[0]
            txt = ''.join(c['text'] for c in sorted(pm.text, key=lambda c: c['x0'])
                          if abs((pm.H - c['matrix'][5]) - g.y) < 2 and g.x1 < c['x0'] < g.x1 + 30)
            m = re.search(r'=\s*(\d+)', txt)
            if m: self.tempo = int(m.group(1))
        # chord symbols
        if chord_staff is not None:
            for pi, pm in enumerate(self.pms):
                for si, sy in enumerate(pm.systems):
                    s = sy[chord_staff]; sp = s['sp']
                    prev = sy[chord_staff - 1]
                    lo = (prev['bot'] + s['top']) / 2
                    cs = [c for c in pm.page.chars if lo < c['top'] < s['top'] and c['bottom'] < s['top']
                          and (('BravuraText' in c['fontname']) or (re.search(chord_font, c['fontname']) and abs(c['size'] - chord_size) < 0.15))]
                    cs.sort(key=lambda c: c['x0'])
                    toks = []
                    for c in cs:
                        if toks and c['x0'] - toks[-1][-1]['x1'] < 1.2: toks[-1].append(c)
                        else: toks.append([c])
                    for t in toks:
                        txt = ''.join({0xED60: 'b', 0xED61: 'n', 0xED62: '#', 0xE87B: '/'}.get(ord(c['text']), c['text']) for c in t)
                        bar, on = self.locate(pi, si, chord_staff, t[0]['x0'])
                        # onset: the piano column nearest the symbol's left edge, either staff
                        cand = [it for kk in (chord_staff, chord_staff + 1) for it in bar['staves'][kk]['items'] if 'on' in it]
                        if cand:
                            it = min(cand, key=lambda it: abs(it['x'] - t[0]['x0']))
                            on = it['on']
                        self.harm[bar['num']].append((on, txt))
        return self

    def end_onset(self, pi, si, k, x):
        """a hairpin's end: the last item that starts at or before x (+1 SP), as (bar, onset + its duration if it
        ends before x)"""
        bars = [b for b in self.bars if b['page'] == pi and b['sys'] == si]
        best = None
        for b in bars:
            for it in b['staves'][k]['items']:
                if 'on' in it and it['x'] <= x + 2:
                    if best is None or it['x'] > best[1]['x']: best = (b, it)
        if best is None: return bars[0], F(0)
        return best[0], best[1]['on']

    # -------------------------------------------------------------- emit MusicXML
    def beams_of(self, it, pm):
        """[(level, 'begin'|'continue'|'end'|'forward hook'|'backward hook')] for a chord's stem"""
        t = it['stem']
        if t is None or it['base'] >= 1: return []
        sp = pm.systems[0][0]['sp']
        bs = []
        for b in pm.beams:
            if not (b['x0'] - 0.6 <= t['x'] <= b['x1'] + 0.6): continue
            w = b['x1'] - b['x0']
            f = 0 if w < 1e-6 else min(max((t['x'] - b['x0']) / w, 0), 1)
            y0 = b['yl0'] + f * (b['yr0'] - b['yl0']); y1 = b['yl1'] + f * (b['yr1'] - b['yl1'])
            if y1 < t['top'] - 0.4 or y0 > t['bot'] + 0.4: continue
            bs.append(((y0 + y1) / 2, b))
        if not bs: return []
        # level 1 is at the stem tip
        tip = t['top'] if it['dir'] == 'up' else t['bot']
        bs.sort(key=lambda p: abs(p[0] - tip))
        out = []
        for lvl, (ym, b) in enumerate(bs, 1):
            at0 = abs(b['x0'] - t['x']) < 1.0
            at1 = abs(b['x1'] - t['x']) < 1.0
            if at0 and at1: continue
            if b['x1'] - b['x0'] < 2.5 * sp and (at0 or at1):
                # a hook: does another stem sit at its other end?
                other = b['x1'] if at0 else b['x0']
                if not any(abs(s2['x'] - other) < 1.0 for s2 in pm.stems):
                    out.append((lvl, 'forward hook' if at0 else 'backward hook')); continue
            out.append((lvl, 'begin' if at0 else ('end' if at1 else 'continue')))
        return out

    def emit(self, path, meta, parts):
        """parts: [(name, abbrev, [staff indices], midi program)]"""
        DIV = 24
        E = []
        w = E.append
        w('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
        w('<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">')
        w('<score-partwise version="4.0">')
        w(f'<work><work-title>{esc(meta["title"])}</work-title></work>')
        w('<identification>')
        for role, nm in meta.get('creators', []):
            w(f'<creator type="{role}">{esc(nm)}</creator>')
        w('<encoding><software>rehearsal-tracks: Dorico PDF glyph reader</software>'
          f'<encoding-date>{meta["date"]}</encoding-date>'
          '<supports element="accidental" type="yes"/><supports element="beam" type="yes"/>'
          '<supports element="stem" type="yes"/></encoding>')
        w('</identification>')
        # page 210 x 297 mm at 7 mm per 40 tenths
        w('<defaults><scaling><millimeters>7</millimeters><tenths>40</tenths></scaling>'
          '<page-layout><page-height>1697</page-height><page-width>1200</page-width>'
          '<page-margins type="both"><left-margin>80</left-margin><right-margin>80</right-margin>'
          '<top-margin>80</top-margin><bottom-margin>80</bottom-margin></page-margins></page-layout></defaults>')
        w(f'<credit page="1"><credit-words default-x="600" default-y="1610" justify="center" valign="top" font-size="22">{esc(meta["title"])}</credit-words></credit>')
        lines = meta.get('credit_lines', [])
        if lines:
            w('<credit page="1">' + ''.join(
                (f'<credit-words default-x="1120" default-y="1540" justify="right" valign="top" font-size="10">' if i == 0
                 else '<credit-words>') + esc(l) + ('\n' if i < len(lines) - 1 else '') + '</credit-words>'
                for i, l in enumerate(lines)) + '</credit>')
        if meta.get('copyright'):
            cl = meta['copyright']
            w('<credit page="1">' + ''.join(
                (f'<credit-words default-x="600" default-y="70" justify="center" valign="bottom" font-size="6">' if i == 0
                 else '<credit-words>') + esc(l) + ('\n' if i < len(cl) - 1 else '') + '</credit-words>'
                for i, l in enumerate(cl)) + '</credit>')
        w('<part-list>')
        vocal = [p for p in parts if len(p[2]) == 1]
        if len(vocal) > 1:
            w('<part-group type="start" number="1"><group-symbol>bracket</group-symbol><group-barline>no</group-barline></part-group>')
        for pn, (name, ab, ks, prog) in enumerate(parts, 1):
            if pn == len(vocal) + 1 and len(vocal) > 1:
                w('<part-group type="stop" number="1"/>')
            w(f'<score-part id="P{pn}"><part-name>{esc(name)}</part-name><part-abbreviation>{esc(ab)}</part-abbreviation>'
              f'<score-instrument id="P{pn}-I1"><instrument-name>{esc(name)}</instrument-name></score-instrument>'
              f'<midi-instrument id="P{pn}-I1"><midi-channel>{pn if pn < 10 else pn + 1}</midi-channel><midi-program>{prog}</midi-program></midi-instrument></score-part>')
        w('</part-list>')
        for pn, (name, ab, ks, prog) in enumerate(parts, 1):
            w(f'<part id="P{pn}">')
            multi = len(ks) > 1
            cur_clefs = {}
            for bar in self.bars:
                pm = self.pms[bar['page']]
                attrs = ''
                num = bar['num']
                w(f'<measure number="{num}">')
                if num == 1 or num in self.keys:
                    a = '<attributes>'
                    if num == 1: a += f'<divisions>{DIV}</divisions>'
                    a += f'<key><fifths>{self.keys.get(num, bar["key"])}</fifths></key>'
                    if num == 1: a += '<time><beats>4</beats><beat-type>4</beat-type></time>'
                    if num == 1 and multi: a += f'<staves>{len(ks)}</staves>'
                    if num == 1:
                        for si_, k in enumerate(ks, 1):
                            c = bar['staves'][k]['clef_start'] or 'G'
                            a += clef_xml(c, si_ if multi else None); cur_clefs[k] = c
                    a += '</attributes>'
                    attrs = a
                # clef changes
                for si_, k in enumerate(ks, 1):
                    c = bar['staves'][k].get('clef_start')
                    if num > 1 and c and c != cur_clefs.get(k):
                        attrs += '<attributes>' + clef_xml(c, si_ if multi else None) + '</attributes>'
                        cur_clefs[k] = c
                w(attrs)
                if bar.get('barline_left'):
                    pass
                if pn == 1 and bar.get('rehearsal'):
                    w(f'<direction placement="above"><direction-type><rehearsal enclosure="square">{bar["rehearsal"]}</rehearsal></direction-type></direction>')
                if pn == 1 and num == 1 and getattr(self, 'tempo', None):
                    w(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
                      f'<per-minute>{self.tempo}</per-minute></metronome></direction-type><sound tempo="{self.tempo}"/></direction>')
                pos = F(0)
                for si_, k in enumerate(ks, 1):
                    sb = bar['staves'][k]
                    vs = sb['voices'] or {1: []}
                    dirs = sorted(self.dirs.get((num, k), []), key=lambda d: d['on'])
                    harm = sorted(self.harm.get(num, []), key=lambda h: h[0]) if (multi and si_ == 1 and getattr(self, 'chord_staff', None) == k) else []
                    for vn, seq in sorted(vs.items()):
                        voice = vn + (4 if si_ == 2 else 0)
                        if pos > 0:
                            w(f'<backup><duration>{int(pos * DIV)}</duration></backup>'); pos = F(0)
                        if not seq:
                            w(f'<note><rest measure="yes"/><duration>{int(self.BAR * DIV)}</duration><voice>{voice}</voice>'
                              + (f'<staff>{si_}</staff>' if multi else '') + '</note>')
                            pos = self.BAR
                            continue
                        pend_d = dirs if vn == min(vs) else []
                        pend_h = harm if vn == min(vs) else []
                        for idx, it in enumerate(seq):
                            if it['on'] > pos:
                                # directions/harmony before the gap
                                w(f'<forward><duration>{int((it["on"] - pos) * DIV)}</duration><voice>{voice}</voice>'
                                  + (f'<staff>{si_}</staff>' if multi else '') + '</forward>')
                                pos = it['on']
                            nxt_on = seq[idx + 1]['on'] if idx + 1 < len(seq) else self.BAR + 1
                            for d in [d for d in pend_d if d['on'] < nxt_on]:
                                w(direction_xml(d, d['on'] - it['on'], si_ if multi else None, DIV))
                                pend_d.remove(d)
                            for h in [h for h in pend_h if h[0] < nxt_on]:
                                w(harmony_xml(h[1], h[0] - it['on'], si_ if multi else None, DIV))
                                pend_h.remove(h)
                            w(self.note_xml(it, voice, si_ if multi else None, DIV, pm, bar))
                            pos += it['dur']
                        for d in pend_d: w(direction_xml(d, d['on'] - pos, si_ if multi else None, DIV))
                        for h in pend_h: w(harmony_xml(h[1], h[0] - pos, si_ if multi else None, DIV))
                        if pos < self.BAR:
                            w(f'<forward><duration>{int((self.BAR - pos) * DIV)}</duration><voice>{voice}</voice>'
                              + (f'<staff>{si_}</staff>' if multi else '') + '</forward>')
                            pos = self.BAR
                bl = bar['barline']
                if bar is self.bars[-1]:
                    w('<barline location="right"><bar-style>light-heavy</bar-style></barline>')
                elif bl[2] >= 2:
                    w('<barline location="right"><bar-style>light-light</bar-style></barline>')
                w('</measure>')
            w('</part>')
        w('</score-partwise>')
        open(path, 'w').write('\n'.join(E) + '\n')

    def note_xml(self, it, voice, staff, DIV, pm, bar):
        stf = f'<staff>{staff}</staff>' if staff else ''
        if it['kind'] == 'rest':
            meas = it.get('whole') and it['dur'] == self.BAR
            s = '<note>' + ('<rest measure="yes"/>' if meas else '<rest/>') + f'<duration>{int(it["dur"] * DIV)}</duration>'
            s += f'<voice>{voice}</voice>'
            if not meas: s += f'<type>{TYPE[it["base"]]}</type>' + '<dot/>' * it['dots']
            return s + stf + '</note>'
        out = ''
        beams = self.beams_of(it, pm)
        heads = sorted(it['heads'], key=lambda h: h.y, reverse=True)   # low to high
        for i, h in enumerate(heads):
            p = it['pitch'][id(h)]
            s = '<note>' + ('<chord/>' if i else '')
            s += f"<pitch><step>{p['step']}</step>" + (f"<alter>{p['alter']}</alter>" if p['alter'] else '') + f"<octave>{p['oct']}</octave></pitch>"
            s += f'<duration>{int(it["dur"] * DIV)}</duration>'
            ts = id(h) in it.get('tie_stop', set()); tb = id(h) in it.get('tie_start', set())
            if ts: s += '<tie type="stop"/>'
            if tb: s += '<tie type="start"/>'
            s += f'<voice>{voice}</voice><type>{TYPE[it["base"]]}</type>' + '<dot/>' * it['dots']
            if p['acc']:
                s += '<accidental>' + {1: 'sharp', -1: 'flat', 0: 'natural'}[p['acc_val']] + '</accidental>'
            if it['dir']: s += f'<stem>{it["dir"]}</stem>'
            if h.code == XHEAD: s += '<notehead>x</notehead>'
            s += stf
            if i == 0:
                for lvl, kind in beams: s += f'<beam number="{lvl}">{kind}</beam>'
            nots = ''
            if ts: nots += '<tied type="stop"/>'
            if tb: nots += '<tied type="start" orientation="%s"/>' % ('over' if it.get('tie_obj', {}).get(id(h)) else 'under')
            if i == 0:
                for _ in range(it.get('slur_stop', 0)): nots += '<slur type="stop" number="1"/>'
                for _ in range(it.get('slur_start', 0)): nots += '<slur type="start" number="1"/>'
                if it.get('artic'):
                    nots += '<articulations>' + ''.join(f'<{a}/>' for a in it['artic']) + '</articulations>'
            if nots: s += f'<notations>{nots}</notations>'
            if i == 0 and it.get('lyric'):
                t = it['lyric']
                s += f'<lyric number="1"><syllabic>{t["syllabic"]}</syllabic><text>{esc(t["t"])}</text>' + ('<extend/>' if t.get('extend') else '') + '</lyric>'
            s += '</note>'
            out += s
        return out


    # -------------------------------------------------------------- lyric repairs and melisma lines
    def lyric_fix(self, k, bar, on, text=None, syllabic=None, extend=None, add=None, why=''):
        """change the syllable on staff k at (bar, onset); `add` puts a new one on a note that has none"""
        b = self.bars[bar - 1]
        its = [it for v in b['staves'][k]['voices'].values() for it in v if it['kind'] == 'chord' and it['on'] == on]
        if not its: raise ValueError(f'no note on staff {k} bar {bar} at {on}')
        it = its[0]
        if add is not None:
            if it.get('lyric'): raise ValueError(f'bar {bar} staff {k} at {on} already has {it["lyric"]["t"]!r}')
            it['lyric'] = dict(t=add, syllabic=syllabic or 'single', extend=bool(extend), fixed=True)
        else:
            t = it.get('lyric')
            if t is None: raise ValueError(f'bar {bar} staff {k} at {on}: no syllable to fix')
            if text is not None: t['t'] = text
            if syllabic is not None: t['syllabic'] = syllabic
            if extend is not None: t['extend'] = extend
            t['fixed'] = True
        self.notes.append(f"FIX bar {bar} {['S','A','T','B'][k]} beat {1 + on}: {why}")

    def melisma_lines(self, vocal_staves):
        """a syllable held over moving (not tied) notes that carry no syllable gets an extender, even where
        the page prints a hyphen (SKILL.md 2.5)"""
        for k in vocal_staves:
            seq = [it for bar in self.bars for it in sorted((it for v in bar['staves'][k]['voices'].values() for it in v), key=lambda it: it['on'])]
            for i, it in enumerate(seq):
                t = it.get('lyric')
                if not t or t.get('extend'): continue
                held = []
                for nx in seq[i + 1:]:
                    if nx['kind'] != 'chord' or nx.get('lyric'): break
                    held.append(nx)
                if held and any(len(nx.get('tie_stop', ())) < len(nx['heads']) for nx in held):
                    t['extend'] = True; t['added_line'] = True
                    self.notes.append(f"LINE bar {it['bar']} {['S','A','T','B'][k]}: {t['t']!r} held over {len(held)} moving note(s); "
                                      f"the page prints {'a hyphen' if t['syllabic'] in ('begin','middle') else 'nothing'}, the file an extender")
        return self

    def matching_lines(self, vocal_staves, share=0.5):
        """a word-end syllable held only by a tie, printed without a line, gets one when the same word on the same
        figure (its note value and the length it is tied through) is printed with a line more often than not
        elsewhere in the piece: the engraver dropped it in a few places (SKILL.md 2.5)"""
        figs = {}
        for k in vocal_staves:
            seq = [it for bar in self.bars for it in sorted((it for v in bar['staves'][k]['voices'].values() for it in v), key=lambda it: it['on'])]
            for i, it in enumerate(seq):
                t = it.get('lyric')
                if not t or t['syllabic'] not in ('single', 'end') or not it.get('tie_start'): continue
                held = it['dur']
                for nx in seq[i + 1:]:
                    if nx['kind'] != 'chord' or nx.get('lyric') or not nx.get('tie_stop'): break
                    held += nx['dur']
                    if not nx.get('tie_start'): break
                figs.setdefault((t['t'], it['dur'], held), []).append((k, it, t))
        for (word, dur, held), occ in figs.items():
            lined = sum(1 for _, _, t in occ if t.get('extend'))
            if not lined or lined / len(occ) <= share: continue
            for k, it, t in occ:
                if t.get('extend'): continue
                t['extend'] = True; t['added_line'] = True
                self.notes.append(f"LINE bar {it['bar']} {['S','A','T','B'][k]}: {word!r} tied through, printed with no line; "
                                  f"{lined} of the {len(occ)} same words on the same figure have one")
        return self


LIGATURES = {'(cid:57)': 'fi'}   # Academico's fi ligature has no Unicode mapping in these PDFs

TYPE = {F(4): 'whole', F(2): 'half', F(1): 'quarter', F(1, 2): 'eighth', F(1, 4): '16th', F(1, 8): '32nd'}


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def clef_xml(c, number):
    n = f' number="{number}"' if number else ''
    return {'G': f'<clef{n}><sign>G</sign><line>2</line></clef>',
            'G8': f'<clef{n}><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>',
            'F': f'<clef{n}><sign>F</sign><line>4</line></clef>'}[c]


def direction_xml(d, off, staff, DIV):
    stf = f'<staff>{staff}</staff>' if staff else ''
    o = f'<offset>{int(off * DIV)}</offset>' if off else ''
    if d['kind'] == 'dyn':
        return (f'<direction placement="{d["place"]}"><direction-type><dynamics><{d["val"]}/></dynamics></direction-type>'
                f'{o}{stf}</direction>')
    if d['kind'] == 'wedge':
        return f'<direction placement="{d["place"]}"><direction-type><wedge type="{d["val"]}" number="1"/></direction-type>{o}{stf}</direction>'
    if d['kind'] == 'words':
        b = ' font-weight="bold"' if d.get('bold') else ''
        return f'<direction placement="{d["place"]}"><direction-type><words{b}>{esc(d["val"])}</words></direction-type>{o}{stf}</direction>'
    raise ValueError(d)


KIND = [('maj7', 'major-seventh', None), ('m7', 'minor-seventh', None), ('sus2', 'suspended-second', None),
        ('sus4', 'suspended-fourth', None), ('sus', 'suspended-fourth', None), ('m', 'minor', None),
        ('7', 'dominant', None), ('6', 'major-sixth', None), ('add9', 'major', 'add9'), ('', 'major', None)]


def harmony_xml(txt, off, staff, DIV):
    m = re.fullmatch(r'([A-G])([b#n]?)(.*?)(?:/([A-G])([b#n]?))?', txt)
    if not m: raise ValueError(f'chord symbol {txt!r}')
    root, ra, rest, bass, ba = m.groups()
    alt = {'b': -1, '#': 1}
    kind = None
    for suf, k, deg in KIND:
        if rest == suf: kind = (k, suf); break
    if kind is None: raise ValueError(f'chord kind {rest!r} in {txt!r}')
    s = '<harmony print-frame="no"><root><root-step>%s</root-step>%s</root>' % (root, f'<root-alter>{alt[ra]}</root-alter>' if ra in alt else '')
    s += f'<kind text="{esc(rest)}">{kind[0]}</kind>'
    if bass:
        s += '<bass><bass-step>%s</bass-step>%s</bass>' % (bass, f'<bass-alter>{alt[ba]}</bass-alter>' if ba in alt else '')
    if off: s += f'<offset>{int(off * DIV)}</offset>'
    if staff: s += f'<staff>{staff}</staff>'
    return s + '</harmony>'



def finish(r, pre, final, meta, parts):
    """Write the file twice: `pre` exactly as read, and `final` with words ended at melismas so Sibelius draws the
    extender lines (SKILL.md 2.5). Make any Cantai copy from `pre`: Cantai reads the hyphens."""
    from chorale.musicxml import break_words_at_melismas
    r.emit(pre, meta, parts)
    xml, changed = break_words_at_melismas(open(pre).read())
    open(final, 'w').write(xml)
    print('problems', len(r.problems)); print('\n'.join(r.problems))
    print('notes', len(getattr(r, 'notes', []))); print('\n'.join(getattr(r, 'notes', [])))
    print('word breaks at melismas', len(changed)); print('\n'.join(changed))
