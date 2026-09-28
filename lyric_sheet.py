#!/usr/bin/env python3
"""Lyric sheet (SKILL.md 10.1): every part's words on one printable page, and videos of that page
with each syllable lit, in the colours of the parts singing it, while it is sung.

    python3 lyric_sheet.py plan LYRICS.musicxml -o "TITLE - lyric sheet plan.json" [--title T] [--credits C]
    python3 lyric_sheet.py structure LYRICS.musicxml
    python3 lyric_sheet.py pdf PLAN.json [-o "TITLE - lyric sheet.pdf"]

score_video.py runs all of this in the course of making the follow-along videos: it writes the draft
plan when there is none (and stops), refuses a plan that fails the checks below, makes the PDF, and
beside each score video "<mp3 name>, lyrics.mp4", timed exactly as the score video is.

LYRICS is a print-faithful MusicXML with one part per sung part (never the Cantai learning file: its
split syllables would print). Syllables that parts sing together (same bar, beat and word) are one word
on the sheet; the parts singing it are shown by coloured dots before the row, a short label under them,
and, for words only some of the row's parts sing, italics and a small tag.

The plan is JSON, written as a draft and finished by hand:

  "sections": [{"name": ..., "rows": [{"from": "55", "to": "56:2", "parts": [...]}, ...]}]
      A row is every syllable from bar:quarter "from" up to "to" (quarters from the bar's start, "3/2"
      allowed), of the named parts (all parts if left out). {"continues": true} prints a row as the
      second line of the one before it, with no label. The draft breaks rows at rests and names
      sections "A?", "B?"... from rehearsal marks, double barlines and melody that repeats; the names
      must come from the musical structure (compare melody and harmony: `structure`).
  "words":  [{"bar": "7", "word": "river", "emoji": "...", "parts": [...]}]
      At least one key word per row, printed bold and followed by its emoji: a fixation point.
  "edits":  [{"bar": "77", "syllable": "ah", "show": "ah..."}]    display text only
  "names":  short part names for the legend;  "sets": label and tag for each set of parts
  "reviewed": true once all of that is done.

Every row prints on one line: the page's font is the largest at which the longest row fits, and a row
too long for a readable size is split, with "continues", only where the music rests. The video uses the
same rows in three columns at 1920x1080 (16:9), and an iPad video (3:4 portrait, 1536x2048) shows
the printed page itself. The PDF has two pages: first the 16:9 video's page, landscape, the full width
with the paper below it empty; then the portrait page to print.

Needs lxml, numpy, pycairo, pillow, the Noto Color Emoji font and one of Carlito, Lato or
Liberation Sans; imports score_video.py (for its MusicXML reader), so keep it beside that.
"""
import sys, os, re, math, json, argparse, subprocess, tempfile, shutil, itertools
from fractions import Fraction as Fr
from concurrent.futures import ThreadPoolExecutor
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_video as sv  # noqa: E402

try:
    import cairo
except ImportError:          # the plan and structure commands need no drawing
    cairo = None

PLAN_KEYS = ('lyrics', 'title', 'credits', 'reviewed', 'names', 'colours', 'sets', 'sections', 'words', 'edits')
GREY = '#BDBDBD'
EMO_W = 1.12                 # an emoji's advance, in font sizes (a thin space, the glyph, a thin space)


def norm(t):
    return re.sub(r"[^\w']", '', t or '').lower()


def font_family():
    fams = subprocess.run(['fc-list', ':', 'family'], capture_output=True, text=True).stdout
    for f in ('Carlito', 'Lato', 'Liberation Sans', 'Arial', 'DejaVu Sans'):
        if re.search(rf'(^|,){re.escape(f)}(,|$)', fams, re.M):
            return f
    return 'sans-serif'


def emoji_font():
    p = subprocess.run(['fc-match', '-f', '%{file}', 'Noto Color Emoji'], capture_output=True, text=True).stdout
    if 'emoji' not in p.lower():
        sys.exit('lyric_sheet: no Noto Color Emoji font (apt install fonts-noto-color-emoji)')
    return p


# ----------------------------------------------------------------------------- the words

