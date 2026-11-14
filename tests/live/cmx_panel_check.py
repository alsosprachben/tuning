#!/usr/bin/env python3
"""The controller matrix on the panel (livetui's C, nvlive's): python3 tests/live/cmx_panel_check.py

The panel moves a cell by sending the GS message a sequencer would
(ctrlmatrix.cell_message, assign_message; nvlive's cmx.h the same), and a
scene keeps the matrix as those messages (ctrlmatrix.scene_messages; a
recall puts back what the scene does not name, undo_messages). Checked:

  bytes     the panel's messages are the very exclusives cmx_live.mid carries
            -- the file whose effects (quieter, up two semitones, brighter, a
            vibrato, a tremolo) tests/live/effects.py measures in live.Live and
            nvlive -- so what the panel sends is heard in both
  native    cmx.h's panel half against ctrlmatrix: every byte's printed value
            and its inverse, the scene and undo messages of random matrices
            (GS cells, CC1/CC2's numbers, GM2's controller cells)
  scene     live.Live: a scene holds the matrix; recalled on another Live it
            makes the same; a scene without one puts a changed matrix back
  nvlive    nvlive --test playing the matrix: the session's scene the same
            events as live's scene_from; that session recalled by nvlive and
            saved again, the same

Exits 1 if any check fails.
"""
import json
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))
os.environ.setdefault("TUNING_NATIVE_TONE", "off")
import mido  # noqa: E402
import ctrlmatrix as CMX  # noqa: E402

BLK = lambda b, a: (9 if b == 0 else (b - 1 if b <= 9 else b)) + (16 if a == 0x50 else 0)   # noqa: E731


def lines(ms):
    return "".join(" ".join(str(b) for b in d) + "\n" for d in ms)


def parse_lines(out):
    return [tuple(int(x) for x in ln.split()) for ln in out.splitlines() if ln.strip()]


def matrix_of(msgs, ch):
    m = CMX.Matrix()
    for d in msgs:
        r = CMX.parse(d, BLK)
        if r and r[0] == ch:
            m.apply(r[1], r[2])
    return m


def random_msgs(rng, ch):
    out = []
    for _ in range(rng.randint(0, 14)):
        k = rng.random()
        if k < 0.65:
            src = rng.choice([s for _r, s in sorted(CMX.GS_SOURCES.items())])
            dest = rng.choice(CMX.GS_DESTS)
            lo, hi = CMX.RAW_RANGE.get(dest, (0, 127))
            out.append(CMX.cell_message(ch, src, dest, rng.choice([lo, hi, 0x40, rng.randint(lo, hi)])))
        elif k < 0.8:
            out.append(CMX.assign_message(ch, rng.choice(('cc1', 'cc2')), rng.choice([16, 17, rng.randint(0, 95)])))
        else:
            src = rng.choice([1, 2, 3])
            d = [0x7F, 0x7F, 0x09, src, ch] + ([rng.randint(1, 95)] if src == 3 else [])
            for _ in range(rng.randint(1, 3)):
                d += [rng.randint(0, 5), rng.choice([0, 64, 127, rng.randint(0, 127)])]
            out.append(tuple(d))
    return out


