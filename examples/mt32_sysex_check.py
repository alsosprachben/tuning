#!/usr/bin/env python3
"""Does the reader hear a file as a real MT-32 / CM-64 would (native/mt32.h,
TUNING_MT32=mt32|cm64)?
    python3 examples/mt32_sysex_check.py
Small files, one per thing the unit does with a file, each read by
native.Midi under TUNING_MT32 and its events checked: the channels (1
silent, parts on 2-9, rhythm 10, moved by the System area), a program
change through the Patch Memory, a patch remapped, a custom timbre played by
its name, Patch Temp's key shift, level and pan, master volume and tune,
the reverb, the Rhythm Setup's level and pan (GS drum NRPNs) and its timbre
(reported, not followed), octave folding, the rhythm part's keys, and
aftertouch not received. Parsing only: light.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import mido             # noqa: E402
import native as N      # noqa: E402

BAD = []


def check(what, ok, detail=""):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what, ("  " + str(detail)) if detail and not ok else ""))
    if not ok:
        BAD.append(what)


def dt1(addr, data):
    body = list(addr) + list(data)
    return mido.Message('sysex', data=[0x41, 0x10, 0x16, 0x12] + body + [(128 - sum(body) % 128) % 128])


def read(msgs, model="mt32"):
    m = mido.MidiFile(type=0, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    for x in msgs:
        t.append(x)
    first = True
    for x in msgs:                      # (each note let go half a second on)
        if x.type == 'note_on':
            t.append(mido.Message('note_off', channel=x.channel, note=x.note, velocity=0, time=480 if first else 0))
            first = False
    os.environ["TUNING_MT32"] = model
    try:
        r = N.Midi(m)
        assert not r.error, r.error
        return r.events(), r.notes(), r.mt32_report(), r
    finally:
        del os.environ["TUNING_MT32"]


def on(ch, k, v=100, t=0):
    return mido.Message('note_on', channel=ch, note=k, velocity=v, time=t)


def last_prog(evs, ch, before=1e9):
    p = [e for e in evs if e[1] == 5 and e[2] == ch and e[0] <= before]
    return p[-1][3] if p else None


def cc(evs, ch, num):
    return [e[4] for e in evs if e[1] == 2 and e[2] == ch and e[3] == num]


def main():
    # 1. CHANNELS: 1 silent, 2 part 1 (on our channel 2), 10 rhythm
    evs, notes, rep, _ = read([on(0, 60), on(1, 60), on(9, 36), on(9, 100)])
    chans = sorted({n[0] for n in notes})
    check("channel 1 silent, channel 2 part 1, 10 rhythm", chans == [1, 9], "notes on %s" % chans)
    check("...reported", any("channel 1: no part" in r for r in rep), rep)
    check("rhythm key 100 dropped on an MT-32 (24-87)", not any(n[1] == 100 for n in notes))
    evs, notes, rep, _ = read([on(9, 100)], "cm64")
    check("...kept on a CM-64 (24-108)", any(n[1] == 100 for n in notes))
    # 2. SYSTEM AREA: part 1 to channel 1, rhythm off
    evs, notes, rep, _ = read([dt1((0x10, 0, 0x0D), [0]), dt1((0x10, 0, 0x15), [16]), on(0, 62), on(9, 36)])
    check("System area: part 1 onto channel 1 (plays on ours 2), rhythm off",
          [(n[0], n[1]) for n in notes] == [(1, 62)], [(n[0], n[1]) for n in notes])
    # 3. PROGRAM CHANGE through the Patch Memory: factory n -> MT-32 set n
    evs, notes, rep, _ = read([mido.Message('program_change', channel=1, program=88), on(1, 60)])
    check("program 89 -> the MT-32 set's 89 (Trumpet 1), bank 127",
          last_prog(evs, 1) == 88 and cc(evs, 1, 0)[-1:] == [127])
    # 4. PATCH MEMORY remapped: patch 1 = group B, timbre 1 (Acou Bass 1)
    evs, notes, rep, _ = read([dt1((5, 0, 0), [1, 0, 24, 50, 12, 0, 1, 0]),
                               mido.Message('program_change', channel=1, program=0), on(1, 40)])
    check("Patch Memory: program 1 -> Acou Bass 1 (65)", last_prog(evs, 1) == 64, last_prog(evs, 1))
    # 5. A CUSTOM TIMBRE by name: Timbre Memory 1 named "Harp", patch 1 selects it
    evs, notes, rep, _ = read([dt1((8, 0, 0), list(b"Harp      ")), dt1((5, 0, 0), [2, 0, 24, 50, 12, 0, 1, 0]),
                               mido.Message('program_change', channel=1, program=0), on(1, 60)])
    check("custom timbre 'Harp' -> GM 47 Harp, bank 0", last_prog(evs, 1) == 46 and cc(evs, 1, 0)[-1:] == [0],
          (last_prog(evs, 1), rep))
    evs, notes, rep, _ = read([dt1((8, 0, 0), list(b"Fr Horn 1 ")), dt1((5, 0, 0), [2, 0, 24, 50, 12, 0, 1, 0]),
                               mido.Message('program_change', channel=1, program=0), on(1, 60)])
    check("custom timbre 'Fr Horn 1' -> the MT-32 set's own", last_prog(evs, 1) == 92, (last_prog(evs, 1), rep))
    # 6. PATCH TEMP: part 2's key shift +5, level 50, pan 14 (left)
    evs, notes, rep, _ = read([dt1((3, 0, 0x12), [29]), dt1((3, 0, 0x18), [50, 14]), on(2, 60)])
    rp = [(e[3], e[4]) for e in evs if e[1] == 2 and e[2] == 2 and e[3] in (100, 101, 6)]
    check("Patch Temp: key shift +5 as RPN 2 (69)", (100, 2) in rp and (6, 69) in rp, rp)
    check("...level 50 -> CC7 64", cc(evs, 2, 7)[-1:] == [64], cc(evs, 2, 7))
    check("...pan 14 (the unit's left) -> GS hard left after the mirror", cc(evs, 2, 10)[-1:] == [1], cc(evs, 2, 10))
    # 7. MASTER VOLUME, TUNE and the REVERB
    evs, notes, rep, r = read([dt1((0x10, 0, 0x16), [50]), dt1((0x10, 0, 0), [64]), dt1((0x10, 0, 1), [1, 3, 7]),
                               on(1, 60)])
    xs = [bytes(r.sysex(e[3])) for e in evs if e[1] == 6]
    check("master volume as the universal message", any(x[:4] == bytes([0x7F, 0x7F, 4, 1]) for x in xs), xs)
    check("master tune as the universal fine tuning", any(x[:4] == bytes([0x7F, 0x7F, 4, 3]) for x in xs))
    check("reverb Hall -> GS Hall 1 (macro 3)", any(x[4:8] == bytes([0x40, 1, 0x30, 3]) for x in xs))
    # 8. RHYTHM SETUP: key 36's level 50, pan 0 (right), timbre changed
    evs, notes, rep, _ = read([dt1((3, 1, 0x10 + 4 * 12), [5, 50, 0, 1]), on(9, 36)])
    nr = [(e[3], e[4]) for e in evs if e[1] == 2 and e[2] == 9 and e[3] in (98, 99, 6)]
    check("Rhythm Setup: key 36 level as NRPN 1A", any(nr[i:i + 3] == [(99, 0x1A), (98, 36), (6, 64)] for i in range(len(nr))), nr)
    check("...pan 0 (the unit's right) as NRPN 1C 127", (6, 127) in nr, nr)
    check("...its timbre reported, not followed", any("rhythm key 36" in x for x in rep), rep)
    # 9. NOTES: folded, aftertouch not received, rhythm takes no program
    evs, notes, rep, _ = read([on(1, 5), mido.Message('aftertouch', channel=1, value=90),
                               mido.Message('program_change', channel=9, program=5), on(1, 120, t=10)])
    keys = sorted(n[1] for n in notes if n[0] == 1)
    check("melodic keys folded into 12-108", keys == [17, 108], keys)
    check("aftertouch not received", not any(e[1] == 3 for e in evs))
    check("the rhythm part takes no program change", last_prog(evs, 9) == 127, last_prog(evs, 9))
    # 10. ALL PARAMETERS RESET
    evs, notes, rep, _ = read([dt1((0x10, 0, 0x0D), [0]), dt1((0x7F, 0, 0), [0]), on(0, 60), on(1, 61)])
    check("7F: the channels back to power-on", [(n[0], n[1]) for n in notes] == [(1, 61)],
          [(n[0], n[1]) for n in notes])
    print("mt32: %d failed" % len(BAD))
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
