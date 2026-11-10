#!/usr/bin/env python3
"""Does nvrender's windowed render (--window, the streaming render's first
step) write what its whole render writes?

    python3 examples/nvwindow_check.py [file.mid ...] [SECONDS] [--from=PATH] [--windows=W,W,...] [--no-sink]

For each file (the corpus by default; the first SECONDS, 20 by default, cut
as bitident cuts): nvrender from one export renders it whole, then at each
--windows size (default 1 and 8 kernel chunks: W=1 rounds up to one), and
the WAVs, the reverb sends and the sidecars are compared byte for byte. No
Python render: nvrender's whole render is nvrender_check's business. And
once more through nv_play's note sink (TUNING_NV_SINK_TEST=1: the table
rebuilt from the rows each note handed over, the store one note's), unless
--no-sink. And --stream (the streaming render: a scan, then the notes again,
each window rendered once nothing to come can reach it), unless --no-stream:
a file it cannot stream yet goes to the whole render (counted, with why). A file
whose GS reverb chose another room renders from that room's export; one with
a part's bus renders whole either way (said, and counted).
"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    seconds = 20.0
    if args and args[-1].replace(".", "", 1).isdigit():
        seconds = float(args.pop())
    env = dict(os.environ, TUNING_STREAM="0", TUNING_GPU="", TUNING_REGISTER_C="1", TUNING_NATIVE_TONE="off")
    os.environ.update(env)
    import bitident as BI
    import native as N
    wins = [int(w) for w in (opt.get("windows") or "1,65536").split(",")]
    if args:
        files = args
    else:
        files = [l.split()[0] for l in open(opt.get("from") or os.path.join(HERE, "corpus.txt"))
                 if l.strip() and not l.startswith("#")]
    exe = N.build_nvrender()
    tmp = tempfile.mkdtemp(prefix="nvwin")
    atexit.register(shutil.rmtree, tmp, True)
    nvx = os.path.join(tmp, "piano.nvx")
    subprocess.check_call([sys.executable, os.path.join(HERE, "examples", "native_export.py"), nvx], env=env,
                          stdout=subprocess.DEVNULL)
    same = differ = refused = whole = 0
    whys, streamed = {}, [0]

    def outputs(wav):
        return [open(f, "rb").read() if os.path.exists(f) else None
                for f in (wav, wav[:-4] + ".send.wav", wav[:-4] + ".room.json")]

    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        mid = os.path.join(tmp, name + ".mid")
        BI.excerpt(path, seconds).save(mid)
        x = nvx
        ref = os.path.join(tmp, name + ".whole.wav")
        r = subprocess.run([exe, x, mid, ref], capture_output=True, text=True)
        rm = re.search(r"the GS reverb's room \((\w+)\)", r.stderr) if r.returncode == 2 else None
        if rm:
            x = os.path.join(tmp, rm.group(1) + ".nvx")
            if not os.path.exists(x):
                subprocess.check_call([sys.executable, os.path.join(HERE, "examples", "native_export.py"), x,
                                       "--room=" + rm.group(1)], env=env, stdout=subprocess.DEVNULL)
            r = subprocess.run([exe, x, mid, ref], capture_output=True, text=True)
        if r.returncode == 2:
            refused += 1
            continue
        if r.returncode != 0:
            differ += 1
            print("  %s: nvrender failed: %s" % (name, r.stderr.strip()[-200:]))
            continue
        want = outputs(ref)
        bad, bus = [], False
        for w in wins + ([] if "no-sink" in opt else ["sink"]) + ([] if "no-stream" in opt else ["stream"]):
            out = os.path.join(tmp, name + ".w%s.wav" % w)
            if w == "stream":
                r = subprocess.run([exe, x, mid, out, "--stream"], capture_output=True, text=True)
                m = re.search(r"--stream: (.*): rendered whole", r.stderr)
                if m:
                    whys[m.group(1)] = whys.get(m.group(1), 0) + 1
                else:
                    streamed[0] += 1
            elif w == "sink":
                r = subprocess.run([exe, x, mid, out], capture_output=True, text=True,
                                   env=dict(env, TUNING_NV_SINK_TEST="1"))
            else:
                r = subprocess.run([exe, x, mid, out, "--window=%d" % w], capture_output=True, text=True)
            bus = bus or "--window: a part's bus" in r.stderr
            if r.returncode != 0:
                bad.append("W=%s failed (%d)" % (w, r.returncode))
                continue
            got = outputs(out)
            for k, what in enumerate(("wav", "send.wav", "room.json")):
                if got[k] != want[k]:
                    bad.append("W=%s %s" % (w, what))
            for f in (out, out[:-4] + ".send.wav", out[:-4] + ".room.json"):
                if os.path.exists(f):
                    os.remove(f)
        for f in (ref, ref[:-4] + ".send.wav", ref[:-4] + ".room.json"):
            if os.path.exists(f):
                os.remove(f)
        if bus:
            whole += 1
        if bad:
            differ += 1
            print("  %s: DIFFERS: %s" % (name, ", ".join(bad)))
        else:
            same += 1
            print("  %s: identical at %s%s" % (name, ", ".join(["W=%d" % w for w in wins]
                                                          + ([] if "no-sink" in opt else ["the sink"])
                                                          + ([] if "no-stream" in opt else ["--stream"])),
                                                " (a bus: rendered whole)" if bus else ""))
    if "no-stream" not in opt:
        print("--stream: %d streamed; rendered whole: %s" % (streamed[0], ", ".join(
            "%s %d" % kv for kv in sorted(whys.items(), key=lambda kv: -kv[1])) or "none"))
    print("nvwindow: %d files identical, %d differ, %d refused by nvrender, %d with a bus (whole)"
          % (same, differ, refused, whole))
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
