#!/usr/bin/env bash
# Render a MIDI and put it in a room.
#
# The reverb is not one setting: it belongs to the instrument and to where you
# are standing. These four are the ones settled by ear, and they lived only in
# a notes file until now.
#
#   usage: ./render-space.sh IN.mid OUT.wav [space] [tuner] [vol]
#
#     space   nave    an organ heard a few rows back      (default)
#             far     an organ from across the building -- the lines wash
#             cath    the closer cathedral, more definition
#             chamber a piano's room
#             corpus  one hall for the whole survey, deliberately even
#
# TUNING_MASTER_DB=-14 leaves headroom for the tail and the final -1 dBFS
# normalise. vol defaults by space; lower it if a dense registration clips --
# the tail sums onto peaks that are already hot, so density decides it, not a
# flat number. Always check the Flat factor line this prints: it must be 0.00.
set -e
if [ $# -lt 2 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    sed -n '2,25p' "$0" | sed 's/^# \?//'
    exit 2
fi
IN="$1"; OUT="$2"; SPACE="${3:-nave}"; TUNER="${4:-hybridharm}"; VOL="$5"
case "$SPACE" in
  # reverberance HF-damp room stereo pre-delay wet-gain
  nave)    CHAIN="pad 0 6 reverb 92 12 100 100 18 -2.0";  DEFVOL=0.5 ;;
  far)     CHAIN="pad 0 7 reverb 96 10 100 100 12 -0.5";  DEFVOL=0.45 ;;
  cath)    CHAIN="pad 0 6 reverb 88 15 100 100 28 -3.5";  DEFVOL=0.5 ;;
  chamber) CHAIN="pad 0 5 reverb 60 20 100 100  0 -6.0";  DEFVOL=0.5 ;;
  corpus)  CHAIN="pad 0 4 reverb 45 25  85 100 20 -6.0";  DEFVOL=1.0 ;;
  *) echo "unknown space: $SPACE (nave|far|cath|chamber|corpus)" >&2; exit 2 ;;
esac
VOL="${VOL:-$DEFVOL}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
TUNING_MASTER_DB=-14 python3 "$(dirname "$0")/blockrender.py" "$IN" "$TMP/dry.wav" "$TUNER"
sox "$TMP/dry.wav" "$OUT" vol "$VOL" $CHAIN gain -n -1
echo "space=$SPACE tuner=$TUNER vol=$VOL -> $OUT"
sox "$OUT" -n stats 2>&1 | grep -E "Pk lev dB|RMS lev dB|Flat factor"
