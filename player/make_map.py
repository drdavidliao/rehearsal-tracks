#!/usr/bin/env python3
"""Write the beat map the rehearsal player needs for a song folder (see README.md here).

    python3 player/make_map.py "song folder" --reader-pdf "... Full score copy.pdf" --score "... (lesson marks).pdf"
        --xml "....musicxml" --stems "Tenor 1=...wav" "Tenor 2=...wav" ... "I=...wav" [--nstaves 6] [--offset 1.02]

A stem is named by its MusicXML part name; I is the one instrumental stem, and a song without one leaves it out. The letters
S, A, A2, T and B still name Soprano, Alto (or Alto 1), Alto 2, Tenor and Bass.

Bars, beats and their x positions come from the vector PDF through dorico_reader.py; times come from the MusicXML's
tempo marks. Without --offset, the time of bar 1 is measured: the fit of the on-beat piano attacks to the instrumental
stem, or in a score with no such part, of each voice's on-beat attacks to its own stem. Swung offbeats are left out of
that fit, and it reports how far the stems drift from the score bar by bar.
A rit mark in the MusicXML (rit, riten, rall) bends the times from its bar to the end of the song, fitted to the stems.
Writes "player map.json" in the song folder, paths relative to it.
"""
import argparse, bisect, copy, json, os, re, subprocess, sys, xml.etree.ElementTree as ET
from fractions import Fraction as F
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import dorico_reader as dr
import vector_reader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dark_score

SR, HOP = 44100, 441
FINE = 220


def beat_len(meter):
    num, den = meter
    if den == 8 and num % 3 == 0: return F(3, 2)
    return F(4, den)


def read_xml(path):
    """per bar: quarters, tempo at its start, rehearsal mark; and per part the attacks as (bar index, quarters into bar)"""
    root = ET.parse(path).getroot()
    names = {sp.get('id'): sp.findtext('part-name') for sp in root.iter('score-part')}
    bars, attacks = [], {}
    tempo = None
    for pi, part in enumerate(root.findall('part')):
        div = 1; ons = []
        for mi, m in enumerate(part.findall('measure')):
            pos = mx = F(0)
            if pi == 0: bars.append(dict(tempos=[], letter=None))
            for e in m:
                if e.tag == 'attributes' and e.find('divisions') is not None: div = int(e.findtext('divisions'))
                elif e.tag == 'backup': pos -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward': pos += F(int(e.findtext('duration')), div); mx = max(mx, pos)
                elif e.tag == 'note':
                    if e.find('chord') is not None: continue
                    d = F(int(e.findtext('duration') or 0), div)
                    tied = any(t.get('type') == 'stop' for t in e.findall('tie'))
                    if e.find('rest') is None and not tied: ons.append((mi, pos))
                    pos += d; mx = max(mx, pos)
                elif e.tag == 'direction' and pi == 0:
                    if e.findtext('direction-type/rehearsal'): bars[mi]['letter'] = e.findtext('direction-type/rehearsal').strip()
                    s = e.find('sound')
                    if s is not None and s.get('tempo'): bars[mi]['tempos'].append((pos, float(s.get('tempo'))))
            if pi == 0: bars[mi]['quarters'] = mx
        attacks[names[part.get('id')]] = ons
    return bars, attacks


def rising(px, py, gap=1.0):
    """A bar's onset positions, or only its ends (beat 1 and the barline) when they don't rise left to right. A crowded
    piano bar can be misread with notes at the wrong onsets, and then no subset of its positions can be trusted (in one,
    beats 2-4 read 194, 184, 180 for a page's 180, 195, 208): spaced evenly across the bar, the cursor is a few points
    out at worst, instead of sliding back across the bar or holding two beats at one place."""
    if all(b - a >= gap for a, b in zip(py, py[1:])): return px, py
    return [px[0], px[-1]], [py[0], py[-1]]


# the letters older commands used for an SATB score's stems
LETTERS = {'S': ['Soprano'], 'A': ['Alto', 'Alto 1'], 'A2': ['Alto 2'], 'T': ['Tenor'], 'B': ['Bass']}


def xml_meters(path):
    """each bar's time signature, as (beats, beat type)"""
    root = ET.parse(path).getroot()
    out, m_ = [], (4, 4)
    for meas in root.find('part').findall('measure'):
        t = meas.find('attributes/time')
        if t is not None and t.findtext('beats'): m_ = (int(t.findtext('beats').split('+')[0]), int(t.findtext('beat-type')))
        out.append(m_)
    return out


def xml_numbers(path):
    """each bar's number as printed: the MusicXML's own (a pickup is 0), or its place counting from 1 where that isn't a number"""
    ms = ET.parse(path).getroot().find('part').findall('measure')
    return [int(m.get('number')) if (m.get('number') or '').lstrip('-').isdigit() else i + 1 for i, m in enumerate(ms)]


