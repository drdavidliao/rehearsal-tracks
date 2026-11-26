#!/usr/bin/env python3
"""Write MP4s that can be watched while they render (SKILL.md, Step 10).

A plain MP4 writes its index (the moov box) last, so a partial file doesn't play until the encode ends. Every
renderer here encodes with FRAG (fragmented MP4: an empty moov first, then self-contained fragments from each
keyframe), so the file in progress opens and plays as far as it has got; then finalize() remuxes it, by stream copy
in seconds, to an ordinary MP4 with its index at the front (+faststart), the form players and uploads expect.
finalize() checks that the remux changed no stream (MD5 of each stream's packets, before and after); if any differs
it keeps the fragmented file as it was and raises.

    cmd = ['ffmpeg', ..., *mp4out.FRAG, out]; subprocess.run(cmd, check=True); mp4out.finalize(out)

    python3 mp4out.py --selftest DIR   (1) a slow piped render probed at frame 400 of 450 while ffmpeg is still
                                       writing must play; (2) a VFR video with B-frames and AAC written plain and
                                       written with FRAG + finalize() must have identical frame and start times
"""
import os, subprocess

# -flush_packets 1: without it ffmpeg holds the fragments (even the empty moov) in its output buffer, and a small or
# slow render shows 28 bytes on disk (just the ftyp box) until the buffer fills, about 2 MiB.
# delay_moov: the moov waits for the first fragment, so it can carry the edit list that hides x264's B-frame delay and
# the AAC encoder's priming. Without it every video frame came out late against the audio: by 24 ms (the priming,
# 1024 samples) on a retimed follow-along video, by 1.312 s (two whole VFR frames of B-frame delay) with the audio's
# priming handled otherwise, and finalize()'s stream copy keeps whatever the fragments say.
FRAG = ['-movflags', 'frag_keyframe+empty_moov+delay_moov+default_base_moof', '-flush_packets', '1']


def stream_md5(path):
    """MD5 of each stream's packets (video, audio), as ffmpeg's md5 muxer gives them"""
    out = []
    for sel in ('0:v', '0:a'):
        r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-map', sel + '?', '-c', 'copy', '-f', 'md5', '-'],
                           capture_output=True, text=True)
        out.append(r.stdout.strip())
    return out


def finalize(path):
    """remux a fragmented MP4 in place to a plain one with +faststart (stream copy); raises, keeping the fragmented
    file, if ffmpeg fails or any stream's packets changed"""
    tmp = path + '.faststart.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-map', '0', '-c', 'copy', '-movflags', '+faststart', tmp],
                   check=True)
    before, after = stream_md5(path), stream_md5(tmp)
    if before != after:
        os.remove(tmp)
        raise RuntimeError(f'mp4out.finalize: the remux changed a stream of {path} ({before} -> {after}); '
                           'the fragmented file is kept')
    os.replace(tmp, path)


def selftest(d):
    """two checks: (1) a slow render from a pipe, probed at frame 400 of 450 while ffmpeg still writes it, must have a
    duration; (2) the same VFR video (B-frames on, AAC audio) written plain and written with FRAG + finalize() must
    have identical frame times and stream start times"""
    import sys, time
    import numpy as np
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, 'mp4out_selftest.mp4')
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '640x360', '-r', '30',
                          '-i', '-', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=15', '-map', '0:v', '-map', '1:a',
                          '-c:v', 'libx264', '-preset', 'veryfast', '-g', '60', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                          '-shortest', *FRAG, out], stdin=subprocess.PIPE)
    probed, size = None, 0
    for k in range(450):
        p.stdin.write(np.full((360, 640, 3), (k * 7) % 256, np.uint8).tobytes())
        time.sleep(0.01)
        if k == 400:
            p.stdin.flush(); time.sleep(1.5)
            probed = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                                    capture_output=True, text=True).stdout.strip()
            size = os.path.getsize(out)
    p.stdin.close(); p.wait()
    ok1 = bool(probed) and float(probed) > 5
    print(f'(1) at frame 400 of 450, while writing: {size} bytes, probed duration {probed or "none"} s -> '
          f'{"plays" if ok1 else "FAILS"}')
    # (2) VFR stills with uneven durations, as score_video.py writes them
    lst = os.path.join(d, 'frames.ffconcat'); lines = ['ffconcat version 1.0']
    for i, dur in enumerate([0.906, 0.406, 0.811, 0.405, 1.227, 0.25, 0.9]):
        f = os.path.join(d, f'still{i}.png')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=0x{(i * 37) % 256:02x}8040:s=320x180',
                        '-frames:v', '1', f], check=True)
        lines += [f"file '{f}'", 'option framerate 1000', f'duration {dur:.3f}']
    lines += [lines[-3], 'option framerate 1000']
    open(lst, 'w').write('\n'.join(lines) + '\n')
    base = ['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-f', 'lavfi', '-i',
            'sine=frequency=440:duration=6', '-map', '0:v', '-map', '1:a', '-fps_mode', 'vfr', '-video_track_timescale',
            '1000', '-c:v', 'libx264', '-preset', 'veryfast', '-g', '30', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-t', '5']
    plain, frag = os.path.join(d, 'plain.mp4'), os.path.join(d, 'frag.mp4')
    subprocess.run(base + ['-movflags', '+faststart', plain], check=True)
    subprocess.run(base + [*FRAG, frag], check=True)
    finalize(frag)
    info = lambda f, s_: subprocess.run(['ffprobe', '-v', 'error', '-select_streams', s_, '-show_entries',
                                         'frame=pts_time:stream=start_time', '-of', 'csv=p=0', f],
                                        capture_output=True, text=True).stdout
    ok2 = info(plain, 'v:0') == info(frag, 'v:0') and info(plain, 'a:0') == info(frag, 'a:0')
    print(f'(2) VFR + B-frames + AAC, plain vs fragmented and finalized: frame and start times '
          f'{"identical" if ok2 else "DIFFER"}')
    sys.exit(0 if ok1 and ok2 else 1)


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--selftest':
        selftest(sys.argv[2])
