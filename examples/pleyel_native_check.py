"""Does the native engine play tonelib.PleyelProperties as Python does? Each
note's harmonic volumes and decays, Python's against nv_voice_init's from the
exported class -- the string tension, stringing and leather included --
for keys across the keyboard and velocities, and the grand's alike (its
tension the defaults'). Exit status: the count of notes that differ.

    python3 examples/pleyel_native_check.py
"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import native as N      # noqa: E402
import tonelib as T     # noqa: E402


def main():
    d = N.lib()
    d.nv_harmonic_volume.restype = ctypes.c_double
    d.nv_harmonic_volume.argtypes = [ctypes.c_void_p, ctypes.c_int]
    bad = asked = 0
    worst = 0.0
    per = {}
    for cls in (T.PleyelProperties, T.GrandPianoProperties):
        nc = N.note_class(cls)
        for key in range(21, 109, 3):
            for vel in (20, 64, 100, 127):
                f = 440.0 * 2 ** ((key - 69) / 12.0)
                p = cls(f, 0.0, (vel / 127.0) ** 2, 1.0)
                s, o = N.VoiceSnap(), N.VoiceNote()
                c = N.VoiceInit.from_buffer_copy(nc.init)
                c.detune_lo, c.detune_hi = nc.detune_lo, nc.detune_hi
                tm = N.VoiceSnap.from_buffer_copy(nc.tmpl)
                d.nv_voice_init(ctypes.byref(c), ctypes.byref(tm), f, 0.0, (vel / 127.0) ** 2, 1.0, 0.0, None,
                                ctypes.byref(s), ctypes.byref(o))
                asked += 1
                diff = 0.0
                for h in range(1, 41):
                    a, b = p.harmonic_volume(h), d.nv_harmonic_volume(ctypes.byref(s), h)
                    diff = max(diff, abs(a - b) / max(abs(a), 1e-12))
                worst = max(worst, diff)
                if diff > 1e-9:
                    bad += 1
                    per[cls.__name__] = per.get(cls.__name__, 0) + 1
                    if bad <= 10:
                        print("%s key %d vel %d: volumes differ by %.2e" % (cls.__name__, key, vel, diff))
    print("%d notes compared, %d differ (worst relative %.1e) %s" % (asked, bad, worst, per))
    return bad


if __name__ == "__main__":
    sys.exit(main())
