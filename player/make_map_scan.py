#!/usr/bin/env python3
"""The player's map for a song whose score is a scan: bars and heads read from the pixels through scanproof, times from the
tempo marks and hand-measured anchors (see README.md here).

    python3 player/make_map_scan.py "song folder" --score scan.pdf --xml open.musicxml --systems systems.json
        --proofs proofA proofB ... --stems "T1=...wav" "T2=...wav" "Bar=...wav" "B=...wav" "Solo=...wav" "I=...mp3"
        --part-stems "Solo=Solo" "Tenor 1=T1" "Tenor 2=T2" "Baritone=Bar" "Bass=B"
        --staff "Tenor 1=TT" "Tenor 2=TT" "Baritone=BB" "Bass=BB" "Solo=S,S2,S3" --anchor 0=1.05 --anchor 9=19.05 --swing 0.62 --tempo 156

--stems names each stem by any key, I being the instrumental one (leave it out for none). --part-stems says which stem sings
each MusicXML part, top to bottom as in the score; the map's voices follow that order, and two parts on one stem are one
voice, named for both.

systems.json: for each system image a scanproof project names, {"file": "s01a.png", "page": 0, "sys": 0, "y0": 0}: its PDF page counted
from 0, its index on the page, and the row of the page image it was cut from. Without a vector PDF there is no dark copy: the app's
page filter does Dark.
"""
import argparse, json, os, sys
from fractions import Fraction as F
import numpy as np
import pdfplumber
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
import make_map as mm
from scanproof.project import Project, STEPS
from scanproof import compare, expected, geom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder'); ap.add_argument('--score', required=True); ap.add_argument('--xml', required=True)
    ap.add_argument('--systems', required=True); ap.add_argument('--proofs', nargs='+', required=True)
    ap.add_argument('--stems', nargs='+', required=True); ap.add_argument('--part-stems', nargs='+', required=True)
    ap.add_argument('--staff', nargs='+', required=True); ap.add_argument('--anchor', action='append', default=[])
    ap.add_argument('--swing', type=float, default=0.5); ap.add_argument('--tempo', type=float, required=True)
    a = ap.parse_args()
    at = lambda f: os.path.join(a.folder, f)
    stems = dict(s.split('=', 1) for s in a.stems)
    stem_of = dict(s.split('=', 1) for s in a.part_stems)
    staves_of = {k: v.split(',') for k, v in (s.split('=', 1) for s in a.staff)}
    anchors = {int(k): float(v) for k, v in (s.split('=', 1) for s in a.anchor)}
    systems = {os.path.basename(s['file']): s for s in json.load(open(at(a.systems)))}
    with pdfplumber.open(at(a.score)) as p:
        sizes = [(float(pg.width), float(pg.height)) for pg in p.pages]

    xbars, _ = mm.read_xml(at(a.xml))
    # score seconds from the tempo marks, each stretch starting at its anchor
    tempo = next(t for b in xbars for _, t in b['tempos'])
    starts = []
    def piece(i, q):
        cur = starts[i][1]; pos = F(0); out = 0.0
        for at_, tp in xbars[i]['tempos']:
            if at_ >= q: break
            out += float(at_ - pos) * 60 / cur; pos = at_; cur = tp
        return out + float(q - pos) * 60 / cur
    t = None
    for i, b in enumerate(xbars):
        if i in anchors: t = anchors[i]
        starts.append((t, tempo))
        t = t + piece(i, b['quarters'])
        if b['tempos']: tempo = b['tempos'][-1][1]
    total = t
    numbers = sorted(n for k in a.proofs for n in Project(at(os.path.join(k, 'proof.json'))).bars())
    index = {n: i for i, n in enumerate(numbers)}
    def secs(i, q):
        return starts[i][0] + piece(i, q)
    def swung(i, q):
        whole = q.numerator // q.denominator
        return float(whole) + a.swing if q - whole == F(1, 2) and starts[i][1] >= 140 else float(q)
    def note_secs(i, q):
        # a swung offbeat, in the tempo of its bar
        f = swung(i, q)
        whole = int(f)
        return secs(i, F(whole)) + (f - whole) * 60 / starts[i][1]

    # what the pixels say: for each bar, onset -> x and staff/onset -> heads
    bars, sysd, found = [], {}, {}
    for k in a.proofs:
        prj = Project(at(os.path.join(k, 'proof.json')))
        E = expected.events(prj)
        B = prj.bars()
        for n in sorted(B):
            b = B[n]
            fname = os.path.basename(prj.page_paths[b['page'] - 1])
            sy = systems[fname]
            w, h = Image.open(prj.page_paths[b['page'] - 1]).size
            pw, ph = sizes[sy['page']]
            sx = pw / w
            # the page images fill the page: rows on the page image scale the same way as columns
            def P(x, y, sx=sx, y0=sy['y0']): return x * sx, (y + y0) * sx
            known = {}
            for name in prj.names:
                evs = E.get((name, n), [])
                st = prj.staff(b, name)
                hh, M, st = compare.read_bar(prj, b, name, evs)
                cols = compare.columns(hh, st['space']) if hh else []
                for ci, ei in compare.align(cols, evs):
                    if ci is None or ei is None: continue
                    x = float(np.mean([c['x'] for c in cols[ci]]))
                    known.setdefault(evs[ei]['onset'], []).append(x)
                    found[(name, n, evs[ei]['onset'])] = (cols[ci], st, prj.bottom(name), P)
                for ev in evs:      # a whole note's place, when the reader passed over it
                    found.setdefault((name, n, ev['onset']), (None, st, prj.bottom(name), P))
            x = xbars[index[n]]
            known = {q: float(np.median(v)) for q, v in known.items() if q < x['quarters']}
            xa, xb = b['x0'], b['x1']
            x0 = known.get(F(0), xa + (st['space'] * (b['start_space'] if b['first_in_system'] else 2)))
            qs = sorted(q for q in known if q > 0)
            px = [0.0] + [float(q) for q in qs] + [float(x['quarters'])]
            py = [x0] + [known[q] for q in qs] + [xb]
            nb = int(x['quarters'])
            beat_x = [float(np.interp(j, px, py)) for j in range(nb)]
            i = index[n]
            first, last = prj.staff(b, prj.names[0]), prj.staff(b, prj.names[-1])
            mid = (xa + xb) / 2
            top = P(0, geom.y_of_step(first, mid, 8))[1]; bot = P(0, geom.y_of_step(last, mid, 0))[1]
            s = sysd.setdefault((sy['page'], sy['sys']), dict(page=sy['page'], sys=sy['sys'], top=top, bottom=bot))
            s['top'] = min(s['top'], top); s['bottom'] = max(s['bottom'], bot)
            bars.append(dict(num=n, page=sy['page'], sys=sy['sys'], xa=round(P(xa, 0)[0], 2), xb=round(P(xb, 0)[0], 2), letter=x['letter'],
                             beat_x=[round(P(v, 0)[0], 2) for v in beat_x],
                             beat_t=[round(secs(i, F(j)), 4) for j in range(nb)],
                             end_t=round(secs(i, x['quarters']), 4)))

    parts = [p for p in stem_of if p in staves_of]
    vnotes, _ = mm.read_voice_notes(at(a.xml), parts)
    notes = []
    for name in parts:
        stem = stem_of[name]
        env = mm.fine_envelope(at(stems[stem]))
        for n in vnotes[name]:
            bi, q = n['start']; ei, qe = n['end']
            n['start_t'] = note_secs(bi, q)
            n['end_t'] = note_secs(ei, qe) if qe < xbars[ei]['quarters'] else secs(ei, qe)
        moved = mm.snap_notes(vnotes[name], env)
        lost = 0
        for n in vnotes[name]:
            heads = []
            for hb, hq in n['heads']:
                num = numbers[hb]
                hit = next((found[(st, num, hq)] for st in staves_of[name] if (st, num, hq) in found), None)
                if hit is None:
                    lost += 1; continue
                cols, st, bottom, P = hit
                # the staff step of this pitch: letters from its MIDI number, sharps as written in a sharp key
                name12 = 'C C D D E F F G G A A B'.split()[n['midi'] % 12]
                oct_ = n['midi'] // 12 - 1
                s = STEPS.index(name12) + 7 * oct_ - bottom
                c = None
                if cols:
                    c = next((h for h in cols if h['step'] == s), None) or min(cols, key=lambda h: abs(h['step'] - s))
                if c is not None:
                    x_, y_ = c['x'], geom.y_of_step(st, c['x'], s)
                else:
                    bar = next(b for b in bars if b['num'] == num)
                    pg_x = bar['beat_x'][min(int(hq), len(bar['beat_x']) - 1)]
                    x_ = pg_x / P(1, 0)[0]; y_ = geom.y_of_step(st, x_, s)
                X, Y = P(x_, y_)
                pg = next(b for b in bars if b['num'] == num)['page']
                heads.append(dict(page=pg, x=round(X, 2), y=round(Y, 2)))
            if not heads: continue
            bi, q = n['start']
            notes.append(dict(id=f'{stem}.{numbers[bi]}.{float(q):g}', part=stem, bar=numbers[bi], beat=round(float(q) + 1, 2), midi=n['midi'],
                              word=n['word'], start=round(n['start_t'], 4), end=round(n['end_t'], 4), heads=heads))
        print(f'{name}: {len(vnotes[name])} notes, {moved} starts snapped to the stem, {lost} heads not found')
    voices = []
    for part, stem in stem_of.items():
        v = next((v for v in voices if v['key'] == stem), None)
        if v: v['name'] += ' and ' + part
        else: voices.append(dict(key=stem, name=part))
    m = dict(voices=voices, notes=notes, score=a.score, stems=stems, offset=round(starts[0][0], 4), page_height=sizes[0][1], pages=len(sizes),
             tempo=a.tempo, music_end=round(total, 4), systems=list(sysd.values()), bars=bars)
    with open(at('player map.json'), 'w') as f:
        json.dump(m, f, indent=0)
    print('wrote player map.json:', len(bars), 'bars, letters', [b['letter'] for b in bars if b['letter']], 'music ends', m['music_end'])


if __name__ == '__main__':
    main()
