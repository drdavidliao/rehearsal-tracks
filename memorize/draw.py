"""Frames for a memorization lesson drawn over a song's 16:9 lyric sheet (lyric_sheet.py, SKILL.md 10.1).

The sheet is laid out exactly as the song's lyric video ('screen' layout), so a frame with nothing faded is that
video's frame. On top of it a View can:
  - fade each word (token) and its emoji separately (alpha 0..1); key words are the plan's bold words;
  - shade each section in a rounded box, one colour per kind of section (every chorus the same);
  - pulse words (a soft glow behind word and emoji) while the narration names them;
  - move a camera (centre and zoom on the page) to a block;
  - show an index card of the key words, or of chosen cue words, instead of the sheet.
Lights (which syllables are being sung) are drawn as the lyric video draws them, from the token's parts.
"""
import math, os, sys
from dataclasses import dataclass, field
import cairo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lyric_sheet as ls

W, H = 1920, 1080


class Sheet:
    """The song's sheet, its screen layout, and which drawn items belong to which token."""

    def __init__(self, plan, kinds):
        """kinds: section name -> kind ('verse', 'chorus', 'bridge', 'tag'), which picks its shade."""
        self.args = (plan, kinds)                 # to rebuild it in a worker process (it holds cairo objects)
        self.S = S = ls.Sheet(plan)
        self.L = L = ls.layouts(S)['screen'][0]
        self.k = min(W / L.W, H / L.H)
        self.ox = (W - L.W * self.k) / 2
        self.tok = {t['id']: t for t in S.W.tokens}
        fs = L.fs
        # a text item at a token box's line and inside its x range is that token's; an emoji item just after a
        # token with an emoji is that token's
        self.owner = {}
        for i, it in enumerate(L.items):
            if it[0] == 'text' and abs(it[4] - fs) < 1e-6:
                for tid, bx in L.boxes.items():
                    if any(abs(y - it[2]) < 1e-6 and x0 - 1e-6 <= it[1] < x1 - 1e-6 for x0, y, x1 in bx):
                        self.owner[i] = tid
                        break
            elif it[0] == 'text' and abs(it[4] - fs * 0.5) < 1e-6 and it[5]:
                # a part tag ("Bar B") just after a word: that word's
                for tid, bx in L.boxes.items():
                    if any(abs(y - fs * 0.38 - it[2]) < 1e-6 and 0 <= it[1] - x1 < fs * 0.3 for x0, y, x1 in bx):
                        self.owner[i] = tid
            elif it[0] == 'emoji':
                # the nearest word with an emoji ending before it on its line (a part tag may sit between)
                best, gap = None, 1e9
                for tid, bx in L.boxes.items():
                    if not self.tok[tid].get('emoji'):
                        continue
                    for x0, y, x1 in bx:
                        if abs(y - it[2]) < 1e-6 and 0 <= it[1] - x1 < min(gap, fs * 3):
                            best, gap = tid, it[1] - x1
                self.owner[i] = best
        # sections: their tokens, kind, and the box round heading and rows
        # a heading the sheet repeats ("Chorus" three times) gets a numbered key ("Chorus 2", "Chorus 3"): the
        # script names sections by key; the sheet still prints the heading
        self.sections = []
        seen = {}
        for title, lines in S.sections:
            seen[title] = seen.get(title, 0) + 1
            name = title if seen[title] == 1 else f'{title} {seen[title]}'
            ids = [t['id'] for ln in lines for ts in [ln['tokens']] + ln['conts'] for t in ts]
            rows = [[t['id'] for t in ts] for ln in lines for ts in [ln['tokens']] + ln['conts']]
            heads = [i for i, it in enumerate(L.items) if it[0] == 'text' and it[3] == title.upper()]
            head = heads[seen[title] - 1]
            # a section the sheet carries on into the next column ("NAME (CONTINUED)") gets a box per column
            conts = [i for i, it in enumerate(L.items) if it[0] == 'text' and it[3] == title.upper() + ' (CONTINUED)']
            boxes = []
            for h in [head] + conts:
                hx, hy = L.items[h][1], L.items[h][2]
                ys = [y for tid in ids for x0, y, _ in L.boxes[tid] if hx - fs <= x0 < hx + L.colw and y > hy]
                # stop at the next heading below in this column (another section's)
                ys = [y for y in ys if not any(it[0] == 'text' and abs(it[1] - hx) < 1 and hy < it[2] < y and
                                               it[3].isupper() and len(it[3]) > 3 for it in L.items)]
                if ys:
                    boxes.append((hx - fs * 0.35, hy - fs * 0.85, hx + L.colw + fs * 0.35, max(ys) + fs * 0.75))
            self.sections.append(dict(name=name, title=title, kind=kinds.get(name, kinds.get(title)), ids=ids,
                                      rows=rows, head=head, box=boxes[0], boxes=boxes))
        self.key = {tid for tid, t in self.tok.items() if t.get('bold')}

    def section_of(self, tid):
        return next(s for s in self.sections if tid in s['ids'])

    def word_ids(self, tid):
        """All the tokens of the word token tid belongs to (syllables joined by hyphens). Two parts singing
        different words at once interleave their tokens ("a", "B", "c"), so a syllable's neighbours are the
        nearest tokens sung by the same parts."""
        ts = self.S.W.tokens
        i = next(j for j, t in enumerate(ts) if t['id'] == tid)
        same = lambda j: set(ts[j].get('parts', {})) == set(ts[i].get('parts', {}))
        out = [i]
        a = i
        while ts[a]['syl'] in ('middle', 'end'):
            a = next((j for j in range(a - 1, -1, -1) if same(j)), None)
            if a is None:
                break
            out.insert(0, a)
        b = i
        while ts[b]['syl'] in ('begin', 'middle'):
            b = next((j for j in range(b + 1, len(ts)) if same(j)), None)
            if b is None:
                break
            out.append(b)
        return [ts[j]['id'] for j in out]


