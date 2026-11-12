# Rehearsal Player

A Mac app that shows a marked score and plays a song's separated stems in time with it. Click a beat to start there,
choose a part, and choose a tempo. It opens on the right 60% of the screen, with the controls down its left edge and one page of score at the window's full height.

On another system, see [PORTING.md](PORTING.md): enough to have an AI coding assistant write your own version.

## Build

Needs Xcode's tools and `brew install rubberband`.

    player/build.sh

This makes `player/build/Rehearsal Player.app`. Rubber Band and libsamplerate are linked statically, so the app runs
on its own. Rubber Band is GPL or commercial: keep that in mind before giving the app to anyone.

The icon is `AppIcon.icns`, drawn by `make_icon.py`.

## A song

The app opens a song folder that has a `player map.json`. Make one with:

    python3 player/make_map.py "song folder" --reader-pdf "... Full score copy.pdf" --score "... (lesson marks).pdf" \
        --xml "....musicxml" --stems "Tenor 1=...wav" "Tenor 2a=...wav" "Tenor 2b=...wav" "Baritone=...wav" "Bass=...wav" "I=...wav"

Each voice stem is named by its MusicXML part, from one to eight of them; `I` is the instrumental stem, left out for a song
without one. The letters `S A A2 T B` still name Soprano, Alto (or Alto 1), Alto 2, Tenor and Bass. The map lists the voices top
to bottom in `voices`, and the Hear list and the Other checkboxes use their names, soloists first. A part whose name starts with
"Solo" is a soloist. A map made before `voices`, with stems `S A T B` and an optional `A2` named in `part_names`, plays as before.

