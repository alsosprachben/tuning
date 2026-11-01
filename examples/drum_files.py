#!/usr/bin/env python3
"""Piano files with a drum part the engine plays: OUT_DIR/drumNN.mid

    python3 examples/drum_files.py OUT_DIR [N] [--seed=S]

N random General MIDI files (default 12), 12-20 seconds each, written for
examples/nvrender_check.py to render both ways:
one or two piano channels (programs 0-3) and channel 10 playing the kit
drums native/voice.c has (native.kits: the kicks and the toms) in a set
whose keys they are (Standard, Room, Power, Jazz, Brush, CM-64/32L; or a
program kit_for_program sends to Standard). What the drum note setup has to
get right, all of it in the mix: each key's pitch and seat in its set; the
one-shot's hold (a drum's key-up ignored, held 8 s, a re-strike of the
same drum ending it); the part's level, pan and expression at each stroke,
and a fader moving under the drums; a sustain pedal on the drum channel
(a drum takes none); the set changed mid-file; All Sound Off.
"""
import os
import random
import sys

KEYS = (35, 36, 41, 43, 45, 47, 48, 50)
SETS = (0, 1, 8, 16, 32, 127, 3, 20, 44, 70)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    import mido
    out = args[0]
    n = int(args[1]) if len(args) > 1 else 12
    rng = random.Random(int(opt.get("seed", 1)))
    os.makedirs(out, exist_ok=True)
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
        # THE PIANOS
        for c in rng.sample(range(9), rng.randint(1, 2)):
            at(0, mido.Message("program_change", channel=c, program=rng.randint(0, 3)))
            t = rng.uniform(0.0, 0.5)
            while t < length - 1.0:
                dur = rng.uniform(0.2, 1.5)
                for _ in range(rng.choice((1, 2))):
                    note = rng.randint(40, 84)
                    at(sec(t), mido.Message("note_on", channel=c, note=note, velocity=rng.randint(30, 110)))
                    at(sec(t + dur), mido.Message("note_off", channel=c, note=note, velocity=0))
                t += dur + rng.uniform(0.0, 0.5)
        # THE DRUMS, on channel 10
        d = 9
        at(0, mido.Message("program_change", channel=d, program=rng.choice(SETS)))
        if rng.random() < 0.5:
            at(0, mido.Message("control_change", channel=d, control=10, value=rng.randint(20, 108)))
        if rng.random() < 0.4:
            at(0, mido.Message("control_change", channel=d, control=7, value=rng.randint(60, 127)))
        keys = rng.sample(KEYS, rng.randint(2, len(KEYS)))
        step = rng.choice((0.25, 0.5, 0.125))
        t = rng.uniform(0.0, 0.3)
        changed = False
        while t < length - 0.5:
            if rng.random() < 0.7:
                key = rng.choice(keys)
                # a key held short, or long past its next stroke
                held = rng.choice((0.05, step * 0.9, rng.uniform(0.5, 10.0)))
                at(sec(t), mido.Message("note_on", channel=d, note=key, velocity=rng.randint(20, 127)))
                at(sec(t + held), mido.Message("note_off", channel=d, note=key, velocity=0))
            y = rng.random()
            if y < 0.05:
                # a swell or a fade under the ringing drums
                for q in range(rng.randint(3, 8)):
                    at(sec(t + step * q / 4.0), mido.Message("control_change", channel=d,
                                                             control=rng.choice((7, 11)),
                                                             value=rng.randint(30, 127)))
            elif y < 0.08:
                at(sec(t), mido.Message("control_change", channel=d, control=10, value=rng.randint(0, 127)))
            elif y < 0.12:
                at(sec(t), mido.Message("control_change", channel=d, control=64, value=rng.choice((0, 127))))
            elif y < 0.13:
                at(sec(t + step / 2), mido.Message("control_change", channel=d, control=120, value=0))
            elif y < 0.14 and not changed:
                at(sec(t), mido.Message("program_change", channel=d, program=rng.choice(SETS)))
                changed = True
            t += step
        ev.sort(key=lambda e: (e[0], e[1]))
        last = 0
        for tick, _, m in ev:
            tick = max(tick, 0)
            tr.append(m.copy(time=tick - last))
            last = tick
        path = os.path.join(out, "drum%02d.mid" % k)
        mid.save(path)
    print("drum files: %d in %s" % (n, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
