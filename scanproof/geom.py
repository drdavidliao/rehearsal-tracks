"""Staff geometry of a scanned page: every staff line followed across the page as a
sampled curve, lines grouped into five-line staves, staves into systems, barlines voted.

Phone scans curve, so a staff line is not a row: each line is followed slice by slice
and kept as samples (x, y), interpolated between them.  Positions are then reported in
staff steps (half spaces) from the bottom line at that x, which is what turns a
notehead into a pitch.

Pixel tolerances were tuned on a 300 dpi phone scan whose staff space is about 19 px;
every one is scaled by the page's own measured staff space (`Page.k`).
"""
import numpy as np
from PIL import Image
from scipy import ndimage

REF_SPACE = 19.0     # staff space (px) the constants below were tuned at


class Page:
    """One page image, with its ink masks cached.

    `dark` is a fixed threshold (staff lines and barlines); `ink(contrast)` is ink
    relative to the local paper, which survives a scan that is paler at one corner.
    """

    def __init__(self, path, thr=150):
        self.path = path
        self.gray = np.asarray(Image.open(path).convert('L'))
        self.dark = self.gray < thr
        self._ink = {}
        self.space = estimate_space(self.dark)
        self.k = self.space / REF_SPACE

    def threshold(self, thr):
        return self.gray < thr

    def ink(self, contrast=75):
        if contrast not in self._ink:
            im = self.gray.astype(np.int16)
            w = int(round(35 * self.k)) | 1
            bg = ndimage.uniform_filter(ndimage.maximum_filter(im, size=w), size=w)
            self._ink[contrast] = (bg - im) > contrast
        return self._ink[contrast]

    def image(self):
        return Image.open(self.path).convert('RGB')


def estimate_space(dark):
    """Most common distance between thin dark runs down a column: the staff space."""
    H, W = dark.shape
    gaps = []
    for x in np.linspace(W * .1, W * .9, 40).astype(int):
        col = dark[:, x]
        d = np.diff(col.astype(np.int8))
        starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
        if len(starts) < 5 or len(ends) < 5:
            continue
        if ends[0] < starts[0]:
            ends = ends[1:]
        n = min(len(starts), len(ends))
        thin = [(a + b) / 2 for a, b in zip(starts[:n], ends[:n]) if b - a <= 6]
        gaps += [g for g in np.diff(thin) if 8 <= g <= 60]
    if not gaps:
        return REF_SPACE
    h, edges = np.histogram(gaps, bins=np.arange(8, 61, 1))
    i = int(np.argmax(h))
    sel = [g for g in gaps if edges[i] - 1 <= g <= edges[i] + 2]
    return float(np.median(sel))


def line_peaks(dark, x, slice_w):
    band = dark[:, x:x + slice_w].mean(1)
    pk = [i for i in range(1, len(band) - 1)
          if band[i] > .35 and band[i] >= band[i - 1] and band[i] >= band[i + 1]]
    g = []
    for i in pk:
        if g and i - g[-1][-1] <= 2:
            g[-1].append(i)
        else:
            g.append([i])
    return [float(np.mean(q)) for q in g]


def five_groups(peaks, space, k):
    """Every run of five peaks with equal spacing (a staff seen in one slice)."""
    out, used = [], set()
    n = len(peaks)
    for i in range(n):
        if i in used:
            continue
        best = None
        for j in range(i + 1, min(n, i + 4)):
            sp = peaks[j] - peaks[i]
            if not .7 * space < sp < 1.35 * space:
                continue
            idx = [i, j]
            for _ in range(3):
                want = peaks[idx[-1]] + sp
                c = min(range(n), key=lambda q: abs(peaks[q] - want))
                if abs(peaks[c] - want) > 2.2 * k:
                    break
                idx.append(c)
            if len(idx) == 5:
                err = np.diff([peaks[q] for q in idx]).std()
                if best is None or err < best[0]:
                    best = (err, idx)
        if best and best[0] < 1.6 * k:
            used.update(best[1])
            out.append([peaks[q] for q in best[1]])
    return out


