#!/usr/bin/env python3
"""Does native/nvrender render a piano file as blockrender's CLI does?

    python3 examples/nvrender_check.py [file.mid ...] [SECONDS] [--from=PATH] [--tuner=NAME [--a=HZ]]

For each file (the corpus by default; the first SECONDS of it, 20 by
default, cut as bitident cuts, saved as a .mid both sides read): blockrender's
CLI on the whole table on the CPU (TUNING_STREAM=0, TUNING_GPU off, the
register on its C core) writes OUT.wav and OUT.room.json; native/nvrender,
from an export made once (examples/native_export.py), writes its own. The
two WAVs compared byte for byte, the sidecars text for text. A file nvrender
refuses (exit 2: not a piano file, a bend, a moving fader) is counted; one
whose GS reverb macro chose another room is rendered again from that room's
export (--room), made once. With NV_EXPORT_CACHE set, the exports come from
that cache (nvlive_check.cached_export): a file at a time costs one export,
not one a file.
--tuner: both at that tuner -- nvrender computing it (native/tuner.cpp),
blockrender's CLI taking it by name -- and --a at that reference pitch.
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
    if args:
        files = args
    else:
        pool = opt.get("from")
        files = [l.split()[0] for l in open(pool or os.path.join(HERE, "corpus.txt"))
                 if l.strip() and not l.startswith("#")]
    exe = N.build_nvrender()
    tmp = tempfile.mkdtemp(prefix="nvcheck")
    atexit.register(shutil.rmtree, tmp, True)       # (an export and WAVs a run: they filled the disk)
    from nvlive_check import cached_export
    nvx = cached_export(tmp)
    same = differ = refused = 0
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        mid = os.path.join(tmp, name + ".mid")
        BI.excerpt(path, seconds).save(mid)
        nv = os.path.join(tmp, name + ".nv.wav")
        tun = (["--tuner=" + opt["tuner"]] if opt.get("tuner") else []) + (["--a=" + opt["a"]] if opt.get("a") else [])
        r = subprocess.run([exe, nvx, mid, nv] + tun, capture_output=True, text=True)
        rm = re.search(r"the GS reverb's room \((\w+)\)", r.stderr) if r.returncode == 2 else None
        if rm:
            rx = cached_export(tmp, rm.group(1))
            r = subprocess.run([exe, rx, mid, nv] + tun, capture_output=True, text=True)
        if r.returncode == 2:
            refused += 1
            print("  %s: %s" % (name, r.stderr.strip().replace("nvrender: ", "")))
            continue
        if r.returncode != 0:
            differ += 1
            print("  %s: nvrender failed: %s" % (name, r.stderr.strip()))
            continue
        py = os.path.join(tmp, name + ".py.wav")
        cli = ([opt.get("tuner") or "hybrid440"] + (["a=" + opt["a"]] if opt.get("a") else [])
               if opt.get("tuner") or opt.get("a") else [])
        subprocess.check_call([sys.executable, os.path.join(HERE, "blockrender.py"), mid, py] + cli, env=env,
                              stdout=subprocess.DEVNULL)
        bad = []
        if open(nv, "rb").read() != open(py, "rb").read():
            bad.append("wav")
        # ...and the reverb send bus, where the channels' sends differ (CC91)
        sn, sp = nv[:-4] + ".send.wav", py[:-4] + ".send.wav"
        if os.path.exists(sn) != os.path.exists(sp) or (
                os.path.exists(sp) and open(sn, "rb").read() != open(sp, "rb").read()):
            bad.append("send.wav")
        jn, jp = nv[:-4] + ".room.json", py[:-4] + ".room.json"
        if not os.path.exists(jn) or open(jn).read() != open(jp).read():
            bad.append("room.json")
        if bad:
            differ += 1
            print("  %s: DIFFERS: %s" % (name, ", ".join(bad)))
        else:
            same += 1
            print("  %s: identical (%d bytes)" % (name, os.path.getsize(nv)))
        for f in (nv, py, jn, jp):
            if os.path.exists(f):
                os.remove(f)
    print("nvrender: %d files identical, %d differ, %d refused" % (same, differ, refused))
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
