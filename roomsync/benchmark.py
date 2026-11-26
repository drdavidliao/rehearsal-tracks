"""The benchmark (DESIGN.md Step 6): an aligner run against the user's tap map, at every played bar's beat 1.

    python3 benchmark.py SCRATCH [--variant all] [--songs song1,song2]

Error = aligner - truth (room seconds) at each bar both cover, also in beats (the truth's local bar length / beats).
Pass: no bar over 0.5 beat, median at most 60 ms, every bar over 0.25 beat flagged. Flags: margin below T, or the
'no_chroma' and 'no_onsets' variants more than 0.25 beat from 'all' (when those runs exist). T is the smallest margin
that flags every bar over 0.25 beat on that song, and is also reported crossed over (the other song's T), as the
leave-one-song-out number. Writes results/benchmark.txt.
"""
import sys, os, json, argparse
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from score import beat_table


def evaluate(song, scratch, variant):
    cfg = json.load(open(os.path.join(HERE, 'songs.json')))[song]
    A = dict(np.load(os.path.join(scratch, song, f'align_{variant}.npz')))
    tk = np.load(os.path.join(cfg['song_dir'], cfg['truth']))
    kn = A['knots']; bf = A['bar_first']; nums = A['bar_num']
    ct = kn[bf, 0]
    nb = np.diff(np.append(bf, len(kn) - 1))
    end_ct = kn[np.minimum(bf + nb, len(kn) - 1), 0]
    ok = (ct >= tk[1, 0] - 1e-6) & (end_ct <= tk[-2, 0] + 1e-6)
    lo_b, hi_b = cfg.get('truth_bars', [-1e9, 1e9])
    # only the bars the user tapped: a bar's number within the tapped range, and none before its first occurrence
    seen_lo = np.argmax(nums == lo_b) if np.any(nums == lo_b) else 0
    ok &= (nums >= lo_b) & (nums <= hi_b) & (np.arange(len(nums)) >= seen_lo)
    tr = np.interp(ct, tk[:, 0], tk[:, 1]); tr_end = np.interp(end_ct, tk[:, 0], tk[:, 1])
    beat = (tr_end - tr) / nb
    err = kn[bf, 1] - tr
    eb = err / beat
    flags_var = np.zeros(len(bf), bool)
    for v in ('no_chroma', 'no_onsets'):
        p = os.path.join(scratch, song, f'align_{v}.npz')
        if variant == 'all' and os.path.exists(p):
            V = dict(np.load(p))
            flags_var |= np.abs(V['knots'][bf, 1] - kn[bf, 1]) / beat > 0.25
    return dict(song=song, ok=ok, err=err, eb=eb, margin=A['margin'], flags_var=flags_var, nums=nums, edge=A['edge'])


def summarize(R, T, label):
    ok = R['ok']; e = R['err'][ok]; eb = R['eb'][ok]
    flag = ((R['margin'] < T) | R['flags_var'])[ok]
    bad25 = np.abs(eb) > 0.25
    missed = np.sum(bad25 & ~flag)
    passed = (np.abs(eb).max() <= 0.5) and (np.median(np.abs(e)) <= 0.060) and missed == 0
    lines = [f"  {label}: {ok.sum()} bars; median |err| {np.median(np.abs(e))*1000:.0f} ms, 90th "
             f"{np.percentile(np.abs(e),90)*1000:.0f} ms, worst {e[np.argmax(np.abs(e))]*1000:+.0f} ms "
             f"({eb[np.argmax(np.abs(e))]:+.2f} beat); over 0.25/0.5/1 beat: {bad25.sum()}/{np.sum(np.abs(eb)>0.5)}/"
             f"{np.sum(np.abs(eb)>1)}; flagged {flag.sum()} (T={T:.1f}), over-0.25 bars not flagged: {missed}; "
             f"{'PASS' if passed else 'FAIL'}"]
    nums = R['nums'][ok]
    bads = [f"{nums[i]}:{eb[i]:+.2f}{'' if flag[i] else '!'}" for i in np.where(np.abs(eb) > 0.25)[0]]
    lines.append("    bars over 0.25 beat (beats; ! = not flagged): " + " ".join(bads))
    return lines, passed


def best_T(R):
    ok = R['ok']; eb = R['eb'][ok]; m = R['margin'][ok]; fv = R['flags_var'][ok]
    need = (np.abs(eb) > 0.25) & ~fv
    if not need.any(): return 0.0
    return float(np.nanmax(m[need]) + 1e-3)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('scratch'); ap.add_argument('--variant', default='all')
    ap.add_argument('--songs', default='song1,song2')
    a = ap.parse_args()
    songs = a.songs.split(',')
    Rs = {s: evaluate(s, a.scratch, a.variant) for s in songs}
    Ts = {s: best_T(Rs[s]) for s in songs}
    out = [f"benchmark, variant '{a.variant}' (song2's looseness rules (a)-(c) in score.py were added after "
           f"seeing its tap map; song1's result is not informed by them)"]
    for s in songs:
        out.append(f"{s}:")
        l, _ = summarize(Rs[s], Ts[s], "T fitted on this song")
        out += l
        for o in songs:
            if o != s:
                l, _ = summarize(Rs[s], Ts[o], f"T from {o} (leave-one-song-out)")
                out += l[:1]
        out.append(f"    margins: median {np.nanmedian(Rs[s]['margin']):.1f}; band edge within 0.5 s at "
                   f"{int(np.sum(Rs[s]['edge'] < 0.5*43.07))} boundaries")
    txt = "\n".join(out); print(txt)
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    open(os.path.join(HERE, 'results', f"benchmark {a.variant}.txt"), 'w').write(txt + "\n")


if __name__ == '__main__':
    main()
