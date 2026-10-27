"""Read a choral MusicXML (SATB, or any one-staff voices such as S A1 A2 T B; a piano is ignored) into per-part,
per-bar note lists and compare parts and sections."""
import xml.etree.ElementTree as ET
from fractions import Fraction as F
from collections import defaultdict

STEPS = 'CDEFGAB'
VOICES = ('Soprano', 'Alto', 'Tenor', 'Baritone', 'Bass')
# the sung parts, top to bottom as the score lists them. Score() fills it in place, so every module that imported
# it sees the piece's parts: Soprano, Alto, Tenor, Bass by default; Soprano, Alto 1, Alto 2, Tenor, Bass for an SAATB
PARTS = ['Soprano', 'Alto', 'Tenor', 'Bass']
# Okabe-Ito, as score_video.py: a second part of the same voice (Alto 2) takes reddish purple
COLOUR = {'Soprano': '#D55E00', 'Alto': '#B8860B', 'Tenor': '#009E73', 'Baritone': '#56B4E9', 'Bass': '#0072B2'}
SECOND = '#CC79A7'
EVERYONE = '#7B3FA0'


def voice(name):
    return next((v for v in VOICES if name.startswith(v)), None)


def colour(p):
    same = [q for q in PARTS if voice(q) == voice(p)]
    return SECOND if p in same[1:] else COLOUR.get(voice(p), EVERYONE)


def abbr(p):
    """S, A, T, B; a numbered part keeps its name (Alto 1): A1 is a step label on the score"""
    return p if p != voice(p) else p[0]


