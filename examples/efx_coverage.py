#!/usr/bin/env python3
"""How far every SC-88Pro insertion effect type is covered: each type's file
(examples/gs_efx_files.py) through the native checks, a row a type.

    python3 examples/efx_coverage.py [SECONDS] [--types=N,N,...] [--skip=python,stream,live] [--json=PATH]

python  blockrender's CLI on the whole table vs native/nvrender, byte for
        byte, the room's sidecar and the send too (examples/nvrender_check.py)
stream  nvrender --stream vs its own whole render, byte for byte -- and
        whether it streamed, or the reason it rendered whole instead
live    native/nvlive vs live.Live, every sample, the file's programs
        followed (examples/nvlive_check.py --programs)

SECONDS (default 20) cuts each file as the checks cut. A table on stdout,
the tally under it; --json writes {"seconds", "types": [{num, name,
python, stream, live}]} with each check's word: "identical", "differs",
"refused: why", "failed: why", "whole: why" (stream: identical, but not
streamed), or null where skipped. Heavy: one Python render a type -- run it
alone (no live session, no other check), under the memory cap.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def python_check(paths, seconds, env):
    """{file's name: word} from nvrender_check's lines."""
    r = subprocess.run([sys.executable, os.path.join(HERE, "examples", "nvrender_check.py")] + paths
                       + [str(seconds)], capture_output=True, text=True, env=env)
    out = {}
    for ln in r.stdout.splitlines():
        m = re.match(r"  (\S+): (.*)$", ln)
        if not m:
            continue
        w = m.group(2)
        out[m.group(1)] = ("identical" if w.startswith("identical") else "differs" if w.startswith("DIFFERS")
                           else "failed: " + w if w.startswith("nvrender failed") else "refused: " + w)
    return out


def stream_check(paths, seconds, env, tmp):
    """{efx_NN: word}: nvrender --stream against its whole render."""
    import bitident as BI
    import native as N
    exe = N.build_nvrender()
    nvx = os.path.join(tmp, "piano.nvx")
    subprocess.check_call([sys.executable, os.path.join(HERE, "examples", "native_export.py"), nvx], env=env,
                          stdout=subprocess.DEVNULL)
    out = {}
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        mid = os.path.join(tmp, name + ".cut.mid")
        BI.excerpt(path, seconds).save(mid)
        w, s = os.path.join(tmp, "w.wav"), os.path.join(tmp, "s.wav")
        x = nvx
        r = subprocess.run([exe, x, mid, w], capture_output=True, text=True, env=env)
        rm = re.search(r"the GS reverb's room \((\w+)\)", r.stderr) if r.returncode == 2 else None
        if rm:                              # (its GS reverb's own room: an export of it, made once)
            x = os.path.join(tmp, rm.group(1) + ".nvx")
            if not os.path.exists(x):
                subprocess.check_call([sys.executable, os.path.join(HERE, "examples", "native_export.py"), x,
                                       "--room=" + rm.group(1)], env=env, stdout=subprocess.DEVNULL)
            r = subprocess.run([exe, x, mid, w], capture_output=True, text=True, env=env)
        if r.returncode:
            out[name] = ("refused: " if r.returncode == 2 else "failed: ") + r.stderr.strip()[-160:]
            continue
        r2 = subprocess.run([exe, x, mid, s, "--stream"], capture_output=True, text=True, env=env)
        whole = re.search(r"--stream: (.*): rendered whole", r2.stderr)
        same = r2.returncode == 0 and all(
            (not os.path.exists(a) and not os.path.exists(b))
            or (os.path.exists(a) and os.path.exists(b) and open(a, "rb").read() == open(b, "rb").read())
            for a, b in ((w, s), (w[:-4] + ".send.wav", s[:-4] + ".send.wav"),
                         (w[:-4] + ".room.json", s[:-4] + ".room.json")))
        out[name] = ("differs" if not same else "whole: " + whole.group(1) if whole else "identical")
        for f in (w, s):
            for suf in ("", ".send.wav", ".room.json"):
                g = f if not suf else f[:-4] + suf
                if os.path.exists(g):
                    os.remove(g)
    return out


def live_check(paths, seconds, env, tmp, extra=("--programs",)):
    """{file's name: word}: nvlive_check --programs (or EXTRA), a file at a time -- the live
    export made once (NV_EXPORT_CACHE, in TMP unless the caller set one), not
    once a type: ~1 GB and minutes each"""
    env = dict(env, NV_EXPORT_CACHE=env.get("NV_EXPORT_CACHE") or os.path.join(tmp, "nvx"))
    out = {}
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        r = subprocess.run([sys.executable, os.path.join(HERE, "examples", "nvlive_check.py"), path, str(seconds)]
                           + list(extra), capture_output=True, text=True, env=env)
        last = (r.stdout.strip().splitlines() or [r.stderr.strip()[-160:]])[-1]
        out[name] = ("identical" if r.returncode == 0 and last.endswith("identical")
                     else "refused: " + last if "refused" in last else "differs" if r.returncode == 1
                     else "failed: " + last)
    return out


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    seconds = float(args[0]) if args else 20.0
    only = {int(x) for x in opt["types"].split(",")} if opt.get("types") else None
    skip = set(opt.get("skip", "").split(",")) - {""}
    import gs_efx_files as GF
    env = dict(os.environ, TUNING_STREAM="0", TUNING_GPU="", TUNING_REGISTER_C="1", TUNING_NATIVE_TONE="off")
    tmp = tempfile.mkdtemp(prefix="efxcov")
    try:
        made = GF.files(os.path.join(tmp, "files"), only)
        paths = [p for _, _, p in made]
        res = {}
        for which, fn in (("python", lambda: python_check(paths, seconds, env)),
                          ("stream", lambda: stream_check(paths, seconds, env, tmp)),
                          ("live", lambda: live_check(paths, seconds, env, tmp))):
            res[which] = None if which in skip else fn()
            if res[which] is not None:
                print("== %s done" % which, flush=True)
        rows = []
        for num, name, path in made:
            key = os.path.splitext(os.path.basename(path))[0]
            row = dict(num=num, name=name)
            for which in ("python", "stream", "live"):
                row[which] = None if res[which] is None else res[which].get(key, "failed: no result")
            rows.append(row)
        word = lambda w: "-" if w is None else w.split(":")[0]     # noqa: E731
        print("%-3s %-20s %-10s %-10s %-10s" % ("no", "type", "python", "stream", "live"))
        for r in rows:
            print("%02d  %-20s %-10s %-10s %-10s" % (r['num'], r['name'], word(r['python']), word(r['stream']),
                                                     word(r['live'])))
        for which in ("python", "stream", "live"):
            if res[which] is None:
                continue
            words = [r[which] for r in rows]
            print("%s: %d of %d identical%s" % (
                which, sum(w == "identical" for w in words), len(words),
                ("; %d whole (identical, not streamed)" % sum(w.startswith("whole") for w in words))
                if which == "stream" else ""))
            for r in rows:
                if r[which] != "identical":
                    print("  %02d %s: %s" % (r['num'], r['name'], r[which]))
        if opt.get("json"):
            with open(opt["json"], "w") as f:
                json.dump(dict(seconds=seconds, types=rows), f, indent=1)
        bad = any(r[w] is not None and r[w] != "identical" and not r[w].startswith("whole")
                  for r in rows for w in ("python", "stream", "live"))
        return 1 if bad else 0
    finally:
        shutil.rmtree(tmp, True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
