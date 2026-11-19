#!/usr/bin/env python3
"""The app's icon: the front panel's LEVEL knob, drawn by the native UI itself.

    python3 examples/app_icon.py EXPORT.nvx [OUT.png]

nvlive --app renders the laptop layout headless at 6x (11520x6480, SDL's
offscreen driver) and saves the frame; the knob -- its centre and its
knurled ring's radius measured there (10860, 680; 444) -- is cut square,
1.09 of the ring out (the LEVEL label left below the cut), and scaled to
1024x1024: ios/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png by
default. iOS rounds its corners. Rerun when the knob's look changes; the
measurements hold while the front panel's layout does."""
import os
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CX, CY, R, MARGIN = 10860, 680, 444, 1.09


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out = argv[2] if len(argv) > 2 else os.path.join(HERE, "ios", "Assets.xcassets", "AppIcon.appiconset",
                                                     "AppIcon-1024.png")
    with tempfile.TemporaryDirectory() as tmp:
        shot = os.path.join(tmp, "big.ppm")
        script = os.path.join(tmp, "s.txt")
        with open(script, "w") as f:
            f.write("wait 2500\nshot %s\nquit\n" % shot)
        session = os.path.join(tmp, "session.json")
        with open(session, "w") as f:
            f.write("{}\n")
        env = dict(os.environ, SDL_VIDEODRIVER="offscreen", NUI_SIZE="11520x6480", NUI_SCRIPT=script)
        subprocess.run([os.path.join(HERE, "nvlive"), argv[1], "--session=" + session, "--app-windowed",
                        "--midi=/dev/null", "--device=null"], env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(shot).convert("RGB")
        r = int(R * MARGIN)
        im.crop((CX - r, CY - r, CX + r, CY + r)).resize((1024, 1024), Image.LANCZOS).save(out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
