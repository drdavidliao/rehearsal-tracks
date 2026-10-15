"""Find noteheads on a scanned staff and say what they are, from pixels alone.

For one staff and an x range:
  1. remove the staff lines (only where the ink is no taller than a line, so a notehead
     sitting on a line keeps its pixels) and stems (thin vertical runs taller than 1.6 SP);
  2. fill enclosed holes, so a hollow (half/whole) head becomes solid, and remember which
     heads were hollow;
  3. explain the solid ink with ellipse-shaped heads, one at a time: at every x and every
     staff step score the fraction of *still unexplained* ink inside a head-sized ellipse,
     take the best, mark its pixels explained, repeat while the best covers enough.
     Two heads a third apart touch, and the ellipse between them is full of ink; scoring
     only unexplained ink is what stops that midpoint from being read as a third head
     (on the first piece this was run on, a phantom head inside two tied chords that a
     hand check had passed);
  4. hollow and x heads are then matched by shape on the ink the filled heads left;
  5. a head is kept only with a stem at least 2.5 SP long and, if filled, at least
     0.6 SP thick (a beam's corner is thinner); beyond the staff its step is re-derived
     from its ledger lines;
  6. for each chord, the beams or flags at its stem's far end are counted (beam_count),
     which is what tells an eighth from a quarter.

Each head is reported as (x, staff step, kind) with step 0 = bottom line.  Pixel
constants are for a staff space of about 19 px and are scaled by M['k'].
"""
import numpy as np
from scipy import ndimage

from .geom import yline


def masks(img_dark, st, x0, x1, pad_steps=9, k=1.0):
    sp = st['space']
    xs = np.arange(int(x0), int(x1))
    ytop = min(yline(st, 0, x) for x in (x0, x1)) - pad_steps * sp / 2
    ybot = max(yline(st, 4, x) for x in (x0, x1)) + pad_steps * sp / 2
    Y0, Y1 = int(ytop), int(ybot)
    sub = img_dark[Y0:Y1, int(x0):int(x1)].copy()
    H, W = sub.shape
    # staff and ledger lines: a thin horizontal run within 3 px of where the line should be;
    # a run taller than a line (a notehead on the line) is left alone
    lw = int(round(5 * k))
    near = max(2, int(round(3 * k)))
    noline = sub.copy()
    for xi in range(W):
        x = xi + int(x0)
        col = sub[:, xi]
        for li in range(-3, 8):            # ledger lines above and below too
            if 0 <= li <= 4:
                y = yline(st, li, x)
            elif li < 0:
                y = yline(st, 0, x) + li * sp
            else:
                y = yline(st, 4, x) + (li - 4) * sp
            yi = int(round(y)) - Y0
            if yi < 5 or yi > H - 6:
                continue
            hits = [yy for yy in range(yi - near, yi + near + 1) if 0 <= yy < H and col[yy]]
            if not hits:
                continue
            a = b = min(hits, key=lambda yy: abs(yy - yi))
            while a - 1 >= 0 and col[a - 1]:
                a -= 1
            while b + 1 < H and col[b + 1]:
                b += 1
            if b - a + 1 <= lw:
                noline[a:b + 1, xi] = False
    # stems: thin vertical runs taller than 1.6 SP
    tall = ndimage.binary_opening(noline, structure=np.ones((int(1.6 * sp), 1)))
    thick = ndimage.binary_opening(noline, structure=np.ones((1, max(3, int(round(6 * k))))))
    stems = tall & ~ndimage.binary_dilation(thick, structure=np.ones((1, 3)))
    nostem = noline & ~ndimage.binary_dilation(stems, structure=np.ones((1, 3)))
    filled = ndimage.binary_fill_holes(ndimage.binary_closing(nostem, structure=np.ones((3, 3))))
    hollow = filled & ~nostem
    return {'Y0': Y0, 'X0': int(x0), 'raw': sub, 'noline': noline, 'nostem': nostem,
            'filled': filled, 'hollow': hollow, 'k': k}


def ellipse(sp):
    rx, ry = 0.52 * sp, 0.36 * sp
    X, Y = np.meshgrid(np.arange(-int(rx) - 1, int(rx) + 2), np.arange(-int(ry) - 1, int(ry) + 2))
    return ((X / rx) ** 2 + (Y / ry) ** 2) <= 1.0


