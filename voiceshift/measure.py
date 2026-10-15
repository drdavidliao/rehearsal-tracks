"""Measurements for revoiced stems.  Every claim about a shift or a balance comes from these.

    python3 -m voiceshift.measure compare ORIG.wav SHIFTED.wav     pitch, envelope, offset, brightness
    python3 -m voiceshift.measure loudness A.wav B.wav ...          Zwicker loudness (ISO 532-1), sones/phon
    python3 -m voiceshift.measure tilt A.wav B.wav ...              brightness: 2-4 kHz against 0.3-1 kHz
    python3 -m voiceshift.measure vowels [--formant -3] [--base 150] the shifter on synthetic vowels

envelope_shift: the long-term spectrum's envelope (cepstrally smoothed, 1.2 kHz quefrency cut) of the
output against the input's, moved by k; the k that fits best over 400-4500 Hz after removing a linear
tilt, in semitones.

vowels: a sawtooth through three resonators (sharp: 80-120 Hz bandwidths; --broad: 250-400 Hz) at
C4, G4, C5, F5, shifted, then fit_k: the stretch of the known filter that best explains the output's
harmonic amplitudes.  fit_k recovers 1.000, 0.845 and 0.500 on vowels built with those factors, so a
miss is the shifter's, not the measurement's.  Sharp formants sampled by harmonics 400-700 Hz apart
are undetermined between harmonics; no method hits them exactly, so judge on --broad.
"""
import argparse
import sys

import numpy as np
import scipy.signal as ss
import soundfile as sf


def _mono(x):
    return x.mean(1) if x.ndim > 1 else x


def ltas_envelope(m, sr, cut_hz=1200):
    f, P = ss.welch(m, sr, nperseg=8192)
    c = np.fft.irfft(np.log(P + 1e-20))
    L = int(sr / cut_hz)
    c[L:-L] = 0
    return f, np.fft.rfft(c).real[:len(f)]


def envelope_shift(x, y, sr):
    f, Ex = ltas_envelope(_mono(x), sr)
    _, Ey = ltas_envelope(_mono(y), sr)
    band = (f > 400) & (f < 4500)
    best = None
    for k in np.arange(0.45, 1.3, 0.0025):
        d = Ey[band] - np.interp(f / k, f, Ex)[band]
        d = d - np.polyval(np.polyfit(f[band], d, 1), f[band])
        e = (d ** 2).mean()
        if best is None or e < best[0]:
            best = (e, k)
    return 12 * np.log2(best[1])


def pitch_shift(x, y, sr, expected=0.0, seconds=10.0):
    """Median semitone change of f0 over the loudest stretch of the input (pYIN on both).  The output
    is searched in the input's range moved by `expected`, so the tracker cannot settle an octave
    away; frames whose change is more than 6 st from `expected` (octave slips) are left out."""
    import librosa
    m, n = _mono(x), _mono(y)
    hop = int(sr * 0.5)
    lev = [np.std(m[i:i + int(seconds * sr)]) for i in range(0, max(1, len(m) - int(seconds * sr)), hop)]
    i0 = int(np.argmax(lev)) * hop
    seg = slice(i0, i0 + int(seconds * sr))
    lo, hi = 120.0, 1100.0
    k = 2 ** (expected / 12)
    fx, vx, _ = librosa.pyin(m[seg], fmin=lo, fmax=hi, sr=sr, frame_length=4096)
    fy, vy, _ = librosa.pyin(n[seg], fmin=lo * k, fmax=hi * k, sr=sr, frame_length=4096)
    ok = vx & vy & ~np.isnan(fx) & ~np.isnan(fy)
    d = 12 * np.log2(fy[ok] / fx[ok])
    d = d[np.abs(d - expected) < 6]
    return float(np.median(d)) if len(d) else float('nan')


def lag_ms(x, y, sr):
    """Offset of y against x from their level envelopes (positive: y late)."""
    def env(s):
        s = _mono(s)
        h = 64
        return np.sqrt(np.convolve(s ** 2, np.ones(512) / 512, 'same')[::h])
    ex, ey = env(x), env(y)
    c = np.correlate(ey - ey.mean(), ex - ex.mean(), 'full')
    return (np.argmax(c) - len(ex) + 1) * 64 / sr * 1000


def tilt(x, sr, hi=(2000, 4000), lo=(300, 1000)):
    f, P = ss.welch(_mono(x), sr, nperseg=8192)
    band = lambda a, b: 10 * np.log10(P[(f >= a) & (f < b)].sum())
    return band(*hi) - band(*lo)


