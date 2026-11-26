"""Where the score's barlines fall in a recording at a steady tempo.

    python3 -m voiceshift.bargrid SCORE.musicxml ACCOMP.mp3 --part Piano [--swing 0.61] [--bpm 120]

Model: quarter q of the score sounds at offset + q * beat (q unrolled from bar 1, no repeats), with
a point exactly halfway through a quarter moved to --swing of the beat.

How the offset is found, and why this way: the beat period comes from a beat tracker with a
straight-line fit (or --bpm).  The offset is NOT taken from matching onsets to the score's notes:
a steady accompaniment matches itself a beat away just as well (on a swing piano part the onset fit
locked on 0.65 s early, and the per-beat score landscape had equal peaks every 0.5 s).  The rests
decide it: every stretch of 1.2 s or more where the accompaniment part plays nothing is a gap in the
audio's onsets of the same length, and only one offset lines the gaps up.  The script lists both,
finds the offset that matches the most gaps (within 60 ms), then refines it on the onsets at the
start of each gap, and prints each check.  It also prints how loud the voice stems' first entrances
are against that grid when --voices are given, as a cross-check.

Also prints --swing measured: where offbeat onsets fall within the beat (straight 0.500, triplet
0.667).  An SSA practice track measured 0.61.
"""
import argparse
from fractions import Fraction as Fr

import numpy as np


def score_events(path, part_name):
    from lxml import etree
    root = etree.parse(path).getroot()
    pid = None
    for sp in root.find('part-list').findall('score-part'):
        if sp.findtext('part-name', '').strip().lower() == part_name.lower():
            pid = sp.get('id')
    if pid is None:
        raise SystemExit(f'no part named {part_name!r}')
    part = root.find(f"part[@id='{pid}']")
    div, pos, onsets, ends = 1, Fr(0), [], []
    starts = []
    for m in part.findall('measure'):
        starts.append(pos)
        t, mx = pos, pos
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= Fr(int(e.findtext('duration')), div)
            elif e.tag == 'forward':
                t += Fr(int(e.findtext('duration')), div)
            elif e.tag == 'note':
                d = Fr(int(e.findtext('duration') or 0), div)
                if e.find('chord') is not None:
                    continue
                if e.find('rest') is None:
                    if e.find("tie[@type='stop']") is None:
                        onsets.append(t)
                    ends.append(t + d)
                t += d
            mx = max(mx, t)
        pos = mx
    return sorted(set(onsets)), sorted(ends), starts


def swing_q(q, swing):
    q = Fr(q)
    return float(q) + (swing - 0.5 if swing and q - (q // 1) == Fr(1, 2) else 0.0)


def rest_gaps(onsets, ends, min_q):
    """Quarters (start, length) where the part sounds nothing new for min_q quarters or more."""
    gaps = []
    on = sorted(onsets)
    for a, b in zip(on, on[1:]):
        if b - a >= min_q:
            gaps.append((a, b - a))
    return gaps


def main():
    import librosa
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score'); ap.add_argument('audio')
    ap.add_argument('--part', default='Piano')
    ap.add_argument('--swing', type=float, default=0.0)
    ap.add_argument('--bpm', type=float)
    a = ap.parse_args()
    sr = 22050
    y, _ = librosa.load(a.audio, sr=sr, mono=True)
    if a.bpm:
        beat = 60 / a.bpm
    else:
        env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
        _, bt = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=256, tightness=400, units='time')
        A = np.vstack([np.arange(len(bt)), np.ones(len(bt))]).T
        beat = float(np.linalg.lstsq(A, bt, rcond=None)[0][0])
    print(f'beat {beat:.5f} s ({60 / beat:.2f} bpm)')
    on = librosa.onset.onset_detect(y=y, sr=sr, units='time', hop_length=128)
    agaps = [(on[i], on[i + 1] - on[i]) for i in range(len(on) - 1) if on[i + 1] - on[i] > 1.2]
    onsets, ends, starts = score_events(a.score, a.part)
    sg = [(q, L) for q, L in rest_gaps(onsets, ends, 0) if float(L) * beat > 1.2]
    sgs = [(swing_q(q, a.swing), swing_q(q + L, a.swing) - swing_q(q, a.swing)) for q, L in sg]
    best = None
    for off in np.arange(-5, 10, 0.005):
        hits = sum(1 for q, L in sgs if any(abs(s - (off + q * beat)) < 0.06 and abs(l - L * beat) < 0.15
                                            for s, l in agaps))
        if best is None or hits > best[0]:
            best = (hits, off)
    hits, off = best
    # refine on the onset that starts each matched gap
    d = []
    for q, L in sgs:
        t = off + q * beat
        near = on[np.argmin(abs(on - t))]
        if abs(near - t) < 0.06:
            d.append(near - t)
    off += float(np.median(d)) if d else 0.0
    bar_of = lambda q: int(np.searchsorted([float(s) for s in starts], q, side='right'))
    print(f'bar 1 at {off + float(starts[0]) * beat:.3f} s; {hits} of {len(sgs)} accompaniment rests line up with '
          f'gaps in the audio')
    for q, L in sgs:
        t = off + q * beat
        near = on[np.argmin(abs(on - t))]
        print(f'   rest from bar {bar_of(q)}: score {t:7.2f} s for {L * beat:.2f} s; nearest onset {near:7.2f} '
              f'({1000 * (near - t):+.0f} ms)')
    beat_pos = ((on - off) / beat) % 1
    offb = beat_pos[(beat_pos > 0.45) & (beat_pos < 0.8)]
    print(f'offbeat onsets sit at {np.median(offb):.3f} of the beat (straight 0.500, triplet swing 0.667) over '
          f'{len(offb)} onsets: use --swing {np.median(offb):.2f}')
    print(f'bar n starts at {off:.3f} + {4 * beat:.4f} * (n - 1) s in 4/4')


if __name__ == '__main__':
    main()
