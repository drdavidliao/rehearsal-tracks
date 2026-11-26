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
      "marks_typed": true,                         # a vector PDF whose notation is outlines, not glyphs: marks.tsv too
      "staff_threshold": {"8": 170},               # a pale scan: the staff finder's darkness threshold (default 150)
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
from fractions import Fraction
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
# a found staff this much covered by words between its lines is text (see staves): set from measurement, 2026-11-14
TEXT_STAFF = 0.66
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
    xml_facts.shorts = []                    # the short names printed before later systems
    for sp in root.iter('score-part'):
        parts[sp.get('id')] = [(sp.findtext('part-name') or '').strip(), 1]
        if sp.findtext('part-abbreviation'): xml_facts.shorts.append(sp.findtext('part-abbreviation').strip())
    marks = collections.defaultdict(list)
    onsets = collections.defaultdict(list)  # bar -> [(part, staff, kind, onset in divisions)] for marks on notes
    dyn_at = []                               # (part, staff, bar, onset in divisions, value) of every dynamic
    starts = collections.defaultdict(set)     # (part, staff, bar) -> onsets (divisions) where a note starts
    sounding = collections.defaultdict(list)  # (part, staff, bar) -> [(start, end)] of every note, held ones too
    # a hairpin's closed end, where its two lines meet: a crescendo's start, a diminuendo's stop. The page's hairpins are
    # found by that point, so a diminuendo running over a system break is on the next system (2026-11-14)
    wedge_closed, open_dim = collections.Counter(), {}
    open_any, wedge_spans = {}, []   # every hairpin (start bar, stop bar, kind), for one typed again past a system break
    lyric_words, other_text = [], []
    lyr = collections.Counter()  # (part id, bar) -> syllables sung there
    verses = collections.defaultdict(list)  # (part id, verse number) -> [(bar, text)] in order
    syls = []   # (part id, bar, onset in quarters, text normalised, text, placed above): for the lyric check by bar
    barlen = {}    # bar -> its length in quarters (the longest part's)
    bare = set()   # (part id, bar, onset in quarters): a sung note starting a syllable's place with no syllable on it (not
                   # tied into, not under a slur or a word's extender: a melisma's later notes have none)
    last = 0
    for c in root.iter('credit-words'): other_text.append(c.text or '')
    for t in ('work-title', 'movement-title', 'creator', 'rights'):
        for e in root.iter(t): other_text.append(e.text or '')
    for pid, (name, _) in parts.items(): other_text.append(name)
    other_text += xml_facts.shorts
    for part in root.iter('part'):
        pid = part.get('id')
        word = ''
        div = 1
        slur_in, ext = collections.Counter(), {}
        for meas in part.iter('measure'):
            try: num = int(re.match(r'\d+', meas.get('number', '0')).group())
            except AttributeError: continue
            last = max(last, num)
            st = meas.find('attributes/staves')
            if st is not None: parts[pid][1] = max(parts[pid][1], int(st.text))
            if meas.find('attributes/divisions') is not None: div = int(meas.findtext('attributes/divisions'))
            pos, last_on, top = 0, 0, 0
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
                                if d.get('type') == 'crescendo': wedge_closed[num] += 1
                                else: open_dim[(pid, staff, d.get('number', '1'))] = num
                                open_any[(pid, staff, d.get('number', '1'))] = (num, 'cresc' if d.get('type') == 'crescendo' else 'dim')
                            elif d.tag == 'wedge' and d.get('type') == 'stop':
                                b_ = open_dim.pop((pid, staff, d.get('number', '1')), None)
                                if b_ is not None: wedge_closed[num] += 1
                                st_ = open_any.pop((pid, staff, d.get('number', '1')), None)
                                if st_: wedge_spans.append((st_[0], num, st_[1]))
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
                    if el.find('rest') is None and el.find('grace') is None:   # held or tied into: it is singing there
                        sounding[(pid, staff, num)].append((on, on + int(el.findtext('duration') or 0)))
                    if el.find('chord') is None and el.find('grace') is None:
                        last_on = pos; pos += int(el.findtext('duration') or 0); top = max(top, pos)
                        barlen[num] = max(barlen.get(num, 0), Fraction(top, div))
                    n = el.find('notations')
                    if n is not None:
                        for f in n.iter('fermata'):
                            # an upright and an inverted fermata on one chord print as two (2026-11-14): the type is
                            # part of the moment, so parts sharing one upright fermata still count once
                            marks[num].append((pid, staff, 'fermata', ''))
                            onsets[num].append((pid, staff, 'fermata', (on, f.get('type') or 'upright')))
                        for a in n.iter('articulations'):
                            for k in a:
                                kind = {'strong-accent': 'marcato', 'breath-mark': 'breath'}.get(k.tag, k.tag)
                                if kind in MARK_KINDS:
                                    marks[num].append((pid, staff, kind, '')); onsets[num].append((pid, staff, kind, on))
                        for d in n.iter('dynamics'):
                            for k in d: marks[num].append((pid, staff, 'dyn', k.tag))
                    for ly in el.findall('lyric'):
                        t = ly.findtext('text') or ''
                        # words placed above the staff print in the band above it: their own verse
                        if norm(t): lyr[(pid, num)] += 1; verses[(pid, ly.get('number', '1') + ('^' if ly.get('placement') == 'above' else ''))].append((num, t))
                        if norm(t): syls.append((pid, num, Fraction(on, div), norm(t), t, ly.get('placement') == 'above'))
                        syl = ly.findtext('syllabic') or 'single'
                        lyric_words.append(t)
                        if syl in ('single', 'begin'): word = t
                        else: word += t
                        if syl in ('single', 'end'): lyric_words.append(word)
                    vk = (staff, el.findtext('voice') or '1')
                    if el.find('rest') is not None: ext[vk] = False
                    elif el.find('grace') is None and el.find('chord') is None:
                        sung_here = any(norm(ly.findtext('text') or '') for ly in el.findall('lyric'))
                        tied_in = any(t_.get('type') == 'stop' for t_ in el.findall('tie'))
                        if not sung_here and not tied_in and not slur_in[vk] and not ext.get(vk):
                            bare.add((pid, num, Fraction(on, div)))
                        if sung_here:
                            ext[vk] = any(e_.get('type', 'start') != 'stop' for ly in el.findall('lyric') for e_ in ly.findall('extend'))
                        if n is not None:
                            for sl in n.findall('slur'):
                                if sl.get('type') == 'start': slur_in[vk] += 1
                                elif sl.get('type') == 'stop': slur_in[vk] = max(0, slur_in[vk] - 1)
    bag = set()
    for s in lyric_words + other_text:
        for w in re.split(r'[\s/]+', s or ''):
            if norm(w): bag.add(norm(w))
        if norm(s or ''): bag.add(norm(s))
    for m in marks.values():
        for (_, _, k, v) in m:
            if k == 'dyn' and v: bag.add(norm(v))
    lbag = {norm(w) for w in lyric_words if norm(w)}
    xml_facts.dyn_at, xml_facts.starts, xml_facts.sounding = dyn_at, starts, sounding
    xml_facts.wedge_closed, xml_facts.wedge_spans = wedge_closed, wedge_spans
    xml_facts.syls, xml_facts.bare, xml_facts.barlen = syls, bare, barlen
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


