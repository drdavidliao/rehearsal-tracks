#!/usr/bin/env python3
"""Is a transcription the whole page? Compare a MusicXML with the score it was made from.

    python3 completeness_check.py FOLDER/completeness.json [--sheets DIR]

SKILL.md, "A transcription is the whole page": every staff and everything printed on it. This script checks that from
the page, independently of how the transcription was made, and writes a stamp beside the MusicXML only when every
check passes. make_map.py refuses a MusicXML without a current stamp.

completeness.json (paths relative to it):

    {
      "musicxml": "Song.musicxml",
      "score": "Song.pdf",
      "staves": {                                  # every staff the score prints, by a name of your choosing,
        "T": [{"part": "Tenor"}, {"part": "Tenor (lower line)"}],   # -> the MusicXML part(s) (id or name) and
        "RH": [{"part": "Piano", "staff": 1}], "LH": [{"part": "Piano", "staff": 2}]      # staff it went to
      },
      "systems": [                                 # every system, in page order, top to bottom
        {"page": 1, "staves": ["RH", "LH"], "bars": [1, 3]}, ...
      ],
      "pages": [1, 11],                            # optional: the pages that are the score, when the PDF has more
      "marks": "marks.tsv",                        # a scan: every mark printed, typed from the page (see below)
      "reviewed": "reviewed.tsv",                  # findings looked at and found to be the reader's (see below)
      "exceptions": [{"what": "...", "user_wrote": "the user's words, quoted"}],
      "known_missing": ["bars 19-20 RH: tremolo, 3 strokes (builder can't write it yet)"]   # fails until emptied
    }

The checks:

  staves    the staves found on each page (scanproof's staff finder) against the systems listed for it; every name
            maps to a MusicXML part (and staff) that exists, and every MusicXML part and staff is printed somewhere.
  bars      the systems' bar ranges run 1, 2, 3 ... without gap or overlap and end at the MusicXML's last bar.
  boxes     rehearsal frames found on the page (player/find_boxes.py's finder) against <rehearsal> in each system's
            bars. Circled or unframed marks are not found by it: those are in marks.tsv for a scan.
  text      every word printed on the page (a vector PDF's text layer; tesseract on a scan) against the MusicXML's
            words: lyrics (by syllable and joined into words), directions, rehearsal marks, credits, part names,
            dynamics. A word with no match is a finding.
  glyphs    a vector PDF in a SMuFL font: dynamics, fermatas and articulations counted on the page against the
            MusicXML's; hairpins as pairs of converging lines against <wedge type="crescendo|diminuendo">.
  marks     a scan: marks.tsv against the MusicXML, both ways. One row per mark as printed:
                bar <tab> staff name <tab> kind <tab> value
            kinds: dyn (p, mf, sfz ...), wedge (cresc|dim), words (the text), tempo (the text, or "q=96"),
            fermata, accent, staccato, tenuto, marcato, breath, caesura, repeat (start|end), ending (1, 2 ...),
            segno, coda, chord (the symbol), rehearsal (the mark). Typing it is a pass over every page in its own
            right, separate from typing the notes; the review sheets draw each row on its bar to check it.

A finding listed in reviewed.tsv (check <tab> the finding's text exactly <tab> why) is reported but does not fail:
that is where a reader's misread (tesseract's "rnf" for "mf", a stain read as a box) is written down after looking.
A check that cannot run (no music font it knows, a scan without marks.tsv) fails rather than passing: what was not
checked is not complete.
"""
import argparse, collections, hashlib, json, os, re, subprocess, sys, tempfile, unicodedata, zipfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanproof import geom  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'player'))
import find_boxes  # noqa: E402

DPI = 300

# SMuFL code points
SMUFL_DYN = {0xE520: 'p', 0xE521: 'm', 0xE522: 'f', 0xE523: 'r', 0xE524: 's', 0xE525: 'z', 0xE526: 'n'}
SMUFL_DYN_RANGE = range(0xE520, 0xE550)
SMUFL_FERMATA = range(0xE4C0, 0xE4D0)
SMUFL_ARTIC = {0xE4A0: 'accent', 0xE4A1: 'accent', 0xE4A2: 'staccato', 0xE4A3: 'staccato', 0xE4A4: 'tenuto',
               0xE4A5: 'tenuto', 0xE4AC: 'marcato', 0xE4AD: 'marcato'}
SMUFL_FONTS = ('Bravura', 'Petaluma', 'Leland', 'Finale Maestro', 'Sebastian', 'Gootville', 'Leipzig', 'November2')

CHORD_KIND = {'major': '', 'minor': 'm', 'dominant': '7', 'major-seventh': 'maj7', 'minor-seventh': 'm7',
              'diminished': 'dim', 'augmented': 'aug', 'suspended-fourth': 'sus4', 'suspended-second': 'sus2',
              'major-sixth': '6', 'minor-sixth': 'm6', 'dominant-ninth': '9', 'half-diminished': 'm7b5',
              'diminished-seventh': 'dim7', 'power': '5'}
