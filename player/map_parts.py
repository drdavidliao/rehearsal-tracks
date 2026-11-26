#!/usr/bin/env python3
"""The notes a player map plays, taken from the stamped transcription (design 2026-11-16, "map rebuild").

    python3 player/map_parts.py "song folder" RULES.json [--old OLD.musicxml]

A stamped transcription writes the page: two singers on one staff are voices and chords of one part. A map wants one
part per stem, one note at a time. This writes that file from the stamped one by a short rule, checks every note it
writes against the stamped file, lists the stamped notes no map voice sings, and with --old lists every difference from
the file the map used before. It writes a record beside the file (OUT.derived.json) that make_map.py and
make_map_scan.py accept in place of a completeness stamp while the file and its source are unchanged and the source's
stamp still passes.

RULES.json (paths from the song folder):

    {"source": "Song (full, from the original).musicxml", "out": "_build/Song (map parts).musicxml",
     "staves": {"Tenors": [["Tenor 1"], ["Tenor 2a", "Tenor 2b"]], "Basses": [["Baritone"], ["Bass"]]},
     "rename": {"T.1": "Tenor 1"},
     "overrides": [{"singer": "Tenor 2", "bars": [174], "as": "Tenor 2a"}],
     "drop": ["Everyone clap"]}

`staves` splits a part (one staff) among its singers, top to bottom, in groups. Where the staff has two voices at a
moment (a note or rest of voice 2 sounding then), voice 1 is the first group's and voice 2 the second's; where it has
one, that voice is everyone's. Within what a voice serves, a single note is everyone's, and a chord gives one note to
each group (as many notes as groups) or to each singer (as many as singers), top down; anything else stops with the bar
named, for an override. Cue-size heads (an optional note) are never given. A note's syllable is its own, or the chord's,
or, with none, the other voice's at the same moment, unless the note is tied into (printed once for both). A hidden rest
(print-object="no") only fills a voice out to the barline, so the staff counts as one voice there.

`overrides` gives a singer, in the bars listed (printed numbers), the notes another singer of the same staff gets:
"singer" may be a name that only overrides use, so a stem that sings 2b but 2a in bar 174 is
{"singer": "Tenor 2", "base": "Tenor 2b", "bars": [174], "as": "Tenor 2a"}, with "Tenor 2" listed in `keep`, or in
place of the staff's singers. `keep`, if given, is the singers written, in order; the others are left out.

Parts not in `staves` are copied as they are (renamed by `rename`), unless dropped; parts copied keep their own voices.
"""
import argparse, copy, datetime, hashlib, json, os, sys, xml.etree.ElementTree as ET
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
STEP = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def midi(n):
    p = n.find('pitch')
    if p is None: return None
    return 12 * (int(p.findtext('octave')) + 1) + STEP[p.findtext('step')] + int(float(p.findtext('alter') or 0))


def cue(n):
    t = n.find('type')
    return n.find('cue') is not None or (t is not None and t.get('size') == 'cue')


def numbers(root):
    first = root.find('part')
    return [m.get('number') for m in first.findall('measure')]


def read_events(part):
    """per measure: divisions, [(pos, element)] of everything that isn't a note, backup or forward, and per voice the
    events [{on, dur, notes: [note elements, chord order], rest}]"""
    out, div = [], 1
    for m in part.findall('measure'):
        pos, others, voices, last = F(0), [], {}, None
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None: div = int(e.findtext('divisions'))
            if e.tag == 'backup': pos -= F(int(e.findtext('duration')), div); continue
            if e.tag == 'forward': pos += F(int(e.findtext('duration')), div); continue
            if e.tag != 'note':
                others.append((pos, e)); continue
            if e.find('grace') is not None: continue
            v = e.findtext('voice') or '1'
            if e.find('chord') is not None and last is not None:
                last['notes'].append(e); continue
            d = F(int(e.findtext('duration') or 0), div)
            last = dict(on=pos, dur=d, notes=[e], rest=e.find('rest') is not None, voice=v)
            voices.setdefault(v, []).append(last)
            pos += d
        out.append(dict(div=div, others=others, voices=voices, number=m.get('number')))
    return out


def syllable(n):
    return n.find('lyric')


