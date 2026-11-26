"""What the score says happens at each played beat (DESIGN.md Step 2, the score side), on the player map's clock.

    from score import beat_table
    bt = beat_table(song_cfg)

The player map gives the played bars in order (repeats expanded) and every beat's time; its notes give the voices.
The full MusicXML gives the piano and the clap staff (read here by measure number and placed in the bar by its
fraction of the measure), fermatas, tempo words and meter changes.

Returns a dict of arrays over played beats k = 0..K-1:
  t0, t1        human-sung (player-map clock) start and end of the beat
  bar_i, beat   index into map['bars'] and beat number within the bar (1-based)
  num           the bar's printed number
  att_v, att_p, att_c   whether the voices / piano / claps attack at the beat's start (within 6% of a beat)
  act_v         share of the beat during which some voice sounds
  loose         tempo-prior looseness 0..1 and 'why' (a list of reasons per beat)
  entry         a voice entry after at least a bar with no voice sounding (a landmark)
and 'notes_v', 'notes_p': lists of (start, end, midi) on the player-map clock, for the chroma templates.
"""
import json, re, os
import numpy as np
import xml.etree.ElementTree as ET

STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
# Looseness of the counting, 0..1 (sigma = 0.05 + 0.45 x looseness, align.py). Two kinds, as a musician counts:
# a JUMP (fermata, the end of a hold, an entry after rests, a new tempo) lets the next beat come at almost any time,
# 0.6-1.0; a DRIFT (rall., stringendo, a meter change, the track maker pushing or pulling) changes the tempo smoothly and the
# counting goes on, DRIFT = 0.15 (sigma 0.12 per beat).
DRIFT = 0.15
TEMPO_WORDS = re.compile(r'rall|rit|stringendo|accel|a tempo|tempo|slow|broad|maestoso|fermata|suddenly|allarg|molto|'
                         r'ballad|groove|swing|faster|freely|colla|rubato|ad lib', re.I)


def read_xml(path):
    """{part name: {measure number: [(frac0, frac1, midi or None, fermata), ...]}}, measure lengths, words, meters."""
    r = ET.parse(path).getroot()
    names = {sp.get('id'): sp.findtext('part-name') for sp in r.iter('score-part')}
    parts, mlen, words, meters = {}, {}, {}, {}
    for p in r.findall('part'):
        name = names[p.get('id')]
        div, beats, btype = 1, 4, 4
        out = {}
        for m in p.findall('measure'):
            num = m.get('number')
            a = m.find('attributes')
            if a is not None:
                if a.findtext('divisions'): div = int(a.findtext('divisions'))
                if a.find('time') is not None:
                    beats, btype = int(a.find('time').findtext('beats')), int(a.find('time').findtext('beat-type'))
                    meters[num] = (beats, btype)
            L = beats * 4 / btype * div             # measure length in divisions
            mlen[num] = (beats, btype)
            pos, last_start, ev = 0, 0, []
            for e in m:
                if e.tag == 'note':
                    dur = int(e.findtext('duration') or 0)
                    chord = e.find('chord') is not None
                    st = last_start if chord else pos
                    if e.find('grace') is not None:
                        continue
                    midi = None
                    pe = e.find('pitch')
                    if pe is not None:
                        midi = 12 * (int(pe.findtext('octave')) + 1) + STEP[pe.findtext('step')] + int(float(pe.findtext('alter') or 0))
                    tie_stop = any(t.get('type') == 'stop' for t in e.findall('tie'))
                    ferm = e.find('notations/fermata') is not None
                    if e.find('rest') is None:
                        ev.append((st / L, (st + dur) / L, midi, ferm, tie_stop))
                    elif ferm:
                        ev.append((st / L, (st + dur) / L, None, True, True))
                    if not chord:
                        last_start = pos; pos += dur
                elif e.tag == 'backup':
                    pos -= int(e.findtext('duration'))
                elif e.tag == 'forward':
                    pos += int(e.findtext('duration'))
                elif e.tag == 'direction':
                    for w in e.iter('words'):
                        if w.text and w.text.strip():
                            words.setdefault(num, []).append(w.text.strip())
                    if e.find('.//metronome') is not None:
                        words.setdefault(num, []).append('(metronome)')
                elif e.tag == 'barline':
                    if e.find('fermata') is not None:
                        ev.append((1.0, 1.0, None, True, True))
            out[num] = ev
        parts[name] = out
    return parts, mlen, words, meters


