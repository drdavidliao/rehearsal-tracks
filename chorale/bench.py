"""Build a revoicing bench: a scrolling score with a clickable beat grid under it.

    python3 -m chorale.bench score.musicxml -o out/ --beats 8 --bars-per-system 4

The bench is how a span of music and a paragraph about it get joined up.  You
shift-click a run of beats, type what should happen there, and the page keeps the
pair.  Sibelius comments do not survive a MusicXML export — the format has no
element for a reviewer's note — so this is the way the spans come back out, as
the JSON `chorale.instructions` reads.

What the build does: lay the score out one system per Verovio page, render each
to its own SVG, then find where every beat sits horizontally so the grid lines up
with the notes rather than dividing each bar evenly.  Beats with no attack are
interpolated between the ones that have, anchored at the barlines, so a bar of
one whole note still gets a usable grid.
"""
import argparse
import json
import os
import re
from fractions import Fraction as F
from html import escape

from lxml import etree

NS = {'s': 'http://www.w3.org/2000/svg'}
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, 'templates')


# ---------------------------------------------------------------- the score
def inspect(path):
    """What the bench needs to know about a file: bars, metre, title."""
    root = etree.parse(path).getroot()
    bars = []
    for p in root.findall('part'):
        ns = [int(m.get('number')) for m in p.findall('measure')
              if (m.get('number') or '').isdigit()]
        if ns:
            bars.append((min(ns), max(ns)))
    if not bars:
        raise SystemExit(f'{path}: no numbered measures')
    first, last = min(b[0] for b in bars), max(b[1] for b in bars)
    t = root.find('.//time')
    beats = int(t.findtext('beats')) if t is not None else 4
    beat_type = int(t.findtext('beat-type')) if t is not None else 4
    bar_quarters = F(beats * 4, beat_type)
    title = None
    for c in root.findall('credit'):
        if c.findtext('credit-type') == 'title':
            title = (c.findtext('credit-words') or '').strip()
    title = title or (root.findtext('.//work-title') or '').strip()
    if title in ('', 'Untitled score'):
        title = os.path.splitext(os.path.basename(path))[0]
    sub = []
    for c in root.findall('credit'):
        if c.findtext('credit-type') == 'composer':
            sub += [w.text.strip() for w in c.findall('credit-words')
                    if w.text and w.text.strip()]
    parts = [p.findtext('part-name') or p.get('id') for p in root.findall('.//score-part')]
    return {'first': first, 'last': last, 'nbars': last - first + 1,
            'beats': beats, 'beat_type': beat_type, 'bar_quarters': bar_quarters,
            'title': title, 'credits': sub, 'parts': parts}


def lay_out(path, starts):
    """One system per Verovio page, so each system renders to its own SVG.

    MuseScore writes `<supports element="print" attribute="new-page" type="no"/>`,
    which tells the reader this file does not use page breaks — and Verovio
    believes it, silently ignoring every break inserted here and flowing the
    whole score onto one system.  The declaration goes.
    """
    xml = open(path, encoding='utf-8').read()
    xml = re.sub(r'\s*<supports[^>]*element="print"[^>]*/>', '', xml)

    def ap(mo):
        n = int(mo.group(1))
        return mo.group(0) + ('<print new-page="yes"/>' if n in starts and n != min(starts) else '')

    # MuseScore writes <measure number="1" width="253.75">; a pattern that
    # demands '>' right after the number matches nothing and inserts no breaks.
    return re.sub(r'<measure number="(\d+)"[^>]*>', ap, xml)


# ---------------------------------------------------------------- the grid
def _xs_in(el):
    out = []
    for n in el.iter():
        if n.get('x') is not None:
            try:
                out.append(float(n.get('x')))
            except ValueError:
                pass
        d = n.get('d')
        if d:
            out += [float(v) for v in re.findall(r'[ML]\s*(-?\d+(?:\.\d+)?)', d)]
    return out


