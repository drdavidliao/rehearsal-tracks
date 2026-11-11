#!/usr/bin/env python3
"""MusicXML for a player map from a hand transcription of a scan's voice staves.

    staff_text.py score.txt out.musicxml

score.txt, one line per staff per bar, sounding pitch:

    @parts T=Tenor 1,Tenor 2 B=Baritone,Bass     staff -> its parts, top first (one part: T=Tenor)
    @clef T=G8 B=F                                 G, G8 or F
    @key 0                                         fifths
    @meter 1 3/4                                   from bar 1 (more lines for changes)
    @tempo 1 84                                    quarter = 84 from bar 1
    5 B: C3h.=Let
    6 B: C3h=there B2q=be

A token is PITCHES DUR [~] [=lyric]: PITCHES is "R" for a rest or "E3,G3" for a chord, DUR w h q e s with "." for a dot
and "3" for a triplet member, "~" ties every pitch to the next note. "M" is a whole-bar rest. A chord's notes go to the
staff's parts from the top down; a single note goes to all of them; with three or more parts and two notes, the middle
part takes the upper. A bar with no line for a staff is a rest. Lyrics go to every part singing the note.
"""
import re, sys
from fractions import Fraction as F
from xml.sax.saxutils import escape

STEPS = 'CDEFGAB'
SEMI = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
DUR = {'w': F(4), 'h': F(2), 'q': F(1), 'e': F(1, 2), 's': F(1, 4)}
TYPE = {'w': 'whole', 'h': 'half', 'q': 'quarter', 'e': 'eighth', 's': '16th'}
DIV = 12
TOK = re.compile(r'^((?:[A-G](?:#|b|n)?\d)(?:,[A-G](?:#|b|n)?\d)*|R)([whqes])(\.?)(3?)(~?)$')
PIT = re.compile(r'([A-G])(#|b|n)?(\d)')


def parse(path):
    parts, clefs, key, meters, tempos, bars = {}, {}, 0, {}, {}, {}
    for line in open(path, encoding='utf-8'):
        line = '' if line.lstrip().startswith('#') else line.strip()     # a sharp is "#" too: only whole lines are comments
        if not line: continue
        if line.startswith('@'):
            w = line[1:].split()
            if w[0] == 'parts':
                for x in w[1:]:
                    k, v = x.split('=', 1); parts[k] = v.split(',')
            elif w[0] == 'clef':
                for x in w[1:]:
                    k, v = x.split('=', 1); clefs[k] = v
            elif w[0] == 'key': key = int(w[1])
            elif w[0] == 'meter': n, d = w[2].split('/'); meters[int(w[1])] = (int(n), int(d))
            elif w[0] == 'tempo': tempos[int(w[1])] = float(w[2])
            continue
        m = re.match(r'(\d+)\s+(\w+):\s*(.*)$', line)
        if not m: raise ValueError(f'bad line: {line}')
        bars.setdefault(int(m.group(1)), {})[m.group(2)] = m.group(3).split()
    # names with spaces in @parts: written with underscores
    parts = {k: [p.replace('_', ' ') for p in v] for k, v in parts.items()}
    return parts, clefs, key, meters, tempos, bars


def token(t):
    lyr = None
    if '=' in t: t, lyr = t.split('=', 1)
    m = TOK.match(t)
    if not m: raise ValueError(f'bad token {t!r}')
    pits, d, dot, trip, tie = m.groups()
    dur = DUR[d] * (F(3, 2) if dot else 1) * (F(2, 3) if trip else 1)
    ps = [] if pits == 'R' else [PIT.match(p).groups() for p in pits.split(',')]
    ps.sort(key=lambda p: -(int(p[2]) * 12 + SEMI[p[0]] + {'#': 1, 'b': -1}.get(p[1], 0)))
    return dict(pitches=ps, dur=dur, type=TYPE[d], dot=bool(dot), trip=bool(trip), tie=bool(tie), lyric=lyr)


def share(ps, n):
    """the pitch each of n parts sings, top part first"""
    if not ps: return [None] * n
    if len(ps) == 1: return [ps[0]] * n
    if len(ps) >= n: return ps[:n]
    if n == 3 and len(ps) == 2: return [ps[0], ps[0], ps[1]]
    return [ps[min(i, len(ps) - 1)] for i in range(n)]


