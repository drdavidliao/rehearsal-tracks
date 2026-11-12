#!/usr/bin/env python3
"""Cut a scan's pages into one image per system, for scanproof projects and make_map_scan.py's systems.json.

    cut_systems.py PAGES_DIR OUT_DIR "2:2,4,4" "3:4,4,4" ... [--threshold 190]

Each argument is a page number (as in p-N.png) and the staff count of each of its systems, top first. Writes OUT_DIR/sPPx.png
and OUT_DIR/../systems.json with each image's page (from 0), system and the row it was cut from. --threshold is the grey (0-255)
below which a pixel is ink when finding staves, 150 unless given: a faint scan can lose a staff at 150 and keep it at 190.
"""
import glob, json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from scanproof import geom

args = sys.argv[1:]
threshold = 150
if '--threshold' in args:
    k = args.index('--threshold'); threshold = int(args[k + 1]); del args[k:k + 2]
pages_dir, out_dir = args[0], args[1]
os.makedirs(out_dir, exist_ok=True)
pages = sorted(glob.glob(os.path.join(pages_dir, 'p-*.png')), key=lambda f: int(f.rsplit('-', 1)[1][:-4]))
systems = []
for arg in args[2:]:
    pn, counts = arg.split(':'); pn = int(pn); counts = [int(c) for c in counts.split(',')]
    path = next(f for f in pages if int(f.rsplit('-', 1)[1][:-4]) == pn)
    st = geom.staves(geom.Page(path, threshold))
    assert len(st) == sum(counts), f'page {pn}: {len(st)} staves found, {sum(counts)} given'
    tops = [float(np.median(s['samples'][0][1])) for s in st]; bots = [float(np.median(s['samples'][4][1])) for s in st]
    im = Image.open(path); edges = [0]; k = 0
    for c in counts[:-1]:
        k += c; edges.append(int((bots[k - 1] + tops[k]) / 2))
    edges.append(im.height)
    for j in range(len(counts)):
        name = f's{pn:02d}{"abcdefgh"[j]}.png'
        im.crop((0, edges[j], im.width, edges[j + 1])).save(os.path.join(out_dir, name))
        systems.append(dict(file=name, page=pn - 1, sys=j, y0=edges[j], staves=counts[j]))
json.dump(systems, open(os.path.join(out_dir, '..', 'systems.json'), 'w'), indent=1)
print(len(systems), 'systems')
