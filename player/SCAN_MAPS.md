# A player map for a song whose only score is a scan, with human-sung stems

The worked example is `~/Dropbox/NJGMC/2026 Fall/Let There Be Peace on Earth/` (its `_build/` folder). Song folders hold the
scan PDF at the top, the Matthew Curtis mp3s in `Matthew Curtis <song>/`, and the separated stems in `Human-sung stems/`
(`<mp3 name>_(Vocals)_MDX23C-8KFFT-InstVoc_HQ.wav`). The scan PDF is the score the player shows.

Transcribe the voice staves only: the accompaniment track is the map's `I` stem, so the piano is never needed.

1. **Pages and systems.** `pdftoppm -r 300 -png SCAN.pdf _build/pages/p` then
   `python3 player/cut_systems.py _build/pages _build/systems 2:2,4,4 3:4,4,4 ...` (page number, then each system's staff
   count, top first; it checks the count against the staves it finds). It writes `_build/systems.json`.
2. **Read and type.** Look at each system's voice staves (crop at about 40% of 300 dpi; zoom with `scanproof zoom` where in
   doubt) and type `_build/score.txt` in the format in `player/staff_text.py`'s docstring: one line per staff per bar,
   sounding pitch (a G8 clef sounds an octave below the written note), `@parts T=Tenor_1,Tenor_2 B=Baritone,Bass`, `@clef`,
   `@key`, `@meter`, `@tempo`. A chord's notes go to the staff's parts from the top down. Name the parts after the stems
   (the Predominant mp3s say which voices exist). Then
   `python3 player/staff_text.py _build/score.txt "<song> (voices, from the scan).musicxml"`; it checks every bar's length.
3. **Proofread with scanproof** (SKILL.md 1.2): one project per staff count (`_build/proofA`, `proofB`, ...), `musicxml`
   source with `{"part": name, "staff": 1}` per part on each voice staff, piano staves with `"source": []`, `first_bar`.
   `python3 -m scanproof bars proof.json`, check the count per system, write `bars.json` with each system's printed
   `first_bar`; `python3 -m scanproof check proof.json BARS...` (only bars in that project); look at every finding on the
   voice staves (the piano's "extra printed column" findings are expected: it isn't transcribed). Hollow-head misses are
   the detector's.
4. **Second proof: the stems.** `player/pitch_guide.py FOLDER XML check` after a first map. Where print and stems disagree
   in one part only, the print wins; say so in the handback.
5. **Accompaniment.** Measure its start against a Predominant mix by cross-correlation (often 1.000 s early in his sets) and
   write it aligned as `Human-sung stems/Accompaniment (aligned to the UVR stems).wav`; a set without one: the separator's
   instrumental output. Its level comes after the map is made (step 6): `player/balance_check.py FOLDER BALANCED.mp3 --write`
   sets it to its balance against all the voices in the Balanced Voices mix, as the player mixes them, and points the map
   at the `(balanced)` copy. Not the Predominant mixes: they duck the accompaniment under the featured voice, and a level
   taken from them came out 5 to 20 dB too soft. With no Balanced mix, give a ratio in dB instead (-6.6 was the median).
6. **Map.** `python3 player/make_map_scan.py FOLDER --score SCAN.pdf --xml XML --systems _build/systems.json --proofs
   _build/proofA _build/proofB --stems "T1=..." ... "I=..." --part-stems "Tenor 1=T1" ... --staff "Tenor 1=T" ...
   --tempo N --warp --warp-beat`, then `pitch_guide.py ... check` (over 0.9 is right); if it fails, `pitch_guide.py ...
   guide GUIDE.txt` and rerun with `--guide`, and `--pin BAR.BEAT=SECONDS` read from the sung pitch where a guide can't
   follow (repeats, long final holds). See README.md's "Human-sung tracks" paragraph.
7. **Balance** the accompaniment (step 5). **Leave** `Human-sung stems/How player map.json was made.txt` (what was used, any pins, the pitch-check figure), and
   keep the Cantai map, if any, as `player map (Cantai).json`.

Two parts sharing one "copy" track (e.g. "(Tenor 1) copy Tenor Predominant" and "(Tenor 2) copy Tenor Predominant", byte
for byte the same) are one voice: give both parts the same stem key.
