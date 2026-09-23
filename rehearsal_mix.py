#!/usr/bin/env python3
"""Mix a full set of rehearsal tracks from per-staff stems (SKILL.md Step 9.4).

    python3 rehearsal_mix.py TITLE OUT_DIR "Bass=bass.wav" "Baritone=bari.wav" "Tenor 2=t2.wav" "Tenor 1=t1.wav"
                             [--accomp "Piano=piano.wav"] [--trim "Bass=-9"] [--featured 3] [--others -21]

List the voices from the LOWEST to the HIGHEST: the order sets the stereo and 3D
layouts. An accompaniment stem (--accomp, repeatable) is never featured and stays
at 0 dB.

Writes, for every voice V (parentheses around the section name, for Chorus
Connection; a voice named Solo... gets none):
    TITLE - (V) predominant.mp3         V +3 dB, other voices -21 dB, accompaniment 0 dB
    TITLE - (V) part-left.mp3           V hard left, other voices hard right, accompaniment as exported
and once:
    TITLE - Balanced.mp3                everything at 0 dB, as exported (no panning)
    TITLE - Balanced panned.mp3         voices spread across the stereo field, lowest on the left
    TITLE - Balanced 3D, use headphones.mp3
                                        voices placed around the listener with a dummy-head HRTF

Layouts, from a TTBB set the user settled on (TTBB: Bass, Baritone, Tenor 2, Tenor 1):
  panned  lowest to highest evenly from 45% left to 45% right (four voices: -45, -15, +15, +45),
          constant-power pan scaled so a centred voice keeps its level; accompaniment centred.
  3D      listener facing north; lowest voice rear-left (135 deg), highest rear-right (225 deg),
          the rest evenly across the front between 10 deg left and 10 deg right (four voices:
          Bass 135, Baritone 10 left, Tenor 2 10 right, Tenor 1 225); accompaniment straight
          ahead (0 deg). Ear height. MIT KEMAR dummy head, measured at 1.4 m, from the `slab`
          package (pip install slab). Loudness matched to the panned Balanced track.

Stem levels: every stem's median level while sounding is printed. A stem several dB off
the others (one set's Bass came out 9 dB hot) gets --trim, applied before every mix gain.

Peaks: every mix is measured before encoding. Only if one goes over 0 dBFS are ALL of them
turned down by the same amount (the loudest lands at -1 dBFS), so the tracks keep their
loudness relative to one another. The 3D track, a headphone extra, is loudness-matched to
the panned Balanced track and then turned down on its own if it would clip.

Needs numpy and ffmpeg (with libmp3lame); slab for the 3D track (without it the 3D track is
not made, the script says so and exits 1).
"""
import sys, os, types, argparse, subprocess
import numpy as np

SR = 44100


def load(path):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ar', str(SR), '-ac', '2', '-f', 'f64le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float64).reshape(-1, 2).copy()


