"""Draft a note/rhythm-learning lesson plan from a SATB MusicXML, following the director's teaching habits."""
import itertools
import re
from fractions import Fraction as F
from . import analyze
from .analyze import PARTS

ABBR = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}
PL = {'Soprano': 'sopranos', 'Alto': 'altos', 'Tenor': 'tenors', 'Bass': 'basses'}


def who(parts):
    ns = [PL[p] for p in parts]
    if len(ns) == 4: return 'everyone'
    return ns[0] if len(ns) == 1 else ', '.join(ns[:-1]) + ' and ' + ns[-1]


def bars_said(a, b):
    return f"bar {a}" if a == b else f"bars {a} to {b}"


def lname(l):
    return 'the intro' if l == 'Intro' else f'letter {l}'


def Cap(t):
    return t[0].upper() + t[1:]


def mrange(a, b):
    return f"m{a}" if a == b else f"m{a}–{b}"


def runs(ns):
    out = []
    for n in ns:
        if out and out[-1][1] == n - 1: out[-1][1] = n
        else: out.append([n, n])
    return [tuple(r) for r in out]


def beat_str(on):
    b = 1 + on
    if b.denominator == 1: return str(b.numerator)
    whole = b.numerator // b.denominator
    frac = b - whole
    return f"{whole}{ {F(1,2):'½', F(1,4):'¼', F(3,4):'¾'}.get(frac, '+' + str(frac)) }"


