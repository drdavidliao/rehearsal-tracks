# voiceshift

Revoicing recorded practice tracks in audio: an SSA set to TTB, say.

The job, as done the first time: a publisher's SSA practice tracks, separated with Ultimate Vocal Remover, became a TTB set.
- **Pitch:** every part went an octave down.
- **Formants:** the envelope went down a minor third.
- **Assignment:** the Baritone took Soprano 2's line for a few bars and the Alto's line otherwise.
- **Balance:** set by what is heard, not by a meter.

SKILL.md Step 9.5 is the method. Syncing a choreography video to the tracks is `dance_sync.py` at the top of the repository (Step 10.3); it takes the bar grid `bargrid` measures.

| module | what it does |
| --- | --- |
| `build.sh` | builds `ssshift` (Signalsmith Stretch at pinned versions) into `~/.cache/voiceshift` |
| `shift` | pitch and formant shift of one stem; `--calibrate` corrects the engine's setting by the measured miss |
| `measure` | `compare` (pitch, envelope, offset, brightness), `loudness` (Zwicker), `tilt`, `vowels` (the shifter on synthetic vowels) |
| `bargrid` | where barlines fall in a steady-tempo recording, decided by the accompaniment's rests; measures the swing |
| `splice` | a part's stem from others, by bar ranges, with crossfades inside shared rests |
| `linelevels` | each sung line's level inside each stem, at its own harmonics |
| `presence` | restores "ring" (2–4 kHz) to match a reference stem's brightness |
| `audibility` | masking-adjusted audibility over the accompaniment; the gain that restores a reference's |

```
sh voiceshift/build.sh
python3 -m voiceshift.shift in.wav out.wav --pitch -12 --formant -3 --calibrate
python3 -m voiceshift.bargrid score.musicxml accompaniment.mp3 --part Piano
python3 -m voiceshift.splice bari.wav --base low.wav --take "24-27=t2.wav" --bar1 1.03 --bar 2.0
python3 -m voiceshift.presence t1.wav "t1 (presence).wav" --like low.wav
python3 -m voiceshift.measure loudness low.wav "t1 (presence).wav"
python3 -m voiceshift.audibility accompaniment.mp3 t1.wav original-s1.wav --new-gain 3 --accomp-gain 3.45
```

Needs `librosa`, `mosqito` (Zwicker loudness), `soundfile`, `scipy`, `lxml`, ffmpeg, and a C++ compiler for `build.sh`.