# Private-use characters in TEXT fonts, read by name (SMuFL glyphnames.json) or, for a font's own glyph, by its drawn
# shape. A text font draws chord-symbol accidentals and metronome notes with them; dropping them silently read
# "Bbmaj7(#11)" as "maj7(11)". Any other private-use character in a text font is reported as unread, never dropped.
PUA_TEXT = {0xED60: '♭', 0xED61: '♮', 0xED62: '♯', 0xED63: '♯♯', 0xED64: '♭♭',
            0xE87B: '/', 0xE87C: '/',   # csymAccidental*, csymAlteredBassSlash, csymDiagonalArrangementSlash
            # metNote*: as the printed note symbols, the way "(\u2669 = ca. 160)" reads in plain text
            0xECA2: '\U0001D15D', 0xECA3: '\U0001D15E', 0xECA4: '\U0001D15E', 0xECA5: '\u2669', 0xECA6: '\u2669',
            0xECA7: '\u266A', 0xECA8: '\u266A', 0xECA9: '\U0001D161', 0xECAA: '\U0001D161', 0xECB7: '.'}  # metAugmentationDot
PUA_TEXT_FONT = {('BravuraText', 0xF4DE): '♯'}   # a small sharp: outline drawn from the embedded font, 2026-11-14
# fonts whose glyphs are notation, not words: skipped here (their marks are counted by glyphs_vector where it can)
# Metrico: Dorico's font for rhythm equations (swing marks); the figures are not compared yet
NOTATION_FONTS = SMUFL_FONTS + ('Opus', 'Helsinki', 'Maestro', 'Sonata', 'Petrucci', 'Metrico')


# Sibelius's chord-symbol font (Opus Chords) sets suffix letters and accidentals as its own glyphs, which come back
# through Mac Roman as other characters. Read from crops of every chord symbol in one score, 2026-11-14 (Bm, A/C#,
# Gmaj9, G(add2) ...). Any other non-ASCII character in it is reported as unread.
OPUS_CHORDS = {'\u00A9': '\u266f', '\u2039': 'm', '\u0152': 'm', '\u201E': 'a', '\u0160': 'j', '\u02C6': 'd'}


def text_char(font, ch):
    """a text font's character as text, or None if it is a glyph this check cannot read"""
    if 'OpusChords' in font:
        return OPUS_CHORDS.get(ch, ch if ord(ch) < 128 else None)
    cp = ord(ch)
    if not (0xE000 <= cp <= 0xF8FF): return ch
    # Finale's text font: ASCII moved up by 0xF000, its "q" being the quarter-note symbol of a metronome mark
    # ("q = 135", read from the page 2026-11-14)
    if 'EngraverText' in font and 0xF020 <= cp <= 0xF07E: return '\u2669' if cp == 0xF071 else chr(cp - 0xF000)
    for (f, c), t in PUA_TEXT_FONT.items():
        if c == cp and f in font: return t
    return PUA_TEXT.get(cp)


def notation_font(font):
    """a font whose glyphs are notation, not words. SMuFL's text fonts (BravuraText, LelandText ...) set words with a
    few music symbols in them, read through text_char; Sibelius's and Finale's text fonts stay notation, as before"""
    if any(font.split('+')[-1].startswith(f + 'Text') for f in SMUFL_FONTS): return False
    if 'OpusChords' in font: return False      # chord symbols: words, read through text_char
    return any(f in font for f in NOTATION_FONTS)


def page_words_vector(pdf, unread=None, boxes=None):
    """[(page, x, y, word)] from the text layer, in points; notation-font glyphs left out. Private-use glyphs in text
    fonts are read through text_char before words are formed, so a word set in two fonts ("B" + flat + "maj7") stays
    one word; one it cannot read is appended to `unread` as (page, x, y, font, code point)"""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf) as d:
        for pi, p in enumerate(d.pages, 1):
            # some text is drawn twice in one place (a bold effect): dedupe_chars keeps one copy
            dp = p.dedupe_chars().filter(lambda o: o.get('object_type') != 'char' or not notation_font(o['fontname']))
            keep = []
            for c in dp.chars:
                txt = c['text']
                t = text_char(c['fontname'].split('+')[-1], txt) if len(txt) == 1 else txt   # "(cid:64)" stays whole
                if t is None:
                    if unread is not None: unread.append((pi, c['x0'], c['top'], c['fontname'].split('+')[-1], f'U+{ord(c["text"][0]):04X}'))
                    continue
                c = dict(c); c['text'] = t; keep.append(c)
            from pdfplumber.utils.text import extract_words
            for w in extract_words(keep, x_tolerance=1.2):
                out.append((pi, w['x0'], w['top'], w['text']))
                if boxes is not None: boxes.append((pi, w['x0'], (w['top'] + w['bottom']) / 2, w['text'], w['x1']))
    return out


def page_words_scan(pngs, boxes=None, every=None):
    """[(page, x, y, word)] by tesseract; `boxes` gets (page, x0, y middle, word, x1) in points; `every` gets every word
    read, at any confidence, as (page, x0, y middle, word, x1, confident)"""
    out = []
    for pi, png in enumerate(pngs, 1):
        r = subprocess.run(['tesseract', png, '-', '--psm', '11', 'tsv'], capture_output=True, text=True)
        for line in r.stdout.splitlines()[1:]:
            f = line.split('\t')
            if len(f) < 12 or not f[11].strip(): continue
            try: conf = float(f[10])
            except ValueError: continue
            w = f[11].strip()
            if every is not None and re.search('[A-Za-z]', w):
                every.append((pi, int(f[6]) * 72 / DPI, (int(f[7]) + int(f[9]) / 2) * 72 / DPI, w, (int(f[6]) + int(f[8])) * 72 / DPI,
                              conf >= 70 and len(re.sub(r'[^A-Za-z]', '', w)) >= 2))
            # a scan's staves read as runs of punctuation and stray letters; a word worth matching has two letters
            if conf < 70 or len(re.sub(r'[^A-Za-z]', '', w)) < 2: continue
            out.append((pi, int(f[6]) * 72 / DPI, int(f[7]) * 72 / DPI, w))
            if boxes is not None:
                boxes.append((pi, int(f[6]) * 72 / DPI, (int(f[7]) + int(f[9]) / 2) * 72 / DPI, w, (int(f[6]) + int(f[8])) * 72 / DPI))
    return out