def xml_repeats(path):
    """{last bar index: (first bar index, times played, last bar index played again)} for each repeat. With first and
    second endings, the time round again stops before the first ending: the second follows the repeat sign."""
    ms = ET.parse(path).getroot().find('part').findall('measure')
    out, s0, ending1 = {}, 0, None
    for i, m in enumerate(ms):
        for bl in m.findall('barline'):
            e = bl.find('ending')
            if e is not None and e.get('type') == 'start' and ending1 is None: ending1 = i
            r = bl.find('repeat')
            if r is None: continue
            if r.get('direction') == 'forward': s0 = i; ending1 = None
            else:
                out[i] = (s0, int(r.get('times') or 2), (ending1 - 1) if ending1 is not None and ending1 > s0 else i)
                s0 = i + 1; ending1 = None
    return out


def play_order(path):
    """the bar indices in the order they're sung: repeats with their endings, and a D.S. or D.C. (al Coda, al Fine). The
    marks are MusicXML's: repeat and ending barlines, and sound segno, coda, tocoda, dalsegno, dacapo and fine, or where a
    direction has no sound, a segno or coda sign and the words "D.S.", "D.C.", "To Coda" and "Fine". After the jump back,
    repeats aren't taken, a "To Coda" goes to the coda, and an ending that leads back to its repeat is passed over."""
    parts = ET.parse(path).getroot().findall('part')
    ms = [p.findall('measure') for p in parts]
    n = len(ms[0])
    marks = [dict(forward=False, backward=0, ending=None, ending_end=False) for _ in range(n)]
    for i in range(n):
        mk = marks[i]
        for p in ms:
            if i >= len(p): continue
            m = p[i]
            for bl in m.findall('barline'):
                r = bl.find('repeat')
                if r is not None and r.get('direction') == 'forward': mk['forward'] = True
                if r is not None and r.get('direction') == 'backward': mk['backward'] = int(r.get('times') or 2)
                e = bl.find('ending')
                if e is not None and e.get('type') == 'start':
                    mk['ending'] = {int(x) for x in re.findall(r'\d+', e.get('number') or '1')}
                if e is not None and e.get('type') in ('stop', 'discontinue'): mk['ending_end'] = True
            for d in m.iter('direction'):
                s = d.find('sound')
                s = s.attrib if s is not None else {}
                words = ' '.join(w.text or '' for w in d.iter('words')).strip().lower()
                if 'segno' in s or (not s and d.find('direction-type/segno') is not None): mk['segno'] = True
                if 'coda' in s or (not s and d.find('direction-type/coda') is not None and 'coda' not in words): mk['coda'] = True
                if 'tocoda' in s or (not s and re.search(r'\bto coda\b', words)): mk['tocoda'] = True
                if 'dalsegno' in s or (not s and re.match(r'd\.\s*s\.|dal segno', words)): mk['ds'] = True
                if 'dacapo' in s or (not s and re.match(r'd\.\s*c\.|da capo', words)): mk['dc'] = True
                if 'fine' in s or (not s and words == 'fine'): mk['fine'] = True
    segno = next((i for i in range(n) if marks[i].get('segno')), None)
    coda = next((i for i in range(n) if marks[i].get('coda')), None)
    def ending_last(i):
        while i < n - 1 and not marks[i]['ending_end']: i += 1
        return i
    order, i, start, pass_, done, jumped = [], 0, 0, 1, {}, False
    while i < n and len(order) < 20 * n:
        mk = marks[i]
        if mk['forward'] and start != i: start, pass_ = i, 1
        if mk['ending'] is not None:
            last = ending_last(i)
            take = marks[last]['backward'] == 0 if jumped else pass_ in mk['ending']
            if not take:
                i = last + 1; continue
        order.append(i)
        if mk['backward'] and not jumped and done.get(i, 1) < mk['backward']:
            done[i] = done.get(i, 1) + 1; pass_ += 1; i = start; continue
        if mk['backward']: start, pass_ = i + 1, 1
        if jumped and mk.get('fine'): break
        if jumped and mk.get('tocoda') and coda is not None and coda > i:
            i = coda; continue
        if not jumped and (mk.get('ds') and segno is not None or mk.get('dc')):
            jumped = True; i = segno if mk.get('ds') else 0; start, pass_ = i, 1; continue
        i += 1
    return order


