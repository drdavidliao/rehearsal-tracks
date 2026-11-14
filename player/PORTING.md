# Making your own version of the Rehearsal Player

The player here is a Mac app. This page is for someone on Windows, Linux or anything else who wants one of their own by
asking an AI coding assistant to write it. It says what the app does, the numbers that matter, what the data looks like,
and what went wrong the first time, so yours doesn't have to find out the same way.

Start by giving your assistant this page and this prompt:

> Read PORTING.md and build this app for my computer, which is [Windows 11 on ...]. Read `Sources/CEngine/engine.cpp` and
> `make_map.py` for how it's done on the Mac. Suggest a language and libraries, tell me what I'd need to install, and wait
> for my OK. Build the engine first, with a test program that writes the mix to a file and measures it against the stems,
> before any interface. Check each feature below by measuring it, not by assuming it works.

You need your own stems and score. Nothing in this repository includes any music.

## What it's for

A director runs a rehearsal over Zoom with part of the screen left over (60% for us, with the controls down the left edge so the score gets the full height). That part shows the score, marked up for the lesson. They
click a beat and the song plays from there, with a line following the music, and they can pick out parts, slow it down, loop a
passage, and repair wrong notes in the audio. It replaces a DAW and a tablet for this one job.

## Input

A song folder holding:

- **Stems:** one audio file for each voice part, from one to eight of them (Soprano, Alto, Tenor and Bass, say, or a soloist and
  Tenor 1, Tenor 2a, Tenor 2b, Baritone and Bass), and one for the instruments unless the song has none. All the same sample rate
  and all stereo. Ours came from a stem separator run on rehearsal tracks, and the app uses one of the instrumental stems.
- **A score PDF**, what's shown on screen.
- **`player map.json`**, which says where every bar, beat and note is on the page and in the audio. See below.

## Features

**Following the score.** One page fitted to the window, with two pages side by side as an option. A line moves through the system
in time with the audio, moving smoothly between beats' x positions. While playing, the page turns 0.4 s (of the music's time)
early so the next page's first bar can be read. Take the audio device's output latency off the position, or the line runs ahead
of the sound.

**Dark mode.** Radio buttons for Light and Dark. Inverting the whole page with a filter works, but a vector PDF can be recolored element by
element for less glare: see `dark_score.py`, which makes a dark copy of the score with warm notes and a cooler, dimmer everything else.

**Going somewhere.** Clicking goes to the nearest beat on the nearest system; double-clicking also plays. The first click on the
app from another window must also count as a click, since the director is often in Zoom. A Bar box takes a number or a rehearsal
letter. Keys: space plays and stops; digits and Return go to a bar; Return alone goes back to the last start; a capital letter goes to
that rehearsal letter; arrows move by a bar, with Shift by a beat; up and down change the tempo. Keys must not fire while a box
is being typed in.

**The mix.** Each voice has a trim and a pan, and the instruments stay on, centred, at 0 dB. The pans and trims come from the
song's parts, top to bottom:

- A soloist is centred at 0 dB.
- The other parts are sections, spread evenly from -45 (the highest) to +45 on Logic's knob (-64 to +63). The outer two are at
  0 dB and any between them at -3 dB, except that four sections are at -0.5, -2.5, -2.5, -0.5 dB.
- A section split in two (Tenor 2a and 2b, Bass a and b, Alto 1 and 2, Soprano 1 and 2) sits 5 either side of where the section would.
  Tenor 1 and Tenor 2, or Baritone and Bass, are sections of their own.

| | Soprano | Alto | Tenor | Bass |
|---|---|---|---|---|
| Trim | -0.5 dB | -2.5 dB | -2.5 dB | -0.5 dB |
| Pan | -45 | -15 | +15 | +45 |

With Alto 1 and Alto 2 they pan at -20 and -10; three sections pan at -45, 0 and +45; two at -45 and +45.

Radio buttons choose Balanced, each part "only" (soloists first), or Other. Other shows a list of checkboxes, "Check all parts you
want to hear:". The voices heard get a boost on top of their trim, and the others are off:

| Voices heard | Boost |
|---|---|
| 0 | instruments alone |
| 1 | +6 dB |
| 2 | +3 dB |
| 3 | +1.5 dB |
| 4 | +0.75 dB, and half again for each more |
| all | none: this is Balanced, and checking the last selects it |

