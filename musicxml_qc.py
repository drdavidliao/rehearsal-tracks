#!/usr/bin/env python3
"""Pre-synthesis QC for MusicXML. Catches the failure modes that wreck singing synthesis:
short/overfull bars, garbled lyrics, and octave discontinuities.

    python3 musicxml_qc.py score.musicxml
"""
import sys, re, zipfile, io
import xml.etree.ElementTree as ET
from fractions import Fraction as F
from collections import defaultdict

def load(path):
    if path.lower().endswith('.mxl'):
        with zipfile.ZipFile(path) as z:
            name=[n for n in z.namelist() if n.endswith(('.xml','.musicxml')) and not n.startswith('META')][0]
            return ET.parse(io.BytesIO(z.read(name))).getroot()
    return ET.parse(path).getroot()

OK_CHARS=re.compile(r"^[A-Za-z][A-Za-z'’\-\.,!?;:\"]*$|^\"[A-Za-z][A-Za-z'’\-\.,!?;:\"]*$")

def qc(path):
    root=load(path)
    issues=defaultdict(list)
    for part in root.findall('part'):
        pid=part.get('id'); div=1; ts=None
        prev_oct=None; octjumps=[]
        seq=[]   # (measure, is_pitched, lyric, has_extend, is_tie_stop)
        for m in part.findall('measure'):
            num=m.get('number')
            for a in m.findall('attributes'):
                d=a.find('divisions')
                if d is not None: div=int(d.text)
                t=a.find('time')
                if t is not None: ts=(int(t.find('beats').text),int(t.find('beat-type').text))
            # --- bar length ---
            pos=F(0); mx=F(0)
            for e in m:
                if e.tag=='note':
                    if e.find('chord') is None: pos+=F(int(e.find('duration').text),div)
                elif e.tag=='backup': pos-=F(int(e.find('duration').text),div)
                elif e.tag=='forward': pos+=F(int(e.find('duration').text),div)
                mx=max(mx,pos)
            if ts:
                exp=F(ts[0]*4,ts[1])
                if mx and mx!=exp:
                    kind='SHORT' if mx<exp else 'OVERFULL'
                    issues['bar length'].append(f"{pid} m{num}: {mx} beats in a {ts[0]}/{ts[1]} bar ({kind})")
            # --- lyrics + octave continuity ---
            for n in m.findall('note'):
                if n.find('chord') is None:
                    ties = [x.get('type') for x in n.findall('tie')]
                    ly = n.find('lyric')
                    if n.find('rest') is not None:
                        seq.append((num, False, None, False, False))
                    else:
                        seq.append((num, True,
                                    ly.findtext('text') if ly is not None else None,
                                    ly is not None and ly.find('extend') is not None and ly.find('extend').get('type') != 'stop',
                                    'stop' in ties))
                        if 'stop' in ties and ly is not None and ly.findtext('text'):
                            issues['syllable on a tie continuation'].append(
                                f"{pid} m{num}: {ly.findtext('text')!r} — a tied note sustains "
                                f"the previous syllable and cannot begin a new one")
                for l in n.findall('lyric'):
                    t=l.find('text')
                    if t is None or not t.text: continue
                    w=t.text.strip()
                    if not OK_CHARS.match(w):
                        issues['garbled lyric'].append(f"{pid} m{num}: {w!r}")
                    elif re.fullmatch(r'(\w+)\1', w, re.I):
                        issues['doubled lyric'].append(f"{pid} m{num}: {w!r}")
                p=n.find('pitch')
                if p is None or n.find('chord') is not None: continue
                o=int(p.find('octave').text)
                if prev_oct is not None and abs(o-prev_oct)>=2:
                    octjumps.append(f"{pid} m{num}: {prev_oct}->{o}")
                prev_oct=o
        # octave leaps only matter where there are lyrics to sing
        if any(True for n in part.iter('lyric')):
            issues['octave jump in a sung line'].extend(octjumps)
            for i,(mn,pit,txt,ext,tie) in enumerate(seq):
                if not pit or txt is not None or tie: continue
                j=i-1; ok=False
                while j>=0:
                    if not seq[j][1]: break            # a rest breaks the melisma
                    if seq[j][2] is not None: ok=seq[j][3]; break
                    j-=1
                if not ok:
                    issues['sung note with no syllable and no extend'].append(f'{pid} m{mn}')
        # --- clef octave consistency (the tenor-8vb trap) ---
        ocs=set()
        for c in part.iter('clef'):
            e=c.find('clef-octave-change')
            ocs.add(e.text if e is not None else '0')
        if len(ocs)>1:
            issues['clef octave flips'].append(f"{pid}: clef-octave-change takes values {sorted(ocs)}")
    return issues

for path in sys.argv[1:]:
    print('='*66); print(path.split('/')[-1])
    iss=qc(path)
    if not iss: print('  clean'); continue
    for k in sorted(iss):
        v=iss[k]
        print(f'  {k}: {len(v)}')
        for line in v[:6]: print(f'      {line}')
        if len(v)>6: print(f'      ... and {len(v)-6} more')