def bar_time(bar, frac):
    """Time at a fraction of a played bar, through its beat times (beats equally long in the bar's own measure)."""
    tt = list(bar['beat_t']) + [bar['end_t']]
    x = frac * (len(tt) - 1)
    return float(np.interp(x, np.arange(len(tt)), tt))


def beat_table(cfg):
    d = cfg['song_dir']
    mp = json.load(open(os.path.join(d, 'player map.json')))
    parts, mlen, words, meters = read_xml(os.path.join(d, cfg['musicxml']))
    bars = mp['bars']
    # An input property the design relies on: every beat has positive length. song2's map has beats that
    # run backwards or nearly vanish (bar 170's beat 1 is -0.061 s; 93, 121, 162; 165's beat 2 is 0.034 s). A beat under
    # 30% of its bar's mean beat is implausible: such a bar's beats are re-spaced evenly between
    # its start and end, and listed in 'repaired'.
    repaired = []
    for b in bars:
        tt = list(b['beat_t']) + [b['end_t']]
        if any(tt[i + 1] - tt[i] < 0.3 * (tt[-1] - tt[0]) / max(1, len(tt) - 1) for i in range(len(tt) - 1)):
            if tt[-1] > tt[0]:
                n = len(b['beat_t'])
                b['beat_t'] = [tt[0] + (tt[-1] - tt[0]) * i / n for i in range(n)]
                repaired.append(b['num'])
    vnames = {v['key'] for v in mp['voices']}
    # voices from the player map; piano and claps from the MusicXML
    notes_v = [(n['start'], n['end'], n['midi']) for n in mp['notes'] if n['part'] in vnames]
    piano = next((p for n, p in parts.items() if 'piano' in n.lower()), {})
    clap = next((p for n, p in parts.items() if 'clap' in n.lower()), {})
    voice_parts = [p for n, p in parts.items() if 'piano' not in n.lower() and 'clap' not in n.lower()]
    notes_p, att_p_t, att_c_t, ferm_t = [], [], [], []
    for bi, b in enumerate(bars):
        num = str(b['num'])
        for (f0, f1, midi, ferm, tie_stop) in piano.get(num, []):
            t0, t1 = bar_time(b, f0), bar_time(b, f1)
            if midi is not None:
                notes_p.append((t0, t1, midi))
                if not tie_stop: att_p_t.append(t0)
            if ferm: ferm_t.append((t0, t1))
        for (f0, f1, midi, ferm, tie_stop) in clap.get(num, []):
            if not tie_stop: att_c_t.append(bar_time(b, f0))
        for vp in voice_parts:
            for (f0, f1, midi, ferm, tie_stop) in vp.get(num, []):
                if ferm: ferm_t.append((bar_time(b, f0), bar_time(b, f1)))
    att_v_t = sorted(n['start'] for n in mp['notes'] if n['part'] in vnames)
    att_p_t, att_c_t = np.array(sorted(att_p_t)), np.array(sorted(att_c_t))
    att_v_t = np.array(att_v_t)

    # played beats
    rows = []
    for bi, b in enumerate(bars):
        tt = list(b['beat_t']) + [b['end_t']]
        for j in range(len(b['beat_t'])):
            rows.append((tt[j], tt[j + 1], bi, j + 1, b['num']))
    t0 = np.array([r[0] for r in rows]); t1 = np.array([r[1] for r in rows])
    K = len(rows)
    blen = t1 - t0
    tol = 0.06 * blen

    def near(att):
        if len(att) == 0: return np.zeros(K, bool)
        i = np.searchsorted(att, t0)
        dl = np.abs(att[np.clip(i - 1, 0, len(att) - 1)] - t0); dr = np.abs(att[np.clip(i, 0, len(att) - 1)] - t0)
        return np.minimum(dl, dr) <= tol
    att_v, att_p, att_c = near(att_v_t), near(att_p_t), near(att_c_t)

    # share of each beat with a voice sounding
    act_v = np.zeros(K)
    nv = np.array(notes_v) if notes_v else np.zeros((0, 3))
    for k in range(K):
        if len(nv):
            ov = np.clip(np.minimum(nv[:, 1], t1[k]) - np.maximum(nv[:, 0], t0[k]), 0, None)
            # union approximated by the largest single overlap plus others capped at the beat
            act_v[k] = min(1.0, ov.max() / blen[k]) if ov.max() > 0 else 0.0

    # looseness of the tempo prior, with reasons
    loose = np.zeros(K); why = [[] for _ in range(K)]

    def mark(k, v, r):
        if 0 <= k < K:
            if v > loose[k]: loose[k] = v
            if r not in why[k]: why[k].append(r)
    for (f0, f1) in ferm_t:
        for k in np.where((t1 > f0 - 1e-6) & (t0 < max(f1, f0 + 1e-3) + 1e-6))[0]:
            mark(k, 1.0, 'fermata'); mark(k + 1, 1.0, 'after fermata')
    bar_first = {}
    for k, r in enumerate(rows):
        bar_first.setdefault(r[2], k)
    nbars = len(bars)
    for bi, b in enumerate(bars):
        num = str(b['num']); k0 = bar_first[bi]
        nb = len(b['beat_t'])
        ws = [w for w in words.get(num, []) if TEMPO_WORDS.search(w) or w == '(metronome)']
        if ws:
            # the word's bar and the next 3 bars: a change of tempo may take that long to settle. A gradual change
            # (rall., rit., stringendo, accel.) lasts until the next tempo word, at most 12 bars.
            span = 4
            if re.search(r'rall|rit|stringendo|accel|slow', ' '.join(ws), re.I):
                span = 12
                for bj in range(bi + 1, min(nbars, bi + 12)):
                    if any(TEMPO_WORDS.search(w) for w in words.get(str(bars[bj]['num']), [])):
                        span = max(4, bj - bi); break
            for bj in range(bi, min(nbars, bi + span)):
                for k in range(bar_first[bj], bar_first[bj] + len(bars[bj]['beat_t'])):
                    mark(k, DRIFT, 'tempo word: ' + ws[0][:30])
            # a gradual change starts smoothly; a new tempo (Maestoso, say) may start at once
            gradual = re.search(r'rall|rit|stringendo|accel|slow', ' '.join(ws), re.I)
            mark(k0, DRIFT if gradual else 0.6, 'tempo word: ' + ws[0][:30])
        if bi > 0 and (len(bars[bi - 1]['beat_t']) != nb or num in meters):
            mark(k0, 0.3, 'meter change'); mark(k0 + 1, DRIFT, 'meter change')
    # Where a room takes liberties that the page doesn't mark (added 2026-11-25 after ratio_check.py on song2's
    # tap map showed unmarked holds at 70-71, 80, 90, 120-122; so song2's benchmark is
    # informed by these rules, song1's is not):
    # (a) the human-sung set's own bar runs more than 15% longer or shorter per beat than its neighbours': the singer held or pushed.
    bl = np.array([(b['end_t'] - b['beat_t'][0]) / len(b['beat_t']) for b in bars])
    for bi in range(nbars):
        nb_ = [j for j in range(max(0, bi - 4), min(nbars, bi + 5)) if j != bi]
        med = np.median(bl[nb_]) if nb_ else bl[bi]
        if abs(np.log(bl[bi] / med)) > np.log(1.15):
            for k in range(bar_first[bi], bar_first[bi] + len(bars[bi]['beat_t'])):
                mark(k, DRIFT, "the human-sung set's own tempo changes here")
            if bi + 1 < nbars: mark(bar_first[bi + 1], DRIFT, "after the human-sung set's tempo change")
    # (b) a sung note of four beats or more: its end and the next beat (how long a hold lasts is the room's choice)
    for (a, b_, m) in notes_v:
        k0 = int(np.searchsorted(t0, a - 1e-6)); k1 = int(np.searchsorted(t0, b_ - 1e-6))
        if k1 - k0 >= 4:
            mark(k1 - 1, 0.3, 'end of a held note'); mark(k1, 0.6, 'end of a held note')
    # (c) a bar where no voice starts a note (piano alone, a run, a hold over chords)
    for bi in range(nbars):
        ks = range(bar_first[bi], bar_first[bi] + len(bars[bi]['beat_t']))
        b0, b1 = bars[bi]['beat_t'][0], bars[bi]['end_t']
        if not np.any((att_v_t >= b0 - 0.02) & (att_v_t < b1 - 0.02)):
            for k in ks: mark(k, DRIFT, 'no voice attack in the bar')
            if bi + 1 < nbars: mark(bar_first[bi + 1], 0.4, 'after a bar with no voice attack')
    # entries after at least a bar with no voice: landmarks, and the tempo may have drifted in the gap
    entry = np.zeros(K, bool)
    silent = 0.0
    for k in range(K):
        if act_v[k] < 0.05:
            silent += blen[k]
        else:
            bl = np.median(blen[max(0, k - 8):k + 8]) * 4
            if att_v[k] and silent >= 0.9 * bl:
                entry[k] = True; mark(k, 0.8, 'entry after rest'); mark(k + 1, DRIFT, 'entry after rest')
            silent = 0.0
    # a stretch with no attack in any stream for a bar or more: nothing fixes the tempo there
    gap = 0.0
    for k in range(K):
        if not (att_v[k] or att_p[k] or att_c[k]):
            gap += blen[k]
        else:
            if gap >= 0.9 * np.median(blen[max(0, k - 8):k + 8]) * 4:
                mark(k, 0.8, 'after a held stretch')
            gap = 0.0
    return dict(t0=t0, t1=t1, bar_i=np.array([r[2] for r in rows]), beat=np.array([r[3] for r in rows]),
                num=[r[4] for r in rows], att_v=att_v, att_p=att_p, att_c=att_c, act_v=act_v, loose=loose,
                why=why, entry=entry, repaired=repaired, notes_v=notes_v, notes_p=notes_p, bars=bars, words=words, mp=mp)


if __name__ == '__main__':
    import sys
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), 'songs.json')))[sys.argv[1]]
    bt = beat_table(cfg)
    K = len(bt['t0'])
    print(f"{K} beats, {len(bt['bars'])} played bars; voice attacks {bt['att_v'].sum()}, piano {bt['att_p'].sum()}, "
          f"claps {bt['att_c'].sum()}; entries {bt['entry'].sum()}; loose beats {np.sum(bt['loose'] > 0)}")
    print('bars whose beats ran backwards in the player map, re-spaced evenly:', bt['repaired'])
    L = bt['t1'] - bt['t0']; print('shortest beat now %.3f s' % L.min())
    print('piano notes', len(bt['notes_p']), 'voice notes', len(bt['notes_v']))
    seen = set()
    for k in range(K):
        if bt['why'][k]:
            key = (bt['num'][k], tuple(bt['why'][k]))
            if bt['beat'][k] == 1 or bt['loose'][k] >= 0.8:
                print(f"  bar {bt['num'][k]} beat {bt['beat'][k]}: {bt['loose'][k]:.1f} {', '.join(bt['why'][k])}")
