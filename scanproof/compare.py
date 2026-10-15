"""Proofread the transcription against the scan, every staff of every bar.

For each bar and staff: read the noteheads from the pixels (heads.read_staff), group
them into columns by x, and align the columns to the transcribed events in time order
(dynamic programming: a column matches an event at a cost of the heads they disagree
on; an unmatched column or event costs more).  Then, for every matched pair, compare

  - the set of staff positions (pitch letters and octaves),
  - notehead kind (filled / hollow / whole / x),
  - note value: beams or flags on the stem (eighth, sixteenth...) against the
    transcribed value, so an eighth entered as a quarter is caught,
  - accidentals: a printed sharp, flat or natural must equal the transcribed
    alteration; a head with no printed accidental must have the alteration the key and
    the bar so far give it (a tie carries it over the barline),
  - augmentation dots.

Every disagreement goes to findings.json.  Most findings are the detector's errors,
not the transcription's: every one is meant to be looked at (review.py).
"""
import json
from collections import Counter

import numpy as np

from . import expected, heads
from .expected import value_name

ACC = {'sharp': 1, 'flat': -1, 'natural': 0}


def columns(hh, sp):
    cols = []
    for h in sorted(hh, key=lambda h: h['x']):
        if cols and abs(h['x'] - np.mean([c['x'] for c in cols[-1]])) < 1.45 * sp \
                and h['kind'] == cols[-1][0]['kind'] and not any(c['step'] == h['step'] for c in cols[-1]):
            cols[-1].append(h)
        else:
            cols.append([h])
    return cols