def unroll(path, out, order):
    """the MusicXML with its bars in the sung order: each bar a copy, numbered by its place in the order (unique, as the
    warp's guide and pins need), repeat and ending barlines dropped. A bar sung out of its written place starts with the
    key, meter and tempo it had there, where those differ from what's in effect."""
    tree = ET.parse(path); root = tree.getroot()
    tempos = {}
    for pi, part in enumerate(root.findall('part')):
        ms = part.findall('measure')
        # what's in effect at the start of each written bar
        state, at = {}, []
        for m in ms:
            at.append(dict(state))
            for a_ in m.findall('attributes'):
                for tag in ('divisions', 'key', 'time'):
                    if a_.find(tag) is not None: state[tag] = a_.find(tag)
            if pi == 0:
                for s in m.iter('sound'):
                    if s.get('tempo'): state['tempo'] = s.get('tempo')
        if pi == 0: tempos = {i: at[i].get('tempo') for i in range(len(ms))}
        for m in list(part): part.remove(m)
        cur = {}
        for k, i in enumerate(order):
            m = copy.deepcopy(ms[i]); m.set('number', str(k))
            if k: m.attrib.pop('implicit', None)
            for bl in m.findall('barline'): m.remove(bl)
            if k and order[k - 1] != i - 1:
                # a jump: carry in what this bar had where it's written
                fix = [tag for tag in ('divisions', 'key', 'time') if tag in at[i] and
                       (cur.get(tag) is None or ET.tostring(cur[tag]) != ET.tostring(at[i][tag]))]
                if fix:
                    a_ = ET.Element('attributes')
                    for tag in fix: a_.append(copy.deepcopy(at[i][tag]))
                    m.insert(0, a_)
                if pi == 0 and tempos.get(i) and tempos[i] != cur.get('tempo'):
                    d = ET.Element('direction'); ET.SubElement(d, 'sound', tempo=tempos[i]); m.insert(0, d)
            for a_ in m.findall('attributes'):
                for tag in ('divisions', 'key', 'time'):
                    if a_.find(tag) is not None: cur[tag] = a_.find(tag)
            for s in m.iter('sound'):
                if s.get('tempo'): cur['tempo'] = s.get('tempo')
            part.append(m)
    tree.write(out, encoding='UTF-8', xml_declaration=True)


def voice_stems(stems, parts):
    """the voice stems in score order, as (key, part name): the key names the stem in the map and the notes' part"""
    out = []
    for k in stems:
        if k == 'I': continue
        if k in parts: out.append((k, k))
        elif k in LETTERS and any(n in parts for n in LETTERS[k]): out.append((k, next(n for n in LETTERS[k] if n in parts)))
        else: sys.exit(f'no part {k!r} in the MusicXML; its parts are {parts}')
    return sorted(out, key=lambda v: parts.index(v[1]))
STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def read_voice_notes(path, parts):
    """per voice, its sung notes with ties joined: start and end as (bar index, quarters into bar), pitch, word"""
    root = ET.parse(path).getroot()
    names = {sp.get('id'): sp.findtext('part-name') for sp in root.iter('score-part')}
    out = {}
    swing = any(True for _ in root.iter('swing'))
    for part in root.findall('part'):
        name = names[part.get('id')]
        if name not in parts: continue
        div = 1; notes = []; open_ = None
        for mi, m in enumerate(part.findall('measure')):
            pos = F(0)
            els = list(m)
            for ei, e in enumerate(els):
                if e.tag == 'attributes' and e.find('divisions') is not None: div = int(e.findtext('divisions'))
                elif e.tag == 'backup': pos -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward': pos += F(int(e.findtext('duration')), div)
                elif e.tag == 'note':
                    if e.find('chord') is not None: continue
                    d = F(int(e.findtext('duration') or 0), div)
                    # a chord's first full-size note is the part's: a small optional octave (a cue-size head) is not
                    if e.find('type') is not None and e.find('type').get('size') == 'cue':
                        for c in els[ei + 1:]:
                            if c.tag != 'note' or c.find('chord') is None: break
                            if c.find('type') is None or c.find('type').get('size') != 'cue':
                                e = c; break
                    if e.find('rest') is None:
                        types = [t.get('type') for t in e.findall('tie')]
                        if 'stop' in types and open_ is not None:
                            open_['end'] = (mi, pos + d); open_['heads'].append((mi, pos))
                        else:
                            st = e.find('pitch')
                            midi = 12 * (int(st.findtext('octave')) + 1) + STEP[st.findtext('step')] + int(float(st.findtext('alter') or 0))
                            open_ = dict(start=(mi, pos), end=(mi, pos + d), midi=midi, word=(e.findtext('lyric/text') or ''), heads=[(mi, pos)])
                            notes.append(open_)
                        if 'start' not in types: open_ = None
                    pos += d
        out[name] = notes
    return out, swing


def swung(q, swing):
    """an offbeat eighth, played at two thirds of the beat in swing; triplets are as written"""
    if not swing: return q
    whole = q.numerator // q.denominator
    return whole + F(2, 3) if q - whole == F(1, 2) else q


def fine_envelope(path):
    a = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                                     capture_output=True, check=True).stdout, dtype='f4')
    n = len(a) // FINE
    e = np.sqrt((a[:n * FINE].reshape(n, FINE) ** 2).mean(1))
    return e


