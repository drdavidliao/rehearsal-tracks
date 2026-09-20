"""Folding an OMR export into a hand-built score.

OMR output is never right, but it is usually right about the accompaniment, which
is the part nobody wants to type in by hand.  These helpers let a piece script
keep the OMR's piano while repairing it bar by bar against the scan: retie a note
the recogniser split, replace a garbled bar with a known-good one, or write a
short replacement bar in the compact notation and drop it in.

Everything here works on xml.etree elements, because that is what the OMR file
parses to and rewriting it in place is less work than re-encoding it.
"""
import copy
import re
import xml.etree.ElementTree as ET
from fractions import Fraction as F

from .events import DUR, TYPE
from .musicxml import words_xml

_TOKEN = re.compile(r'(R|[A-G][#b]?\d(?:,[A-G][#b]?\d)*)([whqest])(\.?)(~?)')
_PITCH = re.compile(r'([A-G])(#|b)?(\d)')


def parts_by_id(root):
    """-> {part id: {measure number as written: measure element}}"""
    return {p.get('id'): {m.get('number'): m for m in p.findall('measure')}
            for p in root.findall('part')}


def notes(meas):
    """The measure's notes, chord members excluded — one per rhythmic slot."""
    return [n for n in meas.findall('note') if n.find('chord') is None]


def add_tie(meas, i, j):
    """Tie slot i to slot j, chord members included.

    Both <tie> (for playback) and <tied> (for the printed slur) are written, in
    the order MusicXML wants: <tie> right after <duration>, <tied> inside
    <notations>, which is inserted before any <lyric> or <play>.
    """
    ns = notes(meas)

    def group(n):
        allnotes = list(meas.findall('note'))
        k = allnotes.index(n)
        g = [n]
        for x in allnotes[k + 1:]:
            if x.find('chord') is None:
                break
            g.append(x)
        return g

    for kind, n0 in (('start', ns[i]), ('stop', ns[j])):
        for n in group(n0):
            if any(t.get('type') == kind for t in n.findall('tie')):
                continue
            t = ET.Element('tie')
            t.set('type', kind)
            d = n.find('duration')
            n.insert(list(n).index(d) + 1, t)
            nots = n.find('notations')
            if nots is None:
                nots = ET.Element('notations')
                kids = list(n)
                idx = len(kids)
                for q, k in enumerate(kids):
                    if k.tag in ('lyric', 'play'):
                        idx = q
                        break
                n.insert(idx, nots)
            td = ET.SubElement(nots, 'tied')
            td.set('type', kind)


def strip(meas, *tags):
    for n in meas.findall('note'):
        for nots in n.findall('notations'):
            for tag in tags:
                for x in nots.findall(tag):
                    nots.remove(x)
            if len(nots) == 0:
                n.remove(nots)


def measure_from(div, body, beats=4):
    """Write a replacement bar in the compact notation, get an element back.

    Tokens are pitch(es) + duration + optional dot and `~` tie, or `R` + duration
    for a rest; `|` backs up to the bar line and starts the next voice.

        measure_from(2, 'C4q. G3e Re G3q G3e | C3q. G2e C3h')
    """
    m = ET.Element('measure')
    a = ET.SubElement(m, 'attributes')
    ET.SubElement(a, 'divisions').text = str(div)
    voice = 1
    pending_tie = False
    for tok in body.split():
        if tok == '|':
            b = ET.SubElement(m, 'backup')
            ET.SubElement(b, 'duration').text = str(beats * div)
            voice += 1
            continue
        mm = _TOKEN.fullmatch(tok)
        if not mm:
            raise ValueError(f'not a token: {tok!r}')
        pitches, d, dot, tie = mm.groups()
        dur = DUR[d] * (F(3, 2) if dot else 1)
        durn = int(dur * div)
        plist = [] if pitches == 'R' else [_pitch(x) for x in pitches.split(',')]
        for pi, pch in enumerate(plist or [None]):
            n = ET.SubElement(m, 'note')
            if pi > 0:
                ET.SubElement(n, 'chord')
            if pch is None:
                ET.SubElement(n, 'rest')
            else:
                pe = ET.SubElement(n, 'pitch')
                ET.SubElement(pe, 'step').text = pch['step']
                if pch['alter']:
                    ET.SubElement(pe, 'alter').text = str(pch['alter'])
                ET.SubElement(pe, 'octave').text = str(pch['oct'])
            ET.SubElement(n, 'duration').text = str(durn)
            if pch is not None and pending_tie:
                ET.SubElement(n, 'tie').set('type', 'stop')
            if pch is not None and tie:
                ET.SubElement(n, 'tie').set('type', 'start')
            ET.SubElement(n, 'voice').text = str(voice)
            ET.SubElement(n, 'type').text = TYPE[DUR[d]]
            if dot:
                ET.SubElement(n, 'dot')
            if pch is not None and DUR[d] < beats:
                ET.SubElement(n, 'stem').text = 'up' if voice == 1 else 'down'
            if pch is not None and (pending_tie or tie):
                nots = ET.SubElement(n, 'notations')
                if pending_tie:
                    ET.SubElement(nots, 'tied').set('type', 'stop')
                if tie:
                    ET.SubElement(nots, 'tied').set('type', 'start')
        pending_tie = bool(tie) and bool(plist)
    _beam_measure(m, div, voice)
    return m


