#!/usr/bin/env python3
"""Makes each voice stem of a map centred, so that the player's own panning is the only panning.

    center_stems.py SONG_FOLDER [--write]

Rehearsal mixes come two ways, and a stem separated from one keeps its layout:
  - the part on the left channel and the other voices on the right (Matthew Curtis's "part-left" mixes, and the
    Predominant mixes of several of his sets): the two channels hardly correlate and the left is far louder. The left
    channel alone is the part; the right would play every other voice again inside this one's stem.
  - an ordinary stereo mix with the part placed at its seat (tenors left, basses right): the channels correlate and one
    is a few dB louder. Folded to mono, the part plays where the player pans it, not further out.
For each voice stem it prints the left-right balance and correlation and what it would do; --write writes the
"(left channel).wav" or "(mono).wav" copy beside the stem (both channels the same) and points the map at it. The
accompaniment stem is left as it is. Run balance_check.py afterwards: the voices' level changes.
"""
import json, os, sys
import numpy as np, soundfile as sf


def plan(x):
    L, R = x[:, 0], x[:, 1]
    eL, eR = float((L * L).sum()), float((R * R).sum())
    if eL == 0 or eR == 0: return 'mono already', 0.0, 1.0
    db = 10 * np.log10(eL / eR); c = float((L * R).sum() / np.sqrt(eL * eR))
    if c > 0.98 and abs(db) < 0.5: return 'centred already', db, c
    if c < 0.5 and abs(db) > 3: return ('left channel' if db > 0 else 'right channel'), db, c
    return 'mono', db, c


def main():
    folder = sys.argv[1]; write = '--write' in sys.argv
    mp = os.path.join(folder, 'player map.json'); m = json.load(open(mp))
    for k, rel in m['stems'].items():
        if k == 'I': continue
        if rel.endswith((' (left channel).wav', ' (right channel).wav', ' (mono).wav')):
            print(f'  {k}: {rel} already made centred'); continue
        src = os.path.join(folder, rel)
        x, sr = sf.read(src, always_2d=True)
        if x.shape[1] < 2: print(f'  {k}: one channel'); continue
        what, db, c = plan(x)
        print(f'  {k}: left {db:+.1f} dB against the right, correlation {c:.2f}: {what}')
        if not write or what in ('mono already', 'centred already'): continue
        y = {'left channel': x[:, 0], 'right channel': x[:, 1]}.get(what)
        if y is None: y = x.mean(1)
        out = os.path.splitext(src)[0] + f' ({what}).wav'
        peak = float(np.abs(y).max())
        sf.write(out + '.tmp.wav', np.stack([y, y], 1), sr, subtype='FLOAT' if peak >= 1 else 'PCM_24')
        os.replace(out + '.tmp.wav', out)
        m['stems'][k] = os.path.relpath(out, folder)
    if write:
        json.dump(m, open(mp + '.tmp', 'w'), indent=0); os.replace(mp + '.tmp', mp)
        print(f'  pointed {mp} at the centred stems')


if __name__ == '__main__':
    main()
