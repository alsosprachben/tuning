#!/usr/bin/env python3
"""Do the native routes (native/slab.cpp's Router) rewrite MIDI as live's do?

    python3 examples/routes_check.py [SETS] [MESSAGES] [--seed=N]

SETS random route sets (default 200) -- one to four routes each, of every
source live.Route has (a CC, the wheel's up, down or both halves, channel
pressure, a key) onto live.CONTROLS' destinations (switches, controllers,
the wheel, pressure, MONO; now and then a name the catalogue lacks), kept or
replacing, on every channel or one, a key latched or held, pushed into or
not -- each fed MESSAGES random messages (default 400): keys, controllers
(the sources' own and others, CC121 among them), the wheel, pressure. live's
side is Live.on_midi with the set installed (set_routes): what it queues
for the audio thread, message for message, against native.Router's feed.
The first difference is reported with its set and message.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import live as L
    import native as N
    sets = int(args[0]) if args else 200
    per = int(args[1]) if len(args) > 1 else 400
    rng = random.Random(int(opt.get("seed", 1)))
    M = mido.Message
    dsts = [c[0] for c in L.CONTROLS] + ["sustain"]
    lv = L.Live(program=0, rate=48000, frames=128, verbose=False, threads=1, gpu=False)
    nmsg = nout = 0
    for s in range(sets):
        routes = []
        for _ in range(rng.randint(1, 4)):
            kind = rng.choice(("cc", "cc", "bend", "pressure", "note", "note"))
            src = (("cc", rng.choice((1, 2, 4, 11, 64, 91))) if kind == "cc"
                   else ("bend", rng.choice(("up", "down", "both"))) if kind == "bend"
                   else ("pressure",) if kind == "pressure" else ("note", rng.choice((36, 41, 53, 60))))
            dst = rng.choice(dsts)
            routes.append(L.Route(src, dst, keep=rng.random() < 0.3,
                                  channel=None if rng.random() < 0.7 else rng.randint(0, 1),
                                  latch=rng.random() < 0.3, press=rng.random() < 0.8))
        lv.set_routes(routes)
        lv.seen.clear()
        nv = N.Router(routes)
        for i in range(per):
            ch = rng.choice((0, 0, 1))
            x = rng.random()
            if x < 0.35:
                note = rng.choice((36, 41, 53, 60, 64, 72))
                m = (M("note_on", channel=ch, note=note, velocity=rng.randint(1, 127)) if rng.random() < 0.55
                     else M("note_off", channel=ch, note=note, velocity=rng.choice((0, 64))))
            elif x < 0.65:
                m = M("control_change", channel=ch,
                      control=rng.choice((1, 2, 4, 11, 64, 91, 7, 10, 66, 121)), value=rng.randint(0, 127))
            elif x < 0.85:
                m = M("pitchwheel", channel=ch, pitch=rng.choice((0, -8192, 8191, rng.randint(-8192, 8191))))
            else:
                m = M("aftertouch", channel=ch, value=rng.randint(0, 127))
            lv.events.clear()
            lv.on_midi(m)
            py = [e[1] for e in lv.events]
            got = nv.feed(m)
            nmsg += 1
            nout += len(py)
            if [p.bytes() for p in py] != [g.bytes() for g in got]:
                print("set %d, message %d: %s" % (s, i, m))
                print("  routes: %s" % "; ".join(r.describe() for r in routes))
                print("  live:   %s" % py)
                print("  native: %s" % got)
                return 1
    print("routes: %d sets, %d messages, %d out, identical" % (sets, nmsg, nout))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
