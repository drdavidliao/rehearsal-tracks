#!/bin/sh
# Build ssshift (Signalsmith Stretch pitch shift with an independent formant shift).
# The library and its linear-algebra dependency are fetched at pinned versions into
# ~/.cache/voiceshift, and the binary is written there too (outside the repository).
#   sh voiceshift/build.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
C="${VOICESHIFT_CACHE:-$HOME/.cache/voiceshift}"
mkdir -p "$C"
if [ ! -d "$C/signalsmith-stretch" ]; then
    git clone -q https://github.com/Signalsmith-Audio/signalsmith-stretch.git "$C/signalsmith-stretch"
fi
git -C "$C/signalsmith-stretch" checkout -q a670068d9aeb64913331d5cc29337b19a457a7df
if [ ! -d "$C/linear" ]; then
    git clone -q https://github.com/Signalsmith-Audio/linear.git "$C/linear"
fi
git -C "$C/linear" fetch -q --tags
git -C "$C/linear" checkout -q 0.6.4
case "$(uname)" in
    Darwin) ACCEL="-framework Accelerate -DSIGNALSMITH_USE_ACCELERATE" ;;
    *) ACCEL="" ;;
esac
c++ -std=c++17 -O3 $ACCEL -I"$C/signalsmith-stretch/include" -I"$C/signalsmith-stretch" \
    -I"$C/linear/include" "$HERE/ssshift.cpp" -o "$C/ssshift"
echo "built $C/ssshift"
