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

**Make rehearsal tracks.** First wait for Cantai to finish rendering: an
export writes only what Cantai has rendered so far, and silence for the rest.
In the Mixer (Play > Mixer, or M), click the gear on each Cantai voice's
strip; the singer's picture on that panel has a spinning halo until that voice
is rendered. When every halo has stopped, export one audio file per staff
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
Chorus Connection. Claude first shows the section each part's files will be
filed under, for you to click and change: Chorus Connection shows a file whose
section it does not recognise to everyone.

**Make follow-along videos.** Once the rehearsal tracks exist, write something
like:

```
Make follow-along videos for the Shenandoah folder.
```

If the MusicXML there is a Cantai learning file, include the print-faithful one
too (the closed score the singers hold is best) and say which is which; the
videos show the print file.
That is Step 10: one mp4 per mp3 used, the score lighting up note by note, rests
included, in each part's colour.

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
the finished score into rehearsal tracks, and Step 10 turns those into follow-along
score videos. Never mix the
Cantai file with the rest — deliver the faithful file always, and the Cantai file
in addition when asked for learning tracks.

**This file is self-contained.** The nine scripts it refers to are printed in
full under *Scripts* near the end. Write them out to disk verbatim before you
start — `check_pdf_type.py`, `find_performer_instructions.py`, `musicxml_qc.py`,
`cantai_mode.py`, `lyric_collisions.py`, `stem_vs_score.py`, `verify.py`,
`rehearsal_mix.py`, `score_video.py`. There are no other files to obtain.

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

The length filter is not optional. Ledger lines are short (about 10 pt), but where
chords climb or drop far off the staff they stack at exactly the staff-line spacing, so a
run of five of them looks like a staff to a finder that doesn't check length. On a Finale
TTBB with piano, a finder written fresh for the piece, which counted any horizontal
segment, locked onto a stack of ledger lines instead of a real line in two piano
systems. Every note in them came out one staff line off. Check 12 still passed, because
the shifted positions were still whole half-spaces. Use `staves_of()` from `verify.py`
instead of writing a new one; check 17 (Step 5) is what caught this.

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
- **A syllable in the middle of a word held only by a tie gets no extender.**
  `long-` held over a tie into `-in'` prints a hyphen, and an `<extend/>` on
  `long` makes Sibelius draw a line where the hyphen should be. The note model
  says "held, so extend"; the page says "hyphen". The page wins.
- **Held over a melisma of moving notes, it does get one, even where the page
  prints only a hyphen.** `be-` sung on a slurred pair of eighths before
  `-gins`, with a hyphen and no line under the second eighth: the hyphen there
  is standing in for an extender, and a singer needs the line to see that the
  syllable is held. This is a deliberate disagreement with the engraving, so
  say in the handback where you made it. `chorale.events.finalize` does both;
  checks 10 and 14 accept the line.
- **Sibelius draws a hyphen after a first or middle syllable even when it
  carries `<extend/>`**; it draws the line only after a syllable that ends a
  word. So in the print and display files, end the word at the held syllable
  and start the rest afresh (`begin` becomes `single`, the next `end` becomes
  `single`): `mu ______ sic`, confirmed in Sibelius on a TTBB with piano.
  `chorale.musicxml.break_words_at_melismas` does it on the finished file. Make
  the Cantai copy from the file before that step: Cantai reads the hyphens to
  pronounce the word.

Where a line runs off the right margin, the leading segment on the next system
is not always drawn at the height of its own lyric line: Finale puts it just
above the staff whichever lyric line it continues. Pair leading segments with
the lines that ran off the previous system by system and count, not by
height.

### 2.6 Tempo: the arranger's words, and measuring a recording

A score with no metronome marks still has tempo in it. Words like "Bright Broadway 2",
"Tempo de Bubbles", "MAESTOSO", "BROADLY", "STRINGENDO" and "SUDDENLY SLOW DOWN!" are
the arranger's tempo marks. List every one with its bar and propose a number for each,
or measure them from a recording, and put the result in as hidden tempi
(`<metronome print-object="no">` plus `<sound tempo>`, in the first part only). Words
that are not tempo: "ACAPELLA" is scoring, and a title engraved close to the first
staff is not a mark.

