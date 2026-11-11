#!/usr/bin/env python3
"""Writes a dark copy of a vector score PDF, element by element, for the player's dark mode.

    python3 player/dark_score.py "score.pdf" "score (dark).pdf"

Notes and rests, with their stems, beams, flags, dots and accidentals, come out warm; staves, barlines, clefs, time signatures,
slurs and words come out cool. Every other color (the lesson marks, say) keeps its hue with its lightness turned over.
"""
import colorsys, math, re, sys
from pypdf import PdfWriter
from pypdf.generic import ContentStream, FloatObject, NameObject, TextStringObject, ByteStringObject

BACKGROUND = (0.118, 0.118, 0.125)
NOTE = (0.957, 0.898, 0.706)      # a slightly yellow white
OTHER = (0.620, 0.682, 0.776)     # a grey with some blue in it

# in Bravura: note heads (Dorico's own at F4BC-F4BE, the rest standard), flags, accidentals, the augmentation dot, rests
NOTE_GLYPHS = [(0xE0A0, 0xE0FF), (0xF4BC, 0xF4BE), (0xE240, 0xE25F), (0xE260, 0xE26F), (0xE1E7, 0xE1E7), (0xE4E0, 0xE4FF)]
# in the Sonata layout of Sibelius's Opus and Finale's Maestro and Helsinki: black, half and whole heads; eighth and 16th flags;
# flat, sharp, natural, double sharp and flat; the dot; whole, half, quarter, eighth, 16th and 32nd rests
SONATA_NOTES = {0xCF, 0xFA, 0x77, 0x6A, 0x4A, 0x72, 0x52, 0x62, 0x23, 0x6E, 0xDC, 0xBA, 0x2E, 0xB7, 0xEE, 0xCE, 0xE4, 0xC5, 0xA8}
SONATA_FONTS = ('Opus', 'Maestro', 'Helsinki')
PATH = {b'm', b'l', b'c', b'v', b'y', b'h', b're'}
PAINT = {b'S', b's', b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*', b'n'}


def flipped(rgb):
    """a color for a dark page: the same hue, its lightness turned over and kept off the extremes"""
    h, l, s = colorsys.rgb_to_hls(*rgb)
    return colorsys.hls_to_rgb(h, 0.12 + 0.8 * (1 - l), s)


def is_note_glyph(u):
    return any(a <= u <= b for a, b in NOTE_GLYPHS)


def sonata_code(u):
    """the Sonata byte of a glyph from its Unicode: a symbol font's private-use copy, or the Mac Roman character of the "Std" fonts"""
    if 0xF000 <= u < 0xF100: return u - 0xF000
    if u >= 0x80:
        try: return chr(u).encode('mac_roman')[0]
        except UnicodeEncodeError: return -1
    return u


def emmentaler_names(font):
    """LilyPond's font: code to glyph name, from its encoding"""
    enc = font.get('/Encoding')
    enc = enc.get_object() if enc is not None else None
    names, code = {}, 0
    for d in (enc.get('/Differences', []) if hasattr(enc, 'get') else []):
        if isinstance(d, (int, float)): code = int(d)
        else: names[code] = str(d).lstrip('/'); code += 1
    return names


def is_note(base, uni):
    if 'Emmentaler' in base: return str(uni).startswith(('noteheads.', 'rests.', 'flags.', 'accidentals.', 'dots.'))
    if 'Bravura' in base or 'Leland' in base: return is_note_glyph(uni)
    if any(m in base for m in SONATA_FONTS) and not any(t in base for t in ('Text', 'Chord', 'Special')): return sonata_code(uni) in SONATA_NOTES
    return False


def to_unicode(font):
    """character code to Unicode, from a font's ToUnicode map"""
    if '/ToUnicode' not in font: return {}
    text = font['/ToUnicode'].get_object().get_data().decode('latin1')
    out = {}
    for block in re.findall(r'beginbfchar(.*?)endbfchar', text, re.S):
        for a, b in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            out[int(a, 16)] = int(b[:4], 16)
    for block in re.findall(r'beginbfrange(.*?)endbfrange', text, re.S):
        # a range's target is a first code counted up from, or a list of one code each
        for a, z, b, listed in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(?:<([0-9A-Fa-f]+)>|\[([^\]]*)\])', block):
            first = int(a, 16)
            if listed:
                for i, u in enumerate(re.findall(r'<([0-9A-Fa-f]+)>', listed)): out[first + i] = int(u[:4], 16)
            else:
                for i in range(first, int(z, 16) + 1): out[i] = int(b[:4], 16) + i - first
    return out


def mul(a, b):
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def subpaths(ops):
    out = []
    for o in ops:
        if o[1] in (b'm', b're') or not out: out.append([])
        out[-1].append(o)
    return out


def points(sub, ctm):
    pts = []
    for args, op in sub:
        v = [float(x) for x in args]
        if op == b're': v = [v[0], v[1], v[0] + v[2], v[1], v[0] + v[2], v[1] + v[3], v[0], v[1] + v[3]]
        for i in range(0, len(v) - 1, 2):
            pts.append((v[i] * ctm[0] + v[i + 1] * ctm[2] + ctm[4], v[i] * ctm[1] + v[i + 1] * ctm[3] + ctm[5]))
    return pts


