"""Proofread a hand transcription against the scan it was typed from.

    geom      staff lines as sampled curves, systems, barlines
    bars      the bar table: drafted from detected barlines, checked by eye on overlays
    heads     noteheads, stems, beams and flags, accidentals, dots
    expected  the transcription (chorale.scoretext or MusicXML) as per-staff events
    compare   alignment of what was read to what was transcribed, and the findings
    review    review sheets, labelled zooms, question images (scan above, render below)
    project   the config file

`python3 -m scanproof` runs it; see README.md.  Nothing here is piece-specific: a
piece supplies its page images, a config and a bar table.
"""
