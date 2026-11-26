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
