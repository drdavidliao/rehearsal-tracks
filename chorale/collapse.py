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

    And the parts must not be crossed.  `a` is the upper part, `b` the lower;
    if `b` is above `a` here, a chord would put the lower part's note on top,
    and a singer reading one stem cannot tell whose note is whose.  A crossing
    is written as two voices, stems up and down, so each part keeps its own
    stem.  A unison is not a crossing.
    """
    if a['pitches'] and b['pitches'] and \
            max(pkey(p) for p in b['pitches']) > min(pkey(p) for p in a['pitches']):
        return False
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


def merge_runs(up, dn, beats=4, hold_start=False, hold_end=False):
    """Collapse two single-voice bars onto one staff.

    Returns (v1, v2).  v1 covers the whole bar: chords where the two parts agree,
    the upper part's own notes where they diverge.  v2 is [(offset, event), ...]
    for the lower part, present only in the divergent stretches.
    """
    U, D = positions(up), positions(dn)
    umap, dmap = dict(U), dict(D)
    sync = {p for p in umap if p in dmap and mergeable(umap[p], dmap[p])}
    if hold_start:                  # voice 2 arrives tied from the bar before
        sync.discard(F(0))
    if hold_end and U and D:        # voice 2 leaves tied into a bar where it splits off
        sync.discard(max(U[-1][0], D[-1][0]))
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



def merge_staff(up, dn, nbars, beats=4):
    """merge_runs over a whole staff, keeping every tie inside one voice.

    Merging is decided bar by bar, so a note held in voice 2 across a barline
    could land, in the next bar, in a unison that merges into voice 1.  The tie
    then jumps voices, and voice 2 has no note left for its syllable's extender
    to run under, so the lyric line under a held word disappears.  When voice 2
    ends a bar on a tie, the tied note in the next bar stays in voice 2 — a
    unison written with one stem up and one down, as an engraver would.  The
    same holds for a melisma that runs on over the barline, and for a tie out
    of a unison into a bar where voice 2 splits off: the tied note stays out of
    the chord.
    `up` and `dn` are {bar: [events]}.  Returns {bar: (v1, v2)}.
    """
    def held_into(m, bars):
        """Voice 2 runs on from bar m-1 into bar m: by a tie, or by a melisma
        whose line needs a voice-2 note to run under."""
        prev = bars.get(m - 1)
        return bool(prev and prev[1] and prev[1][-1][0] + prev[1][-1][1]['dur'] == beats
                    and (prev[1][-1][1]['tie']
                         or (dn[m] and dn[m][0]['pitches'] and not dn[m][0]['lyric'])))

    bars = {}
    for m in range(1, nbars + 1):
        bars[m] = merge_runs(up[m], dn[m], beats, hold_start=held_into(m, bars))
    # The other direction: a tie out of a unison that merged into voice 1, into
    # a bar where voice 2 splits off, would start in voice 1 and stop in voice 2.
    # Keep the tied note out of the chord, and redo the bar after it.
    ends = set()
    changed = True
    while changed:
        changed = False
        for m in range(1, nbars):
            nxt = bars[m + 1][1]
            if (m not in ends and nxt and nxt[0][0] == 0 and dn[m + 1][0].get('tie_stop')
                    and dn[m] and dn[m][-1]['tie']):
                v2 = bars[m][1]
                if not v2 or v2[-1][0] + v2[-1][1]['dur'] != beats:
                    ends.add(m)
                    bars[m] = merge_runs(up[m], dn[m], beats, hold_start=held_into(m, bars),
                                         hold_end=True)
                    bars[m + 1] = merge_runs(up[m + 1], dn[m + 1], beats,
                                             hold_start=held_into(m + 1, bars))
                    changed = True
    return bars


def crossed_bars(bars):
    """Bars where the two parts on a shared staff are crossed the whole time.

    Voice 1 is stems up and voice 2 stems down, because voice 1 is normally the
    higher part.  When the parts cross for a stretch — voice 2 above voice 1 at
    every moment both are singing different notes — that convention puts the
    stems-down notes on top, and anything attached to them (a held note's tie,
    most visibly) is drawn through the other part's noteheads or stems.  No tie
    direction clears it; the engraved fix is to let the stems follow position
    for that bar, which is how the part would look had it never been swapped.

    A bar counts only if the voices are in reverse order at least once and in
    normal order never.  Unisons and moments where one voice rests are neutral.
    `bars` is {bar: (v1, v2)} from merge_runs.  Returns a set of bar numbers.
    """
    out = set()
    for m, (v1, v2) in bars.items():
        crossed = normal = False
        v1pos = positions(v1)
        for p, e in v2:
            if not e['pitches']:
                continue
            for q, f in v1pos:
                if not f['pitches'] or not (q < p + e['dur'] and p < q + f['dur']):
                    continue
                lo2 = min(pkey(x) for x in e['pitches'])
                hi2 = max(pkey(x) for x in e['pitches'])
                lo1 = min(pkey(x) for x in f['pitches'])
                hi1 = max(pkey(x) for x in f['pitches'])
                if lo2 > hi1:
                    crossed = True
                elif hi2 < lo1:
                    normal = True
        if crossed and not normal:
            out.add(m)
    return out


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
        # the words AND where each starts: the same word entering a beat apart
        # in the two voices needs its own copy under each entrance
        return [(p, e['lyric']['text']) for p, e in positions(evs) if e['lyric']]
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
