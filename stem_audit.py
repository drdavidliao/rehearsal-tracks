#!/usr/bin/env python3
"""Audit a set of exported audio stems against the MusicXML they were rendered from.

    python3 stem_audit.py score.musicxml "Tenor 1=T1.wav" "Tenor 2=T2.wav" ... ["Piano=piano.wav"]
                          [--out report.txt] [--thresh -50]

Each argument after the score pairs a part name (as in <part-name>) with its stem. Give every
stem of the set, accompaniment included: the alignment uses all of them, and a stem can only be
caught holding another staff's audio if that staff's stem is there too.

Written after a Cantai set in which every failure below happened at once (SKILL.md 9.1-9.3):

  1. Files. Length, peak, clipped samples, checksum of the audio, first sound, level while
     sounding. A silent stem, a stem that copies another, one entering late.
  2. Missing singing. Cantai exports only what it has rendered so far, silence for the rest, with
     no warning: whole runs of phrases vanish, starting and ending on a phrase's first syllable.
     Every written note of 0.15 s or more is looked up in the stem; stretches of notes with no
     sound are listed by bar. Under 0.5 s is usually the timing, not the stem (a short staccato
     note at the edge of the alignment); look at anything longer.
  3. Whose line each stem sings. The export plug-in gave every stem after the first the opening
     (about 21 s, up to the first rest) of the staff exported before it, over sung notes: right
     rhythm, plausible pitches, wrong part. Per stem and per chunk of bars, the share of
     quarter-or-longer notes sung within half a semitone of each part's written line. A chunk
     where the stem fits another part's line and not its own is flagged. Where two parts are
     written identically the check cannot tell them apart, and says so.
  4. Identical audio. Two stems that are the same audio (2 s windows correlating above 0.99)
     where their parts are written differently: one holds the other's sound. The same audio
     where the parts are written the same is expected (the same voice on the same notes).

The score is played as Sibelius plays it: repeats and first/second endings unrolled (D.C., D.S.
and codas are not followed; the script warns), tempo from <sound tempo>. It is lined up with the
audio by chroma and dynamic time warping over the sum of all stems, so holds, fermatas and
caesuras longer than written are absorbed (to about a beat, which is why check 3 uses notes a
quarter or longer and check 2 allows half a second at each note's edge).

Needs numpy and ffmpeg on the PATH.
"""
import sys, subprocess, argparse, hashlib, collections
import xml.etree.ElementTree as ET
import numpy as np

SR = 22050
HOP = 0.05
STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


# ----------------------------------------------------------------------------- score

def play_order(measures):
    """Measure indices in the order they are played: repeats and endings, nothing else."""
    rep_start, order, i, passes = 0, [], 0, {}
    n = len(measures)
    warned = False
    while i < n:
        m = measures[i]
        for bl in m.findall('barline'):
            r = bl.find('repeat')
            if r is not None and r.get('direction') == 'forward':
                rep_start = i
            if (bl.find('segno') is not None or bl.find('coda') is not None) and not warned:
                warned = True
        for d in m.iter('sound'):
            if (d.get('dacapo') or d.get('dalsegno') or d.get('tocoda')) and not warned:
                warned = True
        ending = next((bl.find('ending') for bl in m.findall('barline')
                       if bl.find('ending') is not None and bl.find('ending').get('type') == 'start'), None)
        p = passes.get(rep_start, 1)
        if ending is not None and str(p) not in (ending.get('number') or '1').replace(' ', '').split(','):
            # skip this ending: jump past its stop
            j = i
            while j < n and not any(bl.find('ending') is not None and bl.find('ending').get('type') in ('stop', 'discontinue')
                                    for bl in measures[j].findall('barline')):
                j += 1
            i = j + 1
            continue
        order.append(i)
        back = next((bl.find('repeat') for bl in m.findall('barline')
                     if bl.find('repeat') is not None and bl.find('repeat').get('direction') == 'backward'), None)
        if back is not None:
            times = int(back.get('times') or 2)
            if p < times:
                passes[rep_start] = p + 1
                i = rep_start
                continue
            passes[rep_start] = 1
        i += 1
    if warned:
        print('warning: the score has D.C., D.S. or a coda; only repeats and endings are followed')
    return order


