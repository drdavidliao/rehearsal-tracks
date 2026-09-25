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

# A syllable may open with an apostrophe or a quote mark: pris-'ner, 'tis, "Hark.
OK_CHARS=re.compile(r"^[\"'’]?[A-Za-z][A-Za-z'’\-\.,!?;:\"]*$")

def syllable_onsets(part):
    """Where each syllable of one part starts (quarters from the start), and whether any staff of
    the part carries two voices."""
    div=1; bar_start=F(0); out=set(); voices=set()
    for m in part.findall('measure'):
        for a in m.findall('attributes'):
            d=a.find('divisions')
            if d is not None: div=int(d.text)
        pos=F(0); mx=F(0)
        for e in m:
            if e.tag=='backup': pos-=F(int(e.find('duration').text),div)
            elif e.tag=='forward': pos+=F(int(e.find('duration').text),div)
            elif e.tag=='note':
                if e.find('chord') is not None: continue
                if e.find('rest') is None:
                    voices.add((e.findtext('staff') or '1', e.findtext('voice') or '1'))
                    if e.find('lyric') is not None and (e.findtext('lyric/text') or '').strip():
                        out.add(bar_start+pos)
                pos+=F(int(e.find('duration').text),div) if e.find('duration') is not None else 0
            mx=max(mx,pos)
        bar_start+=mx
    return out, bool(out) and len({v for st,v in voices})>1     # a sung part (not a piano) on two voices

def qc(path):
    root=load(path)
    issues=defaultdict(list)
    # A closed score (two parts to a staff) prints words once where the staves sing them together,
    # often between the staves: the other staff's notes there carry none and read that line. So in
    # a closed score a note may also borrow a syllable another part starts at the same moment. Not
    # in an open score, where every part carries its own words and a gap is a lost syllable.
    ons={p.get('id'): syllable_onsets(p) for p in root.findall('part')}
    closed=any(two for _,two in ons.values())
    for part in root.findall('part'):
        pid=part.get('id'); div=1; ts=None
        prev_oct={}; octjumps=[]
        # One sequence per part on each staff: on a shared staff the two
        # singers' notes interleave in document order, and walking back from a
        # voice-2 note would otherwise land on voice 1's syllables and rests.
        seqs=defaultdict(list)   # (staff, part) -> [(measure, is_pitched, lyric, has_extend, is_tie_stop, onset, dur)]
        bar_start=F(0)
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
            pos=F(0)
            for e in m:
                if e.tag=='backup': pos-=F(int(e.find('duration').text),div); continue
                if e.tag=='forward': pos+=F(int(e.find('duration').text),div); continue
                if e.tag!='note': continue
                n=e
                dur=F(int(n.find('duration').text),div) if n.find('duration') is not None else F(0)
                # voices 1/5 are the upper part of a staff; any other voice is the
                # lower part (chorale writes a stray lower-part note in voice 3)
                key=(n.findtext('staff') or '1', 'upper' if (n.findtext('voice') or '1') in ('1','5') else 'lower')
                if n.find('chord') is None:
                    onset=bar_start+pos
                    pos+=dur
                    ties = [x.get('type') for x in n.findall('tie')]
                    ly = n.find('lyric')
                    if n.find('rest') is not None:
                        seqs[key].append((num, False, None, False, False, onset, dur))
                    else:
                        seqs[key].append((num, True,
                                    ly.findtext('text') if ly is not None else None,
                                    ly is not None and ly.find('extend') is not None and ly.find('extend').get('type') != 'stop',
                                    'stop' in ties, onset, dur))
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
                    elif re.fullmatch(r'(\w{2,})\1', w, re.I):   # 'songsong'; not 'Oo'
                        issues['doubled lyric'].append(f"{pid} m{num}: {w!r}")
                p=n.find('pitch')
                if p is None or n.find('chord') is not None: continue
                o=int(p.find('octave').text)
                if key in prev_oct and abs(o-prev_oct[key])>=2:
                    octjumps.append(f"{pid} m{num}: {prev_oct[key]}->{o}")
                prev_oct[key]=o
            bar_start+=mx
        # octave leaps only matter where there are lyrics to sing
        if any(True for n in part.iter('lyric')):
            issues['octave jump in a sung line'].extend(octjumps)
            # On a staff two parts share, one lyric line serves both where they
            # sing the same words (SKILL.md 7.4): the lower part's note then has
            # no syllable of its own and sings the one printed for the other
            # part at the same moment.  So a note with no syllable is fine if
            # the other part on its staff starts a syllable at that onset, or if
            # it continues -- contiguous in its own part -- a note that has one
            # (with an extender) or that borrows one, or if its part's notes
            # before it were merged into the other part's chords and that
            # part's syllable is still being held.
            starts=defaultdict(set)   # (staff, part) -> onsets of syllables
            for (st,ln),seq in seqs.items():
                for (mn,pit,txt,ext,tie,on,du) in seq:
                    if pit and txt is not None: starts[(st,ln)].add(on)
            def borrowed(st,ln,on):
                return any(on in s for (st2,ln2),s in starts.items() if st2==st and ln2!=ln) or \
                    (closed and any(on in o for p2,(o,_) in ons.items() if p2!=pid))
            # where each syllable is held with an extender: onset to the end of its melisma
            held=defaultdict(list)    # (staff, part) -> [(from, to)]
            for (st,ln),seq in seqs.items():
                for i,(mn,pit,txt,ext,tie,on,du) in enumerate(seq):
                    if not (pit and txt is not None and ext): continue
                    end=on+du
                    for q in seq[i+1:]:
                        if not q[1] or q[2] is not None or q[5]!=end: break
                        end=q[5]+q[6]
                    held[(st,ln)].append((on,end))
            for (st,ln),seq in seqs.items():
                for i,(mn,pit,txt,ext,tie,on,du) in enumerate(seq):
                    if not pit or txt is not None or tie or borrowed(st,ln,on): continue
                    j=i-1; ok=False
                    while True:
                        q=seq[j] if j>=0 else None
                        if q is None or q[5]+q[6]!=seq[j+1][5]:
                            # a gap: the part's earlier notes merged into the other
                            # part's chords, so the other part's melisma is this one's
                            ok=any(a<seq[j+1][5]<b for (st2,ln2),iv in held.items()
                                   if st2==st and ln2!=ln for a,b in iv)
                            break
                        if not q[1]: break                 # a rest ends the melisma
                        if q[2] is not None: ok=q[3]; break
                        if borrowed(st,ln,q[5]): ok=True; break
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
