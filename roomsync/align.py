"""The aligner (DESIGN.md Steps 3-5): every played beat's room time, beat by beat, with a margin per bar.

    python3 align.py SONG SCRATCH [--variant all|no_chroma|no_onsets] [--band 6]

Reads SCRATCH/SONG/features.npz (features.py) and clock.json; writes SCRATCH/SONG/align_VARIANT.npz:
  r       room frame of every beat boundary k = 0..K (beat k runs r[k]..r[k+1]); K is the end of the last bar
  r_snap  the same in seconds, with each bar's beat 1 snapped to its attacking stream's onset (Step 5)
  margin  per played bar: extra cost of the best path with its beat 1 forced >= 0.3 beat away
  knots   (human-sung Balanced seconds, room seconds) at every boundary: the time map
Frames are 512 samples at 22.05 kHz.

The model (a singer who knows the piece):
- states (boundary k, room frame r_k, ratio index j of the previous beat), ratio = room beat length / the human-sung set's;
- each beat's match: the room's span stretched onto the human-sung span, 6 samples inside it: chroma of the room's vocals
  against the voices' score template and the human-sung vocals, the same for the piano; onset patterns of vocals and piano
  against the human-sung set's; the room's onset at the beat's start weighted by whether the score (and the human-sung set) attack there,
  per stream, claps from the clap staff; the room's vocal activity against the human-sung set's; vocal chroma allows the room's
  singers a semitone of drift (the best of shifts -1, 0, +1);
- every term z-scored on the song's candidates and clipped to [-2, 3]: one stream's bad beat (a wrong note, a fill)
  costs a fixed amount and can't overrule the rest;
- counting: the change in log ratio from one beat to the next costs (change / sigma)^2 / 2, sigma 0.05 where the
  score is steady up to 0.5 where it marks a fermata, a tempo word, a hold (score.py 'loose');
- a free start and end: beats outside the recording carry no evidence (match 0).
Model(...).path_cost(r) scores any path (diag.py uses it to compare the truth with the aligner's choice).
"""
import sys, os, json, argparse, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from score import beat_table
from features import FPS

U = (np.arange(6) + 0.5) / 6
RHO = np.exp(np.linspace(np.log(0.25), np.log(8.0), 61))
LRHO = np.log(RHO)
SIG0, SIG1 = 0.05, 0.5
CLIP = (-2.0, 3.0)
TERMS = ['vch_score', 'vch_tracks', 'pch_score', 'pch_tracks', 'von_pat', 'pon_pat', 'att_v', 'att_p', 'att_c', 'act']
BIG = 1e9