def plural(p):
    v = voice(p)
    base = {'Soprano': 'sopranos', 'Alto': 'altos', 'Tenor': 'tenors', 'Baritone': 'baritones', 'Bass': 'basses'}.get(v, p.lower() + 's')
    return base if p == v else p.lower() + 's'      # 'alto 1s'


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
        sung = [names[p.get('id')] for p in root.findall('part') if voice(names[p.get('id')])]
        PARTS[:] = sung
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
                    elif e.tag == 'direction' and nm == PARTS[0]:
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
                                        syl=(ly.findtext('syllabic') if ly is not None else None),
                                        x=e.find('notehead') is not None))
                        t += d
                bars[n] = evs
            self.bars[nm] = bars
        self.nbars = max(self.bars[PARTS[0]])
        # A letter runs from phrase to phrase, which is not always barline to barline. Notes at the end of a letter's
        # last bar that start the next letter's phrase (phrase_tail) belong to the next letter, and that bar is compared
        # only up to where they start (cut). Notes held over into a letter's first bar from the phrase before, up to a
        # rest, belong to the letter before (lo, per part). Both are left out when a letter is compared with another.
        self.cut = {}            # letter's last bar -> onset where the next letter's phrase starts
        self.lo = {}             # (part, letter's first bar) -> onset where the part's held-over note ends
        for n in sorted(self.letters):
            ons = []
            for p in self.bars:
                tail = self.phrase_tail(p, n - 1)
                for e in tail: e['lead_in'] = True
                if tail: ons.append(tail[0]['on'])
                spill, end = [], None
                for e in self.bars[p].get(n, []):
                    if e['midi'] is None:
                        end = e['on']; break
                    if e['tie_stop'] or (spill and not e['lyric']): spill.append(e)    # tied over, or its melisma
                    else: break
                if spill and end is not None:
                    for e in spill: e['lead_out'] = True
                    self.lo[(p, n)] = end
            if ons: self.cut[n - 1] = min(ons)

    def phrase_tail(self, p, n):
        """the notes at the end of bar n that start a new phrase leading into bar n+1, or []: from beat 3 on (the
        second half of a compound bar), with words, after a rest, or straight after a word that ends a phrase
        ('long.' then 'ding' with no rest between)"""
        evs = self.bars[p].get(n, [])
        tail = []
        for e in reversed(evs):
            if e['midi'] is None: break
            tail.append(e)
        tail.reverse()
        if tail and len(tail) < len(evs) and tail[0]['on'] >= self.pickup_from(n) and tail[0]['lyric']:
            return tail
        # no rest: the first note from beat 3 on that begins a word, when the syllable sung before it ends a phrase
        for i, e in enumerate(evs):
            if e['midi'] is None or e['on'] < self.pickup_from(n) or not e['lyric'] or e['tie_stop']: continue
            if (e.get('syl') or 'single') not in ('single', 'begin'): continue
            prev = self.last_syllable(p, n, e['on'])
            if prev and prev.rstrip()[-1:] in '.,;:!?' and all(x['midi'] is not None for x in evs[i:]):
                return evs[i:]
            break
        return []

    def last_syllable(self, p, n, on):
        for m in range(n, max(0, n - 8), -1):
            for e in reversed(self.bars[p].get(m, [])):
                if m == n and e['on'] >= on: continue
                if e['lyric']: return e['lyric']
        return None

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
    def rhythm(self, part, n, like=None):
        """attack points (not tie continuations) and rests"""
        return tuple((e['on'], e['dur'] if not e['tie_start'] else None) for e in self.own(part, n, like)
                     if e['midi'] is not None and not e['tie_stop'])

    def line(self, part, n, like=None):
        return tuple((e['on'], e['dur'], e['midi'], e['tie_stop']) for e in self.own(part, n, like) if e['midi'] is not None)

    def words(self, part, n, like=None):
        return tuple(e['lyric'] for e in self.own(part, n, like) if e['lyric'])

    def window(self, part, n):
        """the part of bar n that belongs to its own letter: (from, to) in quarters"""
        return self.lo.get((part, n), F(0)), self.cut.get(n)

    def own(self, part, n, like=None):
        """bar n's events that belong to its letter: without a lead-in to the next letter or a note held over from
        the letter before. With `like`, cut to the window of bar `like` instead, so an earlier bar is compared with a
        bar of this letter over the same stretch; a note running past the window's end is cut at it"""
        lo, hi = self.window(part, like if like is not None else n)
        out = []
        for e in self.bars[part].get(n, []):
            if e.get('lead_in') or e.get('lead_out') or e['on'] < lo or (hi is not None and e['on'] >= hi): continue
            if hi is not None and e['on'] + e['dur'] > hi:
                e = dict(e, dur=hi - e['on'], tie_start=False)
            out.append(e)
        return out

    def release_only(self, part, n, m, t=0):
        """bar n against earlier bar m (t semitones away): when they differ only in how long a note is held before a
        rest (the same attacks, pitches and words), the notes that differ as [(onset, syllable, (tied lengths, rest
        after) in n, the same in m, last note of the bar?)]; otherwise None"""
        a, b = self.own(part, n), self.own(part, m, like=n)
        if self.line(part, n) == self.line(part, m, like=n): return None
        att = lambda evs, k: [(e['on'], e['midi'] + k) for e in evs if e['midi'] is not None and not e['tie_stop']]
        if att(a, 0) != att(b, t) or self.words(part, n) != self.words(part, m, like=n): return None
        def held(evs):
            # {onset: ([printed lengths of the note and the notes tied to it], length of the rest after it)} for each
            # note attacked in the bar
            out, last, rest = {}, None, False
            for e in evs:
                if e['midi'] is None:
                    if last is not None: out[last][1] += e['dur']
                    rest = True
                elif e['tie_stop'] and last is not None and not rest: out[last][0].append(e['dur'])
                else: last, rest = e['on'], False; out[last] = [[e['dur']], F(0)]
            return out
        ha, hb = held(a), held(b)
        diff = []
        for i, on in enumerate(sorted(ha)):
            if on not in hb or sum(ha[on][0]) == sum(hb[on][0]): continue
            e = next(x for x in a if x['on'] == on)
            word = e['lyric'] or self.last_syllable(part, n, on + F(1, 64))
            diff.append((on, word, ha[on], hb[on], i == len(ha) - 1))
        return diff or None

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
        dn = {p: [a + i for i in range(n) if S.line(p, a + i) != shifted(S.line(p, a2 + i, like=a + i), t)] for p in parts}
        k = sum(len(v) for v in dn.values())
        if best is None or k < best[0]: best = (k, t, dn)
    _, t, dn = best
    dw = {p: [a + i for i in range(n) if S.words(p, a + i) != S.words(p, a2 + i, like=a + i)] for p in parts}
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
        # each earlier bar is seen over the stretch of the bar it is compared with (a letter's last bar ends where
        # the next letter's phrase starts)
        lines = {n: S.line(p, n) for n in range(a, b + 1)}
        like = lambda n, x: S.line(p, n, like=x)
        for m in range(1, a):
            for t in range(-3, 4):
                i = 0
                while a + i <= b:
                    j = i
                    while a + j <= b and m + j < a and lines[a + j] and lines[a + j] == shifted(like(m + j, a + j), t):
                        j += 1
                    if j - i >= 2:
                        for k in range(i, j):
                            if a + k not in out[p]:
                                out[p][a + k] = (m + k, t, S.words(p, a + k) == S.words(p, m + k, like=a + k))
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
