#!/usr/bin/env python3
"""The palm-muted chug, to hear what makes its thump (Ben: "in later
Metallica, there is a thump short sound when they play muted").

    python3 examples/chug_demo.py OUTDIR

writes OUTDIR/chug.mid: a stop-start riff in E at 108 bpm on the SC-88 map's 28.1
"Muted Dis.Gt" -- the distortion guitar (drive 14.4, a closed-back 4x12)
with the palm mute's decay law fitted to IDMT-SMT's muted takes, through its
gate (efxbus.NoiseGate) -- and open accents on GM 30, the same guitar
unmuted. Quad-tracked as a record is: two
takes a side, each its own timing and touch. A muted pick bass (34.8) on
the roots, stopping where the band stops.

  bars 1-4  the guitars and bass alone: the mute, the gain, the cabinet
  bars 5-8  the band: the kick on every hit, the snare on 2 and 4 where the
            band hits -- how much of the thump you feel is the bass drum's

STOP-START (RIFF: x a muted chug, a letter an open power chord, . a rest):
the whole band hits and stops together, so every rest is where the gate is
heard -- ungated, the muted strings' ring fills it (open_string_ring);
gated, it is silence. (A gallop's chugs abut, and a gate hardly acts.)
Not a Metallica riff: chugs, rests and open power chords, the idiom only.

    python3 examples/chug_demo.py --solo OUTDIR

writes OUTDIR/chug_solo.mid: the muted guitar alone, one take in the middle,
chugs with sixteenth rests between them -- where a gate has something to
close on (in the gallop the chugs abut, and it hardly acts).
"""
import os
import random
import sys

import mido

TPB = 480
BPM = 108.0
S16 = TPB // 4
GS_RESET = (0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41)

MUTE_L, MUTE_R, OPEN_L, OPEN_R, BASS, DRUMS = 0, 1, 2, 3, 4, 9
E5, G5, A5, F5 = (40, 47), (43, 50), (45, 52), (41, 48)


# a bar each: x a muted E5 chug, g/a/f/e an open G5/A5/F5/E5, . a rest
RIFF = ("x.xx.x.xx.x.xx..",
        "xx.xx.x.g..a....",
        "x.xx.x.xx.x.xx..",
        "xx.xx.x.f..e....")
OPEN = dict(g=G5, a=A5, f=F5, e=E5)


def riff():
    """[(tick, kind, chord, sixteenths)]: kind 'mute' or 'open'; RIFF's four
    bars played twice (the second time with the drums). A chug lasts most of
    its sixteenth; an open chord to the next hit, three sixteenths at most."""
    out = []
    for rep in range(2):
        for bar, pat in enumerate(RIFF):
            for i, c in enumerate(pat):
                if c == ".":
                    continue
                t = ((rep * 4 + bar) * 16 + i) * S16
                if c == "x":
                    out.append((t, 'mute', E5, 1))
                else:
                    nxt = next((j for j in range(i + 1, 16) if pat[j] != "."), 16)
                    out.append((t, 'open', OPEN[c], min(3, nxt - i)))
    return out


def build():
    rnd = random.Random(7)
    ev = [(0, mido.Message("sysex", data=GS_RESET))]

    def cc(t, ch, c, v):
        ev.append((t, mido.Message("control_change", channel=ch, control=c, value=v)))

    # the tones, on the SC-88 map (bank select LSB 2): 28.1, 30 and the
    # muted pick bass 34.8, which stops with the band
    for ch, prog, bank, pan in ((MUTE_L, 28, 1, 8), (MUTE_R, 28, 1, 120),
                                (OPEN_L, 30, 0, 16), (OPEN_R, 30, 0, 112), (BASS, 34, 8, 64)):
        cc(10, ch, 0, bank); cc(10, ch, 32, 2)
        ev.append((11, mido.Message("program_change", channel=ch, program=prog)))
        cc(12, ch, 10, pan); cc(12, ch, 91, 18); cc(12, ch, 93, 0)

    ev.append((11, mido.Message("program_change", channel=DRUMS, program=16)))   # the Power set
    cc(12, DRUMS, 91, 24)

    def note(t, ch, n, v, dur):
        t = max(20, t)
        ev.append((t, mido.Message("note_on", channel=ch, note=n, velocity=v)))
        ev.append((t + dur, mido.Message("note_off", channel=ch, note=n, velocity=0)))

    start = 2 * TPB
    for t, kind, chord, n16 in riff():
        t += start
        dur = n16 * S16 - (24 if kind == 'mute' else 12)
        for ch in ((MUTE_L, MUTE_R) if kind == 'mute' else (OPEN_L, OPEN_R)):
            # ...each take its own: a few ms either way, its own touch
            dt = int(rnd.gauss(0, 6))
            v = (104 if kind == 'mute' else 118) + int(rnd.gauss(0, 4))
            for n in chord:
                note(t + dt, ch, n, max(1, min(127, v)), dur)
        note(t, BASS, chord[0] - 12, 100 if kind == 'mute' else 112, dur)
        if t >= start + 64 * S16:
            note(t, DRUMS, 36, 112, S16)                       # the kick on every chug
    # the snare on 2 and 4 where the band hits, and a crash at the top,
    # through bars 5-8 -- no hi-hat: every rest is the whole band's
    for bar in range(4, 8):
        b = start + bar * 16 * S16
        for k in (4, 12):
            if RIFF[bar % 4][k] != ".":
                note(b + k * S16, DRUMS, 38, 110, S16)
    note(start + 64 * S16, DRUMS, 49, 120, 4 * S16)
    return sorted(ev, key=lambda e: e[0])


SOLO = "x.xx.x.x" "x.x.xx.." "xx.xx.x." "x.x.x..."   # sixteenths, x a chug


def solo():
    """One muted guitar, centred, two bars of chugs with rests between."""
    ev = [(0, mido.Message("sysex", data=GS_RESET))]
    for c, v in ((0, 1), (32, 2), (10, 64), (91, 18), (93, 0)):
        ev.append((10, mido.Message("control_change", channel=MUTE_L, control=c, value=v)))
    ev.append((11, mido.Message("program_change", channel=MUTE_L, program=28)))
    start = TPB
    for rep in range(2):
        for i, c in enumerate(SOLO):
            if c != "x":
                continue
            t = start + (rep * len(SOLO) + i) * S16
            for n in E5:
                ev.append((t, mido.Message("note_on", channel=MUTE_L, note=n, velocity=104)))
                ev.append((t + S16 - 24, mido.Message("note_off", channel=MUTE_L, note=n, velocity=0)))
    return sorted(ev, key=lambda e: e[0])


def write(ev, path):
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / BPM), time=0))
    last = 0
    for t, msg in ev:
        tr.append(msg.copy(time=t - last))
        last = t
    m.save(path)


def main(argv):
    so = "--solo" in argv
    argv = [a for a in argv if a != "--solo"]
    out = argv[1] if len(argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "chug_solo.mid" if so else "chug.mid")
    write(solo() if so else build(), path)
    print("  " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