def align(cols, evs, beams=None):
    """Monotone alignment; returns list of (col index or None, event index or None).

    A column costs one per head it disagrees on, half for the wrong notehead kind, and
    a little (0.3) for the wrong number of beams: not enough to outweigh a pitch, but
    enough that when a head was missed the remaining columns pair with the events of
    their own value rather than with the next ones along."""
    n, m = len(cols), len(evs)
    SKIP = 2.5
    D = np.full((n + 1, m + 1), 1e9)
    P = {}
    D[0, 0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            if i < n and D[i, j] + SKIP < D[i + 1, j]:
                D[i + 1, j] = D[i, j] + SKIP
                P[(i + 1, j)] = (i, j)
            if j < m and D[i, j] + SKIP < D[i, j + 1]:
                D[i, j + 1] = D[i, j] + SKIP
                P[(i, j + 1)] = (i, j)
            if i < n and j < m:
                a = {h['step'] for h in cols[i]}
                b = {h['step'] for h in evs[j]['heads']}
                c = len(a ^ b) * 1.0 + (0.5 if cols[i][0]['kind'] != evs[j]['kind'] else 0)
                if beams and beams[i] is not None and beams[i] not in evs[j]['beams']:
                    c += 0.3
                if D[i, j] + c < D[i + 1, j + 1]:
                    D[i + 1, j + 1] = D[i, j] + c
                    P[(i + 1, j + 1)] = (i, j)
    out, cur = [], (n, m)
    while cur != (0, 0):
        prev = P[cur]
        if prev[0] < cur[0] and prev[1] < cur[1]:
            out.append((prev[0], prev[1]))
        elif prev[0] < cur[0]:
            out.append((prev[0], None))
        else:
            out.append((None, prev[1]))
        cur = prev
    return out[::-1]


def read_bar(prj, b, name, evs=None):
    """Heads and masks for one staff of one bar (b: the bar table entry)."""
    page = prj.page(b['page'])
    st = prj.staff(b, name)
    sp = st['space']
    x0 = b['x0'] + 4 * page.k
    if b['first_in_system']:
        x0 = b['x0'] + b['start_space'] * sp
    whole = bool(evs) and any(e['kind'] == 'whole' for e in evs)
    hh, M = heads.read_staff(page.ink(prj.cfg.get('contrast', 75)), st, x0, b['x1'] - 4 * page.k,
                             page.ink(prj.cfg.get('stem_contrast', 30)),
                             xheads=prj.staff_cfg(name).get('xheads', False), whole=whole, k=page.k)
    return hh, M, st


def check(prj, bars=None):
    E = expected.events(prj)
    B = prj.bars()
    requested, bars = bars, bars or sorted(B)
    missing = sorted({m for (_, m) in E} - set(B))
    if missing and not requested:
        raise ValueError(f'bars {missing} are in the transcription but not in the bar table')
    findings = []
    stats = Counter()
    confusion = Counter()        # (transcribed beams, beams read) over matched columns
    for m in bars:
        b = B[m]
        for name in prj.names:
            evs = E.get((name, m), [])
            hh, M, st = read_bar(prj, b, name, evs)
            sp = st['space']
            stats['staff_bars'] += 1
            stats['heads_read'] += len(hh)
            stats['events'] += len(evs)
            cols = columns(hh, sp)
            nb = [heads.beam_count(M, st, c)[0] if c[0]['kind'] in ('filled', 'x') else 0
                  for c in cols]
            for ci, ei in align(cols, evs, nb):
                where = {'bar': m, 'staff': name}
                if ei is None:
                    c = cols[ci]
                    findings.append({**where, 'type': 'extra printed column',
                                     'x': round(c[0]['x']), 'printed': [prj.step_name(h['step'], name) for h in c],
                                     'kind': c[0]['kind']})
                    continue
                ev = evs[ei]
                where['onset'] = str(ev['onset'])
                if ci is None:
                    findings.append({**where, 'type': 'event not found in print',
                                     'expected': [h['name'] for h in ev['heads']], 'kind': ev['kind']})
                    continue
                c = cols[ci]
                where['x'] = round(float(np.mean([h['x'] for h in c])))
                a = sorted(h['step'] for h in c)
                if a != [h['step'] for h in ev['heads']]:
                    findings.append({**where, 'type': 'pitch set differs',
                                     'printed': [prj.step_name(s, name) for s in a],
                                     'expected': [h['name'] for h in ev['heads']]})
                if c[0]['kind'] != ev['kind']:
                    findings.append({**where, 'type': 'notehead kind differs',
                                     'printed': c[0]['kind'], 'expected': ev['kind'],
                                     'heads': [h['name'] for h in ev['heads']]})
                elif ev['kind'] in ('filled', 'x'):
                    n = nb[ci]
                    stats['values_read'] += n is not None
                    confusion[(','.join(map(str, sorted(ev['beams']))), n)] += 1
                    if n is not None and n not in ev['beams']:
                        findings.append({**where, 'type': 'note value differs',
                                         'printed': value_name(n, ev['kind']),
                                         'expected': '/'.join(value_name(v, ev['kind']) for v in sorted(ev['beams'])),
                                         'heads': [h['name'] for h in ev['heads']]})
                for h in c:
                    eh = [e for e in ev['heads'] if e['step'] == h['step']]
                    if not eh:
                        continue
                    eh = eh[0]
                    acc = heads.accidental(M, st, h, hh)
                    if acc in ACC:
                        if ACC[acc] != eh['alter']:
                            findings.append({**where, 'type': 'accidental differs', 'head': eh['name'],
                                             'printed': acc})
                    elif acc is None:
                        if eh['alter'] != eh['state_alter'] and not eh['tie_stop']:
                            findings.append({**where, 'type': 'transcribed alteration has no printed accidental',
                                             'head': eh['name']})
                    elif not eh['acc_needed']:
                        findings.append({**where, 'type': 'unclassified mark left of head', 'head': eh['name']})
                nd = heads.dots(M, st, c)
                if (nd > 0) != (max(ev['dots']) > 0) and ev['kind'] != 'x':
                    findings.append({**where, 'type': 'dot differs', 'printed_dot': nd > 0,
                                     'expected_dots': max(ev['dots']), 'heads': [h['name'] for h in ev['heads']]})
    res = {'stats': dict(stats), 'counts': dict(Counter(f['type'] for f in findings)),
           'value_confusion': {f'{a} -> {b}': n for (a, b), n in sorted(confusion.items(), key=str)},
           'findings': findings}
    return res


def save(res, path):
    with open(path, 'w') as fh:
        json.dump(res, fh, indent=1)
