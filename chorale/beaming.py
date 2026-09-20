"""Beam groups.

A beam group is a run of consecutive flagged notes, unbroken by a rest or a gap,
inside one beat.  Level 1 runs across the whole group; each further level covers
only the notes that carry that many flags, with hooks where a level has a single
note at the edge of the group.
"""
from fractions import Fraction as F

from .events import positions

FLAGS = {F(1, 2): 1, F(1, 4): 2, F(1, 8): 3}


def _nflags(base):
    return FLAGS.get(base, 0)


def beams(events, beat=F(1)):
    """Beam markup for a full bar of consecutive events, one string per event."""
    return beams_at(positions(events), beat)


def beams_at(pairs, beat=F(1)):
    """Beam markup for events at explicit offsets — a voice with gaps in it.

    `pairs` is [(offset, event), ...] in order.  Returns one markup string per
    pair, empty for anything not beamed.
    """
    evs = [e for _, e in pairs]
    marks = [''] * len(pairs)
    groups, cur = [], []
    for i, (pos, e) in enumerate(pairs):
        which = int(pos / beat)
        adjacent = bool(cur) and pairs[cur[-1][0]][0] + evs[cur[-1][0]]['dur'] == pos
        if e['pitches'] and e['base'] < 1:
            if cur and (cur[-1][1] != which or not adjacent):
                groups.append(cur)
                cur = []
            cur.append((i, which))
        else:
            if cur:
                groups.append(cur)
                cur = []
    if cur:
        groups.append(cur)
    for g in groups:
        if len(g) < 2:
            continue
        idx = [i for i, _ in g]
        deep = max(_nflags(evs[i]['base']) for i in idx)
        for n, i in enumerate(idx):
            lv1 = 'begin' if n == 0 else 'end' if n == len(idx) - 1 else 'continue'
            s = f'<beam number="1">{lv1}</beam>'
            for lvl in range(2, deep + 1):
                if _nflags(evs[i]['base']) < lvl:
                    continue
                pv = _nflags(evs[idx[n - 1]]['base']) >= lvl if n > 0 else False
                nx = _nflags(evs[idx[n + 1]]['base']) >= lvl if n + 1 < len(idx) else False
                if pv and nx:
                    v = 'continue'
                elif nx:
                    v = 'begin'
                elif pv:
                    v = 'end'
                else:
                    v = 'forward hook' if n == 0 else 'backward hook'
                s += f'<beam number="{lvl}">{v}</beam>'
            marks[i] = s
    return marks
