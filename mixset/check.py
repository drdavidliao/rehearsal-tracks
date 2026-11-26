"""Checks on a retimed video.

    python3 -m mixset.check frames RESULT.json MP3     # every frame where planned; audio against the mp3
    python3 -m mixset.check sync VIDEO.mp4 AUDIO        # the lights against the sound

sync: per 20 s, the median of (nearest audio onset - frame change) within +-100 ms; positive =
the light leads. The number depends on the detector, so read it against the old video on its
own audio, not against score_video.py's 25-30 ms. A map built on the accompaniment left the
lights 13-18 ms later than the old videos on two sets (up to 35 ms in places): a human
singer's consonants come ahead of the piano. Correct the map per 15 s window by the difference
and render again.
"""
import json, subprocess, sys
import numpy as np, librosa
from .retime import frame_times


def dec(p):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-map', '0:a', '-ac', '1', '-ar', '22050', '-f', 'f32le', '-'],
                       capture_output=True, check=True).stdout
    return np.frombuffer(r, np.float32).astype(float)


def frames(result, mp3):
    d = json.load(open(result))
    pts, plan = frame_times(d['out']), np.array(d['planned_ms']) / 1000
    ok = len(pts) == len(plan) and np.abs(pts - plan).max() < 0.0015
    x, y = dec(mp3), dec(d['out'])
    n = min(len(x), len(y))
    a, b = x[22050 * 10:min(n, 22050 * 70)], y[22050 * 10:min(n, 22050 * 70)]
    cc = [float(np.dot(a[max(0, k):len(a) + min(0, k)], b[max(0, -k):len(b) - max(0, k)])) for k in range(-200, 201)]
    lag_ms = (int(np.argmax(cc)) - 200) / 22.05
    print(f"{d['out']}: frames {len(pts)}/{len(plan)} {'where planned' if ok else 'MISPLACED'}; audio lag {lag_ms:.1f} ms")
    return ok and abs(lag_ms) < 1


def sync(vid, aud, win=20.0):
    pts = frame_times(vid)[1:]
    y, sr = librosa.load(aud, sr=22050)
    on = librosa.onset.onset_detect(y=y, sr=sr, hop_length=110, units='time', backtrack=True)
    rows = []
    for t in pts:
        j = np.searchsorted(on, t)
        c = [on[k] - t for k in (j - 1, j) if 0 <= k < len(on) and abs(on[k] - t) <= 0.1]
        if c:
            rows.append((t, min(c, key=abs)))
    rows = np.array(rows)
    parts = []
    for w0 in np.arange(0, pts[-1] + win, win):
        m = (rows[:, 0] >= w0) & (rows[:, 0] < w0 + win)
        if m.sum() >= 5:
            parts.append(f'{int(w0)}s:{1000 * np.median(rows[m, 1]):+.0f}')
    print(f'{vid}: {1000 * np.median(rows[:, 1]):+.0f} ms ({len(rows)}/{len(pts)} changes near an onset) | ' + ' '.join(parts))
    return True


if __name__ == '__main__':
    sys.exit(0 if {'frames': frames, 'sync': sync}[sys.argv[1]](*sys.argv[2:]) else 1)
