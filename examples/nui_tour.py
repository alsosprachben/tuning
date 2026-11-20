#!/usr/bin/env python3
"""THE NATIVE INTERFACE's TOUR: every card, in the states that change what
it shows, in both layouts -- each frame's text audited (nui.cpp's
NUI_TEXT_AUDIT): a text cut with an ellipsis (CUT), two texts on each other
(OVERLAP), two on one line closer than a space
(CROWD), a text past the edge of its button, pocket or plate (SPILL).

    python3 examples/nui_tour.py EXPORT.nvx OUTDIR [--layout=laptop|ipad|both]
                                 [--session=SESSION.json] [--keep-ppm]

Headless (SDL's offscreen driver), silent (ALSA's null device), on a COPY of
the session (nvlive saves its session at exit). The part on row 1 is set to
each state's patch by the engine's own call (part_pick, by the patches
call's pick numbers, read from an engine opened here); the cards are reached
by tapping their keys, as a finger would. Writes OUTDIR/LAYOUT/*.png and
OUTDIR/audit.txt, prints the counts; exit 1 if anything was found.
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

CARDS = ["parts", "library", "synth", "stops", "piano", "drums", "amp", "effects", "matrix",
         "tuning", "control", "scenes", "files", "setup"]
# (each state: the patch put on part 1, and the cards whose look it changes -- every card for the first)
STATES = [
    ("lead", dict(program=84, variation=0), CARDS),
    ("moogbass", dict(program=38, variation=0), ["library", "synth", "amp"]),
    ("drawbar", dict(program=16, variation=0), ["stops", "amp", "piano"]),
    ("church", dict(program=19, variation=0), ["stops"]),
    ("harmonium", dict(program=20, variation=0), ["stops"]),
    ("piano", dict(program=0, variation=0), ["piano", "amp", "library"]),
    ("guitar", dict(program=27, variation=0), ["amp"]),
    ("kit", dict(program=0, drums=True), ["drums", "piano", "synth", "parts"]),
    ("mt32", dict(family="MT-32"), ["library", "parts"]),
]


def picks(nvx):
    """the engine's patches (the patches call): their pick numbers by program, variation, drums, family"""
    import native as N
    so = N.lib()
    so.nv_host_open_args.restype = ctypes.c_void_p
    so.nv_host_open_args.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int]
    so.nv_ui_call.restype = ctypes.c_void_p
    so.nv_ui_call.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
    so.nv_ui_free.argtypes = [ctypes.c_void_p]
    so.nv_host_close.argtypes = [ctypes.c_void_p]
    av = [b"nvlive", nvx.encode(), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register", b"--no-drums"]
    h = so.nv_host_open_args(len(av), (ctypes.c_char_p * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the engine would not open"
    p = so.nv_ui_call(h, None, b'{"call":"patches"}')
    out = json.loads(ctypes.string_at(p).decode())["patches"]
    so.nv_ui_free(p)
    so.nv_host_close(h)
    return out


def pick_for(ps, want):
    for p in ps:
        if "family" in want:
            if want["family"].lower() in json.dumps(p).lower():
                return p["pick"]
            continue
        if bool(p.get("drums")) == bool(want.get("drums")) and p["program"] == want["program"] and \
                (want.get("drums") or p.get("variation", 0) == want.get("variation", 0)):
            return p["pick"]
    raise SystemExit("no patch for %r" % want)


def tab_xy(layout, i):
    """a card key's centre, in the layout's design units (nui.cpp's draw)"""
    n = len(CARDS)
    if layout == "ipad":
        w = (1113 - 4 * n - 44) / n
        return 10 + i * (w + 4) + w / 2, 182
    w = (1892 - 8 * n - 56) / n
    return 14 + i * (w + 8) + w / 2, 299


def help_xy(layout):
    n = len(CARDS)
    if layout == "ipad":
        w = (1113 - 4 * n - 44) / n
        return 10 + n * (w + 4) + 22, 182
    w = (1892 - 8 * n - 56) / n
    return 14 + n * (w + 8) + 28, 299


def tour(nvx, out, layout, session, ps, keep_ppm):
    d = os.path.join(out, layout)
    os.makedirs(d, exist_ok=True)
    sess = os.path.join(d, "session.json")
    if session and os.path.exists(session):
        shutil.copy(session, sess)
    else:
        with open(sess, "w") as fh:
            fh.write("{}\n")
    steps = ["wait 3000"]
    shots = []
    for name, want, cards in STATES:
        steps += ['call {"call":"part_pick","row":0,"pick":%d}' % pick_for(ps, want), "wait 600"]
        for c in cards:
            x, y = tab_xy(layout, CARDS.index(c))
            ppm = os.path.join(d, "%s_%s.ppm" % (name, c))
            steps += ["tap %.0f %.0f" % (x, y), "wait 500", "shot " + ppm]
            shots.append(ppm)
    x, y = help_xy(layout)
    ppm = os.path.join(d, "help.ppm")
    steps += ["tap %.0f %.0f" % (x, y), "wait 500", "shot " + ppm, "quit"]
    shots.append(ppm)
    script = os.path.join(d, "script.txt")
    with open(script, "w") as fh:
        fh.write("\n".join(steps) + "\n")
    rep = os.path.join(d, "audit.txt")
    if os.path.exists(rep):
        os.remove(rep)
    size = "2266x1488" if layout == "ipad" else "1920x1080"
    env = dict(os.environ, SDL_VIDEODRIVER="offscreen", NUI_SIZE=size, NUI_SCRIPT=script, NUI_TEXT_AUDIT=rep,
               NUI_LAYOUT=layout)
    with open(os.path.join(d, "run.log"), "w") as log:
        rc = subprocess.run([os.path.join(HERE, "nvlive"), nvx, "--session=" + sess, "--app-windowed",
                             "--midi=/dev/null", "--device=null"], env=env, stdout=log, stderr=log,
                            timeout=900).returncode
    from PIL import Image
    for s in shots:
        if os.path.exists(s):
            Image.open(s).save(s[:-4] + ".png")
            if not keep_ppm:
                os.remove(s)
    return rc, rep


def main(argv):
    opt = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    nvx, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    layouts = ["laptop", "ipad"] if opt.get("layout", "both") == "both" else [opt["layout"]]
    ps = picks(nvx)
    total = {"CUT": 0, "OVERLAP": 0, "CROWD": 0, "SPILL": 0}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "audit.txt"), "w") as all_:
        for lay in layouts:
            rc, rep = tour(nvx, out, lay, opt.get("session"), ps, opt.get("keep-ppm"))
            if rc:
                print("%s: nvlive exited %d (see %s/run.log)" % (lay, rc, os.path.join(out, lay)))
            n = {"CUT": 0, "OVERLAP": 0, "CROWD": 0, "SPILL": 0}
            seen = set()
            for line in open(rep) if os.path.exists(rep) else []:
                all_.write(line.replace("== ", "== %s/" % lay, 1) if line.startswith("== ") else line)
                k = line.split("\t", 1)[0]
                if k in n:
                    key = (k, line.split("\t")[1:3] and tuple(line.split("\t")[1:3]))
                    if key not in seen:     # (the same fault on every card: counted once)
                        seen.add(key)
                        n[k] += 1
            print("%s: %d cut, %d overlapping, %d crowded, %d spilling (distinct)" % (lay, n["CUT"], n["OVERLAP"], n["CROWD"], n["SPILL"]))
            for k in n:
                total[k] += n[k]
    print("audit: %s" % os.path.join(out, "audit.txt"))
    return 1 if any(total.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
