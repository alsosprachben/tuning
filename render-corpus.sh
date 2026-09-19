#!/usr/bin/env bash
# Render the corpus to ~/Downloads/bwx-renders as MP3, one file at a time.
#
# Lived in a session scratchpad for a long time and the README said so; it is
# here now because a corpus you cannot rebuild is not a corpus you can compare
# against. Serial on purpose -- a parallel run was killed part-way once, and the
# point of this is an even survey rather than speed.
#
#   ./render-corpus.sh                    # everything in corpus.txt
#   ./render-corpus.sh a.mid b.mid        # just these
#   ROOM=church ./render-corpus.sh ...    # a different building
#
# ONE ROOM, TOLD TO BOTH HALVES. This is the part that changed. It used to
# finish with `sox reverb`, a generic algorithmic tail bolted onto a render
# that had already computed its own first-order reflections -- a hall's early
# reflections in front of a reverb unit's tail, which is two different rooms.
# blockrender now computes the images against TUNING_ROOM and drops a
# `.room.json` sidecar beside the wav; roomtail.py reads that sidecar and
# convolves the diffuse field of the SAME room, with the directivity the render
# actually measured rather than a scalar guess. So TUNING_ROOM is exported
# once and both halves see it. Setting it for one and not the other is the
# specific mistake this arrangement exists to prevent.
#
# `hall` is the default because the corpus is mostly ensemble music. The rooms
# are hall, chamber, chapel and church; an organ wants church (see
# examples/organ.py), and it is not a reverb setting, it is a different
# building -- four times the volume with a tenth the absorption.
#
# NO MORE `pad 0 4`. That existed to give a synthetic reverb somewhere to ring
# into. roomtail convolves, so it extends the file by its own impulse response
# (2.6 s in the hall) and the tail is real.
#
# TUNING_MASTER_DB=-14 leaves room for the tail and the final -1 dBFS
# normalise. It is 2 dB lower than a single piece needs (organ.py uses -12)
# because this is a survey: it has to hold the loudest thing in the corpus
# without clipping, and since today that includes overdriven guitars.
#
# A NOTE ON TIME. Voices with a valve amplifier -- GM 18 rock organ, GM 26-31
# electric guitars -- emit distortion partials, and a lot of them: bwx37 is 31
# seconds of audio and 95,000 partials, rendering at 1.6x realtime where a
# clean voice manages 30x or better. A corpus with guitars in it is a much
# longer run than it used to be.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HOME/Downloads/bwx-renders}"
ROOM="${ROOM:-hall}"
TUNER="${TUNER:-hybrid}"
MASTER_DB="${MASTER_DB:--14}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT"
export TUNING_ROOM="$ROOM"
if [ $# -gt 0 ]; then FILES=("$@"); else mapfile -t FILES < "$HERE/corpus.txt"; fi
echo "--- $ROOM, $TUNER, master $MASTER_DB dB, ${#FILES[@]} files -> $OUT ---"
n=0; ok=0; fail=0; t0=$(date +%s)
for f in "${FILES[@]}"; do
    [ -n "$f" ] || continue
    n=$((n+1))
    b=$(basename "$f" .mid); b=$(basename "$b" .MID)
    if [ ! -f "$f" ]; then echo "MISS $b"; fail=$((fail+1)); continue; fi
    s=$(date +%s)
    if ! TUNING_MASTER_DB="$MASTER_DB" timeout 1800 python3 "$HERE/blockrender.py" \
            "$f" "$TMP/r.wav" "$TUNER" >/dev/null 2>&1; then
        echo "FAIL $b"; fail=$((fail+1)); rm -f "$TMP"/r.*; continue
    fi
    # The sidecar written beside r.wav is what makes this the same room as the
    # render; roomtail finds it by name, so the two must stay side by side.
    if ! timeout 900 python3 "$HERE/roomtail.py" "$TMP/r.wav" "$TMP/t.wav" >/dev/null 2>&1; then
        echo "TAIL $b"; fail=$((fail+1)); rm -f "$TMP"/r.* "$TMP/t.wav"; continue
    fi
    sox "$TMP/t.wav" "$TMP/n.wav" gain -n -1 2>/dev/null \
      && lame --quiet -V2 "$TMP/n.wav" "$OUT/$b.mp3" 2>/dev/null \
      && { ok=$((ok+1)); printf "ok   %-28s %4d/%d  %4ds\n" "$b" "$n" "${#FILES[@]}" "$(( $(date +%s) - s ))"; } \
      || { echo "POST $b"; fail=$((fail+1)); }
    rm -f "$TMP"/r.* "$TMP/t.wav" "$TMP/n.wav"
done
echo "--- $ok rendered, $fail failed, $(( $(date +%s) - t0 ))s ---"