def split_part(part, groups, overrides, bar_no):
    """{singer: per measure [(on, dur, note element or None for a rest, lyric element or None)]}"""
    singers = [s for g in groups for s in g]
    meas = read_events(part)
    got = {s: [[] for _ in meas] for s in singers}
    used = set()
    for mi, M in enumerate(meas):
        vs = sorted(M['voices'])
        if len(vs) > 2: raise SystemExit(f'bar {M["number"]}: {len(vs)} voices on one staff; only two are split')
        # a hidden rest (print-object="no") only fills a voice out to the barline: the staff is one voice there
        for v in list(M['voices']):
            M['voices'][v] = [ev for ev in M['voices'][v] if not (ev['rest'] and ev['notes'][0].get('print-object') == 'no')]
            if not M['voices'][v]: del M['voices'][v]
        vs = sorted(M['voices'])
        def covers(v, t):
            return any(ev['on'] <= t < ev['on'] + ev['dur'] for ev in M['voices'].get(v, []))
        v1 = vs[0] if vs else None
        v2 = vs[1] if len(vs) > 1 else None
        for v in vs:
            for ev in M['voices'][v]:
                if v == v1:
                    serve = groups[:1] if (v2 and covers(v2, ev['on'])) else groups
                else:
                    serve = groups[1:]
                if not serve: raise SystemExit(f'bar {M["number"]}: voice {v} with no group to sing it')
                S = [s for g in serve for s in g]
                notes = sorted((n for n in ev['notes'] if not cue(n)), key=midi, reverse=True) if not ev['rest'] else []
                lyr = next((syllable(n) for n in ev['notes'] if syllable(n) is not None), None)
                tied_in = any(t.get('type') == 'stop' for n in ev['notes'] for t in n.findall('tie'))
                if lyr is None and v2 and not ev['rest'] and not tied_in:
                    # printed once for both voices: the other voice's syllable at the same moment, on a note attacked
                    # here (a note tied into takes no syllable)
                    other = v2 if v == v1 else v1
                    lyr = next((syllable(n) for e1 in M['voices'].get(other, []) if e1['on'] == ev['on']
                                and not e1['rest'] for n in e1['notes'] if syllable(n) is not None), None)
                if ev['rest']: pick = {s: None for s in S}
                elif len(notes) == 1: pick = {s: notes[0] for s in S}
                elif len(notes) == len(serve): pick = {s: notes[gi] for gi, g in enumerate(serve) for s in g}
                elif len(notes) == len(S): pick = dict(zip(S, notes))
                else:
                    raise SystemExit(f'bar {M["number"]}: a chord of {len(notes)} for {S} in groups {serve}; give an override')
                for s, n in pick.items():
                    got[s][mi].append((ev['on'], ev['dur'], n, lyr if n is not None else None))
                    if n is not None: used.add(id(n))
    for s in singers:
        for mi, evs in enumerate(got[s]):
            evs.sort(key=lambda e: e[0])
            for a, b in zip(evs, evs[1:]):
                if a[0] + a[1] > b[0]:
                    raise SystemExit(f'bar {meas[mi]["number"]}: {s} gets overlapping notes at {a[0]} and {b[0]}')
    for o in overrides:
        if o['singer'] not in got and o.get('base') not in got and o['as'] not in got: continue
        base = got.get(o.get('base', o['singer']))
        if base is None: continue
        line = [list(x) for x in base]
        for mi, M in enumerate(meas):
            if bar_no[mi] in {str(b) for b in o['bars']}: line[mi] = list(got[o['as']][mi])
        got[o['singer']] = line
    unsung = [(meas[mi]['number'], ev['on'], midi(n), cue(n)) for mi, M in enumerate(meas) for v in M['voices']
              for ev in M['voices'][v] if not ev['rest'] for n in ev['notes'] if id(n) not in used]
    return got, meas, unsung