def grid(src, starts, beats_per_bar, bar_quarters, staff_mm=7.0, page_width=2000):
    """-> [{w, h, svg, measures: [{n, edges}]}], one entry per system.

    `edges` are fractions of the system's width: beats_per_bar + 1 of them, the
    last being the barline, so cell b spans edges[b] to edges[b+1].
    """
    import verovio
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": page_width, "pageHeight": 4000, "adjustPageHeight": True,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "pageMarginTop": 40, "pageMarginBottom": 20,
        "unit": staff_mm / 4 * 10 / 2, "breaks": "encoded", "svgViewBox": True,
        "header": "none", "footer": "none", "lyricSize": 4.2,
        "svgAdditionalAttribute": ["measure@n"],
    })
    tk.loadData(lay_out(src, starts))
    npages = tk.getPageCount()

    tm = tk.renderToTimemap({"includeMeasures": True, "includeRests": True})
    attacks, meas_q0 = {}, {}
    for e in tm:
        if 'measureOn' in e:
            meas_q0.setdefault(e['measureOn'], e['qstamp'])
        ids = list(e.get('on', [])) + list(e.get('restsOn', []))
        if ids:
            attacks.setdefault(round(float(e['qstamp']), 6), []).extend(ids)

    step = F(bar_quarters, beats_per_bar)
    systems = []
    for pg in range(1, npages + 1):
        svg = tk.renderToSVG(pg)
        root = etree.fromstring(svg.encode())
        vb = [float(v) for v in root.get('viewBox').split()]
        tr = root.xpath('//s:g[@class="page-margin"]/@transform', namespaces=NS)
        dx = float(re.search(r'translate\(\s*(-?[\d.]+)', tr[0]).group(1)) if tr else 0.0

        def frac(x, vb=vb, dx=dx):
            return round((x * 0.1 + dx * 0.1) / vb[2], 6)

        idx = {}
        for el in root.iter():
            i = el.get('id')
            if i:
                xs = _xs_in(el)
                if xs:
                    idx[i] = (min(xs) + max(xs)) / 2

        meas = []
        for mel in root.xpath('//s:g[@class="measure"]', namespaces=NS):
            n = int(mel.get('data-n'))
            xs = _xs_in(mel)
            x0, x1 = min(xs), max(xs)
            q0 = meas_q0.get(mel.get('id'))
            beats = []
            for b in range(beats_per_bar):
                x = None
                if q0 is not None:
                    q = round(float(q0) + float(step) * b, 6)
                    for i in attacks.get(q, []):
                        if i in idx and x0 - 1 <= idx[i] <= x1 + 1:
                            x = idx[i] if x is None else min(x, idx[i])
                beats.append(x)
            known = [(i, v) for i, v in enumerate(beats) if v is not None]
            anchors = [(-1, x0)] + known + [(beats_per_bar, x1)]
            for i, v in enumerate(beats):
                if v is not None:
                    continue
                lo = max(a for a in anchors if a[0] < i)
                hi = min((a for a in anchors if a[0] > i), key=lambda a: a[0])
                beats[i] = lo[1] + (hi[1] - lo[1]) * (i - lo[0]) / (hi[0] - lo[0])
            meas.append({"n": n, "edges": [frac(e) for e in beats + [x1]]})
        meas.sort(key=lambda m: m['n'])
        systems.append({"w": vb[2], "h": vb[3], "svg": svg, "measures": meas})
    return systems