def staves(page):
    """Every staff on the page, top to bottom: {'samples': [[xs, ys]] * 5 lines (top
    first), 'x0', 'x1', 'space'}."""
    dark, k = page.dark, page.k
    H, W = dark.shape
    slice_w, step = int(round(24 * k)), int(round(20 * k))
    chains = []          # each chain: list of (x, [5 ys])
    for x in range(0, W - slice_w, step):
        for g in five_groups(line_peaks(dark, x, slice_w), page.space, k):
            best = None
            for ch in chains:
                lx, ly = ch[-1]
                if 0 < x - lx <= 12 * step:
                    d = abs(ly[0] - g[0]) + abs(ly[4] - g[4])
                    if d < 8 * k + 0.06 * (x - lx) and (best is None or d < best[0]):
                        best = (d, ch)
            if best:
                best[1].append((x, g))
            else:
                chains.append([(x, g)])
    # join pieces of one staff that a big chord or a stain split apart
    chains.sort(key=lambda c: c[0][0])
    joined = []
    for ch in chains:
        for J in joined:
            lx, ly = J[-1]
            fx, fy = ch[0]
            if fx > lx and abs(ly[0] - fy[0]) + abs(ly[4] - fy[4]) < 8 * k + 0.08 * (fx - lx):
                J.extend(ch)
                break
        else:
            joined.append(list(ch))
    chains = [c for c in joined if c[-1][0] - c[0][0] > W * 0.4 and len(c) > 15]
    out = []
    for ch in chains:
        xa = np.array([p[0] + slice_w / 2 for p in ch], dtype=float)
        order = np.argsort(xa)
        xa = xa[order]
        samples = []
        for li in range(5):
            ya = np.array([ch[i][1][li] for i in order], dtype=float)
            # robust: running median, drop points far from it, then a light running mean
            med = np.array([np.median(ya[max(0, i - 4):i + 5]) for i in range(len(ya))])
            keep = np.abs(ya - med) < 2.0 * k
            xk, yk = xa[keep], ya[keep]
            sm = np.array([np.mean(yk[max(0, i - 1):i + 2]) for i in range(len(yk))])
            samples.append([xk.tolist(), sm.tolist()])
        ys = [np.interp(W / 2, *samples[li]) for li in range(5)]
        out.append({'samples': samples, 'x0': float(xa.min()), 'x1': float(xa.max()),
                    'space': float(np.mean(np.diff(ys)))})
    out.sort(key=lambda s: np.interp(W / 2, *s['samples'][0]))
    return out


def yline(st, li, x):
    """y of line li (0 = top) at x; straight-line extension outside the sampled range."""
    xs, ys = st['samples'][li]
    if xs[0] <= x <= xs[-1]:
        return float(np.interp(x, xs, ys))
    # beyond the measured range: continue the slope of the last 200 px
    if x < xs[0]:
        n = max(2, sum(1 for v in xs if v < xs[0] + 200))
        sl = (ys[n - 1] - ys[0]) / max(xs[n - 1] - xs[0], 1)
        return float(ys[0] + sl * (x - xs[0]))
    n = max(2, sum(1 for v in xs if v > xs[-1] - 200))
    sl = (ys[-1] - ys[-n]) / max(xs[-1] - xs[-n], 1)
    return float(ys[-1] + sl * (x - xs[-1]))


def y_of_step(st, x, step):
    """y of staff step `step` (0 = bottom line) at x, by the staff's own spacing."""
    y0, y4 = yline(st, 0, x), yline(st, 4, x)
    return y4 - step * (y4 - y0) / 8


def step_at(st, x, y):
    """Staff step of point (x, y): 0 = bottom line, 1 = space above it, ..."""
    y0, y4 = yline(st, 0, x), yline(st, 4, x)
    return (y4 - y) / ((y4 - y0) / 8)


