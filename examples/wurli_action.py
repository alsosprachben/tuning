#!/usr/bin/env python3
"""THE 200A'S ACTION, MODELLED (Ben, 2026-11-22: "model it, and try to find any
recording that can be used to validate"): the knock heard in the room beside
the speaker -- tonelib.WurlitzerProperties.strike_noise_db -- from the
instrument's construction, no recording (Gwazda's Mech takes, the first
source, are no longer read: licences.md L7).

    python3 examples/wurli_action.py            print the table
    python3 examples/wurli_action.py --write    write it into tonelib.py
    python3 examples/wurli_action.py --ab DIR   A/B renders at three levels

THREE PARTS, each a force into the case and the case radiating it:
  KEY BOTTOMING   the wooden key stopping on its felt punching: a half-sine
                  force of contact time KEY_TAU -- flat to ~1/(2 tau), then
                  falling ~12 dB an octave (the pulse's spectral envelope).
  HAMMER ON REED  a small hard felt on a steel reed, the impact carried into
                  the reed bar: contact HAMMER_TAU, HAMMER_DB under the key's
                  (the bar is heavy; little of it reaches the shell).
  THE CASE        a thin moulded plastic shell: below its first panel modes
                  (CASE_HZ) it barely radiates -- a 2nd-order rise with a mild
                  peak (CASE_Q) -- and its damping (loss factor CASE_ETA)
                  sets the fall, 27.3 f eta dB/s at the knock's centre.
Heard in the ROOM, beside the lid speakers: the renderer sends the knock
through the voice's cabinet, so the table undoes the cabinet's response
(cabinet.WurlitzerInternal.gain), at most UNDO_MAX_DB.
LEVEL_DB, the loudest band re the note, is the one number physics does not
give: set by Ben's ear (--ab renders it at three levels).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

KEY_TAU = 3.0e-3
HAMMER_TAU = 0.8e-3
HAMMER_DB = -8.0
CASE_HZ = 120.0
CASE_Q = 1.5
CASE_ETA = 0.04
UNDO_MAX_DB = 24.0
LEVEL_DB = -26.0       # Ben, 2026-11-22: "Go with the low action" (of -26/-20/-14)
CENTRES = (45, 57, 71, 90, 113, 143, 180, 226, 285, 359, 453, 570, 718, 905, 1140, 1437, 1810,
           2281, 2874, 3620, 4561, 5747, 7241, 9123, 11494)


def pulse_db(f, tau):
    """a half-sine pulse's spectral envelope: flat, then 12 dB an octave"""
    x = 2.0 * f * tau
    return -10.0 * math.log10(1.0 + x ** 4)


def case_db(f):
    """the shell's radiation: a 2nd-order high-pass at CASE_HZ, peak CASE_Q"""
    r = f / CASE_HZ
    h = r * r / math.sqrt((1 - r * r) ** 2 + (r / CASE_Q) ** 2)
    return 20.0 * math.log10(h)


def room_db(f):
    k = 10 ** (pulse_db(f, KEY_TAU) / 10)
    h = 10 ** ((pulse_db(f, HAMMER_TAU) + HAMMER_DB) / 10)
    return 10 * math.log10(k + h) + case_db(f)


def table(level_db=LEVEL_DB):
    import cabinet as C
    cab = C.WurlitzerInternal()
    room = [room_db(f) for f in CENTRES]
    top = max(room)
    out = []
    for f, r in zip(CENTRES, room):
        undo = min(UNDO_MAX_DB, -20 * math.log10(max(float(cab.gain(f)), 1e-6)))
        out.append((f, round(r - top + level_db + undo, 1)))
    return tuple(out)


def decay_dbs():
    """the knock's fall at its centre (the loudest band in the room)"""
    fc = max(CENTRES, key=room_db)
    return round(27.3 * fc * CASE_ETA, 1)


def write(tab, dbs):
    import re
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    a = s.index("class WurlitzerProperties(")
    b = s.index("\nclass ", a + 10)
    body = s[a:b]
    body = re.sub(r"^    strike_noise_db = .*\n", "    strike_noise_db = %s\n" % (tab,), body, count=1, flags=re.M)
    body = re.sub(r"^    strike_noise_dbs = .*\n", "    strike_noise_dbs = %s\n" % dbs, body, count=1, flags=re.M)
    open(p, "w").write(s[:a] + body + s[b:])


def ab(out):
    """a phrase on the Wurlitzer (cabinet in, no tremolo) without the knock,
    then at LEVEL_DB - 6, LEVEL_DB and LEVEL_DB + 6"""
    import mido
    import numpy as np
    import blockrender as B
    import tonelib as T
    from scipy.io import wavfile
    cls = T.WurlitzerProperties
    m = mido.MidiFile(type=0, ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.Message("program_change", channel=0, program=5, time=0))
    seq = [(48, 70), (55, 80), (60, 90), (64, 100), (67, 110), (72, 120), (76, 100), (79, 80)]
    for n, v in seq:
        t.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=0))
        t.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=360))
    for n in (48, 55, 64, 70):
        t.append(mido.Message("note_on", channel=0, note=n, velocity=105, time=0))
    t.append(mido.Message("note_off", channel=0, note=48, velocity=0, time=1440))
    for n in (55, 64, 70):
        t.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    os.makedirs(out, exist_ok=True)
    for tag, lv in (("none", None), ("low", LEVEL_DB - 6), ("mid", LEVEL_DB), ("high", LEVEL_DB + 6)):
        cls.strike_noise_db = table(lv) if lv is not None else ()
        cls.strike_noise_dbs = decay_dbs()
        L, R = B.render(m)[:2]
        y = np.stack([L, R], 1)
        y = y / (np.abs(y).max() + 1e-12) * 0.7
        w = os.path.join(out, "wurli_action_%s.wav" % tag)
        wavfile.write(w, B.SR, (y * 32767).astype(np.int16))
        os.system("lame --quiet -b 256 '%s' '%s' && rm '%s'" % (w, w[:-4] + ".mp3", w))
        print("  written", w[:-4] + ".mp3")


if __name__ == "__main__":
    tab, dbs = table(), decay_dbs()
    print("strike_noise_db = %s\nstrike_noise_dbs = %s" % (tab, dbs))
    print("in the room:", " ".join("%d:%.0f" % (f, room_db(f) - max(room_db(c) for c in CENTRES)) for f in CENTRES))
    if "--write" in sys.argv:
        write(tab, dbs)
    if "--ab" in sys.argv:
        os.environ.setdefault("TUNING_MOD_VIBRATO", "0")
        ab(sys.argv[sys.argv.index("--ab") + 1])
