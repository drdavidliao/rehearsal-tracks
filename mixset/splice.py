"""A part's track from the set's other mixes, by seconds.

    python3 -m mixset.splice OUT.mp3 --base pred_T1.mp3 --ref balanced.mp3 \
        --take "30.0-116.2=pred_T2.mp3" --take "125.8-151.05=pred_T2.mp3:1.182" \
        [--fade 0.05] [--post 0.846]

Times are on the --ref file's timeline (the Balanced track); each file's own lead (a
Predominant mix ran 1.000 s behind) is measured and allowed for, so the output keeps the base
file's timeline. A take is FROM-TO=FILE[:GAIN]; crossfades are linear, centred on each joint.
Put joints in rests both parts share. --post scales the whole result (a mix limited at -0.01 dBFS
cannot take a gain above 1: bring the whole track to the quieter mix's level instead).

ffmpeg's libmp3lame wrote float input 0.9700x (-0.26 dB) on the build used first; the encode is
measured against what went in and redone with the inverse gain when it misses by > 0.02 dB.
"""
import argparse, os, subprocess, tempfile
import numpy as np, soundfile as sf
from .audio import SR, decode, lag, gain_fit


def encode(y, out):
    with tempfile.TemporaryDirectory() as d:
        w = f'{d}/x.wav'
        sf.write(w, y, SR, subtype='FLOAT')
        g = 1.0
        for _ in range(2):
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', w, '-af', f'volume={g:.7f}', '-c:a', 'libmp3lame',
                            '-b:a', '192k', out], check=True)
            z = decode(out)
            n = min(len(z), len(y))
            k, _ = gain_fit(z[SR:n - SR], y[SR:n - SR])
            if abs(20 * np.log10(k)) < 0.02:
                return g, len(z) - len(y)
            g /= k
    return g, len(z) - len(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--base', required=True); ap.add_argument('--ref', required=True)
    ap.add_argument('--take', action='append', default=[])
    ap.add_argument('--fade', type=float, default=0.05)
    ap.add_argument('--post', type=float, default=1.0)
    a = ap.parse_args()
    R = decode(a.ref)
    y = decode(a.base)
    lb = lag(y, R)
    for t in a.take:
        span, src = t.split('=', 1)
        g = 1.0
        if ':' in os.path.basename(src):
            src, gs = src.rsplit(':', 1)
            g = float(gs)
        t0, t1 = map(float, span.split('-'))
        x = decode(src)
        ls = lag(x, R)
        h = int(a.fade * SR / 2)
        idx = np.arange(int(round(t0 * SR)) + lb - h, int(round(t1 * SR)) + lb + h)
        w = np.ones(len(idx))
        w[:2 * h] = np.linspace(0, 1, 2 * h)
        w[-2 * h:] = np.linspace(1, 0, 2 * h)
        y[idx] = y[idx] * (1 - w[:, None]) + g * x[idx - lb + ls] * w[:, None]
        print(f'{t0:.2f}-{t1:.2f} s from {os.path.basename(src)} x{g} (its lead {ls - lb:+d} samples against the base)')
    y *= a.post
    gfix, dn = encode(y, a.out)
    print(f'peak {20 * np.log10(np.abs(y).max()):.2f} dBFS; encoder gain corrected by {20 * np.log10(gfix):+.2f} dB; '
          f'length {dn:+d} samples against the input')


if __name__ == '__main__':
    main()
