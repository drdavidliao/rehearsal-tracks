"""Build a part's stem from others by bars: one stem, with chosen bar ranges taken from another.

    python3 -m voiceshift.splice OUT.wav --base low.wav --take "24-27=t2.wav" --take "56-59=t2.wav" \
        --bar1 1.03 --bar 2.0 [--before 0.3] [--fade 0.05]

Bar n starts at --bar1 + --bar * (n - 1) seconds (voiceshift.bargrid measures both).  Each splice
sits --before seconds ahead of its barline, which should be inside a rest every voice shares (check
the score: the bars before 24, 28, 56 and 60 ended in rests in the piece this was made for), with a
linear crossfade of --fade.  Prints the level of both stems at every splice point: two silent or
two equal tails are safe; a loud note under a splice is not.

Used where a revoicing gives a part another part's line for a few bars (Baritone singing Soprano 2's
line, an octave down, in bars 24-27 and 56-59, the rest of the time the Alto's).
"""
import argparse

import numpy as np
import soundfile as sf


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out')
    ap.add_argument('--base', required=True)
    ap.add_argument('--take', action='append', default=[], help='"FIRST-LAST=stem.wav", bars inclusive')
    ap.add_argument('--bar1', type=float, required=True); ap.add_argument('--bar', type=float, required=True)
    ap.add_argument('--before', type=float, default=0.3); ap.add_argument('--fade', type=float, default=0.05)
    a = ap.parse_args()
    x, sr = sf.read(a.base, always_2d=True)
    info = sf.info(a.base)
    out = x.copy()
    bt = lambda n: a.bar1 + a.bar * (n - 1)
    fade = int(a.fade * sr)
    for spec in a.take:
        rng, path = spec.split('=', 1)
        b0, b1 = (int(v) for v in rng.split('-'))
        y, sr2 = sf.read(path, always_2d=True)
        if sr2 != sr or len(y) != len(x):
            raise SystemExit(f'{path}: not the same rate and length as the base stem')
        i0, i1 = int((bt(b0) - a.before) * sr), int((bt(b1 + 1) - a.before) * sr)
        w = np.zeros(len(x))
        w[i0:i0 + fade] = np.linspace(0, 1, fade); w[i0 + fade:i1] = 1; w[i1:i1 + fade] = np.linspace(1, 0, fade)
        out = out * (1 - w[:, None]) + y * w[:, None]
        for i in (i0, i1):
            seg = slice(i - int(0.05 * sr), i + int(0.05 * sr))
            lv = lambda s: 20 * np.log10(np.std(s[seg]) + 1e-9)
            print(f'splice at {i / sr:7.2f} s: base {lv(x):5.0f} dBFS, {path.split("/")[-1]} {lv(y):5.0f} dBFS')
    sf.write(a.out, out, sr, subtype=info.subtype)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
