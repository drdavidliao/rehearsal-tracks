"""The bar table: for each printed bar, its page, its system, and the x of the barlines
either side of it.

It is drafted from the detected barlines and then checked by eye, because barline
detection on a phone scan is not reliable enough to proofread against: on the first
piece it missed five barlines (pale ones, and system ends at a curled edge) and
invented one (a column of stems).  A wrong bar table makes every finding after it
wrong, so it is the one step that is checked by a person, on overlays.

    {"first_bar": 1,
     "systems": [
       {"page": 1, "system": 0, "barlines": [404, 1062, 1634, 2027], "first_bar": 1},
       {"page": 1, "system": 1, "barlines": [148, 890, 1464, 2026]},
       ...]}

A system's bars run between consecutive barlines.  `first_bar` on a system is optional
and, when given, checked against the running count (copy the printed bar numbers at
system starts in from the scan: they catch a missed barline at once).  A system may
also carry `start_space` to override the config's (a key change at a system start).
"""
import json
import os

import numpy as np
from PIL import ImageDraw, ImageFont

from .geom import yline


def _font(size):
    for f in ('/System/Library/Fonts/Helvetica.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def draft(prj, first_bar=None):
    """Bar table from the detected barlines -> (table, notes).  A system with no
    barline near either end of its staves gets one there, listed in `notes` (the
    final barline at a curled edge is the usual miss)."""
    geo = prj.geometry()
    nb = prj.cfg.get('first_bar', 1) if first_bar is None else first_bar
    systems, notes = [], []
    for p in sorted(geo):
        g = geo[p]
        for si, sy in enumerate(g['systems']):
            sts = [g['staves'][i] for i in sy['staves']]
            sp = np.mean([s['space'] for s in sts])
            xs = [round(x) for x, _ in sy['barlines']]
            added = []
            left, right = min(s['x0'] for s in sts), max(s['x1'] for s in sts)
            if not xs or xs[0] > left + 3 * sp:
                xs.insert(0, round(left))
                added.append(round(left))
                notes.append(f'page {p} system {si}: no barline at the left end; staff start {round(left)} used')
            if xs[-1] < right - 3 * sp:
                xs.append(round(right))
                added.append(round(right))
                notes.append(f'page {p} system {si}: no barline at the right end; staff end {round(right)} used')
            row = {'page': p, 'system': si, 'barlines': xs, 'first_bar': nb}
            if added:
                row['added'] = added            # drawn orange on the overlay
            systems.append(row)
            nb += len(xs) - 1
    return {'first_bar': systems[0]['first_bar'] if systems else 1, 'systems': systems}, notes


def save(table, path):
    """One system per line, so the table is easy to correct by hand."""
    lines = [json.dumps(s) for s in table['systems']]
    with open(path, 'w') as fh:
        fh.write('{"first_bar": %d,\n "systems": [\n  ' % table['first_bar']
                 + ',\n  '.join(lines) + '\n]}\n')


def read(prj):
    path = prj.rel(prj.cfg.get('bars', 'bars.json'))
    if not os.path.exists(path):
        raise SystemExit(f'no bar table at {path}: run `python3 -m scanproof bars '
                         f'{prj.path}` to draft one, check its overlays, then copy it there')
    with open(path) as fh:
        return json.load(fh)


def load(prj, table=None):
    """{bar: {...}} from the bar table, checked against the geometry."""
    table = table or read(prj)
    geo = prj.geometry()
    out, nb = {}, table.get('first_bar', 1)
    seen = set()
    for s in table['systems']:
        p, si = s['page'], s['system']
        if (p, si) in seen:
            raise ValueError(f'bar table: page {p} system {si} listed twice')
        seen.add((p, si))
        try:
            sy = geo[p]['systems'][si]
        except (KeyError, IndexError):
            raise ValueError(f'bar table: page {p} has no system {si}') from None
        xs = s['barlines']
        if any(b <= a for a, b in zip(xs, xs[1:])) or len(xs) < 2:
            raise ValueError(f'bar table: page {p} system {si}: barlines must increase, two or more')
        if 'first_bar' in s and s['first_bar'] != nb:
            raise ValueError(f'bar table: page {p} system {si} says it starts at bar '
                             f'{s["first_bar"]}, but the barlines before it make it bar {nb}')
        for k in range(len(xs) - 1):
            first = k == 0
            sp = s.get('start_space', prj.cfg.get('start_space', 7.0))
            if nb == table.get('first_bar', 1):
                sp = s.get('start_space', prj.cfg.get('first_start_space', sp + 4))
            out[nb] = {'page': p, 'system': si, 'staves': sy['staves'], 'x0': xs[k],
                       'x1': xs[k + 1], 'first_in_system': first,
                       'start_space': sp if first else None}
            nb += 1
    return out


def overlay(prj, table, path_fmt):
    """Every page with its fitted staff lines (red), the bar table's barlines (blue;
    orange where the draft added one the detector did not see) and bar numbers.
    Returns the paths written."""
    geo = prj.geometry()
    bars_ = load(prj, table)
    by_sys = {}
    for b, info in bars_.items():
        by_sys.setdefault((info['page'], info['system']), []).append((b, info))
    font = _font(40)
    small = _font(26)
    paths = []
    for p in sorted(geo):
        g = geo[p]
        im = prj.page(p).image()
        d = ImageDraw.Draw(im)
        for st in g['staves']:
            for li in range(5):
                xs, ys = st['samples'][li]
                d.line(list(zip(xs, ys)), fill=(255, 0, 0), width=2)
        for si, sy in enumerate(g['systems']):
            a, b = g['staves'][sy['staves'][0]], g['staves'][sy['staves'][-1]]
            d.text((8, yline(a, 0, 60) - 60), f'system {si}', fill=(200, 0, 0), font=small)
            row = [s for s in table['systems'] if s['page'] == p and s['system'] == si]
            for x in (row[0]['barlines'] if row else []):
                col = (255, 140, 0) if x in row[0].get('added', ()) else (0, 0, 255)
                d.line((x, yline(a, 0, x) - 30, x, yline(b, 4, x) + 30), fill=col, width=5)
                d.text((x - 20, yline(b, 4, x) + 34), str(x), fill=col, font=small)
            for bn, info in by_sys.get((p, si), []):
                xm = (info['x0'] + info['x1']) / 2
                d.text((xm - 20, yline(a, 0, xm) - 90), str(bn), fill=(0, 0, 255), font=font)
        im = im.resize((im.width * 2 // 5, im.height * 2 // 5))
        path = path_fmt.format(page=p)
        im.save(path)
        paths.append(path)
    return paths
