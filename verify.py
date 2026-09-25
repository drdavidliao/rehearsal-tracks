#!/usr/bin/env python3
"""Run every Step 5 check on a finished MusicXML and print one line per check.

    python3 verify.py score.musicxml [--pdf score.pdf] [--lanes "0a=Tenor,0b=Lead,1a=Baritone,1b=Bass"]
                      [--original before.musicxml] [--render out_dir] [--xsd schema_dir]

Every check ends as one of
    PASS      checked, nothing found
    FAIL      checked, something to fix (details follow the table)
    WARN      checked, something to look at
    MANUAL    needs a person; the line says what to look at
    N/A       does not apply to this file (the line says why)
    NOT RUN   could not run; the line says what input is missing

Paste the table into the handback as printed. A check that did not run is
reported as NOT RUN, never left out: an empty result and a check nobody ran look
the same in the output, and that is how check 10 was once skipped.

--pdf enables the checks that compare against the engraving (6, 10, 11, 12, 17).
--original is the file this one was made from: the score before a revoicing (check 16),
or the open score a closed score was collapsed from, with its printed words, not a Cantai
learning file, which re-sings melismas (check 14: lines under notes whose words moved to
the other line).
--lanes says which part each lyric line of the PDF belongs to: `<staff>a` is
the line above that staff of a system, `<staff>b` the line below, staves counted
from 0 within a system. Default when the PDF has one staff per part: `<k>b` is
part k. A closed score (two parts to a staff) needs --lanes.

Needs lxml; pdfplumber with --pdf; verovio and cairosvg with --render.
Exit status 1 if any check FAILs.
"""
import sys, os, re, argparse, subprocess, difflib, statistics
from collections import defaultdict
from fractions import Fraction as F
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = 'https://raw.githubusercontent.com/w3c/musicxml/v4.0/schema/'
MUSIC_FONTS = ('Opus', 'Helsinki', 'Maestro', 'Sonata', 'Petrucci', 'Emmentaler', 'Bravura',
               'Leland', 'November', 'Leipzig', 'Finale', 'Engraver')
STEPS = 'CDEFGAB'

results = []          # (number, name, status, summary)
details = defaultdict(list)


def report(n, name, status, summary, lines=()):
    results.append((n, name, status, summary))
    details[n].extend(lines)


# ----------------------------------------------------------------- the MusicXML

def load(path):
    root = ET.parse(path).getroot()
    names = {sp.get('id'): (sp.findtext('part-name') or sp.get('id')).strip() for sp in root.iter('score-part')}
    return root, names


def notes_of(part):
    """[(measure number, note element, voice, onset in quarters from the bar line)] in file order."""
    out, div = [], 1
    for m in part.findall('measure'):
        pos = {}
        t = F(0)
        for e in m:
            if e.tag == 'attributes' and e.find('divisions') is not None:
                div = int(e.findtext('divisions'))
            elif e.tag == 'backup':
                t -= F(int(e.findtext('duration')), div)
            elif e.tag == 'forward':
                t += F(int(e.findtext('duration')), div)
            elif e.tag == 'note':
                d = F(int(e.findtext('duration') or 0), div)
                if e.find('chord') is not None:
                    out.append((m.get('number'), e, e.findtext('voice') or '1', out[-1][3] if out else t))
                    continue
                out.append((m.get('number'), e, e.findtext('voice') or '1', t))
                if e.find('grace') is None:
                    t += d
    return out


def pitch_midi(p):
    return 12 * (int(p.findtext('octave')) + 1) + [0, 2, 4, 5, 7, 9, 11][STEPS.index(p.findtext('step'))] + int(float(p.findtext('alter') or 0))


def pname(midi):
    return ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'][midi % 12] + str(midi // 12 - 1)


# ----------------------------------------------------------------- checks on the file alone

def check_xsd(path, xsd_dir):
    try:
        from lxml import etree
    except ImportError:
        return report(1, 'XSD', 'NOT RUN', 'lxml not installed')
    xsd_dir = xsd_dir or os.path.join(HERE, '.musicxml-schema')
    os.makedirs(xsd_dir, exist_ok=True)
    main = os.path.join(xsd_dir, 'musicxml.xsd')
    try:
        for f in ('musicxml.xsd', 'xml.xsd', 'xlink.xsd'):
            dst = os.path.join(xsd_dir, f)
            if not os.path.exists(dst):
                import urllib.request
                urllib.request.urlretrieve(SCHEMA + f, dst)
        s = open(main).read()
        s2 = re.sub(r'schemaLocation="[^"]*/(xml|xlink)\.xsd"', r'schemaLocation="\1.xsd"', s)
        if s2 != s: open(main, 'w').write(s2)
        schema = etree.XMLSchema(etree.parse(main))
    except Exception as ex:
        return report(1, 'XSD', 'NOT RUN', f'schema unavailable ({ex.__class__.__name__}); pass --xsd DIR with musicxml.xsd, xml.xsd, xlink.xsd')
    ok = schema.validate(etree.parse(path))
    report(1, 'XSD', 'PASS' if ok else 'FAIL', 'valid MusicXML 4.0' if ok else f'{len(schema.error_log)} schema error(s)',
           [str(e) for e in list(schema.error_log)[:10]])


def check_bars(root, names):
    bad = []
    for part in root.findall('part'):
        div, ts = 1, None
        for m in part.findall('measure'):
            for a in m.findall('attributes'):
                if a.find('divisions') is not None: div = int(a.findtext('divisions'))
                if a.find('time') is not None:
                    ts = (int(a.find('time').findtext('beats')), int(a.find('time').findtext('beat-type')))
            pos = mx = F(0)
            for e in m:
                if e.tag == 'note' and e.find('chord') is None and e.find('grace') is None:
                    pos += F(int(e.findtext('duration')), div)
                elif e.tag == 'backup': pos -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward': pos += F(int(e.findtext('duration')), div)
                mx = max(mx, pos)
            if ts and m.get('implicit') != 'yes' and mx != F(ts[0] * 4, ts[1]):
                bad.append(f"{names[part.get('id')]} bar {m.get('number')}: {mx} quarters in {ts[0]}/{ts[1]}")
    report(2, 'Bar lengths', 'FAIL' if bad else 'PASS', f'{len(bad)} bar(s) off' if bad else 'every bar fills its meter', bad)