def snap_notes(notes, env):
    """moves each note's times from the score's onto its stem: the start to just before the attack near it, where there
    is one; the end to the next note's start when that follows on, else to where the sound has died away"""
    le = np.log(env + 1e-3)
    fl = np.maximum(np.diff(le, prepend=le[0]), 0)
    # the rise over 20 ms: an attack shows here even when it takes several frames
    rise = np.convolve(fl, np.ones(4), 'same')
    fr = SR / FINE
    moved = 0
    for n in notes:
        lo, hi = int((n['start_t'] - 0.07) * fr), int((n['start_t'] + 0.15) * fr)
        w = rise[max(lo, 0):hi]
        if len(w) and w.max() > 0.5:
            n['start_t'] = (max(lo, 0) + int(np.argmax(w))) / fr - 0.03
            moved += 1
    for a, b in zip(notes, notes[1:] + [None]):
        follows = b is not None and b['start_t'] - a['end_t'] < 0.1
        if follows:
            a['end_t'] = b['start_t']; continue
        i0 = int(a['start_t'] * fr); i1 = int((a['end_t'] + 0.4) * fr)
        if b is not None: i1 = min(i1, int((b['start_t'] - 0.01) * fr))
        seg = env[i0:i1]
        if not len(seg): continue
        low = np.nonzero(seg[int(max(a['end_t'] - 0.1 - a['start_t'], 0) * fr):] < seg.max() * 0.05)[0]
        off = int(max(a['end_t'] - 0.1 - a['start_t'], 0) * fr)
        a['end_t'] = (i0 + off + int(low[0])) / fr if len(low) else i1 / fr
    for a in notes:
        a['end_t'] = max(a['end_t'], a['start_t'] + 0.06)
    return moved


RIT = re.compile(r'^(rit|riten|rall|poco rit|molto rit)', re.I)


def rit_bars(path):
    """the bar index each rit-like mark is in"""
    root = ET.parse(path).getroot()
    out = set()
    for part in root.findall('part'):
        for mi, m in enumerate(part.findall('measure')):
            if any(w.text and RIT.match(w.text.strip()) for w in m.iter('words')): out.add(mi)
    return sorted(out)


def fit_rit(events, t0, total, sound_end):
    """A rit's beat length, as a smooth curve: the score's times, then a step to c times slower and a further slowing by a
    at the end of its span. events: (seconds into the rit by the score, that stem's attacks). Attacks alone won't do, because
    a soft consonant or a legato note has none. The last bar has to end where the sound does, give or take its reverb.
    Returns (c, a, p) with the most attack strength under its notes."""
    best = (-1, 1, 0, 1)
    fr = SR / FINE
    u = np.linspace(0, total, 1601)
    for c in np.arange(1, 3.01, 0.05):
        for a in np.arange(0, 8.01, 0.05):
            for p in (0.5, 1, 2, 3):
                t = t0 + np.concatenate([[0], np.cumsum((c + a * (u[:-1] / total) ** p) * (u[1] - u[0]))])
                if not sound_end - 1.0 <= t[-1] <= sound_end + 0.2: continue
                sc = 0
                for e, fl in events:
                    i = int(np.interp(e, u, t) * fr)
                    if 3 <= i < len(fl) - 4: sc += fl[i - 3:i + 4].max()
                if sc > best[0]: best = (sc, c, a, p)
    return best[1:]


def flux(path):
    a = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                                     capture_output=True, check=True).stdout, dtype='f4')
    n = len(a) // HOP
    e = np.log(np.sqrt((a[:n * HOP].reshape(n, HOP) ** 2).mean(1)) + 1e-3)
    return np.maximum(np.diff(e, prepend=e[0]), 0)


def best_offset(d, secs, lo, hi, step=0.005):
    best = (-1, lo)
    for o in np.arange(lo, hi, step):
        idx = ((secs + o) * SR / HOP).astype(int)
        idx = idx[(idx >= 0) & (idx < len(d) - 1)]
        v = (d[idx] + d[idx + 1]).sum()
        if v > best[0]: best = (v, float(o))
    return best[1]


