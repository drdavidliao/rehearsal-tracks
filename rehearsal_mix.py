#!/usr/bin/env python3
"""Mix a full set of rehearsal tracks from per-staff stems (SKILL.md Step 9.4).

    python3 rehearsal_mix.py TITLE OUT_DIR "Bass=bass.wav" "Baritone=bari.wav" "Tenor 2=t2.wav" "Tenor 1=t1.wav"
                             [--accomp "Piano=piano.wav"] [--trim "Bass=-9"] [--place "Solo=0"]
                             [--only 3d] [--featured 3] [--others -21]

List the voices from the LOWEST to the HIGHEST: the order sets the stereo and 3D
layouts. An accompaniment stem (--accomp, repeatable) is never featured and stays
at 0 dB.

Writes, for every voice V (the Chorus Connection section in parentheses, see Sections below;
a voice named Solo... gets none):
    TITLE - (V) predominant.mp3         V +3 dB, other voices -21 dB, accompaniment 0 dB
    TITLE - (V) part-left.mp3           V hard left, other voices hard right, accompaniment as exported
and once:
    TITLE - Balanced.mp3                everything at 0 dB, as exported (no panning)
    TITLE - Balanced panned.mp3         voices spread across the stereo field, lowest on the left
    TITLE - Balanced 3D, use headphones.mp3
                                        voices placed around the listener with a dummy-head HRTF

Layouts, the ones the user settled on by ear for a TTBB set (Bass, Baritone, Tenor 2, Tenor 1):
  panned  lowest to highest evenly from 45% left to 45% right (four voices: -45, -15, +15, +45),
          constant-power pan scaled so a centred voice keeps its level; accompaniment centred.
  3D      listener facing north; lowest voice rear-left (135 deg), highest rear-right (225 deg),
          the rest evenly across the front between 10 deg left and 10 deg right (four voices:
          Bass 135, Baritone 10 left, Tenor 2 10 right, Tenor 1 225); accompaniment straight
          ahead (0 deg). Ear height. MIT KEMAR dummy head, measured at 1.4 m, from the `slab`
          package (pip install slab). Loudness matched to the panned Balanced track.

Soloists: the layouts are for the choral parts. Put a solo where it belongs with --place
("Solo=0" straight ahead; "Solo 1=5R", "Solo 2=5L"); the choral parts keep the standard
layout, and in the panned track a placed voice sits proportionally (135 deg = 45%).
Chosen for a TTBB piece with one solo (Solo ahead) and one with two soloists (Solo 2 5 deg left,
Solo 1 5 deg right), without listening; the user may move them.

Sections: Chorus Connection files a track under the section named in parentheses, and shows
a track whose parenthesised name is not one of the chorus's sections to EVERYONE. A voice
that is a division of a section goes in as the section plus a suffix after the parentheses:
"Tenor 2a" -> "(Tenor 2) a", "Bass b" -> "(Bass) b". That is the default for a name ending in
a lone lower-case letter; everything else is used as it is. Override per voice with
--section "Voice=Section|suffix" ("Tenor 2a=Tenor 2|a", "Bari=Baritone|", or "Descant=|" for
no parentheses at all). The mapping is printed; confirm it with the user before handing over
the tracks, since each chorus names its sections its own way.

Stem levels: every stem's median level while sounding is printed. A stem several dB off
the others (one set's Bass came out 9 dB hot) gets --trim, applied before every mix gain.

Peaks: every mix is measured before encoding. Only if one goes over 0 dBFS are ALL of them
turned down by the same amount (the loudest lands at -1 dBFS), so the tracks keep their
loudness relative to one another. The 3D track, a headphone extra, is loudness-matched to
the panned Balanced track and then turned down on its own if it would clip.

Needs numpy and ffmpeg (with libmp3lame); slab for the 3D track (without it the 3D track is
not made, the script says so and exits 1).
"""
import re, sys, os, types, argparse, subprocess
import numpy as np

SR = 44100


def load(path):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ar', str(SR), '-ac', '2', '-f', 'f64le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float64).reshape(-1, 2).copy()


