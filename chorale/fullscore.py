"""A whole score from one text file: every staff, and everything printed on it.

    python3 -m chorale.fullscore score.txt out.musicxml

SKILL.md, "A transcription is the whole page". The notes are chorale score text (scoretext.py: `[block]` headers,
`bar: tokens`, ` | ` between two voices on a staff, sounding pitch, a bare letter is natural). Around them:

    @title The Song                     printed text, each as it stands on page 1 (credit-words); also
    @subtitle For TTBB and Piano        @composer, @lyricist, @arranger, @rights, and @credit for anything else
    @key 1 -1                           from bar 1, fifths
    @meter 1 4/4                        from bar 1; `@meter 1 4/4 common`, `@meter 8 2/2 cut` print the C and the
                                        cut C (<time symbol="common|cut">)
    @part T "Tenor" T clef=G8           a part: id, printed name, its block, clef
    @part P "Piano" R L clef=G,F        two blocks: a grand staff, staff 1 and 2
    @part K "Knocking" K clef=perc lines=1   a percussion clef and an optional staff line count (`lines=1`, or one per
                                        staff: `lines=5,1`) -> <staff-details><staff-lines>; on a perc staff every note
                                        is <unpitched> at its written position (write the single line's notes as B4)
    @part T "Tenor" T clef=G8 short="T"   the short name printed before later systems -> <part-abbreviation>
    @dir BAR AT TARGET KIND VALUE...    anything printed that is not a note, AT in quarters from the barline (1/2, 1.5)

TARGET is a part id, `P.2` for a part's second staff, or `*` for a mark printed once over the system (written on the
top part). KIND:

    dyn mp | cresc | dim | wedge-stop   a dynamic; a hairpin's start and end (cresc and dim open one)
    words cresc.   (rest of the line)   staff text and expression words, as printed; `words-i` italic, `words-b` bold
    tempo Gently q=66                   tempo words with an optional metronome mark (q, h, e, q. as the beat)
    chord Bb/D                          a chord symbol
    rehearsal 13                        a rehearsal mark (boxed); `rehearsal 13 circle` circled
    dashes start | dashes stop          the dashed line after a word ("rit. - - -"), from AT to AT
    segno | coda | fine | tocoda        the signs and their words
    repeat start | repeat end           repeat barlines (AT is ignored: start at the bar's left, end at its right)
    ending 1 start | ending 1 stop      first and second endings
    pedal start | pedal stop | pedal change
    8va start | 8va stop | 8vb start | 8vb stop
    breath | caesura                    after the note sounding at AT on that staff
    final                               the closing double bar (AT is ignored)
    barline light-light                 this bar's right barline in that style (light-light, heavy-light, dashed ...)
    clef F                              a clef change on that staff at AT (G, G8, F): a piano's left hand
    swing eighths                       the swing sign (two eighths = a triplet quarter and eighth), printed
    bracket start dashed | bracket stop a bracket line ("(optional) - - - -|"), dashed or solid
    staff-divide down                   the divisi arrows where one staff splits in two (down, up, up-down)

A tempo mark printed with more than a plain number, "Pop Rock (q = ca. 160)", is written as printed and then the
playback after a bar: `@dir 0 0 * tempo Pop Rock (♩ = ca. 160) | q=160`. The words print exactly as given.

Chord symbols are written as printed: root, then the rest of the symbol exactly as it stands ("m7(b5)", "6/9",
"maj9", "7sus4", "°7", "N.C."), then "/bass". The MusicXML kind is the nearest standard one; the printed text is kept.

`@pickup 3/2` makes the first bar, bar 0, a pickup of that many quarters (printed bar numbers are kept).
`@credit-page 3 text` is text printed on page 3 (a page number, a running footer).
`@lyrics-above T1 18-22` prints part T1's words above its staff in bars 18 to 22 (two parts on one staff singing
different words: the higher part's above, the lower's below); `@lyrics-above T1 18@0.5-22@0` from the note at or after
0.5 quarters into bar 18 up to the one at the start of bar 22 (AT as in @dir). The target may name a staff and a
voice: `P.2` the part's second staff, `T1.v1` only voice 1 (the first of ` | `) of T1's staff, `P.2.v2` voice 2 of
staff 2; with neither it is every staff and voice of the part.
`@dir 43 0 * ending 2 discontinue` ends a 2nd ending with its bracket open at the right, as printed.

On a note, `{flags}` (scoretext): ferm, acc, stac, ten, marc, mstac (a mezzo staccato), arp (arpeggiated chord;
arpup / arpdown with the arrowhead printed),
cue (small heads, an optional note), gr (a grace note: write it as a token of any length; it takes no time),
trem1 trem2 trem3 (strokes through the stem), fall, doit, scoop, plop, and tie65: a tie from this note into the
first note of bar 65 (a tie over a 1st ending into the 2nd). A syllable ending in `^` (`=low!^`) gets no extender line
where the page prints none. Also:

    gl, gldash          a glissando / slide line, solid or dashed, from this note to the next note of the same voice (in
                        this bar or a later one): <glissando type="start|stop" line-type="solid|dashed" number="1">; a
                        flagged note with no next note, or a rest next, is an error
    glx, gldashx        the same line to another staff or voice of the same part: it ends on the next note (in time)
                        flagged `glstop` on any staff of the part (number="2"; a bar 75 LH note up to a bar 76 RH
                        chord). The stop must come later in the file than the start: a later bar, or a lower staff
    fermdown            an inverted fermata below (<fermata type="inverted"/>); with `ferm`, one above and one below
    dashslur            the slur(s) starting on this note are dashed (line-type="dashed")
    s2start, s2stop     a second slur inside a slur: <slur number="2" type="start|stop"/>
    showacc             print the accidental of every pitch of this note that has one, or whose step the key alters,
                        (one pitch of a chord only: `!` after it, `Db4!,Eb4q`)
                        even where the key or bar does not need it (a flat reprinted after a tie, a courtesy flat)
    paren               this note's printed accidentals in parentheses (<accidental parentheses="yes">)
    wavystart, wavystop a wavy "shake" line: <ornaments><wavy-line type="start|stop"/></ornaments>
    slash               a slash notehead (<notehead>slash</notehead>)

A `?` after a pitch of a chord (`G2?,G3q`, scoretext) prints that head at cue size: that pitch's own <note> gets
<type size="cue">, the chord's other notes stay full size (<notehead> has no size in MusicXML 4.0, and <cue/> would mean
the note does not sound). Tuplets (scoretext `3`, `5`): every group prints its number; a group of sixteenth triplets
(three in an eighth) or a quintuplet is beamed on its own, with <tuplet bracket="no" show-number="actual"> when the
whole group is beamed notes, bracket="yes" otherwise. Divisions are 24 a quarter, raised (to a multiple of 24) only
where a file's durations need more (quintuplets: 120).

A second lyric line: `=first//second` on a note gives it a syllable on each line (`=-cle//-tor`, `=//O` for line 2
only). Hyphens and a trailing `_` (extender) work as on line 1; `=x//_` ends line 2's extender on that note.
A `~` inside a syllable is a space, for a syllable printed with one: `=Oh~(or~Mm)` is the one <text>Oh (or Mm)</text>.
`@dir 1 0 * tempo Gently (q=66)` prints the metronome mark in parentheses.
Accidentals are printed where the key and the bar so far need one, and wherever a pitch is spelled with `n` for a
courtesy natural.
"""
import re
import sys
from fractions import Fraction as F
from xml.sax.saxutils import escape

