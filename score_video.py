#!/usr/bin/env python3
"""Follow-along score videos from a MusicXML and the rehearsal mp3s made from it (SKILL.md Step 10).

    python3 score_video.py score.musicxml "Shenandoah - Balanced.mp3" \
        "Shenandoah - (Tenor 1) predominant.mp3" "Shenandoah - (Tenor 2) predominant.mp3" ...
        [--display print.musicxml] [-o OUT_DIR] [--part "Tenor 1=Tenor"]
        [--staves "Tenor 1+Tenor 2,Baritone+Bass" | --open] [--pulse 8] [--dark]
        [--clip START,SECONDS] [--stills T1,T2,...] [--staff-px 44] [--fps 30] [--warp]

The MusicXML is the one the audio was rendered from (one part per staff, as Sibelius and
Cantai sing it). When that is a Cantai learning file, give the print-faithful file as
--display: it is shown instead (normal words, slurs and ties), after a check that it has
the same parts, bars, notes and tempo marks. Each mp3 gives one mp4 of the same name
beside it (or in OUT_DIR):

  a Balanced mp3          -> every sung part lights up in its own colour
  "(Part) predominant", "(Part) part-left", "Solo ... " mp3s
                          -> only that part lights up; every other part, piano too, is grey,
                             and that part's staff is never hidden, so its rests stay on screen

A note lights (its colour, and a soft halo) while it sounds; its syllable stays lit from its
note until the next syllable or rest, so a melisma or a tie keeps its word lit. A note or
word two parts share gets a halo split in both colours. A rest lights the same way, and a
bar under it (above the staff for the upper of two voices) runs from where the rest starts
to where it ends as the other staves print that time, filling in jumps of one pulse: each
part's pulse is the coarsest note value that 95% of the bars it sings keep to (eighths in a
piece of eighths with one bar of sixteenths; --pulse sets it). Each jump lands where the
other staves print that time, so the fill meets the piano's notes as they sound and a
singer who cannot count rests sees the beats go by. Pages turn up to a second before the
next page's first note, never before the last note on the old page has begun. Staves empty
for a whole system are hidden, as in a printed score. Black on white by default; --dark for
light notation on a dark screen.

Closed score by default: the sung parts are paired two to a staff, as the singers hold
them (consecutive sung parts in score order, soloists left on their own staff; --staves
names the pairs, --open keeps one part per staff). A bar where the two parts share rhythm,
ties and words becomes chords with one lyric line; elsewhere the upper part is voice 1
(stems up), the lower voice 2 (stems down), and the lower part gets its own lyric line
only where its words differ (SKILL.md 7.2 and 7.4). A tie never changes voice: a merged
bar tied to a divided one is divided too. Crossed parts are never chorded (7.6).
Accompaniment staves are shown as written.

Timing, as stem_vs_score.py does it: beats become seconds with the score's tempo marks,
and the line-up is anchored where the audio first sounds against where the score first
has a note; only the tempo is refined, on note onsets found in the audio. Then the drift
is measured: every score onset against the nearest onset in the audio, reported as a
median per stretch of the piece, so a ritardando or fermata that playback stretches
shows up as the bar where the lights start to lag. --warp follows such drift with a
piecewise line through the measured stretches instead of a single straight line. After
each mp4 is written, its own audio is checked against the mp3 (an offset would shift
everything) and sync is measured on the finished file: when each light comes on in the
picture against the nearest onset in the file's audio.

Needs verovio, cairosvg, lxml, numpy, pillow, fonttools and brotli (the Leipzig font fix,
8.4) and ffmpeg with libx264; stem_vs_score.py beside it. Repeats are not expanded (the
same limit as stem_vs_score.py). A 4:48 piece at 1920x1080 takes a few minutes per video.
"""
import sys, os, io, re, copy, math, argparse, subprocess, zipfile
from fractions import Fraction as Fr
import numpy as np
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stem_vs_score import load_score, beats_to_sec, envelope, runs  # noqa: E402

# Okabe-Ito, colour-blind safe; neighbours on a shared staff get well-separated hues
PALETTE = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#B07A00', '#7F3C8D', '#00798C', '#8C510A']
GREY = '#B4B4B4'
# dark mode, the default: for backlit screens, not paper. Bright hues that keep apart on a dark
# ground; the same order (the four parts sharing staves first)
PALETTE_DARK = ['#56B4E9', '#FF9F43', '#4CD98A', '#F48FD0', '#F0E442', '#B39DFF', '#45D6D0', '#E8B070']
THEME = {}


def set_theme(dark):
    """Light (black on white, like the printed page) by default; --dark for a backlit screen."""
    if dark:
        THEME.update(dark=True, bg=np.array([28, 28, 30], np.float32), ink=np.array([225, 225, 225], np.float32),
                     grey='#8C8C8C', tint=0.5, lift=0.35)
    else:
        THEME.update(dark=False, bg=np.array([255, 255, 255], np.float32),
                     ink=np.array([0, 0, 0], np.float32), grey=GREY, tint=0.30, lift=0.0)


set_theme(False)
STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
NOTE_ORDER = ['grace', 'cue', 'chord', 'pitch', 'unpitched', 'rest', 'duration', 'tie', 'instrument',
              'footnote', 'level', 'voice', 'type', 'dot', 'accidental', 'time-modification', 'stem',
              'notehead', 'notehead-text', 'staff', 'beam', 'notations', 'lyric', 'play', 'listen']


# ----------------------------------------------------------------------------- reading the score

def read_xml(path):
    if path.lower().endswith('.mxl'):
        z = zipfile.ZipFile(path)
        cont = etree.fromstring(z.read('META-INF/container.xml'))
        full = cont.find('.//{*}rootfile').get('full-path')
        return etree.fromstring(z.read(full))
    return etree.parse(path, etree.XMLParser(remove_blank_text=True, recover=True)).getroot()


def hexrgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32)


def midi(note):
    p = note.find('pitch')
    if p is None:
        return None
    return 12 * (int(p.findtext('octave')) + 1) + STEP[p.findtext('step')] + int(float(p.findtext('alter') or 0))


def lyric1(note):
    """The first lyric line's (syllabic, text), or None."""
    ls = note.findall('lyric')
    if not ls:
        return None
    ls.sort(key=lambda l: int(re.sub(r'\D', '', l.get('number') or '1') or 1))
    t = ''.join(x.text or '' for x in ls[0].findall('text'))
    return (ls[0].findtext('syllabic') or 'single', t) if t.strip() else None


def ties(note):
    ts = [t.get('type') for t in note.findall('tie')] + [t.get('type') for t in note.iter('tied')]
    return 'start' in ts, 'stop' in ts


def scan_part(pi, part):
    """Assign an id to every note and return (notes, measure starts, measure lengths) in quarters."""
    div, pos, notes, starts, k = 1, Fr(0), [], [], 0
    for mi, m in enumerate(part.findall('measure')):
        starts.append(pos)
        t, mx, last_on = pos, pos, pos
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= Fr(int(e.findtext('duration')), div)
            elif e.tag == 'forward':
                t += Fr(int(e.findtext('duration')), div)
            elif e.tag == 'note':
                nid = f'n{pi}x{k}'
                k += 1
                e.set('id', nid)
                grace = e.find('grace') is not None
                chord = e.find('chord') is not None
                d = Fr(0) if grace else Fr(int(e.findtext('duration') or 0), div)
                on = last_on if chord else t
                ts, tp = ties(e)
                notes.append(dict(id=nid, part=pi, mi=mi, el=e, on=on, dur=d, rel=on - pos,
                                  voice=e.findtext('voice') or '1', rest=e.find('rest') is not None,
                                  chord=chord, grace=grace, midi=midi(e), tie_start=ts, tie_stop=tp,
                                  lyric=lyric1(e), type=e.findtext('type'), dots=len(e.findall('dot')),
                                  tmod=e.find('time-modification') is not None))
                if not chord:
                    last_on = t
                    t += d
            mx = max(mx, t)
        pos = mx
    return notes, starts


def syllable_windows(notes):
    """Per sung note with a syllable: (start, end) in quarters, the end running on through the
    following syllable-less notes (a melisma or a tie) and stopping at a rest or the next syllable."""
    seq = [n for n in notes if not n['chord'] and not n['grace'] and n['voice'] == '1']
    out, cur = {}, None
    for n in seq:
        if n['rest']:
            cur = None
        elif n['lyric']:
            cur = n['id']
            out[cur] = [n['on'], n['on'] + n['dur']]
        elif cur:
            out[cur][1] = n['on'] + n['dur']
    return out


