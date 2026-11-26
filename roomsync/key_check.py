"""F7: is the room in the human-sung set's key? Best circular chroma shift of the room against that set and the score.

    python3 key_check.py SONG SCRATCH [--path truth|coarse]

Along a path (the tap map when it exists, else the coarse DTW), every room frame is paired with its human-sung frame, and
for each shift s = 0..11 semitones the mean cosine of room chroma rolled by s against the human-sung chroma (vocals, piano)
and the score's templates is printed, per stretch of 20 s and overall. A shift other than 0 means the room sang or
played in another key or tuning there; the aligner must then use the shifted chroma (features are rolled by s).
"""
import sys, os, json, argparse
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from features import FPS


def shift_scores(R, C, rf, cf):
    ok = (rf >= 0) & (rf < R.shape[1]) & (cf >= 0) & (cf < C.shape[1])
    r = R[:, rf[ok]]; c = C[:, cf[ok]]
    live = (np.linalg.norm(r, axis=0) > 0) & (np.linalg.norm(c, axis=0) > 0)
    r, c = r[:, live], c[:, live]
    return np.array([np.mean(np.sum(np.roll(r, -s, axis=0) * c, axis=0)) if r.shape[1] else np.nan for s in range(12)]), live.sum()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('song'); ap.add_argument('scratch')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, 'songs.json')))[a.song]
    F = dict(np.load(os.path.join(a.scratch, a.song, 'features.npz')))
    shift = json.load(open(os.path.join(a.scratch, a.song, 'clock.json')))['balanced_shift']
    tk = np.load(os.path.join(cfg['song_dir'], cfg['truth']))
    nC = F['C_V_ch'].shape[1]
    cf = np.arange(nC); rf = np.round(np.interp(cf / FPS + shift, tk[:, 0], tk[:, 1]) * FPS).astype(int)
    out = []
    for lab, R, C in (('room vocals vs human-sung vocals', 'R_V_ch', 'C_V_ch'), ('room vocals vs score voices', 'R_V_ch', 'T_V_t'),
                      ('room piano vs human-sung accompaniment', 'R_P_ch', 'C_P_ch'), ('room piano vs score piano', 'R_P_ch', 'T_P_t')):
        sc, n = shift_scores(F[R], F[C], rf, cf)
        best = int(np.nanargmax(sc))
        out.append(f"{lab}: best shift {best if best <= 6 else best - 12:+d} semitones ({sc[best]:.3f} vs {sc[0]:.3f} at 0; {n} frames)")
        per = []
        for t0 in range(0, int(nC / FPS), 20):
            m = (cf >= t0 * FPS) & (cf < (t0 + 20) * FPS)
            s2, n2 = shift_scores(F[R], F[C], rf[m], cf[m])
            if n2 > 50:
                b2 = int(np.nanargmax(s2)); per.append(f"{t0}s:{b2 if b2 <= 6 else b2 - 12:+d}")
        out.append("   by 20 s of human-sung time: " + " ".join(per))
    txt = f"{a.song}\n" + "\n".join(out); print(txt)
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    open(os.path.join(HERE, 'results', f'key check {a.song}.txt'), 'w').write(txt + "\n")


if __name__ == '__main__':
    main()
