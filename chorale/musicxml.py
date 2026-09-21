"""MusicXML emission.

Child order inside <note> is not advisory: Sibelius rejects a file that gets it
wrong, usually without saying which note.  The order these emitters keep is

    chord, pitch|rest, duration, tie, voice, type, dot, accidental, stem,
    staff, beam, notations, lyric

with <tie> right after <duration> and its twin <tied> inside <notations>, and
inside <direction>, <direction-type> before <offset>.
"""
from fractions import Fraction as F
from xml.sax.saxutils import escape

from .beaming import beams, beams_at
from .events import TYPE, positions

CLEFS = {
    'G': '<clef><sign>G</sign><line>2</line></clef>',
    'G8': '<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>',
    'F': '<clef><sign>F</sign><line>4</line></clef>',
    'C3': '<clef><sign>C</sign><line>3</line></clef>',
    'C4': '<clef><sign>C</sign><line>4</line></clef>',
}

REPEAT_FORWARD = ('<barline location="left"><bar-style>heavy-light</bar-style>'
                  '<repeat direction="forward"/></barline>')
REPEAT_BACKWARD = ('<barline location="right"><bar-style>light-heavy</bar-style>'
                   '<repeat direction="backward"/></barline>')
FINAL = '<barline location="right"><bar-style>light-heavy</bar-style></barline>'


class ScoreSpec:
    """What every bar of one piece has in common.

    `accidentals` is the set of (step, alter) pairs written out as a printed
    accidental — the ones the key signature does not already give.  Courtesy
    accidentals beyond that are the engraver's business, not this layer's.
    """

    def __init__(self, nbars, divisions=4, fifths=0, beats=4, beat_type=4,
                 left_barlines=None, right_barlines=None,
                 accidentals=(), fermata_bars=()):
        self.nbars = nbars
        self.divisions = divisions
        self.fifths = fifths
        self.beats = beats
        self.beat_type = beat_type
        self.left_barlines = left_barlines or {}
        self.right_barlines = right_barlines or {}
        self.accidentals = set(accidentals)
        self.fermata_bars = set(fermata_bars)

    @property
    def bar_beats(self):
        """Length of a full bar, in quarters."""
        return F(self.beats * 4, self.beat_type)

    def ticks(self, quarters):
        return int(quarters * self.divisions)

    def attributes(self, clef, staves=None):
        s = (f'<attributes><divisions>{self.divisions}</divisions>'
             f'<key><fifths>{self.fifths}</fifths></key>'
             f'<time><beats>{self.beats}</beats><beat-type>{self.beat_type}</beat-type></time>')
        if staves:
            s += f'<staves>{staves}</staves>'
            s += ''.join(f'<clef number="{i + 1}">{CLEFS[c][len("<clef>"):-len("</clef>")]}</clef>'
                         for i, c in enumerate(clef))
        else:
            s += CLEFS[clef]
        return s + '</attributes>'


# ---------------------------------------------------------------- fragments
def pitch_xml(p):
    s = f"<pitch><step>{p['step']}</step>"
    if p['alter']:
        s += f"<alter>{p['alter']}</alter>"
    return s + f"<octave>{p['oct']}</octave></pitch>"


def dyn_xml(mark, placement='below'):
    return (f'<direction placement="{placement}"><direction-type><dynamics>'
            f'<{mark}/></dynamics></direction-type></direction>')


def words_xml(text, placement='above', italic=False, bold=False):
    attrs = (' font-style="italic"' if italic else '') + (' font-weight="bold"' if bold else '')
    return (f'<direction placement="{placement}"><direction-type>'
            f'<words{attrs}>{escape(text)}</words></direction-type></direction>')


def tempo_xml(text, bpm, unit='quarter', parentheses=True):
    par = ' parentheses="yes"' if parentheses else ''
    return (f'<direction placement="above"><direction-type>'
            f'<words font-weight="bold">{escape(text)}</words></direction-type>'
            f'<direction-type><metronome{par}><beat-unit>{unit}</beat-unit>'
            f'<per-minute>{bpm}</per-minute></metronome></direction-type>'
            f'<sound tempo="{bpm}"/></direction>')


def rehearsal_xml(label):
    return (f'<direction placement="above"><direction-type>'
            f'<rehearsal>{escape(str(label))}</rehearsal></direction-type></direction>')