def main():
    bad, n = 0, 0

    def check(what, ok, detail=""):
        nonlocal bad, n
        n += 1
        bad += not ok
        print("  %-66s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    # THE BYTES: cmx_live.mid's matrix exclusives, made again by the panel's builders
    f = mido.MidiFile(os.path.join(HERE, "midi", "cmx_live.mid"))
    got = []
    for tr in f.tracks:
        for m in tr:
            if m.type == "sysex":
                r = CMX.parse(m.data, BLK)
                if r is None:
                    continue
                ch, kind, p = r
                if kind == "cell":
                    src, dest, dep = p
                    mine = CMX.cell_message(ch, src, dest, CMX.gs_raw(dest, dep))
                else:
                    mine = CMX.assign_message(ch, p[0], p[1])
                got.append((tuple(m.data), tuple(mine)))
    check("the panel's messages: cmx_live.mid's %d exclusives byte for byte" % len(got),
          len(got) >= 5 and all(a == b for a, b in got),
          "; ".join("%s != %s" % (a, b) for a, b in got if a != b))

    # NATIVE: cmx.h's panel half against ctrlmatrix
    tmp = tempfile.mkdtemp(prefix="cmxpanel")
    exe = os.path.join(tmp, "cmx_check")
    subprocess.check_call(["g++", "-std=c++17", "-O1", os.path.join(HERE, "cmx_check.cpp"), "-o", exe])
    out = subprocess.run([exe, "printed"], capture_output=True, text=True).stdout.splitlines()
    want = ["%d %d %d %s" % (c, v, CMX.gs_raw(d, CMX.gs_depth(d, v)), CMX.printed(d, CMX.gs_depth(d, v)))
            for c, d in enumerate(CMX.GS_DESTS) for v in range(*((0x28, 0x59) if d == 'pitch' else (0, 128)))]
    diff = [(a, b) for a, b in zip(out, want) if a != b]
    check("cmx.h: every destination's every byte printed, and its inverse (%d)" % len(want),
          len(out) == len(want) and not diff, "%s" % diff[:3])
    rng = random.Random(7)
    sc_bad = un_bad = 0
    trials = 300
    for t in range(trials):
        ch = rng.choice([0, 3, 9, 15])
        msgs = random_msgs(rng, ch)
        m = matrix_of(msgs, ch)
        r = subprocess.run([exe, "scene", str(ch)], input=lines(msgs), capture_output=True, text=True)
        sc_bad += parse_lines(r.stdout) != [tuple(x) for x in CMX.scene_messages(ch, m)]
        keep = random_msgs(rng, ch)
        r = subprocess.run([exe, "undo", str(ch)], input=lines(msgs) + "--\n" + lines(keep),
                           capture_output=True, text=True)
        un_bad += parse_lines(r.stdout) != [tuple(x) for x in CMX.undo_messages(ch, m, keep)]
    check("cmx.h: a matrix's scene messages, %d random matrices" % trials, sc_bad == 0, "%d differ" % sc_bad)
    check("cmx.h: undo messages under a scene's, %d random" % trials, un_bad == 0, "%d differ" % un_bad)

    # THE SCENE, in live.Live
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L

    def drain_apply(lv):
        with lv.lock:
            ev = [m for _t, m in lv.events]
            lv.events.clear()
        for m in ev:
            if m.type == "sysex":
                lv._sysex(0, m)
        return ev

    lv = L.Live(program=0, rate=48000, frames=128)
    lv.cmx_send(2, 'cat', 'pitch', 0x4C)                # (the panel's calls: channel 3)
    lv.cmx_send(2, 'mod', 'lfo1_pitch', 0)
    lv.cmx_assign_send(2, 'cc2', 21)
    lv.cmx_send(2, 'cc2', 'cutoff', 0x70)
    lv.cmx_send(None, 'pat', 'lfo2_tva', 90)            # (a part on every channel: every channel's)
    sent = drain_apply(lv)
    st = lv.cmx_state(2)
    check("live.Live: the panel's calls reach the matrix (%d messages)" % len(sent),
          len(sent) == 20 and st['gs'][('cat', 'pitch')] == 12.0 and st['cc_of']['cc2'] == 21
          and st['gs'][('mod', 'lfo1_pitch')] == 0.0 and abs(lv.cmx_state(11)['gs'][('pat', 'lfo2_tva')] - 90 / 127.0) < 1e-12,
          "%s" % sorted(st['gs'].items(), key=str)[:4])
    ev = L.scene_from(lv)
    sx = [e for e in ev if e.startswith("sysex")]
    lv2 = L.Live(program=0, rate=48000, frames=128)
    L.recall_scene(lv2, ev)
    drain_apply(lv2)
    same = all(lv2.cmx.get(c) is not None and lv2.cmx[c].cells() == lv.cmx[c].cells()
               and lv2.cmx[c].cc_of == lv.cmx[c].cc_of for c in range(16))
    check("live.Live: a scene keeps it (%d exclusives); recalled, the same" % len(sx), len(sx) == 16 + 4 and same)
    L.recall_scene(lv, [e for e in ev if not e.startswith("sysex")])
    drain_apply(lv)
    check("live.Live: a scene without one puts the matrix back to a reset's",
          all(lv.cmx[c].cells() == CMX.Matrix().cells() and lv.cmx[c].cc_of == CMX.Matrix().cc_of for c in lv.cmx))

    # NVLIVE: the session's scene, and that session recalled
    import nvlive_check as NC
    import native as N
    nvx = NC.live_export(tmp, "hall")
    nvl = N.build_nvlive()
    msgs = ([CMX.cell_message(0, 'cat', 'pitch', 0x4C), CMX.cell_message(0, 'mod', 'lfo1_pitch', 0),
             CMX.assign_message(0, 'cc1', 20), CMX.cell_message(0, 'cc1', 'cutoff', 0x70),
             CMX.cell_message(4, 'bend', 'pitch', 0x4C), (0x7F, 0x7F, 0x09, 0x03, 0x04, 0x50, 0x01, 0x10, 0x05, 0x40)])
    mid = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    for d in msgs:
        tr.append(mido.Message("sysex", data=d, time=0))
    tr.append(mido.Message("note_on", channel=0, note=60, velocity=90, time=48))
    tr.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=240))
    fm = os.path.join(tmp, "cmx_panel.mid")
    mid.save(fm)
    plain = mido.MidiFile(ticks_per_beat=480)
    tp = mido.MidiTrack()
    plain.tracks.append(tp)
    tp.append(mido.Message("note_on", channel=0, note=60, velocity=90, time=48))
    tp.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=240))
    fp = os.path.join(tmp, "plain.mid")
    plain.save(fp)

    def nv_session(f, sess):
        subprocess.run([nvl, nvx, "--test", f, os.path.join(tmp, "o.wav"), "--program=0", "--seconds=1.5",
                        "--cpu", "--no-drums", "--no-register", "--session=" + sess],
                       check=True, capture_output=True)
        return [e for e in json.load(open(sess)).get("chanstate", []) if e.startswith("sysex")]

    s1 = os.path.join(tmp, "s1.json")
    got = nv_session(fm, s1)
    lv3 = L.Live(program=0, rate=48000, frames=128)
    for d in msgs:
        lv3._sysex(0, mido.Message("sysex", data=d))
    want = [e for e in L.scene_from(lv3) if e.startswith("sysex")]
    check("nvlive: the session's scene holds the matrix as live's (%d exclusives)" % len(want),
          got == want and len(want) >= 6, "\n    nv %s\n    py %s" % (got, want) if got != want else "")
    s2 = os.path.join(tmp, "s2.json")
    with open(s1) as fh:
        js = json.load(fh)
    with open(s2, "w") as fh:
        json.dump(js, fh)
    got2 = nv_session(fp, s2)
    check("nvlive: that session recalled (a file with no matrix), saved again: the same",
          got2 == want, "%s" % got2)
    print("controller matrix panel: %d checked, %d failed" % (n, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
