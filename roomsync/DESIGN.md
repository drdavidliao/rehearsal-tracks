# roomsync: a phone recording of a rehearsal, timed to the score beat by beat (design, 2026-11-25, for approval)

Why: the automatic maps fitted an offset and
a tempo ratio per 6 s window and slipped whole beats after holds, at tempo changes, in repeated material and through
a stringendo (song 2: 31 of 172 bars more than a beat off, while every check passed).

**The model is a singer who knows the piece.** That singer never silently loses a beat, because they go through the
music beat by beat in order. They know which pitches come next and which beats have an attack and which hold. They
count from the last thing they recognised, and they never lose count in a groove. Losing a beat would mean hearing a
tempo jump the music doesn't have. Each part of the design below stands in for one of those habits.

## Output
For one room recording R (seconds of its audio) and one song's player map:
- `r_k`, the room time of every played beat k, in performance order (repeats expanded as the player map has them).
  The time map is piecewise linear through (human-sung set's time of beat k, r_k). It is the same kind of knot list the build
  folders use (`map knots.npy`: human-sung Balanced seconds → MOV seconds), so render.py and the rest take it unchanged.
- Per bar: a **margin** (how much worse the best map is if that bar is forced a beat early or late) and a **flag**
  when the margin is small or the bar is one the user named.
- A report: flagged bars with MOV times, every check's result, and the inputs as measured.

## Inputs, and what each gives
| input | gives | where |
|---|---|---|
| room recording (MOV) | the room's audio; htdemucs_ft stems: Vocals, Drums, Bass, Other | `separate.sh` (declicks first if the tick check finds a tick) |
| player map.json | every beat's human-sung time and bar; every note's part, beat, MIDI pitch, start/end | the song folder |
| human-sung vocal stem (Balanced Voices, separated) and Accompaniment | the studio performance's sound at each beat | `Human-sung stems/` |
| MusicXML (full, from the original) | fermatas; tempo words (rall., rit., stringendo, a tempo, "suddenly slow"); meter and tempo changes | the song folder |
| the user's answers (below) | structure; the bars that might confuse | asked once, before the first run |

## Step 0: two questions to the user, before anything runs
1. **Structure.** "Is the recording one continuous take? Which repeats and cuts did the room take?" The default is as
   the player map plays it. Scope: one continuous take. A take that stops and restarts is out of scope, and the user is
   asked to give the restart times so it can be cut into pieces.
2. **"Which bars might confuse an auto-syncer?"** Holds, places where the room does something other than the page
   (clapping early, a held fermata, a skipped bar), vamps, solos, a pianist filling. Each answer becomes either a
   loose-tempo bar, a required landmark ("the claps start at 35 beat 2"), or a bar flagged for the ear check
   whatever the margin says. Nothing the user didn't say is assumed: SKILL.md 10.3b's early clap by the room
   turned out to be two errors cancelling (the post-mortem, 1d).

## Step 1: the clock (failure class F4)
The player map's times must be put on the human-sung vocal stem's clock before anything else. In song 1 the map ran
1.000 s ahead of the Balanced files; in song 2 the offset was 0. Measure it on every song: the player map's
note starts (all parts) as an onset train, against the human-sung vocal stem's onset envelope, lag searched ±2 s. The
peak must stand clear: margin over the best lag outside ±0.1 s at least 0.05 correlation, or stop and say so. Apply
the lag once, in one place.

## Step 2: what the room sounds like at each beat (features, 20 ms frames)
Room, from its stems:
- `V_on`: the vocal stem's onset strength. `A_on`: onset strength of Other + Bass (piano). `D_on`: the drum stem's
  onset strength (claps). Each is z-scored over a sliding 10 s window, so a loud stretch doesn't dominate.
- `V_ch`: the vocal stem's chroma (CQT, 12 bins, normalised per frame, zero where the stem is below its noise floor).
- `P_ch`: the same for Other + Bass (the piano), kept apart from `V_ch`. The voices and the piano are two harmonic
  streams. Where one is ambiguous (a held vocal chord, a piano vamp) the other usually moves, and where they agree
  the beat is pinned twice.

Expectations at each beat, from two sources independent of each other:
- **The score (what the singer and the pianist read):** for every frame of human-sung time, the pitch classes the voices
  sound there (from the player map's notes, weighted by how many voices), giving a 12-bin template. The piano's are
  read separately from the full MusicXML's Piano part (both songs have one; song 1 also has the clap staff).
  Also per beat, for voices, piano and claps separately: whether that stream attacks there, or holds or rests.
- **The human-sung recording (what the singer has rehearsed with):** the same `V_on`, `A_on`, `D_on`, `V_ch` and `P_ch`,
  from its vocal stem and its Accompaniment.

## Step 3: going through the music beat by beat (the alignment)
A dynamic programme over states (beat k, room time r_k, room length of the previous beat d), on the 20 ms grid.
- **Match of beat k:** for a candidate room span [r_k, r_k + d], the human-sung set's span for beat k is stretched linearly onto
  it, and each frame pair contributes: chroma agreement of room `V_ch` with the voices' score template and with
  the human-sung `V_ch`, and of room `P_ch` with the piano's template and the human-sung `P_ch` (cosine); and products of
  matching onset strengths (`V_on`·`V_on`, `A_on`·`A_on`, `D_on`·`D_on`). An attack in the score at beat k's start
  weighs the room's onset in that stream. Weights: the terms z-scored and equal, so nothing is tuned before the
  benchmark has been run.
- **The room makes mistakes, and no single stream may overrule the rest.** Singers and pianists sing wrong notes,
  come in early or late, drop out, and fill in (in song 2's Maestoso). So each
  stream's match per beat is capped: a beat where one stream disagrees badly costs a fixed amount, not an unbounded
  one. Where one stream disagrees with all the others for several beats running (a pianist improvising, a section
  out), its weight there drops, and the report names the stretch. A single wrong beat moves nothing, because the
  counting below has to agree on either side of it.
- **Counting (tempo prior):** the cost of the change in log(room beat length ÷ human-sung beat length) from beat k−1 to k
  (the ratio, so the human-sung set's own rits don't count against the room). Its spread is tight in steady stretches, loose at
  fermatas, tempo words and their bars, meter or tempo changes, beats after at least a bar with no sung or played attack,
  and bars the user named. Beat lengths are bounded to 0.3-4× the human-sung set's at the current ratio (8× at a fermata).
  So a one-beat slip in a groove costs two tempo jumps the score doesn't allow there, which the window fit never had to pay.
- **Landmarks:** a sung entry after at least a bar's rest, in both the score and the room's vocal stem, adds a strong
  match term at that beat. So does any landmark the user named.
- **Free start and end:** the footage can start and end mid-song (song 1 from bar 5's pickup, song 2 in
  bar 7). The first and last beats of R are free, chosen by the DP.
- **Search band:** r_k within ±6 s of a coarse chroma DTW (room vocals vs human-sung vocals). That is wider than the worst
  error yet seen (3.3 s). If the path touches the band's edge, widen it to ±12 s and run again (F5).
- Forward and backward passes are both kept, so every state's best path cost through it is known.

## Step 4: confidence per bar
For beat 1 of each bar, the margin is the best path cost with that beat forced at least 0.3 beat from its chosen time,
minus the optimum. It comes from the forward plus backward costs, with no extra runs. A bar is flagged when:
- its margin is below a threshold T;
- it is a bar the user named;
- or two variants of the run (without chroma, without onsets) put it more than 0.25 beat apart.

T is set on the benchmark (Step 6) as the smallest value that flags every bar more than 0.25 beat off. The report
says how many bars that flags, since those bars are what the user's ear check will cost.

## Step 5: fine timing
Each beat 1 is snapped to the strongest onset in the stem its score says attacks (voices, or piano where the voices
hold), within ±60 ms. It is left alone where no onset stands 2× over its surroundings. The snap is written down per bar.

## Step 6: the benchmark (run on every change to the aligner)
Ground truth: the two tap maps.
- Song 1: `map knots (from taps, refined).npy`, 143 bar starts.
- Song 2: `tap knots.npy`, 172 tapped beat 1s, raw taps (their own noise is about ±100 ms).

Compared at beat 1 of every bar both cover:
- **Pass:** no bar more than 0.5 beat off, median error at most 60 ms, every bar more than 0.25 beat off flagged.
- **Report:** median, 90th percentile, worst, bars over 0.25/0.5/1 beat, bars flagged, and the same per stretch
  (holds, groove, vamp, waltz, stringendo).
- **Overfitting guard:** with two songs, any weight or threshold fitted on one is reported on the other
  (leave-one-song-out). The equal weights in Step 3 are fitted to nothing.

## Failure classes and their checks
| # | fails how | check (on every run) |
|---|---|---|
| F1 | whole-beat phase error | benchmark (when building); margins and the variant disagreement (every run); the user's ear check on flagged bars |
| F2 | sub-beat error (over ~80 ms) | benchmark median; onset lag of room vocals vs the warped human-sung stem per 5 s, ±100 ms, after Step 5 |
| F3 | structure wrong (a repeat skipped, a cut) | the user's answer; a run of bars with match cost far above the song's median is reported as "structure?" |
| F4 | clocks not lined up | Step 1's lag and margin; stop if unclear |
| F5 | true path outside the band | path within 0.5 s of the band's edge → rerun at ±12 s |
| F6 | start or end wrong | first chosen beat vs the room's first vocal/piano onset; last vs the room's sound stopping; both listed |
| F7 | the room in another key or out of tune | best circular shift of mean room chroma vs the score template must be 0; otherwise stop and say so |
| F8 | the phone's periodic tick in the onsets | autocorrelation of the >2 kHz onset envelope: a sharp peak not at a beat multiple → declick first |
| F9 | weights tuned to two songs | leave-one-song-out numbers in the report |
| F10 | a bar the room changed on purpose (a cut, an added hold, claps where the page has none) | the user's answer to question 2; the margin there |
| F12 | a performer's mistake taken as timing (a wrong note, an early entry, a fill) | per-stream caps; the stretches where one stream was down-weighted, listed with MOV times; their margins |
| F11 | separation failed (a stem empty or bleeding) | per stem: loudness over the song, and the vocal stem's chroma agreement with the score template over the whole song |

## Assumptions only data can settle, and the test for each
- Beat-level chroma of a phone recording's separated vocals is distinct enough beat to beat to fix phase. Test: the
  benchmark, chroma-only variant.
- The room keeps the human-sung set's beat lengths up to a smoothly changing ratio, except where the score marks a change. Test:
  the tap maps' ratio, beat to beat, against the marks (computed before the aligner, as `ratio_check.py`).
- One weight per term works for both songs. Test: leave-one-song-out.

## Not in this build
- **The ear-check page** for flagged bars: 15-20 s excerpts with a soft click on the map's beat 1s, answered
  on/early/late or tapped along, with taps saved raw. It is a page the user operates, so it gets its own walkthrough,
  a fresh-subagent critique and approval first. This build produces the flagged list it will need.
- Rendering. The knots go to the existing render.py.

## Files (all in this folder, each listed in README.md)
`separate.sh`, `features.py`, `clock.py`, `align.py` (Steps 3-5), `benchmark.py`, `ratio_check.py`, `report.py`.
Bulky intermediates (stems, feature arrays) go to a scratch folder; every script regenerates them.

## As built (2026-11-25/26), changes from the design above, and why
Each was found by a check or by `diag.py`, and is written into the code where it lives.
- **Clock check:** the onset detector peaks about 70 ms after an attack on every stream (+70 ms on both songs'
  voices), so the check is relative: the voices' lag must be 0-120 ms and the piano's within 60 ms of it. Balanced
  seconds = map seconds −0.998 (song 1), +0.000 (song 2), matching the known 1.000 and 0.
- **Coarse DTW** collapsed song 2's whole recording onto 40 s of the human-sung set until its slope was held to 1/2-2.
- **The player map's beats can run backwards** (song 2 bars 92, 93, 121, 162, 165, 170: bar 170's beat 1 is
  −0.061 s). score.py re-spaces such a bar's beats evenly and lists them. This is a defect in that player map.
- **Tuning drift:** song 2's room sang a semitone flat for about 20 s in the Maestoso while its piano stayed in
  tune (`key_check.py`). Vocal chroma now takes the best of shifts −1, 0, +1.
- **Vocal activity** is compared with when the human-sung voices sound, not the score's note lengths (staccato syllables).
- **Two kinds of looseness:** a jump (fermata, end of a hold, entry after rests, a new tempo) and a drift (rall.,
  stringendo, meter change, the track maker pushing or pulling; sigma 0.12 per beat). The first build made drifts nearly as
  loose as jumps, which left song 2 with almost no counting on half its beats.
- **Unmarked holds** (rules (a)-(c) in score.py) were added after `ratio_check.py` on song 2's tap map, so that
  song's benchmark is informed by them; song 1's is not.
- **The benchmark counts tapped bars only** (song 1 3-144, song 2 8-175).
