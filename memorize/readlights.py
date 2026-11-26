"""Read which syllables a lyric video lights, frame by frame (SKILL.md 10.1 videos), so the memorization
lesson can redraw the same lights over its own faded sheet.

    python3 -m memorize.readlights PLAN.json VIDEO.mp4 OUT.json
For each video frame (one per change of lights, variable frame rate): its time and the token ids whose
box is tinted. A box is lit when the mean colour of its band above the text differs from white. The
frame is then redrawn with lyric_sheet.draw_frame and compared with the video frame (mean abs diff).
"""
import sys, json, subprocess, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lyric_sheet as ls


def frames(video, W=1920, H=1080):
    pts = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'frame=pts_time',
                          '-of', 'csv=p=0', video], capture_output=True, text=True).stdout.replace(',', '').split()
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', video, '-fps_mode', 'passthrough', '-f', 'rawvideo',
                          '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    for t in pts:
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        yield float(t), np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    p.wait()


def main(plan, video, out):
    S = ls.Sheet(plan)
    L, fs, lead = ls.layouts(S)['screen']
    k = min(1920 / L.W, 1080 / L.H)
    ox = (1920 - L.W * k) / 2
    # sample strip: the band's top part, above the letters' x-height, inside the box
    probes = {}
    for tid, bx in L.boxes.items():
        rs = []
        for x0, y, x1 in bx:
            top = y - L.fs * 0.86
            # inset from the box's sides: a neighbour's highlight can spill a few pixels onto a narrow box ("a|round")
            a, b = ox + x0 * k, ox + x1 * k
            m = min(5.0, 0.25 * (b - a))
            rs.append((int(a + m), int(b - m), int((top + 0.5) * k), int((top + L.fs * 0.12) * k)))
        probes[tid] = rs
    rec, worst = [], 0
    for i, (t, img) in enumerate(frames(video)):
        lit = []
        for tid, rs in probes.items():
            d = max(255 - img[y0:y1 + 1, a:b].reshape(-1, 3).mean(0).min() for a, b, y0, y1 in rs)
            if d > 25:
                lit.append(tid)
        rec.append(dict(t=t, lit=lit))
    json.dump(dict(video=os.path.basename(video), frames=rec), open(out, 'w'), indent=0)
    print(f'{len(rec)} frames; lit counts {sorted(set(len(r["lit"]) for r in rec))}')


if __name__ == '__main__':
    main(*sys.argv[1:4])