SHADE = {'verse': '#7B6FB0', 'chorus': '#E0A400', 'bridge': '#3F9CA8', 'tag': '#8AA05A', 'refrain': '#C2607E'}


@dataclass
class View:
    lit: tuple = ()                    # token ids being sung
    alpha: dict = field(default_factory=dict)      # token id -> word alpha (default 1)
    ealpha: dict = field(default_factory=dict)     # token id -> its emoji's alpha (default: the word's)
    escale: dict = field(default_factory=dict)     # token id -> its emoji's size (1 = as printed), grown about its centre
    rest: float = 1.0                  # alpha of everything that is not a word (dots, labels, headings, bar nos)
    shade: float = 0.0                 # section shading, 0..1
    shade_only: tuple = ()             # if given, only these sections are shaded
    shade_each: object = None          # if a dict: section name -> its shading 0..1 (overrides shade)
    pulse: dict = field(default_factory=dict)      # token id -> glow 0..1
    cam: tuple = (W / 2, H / 2, 1.0)  # screen point at the centre, and zoom (kept at 1: zoom is ruled out)
    spot: tuple = ()                   # sections to spotlight: everything else darkens, feathered at the edge
    spot_k: float = 0.0                # how far the spotlight has come on, 0..1
    header: str = ''                   # step label, in the header
    bar: object = None
    card: object = None                # a Card to draw instead of (or over) the sheet
    card_alpha: float = 0.0
    caption: str = ''                  # narration caption at the bottom
    toc: tuple = ()                    # chapters: (label, start s, end s), drawn as a strip along the bottom
    now: float = 0.0                   # lesson time, for the strip's playhead


def rgb(h):
    return ls.rgb(h)


TOC_H = 64          # the chapter strip along the bottom; the page is scaled to fit above it


