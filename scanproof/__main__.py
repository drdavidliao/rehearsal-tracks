"""python3 -m scanproof COMMAND proof.json ...

    bars PROOF [--redo]          draft the bar table from detected barlines (out/bars.draft.json)
                                 and draw overlays of every page; with a bar table already in
                                 place, draw that instead.  Also lists staves whose fitted
                                 lines miss the printed ones by more than 1.5 px.
    check PROOF [BAR ...]        read every staff of every bar and compare: out/findings.json
    review PROOF [TYPE ...]      review sheets of the findings (all, or only these types):
                                 out/review/review_NN.png
    zoom PROOF BAR STAFF [X0 X1] one staff of one bar enlarged, every staff position named:
                                 out/zoom/bBAR-STAFF.png
    question PROOF BAR STAFF MUSICXML [--to BAR2] [--title TEXT]
                                 scan above, the MusicXML's rendering below, for asking the
                                 user: out/questions/bBAR-STAFF.png
"""
import json
import os
import sys

from . import bars as bars_mod
from . import compare, geom, review
from .project import Project


def main(argv):
    if len(argv) < 2 or argv[0] in ('-h', '--help'):
        raise SystemExit(__doc__)
    cmd, prj = argv[0], Project(argv[1])
    rest = argv[2:]
    if cmd == 'bars':
        geo = prj.geometry(redo='--redo' in rest)
        for p in sorted(geo):
            for si, st in enumerate(geo[p]['staves']):
                miss = geom.fit_miss(prj.page(p), st)
                if miss > 1.5:
                    print(f'page {p} staff {si}: fitted lines miss the print by {miss:.1f} px (90th pct)')
        path = prj.rel(prj.cfg.get('bars', 'bars.json'))
        if os.path.exists(path):
            table = bars_mod.read(prj)
            what = f'the bar table {path}'
        else:
            table, notes = bars_mod.draft(prj)
            draft = prj.outfile('bars.draft.json')
            bars_mod.save(table, draft)
            print('\n'.join(notes))
            what = f'a draft, {draft}: correct it on the overlays, then save it as {path}'
        os.makedirs(prj.outfile('overlay'), exist_ok=True)
        paths = bars_mod.overlay(prj, table, os.path.join(prj.outfile('overlay'), 'p{page:02d}.png'))
        n = sum(len(s['barlines']) - 1 for s in table['systems'])
        print(f'{n} bars in {what}\noverlays: {os.path.dirname(paths[0])}')
    elif cmd == 'check':
        res = compare.check(prj, [int(a) for a in rest] or None)
        compare.save(res, prj.outfile('findings.json'))
        print(json.dumps(res['stats']))
        for t, n in sorted(res['counts'].items(), key=lambda kv: -kv[1]):
            print(f'{n:5d}  {t}')
        print('note values, transcribed beams -> read:', json.dumps(res['value_confusion']))
        print(f'-> {prj.outfile("findings.json")}')
    elif cmd == 'review':
        with open(prj.outfile('findings.json')) as fh:
            F = json.load(fh)['findings']
        paths, n = review.sheets(prj, F, prj.outfile('review'), set(rest) or None)
        print(f'{len(paths)} sheets, {n} staff-bars -> {prj.outfile("review")}')
    elif cmd == 'zoom':
        bar, staff = int(rest[0]), rest[1]
        x0, x1 = (float(rest[2]), float(rest[3])) if len(rest) >= 4 else (None, None)
        os.makedirs(prj.outfile('zoom'), exist_ok=True)
        tag = f'-{int(x0)}-{int(x1)}' if x0 is not None else ''
        print(review.zoom(prj, bar, staff, prj.outfile(f'zoom/b{bar}-{staff}{tag}.png'), x0, x1))
    elif cmd == 'question':
        bar, staff, mx = int(rest[0]), rest[1], rest[2]
        to = int(rest[rest.index('--to') + 1]) if '--to' in rest else None
        title = rest[rest.index('--title') + 1] if '--title' in rest else None
        os.makedirs(prj.outfile('questions'), exist_ok=True)
        print(review.question(prj, bar, staff, mx, prj.outfile(f'questions/b{bar}-{staff}.png'),
                              to, title))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