class Words:
    """Every syllable of every sung part of LYRICS, merged across parts that sing it together."""

    def __init__(self, path):
        self.path = path
        root = sv.read_xml(path)
        parts = root.findall('part')
        sps = {sp.get('id'): sp for sp in root.find('part-list').findall('score-part')}
        self.all_names = [(sps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in parts]
        self.title = (root.findtext('work/work-title') or root.findtext('movement-title') or '').strip()
        self.credits = [c.findtext('credit-words') or '' for c in root.findall('credit')]
        notes, starts = [], None
        for i, p in enumerate(parts):
            ns, st = sv.scan_part(i, p)
            notes.append(ns)
            starts = starts or st
        self.notes, self.starts, self.parts = notes, starts, parts
        self.numbers = [m.get('number') for m in parts[0].findall('measure')]
        self.mi_of = {}
        for mi, n in enumerate(self.numbers):
            self.mi_of.setdefault(n, mi)
        self.sung = [i for i, ns in enumerate(notes) if any(n['lyric'] for n in ns)]
        self.names = [self.all_names[i] for i in self.sung]
        tok = {}
        for i in self.sung:
            ns = notes[i]
            byid = {n['id']: n for n in ns}
            for nid, (q0, q1) in sv.syllable_windows(ns).items():
                n = byid[nid]
                ly = n['el'].find('lyric')
                text = ly.findtext('text') or ''
                syl = ly.findtext('syllabic') or 'single'
                rel = n['on'] - starts[n['mi']]
                k = (n['mi'], rel, norm(text))
                t = tok.setdefault(k, dict(mi=n['mi'], bar=self.numbers[n['mi']], q=rel, text=text, syl=syl,
                                           parts={}))
                if len(text) > len(t['text']):
                    t['text'] = text                    # "long" and "long," are one word
                t['parts'][self.all_names[i]] = (q0, q1)
        self.tokens = [tok[k] for k in sorted(tok, key=lambda k: (k[0], k[1]))]
        for j, t in enumerate(self.tokens):
            t['id'] = j
        self.order = {n: k for k, n in enumerate(self.names)}

    def pos(self, s):
        """'55' or '56:2' or '75:7/2' -> (measure index, quarters from its start)."""
        b, _, q = str(s).partition(':')
        if b not in self.mi_of:
            if b.isdigit() and int(b) > int(max(self.numbers, key=lambda x: int(x) if x.isdigit() else 0)):
                return (len(self.numbers), Fr(0))
            raise ValueError(f'no bar {b!r}')
        return (self.mi_of[b], Fr(q) if q else Fr(0))

    def sort_parts(self, ps):
        return sorted(ps, key=lambda p: self.order.get(p, 99))

    def melody(self):
        """Per bar: the highest sung pitch at each onset, the lowest unsung one, and the unsung pitch classes."""
        top, low, pcs = {}, {}, {}
        for i, ns in enumerate(self.notes):
            for n in ns:
                if n['rest'] or n['grace'] or n['midi'] is None:
                    continue
                if i in self.sung:
                    q = n['on'] - self.starts[n['mi']]
                    d = top.setdefault(n['mi'], {})
                    d[q] = max(d.get(q, 0), n['midi'])
                else:
                    pcs.setdefault(n['mi'], set()).add(n['midi'] % 12)
                    q = n['on'] - self.starts[n['mi']]
                    cur = low.get(n['mi'])
                    if cur is None or (q, n['midi']) < cur:
                        low[n['mi']] = (q, n['midi'])
        return top, low, pcs

    def signatures(self):
        """A bar's melody, rhythm and intervals only: the same tune a half step up matches."""
        top, _, _ = self.melody()
        sig = {}
        for mi, d in top.items():
            qs = sorted(d)
            sig[mi] = tuple((q, d[b] - d[a]) for a, b, q in zip(qs, qs[1:], qs[1:])) + ((qs[0], 0),)
        return sig


# ----------------------------------------------------------------------------- the draft plan

def section_starts(W):
    """Measure indices where a section may begin: rehearsal marks, double barlines, a new key."""
    out = set()
    for p in W.parts:
        for mi, m in enumerate(p.findall('measure')):
            if m.find('.//rehearsal') is not None:
                out.add(mi)
            for bl in m.findall('barline'):
                if (bl.findtext('bar-style') or '') in ('light-light', 'light-heavy', 'heavy-light'):
                    out.add(mi + 1 if bl.get('location', 'right') == 'right' else mi)
            if mi and m.find('attributes/key') is not None:
                out.add(mi)
    return out


def draft_rows(W):
    """Rows broken where the music rests: after two quarters' rest; after any rest at the end of a
    sentence; after a quarter's rest where the singers change. Parts singing different words at once
    (one part holding while another answers) get rows of their own."""
    rows, open_ = [], []
    for t in W.tokens:
        q0 = W.starts[t['mi']] + t['q']
        ps = set(t['parts'])
        home = None
        for r in open_:
            if not (r['parts'] & ps):
                continue
            last = r['tokens'][-1]
            gap = q0 - max(v[1] for v in last['parts'].values())
            same = set(last['parts']) == ps
            end = bool(re.search(r'[.?!]["”\']?$', last['text']))
            if gap >= 2 or (gap > 0 and end) or (gap >= 1 and not same):
                continue
            home = r
            break
        # a row that shares singers with this word and did not take it is finished
        open_ = [r for r in open_ if r is home or not (r['parts'] & ps)]
        if home is None:
            home = dict(tokens=[], parts=set())
            rows.append(home)
            open_.append(home)
        home['tokens'].append(t)
        home['parts'] |= ps
    return rows


def auto_short(name):
    return re.sub(r'\s*\(.*?\)\s*', ' ', name).strip()


def auto_set(W, ps):
    ps = W.sort_parts(ps)
    short = [auto_short(p) for p in ps]
    choir = [n for n in W.names if not n.lower().startswith('solo')]
    if set(ps) == set(choir) and len(choir) > 1:
        label = 'All'
    elif len(ps) == 1:
        label = short[0]
    elif all(s.lower().startswith('solo') for s in short):
        label = 'Solos'
    elif len({s.split()[0] for s in short}) == 1:
        label = short[0].split()[0] + 's'
    else:
        label = '/'.join(short)
    tag = ''.join(dict.fromkeys(s[0].upper() + ''.join(c for c in s if c.isdigit()) if s.lower().startswith('solo')
                                else s[0].upper() for s in short))
    return dict(label=label, tag=tag)


def bq(W, mi, q):
    return W.numbers[mi] + ('' if q == 0 else f':{q}')


def draft(lyrics, out, title=None, credits=None, colours=None):
    W = Words(lyrics)
    rows = draft_rows(W)
    starts = section_starts(W)
    sig = W.signatures()
    # sections: at the section starts, each taking the rows that begin inside it
    secs = []
    for r in rows:
        mi = r['tokens'][0]['mi']
        if not secs or any(secs[-1]['mi'] < s <= mi for s in starts):
            secs.append(dict(mi=mi, rows=[]))
        secs[-1]['rows'].append(r)
    # letters by melody: a section whose bars mostly match an earlier section's, bar for bar, shares its letter
    letters, spans = [], []
    for k, s in enumerate(secs):
        lo = s['mi']
        hi = secs[k + 1]['mi'] if k + 1 < len(secs) else len(W.numbers)
        spans.append((lo, hi))
    for k, (lo, hi) in enumerate(spans):
        best = (0, None)
        for j in range(k):
            a0, a1 = spans[j]
            n = min(hi - lo, a1 - a0)
            both = [d for d in range(n) if sig.get(lo + d) and sig.get(a0 + d)]
            if both:
                m = sum(sig[lo + d] == sig[a0 + d] for d in both) / len(both)
                if m > best[0]:
                    best = (m, j)
        if best[0] >= 0.5:
            letters.append(letters[best[1]])
        else:
            letters.append(chr(ord('A') + len(set(letters))))
    colours = colours or default_colours(W)
    sets = {}
    plan_secs = []
    for s, L, (lo, hi) in zip(secs, letters, spans):
        prow = []
        for r in s['rows']:
            t0, t1 = r['tokens'][0], r['tokens'][-1]
            nxt = next((u for u in W.tokens if (u['mi'], u['q']) > (t1['mi'], t1['q'])), None)
            end = bq(W, nxt['mi'], nxt['q']) if nxt else str(int(W.numbers[-1]) + 1)
            row = {'from': bq(W, t0['mi'], t0['q']), 'to': end}
            others = [u for u in W.tokens if t0['id'] <= u['id'] <= t1['id'] and u not in r['tokens']]
            if others:
                row['parts'] = W.sort_parts(r['parts'])
            prow.append(row)
            for u in r['tokens']:
                for ps in (r['parts'], set(u['parts'])):
                    key = '+'.join(W.sort_parts(ps))
                    sets.setdefault(key, auto_set(W, ps))
        plan_secs.append({'name': L + '?', 'bars': f'{W.numbers[lo]}-{W.numbers[hi - 1]}', 'rows': prow})
    plan = {
        'lyrics': os.path.relpath(os.path.abspath(lyrics), os.path.dirname(os.path.abspath(out))),
        'title': title or W.title or os.path.splitext(os.path.basename(lyrics))[0],
        'credits': credits or 'lyric sheet',
        'reviewed': False,
        'names': {n: auto_short(n) for n in W.names},
        'colours': colours,
        'sets': sets,
        'sections': plan_secs,
        'words': [],
        'edits': [],
    }
    with open(out, 'w') as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)
    print(f'lyric sheet: draft plan written, {out}: {sum(len(s["rows"]) for s in plan_secs)} rows in '
          f'{len(plan_secs)} sections, lettered by melody')
    structure(W, [(p['name'], p['bars']) for p in plan_secs])
    return out


