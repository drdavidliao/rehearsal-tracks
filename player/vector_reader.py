"""Bars, beats and noteheads of a vector score PDF in any engraver's music font, with the MusicXML saying what's in each bar.

dorico_reader.py reads a Dorico score's rhythms from the page; this only finds where things are. Staves are five long
horizontal lines; a barline is a stroke from a staff's top line to its bottom line at the same x on every staff of the
system; noteheads are the music font's head glyphs. Sibelius's Opus, Finale's Maestro and Helsinki (old Sonata layout:
0xCF black, 0xFA half, 'w' whole, under any of three encodings) and SMuFL fonts (Bravura, Leland) are known, and LilyPond's Emmentaler by the glyph names in its encoding.

Each part's notes come from the MusicXML. A part's staff is named by a label (two parts on one staff share it), and a
system's staves are labelled by how many it has:
    staff_of = {"Tenor": "TL", "Lead": "TL", "Baritone": "BB", "Bass": "BB"}
    layouts = {2: ["TL", "BB"], 4: ["TL", "BB", "P", "P"]}
A label no part has (a piano staff) is ignored. Where the number of staves doesn't say which they are, `names` does by
the staff names printed at their left, as (regular expression, label) pairs, first match winning:
    names = [("Solo", "S"), ("T", "TT"), ("B", "BB")]
The heads of a staff's bar are matched to the onsets its parts sound
there, left to right; at an onset each part takes the head nearest the place its pitch has under the part's clef.
"""
import collections, re
import xml.etree.ElementTree as ET
from fractions import Fraction as F
import pdfplumber
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import verify

SONATA = {0xCF: 'black', 0xFA: 'half', 0x77: 'whole', 0xB7: 'rest', 0xEE: 'rest', 0xCE: 'rest', 0xE4: 'rest', 0xC5: 'rest', 0xA8: 'rest'}
SMUFL = {0xE0A4: 'black', 0xE0A3: 'half', 0xE0A2: 'whole', 0xE0A0: 'whole', **{c: 'rest' for c in range(0xE4E3, 0xE4EA)}}
MUSIC_FONTS = ('Opus', 'Maestro', 'Helsinki', 'Petrucci', 'Engraver', 'Jazz', 'Bravura', 'Leland', 'Petaluma', 'Finale')
SMUFL_FONTS = ('Bravura', 'Leland', 'Petaluma', 'FinaleMaestro', 'FinaleBroadway', 'FinaleJazz')
STEPS = 'CDEFGAB'


EMMENTALER = {}     # LilyPond's subset fonts: their name in the PDF -> {code: glyph name}, from each font's encoding


def read_emmentaler(path):
    from pypdf import PdfReader
    for page in PdfReader(path).pages:
        for v in (page['/Resources'].get('/Font') or {}).values():
            f = v.get_object(); base = str(f.get('/BaseFont', '')).lstrip('/')
            enc = f.get('/Encoding')
            if 'Emmentaler' not in base or base in EMMENTALER or not hasattr(enc, 'get'): continue
            names, code = {}, 0
            for d in enc.get_object().get('/Differences', []):
                if isinstance(d, (int, float)): code = int(d)
                else: names[code] = str(d).lstrip('/'); code += 1
            EMMENTALER[base] = names


def emmentaler_kind(ch):
    m = re.match(r'\(cid:(\d+)\)', ch['text'])
    name = EMMENTALER.get(ch['fontname'], {}).get(int(m.group(1)) if m else ord(ch['text'][0]), '')
    if name.startswith('rests.'): return 'rest'
    return {'noteheads.s0': 'whole', 'noteheads.s1': 'half', 'noteheads.s2': 'black', 'noteheads.s2cross': 'black'}.get(name)


def head_kind(ch):
    if 'Emmentaler' in ch['fontname']: return emmentaler_kind(ch)
    fn = ch['fontname'].split('+')[-1]
    if not any(m in fn for m in MUSIC_FONTS) or 'Text' in fn or 'Chord' in fn or 'Special' in fn: return None
    c = ord(ch['text'][0])
    if any(m in fn for m in SMUFL_FONTS): return SMUFL.get(c)
    if 0xF000 <= c < 0xF100: c -= 0xF000                  # a symbol font's private-use copy of its byte
    elif c >= 0x80:
        try: c = ch['text'][0].encode('mac_roman')[0]     # the "Std" fonts give the Mac Roman character for the byte
        except UnicodeEncodeError: return None
    return SONATA.get(c)


