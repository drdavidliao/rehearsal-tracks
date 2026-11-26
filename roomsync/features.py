"""Features on a 512-sample grid at 22.05 kHz (23.2 ms frames), for the room and for the human-sung set (DESIGN.md Steps 1-2).

    python3 features.py SONG SCRATCH        # writes SCRATCH/SONG/features.npz and prints the clock check

Room (from separate.sh's htdemucs_ft stems): onset strength of the vocals (V_on), the piano = Other + Bass (A_on) and
the drums (D_on); chroma (CQT) of the vocals (V_ch) and the piano (P_ch); vocal activity (dB over its noise floor).
The human-sung set, on the player map's clock: the same from the map's own stems (the voices summed; 'I' is the accompaniment).
Score templates on the human-sung set's grid: the voices' and the piano's pitch classes sounding at each frame.

Clock check (F4): the player map's voice attacks as a pulse train against the human-sung vocal onset envelope, and the
piano's attacks against the accompaniment's, lag searched +-2 s. The onset detector peaks about 70 ms after an
attack on every stream, so the voices' lag must be 0-120 ms and the piano's within 60 ms of it, each with a clear
peak, since the map's stems define its clock; otherwise it stops. The Balanced file (the clock the benchmark and the
build folders use) is measured the same way against the voices: Balanced seconds = map seconds + balanced_shift.
"""
import sys, os, json
import numpy as np, soundfile as sf, librosa
from scipy.ndimage import uniform_filter1d, median_filter

SR, HOP = 22050, 512
FPS = SR / HOP
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import beat_table


def load(path):
    y, sr = librosa.load(path, sr=SR, mono=True)
    return y


def onset(y):
    o = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    return local_z(o)


def local_z(x, win_s=10.0):
    w = int(win_s * FPS)
    m = uniform_filter1d(x, w, mode='nearest')
    s = np.sqrt(np.maximum(uniform_filter1d((x - m) ** 2, w, mode='nearest'), 1e-12))
    return np.clip((x - m) / s, -2, 8).astype(np.float32)


def chroma(y):
    c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP, norm=None)
    e = c.sum(0)
    floor = np.percentile(e, 20) * 2 + 1e-9
    c = c / np.maximum(np.linalg.norm(c, axis=0, keepdims=True), 1e-9)
    c[:, e < floor] = 0               # below the noise floor: no pitch evidence
    return c.astype(np.float32)


def activity(y):
    r = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
    db = 20 * np.log10(r + 1e-9)
    floor = np.percentile(db, 10)
    return np.clip((db - floor - 12) / 12, -1, 1).astype(np.float32)   # -1 silent .. +1 clearly sounding


def template(notes, n):
    t = np.zeros((12, n), np.float32)
    for (a, b, m) in notes:
        i0, i1 = int(round(a * FPS)), max(int(round(a * FPS)) + 1, int(round(b * FPS)))
        if i1 <= 0 or i0 >= n: continue
        t[int(m) % 12, max(0, i0):min(n, i1)] += 1
    nrm = np.linalg.norm(t, axis=0, keepdims=True)
    return (t / np.maximum(nrm, 1e-9)).astype(np.float32)


def pulse(times, n):
    p = np.zeros(n, np.float32)
    for t in times:
        i = int(round(t * FPS))
        if 0 <= i < n: p[i] = 1
    return uniform_filter1d(p, 3) * 3


def lag_of(train, env, max_s=2.0):
    """Lag (s) of env behind train: env(t + lag) ~ train(t). Returns lag, peak, margin over the best lag outside +-0.1 s."""
    L = int(max_s * FPS)
    e = np.clip(env, 0, None)
    n = min(len(train), len(e)); train, e = train[:n], e[:n]
    a = (train - train.mean()); b = (e - e.mean())
    cs = []
    for l in range(-L, L + 1):
        if l >= 0: c = np.dot(a[:len(a) - l], b[l:len(a)])
        else: c = np.dot(a[-l:], b[:len(b) + l])
        cs.append(c)
    cs = np.array(cs) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
    i = int(np.argmax(cs)); lags = np.arange(-L, L + 1) / FPS
    out = np.abs(lags - lags[i]) > 0.1
    return float(lags[i]), float(cs[i]), float(cs[i] - cs[out].max())


