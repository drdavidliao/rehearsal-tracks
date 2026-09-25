#!/usr/bin/env python3
"""Follow-along score videos from a MusicXML and the rehearsal mp3s made from it (SKILL.md Step 10).

    python3 score_video.py score.musicxml "Shenandoah - Balanced.mp3" \
        "Shenandoah - (Tenor 1) predominant.mp3" "Shenandoah - (Tenor 2) predominant.mp3" ...
        [--display print.musicxml] [-o OUT_DIR] [--part "Tenor 1=Tenor"]
        [--staves "Tenor 1+Tenor 2,Baritone+Bass" | --open] [--pulse 8] [--dark]
        [--clip START,SECONDS] [--stills T1,T2,...] [--staff-px 44] [--jobs N] [--proof DIR]

The MusicXML is the one the audio was rendered from (one part per staff, as Sibelius and
Cantai sing it). When that is a Cantai learning file, give the print-faithful file as
--display: it is shown instead (normal words, slurs and ties), after a check that it has
the same parts, bars, notes and tempo marks. --display can also be the closed score the
singers hold (two parts to a staff, fewer parts than the open file): then it is shown as it
is, and whose each notehead, rest and syllable is comes from the open file (the parts
singing that pitch, resting, or starting a syllable at that moment; a second lyric line
goes to the lower part), with voice 1 / voice 2 as the fallback. Repeat signs and first
and second endings are unrolled: the lights follow the bars in the order they are played,
turning back a screen for a repeat. Each mp3 gives one mp4 of the same name beside it (or
in OUT_DIR), and everything the run prints, every check included, also goes to
"<title> - video checks.txt" there; --proof DIR writes one unlit PNG per screen, for the
comparison with the print PDF that SKILL.md Step 10 asks for:

  a Balanced mp3          -> every sung part lights up in its own colour
  "(Part) predominant", "(Part) part-left", "Solo ... " mp3s
                          -> only that part lights up; every other part, piano too, is grey,
                             and that part's staff is never hidden, so its rests stay on screen

A note lights (its colour, and a soft halo) while it sounds; its syllable stays lit from its
note until the next syllable or rest, so a melisma or a tie keeps its word lit. A note or
word two parts share gets its halo and ink in stacked bands, the higher part's colour on
top (side by side would read as one part singing the first half, the other the second).
A tie lights while either of its notes sounds; in a part's own video the other parts' ties
and slurs are grey with their notes. A rest lights the same way, and a
bar under it (above the staff for the upper of two voices) runs from where the rest starts
to where it ends as the other staves print that time, filling in jumps of one pulse: each
part's pulse is the coarsest note value that 95% of the bars it sings keep to (eighths in a
piece of eighths with one bar of sixteenths; --pulse sets it). Each jump lands where the
other staves print that time, so the fill meets the piano's notes as they sound and a
singer who cannot count rests sees the beats go by. Pages turn up to a second before the
next page's first note, never before the last note on the old page has begun. Staves empty
for a whole system are hidden, as in a printed score. Black on white by default; --dark for
light notation on a dark screen.

Closed score by default: the sung parts are paired two to a staff, as the singers hold
them (consecutive sung parts in score order, soloists left on their own staff; --staves
names the pairs, --open keeps one part per staff). A bar where the two parts share rhythm,
ties and words becomes chords with one lyric line; elsewhere the upper part is voice 1
(stems up), the lower voice 2 (stems down), and the lower part gets its own lyric line
only where its words differ (SKILL.md 7.2 and 7.4). A tie never changes voice: a merged
bar tied to a divided one is divided too. Crossed parts are never chorded (7.6).
Accompaniment staves are shown as written.

Timing, as stem_vs_score.py does it: beats become seconds with the score's tempo marks,
and the line-up is anchored where the audio first sounds against where the score first
has a note; only the tempo is refined, on note onsets found in the audio. Then it is
re-anchored after every fermata (on a note, a rest or a barline): playback holds a
fermata longer than written, by an amount the file does not say, and everything after
it runs that much late. Each hold is
measured by aligning the score's pitch content with the audio's (chroma, dynamic time
warping) and refined on the onsets that follow; the report gives each fermata's hold and
checks every 15 s of the lights against the pitch alignment, naming the bar of any stretch
more than 100 ms out. (Matching each light to the nearest onset in the audio cannot catch
this: with a piano in sixteenths there is always an onset near enough, and a 0.75 s lag
measured as -2 ms.) Each finished mp4 is checked too: its audio against the mp3, and its
frames against the times they were meant for.
The video has a variable frame rate: one frame per change of lights or page,
each shown from the exact millisecond of the change, so nothing is rounded to a frame grid
and nothing is encoded twice. With several mp3s, each renders in its own process, one per
CPU core (--jobs).

Needs verovio, cairosvg, lxml, numpy, pillow, fonttools and brotli (the Leipzig font fix,
8.4) and ffmpeg with libx264; stem_vs_score.py and verify.py beside it. D.C., D.S. and codas are not
followed (repeat signs and endings are). Seven videos of a 4:48 piece took 9 minutes on 2
cores.
"""
import sys, os, io, re, copy, math, argparse, subprocess, zipfile, tempfile, shutil, bisect
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction as Fr
import numpy as np
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stem_vs_score import load_score, beats_to_sec, envelope, runs  # noqa: E402
from verify import lyric_line_runs, sung_positions, parts_on  # noqa: E402

# Okabe-Ito, colour-blind safe; neighbours on a shared staff get well-separated hues
PALETTE = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#B07A00', '#7F3C8D', '#00798C', '#8C510A']
GREY = '#B4B4B4'
# dark mode, the default: for backlit screens, not paper. Bright hues that keep apart on a dark
# ground; the same order (the four parts sharing staves first)
PALETTE_DARK = ['#56B4E9', '#FF9F43', '#4CD98A', '#F48FD0', '#F0E442', '#B39DFF', '#45D6D0', '#E8B070']
THEME = {}


def set_theme(dark):
    """Light (black on white, like the printed page) by default; --dark for a backlit screen."""
    if dark:
        THEME.update(dark=True, bg=np.array([28, 28, 30], np.float32), ink=np.array([225, 225, 225], np.float32),
                     grey='#8C8C8C', tint=0.5, lift=0.35)
    else:
        THEME.update(dark=False, bg=np.array([255, 255, 255], np.float32),
                     ink=np.array([0, 0, 0], np.float32), grey=GREY, tint=0.30, lift=0.0)


set_theme(False)
STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
NOTE_ORDER = ['grace', 'cue', 'chord', 'pitch', 'unpitched', 'rest', 'duration', 'tie', 'instrument',
              'footnote', 'level', 'voice', 'type', 'dot', 'accidental', 'time-modification', 'stem',
              'notehead', 'notehead-text', 'staff', 'beam', 'notations', 'lyric', 'play', 'listen']


# ----------------------------------------------------------------------------- reading the score

def read_xml(path):
    if path.lower().endswith('.mxl'):
        z = zipfile.ZipFile(path)
        cont = etree.fromstring(z.read('META-INF/container.xml'))
        full = cont.find('.//{*}rootfile').get('full-path')
        return etree.fromstring(z.read(full))
    return etree.parse(path, etree.XMLParser(remove_blank_text=True, recover=True)).getroot()


def hexrgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32)


def midi(note):
    p = note.find('pitch')
    if p is None:
        return None
    return 12 * (int(p.findtext('octave')) + 1) + STEP[p.findtext('step')] + int(float(p.findtext('alter') or 0))


def _letters(t):
    return re.sub(r'[^a-z]', '', (t or '').lower())


def lyric1(note):
    """The first lyric line's (syllabic, text), or None."""
    ls = note.findall('lyric')
    if not ls:
        return None
    ls.sort(key=lambda l: int(re.sub(r'\D', '', l.get('number') or '1') or 1))
    t = ''.join(x.text or '' for x in ls[0].findall('text'))
    return (ls[0].findtext('syllabic') or 'single', t) if t.strip() else None


def ties(note):
    ts = [t.get('type') for t in note.findall('tie')] + [t.get('type') for t in note.iter('tied')]
    return 'start' in ts, 'stop' in ts


def scan_part(pi, part, prefix='n'):
    """Assign an id to every note and return (notes, measure starts) in quarters."""
    div, pos, notes, starts, k = 1, Fr(0), [], [], 0
    for mi, m in enumerate(part.findall('measure')):
        starts.append(pos)
        t, mx, last_on = pos, pos, pos
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= Fr(int(e.findtext('duration')), div)
            elif e.tag == 'forward':
                t += Fr(int(e.findtext('duration')), div)
            elif e.tag == 'note':
                nid = f'{prefix}{pi}x{k}'
                k += 1
                e.set('id', nid)
                grace = e.find('grace') is not None
                chord = e.find('chord') is not None
                d = Fr(0) if grace else Fr(int(e.findtext('duration') or 0), div)
                on = last_on if chord else t
                ts, tp = ties(e)
                notes.append(dict(id=nid, part=pi, mi=mi, el=e, on=on, dur=d, rel=on - pos,
                                  voice=e.findtext('voice') or '1', rest=e.find('rest') is not None,
                                  chord=chord, grace=grace, midi=midi(e), tie_start=ts, tie_stop=tp,
                                  lyric=lyric1(e), type=e.findtext('type'), dots=len(e.findall('dot')),
                                  tmod=e.find('time-modification') is not None))
                if not chord:
                    last_on = t
                    t += d
            mx = max(mx, t)
        pos = mx
    return notes, starts


def syllable_windows(notes):
    """Per sung note with a syllable: (start, end) in quarters, the end running on through the
    following syllable-less notes (a melisma or a tie) and stopping at a rest or the next syllable."""
    seq = [n for n in notes if not n['chord'] and not n['grace'] and n['voice'] == '1']
    out, cur = {}, None
    for n in seq:
        if n['rest']:
            cur = None
        elif n['lyric']:
            cur = n['id']
            out[cur] = [n['on'], n['on'] + n['dur']]
        elif cur:
            out[cur][1] = n['on'] + n['dur']
    return out


# ----------------------------------------------------------------------------- closed score

def lcm(a, b):
    return a * b // math.gcd(a, b)


def normalise_divisions(part, D):
    div = 1
    for m in part.findall('measure'):
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
                e.find('divisions').text = str(D)
            for d in ([e.find('duration')] if e.tag in ('note', 'backup', 'forward') else []) + \
                     ([e.find('offset')] if e.tag in ('direction', 'harmony') else []):
                if d is not None and d.text:
                    d.text = str(int(Fr(int(float(d.text)) * D, div)))


def set_child(note, tag, text):
    old = note.find(tag)
    if old is not None:
        old.text = text
        return
    new = etree.Element(tag)
    new.text = text
    idx = NOTE_ORDER.index(tag)
    at = len(note)
    for i, c in enumerate(note):
        if c.tag in NOTE_ORDER and NOTE_ORDER.index(c.tag) > idx:
            at = i
            break
    note.insert(at, new)


def strip(note, *tags):
    for t in tags:
        for c in note.findall(t):
            note.remove(c)


def bar_events(notes, mi):
    return [n for n in notes if n['mi'] == mi]


def mergeable(eu, el):
    if len(eu) != len(el) or not eu:
        return False
    for a, b in zip(eu, el):
        if a['chord'] or b['chord'] or a['grace'] or b['grace'] or a['voice'] != '1' or b['voice'] != '1':
            return False
        for k in ('rel', 'dur', 'rest', 'type', 'dots', 'tie_start', 'tie_stop', 'lyric', 'tmod'):
            if a[k] != b[k]:
                return False
        if not a['rest'] and (a['midi'] is None or b['midi'] is None or b['midi'] > a['midi']):
            return False          # crossed parts are never chorded (SKILL.md 7.6)
    return True


def build_pair(up, lo, nu, nl, pid, name, abbr, owners, syl_holder):
    """Write parts `up` and `lo` onto one staff; return the new <part>.
    owners[note id] -> set of part indices sounding that notehead;
    syl_holder[(part, note id)] -> note id whose printed syllable that part reads."""
    D = 1
    for p in (up, lo):
        for d in p.iter('divisions'):
            D = lcm(D, int(d.text))
    normalise_divisions(up, D)
    normalise_divisions(lo, D)
    mu, ml = up.findall('measure'), lo.findall('measure')
    lo_el = {e.get('id'): e for e in lo.iter('note')}
    if len(mu) != len(ml):
        sys.exit(f'{name}: the two parts have {len(mu)} and {len(ml)} bars; cannot share a staff')
    pu, pl = nu[0]['part'] if nu else None, nl[0]['part'] if nl else None
    ev = [(bar_events(nu, i), bar_events(nl, i)) for i in range(len(mu))]
    merged = [mergeable(a, b) for a, b in ev]
    changed = True
    while changed:                            # a tie never changes voice
        changed = False
        for i, (a, b) in enumerate(ev):
            if not merged[i]:
                continue
            firsts = [x[0] for x in (a, b) if x]
            lasts = [x[-1] for x in (a, b) if x]
            if (i > 0 and not merged[i - 1] and any(n['tie_stop'] for n in firsts)) or \
               (i + 1 < len(ev) and not merged[i + 1] and any(n['tie_start'] for n in lasts)):
                merged[i] = False
                changed = True
    part = etree.Element('part', id=pid)
    lo_clef = None
    # a lower-voice extender runs on to the next syllable-less note in its voice, and 7.4 moves the
    # lower part's words to line 1 where both sing them: end it on its last held note (SKILL.md 7.6,
    # Verovio only)
    line2 = {'open': False, 'last': None, 'num': '2'}
    up_el = {e.get('id'): e for e in up.iter('note')}

    def extends(el):
        return any(ly.find('extend') is not None and ly.find('extend').get('type') != 'stop'
                   for ly in el.findall('lyric'))

    def close_line2():
        if line2['open'] and line2['last'] is not None:
            ly = etree.SubElement(line2['last'], 'lyric', number=line2['num'])
            etree.SubElement(ly, 'extend', type='stop')
        line2['open'], line2['last'] = False, None
    for i, (mU, mL) in enumerate(zip(mu, ml)):
        a, b = ev[i]
        m = etree.SubElement(part, 'measure', {k: v for k, v in mU.attrib.items() if k != 'width'})
        la = mL.find('attributes')
        if la is not None and la.find('clef') is not None:
            lo_clef = copy.deepcopy(la.find('clef'))
            lo_clef.attrib.pop('number', None)
        clef_due = la is not None and la.find('clef') is not None
        # one line only for the same words at the same moments: a staggered entrance needs its own
        # copy under its own note (SKILL.md 7.4)
        sa = [(n['rel'], n['lyric']) for n in a if n['lyric']]
        sb = [(n['rel'], n['lyric']) for n in b if n['lyric']]
        same_words = sa == sb
        # which printed syllable each part reads in this bar
        ha = [n['id'] for n in a if n['lyric']]
        hb = [n['id'] for n in b if n['lyric']]
        for h in ha:
            syl_holder[(pu, h)] = h
        # one line for both, but where only the lower part holds a syllable over more notes, print
        # its copy, with the extender (SKILL.md 7.4): the upper part reads it from there
        take = set()
        if same_words and not merged[i]:
            take = {y for x, y in zip(ha, hb) if extends(lo_el[y]) and not extends(up_el[x])}
        if merged[i] or same_words:
            for x, y in zip(ha, hb):
                if y in take:
                    syl_holder[(pu, x)] = y
                    syl_holder[(pl, y)] = y
                else:
                    syl_holder[(pl, y)] = x
        else:
            for y in hb:
                syl_holder[(pl, y)] = y
        taken_up = {x for x, y in zip(ha, hb) if y in take}
        partner = {x['id']: y for x, y in zip(a, b)} if merged[i] else {}
        t = Fr(0)
        placed_clef = False
        for e in mU:
            if e.tag == 'print':
                continue
            c = copy.deepcopy(e)
            if e.tag == 'attributes':
                for cl in c.findall('clef'):
                    c.remove(cl)
                if clef_due and lo_clef is not None and not placed_clef:
                    idx = len(c)
                    for j, ch in enumerate(c):
                        if ch.tag in ('staff-details', 'transpose', 'directive', 'measure-style', 'for-part'):
                            idx = j
                            break
                    c.insert(idx, copy.deepcopy(lo_clef))
                    placed_clef = True
                m.append(c)
                continue
            if e.tag != 'note':
                if e.tag in ('backup', 'forward'):
                    q = int(e.findtext('duration'))
                    t += q if e.tag == 'forward' else -q
                m.append(c)
                continue
            if c.find('chord') is None and c.find('grace') is None:
                t += int(c.findtext('duration') or 0)
            n_id = c.get('id')
            owners.setdefault(n_id, set()).add(pu)
            if n_id in taken_up:
                strip(c, 'lyric')
            if merged[i]:
                set_child(c, 'voice', '1')
                m.append(c)
                y = partner.get(n_id)
                if y is not None and not y['rest']:
                    if y['midi'] == midi(e):
                        owners[n_id].add(pl)                    # unison: one notehead, both parts
                    else:
                        lc = copy.deepcopy(lo_el[y['id']])
                        strip(lc, 'lyric', 'beam', 'stem')
                        nots = lc.find('notations')
                        if nots is not None:
                            for ch in list(nots):
                                if ch.tag != 'tied':
                                    nots.remove(ch)
                        lc.insert(0, etree.Element('chord'))
                        set_child(lc, 'voice', '1')
                        m.append(lc)
                        owners.setdefault(lc.get('id'), set()).add(pl)
                elif y is not None:
                    owners[n_id].add(pl)                        # the shared rest
            else:
                set_child(c, 'voice', str(2 * int(c.findtext('voice') or 1) - 1))
                if c.find('rest') is None:
                    set_child(c, 'stem', 'up')
                m.append(c)
        if clef_due and lo_clef is not None and not placed_clef:
            at = etree.Element('attributes')
            at.append(copy.deepcopy(lo_clef))
            m.insert(0, at)
        if merged[i]:
            if hb:
                close_line2()
            continue
        if t:
            bk = etree.SubElement(m, 'backup')
            etree.SubElement(bk, 'duration').text = str(t)
        # where both voices rest at the same moment for the same time, one rest is printed, lit
        # for both parts: two stacked copies of every rest read as clutter
        up_rests = {(x['rel'], x['dur']): x['id'] for x in a if x['rest'] and not x['chord']}
        for e in mL:
            if e.tag not in ('note', 'backup', 'forward'):
                continue
            c = copy.deepcopy(e)
            if e.tag == 'note':
                owners.setdefault(c.get('id'), set()).add(pl)
                me = next((x for x in b if x['id'] == c.get('id')), None)
                if me is not None and me['rest'] and (me['rel'], me['dur']) in up_rests:
                    c.set('print-object', 'no')
                    owners.setdefault(up_rests[(me['rel'], me['dur'])], set()).add(pl)
                set_child(c, 'voice', str(2 * int(c.findtext('voice') or 1)))
                if c.find('rest') is None:
                    set_child(c, 'stem', 'down')
                lys = c.findall('lyric')
                num = '1' if c.get('id') in take else '2'
                if lys and ((same_words and num == '2') or line2['num'] != num):
                    close_line2()                   # its words are printed on the other line from here
                for j, ly in enumerate(sorted(lys, key=lambda l: int(re.sub(r'\D', '', l.get('number') or '1') or 1))):
                    if (same_words and num == '2') or j > 0:
                        c.remove(ly)
                    else:
                        ly.set('number', num)
                        ly.attrib.pop('placement', None)
                        ly.attrib.pop('default-y', None)
                        ext = ly.find('extend')
                        line2['open'] = ext is not None and ext.get('type') != 'stop'
                        line2['last'], line2['num'] = None, num
                if not lys and c.find('rest') is None and c.find('chord') is None and line2['open']:
                    line2['last'] = c
            m.append(c)
    return part, sum(merged), len(merged)


