#!/usr/bin/env python3
"""Check a player map where no voice times it: the beats between sung attacks.

    python3 player/unvoiced_check.py FOLDER [--map MAP.json] [--gap 3] [--tol 0.15]

make_map.py's warp and the pitch guide time beats from the voices' attacks. Where no voice attacks (an intro, an
interlude, all parts resting, or only holding a note), nothing in them fixes the time: the fit interpolates or follows
whatever the accompaniment gives it, and `pitch_guide.py check` (sung notes only) cannot see the result. This script
lists every such stretch and tests it two independent ways:

  tempo   a beat inside the stretch whose length is more than 12% off the local beat (the median of the voice-timed
          beats within 8 on either side), allowing for the meter's beat. Fermata bars are reported, not judged.
  accomp  the instrumental stem's onsets fitted with a steady beat across the stretch and one beat either side, scored
          against the accompaniment's own pattern around the beat (its onset strength folded by beat phase over the
          voice-timed beats nearby). Beats where the map is more than --tol from that fit are listed.

It never changes the map. A flag is a place to look, not a measured time: confirm each against the accompaniment and
the voices' releases and entries before pinning it (README, "bars where no voice sings").
"""
import argparse, json, os, statistics, sys
import numpy as np
import soundfile as sf

SR_HOP = 441


def onset_env(path):
    y, sr = sf.read(path, dtype='float32')
    if y.ndim > 1: y = y.mean(1)
    n = 4096
    fr = np.lib.stride_tricks.sliding_window_view(y, n)[::SR_HOP]
    f = np.fft.rfftfreq(n, 1 / sr)
    band = (f > 60) & (f < 4000)
    S = np.empty((len(fr), band.sum()), np.float32)
    for i in range(0, len(fr), 2000):
        S[i:i + 2000] = np.log1p(100 * np.abs(np.fft.rfft(fr[i:i + 2000] * np.hanning(n), axis=1))[:, band])
    fl = np.maximum(0, np.diff(S, axis=0)).sum(1)
    fl = (fl - np.median(fl)) / (fl.std() + 1e-9)
    t = np.arange(1, len(S)) * SR_HOP / sr + n / 2 / sr
    return t, np.clip(fl, -1, 6)


def beats_of(m):
    """every beat in play order: (bar index, beat index, time); plus the end of the last bar"""
    out = []
    for i, b in enumerate(m['bars']):
        for k, t in enumerate(b['beat_t']): out.append((i, k, t))
    return out