# ---------------------------------------------------------------- the page
def page(systems, beats_per_bar, score_line, doc_id, sub_line):
    meta = [{"w": s['w'], "h": s['h'],
             "measures": [{"n": m['n'], "edges": m['edges']} for m in s['measures']]}
            for s in systems]
    blocks = []
    for i, s in enumerate(systems):
        bars = ''.join(
            f'<div class="bar" style="left:{m["edges"][0] * 100:.4f}%;'
            f'width:{(m["edges"][-1] - m["edges"][0]) * 100:.4f}%">'
            f'<span class="barno">{m["n"]}</span></div>'
            for m in s['measures'])
        cells = ''
        for m in s['measures']:
            for b in range(beats_per_bar):
                lo, hi = m['edges'][b], m['edges'][b + 1]
                cells += (
                    f'<button type="button" class="beat" '
                    f'data-i="{(m["n"] - 1) * beats_per_bar + b}" '
                    f'data-bar="{m["n"]}" data-beat="{b + 1}" '
                    f'aria-label="bar {m["n"]} beat {b + 1}" '
                    f'style="left:{lo * 100:.4f}%;width:{(hi - lo) * 100:.4f}%">'
                    f'<span>{b + 1}</span></button>')
        blocks.append(
            f'<section class="system" data-sys="{i}">'
            f'<div class="engwrap" style="aspect-ratio:{s["w"]} / {s["h"]}">'
            f'<img class="eng" src="sys/{i:02d}.svg" alt="" '
            f'width="{s["w"]:.0f}" height="{s["h"]:.0f}" loading="lazy" decoding="async">'
            f'</div>'
            f'<div class="grid" aria-label="beat grid, system {i + 1}">{bars}{cells}</div>'
            f'</section>')
    head = open(os.path.join(TEMPLATES, 'head.html'), encoding='utf-8').read()
    tail = open(os.path.join(TEMPLATES, 'tail.html'), encoding='utf-8').read()
    return ((head + '\n'.join(blocks) + tail)
            .replace('__META__', json.dumps(meta, separators=(',', ':')))
            .replace('__BEATS__', str(beats_per_bar))
            .replace('__SCORELINE__', escape(sub_line))
            .replace('__DOC__', doc_id)
            .replace('__SCORE__', json.dumps(score_line)[1:-1]))


def build(src, outdir, beats_per_bar=None, bars_per_system=4, title=None,
          doc_id=None, staff_mm=7.0, page_width=2000, quiet=False):
    info = inspect(src)
    bpb = beats_per_bar or info['beats']
    starts = list(range(info['first'], info['last'] + 1, bars_per_system))
    systems = grid(src, starts, bpb, info['bar_quarters'], staff_mm, page_width)
    name = title or info['title']
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'score'
    doc_id = doc_id or f'bench/{slug}'
    sub = ' · '.join([name] + info['credits'][:1] + [', '.join(info['parts'])])
    score_line = ' — '.join([name] + info['credits']) or name
    os.makedirs(os.path.join(outdir, 'sys'), exist_ok=True)
    for i, s in enumerate(systems):
        with open(os.path.join(outdir, 'sys', f'{i:02d}.svg'), 'w', encoding='utf-8') as fh:
            fh.write(s['svg'])
    html = page(systems, bpb, score_line, doc_id, sub)
    out = os.path.join(outdir, 'bench.html')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(html)
    if not quiet:
        cells = sum(len(s['measures']) for s in systems) * bpb
        print(f'{name}: bars {info["first"]}–{info["last"]} '
              f'({info["beats"]}/{info["beat_type"]}), {len(systems)} systems, '
              f'{bpb} cells per bar, {cells} cells')
        print(f'  doc id {doc_id}')
        print(f'  {out} ({len(html)} bytes) + {len(systems)} SVGs')
    return {'html': out, 'systems': systems, 'info': info,
            'beats_per_bar': bpb, 'doc_id': doc_id}


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m chorale.bench',
                                 description='Build a revoicing bench for a MusicXML score.')
    ap.add_argument('src')
    ap.add_argument('-o', '--out', default='bench')
    ap.add_argument('--beats', type=int, default=None,
                    help='clickable cells per bar (default: the notated beats)')
    ap.add_argument('--bars-per-system', type=int, default=4)
    ap.add_argument('--title', default=None)
    ap.add_argument('--doc', default=None, help='artifact db document id')
    ap.add_argument('--staff-mm', type=float, default=7.0)
    ap.add_argument('--page-width', type=int, default=2000)
    a = ap.parse_args(argv)
    build(a.src, a.out, a.beats, a.bars_per_system, a.title, a.doc,
          a.staff_mm, a.page_width)


if __name__ == '__main__':
    main()