That table is for part-predominant files, where each file has its part loudest and the others bleeding through. A switch, remembered
for each song, says "Each voice file: a single voice / part-predominant". With isolated files, the voices heard
in "only" and Other are at 0 dB in place of their trims, and the others at -18 dB. Balanced and "instruments alone" don't change.

The master volume starts at -3 dB, typed or on a slider, and is remembered. Pan a stereo stem as a balance with a constant-power
law, unity at centre: with `pos = knob / 64` and `th = (pos + 1) * pi / 4`, left gain is `cos(th) * sqrt(2)` and right gain is
`sin(th) * sqrt(2)`. Work out the gains from the current choice each audio block and smooth them, so a boost can't be left behind
and nothing clicks. These numbers push peaks past full scale (1.84 in Bass only, in our song), so round the output off smoothly
above 0.9 and leave everything below that untouched.

**Output device.** A menu of the system's audio outputs, remembered by the device's ID, not its name. If the chosen one is
unplugged, use the system default until it's chosen again.

**Tempo.** At the song's own tempo, play the files themselves. Any other tempo keeps the pitch and needs a high-quality stretcher.
Let the user switch methods during playback, separately for voices and instruments, and compare them by ear: no measurement we
tried can say which sounds best. We offer Rubber Band R3 with channels apart (the default), Rubber Band R3 with channels together,
Signalsmith Stretch with default or short blocks (50 ms, 15 ms), and for one-line voice stems, our own PSOLA (see `render_psola`).

**Never wait for a whole render.** Rendering runs far faster than real time, so the first version here, which rendered every
stem before playing, made people wait for no reason. Instead:

- A new tempo or fix renders from a second ahead of the playhead. When that's buffered, playback moves to it there, with a very short fade.
- A jump past what's rendered starts a second render there, with a second of sound before it for the stretcher to settle
  into. Sound comes in about 0.2 s.
- Meanwhile the whole of each changed stem renders from its start. That's what gets cached to disk.
- Don't move the playhead between two renders while it's playing, because they don't match sample for sample. Only move at a stop or a jump.
- The audio thread must never take a lock or wait. The renderer writes ahead, then publishes how far it has got.
- Cache by a hash of the stem, its fixes, the tempo and the method, so a fix to one voice re-renders only that voice.
  Stems finish at the same moment, so tidy the cache one thread at a time.

**Looping.** Boxes for a start and end bar, or letters, where a letter as the end means the end of that letter. Lines on the score
mark it. Reaching the end by playing goes back to the start. A click past the end plays on, and a click before the start plays into it.

**Set lists.** Any number of named lists of song folders in running order, a song allowed twice, with intermissions between
songs, and one list chosen to run. Songs to add are found by name or narrowed by tags, a song needing all the tags chosen. On the open song's last page (the last page with bars, not a page of notes after it) a button
opens the next song in that list, and on its first page one opens the song before, each naming the song; intermissions are
stepped over and the button says so. If it's playing at the click, the new song plays from its start, except across an intermission.

**Fixing a note.** Right-clicking a note on a voice's staff offers Mute, Up a Semitone and Down a Semitone, and once it has a fix,
nudging its start or end by 20 ms and removing the fix. Only that voice's stem changes, and tied notes count as one. A ring on the
note shows the fix. A menu command plays the song without fixes. Mute fades over up to 12 ms inside the note. Transpose pitch-shifts
the note with formants kept, with 0.3 s of sound either side, and blends it in over the same 12 ms, so nothing outside the note
changes. Apply fixes to the stem before stretching it.

## The map

`player map.json`, with times in seconds of the original audio, and x and y in PDF points from the page's top left:

```json
{
  "score": "the PDF to show", "pages": 12, "page_height": 842, "tempo": 120, "offset": 1.025, "music_end": 219.96,
  "voices": [{"key": "S", "name": "Soprano"}, {"key": "A", "name": "Alto"}, {"key": "T", "name": "Tenor"}, {"key": "B", "name": "Bass"}],
  "stems": {"S": "file.wav", "A": "file.wav", "T": "file.wav", "B": "file.wav", "I": "file.wav"},
  "systems": [{"page": 0, "sys": 0, "top": 174.8, "bottom": 437.0}],
  "bars": [{"num": 5, "page": 0, "sys": 0, "xa": 452.6, "xb": 551.6, "letter": "A",
            "beat_x": [458.9, 476.4, 501.2, 518.8], "beat_t": [9.025, 9.525, 10.025, 10.525], "end_t": 11.025}],
  "notes": [{"id": "S5.3.5", "part": "S", "bar": 5, "beat": 4.5, "midi": 66, "word": "la", "start": 10.80, "end": 11.50,
             "heads": [{"page": 0, "x": 536.6, "y": 188.5}]}]
}
```

