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

A finished step marked `"hidden": true` still counts in the measured pace but is left out of the table, so a long run
can list only what is still to do.

Before anything has been measured there is nothing to go on but the guesses: the band is then half to twice them, and the
basis says so. A step is "end"ed (done) only once its checks have passed and its output is in place.

A step is timed against the finished steps of its own lane (the same kind of work: agents' transcriptions, my checks),
and against every finished step only until its lane has one.

When the band is more than 40 minutes wide the status also forecasts when it will be a quarter as wide: it plays the steps
left forward at the median pace, one finish at a time, recomputing the band as it would then stand (a lane's first finish
gives it its own pace, which is what narrows it), and gives the first such finish before the last, or says the band stays
wide until the end. It assumes the median pace and no pauses, and is recomputed on every check.

Times may be "YYYY-MM-DD HH:MM[:SS]", exactly that, or HH:MM[:SS], its most recent occurrence before the clock (a stamp is
written when it happens; five minutes' grace for a clock a little ahead), so an undated run crosses midnight too but a
file is read against today. Every time the status gives is dated, and the page shows another day's with its weekday.
Write seconds (`date "+%Y-%m-%d %H:%M:%S"`, or a file's mtime). Spans between minute-only stamps
are rounded both ways: a step can read as taking no time, and a steady pace as alternating 2 and 3 minutes, which pulls the
band's fast end in. Such a span counts as at least half a minute.
"""
import argparse, copy, datetime, json, statistics, sys

# Every time is counted in minutes from the midnight that starts REF (today), so a run that crosses midnight just goes on
# counting past 1440, and every time the status reports carries its date.
REF = datetime.date.today()
BASE = datetime.datetime.combine(REF, datetime.time())


def clock():
    return (datetime.datetime.now() - BASE).total_seconds() / 60


# An undated stamp written a little after the clock read (a file's mtime, a `date` a second ahead) is still today's.
SKEW = 5


def stamp(s, real_now):
    """a stamp as (minutes from REF's midnight, known only to the minute). "YYYY-MM-DD HH:MM[:SS]" is exactly that; an
    undated HH:MM[:SS] is its most recent occurrence before the real clock (not a replay's --now: a stamp is written when
    it happens, so it is never in the future)"""
    if not s: return None
    s = s.strip()
    day = None
    if ' ' in s:
        d, s = s.split()
        day = (datetime.date.fromisoformat(d) - REF).days
    f = s.split(':')
    v = int(f[0]) * 60 + int(f[1]) + (float(f[2]) / 60 if len(f) > 2 else 0)
    if day is not None: v += 1440 * day
    else:
        v += 1440 * ((real_now + SKEW - v) // 1440)   # the latest v + 1440k at or before now (+ the skew)
    return (v, len(f) < 3)


# A time written HH:MM is only known to the minute, so a span between two of them can read 0 when it took most of a minute,
# and a 2.6-minute pace reads as 2 or 3. Such a span counts as at least half a minute; stamps with seconds have no floor.
COARSE_FLOOR = 0.5


def span(a, b):
    """minutes from stamp a to stamp b"""
    d = b[0] - a[0]
    return max(d, COARSE_FLOOR) if a[1] or b[1] else d


def dated(v):
    """minutes from REF's midnight as "YYYY-MM-DD HH:MM\""""
    return (BASE + datetime.timedelta(minutes=round(v))).strftime('%Y-%m-%d %H:%M')


def trio(r):
    return (min(r), statistics.median(r), max(r))


def project(steps, now):
    """when each step finishes at the fastest, median and slowest measured pace, as things stood at `now`"""
    done = {s['name'] for s in steps if s.get('end') and s['end'][0] <= now}
    started = lambda s: s.get('start') and s['start'][0] <= now
    allr, lane_r = [], {}
    for s in steps:
        if s['name'] in done and s.get('start') and s.get('guess'):
            r = span(s['start'], s['end']) / s['guess']
            allr.append(r); lane_r.setdefault(s.get('lane', 'me'), []).append(r)
    # a step is timed against the finished steps of its own lane (the same kind of work); until its lane has one, against
    # every finished step; before anything has finished, half to twice its guess
    def k_of(s):
        r = lane_r.get(s.get('lane', 'me')) or allr
        return trio(r) if r else (0.5, 1.0, 2.0)
    def part_times(s):
        ends = sorted((t for t in s.get('parts_done', []) if t[0] <= now), key=lambda t: t[0])
        prev, out = s['start'], []
        for e in ends: out.append(span(prev, e)); prev = e
        return out, ends
    fin, t0s = [{} for _ in range(3)], [{} for _ in range(3)]
    for i in range(3):
        lane_free = {}
        for s in steps:
            name, lane = s['name'], s.get('lane', 'me')
            if name in done:
                fin[i][name] = s['end'][0]; lane_free[lane] = max(lane_free.get(lane, -1e9), s['end'][0]); continue
            if started(s):
                t0 = s['start'][0]
                pt, ends = part_times(s) if s.get('parts') else ([], [])
                if pt:
                    f = (ends[-1][0] if ends else t0) + trio(pt)[i] * (s['parts'] - len(pt))
                else:
                    f = t0 + s['guess'] * k_of(s)[i]
            else:
                t0 = max([lane_free.get(lane, now), now] + [fin[i].get(a, now) for a in s.get('after', [])])
                f = t0 + s['guess'] * k_of(s)[i]
            t0s[i][name] = t0
            fin[i][name] = max(f, now)
            lane_free[lane] = fin[i][name]
    lo, mid, hi = (max(f.values()) for f in fin)
    return dict(done=done, fin=fin, t0=t0s, lo=lo, mid=mid, hi=hi, allr=allr, lane_r=lane_r, started=started,
                part_times=part_times)


# When the band is wider than this many minutes, the status also forecasts when it will have narrowed to a quarter.
WIDE = 40


def forecast(steps, now, width):
    """play the steps left forward at the median pace, one finish at a time, and recompute the band as it would then stand;
    the first finish after which it is a quarter as wide or less (not the last one, where it closes anyway).
    Returns (when, width then, the step that finished) or None."""
    sim, t = copy.deepcopy(steps), now
    for _ in range(len(sim)):
        P = project(sim, t)
        left = [s for s in sim if s['name'] not in P['done']]
        if len(left) <= 1: return None
        nxt = min(left, key=lambda s: P['fin'][1][s['name']])
        te = P['fin'][1][nxt['name']]
        if not P['started'](nxt): nxt['start'] = (P['t0'][1][nxt['name']], False)
        nxt['end'], t = (te, False), te
        Q = project(sim, t)
        if Q['hi'] - Q['lo'] <= width / 4: return t, Q['hi'] - Q['lo'], nxt['name']
    return None


def status(spec, now, real_now=None):
    real_now = clock() if real_now is None else real_now
    S = lambda x: stamp(x, real_now)
    steps = []
    for s in spec['steps']:
        s = dict(s)
        for key in ('start', 'end'):
            if s.get(key): s[key] = S(s[key])
        if 'parts_done' in s: s['parts_done'] = [S(t) for t in s['parts_done']]
        steps.append(s)
    P = project(steps, now)
    done, allr, lane_r = P['done'], P['allr'], P['lane_r']
    if allr:
        k = trio(allr)
        n = len(allr)
        basis = (f'measured: 1 finished step took {k[1]:.2f}x its guess, so no spread yet' if n == 1 else
                 f'measured: steps took {k[0]:.2f}x to {k[2]:.2f}x their guesses (median {k[1]:.2f}x) over {n} finished steps')
        own = sorted({s.get('lane', 'me') for s in steps if s['name'] not in done} & set(lane_r))
        if own:
            basis += '; steps left are timed against their own lane: ' + '; '.join(
                f'{ln} {len(lane_r[ln])} finished' + (f', {min(lane_r[ln]):.2f}x to {max(lane_r[ln]):.2f}x'
                                                      if len(lane_r[ln]) > 1 else f', {lane_r[ln][0]:.2f}x') for ln in own)
    else:
        basis = 'nothing finished yet: half to twice the guesses'
    measured_parts = sum(len(P['part_times'](s)[0]) for s in steps if P['started'](s) and s['name'] not in done and s.get('parts'))
    if measured_parts:
        basis += f'; running steps by their own parts ({measured_parts} timed)'
    items = []
    for s in steps:
        if s['name'] in done:
            if not s.get('hidden'): items.append(dict(name=s['name'], done=True, time=dated(s['end'][0])))
        else:
            st = s.get('state') or ''
            if not st or st.startswith('done'):   # a replay before the step finished: not the state it was given later
                st = 'running' if P['started'](s) else 'waiting'
            if s.get('parts'):
                st += f" ({len([t for t in s.get('parts_done', []) if t[0] <= now])} of {s['parts']})"
            items.append(dict(name=s['name'], state=st, time=dated(P['fin'][1][s['name']])))
    finished = len(done) == len(steps)
    needle = dict(title=spec.get('needle_title', 'Done'), label=spec.get('label', 'all done'),
                  estimate=dated(P['mid']), items=items, basis=basis)
    width = P['hi'] - P['lo']
    if not finished and width >= 1:
        needle['band'] = [dated(P['lo']), dated(P['hi'])]
    if not finished and width > WIDE:
        f = forecast(steps, now, width)
        needle['forecast'] = (dict(width=round(width), time=dated(f[0]), narrow=round(f[1]), after=f[2]) if f else
                              dict(width=round(width), time=None))
    return dict(title=spec.get('title', 'Progress'), refresh=spec.get('refresh', 20), note=spec.get('note', ''),
                now=dated(now), needles=[needle])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('steps')
    ap.add_argument('--now', help='"YYYY-MM-DD HH:MM[:SS]" or HH:MM[:SS] (its latest occurrence): the status as it was then')
    a = ap.parse_args()
    real = clock()
    now = stamp(a.now, real)[0] if a.now else real
    print(json.dumps(status(json.load(open(a.steps)), now, real)))


if __name__ == '__main__':
    main()
