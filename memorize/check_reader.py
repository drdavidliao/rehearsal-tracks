"""Compare two readings of a lyric video's lights (memorize/readlights.py) frame by frame and, where they differ,
measure how much of each disputed syllable's box is tinted: a real light tints the whole width of the band, a
neighbour's highlight spilling over only a few pixels at one side.
    python3 -m memorize.check_reader PLAN VIDEO A.json B.json"""
import sys, json, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lyric_sheet as ls
from memorize.readlights import frames


def main(plan, video, a, b):
    S = ls.Sheet(plan)
    L, fs, lead = ls.layouts(S)['screen']
    k = min(1920 / L.W, 1080 / L.H)
    ox = (1920 - L.W * k) / 2
    tok = {t['id']: t for t in S.W.tokens}
    A, B = json.load(open(a))['frames'], json.load(open(b))['frames']
    diff = {i: set(x['lit']) ^ set(y['lit']) for i, (x, y) in enumerate(zip(A, B)) if set(x['lit']) != set(y['lit'])}
    for i, (t, img) in enumerate(frames(video)):
        if i not in diff:
            continue
        for tid in sorted(diff[i]):
            for x0, y, x1 in L.boxes[tid]:
                top = y - L.fs * 0.86
                c0, c1 = int(ox + x0 * k), int(ox + x1 * k)
                strip = img[int((top + 0.5) * k):int((top + L.fs * 0.12) * k) + 1, c0:c1].astype(float)
                cols = (255 - strip.min(2)).mean(0) > 25
                who = 'A' if tid in A[i]['lit'] else 'B'
                print(f"{t:8.3f}s  {tok[tid]['text']!r:>12} bar {tok[tid]['bar']:>3}  lit only in {who}; box {c1 - c0} px, "
                      f"tinted columns {cols.sum()} ({cols.mean():.0%}) at {np.flatnonzero(cols)[[0, -1]].tolist() if cols.any() else '-'}")


if __name__ == '__main__':
    main(*sys.argv[1:5])