To measure a recording (chroma of the score laid out on the tempo map, dynamic time
warping against the audio's chroma, then onsets to fix bar starts):

- **Trim the audio to the music before aligning.** Plain DTW pins the last score frame
  to the last audio frame. A concert recording goes on past the final chord (a piano
  fill, applause, room tone): about 20 s on one YouTube rip. The alignment has to put
  that time somewhere, and it puts it wherever stretching the score costs least. Find the
  end of the final chord from the loudness and spectral flatness curves (applause is
  flat and noisy), cut there, and check the cut by listening to or looking at the last
  few seconds.
- **Repetitive stretches are where it goes wrong.** In a vamp (the same two chords bar
  after bar, sustained "Ah!"s, a repeat), every bar has nearly the same chroma, so DTW
  can slide or stretch it at almost no cost. On the TTBB above, bars 161–173 came out as
  20 s against the real 12 s. Before aligning, ask the user for the start and end times
  of any vamp or repeated section, align each piece between those anchors separately,
  and place bars inside the vamp from onsets.
- **Align against a score you have checked.** A misread staff (2.1) gives wrong pitch
  classes, which pull the alignment off in exactly those bars. Run check 17 first.
- **Report the measurements as a table** of bar ranges, marking, and tempo with the note
  value spelled out ("half = 138"): the user could not read Unicode note glyphs. Say
  where the measurement differs from what the user hears (MAESTOSO measured 88 on one
  recording where the user heard about 100) and which value went into the file.

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
spelt out. Checks 10, 11, 12 and 17 read the PDF directly with the script's own
staff and barline finders, so they test the file against the engraving rather than
against your own extraction; they work on vector PDFs only.

Four things the checks got wrong on a Finale vector TTBB with piano, fixed in the script:
check 8 compared a tie on the upper note of a chord with the next chord's lowest note (a tie
on a chord member now needs the same pitch in the voice's next event); check 10 took an
extender between two staves for a ledger line because it sat on the upper staff's ledger
grid over a note of the lower staff (the notehead must now be on the same staff), and read
only the most common lyric size, missing two pages Finale had scaled a few percent; and
check 11 counted the courtesy key and time at a system's end as bars. Give `--lanes` every
lane the lyric lines land in: the tenor line between the staves came out as `0b` on one
system and `1a` on the rest.

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
   consistency. It reads the two parts of a shared staff separately, and lets
   a note with no syllable of its own sing the one the other part starts at
   that moment (the single shared line of 7.4).
5. **Render and compare to the PDF, page by page**, with Verovio + cairosvg.
   A render that looks wrong in a way your data doesn't explain means you have a
   pitch or octave bug, not a renderer bug.
6. **Every performer instruction found, and the scope you gave it.** If the list
   is empty, say you looked — an empty list and a list you never made look the
   same in the output.
7. **Hand back the judgment calls.** Every divisi bar, every place you duplicated
   lyrics, every literal-rest reading, every typo you fixed. The singer needs to
   know what you decided on their behalf.
8. **Ties and slurs pair up.** In every monophonic part, each tie start is followed by a
   same-pitch note carrying the stop; no tie runs into a rest. Sibelius plays an
   unpaired tie as a note held through whatever comes next. Every slur start is
   closed by the next stop of the same number in the same voice: on a shared staff
   a slur that starts in voice 2 and ends on a note merged into a voice-1 chord is
   closed by nothing, and is drawn on across the page to the next stop it finds
   (7.2).
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
    And the line must stop where its melisma does: the check walks each line to
    the next syllable on it and fails a line that crosses a printed rest or, given
    `--original`, runs under notes that sing words of their own (7.6). It also
    fails a line on a mid-word syllable held only by a tie (2.5).
15. **No lyric collisions in the layout you are going to print** —
    `lyric_collisions.py`, Step 8.
16. **A revoicing matches the original everywhere it was not asked to change.**
    Sample both scores on a 16th-note grid, per voice, and diff pitch and
    pitch-class; the only differences left should be the ones on the
    instruction list (7.5).
17. **The printed noteheads are the file's pitches.** For each bar and each staff, the
    set of staff positions of the heads printed in the PDF must equal the set the file's
    pitches would print at under the clef in force. When every head in a bar is off by the
    same amount, the check reports that shift: that is a misread staff (2.1) or a wrong
    clef octave. Tested on the Finale TTBB with piano: the delivered file differs only in
    one bar where grace notes had been left out, and a copy with the piano RH moved up one
    line in five bars fails in exactly those five bars. Check 12 passes on that copy. A
    FAIL here is either fixed or listed in the handback as a known omission (grace notes
    left out, an 8va the file writes at sounding pitch).

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

**A slur never changes voice.** The chord's one slur mark belongs to voice 1, so
a lower-part slur that starts in voice 2 (the parts split) and ends on a note
that merges into a chord (they agree again) is left open, and Verovio drew it
from bar 33 to bar 39 of a TTBB with piano; the reverse, a slur that starts on
a merged chord and ends where voice 2 has split off, leaves a stop with no start.
`collapse.merge_staff` keeps both ends of such a slur out of the chord, and
check 8 fails any slur that does not close in its own voice.

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

- **Sequences equal, each syllable starting at the same moment → one lyric
  line.** Drop the lower voice's copies entirely.
  This is the common case: both parts sing the same words, one takes a two-note
  melisma where the other has a plain quarter. The merge cannot chord them, so
  the lower voice gets written out as voice 2 — and its duplicate syllable, the
  same word on the same beat, plus an extender for the melisma, lands on a
  second lyric line beneath an otherwise-empty one. That is the stray
  `ing______` under a bar whose text is already complete. But keep the
  extender: where only the lower voice holds the syllable over more notes, the
  one line carries the lower voice's copy, extender and all, instead of the
  upper's. The user's call for a chorus of non-readers: the slur alone did not
  tell the basses to hold "no" over two notes while the baritones sang it on
  one. A line-2 extender still open when the words move to line 1 must be
  ended (7.6).
- **Sequences differ → two lines,** line 1 the upper voice and line 2 the lower
  voice, *for every bar of the divergent passage*, including bars where one of
  them is silent. So do the same words entering at different moments
  (staggered entrances on one word, a beat or two apart): a shared copy lines
  up with one entrance and not the other, so each voice gets its own under its
  own note.

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
  unless you are reproducing an original that sets words above the staff. When
  there is an original PDF, follow it (7.7): the singers will hold it, and the
  videos are there to get them used to reading it. Without one, mixed placement
  only makes line 1 jump above and below the staff from bar to bar.

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
  it. So does 7.4 dropping the lower voice's copies where both sing the same
  words: its notes there are syllable-less, and an open line-2 extender ran on
  under them into the next divided bar, six bars away. Put a syllable-less
  voice-2 note that follows an already-finished voice-2 line into voice 3; that was the only encoding that worked in a
  Sibelius probe. Do not write `<lyric><extend type="stop"/></lyric>` for
  Sibelius: it reads it as a new, empty syllable and every held word whose line
  ended that way lost its line. A `print-object="no"` syllable was printed
  anyway. The empty stop is fine for Verovio, and only for Verovio.

### 7.7 Words where the original prints them, and fermatas once

When the closed score is built from an original PDF, read from each system of
the scan where each part's words sit, and keep to it. On the TTBB with piano the
octavo prints the tenors' held vowel under the tenor staff, the baritone
melody on a second line under that (above the bass staff), the basses' held
vowel under the bass staff, Tenor 1's divisi words above the tenor staff, and in
most bars one line between the staves that both staves' parts read. `collapsed_part(..., lyric_place=f)` takes `f(role, bar, offset)`
returning `'above'`, `'below'`, or None for "printed on the other staff's line",
and writes it two ways:

- **The file for Sibelius keeps every part's words on its own staff**, with the
  print's above or below as `placement`, and None falling back to below. A
  syllable printed only on the other staff would leave these notes with none,
  and Sibelius would run the line before it on under them (7.6). Lines stay
  numbered by voice (1 upper, 2 lower), so check 14 holds. Whether Sibelius
  honours `placement="above"` on import has not been checked yet.
- **The display copy for the videos is laid out as printed**
  (`hide_unprinted=True`): a syllable sung but printed on the other staff is kept
  as `print-object="no"` (the video reads it from the printed copy with the same
  text at that moment, on the line facing its staff), and `f` returns
  `(side, number)` so that each printed row is one lyric number. Numbered by
  voice, a row that takes one bar's words from the upper voice's chords and the
  next bar's from the lower voice's notes was drawn as two rows. A chord both
  parts sing, whose words the print gives on two rows (Tenor 1 above, Tenor 2
  between the staves), carries the syllable twice; the video gives each row its
  own light (the MEI verse's `@type` names its line in the SVG), so Tenor 2a's
  video lights only the row between the staves, where a singer would read it. Then run
  `end_lines_for_verovio` on it: renumbered lines would otherwise run on under
  notes whose words have moved to another row, and Verovio (not Sibelius) stops
  a line at an empty `<extend type="stop"/>`. A cue the print sets on the lyric
  line after a syllable (an alternative vowel in brackets) goes into the
  syllable's text, not a direction, which Verovio puts on a row of its own.

Verovio ignores a MusicXML lyric's `placement`; `score_video.py` sets
`@place="above"` on the MEI verses (a chord's verses sit under the `<chord>`,
not its notes). Verovio also spaces a row's syllables apart only within one
layer, so where a row takes words from two voices the next bar's first syllable
printed over the last; the script moves such a syllable right until
it clears its neighbour, and drops an extender squeezed to a stub, which read as
a full stop after the word.

**Once the parts split within a bar, they stay split for that bar, except at a
unison.** Where both parts sing the same rhythm and word on two different pitches
after they have split, the print gives each part its own stem, the upper part's up
and the lower's down (the TTBB with piano at bars 13, 42 and 64). Merged into one
chord on one stem, the note read as one part's whichever way the stem went: down,
it looked like Tenor 2's alone, and a first fix that forced it up made it look like
Tenor 1's alone. `merge_staff` keeps such moments out of the chord; a unison still
merges into one note, stemmed by position, as the print's "unis." notes are.

**A fermata once per staff and beat.** Collapsed onto one staff, both voices'
fermatas stack one over the other, and a piano beat of two eighths got one over
each. Voice 2 gets a fermata only where no voice-1 event is sounding; the piano
gets one per beat. In a part's video a fermata is black where it sits on that
part's note or rest, or where that part holds its own fermata on the same staff
to the same moment (the basses' bar rest at bar 51, under the baritones' held
note), and grey otherwise.

## Step 8 — Laying out a part for print

### 8.1 Verovio and cairosvg, the parts that surprise you

- **`unit` is the staff-size knob**, not `scale`. With page dimensions given in
  1/10 mm, `unit = staff_height_mm / 4 * 10 / 2`. `scale` only zooms the output
  and changes nothing about how much music fits on a page.
- **Verovio prints only the accidentals the file writes.** It takes the pitch
  from `<alter>` and what to print from `<accidental>`, and works out nothing
  itself. Sibelius does work them out, so a file that leaves them to the reader
  imports right there and renders wrong in Verovio: a closed-score video showed
  B-flat for every chromatic B-natural, the file having no `<accidental>` at
  all. `score_video.py` writes the missing ones: per staff, both voices
  together, against the key and the bar so far, none on a note tied over the
  barline. A collapse can need one the open score did not, since two voices on
  one staff share the bar's accidentals (one natural in the ballad TTBB).
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

**Wait until Cantai has rendered everything, then export.** Cantai renders in
the background, from bar 1 onward, after the file is opened or its cache is
cleared (its guide: "Cantai automatically re-renders just the affected
segments", https://cantai.app/sibelius), and File > Export > Audio writes only
what is rendered at that moment. The rest of the stem is digital silence, with
no warning. Playing a passage renders it on the spot, which is why live
playback can sing a phrase the export lost. Tell the user to watch for it this
way: in the Mixer (Play > Mixer, or M) the gear on a Cantai voice's strip
opens that voice's Cantai panel, and the singer's picture on its first page
has a spinning halo while the voice is rendering. When one halo stops, open
every other Cantai voice's panel and check that its halo has stopped too. The
three dots at the panel's top right open a second page with the cache size,
which does not update live (leave the page and come back); a size that has
stopped growing is a second confirmation.

Measured on a TTBB with piano split into six Cantai voices, 3:39 long, all
exported with File > Export > Audio. The first set of stems, exported within
two minutes of saving the file, was missing whole runs of phrases in every
voice (Tenor 1 lost 89 s of 167 s sung), and the gaps shrank in export order,
since rendering went on between exports. Each gap started and ended on a
phrase's first syllable. After a cache clear: a Tenor 1 exported about 10 s later
sang only bars 1–3; a full-score export right after the clear held voices for
its first half-minute and was the piano stem alone, sample for sample, from
then on, and a Tenor 1 exported 25 s after that stopped at bar 22; so
exporting everything first does not fill the cache. Left alone after a clear,
with nothing played or exported, the cache grew at about 0.5 MB/s, stopped at
136.5 MB about 4.9 minutes later, and the Tenor 1 halo went out within the
same half-minute; the Tenor 1 exported then was complete, and so were all six
voices exported next. Cantai does not render the same performance twice: two
complete renders of bars 1–3 were different waveforms, so a stem cannot be
checked against a known-good copy, only against the score (9.2).

An earlier version of this file said every manual export tested came out
clean, and 9.2's "voice that stops for good" was put down to Cantai. Some of
those stops may have been exports taken before rendering finished; the
cure is the wait above, and the score check after it.

**Solo each staff and use File > Export > Audio.** Slow. Bob Zawalich's *Export Each Staff As Audio*
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

**A voice that stops for good.** First suspect an export taken before Cantai
had finished rendering (9.1): then the gaps start and end on phrase starts and
shrink from one export to the next. Cantai can also stop rendering a staff partway
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
- **An export before rendering finishes is silent wherever Cantai has not
  rendered yet** (9.1): whole runs of phrases missing, in every voice, with
  sung passages in between. Wait for every voice's halo to stop.
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

**Only a real section goes in the parentheses.** Chorus Connection shows a track
whose parenthesised name is not one of the chorus's sections to *everyone*: on
a TTBB with piano whose score split Tenor 2 and Bass into a and b parts,
`(Tenor 2a)` and `(Bass b)` went to the whole chorus, and the user renamed the
files on Chorus Connection by hand. A division of a section keeps the section in
the parentheses and puts the suffix after them: `Shenandoah - (Tenor 2) a
predominant.mp3`, `Shenandoah - (Bass) b part-left.mp3`. `rehearsal_mix.py` does
that by default for a part name ending in a lone lower-case letter, takes
`--section "Voice=Section|suffix"` for anything else (`"Bari=Baritone|"`,
`"Bass a=Bass 1|"`), and prints the mapping; `score_video.py` reads both forms.

Choruses name their sections differently, so **propose the names and let the
user click to change them before mixing.** Use a question card (AskUserQuestion),
one question per voice, up to four per card: the proposed file name
(`(Tenor 2) a`) as the first option, one plausible alternative (`(Bass 1)` for
a Bass a, say) as the second, and the card's own free-text answer for the
chorus's real name. Ask about every voice whose name is not obviously a
standard section; plain `Tenor 1`, `Baritone` can be listed in the message
as staying as they are. Pass the answers as `--section`.

**Check what landed, not what was sent.** On the unaccompanied TTBB a file written to the
user's computer, reported as written, turned out to hold the previous version
of the same filename: the 3D track the user was told had its front voices at
10° still had them at 22.5°. File sizes and checksums do not settle it (the
mp3s written to the user's computer that night each arrived about 5.8 KB larger
than they left, with the audio intact). After delivering, measure the
audio in the file on the user's computer — for a panned or 3D track, each
voice's left/right balance — and resend from a new source path if it is the old
one.

## Step 10 — Follow-along score videos

A **follow-along video** is the score on screen with each note, and its syllable,
lighting up in its part's colour while it sounds, over one of the rehearsal mp3s
(no new audio). The singers this is for are non-auditioned and many do not read
well; the video is there so that someone who loses their place can find it again
by colour, and someone who cannot count rests can watch them go by. "Make
follow-along videos" means one combined video and one per part:

```
python3 score_video.py "Shenandoah (Cantai learning version).musicxml" \
  "Shenandoah - Balanced.mp3" "Shenandoah - (Tenor 1) predominant.mp3" \
  "Shenandoah - (Tenor 2) predominant.mp3" "Shenandoah - (Baritone) predominant.mp3" \
  "Shenandoah - (Bass) predominant.mp3" --display "Shenandoah.musicxml"
```

The first file is the one the audio was rendered from: the timing comes from it.
Each mp3 gives an mp4 of the same name beside it. The Balanced mp3 gives the
combined video, every sung part in its own colour; a `(Part) predominant` (or
`part-left`, or `Solo …`) mp3 gives that part's video, only that part lit and
everyone else, piano included, in grey. Use the predominant tracks for the part
videos unless asked otherwise. Always test on short clips first
(`--clip 104,20`, `--stills 50,114`) and show them before rendering whole
songs; a whole song is several minutes per video.

What the user settled on, on the two-soloist TTBB:

- **Closed score, the one the singers hold.** Non-auditioned singers struggle to
  follow one line through divisi, so the video pairs the sung parts two to a
  staff by the Step 7 rules (7.2, 7.4, 7.6: chords where rhythm, ties and words
  agree, two voices with stems up and down elsewhere, a second lyric line only
  where the words differ, crossed parts never chorded, a tie never changes
  voice). Before engraving, the score shown gets `verify.py`'s check 14, and the
  script stops on a line that runs past its melisma. Pairing defaults to
  consecutive sung parts in score order with soloists left alone; `--staves` names the pairs, `--open` keeps one part per staff.
  Staves empty for a whole system are hidden, as in print.
- **Show the print file, time from the Cantai file.** The Cantai learning file
  prints Cantai's split syllables ("glea ea ea eams" for "gleams"). Give the print-faithful
  MusicXML as `--display`; the script checks that it has the same parts, bars,
  notes and tempo marks, reports any bar that differs, and refuses different
  tempo marks. On the two-soloist TTBB the two files agreed exactly.
- **Or show the closed score itself.** When the folder has the closed score
  the singers hold (two parts to a staff) beside the open Cantai file, give the
  closed one as `--display`: it is shown as it is, not rebuilt. Whose each
  notehead, rest and syllable is comes from the open file: the parts singing
  that pitch at that moment, the parts resting there, the parts starting a
  syllable there (with two lyric lines at one moment, the second goes to the
  lower part). Voice 1 / voice 2 is only the fallback, and the script says how
  many it needed: on the folk-like TTBB with piano all 753 notes and rests
  matched the open file, none by voice. The staves' part names ("Tenor 1 Tenor
  2") are matched against the open file's; where a closed score's parts have no
  names at all (the ballad TTBB's did not), each sung part goes to the staff
  holding most of its notes, and the staff is labelled with the parts'
  names.
- **Words laid out as the singers' copy prints them** (7.7). Give the display
  copy built with the print's layout; the script sets its above-the-staff words
  above, and a part whose words are printed on the other staff reads them
  there. Where one word prints on two rows (a shared chord), each part lights
  the row it reads: the upper part the upper row, the lower parts the lower.
- **A closed score can put a second voice a beat early.** The ballad TTBB's
  repaired file wrote bar 51 (both staves) and bar 47 (the low staff) as voice 1,
  a `<backup>` of the whole bar, then voice 2 with no `<forward>` over the beats
  it shares with voice 1: voice 2's notes land one or two beats early, in the
  printed score as in the video. The script finds it (the voice is short of a
  full bar, and every one of its notes matches the open file exactly that gap
  later), inserts the `<forward>` for the video, names the bars, and says to fix
  the file. Tell the user.
- **Repeats are unrolled.** Every lit thing is placed by bar and position in
  the bar, then at each moment that bar is played: repeat signs (with
  `times`) and first and second endings, in play order. The screen turns back
  for a repeat, up to a second early as for any turn, and a fermata inside a
  repeat is re-anchored each time. D.C., D.S. and codas are not followed; the
  script warns. The folk-like TTBB repeats its two-bar introduction.
- **Light mode, black on white like the page.** A dark screen was tried and
  rejected. `--dark` remains. Colours are colour-blind safe (Okabe–Ito), and
  the four parts sharing staves get the four strongest.
- **Rests light up too, with a progress bar.** A lit rest gets the same halo as
  a note, and a thin bar under the staff (above it for the upper of two voices)
  that runs from where the rest starts to where it ends *as the other staves
  print that time*, not just under the rest glyph. The bar fills in abrupt jumps
  of one pulse, like a note lighting: smooth motion hid the beats. The pulse is
  the coarsest note value that 95% of the part's sung bars keep to — the
  two-soloist TTBB's choir parts have six sixteenths in two bars and 224–283
  eighths, so eighths; "shortest note" would have given sixteenths, eight jumps a
  second, which reads as smooth again. Each jump lands where the other staves
  print that time, so the fill meets the piano's notes as they sound.
- **A part's own staff never disappears in its video.** Hiding empty staves
  removed the tenors' staff through the solos, so a Tenor 2 had nothing to
  follow and no rests to see lit.
- **Pages turn up to a second before the next page's first note**, never before
  the last note on the old page has started.

**Timing is anchored the way `stem_vs_score.py` does it** (its tempo map, the
offset from where the audio first sounds against the score's first note, only
the tempo refined on onsets) **and re-anchored after every fermata.** Sibelius
holds a fermata longer than written on playback, the MusicXML does not say by
how much, and everything after it runs that much late: on the two-soloist TTBB
0.28 s after bar 34 and 0.76 s after bar 123, which the user heard at 4:03.
The script measures each hold by aligning the score's pitch content with the
audio's (chroma every 50 ms, dynamic time warping within ±3 s of the straight
line), then fits the tempo and every hold together by least squares on the
onsets that the lights now land near. Fitted one after the other, a hold left in
the tempo fit spreads over the whole piece: a synthetic 0.6 s hold over a
barline measured 0.49 s that way, and 0.605 s fitted together. On the
two-soloist TTBB the holds came out 265 and 473 ms, the same from every mp3 to
within a few ms. A fermata counts wherever it is printed: on a note, on a rest
(bar 34 there has it on the soloists' rests and the piano's notes) or over a
barline. A fermata's own note and syllable stay lit through the hold.
Two things the fit could not do alone, both on a ballad TTBB's last line (two
fermata eighths 0.4 s apart, a caesura, then three bars of one held chord): with
no room between them to measure, fermatas less than 1.5 s apart count as one
hold, after the last of them; and where a stretch has too few onsets to refine
and one chord leaves the pitch alignment free to slide (it gave -1.1 s), the
hold is taken from the first onset after the fermata's written end (+0.76 s,
as measured by hand). A negative hold is flagged in the report as a wrong fit.

**When the fit cannot find a hold, measure it and say so: `--anchor BAR=M:SS.ss`.** On a
TTBB with piano the fit put −4.6 s on one fermata, and the stretch after it ran seconds
out: the two fermatas either side of it were only three bars apart, and the bars after it
were a repeated one-bar piano figure the pitch alignment could lock on to a bar early.
The stems settle it: the first onset after a fermata, in a stem that rests through it,
is the next bar's downbeat (there, bar 49 at 1:53.07 and bar 52 at 2:01.15, from the
piano and the voices' entrances). `--anchor` sets the offset of the stretch that bar is
in, overruling the fit, and the report says it was set by hand. Check the anchored
timing against a second entrance in the same stretch (bar 54's voices, 4.6 s after
bar 52, landed within 20 ms).

**The last fermata: the lights stay on until the sound stops.** A piece that ends on a
fermata has a stretch after it with no onsets, holding only the final note's end, and it
keeps the offset of the stretch before it. It once kept the fit's value instead, which the
anchors had not moved, so the last bar's lights ended 6 s before they began and the final
chord never lit; the user noticed. Playback also holds the final fermata as long as it
likes (3 s past the written length there), so every note or syllable that ends with the
score stays lit until the audio drops below -50 dBFS. Check the last bar in a still before
rendering.

**The drift check is aligned around the lights, not the straight line.** The pitch
alignment looks ±3 s either side of what it is centred on. After three fermatas each
held about 1.15 s the lights were 3.5 s from the straight line, and the check, centred
there, locked on to the wrong bar of the piano figure and reported the lights 6.3 s
behind when they were right. Centred on the lights it reads within 50 ms throughout.

**Name the closed score's staves after the parts on them.** The display file's
staves are matched to the open file's parts by name: "Tenors" matched none of "Tenor 1",
"Tenor 2a", "Tenor 2b", so nothing on that staff lit, and "Basses" matched only
"Bass". Giving the video's copy of the closed score the part names "Tenor 1 Tenor 2a
Tenor 2b" and "Baritone Bass" placed all 503 notes and rests from the open file, none by
voice. The staff labels on screen are the abbreviations, so nothing changes there.

**A predominant mix is timed by its Balanced track.** The level-threshold
anchor misreads a predominant mix whose first entrance is by a voice 21 dB
down: on the barbershop-voiced TTBB the Tenor 1, Tenor 2 and Baritone mixes
anchored 0.06-0.1 s late, and their tempo, fitted from that anchor on onsets
that are mostly the featured voice's consonants, drifted from 50 ms behind to
50 ms ahead. Every mp3 of a set made by `rehearsal_mix.py` is sample-aligned, so
when `TITLE - Balanced.mp3` sits beside a `TITLE - (V) predominant.mp3` or
`part-left.mp3` (a soloist's too, `TITLE - Solo predominant.mp3`, whose own fit
put a -1.1 s hold on a ballad's last fermata), is the same length and its level envelope lines up with it
(0 ms of lag within +-0.3 s), the script times the mix by the Balanced track and
says so in the report; the audio check on the mp4 is still against the mix's own
audio. Without a Balanced track, the pitch alignment of the opening overrules
the threshold anchor when they differ by 30 ms or more, and the tempo is refitted
from there.

**Measure drift against pitch, not against the nearest onset.** The first
version matched every light to the nearest onset in the audio within 0.35 s and
reported the median per 15 s; it read the 0.76 s lag as −2 ms, because with a
piano in sixteenths there is always an onset near enough, and the same check on
the finished mp4s was fooled the same way. Matching the onset pattern over a few
seconds fails too: a steady groove matches itself a beat away. Pitch content
tells repeated bars apart. The report now gives each fermata's hold and the
lights against the pitch alignment per 15 s (within 85 ms everywhere on the
two-soloist TTBB, under two 50 ms steps), naming the bar of any stretch 100 ms
out; ignore the last few seconds, where only reverb is left. Each finished mp4
is checked for what the file itself can go wrong on: its audio against the mp3
(0.0 ms) and every frame's time against the time it was meant for (exact).
All of it goes on record (next paragraph).

**Every check goes on record, whatever it finds.** The script writes everything
it prints to `TITLE - video checks.txt` beside the videos, a line for each
check even when it finds nothing: accidentals written out (8.1), lyric lines
(`verify.py` check 14), a **pitch readback** (every note Verovio engraves, read
the way a singer reads it, from its written accidental or else the key
signature and the bar so far, tied notes from their first note, against the
pitch it sounds; any difference stops the run), and per mp3 the sync report.
`--proof DIR` also writes one unlit PNG per screen of the all-parts view.
Compare each with the print PDF bar by bar (pitches and accidentals, rhythms,
ties and slurs, words and where they sit, extenders) and add to the file, under
the proof line, per screen, what differs or "as printed", and a one-line
result; show the user screens only where something differs. The record is so
the user can see, song by song, which checks still find things and which have
gone quiet, and decide which to keep. Cost: the automatic checks take seconds;
the comparison a few minutes for five screens. On the barbershop-voiced TTBB
the readback found 61 notes in 21 bars reading a half step off (the file wrote
no `<accidental>` at all), which inspection by eye had passed, and the first
comparison found 8 cautionary accidentals the print puts in parentheses and
the video leaves out.

**Shared notes and words split top to bottom.** A notehead, rest or syllable
two parts share gets its halo and its ink in stacked bands, the higher part's
colour on top, like the parts on the staff. Split side by side, as first built,
it read as one part singing the first half of the note and the other the
second. A shared rest's bar is striped the same way.

**One rest where both voices rest.** In a divided bar where both parts rest at
the same moment for the same time, voice 2's copy is `print-object="no"` and the
printed rest lights for both parts. The ballad TTBB had a bar sung in unison
by Baritone and Bass that had to be divided only because a tie ran on into a
divided bar, and it printed every rest twice, stacked.

**Triplets with no bracket.** An OMR'd or exported file can give notes their
triplet timing (`<time-modification>`) and no `<tuplet>` marking, and they print
as plain eighths that do not add up (the ballad TTBB's exploded file: 28
groups). The script groups each voice's run of such notes into tuplets and marks
the ends, in the display copy only.

**Ties light, and ties and slurs are greyed with their notes.** A tie lights
while either of its notes sounds, so a held note reads as one lit shape. In a
part's own video every other part's ties and slurs are grey like their notes;
the first build greyed notes but left every slur and tie black. Neither sits in
a voice's layer in Verovio's SVG: they hang off the measure, and whose they are
comes from the MEI, whose `<tie>` and `<slur>` carry `startid`/`endid` and the
same ids as the SVG. A tie is its notes' part's; a slur that starts or ends on
a chord two parts share (a merged bar) is both parts'. Pieces carried over a
system break come without an id, as `class="tie id-<its id> spanning"`, like a
syllable's extender.

Seven things that cost time:

- **Verovio's `condense` does nothing for MusicXML.** Hiding empty staves works
  only for MEI with `<scoreDef optimize="true">`: load the MusicXML, take
  `getMEI()`, add the attribute, reload. Note ids survive the round trip.
- **Keeping one staff while hiding the others** takes an invisible note:
  in every bar where that staff has no note, add
  `<layer n="9"><note dur="1" pname="c" oct="4" visible="false"/></layer>`.
  `<space>` does not keep the staff. The extra layer pushes the rests off
  their lines, a whole-bar rest to above the staff: pin them, `loc="6"` for an
  `mRest` or a whole `<rest>` (some files write a bar's rest as a plain whole
  rest, and the first fix, on `mRest` only, left those floating in the Bass
  video), `loc="4"` for any other rest.
- **A bar rest written as a plain whole rest sits at the left edge.** Verovio
  centres only a rest marked `<rest measure="yes"/>`; the print file of the
  two-soloist TTBB wrote many bar rests as whole rests on beat 1, and they sat
  against the barline. Before engraving, the script marks every rest that fills
  its bar alone (per voice and staff) as a bar rest. And a layer that holds only the
  invisible note is no voice: counting it put the Bass's rest bars above its
  staff, where the upper of two voices goes.
- **Verovio keeps MusicXML note ids** (`<note id="…">`), rests included, but
  not lyric ids; a syllable is found through the note or chord it sits under.
  Except where its extender runs over a system break: the rest of the line is
  drawn at the start of the next system, outside any note, as
  `<g class="syl id-<the syllable's svg id> spanning">`, possibly on the next
  screen. It has to be linked back by that class and lit with its syllable, with
  its own halo; the first build left the continuation dark (bar 78, Bass).
- **Which pixel belongs to which note.** The lights are pixel-exact: every
  lightable piece (note, notehead, rest, syllable) is drawn in a colour that
  spells three bits of its index, red, green and blue, with the rest of the page
  hidden, and the index is read back per pixel. `ceil(log2(n)) / 3` renders of
  the page, about four, plus one all-black one for coverage. The first version
  drew one bit per render, black or hidden, and needed an inverted render per bit
  as well to catch overlaps (on the two-soloist TTBB a Baritone–Bass unison in a
  divided bar drew two noteheads on one spot, their bits ORed into a third
  note's index, and three unlit notes lit up); that was 21 renders a page and
  136 of the 180 s a video took. In colour the piece on top simply wins, as on
  the screen. Noteheads at the same spot are then treated as one note lit in both
  colours. Place halos from the SVG's notehead positions, not from pixels, or
  touching seconds give tall ovals.
- **cairosvg antialiases text with colour fringes**, so each channel of a
  letter's edge has its own coverage. Read the bits against the coverage of the
  same channel; reading all three against red's put one syllable's pixels under
  another staff and blew its halo up across two systems. Draw the base score in
  grey (the engraving is black and white anyway) and let a lit piece claim the
  unattributed ink inside its own outline, or a lit word keeps a blue and
  orange rim.
- **cairosvg honours `visibility="visible"` inside a hidden parent**, which is
  what makes the renders cheap: hide the page, show only the lightable pieces.
  It ignores `@font-face`, so the metronome-mark note is a box until Leipzig is
  installed (8.4; on a Mac in `~/Library/Fonts`, which cairo reads there); the
  script does that itself when fonttools and brotli are there.

**Variable frame rate.** The video has one frame per change of lights or page,
shown from the exact millisecond of the change: about 1,000 frames for 4:48
where 30 fps is 8,643, so nothing is rounded to a frame grid and nothing is
encoded twice. The frames go to ffmpeg as PNGs through the concat demuxer with
a `duration` each; give every file `option framerate 1000`, or the image
demuxer's 1/25 s time base rounds each change to 40 ms. Keyframes every 30
frames keep seeking quick. With several mp3s, each renders in its own process,
one per CPU core, and only the first video's sync is measured (they share one
timing). The seven videos of the two-soloist TTBB took 35 minutes the first
way and 9 minutes this way, on 2 cores.

**Render in Claude's own workspace and copy the mp4s back** (11–13 MB each for
4:48 at 1920×1080). A desktop bridge that kills background jobs and stops each
command at three minutes cannot render a whole song, and the people this repo
is for should never be asked to install Homebrew packages or paste Terminal
commands. Running it on the user's own machine is only for someone who asks. Copies
arrive a few KB larger; compare the streams, not the files:
`ffmpeg -i x.mp4 -map 0:a -c copy -f md5 -` (and `0:v`) on both sides.

## Scripts

All nine are complete and standalone. Write them out as-is; nothing else is
needed. `check_pdf_type.py` and `find_performer_instructions.py` need only
`pdfplumber`; `musicxml_qc.py` and `cantai_mode.py` need only the standard
library; `lyric_collisions.py` needs `verovio` and `lxml`; `stem_vs_score.py`
needs `numpy` and `ffmpeg`; `verify.py` needs `lxml`, plus `pdfplumber` with
`--pdf` and `verovio` and `cairosvg` with `--render`, and calls
`musicxml_qc.py`, `find_performer_instructions.py` and `lyric_collisions.py`, so
keep all three beside it; `rehearsal_mix.py` needs `numpy`, `ffmpeg` with
libmp3lame, and `slab` for the 3D track; `score_video.py` needs `verovio`,
`cairosvg`, `lxml`, `numpy`, `pillow`, `fonttools`, `brotli` and `ffmpeg` with
libx264, and imports `stem_vs_score.py` and `verify.py`, so keep both beside it.


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

# A syllable may open with an apostrophe or a quote mark: pris-'ner, 'tis, "Hark.
OK_CHARS=re.compile(r"^[\"'’]?[A-Za-z][A-Za-z'’\-\.,!?;:\"]*$")

def syllable_onsets(part):
    """Where each syllable of one part starts (quarters from the start), and whether any staff of
    the part carries two voices."""
    div=1; bar_start=F(0); out=set(); voices=set()
    for m in part.findall('measure'):
        for a in m.findall('attributes'):
            d=a.find('divisions')
            if d is not None: div=int(d.text)
        pos=F(0); mx=F(0)
        for e in m:
            if e.tag=='backup': pos-=F(int(e.find('duration').text),div)
            elif e.tag=='forward': pos+=F(int(e.find('duration').text),div)
            elif e.tag=='note':
                if e.find('chord') is not None: continue
                if e.find('rest') is None:
                    voices.add((e.findtext('staff') or '1', e.findtext('voice') or '1'))
                    if e.find('lyric') is not None and (e.findtext('lyric/text') or '').strip():
                        out.add(bar_start+pos)
                pos+=F(int(e.find('duration').text),div) if e.find('duration') is not None else 0
            mx=max(mx,pos)
        bar_start+=mx
    return out, bool(out) and len({v for st,v in voices})>1     # a sung part (not a piano) on two voices

def qc(path):
    root=load(path)
    issues=defaultdict(list)
    # A closed score (two parts to a staff) prints words once where the staves sing them together,
    # often between the staves: the other staff's notes there carry none and read that line. So in
    # a closed score a note may also borrow a syllable another part starts at the same moment. Not
    # in an open score, where every part carries its own words and a gap is a lost syllable.
    ons={p.get('id'): syllable_onsets(p) for p in root.findall('part')}
    closed=any(two for _,two in ons.values())
    for part in root.findall('part'):
        pid=part.get('id'); div=1; ts=None
        prev_oct={}; octjumps=[]
        # One sequence per part on each staff: on a shared staff the two
        # singers' notes interleave in document order, and walking back from a
        # voice-2 note would otherwise land on voice 1's syllables and rests.
        seqs=defaultdict(list)   # (staff, part) -> [(measure, is_pitched, lyric, has_extend, is_tie_stop, onset, dur)]
        bar_start=F(0)
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
            pos=F(0)
            for e in m:
                if e.tag=='backup': pos-=F(int(e.find('duration').text),div); continue
                if e.tag=='forward': pos+=F(int(e.find('duration').text),div); continue
                if e.tag!='note': continue
                n=e
                dur=F(int(n.find('duration').text),div) if n.find('duration') is not None else F(0)
                # voices 1/5 are the upper part of a staff; any other voice is the
                # lower part (chorale writes a stray lower-part note in voice 3)
                key=(n.findtext('staff') or '1', 'upper' if (n.findtext('voice') or '1') in ('1','5') else 'lower')
                if n.find('chord') is None:
                    onset=bar_start+pos
                    pos+=dur
                    ties = [x.get('type') for x in n.findall('tie')]
                    ly = n.find('lyric')
                    if n.find('rest') is not None:
                        seqs[key].append((num, False, None, False, False, onset, dur))
                    else:
                        seqs[key].append((num, True,
                                    ly.findtext('text') if ly is not None else None,
                                    ly is not None and ly.find('extend') is not None and ly.find('extend').get('type') != 'stop',
                                    'stop' in ties, onset, dur))
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
                if key in prev_oct and abs(o-prev_oct[key])>=2:
                    octjumps.append(f"{pid} m{num}: {prev_oct[key]}->{o}")
                prev_oct[key]=o
            bar_start+=mx
        # octave leaps only matter where there are lyrics to sing
        if any(True for n in part.iter('lyric')):
            issues['octave jump in a sung line'].extend(octjumps)
            # On a staff two parts share, one lyric line serves both where they
            # sing the same words (SKILL.md 7.4): the lower part's note then has
            # no syllable of its own and sings the one printed for the other
            # part at the same moment.  So a note with no syllable is fine if
            # the other part on its staff starts a syllable at that onset, or if
            # it continues -- contiguous in its own part -- a note that has one
            # (with an extender) or that borrows one, or if its part's notes
            # before it were merged into the other part's chords and that
            # part's syllable is still being held.
            starts=defaultdict(set)   # (staff, part) -> onsets of syllables
            for (st,ln),seq in seqs.items():
                for (mn,pit,txt,ext,tie,on,du) in seq:
                    if pit and txt is not None: starts[(st,ln)].add(on)
            def borrowed(st,ln,on):
                return any(on in s for (st2,ln2),s in starts.items() if st2==st and ln2!=ln) or \
                    (closed and any(on in o for p2,(o,_) in ons.items() if p2!=pid))
            # where each syllable is held with an extender: onset to the end of its melisma
            held=defaultdict(list)    # (staff, part) -> [(from, to)]
            for (st,ln),seq in seqs.items():
                for i,(mn,pit,txt,ext,tie,on,du) in enumerate(seq):
                    if not (pit and txt is not None and ext): continue
                    end=on+du
                    for q in seq[i+1:]:
                        if not q[1] or q[2] is not None or q[5]!=end: break
                        end=q[5]+q[6]
                    held[(st,ln)].append((on,end))
            for (st,ln),seq in seqs.items():
                for i,(mn,pit,txt,ext,tie,on,du) in enumerate(seq):
                    if not pit or txt is not None or tie or borrowed(st,ln,on): continue
                    j=i-1; ok=False
                    while True:
                        q=seq[j] if j>=0 else None
                        if q is None or q[5]+q[6]!=seq[j+1][5]:
                            # a gap: the part's earlier notes merged into the other
                            # part's chords, so the other part's melisma is this one's
                            ok=any(a<seq[j+1][5]<b for (st2,ln2),iv in held.items()
                                   if st2==st and ln2!=ln for a,b in iv)
                            break
                        if not q[1]: break                 # a rest ends the melisma
                        if q[2] is not None: ok=q[3]; break
                        if borrowed(st,ln,q[5]): ok=True; break
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

--pdf enables the checks that compare against the engraving (6, 10, 11, 12, 17).
--original is the file this one was made from: the score before a revoicing (check 16),
or the open score a closed score was collapsed from, with its printed words, not a Cantai
learning file, which re-sings melismas (check 14: lines under notes whose words moved to
the other line).
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
        # events per voice, a chord being one event: a tie on any chord member must meet the same
        # pitch, carrying the stop, in the voice's next event (a tie on the upper note of a chord was
        # once compared with the next chord's lowest note)
        byv = defaultdict(list)
        for mn, n, v, _ in notes_of(part):
            if n.find('chord') is not None and byv[v]:
                byv[v][-1][1].append(n)
            else:
                byv[v].append((mn, [n]))
        def ties_of(ns, kind):
            return {pitch_midi(x.find('pitch')) for x in ns if x.find('pitch') is not None
                    and kind in {t.get('type') for t in x.findall('tie')}}
        for v, seq in byv.items():
            for i, (mn, ns) in enumerate(seq):
                for p in ties_of(ns, 'start'):
                    nxt = seq[i + 1][1] if i + 1 < len(seq) else []
                    if p not in ties_of(nxt, 'stop'):
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: tie start with no matching stop")
                for p in ties_of(ns, 'stop'):
                    prv = seq[i - 1][1] if i else []
                    if p not in ties_of(prv, 'start'):
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: tie stop with no start")
        # slurs: each start closed by the next stop of the same number, in the same voice. On a shared
        # staff a slur that starts in voice 2 and ends on a note merged into a voice-1 chord is closed
        # by nothing: the chord's one stop closes the upper part's slur, and the lower part's is drawn
        # on to whatever stop comes next, bars later (SKILL.md 7.2)
        open_ = {}
        for mn, n, v, _ in notes_of(part):
            for sl in n.iter('slur'):
                num, typ = sl.get('number') or '1', sl.get('type')
                if typ == 'start':
                    if num in open_:
                        bad.append(f"{names[part.get('id')]} bar {open_[num][0]}: slur {num} (voice {open_[num][1]}) "
                                   f"never closed before another starts in bar {mn}")
                    open_[num] = (mn, v)
                elif typ == 'stop':
                    if num not in open_:
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: slur {num} stop with no start")
                    elif open_[num][1] != v:
                        bad.append(f"{names[part.get('id')]} bar {open_[num][0]}-{mn}: slur {num} starts in voice "
                                   f"{open_[num][1]} and stops in voice {v}")
                    open_.pop(num, None)
        for num, (mn, v) in open_.items():
            bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: slur {num} never closed")
    report(8, 'Ties and slurs pair up', 'FAIL' if bad else 'PASS', f'{len(bad)} unpaired' if bad else
           'every tie and slur pairs', bad)


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


def sung_positions(root, only=None):
    """{(bar, onset, midi)} where a note of `root` starts a syllable: which notes of a derived score
    (a closed score, a revoicing) sing a syllable of their own, whatever line prints it. `only`: the
    part names to take, those sharing the staff being checked (a soloist singing the same pitch at
    the same moment is not the tenors' word)."""
    out = set()
    names = {sp.get('id'): (sp.findtext('part-name') or '').strip() for sp in root.iter('score-part')}
    for part in root.findall('part'):
        if only is not None and names.get(part.get('id')) not in only:
            continue
        for mn, n, v, t in notes_of(part):
            if n.find('pitch') is not None and any(l.findtext('text') for l in n.findall('lyric')):
                out.add((mn, t, pitch_midi(n.find('pitch'))))
    return out


def parts_on(staff_name, source_names):
    """The source parts a derived staff carries, by name ("Tenor 1\nTenor 2", "Tenor 1 + Tenor 2");
    all of them when the name does not say."""
    got = {n for n in source_names if n and re.search(r'(^|[\n+/&,])\s*' + re.escape(n) + r'\s*($|[\n+/&,])', staff_name)}
    return got or set(source_names)


def lyric_line_runs(part, sung=frozenset()):
    """Each lyric line as an engraver draws it: from a syllable with <extend/> on to the next note in
    the same voice with a syllable on that line, over every syllable-less note between, rests or no
    (SKILL.md 7.6). A line is wrong when a note under it comes after a printed rest, or sings a
    syllable of its own (`sung`, from the source) that is printed on the other line (7.4).
    Returns [(bar, voice, line, text, bar it runs to, why)]."""
    byv = defaultdict(list)
    for mn, n, v, t in notes_of(part):
        if n.find('chord') is None and n.find('grace') is None:
            byv[v].append((mn, n, t))
    out = []
    for v, seq in byv.items():
        for i, (mn, n, _) in enumerate(seq):
            for l in n.findall('lyric'):
                e = l.find('extend')
                if e is None or e.get('type') == 'stop' or not l.findtext('text'):
                    continue
                num = l.get('number') or '1'
                rest, last, why = False, None, ''
                for mn2, n2, t2 in seq[i + 1:]:
                    if any((l2.get('number') or '1') == num for l2 in n2.findall('lyric')):
                        break                                   # the next syllable on the line ends it
                    if n2.find('rest') is not None:
                        rest = rest or n2.get('print-object') != 'no'
                        continue
                    p2 = n2.find('pitch')
                    held = any(x.get('type') == 'stop' for x in n2.findall('tie'))   # a tied note begins no word
                    own = p2 is not None and not held and (mn2, t2, pitch_midi(p2)) in sung
                    if rest or own:
                        last, why = mn2, 'past a rest' if rest else 'under notes that sing their own words'
                if last is not None:
                    out.append((mn, v, num, l.findtext('text'), last, why))
    return out


def check_extend_runs(root, names, original=None):
    """14: an <extend/> needs a following note in the same voice for the line to run under, and the
    line must stop where the melisma does (SKILL.md 7.6)."""
    bad = []
    oroot, onames = load(original) if original else (None, {})
    for part in root.findall('part'):
        sung = sung_positions(oroot, parts_on(names[part.get('id')], onames.values())) if original else frozenset()
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
                        # mid-word: a line over a melisma of moving notes, a hyphen over a tie-only hold (2.5)
                        held = []
                        for _, n2 in seq[i + 1:]:
                            if n2.find('rest') is not None or n2.find('lyric') is not None: break
                            held.append(n2)
                        if held and all(any(t.get('type') == 'stop' for t in n2.findall('tie')) for n2 in held):
                            bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: {l.findtext('text')!r} is mid-word "
                                       f"and held only by a tie; it prints a hyphen, and an extender would replace it")
        for mn, v, num, text, last, why in lyric_line_runs(part, sung):
            bad.append(f"{names[part.get('id')]} voice {v} line {num}: the line from {text!r} (bar {mn}) runs on "
                       f"to bar {last}, {why}")
    report(14, 'No extender outruns its voice', 'FAIL' if bad else 'PASS', f'{len(bad)} problem(s)' if bad else
           'every extender has notes under it and stops where its melisma does' +
           ('' if original else ' (lines under notes whose words moved to the other line need --original)'), bad)


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
    mid = lambda t: (t['lines'][0] + t['lines'][4]) / 2
    for c in p.chars:
        if any(f in c['fontname'] for f in MUSIC_FONTS) and (ord(c['text'][0]) in HEADS or c['text'] == 'w') \
                and c['x0'] < l['x1'] and c['x1'] > l['x0'] and abs((p.height - c['matrix'][5]) - l['top']) <= 4 * sp:
            # the notehead must belong to the same staff: an extender between two staves can sit on
            # the upper staff's ledger grid right over a note of the lower staff (a TTBB with piano)
            y = p.height - c['matrix'][5]
            if min(st, key=lambda t: abs(mid(t) - y)) is s:
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
            # the lyric font at its size, or a page scaled a few percent (Finale scales pages one by one:
            # a TTBB with piano set its last two pages' lyrics at 12.1 pt against 11.5)
            cs = [c for c in page['chars'] if c['font'] == self.lyric_font
                  and 0.92 * self.lyric_size <= c['size'] <= 1.09 * self.lyric_size]
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
                mid = (l.findtext('syllabic') or 'single') in ('begin', 'middle')
                xs.append((l.findtext('text') or '', e is not None and e.get('type') != 'stop', mn, slurred or mid))
        ps = printed[nm]
        sm = difflib.SequenceMatcher(a=[t.strip() for t, _, _ in ps], b=[x[0].strip() for x in xs], autojunk=False)
        blocks = sm.get_matching_blocks()
        for a0, b0, n in blocks:
            for k in range(n):
                t, has, where = ps[a0 + k]
                xt, ext, mn, slurred = xs[b0 + k]
                matched += 1
                if ext and not has and slurred:
                    continue          # a slurred or mid-word melisma keeps its line even where none is printed (SKILL.md 2.5)
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
    E.grid_base = base
    bad = [f'p{pn} x{x:.0f}: {d - base:.2f} half-spaces' for d, pn, x in offs if abs((d - base) - round(d - base)) > 0.15]
    report(12, 'Noteheads on the grid', 'FAIL' if bad else 'PASS',
           f'{len(offs)} noteheads, {len(bad)} off the grid' + (f' (font offset {base:+.2f})' if abs(base) > 0.05 else ''), bad[:20])


