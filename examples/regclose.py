#!/usr/bin/env python3
"""Is the register's C core (registercore.c) close enough to its numpy path?

    python3 examples/regclose.py [SECONDS] FILE.mid ...           the tables
    python3 examples/regclose.py --render [SECONDS] FILE.mid ...  the audio

The register's C core is not bit-identical to numpy (numpy's float64 exp is
its own SIMD routine), so it is checked by tolerance, the rest of prepare by
examples/prepident.py (table-identical: only files with a register voice
may move). Each file is prepared twice, each in its own process --
TUNING_REGISTER_C=0 (numpy) and =1 (C) -- and every table compared:

  float32 columns   within one float32 step (2^-23 relative) of each other:
                    the C and numpy values round apart only near a boundary
  float64 columns   within 1e-9 relative (the core agrees to ~1e-12)
  row counts        equal; a row that exists in one only is a threshold
                    decision (a row ending at the floor) moved by the last
                    bits, and is reported

--render renders each excerpt both ways (the file renderer, on the GPU when
TUNING_GPU=1) and reports their difference's level under the render's:
it should be 100 dB or more below.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, os.getcwd())


def child(mode, path, seconds, out):
    """In a child process: prepare (or render) the excerpt, save its arrays."""
    import contextlib
    import io
    import blockrender as B
    import bitident as BI
    src = BI.excerpt(path, seconds) if seconds > 0 else path
    with contextlib.redirect_stdout(io.StringIO()):
        if mode == "render":
            L, R = B.render(src)[:2]
            np.savez(out, L=np.asarray(L, np.float64), R=np.asarray(R, np.float64))
            return
        prep = B.prepare(src)
    arrs = {k: v for k, v in prep.items() if isinstance(v, np.ndarray) and v.dtype.kind in "fiub"}
    np.savez(out, **arrs)


def run(mode, path, seconds, c_on, out):
    env = dict(os.environ, TUNING_REGISTER_C="1" if c_on else "0")
    subprocess.run([sys.executable, os.path.abspath(__file__), "--child", mode, path, str(seconds), out],
                   env=env, check=True, cwd=os.getcwd())


def compare_tables(a, b):
    """[(key, verdict)] over the arrays of two prepare() dumps."""
    out = []
    for k in sorted(set(a.files) | set(b.files)):
        if k not in a.files or k not in b.files:
            out.append((k, "only in %s" % ("numpy" if k in a.files else "C")))
            continue
        x, y = a[k], b[k]
        if x.shape != y.shape:
            out.append((k, "shape %s vs %s" % (x.shape, y.shape)))
            continue
        if x.dtype.kind in "iub":
            n = int(np.count_nonzero(x != y))
            if n:
                out.append((k, "%d of %d integers differ" % (n, x.size)))
            continue
        same = (x == y) | (np.isnan(x) & np.isnan(y))
        if same.all():
            continue
        d = np.abs(x.astype(np.float64) - y.astype(np.float64))
        scale = np.maximum(np.abs(x.astype(np.float64)), np.abs(y.astype(np.float64)))
        rel = np.where(scale > 0, d / np.where(scale > 0, scale, 1.0), 0.0)
        tol = 2.0 ** -23 if x.dtype == np.float32 else 1e-9
        bad = int(np.count_nonzero(rel > tol * 1.0001))
        out.append((k, "%s%d of %d differ, worst %.2g relative (tolerance %.2g)"
                    % ("FAIL: %d over; " % bad if bad else "", int(np.count_nonzero(~same)), x.size,
                       float(rel.max()), tol)))
    return out


def main(argv):
    if argv[1:2] == ["--child"]:
        child(argv[2], argv[3], float(argv[4]), argv[5])
        return 0
    render = "--render" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    seconds = 20.0
    if args and not args[0].lower().endswith((".mid", ".midi")):
        seconds = float(args.pop(0))
    if not args:
        print(__doc__)
        return 2
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        for p in args:
            name = os.path.basename(p)
            fa, fb = os.path.join(tmp, "numpy.npz"), os.path.join(tmp, "c.npz")
            mode = "render" if render else "prepare"
            run(mode, p, seconds, False, fa)
            run(mode, p, seconds, True, fb)
            a, b = np.load(fa), np.load(fb)
            if render:
                ref = np.sqrt(np.mean(a["L"] ** 2 + a["R"] ** 2))
                n = min(len(a["L"]), len(b["L"]))
                diff = np.sqrt(np.mean((a["L"][:n] - b["L"][:n]) ** 2 + (a["R"][:n] - b["R"][:n]) ** 2))
                db = 20.0 * np.log10(max(diff, 1e-300) / max(ref, 1e-300))
                ok = db <= -100.0 and len(a["L"]) == len(b["L"])
                fails += not ok
                print("%-24s difference %7.1f dB under the render%s%s"
                      % (name, db, "" if len(a["L"]) == len(b["L"]) else " (LENGTHS DIFFER)",
                         "" if ok else "  FAIL"))
            else:
                res = compare_tables(a, b)
                bad = [r for r in res if r[1].startswith("FAIL") or "shape" in r[1] or "only" in r[1]
                       or "integers" in r[1]]
                fails += bool(bad)
                print("%-24s %s" % (name, "identical" if not res else
                                    ("%d array(s) differ within tolerance" % len(res) if not bad else "FAIL")))
                for k, v in res:
                    print("    %-10s %s" % (k, v))
            sys.stdout.flush()
            for f in (fa, fb):
                os.remove(f)
    print("%d file(s), %d outside tolerance" % (len(args), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
