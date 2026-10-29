#!/usr/bin/env python3
"""What a keyboard sends: its sustain pedal's values, its key-up velocities,
and its aftertouch -- the things a half-pedal can be played with.

    python3 examples/midi_listen.py [--port=USB] [--secs=60]

For the half-pedal work (damper.py): is the pedal continuous (a half-damper
pedal) or a switch, over what range of CC64 does it move, and does the
keyboard send a real release velocity or a constant. Press the pedal SLOWLY
through its travel a few times, then play some slow and some fast key
releases. With no pedal (a key routed to CC64): press keys soft and hard,
release them slow and fast, and push into a held key -- does it send
aftertouch (channel or per-key), a continuous control a held key can move.
Each event is printed as it comes; a summary at the end (or at Ctrl-C). Not
while live is running: the port is live's.
"""
import collections
import sys
import time

import mido


def main(argv):
    sub = next((a.split("=", 1)[1] for a in argv if a.startswith("--port=")), "USB")
    secs = float(next((a.split("=", 1)[1] for a in argv if a.startswith("--secs=")), 60))
    names = [n for n in mido.get_input_names() if sub.lower() in n.lower()]
    if not names:
        print("no input port matching %r in %s" % (sub, mido.get_input_names()))
        return 1
    print("listening on %s for %.0f s: the pedal slowly, then slow and fast key releases" % (names[0], secs))
    cc64, offs, ons, chat, ptat = [], [], [], [], []
    t0 = time.monotonic()
    try:
        with mido.open_input(names[0]) as port:
            while time.monotonic() - t0 < secs:
                for m in port.iter_pending():
                    t = time.monotonic() - t0
                    if m.type == "control_change" and m.control == 64:
                        cc64.append((t, m.value))
                        print("  %6.2f s  CC64 %3d  %s" % (t, m.value, "#" * (m.value // 4)), flush=True)
                    elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
                        v = m.velocity if m.type == "note_off" else None
                        offs.append(v)
                        print("  %6.2f s  key-up %3d  velocity %s" % (t, m.note, "(note_on 0)" if v is None else v),
                              flush=True)
                    elif m.type == "note_on":
                        ons.append(m.velocity)
                        print("  %6.2f s  key-down %3d  velocity %d" % (t, m.note, m.velocity), flush=True)
                    elif m.type == "aftertouch":
                        chat.append(m.value)
                        print("  %6.2f s  channel aftertouch %3d  %s" % (t, m.value, "#" * (m.value // 4)), flush=True)
                    elif m.type == "polytouch":
                        ptat.append(m.value)
                        print("  %6.2f s  key %3d aftertouch %3d  %s" % (t, m.note, m.value, "#" * (m.value // 4)),
                              flush=True)
                time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    print("\nsummary")
    vals = sorted({v for _, v in cc64})
    print("  CC64: %d events, %d distinct values%s" % (len(cc64), len(vals),
          (": %s .. %s" % (vals[0], vals[-1])) if vals else ""))
    if vals:
        inner = [v for v in vals if 0 < v < 127]
        print("  %s" % ("a SWITCH (only 0 and 127)" if not inner else
                        "CONTINUOUS: %d in-between values, %d..%d" % (len(inner), inner[0], inner[-1])))
        # how finely a slow press steps: the largest jump between successive values
        steps = [abs(b - a) for (_, a), (_, b) in zip(cc64, cc64[1:])]
        if steps:
            print("  successive steps: median %d, largest %d" % (sorted(steps)[len(steps) // 2], max(steps)))
    hv = collections.Counter(offs)
    print("  key-ups: %d; velocities %s" % (len(offs), ", ".join("%s x%d" % (k, n) for k, n in hv.most_common(12))))
    real = [v for v in offs if v is not None]
    print("  %s" % ("NO release velocity (note_on 0 or none)" if not real else
                    "a CONSTANT release velocity (%d)" % real[0] if len(set(real)) == 1 else
                    "VARIED release velocity: %d..%d over %d values" % (min(real), max(real), len(set(real)))))
    if ons:
        print("  key-downs: %d, velocity %d..%d" % (len(ons), min(ons), max(ons)))
    for name, xs in (("channel aftertouch", chat), ("per-key aftertouch", ptat)):
        print("  %s: %s" % (name, "none" if not xs else "%d events, %d..%d, %d distinct"
                            % (len(xs), min(xs), max(xs), len(set(xs)))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