from . import scoretext
from .beaming import beams
from .events import finalize
from .harmony import harmony_xml
from .musicxml import CLEFS, note_xml

DIV = 24
CLEFS = {**CLEFS, 'perc': '<clef><sign>percussion</sign></clef>'}
TAGS = ('title', 'subtitle', 'composer', 'lyricist', 'arranger', 'rights', 'credit')
ARTIC = {'acc': '<accent/>', 'stac': '<staccato/>', 'ten': '<tenuto/>', 'marc': '<strong-accent type="up"/>',
         'mstac': '<detached-legato/>', 'fall': '<falloff/>', 'doit': '<doit/>', 'scoop': '<scoop/>', 'plop': '<plop/>'}
BEAT_UNIT = {'q': ('quarter', 0), 'h': ('half', 0), 'e': ('eighth', 0), 'q.': ('quarter', 1), 'h.': ('half', 1),
             'e.': ('eighth', 1), 'w': ('whole', 0)}
KEY_ORDER_SHARP, KEY_ORDER_FLAT = 'FCGDAEB', 'BEADGCF'


class Spec:
    """what note_xml needs to know: ticks, the bar's length (for a whole-bar rest) and which accidental to print"""

    def __init__(self, bar_beats, acc=()):
        self.bar_beats, self.accidentals = bar_beats, set(acc)

    def ticks(self, q):
        t = q * DIV
        if t != int(t): raise ValueError(f'{q} quarters is not a whole number of {DIV} divisions')
        return int(t)


def key_alters(fifths):
    if fifths >= 0: return {s: 1 for s in KEY_ORDER_SHARP[:fifths]}
    return {s: -1 for s in KEY_ORDER_FLAT[:-fifths]}


def parse(path):
    head = {'credits': [], 'keys': {}, 'meters': {}, 'parts': [], 'dirs': [], 'pickup': None, 'page_credits': [],
            'lyrics_above': [], 'meter_sym': {}}
    body = []
    for line in open(path, encoding='utf-8'):
        s = line.strip()
        if not s.startswith('@') or re.match(r'@[A-Z_0-9]+\s*=', s):  # a macro is the score text's own
            body.append(line); continue
        w = s[1:].split(None, 1)
        k, rest = w[0], (w[1] if len(w) > 1 else '')
        if k in TAGS: head['credits'].append((k, rest))
        elif k == 'key': b, f = rest.split(); head['keys'][int(b)] = int(f)
        elif k == 'pickup': head['pickup'] = F(rest.strip())
        elif k == 'credit-page': n, txt = rest.split(None, 1); head['page_credits'].append((int(n), txt))
        elif k == 'lyrics-above':
            m = re.fullmatch(r'(\S+)\s+(\d+)(?:@([\d./]+))?-(\d+)(?:@([\d./]+))?', rest.strip())
            if not m: raise ValueError(f'@lyrics-above: {s!r}')
            head['lyrics_above'].append([m.group(1), int(m.group(2)), int(m.group(4)),
                                         F(m.group(3) or 0), F(m.group(5)) if m.group(5) else None])
        elif k == 'meter':
            w_ = rest.split()
            if len(w_) not in (2, 3) or (len(w_) == 3 and w_[2] not in ('cut', 'common')): raise ValueError(f'@meter: {s!r}')
            n, d = w_[1].split('/'); head['meters'][int(w_[0])] = (int(n), int(d))
            if len(w_) == 3: head['meter_sym'][int(w_[0])] = w_[2]
        elif k == 'part':
            m = re.fullmatch(r'(\S+)\s+"([^"]*)"\s+(.*?)\s+clef=(\S+)(?:\s+lines=(\d+(?:,\d+)*))?(?:\s+short="([^"]*)")?', rest)
            if not m: raise ValueError(f'@part: {s!r}')
            head['parts'].append(dict(id=m.group(1), name=m.group(2), blocks=m.group(3).split(), clefs=m.group(4).split(','),
                                      lines=[int(x) for x in m.group(5).split(',')] if m.group(5) else None,
                                      short=m.group(6)))
        elif k == 'dir':
            f = rest.split(None, 4)
            if len(f) < 4: raise ValueError(f'@dir: {s!r}')
            head['dirs'].append(dict(bar=int(f[0]), at=F(f[1]), target=f[2], kind=f[3], value=f[4] if len(f) > 4 else ''))
        else: raise ValueError(f'unknown directive {s!r}')
    return head, body


