"""Why did the aligner choose its path over the truth? Scores both under the model, beat by beat, term by term.

    python3 diag.py SONG SCRATCH [--variant all] [--bars 140-160]

For the tap map (truth, interpolated at every beat boundary) and the aligner's path: each beat's z-scored match
terms and the tempo cost. Prints per bar the cost difference (truth - aligner; positive = the model prefers the
aligner's path there) split into match terms and tempo, and totals. If truth costs less in total, the search failed;
if more, the evidence or the prior is wrong, and the terms say which.
"""
import sys, os, json, argparse
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import align
from features import FPS


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('song'); ap.add_argument('scratch')
    ap.add_argument('--variant', default='all'); ap.add_argument('--bars', default='')
    ap.add_argument('--constrained', action='store_true', help="compare the aligner with the model's best path within +-0.15 s of the taps")
    a = ap.parse_args()
    M = align.Model(a.song, a.scratch, a.variant)
    cfg = M.cfg
    A = dict(np.load(os.path.join(a.scratch, a.song, f'align_{a.variant}.npz')))
    tk = np.load(os.path.join(cfg['song_dir'], cfg['truth']))
    trk_t = np.append(M.t0, M.t1[-1]) + M.shift
    r_true = np.round(np.interp(trk_t, tk[:, 0], tk[:, 1]) * FPS).astype(int)
    r_alg = A['r'].astype(int)
    if a.constrained:
        # the best path the model finds within +-0.15 s of the taps: the truth without the taps' own noise
        Mt = align.Model(a.song, a.scratch, a.variant, band_s=0.15, center_knots=tk, tag='truthband')
        rt = Mt.run(verbose=False)
        r_true = rt['r'].astype(int)
    out = []
    tot = {}
    per_bar = {}
    for name, r in (('truth', r_true), ('aligner', r_alg)):
        terms, tempo = M.path_cost(r)
        tempo = np.nan_to_num(tempo, nan=0.0, posinf=0.0)
        tot[name] = (terms, tempo)
    bars = M.bt['bar_i']
    nb = len(M.bt['bars'])
    lo, hi = 0, nb
    if a.bars:
        x, y = a.bars.split('-'); nums = [b['num'] for b in M.bt['bars']]
        lo = nums.index(int(x)); hi = len(nums) - nums[::-1].index(int(y))
    Tt, Pt = tot['truth']; Ta, Pa = tot['aligner']
    names = list(Tt.keys())
    out.append(f"{a.song}: total cost truth {sum(v.sum() for v in Tt.values()) + Pt.sum():.1f}, aligner "
               f"{sum(v.sum() for v in Ta.values()) + Pa.sum():.1f} (lower is preferred)")
    out.append("  by term (truth - aligner): " + ", ".join(f"{n} {Tt[n].sum() - Ta[n].sum():+.1f}" for n in names) +
               f", tempo {Pt.sum() - Pa.sum():+.1f}")
    out.append("  bar: truth-aligner offset (s) | cost diff by term (only |diff| >= 1) | tempo diff")
    for bi in range(lo, hi):
        ks = np.where(bars == bi)[0]
        dk = {n: float(Tt[n][ks].sum() - Ta[n][ks].sum()) for n in names}
        dp = float(Pt[ks].sum() - Pa[ks].sum())
        off = (r_true[ks[0]] - r_alg[ks[0]]) / FPS
        s = " ".join(f"{n}{v:+.1f}" for n, v in dk.items() if abs(v) >= 1)
        out.append(f"  {M.bt['bars'][bi]['num']:>4}: {off:+6.2f} | {s} | tempo {dp:+.1f}")
    print("\n".join(out))


if __name__ == '__main__':
    main()