# ----------------------------------------------------------------------------- closed score

def lcm(a, b):
    return a * b // math.gcd(a, b)


def normalise_divisions(part, D):
    div = 1
    for m in part.findall('measure'):
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
                e.find('divisions').text = str(D)
            for d in ([e.find('duration')] if e.tag in ('note', 'backup', 'forward') else []) + \
                     ([e.find('offset')] if e.tag in ('direction', 'harmony') else []):
                if d is not None and d.text:
                    d.text = str(int(Fr(int(float(d.text)) * D, div)))


def set_child(note, tag, text):
    old = note.find(tag)
    if old is not None:
        old.text = text
        return
    new = etree.Element(tag)
    new.text = text
    idx = NOTE_ORDER.index(tag)
    at = len(note)
    for i, c in enumerate(note):
        if c.tag in NOTE_ORDER and NOTE_ORDER.index(c.tag) > idx:
            at = i
            break
    note.insert(at, new)


def strip(note, *tags):
    for t in tags:
        for c in note.findall(t):
            note.remove(c)


def bar_events(notes, mi):
    return [n for n in notes if n['mi'] == mi]


def mergeable(eu, el):
    if len(eu) != len(el) or not eu:
        return False
    for a, b in zip(eu, el):
        if a['chord'] or b['chord'] or a['grace'] or b['grace'] or a['voice'] != '1' or b['voice'] != '1':
            return False
        for k in ('rel', 'dur', 'rest', 'type', 'dots', 'tie_start', 'tie_stop', 'lyric', 'tmod'):
            if a[k] != b[k]:
                return False
        if not a['rest'] and (a['midi'] is None or b['midi'] is None or b['midi'] > a['midi']):
            return False          # crossed parts are never chorded (SKILL.md 7.6)
    return True


def build_pair(up, lo, nu, nl, pid, name, abbr, owners, syl_holder):
    """Write parts `up` and `lo` onto one staff; return the new <part>.
    owners[note id] -> set of part indices sounding that notehead;
    syl_holder[(part, note id)] -> note id whose printed syllable that part reads."""
    D = 1
    for p in (up, lo):
        for d in p.iter('divisions'):
            D = lcm(D, int(d.text))
    normalise_divisions(up, D)
    normalise_divisions(lo, D)
    mu, ml = up.findall('measure'), lo.findall('measure')
    lo_el = {e.get('id'): e for e in lo.iter('note')}
    if len(mu) != len(ml):
        sys.exit(f'{name}: the two parts have {len(mu)} and {len(ml)} bars; cannot share a staff')
    pu, pl = nu[0]['part'] if nu else None, nl[0]['part'] if nl else None
    ev = [(bar_events(nu, i), bar_events(nl, i)) for i in range(len(mu))]
    merged = [mergeable(a, b) for a, b in ev]
    changed = True
    while changed:                            # a tie never changes voice
        changed = False
        for i, (a, b) in enumerate(ev):
            if not merged[i]:
                continue
            firsts = [x[0] for x in (a, b) if x]
            lasts = [x[-1] for x in (a, b) if x]
            if (i > 0 and not merged[i - 1] and any(n['tie_stop'] for n in firsts)) or \
               (i + 1 < len(ev) and not merged[i + 1] and any(n['tie_start'] for n in lasts)):
                merged[i] = False
                changed = True
    part = etree.Element('part', id=pid)
    lo_clef = None
    for i, (mU, mL) in enumerate(zip(mu, ml)):
        a, b = ev[i]
        m = etree.SubElement(part, 'measure', {k: v for k, v in mU.attrib.items() if k != 'width'})
        la = mL.find('attributes')
        if la is not None and la.find('clef') is not None:
            lo_clef = copy.deepcopy(la.find('clef'))
            lo_clef.attrib.pop('number', None)
        clef_due = la is not None and la.find('clef') is not None
        sa = [(n['lyric']) for n in a if n['lyric']]
        sb = [(n['lyric']) for n in b if n['lyric']]
        same_words = sa == sb
        # which printed syllable each part reads in this bar
        ha = [n['id'] for n in a if n['lyric']]
        hb = [n['id'] for n in b if n['lyric']]
        for h in ha:
            syl_holder[(pu, h)] = h
        if merged[i] or same_words:
            for x, y in zip(ha, hb):
                syl_holder[(pl, y)] = x
        else:
            for y in hb:
                syl_holder[(pl, y)] = y
        partner = {x['id']: y for x, y in zip(a, b)} if merged[i] else {}
        t = Fr(0)
        placed_clef = False
        for e in mU:
            if e.tag == 'print':
                continue
            c = copy.deepcopy(e)
            if e.tag == 'attributes':
                for cl in c.findall('clef'):
                    c.remove(cl)
                if clef_due and lo_clef is not None and not placed_clef:
                    idx = len(c)
                    for j, ch in enumerate(c):
                        if ch.tag in ('staff-details', 'transpose', 'directive', 'measure-style', 'for-part'):
                            idx = j
                            break
                    c.insert(idx, copy.deepcopy(lo_clef))
                    placed_clef = True
                m.append(c)
                continue
            if e.tag != 'note':
                if e.tag in ('backup', 'forward'):
                    q = int(e.findtext('duration'))
                    t += q if e.tag == 'forward' else -q
                m.append(c)
                continue
            if c.find('chord') is None and c.find('grace') is None:
                t += int(c.findtext('duration') or 0)
            n_id = c.get('id')
            owners.setdefault(n_id, set()).add(pu)
            if merged[i]:
                set_child(c, 'voice', '1')
                m.append(c)
                y = partner.get(n_id)
                if y is not None and not y['rest']:
                    if y['midi'] == midi(e):
                        owners[n_id].add(pl)                    # unison: one notehead, both parts
                    else:
                        lc = copy.deepcopy(lo_el[y['id']])
                        strip(lc, 'lyric', 'beam', 'stem')
                        nots = lc.find('notations')
                        if nots is not None:
                            for ch in list(nots):
                                if ch.tag != 'tied':
                                    nots.remove(ch)
                        lc.insert(0, etree.Element('chord'))
                        set_child(lc, 'voice', '1')
                        m.append(lc)
                        owners.setdefault(lc.get('id'), set()).add(pl)
                elif y is not None:
                    owners[n_id].add(pl)                        # the shared rest
            else:
                set_child(c, 'voice', str(2 * int(c.findtext('voice') or 1) - 1))
                if c.find('rest') is None:
                    set_child(c, 'stem', 'up')
                m.append(c)
        if clef_due and lo_clef is not None and not placed_clef:
            at = etree.Element('attributes')
            at.append(copy.deepcopy(lo_clef))
            m.insert(0, at)
        if merged[i]:
            continue
        if t:
            bk = etree.SubElement(m, 'backup')
            etree.SubElement(bk, 'duration').text = str(t)
        for e in mL:
            if e.tag not in ('note', 'backup', 'forward'):
                continue
            c = copy.deepcopy(e)
            if e.tag == 'note':
                owners.setdefault(c.get('id'), set()).add(pl)
                set_child(c, 'voice', str(2 * int(c.findtext('voice') or 1)))
                if c.find('rest') is None:
                    set_child(c, 'stem', 'down')
                lys = c.findall('lyric')
                for j, ly in enumerate(sorted(lys, key=lambda l: int(re.sub(r'\D', '', l.get('number') or '1') or 1))):
                    if same_words or j > 0:
                        c.remove(ly)
                    else:
                        ly.set('number', '2')
                        ly.attrib.pop('placement', None)
                        ly.attrib.pop('default-y', None)
            m.append(c)
    return part, sum(merged), len(merged)


def default_pairs(names, sung):
    order = [i for i in range(len(names)) if i in sung and not names[i].lower().startswith('solo')]
    return [tuple(order[k:k + 2]) for k in range(0, len(order) - 1, 2)]


