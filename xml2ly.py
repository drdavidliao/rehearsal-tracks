#!/usr/bin/env python3
"""A LilyPond engraving of an open choral MusicXML score, written straight from the file (musicxml2ly needs touching up).

    python3 xml2ly.py open.musicxml out.ly --staff "Tenor 1=TT" "Tenor 2=TT" Baritone=BB Bass=BB \
        --label "TT=T. 1, 2" "BB=Bar., B." --title "..." --composer "..." --breaks 3,6,9
    lilypond -o out out.ly

--staff puts each sung part on a staff by label, in score order. Two parts on a label share the staff through \\partCombine,
which writes a chord where they move together and two voices where they don't. Words go under the staff, aligned on a hidden
copy of the first part; the second part gets its own line, holding words only in bars where its words or rhythm differ.
A part not named keeps its own staff: a grand staff if it has two, a one-line staff (hidden when empty) if its clef is percussion.
--breaks ends a system after each bar number given, and --proof takes a scan's systems and pages from its scanproof projects, so
the engraving can follow a print.
"""
import argparse, re, sys
import xml.etree.ElementTree as ET
from fractions import Fraction as F

TYPES = {'breve': '\\breve', 'whole': '1', 'half': '2', 'quarter': '4', 'eighth': '8', '16th': '16', '32nd': '32', '64th': '64'}
ACC = {-2: 'eses', -1: 'es', 0: '', 1: 'is', 2: 'isis'}
KEYS = {-7: 'ces', -6: 'ges', -5: 'des', -4: 'aes', -3: 'ees', -2: 'bes', -1: 'f', 0: 'c', 1: 'g', 2: 'd', 3: 'a', 4: 'e', 5: 'b', 6: 'fis', 7: 'cis'}
ARTS = {'staccato': '-.', 'accent': '->', 'strong-accent': '-^', 'tenuto': '--', 'staccatissimo': '-!', 'doit': '\\bendAfter #+4',
        'falloff': '\\bendAfter #-4'}
DYNS = {'ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff', 'sf', 'sfz', 'fp'}