def default_colours(W):
    """As score_video.py gives them by default: the choir parts, paired in score order, first."""
    pal = sv.PALETTE
    choir = [n for n in W.names if not n.lower().startswith('solo')]
    order = choir + [n for n in W.names if n not in choir]
    return {n: pal[k % len(pal)] for k, n in enumerate(order)}


NOTE = 'C C# D Eb E F F# G Ab A Bb B'.split()


def structure(W, secs=None):
    """The melody and harmony bar by bar, for naming the sections from the music."""
    top, low, pcs = W.melody()
    print('\nbar  bass  accompaniment          melody (highest sung note at each onset)')
    for mi, num in enumerate(W.numbers):
        d = top.get(mi, {})
        mel = ' '.join(f'{NOTE[d[q] % 12]}{d[q] // 12 - 1}' for q in sorted(d))
        b = low.get(mi)
        print(f'{num:>4}  {NOTE[b[1] % 12] if b else "-":>4}  {" ".join(NOTE[p] for p in sorted(pcs.get(mi, ()))):<22} {mel}')
    if secs:
        print('\nsections (letters: the same melody, bar for bar, allowing a change of key):')
        for name, bars in secs:
            print(f'   {name:<6} bars {bars}')


# ----------------------------------------------------------------------------- reading a plan

