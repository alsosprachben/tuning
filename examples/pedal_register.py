#!/usr/bin/env python3
"""Does the free-string register follow the tuning, and the pedal?

    python3 examples/pedal_register.py [identity|equation|tuning|pedal] ...

Four checks of register.py, each read from the real pipeline -- prepare() with
TUNING_REGISTER=1, register.expand wrapped to see what it was handed:

  identity   The register's strings ARE the rendered strings. For seven tuners
             and an MTS bulk dump (examples/tuning_sysex.py --mts, rendered
             as gm2), every free-string mode's frequency equals the emitted
             partial of the same key, string and harmonic, to float rounding.
  equation   The response formula against a direct integration of the damped
             resonator at 8x the sample rate, offsets 0 to 50 Hz, with and
             without the tension glide.
  tuning     What a temperament does to the halo: the octave, fifth and major
             third above C4, under each tuner -- the real stretched partials
             that meet, their offset, the free part's level that offset gives
             (re a coincident one), and the beat it makes.
  pedal      A pedalled chord rings on in the register after its keys are let
             go and stops when the pedal comes up; the undamped top answers with
             the pedal up; a silently held key answers; nothing steps at a
             driver's damper.
"""
import contextlib
import io
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ['TUNING_REGISTER'] = '1'
import blockrender as B                       # noqa: E402
import register as R                          # noqa: E402

TUNERS = ('even', 'just', 'meantone', 'werckmeister', 'hybrid440', 'hybridmean', 'stretch')
FAILS = []


def check(name, ok, detail=""):
    print("   %-62s %s%s" % (name, "ok" if ok else "FAIL", detail))
    if not ok:
        FAILS.append(name)


def midi(path, events, tpb=480):
    """events: (seconds, msg-type, kwargs), written at 120 bpm."""
    import mido
    m = mido.MidiFile(ticks_per_beat=tpb)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    t.append(mido.Message('program_change', program=0, time=0))
    now = 0
    for sec, kind, kw in sorted(events, key=lambda e: e[0]):
        tick = int(round(sec * 2 * tpb))
        t.append(mido.Message(kind, time=tick - now, **kw))
        now = tick
    m.save(path)
    return path


def captured(path, tuner):
    """prepare() with the register on; what register.expand was handed."""
    got = {}
    orig = R.expand

    def spy(A, channels, sr, blk, cols, meta=None):
        got['channels'] = channels
        got['n0'] = len(A['om'])
        m = [] if meta is None else meta
        n = orig(A, channels, sr, blk, cols, m)
        got['meta'] = m
        return n
    R.expand = spy
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            got['table'] = B.prepare(path, tuner)
    finally:
        R.expand = orig
    return got


# ------------------------------------------------------------------ identity

def identity():
    print("identity: the register's strings are the rendered strings")
    d = tempfile.mkdtemp(prefix="register_")
    keys = (28, 41, 48, 55, 60, 67, 72, 79, 84, 96, 103)
    ev = []
    for i, k in enumerate(keys):
        ev += [(0.5 * i, 'note_on', dict(note=k, velocity=80)),
               (0.5 * i + 0.3, 'note_off', dict(note=k))]
    src = midi(os.path.join(d, "keys.mid"), ev)
    cases = [(t, src, t) for t in TUNERS]
    mts = os.path.join(d, "keys_mts.mid")
    subprocess.run([sys.executable, os.path.join(HERE, "examples", "tuning_sysex.py"), "--mts",
                    "--tuner", "stretch", src, mts], check=True, stdout=subprocess.DEVNULL)
    cases.append(("MTS (stretch, as gm2)", mts, "gm2"))
    for label, path, tuner in cases:
        g = captured(path, tuner)
        (ch, C), = g['channels'].items()
        S = C.S
        worst, missing, modes = 0.0, 0, 0
        for s in C.strikes:
            om = np.sort(s['drv']['om'])                  # its direct sound, as emitted
            mine = S.W[S.key == s['key']] / B.SR
            modes += len(mine)
            j = np.clip(np.searchsorted(om, mine), 1, len(om) - 1)
            near = np.where(np.abs(om[j] - mine) < np.abs(om[j - 1] - mine), om[j], om[j - 1])
            rel = np.abs(near - mine) / mine
            missing += int((rel > 1e-12).sum())
            worst = max(worst, float(rel.max()))
        check("%-24s %4d modes of %d keys" % (label, modes, len(C.strikes)),
              missing == 0, "  (worst %.1e relative; %d without their partial)" % (worst, missing))


