#!/bin/bash
# devloop.sh -- run once in Terminal.app on the Mac (your own session: signing
# works there, not over ssh). It waits for ios/.go -- touched over ssh after
# the archives are built -- then builds the app signed, installs it on the
# iPad, and writes its exit code to ios/.done (its log to ios/.build.log).
# Ctrl-C to stop.  Usage: ios/devloop.sh [DEVICE_UDID]
cd "$(dirname "$0")" || exit 1
DEV=${1:-00008120-00160D500E500032}
echo "devloop: waiting for builds (device $DEV) -- Ctrl-C to stop"
while true; do
    if [ -f .go ]; then
        rm -f .go .done
        echo "devloop: building $(date +%H:%M:%S)"
        ( xcodebuild -project ClavitoneIOS.xcodeproj -scheme Clavitone -sdk iphoneos -destination "id=$DEV" \
              -derivedDataPath build -allowProvisioningUpdates build \
          && xcrun devicectl device install app --device "$DEV" build/Build/Products/Debug-iphoneos/Clavitone.app ) \
            > .build.log 2>&1
        rc=$?
        echo $rc > .done
        echo "devloop: done ($rc) $(date +%H:%M:%S)"
    fi
    sleep 1
done
