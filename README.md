# rehearsal-tracks

Skill files, etc. for making part-learning tracks for a community chorus.

## The workflow

**Sheet-music PDF → Claude → Sibelius + Cantai**

1. Start from a PDF that a notation program exported (Sibelius, Finale, Dorico, MuseScore).
   Its noteheads, slurs and lyrics are vector objects with exact coordinates, so they can be
   *read*, not recognised. A scan or photo is a different, worse job — `check_pdf_type.py`
   tells you which you have. For a scan, OMR is the only route in, and it is worth keeping
   mainly for the accompaniment: the vocal staves are usually faster to transcribe by hand
   against 300-dpi crops than to audit (Step 1 of the skill).
2. Give the PDF and `SKILL.md` to Claude. Following the skill, Claude extracts the notes,
   rhythms, lyrics, ties and slurs from the glyph stream, explodes the condensed choral staves
   into one monophonic part per voice, applies the "who sings here" instructions by hand, and
   verifies the result (XSD, bar lengths, ranges, lyric checks, render-and-compare).
   Output: a print-faithful MusicXML, plus — on request — a Cantai version (Step 6 of the skill,
   or `cantai_mode.py` run on the faithful file).
3. Open the MusicXML in Sibelius, put the vocal staves on Cantai voices, and export the
   part-learning tracks.

Steps 7 and 8 of the skill cover the other common ask: re-voicing a piece for a different
ensemble under a director's instructions, collapsing two voices onto one staff, and laying the
result out to be printed and sung from.

## What is here

- `SKILL.md` — the *choral-pdf-to-singable-musicxml* skill: how to turn a choral PDF into
  MusicXML that is correct enough to sing from or to drive singing synthesis, (Step 6) an
  opt-in "Cantai mode" for Sibelius's Cantai singer, and (Steps 7–8) revoicing, closed-score
  collapsing and print layout. The five scripts below are printed inside it in full, so the
  skill is self-contained; they are also here as standalone files for convenience.
- `check_pdf_type.py` — is the PDF vector (read it directly) or a scan (needs OMR)? Needs `pdfplumber`.
- `find_performer_instructions.py` — lists the "Solo", "Basses only", "unis." etc. text that says who
  sings; these never survive OMR and are invisible to every other check. Needs `pdfplumber`.
- `musicxml_qc.py` — pre-synthesis QC of a MusicXML file (bar lengths, lyrics, octave jumps,
  clef flips). Standard library only.
- `cantai_mode.py` — post-processes a finished, print-faithful MusicXML so Cantai sings every note
  through tie chains and melismas. Not for printing. Standard library only.
- `lyric_collisions.py` — renders a laid-out score and reports syllables that would overlap, so
  bars-per-system can be chosen by measurement instead of by squinting at pages.
  Needs `verovio` and `lxml`.

## Typical use

```
pip install pdfplumber lxml music21 verovio cairosvg pillow numpy fonttools brotli
python3 check_pdf_type.py score.pdf
python3 find_performer_instructions.py score.pdf --all-text
# ... build the MusicXML following SKILL.md ...
python3 musicxml_qc.py score.musicxml
python3 cantai_mode.py score.musicxml score-cantai.musicxml --untie-all
python3 lyric_collisions.py score-laid-out.musicxml 7.0
```