def la_sel(target, pid, si, vi):
    """does an @lyrics-above target (`T1`, `P.2`, `T1.v1`, `P.2.v2`) cover staff si, voice vi (from 0) of part pid"""
    m = re.fullmatch(r'(.+?)(?:\.(\d+))?(?:\.v(\d+))?', target)
    return m.group(1) == pid and (m.group(2) is None or int(m.group(2)) == si + 1) and \
        (m.group(3) is None or int(m.group(3)) == vi + 1)


def bar_len(meters, m):
    n, d = meters[max(b for b in meters if b <= m)]
    return F(4 * n, d)


def accidentals(voices_of_staff, fifths):
    """{id(event): {(step, alter, oct)}}: the pitches of a staff's bar that print an accidental, from the key and what
    the bar has already altered on that line and space (all voices of the staff together, in time order)"""
    key = key_alters(fifths)
    evs = []
    for v in voices_of_staff:
        t = F(0)
        for e in v:
            evs.append((t, e)); t += 0 if e.get('grace') else e['dur']
    cur, out = {}, {}
    for t, e in sorted(evs, key=lambda x: x[0]):
        for p in e['pitches']:
            k = (p['step'], p['oct'])
            want = p['alter']
            have = cur.get(k, key.get(p['step'], 0))
            if (want != have or p.get('courtesy')) and not p.get('tie_stop'):
                out.setdefault(id(e), set()).add((p['step'], want, p['oct']))
            cur[k] = want
    return out


def emit_note(e, bar_beats, acc, voice, beam, staff, stem=None, lyr_place=None, perc=False):
    flags = e.get('flags', set())
    if 'slash' in flags: e['notehead'] = 'slash'
    if e.get('tup_new') and e.get('tup'):
        e['tup_attrs'] = (' bracket="no"' if e['tup_new'] == 'beamed' else ' bracket="yes"') + \
            (' show-number="actual"' if e['tup'] == 'start' else '')
    shown = {(s, a) for (s, a, o) in acc.get(id(e), ()) }
    s = note_xml(e, Spec(bar_beats, shown), voice=voice, beam=beam, staff=staff, stem=stem, fermata='ferm' in flags,
                 lyr_place=lyr_place)
    # an accidental is per pitch: note_xml decides by step and alter; keep it only on the octave that needs it
    if e['pitches'] and acc.get(id(e)):
        notes = s.split('</note>')
        for i, p in enumerate(e['pitches']):
            if (p['step'], p['alter'], p['oct']) not in acc[id(e)]:
                notes[i] = re.sub(r'<accidental>[a-z-]+</accidental>', '', notes[i])
        s = '</note>'.join(notes)
    if any(p.get('cue') for p in e['pitches']):
        # `G2?,G3q`: that pitch's own <note> at cue size
        notes = s.split('</note>')
        for i, p in enumerate(e['pitches']):
            if p.get('cue'): notes[i] = notes[i].replace('<type>', '<type size="cue">', 1)
        s = '</note>'.join(notes)
    if 'paren' in flags: s = s.replace('<accidental>', '<accidental parentheses="yes">')
    if perc:
        # a percussion staff: every note unpitched, at its written place; no accidentals
        s = re.sub(r'<pitch><step>([A-G])</step>(?:<alter>-?\d</alter>)?<octave>(\d)</octave></pitch>',
                   r'<unpitched><display-step>\1</display-step><display-octave>\2</display-octave></unpitched>', s)
        s = re.sub(r'<accidental[^>]*>[a-z-]+</accidental>', '', s)
    if 'dashslur' in flags: s = s.replace('<slur type="start" number="1"/>', '<slur type="start" number="1" line-type="dashed"/>', 1)
    extra = ''
    if e.get('gl_stop'): extra += f'<glissando type="stop" line-type="{e["gl_stop"][0]}" number="{e["gl_stop"][1]}"/>'
    if e.get('gl_start'): extra += f'<glissando type="start" line-type="{e["gl_start"][0]}" number="{e["gl_start"][1]}"/>'
    if 's2stop' in flags: extra += '<slur type="stop" number="2"/>'
    if 's2start' in flags: extra += '<slur type="start" number="2"' + (' line-type="dashed"' if 'dashslur' in flags else '') + '/>'
    if 'fermdown' in flags: extra += '<fermata type="inverted"/>'
    if 'wavystop' in flags: extra += '<ornaments><wavy-line type="stop"/></ornaments>'
    if 'wavystart' in flags: extra += '<ornaments><wavy-line type="start"/></ornaments>'
    arts = ''.join(ARTIC[f] for f in ('acc', 'stac', 'ten', 'marc', 'mstac', 'fall', 'doit', 'scoop', 'plop') if f in flags)
    if arts: extra += f'<articulations>{arts}</articulations>'
    for n in (1, 2, 3):
        if f'trem{n}' in flags: extra += f'<ornaments><tremolo type="single">{n}</tremolo></ornaments>'
    if 'arpup' in flags: extra += '<arpeggiate direction="up"/>'
    elif 'arpdown' in flags: extra += '<arpeggiate direction="down"/>'
    elif 'arp' in flags: extra += '<arpeggiate/>'
    if extra and e['pitches']:
        first = s.index('</note>')
        n0 = s[:first]
        n0 = n0.replace('</notations>', extra + '</notations>') if '<notations>' in n0 else \
            re.sub(r'(<lyric|$)', '<notations>' + extra.replace('\\', '\\\\') + r'</notations>\1', n0, count=1)
        s = n0 + s[first:]
    if e.get('lyric2') == '_' and e['pitches']:
        # `=x//_`: line 2's extender ends on this note
        first = s.index('</note>'); s = s[:first] + '<lyric number="2"><extend type="stop"/></lyric>' + s[first:]
    elif e.get('lyric2') and e['pitches']:
        t = e['lyric2']
        ext = t.endswith('_'); t = t.rstrip('_')
        syl = ('middle' if t.startswith('-') and t.endswith('-') and len(t) > 1 else 'end' if t.startswith('-')
               else 'begin' if t.endswith('-') else 'single')
        ly = f'<lyric number="2"><syllabic>{syl}</syllabic><text>{escape(t.strip("-").replace("~", " "))}</text>{"<extend/>" if ext else ""}</lyric>'
        first = s.index('</note>'); s = s[:first] + ly + s[first:]
    if 'cue' in flags: s = s.replace('<note>', '<note>', 1).replace('<type>', '<type size="cue">')
    if e.get('grace'):
        s = re.sub(r'<duration>\d+</duration>', '', s).replace('<note>', '<note><grace slash="yes"/>')
        s = re.sub(r'<note><grace slash="yes"/><chord/>', '<note><grace slash="yes"/><chord/>', s)
    return s


