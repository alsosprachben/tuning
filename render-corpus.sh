#!/usr/bin/env bash
# Render the corpus to ~/Downloads/bwx-renders as MP3, one file at a time.
#
# Lived in a session scratchpad for a long time and the README said so; it is
# here now because a corpus you cannot rebuild is not a corpus you can compare
# against. Serial on purpose -- a parallel run was killed part-way once, and the
# point of this is an even survey rather than speed.
#
#   ./render-corpus.sh              # everything in corpus.txt
#   ./render-corpus.sh a.mid b.mid  # just these
#
# TUNING_MASTER_DB=-14 leaves room for the reverb and the final -1 dBFS
# normalise. The reverb is one hall for the whole corpus, deliberately: these
# are comparison renders, and per-voice spaces would make the survey uneven.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HOME/Downloads/bwx-renders}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT"
if [ $# -gt 0 ]; then FILES=("$@"); else mapfile -t FILES < "$HERE/corpus.txt"; fi
n=0; ok=0; fail=0; t0=$(date +%s)
for f in "${FILES[@]}"; do
    [ -n "$f" ] || continue
    n=$((n+1))
    b=$(basename "$f" .mid); b=$(basename "$b" .MID)
    if [ ! -f "$f" ]; then echo "MISS $b"; fail=$((fail+1)); continue; fi
    if ! TUNING_MASTER_DB=-14 timeout 900 python3 "$HERE/blockrender.py" "$f" "$TMP/r.wav" hybrid >/dev/null 2>&1; then
        echo "FAIL $b"; fail=$((fail+1)); continue
    fi
    sox "$TMP/r.wav" "$TMP/n.wav" pad 0 4 reverb 45 25 85 100 20 -6 gain -n -1 2>/dev/null \
      && lame --quiet -V2 "$TMP/n.wav" "$OUT/$b.mp3" 2>/dev/null \
      && { ok=$((ok+1)); printf "ok   %-28s %4d/%d\n" "$b" "$n" "${#FILES[@]}"; } \
      || { echo "POST $b"; fail=$((fail+1)); }
    rm -f "$TMP/r.wav" "$TMP/n.wav"
done
echo "--- $ok rendered, $fail failed, $(( $(date +%s) - t0 ))s ---"
