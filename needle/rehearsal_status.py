#!/usr/bin/env python3
"""When today's songs will be rehearsed, for the needle page: server.py --cmd "python3 rehearsal_status.py".

    rehearsal_status.py [--songs DIR ...] [--log FILE] [--guess 3]   print the status (starting the poller if it isn't running)
    rehearsal_status.py --poll [--log FILE]                         poll the player's /state every second, logging changes
    rehearsal_status.py --log FILE --at 19:40 --no-poll             the status as it was at 19:40, from a logged rehearsal

Today's songs are the song folders whose "player tags.json" has "Today" (or --songs, in rehearsal order). Each song's
sections to rehearse are the ones checked in the player (its /state "marked", else the player's defaults); with none
checked, the whole song. A section's playing time comes from the map's bar times, scaled by song_tempo/tempo at the
tempo it was last heard at. A section is done when it is played through in Balanced mode, from its first bar to its
last, or when the player plays a later section of the song, or another of today's songs.

The rehearsal's pace is wall-clock time over playing time: at each finish, the time since the last one (or since a
song of today's was first played) over the playing time of the sections finished then that were played at all
(skipped ones just leave the list). The estimate is the last finish plus the remaining playing time at the overall
pace; the band uses the fastest and the slowest pace measured. Before anything has finished the pace is --guess
and there is no band. The estimate moves only when a section finishes.
"""
import argparse, datetime, glob, json, os, plistlib, re, signal, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, '.rehearsal')
STATE_URL = 'http://localhost:8766/state'
EPS = 0.002
KEYS = ('folder', 'song', 'playing', 'bar', 'pass', 'section', 'mode', 'tempo', 'song_tempo', 'marked')


def hm(t): return time.strftime('%H:%M', time.localtime(t))
def today_log():
    """one log per rehearsal day, which runs to 06:00, so a rehearsal past midnight stays in one file"""
    return os.path.join(STORE, (datetime.datetime.now() - datetime.timedelta(hours=6)).date().isoformat() + '.jsonl')


# ---- polling ---------------------------------------------------------------------------------------------------------

def poll(log, url, quiet_exit=600):
    """Append the player's state to log whenever it changes (not its time alone). Stops when nobody has asked for the
    status for quiet_exit seconds, so a forgotten poller doesn't run all week."""
    os.makedirs(STORE, exist_ok=True)
    open(os.path.join(STORE, 'poll.pid'), 'w').write(str(os.getpid()))
    beat = os.path.join(STORE, 'asked')
    last = None
    while True:
        if os.path.exists(beat) and time.time() - os.path.getmtime(beat) > quiet_exit: return
        try:
            s = json.load(urllib.request.urlopen(url, timeout=2))
            rec = {k: s.get(k) for k in KEYS} if s.get('song') else {'folder': None}
            if rec.get('folder'): rec['time'] = s.get('time')
        except Exception:
            rec = {'off': True}
        key = {k: v for k, v in rec.items() if k != 'time'}
        if key != last:
            last = key
            with open(log or today_log(), 'a') as f: f.write(json.dumps(dict(wall=round(time.time(), 2), **rec)) + '\n')
        time.sleep(1)


def ensure_poller(log):
    os.makedirs(STORE, exist_ok=True)
    open(os.path.join(STORE, 'asked'), 'w').write(str(time.time()))
    try:
        os.kill(int(open(os.path.join(STORE, 'poll.pid')).read()), 0); return
    except Exception:
        pass
    cmd = [sys.executable, os.path.abspath(__file__), '--poll'] + (['--log', log] if log else [])
    subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---- songs -----------------------------------------------------------------------------------------------------------

def natural(s): return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', s)]


def is_scratch(p):
    home = os.path.expanduser('~')
    if p.startswith(('/private/', '/tmp/', '/var/')) or '/.Trash/' in p or '/.build/' in p: return True
    return p.startswith(home + '/Library/') and not p.startswith(home + '/Library/CloudStorage/')


def folder_tags(p):
    """the player's SongLibrary.folderTags: the folders a song is in, from the top"""
    home = os.path.expanduser('~') + '/'
    if not p.startswith(home): return []
    parts = p[len(home):].split('/')[:-1]
    if parts[:2] == ['Library', 'CloudStorage']: parts = parts[2:]
    if parts and any(parts[0].startswith(t) for t in ('Dropbox', 'Documents', 'Desktop', 'Downloads', 'Music', 'Cowork')): parts = parts[1:]
    out = []
    for t in parts:
        for above in out:
            if t.startswith(above + ' '): t = t[len(above) + 1:]
        if t not in out: out.append(t)
    return out


