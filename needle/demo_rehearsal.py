#!/usr/bin/env python3
"""A made-up rehearsal, for trying rehearsal_status.py: server.py --cmd "python3 demo_rehearsal.py".
Writes three songs' maps and a log of the player's states under .rehearsal/demo/, the rehearsal having begun 20 minutes
before this was first run, and prints the status as of now: the log runs on past now, so the dial moves as it goes."""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, '.rehearsal', 'demo')
STAMP = os.path.join(DEMO, 'start')
os.makedirs(DEMO, exist_ok=True)
if not os.path.exists(STAMP): open(STAMP, 'w').write(str(time.time()))
T0 = float(open(STAMP).read()) - 20 * 60


def song(name, tempo, bars, letters):
    """bars of 4 beats at tempo; letters: {bar number: letter}"""
    d = os.path.join(DEMO, name); os.makedirs(d, exist_ok=True)
    beat = 60 / tempo
    m = dict(tempo=tempo, bars=[dict(num=n, letter=letters.get(n), beat_t=[(n - 1) * 4 * beat + k * beat for k in range(4)],
                                     end_t=n * 4 * beat) for n in range(1, bars + 1)])
    json.dump(m, open(os.path.join(d, 'player map.json'), 'w'))
    return dict(folder=d, name=name, tempo=tempo, map=m)


songs = [song('Carol of the Demo', 100, 48, {1: 'A', 13: 'B', 25: 'C', 37: 'D'}),
         song('Demo Noel', 80, 54, {5: 'A', 15: 'B', 25: 'C', 35: 'D', 45: 'E'}),
         song('Jingle Example', 120, 40, {1: 'A', 17: 'B', 29: 'C'})]
marks = [['B', 'C'], ['A', 'C', 'E'], []]
events = []


def state(s, k, wall, t, playing, mode, tempo):
    b = max(i for i, x in enumerate(s['map']['bars']) if x['beat_t'][0] <= t + 0.002)
    events.append(dict(wall=round(wall, 2), folder=s['folder'], song=s['name'], playing=playing, bar=b + 1, mode=mode,
                       tempo=tempo, song_tempo=s['tempo'], marked=marks[k], time=round(t, 3)))


def play(k, a, z, at, mode='balanced', tempo=None):
    """plays bars a to z (numbers) starting at minute at; returns the minute it stopped"""
    s = songs[k]; tempo = tempo or s['tempo']; bars = s['map']['bars']
    w = T0 + at * 60
    state(s, k, w, bars[a - 1]['beat_t'][0], False, mode, tempo)
    for n in range(a, z + 1):
        w += 0.3; state(s, k, w, bars[n - 1]['beat_t'][0] + 0.3, True, mode, tempo)
        w += (bars[n - 1]['end_t'] - bars[n - 1]['beat_t'][0]) * s['tempo'] / tempo - 0.3
    state(s, k, w, bars[z - 1]['end_t'] - 0.01, False, mode, tempo)
    return (w - T0) / 60


# each song's checked sections, as the player's defaults would give them
for k, s in enumerate(songs): state(s, k, T0 - 60, 0, False, 'balanced', s['tempo'])
# Carol: B learned part by part at 80, then sung through; C worked on, then on to Noel without a full run of C
play(0, 13, 18, 1, 'only', 80); play(0, 13, 18, 3, 'only', 80); play(0, 19, 24, 5, 'other', 80); play(0, 13, 24, 7.5, tempo=90)
play(0, 25, 30, 9, 'only', 90); play(0, 25, 36, 12, 'other', 100)
# Noel: A worked a little and sung through, C slowly then through, E
play(1, 5, 14, 15.5, 'only', 70); play(1, 5, 14, 17); play(1, 25, 34, 18, 'only', 64); play(1, 25, 34, 22, 'only', 70); play(1, 25, 34, 25)
play(1, 45, 54, 27, 'only', 72); play(1, 45, 54, 31)
# Jingle, whole song
play(2, 1, 16, 34, 'only', 100); play(2, 1, 40, 38)

log = os.path.join(DEMO, 'log.jsonl')
with open(log, 'w') as f:
    for e in events: f.write(json.dumps(e) + '\n')
out = subprocess.run([sys.executable, os.path.join(HERE, 'rehearsal_status.py'), '--no-poll', '--log', log, '--at', str(time.time()),
                      '--songs'] + [s['folder'] for s in songs], capture_output=True, text=True)
s = json.loads(out.stdout); s.pop('now', None); s['note'] += ' · a made-up rehearsal'
print(json.dumps(s))
