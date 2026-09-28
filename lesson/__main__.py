"""Note-learning lesson plan for an SATB piece (SKILL.md Step 11).

    python3 -m lesson score.musicxml [--pdf "Full score.pdf" --pages 1-13] [--rhythm drill|slow] [--out DIR]

Writes "<title> - lesson plan.pdf", a printable landscape checklist, and with --pdf a copy of that PDF with the
steps stamped onto the score: "<pdf name> (lesson marks).pdf". The MusicXML is what the plan is worked out from;
the PDF must be the vector engraving it was read from (dorico_reader.py), since the marks are placed from the
PDF's own staff and bar positions.

--rhythm drill   hard rhythms get slow spoken work (Rh m24), shared ones once for everyone first
--rhythm slow    no drills: the passage is played and sung down tempo first (P↓ S↓), for music the choir
                 already has in its ears
"""
import argparse, os, sys, xml.etree.ElementTree as ET

from . import analyze, plan, render, overlay

KEYS = {0: 'C', 1: 'G', 2: 'D', 3: 'A', 4: 'E', 5: 'B', 6: 'F♯', 7: 'C♯',
        -1: 'F', -2: 'B♭', -3: 'E♭', -4: 'A♭', -5: 'D♭', -6: 'G♭', -7: 'C♭'}


def facts(path, S):
    root = ET.parse(path).getroot()
    title = (root.findtext('work/work-title') or root.findtext('movement-title') or os.path.splitext(os.path.basename(path))[0]).strip()
    parts = [sp.findtext('part-name') for sp in root.iter('score-part')]
    voices = ''.join(p[0] for p in parts if p in analyze.PARTS)
    extra = [p for p in parts if p not in analyze.PARTS]
    tempo = next((s.get('tempo') for s in root.iter('sound') if s.get('tempo')), None)
    times = sorted(S.times.items())
    ts = ', '.join(f"{b}/{t}" + (f" from m{n}" if n > 1 else '') for n, (b, t) in times)
    keys = sorted(S.keys.items())
    ks = '; '.join(f"{KEYS.get(f, f)} major" + (f" from m{n}" if n > 1 else '') for n, f in keys)
    bits = [voices + (' + ' + ', '.join(e.lower() for e in extra) if extra else ''), f'{S.nbars} bars', ts]
    if tempo: bits.append(f'quarter = {float(tempo):g}')
    if ks: bits.append(ks)
    return title, ' · '.join(bits)


def logic_note(S):
    pos = analyze.logic_positions(S)
    drift = [n for n, (b, beat) in pos.items() if (b, beat) != (n, 1)]
    meters = sorted(set(S.times.values()))
    head = '<b>Cueing in Logic.</b> <b>&#9654; /72</b> means type / then 72, Enter. '
    if not drift:
        body = (f'This piece is {meters[0][0]}/{meters[0][1]} all the way through, with no pickup bar and no bars of another '
                'length, so the bar Logic shows is the printed bar, as long as the track\'s first downbeat sits on Logic '
                'bar 1 at the track\'s tempo. ')
    else:
        first = drift[0]
        body = (f'Logic counts every bar as {S.times.get(1, (4, 4))[0]}/{S.times.get(1, (4, 4))[1]}, and this piece has bars of '
                f'another length (the first at m{first - 1 if first > 1 else 1}), so from there Logic\'s bar numbers differ from '
                'the printed ones. Each ▶ gives the Logic position to type (bar, then beat), with the printed bar beside it. ')
    return (head + body + 'If the track doesn\'t start on bar 1, write the offset here and add it to every cue: <b>____</b> bars. '
            '&nbsp;"in on beat 3½" = the singers come in on the &amp; of 3 of that bar; the cue starts at the downbeat so '
            'they hear a lead-in.')


def shorthand(mode):
    rh = ('<b>Rh m24</b> = slow rhythm work on bar 24. ' if mode == 'drill'
          else '<b>P↓ S↓</b> = play / sing it down tempo (Logic tempo or varispeed). ')
    return ('<br/><b>Shorthand.</b> <b>P</b> = play the track, choir listens. <b>S</b> = play it, choir sings (<b>SS</b> = twice). '
            + rh + '<b>m26–29 P+SS</b> = that half only. Easier parts, and parts with the same rhythm and words as one '
            'already taught, get 1 sung play instead of 2. The first part taught rotates from letter to letter.')


def pages(spec, n):
    if not spec: return range(n)
    a, _, b = spec.partition('-')
    return range(int(a) - 1, int(b or a))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('--pdf', help='the vector PDF the MusicXML was read from; stamps the steps onto it')
    ap.add_argument('--pages', help='the full-score pages of that PDF, e.g. 1-13 when parts follow it')
    ap.add_argument('--rhythm', choices=('drill', 'slow'), default='drill')
    ap.add_argument('--out', default='.')
    ap.add_argument('--rhythm-threshold', type=float, default=4.5)
    ap.add_argument('--easy', type=float, default=1.5)
    ap.add_argument('--hard', type=float, default=3.0)
    a = ap.parse_args()
    S = analyze.Score(a.score)
    title, fact = facts(a.score, S)
    P = plan.Planner(S, rhythm_threshold=a.rhythm_threshold, easy_threshold=a.easy, hard_threshold=a.hard, rhythm_mode=a.rhythm)
    pl = P.plan()
    steps = plan.number_steps(pl)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, f'{title} - lesson plan.pdf')
    render.render(out, title, fact, pl, logic_note(S) + shorthand(a.rhythm))
    print('wrote', out)
    if a.pdf:
        import pdfplumber
        with pdfplumber.open(a.pdf) as pdf:
            n = len(pdf.pages)
        dst = os.path.join(a.out, os.path.splitext(os.path.basename(a.pdf))[0] + ' (lesson marks).pdf')
        root = ET.parse(a.score).getroot()
        nst = sum(max([int(x.text) for x in p.iter('staves')] or [1]) for p in root.findall('part'))
        overlay.annotate(a.pdf, pages(a.pages, n), pl, steps, dst, a.rhythm, score=S, nstaves=nst, plan_obj=P)
        print('wrote', dst)


if __name__ == '__main__':
    main()