WEDGE_START = ('<direction><direction-type><wedge type="{kind}" number="1"/>'
               '</direction-type></direction>')
WEDGE_STOP = '<direction><direction-type><wedge type="stop" number="1"/></direction-type></direction>'


def note_xml(e, spec, voice=1, beam='', stem=None, staff=None,
             lyr_place=None, lyr_num=1, fermata=False, tie_attrs=None):
    """One event — a rest, a note, or a chord — as one or more <note> elements."""
    s = ''
    for pi, p in enumerate(e['pitches'] or [None]):
        s += '<note>'
        if pi > 0:
            s += '<chord/>'
        if p is None:
            s += '<rest measure="yes"/>' if e['dur'] == spec.bar_beats else '<rest/>'
        else:
            s += pitch_xml(p)
        s += f'<duration>{spec.ticks(e["dur"])}</duration>'
        if p is not None:
            if e.get('tie_stop'):
                s += '<tie type="stop"/>'
            if e['tie']:
                s += '<tie type="start"/>'
        s += f'<voice>{voice}</voice>'
        if e['dur'] != spec.bar_beats or p is not None:
            s += f"<type>{TYPE[e['base']]}</type>" + '<dot/>' * e['dots']
        if p is not None and (p['step'], p['alter']) in spec.accidentals:
            s += '<accidental>' + {1: 'sharp', -1: 'flat', 0: 'natural'}[p['alter']] + '</accidental>'
        if p is not None and stem:
            s += f'<stem>{stem}</stem>'
        if staff:
            s += f'<staff>{staff}</staff>'
        if pi == 0:
            s += beam
        nots = ''
        if p is not None:
            if e.get('tie_stop'):
                nots += '<tied type="stop"/>'
            if e['tie']:
                # On a shared staff the tie goes on the side away from the stem.
                # Say so explicitly: Verovio picks the side by voice NUMBER, so a
                # voice-2 note whose stems were flipped up (crossed_bars) still
                # gets its tie curved under, straight through the other part.
                if tie_attrs:
                    side = ''.join(f' {k}="{v}"' for k, v in tie_attrs.items())
                else:
                    side = {'up': ' orientation="over"',
                            'down': ' orientation="under"'}.get(stem, '')
                nots += f'<tied type="start"{side}/>'
            if pi == 0 and e['slur_stop']:
                nots += '<slur type="stop" number="1"/>'
            if pi == 0 and e['slur_start']:
                nots += '<slur type="start" number="1"/>'
        if fermata and pi == 0:
            nots += '<fermata/>'
        if nots:
            s += f'<notations>{nots}</notations>'
        if pi == 0 and p is not None and e['lyric']:
            ly = e['lyric']
            pl = f' placement="{lyr_place}"' if lyr_place else ''
            s += (f'<lyric number="{lyr_num}"{pl}><syllabic>{ly["syllabic"]}</syllabic>'
                  f'<text>{escape(ly["text"])}</text>')
            if ly.get('extend'):
                s += '<extend/>'
            s += '</lyric>'
        s += '</note>'
    return s


# ---------------------------------------------------------------- marks
class StaffMarks:
    """What hangs off one staff: dynamics, hairpins, and cue words.

    dyn   {(bar, offset in quarters): 'mp'}
    hair  [(bar, start offset, stop offset, kind), ...]  kind defaults to diminuendo
    mel   {bar: (offset, placement)}  — the "mel." cue, or any single word
    """

    def __init__(self, dyn=None, hair=None, mel=None, mel_text='mel.'):
        self.dyn = dyn or {}
        self.hair = [h if len(h) == 4 else (*h, 'diminuendo') for h in (hair or [])]
        self.mel = mel or {}
        self.mel_text = mel_text

    def at(self, m, pos):
        s = ''
        if (m, pos) in self.dyn:
            s += dyn_xml(self.dyn[(m, pos)])
        if m in self.mel and pos == self.mel[m][0]:
            s += words_xml(self.mel_text, italic=True, placement=self.mel[m][1])
        for h in self.hair:
            if h[0] == m and h[1] == pos:
                s += WEDGE_START.format(kind=h[3])
        return s

    def after(self, m, pos):
        return ''.join(WEDGE_STOP for h in self.hair if h[0] == m and h[2] == pos)


