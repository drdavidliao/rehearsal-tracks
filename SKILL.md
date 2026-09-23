---
name: "choral-pdf-to-singable-musicxml"
description: "Turn a choral PDF into MusicXML correct enough to sing or drive singing synthesis; covers revoicing, closed-score collapsing and print layout, plus an opt-in Cantai mode. Use for rehearsal tracks (part-predominant, part-left and balanced mp3s from Sibelius audio stems), or MusicXML/MIDI from sheet music."
---

# Choral PDF → singable MusicXML

## README

When the user types `README` — on its own, in any case — print the block below
back to them and stop. Do not start work, do not ask a clarifying question.
It is a reminder card for someone who does not handle these files every day,
and the whole value of it is that it comes back the same every time.

These are sentences to type to Claude, with the file attached; nobody runs
the scripts by hand. Print the commands as code blocks, so they read as
something to copy rather than as quotations.

**PDF → MusicXML.** Attach the PDF and write something like:

```
Convert the attached PDF into a MusicXML file.
```

If there is an OMR attempt (Newzik or similar), attach it too:

```
Convert the attached PDF into a MusicXML file. The attached MusicXML file is Newzik's attempt, in case that helps.
```

**Plan arranging / revoicing.** Attach the MusicXML and write something like:

```
Prepare a BENCH for the attached MusicXML so I can write arranging/voicing instructions.
```

Then click to select a run of beats and type what should happen there.

**Add kludges for Cantai.** Attach the MusicXML and write something like:

```
Make the attached MusicXML compatible with Cantai.
```

This deliberately damages the notation to work around Cantai's melisma
handling. Never print from it.

Then open the MusicXML in Sibelius (sibelius.com) to play it with Cantai
(cantai.app).

**Make rehearsal tracks.** Export one audio file per staff from Sibelius
(solo each staff, File > Export > Audio), put them in one folder with the
MusicXML they were rendered from, connect or attach it, and write something
like:

```
Make rehearsal tracks from the audio files in the Shenandoah folder. The MusicXML there is what they were rendered from.
```

Include the MusicXML: optional, but strongly advised. Without it, a voice
Cantai stopped rendering looks exactly like a voice that is resting, and can
only be asked about; with it, every silence is checked against the score, bar
by bar. Without it, write:

```
Make rehearsal tracks from the audio files in the Shenandoah folder.
```

That is Step 9: check every stem, then per part one predominant mp3 and one
part-left mp3, plus Balanced, Balanced panned and Balanced 3D tracks, named for
Chorus Connection.

`BENCH` in the second command means the clickable beat-grid page: build it
with `python3 -m chorale.bench`, publish it, and read the spans back with
`python3 -m chorale.instructions`.

Written up after repairing one badly-converted TTBB octavo end to end, then
extended by a second job that took a scanned SATB octavo through OMR repair,
a director's TTBB revoicing, and print layout. The numbers below are measured,
not guessed. Everything here assumes the goal is a file good enough to *sing
from or synthesise*, which is a much higher bar than a file that opens.

**Decide the deliverables up front.** Steps 0–5 produce a *print-faithful*
file: what the engraver wrote, nothing more, suitable for Sibelius/Dorico/MuseScore
engraving and for most synths. Step 6 is a separate, opt-in post-process that
rewrites lyrics so Sibelius's Cantai singer sounds every note; its output is *not*
for printing. Steps 7–8 are for the other common ask: re-voicing the piece for a
different ensemble and laying it out to be printed and sung from. Step 9 turns
the finished score into rehearsal tracks. Never mix the
Cantai file with the rest — deliver the faithful file always, and the Cantai file
in addition when asked for learning tracks.

**This file is self-contained.** The eight scripts it refers to are printed in
full under *Scripts* near the end. Write them out to disk verbatim before you
start — `check_pdf_type.py`, `find_performer_instructions.py`, `musicxml_qc.py`,
`cantai_mode.py`, `lyric_collisions.py`, `stem_vs_score.py`, `verify.py`,
`rehearsal_mix.py`. There are no other files to obtain.

**Nothing is delivered until `verify.py` has run on it** (Step 5), and its table
goes into the handback as printed. The rules in this file are prose, and prose
gets skipped: on the unaccompanied TTBB the extension lines were derived from the notes instead
of read from the PDF (2.5), check 10 was never run, and the user found the
missing hyphen in "long-in'" by eye. A check that exists as a script that fails
out loud does not get skipped.

```
pip install pdfplumber lxml music21 verovio cairosvg pillow numpy fonttools brotli slab
# and poppler-utils for pdftoppm / pdftotext
```

**No song titles in this repository.** The pieces this method is used on are
commercial, and their names stay out of the repo: out of SKILL.md, README.md,
the scripts and their comments, commit messages, and any file committed here.
That covers the title, the composer, lyricist and arranger names that identify
the piece, publisher catalogue numbers, and quoted lyric fragments longer than
a generic word or two. When a lesson goes into this file, describe the piece by
what it is — "the unaccompanied TTBB", "the scanned SATB octavo", "a TTBB
with two soloists and piano" — and write examples with a public-domain title
(*Shenandoah*) or none. The piece's own folder is a different matter: PDFs,
MusicXML, stems, bench pages and mp3s are named after the song as usual, and
never live in or get committed to this repo (`.gitignore` refuses score, audio
and bench files as a backstop). Before committing a change to this repo, search
the diff for the titles of the pieces worked on in the session.

The only thing fetched from the network is the MusicXML schema, at verification
time (Step 5).

## Step 0 — Triage. This decides everything.

Do not start converting until you know which kind of PDF you have.

```
python3 check_pdf_type.py score.pdf
```

**VECTOR** (exported from Sibelius/Finale/Dorico/MuseScore): every notehead is a
font glyph at an exact coordinate, every slur is a bezier, lyrics are a text
layer. Do not run OMR. Read the file. Go to Step 2.

**SCAN** (photo/photocopy): pixels only. OMR is the only route. Go to Step 1.

A PDF can look identical on screen in both cases. Check, don't assume. In the
case this was written from, the PDF was a 2008 Sibelius 4 export — 1,568 music
glyphs, 1,940 vector paths, zero images — and the OMR subscription being paid for
was solving a problem that did not exist.

