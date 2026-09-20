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

Comments start with `#`; blank lines are ignored.  Nothing here is piece-specific.
"""
import copy
import re
from fractions import Fraction as F

from .events import DUR, check_bar, parse_pitch, pkey

_TOKEN = re.compile(r'(R|[A-G][#b]?\d(?:,[A-G][#b]?\d)*)([whqest])(\.?)(~?)([()]?)')


def parse_token(tok):
    lyric = None
    if '=' in tok:
        tok, lyric = tok.split('=', 1)
    m = _TOKEN.fullmatch(tok)
    if not m:
        raise ValueError(f'not a token: {tok!r}')
    pitches, d, dot, tie, slur = m.groups()
    dur = DUR[d] * (F(3, 2) if dot else 1)
    ev = {'dur': dur, 'base': DUR[d], 'dots': 1 if dot else 0, 'tie': bool(tie),
          'slur_start': slur == '(', 'slur_stop': slur == ')', 'lyric': None}
    ev['pitches'] = [] if pitches == 'R' else sorted(
        (parse_pitch(p) for p in pitches.split(',')), key=pkey)
    if lyric:
        syl, text = 'single', lyric
        if text.startswith('-') and text.endswith('-') and len(text) > 2:
            syl, text = 'middle', text[1:-1]
        elif text.startswith('-'):
            syl, text = 'end', text[1:]
        elif text.endswith('-') and len(text) > 1:
            syl, text = 'begin', text[:-1]
        ev['lyric'] = {'text': text, 'syllabic': syl}
    return ev


def parse_score(path):
    """-> {block name: {bar number: [event, ...]}}"""
    blocks, cur = {}, None
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('['):
                cur = line.strip('[]')
                blocks[cur] = {}
                continue
            if cur is None:
                raise ValueError(f'{path}: bar line before any [block] header')
            num, rest = line.split(':', 1)
            blocks[cur][int(num)] = [parse_token(t) for t in rest.split()]
    return blocks


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
