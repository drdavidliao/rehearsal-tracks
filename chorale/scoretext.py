"""The compact score-text notation, and the parser for it.

A score file is blocks of bars.  A block header names a line (or a pair of lines
sharing a staff); each following line is `bar number: tokens`.

    [SA]
    1: C4,E4q=Ev- C4,E4q=-ery- D4,F4e=-thing D4,F4e~ D4,F4h=here
    [S]
    2: G4q.=Ev- E4e=-ery- F4q(=-thing G4q)=here

A token is `pitches` `duration` `dot?` `tie?` `slur?` `=syllable?`:

    pitches     R for a rest, else one or more of A-G with optional #/b and an
                octave digit, comma separated: `D4`, `F#4`, `D4,F#4,A4`
    duration    w h q e s t  (whole … 32nd)
    dot         `.` — one dot
    tie         `~` — ties into the next event of the same line
    slur        `(` opens a slur, `)` closes one
    syllable    `=word`, `=word-` begins a word, `=-syl-` continues it,
                `=-syl` ends it.  No `=` means the note is held over — either
                tied or a melisma.

The full token, every part optional except the pitches (and the duration,
except after M):

    x? pitches duration dot? 3? ~? slur? {flags}? =syllable?

    x           x-notehead (spoken or shouted): `xE4e=hey`
    pitches     also H, a hidden rest (holds time, prints nothing), and M, a
                whole-bar rest, which takes no duration: `M`.  A tie on one pitch
                of a chord goes on that pitch: `Ab4~,C5q` ties the A-flat only.
    3           triplet member: `C5q3 C5q3 C5q3` fills two beats
    {flags}     comma-separated words for whatever the piece script draws:
                `G4q{marc}`, `Bb4q{doit,acc}`
    =syl_       a trailing `_` writes the extender line out (finalize() would
                derive it anyway)

A bar may hold two voices on one staff, separated by ` | `:

    12: C5h B4h | E4q F4q G4h

Lines outside the bars:

    @NAME = tokens      a macro; `@NAME` in any later bar expands to its tokens
    N: &T               bar N is the same as bar N of block [T]
    N: &24              bar N is the same as bar 24 of this block

Comments start with `#`; blank lines are ignored.  Nothing here is piece-specific.
"""
import copy
import re
from fractions import Fraction as F

from .events import DUR, check_bar, parse_pitch, pkey, pname

_PITCHES = r'[A-G][#b]?\d~?(?:,[A-G][#b]?\d~?)*'
_TOKEN = re.compile(r'(x?)(R|H|M|' + _PITCHES + r')([whqest]?)(\.?)(3?)(~?)([()]?)'
                    r'(?:\{([a-z0-9_,]+)\})?')


def parse_token(tok, beats=4):
    """One token -> one event.  `beats` is the bar length in quarters, which only M needs."""
    lyric = None
    if '=' in tok:
        tok, lyric = tok.split('=', 1)
    m = _TOKEN.fullmatch(tok)
    if not m:
        raise ValueError(f'not a token: {tok!r}')
    x, pitches, d, dot, trip, tie, slur, flags = m.groups()
    if (pitches == 'M') != (d == ''):
        raise ValueError(f'not a token: {tok!r} (every token but M needs a duration)')
    if pitches == 'M':
        dur, base, dots = F(beats), F(4), 0
    else:
        dots = 1 if dot else 0
        base = DUR[d]
        dur = base * (F(3, 2) if dot else 1) * (F(2, 3) if trip else 1)
    ev = {'dur': dur, 'base': base, 'dots': dots, 'tie': bool(tie),
          'slur_start': slur == '(', 'slur_stop': slur == ')', 'lyric': None,
          'x': bool(x), 'triplet': bool(trip), 'flags': set((flags or '').split(',')) - {''}}
    if pitches in ('R', 'H', 'M'):
        ev['pitches'] = []
        ev['hidden'] = pitches == 'H'
        ev['measure_rest'] = pitches == 'M'
    else:
        ps = []
        for p in pitches.split(','):
            q = parse_pitch(p.rstrip('~'))
            if p.endswith('~'):
                q['tie'] = True             # this pitch only; see link_ties
            ps.append(q)
        ev['pitches'] = sorted(ps, key=pkey)
    if lyric:
        ext = lyric.endswith('_') and len(lyric) > 1
        lyric = lyric[:-1] if ext else lyric
        syl, text = 'single', lyric
        if text.startswith('-') and text.endswith('-') and len(text) > 2:
            syl, text = 'middle', text[1:-1]
        elif text.startswith('-'):
            syl, text = 'end', text[1:]
        elif text.endswith('-') and len(text) > 1:
            syl, text = 'begin', text[:-1]
        ev['lyric'] = {'text': text, 'syllabic': syl}
        if ext:
            ev['lyric']['extend'] = True
    return ev


_MACRO = re.compile(r'(@[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)')


def read_raw(path):
    """-> ({block: {bar: text}}, {macro: tokens}): the file before any token is parsed."""
    raw, macros, cur = {}, {}, None
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            mm = _MACRO.fullmatch(line)
            if mm:
                macros[mm.group(1)] = mm.group(2).strip()
                continue
            if line.startswith('['):
                cur = line.strip('[]')
                raw.setdefault(cur, {})
                continue
            if cur is None:
                raise ValueError(f'{path}: bar line before any [block] header')
            num, rest = line.split(':', 1)
            raw[cur][int(num)] = rest.strip()
    return raw, macros


