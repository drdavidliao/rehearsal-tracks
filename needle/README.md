# Finish-time needle

A page that shows when a long batch of work should finish: one dial per batch, with a needle at the best guess, a blue band
from the fastest to the slowest pace measured so far, a marker per job (each its own shape and colour, repeated beside
its row in the table, whose rows run in the markers' order round the dial; filled when done, an outline until then), a dashed line at the current time,
and a table of the jobs. It fetches its status every 20 s (or the status's `refresh`) and says when it checked and when it
will check next. It follows the system's light or dark mode.

    python3 needle/server.py STATUS.json              # the job rewrites STATUS.json as it goes
    python3 needle/server.py --cmd "python3 my_status.py"   # or: a command that prints the status, run on every fetch
    python3 needle/server.py --cmd "python3 needle/demo_status.py"   # a made-up batch, to see it

It serves on http://localhost:8765 (`--port` for another). To keep it in Claude Code's side panel, add it to the project's
`.claude/launch.json` (absolute paths) and ask Claude to start it; the page updates itself, with no reloading:

    {"version": "0.0.1", "configurations": [{"name": "needle", "runtimeExecutable": "python3",
      "runtimeArgs": ["/path/to/rehearsal-tracks/needle/server.py", "--cmd", "python3 /path/to/my_status.py"], "port": 8765}]}

The page also works as an OBS Browser Source pointed at the same address.

To see it on a phone on the same Wi-Fi, add `--host 0.0.0.0`; the server prints the address to open, such as
`http://192.168.1.162:8765/pace.html?from=19:00&until=21:00`. Anyone on that network can then open the pages and
`/status` (song and section names, times); it serves nothing else from `needle/`, so the logs in `.rehearsal/` stay
private. It answers only private addresses (192.168.x.x, 10.x.x.x, 172.16-31.x.x, this Mac): a request from the
internet, even through a port forwarded on the router, is refused, and it listens on IPv4 only, so the Mac's public IPv6
addresses don't reach it. Without `--host` only this Mac can reach it.

## Status

    {"title": "Player maps", "refresh": 20, "note": "anything for the subtitle",
     "needles": [
       {"title": "Maps", "label": "all seven done",
        "estimate": "15:05", "band": ["14:40", "15:30"], "basis": "fastest to slowest pace so far, from 3 finished jobs",
        "items": [{"name": "Silver Bells", "done": true, "time": "14:12"},
                  {"name": "Sleigh Ride", "state": "typing (bar 40)", "time": "14:40"}]}]}

Times are `HH:MM` on this machine's clock; one more than 12 hours before now is read as tomorrow's. `now` is added by the
server. A needle with every item done points at the last one's time and says "done". `band` is optional: leave it out
rather than draw one that isn't measured.

## Estimates from measured pace

`pace.finish_times(jobs, slots, lag)` gives each unfinished job's finish (fastest, median and slowest pace among the
finished jobs, per unit of size: pages, bars, minutes of audio) and the whole batch's, with jobs not yet started taking the
next free slot. The band is the spread actually measured, so it narrows or widens as jobs finish; before any job has
finished there is no pace, and a status should give a hand estimate and say so in `basis`. `demo_status.py` uses it.

## Steps of different kinds: `milestones.py`

For a run of unlike steps (transcribe, mark up, separate, map), where the jobs aren't sized alike:

    python3 needle/server.py --cmd "python3 needle/milestones.py STEPS.json"
    python3 needle/milestones.py STEPS.json --now 16:00     # the status as it was at 16:00

Each step has a `guess` in minutes, which only says how big it is next to the others; the work fills in `start` and `end`
(and `parts_done` for a step of equal parts) as it goes. Every finished step measures taken / guessed, and the steps left
are their guesses times the fastest, median and slowest of those: the needle at the median, the band the spread seen. A
step of equal parts that has finished some times the rest at their own pace. Lanes (`lane`) run their steps one after
another and `after` waits for other steps. Before anything finishes the band is half to twice the guesses and the basis
says so; with one finished step it is that step's ratio and no band, since no spread has been measured. The format is
in the script's header.

Two rules for whoever keeps the steps file:

- **Done means checked.** A step gets its `end` only once its output is checked and in place. A first draft still being
  checked or fixed stays running, with a `state` that says so ("draft made; fixing caption collisions"). Marking the draft
  done shows a finish that isn't real, and the reader will notice.
- **No hand-typed bands.** Write guesses only as relative sizes and let the measured steps set the needle and band.
  Hand-set bands, skewed by intuition before any data, missed the real finish every time they were tried; if a band
  must be typed, its reason goes in `basis`.

Update the file at each real transition (a step started, a part or step finished), not in batches afterwards.

Write times to the second (`HH:MM:SS`: `date +%H:%M:%S`, or the mtime of the file a part writes). `HH:MM` still works, but
it rounds both ends of every span: a step can read as taking no time, and a steady 2.6-minute pace as alternating 2 and 3
minutes. The band's fast end is the fastest of those, so on one batch it sat at 01:49, before the stems that every
remaining step waited on could finish (01:51); timed from the stems' file mtimes, the parts were 2:34 to 2:50 apart and the
fast end moved to 01:52. A span between minute-only stamps counts as at least half a minute.

Replayed on a song whose guesses were four to ten times too long, it said 16:11 from the first
finished step on, for a finish at 16:10; the hand-set bands had started at 16:50, then 16:30, 16:15 and 16:20.

## Rehearsal: when today's songs will be done

`rehearsal_status.py` gives one needle for the songs tagged "Today" in the Rehearsal Player, with a dot per song, so the
singers can see whether there's time for questions:

    python3 needle/server.py --cmd "python3 needle/rehearsal_status.py"            # songs tagged Today
    python3 needle/server.py --cmd "python3 needle/rehearsal_status.py --songs DIR DIR"   # or these, in this order
    python3 needle/server.py --cmd "python3 needle/demo_rehearsal.py" --port 8767  # a made-up rehearsal, to see it

The first status asked for starts a poller (`rehearsal_status.py --poll`) that reads the player's
`http://localhost:8766/state` every second and appends each change of song, bar, play/pause, Balanced/part mode, tempo
or checked sections to `needle/.rehearsal/<date>.jsonl` (a day runs to 06:00, so a rehearsal past midnight stays in
one file; `--log` for another). It stops itself once no status has
been asked for in 10 minutes. Each status replays that day's log; `--at 19:40 --no-poll` gives the status as it was at
19:40 (a time more than 12 hours before the log's first event is the next day's), for looking back over a logged rehearsal.

- **Songs**: folders whose `player tags.json` (or a folder above, as the player's tags go) has "Today", found as the
  player finds songs (Spotlight's `player map.json`s, and `~/Dropbox`), in name order; `--songs` gives them in the order
  they'll be rehearsed. The song playing comes first, then the rest in that order.
- **What's to rehearse**: each song's checked sections (from `/state` once the song has been loaded, else the player's
  `sections:<folder>` default); none checked means the whole song. A section runs from its letter's bar to the bar
  before the next letter, with an Intro for bars before the first, as in the player.
- **Playing time**: from the map's bar times, scaled by `song_tempo/tempo` at the tempo the song was last played at.
- **Done**: a section played through in Balanced mode without a jump, from its first bar (where the player was paused
  before it started) to its last; or, once anything later in the song is played, or another of today's songs is.
  Done stays done if the rehearsal goes back.
- **Pace**: wall-clock time over playing time. At each finish, the time since the last finish (since a song of today's
  was first played, for the first) goes to the sections finished then that were played at all; sections skipped
  unplayed just leave the list. The needle is the last finish plus the remaining playing time at the overall pace
  (all the time over all the playing time so far); the band uses the fastest and slowest single finish. Before any
  finish there is no band and the pace is `--guess` (3× playing time). The estimate moves only when a section
  finishes (or a tempo changes), and the subtitle says when the clock has run past it.

Talking, a break or warm-ups after a song is first played all count as rehearsal time, so they show up in the pace: a
section sung straight through right after another finished gives a pace near 1× and widens the band.

## Rehearsal pace: the schedule to keep

`pace.html` on the same server shows a suggested pace, not where the rehearsal is: the time from a minute after the
rehearsal starts to a minute before it ends (for announcements), split over today's checked sections in rehearsal order
by playing time at each song's own tempo. Each song is a row of its section letters, each as wide as its share of the
time, with the time each is due to start under it (as many as fit), and a cursor slides across them by the clock, the
section under it lit. Give the start and end in the address:

    python3 needle/server.py --cmd "python3 needle/rehearsal_status.py --no-poll" --host 0.0.0.0
    http://localhost:8765/pace.html?from=19:00&until=21:00

or to the status script (`--from 19:00 --until 21:00`; the address wins). `--no-poll` because the page doesn't follow the
player: it reads the songs and their checked sections once a minute, in case they change.