def pdf_bars(E):
    """[(page, system, x from, x to)] for every bar the engraving prints, in reading order.
    A bar is a stretch between two vertical lines that cross every staff of the system; a
    stretch with no note or rest in it is a courtesy key or time at a system's end, and is dropped."""
    out = []
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
                if c:
                    out.append((page, sy, a, b, len(c)))
    return out


def check_onsets(root, E):
    """11: notes that start together in the file start at one x in the PDF.
    Compares, bar by bar, the number of distinct onsets across all parts with the number of
    distinct note/rest columns the engraving prints."""
    ons = defaultdict(set)
    for part in root.findall('part'):
        for mn, n, v, t in notes_of(part):
            r = n.find('rest')
            if r is not None and r.get('measure') == 'yes': continue
            if n.findtext('type') is None and r is not None: continue
            ons[mn].add(t)
    order = [m.get('number') for m in root.find('part').findall('measure')]
    cols = [c for *_, c in pdf_bars(E)]
    if len(cols) != len(order):
        return report(11, 'Cross-staff onset alignment', 'NOT RUN',
                      f'PDF bar count {len(cols)} does not match the file ({len(order)}); first-bar or pickup layout not understood')
    bad = [f'bar {mn}: {len(ons[mn])} onset(s) in the file, {c} column(s) in the PDF'
           for mn, c in zip(order, cols) if c and len(ons[mn]) != c]
    report(11, 'Cross-staff onset alignment', 'WARN' if bad else 'PASS',
           f'{len(bad)} bar(s) where the file and the engraving disagree on how many attack points there are' if bad
           else 'every bar has as many attack points as the engraving has columns', bad)


CLEF_REF = {'G': 4 * 7 + 4, 'F': 3 * 7 + 3, 'C': 4 * 7 + 0}     # the note on the clef's line: G4, F3, C4 (diatonic)


def file_positions(root):
    """{(bar index, staff index in the system): {half-spaces below the top line}} for every notehead
    the file would print, each read with the clef in force at its onset. Staves are counted over the
    parts in file order (a part with <staves>2</staves> takes two)."""
    pos = defaultdict(set)
    base = 0
    for part in root.findall('part'):
        nst, div = 1, 1
        clefs = {}                      # staff number -> [(bar index, onset, top-line diatonic)]
        for bi, m in enumerate(part.findall('measure')):
            t = F(0)
            last = F(0)
            for e in m:
                if e.tag == 'attributes':
                    if e.find('divisions') is not None: div = int(e.findtext('divisions'))
                    if e.find('staves') is not None: nst = int(e.findtext('staves'))
                    for c in e.findall('clef'):
                        k = int(c.get('number', '1'))
                        line = int(c.findtext('line') or {'G': 2, 'F': 4, 'C': 3}.get(c.findtext('sign'), 2))
                        ref = CLEF_REF.get(c.findtext('sign'))
                        if ref is None: continue
                        ref += 7 * int(c.findtext('clef-octave-change') or 0)
                        clefs.setdefault(k, []).append((bi, t, ref + 2 * (5 - line)))
                elif e.tag == 'backup':
                    t -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward':
                    t += F(int(e.findtext('duration')), div)
                elif e.tag == 'note':
                    on = last if e.find('chord') is not None else t
                    if e.find('chord') is None:
                        last = t
                        if e.find('grace') is None: t += F(int(e.findtext('duration') or 0), div)
                    p = e.find('pitch')
                    if p is None: continue
                    k = int(e.findtext('staff') or 1)
                    cl = [c for c in clefs.get(k, []) if (c[0], c[1]) <= (bi, on)]
                    if not cl: continue
                    d = 7 * int(p.findtext('octave')) + STEPS.index(p.findtext('step'))
                    pos[(bi, base + k - 1)].add(cl[-1][2] - d)
        base += nst
    return pos, base


def check_pitches(root, E):
    """17: the staff positions of the noteheads printed in each bar of each staff are the ones
    the file's pitches would print at. Reads the page with this script's own staff finder, so a
    staff misread by the extractor (ledger lines taken for staff lines: every note a line off)
    cannot pass by agreeing with itself."""
    fpos, nst = file_positions(root)
    order = [m.get('number') for m in root.find('part').findall('measure')]
    bars = pdf_bars(E)
    if len(bars) != len(order):
        return report(17, 'Noteheads match the pitches', 'NOT RUN',
                      f'PDF bar count {len(bars)} does not match the file ({len(order)})')
    bad, skipped, seen = [], 0, 0
    runs = defaultdict(list)
    for bi, (page, sy, a, b, _) in enumerate(bars):
        if len(sy) != nst: skipped += 1; continue
        sp = page['sp']
        allst = [s for y in page['systems'] for s in y]
        got = defaultdict(set)
        for c in page['chars']:
            if not any(f in c['font'] for f in MUSIC_FONTS) or not (a + 1 < c['x0'] < b - 1): continue
            code = ord(c['t'][0])
            if code not in HEADS and not (c['t'] == 'w' and 'Helsinki' in c['font']): continue
            s = min(allst, key=lambda s: abs((s['lines'][0] + s['lines'][4]) / 2 - c['y']))
            if not any(s is x for x in sy): continue
            k = next(i for i, x in enumerate(sy) if x is s)
            got[k].add(round((c['y'] - s['lines'][0]) / (sp / 2) - E.grid_base))
        for k in range(nst):
            seen += 1
            want = fpos.get((bi, k), set())
            if got[k] != want:
                sh = {dd for dd in range(-9, 10) if dd and {w + dd for w in want} == got[k] and want}
                what = (f'every head {min(sh, key=abs):+d} half-space(s) from the file' if sh else
                        f'PDF only {sorted(got[k] - want)}, file only {sorted(want - got[k])}')
                bad.append(f'bar {order[bi]}, staff {k + 1} of the system: {what}')
                runs[k].append(bi)
    if not seen:
        return report(17, 'Noteheads match the pitches', 'NOT RUN',
                      f'no system has as many staves as the file ({nst}): hidden staves, not understood')
    note = f'; {skipped} bar(s) on systems with a different staff count not compared' if skipped else ''
    report(17, 'Noteheads match the pitches', 'FAIL' if bad else 'PASS',
           (f'{len(bad)} bar-staff(s) of {seen} where the printed heads and the file disagree' if bad
            else f'{seen} bar-staves compared, printed heads and file pitches agree') + note, bad)


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
            for n, nm in ((10, 'Extension lines match the PDF'), (11, 'Cross-staff onset alignment'), (12, 'Noteheads on the grid'), (17, 'Noteheads match the pitches')):
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
            if hasattr(E, 'grid_base'): check_pitches(root, E)
            else: report(17, 'Noteheads match the pitches', 'NOT RUN', 'no noteheads recognised (see check 12)')
    else:
        for n, nm in ((10, 'Extension lines match the PDF'), (11, 'Cross-staff onset alignment'), (12, 'Noteheads on the grid'), (17, 'Noteheads match the pitches')):
            report(n, nm, 'NOT RUN', 'needs --pdf')
    check_shared_staff(root)
    check_extend_runs(root, names, a.original)
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

Writes, for every voice V (the Chorus Connection section in parentheses, see Sections below;
a voice named Solo... gets none):
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

Sections: Chorus Connection files a track under the section named in parentheses, and shows
a track whose parenthesised name is not one of the chorus's sections to EVERYONE. A voice
that is a division of a section goes in as the section plus a suffix after the parentheses:
"Tenor 2a" -> "(Tenor 2) a", "Bass b" -> "(Bass) b". That is the default for a name ending in
a lone lower-case letter; everything else is used as it is. Override per voice with
--section "Voice=Section|suffix" ("Tenor 2a=Tenor 2|a", "Bari=Baritone|", or "Descant=|" for
no parentheses at all). The mapping is printed; confirm it with the user before handing over
the tracks, since each chorus names its sections its own way.

Stem levels: every stem's median level while sounding is printed. A stem several dB off
the others (one set's Bass came out 9 dB hot) gets --trim, applied before every mix gain.

Peaks: every mix is measured before encoding. Only if one goes over 0 dBFS are ALL of them
turned down by the same amount (the loudest lands at -1 dBFS), so the tracks keep their
loudness relative to one another. The 3D track, a headphone extra, is loudness-matched to
the panned Balanced track and then turned down on its own if it would clip.

Needs numpy and ffmpeg (with libmp3lame); slab for the 3D track (without it the 3D track is
not made, the script says so and exits 1).
"""
import re, sys, os, types, argparse, subprocess
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


def section_of(n, sections):
    """(section, suffix) for a voice: --section if given; a Solo... voice has no section; a name
    ending in a lone lower-case letter ("Tenor 2a", "Bass b") is that section divided."""
    if n in sections:
        return sections[n]
    if n.lower().startswith('solo'):
        return '', ''
    m = re.fullmatch(r'(.*\d)([a-z])', n) or re.fullmatch(r'(.*\S) ([a-z])', n)
    return (m.group(1), m.group(2)) if m else (n, '')


def label(n, sections):
    sec, suf = section_of(n, sections)
    if not sec:
        return n
    return f'({sec})' + (f' {suf}' if suf else '')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('title'); ap.add_argument('out')
    ap.add_argument('voices', nargs='+', help='"Name=stem.wav", lowest voice first')
    ap.add_argument('--accomp', action='append', default=[])
    ap.add_argument('--trim', action='append', default=[], help='"Name=-9": dB applied to that stem first')
    ap.add_argument('--place', action='append', default=[],
                    help='"Solo=0", "Solo 1=5R", "Solo 2=5L": put a voice (or accompaniment) at a fixed '
                         'direction instead of the automatic layout; the other voices keep theirs')
    ap.add_argument('--section', action='append', default=[],
                    help='"Voice=Section|suffix": the Chorus Connection section (in parentheses) and the '
                         'suffix after it, e.g. "Tenor 2a=Tenor 2|a"; "Voice=|" for no section')
    ap.add_argument('--only', choices=['all', '3d'], default='all', help='write every track, or only the 3D one')
    ap.add_argument('--featured', type=float, default=3.0)
    ap.add_argument('--others', type=float, default=-21.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    trims = {k: float(v) for k, v in (t.split('=', 1) for t in a.trim)}
    placed = {k: parse_az(v) for k, v in (t.split('=', 1) for t in a.place)}
    V = [tuple(s.split('=', 1)) for s in a.voices]
    A = [tuple(s.split('=', 1)) for s in a.accomp]
    sections = {}
    for t in a.section:
        k, v = t.split('=', 1)
        if '|' not in v: v += '|'
        sections[k] = tuple(x.strip() for x in v.split('|', 1))
    for n in list(trims) + list(placed) + list(sections):
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

    print('\nfile names (Chorus Connection section in parentheses):')
    for v in names:
        print(f'   {v:12} -> {label(v, sections)}')
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
        builders[f'{a.title} - {label(v, sections)} predominant'] = (lambda v=v: predominant(v))
        builders[f'{a.title} - {label(v, sections)} part-left'] = (lambda v=v: part_left(v))
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

### score_video.py

```python
#!/usr/bin/env python3
"""Follow-along score videos from a MusicXML and the rehearsal mp3s made from it (SKILL.md Step 10).

    python3 score_video.py score.musicxml "Shenandoah - Balanced.mp3" \
        "Shenandoah - (Tenor 1) predominant.mp3" "Shenandoah - (Tenor 2) predominant.mp3" ...
        [--display print.musicxml] [-o OUT_DIR] [--part "Tenor 1=Tenor"]
        [--staves "Tenor 1+Tenor 2,Baritone+Bass" | --open] [--pulse 8] [--dark]
        [--clip START,SECONDS] [--stills T1,T2,...] [--staff-px 44] [--jobs N] [--proof DIR]

The MusicXML is the one the audio was rendered from (one part per staff, as Sibelius and
Cantai sing it). When that is a Cantai learning file, give the print-faithful file as
--display: it is shown instead (normal words, slurs and ties), after a check that it has
the same parts, bars, notes and tempo marks. --display can also be the closed score the
singers hold (two parts to a staff, fewer parts than the open file): then it is shown as it
is, and whose each notehead, rest and syllable is comes from the open file (the parts
singing that pitch, resting, or starting a syllable at that moment; a second lyric line
goes to the lower part), with voice 1 / voice 2 as the fallback. Repeat signs and first
and second endings are unrolled: the lights follow the bars in the order they are played,
turning back a screen for a repeat. Each mp3 gives one mp4 of the same name beside it (or
in OUT_DIR), and everything the run prints, every check included, also goes to
"<title> - video checks.txt" there; --proof DIR writes one unlit PNG per screen, for the
comparison with the print PDF that SKILL.md Step 10 asks for:

  a Balanced mp3          -> every sung part lights up in its own colour
  "(Part) predominant", "(Part) part-left", "(Section) a predominant", "Solo ... " mp3s
                          -> only that part lights up; every other part, piano too, is grey,
                             and that part's staff is never hidden, so its rests stay on screen

A note lights (its colour, and a soft halo) while it sounds; its syllable stays lit from its
note until the next syllable or rest, so a melisma or a tie keeps its word lit. A note or
word two parts share gets its halo and ink in stacked bands, the higher part's colour on
top (side by side would read as one part singing the first half, the other the second).
A tie lights while either of its notes sounds; in a part's own video the other parts' ties
and slurs are grey with their notes. A rest lights the same way, and a
bar under it (above the staff for the upper of two voices) runs from where the rest starts
to where it ends as the other staves print that time, filling in jumps of one pulse: each
part's pulse is the coarsest note value that 95% of the bars it sings keep to (eighths in a
piece of eighths with one bar of sixteenths; --pulse sets it). Each jump lands where the
other staves print that time, so the fill meets the piano's notes as they sound and a
singer who cannot count rests sees the beats go by. Pages turn up to a second before the
next page's first note, never before the last note on the old page has begun. Staves empty
for a whole system are hidden, as in a printed score. Black on white by default; --dark for
light notation on a dark screen.

Closed score by default: the sung parts are paired two to a staff, as the singers hold
them (consecutive sung parts in score order, soloists left on their own staff; --staves
names the pairs, --open keeps one part per staff). A bar where the two parts share rhythm,
ties and words becomes chords with one lyric line; elsewhere the upper part is voice 1
(stems up), the lower voice 2 (stems down), and the lower part gets its own lyric line
only where its words differ (SKILL.md 7.2 and 7.4). A tie never changes voice: a merged
bar tied to a divided one is divided too. Crossed parts are never chorded (7.6).
Accompaniment staves are shown as written.

Timing, as stem_vs_score.py does it: beats become seconds with the score's tempo marks,
and the line-up is anchored where the audio first sounds against where the score first
has a note; only the tempo is refined, on note onsets found in the audio. Then it is
re-anchored after every fermata (on a note, a rest or a barline): playback holds a
fermata longer than written, by an amount the file does not say, and everything after
it runs that much late. Each hold is
measured by aligning the score's pitch content with the audio's (chroma, dynamic time
warping) and refined on the onsets that follow; the report gives each fermata's hold and
checks every 15 s of the lights against the pitch alignment, naming the bar of any stretch
more than 100 ms out. (Matching each light to the nearest onset in the audio cannot catch
this: with a piano in sixteenths there is always an onset near enough, and a 0.75 s lag
measured as -2 ms.) Each finished mp4 is checked too: its audio against the mp3, and its
frames against the times they were meant for.
The video has a variable frame rate: one frame per change of lights or page,
each shown from the exact millisecond of the change, so nothing is rounded to a frame grid
and nothing is encoded twice. With several mp3s, each renders in its own process, one per
CPU core (--jobs).

Needs verovio, cairosvg, lxml, numpy, pillow, fonttools and brotli (the Leipzig font fix,
8.4) and ffmpeg with libx264; stem_vs_score.py and verify.py beside it. D.C., D.S. and codas are not
followed (repeat signs and endings are). Seven videos of a 4:48 piece took 9 minutes on 2
cores.
"""
import sys, os, io, re, copy, math, argparse, subprocess, zipfile, tempfile, shutil, bisect
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction as Fr
import numpy as np
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stem_vs_score import load_score, beats_to_sec, envelope, runs  # noqa: E402
from verify import lyric_line_runs, sung_positions, parts_on  # noqa: E402

# Okabe-Ito, colour-blind safe; neighbours on a shared staff get well-separated hues
PALETTE = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#B07A00', '#7F3C8D', '#00798C', '#8C510A']
GREY = '#B4B4B4'
# dark mode, the default: for backlit screens, not paper. Bright hues that keep apart on a dark
# ground; the same order (the four parts sharing staves first)
PALETTE_DARK = ['#56B4E9', '#FF9F43', '#4CD98A', '#F48FD0', '#F0E442', '#B39DFF', '#45D6D0', '#E8B070']
THEME = {}


def set_theme(dark):
    """Light (black on white, like the printed page) by default; --dark for a backlit screen."""
    if dark:
        THEME.update(dark=True, bg=np.array([28, 28, 30], np.float32), ink=np.array([225, 225, 225], np.float32),
                     grey='#8C8C8C', tint=0.5, lift=0.35)
    else:
        THEME.update(dark=False, bg=np.array([255, 255, 255], np.float32),
                     ink=np.array([0, 0, 0], np.float32), grey=GREY, tint=0.30, lift=0.0)


set_theme(False)
STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
NOTE_ORDER = ['grace', 'cue', 'chord', 'pitch', 'unpitched', 'rest', 'duration', 'tie', 'instrument',
              'footnote', 'level', 'voice', 'type', 'dot', 'accidental', 'time-modification', 'stem',
              'notehead', 'notehead-text', 'staff', 'beam', 'notations', 'lyric', 'play', 'listen']


# ----------------------------------------------------------------------------- reading the score

def read_xml(path):
    if path.lower().endswith('.mxl'):
        z = zipfile.ZipFile(path)
        cont = etree.fromstring(z.read('META-INF/container.xml'))
        full = cont.find('.//{*}rootfile').get('full-path')
        return etree.fromstring(z.read(full))
    return etree.parse(path, etree.XMLParser(remove_blank_text=True, recover=True)).getroot()


def hexrgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32)


def midi(note):
    p = note.find('pitch')
    if p is None:
        return None
    return 12 * (int(p.findtext('octave')) + 1) + STEP[p.findtext('step')] + int(float(p.findtext('alter') or 0))


def _base(key):
    """A syllable key's note id: "id@n" is line n of a note printing its word on two lines."""
    return key.split('@')[0]