class Sheet:
    """A plan read and applied: sections of rows of tokens, with the bold words, emoji and edits."""

    def __init__(self, plan_path, colours=None):
        self.path = plan_path
        self.plan = json.load(open(plan_path))
        unknown = set(self.plan) - set(PLAN_KEYS)
        if unknown:
            print(f'lyric sheet: plan keys not used: {sorted(unknown)}')
        lp = os.path.join(os.path.dirname(os.path.abspath(plan_path)), self.plan['lyrics'])
        self.W = W = Words(lp)
        self.colours = dict(self.plan.get('colours') or default_colours(W))
        if colours:
            self.colours.update(colours)
        self.problems = []
        for e in self.plan.get('edits', []):
            hit = [t for t in W.tokens if t['bar'] == str(e['bar']) and norm(t['text']) == norm(e['syllable'])]
            if not hit:
                self.problems.append(f'edit {e}: no such syllable')
            for t in hit[:1]:
                t['text'] = e['show']
        self.sections, used = [], set()
        for sec in self.plan['sections']:
            lines = []
            for row in sec['rows']:
                try:
                    a, b = W.pos(row['from']), W.pos(row['to'])
                except ValueError as ex:
                    self.problems.append(f'{sec["name"]}: row {row}: {ex}')
                    continue
                flt = set(row['parts']) if row.get('parts') else None
                if row.get('continues') and lines and flt is None:
                    flt = lines[-1]['flt']
                ts = [t for t in W.tokens if a <= (t['mi'], t['q']) < b and t['id'] not in used and
                      (flt is None or set(t['parts']) & flt)]
                if not ts:
                    self.problems.append(f'{sec["name"]}: row {row["from"]}-{row["to"]} has no words')
                    continue
                used |= {t['id'] for t in ts}
                ps = set().union(*[set(t['parts']) for t in ts])
                if row.get('continues') and lines:
                    lines[-1]['conts'].append(ts)
                    lines[-1]['parts'] |= ps
                else:
                    lines.append(dict(tokens=ts, parts=ps, bar=ts[0]['bar'], flt=flt, conts=[]))
            self.sections.append((sec['name'], lines))
        missing = [t for t in W.tokens if t['id'] not in used]
        if missing:
            self.problems.append('words in no row: ' + '; '.join(f'bar {t["bar"]} "{t["text"]}"'
                                                                  for t in missing[:12]))
        for w in self.plan.get('words', []):
            self.mark(w)
        for name, lines in self.sections:
            if not name or name.endswith('?'):
                self.problems.append(f'section {name or "(unnamed)"}: name it from the musical structure')
            for ln in lines:
                for ts in [ln['tokens']] + ln['conts']:
                    if not any(t.get('bold') for t in ts):
                        self.problems.append(f'{name}: the row at bar {ts[0]["bar"]} has no bold key word')
        if not self.plan.get('reviewed'):
            self.problems.append('"reviewed" is not true: finish the plan, then set it')

    def mark(self, w):
        W = self.W
        grp = set(w['parts']) if w.get('parts') else None
        for i, t in enumerate(W.tokens):
            if t['bar'] != str(w['bar']) or t['syl'] not in ('single', 'begin'):
                continue
            if grp and not set(t['parts']) & grp:
                continue
            word, j = [t], i
            while word[-1]['syl'] in ('begin', 'middle') and j + 1 < len(W.tokens):
                j += 1
                u = W.tokens[j]
                if u['syl'] in ('middle', 'end') and set(u['parts']) & set(t['parts']):
                    word.append(u)
            if norm(''.join(x['text'] for x in word)) == norm(w['word']):
                for x in word:
                    x['bold'] = True
                if w.get('emoji'):
                    word[-1]['emoji'] = w['emoji']
                else:
                    self.problems.append(f'word {w["word"]!r} at bar {w["bar"]}: no emoji')
                return
        self.problems.append(f'word {w["word"]!r}: not found in bar {w["bar"]}')

    def set_info(self, ps):
        key = '+'.join(self.W.sort_parts(ps))
        s = (self.plan.get('sets') or {}).get(key)
        return s or auto_set(self.W, set(ps))

    def short(self, name):
        return (self.plan.get('names') or {}).get(name, auto_short(name))


# ----------------------------------------------------------------------------- layout and drawing

def set_opts(cx):
    fo = cairo.FontOptions()
    fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
    fo.set_hint_style(cairo.HINT_STYLE_NONE)
    cx.set_font_options(fo)


def rgb(h, a=None):
    h = h.lstrip('#')
    c = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return c if a is None else c + (a,)


def segs(s, bd):
    """A bold word's own letters bold; its quote marks and punctuation not."""
    if not bd:
        return [(s, False)]
    m = re.match(r'^(\W*)(.*?)(\W*)$', s)
    return [(p, b) for p, b in ((m.group(1), False), (m.group(2), True), (m.group(3), False)) if p]


