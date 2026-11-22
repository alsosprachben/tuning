"""The Spectra-Tone through live.Live (no device), measured as the takes were.

60's Organ 1 on SPECTRA-TONE (its variation key's speaker choice,
patch_map.cab_key), C6 then C7 held, the rocker as st_change had it: Theater
10 s, Cathedral 25 s, Theater 20 s -- block by block through live's callback,
as nvlive_check feeds it. Each held note's swells per turn and pitch swing in
the steady stretches (spectratone_garage.measure), the rotor's speed as it
went (Live.rotor_spectra), and its spin-up time.

    python3 examples/spectratone_live_check.py [--chorus]
"""
import os, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))


def main(argv):
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    import patch_map as PM
    import spectratone_fit as F
    import spectratone_garage as G
    from scipy.io import wavfile
    choice = PM.CAB_CHOICES.index("spectra_chorus" if "--chorus" in argv else "spectra")
    tuner = "hybrid440"
    part = L.Part(L.patch_for(16, False, tuner, variation=PM.cab_key(16, choice)))
    lv = L.Live(program=16, rate=48000, frames=128, capacity=65536, verbose=False, threads=1, gpu=False,
                tuner=tuner, parts=[part])
    lv.parts[0].patch.warm()
    import patchsync
    patchsync.sync(lv)
    lv.slab.shed = lambda n, frac: 0
    M = mido.Message
    ev = [(0.0, M("control_change", channel=0, control=80, value=127))]
    s = 1.0
    for note in (84, 96):
        ev += [(s, M("note_on", channel=0, note=note, velocity=100)),
               (s + 10.0, M("control_change", channel=0, control=80, value=0)),
               (s + 35.0, M("control_change", channel=0, control=80, value=127)),
               (s + 55.0, M("note_off", channel=0, note=note, velocity=0))]
        s += 58.0
    total = s
    ev.sort(key=lambda e: e[0])
    out, rate = [], []
    e = 0
    nb = int(total * 48000) // 128
    for b in range(nb):
        while e < len(ev) and int(ev[e][0] * 48000) // 128 <= b:
            lv.on_midi(ev[e][1]); e += 1
        out.append(np.frombuffer(lv.callback(None, 128, None, 0)[0], np.float32).reshape(-1, 2))
        rate.append(lv.rotor_spectra.rate)
    if lv.cb_exceptions:
        print("live's callback raised %d times; the last: %s" % (lv.cb_exceptions, lv.last_error))
        return 1
    y = np.concatenate(out).astype(np.float64)
    rate = np.array(rate)
    tb = np.arange(nb) * 128 / 48000.0
    # the spin-up: from Cathedral to 1 - 1/e of the way to Theater, after the switch at 36 s
    i = np.flatnonzero(tb >= 36.0)[0]
    lo, hi = rate[i - 1], 2.95
    j = np.flatnonzero(rate[i:] >= lo + (hi - lo) * (1 - np.exp(-1)))
    print("rotor: Theater %.2f, Cathedral %.2f turns/s; spin-up tau %.1f s" % (
        rate[int(10.5 * 375)], rate[int(35.5 * 375)], (j[0] * 128 / 48000.0) if len(j) else float("nan")))
    pk = np.abs(y).max() + 1e-12
    d = tempfile.mkdtemp()
    wavfile.write(os.path.join(d, "live.wav"), 48000, (y / pk * 0.7 * 32767).astype(np.int16))
    F.DIR = d
    for o, t0 in ((6, 1.0), (7, 59.0)):
        for label, a, b_, guess in (("Theater", t0 + 2.0, t0 + 10.0, 2.95), ("Cathedral", t0 + 13.0, t0 + 34.0, 0.60)):
            for r in G.measure("live.wav", (o,), a, b_, frot_guess=guess, harmonics=1):
                print("  C%d %-9s %7.1f Hz  rotor %.2f  c1-3 %s  pitch %4.1f c  depth %4.1f dB" % (
                    o, label, r["f"], r["frot"], " ".join("%.2f" % v for v in r["c"][:3]), r["cents"], r["depth"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
