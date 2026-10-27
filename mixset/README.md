# mixset

A human singer's finished practice set: a Balanced mix, an Accompaniment track, and a Predominant
and a Muted mix per part, with no stems. These tools line the files up, show which voice sings
where, splice a part's track from the set's other mixes, and retime existing follow-along videos
onto the new audio without redrawing a frame.

SKILL.md 9.6 (the tracks) and 10.4 (the videos) are the method.

| module | what it does |
| --- | --- |
| `lags` | each file's lead against the Accompaniment track, at the start and the end |
| `featured` | the featured voice of each part, 3 x Predominant - Muted (factor measured), level per hop |
| `splice` | a part's track by seconds from other mixes of the set, crossfaded; encoder gain checked |
| `timemap` | old audio -> new audio: `dtw`, `refine`, `local` (one stretch, ends pinned), `build` (knots) |
| `retime` | an old variable-frame-rate video moved onto the new mp3 through the knots |
| `check` | `frames` (where planned, audio unshifted) and `sync` (the lights against the sound) |

```
python3 -m mixset.lags acc.mp3 bal.mp3 pred_T1.mp3 muted_T1.mp3 ...
python3 -m mixset.featured acc.mp3 "Tenor=pred_T.mp3,muted_T.mp3" "Bass=pred_B.mp3,muted_B.mp3" --wav F/
python3 -m mixset.splice out.mp3 --base pred_T1.mp3 --ref bal.mp3 --take "30.0-116.2=pred_T2.mp3" --post 0.846
python3 -m mixset.timemap dtw old_piano.wav new_acc.mp3 pathA.npy
python3 -m mixset.timemap refine old_piano.wav new_acc.mp3 pathA.npy winA.npy
python3 -m mixset.timemap build knots.npy --windows winA.npy --windows winB.npy --manual pins.npy --png knots.png
python3 -m mixset.retime "old - (Tenor 1) predominant.mp4" knots.npy "new - (Tenor 1) predominant.mp3" out.mp4 --lag 1.0
python3 -m mixset.check sync out.mp4 "new - (Tenor 1) predominant.mp3"
```

Needs `librosa`, `soundfile`, `scipy`, `matplotlib` (pictures only) and ffmpeg.
