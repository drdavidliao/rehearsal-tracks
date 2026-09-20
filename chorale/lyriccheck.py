"""Find lyric syllables that would print on top of each other.

Verovio warns when a *system* is horizontally compressed, which is a different
question and misses the case that matters: a system that fits, in which two words
under adjacent notes still overlap.  This measures the rendered SVG instead.

Syllables are grouped by baseline, so voice 1's line and voice 2's line are
checked separately, and each word's width is estimated from its characters —
narrow glyphs at 0.30 em, everything else at 0.56 em.  The estimate is rough on
purpose: a near miss is worth looking at too.
"""
from lxml import etree

NS = {'s': 'http://www.w3.org/2000/svg'}
NARROW = set("ijltfr.,'’ ")


def width(t, fs):
    return sum(fs * (0.30 if c in NARROW else 0.56) for c in t)


def collisions(tk):
    """-> (page count, [(page, left word, right word, gap, needed), ...])"""
    n = tk.getPageCount()
    bad = []
    for pg in range(1, n + 1):
        root = etree.fromstring(tk.renderToSVG(pg).encode())
        items = []
        for g in root.xpath('//s:g[@class="syl"]', namespaces=NS):
            ts = g.xpath('.//s:text', namespaces=NS)
            if not ts:
                continue
            t = ts[0]
            txt = ''.join(t.itertext()).strip()
            inner = g.xpath('.//s:tspan[@font-size]', namespaces=NS)
            fs = float(inner[-1].get('font-size').rstrip('px')) if inner else 0
            try:
                xx, yy = float(t.get('x')), float(t.get('y'))
            except (TypeError, ValueError):
                continue
            if txt:
                items.append((round(yy / 20), xx, txt, fs))
        byline = {}
        for yy, xx, txt, fs in items:
            byline.setdefault(yy, []).append((xx, txt, fs))
        for lst in byline.values():
            lst.sort()
            for (x1, t1, fs), (x2, t2, _) in zip(lst, lst[1:]):
                need = width(t1, fs)
                if x2 - x1 < need:
                    bad.append((pg, t1, t2, round(x2 - x1), round(need)))
    return n, bad


def check(plan, src):
    """Lay `src` out with `plan` (a printing.Print) and report the collisions."""
    return collisions(plan.toolkit(plan.lay_out(src)))