class Header:
    """Marks printed once, on the top part: rehearsal figures, tempo, tempo words."""

    def __init__(self, rehearsal=(), tempo=None, words=None):
        self.rehearsal = dict(rehearsal) if isinstance(rehearsal, dict) else {b: b for b in rehearsal}
        self.tempo = tempo            # (bar, xml)
        self.words = words or {}      # {bar: xml}

    def at(self, m):
        s = ''
        if m in self.rehearsal:
            s += rehearsal_xml(self.rehearsal[m])
        if self.tempo and self.tempo[0] == m:
            s += self.tempo[1]
        if m in self.words:
            s += self.words[m]
        return s


EMPTY_MARKS = StaffMarks()
EMPTY_HEADER = Header()


def _measure_open(m, spec, clef, first, header):
    s = f'<measure number="{m}">'
    if m in spec.left_barlines:
        s += spec.left_barlines[m]
    if m == 1:
        s += spec.attributes(clef)
    if first:
        s += header.at(m)
    return s


def _measure_close(m, spec):
    return spec.right_barlines.get(m, '') + '</measure>'


# ---------------------------------------------------------------- part shapes
def open_part(pid, line, clef, spec, first=False, marks=None, header=None):
    """One line, one voice, one staff — an open score."""
    marks = marks or EMPTY_MARKS
    header = header or EMPTY_HEADER
    out = [f'<part id="{pid}">']
    for m in range(1, spec.nbars + 1):
        evs = line[m]
        s = _measure_open(m, spec, clef, first, header)
        bm = beams(evs)
        for i, (pos, e) in enumerate(positions(evs)):
            s += marks.at(m, pos)
            s += note_xml(e, spec, beam=bm[i], fermata=(m in spec.fermata_bars))
            s += marks.after(m, pos + e['dur'])
        out.append(s + _measure_close(m, spec))
    out.append('</part>')
    return '\n'.join(out)


def divided_part(pid, bars, clef, spec, first=False, marks=None, header=None):
    """Two parts on one staff, splitting once per bar and staying split.

    `bars` is {bar: (v1, v2, split offset)} from collapse.closed_bars.
    """
    marks = marks or EMPTY_MARKS
    header = header or EMPTY_HEADER
    out = [f'<part id="{pid}">']
    for m in range(1, spec.nbars + 1):
        v1, v2, split = bars[m]
        s = _measure_open(m, spec, clef, first, header)
        two = bool(v2)
        bm = beams(v1)
        pos = F(0)
        for i, e in enumerate(v1):
            s += marks.at(m, pos)
            in_split = two and pos >= split
            s += note_xml(e, spec, voice=1, beam=bm[i],
                          stem='up' if in_split else None,
                          lyr_place='above' if in_split else None,
                          fermata=(m in spec.fermata_bars))
            pos += e['dur']
            s += marks.after(m, pos)
        if two:
            s += f'<backup><duration>{spec.ticks(pos)}</duration></backup>'
            if split:
                s += f'<forward><duration>{spec.ticks(split)}</duration></forward>'
            bm2 = beams(v2)
            for i, e in enumerate(v2):
                s += note_xml(e, spec, voice=2, beam=bm2[i], stem='down',
                              lyr_place='below', lyr_num=2)
        out.append(s + _measure_close(m, spec))
    out.append('</part>')
    return '\n'.join(out)