def display_score(root, parts, notes_by_part, pairs, sung):
    """Return (display root, owners, syl_holder, staff names)."""
    owners, syl_holder = {}, {}
    pl = root.find('part-list')
    sps = {sp.get('id'): sp for sp in pl.findall('score-part')}
    names = [(sps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in parts]
    abbrs = [(sps[p.get('id')].findtext('part-abbreviation') or '').strip() for p in parts]
    pair_of = {}
    for a, b in pairs:
        pair_of[a] = (a, b)
        pair_of[b] = None
    out = etree.Element('score-partwise', version='4.0')
    new_pl = etree.SubElement(out, 'part-list')
    for i, p in enumerate(parts):
        if i in pair_of and pair_of[i] is None:
            continue
        if i in pair_of:
            a, b = pair_of[i]
            pid = f'PX{a}'
            nm = f'{names[a]}\n{names[b]}'
            ab = f'{abbrs[a] or names[a]}\n{abbrs[b] or names[b]}'
            newp, nmerged, nbars = build_pair(copy.deepcopy(parts[a]), copy.deepcopy(parts[b]),
                                              notes_by_part[a], notes_by_part[b], pid, nm, ab, owners, syl_holder)
            # the copies carry the ids given by scan_part, and the notes' 'el' point at the originals;
            # re-link merged chord partners' ids is not needed: ids are attributes, copied verbatim
            print(f'   staff "{names[a]} + {names[b]}": {nmerged} of {nbars} bars as chords, the rest divided')
            sp = etree.SubElement(new_pl, 'score-part', id=pid)
            etree.SubElement(sp, 'part-name').text = nm
            etree.SubElement(sp, 'part-abbreviation').text = ab
            out.append(newp)
        else:
            sp = copy.deepcopy(sps[p.get('id')])
            new_pl.append(sp)
            c = copy.deepcopy(p)
            for pr in c.iter('print'):
                pr.getparent().remove(pr)
            out.append(c)
            if i in sung:
                for n in notes_by_part[i]:
                    owners.setdefault(n['id'], set()).add(i)
                    if n['lyric']:
                        syl_holder[(i, n['id'])] = n['id']
    return out, owners, syl_holder


# ----------------------------------------------------------------------------- audio and timing

def decode(path, sr=22050):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ac', '1', '-ar', str(sr),
                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def audio_onsets(x, sr=22050, n=1024, hop=128):
    """Spectral-flux onsets (seconds)."""
    win = np.hanning(n).astype(np.float32)
    nfr = 1 + max(0, (len(x) - n) // hop)
    prev, flux = None, np.zeros(nfr, np.float32)
    for c0 in range(0, nfr, 4096):
        c1 = min(nfr, c0 + 4096)
        idx = np.arange(c0, c1)[:, None] * hop + np.arange(n)[None, :]
        L = np.log1p(100 * np.abs(np.fft.rfft(x[idx] * win, axis=1))).astype(np.float32)
        if prev is not None:
            L = np.vstack([prev[None], L])
            d = np.maximum(0, np.diff(L, axis=0)).sum(1)
            flux[c0:c1] = d
        else:
            d = np.maximum(0, np.diff(L, axis=0)).sum(1)
            flux[c0 + 1:c1] = d
        prev = L[-1]
    k = int(0.4 * sr / hop)
    pad = np.pad(flux, k, mode='edge')
    from numpy.lib.stride_tricks import sliding_window_view
    med = np.median(sliding_window_view(pad, 2 * k + 1), axis=1)[:nfr]
    thr = med + 0.25 * np.percentile(flux, 95)
    w = 4
    padm = np.pad(flux, w, mode='constant')
    mx = sliding_window_view(padm, 2 * w + 1).max(1)[:nfr]
    peaks = np.flatnonzero((flux >= mx) & (flux > thr))
    t = (peaks * hop + n / 2) / sr
    keep, last = [], -1
    for v in t:
        if v - last > 0.05:
            keep.append(v)
            last = v
    return np.array(keep)


class Timing:
    def __init__(self, score_path, mp3, score_onsets, first_score, warp=False, seg=12.0):
        self.x = decode(mp3)
        self.dur = len(self.x) / 22050
        env = envelope(mp3, -50.0)
        sounding = [r for r in runs(env) if r[1] - r[0] >= 0.3]
        if not sounding:
            sys.exit(f'{mp3}: no sound above -50 dBFS')
        self.first_audio = sounding[0][0]
        self.off = self.first_audio - first_score           # anchored at the first entrance
        self.aon = audio_onsets(self.x)
        so = np.array(sorted(set(round(s, 3) for s in score_onsets)))
        self.so = so
        scale = 1.0
        for win in (0.5, 0.3, 0.15):                         # refine the tempo only; the anchor stays put
            g = self.off + scale * so
            k = np.clip(np.searchsorted(self.aon, g), 1, len(self.aon) - 1)
            near = np.where(np.abs(self.aon[k - 1] - g) < np.abs(self.aon[k] - g), self.aon[k - 1], self.aon[k])
            ok = np.abs(near - g) < win
            if ok.sum() >= 8:
                X, Y = so[ok], near[ok] - self.off
                scale = float(np.clip(np.dot(X, Y) / max(np.dot(X, X), 1e-9), 0.9, 1.1))
        self.scale = scale
        self.knots = None
        self.residuals = self.measure()
        if warp:
            self.fit_warp(seg)
            self.residuals_warped = self.measure()

    def straight(self, s):
        return self.off + self.scale * np.asarray(s, float)

    def __call__(self, s):
        if self.knots is None:
            return self.straight(s)
        ks, kd = self.knots
        return self.straight(s) + np.interp(np.asarray(s, float), ks, kd)

    def measure(self, win=0.35):
        g = self(self.so)
        k = np.clip(np.searchsorted(self.aon, g), 1, len(self.aon) - 1)
        near = np.where(np.abs(self.aon[k - 1] - g) < np.abs(self.aon[k] - g), self.aon[k - 1], self.aon[k])
        r = near - g
        ok = np.abs(r) < win
        return g[ok], r[ok], len(g)

    def fit_warp(self, seg):
        g, r, _ = self.residuals
        s = (g - self.off) / self.scale
        edges = np.arange(0, s.max() + seg, seg)
        ks, kd = [], []
        for a, b in zip(edges[:-1], edges[1:]):
            sel = (s >= a) & (s < b)
            if sel.sum() >= 6:
                ks.append((a + b) / 2)
                kd.append(float(np.median(r[sel])))
        if ks:
            self.knots = (np.array(ks), np.array(kd))

    def report(self, bar_at, label, seg=15.0):
        fmt = lambda t: f'{int(t // 60)}:{t % 60:04.1f}'
        print(f'\n{label}')
        print(f'   anchor: audio first sounds at {fmt(self.first_audio)}; audio = {self.off:+.3f} s + '
              f'{self.scale:.4f} x score time')
        for tag, res in (('straight line', self.residuals),) + \
                        ((('warped', self.residuals_warped),) if self.knots is not None else ()):
            g, r, n = res
            if not len(r):
                print(f'   {tag}: no audio onsets near the score onsets; drift not measured')
                continue
            print(f'   drift, {tag}: {len(r)} of {n} score onsets matched an audio onset within 0.35 s; '
                  f'median {1000 * np.median(r):+.0f} ms, median |error| {1000 * np.median(np.abs(r)):.0f} ms, '
                  f'90th percentile |error| {1000 * np.percentile(np.abs(r), 90):.0f} ms')
            rows = []
            for a in np.arange(0, g.max() + seg, seg):
                sel = (g >= a) & (g < a + seg)
                if sel.sum() >= 4:
                    rows.append((a, int(sel.sum()), float(np.median(r[sel]))))
            print('   ' + '  '.join(f'{fmt(a)} bar {bar_at(a)}: {1000 * m:+.0f} ms' for a, _, m in rows))
            worst = max(rows, key=lambda x: abs(x[2])) if rows else None
            if worst and abs(worst[2]) > 0.12:
                print(f'   <- lights and audio part by {1000 * worst[2]:+.0f} ms around {fmt(worst[0])} '
                      f'(bar {bar_at(worst[0])}); positive = the audio is later than the lights'
                      + ('' if self.knots is not None else '; --warp follows it'))


# ----------------------------------------------------------------------------- rendering

def install_smufl_font():
    """cairosvg ignores @font-face, so Verovio's text glyphs (the note in a metronome mark,
    chord-symbol accidentals) print as boxes unless Leipzig is installed for fontconfig
    (SKILL.md 8.4). Needs fonttools and brotli; without them the boxes stay."""
    import verovio, base64
    dest = os.path.expanduser('~/.fonts/Leipzig.ttf')
    if os.path.exists(dest):
        return
    try:
        from fontTools.ttLib import TTFont
        css = open(os.path.join(os.path.dirname(verovio.__file__), 'data', 'Leipzig.css')).read()
        f = TTFont(io.BytesIO(base64.b64decode(re.search(r'base64,([A-Za-z0-9+/=]+)', css).group(1))))
        f.flavor = None
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        subprocess.run(['fc-cache', '-f'], check=False, capture_output=True)
    except Exception as e:                                   # a box in a tempo mark is not fatal
        print(f'note: could not install the Leipzig font ({e}); metronome marks may show a box')


def render_png(svg_bytes, W, H):
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=svg_bytes, output_width=W, output_height=H, background_color='white')
    return np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))


