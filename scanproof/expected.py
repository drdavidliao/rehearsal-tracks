"""What each printed staff should show, bar by bar, according to the transcription.

-> {(staff name, bar): [event, ...]} in time order, where an event is

    {'onset': Fraction (quarters from the barline),
     'heads': [{'step': staff step (0 = bottom line), 'alter', 'name',
                'state_alter': what the key and the bar so far give that line or space,
                'acc_needed': a plain engraving prints an accidental here,
                'tie_stop': tied in from the previous note}],
     'kind': 'filled' | 'hollow' | 'whole' | 'x',
     'dots': {n, ...}, 'beams': {n, ...},    # sets: merged voices may differ
     'durs': [Fraction, ...]}

Events at one onset with the same notehead kind are merged into one, whatever voice or
source they come from: on the page they are one column of heads.

The transcription is chorale.scoretext (blocks named by each staff's `source`) or
MusicXML (sources {"part": id or name, "staff": n}).
"""
import xml.etree.ElementTree as ET
from fractions import Fraction as F

from chorale.events import pkey
from chorale.scoretext import parse_score

from .project import STEPS

BEAMS = {F(1, 2): 1, F(1, 4): 2, F(1, 8): 3, F(1, 16): 4}
SHARPS = 'FCGDAEB'


def key_alters(fifths):
    if fifths >= 0:
        return {s: 1 for s in SHARPS[:fifths]}
    return {s: -1 for s in SHARPS[::-1][:-fifths]}


def kind_of(ev):
    if ev.get('x'):
        return 'x'
    if ev['base'] >= 4:
        return 'whole'
    return 'hollow' if ev['base'] >= 2 else 'filled'


def _link(seq):
    """Mark tie_stop on every pitch tied into, along one voice in time order.  Unlike
    scoretext.link_ties this never raises: a dangling tie is the build's business."""
    prev = None
    for e in seq:
        for p in e['pitches']:
            p['tie_stop'] = bool(prev and any(
                pkey(q) == pkey(p) and (q.get('tie') or prev.get('tie')) for q in prev['pitches']))
        prev = e


# ------------------------------------------------------------------ sources
def from_scoretext(prj):
    """{(source, bar): [[event with 'onset'], ...voices]}"""
    blocks = parse_score(prj.rel(prj.cfg['score']), voices=True, beats=prj.cfg.get('beats', 4))
    out = {}
    for b, bars in blocks.items():
        nv = max(len(v) for v in bars.values())
        for vi in range(nv):
            _link([e for m in sorted(bars) if len(bars[m]) > vi for e in bars[m][vi]])
        for m, voices in bars.items():
            vs = []
            for v in voices:
                pos = F(0)
                for e in v:
                    e['onset'] = pos
                    pos += e['dur']
                vs.append(v)
            out[(b, m)] = vs
    return out


