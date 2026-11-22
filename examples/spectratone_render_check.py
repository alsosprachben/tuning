"""The Spectra-Tone through the renderer, measured as Ben's takes were.

60's Organ 1 with SPECTRA-TONE chosen (CC83, patch_map.SPECTRA_CHOICES),
single notes C2..C7 as st_warm has them -- Theater (CC80 127) 10 s each, then
Cathedral (CC80 0) 15 s each -- rendered dry (TUNING_REFLECT=0: the direct
path alone, the cones as fitted) or in the room (--room). Each partial's swells
per turn (c1..c3 of its level over a turn), its pitch swing and depth, by
spectratone_garage.measure, beside the takes'.

    python3 examples/spectratone_render_check.py [--room] [--chorus] [--wav=PATH] [--from=PATH]
"""
import os, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
if "--room" not in sys.argv:
    os.environ["TUNING_REFLECT"] = "0"


def midi(choice):
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tk = lambda s: int(round(s * 960))
    ev = [(0.0, mido.Message("control_change", channel=0, control=0, value=16)),
          (0.0, mido.Message("program_change", channel=0, program=16)),
          (0.0, mido.Message("control_change", channel=0, control=83, value=choice)),
          (0.0, mido.Message("control_change", channel=0, control=80, value=127))]
    s = 1.0
    for o in (2, 3, 4, 5, 6, 7):
        ev += [(s, mido.Message("note_on", channel=0, note=12 * (o + 1), velocity=100)),
               (s + 10.0, mido.Message("note_off", channel=0, note=12 * (o + 1), velocity=0))]
        s += 11.0
    ev.append((s, mido.Message("control_change", channel=0, control=80, value=0)))
    s += 3.0
    for o in (2, 3, 4, 5, 6, 7):
        ev += [(s, mido.Message("note_on", channel=0, note=12 * (o + 1), velocity=100)),
               (s + 15.0, mido.Message("note_off", channel=0, note=12 * (o + 1), velocity=0))]
        s += 16.0
    ev.append((s + 1.0, mido.MetaMessage("end_of_track")))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        msg.time = tk(at) - now; now = tk(at)
        t.append(msg)
    return m, s


def main(argv):
    import blockrender as B
    import patch_map as PM
    import spectratone_fit as F
    import spectratone_garage as G
    from scipy.io import wavfile
    choice = PM.CAB_CHOICES.index("spectra_chorus" if "--chorus" in argv else "spectra")
    m, total = midi(choice)
    src = next((a.split("=", 1)[1] for a in argv if a.startswith("--from=")), None)
    if src:                                 # measure a render already made
        sr, y = wavfile.read(src)
        L, R = y[:, 0].astype(np.float64), y[:, 1].astype(np.float64)
    else:
        L, R = B.render(m)[:2]
        sr = B.SR
    L, R = np.asarray(L, np.float64), np.asarray(R, np.float64)
    pk = max(np.abs(L).max(), np.abs(R).max()) + 1e-12
    y = (np.stack([L, R], 1) / pk * 0.7 * 32767).astype(np.int16)
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--wav=")), None)
    d = tempfile.mkdtemp()
    name = "render.wav"
    wavfile.write(os.path.join(d, name), sr, y)
    if out:
        wavfile.write(out, sr, y)
    F.DIR = d
    fast_end = 1.0 + 6 * 11.0
    take = {}
    for nm, notes, lo, hi in (("st_warm.wav", (2, 3, 4, 5, 6, 7), 113.0, 226.0),):
        Fd = F.DIR
        F.DIR = os.path.expanduser("~/Documents/refs/wurlitzer_ben/spectratone2")
        for r in G.measure(nm, notes, lo, hi):
            take.setdefault(round(r["f"], 0), r)
        F.DIR = Fd
    for label, lo, hi, guess in (("Theater", 0.0, fast_end, 2.95), ("Cathedral", fast_end + 3.0, None, 0.60)):
        print("%s:" % label)
        for r in G.measure(name, (2, 3, 4, 5, 6, 7), lo, hi, frot_guess=guess):
            t = take.get(round(r["f"], 0)) if label == "Cathedral" else None
            print("  %7.1f Hz  rotor %.2f Hz  c1-3 %s  pitch %4.1f c  depth %4.1f dB%s" % (
                r["f"], r["frot"], " ".join("%.2f" % v for v in r["c"][:3]), r["cents"], r["depth"],
                ("   | take c1-3 %s  %4.1f c  %4.1f dB" % (" ".join("%.2f" % v for v in t["c"][:3]),
                                                           t["cents"], t["depth"])) if t else ""))


if __name__ == "__main__":
    main(sys.argv)
