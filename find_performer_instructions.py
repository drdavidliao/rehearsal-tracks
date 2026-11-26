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
