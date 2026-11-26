# Chord Reduction Trainer: design for version 2

Status: built 2026-11-18 as written, with the changes listed in section 0. The questions in section 12 were answered
with the defaults given there.

## 0. Where the build differs from the first draft

- **The demo starts on a click, not by itself.** Browsers only allow sound after the page is clicked, so on a level you
  haven't seen, "Watch the demo (20 s)" is the main button and Start is secondary; after the demo they swap.
- **Shape outlines only appear on printed-as-played levels**, because only there is the right hand a single three-note
  shape: full on levels 1–3, faint on 4–5, off from 6.
- **Landmine** is defined as a chord tone outside the key signature (natural minor in minor keys); the tint goes on
  every such note, whether or not an accidental is repeated in the bar.
- **Grading is in points** (an AP-style rubric): per change +2 root as the lowest key,
  +1 each for two differently named chord notes above it, −1 per key outside the chord, late notes at half value. The
  page prints this rubric for every run, with the run's own window in ms. Left-hand and right-hand levels score only
  their part (max 2).
- **Dark page by default**, the score drawn in light ink; a light page is one click away.
- **Keys follow the repertoire** (changed 2026-11-18): the ladder's keys are the ones a sample of current choral scores
  start in, C G D A E F B♭ E♭ major (96% of their 3,047 bars) and their relative minors; D♭ appeared in none of the 31
  songs and is left to free play. Level 4 adds G D F, level 8 the other four.
- **Voices over piano is the main texture from level 6** (changed because that is the style a
  chorus accompanist plays from, not block chords or chorales). Section 3a describes it. The block-chord and chorale
  textures are off the ladder and stay in free play.
- **Misprints** happen in the block and moving-part textures and SATB score; a run that draws the piano-figure texture
  has none.

## 1. Goal and rules that hold everywhere

Goal: read a score and play its harmony in time, root in the left hand and two or three chord tones in the right, well
enough to give a chorus pitch support at rehearsal. Levels 1–5 also practise skill 1 (playing a simple two-hand texture
as printed), because there the printed texture is exactly what you play.

Rules every part of the design must keep:

1. **The music never waits.** The click and the score move on whatever you play. Tempo and level change only between
   runs.
2. **The page shows before it tells.** A wordless demo shows each level's game. Words on the page are one line.
3. **Salience is ranked on purpose** (section 5). The next chord to read is the most visible thing during a run;
   results are quiet until the run ends.
4. **Help fades.** Every visual aid (outline, grey passing notes, tint) is strongest on the level that introduces what
   it marks and is gone a few levels later.
5. **Your own scores decide what helps.** Aids whose benefit is a guess are switched on and off between runs and
   compared (section 9).

## 2. Terms

- **Change**: a point where the harmony changes; what is graded. A run of 8 bars has 8–20 changes.
- **Run**: one pass through one generated exercise, count-in to last bar.
- **Level**: a fixed setting of every difficulty axis (section 3) plus which aids are on.
- **Aid**: anything drawn that is not the music: the conductor, shape outlines, grey non-chord tones, the
  chord-change tint, marks.
- **Printed as played**: a texture whose notes are exactly what you should play: left hand the root alone, right hand the
  three chord tones in close position (all within an octave, nothing between them).
- **Landmine**: a chord tone outside the key's scale (natural minor for minor keys), so an accidental that changes which
  chord it is: the raised 7th in a minor key's V, the third of V/V, and so on.
- **Harmless note**: a passing or neighbour tone (generated with the `nct` flag). Ignoring it never changes the chord.

## 3. Difficulty axes