A score that's a scan has no vector PDF to read, so `make_map_scan.py` takes the bars and heads from the pixels through scanproof's projects (SKILL.md 1.2),
the times from the tempo marks and `--anchor BAR=SECONDS`, and shows the scan. Its header has the arguments. Dark is then the page filter.
`--part-stems` there says which stem sings each part, so two parts on one stem make one voice. It follows repeats, endings, a
D.S. or a D.C. (al Coda, al Fine) as `make_map.play_order` reads them from the MusicXML's marks: the notes are timed on a copy
of the MusicXML in the sung order, so every pass of a bar is timed from the stems, and a later pass's notes have ids ending in `'`
(`T1.57.0'`). `--pin` and a guide name a later pass the same way (`57'.1=96.3`). `--swing 0.62` puts swung offbeat eighths
at 0.62 of the beat at any tempo, and with `--warp` fits the voices' attacks there; `--swing-above 140` keeps it to bars at
140 or faster. `--out` writes the map under another name, to compare it with the one in use. `staff_text.py` writes the marks
from a transcription's `@repeat`, `@ending`, `@segno`, `@tocoda`, `@ds`, `@dc`, `@fine` and `@coda` lines.
With no Piano part, as in an unaccompanied score, the time of bar 1 is fitted from each voice's attacks on its own stem.

`--reader-pdf` is the vector score the bar and beat positions are read from, and `--score` is what the app shows, with the same
pages. A Dorico export (Bravura glyphs) is read through `dorico_reader.py`. Any other vector PDF (Sibelius, Finale, MuseScore,
LilyPond, or Verovio's paths) is read through `vector_reader.py` when `--staff` says which staff each part is on, by a label that parts on one
staff share:

    --staff "Tenor 1=TT" "Tenor 2=TT" Baritone=BB Bass=BB --layout "4=TT,BB,P,P"

`--layout` labels a system's staves by how many it has (by default, the labels in order); a label no part has, like `P`, is passed
over. Where systems with the same number of staves differ, `--names "Solo=S" "T=TT" "B=BB"` labels each staff by the name printed
at its left, first match winning. The reader finds staves and barlines from the lines, and noteheads from the music font or, with
none, from filled shapes of a notehead's size; it matches them to the MusicXML's notes bar by bar, and at each onset a part
takes the head nearest its pitch. It prints any bar where the heads and the onsets don't match. A bar's number is the MusicXML's,
so a pickup is bar 0.

A song whose only print is a scan can show an engraving instead: `../xml2ly.py` writes a LilyPond file from the MusicXML, with the
scan's systems and pages if given its scanproof project, and `lilypond` makes the PDF for `--reader-pdf` and `--score`.

`I` is the one instrumental stem. `--trim "Bass=-3.68"` takes a stem down (or up) on top of the voice's own trim, for a stem
exported louder than the others. Times come from the MusicXML's tempo marks, so this suits tracks rendered to the score's tempo;
a repeat is played as written (with first and second endings), and the map lists its bars again for each time through, so the
cursor follows; a repeated bar's notes are timed on its first time through, so a note fix there applies only then. The script fits the
time of bar 1 from the piano's on-beat attacks and prints the drift by section: look at that before trusting a new song. A rit,
riten or rall mark bends the times from its bar on, by a smooth curve fitted to the stems' attacks and to where the sound ends;
the fit assumes the rit runs to the last bar. Where the stems stray from the written tempo in other ways (held fermatas, a
slower intro, tempo marks that don't match the playback), `--warp` fits an offset for every bar from the voices' attacks, letting
it change little from bar to bar and fall less readily than rise, and prints them; `--warp-beat` fits every beat instead, for
singing that bends the time inside a bar (where the MusicXML has the instrumental part, its attacks on the `I` stem
count too, so an introduction or interlude nobody sings in is timed as well), and `--pin BAR.BEAT=SECONDS` fixes a measured time the fit must pass through.

Human-sung tracks are sung freely, and on slow legato singing an attack fit can lock a beat or several bars out and still look
right. `pitch_guide.py FOLDER XML check` says how many of the map's notes the stems actually sing at the written pitch (any
octave): over 0.9 is right, far less is not. For such a song, make the map once, then
`pitch_guide.py FOLDER XML guide GUIDE.txt` times every beat by matching each part's written pitches to its stem, and
`--warp --warp-beat --guide GUIDE.txt` keeps the attack fit within 0.35 s of it (`--from BAR` limits the guide to where it's
needed). The guide follows the bars as sung and writes a bar's later passes with a `'`, which `make_map.py` leaves out. It
finds each stem's part by the stem's key or, where the key isn't a part's name (`T1`), by the map's voice name, and gives no
times before the first sung note. Separated stems come from mp3s whose accompaniment track may start earlier than the singing
(1.000 s in several of Matthew Curtis's sets, 0.000 s in others): measure it by cross-correlating the accompaniment with a
Predominant mix before using it as `I`. The voice stems keep their mix's stereo: in some of his sets the part is on the left
channel and every other voice on the right, in others each part sits at its seat (tenors left, basses right).
`center_stems.py FOLDER --write` keeps the left channel of the first kind and folds the second to mono, so the player's pan
is the only one. Then set the accompaniment's level with `balance_check.py FOLDER BALANCED.mp3 --write`, which matches
the accompaniment's balance against all the voices, as the player mixes them, to the set's Balanced Voices mix: the
Predominant mixes duck it, and levels taken from them are far too soft.

## Keys

| Key | Does |
| --- | --- |
| Space | play or stop |
| click / double-click | go to that beat / go there and play (in a repeat, the time through nearest the playhead) |
| digits, Return | go to that bar (the Bar box does the same and also takes a letter); `17'` or, in the boxes, `17b` is bar 17's second time through a repeat |
| Return | back to where you last started |
| capital letter | go to that rehearsal letter |
| ← → | a bar back or on (with Shift, a beat) |
| ↑ ↓ | tempo up or down by 1 |
| m, o | Balanced, Other |
| s a t b | each section only, top to bottom, the lowest always `b` (two sections are `s b`, three `s a b`; past four, `e f g h` follow) |
| z x y w | soloists only, then the second half of a divided section (Alto 2, Tenor 2b, Bass b) |
| v / i | next stretch method for the voices / instruments |
| l | loop on or off |
| c | instruments (or click) on or off |
| d | light or dark score |
| right-click a note | mute or transpose it |
| ⌘F | hear without fixes |
| ⌘2 | two pages side by side |
| ⌘O | open a song folder (File > Recent Songs has the last 12) |
| ⇧⌘O | find a song by its tags |

## Finding a song

File > Find Songs lists every folder on this Mac with a `player map.json`, through Spotlight, so a new song appears by itself. Click tags in the cloud to narrow the list: a song must have all the
tags chosen, and a tag that would leave nothing is dimmed. Double-click a song to open it, or click one to tag it. Tags, folded at the foot of the sidebar, tags the open song.

A song's folders are its first tags: `Choir/2026 Fall/Song` gives Choir and 2026 Fall, and `Band/Band 2026 Fall/Song` gives Band and 2026 Fall. These can't be removed. Tags you add are in
`player tags.json` in the song folder, so they sync with it and survive a new map.

## Dark mode

Light and Dark under Settings, folded at the foot of the sidebar, or `d`. `make_map.py` also writes a dark copy of the score through `dark_score.py` (it needs `pypdf`),
drawn element by element: notes and rests with their stems, beams, flags, dots and accidentals are warm, and staves, clefs, time
signatures, slurs and words are cool. The colors are at the top of that file. For a song without a dark copy, Dark is a filter on the page.

## The mix

In `Sources/CEngine/engine.cpp`, with each voice's pan and trim worked out in `Sources/RehearsalPlayer/Model.swift`.

- Sections, top to bottom, pan evenly from -45 to +45 on Logic's knob scale (-64 to +63). The outer two are at 0 dB and any between
  at -3 dB. SATB is S -45, A -15, T +15, B +45 with trims 0, -3, -3, 0; three sections pan -45, 0, +45; two, -45 and +45.
- A section split in two sits 5 either side of the section's place, with its trim: Alto 1 and Alto 2 in SATB at -20 and -10, or
  Tenor 2a and 2b in a TTBB at -20 and -10. The names decide: a trailing a or b (Tenor 2a, Bass b), or Soprano or Alto 1 and 2. Tenor 1 and
  Tenor 2, and Baritone and Bass, are sections of their own. A map can say `"section"` for a voice where the names don't show it.
- A soloist is 0 dB and centred. Instruments 0 dB, centred.
- The Instruments / click checkbox, or `c`, takes the instrumental stem out of every mode, for a stem that's a click, say. It's remembered for each song.
- The whole mix is -3 dB until the Volume box says otherwise. The setting is remembered.
- The Each voice file switch ("a single voice" or "part-predominant") says what the voice files are, and is remembered for each song. It changes "only" and "Other", not Balanced.
- With part-predominant files (each has its part loudest and the others bleeding through):
  - "Only": that voice +6 dB on top of its trim, keeping its pan; the other voices off; instruments on.
  - "Other": the voices checked, each with a boost on top of its trim: two +3 dB, three +1.5 dB, four +0.75 dB, halving again for each more.
- With purely isolated files (one voice per file), for "only" and for "Other": the voices heard at 0 dB in place of their trims,
  the others at -18 dB, all keeping their pans.
- In "Other", none checked is the instruments alone, and checking them all is Balanced, with either kind of file. Gains are worked
  out from the voices each audio block, so no boost is left behind.
- A stereo stem pans as a balance with a constant-power law, unity at centre.
- Past 0.9 the output rounds off smoothly towards 1 so a boosted part can't hard-clip. Below that the samples are untouched.

Output, under Settings at the foot of the sidebar, chooses the Core Audio output device. The choice is remembered. If that device is
unplugged, sound goes to the system output until it's chosen again.

## Looping

The Loop boxes take a start and end bar, or a rehearsal letter (to the end of that letter); Return turns the loop on. Green
lines mark it. Reaching the end by playing goes back to the start. A click past the end plays on, and a click before the
start plays into the loop. A tempo change or fix made during a loop takes effect about a second later, carrying round to the start if that
falls past the end.

## Sections to rehearse

The sidebar lists the rehearsal letters, and Intro if there are bars before the first. A checked section gets a blue tint on the
score, from its letter's bar to the bar before the next letter. Uncheck it once it's rehearsed. The checks are remembered for each song.

The letters come from the MusicXML's rehearsal marks. A map made from a scan's typed voices, or from MusicXML without them,
has none until `find_boxes.py FOLDER --write` reads the score's boxed marks (bar numbers or letters in a frame) off the
page and puts them on the map's bars; run it without `--write` first and check its contact sheet. It doesn't find circled
marks, unboxed letters, or a box drawn over the staff, and a score that boxes the first bar number of every system (one scanned
octavo did) has no rehearsal marks to find. A rebuilt map loses them, so run it again after a rebuild.

## A chyron for OBS

While the player runs, it serves a chyron at http://localhost:8766/ (View ▸ Copy Chyron Address for OBS). In OBS, add a
Browser Source at the canvas's size (1920 × 1080, say); its background is see-through. Give it the loader,
`player/chyron-obs.html`, as a file address with any options after `#`:

    file:///Users/davidliao/Cowork/rehearsal-tracks/player/chyron-obs.html#style=broadcast

The loader is there even while the player isn't: it asks the player every half second, shows the chyron once it answers,
and loads it afresh whenever the player restarts, so a rebuilt chyron.html shows without touching OBS. Pointing OBS at
http://localhost:8766/ directly works too, but a source loaded while the player is closed stays blank until it's
refreshed (Refresh cache of current page in its properties), and it keeps the page it loaded across restarts.

It shows the song, ▶ or ❚❚ and where the playhead is, who's heard (Tutti, a part, or the parts checked under Other, with
"(a cappella)" when the accompaniment is off), the loop if one is on, and a box for each section checked to rehearse, the
one playing filled in. Where is said as at rehearsal: "B", "1 after B", "2 before C", otherwise "B: 34"; with marks that
are bar numbers, or before the first mark, "Bar 34". A repeat's later times say so.

