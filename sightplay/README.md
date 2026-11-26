# Chord Reduction Trainer

A page for practising skill 3: reading a score and playing its chords in time, with the root in the left hand and two or
three chord tones in the right. It reads the digital piano over MIDI, generates new music each run and never stops for a
mistake. Version 2 adds a 12-level ladder, a demo per level, visual aids that fade with the levels, a flash drill and
timing calibration; DESIGN.md has the whole design and why.

Run it from this folder and open the page in Chrome (Safari has no Web MIDI):

    python3 -m http.server 8774 --bind 127.0.0.1

then go to http://localhost:8774. The first time, Chrome asks to allow MIDI. Under "Timing, click and piano",
"Calibrate timing" measures how late you hear the click (tap along 8 times); do it once per setup.

Modes, at the bottom of the page: **Levels** (the ladder; your level and tempo are kept in the browser),
**Free play** (choose everything; never moves your level), **Flash drill** (a chord shows briefly; play it).

## What it generates

- Keys: on the ladder, C, G, D, A, E, F, B♭, E♭ major (the keys a sample of current choral scores start in) and their relative
  minors (harmonic-minor V and vii°). Free play also offers D♭ major and B♭ minor. Tick the ones to draw from.
- Phrases of four bars, a half cadence then an authentic one, from a table of functional progressions (I, ii, iii, IV, V,
  V7, vi, vii°; i, ii°, III, iv, V, V7, VI, VII in minor; V/V and V/vi from the second texture up).
- A four-part voicing chosen by search for smooth voice-leading: no parallel fifths or octaves, the leading tone and
  sevenths resolved, no doubled leading tone, voices in their ranges.
- Textures: L1 block chords on two staves; L2 the same with restruck rhythms and passing and neighbour tones;
  L3 piano accompaniment (melody over an arpeggiated or oom-pah left hand); L4 SATB open score on four staves
  (tenor in treble-8); V voices over piano, the ladder's texture from level 6: the choir in closed score (SATB or TTBB,
  the two usual layouts) over a piano part whose figures grow by piano level: chords on the beat or broken chords over
  a held or octave bass; then arpeggios, after-beat chords and the tune doubled, over oom-pah or broken bass; then
  syncopated pop chords, over a thick orchestral-style reduction or the choir's bass line. You read the piano part and
  play its chords reduced; the voices are context. Four-staff scores are drawn at 85% so two lines fit the screen.
- Chord changes slow (mostly one a bar), medium or fast (up to one a beat), in 4/4 or 3/4, 8 or 16 bars.

## How a chord change is judged

In points, per change, from the keys struck in a window of half a beat either side (at most 350 ms early, 400 ms late),
plus keys still held from before. The page shows this rubric under the music for every run, with the window in ms:

- both hands (max 4): +2 the lowest key struck is the root (or printed bass); +1 and +1 for two chord notes with
  different names above it; −1 per struck key outside the chord; never below 0.
- left hand only (max 2): +2 for the root as the lowest key; nothing else counts.
- right hand only (max 2): +1 and +1 for two differently named chord notes; −1 per wrong key.
- keys struck after the window, up to a beat after the change, score at half value if that is higher.

Marks: ✓ every point on time, ⟳ every point but late, ½ some, ✗ none. The run's score is points ÷ maximum; on the ladder
85% or more raises the tempo 6 (at ♩ = 72, the next level), below 60% lowers it 6.

The page is dark by default; "Light page" is under "Timing, click, piano and page colour".

## Reading ahead

"Hide the current half-bar" or "the current bar" blanks the music you are playing from its downbeat, so you have to have
read it already. The page keeps the current system at the top of the screen so the next line is in view.

## Files

- `theory.js` keys, spelling, chords. `generate.js` progression, voicing, textures. `grade.js` the judging and the
  simulated players. `render.js` VexFlow drawing and bar positions. `app.js` MIDI, click, run loop, results.
- `levels.js` the ladder, aids per level, and how a score moves you.
- `conductor.js` the conductor over the music: beat patterns, mirrored as you face them, blurred as an eye focused on
  the page sees someone 20 feet away (DESIGN.md 6.1). It replaced the next-chord highlight.
- `choir.js` the choir singing its printed parts, with mistakes and two options: half of each section dragging
  behind by ear, and two sections rushing in a spiral and vamping to get back (DESIGN.md 6.1a). Settings under
  "Choir, timing, click, piano and page colour".
- `test.html` generates 1,944 exercises (every key, texture, meter and density) and checks spelling, ranges, voice-leading,
  bar fill and chord tones on every change, then grades simulated players (perfect, root plus two tones, bass only,
  a wrong note added, nothing, a beat late) against what each should get; then 200 exercises per level against that
  level's keys, chords, basses, textures and changes, the misprints, the landmine flags, hand-by-hand grading, the
  promotion rules, the painted colours of grey and tinted notes, the voices-over-piano figures for each piano level and both choirs (the piano bass matching the choir's bass at
  every change), and that two four-staff systems fit a 1024×700 screen. Every
  row should read pass.
- `index.html?sim=perfect|roots|late|bassonly|wrongnote|nothing|sloppy&mute` runs the page with a simulated player and
  no click.