_EMO = {}


def emoji_surface(ch):
    """A colour emoji as a 128 px cairo surface (the font's bitmaps, drawn by pillow)."""
    if ch not in _EMO:
        from PIL import Image, ImageDraw, ImageFont
        f = ImageFont.truetype(emoji_font(), 109)
        im = Image.new('RGBA', (136, 128), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
        arr = np.asarray(im.crop((0, 0, 128, 128))).astype(np.float32)
        al = arr[..., 3:4] / 255
        pm = np.concatenate([arr[..., 2:3] * al, arr[..., 1:2] * al, arr[..., 0:1] * al, arr[..., 3:4]], 2)
        _EMO[ch] = cairo.ImageSurface.create_for_data(bytearray(pm.astype(np.uint8).tobytes()),
                                                      cairo.FORMAT_ARGB32, 128, 128, 512)
    return _EMO[ch]


class Layout:
    """Everything's position, in page units: title, legend, then the sections in columns, none broken."""

    def __init__(self, S, W, H, margin, fs, title_fs, gutter, col_gap, lead=1.34, ncols=2, subtitle=True):
        self.S, self.W, self.H, self.fs, self.font = S, W, H, fs, font_family()
        self.cx = cairo.Context(cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None))
        set_opts(self.cx)
        self.items, self.boxes, self.overflow = [], {}, -1e9
        self.m, self.gutter, self.col_gap, self.ncols = margin, gutter, col_gap, ncols
        self.lead, self.sec_gap = lead * fs, 0.9 * fs
        y = margin + title_fs * 0.9
        self.text(margin, y, S.plan['title'], title_fs, bold=True)
        if subtitle and S.plan.get('credits'):
            self.text(margin, y + fs * 1.15, S.plan['credits'], fs * 0.72, colour='#555555')
        x = W - margin
        for n in reversed(S.W.names):
            nm = S.short(n)
            x -= self.width(nm, fs * 0.72, bold=True)
            self.text(x, y, nm, fs * 0.72, bold=True, colour=S.colours[n])
            x -= fs * 0.55
            self.items.append(('dot', x + fs * 0.2, y - fs * 0.24, fs * 0.2, S.colours[n]))
            x -= fs * 0.9
        self.legend_left = x
        y += (fs * 1.15 if subtitle and S.plan.get('credits') else 0) + fs * 0.6
        self.items.append(('rule', margin, y, W - margin, y))
        self.head_y = margin + title_fs * 0.9
        self.top = y + fs * 0.6
        self.colw = (W - 2 * margin - (ncols - 1) * col_gap) / ncols

    def width(self, s, size, bold=False, italic=False):
        self.cx.select_font_face(self.font, cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
                                 cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        self.cx.set_font_size(size)
        return self.cx.text_extents(s).x_advance

    def text(self, x, y, s, size, bold=False, italic=False, colour='#000000'):
        self.items.append(('text', x, y, s, size, bold, italic, colour))

    def pieces(self, ts, line_parts):
        out = []
        for j, t in enumerate(ts):
            s = t['text']
            if j == 0:                                    # a row starts with a capital
                i = next((k for k, c in enumerate(s) if c.isalpha()), None)
                if i is not None and not (i > 0 and s[i - 1] == "'"):
                    s = s[:i] + s[i].upper() + s[i + 1:]
            space = t['syl'] in ('single', 'end') and j < len(ts) - 1
            out.append([t, s, space, set(t['parts']) != line_parts])
        return out

    def measure(self, pcs):
        fs, w = self.fs, 0
        for t, s, sp, sub in pcs:
            w += sum(self.width(p, fs, italic=sub, bold=b) for p, b in segs(s, t.get('bold', False)))
            w += self.width(' ', fs) if sp else 0
            w += fs * EMO_W if t.get('emoji') else 0
            if sub:
                w += self.width(self.S.set_info(t['parts'])['tag'], fs * 0.5, bold=True) + fs * 0.06
        return w

    def flow(self):
        """Lay out every section; returns the tallest column's height. Rows never wrap: a row wider than
        its column shows as self.overflow > 0, and the caller makes the type smaller."""
        fs = self.fs
        avail = self.colw - self.gutter - fs * 1.25
        blocks = []
        for name, lines in self.S.sections:
            rows = []
            for ln in lines:
                for k, ts in enumerate([ln['tokens']] + ln['conts']):
                    pcs = self.pieces(ts, ln['parts'])
                    self.overflow = max(self.overflow, self.measure(pcs) + (fs * 0.8 if k else 0) - avail)
                    rows.append(dict(pcs=pcs, line=ln, first=k == 0))
            blocks.append((name, rows, fs * 1.25 + len(rows) * self.lead))
        tot = [b[2] for b in blocks]
        hcol = lambda a, b: sum(tot[a:b]) + (b - a - 1) * self.sec_gap
        best = None
        for cuts in itertools.combinations(range(1, len(blocks)), self.ncols - 1):
            e = (0,) + cuts + (len(blocks),)
            v = max(hcol(a, b) for a, b in zip(e[:-1], e[1:]))
            if best is None or v < best[0]:
                best = (v, e)
        e = best[1]
        for ci, (a, b) in enumerate(zip(e[:-1], e[1:])):
            x0 = self.m + ci * (self.colw + self.col_gap)
            y = self.top
            for name, rows, h in blocks[a:b]:
                y += fs * 0.95
                self.text(x0, y, name.upper(), fs * 0.66, bold=True, colour='#6b6b6b')
                y += fs * 0.3
                for r in rows:
                    y += self.lead
                    self.row(x0, y, r)
                y += self.sec_gap
        return best[0]

    def row(self, x0, y, r):
        fs, S, ln = self.fs, self.S, r['line']
        if r['first']:
            lx = x0
            for p in S.W.sort_parts(ln['parts']):
                self.items.append(('dot', lx + fs * 0.17, y - fs * 0.3, fs * 0.17, S.colours[p]))
                lx += fs * 0.38
            self.text(x0, y + fs * 0.62, S.set_info(ln['parts'])['label'], fs * 0.5, colour='#777777')
            s = str(ln['bar'])
            self.text(x0 + self.colw - self.width(s, fs * 0.55), y, s, fs * 0.55, colour='#9a9a9a')
        x = x0 + self.gutter + (0 if r['first'] else fs * 0.8)
        pcs = r['pcs']
        for j, (t, s, sp, sub) in enumerate(pcs):
            w = 0
            for p, b in segs(s, t.get('bold', False)):
                self.text(x + w, y, p, fs, italic=sub, bold=b)
                w += self.width(p, fs, italic=sub, bold=b)
            self.boxes.setdefault(t['id'], []).append((x, y, x + w))
            x += w
            if sub and (j == len(pcs) - 1 or not pcs[j + 1][3] or set(pcs[j + 1][0]['parts']) != set(t['parts'])):
                tg = S.set_info(t['parts'])['tag']
                x += fs * 0.06
                self.text(x, y - fs * 0.38, tg, fs * 0.5, bold=True,
                          colour=S.colours[S.W.sort_parts(t['parts'])[0]])
                x += self.width(tg, fs * 0.5, bold=True)
            if t.get('emoji'):
                self.items.append(('emoji', x + fs * 0.12, y, t['emoji'], fs))
                x += fs * EMO_W
            if sp:
                x += self.width(' ', fs)

    def draw(self, cx):
        set_opts(cx)
        for it in self.items:
            if it[0] == 'text':
                _, x, y, s, size, bold, italic, colour = it
                cx.select_font_face(self.font, cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
                                    cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
                cx.set_font_size(size)
                cx.set_source_rgb(*rgb(colour))
                cx.move_to(x, y)
                cx.show_text(s)
            elif it[0] == 'emoji':
                _, x, y, ch, size = it
                sc = size * 0.95 / 128
                cx.save()
                cx.translate(x, y - size * 0.8)
                cx.scale(sc, sc)
                cx.set_source_surface(emoji_surface(ch), 0, 0)
                cx.get_source().set_filter(cairo.FILTER_BEST)
                cx.paint()
                cx.restore()
            elif it[0] == 'dot':
                _, x, y, r, colour = it
                cx.set_source_rgb(*rgb(colour))
                cx.new_path()
                cx.arc(x, y, r, 0, 2 * math.pi)
                cx.fill()
            elif it[0] == 'rule':
                _, x0, y0, x1, y1 = it
                cx.set_source_rgb(*rgb('#cccccc'))
                cx.set_line_width(max(0.6, self.fs * 0.05))
                cx.move_to(x0, y0)
                cx.line_to(x1, y1)
                cx.stroke()

    def highlight(self, cx, tid, cols):
        """Bands, one per part singing, top to bottom in score order (as the score videos stack them)."""
        fs, pad = self.fs, self.fs * 0.12
        for x0, y, x1 in self.boxes.get(tid, []):
            top, bot = y - fs * 0.86, y + fs * 0.3
            h = (bot - top) / len(cols)
            for k, c in enumerate(cols):
                cx.set_source_rgba(*rgb(c, 0.55))
                cx.rectangle(x0 - pad, top + k * h, x1 - x0 + 2 * pad, h)
                cx.fill()


def fit(S, W, H, margin, ncols, start, step, gutter_k, col_gap, bottom, subtitle, title_k=None):
    """The largest type with every row on one line and every column on the page; then the line
    spacing opened into the room left."""
    fs = start
    mk = lambda fs, lead: Layout(S, W, H, margin=margin, fs=fs, title_fs=title_k * fs if title_k else 22,
                                 gutter=fs * gutter_k, col_gap=col_gap(fs), lead=lead, ncols=ncols,
                                 subtitle=subtitle)
    while True:
        L = mk(fs, 1.34)
        h = L.flow()
        if L.overflow <= 0 and L.top + h <= H - bottom:
            break
        fs -= step
    lead = 1.34
    while lead < 1.8:
        L2 = mk(fs, lead + 0.02)
        h2 = L2.flow()
        if L2.top + h2 > H - bottom:
            break
        L, lead = L2, lead + 0.02
    return L, fs, lead


FOOTNOTE = ('Dots: who sings the row.  Italic words with a small tag: only those parts sing them.  '
            'Grey numbers: the bar where the row starts.')


def layouts(S):
    """The two layouts, each computed once, so every copy of a layout is the same:
    'page', the letter portrait page in two columns (the PDF's second page, and the iPad video);
    'screen', 1920x1080 in three columns (the 16:9 video, and the PDF's first page)."""
    if not hasattr(S, '_layouts'):
        S._layouts = {
            'page': fit(S, 612, 792, 34, 2, 12.0, 0.1, 2.75, lambda fs: 18, 30, True),
            'screen': fit(S, 1920, 1080, 34, 3, 32.0, 0.25, 2.75, lambda fs: fs * 1.3, 20, False, title_k=1.45),
        }
    return S._layouts


def footnote(cx, L):
    cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cx.set_font_size(7.5)
    cx.set_source_rgb(*rgb('#888888'))
    cx.move_to(34, L.H - 20)
    cx.show_text(FOOTNOTE)


def pdf(S, out):
    """Two pages. First, landscape letter: the 16:9 video's page, the full width, with the paper
    below it left empty. Second, portrait letter: the page to print (and the iPad video's page).
    One file, so nobody downloads the wrong one."""
    lay = layouts(S)
    Ls, fs_s, _ = lay['screen']
    Lp, fs_p, lead_p = lay['page']
    surf = cairo.PDFSurface(out, 792, 612)
    cx = cairo.Context(surf)
    cx.save()
    k = 792 / Ls.W
    cx.scale(k, k)
    Ls.draw(cx)
    cx.restore()
    cx.show_page()
    surf.set_size(612, 792)
    cx = cairo.Context(surf)
    Lp.draw(cx)
    footnote(cx, Lp)
    surf.finish()
    print(f'lyric sheet: {os.path.basename(out)}: page 1 landscape, the 16:9 video\'s page '
          f'({fs_s * k:.1f} pt type, {612 - Ls.H * k:.0f} pt empty below); page 2 portrait, to print '
          f'({fs_p:.1f} pt type, line spacing {lead_p:.2f}); '
          f'{sum(len(ln["conts"]) + 1 for _, lns in S.sections for ln in lns)} rows, all on one line each')
    return out


SHAPES = {
    # 16:9, the three-column layout at its own size
    'screen': dict(size=(1920, 1080), layout='screen'),
    # 3:4 for an iPad in portrait: the printed page, scaled to the full width, at the top; the band
    # left below it carries the bar number
    'ipad': dict(size=(1536, 2048), layout='page'),
}


def video(S, wins, bars, mp3, out, featured=None, crf=20, shape='screen'):
    """The sheet with each syllable lit while it is sung: in the colours of every part singing it
    (stacked), or in a part's own video, that part's colour where it sings and grey where only others
    do. shape 'screen': 1920x1080, three columns. shape 'ipad': 1536x2048 (3:4 portrait), exactly the
    printed page. wins: (audio start, audio end, token id, part name). bars: (audio time, bar
    number) for the bar number shown. One frame per change, exact to the millisecond."""
    W, H = SHAPES[shape]['size']
    L, fs, lead = layouts(S)[SHAPES[shape]['layout']]
    k = min(W / L.W, H / L.H)
    band = H - L.H * k                       # below the page: the iPad's bar number goes here
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                mp3], capture_output=True, text=True).stdout)
    bar_t = np.array([b[0] for b in bars])

    def state(t):
        act = tuple(sorted((tid, p) for t0, t1, tid, p in wins if t0 <= t < t1))
        j = int(np.searchsorted(bar_t, t, side='right')) - 1
        return act, (bars[j][1] if j >= 0 else None)

    def draw(st, path):
        act, bar = st
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
        cx = cairo.Context(surf)
        cx.set_source_rgb(1, 1, 1)
        cx.paint()
        cx.save()
        cx.translate((W - L.W * k) / 2, 0)
        cx.scale(k, k)
        by = {}
        for tid, p in act:
            by.setdefault(tid, []).append(p)
        for tid, ps in by.items():
            if featured is None:
                L.highlight(cx, tid, [S.colours[p] for p in S.W.sort_parts(ps)])
            else:
                L.highlight(cx, tid, [S.colours[featured] if featured in ps else GREY])
        L.draw(cx)
        if shape == 'ipad':
            footnote(cx, L)
        cx.restore()
        # the bar number, and whose video it is: in the header on the 16:9 screen, below the page on
        # the iPad
        size = fs * 0.7 * k if shape == 'screen' else min(band * 0.45, 30)
        y = L.head_y * k if shape == 'screen' else H - band / 2 + size * 0.35
        cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cx.set_font_size(size)
        bits = []
        if bar is not None:
            bits.append((f'bar {bar}', '#8a8a8a', False))
        if featured is not None:
            bits.append((f'{S.short(featured)} in colour, other parts grey', S.colours[featured], True))
        if shape == 'screen':
            x = W / 2
            for s, c, b in bits:
                cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL,
                                    cairo.FONT_WEIGHT_BOLD if b else cairo.FONT_WEIGHT_NORMAL)
                cx.set_source_rgb(*rgb(c))
                w = cx.text_extents(s).x_advance
                cx.move_to(x - (w / 2 if not b else 0) + (fs * 3 * k if b else 0), y)
                cx.show_text(s)
        else:
            x = 34 * k
            for s, c, b in bits:
                cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL,
                                    cairo.FONT_WEIGHT_BOLD if b else cairo.FONT_WEIGHT_NORMAL)
                cx.set_source_rgb(*rgb(c))
                cx.move_to(x, y)
                cx.show_text(s)
                x += cx.text_extents(s).x_advance + size * 1.5
        surf.write_to_png(path)

    times = sorted({0.0} | {x for w in wins for x in w[:2] if 0 <= x < dur} | {b for b in bar_t if 0 <= b < dur})
    segs_ = []
    for t in times:
        st = state(t)
        ms = int(round(1000 * t))
        if segs_ and (segs_[-1][1] == st or segs_[-1][0] == ms):
            if segs_[-1][1] != st:
                segs_[-1] = (ms, st)
            continue
        segs_.append((ms, st))
    end_ms = int(round(1000 * dur))
    tmpd = tempfile.mkdtemp(prefix='lyric_video_')
    lines, files = ['ffconcat version 1.0'], {}
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
        futs = []
        for j, (ms, st) in enumerate(segs_):
            if st not in files:
                files[st] = os.path.join(tmpd, f'{len(files):06d}.png')
                futs.append(pool.submit(draw, st, files[st]))
            nxt = segs_[j + 1][0] if j + 1 < len(segs_) else end_ms
            lines += [f"file '{files[st]}'", 'option framerate 1000', f'duration {(nxt - ms) / 1000:.3f}']
        for f in futs:
            f.result()
    lines += [f"file '{files[segs_[-1][1]]}'", 'option framerate 1000']
    lst = os.path.join(tmpd, 'frames.ffconcat')
    open(lst, 'w').write('\n'.join(lines) + '\n')
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-i', mp3,
                        '-map', '0:v', '-map', '1:a', *sv.vfr_flag(), '-video_track_timescale', '1000',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-g', '30',
                        '-crf', str(crf), '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                        '-t', f'{dur:.3f}', '-movflags', '+faststart', out])
    shutil.rmtree(tmpd, ignore_errors=True)
    if r.returncode:
        sys.exit(f'ffmpeg failed on {out}')
    pts = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'frame=pts_time',
                          '-of', 'csv=p=0', out], capture_output=True, text=True).stdout.replace(',', '').split()
    err = (max(abs(float(p) * 1000 - s[0]) for p, s in zip(pts, segs_)) if len(pts) == len(segs_) else None)
    print(f'   wrote {os.path.basename(out)}: {W}x{H}, {fs * k:.1f} px type, {len(segs_)} frames, one per change '
          f'of lights; ' + (f'every frame where planned (within {err:.0f} ms)' if err is not None
                            else f'{len(pts)} frames in the file, {len(segs_)} planned'))
    return out