def cluster(xs, tol):
    out = []
    for x in sorted(xs):
        if out and x - out[-1][-1] <= tol: out[-1].append(x)
        else: out.append([x])
    return out


def read_parts(path):
    """per part: its clef's bottom line as a diatonic number, and per bar its sounding notes (each head, ties included):
    (onset, diatonic number, midi); plus the bar lengths in quarters"""
    root = ET.parse(path).getroot()
    names = {sp.get('id'): sp.findtext('part-name') for sp in root.iter('score-part')}
    out, bottom, lengths = {}, {}, []
    for pi, part in enumerate(root.findall('part')):
        name = names[part.get('id')]
        div = 1; bars = []
        for mi, m in enumerate(part.findall('measure')):
            pos = mx = F(0); notes = []
            for e in m:
                if e.tag == 'attributes':
                    if e.find('divisions') is not None: div = int(e.findtext('divisions'))
                    c = e.find('clef')
                    if c is not None and name not in bottom:
                        sign, line = c.findtext('sign'), int(c.findtext('line') or 2)
                        octave = int(c.findtext('clef-octave-change') or 0)
                        # the clef's own note and the line it sits on give the bottom line
                        ref = {'G': 4 * 7 + 4, 'F': 3 * 7 + 3, 'C': 4 * 7 + 0}.get(sign, 4 * 7 + 4) + 7 * octave
                        bottom[name] = ref - 2 * (line - 1)
                elif e.tag == 'backup': pos -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward': pos += F(int(e.findtext('duration')), div); mx = max(mx, pos)
                elif e.tag == 'note':
                    if e.find('grace') is not None: continue
                    chord = e.find('chord') is not None
                    d = F(int(e.findtext('duration') or 0), div)
                    if chord: pos -= last_d
                    if e.find('rest') is None and e.find('pitch') is not None:
                        p = e.find('pitch'); oc = int(p.findtext('octave')); st = p.findtext('step')
                        midi = 12 * (oc + 1) + [0, 2, 4, 5, 7, 9, 11][STEPS.index(st)] + int(float(p.findtext('alter') or 0))
                        notes.append((pos, oc * 7 + STEPS.index(st), midi))
                    pos += d; last_d = d; mx = max(mx, pos)
            bars.append(notes)
            if pi == 0: lengths.append(mx)
        out[name] = bars
    return out, bottom, lengths


