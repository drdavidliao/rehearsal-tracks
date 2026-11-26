"""Which voice sings where, from finished mixes with no stems.

    python3 -m mixset.featured ACCOMP.mp3 "Tenor=pred.mp3,muted.mp3" "Bass=pred.mp3,muted.mp3" \
        [--hop 0.5] [--wav DIR] [--fit T0-T1]

The mixes do not null by subtraction: the accompaniment sat at a different gain in each kind of
mix (0.12 Predominant, 0.35 Muted, 0.15 Balanced) and Balanced - Muted left it 15 dB down at
best. But the Muted accompaniment was 3x the Predominant one (0.3513 / 0.1171; 2.99 fitted on
another set), so F = 3 x Predominant - Muted cancels it and keeps the featured voice: a part
that was silent read about 30 dB under the parts singing. 3 is the default and served three
sets. --fit measures it over a stretch where nobody sings, the accompaniment alone; fitted over
an ending where the choir still held its chord it came out 0.18-0.37, which is wrong. Prints F's
level per hop for each part; --wav writes F for a pitch tracker.
"""
import argparse, os
import numpy as np, soundfile as sf
from .audio import SR, decode, lag, levels, gain_fit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('accomp'); ap.add_argument('parts', nargs='+')
    ap.add_argument('--hop', type=float, default=0.5)
    ap.add_argument('--wav')
    ap.add_argument('--fit', help='T0-T1: measure the factor over this accompaniment-only stretch')
    a = ap.parse_args()
    A = decode(a.accomp)
    F = {}
    for spec in a.parts:
        name, files = spec.split('=', 1)
        p, m = (decode(f) for f in files.split(','))
        p, m = p[lag(p, A):], m[lag(m, A):]
        n = min(len(p), len(m), len(A))
        p, m = p[:n], m[:n]
        k = 3.0
        if a.fit:
            t0, t1 = map(float, a.fit.split('-'))
            k, res = gain_fit(m[int(t0 * SR):int(t1 * SR)], p[int(t0 * SR):int(t1 * SR)])
            print(f'{name}: Muted = {k:.3f} x Predominant over {a.fit} s ({res:.1f} dB left)')
        F[name] = k * p - m
        if a.wav:
            os.makedirs(a.wav, exist_ok=True)
            f = F[name].mean(1)
            sf.write(f'{a.wav}/{name}.wav', f / (np.abs(f).max() + 1e-9) * 0.9, SR)
    L = {k: levels(v, a.hop) for k, v in F.items()}
    n = min(len(v) for v in L.values())
    print('     t ' + ' '.join(f'{k[:9]:>9}' for k in L))
    for i in range(n):
        print(f'{i * a.hop:6.1f} ' + ' '.join(f'{L[k][i]:9.0f}' for k in L))


if __name__ == '__main__':
    main()
