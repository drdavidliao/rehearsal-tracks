"""Sync a choreography video, filmed to a different recording, to a follow-along score video.

    python3 -m voiceshift.dancesync DANCE.mp4 SCORE_VIDEO.mp4 MIX.mp3 --accomp ACCOMP.mp3 \
        --bar1 1.03 --beat 0.5 --stack "OUT stacked.mp4" --overlay "OUT over dance.mp4" [--white-opacity 0.75]

1. The dance recording's tempo: beat tracker, straight-line fit of its beats.
2. A straight map, dance time = c + r * (our time - bar1): r near (dance beat / our beat), c and r
   fitted by the dance audio's onset strength at our accompaniment's onset times.  The search range
   for r is set from the beat periods: a range set by guess once missed it and fitted the edge.
3. Corrected by the beats: each dance beat is paired with our nearest grid beat; the residual is
   smoothed (median over +-8 beats) and sampled every 8 s; a piecewise-linear map through those
   knots.  On a ChoreoTrax demo at 120.9 bpm against a 120 bpm practice track, the straight map left
   the opening 110 ms off; the piecewise one put every 20 s within +-11 ms of the grid, at speeds of
   0.986-1.004.
4. Rendered with ONE setpts expression (output time as a piecewise function of the frame's own time),
   then resampled to 29.97 fps.  Cutting into segments, retiming each and joining them drifted to
   130 ms by the end: each cut rounds to a frame.
5. Checked on the rendered file: for dance frames at 20/40/60/80% of the piece, the output frame that
   matches best (pixel difference) against where the map puts it.  Expect one frame of seek rounding.

Layouts: --stack puts the dance on top and the score video below (1920x2160).  --overlay puts the
score over the dance at 1920x1080 with the score's white (and near-white, for compression noise)
at --white-opacity and its ink opaque: opacity 1 for channels below 200, ramping to --white-opacity
above 235.  At 0.75 the score stays fully legible; dancers in a white studio show as faint figures.
The audio is MIX.mp3; re-mux a new mix later with -c:v copy, the picture does not depend on it.
"""
import argparse
import subprocess

import numpy as np


def load(path, sr=22050):
    """Any audio or video file's sound, mono, via ffmpeg (soundfile cannot open an mp4)."""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def beats(y, sr=22050, bpm=120):
    import librosa
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    _, b = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=256, start_bpm=bpm, tightness=800, units='time')
    return b


def fit_map(dance, accomp, bar1, beat, sr=22050):
    import librosa
    db = beats(dance, sr, 60 / beat)
    A = np.vstack([np.arange(len(db)), np.ones(len(db))]).T
    dperiod = float(np.linalg.lstsq(A, db, rcond=None)[0][0])
    r0 = dperiod / beat
    print(f'dance recording: beat {dperiod:.5f} s ({60 / dperiod:.2f} bpm); ours {beat:.5f} s; ratio about {r0:.4f}')
    hop = 128
    ed = librosa.onset.onset_strength(y=dance, sr=sr, hop_length=hop)
    td = np.arange(len(ed)) * hop / sr
    on = librosa.onset.onset_detect(y=accomp, sr=sr, units='time', hop_length=hop)
    on = on[on > bar1]
    best = None
    for r in np.arange(r0 - 0.004, r0 + 0.0041, 0.0002):
        for c in np.arange(-2.0, 6.0, 0.004):
            s = np.interp(c + (on - bar1) * r, td, ed).mean()
            if best is None or s > best[0]:
                best = (s, r, c)
    _, r, c = best
    print(f'straight map: dance = {c:.3f} + {r:.4f} * (ours - {bar1})')
    # piecewise correction from the beats
    t = bar1 + (db - c) / r
    k = np.round((t - bar1) / beat)
    g = bar1 + beat * k
    keep = np.r_[True, np.diff(k) > 0]
    g, b = g[keep], db[keep]
    res = b - (c + r * (g - bar1))
    sm = np.array([np.median(res[max(0, i - 8):i + 9]) for i in range(len(res))])
    T = np.arange(0.0, len(accomp) / sr + 8.0, 8.0)
    D = c + r * (T - bar1) + np.interp(T, g, sm)
    after = b - np.interp(g, T, D)
    for s in range(0, int(T[-1]), 20):
        sel = (g >= s) & (g < s + 20)
        if sel.any():
            print(f'   {s:3d}-{s + 20:3d} s: dance beats {1000 * np.median(after[sel]):+.0f} ms from our grid')
    sp = np.diff(D) / np.diff(T)
    print(f'speeds {sp.min():.4f}-{sp.max():.4f}')
    return T, D