class Page:
    """One rendered page: base images per view, and every lightable element's pixels."""

    def __init__(self, svg, W, H, owners, syl_holder, colours, views, names, label_px, times, bar_end):
        self.W, self.H, self.names, self.label_px = W, H, names, label_px
        root = etree.fromstring(svg.encode())
        ns = '{http://www.w3.org/2000/svg}'
        self.root = root
        cls = lambda e: (e.get('class') or '').split()
        # SVG drawing units -> pixels, for noteheads placed straight from the SVG
        inner = root.find(ns + 'svg')
        vb = [float(v) for v in inner.get('viewBox').split()]
        kx, ky = W / vb[2], H / vb[3]
        pm = next(g for g in inner.iter(ns + 'g') if 'page-margin' in cls(g))
        mx, my = (float(v) for v in re.findall(r'-?[\d.]+', pm.get('transform'))[:2])
        notes, syls, rests = [], [], []
        for g in root.iter(ns + 'g'):
            c = cls(g)
            if 'note' in c and g.get('id') in owners:
                notes.append(g)
            elif ('rest' in c or 'mRest' in c) and g.get('id') in owners:
                rests.append(g)
            elif 'syl' in c:
                syls.append(g)
        # elements: (kind, key, g); heads get their own entry for the halo
        self.elems = []
        self.heads = {}
        space = 180.0                     # a staff space in drawing units (Verovio's unit 9, x10)
        self.space_px = space * ky
        widths = {'E0A0': 2.0, 'E0A2': 1.69, 'E0A3': 1.18, 'E0A4': 1.18}
        for g in notes:
            head = next((h for h in g if 'notehead' in cls(h)), None)
            self.elems.append(('body', g.get('id'), g))
            if head is not None:
                self.elems.append(('head', g.get('id'), head))
                use = head.find(ns + 'use')
                if use is not None and use.get('transform'):
                    tx, ty = (float(v) for v in re.findall(r'-?[\d.]+', use.get('transform'))[:2])
                    href = use.get('{http://www.w3.org/1999/xlink}href') or ''
                    sc = float((re.findall(r'scale\(([\d.]+)', use.get('transform')) or ['0.72'])[0]) / 0.72
                    w = widths.get(href[1:5], 1.18) * space * sc
                    self.heads[g.get('id')] = ((tx + mx + w / 2) * kx, (ty + my) * ky,
                                               w / 2 * kx, space * sc / 2 * ky)
        for g in rests:
            self.elems.append(('rest', g.get('id'), g))
        for s in syls:
            a = s.getparent()
            while a is not None and not ({'note', 'chord'} & set(cls(a))):
                a = a.getparent()
            if a is None:
                continue
            ids = [a.get('id')] if 'note' in cls(a) else [n.get('id') for n in a.iter(ns + 'g') if 'note' in cls(n)]
            holder = next((i for i in ids if i in _SYL_INDEX), None)
            if holder is None:
                continue
            self.elems.append(('syl', holder, s))
        self.ids_on_page = {g.get('id') for g in root.iter(ns + 'g')
                            if {'note', 'rest', 'mRest'} & set(cls(g)) and g.get('id')}
        # score time -> x on each system, from every note and rest printed on it (any staff) and
        # its barlines: a rest's progress bar runs across what the other staves play meanwhile
        first_x = lambda e: next((float(re.findall(r'-?[\d.]+', u.get('transform'))[0])
                                  for u in e.iter(ns + 'use') if u.get('transform')), None)
        self.timemap, self.rest_bar = [], {}
        for si, sysg in enumerate(g for g in root.iter(ns + 'g') if 'system' in cls(g)):
            pts = []
            for m in (g for g in sysg.iter(ns + 'g') if 'measure' in cls(g)):
                mend = None
                for e in m.iter(ns + 'g'):
                    c, i = set(cls(e)), e.get('id')
                    if i not in bar_end or not ({'note', 'rest', 'mRest'} & c):
                        continue
                    mend = bar_end.get(i, mend)
                    if c & {'note', 'rest'} and i in times:
                        x = first_x(e)
                        if x is not None:
                            pts.append((times[i], (x + mx) * kx))
                bl = next((b for b in m if 'barLine' in cls(b)), None)
                d = bl.find(ns + 'path') if bl is not None else None
                if mend is not None and d is not None:
                    pts.append((mend, (float(re.findall(r'-?[\d.]+', d.get('d'))[0]) + mx) * kx))
            first = {}
            for t_, x_ in pts:                   # one x per time: the leftmost (a barline before
                first[round(t_, 4)] = min(x_, first.get(round(t_, 4), x_))   # the next bar's downbeat)
            ts = np.array(sorted(first)) if first else np.zeros(1)
            xs = np.maximum.accumulate(np.array([first[t_] for t_ in sorted(first)])) if first else np.zeros(1)
            self.timemap.append((ts, xs))
            # where each rest's bar goes: under its staff, or above it for the upper of two voices
            for st in (g for g in sysg.iter(ns + 'g') if 'staff' in cls(g)):
                ys = [float(v) for pth in st.findall(ns + 'path') for v in re.findall(r'-?[\d.]+', pth.get('d'))[1::2]]
                if not ys:
                    continue
                top, bot = (min(ys) + my) * ky, (max(ys) + my) * ky
                layers = [l for l in st if 'layer' in cls(l)]
                for li, l in enumerate(layers):
                    for e in l.iter(ns + 'g'):
                        if e.get('id') in owners and {'rest', 'mRest'} & set(cls(e)):
                            above = len(layers) > 1 and li == 0
                            self.rest_bar[e.get('id')] = (si, above, top, bot)
        # noteheads drawn on the same spot are one lit note: its ink is whatever is drawn
        # inside the notehead, and it lights in every colour singing it
        spots = {}
        for nid, (cx, cy, rx, ry) in self.heads.items():
            spots.setdefault((round(cx), round(cy)), []).append(nid)
        self.alias = {}
        self.spots = [ids for ids in spots.values() if len(ids) > 1]
        for ids in self.spots:
            for i in ids:
                self.alias[i] = ids[0]
        self.args = (owners, syl_holder, colours, views)
        self.ready = False

    def raster(self):
        """Render the ownership planes and the base images (slow; done only for screens shown)."""
        if self.ready:
            return
        owners, syl_holder, colours, views = self.args
        W, H, root = self.W, self.H, self.root
        # ownership planes
        n = len(self.elems)
        K = max(1, int(math.ceil(math.log2(n + 2))))
        top = root
        def plane(bits, invert=False):
            top.set('visibility', 'hidden')
            for j, (_, _, g) in enumerate(self.elems):
                on = bits is None or bool(((j + 1) >> bits) & 1) != invert
                g.set('visibility', 'visible' if on else 'hidden')
                g.set('fill', '#000000')
                g.set('color', '#000000')
            img = render_png(etree.tostring(root), W, H)
            for _, _, g in self.elems:
                for a in ('visibility', 'fill', 'color'):
                    g.attrib.pop(a, None)
            top.attrib.pop('visibility', None)
            return 1.0 - img[..., 0].astype(np.float32) / 255.0
        au = plane(None)
        owner = np.zeros(au.shape, np.int32)
        unsure = au <= 0.06
        for k in range(K):
            r = plane(k) / np.maximum(au, 1e-6)
            ri = plane(k, invert=True) / np.maximum(au, 1e-6)
            owner |= (r > 0.5).astype(np.int32) << k
            # where two pieces overlap (antialiased edges, or two noteheads drawn on the same
            # spot: a unison between the voices of a divided bar) the bits of both would OR
            # into some third piece's id; such a pixel belongs to neither
            unsure |= ((r > 0.2) & (r < 0.8)) | ((r > 0.5) & (ri > 0.5))
        owner[unsure] = 0
        flat = owner.ravel()
        order = np.argsort(flat, kind='stable')
        sorted_ids = flat[order]
        bounds = np.searchsorted(sorted_ids, np.arange(n + 2))
        self.alpha = au.ravel()
        self.pix = [order[bounds[j + 1]:bounds[j + 2]] for j in range(n)]
        self.shared_ink = {}
        for ids in self.spots:
            cx, cy, rx, ry = self.heads[ids[0]]
            y0, y1 = int(max(0, cy - ry)), int(min(H - 1, cy + ry))
            x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.1
            cand = (yy[inside] * W + xx[inside]).ravel()
            self.shared_ink[ids[0]] = cand[self.alpha[cand] > 0.06]
        # base images per view
        self.base = {}
        for v in views:
            self.base[v] = self.render_base(v, owners, syl_holder, colours)

        for v in views:
            items = [(self.names[i], colours[i]) for i in sorted(colours)] if v == 'all' \
                else [(self.names[v], colours[v])]
            self.base[v] = label_band(self.base[v], items, self.label_px)
        self.lights = Lights(self)
        self.ready = True

    def render_base(self, view, owners, syl_holder, colours):
        ns = '{http://www.w3.org/2000/svg}'
        cls = lambda e: (e.get('class') or '').split()
        touched = []
        def paint(g, col):
            g.set('fill', col)
            g.set('color', col)
            touched.append(g)
        if view != 'all':
            for g in self.root.iter(ns + 'g'):
                c = cls(g)
                if 'layer' in c:
                    paint(g, THEME['grey'])
            for g in self.root.iter(ns + 'g'):
                c = cls(g)
                if 'chord' in c or 'beam' in c:
                    ids = [n.get('id') for n in g.iter(ns + 'g') if 'note' in cls(n)]
                    if any(view in owners.get(i, ()) for i in ids):
                        paint(g, '#000000')
                elif ({'note', 'rest', 'mRest'} & set(c)) and g.get('id'):
                    paint(g, '#000000' if view in owners.get(g.get('id'), ()) else THEME['grey'])
            for kind, key, g in self.elems:
                if kind == 'syl':
                    paint(g, '#000000' if (view, key) in syl_readers(syl_holder, key) else THEME['grey'])
        img = render_png(etree.tostring(self.root), self.W, self.H).copy()
        if THEME['dark']:                 # engraved black on white; ink becomes light on dark
            a = 1.0 - img.min(2, keepdims=True).astype(np.float32) / 255.0
            img = (THEME['bg'] + (THEME['ink'] - THEME['bg']) * a).astype(np.uint8)
        for g in touched:
            g.attrib.pop('fill', None)
            g.attrib.pop('color', None)
        return img


