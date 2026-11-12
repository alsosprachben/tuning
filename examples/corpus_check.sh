#!/bin/bash
# THE CORPUS, A FILE A PROCESS: each of corpus.txt's files through
# nvrender_check.py on its own, under its own memory cap and time limit,
# its word kept in STATE as it comes (nvrender_check --state) -- a file
# killed is that file's word ("killed"), the rest go on, and a run started
# again resumes where it was. Stops before a file when live is playing.
#
#     examples/corpus_check.sh STATE [SECONDS]
#
# NV_EXPORT_CACHE (if set) makes the file export once for every file.
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
STATE=$1
SECS=${2:-20}
CAP=${COVERAGE_CAP:-3500M}
touch "$STATE"
grep -v '^#' "$HERE/corpus.txt" | awk 'NF {print $1}' | while read -r f; do
    if grep -q "^$f	" "$STATE"; then
        continue
    fi
    if pgrep -x nvlive >/dev/null || pgrep -f "^python3? [^ ]*(livetui|/live)\.py" >/dev/null; then
        echo "live is playing: stopped before $f"
        exit 3
    fi
    systemd-run --user --scope -q -p MemoryMax=$CAP -p MemorySwapMax=0 \
        timeout ${COVERAGE_TIMEOUT:-1800} python3 "$HERE/examples/nvrender_check.py" "$f" "$SECS" --state="$STATE" \
        > /dev/null 2>&1
    rc=$?
    if ! grep -q "^$f	" "$STATE"; then
        printf '%s\t%s\n' "$f" "$([ $rc -eq 124 ] && echo "timed out" || echo "killed (exit $rc)")" >> "$STATE"
    fi
done
n=$(grep -c . "$STATE")
same=$(grep -c "	identical" "$STATE")
diff=$(grep -c "	DIFFERS\|	nvrender failed" "$STATE")
echo "corpus: $n files: $same identical, $diff differ, $((n - same - diff)) refused, killed or timed out"
