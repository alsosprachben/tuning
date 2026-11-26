#!/bin/bash
# devloop.sh -- run once in Terminal.app on the Mac (your own session: signing
# works there, not over ssh). It waits for ios/.go -- touched over ssh after
# the archives are built -- then, for each device given or (none given) each
# paired iPad or iPhone that is connected now, builds the app signed for it
# (the first build for a new device registers it with the team) and installs
# it; ios/.done gets 0 if every install worked (the log: ios/.build.log).
# Ctrl-C to stop.  Usage: ios/devloop.sh [DEVICE_UDID ...]
cd "$(dirname "$0")" || exit 1
devices() {
    if [ $# -gt 0 ]; then echo "$@"; return; fi
    xcrun devicectl list devices --json-output .devices.json > /dev/null 2>&1
    /usr/bin/python3 - <<'PY'
import json
try:
    ds = json.load(open('.devices.json'))['result']['devices']
except Exception:
    ds = []
for d in ds:
    hw, cp = d.get('hardwareProperties', {}), d.get('connectionProperties', {})
    if hw.get('platform') == 'iOS' and cp.get('pairingState') == 'paired' and cp.get('tunnelState') != 'unavailable':
        print(hw.get('udid'))
PY
}
echo "devloop: waiting for builds (devices: ${*:-every connected one}) -- Ctrl-C to stop"
while true; do
    if [ -f .go ]; then
        rm -f .go .done
        echo "devloop: building $(date +%H:%M:%S)"
        rc=0; n=0
        : > .build.log
        for DEV in $(devices "$@"); do
            n=$((n + 1))
            echo "== $DEV" >> .build.log
            ( xcodebuild -project ClavitoneIOS.xcodeproj -scheme Clavitone -sdk iphoneos -destination "id=$DEV" \
                  -derivedDataPath build -allowProvisioningUpdates build \
              && xcrun devicectl device install app --device "$DEV" build/Build/Products/Debug-iphoneos/Clavitone.app ) \
                >> .build.log 2>&1 || rc=1
            echo "devloop: $DEV done (rc so far $rc)"
        done
        [ $n -eq 0 ] && { echo "no device connected" >> .build.log; rc=2; }
        echo $rc > .done
        echo "devloop: done ($rc, $n device(s)) $(date +%H:%M:%S)"
    fi
    sleep 1
done
