roomsync: time a phone recording of a rehearsal to the score, beat by beat (DESIGN.md; results in results/).
Run order for a song: separate.sh -> features.py -> align.py (all, no_chroma, no_onsets) -> benchmark.py (when a tap map exists).
- DESIGN.md: the design, and "As built": what changed in building it, and why.
- songs.json: per song, the inputs, the room stems' scratch folder, the Balanced file, the tap map used as truth and which bars were tapped.
- separate.sh: room recording -> 44.1 kHz wav (declicked with song1's declick.py if DECLICK=1) -> htdemucs_ft stems via audio-separator (~/Models/uvr), into a scratch folder.
- score.py: per played beat, what the score says: attacks of voices / piano / claps, fermatas, tempo words, holds, entries after rests, and how loose the counting is (jump or drift); repairs a player map's backwards beats and lists them.
- features.py: onset strength, chroma and vocal activity of the room's stems and of the human-sung set's (the map's own stems), the score's chroma templates, and the clock check (writes features.npz and clock.json in the scratch folder).
- align.py: the aligner (beat-by-beat DP with the tempo prior, margins per bar, snap of each beat 1 to its onset); writes align_VARIANT.npz with the knots (human-sung Balanced s -> MOV s).
- benchmark.py: the aligner against the user's tap map per tapped bar; pass criteria and flags; writes results/benchmark VARIANT.txt.
- ratio_check.py: assumption test: how the room's tempo against the human-sung set's changes bar to bar on the tap map, steady vs marked loose; results/ratio check SONG.txt.
- key_check.py: F7, is the room in the human-sung set's key and tuning, per 20 s; results/key check SONG.txt.
- diag.py: why the aligner chose its path: the truth (or, --constrained, the model's best path within 0.15 s of it) and the aligner's path scored term by term per bar.
