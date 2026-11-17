#!/usr/bin/env python3
"""Does the native mux (native/partmux.h, TUNING_PARTS=names) read a file as
the reader reads mt32mux.py's output of it?
    python3 examples/partmux_check.py FILE.mid [...] [--velocity=none]
For each file: mt32mux.py IN OUT (into a temporary folder), then native.Midi
of OUT against native.Midi of IN under TUNING_PARTS=names -- every note,
controller, event and the length with ==, and the per-part report lines and
overlap counts against mt32mux's printout. Parsing only: light.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import native as N      # noqa: E402


def reading(path, env):
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        m = N.Midi(path)
        if m.error:
            return None, m.error
        return (m.notes(), m.ccs(), m.events(), m.total(), m.track_names(), m.mux_report()), 0
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main(argv):
    files = [a for a in argv[1:] if not a.startswith("--")]
    vel = next((a.split("=", 1)[1] for a in argv if a.startswith("--velocity=")), "scummvm")
    tmp = tempfile.mkdtemp(prefix="partmux_")
    same = bad = 0
    for f in files:
        out = os.path.join(tmp, os.path.basename(f))
        p = subprocess.run([sys.executable, os.path.join(HERE, "mt32mux.py"), f, out, "--velocity=" + vel],
                           capture_output=True, text=True)
        if p.returncode:
            print("  mt32mux failed on %s: %s" % (f, p.stderr[-300:]))
            bad += 1
            continue
        lines = [l[3:] for l in p.stdout.splitlines() if l.startswith("   ch")]
        ov = re.search(r"same-pitch overlaps: (\d+) if every part shared, (\d+) as assigned", p.stdout)
        want, e1 = reading(out, {})
        got, e2 = reading(f, {"TUNING_PARTS": "names", "TUNING_MT32_VEL": "0" if vel == "none" else "1"})
        if e1 or e2:
            print("  refused %s: python's output %d, native %d" % (os.path.basename(f), e1, e2))
            bad += 1
            continue
        diffs = []
        for k, (a, b) in enumerate(zip(got[:5], want[:5])):
            if a != b:
                diffs.append(("notes", "ccs", "events", "total", "track names")[k])
        rep, before, left = got[5]
        if rep != lines:
            diffs.append("report")
        if not ov or (before, left) != (int(ov.group(1)), int(ov.group(2))):
            diffs.append("overlaps %s vs %s" % ((before, left), ov and ov.groups()))
        if diffs:
            bad += 1
            print("  DIFFERS %s: %s" % (os.path.basename(f), ", ".join(diffs)))
            if "report" in diffs:
                for a, b in zip(rep + [None] * len(lines), lines + [None] * len(rep)):
                    if a != b:
                        print("    native: %s\n    python: %s" % (a, b))
                        break
            if "notes" in diffs:
                for a, b in zip(got[0], want[0]):
                    if a != b:
                        print("    native: %s\n    python: %s" % (a, b))
                        break
                print("    (notes %d vs %d)" % (len(got[0]), len(want[0])))
        else:
            same += 1
            print("  same %s: %d parts, overlaps %d -> %d" % (os.path.basename(f), len(rep), before, left))
    print("mux: %d files identical, %d differ" % (same, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