def _letters(t):
    return re.sub(r'[^a-z]', '', (t or '').lower())


def lyric1(note):
    """The first lyric line's (syllabic, text), or None."""
    ls = note.findall('lyric')
    if not ls:
        return None
    ls.sort(key=lambda l: int(re.sub(r'\D', '', l.get('number') or '1') or 1))
    t = ''.join(x.text or '' for x in ls[0].findall('text'))
    return (ls[0].findtext('syllabic') or 'single', t) if t.strip() else None


def ties(note):
    ts = [t.get('type') for t in note.findall('tie')] + [t.get('type') for t in note.iter('tied')]
    return 'start' in ts, 'stop' in ts


def scan_part(pi, part, prefix='n'):
    """Assign an id to every note and return (notes, measure starts) in quarters."""
    div, pos, notes, starts, k = 1, Fr(0), [], [], 0
    for mi, m in enumerate(part.findall('measure')):
        starts.append(pos)
        t, mx, last_on = pos, pos, pos
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= Fr(int(e.findtext('duration')), div)
            elif e.tag == 'forward':
                t += Fr(int(e.findtext('duration')), div)
            elif e.tag == 'note':
                nid = f'{prefix}{pi}x{k}'
                k += 1
                e.set('id', nid)
                grace = e.find('grace') is not None
                chord = e.find('chord') is not None
                d = Fr(0) if grace else Fr(int(e.findtext('duration') or 0), div)
                on = last_on if chord else t
                ts, tp = ties(e)
                notes.append(dict(id=nid, part=pi, mi=mi, el=e, on=on, dur=d, rel=on - pos,
                                  voice=e.findtext('voice') or '1', rest=e.find('rest') is not None,
                                  chord=chord, grace=grace, midi=midi(e), tie_start=ts, tie_stop=tp,
                                  lyric=lyric1(e), type=e.findtext('type'), dots=len(e.findall('dot')),
                                  tmod=e.find('time-modification') is not None))
                if not chord:
                    last_on = t
                    t += d
            mx = max(mx, t)
        pos = mx
    return notes, starts


def syllable_windows(notes):
    """Per sung note with a syllable: (start, end) in quarters, the end running on through the
    following syllable-less notes (a melisma or a tie) and stopping at a rest or the next syllable."""
    seq = [n for n in notes if not n['chord'] and not n['grace'] and n['voice'] == '1']
    out, cur = {}, None
    for n in seq:
        if n['rest']:
            cur = None
        elif n['lyric']:
            cur = n['id']
            out[cur] = [n['on'], n['on'] + n['dur']]
        elif cur:
            out[cur][1] = n['on'] + n['dur']
    return out


# ----------------------------------------------------------------------------- closed score

def lcm(a, b):
    return a * b // math.gcd(a, b)


def normalise_divisions(part, D):
    div = 1
    for m in part.findall('measure'):
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
                e.find('divisions').text = str(D)
            for d in ([e.find('duration')] if e.tag in ('note', 'backup', 'forward') else []) + \
                     ([e.find('offset')] if e.tag in ('direction', 'harmony') else []):
                if d is not None and d.text:
                    d.text = str(int(Fr(int(float(d.text)) * D, div)))


def set_child(note, tag, text):
    old = note.find(tag)
    if old is not None:
        old.text = text
        return
    new = etree.Element(tag)
    new.text = text
    idx = NOTE_ORDER.index(tag)
    at = len(note)
    for i, c in enumerate(note):
        if c.tag in NOTE_ORDER and NOTE_ORDER.index(c.tag) > idx:
            at = i
            break
    note.insert(at, new)


def strip(note, *tags):
    for t in tags:
        for c in note.findall(t):
            note.remove(c)


def bar_events(notes, mi):
    return [n for n in notes if n['mi'] == mi]


def mergeable(eu, el):
    if len(eu) != len(el) or not eu:
        return False
    for a, b in zip(eu, el):
        if a['chord'] or b['chord'] or a['grace'] or b['grace'] or a['voice'] != '1' or b['voice'] != '1':
            return False
        for k in ('rel', 'dur', 'rest', 'type', 'dots', 'tie_start', 'tie_stop', 'lyric', 'tmod'):
            if a[k] != b[k]:
                return False
        if not a['rest'] and (a['midi'] is None or b['midi'] is None or b['midi'] > a['midi']):
            return False          # crossed parts are never chorded (SKILL.md 7.6)
    return True


def build_pair(up, lo, nu, nl, pid, name, abbr, owners, syl_holder):
    """Write parts `up` and `lo` onto one staff; return the new <part>.
    owners[note id] -> set of part indices sounding that notehead;
    syl_holder[(part, note id)] -> note id whose printed syllable that part reads."""
    D = 1
    for p in (up, lo):
        for d in p.iter('divisions'):
            D = lcm(D, int(d.text))
    normalise_divisions(up, D)
    normalise_divisions(lo, D)
    mu, ml = up.findall('measure'), lo.findall('measure')
    lo_el = {e.get('id'): e for e in lo.iter('note')}
    if len(mu) != len(ml):
        sys.exit(f'{name}: the two parts have {len(mu)} and {len(ml)} bars; cannot share a staff')
    pu, pl = nu[0]['part'] if nu else None, nl[0]['part'] if nl else None
    ev = [(bar_events(nu, i), bar_events(nl, i)) for i in range(len(mu))]
    merged = [mergeable(a, b) for a, b in ev]
    changed = True
    while changed:                            # a tie never changes voice
        changed = False
        for i, (a, b) in enumerate(ev):
            if not merged[i]:
                continue
            firsts = [x[0] for x in (a, b) if x]
            lasts = [x[-1] for x in (a, b) if x]
            if (i > 0 and not merged[i - 1] and any(n['tie_stop'] for n in firsts)) or \
               (i + 1 < len(ev) and not merged[i + 1] and any(n['tie_start'] for n in lasts)):
                merged[i] = False
                changed = True
    part = etree.Element('part', id=pid)
    lo_clef = None
    # a lower-voice extender runs on to the next syllable-less note in its voice, and 7.4 moves the
    # lower part's words to line 1 where both sing them: end it on its last held note (SKILL.md 7.6,
    # Verovio only)
    line2 = {'open': False, 'last': None, 'num': '2'}
    up_el = {e.get('id'): e for e in up.iter('note')}

    def extends(el):
        return any(ly.find('extend') is not None and ly.find('extend').get('type') != 'stop'
                   for ly in el.findall('lyric'))

    def close_line2():
        if line2['open'] and line2['last'] is not None:
            ly = etree.SubElement(line2['last'], 'lyric', number=line2['num'])
            etree.SubElement(ly, 'extend', type='stop')
        line2['open'], line2['last'] = False, None
    for i, (mU, mL) in enumerate(zip(mu, ml)):
        a, b = ev[i]
        m = etree.SubElement(part, 'measure', {k: v for k, v in mU.attrib.items() if k != 'width'})
        la = mL.find('attributes')
        if la is not None and la.find('clef') is not None:
            lo_clef = copy.deepcopy(la.find('clef'))
            lo_clef.attrib.pop('number', None)
        clef_due = la is not None and la.find('clef') is not None
        # one line only for the same words at the same moments: a staggered entrance needs its own
        # copy under its own note (SKILL.md 7.4)
        sa = [(n['rel'], n['lyric']) for n in a if n['lyric']]
        sb = [(n['rel'], n['lyric']) for n in b if n['lyric']]
        same_words = sa == sb
        # which printed syllable each part reads in this bar
        ha = [n['id'] for n in a if n['lyric']]
        hb = [n['id'] for n in b if n['lyric']]
        for h in ha:
            syl_holder[(pu, h)] = h
        # one line for both, but where only the lower part holds a syllable over more notes, print
        # its copy, with the extender (SKILL.md 7.4): the upper part reads it from there
        take = set()
        if same_words and not merged[i]:
            take = {y for x, y in zip(ha, hb) if extends(lo_el[y]) and not extends(up_el[x])}
        if merged[i] or same_words:
            for x, y in zip(ha, hb):
                if y in take:
                    syl_holder[(pu, x)] = y
                    syl_holder[(pl, y)] = y
                else:
                    syl_holder[(pl, y)] = x
        else:
            for y in hb:
                syl_holder[(pl, y)] = y
        taken_up = {x for x, y in zip(ha, hb) if y in take}
        partner = {x['id']: y for x, y in zip(a, b)} if merged[i] else {}
        t = Fr(0)
        placed_clef = False
        for e in mU:
            if e.tag == 'print':
                continue
            c = copy.deepcopy(e)
            if e.tag == 'attributes':
                for cl in c.findall('clef'):
                    c.remove(cl)
                if clef_due and lo_clef is not None and not placed_clef:
                    idx = len(c)
                    for j, ch in enumerate(c):
                        if ch.tag in ('staff-details', 'transpose', 'directive', 'measure-style', 'for-part'):
                            idx = j
                            break
                    c.insert(idx, copy.deepcopy(lo_clef))
                    placed_clef = True
                m.append(c)
                continue
            if e.tag != 'note':
                if e.tag in ('backup', 'forward'):
                    q = int(e.findtext('duration'))
                    t += q if e.tag == 'forward' else -q
                m.append(c)
                continue
            if c.find('chord') is None and c.find('grace') is None:
                t += int(c.findtext('duration') or 0)
            n_id = c.get('id')
            owners.setdefault(n_id, set()).add(pu)
            if n_id in taken_up:
                strip(c, 'lyric')
            if merged[i]:
                set_child(c, 'voice', '1')
                m.append(c)
                y = partner.get(n_id)
                if y is not None and not y['rest']:
                    if y['midi'] == midi(e):
                        owners[n_id].add(pl)                    # unison: one notehead, both parts
                    else:
                        lc = copy.deepcopy(lo_el[y['id']])
                        strip(lc, 'lyric', 'beam', 'stem')
                        nots = lc.find('notations')
                        if nots is not None:
                            for ch in list(nots):
                                if ch.tag != 'tied':
                                    nots.remove(ch)
                        lc.insert(0, etree.Element('chord'))
                        set_child(lc, 'voice', '1')
                        m.append(lc)
                        owners.setdefault(lc.get('id'), set()).add(pl)
                elif y is not None:
                    owners[n_id].add(pl)                        # the shared rest
            else:
                set_child(c, 'voice', str(2 * int(c.findtext('voice') or 1) - 1))
                if c.find('rest') is None:
                    set_child(c, 'stem', 'up')
                m.append(c)
        if clef_due and lo_clef is not None and not placed_clef:
            at = etree.Element('attributes')
            at.append(copy.deepcopy(lo_clef))
            m.insert(0, at)
        if merged[i]:
            if hb:
                close_line2()
            continue
        if t:
            bk = etree.SubElement(m, 'backup')
            etree.SubElement(bk, 'duration').text = str(t)
        # where both voices rest at the same moment for the same time, one rest is printed, lit
        # for both parts: two stacked copies of every rest read as clutter
        up_rests = {(x['rel'], x['dur']): x['id'] for x in a if x['rest'] and not x['chord']}
        for e in mL:
            if e.tag not in ('note', 'backup', 'forward'):
                continue
            c = copy.deepcopy(e)
            if e.tag == 'note':
                owners.setdefault(c.get('id'), set()).add(pl)
                me = next((x for x in b if x['id'] == c.get('id')), None)
                if me is not None and me['rest'] and (me['rel'], me['dur']) in up_rests:
                    c.set('print-object', 'no')
                    owners.setdefault(up_rests[(me['rel'], me['dur'])], set()).add(pl)
                set_child(c, 'voice', str(2 * int(c.findtext('voice') or 1)))
                if c.find('rest') is None:
                    set_child(c, 'stem', 'down')
                lys = c.findall('lyric')
                num = '1' if c.get('id') in take else '2'
                if lys and ((same_words and num == '2') or line2['num'] != num):
                    close_line2()                   # its words are printed on the other line from here
                for j, ly in enumerate(sorted(lys, key=lambda l: int(re.sub(r'\D', '', l.get('number') or '1') or 1))):
                    if (same_words and num == '2') or j > 0:
                        c.remove(ly)
                    else:
                        ly.set('number', num)
                        ly.attrib.pop('placement', None)
                        ly.attrib.pop('default-y', None)
                        ext = ly.find('extend')
                        line2['open'] = ext is not None and ext.get('type') != 'stop'
                        line2['last'], line2['num'] = None, num
                if not lys and c.find('rest') is None and c.find('chord') is None and line2['open']:
                    line2['last'] = c
            m.append(c)
    return part, sum(merged), len(merged)


ACC = {-2: 'flat-flat', -1: 'flat', 0: 'natural', 1: 'sharp', 2: 'double-sharp'}
ACC_AFTER = ('type', 'dot', 'voice', 'instrument', 'footnote', 'level', 'unpitched', 'pitch', 'rest', 'chord',
             'grace', 'cue', 'duration', 'tie')


def mark_accidentals(root):
    """Verovio prints only the accidentals a MusicXML writes as <accidental>; it does not work them
    out from <alter>, and a file that leaves them to the reader (Sibelius does) shows B-flat for
    B-natural (SKILL.md 8.1). Write the ones the score needs: per staff, both voices together,
    against the key signature and what earlier notes in the bar have already altered; a note tied
    over from the last bar shows none. Returns how many were added."""
    added = 0
    for part in root.findall('part'):
        fifths, div = 0, 1
        for m in part.findall('measure'):
            key = {}
            for e in m:
                if e.tag == 'attributes':
                    if e.find('key/fifths') is not None:
                        fifths = int(e.findtext('key/fifths'))
                    if e.find('divisions') is not None:
                        div = int(e.findtext('divisions'))
            order = 'FCGDAEB' if fifths >= 0 else 'BEADGCF'
            key = {st: (1 if fifths > 0 else -1) for st in order[:abs(fifths)]}
            evs, t, k = [], Fr(0), 0
            for e in m:
                if e.tag == 'backup':
                    t -= Fr(int(e.findtext('duration')), div)
                elif e.tag == 'forward':
                    t += Fr(int(e.findtext('duration')), div)
                elif e.tag == 'note':
                    on = evs[-1][0] if (e.find('chord') is not None and evs) else t
                    evs.append((on, k, e))
                    k += 1
                    if e.find('chord') is None and e.find('grace') is None:
                        t += Fr(int(e.findtext('duration') or 0), div)
            state = {}
            for _, _, n in sorted(evs, key=lambda x: (x[0], x[1])):
                p = n.find('pitch')
                if p is None:
                    continue
                st, octv = p.findtext('step'), p.findtext('octave')
                alt = int(float(p.findtext('alter') or 0))
                held = any(x.get('type') == 'stop' for x in n.findall('tie'))
                have = n.find('accidental')
                now = state.get((st, octv), key.get(st, 0))
                if have is not None:
                    state[(st, octv)] = alt
                    continue
                if held or alt == now or alt not in ACC:
                    if not held:
                        state[(st, octv)] = alt
                    continue
                acc = etree.Element('accidental')
                acc.text = ACC[alt]
                at = 0
                for j, ch in enumerate(n):
                    if ch.tag in ACC_AFTER:
                        at = j + 1
                n.insert(at, acc)
                state[(st, octv)] = alt
                added += 1
    return added


MEI_ACC = {'s': 1, 'f': -1, 'n': 0, 'x': 2, 'ss': 2, 'ff': -2, 'ns': 1, 'nf': -1}


def pitch_readback(tk):
    """Every note as a singer would read it off the page Verovio draws, against the pitch it
    plays: written accidentals, else the key signature and what earlier notes in the bar on that
    staff have altered. Returns [(bar, staff, note name, reads, sounds)] where they differ."""
    M = '{http://www.music-encoding.org/ns/mei}'
    X = '{http://www.w3.org/XML/1998/namespace}id'
    root = etree.fromstring(tk.getMEI().encode())
    q = {}
    for ev in tk.renderToTimemap():
        for i in ev.get('on', []):
            q.setdefault(i, ev['qstamp'])
    key, bad = {}, []
    held = {t.get('endid', '').lstrip('#') for t in root.iter(M + 'tie')}   # tied over: reads as its first note

    def setkey(el, n=None):
        sig = el.get('keysig') or next((k.get('sig') for k in el.iter(M + 'keySig')), None)
        if sig is None:
            return
        d = {}
        if sig not in ('0', 'mixed'):
            k, a = int(sig[:-1]), (1 if sig[-1] == 's' else -1)
            d = {st: a for st in ('fcgdaeb' if a > 0 else 'beadgcf')[:k]}
        if n is None:
            for s_ in list(key) or ['*']:
                key[s_] = d
            key['*'] = d
        else:
            key[n] = d
    for el in root.iter(M + 'scoreDef', M + 'staffDef', M + 'measure'):
        if el.tag == M + 'scoreDef':
            setkey(el)
        elif el.tag == M + 'staffDef':
            setkey(el, el.get('n'))
        else:
            for st in el.findall(M + 'staff'):
                n = st.get('n')
                kd = key.get(n, key.get('*', {}))
                notes = [(q.get(nt.get(X)), k, nt) for k, nt in enumerate(st.iter(M + 'note'))
                         if nt.get(X) not in held and nt.get('tie') not in ('m', 't')]
                state = {}
                for qs, _, nt in sorted((x for x in notes if x[0] is not None), key=lambda x: (x[0], x[1])):
                    pn, oc = nt.get('pname'), nt.get('oct')
                    w = nt.get('accid') or next((a.get('accid') for a in nt.findall(M + 'accid') if a.get('accid')), None)
                    g = nt.get('accid.ges') or next((a.get('accid.ges') for a in nt.findall(M + 'accid') if a.get('accid.ges')), None)
                    sounds = MEI_ACC.get(g, MEI_ACC.get(w, 0)) if (g or w) else 0
                    reads = MEI_ACC[w] if w in MEI_ACC else state.get((pn, oc), kd.get(pn, 0))
                    state[(pn, oc)] = reads
                    if reads != sounds:
                        nm = lambda a: pn.upper() + {-2: 'bb', -1: 'b', 0: '', 1: '#', 2: '##'}[a] + oc
                        bad.append((el.get('n'), n, nm(sounds), nm(reads), nm(sounds)))
    return bad


def mark_tuplets(root):
    """Notes timed as tuplets (<time-modification>) but with no <tuplet> marking print with no
    bracket or number, so a triplet looks like a misprint. Group each voice's run of them into
    tuplets (a group is complete when it fills its normal notes' worth) and mark the ends.
    Returns how many groups were marked."""
    count = 0
    for part in root.findall('part'):
        for m in part.findall('measure'):
            notes = [e for e in m if e.tag == 'note' and e.find('chord') is None and e.find('grace') is None]
            if any(e.find('.//tuplet') is not None for e in notes):
                continue
            by_voice = {}
            for e in notes:
                by_voice.setdefault((e.findtext('voice') or '1', e.findtext('staff') or '1'), []).append(e)
            for vs in by_voice.values():
                group, total, need = [], 0, None
                for e in vs + [None]:
                    tm = e.find('time-modification') if e is not None else None
                    if tm is None:
                        group, total, need = [], 0, None
                        continue
                    act, nor = int(tm.findtext('actual-notes') or 3), int(tm.findtext('normal-notes') or 2)
                    d = int(e.findtext('duration') or 0)
                    if not group:
                        need = Fr(nor) * Fr(d * act, nor)       # the group's length: nor normal notes
                    group.append(e)
                    total += d
                    if total >= need:
                        if total == need and len(group) > 1:
                            for el, kind in ((group[0], 'start'), (group[-1], 'stop')):
                                nots = el.find('notations')
                                if nots is None:
                                    nots = etree.Element('notations')
                                    at = len(el)
                                    for i2, ch in enumerate(el):
                                        if ch.tag in ('lyric', 'play', 'listen'):
                                            at = i2
                                            break
                                    el.insert(at, nots)
                                t = etree.SubElement(nots, 'tuplet', type=kind)
                                if kind == 'start':
                                    t.set('bracket', 'yes')
                            count += 1
                        group, total, need = [], 0, None
    return count


def default_pairs(names, sung):
    order = [i for i in range(len(names)) if i in sung and not names[i].lower().startswith('solo')]
    return [tuple(order[k:k + 2]) for k in range(0, len(order) - 1, 2)]


