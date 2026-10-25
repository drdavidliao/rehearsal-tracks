"""A time map from one recording of a piece to another (old render -> human-sung set).

    python3 -m mixset.timemap dtw OLD NEW path.npy              # coarse: chroma + onset DTW
    python3 -m mixset.timemap refine OLD NEW path.npy win.npy   # onset cross-correlation per window
    python3 -m mixset.timemap local OLD NEW O0 O1 N0 N1 out.npy [--png P]   # one stretch, ends pinned
    python3 -m mixset.timemap build knots.npy --windows winA.npy --windows winB.npy \
        [--drop T0-T1] [--manual pins.npy] [--png P]

Run dtw and refine twice: on the old accompaniment stem against the new Accompaniment track
(sharp where the piano plays), and on the old Balanced mp3 against the new Balanced (needed
where the piano rests). build keeps windows correlating >= 0.5, the better of the two at each
time, drops any more than 60 ms from the median of its +-2.5 s neighbours, adds hand pins
(an (N, 2) array of old, new seconds) over their span, and writes a monotone knot list. Hand
pins are for what the windows cannot see: a rit. or fermata taken differently, a breath one
singer takes and the other does not, a tempo change one recording ignores (a straight segment
between its two ends), and where the sound stops at the end.
"""
import argparse
import numpy as np, librosa
from scipy.ndimage import median_filter

SR = 22050


def feats(path, hop, t0=None, t1=None, bins=12):
    kw = {} if t0 is None else {'offset': t0, 'duration': t1 - t0}
    y, _ = librosa.load(path, sr=SR, mono=True, **kw)
    C = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=hop, norm=2, bins_per_octave=3 * bins)
    o = librosa.onset.onset_strength(y=y, sr=SR, hop_length=hop)
    o = o / (o.max() + 1e-9)
    n = min(C.shape[1], len(o))
    return np.vstack([C[:, :n], 0.5 * o[None, :n]]) + 1e-4      # the offset keeps silent frames finite


def cmd_dtw(a):
    hop = 441
    X, Y = feats(a.old, hop), feats(a.new, hop)
    _, wp = librosa.sequence.dtw(X=X, Y=Y, metric='cosine', global_constraints=True, band_rad=a.band)
    np.save(a.out, wp[::-1].astype(float) * hop / SR)


def cmd_local(a):
    hop = 220
    o0, o1, n0, n1 = a.o0, a.o1, a.n0, a.n1
    X, Y = feats(a.old, hop, o0, o1), feats(a.new, hop, n0, n1)
    _, wp = librosa.sequence.dtw(X=X, Y=Y, metric='cosine')
    wp = wp[::-1].astype(float) * hop / SR
    wp[:, 0] += o0
    wp[:, 1] += n0
    np.save(a.out, wp)
    if a.png:
        import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 3, figsize=(20, 7))
        ax[0].imshow(X, aspect='auto', origin='lower', extent=[o0, o1, 0, 13]); ax[0].set_title('old')
        ax[1].imshow(Y, aspect='auto', origin='lower', extent=[n0, n1, 0, 13]); ax[1].set_title('new')
        ax[2].plot(wp[:, 0], wp[:, 1] - wp[:, 0]); ax[2].grid(); ax[2].set_title('new - old')
        plt.tight_layout(); plt.savefig(a.png, dpi=60)


def onset_env(p, hop):
    y, _ = librosa.load(p, sr=SR, mono=True)
    return librosa.onset.onset_strength(y=y, sr=SR, hop_length=hop, lag=2, max_size=3)