def attack_positions(m, beats):
    """global beat positions (float) of every sung attack, placed by the note's own bar and beat"""
    first = {}
    for g, (i, k, t) in enumerate(beats):
        if k == 0: first[i] = g
    pos = []
    bars = m['bars']
    for n in m['notes']:
        cands = [i for i, b in enumerate(bars) if b['num'] == n['bar']]
        if not cands: continue
        i = min(cands, key=lambda i: 0 if bars[i]['beat_t'][0] - 0.05 <= n['start'] < bars[i]['end_t'] + 0.05
                else 1 + min(abs(n['start'] - bars[i]['beat_t'][0]), abs(n['start'] - bars[i]['end_t'])))
        pos.append(first[i] + n['beat'] - 1)
    return sorted(set(round(p, 3) for p in pos))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('--map', help='a map other than FOLDER/player map.json (a backup, to test the check)')
    ap.add_argument('--gap', type=float, default=3, help='beats without a sung attack that make a stretch (default 3)')
    ap.add_argument('--tol', type=float, default=0.15)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    m = json.load(open(a.map or os.path.join(a.folder, 'player map.json')))
    if 'I' not in m['stems']:
        print('no instrumental stem: accompaniment test skipped'); inst = None
    else:
        inst = onset_env(os.path.join(a.folder, m['stems']['I']))
    beats = beats_of(m)
    T = np.array([t for _, _, t in beats] + [m['bars'][-1]['end_t']])  # T[g] = time of global beat g; T[-1] the end
    nb = len(beats)
    dur = np.diff(T)
    # a bar's beat length is its own unit; compare per bar with the bar's beat count against its written length is
    # not in the map, so compare beat lengths only between bars with the same number of beats per bar
    perbar = np.array([len(m['bars'][i]['beat_t']) for i, _, _ in beats])
    att = attack_positions(m, beats)
    timed = np.zeros(nb, bool)
    for p in att:
        g = int(np.floor(p + 1e-6))
        if 0 <= g < nb: timed[g] = True
    # stretches: from one attack to the next more than --gap beats apart, plus before the first and after the last
    pts = [0.0] + att + [float(nb)]
    stretches = [(p, q) for p, q in zip(pts, pts[1:]) if q - p >= a.gap]
    at = lambda gpos: np.interp(gpos, np.arange(nb + 1), T)
    label = lambda g: f"{m['bars'][beats[g][0]]['num']}.{beats[g][1] + 1}" if g < nb else 'end'
    report = []
    for p, q in stretches:
        g0, g1 = int(np.ceil(p - 1e-6)), int(np.floor(q + 1e-6))
        inner = list(range(g0, min(g1, nb)))
        if not inner: continue
        # local beat from voice-timed beats nearby, same beats-per-bar
        near = [g for g in range(max(0, g0 - 8), min(nb, g1 + 8)) if timed[g] and (g < g0 or g >= g1)]
        flags = []
        for g in inner:
            ref = [dur[h] for h in near if perbar[h] == perbar[g]]
            if len(ref) >= 3:
                r = statistics.median(ref)
                if abs(dur[g] / r - 1) > 0.12: flags.append(('tempo', label(g), round(dur[g], 2), round(r, 2)))
            else:
                # no voice-timed bar of this meter nearby (a 6/4 bar among 4/4s and 6/8s): the map doesn't say the beat's
                # note value, so there is nothing fair to compare it with. Say so rather than pass it.
                flags.append(('unjudged', label(g)))
        if inst is not None and len(inner) >= 2:
            t, fl = inst
            # the accompaniment's pattern through the bar, from voice-timed beats nearby: 24 bins a beat, kept apart by
            # (beats in the bar, which beat), so a downbeat looks unlike the beats after it. Folded by beat alone, a
            # steady accompaniment looks the same a beat later and the fit slips a whole beat.
            ph = np.linspace(0, 1, 24, endpoint=False)
            prof, cnt = {}, {}
            for h in near:
                key = (perbar[h], beats[h][1])
                prof[key] = prof.get(key, 0) + np.interp(T[h] + ph * dur[h], t, fl); cnt[key] = cnt.get(key, 0) + 1
            lo, hi = max(0, g0 - 1), min(nb, g1 + 1)
            keys = [(perbar[g], beats[g][1]) for g in range(lo, hi)]
            if sum(k in prof for k in keys) >= 0.75 * len(keys):
                allm = np.mean([prof[k] / cnt[k] for k in prof], 0)
                rows = np.array([prof[k] / cnt[k] if k in prof else allm for k in keys])
                rows -= rows.mean()
                n = hi - lo; span = T[hi] - T[lo]
                score = lambda times, per: (np.interp(times[:, None] + ph[None, :] * per, t, fl) * rows).sum()
                mine = (np.interp(T[lo:hi, None] + ph[None, :] * dur[lo:hi, None], t, fl) * rows).sum()
                beat = span / n
                best = None
                for per in np.linspace(beat * 0.92, beat * 1.08, 33):
                    # under half a beat either way: a whole beat or more out is the tempo test's to find
                    for t0 in np.arange(T[lo] - 0.45 * beat, T[lo] + 0.45 * beat, 0.01):
                        sc = score(t0 + np.arange(n) * per, per)
                        if best is None or sc > best[0]: best = (sc, per, t0)
                sc, per, t0 = best
                fit = {lo + j: t0 + j * per for j in range(n)}
                off = [(label(g), round(T[g] - fit[g], 2)) for g in inner if abs(T[g] - fit[g]) > a.tol]
                gain = (sc - mine) / (abs(mine) + 1e-9)
                if off and gain > 0.15: flags.append(('accomp', off, round(per, 3), round(gain, 2)))
        kind = 'intro' if p == 0 else 'end' if q == nb else 'rest/hold'
        report.append(dict(kind=kind, start=label(g0), stop=label(min(g1, nb)), beats=len(inner), flags=flags))
    if a.json:
        print(json.dumps(report)); return
    flagged = [r for r in report if r['flags']]
    print(f"{len(report)} stretches of {a.gap:g}+ beats without a sung attack; {len(flagged)} flagged")
    for r in report:
        print(f"  {r['kind']:9s} {r['start']:>7s} to {r['stop']:<7s} {r['beats']:3d} beats", 'ok' if not r['flags'] else '')
        for f in r['flags']:
            if f[0] == 'tempo': print(f'      tempo  {f[1]}: beat {f[2]} s against {f[3]}')
            elif f[0] == 'unjudged': print(f'      tempo  {f[1]}: not judged, no voice-timed bar of its meter nearby')
            else: print(f"      accomp map minus fit (beat {f[2]} s, fit scores {f[3]:+.0%} over the map): "
                        + ' '.join(f'{l} {d:+.2f}' for l, d in f[1]))


if __name__ == '__main__':
    main()
