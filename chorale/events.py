"""The event model every other module speaks.

An *event* is a plain dict.  One event is one rhythmic slot in one line of music:

    {'dur': Fraction,          # sounding length in quarters, dots included
     'base': Fraction,         # undotted length -> notated note type
     'dots': int,
     'pitches': [pitch, ...],  # empty list = rest; sorted low to high
     'tie': bool,              # ties INTO the next event
     'tie_stop': bool,         # set by finalize(), not by the parser
     'slur_start': bool, 'slur_stop': bool,
     'lyric': {'text': str, 'syllabic': str, 'extend': bool} | None}

A *pitch* is {'step': 'A'..'G', 'alter': -1|0|1, 'oct': int}.

A *line* is {bar number: [event, ...]}, bars numbered from 1, every bar full.

Nothing here knows about MusicXML, about any particular piece, or about how many
bars a piece has: bar counts are always passed in.
"""
import re
from fractions import Fraction as F

DUR = {'w': F(4), 'h': F(2), 'q': F(1), 'e': F(1, 2), 's': F(1, 4), 't': F(1, 8)}
TYPE = {F(4): 'whole', F(2): 'half', F(1): 'quarter',
        F(1, 2): 'eighth', F(1, 4): '16th', F(1, 8): '32nd'}
STEP_ORDER = 'CDEFGAB'

_PITCH = re.compile(r'([A-G])(#|b)?(\d)')


def parse_pitch(p):
    m = _PITCH.fullmatch(p)
    if not m:
        raise ValueError(f'not a pitch: {p!r}')
    step, acc, octv = m.groups()
    return {'step': step, 'alter': {'#': 1, 'b': -1}.get(acc, 0), 'oct': int(octv)}


def pkey(p):
    """Sort/compare key for a pitch.  Two spellings of one key are distinct."""
    return (p['oct'], STEP_ORDER.index(p['step']), p['alter'])


def pname(p):
    return p['step'] + {1: '#', -1: 'b'}.get(p['alter'], '') + str(p['oct'])


def check_bar(events, tag, beats=4):
    tot = sum(e['dur'] for e in events)
    if tot != beats:
        raise ValueError(f'{tag}: bar sums to {tot} beats, expected {beats}')


def finalize(line, tag, nbars):
    """Derive tie_stop and lyric extend for one single-voice line, and check it.

    A note carries `extend` when the next event is a pitched note with no syllable
    of its own — the syllable is held over it, whether by tie or by melisma.  A
    pitched note with neither a syllable nor a tie into it must sit inside such a
    melisma; anything else means the transcription lost a syllable, so it raises.
    """
    prev = None
    for m in range(1, nbars + 1):
        for e in line[m]:
            e['tie_stop'] = bool(prev and prev['tie'] and prev['pitches'] and e['pitches']
                                 and pkey(prev['pitches'][0]) == pkey(e['pitches'][0]))
            if prev and prev['tie'] and not e['tie_stop']:
                raise ValueError(f'{tag} bar {m}: tie from the previous note has no continuation')
            prev = e
    flat = [e for m in range(1, nbars + 1) for e in line[m]]
    for i, e in enumerate(flat):
        if not e['pitches'] or not e['lyric']:
            continue
        j = i + 1
        e['lyric']['extend'] = j < len(flat) and bool(flat[j]['pitches']) and not flat[j]['lyric']
    for i, e in enumerate(flat):
        if e['pitches'] and not e['lyric'] and not e['tie_stop']:
            k = i - 1
            while k >= 0 and flat[k]['pitches'] and not flat[k]['lyric']:
                k -= 1
            if k < 0 or not flat[k]['pitches'] or not flat[k]['lyric']:
                raise ValueError(f'{tag}: sung note without a syllable at flat index {i}')
    return line


def positions(events, start=F(0)):
    """[(offset in quarters from the bar line, event), ...]"""
    out = []
    p = start
    for e in events:
        out.append((p, e))
        p += e['dur']
    return out


def syllables(line, nbars):
    """The words of a line, in order — what a singer actually reads."""
    return [e['lyric']['text'] for m in range(1, nbars + 1) for e in line[m] if e['lyric']]