def direction(d, ticks, staff):
    k, v = d['kind'], d['value']
    off = f'<offset>{ticks}</offset>' if ticks else ''
    st = f'<staff>{staff}</staff>'
    above = 'above'
    if k == 'dyn': return f'<direction placement="below"><direction-type><dynamics><{v}/></dynamics></direction-type>{off}{st}</direction>' \
        if v in ('p', 'pp', 'ppp', 'mp', 'mf', 'f', 'ff', 'fff', 'sf', 'sfz', 'sfp', 'fp', 'rf', 'rfz', 'fz') else \
        f'<direction placement="below"><direction-type><dynamics><other-dynamics>{escape(v)}</other-dynamics></dynamics></direction-type>{off}{st}</direction>'
    if k in ('cresc', 'dim'):
        return f'<direction placement="below"><direction-type><wedge type="{"crescendo" if k == "cresc" else "diminuendo"}" number="1"/></direction-type>{off}{st}</direction>'
    if k == 'wedge-stop': return f'<direction><direction-type><wedge type="stop" number="1"/></direction-type>{off}{st}</direction>'
    if k.startswith('words'):
        a = {'words-i': ' font-style="italic"', 'words-b': ' font-weight="bold"'}.get(k, '')
        return f'<direction placement="{above}"><direction-type><words{a}>{escape(v)}</words></direction-type>{off}{st}</direction>'
    if k == 'tempo' and ' | ' in v:
        printed, play = v.rsplit(' | ', 1)
        m = re.fullmatch(r'([qhew]\.?)=(\d+)', play.strip())
        if not m: raise ValueError(f'tempo playback {play!r}: write it as q=160')
        u, dots = BEAT_UNIT[m.group(1)]
        bpm = F(int(m.group(2))) * {"quarter": 1, "half": 2, "eighth": F(1, 2), "whole": 4}[u] * (F(3, 2) if dots else 1)
        # the printed text as words; the mark itself kept as a metronome that does not print (its text is in the words)
        return (f'<direction placement="above"><direction-type><words font-weight="bold">{escape(printed.strip())}</words>'
                f'</direction-type><direction-type><metronome print-object="no"><beat-unit>{u}</beat-unit>'
                f'{"<beat-unit-dot/>" * dots}<per-minute>{m.group(2)}</per-minute></metronome></direction-type>'
                f'{off}{st}<sound tempo="{bpm}"/></direction>')
    if k == 'swing':
        note = lambda t, beam='', tup='': f'<metronome-note><metronome-type>{t}</metronome-type>{beam}{tup}</metronome-note>'
        trip = lambda ty: f'<metronome-tuplet type="{ty}" bracket="yes"><actual-notes>3</actual-notes><normal-notes>2</normal-notes></metronome-tuplet>'
        return ('<direction placement="above"><direction-type><metronome>'
                + note('eighth', '<metronome-beam number="1">begin</metronome-beam>')
                + note('eighth', '<metronome-beam number="1">end</metronome-beam>')
                + '<metronome-relation>equals</metronome-relation>'
                + note('quarter', '', trip('start')) + note('eighth', '', trip('stop'))
                + f'</metronome></direction-type>{off}{st}<sound><swing><first>2</first><second>1</second>'
                  '<swing-type>eighth</swing-type></swing></sound></direction>')
    if k == 'bracket':
        w = v.split()
        if w[0] == 'start':
            lt = w[1] if len(w) > 1 else 'dashed'
            return f'<direction placement="above"><direction-type><bracket type="start" number="1" line-end="none" line-type="{lt}"/></direction-type>{off}{st}</direction>'
        return f'<direction placement="above"><direction-type><bracket type="stop" number="1" line-end="down"/></direction-type>{off}{st}</direction>'
    if k == 'staff-divide':
        return f'<direction><direction-type><staff-divide type="{v}"/></direction-type>{off}{st}</direction>'
    if k == 'tempo':
        # "Gently q=66", or "Gently (q=66)" for a mark printed in parentheses
        m = re.search(r'\s*(\()?([qhew]\.?)=(\d+)(\))?\s*$', v)
        words = v[:m.start()] if m else v
        par = ' parentheses="yes"' if m and m.group(1) and m.group(4) else ''
        if m: m = re.match(r'(.*)', m.group(2) + '=' + m.group(3)); m = re.fullmatch(r'([qhew]\.?)=(\d+)', m.group(1))
        s = f'<direction placement="above">'
        if words.strip(): s += f'<direction-type><words font-weight="bold">{escape(words.strip())}</words></direction-type>'
        if m:
            u, dots = BEAT_UNIT[m.group(1)]
            s += f'<direction-type><metronome{par}><beat-unit>{u}</beat-unit>{"<beat-unit-dot/>" * dots}<per-minute>{m.group(2)}</per-minute></metronome></direction-type>'
        s += f'{off}{st}'
        if m: s += f'<sound tempo="{F(int(m.group(2))) * {"quarter": 1, "half": 2, "eighth": F(1, 2), "whole": 4}[u] * (F(3, 2) if dots else 1)}"/>'
        return s + '</direction>'
    if k == 'rehearsal':
        # `rehearsal 11` boxed, as most octavos print; `rehearsal 11 circle` circled
        enc, v = ('circle', v[:-len(' circle')]) if v.endswith(' circle') else ('square', v)
        return f'<direction placement="above"><direction-type><rehearsal enclosure="{enc}">{escape(v)}</rehearsal></direction-type>{off}{st}</direction>'
    if k == 'dashes':
        # the dashed line after a word ("rit. - - - -"): `dashes start` where the dashes begin, `dashes stop` where they end
        return f'<direction placement="above"><direction-type><dashes type="{v.strip()}" number="1"/></direction-type>{off}{st}</direction>'
    if k in ('segno', 'coda'): return f'<direction placement="above"><direction-type><{k}/></direction-type>{off}{st}</direction>'
    if k in ('fine', 'tocoda'):
        return f'<direction placement="above"><direction-type><words>{escape(v or ("Fine" if k == "fine" else "To Coda"))}</words></direction-type>{off}{st}</direction>'
    if k == 'pedal':
        t = {'start': 'start', 'stop': 'stop', 'change': 'change'}[v]
        return f'<direction placement="below"><direction-type><pedal type="{t}" line="no"/></direction-type>{off}{st}</direction>'
    if k in ('8va', '8vb'):
        t = 'stop' if v == 'stop' else ('down' if k == '8va' else 'up')
        return f'<direction placement="{"above" if k == "8va" else "below"}"><direction-type><octave-shift type="{t}" size="8"/></direction-type>{off}{st}</direction>'
    raise ValueError(f'@dir kind {k!r}')