CHORDS_RE = re.compile(r'(?:[a-g][b#]?(?:maj|min|m|dim|aug|sus|add|alt|no|[b#]?\d{1,2})*(?:[a-g][b#]?)?)+')
# the text of a metronome mark printed as words ("(q = ca. 160)"): its number is compared as the tempo mark instead
METRO_WORD = re.compile(r'\d+|ca|q|h|e')
MARK_KINDS = {'dyn', 'wedge', 'words', 'tempo', 'fermata', 'accent', 'staccato', 'tenuto', 'marcato', 'breath',
              'caesura', 'repeat', 'ending', 'segno', 'coda', 'chord', 'rehearsal'}


def norm(w):
    # accidentals in chord symbols are letters here: dropped, "F#" would match "F"
    w = w.replace('\u266d', 'b').replace('\u266f', 'sharp').replace('#', 'sharp').replace('\u266e', 'natural')
    w = unicodedata.normalize('NFKD', w).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', w)


# ---------------------------------------------------------------- the MusicXML

def load_xml(path):
    if path.lower().endswith('.mxl'):
        z = zipfile.ZipFile(path)
        root = ET.fromstring(z.read([n for n in z.namelist() if n.endswith(('.xml', '.musicxml'))
                                     and not n.startswith('META')][0]))
    else:
        root = ET.parse(path).getroot()
    return root


def xml_facts(root):
    """parts {id: (name, nstaves)}; per bar the marks [(part, staff, kind, value)]; the text bag; last bar number"""
    parts = {}
    for sp in root.iter('score-part'):
        parts[sp.get('id')] = [(sp.findtext('part-name') or '').strip(), 1]
    marks = collections.defaultdict(list)
    onsets = collections.defaultdict(list)  # bar -> [(part, staff, kind, onset in divisions)] for marks on notes
    dyn_at = []                               # (part, staff, bar, onset in divisions, value) of every dynamic
    starts = collections.defaultdict(set)     # (part, staff, bar) -> onsets (divisions) where a note starts
    lyric_words, other_text = [], []
    lyr = collections.Counter()  # (part id, bar) -> syllables sung there
    verses = collections.defaultdict(list)  # (part id, verse number) -> [(bar, text)] in order
    last = 0
    for c in root.iter('credit-words'): other_text.append(c.text or '')
    for t in ('work-title', 'movement-title', 'creator', 'rights'):
        for e in root.iter(t): other_text.append(e.text or '')
    for pid, (name, _) in parts.items(): other_text.append(name)
    for part in root.iter('part'):
        pid = part.get('id')
        word = ''
        for meas in part.iter('measure'):
            try: num = int(re.match(r'\d+', meas.get('number', '0')).group())
            except AttributeError: continue
            last = max(last, num)
            st = meas.find('attributes/staves')
            if st is not None: parts[pid][1] = max(parts[pid][1], int(st.text))
            pos, last_on = 0, 0
            for el in meas:
                staff = int(el.findtext('staff') or 1)
                if el.tag == 'backup': pos -= int(el.findtext('duration') or 0); continue
                if el.tag == 'forward': pos += int(el.findtext('duration') or 0); continue
                if el.tag == 'direction':
                    off_ = int(el.findtext('offset') or 0)
                    for dyn_ in el.iter('dynamics'):
                        for k_ in dyn_: dyn_at.append((pid, staff, num, pos + off_, k_.tag))
                    for dt in el.findall('direction-type'):
                        for d in dt:
                            if d.tag == 'dynamics':
                                for k in d: marks[num].append((pid, staff, 'dyn', k.text if k.tag == 'other-dynamics' else k.tag))
                            elif d.tag == 'wedge' and d.get('type') in ('crescendo', 'diminuendo'):
                                marks[num].append((pid, staff, 'wedge', 'cresc' if d.get('type') == 'crescendo' else 'dim'))
                            elif d.tag == 'words' and (d.text or '').strip():
                                marks[num].append((pid, staff, 'words', d.text.strip())); other_text.append(d.text)
                            elif d.tag == 'rehearsal':
                                marks[num].append((pid, staff, 'rehearsal', (d.text or '').strip())); other_text.append(d.text or '')
                            elif d.tag == 'metronome' and d.findtext('per-minute'):
                                # a metronome with no number is a swing or note-equals-note figure, not a tempo mark
                                marks[num].append((pid, staff, 'tempo', 'q=' + d.findtext('per-minute')))
                            elif d.tag in ('segno', 'coda'):
                                marks[num].append((pid, staff, d.tag, ''))
                elif el.tag == 'barline':
                    r = el.find('repeat')
                    if r is not None: marks[num].append((pid, 0, 'repeat', 'start' if r.get('direction') == 'forward' else 'end'))
                    e = el.find('ending')
                    if e is not None and e.get('type') == 'start': marks[num].append((pid, 0, 'ending', e.get('number')))
                elif el.tag == 'harmony':
                    k = el.find('kind')
                    alt = {'-1': 'b', '1': '#'}.get(el.findtext('root/root-alter') or '', '')
                    txt = (k.get('text') or 'N.C.') if k is not None and k.text == 'none' else \
                        (el.findtext('root/root-step') or '') + alt + (k.get('text') if k is not None and k.get('text') is not None
                                                                         else CHORD_KIND.get(k.text if k is not None else '', ''))
                    b = el.find('bass')
                    if b is not None: txt += '/' + (b.findtext('bass-step') or '') + {'-1': 'b', '1': '#'}.get(b.findtext('bass-alter') or '', '')
                    # printed as one symbol ("C6/G"), or with the bass apart ("C6" over "/G"), or with the kind raised
                    marks[num].append((pid, staff, 'chord', txt)); other_text += [txt.replace('/', ''), txt.replace('/', ' ')]
                    if k is not None and k.get('text'): other_text.append(k.get('text'))
                elif el.tag == 'note':
                    on = last_on if el.find('chord') is not None else pos
                    if el.find('rest') is None and el.find('grace') is None and \
                            not any(t_.get('type') == 'stop' for t_ in el.findall('tie')):
                        starts[(pid, staff, num)].add(on)
                    if el.find('chord') is None and el.find('grace') is None:
                        last_on = pos; pos += int(el.findtext('duration') or 0)
                    n = el.find('notations')
                    if n is not None:
                        for f in n.iter('fermata'):
                            marks[num].append((pid, staff, 'fermata', '')); onsets[num].append((pid, staff, 'fermata', on))
                        for a in n.iter('articulations'):
                            for k in a:
                                kind = {'strong-accent': 'marcato', 'breath-mark': 'breath'}.get(k.tag, k.tag)
                                if kind in MARK_KINDS:
                                    marks[num].append((pid, staff, kind, '')); onsets[num].append((pid, staff, kind, on))
                        for d in n.iter('dynamics'):
                            for k in d: marks[num].append((pid, staff, 'dyn', k.tag))
                    for ly in el.findall('lyric'):
                        t = ly.findtext('text') or ''
                        if norm(t): lyr[(pid, num)] += 1; verses[(pid, ly.get('number', '1'))].append((num, t))
                        syl = ly.findtext('syllabic') or 'single'
                        lyric_words.append(t)
                        if syl in ('single', 'begin'): word = t
                        else: word += t
                        if syl in ('single', 'end'): lyric_words.append(word)
    bag = set()
    for s in lyric_words + other_text:
        for w in re.split(r'[\s/]+', s or ''):
            if norm(w): bag.add(norm(w))
        if norm(s or ''): bag.add(norm(s))
    for m in marks.values():
        for (_, _, k, v) in m:
            if k == 'dyn' and v: bag.add(norm(v))
    lbag = {norm(w) for w in lyric_words if norm(w)}
    xml_facts.dyn_at, xml_facts.starts = dyn_at, starts
    return parts, marks, bag, last, lyr, lbag, verses, onsets