def coarse_center(F, nR, nC):
    """Room frame for every human-sung frame, by subsequence DTW of 8-frame chroma (vocals + piano)."""
    import librosa
    def pool(x):
        m = (x.shape[1] // 8) * 8
        y = x[:, :m].reshape(x.shape[0], -1, 8).mean(2) + 1e-3   # silent columns: flat, not NaN
        return y / np.maximum(np.linalg.norm(y, axis=0, keepdims=True), 1e-6)
    X = pool(np.vstack([F['R_V_ch'], F['R_P_ch']]))
    Y = pool(np.vstack([F['C_V_ch'], F['C_P_ch']]))
    # steps (1,1), (2,1), (1,2) only: the local slope stays within 1/2..2, so it cannot collapse a stretch
    D, wp = librosa.sequence.dtw(X=X, Y=Y, metric='cosine', subseq=True,
                                 step_sizes_sigma=np.array([[1, 1], [2, 1], [1, 2]]),
                                 weights_add=np.array([0, 0, 0]), weights_mul=np.array([1, 1.5, 1.5]))
    wp = wp[::-1]
    ci, ri = wp[:, 1] * 8 + 4, wp[:, 0] * 8 + 4
    cu, inv = np.unique(ci, return_inverse=True)
    rm = np.bincount(inv, ri) / np.bincount(inv)
    return cu.astype(float), rm


class Model:
    def __init__(self, song, scratch, variant='all', band_s=6.0, center_knots=None, tag=None):
        """center_knots (human-sung Balanced s -> room s): centre the band on them instead of the coarse DTW (diag.py's
        truth-constrained run). tag names the output file (default: the variant)."""
        self.song, self.scratch, self.variant, self.band_s = song, scratch, variant, band_s
        self.tag = tag or variant
        self.cfg = cfg = json.load(open(os.path.join(HERE, 'songs.json')))[song]
        self.bt = bt = beat_table(cfg)
        F = dict(np.load(os.path.join(scratch, song, 'features.npz')))
        clock = json.load(open(os.path.join(scratch, song, 'clock.json')))
        self.lat = clock['map_vs_voices'][0]                       # the onset detector's latency
        self.shift = clock['balanced_shift']
        self.nR = nR = F['R_V_on'].shape[0]; self.nC = nC = F['C_V_on'].shape[0]
        self.t0, self.t1 = t0, t1 = bt['t0'], bt['t1']
        self.K = K = len(t0)
        a = t0 * FPS; self.L = L = (t1 - t0) * FPS                  # human-sung frames of each beat
        cb = np.append(a, t1[-1] * FPS)                             # boundaries 0..K
        if center_knots is None:
            cu, rm = coarse_center(F, nR, nC)
            cen = np.interp(cb, cu, rm)                              # outside the DTW: ratio 1 from its ends
            cen = np.where(cb < cu[0], rm[0] - (cu[0] - cb), cen)
            cen = np.where(cb > cu[-1], rm[-1] + (cb - cu[-1]), cen)
        else:
            ck = np.asarray(center_knots)
            cen = np.interp(cb / FPS + self.shift, ck[:, 0], ck[:, 1]) * FPS
        self.B = B = int(round(band_s * FPS)); self.P = 2 * B + 1
        self.c0 = np.round(cen).astype(int) - B                     # room frame of band index 0 at each boundary
        self.RV, self.RP = F['R_V_ch'].T, F['R_P_ch'].T
        self.RVon, self.RPon, self.RDon, self.Ract = F['R_V_on'], F['R_A_on'], F['R_D_on'], F['R_act']
        self.CV, self.CP = F['C_V_ch'].T, F['C_P_ch'].T
        self.TV, self.TP = F['T_V_t'].T, F['T_P_t'].T
        self.CVon, self.CPon, self.Cact = F['C_V_on'], F['C_A_on'], F['C_act']
        self.w = {t: 1.0 for t in TERMS}
        if variant == 'no_chroma':
            for t in ('vch_score', 'vch_tracks', 'pch_score', 'pch_tracks'): self.w[t] = 0.0
        if variant == 'no_onsets':
            for t in ('von_pat', 'pon_pat', 'att_v', 'att_p', 'att_c'): self.w[t] = 0.0
        self.ci = np.clip(np.round(a[:, None] + U[None, :] * L[:, None]).astype(int), 0, nC - 1)   # (K, 6)
        ca = np.clip(np.round(a).astype(int), 0, nC - 1)
        self.exp_v = 0.5 * bt['att_v'] + 0.5 * np.clip(self.CVon[ca], 0, 3) / 3
        self.exp_p = 0.5 * bt['att_p'] + 0.5 * np.clip(self.CPon[ca], 0, 3) / 3
        self.exp_v[bt['entry']] *= 3                                # landmarks: an entry after rest
        self.exp_c = bt['att_c'].astype(float)
        self.snd = (np.linalg.norm(self.TV[self.ci], axis=2) > 0).astype(float) * 2 - 1   # a voice sounds (+1) or not
        self.sig = SIG0 + (SIG1 - SIG0) * bt['loose']
        self.allow = np.where(bt['loose'][:, None] >= 0.6, True, (RHO[None, :] >= 0.3) & (RHO[None, :] <= 4.0))
        # term statistics over the candidates of every 7th beat, for z-scoring
        acc = {t: [] for t in TERMS}
        for k in range(0, K, 7):
            o, _ = self.raw_terms(k, self.c0[k] + np.arange(self.P))
            for t in TERMS:
                x = o[t][np.isfinite(o[t])]
                if len(x): acc[t].append(x[::13])
        self.stats = {}
        for t in TERMS:
            x = np.concatenate(acc[t]) if acc[t] else np.zeros(1)
            self.stats[t] = (float(np.mean(x)), float(np.std(x)) + 1e-6)

    def raw_terms(self, k, r, d=None):
        """Raw term values for beat k at room start frames r (P,), durations d (J,) frames (default: every ratio)."""
        if d is None: d = np.maximum(1, np.round(RHO * self.L[k])).astype(int)
        J = len(d); nR = self.nR
        idx = r[:, None, None] + np.floor(U[None, None, :] * d[None, :, None]).astype(int)   # (P, J, 6)
        valid = (idx >= 0) & (idx < nR)
        ic = np.clip(idx, 0, nR - 1)
        nv = valid.sum(2)
        def mean6(x):
            return np.where(nv > 0, (x * valid).sum(2) / np.maximum(nv, 1), np.nan)
        ci = self.ci[k]
        rv = self.RV[ic]; rp = self.RP[ic]
        out = {}
        # the room's singers may drift up to a semitone off (song2's room sang a semitone flat for ~20 s
        # in the Maestoso while its piano stayed in tune): a vocal chroma match is the best of shifts -1, 0, +1
        def vmatch(tgt):
            return np.max([np.einsum('pjsc,sc->pjs', rv, np.roll(tgt, s_, axis=1)) for s_ in (-1, 0, 1)], axis=0)
        out['vch_score'] = mean6(vmatch(self.TV[ci]))
        out['vch_tracks'] = mean6(vmatch(self.CV[ci]))
        out['pch_score'] = mean6(np.einsum('pjsc,sc->pjs', rp, self.TP[ci]))
        out['pch_tracks'] = mean6(np.einsum('pjsc,sc->pjs', rp, self.CP[ci]))
        out['von_pat'] = mean6(self.RVon[ic] * self.CVon[ci][None, None, :])
        out['pon_pat'] = mean6(self.RPon[ic] * self.CPon[ci][None, None, :])
        # sounding or quiet where the human-sung voices are (the score's note lengths overstate staccato singing)
        out['act'] = mean6(self.Ract[ic] * self.Cact[ci][None, None, :])
        rr = np.clip(r, 1, nR - 2); ok = (r >= 0) & (r < nR)
        def peak(x):
            v = np.maximum(np.maximum(x[rr - 1], x[rr]), x[rr + 1])
            return np.where(ok, v, np.nan)[:, None] * np.ones((1, J))
        out['att_v'] = peak(self.RVon) * self.exp_v[k]
        out['att_p'] = peak(self.RPon) * self.exp_p[k]
        out['att_c'] = peak(self.RDon) * self.exp_c[k]
        return out, d

    def zterms(self, k, r, d=None):
        """Weighted, z-scored, clipped terms (positive = evidence for), each (P, J)."""
        o, d = self.raw_terms(k, r, d)
        z = {}
        for t in TERMS:
            if self.w[t] == 0: continue
            if (t == 'att_v' and self.exp_v[k] == 0) or (t == 'att_p' and self.exp_p[k] == 0) or \
               (t == 'att_c' and self.exp_c[k] == 0):
                continue                                             # an attack only counts where one is expected
            x = (o[t] - self.stats[t][0]) / self.stats[t][1]
            z[t] = self.w[t] * np.clip(np.nan_to_num(x, nan=0.0), *CLIP)
        return z, d

    def match(self, k, r):
        z, d = self.zterms(k, r)
        tot = np.zeros((len(r), len(d)), np.float32)
        for v in z.values(): tot += v
        return -tot, d

    def tempo_T(self, k):
        s = max(self.sig[k], self.sig[k - 1] if k > 0 else 0)
        T = ((LRHO[:, None] - LRHO[None, :]) / s) ** 2 / 2           # T[j_new, j_prev]
        return np.zeros_like(T) if k == 0 else T

    def path_cost(self, r):
        """Cost of a path given by boundary frames r (K+1,): per-term match costs (K,) and tempo costs (K,)."""
        K = self.K
        terms = {t: np.zeros(K) for t in TERMS}
        tempo = np.zeros(K)
        lr_prev = None
        for k in range(K):
            d = max(1, int(r[k + 1] - r[k]))
            z, _ = self.zterms(k, np.array([r[k]]), np.array([d]))
            for t, v in z.items(): terms[t][k] = -float(v[0, 0])
            # the ratio as the DP sees it: the grid ratio whose duration is nearest d
            jj = int(np.argmin(np.abs(np.maximum(1, np.round(RHO * self.L[k])) - d)))
            lr = LRHO[jj]
            if lr_prev is not None:
                s = max(self.sig[k], self.sig[k - 1])
                tempo[k] = ((lr - lr_prev) / s) ** 2 / 2
            lr_prev = lr
        return terms, tempo

    def run(self, verbose=True):
        K, P, c0, bt = self.K, self.P, self.c0, self.bt
        J = len(RHO)
        t_start = time.time()
        Fs = np.zeros((K + 1, P, J), np.float32)
        BP = np.zeros((K + 1, P, J), np.int16)                       # best previous ratio index
        Ms = np.zeros((K, P, J), np.float32)
        Ds = np.zeros((K, J), np.int32)
        for k in range(K):
            M, d = self.match(k, c0[k] + np.arange(P))
            M[:, ~self.allow[k]] = BIG
            Ms[k] = M; Ds[k] = d
            T = self.tempo_T(k)
            cand = Fs[k][:, None, :] + T[None, :, :]                 # (P, Jnew, Jprev)
            jb = np.argmin(cand, axis=2); best = np.take_along_axis(cand, jb[:, :, None], 2)[:, :, 0]
            tot = best + M
            Fn = np.full((P, J), BIG, np.float32); Bn = np.zeros((P, J), np.int16)
            sh = c0[k] - c0[k + 1]
            for j in range(J):
                o_new = np.arange(P) + sh + d[j]
                ok = (o_new >= 0) & (o_new < P)
                Fn[o_new[ok], j] = tot[ok, j]; Bn[o_new[ok], j] = jb[ok, j]
            Fs[k + 1] = Fn; BP[k + 1] = Bn
        oK, jK = np.unravel_index(np.argmin(Fs[K]), Fs[K].shape)
        best_cost = float(Fs[K][oK, jK])
        o_path = np.zeros(K + 1, int); j_path = np.zeros(K + 1, int)
        o_path[K], j_path[K] = oK, jK
        for k in range(K, 0, -1):
            j = j_path[k]
            o_path[k - 1] = o_path[k] - (c0[k - 1] - c0[k]) - Ds[k - 1][j]
            j_path[k - 1] = BP[k][o_path[k], j]
        r_path = c0 + o_path
        edge = np.minimum(o_path, P - 1 - o_path)
        # backward pass for margins
        G = np.zeros((P, J), np.float32)
        thru = np.zeros((K + 1, P), np.float32)
        thru[K] = Fs[K].min(1)
        for k in range(K - 1, -1, -1):
            T = self.tempo_T(k)
            sh = c0[k] - c0[k + 1]
            nxt = np.full((P, J), BIG, np.float32)
            for j in range(J):
                o_new = np.arange(P) + sh + Ds[k][j]
                ok = (o_new >= 0) & (o_new < P)
                nxt[ok, j] = Ms[k][ok, j] + G[o_new[ok], j]
            G = (nxt[:, :, None] + T[None, :, :]).min(1).astype(np.float32)
            thru[k] = (Fs[k] + G).min(1)
        first = {}
        for k, bi in enumerate(bt['bar_i']): first.setdefault(bi, k)
        nbars = len(bt['bars'])
        margin = np.full(nbars, np.nan)
        for bi in range(nbars):
            k = first[bi]
            beat_frames = max(2.0, (r_path[k + 1] - r_path[k]))
            far = np.abs(np.arange(P) - o_path[k]) >= 0.3 * beat_frames
            if far.any(): margin[bi] = float(thru[k][far].min() - best_cost)
        # Step 5: snap each bar's beat 1 to its attacking stream's onset within +-60 ms
        nR = self.nR
        r_snap = r_path.astype(float).copy(); snapped = []
        W = int(round(0.06 * FPS))
        for bi in range(nbars):
            k = first[bi]
            if not (0 <= r_path[k] < nR): continue
            env = self.RVon if (bt['att_v'][k] and not bt['att_p'][k]) else (self.RPon if bt['att_p'][k] else None)
            if env is None: continue
            lo, hi = max(0, r_path[k] - W), min(nR - 1, r_path[k] + W)
            seg = env[lo:hi + 1]
            i = int(np.argmax(seg)); med = np.median(env[max(0, lo - 40):hi + 40])
            if seg[i] >= 2.0 and seg[i] >= 2 * max(med, 0.5):
                r_snap[k] = lo + i; snapped.append((bt['bars'][bi]['num'], (lo + i - r_path[k]) / FPS))
        r_snap_sec = r_snap / FPS
        for bi in range(nbars):
            k = first[bi]
            if r_snap[k] != r_path[k]: r_snap_sec[k] -= self.lat   # the snap is to a peak, which lags the attack
        r_snap_sec = np.maximum.accumulate(r_snap_sec)
        trk_t = np.append(self.t0, self.t1[-1]) + self.shift
        knots = np.stack([trk_t, r_snap_sec], 1)
        res = dict(r=r_path, r_snap=r_snap_sec, knots=knots, margin=margin, edge=edge,
                   bar_first=np.array([first[i] for i in range(nbars)]), j=j_path, best_cost=best_cost,
                   bar_num=np.array([b['num'] for b in bt['bars']]))
        np.savez(os.path.join(self.scratch, self.song, f'align_{self.tag}.npz'), **res)
        if verbose:
            print(f"{self.song} {self.variant}: {K} beats, band +-{self.band_s:.0f} s, {time.time()-t_start:.0f} s; "
                  f"path within 0.5 s of the band edge at {int(np.sum(edge < 0.5*FPS))} boundaries; snapped "
                  f"{len(snapped)} beat 1s (median {np.median([abs(s[1]) for s in snapped])*1000 if snapped else 0:.0f} ms)")
        return res


def build(song, scratch, variant='all', band_s=6.0, verbose=True):
    M = Model(song, scratch, variant, band_s)
    return M.run(verbose), M.bt


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('song'); ap.add_argument('scratch')
    ap.add_argument('--variant', default='all'); ap.add_argument('--band', type=float, default=6.0)
    a = ap.parse_args()
    build(a.song, a.scratch, a.variant, a.band)
