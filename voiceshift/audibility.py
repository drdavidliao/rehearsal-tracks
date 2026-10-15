"""How audible a voice is over the accompaniment, masking included; and the gain that restores the
audibility a reference mix had.

    python3 -m voiceshift.audibility ACCOMP NEW_STEM REF_STEM [--new-gain 3] [--accomp-gain 3.45] [--ref-gain 0]

Critical bands (0.5 Bark), 46 ms frames.  The accompaniment's excitation is spread across bands
(+25 dB/Bark below, -10 dB/Bark above: masking spreads upward); in each band the voice's audible
share is E_v / (E_v + masker), weighted by the voice's specific loudness (E^0.23), averaged over the
frames where the voice sounds.  Prints both audibilities and the voice gain (dB, relative to the
accompaniment) that makes the new one match the reference.

Use: a part moved an octave down lands in the piano's register and is masked more at the same level
ratio.  On an SSA set revoiced to TTB, every part needed +1.25-1.5 dB against the piano to be as
audible as the SSA original (with voices and accompaniment at 0 dB, as the publisher mixed them);
since it was the same for every part, the piano came down 1.5 dB instead.
"""
import argparse

import numpy as np
import soundfile as sf

SR, N, HOP = 44100, 2048, 1024


def _bank():
    fr = np.fft.rfftfreq(N, 1 / SR)
    bark = 13 * np.arctan(0.00076 * fr) + 3.5 * np.arctan((fr / 7500) ** 2)
    edges = np.arange(0, 24.5, 0.5)
    idx = np.digitize(bark, edges) - 1
    z = (edges[:-1] + edges[1:]) / 2
    dz = z[None, :] - z[:, None]
    S = 10 ** (np.where(dz >= 0, -10 * dz, 25 * dz) / 10)
    return idx, len(edges) - 1, S


IDX, NB, SPREAD = _bank()


def load(path):
    if path.endswith('.wav') or path.endswith('.aiff') or path.endswith('.flac'):
        x, sr = sf.read(path, always_2d=True)
        m = x.mean(1)
    else:
        import librosa
        m, sr = librosa.load(path, sr=SR, mono=True)
    if sr != SR:
        import librosa
        m = librosa.resample(m, orig_sr=sr, target_sr=SR)
    return m


def bands(m):
    import librosa
    X = np.abs(librosa.stft(m, n_fft=N, hop_length=HOP)) ** 2
    E = np.zeros((NB, X.shape[1]))
    for b in range(NB):
        E[b] = X[IDX == b].sum(0)
    return E


def audibility(Ev, Ep, voice_db=0.0, accomp_db=0.0):
    n = min(Ev.shape[1], Ep.shape[1])
    Ev = Ev[:, :n] * 10 ** (voice_db / 10)
    M = SPREAD.T @ (Ep[:, :n] * 10 ** (accomp_db / 10))
    share = Ev / (Ev + M + 1e-12)
    w = (Ev + 1e-12) ** 0.23
    a = (share * w).sum(0) / w.sum(0)
    on = Ev.sum(0) > 1e-3 * Ev.sum(0).max()
    return float(a[on].mean())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('accomp'); ap.add_argument('new'); ap.add_argument('ref')
    ap.add_argument('--new-gain', type=float, default=0.0, help='voice gain in the new mix, dB')
    ap.add_argument('--accomp-gain', type=float, default=0.0, help='accompaniment gain in the new mix, dB')
    ap.add_argument('--ref-gain', type=float, default=0.0, help='voice gain in the reference mix (accompaniment at 0 dB)')
    a = ap.parse_args()
    Ep = bands(load(a.accomp))
    En, Er = bands(load(a.new)), bands(load(a.ref))
    ar = audibility(Er, Ep, a.ref_gain)
    an = audibility(En, Ep, a.new_gain, a.accomp_gain)
    gs = np.arange(-6, 15.01, 0.25)
    need = gs[int(np.argmin([abs(audibility(En, Ep, a.new_gain + g, a.accomp_gain) - ar) for g in gs]))]
    print(f'audibility: reference {ar:.3f}, new {an:.3f}; the new voice needs {need:+.2f} dB against the '
          f'accompaniment to match')


if __name__ == '__main__':
    main()