def _pitch(p):
    step, acc, octv = _PITCH.fullmatch(p).groups()
    return {'step': step, 'alter': {'#': 1, 'b': -1}.get(acc, 0), 'oct': int(octv)}


def _beam_measure(m, div, voices):
    """Beam a written-out measure: flagged notes, grouped by beat, per voice."""
    for v in range(1, voices + 1):
        evs = []
        pos = F(0)
        for n in m.findall('note'):
            if n.findtext('voice') != str(v) or n.find('chord') is not None:
                continue
            dq = F(int(n.findtext('duration')), div)
            evs.append((n, pos, dq))
            pos += dq
        groups, cur = [], []
        for n, pos, dq in evs:
            if n.find('rest') is None and dq < 1:
                if cur and int(cur[-1][1]) != int(pos):
                    groups.append(cur)
                    cur = []
                cur.append((n, pos, dq))
            else:
                if cur:
                    groups.append(cur)
                    cur = []
        if cur:
            groups.append(cur)
        for g in groups:
            if len(g) < 2:
                continue
            for k, (n, pos, dq) in enumerate(g):
                lv1 = 'begin' if k == 0 else 'end' if k == len(g) - 1 else 'continue'
                b = ET.Element('beam')
                b.set('number', '1')
                b.text = lv1
                ins = [b]
                if dq < F(1, 2):
                    pv = g[k - 1][2] < F(1, 2) if k > 0 else False
                    nx = g[k + 1][2] < F(1, 2) if k + 1 < len(g) else False
                    v2 = ('continue' if pv and nx else 'begin' if nx else 'end' if pv
                          else ('forward hook' if k == 0 else 'backward hook'))
                    b2 = ET.Element('beam')
                    b2.set('number', '2')
                    b2.text = v2
                    ins.append(b2)
                kids = list(n)
                idx = len(kids)
                for q, kd in enumerate(kids):
                    if kd.tag in ('notations', 'lyric'):
                        idx = q
                        break
                for off, el in enumerate(ins):
                    n.insert(idx + off, el)


def import_staff(src, staff, spec, keep_words=(), voice_offset=0):
    """Re-emit one imported measure as one staff of a multi-staff part.

    The source's own divisions are rescaled to the target's, voices are pushed
    clear of the other staff's, lyrics and noteheads are dropped, and directions
    are kept only where they say something: dynamics, hairpins, and the words the
    caller asked for.  Returns (xml, beats spanned).
    """
    div = None
    for a in src.findall('attributes'):
        if a.find('divisions') is not None:
            div = int(a.findtext('divisions'))
    if div is None:
        raise ValueError('imported measure states no divisions')
    scale = F(spec.divisions, div)
    s = ''
    pos = F(0)
    mx = F(0)
    for el in src:
        if el.tag == 'note':
            n = copy.deepcopy(el)
            for tag in ('lyric', 'staff', 'notehead'):
                for x in n.findall(tag):
                    n.remove(x)
            d = n.find('duration')
            dq = F(int(d.text)) * scale
            d.text = str(int(dq))
            rest = n.find('rest')
            if rest is not None and rest.get('measure') == 'yes':
                for x in n.findall('type'):
                    n.remove(x)
            v = n.find('voice')
            if v is None:
                v = ET.Element('voice')
                v.text = '1'
                n.insert(list(n).index(d) + 1 + len(n.findall('tie')), v)
            if voice_offset:
                v.text = str(int(v.text) + voice_offset)
            st = ET.Element('staff')
            st.text = str(staff)
            kids = list(n)
            ins = len(kids)
            for i, k in enumerate(kids):
                if k.tag in ('beam', 'notations', 'lyric', 'play'):
                    ins = i
                    break
            n.insert(ins, st)
            if n.find('chord') is None:
                pos += dq
            mx = max(mx, pos)
            s += ET.tostring(n, encoding='unicode')
        elif el.tag == 'backup':
            dq = F(int(el.findtext('duration'))) * scale
            pos -= dq
            s += f'<backup><duration>{int(dq)}</duration></backup>'
        elif el.tag == 'forward':
            dq = F(int(el.findtext('duration'))) * scale
            pos += dq
            mx = max(mx, pos)
            s += f'<forward><duration>{int(dq)}</duration></forward>'
        elif el.tag == 'direction':
            dt = el.find('direction-type')
            if dt is None:
                continue
            child = list(dt)[0]
            if child.tag == 'dynamics':
                s += (f'<direction placement="below"><direction-type>'
                      f'{ET.tostring(child, encoding="unicode")}</direction-type>'
                      f'<staff>{staff}</staff></direction>')
            elif child.tag == 'wedge':
                s += (f'<direction><direction-type>'
                      f'{ET.tostring(child, encoding="unicode")}</direction-type>'
                      f'<staff>{staff}</staff></direction>')
            elif child.tag == 'words' and (child.text or '').strip() in keep_words:
                s += words_xml(child.text.strip(), italic=True, bold=True).replace(
                    '</direction>', f'<staff>{staff}</staff></direction>')
    full = spec.ticks(spec.bar_beats)
    if pos < full:
        s += f'<forward><duration>{int(full - pos)}</duration></forward>'
    return s, mx
