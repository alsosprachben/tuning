#!/usr/bin/env python3
"""Does the native file check (native/filecheck.h) report what mt32check.py does?
    python3 examples/filecheck_check.py [file.mid ...] [--from=PATH]
Each file read by native.Midi with TUNING_CHECK=1, its findings against
mt32check.check()'s, word for word, and the muxed test against
mt32check._multiplexed. Also: filecheck.h's registerable programs against
patch_map.PROGRAM_CLASS. Files: the arguments, else the corpus (corpus.txt)
plus the MT-32 test files in ~/Music/nvlive_tests. Parsing only: light.
"""
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import mido             # noqa: E402
import mt32check as MC  # noqa: E402
import native as N      # noqa: E402
import patch_map as PM  # noqa: E402

REGISTERABLE = (6, 16, 17, 18, 19, 20, 55)      # filecheck.h's registerable()


def files(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if args:
        return args
    frm = next((a.split("=", 1)[1] for a in argv if a.startswith("--from=")), None)
    if frm:
        if os.path.isdir(frm):
            return sorted(os.path.join(frm, f) for f in os.listdir(frm) if f.lower().endswith((".mid", ".midi")))
        return [l.strip() for l in open(frm) if l.strip()]
    out = [l.strip() for l in open(os.path.join(HERE, "corpus.txt")) if l.strip() and not l.startswith("#")]
    t = os.path.expanduser("~/Music/nvlive_tests")
    if os.path.isdir(t):
        out += sorted(os.path.join(t, f) for f in os.listdir(t) if f.startswith(("cm32", "mt32")))
    return [f for f in out if os.path.exists(f)]


def main(argv):
    reg = tuple(p for p in range(128) if getattr(PM.PROGRAM_CLASS[p], "registerable", False))
    bad = 0
    if reg != REGISTERABLE:
        print("  registerable programs moved: patch_map %s, filecheck.h %s" % (reg, REGISTERABLE))
        bad += 1
    os.environ["TUNING_CHECK"] = "1"
    os.environ["TUNING_MT32_SEEN"] = "1"
    same = skipped = 0
    for f in files(argv):
        try:
            mid = mido.MidiFile(f)
            with contextlib.redirect_stdout(io.StringIO()):
                want = MC.check(f)
            muxed = MC._multiplexed(mid)
        except Exception as e:          # (a file mido cannot read: not the check's)
            skipped += 1
            print("  skipped %s: %s" % (os.path.basename(f), e))
            continue
        m = N.Midi(f)
        if m.error:
            skipped += 1
            print("  refused %s (%d)" % (os.path.basename(f), m.error))
            continue
        got = m.findings()
        if got == want and m.muxed() == muxed:
            same += 1
            continue
        bad += 1
        print("  DIFFERS %s (muxed %s vs %s)" % (os.path.basename(f), m.muxed(), muxed))
        for a, b in zip(got + [None] * len(want), want + [None] * len(got)):
            if a != b:
                print("    native: %s\n    python: %s" % (a, b))
                break
    print("file check: %d files identical, %d differ, %d skipped" % (same, bad, skipped))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
