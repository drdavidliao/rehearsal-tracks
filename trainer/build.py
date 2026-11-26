#!/usr/bin/env python3
"""Build one pitch-trainer exercise: a few bars of one part, from a song folder that has a player map.

    python3 trainer/build.py "<song folder>" --part Bass --bars 159-161 --out "<folder>"
        [--crop "page,x0,y0,x1,y1[,dy];..."]   # PDF points, y down from the top, one piece per system;
                                                      # dy pastes a piece lower so the staves line up

Writes into --out (with trainer/index.html copied beside it, so the folder is the whole site):
  exercise.json   notes (midi, bar, beat, word, length in beats, times in the clips), each note's piano chord, the
                  bar layout for the staff, the clip timings
  score.png       the singers' PDF cut to the part's staff in those bars (pieces side by side)
  voice-<pct>.mp3, accomp-<pct>.mp3   the part's stem and the accompaniment from one bar before to the end of the
                  bar after, at 100, 80 and 60% speed (rubberband, pitch kept)

Scope: songs with a player map (`player map.json`) whose stems hold the part and an accompaniment "I"; one part,
1-4 bars, one note at a time in that part. The notes and their times come from the map, the chords, meters and staff
text from the MusicXML named here (the map's own score PDF is the crop's source).
"""
import argparse, json, os, shutil, subprocess, sys, tempfile
from fractions import Fraction as F

import music21 as m21

HERE = os.path.dirname(os.path.abspath(__file__))
SPEEDS = (100, 80, 60)


