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
