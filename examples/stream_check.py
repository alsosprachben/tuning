#!/usr/bin/env python3
"""Does native/nvrender --stream render each file as its own whole render does?
    python3 examples/stream_check.py [file.mid ...] [--state=PATH] [--keep=DIR]

The stream renders everything the file renderer does (Ben, 2026-11-25): for
each file (default: every MIDI file in tests/live/midi, and in its folders),
nvrender renders it whole and --stream from the same export (made once:
nvlive_check.cached_export, NV_EXPORT_CACHE's), both on the CPU, and the WAVs
are compared byte for byte, the room's sidecars and send files too. A file is
"identical" only when the stream truly streamed: one it rendered whole
instead ("--stream: WHY: rendered whole") is a failure -- a refusal is a
thing the stream does not do yet, which this check is here to keep at none.
A file the whole render itself refuses (not a file the engine plays) is
counted "refused", not failed: that is nvrender_check's business.

tests/live/make_midi.py's stream_* files are the cases the stream once
refused or broke on (a chorus share rising on a valve's products, the
Clavinet's rockers, the controller matrix's tremolo, a Tremolo stop beside a
channel's tremolo, a scanner through a valve, sympathetic strings, a voice's
own gate, the register).

--state=PATH: each file's word appended as it comes (FILE<TAB>word), a file
it holds skipped on a rerun. --keep=DIR: a differing file's two renders kept.
Its last line: "stream: N files identical, D differ, W rendered whole, R
refused"; exit 1 if any differ, rendered whole or failed.
"""
import atexit
import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
MIDI = os.path.join(HERE, "tests", "live", "midi")
# (a file that needs its own settings: the environment its renders take)
FILE_ENV = {"cm64_mode.mid": {"TUNING_CM64": "1", "TUNING_MAP": "1"}}


def same(a, b):
    if not os.path.exists(a) and not os.path.exists(b):
        return True
    if not (os.path.exists(a) and os.path.exists(b)):
        return False
    with open(a, "rb") as x, open(b, "rb") as y:
        return x.read() == y.read()


def one(exe, nvx, mid, tmp, keep=None):
    """A file's word: identical, differs, whole: WHY, refused: WHY or failed: WHY."""
    env = dict(os.environ, **FILE_ENV.get(os.path.basename(mid), {}))
    w, s = os.path.join(tmp, "w.wav"), os.path.join(tmp, "s.wav")
    for f in glob.glob(os.path.join(tmp, "[ws].*")):
        os.remove(f)
    rw = subprocess.run([exe, nvx, mid, w], env=env, capture_output=True, text=True)
    if rw.returncode == 2:
        return "refused: " + (rw.stderr.strip().splitlines() or ["?"])[-1]
    if rw.returncode != 0:
        return "failed: the whole render (%d): %s" % (rw.returncode, (rw.stderr.strip().splitlines() or ["?"])[-1])
    rs = subprocess.run([exe, nvx, mid, s, "--stream"], env=env, capture_output=True, text=True)
    if rs.returncode != 0:
        return "failed: the stream (%d): %s" % (rs.returncode, (rs.stderr.strip().splitlines() or ["?"])[-1])
    for ln in rs.stderr.splitlines():
        if "--stream:" in ln and "rendered whole" in ln:
            return "whole: " + ln.split("--stream:", 1)[1].rsplit(": rendered whole", 1)[0].strip()
    ok = all(same(w[:-4] + x, s[:-4] + x) for x in (".wav", ".room.json", ".send.wav"))
    if not ok and keep:
        os.makedirs(keep, exist_ok=True)
        base = os.path.splitext(os.path.basename(mid))[0]
        for f in glob.glob(os.path.join(tmp, "[ws].*")):
            shutil.copy(f, os.path.join(keep, base + "." + os.path.basename(f)))
    return "identical" if ok else "differs"


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ.update(TUNING_STREAM="0", TUNING_GPU="", TUNING_REGISTER_C="1", TUNING_NATIVE_TONE="off")
    import native as N
    files = args or sorted(glob.glob(os.path.join(MIDI, "*.mid")) + glob.glob(os.path.join(MIDI, "*", "*.mid")))
    exe = N.build_nvrender()
    tmp = tempfile.mkdtemp(prefix="streamcheck")
    atexit.register(shutil.rmtree, tmp, True)       # (an export and WAVs a run)
    from nvlive_check import cached_export
    nvx = cached_export(tmp)
    state = opt.get("state")
    done = {}
    if state and os.path.exists(state):
        for ln in open(state):
            if "\t" in ln:
                f_, w_ = ln.rstrip("\n").split("\t", 1)
                done[f_] = w_
    tally = {"identical": 0, "differs": 0, "whole": 0, "refused": 0, "failed": 0}
    for mid in files:
        w = done.get(mid) or one(exe, nvx, mid, tmp, opt.get("keep"))
        if mid not in done and state:
            with open(state, "a") as fh:
                fh.write("%s\t%s\n" % (mid, w))
        tally[w.split(":")[0] if w.split(":")[0] in tally else "failed"] += 1
        print("  %-48s %s" % (os.path.relpath(mid, HERE) if mid.startswith(HERE) else mid, w), flush=True)
    bad = tally["differs"] + tally["whole"] + tally["failed"]
    print("stream: %d files identical, %d differ, %d rendered whole, %d refused%s" % (
        tally["identical"], tally["differs"], tally["whole"], tally["refused"],
        ", %d failed" % tally["failed"] if tally["failed"] else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
