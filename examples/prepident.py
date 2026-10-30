#!/usr/bin/env python3
"""Is a change to blockrender._prepare table-identical on the corpus?

    python3 examples/prepident.py HASHFILE [SECONDS] [file.mid ...] [options]

bitident.py's check one stage earlier: instead of rendering, it hashes
everything blockrender.prepare returns -- every array of the partial table,
every side table (reverb sends, fader rows, buses...) -- for the first SECONDS
(default 20; 0 for whole files) of each file. A refactor of _prepare that moves
nothing must give identical hashes, and it can say WHICH key moved. No kernel
runs, so it is CPU work, far lighter than a render, and the GPU is not used.

Options as bitident's: --from=PATH --grep=REGEX --gs --program=N --kit=N
--list --against=FILE; and --cap-mb=N. Run it in a worktree at the old commit and in the
working tree, or once at the old commit to a file and --against it after.

EACH FILE IN ITS OWN PROCESS, under a memory cap (--cap-mb=N, default
3000): in one process the GS files' tables and blockrender's module state
piled up to 5 GB and the machine swapped. A file over the cap is stopped
and written as SKIPPED, and the run goes on. Between files the run waits
while live is playing (live.py or livetui), so it never competes with it.

Objects with no stable value (functions, ctypes, class instances) are hashed
by type name only: a change inside one is invisible here, and bitident's
render is the check for that.
"""
import hashlib
import os
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, os.getcwd())          # the tree being tested, not this one
import blockrender as B                  # noqa: E402
import bitident as BI                    # noqa: E402


def feed(h, v, depth=0):
    """Canonical bytes of a prepare() value into hash h."""
    if depth > 20:
        h.update(b"<deep>")
    elif isinstance(v, np.ndarray):
        h.update(b"A%s%r" % (str(v.dtype).encode(), v.shape))
        if v.dtype.kind == "O":
            for x in v.ravel():
                feed(h, x, depth + 1)
        else:
            h.update(np.ascontiguousarray(v).tobytes())
    elif isinstance(v, dict):
        h.update(b"D%d" % len(v))
        for k in sorted(v, key=repr):
            h.update(repr(k).encode())
            feed(h, v[k], depth + 1)
    elif isinstance(v, (list, tuple)):
        h.update(b"L%d" % len(v))
        for x in v:
            feed(h, x, depth + 1)
    elif isinstance(v, (set, frozenset)):
        h.update(b"S%d" % len(v))
        for x in sorted(v, key=repr):
            feed(h, x, depth + 1)
    elif isinstance(v, (bool, int, float, str, bytes, type(None), np.generic)):
        h.update(repr(v).encode())
    else:
        h.update(b"<%s>" % type(v).__name__.encode())


def table_hashes(prep):
    """{key: sha1} for each key of the prepare() dict, and one for the whole."""
    out = {}
    whole = hashlib.sha1()
    for k in sorted(prep):
        if k == "lib":
            continue
        h = hashlib.sha1()
        feed(h, prep[k])
        out[k] = h.hexdigest()[:12]
        whole.update(k.encode() + out[k].encode())
    return whole.hexdigest(), out


def against(out, ref):
    a = {l.split()[1]: l.split() for l in open(out) if l.strip()}
    b = {l.split()[1]: l.split() for l in open(ref) if l.strip()}
    moved = []
    for name, la in a.items():
        lb = b.get(name)
        if lb is None:
            continue
        if la[0] in ("SKIPPED", "FAILED") or lb[0] in ("SKIPPED", "FAILED"):
            moved.append((name, ["(not compared: %s)" % (la[0] if la[0] in ("SKIPPED", "FAILED") else "ref " + lb[0])]))
            continue
        if la[0] != lb[0]:
            ka = dict(x.split("=") for x in la[2:])
            kb = dict(x.split("=") for x in lb[2:])
            keys = sorted(k for k in set(ka) | set(kb) if ka.get(k) != kb.get(k))
            moved.append((name, keys))
    same = [n for n in a if n in b and a[n][0] == b[n][0] and a[n][0] not in ("SKIPPED", "FAILED")]
    new = [n for n in a if n not in b]
    return moved, same, new


def live_running():
    try:
        out = subprocess.run(["pgrep", "-af", "python3"], capture_output=True, text=True).stdout
    except OSError:
        return False
    return any(("livetui" in l or "live.py" in l) and "prepident" not in l for l in out.splitlines())


def wait_for_live():
    said = False
    while live_running():
        if not said:
            print("  live is playing: waiting", flush=True)
            said = True
        time.sleep(30)


def one_file(p, seconds, cap_mb):
    """One file's line, from a child process watched for memory."""
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--one", p, str(seconds)],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    peak = 0
    while child.poll() is None:
        try:
            with open("/proc/%d/status" % child.pid) as st:
                rss = next((int(l.split()[1]) // 1024 for l in st if l.startswith("VmRSS:")), 0)
        except OSError:
            rss = 0
        peak = max(peak, rss)
        if rss > cap_mb:
            child.kill()
            child.wait()
            return "SKIPPED %s over_cap=%dMB" % (os.path.basename(p), rss)
        time.sleep(0.5)
    line = (child.stdout.read() or "").strip().splitlines()
    line = [l for l in line if l.startswith("PREPIDENT ")]
    if child.returncode != 0 or not line:
        return "FAILED %s rc=%d" % (os.path.basename(p), child.returncode)
    return line[-1][len("PREPIDENT "):]


def main():
    if sys.argv[1:2] == ["--one"]:
        p, seconds = sys.argv[2], float(sys.argv[3])
        src = BI.excerpt(p, seconds) if seconds > 0 else p
        whole, keys = table_hashes(B.prepare(src))
        print("PREPIDENT %s %s %s" % (whole, os.path.basename(p),
                                      " ".join("%s=%s" % kv for kv in sorted(keys.items()))))
        return 0
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in sys.argv[1:] if a.startswith("--"))
    if not args and "list" not in opt:
        print(__doc__)
        return 2
    out = args[0] if args else None
    seconds = float(args[1]) if len(args) > 1 else 20.0
    pool = opt.get("from")
    if args[2:]:
        files = args[2:]
    elif pool and os.path.isdir(pool):
        files = sorted(os.path.join(d, n) for d, _, ns in os.walk(pool) for n in ns
                       if n.lower().endswith((".mid", ".midi")))
    else:
        files = [l.split()[0] for l in open(pool or os.path.join(HERE, "corpus.txt"))
                 if l.strip() and not l.startswith("#")]
    files = BI.select(files, grep=opt.get("grep") or None, gs="gs" in opt,
                      program=int(opt["program"]) if "program" in opt else None,
                      kit=int(opt["kit"]) if "kit" in opt else None)
    if "list" in opt:
        for p in files:
            print(p)
        print("%d file(s)" % len(files))
        return 0
    cap = int(opt.get("cap-mb") or 3000)
    with open(out, "w") as f:
        for p in files:
            wait_for_live()
            f.write(one_file(p, seconds, cap) + "\n")
            f.flush()
    if opt.get("against"):
        moved, same, new = against(out, opt["against"])
        print("against %s: %d moved, %d table-identical, %d not in it"
              % (os.path.basename(opt["against"]), len(moved), len(same), len(new)))
        for name, keys in moved:
            print("  moved  %s: %s" % (name, " ".join(keys)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