def setpts_expr(T, D):
    terms = []
    for i in range(len(T) - 1):
        s = (T[i + 1] - T[i]) / (D[i + 1] - D[i])
        lo = '-1e9' if i == 0 else f'{D[i]:.5f}'
        hi = '1e9' if i == len(T) - 2 else f'{D[i + 1]:.5f}'
        terms.append(f'gte(T\\,{lo})*lt(T\\,{hi})*({T[i]:.5f}+(T-{D[i]:.5f})*{s:.7f})')
    return '+'.join(terms)


def duration(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                capture_output=True, text=True).stdout)


def render(dance, score, mix, expr, out, mode, opacity):
    dur = duration(mix)
    fit = f'fps=30000/1001,scale=1920:1080,tpad=stop_mode=clone:stop_duration=5,trim=duration={dur},setsar=1'
    top = f"[0:v]setpts='({expr})/TB',{fit}[d]"
    bot = f'[1:v]{fit}[s]'
    if mode == 'stack':
        fc = f'{top};{bot};[d][s]vstack=inputs=2[v]'
    else:
        lo = int(round(255 * opacity))
        mn = 'min(min(r(X,Y),g(X,Y)),b(X,Y))'
        alpha = f"if(lt({mn},200),255,if(gt({mn},235),{lo},255-{255 - lo}*({mn}-200)/35))"
        fc = f"{top};{bot[:-3]},format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{alpha}'[s];[d][s]overlay=format=auto[v]"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', dance, '-i', score, '-i', mix, '-filter_complex', fc,
                    '-map', '[v]', '-map', '2:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
                    '-pix_fmt', 'yuv420p', '-g', '60', '-c:a', 'aac', '-b:a', '192k', '-shortest', out], check=True)


def check(dance, out, T, D, mode):
    """Find source dance frames in the output.  In the stacked video, the top half; in the overlay,
    the bottom 40% of the frame (below the systems on these screens), where the score adds only an
    even wash of white that does not move the best match."""
    W, H = 320, 180
    def frames(path, t0, n, region):
        crops = {'full': '', 'top': 'crop=1920:1080:0:0,', 'low': 'crop=1920:432:0:648,'}
        vf = crops[region] + f'scale={W}:{H},format=gray'
        r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(t0, 0):.3f}', '-i', path, '-frames:v', str(n),
                            '-vf', vf, '-f', 'rawvideo', '-'], capture_output=True)
        f = np.frombuffer(r.stdout, np.uint8).reshape(-1, H, W).astype(float)
        return (f - f.mean(axis=(1, 2), keepdims=True)) / (f.std(axis=(1, 2), keepdims=True) + 1e-6)
    fps = 30000 / 1001
    span = duration(dance)
    for frac in (0.2, 0.4, 0.6, 0.8):
        d = frac * span
        src = frames(dance, d, 1, 'full' if mode == 'stack' else 'low')[0]
        t = float(np.interp(d, D, T))
        got = frames(out, t - 0.3, 19, 'top' if mode == 'stack' else 'low')
        e = [np.abs(o - src).mean() for o in got]
        j = int(np.argmin(e))
        print(f'   dance {d:6.1f} s: expected at {t:7.3f} s, found {1000 * ((t - 0.3) + j / fps - t):+.0f} ms '
              f'away (one frame is 33 ms)')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dance'); ap.add_argument('score_video'); ap.add_argument('mix')
    ap.add_argument('--accomp', required=True, help='our accompaniment track (its onsets fit the map)')
    ap.add_argument('--bar1', type=float, required=True); ap.add_argument('--beat', type=float, required=True)
    ap.add_argument('--stack'); ap.add_argument('--overlay')
    ap.add_argument('--white-opacity', type=float, default=0.75)
    a = ap.parse_args()
    T, D = fit_map(load(a.dance), load(a.accomp), a.bar1, a.beat)
    expr = setpts_expr(T, D)
    for mode, out in (('stack', a.stack), ('overlay', a.overlay)):
        if out:
            render(a.dance, a.score_video, a.mix, expr, out, mode, a.white_opacity)
            print(f'wrote {out}')
            check(a.dance, out, T, D, mode)


if __name__ == '__main__':
    main()