When the player opens a different song, the chyron breaks into it like an election-night network: slashes sweep
the picture, NEXT SONG slams in over a band, the title slams down with
a jolt, and after about 4 seconds the title flies into its place and the band shuts. A page
opened mid-song, or the same song coming back after the player was closed, makes no news. `&breaking=0` turns it off.

Chyron ▸ Note names in the sidebar slides in a card of the British and North American names for whole to 32nd notes
(semibreve to demisemiquaver), each with its note drawn, for a London chorus with singers in North America.

There are two looks:

- **Plain** (the default): one dark panel. `?corner=br` (bl, br, tl, tr) for where it sits, `?panel=0` for no panel.
- **Broadcast**: `?style=broadcast`. The title in a tag at top left; a lower third with who's heard on a coloured tab over
  where you are, and when a loop is on, LOOP ↻ on a green tab over its bars; and the sections in a tracker at bottom
  right, or top right for the rest of a song once the lower third grows into it. All of it sits in the picture's safe
  area, its main words in DIN Condensed at one size and its labels in Avenir Next Condensed (both come with macOS).
  Each piece wipes in. Where you are slides sideways, and only on the way into or out of "1 after B" or "2 before C",
  and then only the words that change; other bar numbers simply change. The part, title and loop numbers roll when they
  change, play and pause turn into each other, and the highlight slides along the sections. `&layout=stack` puts
  everything in the lower third; `&accent=2a7de1` sets the colour.