def resolve(parts, ref):
    """{"part": id or name, "staff": n} -> (part id, staff or None)"""
    p = ref['part']
    if p not in parts:
        hits = [k for k, (name, _) in parts.items() if name == p]
        if len(hits) != 1: raise KeyError(f'no single MusicXML part called {p!r} (parts: {[v[0] for v in parts.values()]})')
        p = hits[0]
    return p, ref.get('staff')


# ---------------------------------------------------------------- the page

def render(pdf, outdir):
    subprocess.run(['pdftoppm', '-r', str(DPI), '-png', pdf, os.path.join(outdir, 'p')], check=True)
    return sorted(os.path.join(outdir, f) for f in os.listdir(outdir) if f.startswith('p') and f.endswith('.png'))


def is_vector(pdf):
    import pdfplumber
    with pdfplumber.open(pdf) as d:
        chars = sum(len(p.chars) for p in d.pages[:3])
        imgs = sum(len(p.images) for p in d.pages[:3])
    return chars > 200 or not imgs


def page_words_vector(pdf):
    """[(page, x, y, word)] from the text layer, in points; music-font glyphs left out"""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf) as d:
        for pi, p in enumerate(d.pages, 1):
            # some text is drawn twice in one place (a bold effect): dedupe_chars keeps one copy
            for w in p.dedupe_chars().extract_words(extra_attrs=['fontname'], x_tolerance=1.2):
                if any(f in w['fontname'] for f in SMUFL_FONTS + ('Opus', 'Helsinki', 'Maestro', 'Sonata', 'Petrucci')):
                    continue
                out.append((pi, w['x0'], w['top'], w['text']))
    return out


def page_words_scan(pngs):
    out = []
    for pi, png in enumerate(pngs, 1):
        r = subprocess.run(['tesseract', png, '-', '--psm', '11', 'tsv'], capture_output=True, text=True)
        for line in r.stdout.splitlines()[1:]:
            f = line.split('\t')
            if len(f) < 12 or not f[11].strip(): continue
            try: conf = float(f[10])
            except ValueError: continue
            w = f[11].strip()
            # a scan's staves read as runs of punctuation and stray letters; a word worth matching has two letters
            if conf < 70 or len(re.sub(r'[^A-Za-z]', '', w)) < 2: continue
            out.append((pi, int(f[6]) * 72 / DPI, int(f[7]) * 72 / DPI, w))
    return out