def run(*a):
    subprocess.run(a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def piano_parts(score):
    return [p for p in score.parts if 'piano' in (p.partName or '').lower() or 'pno' in (p.partName or '').lower()]


def sounding_at(parts, bar, q):
    """MIDI numbers of the piano notes sounding at quarter offset q of bar (held notes included)."""
    out = set()
    for p in parts:
        mm = p.measure(bar)
        if mm is None:
            continue
        for n in mm.recurse().notes:
            off = n.getOffsetInHierarchy(mm)
            if off <= q < off + n.quarterLength:
                out.update(x.midi for x in n.pitches)
    # the bass the ear hears under it: the lowest piano note struck in the bar up to q, if nothing lower sounds
    low = None
    for p in parts:
        mm = p.measure(bar)
        if mm is None:
            continue
        for n in mm.recurse().notes:
            if n.getOffsetInHierarchy(mm) <= q:
                lo = min(x.midi for x in n.pitches)
                low = lo if low is None else min(low, lo)
    if low is not None and (not out or low < min(out)):
        out.add(low)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('song')
    ap.add_argument('--part', required=True)
    ap.add_argument('--bars', required=True)
    ap.add_argument('--xml', default=None, help='MusicXML for chords and meters (default: the map\'s full score)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--crop', default=None)
    ap.add_argument('--title', default=None)
    ap.add_argument('--text', default='', help='staff text printed over these bars, shown under the score')
    a = ap.parse_args()

    song = a.song
    mp = json.load(open(os.path.join(song, 'player map.json')))
    b0, b1 = (int(x) for x in a.bars.split('-'))
    if not 1 <= b1 - b0 + 1 <= 4:
        sys.exit('scope: 1-4 bars')
    bars = {b['num']: b for b in mp['bars']}
    for b in range(b0 - 1, b1 + 2):
        if b not in bars:
            sys.exit(f'bar {b} is not in the map')

    notes = [n for n in mp['notes'] if n['part'] == a.part and b0 <= n['bar'] <= b1]
    if not notes:
        sys.exit(f'no {a.part} notes in m{b0}-{b1}')
    notes.sort(key=lambda n: n['start'])
    for x, y in zip(notes, notes[1:]):
        if y['start'] < x['start'] + 0.02:
            sys.exit(f'scope: {a.part} has two notes at once near m{x["bar"]}')

    xml = a.xml or os.path.join(song, next(f for f in os.listdir(song) if f.endswith('(full, from the original).musicxml')))
    sc = m21.converter.parse(xml)
    pianos = piano_parts(sc)
    any_part = sc.parts[0]

    # the map counts beats in its own unit; turn a map beat into a quarter offset with the bar's beat times
    t_clip0 = bars[b0 - 1]['beat_t'][0]
    t_clip1 = bars[b1 + 1]['end_t'] + 0.4
    out_notes = []
    for n in notes:
        bar = bars[n['bar']]
        mm = any_part.measure(n['bar'])
        ts = mm.getContextByClass('TimeSignature')
        bar_q = float(ts.barDuration.quarterLength)
        frac = (n['start'] - bar['beat_t'][0]) / (bar['end_t'] - bar['beat_t'][0])
        q = round(frac * bar_q * 2) / 2
        out_notes.append({
            'bar': n['bar'], 'q': q, 'midi': n['midi'], 'word': n.get('word') or '',
            'len_q': None,
            't0': round(n['start'] - t_clip0, 3), 't1': round(n['end'] - t_clip0, 3),
            'chord': sounding_at(pianos, n['bar'], q),
        })
    # written length: from the part's own MusicXML voice, matched by bar, offset and pitch (any staff)
    for o in out_notes:
        for p in sc.parts:
            if p in pianos:
                continue
            mm = p.measure(o['bar'])
            if mm is None:
                continue
            for el in mm.recurse().notes:
                if abs(float(el.getOffsetInHierarchy(mm)) - o['q']) < 1e-6 and o['midi'] in [x.midi for x in el.pitches]:
                    o['len_q'] = float(el.quarterLength)
                    pt = next(x for x in el.pitches if x.midi == o['midi'])
                    o['step'], o['alter'], o['octave'] = pt.step, int(pt.alter), pt.octave
                    o['name'] = pt.name.replace('-', '♭').replace('#', '♯') + str(pt.octave)
        if o['len_q'] is None:
            sys.exit(f'note m{o["bar"]} q{o["q"]} midi {o["midi"]} not found in the MusicXML: map and score disagree')

    meters = []
    for b in range(b0 - 1, b1 + 2):
        mm = any_part.measure(b)
        ts = mm.getContextByClass('TimeSignature')
        meters.append({'bar': b, 'num': ts.numerator, 'den': ts.denominator, 'new_meter': bool(mm.getElementsByClass('TimeSignature')),
                       't0': round(bars[b]['beat_t'][0] - t_clip0, 3), 't1': round(bars[b]['end_t'] - t_clip0, 3)})

    os.makedirs(a.out, exist_ok=True)

    # audio
    voice = os.path.join(song, mp['stems'][a.part])
    acc = os.path.join(song, mp['stems']['I'])
    with tempfile.TemporaryDirectory() as td:
        for name, src in (('voice', voice), ('accomp', acc)):
            cut = os.path.join(td, name + '.wav')
            run('ffmpeg', '-y', '-ss', f'{t_clip0:.3f}', '-to', f'{t_clip1:.3f}', '-i', src, '-ac', '1', '-ar', '44100', cut)
            for pct in SPEEDS:
                src2 = cut
                if pct != 100:
                    src2 = os.path.join(td, f'{name}{pct}.wav')
                    run('rubberband', '-t', f'{100 / pct:.4f}', '-3', cut, src2)  # -t: time ratio, so 60% is 1.667x as long
                run('ffmpeg', '-y', '-i', src2, '-codec:a', 'libmp3lame', '-b:a', '128k', os.path.join(a.out, f'{name}-{pct}.mp3'))

    # score crop
    if a.crop:
        from PIL import Image
        pdf = os.path.join(song, mp['score'])
        dpi = 200
        s = dpi / 72
        pieces = []
        with tempfile.TemporaryDirectory() as td:
            for spec in a.crop.split(';'):
                v = [float(x) for x in spec.split(',')]
                pg, x0, y0, x1, y1 = v[:5]
                dy = v[5] if len(v) > 5 else 0  # paste this many points lower, to line the staves up
                pg = int(pg)
                stem = os.path.join(td, f'p{pg}')
                run('pdftoppm', '-f', str(pg + 1), '-l', str(pg + 1), '-r', str(dpi), '-png', '-singlefile', pdf, stem)
                im = Image.open(stem + '.png').convert('L')
                pieces.append((im.crop((int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s))), int(dy * s)))
        h = max(p.height + dy for p, dy in pieces)
        gap = 24
        im = Image.new('L', (sum(p.width for p, _ in pieces) + gap * (len(pieces) - 1), h), 255)
        x = 0
        for p, dy in pieces:
            im.paste(p, (x, dy))
            x += p.width + gap
        im.save(os.path.join(a.out, 'score.png'), optimize=True)

    ex = {
        'title': a.title or f'{os.path.basename(os.path.normpath(song))}, {a.part}, m{b0}-{b1}',
        'part': a.part, 'bars': [b0, b1], 'text': a.text,
        'tempo_note': f'{mp.get("tempo")} in the map\'s beat unit',
        'speeds': list(SPEEDS), 'clip_len': round(t_clip1 - t_clip0, 3),
        'lead_in': {'t0': meters[0]['t0'], 't1': meters[0]['t1']},
        'meters': meters, 'notes': out_notes, 'score_png': bool(a.crop),
        'source': {'xml': os.path.basename(xml), 'voice': os.path.basename(voice), 'accomp': os.path.basename(acc),
                   'score': mp['score']},
    }
    json.dump(ex, open(os.path.join(a.out, 'exercise.json'), 'w'), indent=1)
    for f in ('index.html', 'pitch.js', 'trainer.js', 'test.html'):
        if os.path.exists(os.path.join(HERE, f)):
            shutil.copy(os.path.join(HERE, f), os.path.join(a.out, f))
    print(json.dumps(ex['notes'], indent=0))


if __name__ == '__main__':
    main()
