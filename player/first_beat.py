#!/usr/bin/env python3
"""Beat 1's place in a scan map's bars where no voice sings on beat 1 (piano bars, a voice entering late), read from the
page: the leftmost filled notehead on any staff of the system, piano included, past the clef and key.

    python3 player/first_beat.py "song folder"            prints the bars it would move, and a picture to check
    python3 player/first_beat.py "song folder" --write    and moves them in player map.json
    python3 player/first_beat.py "song folder" --write --bars 1 4    only these

Look at the picture before writing: a time signature's digits, a key signature's flats or a rest can pass for a head, and
then beat 1 lands on them (We Three Kings 1 and 14, Frosty's pickup, Sleigh Ride 1 and 59 did); --bars writes the right ones.

make_map_scan.py puts such a bar's beat 1 a fixed number of staff spaces after its start (scanproof's start_space, 7, or
11 in a system's first bar), which can land a beat or more past the first chord. Here the page is rendered at 150 dpi,
staff lines are found as rows inked across a third of the bar, and an opening with a disk about half a space across leaves
filled heads (lines, stems, flats and thin clef strokes go). A head is a blob 0.7-1.9 spaces wide and 0.5-1.4 high
within a staff, searched from half of make_map_scan's guess after the bar's start (past the clef and key) to the bar's
first voice note. Hollow heads and chord clusters aren't found, so only a head before the guess moves beat 1 (one
after it may be a later beat); otherwise the bar keeps its place. The other beats are spread from the
new beat 1 through the voice notes' places to the bar's end, as make_map_scan does.
"""
import argparse, json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

DPI = 150
K = DPI / 72


def staves(grey):
    """the staff lines' rows in this strip, as (top, bottom, space) per five-line staff (lines can print grey, and a
    scan's tilt spreads a line over rows that are each only partly inked)"""
    rows = np.where((grey < 200).mean(1) > 0.3)[0]
    lines = []
    for r in rows:
        if lines and r - lines[-1][-1] <= 1: lines[-1].append(r)
        else: lines.append([r])
    c = [float(np.mean(l)) for l in lines]
    out = []
    i = 0
    while i + 4 < len(c):
        gaps = np.diff(c[i:i + 5])
        if gaps.max() < 1.3 * gaps.min():
            out.append((c[i], c[i + 4], float(gaps.mean()))); i += 5
        else: i += 1
    return out


