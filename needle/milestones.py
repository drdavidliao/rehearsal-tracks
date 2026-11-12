#!/usr/bin/env python3
"""A needle for a run of different steps (transcribe, mark up, separate, map) whose estimate and band come from what has
been measured so far, not from the guesses made before starting.

    python3 needle/server.py --cmd "python3 needle/milestones.py STEPS.json"
    python3 needle/milestones.py STEPS.json --now 16:00        the status as it would have been at 16:00 (a replay)

STEPS.json, rewritten by hand or by the work as it goes:

    {"title": "Song", "label": "player map done", "note": "...",
     "steps": [
       {"name": "Separated stems", "guess": 12, "lane": "machine", "start": "15:54",
        "parts": 5, "parts_done": ["15:57", "15:59"]},
       {"name": "Transcribed MusicXML", "guess": 45, "start": "15:54", "end": "15:58"},
       {"name": "Lesson-marked PDF", "guess": 15, "after": ["Transcribed MusicXML"], "state": "checking pages"},
       {"name": "Player map", "guess": 25, "after": ["Separated stems", "Lesson-marked PDF"]}]}

A guess (minutes) only says how big a step is next to the others. Each finished step measures how far off its guess was
(taken / guessed), and every step still to do is its guess times the fastest, median and slowest of those measurements:
the needle at the median, the band from fastest to slowest. So the band is the spread actually seen, and it moves with every
step that finishes. A step that is several equal parts (stems, pages) and has finished some times its remaining parts at
their own measured pace instead, fastest to slowest part. A running step never finishes before now, and steps on one lane
("me" by default; a background job its own) run one after another, each also waiting for the steps it is `after`.

Before anything has been measured there is nothing to go on but the guesses: the band is then half to twice them, and the
basis says so. A step is "end"ed (done) only once its checks have passed and its output is in place.
"""
import argparse, datetime, json, statistics, sys


def minutes(s, now):
    """HH:MM as minutes since midnight; more than 12 hours before now is tomorrow's"""
    if not s: return None
    h, m = map(int, s.split(':'))
    v = h * 60 + m
    return v + 1440 if v < now - 720 else v


def hm(v):
    v = round(v) % 1440
    return f'{v // 60:02d}:{v % 60:02d}'


def status(spec, now):
    steps = spec['steps']
    T = lambda s: minutes(s, now)
    # what has finished by `now` (a replay ignores what came after)
    done = {s['name'] for s in steps if s.get('end') and T(s['end']) <= now}
    started = lambda s: s.get('start') and T(s['start']) <= now
    ratios = [(T(s['end']) - T(s['start'])) / s['guess'] for s in steps
              if s['name'] in done and s.get('start') and s.get('guess')]
    # equal parts of a running step, measured: each part's time since the one before (or the step's start)
    def part_times(s):
        ends = sorted(T(t) for t in s.get('parts_done', []) if T(t) <= now)
        prev, out = T(s['start']), []
        for e in ends: out.append(e - prev); prev = e
        return out
    measured_parts = sum(len(part_times(s)) for s in steps if started(s) and s['name'] not in done and s.get('parts'))
    if ratios:
        k = (min(ratios), statistics.median(ratios), max(ratios))
        n = len(ratios)
        basis = (f'measured: 1 finished step took {k[1]:.2f}x its guess, so no spread yet' if n == 1 else
                 f'measured: steps took {k[0]:.2f}x to {k[2]:.2f}x their guesses (median {k[1]:.2f}x) over {n} finished steps')
    else:
        k, basis = (0.5, 1.0, 2.0), 'nothing finished yet: half to twice the guesses'
    if measured_parts:
        basis += f'; running steps by their own parts ({measured_parts} timed)'

    fin = [{} for _ in range(3)]
    for i in range(3):
        lane_free = {}
        for s in steps:
            name, lane = s['name'], s.get('lane', 'me')
            if name in done:
                fin[i][name] = T(s['end']); lane_free[lane] = max(lane_free.get(lane, 0), T(s['end'])); continue
            if started(s):
                t0 = T(s['start'])
                pt = part_times(s) if s.get('parts') else []
                if pt:
                    rate = (min(pt), statistics.median(pt), max(pt))[i]
                    left = s['parts'] - len(pt)
                    last = max([T(t) for t in s.get('parts_done', []) if T(t) <= now], default=t0)
                    f = last + rate * left
                else:
                    f = t0 + s['guess'] * k[i]
            else:
                t0 = max([lane_free.get(lane, now), now] + [fin[i].get(a, now) for a in s.get('after', [])])
                f = t0 + s['guess'] * k[i]
            fin[i][name] = max(f, now)
            lane_free[lane] = fin[i][name]
    lo, mid, hi = (max(f.values()) for f in fin)
    items = []
    for s in steps:
        if s['name'] in done:
            items.append(dict(name=s['name'], done=True, time=s['end']))
        else:
            st = s.get('state') or ('running' if started(s) else 'waiting')
            if s.get('parts'):
                st += f" ({len([t for t in s.get('parts_done', []) if T(t) <= now])} of {s['parts']})"
            items.append(dict(name=s['name'], state=st, time=hm(fin[1][s['name']])))
    finished = len(done) == len(steps)
    out = dict(title=spec.get('title', 'Progress'), refresh=spec.get('refresh', 20), note=spec.get('note', ''), now=hm(now),
               needles=[dict(title=spec.get('needle_title', 'Done'), label=spec.get('label', 'all done'),
                             estimate=hm(mid), items=items, basis=basis)])
    if not finished and hi - lo >= 1:
        out['needles'][0]['band'] = [hm(lo), hm(hi)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('steps')
    ap.add_argument('--now', help='HH:MM: the status as it was then')
    a = ap.parse_args()
    clock = datetime.datetime.now()
    now = clock.hour * 60 + clock.minute
    if a.now:
        now = minutes(a.now, now)
    print(json.dumps(status(json.load(open(a.steps)), now)))


if __name__ == '__main__':
    main()
