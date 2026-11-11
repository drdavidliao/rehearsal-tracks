#!/usr/bin/env python3
"""Draws the app's icon, the score as Dark shows it with the playhead crossing it, and writes AppIcon.icns here. Needs Pillow and macOS's iconutil."""
import os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFilter

S = 4096; K = S / 1024     # drawn large, in 1024ths, then scaled down
def px(*v): return [x * K for x in v]

def icon():
    body = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    grad = Image.linear_gradient('L').resize((S, S))
    top, bottom = (52, 54, 74), (24, 25, 36)
    fill = Image.merge('RGB', [grad.point(lambda g, a=a, b=b: a + (b - a) * g / 255) for a, b in zip(top, bottom)])
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(px(100, 100, 924, 924), 185 * K, fill=255)
    body.paste(fill, (0, 0), mask)
    d = ImageDraw.Draw(body)
    # the staff, a dim blue-grey
    for i in range(5):
        y = 372 + i * 70
        d.rectangle(px(100, y - 6, 924, y + 6), fill=(122, 134, 168, 255))
    # two beamed eighths, in the notes' warm white
    note = (255, 240, 200, 255)
    heads = [(372, 652), (652, 582)]
    for x, y in heads:
        h = Image.new('RGBA', (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(h).ellipse(px(x - 72, y - 50, x + 72, y + 50), fill=note)
        h = h.rotate(22, center=(x * K, y * K), resample=Image.BICUBIC)
        body.alpha_composite(h)
    tops = {372: 305, 652: 245}
    for x, y in heads:
        d.rectangle(px(x + 49, tops[x], x + 69, y - 12), fill=note)
    d.polygon([tuple(px(421, 300)), tuple(px(721, 230)), tuple(px(721, 310)), tuple(px(421, 380))], fill=note)
    # the playhead, with a little glow
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rectangle(px(520, 100, 548, 924), fill=(255, 70, 60, 170))
    glow = glow.filter(ImageFilter.GaussianBlur(22 * K))
    body.alpha_composite(glow)
    ImageDraw.Draw(body).rectangle(px(524, 100, 544, 924), fill=(255, 70, 60, 255))
    # nothing outside the rounded square, then its shadow
    body.putalpha(Image.composite(body.getchannel('A'), Image.new('L', (S, S), 0), mask))
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    shadow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), (0, int(12 * K)), mask)
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14 * K)))
    out.alpha_composite(body)
    return out

here = os.path.dirname(os.path.abspath(__file__))
art = icon()
with tempfile.TemporaryDirectory() as t:
    folder = os.path.join(t, 'AppIcon.iconset'); os.mkdir(folder)
    for size in (16, 32, 128, 256, 512):
        art.resize((size, size), Image.LANCZOS).save(f'{folder}/icon_{size}x{size}.png')
        art.resize((size * 2, size * 2), Image.LANCZOS).save(f'{folder}/icon_{size}x{size}@2x.png')
    subprocess.run(['iconutil', '-c', 'icns', folder, '-o', os.path.join(here, 'AppIcon.icns')], check=True)