`voices` lists the voice stems top to bottom as in the score; a note's `part` is its voice's `key`. A voice may also say
`"section"`, for two parts that are halves of one where the names don't show it, `"solo": true` (a name starting "Solo" is a
soloist anyway), and `"trim"` in dB, added to its own, for a stem exported louder or softer than the rest. `I` is the instrumental stem.

`player fixes.json`, kept beside it, is a list of `{"id", "part", "start", "end", "mute", "semitones"}`.

`player tags.json`, also beside it, is a list of the song's tags as strings. Finding songs by tag is optional: search for folders holding a map, and give each its parent folders' names as tags too.

`make_map.py` writes the map from a vector PDF and a MusicXML file: a Dorico export through `../dorico_reader.py`, any other
through `vector_reader.py`, which needs only the staff lines, the barlines and the noteheads (by music-font glyph, or by size where
they're drawn as paths). It's Python and shouldn't care what system it runs on, though we've only run it on a Mac. A score that's
a scan has no positions to read: `make_map_scan.py` gets them from the pixels, and another way is clicking through the score once
to mark bars.

## What went wrong here

Check for these in yours.

- **Timing isn't only the MusicXML.** Our audio starts 1.025 s in, which we measured by fitting the piano's on-beat attacks to the
  instrumental stem. Leave swung offbeats out of that fit.
- **A rit.** The line drifted away from the audio from the bar marked Riten. Chasing attacks gave a tempo that sped up and slowed down at
  random, since soft consonants and legato notes have no attack to find. A smooth curve fitted to the attacks, with the last bar
  ending where the sound stops, worked. A rit in the middle of a song isn't handled yet.
- **Swing.** Notes on offbeat eighths sound at two thirds of the beat, not halfway.
- **Note times.** The score's times are only near the stem's. Move each start to the attack found near it (we search from 70 ms
  before to 150 ms after) and each end to the next note's start, or to where the sound dies away. About 30% of ours found no clear attack and stay at the score's time.
- **Rounding.** A seek lands on a whole sample just before a beat, so "the bar this time is in" says the previous bar unless you allow a
  small margin (we use 2 ms).
- **Separated stems aren't mono.** Ours have different left and right channels, and the instrumental's are partly out of phase. Don't sum to mono.
- **A hang.** Our progress loop once waited for a sample count that rounding could never reach, so renders never finished at some tempos.
  Wait for the render threads, not a count.
- **Memory.** A task manager's figure can include memory already freed, and we saw 4.6 GB that way when the real footprint was about 1 GB.
  Each version of a 3 3/4-minute song is about 460 MB, and the song itself 400 MB.
- **Starting before a song loads.** Remembered settings applied at launch crashed ours, as there was nothing to apply them to.

## Measure these

Render to a file without playing, and compare with the stems:

- Every mode's mix, against the stems summed separately with the expected gains. Ours matched to better than -140 dB, once a one-sample offset was allowed for.
- Stretched audio against the original, scaled: length, and the lag of attacks by section. Ours was 0 at 5 ms resolution.
- A fixed note: its pitch change, silence if muted, and no change at all outside the note at the song's own tempo.
- Going to a new place with nothing rendered: time to first sound, and gaps while playing faster than real time.
- Memory, after dozens of rapid tempo, method and place changes.

Then listen. The measurements above catch mistakes, but only ears can say whether a stretch sounds good.

## Libraries

We use Rubber Band (GPL or commercial) and Signalsmith Stretch (MIT). Signalsmith's README says "This has mostly been tested with
AppleClang (Mac), and MSVC (Windows)". What's below is from memory, so have your assistant check it for your system:

- Audio output: WASAPI or ASIO on Windows, reached through a library such as JUCE, PortAudio or miniaudio.
- Showing a PDF: PDFium is a common choice. A browser's PDF.js is another, if you build a web or Electron version.
- Rubber Band should build on Windows, but check how much work that is before relying on it.

If you give your version to anyone else, check the licenses: Rubber Band's GPL means releasing your source under the GPL, or buying a license.