RANGES = [  # (name keyword, lowest, highest) sounding, generous
    ('sop', 'A3', 'C6'), ('alt', 'E3', 'F5'), ('ten', 'B2', 'C5'), ('lead', 'A2', 'A4'),
    ('bari', 'F2', 'F4'), ('bass', 'C2', 'E4')]


def midi_of(name):
    m = re.fullmatch(r'([A-G])(b|#)?(-?\d)', name)
    return 12 * (int(m.group(3)) + 1) + [0, 2, 4, 5, 7, 9, 11][STEPS.index(m.group(1))] + {'b': -1, '#': 1, None: 0}[m.group(2)]


def check_ranges(root, names):
    lines, status = [], 'PASS'
    for part in root.findall('part'):
        ps = [pitch_midi(n.find('pitch')) for _, n, _, _ in notes_of(part) if n.find('pitch') is not None]
        if not ps: continue
        nm = names[part.get('id')]
        lo, hi = min(ps), max(ps)
        rule = next((r for r in RANGES if r[0] in nm.lower()), None)
        verdict = ''
        if rule:
            a, b = midi_of(rule[1]), midi_of(rule[2])
            if lo < a - 11 or hi > b + 11:
                verdict = '  <- an octave outside the usual range: octave/clef error?'; status = 'FAIL'
            elif lo < a or hi > b:
                verdict = f'  <- outside {rule[1]}-{rule[2]}'; status = 'WARN' if status == 'PASS' else status
        lines.append(f'{nm}: {pname(lo)}-{pname(hi)}{verdict}')
    report(3, 'Ranges', status, '; '.join(l.split('  <-')[0] for l in lines), [l for l in lines if '<-' in l])


def check_qc(path):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'musicxml_qc.py'), path], capture_output=True, text=True)
    cats = [l.strip() for l in r.stdout.splitlines() if re.match(r'\s+\S.*: \d+$', l)]
    bad = [c for c in cats if not c.endswith(': 0')]
    report(4, 'musicxml_qc.py', 'FAIL' if bad else 'PASS', '; '.join(bad) if bad else 'clean',
           [l for l in r.stdout.splitlines()[2:] if l.strip()] if bad else [])


def check_render(path, out):
    if not out:
        return report(5, 'Render vs PDF', 'MANUAL', 'pass --render DIR to write page images, then compare them with the PDF page by page')
    try:
        import verovio, cairosvg
    except ImportError:
        return report(5, 'Render vs PDF', 'NOT RUN', 'verovio / cairosvg not installed')
    os.makedirs(out, exist_ok=True)
    tk = verovio.toolkit()
    tk.setOptions({'pageWidth': 2159, 'pageHeight': 2794, 'unit': 8, 'breaks': 'auto', 'adjustPageHeight': True})
    tk.loadFile(path)
    for i in range(1, tk.getPageCount() + 1):
        cairosvg.svg2png(bytestring=tk.renderToSVG(i).encode(), write_to=os.path.join(out, f'page{i}.png'),
                         output_width=1400, background_color='white')
    report(5, 'Render vs PDF', 'MANUAL', f'{tk.getPageCount()} page(s) in {out}/ - compare with the PDF, page by page')


def check_ties(root, names):
    bad = []
    for part in root.findall('part'):
        # events per voice, a chord being one event: a tie on any chord member must meet the same
        # pitch, carrying the stop, in the voice's next event (a tie on the upper note of a chord was
        # once compared with the next chord's lowest note)
        byv = defaultdict(list)
        for mn, n, v, _ in notes_of(part):
            if n.find('chord') is not None and byv[v]:
                byv[v][-1][1].append(n)
            else:
                byv[v].append((mn, [n]))
        def ties_of(ns, kind):
            return {pitch_midi(x.find('pitch')) for x in ns if x.find('pitch') is not None
                    and kind in {t.get('type') for t in x.findall('tie')}}
        for v, seq in byv.items():
            for i, (mn, ns) in enumerate(seq):
                for p in ties_of(ns, 'start'):
                    nxt = seq[i + 1][1] if i + 1 < len(seq) else []
                    if p not in ties_of(nxt, 'stop'):
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: tie start with no matching stop")
                for p in ties_of(ns, 'stop'):
                    prv = seq[i - 1][1] if i else []
                    if p not in ties_of(prv, 'start'):
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: tie stop with no start")
        # slurs: each start closed by the next stop of the same number, in the same voice. On a shared
        # staff a slur that starts in voice 2 and ends on a note merged into a voice-1 chord is closed
        # by nothing: the chord's one stop closes the upper part's slur, and the lower part's is drawn
        # on to whatever stop comes next, bars later (SKILL.md 7.2)
        open_ = {}
        for mn, n, v, _ in notes_of(part):
            for sl in n.iter('slur'):
                num, typ = sl.get('number') or '1', sl.get('type')
                if typ == 'start':
                    if num in open_:
                        bad.append(f"{names[part.get('id')]} bar {open_[num][0]}: slur {num} (voice {open_[num][1]}) "
                                   f"never closed before another starts in bar {mn}")
                    open_[num] = (mn, v)
                elif typ == 'stop':
                    if num not in open_:
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: slur {num} stop with no start")
                    elif open_[num][1] != v:
                        bad.append(f"{names[part.get('id')]} bar {open_[num][0]}-{mn}: slur {num} starts in voice "
                                   f"{open_[num][1]} and stops in voice {v}")
                    open_.pop(num, None)
        for num, (mn, v) in open_.items():
            bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: slur {num} never closed")
    report(8, 'Ties and slurs pair up', 'FAIL' if bad else 'PASS', f'{len(bad)} unpaired' if bad else
           'every tie and slur pairs', bad)