def sounding_level(x):
    m = x.mean(1); w = SR // 10; n = len(m) // w
    r = 20 * np.log10(np.sqrt((m[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-12)
    s = r[r > -45]
    return float(np.median(s)) if len(s) else float('-inf'), len(s) / 10


def pad(x, n):
    return np.vstack([x, np.zeros((n - len(x), 2))]) if len(x) < n else x[:n]


def db(g):
    return 10 ** (g / 20)


def mono(x):
    return x.mean(1)


def pan_positions(k):
    return [0.0] if k == 1 else list(np.linspace(-0.45, 0.45, k))


def azimuths(k):
    """degrees counterclockwise from straight ahead (90 = left), lowest voice first"""
    if k == 1: return [0.0]
    if k == 2: return [135.0, 225.0]
    front = [0.0] if k == 3 else list(np.linspace(10, -10, k - 2))
    return [135.0] + [a % 360 for a in front] + [225.0]


def hrir_bank():
    sys.modules.setdefault('sounddevice', types.ModuleType('sounddevice'))   # slab imports it; playback unused
    import slab
    h = slab.HRTF.kemar()
    src = np.asarray(h.sources.vertical_polar, float)

    def left_side(az):                       # 0..180, measured every 5 deg at ear height
        near = sorted(range(len(src)), key=lambda i: abs(src[i, 0] - az) + 1000 * abs(src[i, 1]))[:2]
        a, b = near
        if abs(src[a, 0] - az) < 0.01: return np.asarray(h.data[a].data, float)
        wa = abs(src[b, 0] - az) / abs(src[b, 0] - src[a, 0])       # blend the two measured neighbours
        return wa * np.asarray(h.data[a].data, float) + (1 - wa) * np.asarray(h.data[b].data, float)

    def hrir(az):
        az = az % 360
        if az <= 180: return left_side(az)
        return left_side(360 - az)[:, ::-1]  # the set is left/right symmetric: mirror the left side
    return hrir


def parse_az(txt):
    """'0', '5L', '10R', '135L' -> degrees counterclockwise from ahead (90 = left)"""
    t = txt.strip().upper()
    if t in ('0', 'AHEAD', 'C'): return 0.0
    if t[-1] in 'LR': return float(t[:-1]) % 360 if t[-1] == 'L' else (-float(t[:-1])) % 360
    return float(t) % 360


def fftconv(x, h):
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]


def section_of(n, sections):
    """(section, suffix) for a voice: --section if given; a Solo... voice has no section; a name
    ending in a lone lower-case letter ("Tenor 2a", "Bass b") is that section divided."""
    if n in sections:
        return sections[n]
    if n.lower().startswith('solo'):
        return '', ''
    m = re.fullmatch(r'(.*\d)([a-z])', n) or re.fullmatch(r'(.*\S) ([a-z])', n)
    return (m.group(1), m.group(2)) if m else (n, '')


def label(n, sections):
    sec, suf = section_of(n, sections)
    if not sec:
        return n
    return f'({sec})' + (f' {suf}' if suf else '')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('title'); ap.add_argument('out')
    ap.add_argument('voices', nargs='+', help='"Name=stem.wav", lowest voice first')
    ap.add_argument('--accomp', action='append', default=[])
    ap.add_argument('--trim', action='append', default=[], help='"Name=-9": dB applied to that stem first')
    ap.add_argument('--place', action='append', default=[],
                    help='"Solo=0", "Solo 1=5R", "Solo 2=5L": put a voice (or accompaniment) at a fixed '
                         'direction instead of the automatic layout; the other voices keep theirs')
    ap.add_argument('--section', action='append', default=[],
                    help='"Voice=Section|suffix": the Chorus Connection section (in parentheses) and the '
                         'suffix after it, e.g. "Tenor 2a=Tenor 2|a"; "Voice=|" for no section')
    ap.add_argument('--only', choices=['all', '3d'], default='all', help='write every track, or only the 3D one')
    ap.add_argument('--featured', type=float, default=3.0)
    ap.add_argument('--others', type=float, default=-21.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    trims = {k: float(v) for k, v in (t.split('=', 1) for t in a.trim)}
    placed = {k: parse_az(v) for k, v in (t.split('=', 1) for t in a.place)}
    V = [tuple(s.split('=', 1)) for s in a.voices]
    A = [tuple(s.split('=', 1)) for s in a.accomp]
    sections = {}
    for t in a.section:
        k, v = t.split('=', 1)
        if '|' not in v: v += '|'
        sections[k] = tuple(x.strip() for x in v.split('|', 1))
    for n in list(trims) + list(placed) + list(sections):
        if n not in {x for x, _ in V + A}: sys.exit(f'{n!r} is not a stem')
    st = {n: load(p).astype(np.float32) for n, p in V + A}
    N = max(len(x) for x in st.values())
    st = {n: (pad(x, N) * db(trims.get(n, 0.0))).astype(np.float32) for n, x in st.items()}
    names = [n for n, _ in V]; acc = [n for n, _ in A]

    print('stem levels while sounding (after --trim):')
    lv = {n: sounding_level(st[n]) for n in names + acc}
    ref = np.median([lv[n][0] for n in names])
    for n in names + acc:
        l, secs = lv[n]
        flag = f'   <- {l - ref:+.1f} dB from the other voices: consider --trim "{n}={-(l - ref):.0f}"' \
            if n in names and abs(l - ref) >= 4 else ''
        print(f'   {n:12s} {l:6.1f} dBFS over {secs:5.1f} s{flag}')

    # layouts: placed voices where they were put; the rest spread as usual, lowest first
    auto = [n for n in names if n not in placed]
    az = dict(zip(auto, azimuths(len(auto)))); az.update({n: placed.get(n, 0.0) for n in acc}); az.update(placed)
    signed = lambda d: d if d <= 180 else d - 360                    # + left, - right
    pan = dict(zip(auto, pan_positions(len(auto))))
    pan.update({n: float(np.clip(-signed(placed[n]) / 135 * 0.45, -0.45, 0.45)) for n in placed})
    pan.update({n: pan.get(n, 0.0) if n in placed else 0.0 for n in acc})
    side = lambda d: 'ahead' if d == 0 else (f'{d:g} deg left' if d <= 180 else f'{360 - d:g} deg right')
    print('\npanned: ' + ', '.join(f'{n} ' + ('centre' if abs(pan[n]) < 1e-9 else
                                   f'{round(abs(pan[n])*100, 1):g}% {"left" if pan[n] < 0 else "right"}') for n in names + acc))
    print('3D: ' + ', '.join(f'{n} {side(az[n])}' for n in names + acc))

    print('\nfile names (Chorus Connection section in parentheses):')
    for v in names:
        print(f'   {v:12} -> {label(v, sections)}')
    accsum = sum((st[n] for n in acc), np.zeros((N, 2), np.float32))
    mono_ = {n: mono(st[n]) for n in names + acc}

    def predominant(v):
        return accsum + sum(st[n] * np.float32(db(a.featured if n == v else a.others)) for n in names)

    def part_left(v):
        R = sum((mono_[n] for n in names if n != v), np.zeros(N, np.float32))
        return accsum + np.stack([mono_[v], R], 1)

    def balanced():
        return accsum + sum(st[n] for n in names)

    def panned():
        out = np.zeros((N, 2), np.float32)
        for n in names + acc:
            if n in acc and n not in placed:
                out += st[n]; continue                                  # accompaniment as exported
            th = (pan[n] + 1) * np.pi / 4
            out += np.outer(mono_[n], np.float32([np.sqrt(2) * np.cos(th), np.sqrt(2) * np.sin(th)]))
        return out

    missing3d = None
    try:
        hrir = hrir_bank()
    except Exception as ex:
        missing3d = f'{ex.__class__.__name__}: {ex}'
    rms = lambda x: float(np.sqrt((x.astype(np.float64) ** 2).mean()))
    pan_rms = rms(panned())

    def three_d():
        out = np.zeros((N, 2))
        for n in names + acc:
            f = hrir(az[n])
            for ch in (0, 1):
                out[:, ch] += fftconv(mono_[n].astype(np.float64), f[:, ch])[:N]
        return (out * (pan_rms / rms(out))).astype(np.float32)

    builders = {}
    for v in names:
        builders[f'{a.title} - {label(v, sections)} predominant'] = (lambda v=v: predominant(v))
        builders[f'{a.title} - {label(v, sections)} part-left'] = (lambda v=v: part_left(v))
    builders[f'{a.title} - Balanced'] = balanced
    builders[f'{a.title} - Balanced panned'] = panned
    three = f'{a.title} - Balanced 3D, use headphones'
    if missing3d is None:
        builders[three] = three_d

    # Peaks. The tracks singers switch between keep their loudness relative to one another: only if
    # one of them goes over 0 dBFS are all of them turned down, by the same amount. The 3D track is
    # a headphone extra: loudness-matched to the panned Balanced track, then turned down on its
    # own if it would clip (one set: +1.1 dBFS, taken to -1). Two passes: measure every mix, then
    # write, building one mix at a time so long pieces fit in memory.
    peaks = {k: 20 * np.log10(float(np.abs(f()).max()) + 1e-12) for k, f in builders.items()}
    worst = max(v for k, v in peaks.items() if k != three)
    gains = {k: (-(worst + 1.0) if worst > 0 else 0.0) for k in builders}
    if three in builders and peaks[three] + gains[three] > 0:
        gains[three] = -(peaks[three] + 1.0)
    write = [k for k in builders if a.only == 'all' or k == three]
    print('\npeaks before encoding, and the gain applied:')
    for k in builders:
        print(f'   {peaks[k]:+6.2f} dBFS  {gains[k]:+5.2f} dB  {k}' + ('' if k in write else '   (not written: --only 3d)'))
    for k in write:
        y = (builders[k]() * np.float32(db(gains[k]))).astype(np.float32)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-',
                        '-c:a', 'libmp3lame', '-b:a', '192k', '-joint_stereo', '1', os.path.join(a.out, k + '.mp3')],
                       input=y.tobytes(), check=True)
    print(f'\n{len(write)} track(s) written to {a.out}')
    if missing3d:
        print(f'3D track NOT made: the HRTF set could not be loaded ({missing3d}); pip install slab')
        sys.exit(1)


if __name__ == '__main__':
    main()
