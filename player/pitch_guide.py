#!/usr/bin/env python3
"""Times a freely sung song by its pitches, and checks a map against them.

    pitch_guide.py FOLDER XML guide OUT [--from BAR]
        writes "bar.beat=seconds" for every beat, for make_map.py's --guide: the written notes of every part are matched to
        the pitch sung on its stem (any octave), by dynamic time warping at 20 frames a second. Bar starts the guide
        gives no times before (a stretch it gets wrong where the attack fit does well). A repeat is followed as sung; the
        guide gives a bar's first time through.
    pitch_guide.py FOLDER XML check [MAP]
        for each bar, the share of the map's sung notes whose stem holds the written pitch (any octave) for most of the
        note; a map in the right place scores over 0.9 overall, a beat or a bar out far less

The stems are the ones player map.json names, so make the map once without a guide first. Attack fits alone can lock a beat
or several bars out on slow legato singing and still look right to an attack check; the pitch can't be fooled that way.
Sung pitch (librosa's pyin) is cached in ~/.cache/rehearsal-player-f0.
"""
import argparse, hashlib, json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import librosa
import make_map as mm

CACHE = os.path.expanduser('~/.cache/rehearsal-player-f0')
SR, HOP = 22050, 512
FR = SR / HOP


def f0_of(path):
    """sung pitch as MIDI numbers every HOP samples, nan where unvoiced"""
    st = os.stat(path)
    out = os.path.join(CACHE, hashlib.md5(f'{path}|{st.st_size}|{st.st_mtime}'.encode()).hexdigest() + '.npy')
    if not os.path.exists(out):
        os.makedirs(CACHE, exist_ok=True)
        y, _ = librosa.load(path, sr=SR, mono=True)
        f0, v, _ = librosa.pyin(y, fmin=65, fmax=700, sr=SR, hop_length=HOP, frame_length=2048)
        np.save(out, np.where(v, librosa.hz_to_midi(f0), np.nan))
    return np.load(out)


def pitches(folder, m):
    parts = [k for k in m['stems'] if k != 'I']
    paths = [os.path.join(folder, m['stems'][k]) for k in parts]
    # one process per core; PITCH_WORKERS sets fewer, for anyone who wants cores kept free
    with ProcessPoolExecutor(int(os.environ.get("PITCH_WORKERS") or os.cpu_count() or 1)) as ex:
        return dict(zip(parts, ex.map(f0_of, paths)))


def check(folder, m):
    f0 = pitches(folder, m)
    per = {}
    for n in m['notes']:
        p = f0.get(n['part'])
        if p is None: continue
        a, b = int(n['start'] * FR) + 2, int(n['end'] * FR)
        seg = p[a:max(b, a + 3)]; seg = seg[~np.isnan(seg)]
        if len(seg) < 3: continue
        d = (seg - n['midi'] + 6) % 12 - 6
        per.setdefault(n['bar'], []).append(float((abs(d) < 0.75).mean() > 0.5))
    allv = [x for v in per.values() for x in v]
    print(f'on the sung pitch: {np.mean(allv):.2f} of {len(allv)} notes; bars under half:',
          ' '.join(f'{b}:{np.mean(v):.2f}' for b, v in sorted(per.items()) if np.mean(v) < 0.5) or 'none')