def fit_miss(page, st, every=40):
    """90th-percentile distance (px) from the fitted lines to the printed ones."""
    slice_w = int(round(24 * page.k))
    miss = []
    for x in range(int(st['x0']), int(st['x1']) - slice_w, every):
        pk = np.array(line_peaks(page.dark, x, slice_w))
        if len(pk) == 0:
            continue
        for li in range(5):
            miss.append(np.abs(pk - yline(st, li, x + slice_w / 2)).min())
    return float(np.percentile(miss, 90)) if miss else float('nan')


def full_strokes(dark, st, lo, hi, k):
    """x where a thin vertical stroke covers the staff from top line to bottom line, with
    no notehead at either end."""
    sp = st['space']
    out = []
    hw, wide_n = int(round(14 * k)), 12 * k
    for x in range(lo, hi):
        y0, y1 = yline(st, 0, x), yline(st, 4, x)
        ys = np.arange(int(round(y0)), int(round(y1)) + 1)
        if dark[ys, x - 1:x + 2].any(1).mean() < .94:
            continue
        # a notehead at either end is wide ink just inside the staff
        wide = False
        for yy in (y0 + .5 * sp, y1 - .5 * sp):
            row = dark[int(yy) - 3:int(yy) + 4, max(0, x - hw):x + hw + 1].mean(0)
            if (row > .5).sum() > wide_n:
                wide = True
        if not wide:
            out.append(x)
    return out


def barlines_system(dark, sts, g, k, grand=None):
    """Barline x's of one system: a full-height stroke voted by most of its staves.

    `grand` is a pair of indices into `g` (a piano's two staves): a stroke through
    both of them that also crosses the gap between them counts on its own, since the
    voices above may be resting with no barline drawn through their staves.
    Returns [(x, votes)]."""
    W = dark.shape[1]
    lo = max(int(min(sts[i]['x0'] for i in g)) - 40, 3)
    hi = min(int(max(sts[i]['x1'] for i in g)) + 40, W - 3)
    votes = {}
    for i in g:
        for x in full_strokes(dark, sts[i], lo, hi, k):
            votes.setdefault(x, set()).add(i)
    clusters = []
    for x in sorted(votes):
        if clusters and x - clusters[-1][-1] <= 10 * k:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    need = max(1, int(np.ceil(.75 * len(g))))
    out = []
    for c in clusters:
        who = set().union(*(votes[x] for x in c))
        xm = int(round(np.mean(c)))
        ok = len(who) >= need
        if not ok and grand:
            R, L = sts[g[grand[0]]], sts[g[grand[1]]]
            if {g[grand[0]], g[grand[1]]} <= who:
                gy = np.arange(int(yline(R, 4, xm)) + 1, int(yline(L, 0, xm)))
                gap = max(dark[gy, x - 1:x + 2].any(1).mean() for x in range(xm - 4, xm + 5))
                ok = gap > .9
        if ok:
            out.append((float(np.mean(c)), len(who)))
    return out


def page_geometry(page, staves_per_system, grand=None, barline_thr=228):
    """{'staves': [...], 'systems': [{'staves': [i...], 'barlines': [(x, votes)]}]}.

    Staves are grouped top to bottom, `staves_per_system` at a time; a page whose staff
    count is not a multiple of it raises, since every bar reference after that would be
    wrong.  Barlines are looked for on a paler threshold: they print grey on some scans."""
    sts = staves(page)
    if len(sts) % staves_per_system:
        raise ValueError(f'{page.path}: {len(sts)} staves found, not a multiple of '
                         f'{staves_per_system}; check the page overlay')
    pale = page.threshold(barline_thr)
    systems = []
    for i in range(0, len(sts), staves_per_system):
        g = list(range(i, i + staves_per_system))
        systems.append({'staves': g, 'barlines': barlines_system(pale, sts, g, page.k, grand)})
    return {'staves': sts, 'systems': systems, 'space': page.space}
