#!/usr/bin/env python3
"""Post-process a finished, print-faithful MusicXML so Cantai (Sibelius's AI singer) sings every note.

    python3 cantai_mode.py in.musicxml out.musicxml [--parts P3,P4,...] [--keep-dotted-ties] [--untie-all]

What it changes (vocal parts only, one voice per part assumed):
  * Inside every melisma that contains a tie, each note that starts a sound gets a piece of the
    syllable: onset+vowel on the syllable note, the bare vowel on intermediate notes, vowel+coda on
    the last.  "gleams" over E♭-(E♭)-(E♭)-D-B♭-C-(C)-D becomes  glea / ea / ea / ea / eams.
  * A dotted tie-continuation in the middle of such a melisma is un-tied and re-sung on the vowel.
    (--keep-dotted-ties turns this off.)
  * --untie-all: EVERY tie continuation inside a real melisma (tie chain followed by at least one
    further sung note) is un-tied and re-sung on the vowel, so no tie survives in a melisma at all
    (blunt fallback for renderers that mis-stitch tied phrases). Plain tied holds that lead straight
    into the next syllable are left alone.
  * Pure slur melismas (no tie) are left as printed — Cantai handles those.
  * Lyric extension lines are re-derived: a piece gets <extend/> only if lyric-less notes follow it.
Prints one line per change.  Standard library only.
"""
import sys, re, copy
import xml.etree.ElementTree as ET

VOWELS = 'aeiouy'

def split_syllable(text, n):
    m = re.match(r"^([^A-Za-z]*)([A-Za-z']*)([^A-Za-z']*)$", text)
    prefix, core, suffix = m.groups() if m else ('', text, '')
    low = core.lower()
    mm = (re.match(r"^(y)([aeiou]+[wy]?)(.*)$", low) if low.startswith('y')
          else re.match(r"^([^aeiou]*?)([aeiouy]+[wy]?)(.*)$", low))
    if n == 1 or not mm or not mm.group(2):
        return [text] + [core] * (n - 1)
    o, nu = mm.group(1), mm.group(2)
    onset, nucleus, coda = core[:len(o)], core[len(o):len(o) + len(nu)], core[len(o) + len(nu):]
    return [prefix + onset + nucleus] + [nucleus] * (n - 2) + [nucleus + coda + suffix]

def is_rest(n): return n.find('rest') is not None
def tie_types(n): return {t.get('type') for t in n.findall('tie')} | {t.get('type') for t in n.findall('tied')}
def lyric_text(n):
    ly = n.find('lyric')
    return ly.findtext('text') if ly is not None else None
def is_dotted(n): return n.find('dot') is not None and n.findtext('type') not in ('whole', 'breve')

def set_lyric(n, text, syllabic, extend):
    for ly in n.findall('lyric'): n.remove(ly)
    ly = ET.SubElement(n, 'lyric'); ly.set('number', '1')
    ET.SubElement(ly, 'syllabic').text = syllabic
    ET.SubElement(ly, 'text').text = text
    if extend: ET.SubElement(ly, 'extend')
    # <lyric> must follow <notations>; move it after the last notations/beam if needed
    kids = list(n)
    n.remove(ly)
    idx = len(kids) - 1
    for i, k in enumerate(kids):
        if k.tag in ('play', 'listen'): idx = i - 1; break
    n.insert(idx + 1 if idx >= 0 else len(kids), ly)

def untie(prev, cur):
    for t in prev.findall('tie'):
        if t.get('type') == 'start': prev.remove(t)
    for nots in prev.findall('notations'):
        for t in nots.findall('tied'):
            if t.get('type') == 'start': nots.remove(t)
        if len(nots) == 0: prev.remove(nots)
    for t in cur.findall('tie'):
        if t.get('type') == 'stop': cur.remove(t)
    for nots in cur.findall('notations'):
        for t in nots.findall('tied'):
            if t.get('type') == 'stop': nots.remove(t)
        if len(nots) == 0: cur.remove(nots)

def process_part(part, keep_dotted, log, untie_all=False):
    notes = []   # (measure number, note element) in order, excluding chord members
    for m in part.findall('measure'):
        for n in m.findall('note'):
            if n.find('chord') is None: notes.append((m.get('number'), n))
    i = 0
    while i < len(notes):
        mn, n = notes[i]
        if is_rest(n) or not lyric_text(n):
            i += 1; continue
        j = i + 1
        while j < len(notes) and not is_rest(notes[j][1]) and not lyric_text(notes[j][1]):
            j += 1
        group = [x for _, x in notes[i:j]]
        has_tie = any('stop' in tie_types(g) for g in group[1:])
        has_melisma = any('stop' not in tie_types(g) for g in group[1:])   # a plain tied hold is not a melisma
        if has_tie and len(group) > 1 and (has_melisma or not untie_all):
            targets = [group[0]]
            for gi in range(1, len(group)):
                g = group[gi]
                followed = any('stop' not in tie_types(h) for h in group[gi + 1:])
                if 'stop' not in tie_types(g):
                    targets.append(g)
                elif untie_all or (is_dotted(g) and followed and not keep_dotted):
                    untie(group[gi - 1], g); targets.append(g)
                    log.append(f"{part.get('id')} m{mn}: tie into {'dotted ' if is_dotted(g) else ''}{g.findtext('type')} removed, note re-sung")
            if len(targets) > 1:
                ly = group[0].find('lyric'); text = ly.findtext('text'); syl = ly.findtext('syllabic') or 'single'
                pieces = split_syllable(text, len(targets))
                first = 'end' if syl in ('middle', 'end') else 'single'
                last = 'begin' if syl in ('begin', 'middle') else 'single'
                for ti, (t, ptxt) in enumerate(zip(targets, pieces)):
                    s = first if ti == 0 else last if ti == len(targets) - 1 else 'single'
                    # extend if lyric-less notes follow before the next target
                    k = group.index(t) + 1
                    ext = k < len(group) and group[k] not in targets
                    set_lyric(t, ptxt, s, ext)
                log.append(f"{part.get('id')} m{mn}: {text!r} -> {' / '.join(pieces)}")
        i = j

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    keep_dotted = '--keep-dotted-ties' in sys.argv
    untie_all = '--untie-all' in sys.argv
    only = None
    if '--parts' in sys.argv: only = set(sys.argv[sys.argv.index('--parts') + 1].split(','))
    tree = ET.parse(args[0]); root = tree.getroot()
    log = []
    for part in root.findall('part'):
        if only and part.get('id') not in only: continue
        if not any(True for _ in part.iter('lyric')): continue      # not a vocal part
        process_part(part, keep_dotted, log, untie_all)
    for l in log: print(l)
    print(f'{len(log)} changes')
    tree.write(args[1], encoding='UTF-8', xml_declaration=True)

if __name__ == '__main__':
    main()