def q(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def skip(d, ch='s'):
    return f'{ch}1*{d.numerator}/{d.denominator}'


def clef_of(c):
    sign, line, oc = c.findtext('sign'), c.findtext('line'), int(c.findtext('clef-octave-change') or 0)
    if sign == 'percussion': return 'percussion'
    name = {('G', '2'): 'treble', ('F', '4'): 'bass', ('C', '3'): 'alto', ('C', '4'): 'tenor'}[(sign, line)]
    return name + {-1: '_8', 1: '^8', 0: ''}[oc]


class Part:
    """one part: its voices as (staff, voice) -> per bar a list of events, its clefs, and what's in its directions"""
    def __init__(self, el, name):
        self.name, self.voices, self.staves, self.clefs, self.lengths = name, {}, 1, {}, []
        self.first_directions, self.barlines, self.keys, self.times, self.marks = {}, {}, {}, {}, {}
        div, nb = 1, len(el.findall('measure'))
        for mi, m in enumerate(el.findall('measure')):
            pos = mx = F(0); last = {}; pending = []
            for e in m:
                if e.tag == 'attributes':
                    if e.find('divisions') is not None: div = int(e.findtext('divisions'))
                    if e.find('staves') is not None: self.staves = int(e.findtext('staves'))
                    k, t = e.find('key'), e.find('time')
                    if k is not None: self.keys[(mi, pos)] = int(k.findtext('fifths'))
                    if t is not None: self.times[(mi, pos)] = (t.findtext('beats'), t.findtext('beat-type'))
                    for c in e.findall('clef'):
                        self.clefs.setdefault(int(c.get('number') or 1), []).append((mi, pos, clef_of(c)))
                elif e.tag == 'backup': pos -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward': pos += F(int(e.findtext('duration')), div); mx = max(mx, pos)
                elif e.tag == 'barline':
                    r, st, en = e.find('repeat'), e.findtext('bar-style'), e.find('ending')
                    self.barlines.setdefault(mi, []).append((e.get('location') or 'right', st, r.get('direction') if r is not None else None,
                                                             (en.get('number'), en.get('type')) if en is not None else None))
                elif e.tag == 'direction':
                    place = e.get('placement')
                    for dt in e.findall('direction-type'):
                        for x in dt:
                            if x.tag == 'rehearsal': self.marks.setdefault((mi, pos), []).append(('mark', x.text.strip()))
                            elif x.tag == 'metronome':
                                self.marks.setdefault((mi, pos), []).append(('metro', x.findtext('beat-unit'), x.findtext('per-minute')))
                            elif x.tag == 'words' and x.get('font-weight') == 'bold' and e.find('direction-type/metronome') is not None:
                                self.marks.setdefault((mi, pos), []).append(('tempo', x.text.strip()))
                            elif x.tag == 'words' and (x.text or '').strip():
                                pending.append(('words', x.text.strip(), place, x.get('font-style'), x.get('font-weight')))
                            elif x.tag == 'dynamics':
                                pending += [('dyn', d.tag) for d in x if d.tag in DYNS]
                            elif x.tag == 'wedge':
                                pending.append(('wedge', x.get('type')))
                elif e.tag == 'note':
                    if e.find('grace') is not None: continue
                    v = (int(e.findtext('staff') or 1), e.findtext('voice') or '1')
                    bars = self.voices.setdefault(v, [[] for _ in range(nb)])
                    no = e.find('notations')
                    p = e.find('pitch')
                    pitch = None
                    if p is not None:
                        pitch = (p.findtext('step').lower(), int(p.findtext('octave')), int(float(p.findtext('alter') or 0)), e.find('tie[@type="start"]') is not None)
                    elif e.find('unpitched') is not None: pitch = ('c', 4, 0, False)
                    if e.find('chord') is not None:
                        ev = last[v]
                        if pitch: ev['pitches'].append(pitch)
                    else:
                        d = F(int(e.findtext('duration') or 0), div)
                        r = e.find('rest')
                        ev = dict(pos=pos, dur=d, type=e.findtext('type'), dots=len(e.findall('dot')), rest=r is not None,
                                  whole=r is not None and r.get('measure') == 'yes', hidden=e.get('print-object') == 'no',
                                  pitches=[pitch] if pitch else [], tuplet=None, close=False, post=[], head=None, slur=[], lyric=None)
                        tm = e.find('time-modification')
                        if tm is not None: ev['tm'] = (tm.findtext('actual-notes'), tm.findtext('normal-notes'))
                        l = e.find('lyric')
                        if l is not None and ''.join(t.text or '' for t in l.findall('text')).strip():
                            ev['lyric'] = (''.join(t.text or '' for t in l.findall('text')), l.findtext('syllabic') or 'single', l.find('extend') is not None)
                        ev['post'], pending = [('dir', x) for x in pending], []
                        bars[mi].append(ev); last[v] = ev
                        pos += d; mx = max(mx, pos)
                    if e.findtext('notehead') == 'x': ev['head'] = 'x'
                    if no is not None:
                        for x in no:
                            if x.tag == 'tuplet' and x.get('type') == 'start': ev['tuplet'] = True
                            elif x.tag == 'tuplet' and x.get('type') == 'stop': ev['close'] = True
                            elif x.tag == 'slur': ev['slur'].append(x.get('type'))
                            elif x.tag == 'slide' and x.get('type') == 'start': ev['post'].append(('art', '\\glissando'))
                            elif x.tag == 'fermata': ev['post'].append(('art', '\\fermata'))
                            elif x.tag == 'articulations':
                                ev['post'] += [('art', ARTS[a.tag]) for a in x if a.tag in ARTS]
            self.lengths.append(mx)

    def clef_at(self, staff, mi, pos):
        return [c for m_, p_, c in self.clefs.get(staff, []) if m_ == mi and p_ == pos]


def pitch_ly(p):
    step, octv, alter, _ = p
    return step + ACC[alter] + ("'" * (octv - 3) if octv >= 3 else ',' * (3 - octv))


def dur_ly(ev):
    if ev['type'] in TYPES: return TYPES[ev['type']] + '.' * ev['dots']
    return '1*' + str(ev['dur'] / 4)


def post_ly(ev):
    out = ''
    for kind, x in ev['post']:
        if kind == 'art': out += x if x.startswith('-') else ' ' + x
        elif x[0] == 'dyn': out += '\\' + x[1]
        elif x[0] == 'wedge': out += {'crescendo': '\\<', 'diminuendo': '\\>', 'stop': '\\!'}.get(x[1], '')
        elif x[0] == 'words':
            style = ('\\italic ' if x[3] == 'italic' else '') + ('\\bold ' if x[4] == 'bold' else '')
            out += ('_' if x[2] == 'below' else '^') + '\\markup ' + style + q(x[1])
    return out


def voice_ly(part, key, length, plain=False, melisma=None):
    """the voice's music, a bar to a line. plain: for a hidden aligner, the rhythm only; melisma says which notes start or end one"""
    bars, out = part.voices[key], []
    for mi, evs in enumerate(bars):
        toks, pos = [], F(0)
        for c in ([] if plain else part.clef_at(key[0], mi, F(0))): toks.append(f'\\clef "{c}"')
        for ev in evs:
            if ev['pos'] > pos: toks.append(skip((ev['pos'] - pos) / 4))
            if ev['tuplet'] and 'tm' in ev: toks.append(f"\\tuplet {ev['tm'][0]}/{ev['tm'][1]} {{")
            if ev['whole']: t = skip(length[mi] / 4, 's' if plain else 'R')
            elif ev['rest']: t = ('s' if ev['hidden'] or plain else 'r') + dur_ly(ev)
            elif plain:
                t = 'c' + dur_ly(ev)
                t += {'start': '\\melisma', 'end': '\\melismaEnd'}.get(melisma.get((mi, ev['pos'])), '') if melisma else ''
            else:
                ps = ev['pitches']
                if len(ps) == 1: t = pitch_ly(ps[0]) + dur_ly(ev) + ('~' if ps[0][3] else '')
                else: t = '<' + ' '.join(pitch_ly(p) + ('~' if p[3] else '') for p in ps) + '>' + dur_ly(ev)
                if ev['head'] == 'x': t = '\\xNote ' + t
            if not plain:
                t += post_ly(ev)
                t += ''.join({'start': '(', 'stop': ')'}.get(s, '') for s in ev['slur'])
            toks.append(t)
            if ev['close'] and 'tm' in ev: toks.append('}')
            pos = ev['pos'] + ev['dur']
        if pos < length[mi]: toks.append(skip((length[mi] - pos) / 4))
        out.append('  ' + ' '.join(toks) + f' | % {mi + 1}')
    return '\n'.join(out)


def melismas(bars):
    """a note with no word carries on the syllable before it: {(bar, pos): 'start'|'end'}, and the notes with no syllable to carry"""
    notes = [(mi, ev) for mi, evs in enumerate(bars) for ev in evs]
    marks, orphans, i = {}, set(), 0
    while i < len(notes):
        mi, ev = notes[i]
        if ev['rest']: i += 1; continue
        if ev['lyric'] is None:
            orphans.add((mi, ev['pos'])); i += 1; continue
        j = i
        while j + 1 < len(notes) and not notes[j + 1][1]['rest'] and notes[j + 1][1]['lyric'] is None: j += 1
        if j > i:
            marks[(mi, ev['pos'])] = 'start'
            marks[(notes[j][0], notes[j][1]['pos'])] = 'end'
        i = j + 1
    return marks, orphans


def bar_words(evs):
    return [(e['pos'], e['rest'], e['lyric'][:2] if e['lyric'] else None) for e in evs]


def lyrics_ly(bars, orphans, same=None):
    """the words, one token per syllable; `same` bars (identical to the line above) are skips"""
    toks = []
    for mi, evs in enumerate(bars):
        for ev in evs:
            if ev['rest']: continue
            if (mi, ev['pos']) in orphans: toks.append('\\skip 1'); continue
            if ev['lyric'] is None: continue
            if same and mi in same: toks.append('\\skip 1'); continue
            text, syl, ext = ev['lyric']
            toks.append(q(text) + (' --' if syl in ('begin', 'middle') else '') + (' __' if ext else ''))
        toks.append(f'\n  % {mi + 1}\n ')
    return ' '.join(toks)


def global_ly(p, length, breaks, page_ends=()):
    out = []
    for mi, ln in enumerate(length):
        toks = []
        if (mi, F(0)) in p.keys: toks.append(f'\\key {KEYS[p.keys[(mi, F(0))]]} \\major')
        if (mi, F(0)) in p.times: toks.append(f'\\time {p.times[(mi, F(0))][0]}/{p.times[(mi, F(0))][1]}')
        marks = sorted(k for k in p.marks if k[0] == mi)
        pos = F(0)
        for k in marks:
            if k[1] > pos: toks.append(skip((k[1] - pos) / 4)); pos = k[1]
            items = p.marks[k]
            tempo = next((x[1] for x in items if x[0] == 'tempo'), None)
            metro = next((x for x in items if x[0] == 'metro'), None)
            if tempo or metro:
                m = ''
                if metro: m = f' \\concat {{ "(" \\fontsize #-2 \\rhythm {{ {TYPES.get(metro[1], "4")} }} " = {metro[2]})" }}'
                toks.append(f'\\tempo \\markup {{ {q(tempo or "")}{m} }}')
            for x in items:
                if x[0] == 'mark': toks.append(f'\\mark \\markup \\box {q(x[1])}')
        if ln > pos: toks.append(skip((ln - pos) / 4))
        for loc, style, rep, end in p.barlines.get(mi, []):
            if rep == 'forward': toks.insert(0, '\\bar ".|:"')
            elif rep == 'backward': toks.append('\\bar ":|."')
            elif loc == 'right' and style == 'light-heavy': toks.append('\\bar "|."')
            elif loc == 'right' and style == 'light-light': toks.append('\\bar "||"')
            if end and end[1] == 'start': toks.insert(0, f"\\set Score.repeatCommands = #'((volta \"{end[0]}.\"))")
            elif end: toks.append("\\set Score.repeatCommands = #'((volta #f))")
        if mi + 1 in page_ends: toks.append('\\pageBreak')
        elif mi + 1 in breaks: toks.append('\\break')
        else: toks.append('\\noBreak' if breaks else '')
        out.append('  ' + ' '.join(toks) + f' | % {mi + 1}')
    return '\n'.join(out)


def var(i, what):
    return what + ''.join(chr(ord('A') + int(d)) for d in str(i))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xml'); ap.add_argument('out')
    ap.add_argument('--staff', nargs='+', required=True); ap.add_argument('--label', nargs='*', default=[])
    ap.add_argument('--title', default=''); ap.add_argument('--composer', default=''); ap.add_argument('--arranger', default='')
    ap.add_argument('--first-page', type=int, default=1, help="the number printed on the first page, to match a print's")
    ap.add_argument('--margin', type=float, default=16, help='page margins in mm, staff names inside them')
    ap.add_argument('--breaks', default=''); ap.add_argument('--size', type=float, default=16)
    ap.add_argument('--proof', nargs='*', default=[], help="scanproof projects: end systems and pages where the scan's do")
    a = ap.parse_args()
    root = ET.parse(a.xml).getroot()
    names = {sp.get('id'): sp.findtext('part-name') for sp in root.iter('score-part')}
    parts = [Part(el, names[el.get('id')]) for el in root.findall('part')]
    length = [max(p.lengths[i] for p in parts) for i in range(len(parts[0].lengths))]
    by_name = {p.name: p for p in parts}
    staff_of = dict(s.split('=', 1) for s in a.staff)
    labels = dict(s.split('=', 1) for s in a.label)
    breaks = {int(b) for b in a.breaks.split(',') if b}
    page_ends = set()
    if a.proof:
        from scanproof.project import Project
        bars = {}
        for f in a.proof: bars.update({(f, n): b for n, b in Project(f).bars().items()})
        order = sorted(bars, key=lambda k: k[1])
        for k0, k1 in zip(order, order[1:]):
            if bars[k1]['first_in_system']:
                breaks.add(k0[1])
                if (k0[0], bars[k0]['page']) != (k1[0], bars[k1]['page']): page_ends.add(k0[1])
    defs, body, done, n = [], [], set(), 0
    defs.append('global = {\n' + global_ly(parts[0], length, breaks, page_ends) + '\n}')

    def define(what, text):
        nonlocal n
        n += 1
        name = var(n, what)
        defs.append(f'{name} = {text}')
        return name

    def music(p, key):
        return define('music', '{\n' + voice_ly(p, key, length) + '\n}')

    choir = []
    for lab in dict.fromkeys(staff_of.values()):
        members = [by_name[p] for p, l in staff_of.items() if l == lab]
        done |= {m.name for m in members}
        clef = members[0].clefs[1][0][2]
        keys = [next(iter(m.voices)) for m in members]
        # the upper part alone carries directions the lower repeats
        if len(members) > 1:
            for mi, (e0, e1) in enumerate(zip(members[0].voices[keys[0]], members[1].voices[keys[1]])):
                top = {(e['pos'], str(x)) for e in e0 for x in e['post'] if x[0] == 'dir'}
                for e in e1: e['post'] = [x for x in e['post'] if x[0] != 'dir' or (e['pos'], str(x)) not in top]
        vis = [music(m, k) for m, k in zip(members, keys)]
        name = q(labels.get(lab, members[0].name))
        aligners, lyrics, first = [], [], None
        for idx, (m, k) in enumerate(zip(members, keys)):
            marks, orphans = melismas(m.voices[k])
            al = define('aligner', '{\n' + voice_ly(m, k, length, plain=True, melisma=marks) + '\n}')
            vname = f'{lab}{idx}'
            aligners.append(f'\\new NullVoice = "{vname}" \\{al}')
            same = None
            if idx: same = {mi for mi in range(len(length)) if bar_words(m.voices[k][mi]) == bar_words(first[mi])}
            else: first = m.voices[k]
            words = define('words', '\\lyricmode {\n ' + lyrics_ly(m.voices[k], orphans, same) + '\n}')
            if not idx or len(same) < len(length):
                lyrics.append(f'\\new Lyrics \\lyricsto "{vname}" \\{words}')
        voices = f'\\partCombine \\{vis[0]} \\{vis[1]}' if len(vis) == 2 else f'\\new Voice \\{vis[0]}'
        choir.append(f'\\new Staff \\with {{ instrumentName = {name} shortInstrumentName = {name} printPartCombineTexts = ##f }} << \\clef "{clef}" \\global {" ".join(aligners)} {voices} >>\n    ' + '\n    '.join(lyrics))
    body.append('\\new ChoirStaff <<\n    ' + '\n    '.join(choir) + '\n  >>')

    for p in parts:
        if p.name in done: continue
        if p.staves == 2:
            staves = []
            for st in (1, 2):
                vs = [k for k in sorted(p.voices) if k[0] == st]
                inner = ' '.join(f'\\new Voice {{ \\{"voiceOne" if i == 0 else "voiceTwo"} \\{music(p, k)} }}' if len(vs) > 1 else f'\\new Voice \\{music(p, k)}' for i, k in enumerate(vs))
                staves.append(f'\\new Staff << \\clef "{p.clefs[st][0][2]}" \\global {inner} >>')
            body.append(f'\\new PianoStaff \\with {{ instrumentName = {q(p.name)} shortInstrumentName = "Pno." }} <<\n    ' + '\n    '.join(staves) + '\n  >>')
        elif p.clefs[1][0][2] == 'percussion':
            k = next(iter(p.voices))
            # its own rhythm, no key
            body.append(f'\\new RhythmicStaff \\with {{ \\RemoveAllEmptyStaves instrumentName = {q(p.name)} shortInstrumentName = {q(p.name)} }} \\new Voice \\{music(p, k)}')
        else:
            k = next(iter(p.voices))
            body.append(f'\\new Staff \\with {{ instrumentName = {q(p.name)} }} << \\clef "{p.clefs[1][0][2]}" \\global \\new Voice \\{music(p, k)} >>')

    text = f'''\\version "2.24.0"
#(set-global-staff-size {a.size})
\\paper {{ #(set-paper-size "letter") print-first-page-number = ##t first-page-number = {a.first_page} ragged-last-bottom = ##f
  top-margin = {a.margin}\\mm bottom-margin = {a.margin}\\mm left-margin = {a.margin}\\mm right-margin = {a.margin}\\mm }}
\\header {{ title = {q(a.title)} composer = {q(a.composer)} arranger = {q(a.arranger)} tagline = ##f }}
''' + '\n'.join(defs) + '''
\\score {
  <<
  ''' + '\n  '.join(body) + '''
  >>
  \\layout {
    indent = 18\\mm short-indent = 15\\mm
    \\context { \\Score \\override BarNumber.break-visibility = ##(#f #f #t) \\override Beam.breakable = ##t }
    \\context { \\Lyrics \\override LyricSpace.minimum-distance = #0.8 \\override LyricHyphen.minimum-distance = #0.6 }
    \\context { \\NullVoice melismaBusyProperties = #'(melismaBusy) }
  }
}
'''
    open(a.out, 'w').write(text)


if __name__ == '__main__':
    main()
