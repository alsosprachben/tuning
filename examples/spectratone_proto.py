"""A prototype Spectra-Tone, for Ben's ear before the model is ported.

Each partial of Flute 8 at the level the warm take holds it (so only the
MOTION differs), through the fitted two cones in the fitted garage
(spectratone_garage.json), the rotor turning on leslie.Rotor with the measured
speeds and spin times. Played as Ben played the takes:

  warm    C2..C7 fast ~10 s each, then slow ~15 s each (st_warm.wav)
  change  C6 held: fast 10 s, slow 25 s, fast 20 s; then C7 the same (st_change.wav)

Writes ~/Music/spectratone_proto/{ours,take}_{warm,change}.mp3.

    python3 examples/spectratone_proto.py
"""
import os, sys, json, subprocess
import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import spectratone_fit as F
import spectratone_garage as G
from spectratone_response import levels
import leslie

SR = 48000
SLOW, FAST = 0.60, 2.95
TAUS = (13.0, 1.0)
OUT = os.path.expanduser("~/Music/spectratone_proto")
NG = 1440


def params():
    P = json.load(open(os.path.join(F.DIR, "spectratone_garage.json")))["params"]
    return np.array([P[n] for n in G.NAMES])


def spectra():
    """{octave: [(f, amplitude)]}: the warm take's own partials (slow half, mean over turns)."""
    lv = levels("st_warm.wav", 113.0, 226.0, (2, 3, 4, 5, 6, 7), harmonics=8, floor_db=-80.0)
    out = {}
    for (o, h), (f, db) in lv.items():
        out.setdefault(o, []).append((f, 10 ** (db / 20)))
    return out


def render(events, total, requests, p, spec):
    """events [(t0, t1, octave)]; requests [(t, Hz)] for the rotor."""
    rot = leslie.Rotor(True, requests, taus=TAUS, length=total)
    t = np.arange(int(total * SR)) / SR
    th = np.mod(rot.angles(t), 2 * np.pi)
    gi = th / (2 * np.pi) * NG
    i0 = np.floor(gi).astype(int) % NG; i1 = (i0 + 1) % NG; w = gi - np.floor(gi)
    y = np.zeros(len(t))
    cache = {}
    for t0, t1, o in events:
        a, b = int(t0 * SR), int(t1 * SR)
        env = np.ones(b - a)
        na, nr = int(0.01 * SR), int(0.05 * SR)
        env[:na] = np.linspace(0, 1, na); env[-nr:] = np.linspace(1, 0, nr)
        tt = t[a:b]
        for f, amp in spec[o]:
            if f not in cache:
                S = G.response(f, p, NG)
                cache[f] = S / np.mean(np.abs(S))
            S = cache[f]
            Sv = S[i0[a:b]] * (1 - w[a:b]) + S[i1[a:b]] * w[a:b]
            y[a:b] += amp * env * np.real(np.exp(2j * np.pi * f * tt) * Sv)
    return y


def save(name, y):
    y = y / (np.abs(y).max() + 1e-12) * 0.7
    os.makedirs(OUT, exist_ok=True)
    wav = os.path.join(OUT, name + ".wav")
    wavfile.write(wav, SR, (np.stack([y, y], 1) * 32767).astype(np.int16))
    subprocess.run(["lame", "--quiet", "-b", "256", wav, wav[:-4] + ".mp3"], check=True)
    os.remove(wav)


def take(name, t0, t1):
    x, sr = F.load(name)
    return x[int(t0 * sr):int(t1 * sr)]


def main(argv):
    p = params()
    spec = spectra()
    # warm: fast C2..C7, 10 s each with 1 s gaps, then slow 15 s each
    ev, t = [], 1.0
    for o in (2, 3, 4, 5, 6, 7):
        ev.append((t, t + 10.0, o)); t += 11.0
    switch = t
    t += 2.0
    for o in (2, 3, 4, 5, 6, 7):
        ev.append((t, t + 15.0, o)); t += 16.0
    save("ours_warm", render(ev, t + 1.0, [(0.0, FAST), (switch, SLOW)], p, spec))
    save("take_warm", take("st_warm.wav", 26.0, 216.0))
    # change: C6 then C7, each fast 10 s -> slow 25 s -> fast 20 s
    ev, req, t = [], [(0.0, FAST)], 1.0
    for o in (6, 7):
        ev.append((t, t + 55.0, o))
        req += [(t + 10.0, SLOW), (t + 35.0, FAST)]
        t += 58.0
    save("ours_change", render(ev, t, req, p, spec))
    save("take_change", take("st_change.wav", 28.0, 189.0))
    print("written:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main(sys.argv)