def draw(sh, v, path=None):
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    cx = cairo.Context(surf)
    cx.set_source_rgb(1, 1, 1)
    cx.paint()
    sc = (H - TOC_H) / H if v.toc else 1.0
    cx.save()
    cx.translate((W - W * sc) / 2, 0)
    cx.scale(sc, sc)
    cx.rectangle(0, 0, W, H)
    cx.clip()
    page(cx, sh, v)
    cx.restore()
    if v.spot and v.spot_k > 0:
        spotlight(surf, sh, v, sc)
        cx = cairo.Context(surf)
    if v.toc:
        toc(cx, v)
    if path:
        surf.write_to_png(path)
    return surf


SPOT_DARK = 0.42      # the darkened page: blended this far toward SPOT_INK
SPOT_INK = (24, 26, 32)
SPOT_FEATHER = 14     # px, Gaussian radius of the edge
_masks = {}


def spot_mask(sh, names, sc):
    """1 inside the spotlit sections' boxes, 0 outside, the edge feathered by a Gaussian blur."""
    key = (names, sc)
    if key not in _masks:
        from PIL import Image, ImageDraw, ImageFilter
        import numpy as np
        m = Image.new('L', (W, H), 0)
        d = ImageDraw.Draw(m)
        off = (W - W * sc) / 2
        for s in sh.sections:
            if s['name'] in names:
                for x0, y0, x1, y1 in s['boxes']:
                    pad = sh.L.fs * 0.25
                    box = [off + (sh.ox + (x0 - pad) * sh.k) * sc, (y0 - pad) * sh.k * sc,
                           off + (sh.ox + (x1 + pad) * sh.k) * sc, (y1 + pad) * sh.k * sc]
                    d.rounded_rectangle(box, radius=int(sh.L.fs * 0.6 * sh.k), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(SPOT_FEATHER))
        _masks[key] = np.asarray(m, dtype=np.float32)[:, :, None] / 255
    return _masks[key]


def spotlight(surf, sh, v, sc):
    import numpy as np
    surf.flush()
    a = np.ndarray((H, W, 4), np.uint8, surf.get_data())
    m = spot_mask(sh, tuple(v.spot), sc)
    top = int(H - TOC_H) if v.toc else H
    k = SPOT_DARK * v.spot_k * (1 - m[:top])
    rule = next(it for it in sh.L.items if it[0] == 'rule')[2]
    k[:int(rule * sh.k * sc) + 2] = 0                         # the header (title, step, legend) stays lit
    ink = np.array(SPOT_INK[::-1] + (0,), np.float32)        # BGRA in memory
    a[:top] = (a[:top] * (1 - k) + ink * k).astype(np.uint8)
    surf.mark_dirty()