ACC = {-2: 'flat-flat', -1: 'flat', 0: 'natural', 1: 'sharp', 2: 'double-sharp'}
ACC_AFTER = ('type', 'dot', 'voice', 'instrument', 'footnote', 'level', 'unpitched', 'pitch', 'rest', 'chord',
             'grace', 'cue', 'duration', 'tie')


def mark_accidentals(root):
    """Verovio prints only the accidentals a MusicXML writes as <accidental>; it does not work them
    out from <alter>, and a file that leaves them to the reader (Sibelius does) shows B-flat for
    B-natural (SKILL.md 8.1). Write the ones the score needs: per staff, both voices together,
    against the key signature and what earlier notes in the bar have already altered; a note tied
    over from the last bar shows none. Returns how many were added."""
    added = 0
    for part in root.findall('part'):
        fifths, div = 0, 1
        for m in part.findall('measure'):
            key = {}
            for e in m:
                if e.tag == 'attributes':
                    if e.find('key/fifths') is not None:
                        fifths = int(e.findtext('key/fifths'))
                    if e.find('divisions') is not None:
                        div = int(e.findtext('divisions'))
            order = 'FCGDAEB' if fifths >= 0 else 'BEADGCF'
            key = {st: (1 if fifths > 0 else -1) for st in order[:abs(fifths)]}
            evs, t, k = [], Fr(0), 0
            for e in m:
                if e.tag == 'backup':
                    t -= Fr(int(e.findtext('duration')), div)
                elif e.tag == 'forward':
                    t += Fr(int(e.findtext('duration')), div)
                elif e.tag == 'note':
                    on = evs[-1][0] if (e.find('chord') is not None and evs) else t
                    evs.append((on, k, e))
                    k += 1
                    if e.find('chord') is None and e.find('grace') is None:
                        t += Fr(int(e.findtext('duration') or 0), div)
            state = {}
            for _, _, n in sorted(evs, key=lambda x: (x[0], x[1])):
                p = n.find('pitch')
                if p is None:
                    continue
                st, octv = p.findtext('step'), p.findtext('octave')
                alt = int(float(p.findtext('alter') or 0))
                held = any(x.get('type') == 'stop' for x in n.findall('tie'))
                have = n.find('accidental')
                now = state.get((st, octv), key.get(st, 0))
                if have is not None:
                    state[(st, octv)] = alt
                    continue
                if held or alt == now or alt not in ACC:
                    if not held:
                        state[(st, octv)] = alt
                    continue
                acc = etree.Element('accidental')
                acc.text = ACC[alt]
                at = 0
                for j, ch in enumerate(n):
                    if ch.tag in ACC_AFTER:
                        at = j + 1
                n.insert(at, acc)
                state[(st, octv)] = alt
                added += 1
    return added


MEI_ACC = {'s': 1, 'f': -1, 'n': 0, 'x': 2, 'ss': 2, 'ff': -2, 'ns': 1, 'nf': -1}


def pitch_readback(tk):
    """Every note as a singer would read it off the page Verovio draws, against the pitch it
    plays: written accidentals, else the key signature and what earlier notes in the bar on that
    staff have altered. Returns [(bar, staff, note name, reads, sounds)] where they differ."""
    M = '{http://www.music-encoding.org/ns/mei}'
    X = '{http://www.w3.org/XML/1998/namespace}id'
    root = etree.fromstring(tk.getMEI().encode())
    q = {}
    for ev in tk.renderToTimemap():
        for i in ev.get('on', []):
            q.setdefault(i, ev['qstamp'])
    key, bad = {}, []
    held = {t.get('endid', '').lstrip('#') for t in root.iter(M + 'tie')}   # tied over: reads as its first note

    def setkey(el, n=None):
        sig = el.get('keysig') or next((k.get('sig') for k in el.iter(M + 'keySig')), None)
        if sig is None:
            return
        d = {}
        if sig not in ('0', 'mixed'):
            k, a = int(sig[:-1]), (1 if sig[-1] == 's' else -1)
            d = {st: a for st in ('fcgdaeb' if a > 0 else 'beadgcf')[:k]}
        if n is None:
            for s_ in list(key) or ['*']:
                key[s_] = d
            key['*'] = d
        else:
            key[n] = d
    for el in root.iter(M + 'scoreDef', M + 'staffDef', M + 'measure'):
        if el.tag == M + 'scoreDef':
            setkey(el)
        elif el.tag == M + 'staffDef':
            setkey(el, el.get('n'))
        else:
            for st in el.findall(M + 'staff'):
                n = st.get('n')
                kd = key.get(n, key.get('*', {}))
                notes = [(q.get(nt.get(X)), k, nt) for k, nt in enumerate(st.iter(M + 'note'))
                         if nt.get(X) not in held and nt.get('tie') not in ('m', 't')]
                state = {}
                for qs, _, nt in sorted((x for x in notes if x[0] is not None), key=lambda x: (x[0], x[1])):
                    pn, oc = nt.get('pname'), nt.get('oct')
                    w = nt.get('accid') or next((a.get('accid') for a in nt.findall(M + 'accid') if a.get('accid')), None)
                    g = nt.get('accid.ges') or next((a.get('accid.ges') for a in nt.findall(M + 'accid') if a.get('accid.ges')), None)
                    sounds = MEI_ACC.get(g, MEI_ACC.get(w, 0)) if (g or w) else 0
                    reads = MEI_ACC[w] if w in MEI_ACC else state.get((pn, oc), kd.get(pn, 0))
                    state[(pn, oc)] = reads
                    if reads != sounds:
                        nm = lambda a: pn.upper() + {-2: 'bb', -1: 'b', 0: '', 1: '#', 2: '##'}[a] + oc
                        bad.append((el.get('n'), n, nm(sounds), nm(reads), nm(sounds)))
    return bad


def mark_tuplets(root):
    """Notes timed as tuplets (<time-modification>) but with no <tuplet> marking print with no
    bracket or number, so a triplet looks like a misprint. Group each voice's run of them into
    tuplets (a group is complete when it fills its normal notes' worth) and mark the ends.
    Returns how many groups were marked."""
    count = 0
    for part in root.findall('part'):
        for m in part.findall('measure'):
            notes = [e for e in m if e.tag == 'note' and e.find('chord') is None and e.find('grace') is None]
            if any(e.find('.//tuplet') is not None for e in notes):
                continue
            by_voice = {}
            for e in notes:
                by_voice.setdefault((e.findtext('voice') or '1', e.findtext('staff') or '1'), []).append(e)
            for vs in by_voice.values():
                group, total, need = [], 0, None
                for e in vs + [None]:
                    tm = e.find('time-modification') if e is not None else None
                    if tm is None:
                        group, total, need = [], 0, None
                        continue
                    act, nor = int(tm.findtext('actual-notes') or 3), int(tm.findtext('normal-notes') or 2)
                    d = int(e.findtext('duration') or 0)
                    if not group:
                        need = Fr(nor) * Fr(d * act, nor)       # the group's length: nor normal notes
                    group.append(e)
                    total += d
                    if total >= need:
                        if total == need and len(group) > 1:
                            for el, kind in ((group[0], 'start'), (group[-1], 'stop')):
                                nots = el.find('notations')
                                if nots is None:
                                    nots = etree.Element('notations')
                                    at = len(el)
                                    for i2, ch in enumerate(el):
                                        if ch.tag in ('lyric', 'play', 'listen'):
                                            at = i2
                                            break
                                    el.insert(at, nots)
                                t = etree.SubElement(nots, 'tuplet', type=kind)
                                if kind == 'start':
                                    t.set('bracket', 'yes')
                            count += 1
                        group, total, need = [], 0, None
    return count


def default_pairs(names, sung):
    order = [i for i in range(len(names)) if i in sung and not names[i].lower().startswith('solo')]
    return [tuple(order[k:k + 2]) for k in range(0, len(order) - 1, 2)]