def band_lines_vector(pdf, syllables=frozenset(), pages=None, tokens=None):
    """[(page, y, letters)]: the lyric lines on each page. Lyrics are set in the text font and size used most on the
    page under staves; letters are gathered by line (tops within 3 pt) and read left to right. A glyph the text layer
    can't name (a ligature) is '?'."""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf) as d:
        allc = []
        for pi, p in enumerate(d.pages, 1):
            for c in p.dedupe_chars().chars:
                if notation_font(c['fontname']): continue
                allc.append((pi, c))
        # the font by its name without the subset prefix: a PDF may give one font a new prefix on every page
        # ("JUCNAZ+Times-Roman" on page 1, "CEWRHL+Times-Roman" on page 2), and only one page's lyrics were read
        fn = lambda c: c['fontname'].split('+')[-1]
        # the lyric font is the one whose words are the file's sung syllables: the most common font was a coin toss
        # where two sizes of one font print equally many letters (3787 each in one score, 2026-11-14)
        fonts, by_page = collections.Counter(), collections.defaultdict(collections.Counter)
        for pi, p in enumerate(d.pages, 1):
            if pages is not None and pi not in pages: continue   # a PDF with the parts after the score sets their words in another size
            for w in p.dedupe_chars().extract_words(extra_attrs=['fontname', 'size'], x_tolerance=1.2):
                if notation_font(w['fontname']) or not norm(w['text']): continue
                if norm(w['text'].strip('-_')) in syllables:
                    k_ = (w['fontname'].split('+')[-1], round(w['size'], 1)); fonts[k_] += 1; by_page[pi][k_] += 1
        if not fonts:
            fonts = collections.Counter((fn(c), round(c['size'], 1)) for _, c in allc if c['text'].isalpha())
        if not fonts: return out
        lf = fonts.most_common(1)[0][0]
        # a page scaled up or down sets its words in another size (12.1 pt on two pages against 11.5, 2026-11-14): each
        # page's own most matched font, where it has a dozen matches to go on
        # (or where the score's font has no syllable on that page at all: one "Ah!" in 12.1 pt on a page of its own)
        # always the score's lyric font family, at that page's size: a running header's words can be sung words too
        def page_font(c_):
            fam = collections.Counter({k_: v for k_, v in c_.items() if k_[0] == lf[0]})
            if not fam: return lf
            best, n_ = fam.most_common(1)[0]
            return best if n_ >= 12 or not c_[lf] else lf
        lf_page = {pi: page_font(c_) for pi, c_ in by_page.items()}
        rows = collections.defaultdict(list)
        for pi, c in allc:
            if (fn(c), round(c['size'], 1)) != lf_page.get(pi, lf): continue
            rows[pi].append(c)
        for pi, cs in rows.items():
            cs.sort(key=lambda c: c['top'])
            line = []
            for c in cs + [None]:
                if c is None or (line and c['top'] - line[0]['top'] > 3):
                    srt = sorted(line, key=lambda x: x['x0'])
                    t = ''.join('?' if x['text'].startswith('(cid') else norm(x['text']) for x in srt)
                    if t.strip('?'): out.append((pi, line[0]['top'], t))
                    if tokens is not None:
                        # the line's words: letters set apart by more than a fifth of the type size, or by a space, start one
                        cur = []
                        for x in srt + [None]:
                            # a hyphen between syllables set close (Dorico's short hyphen) ends one too
                            hy = x is not None and len(x['text']) == 1 and x['text'] in '-\u2010\u2011\u2013'
                            if cur and (x is None or hy or not x['text'].strip() or x['x0'] - cur[-1]['x1'] > 0.2 * x['size']):
                                txt = ''.join('?' if y['text'].startswith('(cid') else norm(y['text']) for y in cur)
                                if txt: tokens.append((pi, cur[0]['x0'], cur[-1]['x1'], line[0]['top'], txt,
                                                                  ''.join(y['text'] for y in cur)))
                                cur = []
                            if x is not None and x['text'].strip() and not hy: cur.append(x)
                    line = []
                if c is not None: line.append(c)
    return out


# Sibelius (Opus, Helsinki) and Finale (Maestro) fonts, every code seen in the scores checked so far (2026-11-14:
# three Opus, one Helsinki, two Maestro exports), each identified from a crop of one instance (SKILL.md's appendix has
# the method). Codes are bytes: the old Opus/Maestro fonts put them at U+F0xx (minus 0xF000 here); OpusStd and the
# Helsinki fonts come back through the Mac Roman table ("\u0153" = 0xCF), so they are encoded back to Mac Roman.
# A code not in these tables is reported, never passed over: an unseen dynamic must not hide.
LEGACY_MAIN = {   # the main music font (Opus, OpusStd, HelsinkiStd)
    'mark': {0x55: 'fermata', 0x75: 'fermata', 0x3E: 'accent', 0x5E: 'marcato', 0x2E: 'staccato'},
    'ignore': {0x22, 0x2C, 0x23, 0x26, 0x32, 0x34, 0x3F, 0x4A, 0x52, 0x6A, 0x72, 0x62, 0x6E, 0x77, 0xB7, 0xC5, 0xCE,
               0xCF, 0xC0, 0xE4, 0xEE, 0xFA}}   # caesura, breath, accidentals, clefs, time digits, flags, heads, rests
LEGACY_MAESTRO = {
    'dyn': {0x66: 'f', 0x50: 'mp', 0x46: 'mf', 0xC4: 'ff', 0xA7: 'sfz'},
    'mark': {0x55: 'fermata', 0x75: 'fermata', 0x3E: 'accent', 0x2D: 'tenuto'},
    'both': {0xF9: ('accent', 'staccato'), 0xDF: ('accent', 'staccato')},   # stacked in one glyph, above / below
    'dot': {0x2E},     # a staccato over or under its head, or an augmentation dot to its right
    'ignore': {0x22, 0x23, 0x26, 0x33, 0x34, 0x3F, 0x43, 0x4A, 0x4E, 0x56, 0x62, 0x6A, 0x6E, 0x72, 0x77, 0x7E, 0xB7,
               0xBA, 0xBE, 0xCE, 0xCF, 0xE4, 0xEE, 0xFA}}   # also: the clef's 8, a bracketed natural, a trill line, tremolo
LEGACY_HEADS = {0xCF, 0xFA, 0x77, 0xC0}
DYN_LETTERS = set('pmfszrn')


def legacy_code(c):
    """the byte a Sibelius or Finale music font draws for this char"""
    cp = ord(c['text'][0])
    if 0xF000 <= cp <= 0xF0FF: return cp - 0xF000
    try: return c['text'][0].encode('mac_roman')[0]
    except UnicodeEncodeError: return cp


def legacy_family(font):
    """'main', 'special', 'text', 'maestro', or None for a font these tables do not cover"""
    f = font.split('+')[-1]
    if f.startswith('Maestro') and 'Times' not in f and 'Text' not in f and 'Percussion' not in f and 'Wide' not in f: return 'maestro'
    for fam in ('Opus', 'Helsinki'):
        if f.startswith(fam):
            rest = f[len(fam):]
            if rest.startswith('Special'): return 'special'
            if rest.startswith('Text'): return 'text'
            if rest in ('', 'Std'): return 'main'
    return None


def join_runs(chars):
    """letters of one dynamic set one by one sit on one line, each starting at the previous one's right edge: join a
    glyph to one that ends 2.5 pt past its left edge (Helsinki kerns "ff" to -2.1) to 2 pt before it, on the same line;
    the first of each run.
    The gap is bounded below: a dynamic far to the left on the same line is not a letter of it, whatever order the PDF
    lists them in (an f in bar 102 and an mf in bar 106 were once counted as one)"""
    chars = sorted(chars, key=lambda c: c['x0'])
    head = list(range(len(chars)))
    for j, c in enumerate(chars):
        for i in range(j):
            if abs(chars[i]['top'] - c['top']) < 1 and -2.5 <= c['x0'] - chars[i]['x1'] < 2: head[j] = head[i]; break
    return [c for j, c in enumerate(chars) if head[j] == j]