# ------------------------------------------------------------------ equation

def equation():
    print("equation: the response, against a direct integration")
    sr8 = 44100 * 8

    def ode(c, Wi, bi, Wm, am, tb, tau, cut, T):
        n = int(T * sr8); n += n % 2; dt = T / n
        t = np.linspace(0, T, n + 1)
        v = c * np.exp(1j * (Wi - Wm) * t + 1j * R.glide_phase(Wi, tb, tau, cut, t) + (am - bi) * t)
        y = (v[0] + v[-1] + 4 * v[1:-1:2].sum() + 2 * v[2:-1:2].sum()) * dt / 3
        return y * np.exp((1j * Wm - am) * T)
    fi, bi, am, T = 440.0, 0.5, 0.2, 2.5
    Wi = 2 * np.pi * fi
    for tb in (0.0, 0.008):
        worst, top = 0.0, 0.0
        for df in (0.0, 0.032, 0.064, 0.32, 1.0, 3.5, 10.0, 50.0):
            Wm = 2 * np.pi * (fi + df)
            fr, fo = R.free_part(1.0, Wi, bi, Wm, am, tb, 0.28, 1.8)
            model = fr * np.exp((1j * Wm - am) * T) + fo * np.exp(
                1j * (Wi * T + R.glide_phase(Wi, tb, 0.28, 1.8, T)) - bi * T)
            ref = ode(1.0, Wi, bi, Wm, am, tb, 0.28, 1.8, T)
            top = max(top, abs(ref))
            worst = max(worst, abs(model - ref))
        check("%s, offsets 0-50 Hz" % ("no glide" if not tb else "the glide (14 c at full strike)"),
              worst < 1e-5 * top, "  (worst error %.1e of the coincident response)" % (worst / top))


# ------------------------------------------------------------------ tuning

def tuning():
    print("tuning: what each temperament does to the halo above C4")
    d = tempfile.mkdtemp(prefix="register_")
    src = midi(os.path.join(d, "c4.mid"), [(0.0, 'note_on', dict(note=60, velocity=90)),
                                           (1.0, 'note_off', dict(note=60))])
    pairs = (("octave C5", 72, 2, 1), ("fifth G4", 67, 3, 2), ("third E4", 64, 5, 4))
    print("   %-13s %-11s %10s %10s %9s %10s" % ("tuner", "interval", "offset Hz", "beat /s",
                                                 "free dB", "(re unison)"))
    res = {}
    for t in TUNERS:
        g = captured(src, t)
        (ch, C), = g['channels'].items()
        S = C.S
        for name, key, hd, hr in pairs:
            # the struck C4's partial hd (its main string) and the free key's hr
            fd = S.f[(S.key == 60) & (S.harm == hd) & (S.string == 0)][0]
            fr = S.f[(S.key == key) & (S.harm == hr) & (S.string == 0)][0]
            am = S.alpha[(S.key == key) & (S.harm == hr) & (S.string == 0)][0]
            Wi, Wm = 2 * np.pi * fd, 2 * np.pi * fr
            free, _ = R.free_part(1.0, Wi, 1.5, Wm, am)
            unison, _ = R.free_part(1.0, Wm, 1.5, Wm, am)
            lv = 20 * math.log10(abs(free) / abs(unison))
            res[(t, name)] = lv
            print("   %-13s %-11s %+10.3f %10.3f %9.1f" % (t, name, fd - fr, abs(fd - fr), lv))
    check("a just fifth rings more than an equal one",
          res[('just', 'fifth G4')] > res[('even', 'fifth G4')],
          "  (%.1f dB against %.1f)" % (res[('just', 'fifth G4')], res[('even', 'fifth G4')]))
    check("a just third rings more than an equal one",
          res[('just', 'third E4')] > res[('even', 'third E4')],
          "  (%.1f dB against %.1f)" % (res[('just', 'third E4')], res[('even', 'third E4')]))


# ------------------------------------------------------------------ the pedal

def render(path, tuner, register=True):
    out = path[:-4] + ("_reg" if register else "_dry") + ".wav"
    env = dict(os.environ, TUNING_REGISTER='1' if register else '0', TUNING_REFLECT='0')
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), path, out, tuner],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    import wave
    w = wave.open(out)
    a = np.frombuffer(w.readframes(w.getnframes()), {2: '<i2', 4: '<i4'}[w.getsampwidth()])
    a = a.astype(float).reshape(-1, w.getnchannels()).mean(1)
    return a / (32768.0 if w.getsampwidth() == 2 else 2147483648.0), w.getframerate()