The pieces along the bottom sit 13% of the height up, clear of the name Zoom draws in the bottom left of a tile (it
reaches about 10% up a 16:9 tile); `&bottom=5` puts them in the usual safe area when the picture isn't going to Zoom.
In your own Zoom tile the chyron reads backwards if Zoom mirrors your video for you; others see it the right way round.

OBS puts the page in the picture a little late, so the chyron shows where the music will be 100 ms from now: while
playing, the page asks for the playhead that far ahead (round to the start of a loop when that passes its end), ten times
a second. `&lead=150` for more, `&lead=0` for none.

`?scale=1.5` makes either bigger. The page is `player/chyron.html`, copied into the app by `build.sh`;
`python3 player/chyron_demo.py` serves it with a made-up rehearsal at http://localhost:8767/ to see a look move without
the player (`&bg=556` gives it a background outside OBS).

http://localhost:8766/state is the same as JSON, with the bar, beat, section, tempo, loop ends, the sections checked and
whether the card is on; `/state?at=SECONDS` describes another moment of the song, `&lead=MS` the playhead that far ahead, and `started` changes with each run of
the player. Only this Mac can reach it. Another port: `defaults write local.rehearsal.player chyronPort -int 8770`, or
`-chyronPort 8770` after the app's path for one run; the loader then takes `port=8770` among its options.

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

`enginetest <cache> <out> <speed> <instruments or -> <voice stems...>` prints the gains of every combination of voices and writes
the mix of Balanced and each voice alone to raw float files, for measuring against the stems. `PANS` and `TRIMS` in the
environment, comma-separated, give the song's pans and trims (four voices default to SATB's), and `FIXES` takes `stem:start:end:semitones`
(or `m` to mute), space-separated.
