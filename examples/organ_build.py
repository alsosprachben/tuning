#!/usr/bin/env python3
"""HOW THE CHURCH ORGAN (GM 19) IS BUILT, start to finish -- each step a
script of its own, run in this order, each reading what the one before wrote
(Ben 2026-11-25: "keep how we built this organ reproducible").

    python3 examples/organ_build.py [--organ=NAME] [--from=STEP] [--to=STEP] [--check]

--organ: which organ (examples/organ_specs.py; default "baroque", GM 19's).

  bake      examples/organ_bake.py --write
            every stop simulated from its construction (fluepipe_sim: the jet
            on the pipe's impedance; reedpipe_sim: the beating tongue):
            its harmonic tables at anchor pitches, fundamental 1 (the TONE),
            its speech, its level (a "hold" stop re-held where the console
            has it -- set by Ben's ear -- a "sim" stop the simulated pipe's
            against the principal's). Hours; cached in .organ_bake_cache.json
            (local, ignored), keyed by the stop and the simulator's constants
  wind      examples/organ_bake.py --wind --write
            each stop's pitch and level against its wind, and its draw
  levels    examples/organ_levels.py --simulate --write
            each rank's radiated power key by key (the simulated pipe on full
            wind), folded into its tables as extra anchors -- the tone as the
            bake left it, its level held where its balance was set by ear
            (the manuals' C3-C5, the Pedal's C2-C3)
  regulate  examples/organ_regulate.py --rounds=4
            the voicer's regulation: each rank rendered alone, free-standing,
            its loudness by ISO 226 made even across its compass within
            +-12 dB (examples/organ_regulation.json, committed: the record of
            what the voicer did), folded in by organ_levels

Settings that are not steps, all in tonelib.py by name (each set by ear or
from a source, the comment beside it says which): the divisions and their
chests, the Tremulant's valve, the Swell's box, THE CASE (case_spread,
case_projection), the grooves, the touch.

A step reads its predecessors' output from tonelib.py and the cache: rerun
from any step and every later one must be rerun too. --check reruns from
--from (default: levels, minutes) on a copy of tonelib.py and compares: the
build is reproducible when nothing changes.
"""
import filecmp
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STEPS = [
    ("bake", ["organ_bake.py", "--write"]),
    ("wind", ["organ_bake.py", "--wind", "--write"]),
    ("levels", ["organ_levels.py", "--simulate", "--write"]),
    ("regulate", ["organ_regulate.py", "--rounds=4"]),
]


def run(first, last):
    names = [n for n, _ in STEPS]
    for name, cmd in STEPS[names.index(first):names.index(last) + 1]:
        print("== %s: %s" % (name, " ".join(cmd)), flush=True)
        if name == "regulate":
            # (the regulation is measured from the levelled tables without
            # it: its rounds start from none)
            import organ_specs as OS
            reg = os.path.join(HERE, OS.current()["regulation"])
            if os.path.exists(reg):
                os.remove(reg)
            subprocess.run([sys.executable, os.path.join(HERE, "organ_levels.py"), "--write"], cwd=ROOT,
                           check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, os.path.join(HERE, cmd[0])] + cmd[1:], cwd=ROOT, check=True,
                       stdout=subprocess.DEVNULL)


def main(argv):
    opt = dict(a[2:].split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
    os.environ["ORGAN_BUILD"] = opt.get("organ", os.environ.get("ORGAN_BUILD", "baroque"))
    sys.path.insert(0, HERE)
    import organ_specs as OS
    spec = OS.current()
    first = opt.get("from", "levels" if "--check" in argv else "bake")
    last = opt.get("to", "regulate")
    if "--check" not in argv:
        run(first, last)
        return 0
    tl = os.path.join(ROOT, "tonelib.py")
    reg = os.path.join(HERE, spec["regulation"])
    keep_tl, keep_reg = tl + ".build_check", reg + ".build_check"
    shutil.copyfile(tl, keep_tl)
    if os.path.exists(reg):
        shutil.copyfile(reg, keep_reg)
    try:
        run(first, last)
        same_tl = filecmp.cmp(tl, keep_tl, shallow=False)
        same_reg = not os.path.exists(keep_reg) or filecmp.cmp(reg, keep_reg, shallow=False)
        print("organ build from %s: tonelib.py %s, organ_regulation.json %s" % (
            first, "unchanged" if same_tl else "CHANGED", "unchanged" if same_reg else "CHANGED"))
        return 0 if same_tl and same_reg else 1
    finally:
        shutil.move(keep_tl, tl)
        if os.path.exists(keep_reg):
            shutil.move(keep_reg, reg)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
