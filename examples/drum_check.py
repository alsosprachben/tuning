#!/usr/bin/env python3
"""Is the native kit drum (native/voice.c, VoiceSnap.kind 1) bit-identical to
the Python it ports?

    python3 examples/drum_check.py [NOTES]

For NOTES random strokes (default 400) of the Standard set's drums the
native voice plays (native.kit_drum: the kick, the toms, the snares and the
side stick) -- each at its key's
pitch, now and then retuned as a file's drum setup retunes it, across the
velocities and the kit's seats -- the constructor (nv_voice_init: the
voice, seated in the kit or not, what the note setup reads, the global
random stream after it) and
every function native/voice.c ports is
asked what its Python method is asked: each partial's mode ratio (the
measured modes, the stick's click), series and volume (a snare's roll-off
and band trim), decay and its two stages (aftersound_partial), a snare's
jitter, and blockrender's string_partial and
partial_decay, the unison, radiation, the head's shadow, chiff, bloom and
vibrato. The answers compared with ==; any difference printed; the exit
status is the count.
"""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import blockrender as B         # noqa: E402
import native as N              # noqa: E402
import percussion_map as PCM    # noqa: E402


def main(argv):
    n_notes = int(argv[1]) if len(argv) > 1 else 400
    d = N.lib()
    D4 = ctypes.c_double * 4
    D40 = ctypes.c_double * 80
    rng = random.Random(17)
    bad, asked = [], 0

    def same(what, a, b):
        nonlocal asked
        asked += 1
        if a != b and not (a != a and b != b):
            bad.append((what, a, b))

    keys = [k for k in range(128)
            if PCM.percussion_for_note(k, 0) and N.kit_drum(PCM.percussion_for_note(k, 0)[1])]
    for k in range(n_notes):
        key = keys[k % len(keys)]
        name, cls, f0, pan = PCM.percussion_for_note(key, 0)
        if rng.random() < 0.3:
            f0 *= 2.0 ** (rng.randint(-24, 24) / 12.0)        # a drum setup's pitch
        av = (rng.randint(1, 127) / 127.0) ** 2
        p = cls(f0, pan if rng.random() < 0.7 else rng.uniform(-1, 1), av, rng.uniform(0.2, 1.0))
        s = N.snapshot(p)
        if s is None:
            bad.append((name, "not supported"))
            continue
        sp = ctypes.byref(s)
        for m in range(1, p.max_harmonic + 2):
            same(('mode_ratio', key, m), p.mode_ratio(m), d.nv_mode_ratio(sp, m))
            same(('series', key, m), p.series_volume(m), d.nv_series_volume(sp, m))
            same(('volume', key, m), p.harmonic_volume(m), d.nv_harmonic_volume(sp, m))
            dec = p.harmonic_decay(m)
            same(('decay', key, m), dec, d.nv_harmonic_decay(sp, m))
            if getattr(p, 'jitter_by_partial', False):
                same(('jitter', key, m), p.partial_jitter(m), d.nv_partial_jitter(sp, m))
            if getattr(p, 'stroke_scatter', False):
                same(('scatter', key, m), p.stroke_scatter_db(m), d.nv_stroke_scatter_db(sp, m))
            out = D40()
            n = d.nv_unison_voices(sp, f0, m, dec, out)
            same(('unison', key, m), [tuple(float(x) for x in v) for v in p.unison_voices(f0, m, dec)],
                 [tuple(out[5 * i:5 * i + 5]) for i in range(n)])
            o2 = D4()
            got = d.nv_string_partial(sp, f0, 1.0, m, 0.0, o2)
            py = B.string_partial(p, f0, 1.0, m, 0.0)
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
                same(('bloom gain', key, m), p.bloom_gain_for(hf), d.nv_bloom_gain_for(sp, hf))
        for rate in (0.0, 3.5, 40.0, 300.0):
            o2 = D4()
            d.nv_aftersound(sp, f0, rate, o2)
            same(('aftersound', key, rate), tuple(p.aftersound(f0, rate)), (o2[0], o2[1]))
        for idx in range(3):
            o3 = D4()
            got = d.nv_voice_vibrato(sp, f0, idx, o3)
            vv = p.voice_vibrato(f0, idx)
            same(('vibrato', key, idx), tuple(vv) if vv else None, (o3[0], o3[1], o3[2]) if got else None)
    # THE CONSTRUCTOR (nv_voice_init): each class from the same arguments and
    # the same global random stream as Python's, its VoiceSnap and what the
    # note setup reads, and the stream after it
    import random as R_
    import tonelib as T
    inits = 0
    for k in range(n_notes):
        key = keys[k % len(keys)]
        name, cls, f0, pan = PCM.percussion_for_note(key, 0)
        args = (f0 * (2.0 ** (rng.randint(-12, 12) / 12.0) if rng.random() < 0.3 else 1.0),
                rng.choice((pan, rng.uniform(-1, 1))), (rng.randint(1, 127) / 127.0) ** 2,
                rng.uniform(0.2, 1.0), rng.choice((0.0, 0.0, rng.uniform(-6, 6))))
        seat = rng.choice((0.0, pan, rng.uniform(-1, 1)))
        R_.seed(rng.getrandbits(64))
        st = N.random_state()
        p = cls(*args)
        after = R_.getstate()[1]
        if seat:
            # its seat in the kit, as blockrender places it
            import math
            p.seat_x = p.listener_distance * math.tan(T.stage_angle(seat))
            p.place()
        got = N.voice(cls, *args, state=st, seat=seat)
        if got is None:
            bad.append((name, "constructor not supported"))
            continue
        inits += 1
        sp = N.snapshot(p)
        for f, _ in N.VoiceSnap._fields_:
            a, b = getattr(sp, f), getattr(got[0], f)
            if not isinstance(a, (int, float)):
                flat = lambda x: [list(r) if not isinstance(r, (int, float)) else r for r in x]  # noqa: E731
                a, b = flat(a), flat(b)
            same(('init', name, f), a, b)
        o = got[1]
        for f, py in (('pitch_jitter', p.pitch_jitter), ('attack_jitter', p.attack_jitter),
                      ('pan_angle', p.pan_angle), ('left_incidence', p.left_incidence),
                      ('right_incidence', p.right_incidence), ('left_hrtf_delay', p.left_hrtf_delay),
                      ('right_hrtf_delay', p.right_hrtf_delay),
                      ('inharmonicity_coefficient', p.inharmonicity_coefficient),
                      ('B', p.inharmonicity_coefficient), ('tension_bend', p.tension_bend),
                      ('attack_time', p.attack_time if p.attack_time is not None else p.chiff_max_valve_time),
                      ('chiff_volume', p.chiff_volume),
                      ('sustain_jitter', p.sustain_jitter)):
            same(('init', name, f), py, getattr(o, f))
        same(('init', name, 'stream'), list(after[:624]) + [after[624]], list(st.mt) + [st.i])
    for b in bad[:12]:
        print("  DIFFERS", b)
    print("drum voice: %d strokes of %s and %d constructions, %d answers, %s"
          % (n_notes, ", ".join(PCM.percussion_for_note(k, 0)[0] for k in keys), inits, asked,
             "identical" if not bad else "%d differ" % len(bad)))
    return len(bad)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
