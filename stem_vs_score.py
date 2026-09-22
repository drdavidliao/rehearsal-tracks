#!/usr/bin/env python3
"""Check exported audio stems against the MusicXML they were rendered from.

    python3 stem_vs_score.py score.musicxml "Tenor 1=T1.wav" "Tenor 2=T2.wav" ...
        [--thresh -50] [--gap 2.0] [--tol 1.5]

Each argument after the score pairs a part name (as in <part-name>) with its
stem. For every part the script lists where the score has notes and where it
rests, converts beats to seconds with the score's tempo marks, lines the score
up with the audio, and reports, by bar number:

  SILENT  - a written phrase (or run of phrases) with next to no sound in the
            stem: a renderer that stopped, or a staff exported empty
  EXTRA   - a written rest (at least --gap s long once the slack is taken
            off) that mostly sounds in the stem: audio leaked in from another
            staff

It cannot tell apart two staves that sing the same rhythm (a stem filed under
the wrong name in homophonic writing passes); the checksum comparison in the
stem checks catches exact copies. Repeats, D.S. and D.C. are not expanded, so
a score that uses them reports everything after the first jump; check against
a copy with the repeats written out.

Alignment: a straight-line map from score seconds to audio seconds, fitted to
the onsets of every part's phrases. That absorbs the lead-in silence and a
uniformly faster or slower playback, but not a ritard or fermata that playback
stretches more than the file says; --tol (seconds of slack at every phrase edge)
covers most of that. A phrase counts as missing only when under 10% of its
middle sounds, and a rest as leaked only when over 30% of its middle sounds,
so breaths, reverb tails and short rests do not trigger anything.

Needs numpy and ffmpeg on the PATH.
"""
import sys, subprocess, argparse
import xml.etree.ElementTree as ET
import numpy as np

HOP = 0.05   # seconds per envelope frame


def load_score(path):
    root = ET.parse(path).getroot()
    names = {sp.get('id'): (sp.findtext('part-name') or '').strip()
             for sp in root.iter('score-part')}
    parts, bar_starts, tempos = {}, None, []
    for pi, part in enumerate(root.findall('part')):
        div, pos, spans, starts = 1, 0.0, [], []
        for m in part.findall('measure'):
            starts.append((pos, m.get('number')))
            t, mx = pos, pos
            for e in m:
                if e.tag == 'attributes' and e.find('divisions') is not None:
                    div = int(e.findtext('divisions'))
                elif e.tag in ('direction', 'sound'):
                    s = e if e.tag == 'sound' else e.find('sound')
                    if pi == 0 and s is not None and s.get('tempo'):
                        off = e.findtext('offset')
                        tempos.append((t + (int(off) / div if off else 0.0), float(s.get('tempo'))))
                elif e.tag == 'backup':
                    t -= int(e.findtext('duration')) / div
                elif e.tag == 'forward':
                    t += int(e.findtext('duration')) / div
                elif e.tag == 'note':
                    if e.find('grace') is not None:
                        continue
                    d = int(e.findtext('duration') or 0) / div
                    if e.find('chord') is not None:
                        continue
                    if e.find('rest') is None and d > 0:
                        spans.append((t, t + d))
                    t += d
                mx = max(mx, t)
            pos = mx
        spans.sort()
        merged = []
        for a, b in spans:
            if merged and a <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        parts[names.get(part.get('id'), part.get('id'))] = merged
        if bar_starts is None:
            bar_starts = starts + [(pos, 'end')]
    tempos.sort(key=lambda bt: bt[0])          # stable: keeps file order at equal positions
    if not tempos or tempos[0][0] > 0.0:
        tempos.insert(0, (0.0, tempos[0][1] if tempos else 120.0))
    return parts, bar_starts, tempos


def beats_to_sec(b, tempos):
    s, (b0, q0) = 0.0, tempos[0]
    for b1, q1 in tempos[1:]:
        if b <= b1:
            break
        s += (b1 - b0) * 60.0 / q0
        b0, q0 = b1, q1
    return s + (b - b0) * 60.0 / q0


def envelope(wav, thresh):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', wav, '-ac', '1', '-ar', '8000',
                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    w = int(8000 * HOP)
    n = len(a) // w
    rms = np.sqrt(np.mean(a[:n * w].reshape(n, w) ** 2, axis=1) + 1e-20)
    return 20 * np.log10(rms) > thresh


