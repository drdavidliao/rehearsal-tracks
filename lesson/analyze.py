"""Read a SATB+piano MusicXML into per-part, per-bar note lists and compare parts and sections."""
import xml.etree.ElementTree as ET
from fractions import Fraction as F
from collections import defaultdict

STEPS = 'CDEFGAB'
PARTS = ['Soprano', 'Alto', 'Tenor', 'Bass']


def midi(p):
    return 12 * (int(p.findtext('octave')) + 1) + [0, 2, 4, 5, 7, 9, 11][STEPS.index(p.findtext('step'))] + int(float(p.findtext('alter') or 0))


class Score:
    def __init__(self, path):
        root = ET.parse(path).getroot()
        names = {sp.get('id'): sp.findtext('part-name') for sp in root.iter('score-part')}
        self.bars = {}      # part -> {bar: [event]}   event = dict(on, dur, midi|None, tie_stop, tie_start, lyric)
        self.letters = {}   # bar -> letter
        self.keys = {}
        self.times = {}
        self.implicit = set()     # bars marked implicit (a pickup bar)
        for part in root.findall('part'):
            nm = names[part.get('id')]
            if nm not in PARTS:
                continue
            div = 1
            bars = {}
            for m in part.findall('measure'):
                n = int(m.get('number'))
                if m.get('implicit') == 'yes': self.implicit.add(n)
                t = F(0)
                evs = []
                for e in m:
                    if e.tag == 'attributes':
                        if e.find('divisions') is not None: div = int(e.findtext('divisions'))
                        if e.find('key') is not None: self.keys[n] = int(e.find('key').findtext('fifths'))
                        if e.find('time') is not None: self.times[n] = (int(e.find('time').findtext('beats')), int(e.find('time').findtext('beat-type')))
                    elif e.tag == 'direction' and nm == 'Soprano':
                        r = e.find('.//rehearsal')
                        if r is not None: self.letters[n] = r.text
                    elif e.tag == 'backup': t -= F(int(e.findtext('duration')), div)
                    elif e.tag == 'forward': t += F(int(e.findtext('duration')), div)
                    elif e.tag == 'note':
                        if e.find('chord') is not None: continue
                        d = F(int(e.findtext('duration')), div)
                        p = e.find('pitch')
                        ties = {x.get('type') for x in e.findall('tie')}
                        ly = e.find('lyric')
                        evs.append(dict(on=t, dur=d, midi=midi(p) if p is not None else None,
                                        tie_stop='stop' in ties, tie_start='start' in ties,
                                        lyric=(ly.findtext('text') if ly is not None else None),
                                        x=e.find('notehead') is not None))
                        t += d
                bars[n] = evs
            self.bars[nm] = bars
        self.nbars = max(self.bars['Soprano'])
        # notes at the end of a letter's last bar that lead into the next letter (after the bar's last rest, on beat 3
        # or later, with words) belong to the next letter: they are left out when a letter is compared with another
        for p, bars in self.bars.items():
            for n, evs in bars.items():
                if n + 1 not in self.letters: continue
                tail = []
                for e in reversed(evs):
                    if e['midi'] is None: break
                    tail.append(e)
                if tail and len(tail) < len(evs) and tail[-1]['on'] >= self.pickup_from(n) and tail[-1]['lyric']:
                    for e in tail: e['lead_in'] = True

    # ---------------------------------------------------------------- meter
    def meter(self, n):
        """(beat in quarters, compound) for bar n: 6/8, 9/8, 12/8 are counted in dotted quarters, '1 & a 2 & a'"""
        ts = (4, 4)
        for m in sorted(self.times):
            if m > n: break
            ts = self.times[m]
        if ts[1] >= 8 and ts[0] % 3 == 0 and ts[0] > 3:
            return F(12, ts[1]), True
        return F(4, ts[1]), False

    def pickup_from(self, n):
        """where a lead-in into the next bar may start: beat 3 of a simple bar, the second half of a compound one"""
        beat, compound = self.meter(n)
        if not compound: return 2
        ts = max(((m, t) for m, t in self.times.items() if m <= n), default=(1, (6, 8)))[1]
        return beat * (ts[0] // 3 // 2)

    def notes(self, part, b):
        return [e for e in self.bars[part].get(b, []) if e['midi'] is not None]

    def sings(self, part, a, b):
        return any(self.notes(part, n) for n in range(a, b + 1))

    # ---------------------------------------------------------------- relations
    def rhythm(self, part, n):
        """attack points (not tie continuations) and rests"""
        return tuple((e['on'], e['dur'] if not e['tie_start'] else None) for e in self.own(part, n)
                     if e['midi'] is not None and not e['tie_stop'])

    def line(self, part, n):
        return tuple((e['on'], e['dur'], e['midi'], e['tie_stop']) for e in self.own(part, n) if e['midi'] is not None)

    def words(self, part, n):
        return tuple(e['lyric'] for e in self.own(part, n) if e['lyric'])

    def own(self, part, n):
        """bar n's events without a lead-in to the next letter"""
        return [e for e in self.bars[part].get(n, []) if not e.get('lead_in')]

    def relation(self, p, q, a, b):
        """over bars a..b where both sing: 'unison' (same pitches), 'octave', 'duet' (same rhythm and words),
        'rhythm' (same rhythm), or None, with the share of bars it holds in"""
        both = [n for n in range(a, b + 1) if self.notes(p, n) and self.notes(q, n)]
        only = [n for n in range(a, b + 1) if bool(self.notes(p, n)) != bool(self.notes(q, n))]
        if not both:
            return None, 0, both, only
        uni = octv = duet = rhy = 0
        for n in both:
            lp, lq = self.line(p, n), self.line(q, n)
            if lp == lq: uni += 1
            elif len(lp) == len(lq) and all(x[:2] == y[:2] and (x[2] - y[2]) % 12 == 0 for x, y in zip(lp, lq)): octv += 1
            elif self.rhythm(p, n) == self.rhythm(q, n):
                if self.words(p, n) == self.words(q, n): duet += 1
                else: rhy += 1
        k = len(both)
        if uni / k >= 0.8: return 'unison', uni / k, both, only
        if (uni + octv) / k >= 0.8: return 'octave', (uni + octv) / k, both, only
        if (uni + octv + duet) / k >= 0.75: return 'duet', (uni + octv + duet) / k, both, only
        if (uni + octv + duet + rhy) / k >= 0.75: return 'rhythm', (uni + octv + duet + rhy) / k, both, only
        return None, 0, both, only

    # ---------------------------------------------------------------- difficulty
    def rhythm_score(self, part, n):
        """syncopation / rhythmic trickiness of one bar: attacks off the beat, ties across a beat,
        16ths, dotted figures"""
        s = 0.0
        beat, compound = self.meter(n)
        for e in self.bars[part].get(n, []):
            if e['midi'] is None or e['tie_stop']: continue
            on = e['on']
            if compound:
                # the beat is a dotted quarter: 8ths on '&' and 'a' are its ordinary subdivision
                pos = on % beat
                if on.denominator >= 4: s += 1.5        # attack on a 16th
                elif pos:
                    s += 1.2 if (pos + e['dur'] > beat or e['tie_start']) else 0.4
                if e['tie_start'] and (on + e['dur']) % beat: s += 0.5
                if e['dur'].denominator >= 4: s += 0.3
                if e['dur'] in (F(3, 4), F(3, 8)): s += 0.6
                continue
            if on.denominator >= 4: s += 1.5            # attack on a 16th
            elif on.denominator == 2:
                # off-beat 8th: syncopated when it is held past the next beat
                end = on + e['dur']
                s += 1.2 if (e['dur'] >= 1 or e['tie_start']) else 0.4
            if e['tie_start'] and (on + e['dur']).denominator != 1: s += 0.5
            if e['dur'].denominator >= 4: s += 0.3
            if e['dur'] in (F(3, 4), F(3, 8)): s += 0.6
        return s

    def pitch_score(self, part, n):
        ns = [e['midi'] for e in self.notes(part, n)]
        s = 0.0
        for a, b in zip(ns, ns[1:]):
            if abs(a - b) >= 5: s += 0.5
            if abs(a - b) >= 8: s += 0.5
        return s + 0.15 * len(set(ns))

    # ---------------------------------------------------------------- sections
    def same_bar(self, p, a, b, words=True):
        x = (self.line(p, a), self.words(p, a) if words else None)
        y = (self.line(p, b), self.words(p, b) if words else None)
        return x == y


def shifted(line, t):
    return tuple((o, d, m + t, ts) for o, d, m, ts in line)


def compare(S, a, a2, n, parts=PARTS):
    """section at a vs earlier section at a2, n bars: best transposition, and per part the bars whose notes
    differ and the bars whose words differ"""
    best = None
    for t in range(-12, 13):
        dn = {p: [a + i for i in range(n) if S.line(p, a + i) != shifted(S.line(p, a2 + i), t)] for p in parts}
        k = sum(len(v) for v in dn.values())
        if best is None or k < best[0]: best = (k, t, dn)
    _, t, dn = best
    dw = {p: [a + i for i in range(n) if S.words(p, a + i) != S.words(p, a2 + i)] for p in parts}
    return t, dn, dw


def sections(S):
    L = sorted(S.letters.items())
    starts = ([(1, 'Intro')] if L[0][0] > 1 else []) + L
    return [(l, b, (starts[i + 1][0] - 1 if i + 1 < len(starts) else S.nbars)) for i, (b, l) in enumerate(starts)]


def coverage(S, a, b, parts=PARTS):
    """for each bar of a..b, per part: an earlier bar (before a) holding the same notes, found as runs of >= 2 bars
    that match at one transposition. Returns {part: {bar: (earlier bar, shift, same words)}}"""
    out = {p: {} for p in parts}
    for p in parts:
        lines = {n: S.line(p, n) for n in range(1, b + 1)}
        for m in range(1, a):
            for t in range(-3, 4):
                i = 0
                while a + i <= b:
                    j = i
                    while a + j <= b and m + j < a and lines[a + j] and lines[a + j] == shifted(lines[m + j], t):
                        j += 1
                    if j - i >= 2:
                        for k in range(i, j):
                            if a + k not in out[p]:
                                out[p][a + k] = (m + k, t, S.words(p, a + k) == S.words(p, m + k))
                        i = j
                    else:
                        i += 1
    return out


def bar_lengths(S):
    """{bar: length in quarters}: the time signature in force, or what a pickup bar actually holds"""
    out, ts = {}, (4, 4)
    for n in range(1, S.nbars + 1):
        ts = S.times.get(n, ts)
        full = F(4 * ts[0], ts[1])
        if n in S.implicit:
            ends = [e['on'] + e['dur'] for p in PARTS for e in S.bars[p].get(n, [])]
            out[n] = max(ends) if ends else full
        else:
            out[n] = full
    return out


def logic_positions(S):
    """{printed bar: (Logic bar, Logic beat)} for a Logic project left in the first time signature with the
    track's first downbeat on bar 1: 2/4 bars, meter changes and pickups shift Logic's bar numbers."""
    lens = bar_lengths(S)
    ts0 = S.times.get(1, (4, 4))
    beat = F(4, ts0[1])
    L0 = ts0[0] * beat
    out, t = {}, F(0)
    for n in range(1, S.nbars + 1):
        out[n] = (int(t // L0) + 1, t % L0 / beat + 1)
        t += lens[n]
    return out