def display_score(root, parts, notes_by_part, pairs, sung):
    """Return (display root, owners, syl_holder, staff names)."""
    owners, syl_holder = {}, {}
    pl = root.find('part-list')
    sps = {sp.get('id'): sp for sp in pl.findall('score-part')}
    names = [(sps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in parts]
    abbrs = [(sps[p.get('id')].findtext('part-abbreviation') or '').strip() for p in parts]
    pair_of = {}
    for a, b in pairs:
        pair_of[a] = (a, b)
        pair_of[b] = None
    out = etree.Element('score-partwise', version='4.0')
    new_pl = etree.SubElement(out, 'part-list')
    for i, p in enumerate(parts):
        if i in pair_of and pair_of[i] is None:
            continue
        if i in pair_of:
            a, b = pair_of[i]
            pid = f'PX{a}'
            nm = f'{names[a]}\n{names[b]}'
            ab = f'{abbrs[a] or names[a]}\n{abbrs[b] or names[b]}'
            newp, nmerged, nbars = build_pair(copy.deepcopy(parts[a]), copy.deepcopy(parts[b]),
                                              notes_by_part[a], notes_by_part[b], pid, nm, ab, owners, syl_holder)
            # the copies carry the ids given by scan_part, and the notes' 'el' point at the originals;
            # re-link merged chord partners' ids is not needed: ids are attributes, copied verbatim
            print(f'   staff "{names[a]} + {names[b]}": {nmerged} of {nbars} bars as chords, the rest divided')
            sp = etree.SubElement(new_pl, 'score-part', id=pid)
            etree.SubElement(sp, 'part-name').text = nm
            etree.SubElement(sp, 'part-abbreviation').text = ab
            out.append(newp)
        else:
            sp = copy.deepcopy(sps[p.get('id')])
            new_pl.append(sp)
            c = copy.deepcopy(p)
            for pr in c.iter('print'):
                pr.getparent().remove(pr)
            out.append(c)
            if i in sung:
                for n in notes_by_part[i]:
                    owners.setdefault(n['id'], set()).add(i)
                    if n['lyric']:
                        syl_holder[(i, n['id'])] = n['id']
    return out, owners, syl_holder


# ----------------------------------------------------------------------------- audio and timing

def decode(path, sr=22050):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ac', '1', '-ar', str(sr),
                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def audio_onsets(x, sr=22050, n=1024, hop=128):
    """Spectral-flux onsets (seconds)."""
    win = np.hanning(n).astype(np.float32)
    nfr = 1 + max(0, (len(x) - n) // hop)
    prev, flux = None, np.zeros(nfr, np.float32)
    for c0 in range(0, nfr, 4096):
        c1 = min(nfr, c0 + 4096)
        idx = np.arange(c0, c1)[:, None] * hop + np.arange(n)[None, :]
        L = np.log1p(100 * np.abs(np.fft.rfft(x[idx] * win, axis=1))).astype(np.float32)
        if prev is not None:
            L = np.vstack([prev[None], L])
            d = np.maximum(0, np.diff(L, axis=0)).sum(1)
            flux[c0:c1] = d
        else:
            d = np.maximum(0, np.diff(L, axis=0)).sum(1)
            flux[c0 + 1:c1] = d
        prev = L[-1]
    k = int(0.4 * sr / hop)
    pad = np.pad(flux, k, mode='edge')
    from numpy.lib.stride_tricks import sliding_window_view
    med = np.median(sliding_window_view(pad, 2 * k + 1), axis=1)[:nfr]
    thr = med + 0.25 * np.percentile(flux, 95)
    w = 4
    padm = np.pad(flux, w, mode='constant')
    mx = sliding_window_view(padm, 2 * w + 1).max(1)[:nfr]
    peaks = np.flatnonzero((flux >= mx) & (flux > thr))
    t = (peaks * hop + n / 2) / sr
    keep, last = [], -1
    for v in t:
        if v - last > 0.05:
            keep.append(v)
            last = v
    return np.array(keep)


HOP_C = 0.05          # seconds per chroma frame


def chroma_audio(x, sr=22050):
    """Pitch-class profile of the audio every HOP_C s (55 Hz - 2 kHz, log magnitude)."""
    n, h = 4096, int(sr * HOP_C)
    nfr = max(0, (len(x) - n) // h)
    f = np.fft.rfftfreq(n, 1 / sr)
    sel = (f > 55) & (f < 2000)
    pc = ((np.round(12 * np.log2(f[sel] / 440)) + 9) % 12).astype(int)
    M = np.zeros((12, sel.sum()), np.float32)
    M[pc, np.arange(sel.sum())] = 1
    win = np.hanning(n).astype(np.float32)
    A = np.zeros((nfr, 12), np.float32)
    for c0 in range(0, nfr, 1000):
        idx = np.arange(c0, min(nfr, c0 + 1000))[:, None] * h + np.arange(n)[None, :]
        A[c0:c0 + len(idx)] = np.log1p(1000 * np.abs(np.fft.rfft(x[idx] * win, axis=1))[:, sel]) @ M.T
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)


def chroma_score(notes, to_audio, nfr):
    """The same profile built from the score's notes (with a little of each note's fifth and third,
    as a voice's overtones put there), placed on the audio timeline by `to_audio`."""
    S = np.zeros((nfr, 12), np.float32)
    for a, b, m in notes:
        i0 = int(to_audio(a) / HOP_C)
        i1 = max(i0 + 1, int(to_audio(b) / HOP_C))
        for hh, w in ((0, 1.0), (7, 0.35), (4, 0.15)):
            S[max(i0, 0):min(i1, nfr), (m + hh) % 12] += w
    return S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-9)


def dtw_offset(A, S, band):
    """Dynamic time warping of the score's profile S against the audio's A, within +-band frames of
    the straight line. Returns, per frame of S, how far (s) the audio has it from the straight line."""
    n = min(len(A), len(S))
    W = 2 * band + 1
    D = np.full(W, np.inf)
    P = np.zeros((n, W), np.int8)
    ks = np.arange(W)
    for i in range(n):
        c = 1.0 - A[np.clip(i + ks - band, 0, len(A) - 1)] @ S[i]
        if i == 0:
            row = c.copy()
        else:
            up = np.append(D[1:], np.inf)        # the audio holds while the score moves on
            best = np.minimum(D, up)
            P[i] = np.where(D <= up, 0, 1)
            row = c + best
        for k in range(1, W):                    # the audio moves on while the score holds
            v = row[k - 1] + c[k]
            if v < row[k]:
                row[k] = v
                P[i, k] = 2
        D = row
    k, i, off = int(np.argmin(D)), n - 1, np.zeros(n)
    seen = np.zeros(n, bool)
    while i > 0:
        if not seen[i]:
            off[i], seen[i] = (k - band) * HOP_C, True
        p = P[i, k]
        if p == 0:
            i -= 1
        elif p == 1:
            i, k = i - 1, k + 1
        else:
            k -= 1
    return off


class Timing:
    """Score seconds -> audio seconds.

    Anchored as stem_vs_score.py does it: the offset from where the audio first sounds against the
    score's first note, only the tempo refined on onsets. Then re-anchored after every fermata:
    playback holds a fermata longer than written, by an amount the file does not say (Sibelius
    held the two-soloist TTBB's by 0.25 s and 0.45 s), and everything after it runs that much
    late. The hold is measured by aligning the score's pitch content with the audio's (chroma,
    dynamic time warping), which a steady groove cannot fool, and refined to the millisecond on
    the onsets of the stretch that follows."""

    def __init__(self, mp3, notes, first_score, breaks):
        self.x = decode(mp3)
        self.dur = len(self.x) / 22050
        env = envelope(mp3, -50.0)
        sounding = [r for r in runs(env) if r[1] - r[0] >= 0.3]
        if not sounding:
            sys.exit(f'{mp3}: no sound above -50 dBFS')
        self.first_audio = sounding[0][0]
        self.last_audio = sounding[-1][1]
        self.off = self.first_audio - first_score           # anchored at the first entrance
        self.aon = audio_onsets(self.x)
        so = np.array(sorted(set(round(a, 3) for a, _, _ in notes)))
        self.so = so
        self.fit_tempo(so)
        self.breaks = np.array(sorted(breaks))
        self.cum = np.zeros(len(self.breaks) + 1)
        A = chroma_audio(self.x)
        self.A, self.notes = A, notes
        self.fit_holds(A, notes, so)
        # the first entrance can be too quiet to trip the level threshold (a predominant mix with
        # the entering voice 21 dB down started 0.1 s late): the pitch alignment of the first
        # stretch overrules the anchor when they disagree by a frame or more
        self.moved = 0.0
        if abs(self.base) >= 0.03:
            self.moved, self.off = self.base, self.off + self.base
            self.fit_tempo(so)
            self.fit_holds(A, notes, so)
        # then the tempo and every hold together, by least squares on the onsets each lands near:
        # fitted one after the other, a hold left in the tempo spreads over the whole piece (a
        # 0.6 s hold measured 0.49 s), and the tempo refitted round the holds overshoots
        if len(self.breaks):
            for win in (0.15, 0.1, 0.06):
                H = (so[:, None] >= self.breaks[None, :]).astype(float)
                g = self(so)
                ok, near = self.nearest(g, win)
                if ok.sum() < len(self.breaks) + 8:
                    break
                X = np.column_stack([so, H])[ok]
                sol = np.linalg.lstsq(X, near[ok] - self.off, rcond=None)[0]
                self.scale = float(np.clip(sol[0], 0.9, 1.1))
                self.steps = [float(v) for v in sol[1:]]     # one column per fermata: its hold
                self.cum = np.concatenate([[0.0], np.cumsum(self.steps)])
            # the check in the report is against a pitch alignment on the final straight line
            self.dtw = dtw_offset(A, chroma_score(notes, self.straight, len(A)), band=int(3.0 / HOP_C))

    def fit_tempo(self, so):
        scale = 1.0
        for win in (0.5, 0.3, 0.15):                         # refine the tempo only; the anchor stays put
            g = self.off + scale * so
            ok, near = self.nearest(g, win)
            if ok.sum() >= 8:
                X, Y = so[ok], near[ok] - self.off
                scale = float(np.clip(np.dot(X, Y) / max(np.dot(X, X), 1e-9), 0.9, 1.1))
        self.scale = scale

    def fit_holds(self, A, notes, so):
        """One offset per stretch between fermatas: coarse from the pitch alignment, fine from onsets."""
        S = chroma_score(notes, self.straight, len(A))
        self.dtw = dtw_offset(A, S, band=int(3.0 / HOP_C))
        edges = [-1e9] + list(self.breaks) + [1e9]
        # the alignment's own ends are loose: judge from 5 s in to 5 s before the last written note
        self.lo = 5.0
        self.hi = min(self.dur, float(self.straight(max(b for _, b, _ in notes)))) - 5.0
        lo, hi = self.lo, self.hi
        seg = []
        for a, b in zip(edges[:-1], edges[1:]):
            t0, t1 = max(float(self.straight(a)) + 1.0, lo), min(float(self.straight(b)) - 1.0, hi)
            if t1 - t0 < 2.0:
                seg.append(None)
                continue
            coarse = float(np.median(self.dtw[int(t0 / HOP_C):int(t1 / HOP_C)]))
            inside = so[(so >= a) & (so < b)]
            g = self.straight(inside) + coarse
            g = g[(g > t0) & (g < t1)]
            ok, near = self.nearest(g, 0.1)
            if ok.sum() >= 6:
                seg.append(coarse + float(np.median(near[ok] - g[ok])))
            elif len(inside) and seg and a > -1e8:
                # too few onsets to refine, and held chords leave the pitch alignment free to slide
                # (a ballad's last three bars, one chord: -1.1 s where playback held +0.75 s): after
                # a fermata the sound comes back with the next note, so take the first onset after it
                # (a hold is never negative: an onset before the written end is the held note's own)
                prev = seg[-1] if seg[-1] is not None else 0.0
                g0 = float(self.straight(inside.min()))
                later = self.aon[(self.aon > g0 + prev - 0.03) & (self.aon < g0 + prev + 3.0)]
                seg.append(float(later[0]) - g0 if len(later) else coarse)
            else:
                seg.append(coarse)
        base = seg[0] if seg[0] is not None else 0.0
        self.base = base
        self.steps, prev = [], base
        for v in seg[1:]:
            v = prev if v is None else v
            self.steps.append(v - prev)
            prev = v
        self.cum = np.concatenate([[0.0], np.cumsum(self.steps)])

    def nearest(self, g, win):
        g = np.asarray(g, float)
        if not len(g) or len(self.aon) < 2:
            return np.zeros(len(g), bool), g
        k = np.clip(np.searchsorted(self.aon, g), 1, len(self.aon) - 1)
        near = np.where(np.abs(self.aon[k - 1] - g) < np.abs(self.aon[k] - g), self.aon[k - 1], self.aon[k])
        return np.abs(near - g) < win, near

    def straight(self, s):
        return self.off + self.scale * np.asarray(s, float)

    def __call__(self, s):
        s = np.asarray(s, float)
        return self.straight(s) + self.cum[np.searchsorted(self.breaks, s, side='right')]

    def report(self, bar_at, label, seg=15.0):
        fmt = lambda t: (lambda r: f'{int(r // 60)}:{r % 60:04.1f}')(round(t, 1))
        print(f'\n{label}')
        print(f'   anchor: audio first sounds at {fmt(self.first_audio)}; audio = {self.off:+.3f} s + '
              f'{self.scale:.4f} x score time')
        if self.moved:
            print(f'   (moved {1000 * self.moved:+.0f} ms from where the audio first sounds, to agree with the '
                  f'pitch alignment of the opening)')
        for b, d in zip(self.breaks, self.steps):
            if b >= self.so.max() - 1e-6:
                print(f'   fermata ending at {fmt(float(self.straight(b)))}: the last; nothing after it to re-anchor, '
                      f'and the last notes stay lit until the sound stops at {fmt(self.last_audio)}')
                continue
            print(f'   fermata ending at {fmt(float(self.straight(b)))} (bar {bar_at(float(self(b)))}): playback '
                  f'holds it {1000 * d:+.0f} ms beyond the written length; the lights after it follow')
            if d < -0.1:
                print(f'   <- a hold cannot be negative: the fit is wrong here; check the lights after bar '
                      f'{bar_at(float(self(b)))} by eye')
        # the check: the pitch alignment against the lights, per stretch. Aligned around the lights
        # themselves, not around the straight line: the alignment only looks +-3 s either side, and
        # after a few long holds the lights can be further than that from the straight line (a TTBB
        # with piano: 3.5 s by bar 52), where it locks on to the wrong bar of a repeated figure
        err = dtw_offset(self.A, chroma_score(self.notes, self, len(self.A)), band=int(3.0 / HOP_C))
        t = np.arange(len(err)) * HOP_C
        rows = []
        for a in np.arange(self.lo, self.hi, seg):
            sel = (t >= a) & (t < min(a + seg, self.hi))
            if sel.sum() > 20:
                rows.append((a, float(np.median(err[sel]))))
        g = self(self.so)
        ok, near = self.nearest(g, 0.1)
        r = (near - g)[ok]
        print(f'   check against the pitch alignment, per {seg:.0f} s (to its {1000 * HOP_C:.0f} ms step): ' +
              '  '.join(f'{fmt(a)} {1000 * m:+.0f}' for a, m in rows))
        bad = [(a, m) for a, m in rows if abs(m) >= 0.1]
        for a, m in bad:
            print(f'   <- the lights are {1000 * abs(m):.0f} ms {"ahead of" if m > 0 else "behind"} the audio around '
                  f'{fmt(a)} (bar {bar_at(a)}), with no fermata to explain it')
        if not bad:
            print('   every stretch within 100 ms of the pitch alignment')
        if len(r):
            print(f'   onsets within 100 ms of a light: {len(r)} of {len(g)}; median {1000 * np.median(r):+.0f} ms '
                  f'(positive = the sound comes after the light)')


# ----------------------------------------------------------------------------- rendering

def install_smufl_font():
    """cairosvg ignores @font-face, so Verovio's text glyphs (the note in a metronome mark,
    chord-symbol accidentals) print as boxes unless Leipzig is installed for fontconfig
    (SKILL.md 8.4). Needs fonttools and brotli; without them the boxes stay."""
    import verovio, base64
    # fontconfig reads ~/.fonts; cairo on a Mac finds fonts through the system, in ~/Library/Fonts
    dest = os.path.expanduser('~/Library/Fonts/Leipzig.ttf' if sys.platform == 'darwin' else '~/.fonts/Leipzig.ttf')
    if os.path.exists(dest):
        return
    try:
        from fontTools.ttLib import TTFont
        css = open(os.path.join(os.path.dirname(verovio.__file__), 'data', 'Leipzig.css')).read()
        f = TTFont(io.BytesIO(base64.b64decode(re.search(r'base64,([A-Za-z0-9+/=]+)', css).group(1))))
        f.flavor = None
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        subprocess.run(['fc-cache', '-f'], check=False, capture_output=True)
    except Exception as e:                                   # a box in a tempo mark is not fatal
        print(f'note: could not install the Leipzig font ({e}); metronome marks may show a box')


def render_png(svg_bytes, W, H):
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=svg_bytes, output_width=W, output_height=H, background_color='white')
    return np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))


_LYRIC_FONT = []


def _lyric_width(text, size):
    """The printed width of a syllable, in the SVG's units: measured in the serif font cairo
    draws Verovio's "Times, serif" with, or estimated when that cannot be found."""
    if not _LYRIC_FONT:
        try:
            from PIL import ImageFont
            path = subprocess.run(['fc-match', '-f', '%{file}', 'Times'], capture_output=True,
                                  text=True).stdout.strip()
            _LYRIC_FONT.append(ImageFont.truetype(path, 400) if path else None)
        except Exception:
            _LYRIC_FONT.append(None)
    f = _LYRIC_FONT[0]
    if f is None:
        return sum(size * (0.30 if c in "ijltfr.,'’ " else 0.56) for c in text)
    return f.getlength(text) * size / 400


def nudge_syllables(syls, ns):
    """Verovio spaces a line's syllables apart only within one layer, so where the words on one
    line come from two voices (the upper part's chord, then the lower part's own note) the next
    bar's first syllable can print over the last one. Move each such syllable right until it
    clears its neighbour by a space's width, as an engraver would, and shorten its line to match."""
    rows = {}
    for g in syls:
        if 'spanning' in (g.get('class') or ''):
            continue
        t = g.find(ns + 'text')
        inner = [x for x in g.iter(ns + 'tspan') if x.get('font-size')]
        if t is None or not inner or t.get('x') is None:
            continue
        txt = ''.join(t.itertext()).strip()
        if not txt:
            continue
        size = float(inner[-1].get('font-size').rstrip('px'))
        rows.setdefault(t.get('y'), []).append([float(t.get('x')), txt, size, g, t])
    moved = 0
    for row in rows.values():
        row.sort(key=lambda r: r[0])
        for prev, cur in zip(row, row[1:]):
            need = prev[0] + _lyric_width(prev[1], prev[2]) + 0.15 * prev[2]
            if cur[0] < need:
                dx = need - cur[0]
                cur[0] = need
                cur[4].set('x', f'{need:.0f}')
                for r_ in cur[3].findall(ns + 'rect'):          # its own line or hyphen moves with it
                    x0, w0 = float(r_.get('x')), float(r_.get('width'))
                    r_.set('x', f'{x0 + dx:.0f}')
                    if w0 - dx > 0.5 * cur[2]:            # a line ends where it did; a hyphen keeps its length
                        r_.set('width', f'{w0 - dx:.0f}')
                moved += 1
    return moved