CHORD = re.compile(r'([A-G])([#b\u266f\u266d]?)(.*?)(?:/([A-G])([#b\u266f\u266d]?))?')
KIND = [('maj13', 'major-13th'), ('maj11', 'major-11th'), ('maj9', 'major-ninth'), ('maj7', 'major-seventh'),
        ('m7b5', 'half-diminished'), ('m7(b5)', 'half-diminished'), ('\u00f87', 'half-diminished'),
        ('mmaj7', 'major-minor'), ('m13', 'minor-13th'), ('m11', 'minor-11th'), ('m9', 'minor-ninth'),
        ('m7', 'minor-seventh'), ('m6', 'minor-sixth'), ('dim7', 'diminished-seventh'), ('\u00b07', 'diminished-seventh'),
        ('dim', 'diminished'), ('\u00b0', 'diminished'), ('aug', 'augmented'), ('+', 'augmented'),
        ('sus2', 'suspended-second'), ('sus', 'suspended-fourth'), ('13', 'dominant-13th'), ('11', 'dominant-11th'),
        ('9', 'dominant-ninth'), ('7', 'dominant'), ('6', 'major-sixth'), ('m', 'minor'), ('5', 'power')]


def chord_xml(sym, ticks, staff):
    """a chord symbol as printed: <kind text> carries the printed suffix, the kind value the nearest standard one"""
    off = f'<offset>{ticks}</offset>' if ticks else ''
    if sym.replace('.', '').upper() == 'NC':
        return f'<harmony><root><root-step>C</root-step></root><kind text="{escape(sym)}">none</kind>{off}<staff>{staff}</staff></harmony>'
    m = CHORD.fullmatch(sym)
    if not m: raise ValueError(f'chord symbol not understood: {sym!r}')
    root, ra, rest, bass, ba = m.groups()
    alt = {'#': 1, '\u266f': 1, 'b': -1, '\u266d': -1}
    kind = 'major' if not rest else next((v for k, v in KIND if rest.startswith(k)), 'other')
    s = f'<harmony><root><root-step>{root}</root-step>' + (f'<root-alter>{alt[ra]}</root-alter>' if ra else '') + '</root>'
    s += f'<kind text="{escape(rest)}">{kind}</kind>'
    if bass: s += f'<bass><bass-step>{bass}</bass-step>' + (f'<bass-alter>{alt[ba]}</bass-alter>' if ba else '') + '</bass>'
    return s + f'{off}<staff>{staff}</staff></harmony>'