def solid_heads(M, st, min_cover=0.72):
    sp = st['space']
    E = ellipse(sp)
    eh, ew = E.shape
    ink = ndimage.binary_closing(M['nostem'], structure=np.ones((3, 3)))
    H, W = ink.shape
    explained = np.zeros_like(ink)
    heads = []
    cand_steps = np.arange(-8, 17)
    for _ in range(40):
        best = None
        avail = ink & ~explained
        if avail.sum() < E.sum() * min_cover:
            break
        # only consider x where some unexplained ink exists
        colsum = avail.sum(0)
        xs = [xi for xi in range(ew // 2, W - ew // 2, 2) if colsum[max(0, xi - 3):xi + 4].sum() > 0]
        for xi in xs:
            x = xi + M['X0']
            ybot = yline(st, 4, x)
            for s in cand_steps:
                yc = int(round(ybot - s * sp / 2)) - M['Y0']
                if yc - eh // 2 < 0 or yc + eh // 2 + 1 > H:
                    continue
                win = avail[yc - eh // 2: yc - eh // 2 + eh, xi - ew // 2: xi - ew // 2 + ew]
                tot = ink[yc - eh // 2: yc - eh // 2 + eh, xi - ew // 2: xi - ew // 2 + ew]
                c = (win & E).sum() / E.sum()
                if c >= min_cover and (tot & E).sum() / E.sum() >= .85:
                    # prefer the centre: ink balanced above and below
                    up = (win[:eh // 2] & E[:eh // 2]).sum()
                    dn = (win[eh - eh // 2:] & E[eh - eh // 2:]).sum()
                    bal = 1 - abs(up - dn) / max(up + dn, 1)
                    score = c + 0.15 * bal
                    if best is None or score > best[0]:
                        best = (score, xi, s, yc, c)
        if best is None:
            break
        _, xi, s, yc, c = best
        sl = (slice(yc - eh // 2, yc - eh // 2 + eh), slice(xi - ew // 2, xi - ew // 2 + ew))
        explained[sl] |= E
        hol = (M['hollow'][sl] & E).sum() / E.sum()
        heads.append({'x': xi + M['X0'], 'step': int(s), 'kind': 'hollow' if hol > .2 else 'filled',
                      'cover': round(float(c), 2)})
    return heads


def _shapes(sp):
    rx, ry = 0.62 * sp, 0.44 * sp
    X, Y = np.meshgrid(np.arange(-int(rx) - 2, int(rx) + 3), np.arange(-int(ry) - 2, int(ry) + 3))
    r = np.sqrt((X / rx) ** 2 + (Y / ry) ** 2)
    ring = (r > .62) & (r <= 1.08)
    inner = r <= .42
    # X: two diagonals of a box about a head in size
    hx, hy = 0.5 * sp, 0.5 * sp
    dd = np.minimum(np.abs(X / hx - Y / hy), np.abs(X / hx + Y / hy))
    box = (np.abs(X) <= hx) & (np.abs(Y) <= hy)
    xdiag = box & (dd < 0.28)
    xgap = box & (dd > 0.75) & (np.maximum(np.abs(X / hx), np.abs(Y / hy)) < .9)
    return ring, inner, xdiag, xgap


def shaped_heads(M, st, kind, taken=()):
    """Hollow ('ring') or crossed ('x') heads by matching pursuit on the line-free ink."""
    sp = st['space']
    ring, inner, xdiag, xgap = _shapes(sp)
    on, off = (ring, inner) if kind == 'hollow' else (xdiag, xgap)
    eh, ew = on.shape
    ink = M['noline']
    H, W = ink.shape
    found = []
    blocked = np.zeros_like(ink)
    for h in taken:
        xi = int(round(h['x'])) - M['X0']
        yc = int(round(yline(st, 4, h['x']) - h['step'] * sp / 2)) - M['Y0']
        blocked[max(0, yc - eh // 2):yc + eh // 2 + 1, max(0, xi - ew // 2):xi + ew // 2 + 1] = True
    cands = []
    for xi in range(ew // 2, W - ew // 2, 2):
        x = xi + M['X0']
        ybot = yline(st, 4, x)
        for s in range(-8, 17):
            yc = int(round(ybot - s * sp / 2)) - M['Y0']
            if yc - eh // 2 < 0 or yc - eh // 2 + eh > H:
                continue
            win = ink[yc - eh // 2: yc - eh // 2 + eh, xi - ew // 2: xi - ew // 2 + ew]
            if blocked[yc, xi]:
                continue
            a = (win & on).sum() / on.sum()
            # a staff line may run through the middle of a hollow head: ignore its rows
            offm = off.copy()
            b = 1 - (win & offm).sum() / max(offm.sum(), 1)
            sc = a * b
            thr = (.55, .7) if kind == 'hollow' else (.62, .6)
            if a >= thr[0] and b >= thr[1]:
                cands.append((sc, xi, s))
    cands.sort(reverse=True)
    for sc, xi, s in cands:
        if any(abs(xi + M['X0'] - f['x']) < .9 * sp and abs(s - f['step']) < 2 for f in found):
            continue
        found.append({'x': xi + M['X0'], 'step': int(s), 'kind': kind, 'cover': round(float(sc), 2)})
    return found


def true_center(M, st, head):
    """Pixel centre (y) of a head's ink, not the staff-step grid row it was found at."""
    sp = st['space']
    hx = int(round(head['x'])) - M['X0']
    gy = int(round(yline(st, 4, head['x']) - head['step'] * sp / 2)) - M['Y0']
    win = M['nostem'][max(0, gy - int(.75 * sp)):gy + int(.75 * sp) + 1, max(0, hx - int(.45 * sp)):hx + int(.45 * sp) + 1]
    if win.sum() == 0:
        return gy
    rows = win.sum(1)
    return max(0, gy - int(.75 * sp)) + float((np.arange(len(rows)) * rows).sum() / rows.sum())


def stem(M, st, head):
    """The stem leaving this head: {'reach': SP from the head centre to the stem's far
    end, 'x': its column, 'dir': -1 up / +1 down, 'end': y of the far end (M coords)},
    the longest found up or down from either edge of the head.  Stems print pale on some
    scans, so the light mask is used when read_staff was given one."""
    sp = st['space']
    raw = M.get('light', M['raw'])
    gap_max = max(2, int(round(2 * M['k'])))
    hx = int(round(head['x'])) - M['X0']
    hy = int(round(true_center(M, st, head)))
    best = {'reach': 0.0, 'x': None, 'dir': 0, 'end': hy}
    for cx in list(range(hx - int(.75 * sp), hx - int(.3 * sp))) + list(range(hx + int(.3 * sp), hx + int(.75 * sp))):
        if cx < 0 or cx >= raw.shape[1]:
            continue
        col = raw[:, max(0, cx - 1):cx + 2].any(1)
        # start from ink anywhere in the head's own height (an x-head's stem leaves
        # from a corner, not from the middle row)
        starts = [y for y in range(hy - int(.5 * sp), hy + int(.5 * sp) + 1) if 0 <= y < len(col) and col[y]]
        if not starts:
            continue
        for d in (-1, 1):
            y = min(starts) if d < 0 else max(starts)
            gaps, last = 0, y
            while 0 <= y < len(col):
                if col[y]:
                    gaps, last = 0, y
                else:
                    gaps += 1
                    if gaps > gap_max:
                        break
                y += d
            r = abs(y - hy) / sp
            if r > best['reach']:
                best = {'reach': r, 'x': cx, 'dir': d, 'end': last}
    return best


def stem_reach(M, st, head):
    """How far (in SP) a stem runs from this head's centre, up or down, whichever is longer."""
    return stem(M, st, head)['reach']


def follow_stem(img, x, y, d, k=1.0):
    """Continue a stem past where stem() lost it: a phone scan leans, and a stem that
    drifts a pixel or two sideways leaves a fixed three-pixel column short of its beam.
    Walks on from (x, y) in direction d, re-centring on the ink within 2 px each row.
    -> (end y, x at the end)."""
    H, W = img.shape
    gap_max = max(2, int(round(2 * k)))
    gaps, last, yy, xx = 0, (y, x), y, float(x)
    while 0 <= yy < H:
        xi = int(round(xx))
        lo, hi = max(0, xi - 2), min(W, xi + 3)
        hit = np.where(img[yy, lo:hi])[0]
        if len(hit):
            gaps = 0
            xx = .7 * xx + .3 * (lo + hit.mean())
            last = (yy, int(round(xx)))
        else:
            gaps += 1
            if gaps > gap_max:
                break
        yy += d
    return last


def stem_centre(img, x, y, d, sp):
    """Middle column of the stem near (x, y), measured over the 1 SP of stem from y in
    direction d (towards the heads): stem() reports the edge of its search window,
    which can sit a pixel or two beside the stem."""
    H, W = img.shape
    xs = []
    for yy in range(y, y + d * int(sp), d):
        if not 0 <= yy < H:
            break
        lo = max(0, x - 4)
        row = img[yy, lo:min(W, x + 5)]
        hit = np.where(row)[0]
        if 0 < len(hit) <= 5:              # a stem, not a beam crossing it
            xs.append(lo + hit.mean())
    return int(round(np.median(xs))) if xs else x


def beam_count(M, st, col):
    """Beams or flags on the stem of one column of heads (a chord): 0 for a quarter or
    longer, 1 for an eighth, 2 for a sixteenth.

    The stem is the longest one leaving any head of the column, followed to its far end
    (follow_stem).  Beside it, 0.35-0.7 SP
    to the left and to the right, the line-free ink is walked from the stem's far end
    back towards the heads (at most 2.6 SP, and stopping 0.9 SP short of the chord's
    nearest head); each run of ink at least 0.28 SP tall and joined to the stem is a beam or a
    flag.  Two beams that the
    scan has blurred into one run count by length (a beam and its gap are 0.75 SP).  A
    beam can leave a stem on one side only (the last note of a group) and a sixteenth's
    second beam may be a hook on one side, so the larger side is the answer.
    Returns (count, stem) or (None, stem) when no stem was found."""
    sp = st['space']
    best = max((stem(M, st, h) for h in col), key=lambda s: s['reach'])
    if best['x'] is None or best['reach'] < 2.0:
        return None, best
    ink = M['noline']
    H, W = ink.shape
    img = M.get('light', M['raw'])
    d, end, cx = best['dir'], *follow_stem(img, best['x'], best['end'], best['dir'], M['k'])
    cx = stem_centre(img, cx, end, -d, sp)
    # stop 0.9 SP short of the head nearest the stem's end: in a chord the stem runs
    # past the other heads, and a cluster's heads beside it would count as beams
    ys_h = [true_center(M, st, h) for h in col]
    near_y = min(ys_h) if d < 0 else max(ys_h)
    span = min(2.6 * sp, abs(near_y - end) - .9 * sp)
    if span < .3 * sp:
        return None, best
    lo, hi = (end, end + span) if d < 0 else (end - span, end)
    ys = np.arange(max(0, int(lo)), min(H, int(hi) + 1))
    min_run = .28 * sp

    # a beam or flag is joined to the stem: its ink connects to the stem's within the
    # window (a marcato wedge, a rest or a letter near the stem end does not)
    xa, xb = max(0, cx - int(.9 * sp)), min(W, cx + int(.9 * sp) + 1)
    lab, _ = ndimage.label(ink[ys[0]:ys[-1] + 1, xa:xb], structure=np.ones((3, 3)))
    stem_labels = set(np.unique(lab[:, max(0, cx - 1 - xa):cx + 2 - xa])) - {0}

    def attached(rows, x):
        return bool(stem_labels & set(lab[rows - ys[0], x - xa]))

    sides = []
    for sign in (-1, 1):
        counts = []
        for off in (.35, .5, .7):
            x = cx + sign * int(round(off * sp))
            if not 0 <= x < W:
                continue
            colv = ink[ys, x]
            n, run, gap = 0, 0, 0
            for i, v in enumerate(list(colv) + [False, False]):
                if v:
                    run += 1 + (gap if run else 0)
                    gap = 0
                elif run:
                    gap += 1
                    if gap > 1:
                        if run >= min_run and attached(ys[i - gap - run + 1:i - gap + 1], x):
                            n += max(1, int(round((run / sp + .25) / .75)))
                        run, gap = 0, 0
            counts.append(n)
        if counts:
            sides.append(int(np.median(counts)))
    return (max(sides) if sides else None), best


def thickness(M, st, head):
    """Median vertical thickness (SP) of the ink through the middle of a head: a notehead
    is about 0.8 SP tall, a beam about 0.45."""
    sp = st['space']
    hx = int(round(head['x'])) - M['X0']
    hy = int(round(true_center(M, st, head)))
    ink = M['nostem']
    ts = []
    for c in range(hx - int(.25 * sp), hx + int(.25 * sp) + 1):
        if c < 0 or c >= ink.shape[1] or not ink[min(max(hy, 0), ink.shape[0] - 1), c]:
            ts.append(0)
            continue
        a = b = hy
        while a > 0 and ink[a - 1, c]:
            a -= 1
        while b < ink.shape[0] - 1 and ink[b + 1, c]:
            b += 1
        ts.append(b - a + 1)
    return float(np.median(ts)) / sp


def ledger_step(M, st, head):
    """Re-derive the step of a head beyond the staff by counting its ledger lines.

    Near a curled page edge the paper bends and the space between ledger lines shrinks
    (16 px instead of 21 at the bottom of one phone-scanned page), so distance from the staff in staff
    spaces undercounts; the ledger lines themselves do not lie.  Returns the corrected
    step, or None when a head two or more steps out has no ledger line at all (text, a
    dynamic, a tuplet number)."""
    sp = st['space']
    s = head['step']
    if -1 <= s <= 9:
        return s
    raw = M['raw']
    hx = int(round(head['x'])) - M['X0']
    hy = true_center(M, st, head)
    below = s < 0
    edge = (yline(st, 4, head['x']) if below else yline(st, 0, head['x'])) - M['Y0']
    # thin horizontal runs (ledger lines) in a window 0.85 SP either side of the head:
    # per row, the share of columns whose ink there is part of a run no taller than a line
    xa, xb = max(0, hx - int(.85 * sp)), min(raw.shape[1], hx + int(.85 * sp))
    win = raw[:, xa:xb]
    Hh = win.shape[0]
    thin = np.zeros(win.shape, bool)
    for c in range(win.shape[1]):
        col = win[:, c]
        y = 0
        while y < Hh:
            if col[y]:
                e = y
                while e + 1 < Hh and col[e + 1]:
                    e += 1
                if e - y + 1 <= 6 * M['k']:
                    thin[y:e + 1, c] = True
                y = e + 1
            else:
                y += 1
    prof = thin.mean(1)
    # use the staff's own spacing unless the ledger lines say the paper is squeezed here
    e5 = int(round(5 * M['k']))
    lo, hi = (int(edge) + e5, int(hy + .3 * sp)) if below else (int(hy - .3 * sp), int(edge) - e5)
    rows = [y for y in range(max(lo, 1), min(hi, Hh - 2) + 1) if prof[y] >= .3 and prof[y] >= prof[y - 1] and prof[y] >= prof[y + 1]]
    g = []
    for y in rows:
        if g and y - g[-1][-1] <= 3 * M['k']:
            g[-1].append(y)
        else:
            g.append([y])
    pos = sorted([edge] + [float(np.mean(q)) for q in g], reverse=not below)
    gap = sp
    if len(pos) >= 3:
        d = np.abs(np.diff(pos))
        if d.min() > .5 * sp:
            gap = float(np.median(d))
    n = abs(hy - edge) / (gap / 2)
    if n < 1.5 and not g:
        return -1 if below else 9
    return -int(round(n)) if below else 8 + int(round(n))


def read_staff(img_dark, st, x0, x1, img_light=None, xheads=True, whole=False, k=1.0):
    """Every notehead on staff `st` between x0 and x1 -> (heads, masks).

    xheads: also look for x-noteheads (only worth it on staves that have them: an
    accidental's strokes can pass for one).  whole: keep hollow heads with no stem,
    as whole notes (kind 'whole'); otherwise a head needs a stem, which is what rejects
    an eighth rest's knob, an accidental's crossing strokes, and letters."""
    M = masks(img_dark, st, x0, x1, k=k)
    if img_light is not None:      # stems print pale on some scans
        M['light'] = img_light[M['Y0']:M['Y0'] + M['raw'].shape[0], M['X0']:M['X0'] + M['raw'].shape[1]]
    out = []
    hs = solid_heads(M, st)
    ho = shaped_heads(M, st, 'hollow', hs)
    xs = shaped_heads(M, st, 'x', hs + ho) if xheads else []
    for h in hs + ho + xs:
        if stem_reach(M, st, h) < 2.5:
            if not (whole and h['kind'] == 'hollow'):
                continue
            h['kind'] = 'whole'
        if h['kind'] == 'filled' and thickness(M, st, h) < .6:
            continue                    # the corner where a stem meets a beam
        s = ledger_step(M, st, h)
        if s is None:
            continue
        h['step'] = s
        out.append(h)
    return sorted(out, key=lambda h: (h['x'], h['step'])), M


def accidental(M, st, head, others):
    """Sharp, flat or natural printed just left of a head, or None.

    Looks at line-free ink (stems kept: an accidental is mostly vertical strokes) in a
    window 0.5-2.6 SP left of the head centre and 2 SP above and below it, ignoring other
    heads.  Classifies the component nearest the head's height by its vertical strokes:
    a flat has one stroke rising well above the head and ending just below it; a sharp has
    two strokes of equal span about the head; a natural has two strokes, the left one
    higher and the right one lower.
    """
    sp = st['space']
    ink = M['noline'].copy()
    for o in others:                       # blank other heads in the window
        if o is head:
            continue
        xi = int(round(o['x'])) - M['X0']
        yc = int(round(yline(st, 4, o['x']) - o['step'] * sp / 2)) - M['Y0']
        ink[max(0, yc - int(.5 * sp)):yc + int(.5 * sp) + 1, max(0, xi - int(.7 * sp)):xi + int(.7 * sp) + 1] = False
    hx = int(round(head['x'])) - M['X0']
    hy = int(round(yline(st, 4, head['x']) - head['step'] * sp / 2)) - M['Y0']
    xa, xb = max(0, hx - int(2.6 * sp)), max(0, hx - int(.55 * sp))
    ya, yb = max(0, hy - int(2.2 * sp)), min(ink.shape[0], hy + int(2.2 * sp))
    win = ink[ya:yb, xa:xb]
    if win.size == 0:
        return None
    lab, n = ndimage.label(ndimage.binary_closing(win, structure=np.ones((3, 3))))
    best = None
    for i, sl in enumerate(ndimage.find_objects(lab)):
        top, bot = sl[0].start + ya - hy, sl[0].stop + ya - hy
        w = sl[1].stop - sl[1].start
        h = bot - top
        if h < 1.3 * sp or h > 3.6 * sp or w < .3 * sp or w > 1.4 * sp:
            continue
        if not (top < 0 < bot):
            continue
        # an accidental sits right against its head
        dist = hx - (sl[1].stop + xa)
        if dist > 1.25 * sp:
            continue
        if best is None or dist < best[0]:
            best = (dist, i + 1, sl, top, bot)
    if best is None:
        return None
    _, li, sl, top, bot = best
    blob = lab[sl] == li
    # vertical strokes: columns with a run of ink at least 1.2 SP long
    runs = []
    for c in range(blob.shape[1]):
        col = blob[:, c]
        r, best_r, start, bs = 0, 0, 0, 0
        for yy, v in enumerate(col):
            if v:
                if r == 0:
                    start = yy
                r += 1
                if r > best_r:
                    best_r, bs = r, start
            else:
                r = 0
        if best_r >= 1.2 * sp:
            runs.append((c, bs + sl[0].start + ya - hy, bs + best_r + sl[0].start + ya - hy))
    strokes = []
    for c, a, b in runs:
        if strokes and c - strokes[-1][-1][0] <= 2:
            strokes[-1].append((c, a, b))
        else:
            strokes.append([(c, a, b)])
    spans = [(min(a for _, a, _ in s), max(b for _, _, b in s)) for s in strokes]
    if len(spans) == 1:
        a, b = spans[0]
        if a < -1.0 * sp and b < .9 * sp:
            return 'flat'
        return '?'
    if len(spans) >= 2:
        (a1, b1), (a2, b2) = spans[0], spans[-1]
        if a1 < a2 - .35 * sp and b2 > b1 + .35 * sp:
            return 'natural'
        if abs(a1 - a2) < .6 * sp and abs(b1 - b2) < .6 * sp:
            return 'sharp'
        return '?'
    return None


def dots(M, st, col_heads):
    """Augmentation dots right of a column of heads: small round blobs in a space."""
    sp = st['space']
    ink = M['noline']
    xr = max(h['x'] for h in col_heads) - M['X0']
    out = 0
    xa, xb = int(xr + .75 * sp), int(xr + 1.9 * sp)
    for h in col_heads:
        s = h['step'] if h['step'] % 2 else h['step'] + 1       # dot sits in a space
        yc = int(round(yline(st, 4, h['x']) - s * sp / 2)) - M['Y0']
        win = ink[max(0, yc - int(.35 * sp)):yc + int(.35 * sp) + 1, max(0, xa):max(0, xb)]
        if win.size == 0:
            continue
        lab, n = ndimage.label(win)
        for sl in ndimage.find_objects(lab):
            hh = sl[0].stop - sl[0].start
            ww = sl[1].stop - sl[1].start
            if .2 * sp <= hh <= .6 * sp and .2 * sp <= ww <= .6 * sp:
                out += 1
                break
    return out