def today_songs(tag='Today'):
    try: found = subprocess.run(['mdfind', '-name', 'player map.json'], capture_output=True, text=True, timeout=20).stdout.split('\n')
    except Exception: found = []
    found += glob.glob(os.path.expanduser('~/Dropbox/**/player map.json'), recursive=True)
    out = set()
    for f in found:
        if not f.endswith('/player map.json'): continue
        d = os.path.dirname(f)
        if is_scratch(d): continue
        try: tags = json.load(open(os.path.join(d, 'player tags.json')))
        except Exception: tags = []
        if tag in tags or tag in folder_tags(d): out.add(d)
    return sorted(out, key=lambda d: natural(os.path.basename(d)))


def player_marks():
    """sections:<folder> from the player's defaults"""
    try:
        d = plistlib.loads(subprocess.run(['defaults', 'export', 'local.rehearsal.player', '-'], capture_output=True, timeout=10).stdout)
        return {k[len('sections:'):]: v for k, v in d.items() if k.startswith('sections:')}
    except Exception:
        return {}


class Song:
    def __init__(self, folder, marked):
        m = json.load(open(os.path.join(folder, 'player map.json')))
        self.folder, self.name, self.tempo = folder, os.path.basename(folder), m['tempo']
        self.heard = m['tempo']                       # the tempo it was last played at
        bars = m['bars']
        self.starts = [b['beat_t'][0] for b in bars]
        lettered = [i for i, b in enumerate(bars) if b.get('letter')]
        if lettered:
            secs = ([('Intro', 0)] if lettered[0] > 0 else []) + [(bars[i]['letter'], i) for i in lettered]
        else:
            secs = [('whole song', 0)]
        self.secs = []                                # (name, first bar index, last bar index, seconds at the song's tempo)
        for k, (name, a) in enumerate(secs):
            z = secs[k + 1][1] - 1 if k + 1 < len(secs) else len(bars) - 1
            self.secs.append((name, a, z, bars[z]['end_t'] - bars[a]['beat_t'][0]))
        self.set_marked(marked)
        self.done = {}                                # section index -> wall time it finished
        self.visited = set()

    def set_marked(self, names):
        self.marked = [k for k, s in enumerate(self.secs) if s[0] in (names or [])] or list(range(len(self.secs)))
        self.whole = not names

    def bar(self, t):
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= t + EPS: lo = mid
            else: hi = mid - 1
        return lo

    def sec(self, i): return max(k for k, s in enumerate(self.secs) if s[1] <= i)
    def play(self, k): return self.secs[k][3] * self.tempo / self.heard
    def left(self): return [k for k in self.marked if k not in self.done]


# ---- replay ----------------------------------------------------------------------------------------------------------

def replay(events, songs):
    """Goes through the logged states and returns the pace samples [(wall seconds, playing seconds)], the last finish's
    wall time (or the first play's), and the song playing last; the songs' done and visited are filled in."""
    by = {s.folder: s for s in songs}
    samples, anchor, current = [], None, None
    run, prev = None, None                         # run: [song, first bar index, furthest bar index, song time, wall]

    def finish(song, ks, wall):
        nonlocal anchor
        ks = [k for k in ks if k not in song.done]
        for k in ks: song.done[k] = wall
        played = [k for k in ks if k in song.visited]
        if played and anchor is not None:
            samples.append((wall - anchor, sum(song.play(k) for k in played)))
            anchor = wall

    for e in events:
        s = by.get(e.get('folder'))
        if s is None:
            run, prev = None, e; continue
        if e.get('marked') is not None: s.set_marked(e['marked'])
        if e.get('tempo'): s.heard = e['tempo']
        i = s.bar(e.get('time') or 0); k = s.sec(i); w = e['wall']
        if e.get('playing'):
            if anchor is None: anchor = w
            if current is not None and current is not s: finish(current, current.left(), w)
            current = s
            s.visited.add(k)
            finish(s, [j for j in s.marked if j < k], w)
        # a run: played in Balanced without a jump; it starts where the player was paused just before
        # (a pause ends it, the bar it paused in counting as reached)
        t = e.get('time') or 0
        if run and run[0] is s and e.get('mode') == 'balanced':
            speed = (e.get('tempo') or s.tempo) / s.tempo
            ok = run[3] - EPS <= t <= run[3] + (w - run[4]) * speed + 2
            run = [s, run[1], max(run[2], i), t, w] if ok else None
        else:
            run = None
        if run is None and e.get('playing') and e.get('mode') == 'balanced':
            p = prev if prev and prev.get('folder') == s.folder and not prev.get('playing') else None
            pi = s.bar(p.get('time') or 0) if p else i
            run = [s, min(pi, i), i, t, w]
        if run:
            for j in range(run[1], run[2] + 1): s.visited.add(s.sec(j))
            finish(s, [j for j in s.marked if run[1] <= s.secs[j][1] and run[2] >= s.secs[j][2]], w)
        if not e.get('playing'): run = None
        prev = e
    return samples, anchor, current


