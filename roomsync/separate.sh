#!/bin/zsh
# Room audio -> 44.1 kHz stereo wav (declicked if DECLICK=1, with song1's declick.py) -> htdemucs_ft stems
# (Vocals, Drums, Bass, Other) via audio-separator from ~/Models/uvr. Bulky outputs go to OUT (a scratch folder).
#   separate.sh ROOM.mov OUT_DIR
set -e
IN="$1"; OUT="$2"; mkdir -p "$OUT/demucs"
ffmpeg -nostdin -y -loglevel error -i "$IN" -vn -ac 2 -ar 44100 "$OUT/room.wav"
SRC="$OUT/room.wav"
if [ "${DECLICK:-0}" = 1 ]; then
  python3 "/path/to/song folder/_build/declick.py" "$OUT/room.wav" "$OUT/room_declicked.wav" "$OUT/declick report.json"
  SRC="$OUT/room_declicked.wav"
fi
~/Models/uvr/venv/bin/audio-separator "$SRC" --model_filename htdemucs_ft.yaml --model_file_dir ~/Models/uvr/models \
  --output_dir "$OUT/demucs" --output_format WAV
ls -la "$OUT/demucs"