def cmd_refine(a):
    hop = 110                                          # 5 ms
    eo, en = onset_env(a.old, hop), onset_env(a.new, hop)
    wp = np.load(a.path)
    u, idx = np.unique(wp[:, 0], return_index=True)
    off = median_filter(np.interp(u, wp[:, 0], wp[:, 1]) - u, size=151, mode='nearest')
    fps = SR / hop
    half, S = int(a.win / 2 * fps), int(a.search * fps)
    rows, t = [], a.win / 2
    while t < len(eo) / fps - a.win / 2:
        p = t + np.interp(t, u, off)
        i0, j0 = int(t * fps), int(p * fps)
        x = eo[i0 - half:i0 + half]
        best, bk = -1.0, 0
        if x.std() > 1e-6 and j0 - half - S >= 0 and j0 + half + S < len(en):
            x = (x - x.mean()) / x.std()
            cs = []
            for k in range(-S, S + 1):
                y = en[j0 + k - half:j0 + k + half]
                cs.append(-1 if y.std() < 1e-6 else float(np.dot(x, (y - y.mean()) / y.std())) / len(x))
            bk, best = int(np.argmax(cs)) - S, max(cs)
        rows.append((t, (j0 + bk) / fps, best, p))
        t += a.step
    np.save(a.out, np.array(rows))


def cmd_build(a):
    drops = [tuple(map(float, d.split('-'))) for d in a.drop]
    man = [np.load(m) for m in a.manual]
    spans = drops + [(m[0, 0], m[-1, 0]) for m in man]
    best = {}
    for f in a.windows:
        for t, n, c, _ in np.load(f):
            if c >= a.minc and not any(lo <= t <= hi for lo, hi in spans):
                k = round(t, 3)
                if k not in best or c > best[k][1]:
                    best[k] = (n, c)
    T = np.array(sorted(best)); N = np.array([best[k][0] for k in sorted(best)]); O = N - T
    keep = np.ones(len(T), bool)
    for _ in range(3):
        for i in range(len(T)):
            nb = keep & (np.abs(T - T[i]) <= 2.5)
            if nb.sum() >= 3 and abs(O[i] - np.median(O[nb])) > a.tol:
                keep[i] = False
    pts = list(zip(T[keep], N[keep]))
    for m in man:
        pts += [tuple(p) for p in m]
    K = []
    for t, n in sorted(pts):
        if not K or (t > K[-1][0] + 1e-6 and n > K[-1][1] + 1e-6):
            K.append((t, n))
    K = np.array(K)
    np.save(a.out, K)
    sl = np.diff(K[:, 1]) / np.diff(K[:, 0])
    print(f'{len(K)} knots; slope {sl.min():.3f}..{sl.max():.3f}')
    if a.png:
        import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(16, 9))
        ax[0].plot(K[:, 0], K[:, 1] - K[:, 0], 'k.-', ms=3, lw=.5); ax[0].grid(); ax[0].set_title('new - old')
        ax[1].plot(K[1:, 0], sl, '.-', ms=3, lw=.5); ax[1].set_ylim(0.3, 2); ax[1].grid(); ax[1].set_title('slope')
        plt.tight_layout(); plt.savefig(a.png, dpi=60)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('dtw'); p.add_argument('old'); p.add_argument('new'); p.add_argument('out')
    p.add_argument('--band', type=float, default=0.1)
    p = sub.add_parser('refine'); p.add_argument('old'); p.add_argument('new'); p.add_argument('path'); p.add_argument('out')
    p.add_argument('--step', type=float, default=0.5); p.add_argument('--win', type=float, default=3.0)
    p.add_argument('--search', type=float, default=0.3)
    p = sub.add_parser('local'); p.add_argument('old'); p.add_argument('new')
    for k in ('o0', 'o1', 'n0', 'n1'):
        p.add_argument(k, type=float)
    p.add_argument('out'); p.add_argument('--png')
    p = sub.add_parser('build'); p.add_argument('out')
    p.add_argument('--windows', action='append', default=[]); p.add_argument('--drop', action='append', default=[])
    p.add_argument('--manual', action='append', default=[]); p.add_argument('--png')
    p.add_argument('--minc', type=float, default=0.5); p.add_argument('--tol', type=float, default=0.06)
    a = ap.parse_args()
    {'dtw': cmd_dtw, 'local': cmd_local, 'refine': cmd_refine, 'build': cmd_build}[a.cmd](a)


if __name__ == '__main__':
    main()
