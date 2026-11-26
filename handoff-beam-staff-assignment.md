# Handoff: stems and beams must not be assigned to staves by proximity

Found while converting a 12/8 TTBB + piano score (MuseScore/Leland vector PDF,
47 bars, 6 staves per system). Affects
SKILL.md §2.2 and §2.3.

## The rule that is wrong

§2.2 currently says:

> Assign every glyph to the **nearest staff on the whole page** (not the nearest
> of the current system — otherwise the top staff swallows glyphs from the
> system above).

That rule is correct, and necessary, for glyphs that *sit on or near their own
staff*: noteheads, rests, accidentals, clefs, dots, flags. It is wrong for
**stems and beams**, which are drawn away from the staff by design and can end
up geometrically closer to a neighbouring staff than to their own.

§2.3 tells you how to recognise beams (slanted = filled 5-point curves, flat =
rects) but never says how a beam gets attached to a staff, so the §2.2 rule gets
applied to them by default. It should not be.

## Why it fails, with measurements

From p3 system 2 of the reference file (SP = 4.375 pt):

```
staff 4 (piano RH)  614.7 .. 632.2   centre 623.45
staff 5 (piano LH)  659.3 .. 676.8   centre 668.05
```

Nearest-centre assignment tips from RH to LH at the midpoint of the gap,
y = 645.75 — only **3.10 SP below the RH bottom line**.

A down-stemmed lower voice in the RH staff clears that routinely. The actual
beam for the RH lower voice in bar 11:

```
beam   x 202.7 .. 240.8    y 645.2 .. 651.8   mid 648.76   -> assigned to LH
```

Its *top edge* is already at the tipping point. The stems of the same three
notes are no safer:

```
stem x=240.5  mid 640.66   -> RH   (5.1 pt of margin)
stem x=221.7  mid 642.85   -> RH   (2.9 pt)
stem x=203.0  mid 645.03   -> RH   (0.7 pt)
```

Three stems inside 5 pt of flipping. This is not a quirk of one engraving. Any
grand staff, and any vocal staff carrying a stem-down lower divisi voice, sits
in the same geometry. A stem only has to reach ~3 SP below its staff.

## The symptom, and why it is easy to misread

The beam vanishes from its own staff's beam list, so every note in that beam
group loses its flag/beam count and is read as a **quarter instead of an
eighth**. The bar then overruns.

In this file the damage was:

- 9 bars (piano RH bars 11, 12, 13 and their identical repeats at 23–25 and
  35–37) where the voice splitter could not make both voices sum to the meter.
- The lower voice summed to 180 in a 144 bar — three notes read 24 instead of 12.

The trap: the *upper* voice in those bars was fine, and the bar-length check
fires on the staff, not the voice. It is tempting to read "one staff is 36 over"
as a dot or tuplet misread and go looking in the wrong place. The give-away is
that the over-run is always a multiple of one beam group's worth of notes, and
always in a staff that has two voices.

## The fix

Do not assign stems or beams to a staff at all. Keep them in a **page-global**
list and let each staff query it:

```python
# per page, not per staff
V = [...]   # all vertical lines of stem linewidth
B = [...]   # all beam rects and 5-point filled curves
```

A stem is claimed by a notehead when its x matches the notehead's left or right
edge and its y-range reaches the notehead's baseline. A beam is counted for a
stem when it crosses the stem's x **and** its interpolated y falls inside the
stem's y-span. Both tests are already in the pipeline; they just need to run
against the page-global list instead of a pre-filtered per-staff one.

This is safe, and strictly safer than proximity, because the y-test is what
discriminates. Staves are ~46 pt apart here; a stem is ~11–15 pt long. A beam
belonging to another staff at the same x is 30+ pt away from this stem's span
and cannot be inside it. Proximity throws away the very information that
resolves the ambiguity.

Note the ordering consequence: stem assignment must also drive **chord
grouping**. Group noteheads that share a stem, not noteheads that share an x.
A stemless whole note and a stemmed note printed at the same x in different
voices are a different bug with the same smell (bar summed to 288 in piano LH
bar 1 before this was fixed).

## The check that closes the loop

Once stems and beams are page-global, staff assignment for the remaining glyphs
can be verified outright:

> Every notehead's computed staff position must be a whole number of half staff
> spaces.

A notehead assigned to the wrong staff lands on that staff's grid at a
non-integral position, because two staves in a system are at arbitrary vertical
offsets from each other. On this file all 1,949 noteheads came in within 0.12 of
an integer — including the ledger-line notes sitting in the grand-staff gap,
which is exactly where a proximity rule is least trustworthy. One line of code,
and it is the only positive evidence that nearest-staff assignment worked
everywhere rather than merely not having been caught failing.

Worth adding to §5 as a numbered check alongside the cross-staff onset test.

## Suggested edits

1. **§2.2** — after the nearest-staff paragraph, add a sentence scoping it:
   applies to glyphs drawn on or beside the staff, *not* to stems and beams.
2. **§2.3** — add a short subsection on attaching stems and beams: page-global
   list, x-match plus y-containment, with the 3 SP tipping-point figure as the
   reason.
3. **§3.1** — note that chord grouping keys on a shared stem, not shared x.
4. **§5** — add the notehead-position integrality check.
