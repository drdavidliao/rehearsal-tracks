# Finish-time needle

A page that shows when a long batch of work should finish: one dial per batch, with a needle at the best guess, a blue band
from the fastest to the slowest pace measured so far, a dot per job (green when done), a dashed line at the current time,
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

## Rehearsal: when today's songs will be done

`rehearsal_status.py` gives one needle for the songs tagged "Today" in the Rehearsal Player, with a dot per song, so the
singers can see whether there's time for questions:

    python3 needle/server.py --cmd "python3 needle/rehearsal_status.py"            # songs tagged Today
    python3 needle/server.py --cmd "python3 needle/rehearsal_status.py --songs DIR DIR"   # or these, in this order
    python3 needle/server.py --cmd "python3 needle/demo_rehearsal.py" --port 8767  # a made-up rehearsal, to see it

The first status asked for starts a poller (`rehearsal_status.py --poll`) that reads the player's
`http://localhost:8766/state` every second and appends each change of song, bar, play/pause, Balanced/part mode, tempo
or checked sections to `needle/.rehearsal/<date>.jsonl` (`--log` for another file). It stops itself once no status has
been asked for in 10 minutes. Each status replays that day's log; `--at 19:40 --no-poll` gives the status as it was at
19:40, for looking back over a logged rehearsal.

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