def check_words(root, names, out_dir):
    bad, words = [], []
    for part in root.findall('part'):
        cur = {}
        for mn, n, v, _ in notes_of(part):
            for l in n.findall('lyric'):
                k = (v, l.get('number', '1'))
                syl, txt = l.findtext('syllabic') or 'single', l.findtext('text') or ''
                if syl in ('single', 'begin'):
                    if k in cur: bad.append(f"{names[part.get('id')]} bar {mn}: word {cur[k][1]!r} never ended")
                    cur[k] = (mn, txt)
                elif k not in cur:
                    bad.append(f"{names[part.get('id')]} bar {mn}: {syl} syllable {txt!r} with no word start")
                    cur[k] = (mn, txt)
                else:
                    cur[k] = (cur[k][0], cur[k][1] + txt)
                if syl in ('single', 'end') and k in cur:
                    words.append(f"{names[part.get('id')]} bar {cur[k][0]}: {cur[k][1]}")
                    del cur[k]
        for k, (mn, w) in cur.items():
            bad.append(f"{names[part.get('id')]} bar {mn}: word {w!r} never ended")
    fn = os.path.join(out_dir, 'words.txt')
    open(fn, 'w').write('\n'.join(words) + '\n')
    if bad:
        report(9, 'Words reassemble', 'FAIL', f'{len(bad)} broken hyphen chain(s)', bad)
    else:
        report(9, 'Words reassemble', 'MANUAL', f'hyphen chains all close; read the {len(words)} words in {fn} for typos')


def sung_positions(root, only=None):
    """{(bar, onset, midi)} where a note of `root` starts a syllable: which notes of a derived score
    (a closed score, a revoicing) sing a syllable of their own, whatever line prints it. `only`: the
    part names to take, those sharing the staff being checked (a soloist singing the same pitch at
    the same moment is not the tenors' word)."""
    out = set()
    names = {sp.get('id'): (sp.findtext('part-name') or '').strip() for sp in root.iter('score-part')}
    for part in root.findall('part'):
        if only is not None and names.get(part.get('id')) not in only:
            continue
        for mn, n, v, t in notes_of(part):
            if n.find('pitch') is not None and any(l.findtext('text') for l in n.findall('lyric')):
                out.add((mn, t, pitch_midi(n.find('pitch'))))
    return out


def parts_on(staff_name, source_names):
    """The source parts a derived staff carries, by name ("Tenor 1\nTenor 2", "Tenor 1 + Tenor 2");
    all of them when the name does not say."""
    got = {n for n in source_names if n and re.search(r'(^|[\n+/&,])\s*' + re.escape(n) + r'\s*($|[\n+/&,])', staff_name)}
    return got or set(source_names)


def lyric_line_runs(part, sung=frozenset()):
    """Each lyric line as an engraver draws it: from a syllable with <extend/> on to the next note in
    the same voice with a syllable on that line, over every syllable-less note between, rests or no
    (SKILL.md 7.6). A line is wrong when a note under it comes after a printed rest, or sings a
    syllable of its own (`sung`, from the source) that is printed on the other line (7.4).
    Returns [(bar, voice, line, text, bar it runs to, why)]."""
    byv = defaultdict(list)
    for mn, n, v, t in notes_of(part):
        if n.find('chord') is None and n.find('grace') is None:
            byv[v].append((mn, n, t))
    out = []
    for v, seq in byv.items():
        for i, (mn, n, _) in enumerate(seq):
            for l in n.findall('lyric'):
                e = l.find('extend')
                if e is None or e.get('type') == 'stop' or not l.findtext('text'):
                    continue
                num = l.get('number') or '1'
                rest, last, why = False, None, ''
                for mn2, n2, t2 in seq[i + 1:]:
                    if any((l2.get('number') or '1') == num for l2 in n2.findall('lyric')):
                        break                                   # the next syllable on the line ends it
                    if n2.find('rest') is not None:
                        rest = rest or n2.get('print-object') != 'no'
                        continue
                    p2 = n2.find('pitch')
                    held = any(x.get('type') == 'stop' for x in n2.findall('tie'))   # a tied note begins no word
                    own = p2 is not None and not held and (mn2, t2, pitch_midi(p2)) in sung
                    if rest or own:
                        last, why = mn2, 'past a rest' if rest else 'under notes that sing their own words'
                if last is not None:
                    out.append((mn, v, num, l.findtext('text'), last, why))
    return out


def check_extend_runs(root, names, original=None):
    """14: an <extend/> needs a following note in the same voice for the line to run under, and the
    line must stop where the melisma does (SKILL.md 7.6)."""
    bad = []
    oroot, onames = load(original) if original else (None, {})
    for part in root.findall('part'):
        sung = sung_positions(oroot, parts_on(names[part.get('id')], onames.values())) if original else frozenset()
        byv = defaultdict(list)
        for mn, n, v, _ in notes_of(part):
            if n.find('chord') is None: byv[v].append((mn, n))
        for v, seq in byv.items():
            for i, (mn, n) in enumerate(seq):
                for l in n.findall('lyric'):
                    e = l.find('extend')
                    if e is None or e.get('type') == 'stop': continue
                    nxt = seq[i + 1][1] if i + 1 < len(seq) else None
                    if nxt is None or nxt.find('rest') is not None or nxt.find('lyric') is not None:
                        bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: {l.findtext('text')!r} extends over no note")
                    if (l.findtext('syllabic') or 'single') in ('begin', 'middle'):
                        # mid-word: a line over a melisma of moving notes, a hyphen over a tie-only hold (2.5)
                        held = []
                        for _, n2 in seq[i + 1:]:
                            if n2.find('rest') is not None or n2.find('lyric') is not None: break
                            held.append(n2)
                        if held and all(any(t.get('type') == 'stop' for t in n2.findall('tie')) for n2 in held):
                            bad.append(f"{names[part.get('id')]} voice {v} bar {mn}: {l.findtext('text')!r} is mid-word "
                                       f"and held only by a tie; it prints a hyphen, and an extender would replace it")
        for mn, v, num, text, last, why in lyric_line_runs(part, sung):
            bad.append(f"{names[part.get('id')]} voice {v} line {num}: the line from {text!r} (bar {mn}) runs on "
                       f"to bar {last}, {why}")
    report(14, 'No extender outruns its voice', 'FAIL' if bad else 'PASS', f'{len(bad)} problem(s)' if bad else
           'every extender has notes under it and stops where its melisma does' +
           ('' if original else ' (lines under notes whose words moved to the other line need --original)'), bad)