def windows(S, to_audio, final_q=None, last_audio=None):
    """(audio start, end, token id, part) for every syllable of every part, at every time it is sung.
    to_audio(mi, q0, q1) -> [(t0, t1), ...], one per time the bar is played (repeats)."""
    W, out = S.W, []
    end_q = final_q if final_q is not None else max(q1 for t in W.tokens for _, q1 in t['parts'].values())
    for t in W.tokens:
        for p, (q0, q1) in t['parts'].items():
            for t0, t1 in to_audio(t['mi'], q0, q1):
                if last_audio is not None and q1 >= end_q:
                    t1 = max(t1, last_audio)        # the last syllable stays lit through the final hold
                out.append((t0, t1, t['id'], p))
    return out


# ----------------------------------------------------------------------------- command line

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('plan')
    p.add_argument('lyrics')
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--title')
    p.add_argument('--credits')
    p = sub.add_parser('structure')
    p.add_argument('lyrics')
    p = sub.add_parser('pdf')
    p.add_argument('plan')
    p.add_argument('-o', '--out')
    a = ap.parse_args()
    if a.cmd == 'plan':
        if os.path.exists(a.out):
            sys.exit(f'{a.out} exists; not overwriting a plan that may have been finished by hand')
        draft(a.lyrics, a.out, a.title, a.credits)
    elif a.cmd == 'structure':
        structure(Words(a.lyrics))
    else:
        S = Sheet(a.plan)
        if S.problems:
            print('lyric sheet plan: not ready:\n   ' + '\n   '.join(S.problems))
            sys.exit(1)
        out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.plan)),
                                    S.plan['title'] + ' - lyric sheet.pdf')
        pdf(S, out)


if __name__ == '__main__':
    main()
