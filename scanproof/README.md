# scanproof

Proofreads a hand transcription against the scan it was typed from, every staff of
every bar, from the pixels. It exists because a person proofreading a hand
transcription misses the same kinds of error that the person typing it made. On
the first piece it was run on (an SSA-and-piano octavo from a phone scan), it
found four errors that a careful hand check had passed.

`verify.py`'s PDF checks read vector PDFs only. This package is the
counterpart for a scan.

## What it reads, and what it compares

From the pixels, for each staff of each bar:

- **Staff lines.** Each line is followed across the page as a sampled curve,
  because phone scans bend. Pitch is a staff step measured from the bottom line
  at that x.
- **Filled heads.** They are found one at a time, each scoring only ink that no
  earlier head has explained. Two heads a third apart touch, and the ellipse
  between them is full of ink. Scoring only unexplained ink stops that midpoint
  from being read as a third head.
- **Hollow and x heads.** These are matched by shape.
- **Filtering.** A head needs a stem at least 2.5 staff spaces long and, if
  filled, at least 0.6 SP thick, which rejects beam corners. Whole notes are
  looked for without a stem, but only in bars the transcription says hold one.
- **Notes beyond the staff.** Their steps are re-derived from the measured
  ledger-line spacing, because the paper compresses near a curled edge.
- **Note values.** Beams or flags are counted at the far end of each chord's
  stem. A run of ink is counted only if it joins the stem, so a marcato wedge or
  a rest beside the stem is not a beam. On the first piece, 1059 of the 1065
  values read agreed with the transcription.
- **Accidentals and augmentation dots.** Each is read by its own classifier.

These readings are aligned to the transcription's events by dynamic programming.
The alignment then reports any disagreement in:

- the set of pitches,
- notehead kind,
- note value,
- printed accidentals, checked against the key and the bar so far,
- dots.

Most findings are the detector's errors, not the transcription's. Every finding
must be looked at on a review sheet.

## Not read

Rests, ties, slurs, articulations, dynamics, lyrics and tremolo strokes are not
read. A tremolo reads as extra beams, which is how one was found. Bar lengths are
the build's job.

## Use

```
python3 -m scanproof bars proof.json        # draft the bar table + overlays; check them by eye
python3 -m scanproof check proof.json       # -> out/findings.json
python3 -m scanproof review proof.json      # -> out/review/review_NN.png
python3 -m scanproof zoom proof.json 51 T 1550 1760    # labelled zoom of one spot
python3 -m scanproof question proof.json 51 T piece.musicxml   # scan above, render below
```

`question` needs cairo. On a Mac with Homebrew's cairo, run it with
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

The config (`proof.json`) is documented in `project.py`. In short, it gives:

- the page images,
- the transcription (`score`, chorale.scoretext, or `musicxml`),
- each system's staves from top to bottom, with each staff's clef and the
  score-text blocks or MusicXML part/staff it is transcribed in,
- the key,
- the bar table.

The **bar table** (`bars.py`) is the one step a person checks. Barline detection
on a phone scan missed five barlines and invented one on the first piece.
`bars` drafts the table from what it detects. It fills in a system end it could
not see (drawn orange on the overlay) and draws every page. Correct the JSON
against the overlays, and copy the printed bar numbers at system starts into
`first_bar`, which then checks itself.

Pixel constants were tuned at a staff space of about 19 px (300 dpi). Each one
is scaled by each page's measured staff space.

## Modules

| module | does |
| --- | --- |
| `geom` | page masks, staff space, staff lines as curves, systems, barline voting |
| `bars` | the bar table: draft, load and check, overlays |
| `heads` | noteheads, stems, beams and flags, ledger steps, accidentals, dots |
| `expected` | the transcription as per-staff, per-bar events (score text or MusicXML) |
| `compare` | alignment and findings |
| `review` | review sheets, labelled zooms, question images |
| `project` | the config, page and geometry caching |