def multi_voice_staves(root):
    for part in root.findall('part'):
        vs = {n.findtext('voice') for n in part.iter('note') if n.find('rest') is None}
        if len(vs) > 1: return True
    return False


def check_shared_staff(root):
    if not multi_voice_staves(root):
        return report(13, 'Shared-staff lyric reads', 'N/A', 'no staff carries two voices')
    report(13, 'Shared-staff lyric reads', 'MANUAL',
           'staves carry two voices: rebuild each singer\'s read (line 2 where it has its own note, line 1 where shared) '
           'and compare with that voice\'s syllables (SKILL.md 7.4)')


def check_layout(path, root):
    if root.find('.//print[@new-system="yes"]') is None and root.find('.//print[@new-page="yes"]') is None:
        return report(15, 'Lyric collisions', 'N/A', 'no print layout in the file (no system or page breaks)')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'lyric_collisions.py'), path], capture_output=True, text=True)
    m = re.search(r'(\d+) overlapping', r.stdout)
    n = int(m.group(1)) if m else -1
    report(15, 'Lyric collisions', 'PASS' if n == 0 else ('FAIL' if n > 0 else 'NOT RUN'),
           f'{n} overlapping pair(s)' if n >= 0 else 'lyric_collisions.py failed', r.stdout.splitlines()[1:21])


def check_original(root, names, original):
    if not original:
        return report(16, 'Revoicing vs original', 'N/A', 'no --original given (not a revoicing)')
    oroot, onames = load(original)
    def grid(r, nm):
        g = defaultdict(set)
        for part in r.findall('part'):
            for mn, n, v, t in notes_of(part):
                if n.find('pitch') is not None:
                    g[(mn, t)].add(pitch_midi(n.find('pitch')) % 12)
        return g
    a, b = grid(oroot, onames), grid(root, names)
    diff = sorted({k[0] for k in set(a) | set(b) if a.get(k) != b.get(k)}, key=lambda x: int(re.sub(r'\D', '', x) or 0))
    report(16, 'Revoicing vs original', 'MANUAL' if diff else 'PASS',
           f'pitch classes differ in {len(diff)} bar(s); each must be on the instruction list' if diff else 'same pitch classes at every onset',
           [f'bars: {", ".join(diff)}'] if diff else [])


# ----------------------------------------------------------------- checks against the PDF

def staves_of(page):
    hs = sorted((l for l in page.lines if abs(l['y0'] - l['y1']) < 0.6 and (l['x1'] - l['x0']) > 150), key=lambda l: l['top'])
    tops = []
    for l in hs:
        if not tops or abs(l['top'] - tops[-1][0]) > 0.3: tops.append((l['top'], l['x0'], l['x1']))
    st, i = [], 0
    while i <= len(tops) - 5:
        w = [t[0] for t in tops[i:i + 5]]
        g = [w[j + 1] - w[j] for j in range(4)]
        if max(g) - min(g) < 0.2 and g[0] > 1.0:
            st.append({'lines': w, 'x0': tops[i][1], 'x1': tops[i][2]}); i += 5
        else:
            i += 1
    return st


def systems_of(page, st):
    """group staves into systems by the vertical line that joins them at the left edge"""
    if not st: return []
    sh = st[0]['lines'][4] - st[0]['lines'][0]
    joins = set()
    for l in page.lines:
        if abs(l['x0'] - l['x1']) > 0.8 or l['bottom'] - l['top'] < sh * 1.6: continue
        idx = tuple(k for k, s in enumerate(st) if l['top'] - 1 <= s['lines'][0] and s['lines'][4] <= l['bottom'] + 1)
        if len(idx) >= 2: joins.add(idx)
    groups, used = [], set()
    for idx in sorted(joins, key=len, reverse=True):
        if used & set(idx): continue
        groups.append(list(idx)); used |= set(idx)
    for k in range(len(st)):
        if k not in used: groups.append([k])
    groups.sort()
    return [[st[k] for k in g] for g in groups]


def is_ledger(l, st, p):
    """a short line on a staff's ledger grid with a notehead over it"""
    if not st or l['x1'] - l['x0'] > 20: return False
    s = min(st, key=lambda s: abs((s['lines'][0] + s['lines'][4]) / 2 - l['top']))
    sp = (s['lines'][4] - s['lines'][0]) / 4
    edge = s['lines'][0] if l['top'] < s['lines'][0] else s['lines'][4]
    k = abs(l['top'] - edge) / sp
    if abs(k - round(k)) > 0.15 or round(k) < 1 or round(k) > 6: return False
    mid = lambda t: (t['lines'][0] + t['lines'][4]) / 2
    for c in p.chars:
        if any(f in c['fontname'] for f in MUSIC_FONTS) and (ord(c['text'][0]) in HEADS or c['text'] == 'w') \
                and c['x0'] < l['x1'] and c['x1'] > l['x0'] and abs((p.height - c['matrix'][5]) - l['top']) <= 4 * sp:
            # the notehead must belong to the same staff: an extender between two staves can sit on
            # the upper staff's ledger grid right over a note of the lower staff (a TTBB with piano)
            y = p.height - c['matrix'][5]
            if min(st, key=lambda t: abs(mid(t) - y)) is s:
                return True
    return False


