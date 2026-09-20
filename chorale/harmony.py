"""Chord symbols.

Only the kinds a folk/pop choral chart actually prints.  `(add2)` is spelled as a
major triad plus a parenthesised added second, which is what MusicXML has and
what every reader draws as G(add2).
"""
import re

SYMBOL = re.compile(r'([A-G])([#b]?)(m|maj9|maj7|m7|7|sus4|sus2|dim|aug|\(add2\)|\(add9\))?'
                    r'(?:/([A-G])([#b]?))?')

KINDS = {None: 'major', 'm': 'minor', 'maj9': 'major-ninth', 'maj7': 'major-seventh',
         'm7': 'minor-seventh', '7': 'dominant', 'sus4': 'suspended-fourth',
         'sus2': 'suspended-second', 'dim': 'diminished', 'aug': 'augmented',
         '(add2)': 'major', '(add9)': 'major'}

ADDED = {'(add2)': 2, '(add9)': 9}

_ALTER = {'#': 1, 'b': -1, '': 0}


def harmony_xml(sym, offset_ticks=0):
    """One <harmony>.  `offset_ticks` is in the part's own divisions, 0 for beat 1."""
    m = SYMBOL.fullmatch(sym)
    if not m:
        raise ValueError(f'chord symbol not understood: {sym!r}')
    root, ralt, kind, bass, balt = m.groups()
    s = f'<harmony><root><root-step>{root}</root-step>'
    if _ALTER[ralt]:
        s += f'<root-alter>{_ALTER[ralt]}</root-alter>'
    s += '</root>'
    paren = ' parentheses-degrees="yes"' if kind in ADDED else ''
    s += f'<kind{paren}>{KINDS[kind]}</kind>'
    if bass:
        s += f'<bass><bass-step>{bass}</bass-step>'
        if _ALTER[balt]:
            s += f'<bass-alter>{_ALTER[balt]}</bass-alter>'
        s += '</bass>'
    if kind in ADDED:
        s += (f'<degree><degree-value>{ADDED[kind]}</degree-value><degree-alter>0</degree-alter>'
              f'<degree-type>add</degree-type></degree>')
    if offset_ticks:
        s += f'<offset>{offset_ticks}</offset>'
    return s + '</harmony>'