def build_part(src_part, meas, line, pid):
    """a part with one line, keeping the source's non-note elements (attributes, directions, barlines) at their places"""
    P = ET.Element('part', id=pid)
    for mi, (sm, M) in enumerate(zip(src_part.findall('measure'), meas)):
        m = ET.SubElement(P, 'measure', dict(sm.attrib))
        div = M['div']
        evs, pos = [], F(0)
        for on, dur, n, lyr in line[mi]:
            if on > pos: evs.append((pos, on - pos, None, None))
            evs.append((on, dur, n, lyr)); pos = on + dur
        others = sorted(M['others'], key=lambda x: (x[1].tag != 'print', x[1].tag != 'attributes', x[0]))
        right = [e for _, e in others if e.tag == 'barline' and e.get('location', 'right') == 'right']
        rest_others = [(p, e) for p, e in others if not (e.tag == 'barline' and e.get('location', 'right') == 'right')]
        k = 0
        def flush(upto):
            nonlocal k
            while k < len(rest_others) and rest_others[k][0] <= upto:
                e = copy.deepcopy(rest_others[k][1])
                if e.tag == 'attributes':
                    for t in ('staves',): [e.remove(x) for x in e.findall(t)]
                    for c in e.findall('clef'):
                        if c.get('number') not in (None, '1'): e.remove(c)
                        else: c.attrib.pop('number', None)
                for st in e.iter('staff'): st.text = '1'
                m.append(e); k += 1
        rest_others.sort(key=lambda x: x[0])
        for on, dur, n, lyr in evs:
            flush(on)
            if n is None:
                ne = ET.SubElement(m, 'note'); ET.SubElement(ne, 'rest')
                ET.SubElement(ne, 'duration').text = str(int(dur * div))
                ET.SubElement(ne, 'voice').text = '1'
                continue
            ne = copy.deepcopy(n)
            for t in ('chord', 'staff', 'beam', 'stem'):
                for x in ne.findall(t): ne.remove(x)
            for x in ne.findall('lyric'): ne.remove(x)
            ne.find('duration').text = str(int(dur * div))
            v = ne.find('voice')
            if v is None: v = ET.SubElement(ne, 'voice')
            v.text = '1'
            nots = ne.find('notations')
            if nots is not None:
                for x in list(nots):
                    if x.tag in ('slur', 'tuplet'): nots.remove(x)
            if lyr is not None:
                L = copy.deepcopy(lyr); L.set('number', '1'); L.attrib.pop('placement', None)
                # MusicXML order: lyric after notations
                idx = len(ne)
                for i, x in enumerate(ne):
                    if x.tag in ('play', 'listen'): idx = i; break
                ne.insert(idx, L)
            m.append(ne)
        flush(F(10 ** 6))
        for e in right: m.append(copy.deepcopy(e))
    return P


def line_of(part):
    """[(bar index, onset, midi, duration, syllable)] of a one-line part, ties not joined"""
    out = []
    for mi, M in enumerate(read_events(part)):
        for v in M['voices']:
            for ev in M['voices'][v]:
                if ev['rest']: continue
                n = next((n for n in ev['notes'] if not cue(n)), ev['notes'][0])
                L = next((syllable(x) for x in ev['notes'] if syllable(x) is not None), None)
                out.append((mi, ev['on'], midi(n), ev['dur'], (L.findtext('text') or '') if L is not None else ''))
    return sorted(out)