def display_score(root, parts, notes_by_part, pairs, sung):
    """Return (display root, owners, syl_holder, staff names)."""
    owners, syl_holder = {}, {}
    pl = root.find('part-list')
    sps = {sp.get('id'): sp for sp in pl.findall('score-part')}
    names = [(sps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in parts]
    abbrs = [(sps[p.get('id')].findtext('part-abbreviation') or '').strip() for p in parts]
    pair_of = {}
    for a, b in pairs:
        pair_of[a] = (a, b)
        pair_of[b] = None
    out = etree.Element('score-partwise', version='4.0')
    new_pl = etree.SubElement(out, 'part-list')
    for i, p in enumerate(parts):
        if i in pair_of and pair_of[i] is None:
            continue
        if i in pair_of:
            a, b = pair_of[i]
            pid = f'PX{a}'
            nm = f'{names[a]}\n{names[b]}'
            ab = f'{abbrs[a] or names[a]}\n{abbrs[b] or names[b]}'
            newp, nmerged, nbars = build_pair(copy.deepcopy(parts[a]), copy.deepcopy(parts[b]),
                                              notes_by_part[a], notes_by_part[b], pid, nm, ab, owners, syl_holder)
            # the copies carry the ids given by scan_part, and the notes' 'el' point at the originals;
            # re-link merged chord partners' ids is not needed: ids are attributes, copied verbatim
            print(f'   staff "{names[a]} + {names[b]}": {nmerged} of {nbars} bars as chords, the rest divided')
            sp = etree.SubElement(new_pl, 'score-part', id=pid)
            etree.SubElement(sp, 'part-name').text = nm
            etree.SubElement(sp, 'part-abbreviation').text = ab
            out.append(newp)
        else:
            sp = copy.deepcopy(sps[p.get('id')])
            new_pl.append(sp)
            c = copy.deepcopy(p)
            for pr in c.iter('print'):
                pr.getparent().remove(pr)
            out.append(c)
            if i in sung:
                for n in notes_by_part[i]:
                    owners.setdefault(n['id'], set()).add(i)
                    if n['lyric']:
                        syl_holder[(i, n['id'])] = n['id']
    return out, owners, syl_holder


# ----------------------------------------------------------------------------- audio and timing

def decode(path, sr=22050):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ac', '1', '-ar', str(sr),
                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def audio_onsets(x, sr=22050, n=1024, hop=128):
    """Spectral-flux onsets (seconds)."""
    win = np.hanning(n).astype(np.float32)
    nfr = 1 + max(0, (len(x) - n) // hop)
    prev, flux = None, np.zeros(nfr, np.float32)
    for c0 in range(0, nfr, 4096):
        c1 = min(nfr, c0 + 4096)
        idx = np.arange(c0, c1)[:, None] * hop + np.arange(n)[None, :]
        L = np.log1p(100 * np.abs(np.fft.rfft(x[idx] * win, axis=1))).astype(np.float32)
        if prev is not None:
            L = np.vstack([prev[None], L])
            d = np.maximum(0, np.diff(L, axis=0)).sum(1)
            flux[c0:c1] = d
        else:
            d = np.maximum(0, np.diff(L, axis=0)).sum(1)
            flux[c0 + 1:c1] = d
        prev = L[-1]
    k = int(0.4 * sr / hop)
    pad = np.pad(flux, k, mode='edge')
    from numpy.lib.stride_tricks import sliding_window_view
    med = np.median(sliding_window_view(pad, 2 * k + 1), axis=1)[:nfr]
    thr = med + 0.25 * np.percentile(flux, 95)
    w = 4
    padm = np.pad(flux, w, mode='constant')
    mx = sliding_window_view(padm, 2 * w + 1).max(1)[:nfr]
    peaks = np.flatnonzero((flux >= mx) & (flux > thr))
    t = (peaks * hop + n / 2) / sr
    keep, last = [], -1
    for v in t:
        if v - last > 0.05:
            keep.append(v)
            last = v
    return np.array(keep)


HOP_C = 0.05          # seconds per chroma frame


def chroma_audio(x, sr=22050):
    """Pitch-class profile of the audio every HOP_C s (55 Hz - 2 kHz, log magnitude)."""
    n, h = 4096, int(sr * HOP_C)
    nfr = max(0, (len(x) - n) // h)
    f = np.fft.rfftfreq(n, 1 / sr)
    sel = (f > 55) & (f < 2000)
    pc = ((np.round(12 * np.log2(f[sel] / 440)) + 9) % 12).astype(int)
    M = np.zeros((12, sel.sum()), np.float32)
    M[pc, np.arange(sel.sum())] = 1
    win = np.hanning(n).astype(np.float32)
    A = np.zeros((nfr, 12), np.float32)
    for c0 in range(0, nfr, 1000):
        idx = np.arange(c0, min(nfr, c0 + 1000))[:, None] * h + np.arange(n)[None, :]
        A[c0:c0 + len(idx)] = np.log1p(1000 * np.abs(np.fft.rfft(x[idx] * win, axis=1))[:, sel]) @ M.T
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def chroma_score(notes, to_audio, nfr):
    """The same profile built from the score's notes (with a little of each note's fifth and third,
    as a voice's overtones put there), placed on the audio timeline by `to_audio`."""
    S = np.zeros((nfr, 12), np.float32)
    for a, b, m in notes:
        i0 = int(to_audio(a) / HOP_C)
        i1 = max(i0 + 1, int(to_audio(b) / HOP_C))
        for hh, w in ((0, 1.0), (7, 0.35), (4, 0.15)):
            S[max(i0, 0):min(i1, nfr), (m + hh) % 12] += w
    return S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-9)


def dtw_offset(A, S, band):
    """Dynamic time warping of the score's profile S against the audio's A, within +-band frames of
    the straight line. Returns, per frame of S, how far (s) the audio has it from the straight line."""
    n = min(len(A), len(S))
    W = 2 * band + 1
    D = np.full(W, np.inf)
    P = np.zeros((n, W), np.int8)
    ks = np.arange(W)
    for i in range(n):
        c = 1.0 - A[np.clip(i + ks - band, 0, len(A) - 1)] @ S[i]
        if i == 0:
            row = c.copy()
        else:
            up = np.append(D[1:], np.inf)        # the audio holds while the score moves on
            best = np.minimum(D, up)
            P[i] = np.where(D <= up, 0, 1)
            row = c + best
        for k in range(1, W):                    # the audio moves on while the score holds
            v = row[k - 1] + c[k]
            if v < row[k]:
                row[k] = v
                P[i, k] = 2
        D = row
    k, i, off = int(np.argmin(D)), n - 1, np.zeros(n)
    seen = np.zeros(n, bool)
    while i > 0:
        if not seen[i]:
            off[i], seen[i] = (k - band) * HOP_C, True
        p = P[i, k]
        if p == 0:
            i -= 1
        elif p == 1:
            i, k = i - 1, k + 1
        else:
            k -= 1
    return off


class Timing:
    """Score seconds -> audio seconds.

    Anchored as stem_vs_score.py does it: the offset from where the audio first sounds against the
    score's first note, only the tempo refined on onsets. Then re-anchored after every fermata:
    playback holds a fermata longer than written, by an amount the file does not say (Sibelius
    held the two-soloist TTBB's by 0.25 s and 0.45 s), and everything after it runs that much
    late. The hold is measured by aligning the score's pitch content with the audio's (chroma,
    dynamic time warping), which a steady groove cannot fool, and refined to the millisecond on
    the onsets of the stretch that follows."""

    def __init__(self, mp3, notes, first_score, breaks):
        self.x = decode(mp3)
        self.dur = len(self.x) / 22050
        env = envelope(mp3, -50.0)
        sounding = [r for r in runs(env) if r[1] - r[0] >= 0.3]
        if not sounding:
            sys.exit(f'{mp3}: no sound above -50 dBFS')
        self.first_audio = sounding[0][0]
        self.last_audio = sounding[-1][1]
        self.off = self.first_audio - first_score           # anchored at the first entrance
        self.aon = audio_onsets(self.x)
        so = np.array(sorted(set(round(a, 3) for a, _, _ in notes)))
        self.so = so
        self.fit_tempo(so)
        self.breaks = np.array(sorted(breaks))
        self.cum = np.zeros(len(self.breaks) + 1)
        A = chroma_audio(self.x)
        self.A, self.notes = A, notes
        self.fit_holds(A, notes, so)
        # the first entrance can be too quiet to trip the level threshold (a predominant mix with
        # the entering voice 21 dB down started 0.1 s late): the pitch alignment of the first
        # stretch overrules the anchor when they disagree by a frame or more
        self.moved = 0.0
        if abs(self.base) >= 0.03:
            self.moved, self.off = self.base, self.off + self.base
            self.fit_tempo(so)
            self.fit_holds(A, notes, so)
        # then the tempo and every hold together, by least squares on the onsets each lands near:
        # fitted one after the other, a hold left in the tempo spreads over the whole piece (a
        # 0.6 s hold measured 0.49 s), and the tempo refitted round the holds overshoots
        if len(self.breaks):
            for win in (0.15, 0.1, 0.06):
                H = (so[:, None] >= self.breaks[None, :]).astype(float)
                g = self(so)
                ok, near = self.nearest(g, win)
                if ok.sum() < len(self.breaks) + 8:
                    break
                X = np.column_stack([so, H])[ok]
                sol = np.linalg.lstsq(X, near[ok] - self.off, rcond=None)[0]
                self.scale = float(np.clip(sol[0], 0.9, 1.1))
                self.steps = [float(v) for v in sol[1:]]     # one column per fermata: its hold
                self.cum = np.concatenate([[0.0], np.cumsum(self.steps)])
            # the check in the report is against a pitch alignment on the final straight line
            self.dtw = dtw_offset(A, chroma_score(notes, self.straight, len(A)), band=int(3.0 / HOP_C))

    def fit_tempo(self, so):
        scale = 1.0
        for win in (0.5, 0.3, 0.15):                         # refine the tempo only; the anchor stays put
            g = self.off + scale * so
            ok, near = self.nearest(g, win)
            if ok.sum() >= 8:
                X, Y = so[ok], near[ok] - self.off
                scale = float(np.clip(np.dot(X, Y) / max(np.dot(X, X), 1e-9), 0.9, 1.1))
        self.scale = scale

    def fit_holds(self, A, notes, so):
        """One offset per stretch between fermatas: coarse from the pitch alignment, fine from onsets."""
        S = chroma_score(notes, self.straight, len(A))
        self.dtw = dtw_offset(A, S, band=int(3.0 / HOP_C))
        edges = [-1e9] + list(self.breaks) + [1e9]
        # the alignment's own ends are loose: judge from 5 s in to 5 s before the last written note
        self.lo = 5.0
        self.hi = min(self.dur, float(self.straight(max(b for _, b, _ in notes)))) - 5.0
        lo, hi = self.lo, self.hi
        seg = []
        for a, b in zip(edges[:-1], edges[1:]):
            t0, t1 = max(float(self.straight(a)) + 1.0, lo), min(float(self.straight(b)) - 1.0, hi)
            if t1 - t0 < 2.0:
                seg.append(None)
                continue
            coarse = float(np.median(self.dtw[int(t0 / HOP_C):int(t1 / HOP_C)]))
            inside = so[(so >= a) & (so < b)]
            g = self.straight(inside) + coarse
            g = g[(g > t0) & (g < t1)]
            ok, near = self.nearest(g, 0.1)
            if ok.sum() >= 6:
                seg.append(coarse + float(np.median(near[ok] - g[ok])))
            elif len(inside) and seg and a > -1e8:
                # too few onsets to refine, and held chords leave the pitch alignment free to slide
                # (a ballad's last three bars, one chord: -1.1 s where playback held +0.75 s): after
                # a fermata the sound comes back with the next note, so take the first onset after it
                # (a hold is never negative: an onset before the written end is the held note's own)
                prev = seg[-1] if seg[-1] is not None else 0.0
                g0 = float(self.straight(inside.min()))
                later = self.aon[(self.aon > g0 + prev - 0.03) & (self.aon < g0 + prev + 3.0)]
                seg.append(float(later[0]) - g0 if len(later) else coarse)
            else:
                seg.append(coarse)
        base = seg[0] if seg[0] is not None else 0.0
        self.base = base
        self.steps, prev = [], base
        for v in seg[1:]:
            v = prev if v is None else v
            self.steps.append(v - prev)
            prev = v
        self.cum = np.concatenate([[0.0], np.cumsum(self.steps)])

    def nearest(self, g, win):
        g = np.asarray(g, float)
        if not len(g) or len(self.aon) < 2:
            return np.zeros(len(g), bool), g
        k = np.clip(np.searchsorted(self.aon, g), 1, len(self.aon) - 1)
        near = np.where(np.abs(self.aon[k - 1] - g) < np.abs(self.aon[k] - g), self.aon[k - 1], self.aon[k])
        return np.abs(near - g) < win, near

    def straight(self, s):
        return self.off + self.scale * np.asarray(s, float)

    def __call__(self, s):
        s = np.asarray(s, float)
        return self.straight(s) + self.cum[np.searchsorted(self.breaks, s, side='right')]

    def report(self, bar_at, label, seg=15.0):
        fmt = lambda t: (lambda r: f'{int(r // 60)}:{r % 60:04.1f}')(round(t, 1))
        print(f'\n{label}')
        print(f'   anchor: audio first sounds at {fmt(self.first_audio)}; audio = {self.off:+.3f} s + '
              f'{self.scale:.4f} x score time')
        if self.moved:
            print(f'   (moved {1000 * self.moved:+.0f} ms from where the audio first sounds, to agree with the '
                  f'pitch alignment of the opening)')
        for b, d in zip(self.breaks, self.steps):
            if b >= self.so.max() - 1e-6:
                print(f'   fermata ending at {fmt(float(self.straight(b)))}: the last; nothing after it to re-anchor, '
                      f'and the last notes stay lit until the sound stops at {fmt(self.last_audio)}')
                continue
            print(f'   fermata ending at {fmt(float(self.straight(b)))} (bar {bar_at(float(self(b)))}): playback '
                  f'holds it {1000 * d:+.0f} ms beyond the written length; the lights after it follow')
            if d < -0.1:
                print(f'   <- a hold cannot be negative: the fit is wrong here; check the lights after bar '
                      f'{bar_at(float(self(b)))} by eye')
        # the check: the pitch alignment against the lights, per stretch. Aligned around the lights
        # themselves, not around the straight line: the alignment only looks +-3 s either side, and
        # after a few long holds the lights can be further than that from the straight line (a TTBB
        # with piano: 3.5 s by bar 52), where it locks on to the wrong bar of a repeated figure
        err = dtw_offset(self.A, chroma_score(self.notes, self, len(self.A)), band=int(3.0 / HOP_C))
        t = np.arange(len(err)) * HOP_C
        rows = []
        for a in np.arange(self.lo, self.hi, seg):
            sel = (t >= a) & (t < min(a + seg, self.hi))
            if sel.sum() > 20:
                rows.append((a, float(np.median(err[sel]))))
        g = self(self.so)
        ok, near = self.nearest(g, 0.1)
        r = (near - g)[ok]
        print(f'   check against the pitch alignment, per {seg:.0f} s (to its {1000 * HOP_C:.0f} ms step): ' +
              '  '.join(f'{fmt(a)} {1000 * m:+.0f}' for a, m in rows))
        bad = [(a, m) for a, m in rows if abs(m) >= 0.1]
        for a, m in bad:
            print(f'   <- the lights are {1000 * abs(m):.0f} ms {"ahead of" if m > 0 else "behind"} the audio around '
                  f'{fmt(a)} (bar {bar_at(a)}), with no fermata to explain it')
        if not bad:
            print('   every stretch within 100 ms of the pitch alignment')
        if len(r):
            print(f'   onsets within 100 ms of a light: {len(r)} of {len(g)}; median {1000 * np.median(r):+.0f} ms '
                  f'(positive = the sound comes after the light)')


# ----------------------------------------------------------------------------- rendering

def install_smufl_font():
    """cairosvg ignores @font-face, so Verovio's text glyphs (the note in a metronome mark,
    chord-symbol accidentals) print as boxes unless Leipzig is installed for fontconfig
    (SKILL.md 8.4). Needs fonttools and brotli; without them the boxes stay."""
    import verovio, base64
    # fontconfig reads ~/.fonts; cairo on a Mac finds fonts through the system, in ~/Library/Fonts
    dest = os.path.expanduser('~/Library/Fonts/Leipzig.ttf' if sys.platform == 'darwin' else '~/.fonts/Leipzig.ttf')
    if os.path.exists(dest):
        return
    try:
        from fontTools.ttLib import TTFont
        css = open(os.path.join(os.path.dirname(verovio.__file__), 'data', 'Leipzig.css')).read()
        f = TTFont(io.BytesIO(base64.b64decode(re.search(r'base64,([A-Za-z0-9+/=]+)', css).group(1))))
        f.flavor = None
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        subprocess.run(['fc-cache', '-f'], check=False, capture_output=True)
    except Exception as e:                                   # a box in a tempo mark is not fatal
        print(f'note: could not install the Leipzig font ({e}); metronome marks may show a box')


def render_png(svg_bytes, W, H):
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=svg_bytes, output_width=W, output_height=H, background_color='white')
    return np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))


_LYRIC_FONT = []


def _lyric_width(text, size):
    """The printed width of a syllable, in the SVG's units: measured in the serif font cairo
    draws Verovio's "Times, serif" with, or estimated when that cannot be found."""
    if not _LYRIC_FONT:
        try:
            from PIL import ImageFont
            path = subprocess.run(['fc-match', '-f', '%{file}', 'Times'], capture_output=True,
                                  text=True).stdout.strip()
            _LYRIC_FONT.append(ImageFont.truetype(path, 400) if path else None)
        except Exception:
            _LYRIC_FONT.append(None)
    f = _LYRIC_FONT[0]
    if f is None:
        return sum(size * (0.30 if c in "ijltfr.,'’ " else 0.56) for c in text)
    return f.getlength(text) * size / 400


def nudge_syllables(syls, ns):
    """Verovio spaces a line's syllables apart only within one layer, so where the words on one
    line come from two voices (the upper part's chord, then the lower part's own note) the next
    bar's first syllable can print over the last one. Move each such syllable right until it
    clears its neighbour by a space's width, as an engraver would, and shorten its line to match."""
    rows = {}
    for g in syls:
        if 'spanning' in (g.get('class') or ''):
            continue
        t = g.find(ns + 'text')
        inner = [x for x in g.iter(ns + 'tspan') if x.get('font-size')]
        if t is None or not inner or t.get('x') is None:
            continue
        txt = ''.join(t.itertext()).strip()
        if not txt:
            continue
        size = float(inner[-1].get('font-size').rstrip('px'))
        rows.setdefault(t.get('y'), []).append([float(t.get('x')), txt, size, g, t])
    moved = 0
    for row in rows.values():
        row.sort(key=lambda r: r[0])
        for prev, cur in zip(row, row[1:]):
            need = prev[0] + _lyric_width(prev[1], prev[2]) + 0.15 * prev[2]
            if cur[0] < need:
                dx = need - cur[0]
                cur[0] = need
                cur[4].set('x', f'{need:.0f}')
                for r_ in cur[3].findall(ns + 'rect'):          # its own line or hyphen moves with it
                    x0, w0 = float(r_.get('x')), float(r_.get('width'))
                    r_.set('x', f'{x0 + dx:.0f}')
                    if w0 - dx > 0.5 * cur[2]:            # a line ends where it did; a hyphen keeps its length
                        r_.set('width', f'{w0 - dx:.0f}')
                moved += 1
    return moved


