"""Put two lines on one staff.

Two ways, both used by real engraving:

`closed_bars` merges a common *prefix* — the two parts agree from the bar line
until they split, and stay split to the end of the bar.  That is how most closed
SATB scores are actually printed.

`merge_runs` merges every agreeing beat wherever it falls, so the parts may
diverge and re-converge any number of times inside one bar.  It is what you want
after a revoicing, where the two new parts agree in irregular patches.

`lyric_split` then decides, per bar, whether the staff needs a second lyric line,
and `prune_v2_extends` removes extender lines the engraver cannot draw.
"""
import copy
from fractions import Fraction as F

from .events import pkey, positions


# ---------------------------------------------------------------- prefix merge
def same_event(a, b):
    return (a['dur'] == b['dur'] and a['tie'] == b['tie']
            and a['slur_start'] == b['slur_start'] and a['slur_stop'] == b['slur_stop']
            and [pkey(x) for x in a['pitches']] == [pkey(x) for x in b['pitches']]
            and a['lyric'] == b['lyric'])


def closed_bars(nbars, block_shared, up_block, down_block):
    """-> {bar: (voice 1 events, voice 2 events, split offset)}

    Voice 2 is empty, and the split offset None, in any bar the staff is a single
    voice.  Where the parts split, voice 1 carries the shared prefix as chords
    and then the upper part alone; voice 2 starts at the split offset.
    """
    out = {}
    for m in range(1, nbars + 1):
        shared = block_shared.get(m)
        if m not in up_block and m not in down_block:
            out[m] = (copy.deepcopy(shared), [], None)
            continue
        up = copy.deepcopy(up_block.get(m) or shared)
        dn = copy.deepcopy(down_block.get(m) or shared)
        k = 0
        while k < min(len(up), len(dn)) and same_event(up[k], dn[k]):
            k += 1
        if k == len(up) == len(dn):
            out[m] = (up, [], None)
            continue
        v1 = up
        for i in range(k):
            merged = {pkey(x): x for x in up[i]['pitches'] + dn[i]['pitches']}
            v1[i]['pitches'] = [merged[q] for q in sorted(merged)]
        out[m] = (v1, dn[k:], sum(e['dur'] for e in up[:k]))
    return out


def finalize_closed(bars, nbars):
    """tie_stop and lyric extend for a staff already merged into two voices.

    A tie here may land on a chord rather than a single note — the note it
    sustains only has to be *one of* the pitches in the next event — because the
    continuation may have been merged into voice 1.
    """
    for vi in (0, 1):
        prev = None
        for m in range(1, nbars + 1):
            for e in bars[m][vi]:
                e['tie_stop'] = bool(prev and prev['tie'] and prev['pitches'] and e['pitches']
                                     and {pkey(x) for x in prev['pitches']}
                                     & {pkey(x) for x in e['pitches']})
                prev = e
    for vi in (0, 1):
        flat = [e for m in range(1, nbars + 1) for e in bars[m][vi]]
        for i, e in enumerate(flat):
            if e['pitches'] and e['lyric']:
                e['lyric']['extend'] = (i + 1 < len(flat) and bool(flat[i + 1]['pitches'])
                                        and not flat[i + 1]['lyric'])
    return bars


# ---------------------------------------------------------------- run merge
def mergeable(a, b):
    """Can two simultaneous events share one notehead group in one voice?

    They must agree in everything a reader sees except pitch: length, notation,
    ties, slurs, and the syllable underneath.  Same sound, different spelling is
    still two voices.
    """
    if a['dur'] != b['dur'] or a['dots'] != b['dots'] or a['base'] != b['base']:
        return False
    if bool(a['pitches']) != bool(b['pitches']):           # rest against note
        return False
    if a['tie'] != b['tie'] or a.get('tie_stop') != b.get('tie_stop'):
        return False
    if a['slur_start'] != b['slur_start'] or a['slur_stop'] != b['slur_stop']:
        return False
    la, lb = a['lyric'], b['lyric']
    if (la is None) != (lb is None):
        return False
    if la and (la['text'] != lb['text'] or la['syllabic'] != lb['syllabic']):
        return False
    return True


def chord_merge(a, b):
    e = copy.deepcopy(a)
    seen = {pkey(p): p for p in a['pitches']}
    for p in b['pitches']:
        seen.setdefault(pkey(p), p)
    e['pitches'] = [seen[k] for k in sorted(seen)]
    return e


def merge_runs(up, dn, beats=4):
    """Collapse two single-voice bars onto one staff.

    Returns (v1, v2).  v1 covers the whole bar: chords where the two parts agree,
    the upper part's own notes where they diverge.  v2 is [(offset, event), ...]
    for the lower part, present only in the divergent stretches.
    """
    U, D = positions(up), positions(dn)
    umap, dmap = dict(U), dict(D)
    sync = {p for p in umap if p in dmap and mergeable(umap[p], dmap[p])}
    v1, v2 = [], []
    cur = F(0)
    ui = di = 0
    while ui < len(U) or di < len(D):
        if cur in sync:
            v1.append(chord_merge(umap[cur], dmap[cur]))
            cur += umap[cur]['dur']
            while ui < len(U) and U[ui][0] < cur:
                ui += 1
            while di < len(D) and D[di][0] < cur:
                di += 1
            continue
        nxt = min([p for p in sync if p > cur], default=F(beats))
        while ui < len(U) and U[ui][0] < nxt:
            v1.append(copy.deepcopy(U[ui][1]))
            ui += 1
        while di < len(D) and D[di][0] < nxt:
            v2.append((D[di][0], copy.deepcopy(D[di][1])))
            di += 1
        cur = nxt
    return v1, v2


# ---------------------------------------------------------------- lyric lines
def lyric_split(up, dn, nbars):
    """Per bar: does this staff need two lyric lines?

    It does only where the two voices sing *different syllables*.  Where they
    sing the same words and differ only in rhythm — a melisma in one part against
    a plain note in the other — one line serves both, and the lower voice's copy
    of the syllable is dropped rather than printed as a stray second line.

    Deciding this by asking whether two syllables collide on the page instead
    puts half a word on line 2 and leaves an extender dangling under it.
    """
    def seq(evs):
        return [e['lyric']['text'] for e in evs if e['lyric']]
    return {m: seq(up[m]) != seq(dn[m]) for m in range(1, nbars + 1)}


def prune_v2_extends(bars, nbars, beats=4):
    """Drop an extender the printed score cannot draw.

    A voice-2 syllable may be held over a note that, in the next bar, merges back
    into voice 1.  Voice 2 then has no further note for the extender line to run
    under, so the line goes and the tie alone shows the sustain.  Verovio reports
    the case as "syllable with underline extender under one single note".
    """
    stream = []
    for m in range(1, nbars + 1):
        for p, e in bars[m][1]:
            if e['pitches']:
                stream.append((m, p, p + e['dur'], e))
    for i, (m, a, b, e) in enumerate(stream):
        if not (e['lyric'] and e['lyric'].get('extend')):
            continue
        nx = stream[i + 1] if i + 1 < len(stream) else None
        cont = nx is not None and ((nx[0] == m and nx[1] == b)
                                   or (nx[0] == m + 1 and b == beats and nx[1] == 0))
        if not cont:
            e['lyric']['extend'] = False
    return bars