def bar_text(raw, macros, block, bar):
    """A bar's tokens with `&` references followed and macros expanded."""
    txt, seen = raw[block][bar], set()
    while txt.startswith('&'):
        ref = txt[1:].strip()
        key = (ref, bar) if not ref.isdigit() else (block, int(ref))
        if key in seen:
            raise ValueError(f'[{block}] bar {bar}: circular reference {txt!r}')
        seen.add(key)
        try:
            txt = raw[key[0]][key[1]]
        except KeyError:
            raise ValueError(f'[{block}] bar {bar}: {txt!r} names no bar') from None
        block = key[0]
    for k in sorted(macros, key=len, reverse=True):
        txt = re.sub(re.escape(k) + r'(?![A-Za-z0-9_])', lambda _m, v=macros[k]: v, txt)
    if '@' in txt:
        raise ValueError(f'bar {bar}: undefined macro in {txt!r}')
    return txt


def parse_score(path, voices=False, beats=4):
    """-> {block name: {bar number: [event, ...]}}

    With voices=True every bar is instead a list of voices, each a list of events,
    and a bar written with ` | ` has more than one.  Without it such a bar raises,
    so a caller that expects one line per block never silently drops a voice.
    `beats` (quarters in a bar) is what M fills.
    """
    raw, macros = read_raw(path)
    blocks = {}
    for b, bars in raw.items():
        blocks[b] = {}
        for m in bars:
            txt = bar_text(raw, macros, b, m)
            vs = [[parse_token(t, beats) for t in v.split()] for v in txt.split(' | ')]
            if voices:
                blocks[b][m] = vs
            elif len(vs) > 1:
                raise ValueError(f'[{b}] bar {m} has {len(vs)} voices: parse with voices=True')
            else:
                blocks[b][m] = vs[0]
    return blocks


def link_ties(seq):
    """Per-pitch ties along one voice: `seq` is its events in time order.

    A pitch is tied if its own `~` says so or the event's does; the tie closes on
    the same pitch in the next event, which gets `tie_stop` on that pitch.  Raises
    on a tie with nowhere to go."""
    prev = None
    for e in seq:
        for p in e['pitches']:
            p['tie_stop'] = bool(prev and any(
                pkey(q) == pkey(p) and (q.get('tie') or prev['tie']) for q in prev['pitches']))
        if prev:
            for q in prev['pitches']:
                if (q.get('tie') or prev['tie']) and not any(pkey(p) == pkey(q) for p in e['pitches']):
                    raise ValueError(f'tie from {pname(q)} has no continuation')
        prev = e
    return seq


def mark_tuplets(events):
    """Set e['tup'] = 'start' / 'stop' on the ends of each run of triplet members
    that fills one beat or two (three eighths, three quarters, six sixteenths...)."""
    run, acc = [], F(0)
    for e in events:
        if not e.get('triplet'):
            run, acc = [], F(0)
            continue
        run.append(e)
        acc += e['dur']
        if acc in (F(1), F(2)) and (acc == F(2) or e['base'] < 1 or len(run) == 3):
            run[0]['tup'] = 'start'
            if len(run) > 1:
                run[-1]['tup'] = 'stop'
            run, acc = [], F(0)
    return events


def split_line(events, which):
    """Pull one voice out of a block written as chords.

    `which` is 'top' or 'bottom'.  A single note belongs to both voices, which is
    how a score-text block writes a passage the two parts sing in unison.
    """
    out = []
    for ev in events:
        e = copy.deepcopy(ev)
        if e['pitches']:
            e['pitches'] = [e['pitches'][-1] if which == 'top' else e['pitches'][0]]
        out.append(e)
    return out


def make_line(nbars, block_shared, block_own=None, which='top', block_own2=None, beats=4):
    """Build one line, bar by bar, from up to three blocks.

    For each bar the first block that has it wins: block_own2, then block_own,
    then block_shared.  That is how a divisi bar or a bar where one part breaks
    away overrides the shared writing without repeating the rest of the piece.
    """
    block_own = block_own or {}
    block_own2 = block_own2 or {}
    line = {}
    for m in range(1, nbars + 1):
        src = block_own2.get(m) or block_own.get(m) or block_shared.get(m)
        if src is None:
            raise ValueError(f'bar {m} missing for {which}')
        check_bar(src, f'{which} bar {m}', beats)
        line[m] = split_line(src, which)
    return line


def raw_line(nbars, block_shared, block_own=None):
    """The same override rule, but keeping chords intact."""
    block_own = block_own or {}
    return {m: (block_own.get(m) or block_shared[m]) for m in range(1, nbars + 1)}


def single_line(nbars, block, tag, beats=4):
    """A block that is already one voice per line: copy it out and check it."""
    line = {}
    for m in range(1, nbars + 1):
        src = block.get(m)
        if src is None:
            raise ValueError(f'{tag}: bar {m} missing')
        check_bar(src, f'{tag} bar {m}', beats)
        for e in src:
            if len(e['pitches']) > 1:
                raise ValueError(f'{tag} bar {m}: chord in a single-voice line')
        line[m] = copy.deepcopy(src)
    return line
