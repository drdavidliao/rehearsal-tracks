"""Assumption test (DESIGN.md): the room keeps the human-sung set's beat lengths up to a smoothly changing ratio, except where the
score marks a change. Measured on the tap map (truth): per played bar, ratio = room bar length / human-sung bar length;
the change in log ratio from bar to bar, split by whether the score.py marks the bar loose. Per-beat sd is the
per-bar change / sqrt(beats per bar) (a random walk). Read-only: nothing is fitted to it unless DESIGN.md says so.

    python3 ratio_check.py SONG SCRATCH
"""
import sys, os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from score import beat_table


def truth_knots(cfg):
    return np.load(os.path.join(cfg['song_dir'], cfg['truth']))


def bar_starts(bt, shift):
    """Human-sung Balanced time of each played bar's start, and each bar's end."""
    bars = bt['bars']
    return np.array([b['beat_t'][0] + shift for b in bars]), np.array([b['end_t'] + shift for b in bars])


def main(song, scratch):
    cfg = json.load(open(os.path.join(HERE, 'songs.json')))[song]
    bt = beat_table(cfg)
    shift = json.load(open(os.path.join(scratch, song, 'clock.json')))['balanced_shift']
    tk = truth_knots(cfg)
    s, e = bar_starts(bt, shift)
    lo, hi = tk[1, 0], tk[-2, 0]     # the first and last knots are extrapolations
    ok = (s >= lo - 1e-6) & (e <= hi + 1e-6)
    rs, re_ = np.interp(s, tk[:, 0], tk[:, 1]), np.interp(e, tk[:, 0], tk[:, 1])
    ratio = (re_ - rs) / (e - s)
    lr = np.log(ratio)
    first = {}
    for k, bi in enumerate(bt['bar_i']): first.setdefault(bi, k)
    loose = np.array([bt['loose'][first[i]: first[i] + len(bt['bars'][i]['beat_t'])].max() for i in range(len(s))])
    nb = np.array([len(b['beat_t']) for b in bt['bars']])
    idx = [i for i in range(1, len(s)) if ok[i] and ok[i - 1]]
    dl = np.array([lr[i] - lr[i - 1] for i in idx])
    per_beat = dl / np.sqrt(nb[idx])
    lz = np.array([max(loose[i], loose[i - 1]) for i in idx])
    out = [f"{song}: {len(idx)} bar-to-bar changes of log(room/human-sung) from the tap map",
           f"  ratio range {ratio[ok].min():.2f}-{ratio[ok].max():.2f}"]
    for name, m in (('steady (not loose)', lz == 0), ('loose', lz > 0)):
        x = per_beat[m]
        if len(x):
            out.append(f"  {name}: n={len(x)}, per-beat sd {x.std():.3f}, |change| 90th {np.percentile(abs(x),90):.3f}, max {abs(x).max():.3f}")
    big = [(bt['bars'][i]['num'], dl[n], lz[n]) for n, i in enumerate(idx) if abs(per_beat[n]) > 0.15]
    out.append("  bars with per-beat change > 0.15 (bar, log change per bar, looseness): " +
               ", ".join(f"{b}:{d:+.2f}/{l:.1f}" for b, d, l in big))
    txt = "\n".join(out); print(txt)
    open(os.path.join(HERE, 'results', f'ratio check {song}.txt'), 'w').write(txt + "\n")


if __name__ == '__main__':
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    main(sys.argv[1], sys.argv[2])