def derived_ok(path):
    """the file was written by this script from a source that still passes its completeness check, and neither has changed"""
    rec = path + '.derived.json'
    if not os.path.exists(rec): return False
    r = json.load(open(rec))
    src = os.path.join(os.path.dirname(path), r['source'])
    import completeness_check
    return (r.get('sha256') == sha(path) and os.path.exists(src) and r.get('source_sha256') == sha(src)
            and completeness_check.stamped(src))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder'); ap.add_argument('rules')
    ap.add_argument('--old', help='the notes file the map used before: every difference from it is listed')
    a = ap.parse_args()
    at = lambda f: os.path.join(a.folder, f)
    R = json.load(open(at(a.rules)))
    src = at(R['source'])
    import completeness_check
    if not completeness_check.stamped(src): sys.exit(f'{R["source"]}: no passing completeness stamp')
    tree = ET.parse(src); root = tree.getroot()
    names = {sp.get('id'): sp for sp in root.iter('score-part')}
    bar_no = numbers(root)
    plist = root.find('part-list')
    new_parts, new_sp, report = [], [], dict(unsung={}, checked=0)
    keep = R.get('keep')
    k = 0
    for part in root.findall('part'):
        sp = names[part.get('id')]; nm = sp.findtext('part-name')
        if nm in R.get('drop', []): continue
        if nm in R.get('staves', {}):
            got, meas, unsung = split_part(part, R['staves'][nm], R.get('overrides', []), bar_no)
            report['unsung'][nm] = [f'bar {b} at {on} midi {p}' + (' (cue)' if c else '') for b, on, p, c in unsung]
            order = [s for g in R['staves'][nm] for s in g] + [s for s in got if s not in {x for g in R['staves'][nm] for x in g}]
            for s in order:
                if keep and s not in keep: continue
                k += 1; pid = f'P{k}'
                new_parts.append(build_part(part, meas, got[s], pid))
                e = copy.deepcopy(sp); e.set('id', pid); e.find('part-name').text = s
                for t in ('part-abbreviation',):
                    for x in e.findall(t): e.remove(x)
                new_sp.append(e)
        else:
            k += 1; pid = f'P{k}'
            p2 = copy.deepcopy(part); p2.set('id', pid)
            e = copy.deepcopy(sp); e.set('id', pid); e.find('part-name').text = R.get('rename', {}).get(nm, nm)
            new_parts.append(p2); new_sp.append(e)
    for x in list(plist):
        if x.tag == 'score-part': plist.remove(x)
    for e in new_sp: plist.append(e)
    for p in root.findall('part'): root.remove(p)
    for p in new_parts: root.append(p)
    out = at(R['out'])
    tree.write(out, encoding='UTF-8', xml_declaration=True)

    # every note written is a note of the stamped file: same bar, onset, pitch, length and syllable
    src_root = ET.parse(src).getroot()
    src_names = {sp.get('id'): sp.findtext('part-name') for sp in src_root.iter('score-part')}
    src_notes = {}
    for part in src_root.findall('part'):
        nm = src_names[part.get('id')]
        for mi, M in enumerate(read_events(part)):
            for v in M['voices']:
                for ev in M['voices'][v]:
                    if ev['rest']: continue
                    L = next((syllable(x) for x in ev['notes'] if syllable(x) is not None), None)
                    for n in ev['notes']:
                        src_notes.setdefault(nm, set()).add((mi, ev['on'], midi(n), ev['dur']))
    staff_of = {}
    for nm, groups in R.get('staves', {}).items():
        for g in groups:
            for s in g: staff_of[s] = nm
    for o in R.get('overrides', []): staff_of[o['singer']] = staff_of.get(o.get('base', o['as']), staff_of.get(o['as']))
    inv = {v: k_ for k_, v in R.get('rename', {}).items()}
    out_root = ET.parse(out).getroot()
    out_names = {sp.get('id'): sp.findtext('part-name') for sp in out_root.iter('score-part')}
    bad = []
    for part in out_root.findall('part'):
        nm = out_names[part.get('id')]
        srcnm = staff_of.get(nm, inv.get(nm, nm))
        for mi, on, p, d, w in line_of(part):
            report['checked'] += 1
            if (mi, on, p, d) not in src_notes.get(srcnm, set()):
                bad.append(f'{nm} bar {bar_no[mi]} at {on}: midi {p} length {d} is not in {srcnm}')
    if bad:
        print('\n'.join(bad)); sys.exit(f'{len(bad)} notes not in the stamped file; {out} written but not recorded')
    print(f'{report["checked"]} notes written, every one in the stamped file')
    for nm, u in report['unsung'].items():
        print(f'{nm}: {len(u)} stamped notes no map voice sings' + (': ' + '; '.join(u) if u else ''))

    if a.old:
        old_root = ET.parse(at(a.old)).getroot()
        old_names = {sp.get('id'): sp.findtext('part-name') for sp in old_root.iter('score-part')}
        old = {old_names[p.get('id')]: line_of(p) for p in old_root.findall('part')}
        new = {out_names[p.get('id')]: line_of(p) for p in out_root.findall('part')}
        ob = numbers(old_root)
        report['diff'] = {}
        for nm in new:
            if nm not in old: print(f'{nm}: not in the old file'); continue
            A = {(ob[x[0]] if x[0] < len(ob) else x[0], x[1]): x for x in old[nm]}
            B = {(bar_no[x[0]], x[1]): x for x in new[nm]}
            diffs = []
            for key in sorted(set(A) | set(B), key=lambda t: (int(''.join(c for c in str(t[0]) if c.isdigit()) or 0), t[1])):
                x, y = A.get(key), B.get(key)
                fx = None if x is None else (x[2], x[3], x[4])
                fy = None if y is None else (y[2], y[3], y[4])
                if fx != fy: diffs.append(f'bar {key[0]} at {key[1]}: old {fx}, new {fy}')
            report['diff'][nm] = diffs
            print(f'{nm}: {len(diffs)} differences from the old file' + ''.join('\n    ' + d for d in diffs[:60]) +
                  (f'\n    ... {len(diffs) - 60} more' if len(diffs) > 60 else ''))
        for nm in old:
            if nm not in new: print(f'{nm}: in the old file, not written')
    json.dump(dict(source=os.path.relpath(src, os.path.dirname(out)), source_sha256=sha(src), sha256=sha(out),
                   rules=R, written=datetime.datetime.now().isoformat(timespec='seconds'), checked=report['checked'],
                   unsung=report['unsung'], diff=report.get('diff')),
              open(out + '.derived.json', 'w'), indent=1)
    print(f'wrote {out} and its record')


if __name__ == '__main__':
    main()