| Axis | Easiest | Hardest |
|---|---|---|
| Hands judged | left only, or right only | both |
| Keys | C | the eight repertoire major keys plus relative minors |
| Chords | I IV V | full set with V7, vii°, V/V, V/vi |
| Printed bass | always the root | inversions |
| Texture | printed as played | voices over a full piano part, SATB open score |
| Changes | one a bar | up to one a beat |
| Meter | 4/4 | 3/4 too |
| Tempo | ♩ = 40 | ♩ = 72 (each level's top) |
| Reading ahead | nothing hidden | current bar hidden |

## 3a. Voices over piano

The page looks like a choral octavo: the choir on top, a piano part below. You read the piano part and play its
chords reduced (the root in the left hand, two chord notes in the right); the grading is the same as on every level.
The voices are there for context and are not graded.

- **Choir:** two staves in closed score with a bracket, two voices on each, stems up and down. Each run is one of the
  two usual layouts: SATB (soprano and alto on a treble staff, tenor and bass on a bass staff) or TTBB (tenors on an
  octave treble staff, baritones and basses on a bass staff). The voices sing the progression's four-part voicing, with
  repeated notes and passing and neighbour notes. Closed score, not one staff per part, because six staves leave room
  for only about two bars a line, and reading ahead needs the next bars on screen. 
- **Piano:** a grand staff with a brace, its own barlines, labelled "Pno". It plays the same chords, its bass on the
  choir's bass note (so inversions match). One right-hand figure and one left-hand figure per run:

| Piano level | Right hand | Left hand |
|---|---|---|
| 1 | chords on every beat; broken chord in eighths (low–high–middle–high) | held bass note; bass in octaves, twice a bar |
| 2 | adds: arpeggio in eighths up and back; after-beat chords (rest, chord); the choir's top line doubled over held chord notes | adds: oom-pah; broken bass in eighths |
| 3 | adds: syncopated pop chords (3 + 3 + 2 eighths) | adds: a reduction, the bass in octaves with two chord notes above, held (more than you would play); the choir's bass line with its passing notes |

  The right hand's chords take three chord notes, the seventh in place of the fifth on V7. With TTBB the doubled top line
  is an octave above the tenors.
- **Misprints** are not put in this texture: a misprinted choir note is not what you read, and a misprinted piano
  note is left for later.
- **Screen:** four staves a line, four bars a line, as in the SATB open score. Two lines must fit in 1024 × 700 under
  the header (tested).

## 4. The ladder

Each level turns up one axis. Tempo runs ♩ = 40 → 72 inside every level.

| Lvl | Turns up | Keys | Chords | Bass | Texture | Changes | Meter | Hidden | Judged |
|---|---|---|---|---|---|---|---|---|---|
| 1 | (start) | C | I IV V | root | printed as played | 1/bar | 4/4 | — | left: root |
| 2 | hand | C | I IV V | root | printed as played | 1/bar | 4/4 | — | right: 2+ tones |
| 3 | hands | C | I IV V | root | printed as played | 1/bar | 4/4 | — | both |
| 4 | keys | C G D F | I IV V | root | printed as played | 1/bar | 4/4 | — | both |
| 5 | chords | C G D F | + vi ii | root | printed as played | 1/bar | 4/4 | — | both |
| 6 | texture | C G D F | + vi ii | root | voices over piano 1 | 1/bar | 4/4 | — | both |
| 7 | changes | C G D F | + V7 | root | voices over piano 1 | some 2/bar | 4/4 | — | both |
| 8 | bass, keys, piano | + A E B♭ E♭ | + vii° | inversions | voices over piano 2 | some 2/bar | 4/4 | — | both |
| 9 | keys, meter | + minors | full diatonic | inversions | voices over piano 2 | some 2/bar | 4/4, 3/4 | — | both |
| 10 | piano, chords | all | + V/V V/vi | inversions | voices over piano 3; one run in four SATB open score | up to 1/beat | both | — | both |
| 11 | reading ahead | all | all | inversions | all | up to 1/beat | both | half-bar | both |
| 12 | reading ahead | all | all | inversions | all | up to 1/beat | both | bar | both |

Aids by level:

| Aid | On at | Fading | Off from |
|---|---|---|---|
| Shape outlines (section 6.2) | 1–3 | 4–5 faint | 6 |
| Grey harmless notes (6.3) | 9 grey | 10 mid-grey | 11 |
| Landmine tint (6.4) | 9–10 | — | 11 |
| Misprint runs (6.5) | — | — | from 10, one run in three |
| Conductor (6.1) | every run, every level | | |

Judging by hand (the grader's lowest-note split stays):

- Left only: the lowest new note in the window is the root (or printed bass). Nothing else is judged; right-hand notes
  are ignored.
- Right only: at least two different chord tones among the new or held notes; no new note outside the chord. The bass
  is not judged.
- Both: as in version 1.

Moving up and down:

- A run at 85% or better: tempo +6. At 85% or better at ♩ = 72: next level at ♩ = 40.
- Below 60%: tempo −6, not below 40. Two runs below 60% at ♩ = 40: the page offers the level below; it never moves you
  down by itself.
- Level, tempo and every run (settings, aids on, each change's result and timing) are saved in the browser.
- "Free play" keeps version 1's settings panel for choosing everything by hand. Free-play runs never move the level.

## 5. Page: reading order and salience

Reading order of the page before a run, largest and first to smallest and last:

1. What this is and the rule, one line: **Chord Reduction Trainer: left hand the root, right hand two chord tones, the
   music never waits.**
2. The level card: "Level 3 · C major · ♩ = 48", the demo playing in it the first time (section 7), and a replay button.
3. Start.
4. The music (its first system).
5. Progress and history; Free play and settings, collapsed, at the bottom.

During a run, salience ranks (most visible first):

1. The conductor, over the top of the music.
2. The music.
3. The count-in number (only during the count-in).
4. Everything else: no coloured marks. A passed change gets a small grey dot; colours and chord names appear when the
   run ends.

The header, title and buttons dim to 40% during a run.

## 6. Aids

### 6.1 The conductor (replaced the next-chord highlight, 2026-11-18)

An accompanist doesn't get a band moving across the music; they look over the top of the stand at the conductor. A
strip above the score, sticky at the top of the screen, shows a conductor in a dim hall beating the run's meter with
the common 2/4, 3/4 and 4/4 patterns, mirrored because you face them (their beat 2 of 4/4 goes to your right). The
baton falls into each beat point fastest and floats at the top of each rebound; it waits raised before the count-in,
then conducts the count-in bar.

It is drawn out of focus, as an eye focused on music 18 inches away sees a conductor 20 feet away: 2.02 dioptres of
defocus, and with a pupil of about 5.5 mm (assumed for evening hall lighting, not measured) a blur disc of about 11
mrad, 16 drawing units at the figure's scale, drawn as a Gaussian blur of σ = 4 units. The figure is smaller on screen
than it would be next to real music at 18 inches, so that two lines of four-staff score still fit under it (four-staff
scores are drawn at 78%); the blur is to the figure's own scale. When you look straight at a real conductor your eyes
refocus within a fraction of a second; the strip shows what you see while your eyes stay on the page.

Forearm rule: the hand barely goes outward past the downbeat, since swinging the forearm far out is not
healthy. Nothing goes more than about 9 cm outward from the 4/4 downbeat; most of the sideways travel is inward, across
the body (4/4: beat 1 to beat 2). The outward beat lands at that edge and the next beat leaves from the same spot after a
stationary dwell (4/4: beats 3 and 4; 3/4: beats 2 and 3). Tested.

The downbeat is perfectly vertical in every pattern: the upbeat rises to a point directly
over beat 1 by mid-beat, floats there, and falls straight down, fastest at the beat. Tested: no sideways movement at all
from the top to beat 1, a fall of at least 100 units.

The 3/4 beat points: 1 at the bottom of the downbeat; 2 at the outer end of a horizontal
stroke; a dwell; 3 at the start of a diagonal upstroke, up and inward in a straight line to the top over beat 1. Tested:
the stroke to 2 is at least 2.5 times as wide as tall, the hand does not move at all from 2 until 3, and from 3 it rises
60 or more and moves 15 or more inward while staying within 4 units of the straight line.

The 4/4 beat points: 1 at the bottom of the downbeat; 2 at the inner end of a horizontal
stroke; 3 at the outer end of a horizontal stroke; then a dwell; 4 where the upbeat begins. The strokes 1→2 and 2→3 are
low and flat (a small rebound, then across, speeding into the beat).

Every dwell is stationary: 4/4 beats 3 and 4, and 3/4 beats 2 and 3, are the same spot, and the
hand holds dead still on it for the whole beat. The two ends are half ictuses: the first only arrives (the hand stops
on it with no rebound), the second only leaves (the upbeat snaps away from it). Tested: no movement at all through the
dwell; both strokes into the dwell at least 2.5 times as wide as tall; a rise of 60 or more in the half beat after 4/4
beat 4.

It conducts every ladder run (no on/off comparison runs). Free play has a Conductor
checkbox.

**No click while it conducts**, count-in included: a conductor makes no sound, and the point is to train reading the
tempo from the baton, not hearing it. The click plays only on free-play runs with the conductor unticked; the latency
calibration still uses clicks.

### 6.1a The choir sings (added 2026-11-18)

From level 6, wherever choir staves are printed (voices over piano, SATB open score), the choir sings its parts: a
synthesized "ah" per section (a sawtooth through three formant filters, soft attack, vibrato), two singers a section,
at sounding pitch (TTBB an octave lower). It sings from its own copies, so a misprint in yours is sung correctly. Nobody
sings in the count-in. Grading stays on the conductor's beat. Setting: sings / sings softly / silent. The end of the
run lists what the choir did wrong.

- **Mistakes**, always, about one every three bars, not in bar 1, never two at once, never on your misprinted note,
  one section each: a wrong note (a half step off), holding the last chord's note half a beat into the new chord,
  coming in a beat early off a long note, sagging 35 cents flat over a long note.
- **Dragging** (checkbox, off by default): half of each section follows by ear: 70 ms late on average, unevenly
  (σ 30 ms, between 20 and 160 ms), every note; the leaders sing within 15 ms of the beat.
- **Rushing** (checkbox, off by default): the two busiest sections (most notes, repeated notes counting extra: the
  "doo doo" parts) rush in a runaway spiral. Each beat they get 20 ms further ahead plus 0.35 ms for every ms they are
  already ahead (anxiety), ±20%. About 0.6 of a beat ahead they notice, vamp on their note until the written music
  catches up, come back in exactly on the beat, and start rushing again. Rushing sections make no other mistakes.

Tested without sound (127 rows in all): timings for leaders and followers, the followers' mean and spread, mistakes'
count and spacing, no singing in the count-in, the misprint sung correctly, and the spiral (further ahead every note,
speeding up, back on the beat after each vamp). A silent run on the page scheduled the voices only after the count-in.
The sound itself has not been listened to.

### 6.2 Shape outlines

On printed-as-played levels, the right-hand triad gets a thin rounded outline with the shape's name in small grey type:
"lines" (three stacked lines), "spaces" (three stacked spaces), or for inversions on level 8 the gap position. Opacity
100% on 1–5, 40% on 6–7.

### 6.3 Grey harmless notes

Notes with the `nct` flag are drawn grey (level 9) or mid-grey (level 10); chord tones are never grey.

### 6.4 Landmine tint

A chord tone that is a landmine (section 2) and carries a printed accidental gets an amber note head on levels 9–10.

### 6.5 Misprint runs

From level 10, one run in three, when that run draws the SATB open score, replaces one inner-voice (alto or tenor) chord tone at one change with a note a half step
away that is outside the chord. Grading is unchanged: the chord is what counts, so playing the chord is right. The end
summary says where the misprint was and whether you played it.

### 6.6 Flash drill (separate mode)

A chord appears for a set time, vanishes, and you have until the next one (a fixed 3-second cycle, never waiting) to
play it. Its own small ladder: root-position triads in C at 1000 ms → inversions → the eight repertoire keys → shown for 250 ms. A
later version adds two-chord pairs and scale figures for skill 1.

## 7. Demo

About 20 seconds the first time a level is opened, and on demand: one bar of count-in then four bars at ♩ = 60.

- The score runs exactly as a real run with that level's aids.
- A keyboard strip under the score lights the keys the demo player presses, and the page plays them (a simple synth) so
  the chord is heard on the click.
- The demo player is the tests' simulated player for that level's rule (left only, right only, both). It misses one
  chord on purpose; the mark appears and the next chord comes on time.
- On misprint levels the demo's misprint is passed over unplayed.
- No text plays a part. The demo never counts towards progress, and its sound stops the moment it ends or you leave.

## 8. Timing: what the grader assumes about the clock

- **MIDI timestamps** are taken to share `performance.now()`'s clock. Check on connect: compare each of the first 20
  events' `timeStamp` with `performance.now()` in the handler; if they differ by more than 20 ms, use the handler's
  time instead and say so on the page.
- **The click is heard late by the audio output latency**, and you play to what you hear. Version 1 ignores this. Add a
  one-time calibration: tap any key along with 8 clicks; the median offset is subtracted from every note's time. Until
  calibrated, the page uses `AudioContext.outputLatency` where the browser reports it.
- **A hidden tab stops animation frames.** Grading moves to a timer so a run still finishes and grades correctly; the
  masks only matter while visible anyway.
- **Sustain pedal** is ignored: "held" means the key is down.

## 9. What is a guess, and how your scores test it

| Guess | How it is tested |
|---|---|
| ±½ beat (≤ 350/400 ms) is a fair on-time window | per-change timing is saved; after 20 runs the summary shows where your on-time chords land |
| +6/−6 tempo steps and the 85%/60% thresholds | look at how many runs each level takes; adjust if a level takes under 3 or over 30 |
| The conductor helps | not tested: it conducts every run |
| Shape outlines and grey notes help | compare your first runs on the levels just after they fade with the runs just before |
| Flash timings (1000 → 250 ms) | drill accuracy per timing is saved |
| MIDI and audio timing (section 8) | measured on your setup, shown in settings |

## 10. Ways it could go wrong, and the check for each

All automatic checks run in `test.html`; every row must read pass.

| Failure | Check |
|---|---|
| A level produces material outside its row (key, chord, inversion, texture, meter, changes) | generate 200 exercises per level; every key, chord, bass role, texture, slot length and meter is in that level's set |
| Printed-as-played texture is not exactly the target | levels 1–5: left hand one note, the root; right hand three notes, the chord's three pitch classes, within 12 semitones |
| A one-hand level grades the wrong hand | simulated players per hand mode: root alone passes level 1 and fails 2; two right-hand tones pass 2 and fail 1; both pass 3 |
| Promotion rules wrong | unit tests on score sequences: 85% at 72 promotes; 60–84 holds; two runs below 60 at 40 offer the level below; free play never moves the level |
| Marks are coloured during a run | simulated run: during the run every mark is grey; after it, coloured |
| The baton off the beat | tests: on the beat point at every whole beat in 2/4, 3/4, 4/4; faster through each beat than mid-beat; mirrored; hand and baton inside the strip. A muted run: sampled baton positions match the pattern at the run's beat |
| A chord tone drawn grey, or a harmless note black on level 9 | every rendered note's colour matches its `nct` flag for the level |
| Tint on the wrong notes | tinted set equals the landmine predicate's set, per exercise |
| Misprint in the wrong place or a chord tone | exactly one per misprint run, alto or tenor, at a change, outside the chord, a half step from the note it replaced; grading treats playing the chord as hit |
| Demo misrepresents its level | the demo's player is the level's simulated player; its run reproduces the level's rule and contains exactly one miss |
| Demo or a test keeps making sound | sound stops at the demo's end, on Escape and on leaving the page (checked by the audio nodes left running) |
| Two systems don't fit the screen in SATB score | at 1280×720 and 1024×700 the current and next system are both fully visible |
| Flash drill waits | the next item always comes 3 s after the last |
| Timing assumptions false on your setup | section 8's measurements, shown in settings |

## 11. Build order and cost

1. Ladder, hand modes, promotion, persistence, page layout and salience, grey marks. Checks for those.
2. Highlight with on/off alternation, outlines, grey notes, tint, misprints. Their checks.
3. Synth, keyboard strip, demo. Checks; sound tests muted except one, stopped right after.
4. Timing: timer-driven grading, MIDI clock check, calibration.
5. Flash drill.

Rough guess, not measured: about four times version 1's build, so near 12% of a 5-hour window, spread over two
sessions. Each phase ends with its checks passing before the next starts; you can play after phase 1.

## 12. Questions for you

1. Level 1 judges only the root. Should an octave-doubled root (both hands' bottom notes) count, or must the left hand
   play exactly one note?
2. Should the landmine tint also mark accidentals that are not chord tones (a chromatic passing note), or only chord
   tones as defined here?
3. The demo plays at ♩ = 60 whatever your tempo. Would you rather it played at your current tempo?