class Page:
    """One rendered page: base images per view, and every lightable element's pixels."""

    def __init__(self, svg, W, H, owners, syl_holder, colours, views, names, label_px, times, bar_end, ctrl):
        self.W, self.H, self.names, self.label_px = W, H, names, label_px
        root = etree.fromstring(svg.encode())
        ns = '{http://www.w3.org/2000/svg}'
        self.root = root
        cls = lambda e: (e.get('class') or '').split()
        # SVG drawing units -> pixels, for noteheads placed straight from the SVG
        inner = root.find(ns + 'svg')
        vb = [float(v) for v in inner.get('viewBox').split()]
        kx, ky = W / vb[2], H / vb[3]
        pm = next(g for g in inner.iter(ns + 'g') if 'page-margin' in cls(g))
        mx, my = (float(v) for v in re.findall(r'-?[\d.]+', pm.get('transform'))[:2])
        notes, syls, rests = [], [], []
        self.ctrl, self.ctrl_g = ctrl, []
        for g in root.iter(ns + 'g'):
            c = cls(g)
            if 'note' in c and g.get('id') in owners:
                notes.append(g)
            elif ('rest' in c or 'mRest' in c) and g.get('id') in owners:
                rests.append(g)
            elif 'syl' in c:
                syls.append(g)
            elif 'tie' in c or 'slur' in c or 'fermata' in c:
                # a tie or slur carried over a system break is drawn again at the next system's
                # start with no id, naming the original in a class "id-<its id>"
                cid = g.get('id') or next((x[3:] for x in c if x.startswith('id-')), None)
                if cid in ctrl:
                    self.ctrl_g.append((cid, g))
        # elements: (kind, key, g); heads get their own entry for the halo
        self.elems = []
        self.heads = {}
        space = 180.0                     # a staff space in drawing units (Verovio's unit 9, x10)
        self.space_px = space * ky
        widths = {'E0A0': 2.0, 'E0A2': 1.69, 'E0A3': 1.18, 'E0A4': 1.18}
        for g in notes:
            head = next((h for h in g if 'notehead' in cls(h)), None)
            self.elems.append(('body', g.get('id'), g))
            if head is not None:
                self.elems.append(('head', g.get('id'), head))
                use = head.find(ns + 'use')
                if use is not None and use.get('transform'):
                    tx, ty = (float(v) for v in re.findall(r'-?[\d.]+', use.get('transform'))[:2])
                    href = use.get('{http://www.w3.org/1999/xlink}href') or ''
                    sc = float((re.findall(r'scale\(([\d.]+)', use.get('transform')) or ['0.72'])[0]) / 0.72
                    w = widths.get(href[1:5], 1.18) * space * sc
                    self.heads[g.get('id')] = ((tx + mx + w / 2) * kx, (ty + my) * ky,
                                               w / 2 * kx, space * sc / 2 * ky)
        for g in rests:
            self.elems.append(('rest', g.get('id'), g))
        for cid, g in self.ctrl_g:                     # a tie lights while either of its notes sounds
            if ctrl[cid][0] == 'tie':
                self.elems.append(('tie', f'{cid}#{len(self.elems)}', g))
        self.nudged = nudge_syllables(syls, ns)
        for s in syls:
            # an extender squeezed to a stub (the next note sits right under the word's end) would
            # read as a full stop after the word; a print has room for the line, this has not
            for r_ in s.findall(ns + 'rect'):
                if float(r_.get('width') or 0) < 0.6 * space:
                    s.remove(r_)
            if 'spanning' in cls(s):
                # an extender carried over a system break: Verovio draws the rest of the line at
                # the start of the next system, outside any note, naming its syllable only in a
                # class "id-<syllable's svg id>". It lights with that syllable, with a halo of its own
                ref = next((c[3:] for c in cls(s) if c.startswith('id-')), None)
                holder = _SYL_SVG.get(ref)
                if holder is not None:
                    self.elems.append(('sylx', f'{holder}#{len(self.elems)}', s))
                continue
            a = s.getparent()
            while a is not None and not ({'note', 'chord'} & set(cls(a))):
                a = a.getparent()
            if a is None:
                continue
            ids = [a.get('id')] if 'note' in cls(a) else [n.get('id') for n in a.iter(ns + 'g') if 'note' in cls(n)]
            holder = next((i for i in ids if i in _SYL_INDEX), None)
            if holder is None:
                continue
            self.elems.append(('syl', holder, s))
            _SYL_SVG[s.get('id')] = holder
        self.ids_on_page = {g.get('id') for g in root.iter(ns + 'g')
                            if {'note', 'rest', 'mRest'} & set(cls(g)) and g.get('id')}
        # score time -> x on each system, from every note and rest printed on it (any staff) and
        # its barlines: a rest's progress bar runs across what the other staves play meanwhile
        first_x = lambda e: next((float(re.findall(r'-?[\d.]+', u.get('transform'))[0])
                                  for u in e.iter(ns + 'use') if u.get('transform')), None)
        self.timemap, self.rest_bar = [], {}
        for si, sysg in enumerate(g for g in root.iter(ns + 'g') if 'system' in cls(g)):
            pts = []
            for m in (g for g in sysg.iter(ns + 'g') if 'measure' in cls(g)):
                mend = None
                for e in m.iter(ns + 'g'):
                    c, i = set(cls(e)), e.get('id')
                    if i not in bar_end or not ({'note', 'rest', 'mRest'} & c):
                        continue
                    mend = bar_end.get(i, mend)
                    if c & {'note', 'rest'} and i in times:
                        x = first_x(e)
                        if x is not None:
                            pts.append((times[i], (x + mx) * kx))
                # the bar's right barline: a bar opening with a repeat sign has its left one too
                bl = next((b for b in reversed(list(m)) if 'barLine' in cls(b)), None)
                d = bl.find(ns + 'path') if bl is not None else None
                if mend is not None and d is not None:
                    pts.append((mend, (float(re.findall(r'-?[\d.]+', d.get('d'))[0]) + mx) * kx))
            first = {}
            for t_, x_ in pts:                   # one x per time: the leftmost (a barline before
                first[round(t_, 4)] = min(x_, first.get(round(t_, 4), x_))   # the next bar's downbeat)
            ts = np.array(sorted(first)) if first else np.zeros(1)
            xs = np.maximum.accumulate(np.array([first[t_] for t_ in sorted(first)])) if first else np.zeros(1)
            self.timemap.append((ts, xs))
            # where each rest's bar goes: under its staff, or above it for the upper of two voices
            for st in (g for g in sysg.iter(ns + 'g') if 'staff' in cls(g)):
                ys = [float(v) for pth in st.findall(ns + 'path') for v in re.findall(r'-?[\d.]+', pth.get('d'))[1::2]]
                if not ys:
                    continue
                top, bot = (min(ys) + my) * ky, (max(ys) + my) * ky
                # a layer that draws nothing (the invisible note keeping a part's staff) is no voice
                layers = [l for l in st if 'layer' in cls(l) and any(e.get('id') in owners for e in l.iter(ns + 'g'))]
                for li, l in enumerate(layers):
                    for e in l.iter(ns + 'g'):
                        if e.get('id') in owners and {'rest', 'mRest'} & set(cls(e)):
                            above = len(layers) > 1 and li == 0
                            self.rest_bar[e.get('id')] = (si, above, top, bot)
        # noteheads drawn on the same spot are one lit note: its ink is whatever is drawn
        # inside the notehead, and it lights in every colour singing it
        spots = {}
        for nid, (cx, cy, rx, ry) in self.heads.items():
            spots.setdefault((round(cx), round(cy)), []).append(nid)
        self.alias = {}
        self.spots = [ids for ids in spots.values() if len(ids) > 1]
        for ids in self.spots:
            for i in ids:
                self.alias[i] = ids[0]
        self.args = (owners, syl_holder, colours, views)
        self.ready = False

    def raster(self):
        """Render the ownership planes and the base images (slow; done only for screens shown)."""
        if self.ready:
            return
        owners, syl_holder, colours, views = self.args
        W, H, root = self.W, self.H, self.root
        # ownership planes
        n = len(self.elems)
        K = max(1, int(math.ceil(math.log2(n + 2))))
        top = root
        def plane(group):
            """group None: every piece black (the ink). Otherwise every piece drawn in a colour that
            spells three bits of its index (red, green, blue = bits 3g, 3g+1, 3g+2): where pieces
            overlap the one on top wins, as on the screen, so no bits mix."""
            top.set('visibility', 'hidden')
            for j, (_, _, g) in enumerate(self.elems):
                g.set('visibility', 'visible')
                if group is None:
                    col = '#000000'
                else:
                    b = ((j + 1) >> (3 * group)) & 7
                    col = '#' + ''.join('00' if b >> c & 1 else 'ff' for c in range(3))
                g.set('fill', col)
                g.set('color', col)
            img = render_png(etree.tostring(root), W, H)
            for _, _, g in self.elems:
                for a in ('visibility', 'fill', 'color'):
                    g.attrib.pop(a, None)
            top.attrib.pop('visibility', None)
            return img
        # coverage per channel: cairosvg antialiases text with colour fringes, so a letter's edge
        # covers red, green and blue by different amounts
        au3 = 1.0 - plane(None).astype(np.float32) / 255.0
        au = au3.max(2)
        self.alpha_mean = au3.mean(2)
        owner = np.zeros(au.shape, np.int32)
        unsure = au <= 0.06
        cov = np.maximum(au3, 1e-6)
        for grp in range((K + 2) // 3):
            # a channel at 255 is a 0 bit; one darkened by the ink's own coverage is a 1 bit;
            # anything in between is an edge where two pieces blend: it belongs to neither
            r = (1.0 - plane(grp).astype(np.float32) / 255.0) / cov
            bits = r > 0.5
            unsure |= (((r > 0.25) & (r < 0.75)) | (au3 < 0.03) & (au[..., None] > 0.06)).any(2)
            for c in range(3):
                owner |= bits[..., c].astype(np.int32) << (3 * grp + c)
        owner[unsure] = 0
        owner[owner > n] = 0
        flat = owner.ravel()
        order = np.argsort(flat, kind='stable')
        sorted_ids = flat[order]
        bounds = np.searchsorted(sorted_ids, np.arange(n + 2))
        self.alpha = self.alpha_mean.ravel()      # how much ink, for blending a lit piece's colour
        self.free_ink = ((flat == 0) & (au.ravel() > 0.06)).reshape(H, W)   # lightable ink no piece claimed
        self.pix = [order[bounds[j + 1]:bounds[j + 2]] for j in range(n)]
        self.shared_ink = {}
        for ids in self.spots:
            cx, cy, rx, ry = self.heads[ids[0]]
            y0, y1 = int(max(0, cy - ry)), int(min(H - 1, cy + ry))
            x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.1
            cand = (yy[inside] * W + xx[inside]).ravel()
            self.shared_ink[ids[0]] = cand[self.alpha[cand] > 0.06]
        # base images per view
        self.base = {}
        for v in views:
            self.base[v] = self.render_base(v, owners, syl_holder, colours)

        for v in views:
            items = [(self.names[i], colours[i]) for i in sorted(colours)] if v == 'all' \
                else [(self.names[v], colours[v])]
            self.base[v] = label_band(self.base[v], items, self.label_px)
        self.lights = Lights(self)
        self.ready = True

    def render_base(self, view, owners, syl_holder, colours):
        ns = '{http://www.w3.org/2000/svg}'
        cls = lambda e: (e.get('class') or '').split()
        touched = []
        def paint(g, col):
            g.set('fill', col)
            g.set('color', col)
            touched.append(g)
        if view != 'all':
            for g in self.root.iter(ns + 'g'):
                c = cls(g)
                if 'layer' in c:
                    paint(g, THEME['grey'])
            for g in self.root.iter(ns + 'g'):
                c = cls(g)
                if 'chord' in c or 'beam' in c:
                    ids = [n.get('id') for n in g.iter(ns + 'g') if 'note' in cls(n)]
                    if any(view in owners.get(i, ()) for i in ids):
                        paint(g, '#000000')
                elif ({'note', 'rest', 'mRest'} & set(c)) and g.get('id'):
                    paint(g, '#000000' if view in owners.get(g.get('id'), ()) else THEME['grey'])
            for cid, g in self.ctrl_g:
                paint(g, '#000000' if view in self.ctrl[cid][3] else THEME['grey'])
            for kind, key, g in self.elems:
                if kind in ('syl', 'sylx'):
                    k0 = key.split('#')[0]
                    paint(g, '#000000' if (view, k0) in syl_readers(syl_holder, k0) else THEME['grey'])
        img = render_png(etree.tostring(self.root), self.W, self.H).copy()
        # the engraving is black, grey and white: drop cairosvg's coloured subpixel text fringes,
        # which a lit syllable's unclaimed edge pixels would otherwise show as blue and orange
        img[:] = img.mean(2, keepdims=True).astype(np.uint8)
        if THEME['dark']:                 # engraved black on white; ink becomes light on dark
            a = 1.0 - img.min(2, keepdims=True).astype(np.float32) / 255.0
            img = (THEME['bg'] + (THEME['ink'] - THEME['bg']) * a).astype(np.uint8)
        for g in touched:
            g.attrib.pop('fill', None)
            g.attrib.pop('color', None)
        return img


_SYL_INDEX = {}
_SYL_SVG = {}          # a syllable's svg id -> the note holding it, for extenders over a system break


def index_syl_holder(syl_holder):
    _SYL_INDEX.clear()
    for (part, nid), holder in syl_holder.items():
        _SYL_INDEX.setdefault(holder, []).append((part, nid))


def syl_readers(syl_holder, holder):
    return {(p, holder) for p, _ in _SYL_INDEX.get(holder, [])}


class Lights:
    """Precomputed pixels and halos for each element, per colour."""

    def __init__(self, page):
        self.page, self.tint = page, THEME['tint']
        self.cache = {}
        W = page.W
        self.groups = {}                      # (kind, key) -> indices of elems
        for j, (kind, key, _) in enumerate(page.elems):
            k2 = self.key(kind, key)
            self.groups.setdefault(k2, []).append(j)
        self.geom = {}
        for gk, js in self.groups.items():
            pix = np.concatenate([page.pix[j] for j in js] + [page.shared_ink.get(gk[1], np.zeros(0, int))
                                                             if gk[0] == 'note' else np.zeros(0, int)])
            pix = np.unique(pix)
            if not len(pix):
                continue
            # the edge pixels no piece could be sure of (antialiasing, overlaps) inside this piece's
            # outline are its own: a lit word or note has no grey rim
            ys, xs = pix // W, pix % W
            y0, y1, x0, x1 = max(ys.min() - 1, 0), ys.max() + 2, max(xs.min() - 1, 0), xs.max() + 2
            fy, fx = np.nonzero(page.free_ink[y0:y1, x0:x1])
            if len(fy):
                pix = np.unique(np.concatenate([pix, (fy + y0) * W + fx + x0]))
            if gk[0] == 'note' and gk[1] in page.heads:
                cx, cy, rx, ry = page.heads[gk[1]]
                pad = max(5.0, 1.4 * ry)
                ry, rx = ry + pad, rx + pad
                y0, y1 = int(max(0, cy - ry)), int(min(page.H - 1, cy + ry))
                x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1
                halo = (yy[inside] * W + xx[inside]).ravel()
            elif gk[0] == 'note':
                continue                  # a note whose head was not found in the SVG
            elif gk[0] == 'rest':
                ys, xs = pix // W, pix % W
                (ya, yb), (xa, xb) = np.percentile(ys, [1, 99]), np.percentile(xs, [1, 99])
                cy, cx = (ya + yb) / 2, (xa + xb) / 2
                ry, rx = (yb - ya) / 2 + 1, (xb - xa) / 2 + 1
                # a whole-bar rest is a small glyph: size its halo by the staff, not the glyph
                sp = page.space_px
                ry, rx = max(ry + 0.6 * sp, 1.5 * sp), max(rx + 0.6 * sp, 1.8 * sp)
                y0, y1 = int(max(0, cy - ry)), int(min(page.H - 1, cy + ry))
                x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1
                halo = (yy[inside] * W + xx[inside]).ravel()
            else:
                ys, xs = pix // W, pix % W
                (ya, yb), (xa, xb) = np.percentile(ys, [1, 99]).astype(int), np.percentile(xs, [1, 99]).astype(int)
                h = yb - ya + 1
                pad = max(3, int(0.25 * h))
                if gk[0] == 'sylx':        # a bare extender line: a halo as tall as a word's
                    pad = max(pad, int(0.6 * page.space_px))
                y0, y1 = max(0, ya - pad), min(page.H - 1, yb + pad)
                x0, x1 = max(0, xa - pad), min(W - 1, xb + pad)
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                halo = (yy * W + xx).ravel()
            in_halo = np.isin(pix, halo)
            hy, hx = halo // W, halo % W
            self.geom[gk] = (pix, self.page.alpha[pix][:, None], in_halo[:, None], halo,
                             (int(hx.min()), int(hx.max()), int(hy.max())), (int(hy.min()), int(hy.max())))

    def key(self, kind, nid):
        if kind in ('body', 'head', 'note'):
            return ('note', self.page.alias.get(nid, nid))
        return (kind, nid)

    def band(self, gk, ys, n):
        """Which of n stacked bands each row is in, over the height of the halo."""
        y0, y1 = self.geom[gk][5]
        return np.clip(((ys - y0) * n) // max(y1 - y0 + 1, 1), 0, n - 1)

    def tints(self, gk, cols):
        """Halo pixel values; a note or word two parts share gets a halo split in their colours."""
        key = ('halo', gk, cols)
        v = self.cache.get(key)
        if v is None:
            halo = self.geom[gk][3]
            ts = np.array([THEME['bg'] * (1 - self.tint) + hexrgb(c) * self.tint for c in cols]).astype(np.uint8)
            if len(cols) == 1:
                v = np.broadcast_to(ts[0], (len(halo), 3))
            else:
                # stacked, not side by side: side by side would read as one part singing the
                # first half of the note and the other the second. Top to bottom in part order,
                # which on a shared staff is high to low
                v = ts[self.band(gk, halo // self.page.W, len(cols))]
            self.cache[key] = v
        return v

    def apply(self, frame_flat, lit):
        """lit: list of (group key, tuple of colour hexes in part order, fraction of a rest gone)."""
        W = self.page.W
        for gk, cols, prog in lit:
            if prog is None:
                continue
            # a lit rest gets a bar that fills while the rest lasts, running from where the rest
            # starts to where it ends as the other staves lay out that time: the fill reaches each
            # note they print as it sounds, so nobody has to count
            _, above, top, bot = self.page.rest_bar[gk[1]]
            x0, x1, xe = prog
            sp = self.page.space_px
            th = max(4, int(round(0.4 * sp)))
            y0 = int(round(top - 0.45 * sp - th)) if above else int(round(bot + 0.45 * sp))
            y0 = min(max(0, y0), self.page.H - th)
            f = frame_flat.reshape(self.page.H, W, 3)
            for k, col in enumerate(cols):       # a rest two parts share: one stripe each
                c = hexrgb(col)
                ya, yb = y0 + k * th // len(cols), y0 + (k + 1) * th // len(cols)
                f[ya:yb, x0:x1 + 1] = (THEME['bg'] * 0.65 + c * 0.35).astype(np.uint8)
                if xe > x0:
                    f[ya:yb, x0:xe] = c.astype(np.uint8)
        lit = [(gk, cols) for gk, cols, _ in lit]
        for gk, cols in lit:
            if gk in self.geom:
                h = self.geom[gk][3]
                frame_flat[h] = (np.maximum if THEME['dark'] else np.minimum)(frame_flat[h], self.tints(gk, cols))
        for gk, cols in lit:
            g = self.geom.get(gk)
            if g is None:
                continue
            key = (gk, cols)
            v = self.cache.get(key)
            if v is None:
                cs = np.array([hexrgb(col) for col in cols])
                cs = cs + (255 - cs) * THEME['lift']      # lit ink a shade lighter than its halo
                c = cs[self.band(gk, g[0] // W, len(cols))]   # ink banded like its halo
                t = self.tints(gk, cols).astype(np.float32)
                bg = np.tile(THEME['bg'], (len(g[0]), 1))
                inside = g[2][:, 0]
                if inside.any():
                    pos = np.searchsorted(g[3], g[0][inside]) if np.all(np.diff(g[3]) > 0) else None
                    bg[inside] = t[pos] if pos is not None else t[0]
                v = (bg * (1 - g[1]) + c * g[1]).astype(np.uint8)
                self.cache[key] = v
            frame_flat[g[0]] = v


def label_band(img, items, px):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype('DejaVuSans-Bold.ttf', px)
    except OSError:
        try:
            font = ImageFont.load_default(size=px)
        except TypeError:
            font = ImageFont.load_default()
    x = int(px * 0.8)
    for text, col in items:
        d.text((x, int(px * 0.4)), text, fill=col, font=font)
        x += int(d.textlength(text, font=font)) + int(px * 1.2)
    return np.asarray(im).copy()


def vfr_flag(passthrough=False):
    """ffmpeg 5 renamed -vsync to -fps_mode."""
    v = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout
    m = re.search(r'version n?(\d+)', v)
    new = not m or int(m.group(1)) >= 5
    mode = 'passthrough' if passthrough else 'vfr'
    return ['-fps_mode', mode] if new else ['-vsync', mode]


def check_frames(mp4, planned_ms):
    """Each frame of the finished file against the moment it was meant to appear."""
    pts = [float(v) for v in subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'frame=pts_time', '-of', 'csv=p=0',
         mp4], capture_output=True, text=True).stdout.replace(',', '').split()]
    if len(pts) != len(planned_ms):
        print(f'   frames: {len(pts)} in the file, {len(planned_ms)} planned')
        return
    err = np.abs(np.array(pts) * 1000 - np.array(planned_ms))
    print(f'   frames: all {len(pts)} where planned, to within {err.max():.0f} ms')


# ----------------------------------------------------------------------------- main

def featured_of(mp3, names, part_map):
    b = os.path.basename(mp3)
    m = re.search(r' - \((.+?)\) ', b) or re.search(r' - (Solo[^-]*?) (?:predominant|part-left)', b)
    if not m:
        return None
    sec = m.group(1).strip()
    sec = part_map.get(sec, sec)
    for i, n in enumerate(names):
        if n.lower() == sec.lower():
            return i
    # "Solo 1" in the mp3 name for a part called "Solo 1 (tenor)"
    near = [i for i, n in enumerate(names)
            if n.lower().startswith(sec.lower()) and not n[len(sec):len(sec) + 1].isalnum()]
    if len(near) == 1:
        return near[0]
    sys.exit(f'{b}: no part named {sec!r} in the score (parts: {names}); map it with --part "{sec}=<part name>"')


def use_display(path, root, parts, names, notes_by_part, tempos):
    """Show `path` instead of the file the audio was rendered from, after checking that it
    has the same parts, bars, notes and tempo marks (words, slurs and ties may differ: the
    Cantai learning file re-sings tied notes that the print file ties)."""
    droot = read_xml(path)
    dparts = droot.findall('part')
    dsps = {sp.get('id'): sp for sp in droot.find('part-list').findall('score-part')}
    dnames = [(dsps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in dparts]
    if len(dparts) != len(parts):
        sys.exit(f'--display: {len(dparts)} parts against {len(parts)} in the file the audio came from')
    tmp = tempfile.NamedTemporaryFile(suffix='.musicxml', delete=False)
    tmp.write(etree.tostring(droot))
    tmp.close()
    _p, _b, dtempos = load_score(tmp.name)
    os.unlink(tmp.name)
    if [(round(b, 3), q) for b, q in dtempos] != [(round(b, 3), q) for b, q in tempos]:
        sys.exit(f'--display: tempo marks differ ({dtempos} against {tempos}); the lights would not follow the audio')
    dnotes, dstarts = [], None
    for i, p in enumerate(dparts):
        ns_, st = scan_part(i, p)
        dnotes.append(ns_)
        dstarts = dstarts or st
    sig = lambda ns_: {} if not ns_ else {mi: sorted((n['rel'], n['dur'], n['midi']) for n in ns_
                                                     if n['mi'] == mi and not n['rest'] and not n['grace'])
                                          for mi in range(max(n['mi'] for n in ns_) + 1)}
    bad = 0
    for i in range(len(parts)):
        if dnames[i] != names[i]:
            print(f'   --display: part {i + 1} is "{dnames[i]}" there and "{names[i]}" here')
        a, b = sig(notes_by_part[i]), sig(dnotes[i])
        diff = [mi + 1 for mi in sorted(set(a) | set(b)) if a.get(mi) != b.get(mi)]
        if diff:
            bad += 1
            print(f'   --display: {names[i]} has different notes in bars {diff[:12]}{" ..." if len(diff) > 12 else ""}')
    print(f'display: {os.path.basename(path)}; ' +
          ('same bars, notes and tempo marks as the file the audio came from' if not bad
           else 'the lights in the bars above follow the display file, not the audio'))
    sung = {i for i, ns_ in enumerate(dnotes) if any(n['lyric'] for n in ns_)}
    return droot, dparts, dnames, dnotes, dstarts, sung



# ----------------------------------------------------------------------------- repeats

def play_order(part):
    """The bars in the order they are played: repeat signs (with times="n") and first/second
    endings unrolled. D.C., D.S. and codas are not followed (a warning says so)."""
    ms = part.findall('measure')
    n = len(ms)
    fwd, bwd, times, end_nums, end_stop = [False] * n, [False] * n, [2] * n, [None] * n, [False] * n
    for i, m in enumerate(ms):
        for bl in m.findall('barline'):
            rp, en = bl.find('repeat'), bl.find('ending')
            if rp is not None and rp.get('direction') == 'forward':
                fwd[i] = True
            if rp is not None and rp.get('direction') == 'backward':
                bwd[i] = True
                times[i] = int(rp.get('times') or 2)
            if en is not None:
                if en.get('type') == 'start':
                    end_nums[i] = [int(x) for x in re.findall(r'\d+', en.get('number') or '1')]
                if en.get('type') in ('stop', 'discontinue'):
                    end_stop[i] = True
    if any(s_.get('dacapo') or s_.get('dalsegno') or s_.get('tocoda') for s_ in part.iter('sound')):
        print('warning: D.C., D.S. or a coda in the score is not followed; only repeat signs are')
    order, i, start, passno, done = [], 0, 0, 1, {}
    while i < n and len(order) < 20 * n:
        if fwd[i] and start != i:
            start, passno = i, 1
        if end_nums[i] is not None and passno not in end_nums[i]:
            j = i
            while j < n - 1 and not end_stop[j]:
                j += 1
            i = j + 1
            continue
        order.append(i)
        if bwd[i]:
            k = done.get(i, 1)
            if k < times[i]:
                done[i] = k + 1
                passno = k + 1
                i = start
                continue
        i += 1
    return order


# ----------------------------------------------------------------------------- a closed score to show

def repair_forwards(droot, src_notes, sung):
    """A second voice written after a <backup> to the start of the bar but missing the <forward>
    over the beats where it has no notes of its own starts too early: its notes land where
    another part's are, and the lights would come a beat early. Where the open score has every
    note of that voice exactly one gap later (the gap being what the voice is short of a full
    bar), put the <forward> in. Returns the bars mended, by staff."""
    at = {(n['mi'], n['rel'], n['midi']) for i, ns_ in enumerate(src_notes) if i in sung
          for n in ns_ if not n['rest'] and not n['grace']}
    mended = []
    for j, part in enumerate(droot.findall('part')):
        div = 1
        for mi, m in enumerate(part.findall('measure')):
            kids = list(m)
            for e in kids:
                if e.tag == 'attributes' and e.find('divisions') is not None:
                    div = int(e.findtext('divisions'))
            full = sum(int(e.findtext('duration') or 0) for e in kids
                       if e.tag == 'note' and e.findtext('voice', '1') == '1' and e.find('chord') is None
                       and e.find('grace') is None)
            for e in kids:
                if e.tag != 'backup' or int(e.findtext('duration') or 0) != full:
                    continue
                voice, t, notes = None, 0, []
                for f in kids[kids.index(e) + 1:]:
                    if f.tag in ('backup', 'forward'):
                        break
                    if f.tag != 'note' or f.find('grace') is not None:
                        continue
                    voice = voice or f.findtext('voice')
                    if f.findtext('voice') != voice:
                        break
                    if f.find('chord') is None:
                        notes.append((t, f))
                        t += int(f.findtext('duration') or 0)
                    else:
                        notes.append((notes[-1][0] if notes else 0, f))
                gap = full - t
                pitched = [(tt, f) for tt, f in notes if f.find('rest') is None]
                if gap <= 0 or not pitched:
                    continue
                if all((mi, Fr(tt + gap, div), midi(f)) in at for tt, f in pitched) and \
                        not all((mi, Fr(tt, div), midi(f)) in at for tt, f in pitched):
                    fw = etree.Element('forward')
                    etree.SubElement(fw, 'duration').text = str(gap)
                    m.insert(list(m).index(e) + 1, fw)
                    mended.append((j, m.get('number'), Fr(gap, div)))
    return mended


def closed_display(droot, src_names, src_notes, sung):
    """Use a closed score (two parts to a staff, as printed) as the display. Whose each notehead,
    rest and syllable is comes from the open score the audio was rendered from: a notehead is
    the parts that sing that pitch at that moment, a rest the parts resting there, a syllable
    the parts starting a syllable there (a second lyric line going to the lower part). What
    the open score cannot settle falls back to the voices: voice 1 and the top of a chord to
    the upper part, voice 2 and the bottom to the lower."""
    for j, num, g in repair_forwards(droot, src_notes, sung):
        print(f'   display bar {num}, staff {j + 1}: its second voice had no <forward> over its first '
              f'{g} beat(s) and began too early; mended to match the open score (fix the file too)')
    dparts = droot.findall('part')
    dsps = {sp.get('id'): sp for sp in droot.find('part-list').findall('score-part')}
    dnames = [(dsps[p.get('id')].findtext('part-name') or p.get('id')) for p in dparts]
    scans = [scan_part(j, p, prefix='d') for j, p in enumerate(dparts)]
    dnotes, dstarts = [sc[0] for sc in scans], scans[0][1]
    staff_parts = {}
    for j, nm in enumerate(dnames):
        flat = ' '.join(nm.lower().split())
        hit = [i for i, sn in enumerate(src_names) if ' '.join(sn.lower().split()) in flat]
        # a name found inside a longer one ("Tenor 1" in "Tenor 1 Tenor 2") is not also its own
        hit = [i for i in hit if not any(i != k and src_names[i].lower() in src_names[k].lower()
                                         and k in hit for k in hit)] or hit
        staff_parts[j] = sorted(hit)
    at, rests, syls = set(), set(), set()
    syl_text = {}
    count = {}
    for i, ns_ in enumerate(src_notes):
        for n in ns_:
            if n['grace']:
                continue
            if n['rest']:
                rests.add((i, n['mi'], n['rel'], n['dur']))
            else:
                at.add((i, n['mi'], n['rel'], n['midi']))
                count[i] = count.get(i, 0) + 1
                if n['lyric']:
                    syls.add((i, n['mi'], n['rel']))
                    syl_text[(i, n['mi'], n['rel'])] = _letters(n['lyric'][1])
    # staves with no part names (or names that match nothing): each sung part goes to the staff
    # holding most of its notes, if that is most of them
    if not any(set(staff_parts[j]) & sung for j in staff_parts):
        staff_parts = {j: [] for j in range(len(dparts))}
        for i in sorted(sung):
            hits = [sum(1 for n in ns_ if not n['rest'] and not n['grace'] and (i, n['mi'], n['rel'], n['midi']) in at)
                    for ns_ in dnotes]
            j = int(np.argmax(hits))
            if hits[j] >= 0.5 * count.get(i, 1):
                staff_parts[j].append(i)
        for j, sp in staff_parts.items():             # label a nameless staff with its parts
            spp = dsps.get(dparts[j].get('id'))
            if sp and spp is not None and not (spp.findtext('part-name') or '').strip():
                for tag, val in (('part-name', '\n'.join(src_names[i] for i in sp)),
                                 ('part-abbreviation', '\n'.join(src_names[i] for i in sp))):
                    el = spp.find(tag)
                    if el is None:
                        el = etree.SubElement(spp, tag)
                    el.text = val
                dnames[j] = ' '.join(src_names[i] for i in sp)
    owners, fall = {}, 0
    for j, ns_ in enumerate(dnotes):
        sp = [i for i in staff_parts[j] if i in sung]
        if not sp:
            continue
        voices = {}
        for n in ns_:
            voices.setdefault(n['mi'], set()).add(n['voice'])
        for n in ns_:
            if n['grace']:
                continue
            if n['rest']:
                c = {i for i in sp if (i, n['mi'], n['rel'], n['dur']) in rests}
            else:
                c = {i for i in sp if (i, n['mi'], n['rel'], n['midi']) in at}
            if not c:
                fall += 1
                vs = sorted(voices[n['mi']], key=lambda v: int(v) if v.isdigit() else 0)
                if n['rest'] and len(vs) == 1:
                    c = set(sp)
                else:
                    c = {sp[0] if vs.index(n['voice']) == 0 else sp[-1]}
            owners[n['id']] = c
    # syllables: grouped by staff and moment; with two lines at one moment, line k is the
    # k-th part (top down) that starts a syllable there in the open score
    groups = {}
    el_of = {n['id']: n['el'] for ns_ in dnotes for n in ns_}

    def placed_above(h):
        return any(ly.get('placement') == 'above' and ly.get('print-object') != 'no'
                   and str(h[0]) == (re.sub(r'\D', '', ly.get('number') or '1') or '1')
                   for ly in el_of[h[1]].findall('lyric'))

    def text_of_el(nid):
        return next((''.join(x.text or '' for x in ly.findall('text')) for ly in el_of[nid].findall('lyric')
                     if ly.get('print-object') != 'no'), '')
    for j, ns_ in enumerate(dnotes):
        for n in ns_:
            for ly in n['el'].findall('lyric'):
                if ly.get('print-object') == 'no':
                    continue                  # sung here, printed for another part (read below)
                if ''.join(x.text or '' for x in ly.findall('text')).strip():
                    num = int(re.sub(r'\D', '', ly.get('number') or '1') or 1)
                    groups.setdefault((j, n['mi'], n['rel']), []).append((num, n['id']))
    readers = {}
    for (j, mi, rel), lst in groups.items():
        sp = [i for i in staff_parts[j] if i in sung]
        cand = [i for i in sp if (i, mi, rel) in syls]
        lst.sort()
        if len(lst) == 1 and len(cand) > 1:
            # two parts start a syllable here but one word is printed: it is the parts whose word
            # it is (a Cantai file restarts a held vowel as a new syllable under another part's new word)
            pt = _letters(text_of_el(lst[0][1]))
            same = [i for i in cand if syl_text[(i, mi, rel)] and pt
                    and (pt.startswith(syl_text[(i, mi, rel)]) or syl_text[(i, mi, rel)].startswith(pt))]
            cand = same or cand
        if len(lst) == 1:
            readers.setdefault(lst[0][1], set()).update(cand or owners.get(lst[0][1], set()))
        else:
            # lines top down: those above the staff first. A part reads the line on its own note
            # (the upper part's words above, the lower's below, as printed); where that does not
            # tell them apart, line k is the k-th part down
            lst.sort(key=lambda h: (0 if placed_above(h) else 1, h[0]))
            holders = list(dict.fromkeys(hid for _, hid in lst))
            if len(holders) == 1:                 # one note's word printed on two lines
                readers.setdefault(holders[0], set()).update(cand or owners.get(holders[0], set()))
            else:
                for k, i in enumerate(cand):
                    mine = [hid for hid in holders if i in owners.get(hid, set())]
                    readers.setdefault(mine[0] if len(mine) == 1 else holders[min(k, len(holders) - 1)],
                                       set()).add(i)
                for hid in holders:
                    if not readers.get(hid):
                        readers.setdefault(hid, set()).update(owners.get(hid, set()))
    # words printed once for parts on two staves, as a closed score prints them between the staves
    # where both sing them: a part whose own staff prints no syllable at a moment it starts one reads
    # the one printed on another staff there with the same text (a hidden, print-object="no" copy on
    # its own staff says so, and gives the text)
    hidden = {}
    for j, ns_ in enumerate(dnotes):
        for n in ns_:
            for ly in n['el'].findall('lyric'):
                if ly.get('print-object') == 'no':
                    hidden[(j, n['mi'], n['rel'])] = ''.join(x.text or '' for x in ly.findall('text')).strip()
    text_of = {}
    for j, ns_ in enumerate(dnotes):
        for n in ns_:
            for ly in n['el'].findall('lyric'):
                if ly.get('print-object') != 'no':
                    text_of.setdefault(n['id'], ''.join(x.text or '' for x in ly.findall('text')).strip())
    for (j, mi, rel), txt in hidden.items():
        if (j, mi, rel) in groups:
            continue
        sp = [i for i in staff_parts[j] if i in sung and (i, mi, rel) in syls]
        for (j2, mi2, rel2), lst in groups.items():
            if j2 != j and mi2 == mi and rel2 == rel:
                hit = [(num, hid) for num, hid in lst if text_of.get(hid) == txt]
                if hit:
                    # the same word on two lines of that staff: the one on the side facing this staff
                    def facing(h, j2=j2):
                        ab = any(ly.get('placement') == 'above' and ly.get('print-object') != 'no'
                                 and str(h[0]) == re.sub(r'\D', '', ly.get('number') or '1')
                                 for ly in el_of[h[1]].findall('lyric'))
                        return ab == (j < j2)
                    pick = [h for h in hit if facing(h)] or hit
                    readers.setdefault(pick[-1][1], set()).update(sp)
                    break
    return dparts, dnames, dnotes, staff_parts, owners, readers, fall, dstarts


def part_windows(dnotes, owners, readers, part):
    """One part's notes, rests and syllables in a closed display, in written quarters: a
    syllable lit from its note through the part's following notes until its next syllable or
    rest."""
    evs = {}
    for ns_ in dnotes:
        for n in ns_:
            if not n['grace'] and n['dur'] > 0 and part in owners.get(n['id'], ()):
                evs.setdefault(n['on'], []).append(n)
    syl_at = {}
    for ns_ in dnotes:
        for n in ns_:
            if part in readers.get(n['id'], ()):
                syl_at[n['on']] = n['id']
    out, cur = {}, None
    for on in sorted(evs):
        ns_ = evs[on]
        end = max(n['on'] + n['dur'] for n in ns_)
        if all(n['rest'] for n in ns_):
            cur = None
        elif on in syl_at:
            cur = syl_at[on]
            out[cur] = [ns_[0]['mi'], on, end]
        elif cur:
            out[cur][2] = max(out[cur][2], end)
    return out


def timing_source(mp3):
    """The mp3 to time this one by. A set made by rehearsal_mix.py is sample-aligned, and its
    Balanced track, every voice at the same level, times best: in a predominant mix a voice 21 dB
    down can enter too quietly to trip the level threshold (one set's Baritone and Tenor mixes
    anchored 0.04-0.1 s late), and its onsets are mostly the featured voice's consonants. Used
    only when the Balanced track sits beside this one, is the same length and lines up with it."""
    m = re.match(r'(.*?) - (\(.+\)|Solo.*) (predominant|part-left)\.mp3$', os.path.basename(mp3))
    if not m:
        return mp3, ''
    ref = os.path.join(os.path.dirname(mp3), m.group(1) + ' - Balanced.mp3')
    if not os.path.exists(ref):
        return mp3, ''
    x, y = decode(ref), decode(mp3)
    if abs(len(x) - len(y)) > 0.03 * 22050:
        return mp3, ''
    h = 220                                              # 10 ms envelopes, compared over +-0.3 s
    n = min(len(x), len(y)) // h
    ex = np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1))
    ey = np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(1))
    ex, ey = ex - ex.mean(), ey - ey.mean()
    lags = range(-30, 31)
    cc = [float(np.dot(ex[max(0, k):n + min(0, k)], ey[max(0, -k):n - max(0, k)])) for k in lags]
    k = lags[int(np.argmax(cc))]
    if k != 0:
        return mp3, ''
    return ref, f'timed by {os.path.basename(ref)}, which it lines up with (same length, 0 ms apart)'


class Tee:
    """Everything the run prints also goes to the checks file beside the videos, so what every
    check found, including nothing, is on record song by song (SKILL.md Step 10)."""
    def __init__(self, path, out):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.f, self.out = open(path, 'w'), out

    def write(self, s):
        self.out.write(s)
        self.f.write(s)

    def flush(self):
        self.out.flush()
        self.f.flush()


def checks_file(a):
    """<title> - video checks.txt in the output folder, the title being what the mp3 names share."""
    import datetime, hashlib
    names = [os.path.basename(m) for m in a.mp3s]
    title = os.path.commonprefix(names).split(' - ')[0].strip() or os.path.splitext(os.path.basename(a.score))[0]
    out_dir = a.out or os.path.dirname(os.path.abspath(a.mp3s[0]))
    path = os.path.join(out_dir, f'{title} - video checks.txt')
    sys.stdout = Tee(path, sys.stdout)
    ver = hashlib.md5(open(os.path.abspath(__file__), 'rb').read()).hexdigest()[:8]
    print(f'Video checks for {title}, {datetime.datetime.now():%Y-%m-%d %H:%M}, score_video.py {ver}')
    print(f'score: {os.path.basename(a.score)}' + (f'; shown: {os.path.basename(a.display)}' if a.display else ''))
    print('mp3s: ' + '; '.join(names) + '\n')
    return path


def proof_note(a):
    print('\ncheck, proof against the print PDF: ' + (
        'screens written; Claude compares each with the PDF and records what differs, or that nothing '
        'does, below (SKILL.md Step 10)' if a.proof else 'NOT RUN (no --proof)'))


def run_parallel(a):
    """One process per mp3, as many at a time as there are cores: each renders its own
    screens and encodes its own video. Each process's report is printed whole, in the order given."""
    import time
    rest = [x for x in sys.argv[1:] if x not in a.mp3s]
    n = a.jobs or os.cpu_count() or 2
    todo = list(enumerate(a.mp3s))
    running, done, nxt, failed, t0 = {}, {}, 0, 0, time.time()
    while todo or running:
        while todo and len(running) < n:
            k, mp3 = todo.pop(0)
            cmd = [sys.executable, os.path.abspath(__file__), *rest, mp3, '--jobs', '1', '--child']
            log = tempfile.TemporaryFile('w+')      # a pipe could fill and stall the process
            running[k] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, text=True), log)
        for k, (pr, log) in list(running.items()):
            if pr.poll() is not None:
                log.seek(0)
                out = log.read()
                log.close()
                done[k] = (pr.returncode, '\n'.join(l for l in out.splitlines() if not l.startswith('[Warning]')))
                del running[k]
        while nxt in done:
            code, text = done.pop(nxt)
            print(text if nxt == 0 else text.split('\n\n', 1)[-1], flush=True)   # parts and staves once
            if code:
                print(f'   ^ failed: {a.mp3s[nxt]}', flush=True)
                failed += 1
            nxt += 1
        time.sleep(0.5)
    print(f'{len(a.mp3s) - failed} of {len(a.mp3s)} videos in {time.time() - t0:.0f} s')
    proof_note(a)
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('mp3s', nargs='+')
    ap.add_argument('-o', '--out', help='folder for the mp4s (default: beside each mp3)')
    ap.add_argument('--part', action='append', default=[], help='"Section in the mp3 name=part name in the score"')
    ap.add_argument('--staves', help='pairs sharing a staff, e.g. "Tenor 1+Tenor 2,Baritone+Bass"')
    ap.add_argument('--open', action='store_true', help='one part per staff (open score)')
    ap.add_argument('--clip', help='START,SECONDS: render only this stretch (for a test)')
    ap.add_argument('--stills', help='comma-separated times (s): write PNG frames instead of a video')
    ap.add_argument('--size', default='1920x1080')
    ap.add_argument('--staff-px', type=float, default=44.0, help='staff height in pixels')
    ap.add_argument('--jobs', type=int, default=0,
                    help='mp3s rendered at once, each in its own process (default: one per CPU core)')
    ap.add_argument('--lead', type=float, default=1.0, help='turn the page up to this many s early')
    ap.add_argument('--anchor', action='append', default=[],
                    help='BAR=M:SS.ss: the audio time of that bar\'s downbeat, measured by hand (from a stem\'s '
                         'first onset after a fermata, say); overrules the fitted hold of the stretch it falls in')
    ap.add_argument('--crf', type=int, default=20)
    ap.add_argument('--no-condense', action='store_true', help='keep empty staves on every system')
    ap.add_argument('--display', help='a print-faithful MusicXML with the same bars, notes and tempo marks '
                    '(normal slurs, ties and words) to show instead of the file the audio came from')
    ap.add_argument('--pulse', type=int, help='rest bars jump in these notes (8 = eighths, 16 = sixteenths); '
                    'default: per part, the coarsest value 95%% of its sung bars keep to')
    ap.add_argument('--dark', action='store_true', help='light notation on a dark screen instead of black on white')
    ap.add_argument('--proof', help='folder for one unlit PNG per screen of the all-parts view, to compare '
                    'with the print PDF (SKILL.md Step 10)')
    ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    a = ap.parse_args()
    if not (a.child or a.stills or a.clip):
        checks_file(a)
    if len(a.mp3s) > 1 and a.jobs != 1 and not a.stills:
        sys.exit(run_parallel(a))
    set_theme(a.dark)
    palette = PALETTE_DARK if a.dark else PALETTE
    W, H = (int(v) for v in a.size.lower().split('x'))
    part_map = dict(p.split('=', 1) for p in a.part)

    root = read_xml(a.score)
    parts = root.findall('part')
    sps = {sp.get('id'): sp for sp in root.find('part-list').findall('score-part')}
    names = [(sps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in parts]
    notes_by_part, starts = [], None
    for i, p in enumerate(parts):
        ns_, st = scan_part(i, p)
        notes_by_part.append(ns_)
        starts = starts or st
    sung = {i for i, ns_ in enumerate(notes_by_part) if any(n['lyric'] for n in ns_)}
    if not sung:
        sys.exit('no part has lyrics; nothing to follow')

    # tempo map, as stem_vs_score.py reads it
    tmp = tempfile.NamedTemporaryFile(suffix='.musicxml', delete=False)
    tmp.write(etree.tostring(root))
    tmp.close()
    _phr, bars, tempos = load_score(tmp.name)
    os.unlink(tmp.name)
    src_parts, src_notes, src_starts = parts, notes_by_part, starts
    k = mark_tuplets(root)
    if k:
        print(f'{k} tuplet group(s) had no bracket or number in the file; marked for the video')

    droot = read_xml(a.display) if a.display else None
    closed = droot is not None and len(droot.findall('part')) != len(parts)
    if droot is not None:
        k = mark_tuplets(droot)
        if k:
            print(f'{k} tuplet group(s) in the display file had no bracket or number; marked for the video')
    if a.display and not closed:
        root, parts, names, notes_by_part, starts, sung = use_display(
            a.display, root, parts, names, notes_by_part, tempos)

    # ---- the order the music is played in: repeats unrolled. Every lit thing is placed by bar
    # and position in the bar, then at each moment that bar is played
    order = play_order(src_parts[0])
    piece_q = max(n['on'] + n['dur'] for ns_ in src_notes for n in ns_)
    blen = [b - a_ for a_, b in zip(src_starts, list(src_starts[1:]) + [piece_q])]
    ubars, u = [], Fr(0)
    for mi in order:
        ubars.append((mi, u))
        u += blen[mi]
    occ = {}
    for mi, us in ubars:
        occ.setdefault(mi, []).append(us)
    if len(order) != len(src_starts):
        print(f'repeats: {len(order)} bars played from {len(src_starts)} written')

    def bpm_at(q):
        v = tempos[0][1]
        for b, t in tempos:
            if b <= q + 1e-9:
                v = t
        return v
    utempos = []
    for mi, us in ubars:
        a0, a1 = src_starts[mi], src_starts[mi] + blen[mi]
        utempos.append((float(us), bpm_at(float(a0))))
        utempos += [(float(us) + b - float(a0), t) for b, t in tempos if float(a0) < b < float(a1)]
    usec = lambda uq: beats_to_sec(float(uq), utempos)

    def times_of(mi, q0, q1):
        """Score seconds (s0, s1) of written quarters q0..q1 in bar mi, each time the bar is played."""
        return [(usec(us + q0 - src_starts[mi]), usec(us + q1 - src_starts[mi])) for us in occ.get(mi, [])]

    # ---- the timing's own material, from the file the audio came from: every sounding note with
    # its pitch, and where each fermata ends (on a note or a rest where it does; over a barline, at
    # that barline)
    pitched, all_onsets, fermata_at = [], [], []
    for ns_ in src_notes:
        for n in ns_:
            if n['grace'] or n['dur'] == 0:
                continue
            spans = times_of(n['mi'], n['on'], n['on'] + n['dur'])
            if not n['rest']:
                all_onsets += [s0 for s0, _ in spans]
                if n['midi'] is not None:
                    pitched += [(s0, s1, n['midi']) for s0, s1 in spans]
            if n['el'].find('.//fermata') is not None:
                fermata_at += [s1 for _, s1 in spans]
    for mi, m in enumerate(src_parts[0].findall('measure')):
        for bl in m.findall('barline'):
            if bl.find('fermata') is not None:
                q = src_starts[mi] + (0 if bl.get('location') == 'left' else blen[mi])
                fermata_at += [s0 for s0, _ in times_of(mi, q, q)]
    # fermatas a moment apart are one hold for the fit, taken after the last of them: two
    # fermata eighths 0.4 s apart and a caesura (a ballad TTBB's last line) left too little
    # between them to measure, and the fit put -1.1 s on the second where playback held +0.75 s
    breaks = []
    for b in sorted(fermata_at):
        if breaks and b - breaks[-1] < 1.5:
            breaks[-1] = b
        else:
            breaks.append(b)
    first_score = min(all_onsets)

    # ---- what is shown, and whose each thing on it is; windows in written quarters by bar
    note_q, rest_q, syl_q = {}, {}, {}
    if closed:
        dparts, dnames, dnotes, staff_parts, owners, readers, fall, dstarts = closed_display(
            droot, names, notes_by_part, sung)
        if len(dstarts) != len(src_starts) or any(x != y for x, y in zip(dstarts, src_starts)):
            sys.exit('--display: the closed score\'s bars do not line up with the open score\'s')
        disp, d_all = droot, [n for ns_ in dnotes for n in ns_]
        pid_of = {n['id']: dparts[j].get('id') for j, ns_ in enumerate(dnotes) for n in ns_}
        pairs = [tuple(i for i in sp if i in sung) for sp in staff_parts.values()
                 if len([i for i in sp if i in sung]) == 2]
        staff_pid = {i: dparts[j].get('id') for j, sp in staff_parts.items() for i in sp}
        print(f'display: {os.path.basename(a.display)}, a closed score: ' + ', '.join(
            f'"{" ".join(dnames[j].split())}" = {" + ".join(names[i] for i in sp) or "?"}'
            for j, sp in staff_parts.items()) +
            f'; {fall} of {sum(1 for n in d_all if n["id"] in owners)} notes and rests placed by voice, the '
            'rest matched to the open score')
        for n in d_all:
            for i in owners.get(n['id'], ()):
                (rest_q if n['rest'] else note_q).setdefault(n['id'], []).append(
                    (i, n['mi'], n['on'], n['on'] + n['dur']))
        for i in sung:
            for hid, (mi, q0, q1) in part_windows(dnotes, owners, readers, i).items():
                syl_q.setdefault(hid, []).append((i, mi, q0, q1))
        syl_holder = {(i, hid): hid for hid, ps in readers.items() for i in ps}
        centre = dnotes
    else:
        if a.open:
            pairs = []
        elif a.staves:
            idx = {n.lower(): i for i, n in enumerate(names)}
            pairs = []
            for grp in a.staves.split(','):
                up, lo = (x.strip().lower() for x in grp.split('+'))
                if up not in idx or lo not in idx:
                    sys.exit(f'--staves: unknown part in {grp!r}; parts are {names}')
                pairs.append((idx[up], idx[lo]))
        else:
            pairs = default_pairs(names, sung)
        centre = notes_by_part
    # A rest that fills its bar alone is a bar rest, centred in the bar. Some files write it as a
    # plain whole rest on beat 1, which Verovio sets at the left edge of the bar; mark it as one.
    for ns_ in centre:
        by_bar = {}
        for n in ns_:
            if not n['grace']:
                by_bar.setdefault((n['mi'], n['voice'], n['el'].findtext('staff') or '1'), []).append(n)
        for (mi, _, _), evs in by_bar.items():
            if len(evs) == 1 and evs[0]['rest'] and evs[0]['rel'] == 0 and mi < len(blen) \
                    and evs[0]['dur'] == blen[mi]:
                evs[0]['el'].find('rest').set('measure', 'yes')
    if not closed:
        disp, owners, syl_holder = display_score(root, parts, notes_by_part, pairs, sung)
        d_all = [n for ns_ in notes_by_part for n in ns_]
        pair_of = {x: pr for pr in pairs for x in pr}
        staff_pid = {i: (f'PX{pair_of[i][0]}' if i in pair_of else parts[i].get('id')) for i in range(len(parts))}
        pid_of = {n['id']: staff_pid[i] for i, ns_ in enumerate(notes_by_part) for n in ns_}
        mi_of = {n['id']: n['mi'] for n in d_all}
        for i, ns_ in enumerate(notes_by_part):
            if i not in sung:
                continue
            for n in ns_:
                if not n['grace'] and n['dur'] > 0:
                    (rest_q if n['rest'] else note_q).setdefault(n['id'], []).append(
                        (i, n['mi'], n['on'], n['on'] + n['dur']))
            for nid, (q0, q1) in syllable_windows(ns_).items():
                h = syl_holder.get((i, nid))
                if h:
                    syl_q.setdefault(h, []).append((i, mi_of[nid], q0, q1))
        # a unison notehead carries both parts; the lower part's own note id is not printed
        for table in (note_q, rest_q):
            for nid, ps in owners.items():
                if nid in table:
                    have = {w[0] for w in table[nid]}
                    _, mi, q0, q1 = table[nid][0]
                    table[nid] += [(p, mi, q0, q1) for p in ps if p not in have]
    colours = {}                           # the parts sharing staves get the four strongest colours
    for i in [x for pr in pairs for x in pr] + sorted(sung):
        if i in sung and i not in colours:
            colours[i] = palette[len(colours) % len(palette)]
    print('parts: ' + ', '.join(f'{names[i]}{" (sung, " + colours[i] + ")" if i in sung else ""}'
                                 for i in range(len(names))))
    if not closed:
        print('staves: ' + ('open score' if not pairs else
                            ', '.join(f'{names[u_]} + {names[l_]}' for u_, l_ in pairs)))
    index_syl_holder(syl_holder)

    # each sung part's pulse: the coarsest note value that 95% of the bars it sings keep to
    # (every note starting and lasting a whole number of them; tuplets aside). A piece in
    # eighths with one bar of sixteenths pulses in eighths. A rest's bar fills in jumps of this
    # length counted from the barline, so the pulse shows, the way a sung note lights up
    pulse = {}
    for i in sung:
        bars_ = {}
        for n in src_notes[i]:
            if not n['grace'] and not n['tmod'] and n['dur'] > 0:
                bars_.setdefault(n['mi'], []).append(n)
        sung_bars = [ns_ for ns_ in bars_.values() if any(not n['rest'] for n in ns_)]
        pulse[i] = Fr(1, 8)
        for u_ in (Fr(4), Fr(2), Fr(1), Fr(1, 2), Fr(1, 4), Fr(1, 8)):
            fits = sum(all(n['rel'] % u_ == 0 and n['dur'] % u_ == 0 for n in ns_) for ns_ in sung_bars)
            if sung_bars and fits >= 0.95 * len(sung_bars):
                pulse[i] = u_
                break
        if a.pulse:
            pulse[i] = Fr(4, a.pulse)
    note_name = {Fr(4): 'whole', Fr(2): 'half', Fr(1): 'quarter', Fr(1, 2): 'eighth', Fr(1, 4): 'sixteenth',
                 Fr(1, 8): '32nd'}
    print('rest bars jump in: ' + ', '.join(f'{names[i]} {note_name.get(pulse[i], str(pulse[i]) + " quarter")}s'
                                             for i in sorted(sung)))

    def unroll(table):
        """{id: [(part, bar, q0, q1)]} -> {id: [(part, s0, s1, q0, q1, bar)]}, once per playing."""
        out = {}
        for k, ws in table.items():
            for p_, mi, q0, q1 in ws:
                for s0, s1 in times_of(mi, q0, q1):
                    out.setdefault(k, []).append((p_, s0, s1, q0, q1, mi))
        return out
    note_s, rest_s, syl_s = unroll(note_q), unroll(rest_q), unroll(syl_q)

    def steps(part, s0, s1, q0, q1, mi):
        """Score seconds where a rest's bar jumps: the end of each pulse inside the rest."""
        m0, u_ = src_starts[mi], pulse[part]
        k = (q0 - m0) // u_ + 1
        out = []
        while m0 + k * u_ < q1:
            out.append(s0 + float(m0 + k * u_ - q0) / float(q1 - q0) * (s1 - s0))
            k += 1
        return tuple(out) + (s1,)

    # where things are on the page, in written quarters: for the rest bars' time -> x maps, and
    # which screen each bar is on
    d_mi = {n['id']: n['mi'] for n in d_all}
    x_q = {n['id']: float(n['on']) for n in d_all if not n['grace'] and not (
        n['rest'] and (n['el'].find('rest').get('measure') == 'yes' or n['type'] in (None, 'whole') and n['rel'] == 0))}
    bar_end = {n['id']: float(src_starts[n['mi']] + blen[n['mi']]) for n in d_all if n['mi'] < len(blen)}
    last_on_q = {}
    for n in d_all:
        if not n['grace'] and not n['rest']:
            last_on_q[n['mi']] = max(last_on_q.get(n['mi'], n['on']), n['on'])

    # engrave
    import verovio
    install_smufl_font()
    z = 72.0 / a.staff_px
    band = int(round(0.045 * H))
    opts = {'pageWidth': int(W * z), 'pageHeight': int(H * z), 'scale': 100,
            'pageMarginTop': int((band + 0.01 * H) * z), 'pageMarginBottom': int(0.02 * H * z),
            'pageMarginLeft': int(0.02 * W * z), 'pageMarginRight': int(0.02 * W * z),
            'breaks': 'auto', 'header': 'none', 'footer': 'none', 'adjustPageHeight': False,
            'justifyVertically': False, 'lyricSize': 5.0, 'spacingSystem': 10, 'svgViewBox': False}
    k = mark_accidentals(disp)
    print('check, accidentals: ' + (f'{k} the file leaves to the reader, written out for the video' if k else
                                     'the file writes every one the page needs'))
    # every lyric line stops where its melisma does (SKILL.md 7.6): verify.py's check 14, on what is shown
    dsp = {sp.get('id'): (sp.findtext('part-name') or sp.get('id')).strip() for sp in disp.iter('score-part')}
    # which notes sing words of their own: the open score whose words are shown (a closed display file
    # given ready-made has none beside it, and verify.py --original checks that one)
    src_names = [(sp.findtext('part-name') or '').strip() for sp in root.iter('score-part')]

    def sung_on(p):                        # only the parts sharing that staff (a soloist is not the tenors)
        return frozenset() if closed else sung_positions(root, parts_on(dsp.get(p.get('id'), ''), src_names))
    bad = [f"{dsp.get(p.get('id'), p.get('id'))} voice {v} line {num}: the line from {t!r} (bar {mn}) runs on to "
           f"bar {last}, {why}" for p in disp.findall('part') for mn, v, num, t, last, why in lyric_line_runs(p, sung_on(p))]
    if bad:
        sys.exit('lyric lines that run on past their melisma in the score shown (SKILL.md 7.6):\n   ' + '\n   '.join(bad))
    print('check, lyric lines: every one stops where its melisma does' +
          ('' if not closed else ' (past rests only: a closed display file has no open score beside it)'))
    tk = verovio.toolkit()
    tk.setOptions(opts)
    if not tk.loadData(etree.tostring(disp).decode()):
        sys.exit('verovio could not read the closed score')
    wrong = pitch_readback(tk)
    if wrong:
        sys.exit('notes that read on the page as a pitch they do not sound (bar, staff, reads, sounds):\n   ' +
                 '\n   '.join(f'{b} staff {n}: reads {r}, sounds {s}' for b, n, _, r, s in wrong))
    print('check, pitch readback: every note reads on the page as the pitch it sounds')
    base_mei = tk.getMEI()
    # words printed above the staff: Verovio reads no placement from a MusicXML lyric, but honours
    # it on an MEI verse (@place). The note ids survive the trip, and a verse's @n is its lyric number
    above = {(n_.get('id'), ly.get('number') or '1') for n_ in disp.iter('note') for ly in n_.findall('lyric')
             if ly.get('placement') == 'above' and n_.get('id')}
    if above:
        M_, X_ = '{http://www.music-encoding.org/ns/mei}', '{http://www.w3.org/XML/1998/namespace}id'
        rm = etree.fromstring(base_mei.encode())
        k_ = 0
        for el in rm.iter(M_ + 'note', M_ + 'chord'):
            # a chord's verses sit under the <chord>, not its notes: take any member's placement
            ids = [el.get(X_)] + ([m_.get(X_) for m_ in el.iter(M_ + 'note')] if el.tag == M_ + 'chord' else [])
            for vv in el.findall(M_ + 'verse'):
                if any((i_, vv.get('n') or '1') in above for i_ in ids):
                    vv.set('place', 'above')
                    k_ += 1
        base_mei = etree.tostring(rm).decode()
        print(f'words above the staff: {k_} syllables, as printed')
    layouts = {}

    def layout(view):
        """The screens for one view. Staves empty for a whole system are hidden, as in a printed
        score (Verovio does this for MEI with <scoreDef optimize="true">, not for MusicXML, and
        keeps the note ids); in one part's own video its staff is never hidden, so its rests
        stay on screen to be lit."""
        if view in layouts:
            return layouts[view]
        _SYL_SVG.clear()
        mei = base_mei
        if not a.no_condense:
            M = '{http://www.music-encoding.org/ns/mei}'
            r = etree.fromstring(re.sub(r'<scoreDef ', '<scoreDef optimize="true" ', mei, count=1).encode())
            if view != 'all':
                pid = staff_pid.get(view)
                sd = next((d for d in r.iter(M + 'staffDef')
                           if d.get('{http://www.w3.org/XML/1998/namespace}id') == pid), None)
                for st in (r.iter(M + 'staff') if sd is not None else []):
                    if st.get('n') == sd.get('n') and st.find('.//' + M + 'note') is None \
                            and st.find('.//' + M + 'chord') is None:
                        # an invisible whole note keeps the staff; a second layer would push the
                        # rests off their usual lines, so pin them there (a whole rest hangs from the
                        # fourth line, loc 6; the rest sit on the middle line, loc 4). A bar of rest
                        # is an <mRest> or, from some files, a plain whole <rest>
                        for mr in st.iter(M + 'mRest'):
                            mr.set('loc', '6')
                        for rr in st.iter(M + 'rest'):
                            rr.set('loc', '6' if rr.get('dur') in ('1', 'breve', 'long') else '4')
                        ly = etree.SubElement(st, M + 'layer', n='9')
                        etree.SubElement(ly, M + 'note', dur='1', oct='4', pname='c', visible='false')
            mei = etree.tostring(r).decode()
        t = verovio.toolkit()
        t.setOptions(opts)
        if not t.loadData(mei):
            sys.exit('verovio could not re-read the score as MEI')
        # whose each tie and slur is: from the notes the MEI says it starts and ends on (the SVG
        # keeps the MEI ids). A tie is its notes' part's; a slur starting or ending on a chord
        # that two parts share is both parts'
        M, X = '{http://www.music-encoding.org/ns/mei}', '{http://www.w3.org/XML/1998/namespace}id'
        rr = etree.fromstring(mei.encode())
        chord_of = {}
        for ch in rr.iter(M + 'chord'):
            mem = [nn.get(X) for nn in ch.iter(M + 'note')]
            for nn in mem:
                chord_of[nn] = mem
        ctrl = {}
        d_end = {n['id']: (n['mi'], n['on'] + n['dur']) for n in d_all}

        def staff_sung(nid):
            # the parts on the fermata's own staff: the tenors' hold is not the basses'
            return {i for i, pid in staff_pid.items() if pid == pid_of.get(nid)}
        ferm_end = {}
        for i_, ns_ in enumerate(notes_by_part):
            for n in ns_:
                if i_ in sung and n['el'].find('.//fermata') is not None:
                    ferm_end.setdefault((n['mi'], n['on'] + n['dur']), set()).add(i_)
        for ch in rr.iter(M + 'chord'):
            chord_of[ch.get(X)] = [nn.get(X) for nn in ch.iter(M + 'note')]
        for tag in ('tie', 'slur', 'fermata'):
            for e in rr.iter(M + tag):
                st, en = (e.get('startid') or '').lstrip('#'), (e.get('endid') or '').lstrip('#')
                ends = [st, en] if tag == 'tie' else chord_of.get(st, [st]) + chord_of.get(en, [en])
                # a fermata is black in a part's own video only where it sits on that part's note or
                # rest (grey over everyone else's, like their notes)
                own = set().union(*[owners.get(i, set()) for i in ends if i])
                k_ = next((i for i in [st] + chord_of.get(st, []) if i in d_end), None)
                if tag == 'fermata' and k_:
                    # and every part holding its own fermata to the same moment (a bar rest's
                    # fermata, left out on the closed staff where it would stack over this one)
                    own |= ferm_end.get(d_end[k_], set()) & staff_sung(k_)
                ctrl[e.get(X)] = (tag, st, en, own)
        pages = [Page(t.renderToSVG(p), W, H, owners, syl_holder, colours, [view], names, int(band * 0.62),
                      x_q, bar_end, ctrl)
                 for p in range(1, t.getPageCount() + 1)]
        bar_page = {}                            # which screen each written bar is on
        for pi_, pg in enumerate(pages):
            for i in pg.ids_on_page:
                if i in d_mi:
                    bar_page.setdefault(d_mi[i], pi_)
        print(f'engraved for {"every part" if view == "all" else names[view]}: {len(pages)} screens of '
              f'{W}x{H}, staff {a.staff_px:.0f} px')
        nud = sum(p_.nudged for p_ in pages)
        if nud:
            print(f'   {nud} syllables moved right to clear the word before them on their line')
        layouts[view] = (pages, bar_page, ctrl)
        return layouts[view]

    jobs = []
    for mp3 in a.mp3s:
        f = featured_of(mp3, names, part_map)
        if f is not None and f not in sung:
            sys.exit(f'{mp3}: {names[f]} has no lyrics in the score')
        out_dir = a.out or os.path.dirname(os.path.abspath(mp3))
        base = os.path.splitext(os.path.basename(mp3))[0]
        jobs.append((mp3, 'all' if f is None else f, os.path.join(out_dir, base)))

    numbers = [m.get('number') for m in src_parts[0].findall('measure')]
    bar_sec = [(usec(us), numbers[mi]) for mi, us in ubars]

    for mp3, view, stem in jobs:
        pages, bar_page, ctrl = layout(view)
        if a.proof and view == 'all':
            from PIL import Image
            os.makedirs(a.proof, exist_ok=True)
            nums = [m.get('number') for m in src_parts[0].findall('measure')]
            for p_ in range(len(pages)):
                bars = sorted(mi for mi, pg in bar_page.items() if pg == p_)
                pages[p_].raster()
                fn = os.path.join(a.proof, f'screen {p_ + 1} bars {nums[bars[0]]}-{nums[bars[-1]]}.png')
                Image.fromarray(pages[p_].base['all']).save(fn)
                print(f'   proof screen: {os.path.basename(fn)}')
        ref, why = timing_source(mp3)
        T = Timing(ref, pitched, first_score, breaks)
        # hand-measured downbeats overrule the fit for the stretch between fermatas that holds them:
        # where the pitch alignment has too little to hold on to (a repeated piano figure, held
        # chords, few onsets) the fitted hold can come out seconds wrong, and even negative
        for an in a.anchor:
            num, t = an.split('=', 1)
            mm, _, ss = t.rpartition(':')
            t_audio = (float(mm) * 60 if mm else 0.0) + float(ss)
            s0 = next((s0 for s0, n_ in bar_sec if str(n_) == num.strip()), None)
            if s0 is None:
                sys.exit(f'--anchor {an}: no bar {num}')
            j = int(np.searchsorted(T.breaks, s0, side='right'))
            T.cum[j] = t_audio - float(T.straight(s0))
            T.steps = [float(v) for v in np.diff(T.cum)]
            print(f'   anchored: bar {num} at {t}, by hand (the stretch after fermata {j} of {len(T.breaks)})')
        # a stretch with no onsets to fit (after the last fermata: only the final note's end) holds
        # nothing of its own and keeps the offset before it. Left at the fit's value it did not follow
        # an anchor: bar 76's lights ended 6 s before they began, and the last bar never lit
        for j in range(1, len(T.cum)):
            lo_ = T.breaks[j - 1]
            hi_ = T.breaks[j] if j < len(T.breaks) else np.inf
            if not ((T.so >= lo_) & (T.so < hi_)).any():
                T.cum[j] = T.cum[j - 1]
        T.steps = [float(v) for v in np.diff(T.cum)]
        if ref != mp3:
            T.x = decode(mp3)                            # the audio check below is against this mp3
        def bar_at(t_audio):
            s = (t_audio - T.off) / T.scale
            cur = bar_sec[0][1]
            for s0, num in bar_sec:
                if s0 <= s + 1e-6:
                    cur = num
            return cur
        T.report(bar_at, f'{os.path.basename(mp3)} -> {"every part" if view == "all" else names[view]}')
        if why:
            print(f'   {why}')
        # page turns (audio seconds), in the order the bars are played: a repeat turns back.
        # Up to --lead s before the next screen's first bar, never before the last note on the old
        # screen has begun
        turns, pages_at, prev = [], [], None
        for k, (mi, us) in enumerate(ubars):
            pg_ = bar_page.get(mi)
            if pg_ is None or pg_ == prev:
                continue
            start = float(T(usec(us)))
            if prev is None:
                tsw = 0.0
            else:
                pmi, pus = ubars[k - 1]
                last_on = float(T(usec(pus + last_on_q.get(pmi, src_starts[pmi]) - src_starts[pmi])))
                tsw = min(start, max(last_on + 0.3, start - a.lead))
            turns.append(tsw)
            pages_at.append(pg_)
            prev = pg_
        # light windows per page: (t0, t1, page, group key, colour)
        wins = []
        page_of = {}                               # (kind, id) -> [(page, lit group)]
        for pi_, pg in enumerate(pages):
            for kind, key, _ in pg.elems:
                if kind == 'sylx':                 # an extender's continuation lights with its syllable
                    page_of.setdefault(('syl', key.split('#')[0]), []).append((pi_, (kind, key)))
                    continue
                if kind == 'tie':                  # each drawn piece of a tie, on whatever screen
                    page_of.setdefault(('tie', key.split('#')[0]), []).append((pi_, (kind, key)))
                    continue
                kk = ('note' if kind in ('body', 'head') else kind, key)
                gk = ('note', pg.alias.get(key, key)) if kk[0] == 'note' else kk
                if (pi_, gk) not in page_of.setdefault(kk, []):
                    page_of[kk].append((pi_, gk))
        score_end = max(w[2] for tb in (note_s, rest_s) for ws in tb.values() for w in ws)
        tie_s = {}
        for cid, (tag, st, en, ps) in ctrl.items():
            if tag == 'tie':
                tie_s[cid] = [w for nid in (st, en) for w in note_s.get(nid, []) if w[0] in ps]
        for kind, table in (('note', note_s), ('syl', syl_s), ('rest', rest_s), ('tie', tie_s)):
            for nid, ws in table.items():
                if (kind, nid) not in page_of:
                    continue
                for pi_, gk in page_of[(kind, nid)]:
                    for part, s0, s1, q0, q1, mi in ws:
                        if view == 'all' or part == view:
                            t1_ = float(T(s1))
                            if s1 >= score_end - 1e-6 and kind != 'rest':
                                # playback holds the final fermata as long as it likes: the last
                                # notes stay lit until the sound stops
                                t1_ = max(t1_, min(T.last_audio, T.dur))
                            wins.append((float(T(s0)), t1_, pi_, gk, colours[part], part, s0, s1,
                                         steps(part, s0, s1, q0, q1, mi) if kind == 'rest' else None,
                                         float(q0), float(q1)))
        wins.sort()

        t_start, t_len = 0.0, T.dur
        if a.clip:
            c0, c1 = (float(v) for v in a.clip.split(','))
            t_start, t_len = c0, min(c1, T.dur - c0)

        def lit_key(p, ws, t):
            lit, prog = {}, {}
            for w in ws:
                if w[2] == p:
                    lit.setdefault(w[3], set()).add((w[5], w[4]))
                    rb = pages[p].rest_bar.get(w[3][1]) if w[3][0] == 'rest' else None
                    if rb is not None:
                        ts, xs = pages[p].timemap[rb[0]]
                        s = w[6] + (t - w[0]) / max(w[1] - w[0], 1e-6) * (w[7] - w[6])
                        s = next((b for b in w[8] if b > s + 1e-9), w[7])   # through the current pulse
                        q = w[9] + (s - w[6]) / max(w[7] - w[6], 1e-9) * (w[10] - w[9])   # where on the page
                        prog[w[3]] = tuple(int(round(float(np.interp(v, ts, xs)))) for v in (w[9], w[10], q))
            return (p, tuple(sorted((k, tuple(c for _, c in sorted(v)), prog.get(k)) for k, v in lit.items())))

        def page_at(t):
            k = bisect.bisect_right(turns, t) - 1
            return pages_at[max(k, 0)]

        def frame_at(t):
            p = page_at(t)
            return lit_key(p, [w for w in wins if w[0] <= t < w[1]], t)

        def compose(key):
            p, lit = key
            pages[p].raster()
            fr = pages[p].base[view].copy()
            pages[p].lights.apply(fr.reshape(-1, 3), list(lit))
            return fr

        from PIL import Image
        if a.stills:
            for tv in a.stills.split(','):
                tv = float(tv)
                path = f'{stem} @{tv:.0f}s.png'
                Image.fromarray(compose(frame_at(tv))).save(path)
                print(f'   still: {path}')
            continue

        out = stem + ('' if not a.clip else f' clip {int(t_start)}-{int(t_start + t_len)}s') + '.mp4'
        t_end = t_start + t_len
        # Variable frame rate: one frame per change of lights or page, shown from the exact
        # moment of the change (to the millisecond) until the next. No frame grid, so no rounding
        # of a light to the nearest frame, and nothing encoded twice.
        ev = {t_start, t_end}
        for w in wins:
            ev.update(v for v in (w[0], w[1]) if t_start < v < t_end)
            if w[8]:
                ev.update(float(T(b)) for b in w[8] if t_start < float(T(b)) < t_end)
        ev.update(v for v in turns if t_start < v < t_end)
        ev = sorted(ev)
        segs = []                                  # (start ms, key)
        wi, active = 0, []
        for e0, e1 in zip(ev[:-1], ev[1:]):
            t = (e0 + e1) / 2
            while wi < len(wins) and wins[wi][0] <= t:
                active.append(wins[wi])
                wi += 1
            active = [w for w in active if w[1] > t]
            key = lit_key(page_at(t), active, t)
            ms = int(round(1000 * (e0 - t_start)))
            if segs and (segs[-1][1] == key or segs[-1][0] == ms):
                if segs[-1][1] != key:
                    segs[-1] = (ms, key)           # under a millisecond: the later state wins
                continue
            segs.append((ms, key))
        end_ms = int(round(1000 * t_len))
        tmpd = tempfile.mkdtemp(prefix='score_video_')
        lines = ['ffconcat version 1.0']
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
            jobs_ = []
            for k, (ms, key) in enumerate(segs):
                fn = os.path.join(tmpd, f'{k:06d}.png')
                jobs_.append(pool.submit(lambda im, fn: Image.fromarray(im).save(fn, compress_level=1),
                                         compose(key), fn))
                nxt = segs[k + 1][0] if k + 1 < len(segs) else end_ms
                lines += [f"file '{fn}'", 'option framerate 1000', f'duration {(nxt - ms) / 1000:.3f}']
            for jb in jobs_:
                jb.result()
        lines += [f"file '{os.path.join(tmpd, f'{len(segs) - 1:06d}.png')}'", 'option framerate 1000']
        lst = os.path.join(tmpd, 'frames.ffconcat')
        open(lst, 'w').write('\n'.join(lines) + '\n')
        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
               '-ss', f'{t_start:.3f}', '-t', f'{t_len:.3f}', '-i', mp3, '-map', '0:v', '-map', '1:a',
               *vfr_flag(), '-video_track_timescale', '1000', '-c:v', 'libx264', '-preset', 'veryfast',
               '-tune', 'stillimage', '-g', '30', '-crf', str(a.crf), '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '192k', '-t', f'{t_len:.3f}', '-movflags', '+faststart', out]
        r = subprocess.run(cmd)
        shutil.rmtree(tmpd, ignore_errors=True)
        if r.returncode:
            sys.exit(f'ffmpeg failed on {out}')
        # check the audio that landed against the mp3 (an AAC priming delay would shift everything)
        y = decode(out)
        x = T.x[int(t_start * 22050):int(t_start * 22050) + len(y)]
        n = min(len(x), len(y), 22050 * 20)
        lag = 0
        if n > 22050:
            seg_x, seg_y = x[:n] - x[:n].mean(), y[:n] - y[:n].mean()
            cc = np.fft.irfft(np.fft.rfft(seg_y, 2 * n) * np.conj(np.fft.rfft(seg_x, 2 * n)))
            k = int(np.argmax(np.concatenate([cc[-2205:], cc[:2206]]))) - 2205
            lag = k / 22.05
        print(f'   wrote {os.path.basename(out)}: {len(segs)} frames, one per change of lights or page; '
              f'audio in the mp4 is {lag:+.1f} ms from the mp3')
        check_frames(out, [ms for ms, _ in segs])
        if all(v != view for _, v, _ in jobs[jobs.index((mp3, view, stem)) + 1:]):
            layouts.pop(view, None)              # its screens are not needed again: free them
    if not (a.child or a.stills or a.clip):
        proof_note(a)


if __name__ == '__main__':
    main()
