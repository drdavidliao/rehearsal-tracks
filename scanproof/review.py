"""Pictures for a person: review sheets of the findings, a labelled zoom of one spot,
and a question image (scan above, the transcription's rendering below).

Review sheet: for each staff-bar with findings, the scan with what the reader saw
drawn on it (red = filled head, green = hollow, purple = whole, blue = x; the letter
name beside each; the beams it counted at each stem's end, as `b1`, `b2`), the
transcription underneath, then the findings.  Several staff-bars per sheet.

Zoom: one staff of one bar, enlarged, with every line and space labelled with its
note name in the margin and a faint guide across, ledger positions included.  This is
the check for an ambiguous finding: on a phone scan, the eye alone misplaces a head by
a step as easily as the detector does.
"""
import os
from collections import defaultdict

from PIL import Image, ImageDraw

from . import compare, expected, heads
from .bars import _font
from .geom import y_of_step, yline

COL = {'filled': (230, 0, 0), 'hollow': (0, 150, 0), 'whole': (150, 0, 150), 'x': (0, 60, 255)}


def _ev_text(evs):
    out = []
    for e in evs:
        val = '/'.join(expected.value_name(b, e['kind']) for b in sorted(e['beams']))
        val += '.' * max(e['dots'])
        out.append(f"{e['onset']}:" + ','.join(h['name'] for h in e['heads']) + f' {val}')
    return '  '.join(out)


def panel(prj, B, E, m, name, lines):
    b = B[m]
    hh, M, st = compare.read_bar(prj, b, name, E.get((name, m)))
    sp = st['space']
    im = prj.page(b['page']).image()
    ya = int(yline(st, 0, b['x0']) - 5 * sp)
    yb = int(yline(st, 4, b['x0']) + 5 * sp)
    ox = int(b['x0']) - 8
    crop = im.crop((ox, ya, int(b['x1']) + 8, yb))
    d = ImageDraw.Draw(crop)
    small = _font(17)
    for h in hh:
        x = h['x'] - ox
        y = heads.true_center(M, st, h) + M['Y0'] - ya
        d.ellipse((x - .62 * sp, y - .45 * sp, x + .62 * sp, y + .45 * sp), outline=COL[h['kind']], width=2)
        d.text((x + .7 * sp, y - 9), prj.step_name(h['step'], name), fill=COL[h['kind']], font=small)
    for c in compare.columns(hh, sp):
        if c[0]['kind'] not in ('filled', 'x'):
            continue
        n, s = heads.beam_count(M, st, c)
        if n is None:
            continue
        x, y = s['x'] + M['X0'] - ox, s['end'] + M['Y0'] - ya
        d.text((x + 4, y - 18 if s['dir'] < 0 else y + 2), f'b{n}', fill=(200, 100, 0), font=small)
    W = max(crop.width, 900)
    out = Image.new('RGB', (W, crop.height + 28 * (len(lines) + 1) + 10), 'white')
    out.paste(crop, (0, 0))
    d = ImageDraw.Draw(out)
    y = crop.height + 4
    d.text((4, y), f'bar {m} staff {name}   transcribed: {_ev_text(E.get((name, m), []))}',
           fill=(0, 0, 0), font=small)
    y += 28
    font = _font(22)
    for ln in lines:
        d.text((4, y), ln, fill=(150, 0, 0), font=font)
        y += 28
    return out


def sheets(prj, findings, outdir, only=None, height=2400):
    """Review sheets for every finding (or only those of the given types)."""
    os.makedirs(outdir, exist_ok=True)
    E = expected.events(prj)
    B = prj.bars()
    groups = defaultdict(list)
    for f in findings:
        if only and f['type'] not in only:
            continue
        txt = f"{f['type']}: " + ', '.join(f'{k}={v}' for k, v in f.items() if k not in ('bar', 'staff', 'type'))
        groups[(f['bar'], f['staff'])].append(txt)
    order = {n: i for i, n in enumerate(prj.names)}
    panels = [panel(prj, B, E, m, name, lines)
              for (m, name), lines in sorted(groups.items(), key=lambda kv: (kv[0][0], order[kv[0][1]]))]
    paths, sheet = [], []
    for pn in panels:
        sheet.append(pn)
        if sum(p.height for p in sheet) > height:
            paths.append(_save(sheet, os.path.join(outdir, f'review_{len(paths):02d}.png')))
            sheet = []
    if sheet:
        paths.append(_save(sheet, os.path.join(outdir, f'review_{len(paths):02d}.png')))
    return paths, len(panels)


