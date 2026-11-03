#!/usr/bin/env python3
"""Write the beat map the rehearsal player needs for a song folder (see README.md here).

    python3 player/make_map.py "song folder" --reader-pdf "... Full score copy.pdf" --score "... (lesson marks).pdf"
        --xml "....musicxml" --stems S=...wav A=...wav T=...wav B=...wav I=...wav [--nstaves 6] [--offset 1.02]

Bars, beats and their x positions come from the vector PDF through dorico_reader.py; times come from the MusicXML's
tempo marks. Without --offset, the time of bar 1 is measured: the fit of the on-beat piano attacks to the instrumental
stem. Swung offbeats are left out of that fit, and it reports how far the stems drift from the score bar by bar.
A rit mark in the MusicXML (rit, riten, rall) bends the times from its bar to the end of the song, fitted to the stems.
Writes "player map.json" in the song folder, paths relative to it.
"""
import argparse, json, os, re, subprocess, sys, xml.etree.ElementTree as ET
from fractions import Fraction as F
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import dorico_reader as dr

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
            for e in m:
                if e.tag == 'attributes' and e.find('divisions') is not None: div = int(e.findtext('divisions'))
                elif e.tag == 'backup': pos -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward': pos += F(int(e.findtext('duration')), div)
                elif e.tag == 'note':
                    if e.find('chord') is not None: continue
                    d = F(int(e.findtext('duration') or 0), div)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder'); ap.add_argument('--reader-pdf', required=True); ap.add_argument('--score', required=True)
    ap.add_argument('--xml', required=True); ap.add_argument('--stems', nargs='+', required=True)
    ap.add_argument('--nstaves', type=int, default=6); ap.add_argument('--offset', type=float)
    ap.add_argument('--instrument-part', default='Piano')
    a = ap.parse_args()
    at = lambda f: os.path.join(a.folder, f)
    stems = dict(s.split('=', 1) for s in a.stems)

    xbars, attacks = read_xml(at(a.xml))
    import pdfplumber
    with pdfplumber.open(at(a.reader_pdf)) as p: npages = len(p.pages)
    r = dr.Reader(at(a.reader_pdf), range(npages), nstaves=a.nstaves).read().voices()
    assert len(r.bars) == len(xbars), (len(r.bars), len(xbars))

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
    for i, b in enumerate(xbars):
        starts.append((t, tempo))
        t += piece(i, b['quarters'])
        if b['tempos']: tempo = b['tempos'][-1][1]
    total = t

    if a.offset is None:
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
    if rits:
        vn, swing0 = read_voice_notes(at(a.xml), ['Soprano', 'Alto', 'Tenor', 'Bass'])
        first = rits[0]
        s0 = plain_secs(first, F(0))
        ev = []
        for name, ns in vn.items():
            if name[0] not in stems: continue
            e = np.log(fine_envelope(at(stems[name[0]])) + 1e-3)
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
    def secs(bar_i, q):
        s_ = plain_secs(bar_i, q)
        if not anchors or s_ <= anchors[0][0]: return s_
        return float(np.interp(s_, [x for x, _ in anchors], [y for _, y in anchors])) - offset

    bars = []
    systems = {}
    for b, x in zip(r.bars, xbars):
        items = [it for sb in b['staves'] for it in sb['items'] if not it.get('whole')]
        bl = beat_len(b['meter'])
        nb = max(1, int(x['quarters'] / bl))
        known = {}
        for it in items:
            known.setdefault(it['on'], []).append(it['x'])
        known = {q: float(np.median(v)) for q, v in known.items() if q < x['quarters']}
        qs = sorted(known)
        # beat 1 at its notes if any (a system's first bar opens with clef and key); else just inside the barline
        x0 = known.get(F(0), (b['xa'] + 8 if not b['first_in_system'] else (known[qs[0]] if qs else b['xa'] + 40)))
        px = [F(0)] + [q for q in qs if q > 0] + [x['quarters']]
        py = [x0] + [known[q] for q in qs if q > 0] + [b['xb']]
        beatx = [float(np.interp(float(i * bl), [float(p) for p in px], py)) for i in range(nb)]
        pm = r.pms[b['page']]; sy = pm.systems[b['sys']]
        systems[(b['page'], b['sys'])] = dict(page=b['page'], sys=b['sys'], top=sy[0]['top'], bottom=sy[-1]['bot'])
        i = b['num'] - 1
        bars.append(dict(num=b['num'], page=b['page'], sys=b['sys'], xa=b['xa'], xb=b['xb'], letter=x['letter'],
                         beat_x=[round(v, 2) for v in beatx],
                         beat_t=[round(offset + secs(i, k * bl), 4) for k in range(nb)],
                         end_t=round(offset + secs(i, x['quarters']), 4)))
    # each voice's notes, for marking one to mute or transpose: where its heads are, and when its stem sings it
    parts = ['Soprano', 'Alto', 'Tenor', 'Bass']
    vnotes, swing = read_voice_notes(at(a.xml), parts)
    notes = []
    for k, name in enumerate(parts):
        if name not in vnotes or name[0] not in stems: continue
        env = fine_envelope(at(stems[name[0]]))
        for n in vnotes[name]:
            bi, q = n['start']; ei, qe = n['end']
            n['start_t'] = offset + secs(bi, swung(q, swing)); n['end_t'] = offset + secs(ei, swung(qe, swing)) if qe < xbars[ei]['quarters'] else offset + secs(ei, qe)
        moved = snap_notes(vnotes[name], env)
        lost = 0
        for n in vnotes[name]:
            heads = []
            for hb, hq in n['heads']:
                b = r.bars[hb]
                it = next((it for it in b['staves'][k]['items'] if it['kind'] == 'chord' and it.get('on') == hq), None)
                if it is None: lost += 1; continue
                h = it['heads'][0]
                heads.append(dict(page=b['page'], x=round(h.cx, 2), y=round(h.y, 2)))
            if not heads: continue
            bi, q = n['start']
            notes.append(dict(id=f"{name[0]}{bi + 1}.{float(q):g}", part=name[0], bar=bi + 1, beat=round(float(q / beat_len(r.bars[bi]['meter'])) + 1, 2),
                              midi=n['midi'], word=n['word'], start=round(n['start_t'], 4), end=round(n['end_t'], 4), heads=heads))
        print(f"{name}: {len(vnotes[name])} notes, {moved} starts snapped to the stem, {lost} heads not found")
    m = dict(notes=notes, score=a.score, stems=stems, offset=round(offset, 4), page_height=float(r.pms[0].H), pages=npages,
             tempo=float(next((t_ for b in xbars for _, t_ in b['tempos']), 120.0)), music_end=round(offset + secs(len(xbars) - 1, xbars[-1]['quarters']), 4),
             systems=list(systems.values()), bars=bars)
    with open(at('player map.json'), 'w') as f:
        json.dump(m, f, indent=0)
    print('wrote player map.json:', len(bars), 'bars, letters', [b['letter'] for b in bars if b['letter']], 'tempo', m['tempo'], 'music ends', m['music_end'])


if __name__ == '__main__':
    main()