def main(song, scratch):
    cfg = json.load(open(os.path.join(HERE, 'songs.json')))[song]
    d = cfg['song_dir']
    out_dir = os.path.join(scratch, song); os.makedirs(out_dir, exist_ok=True)
    bt = beat_table(cfg)
    mp = bt['mp']
    # room
    sd = os.path.join(scratch, cfg['stems_dir']); pre = cfg['stem_prefix']
    st = {k: load(os.path.join(sd, f'{pre}_({k})_htdemucs_ft.wav')) for k in ('Vocals', 'Drums', 'Bass', 'Other')}
    pia = st['Other'] + st['Bass']
    R = dict(V_on=onset(st['Vocals']), A_on=onset(pia), D_on=onset(st['Drums']),
             V_ch=chroma(st['Vocals']), P_ch=chroma(pia), act=activity(st['Vocals']))
    nR = min(len(R['V_on']), R['V_ch'].shape[1])
    R = {k: (v[..., :nR]) for k, v in R.items()}
    # the human-sung set, from the map's own stems
    voc = None
    for k, rel in mp['stems'].items():
        if k == 'I': continue
        y = load(os.path.join(d, rel))
        voc = y if voc is None else (voc[:len(y)] + y[:len(voc)])
    acc = load(os.path.join(d, mp['stems']['I']))
    n = min(len(voc), len(acc)); voc, acc = voc[:n], acc[:n]
    C = dict(V_on=onset(voc), A_on=onset(acc), V_ch=chroma(voc), P_ch=chroma(acc), act=activity(voc))
    nC = min(len(C['V_on']), C['V_ch'].shape[1])
    C = {k: v[..., :nC] for k, v in C.items()}
    T = dict(V_t=template(bt['notes_v'], nC), P_t=template(bt['notes_p'], nC))
    # clock checks
    att_v = sorted({round(n_['start'], 3) for n_ in mp['notes']})
    att_p = sorted({round(a, 3) for a, b, m in bt['notes_p']})
    cv = lag_of(pulse(att_v, nC), C['V_on']); cp = lag_of(pulse(att_p, nC), C['A_on'])
    bal = load(os.path.join(d, cfg['balanced']))
    cb = lag_of(pulse(att_v, nC), onset(bal)[:nC])
    rep = dict(map_vs_voices=cv, map_vs_accompaniment=cp, map_vs_balanced=cb, frames_room=nR, frames_tracks=nC)
    print(json.dumps(rep, indent=1))
    # the onset detector peaks ~70 ms after an attack (measured: +70 ms on both songs' voices), the same on every
    # stream, so only lags relative to the voices' mean anything
    ok = 0 <= cv[0] <= 0.12 and abs(cp[0] - cv[0]) <= 0.06 and cv[2] >= 0.02 and cp[2] >= 0.02
    if not ok:
        print('CLOCK CHECK FAILED: the map does not line up with its own stems; stop.'); sys.exit(1)
    if cb[2] < 0.02:
        print('CLOCK CHECK FAILED: the Balanced file\'s lag is unclear; stop.'); sys.exit(1)
    np.savez_compressed(os.path.join(out_dir, 'features.npz'),
                        **{'R_' + k: v for k, v in R.items()}, **{'C_' + k: v for k, v in C.items()},
                        **{'T_' + k: v for k, v in T.items()}, balanced_shift=cb[0] - cv[0])
    rep['balanced_shift'] = cb[0] - cv[0]
    print('Balanced seconds = map seconds %+.3f' % rep['balanced_shift'])
    json.dump(rep, open(os.path.join(out_dir, 'clock.json'), 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