def build(path, out):
    global DIV
    DIV = 24
    head, body = parse(path)
    import tempfile, os
    tf = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8')
    # a courtesy natural: `Bn3` is B natural, printed with its sign
    tf.write(re.sub(r'(?<=[A-G])n(?=\d)', 'N', ''.join(body))); tf.close()
    raw, macros = scoretext.read_raw(tf.name)
    meters = head['meters'] or {1: (4, 4)}
    keys = head['keys'] or {1: 0}
    # a pickup: built as a short first bar and every bar one up, then numbered back as printed (bar 0, implicit)
    shift = 0
    show_time = {}
    if head['pickup'] is not None:
        shift = 1
        # bar references move with the bars: "&24" (bar 24 of this block) is "&25" inside
        raw = {b: {m + 1: re.sub(r'^&(\d+)$', lambda r_: f'&{int(r_.group(1)) + 1}', t.strip()) for m, t in bars.items()}
               for b, bars in raw.items()}
        for d in head['dirs']: d['bar'] += 1
        for la in head['lyrics_above']: la[1] += 1; la[2] += 1
        head['meter_sym'] = {k + 1: v for k, v in head['meter_sym'].items()}
        if 2 in head['meter_sym']: head['meter_sym'][1] = head['meter_sym'][2]   # the pickup prints bar 1's meter
        first = meters[min(meters)]
        q = head['pickup'] / 4
        pick = (q.numerator * 4, q.denominator * 4) if q.denominator < 4 else (q.numerator, q.denominator)
        meters = {**{k + 1: v for k, v in meters.items() if k >= 1}, 1: pick}
        meters.setdefault(2, first)
        show_time = {1: first, 2: None if meters[2] == first else meters[2]}
        keys = {k + 1: v for k, v in keys.items()}
        keys = {1 if k <= 1 else k: v for k, v in keys.items()}
        if 1 not in keys: keys[1] = keys[min(keys)]   # a key given from bar 1 holds in the pickup too
    nbars = max(max(b) for b in raw.values() if b)
    blocks = {}
    for b, bars in raw.items():
        blocks[b] = {}
        for m in range(1, nbars + 1):
            L = bar_len(meters, m)
            if m not in bars: blocks[b][m] = [[scoretext.parse_token('M', L)]]; continue
            txt = scoretext.bar_text(raw, macros, b, m)
            vs = []
            for v in txt.split(' | '):
                evs = []
                for t in v.split():
                    l2 = None
                    if '=' in t and '//' in t.split('=', 1)[1]:
                        base_, ly_ = t.split('=', 1); l1, l2 = ly_.split('//', 1)
                        t = base_ + ('=' + l1 if l1 else '')
                    cour = re.findall(r'([A-G])N(\d)', t)
                    t2 = re.sub(r'([A-G])N(\d)', r'\1\2', t)
                    e = scoretext.parse_token(t2, L)
                    for p in e['pitches']:
                        if (p['step'], str(p['oct'])) in cour: p['courtesy'] = True
                    if 'gr' in e['flags']: e['grace'] = True
                    if l2: e['lyric2'] = l2
                    if e['lyric'] and '~' in e['lyric']['text']: e['lyric']['text'] = e['lyric']['text'].replace('~', ' ')
                    evs.append(e)
                tot = sum(e['dur'] for e in evs if not e.get('grace'))
                if tot != L: raise ValueError(f'[{b}] bar {m}: {tot} quarters in a bar of {L}: {v!r}')
                vs.append(evs)
            blocks[b][m] = vs
    os.unlink(tf.name)
    # divisions: 24 a quarter unless a duration, a bar or a mark's place needs a finer grid (quintuplets)
    for x in [e['dur'] for b in blocks for m in blocks[b] for v in blocks[b][m] for e in v] + \
             [bar_len(meters, m) for m in range(1, nbars + 1)] + [d['at'] for d in head['dirs']]:
        q_ = F(x).denominator
        DIV = DIV * q_ // __import__('math').gcd(DIV, q_)
    # ties and tuplets along each voice; lyrics checked on a voice that has any
    for b in blocks:
        nv = max(len(blocks[b][m]) for m in blocks[b])
        for vi in range(nv):
            seq = [e for m in range(1, nbars + 1) if vi < len(blocks[b][m]) for e in blocks[b][m][vi] if not e.get('grace')]
            scoretext.link_ties(seq)
            for m in range(1, nbars + 1):
                if vi < len(blocks[b][m]): scoretext.mark_tuplet_groups(blocks[b][m][vi])
            # `{gl}` / `{gldash}`: a glissando line to the next note of this voice
            for i, e in enumerate(seq):
                lt = 'dashed' if 'gldash' in e['flags'] else 'solid' if 'gl' in e['flags'] else None
                if not lt: continue
                if i + 1 >= len(seq) or not seq[i + 1]['pitches']:
                    raise ValueError(f'[{b}] voice {vi + 1}: a glissando ({lt}) with no next note to end on')
                e['gl_start'] = (lt, 1); seq[i + 1]['gl_stop'] = (lt, 1)
            if any(e['lyric'] for e in seq) and nv == 1:
                finalize({m: blocks[b][m][0] for m in range(1, nbars + 1)}, b, nbars)
            # `=low!^`: a syllable whose melisma the page prints with no extender line
            for e in seq:
                if e['lyric'] and e['lyric']['text'].endswith('^'):
                    e['lyric']['text'] = e['lyric']['text'][:-1]; e['lyric']['extend'] = False
            # `{tie65}`: a tie from this note into the first note of bar 65 (over a 1st ending into the 2nd)
            for m in range(1, nbars + 1):
                if vi >= len(blocks[b][m]): continue
                for e in blocks[b][m][vi]:
                    for f_ in list(e['flags']):
                        mt = re.fullmatch(r'tie(\d+)', f_)
                        if not mt: continue
                        tgt = int(mt.group(1)) + shift
                        e['tie'] = True
                        nxt = next(x for x in blocks[b][tgt][vi] if not x.get('grace'))
                        for q_ in nxt['pitches']:
                            if any((q_['step'], q_['oct'], q_['alter']) == (r_['step'], r_['oct'], r_['alter']) for r_ in e['pitches']):
                                q_['tie_stop'] = True
    parts = head['parts']
    # `{glx}` / `{gldashx}` ... `{glstop}`: a glissando line to a note on another staff or voice of the same part
    for p in parts:
        found = []
        for si, b in enumerate(p['blocks']):
            for m in range(1, nbars + 1):
                for vi, v in enumerate(blocks[b][m]):
                    pos = F(0)
                    for e in v:
                        if e['flags'] & {'glx', 'gldashx', 'glstop'}: found.append((m, pos, si, vi, e))
                        if not e.get('grace'): pos += e['dur']
        found.sort(key=lambda x: x[:4])
        pending = []
        for m, pos, si, vi, e in found:
            if 'glstop' in e['flags']:
                if not pending: raise ValueError(f'part {p["id"]} bar {m - shift}: glstop with no glx before it')
                m0, si0, vi0, e0 = pending.pop(0)
                if (m, si, vi) < (m0, si0, vi0):
                    raise ValueError(f'part {p["id"]} bar {m - shift}: glstop would be written before its glx')
                e['gl_stop'] = e0['gl_start']
            if e['flags'] & {'glx', 'gldashx'}:
                if not e['pitches']: raise ValueError(f'part {p["id"]} bar {m - shift}: glx on a rest')
                e['gl_start'] = ('dashed' if 'gldashx' in e['flags'] else 'solid', 2)
                pending.append((m, si, vi, e))
        if pending: raise ValueError(f'part {p["id"]}: glx with no glstop after it')
    known = {p['id'] for p in parts} | {f"{p['id']}.{i + 1}" for p in parts for i in range(len(p['blocks']))} | {'*'}
    for d in head['dirs']:
        if d['target'] not in known: raise ValueError(f'@dir bar {d["bar"]}: no part {d["target"]!r}')
        if not 1 <= d['bar'] <= nbars: raise ValueError(f'@dir: no bar {d["bar"]}')
    # ---- the file
    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
         '<score-partwise version="4.0">']
    cr = dict((k, v) for k, v in head['credits'] if k != 'credit')
    if 'title' in cr: o.append(f'<work><work-title>{escape(cr["title"])}</work-title></work>')
    o.append('<identification>' + ''.join(f'<creator type="{k}">{escape(cr[k])}</creator>' for k in ('composer', 'lyricist', 'arranger') if k in cr)
             + (f'<rights>{escape(cr["rights"])}</rights>' if 'rights' in cr else '')
             + '<encoding><software>chorale.fullscore: whole-page transcription</software></encoding></identification>')
    for k, v in head['credits']:
        o.append(f'<credit page="1"><credit-type>{k}</credit-type><credit-words>{escape(v)}</credit-words></credit>'
                 if k != 'credit' else f'<credit page="1"><credit-words>{escape(v)}</credit-words></credit>')
    for n, v in head['page_credits']:
        o.append(f'<credit page="{n}"><credit-words>{escape(v)}</credit-words></credit>')
    o.append('<part-list>' + ''.join(f'<score-part id="{p["id"]}"><part-name>{escape(p["name"])}</part-name>'
                                     + (f'<part-abbreviation>{escape(p["short"])}</part-abbreviation>' if p.get('short') else '')
                                     + '</score-part>' for p in parts) + '</part-list>')
    for pi_, p in enumerate(parts):
        o.append(f'<part id="{p["id"]}">')
        ns = len(p['blocks'])
        for m in range(1, nbars + 1):
            L = bar_len(meters, m)
            fifths = keys[max(b for b in keys if b <= m)]
            s = f'<measure number="{m - shift}"' + (' implicit="yes"' if shift and m == 1 else '') + '>'
            left = [d for d in head['dirs'] if d['bar'] == m and d['kind'] in ('repeat', 'ending') and
                    (d['value'] == 'start' or d['value'].endswith(' start')) and (d['target'] == '*' or d['target'].split('.')[0] == p['id'])]
            if left:
                s += '<barline location="left">'
                if any(d['kind'] == 'repeat' for d in left): s += '<bar-style>heavy-light</bar-style>'
                for d in left:
                    if d['kind'] == 'ending': s += f'<ending number="{d["value"].split()[0]}" type="start"/>'
                if any(d['kind'] == 'repeat' for d in left): s += '<repeat direction="forward"/>'
                s += '</barline>'
            if m == 1 or m in meters or m in keys:
                s += f'<attributes>' + (f'<divisions>{DIV}</divisions>' if m == 1 else '')
                if m == 1 or m in keys: s += f'<key><fifths>{fifths}</fifths></key>'
                tm = show_time.get(m, meters[max(b for b in meters if b <= m)]) if (m == 1 or m in meters) else None
                sym = head['meter_sym'].get(m)
                sym = f' symbol="{sym}"' if sym else ''
                if tm: s += f'<time{sym}><beats>{tm[0]}</beats><beat-type>{tm[1]}</beat-type></time>'
                if m == 1:
                    if ns > 1: s += f'<staves>{ns}</staves>'
                    for i, c in enumerate(p['clefs']):
                        s += CLEFS[c].replace('<clef>', f'<clef number="{i + 1}">' if ns > 1 else '<clef>')
                    for i, n_ in enumerate(p['lines'] or []):
                        s += (f'<staff-details number="{i + 1}">' if ns > 1 else '<staff-details>') + \
                             f'<staff-lines>{n_}</staff-lines></staff-details>'
                s += '</attributes>'
            # directions and chord symbols, each placed by its offset from the barline
            for d in head['dirs']:
                if d['bar'] != m or d['kind'] in ('repeat', 'ending', 'final', 'breath', 'caesura', 'barline', 'clef'): continue
                tgt = d['target']
                if tgt == '*': mine, staff = pi_ == 0, 1
                else:
                    pid, _, sn = tgt.partition('.')
                    mine, staff = pid == p['id'], int(sn or 1)
                if not mine: continue
                if d['kind'] == 'chord':
                    s += chord_xml(d['value'], int(d['at'] * DIV), staff)
                else:
                    s += direction(d, int(d['at'] * DIV), staff)
            first = True
            for si, b in enumerate(p['blocks']):
                vs = blocks[b][m]
                perc = p['clefs'][min(si, len(p['clefs']) - 1)] == 'perc'
                acc = {} if perc else accidentals(vs, fifths)
                for v_ in vs:
                    for e in v_:
                        # `{showacc}`: every pitch that has an accidental, or whose step the key alters, prints it
                        if 'showacc' in e['flags'] and not perc:
                            acc.setdefault(id(e), set()).update((q_['step'], q_['alter'], q_['oct']) for q_ in e['pitches']
                                                                if q_['alter'] or key_alters(fifths).get(q_['step']))
                        # `Db4!`: that one pitch prints its accidental (one flat in a two-note chord)
                        if not perc and any(q_.get('showacc') for q_ in e['pitches']):
                            acc.setdefault(id(e), set()).update((q_['step'], q_['alter'], q_['oct'])
                                                                for q_ in e['pitches'] if q_.get('showacc'))
                for vi, v in enumerate(vs):
                    if not first: s += f'<backup><duration>{int(L * DIV)}</duration></backup>'
                    first = False
                    voice = si * 4 + vi + 1
                    stem = None if len(vs) == 1 else ('up' if vi == 0 else 'down')
                    bm = beams([e for e in v if not e.get('grace')], F(3, 2) if (lambda n, d: d == 8 and n % 3 == 0)(*meters[max(x for x in meters if x <= m)]) else F(1))
                    j, pos = 0, F(0)
                    clefs_here = [d for d in head['dirs'] if d['bar'] == m and d['kind'] == 'clef' and vi == 0 and
                                  d['target'] in ((p['id'],) if si == 0 else ()) + (f"{p['id']}.{si + 1}",)]
                    clef_at = lambda at_: ''.join('<attributes>' + CLEFS[d['value']].replace('<clef>', f'<clef number="{si + 1}">' if ns > 1 else '<clef>')
                                                  + '</attributes>' for d in clefs_here if d['at'] == at_)
                    for e in v:
                        if not e.get('grace'): s += clef_at(pos)
                        above = 'above' if any(la_sel(la[0], p['id'], si, vi) and (la[1], la[3]) <= (m, pos) and
                                               (m < la[2] or (m == la[2] and (la[4] is None or pos <= la[4])))
                                               for la in head['lyrics_above']) else None
                        if e.get('grace'):
                            s += emit_note(e, L, acc, voice, '', si + 1 if ns > 1 else None, stem, above, perc); continue
                        s += emit_note(e, L, acc, voice, bm[j], si + 1 if ns > 1 else None, stem, above, perc)
                        j += 1; pos += e['dur']
                        for d in head['dirs']:
                            if d['bar'] == m and d['kind'] in ('breath', 'caesura') and d['at'] == pos - e['dur'] and \
                                    d['target'] in (p['id'] if si == 0 else None, f"{p['id']}.{si + 1}"):
                                tag = '<breath-mark/>' if d['kind'] == 'breath' else '<caesura/>'
                                last = s.rindex('</note>')
                                n0 = s[:last]
                                k0 = n0.rindex('<note>')
                                seg = n0[k0:]
                                seg = seg.replace('</notations>', f'<articulations>{tag}</articulations></notations>') if '<notations>' in seg \
                                    else re.sub(r'(<lyric|$)', f'<notations><articulations>{tag}</articulations></notations>\\1', seg, count=1)
                                s = n0[:k0] + seg + s[last:]
                    if vi == 0: s += clef_at(L)
            right = [d for d in head['dirs'] if d['bar'] == m and (d['target'] == '*' or d['target'].split('.')[0] == p['id']) and
                     ((d['kind'] == 'repeat' and d['value'] == 'end') or (d['kind'] == 'ending' and d['value'].endswith(('stop', 'discontinue')))
                      or d['kind'] in ('final', 'barline'))]
            if right:
                s += '<barline location="right">'
                style = next((d['value'] for d in right if d['kind'] == 'barline'), None)
                s += '<bar-style>light-heavy</bar-style>' if any(d['kind'] in ('repeat', 'final') for d in right) else \
                    (f'<bar-style>{style}</bar-style>' if style else '')
                for d in right:
                    if d['kind'] == 'ending': s += f'<ending number="{d["value"].split()[0]}" type="{d["value"].split()[-1]}"/>'
                if any(d['kind'] == 'repeat' for d in right): s += '<repeat direction="backward"/>'
                s += '</barline>'
            o.append(s + '</measure>')
        o.append('</part>')
    o.append('</score-partwise>')
    open(out, 'w', encoding='utf-8').write('\n'.join(o) + '\n')
    return out


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
