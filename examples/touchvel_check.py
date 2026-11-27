#!/usr/bin/env python3
"""TOUCH VELOCITY, checked (nui/touchvel.h): the laptop layout, scripted taps on
the Keys card and the Drums pads under touch settings saved in the session; the
velocities the interface sends (NUI_LOG_CALLS=drum_hit) against the formula.

usage: python3 examples/touchvel_check.py OUT [--shots]
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import nui_tour as T

NVX = os.path.expanduser("~/nvx/live.nvx")


def run(out, name, touch, steps, shots=False):
    """One run: a session holding these touch settings (None: none), the steps; the drum_hits sent."""
    d = os.path.join(out, name)
    os.makedirs(d, exist_ok=True)
    sess = {} if touch is None else {"ui": {"touch": touch}}
    with open(os.path.join(d, "session.json"), "w") as f:
        json.dump(sess, f)
    lines = ["wait 3000"] + [s.replace("SHOT", os.path.join(d, "")) for s in steps] + ["quit"]
    with open(os.path.join(d, "script.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    env = dict(os.environ, SDL_VIDEODRIVER="offscreen", NUI_SIZE="1920x1080", NUI_LAYOUT="laptop", NUI_LANG="en",
               NUI_SCRIPT=os.path.join(d, "script.txt"), NUI_LOG_CALLS="drum_hit,key_ctl")
    with open(os.path.join(d, "run.log"), "w") as log:
        subprocess.run([os.path.join(HERE, "nvlive"), NVX, "--session=" + os.path.join(d, "session.json"), "--app-windowed",
                        "--midi=/dev/null", "--device=null"], env=env, stdout=log, stderr=log, timeout=300)
    hits, ctl = [], []
    for l in open(os.path.join(d, "run.log"), errors="replace"):
        m = re.search(r'nui: call (\{"call":"(drum_hit|key_ctl)".*\})', l)
        if m:
            j = json.loads(m.group(1))
            if m.group(2) == "drum_hit":
                hits.append((j["key"], j["v"]))
            else:
                ctl.append((j["kind"], j.get("semis", j.get("v"))))
    run.ctl = ctl
    saved = json.load(open(os.path.join(d, "session.json")))
    return hits, saved


def card(c):
    x, y = T.tab_xy("laptop", T.CARDS.index(c))
    return "tap %.0f %.0f" % (x, y)


def main(argv):
    out = argv[0]
    shots = "--shots" in argv
    ps = T.picks(NVX)
    piano = 'call {"call":"part_pick","row":0,"pick":%d}' % T.pick_for(ps, dict(program=0, variation=0))
    kit = 'call {"call":"part_pick","row":0,"pick":%d}' % T.pick_for(ps, dict(program=0, drums=True))
    # (a white key, C3, at its top and its front edge: the keys from y 404 to 1048)
    keys = [piano, "wait 600", card("keys"), "wait 500", "tap 55 420", "wait 300", "tap 55 1040", "wait 300"]
    if shots:
        keys += ["shot SHOTkeys.ppm"]
    fails = 0

    def expect(name, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%-28s %s  got %s want %s" % (name, "ok  " if ok else "FAIL", got, want))

    def v(lo, hi, d, g=1.0, flip=False):
        d = 1 - d if flip else d
        return max(1, min(127, round(lo + (hi - lo) * d ** g)))

    d_top, d_front = (420 - 404) / 644, (1040 - 404) / 644
    hits, _ = run(out, "keys_default", None, keys)
    on = [h for h in hits if h[1] > 0]
    expect("keys: default", [x[1] for x in on], [v(30, 127, d_top), v(30, 127, d_front)])
    hits, _ = run(out, "keys_fixed", {"all": {"mode": "fixed", "fixed": 77}}, keys)
    expect("keys: fixed 77", [x[1] for x in hits if x[1] > 0], [77, 77])
    hits, _ = run(out, "keys_soft_flip", {"all": {"mode": "position", "lo": 10, "hi": 120, "curve": "soft", "flip": True}}, keys)
    expect("keys: soft, reversed", [x[1] for x in hits if x[1] > 0], [v(10, 120, d_top, 1.6, True), v(10, 120, d_front, 1.6, True)])
    hits, _ = run(out, "keys_own", {"all": {"mode": "fixed", "fixed": 77}, "keys_own": True,
                                    "keys": {"mode": "position", "lo": 40, "hi": 100, "curve": "hard"}}, keys)
    expect("keys: own over Setup's", [x[1] for x in hits if x[1] > 0], [v(40, 100, d_top, 0.6), v(40, 100, d_front, 0.6)])
    expect("keys: each let go", len([h for h in hits if h[1] == 0]), 2)

    # A HELD KEY DRAWN: sideways a bend (a key's width -- 7/12 of a white key, 63.9 -- a semitone, past a quarter's
    # wobble), toward the front aftertouch (its full 127 at 0.35 of the key's depth); a glissando strikes others
    ww = (1886 - 34) / 29
    drag = [piano, "wait 600", card("keys"), "wait 500", "drag 55 700 %.0f 700 400" % (55 + ww * 7 / 12 * 1.25), "wait 400",
            "drag 55 600 55 900 400", "wait 400"]
    hits, _ = run(out, "keys_bend", {"keys_slide": "bend"}, drag)
    bends = [c[1] for c in run.ctl if c[0] == "bend"]
    # (a scripted drag lifts on its last step: the card sees the one before, a few points short)
    expect("bend: drawn a key's width", len(bends) >= 2 and abs(bends[-2] - 1.0) < 0.07, True)
    expect("bend: back to 0 on lift", bends[-1] if bends else None, 0)
    expect("bend: one key struck", len(set(h[0] for h in hits if h[1] > 0)), 1)
    hits, _ = run(out, "keys_press", {"keys_slide": "press"}, drag)
    pr = [c[1] for c in run.ctl if c[0] == "press"]
    expect("aftertouch: drawn deep, full", max(pr) if pr else None, 127)
    expect("aftertouch: 0 on lift", pr[-1] if pr else None, 0)
    hits, _ = run(out, "keys_glide", None, drag)
    expect("glissando: keys crossed struck", len(set(h[0] for h in hits if h[1] > 0)) >= 2, True)
    expect("glissando: no bend or pressure", run.ctl, [])

    # THE PADS: the first pad (its top 0..96 from the grid's first row); the second, slid onto
    pads = [kit, "wait 800", card("drums"), "wait 800", "tap PX PT", "wait 300", "tap PX PB", "wait 300",
            "drag PX PB PX2 PB 300", "wait 400"]
    if shots:
        pads += ["shot SHOTpads.ppm"]
    # (the laptop's first pad, C-1 -- the pads the card's width since the KITS card took the list:
    #  from x 34, its top at y 430 under "Kicks", 96 tall; the second from x 200)
    geo = {"x": 100, "x2": 260, "top": 430, "yt": 436, "yb": 516, "h": 96}
    if geo:
        pads = [s.replace("PX2", str(geo["x2"])).replace("PX", str(geo["x"])).replace("PT", str(geo["yt"])).replace("PB", str(geo["yb"]))
                for s in pads]
        hits, _ = run(out, "pads_default", None, pads)
        on = [h for h in hits if h[1] > 0]
        dt, db = 1 - (geo["yt"] - geo["top"]) / geo["h"], 1 - (geo["yb"] - geo["top"]) / geo["h"]
        expect("pads: default", [x[1] for x in on], [v(30, 127, dt), v(30, 127, db), v(30, 127, db)])
        expect("pads: a slide strikes no other", len(set(x[0] for x in on)), 1)
        hits, saved = run(out, "pads_own_fixed", {"drums_own": True, "drums": {"mode": "fixed", "fixed": 55}}, pads)
        expect("pads: own fixed 55", [x[1] for x in hits if x[1] > 0], [55, 55, 55])
        expect("session keeps the touch", saved.get("ui", {}).get("touch", {}).get("drums", {}).get("fixed"), 55)
    print("%d failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
