"""THE PLEYEL's HAMMER, SET FOR ITS PUBLISHED BEHAVIOUR (tonelib.PleyelProperties):
soft felt over leather -- "sweet and velvety piano becoming brighter with
force" (Montal, 1836). No hammer measurements are published, so the felt's
stiffness (an offset to the grand's law), how far a blow squeezes before the
leather (mm) and the leather's stiffness are chosen by what they do, against
the modern grand at the same keys and velocities: the share of each note's
energy above its 2nd harmonic, in dB re the grand's. The aim: a soft touch
clearly darker (-4 to -7 dB), a hard one as bright as the grand's (0 to +1),
in every register; and the contact time, against Chaigne's measured
fortepiano pulses (~4-5 ms at C1, under 1 ms at C7). What it found: the
model's hard layer (hammer_core_*) engages like a wall at any depth and
stiffness -- a forte +100-250% brighter in one velocity step -- so the class
has the soft felt alone for now.

    python3 examples/pleyel_voice.py [grid]     -> the grid, or the class as set
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import tonelib as T     # noqa: E402

KEYS = {'bass': (31, 38), 'mid': (55, 62), 'treble': (79, 86)}
VELS = (40, 80, 115)


def upper(cls, key, vel):
    f = 440 * 2 ** ((key - 69) / 12)
    p = cls(f, 0.0, (vel / 127) ** 2, 1.0)
    v = [p.harmonic_volume(h) ** 2 for h in range(1, 41)]
    return 10 * math.log10(max(sum(v[2:]), 1e-30) / sum(v))


def contact_ms(cls, key, vel):
    import hammer as H
    f = 440 * 2 ** ((key - 69) / 12)
    p = cls(f, 0.0, (vel / 127) ** 2, 1.0)
    fn, mass, K, pp = p._hammer_felt()
    L, Tn, Z = H.string_of(fn, *p._string_scale())
    v0 = p.hammer_speed_lo * (p.hammer_speed_hi / p.hammer_speed_lo) ** ((vel - 1) / 126.0)
    F, dt = H.contact(fn, v0, mass, K, pp, p.strike_point, L, Z, alpha=p.hammer_alpha, tau=10 ** p.hammer_log_tau,
                      core_x=p._core_mm(fn) * 1e-3, core_K=10 ** p.hammer_core_logk)
    on = [i for i, x in enumerate(F) if x > 0]
    return (on[-1] - on[0] + 1) * dt * 1000 if on else 0.0


def table(cls, ref):
    out = []
    for r, ks in KEYS.items():
        for v in VELS:
            out.append(sum(upper(cls, k, v) - upper(ref, k, v) for k in ks) / len(ks))
    return out


def main(argv):
    ref = T.GrandPianoProperties
    head = "  ".join("%s%-3d" % (r[0], v) for r in KEYS for v in VELS)
    if len(argv) > 1 and argv[1] == 'grid':
        print("dlogk core_mm core_logk | " + head)
        for dk in (-0.8, -0.5, -0.3):
            for cm in (0.25, 0.5, 0.8):
                for cl in (15.0, 15.7, 16.3):
                    c = type('P', (T.PleyelProperties,), dict(hammer_logk=ref.hammer_logk + dk, hammer_core_mm=cm,
                                                                hammer_core_edge_mm=0.0, hammer_core_logk=cl))
                    print("%+5.1f %6.2f %8.1f  | " % (dk, cm, cl) + "  ".join("%+5.1f" % x for x in table(c, ref)),
                          flush=True)
        return 0
    c = T.PleyelProperties
    print("the class: " + head)
    print("           " + "  ".join("%+5.1f" % x for x in table(c, ref)))
    for k in (24, 60, 96):
        print("contact at %d, v80: %.2f ms (the grand's %.2f)" % (k, contact_ms(c, k, 80), contact_ms(ref, k, 80)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