def collapsed_part(pid, bars, clef, spec, first=False, marks=None, header=None, two_map=None,
                   stems_follow_crossing=False, crossed_tie=(('orientation', 'over'),)):
    """Two parts on one staff, merging and splitting freely inside the bar.

    `bars` is {bar: (v1, v2)} from collapse.merge_runs; `two_map` is
    collapse.lyric_split.  Where the bar needs only one lyric line, voice 2's
    duplicate syllables are dropped rather than printed underneath.

    A direction that falls where voice 1 has no note start would otherwise be
    lost, so it is attached at the bar line with an <offset> instead.

    Stems identify the part: voice 1 up, voice 2 down, even where the parts
    cross.  In a bar crossed throughout (collapse.crossed_bars), a voice-2 tie
    is then the higher one, and its default under-curve runs through voice 1's
    noteheads; it is written with the `crossed_tie` attributes instead, by
    default orientation="over".  Only the side survives the trip: a probe
    imported into Sibelius drew bezier-x/-y, bezier-x2/-y2 and default-y
    exactly like plain "over", so the arc's height cannot be set from the file
    and any further lift is a hand touch-up in Sibelius (Tie Middle Y).
    Pass crossed_tie=None to leave those ties alone, or
    `stems_follow_crossing=True` to flip the stems in those bars instead.
    """
    from .collapse import crossed_bars
    marks = marks or EMPTY_MARKS
    crossed = crossed_bars(bars)
    flipped = crossed if stems_follow_crossing else set()
    v2_tie = None if flipped else (dict(crossed_tie) if crossed_tie else None)
    header = header or EMPTY_HEADER
    out = [f'<part id="{pid}">']
    for m in range(1, spec.nbars + 1):
        v1, v2 = bars[m]
        spans = [(p, p + e['dur']) for p, e in v2]

        def split_here(p, d, spans=spans):
            return any(p < b and p + d > a for a, b in spans)

        v1pos = positions(v1)
        two_lines = bool(two_map and two_map.get(m))
        if not two_lines:
            for _, e in v2:
                if e['lyric']:
                    e['lyric'] = None
        s = _measure_open(m, spec, clef, first, header)
        bm = beams(v1)
        starts = {q for q, _ in v1pos}
        floating = [(q, dyn_xml(v)) for (b, q), v in marks.dyn.items() if b == m]
        if m in marks.mel:
            floating.append((marks.mel[m][0],
                             words_xml(marks.mel_text, italic=True, placement=marks.mel[m][1])))
        for q, x in sorted(floating, key=lambda t: t[0]):
            if q not in starts:
                s += x.replace('</direction>', f'<offset>{spec.ticks(q)}</offset></direction>')
        for i, (pos, e) in enumerate(v1pos):
            s += marks.at(m, pos)
            s += note_xml(e, spec, voice=1, beam=bm[i],
                          stem=((('down' if m in flipped else 'up'))
                                if split_here(pos, e['dur']) else None),
                          fermata=(m in spec.fermata_bars))
            s += marks.after(m, pos + e['dur'])
        if v2:
            s += f'<backup><duration>{spec.ticks(spec.bar_beats)}</duration></backup>'
            bm2 = beams_at(v2)
            cur = F(0)
            for i, (pos, e) in enumerate(v2):
                if pos > cur:
                    s += f'<forward><duration>{spec.ticks(pos - cur)}</duration></forward>'
                s += note_xml(e, spec, voice=2, beam=bm2[i],
                              stem='up' if m in flipped else 'down',
                              tie_attrs=v2_tie if (m in crossed and v2_tie) else None,
                              lyr_num=2 if two_lines else 1,
                              fermata=(m in spec.fermata_bars))
                cur = pos + e['dur']
        out.append(s + _measure_close(m, spec))
    out.append('</part>')
    return '\n'.join(out)


# ---------------------------------------------------------------- wrapper
HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">\n'
        '<score-partwise version="4.0">')

# Choral staves are bracketed but their barlines are NOT joined: the lyrics sit
# between the staves, and a barline drawn through that gap runs straight
# through the words.  Engraved choral octavos break the barline at every vocal
# staff for exactly this reason.  The piano's two staves still join, because a
# multi-staff part always does and there is no text between them.
GROUP_START = ('<part-group type="start" number="1"><group-symbol>bracket</group-symbol>'
               '<group-barline>no</group-barline></part-group>')
GROUP_STOP = '<part-group type="stop" number="1"/>'


def identification(composer=None, arranger=None, rights=None, software=None,
                   creators=()):
    """`creators` is [(type, name), ...] for anyone past composer and arranger.

    MusicXML's `type` on `<creator>` is free text — composer, lyricist and
    arranger are only the standard values — so "adapter", "editor" or
    "translator" are all legal, and a reader that does not recognise a type
    still has the name.  An adaptation is somebody's work and belongs in the
    file, not in a filename: a director who decides how a piece is revoiced
    made editorial decisions on every bar of it.
    """
    s = '<identification>'
    if composer:
        s += f'<creator type="composer">{escape(composer)}</creator>'
    if arranger:
        s += f'<creator type="arranger">{escape(arranger)}</creator>'
    for kind, name in creators:
        s += f'<creator type="{escape(kind)}">{escape(name)}</creator>'
    if rights:
        s += f'<rights>{escape(rights)}</rights>'
    if software:
        s += f'<encoding><software>{escape(software)}</software></encoding>'
    return s + '</identification>'