class Page:
    """One rendered page: base images per view, and every lightable element's pixels."""

    def __init__(self, svg, W, H, owners, syl_holder, colours, views, names, label_px, times, bar_end, ctrl):
        self.W, self.H, self.names, self.label_px = W, H, names, label_px
        root = etree.fromstring(svg.encode())
        ns = '{http://www.w3.org/2000/svg}'
        self.root = root
        cls = lambda e: (e.get('class') or '').split()
        # SVG drawing units -> pixels, for noteheads placed straight from the SVG
        inner = root.find(ns + 'svg')
        vb = [float(v) for v in inner.get('viewBox').split()]
        kx, ky = W / vb[2], H / vb[3]
        pm = next(g for g in inner.iter(ns + 'g') if 'page-margin' in cls(g))
        mx, my = (float(v) for v in re.findall(r'-?[\d.]+', pm.get('transform'))[:2])
        notes, syls, rests = [], [], []
        self.ctrl, self.ctrl_g = ctrl, []
        for g in root.iter(ns + 'g'):
            c = cls(g)
            if 'note' in c and g.get('id') in owners:
                notes.append(g)
            elif ('rest' in c or 'mRest' in c) and g.get('id') in owners:
                rests.append(g)
            elif 'syl' in c:
                syls.append(g)
            elif 'tie' in c or 'slur' in c or 'fermata' in c:
                # a tie or slur carried over a system break is drawn again at the next system's
                # start with no id, naming the original in a class "id-<its id>"
                cid = g.get('id') or next((x[3:] for x in c if x.startswith('id-')), None)
                if cid in ctrl:
                    self.ctrl_g.append((cid, g))
        # elements: (kind, key, g); heads get their own entry for the halo
        self.elems = []
        self.heads = {}
        space = 180.0                     # a staff space in drawing units (Verovio's unit 9, x10)
        self.space_px = space * ky
        widths = {'E0A0': 2.0, 'E0A2': 1.69, 'E0A3': 1.18, 'E0A4': 1.18}
        for g in notes:
            head = next((h for h in g if 'notehead' in cls(h)), None)
            self.elems.append(('body', g.get('id'), g))
            if head is not None:
                self.elems.append(('head', g.get('id'), head))
                use = head.find(ns + 'use')
                if use is not None and use.get('transform'):
                    tx, ty = (float(v) for v in re.findall(r'-?[\d.]+', use.get('transform'))[:2])
                    href = use.get('{http://www.w3.org/1999/xlink}href') or ''
                    sc = float((re.findall(r'scale\(([\d.]+)', use.get('transform')) or ['0.72'])[0]) / 0.72
                    w = widths.get(href[1:5], 1.18) * space * sc
                    self.heads[g.get('id')] = ((tx + mx + w / 2) * kx, (ty + my) * ky,
                                               w / 2 * kx, space * sc / 2 * ky)
        for g in rests:
            self.elems.append(('rest', g.get('id'), g))
        for cid, g in self.ctrl_g:                     # a tie lights while either of its notes sounds
            if ctrl[cid][0] == 'tie':
                self.elems.append(('tie', f'{cid}#{len(self.elems)}', g))
        self.nudged = nudge_syllables(syls, ns)
        for s in syls:
            # an extender squeezed to a stub (the next note sits right under the word's end) would
            # read as a full stop after the word; a print has room for the line, this has not
            for r_ in s.findall(ns + 'rect'):
                if float(r_.get('width') or 0) < 0.6 * space:
                    s.remove(r_)
            if 'spanning' in cls(s):
                # an extender carried over a system break: Verovio draws the rest of the line at
                # the start of the next system, outside any note, naming its syllable only in a
                # class "id-<syllable's svg id>". It lights with that syllable, with a halo of its own
                ref = next((c[3:] for c in cls(s) if c.startswith('id-')), None)
                holder = _SYL_SVG.get(ref)
                if holder is not None:
                    self.elems.append(('sylx', f'{holder}#{len(self.elems)}', s))
                continue
            a = s.getparent()
            while a is not None and not ({'note', 'chord'} & set(cls(a))):
                a = a.getparent()
            if a is None:
                continue
            ids = [a.get('id')] if 'note' in cls(a) else [n.get('id') for n in a.iter(ns + 'g') if 'note' in cls(n)]
            vg = s.getparent()
            vn = next((c[2:] for c in cls(vg) if c.startswith('vn')), None) if vg is not None else None
            holder = next((k for i in ids for k in (f'{i}@{vn}', i) if k in _SYL_INDEX), None)
            if holder is None:
                continue
            self.elems.append(('syl', holder, s))
            _SYL_SVG[s.get('id')] = holder
        self.ids_on_page = {g.get('id') for g in root.iter(ns + 'g')
                            if {'note', 'rest', 'mRest'} & set(cls(g)) and g.get('id')}
        # score time -> x on each system, from every note and rest printed on it (any staff) and
        # its barlines: a rest's progress bar runs across what the other staves play meanwhile
        first_x = lambda e: next((float(re.findall(r'-?[\d.]+', u.get('transform'))[0])
                                  for u in e.iter(ns + 'use') if u.get('transform')), None)
        self.timemap, self.rest_bar = [], {}
        for si, sysg in enumerate(g for g in root.iter(ns + 'g') if 'system' in cls(g)):
            pts = []
            for m in (g for g in sysg.iter(ns + 'g') if 'measure' in cls(g)):
                mend = None
                for e in m.iter(ns + 'g'):
                    c, i = set(cls(e)), e.get('id')
                    if i not in bar_end or not ({'note', 'rest', 'mRest'} & c):
                        continue
                    mend = bar_end.get(i, mend)
                    if c & {'note', 'rest'} and i in times:
                        x = first_x(e)
                        if x is not None:
                            pts.append((times[i], (x + mx) * kx))
                # the bar's right barline: a bar opening with a repeat sign has its left one too
                bl = next((b for b in reversed(list(m)) if 'barLine' in cls(b)), None)
                d = bl.find(ns + 'path') if bl is not None else None
                if mend is not None and d is not None:
                    pts.append((mend, (float(re.findall(r'-?[\d.]+', d.get('d'))[0]) + mx) * kx))
            first = {}
            for t_, x_ in pts:                   # one x per time: the leftmost (a barline before
                first[round(t_, 4)] = min(x_, first.get(round(t_, 4), x_))   # the next bar's downbeat)
            ts = np.array(sorted(first)) if first else np.zeros(1)
            xs = np.maximum.accumulate(np.array([first[t_] for t_ in sorted(first)])) if first else np.zeros(1)
            self.timemap.append((ts, xs))
            # where each rest's bar goes: under its staff, or above it for the upper of two voices
            for st in (g for g in sysg.iter(ns + 'g') if 'staff' in cls(g)):
                ys = [float(v) for pth in st.findall(ns + 'path') for v in re.findall(r'-?[\d.]+', pth.get('d'))[1::2]]
                if not ys:
                    continue
                top, bot = (min(ys) + my) * ky, (max(ys) + my) * ky
                # a layer that draws nothing (the invisible note keeping a part's staff) is no voice
                layers = [l for l in st if 'layer' in cls(l) and any(e.get('id') in owners for e in l.iter(ns + 'g'))]
                for li, l in enumerate(layers):
                    for e in l.iter(ns + 'g'):
                        if e.get('id') in owners and {'rest', 'mRest'} & set(cls(e)):
                            above = len(layers) > 1 and li == 0
                            self.rest_bar[e.get('id')] = (si, above, top, bot)
        # noteheads drawn on the same spot are one lit note: its ink is whatever is drawn
        # inside the notehead, and it lights in every colour singing it
        spots = {}
        for nid, (cx, cy, rx, ry) in self.heads.items():
            spots.setdefault((round(cx), round(cy)), []).append(nid)
        self.alias = {}
        self.spots = [ids for ids in spots.values() if len(ids) > 1]
        for ids in self.spots:
            for i in ids:
                self.alias[i] = ids[0]
        self.args = (owners, syl_holder, colours, views)
        self.ready = False

    def raster(self):
        """Render the ownership planes and the base images (slow; done only for screens shown)."""
        if self.ready:
            return
        owners, syl_holder, colours, views = self.args
        W, H, root = self.W, self.H, self.root
        # ownership planes
        n = len(self.elems)
        K = max(1, int(math.ceil(math.log2(n + 2))))
        top = root
        def plane(group):
            """group None: every piece black (the ink). Otherwise every piece drawn in a colour that
            spells three bits of its index (red, green, blue = bits 3g, 3g+1, 3g+2): where pieces
            overlap the one on top wins, as on the screen, so no bits mix."""
            top.set('visibility', 'hidden')
            for j, (_, _, g) in enumerate(self.elems):
                g.set('visibility', 'visible')
                if group is None:
                    col = '#000000'
                else:
                    b = ((j + 1) >> (3 * group)) & 7
                    col = '#' + ''.join('00' if b >> c & 1 else 'ff' for c in range(3))
                g.set('fill', col)
                g.set('color', col)
            img = render_png(etree.tostring(root), W, H)
            for _, _, g in self.elems:
                for a in ('visibility', 'fill', 'color'):
                    g.attrib.pop(a, None)
            top.attrib.pop('visibility', None)
            return img
        # coverage per channel: cairosvg antialiases text with colour fringes, so a letter's edge
        # covers red, green and blue by different amounts
        au3 = 1.0 - plane(None).astype(np.float32) / 255.0
        au = au3.max(2)
        self.alpha_mean = au3.mean(2)
        owner = np.zeros(au.shape, np.int32)
        unsure = au <= 0.06
        cov = np.maximum(au3, 1e-6)
        for grp in range((K + 2) // 3):
            # a channel at 255 is a 0 bit; one darkened by the ink's own coverage is a 1 bit;
            # anything in between is an edge where two pieces blend: it belongs to neither
            r = (1.0 - plane(grp).astype(np.float32) / 255.0) / cov
            bits = r > 0.5
            unsure |= (((r > 0.25) & (r < 0.75)) | (au3 < 0.03) & (au[..., None] > 0.06)).any(2)
            for c in range(3):
                owner |= bits[..., c].astype(np.int32) << (3 * grp + c)
        owner[unsure] = 0
        owner[owner > n] = 0
        flat = owner.ravel()
        order = np.argsort(flat, kind='stable')
        sorted_ids = flat[order]
        bounds = np.searchsorted(sorted_ids, np.arange(n + 2))
        self.alpha = self.alpha_mean.ravel()      # how much ink, for blending a lit piece's colour
        self.free_ink = ((flat == 0) & (au.ravel() > 0.06)).reshape(H, W)   # lightable ink no piece claimed
        self.pix = [order[bounds[j + 1]:bounds[j + 2]] for j in range(n)]
        self.shared_ink = {}
        for ids in self.spots:
            cx, cy, rx, ry = self.heads[ids[0]]
            y0, y1 = int(max(0, cy - ry)), int(min(H - 1, cy + ry))
            x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.1
            cand = (yy[inside] * W + xx[inside]).ravel()
            self.shared_ink[ids[0]] = cand[self.alpha[cand] > 0.06]
        # base images per view
        self.base = {}
        for v in views:
            self.base[v] = self.render_base(v, owners, syl_holder, colours)

        for v in views:
            items = [(self.names[i], colours[i]) for i in sorted(colours)] if v == 'all' \
                else [(self.names[v], colours[v])]
            self.base[v] = label_band(self.base[v], items, self.label_px)
        self.lights = Lights(self)
        self.ready = True

    def render_base(self, view, owners, syl_holder, colours):
        ns = '{http://www.w3.org/2000/svg}'
        cls = lambda e: (e.get('class') or '').split()
        touched = []
        def paint(g, col):
            g.set('fill', col)
            g.set('color', col)
            touched.append(g)
        if view != 'all':
            for g in self.root.iter(ns + 'g'):
                c = cls(g)
                if 'layer' in c:
                    paint(g, THEME['grey'])
            for g in self.root.iter(ns + 'g'):
                c = cls(g)
                if 'chord' in c or 'beam' in c:
                    ids = [n.get('id') for n in g.iter(ns + 'g') if 'note' in cls(n)]
                    if any(view in owners.get(i, ()) for i in ids):
                        paint(g, '#000000')
                elif ({'note', 'rest', 'mRest'} & set(c)) and g.get('id'):
                    paint(g, '#000000' if view in owners.get(g.get('id'), ()) else THEME['grey'])
            for cid, g in self.ctrl_g:
                paint(g, '#000000' if view in self.ctrl[cid][3] else THEME['grey'])
            for kind, key, g in self.elems:
                if kind in ('syl', 'sylx'):
                    k0 = key.split('#')[0]
                    paint(g, '#000000' if (view, k0) in syl_readers(syl_holder, k0) else THEME['grey'])
        img = render_png(etree.tostring(self.root), self.W, self.H).copy()
        # the engraving is black, grey and white: drop cairosvg's coloured subpixel text fringes,
        # which a lit syllable's unclaimed edge pixels would otherwise show as blue and orange
        img[:] = img.mean(2, keepdims=True).astype(np.uint8)
        if THEME['dark']:                 # engraved black on white; ink becomes light on dark
            a = 1.0 - img.min(2, keepdims=True).astype(np.float32) / 255.0
            img = (THEME['bg'] + (THEME['ink'] - THEME['bg']) * a).astype(np.uint8)
        for g in touched:
            g.attrib.pop('fill', None)
            g.attrib.pop('color', None)
        return img


_SYL_INDEX = {}
_SYL_SVG = {}          # a syllable's svg id -> the note holding it, for extenders over a system break


def index_syl_holder(syl_holder):
    _SYL_INDEX.clear()
    for (part, nid), holder in syl_holder.items():
        _SYL_INDEX.setdefault(holder, []).append((part, nid))


def syl_readers(syl_holder, holder):
    return {(p, holder) for p, _ in _SYL_INDEX.get(holder, [])}


class Lights:
    """Precomputed pixels and halos for each element, per colour."""

    def __init__(self, page):
        self.page, self.tint = page, THEME['tint']
        self.cache = {}
        W = page.W
        self.groups = {}                      # (kind, key) -> indices of elems
        for j, (kind, key, _) in enumerate(page.elems):
            k2 = self.key(kind, key)
            self.groups.setdefault(k2, []).append(j)
        self.geom = {}
        for gk, js in self.groups.items():
            pix = np.concatenate([page.pix[j] for j in js] + [page.shared_ink.get(gk[1], np.zeros(0, int))
                                                             if gk[0] == 'note' else np.zeros(0, int)])
            pix = np.unique(pix)
            if not len(pix):
                continue
            # the edge pixels no piece could be sure of (antialiasing, overlaps) inside this piece's
            # outline are its own: a lit word or note has no grey rim
            ys, xs = pix // W, pix % W
            y0, y1, x0, x1 = max(ys.min() - 1, 0), ys.max() + 2, max(xs.min() - 1, 0), xs.max() + 2
            fy, fx = np.nonzero(page.free_ink[y0:y1, x0:x1])
            if len(fy):
                pix = np.unique(np.concatenate([pix, (fy + y0) * W + fx + x0]))
            if gk[0] == 'note' and gk[1] in page.heads:
                cx, cy, rx, ry = page.heads[gk[1]]
                pad = max(5.0, 1.4 * ry)
                ry, rx = ry + pad, rx + pad
                y0, y1 = int(max(0, cy - ry)), int(min(page.H - 1, cy + ry))
                x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1
                halo = (yy[inside] * W + xx[inside]).ravel()
            elif gk[0] == 'note':
                continue                  # a note whose head was not found in the SVG
            elif gk[0] == 'rest':
                ys, xs = pix // W, pix % W
                (ya, yb), (xa, xb) = np.percentile(ys, [1, 99]), np.percentile(xs, [1, 99])
                cy, cx = (ya + yb) / 2, (xa + xb) / 2
                ry, rx = (yb - ya) / 2 + 1, (xb - xa) / 2 + 1
                # a whole-bar rest is a small glyph: size its halo by the staff, not the glyph
                sp = page.space_px
                ry, rx = max(ry + 0.6 * sp, 1.5 * sp), max(rx + 0.6 * sp, 1.8 * sp)
                y0, y1 = int(max(0, cy - ry)), int(min(page.H - 1, cy + ry))
                x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1
                halo = (yy[inside] * W + xx[inside]).ravel()
            else:
                ys, xs = pix // W, pix % W
                (ya, yb), (xa, xb) = np.percentile(ys, [1, 99]).astype(int), np.percentile(xs, [1, 99]).astype(int)
                h = yb - ya + 1
                pad = max(3, int(0.25 * h))
                if gk[0] == 'sylx':        # a bare extender line: a halo as tall as a word's
                    pad = max(pad, int(0.6 * page.space_px))
                y0, y1 = max(0, ya - pad), min(page.H - 1, yb + pad)
                x0, x1 = max(0, xa - pad), min(W - 1, xb + pad)
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                halo = (yy * W + xx).ravel()
            in_halo = np.isin(pix, halo)
            hy, hx = halo // W, halo % W
            self.geom[gk] = (pix, self.page.alpha[pix][:, None], in_halo[:, None], halo,
                             (int(hx.min()), int(hx.max()), int(hy.max())), (int(hy.min()), int(hy.max())))

    def key(self, kind, nid):
        if kind in ('body', 'head', 'note'):
            return ('note', self.page.alias.get(nid, nid))
        return (kind, nid)

    def band(self, gk, ys, n):
        """Which of n stacked bands each row is in, over the height of the halo."""
        y0, y1 = self.geom[gk][5]
        return np.clip(((ys - y0) * n) // max(y1 - y0 + 1, 1), 0, n - 1)

    def tints(self, gk, cols):
        """Halo pixel values; a note or word two parts share gets a halo split in their colours."""
        key = ('halo', gk, cols)
        v = self.cache.get(key)
        if v is None:
            halo = self.geom[gk][3]
            ts = np.array([THEME['bg'] * (1 - self.tint) + hexrgb(c) * self.tint for c in cols]).astype(np.uint8)
            if len(cols) == 1:
                v = np.broadcast_to(ts[0], (len(halo), 3))
            else:
                # stacked, not side by side: side by side would read as one part singing the
                # first half of the note and the other the second. Top to bottom in part order,
                # which on a shared staff is high to low
                v = ts[self.band(gk, halo // self.page.W, len(cols))]
            self.cache[key] = v
        return v

    def apply(self, frame_flat, lit):
        """lit: list of (group key, tuple of colour hexes in part order, fraction of a rest gone)."""
        W = self.page.W
        for gk, cols, prog in lit:
            if prog is None:
                continue
            # a lit rest gets a bar that fills while the rest lasts, running from where the rest
            # starts to where it ends as the other staves lay out that time: the fill reaches each
            # note they print as it sounds, so nobody has to count
            _, above, top, bot = self.page.rest_bar[gk[1]]
            x0, x1, xe = prog
            sp = self.page.space_px
            th = max(4, int(round(0.4 * sp)))
            y0 = int(round(top - 0.45 * sp - th)) if above else int(round(bot + 0.45 * sp))
            y0 = min(max(0, y0), self.page.H - th)
            f = frame_flat.reshape(self.page.H, W, 3)
            for k, col in enumerate(cols):       # a rest two parts share: one stripe each
                c = hexrgb(col)
                ya, yb = y0 + k * th // len(cols), y0 + (k + 1) * th // len(cols)
                f[ya:yb, x0:x1 + 1] = (THEME['bg'] * 0.65 + c * 0.35).astype(np.uint8)
                if xe > x0:
                    f[ya:yb, x0:xe] = c.astype(np.uint8)
        lit = [(gk, cols) for gk, cols, _ in lit]
        for gk, cols in lit:
            if gk in self.geom:
                h = self.geom[gk][3]
                frame_flat[h] = (np.maximum if THEME['dark'] else np.minimum)(frame_flat[h], self.tints(gk, cols))
        for gk, cols in lit:
            g = self.geom.get(gk)
            if g is None:
                continue
            key = (gk, cols)
            v = self.cache.get(key)
            if v is None:
                cs = np.array([hexrgb(col) for col in cols])
                cs = cs + (255 - cs) * THEME['lift']      # lit ink a shade lighter than its halo
                c = cs[self.band(gk, g[0] // W, len(cols))]   # ink banded like its halo
                t = self.tints(gk, cols).astype(np.float32)
                bg = np.tile(THEME['bg'], (len(g[0]), 1))
                inside = g[2][:, 0]
                if inside.any():
                    pos = np.searchsorted(g[3], g[0][inside]) if np.all(np.diff(g[3]) > 0) else None
                    bg[inside] = t[pos] if pos is not None else t[0]
                v = (bg * (1 - g[1]) + c * g[1]).astype(np.uint8)
                self.cache[key] = v
            frame_flat[g[0]] = v


def label_band(img, items, px):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype('DejaVuSans-Bold.ttf', px)
    except OSError:
        try:
            font = ImageFont.load_default(size=px)
        except TypeError:
            font = ImageFont.load_default()
    x = int(px * 0.8)
    for text, col in items:
        d.text((x, int(px * 0.4)), text, fill=col, font=font)
        x += int(d.textlength(text, font=font)) + int(px * 1.2)
    return np.asarray(im).copy()


def vfr_flag(passthrough=False):
    """ffmpeg 5 renamed -vsync to -fps_mode."""
    v = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout
    m = re.search(r'version n?(\d+)', v)
    new = not m or int(m.group(1)) >= 5
    mode = 'passthrough' if passthrough else 'vfr'
    return ['-fps_mode', mode] if new else ['-vsync', mode]


def check_frames(mp4, planned_ms):
    """Each frame of the finished file against the moment it was meant to appear."""
    pts = [float(v) for v in subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'frame=pts_time', '-of', 'csv=p=0',
         mp4], capture_output=True, text=True).stdout.replace(',', '').split()]
    if len(pts) != len(planned_ms):
        print(f'   frames: {len(pts)} in the file, {len(planned_ms)} planned')
        return
    err = np.abs(np.array(pts) * 1000 - np.array(planned_ms))
    print(f'   frames: all {len(pts)} where planned, to within {err.max():.0f} ms')


# ----------------------------------------------------------------------------- main

def featured_of(mp3, names, part_map):
    b = os.path.basename(mp3)
    # "(Tenor 2) predominant", or a division of a section: "(Tenor 2) a predominant" (rehearsal_mix.py)
    m = re.search(r' - \((.+?)\) (?:(\S+) )?(?:predominant|part-left)', b) \
        or re.search(r' - (Solo[^-]*?) (?:predominant|part-left)', b)
    if not m:
        return None
    sec = m.group(1).strip()
    suf = (m.group(2) or '') if m.re.groups > 1 else ''
    tries = [f'{sec} {suf}', f'{sec}{suf}'] if suf else [sec]
    for t in tries:
        t = part_map.get(t, t)
        for i, n in enumerate(names):
            if n.lower() == t.lower():
                return i
    if suf:
        sys.exit(f'{b}: no part named {tries[0]!r} or {tries[1]!r} in the score (parts: {names}); '
                 f'map it with --part "{tries[0]}=<part name>"')
    sec = part_map.get(sec, sec)
    # "Solo 1" in the mp3 name for a part called "Solo 1 (tenor)"
    near = [i for i, n in enumerate(names)
            if n.lower().startswith(sec.lower()) and not n[len(sec):len(sec) + 1].isalnum()]
    if len(near) == 1:
        return near[0]
    sys.exit(f'{b}: no part named {sec!r} in the score (parts: {names}); map it with --part "{sec}=<part name>"')


def use_display(path, root, parts, names, notes_by_part, tempos):
    """Show `path` instead of the file the audio was rendered from, after checking that it
    has the same parts, bars, notes and tempo marks (words, slurs and ties may differ: the
    Cantai learning file re-sings tied notes that the print file ties)."""
    droot = read_xml(path)
    dparts = droot.findall('part')
    dsps = {sp.get('id'): sp for sp in droot.find('part-list').findall('score-part')}
    dnames = [(dsps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in dparts]
    if len(dparts) != len(parts):
        sys.exit(f'--display: {len(dparts)} parts against {len(parts)} in the file the audio came from')
    tmp = tempfile.NamedTemporaryFile(suffix='.musicxml', delete=False)
    tmp.write(etree.tostring(droot))
    tmp.close()
    _p, _b, dtempos = load_score(tmp.name)
    os.unlink(tmp.name)
    if [(round(b, 3), q) for b, q in dtempos] != [(round(b, 3), q) for b, q in tempos]:
        sys.exit(f'--display: tempo marks differ ({dtempos} against {tempos}); the lights would not follow the audio')
    dnotes, dstarts = [], None
    for i, p in enumerate(dparts):
        ns_, st = scan_part(i, p)
        dnotes.append(ns_)
        dstarts = dstarts or st
    sig = lambda ns_: {} if not ns_ else {mi: sorted((n['rel'], n['dur'], n['midi']) for n in ns_
                                                     if n['mi'] == mi and not n['rest'] and not n['grace'])
                                          for mi in range(max(n['mi'] for n in ns_) + 1)}
    bad = 0
    for i in range(len(parts)):
        if dnames[i] != names[i]:
            print(f'   --display: part {i + 1} is "{dnames[i]}" there and "{names[i]}" here')
        a, b = sig(notes_by_part[i]), sig(dnotes[i])
        diff = [mi + 1 for mi in sorted(set(a) | set(b)) if a.get(mi) != b.get(mi)]
        if diff:
            bad += 1
            print(f'   --display: {names[i]} has different notes in bars {diff[:12]}{" ..." if len(diff) > 12 else ""}')
    print(f'display: {os.path.basename(path)}; ' +
          ('same bars, notes and tempo marks as the file the audio came from' if not bad
           else 'the lights in the bars above follow the display file, not the audio'))
    sung = {i for i, ns_ in enumerate(dnotes) if any(n['lyric'] for n in ns_)}
    return droot, dparts, dnames, dnotes, dstarts, sung



# ----------------------------------------------------------------------------- repeats

def play_order(part):
    """The bars in the order they are played: repeat signs (with times="n") and first/second
    endings unrolled. D.C., D.S. and codas are not followed (a warning says so)."""
    ms = part.findall('measure')
    n = len(ms)
    fwd, bwd, times, end_nums, end_stop = [False] * n, [False] * n, [2] * n, [None] * n, [False] * n
    for i, m in enumerate(ms):
        for bl in m.findall('barline'):
            rp, en = bl.find('repeat'), bl.find('ending')
            if rp is not None and rp.get('direction') == 'forward':
                fwd[i] = True
            if rp is not None and rp.get('direction') == 'backward':
                bwd[i] = True
                times[i] = int(rp.get('times') or 2)
            if en is not None:
                if en.get('type') == 'start':
                    end_nums[i] = [int(x) for x in re.findall(r'\d+', en.get('number') or '1')]
                if en.get('type') in ('stop', 'discontinue'):
                    end_stop[i] = True
    if any(s_.get('dacapo') or s_.get('dalsegno') or s_.get('tocoda') for s_ in part.iter('sound')):
        print('warning: D.C., D.S. or a coda in the score is not followed; only repeat signs are')
    order, i, start, passno, done = [], 0, 0, 1, {}
    while i < n and len(order) < 20 * n:
        if fwd[i] and start != i:
            start, passno = i, 1
        if end_nums[i] is not None and passno not in end_nums[i]:
            j = i
            while j < n - 1 and not end_stop[j]:
                j += 1
            i = j + 1
            continue
        order.append(i)
        if bwd[i]:
            k = done.get(i, 1)
            if k < times[i]:
                done[i] = k + 1
                passno = k + 1
                i = start
                continue
        i += 1
    return order


# ----------------------------------------------------------------------------- a closed score to show

def repair_forwards(droot, src_notes, sung):
    """A second voice written after a <backup> to the start of the bar but missing the <forward>
    over the beats where it has no notes of its own starts too early: its notes land where
    another part's are, and the lights would come a beat early. Where the open score has every
    note of that voice exactly one gap later (the gap being what the voice is short of a full
    bar), put the <forward> in. Returns the bars mended, by staff."""
    at = {(n['mi'], n['rel'], n['midi']) for i, ns_ in enumerate(src_notes) if i in sung
          for n in ns_ if not n['rest'] and not n['grace']}
    mended = []
    for j, part in enumerate(droot.findall('part')):
        div = 1
        for mi, m in enumerate(part.findall('measure')):
            kids = list(m)
            for e in kids:
                if e.tag == 'attributes' and e.find('divisions') is not None:
                    div = int(e.findtext('divisions'))
            full = sum(int(e.findtext('duration') or 0) for e in kids
                       if e.tag == 'note' and e.findtext('voice', '1') == '1' and e.find('chord') is None
                       and e.find('grace') is None)
            for e in kids:
                if e.tag != 'backup' or int(e.findtext('duration') or 0) != full:
                    continue
                voice, t, notes = None, 0, []
                for f in kids[kids.index(e) + 1:]:
                    if f.tag in ('backup', 'forward'):
                        break
                    if f.tag != 'note' or f.find('grace') is not None:
                        continue
                    voice = voice or f.findtext('voice')
                    if f.findtext('voice') != voice:
                        break
                    if f.find('chord') is None:
                        notes.append((t, f))
                        t += int(f.findtext('duration') or 0)
                    else:
                        notes.append((notes[-1][0] if notes else 0, f))
                gap = full - t
                pitched = [(tt, f) for tt, f in notes if f.find('rest') is None]
                if gap <= 0 or not pitched:
                    continue
                if all((mi, Fr(tt + gap, div), midi(f)) in at for tt, f in pitched) and \
                        not all((mi, Fr(tt, div), midi(f)) in at for tt, f in pitched):
                    fw = etree.Element('forward')
                    etree.SubElement(fw, 'duration').text = str(gap)
                    m.insert(list(m).index(e) + 1, fw)
                    mended.append((j, m.get('number'), Fr(gap, div)))
    return mended


def closed_display(droot, src_names, src_notes, sung):
    """Use a closed score (two parts to a staff, as printed) as the display. Whose each notehead,
    rest and syllable is comes from the open score the audio was rendered from: a notehead is
    the parts that sing that pitch at that moment, a rest the parts resting there, a syllable
    the parts starting a syllable there (a second lyric line going to the lower part). What
    the open score cannot settle falls back to the voices: voice 1 and the top of a chord to
    the upper part, voice 2 and the bottom to the lower."""
    for j, num, g in repair_forwards(droot, src_notes, sung):
        print(f'   display bar {num}, staff {j + 1}: its second voice had no <forward> over its first '
              f'{g} beat(s) and began too early; mended to match the open score (fix the file too)')
    dparts = droot.findall('part')
    dsps = {sp.get('id'): sp for sp in droot.find('part-list').findall('score-part')}
    dnames = [(dsps[p.get('id')].findtext('part-name') or p.get('id')) for p in dparts]
    scans = [scan_part(j, p, prefix='d') for j, p in enumerate(dparts)]
    dnotes, dstarts = [sc[0] for sc in scans], scans[0][1]
    staff_parts = {}
    for j, nm in enumerate(dnames):
        flat = ' '.join(nm.lower().split())
        hit = [i for i, sn in enumerate(src_names) if ' '.join(sn.lower().split()) in flat]
        # a name found inside a longer one ("Tenor 1" in "Tenor 1 Tenor 2") is not also its own
        hit = [i for i in hit if not any(i != k and src_names[i].lower() in src_names[k].lower()
                                         and k in hit for k in hit)] or hit
        staff_parts[j] = sorted(hit)
    at, rests, syls = set(), set(), set()
    syl_text = {}
    count = {}
    for i, ns_ in enumerate(src_notes):
        for n in ns_:
            if n['grace']:
                continue
            if n['rest']:
                rests.add((i, n['mi'], n['rel'], n['dur']))
            else:
                at.add((i, n['mi'], n['rel'], n['midi']))
                count[i] = count.get(i, 0) + 1
                if n['lyric']:
                    syls.add((i, n['mi'], n['rel']))
                    syl_text[(i, n['mi'], n['rel'])] = _letters(n['lyric'][1])
    # staves with no part names (or names that match nothing): each sung part goes to the staff
    # holding most of its notes, if that is most of them
    if not any(set(staff_parts[j]) & sung for j in staff_parts):
        staff_parts = {j: [] for j in range(len(dparts))}
        for i in sorted(sung):
            hits = [sum(1 for n in ns_ if not n['rest'] and not n['grace'] and (i, n['mi'], n['rel'], n['midi']) in at)
                    for ns_ in dnotes]
            j = int(np.argmax(hits))
            if hits[j] >= 0.5 * count.get(i, 1):
                staff_parts[j].append(i)
        for j, sp in staff_parts.items():             # label a nameless staff with its parts
            spp = dsps.get(dparts[j].get('id'))
            if sp and spp is not None and not (spp.findtext('part-name') or '').strip():
                for tag, val in (('part-name', '\n'.join(src_names[i] for i in sp)),
                                 ('part-abbreviation', '\n'.join(src_names[i] for i in sp))):
                    el = spp.find(tag)
                    if el is None:
                        el = etree.SubElement(spp, tag)
                    el.text = val
                dnames[j] = ' '.join(src_names[i] for i in sp)
    owners, fall = {}, 0
    for j, ns_ in enumerate(dnotes):
        sp = [i for i in staff_parts[j] if i in sung]
        if not sp:
            continue
        voices = {}
        for n in ns_:
            voices.setdefault(n['mi'], set()).add(n['voice'])
        for n in ns_:
            if n['grace']:
                continue
            if n['rest']:
                c = {i for i in sp if (i, n['mi'], n['rel'], n['dur']) in rests}
            else:
                c = {i for i in sp if (i, n['mi'], n['rel'], n['midi']) in at}
            if not c:
                fall += 1
                vs = sorted(voices[n['mi']], key=lambda v: int(v) if v.isdigit() else 0)
                if n['rest'] and len(vs) == 1:
                    c = set(sp)
                else:
                    c = {sp[0] if vs.index(n['voice']) == 0 else sp[-1]}
            owners[n['id']] = c
    # syllables: grouped by staff and moment; with two lines at one moment, line k is the
    # k-th part (top down) that starts a syllable there in the open score
    groups = {}
    el_of = {n['id']: n['el'] for ns_ in dnotes for n in ns_}

    def placed_above(h):
        return any(ly.get('placement') == 'above' and ly.get('print-object') != 'no'
                   and str(h[0]) == (re.sub(r'\D', '', ly.get('number') or '1') or '1')
                   for ly in el_of[_base(h[1])].findall('lyric'))

    def text_of_el(nid):
        return next((''.join(x.text or '' for x in ly.findall('text')) for ly in el_of[nid].findall('lyric')
                     if ly.get('print-object') != 'no'), '')
    for j, ns_ in enumerate(dnotes):
        for n in ns_:
            for ly in n['el'].findall('lyric'):
                if ly.get('print-object') == 'no':
                    continue                  # sung here, printed for another part (read below)
                if ''.join(x.text or '' for x in ly.findall('text')).strip():
                    num = int(re.sub(r'\D', '', ly.get('number') or '1') or 1)
                    # a note printing its word on two lines (a chord both parts sing, the print
                    # giving each its own row) has one key per line, "id@n", so each part lights
                    # only the row it reads
                    two = sum(1 for x in n['el'].findall('lyric') if x.get('print-object') != 'no'
                              and ''.join(t.text or '' for t in x.findall('text')).strip()) > 1
                    groups.setdefault((j, n['mi'], n['rel']), []).append(
                        (num, f"{n['id']}@{num}" if two else n['id']))
    readers = {}
    for (j, mi, rel), lst in groups.items():
        sp = [i for i in staff_parts[j] if i in sung]
        cand = [i for i in sp if (i, mi, rel) in syls]
        lst.sort()
        if len(lst) == 1 and len(cand) > 1:
            # two parts start a syllable here but one word is printed: it is the parts whose word
            # it is (a Cantai file restarts a held vowel as a new syllable under another part's new word)
            pt = _letters(text_of_el(_base(lst[0][1])))
            same = [i for i in cand if syl_text[(i, mi, rel)] and pt
                    and (pt.startswith(syl_text[(i, mi, rel)]) or syl_text[(i, mi, rel)].startswith(pt))]
            cand = same or cand
        if len(lst) == 1:
            readers.setdefault(lst[0][1], set()).update(cand or owners.get(_base(lst[0][1]), set()))
        else:
            # lines top down: those above the staff first. A part reads the line on its own note
            # (the upper part's words above, the lower's below, as printed); where that does not
            # tell them apart, line k is the k-th part down
            lst.sort(key=lambda h: (0 if placed_above(h) else 1, h[0]))
            holders = list(dict.fromkeys(hid for _, hid in lst))
            if len(holders) == 1:                 # one note's word printed on two lines
                readers.setdefault(holders[0], set()).update(cand or owners.get(_base(holders[0]), set()))
            else:
                for k, i in enumerate(cand):
                    mine = [hid for hid in holders if i in owners.get(_base(hid), set())]
                    readers.setdefault(mine[0] if len(mine) == 1 else holders[min(k, len(holders) - 1)],
                                       set()).add(i)
                for hid in holders:
                    if not readers.get(hid):
                        readers.setdefault(hid, set()).update(owners.get(_base(hid), set()))
    # words printed once for parts on two staves, as a closed score prints them between the staves
    # where both sing them: a part whose own staff prints no syllable at a moment it starts one reads
    # the one printed on another staff there with the same text (a hidden, print-object="no" copy on
    # its own staff says so, and gives the text)
    hidden = {}
    for j, ns_ in enumerate(dnotes):
        for n in ns_:
            for ly in n['el'].findall('lyric'):
                if ly.get('print-object') == 'no':
                    hidden[(j, n['mi'], n['rel'])] = ''.join(x.text or '' for x in ly.findall('text')).strip()
    text_of = {}
    for j, ns_ in enumerate(dnotes):
        for n in ns_:
            for ly in n['el'].findall('lyric'):
                if ly.get('print-object') != 'no':
                    text_of.setdefault(n['id'], ''.join(x.text or '' for x in ly.findall('text')).strip())
    for (j, mi, rel), txt in hidden.items():
        if (j, mi, rel) in groups:
            continue
        sp = [i for i in staff_parts[j] if i in sung and (i, mi, rel) in syls]
        for (j2, mi2, rel2), lst in groups.items():
            if j2 != j and mi2 == mi and rel2 == rel:
                hit = [(num, hid) for num, hid in lst if text_of.get(_base(hid)) == txt]
                if hit:
                    # the same word on two lines of that staff: the one on the side facing this staff
                    def facing(h, j2=j2):
                        ab = any(ly.get('placement') == 'above' and ly.get('print-object') != 'no'
                                 and str(h[0]) == re.sub(r'\D', '', ly.get('number') or '1')
                                 for ly in el_of[_base(h[1])].findall('lyric'))
                        return ab == (j < j2)
                    pick = [h for h in hit if facing(h)] or hit
                    readers.setdefault(pick[-1][1], set()).update(sp)
                    break
    return dparts, dnames, dnotes, staff_parts, owners, readers, fall, dstarts


def part_windows(dnotes, owners, readers, part):
    """One part's notes, rests and syllables in a closed display, in written quarters: a
    syllable lit from its note through the part's following notes until its next syllable or
    rest."""
    evs = {}
    for ns_ in dnotes:
        for n in ns_:
            if not n['grace'] and n['dur'] > 0 and part in owners.get(n['id'], ()):
                evs.setdefault(n['on'], []).append(n)
    syl_at = {}
    on_of = {n['id']: n['on'] for ns_ in dnotes for n in ns_}
    for k, ps in readers.items():
        if part in ps and _base(k) in on_of:
            syl_at[on_of[_base(k)]] = k
    out, cur = {}, None
    for on in sorted(evs):
        ns_ = evs[on]
        end = max(n['on'] + n['dur'] for n in ns_)
        if all(n['rest'] for n in ns_):
            cur = None
        elif on in syl_at:
            cur = syl_at[on]
            out[cur] = [ns_[0]['mi'], on, end]
        elif cur:
            out[cur][2] = max(out[cur][2], end)
    return out


def timing_source(mp3):
    """The mp3 to time this one by. A set made by rehearsal_mix.py is sample-aligned, and its
    Balanced track, every voice at the same level, times best: in a predominant mix a voice 21 dB
    down can enter too quietly to trip the level threshold (one set's Baritone and Tenor mixes
    anchored 0.04-0.1 s late), and its onsets are mostly the featured voice's consonants. Used
    only when the Balanced track sits beside this one, is the same length and lines up with it."""
    m = re.match(r'(.*?) - (\(.+?\)(?: \S+)?|Solo.*) (predominant|part-left)\.mp3$', os.path.basename(mp3))
    if not m:
        return mp3, ''
    ref = os.path.join(os.path.dirname(mp3), m.group(1) + ' - Balanced.mp3')
    if not os.path.exists(ref):
        return mp3, ''
    x, y = decode(ref), decode(mp3)
    if abs(len(x) - len(y)) > 0.03 * 22050:
        return mp3, ''
    h = 220                                              # 10 ms envelopes, compared over +-0.3 s
    n = min(len(x), len(y)) // h
    ex = np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1))
    ey = np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(1))
    ex, ey = ex - ex.mean(), ey - ey.mean()
    lags = range(-30, 31)
    cc = [float(np.dot(ex[max(0, k):n + min(0, k)], ey[max(0, -k):n - max(0, k)])) for k in lags]
    k = lags[int(np.argmax(cc))]
    if k != 0:
        return mp3, ''
    return ref, f'timed by {os.path.basename(ref)}, which it lines up with (same length, 0 ms apart)'


class Tee:
    """Everything the run prints also goes to the checks file beside the videos, so what every
    check found, including nothing, is on record song by song (SKILL.md Step 10)."""
    def __init__(self, path, out):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.f, self.out = open(path, 'w'), out

    def write(self, s):
        self.out.write(s)
        self.f.write(s)

    def flush(self):
        self.out.flush()
        self.f.flush()


def checks_file(a):
    """<title> - video checks.txt in the output folder, the title being what the mp3 names share."""
    import datetime, hashlib
    names = [os.path.basename(m) for m in a.mp3s]
    title = os.path.commonprefix(names).split(' - ')[0].strip() or os.path.splitext(os.path.basename(a.score))[0]
    out_dir = a.out or os.path.dirname(os.path.abspath(a.mp3s[0]))
    path = os.path.join(out_dir, f'{title} - video checks.txt')
    sys.stdout = Tee(path, sys.stdout)
    ver = hashlib.md5(open(os.path.abspath(__file__), 'rb').read()).hexdigest()[:8]
    print(f'Video checks for {title}, {datetime.datetime.now():%Y-%m-%d %H:%M}, score_video.py {ver}')
    print(f'score: {os.path.basename(a.score)}' + (f'; shown: {os.path.basename(a.display)}' if a.display else ''))
    print('mp3s: ' + '; '.join(names) + '\n')
    return path


def proof_note(a):
    print('\ncheck, proof against the print PDF: ' + (
        'screens written; Claude compares each with the PDF and records what differs, or that nothing '
        'does, below (SKILL.md Step 10)' if a.proof else 'NOT RUN (no --proof)'))


def run_parallel(a):
    """One process per mp3, as many at a time as there are cores: each renders its own
    screens and encodes its own video. Each process's report is printed whole, in the order given."""
    import time
    rest = [x for x in sys.argv[1:] if x not in a.mp3s]
    n = a.jobs or os.cpu_count() or 2
    todo = list(enumerate(a.mp3s))
    running, done, nxt, failed, t0 = {}, {}, 0, 0, time.time()
    while todo or running:
        while todo and len(running) < n:
            k, mp3 = todo.pop(0)
            cmd = [sys.executable, os.path.abspath(__file__), *rest, mp3, '--jobs', '1', '--child']
            log = tempfile.TemporaryFile('w+')      # a pipe could fill and stall the process
            running[k] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, text=True), log)
        for k, (pr, log) in list(running.items()):
            if pr.poll() is not None:
                log.seek(0)
                out = log.read()
                log.close()
                done[k] = (pr.returncode, '\n'.join(l for l in out.splitlines() if not l.startswith('[Warning]')))
                del running[k]
        while nxt in done:
            code, text = done.pop(nxt)
            print(text if nxt == 0 else text.split('\n\n', 1)[-1], flush=True)   # parts and staves once
            if code:
                print(f'   ^ failed: {a.mp3s[nxt]}', flush=True)
                failed += 1
            nxt += 1
        time.sleep(0.5)
    print(f'{len(a.mp3s) - failed} of {len(a.mp3s)} videos in {time.time() - t0:.0f} s')
    proof_note(a)
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('mp3s', nargs='+')
    ap.add_argument('-o', '--out', help='folder for the mp4s (default: beside each mp3)')
    ap.add_argument('--part', action='append', default=[], help='"Section in the mp3 name=part name in the score"')
    ap.add_argument('--staves', help='pairs sharing a staff, e.g. "Tenor 1+Tenor 2,Baritone+Bass"')
    ap.add_argument('--open', action='store_true', help='one part per staff (open score)')
    ap.add_argument('--clip', help='START,SECONDS: render only this stretch (for a test)')
    ap.add_argument('--stills', help='comma-separated times (s): write PNG frames instead of a video')
    ap.add_argument('--size', default='1920x1080')
    ap.add_argument('--staff-px', type=float, default=44.0, help='staff height in pixels')
    ap.add_argument('--jobs', type=int, default=0,
                    help='mp3s rendered at once, each in its own process (default: one per CPU core)')
    ap.add_argument('--lead', type=float, default=1.0, help='turn the page up to this many s early')
    ap.add_argument('--anchor', action='append', default=[],
                    help='BAR=M:SS.ss: the audio time of that bar\'s downbeat, measured by hand (from a stem\'s '
                         'first onset after a fermata, say); overrules the fitted hold of the stretch it falls in')
    ap.add_argument('--crf', type=int, default=20)
    ap.add_argument('--no-condense', action='store_true', help='keep empty staves on every system')
    ap.add_argument('--display', help='a print-faithful MusicXML with the same bars, notes and tempo marks '
                    '(normal slurs, ties and words) to show instead of the file the audio came from')
    ap.add_argument('--pulse', type=int, help='rest bars jump in these notes (8 = eighths, 16 = sixteenths); '
                    'default: per part, the coarsest value 95%% of its sung bars keep to')
    ap.add_argument('--dark', action='store_true', help='light notation on a dark screen instead of black on white')
    ap.add_argument('--proof', help='folder for one unlit PNG per screen of the all-parts view, to compare '
                    'with the print PDF (SKILL.md Step 10)')
    ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    a = ap.parse_args()
    if not (a.child or a.stills or a.clip):
        checks_file(a)
    if len(a.mp3s) > 1 and a.jobs != 1 and not a.stills:
        sys.exit(run_parallel(a))
    set_theme(a.dark)
    palette = PALETTE_DARK if a.dark else PALETTE
    W, H = (int(v) for v in a.size.lower().split('x'))
    part_map = dict(p.split('=', 1) for p in a.part)

    root = read_xml(a.score)
    parts = root.findall('part')
    sps = {sp.get('id'): sp for sp in root.find('part-list').findall('score-part')}
    names = [(sps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in parts]
    notes_by_part, starts = [], None
    for i, p in enumerate(parts):
        ns_, st = scan_part(i, p)
        notes_by_part.append(ns_)
        starts = starts or st
    sung = {i for i, ns_ in enumerate(notes_by_part) if any(n['lyric'] for n in ns_)}
    if not sung:
        sys.exit('no part has lyrics; nothing to follow')

    # tempo map, as stem_vs_score.py reads it
    tmp = tempfile.NamedTemporaryFile(suffix='.musicxml', delete=False)
    tmp.write(etree.tostring(root))
    tmp.close()
    _phr, bars, tempos = load_score(tmp.name)
    os.unlink(tmp.name)
    src_parts, src_notes, src_starts = parts, notes_by_part, starts
    k = mark_tuplets(root)
    if k:
        print(f'{k} tuplet group(s) had no bracket or number in the file; marked for the video')

    droot = read_xml(a.display) if a.display else None
    closed = droot is not None and len(droot.findall('part')) != len(parts)
    if droot is not None:
        k = mark_tuplets(droot)
        if k:
            print(f'{k} tuplet group(s) in the display file had no bracket or number; marked for the video')
    if a.display and not closed:
        root, parts, names, notes_by_part, starts, sung = use_display(
            a.display, root, parts, names, notes_by_part, tempos)

    # ---- the order the music is played in: repeats unrolled. Every lit thing is placed by bar
    # and position in the bar, then at each moment that bar is played
    order = play_order(src_parts[0])
    piece_q = max(n['on'] + n['dur'] for ns_ in src_notes for n in ns_)
    blen = [b - a_ for a_, b in zip(src_starts, list(src_starts[1:]) + [piece_q])]
    ubars, u = [], Fr(0)
    for mi in order:
        ubars.append((mi, u))
        u += blen[mi]
    occ = {}
    for mi, us in ubars:
        occ.setdefault(mi, []).append(us)
    if len(order) != len(src_starts):
        print(f'repeats: {len(order)} bars played from {len(src_starts)} written')

    def bpm_at(q):
        v = tempos[0][1]
        for b, t in tempos:
            if b <= q + 1e-9:
                v = t
        return v
    utempos = []
    for mi, us in ubars:
        a0, a1 = src_starts[mi], src_starts[mi] + blen[mi]
        utempos.append((float(us), bpm_at(float(a0))))
        utempos += [(float(us) + b - float(a0), t) for b, t in tempos if float(a0) < b < float(a1)]
    usec = lambda uq: beats_to_sec(float(uq), utempos)

    def times_of(mi, q0, q1):
        """Score seconds (s0, s1) of written quarters q0..q1 in bar mi, each time the bar is played."""
        return [(usec(us + q0 - src_starts[mi]), usec(us + q1 - src_starts[mi])) for us in occ.get(mi, [])]

    # ---- the timing's own material, from the file the audio came from: every sounding note with
    # its pitch, and where each fermata ends (on a note or a rest where it does; over a barline, at
    # that barline)
    pitched, all_onsets, fermata_at = [], [], []
    for ns_ in src_notes:
        for n in ns_:
            if n['grace'] or n['dur'] == 0:
                continue
            spans = times_of(n['mi'], n['on'], n['on'] + n['dur'])
            if not n['rest']:
                all_onsets += [s0 for s0, _ in spans]
                if n['midi'] is not None:
                    pitched += [(s0, s1, n['midi']) for s0, s1 in spans]
            if n['el'].find('.//fermata') is not None:
                fermata_at += [s1 for _, s1 in spans]
    for mi, m in enumerate(src_parts[0].findall('measure')):
        for bl in m.findall('barline'):
            if bl.find('fermata') is not None:
                q = src_starts[mi] + (0 if bl.get('location') == 'left' else blen[mi])
                fermata_at += [s0 for s0, _ in times_of(mi, q, q)]
    # fermatas a moment apart are one hold for the fit, taken after the last of them: two
    # fermata eighths 0.4 s apart and a caesura (a ballad TTBB's last line) left too little
    # between them to measure, and the fit put -1.1 s on the second where playback held +0.75 s
    breaks = []
    for b in sorted(fermata_at):
        if breaks and b - breaks[-1] < 1.5:
            breaks[-1] = b
        else:
            breaks.append(b)
    first_score = min(all_onsets)

    # ---- what is shown, and whose each thing on it is; windows in written quarters by bar
    note_q, rest_q, syl_q = {}, {}, {}
    if closed:
        dparts, dnames, dnotes, staff_parts, owners, readers, fall, dstarts = closed_display(
            droot, names, notes_by_part, sung)
        if len(dstarts) != len(src_starts) or any(x != y for x, y in zip(dstarts, src_starts)):
            sys.exit('--display: the closed score\'s bars do not line up with the open score\'s')
        disp, d_all = droot, [n for ns_ in dnotes for n in ns_]
        pid_of = {n['id']: dparts[j].get('id') for j, ns_ in enumerate(dnotes) for n in ns_}
        pairs = [tuple(i for i in sp if i in sung) for sp in staff_parts.values()
                 if len([i for i in sp if i in sung]) == 2]
        staff_pid = {i: dparts[j].get('id') for j, sp in staff_parts.items() for i in sp}
        print(f'display: {os.path.basename(a.display)}, a closed score: ' + ', '.join(
            f'"{" ".join(dnames[j].split())}" = {" + ".join(names[i] for i in sp) or "?"}'
            for j, sp in staff_parts.items()) +
            f'; {fall} of {sum(1 for n in d_all if n["id"] in owners)} notes and rests placed by voice, the '
            'rest matched to the open score')
        for n in d_all:
            for i in owners.get(n['id'], ()):
                (rest_q if n['rest'] else note_q).setdefault(n['id'], []).append(
                    (i, n['mi'], n['on'], n['on'] + n['dur']))
        for i in sung:
            for hid, (mi, q0, q1) in part_windows(dnotes, owners, readers, i).items():
                syl_q.setdefault(hid, []).append((i, mi, q0, q1))
        syl_holder = {(i, hid): hid for hid, ps in readers.items() for i in ps}
        centre = dnotes
    else:
        if a.open:
            pairs = []
        elif a.staves:
            idx = {n.lower(): i for i, n in enumerate(names)}
            pairs = []
            for grp in a.staves.split(','):
                up, lo = (x.strip().lower() for x in grp.split('+'))
                if up not in idx or lo not in idx:
                    sys.exit(f'--staves: unknown part in {grp!r}; parts are {names}')
                pairs.append((idx[up], idx[lo]))
        else:
            pairs = default_pairs(names, sung)
        centre = notes_by_part
    # A rest that fills its bar alone is a bar rest, centred in the bar. Some files write it as a
    # plain whole rest on beat 1, which Verovio sets at the left edge of the bar; mark it as one.
    for ns_ in centre:
        by_bar = {}
        for n in ns_:
            if not n['grace']:
                by_bar.setdefault((n['mi'], n['voice'], n['el'].findtext('staff') or '1'), []).append(n)
        for (mi, _, _), evs in by_bar.items():
            if len(evs) == 1 and evs[0]['rest'] and evs[0]['rel'] == 0 and mi < len(blen) \
                    and evs[0]['dur'] == blen[mi]:
                evs[0]['el'].find('rest').set('measure', 'yes')
    if not closed:
        disp, owners, syl_holder = display_score(root, parts, notes_by_part, pairs, sung)
        d_all = [n for ns_ in notes_by_part for n in ns_]
        pair_of = {x: pr for pr in pairs for x in pr}
        staff_pid = {i: (f'PX{pair_of[i][0]}' if i in pair_of else parts[i].get('id')) for i in range(len(parts))}
        pid_of = {n['id']: staff_pid[i] for i, ns_ in enumerate(notes_by_part) for n in ns_}
        mi_of = {n['id']: n['mi'] for n in d_all}
        for i, ns_ in enumerate(notes_by_part):
            if i not in sung:
                continue
            for n in ns_:
                if not n['grace'] and n['dur'] > 0:
                    (rest_q if n['rest'] else note_q).setdefault(n['id'], []).append(
                        (i, n['mi'], n['on'], n['on'] + n['dur']))
            for nid, (q0, q1) in syllable_windows(ns_).items():
                h = syl_holder.get((i, nid))
                if h:
                    syl_q.setdefault(h, []).append((i, mi_of[nid], q0, q1))
        # a unison notehead carries both parts; the lower part's own note id is not printed
        for table in (note_q, rest_q):
            for nid, ps in owners.items():
                if nid in table:
                    have = {w[0] for w in table[nid]}
                    _, mi, q0, q1 = table[nid][0]
                    table[nid] += [(p, mi, q0, q1) for p in ps if p not in have]
    colours = {}                           # the parts sharing staves get the four strongest colours
    for i in [x for pr in pairs for x in pr] + sorted(sung):
        if i in sung and i not in colours:
            colours[i] = palette[len(colours) % len(palette)]
    print('parts: ' + ', '.join(f'{names[i]}{" (sung, " + colours[i] + ")" if i in sung else ""}'
                                 for i in range(len(names))))
    if not closed:
        print('staves: ' + ('open score' if not pairs else
                            ', '.join(f'{names[u_]} + {names[l_]}' for u_, l_ in pairs)))
    index_syl_holder(syl_holder)

    # each sung part's pulse: the coarsest note value that 95% of the bars it sings keep to
    # (every note starting and lasting a whole number of them; tuplets aside). A piece in
    # eighths with one bar of sixteenths pulses in eighths. A rest's bar fills in jumps of this
    # length counted from the barline, so the pulse shows, the way a sung note lights up
    pulse = {}
    for i in sung:
        bars_ = {}
        for n in src_notes[i]:
            if not n['grace'] and not n['tmod'] and n['dur'] > 0:
                bars_.setdefault(n['mi'], []).append(n)
        sung_bars = [ns_ for ns_ in bars_.values() if any(not n['rest'] for n in ns_)]
        pulse[i] = Fr(1, 8)
        for u_ in (Fr(4), Fr(2), Fr(1), Fr(1, 2), Fr(1, 4), Fr(1, 8)):
            fits = sum(all(n['rel'] % u_ == 0 and n['dur'] % u_ == 0 for n in ns_) for ns_ in sung_bars)
            if sung_bars and fits >= 0.95 * len(sung_bars):
                pulse[i] = u_
                break
        if a.pulse:
            pulse[i] = Fr(4, a.pulse)
    note_name = {Fr(4): 'whole', Fr(2): 'half', Fr(1): 'quarter', Fr(1, 2): 'eighth', Fr(1, 4): 'sixteenth',
                 Fr(1, 8): '32nd'}
    print('rest bars jump in: ' + ', '.join(f'{names[i]} {note_name.get(pulse[i], str(pulse[i]) + " quarter")}s'
                                             for i in sorted(sung)))

    def unroll(table):
        """{id: [(part, bar, q0, q1)]} -> {id: [(part, s0, s1, q0, q1, bar)]}, once per playing."""
        out = {}
        for k, ws in table.items():
            for p_, mi, q0, q1 in ws:
                for s0, s1 in times_of(mi, q0, q1):
                    out.setdefault(k, []).append((p_, s0, s1, q0, q1, mi))
        return out
    note_s, rest_s, syl_s = unroll(note_q), unroll(rest_q), unroll(syl_q)

    def steps(part, s0, s1, q0, q1, mi):
        """Score seconds where a rest's bar jumps: the end of each pulse inside the rest."""
        m0, u_ = src_starts[mi], pulse[part]
        k = (q0 - m0) // u_ + 1
        out = []
        while m0 + k * u_ < q1:
            out.append(s0 + float(m0 + k * u_ - q0) / float(q1 - q0) * (s1 - s0))
            k += 1
        return tuple(out) + (s1,)

    # where things are on the page, in written quarters: for the rest bars' time -> x maps, and
    # which screen each bar is on
    d_mi = {n['id']: n['mi'] for n in d_all}
    x_q = {n['id']: float(n['on']) for n in d_all if not n['grace'] and not (
        n['rest'] and (n['el'].find('rest').get('measure') == 'yes' or n['type'] in (None, 'whole') and n['rel'] == 0))}
    bar_end = {n['id']: float(src_starts[n['mi']] + blen[n['mi']]) for n in d_all if n['mi'] < len(blen)}
    last_on_q = {}
    for n in d_all:
        if not n['grace'] and not n['rest']:
            last_on_q[n['mi']] = max(last_on_q.get(n['mi'], n['on']), n['on'])

    # engrave
    import verovio
    install_smufl_font()
    z = 72.0 / a.staff_px
    band = int(round(0.045 * H))
    opts = {'pageWidth': int(W * z), 'pageHeight': int(H * z), 'scale': 100,
            'pageMarginTop': int((band + 0.01 * H) * z), 'pageMarginBottom': int(0.02 * H * z),
            'pageMarginLeft': int(0.02 * W * z), 'pageMarginRight': int(0.02 * W * z),
            'breaks': 'auto', 'header': 'none', 'footer': 'none', 'adjustPageHeight': False,
            'justifyVertically': False, 'lyricSize': 5.0, 'spacingSystem': 10, 'svgViewBox': False}
    k = mark_accidentals(disp)
    print('check, accidentals: ' + (f'{k} the file leaves to the reader, written out for the video' if k else
                                     'the file writes every one the page needs'))
    # every lyric line stops where its melisma does (SKILL.md 7.6): verify.py's check 14, on what is shown
    dsp = {sp.get('id'): (sp.findtext('part-name') or sp.get('id')).strip() for sp in disp.iter('score-part')}
    # which notes sing words of their own: the open score whose words are shown (a closed display file
    # given ready-made has none beside it, and verify.py --original checks that one)
    src_names = [(sp.findtext('part-name') or '').strip() for sp in root.iter('score-part')]

    def sung_on(p):                        # only the parts sharing that staff (a soloist is not the tenors)
        return frozenset() if closed else sung_positions(root, parts_on(dsp.get(p.get('id'), ''), src_names))
    bad = [f"{dsp.get(p.get('id'), p.get('id'))} voice {v} line {num}: the line from {t!r} (bar {mn}) runs on to "
           f"bar {last}, {why}" for p in disp.findall('part') for mn, v, num, t, last, why in lyric_line_runs(p, sung_on(p))]
    if bad:
        sys.exit('lyric lines that run on past their melisma in the score shown (SKILL.md 7.6):\n   ' + '\n   '.join(bad))
    print('check, lyric lines: every one stops where its melisma does' +
          ('' if not closed else ' (past rests only: a closed display file has no open score beside it)'))
    tk = verovio.toolkit()
    tk.setOptions(opts)
    if not tk.loadData(etree.tostring(disp).decode()):
        sys.exit('verovio could not read the closed score')
    wrong = pitch_readback(tk)
    if wrong:
        sys.exit('notes that read on the page as a pitch they do not sound (bar, staff, reads, sounds):\n   ' +
                 '\n   '.join(f'{b} staff {n}: reads {r}, sounds {s}' for b, n, _, r, s in wrong))
    print('check, pitch readback: every note reads on the page as the pitch it sounds')
    base_mei = tk.getMEI()
    # words printed above the staff: Verovio reads no placement from a MusicXML lyric, but honours
    # it on an MEI verse (@place). The note ids survive the trip, and a verse's @n is its lyric number
    # every verse names its line in the SVG (a class "vn<n>"), for a note printing its word on two lines
    _rm = etree.fromstring(base_mei.encode())
    for vv in _rm.iter('{http://www.music-encoding.org/ns/mei}verse'):
        vv.set('type', 'vn' + (vv.get('n') or '1'))
    base_mei = etree.tostring(_rm).decode()
    above = {(n_.get('id'), ly.get('number') or '1') for n_ in disp.iter('note') for ly in n_.findall('lyric')
             if ly.get('placement') == 'above' and n_.get('id')}
    if above:
        M_, X_ = '{http://www.music-encoding.org/ns/mei}', '{http://www.w3.org/XML/1998/namespace}id'
        rm = etree.fromstring(base_mei.encode())
        k_ = 0
        for el in rm.iter(M_ + 'note', M_ + 'chord'):
            # a chord's verses sit under the <chord>, not its notes: take any member's placement
            ids = [el.get(X_)] + ([m_.get(X_) for m_ in el.iter(M_ + 'note')] if el.tag == M_ + 'chord' else [])
            for vv in el.findall(M_ + 'verse'):
                if any((i_, vv.get('n') or '1') in above for i_ in ids):
                    vv.set('place', 'above')
                    k_ += 1
        base_mei = etree.tostring(rm).decode()
        print(f'words above the staff: {k_} syllables, as printed')
    layouts = {}

    def layout(view):
        """The screens for one view. Staves empty for a whole system are hidden, as in a printed
        score (Verovio does this for MEI with <scoreDef optimize="true">, not for MusicXML, and
        keeps the note ids); in one part's own video its staff is never hidden, so its rests
        stay on screen to be lit."""
        if view in layouts:
            return layouts[view]
        _SYL_SVG.clear()
        mei = base_mei
        if not a.no_condense:
            M = '{http://www.music-encoding.org/ns/mei}'
            r = etree.fromstring(re.sub(r'<scoreDef ', '<scoreDef optimize="true" ', mei, count=1).encode())
            if view != 'all':
                pid = staff_pid.get(view)
                sd = next((d for d in r.iter(M + 'staffDef')
                           if d.get('{http://www.w3.org/XML/1998/namespace}id') == pid), None)
                for st in (r.iter(M + 'staff') if sd is not None else []):
                    if st.get('n') == sd.get('n') and st.find('.//' + M + 'note') is None \
                            and st.find('.//' + M + 'chord') is None:
                        # an invisible whole note keeps the staff; a second layer would push the
                        # rests off their usual lines, so pin them there (a whole rest hangs from the
                        # fourth line, loc 6; the rest sit on the middle line, loc 4). A bar of rest
                        # is an <mRest> or, from some files, a plain whole <rest>
                        for mr in st.iter(M + 'mRest'):
                            mr.set('loc', '6')
                        for rr in st.iter(M + 'rest'):
                            rr.set('loc', '6' if rr.get('dur') in ('1', 'breve', 'long') else '4')
                        ly = etree.SubElement(st, M + 'layer', n='9')
                        etree.SubElement(ly, M + 'note', dur='1', oct='4', pname='c', visible='false')
            mei = etree.tostring(r).decode()
        t = verovio.toolkit()
        t.setOptions(opts)
        if not t.loadData(mei):
            sys.exit('verovio could not re-read the score as MEI')
        # whose each tie and slur is: from the notes the MEI says it starts and ends on (the SVG
        # keeps the MEI ids). A tie is its notes' part's; a slur starting or ending on a chord
        # that two parts share is both parts'
        M, X = '{http://www.music-encoding.org/ns/mei}', '{http://www.w3.org/XML/1998/namespace}id'
        rr = etree.fromstring(mei.encode())
        chord_of = {}
        for ch in rr.iter(M + 'chord'):
            mem = [nn.get(X) for nn in ch.iter(M + 'note')]
            for nn in mem:
                chord_of[nn] = mem
        ctrl = {}
        d_end = {n['id']: (n['mi'], n['on'] + n['dur']) for n in d_all}

        def staff_sung(nid):
            # the parts on the fermata's own staff: the tenors' hold is not the basses'
            return {i for i, pid in staff_pid.items() if pid == pid_of.get(nid)}
        ferm_end = {}
        for i_, ns_ in enumerate(notes_by_part):
            for n in ns_:
                if i_ in sung and n['el'].find('.//fermata') is not None:
                    ferm_end.setdefault((n['mi'], n['on'] + n['dur']), set()).add(i_)
        for ch in rr.iter(M + 'chord'):
            chord_of[ch.get(X)] = [nn.get(X) for nn in ch.iter(M + 'note')]
        for tag in ('tie', 'slur', 'fermata'):
            for e in rr.iter(M + tag):
                st, en = (e.get('startid') or '').lstrip('#'), (e.get('endid') or '').lstrip('#')
                ends = [st, en] if tag == 'tie' else chord_of.get(st, [st]) + chord_of.get(en, [en])
                # a fermata is black in a part's own video only where it sits on that part's note or
                # rest (grey over everyone else's, like their notes)
                own = set().union(*[owners.get(i, set()) for i in ends if i])
                k_ = next((i for i in [st] + chord_of.get(st, []) if i in d_end), None)
                if tag == 'fermata' and k_:
                    # and every part holding its own fermata to the same moment (a bar rest's
                    # fermata, left out on the closed staff where it would stack over this one)
                    own |= ferm_end.get(d_end[k_], set()) & staff_sung(k_)
                ctrl[e.get(X)] = (tag, st, en, own)
        pages = [Page(t.renderToSVG(p), W, H, owners, syl_holder, colours, [view], names, int(band * 0.62),
                      x_q, bar_end, ctrl)
                 for p in range(1, t.getPageCount() + 1)]
        bar_page = {}                            # which screen each written bar is on
        for pi_, pg in enumerate(pages):
            for i in pg.ids_on_page:
                if i in d_mi:
                    bar_page.setdefault(d_mi[i], pi_)
        print(f'engraved for {"every part" if view == "all" else names[view]}: {len(pages)} screens of '
              f'{W}x{H}, staff {a.staff_px:.0f} px')
        nud = sum(p_.nudged for p_ in pages)
        if nud:
            print(f'   {nud} syllables moved right to clear the word before them on their line')
        layouts[view] = (pages, bar_page, ctrl)
        return layouts[view]

    jobs = []
    for mp3 in a.mp3s:
        f = featured_of(mp3, names, part_map)
        if f is not None and f not in sung:
            sys.exit(f'{mp3}: {names[f]} has no lyrics in the score')
        out_dir = a.out or os.path.dirname(os.path.abspath(mp3))
        base = os.path.splitext(os.path.basename(mp3))[0]
        jobs.append((mp3, 'all' if f is None else f, os.path.join(out_dir, base)))

    numbers = [m.get('number') for m in src_parts[0].findall('measure')]
    bar_sec = [(usec(us), numbers[mi]) for mi, us in ubars]

    for mp3, view, stem in jobs:
        pages, bar_page, ctrl = layout(view)
        if a.proof and view == 'all':
            from PIL import Image
            os.makedirs(a.proof, exist_ok=True)
            nums = [m.get('number') for m in src_parts[0].findall('measure')]
            for p_ in range(len(pages)):
                bars = sorted(mi for mi, pg in bar_page.items() if pg == p_)
                pages[p_].raster()
                fn = os.path.join(a.proof, f'screen {p_ + 1} bars {nums[bars[0]]}-{nums[bars[-1]]}.png')
                Image.fromarray(pages[p_].base['all']).save(fn)
                print(f'   proof screen: {os.path.basename(fn)}')
        ref, why = timing_source(mp3)
        T = Timing(ref, pitched, first_score, breaks)
        # hand-measured downbeats overrule the fit for the stretch between fermatas that holds them:
        # where the pitch alignment has too little to hold on to (a repeated piano figure, held
        # chords, few onsets) the fitted hold can come out seconds wrong, and even negative
        for an in a.anchor:
            num, t = an.split('=', 1)
            mm, _, ss = t.rpartition(':')
            t_audio = (float(mm) * 60 if mm else 0.0) + float(ss)
            s0 = next((s0 for s0, n_ in bar_sec if str(n_) == num.strip()), None)
            if s0 is None:
                sys.exit(f'--anchor {an}: no bar {num}')
            j = int(np.searchsorted(T.breaks, s0, side='right'))
            T.cum[j] = t_audio - float(T.straight(s0))
            T.steps = [float(v) for v in np.diff(T.cum)]
            print(f'   anchored: bar {num} at {t}, by hand (the stretch after fermata {j} of {len(T.breaks)})')
        # a stretch with no onsets to fit (after the last fermata: only the final note's end) holds
        # nothing of its own and keeps the offset before it. Left at the fit's value it did not follow
        # an anchor: bar 76's lights ended 6 s before they began, and the last bar never lit
        for j in range(1, len(T.cum)):
            lo_ = T.breaks[j - 1]
            hi_ = T.breaks[j] if j < len(T.breaks) else np.inf
            if not ((T.so >= lo_) & (T.so < hi_)).any():
                T.cum[j] = T.cum[j - 1]
        T.steps = [float(v) for v in np.diff(T.cum)]
        if ref != mp3:
            T.x = decode(mp3)                            # the audio check below is against this mp3
        def bar_at(t_audio):
            s = (t_audio - T.off) / T.scale
            cur = bar_sec[0][1]
            for s0, num in bar_sec:
                if s0 <= s + 1e-6:
                    cur = num
            return cur
        T.report(bar_at, f'{os.path.basename(mp3)} -> {"every part" if view == "all" else names[view]}')
        if why:
            print(f'   {why}')
        # page turns (audio seconds), in the order the bars are played: a repeat turns back.
        # Up to --lead s before the next screen's first bar, never before the last note on the old
        # screen has begun
        turns, pages_at, prev = [], [], None
        for k, (mi, us) in enumerate(ubars):
            pg_ = bar_page.get(mi)
            if pg_ is None or pg_ == prev:
                continue
            start = float(T(usec(us)))
            if prev is None:
                tsw = 0.0
            else:
                pmi, pus = ubars[k - 1]
                last_on = float(T(usec(pus + last_on_q.get(pmi, src_starts[pmi]) - src_starts[pmi])))
                tsw = min(start, max(last_on + 0.3, start - a.lead))
            turns.append(tsw)
            pages_at.append(pg_)
            prev = pg_
        # light windows per page: (t0, t1, page, group key, colour)
        wins = []
        page_of = {}                               # (kind, id) -> [(page, lit group)]
        for pi_, pg in enumerate(pages):
            for kind, key, _ in pg.elems:
                if kind == 'sylx':                 # an extender's continuation lights with its syllable
                    page_of.setdefault(('syl', key.split('#')[0]), []).append((pi_, (kind, key)))
                    continue
                if kind == 'tie':                  # each drawn piece of a tie, on whatever screen
                    page_of.setdefault(('tie', key.split('#')[0]), []).append((pi_, (kind, key)))
                    continue
                kk = ('note' if kind in ('body', 'head') else kind, key)
                gk = ('note', pg.alias.get(key, key)) if kk[0] == 'note' else kk
                if (pi_, gk) not in page_of.setdefault(kk, []):
                    page_of[kk].append((pi_, gk))
        score_end = max(w[2] for tb in (note_s, rest_s) for ws in tb.values() for w in ws)
        tie_s = {}
        for cid, (tag, st, en, ps) in ctrl.items():
            if tag == 'tie':
                tie_s[cid] = [w for nid in (st, en) for w in note_s.get(nid, []) if w[0] in ps]
        for kind, table in (('note', note_s), ('syl', syl_s), ('rest', rest_s), ('tie', tie_s)):
            for nid, ws in table.items():
                if (kind, nid) not in page_of:
                    continue
                for pi_, gk in page_of[(kind, nid)]:
                    for part, s0, s1, q0, q1, mi in ws:
                        if view == 'all' or part == view:
                            t1_ = float(T(s1))
                            if s1 >= score_end - 1e-6 and kind != 'rest':
                                # playback holds the final fermata as long as it likes: the last
                                # notes stay lit until the sound stops
                                t1_ = max(t1_, min(T.last_audio, T.dur))
                            wins.append((float(T(s0)), t1_, pi_, gk, colours[part], part, s0, s1,
                                         steps(part, s0, s1, q0, q1, mi) if kind == 'rest' else None,
                                         float(q0), float(q1)))
        wins.sort()

        t_start, t_len = 0.0, T.dur
        if a.clip:
            c0, c1 = (float(v) for v in a.clip.split(','))
            t_start, t_len = c0, min(c1, T.dur - c0)

        def lit_key(p, ws, t):
            lit, prog = {}, {}
            for w in ws:
                if w[2] == p:
                    lit.setdefault(w[3], set()).add((w[5], w[4]))
                    rb = pages[p].rest_bar.get(w[3][1]) if w[3][0] == 'rest' else None
                    if rb is not None:
                        ts, xs = pages[p].timemap[rb[0]]
                        s = w[6] + (t - w[0]) / max(w[1] - w[0], 1e-6) * (w[7] - w[6])
                        s = next((b for b in w[8] if b > s + 1e-9), w[7])   # through the current pulse
                        q = w[9] + (s - w[6]) / max(w[7] - w[6], 1e-9) * (w[10] - w[9])   # where on the page
                        prog[w[3]] = tuple(int(round(float(np.interp(v, ts, xs)))) for v in (w[9], w[10], q))
            return (p, tuple(sorted((k, tuple(c for _, c in sorted(v)), prog.get(k)) for k, v in lit.items())))

        def page_at(t):
            k = bisect.bisect_right(turns, t) - 1
            return pages_at[max(k, 0)]

        def frame_at(t):
            p = page_at(t)
            return lit_key(p, [w for w in wins if w[0] <= t < w[1]], t)

        def compose(key):
            p, lit = key
            pages[p].raster()
            fr = pages[p].base[view].copy()
            pages[p].lights.apply(fr.reshape(-1, 3), list(lit))
            return fr

        from PIL import Image
        if a.stills:
            for tv in a.stills.split(','):
                tv = float(tv)
                path = f'{stem} @{tv:.0f}s.png'
                Image.fromarray(compose(frame_at(tv))).save(path)
                print(f'   still: {path}')
            continue

        out = stem + ('' if not a.clip else f' clip {int(t_start)}-{int(t_start + t_len)}s') + '.mp4'
        t_end = t_start + t_len
        # Variable frame rate: one frame per change of lights or page, shown from the exact
        # moment of the change (to the millisecond) until the next. No frame grid, so no rounding
        # of a light to the nearest frame, and nothing encoded twice.
        ev = {t_start, t_end}
        for w in wins:
            ev.update(v for v in (w[0], w[1]) if t_start < v < t_end)
            if w[8]:
                ev.update(float(T(b)) for b in w[8] if t_start < float(T(b)) < t_end)
        ev.update(v for v in turns if t_start < v < t_end)
        ev = sorted(ev)
        segs = []                                  # (start ms, key)
        wi, active = 0, []
        for e0, e1 in zip(ev[:-1], ev[1:]):
            t = (e0 + e1) / 2
            while wi < len(wins) and wins[wi][0] <= t:
                active.append(wins[wi])
                wi += 1
            active = [w for w in active if w[1] > t]
            key = lit_key(page_at(t), active, t)
            ms = int(round(1000 * (e0 - t_start)))
            if segs and (segs[-1][1] == key or segs[-1][0] == ms):
                if segs[-1][1] != key:
                    segs[-1] = (ms, key)           # under a millisecond: the later state wins
                continue
            segs.append((ms, key))
        end_ms = int(round(1000 * t_len))
        tmpd = tempfile.mkdtemp(prefix='score_video_')
        lines = ['ffconcat version 1.0']
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
            jobs_ = []
            for k, (ms, key) in enumerate(segs):
                fn = os.path.join(tmpd, f'{k:06d}.png')
                jobs_.append(pool.submit(lambda im, fn: Image.fromarray(im).save(fn, compress_level=1),
                                         compose(key), fn))
                nxt = segs[k + 1][0] if k + 1 < len(segs) else end_ms
                lines += [f"file '{fn}'", 'option framerate 1000', f'duration {(nxt - ms) / 1000:.3f}']
            for jb in jobs_:
                jb.result()
        lines += [f"file '{os.path.join(tmpd, f'{len(segs) - 1:06d}.png')}'", 'option framerate 1000']
        lst = os.path.join(tmpd, 'frames.ffconcat')
        open(lst, 'w').write('\n'.join(lines) + '\n')
        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
               '-ss', f'{t_start:.3f}', '-t', f'{t_len:.3f}', '-i', mp3, '-map', '0:v', '-map', '1:a',
               *vfr_flag(), '-video_track_timescale', '1000', '-c:v', 'libx264', '-preset', 'veryfast',
               '-tune', 'stillimage', '-g', '30', '-crf', str(a.crf), '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '192k', '-t', f'{t_len:.3f}', '-movflags', '+faststart', out]
        r = subprocess.run(cmd)
        shutil.rmtree(tmpd, ignore_errors=True)
        if r.returncode:
            sys.exit(f'ffmpeg failed on {out}')
        # check the audio that landed against the mp3 (an AAC priming delay would shift everything)
        y = decode(out)
        x = T.x[int(t_start * 22050):int(t_start * 22050) + len(y)]
        n = min(len(x), len(y), 22050 * 20)
        lag = 0
        if n > 22050:
            seg_x, seg_y = x[:n] - x[:n].mean(), y[:n] - y[:n].mean()
            cc = np.fft.irfft(np.fft.rfft(seg_y, 2 * n) * np.conj(np.fft.rfft(seg_x, 2 * n)))
            k = int(np.argmax(np.concatenate([cc[-2205:], cc[:2206]]))) - 2205
            lag = k / 22.05
        print(f'   wrote {os.path.basename(out)}: {len(segs)} frames, one per change of lights or page; '
              f'audio in the mp4 is {lag:+.1f} ms from the mp3')
        check_frames(out, [ms for ms, _ in segs])
        if all(v != view for _, v, _ in jobs[jobs.index((mp3, view, stem)) + 1:]):
            layouts.pop(view, None)              # its screens are not needed again: free them
    if not (a.child or a.stills or a.clip):
        proof_note(a)


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