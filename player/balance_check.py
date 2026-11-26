#!/usr/bin/env python3
"""How loud a map's accompaniment stem plays against its voices, compared with the singers' own Balanced mix.

    balance_check.py SONG_FOLDER BALANCED.mp3 [--write]
    balance_check.py SONG_FOLDER -6.6 [--write]          (no Balanced mix: the ratio to aim for, in dB)

The player plays the instrumental stem `I` at unity and each voice at its trim, panned with a constant-power law; this mixes
the map's stems that way, all voices on. In the Balanced mix the accompaniment track is fitted (one gain, after lining the two
up), and what is left is the voices. The ratio of accompaniment to voices in each is compared; --write rescales the `I` stem
(a new file beside it, `... (balanced).wav`) by the difference and points the map at it.
"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf

SR = 11025


def load(path):
    b = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'], capture_output=True, check=True).stdout
    return np.frombuffer(b, 'f4').reshape(-1, 2).astype(np.float64)


def section_of(name):
    """Model.swift's Voice.section(of:): "Tenor 2a" and "Tenor 2b" are halves of "Tenor 2"; "Alto 1" of "Alto" """
    n = name.strip()
    if len(n) > 2 and n[-1] in 'abcd' and (n[-2] == ' ' or n[-2].isdigit()): return n[:-1].strip()
    for s in ('Soprano', 'Alto'):
        if n.startswith(s + ' ') and n[len(s) + 1:] in ('1', '2', '3'): return s
    return n


def voices_of(m):
    """the map's voices as the app reads them (Model.swift Voice.from): (stem key, section, solo, stem trim)"""
    if m.get('voices'):
        return [(v['key'], v.get('section') or section_of(v.get('name') or v['key']),
                 v.get('solo', (v.get('name') or v['key']).lower().startswith('solo')), v.get('trim', 0.0)) for v in m['voices']]
    names = m.get('part_names') or {}; solo = names.get('A2') == 'Solo'; two = 'A2' in m['stems'] and not solo
    order = (['A2'] if solo else []) + ['S', 'A'] + (['A2'] if two else []) + ['T', 'B']
    return [(k, 'A' if k == 'A2' and two else k, k == 'A2' and solo, 0.0) for k in order if k in m['stems']]


def sections(m):
    """each stem's (pan knob, trim dB) as Model.swift's mix() sets them: sections spread from -45 to +45, the outer two at
    0 dB and any between at -3 dB, a section's halves 5 either side of its place, soloists centred at their stem trim"""
    vs = voices_of(m); secs = []
    for k, sec, solo, _ in vs:
        if not solo and sec not in secs: secs.append(sec)
    n = len(secs); out = {}
    for j, sec in enumerate(secs):
        pan = 0.0 if n == 1 else -45 + 90 * j / (n - 1); trim = 0.0 if j in (0, n - 1) else -3.0
        members = [v for v in vs if not v[2] and v[1] == sec]
        for i, v in enumerate(members):
            out[v[0]] = (pan + (0 if len(members) == 1 else -5 + 10 * i / (len(members) - 1)), trim + v[3])
    for k, _, solo, t in vs:
        if solo: out[k] = (0.0, t)
    return out


def pan_gains(knob):
    if knob == 0: return 1.0, 1.0
    th = (np.clip(knob / 64, -1, 1) + 1) * np.pi / 4
    return np.cos(th) * np.sqrt(2), np.sin(th) * np.sqrt(2)


def lag(ref, x):
    a, b = ref.mean(1), x.mean(1); n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    k = int(np.argmax(c)); return k if k < n // 2 else k - n


def main():
    folder, bal = sys.argv[1], sys.argv[2]
    m = json.load(open(os.path.join(folder, 'player map.json')))
    pans = sections(m)
    I = load(os.path.join(folder, m['stems']['I']))
    V = np.zeros_like(I)
    for key, (p, t) in pans.items():
        s = load(os.path.join(folder, m['stems'][key]))[:len(I)]
        l, r = pan_gains(p); g = 10 ** (t / 20)
        V[:len(s), 0] += s[:, 0] * g * l; V[:len(s), 1] += s[:, 1] * g * r
    rms = lambda x: float(np.sqrt((x ** 2).mean()))
    have = 20 * np.log10(rms(I) / rms(V))
    try:
        want = float(bal); how = 'asked for'
    except ValueError:
        B0 = load(bal); k = lag(I, B0)            # B0 is k samples later than I
        B = np.zeros_like(I)
        if k >= 0: n = min(len(B0) - k, len(I)); B[:n] = B0[k:k + n]
        else: n = min(len(B0), len(I) + k); B[-k:-k + n] = B0[:n]
        c = float((B * I).sum() / (I * I).sum()); R = B - c * I
        want = 20 * np.log10(rms(c * I) / rms(R))
        how = f'in the Balanced mix (lag {k / SR:+.3f} s, voices left after the fit {20 * np.log10(rms(R) / rms(B)):+.1f} dB of it)'
    print(f'{os.path.basename(folder.rstrip("/"))}: accompaniment vs voices {have:+.1f} dB in the map, {want:+.1f} dB {how}: '
          f'{want - have:+.1f} dB to add')
    if '--write' in sys.argv:
        src = os.path.join(folder, m['stems']['I']); full, sr = sf.read(src)
        out = src[:-4] + ' (balanced).wav' if not src.endswith(' (balanced).wav') else src
        y = full * 10 ** ((want - have) / 20)
        peak = float(np.abs(y).max())
        # a peak over full scale stays whole in float; the player mixes in float
        sf.write(out + '.tmp.wav', y, sr, subtype='FLOAT' if peak >= 1 else 'PCM_24'); os.replace(out + '.tmp.wav', out)
        m['stems']['I'] = os.path.relpath(out, folder)
        json.dump(m, open(os.path.join(folder, 'player map.json'), 'w'), indent=0)
        print(f'  wrote {os.path.relpath(out, folder)} (peak {peak:.2f}) and pointed the map at it')


if __name__ == '__main__':
    main()
