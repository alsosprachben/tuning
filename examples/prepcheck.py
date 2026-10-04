#!/usr/bin/env python3
"""prepare()'s speed and memory work must not change one bit of the table.

    python3 examples/prepcheck.py FILE.mid [...] [--tuner hybridmean:440]
    python3 examples/prepcheck.py FILE.mid [...] --against HEAD
    python3 examples/prepcheck.py --effects --against HEAD

--effects adds a file written for the purpose: a part on each voice whose
effect builds from the partials already in the table -- sitar (sympathetic
strings), e-piano and tremolo strings (tremolo), clavinet (its tone section, CC1), organ (the
Leslie), overdriven guitar (tube amp and cabinet), a Moog lead through the
MF-104M, a string part sent to the chorus (CC93), and the sound controllers
(CC71/74/75) -- since no one piece in the corpus plays them all.

Each file is prepared twice and every array of the two partial tables
compared by its SHA-1; the times and peak memory are printed.

  default        with blockrender.PREP_MEMO on and off, in one process
  --against REV  the working tree against blockrender.py as of git REV (its
                 other modules from the working tree), each in a process of
                 its own -- two tables of a long piece at once ran a 7 GB
                 machine out of memory

What it has caught: an early-reflection memo keyed on id(), which moved 6% of
Mars's partial levels by 0.2%; and a comparison whose "new" side imported the
old blockrender.py from the folder it was run in -- which is why each side
runs from a folder of its own here.
"""
import ast
import hashlib
import os
import resource
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def table(path, tuner, memo=True, src=None):
    """(seconds, peak RSS GB, {array: sha1}, module file, memo stats, P)."""
    if src:
        sys.path.insert(0, src)
    sys.path.insert(1 if src else 0, HERE)
    import numpy as np
    import blockrender as B
    B.PREP_MEMO = memo
    if hasattr(B, 'PREP_MEMO_STATS'):
        B.PREP_MEMO_STATS[:] = [0, 0, 0]
    t0 = time.time()
    p = B.prepare(path, tuner)
    dt = time.time() - t0
    h = {k: hashlib.sha1(v.tobytes()).hexdigest() for k, v in p.items() if isinstance(v, np.ndarray)}
    return (dt, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, h, B.__file__,
            list(getattr(B, 'PREP_MEMO_STATS', [0, 0, 0])), p['P'])


def child(argv):
    """--child PATH TUNER SRC|-: one table, printed as a literal."""
    path, tuner, src = argv[2], argv[3], argv[4]
    r = table(path, tuner, src=None if src == '-' else src)
    sys.stdout.write("\nRESULT " + repr(r) + "\n")


def in_child(path, tuner, src):
    out = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", path, tuner, src or '-'],
                         capture_output=True, text=True, cwd=tempfile.gettempdir())
    for line in out.stdout.splitlines():
        if line.startswith("RESULT "):
            r = ast.literal_eval(line[7:])
            want = os.path.join(src, "blockrender.py") if src else os.path.join(HERE, "blockrender.py")
            if os.path.realpath(r[3]) != os.path.realpath(want):
                raise RuntimeError("the %s side imported %s" % (src or "working tree", r[3]))
            return r
    raise RuntimeError("the %s side failed:\n%s" % (src or "working tree", out.stderr[-2000:]))


def old_tree(rev):
    """blockrender.py as of rev, in a folder of its own, reading the working
    tree's kernel and modules."""
    d = tempfile.mkdtemp(prefix="prepcheck_")
    src = subprocess.check_output(["git", "-C", HERE, "show", "%s:blockrender.py" % rev], text=True)
    src = src.replace("HERE = os.path.dirname(os.path.abspath(__file__));", "HERE = %r;" % HERE, 1)
    open(os.path.join(d, "blockrender.py"), "w").write(src)
    return d


# (channel, program, controllers) for the --effects file
EFFECTS = ((0, 104, {}), (1, 4, {1: 100}), (2, 7, {1: 90}), (3, 16, {1: 127}), (4, 29, {}),
           (5, 81, {}), (6, 48, {93: 90}), (7, 61, {71: 100, 74: 30, 75: 90}), (8, 44, {}))


def effects_file():
    """The --effects MIDI: each part a short phrase and a held chord."""
    import mido
    m = mido.MidiFile(ticks_per_beat=480)
    for ch, prog, ccs in EFFECTS:
        tr = mido.MidiTrack()
        m.tracks.append(tr)
        tr.append(mido.Message('program_change', channel=ch, program=prog, time=0))
        for cc, v in ccs.items():
            tr.append(mido.Message('control_change', channel=ch, control=cc, value=v, time=0))
        for n in (60, 64, 67, 72):
            tr.append(mido.Message('note_on', channel=ch, note=n - 12 * (prog in (29,)), velocity=96, time=0))
            tr.append(mido.Message('note_off', channel=ch, note=n - 12 * (prog in (29,)), time=240))
        for n in (48, 55, 64):
            tr.append(mido.Message('note_on', channel=ch, note=n, velocity=90, time=0))
        tr.append(mido.Message('note_off', channel=ch, note=48, time=1920))
        tr.append(mido.Message('note_off', channel=ch, note=55, time=0))
        tr.append(mido.Message('note_off', channel=ch, note=64, time=0))
    path = os.path.join(tempfile.mkdtemp(prefix="prepcheck_"), "effects.mid")
    m.save(path)
    # the Moog through the MF-104M; the env reaches the child processes too
    os.environ.setdefault("TUNING_MOOG_PANEL", '{"mf104_on": 1, "mf104_mix": 0.5}')
    return path


def main(argv):
    if len(argv) > 1 and argv[1] == "--child":
        return child(argv)
    if "--effects" in argv:
        argv = [a for a in argv if a != "--effects"] + [effects_file()]
    tuner, against = "hybridmean:440", None
    for opt in ("--tuner", "--against"):
        if opt in argv:
            i = argv.index(opt)
            if opt == "--tuner":
                tuner = argv[i + 1]
            else:
                against = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    bad = 0
    old = old_tree(against) if against else None
    for f in argv[1:]:
        if old:
            b = in_child(f, tuner, None)
            a = in_child(f, tuner, old)
            how = "%s %.1fs %.2fGB -> now %.1fs %.2fGB" % (against, a[0], a[1], b[0], b[1])
        else:
            a = table(f, tuner, memo=False)
            b = table(f, tuner, memo=True)
            look, miss, emptied = b[4]
            how = "memo off %.1fs -> on %.1fs, hits %.1f%% (emptied %d)" % (
                a[0], b[0], 100.0 * (look - miss) / max(look, 1), emptied)
        diff = sorted(k for k in a[2] if a[2][k] != b[2].get(k)) + sorted(k for k in b[2] if k not in a[2])
        bad += bool(diff)
        print("%-24s P=%-9d %s  %s" % (os.path.basename(f), b[5], how,
                                       "identical" if not diff else "DIFFERS: " + " ".join(diff)), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