def status(songs, events, now, guess):
    samples, anchor, current = replay(events, songs)
    rates = [a / b for a, b in samples if b > 0]
    if rates:
        r = (min(rates), sum(a for a, _ in samples) / sum(b for _, b in samples), max(rates))
        n = len(rates)
        basis = f'fastest to slowest pace so far ({r[0]:.1f}× to {r[2]:.1f}× playing time), from {n} finish{"es" if n != 1 else ""}'
    else:
        r, basis = (guess, guess, guess), None
    order = ([current] if current and current.left() else []) + [s for s in songs if s is not current and s.left()]
    start = anchor if anchor is not None else now
    cum, items, est = 0.0, {}, {}
    for s in order:
        cum += sum(s.play(k) for k in s.left())
        est[s.folder] = tuple(start + x * cum for x in r)
    for s in songs:
        n_m = len(s.marked); n_d = sum(1 for k in s.marked if k in s.done)
        which = 'whole song' if s.whole else ', '.join(s.secs[k][0] for k in s.marked)
        if not s.left():
            items[s.folder] = dict(name=s.name, done=True, time=hm(max(s.done[k] for k in s.marked)))
        else:
            st = f'{n_d} of {n_m} done' if n_d else which
            if s is current: st = 'now: ' + st
            items[s.folder] = dict(name=s.name, state=st, time=hm(est[s.folder][1]))
    done_first = sorted([s for s in songs if not s.left()], key=lambda s: max(s.done[k] for k in s.marked))
    rows = [items[s.folder] for s in done_first] + [items[s.folder] for s in order]
    secs_all = sum(len(s.marked) for s in songs); secs_done = sum(1 for s in songs for k in s.marked if k in s.done)
    last = est[order[-1].folder] if order else None
    needle = dict(title='Today', label="today's songs done", items=rows,
                  estimate=hm(last[1]) if last else None)
    if last and basis: needle.update(band=[hm(last[0]), hm(last[2])], basis=basis)
    elif last: needle['basis'] = f'no section finished yet: a guess of {guess:g}× playing time'
    note = f'{secs_done} of {secs_all} sections done'
    if last and last[1] < now: note += ' · running past the estimate'
    if not songs: note = 'no song is tagged Today'
    return dict(title='Rehearsal', refresh=10, note=note, needles=[needle])


def clock(s, first):
    """HH:MM after the log's first event (the next day's if more than 12 hours before it), or epoch seconds"""
    if ':' not in s: return float(s)
    h, m = map(int, s.split(':'))
    t = datetime.datetime.combine(datetime.date.fromtimestamp(first), datetime.time(h, m)).timestamp()
    return t + 86400 if t < first - 12 * 3600 else t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--songs', nargs='*', help="today's song folders, in rehearsal order (default: those tagged Today)")
    ap.add_argument('--tag', default='Today')
    ap.add_argument('--log', help='the event log (default: needle/.rehearsal/<today>.jsonl)')
    ap.add_argument('--poll', action='store_true', help='poll the player and log what changes')
    ap.add_argument('--url', default=STATE_URL)
    ap.add_argument('--no-poll', action='store_true', help="don't start the poller (for a logged rehearsal)")
    ap.add_argument('--at', help='the status as at this time (HH:MM, or epoch seconds); later events are ignored')
    ap.add_argument('--guess', type=float, default=3.0, help='wall-clock over playing time before anything has finished')
    a = ap.parse_args()
    if a.poll: return poll(a.log, a.url)
    if not a.no_poll: ensure_poller(a.log)
    log = a.log or today_log()
    events = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    now = clock(a.at, events[0]['wall'] if events else time.time()) if a.at else time.time()
    events = [e for e in events if e['wall'] <= now]
    folders = a.songs if a.songs is not None else today_songs(a.tag)
    marks = player_marks()
    songs = []
    for f in folders:
        f = os.path.abspath(os.path.expanduser(f)).rstrip('/')
        try: songs.append(Song(f, marks.get(f)))
        except Exception as e: print(f'{f}: {e}', file=sys.stderr)
    s = status(songs, events, now, a.guess)
    if a.at: s['now'] = hm(now)
    print(json.dumps(s))


if __name__ == '__main__':
    main()
