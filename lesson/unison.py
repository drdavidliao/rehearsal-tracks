"""Bars where parts sing in unison (same pitches and rhythm) or in octaves, as runs of bars per grouping."""
from . import analyze
from .analyze import PARTS


def bar_groups(S, n):
    """[(unison parts, octave parts)] for bar n. Parts singing the same line in any octave form a class; within it
    the largest set singing the very same pitches is the unison, the rest are octave doublings. A class of two
    parts an octave apart and nothing else is (one part, its octave partner)."""
    lines = {p: S.line(p, n) for p in PARTS if S.notes(p, n)}
    def same_shape(x, y):
        return len(x) == len(y) and all(a[:2] == b[:2] and a[3] == b[3] for a, b in zip(x, y)) \
            and len({a[2] - b[2] for a, b in zip(x, y)}) == 1 and (x[0][2] - y[0][2]) % 12 == 0
    classes = []
    for p in PARTS:
        if p not in lines: continue
        for c in classes:
            if same_shape(lines[p], lines[c[0]]): c.append(p); break
        else: classes.append([p])
    out = []
    for c in classes:
        if len(c) < 2: continue
        exact = {}
        for p in c: exact.setdefault(lines[p], []).append(p)
        uni = max(exact.values(), key=len)
        octv = [p for p in c if p not in uni]
        out.append((tuple(uni), tuple(octv)))
    return out


def passages(S):
    """[(first bar, last bar, unison parts, octave parts)] maximal runs of bars with the same grouping"""
    out = []
    for n in range(1, S.nbars + 1):
        for g in bar_groups(S, n):
            if out and out[-1][1] == n - 1 and (out[-1][2], out[-1][3]) == g:
                out[-1][1] = n
            else:
                # merge only with a run that ended on the previous bar
                cont = [o for o in out if o[1] == n - 1 and (o[2], o[3]) == g]
                if cont: cont[0][1] = n
                else: out.append([n, n, g[0], g[1]])
    return [tuple(o) for o in out]