def load_score(path):
    root = ET.parse(path).getroot()
    names = {sp.get('id'): (sp.findtext('part-name') or '').strip() for sp in root.iter('score-part')}
    parts_el = root.findall('part')
    order = play_order(parts_el[0].findall('measure'))
    # quarter-note positions of every played bar, and the tempo map, from the first part
    tempos, bar_q, q = [], [], 0.0
    ms0 = parts_el[0].findall('measure')
    div = 1
    lens = []
    for mi, m in enumerate(ms0):
        t, mx = 0.0, 0.0
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= int(e.findtext('duration')) / div
            elif e.tag == 'forward':
                t += int(e.findtext('duration')) / div
            elif e.tag == 'note':
                if e.find('chord') is None and e.find('grace') is None:
                    t += int(e.findtext('duration') or 0) / div
            mx = max(mx, t)
        lens.append(mx)
    tempo_in = {}
    div_ = 1
    for mi, m in enumerate(ms0):
        t = 0.0
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div_ = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= int(e.findtext('duration')) / div_
            elif e.tag == 'forward':
                t += int(e.findtext('duration')) / div_
            elif e.tag == 'note' and e.find('chord') is None and e.find('grace') is None:
                t += int(e.findtext('duration') or 0) / div_
            s = e if e.tag == 'sound' else (e.find('sound') if e.tag == 'direction' else None)
            if s is not None and s.get('tempo'):
                off = e.findtext('offset') if e.tag == 'direction' else None
                tempo_in.setdefault(mi, []).append((t + (int(off) / div_ if off else 0.0), float(s.get('tempo'))))
    seen = collections.Counter()
    for mi in order:
        seen[mi] += 1
        bar_q.append((q, ms0[mi].get('number') + "'" * (seen[mi] - 1), mi))
        for off, bpm in tempo_in.get(mi, []):
            tempos.append((q + off, bpm))
        q += lens[mi]
    end_q = q
    tempos.sort()
    if not tempos or tempos[0][0] > 0:
        tempos.insert(0, (0.0, tempos[0][1] if tempos else 120.0))

    def q2s(x):
        s, (b0, t0) = 0.0, tempos[0]
        for b1, t1 in tempos[1:]:
            if x <= b1:
                break
            s += (b1 - b0) * 60.0 / t0
            b0, t0 = b1, t1
        return s + (x - b0) * 60.0 / t0

    start_q = {mi: [] for mi in range(len(ms0))}
    for q0, num, mi in bar_q:
        start_q[mi].append(q0)
    notes = {}
    for p in parts_el:
        nm = names[p.get('id')]
        out = []
        div = 1
        for mi, m in enumerate(p.findall('measure')):
            t, last = 0.0, 0.0
            evs = []
            for e in m:
                if e.tag == 'attributes' and e.find('divisions') is not None:
                    div = int(e.findtext('divisions'))
                elif e.tag == 'backup':
                    t -= int(e.findtext('duration')) / div
                elif e.tag == 'forward':
                    t += int(e.findtext('duration')) / div
                elif e.tag == 'note':
                    if e.find('grace') is not None:
                        continue
                    d = int(e.findtext('duration') or 0) / div
                    st = t - last if e.find('chord') is not None else t
                    pt = e.find('pitch')
                    tie_stop = any(x.get('type') == 'stop' for x in e.findall('tie'))
                    if pt is not None:
                        midi = 12 * (int(pt.findtext('octave')) + 1) + STEP[pt.findtext('step')] + int(float(pt.findtext('alter') or 0))
                        evs.append((st, st + d, midi, tie_stop, e.find('chord') is not None))
                    if e.find('chord') is None:
                        last = d
                        t += d
            for k, q0 in enumerate(start_q.get(mi, [])):
                lab = m.get('number') + ("'" * k)
                for a, b, midi, ts, ch in evs:
                    out.append((q2s(q0 + a), q2s(q0 + b), midi, ts, ch, lab))
        out.sort()
        notes[nm] = out
    bars = [(q2s(q0), lab) for q0, lab, mi in bar_q]
    return notes, bars, q2s(end_q)


# ----------------------------------------------------------------------------- audio