def from_musicxml(prj):
    """{((part id, staff), bar): [[event with 'onset'], ...voices]}, in the same event
    shape as the score text.  Bars are counted from 1 in file order (an implicit pickup
    measure is bar 0)."""
    root = ET.parse(prj.rel(prj.cfg['musicxml'])).getroot()
    names = {sp.get('id'): (sp.findtext('part-name') or '') for sp in root.iter('score-part')}
    out = {}
    fifths = None
    for part in root.iter('part'):
        pid = part.get('id')
        div = 1
        seqs = {}
        bar = 0
        for meas in part.iter('measure'):
            bar = 0 if meas.get('implicit') == 'yes' and bar == 0 else bar + 1
            pos = F(0)
            last_onset = F(0)
            for el in meas:
                if el.tag == 'attributes':
                    div = int(el.findtext('divisions') or div)
                    fx = el.findtext('key/fifths')
                    if fx is not None and fifths is None:
                        fifths = int(fx)
                elif el.tag == 'backup':
                    pos -= F(int(el.findtext('duration')), div)
                elif el.tag == 'forward':
                    pos += F(int(el.findtext('duration')), div)
                elif el.tag == 'note':
                    if el.find('grace') is not None or el.find('cue') is not None:
                        continue
                    dur = F(int(el.findtext('duration') or 0), div)
                    chord = el.find('chord') is not None
                    staff = int(el.findtext('staff') or 1)
                    voice = el.findtext('voice') or '1'
                    onset = last_onset if chord else pos
                    key = ((pid, staff), bar)
                    vl = out.setdefault(key, {}).setdefault(voice, [])
                    pitch = el.find('pitch')
                    p = None
                    if pitch is not None:
                        p = {'step': pitch.findtext('step'), 'alter': int(float(pitch.findtext('alter') or 0)),
                             'oct': int(pitch.findtext('octave'))}
                        if any(t.get('type') == 'start' for t in el.findall('tie')):
                            p['tie'] = True
                    if chord and vl:
                        if p:
                            vl[-1]['pitches'].append(p)
                            vl[-1]['pitches'].sort(key=pkey)
                    else:
                        typ = el.findtext('type')
                        base = {'whole': F(4), 'half': F(2), 'quarter': F(1), 'eighth': F(1, 2),
                                '16th': F(1, 4), '32nd': F(1, 8), 'breve': F(8)}.get(typ, dur)
                        if el.find('rest') is not None and el.find('rest').get('measure') == 'yes':
                            base = F(4)
                        ev = {'onset': onset, 'dur': dur, 'base': base, 'dots': len(el.findall('dot')),
                              'pitches': [p] if p else [], 'tie': False,
                              'x': el.findtext('notehead') == 'x',
                              'hidden': el.get('print-object') == 'no'}
                        vl.append(ev)
                        seqs.setdefault((staff, voice), []).append(ev)
                        last_onset = onset
                        pos += dur
        for seq in seqs.values():
            _link(seq)
    res = {}
    for key, voices in out.items():
        res[key] = list(voices.values())
        (pid, staff), bar = key
        if names.get(pid):
            res[((names[pid], staff), bar)] = res[key]
    if prj.cfg.get('key_fifths') is None and fifths is not None:
        prj.cfg['key_fifths'] = fifths
    return res


# ------------------------------------------------------------------ per staff
def events(prj):
    if 'score' in prj.cfg:
        src = from_scoretext(prj)
        keyof = lambda s: s                                          # noqa: E731
    elif 'musicxml' in prj.cfg:
        src = from_musicxml(prj)
        keyof = lambda s: (s['part'], s.get('staff', 1))             # noqa: E731
    else:
        raise ValueError('the config needs "score" (score text) or "musicxml"')
    key = key_alters(prj.cfg.get('key_fifths') or 0)
    bars = sorted({m for (_, m) in src})
    out = {}
    for st in prj.staves:
        name = st['name']
        bottom = prj.bottom(name)
        for m in bars:
            raw = []
            for s in st.get('source', [name]):
                for v in src.get((keyof(s), m), []):
                    raw += [e for e in v if e['pitches'] and not e.get('hidden')]
            raw.sort(key=lambda e: e['onset'])
            state = {}
            merged = []
            for e in raw:
                kind = kind_of(e)
                hs = []
                for p in e['pitches']:
                    k = (p['step'], p['oct'])
                    cur = state.get(k, key.get(p['step'], 0))
                    state[k] = p['alter']
                    hs.append({'step': STEPS.index(p['step']) + 7 * p['oct'] - bottom,
                               'alter': p['alter'], 'state_alter': cur,
                               'acc_needed': p['alter'] != cur and not p.get('tie_stop'),
                               'tie_stop': bool(p.get('tie_stop')),
                               'name': f"{p['step']}{'#' if p['alter'] > 0 else 'b' if p['alter'] < 0 else ''}{p['oct']}"})
                beams = BEAMS.get(e['base'], 0)
                same = [x for x in merged if x['onset'] == e['onset'] and x['kind'] == kind]
                if same:
                    x = same[0]
                    for h in hs:
                        if not any(h['step'] == g['step'] for g in x['heads']):
                            x['heads'].append(h)
                    x['heads'].sort(key=lambda h: h['step'])
                    x['dots'].add(e['dots'])
                    x['beams'].add(beams)
                    x['durs'].append(e['dur'])
                else:
                    merged.append({'onset': e['onset'], 'heads': sorted(hs, key=lambda h: h['step']),
                                   'kind': kind, 'dots': {e['dots']}, 'beams': {beams},
                                   'durs': [e['dur']]})
            out[(name, m)] = merged
    return out


def value_name(beams, kind):
    if kind == 'whole':
        return 'whole'
    if kind == 'hollow':
        return 'half'
    return {0: 'quarter', 1: 'eighth', 2: '16th', 3: '32nd'}.get(beams, f'{beams} beams')
