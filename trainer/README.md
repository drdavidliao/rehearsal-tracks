# Pitch trainer

A phone page that walks one singer through a few notes of their part: out of time first (the phone sings a cue, then
listens; if they can't find the note it finds theirs and walks them there a half step at a time, then has them stop and come
back in after longer and longer gaps), then note to note, then in time at 60, 80 and 100% speed, with their part in the
track fading note by note as they earn it. Speaker and mic take turns, so no earbuds are needed.

    python3 trainer/build.py "<song folder>" --part Bass --bars 159-161 --out "<song folder>/Pitch trainer/bass-159-161" \
        --crop "12,328,108,548,166;12,82,338,192,381,12.2" --text "(an awkward jump)"

The song needs a `player map.json` (notes and times in the human-sung stems, the accompaniment as stem "I"). `--crop`
cuts the singers' PDF to the part's staff, one piece per system, in PDF points from the top; a sixth number moves a
piece down so the staves line up. Upload everything in the out folder except `test.html` to an HTTPS site (the mic
needs HTTPS). Progress is kept on the phone.

- `pitch.js`: the detector (period by NSDF, an octave check on the spectrum both ways, a 100 Hz low cut against
  rumble) and the guide voice's synth.
- `test.html`: the detector on made-up hard cases and on the part's own stem (as recorded, phone-filtered, an octave
  down). Every row should read pass.
- `index.html?sim&rate=8&auto=sing`: a simulated singer instead of the mic, the clock 8x; `?nomic` plays the real sounds
  with a silent input. `TRAINER_LOG` in the console has every cue, pulse and result.

Leeway, as people sing: "on the note" is their median over half a second within ±40¢ with 70% of it within ±75¢
(a scoop, vibrato and wobble pass; a semitone off fails); a re-entry skips their first 0.1 s and judges the next 0.3 s
to ±50¢. Repetitions are few: three stop/start gaps per new note (0.5, 1.5, 4 s, a miss repeats the gap), a missed
pair once more, one good take per step of fading their part out. The first version held them to ±35¢ on 85% of frames
with five gaps and two takes per step, and asked for repeats while their trace was mostly green.
