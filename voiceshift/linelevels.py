"""How loud each sung line is inside each stem, measured at the line's own pitches.

    python3 -m voiceshift.linelevels SCORE.musicxml --line "Tenor 1=P1" --line "Tenor 2=P2" --line "Low=P4" \
        --stem "T1=t1.wav" --stem "T2=t2.wav" --stem "Low=low.wav" --bar1 1.03 --beat 0.5 [--swing 0.61]

For each note of each line (0.2 s or longer, not an x-notehead) where none of its first four
harmonics lies within 4% of a harmonic of another line sounding then: the stem's energy at those
harmonics over the note (from 60 ms in to 30 ms before its end).  Median per stem and line, in dB.
Then, for a mix that is the plain sum of the stems (stems made from one session's recordings, so a
line adds coherently across stems), each line's level in that sum.

What it was for: practice-track stems are mixes of every voice with one featured, and their
"others" level is not one number (one publisher's Soprano 1 track had the other voices ~20 dB down,
while its Soprano 2 and Alto tracks had Soprano 1 only 5-10 dB down), so a stem can't be un-mixed
with one ratio.  Measured line by line, it showed that a duplicated low stem was not what made the
tenors sound soft: the low line sat 4 dB under Tenor 1 in the Balanced sum.
"""
import argparse

import numpy as np
import soundfile as sf


def events(path, pid, bar1, beat, swing):
    from lxml import etree
    x = etree.parse(path)
    ev, pos = [], 0.0
    div = 1
    for m in x.findall(f".//part[@id='{pid}']/measure"):
        cur, mx = 0, 0
        for el in m:
            if el.tag == 'attributes' and el.find('divisions') is not None:
                div = int(el.findtext('divisions'))
            if el.tag == 'backup':
                cur -= int(el.findtext('duration'))
            if el.tag != 'note' or el.find('chord') is not None:
                continue
            d = int(el.findtext('duration') or 0)
            p = el.find('pitch')
            if p is not None and el.find('notehead') is None:
                st = 'CDEFGAB'.index(p.findtext('step'))
                midi = 12 * (int(p.findtext('octave')) + 1) + [0, 2, 4, 5, 7, 9, 11][st] + int(p.findtext('alter') or 0)
                q0, q1 = pos + cur / div, pos + (cur + d) / div
                sw = lambda q: q + (swing - 0.5) if swing and abs(q % 1 - 0.5) < 1e-9 else q
                ev.append((bar1 + sw(q0) * beat, bar1 + sw(q1) * beat, 440 * 2 ** ((midi - 69) / 12)))
            cur += d
            mx = max(mx, cur)
        pos += mx / div
    return ev


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('--line', action='append', required=True, help='"Name=part id"')
    ap.add_argument('--stem', action='append', required=True, help='"Name=file.wav"')
    ap.add_argument('--bar1', type=float, required=True); ap.add_argument('--beat', type=float, required=True)
    ap.add_argument('--swing', type=float, default=0.0)
    a = ap.parse_args()
    lines = {k: events(a.score, v, a.bar1, a.beat, a.swing) for k, v in (s.split('=', 1) for s in a.line)}
    stems = {k: sf.read(v, always_2d=True) for k, v in (s.split('=', 1) for s in a.stem)}
    table = {}
    for L, ev in lines.items():
        others = [e for K, E in lines.items() if K != L for e in E]
        good = []
        for t0, t1, f in ev:
            if t1 - t0 < 0.2:
                continue
            snd = [g for s0, s1, g in others if s0 < t1 and s1 > t0]
            if not any(abs(h * f / (k * g) - 1) < 0.04 for g in snd for h in range(1, 5) for k in range(1, 5)):
                good.append((t0, t1, f))
        print(f'{L}: {len(good)} notes clear of the other lines')
        for s, (x, sr) in stems.items():
            m = x.mean(1)
            vals = []
            for t0, t1, f in good:
                seg = m[int((t0 + 0.06) * sr):int((t1 - 0.03) * sr)]
                X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
                fr = np.fft.rfftfreq(len(seg), 1 / sr)
                p = sum(X[(fr > h * f * 0.97) & (fr < h * f * 1.03)].sum() for h in range(1, 5)) / len(seg)
                vals.append(10 * np.log10(p + 1e-20))
            table[(s, L)] = float(np.median(vals))
    names = list(lines)
    print(f"{'':12s}" + ''.join(f'{L:>11s}' for L in names))
    for s in stems:
        print(f'{s:12s}' + ''.join(f'{table[(s, L)]:11.1f}' for L in names))
    print(f"{'sum of all':12s}" + ''.join(
        f'{20 * np.log10(sum(10 ** (table[(s, L)] / 20) for s in stems)):11.1f}' for L in names))


if __name__ == '__main__':
    main()