def sounding_level(x):
    m = x.mean(1); w = SR // 10; n = len(m) // w
    r = 20 * np.log10(np.sqrt((m[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-12)
    s = r[r > -45]
    return float(np.median(s)) if len(s) else float('-inf'), len(s) / 10


def pad(x, n):
    return np.vstack([x, np.zeros((n - len(x), 2))]) if len(x) < n else x[:n]


def db(g):
    return 10 ** (g / 20)


def mono(x):
    return x.mean(1)


def pan_positions(k):
    return [0.0] if k == 1 else list(np.linspace(-0.45, 0.45, k))


def azimuths(k):
    """degrees counterclockwise from straight ahead (90 = left), lowest voice first"""
    if k == 1: return [0.0]
    if k == 2: return [135.0, 225.0]
    front = [0.0] if k == 3 else list(np.linspace(10, -10, k - 2))
    return [135.0] + [a % 360 for a in front] + [225.0]


def hrir_bank():
    sys.modules.setdefault('sounddevice', types.ModuleType('sounddevice'))   # slab imports it; playback unused
    import slab
    h = slab.HRTF.kemar()
    src = np.asarray(h.sources.vertical_polar, float)

    def left_side(az):                       # 0..180, measured every 5 deg at ear height
        near = sorted(range(len(src)), key=lambda i: abs(src[i, 0] - az) + 1000 * abs(src[i, 1]))[:2]
        a, b = near
        if abs(src[a, 0] - az) < 0.01: return np.asarray(h.data[a].data, float)
        wa = abs(src[b, 0] - az) / abs(src[b, 0] - src[a, 0])       # blend the two measured neighbours
        return wa * np.asarray(h.data[a].data, float) + (1 - wa) * np.asarray(h.data[b].data, float)

    def hrir(az):
        az = az % 360
        if az <= 180: return left_side(az)
        return left_side(360 - az)[:, ::-1]  # the set is left/right symmetric: mirror the left side
    return hrir


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('title'); ap.add_argument('out')
    ap.add_argument('voices', nargs='+', help='"Name=stem.wav", lowest voice first')
    ap.add_argument('--accomp', action='append', default=[])
    ap.add_argument('--trim', action='append', default=[], help='"Name=-9": dB applied to that stem first')
    ap.add_argument('--featured', type=float, default=3.0)
    ap.add_argument('--others', type=float, default=-21.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    trims = {k: float(v) for k, v in (t.split('=', 1) for t in a.trim)}
    V = [tuple(s.split('=', 1)) for s in a.voices]
    A = [tuple(s.split('=', 1)) for s in a.accomp]
    for n in trims:
        if n not in {x for x, _ in V + A}: sys.exit(f'--trim names {n!r}, which is not a stem')
    st = {n: load(p) for n, p in V + A}
    N = max(len(x) for x in st.values())
    st = {n: pad(x, N) * db(trims.get(n, 0.0)) for n, x in st.items()}
    names = [n for n, _ in V]; acc = [n for n, _ in A]

    print('stem levels while sounding (after --trim):')
    lv = {n: sounding_level(st[n]) for n in names + acc}
    ref = np.median([lv[n][0] for n in names])
    for n in names + acc:
        l, secs = lv[n]
        flag = f'   <- {l - ref:+.1f} dB from the other voices: consider --trim "{n}={-(l - ref):.0f}"' \
            if n in names and abs(l - ref) >= 4 else ''
        print(f'   {n:12s} {l:6.1f} dBFS over {secs:5.1f} s{flag}')

    label = lambda n: n if n.lower().startswith('solo') else f'({n})'
    accsum = sum((st[n] for n in acc), np.zeros((N, 2)))
    mixes = {}
    for v in names:
        mixes[f'{a.title} - {label(v)} predominant'] = accsum + sum(
            st[n] * db(a.featured if n == v else a.others) for n in names)
        L = mono(st[v]); R = sum((mono(st[n]) for n in names if n != v), np.zeros(N))
        mixes[f'{a.title} - {label(v)} part-left'] = accsum + np.stack([L, R], 1)
    mixes[f'{a.title} - Balanced'] = accsum + sum(st[n] for n in names)
    panned = np.outer(mono(accsum), [1, 1])
    for n, p in zip(names, pan_positions(len(names))):
        th = (p + 1) * np.pi / 4
        panned = panned + np.outer(mono(st[n]), [np.sqrt(2) * np.cos(th), np.sqrt(2) * np.sin(th)])
    mixes[f'{a.title} - Balanced panned'] = panned
    print('\npanned: ' + ', '.join(f'{n} ' + ('centre' if abs(p) < 1e-9 else f'{abs(p)*100:g}% {"left" if p < 0 else "right"}')
                                   for n, p in zip(names, pan_positions(len(names)))))

    missing3d = None
    try:
        hrir = hrir_bank()
    except Exception as ex:
        missing3d = f'{ex.__class__.__name__}: {ex}'
    if missing3d is None:
        out = np.zeros((N + 1024, 2))
        place = list(zip(names, azimuths(len(names)))) + [(n, 0.0) for n in acc]
        for n, az in place:
            f = hrir(az); m = mono(st[n])
            for ch in (0, 1):
                y = np.convolve(m, f[:, ch]); out[:len(y), ch] += y
        out = out[:N]
        rms = lambda x: np.sqrt((x ** 2).mean())
        out *= rms(panned) / rms(out)
        mixes[f'{a.title} - Balanced 3D, use headphones'] = out
        side = lambda az: 'ahead' if az == 0 else (f'{az:g} deg left' if az <= 180 else f'{360 - az:g} deg right')
        print('3D: ' + ', '.join(f'{n} {side(az)}' for n, az in place))

    # Peaks. The tracks singers switch between keep their loudness relative to one another: only if
    # one of them goes over 0 dBFS are all of them turned down, by the same amount. The 3D track is
    # a headphone extra: loudness-matched to the panned Balanced track, then turned down on its
    # own if it would clip (one piece: +1.1 dBFS, taken to -1).
    three_d = f'{a.title} - Balanced 3D, use headphones'
    peaks = {k: 20 * np.log10(np.abs(x).max() + 1e-12) for k, x in mixes.items()}
    worst = max(v for k, v in peaks.items() if k != three_d)
    gains = {k: (-(worst + 1.0) if worst > 0 else 0.0) for k in mixes}
    if three_d in mixes:
        gains[three_d] = min(gains[three_d], -(peaks[three_d] + 1.0)) if peaks[three_d] + gains[three_d] > 0 else gains[three_d]
    print('\npeaks before encoding, and the gain applied:')
    for k in mixes: print(f'   {peaks[k]:+6.2f} dBFS  {gains[k]:+5.2f} dB  {k}')
    for k, x in mixes.items():
        y = (x * db(gains[k])).astype(np.float32)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-',
                        '-c:a', 'libmp3lame', '-b:a', '192k', '-joint_stereo', '1', os.path.join(a.out, k + '.mp3')],
                       input=y.tobytes(), check=True)
    print(f'\n{len(mixes)} tracks written to {a.out}')
    if missing3d:
        print(f'3D track NOT made: the HRTF set could not be loaded ({missing3d}); pip install slab')
        sys.exit(1)


if __name__ == '__main__':
    main()
