#!/usr/bin/env python3
"""Piano files that work the bend passes: OUT_DIR/bendNN.mid

    python3 examples/bend_files.py OUT_DIR [N] [--seed=S]

N random General MIDI piano files (default 12, programs 0-3), 12-20
seconds each, two or three channels, written for examples/nvrender_check.py
to render both ways. What native/bend.cpp has to get right, all of it in
the mix: a channel TUNED before it plays -- a static wheel, a bend range,
RPN fine and coarse tuning, data increment and decrement -- and then moved
while it sounds (a piano takes none of that: it cannot be bent); GM System
On and GS Reset putting the tuning back, mid-file too (each channel's
program sent again after it, or left at 0: a piano class changed
mid-channel); CC121; RPNs chosen
and left (the null) and NRPN-free; the channel FADER, CC7 and CC11 swells
and fades under held notes, and a channel that only sets its level between
notes; one channel STAMPED as mt32mux writes them, a CC7 before every note;
the sustain pedal throughout.
"""
import os
import random
import sys


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    import mido
    out = args[0]
    n = int(args[1]) if len(args) > 1 else 12
    rng = random.Random(int(opt.get("seed", 1)))
    os.makedirs(out, exist_ok=True)
    GM_ON = [0x7E, 0x7F, 0x09, 0x01]
    GS_RESET = [0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41]
    for k in range(n):
        tpb = 480
        mid = mido.MidiFile(ticks_per_beat=tpb)
        tr = mido.MidiTrack()
        mid.tracks.append(tr)
        ev = []                     # (tick, order, message)
        o = [0]

        def at(tick, m):
            o[0] += 1
            ev.append((int(tick), o[0], m))
        sec = lambda s: int(s * tpb * 2)            # 120 bpm: a beat a half second
        length = rng.uniform(12.0, 20.0)
        chans = rng.sample(range(9), rng.randint(2, 3))
        if rng.random() < 0.3:
            at(0, mido.Message("sysex", data=rng.choice((GM_ON, GS_RESET))))
        stamped = rng.choice(chans) if rng.random() < 0.3 else None
        progs = {c: rng.randint(0, 3) for c in chans}
        for c in chans:
            at(0, mido.Message("program_change", channel=c, program=progs[c]))
            # A TUNING, before the first note
            t0 = rng.uniform(0.0, 0.3)
            x = rng.random()
            if x < 0.3:
                at(sec(t0) - 2, mido.Message("pitchwheel", channel=c, pitch=rng.randint(-2000, 2000)))
            if x < 0.55 or rng.random() < 0.3:
                # RPN 0/0, 0/1, 0/2 (and sometimes a step), then the null
                for sel, vals in (((0, 0), (rng.choice((1, 2, 7, 12)), rng.randint(0, 99))),
                                  ((0, 1), (rng.randint(40, 88), rng.randint(0, 127))),
                                  ((0, 2), (rng.randint(60, 68), 0))):
                    if rng.random() < 0.6:
                        at(sec(t0) - 1, mido.Message("control_change", channel=c, control=101, value=sel[0]))
                        at(sec(t0) - 1, mido.Message("control_change", channel=c, control=100, value=sel[1]))
                        at(sec(t0) - 1, mido.Message("control_change", channel=c, control=6, value=vals[0]))
                        if rng.random() < 0.5:
                            at(sec(t0) - 1, mido.Message("control_change", channel=c, control=38, value=vals[1]))
                        for _ in range(rng.choice((0, 0, 1, 3))):
                            at(sec(t0) - 1, mido.Message("control_change", channel=c,
                                                         control=rng.choice((96, 97)), value=0))
                if rng.random() < 0.6:
                    at(sec(t0) - 1, mido.Message("control_change", channel=c, control=101, value=127))
                    at(sec(t0) - 1, mido.Message("control_change", channel=c, control=100, value=127))
            if rng.random() < 0.4:
                at(sec(t0) - 1, mido.Message("control_change", channel=c, control=7, value=rng.randint(60, 127)))
            # THE NOTES, the pedal, and what moves under them
            t = t0
            while t < length - 1.0:
                dur = rng.uniform(0.15, 1.6)
                for _ in range(rng.choice((1, 1, 2, 3))):
                    note = rng.randint(36, 90)
                    if c == stamped:
                        at(sec(t) - 2, mido.Message("control_change", channel=c, control=7,
                                                    value=rng.randint(70, 110)))
                    at(sec(t), mido.Message("note_on", channel=c, note=note, velocity=rng.randint(30, 120)))
                    at(sec(t + dur), mido.Message("note_off", channel=c, note=note, velocity=0))
                y = rng.random()
                if y < 0.15:
                    at(sec(t + dur / 2), mido.Message("pitchwheel", channel=c, pitch=rng.randint(-8192, 8191)))
                elif y < 0.3 and c != stamped:
                    # a swell or a fade under the held notes
                    for q in range(rng.randint(3, 10)):
                        at(sec(t + dur * q / 10.0), mido.Message("control_change", channel=c,
                                                                 control=rng.choice((7, 11)),
                                                                 value=rng.randint(20, 127)))
                elif y < 0.35:
                    at(sec(t + dur / 3), mido.Message("control_change", channel=c, control=101, value=0))
                    at(sec(t + dur / 3), mido.Message("control_change", channel=c, control=100, value=0))
                    at(sec(t + dur / 3), mido.Message("control_change", channel=c, control=6,
                                                      value=rng.randint(1, 12)))
                elif y < 0.38:
                    at(sec(t + dur), mido.Message("control_change", channel=c, control=121, value=0))
                elif y < 0.45:
                    at(sec(t + dur / 2), mido.Message("control_change", channel=c, control=64,
                                                      value=rng.choice((0, 127))))
                t += dur + rng.uniform(0.0, 0.4)
        if rng.random() < 0.2:
            # a reset mid-file -- each channel's program sent again after it, as
            # a file does, or left at 0, so a channel changes its piano class
            # mid-file (a register channel of its own: its tone's)
            at(sec(length / 2), mido.Message("sysex", data=rng.choice((GM_ON, GS_RESET))))
            if rng.random() < 0.5:
                for c in chans:
                    at(sec(length / 2), mido.Message("program_change", channel=c, program=progs[c]))
        ev.sort(key=lambda e: (e[0], e[1]))
        last = 0
        for tick, _, m in ev:
            tick = max(tick, 0)
            tr.append(m.copy(time=tick - last))
            last = tick
        path = os.path.join(out, "bend%02d.mid" % k)
        mid.save(path)
    print("bend files: %d in %s" % (n, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
