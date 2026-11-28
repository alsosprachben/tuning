"""A PIANO's KNOBS, LIVE (piano_knobs.py; the host's set_voicing): through the
host library in step (ctypes, no device), a part on the grand --

- its knobs as the VOICE card reads them (voicing): the grand's seven, each
  at the voice's value, none its own, the patch not building;
- a knob turned (voicing_set): the patch rebuilt (seen building, then in), the
  knob its own at the value set, and the note struck after it changed the
  way the knob says -- the felt harder: brighter; the lid shut: darker;
- put back (voicing_forget): the note as it was before any knob moved;
- a program change: the knobs gone (another instrument's, as a cabinet's).

Brightness is the spectrum's centroid over a note's first 0.4 s.

    python3 examples/voicing_live_check.py EXPORT.nvx [PROGRAM]

PROGRAM 27 or 33 (an electric guitar, a bass): PICK, STRINGS and TONE; the
pick at the bridge, brighter; the strings dead, darker; the tone pot all the
way down, darker.

PROGRAM 4 (the Rhodes) instead: its four knobs; the swing wider and the
pickup closer, brighter; the tone bar up, its bell heard in the attack (a
12 ms ring: the first 50 ms changed by more than -30 dB re the note).
"""
import ctypes
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    nvx = argv[1]
    prog = int(argv[2]) if len(argv) > 2 else 0
    import native as N
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_rate", [vp]),
                 ("nv_host_render", [vp, vp, vp, ci]), ("nv_host_midi", [vp, ctypes.c_char_p, ci])):
        getattr(d, f).argtypes = a
    d.nv_ui_watch_new.restype = vp
    d.nv_ui_call.restype = ctypes.c_void_p
    d.nv_ui_call.argtypes = [vp, vp, cp]
    d.nv_ui_free.argtypes = [vp]
    av = [b"nvlive", nvx.encode(), ("--program=%d" % prog).encode(), b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor"]
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    w = d.nv_ui_watch_new()
    blk, sr = d.nv_host_block(h), d.nv_host_rate(h)
    L = np.zeros(blk, np.float32)
    R = np.zeros(blk, np.float32)

    def call(o):
        p = d.nv_ui_call(h, w, json.dumps(o).encode())
        r = json.loads(ctypes.string_at(p).decode())
        d.nv_ui_free(p)
        return r

    def render(sec):
        out = []
        for _ in range(max(1, int(sec * sr) // blk)):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            out.append(L + R)
        return np.concatenate(out)

    def strike(key, vel=100, hold=0.5):
        d.nv_host_midi(h, bytes([0x90, key, vel]), 3)
        x = render(hold)
        d.nv_host_midi(h, bytes([0x80, key, 0]), 3)
        render(1.0)
        return x

    def bright(x, win=0.4):
        x = x[:int(win * sr)] * np.hanning(int(win * sr))
        s = np.abs(np.fft.rfft(x)) ** 2
        f = np.fft.rfftfreq(len(x), 1.0 / sr)
        return float((s * f).sum() / max(1e-30, s.sum()))

    def highs(x, win=0.4):
        """the share of the note's power above 1.5 kHz, in thousandths (a tone
        pot turned down: its capacitor's resonance can lift the mids a bass
        lives in, so the centroid alone can rise while the highs go)"""
        x = x[:int(win * sr)] * np.hanning(int(win * sr))
        s = np.abs(np.fft.rfft(x)) ** 2
        f = np.fft.rfftfreq(len(x), 1.0 / sr)
        return float(1000.0 * s[f > 1500.0].sum() / max(1e-30, s.sum()))

    def settle(k=None):
        """until the patch is in: (its knobs then, the seconds it took, whether
        it was seen building) -- k: the knob just set, its own once posted"""
        t0, saw = time.time(), False
        while time.time() - t0 < 60:
            render(0.02)
            v = call({"call": "voicing", "row": 0})["voicing"]
            saw = saw or v["building"]
            mine = k is None or any(x["k"] == k and x["own"] for x in v["knobs"])
            if mine and not v["building"] and (saw or k is None or time.time() - t0 > 2.0):
                took = time.time() - t0
                render(0.1)     # (the patch built is handed to the audio a block or two after: then strike)
                return v, took, saw
        return v, None, saw

    render(1.0)
    bad = 0
    v = call({"call": "voicing", "row": 0})["voicing"]
    names = [k["name"] for k in v["knobs"]]
    want = {0: ["felt", "felt_left", "strike", "unison", "lid", "board"], 4: ["tine", "gap", "swing", "tonebar"]}.get(
        prog, ["pick", "strings", "tone"])
    ok = names == want and not any(k["own"] for k in v["knobs"])
    ok = ok and all(abs(k["v"] - k["v0"]) < 1e-12 and k["lo"] <= k["v"] <= k["hi"] for k in v["knobs"])
    print("the voice's knobs:", ", ".join("%s %s" % (k["name"], k["text"]) for k in v["knobs"]), "ok" if ok else "WRONG")
    bad += not ok
    kn = {k["name"]: k for k in v["knobs"]}
    keys = {0: (60, 84), 4: (48, 60, 72)}.get(prog, (40, 52, 64) if prog < 32 else (28, 40))
    base = {key: bright(strike(key)) for key in keys}
    print("plain: brightness %s" % ", ".join("key %d %.0f Hz" % kv for kv in base.items()))

    def case(name, k, val, key, darker, win=0.4, late=False, hi=False):
        """... late: the brightness of 0.4 s two seconds into a held note (a
        bass's strings: their loss shows as the note goes on); hi: the
        highs' share (highs) and not the centroid"""
        nonlocal bad
        tail = int(0.4 * sr)
        x_plain = strike(key, hold=2.4 if late else 0.5) if win != 0.4 or late or hi else None
        b_plain = (highs(x_plain) if hi else bright(x_plain[-tail:]) if late else bright(x_plain, win) if win != 0.4
                   else base[key])
        call({"call": "voicing_set", "row": 0, "k": k, "v": val})
        v, took, b0 = settle(k)
        own = [x for x in v["knobs"] if x["k"] == k][0]
        x = strike(key, hold=2.4 if late else 0.5)
        b = highs(x) if hi else bright(x[-tail:]) if late else bright(x, win)
        moved = b < 0.98 * b_plain if darker else b > 1.02 * b_plain
        if win != 0.4:          # (a brief part of the attack: how much the note changed there, re the note)
            n = int(win * sr)
            dd = 10 * np.log10(np.sum((x[:n] - x_plain[:n]) ** 2) / max(1e-30, np.sum(x_plain[:n] ** 2)))
            moved = dd > -30.0
        ok = b0 and took is not None and own["own"] and abs(own["v"] - val) < 1e-9 and moved
        print("%-14s building %s, rebuilt in %s s, its own %s at %s; key %d %s %.3g %s (plain %.3g)  %s" % (
            name, b0, "%.1f" % took if took is not None else "never", own["own"], own["text"], key,
            "highs" if hi else "brightness", b, "/1000" if hi else "Hz", b_plain,
            "ok" if ok else "WRONG"))
        if win != 0.4:
            print("               (the first %.0f ms changed by %.1f dB re the note)" % (win * 1000, dd))
        bad += not ok
        call({"call": "voicing_forget", "row": 0, "k": -1})
        render(0.1)
        settle()

    if prog == 0:
        case("felt harder", 0, kn["felt"]["v0"] + 1.0, 84, False)
        case("lid shut", 4, -9.0, 84, True)
        case("board lower", 5, kn["board"]["v0"] * 0.5, 60, True)
    elif prog != 4:
        g = keys[1]
        case("pick at bridge", 12, 0.06, g, False)
        case("strings dead", 13, kn["strings"]["v0"] * 5.0, g, True, late=True)
        case("tone down", 14, 0.004, g, True, hi=True)
    else:
        case("swing wider", 9, kn["swing"]["v0"] * 1.8, 60, False)
        case("pickup closer", 8, kn["gap"]["v0"] * 0.5, 48, False)
        case("tone bar up", 10, kn["tonebar"]["v0"] * 4.0, 72, False, 0.05)
    after = {key: bright(strike(key)) for key in keys}
    v = call({"call": "voicing", "row": 0})["voicing"]
    ok = all(abs(after[k] - base[k]) < 0.005 * base[k] for k in base) and not any(x["own"] for x in v["knobs"])
    print("put back: brightness %s  %s" % (", ".join("key %d %.0f Hz" % kv for kv in after.items()), "ok" if ok else "WRONG"))
    bad += not ok
    # A PROGRAM CHANGE is another instrument: its knobs go (as its cabinet does)
    k4 = {0: 4, 4: 9}.get(prog, 12)
    call({"call": "voicing_set", "row": 0, "k": k4, "v": {0: -6.0, 4: kn["swing"]["v0"] * 1.5 if prog == 4 else 0.0}.get(prog, 0.1)})
    settle(k4)
    d.nv_host_midi(h, bytes([0xC0, prog]), 2)
    render(0.2)
    v, took, _ = settle()
    ok = not any(x["own"] for x in v["knobs"])
    print("program change: its knobs %s  %s" % ("gone" if ok else "kept", "ok" if ok else "WRONG"))
    bad += not ok
    print("%d wrong" % bad)
    sys.stdout.flush()
    os._exit(bad)


if __name__ == '__main__':
    main(sys.argv)
