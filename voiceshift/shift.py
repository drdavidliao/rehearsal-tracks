"""Shift a vocal stem's pitch, with the formant envelope placed separately.

    python3 -m voiceshift.shift IN.wav OUT.wav [--pitch -12] [--formant -3] [--base 150] [--calibrate]

--formant is where the spectral envelope should END UP relative to the input, in semitones
(0 = kept, equal to --pitch = moved with the pitch).  --base is Signalsmith's rough guess of the
fundamental for its formant analysis: 150 Hz kept the envelope within 0.81-0.90 of a -3 st target
(0.841) across C4-F5 on synthetic vowels; 0 (auto) and 300+ collapsed on some notes.

The engine's setting is not the result: on soprano/alto stems a setting of -3.0 measured -2.71 st
and -3.3 measured -3.02.  --calibrate measures the result (long-term envelope, measure.envelope_shift)
and re-runs once with the setting corrected by the miss.  Every run prints the measured pitch shift
(pYIN, median), envelope shift and time offset, so the numbers that go in the handback are measured.

Signalsmith Stretch, not Rubber Band: Rubber Band R3's formant scale (library, setFormantScale)
reached only 0.6-0.82 of the target on an octave shift and fell back to moving the formants with the
pitch for some settings; its command line has no formant scale at all.
"""
import argparse
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from . import measure

CACHE = os.environ.get('VOICESHIFT_CACHE', os.path.expanduser('~/.cache/voiceshift'))
BIN = os.path.join(CACHE, 'ssshift')


def run(x, sr, pitch, formant, base=150.0):
    """x: frames x channels.  Returns the shifted signal, same length, latency removed."""
    if not os.path.exists(BIN):
        raise SystemExit(f'{BIN} not built: sh voiceshift/build.sh')
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, 'in.f32'), os.path.join(d, 'out.f32')
        x.astype(np.float32).tofile(a)
        subprocess.run([BIN, a, b, str(x.shape[1]), str(sr), str(pitch), str(formant), str(base)],
                       check=True, stderr=subprocess.DEVNULL)
        return np.fromfile(b, np.float32).reshape(-1, x.shape[1]).astype(np.float64)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--pitch', type=float, default=-12.0)
    ap.add_argument('--formant', type=float, default=-3.0, help='target envelope shift, semitones')
    ap.add_argument('--base', type=float, default=150.0)
    ap.add_argument('--setting', type=float, help='engine formant setting (default: --formant)')
    ap.add_argument('--calibrate', action='store_true', help='measure, correct the setting by the miss, re-run once')
    a = ap.parse_args()
    x, sr = sf.read(a.src, always_2d=True)
    setting = a.formant if a.setting is None else a.setting
    y = run(x, sr, a.pitch, setting, a.base)
    env = measure.envelope_shift(x, y, sr)
    if a.calibrate and abs(env - a.formant) > 0.1:
        setting += a.formant - env
        print(f'envelope moved {env:+.2f} st for setting {setting - (a.formant - env):+.2f}; re-running at {setting:+.2f}')
        y = run(x, sr, a.pitch, setting, a.base)
        env = measure.envelope_shift(x, y, sr)
    sf.write(a.dst, y, sr, subtype='PCM_24')
    p = measure.pitch_shift(x, y, sr, a.pitch)
    lag = measure.lag_ms(x, y, sr)
    print(f'{a.dst}: setting {setting:+.2f}; measured pitch {p:+.2f} st, envelope {env:+.2f} st, '
          f'offset {lag:+.1f} ms; peak {20 * np.log10(np.abs(y).max()):+.1f} dBFS')


if __name__ == '__main__':
    main()
