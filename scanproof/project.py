"""A proofreading project: the config file, the page images, their geometry, the bar table.

The config is JSON; paths in it are relative to the config file.

    {
      "pages": "pages/p-*.png",               # a glob (sorted) or a list, page 1 first
      "score": "../score.txt",                # chorale.scoretext ...
      "musicxml": "piece.musicxml",           # ... or MusicXML (give one of the two)
      "staves": [                             # every system's staves, top to bottom
        {"name": "T", "clef": "G", "xheads": true, "source": ["T"]},
        {"name": "B", "clef": "G", "xheads": true, "source": ["B"]},
        {"name": "R", "clef": "G", "source": ["R"]},
        {"name": "L", "clef": "F", "source": ["L"]}
      ],
      "grand_staff": ["R", "L"],              # optional: the piano's pair
      "key_fifths": -3,                       # key signature (MusicXML: read from the file)
      "beats": 4,                             # quarters in a bar (what M fills)
      "start_space": 7.0,                     # SP after a system's first barline that
      "first_start_space": 11.0,              #   clef + key (+ time, in bar 1) take
      "bars": "bars.json",                    # the bar table (see bars.py)
      "out": "scanproof-out"                  # where geometry, findings, sheets go
    }

`source` names score-text blocks, or for MusicXML {"part": id-or-name, "staff": n}
entries; several sources on one staff are merged (two parts sharing a staff).
Clefs: G, G8 (treble 8vb), F, C3 (alto), C4 (tenor).
"""
import glob
import json
import os

from . import geom

STEPS = 'CDEFGAB'
# diatonic index (step + 7 * octave) of each clef's bottom line
CLEF_BOTTOM = {'G': 2 + 7 * 4, 'G8': 2 + 7 * 3, 'F': 4 + 7 * 2, 'C3': 3 + 7 * 3, 'C4': 1 + 7 * 3}


class Project:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        with open(self.path, encoding='utf-8') as fh:
            self.cfg = json.load(fh)
        c = self.cfg
        pages = c['pages']
        if isinstance(pages, str):
            pages = sorted(glob.glob(self.rel(pages)))
        else:
            pages = [self.rel(p) for p in pages]
        if not pages:
            raise ValueError(f'{path}: no page images match {c["pages"]!r}')
        self.page_paths = pages
        self.staves = c['staves']
        self.names = [s['name'] for s in self.staves]
        for s in self.staves:
            if s.get('clef', 'G') not in CLEF_BOTTOM:
                raise ValueError(f'staff {s["name"]}: unknown clef {s["clef"]!r}')
        g = c.get('grand_staff')
        self.grand = (self.names.index(g[0]), self.names.index(g[1])) if g else None
        self.out = self.rel(c.get('out', 'scanproof-out'))
        os.makedirs(self.out, exist_ok=True)
        self._pages, self._geo = {}, None

    def rel(self, p):
        return p if os.path.isabs(p) else os.path.join(self.dir, p)

    def outfile(self, name):
        return os.path.join(self.out, name)

    # -------------------------------------------------------------- pages
    def page(self, n):
        """Page n, counting from 1."""
        if n not in self._pages:
            self._pages[n] = geom.Page(self.page_paths[n - 1], self.cfg.get('threshold', 150))
        return self._pages[n]

    def npages(self):
        return len(self.page_paths)

    def geometry(self, redo=False):
        """{page: page_geometry}, cached in out/geom.json against the images' mtimes."""
        if self._geo is not None and not redo:
            return self._geo
        path = self.outfile('geom.json')
        stamp = [os.path.getmtime(p) for p in self.page_paths]
        if not redo and os.path.exists(path):
            with open(path) as fh:
                d = json.load(fh)
            if d.get('stamp') == stamp and d.get('staves_per_system') == len(self.staves):
                self._geo = {int(k): v for k, v in d['pages'].items()}
                return self._geo
        geo = {}
        for n in range(1, self.npages() + 1):
            geo[n] = geom.page_geometry(self.page(n), len(self.staves), self.grand,
                                        self.cfg.get('barline_threshold', 228))
        with open(path, 'w') as fh:
            json.dump({'stamp': stamp, 'staves_per_system': len(self.staves),
                       'pages': geo}, fh)
        self._geo = geo
        return geo

    # -------------------------------------------------------------- bars
    def bars(self):
        """{bar: {'page', 'system', 'staves': [staff index per name], 'x0', 'x1',
        'first_in_system', 'start_space'}} from the bar table."""
        from . import bars
        return bars.load(self)

    def staff(self, bar_info, name):
        geo = self.geometry()[bar_info['page']]
        return geo['staves'][bar_info['staves'][self.names.index(name)]]

    def staff_cfg(self, name):
        return self.staves[self.names.index(name)]

    def bottom(self, name):
        return CLEF_BOTTOM[self.staff_cfg(name).get('clef', 'G')]

    def step_name(self, step, name):
        i = step + self.bottom(name)
        return f'{STEPS[i % 7]}{i // 7}'
