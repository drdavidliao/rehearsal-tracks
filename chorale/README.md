# chorale

The piece-independent half of building a choral score by hand.

It came out of two octavos built the same way twice. A piece script should hold
only what is true of that piece — its bar count, its dynamics, its rehearsal
figures, its chord chart, the bars the OMR garbled — and nothing about how a
`<note>` is spelled or how two voices share a staff.

## The event model

Everything speaks one shape, documented in `events.py`: an event is a dict with
`dur`, `base`, `dots`, `pitches`, `tie`, `slur_start`, `slur_stop`, `lyric`.
A line is `{bar: [event, ...]}`, bars numbered from 1. `finalize()` derives
`tie_stop` and lyric `extend` across a whole line and raises on a sung note with
no syllable, which is how a dropped syllable gets caught at build time rather
than in a rehearsal.

## Modules

| module | what it does |
| --- | --- |
| `events` | the event model, pitch helpers, `finalize()` |
| `scoretext` | the compact `[block]` / `bar: tokens` notation and its parser |
| `beaming` | beam groups, including for a voice with gaps in it |
| `collapse` | two lines onto one staff; which bars need two lyric lines |
| `musicxml` | `ScoreSpec`, `StaffMarks`, `Header`, note and direction fragments, three part shapes, the score wrapper |
| `harmony` | chord symbols |
| `omr` | folding an OMR export in and repairing it bar by bar |
| `printing` | `Print` — page plan, Verovio options, PDF; and the SMuFL font fix |
| `lyriccheck` | syllables that would print on top of each other |
| `bench` | build a revoicing bench page from any score |
| `instructions` | the Revoicing Bench's exported spans, resolved against real notes |

## Three ways two voices share a staff

`open_part` — one voice, one staff. `divided_part` — the parts agree from the
bar line, split once, and stay split; that is how most printed closed scores
work, and it is what `collapse.closed_bars` produces. `collapsed_part` — the
parts agree and disagree in patches inside the bar, which is what a revoicing
actually looks like; `collapse.merge_runs` produces it.

## The two things that cost the most time to find

**Lyric lines are decided by words, not by collisions.** A bar needs a second
lyric line only where the two voices sing *different syllables*. Deciding it by
asking whether two syllables would collide puts half a word on line 2 and leaves
an extender dangling under it. `collapse.lyric_split` compares syllable
sequences; `collapse.prune_v2_extends` removes the extenders voice 2 has no note
left to draw under.

**Verovio's `unit` is the staff-size knob, not `scale`.** `unit` is half a staff
space in 1/10 mm, so `mm / 4 * 10 / 2`. `scale` only zooms the finished SVG.
And cairosvg ignores `@font-face`, so every SMuFL glyph Verovio draws as text —
chord-symbol accidentals above all — becomes a tofu rectangle in the PDF no
matter what `smuflTextFont` says. `printing.install_smufl_font()` unpacks
Verovio's own Leipzig out of its stylesheet and installs it for fontconfig,
which is what cairosvg actually consults.

**The two readers want opposite credit encodings, and a probe is the only
way to learn that.** A file with six differently-encoded credits, each
labelled with its own encoding, settles in one import what three rounds of
guessing did not:

* **Sibelius keeps one credit per zone of the page.** Given six separate
  `<credit>` elements aimed at the same corner it drew the last and silently
  dropped five. But it renders every `<credit-words>` inside a *single*
  credit as its own line. So a multi-line credit block is the encoding that
  survives — which is what MuseScore writes.
* **Verovio is the mirror image.** It draws every separate credit and only the
  *first* `<credit-words>` of a block.

`printing.Print.credit_xml` therefore emits one block, and
`expand_credit_blocks` splits it into one credit per line on the way into
Verovio and nowhere else: the file gets the encoding the notation program
reads, the renderer gets the one it reads.

**The copyright notice is a third case.** Sibelius turns `<rights>` into a
copyright line of its own and pins it to the *bottom margin* — which is also
where it justifies the staves down to after import, so the notice and the last
system land on each other. Widening the bottom margin does not help: it moves
both together. The fix is to drop `<rights>`, pass the notice as `credit_xml`'s
`footer`, and let it sit *inside* the margin band a few millimetres off the
paper edge, where justification cannot reach it. Leaving `<rights>` in as well
gets you two notices. Verovio needs it painted on separately (`draw_footer`):
it converts credits into the page head only and drops a bottom-positioned one
under all three `footer` settings — none, auto and encoded were all tried.

Positions are not optional either. MusicXML page coordinates are in tenths and
the schema's own documentation says "the default-x and default-y attributes
adjust the origin relative to the bottom left-hand corner of the page", so a
credit without them lands at (0, 0) — the corner of the paper, no margin.
`credit_xml` computes them from the same page plan the layout uses, and
`header_tenths` sizes the gap above the first system so the block has
somewhere to sit. `<defaults>` must also precede `<credit>`, which must
precede `<part-list>`, or the file fails the schema.

Two smaller ones. Verovio randomises the id suffix on every generated SVG
element per render, and rendering a page after sweeping the whole document can
move a header baseline by one 1/10-mm unit, so **you cannot verify a layout
change by diffing two PDFs** — diff the laid-out MusicXML. And Verovio's
"justification is highly compressed" warning is about note spacing: it will not
fire on a system that fits but whose words overlap, which is what `lyriccheck`
is for.

## The bench

```
python3 -m chorale.bench score.musicxml -o out/ --beats 8 --bars-per-system 4
```

A scrolling engraving with a clickable beat grid under every bar: shift-click a
run of beats, write what should happen there. `--beats` is cells per bar and
defaults to the notated beats, which is usually too coarse — in cut time the
notated beat is a half note, so 4 or 8 is what you want. The grid is placed from
the rendered SVG, so a cell sits under its note rather than dividing the bar
evenly; cells with no attack are interpolated between the ones that have,
anchored at the barlines, so a bar of one whole note still gets a usable grid.

Publish the result as an artifact with the `db` and `downloads` capabilities,
and seed `bench/<slug>` with a palette.

Two things about other programs' exports. MuseScore declares
`<supports element="print" attribute="new-page" type="no"/>`, and Verovio
believes it and ignores every break you insert, flowing the whole score onto one
system; the declaration has to go. And MuseScore writes
`<measure number="1" width="253.75">`, so a pattern matching `<measure
number="(\d+)">` finds nothing and inserts no breaks at all, silently.

## Instructions from the bench

Sibelius comments do not survive a MusicXML export. The format has no element
for a reviewer's note — no `comment`, nothing in `other-direction`, `footnote`
or `level` that Sibelius writes one into — so spans and prose come out of the
Revoicing Bench instead, as JSON:

```json
{"score": "...", "beats_per_bar": 4,
 "instructions": [{"from": "24.1", "to": "26.4", "tag": "P4to4", "text": "..."}]}
```

`from` and `to` are `bar.beat`, 1-based and inclusive.

```
python3 -m chorale.instructions revoicing.json score.txt T1,T2,B1,B2
```

prints each instruction with the notes it actually selects, per part, which is
the check to run before acting on any of them.

## Worked example

A piece script built on this package is a `ScoreSpec`, a few dicts of dynamics,
hairpins and cues keyed by bar, the OMR repairs, and one `build_*` function per
output — each of those mostly a part list. Around 300 lines for a 67-bar octavo,
nearly all of it data.

No worked example ships here. A real one is a transcription of a published
arrangement, and this repository is public.