class Engraving:
    def __init__(self, path, lyric_font=None, lyric_size=None):
        import pdfplumber
        self.pages = []
        with pdfplumber.open(path) as pdf:
            from collections import Counter
            text = Counter()
            for p in pdf.pages:
                for c in p.chars:
                    if not any(f in c['fontname'] for f in MUSIC_FONTS) and c['text'].isalpha():
                        text[(c['fontname'], round(c['size'], 1))] += 1
            lf = text.most_common(1)[0][0] if text else (None, None)
            self.lyric_font = lyric_font or lf[0]
            self.lyric_size = lyric_size or lf[1]
            for p in pdf.pages:
                st = staves_of(p)
                sysl = systems_of(p, st)
                self.pages.append({
                    'n': p.page_number, 'height': p.height, 'systems': sysl,
                    'sp': statistics.median([(s['lines'][4] - s['lines'][0]) / 4 for s in st]) if st else 4.0,
                    'chars': [dict(t=c['text'], x0=c['x0'], x1=c['x1'], top=c['top'], font=c['fontname'],
                                   size=round(c['size'], 1), y=p.height - c['matrix'][5]) for c in p.chars],
                    'hlines': [(l['x0'], l['x1'], l['top']) for l in p.lines
                               if abs(l['y0'] - l['y1']) < 0.3 and l['x1'] - l['x0'] > 2
                               and not any(abs(l['top'] - y) < 0.3 for s in st for y in s['lines'])
                               and not is_ledger(l, st, p)],
                    'vlines': [(l['x0'], l['top'], l['bottom']) for l in p.lines if abs(l['x0'] - l['x1']) < 0.3],
                })

    def home(self, page, y):
        """(system index, lane) for a mark at height y: lane '<staff>a' above that staff, '<staff>b' below."""
        best = None
        for si, sy in enumerate(page['systems']):
            top, bot = sy[0]['lines'][0], sy[-1]['lines'][4]
            d = top - y if y < top else (y - bot if y > bot else 0)
            if best is None or d < best[0]: best = (d, si)
        if best is None: return None, None
        d, si = best
        sy = page['systems'][si]
        for k, s in enumerate(sy):
            if s['lines'][0] <= y <= s['lines'][4]: return si, None     # inside a staff
        for k, s in enumerate(sy):
            if y < s['lines'][0]:
                if k == 0: return si, f'{k}a'
                prev = sy[k - 1]['lines'][4]
                return si, (f'{k - 1}b' if y - prev < s['lines'][0] - y else f'{k}a')
        return si, f'{len(sy) - 1}b'

    def lyric_rows(self):
        """-> [(page idx, system idx, lane, top, [syllable dicts])] in reading order."""
        out = []
        for pi, page in enumerate(self.pages):
            # the lyric font at its size, or a page scaled a few percent (Finale scales pages one by one:
            # a TTBB with piano set its last two pages' lyrics at 12.1 pt against 11.5)
            cs = [c for c in page['chars'] if c['font'] == self.lyric_font
                  and 0.92 * self.lyric_size <= c['size'] <= 1.09 * self.lyric_size]
            rows = []
            for c in sorted(cs, key=lambda c: c['top']):
                for r in rows:
                    if abs(r[0] - c['top']) < 1.0: r[1].append(c); break
                else: rows.append([c['top'], [c]])
            for top, chars in rows:
                si, lane = self.home(page, top + 0.75 * self.lyric_size)
                if si is None or lane is None: continue
                sy = page['systems'][si]
                if top < sy[0]['lines'][0] - 12 * page['sp'] or top > sy[-1]['lines'][4] + 12 * page['sp']: continue
                syl = syllables(chars)
                for x in syl: x['top'] = top
                out.append((pi, si, lane, top, syl))
        # one lane can be set at two heights in one system (a phrase nudged down to clear
        # something): merge them and read left to right
        merged = {}
        for pi, si, lane, top, syl in out:
            merged.setdefault((pi, si, lane), [pi, si, lane, top, []])[4].extend(syl)
        out = []
        for r in merged.values():
            r[4].sort(key=lambda x: x['x0'])
            r[3] = min(x['top'] for x in r[4])
            out.append(tuple(r))
        out.sort(key=lambda r: (r[0], r[1], r[3]))
        return out


def syllables(chars):
    chars = sorted(chars, key=lambda c: c['x0'])
    toks = []
    for c in chars:
        if toks and c['x0'] - toks[-1]['x1'] < 0.25 and c['t'] != '-' and not toks[-1]['t'].endswith('-'):
            toks[-1]['t'] += c['t']; toks[-1]['x1'] = c['x1']
        else:
            toks.append({'t': c['t'], 'x0': c['x0'], 'x1': c['x1']})
    out = []
    for t in toks:
        if not t['t'].strip(): continue
        if t['t'] == '-': continue
        out.append(t)
    return out


def check_instructions(pdf):
    if not pdf:
        return report(6, 'Performer instructions', 'NOT RUN', 'needs --pdf')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'find_performer_instructions.py'), pdf], capture_output=True, text=True)
    hits = [l.strip() for l in r.stdout.splitlines()[1:] if l.strip().startswith('p')]
    if not hits:
        return report(6, 'Performer instructions', 'PASS', 'none found (italic scan); rerun find_performer_instructions.py --all-text if the engraving sets them upright')
    report(6, 'Performer instructions', 'MANUAL', f'{len(hits)} found: each needs a rule and a stated scope', hits)


