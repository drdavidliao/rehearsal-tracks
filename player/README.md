# Rehearsal Player

A Mac app that shows a marked score and plays a song's separated stems in time with it. Click a beat to start there,
choose a part, and choose a tempo. It opens on the right 60% of the screen, with the controls down its left edge and one page of score at the window's full height.

On another system, see [PORTING.md](PORTING.md): enough to have an AI coding assistant write your own version.

## Build

Needs Xcode's tools and `brew install rubberband`.

    player/build.sh

This makes `player/build/Rehearsal Player.app`. Rubber Band and libsamplerate are linked statically, so the app runs
on its own. Rubber Band is GPL or commercial: keep that in mind before giving the app to anyone.

## A song

The app opens a song folder that has a `player map.json`. Make one with:

    python3 player/make_map.py "song folder" --reader-pdf "... Full score copy.pdf" --score "... (lesson marks).pdf" \
        --xml "....musicxml" --stems "S=...wav" "A=...wav" "T=...wav" "B=...wav" "I=...wav"

`--reader-pdf` is the vector score the bar and beat positions are read from, through `dorico_reader.py`. `--score` is
what the app shows, with the same pages. `I` is the one instrumental stem. Times come from the MusicXML's tempo marks,
so this suits tracks rendered to the score's tempo. The script fits the time of bar 1 from the piano's on-beat attacks
and prints the drift by section: look at that before trusting a new song. A song with a rit or a fermata that the
MusicXML's tempo marks don't describe would need its beat times measured instead, except a rit to the end of the song: a
rit, riten or rall mark bends the times from its bar on, by a smooth curve fitted to the stems' attacks and to where the sound
ends. The script prints the curve; the fit assumes the rit runs to the last bar. So far only one song has been mapped.

## Keys

| Key | Does |
| --- | --- |
| Space | play or stop |
| click / double-click | go to that beat / go there and play |
| digits, Return | go to that bar (the Bar box does the same and also takes a letter) |
| Return | back to where you last started |
| capital letter | go to that rehearsal letter |
| ← → | a bar back or on (with Shift, a beat) |
| ↑ ↓ | tempo up or down by 1 |
| m s a t b o | Balanced, Soprano, Alto, Tenor, Bass only, Other |
| v / i | next stretch method for the voices / instruments |
| l | loop on or off |
| right-click a note | mute or transpose it |
| ⌘F | hear without fixes |
| ⌘2 | two pages side by side |
| ⌘O | open a song folder |

## The mix

In `Sources/CEngine/engine.cpp`.

- Trims: S 0, A -3, T -3, B 0 dB. Pan on Logic's knob scale (-64 to +63): S -45, A -15, T +15, B +45. Instruments 0 dB, centred.
- The whole mix is -3 dB until the Volume box says otherwise. The setting is remembered.
- The Source files switch says what the voice files are, and is remembered for each song. It changes "only" and "Other", not Balanced.
- With part-predominant files (each has its part loudest and the others bleeding through):
  - "Only": that voice +6 dB on top of its trim, keeping its pan; the other voices off; instruments on.
  - "Other": the voices checked, each with a boost on top of its trim: two +3 dB, three +1.5 dB.
- With purely isolated files (one voice per file), for "only" and for "Other": the voices heard at 0 dB in place of their trims,
  the others at -18 dB, all keeping their pans.
- In "Other", none checked is the instruments alone, and checking all four is Balanced, with either kind of file. Gains are worked
  out from the voices each audio block, so no boost is left behind.
- A stereo stem pans as a balance with a constant-power law, unity at centre.
- Past 0.9 the output rounds off smoothly towards 1 so a boosted part can't hard-clip. Below that the samples are untouched.

The menu at the top right chooses the Core Audio output device. The choice is remembered. If that device is
unplugged, sound goes to the system output until it's chosen again.

## Looping

The Loop boxes take a start and end bar, or a rehearsal letter (to the end of that letter); Return turns the loop on. Green
lines mark it. Reaching the end by playing goes back to the start. A click past the end plays on, and a click before the
start plays into the loop.

## Correcting a note

Right-click a note on a voice's staff to mute it or move it up or down by semitones. Tied notes count as one, and only
that voice's stem changes. A ring on the note shows the fix. Once a note has a fix, the same menu nudges its start and end
by 20 ms or removes it. ⌘F hears the song without fixes. Fixes are kept in `player fixes.json` in the song folder.

A note's times are in `player map.json`: `make_map.py` starts from the score, with swing, and moves each start to the
attack it finds in the stem and each end to the next note or to where the sound dies away. A mute fades over up to 12 ms
inside the note. A transpose is a Rubber Band R3 pitch shift with the formants kept, of the note with 0.3 s of sound
either side, blended in over the same 12 ms, so the audio outside the note isn't touched at the song's own tempo. At
another tempo the corrected voice's stem is rendered again, so its waveform changes throughout, though not its timing.

## Tempo

The song's own tempo plays the files themselves. Any other tempo is rendered, by the method chosen in the Stretch menu,
separately for the voices and the instruments (`v` and `i` step through them during playback):

- Rubber Band R3 with the channels apart (the default), or together, which the library says trades some fidelity for stereo focus.
- Signalsmith Stretch, with its default blocks or short ones (50 ms, 15 ms).
- PSOLA, for the voices only: for a stem with one line. Whole periods of the sound are repeated or dropped, not phase-adjusted.

Nothing waits for a whole render. A new tempo or fix is rendered from a second ahead of the playhead, and playback moves to it
there, with a short fade. A jump past what's rendered starts another render there. Behind that, the whole of each changed stem
renders from its start, which is what's kept. The playhead stays on one render until it stops or jumps, so it never crosses a
join between two. The
stems used last are kept in `~/Library/Caches/Rehearsal Player`, up to 4 GB. Each stem has its own file per tempo and
set of fixes, so a fix to one voice re-renders only that voice.

`enginetest` writes the mix of every mode to raw float files, for measuring against the stems.
