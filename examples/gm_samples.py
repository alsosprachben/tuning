#!/usr/bin/env python3
"""What do General MIDI sets play for a program? Its samples, read straight out
of the SoundFonts on this machine (examples/gm_release.py's four) and measured
as examples/wind_fit.py measures a recording -- for a voice with no usable
recording of its own, the sets' consensus is the next-best witness.

    python3 examples/gm_samples.py PROGRAM [--pluck]

Per sample zone of the bank-0 preset: its key range and root key, the SF2
low-pass it is played through (generator 8, initialFilterFc, cents re 8.176
Hz; 13500 = open), and its sustain's harmonic ladder, h1-h12 dB re h1 -- the
LOOP (what a held note sustains on) tiled to 0.5 s, or the sample's last
0.4 s when it has none. --pluck reads a plucked sample where it is heard,
50-250 ms from its start, not its loop (a pluck's loop is its decayed tail).
The filter is NOT applied to the ladder: it is printed, to be read beside it.
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)
from gm_release import SETS, _chunks, _recs  # noqa: E402

INST, SAMPLE, KEYRANGE, ROOT, FC = 41, 53, 43, 58, 8
NH = 12


def zones(path, program):
    """(preset name, [(lo key, hi key, root key, fc, sample rate, data, loop)])."""
    b = open(path, "rb").read()
    d, smpl = None, None
    for cid, o, sz in _chunks(b, 12, len(b)):
        if cid == b"LIST" and b[o:o + 4] == b"pdta":
            d = {c.decode(): b[oo:oo + s] for c, oo, s in _chunks(b, o + 4, o + sz)}
        if cid == b"LIST" and b[o:o + 4] == b"sdta":
            for c, oo, s in _chunks(b, o + 4, o + sz):
                if c == b"smpl":
                    smpl = (oo, s)
    phdr = _recs(d["phdr"], "<20sHHHIII", 38)
    pbag, pgen = _recs(d["pbag"], "<HH", 4), _recs(d["pgen"], "<HH", 4)
    inst, ibag, igen = _recs(d["inst"], "<20sH", 22), _recs(d["ibag"], "<HH", 4), _recs(d["igen"], "<HH", 4)
    shdr = _recs(d["shdr"], "<20sIIIIIBbHH", 46)

    def gens(gen, bag, i):
        return {g[0]: g[1] for g in gen[bag[i][0]:bag[i + 1][0]]}
    for pi, h in enumerate(phdr[:-1]):
        if h[2] != 0 or h[1] != program:
            continue
        out = []
        for zb in range(h[3], phdr[pi + 1][3]):
            pg = gens(pgen, pbag, zb)
            if INST not in pg:
                continue
            iglob = {}
            for zi in range(inst[pg[INST]][1], inst[pg[INST] + 1][1]):
                ig = gens(igen, ibag, zi)
                if SAMPLE not in ig:
                    iglob = ig
                    continue
                g = {**iglob, **ig}
                s = shdr[g[SAMPLE]]
                kr = g.get(KEYRANGE, 127 << 8)
                lo, hi = kr & 0xFF, kr >> 8
                root = g.get(ROOT, s[6]) if g.get(ROOT, 65535) != 65535 else s[6]
                raw = b[smpl[0] + 2 * s[1]: smpl[0] + 2 * s[2]]
                x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0
                loop = (s[3] - s[1], s[4] - s[1]) if s[4] > s[3] + 32 else None
                out.append((lo, hi, root, g.get(FC, 13500), s[5], x, loop))
        return h[0].split(b"\0")[0].decode("latin1"), out
    return None, []


def ladder(x, sr, loop, f_guess, pluck=False):
    if pluck:
        seg = x[int(0.05 * sr):int(0.25 * sr)]
    elif loop:
        lp = x[loop[0]:loop[1]]
        seg = np.tile(lp, int(np.ceil(0.5 * sr / len(lp))))[:int(0.5 * sr)]
    else:
        seg = x[-int(0.4 * sr):]
    seg = seg - seg.mean()
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    b = (f > f_guess / 1.06) & (f < f_guess * 1.06)
    f0 = f[b][np.argmax(X[b])]
    h = []
    for m in range(1, NH + 1):
        w = (f > m * f0 * 0.97) & (f < m * f0 * 1.03)
        h.append(X[w].max() if w.any() and m * f0 < 0.45 * sr else np.nan)
    h = np.array(h)
    return f0, 20 * np.log10(h / h[0] + 1e-30)


def main(argv):
    prog = int(argv[1])
    pluck = "--pluck" in argv
    for name, path in SETS:
        if not path or not os.path.exists(path):
            continue
        pname, zs = zones(path, prog)
        print("%s: %s, %d zones" % (name, pname, len(zs)))
        for lo, hi, root, fc, sr, x, loop in sorted(zs, key=lambda z: z[0]):
            if pluck and len(x) < int(0.25 * sr):
                continue
            f0, L = ladder(x, sr, loop, 440.0 * 2 ** ((root - 69) / 12.0), pluck)
            fch = 8.176 * 2 ** (fc / 1200.0)
            print("  keys %3d-%3d root %3d f0 %6.1f  %s  %s  " % (
                lo, hi, root, f0, "loop" if loop else "tail",
                "fc open " if fc >= 13500 else "fc %5.0f" % fch)
                + " ".join("%+5.1f" % v for v in L[1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