def band_lines_vector(pdf):
    """[(page, y, letters)]: the lyric lines on each page. Lyrics are set in the text font and size used most on the
    page under staves; letters are gathered by line (tops within 3 pt) and read left to right. A glyph the text layer
    can't name (a ligature) is '?'."""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf) as d:
        allc = []
        for pi, p in enumerate(d.pages, 1):
            for c in p.dedupe_chars().chars:
                if any(f in c['fontname'] for f in SMUFL_FONTS + ('Opus', 'Helsinki', 'Maestro', 'Sonata', 'Petrucci')): continue
                allc.append((pi, c))
        fonts = collections.Counter((c['fontname'], round(c['size'], 1)) for _, c in allc if c['text'].isalpha())
        if not fonts: return out
        lf = fonts.most_common(1)[0][0]
        rows = collections.defaultdict(list)
        for pi, c in allc:
            if (c['fontname'], round(c['size'], 1)) != lf: continue
            rows[pi].append(c)
        for pi, cs in rows.items():
            cs.sort(key=lambda c: c['top'])
            line = []
            for c in cs + [None]:
                if c is None or (line and c['top'] - line[0]['top'] > 3):
                    t = ''.join('?' if x['text'].startswith('(cid') else norm(x['text']) for x in sorted(line, key=lambda x: x['x0']))
                    if t.strip('?'): out.append((pi, line[0]['top'], t))
                    line = []
                if c is not None: line.append(c)
    return out


def glyphs_vector(pdf):
    """[(page, y, kind)] for SMuFL dynamics (a run of letters is one), fermatas, articulations, and hairpins; None if no
    SMuFL font is used, so nothing was counted"""
    import pdfplumber
    out, smufl = [], False
    with pdfplumber.open(pdf) as d:
        for pi, p in enumerate(d.pages, 1):
            run = []
            for c in sorted(p.chars, key=lambda c: (round(c['top']), c['x0'])):
                if not any(f in c['fontname'] for f in SMUFL_FONTS): continue
                smufl = True
                cp = ord(c['text'][0]) if c['text'] else 0
                if cp in SMUFL_FERMATA: out.append((pi, c['top'], 'fermata'))
                elif cp in SMUFL_ARTIC: out.append((pi, c['top'], SMUFL_ARTIC[cp]))
                if cp in SMUFL_DYN_RANGE:
                    # letters of one dynamic sit side by side: count a run as one marking
                    if run and abs(run[-1]['top'] - c['top']) < 1 and c['x0'] - run[-1]['x1'] < 2: run.append(c)
                    else: run = [c]; out.append((pi, c['top'], 'dyn'))
            # a hairpin drawn as one path (Dorico: a filled outline): its points gather at two ends, open (4 pt or more
            # apart) at one and closed (a point or so) at the other
            for c in p.curves:
                pts = c.get('pts') or []
                if len(pts) < 4: continue
                xs = np.array([q[0] for q in pts]); ys = np.array([q[1] for q in pts])
                if xs.max() - xs.min() < 10 or ys.max() - ys.min() > 16: continue
                lo, hi = ys[xs < xs.min() + 2], ys[xs > xs.max() - 2]
                if len(lo) < 2 or len(hi) < 1: continue
                sl, sh = lo.max() - lo.min(), (hi.max() - hi.min() if len(hi) > 1 else 0)
                if (sl >= 4 and sh <= 1.5) or (sh >= 4 and sl <= 1.5): out.append((pi, ys.mean(), 'wedge'))
            # or as two lines meeting at one end
            segs = [l for l in p.lines if abs(l['x1'] - l['x0']) > 8]
            segs = [l for l in segs if 0.005 < abs((l['bottom'] - l['top']) / (l['x1'] - l['x0'])) < 0.2]
            ends = collections.Counter()
            for l in segs:
                for e in ((round(l['x0']), round(l['top'])), (round(l['x1']), round(l['bottom'])),
                          (round(l['x0']), round(l['bottom'])), (round(l['x1']), round(l['top']))):
                    ends[e] += 1
            out += [(pi, e[1], 'wedge') for e, v in ends.items() if v >= 2]
    return out if smufl else None


