#!/bin/bash
# A FILE IN THE STUDIO ROOM, for listening: blockrender on the GPU with the
# room forced to the studio (TUNING_ROOM=studio: the file's GS reverb macro
# does not choose another), its reverb-send bus beside it; roomtail's late
# field from the same room; an MP3 of the result.
#
#     examples/studio_render.sh IN.mid OUT_BASE [TUNER]
#
# writes OUT_BASE.wav (dry), OUT_BASE.send.wav, OUT_BASE.room.json,
# OUT_BASE_room.wav and OUT_BASE_room.mp3. Under a 3.5 GB memory cap; stops
# if live is playing.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
IN=$1; OUT=$2; TUNER=${3:-hybrid440}
if pgrep -x nvlive >/dev/null || pgrep -f "^python3? [^ ]*(livetui|/live)\.py" >/dev/null; then
    echo "live is playing: not rendering"; exit 3
fi
export TUNING_ROOM=studio TUNING_GPU=1
systemd-run --user --scope -q -p MemoryMax=3500M -p MemorySwapMax=0 -E TUNING_ROOM -E TUNING_GPU \
    python3 "$HERE/blockrender.py" "$IN" "$OUT.wav" "$TUNER" 2>&1 | tee "$OUT.render.log"
python3 "$HERE/roomtail.py" "$OUT.wav" "${OUT}_room.wav" 2>&1 | tee "$OUT.room.log"
lame --quiet -V2 "${OUT}_room.wav" "${OUT}_room.mp3"
echo "-> ${OUT}_room.mp3"
