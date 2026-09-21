# rehearsal-tracks

Turning sheet music into files a community chorus can rehearse from — part-learning
tracks, revoicings, printable parts.

**The work happens in a conversation with Claude**, following the method written
down in `SKILL.md`. You attach a file and type a sentence. You do not have to run
any of the scripts in this repository yourself — Claude does that. The four
sentences below are the ones worth knowing.

Typing `MENU` to Claude prints this same list back to you.

---

### 🎼 &nbsp;PDF → MusicXML

To convert a PDF of sheet music, attach the PDF and write something like:

```
Convert the attached PDF into a MusicXML file.
```

A glyph-based PDF — one that a notation program exported — works far better than
a scan or a photo.

Or, if you already have a MusicXML file from an OMR like Newzik, attach that as
well and write something like:

```
Convert the attached PDF into a MusicXML file. The attached MusicXML file is
Newzik's attempt, in case that helps.
```

It is worth handing over even when the OMR made a mess of the vocal staves; the
accompaniment is usually salvageable.

### ✍️ &nbsp;Plan an arrangement or revoicing

To prepare a list of edits by clicking to select measures and then typing
instructions in plain English, attach the MusicXML and write something like:

```
Prepare a BENCH for the attached MusicXML so I can write arranging/voicing
instructions.
```

A **bench** is a scrolling page of the score with clickable boxes under every beat.
Shift-click a run of beats, type what should happen there, and the pairs come back
as a list of edits. The measure and beat range comes from what you clicked, so you
never have to type it. For example, after clicking to select measure 3 beat 2
through measure 5 beat 4, someone might write something like:

> reassign the soprano part to tenor 2, alto part to bass, tenor part to tenor 1,
> and bass part to baritone

### 🔧 &nbsp;Add kludges for Cantai

To deliberately damage the arrangement to work around Cantai bugs — for example
removing some slurs and writing extra copies of a syllable, so that Cantai's
melisma handling stops holding a note that should have moved on — attach the
MusicXML and write something like:

```
Make the attached MusicXML compatible with Cantai.
```

**This file is for learning tracks only. Never print from it.** You always get the
faithful file as well.

---

Then send the MusicXML to [Sibelius](https://sibelius.com) to play with
[Cantai](https://cantai.app).

### 🎧 &nbsp;Make part-predominant practice tracks

To make one practice track per part, with that part loud, the other voices
faint, and the piano as written, first export one audio file per staff from
Sibelius: solo each staff in turn and use **File > Export > Audio**. Put the
files in one folder, connect that folder to Claude (or attach the files), and
write something like:

```
Make a set of part-predominant tracks using the audio files in the the 2008 Sibelius TTBB folder.
```

Claude checks every file first for silent exports, accidental copies of another
staff, and voices that come in late, then writes one mp3 per part beside the
originals, named for Chorus Connection, e.g. `the 2008 Sibelius TTBB - (Tenor 2)
predominant.mp3`, plus a `the 2008 Sibelius TTBB - Balanced.mp3` with every part at
the same level.

---

## How the whole thing fits together

**Sheet-music PDF → Claude → Sibelius + Cantai**

1. Start from a PDF that a notation program exported (Sibelius, Finale, Dorico,
   MuseScore). Its noteheads, slurs and lyrics are vector objects with exact
   coordinates, so they can be *read*, not recognised. A scan or photo is a
   different, worse job — `check_pdf_type.py` tells you which you have. For a scan,
   OMR is the only route in, and it is worth keeping mainly for the accompaniment:
   the vocal staves are usually faster to transcribe by hand against 300-dpi crops
   than to audit.
2. Claude extracts the notes, rhythms, lyrics, ties and slurs from the glyph stream,
   explodes the condensed choral staves into one monophonic part per voice, applies
   the "who sings here" instructions by hand, and verifies the result (XSD, bar
   lengths, ranges, lyric checks, render-and-compare).
3. Open the MusicXML in Sibelius, put the vocal staves on Cantai voices, and export
   the part-learning tracks.

Steps 7 and 8 of the skill cover the other common ask: re-voicing a piece for a
different ensemble under a director's instructions, collapsing two voices onto one
staff, and laying the result out to be printed and sung from.

## What is here

| File | What it does | Needs |
|---|---|---|
| `SKILL.md` | The whole method, start to finish. The five scripts below are printed inside it in full, so it is self-contained. | — |
| `chorale/` | The piece-independent half, as an importable package: event model, score-text parser, voice collapsing, MusicXML emission, print layout, the bench builder. See `chorale/README.md`. | see below |
| `check_pdf_type.py` | Is this PDF vector (read it directly) or a scan (needs OMR)? | `pdfplumber` |
| `find_performer_instructions.py` | Lists the "Solo", "Basses only", "unis." text that says *who sings*. These never survive OMR and are invisible to every other check. | `pdfplumber` |
| `musicxml_qc.py` | Pre-synthesis QC: bar lengths, lyrics, octave jumps, clef flips. | stdlib |
| `cantai_mode.py` | Post-processes a finished file so Cantai sings every note. Not for printing. | stdlib |
| `lyric_collisions.py` | Renders a laid-out score and reports syllables that would overlap, so bars-per-system is chosen by measurement rather than by squinting. | `verovio`, `lxml` |

## Setup

```
pip install pdfplumber lxml music21 verovio cairosvg pillow numpy fonttools brotli
```

Plus `poppler-utils` for `pdftoppm` / `pdftotext`. The only thing fetched from the
network is the MusicXML schema, at verification time.

## Running the scripts directly

```
python3 check_pdf_type.py score.pdf
python3 find_performer_instructions.py score.pdf --all-text
python3 musicxml_qc.py score.musicxml
python3 cantai_mode.py score.musicxml score-cantai.musicxml --untie-all
python3 lyric_collisions.py score-laid-out.musicxml 7.0
python3 -m chorale.bench score.musicxml -o bench/ --beats 8 --bars-per-system 4
python3 -m chorale.instructions revoicing.json score.txt T1,T2,B1,B2
```

## Licence

`LICENSE.txt` — the Unlicense, a public-domain dedication. It covers the tooling
in this repository: the skill, the scripts and the `chorale` package. It has no
bearing on any published arrangement; no score content is included here.