def fit_warp(xml, xbars, plain_secs, total, voice_stems, offset, beat=False, guide_path=None, pins=(), labels=None, at_q=None,
             inst=None):
    """where the stems' tempo strays from the written one: an offset for each bar (or beat), chosen together so that the
    voices' attacks land on their stems' attacks and the offset changes little from piece to piece (a hold can jump it; a
    repeated figure, which fits as well a beat either way, can't), and followed between piece starts. voice_stems: (part,
    stem path). labels: each bar's name in the guide and pins (default its number); a guide line naming none of them is left
    out. at_q(bar, q): where an attack written q quarters into a bar is played (swing), in quarters. inst: (attacks as (bar
    index, quarters), stem path), the instrumental part on its stem, so that bars where nobody sings (an introduction, an
    interlude) are timed too. Returns the anchors (score seconds, stem seconds)."""
    at_q = at_q or (lambda i, q: q)
    vn_, _ = read_voice_notes(xml, [n_ for n_, _ in voice_stems])
    refs = []
    for n_, path in voice_stems:
        d = flux(path); d = d / (np.percentile(d[d > 0], 99) if (d > 0).any() else 1)
        refs.append((d, [(nt['start'][0], at_q(*nt['start'])) for nt in vn_.get(n_, [])]))
    if inst:
        d = flux(inst[1]); d = d / (np.percentile(d[d > 0], 99) if (d > 0).any() else 1)
        refs.append((d, [(i, at_q(i, q)) for i, q in inst[0]]))
    # the pieces an offset is fitted for: bars, or with --warp-beat beats, for singing that bends the time inside a bar
    if beat:
        mts_ = xml_meters(xml)
        segs = [(i, k * beat_len(mts_[i])) for i in range(len(xbars))
                for k in range(max(1, int(xbars[i]['quarters'] / beat_len(mts_[i]))))]
    else:
        segs = [(i, F(0)) for i in range(len(xbars))]
    seg_t = [plain_secs(i, q) for i, q in segs]
    nb = len(segs)
    nums_, mts_p = labels or [str(x) for x in xml_numbers(xml)], xml_meters(xml)
    guide = []
    for ln in (open(guide_path).read().split() if guide_path else []):
        pos_, sec_ = ln.split('='); bar_, beat_ = (pos_.split('.') + ['1'])[:2]
        if bar_ not in nums_: continue
        bi = nums_.index(bar_); s_ = plain_secs(bi, (int(beat_) - 1) * beat_len(mts_p[bi]))
        j = bisect.bisect_right(seg_t, s_ + 1e-6) - 1
        if abs(seg_t[j] - s_) < 1e-6: guide.append((j, float(sec_) - s_))
    # the offsets tried: with a guide, as far as it goes either way
    lo_, hi_ = (min(o for _, o in guide) - 1, max(o for _, o in guide) + 1) if guide else (offset - 2.0, offset + 6.0)
    grid = np.arange(lo_, hi_, 0.02)
    S = np.zeros((nb, len(grid)))
    for d, on in refs:
        for i, q in on:
            s_ = plain_secs(i, q)
            j = max(0, bisect.bisect_right(seg_t, s_ + 1e-6) - 1)
            idx = ((s_ + grid) * SR / HOP).astype(int)
            ok = (idx >= 0) & (idx < len(d) - 1)
            S[j, ok] += d[idx[ok]] + d[idx[ok] + 1]
    # measured times the fit must pass through, where slow legato singing gives it too few attacks to find its way
    for t_ in pins:
        pos_, sec_ = t_.split('='); bar_, beat_ = (pos_.split('.') + ['1'])[:2]
        assert bar_ in nums_, f'--pin {t_}: no bar {bar_}'
        s_ = plain_secs(nums_.index(bar_), (int(beat_) - 1) * beat_len(mts_p[nums_.index(bar_)]))
        j = bisect.bisect_right(seg_t, s_ + 1e-6) - 1
        assert abs(seg_t[j] - s_) < 1e-6, f'--pin {t_}: not the start of a {"beat" if beat else "bar"}'
        S[j, np.abs(grid - (float(sec_) - s_)) > 0.011] -= 1e6
    # a guide: rough times for the pieces, from following the sung pitch, which a song sung freely needs; attacks alone
    # can lock a beat or a bar out and fit as well there. The fit keeps within 0.35 s of it
    for j, o in guide: S[j, np.abs(grid - o) > 0.35] -= 1e6
    # score given up per second of change: holds and slower playing push the audio later, so the offset falling
    # costs three times as much as it rising
    diff = grid[None, :] - grid[:, None]            # from k (row) to j (column)
    step = np.where(diff >= 0, 15.0 * diff, -45.0 * diff)
    V = S[0].copy(); back = np.zeros((nb, len(grid)), int)
    for i in range(1, nb):
        T = V[:, None] - step               # from k to j
        back[i] = T.argmax(0); V = T.max(0) + S[i]
    k = int(V.argmax()); offs = [0.0] * nb
    for i in range(nb - 1, -1, -1):
        offs[i] = float(grid[k]); k = back[i][k]
    print('warp: offset by', 'beat' if beat else 'bar', 's:', ' '.join(f'{o:.2f}' for o in offs))
    anchors = [(-1.0, -1.0 + offs[0])] + [(seg_t[j], seg_t[j] + offs[j]) for j in range(nb)] + \
              [(total + 30, total + 30 + offs[-1])]
    return anchors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder'); ap.add_argument('--reader-pdf', required=True); ap.add_argument('--score', required=True)
    ap.add_argument('--xml', required=True); ap.add_argument('--stems', nargs='+', required=True)
    ap.add_argument('--nstaves', type=int, default=6); ap.add_argument('--offset', type=float)
    ap.add_argument('--instrument-part', default='Piano')
    ap.add_argument('--staff', nargs='+', help='for a score not from Dorico: "Part=label" per part, parts sharing a staff sharing a label')
    ap.add_argument('--layout', nargs='+', help='"n=label,label,..." for a system of n staves (default: the labels in order)')
    ap.add_argument('--warp', action='store_true', help='fit the time every 4 bars, for stems whose tempo strays from the written one')
    ap.add_argument('--warp-beat', action='store_true', help='with --warp: fit every beat, not every bar, for singing freer than a bar at a time')
    ap.add_argument('--guide', help='with --warp: a file of "bar.beat=seconds" lines, rough times the fit keeps within 0.35 s of')
    ap.add_argument('--pin', nargs='+', default=[], help='with --warp: "bar.beat=seconds" measured times the fit must pass through')
    ap.add_argument('--anchor', nargs='+', default=[], help='"bar.beat=seconds": measured times; from the first of them on, the times follow these')
    ap.add_argument('--trim', nargs='+', default=[], help='"Part=dB": a stem louder or softer than the others were made, as the mixes trim it')
    ap.add_argument('--names', nargs='+', help='"pattern=label": a staff whose printed name matches takes the label, first match winning')
    a = ap.parse_args()
    at = lambda f: os.path.join(a.folder, f)
    stems = dict(s.split('=', 1) for s in a.stems)

    xbars, attacks = read_xml(at(a.xml))
    xml_parts = list(attacks)          # top to bottom
    voices = voice_stems(stems, xml_parts)
    STEM_OF = {name: key for key, name in voices}
    VOICES = [name for _, name in voices]
    import pdfplumber
    with pdfplumber.open(at(a.reader_pdf)) as p: npages = len(p.pages)
    if a.staff:
        # any engraver's PDF: the bars and heads found from the MusicXML (vector_reader.py)
        layouts = {int(k): v.split(',') for k, v in (s_.split('=', 1) for s_ in a.layout)} if a.layout else None
        names = [tuple(s_.split('=', 1)) for s_ in a.names] if a.names else None
        vs = vector_reader.Score(at(a.reader_pdf), at(a.xml), dict(s_.split('=', 1) for s_ in a.staff), layouts, names)
        for pr in vs.problems: print('  reader:', pr)
        assert len(vs.bars) == len(xbars), (len(vs.bars), len(xbars))
        page_h = vs.H
    else:
        r = dr.Reader(at(a.reader_pdf), range(npages), nstaves=a.nstaves).read().voices()
        assert len(r.bars) == len(xbars), (len(r.bars), len(xbars))
        page_h = float(r.pms[0].H)

    # seconds from bar 1 at the start of each bar, with tempo changes inside bars
    tempo = next((t for b in xbars for _, t in b['tempos']), 120.0)
    t = 0.0; starts = []
    def secs(bar_i, q):
        return starts[bar_i][0] + piece(bar_i, q)
    def piece(bar_i, q):
        cur = starts[bar_i][1]; pos = F(0); out = 0.0
        for at_, tp in xbars[bar_i]['tempos']:
            if at_ >= q: break
            out += float(at_ - pos) * 60 / cur; pos = at_; cur = tp
        return out + float(q - pos) * 60 / cur
    repeats = xml_repeats(at(a.xml))
    played = []        # the bars in the order the stems play them: (bar index, score seconds at its start)
    for i, b in enumerate(xbars):
        starts.append((t, tempo))
        played.append((i, t))
        t += piece(i, b['quarters'])
        if b['tempos']: tempo = b['tempos'][-1][1]
        # a repeat: the stems play it again, so what follows comes that much later. Notes are timed on the first time
        # through; the map lists the bars again for the cursor
        if i in repeats:
            s0, times, e0 = repeats[i]
            for _ in range(times - 1):
                for j in range(s0, e0 + 1):
                    played.append((j, t)); t += piece(j, xbars[j]['quarters'])
    total = t

    if a.offset is None and (a.instrument_part not in attacks or 'I' not in stems):
        # unaccompanied: each voice against its own stem
        fits = [(flux(at(stems[STEM_OF[n]])), np.array([secs(i, q) for i, q in attacks[n] if q == int(q)])) for n in VOICES]
        def best_all(fs, lo, hi, step=0.005):
            os_ = np.arange(lo, hi, step)
            def score(o):
                v = 0.0
                for d, ss in fs:
                    idx = ((ss + o) * SR / HOP).astype(int)
                    idx = idx[(idx >= 0) & (idx < len(d) - 1)]
                    v += (d[idx] + d[idx + 1]).sum()
                return v
            return float(max(os_, key=score))
        offset = best_all(fits, 0.0, 30.0)
        print(f'offset from the voices\' on-beat attacks on their own stems: {offset:.3f} s')
        sections = [(np.array_split(ss, 8)) for _, ss in fits]
        print('  drift by section, s:', [round(best_all([(fits[v][0], sections[v][k]) for v in range(len(fits))], offset - 0.15, offset + 0.15) - offset, 3) for k in range(8)])
    elif a.offset is None:
        d = flux(at(stems['I']))
        on = [(i, q) for i, q in attacks[a.instrument_part] if q == int(q)]
        ss = np.array([secs(i, q) for i, q in on])
        offset = best_offset(d, ss, 0.0, 20.0)
        # refine, and report the drift over the song, on each stem against its own part
        print(f'offset from {a.instrument_part} on {stems["I"]}: {offset:.3f} s')
        spans = np.array_split(np.arange(len(ss)), 8)
        print('  drift by section, s:', [round(best_offset(d, ss[g], offset - 0.15, offset + 0.15) - offset, 3) for g in spans if len(g) > 3])
    else:
        offset = a.offset

    # a rit: the song's own beat from then on is measured from the stems, and score seconds are bent to fit
    plain_secs = secs
    anchors = []
    rits = rit_bars(at(a.xml))
    if a.warp:
        # where the stems' tempo strays from the written one: an offset for each bar, chosen together so that the voices'
        # attacks land on their stems' attacks and the offset changes little from bar to bar (a hold can jump it; a
        # repeated figure, which fits as well a beat either way, can't), and followed between bar starts
        inst = (attacks[a.instrument_part], at(stems['I'])) if a.instrument_part in attacks and 'I' in stems else None
        anchors = fit_warp(at(a.xml), xbars, plain_secs, total, [(n_, at(stems[STEM_OF[n_]])) for n_ in VOICES], offset,
                           a.warp_beat, at(a.guide) if a.guide else None, a.pin, inst=inst)
        if a.anchor:
            # measured by hand, for a slowing the fit can't follow: bar numbers as printed, beats counted from 1
            nums, mts = xml_numbers(at(a.xml)), xml_meters(at(a.xml))
            hand = []
            for t_ in a.anchor:
                pos_, sec_ = t_.split('='); bar_, beat_ = (pos_.split('.') + ['1'])[:2]
                bi = nums.index(int(bar_))
                hand.append((plain_secs(bi, (int(beat_) - 1) * beat_len(mts[bi])), float(sec_)))
            hand.sort()
            kept = [p_ for p_ in anchors if p_[0] < hand[0][0]]
            anchors = kept + hand + [(total + 30, total + 30 + hand[-1][1] - hand[-1][0])]
    elif rits:
        vn, swing0 = read_voice_notes(at(a.xml), VOICES)
        first = rits[0]
        s0 = plain_secs(first, F(0))
        ev = []
        for name, ns in vn.items():
            if STEM_OF[name] not in stems: continue
            e = np.log(fine_envelope(at(stems[STEM_OF[name]])) + 1e-3)
            fl = np.convolve(np.maximum(np.diff(e, prepend=e[0]), 0), np.ones(4), 'same')
            for n in ns:
                if n['start'][0] >= first: ev.append((plain_secs(n['start'][0], swung(n['start'][1], swing0)) - s0, fl))
        sound_end = max(np.nonzero(fine_envelope(at(f)) > 1e-3)[0][-1] for f in stems.values()) * FINE / SR
        c, a_, p_ = fit_rit(ev, offset + s0, total - s0, sound_end)
        print(f'sound ends at {sound_end:.2f} s')
        print(f'rit from bar {first + 1}: beat {c:.2f} times longer, then up to {a_:.1f} more by the end (power {p_}): about {tempo / c:.0f} bpm at the start')
        u_ = np.linspace(0, total - s0, 801)
        t_ = np.concatenate([[0], np.cumsum((c + a_ * (u_[:-1] / (total - s0)) ** p_) * (u_[1] - u_[0]))])
        anchors = [(float(s0 + x), float(s0 + y + offset)) for x, y in zip(u_, t_)]
    def warp(s_):
        if not anchors or s_ <= anchors[0][0]: return s_
        return float(np.interp(s_, [x for x, _ in anchors], [y for _, y in anchors])) - offset
    def secs(bar_i, q):
        return warp(plain_secs(bar_i, q))

    bars, layout = [], []
    systems = {}
    meters = xml_meters(at(a.xml))
    numbers = xml_numbers(at(a.xml))
    for bi_, (b, x) in enumerate(zip(vs.bars if a.staff else r.bars, xbars)):
        if a.staff:
            b['meter'] = meters[bi_]
            known = {q: v for q, v in b['known'].items() if q < x['quarters']}
        else:
            items = [it for sb in b['staves'] for it in sb['items'] if not it.get('whole')]
            known = {}
            for it in items:
                known.setdefault(it['on'], []).append(it['x'])
            known = {q: float(np.median(v)) for q, v in known.items() if q < x['quarters']}
        bl = beat_len(b['meter'])
        nb = max(1, int(x['quarters'] / bl))
        qs = sorted(known)
        # beat 1 at its notes if any; else at the bar's first head or rest on any staff (the piano's too), if that comes
        # before the voices' first note; else just inside the barline, or past the clef and key in a system's first bar
        fx = b.get('first_x')
        x0 = known.get(F(0), fx if fx is not None and (not qs or fx < known[qs[0]] - 1) else
                       (b['xa'] + 8 if not b['first_in_system'] else (known[qs[0]] if qs else b['xa'] + 40)))
        px = [F(0)] + [q for q in qs if q > 0] + [x['quarters']]
        py = [x0] + [known[q] for q in qs if q > 0] + [b['xb']]
        px, py = rising(px, py)
        beatx = [float(np.interp(float(i * bl), [float(p) for p in px], py)) for i in range(nb)]
        if a.staff: systems[(b['page'], b['sys'])] = vs.systems[(b['page'], b['sys'])]
        else:
            pm = r.pms[b['page']]; sy = pm.systems[b['sys']]
            systems[(b['page'], b['sys'])] = dict(page=b['page'], sys=b['sys'], top=sy[0]['top'], bottom=sy[-1]['bot'])
        layout.append(dict(num=numbers[bi_], page=b['page'], sys=b['sys'], xa=b['xa'], xb=b['xb'], letter=x['letter'],
                           beat_x=[round(v, 2) for v in beatx], bl=bl, nb=nb))
    # each bar every time it's played, so the cursor follows a repeat; a letter marks only its first time
    seen = set()
    for bi_, p0 in played:
        L_ = dict(layout[bi_]); bl, nb = L_.pop('bl'), L_.pop('nb')
        if bi_ in seen: L_['letter'] = None
        seen.add(bi_)
        bars.append(dict(L_, beat_t=[round(offset + warp(p0 + piece(bi_, k * bl)), 4) for k in range(nb)],
                         end_t=round(offset + warp(p0 + piece(bi_, xbars[bi_]['quarters'])), 4)))
    # each voice's notes, for marking one to mute or transpose: where its heads are, and when its stem sings it
    vnotes, swing = read_voice_notes(at(a.xml), VOICES)
    notes = []
    for name in VOICES:
        k = xml_parts.index(name)     # its staff: one per part, top to bottom, as on the page
        if name not in vnotes: continue
        env = fine_envelope(at(stems[STEM_OF[name]]))
        for n in vnotes[name]:
            bi, q = n['start']; ei, qe = n['end']
            n['start_t'] = offset + secs(bi, swung(q, swing)); n['end_t'] = offset + secs(ei, swung(qe, swing)) if qe < xbars[ei]['quarters'] else offset + secs(ei, qe)
        moved = snap_notes(vnotes[name], env)
        lost = 0
        for n in vnotes[name]:
            heads = []
            for hb, hq in n['heads']:
                if a.staff:
                    h = vs.head(name, hb, hq, n['midi'])
                    if h is None: lost += 1
                    else: heads.append(h)
                    continue
                b = r.bars[hb]
                it = next((it for it in b['staves'][k]['items'] if it['kind'] == 'chord' and it.get('on') == hq), None)
                if it is None: lost += 1; continue
                h = it['heads'][0]
                heads.append(dict(page=b['page'], x=round(h.cx, 2), y=round(h.y, 2)))
            if not heads: continue
            bi, q = n['start']
            key = STEM_OF[name]
            nid = f"{key}.{bi + 1}.{float(q):g}" if key == 'A2' else f"{key}{bi + 1}.{float(q):g}" if key in LETTERS else f"{key} {numbers[bi]}.{float(q):g}"
            notes.append(dict(id=nid, part=key, bar=numbers[bi], beat=round(float(q / beat_len((vs.bars if a.staff else r.bars)[bi]['meter'])) + 1, 2),
                              midi=n['midi'], word=n['word'], start=round(n['start_t'], 4), end=round(n['end_t'], 4), heads=heads))
        print(f"{name}: {len(vnotes[name])} notes, {moved} starts snapped to the stem, {lost} heads not found")
    # the dark mode's copy of the score, with notes and everything else in their own colors
    stem, ext = os.path.splitext(a.score)
    score_dark = f'{stem} (dark){ext}'
    counts = dark_score.make(at(a.score), at(score_dark))
    print('dark copy:', counts)
    if not counts['note glyphs']:
        # heads drawn as paths, which it can't tell from words and dynamics: the app's page filter does Dark instead
        os.remove(at(score_dark)); score_dark = None
        print('  no note glyphs found: no dark copy')
    trims = {k: float(v) for k, v in (t_.split('=', 1) for t_ in a.trim)}
    m = dict(voices=[dict(key=k, name=n, **({'trim': trims[n]} if n in trims else {})) for k, n in voices], notes=notes, score=a.score, **({'score_dark': score_dark} if score_dark else {}), stems=stems, offset=round(offset, 4), page_height=page_h, pages=npages,
             tempo=float(next((t_ for b in xbars for _, t_ in b['tempos']), 120.0)), music_end=bars[-1]['end_t'],
             systems=list(systems.values()), bars=bars)
    with open(at('player map.json'), 'w') as f:
        json.dump(m, f, indent=0)
    print('wrote player map.json:', len(bars), 'bars, letters', [b['letter'] for b in bars if b['letter']], 'tempo', m['tempo'], 'music ends', m['music_end'])


if __name__ == '__main__':
    main()