`check_pdf_type.py` only knows the font names listed in it. A Sibelius export in
**Helsinki** (Sibelius's other house font) reports "unrecognised music font" —
it is still fully extractable, with the same code points as Opus once you undo
the Mac Roman mapping (see the appendix). Add the font name to the script when
you meet a new one.

## Step 1 — If it's a scan

OMR is genuinely required. Expect to repair it. The failure modes seen in real
commercial OMR output, all from one 64-bar piece:

- **A hidden time signature carried forward for 39 bars.** The engraving had a
  2/4 bar and then returned to 4/4 *without printing the 4/4*. The OMR read every
  symbol correctly and never noticed that 39 consecutive bars contained twice
  their declared meter. About half those bars were then truncated to 2/4 —
  music silently discarded — and half were left overfull, where the editor
  displays the first half and hides the rest. This is what "measures are missing
  their second halves" looks like.
- **Clef-octave flip-flop.** A treble-8vb tenor staff exported as treble and
  treble-8vb alternately, eleven times, with pitches rewritten to match each
  flip. Notation looks fine; playback jumps octaves.
- **Dropped chord tones** — a four-note chord read as three. Invisible to any
  duration check.
- **Garbled lyrics** — `Riv- V er: we' "Ve ‘crossed`, `1S` for `is`,
  `taıns` for `tains`. For synthesis the lyrics *are* the deliverable, so this
  alone can make OMR output worthless.
- **Lyric fragments filed as tempo directions**, floating above staves.

Run the QC script (Step 5) on anything OMR hands you, before you build on it.

### 1.1 Treat OMR output as a donor, not a draft

On a 67-bar SATB-with-piano octavo the commercial OMR (Newzik/Maestria) was
worth keeping only for the **piano**, and even that needed twenty hand repairs.
The vocal staves were faster to transcribe from scratch against image crops than
to audit: the OMR had dropped a chord tone here, read G3 for B3 there, A4 for
G4, C♮ for C♯ — and nothing in the file tells you which readings it got right.
Budget the job as *transcribe the voices, repair the piano*.

Hand-transcription wants a compact text source you can read and diff, not XML.
A one-token-per-note line format (`B3q=hap- B3s=-py F#3e. E3q=day`, `R`
for rests, `~` for ties, `(` `)` for slurs, one block per voice, one line per
bar, bar number as the line label) is fast to type, trivially checkable against
the meter, and makes a revoicing (Step 7) a text edit rather than an XML edit.

**Check the OMR's bar numbering before you trust any bar reference.** That file
had 69 measures for a 67-bar piece, and real bars 19–20 were filed as measures
21–22 *in two parts only*, the rest unshifted. Write an explicit `real bar → OMR
measure` map per part and route every repair through it. A repair applied to the
wrong measure looks exactly like a repair that didn't work.

**Work from crops, not pages.** `pdftoppm -r 300` the scan, then cut each system
and each questioned bar to its own PNG and look at it. A crop of one bar answers
"C♯ or D?" in seconds; a full page does not. Keep the crops — you will come back
to the same bars when the user reports a problem three rounds later, and a
named crop library (`pf_b47rh.png`, `z05_b25.png`) is the difference between
re-answering a question and re-deriving it.

## Step 2 — If it's vector: read the glyph stream

Use `pdfplumber`. The whole score is sitting there as typed objects.

### 2.1 Geometry first

**Staff lines** are horizontal vector `lines` in groups of five, evenly spaced.
Find them by scanning sorted line tops for runs of 5 with equal gaps:

```python
tops = sorted(l['top'] for l in page.lines
              if abs(l['y0']-l['y1']) < 0.6 and (l['x1']-l['x0']) > 150)
# then find runs of 5 whose consecutive gaps are equal within ~0.15pt
```

The gap is your **staff space, SP**. Measure it; do not hardcode. Everything
below is expressed as a multiple of SP so it transfers between page scales.
(In the reference file SP = 4.2525 pt.)

**Barlines** are vertical lines spanning a staff top to bottom. Take only those
present on ≥3 staves of the system — stems and slur edges produce false hits
otherwise. If the count doesn't match the printed bar count for that system,
tighten to "present on all 4 staves".

**Systems** are groups of staves (4 per system for SATB-with-piano, etc.). Build
a page→system→measure map once and reuse it.

### 2.2 Pitch: exact, from glyph position

Assign every glyph to the **nearest staff on the whole page** (not the nearest
of the current system — otherwise the top staff swallows glyphs from the system
above).

That rule is for glyphs drawn **on or beside their own staff**: noteheads,
rests, accidentals, clefs, dots, flags. **It is wrong for stems and beams**,
which are drawn away from the staff by design and routinely end up geometrically
nearer a neighbouring staff than their own. Do not assign those to a staff at
all — see 2.3.

Then:

```python
centre = (char['top'] + char['bottom']) / 2
d = round((staff_top_line - centre) / (SP/2)) * -1 - 2   # staff positions below the top line
```

That `- 2` is a font-baseline offset. **Calibrate it** rather than trusting it:
find the key-signature accidentals, which must land on known positions
(treble E♭ major = B♭ on the middle line, E♭ top space, A♭ second space), and
solve for the constant. Then verify against a bar you can read by eye.

Top line is F5 in treble, A3 in bass. Map `d` down the diatonic ladder.

**Note: `<pitch>` in MusicXML is SOUNDING pitch.** Under
`<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>`
the note *displays* an octave above what you encode. Transcribe what you see on
the page, subtract one octave at build time for 8vb parts. Getting this backwards
puts the tenors an octave high in both notation and synthesis.

### 2.3 Rhythm: from noteheads, beams, flags and dots

- **Notehead type** from the glyph code (filled / half / whole).
- **Beams**: slanted beams are filled `curves` with exactly 2 distinct x values,
  each with 2 y values ~0.5·SP apart. Flat beams are `rects` of the same
  thickness. *You must handle both* — a beam that happens to be horizontal is a
  different object type in the PDF.
- Count beams crossing a stem's x within its y-range → 1 beam = eighth,
  2 = sixteenth, 3 = thirty-second.
- **Flags** are glyphs (unbeamed notes only).
- **Dots** are in a *different font* (OpusSpecial) with a different baseline —
  roughly 0.85·SP lower than an Opus glyph at the same staff position.
  Calibrate separately. Dot x-offset ≈ 1.6–2·SP right of the notehead.
- **A chord prints one dot per notehead.** Count distinct dot *columns*, not
  dots, or you will read a dotted eighth as double-dotted (0.5 → 0.875).
- **Triplets** are marked by a "3" in the OpusText font. Find the group of 3
  consecutive equal-duration notes bracketing it and scale by 2/3.
- **Chord grouping keys on a shared stem, not a shared x.** Group the noteheads
  one stem claims. A chord's noteheads do spread over ~1.3·SP of x, because a
  second is drawn offset by one notehead width (≈1.28·SP) — but that spread is a
  *consequence* of the grouping, not the test for it. Two notes in different
  voices can print at the same x, and a stemless whole note sitting under a
  stemmed note there is not a chord member; grouping by x merges them. (One
  piano left-hand bar summed to 288 in a 144 bar before this was fixed.)
  Deduplicate identical (x, staff-position, glyph) triples — Sibelius
  double-strikes some glyphs for faux-bold, which otherwise produces phantom
  chord members like `C4+C4`.

**Stems and beams are page-global. Never assign them to a staff.**

Nearest-staff assignment (2.2) tips from one staff to the next at the midpoint
of the gap between their centres, and on a grand staff that midpoint is only
about 3 SP below the upper staff's bottom line. Measured on one reference page
at SP = 4.375: the piano right-hand staff ran 614.7–632.2 and the left hand
659.3–676.8, so the boundary fell at y = 645.75 — **3.10 SP below the RH bottom
line**. A down-stemmed lower voice clears that routinely. The beam under the RH
lower voice spanned 645.2–651.8, straddling the boundary, and the three stems
feeding it had centres 5.1, 2.9 and 0.7 pt from flipping. This is not a quirk of
one engraving: any grand staff, and any vocal staff carrying a stem-down lower
divisi voice, has the same geometry. A stem only has to reach ~3 SP below its
own staff.

So keep them in two page-global lists and let each staff query those:

```python
# per page, not per staff
V = [...]   # every vertical line of stem linewidth
B = [...]   # every beam rect and 5-point filled curve
```

- A **stem** is claimed by a notehead when its x matches the notehead's left or
  right edge and its y-range reaches the notehead's baseline.
- A **beam** counts for a stem when it crosses the stem's x **and** its
  interpolated y falls inside the stem's y-span.

Both tests are already in the pipeline; they just have to run against the
page-global list instead of a pre-filtered per-staff one. This is strictly safer
than proximity, because y-containment is what discriminates: staves sit ~45 pt
apart here and a stem is 11–15 pt long, so a beam belonging to the neighbouring
staff at the same x is 30+ pt outside this stem's span and cannot match.
Proximity throws away the one measurement that resolves the ambiguity.

*The symptom, if you get this wrong.* The beam vanishes from its own staff's
beam list, so every note in that group loses its beam count, reads as a quarter
instead of an eighth, and the bar over-runs. It is easy to misdiagnose: the
*other* voice on that staff is fine, and the bar-length check fires on the staff
rather than the voice, so "this staff is 36 over" reads like a missed dot or a
tuplet and sends you looking in the wrong place. The tell is that the over-run is
always one beam group's worth of notes and always on a staff carrying two voices.
On the reference file it cost nine bars — a 12/8 bar of 144 summing to 180, three
eighths read as quarters.

**Validate every bar against its time signature.** This is the single most
valuable check in the whole pipeline; it catches beam misreads, missed dots and
the hidden-meter trap in one line. When a bar over-runs by exactly the amount
that one note being longer than it should be would explain, the constraint tells
you which reading is right.

### 2.4 Lyrics: from the text layer

Filter `page.chars` by font (the text font, not the music font) and by a y-band
just below the staff. Rebuild words by x-gap. Two thresholds matter:

- Gaps **within** a word are 0.00 pt.
- Gaps at syllable/word boundaries are ≥0.25 pt.

So split on gaps ≥0.25 pt and at hyphens; do not use a larger threshold or you
merge `hope`+`is` into `hopeis` and `we`+`know` into `weknow`.

Sibelius fakes bold by drawing text twice — `TThhoouugghh`. Detect
even-length strings where every character is doubled and halve them.

Sibelius attaches a hyphen to whichever syllable it was typed after, so the
text layer has `a-` `bout,` in one place and `be` `-long,` in another. Treat a
hyphen as shared by both neighbours; marking only one side leaves a syllabic
chain with a `begin` and no `end` (or the reverse), which a synth that rebuilds
words from syllabics then pronounces as two non-words. After building the file,
reassemble every hyphenated word from its syllabics and read the list — that
check also catches engraver typos (`smil-ling`, `wa-ater`, a missing hyphen in
`beau-ti ful`) that are invisible on the page but wreck pronunciation.

Performer instructions are not always italic. In the reference Sibelius file
`Solo 2 (tenor):`, `Bari/Bass`, `T1/T2` and `Everyone clap!` were upright
Palatino at 8.4 pt, separated from the 8.8 pt lyrics only by size. Filter the
text layer by font *and size*, not by style.

Assign syllables to notes **across a whole system, not per bar**. Per-bar
assignment loses any word that straddles a barline.

**Do not match syllable centre to notehead centre.** This is the single most
productive source of wrong-but-plausible output, and it is silent — the words
read correctly, they are just on the wrong notes, and you only find out when
someone sings it.

Engravers *centre* a syllable on its notehead **but left-align it when the
syllable is held over following notes**, so the extender line has room. A wide
left-aligned syllable's centre then sits over the *next* note. Centre-matching
slides it one note right. In the reference file this corrupted 17 of 64 bars,
always in the same direction.

The rule that handles both alignments:

> the syllable belongs to the **first note whose centre falls inside the
> syllable's horizontal span**, among notes that can legally begin a syllable.

"Can legally begin a syllable" matters. A wide word often spans a tied note:

**A tie continuation never begins a syllable.** It sustains the previous one.
So tie-stop notes are excluded from candidacy *during* matching — not patched
afterwards. (Extract ties first, then lyrics. Order your pipeline accordingly.)

Verify with slurs as an independent signal: a syllable must begin at the start
of the slur it is sung over. If span-matching and slur-snapping disagree, one of
them has a bug. When both are right they agree on every syllable, which is a
much stronger result than either alone.

### 2.5 Slurs, ties and melisma lines

A slur or tie is a **single cubic bezier**: a path of exactly two operators,
`('m', p0)` then `('c', c1, c2, p1)`. This is unambiguous and complete.

- Control points above/below the endpoints tell you which side the arc sits on,
  which is how you assign it to the right voice of a divisi.
- Match endpoints to noteheads: try a tight x-window first (±1.4·SP), then widen
  *asymmetrically* — a tie leaves the right side of its note and arrives at the
  left side of the next, so long notes need ~5·SP of slack on the appropriate side.
- **Dashed slurs** arrive as ~0.6·SP fragments tiling end-to-end with small gaps.
  Merge contiguous fragments at the same height and direction before matching.
- **A slur crossing a system or page break is two arcs** — one ending at the
  right margin, one starting at the left. Stitch by staff and system index.
- **Tie vs slur**: same pitch *and* adjacent notes → tie; anything else → slur.
- A **divisi dyad** draws one arc above and one below. If both match the same
  chord member, give the upper arc the top note and the lower arc the bottom.

**Lyric extension lines** (the `____` after a held syllable) are thin horizontal
lines in the lyric band. Ledger lines live in the same band — distinguish by
line weight (ledger lines are drawn heavier) where the engraver varies it. Finale
(Maestro) draws both at 0.48 pt; there, a ledger line is a short line on a
staff's ledger grid (a whole number of staff spaces above or below it) with a
notehead over it. They are an excellent independent
cross-check: every extension line that runs past a following notehead should
correspond to a slur or tie in your extracted set. In the reference file that
check came out 32/32.

They are also the **source** of `<extend>`, not merely a check. Deriving extends
from your note model ("a lyric-less, non-tied note follows") misses every
syllable that is held only by a tie — `seen` tied over the barline gets no line
at all, and Sibelius then draws none. Instead: for each syllable, find the line
that starts within ~2.5 SP of its right edge (or, when the syllable runs to the
margin, the leading segment on the next system), put `<extend/>` on the
syllable, and walk the following lyric-less notes under the line, across system
and page breaks. Then check both directions: every printed segment consumed by
exactly one syllable, and every extend you emit backed by a printed line (a
slurred melisma with no printed line is the one case to keep anyway). Do not put
a text-less `<lyric><extend type="stop"/></lyric>` on the held notes — no
engraver writes that, and Sibelius/Cantai treat it as an empty syllable.

Two consequences of taking the lines from the page rather than the notes, both
learned on the unaccompanied TTBB (TTBB closed score, Finale/Maestro):

- **A syllable held only by a tie often has no line.** `hands,` tied over the
  barline into an eighth, `man` likewise, a third word tied from an eighth into a half:
  the engraving prints none, so the file carries none.
- **A syllable in the middle of a word never gets an extender.** `long-` held
  over a tie into `-in'` prints a hyphen, and an `<extend/>` on `long` makes
  Sibelius draw a line where the hyphen should be. The note model says "held,
  so extend"; the page says "hyphen". The page wins.

Where a line runs off the right margin, the leading segment on the next system
is not always drawn at the height of its own lyric line: Finale puts it just
above the staff whichever lyric line it continues. Pair leading segments with
the lines that ran off the previous system by system and count, not by
height.

## Step 3 — Exploding a condensed score into one part per voice

For singing synthesis you need one monophonic part per voice, because a synth
cannot sing a chord. Condensed choral scores put two voices on one staff.

### 3.0 Read the score's words before its notes

**Before deciding who sings what, find the instructions that say who sings.**
`Basses only`, `Tenors only`, `unis.`, `div.`, `tutti`, `soli`, `tacet`,
`Soprano solo`, `men`, `women`. They are ordinary italic text above a staff.

They are invisible to every check in this document. Pitches are right, rhythms
are right, lyrics are right, bar lengths are right — and half the choir is
singing a passage marked for the other half. Nothing catches it but reading.
They also never survive OMR: in the reference file the commercial OMR dropped
`Basses only` entirely, and I then wrote a whole explosion pipeline that
duplicated every unison passage to both daughter parts without ever looking.

Extract every italic run, discard the ones that are only tempo or expression
(`Ritard`, `a Tempo`, `Gently`, `Big Ritard!`, bar numbers), and treat whatever
is left as a decision you must make. Attribute each one to the staff **below**
it — an instruction sits above the staff it governs — and to the bar it sits in,
or the next bar if its text runs up against the barline.

**Scope cannot be inferred; state it by hand.** `Basses only` ended at the next
bar because that bar is divisi — two voices on the staff means both sections are
singing again — but nothing in the text says so. Encode the scope explicitly
with the reasoning next to it.

Make the build **fail** on an instruction that has no rule, rather than
defaulting to "everybody sings". A script that stops is a script that cannot
quietly hand you a wrong file.

A staff's role can change over the piece, not only within a bar. In a TTBB
piece with two tenor soloists (the two-soloist TTBB below) the treble staff
was `Solo 1 (tenor)` for bars 1–38 and `T1/T2` from 39; the bass-clef staff was `Solo 2 (tenor)` then
`Bari/Bass`; and bars 35–38 were `Everyone clap!` X-noteheads on both staves.
Encode this as a bar-range → part map written by hand from the instruction
list, give the solos their own parts, and give claps their own unpitched part:
a 1-line percussion staff, ordinary noteheads on the line, a `<score-instrument>`
plus `<midi-instrument>` with `<midi-channel>10</midi-channel>` and
`<midi-unpitched>40</midi-unpitched>` (GM hand clap), and `<instrument id>` on
every clap note. X-noteheads on B4 of a 5-line staff with no instrument mapping
display fine in Sibelius and play nothing.

```
python3 find_performer_instructions.py score.pdf        # --start 0 for a pickup bar
```

The script (in *Scripts*) derives the system and bar layout from the PDF itself
and prints every hit with its staff and bar number. Anything it reports needs a
rule written by hand; make your build refuse to run until it has one.

### 3.1 Splitting the staff

Rules, in priority order:

0. **When mapping an extracted event back to an XML note in a multi-voice bar,
   disambiguate by duration.** Two notes of the same pitch in one bar — a held
   pedal and a passing note — are otherwise indistinguishable, and a tie landing
   on the wrong one puts a syllable in the wrong voice.
1. **Chord on one stem** → upper notehead to part 1, lower to part 2. *One
   stem* is literal: take the noteheads that stem claims (2.3), not the ones
   sharing its x. A stemless whole note printed at the same x belongs to another
   voice, not to this chord.
2. **Two stems on one column** (one up, one down) → upper voice to part 1, lower
   to part 2.
3. **Unison (single note)** → duplicate identically to *both* daughter parts.
   This is what makes the output singable; do not leave gaps.
4. **Second voice starting mid-bar** — the print shares the opening notes and
   splits later. The lower part gets voice 1's material up to the split, then
   voice 2's. Encode the lead-in with `<forward>`, not a rest.

   *Check for this explicitly.* A second voice that starts on beat 1 and ends
   before the barline is a bug, and a bar-length check will not catch it, because
   voice 1 still sums correctly. Audit every voice's span, not just the maximum.

5. **Lyrics are on the chord's first-written note**, which is not necessarily the
   note you picked. Read the syllable off the whole chord group.
5b. **Never place a borrowed or duplicated lyric on a tie continuation.** In a
   divisi melisma one voice holds the previous syllable while the other takes the
   new text; the tie is what tells them apart. Enforce it at the point you emit
   the note, not as a later sweep.
6. **Engravers print words on only one staff of a homophonic pair.** Duplicate
   them to the other staff, matching **by onset**, not by requiring identical
   rhythms — the lower staff often has extra passing notes, which should become
   melisma rather than blocking the copy.
7. **Melismas**: `<extend/>` on the syllable; following notes carry no lyric.
   Take the extends from the printed extension lines (2.5), walked over the
   **whole part**, not per bar, or every melisma that crosses a barline is
   missed and every tie-only hold gets no line.

8. **A tacet instruction beats every other rule.** If a section is marked out,
   that part gets a whole-measure rest no matter what the staff contains.

Target invariants for each vocal part: no `<chord/>`, one voice per bar, every
bar sums to its meter, and every sung note either carries a syllable or is
covered by an `<extend/>` on an earlier one.

### 3.2 Editorial cues belong to a voice, and the only clue is their height

A condensed choral score is a grand staff: soprano and alto share the treble
staff, tenor and bass the bass staff. `mel.`, dynamics and hairpins are attached
to **one** of the two voices on a staff, and the only thing on the page that
says which is whether the mark sits **above** the staff (the upper voice) or
**below** it (the lower voice). Record the placement when you extract the mark
and keep it attached; "it is near the treble clef, so it belongs to the treble
part" sends every alto cue to the wrong singer, and nothing downstream notices.
`mel.` means *this part has the melody* and must travel with the notes it labels
through any explosion or revoicing.

Small/cue-size noteheads are load-bearing too. Where a divisi prints its upper
line cue-size, the arranger is marking it optional, which also tells you that an
adjacent `mel.` belongs to the full-size lower line. Preserve it as
`<type size="cue">`, or at minimum write it down.

## Step 4 — MusicXML element order (Sibelius rejects what others accept)

music21, Verovio and MuseScore silently accept out-of-order children. Sibelius
refuses to import. Order inside `<note>`:

```
grace? cue? chord? (pitch|rest|unpitched) duration tie* instrument? footnote?
level? voice? type? dot* accidental? time-modification? stem? notehead?
notehead-text? staff? beam* notations* lyric* play? listen?
```

Inside `<direction>`: `direction-type+ offset? footnote? level? voice? staff?
sound? listening?` — and only **one** `<staff>`.

Two real errors from this exact pipeline: `<notations>` emitted after `<lyric>`
(because slurs were appended to finished notes), and a duplicated `<staff>` in a
direction (because a staff number was added to a direction that already had one).
A third, from adding ties to an already-built note: `<tie>` goes immediately
after `<duration>` and `<tied>` goes inside `<notations>`; appending `<tie>` at
the end of the note validates nowhere. Write a normaliser that reorders children
to the canonical sequence and run it as the last step of every build.

## Step 5 — Verify. All of it, every build.

Run the script, on the **print-faithful** file (the Cantai file departs from
the page by design, and fails check 10 because of it):

```
python3 verify.py score.musicxml --pdf score.pdf [--lanes "0a=Tenor,0b=Lead,1a=Baritone,1b=Bass"] [--render pages/] [--original before.musicxml]
```

It prints one line per check below: PASS, FAIL, WARN, MANUAL (needs a person;
the line says what to look at), N/A (the line says why) or NOT RUN (the line
says which input is missing). Put the table into the handback exactly as
printed, with a sentence for every FAIL, WARN and MANUAL line saying what you
did about it. Do not deliver on a FAIL. A NOT RUN is reported as NOT RUN,
never dropped: an empty result and a check nobody ran look identical downstream.

`--lanes` tells it which part each lyric line of the PDF belongs to — `0a` is
the line above the first staff of a system, `0b` the line below it. With one
staff per part it defaults to part *k* below staff *k*; a closed score needs it
spelt out. Checks 10, 11 and 12 read the PDF directly, so they test the file
against the engraving rather than against your own extraction; they work on
vector PDFs only.

Tested on the unaccompanied TTBB: the delivered file passes; a copy with the two mistakes that
reached the user put back (extenders on mid-word syllables, extenders on
tie-only holds) fails check 10 with 9 disagreements and check 14 with 18.

The checks:

1. **XSD.** Fetch `musicxml.xsd`, `xml.xsd`, `xlink.xsd` from
   `https://raw.githubusercontent.com/w3c/musicxml/v4.0/schema/` and rewrite the
   two `xs:import schemaLocation` attributes to point at the local copies.
   `lxml.etree.XMLSchema(...).validate(doc)` must be True.
2. **Bar lengths** against the meter in force. Zero exceptions.
3. **Ranges** per part via music21 — a tenor part reading B♭1 means you got the
   8vb clef backwards.
4. **QC script** below — lyrics, octave leaps in sung lines, clef-octave
   consistency.
5. **Render and compare to the PDF, page by page**, with Verovio + cairosvg.
   A render that looks wrong in a way your data doesn't explain means you have a
   pitch or octave bug, not a renderer bug.
6. **Every performer instruction found, and the scope you gave it.** If the list
   is empty, say you looked — an empty list and a list you never made look the
   same in the output.
7. **Hand back the judgment calls.** Every divisi bar, every place you duplicated
   lyrics, every literal-rest reading, every typo you fixed. The singer needs to
   know what you decided on their behalf.
8. **Ties pair up.** In every monophonic part, each tie start is followed by a
   same-pitch note carrying the stop; no tie runs into a rest. Sibelius plays an
   unpaired tie as a note held through whatever comes next.
9. **Words reassemble.** Rebuild every hyphenated word from the syllabics and
   read the list (see 2.4).
10. **Every printed extension line is consumed** by exactly one syllable, and
    every emitted `<extend>` has a printed line behind it (see 2.5).
11. **Cross-staff onset alignment.** Notes at the same onset in different staves
    share an x within ~1.5 SP. One line of code; it catches a mis-split voice or
    a mis-read duration before you ever look at a render.
12. **Every notehead lands on its own staff's grid.** Its computed staff
    position must come out a whole number of half staff spaces. A notehead
    assigned to the wrong staff lands at a non-integral position, because two
    staves in a system sit at arbitrary vertical offsets from each other. One
    line of code, and it is the only *positive* evidence that nearest-staff
    assignment (2.2) worked everywhere rather than merely not having been caught
    failing — including the ledger-line notes in a grand-staff gap, which is
    exactly where proximity is least trustworthy. On the reference file all
    1,949 noteheads came within 0.12 of an integer.
13. **Every voice can read its own part off a shared staff.** On any staff
    carrying two voices, reconstruct what each singer actually reads — the
    line-2 syllable wherever that voice has its own notehead, the line-1
    syllable wherever it is sharing one — and compare to that voice's own
    syllable list. Equality, or you have a lyric-line bug (7.4).
14. **No extender outruns its voice.** Every `<extend/>` must have a following
    note *in the same voice* for the line to run under. Verovio says
    "Syllable with underline extender under one single note" when it doesn't.
    The fix is to keep the tied note in that voice (7.4), never to drop the line.
15. **No lyric collisions in the layout you are going to print** —
    `lyric_collisions.py`, Step 8.
16. **A revoicing matches the original everywhere it was not asked to change.**
    Sample both scores on a 16th-note grid, per voice, and diff pitch and
    pitch-class; the only differences left should be the ones on the
    instruction list (7.5).

## Step 6 — Cantai mode (optional; not for printing)

Sibelius's Cantai singer reads lyrics from the score and, as of this writing,
**does not start a new sound on a note that has no lyric of its own when that
note follows a tie continuation**. It keeps holding the previous pitch. The
notation is right, the ties are right, a sampled voice plays it right; only
Cantai sustains. Diagnosed on the two-soloist TTBB: bar 57, a syllable on an E♭ eighth →
E♭ half → E♭ eighth (tied), then D — Cantai held the E♭ through the D and the
following eighths; switching the staff to a Sibelius Sounds voice fixed it.
Pure slur melismas (no tie in the chain) sang fine. Adding text to the
lyric-less note fixed it.

So the workaround is lyric text on every note that must start a sound, and
nothing else: keep the print-faithful file as the deliverable for engraving and
produce a second file for learning tracks. Cantai's own guide documents only
that it "reads Sibelius's lyric hyphens to map phonemes correctly"
(https://cantai.app/sibelius); there is no published melisma rule, so expect
this section to age.

**Rule, as implemented in `cantai_mode.py`** (runs on the finished MusicXML):

- A *melisma group* is a lyric-bearing note plus the lyric-less notes after it
  up to the next syllable or rest.
- If the group contains a tie continuation, every note in it that starts a
  sound gets a piece of the syllable: onset+vowel on the syllable note, the bare
  vowel on intermediate notes, vowel+final consonants (with punctuation) on the
  last. `gleams` over E♭ ~E♭ ~E♭ D B♭ C ~C D → `glea / ea / ea / ea / eams`;
  `now,` over C ~C D → `now / ow,`; `ful` over F ~G G → `fu / ul`; an in-word
  syllable such as `smil-` keeps its hyphen semantics on the outer pieces.
- A **dotted** tie-continuation in the middle of such a group is un-tied and
  re-sung on the vowel (`G3 half ~ G3 dotted quarter` → `G3 half`, `G3 dotted
  quarter: ea`). `--keep-dotted-ties` turns it off.
- `--untie-all`: every tie continuation inside a real melisma (a tie chain
  followed by at least one further sung note) is un-tied and re-sung on the
  vowel, so no tie survives in a melisma. Plain tied holds that lead straight
  into the next syllable (`seen ~`, `bright. ~`) are left alone; they never
  misbehaved. **This is the setting that finally worked** on the reference
  score; see the rounds below.
- Groups with no tie are left exactly as printed. So is everything outside
  melismas. Extension lines are re-derived so a piece gets `<extend/>` only if
  lyric-less notes still follow it.

**Respell vocables, in the Cantai file only.** Cantai pronounces each syllable
as though it were an isolated English word, so the `Li, li, li` and `Ni, ni, ni`
of a vocalise come out wrong — on the scanned SATB octavo the user's report
was that Cantai "had a field day" with them. Respelling to `lai` / `nai` in the
Cantai copy fixed it. Do it as a narrow regex over lyric text in the Cantai file
only (`[LlNn]i[,.]?`, preserving case and trailing punctuation), print the count,
and say in the handback which words were respelled. The print-faithful file
keeps the engraver's spelling. Look for this whenever the text contains
non-words: vocalise syllables, scat, and any invented syllable are the ones a
grapheme-to-phoneme model has no dictionary entry for.

**What to tell the user:** the pieces are pronounced by Cantai as isolated
words, so vowels drift (`lo` from `love` comes out "low"); pitch and syllable
timing are right, which is what a learning track needs. A bad piece is fixed
by retyping that one lyric in Sibelius with a phonetic spelling. The Cantai
file must not be used for printed parts.

**Do it minimally and in rounds, and expect the renderer to be inconsistent.**
The rounds on the reference score: (1) every melisma note gets a syllable —
worked, rejected as "overly so"; (2) only after holds of 2½ beats or more —
too narrow, sustains reappeared where a melisma ran into a second tie;
(3) every sung note in a tie-containing melisma gets a piece, dotted
continuations re-sung — fixed most spots, but T1 still held bar 101 while T2,
whose XML was byte-for-byte identical, sang it correctly, with T1 soloed and the
Sibelius level meter flat during the hold: Cantai's own pre-rendered audio,
not a note event, and not something notation can address; (4) `--untie-all`,
which takes ties out of melismas entirely so no singer in the ensemble has to
stitch across one — that ended it. Keep the change log the script prints and
hand it over, so the user knows every place the file departs from the print.

## Step 7 — Revoicing, and collapsing voices onto shared staves

A director hands you an instruction list ("SATB → TTBB: soprano down an octave
to Tenor 2, alto to Bass, …, with these exceptions at bars 25–28, 43–44, 59–64").
This is a *transcription of someone else's decisions*, and the failure mode is
not wrong notes — it is quietly answering a question they already answered.

### 7.1 Work from a text source, not from XML

With the per-voice text format from 1.1, a revoicing is a new block of text per
new voice, every bar written out explicitly, one pitch per token. It is
readable, diffable, and you can hand the user the exact bars you produced for a
rule you were unsure about. Editing XML directly makes every question
"what did you do at bar 61?" expensive.

Read the instruction list back to the user in your own words before building,
and quote the bars. On the reference job an instruction that said "bars 61 beat 3
to 64 repeat the bar 59 beat 4 – 61 beat 2 span" was first implemented as
repeating a shorter span; only restating it caught that. When the user says a
restatement is false, treat it as a hard stop and re-read the source — do not
adjust the implementation around the misreading.

### 7.2 Merging two parts onto one staff

Two simultaneous events merge into one chord in voice 1 only when everything
printable about them agrees: same duration, same dots, same note type, both
notes or both rests, same tie start and stop, same slur start and stop, same
lyric text and syllabic. Anything else → voice 1 carries the upper part, and a
second voice follows after `<backup>`, with `<forward>` for its lead-in,
explicit `<stem>up</stem>` / `<stem>down</stem>` on the split stretch, and
`<voice>2</voice>`.

Parts diverge and reconverge **several times inside one bar**. A prefix merge
— agree until the first difference, then two voices to the end of the bar —
produces needless two-voice writing and duplicate lyrics. Sync on every position
where both parts have an event and the two are mergeable; write two voices only
in the stretches between syncs.

### 7.3 Directions can land where voice 1 has no note

On a merged staff, a dynamic, a rehearsal mark or a `mel.` belonging to the
lower voice can fall on a beat where voice 1 is in the middle of a held note.
If you only emit directions at voice-1 note starts, those vanish — silently, and
only in the bars where the parts diverge, which is exactly where the marks
matter. Attach them at the barline with an offset instead:

```xml
<direction placement="below">
  <direction-type><words font-style="italic">mel.</words></direction-type>
  <offset>8</offset>
</direction>
```

`<offset>` is in divisions and comes *after* `direction-type` (Step 4).

### 7.4 Lyrics on a shared staff — decide by words, not by beats

This is the part that goes wrong. **Decide the number of lyric lines for a bar
by comparing the two voices' syllable *sequences*, not their note positions.**

- **Sequences equal → one lyric line.** Drop the lower voice's copies entirely.
  This is the common case: both parts sing the same words, one takes a two-note
  melisma where the other has a plain quarter. The merge cannot chord them, so
  the lower voice gets written out as voice 2 — and its duplicate syllable, the
  same word on the same beat, plus an extender for the melisma, lands on a
  second lyric line beneath an otherwise-empty one. That is the stray
  `ing______` under a bar whose text is already complete. The slur shows the
  melisma; the second line adds nothing.
- **Sequences differ → two lines,** line 1 the upper voice and line 2 the lower
  voice, *for every bar of the divergent passage*, including bars where one of
  them is silent.

A per-bar collision test — "does a voice-2 syllable start on the same beat as a
voice-1 syllable?" — gets both cases wrong. It prints the duplicate in the first
case. In the second it flips between one and two lines from bar to bar, so a
single continuous phrase in one voice is split across two lyric lines: every
word is present, and the part cannot be read. On the reference score this hit
bars 20–26, 38–42, 48–49 and 54–58 in the tenors and eleven more in the low
voices, and it is what the user saw as "stray syllables".

Two details that follow published practice, checked against the engraved
original:

- **Do not copy a shared syllable onto both lines** where the parts are chorded
  together. The second line appears only over the bars where the parts diverge;
  a singer follows line 2 while it exists and line 1 where the notes are shared.
- **Put both lines below the staff** (`number="1"`, `number="2"`, no `placement`)
  unless you are deliberately reproducing an octavo that puts the divisi line
  above to save vertical space. Mixed placement makes line 1 jump above and
  below the staff from bar to bar.

**A tie never changes voice, and a held word keeps its line.** Merging is decided
bar by bar, so a note held in voice 2 across a barline can land in a unison
that merges into voice 1. The tie then jumps voices, and voice 2 has no note
left for its syllable's extender to run under. Keep the tied note in voice 2 —
a unison with one stem up and one down — and the line draws. Do not delete the
`<extend/>` instead: an earlier version of this file said "the tie shows the
sustain", and that was a workaround passed off as practice. The engraved
original of the reference score prints both parts' lines into exactly such a
unison, the upper tie curving in from above and the lower from below.

**Verify by reconstructing the read** (check 13). Walk each voice and collect
the syllable it would actually sing — line 2 where it has its own notehead,
line 1 where it shares one — and compare to that voice's source syllable list.
On the reference piece: 131 / 135 / 144 / 138 syllables, exact on all four.
Nothing else catches a split phrase, because every syllable is present in the
file and the XML validates.

### 7.5 Cross-check the revoicing against the original

Sample both scores on a 16th-note grid, per voice, and diff pitch and
pitch-class; do the same for lyric position. Everything the director did not ask
you to change must match, so the only differences left are the ones on the
instruction list — which you then read back to them. On the reference job this
caught an alto line extracted from the wrong half of a condensed staff, a bug
no bar-length, XSD or range check would ever see, because the wrong notes were
all perfectly plausible altos.

### 7.6 Crossed parts on a shared staff

When the lower part goes above the upper, three things break on the page and
nothing in the data catches any of them.

- **Never chord crossed notes.** Two parts that agree in rhythm, ties, slurs
  and syllable will merge into one chord, and a chord cannot say whose note is
  whose: Baritone D3 under Bass E3 reads as the Baritone singing E3. Refuse the
  merge whenever the lower part's note is above the upper's (a unison is not a
  crossing) and write that stretch as two voices.
- **Stems keep identifying the part.** Voice 1 stays up and voice 2 down even
  while crossed. In a bar crossed throughout, voice 2's tie then defaults to
  curving under, straight through voice 1's noteheads; write it
  `<tied orientation="over">`. Sibelius honours the side. A probe showed it
  ignores `bezier-x`/`bezier-y`/`bezier-x2`/`bezier-y2` and `default-y` on a
  tie, so the height of the arc cannot be set from the file; any further lift
  is a hand touch-up in Sibelius (Tie Middle Y). Verovio picks the tie side by
  voice number rather than stem, so write the side explicitly on every tie of a
  shared staff.
- **A lyric line is not ended by a rest.** Both Sibelius and Verovio run an
  extender on to the next syllable-less note in the same voice, however far
  away. Splitting one crossed note off a chord gives voice 2 exactly such a
  note, and a line from seven bars earlier ran across three systems to reach
  it. Put a syllable-less voice-2 note that follows an already-finished
  voice-2 line into voice 3; that was the only encoding that worked in a
  Sibelius probe. Do not write `<lyric><extend type="stop"/></lyric>` for
  Sibelius: it reads it as a new, empty syllable and every held word whose line
  ended that way lost its line. A `print-object="no"` syllable was printed
  anyway. The empty stop is fine for Verovio, and only for Verovio.

## Step 8 — Laying out a part for print

### 8.1 Verovio and cairosvg, the parts that surprise you

- **`unit` is the staff-size knob**, not `scale`. With page dimensions given in
  1/10 mm, `unit = staff_height_mm / 4 * 10 / 2`. `scale` only zooms the output
  and changes nothing about how much music fits on a page.
- Page size and margins are in 1/10 mm. **`cairosvg.svg2pdf(..., dpi=254)`** maps
  those units to a real page; without it a US-Letter score comes out 22 × 29 in.
- `breaks: "encoded"` honours `<print new-system="yes"/>` and
  `<print new-page="yes"/>`. `breaks: "line"` honours system breaks and
  paginates automatically — useful for a pilot, wrong for a final layout.
- `justifyVertically` spreads systems from the top margin to the bottom margin.
  With three or more systems that reads as even spacing. With two it opens one
  chasm in the middle; leave it off.
- cairosvg PNGs have a **transparent** background. Composite onto white before
  converting to greyscale, or every ink measurement comes back NaN.
- Verovio's SVG inner coordinates are 10× the viewBox units (viewBox in 1/10 mm,
  drawing in 1/100 mm), which matters when you measure anything out of the SVG.

### 8.2 How many bars fit on a line — do the arithmetic, don't guess

Density is usable width ÷ staff height, and it transfers between page sizes.
A published octavo at a 6.35 mm staff on a 6¾ × 10½ in page has ~137 mm of
usable width and prints about **2 bars to a system** — call it ~10.8
staff-heights per bar. US Letter with 14 / 11 mm side margins gives ~191 mm,
1.4× as wide, so the same density is ~2.8 bars. **Three bars per system is the
ceiling**, at a 6–7 mm staff. Four runs the words together, and Verovio will not
always warn: its "justification is highly compressed" warning fires on note
spacing, not on lyric width, so a system can be flagged clean and still print
`Allthatwe'veknown`.

Vertically, a four-staff system (two voice staves plus piano) with lyrics and
chord symbols is about 78 mm at a 7 mm staff. **Three fit a Letter page and fill
it. Two fit and leave the bottom third blank**, and no staff size fixes that:
filling the page with two systems needs ~11 mm staves, at which only 1–2 bars
fit per line and the piece grows from 12 pages to 17. Say this to the user
rather than stretching the spacing — they are usually asking because of paper.

Where you must shorten a system, shorten the *texted* ones. Four-bar systems are
fine through passages where the voices are resting or holding.

### 8.3 Measure the crowding

`lyric_collisions.py` renders the laid-out file, pulls every syllable's x, y and
font size out of the SVG, groups them by baseline and reports every pair whose
gap is smaller than the estimated width of the first. That turns "does this look
cramped" into a number you can iterate on, which is the only practical way to
choose system breaks across a whole score. The width estimate is approximate:
treat a gap a little under the estimate as tight-but-legible and a gap well
under it as a collision, and use the tool comparatively between candidate
layouts rather than as an absolute.

### 8.4 Missing-glyph rectangles in the PDF

Verovio draws notated accidentals as **paths**, but **chord-symbol** accidentals
as `<text font-family="Leipzig">` at private-use code points (sharp = U+EA66).
cairosvg does not implement `@font-face`, so with no Leipzig installed on the
system, every chord-symbol sharp and flat renders as a tofu box while the music
itself looks perfect — `A/C□`, `D/F□`. `smuflTextFont` does not change this.
Install the font; Verovio ships it base64'd inside its own CSS:

```python
import re, base64
from fontTools.ttLib import TTFont          # pip install fonttools brotli
css = open('.../verovio/data/Leipzig.css').read()
open('Leipzig.woff2','wb').write(base64.b64decode(
    re.search(r'base64,([A-Za-z0-9+/=]+)', css).group(1)))
f = TTFont('Leipzig.woff2'); f.flavor = None; f.save('Leipzig.ttf')
```

then `mkdir -p ~/.fonts && cp Leipzig.ttf ~/.fonts/ && fc-cache -f`. The same
trick works for Bravura, Leland, Gootville and Petaluma, which ship the same way.
Check for the problem by scanning the SVG for characters above U+007F: anything
in the private-use range is a font you need installed.

### 8.5 What travels to Sibelius

Layout goes in `<defaults>` — `<scaling>` (millimetres per 40 tenths),
`<page-layout>`, `<system-layout>`, `<staff-layout>` — plus `<print
new-system>` / `<print new-page>` on measures. Sibelius honours the breaks and
then runs its own vertical justification (Engraving Rules → Staves → "Justify
staves when page is at least N% full").

Set `<system-distance>` generously. 110 tenths at a 6 mm staff is ~17 mm between
systems, which is not enough clearance for lyrics under one system and chord
symbols over the next, and Sibelius will overlap them — the same layout that
renders cleanly in Verovio. 150 tenths with `<staff-distance>` 85 behaved.

Bracket the vocal staves with `<group-barline>no</group-barline>`. A joined
barline runs down through the lyrics between the staves; engraved choral
octavos break it at every vocal staff. The piano's two staves still join.

### 8.6 Credits: who wrote the piece, and why nobody sees it

Getting a name onto the page took four rounds, because the two readers want
opposite encodings and neither complains.

**Position every credit.** MusicXML page coordinates are in tenths and the
schema's own documentation says the `default-x` and `default-y` attributes
"adjust the origin relative to the bottom left-hand corner of the page". A
`<credit>` without them therefore sits at (0, 0) — the corner of the paper,
flush to the edge, no margin — and several unpositioned credits pile up there,
so all but one look dropped. Verovio skips them; Sibelius draws the pile.

**Put every line that belongs in one corner into ONE `<credit>`, as successive
`<credit-words>`.** The spec says "a series of credit-words and credit-symbol
elements within a single credit element follow one another in sequence
visually"; only the first carries the position, and the line break is a literal
newline at the end of each. This is what MuseScore writes. Sibelius keeps one
credit per zone of the page — given six separate `<credit>` elements aimed at
the same corner it drew the last and silently dropped five — but renders every
`<credit-words>` of a single credit as its own line. Verovio is the mirror
image: it draws every separate credit and only the *first* line of a block. So
encode the block, and expand it into separate credits on the way into Verovio
and nowhere else.

**`credit-type` is not decoration.** Sibelius routes a typed credit into its
Score Info fields instead of onto the page. Leave the type off any line you
want to see; the names still reach Score Info through
`<identification><creator>`, which is where that metadata belongs.

**The copyright notice is its own problem.** Sibelius turns `<rights>` into a
copyright line pinned to the *bottom margin* — which is also where it
justifies the staves down to after import, so the notice and the last system
land on each other. Widening the bottom margin moves both together and cannot
separate them. Drop `<rights>`, place the notice as a positioned credit inside
the margin band a few millimetres off the paper edge, and justification can no
longer reach it; leaving `<rights>` in as well gets two notices. Verovio needs
that line painted onto the rendered page separately — it converts credits into
the page *head* only and drops a bottom-positioned one under all three
`footer` settings.

**When a reader silently omits something, probe rather than tune.** Three
rounds of adjusting attributes taught nothing. One throwaway file carrying six
differently-encoded credits, each labelled with the encoding that produced it,
answered every question in a single import. Build the probe the moment you are
guessing twice about the same thing.

## Step 9 — Stems and rehearsal tracks

A set of **rehearsal tracks** is five kinds of mp3, and "make rehearsal
tracks" means all five (so do older requests for "part-predominant tracks" or
"practice tracks"): per part, one predominant track (the part loud, the other
voices faint, the piano as written) and one part-left track (the part hard
left, the other voices hard right, the piano centred); and three Balanced
tracks with every part at the same level: plain (no panning), panned (the
voices spread across the stereo field) and 3D (the voices placed around the
listener, for headphones). Sibelius does not make these.
Export one audio stem per staff, check every stem, and mix with
`rehearsal_mix.py`, which makes the whole set in one run (9.4).
Everything in this step was worked out on the solo-and-TTBB piece
(TTBB + Solo + piano) with Cantai voices; treat the Cantai findings as
observations from that session, not documented behaviour.

### 9.1 Export one stem per staff

**Solo each staff and use File > Export > Audio.** Slow, and every manual
export tested came out clean. Bob Zawalich's *Export Each Staff As Audio*
plug-in is faster but not trustworthy with Cantai (9.3); if you use it, check
every stem it writes. It writes WAV or AIFF only, not mp3.

The Sibelius staff faders do not change a Cantai voice's volume — they send
MIDI CC7, which Cantai appears to ignore. Balance with the per-instance Cantai
strips in the Mixer, or, better, leave the stems flat and balance in the mix.

### 9.2 Check every stem before mixing

**Ask for the MusicXML first, once, if it is not already there.** Look in the
stems' folder and among the attachments for the MusicXML the stems were
rendered from. If there is none, before any checking, say that it is optional
but strongly advised, and why in one sentence: without it, a voice Cantai
stopped rendering (or never started) is indistinguishable from a voice that is
resting, so those silences can only be reported as questions; with it,
`stem_vs_score.py` reports them by bar as errors. Ask once. If the user
declines, cannot supply it, or is not there to answer, go ahead with the
audio-only checks below and say in the handback that the score check was not
run — NOT RUN, not silently skipped.

The case that settled this: the two-soloist TTBB, whose folder had stems
and no MusicXML. Cantai stopped rendering Solo 1 at 1:04.55 of a 4:48 piece;
Solo 2 sang on to 1:13.85, then both went to digital silence for good, as the
score says the solos do. From the audio, Solo 1's early stop and Solo 2's
correct one are the same shape: a last phrase, a reverb tail, zeros. The level
report even showed it — Solo 1 sounding 19.3 s against Solo 2's 32.6 s — and
nothing flagged it. The tracks, a 3D track among them, went out with Solo 1's
last phrase missing, and were remade after the user noticed the gap and
re-exported the staff.

Three failures have all been seen, and none is audible until someone rehearses
from the wrong track:

```
# peak per stem: -91.0 dB (ffmpeg's floor) means all zeros
ffmpeg -hide_banner -i "Tenor 1.aiff" -af volumedetect -f null - 2>&1 | grep max_volume

# a peak that can be ABOVE full scale (a mix before encoding): volumedetect stops
# at 0.0 dB, so read astats on double-precision samples instead
ffmpeg -hide_banner -i mix.wav -af aformat=sample_fmts=dbl,astats=measure_overall=Peak_level:measure_perchannel=none \
  -f null - 2>&1 | grep "Peak level"

# sample-for-sample copies: identical checksums are the same audio.
# Compare the opening too (-t 40): the plug-in leak copies only the first 25-38 s.
ffmpeg -loglevel error -i "Tenor 1.aiff" -f s16le - | md5sum
ffmpeg -loglevel error -i "Tenor 1.aiff" -t 40 -f s16le - | md5sum

# first entrance: when the leading silence ends; compare across the section
ffmpeg -hide_banner -i "Tenor 1.aiff" -af silencedetect=n=-50dB:d=0.3 -f null - 2>&1 \
  | grep -m1 silence_end
```

A silent stem, a stem matching another stem, or a voice entering seconds after
the rest of its section is a bad export. Re-export that staff by hand. Staggered
entrances that agree *within* a section point to the score, not the bug (check
the score when you have it): in the 2008 Sibelius TTBB both tenors came in at
10.9 s and Baritone and Bass at 3.5 s, each pair within milliseconds, where the
late-ensemble bug shifts one staff by a different 4–12 s every export.

**A voice that stops for good.** Cantai can also stop rendering a staff partway
through and never resume: the last note fades out normally and the rest of the
stem is digital silence. On the two-soloist TTBB Tenor 1, Tenor 2 and
Baritone stopped at 2:48, 3:38 and 4:12 in one export while Bass sang to the
end; on an export of the solo-and-TTBB piece every voice stopped at a different point. List
each stem's sounding spans and last sound, and compare with the section partner
and with any earlier export of the same piece:

```
ffmpeg -hide_banner -i "Tenor 1.wav" -af silencedetect=n=-50dB:d=2 -f null - 2>&1 \
  | grep -oE "silence_(start|end): [0-9.]+"
```

From audio alone this is a question, not a verdict: whether Tenor 2 really rests
from 3:38 is a fact about the score, and "the other parts keep singing" does
not settle it. Report the times and ask. **When the user supplies the MusicXML
the stems were rendered from, check against it instead** with
`stem_vs_score.py`, which reads each part's notes and rests, converts beats to
seconds with the tempo marks, fits the score to the audio, and reports by bar
number every written phrase the stem leaves silent (SILENT) and every written
rest the stem fills (EXTRA, a leak):

```
python3 stem_vs_score.py score.musicxml "Tenor 1=Tenor 1.wav" "Tenor 2=Tenor 2.wav" \
  "Baritone=Baritone.wav" "Bass=Bass.wav"
```

The part names are the MusicXML `<part-name>`s. Tested on the scanned SATB octavo's stems:
clean stems all match; a Tenor 2 copy silenced from 1:40 came back as
`SILENT 1:42.2-2:54.6 (bars 38-66)`; six seconds of Baritone mixed into a
Tenor 1 rest came back as `EXTRA 1:16.3-1:19.2 (bars 28-29)`. It cannot tell two
staves with the same rhythm apart (the Baritone stem filed as Bass passed), and
it does not expand repeats.

**The line-up is anchored at the first entrances.** It used to be fitted to
every phrase onset, and on the unaccompanied TTBB, which is built from repeated "doo doot"
figures, that fit locked on 1.5 bars (2.7 s) late: every stem "matched", and
the one flag it raised, an EXTRA at the Tenor's entrance, was false. It now
takes the offset from where each part first sounds against where the score
brings it in, refines only the tempo, and prints each part's first entrance.
A part that misses the line-up by more than `--tol` is reported LATE — the
ensemble-voice bug of 9.3, which the old fit absorbed into its offset. Tested on
the unaccompanied TTBB's stems: clean stems match with the line-up at −0.05 s; Tenor pushed
5 s late came back `LATE by 5.0 s` (the old fit blamed bars 12–15); Lead
silenced from 1:20 came back `SILENT 1:24.6-1:55.5 (bars 48-65)`, the phrase
already under way at 1:20 still sounding enough to pass; four seconds of Bass
copied into the Tenor's rest in bars 57–58 came back `EXTRA` — only after
`--gap` went from 2.0 to 1.0 s, because a 4.4 s rest less 1.5 s of slack at
each end was too short to judge.

**Which stem is which part, when rhythm cannot tell.** Stems named for the
chorus's sections (Tenor 1, Tenor 2) need not match the score's part names
(Tenor, Lead), and two parts in the same rhythm pass `stem_vs_score.py` either
way round. Settle it with the first entrances (the script prints them) and the
median sung pitch of each stem; on the unaccompanied TTBB, Tenor 1 sat near G4 and Tenor 2 near
C4, so Tenor 1 was the Tenor and Tenor 2 the Lead.

**Stems rendered at different levels.** On the unaccompanied TTBB the Bass stem sang about
9 dB hotter than the other three (median level while sounding), which would
have made the Balanced track mostly Bass. Measure each stem's level while
sounding, not its mean (a part that rests less has a higher mean), and where
one stem is off by several dB, trim that stem before the mix gains and say so
in the handback. That is balancing in the mix (9.1), not evening out the
tracks' loudness (9.4).

### 9.3 What went wrong in Cantai exports

- **The plug-in leaks the previous staff's audio.** The stem exported right
  after Solo (Tenor 1) held the Solo's audio, sample for sample, for its first
  25–38 s, where the score has rests. It reproduced in five exports, with
  ensemble and single voices, with the same and different singers on the two
  staves, and with a separate Cantai instance per staff. Live playback and
  Sibelius's own File > Export > Audio of that staff were both clean.
  Workaround: export the failing staff by hand. Untested: reorder the staves,
  or put an empty staff after Solo, to see whether the leak follows export
  order; if it does, it is worth reporting to the plug-in's author.
- **Ensemble voices enter late.** With "Choir Male" (voices = 6), Tenor 1 came
  in 4–12 s after the rest of the section, by a different amount each export,
  and the individual singers were audible rather than blended. Single solo
  voices entered on time. Prefer single voices for learning tracks.
- **The first export after a settings change can be silent.** Three stems were
  all zeros on the first run and fine on the second.

### 9.4 Mix

```
python3 rehearsal_mix.py "Shenandoah" out/ "Bass=Bass.wav" "Baritone=Baritone.wav" \
  "Tenor 2=Tenor 2.wav" "Tenor 1=Tenor 1.wav" [--accomp "Piano=Piano.wav"] [--trim "Bass=-9"]
```

List the voices **lowest first**: the order sets the panned and 3D layouts. It
prints every stem's level while sounding and suggests a `--trim` for a stem
several dB off the others; apply it and rerun. It writes 2 × parts + 3 mp3s and
prints each one's peak and the gain applied. For the unaccompanied TTBB (four voices, no
accompaniment) that was eleven tracks. What it does, and why:

For each featured part: the featured voice +3 dB, every other voice −21 dB, the
piano at 0 dB, summed without normalising, then encoded. These are the defaults;
use others only when the user asks. The other voices were at −18 dB until
the 2008 Sibelius TTBB, where the user moved them to −21 dB. That lowers the other
singers only: the featured part stays exactly as far above the piano as before,
so if a part is lost under the piano, the fix is the piano level or the
featured level, not the other voices.

```
ffmpeg -i "Tenor 1.aiff" -i "Tenor 2.aiff" -i "Baritone.aiff" -i "Bass.aiff" -i "Piano.aiff" \
  -filter_complex "[0:a]volume=-21dB[a0];[1:a]volume=3dB[a1];[2:a]volume=-21dB[a2];\
[3:a]volume=-21dB[a3];[4:a]volume=0dB[a4];[a0][a1][a2][a3][a4]amix=inputs=5:normalize=0" \
  -c:a libmp3lame -b:a 192k -joint_stereo 1 "Title - (Tenor 2) predominant.mp3"
```

**Always make a Balanced track as well:** every voice and the piano at 0 dB,
nothing featured, as exported. It is part of every set, not an extra.

**Always make a panned Balanced track and a 3D Balanced track as well.** Cantai
single voices come out nearly centred with a little reverb, so the plain
Balanced track puts four singers in one spot. The layouts below are the ones the
user settled on, by ear, on the unaccompanied TTBB. Both are standard; change them only
when the user asks.

- **Panned** (`Title - Balanced panned.mp3`): the voices evenly from 45% left
  (lowest) to 45% right (highest) — four voices at 45% left, 15% left, 15%
  right, 45% right. Constant-power pan, scaled so a centred voice keeps its
  level: at 45% the voice is 6.7 dB louder in the near channel, at 15% 2.1 dB.
  Accompaniment centred.
- **3D** (`Title - Balanced 3D, use headphones.mp3`): each voice folded to mono
  and convolved with the head-related impulse response for its direction, at
  ear height, listener facing north. The lowest voice is rear-left (135°) and
  the highest rear-right (225°); the others are spread evenly across the front
  between 10° left and 10° right — four voices: Bass rear-left, Baritone 10°
  left, Tenor 2 10° right, Tenor 1 rear-right. Accompaniment straight ahead.
  The set is the MIT KEMAR dummy head, measured with "a Realistic Optimus Pro 7
  loudspeaker mounted 1.4 meters from the KEMAR"
  (https://sound.media.mit.edu/resources/KEMAR.html), every 5° at ear height,
  and shipped inside the `slab` package (`pip install slab`; the script stubs
  out slab's audio-playback import, which needs PortAudio). The set is exactly
  left/right symmetric, so a right-hand direction is the left-hand filter with
  the ears swapped. It is loudness-matched to the panned track and then turned
  down on its own if it would clip.

  Headphones only; on speakers it is coloured and the positions collapse. A
  generic dummy head gives clear left/right but unreliable front/back, so a
  rear voice may be heard beside or even ahead of the listener. The HRTF barely
  changes past about a metre and this set has no distance setting: distance
  would come from level, direct-to-reverberant ratio and treble, and a stem's
  baked-in reverb means a voice can be pushed back but not brought closer.

Name them without parentheses: a parenthesised word is how Chorus Connection
knows a section, and there is no section called "3D".

**Soloists and accompaniment in the 3D layout.** The layout is for the choral
parts; a solo would otherwise land by pitch order at rear-right. Place it with
`--place`: the solo-and-TTBB piece has `--place "Solo=0"` (straight ahead, with the
piano); the two-soloist TTBB has `--place "Solo 2=5L" --place "Solo 1=5R"`
(the lower soloist 5° left, the higher 5° right; the piano-and-claps stem
ahead). These were chosen without the user listening; move them if asked.
Accompaniment defaults to straight ahead.

**A 3D track on its own** — for a set made before 3D was standard — is
`--only 3d`. Every mix is still measured, so the 3D track gets the same gain it
would have had in a full run; only the 3D mp3 is written. Use the same `--trim`
values the level report suggests. Made this way for five older sets, with
trims for choral stems 4 dB or more from the others: a Baritone −4.5 dB; in
one set Baritone and Bass −4 dB and both Tenors +4 dB (the Tenors sat 8 dB
under the low voices); a Bass −7.5 dB, and −6.5 dB in the same piece's
ensemble-voice set. The script builds one mix at a time, so seven 4.8-minute stems fit in about
2 GB of memory.

**Always make a part-left track for every part as well.** The featured voice
goes hard left, every other voice hard right, and the piano (or whatever the
accompaniment stem holds) stays centred as exported. All at 0 dB: the panning
does the separating. A singer can take out one earbud, or turn the balance, to
hear their own part with the piano, or the piano and everyone else to sing
against. Fold each voice stem to mono and send it to one side:

```
# featured voice -> left only; every other voice -> right only; piano untouched
[1:a]pan=stereo|c0=0.5*c0+0.5*c1|c1=0*c0[a1]      # featured
[0:a]pan=stereo|c0=0*c0|c1=0.5*c0+0.5*c1[a0]      # each of the others
[4:a]volume=0dB[a4]                               # piano
[a0][a1][a2][a3][a4]amix=inputs=5:normalize=0
```

Averaging the two channels leaves a centred voice at the level it already had
in each channel, so it does not get louder by moving to one side. Check the
result: the left channel minus the right should correlate with the featured
stem minus the others (the centred piano cancels). On the scanned SATB octavo it came out 0.998
for all four parts.

`normalize=0` matters. By default amix scales every input down to share the
headroom and re-scales when a stem ends early, so a track's level would depend
on how many stems went into it and would jump where one ran out. Measure every
mix's peak before encoding (`astats`, as above; `volumedetect` cannot read past
0.0), part-left tracks included. Only if one goes over 0 dBFS, trim all of them
by the same amount, so the tracks keep their loudness relative to one another.
The Balanced track is usually the one that goes over, because nothing in it is
turned down: on the 2008 Sibelius TTBB it reached +2.06 dBFS (686 clipped samples),
so all five tracks were trimmed 3 dB and the Balanced track landed at −1.2 dBFS
after encoding.
Do not otherwise even out the tracks' loudness.

**Filenames for Chorus Connection:** put the section in parentheses —
`Shenandoah - (Tenor 2) predominant.mp3`. A Solo track gets no parentheses;
Chorus Connection has no Solo section to file it under. Nor do the Balanced
tracks, which belong to no section: `Shenandoah - Balanced.mp3`,
`Shenandoah - Balanced panned.mp3`, `Shenandoah - Balanced 3D, use
headphones.mp3`. Part-left tracks follow the same pattern:
`Shenandoah - (Tenor 2) part-left.mp3`, `Shenandoah - Solo part-left.mp3`.

**Check what landed, not what was sent.** On the unaccompanied TTBB a file written to the
user's computer, reported as written, turned out to hold the previous version
of the same filename: the 3D track the user was told had its front voices at
10° still had them at 22.5°. File sizes and checksums do not settle it (the
mp3s written to the user's computer that night each arrived about 5.8 KB larger
than they left, with the audio intact). After delivering, measure the
audio in the file on the user's computer — for a panned or 3D track, each
voice's left/right balance — and resend from a new source path if it is the old
one.

## Scripts

All eight are complete and standalone. Write them out as-is; nothing else is
needed. `check_pdf_type.py` and `find_performer_instructions.py` need only
`pdfplumber`; `musicxml_qc.py` and `cantai_mode.py` need only the standard
library; `lyric_collisions.py` needs `verovio` and `lxml`; `stem_vs_score.py`
needs `numpy` and `ffmpeg`; `verify.py` needs `lxml`, plus `pdfplumber` with
`--pdf` and `verovio` and `cairosvg` with `--render`, and calls
`musicxml_qc.py`, `find_performer_instructions.py` and `lyric_collisions.py`, so
keep all three beside it; `rehearsal_mix.py` needs `numpy`, `ffmpeg` with
libmp3lame, and `slab` for the 3D track.


### check_pdf_type.py

```python
#!/usr/bin/env python3
"""Tell whether a sheet-music PDF is vector (extractable) or a scan (needs OMR)."""
import sys, pdfplumber
def verdict(path):
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[:4]
        glyphs = sum(len(p.chars) for p in pages)
        paths  = sum(len(p.lines) + len(p.curves) + len(p.rects) for p in pages)
        images = sum(len(p.images) for p in pages)
        music  = sum(1 for p in pages for c in p.chars
                     if any(k in c['fontname'] for k in
                            ('Opus','Helsinki','Maestro','Sonata','Petrucci','Emmentaler','Bravura','November')))
        lyr    = sum(1 for p in pages for c in p.chars if 'Opus' not in c['fontname'] and 'Helsinki' not in c['fontname'])
    if music > 200 and paths > 200:
        v = 'VECTOR - fully extractable, OMR adds nothing'
    elif glyphs > 200 and paths > 200:
        v = 'VECTOR (unrecognised music font) - probably extractable'
    elif images and glyphs < 50:
        v = 'SCAN - pixels only, OMR is the only option'
    else:
        v = 'MIXED / uncertain - inspect by hand'
    return dict(file=path.split('/')[-1], music_glyphs=music, text_glyphs=lyr,
                vector_paths=paths, embedded_images=images, verdict=v)
for f in sys.argv[1:]:
    r = verdict(f)
    print(f"{r['file']}\n  music glyphs {r['music_glyphs']:6d} | other text {r['text_glyphs']:6d} | "
          f"vector paths {r['vector_paths']:6d} | images {r['embedded_images']}\n  -> {r['verdict']}\n")
```

### find_performer_instructions.py

```python
#!/usr/bin/env python3
"""List the instructions in an engraving that say WHO sings.

    python3 find_performer_instructions.py score.pdf [--start N]

"Basses only", "unis.", "div.", "tutti", "soli", "tacet", section names. These
change which singers perform a passage. They are invisible to every pitch,
rhythm, bar-length and lyric check, and OMR drops them. Read them before you
decide anything about voice assignment.

--start sets the number of the first bar (use 0 for an uncounted pickup).
Self-contained: needs only pdfplumber.

Note: instructions are not always italic (see 2.4). If this reports nothing,
rerun with --all-text to scan every non-music-font run, then filter by size.
"""
import sys, re, pdfplumber

PERFORMER = re.compile(r'\b(only|unis\.?|div\.?|divisi|tutti|soli|solo|tacet|all|men|women|'
                       r'sopranos?|altos?|tenors?|baritones?|basses?|bari|clap)\b', re.I)
TEMPO_ONLY = re.compile(r'^(ritard|rit\.?|a tempo|accel\.?|rall\.?|gently|smoothly|smmothly|'
                        r'big ritard!?|molto|poco|sub\.?|cresc\.?|dim\.?|[\d\s]+)$', re.I)

def staves_of(page):
    """-> list of staves on the page, each a list of 5 line tops."""
    hs = sorted((l for l in page.lines
                 if abs(l['y0'] - l['y1']) < 0.6 and (l['x1'] - l['x0']) > 150),
                key=lambda l: l['top'])
    tops = [l['top'] for l in hs]
    staves, i = [], 0
    while i <= len(tops) - 5:
        w = tops[i:i + 5]
        gaps = [w[j + 1] - w[j] for j in range(4)]
        if max(gaps) - min(gaps) < 0.15 and gaps[0] > 1.0:
            staves.append(w); i += 5
        else:
            i += 1
    return staves

def split_systems(page, staves):
    """Group staves into systems using the system-start barline: the vertical line
    at the left edge that runs from the top staff to the bottom staff of a system.
    Vertical gaps are NOT reliable — a system break can be smaller than the
    stretch between two staves on a busy page."""
    if not staves: return []
    sh = staves[0][4] - staves[0][0]
    cands = []
    for l in page.lines:
        if abs(l['x0'] - l['x1']) > 0.8: continue
        if (l['bottom'] - l['top']) < sh * 1.6: continue
        idx = tuple(k for k, w in enumerate(staves)
                    if l['top'] - 1 <= w[0] and w[4] <= l['bottom'] + 1)
        if len(idx) >= 2: cands.append((len(idx), idx))
    if not cands:
        return [staves]
    best = max(n for n, _ in cands)
    groups = sorted({idx for n, idx in cands if n == best})
    return [[staves[k] for k in g] for g in groups]

def barlines(page, system):
    """x of every barline in a system: a vertical line spanning a staff, on >=3 staves.
    Brackets and braces sit left of the staff lines, so they are excluded."""
    from collections import Counter
    left = min(l['x0'] for l in page.lines
               if abs(l['y0'] - l['y1']) < 0.6 and (l['x1'] - l['x0']) > 150
               and any(abs(l['top'] - t) < 0.2 for w in system for t in w))
    c = Counter()
    for w in system:
        for l in page.lines:
            if abs(l['x0'] - l['x1']) < 0.6 and l['top'] <= w[0] + 0.6 and l['bottom'] >= w[4] - 0.6:
                c[round(l['x0'])] += 1
    def build(need):
        xs = sorted(x for x, n in c.items() if n >= need and x >= left - 2)
        out = []
        for x in xs:
            if out and x - out[-1] < 5: continue
            out.append(x)
        return out
    # a real barline is drawn on every staff of the system; stems and slur edges
    # can fake one on a few staves. Prefer the strict reading.
    strict = build(len(system))
    return strict if len(strict) >= 2 else build(max(len(system) - 1, 1))

def text_runs(page, all_text=False):
    rows = {}
    for c in page.chars:
        if any(k in c['fontname'] for k in ('Opus', 'Helsinki', 'Maestro', 'Bravura', 'Emmentaler', 'Leland')): continue
        if not all_text and 'Italic' not in c['fontname']: continue
        rows.setdefault((round(c['top'] / 2) * 2, round(c['size'], 1)), []).append(c)
    out = []
    for (top, size), cs in rows.items():
        cs.sort(key=lambda c: c['x0'])
        s, prev = '', None
        for c in cs:
            if prev is not None and c['x0'] - prev > 1.0: s += ' '
            s += c['text']; prev = c['x1']
        out.append({'text': s.strip(), 'top': top, 'size': size,
                    'x0': cs[0]['x0'], 'x1': cs[-1]['x1']})
    return out

def scan(path, start=1, all_text=False):
    hits, measure = [], start
    with pdfplumber.open(path) as pdf:
        layout = []
        for page in pdf.pages:
            staves = staves_of(page)
            systems = split_systems(page, staves)
            layout.append((page, systems, [barlines(page, s) for s in systems]))
        for page, systems, bars in layout:
            for si, system in enumerate(systems):
                bl = bars[si]
                first = measure
                measure += max(len(bl) - 1, 0)
                for r in text_runs(page, all_text):
                    t = r['text']
                    if not t or TEMPO_ONLY.match(t) or not PERFORMER.search(t): continue
                    # an instruction sits ABOVE the staff it governs
                    below = [(pi, w) for pi, w in enumerate(system) if 0 < w[0] - r['top'] < 30]
                    if not below: continue
                    pi, w = min(below, key=lambda z: z[1][0] - r['top'])
                    m = None
                    for k in range(len(bl) - 1):
                        if bl[k] - 2 <= r['x0'] < bl[k + 1] - 2: m = first + k
                    if m is None: continue
                    # text butting against a barline belongs to the bar after it
                    if any(abs(r['x1'] - b) < 4 for b in bl): m += 1
                    hits.append({'text': t, 'page': page.page_number, 'size': r['size'],
                                 'system': si, 'staff': pi, 'measure': m})
    return hits

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    start = 1
    if '--start' in sys.argv: start = int(sys.argv[sys.argv.index('--start') + 1])
    all_text = '--all-text' in sys.argv
    for path in args:
        hits = scan(path, start, all_text)
        print(f'{path.split("/")[-1]}: {len(hits)} performer instruction(s)')
        for h in hits:
            print(f"   p{h['page']} system {h['system']} staff {h['staff']} "
                  f"bar {h['measure']} ({h['size']}pt): {h['text']!r}")
        if not hits:
            print('   none — but say so in your notes; "none found" and '
                  '"never looked" look identical downstream')
```

### musicxml_qc.py

```python
#!/usr/bin/env python3
"""Pre-synthesis QC for MusicXML. Catches the failure modes that wreck singing synthesis:
short/overfull bars, garbled lyrics, and octave discontinuities.

    python3 musicxml_qc.py score.musicxml
"""
import sys, re, zipfile, io
import xml.etree.ElementTree as ET
from fractions import Fraction as F
from collections import defaultdict

def load(path):
    if path.lower().endswith('.mxl'):
        with zipfile.ZipFile(path) as z:
            name=[n for n in z.namelist() if n.endswith(('.xml','.musicxml')) and not n.startswith('META')][0]
            return ET.parse(io.BytesIO(z.read(name))).getroot()
    return ET.parse(path).getroot()

OK_CHARS=re.compile(r"^[A-Za-z][A-Za-z'’\-\.,!?;:\"]*$|^\"[A-Za-z][A-Za-z'’\-\.,!?;:\"]*$")

def qc(path):
    root=load(path)
    issues=defaultdict(list)
    for part in root.findall('part'):
        pid=part.get('id'); div=1; ts=None
        prev_oct=None; octjumps=[]
        seq=[]   # (measure, is_pitched, lyric, has_extend, is_tie_stop)
        for m in part.findall('measure'):
            num=m.get('number')
            for a in m.findall('attributes'):
                d=a.find('divisions')
                if d is not None: div=int(d.text)
                t=a.find('time')
                if t is not None: ts=(int(t.find('beats').text),int(t.find('beat-type').text))
            # --- bar length ---
            pos=F(0); mx=F(0)
            for e in m:
                if e.tag=='note':
                    if e.find('chord') is None: pos+=F(int(e.find('duration').text),div)
                elif e.tag=='backup': pos-=F(int(e.find('duration').text),div)
                elif e.tag=='forward': pos+=F(int(e.find('duration').text),div)
                mx=max(mx,pos)
            if ts:
                exp=F(ts[0]*4,ts[1])
                if mx and mx!=exp:
                    kind='SHORT' if mx<exp else 'OVERFULL'
                    issues['bar length'].append(f"{pid} m{num}: {mx} beats in a {ts[0]}/{ts[1]} bar ({kind})")
            # --- lyrics + octave continuity ---
            for n in m.findall('note'):
                if n.find('chord') is None:
                    ties = [x.get('type') for x in n.findall('tie')]
                    ly = n.find('lyric')
                    if n.find('rest') is not None:
                        seq.append((num, False, None, False, False))
                    else:
                        seq.append((num, True,
                                    ly.findtext('text') if ly is not None else None,
                                    ly is not None and ly.find('extend') is not None and ly.find('extend').get('type') != 'stop',
                                    'stop' in ties))
                        if 'stop' in ties and ly is not None and ly.findtext('text'):
                            issues['syllable on a tie continuation'].append(
                                f"{pid} m{num}: {ly.findtext('text')!r} — a tied note sustains "
                                f"the previous syllable and cannot begin a new one")
                for l in n.findall('lyric'):
                    t=l.find('text')
                    if t is None or not t.text: continue
                    w=t.text.strip()
                    if not OK_CHARS.match(w):
                        issues['garbled lyric'].append(f"{pid} m{num}: {w!r}")
                    elif re.fullmatch(r'(\w{2,})\1', w, re.I):   # 'songsong'; not 'Oo'
                        issues['doubled lyric'].append(f"{pid} m{num}: {w!r}")
                p=n.find('pitch')
                if p is None or n.find('chord') is not None: continue
                o=int(p.find('octave').text)
                if prev_oct is not None and abs(o-prev_oct)>=2:
                    octjumps.append(f"{pid} m{num}: {prev_oct}->{o}")
                prev_oct=o
        # octave leaps only matter where there are lyrics to sing
        if any(True for n in part.iter('lyric')):
            issues['octave jump in a sung line'].extend(octjumps)
            for i,(mn,pit,txt,ext,tie) in enumerate(seq):
                if not pit or txt is not None or tie: continue
                j=i-1; ok=False
                while j>=0:
                    if not seq[j][1]: break            # a rest breaks the melisma
                    if seq[j][2] is not None: ok=seq[j][3]; break
                    j-=1
                if not ok:
                    issues['sung note with no syllable and no extend'].append(f'{pid} m{mn}')
        # --- clef octave consistency (the tenor-8vb trap) ---
        ocs=set()
        for c in part.iter('clef'):
            e=c.find('clef-octave-change')
            ocs.add(e.text if e is not None else '0')
        if len(ocs)>1:
            issues['clef octave flips'].append(f"{pid}: clef-octave-change takes values {sorted(ocs)}")
    return issues

for path in sys.argv[1:]:
    print('='*66); print(path.split('/')[-1])
    iss=qc(path)
    if not iss: print('  clean'); continue
    for k in sorted(iss):
        v=iss[k]
        print(f'  {k}: {len(v)}')
        for line in v[:6]: print(f'      {line}')
        if len(v)>6: print(f'      ... and {len(v)-6} more')
```

### cantai_mode.py

```python
#!/usr/bin/env python3
"""Post-process a finished, print-faithful MusicXML so Cantai (Sibelius's AI singer) sings every note.

    python3 cantai_mode.py in.musicxml out.musicxml [--parts P3,P4,...] [--keep-dotted-ties] [--untie-all]

What it changes (vocal parts only, one voice per part assumed):
  * Inside every melisma that contains a tie, each note that starts a sound gets a piece of the
    syllable: onset+vowel on the syllable note, the bare vowel on intermediate notes, vowel+coda on
    the last.  "gleams" over E♭-(E♭)-(E♭)-D-B♭-C-(C)-D becomes  glea / ea / ea / ea / eams.
  * A dotted tie-continuation in the middle of such a melisma is un-tied and re-sung on the vowel.
    (--keep-dotted-ties turns this off.)
  * --untie-all: EVERY tie continuation inside a real melisma (tie chain followed by at least one
    further sung note) is un-tied and re-sung on the vowel, so no tie survives in a melisma at all
    (blunt fallback for renderers that mis-stitch tied phrases). Plain tied holds that lead straight
    into the next syllable are left alone.
  * Pure slur melismas (no tie) are left as printed — Cantai handles those.
  * Lyric extension lines are re-derived: a piece gets <extend/> only if lyric-less notes follow it.
Prints one line per change.  Standard library only.
"""
import sys, re, copy
import xml.etree.ElementTree as ET

VOWELS = 'aeiouy'

def split_syllable(text, n):
    m = re.match(r"^([^A-Za-z]*)([A-Za-z']*)([^A-Za-z']*)$", text)
    prefix, core, suffix = m.groups() if m else ('', text, '')
    low = core.lower()
    mm = (re.match(r"^(y)([aeiou]+[wy]?)(.*)$", low) if low.startswith('y')
          else re.match(r"^([^aeiou]*?)([aeiouy]+[wy]?)(.*)$", low))
    if n == 1 or not mm or not mm.group(2):
        return [text] + [core] * (n - 1)
    o, nu = mm.group(1), mm.group(2)
    onset, nucleus, coda = core[:len(o)], core[len(o):len(o) + len(nu)], core[len(o) + len(nu):]
    return [prefix + onset + nucleus] + [nucleus] * (n - 2) + [nucleus + coda + suffix]

def is_rest(n): return n.find('rest') is not None
def tie_types(n): return {t.get('type') for t in n.findall('tie')} | {t.get('type') for t in n.findall('tied')}
def lyric_text(n):
    ly = n.find('lyric')
    return ly.findtext('text') if ly is not None else None
def is_dotted(n): return n.find('dot') is not None and n.findtext('type') not in ('whole', 'breve')

def set_lyric(n, text, syllabic, extend):
    for ly in n.findall('lyric'): n.remove(ly)
    ly = ET.SubElement(n, 'lyric'); ly.set('number', '1')
    ET.SubElement(ly, 'syllabic').text = syllabic
    ET.SubElement(ly, 'text').text = text
    if extend: ET.SubElement(ly, 'extend')
    # <lyric> must follow <notations>; move it after the last notations/beam if needed
    kids = list(n)
    n.remove(ly)
    idx = len(kids) - 1
    for i, k in enumerate(kids):
        if k.tag in ('play', 'listen'): idx = i - 1; break
    n.insert(idx + 1 if idx >= 0 else len(kids), ly)

def untie(prev, cur):
    for t in prev.findall('tie'):
        if t.get('type') == 'start': prev.remove(t)
    for nots in prev.findall('notations'):
        for t in nots.findall('tied'):
            if t.get('type') == 'start': nots.remove(t)
        if len(nots) == 0: prev.remove(nots)
    for t in cur.findall('tie'):
        if t.get('type') == 'stop': cur.remove(t)
    for nots in cur.findall('notations'):
        for t in nots.findall('tied'):
            if t.get('type') == 'stop': nots.remove(t)
        if len(nots) == 0: cur.remove(nots)

def process_part(part, keep_dotted, log, untie_all=False):
    notes = []   # (measure number, note element) in order, excluding chord members
    for m in part.findall('measure'):
        for n in m.findall('note'):
            if n.find('chord') is None: notes.append((m.get('number'), n))
    i = 0
    while i < len(notes):
        mn, n = notes[i]
        if is_rest(n) or not lyric_text(n):
            i += 1; continue
        j = i + 1
        while j < len(notes) and not is_rest(notes[j][1]) and not lyric_text(notes[j][1]):
            j += 1
        group = [x for _, x in notes[i:j]]
        has_tie = any('stop' in tie_types(g) for g in group[1:])
        has_melisma = any('stop' not in tie_types(g) for g in group[1:])   # a plain tied hold is not a melisma
        if has_tie and len(group) > 1 and (has_melisma or not untie_all):
            targets = [group[0]]
            for gi in range(1, len(group)):
                g = group[gi]
                followed = any('stop' not in tie_types(h) for h in group[gi + 1:])
                if 'stop' not in tie_types(g):
                    targets.append(g)
                elif untie_all or (is_dotted(g) and followed and not keep_dotted):
                    untie(group[gi - 1], g); targets.append(g)
                    log.append(f"{part.get('id')} m{mn}: tie into {'dotted ' if is_dotted(g) else ''}{g.findtext('type')} removed, note re-sung")
            if len(targets) > 1:
                ly = group[0].find('lyric'); text = ly.findtext('text'); syl = ly.findtext('syllabic') or 'single'
                pieces = split_syllable(text, len(targets))
                first = 'end' if syl in ('middle', 'end') else 'single'
                last = 'begin' if syl in ('begin', 'middle') else 'single'
                for ti, (t, ptxt) in enumerate(zip(targets, pieces)):
                    s = first if ti == 0 else last if ti == len(targets) - 1 else 'single'
                    # extend if lyric-less notes follow before the next target
                    k = group.index(t) + 1
                    ext = k < len(group) and group[k] not in targets
                    set_lyric(t, ptxt, s, ext)
                log.append(f"{part.get('id')} m{mn}: {text!r} -> {' / '.join(pieces)}")
        i = j

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    keep_dotted = '--keep-dotted-ties' in sys.argv
    untie_all = '--untie-all' in sys.argv
    only = None
    if '--parts' in sys.argv: only = set(sys.argv[sys.argv.index('--parts') + 1].split(','))
    tree = ET.parse(args[0]); root = tree.getroot()
    log = []
    for part in root.findall('part'):
        if only and part.get('id') not in only: continue
        if not any(True for _ in part.iter('lyric')): continue      # not a vocal part
        process_part(part, keep_dotted, log, untie_all)
    for l in log: print(l)
    print(f'{len(log)} changes')
    tree.write(args[1], encoding='UTF-8', xml_declaration=True)

if __name__ == '__main__':
    main()
```

### lyric_collisions.py

```python
#!/usr/bin/env python3
"""Flag lyric syllables that would collide horizontally in a Verovio layout.

    python3 lyric_collisions.py laid_out.musicxml [staff_mm]

The input must already carry its <print new-system>/<print new-page> breaks.
Renders it, pulls every syllable's x, baseline and font size out of the SVG,
groups by baseline and reports every consecutive pair whose gap is smaller than
an estimate of the first syllable's printed width.

This is how you choose bars-per-system across a whole score without rendering
and squinting at every page. Verovio's own "justification is highly compressed"
warning is about NOTE spacing and will not fire on a system whose words overlap.

The width estimate is approximate. A gap a little under the estimate is tight
but legible; a gap well under it overlaps. Use it to compare candidate layouts.
Needs verovio and lxml.
"""
import sys
import verovio
from lxml import etree

NS = {'s': 'http://www.w3.org/2000/svg'}
NARROW = set("ijltfr.,'’ ")

def width(t, fs):
    return sum(fs * (0.30 if c in NARROW else 0.56) for c in t)

def check(path, staff_mm=7.0, page=(2159, 2794), marg=(140, 110, 130, 120)):
    """page and margins in 1/10 mm: (w, h) and (left, right, top, bottom)."""
    tk = verovio.toolkit()
    tk.setOptions({"pageWidth": page[0], "pageHeight": page[1],
                   "pageMarginLeft": marg[0], "pageMarginRight": marg[1],
                   "pageMarginTop": marg[2], "pageMarginBottom": marg[3],
                   "unit": staff_mm / 4 * 10 / 2, "adjustPageHeight": False,
                   "breaks": "encoded", "svgViewBox": True})
    tk.loadFile(path)
    bad = []
    for pg in range(1, tk.getPageCount() + 1):
        root = etree.fromstring(tk.renderToSVG(pg).encode())
        rows = {}
        for g in root.xpath('//s:g[@class="syl"]', namespaces=NS):
            ts = g.xpath('.//s:text', namespaces=NS)
            inner = g.xpath('.//s:tspan[@font-size]', namespaces=NS)
            if not ts or not inner: continue
            txt = ''.join(ts[0].itertext()).strip()
            if not txt: continue
            fs = float(inner[-1].get('font-size').rstrip('px'))
            try:
                x, y = float(ts[0].get('x')), float(ts[0].get('y'))
            except (TypeError, ValueError):
                continue
            # SVG inner units are 10x the viewBox; /20 buckets one lyric baseline
            rows.setdefault(round(y / 20), []).append((x, txt, fs))
        for row in rows.values():
            row.sort()
            for (x1, t1, fs), (x2, t2, _) in zip(row, row[1:]):
                need = width(t1, fs)
                if x2 - x1 < need:
                    bad.append((pg, t1, t2, round(x2 - x1), round(need)))
    return tk.getPageCount(), bad

if __name__ == '__main__':
    mm = float(sys.argv[2]) if len(sys.argv) > 2 else 7.0
    n, bad = check(sys.argv[1], mm)
    print(f'{n} pages, {len(bad)} overlapping syllable pair(s)')
    for pg, a, b, gap, need in bad:
        print(f'   p{pg}: {a!r} -> {b!r}   gap {gap} < {need}')
    if not bad:
        print('   none — this layout is printable')
```

### stem_vs_score.py

```python
#!/usr/bin/env python3
"""Check exported audio stems against the MusicXML they were rendered from.

    python3 stem_vs_score.py score.musicxml "Tenor 1=T1.wav" "Tenor 2=T2.wav" ...
        [--thresh -50] [--gap 1.0] [--tol 1.5]

Each argument after the score pairs a part name (as in <part-name>) with its
stem. For every part the script lists where the score has notes and where it
rests, converts beats to seconds with the score's tempo marks, lines the score
up with the audio, and reports, by bar number:

  SILENT  - a written phrase (or run of phrases) with next to no sound in the
            stem: a renderer that stopped, or a staff exported empty
  EXTRA   - a written rest (at least --gap s long once the slack is taken
            off) that mostly sounds in the stem: audio leaked in from another
            staff
  LATE    - a part whose first entrance misses the line-up by more than --tol:
            the late-entrance bug of an ensemble Cantai voice

It cannot tell apart two staves that sing the same rhythm (a stem filed under
the wrong name in homophonic writing passes); the checksum comparison in the
stem checks catches exact copies. Repeats, D.S. and D.C. are not expanded, so
a score that uses them reports everything after the first jump; check against
a copy with the repeats written out.

Alignment: a straight-line map from score seconds to audio seconds, anchored at
the parts' first entrances (the median of stem entrance minus score entrance),
with only the tempo refined on the onsets of every part's phrases. A part whose
first entrance misses the anchor by more than --tol is reported LATE or EARLY:
that is the late-entrance bug of an ensemble Cantai voice. The map absorbs the
lead-in silence and a uniformly faster or slower playback, but not a ritard or fermata that playback
stretches more than the file says; --tol (seconds of slack at every phrase edge)
covers most of that. A phrase counts as missing only when under 10% of its
middle sounds, and a rest as leaked only when over 30% of its middle sounds,
so breaths, reverb tails and short rests do not trigger anything.

Needs numpy and ffmpeg on the PATH.
"""
import sys, subprocess, argparse
import xml.etree.ElementTree as ET
import numpy as np

HOP = 0.05   # seconds per envelope frame


def load_score(path):
    root = ET.parse(path).getroot()
    names = {sp.get('id'): (sp.findtext('part-name') or '').strip()
             for sp in root.iter('score-part')}
    parts, bar_starts, tempos = {}, None, []
    for pi, part in enumerate(root.findall('part')):
        div, pos, spans, starts = 1, 0.0, [], []
        for m in part.findall('measure'):
            starts.append((pos, m.get('number')))
            t, mx = pos, pos
            for e in m:
                if e.tag == 'attributes' and e.find('divisions') is not None:
                    div = int(e.findtext('divisions'))
                elif e.tag in ('direction', 'sound'):
                    s = e if e.tag == 'sound' else e.find('sound')
                    if pi == 0 and s is not None and s.get('tempo'):
                        off = e.findtext('offset')
                        tempos.append((t + (int(off) / div if off else 0.0), float(s.get('tempo'))))
                elif e.tag == 'backup':
                    t -= int(e.findtext('duration')) / div
                elif e.tag == 'forward':
                    t += int(e.findtext('duration')) / div
                elif e.tag == 'note':
                    if e.find('grace') is not None:
                        continue
                    d = int(e.findtext('duration') or 0) / div
                    if e.find('chord') is not None:
                        continue
                    if e.find('rest') is None and d > 0:
                        spans.append((t, t + d))
                    t += d
                mx = max(mx, t)
            pos = mx
        spans.sort()
        merged = []
        for a, b in spans:
            if merged and a <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        parts[names.get(part.get('id'), part.get('id'))] = merged
        if bar_starts is None:
            bar_starts = starts + [(pos, 'end')]
    tempos.sort(key=lambda bt: bt[0])          # stable: keeps file order at equal positions
    if not tempos or tempos[0][0] > 0.0:
        tempos.insert(0, (0.0, tempos[0][1] if tempos else 120.0))
    return parts, bar_starts, tempos


def beats_to_sec(b, tempos):
    s, (b0, q0) = 0.0, tempos[0]
    for b1, q1 in tempos[1:]:
        if b <= b1:
            break
        s += (b1 - b0) * 60.0 / q0
        b0, q0 = b1, q1
    return s + (b - b0) * 60.0 / q0


def envelope(wav, thresh):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', wav, '-ac', '1', '-ar', '8000',
                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    w = int(8000 * HOP)
    n = len(a) // w
    rms = np.sqrt(np.mean(a[:n * w].reshape(n, w) ** 2, axis=1) + 1e-20)
    return 20 * np.log10(rms) > thresh


def runs(mask, value=True):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i] == value:
            j = i
            while j < n and mask[j] == value:
                j += 1
            out.append((i * HOP, j * HOP))
            i = j
        else:
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('score')
    ap.add_argument('pairs', nargs='+', help='"Part name=stem.wav"')
    ap.add_argument('--thresh', type=float, default=-50.0, help='dBFS; quieter counts as silent')
    ap.add_argument('--gap', type=float, default=1.0, help='shortest rest (after slack) worth judging (s)')
    ap.add_argument('--tol', type=float, default=1.5, help='slack at every phrase edge (s)')
    a = ap.parse_args()

    parts, bars, tempos = load_score(a.score)
    stems = {}
    for p in a.pairs:
        name, wav = p.split('=', 1)
        if name not in parts:
            sys.exit(f'no part named {name!r}; the score has {sorted(parts)}')
        stems[name] = envelope(wav, a.thresh)

    # phrase onsets: score (seconds at the written tempo) and audio
    sc = {n: [(beats_to_sec(x, tempos), beats_to_sec(y, tempos)) for x, y in parts[n]] for n in stems}
    au = {n: [r for r in runs(stems[n]) if r[1] - r[0] >= 0.3] for n in stems}
    # Anchor the line-up at the first entrances: where each part first sounds in its stem
    # against where the score says it comes in. Fitting on phrase onsets alone can lock on a
    # bar or two late in music built from repeated figures (one piece: 2.7 s late, a false EXTRA
    # at the Tenor entrance), because every "doo doot" looks like its neighbour.
    firsts = {n: (sc[n][0][0], au[n][0][0]) for n in stems if sc[n] and au[n]}
    if not firsts:
        sys.exit('no part has both notes in the score and sound in its stem')
    off = float(np.median([y - x for x, y in firsts.values()]))
    scale, pairs = 1.0, []
    for win in (1.5, 1.0, 0.75):             # refine the tempo only; the anchor stays put
        pairs = []
        for n in stems:
            ons = np.array([r[0] for r in au[n]])
            if not len(ons):
                continue
            for x, _y in sc[n]:
                g = off + scale * x
                k = int(np.argmin(np.abs(ons - g)))
                if abs(ons[k] - g) < win:
                    pairs.append((x, ons[k]))
        if len(pairs) >= 4:
            X = np.array(pairs)
            s = float(np.dot(X[:, 0], X[:, 1] - off) / max(np.dot(X[:, 0], X[:, 0]), 1e-9))
            scale = min(max(s, 0.9), 1.1)
    to_audio = lambda s: off + scale * s

    bar_sec = [(to_audio(beats_to_sec(b, tempos)), num) for b, num in bars]
    def bar_at(t):
        cur = bar_sec[0][1]
        for s, num in bar_sec:
            if s <= t + 1e-6 and num != 'end':
                cur = num
        return cur
    fmt = lambda t: ('-' if t < 0 else '') + f'{int(abs(t) // 60)}:{abs(t) % 60:04.1f}'

    print(f'alignment: audio = {off:+.2f} s + {scale:.4f} x score time '
          f'(anchored at the first entrances; {len(pairs) if len(pairs) >= 4 else 0} phrase onsets fitted)')
    problems = 0
    print('\nfirst entrances (score -> audio):')
    for n, (x, y) in firsts.items():
        late = y - to_audio(x)
        flag = ''
        if abs(late) > a.tol:
            flag = f'   <- {"LATE" if late > 0 else "EARLY"} by {abs(late):.1f} s'
            problems += 1
        print(f'   {n}: bar {bar_at(to_audio(x))}, {fmt(to_audio(x))} expected, {fmt(y)} in the stem{flag}')
    for n in stems:
        mask = stems[n]
        L = len(mask)
        found = []
        # SILENT: judge each written phrase as a whole; a phrase whose middle is
        # (almost) soundless is missing, and consecutive missing phrases merge
        miss = []
        for x, y in sc[n]:
            s0, s1 = to_audio(x), to_audio(y)
            edge = min(a.tol, 0.25 * (s1 - s0))
            i0, i1 = int((s0 + edge) / HOP), int((s1 - edge) / HOP)
            if i1 - i0 < int(0.5 / HOP):
                continue                     # too short to judge
            cov = float(mask[max(i0, 0):min(i1, L)].mean()) if i0 < L else 0.0
            if cov < 0.1:
                if miss and miss[-1][2]:
                    miss[-1][1] = s1
                else:
                    miss.append([s0, s1, True])
            elif miss:
                miss[-1][2] = False
        for t0, t1, _ in miss:
            found.append(('SILENT', t0, t1))
        # EXTRA: judge each written rest (including before the first note and
        # after the last) the same way; a rest whose middle mostly sounds is a leak
        edges = [(to_audio(x), to_audio(y)) for x, y in sc[n]]
        rests, prev = [], 0.0
        for s0, s1 in edges:
            rests.append((prev, s0)); prev = s1
        rests.append((prev, L * HOP))
        for r0, r1 in rests:
            i0, i1 = int((r0 + a.tol) / HOP), int((r1 - a.tol) / HOP)
            if (i1 - i0) * HOP < a.gap or i0 >= L:
                continue
            seg = mask[max(i0, 0):min(i1, L)]
            if seg.mean() > 0.3:
                on = np.flatnonzero(seg)
                found.append(('EXTRA ', (max(i0, 0) + on[0]) * HOP, (max(i0, 0) + on[-1] + 1) * HOP))
        found.sort(key=lambda f: f[1])
        print(f'\n{n}: ' + ('matches the score' if not found else f'{len(found)} disagreement(s)'))
        for kind, t0, t1 in found:
            print(f'   {kind} {fmt(t0)}-{fmt(t1)}  (bars {bar_at(t0)}-{bar_at(t1)})')
        problems += len(found)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
```

### verify.py

```python
#!/usr/bin/env python3
"""Run every Step 5 check on a finished MusicXML and print one line per check.

    python3 verify.py score.musicxml [--pdf score.pdf] [--lanes "0a=Tenor,0b=Lead,1a=Baritone,1b=Bass"]
                      [--original before.musicxml] [--render out_dir] [--xsd schema_dir]

Every check ends as one of
    PASS      checked, nothing found
    FAIL      checked, something to fix (details follow the table)
    WARN      checked, something to look at
    MANUAL    needs a person; the line says what to look at
    N/A       does not apply to this file (the line says why)
    NOT RUN   could not run; the line says what input is missing

Paste the table into the handback as printed. A check that did not run is
reported as NOT RUN, never left out: an empty result and a check nobody ran look
the same in the output, and that is how check 10 was once skipped.

--pdf enables the checks that compare against the engraving (6, 10, 11, 12).
--lanes says which part each lyric line of the PDF belongs to: `<staff>a` is
the line above that staff of a system, `<staff>b` the line below, staves counted
from 0 within a system. Default when the PDF has one staff per part: `<k>b` is
part k. A closed score (two parts to a staff) needs --lanes.

Needs lxml; pdfplumber with --pdf; verovio and cairosvg with --render.
Exit status 1 if any check FAILs.
"""
import sys, os, re, argparse, subprocess, difflib, statistics
from collections import defaultdict
from fractions import Fraction as F
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = 'https://raw.githubusercontent.com/w3c/musicxml/v4.0/schema/'
MUSIC_FONTS = ('Opus', 'Helsinki', 'Maestro', 'Sonata', 'Petrucci', 'Emmentaler', 'Bravura',
               'Leland', 'November', 'Leipzig', 'Finale', 'Engraver')
STEPS = 'CDEFGAB'

results = []          # (number, name, status, summary)
details = defaultdict(list)


def report(n, name, status, summary, lines=()):
    results.append((n, name, status, summary))
    details[n].extend(lines)


# ----------------------------------------------------------------- the MusicXML

def load(path):
    root = ET.parse(path).getroot()
    names = {sp.get('id'): (sp.findtext('part-name') or sp.get('id')).strip() for sp in root.iter('score-part')}
    return root, names


def notes_of(part):
    """[(measure number, note element, voice, onset in quarters from the bar line)] in file order."""
    out, div = [], 1
    for m in part.findall('measure'):
        pos = {}
        t = F(0)
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= F(int(e.findtext('duration')), div)
            elif e.tag == 'forward':
                t += F(int(e.findtext('duration')), div)
            elif e.tag == 'note':
                d = F(int(e.findtext('duration') or 0), div)
                if e.find('chord') is not None:
                    out.append((m.get('number'), e, e.findtext('voice') or '1', out[-1][3] if out else t))
                    continue
                out.append((m.get('number'), e, e.findtext('voice') or '1', t))
                if e.find('grace') is None:
                    t += d
    return out


def pitch_midi(p):
    return 12 * (int(p.findtext('octave')) + 1) + [0, 2, 4, 5, 7, 9, 11][STEPS.index(p.findtext('step'))] + int(float(p.findtext('alter') or 0))


def pname(midi):
    return ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'][midi % 12] + str(midi // 12 - 1)


# ----------------------------------------------------------------- checks on the file alone

def check_xsd(path, xsd_dir):
    try:
        from lxml import etree
    except ImportError:
        return report(1, 'XSD', 'NOT RUN', 'lxml not installed')
    xsd_dir = xsd_dir or os.path.join(HERE, '.musicxml-schema')
    os.makedirs(xsd_dir, exist_ok=True)
    main = os.path.join(xsd_dir, 'musicxml.xsd')
    try:
        for f in ('musicxml.xsd', 'xml.xsd', 'xlink.xsd'):
            dst = os.path.join(xsd_dir, f)
            if not os.path.exists(dst):
                import urllib.request
                urllib.request.urlretrieve(SCHEMA + f, dst)
        s = open(main).read()
        s2 = re.sub(r'schemaLocation="[^"]*/(xml|xlink)\.xsd"', r'schemaLocation="\1.xsd"', s)
        if s2 != s: open(main, 'w').write(s2)
        schema = etree.XMLSchema(etree.parse(main))
    except Exception as ex:
        return report(1, 'XSD', 'NOT RUN', f'schema unavailable ({ex.__class__.__name__}); pass --xsd DIR with musicxml.xsd, xml.xsd, xlink.xsd')
    ok = schema.validate(etree.parse(path))
    report(1, 'XSD', 'PASS' if ok else 'FAIL', 'valid MusicXML 4.0' if ok else f'{len(schema.error_log)} schema error(s)',
           [str(e) for e in list(schema.error_log)[:10]])


def check_bars(root, names):
    bad = []
    for part in root.findall('part'):
        div, ts = 1, None
        for m in part.findall('measure'):
            for a in m.findall('attributes'):
                if a.find('divisions') is not None: div = int(a.findtext('divisions'))
                if a.find('time') is not None:
                    ts = (int(a.find('time').findtext('beats')), int(a.find('time').findtext('beat-type')))
            pos = mx = F(0)
            for e in m:
                if e.tag == 'note' and e.find('chord') is None and e.find('grace') is None:
                    pos += F(int(e.findtext('duration')), div)
                elif e.tag == 'backup': pos -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward': pos += F(int(e.findtext('duration')), div)
                mx = max(mx, pos)
            if ts and m.get('implicit') != 'yes' and mx != F(ts[0] * 4, ts[1]):
                bad.append(f"{names[part.get('id')]} bar {m.get('number')}: {mx} quarters in {ts[0]}/{ts[1]}")
    report(2, 'Bar lengths', 'FAIL' if bad else 'PASS', f'{len(bad)} bar(s) off' if bad else 'every bar fills its meter', bad)


RANGES = [  # (name keyword, lowest, highest) sounding, generous
    ('sop', 'A3', 'C6'), ('alt', 'E3', 'F5'), ('ten', 'B2', 'C5'), ('lead', 'A2', 'A4'),
    ('bari', 'F2', 'F4'), ('bass', 'C2', 'E4')]


def midi_of(name):
    m = re.fullmatch(r'([A-G])(b|#)?(-?\d)', name)
    return 12 * (int(m.group(3)) + 1) + [0, 2, 4, 5, 7, 9, 11][STEPS.index(m.group(1))] + {'b': -1, '#': 1, None: 0}[m.group(2)]


def check_ranges(root, names):
    lines, status = [], 'PASS'
    for part in root.findall('part'):
        ps = [pitch_midi(n.find('pitch')) for _, n, _, _ in notes_of(part) if n.find('pitch') is not None]
        if not ps: continue
        nm = names[part.get('id')]
        lo, hi = min(ps), max(ps)
        rule = next((r for r in RANGES if r[0] in nm.lower()), None)
        verdict = ''
        if rule:
            a, b = midi_of(rule[1]), midi_of(rule[2])
            if lo < a - 11 or hi > b + 11:
                verdict = '  <- an octave outside the usual range: octave/clef error?'; status = 'FAIL'
            elif lo < a or hi > b:
                verdict = f'  <- outside {rule[1]}-{rule[2]}'; status = 'WARN' if status == 'PASS' else status
        lines.append(f'{nm}: {pname(lo)}-{pname(hi)}{verdict}')
    report(3, 'Ranges', status, '; '.join(l.split('  <-')[0] for l in lines), [l for l in lines if '<-' in l])


def check_qc(path):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'musicxml_qc.py'), path], capture_output=True, text=True)
    cats = [l.strip() for l in r.stdout.splitlines() if re.match(r'\s+\S.*: \d+$', l)]
    bad = [c for c in cats if not c.endswith(': 0')]
    report(4, 'musicxml_qc.py', 'FAIL' if bad else 'PASS', '; '.join(bad) if bad else 'clean',
           [l for l in r.stdout.splitlines()[2:] if l.strip()] if bad else [])


def check_render(path, out):
    if not out:
        return report(5, 'Render vs PDF', 'MANUAL', 'pass --render DIR to write page images, then compare them with the PDF page by page')
    try:
        import verovio, cairosvg
    except ImportError:
        return report(5, 'Render vs PDF', 'NOT RUN', 'verovio / cairosvg not installed')
    os.makedirs(out, exist_ok=True)
    tk = verovio.toolkit()
    tk.setOptions({'pageWidth': 2159, 'pageHeight': 2794, 'unit': 8, 'breaks': 'auto', 'adjustPageHeight': True})
    tk.loadFile(path)
    for i in range(1, tk.getPageCount() + 1):
        cairosvg.svg2png(bytestring=tk.renderToSVG(i).encode(), write_to=os.path.join(out, f'page{i}.png'),
                         output_width=1400, background_color='white')
    report(5, 'Render vs PDF', 'MANUAL', f'{tk.getPageCount()} page(s) in {out}/ - compare with the PDF, page by page')


def check_ties(root, names):
    bad = []
    for part in root.findall('part'):
        byv = defaultdict(list)
        for mn, n, v, _ in notes_of(part):
            if n.find('chord') is not None: continue
            byv[v].append((mn, n))
        for v, seq in byv.items():
            for i, (mn, n) in enumerate(seq):
                t = {x.get('type') for x in n.findall('tie')}
                if 'start' in t:
                    nxt = seq[i + 1][1] if i + 1 < len(seq) else None
                    if nxt is None or nxt.find('pitch') is None or 'stop' not in {x.get('type') for x in nxt.findall('tie')} \
                            or pitch_midi(nxt.find('pitch')) != pitch_midi(n.find('pitch')):
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: tie start with no matching stop")
                if 'stop' in t:
                    prv = seq[i - 1][1] if i else None
                    if prv is None or 'start' not in {x.get('type') for x in prv.findall('tie')}:
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: tie stop with no start")
    report(8, 'Ties pair up', 'FAIL' if bad else 'PASS', f'{len(bad)} unpaired' if bad else 'every tie pairs', bad)


def check_words(root, names, out_dir):
    bad, words = [], []
    for part in root.findall('part'):
        cur = {}
        for mn, n, v, _ in notes_of(part):
            for l in n.findall('lyric'):
                k = (v, l.get('number', '1'))
                syl, txt = l.findtext('syllabic') or 'single', l.findtext('text') or ''
                if syl in ('single', 'begin'):
                    if k in cur: bad.append(f"{names[part.get('id')]} bar {mn}: word {cur[k][1]!r} never ended")
                    cur[k] = (mn, txt)
                elif k not in cur:
                    bad.append(f"{names[part.get('id')]} bar {mn}: {syl} syllable {txt!r} with no word start")
                    cur[k] = (mn, txt)
                else:
                    cur[k] = (cur[k][0], cur[k][1] + txt)
                if syl in ('single', 'end') and k in cur:
                    words.append(f"{names[part.get('id')]} bar {cur[k][0]}: {cur[k][1]}")
                    del cur[k]
        for k, (mn, w) in cur.items():
            bad.append(f"{names[part.get('id')]} bar {mn}: word {w!r} never ended")
    fn = os.path.join(out_dir, 'words.txt')
    open(fn, 'w').write('\n'.join(words) + '\n')
    if bad:
        report(9, 'Words reassemble', 'FAIL', f'{len(bad)} broken hyphen chain(s)', bad)
    else:
        report(9, 'Words reassemble', 'MANUAL', f'hyphen chains all close; read the {len(words)} words in {fn} for typos')


def check_extend_runs(root, names):
    """14: an <extend/> needs a following note in the same voice for the line to run under."""
    bad = []
    for part in root.findall('part'):
        byv = defaultdict(list)
        for mn, n, v, _ in notes_of(part):
            if n.find('chord') is None: byv[v].append((mn, n))
        for v, seq in byv.items():
            for i, (mn, n) in enumerate(seq):
                for l in n.findall('lyric'):
                    e = l.find('extend')
                    if e is None or e.get('type') == 'stop': continue
                    nxt = seq[i + 1][1] if i + 1 < len(seq) else None
                    if nxt is None or nxt.find('rest') is not None or nxt.find('lyric') is not None:
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: {l.findtext('text')!r} extends over no note")
                    if (l.findtext('syllabic') or 'single') in ('begin', 'middle'):
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: {l.findtext('text')!r} is mid-word; "
                                   f"it prints a hyphen, and an extender would replace it (unless the PDF prints one)")
    report(14, 'No extender outruns its voice', 'FAIL' if bad else 'PASS', f'{len(bad)} problem(s)' if bad else 'every extender has notes under it', bad)


def multi_voice_staves(root):
    for part in root.findall('part'):
        vs = {n.findtext('voice') for n in part.iter('note') if n.find('rest') is None}
        if len(vs) > 1: return True
    return False


def check_shared_staff(root):
    if not multi_voice_staves(root):
        return report(13, 'Shared-staff lyric reads', 'N/A', 'no staff carries two voices')
    report(13, 'Shared-staff lyric reads', 'MANUAL',
           'staves carry two voices: rebuild each singer\'s read (line 2 where it has its own note, line 1 where shared) '
           'and compare with that voice\'s syllables (SKILL.md 7.4)')


def check_layout(path, root):
    if root.find('.//print[@new-system="yes"]') is None and root.find('.//print[@new-page="yes"]') is None:
        return report(15, 'Lyric collisions', 'N/A', 'no print layout in the file (no system or page breaks)')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'lyric_collisions.py'), path], capture_output=True, text=True)
    m = re.search(r'(\d+) overlapping', r.stdout)
    n = int(m.group(1)) if m else -1
    report(15, 'Lyric collisions', 'PASS' if n == 0 else ('FAIL' if n > 0 else 'NOT RUN'),
           f'{n} overlapping pair(s)' if n >= 0 else 'lyric_collisions.py failed', r.stdout.splitlines()[1:21])


def check_original(root, names, original):
    if not original:
        return report(16, 'Revoicing vs original', 'N/A', 'no --original given (not a revoicing)')
    oroot, onames = load(original)
    def grid(r, nm):
        g = defaultdict(set)
        for part in r.findall('part'):
            for mn, n, v, t in notes_of(part):
                if n.find('pitch') is not None:
                    g[(mn, t)].add(pitch_midi(n.find('pitch')) % 12)
        return g
    a, b = grid(oroot, onames), grid(root, names)
    diff = sorted({k[0] for k in set(a) | set(b) if a.get(k) != b.get(k)}, key=lambda x: int(re.sub(r'\D', '', x) or 0))
    report(16, 'Revoicing vs original', 'MANUAL' if diff else 'PASS',
           f'pitch classes differ in {len(diff)} bar(s); each must be on the instruction list' if diff else 'same pitch classes at every onset',
           [f'bars: {", ".join(diff)}'] if diff else [])


# ----------------------------------------------------------------- checks against the PDF

def staves_of(page):
    hs = sorted((l for l in page.lines if abs(l['y0'] - l['y1']) < 0.6 and (l['x1'] - l['x0']) > 150), key=lambda l: l['top'])
    tops = []
    for l in hs:
        if not tops or abs(l['top'] - tops[-1][0]) > 0.3: tops.append((l['top'], l['x0'], l['x1']))
    st, i = [], 0
    while i <= len(tops) - 5:
        w = [t[0] for t in tops[i:i + 5]]
        g = [w[j + 1] - w[j] for j in range(4)]
        if max(g) - min(g) < 0.2 and g[0] > 1.0:
            st.append({'lines': w, 'x0': tops[i][1], 'x1': tops[i][2]}); i += 5
        else:
            i += 1
    return st


def systems_of(page, st):
    """group staves into systems by the vertical line that joins them at the left edge"""
    if not st: return []
    sh = st[0]['lines'][4] - st[0]['lines'][0]
    joins = set()
    for l in page.lines:
        if abs(l['x0'] - l['x1']) > 0.8 or l['bottom'] - l['top'] < sh * 1.6: continue
        idx = tuple(k for k, s in enumerate(st) if l['top'] - 1 <= s['lines'][0] and s['lines'][4] <= l['bottom'] + 1)
        if len(idx) >= 2: joins.add(idx)
    groups, used = [], set()
    for idx in sorted(joins, key=len, reverse=True):
        if used & set(idx): continue
        groups.append(list(idx)); used |= set(idx)
    for k in range(len(st)):
        if k not in used: groups.append([k])
    groups.sort()
    return [[st[k] for k in g] for g in groups]


def is_ledger(l, st, p):
    """a short line on a staff's ledger grid with a notehead over it"""
    if not st or l['x1'] - l['x0'] > 20: return False
    s = min(st, key=lambda s: abs((s['lines'][0] + s['lines'][4]) / 2 - l['top']))
    sp = (s['lines'][4] - s['lines'][0]) / 4
    edge = s['lines'][0] if l['top'] < s['lines'][0] else s['lines'][4]
    k = abs(l['top'] - edge) / sp
    if abs(k - round(k)) > 0.15 or round(k) < 1 or round(k) > 6: return False
    for c in p.chars:
        if any(f in c['fontname'] for f in MUSIC_FONTS) and (ord(c['text'][0]) in HEADS or c['text'] == 'w') \
                and c['x0'] < l['x1'] and c['x1'] > l['x0'] and abs((p.height - c['matrix'][5]) - l['top']) <= 4 * sp:
            return True
    return False


class Engraving:
    def __init__(self, path, lyric_font=None, lyric_size=None):
        import pdfplumber
        self.pages = []
        with pdfplumber.open(path) as pdf:
            from collections import Counter
            text = Counter()
            for p in pdf.pages:
                for c in p.chars:
                    if not any(f in c['fontname'] for f in MUSIC_FONTS) and c['text'].isalpha():
                        text[(c['fontname'], round(c['size'], 1))] += 1
            lf = text.most_common(1)[0][0] if text else (None, None)
            self.lyric_font = lyric_font or lf[0]
            self.lyric_size = lyric_size or lf[1]
            for p in pdf.pages:
                st = staves_of(p)
                sysl = systems_of(p, st)
                self.pages.append({
                    'n': p.page_number, 'height': p.height, 'systems': sysl,
                    'sp': statistics.median([(s['lines'][4] - s['lines'][0]) / 4 for s in st]) if st else 4.0,
                    'chars': [dict(t=c['text'], x0=c['x0'], x1=c['x1'], top=c['top'], font=c['fontname'],
                                   size=round(c['size'], 1), y=p.height - c['matrix'][5]) for c in p.chars],
                    'hlines': [(l['x0'], l['x1'], l['top']) for l in p.lines
                               if abs(l['y0'] - l['y1']) < 0.3 and l['x1'] - l['x0'] > 2
                               and not any(abs(l['top'] - y) < 0.3 for s in st for y in s['lines'])
                               and not is_ledger(l, st, p)],
                    'vlines': [(l['x0'], l['top'], l['bottom']) for l in p.lines if abs(l['x0'] - l['x1']) < 0.3],
                })

    def home(self, page, y):
        """(system index, lane) for a mark at height y: lane '<staff>a' above that staff, '<staff>b' below."""
        best = None
        for si, sy in enumerate(page['systems']):
            top, bot = sy[0]['lines'][0], sy[-1]['lines'][4]
            d = top - y if y < top else (y - bot if y > bot else 0)
            if best is None or d < best[0]: best = (d, si)
        if best is None: return None, None
        d, si = best
        sy = page['systems'][si]
        for k, s in enumerate(sy):
            if s['lines'][0] <= y <= s['lines'][4]: return si, None     # inside a staff
        for k, s in enumerate(sy):
            if y < s['lines'][0]:
                if k == 0: return si, f'{k}a'
                prev = sy[k - 1]['lines'][4]
                return si, (f'{k - 1}b' if y - prev < s['lines'][0] - y else f'{k}a')
        return si, f'{len(sy) - 1}b'

    def lyric_rows(self):
        """-> [(page idx, system idx, lane, top, [syllable dicts])] in reading order."""
        out = []
        for pi, page in enumerate(self.pages):
            cs = [c for c in page['chars'] if c['font'] == self.lyric_font and c['size'] == self.lyric_size]
            rows = []
            for c in sorted(cs, key=lambda c: c['top']):
                for r in rows:
                    if abs(r[0] - c['top']) < 1.0: r[1].append(c); break
                else: rows.append([c['top'], [c]])
            for top, chars in rows:
                si, lane = self.home(page, top + 0.75 * self.lyric_size)
                if si is None or lane is None: continue
                sy = page['systems'][si]
                if top < sy[0]['lines'][0] - 12 * page['sp'] or top > sy[-1]['lines'][4] + 12 * page['sp']: continue
                syl = syllables(chars)
                for x in syl: x['top'] = top
                out.append((pi, si, lane, top, syl))
        # one lane can be set at two heights in one system (a phrase nudged down to clear
        # something): merge them and read left to right
        merged = {}
        for pi, si, lane, top, syl in out:
            merged.setdefault((pi, si, lane), [pi, si, lane, top, []])[4].extend(syl)
        out = []
        for r in merged.values():
            r[4].sort(key=lambda x: x['x0'])
            r[3] = min(x['top'] for x in r[4])
            out.append(tuple(r))
        out.sort(key=lambda r: (r[0], r[1], r[3]))
        return out


def syllables(chars):
    chars = sorted(chars, key=lambda c: c['x0'])
    toks = []
    for c in chars:
        if toks and c['x0'] - toks[-1]['x1'] < 0.25 and c['t'] != '-' and not toks[-1]['t'].endswith('-'):
            toks[-1]['t'] += c['t']; toks[-1]['x1'] = c['x1']
        else:
            toks.append({'t': c['t'], 'x0': c['x0'], 'x1': c['x1']})
    out = []
    for t in toks:
        if not t['t'].strip(): continue
        if t['t'] == '-': continue
        out.append(t)
    return out


def check_instructions(pdf):
    if not pdf:
        return report(6, 'Performer instructions', 'NOT RUN', 'needs --pdf')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'find_performer_instructions.py'), pdf], capture_output=True, text=True)
    hits = [l.strip() for l in r.stdout.splitlines()[1:] if l.strip().startswith('p')]
    if not hits:
        return report(6, 'Performer instructions', 'PASS', 'none found (italic scan); rerun find_performer_instructions.py --all-text if the engraving sets them upright')
    report(6, 'Performer instructions', 'MANUAL', f'{len(hits)} found: each needs a rule and a stated scope', hits)


def check_extender_lines(root, names, E, lanes):
    """10: every printed extension line is consumed by exactly one syllable, and every <extend/>
    on a syllable the PDF prints for that part has a printed line behind it.

    A line that runs to the right margin carries on at the start of the next system. Where that
    leading segment is drawn vertically varies by engraver (Finale puts it just above the staff
    whichever lyric line it continues), so leading segments are paired with the lines that ran
    off the previous system by count and vertical order, not by lane."""
    rows = E.lyric_rows()
    unknown = sorted({r[2] for r in rows if r[2] not in lanes})
    size = E.lyric_size
    printed = defaultdict(list)       # part name -> [[text, has_line, where]]
    consumed = set()
    runs = defaultdict(list)          # (page, system) -> [(y, entry, needs_continuation)]
    for pi, si, lane, top, syls in rows:
        if lane not in lanes: continue
        page = E.pages[pi]; sp = page['sp']
        right = page['systems'][si][0]['x1']
        for k, s in enumerate(syls):
            band = [ln for ln in page['hlines'] if s['top'] + 0.35 * size <= ln[2] <= s['top'] + 1.5 * size and ln[1] - ln[0] > 2.25 * sp]
            hit = [ln for ln in band if s['x1'] - 1 <= ln[0] <= s['x1'] + 2.5 * sp]
            for ln in hit: consumed.add((pi, tuple(ln)))
            entry = [s['t'], bool(hit), f"p{page['n']} system {si + 1}"]
            printed[lanes[lane]].append(entry)
            if any(ln[1] > right - 3 for ln in hit):
                runs[(pi, si)].append((s['top'], entry, False))
            elif not hit and k == len(syls) - 1 and s['x1'] > right - 12 * sp:
                runs[(pi, si)].append((s['top'], entry, True))    # its whole line may be on the next system
    bad = []
    for pi, page in enumerate(E.pages):
        sp = page['sp']
        tops = sorted({x['top'] for r in rows if r[0] == pi for x in r[4]})
        for si, sy in enumerate(page['systems']):
            left = sy[0]['x0']
            lead = sorted((ln for ln in page['hlines'] if ln[1] - ln[0] > 2.25 * sp and ln[0] < left + 15 * sp
                           and E.home(page, ln[2])[0] == si and (pi, tuple(ln)) not in consumed), key=lambda ln: ln[2])
            prev = [k for k in runs if next_system(E, *k) == (pi, si)]
            ran = sorted(runs[prev[0]], key=lambda r: r[0]) if prev else []
            must = [r for r in ran if not r[2]]
            maybe = [r for r in ran if r[2]]
            if len(lead) < len(must):
                pass                                  # a line may end exactly at the margin
            extra = len(lead) - len(must)
            for r in maybe[:max(extra, 0)]:
                r[1][1] = True                        # its line is the leading segment here
            for ln in lead[:len(must) + len(maybe)]:
                consumed.add((pi, tuple(ln)))
        for ln in page['hlines']:
            if ln[1] - ln[0] <= 2.25 * sp or (pi, tuple(ln)) in consumed: continue
            si, lane = E.home(page, ln[2])
            in_band = any(t + 0.35 * size <= ln[2] <= t + 1.5 * size for t in tops)
            at_left = si is not None and lane is not None and ln[0] < page['systems'][si][0]['x0'] + 15 * sp
            if in_band or at_left:
                bad.append(f"p{page['n']}: printed line x{ln[0]:.0f}-{ln[1]:.0f} y{ln[2]:.0f} belongs to no syllable")
    # compare with the MusicXML, part by part, by aligning the syllable texts
    matched = skipped = 0
    for part in root.findall('part'):
        nm = names[part.get('id')]
        if nm not in printed: continue
        xs = []
        for mn, n, v, _ in notes_of(part):
            for l in n.findall('lyric'):
                e = l.find('extend')
                slurred = any(x.get('type') == 'start' for x in n.iter('slur'))
                xs.append((l.findtext('text') or '', e is not None and e.get('type') != 'stop', mn, slurred))
        ps = printed[nm]
        sm = difflib.SequenceMatcher(a=[t.strip() for t, _, _ in ps], b=[x[0].strip() for x in xs], autojunk=False)
        blocks = sm.get_matching_blocks()
        for a0, b0, n in blocks:
            for k in range(n):
                t, has, where = ps[a0 + k]
                xt, ext, mn, slurred = xs[b0 + k]
                matched += 1
                if ext and not has and slurred:
                    continue          # a slurred melisma keeps its line even where none is printed (SKILL.md 2.5)
                if has != ext:
                    bad.append(f"{nm} bar {mn} {xt!r}: PDF {'prints' if has else 'has no'} extension line, "
                               f"file {'has' if ext else 'has no'} <extend/>")
        skipped += len(xs) - sum(b[2] for b in blocks)
        lost = len(ps) - sum(b[2] for b in blocks)
        if lost:
            bad.append(f"{nm}: {lost} printed syllable(s) could not be matched to the file's lyrics - a missing or misspelt syllable?")
    if unknown:
        bad.append(f"lyric lines in lanes {unknown} have no part: add them to --lanes")
    summary = (f'{matched} printed syllables compared, {len(bad)} disagreement(s)'
               + (f'; {skipped} syllable(s) in the file are not printed for that part (copied from another line), not compared' if skipped else ''))
    report(10, 'Extension lines match the PDF', 'FAIL' if bad else 'PASS', summary, bad)


def next_system(E, pi, si):
    if si + 1 < len(E.pages[pi]['systems']): return pi, si + 1
    for q in range(pi + 1, len(E.pages)):
        if E.pages[q]['systems']: return q, 0
    return None


HEADS = {0xF0CF, 0xF0FA, 0xF077, 0x153, 0x2D9, 0xE0A2, 0xE0A3, 0xE0A4}


def check_grid(E):
    """12: every notehead sits a whole number of half staff spaces from its staff's top line."""
    offs = []
    for page in E.pages:
        sp = page['sp']
        st = [s for sy in page['systems'] for s in sy]
        for c in page['chars']:
            if not any(f in c['font'] for f in MUSIC_FONTS): continue
            code = ord(c['t'][0])
            if code not in HEADS and not (c['t'] == 'w' and 'Helsinki' in c['font']): continue
            s = min(st, key=lambda s: abs((s['lines'][0] + s['lines'][4]) / 2 - c['y']))
            d = (c['y'] - s['lines'][0]) / (sp / 2)
            offs.append((d, page['n'], c['x0']))
    if not offs:
        return report(12, 'Noteheads on the grid', 'NOT RUN', 'no noteheads recognised (music font not in the list)')
    base = statistics.median([d - round(d) for d, _, _ in offs])      # font baseline offset, if any
    bad = [f'p{pn} x{x:.0f}: {d - base:.2f} half-spaces' for d, pn, x in offs if abs((d - base) - round(d - base)) > 0.15]
    report(12, 'Noteheads on the grid', 'FAIL' if bad else 'PASS',
           f'{len(offs)} noteheads, {len(bad)} off the grid' + (f' (font offset {base:+.2f})' if abs(base) > 0.05 else ''), bad[:20])


def check_onsets(root, E):
    """11: notes that start together in the file start at one x in the PDF.
    Compares, bar by bar, the number of distinct onsets across all parts with the number of
    distinct note/rest columns the engraving prints."""
    from collections import Counter
    ons = defaultdict(set)
    for part in root.findall('part'):
        for mn, n, v, t in notes_of(part):
            r = n.find('rest')
            if r is not None and r.get('measure') == 'yes': continue
            if n.findtext('type') is None and r is not None: continue
            ons[mn].add(t)
    order = [m.get('number') for m in root.find('part').findall('measure')]
    cols = []
    for page in E.pages:
        sp = page['sp']
        for sy in page['systems']:
            top, bot = sy[0]['lines'][0], sy[-1]['lines'][4]
            cover = defaultdict(set)
            for x, t, b in page['vlines']:
                for k, s in enumerate(sy):
                    if t <= s['lines'][0] + 0.6 and b >= s['lines'][4] - 0.6: cover[round(x)].add(k)
            bars = []
            for x in sorted(x for x, ks in cover.items() if len(ks) == len(sy)):
                if bars and x - bars[-1] < 4: bars[-1] = x; continue
                bars.append(x)
            glyphs = sorted(c['x0'] for c in page['chars'] if any(f in c['font'] for f in MUSIC_FONTS)
                            and top - 6 * sp < c['y'] < bot + 6 * sp
                            and (ord(c['t'][0]) in HEADS | {0xF0E4, 0xF0CE, 0xF0EE, 0xF0C5, 0x2030, 0x152, 0xD3}
                                 or (c['t'] == 'w' and 'Helsinki' in c['font'])))
            for a, b in zip(bars, bars[1:]):
                g = [x for x in glyphs if a + 1 < x < b - 1]
                c = []
                for x in g:
                    if c and x - c[-1][0] < 1.9 * sp: c[-1].append(x)   # a second prints its heads one head-width apart
                    else: c.append([x])
                cols.append(len(c))
    if len(cols) != len(order):
        return report(11, 'Cross-staff onset alignment', 'NOT RUN',
                      f'PDF bar count {len(cols)} does not match the file ({len(order)}); first-bar or pickup layout not understood')
    bad = [f'bar {mn}: {len(ons[mn])} onset(s) in the file, {c} column(s) in the PDF'
           for mn, c in zip(order, cols) if c and len(ons[mn]) != c]
    report(11, 'Cross-staff onset alignment', 'WARN' if bad else 'PASS',
           f'{len(bad)} bar(s) where the file and the engraving disagree on how many attack points there are' if bad
           else 'every bar has as many attack points as the engraving has columns', bad)


# ----------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('score')
    ap.add_argument('--pdf')
    ap.add_argument('--lanes', help='"0a=Tenor,0b=Lead,1a=Baritone,1b=Bass"')
    ap.add_argument('--original')
    ap.add_argument('--render')
    ap.add_argument('--xsd')
    ap.add_argument('--lyric-font'); ap.add_argument('--lyric-size', type=float)
    a = ap.parse_args()
    root, names = load(a.score)
    out_dir = os.path.dirname(os.path.abspath(a.score))

    check_xsd(a.score, a.xsd)
    check_bars(root, names)
    check_ranges(root, names)
    check_qc(a.score)
    check_render(a.score, a.render)
    check_instructions(a.pdf)
    report(7, 'Judgment calls handed back', 'MANUAL', 'list every divisi bar, duplicated lyric, literal-rest reading and fixed typo in the handback')
    check_ties(root, names)
    check_words(root, names, out_dir)
    if a.pdf:
        try:
            E = Engraving(a.pdf, a.lyric_font, a.lyric_size)
        except Exception as ex:
            E = None
            for n, nm in ((10, 'Extension lines match the PDF'), (11, 'Cross-staff onset alignment'), (12, 'Noteheads on the grid')):
                report(n, nm, 'NOT RUN', f'could not read the PDF: {ex}')
        if E:
            if a.lanes:
                lanes = dict(kv.split('=', 1) for kv in a.lanes.split(','))
            else:
                per_sys = {len(sy) for p in E.pages for sy in p['systems']}
                pn = [names[p.get('id')] for p in root.findall('part')]
                lanes = {f'{k}b': pn[k] for k in range(len(pn))} if per_sys == {len(pn)} else None
            if lanes:
                missing = [v for v in lanes.values() if v not in names.values()]
                if missing:
                    report(10, 'Extension lines match the PDF', 'NOT RUN', f'--lanes names parts the file does not have: {missing}')
                else:
                    check_extender_lines(root, names, E, lanes)
            else:
                report(10, 'Extension lines match the PDF', 'NOT RUN',
                       'the PDF has fewer staves than the file has parts (a closed score): pass --lanes')
            check_onsets(root, E)
            check_grid(E)
    else:
        for n, nm in ((10, 'Extension lines match the PDF'), (11, 'Cross-staff onset alignment'), (12, 'Noteheads on the grid')):
            report(n, nm, 'NOT RUN', 'needs --pdf')
    check_shared_staff(root)
    check_extend_runs(root, names)
    check_layout(a.score, root)
    check_original(root, names, a.original)

    results.sort()
    w = max(len(r[1]) for r in results)
    print(f'Step 5 checks for {os.path.basename(a.score)}' + (f' against {os.path.basename(a.pdf)}' if a.pdf else ''))
    for n, name, status, summary in results:
        print(f'{n:>3}  {name:<{w}}  {status:<8} {summary}')
    for n, name, status, summary in results:
        if details[n] and status in ('FAIL', 'WARN', 'MANUAL'):
            print(f'\n{n}. {name}')
            for l in details[n][:40]: print(f'    {l}')
            if len(details[n]) > 40: print(f'    ... and {len(details[n]) - 40} more')
    sys.exit(1 if any(r[2] == 'FAIL' for r in results) else 0)


if __name__ == '__main__':
    main()
```

### rehearsal_mix.py

```python
#!/usr/bin/env python3
"""Mix a full set of rehearsal tracks from per-staff stems (SKILL.md Step 9.4).

    python3 rehearsal_mix.py TITLE OUT_DIR "Bass=bass.wav" "Baritone=bari.wav" "Tenor 2=t2.wav" "Tenor 1=t1.wav"
                             [--accomp "Piano=piano.wav"] [--trim "Bass=-9"] [--place "Solo=0"]
                             [--only 3d] [--featured 3] [--others -21]

List the voices from the LOWEST to the HIGHEST: the order sets the stereo and 3D
layouts. An accompaniment stem (--accomp, repeatable) is never featured and stays
at 0 dB.

Writes, for every voice V (parentheses around the section name, for Chorus
Connection; a voice named Solo... gets none):
    TITLE - (V) predominant.mp3         V +3 dB, other voices -21 dB, accompaniment 0 dB
    TITLE - (V) part-left.mp3           V hard left, other voices hard right, accompaniment as exported
and once:
    TITLE - Balanced.mp3                everything at 0 dB, as exported (no panning)
    TITLE - Balanced panned.mp3         voices spread across the stereo field, lowest on the left
    TITLE - Balanced 3D, use headphones.mp3
                                        voices placed around the listener with a dummy-head HRTF

Layouts, the ones the user settled on by ear for a TTBB set (Bass, Baritone, Tenor 2, Tenor 1):
  panned  lowest to highest evenly from 45% left to 45% right (four voices: -45, -15, +15, +45),
          constant-power pan scaled so a centred voice keeps its level; accompaniment centred.
  3D      listener facing north; lowest voice rear-left (135 deg), highest rear-right (225 deg),
          the rest evenly across the front between 10 deg left and 10 deg right (four voices:
          Bass 135, Baritone 10 left, Tenor 2 10 right, Tenor 1 225); accompaniment straight
          ahead (0 deg). Ear height. MIT KEMAR dummy head, measured at 1.4 m, from the `slab`
          package (pip install slab). Loudness matched to the panned Balanced track.

Soloists: the layouts are for the choral parts. Put a solo where it belongs with --place
("Solo=0" straight ahead; "Solo 1=5R", "Solo 2=5L"); the choral parts keep the standard
layout, and in the panned track a placed voice sits proportionally (135 deg = 45%).
Chosen for a TTBB piece with one solo (Solo ahead) and one with two soloists (Solo 2 5 deg left,
Solo 1 5 deg right), without listening; the user may move them.

Stem levels: every stem's median level while sounding is printed. A stem several dB off
the others (one set's Bass came out 9 dB hot) gets --trim, applied before every mix gain.

Peaks: every mix is measured before encoding. Only if one goes over 0 dBFS are ALL of them
turned down by the same amount (the loudest lands at -1 dBFS), so the tracks keep their
loudness relative to one another. The 3D track, a headphone extra, is loudness-matched to
the panned Balanced track and then turned down on its own if it would clip.

Needs numpy and ffmpeg (with libmp3lame); slab for the 3D track (without it the 3D track is
not made, the script says so and exits 1).
"""
import sys, os, types, argparse, subprocess
import numpy as np

SR = 44100


def load(path):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ar', str(SR), '-ac', '2', '-f', 'f64le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float64).reshape(-1, 2).copy()


def sounding_level(x):
    m = x.mean(1); w = SR // 10; n = len(m) // w
    r = 20 * np.log10(np.sqrt((m[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-12)
    s = r[r > -45]
    return float(np.median(s)) if len(s) else float('-inf'), len(s) / 10


def pad(x, n):
    return np.vstack([x, np.zeros((n - len(x), 2))]) if len(x) < n else x[:n]


def db(g):
    return 10 ** (g / 20)


def mono(x):
    return x.mean(1)


def pan_positions(k):
    return [0.0] if k == 1 else list(np.linspace(-0.45, 0.45, k))


def azimuths(k):
    """degrees counterclockwise from straight ahead (90 = left), lowest voice first"""
    if k == 1: return [0.0]
    if k == 2: return [135.0, 225.0]
    front = [0.0] if k == 3 else list(np.linspace(10, -10, k - 2))
    return [135.0] + [a % 360 for a in front] + [225.0]


def hrir_bank():
    sys.modules.setdefault('sounddevice', types.ModuleType('sounddevice'))   # slab imports it; playback unused
    import slab
    h = slab.HRTF.kemar()
    src = np.asarray(h.sources.vertical_polar, float)

    def left_side(az):                       # 0..180, measured every 5 deg at ear height
        near = sorted(range(len(src)), key=lambda i: abs(src[i, 0] - az) + 1000 * abs(src[i, 1]))[:2]
        a, b = near
        if abs(src[a, 0] - az) < 0.01: return np.asarray(h.data[a].data, float)
        wa = abs(src[b, 0] - az) / abs(src[b, 0] - src[a, 0])       # blend the two measured neighbours
        return wa * np.asarray(h.data[a].data, float) + (1 - wa) * np.asarray(h.data[b].data, float)

    def hrir(az):
        az = az % 360
        if az <= 180: return left_side(az)
        return left_side(360 - az)[:, ::-1]  # the set is left/right symmetric: mirror the left side
    return hrir


def parse_az(txt):
    """'0', '5L', '10R', '135L' -> degrees counterclockwise from ahead (90 = left)"""
    t = txt.strip().upper()
    if t in ('0', 'AHEAD', 'C'): return 0.0
    if t[-1] in 'LR': return float(t[:-1]) % 360 if t[-1] == 'L' else (-float(t[:-1])) % 360
    return float(t) % 360


def fftconv(x, h):
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('title'); ap.add_argument('out')
    ap.add_argument('voices', nargs='+', help='"Name=stem.wav", lowest voice first')
    ap.add_argument('--accomp', action='append', default=[])
    ap.add_argument('--trim', action='append', default=[], help='"Name=-9": dB applied to that stem first')
    ap.add_argument('--place', action='append', default=[],
                    help='"Solo=0", "Solo 1=5R", "Solo 2=5L": put a voice (or accompaniment) at a fixed '
                         'direction instead of the automatic layout; the other voices keep theirs')
    ap.add_argument('--only', choices=['all', '3d'], default='all', help='write every track, or only the 3D one')
    ap.add_argument('--featured', type=float, default=3.0)
    ap.add_argument('--others', type=float, default=-21.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    trims = {k: float(v) for k, v in (t.split('=', 1) for t in a.trim)}
    placed = {k: parse_az(v) for k, v in (t.split('=', 1) for t in a.place)}
    V = [tuple(s.split('=', 1)) for s in a.voices]
    A = [tuple(s.split('=', 1)) for s in a.accomp]
    for n in list(trims) + list(placed):
        if n not in {x for x, _ in V + A}: sys.exit(f'{n!r} is not a stem')
    st = {n: load(p).astype(np.float32) for n, p in V + A}
    N = max(len(x) for x in st.values())
    st = {n: (pad(x, N) * db(trims.get(n, 0.0))).astype(np.float32) for n, x in st.items()}
    names = [n for n, _ in V]; acc = [n for n, _ in A]

    print('stem levels while sounding (after --trim):')
    lv = {n: sounding_level(st[n]) for n in names + acc}
    ref = np.median([lv[n][0] for n in names])
    for n in names + acc:
        l, secs = lv[n]
        flag = f'   <- {l - ref:+.1f} dB from the other voices: consider --trim "{n}={-(l - ref):.0f}"' \
            if n in names and abs(l - ref) >= 4 else ''
        print(f'   {n:12s} {l:6.1f} dBFS over {secs:5.1f} s{flag}')

    # layouts: placed voices where they were put; the rest spread as usual, lowest first
    auto = [n for n in names if n not in placed]
    az = dict(zip(auto, azimuths(len(auto)))); az.update({n: placed.get(n, 0.0) for n in acc}); az.update(placed)
    signed = lambda d: d if d <= 180 else d - 360                    # + left, - right
    pan = dict(zip(auto, pan_positions(len(auto))))
    pan.update({n: float(np.clip(-signed(placed[n]) / 135 * 0.45, -0.45, 0.45)) for n in placed})
    pan.update({n: pan.get(n, 0.0) if n in placed else 0.0 for n in acc})
    side = lambda d: 'ahead' if d == 0 else (f'{d:g} deg left' if d <= 180 else f'{360 - d:g} deg right')
    print('\npanned: ' + ', '.join(f'{n} ' + ('centre' if abs(pan[n]) < 1e-9 else
                                   f'{round(abs(pan[n])*100, 1):g}% {"left" if pan[n] < 0 else "right"}') for n in names + acc))
    print('3D: ' + ', '.join(f'{n} {side(az[n])}' for n in names + acc))

    label = lambda n: n if n.lower().startswith('solo') else f'({n})'
    accsum = sum((st[n] for n in acc), np.zeros((N, 2), np.float32))
    mono_ = {n: mono(st[n]) for n in names + acc}

    def predominant(v):
        return accsum + sum(st[n] * np.float32(db(a.featured if n == v else a.others)) for n in names)

    def part_left(v):
        R = sum((mono_[n] for n in names if n != v), np.zeros(N, np.float32))
        return accsum + np.stack([mono_[v], R], 1)

    def balanced():
        return accsum + sum(st[n] for n in names)

    def panned():
        out = np.zeros((N, 2), np.float32)
        for n in names + acc:
            if n in acc and n not in placed:
                out += st[n]; continue                                  # accompaniment as exported
            th = (pan[n] + 1) * np.pi / 4
            out += np.outer(mono_[n], np.float32([np.sqrt(2) * np.cos(th), np.sqrt(2) * np.sin(th)]))
        return out

    missing3d = None
    try:
        hrir = hrir_bank()
    except Exception as ex:
        missing3d = f'{ex.__class__.__name__}: {ex}'
    rms = lambda x: float(np.sqrt((x.astype(np.float64) ** 2).mean()))
    pan_rms = rms(panned())

    def three_d():
        out = np.zeros((N, 2))
        for n in names + acc:
            f = hrir(az[n])
            for ch in (0, 1):
                out[:, ch] += fftconv(mono_[n].astype(np.float64), f[:, ch])[:N]
        return (out * (pan_rms / rms(out))).astype(np.float32)

    builders = {}
    for v in names:
        builders[f'{a.title} - {label(v)} predominant'] = (lambda v=v: predominant(v))
        builders[f'{a.title} - {label(v)} part-left'] = (lambda v=v: part_left(v))
    builders[f'{a.title} - Balanced'] = balanced
    builders[f'{a.title} - Balanced panned'] = panned
    three = f'{a.title} - Balanced 3D, use headphones'
    if missing3d is None:
        builders[three] = three_d

    # Peaks. The tracks singers switch between keep their loudness relative to one another: only if
    # one of them goes over 0 dBFS are all of them turned down, by the same amount. The 3D track is
    # a headphone extra: loudness-matched to the panned Balanced track, then turned down on its
    # own if it would clip (one set: +1.1 dBFS, taken to -1). Two passes: measure every mix, then
    # write, building one mix at a time so long pieces fit in memory.
    peaks = {k: 20 * np.log10(float(np.abs(f()).max()) + 1e-12) for k, f in builders.items()}
    worst = max(v for k, v in peaks.items() if k != three)
    gains = {k: (-(worst + 1.0) if worst > 0 else 0.0) for k in builders}
    if three in builders and peaks[three] + gains[three] > 0:
        gains[three] = -(peaks[three] + 1.0)
    write = [k for k in builders if a.only == 'all' or k == three]
    print('\npeaks before encoding, and the gain applied:')
    for k in builders:
        print(f'   {peaks[k]:+6.2f} dBFS  {gains[k]:+5.2f} dB  {k}' + ('' if k in write else '   (not written: --only 3d)'))
    for k in write:
        y = (builders[k]() * np.float32(db(gains[k]))).astype(np.float32)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-',
                        '-c:a', 'libmp3lame', '-b:a', '192k', '-joint_stereo', '1', os.path.join(a.out, k + '.mp3')],
                       input=y.tobytes(), check=True)
    print(f'\n{len(write)} track(s) written to {a.out}')
    if missing3d:
        print(f'3D track NOT made: the HRTF set could not be loaded ({missing3d}); pip install slab')
        sys.exit(1)


if __name__ == '__main__':
    main()
```

## Appendix — Sibelius "Opus" font glyph codes

Empirically determined. **Other engravers use other fonts** (Finale = Maestro,
Dorico/modern = Bravura, MuseScore = Emmentaler/Leland) with entirely different
code points. Re-derive by cropping one instance of each unseen code and looking
at it — that takes about five minutes and is the fastest part of the job.

| Code | Font | Meaning |
|---|---|---|
| `0xf0cf` | Opus | filled notehead |
| `0xf0fa` | Opus | half notehead |
| `0xf077` | Opus | whole notehead |
| `0xf0aa` | OpusSpecial | augmentation dot |
| `0xf0e4` | Opus | eighth rest |
| `0xf0ce` | Opus | quarter rest |
| `0xf0c5` | Opus | 16th rest |
| `0xf0ee` | Opus | half rest |
| `0xf0b7` | Opus | whole / whole-measure rest |
| `0xf062` | Opus | flat |
| `0xf023` | Opus | sharp |
| `0xf06e` | Opus | natural |
| `0xf026` | Opus | treble clef |
| `0xf03f` | Opus | bass clef |
| `0xf0dc` | OpusSpecial | the "8" under a treble-8vb clef |
| `0xf032` / `0xf034` | Opus | time-signature digits 2 / 4 |
| `0xf06a` / `0xf04a` | Opus | eighth flag up / down |
| `0xf072` / `0xf052` | Opus | 16th flag up / down |
| `0xf055` | Opus | fermata |
| `0xf03e` | Opus | accent |
| `0xf02c` | Opus | breath mark |
| `"3"` | OpusText | triplet bracket number |

**Helsinki** (Sibelius's other house font) uses the same code points, but
pdfplumber hands them back through the Mac Roman table, so they arrive as
ordinary Unicode: filled notehead `U+0153 œ` (= 0xCF), half notehead `U+02D9`
(0xFA), whole `w`, X-notehead `U+00BF ¿` (0xC0), quarter rest `U+0152 Œ`
(0xCE), eighth rest `U+2030 ‰` (0xE4), half rest `U+00D3 Ó` (0xEE), whole rest
`U+2211 ∑` (0xB7), augmentation dot `U+2122 ™` in HelsinkiSpecial (0xAA),
flags `j`/`J`/`r`, fermata `U`, accent `>`, marcato `^`, staccato `.`, treble
clef `&`, bass clef `?`, the 8 under a treble-8vb clef `U+2039 ‹` in
HelsinkiSpecial (0xDC), dynamics and tuplet digits in HelsinkiTextStd. Glyph
*baselines* (`matrix[5]`), not char-box centres, sit exactly on the staff
position — the key-signature accidentals landed on their lines with zero
correction, so no baseline offset was needed for this font.

In this file slanted beams were 5-point filled curves, flat beams were rects
0.5 SP high, ties/slurs were the 2-operator stroked curve of a pair (the
4-operator filled twin is the same arc), stems were vertical lines of one
line-width and barlines of another, and lyric extension lines had their own
line-width — three widths, three object classes, no ambiguity.

Derived measurements, in staff spaces (SP = distance between adjacent staff lines):

| Quantity | Value |
|---|---|
| notehead width | 1.28 · SP |
| beam thickness | 0.5 · SP |
| OpusSpecial baseline offset vs Opus | 0.85 · SP lower |
| dot x-offset from notehead | 1.6 – 2.0 · SP |

**Verovio's own output**, when you render: notated accidentals are paths, but
chord-symbol accidentals are `<text font-family="Leipzig">` at private-use code
points — sharp `U+EA66`. See 8.4.

## Credits

Pieces are described, not named (see *No song titles in this repository*).

The Cantai section, the extension-line-as-source rule, the shared-hyphen rule,
the Helsinki appendix, the clap-part encoding and checks 8–11 come from
the two-soloist TTBB (TTBB + two tenor soloists + piano, with a clapped
passage), a 2021 Sibelius/Helsinki export, done for a community chorus's
learning tracks.

The OMR-as-donor rule, the bar-remap warning, the cue-placement rule (3.2), the
whole of Steps 7 and 8, checks 13–16, the vocable respelling and
`lyric_collisions.py` come from the scanned SATB octavo (SATB + piano), a hand scan, taken through OMR repair, a director's TTBB
revoicing, collapsing to two staves, and print layout.

The page-global stem-and-beam rule (2.2, 2.3), the stem-keyed chord grouping
(2.3, 3.1) and the notehead-grid check (check 12) come from the 12/8 TTBB (TTBB + piano, six staves per system), a
MuseScore/Leland vector PDF.

The credit rules (8.6) and the probe-instead-of-tune habit come from putting
an arranger's and an adapter's names on that same scanned SATB octavo. The
crossed-parts rules (7.6), the tie-stays-in-its-voice rule (7.4) and the
barline rule (8.5) come from proofreading its TTBB print layout in Sibelius.

Step 9 comes from exporting Cantai stems and mixing rehearsal tracks for
the solo-and-TTBB piece (TTBB + Solo + piano), handed over from another
session; its ffmpeg checks and mix command were re-run on synthetic stems
before being written here. The Balanced track, the above-full-scale peak
measurement, the −21 dB default and the entrance-pattern note come from mixing
the set for the 2008 Sibelius TTBB. The part-left
tracks come from the set for the scanned SATB octavo; `stem_vs_score.py` was
tested on its stems. The stop-for-good dropouts come from exports of the
two-soloist TTBB and the solo-and-TTBB piece.

The panned and 3D Balanced tracks, `rehearsal_mix.py`, the anchored line-up in
`stem_vs_score.py` and the check-what-landed rule (9.4) come from mixing the
unaccompanied TTBB's set, where the front pair of the 3D layout went from 45°
to 22.5° to 10° by ear.

`verify.py`, the page-over-notes rules for extension lines (2.5) and the
Finale ledger-line note come from the unaccompanied TTBB (a TTBB closed score,
a Finale/Maestro vector PDF bought as a download), where the extension lines
were derived from the notes, check 10 was never run, and the
user caught the result by eye.

The voice-explosion requirements (one part per voice, no chords, `<extend/>`
melismas, the `<note>` element order that Sibelius enforces, and the
XSD/music21/Verovio verification stack) come from a prior handoff by another
agent working on the solo-and-TTBB piece. The vector-extraction method,
the OMR failure catalogue and the two scripts come from repairing the 2008
Sibelius TTBB.