def page(cx, sh, v):
    S, L, k = sh.S, sh.L, sh.k
    cx.save()
    cxx, cy, z = v.cam
    cx.translate(W / 2, H / 2)
    cx.scale(z, z)
    cx.translate(-cxx, -cy)
    cx.translate(sh.ox, 0)
    cx.scale(k, k)
    ls.set_opts(cx)
    fs = L.fs
    # section shading
    if v.shade > 0:
        for s in sh.sections:
            if v.shade_only and s['name'] not in v.shade_only:
                continue
            sa = v.shade if v.shade_each is None else v.shade * v.shade_each.get(s['name'], 0.0)
            if sa <= 0:
                continue
            c = rgb(SHADE[s['kind']])
            for x0, y0, x1, y1 in s['boxes']:
                rr(cx, x0, y0, x1 - x0, y1 - y0, fs * 0.45)
                cx.set_source_rgba(*c, 0.13 * sa)
                cx.fill_preserve()
                cx.set_source_rgba(*c, 0.75 * sa)
                cx.set_line_width(fs * 0.07)
                cx.stroke()
    # glow behind pulsed words
    for tid, g in v.pulse.items():
        if g <= 0:
            continue
        for x0, y, x1 in L.boxes.get(tid, []):
            x1e = x1 + (fs * ls.EMO_W + fs * 0.1 if sh.tok[tid].get('emoji') else 0)
            pad = fs * 0.25
            rr(cx, x0 - pad, y - fs * 1.0, x1e - x0 + 2 * pad, fs * 1.4, fs * 0.35)
            cx.set_source_rgba(1.0, 0.86, 0.2, 0.55 * g)
            cx.fill()
    # lights, as the lyric video draws them (stacked part colours), faded with the word
    for tid in v.lit:
        t = sh.tok[tid]
        cols = [S.colours[p] for p in S.W.sort_parts(t['parts'])]
        a = 1.0
        pad = fs * 0.12
        for x0, y, x1 in L.boxes.get(tid, []):
            top, bot = y - fs * 0.86, y + fs * 0.3
            hh = (bot - top) / len(cols)
            for j, c in enumerate(cols):
                cx.set_source_rgba(*rgb(c), 0.55 * a)
                cx.rectangle(x0 - pad, top + j * hh, x1 - x0 + 2 * pad, hh)
                cx.fill()
    # the sheet's items, each at its alpha
    for i, it in enumerate(L.items):
        tid = sh.owner.get(i)
        a = v.alpha.get(tid, 1.0) if tid is not None else v.rest
        if it[0] == 'emoji' and tid is not None and tid in v.ealpha:
            a = v.ealpha[tid]
        if a <= 0.003:
            continue
        if it[0] == 'text':
            _, x, y, s, size, bold, italic, colour = it
            cx.select_font_face(L.font, cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
            cx.set_font_size(size)
            cx.set_source_rgba(*rgb(colour), a)
            cx.move_to(x, y)
            cx.show_text(s)
        elif it[0] == 'emoji':
            _, x, y, ch, size = it
            g = v.escale.get(tid, 1.0)
            sc = size * 0.95 / 128 * g
            cx.save()
            cx.translate(x + size * 0.475 * (1 - g), y - size * 0.8 + size * 0.475 * (1 - g))
            cx.scale(sc, sc)
            cx.set_source_surface(ls.emoji_surface(ch), 0, 0)
            cx.get_source().set_filter(cairo.FILTER_BEST)
            cx.paint_with_alpha(a)
            cx.restore()
        elif it[0] == 'dot':
            _, x, y, r, colour = it
            cx.set_source_rgba(*rgb(colour), a)
            cx.new_path()
            cx.arc(x, y, r, 0, 2 * math.pi)
            cx.fill()
        elif it[0] == 'rule':
            _, x0, y0, x1, y1 = it
            cx.set_source_rgba(*rgb('#cccccc'), a)
            cx.set_line_width(max(0.6, fs * 0.05))
            cx.move_to(x0, y0)
            cx.line_to(x1, y1)
            cx.stroke()
    cx.restore()
    if v.cam[2] > 1.001:
        cx.set_source_rgba(1, 1, 1, min(1.0, (v.cam[2] - 1) * 4))
        cx.rectangle(0, 0, W, 92)
        cx.fill()
    if v.card is not None and v.card_alpha > 0:
        v.card.draw(cx, sh, v)
    header(cx, sh, v)
    if v.caption:
        caption(cx, v.caption)


def toc(cx, v):
    """The lesson's chapters as a strip along the bottom, each as wide as its share of the running time, the
    current one filled and a playhead at the current time: a scrubbing preview shows where in the lesson it is."""
    font = ls.font_family()
    y0 = H - TOC_H
    cx.set_source_rgb(*rgb('#f3f1ec'))
    cx.rectangle(0, y0, W, TOC_H)
    cx.fill()
    cx.set_source_rgb(*rgb('#d6d2c8'))
    cx.rectangle(0, y0, W, 1.5)
    cx.fill()
    T = v.toc[-1][2]
    m = 16
    span = W - 2 * m
    X = lambda t: m + span * t / T

    def chip(label, x0, x1, cur, top, bot, size, colour_on='#B8540A', colour_off='#e4e0d6'):
        rr(cx, x0 + 2, top, x1 - x0 - 4, bot - top, 8)
        cx.set_source_rgb(*rgb(colour_on if cur else colour_off))
        cx.fill()
        cx.select_font_face(font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if cur else cairo.FONT_WEIGHT_NORMAL)
        cx.set_font_size(size)
        lab = label
        if cx.text_extents(lab).x_advance > x1 - x0 - 12:
            lab = label.split(' ')[0]
        w = cx.text_extents(lab).x_advance
        if w > x1 - x0 - 6:
            return
        cx.set_source_rgb(*rgb('#ffffff' if cur else '#55524a'))
        cx.move_to((x0 + x1) / 2 - w / 2, (top + bot) / 2 + size * 0.35)
        cx.show_text(lab)

    for ch in v.toc:
        label, t0, t1 = ch[:3]
        subs = ch[3] if len(ch) > 3 else None
        cur = t0 <= v.now < t1
        if not subs:
            chip(label, X(t0), X(t1), cur, y0 + 10, y0 + TOC_H - 10, 21)
            continue
        # a step with parts: its name in a band on top, the parts as chips under it
        rr(cx, X(t0) + 2, y0 + 6, X(t1) - X(t0) - 4, TOC_H - 12, 8)
        cx.set_source_rgb(*rgb('#cfc7b6' if cur else '#e4e0d6'))
        cx.fill()
        cx.select_font_face(font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cx.set_font_size(15)
        cx.set_source_rgb(*rgb('#55524a'))
        cx.move_to(X(t0) + 12, y0 + 22)
        cx.show_text(label)
        for sl, s0, s1 in subs:
            chip(sl, X(s0), X(s1), s0 <= v.now < s1, y0 + 28, y0 + TOC_H - 9, 16)
    # playhead
    x = m + span * min(max(v.now, 0), T) / T
    cx.set_source_rgb(*rgb('#1a1a1a'))
    cx.rectangle(x - 1.5, y0 + 4, 3, TOC_H - 8)
    cx.fill()


def rr(cx, x, y, w, h, r):
    cx.new_path()
    cx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cx.close_path()


def header(cx, sh, v):
    """Bar number and step label between the title and the legend, as the lyric video places its bar number."""
    L, k = sh.L, sh.k
    size = L.fs * 0.7 * k
    y = L.head_y * k
    lo, hi = sh.ox + (L.title_right + L.fs) * k, sh.ox + (L.legend_left - L.fs) * k
    cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cx.set_font_size(size)
    bar = f'bar {v.bar}' if v.bar is not None else ''
    wb = cx.text_extents('bar 60').x_advance
    cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    wh = cx.text_extents(v.header).x_advance if v.header else 0
    tot = wb + (size * 1.5 + wh if v.header else 0)
    x = (lo + hi) / 2 - tot / 2
    cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cx.set_source_rgb(*rgb('#8a8a8a'))
    cx.move_to(x, y)
    cx.show_text(bar)
    if v.header:
        cx.select_font_face(L.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cx.set_source_rgb(*rgb('#B8540A'))
        cx.move_to(x + wb + size * 1.5, y)
        cx.show_text(v.header)


def caption(cx, s):
    font = ls.font_family()
    size = 30
    cx.select_font_face(font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cx.set_font_size(size)
    w = cx.text_extents(s).x_advance
    x = (W - w) / 2
    rr(cx, x - 18, H - 64, w + 36, 50, 12)
    cx.set_source_rgba(0.1, 0.1, 0.12, 0.82)
    cx.fill()
    cx.set_source_rgb(1, 1, 1)
    cx.move_to(x, H - 29)
    cx.show_text(s)


class Card:
    """An index card: each section's key words (or chosen cue words) with their emoji, sections in the sheet's
    order and columns. words: section name -> list of rows, each a list of token ids to show (the word's
    tokens joined). emoji_only: show emoji alone."""

    def __init__(self, sh, words, emoji_only=False, title='Song'):
        self.sh, self.words, self.emoji_only, self.title = sh, words, emoji_only, title

    def draw(self, cx, sh, v):
        a = v.card_alpha
        font = sh.L.font
        cw, ch = 1560, 900
        x0, y0 = (W - cw) / 2, (H - ch) / 2 + 30
        # shadow, card, ruled lines
        cx.save()
        cx.set_source_rgba(0, 0, 0, 0.18 * a)
        rr(cx, x0 + 8, y0 + 10, cw, ch, 14)
        cx.fill()
        cx.set_source_rgba(1.0, 0.985, 0.94, a)
        rr(cx, x0, y0, cw, ch, 14)
        cx.fill()
        cx.set_source_rgba(0.85, 0.3, 0.3, 0.55 * a)
        cx.set_line_width(2)
        cx.move_to(x0 + 20, y0 + 78)
        cx.line_to(x0 + cw - 20, y0 + 78)
        cx.stroke()
        cx.select_font_face(font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cx.set_font_size(34)
        cx.set_source_rgba(0.15, 0.15, 0.2, a)
        cx.move_to(x0 + 40, y0 + 56)
        cx.show_text(self.title)
        # the sheet's columns: sections in the left column of the sheet go left on the card
        mid = sh.ox + sh.L.W * sh.k / 2
        cols = {0: [], 1: []}
        for s in sh.sections:
            sx = sh.ox + s['box'][0] * sh.k
            cols[0 if sx < mid else 1].append(s)
        litw = set()
        for tid in v.lit:
            litw.update(sh.word_ids(tid))
        for c, secs in cols.items():
            x = x0 + 50 + c * (cw / 2)
            y = y0 + 125
            for s in secs:
                rows = self.words.get(s['name'], [])
                if not rows:
                    continue
                shade = rgb(SHADE[s['kind']])
                cx.select_font_face(font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cx.set_font_size(19)
                cx.set_source_rgba(*shade, a)
                cx.move_to(x, y)
                cx.show_text(s['name'].upper())
                y += 12
                top = y
                cur = any(t in s['ids'] for t in v.lit)
                y += 46
                xx = x + 22
                right = x + cw / 2 - 70
                fsz = 34 if not self.emoji_only else 40
                for row in rows:
                    for word in row:
                        ids = sh.word_ids(word)
                        t_last = sh.tok[ids[-1]]
                        txt = ''.join(sh.tok[i]['text'] for i in ids).strip(',.?!;:')
                        on = bool(set(ids) & litw)
                        cx.select_font_face(font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                        cx.set_font_size(fsz)
                        w = (cx.text_extents(txt).x_advance + 8 if not self.emoji_only else 0) + 46
                        if xx + w > right:
                            xx = x + 22
                            y += 50
                        if on:
                            cx.set_source_rgba(1.0, 0.82, 0.2, 0.65 * a)
                            rr(cx, xx - 7, y - fsz, w + 4, fsz + 14, 8)
                            cx.fill()
                        if not self.emoji_only:
                            cx.set_source_rgba(0.12, 0.12, 0.16, a)
                            cx.move_to(xx, y)
                            cx.show_text(txt)
                            xx += cx.text_extents(txt).x_advance + 8
                        em = t_last.get('emoji')
                        if em:
                            sc = fsz * 1.05 / 128
                            cx.save()
                            cx.translate(xx, y - fsz * 0.9)
                            cx.scale(sc, sc)
                            cx.set_source_surface(ls.emoji_surface(em), 0, 0)
                            cx.paint_with_alpha(a)
                            cx.restore()
                            xx += 46
                        xx += 26
                # the section's bar at the left, bright while it is sung
                cx.set_source_rgba(*shade, (0.95 if cur else 0.45) * a)
                rr(cx, x, top + 6, 7, y - top + 10, 3)
                cx.fill()
                y += 62
        cx.restore()
