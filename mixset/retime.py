"""Retime a variable-frame-rate follow-along video onto new audio through a time map.

    python3 -m mixset.retime OLD.mp4 knots.npy NEW.mp3 OUT.mp4 [--lag 1.0]

knots.npy: old-audio seconds -> new Balanced-timeline seconds (mixset.timemap build); --lag: how
far this mp3 runs behind that timeline (a Predominant mix's 1.000 s lead). Each old frame starts
at map(t) + lag, past the knots at slope 1; frames squeezed into one millisecond keep the later,
as score_video.py does. Encoded as score_video.py encodes, over the new mp3 (--tune film for a
dance composite, 30 fps of motion). No frame is redrawn:
about 7 s a video. Prints JSON with the planned frame times, for mixset.check.
"""
import argparse, json, os, shutil, subprocess, tempfile
import numpy as np


def fmap(K, t):
    t = np.asarray(t, float)
    y = np.interp(t, K[:, 0], K[:, 1])
    y = np.where(t < K[0, 0], K[0, 1] + (t - K[0, 0]), y)
    return np.where(t > K[-1, 0], K[-1, 1] + (t - K[-1, 0]), y)


def frame_times(mp4):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'frame=pts_time',
                          '-of', 'csv=p=0', mp4], capture_output=True, text=True, check=True).stdout.split()
    return np.array([float(p.strip(',')) for p in out if p.strip(',')])


def duration(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                capture_output=True, text=True, check=True).stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('old'); ap.add_argument('knots'); ap.add_argument('mp3'); ap.add_argument('out')
    ap.add_argument('--lag', type=float, default=0.0); ap.add_argument('--crf', type=int, default=20)
    ap.add_argument('--tune', default='stillimage', help='film for a video with motion (a dance composite)')
    a = ap.parse_args()
    K = np.load(a.knots)
    pts = frame_times(a.old)
    end_ms = int(round(duration(a.mp3) * 1000))
    tmpd = tempfile.mkdtemp(prefix='retime_')
    try:
        subprocess.run(['ffmpeg', '-v', 'error', '-i', a.old, '-fps_mode', 'passthrough', f'{tmpd}/%06d.png'], check=True)
        files = sorted(f for f in os.listdir(tmpd) if f.endswith('.png'))
        assert len(files) == len(pts), (len(files), len(pts))
        ms = np.clip(np.round((fmap(K, pts) + a.lag) * 1000).astype(int), 0, end_ms - 1)
        ms[0] = 0
        segs = []
        for m, f in zip(ms, files):
            if segs and segs[-1][0] >= m:
                segs[-1] = (segs[-1][0], f)
            else:
                segs.append((int(m), f))
        lines = ['ffconcat version 1.0']
        for k, (m, f) in enumerate(segs):
            nxt = segs[k + 1][0] if k + 1 < len(segs) else end_ms
            lines += [f"file '{tmpd}/{f}'", 'option framerate 1000', f'duration {(nxt - m) / 1000:.3f}']
        lines += [f"file '{tmpd}/{segs[-1][1]}'", 'option framerate 1000']
        open(f'{tmpd}/frames.ffconcat', 'w').write('\n'.join(lines) + '\n')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', f'{tmpd}/frames.ffconcat',
                        '-i', a.mp3, '-map', '0:v', '-map', '1:a', '-fps_mode', 'vfr', '-video_track_timescale', '1000',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-tune', a.tune, '-g', '30', '-crf', str(a.crf),
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-t', f'{end_ms / 1000:.3f}',
                        '-movflags', '+faststart', a.out], check=True)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    print(json.dumps({'out': a.out, 'frames_in': len(pts), 'frames_out': len(segs), 'planned_ms': [s[0] for s in segs]}))


if __name__ == '__main__':
    main()
