#!/usr/bin/env python3
"""The boxed rehearsal marks in a song's score, found on the page and put on the map's bars, for a score whose MusicXML
has none (a scan's transcription, or one made without them), so the player has a section checkbox for each.

    python3 player/find_boxes.py "song folder"            prints the bars it finds and writes a contact sheet to check
    python3 player/find_boxes.py "song folder" --write    and sets them in player map.json

It renders the map's score at 150 dpi and looks for frames 9-30 pt across with something printed inside, standing just
above a system or inside its top: three sides inked along most of their length, the fourth at least a third (scans break
them), looked for in the ink as printed, with small gaps joined, and with grey counted as ink. A box goes to the bar of
that system whose start is nearest the box's left edge (a mark sits on the barline, or at the start of a system).

tesseract reads each box. One that reads as a word (two or more letters, no digit) is not a mark: text and barlines can
make a frame. The mark is the bar's printed number, as a boxed number is, unless most boxes in the song read as letters,
when it's the letter; it says where what was read isn't the bar's number (usually a misread: 13 as B). The contact sheet
shows each box cropped beside the bar it was given: look at it, and at the pages for any missed, before --write. As in
make_map.py, only a bar's first pass in the map gets the mark. Not found: circled marks, unboxed letters, a box over the
staff lines.
"""
import argparse, json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

DPI = 150
K = DPI / 72


def boxes(png):
    grey = np.asarray(Image.open(png).convert('L'))
    g = grey < 128
    out = []
    # as printed, with gaps of a pixel or two joined (a scanned frame broken in places; joining can also fuse a whole
    # frame to a stem beside it, so both are looked at), and with grey ink as ink (a frame printed light)
    for mask in (g, ndimage.binary_closing(g, np.ones((3, 3))), grey < 200):
        lab, n = ndimage.label(mask)
        for i, sl in enumerate(ndimage.find_objects(lab)):
            h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            if not (9 * K <= w <= 30 * K and 9 * K <= h <= 30 * K and 0.5 <= w / h <= 2): continue
            m = lab[sl] == i + 1
            t = max(2, int(round(1.5 * K)))
            # each side inked along most of its length, at the edge itself or a pixel or two in, by the frame or by ink it
            # touches (a stem its bottom sits on); one side may be broken in the print, if a third of it is there
            e = lambda q: [q[:t].any(0).mean(), q[-t:].any(0).mean(), q[:, :t].any(1).mean(), q[:, -t:].any(1).mean()]
            # (the ink on the same mask, a few pixels past the frame's own edges, where a fused line may lie)
            y0, x0 = max(sl[0].start - 2, 0), max(sl[1].start - 2, 0)
            ink = mask[y0:sl[0].stop + 2, x0:sl[1].stop + 2]
            ink = [max(a, b) for a, b in zip(e(m), e(ink))]
            if sorted(ink)[1] < 0.85 or min(ink) < 0.3: continue  # one side may be broken in the print
            if m[t + 1:-t - 1, t + 1:-t - 1].mean() > 0.3: continue  # mostly a frame (what's inside may touch it)
            inside = g[sl][t + 1:-t - 1, t + 1:-t - 1]
            if inside.mean() < 0.05: continue  # something is printed inside
            r = (sl[1].start / K, sl[0].start / K, sl[1].stop / K, sl[0].stop / K)
            if not any(abs(r[0] - o[0]) < 4 and abs(r[1] - o[1]) < 4 for o in out): out.append(r)
    return out


def read(crop):
    """what tesseract reads in the box ('' if nothing)"""
    big = crop.convert('L').resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
    b = Image.new('L', (big.width + 40, big.height + 40), 255); b.paste(big, (20, 20))
    p = tempfile.mktemp(suffix='.png'); b.save(p)
    r = subprocess.run(['tesseract', p, '-', '--psm', '7', '-c',
                        'tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'], capture_output=True, text=True)
    os.remove(p)
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder'); ap.add_argument('--write', action='store_true')
    ap.add_argument('--sheet', help='contact sheet path (default: the scratch folder)')
    a = ap.parse_args()
    mp = os.path.join(a.folder, 'player map.json')
    m = json.load(open(mp))
    tmp = tempfile.mkdtemp()
    subprocess.run(['pdftoppm', '-r', str(DPI), '-png', os.path.join(a.folder, m['score']), os.path.join(tmp, 'p')], check=True)
    pages = sorted(f for f in os.listdir(tmp) if f.endswith('.png'))
    found, crops = {}, []
    for pi, f in enumerate(pages):
        systems = [s for s in m['systems'] if s['page'] == pi]
        for x0, y0, x1, y1 in boxes(os.path.join(tmp, f)):
            # the system the box stands over: its bottom from 45 pt above the top to 15 pt inside it
            near = [s for s in systems if s['top'] - 45 <= y1 <= s['top'] + 15]
            if not near: continue
            s = min(near, key=lambda s: abs(y1 - s['top']))
            cx = (x0 + x1) / 2
            bars = [b for b in m['bars'] if b['page'] == pi and b['sys'] == s['sys'] and b['xa'] - 25 <= cx < b['xb'] + 25]
            if not bars: continue
            num = min(bars, key=lambda b: abs(b['xa'] - x0))['num']
            im = Image.open(os.path.join(tmp, f)).convert('RGB')
            text = read(im.crop((int(x0 * K) + 3, int(y0 * K) + 3, int(x1 * K) - 3, int(y1 * K) - 3)))
            if text and not (len(text) == 1 or any(c.isdigit() for c in text)):
                print(f'  bar {num}: not a mark, it reads {text!r}'); continue  # words and barlines that look like a box
            if text and text != str(num): print(f'  bar {num}: the box reads {text!r}')
            found[num] = text
            crops.append((num, im.crop((int((x0 - 20) * K), int((y0 - 8) * K), int((x1 + 60) * K), int((y1 + 8) * K)))))
    # letters as printed if most boxes read as letters; otherwise each bar's number, since a boxed number is the bar's and
    # what's read can drop or misread a digit (13 as B)
    letters = sum(t.isalpha() for t in found.values()) > len(found) / 2
    found = {n: t if letters and t.isalpha() else str(n) for n, t in found.items()}
    print(os.path.basename(a.folder.rstrip('/')) + ':', [found[n] for n in sorted(found)])
    if crops:
        W = max(c.width for _, c in crops) + 70
        sheet = Image.new('RGB', (W, sum(c.height + 6 for _, c in crops)), 'white')
        y = 0
        d = ImageDraw.Draw(sheet)
        for num, c in sorted(crops, key=lambda c: c[0]):
            sheet.paste(c, (70, y)); d.text((4, y + c.height // 2 - 6), f'bar {num}', fill='red'); y += c.height + 6
        path = a.sheet or os.path.join(os.environ.get('SHEETS', tmp), os.path.basename(a.folder.rstrip('/')) + ' boxes.png')
        sheet.save(path); print('contact sheet:', path)
    if a.write:
        seen = set()
        for b in m['bars']:
            if b['num'] in seen: b['letter'] = None
            else: b['letter'] = found.get(b['num'])
            seen.add(b['num'])
        json.dump(m, open(mp, 'w'), indent=0)
        print('wrote', mp)


if __name__ == '__main__':
    main()