def align(cols, onsets, xa, xb, length):
    """columns (x) to onsets (quarters), in order, skipping on either side where the counts differ: by place in the bar"""
    if len(cols) == len(onsets): return list(zip(range(len(cols)), range(len(onsets))))
    if not cols or not onsets: return []
    w = max(xb - xa, 1); L = float(length) or 1
    cx = [(c - xa) / w for c in cols]; oq = [float(q) / L for q in onsets]
    n, m = len(cx), len(oq)
    INF = 1e9; skip = 0.25
    D = [[INF] * (m + 1) for _ in range(n + 1)]; B = [[None] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            if D[i][j] >= INF: continue
            if i < n and j < m and D[i][j] + abs(cx[i] - oq[j]) < D[i + 1][j + 1]:
                D[i + 1][j + 1] = D[i][j] + abs(cx[i] - oq[j]); B[i + 1][j + 1] = (i, j, True)
            if i < n and D[i][j] + skip < D[i + 1][j]: D[i + 1][j] = D[i][j] + skip; B[i + 1][j] = (i, j, False)
            if j < m and D[i][j] + skip < D[i][j + 1]: D[i][j + 1] = D[i][j] + skip; B[i][j + 1] = (i, j, False)
    out = []; i, j = n, m
    while (i, j) != (0, 0):
        pi, pj, match = B[i][j]
        if match: out.append((pi, pj))
        i, j = pi, pj
    return out[::-1]


def rests_in(page, top, bot):
    return [(c['x0'] + c['x1']) / 2 for c in page.chars if head_kind(c) == 'rest' and top < (c['top'] + c['bottom']) / 2 < bot]


class Score:
    def __init__(self, pdf_path, xml_path, staff_of, layouts=None, names=None):
        parts, bottom, lengths = read_parts(xml_path)
        self.lengths = lengths
        labels = list(dict.fromkeys(staff_of.values()))
        layouts = layouts or {len(labels): labels}
        self.bars, self.systems, self.heads, self.problems = [], {}, {}, []
        self.pdf = pdfplumber.open(pdf_path)
        read_emmentaler(pdf_path)
        self.H = float(self.pdf.pages[0].height)
        for pi, page in enumerate(self.pdf.pages):
            st = verify.staves_of(page)
            if not st: continue
            for s in st:
                s['sp'] = (s['lines'][4] - s['lines'][0]) / 4; s['top'], s['bot'] = s['lines'][0], s['lines'][4]
            strokes = [(l['x0'], l['top'], l['bottom']) for l in page.lines if abs(l['x0'] - l['x1']) < 0.3]
            strokes += [((r['x0'] + r['x1']) / 2, r['top'], r['bottom']) for r in page.rects if r['width'] < 6 and r['height'] > 8]
            def bar_xs(s):
                return {round(x, 1) for x, t, b in strokes if t <= s['top'] + 0.7 and b >= s['bot'] - 0.7 and t >= s['top'] - 0.7 - 30 * s['sp']}
            for s in st: s['bx'] = bar_xs(s)
            # systems: staves joined at the left, then neighbours that share their barlines
            groups = verify.systems_of(page, st)
            merged = []
            for g in groups:
                if merged:
                    def common(grp): return {x for x in grp[0]['bx'] if all(any(abs(x - y) < 1 for y in s['bx']) for s in grp)}
                    a, b = common(merged[-1]), common(g)
                    near = sum(1 for x in a if any(abs(x - y) < 1 for y in b))
                    fits = len(merged[-1]) + len(g) <= max(layouts) and (len(merged[-1]) not in layouts or len(g) not in layouts)
                    if fits and a and b and near >= 0.6 * min(len(a), len(b)) and len(a) > 1:
                        merged[-1] = merged[-1] + g; continue
                merged.append(g)
            heads = []
            for ch in page.chars:
                k = head_kind(ch)
                if k and k != 'rest': heads.append(dict(kind=k, cx=(ch['x0'] + ch['x1']) / 2, y=float(page.height) - ch['matrix'][5]))
            if not heads:
                # no music font: heads drawn as filled paths (Verovio through cairo), told by their size against the staff
                for cv in page.curves:
                    if not cv.get('fill'): continue
                    w, h = cv['x1'] - cv['x0'], cv['bottom'] - cv['top']
                    y = (cv['top'] + cv['bottom']) / 2
                    sp = self.nearest(st, y)['sp']
                    if 1.0 * sp <= w <= 2.4 * sp and 0.85 * sp <= h <= 1.25 * sp:
                        heads.append(dict(kind='path', cx=(cv['x0'] + cv['x1']) / 2, y=y))
            for si, sy in enumerate(merged):
                lay = layouts.get(len(sy))
                if names:
                    # the staff's name, printed at its left: a staff it names takes that label, another (a piano's lower
                    # staff) none
                    named = []
                    for s in sy:
                        txt = ''.join(c['text'] for c in sorted(page.chars, key=lambda c: (round(c['top']), c['x0']))
                                      if c['x1'] < s['x0'] + 1 and c['x0'] > s['x0'] - 90
                                      and s['top'] - s['sp'] <= (c['top'] + c['bottom']) / 2 <= s['bot'] + s['sp'])
                        named.append(next((lab for pat, lab in names if re.search(pat, txt)), None))
                    if any(named): lay = named
                if lay is None:
                    self.problems.append(f'page {pi + 1} system {si + 1}: {len(sy)} staves, no layout for that'); continue
                # a barline: a stroke on every staff at one x (within a point)
                xs = cluster(sorted(set.union(*[s['bx'] for s in sy])), 1.0)
                bls = [g for g in xs if all(any(abs(x - y) < 1.0 for y in s['bx'] for x in g) for s in sy)]
                bls = cluster([x for g in bls for x in g], 4.5)
                start = min(s['x0'] for s in sy)
                bls = [g for g in bls if g[0] > start + 2]
                # a start repeat after the clef and key: no note or rest before it
                top_, bot_ = sy[0]['top'] - 6 * sy[0]['sp'], sy[-1]['bot'] + 6 * sy[-1]['sp']
                if bls and not any(start < h['cx'] < bls[0][0] and top_ < h['y'] < bot_ for h in heads) \
                        and not any(start < x < bls[0][0] for x in rests_in(page, top_, bot_)):
                    start = bls[0][-1]; bls = bls[1:]
                self.systems[(pi, si)] = dict(page=pi, sys=si, top=sy[0]['top'], bottom=sy[-1]['bot'])
                edges = [start] + [g[-1] for g in bls]
                rests = rests_in(page, top_, bot_)
                for bi, g in enumerate(bls):
                    xa, xb = edges[bi], g[0]
                    num = len(self.bars)
                    # where beat 1 is printed when no voice sings on it: the bar's first head or rest on any staff, the
                    # piano's included (a whole-bar rest, centred, doesn't count)
                    mid, w = (xa + xb) / 2, xb - xa
                    xs = [h['cx'] for h in heads if xa < h['cx'] < xb and top_ < h['y'] < bot_] + \
                         [x for x in rests if xa < x < xb and abs(x - mid) > 0.1 * w]
                    bar = dict(num=num + 1, page=pi, sys=si, xa=round(xa, 2), xb=round(xb, 2), first_in_system=bi == 0, known={},
                               first_x=round(min(xs), 2) if xs else None)
                    self.bars.append(bar)
                    if num >= len(lengths): continue
                    for k, s in enumerate(sy):
                        mine = [p for p, lab in staff_of.items() if lab == lay[k] and p in parts]
                        if not mine: continue
                        hs = [h for h in heads if xa < h.get('cx') < xb and self.nearest(st, h['y']) is s]
                        onsets = sorted({q for p in mine for q, _, _ in parts[p][num]})
                        # columns: a tolerance that makes as many as there are onsets, if one does
                        cols = None
                        for tol in (1.4, 1.0, 0.6, 1.8, 0.3):
                            c = cluster([h['cx'] for h in hs], tol * s['sp'])
                            if cols is None or len(c) == len(onsets): cols = c
                            if len(c) == len(onsets): break
                        pairs = align([sum(c) / len(c) for c in cols], onsets, xa, xb, lengths[num])
                        if len(cols) != len(onsets):
                            self.problems.append(f'bar {num + 1} staff {lay[k]}: {len(cols)} head columns, {len(onsets)} onsets')
                        for ci, oi in pairs:
                            col = [h for h in hs if cols[ci][0] - 0.01 <= h['cx'] <= cols[ci][-1] + 0.01]
                            q = onsets[oi]
                            bar['known'].setdefault(q, []).append(sum(cols[ci]) / len(cols[ci]))
                            for p in mine:
                                for q2, dia, midi in parts[p][num]:
                                    if q2 != q: continue
                                    want = s['bot'] - (dia - bottom.get(p, 30)) * s['sp'] / 2
                                    h = min(col, key=lambda h: abs(h['y'] - want))
                                    self.heads.setdefault((p, num, q), []).append(dict(page=pi, x=round(h['cx'], 2), y=round(h['y'], 2), midi=midi))
        for b in self.bars:
            b['known'] = {q: sum(v) / len(v) for q, v in b['known'].items()}

    @staticmethod
    def nearest(st, y):
        return min(st, key=lambda s: 0 if s['top'] <= y <= s['bot'] else min(abs(y - s['top']), abs(y - s['bot'])))

    def head(self, part, bar_i, q, midi):
        """the head of the part's note of this pitch at this onset"""
        hs = self.heads.get((part, bar_i, q), [])
        h = next((h for h in hs if h['midi'] == midi), hs[0] if hs else None)
        return None if h is None else dict(page=h['page'], x=h['x'], y=h['y'])