# ---------------------------------------------------------------- the checks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--sheets', help='where to draw the pages with what each check found (default: beside config)')
    a = ap.parse_args()
    cdir = os.path.dirname(os.path.abspath(a.config))
    cfg = json.load(open(a.config))
    rel = lambda p: os.path.join(cdir, p)
    xml_path, pdf = rel(cfg['musicxml']), rel(cfg['score'])
    parts, xmarks, bag, last, xlyr, lbag, xverses, xonsets = xml_facts(load_xml(xml_path))
    reviewed = set()
    if cfg.get('reviewed') and os.path.exists(rel(cfg['reviewed'])):
        for line in open(rel(cfg['reviewed']), encoding='utf-8'):
            f = line.rstrip('\n').split('\t')
            if len(f) >= 3 and not line.startswith('#'): reviewed.add((f[0], f[1]))
    fails, notes = collections.defaultdict(list), collections.defaultdict(list)

    def finding(check, text):
        (notes if (check, text) in reviewed else fails)[check].append(text)

    systems = cfg['systems']
    names = cfg['staves']
    # -- staves: names map, every part printed
    used = set()
    for n, refs in names.items():
        for r in refs:
            try: pid, st = resolve(parts, r)
            except KeyError as e: finding('staves', f'staff {n}: {e}'); continue
            if st and st > parts[pid][1]: finding('staves', f'staff {n}: part {parts[pid][0]} has no staff {st}')
            if st: used.add((pid, st))
            else: used.update((pid, k) for k in range(1, parts[pid][1] + 1))
    for pid, (name, ns) in parts.items():
        for k in range(1, ns + 1):
            if (pid, k) not in used: finding('staves', f'MusicXML part {name!r} staff {k} is not any printed staff')
    for s in systems:
        for n in s['staves']:
            if n not in names: finding('staves', f'page {s["page"]}: staff {n!r} is not in "staves"')
    # -- bars
    nxt = 0 if systems and systems[0]['bars'][0] == 0 else 1   # a printed pickup is bar 0
    for s in systems:
        b0, b1 = s['bars']
        if b0 != nxt: finding('bars', f'page {s["page"]}: a system starts at bar {b0}, the one before ended at {nxt - 1}')
        nxt = b1 + 1
    if nxt - 1 != last: finding('bars', f'the systems end at bar {nxt - 1}, the MusicXML at {last}')
    # -- the page
    tmp = tempfile.mkdtemp()
    pngs = render(pdf, tmp)
    # the pages the transcription covers: "pages" [first, last] when the PDF holds more (parts after the score)
    scored = set(range(cfg['pages'][0], cfg['pages'][1] + 1)) if cfg.get('pages') else set(range(1, len(pngs) + 1))
    vector = is_vector(pdf)
    sheets = a.sheets or os.path.join(cdir, 'completeness-out'); os.makedirs(sheets, exist_ok=True)
    draws = collections.defaultdict(list)  # page -> [(x, y, colour, label)] in points
    sys_y = {}  # (page, index on page) -> (top, bottom) in points
    staff_band = []  # (page, system on page, staff name, staff bottom, next staff's top): where its words print
    for pi, png in enumerate(pngs, 1):
        if pi not in scored: continue
        page = geom.Page(png)
        found = geom.staves(page)
        mine = [s for s in systems if s['page'] == pi]
        want = sum(len(s['staves']) for s in mine)
        if len(found) != want:
            finding('staves', f'page {pi}: {len(found)} staves on the page, {want} listed in its systems')
        ys = [np.interp(page.gray.shape[1] / 2, *f['samples'][0]) * 72 / DPI for f in found]
        ye = [np.interp(page.gray.shape[1] / 2, *f['samples'][4]) * 72 / DPI for f in found]
        i = 0
        for si, s in enumerate(mine):
            k = len(s['staves'])
            if i + k <= len(found): sys_y[(pi, si)] = (ys[i], ye[i + k - 1])
            for j, n in enumerate(s['staves']):
                if i + j < len(found):
                    draws[pi].append((40, ys[i + j], 'blue', n))
                    nxt_top = ys[i + j + 1] if i + j + 1 < len(found) else ye[i + j] + 60
                    staff_band.append((pi, si, n, ye[i + j], nxt_top))
            i += k
    # -- boxes
    xreh = {b: [v for (_, _, k, v) in m if k == 'rehearsal'] for b, m in xmarks.items()}
    xreh = {b: v for b, v in xreh.items() if v}
    seen_reh = set()
    for pi, png in enumerate(pngs, 1):
        if pi not in scored: continue
        small = os.path.join(tmp, f'b{pi}.png')
        Image.open(png).resize((int(Image.open(png).width * 150 / DPI), int(Image.open(png).height * 150 / DPI))).save(small)
        mine = [(si, s) for si, s in enumerate([s for s in systems if s['page'] == pi])]
        for x0, y0, x1, y1 in find_boxes.boxes(small):
            near = [(si, s) for si, s in mine if (pi, si) in sys_y and sys_y[(pi, si)][0] - 45 <= y1 <= sys_y[(pi, si)][0] + 15]
            if not near: continue
            si, s = min(near, key=lambda t: abs(y1 - sys_y[(pi, t[0])][0]))
            bars = [b for b in xreh if s['bars'][0] <= b <= s['bars'][1]]
            draws[pi].append((x0, y0, 'green' if bars else 'red', 'box'))
            if bars: seen_reh.update(bars)
            else: finding('boxes', f'page {pi} system {si + 1} (bars {s["bars"][0]}-{s["bars"][1]}): a box at x={x0:.0f}, no <rehearsal> in those bars')
    for b in sorted(xreh):
        if b not in seen_reh:
            notes['boxes'].append(f'bar {b}: <rehearsal> {xreh[b]} with no frame found (circled or unframed marks are not looked for)')
    # -- text
    words = [w for w in (page_words_vector(pdf) if vector else page_words_scan(pngs)) if w[0] in scored]
    joined = ''.join(sorted(bag, key=len, reverse=True))
    for pi, x, y, w in words:
        # a glyph the text layer can't name (a ligature, "(cid:33)" for fl): match what is around it
        frags = [norm(f) for f in re.split(r'\(cid:\d+\)', w)]
        n = ''.join(frags)
        if not n or n.isdigit() or n in bag: continue
        if len(n) >= 4 and n in joined: continue
        if '(cid:' in w and all(len(f) < 2 or f in joined for f in frags): continue
        # hyphenated syllables print apart: "Christ-" "mas"; a syllable is in the bag on its own
        finding('text', f'page {pi}: {w!r} at x={x:.0f} y={y:.0f}')
        draws[pi].append((x, y, 'red', w))
    # -- lyrics, staff by staff: each line of words printed under a staff, letter for letter, against a verse its
    # part(s) sing in those bars. Two parts on one staff print their words once: either part's verse may match.
    lyric_lines = band_lines_vector(pdf) if vector else None
    dir_words = {norm(v) for m in xmarks.values() for (_, _, k, v) in m if k == 'words' and norm(v)}
    for pi, si, n, y0, y1 in staff_band:
        s_ = [s for s in systems if s['page'] == pi][si]
        pids = set()
        for r in names.get(n, []):
            try: pids.add(resolve(parts, r)[0])
            except KeyError: pass
        # a staff whose parts sing no words anywhere (a piano) has none to compare; what prints under it is directions
        if not pids or not any(xlyr[(pid, b)] for pid in pids for b in range(1, last + 1)): continue
        b0, b1 = s_['bars']
        sung = set()
        for (pid, num), seq in xverses.items():
            if pid in pids:
                t = norm(''.join(x for b, x in seq if b0 <= b <= b1))
                if t: sung.add(t)
        if vector:
            pat = lambda t: re.compile(''.join('.{1,3}' if c == '?' else re.escape(c) for c in t))
            lines = [t for (p2, y, t) in lyric_lines if p2 == pi and y0 < y < y1]
            matched = {v for t in lines for v in sung if pat(t).fullmatch(v)}
            for t in lines:
                if any(pat(t).fullmatch(v) for v in sung): continue
                # the chord symbols over a piano staff are set in the same font: a line that reads as nothing but chord
                # symbols is theirs (the text check has matched them already)
                if CHORDS_RE.fullmatch(t): continue
                # words of a direction set in the same font on the same line as the chord symbols ("pedal ad lib.")
                rest = t
                for wd in sorted(dir_words, key=len, reverse=True): rest = rest.replace(wd, '')
                if not rest or CHORDS_RE.fullmatch(rest): continue
                finding('lyrics', f'page {pi} system {si + 1} staff {n} (bars {b0}-{b1}): printed {t!r}, '
                                  f'not a verse in the MusicXML: {sorted(sung)}')
            for v in sorted(sung - matched):
                if not any(not CHORDS_RE.fullmatch(t) or len(t) == len(v) for t in lines if not any(pat(t).fullmatch(w) for w in sung)):
                    finding('lyrics', f'page {pi} system {si + 1} staff {n} (bars {b0}-{b1}): the MusicXML sings {v!r}, '
                                      f'printed nowhere under the staff')
        else:
            got = [norm(w) for (p2, x, y, w) in sorted(words, key=lambda t: (round(t[2] / 4), t[1])) if p2 == pi and y0 < y < y1]
            got = ''.join(g for g in got if g)
            import difflib
            best = max((difflib.SequenceMatcher(None, got, v).ratio() for v in sung), default=0 if got else 1)
            if sung and best < 0.75:
                finding('lyrics', f'page {pi} system {si + 1} staff {n} (bars {b0}-{b1}): the words read under it match '
                                  f'its verse at {best:.0%}: read {got[:60]!r}')
    # -- glyphs / marks
    count = collections.Counter(k for m in xmarks.values() for (_, _, k, _) in m)
    if vector:
        g = glyphs_vector(pdf)
        g = None if g is None else [t for t in g if t[0] in scored]
        if g is None:
            finding('glyphs', 'no SMuFL music font on the page: dynamics, fermatas, articulations and hairpins not counted')
        else:
            # per system, so a missing mark in one place cannot hide behind an extra one elsewhere: a glyph belongs to
            # the system whose top is the last one above it (less 40 pt, for marks over the top staff)
            # a mark belongs to the system whose staves it lies within, or failing that the nearest one: marks hang
            # below a system's bottom staff as far as they stand above its top one
            pg = collections.Counter()
            for pi, y, kind in g:
                spans = [(si, t, b) for (p2, si), (t, b) in sys_y.items() if p2 == pi]
                if not spans: continue
                si = min(spans, key=lambda s3: 0 if s3[1] <= y <= s3[2] else min(abs(y - s3[1]), abs(y - s3[2])))[0]
                pg[(pi, si, kind)] += 1
            for (pi, si), (t, _) in sorted(sys_y.items()):
                s_ = [s for s in systems if s['page'] == pi][si]
                xm = collections.Counter(k for b in range(s_['bars'][0], s_['bars'][1] + 1) for (_, _, k, _) in xmarks.get(b, []))
                for kind in ('dyn', 'fermata', 'wedge', 'accent', 'staccato', 'tenuto', 'marcato'):
                    if pg[(pi, si, kind)] != xm[kind]:
                        finding('glyphs', f'page {pi} system {si + 1} (bars {s_["bars"][0]}-{s_["bars"][1]}) {kind}: '
                                          f'{pg[(pi, si, kind)]} on the page, {xm[kind]} in the MusicXML')
    else:
        mp = cfg.get('marks')
        if not mp or not os.path.exists(rel(mp)):
            finding('marks', 'a scan with no marks.tsv: the marks printed have not been typed from the page, so not checked')
        else:
            typed = collections.Counter()
            for ln, line in enumerate(open(rel(mp), encoding='utf-8'), 1):
                if not line.strip() or line.startswith('#'): continue
                f = line.rstrip('\n').split('\t')
                if len(f) < 3 or f[2] not in MARK_KINDS: finding('marks', f'marks.tsv line {ln}: not "bar, staff, kind, value": {line.strip()!r}'); continue
                bar, st, kind, val = int(f[0]), f[1], f[2], (f[3] if len(f) > 3 else '').strip()
                typed[(bar, st, kind, norm(val))] += 1
            have = collections.Counter()
            # which printed staff a part's staff is in a given bar: a score may print two parts on one staff in some
            # systems and on two in others, so it is the name, among that bar's system's staves, that maps to it
            cands = collections.defaultdict(list)
            for n, refs in names.items():
                for r in refs:
                    try: pid, st = resolve(parts, r)
                    except KeyError: continue
                    for k in ([st] if st else range(1, parts[pid][1] + 1)): cands[(pid, k)].append(n)

            class _Back:
                def get(self, key, default='?', bar=None):
                    ns = cands.get(key, [])
                    if bar is not None:
                        here = [s3 for s3 in systems if s3['bars'][0] <= bar <= s3['bars'][1]]
                        if here: ns = [n for n in ns if n in here[0]['staves']] or ns
                    return ns[0] if ns else default
            back = _Back()
            # parts sharing a printed staff (Tenor 1 and 2 on one staff) each carry a mark printed once on it: the
            # staff shows the most any one of its parts has
            per_part = collections.Counter()
            for b, m in xmarks.items():
                for (pid, st, kind, val) in m:
                    per_part[(b, back.get((pid, st or 1), '?', b), pid, kind, norm(val))] += 1
            for (b, name, pid, kind, val), c in per_part.items():
                have[(b, name, kind, val)] = max(have[(b, name, kind, val)], c)
            # a mark on a note: parts sharing a staff that carry it at the same moment print it once (a unison, or a
            # chord split between them); at different moments (two voices, each with its own fermata) it prints for each
            note_kinds = {'fermata', 'accent', 'staccato', 'tenuto', 'marcato', 'breath', 'caesura'}
            for k_ in [k_ for k_ in have if k_[2] in note_kinds]: del have[k_]
            moments = collections.defaultdict(set)
            for b, lst in xonsets.items():
                for (pid, st, kind, on) in lst:
                    moments[(b, back.get((pid, st or 1), '?', b), kind)].add(on)
            for (b, name, kind), ons in moments.items(): have[(b, name, kind, '')] = len(ons)
            # a system-wide mark (repeat, rehearsal, tempo ...) is written on every part: one row in marks.tsv, '*' staff
            sysw = collections.Counter()
            for (b, st, kind, val), c in list(have.items()):
                if kind in ('repeat', 'ending', 'rehearsal', 'tempo', 'segno', 'coda'):
                    sysw[(b, '*', kind, val)] = max(sysw[(b, '*', kind, val)], 1 if c else 0)
                    del have[(b, st, kind, val)]
            have.update({k: v for k, v in sysw.items() if v})
            # compare marks as they print, not as one reader or the other filed them:
            #  - text (words, and tempo words) word by word per bar, wherever on the system it stands: "unis. (opt.
            #    solo)" typed as two items is the same print as one item, and tempo words are words;
            #  - a dynamic, hairpin or word between a grand staff's two staves belongs to the pair, not to one of them.
            # a grand staff: one part printed on two numbered staves
            pair = collections.defaultdict(dict)
            for n, refs in names.items():
                for r in refs:
                    try: pid, st = resolve(parts, r)
                    except KeyError: continue
                    if st: pair[pid][st] = n
            grp = {n: '+'.join(sorted(v.values())) for v in pair.values() if len(v) > 1 for n in v.values()}

            def canon(counter):
                out = collections.Counter()
                for (b, st, kind, val), c in counter.items():
                    if kind == 'chord' and val == 'nc':
                        # "N.C." stands in the chord-symbol row but is words: one reader files it as a chord, the other not
                        out[(b, '(text)', 'words', 'nc')] += c
                    elif kind in ('words', 'tempo') and not re.fullmatch(r'[qhew]\d+', val):
                        raw_ = val
                        out[(b, '(text)', 'words', val)] += c
                    elif kind in ('dyn', 'wedge'):
                        out[(b, grp.get(st, st), kind, val)] += c
                    elif kind == 'tempo':
                        # a metronome mark is one per system, however often the engraver repeats it (over the voices
                        # and again over the piano)
                        out[(b, '*', kind, val)] = 1
                    else:
                        out[(b, st, kind, val)] += c
                return out
            typed_raw = collections.Counter()
            for ln, line in enumerate(open(rel(mp), encoding='utf-8'), 1):
                if not line.strip() or line.startswith('#'): continue
                f = line.rstrip('\n').split('\t')
                if len(f) < 3 or f[2] not in MARK_KINDS: continue
                v = (f[3] if len(f) > 3 else '').strip()
                if f[2] in ('words', 'tempo') and not re.fullmatch(r'[qhew]\.?\s*=\s*\d+', v):
                    for wd in re.split(r'[\s,]+', v):
                        if norm(wd) and not METRO_WORD.fullmatch(norm(wd)): typed_raw[(int(f[0]), '(text)', 'words', norm(wd))] += 1
                else: typed_raw[(int(f[0]), f[1], f[2], norm(v))] += 1
            have_w = collections.Counter()
            for b, m in xmarks.items():
                seen_txt = collections.Counter()
                for (pid, st, kind, val) in m:
                    if kind == 'words':
                        for wd in re.split(r'[\s,]+', val):
                            if norm(wd): seen_txt[norm(wd)] += 1
                # a word printed once over a staff shared by two parts sits on both parts in the MusicXML: count each
                # printed staff once (the most any of its parts has), and add up the staves
                per = collections.Counter()
                for (pid, st, kind, val) in m:
                    if kind == 'words':
                        for wd in re.split(r'[\s,]+', val):
                            if norm(wd) and not METRO_WORD.fullmatch(norm(wd)): per[(back.get((pid, st or 1), pid, b), pid, norm(wd))] += 1
                best = collections.Counter()
                for (staff_, pid, wd), c in per.items(): best[(staff_, wd)] = max(best[(staff_, wd)], c)
                for (staff_, wd), c in best.items(): have_w[(b, '(text)', 'words', wd)] += c
            typed = canon(collections.Counter({k: v for k, v in typed_raw.items() if k[1] != '(text)'}))
            typed.update({k: v for k, v in typed_raw.items() if k[1] == '(text)'})
            have = canon(collections.Counter({k: v for k, v in have.items() if k[2] != 'words'}))
            have.update(have_w)
            for k in sorted(set(typed) | set(have), key=str):
                if typed[k] != have[k]:
                    finding('marks', f'bar {k[0]} staff {k[1]} {k[2]} {k[3]!r}: {typed[k]} typed from the page, {have[k]} in the MusicXML')
    # -- dynamics on the right staff: a dynamic marks the part it stands with, so that part has a note starting at it
    # or within the next beat (an entry after a rest). A dynamic on a part that is resting there was put on the
    # wrong staff: one reader read every voice's dynamics one staff low. Divisions per quarter from the file.
    divs = [int(d.text) for d in load_xml(xml_path).iter('divisions')]
    div_ = divs[0] if divs else 1
    for (pid, st, b, on, val) in xml_facts.dyn_at:
        if parts.get(pid, ('', 0))[0].lower().startswith(('piano', 'pno', 'keyboard')): continue
        if not any(0 <= x - on <= div_ for x in xml_facts.starts.get((pid, st, b), ())):
            finding('dynstaff', f'bar {b} {parts[pid][0]}: {val} where the part has no note starting (within a beat)')
    # -- what is known to be printed and not yet in the file (a builder that cannot write it yet): listed so the check
    # cannot pass while it is missing
    for k in cfg.get('known_missing', []):
        finding('known', f'known missing: {k}')
    # -- report
    for pi in draws:
        im = Image.open(pngs[pi - 1]).convert('RGB'); d = ImageDraw.Draw(im)
        for x, y, c, t in draws[pi]:
            X, Y = x * DPI / 72, y * DPI / 72
            d.rectangle((X - 4, Y - 4, X + 60, Y + 30), outline=c, width=4); d.text((X, Y - 24), t, fill=c)
        im.save(os.path.join(sheets, f'page {pi}.png'))
    exc = cfg.get('exceptions', [])
    ok = not fails
    print(f'{os.path.basename(xml_path)} against {os.path.basename(pdf)} ({"vector" if vector else "scan"})')
    for chk in ('staves', 'bars', 'boxes', 'text', 'lyrics', 'glyphs', 'marks', 'dynstaff', 'known'):
        f, n = fails.get(chk, []), notes.get(chk, [])
        print(f'  {chk:7s} {"FAIL" if f else "ok"}' + (f' ({len(f)})' if f else '') + (f', {len(n)} noted' if n else ''))
        for t in f[:60]: print('      ' + t)
        if len(f) > 60: print(f'      ... {len(f) - 60} more')
        for t in n[:20]: print('      noted: ' + t)
    for e in exc: print(f'  exception: {e["what"]} (the user wrote: "{e["user_wrote"]}")')
    print('  sheets:', sheets)
    stamp = xml_path + '.complete.json'
    if ok:
        json.dump({'sha256': hashlib.sha256(open(xml_path, 'rb').read()).hexdigest(), 'score': cfg['score'],
                   'exceptions': exc, 'noted': dict(notes)}, open(stamp, 'w'), indent=1)
        print('PASS: stamp written,', stamp)
    else:
        if os.path.exists(stamp): os.remove(stamp)
        print('NOT COMPLETE')
        sys.exit(1)


def stamped(xml_path):
    """True if xml_path has a stamp from a passing run of this check, for the file as it is now"""
    s = xml_path + '.complete.json'
    if not os.path.exists(s): return False
    return json.load(open(s))['sha256'] == hashlib.sha256(open(xml_path, 'rb').read()).hexdigest()


if __name__ == '__main__':
    main()