class Planner:
    def __init__(self, S, rhythm_threshold, easy_threshold, hard_threshold, rhythm_mode='drill'):
        # 'drill': slow spoken rhythm work on the bars; 'slow': play and sing the passage down tempo first
        self.mode = rhythm_mode
        self.S = S
        self.secs = analyze.sections(S)
        self.rth, self.easy, self.hard = rhythm_threshold, easy_threshold, hard_threshold
        self.lead = {p: 0 for p in PARTS}
        self.last_lead = None
        self.rhythm_done = set()     # (part, bar-shape) already drilled
        self.flagged = {}            # bar -> parts whose rhythm there is tricky (the score marks their beats)

    # -------------------------------------------------------------- where a passage really starts
    def pickup(self, a):
        """a phrase that starts in the bar before `a`: (bar, onset) of its first note, or None"""
        if a <= 1: return None
        best = None
        for p in PARTS:
            evs = self.S.bars[p].get(a - 1, [])
            # trailing notes after the bar's last rest, if they lead straight into bar a
            tail = []
            for e in reversed(evs):
                if e['midi'] is None: break
                tail.append(e)
            if not tail or len(tail) == len(evs): continue
            first = tail[-1]
            if first['on'] >= 2 and first['lyric']:
                if best is None or first['on'] < best: best = first['on']
        return (a - 1, best) if best is not None else None

    def cue(self, a):
        """(printed bar to start from, pickup beat or None, where that is in Logic: 'bar' or 'bar beat')"""
        if not hasattr(self, '_logic'):
            self._logic = analyze.logic_positions(self.S)
        pu = self.pickup(a)
        bar = pu[0] if pu else a
        lb, lbeat = self._logic[bar]
        logic = f"{lb}" if lbeat == 1 else f"{lb} {beat_str(lbeat - 1)}"
        return (bar, beat_str(pu[1]) if pu else None, logic)

    # -------------------------------------------------------------- per part difficulty
    def difficulty(self, p, a, b):
        sung = [n for n in range(a, b + 1) if self.S.notes(p, n)]
        if not sung: return 0
        return sum(self.S.rhythm_score(p, n) + self.S.pitch_score(p, n) for n in sung) / len(sung)

    def groups(self, a, b):
        act = [p for p in PARTS if self.S.sings(p, a, b)]
        parent = {p: p for p in act}
        def find(p):
            while parent[p] != p: p = parent[p]
            return p
        rel = {}
        for p, q in itertools.combinations(act, 2):
            r, f, both, only = self.S.relation(p, q, a, b)
            rel[(p, q)] = r
            # parts sing together when they share the notes (unison or octaves) and neither sings much alone
            if r in ('unison', 'octave') and len(only) <= 1:
                parent[find(q)] = find(p)
        gs = {}
        for p in act: gs.setdefault(find(p), []).append(p)
        return list(gs.values()), rel

    def rhythm_spots(self, p, a, b):
        """runs of bars in this passage that need slow rhythm work for part p, first time only"""
        spots = []
        for n in range(a, b + 1):
            if self.S.rhythm_score(p, n) >= self.rth:
                shape = self.S.rhythm(p, n)
                if (p, shape) in self.rhythm_done: continue
                self.rhythm_done.add((p, shape))
                if spots and spots[-1][1] == n - 1: spots[-1][1] = n
                else: spots.append([n, n])
        return spots

    def split_point(self, a, b):
        """a bar line near the middle where most parts breathe"""
        mid = (a + b + 1) / 2
        best = None
        L = b - a + 1
        lo, hi = a + max(3, L // 3), b - max(2, L // 3) + 1
        for n in range(lo, hi + 1):
            # parts with a rest at the end of bar n-1 or start of bar n
            breathe = 0
            for p in PARTS:
                e1 = self.S.bars[p].get(n - 1, [])
                e2 = self.S.bars[p].get(n, [])
                if (e1 and e1[-1]['midi'] is None) or (e2 and e2[0]['midi'] is None): breathe += 1
                elif e2 and e2[0]['tie_stop']: breathe -= 1
            score = breathe - 1.2 * abs(n - mid)
            if best is None or score > best[0]: best = (score, n)
        return best[1] if best else None

    # -------------------------------------------------------------- ordering
    def order(self, groups):
        """rotate who goes first: never the part(s) that led the last section, fewest leads first"""
        def key(g):
            return (any(p == self.last_lead for p in g), min(self.lead[p] for p in g), PARTS.index(g[0]))
        gs = sorted(groups, key=key)
        if gs:
            self.lead[gs[0][0]] += 1
            self.last_lead = gs[0][0]
        return gs

    # -------------------------------------------------------------- plan one passage from scratch
    def rhythm_plan(self, a, b, parts):
        """rhythm spots in a..b: joint ones (several parts, same rhythm, same bars) and per part"""
        spots = {p: set() for p in parts}
        for p in parts:
            for s0, s1 in self.rhythm_spots(p, a, b):
                spots[p] |= set(range(s0, s1 + 1))
        joint = []   # [(bars, parts)]
        for n in range(a, b + 1):
            have = [p for p in parts if n in spots[p]]
            if not have: continue
            # every singing part with the same rhythm in this bar joins the drill, flagged or not:
            # one spoken run-through for all of them replaces a drill inside each part's turn
            byr = {}
            for p in parts:
                if self.S.notes(p, n): byr.setdefault(self.S.rhythm(p, n), []).append(p)
            byr = {r: sorted(ps, key=PARTS.index) for r, ps in byr.items()}
            for r, ps in byr.items():
                if len(ps) >= 2 and any(p in have for p in ps):
                    self.flagged.setdefault(n, set()).update(ps)
                    for p in ps: self.rhythm_done.add((p, r))
                    for p in ps: spots[p].discard(n)
                    if joint and joint[-1][0][-1] == n - 1 and joint[-1][1] == ps: joint[-1][0].append(n)
                    else: joint.append(([n], ps))
        for q, bars in spots.items():
            for n in bars: self.flagged.setdefault(n, set()).add(q)
        if self.mode == 'slow' and joint:
            # shared tricky bars: learn the notes part by part, then everyone sings it down tempo together
            self.slow_all = True
            joint = []
        per = {p: runs(sorted(v)) for p, v in spots.items()}
        return joint, per

    def teach(self, a, b, items, parts=None, micro=False):
        groups, rel = self.groups(a, b)
        if parts is not None:
            groups = [g for g in ([p for p in g if p in parts] for g in groups) if g]
        gs = self.order(groups)
        joint, per = self.rhythm_plan(a, b, [p for g in gs for p in g])
        for bars, ps in joint:
            items.append(dict(kind='rhythm', bar=bars[0], bar_end=bars[-1], parts=ps, text=f"Rhythm work {mrange(bars[0], bars[-1])}, slowly: "
                              + ('everyone' if len(ps) == 4 else '+'.join(ps)) + ' (same rhythm; speak it together)', cue=self.cue(bars[0]),
                              say=(f"Let's take {bars_said(bars[0], bars[-1])} slowly together first." if len(ps) == 4 else f"{Cap(who(ps))}, let's take {bars_said(bars[0], bars[-1])} slowly together first.")))
        taught = []
        for g in gs:
            name = '+'.join(g)
            d = max(self.difficulty(p, a, b) for p in g)
            partner = None
            for t in taught:
                for p in g:
                    for q in t:
                        r = rel.get((p, q)) or rel.get((q, p))
                        if r in ('duet', 'unison', 'octave') and partner is None: partner = (q, r)
                        elif r == 'rhythm' and partner is None: partner = (q, r)
            easy = not micro and (d <= self.easy or (partner is not None and d <= self.hard))
            spots = []
            for p in g:
                for sp in per.get(p, []):
                    if sp not in spots: spots.append(sp)
            note = ''
            if len(g) > 1:
                rs = {rel.get((p, q)) or rel.get((q, p)) for p, q in itertools.combinations(g, 2)}
                note = 'in octaves' if 'octave' in rs else 'in unison'
            elif partner:
                note = {'duet': f'same rhythm and words as {partner[0]}', 'rhythm': f'same rhythm as {partner[0]}',
                        'unison': f'same notes as {partner[0]}', 'octave': f"{partner[0]}'s line in octaves"}[partner[1]]
            if spots and self.mode == 'slow':
                sub = [('Play 1x slow, listen', None), ('Play 1x slow, sing', None), ('Play 1x, sing', None)]
            else:
                sub = [('Play 1x, listen', None)]
                for s0, s1 in spots:
                    sub.append((f"Rhythm work {mrange(s0, s1)}, slowly", self.cue(s0)))
                sub.append(('Play 1x, sing' if easy else 'Play 2x, sing', None))
            if len(g) > 1:
                say = f"{Cap(who(g))}, you're singing the same line{' an octave apart' if note == 'in octaves' else ''}, so we'll learn it together."
            else:
                say = None
            if spots and not say and self.mode == 'slow':
                say = f"{Cap(who(g))}, we'll take it down tempo first, then up to speed."
            elif spots and not say:
                say = f"{Cap(who(g))}, listen first; then we'll slow down {bars_said(*spots[0])}."
            items.append(dict(kind='part', who=name, note=note, sub=sub, say=say, bar=a, parts=list(g)))
            taught.append(g)
        return gs

    def why(self, r0, r1, a, src, srcname, parts):
        """what changed in bars r0..r1 against the same bars of the earlier letter, per part:
        'm46 ≠ m25 (C): altos, tenors new notes'"""
        off = src[0] - a
        kinds = {}
        for p in parts:
            ks = set()
            for n in range(r0, r1 + 1):
                m = n + off
                if self.S.rhythm(p, n) != self.S.rhythm(p, m): ks.add('rhythm')
                if [x[2] for x in self.S.line(p, n)] != [x[2] + src[1] for x in self.S.line(p, m)]: ks.add('notes')
                if self.S.words(p, n) != self.S.words(p, m): ks.add('words')
            ks = sorted(ks, key=['notes', 'rhythm', 'words'].index)
            k = ('new ' + (', '.join(ks[:-1]) + ' and ' + ks[-1] if len(ks) > 1 else ks[0])) if ks else 'changed'
            kinds.setdefault(k, []).append(p)
        where = f"{mrange(r0, r1)} ≠ {mrange(r0 + off, r1 + off)} ({srcname[0]})"
        return where + ': ' + '; '.join(f"{who(ps)} {k}" for k, ps in kinds.items())

    def texture(self, a, b):
        act = [p for p in PARTS if self.S.sings(p, a, b)]
        rel = {}
        for p, q in itertools.combinations(act, 2):
            rel[(p, q)] = self.S.relation(p, q, a, b)[0]
        if len(act) == 4 and all(r in ('duet', 'unison', 'octave') for r in rel.values()):
            return 'All four sing the same rhythm and words (block chords).'
        bits = []
        for (p, q), r in rel.items():
            if r == 'unison': bits.append(f"{ABBR[p]}+{ABBR[q]} in unison")
            elif r == 'octave': bits.append(f"{ABBR[p]}+{ABBR[q]} in octaves")
            elif r == 'duet': bits.append(f"{ABBR[p]}+{ABBR[q]} same rhythm and words")
            elif r == 'rhythm': bits.append(f"{ABBR[p]}+{ABBR[q]} same rhythm")
        return ('; '.join(bits) + '.') if bits else 'All four parts move independently.'

    def plan(self):
        out = []
        for l, a, b in self.secs:
            sung = any(self.S.sings(p, a, b) for p in PARTS)
            only_pickup = all(not self.S.notes(p, n) for p in PARTS for n in range(a, b))
            sec = dict(letter=l, a=a, b=b, cue=self.cue(a), items=[], notes=[])
            out.append(sec)
            if not sung or only_pickup:
                sec['kind'] = 'skip'
                sec['notes'].append('Piano only; the voices come in on the pickup to the next letter.' if sung else 'Piano only.')
                continue
            cov = analyze.coverage(self.S, a, b)
            sungbars = {p: [n for n in range(a, b + 1) if self.S.notes(p, n)] for p in PARTS}
            new = {p: [n for n in sungbars[p] if n not in cov[p]] for p in PARTS}
            allnew = sorted({n for v in new.values() for n in v})
            nsung = len({n for v in sungbars.values() for n in v})
            srcs = {}
            for p in PARTS:
                for n, (m, t, w) in cov[p].items():
                    k = (m - (n - a), t); srcs[k] = srcs.get(k, 0) + 1
            src = max(srcs, key=lambda k: (srcs[k], k[0])) if srcs else None
            if src and not allnew:
                for l2, a2, b2 in reversed(self.secs):
                    if a2 >= a or b2 - a2 != b - a: continue
                    t, dn, dw = analyze.compare(self.S, a, a2, b - a + 1)
                    if not any(dn.values()):
                        src = (a2, t); break
            srcname = None
            if src:
                for l2, a2, b2 in self.secs:
                    if a2 <= src[0] <= b2: srcname = (l2, a2)
            if not allnew and srcname:
                sec['kind'] = 'repeat'
                t, dn, dw = analyze.compare(self.S, a, src[0], b - a + 1)
                wordsdiff = sorted({n for v in dw.values() for n in v})
                key = {0: '', 1: ', a half step higher', 2: ', a whole step higher', -1: ', a half step lower',
                       -2: ', a whole step lower'}.get(src[1], f', {src[1]:+d} semitones')
                note = f"Same notes as {srcname[0]} (m{srcname[1]}){key}"
                if wordsdiff: note += f"; different words in {mrange(wordsdiff[0], wordsdiff[-1])}"
                sec['notes'].append(note + '.')
                keysay = {1: ', just a half step higher', 2: ', just a whole step higher', -1: ', just a half step lower', -2: ', just a whole step lower'}.get(src[1], '')
                sec['say'] = (f"Letter {l} is the same as letter {srcname[0]}{keysay}"
                              + (", with different words" if wordsdiff else '')
                              + (". Here are your starting notes. Let's" if src[1] else ", so let's") + " sing it together just once.")
                sec['items'].append(dict(kind='all', bar=a, text='Everyone: play 1x, sing' + (' (new key: give the starting pitches)' if src[1] else ''), cue=sec['cue']))
                continue
            if srcname and len(allnew) <= max(1, nsung // 3) and len(allnew) < nsung / 2:
                sec['kind'] = 'near'
                sec['notes'].append(f"Like {srcname[0]} (m{srcname[1]}) except {mrange(allnew[0], allnew[-1])}.")
                chg = [p for p in PARTS if new[p]]
                sec['say'] = (f"Letter {l} is almost the same as letter {srcname[0]}. Only {bars_said(allnew[0], allnew[-1])} "
                              f"{'is' if allnew[0] == allnew[-1] else 'are'} different"
                              + ('' if len(chg) == 4 else f", and only for the {who(chg)}")
                              + f". We'll learn just that, then sing {l} together from the top.")
                for r0, r1 in runs(allnew):
                    s0 = max(a, r0 - 1)            # a bar of run-up, inside the letter
                    changed = [p for p in PARTS if any(r0 <= n <= r1 for n in new[p])]
                    blk = dict(kind='block', bar=s0, text=f"{mrange(s0, r1)}: the bars that differ", cue=self.cue(s0), items=[])
                    blk['why'] = self.why(r0, r1, a, src, srcname, changed)
                    self.teach(s0, r1, blk['items'], parts=changed, micro=True)
                    sec['items'].append(blk)
                sec['items'].append(dict(kind='all', bar=a, text=f"Everyone from the top of {l}: play 1x, sing", cue=sec['cue']))
                continue
            sec['kind'] = 'new'
            sec['notes'].append(self.texture(a, b))
            tx = sec['notes'][0]
            doubled = [b_ for b_ in tx.rstrip('.').split('; ') if b_.endswith('in unison') or b_.endswith('in octaves')]
            if doubled:
                full = {v: k for k, v in ABBR.items()}
                sec['say'] = f"In {lname(l)}, " + '; '.join(
                    f"the {who([full[c] for c in b_.split(' ')[0].split('+')])} sing "
                    + ('in unison' if b_.endswith('in unison') else 'the same line in octaves') for b_ in doubled) + '.'
            # a section taught in full needs no remarks on what resembles earlier material
            dmax = max(self.difficulty(p, a, b) for p in PARTS)
            long_ = ((b - a + 1) >= 10 and dmax > self.easy) or ((b - a + 1) >= 8 and dmax > self.hard)
            if long_:
                c = self.split_point(a, b)
                halves = [(a, c - 1), (c, b)]
                sec['notes'].append(f"Long or hard: taught in halves, {mrange(a, c - 1)} and {mrange(c, b)}.")
                sec['say'] = sec.get('say', '') + (f" This one is {'long' if b - a + 1 >= 10 else 'tricky'}, so we'll hear each part whole, then learn it in two halves: "
                                                   f"{bars_said(a, c - 1)}, then {bars_said(c, b)}.")
                groups, rel = self.groups(a, b)
                gs = self.order(groups)
                allp = [p for g in gs for p in g]
                hj = {h: self.rhythm_plan(h[0], h[1], allp) for h in halves}
                for h in halves:
                    for bars, ps in hj[h][0]:
                        sec['items'].append(dict(kind='rhythm', bar=bars[0], bar_end=bars[-1], parts=ps, text=f"Rhythm work {mrange(bars[0], bars[-1])}, slowly: "
                                                 + ('everyone' if len(ps) == 4 else '+'.join(ps)) + ' (same rhythm; speak it together)', cue=self.cue(bars[0]),
                                                 say=(f"Let's take {bars_said(bars[0], bars[-1])} slowly together first." if len(ps) == 4 else f"{Cap(who(ps))}, let's take {bars_said(bars[0], bars[-1])} slowly together first.")))
                for g in gs:
                    sub = [('Play whole section 1x, listen', sec['cue'])]
                    for h in halves:
                        if all(n in cov[p] for p in g for n in range(h[0], h[1] + 1) if self.S.notes(p, n)):
                            m0 = cov[g[0]].get(h[0], (None,))[0]
                            sub.append((f"{mrange(*h)}: play 1x, sing (already sung" + (f" at m{m0})" if m0 else ")"), self.cue(h[0])))
                            continue
                        hs = [s_ for p in g for s_ in hj[h][1].get(p, [])]
                        if hs and self.mode == 'slow':
                            sub.append((f"{mrange(*h)}: play 1x slow, listen", self.cue(h[0])))
                            sub.append((f"{mrange(*h)}: play 1x slow, sing", None))
                            sub.append((f"{mrange(*h)}: play 1x, sing", None))
                            continue
                        sub.append((f"{mrange(*h)}: play 1x, listen", self.cue(h[0])))
                        for p in g:
                            for s0, s1 in hj[h][1].get(p, []):
                                sub.append((f"Rhythm work {mrange(s0, s1)}, slowly", self.cue(s0)))
                        sub.append((f"{mrange(*h)}: play 2x, sing", None))
                    sec['items'].append(dict(kind='part', who='+'.join(g), note='in unison' if len(g) > 1 else '', sub=sub, bar=a, parts=list(g), split=c))
            else:
                self.teach(a, b, sec['items'])
            if getattr(self, 'slow_all', False):
                sec['items'].append(dict(kind='all', slow=True, bar=a, text=f"Everyone: play 1x slow, sing; then 1x at tempo, sing {l}", cue=sec['cue'],
                                         say=f"Now everyone together, all of {lname(l)}: once down tempo, then up to speed."))
            else:
                sec['items'].append(dict(kind='all', bar=a, text=f"Everyone: play 1x, sing {l}", cue=sec['cue'],
                                         say=f"Now everyone together, all of {lname(l)}."))
            self.slow_all = False
        return out


def cuestr(c):
    if not c: return ''
    return f"/{c[2] if len(c) > 2 else c[0]}" + (f"  (in on beat {c[1]})" if c[1] else '')


def dump(plan):
    for s in plan:
        print(f"[ ] {s['letter']}  {mrange(s['a'], s['b'])}  {cuestr(s['cue'])}  ({s.get('kind')})")
        for n in s['notes']: print('      * ' + n)
        for it in s['items']:
            if it['kind'] == 'part':
                print(f"    [ ] {it['who']}" + (f"  ({it['note']})" if it['note'] else ''))
                for t, c in it['sub']: print(f"        [ ] {t}  {cuestr(c)}")
            elif it['kind'] == 'block':
                print(f"    [ ] {it['text']}  {cuestr(it['cue'])}")
                for jt in it['items']:
                    if jt['kind'] == 'part':
                        print(f"        [ ] {jt['who']}" + (f"  ({jt['note']})" if jt['note'] else ''))
                        for t, c in jt['sub']: print(f"            [ ] {t}  {cuestr(c)}")
                    else: print(f"        [ ] {jt['text']}  {cuestr(jt.get('cue'))}")
            else:
                print(f"    [ ] {it['text']}  {cuestr(it.get('cue'))}")


def number_steps(plan):
    """label every step in the order it is done: letter + running number (A1, A2 ...). Returns flat steps."""
    steps = []
    for sec in plan:
        k = 0
        def lab(it):
            nonlocal k
            k += 1
            it['label'] = f"{sec['letter'] if sec['letter'] != 'Intro' else 'In'}{k}"
            it['sec'] = sec
            steps.append(it)
        for it in sec['items']:
            if it['kind'] == 'block':
                for jt in it['items']:
                    lab(jt)
            else:
                lab(it)
    return steps


def notation(it, cues=False):
    """a step in shorthand: P = play (they listen), S = play and they sing, R = slow rhythm work on the bars given.
    With cues=True, returns [(text, cue)] segments so a checklist can print the Logic cue for each start."""
    if it['kind'] == 'all':
        t = 'all S↓+S' if it.get('slow') else 'all S'
        return [(t, None)] if cues else t
    if it['kind'] == 'rhythm':
        t = 'Rh m' + (f"{it['bar']}" if it['bar'] == it['bar_end'] else f"{it['bar']}–{it['bar_end']}") + ', spoken together'
        return [(t, None)] if cues else t
    segs = [['', None, []]]
    for t, c in it['sub']:
        m = re.match(r'm([\d–]+): ', t)
        if m and segs[-1][0] != 'm' + m.group(1):
            segs.append(['m' + m.group(1), c, []])
        if t.startswith('Rhythm'):
            tok = 'Rh m' + re.search(r'm([\d–]+)', t).group(1)
        elif 'already sung' in t:
            tok = 'S(known)'
        elif 'listen' in t:
            tok = 'P↓' if 'slow' in t else 'P'
        else:
            mm = re.search(r'(\d)x( slow)?, sing', t)
            tok = ('S↓' if mm.group(2) else 'S') * int(mm.group(1)) if mm else t
        segs[-1][2].append(tok)
    out = [((h + ' ' if h else '') + '+'.join(toks), c) for h, c, toks in segs if toks]
    return out if cues else ' · '.join(s_ for s_, _ in out)


def caption(it):
    """the badge's note: the shorthand, with a split section's halves left to the dashed line on the score"""
    t = notation(it).replace(', slowly', '')
    if it.get('split'):
        segs = t.split(' · ')
        t = segs[0] + ' · halves: ' + ', '.join(s_.split(' ', 1)[1] for s_ in segs[1:])
    return t


def _old_caption(it):
    """short play count for a badge: '1 listen · 2 sing'"""
    if it['kind'] == 'all': return 'all · sing 1x'
    if it['kind'] == 'rhythm': return 'rhythm, slowly'
    if it.get('split'):
        return f"whole · halves m{it['split']}"
    lis = sum(1 for t, c in it['sub'] if t.endswith('listen'))
    sing = sum(int(t.split('Play ')[1][0]) if t.startswith('Play ') and 'sing' in t else 0 for t, c in it['sub'])
    r = any(t.startswith('Rhythm') for t, c in it['sub'])
    return f"listen {lis} · sing {sing}" + (' · rhythm' if r else '')