def is_note_path(sub, paint, ctm, width, lily=False):
    """a stem (a thin vertical line) or a beam (a filled four-sided shape of a beam's thickness at both ends)"""
    pts = points(sub, ctm)
    curved = any(op in (b'c', b'v', b'y') for _, op in sub)
    if len(pts) < 2 or curved: return False
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if paint in (b'S', b's'):
        scale = math.sqrt(abs(ctm[0] * ctm[3] - ctm[1] * ctm[2]))
        return len(pts) == 2 and max(xs) - min(xs) < 0.3 and max(ys) - min(ys) > 4 and width * scale < 0.55
    # LilyPond draws a stem as a thin filled rectangle (its systems' opening lines are the same, but much taller)
    if lily and paint in (b'f', b'F', b'f*') and len(pts) in (4, 5) and max(xs) - min(xs) < 0.5:
        return 6 < max(ys) - min(ys) < 45
    if paint in (b'f', b'F', b'f*') and len(pts) in (4, 5) and max(xs) - min(xs) > 2:
        left = [p[1] for p in pts if abs(p[0] - min(xs)) < 0.3]
        right = [p[1] for p in pts if abs(p[0] - max(xs)) < 0.3]
        return len(left) >= 2 and len(right) >= 2 and 1.0 < max(left) - min(left) < 2.6 and 1.0 < max(right) - min(right) < 2.6
    return False


def rgb_op(rgb, stroke):
    return ([FloatObject(round(c, 4)) for c in rgb], b'RG' if stroke else b'rg')


def recolor(page, writer):
    fonts = {}
    res = page['/Resources'].get_object()
    for k, v in (res.get('/Font') or {}).items():
        f = v.get_object()
        base = str(f.get('/BaseFont', ''))
        fonts[k] = (base, emmentaler_names(f) if 'Emmentaler' in base else to_unicode(f), 2 if f.get('/Subtype') == '/Type0' else 1)
    lily = any('Emmentaler' in f[0] for f in fonts.values())
    cs = ContentStream(page.get_contents(), writer)
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    out = [([], b'q'), rgb_op(BACKGROUND, False),
           ([FloatObject(0), FloatObject(0), FloatObject(w), FloatObject(h)], b're'), ([], b'f'), ([], b'Q')]
    ctm = (1, 0, 0, 1, 0, 0)
    fill, stroke = rgb_op(OTHER, False), rgb_op(OTHER, True)
    line = 1.0
    font = None
    stack = []
    path = []
    counts = {'note glyphs': 0, 'stems': 0, 'beams': 0}
    for args, op in cs.operations:
        if op in PATH:
            path.append((args, op))
            continue
        if op in PAINT and path:
            if op == b'n' or len(path) == 0:
                out += path; out.append((args, op))
            else:
                paint = b'f' if op == b'F' else op
                notes, others = [], []
                for sub in subpaths(path):
                    (notes if is_note_path(sub, paint, ctm, line, lily) else others).append(sub)
                if others:
                    out += [o for s in others for o in s]
                    out.append((args, op))
                if notes:
                    counts['stems' if paint in (b'S', b's') else 'beams'] += len(notes)
                    out.append(rgb_op(NOTE, paint in (b'S', b's')))
                    out += [o for s in notes for o in s]
                    out.append((args, op))
                    out.append(stroke if paint in (b'S', b's') else fill)
            path = []
            continue
        if op == b'q': stack.append((ctm, fill, stroke, line, font))
        elif op == b'Q' and stack: ctm, fill, stroke, line, font = stack.pop()
        elif op == b'cm': ctm = mul(tuple(float(x) for x in args), ctm)
        elif op == b'w': line = float(args[0])
        elif op == b'Tf': font = str(args[0])
        elif op in (b'scn', b'SCN', b'sc', b'SC', b'rg', b'RG') and len(args) == 3:
            rgb = tuple(float(x) for x in args)
            new = rgb_op(OTHER if max(rgb) < 0.01 else flipped(rgb), op in (b'SCN', b'SC', b'RG'))
            if new[1] == b'RG': stroke = new
            else: fill = new
            out.append(new)
            continue
        elif op in (b'g', b'G') and len(args) == 1:
            v = float(args[0])
            new = rgb_op(OTHER if v < 0.01 else flipped((v, v, v)), op == b'G')
            if new[1] == b'RG': stroke = new
            else: fill = new
            out.append(new)
            continue
        elif op == b'Tj' and font in fonts:
            base, uni, width = fonts[font]
            raw = args[0]
            data = raw.original_bytes if hasattr(raw, 'original_bytes') else bytes(raw)
            codes = [int.from_bytes(data[i:i + width], 'big') for i in range(0, len(data) - width + 1, width)]
            if codes and all(is_note(base, uni.get(c, c if width == 1 else 0)) for c in codes):
                counts['note glyphs'] += 1
                out += [rgb_op(NOTE, False), (args, op), fill]
                continue
        out.append((args, op))
    cs.operations = out
    page.replace_contents(cs)
    return counts


def make(src, dst):
    writer = PdfWriter(clone_from=src)
    total = {}
    for page in writer.pages:
        for k, v in recolor(page, writer).items(): total[k] = total.get(k, 0) + v
    writer.compress_identical_objects()
    with open(dst, 'wb') as f: writer.write(f)
    return total


if __name__ == '__main__':
    print(make(sys.argv[1], sys.argv[2]))
