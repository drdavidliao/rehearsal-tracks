# rehearsal-tracks

Skill files, etc. for making part-learning tracks for a community chorus.

## What is here

- `SKILL.md` — the *choral-pdf-to-singable-musicxml* skill: how to turn a choral PDF into
  MusicXML that is correct enough to sing from or to drive singing synthesis, and (Step 6) an
  opt-in "Cantai mode" for Sibelius's Cantai singer. The four scripts below are printed inside it
  in full, so the skill is self-contained; they are also here as standalone files for convenience.
- `check_pdf_type.py` — is the PDF vector (read it directly) or a scan (needs OMR)? Needs `pdfplumber`.
- `find_performer_instructions.py` — lists the "Solo", "Basses only", "unis." etc. text that says who
  sings; these never survive OMR and are invisible to every other check. Needs `pdfplumber`.
- `musicxml_qc.py` — pre-synthesis QC of a MusicXML file (bar lengths, lyrics, octave jumps,
  clef flips). Standard library only.
- `cantai_mode.py` — post-processes a finished, print-faithful MusicXML so Cantai sings every note
  through tie chains and melismas. Not for printing. Standard library only.

## Typical use

```
pip install pdfplumber lxml music21 verovio cairosvg pillow numpy
python3 check_pdf_type.py score.pdf
python3 find_performer_instructions.py score.pdf --all-text
# ... build the MusicXML following SKILL.md ...
python3 musicxml_qc.py score.musicxml
python3 cantai_mode.py score.musicxml score-cantai.musicxml --untie-all
```
