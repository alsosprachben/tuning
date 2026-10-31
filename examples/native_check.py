#!/usr/bin/env python3
"""Is the native voice (native/voice.c) bit-identical to the Python it ports?

    python3 examples/native_check.py [NOTES]

For NOTES random grand piano notes (default 300) across the keyboard and the
velocities, every function native/voice.c ports is asked what its Python
method is asked -- each harmonic's series, volume and decay, the unison
strings, the aftersound, radiation, the head's shadow, chiff, bloom,
vibrato, and blockrender's string_partial / partial_decay / unison_partial
-- and the answers compared with ==. Also CPython's Random(seed) streams.
Any difference is printed; the exit status is the count.
"""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import blockrender as B     # noqa: E402
import native as N          # noqa: E402
import patch_map as PM      # noqa: E402
import tonelib as T         # noqa: E402


def main(argv):
    n_notes = int(argv[1]) if len(argv) > 1 else 300
    d = N.lib()
    if d is None:
        print("native: no library")
        return 1
    D4 = ctypes.c_double * 4
    D20 = ctypes.c_double * 20
    rng = random.Random(11)
    bad, asked = [], 0

    def same(what, a, b):
        nonlocal asked
        asked += 1
        if a != b and not (a != a and b != b):
            bad.append((what, a, b))

    # CPython's random streams
    for seed in [0, 1, 7, 2 ** 32 - 1, 2 ** 32, 2 ** 40 + 5, 123456789012, -42]:
        out = (ctypes.c_double * 8)()
        d.nv_random_check(seed, 8, out)
        r = random.Random(seed)
        same(('random', seed), [r.random() for _ in range(8)], list(out))

    pc = PM.PROGRAM_CLASS[0]
    skipped = 0
    for k in range(n_notes):
        key = rng.randint(21, 108)
        f0 = 440.0 * 2.0 ** ((key - 69) / 12.0) * (1.0 + rng.uniform(-0.002, 0.002))
        av = (rng.randint(1, 127) / 127.0) ** 2
        p = pc(f0, rng.uniform(-1, 1), av, rng.uniform(0.2, 1.0))
        T.soft_pedal_down = (k % 9 == 0)
        s = N.snapshot(p)
        if s is None:
            skipped += 1
            continue
        sp = ctypes.byref(s)
        B_ = p.inharmonicity_coefficient
        for m in range(1, p.max_harmonic + 2):
            same(('series', key, m), p.series_volume(m), d.nv_series_volume(sp, m))
            same(('volume', key, m), p.harmonic_volume(m), d.nv_harmonic_volume(sp, m))
            dec = p.harmonic_decay(m)
            same(('decay', key, m), dec, d.nv_harmonic_decay(sp, m))
            out = D20()
            n = d.nv_unison_voices(sp, f0, m, dec, out)
            same(('unison', key, m), [tuple(float(x) for x in v) for v in p.unison_voices(f0, m, dec)],
                 [tuple(out[5 * i:5 * i + 5]) for i in range(n)])
            o2 = D4()
            got = d.nv_string_partial(sp, f0, 1.0, m, B_, o2)
            py = B.string_partial(p, f0, 1.0, m, B_)
            same(('string_partial', key, m), py, (o2[0], o2[1]) if got else None)
            o4 = D4()
            d.nv_partial_decay(sp, f0, m, o4)
            same(('partial_decay', key, m), tuple(B.partial_decay(p, f0, m)), tuple(o4))
            if py:
                hf = py[1]
                same(('radiation', key, m), p.radiation_gain(hf), d.nv_radiation_gain(sp, hf, 0.0, 0))
                for inc in (p.left_incidence, p.right_incidence, 0.3, 2.9):
                    same(('hrtf', key, m, inc), p.hrtf_gain(hf, inc), d.nv_hrtf_gain(sp, hf, inc))
                same(('chiff', key, m), p.chiff_harmonic_gain(py[0]), d.nv_chiff_harmonic_gain(sp, py[0]))
                same(('bloom', key, m), p.bloom_delay_for(hf), d.nv_bloom_delay_for(sp, hf))
                for off, dr, ud in ((0.13, 0.0, dec), (-0.3, 0.0012, dec * 0.5), (0.0, -0.0008, 0.0)):
                    o5 = D4()
                    d.nv_unison_partial(hf, off, dr, ud, o5)
                    same(('unison_partial', key, m), tuple(B.unison_partial(hf, off, dr, ud)), (o5[0], o5[1]))
        for rate in (0.0, 3.5, 40.0):
            o2 = D4()
            d.nv_aftersound(sp, f0, rate, o2)
            same(('aftersound', key, rate), tuple(p.aftersound(f0, rate)), (o2[0], o2[1]))
        for idx in range(4):
            o3 = D4()
            got = d.nv_voice_vibrato(sp, f0, idx, o3)
            vv = p.voice_vibrato(f0, idx)
            same(('vibrato', key, idx), tuple(vv) if vv else None, (o3[0], o3[1], o3[2]) if got else None)
    T.soft_pedal_down = False
    for what, a, b in bad[:20]:
        print("  DIFF %s: python %r, native %r" % (what, a, b))
    print("native voice: %d comparisons over %d piano notes (%d unsupported), %d differ"
          % (asked, n_notes - skipped, skipped, len(bad)))
    return len(bad)


if __name__ == "__main__":
    sys.exit(min(main(sys.argv), 255))