def glyphs_vector(pdf, unknown=None):
    """[(page, y, kind)] for dynamics (a run of letters is one), fermatas, articulations, and hairpins, from SMuFL
    fonts and the Sibelius/Finale fonts in the tables above; None if no music font it reads is used, so nothing was
    counted. A legacy-font code not in the tables goes to `unknown` as (page, x, y, font, code)."""
    import pdfplumber
    out, known = [], False
    with pdfplumber.open(pdf) as d:
        for pi, p in enumerate(d.pages, 1):
            dyn, letters, dots, heads = [], [], [], []
            # a glyph struck twice at one spot (a faux bold) is one glyph
            for c in p.dedupe_chars().chars:
                if not c['text']: continue
                if any(f in c['fontname'] for f in SMUFL_FONTS):
                    known = True
                    cp = ord(c['text'][0])
                    if cp in SMUFL_FERMATA: out.append((pi, c['top'], 'fermata'))
                    elif cp in SMUFL_ARTIC: out.append((pi, c['top'], SMUFL_ARTIC[cp]))
                    if cp in SMUFL_DYN_RANGE: dyn.append(c)
                    continue
                fam = legacy_family(c['fontname'])
                if fam is None: continue
                known = True
                code = legacy_code(c)
                if fam == 'text':
                    if c['text'] in DYN_LETTERS: letters.append(c)
                    continue          # tuplet digits, the metronome note: not marks
                if fam == 'special': continue     # augmentation dots, brackets, the clef's 8, grace slashes, arpeggios
                tab = LEGACY_MAESTRO if fam == 'maestro' else LEGACY_MAIN
                if code in LEGACY_HEADS: heads.append(c)
                if code in tab.get('dyn', {}): out.append((pi, c['top'], 'dyn'))
                elif code in tab['mark']: out.append((pi, c['top'], tab['mark'][code]))
                elif code in tab.get('both', {}): out += [(pi, c['top'], k) for k in tab['both'][code]]
                elif code in tab.get('dot', set()): dots.append(c)
                elif code not in tab['ignore'] and unknown is not None:
                    unknown.append((pi, c['x0'], c['top'], c['fontname'].split('+')[-1], f'0x{code:02X}'))
            for c in dots:
                # over or under a head: its middle within the head's width (an augmentation dot stands 1.6-2 SP right)
                xm = (c['x0'] + c['x1']) / 2
                if any(h['x0'] - 0.5 <= xm <= h['x1'] + 0.5 and abs(h['top'] - c['top']) < 25 for h in heads):
                    out.append((pi, c['top'], 'staccato'))
            out += [(pi, c['top'], 'dyn') for c in join_runs(dyn) + join_runs(letters)]
            # a hairpin drawn as one path (Dorico: a filled outline): its points gather at two ends, open (4 pt or more
            # apart) at one and closed (a point or so) at the other
            for c in p.curves:
                pts = c.get('pts') or []
                # Finale: one stroked three-point path, open end, closed end, open end ("<": (404,166) (340,170)
                # (404,173), 2026-11-14)
                if len(pts) == 3 and c.get('stroke'):
                    (xa, ya), (xm, ym), (xb, yb) = pts
                    if abs(xa - xb) < 1 and abs(xm - xa) >= 10 and abs(ya - yb) >= 3 and min(ya, yb) < ym < max(ya, yb):
                        out.append((pi, (ya + yb) / 2, 'wedge'))
                    continue
                if len(pts) < 4: continue
                xs = np.array([q[0] for q in pts]); ys = np.array([q[1] for q in pts])
                if xs.max() - xs.min() < 10 or ys.max() - ys.min() > 16: continue
                lo, hi = ys[xs < xs.min() + 2], ys[xs > xs.max() - 2]
                if len(lo) < 2 or len(hi) < 1: continue
                sl, sh = lo.max() - lo.min(), (hi.max() - hi.min() if len(hi) > 1 else 0)
                if (sl >= 4 and sh <= 1.5) or (sh >= 4 and sl <= 1.5): out.append((pi, ys.mean(), 'wedge'))
            # or as two lines meeting at one end
            # 5 pt and a slope up to 0.3: the closing piece of a hairpin carried over a system break can be 7.5 pt long,
            # rising 1.9 (2026-11-14)
            segs = [l for l in p.lines if abs(l['x1'] - l['x0']) > 5]
            # a hairpin's lines slope a little: the half of one that runs into the next system opens 3 pt over a whole
            # system (slope under 0.005, 2026-11-14); staff and extender lines are flat (no rise at all)
            segs = [l for l in segs if l['bottom'] - l['top'] >= 0.5 and abs((l['bottom'] - l['top']) / (l['x1'] - l['x0'])) < 0.3]
            # a line drawn twice at the same place (Sibelius redraws some hairpins) is one line
            segs = list({(round(l['x0'], 1), round(l['x1'], 1), round(l['top'], 1), round(l['bottom'], 1)): l for l in segs}.values())
            # by the lines' own two ends: the corners of their boxes also meet at the open end (two lines of a
            # Sibelius hairpin: one box's top-right is the other's bottom-right), which counted every hairpin twice
            ends = collections.Counter()
            for l in segs:
                pts = l.get('pts') or [(l['x0'], l['top']), (l['x1'], l['bottom'])]
                for e in {(round(x), round(y)) for x, y in (pts[0], pts[-1])}:
                    ends[e] += 1
            out += [(pi, e[1], 'wedge') for e, v in ends.items() if v >= 2]
    return out if known else None