def runs(mask, value=True):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i] == value:
            j = i
            while j < n and mask[j] == value:
                j += 1
            out.append((i * HOP, j * HOP))
            i = j
        else:
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('score')
    ap.add_argument('pairs', nargs='+', help='"Part name=stem.wav"')
    ap.add_argument('--thresh', type=float, default=-50.0, help='dBFS; quieter counts as silent')
    ap.add_argument('--gap', type=float, default=2.0, help='shortest rest (after slack) worth judging (s)')
    ap.add_argument('--tol', type=float, default=1.5, help='slack at every phrase edge (s)')
    a = ap.parse_args()

    parts, bars, tempos = load_score(a.score)
    stems = {}
    for p in a.pairs:
        name, wav = p.split('=', 1)
        if name not in parts:
            sys.exit(f'no part named {name!r}; the score has {sorted(parts)}')
        stems[name] = envelope(wav, a.thresh)

    # phrase onsets: score (seconds at the written tempo) and audio
    sc = {n: [(beats_to_sec(x, tempos), beats_to_sec(y, tempos)) for x, y in parts[n]] for n in stems}
    au = {n: [r for r in runs(stems[n]) if r[1] - r[0] >= 0.3] for n in stems}
    firsts = [(sc[n][0][0], au[n][0][0]) for n in stems if sc[n] and au[n]]
    if not firsts:
        sys.exit('no part has both notes in the score and sound in its stem')
    off = float(np.median([y - x for x, y in firsts]))
    scale = 1.0
    for _ in range(3):                       # refit on phrase onsets that pair up
        pairs = []
        for n in stems:
            ons = np.array([r[0] for r in au[n]])
            if not len(ons):
                continue
            for x, _y in sc[n]:
                g = off + scale * x
                k = int(np.argmin(np.abs(ons - g)))
                if abs(ons[k] - g) < 3.0:
                    pairs.append((x, ons[k]))
        if len(pairs) >= 4:
            X = np.array(pairs)
            scale, off = np.polyfit(X[:, 0], X[:, 1], 1)
    to_audio = lambda s: off + scale * s

    bar_sec = [(to_audio(beats_to_sec(b, tempos)), num) for b, num in bars]
    def bar_at(t):
        cur = bar_sec[0][1]
        for s, num in bar_sec:
            if s <= t + 1e-6 and num != 'end':
                cur = num
        return cur
    fmt = lambda t: f'{int(t // 60)}:{t % 60:04.1f}'

    print(f'alignment: audio = {off:+.2f} s + {scale:.4f} x score time '
          f'({len(pairs) if len(pairs) >= 4 else 0} phrase onsets fitted)')
    problems = 0
    for n in stems:
        mask = stems[n]
        L = len(mask)
        found = []
        # SILENT: judge each written phrase as a whole; a phrase whose middle is
        # (almost) soundless is missing, and consecutive missing phrases merge
        miss = []
        for x, y in sc[n]:
            s0, s1 = to_audio(x), to_audio(y)
            edge = min(a.tol, 0.25 * (s1 - s0))
            i0, i1 = int((s0 + edge) / HOP), int((s1 - edge) / HOP)
            if i1 - i0 < int(0.5 / HOP):
                continue                     # too short to judge
            cov = float(mask[max(i0, 0):min(i1, L)].mean()) if i0 < L else 0.0
            if cov < 0.1:
                if miss and miss[-1][2]:
                    miss[-1][1] = s1
                else:
                    miss.append([s0, s1, True])
            elif miss:
                miss[-1][2] = False
        for t0, t1, _ in miss:
            found.append(('SILENT', t0, t1))
        # EXTRA: judge each written rest (including before the first note and
        # after the last) the same way; a rest whose middle mostly sounds is a leak
        edges = [(to_audio(x), to_audio(y)) for x, y in sc[n]]
        rests, prev = [], 0.0
        for s0, s1 in edges:
            rests.append((prev, s0)); prev = s1
        rests.append((prev, L * HOP))
        for r0, r1 in rests:
            i0, i1 = int((r0 + a.tol) / HOP), int((r1 - a.tol) / HOP)
            if (i1 - i0) * HOP < a.gap or i0 >= L:
                continue
            seg = mask[max(i0, 0):min(i1, L)]
            if seg.mean() > 0.3:
                on = np.flatnonzero(seg)
                found.append(('EXTRA ', (max(i0, 0) + on[0]) * HOP, (max(i0, 0) + on[-1] + 1) * HOP))
        found.sort(key=lambda f: f[1])
        print(f'\n{n}: ' + ('matches the score' if not found else f'{len(found)} disagreement(s)'))
        for kind, t0, t1 in found:
            print(f'   {kind} {fmt(t0)}-{fmt(t1)}  (bars {bar_at(t0)}-{bar_at(t1)})')
        problems += len(found)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