def guide(folder, xml, m, out, from_bar, R=20):
    parts = [k for k in m['stems'] if k != 'I']
    xb, _ = mm.read_xml(xml); nums = mm.xml_numbers(xml); mts = mm.xml_meters(xml)
    starts, t, tempo = [], 0.0, m['tempo']
    for b in xb:
        starts.append((t, tempo)); pos = 0
        for at_, tp in b['tempos']: t += float(at_ - pos) * 60 / tempo; pos = at_; tempo = tp
        t += float(b['quarters'] - pos) * 60 / tempo
    def local(i, q):
        """seconds from bar i's start to q quarters into it"""
        t_, cur = 0.0, starts[i][1]; pos = 0
        for at_, tp in xb[i]['tempos']:
            if at_ >= q: break
            t_ += float(at_ - pos) * 60 / cur; pos = at_; cur = tp
        return t_ + float(q - pos) * 60 / cur
    # the bars in the order they're sung, repeats played as make_map.py plays them, and when each starts at the written tempo
    reps = mm.xml_repeats(xml); played = []
    for i in range(len(xb)):
        played.append(i)
        if i in reps:
            s0, times, e0 = reps[i]
            played += list(range(s0, e0 + 1)) * (times - 1)
    occ, t = [], 0.0
    for i in played: occ.append((i, t)); t += local(i, xb[i]['quarters'])
    total = t
    firsts = {}
    for i, t_ in occ: firsts.setdefault(i, t_)
    plain = lambda i, q: starts[i][0] + local(i, q)        # the score's own seconds, each bar once
    vn, _ = mm.read_voice_notes(xml, parts)
    f0 = pitches(folder, m)
    # each part, frame by frame: its pitch class, or a 13th class for silence
    nS = int(total * R) + 1
    def written(notes):
        a = np.zeros((nS, 13)); a[:, 12] = 1
        for n in notes:
            dur = plain(*n['end']) - plain(*n['start'])
            for i, t_ in occ:
                if i != n['start'][0]: continue
                s = t_ + local(*n['start']); s_, e_ = int(s * R), int((s + dur) * R)
                a[s_:e_] = 0; a[s_:e_, n['midi'] % 12] = 1
        return a
    def sung(p):
        n = int(len(p) / FR * R); a = np.zeros((n, 13))
        for i in range(n):
            seg = p[int(i * FR / R):int((i + 1) * FR / R)]; v = seg[~np.isnan(seg)]
            if len(v) < len(seg) / 2: a[i, 12] = 1; continue
            for x in v: a[i, int(round(x)) % 12] += 1 / len(v)
        return a
    X = [written(vn[p]) for p in parts]; Y = [sung(f0[p]) for p in parts]
    nY = min(len(y) for y in Y)
    cost = sum(1 - xs @ ys[:nY].T for xs, ys in zip(X, Y)) / len(parts)
    _, wp = librosa.sequence.dtw(C=cost, step_sizes_sigma=np.array([[1, 1], [1, 0], [0, 1], [1, 2], [2, 1]]),
                                 weights_add=np.array([0, 0.3, 0.3, 0.1, 0.1]))
    wp = wp[::-1]
    u, idx = np.unique(wp[:, 0] / R, return_index=True)
    at = lambda s: float(np.interp(s, u, wp[idx, 1] / R))
    lines = []
    for i in range(len(xb)):
        if nums[i] < from_bar: continue
        bl = mm.beat_len(mts[i])
        for k in range(max(1, int(xb[i]['quarters'] / bl))):
            lines.append(f'{nums[i]}.{k + 1}={at(firsts[i] + local(i, k * bl)):.2f}')
    open(out, 'w').write('\n'.join(lines) + '\n')
    print(f'match cost {float(cost[wp[:, 0], wp[:, 1]].mean()):.3f} (0 is every frame the written pitch); wrote {len(lines)} beats to {out}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('folder'); ap.add_argument('xml'); ap.add_argument('what', choices=['guide', 'check'])
    ap.add_argument('out', nargs='?', help='guide: the file to write; check: a map other than player map.json')
    ap.add_argument('--from', dest='from_bar', type=int, default=-999)
    a = ap.parse_args()
    if a.what == 'guide':
        m = json.load(open(os.path.join(a.folder, 'player map.json')))
        guide(a.folder, os.path.join(a.folder, a.xml), m, a.out, a.from_bar)
    else:
        check(a.folder, json.load(open(a.out or os.path.join(a.folder, 'player map.json'))))