def first_head(grey, x_from, x_to):
    """x (pixels) of the leftmost filled head in columns x_from..x_to of this system strip (grey levels), or None"""
    if x_to - x_from < 10: return None
    st = staves(grey[:, x_from:x_to])
    g = grey < 128
    if not st: return None
    sp = float(np.median([s[2] for s in st]))
    r = max(1, int(round(sp * 0.25)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    heads = ndimage.binary_opening(g[:, x_from:x_to], structure=(xx ** 2 + yy ** 2 <= r * r))
    lab, n = ndimage.label(heads)
    best = None
    for sl in ndimage.find_objects(lab):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (0.7 * sp <= w <= 1.9 * sp and 0.5 * sp <= h <= 1.4 * sp): continue
        cy = (sl[0].start + sl[0].stop) / 2
        if not any(t - 1.5 * sp <= cy <= b + 1.5 * sp for t, b, _ in st): continue
        cx = x_from + (sl[1].start + sl[1].stop) / 2
        if best is None or cx < best: best = cx
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder'); ap.add_argument('--write', action='store_true')
    ap.add_argument('--bars', nargs='+', type=int, help='with --write: only these of the bars it would move (the ones the picture shows right)')
    ap.add_argument('--picture', help='where to save the check picture (default: a temporary folder)')
    a = ap.parse_args()
    mp = os.path.join(a.folder, 'player map.json')
    m = json.load(open(mp))
    tmp = tempfile.mkdtemp()
    subprocess.run(['pdftoppm', '-r', str(DPI), '-png', os.path.join(a.folder, m['score']), os.path.join(tmp, 'p')], check=True)
    pages = [os.path.join(tmp, f) for f in sorted(os.listdir(tmp)) if f.endswith('.png')]
    imgs = {}
    # the voice notes' places, by bar and beat, from the bars' first passes
    known = {}
    for nt in m['notes']:
        if "'" in nt['id'] or not nt.get('heads'): continue
        known.setdefault(nt['bar'], {}).setdefault(nt['beat'] - 1, []).append(float(np.mean([h['x'] for h in nt['heads']])))
    systems = sorted(m['systems'], key=lambda s: (s['page'], s['top']))
    moved, done = [], set()
    for b in m['bars']:
        n = b['num']
        if n in done: continue
        done.add(n)
        kn = {q: float(np.median(v)) for q, v in known.get(n, {}).items()}
        if 0 in kn: continue
        if b['page'] not in imgs: imgs[b['page']] = np.asarray(Image.open(pages[b['page']]).convert('L'))
        g = imgs[b['page']]
        s = next(s for s in systems if s['page'] == b['page'] and s['sys'] == b['sys'])
        nxt = [t for t in systems if t['page'] == s['page'] and t['top'] > s['top']]
        y0 = max(0, int((s['top'] - 20) * K))
        y1 = int(((nxt[0]['top'] - 20) if nxt else g.shape[0] / K) * K)
        guess = b['beat_x'][0] - b['xa']
        x_from = int((b['xa'] + guess / 2) * K)
        upto = min([x for x in kn.values()] + [b['xb']]) - 2
        x = first_head(g[y0:y1], x_from, int(upto * K))
        if x is None: continue
        x0 = x / K
        qs = sorted(kn)
        px = [0.0] + [float(q) for q in qs] + [float(len(b['beat_x']))]
        py = [x0] + [kn[q] for q in qs] + [b['xb']]
        new = [round(float(np.interp(j, px, py)), 2) for j in range(len(b['beat_x']))]
        # only earlier: a later head can be a later beat (beat 1 a rest, a held or hollow note, or a chord cluster
        # too tall to pass for a head), while the guess's fault is landing past the first chord
        if new[0] > b['beat_x'][0] - 2: continue
        moved.append((n, b['beat_x'], new))
    for n, old, new in moved: print(f'bar {n}: beat 1 {old[0]} -> {new[0]}  ({old} -> {new})')
    print(os.path.basename(a.folder.rstrip('/')) + ':', len(moved), 'bars moved')
    if moved:
        pic = a.picture or os.path.join(tmp, 'first beats.png')
        crops = []
        for n, old, new in moved:
            b = next(b for b in m['bars'] if b['num'] == n)
            s = next(s for s in systems if s['page'] == b['page'] and s['sys'] == b['sys'])
            nxt = [t for t in systems if t['page'] == s['page'] and t['top'] > s['top']]
            y1 = (nxt[0]['top'] - 20) if nxt else s['bottom'] + 120
            im = Image.open(pages[b['page']]).convert('RGB')
            c = im.crop((int((b['xa'] - 15) * K), int((s['top'] - 30) * K), int((b['xb'] + 15) * K), int(y1 * K)))
            d = ImageDraw.Draw(c)
            for xs, col in ((old, (255, 160, 0)), (new, (220, 0, 0))):
                for i, x in enumerate(xs):
                    X = (x - b['xa'] + 15) * K
                    d.line([(X, 0), (X, c.height)], fill=col, width=4 if i == 0 else 1)
            d.text((4, 4), f'bar {n}', fill=(0, 0, 255))
            crops.append(c.resize((c.width * 2 // 3, c.height * 2 // 3)))
        cols = 4
        rows = [crops[i:i + cols] for i in range(0, len(crops), cols)]
        W = max(sum(c.width + 10 for c in r) for r in rows)
        sheet = Image.new('RGB', (W, sum(max(c.height for c in r) + 10 for r in rows)), 'white')
        y = 0
        for r in rows:
            x = 0
            for c in r: sheet.paste(c, (x, y)); x += c.width + 10
            y += max(c.height for c in r) + 10
        sheet.save(pic); print('picture (orange the old beats, red the new; beat 1 thick):', pic)
    if a.write and moved:
        new = {n: nw for n, _, nw in moved if a.bars is None or n in a.bars}
        for b in m['bars']:
            if b['num'] in new: b['beat_x'] = new[b['num']]
        json.dump(m, open(mp, 'w'), indent=0)
        print('wrote', mp, 'bars', sorted(new))


if __name__ == '__main__':
    main()