def decode(path, sr=SR, stereo=False):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path] + ([] if stereo else ['-ac', '1']) +
                         ['-ar', str(sr), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    return x.reshape(-1, 2) if stereo else x


def level_db(x, hop):
    w = int(SR * hop)
    n = len(x) // w
    return 20 * np.log10(np.sqrt((x[:n * w].reshape(n, w).astype(np.float64) ** 2).mean(1)) + 1e-12)


def chroma_audio(x):
    N, hop = 4096, int(SR * HOP)
    fr = np.lib.stride_tricks.sliding_window_view(np.pad(x, (N // 2, N // 2)), N)[::hop] * np.hanning(N)
    X = np.abs(np.fft.rfft(fr, axis=1))
    f = np.fft.rfftfreq(N, 1 / SR)
    sel = (f > 55) & (f < 2000)
    pcs = (np.round(12 * np.log2(f[sel] / 440)) + 9) % 12
    A = np.stack([X[:, sel][:, pcs == k].sum(1) for k in range(12)], 1)
    A = np.log1p(A)
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def chroma_score(notes, n):
    C = np.zeros((n, 12))
    for ns in notes.values():
        for a, b, midi, *_ in ns:
            i0, i1 = int(a / HOP), min(n, int(b / HOP))
            if i1 > i0:
                C[i0:i1, midi % 12] += np.exp(-np.arange(i1 - i0) * HOP / 1.5)
    return C / (np.linalg.norm(C, axis=1, keepdims=True) + 1e-9)


def dtw_path(Cs, Ca):
    """Score frames -> audio frames. Steps (1,1), (1,2), (2,1); start within 2 s, end free."""
    cost = 1 - Cs @ Ca.T
    cost[np.linalg.norm(Cs, axis=1) < 0.5] = 0.5
    cost[:, np.linalg.norm(Ca, axis=1) < 0.5] = 0.5
    n, m = cost.shape
    INF = 1e18
    D = np.full((n, m), INF)
    P = np.zeros((n, m), np.int8)
    D[0, :int(2 / HOP)] = cost[0, :int(2 / HOP)]
    for i in range(1, n):
        c = cost[i]
        a = np.full(m, INF); a[1:] = D[i - 1, :-1]
        b = np.full(m, INF); b[2:] = D[i - 1, :-2] + c[1:-1]
        d = np.full(m, INF)
        if i >= 2:
            d[1:] = D[i - 2, :-1] + cost[i - 1, 1:]
        st = np.vstack([a, b, d])
        k = st.argmin(0)
        D[i] = st[k, np.arange(m)] + c
        P[i] = k
    j, i = int(np.argmin(D[-1])), n - 1
    path = [(i, j)]
    while i > 0:
        k = P[i, j]
        i, j = (i - 1, j - 1) if k == 0 else ((i - 1, j - 2) if k == 1 else (i - 2, j - 1))
        path.append((i, j))
    path = np.array(path[::-1], float)
    return lambda s: np.interp(np.asarray(s) / HOP, path[:, 0], path[:, 1]) * HOP


def f0(x, a, b):
    s = x[int(a * SR):int(b * SR)][:4096]
    if len(s) < 2048 or np.sqrt((s ** 2).mean()) < 1e-3:
        return None
    S = np.abs(np.fft.rfft(s * np.hanning(len(s)), 8 * len(s)))
    f = np.fft.rfftfreq(8 * len(s), 1 / SR)
    h = S.copy()
    for k in (2, 3):                      # harmonic product spectrum: no octave errors
        h[:len(S) // k] *= S[::k][:len(S) // k]
    k = np.argmax(h * ((f > 60) & (f < 700)))
    return 12 * np.log2(f[k] / 440) + 69


def fmt(t):
    return f'{int(t // 60)}:{t % 60:04.1f}'


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('pairs', nargs='+', help='"Part name=stem file"')
    ap.add_argument('--thresh', type=float, default=-50.0, help='dBFS; quieter counts as silent')
    ap.add_argument('--chunk', type=int, default=4, help='bars per chunk for the whose-line check')
    ap.add_argument('--out', help='also write the report here')
    a = ap.parse_args()
    lines = []

    def say(s=''):
        print(s)
        lines.append(s)

    notes, bars, end_s = load_score(a.score)
    pairs = [p.split('=', 1) for p in a.pairs]
    for nm, _ in pairs:
        if nm not in notes:
            sys.exit(f'no part named {nm!r}; the score has {list(notes)}')
    say(f'Stem audit: {a.score}')
    say(f'{len(bars)} bars as played; {fmt(end_s)} at the written tempo')

    # 1. files
    say('\n1. Files')
    X = {}
    for nm, path in pairs:
        st = decode(path, stereo=True)
        x = st.mean(1)
        X[nm] = x
        db = level_db(x, 0.05)
        snd = db > a.thresh
        pk = float(np.abs(st).max())
        clip = int((np.abs(st) >= 0.999).sum())
        md5 = hashlib.md5(st.tobytes()).hexdigest()[:8]
        first = float(np.argmax(snd) * 0.05) if snd.any() else None
        med = float(np.median(db[snd])) if snd.any() else None
        say(f'   {nm:12} {len(x) / SR:7.2f} s  peak {20 * np.log10(pk + 1e-12):6.1f} dB  clipped {clip:5d}  '
            f'audio md5 {md5}  first sound {fmt(first) if first is not None else "never"}  '
            f'level while sounding {med:6.1f} dB' if med is not None else f'   {nm:12} SILENT')
    lens = {nm: len(x) for nm, x in X.items()}
    if len(set(lens.values())) > 1:
        say('   <- the stems differ in length: exported from different takes or ranges?')
    md5s = collections.Counter(hashlib.md5(x.tobytes()).hexdigest() for x in X.values())
    if any(v > 1 for v in md5s.values()):
        say('   <- two stems are the same audio, sample for sample')

    # alignment on the sum of all stems
    n = min(lens.values())
    mix = sum(x[:n] for x in X.values())
    Ca = chroma_audio(mix)
    Cs = chroma_score(notes, int(end_s / HOP) + int(4 / HOP))
    to_audio = dtw_path(Cs, Ca)
    bar_audio = [(float(to_audio(s)), lab) for s, lab in bars]

    def bar_at(t):
        cur = bar_audio[0][1]
        for s, lab in bar_audio:
            if s <= t + 1e-6:
                cur = lab
        return cur

    # 2. missing singing
    say('\n2. Written notes with no sound in the stem: stretches of 0.5 s or more that are silent throughout')
    found2 = {}
    for nm, _ in pairs:
        env = level_db(X[nm], HOP) > a.thresh
        miss = []
        tot = 0.0
        for s0, s1, midi, tie_stop, chord, lab in notes[nm]:
            if chord:
                continue
            t0, t1 = float(to_audio(s0)), float(to_audio(s1))
            if t1 - t0 < 0.15:
                continue
            tot += t1 - t0
            fr = env[int((t0 + 0.1) / HOP):max(int((t0 + 0.1) / HOP) + 1, int((t1 - 0.05) / HOP))]
            if len(fr) and fr.mean() < 0.2:
                miss.append([t0, t1, lab, lab])
        merged = []
        for m in miss:
            if merged and m[0] - merged[-1][1] < 1.5:
                merged[-1][1], merged[-1][3] = m[1], m[3]
            else:
                merged.append(m)
        # a real dropout is silence across the whole stretch; a stretch the alignment put a little
        # off, or quiet notes near the threshold, still has sound in it
        def silent_share(t0, t1):
            fr = env[int(t0 / HOP):max(int(t0 / HOP) + 1, int(t1 / HOP))]
            return 1 - fr.mean() if len(fr) else 0
        long_ = [m for m in merged if m[1] - m[0] >= 0.5 and silent_share(m[0], m[1]) > 0.9]
        short = len(merged) - len(long_)       # short, or with sound in it: timing, not a dropout
        found2[nm] = (long_, short)
    # the same stretch silent in every stem that has notes there is a hold or pause the alignment
    # placed wrongly (a fermata released early), not a dropout: Cantai drops one staff at a time
    envs = {nm: level_db(X[nm], HOP) > a.thresh for nm in found2}
    chordal = {nm for nm, ns in notes.items() if sum(1 for n_ in ns if n_[4]) > 0.05 * max(1, len(ns))}

    def everyone(t0, t1, nm):
        others = [o for o in found2 if o != nm and o not in chordal]   # voices, not the accompaniment
        quiet = [1 - envs[o][int(t0 / HOP):max(int(t0 / HOP) + 1, int(t1 / HOP))].mean() > 0.7 for o in others]   # mostly silent: tails ring on
        return bool(others) and all(quiet)
    for nm, _ in pairs:
        long_, short = found2[nm]
        real = [m for m in long_ if not everyone(m[0], m[1], nm)]
        shared = [m for m in long_ if everyone(m[0], m[1], nm)]
        verdict = f'{len(real)} silent stretch(es)' if real else 'none silent'
        extra = []
        if short:
            extra.append(f'{short} short or partly sounding: the alignment, not the stem')
        if shared:
            extra.append(f'{len(shared)} silent in every stem at once, bars ' +
                         ', '.join(f'{m[2]}-{m[3]}' for m in shared) + ': a hold the alignment misplaced; check by ear')
        say(f'   {nm}: {verdict}' + (f' ({"; ".join(extra)})' if extra else ''))
        for t0, t1, l0, l1 in real:
            say(f'      MISSING {fmt(t0)}-{fmt(t1)}  bars {l0}-{l1}  ({t1 - t0:.1f} s)')

    # 3. whose line
    say(f'\n3. Whose written line each stem sings, per {a.chunk} bars (share of notes a quarter or longer, '
        'within half a semitone)')
    long_notes = {nm: [(s0, s1, midi, lab) for s0, s1, midi, ts, ch, lab in ns if not ch and not ts]
                  for nm, ns in notes.items()}
    labs = [lab for _, lab in bars]
    chunks = [labs[i:i + a.chunk] for i in range(0, len(labs), a.chunk)]
    sung_parts = [nm for nm, _ in pairs]
    X22 = X
    flagged = 0
    for nm, _ in pairs:
        if nm in chordal:
            say(f'   {nm}: plays chords, not checked (a pitch tracker reads its top note, often the melody)')
            continue
        bad = []
        for ch in chunks:
            chs = set(ch)
            share = {}
            written = {}
            for pn in [p_ for p_ in sung_parts if p_ not in chordal]:
                ns = [(s0, s1, midi) for s0, s1, midi, lab in long_notes[pn] if lab in chs]
                written[pn] = tuple(midi for _, _, midi in ns)
                hits, cnt = 0, 0
                for s0, s1, midi in ns:
                    t0, t1 = float(to_audio(s0)), float(to_audio(s1))
                    if t1 - t0 < 0.25:            # quarter-ish or longer: steady enough to read
                        continue
                    v = f0(X22[nm], t0 + 0.08, t1 - 0.04)
                    if v is None:
                        continue
                    cnt += 1
                    hits += abs(v - midi) < 0.5
                share[pn] = (hits / cnt, cnt) if cnt >= 3 else None
            own = share.get(nm)
            if own is None:
                continue
            best = max((p for p in share if share[p] is not None), key=lambda p: share[p][0])
            if own[0] < 0.5 and best != nm and share[best][0] >= 0.75 and written[best] != written[nm]:
                bad.append((ch[0], ch[-1], best, own[0], share[best][0]))
            elif own[0] < 0.3 and own[1] >= 6:        # six notes or more: fewer is too few to judge
                # nobody's line: audio from a staff not in this set (the first stem the plug-in
                # exported sang a basses' line), or a wrong render
                bad.append((ch[0], ch[-1], None, own[0], 0))
        if bad:
            flagged += 1
            say(f'   {nm}: sings another part\'s line in {len(bad)} chunk(s)')
            for l0, l1, other, o, b in bad:
                say(f'      bars {l0}-{l1}: {100 * o:.0f}% on its own line, ' +
                    (f'{100 * b:.0f}% on {other}\'s' if other else 'and on no other part\'s either'))
        else:
            say(f'   {nm}: its own line throughout (where its line differs from every other part\'s)')

    # 4. identical audio
    say('\n4. The same audio in two stems (2 s windows correlating above 0.99)')
    names_ = [nm for nm, _ in pairs]
    w = 2 * SR
    found = False
    for i in range(len(names_)):
        for j in range(i + 1, len(names_)):
            p, q = names_[i], names_[j]
            x, y = X[p], X[q]
            m = min(len(x), len(y)) // w
            same_diff, same_same = [], 0
            for k in range(m):
                s = slice(k * w, (k + 1) * w)
                if np.sqrt((x[s] ** 2).mean()) < 1e-4 or np.sqrt((y[s] ** 2).mean()) < 1e-4:
                    continue
                if np.corrcoef(x[s], y[s])[0, 1] > 0.99:
                    t0 = k * 2.0
                    # are the two parts written the same here?
                    wp = [(round(s0, 2), midi) for s0, s1, midi, *_ in notes[p] if t0 - 1 <= to_audio(s0) < t0 + 3]
                    wq = [(round(s0, 2), midi) for s0, s1, midi, *_ in notes[q] if t0 - 1 <= to_audio(s0) < t0 + 3]
                    if sorted(wp) == sorted(wq):
                        same_same += 1
                    else:
                        same_diff.append(t0)
            if same_diff:
                found = True
                say(f'   {p} / {q}: SAME AUDIO where the parts are written differently, {len(same_diff)} window(s), '
                    f'{fmt(same_diff[0])}-{fmt(same_diff[-1] + 2)} (bars {bar_at(same_diff[0])}-{bar_at(same_diff[-1] + 2)})')
            elif same_same:
                say(f'   {p} / {q}: same audio in {same_same} window(s), all where the parts are written the same (expected)')
    if not found:
        say('   no stem holds another part\'s audio')

    say('\nVerdict: re-export by hand (File > Export > Audio, one staff at a time, after every Cantai voice\'s halo')
    say('and "Rendering..." dot have gone) any stem with a MISSING stretch of 0.5 s or more, one flagged in 3,')
    say('or one holding SAME AUDIO in 4. A stem flagged only in 3 or 4 may also be the source for another\'s leak:')
    say('fix the flagged one, then run this again.')
    if a.out:
        open(a.out, 'w').write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
