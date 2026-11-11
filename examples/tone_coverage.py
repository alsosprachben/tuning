#!/usr/bin/env python3
"""How far every tone and drum set is covered: each through the native checks,
a row a tone (examples/gs_tone_files.py's files) -- the program side of
examples/efx_coverage.py.

    python3 examples/tone_coverage.py [--stages=GM1,GM2,...] [--per=16] [--skip=python,stream,live]
                                      [--no-kits] [--no-split] [--json=PATH] [--state=PATH]

python  blockrender's CLI vs native/nvrender on each file, byte for byte
        (examples/nvrender_check.py)
stream  nvrender --stream vs its own whole render, byte for byte
live    native/nvlive vs live.Live, every sample (examples/nvlive_check.py):
        a tone file --programs, its program changes followed as a keyboard
        sends them; a drum set --drums at its program (a map's set, past 127,
        is not run live: "not run")

A file is PER tones in turn; one that is not identical is SPLIT: each of its
tones in a file of its own, the failing checks run again on each, so every
row is a tone's own word (--no-split: the batch's word on all its tones,
"batch: ..."). The live export is made once (NV_EXPORT_CACHE). Words as
efx_coverage's: "identical", "differs", "refused: why", "failed: why",
"whole: why" (stream: identical, not streamed), "not run: why", null where
skipped. Each check a file runs capped, its word kept as it comes
(efx_coverage's COVERAGE_CAP, COVERAGE_TIMEOUT and --state, default the
--json's path + ".state"): a check killed is that file's word, and a run
killed whole starts again where it was. --json: {"tones": [{stage, program, key, tone, name, python, stream,
live}], "kits": [{stage, set, name, keys, python, stream, live}]}. Heavy: run
it alone, under the memory cap; hours for every stage.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

import efx_coverage as EC       # noqa: E402

CHECKS = ("python", "stream", "live")


def run_checks(man, which, env, tmp, state):
    """{file: {check: word}} for the manifest's files, the checks in which"""
    out = {f["file"]: {} for f in man}
    for f in man:                               # (one file at a time: each its own length)
        secs = f["seconds"]
        if "python" in which:
            out[f["file"]]["python"] = EC.python_check([f["path"]], secs, env, state).get(f["file"],
                                                                                         "failed: no result")
        if "stream" in which:
            out[f["file"]]["stream"] = EC.stream_check([f["path"]], secs, env, tmp, state).get(f["file"],
                                                                                         "failed: no result")
        if "live" in which:
            if f["kind"] == "kit":
                s = f["kit"]["set"]
                out[f["file"]]["live"] = ("not run: a map's own set" if s >= 128 else
                                          EC.live_check([f["path"]], secs, env, tmp,
                                                        ["--drums", "--program=%d" % s], state).get(f["file"],
                                                                                            "failed: no result"))
            else:
                out[f["file"]]["live"] = EC.live_check([f["path"]], secs, env, tmp, state=state).get(f["file"],
                                                                                       "failed: no result")
        print("  %-32s %s" % (f["file"], "  ".join("%s %s" % (w, out[f["file"]].get(w, "-").split(":")[0])
                                                   for w in CHECKS if w in which)), flush=True)
    return out


def ok(w):
    return w is None or w == "identical" or w.startswith("whole") or w.startswith("not run")


def main(argv):
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    stages = set(opt["stages"].split(",")) if opt.get("stages") else None
    skip = set(opt.get("skip", "").split(",")) - {""}
    which = [w for w in CHECKS if w not in skip]
    import gs_tone_files as GT
    env = dict(os.environ, TUNING_STREAM="0", TUNING_GPU="", TUNING_REGISTER_C="1", TUNING_NATIVE_TONE="off")
    tmp = tempfile.mkdtemp(prefix="tonecov")
    state = EC.State(opt.get("state") or (opt["json"] + ".state" if opt.get("json") else None))
    env.setdefault("NV_EXPORT_CACHE", os.path.join(tmp, "nvx"))
    try:
        man = GT.files(os.path.join(tmp, "files"), stages, int(opt.get("per") or 16), "no-kits" not in opt)
        print("== %d files" % len(man), flush=True)
        res = run_checks(man, which, env, tmp, state)
        rows, krows = [], []
        for f in man:
            r = res[f["file"]]
            if f["kind"] == "kit":
                k = f["kit"]
                krows.append(dict(stage=k["stage"], set=k["set"], name=k["name"], keys=k["keys"],
                                  **{w: r.get(w) for w in CHECKS}))
                continue
            bad = [w for w in which if not ok(r.get(w))]
            if bad and len(f["tones"]) > 1 and "no-split" not in opt:
                # SPLIT: each tone alone, the checks the batch failed
                print("== split %s (%s)" % (f["file"], ",".join(bad)), flush=True)
                sub = []
                for i, t in enumerate(f["tones"]):
                    nm = "%s_t%02d" % (f["file"], i)
                    path = os.path.join(tmp, "files", nm + ".mid")
                    GT.make_tones(path, [(t["stage"], t["program"], t["key"], t["name"], t["msb"], t["lsb"])])
                    sub.append(dict(file=nm, path=path, kind="tones", seconds=GT.tone_seconds(1), tones=[t]))
                sres = run_checks(sub, bad, env, tmp, state)
                for s in sub:
                    t = s["tones"][0]
                    rows.append(dict(t, **{w: (sres[s["file"]][w] if w in bad else r.get(w)) for w in CHECKS}))
                continue
            for t in f["tones"]:
                rows.append(dict(t, **{w: (r.get(w) if ok(r.get(w)) or len(f["tones"]) == 1
                                           else "batch: " + r.get(w)) for w in CHECKS}))
        for t in rows:
            t["tone"] = str(t["program"]) if t["stage"] == "GM1" else "%d.%d" % (
                t["program"], t["key"] if t["key"] == 127 else t["key"] % 128)
            for k in ("start", "msb", "lsb"):
                t.pop(k, None)
        word = lambda w: "-" if w is None else w.split(":")[0]     # noqa: E731
        print("%-9s %-7s %-24s %-10s %-10s %-10s" % ("stage", "tone", "name", *CHECKS))
        for t in rows:
            if any(not ok(t[w]) for w in which):
                print("%-9s %-7s %-24s %-10s %-10s %-10s" % (t["stage"], t["tone"], t["name"][:24],
                                                             *(word(t[w]) for w in CHECKS)))
        for k in krows:
            if any(not ok(k[w]) for w in which):
                print("%-9s set %-3d %-24s %-10s %-10s %-10s" % (k["stage"], k["set"], k["name"][:24],
                                                                 *(word(k[w]) for w in CHECKS)))
        for w in which:
            print("%s: tones %d of %d identical, drum sets %d of %d%s" % (
                w, sum(t[w] == "identical" for t in rows), len(rows),
                sum(k[w] == "identical" for k in krows), len(krows),
                ("; %d whole (identical, not streamed)" % sum((t[w] or "").startswith("whole") for t in rows + krows))
                if w == "stream" else ""))
        if opt.get("json"):
            with open(opt["json"], "w") as f:
                json.dump(dict(stages=sorted(stages) if stages else None, tones=rows, kits=krows), f, indent=1)
        return 1 if any(not ok(x[w]) for x in rows + krows for w in which) else 0
    finally:
        shutil.rmtree(tmp, True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