def note_xml(p, ev, tie_stop, lyric):
    out = ['<note>']
    if p is None: out.append('<rest/>')
    else:
        step, acc, octv = p
        alter = {'#': 1, 'b': -1}.get(acc, 0)
        out.append(f'<pitch><step>{step}</step>' + (f'<alter>{alter}</alter>' if alter else '') + f'<octave>{octv}</octave></pitch>')
    out.append(f'<duration>{int(ev["dur"] * DIV)}</duration>')
    if p is not None:
        if tie_stop: out.append('<tie type="stop"/>')
        if ev['tie']: out.append('<tie type="start"/>')
    out.append('<voice>1</voice>')
    out.append(f'<type>{ev["type"]}</type>' + ('<dot/>' if ev['dot'] else ''))
    if p is not None and p[1] in ('#', 'b', 'n'):
        out.append('<accidental>' + {'#': 'sharp', 'b': 'flat', 'n': 'natural'}[p[1]] + '</accidental>')
    if ev['trip']: out.append('<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>')
    if p is not None and (tie_stop or ev['tie']):
        out.append('<notations>' + ('<tied type="stop"/>' if tie_stop else '') + ('<tied type="start"/>' if ev['tie'] else '') + '</notations>')
    if p is not None and lyric:
        syl = 'single'; t = lyric
        if t.startswith('-') and t.endswith('-') and len(t) > 2: syl, t = 'middle', t[1:-1]
        elif t.startswith('-'): syl, t = 'end', t[1:]
        elif t.endswith('-'): syl, t = 'begin', t[:-1]
        out.append(f'<lyric number="1"><syllabic>{syl}</syllabic><text>{escape(t.replace("_", " "))}</text></lyric>')
    out.append('</note>')
    return ''.join(out)


def build(path, out):
    parts, clefs, key, meters, tempos, bars = parse(path)
    nb = max(bars)
    plist = [(st, i, name) for st, names in parts.items() for i, name in enumerate(names)]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
           '<score-partwise version="4.0"><part-list>']
    for k, (st, i, name) in enumerate(plist):
        xml.append(f'<score-part id="P{k + 1}"><part-name>{escape(name)}</part-name></score-part>')
    xml.append('</part-list>')
    for k, (st, i, name) in enumerate(plist):
        xml.append(f'<part id="P{k + 1}">')
        meter, tie_open = (3, 4), set()
        for b in range(1, nb + 1):
            xml.append(f'<measure number="{b}">')
            attrs = []
            if b == 1: attrs.append(f'<divisions>{DIV}</divisions><key><fifths>{key}</fifths></key>')
            if b in meters:
                meter = meters[b]; attrs.append(f'<time><beats>{meter[0]}</beats><beat-type>{meter[1]}</beat-type></time>')
            if b == 1:
                c = clefs.get(st, 'G')
                attrs.append({'G': '<clef><sign>G</sign><line>2</line></clef>', 'F': '<clef><sign>F</sign><line>4</line></clef>',
                              'G8': '<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>'}[c])
            if attrs: xml.append('<attributes>' + ''.join(attrs) + '</attributes>')
            if k == 0 and b in tempos:
                xml.append(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>{tempos[b]:g}</per-minute></metronome></direction-type><sound tempo="{tempos[b]:g}"/></direction>')
            length = F(meter[0] * 4, meter[1])
            toks = bars.get(b, {}).get(st, ['M'])
            if toks == ['M']:
                xml.append(f'<note><rest measure="yes"/><duration>{int(length * DIV)}</duration><voice>1</voice></note>')
                tie_open = set(); xml.append('</measure>'); continue
            total = F(0)
            for t in toks:
                ev = token(t); total += ev['dur']
                p = share(ev['pitches'], len(parts[st]))[i]
                key_ = p and (p[0], p[1] or '', p[2])       # a tie joins the same pitch, accidental and all
                xml.append(note_xml(p, ev, key_ in tie_open if p else False, ev['lyric']))
                tie_open = {key_} if (p and ev['tie']) else set()
            if total != length: raise ValueError(f'bar {b} staff {st}: {total} quarters, the meter has {length}')
            xml.append('</measure>')
        xml.append('</part>')
    xml.append('</score-partwise>')
    open(out, 'w', encoding='utf-8').write('\n'.join(xml))
    return [n for _, _, n in plist], nb


if __name__ == '__main__':
    names, nb = build(sys.argv[1], sys.argv[2])
    print(f'{sys.argv[2]}: {nb} bars, parts {names}')
