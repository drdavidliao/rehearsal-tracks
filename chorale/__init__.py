"""Tools for turning a scanned choral octavo into MusicXML, and for rearranging it.

    events        the event model: what a note is here
    scoretext     the compact score notation and its parser
    beaming       beam groups
    collapse      two lines onto one staff, and the lyric lines that follow
    musicxml      emission — ScoreSpec, note/direction fragments, part shapes
    harmony       chord symbols
    omr           folding an OMR export in, and repairing it
    printing      page layout, PDF rendering, the SMuFL font fix
    lyriccheck    syllables that would print on top of each other
    instructions  the Revoicing Bench's exported spans

A piece script holds only what is true of that piece: its bars, its dynamics,
its rehearsal letters, its part list.  Everything above is true of any piece.

Checking a *finished* MusicXML file is a separate job with its own standalone
scripts at the repository root — musicxml_qc.py, lyric_collisions.py,
cantai_mode.py, check_pdf_type.py, find_performer_instructions.py.  Those are
printed inside SKILL.md in full and deliberately import nothing, so the skill
stays self-contained; lyriccheck here is the library form of the same
measurement, taking a loaded toolkit instead of a path.
"""
__all__ = ['events', 'scoretext', 'beaming', 'collapse', 'musicxml', 'harmony',
           'omr', 'printing', 'lyriccheck', 'instructions']