def rms_db(x):
    return 10 * math.log10(float(np.mean(x ** 2)) + 1e-30)


def pedal():
    print("pedal: when the strings are free, and what they do")
    d = tempfile.mkdtemp(prefix="register_")
    # a pedalled chord: keys up at 1.5 s, pedal up at 4.0 s
    chord = (48, 52, 55, 60)
    ev = [(0.0, 'control_change', dict(control=64, value=127))]
    ev += [(0.5, 'note_on', dict(note=n, velocity=90)) for n in chord]
    ev += [(1.5, 'note_off', dict(note=n)) for n in chord]
    ev += [(4.0, 'control_change', dict(control=64, value=0)), (5.5, 'note_on', dict(note=21, velocity=1)),
           (5.51, 'note_off', dict(note=21))]
    f = midi(os.path.join(d, "chord.mid"), ev)
    x, sr = render(f, "hybrid440", True)
    y, _ = render(f, "hybrid440", False)
    n = min(len(x), len(y)); reg = x[:n] - y[:n]
    w = lambda a, b: slice(int(a * sr), int(b * sr))          # noqa: E731
    held = rms_db(reg[w(2.0, 3.9)])
    after = rms_db(reg[w(4.3, 5.4)])
    check("a pedalled chord rings on in the register after its keys are up",
          held > -90, "  (%.1f dB, 2.0-3.9 s)" % held)
    check("...and stops when the pedal comes up", after < held - 60,
          "  (%.1f dB after, %.1f before)" % (after, held))
    early, late = rms_db(reg[w(0.6, 1.4)]) - rms_db(y[w(0.6, 1.4)]), held - rms_db(y[w(2.0, 3.9)])
    check("...and the halo outlasts the struck strings (the longer decay)",
          late > early, "  (register re dry %.1f dB early, %.1f dB late)" % (early, late))
    # the top has no dampers: a short C5, pedal up, and only keys >= damper_top answer
    f2 = midi(os.path.join(d, "top.mid"), [(0.2, 'note_on', dict(note=72, velocity=100)),
                                           (0.5, 'note_off', dict(note=72))])
    # the MECHANISM, so the coupling is raised for it: at the ear's level a C5
    # reaches the undamped strings only through partials under the floor
    import patch_map
    pc = patch_map.property_class_for_note(0, 72)
    was = pc.register_gain
    pc.register_gain = was * 100.0
    try:
        g = captured(f2, "hybrid440")
    finally:
        pc.register_gain = was
    (ch, C), = g['channels'].items()
    top = C.top
    keys = {int(C.S.key[m[3]]) for m in g['meta'] if m[1] == 'free'}
    check("with the pedal up only the undamped top answers",
          keys and min(keys) >= top, "  (keys %s; dampers stop at %d)" % (sorted(keys)[:6], top))
    # a silently held key: C4 held (velocity 1) through a staccato C3, pedal up
    f3 = midi(os.path.join(d, "held.mid"), [(0.1, 'note_on', dict(note=60, velocity=1)),
                                            (0.6, 'note_on', dict(note=48, velocity=100)),
                                            (0.8, 'note_off', dict(note=48)),
                                            (3.5, 'note_off', dict(note=60))])
    g = captured(f3, "hybrid440")
    (ch, C), = g['channels'].items()
    keys = {int(C.S.key[m[3]]) for m in g['meta'] if m[1] == 'free'}
    check("a silently held key answers, its damper up", 60 in keys and 64 not in keys,
          "  (C4 %s, E4 %s)" % ("rings" if 60 in keys else "silent", "rings" if 64 in keys else "silent"))
    x, sr = render(f3, "hybrid440", True)
    y, _ = render(f3, "hybrid440", False)
    n = min(len(x), len(y)); reg = x[:n] - y[:n]
    # the C3's damper: key up at 0.8 s, release 0.12 s; no step in the register
    lv = [rms_db(reg[int(t * sr):int((t + 0.02) * sr)]) for t in np.arange(0.70, 1.10, 0.02)]
    step = max(abs(a - b) for a, b in zip(lv, lv[1:]))
    check("nothing steps where the driver's damper falls", step < 3.0,
          "  (largest change between 20 ms windows %.1f dB)" % step)


def main(argv):
    which = argv[1:] or ['identity', 'equation', 'tuning', 'pedal']
    for w in which:
        globals()[w]()
    print("\n  %s" % ("all passed" if not FAILS else "FAILED: " + ", ".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