def credit(text, page=1, kind=None, justify='right', valign='bottom',
           x=None, y=None, size=None):
    """A printed credit. `text` is one string, or several for a stacked block.

    `<identification>` is metadata; `<credit>` is what appears on the page.

    Several lines go in ONE credit as successive `<credit-words>`, not as
    separate `<credit>` elements: the spec says "a series of credit-words and
    credit-symbol elements within a single credit element follow one another
    in sequence visually", only the first carries the position, and the line
    break is a literal newline at the end of each. This is what MuseScore
    writes, and Sibelius keeps only one of several sibling `<credit>` elements
    aimed at the same corner of the page — give it three and two disappear.
    """
    lines = [text] if isinstance(text, str) else list(text)
    s = f'<credit page="{page}">'
    if kind:
        s += f'<credit-type>{escape(kind)}</credit-type>'
    attrs = f' justify="{justify}" valign="{valign}"'
    if x is not None:
        attrs += f' default-x="{x}"'
    if y is not None:
        attrs += f' default-y="{y}"'
    if size is not None:
        attrs += f' font-size="{size}"'
    for i, line in enumerate(lines):
        nl = '\n' if i < len(lines) - 1 else ''
        s += f'<credit-words{attrs if i == 0 else ""}>{escape(line)}{nl}</credit-words>'
    return s + '</credit>'


def score_part(pid, name, abbr):
    return (f'<score-part id="{pid}"><part-name>{escape(name)}</part-name>'
            f'<part-abbreviation>{escape(abbr)}</part-abbreviation></score-part>')


def score_xml(title, ident, part_list, parts, credits=()):
    """part_list: the already-built <part-list> children, in order.

    `credits` are `credit()` strings, and sit between <identification> and
    <part-list>, which is where MusicXML wants them.
    """
    return '\n'.join([HEAD, f'<work><work-title>{escape(title)}</work-title></work>', ident,
                      *credits,
                      '<part-list>', *part_list, '</part-list>', *parts, '</score-partwise>'])


def orient_tie(xml, part, bar, voice, pitch, orientation):
    """Force the curve of one tie `over` or `under` the notes, in a built score.

    `pitch` is the SOUNDING pitch as (step, alter, octave).  Renderers put the
    tie on the stem-less side, which is almost always right; the exception is a
    two-voice staff where the parts cross: voice 2 (stems down) is then the
    higher part, its tie curves under by default, and it is drawn straight
    through voice 1's noteheads.  The stems stay as they are;
    only the arc moves.  Exactly one tie must match, or this raises.
    """
    import re
    assert orientation in ('over', 'under')
    pm = re.search(r'<part id="%s">.*?</part>' % re.escape(part), xml, re.S)
    mm = re.search(r'<measure number="%d"[^>]*>.*?</measure>' % bar, pm.group(0), re.S)
    step, alter, octave = pitch
    want = f'<step>{step}</step>' + (f'<alter>{alter}</alter>' if alter else '') \
        + f'<octave>{octave}</octave>'
    hits = []
    for nm in re.finditer(r'<note\b.*?</note>', mm.group(0), re.S):
        n = nm.group(0)
        if (f'<voice>{voice}</voice>' in n and want in n
                and re.search(r'<tied type="start"\s*/>', n)):
            hits.append(nm)
    if len(hits) != 1:
        raise ValueError(f'orient_tie: {len(hits)} tie starts match {part} bar {bar} '
                         f'voice {voice} {pitch}, expected 1')
    n = hits[0].group(0)
    fixed = re.sub(r'<tied type="start"\s*/>',
                   f'<tied type="start" orientation="{orientation}"/>', n, count=1)
    measure = mm.group(0).replace(n, fixed, 1)
    part_xml = pm.group(0).replace(mm.group(0), measure, 1)
    return xml.replace(pm.group(0), part_xml, 1)
