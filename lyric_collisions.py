#!/usr/bin/env python3
"""Flag lyric syllables that would collide horizontally in a Verovio layout.

    python3 lyric_collisions.py laid_out.musicxml [staff_mm]

The input must already carry its <print new-system>/<print new-page> breaks.
Renders it, pulls every syllable's x, baseline and font size out of the SVG,
groups by baseline and reports every consecutive pair whose gap is smaller than
an estimate of the first syllable's printed width.

This is how you choose bars-per-system across a whole score without rendering
and squinting at every page. Verovio's own "justification is highly compressed"
warning is about NOTE spacing and will not fire on a system whose words overlap.

The width estimate is approximate. A gap a little under the estimate is tight
but legible; a gap well under it overlaps. Use it to compare candidate layouts.
Needs verovio and lxml.
"""
import sys
import verovio
from lxml import etree

NS = {'s': 'http://www.w3.org/2000/svg'}
NARROW = set("ijltfr.,'’ ")

def width(t, fs):
    return sum(fs * (0.30 if c in NARROW else 0.56) for c in t)

def check(path, staff_mm=7.0, page=(2159, 2794), marg=(140, 110, 130, 120)):
    """page and margins in 1/10 mm: (w, h) and (left, right, top, bottom)."""
    tk = verovio.toolkit()
    tk.setOptions({"pageWidth": page[0], "pageHeight": page[1],
                   "pageMarginLeft": marg[0], "pageMarginRight": marg[1],
                   "pageMarginTop": marg[2], "pageMarginBottom": marg[3],
                   "unit": staff_mm / 4 * 10 / 2, "adjustPageHeight": False,
                   "breaks": "encoded", "svgViewBox": True})
    tk.loadFile(path)
    bad = []
    for pg in range(1, tk.getPageCount() + 1):
        root = etree.fromstring(tk.renderToSVG(pg).encode())
        rows = {}
        for g in root.xpath('//s:g[@class="syl"]', namespaces=NS):
            ts = g.xpath('.//s:text', namespaces=NS)
            inner = g.xpath('.//s:tspan[@font-size]', namespaces=NS)
            if not ts or not inner: continue
            txt = ''.join(ts[0].itertext()).strip()
            if not txt: continue
            fs = float(inner[-1].get('font-size').rstrip('px'))
            try:
                x, y = float(ts[0].get('x')), float(ts[0].get('y'))
            except (TypeError, ValueError):
                continue
            # SVG inner units are 10x the viewBox; /20 buckets one lyric baseline
            rows.setdefault(round(y / 20), []).append((x, txt, fs))
        for row in rows.values():
            row.sort()
            for (x1, t1, fs), (x2, t2, _) in zip(row, row[1:]):
                need = width(t1, fs)
                if x2 - x1 < need:
                    bad.append((pg, t1, t2, round(x2 - x1), round(need)))
    return tk.getPageCount(), bad

if __name__ == '__main__':
    mm = float(sys.argv[2]) if len(sys.argv) > 2 else 7.0
    n, bad = check(sys.argv[1], mm)
    print(f'{n} pages, {len(bad)} overlapping syllable pair(s)')
    for pg, a, b, gap, need in bad:
        print(f'   p{pg}: {a!r} -> {b!r}   gap {gap} < {need}')
    if not bad:
        print('   none — this layout is printable')
