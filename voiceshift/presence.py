"""Restore presence ("ring") to a stem: a broad peaking boost, gain chosen to match a reference
stem's brightness (2-4 kHz energy against 0.3-1 kHz).

    python3 -m voiceshift.presence IN.wav OUT.wav --like REF.wav [--freq 3000] [--q 0.9]

Why: an SSA practice set dropped an octave to TTB sounded as if its tenors were soft.  Nothing in
the shift had dulled them (brightness within 1 dB of the originals), but the soprano recordings were
3.5-4 dB darker than the alto's, and a TTB whose top lines are duller than its low ones reads as
soft tenors.  +3.75-4.25 dB at 3 kHz, Q 0.9, matched the low stem's brightness and alone brought the
tenors level with the low parts in Zwicker loudness (0.0, +0.3 phon): no level trim was needed.
Zero-phase (forward-backward), so nothing moves in time.
"""
import argparse

import numpy as np
import scipy.signal as ss
import soundfile as sf

from .measure import tilt


def peaking(f0, q, g_db, sr):
    A = 10 ** (g_db / 40)
    w = 2 * np.pi * f0 / sr
    al = np.sin(w) / (2 * q)
    b = [1 + al * A, -2 * np.cos(w), 1 - al * A]
    a = [1 + al / A, -2 * np.cos(w), 1 - al / A]
    return np.array(b) / a[0], np.array(a) / a[0]


def boost(x, sr, g_db, f0=3000.0, q=0.9):
    b, a = peaking(f0, q, g_db / 2, sr)          # applied twice by filtfilt
    return ss.filtfilt(b, a, x, axis=0)


def match(x, sr, target, f0=3000.0, q=0.9, max_db=9.0):
    best = None
    for g in np.arange(0, max_db + 0.01, 0.25):
        y = boost(x, sr, g, f0, q)
        t = tilt(y, sr)
        if best is None or abs(t - target) < abs(best[1] - target):
            best = (g, t, y)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--like', required=True, help='stem whose brightness to match')
    ap.add_argument('--freq', type=float, default=3000.0); ap.add_argument('--q', type=float, default=0.9)
    a = ap.parse_args()
    x, sr = sf.read(a.src, always_2d=True)
    r, _ = sf.read(a.like, always_2d=True)
    target = tilt(r, sr)
    g, t, y = match(x, sr, target, a.freq, a.q)
    sf.write(a.dst, y, sr, subtype='PCM_24')
    print(f'{a.dst}: +{g:.2f} dB at {a.freq:.0f} Hz (Q {a.q}); brightness {tilt(x, sr):+.1f} -> {t:+.1f} dB '
          f'(reference {target:+.1f}); peak {20 * np.log10(np.abs(y).max()):+.1f} dBFS')


if __name__ == '__main__':
    main()