def zwicker(x, sr, t0=None, t1=None, cal_db=100.0):
    """Mean time-varying loudness (sones) while sounding (frames above 10% of the stem's peak).
    One calibration for every stem: a full-scale sine plays at cal_db SPL."""
    from scipy.signal import resample_poly
    from mosqito.sq_metrics import loudness_zwtv
    m = _mono(x)
    if t0 is not None:
        m = m[int(t0 * sr):int(t1 * sr)]
    m = resample_poly(m, 48000, sr)
    pa = m * 2e-5 * 10 ** (cal_db / 20)
    N, _, _, _ = loudness_zwtv(pa, 48000, field_type='free')
    return float(N[N > 0.1 * N.max()].mean())


# ---- synthetic vowels
FORM_SHARP = ((800, 80), (1300, 90), (2800, 120))
FORM_BROAD = ((750, 250), (1250, 300), (2700, 400))


def vowel(f0hz, form, sr=44100, T=3.0, scale=1.0):
    t = np.arange(int(sr * T)) / sr
    ph = np.cumsum(f0hz * (1 + 0.01 * np.sin(2 * np.pi * 5 * t))) / sr
    y = ss.sawtooth(2 * np.pi * ph) * 0.3
    for F, bw in form:
        r = np.exp(-np.pi * bw * scale / sr)
        th = 2 * np.pi * F * scale / sr
        y = ss.lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], y)
    return y / np.abs(y).max() * 0.5


def fit_k(s, f0n, form, sr=44100):
    def H(f):
        z = np.exp(1j * 2 * np.pi * f / sr)
        h = np.ones_like(f, complex)
        for F, bw in form:
            r = np.exp(-np.pi * bw / sr)
            th = 2 * np.pi * F / sr
            h *= (1 - r) / (1 - 2 * r * np.cos(th) / z + r * r / z ** 2)
        return np.abs(h)
    s = s[sr // 2:-sr // 2].astype(float)
    S = np.abs(np.fft.rfft(s * np.hanning(len(s))))
    fr = np.fft.rfftfreq(len(s), 1 / sr)
    hs = np.arange(1, int(4000 / f0n))
    la = np.log([S[(fr > h * f0n * 0.97) & (fr < h * f0n * 1.03)].max() for h in hs])
    best = None
    for k in np.arange(0.40, 1.30, 0.005):
        lh = np.log(H(hs * f0n / k))
        tl = np.polyfit(np.log(hs), la - lh, 1)
        e = ((la - lh - np.polyval(tl, np.log(hs))) ** 2).mean()
        if best is None or e < best[0]:
            best = (e, k)
    return best[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('compare'); c.add_argument('orig'); c.add_argument('shifted')
    c.add_argument('--expected', type=float, default=-12.0, help='the shift asked for, semitones')
    l = sub.add_parser('loudness'); l.add_argument('files', nargs='+')
    l.add_argument('--window', default='15,75', help='T0,T1 seconds to measure (default 15,75)')
    t = sub.add_parser('tilt'); t.add_argument('files', nargs='+')
    v = sub.add_parser('vowels'); v.add_argument('--pitch', type=float, default=-12)
    v.add_argument('--formant', type=float, default=-3); v.add_argument('--base', type=float, default=150)
    a = ap.parse_args()
    if a.cmd == 'compare':
        x, sr = sf.read(a.orig, always_2d=True); y, _ = sf.read(a.shifted, always_2d=True)
        print(f'pitch {pitch_shift(x, y, sr, a.expected):+.2f} st, envelope {envelope_shift(x, y, sr):+.2f} st, '
              f'offset {lag_ms(x, y, sr):+.1f} ms, brightness {tilt(x, sr):+.1f} -> {tilt(y, sr):+.1f} dB')
    elif a.cmd == 'loudness':
        t0, t1 = map(float, a.window.split(','))
        ref = None
        for f in a.files:
            x, sr = sf.read(f, always_2d=True)
            n = zwicker(x, sr, t0, t1)
            ref = ref or n
            print(f'{n:6.2f} sone  ({10 * np.log2(n / ref):+5.1f} phon vs first)  {f}')
    elif a.cmd == 'tilt':
        for f in a.files:
            x, sr = sf.read(f, always_2d=True)
            print(f'{tilt(x, sr):+6.1f} dB (2-4 kHz vs 0.3-1 kHz)  {f}')
    else:
        from . import shift
        for name, form in (('sharp', FORM_SHARP), ('broad', FORM_BROAD)):
            ks = []
            for f0 in (262, 392, 523, 698):
                y = vowel(f0, form)
                o = shift.run(np.stack([y, y], 1), 44100, a.pitch, a.formant, a.base)[:, 0]
                ks.append(fit_k(o, f0 * 2 ** (a.pitch / 12), form))
            print(f'{name} formants: envelope scale at C4 G4 C5 F5 {[round(k, 3) for k in ks]}, '
                  f'target {2 ** (a.formant / 12):.3f}')


if __name__ == '__main__':
    sys.exit(main())
