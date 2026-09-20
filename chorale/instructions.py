"""Read the Revoicing Bench's export and resolve it against a score.

The bench writes:

    {"score": "...", "beats_per_bar": 4,
     "instructions": [{"from": "24.1", "to": "26.4",
                       "tag": "P4to4", "text": "..."}, ...]}

`from` and `to` are "bar.beat", both 1-based and both inclusive: "24.1" to
"26.4" means every beat from the downbeat of 24 through the last beat of 26.

Sibelius comments do not survive a MusicXML export — the format has no element
for a reviewer's note, so there is nowhere standard to put one — which is why the
spans come through this file rather than through the score itself.
"""
import json
import re
from fractions import Fraction as F

REF = re.compile(r'(\d+)\.(\d+)')


def parse_ref(s):
    m = REF.fullmatch(str(s).strip())
    if not m:
        raise ValueError(f'not a bar.beat reference: {s!r}')
    return int(m.group(1)), int(m.group(2))


class Span:
    """One instruction: a contiguous run of beats, and what to do with them."""

    def __init__(self, start, end, text, tag=None, beats_per_bar=4):
        self.bar0, self.beat0 = start
        self.bar1, self.beat1 = end
        self.text = text or ''
        self.tag = tag or None
        self.beats_per_bar = beats_per_bar
        if (self.bar1, self.beat1) < (self.bar0, self.beat0):
            raise ValueError(f'{self} runs backwards')

    # ---- geometry -------------------------------------------------------
    @property
    def _i0(self):
        return (self.bar0 - 1) * self.beats_per_bar + (self.beat0 - 1)

    @property
    def _i1(self):
        return (self.bar1 - 1) * self.beats_per_bar + (self.beat1 - 1)

    def cells(self):
        """[(bar, beat), ...] — every beat the span covers."""
        return [(i // self.beats_per_bar + 1, i % self.beats_per_bar + 1)
                for i in range(self._i0, self._i1 + 1)]

    def bars(self):
        return range(self.bar0, self.bar1 + 1)

    def whole_bars(self):
        """The bars the span covers from first beat to last — safe to rewrite whole."""
        return [m for m in self.bars()
                if (m > self.bar0 or self.beat0 == 1)
                and (m < self.bar1 or self.beat1 == self.beats_per_bar)]

    def contains(self, bar, beat):
        return self._i0 <= (bar - 1) * self.beats_per_bar + (beat - 1) <= self._i1

    def contains_offset(self, bar, offset):
        """`offset` in quarters from the bar line — where a parsed event actually sits.

        A note that starts inside the span is in it even when it began off the
        beat; a note that started before the span and is still sounding is not.
        """
        beat = int(F(offset)) + 1
        return self.contains(bar, beat)

    # ---- resolution against real music ----------------------------------
    def events(self, line):
        """[(bar, offset, event), ...] — the notes of `line` this span selects."""
        out = []
        for m in self.bars():
            if m not in line:
                continue
            pos = F(0)
            for e in line[m]:
                if self.contains_offset(m, pos):
                    out.append((m, pos, e))
                pos += e['dur']
        return out

    def label(self):
        a = f'm{self.bar0} b{self.beat0}'
        b = f'm{self.bar1} b{self.beat1}'
        return a if a == b else f'{a} – {b}'

    def __repr__(self):
        return f'<Span {self.label()}{" [" + self.tag + "]" if self.tag else ""}>'


class Instructions:
    def __init__(self, spans, score='', beats_per_bar=4):
        self.spans = spans
        self.score = score
        self.beats_per_bar = beats_per_bar

    def __len__(self):
        return len(self.spans)

    def __iter__(self):
        return iter(self.spans)

    def for_bar(self, bar):
        return [s for s in self.spans if s.bar0 <= bar <= s.bar1]

    def tagged(self, tag):
        return [s for s in self.spans if s.tag == tag]

    def tags(self):
        seen = []
        for s in self.spans:
            if s.tag and s.tag not in seen:
                seen.append(s.tag)
        return seen

    def check(self, nbars):
        """Anything that cannot be acted on: off the end of the piece, or overlapping."""
        problems = []
        for s in self.spans:
            if s.bar1 > nbars or s.bar0 < 1:
                problems.append(f'{s.label()}: outside bars 1–{nbars}')
            if not (1 <= s.beat0 <= self.beats_per_bar and 1 <= s.beat1 <= self.beats_per_bar):
                problems.append(f'{s.label()}: beat outside 1–{self.beats_per_bar}')
            if not s.text.strip():
                problems.append(f'{s.label()}: no instruction text')
        ordered = sorted(self.spans, key=lambda s: (s._i0, s._i1))
        for a, b in zip(ordered, ordered[1:]):
            if b._i0 <= a._i1:
                problems.append(f'{a.label()} and {b.label()} overlap')
        return problems

    def to_text(self):
        out = [self.score, '']
        for s in sorted(self.spans, key=lambda s: (s._i0, s._i1)):
            out.append(s.label() + (f'  [{s.tag}]' if s.tag else ''))
            out += ['    ' + ln for ln in s.text.splitlines()]
            out.append('')
        return '\n'.join(out)

    def report(self, lines, pname=None):
        """What each instruction actually selects, line by line — read this before acting.

        `lines` is {part name: line}.  `pname` formats a pitch; the default
        prints scientific names.
        """
        from .events import pname as default_pname
        fmt = pname or default_pname
        out = []
        for s in sorted(self.spans, key=lambda s: (s._i0, s._i1)):
            out.append(s.label() + (f'  [{s.tag}]' if s.tag else ''))
            for ln in s.text.splitlines():
                out.append('    ' + ln)
            for name, line in lines.items():
                evs = s.events(line)
                bits = []
                for m, pos, e in evs:
                    p = '/'.join(fmt(x) for x in e['pitches']) or 'rest'
                    w = e['lyric']['text'] if e['lyric'] else ''
                    bits.append(f'{p}{"=" + w if w else ""}')
                out.append(f'      {name:<8} ' + ' '.join(bits))
            out.append('')
        return '\n'.join(out)


def load(path):
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
    return from_dict(d)


def from_dict(d):
    bpb = int(d.get('beats_per_bar', 4))
    spans = [Span(parse_ref(it['from']), parse_ref(it.get('to', it['from'])),
                  it.get('text', ''), it.get('tag'), bpb)
             for it in d.get('instructions', [])]
    return Instructions(spans, d.get('score', ''), bpb)


if __name__ == '__main__':
    import sys

    from .scoretext import parse_score

    if len(sys.argv) < 2:
        raise SystemExit('usage: python3 -m chorale.instructions FILE.json [score.txt [blocks]]')
    ins = load(sys.argv[1])
    print(f'{ins.score}\n{len(ins)} instruction(s), '
          f'tags: {", ".join(ins.tags()) or "none"}\n')
    if len(sys.argv) > 2:
        blocks = parse_score(sys.argv[2])
        want = sys.argv[3].split(',') if len(sys.argv) > 3 else sorted(blocks)
        nbars = max(max(b) for b in blocks.values() if b)
        for p in ins.check(nbars):
            print('  !', p)
        print(ins.report({k: blocks[k] for k in want if k in blocks}))
    else:
        print(ins.to_text())