# ---------------------------------------------------------------- the checks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--no-stamp', action='store_true', help='report only: neither write nor remove the stamp')
    ap.add_argument('--json', help='also write every finding and note to this file')
    ap.add_argument('--old-lyrics', action='store_true', help='the lyric check by line (before 2026-11-16), for comparison')
    ap.add_argument('--sheets', help='where to draw the pages with what each check found (default: beside config)')
    a = ap.parse_args()
    json_out, no_stamp, old_lyrics = a.json, a.no_stamp, a.old_lyrics   # `a` is reused below
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
    sys_bl = {}  # (page, index on page) -> the system's barline x's in points, left to right (scanproof's finder)
    staves_off = set()  # pages whose staves found differ in number from those listed: their bands can't be placed
    staff_band = []  # (page, system on page, staff name, staff bottom, next staff's top): where its words print
    top_band = []    # (page, system on page, top staff's name, the staff before's bottom, its top)
    # the words on the page (text layer, or tesseract on a scan): also what tells a staff from lines of small text
    unread, boxes = [], []
    every = []
    words = [w for w in (page_words_vector(pdf, unread, boxes) if vector else page_words_scan(pngs, boxes, every)) if w[0] in scored]
    words_box = collections.defaultdict(list)
    for b in boxes: words_box[b[0]].append(b)
    for pi, png in enumerate(pngs, 1):
        if pi not in scored: continue
        # a pale scan: the staff lines' darkness threshold, as scanproof's project "threshold" (one number, or by page)
        thr = cfg.get('staff_threshold', 150)
        thr = thr.get(str(pi), 150) if isinstance(thr, dict) else thr
        page = geom.Page(png, thr)
        found = []
        for f in geom.staves(page):
            # five evenly spaced rows of small text (a copyright footer) pass the staff finder: a band whose width is
            # mostly covered by words lying between its top and bottom line is text. Measured 2026-11-14 on every
            # staff of 19 vector scores (2537 staves): real staves at most 0.565 covered even counting music glyphs as words, the one footer 0.997
            top = np.interp(page.gray.shape[1] / 2, *f['samples'][0]) * 72 / DPI
            bot = np.interp(page.gray.shape[1] / 2, *f['samples'][4]) * 72 / DPI
            x0, x1 = f['x0'] * 72 / DPI, f['x1'] * 72 / DPI
            cov = np.zeros(int(x1 - x0) + 1, bool)
            for wp, wx, wy, wt, *wr in words_box.get(pi, []):
                if top <= wy <= bot: cov[max(0, int(wx - x0)):max(0, int(wr[0] - x0))] = True
            if cov.mean() >= TEXT_STAFF:
                notes['staves'].append(f'page {pi}: lines at y {top:.0f}-{bot:.0f} pt are text ({cov.mean():.0%} covered by words), not a staff')
                continue
            found.append(f)
        mine = [s for s in systems if s['page'] == pi]
        want = sum(len(s['staves']) for s in mine)
        if len(found) != want:
            staves_off.add(pi)
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
                    # above a system's top staff: where words placed above it print (down from the staff before)
                    if j == 0: top_band.append((pi, si, n, ye[i + j - 1] if i + j > 0 else 0, ys[i + j]))
            i += k
        # barlines, system by system, on a paler threshold (they print grey on some scans); a piano's two staves vote
        # together, since the voices above may rest with no barline through them
        pale, i = page.threshold(228), 0
        for si, s in enumerate(mine):
            k = len(s['staves'])
            if len(found) == want:
                grand = None
                for j in range(k - 1):
                    r0, r1 = names.get(s['staves'][j], []), names.get(s['staves'][j + 1], [])
                    if len(r0) == len(r1) == 1 and r0[0]['part'] == r1[0]['part'] and (r0[0].get('staff'), r1[0].get('staff')) == (1, 2):
                        grand = (j, j + 1)
                bl = geom.barlines_system(pale, found, list(range(i, i + k)), page.k, grand)
                # the system's own ends bound its first and last bars (an opening line is not always a full stroke);
                # the finder gives the barlines between, a double barline's two strokes taken as one
                sx0 = min(found[j]['x0'] for j in range(i, i + k)) * 72 / DPI
                sx1 = max(found[j]['x1'] for j in range(i, i + k)) * 72 / DPI
                inner = []
                for x in sorted(x * 72 / DPI for x, _ in bl):
                    if x < sx0 + 12 or x > sx1 - 12: continue
                    if inner and x - inner[-1] < 8: continue
                    inner.append(x)
                sys_bl[(pi, si)] = [sx0] + inner + [sx1]
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
    for pi, x, y, font, cp in unread:
        if pi in scored: finding('text', f'page {pi}: unread glyph {cp} in {font} at x={x:.0f} y={y:.0f}')
    joined = ''.join(sorted(bag, key=len, reverse=True))

    def splits(n_):
        # the text layer joins words set close together ("weknow", 2026-11-14): a run that is wholly words
        # of the file (pieces of two letters or more, or "a" and "i") is those words
        ok = [True] + [False] * len(n_)
        for i_ in range(1, len(n_) + 1):
            ok[i_] = any(ok[j_] and n_[j_:i_] in bag and (i_ - j_ >= 2 or n_[j_:i_] in ('a', 'i')) for j_ in range(i_))
        return ok[-1]
    line_of = collections.defaultdict(list)
    for w_ in words: line_of[w_[0]].append(w_)

    def neighbours(pi_, x_, y_):
        # the words just left and right on the line: a kerned word can come apart ("Y" "et" with a space between)
        row = sorted((w_ for w_ in line_of[pi_] if abs(w_[2] - y_) < 2), key=lambda w_: w_[1])
        i_ = next((k_ for k_, w_ in enumerate(row) if w_[1] == x_), None)
        if i_ is None: return '', ''
        return (norm(row[i_ - 1][3]) if i_ > 0 else ''), (norm(row[i_ + 1][3]) if i_ + 1 < len(row) else '')
    for pi, x, y, w in words:
        # a glyph the text layer can't name (a ligature, "(cid:33)" for fl): match what is around it
        frags = [norm(f) for f in re.split(r'\(cid:\d+\)', w)]
        n = ''.join(frags)
        if not n or n.isdigit() or n in bag: continue
        if len(n) >= 4 and n in joined: continue
        if '(cid:' in w and all(len(f) < 2 or f in joined for f in frags): continue
        if splits(n): continue
        lft, rgt = neighbours(pi, x, y)
        if (lft and lft + n in bag) or (rgt and n + rgt in bag): continue
        # hyphenated syllables print apart: "sing-" "ing"; a syllable is in the bag on its own
        finding('text', f'page {pi}: {w!r} at x={x:.0f} y={y:.0f}')
        draws[pi].append((x, y, 'red', w))
    # -- lyrics, staff by staff: each line of words printed under a staff, letter for letter, against a verse its
    # part(s) sing in those bars. Two parts on one staff print their words once: either part's verse may match.
    lyric_lines = band_lines_vector(pdf, lbag, scored) if vector else None
    dir_words = {norm(v) for m in xmarks.values() for (_, _, k, v) in m if k == 'words' and norm(v)}
    def pids_of(n):
        out = set()
        for r in names.get(n, []):
            try: out.add(resolve(parts, r)[0])
            except KeyError: pass
        return out

    def verses_in(pids, b0, b1, above):
        out = set()
        for (pid, num), seq in xverses.items():
            if pid in pids and num.endswith('^') == above:
                t = norm(''.join(x for b, x in seq if b0 <= b <= b1))
                if t: out.add(t)
        return out
    # each band between staves holds the upper staff's words placed below it and the lower staff's words placed above
    # it (two parts on a staff singing different words: the higher part's above, 2026-11-14); a system's top staff's
    # words placed above it print over the system
    bands = []
    for idx, (pi, si, n, y0, y1) in enumerate(staff_band):
        nb = staff_band[idx + 1] if idx + 1 < len(staff_band) and staff_band[idx + 1][:2] == (pi, si) else None
        bands.append((pi, si, n, y0, y1, pids_of(n), False, pids_of(nb[2]) if nb else set()))
    for (pi, si, n, y0, y1) in top_band:
        bands.append((pi, si, n + ' (above)', y0, y1, set(), False, pids_of(n)))
    def lyrics_by_bar():
        # The lyric check by bar (design agreed 2026-11-16, "_design 2026-11-14 lyric check by bar.md"): in each system,
        # bar and band (the space under a staff, and over a system's top staff), every printed syllable is sung there by
        # a part of that band, and every sung syllable is printed there; a sung syllable printed once, in another band of
        # the system where a part sings the same syllable at the same moment, is noted, not failed (the
        # words are kept on every part that sings them). A bar runs from barline to barline (scanproof's finder); a
        # syllable belongs to the bar its middle falls in.
        toks = []   # (page, x0, x1, y, text normalised, text as printed)
        if vector:
            band_lines_vector(pdf, lbag, scored, toks)
        else:
            # every word tesseract reads may be a syllable; only a confident reading is reported when it matches none
            toks = []
            for (p_, x0_, y_, w_, x1_, sure) in every:
                if p_ not in scored or not norm(w_): continue
                # tesseract reads a hyphenated word whole ("beau-ti-ful"): its syllables, spread over its width
                parts_ = [q for q in re.split(r'[-\u2010\u2013]+', w_) if norm(q)] or [w_]
                L_ = sum(len(q) for q in parts_) or 1
                xa = x0_
                for q in parts_:
                    xb = xa + (x1_ - x0_) * len(q) / L_
                    toks.append((p_, xa, xb, y_, norm(q), q, sure)); xa = xb
        sung = collections.defaultdict(list)   # (part, bar) -> [(onset, text, as written, placed above)]
        for pid, b, on, t, raw, ab in xml_facts.syls: sung[(pid, b)].append((on, t, raw, ab))
        nonlyric = (bag - lbag) | dir_words | {norm(v) for v in xml_facts.shorts} | {norm(nm) for nm, _ in parts.values()}
        chord_raw = re.compile(r'(?:[A-G][b#♭♯]?(?:maj|min|m|dim|aug|sus|add|alt|no|\+|[b#♭♯]?\d{1,2}|[()°ø])*'
                               r'(?:/[A-G][b#♭♯]?)?)+')
        dyn_re = re.compile(r'(?:p+|m?f+|mp|fp|sfz?|rfz?|sf|fz)')
        pname = {pid: nm for pid, (nm, _) in parts.items()}

        def noise(t, raw):
            # printed in the band and not a syllable: a chord symbol, a dynamic, a direction or label the file has
            return bool(chord_raw.fullmatch(raw.strip('.,;:!?')) or dyn_re.fullmatch(t) or t in nonlyric or t.isdigit())

        def near(a_, b_):
            # a scan's reading of a word of four letters or more, one letter off
            if len(b_) < 4 or abs(len(a_) - len(b_)) > 1: return False
            if len(a_) == len(b_): return sum(x != y for x, y in zip(a_, b_)) <= 1
            sh, lo = (a_, b_) if len(a_) < len(b_) else (b_, a_)
            return any(lo[:k] + lo[k + 1:] == sh for k in range(len(lo)))

        def same(t, it):
            if t == it: return True
            if '?' in t: return re.fullmatch(''.join('.{1,3}' if c == '?' else re.escape(c) for c in t), it) is not None
            return not vector and near(t, it)

        def items_of(pids, pids_up, bars):
            # one item per syllable and moment: two parts singing it together need it printed once (a staff of two parts
            # may print it twice, once per line)
            g = {}
            # the staff above the band: its words placed below; the staff below: its words placed above
            for pid, above in [(p_, False) for p_ in pids] + [(p_, True) for p_ in pids_up]:
                for b in bars:
                    for on, t, raw, ab in sung[(pid, b)]:
                        if ab != above: continue
                        it = g.setdefault((b, on, t), dict(bar=b, on=on, t=t, raw=raw, pids=set(), got=0))
                        it['pids'].add(pid)
            return list(g.values())

        def place(x, it):
            # how far a printed syllable's place across its bar is from the moment it is sung there (0 to 1); where a
            # bar has two of one syllable ("I" at beat 1 and 2.5), the nearer one (2026-11-16)
            e = x.get('span')
            L = xml_facts.barlen.get(it['bar'])
            if not e or not L: return 0
            return abs((x['x0'] - e[0]) / max(1e-6, e[1] - e[0]) - float(it['on'] / L))

        def match(tk, its):
            """pair printed tokens with sung items; returns [(token, item)]"""
            pairs, free = [], list(range(len(tk)))
            def take(ti, it): pairs.append((tk[ti], it)); it['got'] += 1; free.remove(ti)
            for ti in sorted(free, key=lambda i_: tk[i_]['x0']):
                c = [it for it in its if it['got'] < len(it['pids']) and same(tk[ti]['t'], it['t'])]
                # in order, as printed; by place across the bar only where fewer of a syllable are printed than sung
                few = sum(1 for x in tk if x['t'] == tk[ti]['t']) < sum(1 for it in its if it['t'] == tk[ti]['t'])
                if c: take(ti, min(c, key=lambda it: (it['got'] > 0, place(tk[ti], it) if few else 0, it['bar'], it['on'])))
            # words set touching read as one ("itis"): a token that is two to four of one part's syllables in a row
            for ti in sorted(free, key=lambda i_: tk[i_]['x0']):
                for pid in sorted({p_ for it in its for p_ in it['pids']}):
                    seq = sorted((it for it in its if pid in it['pids'] and not it['got']), key=lambda it: (it['bar'], it['on']))
                    hit = next((seq[k:k + w] for w in range(2, len(seq) + 1) for k in range(len(seq) - w + 1)
                                if ''.join(x['t'] for x in seq[k:k + w]) == tk[ti]['t']), None)
                    if hit:
                        tk[ti]['joined'] = True
                        pairs.append((tk[ti], hit[0])); free.remove(ti)
                        for x in hit: x['got'] += 1
                        break
            # one syllable set apart by kerning ("Y" "et"): neighbours on one line that together are a syllable
            for ti in sorted(free, key=lambda i_: tk[i_]['x0']):
                if ti not in free: continue
                row = sorted((j for j in free if abs(tk[j]['y'] - tk[ti]['y']) < 3 and tk[j]['x0'] >= tk[ti]['x0']), key=lambda j: tk[j]['x0'])
                for w in (2, 3):
                    if len(row) < w: break
                    cat = ''.join(tk[j]['t'] for j in row[:w])
                    c = [it for it in its if not it['got'] and it['t'] == cat]
                    if c:
                        c[0]['got'] += 1
                        for j in row[:w]: pairs.append((tk[j], c[0])); free.remove(j)
                        break
            return pairs

        for pi in sorted(scored):
            mine = [s for s in systems if s['page'] == pi]
            if pi in staves_off:
                notes['lyrics'].append(f'page {pi}: its words are not compared (the staves found there are not the staves listed, so '
                                       f'no band can be placed; see the staves check)')
                continue
            for si, s_ in enumerate(mine):
                b0, b1 = s_['bars']
                edges = sys_bl.get((pi, si))
                by_bar = bool(edges) and len(edges) == b1 - b0 + 2
                if by_bar:
                    def bar_of(x_, e=edges): return b0 + max(0, min(b1 - b0, sum(1 for v in e[1:] if v <= x_)))
                else:
                    notes['lyrics'].append(f'page {pi} system {si + 1} (bars {b0}-{b1}): {len(edges or [])} barlines found for '
                                           f'{b1 - b0 + 1} bars; its words compared over the whole system')
                    def bar_of(x_): return None
                bars = range(b0, b1 + 1)
                sysbands = []
                for (p2, s2, n, y0, y1, pids, _, pids_up) in bands:
                    if (p2, s2) != (pi, si): continue
                    if not (pids | pids_up) or not any(xlyr[(pid, b)] for pid in pids | pids_up for b in range(0, last + 1)): continue
                    # the gap between two systems: its upper half holds the words under the upper system's lowest staff,
                    # its lower half the words over the next system's top staff ("night" over the next system was read
                    # under this one, in the wrong bar, 2026-11-16); over a page's first system, 50 pt (not the title)
                    if n.endswith(' (above)'): y0 = (y0 + y1) / 2 if si > 0 else max(y0, y1 - 50)
                    elif not any(b_[:2] == (pi, si) and b_[3] > y0 and not b_[2].endswith(' (above)') for b_ in bands) and si + 1 < len(mine):
                        y1 = (y0 + y1) / 2
                    its = items_of(pids, pids_up, bars)
                    # over the top staff: kept even with no words placed above, as the band its words may print in
                    report = bool(its) or not n.endswith(' (above)')
                    tk = [dict(x0=x0, x1=x1, y=y, t=t, raw=raw, bar=bar_of((x0 + x1) / 2), sure=(rest[0] if rest else True))
                          for (p_, x0, x1, y, t, raw, *rest) in toks if p_ == pi and y0 < y < y1]
                    for x in tk:
                        if by_bar and x['bar'] is not None: x['span'] = (edges[x['bar'] - b0], edges[x['bar'] - b0 + 1])
                    # chord symbols set in the lyric font ("A", "E" over a piano staff): a line with nothing but chord
                    # symbols on it is theirs, not words to match ("A" read as the sung "a", 2026-11-16)
                    is_chord = lambda x: bool(chord_raw.fullmatch(x['raw'].strip('.,;:')) and x['raw'][:1] in 'ABCDEFG')
                    # a symbol's suffix set apart from its root by a flat glyph ("B" "7sus4" for B♭7sus4) is part of a
                    # chord line too: "A" of A♭ was read as a sung "a" beside it (the Dorico 6.2.40 SATB with piano, m95, 2026-11-16)
                    is_suffix = lambda x: bool(re.fullmatch(r'(?:maj|min|m|dim|aug|sus|add|alt|no|\+|[b#♭♯]?\d{1,2}|[()°ø/])+',
                                                            x['raw'].strip('.,;:'))) and bool(re.search(r'\d|sus|add|maj|dim|aug', x['raw']))
                    is_piece = lambda x: is_chord(x) or is_suffix(x)
                    tk = [x for x in tk if not (is_piece(x) and any(is_chord(y) for y in tk if abs(y['y'] - x['y']) < 3)
                                                and all(is_piece(y) for y in tk if abs(y['y'] - x['y']) < 3))]
                    pairs = []
                    for b in (bars if by_bar else [None]):
                        tb = [x for x in tk if x['bar'] == b]
                        ib = [it for it in its if b is None or it['bar'] == b]
                        pairs += match(tb, ib)
                    used = {id(x) for x, _ in pairs}
                    left = [x for x in tk if id(x) not in used]
                    # a word whose middle lies just over a barline from its note (a long word centred under the bar's first
                    # or last note): the neighbouring bar's syllable
                    for x in list(left):
                        if not by_bar: continue
                        # words set touching across a barline (two words read as one): one part's syllables in a row, either side
                        hit = None
                        for pid in sorted({p_ for it in its for p_ in it['pids']}):
                            seq = sorted((it for it in its if pid in it['pids'] and not it['got'] and abs(it['bar'] - x['bar']) <= 1),
                                         key=lambda it: (it['bar'], it['on']))
                            hit = next((seq[k:k + w] for w in range(2, len(seq) + 1) for k in range(len(seq) - w + 1)
                                        if ''.join(y['t'] for y in seq[k:k + w]) == x['t']), None)
                            if hit: break
                        if hit:
                            for y in hit: y['got'] += 1
                            pairs.append((x, hit[0])); left.remove(x); continue
                        c = [it for it in its if not it['got'] and abs(it['bar'] - x['bar']) == 1 and same(x['t'], it['t'])]
                        if c:
                            e_ = edges[min(c[0]['bar'], x['bar']) - b0 + 1]
                            if x['x0'] - 6 <= e_ <= x['x1'] + 6:
                                c[0]['got'] += 1; pairs.append((x, c[0])); left.remove(x)
                    sysbands.append(dict(n=n, tk=tk, its=its, pairs=pairs, left=left, pids=pids, pids_up=pids_up, report=report))
                    # the order along each printed line follows the order sung (vector PDFs; a scan's reading order is not the page's)
                    if vector and by_bar:
                        # (a token of several syllables set touching is paired after the others: not ordered)
                        for x, it in pairs:
                            if not x.get('joined'): x['at'] = (it['bar'], it['on'])
                        for x in tk:
                            prev = [y for y in tk if 'at' in y and abs(y['y'] - x['y']) < 3 and y['x1'] <= x['x0'] and y['bar'] == x['bar']]
                            if 'at' in x and prev and max(prev, key=lambda y: y['x0'])['at'] > x['at']:
                                p_ = max(prev, key=lambda y: y['x0'])
                                finding('lyrics', f'page {pi} system {si + 1} staff {n} bar {x["bar"]}: {p_["raw"]!r} is printed before '
                                                  f'{x["raw"]!r}, sung after it')
                # a part's words printed above its staff instead of below (one line between two staves serving the
                # lower one, an upper voice's words over the staff): its syllable in that bar of the band above
                above_of = {}
                for ob in sysbands:
                    for p_ in ob['pids_up']: above_of[p_] = ob
                for sb in sysbands:
                    for it in sb['its']:
                        if it['got'] or not it['pids'] <= sb['pids']: continue
                        ob = next((above_of[p_] for p_ in it['pids'] if p_ in above_of), None)
                        if ob is None or ob is sb: continue
                        c = [x for x in ob['left'] if same(x['t'], it['t']) and (x['bar'] == it['bar'] or x['bar'] is None)]
                        if c:
                            x = min(c, key=lambda x: x['x0']); ob['left'].remove(x); it['got'] += 1; it['above'] = ob['n']
                for sb in sysbands:
                    ab = collections.defaultdict(list)
                    for it in sb['its']:
                        if it.get('above'): ab[it['above']].append(it['bar'])
                    for on_, bs in ab.items():
                        notes['lyrics'].append(f'page {pi} system {si + 1} staff {sb["n"]}: words in bars {min(bs)}-{max(bs)} printed above '
                                               f'the staff, in the band of {on_} ({len(bs)} syllables)')
                for sb in sysbands:
                    n = sb['n']
                    for x in sb['left']:
                        if not sb['report'] or not x['sure'] or noise(x['t'], x['raw']): continue
                        finding('lyrics', f'page {pi} system {si + 1} staff {n} bar {x["bar"] if x["bar"] is not None else f"{b0}-{b1}"}: '
                                          f'printed {x["raw"]!r}, not sung there by the staff\'s parts')
                    once = collections.defaultdict(list)
                    for it in sb['its']:
                        if it['got']: continue
                        # the scan reader keeps words of two letters or more (page_words_scan): "I" and "a" are not read
                        if not vector and len(it['t']) < 2:
                            notes['lyrics'].append(f'page {pi} system {si + 1} staff {n} bar {it["bar"]}: {it["raw"]!r} '
                                                   f'not looked for (one letter: the scan reader skips those)')
                            continue
                        # printed once for several parts: the same syllable printed in that bar under another staff whose
                        # parts sing it at the same moment
                        # (that band matched a printed syllable to its own parts' same syllable at the same moment)
                        other = next((ob for ob in sysbands if ob is not sb and
                                      any(o['got'] and o['t'] == it['t'] and o['bar'] == it['bar'] and o['on'] == it['on'] for o in ob['its'])), None)
                        who = '+'.join(sorted(pname[p_] for p_ in it['pids']))
                        if other: once[(who, other['n'])].append(it['bar'])
                        else: finding('lyrics', f'page {pi} system {si + 1} staff {n} bar {it["bar"]}: {who} sings {it["raw"]!r}, printed '
                                                f'neither under the staff nor once elsewhere in the system')
                    # two parts on one staff printing their words once: a part with a note where the other sings a syllable,
                    # and none of its own, has lost it (the page gives the word to both)
                    for it in sb['its']:
                        if not it['got']: continue
                        side = sb['pids'] if it['pids'] <= sb['pids'] else sb['pids_up'] if it['pids'] <= sb['pids_up'] else set()
                        singers = {q for q in side if any(xlyr[(q, b)] for b in range(0, last + 1))}
                        for p_ in sorted(singers - it['pids']):
                            if (p_, it['bar'], it['on']) in xml_facts.bare:
                                finding('lyrics', f'page {pi} system {si + 1} staff {n} bar {it["bar"]}: {pname[p_]} has a note where '
                                                  f'{"+".join(sorted(pname[q] for q in it["pids"]))} sings {it["raw"]!r} (printed once '
                                                  f'for the staff), with no syllable of its own')
                    for (who, on_), bs in once.items():
                        notes['lyrics'].append(f'page {pi} system {si + 1}: {who}\'s words in bars {min(bs)}-{max(bs)} printed once, '
                                               f'under {on_} ({len(bs)} syllables)')

    if old_lyrics:
        for pi, si, n, y0, y1, pids, _, pids_up in bands:
            s_ = [s for s in systems if s['page'] == pi][si]
            # a staff whose parts sing no words anywhere (a piano) has none to compare; what prints under it is directions
            if not (pids | pids_up) or not any(xlyr[(pid, b)] for pid in pids | pids_up for b in range(1, last + 1)): continue
            b0, b1 = s_['bars']
            sung = verses_in(pids, b0, b1, False) | verses_in(pids_up, b0, b1, True)
            if not sung and n.endswith(' (above)'): continue
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
                    # words two parts on the staff sing together, printed once, on the line that is the other part's verse
                    # ("long." under both tenors, 2026-11-14): this part's words are a run of a line matched in this band
                    if any(v in m_ for m_ in matched): continue
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
    else:
        lyrics_by_bar()
    # -- glyphs / marks
    count = collections.Counter(k for m in xmarks.values() for (_, _, k, _) in m)
    # a vector PDF that draws its notation as paths (Verovio's output: dynamics and fermatas are outlines, not font
    # glyphs) gives the glyph counter nothing to count: its config sets "marks_typed": true and names a blind
    # marks.tsv, checked as a scan's is
    if vector and not cfg.get('marks_typed'):
        unknown = []
        g = glyphs_vector(pdf, unknown)
        for pi, x, y, font, code in unknown:
            if pi in scored: finding('glyphs', f'page {pi}: unclassified glyph {code} in {font} at x={x:.0f} y={y:.0f} (not counted)')
        g = None if g is None else [t for t in g if t[0] in scored]
        if g is None:
            finding('glyphs', 'no SMuFL music font on the page: dynamics, fermatas, articulations and hairpins not counted')
        else:
            # per system, so a missing mark in one place cannot hide behind an extra one elsewhere: a glyph belongs to
            # the system whose top is the last one above it (less 40 pt, for marks over the top staff)
            # a mark belongs to the system whose staves it lies within, or failing that the nearest one: marks hang
            # below a system's bottom staff as far as they stand above its top one
            xms = {}
            for (pi, si), (t, _) in sorted(sys_y.items()):
                s_ = [s for s in systems if s['page'] == pi][si]
                xm = collections.Counter(k for b in range(s_['bars'][0], s_['bars'][1] + 1) for (_, _, k, _) in xmarks.get(b, []))
                xm['wedge'] = sum(xml_facts.wedge_closed[b] for b in range(s_['bars'][0], s_['bars'][1] + 1))
                xms[(pi, si)] = xm
            pg, between = collections.Counter(), []
            for pi, y, kind in g:
                spans = sorted([(t, b, si) for (p2, si), (t, b) in sys_y.items() if p2 == pi])
                if not spans: continue
                inside = [si for t, b, si in spans if t <= y <= b]
                gap = [(spans[i][2], spans[i + 1][2]) for i in range(len(spans) - 1) if spans[i][1] < y < spans[i + 1][0]]
                if inside: pg[(pi, inside[0], kind)] += 1
                elif gap: between.append((pi, gap[0], kind, y))
                else: pg[(pi, min(spans, key=lambda s3: min(abs(y - s3[0]), abs(y - s3[1])))[2], kind)] += 1
            # a mark in the gap between two systems (a hairpin under one system's piano and over the next one's
            # voices, an accent under a low note) belongs to one of them: it goes to the one the file has a mark of that
            # kind left unmatched in (2026-11-14), else to the nearer
            for pi, (a, b), kind, y in between:
                da = xms[(pi, a)][kind] - pg[(pi, a, kind)]; db = xms[(pi, b)][kind] - pg[(pi, b, kind)]
                if da == db:   # neither is short of one: the nearer, as a mark stands nearer the staff it marks
                    near = b if abs(y - sys_y[(pi, b)][0]) < abs(y - sys_y[(pi, a)][1]) else a
                else: near = b if db > da else a
                pg[(pi, near, kind)] += 1
            for (pi, si), (t, _) in sorted(sys_y.items()):
                s_ = [s for s in systems if s['page'] == pi][si]
                xm = xms[(pi, si)]
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
                # a metronome range or "ca." ("q=76-80", "q=ca. 120"): the page's words carry it as printed and the
                # file's metronome mark is its first number, the one played (2026-11-14)
                mr = re.fullmatch(r'([qhew]\.?)\s*=\s*(?:ca\.?\s*)?(\d+)(?:\s*[-\u2013]\s*\d+)?', v) if f[2] == 'tempo' else None
                if mr: v = f'{mr.group(1)}={mr.group(2)}'
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
            # a hairpin running over a system break is printed in two pieces; a reader may type the second piece again
            # at the next system's first bar (2026-11-14). The file has one hairpin there, started before that bar.
            first_bars = {s_['bars'][0] for s_ in systems}
            for k in [k for k in typed_raw if k[2] == 'wedge' and k[0] in first_bars]:
                if any(a < k[0] <= b and kind == k[3] for a, b, kind in xml_facts.wedge_spans):
                    notes['marks'].append(f'bar {k[0]} staff {k[1]} wedge {k[3]!r}: the second piece of a hairpin from the system before')
                    del typed_raw[k]
            typed = canon(collections.Counter({k: v for k, v in typed_raw.items() if k[1] != '(text)'}))
            typed.update({k: v for k, v in typed_raw.items() if k[1] == '(text)'})
            have = canon(collections.Counter({k: v for k, v in have.items() if k[2] != 'words'}))
            have.update(have_w)
            for k in sorted(set(typed) | set(have), key=str):
                if typed[k] != have[k]:
                    finding('marks', f'bar {k[0]} staff {k[1]} {k[2]} {k[3]!r}: {typed[k]} typed from the page, {have[k]} in the MusicXML')
    # -- dynamics on the right staff: a dynamic marks the part it stands with, so that part is singing there: a note
    # sounding at it (a p late in a held note, an f where a crescendo ends, 2026-11-14) or starting within the next
    # beat (an entry after a rest). A dynamic on a part that is resting there was put on the
    # wrong staff: one reader read every voice's dynamics one staff low. Divisions per quarter from the file.
    divs = [int(d.text) for d in load_xml(xml_path).iter('divisions')]
    div_ = divs[0] if divs else 1
    for (pid, st, b, on, val) in xml_facts.dyn_at:
        if parts.get(pid, ('', 0))[0].lower().startswith(('piano', 'pno', 'keyboard')): continue
        # an entry later in the bar counts too: a dynamic printed at the barline over a rest before a beat-2.5 entry
        if not any(x >= on for x in xml_facts.starts.get((pid, st, b), ())) and \
                not any(a <= on < e for a, e in xml_facts.sounding.get((pid, st, b), ())):
            finding('dynstaff', f'bar {b} {parts[pid][0]}: {val} where the part is silent (no note sounding, none starting later in the bar)')
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
    if json_out: json.dump({'fails': dict(fails), 'notes': dict(notes)}, open(json_out, 'w'), indent=1)
    if no_stamp:
        print('PASS (not stamped: --no-stamp)' if ok else 'NOT COMPLETE')
        return
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