def check_extender_lines(root, names, E, lanes):
    """10: every printed extension line is consumed by exactly one syllable, and every <extend/>
    on a syllable the PDF prints for that part has a printed line behind it.

    A line that runs to the right margin carries on at the start of the next system. Where that
    leading segment is drawn vertically varies by engraver (Finale puts it just above the staff
    whichever lyric line it continues), so leading segments are paired with the lines that ran
    off the previous system by count and vertical order, not by lane."""
    rows = E.lyric_rows()
    unknown = sorted({r[2] for r in rows if r[2] not in lanes})
    size = E.lyric_size
    printed = defaultdict(list)       # part name -> [[text, has_line, where]]
    consumed = set()
    runs = defaultdict(list)          # (page, system) -> [(y, entry, needs_continuation)]
    for pi, si, lane, top, syls in rows:
        if lane not in lanes: continue
        page = E.pages[pi]; sp = page['sp']
        right = page['systems'][si][0]['x1']
        for k, s in enumerate(syls):
            band = [ln for ln in page['hlines'] if s['top'] + 0.35 * size <= ln[2] <= s['top'] + 1.5 * size and ln[1] - ln[0] > 2.25 * sp]
            hit = [ln for ln in band if s['x1'] - 1 <= ln[0] <= s['x1'] + 2.5 * sp]
            for ln in hit: consumed.add((pi, tuple(ln)))
            entry = [s['t'], bool(hit), f"p{page['n']} system {si + 1}"]
            printed[lanes[lane]].append(entry)
            if any(ln[1] > right - 3 for ln in hit):
                runs[(pi, si)].append((s['top'], entry, False))
            elif not hit and k == len(syls) - 1 and s['x1'] > right - 12 * sp:
                runs[(pi, si)].append((s['top'], entry, True))    # its whole line may be on the next system
    bad = []
    for pi, page in enumerate(E.pages):
        sp = page['sp']
        tops = sorted({x['top'] for r in rows if r[0] == pi for x in r[4]})
        for si, sy in enumerate(page['systems']):
            left = sy[0]['x0']
            lead = sorted((ln for ln in page['hlines'] if ln[1] - ln[0] > 2.25 * sp and ln[0] < left + 15 * sp
                           and E.home(page, ln[2])[0] == si and (pi, tuple(ln)) not in consumed), key=lambda ln: ln[2])
            prev = [k for k in runs if next_system(E, *k) == (pi, si)]
            ran = sorted(runs[prev[0]], key=lambda r: r[0]) if prev else []
            must = [r for r in ran if not r[2]]
            maybe = [r for r in ran if r[2]]
            if len(lead) < len(must):
                pass                                  # a line may end exactly at the margin
            extra = len(lead) - len(must)
            for r in maybe[:max(extra, 0)]:
                r[1][1] = True                        # its line is the leading segment here
            for ln in lead[:len(must) + len(maybe)]:
                consumed.add((pi, tuple(ln)))
        for ln in page['hlines']:
            if ln[1] - ln[0] <= 2.25 * sp or (pi, tuple(ln)) in consumed: continue
            si, lane = E.home(page, ln[2])
            in_band = any(t + 0.35 * size <= ln[2] <= t + 1.5 * size for t in tops)
            at_left = si is not None and lane is not None and ln[0] < page['systems'][si][0]['x0'] + 15 * sp
            if in_band or at_left:
                bad.append(f"p{page['n']}: printed line x{ln[0]:.0f}-{ln[1]:.0f} y{ln[2]:.0f} belongs to no syllable")
    # compare with the MusicXML, part by part, by aligning the syllable texts
    matched = skipped = 0
    for part in root.findall('part'):
        nm = names[part.get('id')]
        if nm not in printed: continue
        xs = []
        for mn, n, v, _ in notes_of(part):
            for l in n.findall('lyric'):
                e = l.find('extend')
                slurred = any(x.get('type') == 'start' for x in n.iter('slur'))
                mid = (l.findtext('syllabic') or 'single') in ('begin', 'middle')
                xs.append((l.findtext('text') or '', e is not None and e.get('type') != 'stop', mn, slurred or mid))
        ps = printed[nm]
        sm = difflib.SequenceMatcher(a=[t.strip() for t, _, _ in ps], b=[x[0].strip() for x in xs], autojunk=False)
        blocks = sm.get_matching_blocks()
        for a0, b0, n in blocks:
            for k in range(n):
                t, has, where = ps[a0 + k]
                xt, ext, mn, slurred = xs[b0 + k]
                matched += 1
                if ext and not has and slurred:
                    continue          # a slurred or mid-word melisma keeps its line even where none is printed (SKILL.md 2.5)
                if has != ext:
                    bad.append(f"{nm} bar {mn} {xt!r}: PDF {'prints' if has else 'has no'} extension line, "
                               f"file {'has' if ext else 'has no'} <extend/>")
        skipped += len(xs) - sum(b[2] for b in blocks)
        lost = len(ps) - sum(b[2] for b in blocks)
        if lost:
            bad.append(f"{nm}: {lost} printed syllable(s) could not be matched to the file's lyrics - a missing or misspelt syllable?")
    if unknown:
        bad.append(f"lyric lines in lanes {unknown} have no part: add them to --lanes")
    summary = (f'{matched} printed syllables compared, {len(bad)} disagreement(s)'
               + (f'; {skipped} syllable(s) in the file are not printed for that part (copied from another line), not compared' if skipped else ''))
    report(10, 'Extension lines match the PDF', 'FAIL' if bad else 'PASS', summary, bad)


def next_system(E, pi, si):
    if si + 1 < len(E.pages[pi]['systems']): return pi, si + 1
    for q in range(pi + 1, len(E.pages)):
        if E.pages[q]['systems']: return q, 0
    return None


HEADS = {0xF0CF, 0xF0FA, 0xF077, 0x153, 0x2D9, 0xE0A2, 0xE0A3, 0xE0A4}


def check_grid(E):
    """12: every notehead sits a whole number of half staff spaces from its staff's top line."""
    offs = []
    for page in E.pages:
        sp = page['sp']
        st = [s for sy in page['systems'] for s in sy]
        for c in page['chars']:
            if not any(f in c['font'] for f in MUSIC_FONTS): continue
            code = ord(c['t'][0])
            if code not in HEADS and not (c['t'] == 'w' and 'Helsinki' in c['font']): continue
            s = min(st, key=lambda s: abs((s['lines'][0] + s['lines'][4]) / 2 - c['y']))
            d = (c['y'] - s['lines'][0]) / (sp / 2)
            offs.append((d, page['n'], c['x0']))
    if not offs:
        return report(12, 'Noteheads on the grid', 'NOT RUN', 'no noteheads recognised (music font not in the list)')
    base = statistics.median([d - round(d) for d, _, _ in offs])      # font baseline offset, if any
    E.grid_base = base
    bad = [f'p{pn} x{x:.0f}: {d - base:.2f} half-spaces' for d, pn, x in offs if abs((d - base) - round(d - base)) > 0.15]
    report(12, 'Noteheads on the grid', 'FAIL' if bad else 'PASS',
           f'{len(offs)} noteheads, {len(bad)} off the grid' + (f' (font offset {base:+.2f})' if abs(base) > 0.05 else ''), bad[:20])