_SYL_INDEX = {}


def index_syl_holder(syl_holder):
    _SYL_INDEX.clear()
    for (part, nid), holder in syl_holder.items():
        _SYL_INDEX.setdefault(holder, []).append((part, nid))


def syl_readers(syl_holder, holder):
    return {(p, holder) for p, _ in _SYL_INDEX.get(holder, [])}


class Lights:
    """Precomputed pixels and halos for each element, per colour."""

    def __init__(self, page):
        self.page, self.tint = page, THEME['tint']
        self.cache = {}
        W = page.W
        self.groups = {}                      # (kind, key) -> indices of elems
        for j, (kind, key, _) in enumerate(page.elems):
            k2 = self.key(kind, key)
            self.groups.setdefault(k2, []).append(j)
        self.geom = {}
        for gk, js in self.groups.items():
            pix = np.concatenate([page.pix[j] for j in js] + [page.shared_ink.get(gk[1], np.zeros(0, int))
                                                             if gk[0] == 'note' else np.zeros(0, int)])
            pix = np.unique(pix)
            if not len(pix):
                continue
            if gk[0] == 'note' and gk[1] in page.heads:
                cx, cy, rx, ry = page.heads[gk[1]]
                pad = max(5.0, 1.4 * ry)
                ry, rx = ry + pad, rx + pad
                y0, y1 = int(max(0, cy - ry)), int(min(page.H - 1, cy + ry))
                x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1
                halo = (yy[inside] * W + xx[inside]).ravel()
            elif gk[0] == 'note':
                continue                  # a note whose head was not found in the SVG
            elif gk[0] == 'rest':
                ys, xs = pix // W, pix % W
                (ya, yb), (xa, xb) = np.percentile(ys, [1, 99]), np.percentile(xs, [1, 99])
                cy, cx = (ya + yb) / 2, (xa + xb) / 2
                ry, rx = (yb - ya) / 2 + 1, (xb - xa) / 2 + 1
                # a whole-bar rest is a small glyph: size its halo by the staff, not the glyph
                sp = page.space_px
                ry, rx = max(ry + 0.6 * sp, 1.5 * sp), max(rx + 0.6 * sp, 1.8 * sp)
                y0, y1 = int(max(0, cy - ry)), int(min(page.H - 1, cy + ry))
                x0, x1 = int(max(0, cx - rx)), int(min(W - 1, cx + rx))
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1
                halo = (yy[inside] * W + xx[inside]).ravel()
            else:
                ys, xs = pix // W, pix % W
                (ya, yb), (xa, xb) = np.percentile(ys, [1, 99]).astype(int), np.percentile(xs, [1, 99]).astype(int)
                h = yb - ya + 1
                pad = max(3, int(0.25 * h))
                y0, y1 = max(0, ya - pad), min(page.H - 1, yb + pad)
                x0, x1 = max(0, xa - pad), min(W - 1, xb + pad)
                yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                halo = (yy * W + xx).ravel()
            in_halo = np.isin(pix, halo)
            hy, hx = halo // W, halo % W
            self.geom[gk] = (pix, self.page.alpha[pix][:, None], in_halo[:, None], halo,
                             (int(hx.min()), int(hx.max()), int(hy.max())))

    def key(self, kind, nid):
        if kind in ('body', 'head', 'note'):
            return ('note', self.page.alias.get(nid, nid))
        return (kind, nid)

    def tints(self, gk, cols):
        """Halo pixel values; a note or word two parts share gets a halo split in their colours."""
        key = ('halo', gk, cols)
        v = self.cache.get(key)
        if v is None:
            halo = self.geom[gk][3]
            ts = np.array([THEME['bg'] * (1 - self.tint) + hexrgb(c) * self.tint for c in cols]).astype(np.uint8)
            if len(cols) == 1:
                v = np.broadcast_to(ts[0], (len(halo), 3))
            else:
                xs = halo % self.page.W
                k = np.clip(((xs - xs.min()) * len(cols)) // (xs.max() - xs.min() + 1), 0, len(cols) - 1)
                v = ts[k]
            self.cache[key] = v
        return v

    def apply(self, frame_flat, lit):
        """lit: list of (group key, tuple of colour hexes in part order, fraction of a rest gone)."""
        W = self.page.W
        for gk, cols, prog in lit:
            if prog is None:
                continue
            # a lit rest gets a bar that fills while the rest lasts, running from where the rest
            # starts to where it ends as the other staves lay out that time: the fill reaches each
            # note they print as it sounds, so nobody has to count
            _, above, top, bot = self.page.rest_bar[gk[1]]
            x0, x1, xe = prog
            sp = self.page.space_px
            th = max(4, int(round(0.4 * sp)))
            y0 = int(round(top - 0.45 * sp - th)) if above else int(round(bot + 0.45 * sp))
            y0 = min(max(0, y0), self.page.H - th)
            f = frame_flat.reshape(self.page.H, W, 3)
            for k, col in enumerate(cols):       # a rest two parts share: one stripe each
                c = hexrgb(col)
                ya, yb = y0 + k * th // len(cols), y0 + (k + 1) * th // len(cols)
                f[ya:yb, x0:x1 + 1] = (THEME['bg'] * 0.65 + c * 0.35).astype(np.uint8)
                if xe > x0:
                    f[ya:yb, x0:xe] = c.astype(np.uint8)
        lit = [(gk, cols) for gk, cols, _ in lit]
        for gk, cols in lit:
            if gk in self.geom:
                h = self.geom[gk][3]
                frame_flat[h] = (np.maximum if THEME['dark'] else np.minimum)(frame_flat[h], self.tints(gk, cols))
        for gk, cols in lit:
            g = self.geom.get(gk)
            if g is None:
                continue
            key = (gk, cols)
            v = self.cache.get(key)
            if v is None:
                c = hexrgb(cols[0])
                c = c + (255 - c) * THEME['lift']        # lit ink a shade lighter than its halo
                t = self.tints(gk, cols).astype(np.float32)
                bg = np.tile(THEME['bg'], (len(g[0]), 1))
                inside = g[2][:, 0]
                if inside.any():
                    pos = np.searchsorted(g[3], g[0][inside]) if np.all(np.diff(g[3]) > 0) else None
                    bg[inside] = t[pos] if pos is not None else t[0]
                v = (bg * (1 - g[1]) + c[None, :] * g[1]).astype(np.uint8)
                self.cache[key] = v
            frame_flat[g[0]] = v


def label_band(img, items, px):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype('DejaVuSans-Bold.ttf', px)
    except OSError:
        try:
            font = ImageFont.load_default(size=px)
        except TypeError:
            font = ImageFont.load_default()
    x = int(px * 0.8)
    for text, col in items:
        d.text((x, int(px * 0.4)), text, fill=col, font=font)
        x += int(d.textlength(text, font=font)) + int(px * 1.2)
    return np.asarray(im).copy()


def measure_output(mp4, fps, W, H):
    """Sync measured on the finished file: when a light comes on in the picture against the
    nearest onset in the file's own audio."""
    w, h = 240, int(240 * H / W)
    ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-i', mp4, '-vf', f'scale={w}:{h}:flags=area',
                           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    on, prev, k = [], None, 0                  # a frame at a time: a whole song would not fit in memory
    while True:
        buf = ff.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        v = np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(np.int16)
        sat = (v.max(2) - v.min(2)) > 40                       # coloured pixels: the lights
        if prev is not None:
            grew = np.logical_and(sat, ~prev[1]).sum()
            big = np.abs(v - prev[0]).mean() > 20              # a page turn changes everything
            if grew >= 2 and not big:
                on.append(k)
        prev, k = (v, sat), k + 1
    ff.wait()
    on = np.array(on)
    t_on = on / fps
    aon = audio_onsets(decode(mp4))
    if not len(t_on) or not len(aon):
        print('   measured in the mp4: nothing to compare')
        return
    k = np.clip(np.searchsorted(aon, t_on), 1, max(1, len(aon) - 1))
    near = np.where(np.abs(aon[k - 1] - t_on) < np.abs(aon[np.minimum(k, len(aon) - 1)] - t_on),
                    aon[k - 1], aon[np.minimum(k, len(aon) - 1)])
    r = near - t_on
    r = r[np.abs(r) < 0.35]
    if not len(r):
        print('   measured in the mp4: no light matched an audio onset within 0.35 s')
        return
    q = len(r) // 3 or 1
    print(f'   measured in the mp4: {len(r)} of {len(t_on)} lights coming on matched an audio onset; '
          f'median {1000 * np.median(r):+.0f} ms (a frame is {1000 / fps:.0f} ms), first third '
          f'{1000 * np.median(r[:q]):+.0f} ms, last third {1000 * np.median(r[-q:]):+.0f} ms')


# ----------------------------------------------------------------------------- main

def featured_of(mp3, names, part_map):
    b = os.path.basename(mp3)
    m = re.search(r' - \((.+?)\) ', b) or re.search(r' - (Solo[^-]*?) (?:predominant|part-left)', b)
    if not m:
        return None
    sec = m.group(1).strip()
    sec = part_map.get(sec, sec)
    for i, n in enumerate(names):
        if n.lower() == sec.lower():
            return i
    # "Solo 1" in the mp3 name for a part called "Solo 1 (tenor)"
    near = [i for i, n in enumerate(names)
            if n.lower().startswith(sec.lower()) and not n[len(sec):len(sec) + 1].isalnum()]
    if len(near) == 1:
        return near[0]
    sys.exit(f'{b}: no part named {sec!r} in the score (parts: {names}); map it with --part "{sec}=<part name>"')


def use_display(path, root, parts, names, notes_by_part, tempos):
    """Show `path` instead of the file the audio was rendered from, after checking that it
    has the same parts, bars, notes and tempo marks (words, slurs and ties may differ: the
    Cantai learning file re-sings tied notes that the print file ties)."""
    import tempfile
    droot = read_xml(path)
    dparts = droot.findall('part')
    dsps = {sp.get('id'): sp for sp in droot.find('part-list').findall('score-part')}
    dnames = [(dsps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in dparts]
    if len(dparts) != len(parts):
        sys.exit(f'--display: {len(dparts)} parts against {len(parts)} in the file the audio came from')
    tmp = tempfile.NamedTemporaryFile(suffix='.musicxml', delete=False)
    tmp.write(etree.tostring(droot))
    tmp.close()
    _p, _b, dtempos = load_score(tmp.name)
    os.unlink(tmp.name)
    if [(round(b, 3), q) for b, q in dtempos] != [(round(b, 3), q) for b, q in tempos]:
        sys.exit(f'--display: tempo marks differ ({dtempos} against {tempos}); the lights would not follow the audio')
    dnotes, dstarts = [], None
    for i, p in enumerate(dparts):
        ns_, st = scan_part(i, p)
        dnotes.append(ns_)
        dstarts = dstarts or st
    sig = lambda ns_: {} if not ns_ else {mi: sorted((n['rel'], n['dur'], n['midi']) for n in ns_
                                                     if n['mi'] == mi and not n['rest'] and not n['grace'])
                                          for mi in range(max(n['mi'] for n in ns_) + 1)}
    bad = 0
    for i in range(len(parts)):
        if dnames[i] != names[i]:
            print(f'   --display: part {i + 1} is "{dnames[i]}" there and "{names[i]}" here')
        a, b = sig(notes_by_part[i]), sig(dnotes[i])
        diff = [mi + 1 for mi in sorted(set(a) | set(b)) if a.get(mi) != b.get(mi)]
        if diff:
            bad += 1
            print(f'   --display: {names[i]} has different notes in bars {diff[:12]}{" ..." if len(diff) > 12 else ""}')
    print(f'display: {os.path.basename(path)}; ' +
          ('same bars, notes and tempo marks as the file the audio came from' if not bad
           else 'the lights in the bars above follow the display file, not the audio'))
    sung = {i for i, ns_ in enumerate(dnotes) if any(n['lyric'] for n in ns_)}
    return droot, dparts, dnames, dnotes, dstarts, sung


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('mp3s', nargs='+')
    ap.add_argument('-o', '--out', help='folder for the mp4s (default: beside each mp3)')
    ap.add_argument('--part', action='append', default=[], help='"Section in the mp3 name=part name in the score"')
    ap.add_argument('--staves', help='pairs sharing a staff, e.g. "Tenor 1+Tenor 2,Baritone+Bass"')
    ap.add_argument('--open', action='store_true', help='one part per staff (open score)')
    ap.add_argument('--clip', help='START,SECONDS: render only this stretch (for a test)')
    ap.add_argument('--stills', help='comma-separated times (s): write PNG frames instead of a video')
    ap.add_argument('--size', default='1920x1080')
    ap.add_argument('--staff-px', type=float, default=44.0, help='staff height in pixels')
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--lead', type=float, default=1.0, help='turn the page up to this many s early')
    ap.add_argument('--warp', action='store_true', help='follow measured drift piecewise')
    ap.add_argument('--crf', type=int, default=20)
    ap.add_argument('--no-condense', action='store_true', help='keep empty staves on every system')
    ap.add_argument('--display', help='a print-faithful MusicXML with the same bars, notes and tempo marks '
                    '(normal slurs, ties and words) to show instead of the file the audio came from')
    ap.add_argument('--pulse', type=int, help='rest bars jump in these notes (8 = eighths, 16 = sixteenths); '
                    'default: per part, the coarsest value 95%% of its sung bars keep to')
    ap.add_argument('--dark', action='store_true', help='light notation on a dark screen instead of black on white')
    a = ap.parse_args()
    set_theme(a.dark)
    palette = PALETTE_DARK if a.dark else PALETTE
    W, H = (int(v) for v in a.size.lower().split('x'))
    part_map = dict(p.split('=', 1) for p in a.part)

    root = read_xml(a.score)
    if root.find('.//repeat') is not None or root.find('.//sound[@dacapo]') is not None or \
            root.find('.//sound[@dalsegno]') is not None:
        print('warning: the score has repeats or jumps; they are not expanded, so timing after the first '
              'one will be wrong. Use a copy with the repeats written out.')
    parts = root.findall('part')
    sps = {sp.get('id'): sp for sp in root.find('part-list').findall('score-part')}
    names = [(sps[p.get('id')].findtext('part-name') or p.get('id')).strip() for p in parts]
    notes_by_part, starts = [], None
    for i, p in enumerate(parts):
        ns_, st = scan_part(i, p)
        notes_by_part.append(ns_)
        starts = starts or st
    sung = {i for i, ns_ in enumerate(notes_by_part) if any(n['lyric'] for n in ns_)}
    if not sung:
        sys.exit('no part has lyrics; nothing to follow')

    # tempo map and bars, exactly as stem_vs_score.py reads them
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix='.musicxml', delete=False)
    tmp.write(etree.tostring(root))
    tmp.close()
    _phr, bars, tempos = load_score(tmp.name)
    os.unlink(tmp.name)
    sec = lambda q: beats_to_sec(float(q), tempos)

    if a.display:
        root, parts, names, notes_by_part, starts, sung = use_display(
            a.display, root, parts, names, notes_by_part, tempos)

    # pairs
    if a.open:
        pairs = []
    elif a.staves:
        idx = {n.lower(): i for i, n in enumerate(names)}
        pairs = []
        for grp in a.staves.split(','):
            u, l = (s.strip().lower() for s in grp.split('+'))
            if u not in idx or l not in idx:
                sys.exit(f'--staves: unknown part in {grp!r}; parts are {names}')
            pairs.append((idx[u], idx[l]))
    else:
        pairs = default_pairs(names, sung)
    colours = {}                           # the parts sharing staves get the four strongest colours
    for i in [x for pr in pairs for x in pr] + sorted(sung):
        if i in sung and i not in colours:
            colours[i] = palette[len(colours) % len(palette)]
    print('parts: ' + ', '.join(f'{names[i]}{" (sung, " + colours[i] + ")" if i in sung else ""}'
                                 for i in range(len(names))))
    print('staves: ' + ('open score' if not pairs else
                        ', '.join(f'{names[u]} + {names[l]}' for u, l in pairs)))
    disp, owners, syl_holder = display_score(root, parts, notes_by_part, pairs, sung)
    index_syl_holder(syl_holder)

    # windows in score seconds
    note_win, syl_win, rest_win, rest_q = {}, {}, {}, {}
    # each sung part's pulse: the coarsest note value that 95% of the bars it sings keep to
    # (every note starting and lasting a whole number of them; tuplets aside). A piece in
    # eighths with one bar of sixteenths pulses in eighths. A rest's bar fills in jumps of this
    # length counted from the barline, so the pulse shows, the way a sung note lights up
    pulse = {}
    for i in sung:
        bars_ = {}
        for n in notes_by_part[i]:
            if not n['grace'] and not n['tmod'] and n['dur'] > 0:
                bars_.setdefault(n['mi'], []).append(n)
        sung_bars = [ns_ for ns_ in bars_.values() if any(not n['rest'] for n in ns_)]
        pulse[i] = Fr(1, 8)
        for u in (Fr(4), Fr(2), Fr(1), Fr(1, 2), Fr(1, 4), Fr(1, 8)):
            fits = sum(all(n['rel'] % u == 0 and n['dur'] % u == 0 for n in ns_) for ns_ in sung_bars)
            if sung_bars and fits >= 0.95 * len(sung_bars):
                pulse[i] = u
                break
        if a.pulse:
            pulse[i] = Fr(4, a.pulse)
    note_name = {Fr(4): 'whole', Fr(2): 'half', Fr(1): 'quarter', Fr(1, 2): 'eighth', Fr(1, 4): 'sixteenth',
                 Fr(1, 8): '32nd'}
    print('rest bars jump in: ' + ', '.join(f'{names[i]} {note_name.get(pulse[i], str(pulse[i]) + " quarter")}s'
                                             for i in sorted(sung)))

    def steps(nid, part):
        """Score seconds where a rest's bar jumps: the end of each pulse inside the rest."""
        q0, q1, m0 = rest_q[nid]
        u = pulse[part]
        k = (q0 - m0) // u + 1
        out = []
        while m0 + k * u < q1:
            out.append(sec(m0 + k * u))
            k += 1
        return tuple(out) + (sec(q1),)
    all_onsets = []
    for i, ns_ in enumerate(notes_by_part):
        for n in ns_:
            if not n['rest'] and not n['grace'] and n['dur'] > 0:
                all_onsets.append(sec(n['on']))
        if i not in sung:
            continue
        for n in ns_:
            if n['grace'] or n['dur'] == 0:
                continue
            # a rest lights for as long as it lasts, like a note: a singer who cannot count
            # rests watches the light move through them
            (rest_win if n['rest'] else note_win).setdefault(n['id'], []).append(
                (i, sec(n['on']), sec(n['on'] + n['dur'])))
            if n['rest']:
                rest_q[n['id']] = (n['on'], n['on'] + n['dur'], n['on'] - n['rel'])
        for nid, (q0, q1) in syllable_windows(ns_).items():
            h = syl_holder.get((i, nid))
            if h:
                syl_win.setdefault(h, []).append((i, sec(q0), sec(q1)))
    # a unison notehead carries both parts; the lower part's own note id is not printed
    unison_extra = {}
    for table in (note_win, rest_win):
        for nid, ps in owners.items():
            for p in ps:
                if nid in table and not any(w[0] == p for w in table[nid]):
                    unison_extra.setdefault(nid, []).append(p)
    for nid, ps in unison_extra.items():
        table = note_win if nid in note_win else rest_win
        _, t0, t1 = table[nid][0]
        for p in ps:
            table[nid].append((p, t0, t1))
    first_score = min(all_onsets)

    # engrave
    import verovio
    install_smufl_font()
    z = 72.0 / a.staff_px
    band = int(round(0.045 * H))
    opts = {'pageWidth': int(W * z), 'pageHeight': int(H * z), 'scale': 100,
            'pageMarginTop': int((band + 0.01 * H) * z), 'pageMarginBottom': int(0.02 * H * z),
            'pageMarginLeft': int(0.02 * W * z), 'pageMarginRight': int(0.02 * W * z),
            'breaks': 'auto', 'header': 'none', 'footer': 'none', 'adjustPageHeight': False,
            'justifyVertically': False, 'lyricSize': 5.0, 'spacingSystem': 10, 'svgViewBox': False}
    tk = verovio.toolkit()
    tk.setOptions(opts)
    if not tk.loadData(etree.tostring(disp).decode()):
        sys.exit('verovio could not read the closed score')
    base_mei = tk.getMEI()
    pair_of = {x: pr for pr in pairs for x in pr}
    on_sec = {n['id']: sec(n['on']) for ns_ in notes_by_part for n in ns_ if not n['grace']}
    piece_end = max(n['on'] + n['dur'] for ns_ in notes_by_part for n in ns_)
    ends = [sec(q) for q in starts[1:]] + [sec(piece_end)]
    bar_end = {n['id']: ends[n['mi']] for ns_ in notes_by_part for n in ns_ if n['mi'] < len(ends)}
    # a whole-bar rest is printed mid-bar, so it says nothing about where in the bar a time falls
    x_sec = {n['id']: on_sec[n['id']] for ns_ in notes_by_part for n in ns_
             if n['id'] in on_sec and not (n['rest'] and (n['el'].find('rest').get('measure') == 'yes'
                                                           or n['type'] in (None, 'whole') and n['rel'] == 0))}
    layouts = {}

    def layout(view):
        """The screens for one view. Staves empty for a whole system are hidden, as in a printed
        score (Verovio does this for MEI with <scoreDef optimize="true">, not for MusicXML, and
        keeps the note ids); in one part's own video its staff is never hidden, so its rests
        stay on screen to be lit."""
        if view in layouts:
            return layouts[view]
        mei = base_mei
        if not a.no_condense:
            M = '{http://www.music-encoding.org/ns/mei}'
            r = etree.fromstring(re.sub(r'<scoreDef ', '<scoreDef optimize="true" ', mei, count=1).encode())
            if view != 'all':
                pid = f'PX{pair_of[view][0]}' if view in pair_of else parts[view].get('id')
                sd = next((d for d in r.iter(M + 'staffDef')
                           if d.get('{http://www.w3.org/XML/1998/namespace}id') == pid), None)
                for st in (r.iter(M + 'staff') if sd is not None else []):
                    if st.get('n') == sd.get('n') and st.find('.//' + M + 'note') is None \
                            and st.find('.//' + M + 'chord') is None:
                        # an invisible whole note keeps the staff; the bar rest stays on its line
                        for mr in st.iter(M + 'mRest'):
                            mr.set('loc', '6')
                        ly = etree.SubElement(st, M + 'layer', n='9')
                        etree.SubElement(ly, M + 'note', dur='1', oct='4', pname='c', visible='false')
            mei = etree.tostring(r).decode()
        t = verovio.toolkit()
        t.setOptions(opts)
        if not t.loadData(mei):
            sys.exit('verovio could not re-read the score as MEI')
        pages = [Page(t.renderToSVG(p), W, H, owners, syl_holder, colours, [view], names, int(band * 0.62),
                      x_sec, bar_end)
                 for p in range(1, t.getPageCount() + 1)]
        first, last = [], []
        for pg in pages:
            ts = [on_sec[i] for i in pg.ids_on_page if i in on_sec]
            first.append(min(ts) if ts else None)
            last.append(max(ts) if ts else None)
        print(f'engraved for {"every part" if view == "all" else names[view]}: {len(pages)} screens of '
              f'{W}x{H}, staff {a.staff_px:.0f} px')
        layouts[view] = (pages, first, last)
        return layouts[view]

    jobs = []
    for mp3 in a.mp3s:
        f = featured_of(mp3, names, part_map)
        if f is not None and f not in sung:
            sys.exit(f'{mp3}: {names[f]} has no lyrics in the score')
        out_dir = a.out or os.path.dirname(os.path.abspath(mp3))
        base = os.path.splitext(os.path.basename(mp3))[0]
        jobs.append((mp3, 'all' if f is None else f, os.path.join(out_dir, base)))

    bar_sec = [(sec(q), b.get('number')) for q, b in zip(starts, parts[0].findall('measure'))]

    for mp3, view, stem in jobs:
        pages, page_first, page_last = layout(view)
        T = Timing(a.score, mp3, all_onsets, first_score, warp=a.warp)
        def bar_at(t_audio):
            s = (t_audio - T.off) / T.scale
            cur = bar_sec[0][1]
            for s0, num in bar_sec:
                if s0 <= s + 1e-6:
                    cur = num
            return cur
        T.report(bar_at, f'{os.path.basename(mp3)} -> {"every part" if view == "all" else names[view]}')
        # page turns (audio seconds)
        turns = [0.0]
        for p in range(1, len(pages)):
            if page_first[p] is None:
                turns.append(turns[-1])
                continue
            start = float(T(page_first[p]))
            prev_last = float(T(page_last[p - 1])) if page_last[p - 1] is not None else 0.0
            turns.append(min(start, max(prev_last + 0.3, start - a.lead)))
        # light windows per page: (t0, t1, page, group key, colour)
        wins = []
        page_of = {}                               # (kind, id) -> (page, lit group)
        for pi_, pg in enumerate(pages):
            for kind, key, _ in pg.elems:
                kk = ('note' if kind in ('body', 'head') else kind, key)
                page_of[kk] = (pi_, ('note', pg.alias.get(key, key)) if kk[0] == 'note' else kk)
        for kind, table in (('note', note_win), ('syl', syl_win), ('rest', rest_win)):
            for nid, ws in table.items():
                if (kind, nid) not in page_of:
                    continue
                pi_, gk = page_of[(kind, nid)]
                for part, s0, s1 in ws:
                    if view == 'all' or part == view:
                        wins.append((float(T(s0)), float(T(s1)), pi_, gk, colours[part], part, s0, s1,
                                     steps(nid, part) if kind == 'rest' else None))
        wins.sort()

        t_start, t_len = 0.0, T.dur
        if a.clip:
            c0, c1 = (float(v) for v in a.clip.split(','))
            t_start, t_len = c0, min(c1, T.dur - c0)

        def lit_key(p, ws, t):
            lit, prog = {}, {}
            for w in ws:
                if w[2] == p:
                    lit.setdefault(w[3], set()).add((w[5], w[4]))
                    rb = pages[p].rest_bar.get(w[3][1]) if w[3][0] == 'rest' else None
                    if rb is not None:
                        ts, xs = pages[p].timemap[rb[0]]
                        s = w[6] + (t - w[0]) / max(w[1] - w[0], 1e-6) * (w[7] - w[6])
                        s = next((b for b in w[8] if b > s + 1e-9), w[7])   # through the current pulse
                        prog[w[3]] = tuple(int(round(float(np.interp(v, ts, xs)))) for v in (w[6], w[7], s))
            return (p, tuple(sorted((k, tuple(c for _, c in sorted(v)), prog.get(k)) for k, v in lit.items())))

        def page_at(t):
            p = 0
            for k, tt in enumerate(turns):
                if t >= tt:
                    p = k
            return p

        def frame_at(t):
            p = page_at(t)
            return lit_key(p, [w for w in wins if w[0] <= t < w[1]], t)

        def compose(key):
            p, lit = key
            pages[p].raster()
            fr = pages[p].base[view].copy()
            pages[p].lights.apply(fr.reshape(-1, 3), list(lit))
            return fr

        if a.stills:
            from PIL import Image
            for tv in a.stills.split(','):
                tv = float(tv)
                path = f'{stem} @{tv:.0f}s.png'
                Image.fromarray(compose(frame_at(tv))).save(path)
                print(f'   still: {path}')
            continue

        out = stem + ('' if not a.clip else f' clip {int(t_start)}-{int(t_start + t_len)}s') + '.mp4'
        nfr = int(round(t_len * a.fps))
        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
               '-r', str(a.fps), '-i', '-', '-ss', f'{t_start:.3f}', '-t', f'{t_len:.3f}', '-i', mp3,
               '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage',
               '-crf', str(a.crf), '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
               '-movflags', '+faststart', '-shortest', out]
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        # sweep: windows are sorted by start; keep an active list
        wi, active, prev_key, buf = 0, [], None, None
        changes = 0
        for f in range(nfr):
            t = t_start + (f + 0.5) / a.fps
            while wi < len(wins) and wins[wi][0] <= t:
                active.append(wins[wi])
                wi += 1
            active = [w for w in active if w[1] > t]
            p = page_at(t)
            key = lit_key(p, active, t)
            if key != prev_key:
                buf = compose(key).tobytes()
                prev_key = key
                changes += 1
            ff.stdin.write(buf)
        ff.stdin.close()
        if ff.wait():
            sys.exit(f'ffmpeg failed on {out}')
        # check the audio that landed against the mp3 (an AAC priming delay would shift everything)
        y = decode(out)
        x = T.x[int(t_start * 22050):int(t_start * 22050) + len(y)]
        n = min(len(x), len(y), 22050 * 20)
        lag = 0
        if n > 22050:
            seg_x, seg_y = x[:n] - x[:n].mean(), y[:n] - y[:n].mean()
            cc = np.fft.irfft(np.fft.rfft(seg_y, 2 * n) * np.conj(np.fft.rfft(seg_x, 2 * n)))
            k = int(np.argmax(np.concatenate([cc[-2205:], cc[:2206]]))) - 2205
            lag = k / 22.05
        print(f'   wrote {out}: {nfr} frames, {changes} changes of lights or page; '
              f'audio in the mp4 is {lag:+.1f} ms from the mp3')
        measure_output(out, a.fps, W, H)
        if all(v != view for _, v, _ in jobs[jobs.index((mp3, view, stem)) + 1:]):
            layouts.pop(view, None)              # its screens are not needed again: free them


if __name__ == '__main__':
    main()