def _save(ps, path):
    W = max(p.width for p in ps)
    s = Image.new('RGB', (W, sum(p.height for p in ps) + 10 * len(ps)), (200, 200, 200))
    y = 0
    for p in ps:
        s.paste(p, (0, y))
        y += p.height + 10
    s.save(path)
    return path


def scan_crop(prj, bar, name, x0=None, x1=None, pad=5, bar_end=None):
    """The scan around one staff, bars `bar`..`bar_end`, or page x0..x1 within it.
    -> (image, staff, (left, top) of the crop on the page)."""
    B = prj.bars()
    b = B[bar]
    e = B[bar_end or bar]
    if e['page'] != b['page'] or e['system'] != b['system']:
        e = b
    st = prj.staff(b, name)
    sp = st['space']
    xa = int(x0 if x0 is not None else b['x0'] - 8)
    xb = int(x1 if x1 is not None else e['x1'] + 8)
    ya = int(min(yline(st, 0, xa), yline(st, 0, xb)) - pad * sp)
    yb = int(max(yline(st, 4, xa), yline(st, 4, xb)) + pad * sp)
    return prj.page(b['page']).image().crop((xa, ya, xb, yb)), st, (xa, ya)


def zoom(prj, bar, name, path, x0=None, x1=None, scale=3, steps=(-7, 15)):
    """One staff of one bar (or page x0..x1 of it), enlarged, every staff position
    from steps[0] to steps[1] (0 = bottom line) named in a margin with a guide across."""
    crop, st, (xa, ya) = scan_crop(prj, bar, name, x0, x1, pad=(max(-steps[0], steps[1] - 8) + 2) / 2)
    big = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    margin = 70
    out = Image.new('RGB', (big.width + 2 * margin, big.height), 'white')
    out.paste(big, (margin, 0))
    d = ImageDraw.Draw(out, 'RGBA')
    font = _font(22)
    for s in range(steps[0], steps[1] + 1):
        ys = [(y_of_step(st, xa + px / scale, s) - ya) * scale for px in range(0, big.width + 30, 30)]
        if min(ys) < 0 or max(ys) >= out.height:
            continue
        line = s % 2 == 0
        col = (0, 90, 220, 120) if line else (220, 120, 0, 90)
        d.line([(margin + i * 30, yy) for i, yy in enumerate(ys)], fill=col, width=1)
        label = prj.step_name(s, name)
        tc = (0, 60, 180) if line else (180, 90, 0)
        d.text((4, ys[0] - 11), label, fill=tc, font=font)
        d.text((margin + big.width + 4, ys[-1] - 11), label, fill=tc, font=font)
    out.save(path)
    return path


def question(prj, bar, name, musicxml, path, bar_end=None, title=None):
    """A question for the user: the scan of bars `bar`..`bar_end` on staff `name` above,
    the same bars of `musicxml` rendered by Verovio below.  Ask about the transcription
    with this, not with note names in text: the user reads music, and a rendering shows
    a wrong note at a glance where 'B-flat 4 or C5?' does not."""
    import cairosvg
    import io
    import verovio
    crop, _, _ = scan_crop(prj, bar, name, bar_end=bar_end)
    tk = verovio.toolkit()
    tk.setOptions({'pageWidth': 2100, 'adjustPageHeight': True, 'scale': 45, 'header': 'none',
                   'footer': 'none', 'breaks': 'none'})
    tk.loadFile(prj.rel(musicxml) if not os.path.isabs(musicxml) else musicxml)
    tk.select({'measureRange': f'{bar}-{bar_end or bar}'})
    tk.redoLayout()
    png = cairosvg.svg2png(bytestring=tk.renderToSVG(1).encode(), background_color='white')
    render = Image.open(io.BytesIO(png)).convert('RGB')
    font = _font(28)
    W = max(crop.width, render.width)
    head = 44
    out = Image.new('RGB', (W, head * 2 + crop.height + render.height + 20), 'white')
    d = ImageDraw.Draw(out)
    d.text((8, 8), title or f'Scan: bar{"s" if bar_end else ""} {bar}{f"-{bar_end}" if bar_end else ""}',
           fill=(0, 0, 0), font=font)
    out.paste(crop, (0, head))
    y = head + crop.height + 10
    d.text((8, y + 8), 'Transcription (MusicXML)', fill=(0, 0, 0), font=font)
    out.paste(render, (0, y + head))
    out.save(path)
    return path