def pdf_bars(E):
    """[(page, system, x from, x to)] for every bar the engraving prints, in reading order.
    A bar is a stretch between two vertical lines that cross every staff of the system; a
    stretch with no note or rest in it is a courtesy key or time at a system's end, and is dropped."""
    out = []
    for page in E.pages:
        sp = page['sp']
        for sy in page['systems']:
            top, bot = sy[0]['lines'][0], sy[-1]['lines'][4]
            cover = defaultdict(set)
            for x, t, b in page['vlines']:
                for k, s in enumerate(sy):
                    if t <= s['lines'][0] + 0.6 and b >= s['lines'][4] - 0.6: cover[round(x)].add(k)
            bars = []
            for x in sorted(x for x, ks in cover.items() if len(ks) == len(sy)):
                if bars and x - bars[-1] < 4: bars[-1] = x; continue
                bars.append(x)
            glyphs = sorted(c['x0'] for c in page['chars'] if any(f in c['font'] for f in MUSIC_FONTS)
                            and top - 6 * sp < c['y'] < bot + 6 * sp
                            and (ord(c['t'][0]) in HEADS | {0xF0E4, 0xF0CE, 0xF0EE, 0xF0C5, 0x2030, 0x152, 0xD3}
                                 or (c['t'] == 'w' and 'Helsinki' in c['font'])))
            for a, b in zip(bars, bars[1:]):
                g = [x for x in glyphs if a + 1 < x < b - 1]
                c = []
                for x in g:
                    if c and x - c[-1][0] < 1.9 * sp: c[-1].append(x)   # a second prints its heads one head-width apart
                    else: c.append([x])
                if c:
                    out.append((page, sy, a, b, len(c)))
    return out


def check_onsets(root, E):
    """11: notes that start together in the file start at one x in the PDF.
    Compares, bar by bar, the number of distinct onsets across all parts with the number of
    distinct note/rest columns the engraving prints."""
    ons = defaultdict(set)
    for part in root.findall('part'):
        for mn, n, v, t in notes_of(part):
            r = n.find('rest')
            if r is not None and r.get('measure') == 'yes': continue
            if n.findtext('type') is None and r is not None: continue
            ons[mn].add(t)
    order = [m.get('number') for m in root.find('part').findall('measure')]
    cols = [c for *_, c in pdf_bars(E)]
    if len(cols) != len(order):
        return report(11, 'Cross-staff onset alignment', 'NOT RUN',
                      f'PDF bar count {len(cols)} does not match the file ({len(order)}); first-bar or pickup layout not understood')
    bad = [f'bar {mn}: {len(ons[mn])} onset(s) in the file, {c} column(s) in the PDF'
           for mn, c in zip(order, cols) if c and len(ons[mn]) != c]
    report(11, 'Cross-staff onset alignment', 'WARN' if bad else 'PASS',
           f'{len(bad)} bar(s) where the file and the engraving disagree on how many attack points there are' if bad
           else 'every bar has as many attack points as the engraving has columns', bad)


CLEF_REF = {'G': 4 * 7 + 4, 'F': 3 * 7 + 3, 'C': 4 * 7 + 0}     # the note on the clef's line: G4, F3, C4 (diatonic)


def file_positions(root):
    """{(bar index, staff index in the system): {half-spaces below the top line}} for every notehead
    the file would print, each read with the clef in force at its onset. Staves are counted over the
    parts in file order (a part with <staves>2</staves> takes two)."""
    pos = defaultdict(set)
    base = 0
    for part in root.findall('part'):
        nst, div = 1, 1
        clefs = {}                      # staff number -> [(bar index, onset, top-line diatonic)]
        for bi, m in enumerate(part.findall('measure')):
            t = F(0)
            last = F(0)
            for e in m:
                if e.tag == 'attributes':
                    if e.find('divisions') is not None: div = int(e.findtext('divisions'))
                    if e.find('staves') is not None: nst = int(e.findtext('staves'))
                    for c in e.findall('clef'):
                        k = int(c.get('number', '1'))
                        line = int(c.findtext('line') or {'G': 2, 'F': 4, 'C': 3}.get(c.findtext('sign'), 2))
                        ref = CLEF_REF.get(c.findtext('sign'))
                        if ref is None: continue
                        ref += 7 * int(c.findtext('clef-octave-change') or 0)
                        clefs.setdefault(k, []).append((bi, t, ref + 2 * (5 - line)))
                elif e.tag == 'backup':
                    t -= F(int(e.findtext('duration')), div)
                elif e.tag == 'forward':
                    t += F(int(e.findtext('duration')), div)
                elif e.tag == 'note':
                    on = last if e.find('chord') is not None else t
                    if e.find('chord') is None:
                        last = t
                        if e.find('grace') is None: t += F(int(e.findtext('duration') or 0), div)
                    p = e.find('pitch')
                    if p is None: continue
                    k = int(e.findtext('staff') or 1)
                    cl = [c for c in clefs.get(k, []) if (c[0], c[1]) <= (bi, on)]
                    if not cl: continue
                    d = 7 * int(p.findtext('octave')) + STEPS.index(p.findtext('step'))
                    pos[(bi, base + k - 1)].add(cl[-1][2] - d)
        base += nst
    return pos, base


