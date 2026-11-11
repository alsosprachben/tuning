#!/usr/bin/env python3
"""How far every SC-88Pro insertion effect type is covered: each type's file
(examples/gs_efx_files.py) through the native checks, a row a type.

    python3 examples/efx_coverage.py [SECONDS] [--types=N,N,...] [--skip=python,stream,live] [--json=PATH]
                                     [--state=PATH]

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
alone (no live session, no other check).

Each check runs in a scope of its own under the memory cap (COVERAGE_CAP,
default 3500M; "" for none) and a time limit (COVERAGE_TIMEOUT s, default
3600): one the cap or the clock kills is that check's "failed: killed at the
memory cap" or "failed: timed out", and the rest go on. --state=PATH (default
the --json's path + ".state") keeps each word as it comes: a run started again
with it skips what is there, so a run killed whole loses one check, not hours.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


CAP = os.environ.get("COVERAGE_CAP", "3500M")
TIMEOUT = float(os.environ.get("COVERAGE_TIMEOUT") or 3600)
_units = [0]
KILLED, TIMED_OUT = -1009, -1124        # (run_capped's returncodes)


def run_capped(cmd, env, timeout=None):
    """subprocess.run(cmd), text out, in a scope of its own under CAP: a
    CompletedProcess whose returncode is KILLED when the cap killed it,
    TIMED_OUT past the time limit (the scope stopped, its children too)"""
    unit = None
    if CAP and shutil.which("systemd-run"):
        _units[0] += 1
        unit = "coverage-%d-%d" % (os.getpid(), _units[0])
        cmd = ["systemd-run", "--user", "--scope", "-q", "--unit=" + unit, "-p", "MemoryMax=" + CAP,
               "-p", "MemorySwapMax=0"] + list(cmd)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        out, err = p.communicate(timeout=timeout or TIMEOUT)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        if unit:
            subprocess.run(["systemctl", "--user", "stop", unit + ".scope"], capture_output=True)
        p.kill()
        out, err = p.communicate()
        rc = TIMED_OUT
    if rc in (-9, 137):
        rc = KILLED
    if unit and rc:
        subprocess.run(["systemctl", "--user", "reset-failed", unit + ".scope"], capture_output=True)
    return subprocess.CompletedProcess(cmd, rc, out, err)


def died(r):
    """the word for a check the cap or the clock killed, else None"""
    return ("failed: killed at the memory cap" if r.returncode == KILLED else
            "failed: timed out" if r.returncode == TIMED_OUT else None)


class State:
    """words kept as they come (a JSON line each, flushed): {key: word}"""

    def __init__(self, path):
        self.path, self.words = path, {}
        if path and os.path.exists(path):
            with open(path, "rb+") as f:    # (a line cut short by a kill: ended, so the next starts clean)
                if f.seek(0, 2) and (f.seek(-1, 2), f.read(1))[1] != b"\n":
                    f.write(b"\n")
            for ln in open(path):
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue                # (a line cut short by a kill)
                self.words[d["key"]] = d["word"]

    def get(self, key):
        return self.words.get(key)

    def put(self, key, word):
        self.words[key] = word
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(dict(key=key, word=word, at=time.strftime("%H:%M"))) + "\n")
        return word


def _nvrender_word(w):
    return ("identical" if w.startswith("identical") else "differs" if w.startswith("DIFFERS")
            else "failed: " + w if w.startswith("nvrender failed") else "refused: " + w)


def python_check(paths, seconds, env, state=None):
    """{file's name: word} from nvrender_check's lines, a file at a time"""
    state = state or State(None)
    out = {}
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        if state.get("python:" + name) is not None:
            out[name] = state.get("python:" + name)
            continue
        r = run_capped([sys.executable, os.path.join(HERE, "examples", "nvrender_check.py"), path, str(seconds)],
                       env)
        w = died(r)
        for ln in r.stdout.splitlines():
            m = re.match(r"  (\S+): (.*)$", ln)
            if m and m.group(1) == name and w is None:
                w = _nvrender_word(m.group(2))
        out[name] = state.put("python:" + name, w or "failed: no result: " + (r.stderr.strip()[-160:]))
    return out


def _export(x, env, *extra):
    """a native export at x (made once), under the cap: None, or the word for its failure"""
    if os.path.exists(x):
        return None
    r = run_capped([sys.executable, os.path.join(HERE, "examples", "native_export.py"), x] + list(extra), env)
    return None if r.returncode == 0 else died(r) or "failed: export: " + r.stderr.strip()[-160:]


def stream_check(paths, seconds, env, tmp, state=None):
    """{efx_NN: word}: nvrender --stream against its whole render."""
    import bitident as BI
    import native as N
    state = state or State(None)
    exe = N.build_nvrender()
    nvx = os.path.join(tmp, "piano.nvx")
    out = {}
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        if state.get("stream:" + name) is not None:
            out[name] = state.get("stream:" + name)
            continue
        mid = os.path.join(tmp, name + ".cut.mid")
        BI.excerpt(path, seconds).save(mid)
        out[name] = state.put("stream:" + name, _export(nvx, env) or _stream_one(exe, nvx, mid, env, tmp))
    return out


def _stream_one(exe, x, mid, env, tmp):
    """one file's stream word"""
    w, s = os.path.join(tmp, "w.wav"), os.path.join(tmp, "s.wav")
    r = run_capped([exe, x, mid, w], env)
    rm = re.search(r"the GS reverb's room \((\w+)\)", r.stderr) if r.returncode == 2 else None
    if rm:                              # (its GS reverb's own room: an export of it, made once)
        x = os.path.join(tmp, rm.group(1) + ".nvx")
        bad = _export(x, env, "--room=" + rm.group(1))
        if bad:
            return bad
        r = run_capped([exe, x, mid, w], env)
    if r.returncode:
        return died(r) or ("refused: " if r.returncode == 2 else "failed: ") + r.stderr.strip()[-160:]
    r2 = run_capped([exe, x, mid, s, "--stream"], env)
    whole = re.search(r"--stream: (.*): rendered whole", r2.stderr)
    same = r2.returncode == 0 and all(
        (not os.path.exists(a) and not os.path.exists(b))
        or (os.path.exists(a) and os.path.exists(b) and open(a, "rb").read() == open(b, "rb").read())
        for a, b in ((w, s), (w[:-4] + ".send.wav", s[:-4] + ".send.wav"),
                     (w[:-4] + ".room.json", s[:-4] + ".room.json")))
    for f in (w, s):
        for suf in ("", ".send.wav", ".room.json"):
            g = f if not suf else f[:-4] + suf
            if os.path.exists(g):
                os.remove(g)
    return died(r2) or ("differs" if not same else "whole: " + whole.group(1) if whole else "identical")


def live_check(paths, seconds, env, tmp, extra=("--programs",), state=None):
    """{file's name: word}: nvlive_check --programs (or EXTRA), a file at a time -- the live
    export made once (NV_EXPORT_CACHE, in TMP unless the caller set one), not
    once a type: ~1 GB and minutes each"""
    env = dict(env, NV_EXPORT_CACHE=env.get("NV_EXPORT_CACHE") or os.path.join(tmp, "nvx"))
    state = state or State(None)
    out = {}
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        if state.get("live:" + name) is not None:
            out[name] = state.get("live:" + name)
            continue
        r = run_capped([sys.executable, os.path.join(HERE, "examples", "nvlive_check.py"), path, str(seconds)]
                       + list(extra), env)
        last = (r.stdout.strip().splitlines() or [r.stderr.strip()[-160:]] or [""])[-1]
        out[name] = state.put("live:" + name, died(r) or (
            "identical" if r.returncode == 0 and last.endswith("identical")
            else "refused: " + last if "refused" in last else "differs" if r.returncode == 1
            else "failed: " + last))
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
    state = State(opt.get("state") or (opt["json"] + ".state" if opt.get("json") else None))
    try:
        made = GF.files(os.path.join(tmp, "files"), only)
        paths = [p for _, _, p in made]
        res = {}
        for which, fn in (("python", lambda: python_check(paths, seconds, env, state)),
                          ("stream", lambda: stream_check(paths, seconds, env, tmp, state)),
                          ("live", lambda: live_check(paths, seconds, env, tmp, state=state))):
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