def check_pitches(root, E):
    """17: the staff positions of the noteheads printed in each bar of each staff are the ones
    the file's pitches would print at. Reads the page with this script's own staff finder, so a
    staff misread by the extractor (ledger lines taken for staff lines: every note a line off)
    cannot pass by agreeing with itself."""
    fpos, nst = file_positions(root)
    order = [m.get('number') for m in root.find('part').findall('measure')]
    bars = pdf_bars(E)
    if len(bars) != len(order):
        return report(17, 'Noteheads match the pitches', 'NOT RUN',
                      f'PDF bar count {len(bars)} does not match the file ({len(order)})')
    bad, skipped, seen = [], 0, 0
    runs = defaultdict(list)
    for bi, (page, sy, a, b, _) in enumerate(bars):
        if len(sy) != nst: skipped += 1; continue
        sp = page['sp']
        allst = [s for y in page['systems'] for s in y]
        got = defaultdict(set)
        for c in page['chars']:
            if not any(f in c['font'] for f in MUSIC_FONTS) or not (a + 1 < c['x0'] < b - 1): continue
            code = ord(c['t'][0])
            if code not in HEADS and not (c['t'] == 'w' and 'Helsinki' in c['font']): continue
            s = min(allst, key=lambda s: abs((s['lines'][0] + s['lines'][4]) / 2 - c['y']))
            if not any(s is x for x in sy): continue
            k = next(i for i, x in enumerate(sy) if x is s)
            got[k].add(round((c['y'] - s['lines'][0]) / (sp / 2) - E.grid_base))
        for k in range(nst):
            seen += 1
            want = fpos.get((bi, k), set())
            if got[k] != want:
                sh = {dd for dd in range(-9, 10) if dd and {w + dd for w in want} == got[k] and want}
                what = (f'every head {min(sh, key=abs):+d} half-space(s) from the file' if sh else
                        f'PDF only {sorted(got[k] - want)}, file only {sorted(want - got[k])}')
                bad.append(f'bar {order[bi]}, staff {k + 1} of the system: {what}')
                runs[k].append(bi)
    if not seen:
        return report(17, 'Noteheads match the pitches', 'NOT RUN',
                      f'no system has as many staves as the file ({nst}): hidden staves, not understood')
    note = f'; {skipped} bar(s) on systems with a different staff count not compared' if skipped else ''
    report(17, 'Noteheads match the pitches', 'FAIL' if bad else 'PASS',
           (f'{len(bad)} bar-staff(s) of {seen} where the printed heads and the file disagree' if bad
            else f'{seen} bar-staves compared, printed heads and file pitches agree') + note, bad)


# ----------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('score')
    ap.add_argument('--pdf')
    ap.add_argument('--lanes', help='"0a=Tenor,0b=Lead,1a=Baritone,1b=Bass"')
    ap.add_argument('--original')
    ap.add_argument('--render')
    ap.add_argument('--xsd')
    ap.add_argument('--lyric-font'); ap.add_argument('--lyric-size', type=float)
    a = ap.parse_args()
    root, names = load(a.score)
    out_dir = os.path.dirname(os.path.abspath(a.score))

    check_xsd(a.score, a.xsd)
    check_bars(root, names)
    check_ranges(root, names)
    check_qc(a.score)
    check_render(a.score, a.render)
    check_instructions(a.pdf)
    report(7, 'Judgment calls handed back', 'MANUAL', 'list every divisi bar, duplicated lyric, literal-rest reading and fixed typo in the handback')
    check_ties(root, names)
    check_words(root, names, out_dir)
    if a.pdf:
        try:
            E = Engraving(a.pdf, a.lyric_font, a.lyric_size)
        except Exception as ex:
            E = None
            for n, nm in ((10, 'Extension lines match the PDF'), (11, 'Cross-staff onset alignment'), (12, 'Noteheads on the grid'), (17, 'Noteheads match the pitches')):
                report(n, nm, 'NOT RUN', f'could not read the PDF: {ex}')
        if E:
            if a.lanes:
                lanes = dict(kv.split('=', 1) for kv in a.lanes.split(','))
            else:
                per_sys = {len(sy) for p in E.pages for sy in p['systems']}
                pn = [names[p.get('id')] for p in root.findall('part')]
                lanes = {f'{k}b': pn[k] for k in range(len(pn))} if per_sys == {len(pn)} else None
            if lanes:
                missing = [v for v in lanes.values() if v not in names.values()]
                if missing:
                    report(10, 'Extension lines match the PDF', 'NOT RUN', f'--lanes names parts the file does not have: {missing}')
                else:
                    check_extender_lines(root, names, E, lanes)
            else:
                report(10, 'Extension lines match the PDF', 'NOT RUN',
                       'the PDF has fewer staves than the file has parts (a closed score): pass --lanes')
            check_onsets(root, E)
            check_grid(E)
            if hasattr(E, 'grid_base'): check_pitches(root, E)
            else: report(17, 'Noteheads match the pitches', 'NOT RUN', 'no noteheads recognised (see check 12)')
    else:
        for n, nm in ((10, 'Extension lines match the PDF'), (11, 'Cross-staff onset alignment'), (12, 'Noteheads on the grid'), (17, 'Noteheads match the pitches')):
            report(n, nm, 'NOT RUN', 'needs --pdf')
    check_shared_staff(root)
    check_extend_runs(root, names, a.original)
    check_layout(a.score, root)
    check_original(root, names, a.original)

    results.sort()
    w = max(len(r[1]) for r in results)
    print(f'Step 5 checks for {os.path.basename(a.score)}' + (f' against {os.path.basename(a.pdf)}' if a.pdf else ''))
    for n, name, status, summary in results:
        print(f'{n:>3}  {name:<{w}}  {status:<8} {summary}')
    for n, name, status, summary in results:
        if details[n] and status in ('FAIL', 'WARN', 'MANUAL'):
            print(f'\n{n}. {name}')
            for l in details[n][:40]: print(f'    {l}')
            if len(details[n]) > 40: print(f'    ... and {len(details[n]) - 40} more')
    sys.exit(1 if any(r[2] == 'FAIL' for r in results) else 0)


if __name__ == '__main__':
    main()
