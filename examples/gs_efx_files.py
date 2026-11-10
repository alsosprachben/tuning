#!/usr/bin/env python3
"""A GS test file for every SC-88Pro insertion effect type -- the coverage set.

    python3 examples/gs_efx_files.py OUTDIR [--types=N,N,...]

One file a type (all 65 of gs_efx_params.TYPES, Thru among them), named
efx_NN.mid by the type's number in Roland's list: a GS reset, the type at its
defaults (no parameter sent: the type's own, as a file that only selects it
gets), part 1 on the effect playing a phrase on a program the type is made
for -- a guitar for the overdrives and the guitar multis, a bass for the Bass
Multi, an electric piano for the Rhodes Multi, an organ for the rotaries, a
piano otherwise -- and part 2 dry beside it (strings, held), so the effect is
heard on its part alone. Deterministic: the same bytes every run, so a check
can make them where it runs (examples/efx_coverage.py). The deeper cases --
parameters moved, controllers, sends, types changed mid-file -- are the live
batches' files; this is the floor: every type sounding once.
"""
import os
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gs_efx_params as P       # noqa: E402

GUITAR, CLEAN, BASS, EP, ORGAN, PIANO, STRINGS = 29, 27, 33, 4, 16, 0, 48


def program_for(name):
    """The program a type is made for (0-based GM)."""
    n = name.replace(" ", "")
    if "Rotary" in name:
        return ORGAN
    if name == "Bass Multi":
        return BASS
    if name == "Rhodes Multi":
        return EP
    if name.startswith("Clean"):
        return CLEAN
    if (name in ("Overdrive", "Distortion") or name.startswith("GTR") or n.startswith("OD")
            or n.startswith("DS")):
        return GUITAR
    return PIANO


def gs(addr, data):
    body = list(addr) + list(data)
    return mido.Message('sysex', data=[0x41, 0x10, 0x42, 0x12] + body + [(128 - sum(body) % 128) % 128])


def part_on(ch, v=1):
    """40 4x 22: the part's insertion effect switch (x the part's block)."""
    blk = 0 if ch == 9 else (ch + 1 if ch < 9 else ch)
    return gs((0x40, 0x40 | blk, 0x22), [v])


def make(path, msb, lsb, name):
    m = mido.MidiFile(ticks_per_beat=480)
    setup = mido.MidiTrack()
    m.tracks.append(setup)
    setup.append(gs((0x40, 0x00, 0x7F), [0x00]))                 # GS reset
    setup.append(gs((0x40, 0x03, 0x00), [msb, lsb]))             # the type, its defaults
    setup.append(part_on(0))
    lead = mido.MidiTrack()
    m.tracks.append(lead)
    lead += [mido.Message('program_change', channel=0, program=program_for(name), time=240)]
    base = 40 if program_for(name) == BASS else 55
    t = 0
    # a broken chord, a held chord, single notes with gaps (the effect's tail heard), a last chord
    for k, n in enumerate((0, 4, 7, 12, 7, 4)):
        lead.append(mido.Message('note_on', channel=0, note=base + n, velocity=88 + 4 * (k % 3), time=t))
        lead.append(mido.Message('note_off', channel=0, note=base + n, time=200))
        t = 40
    for n in (0, 7, 12, 16):
        lead.append(mido.Message('note_on', channel=0, note=base + n, velocity=96, time=t))
        t = 0
    lead.append(mido.Message('note_off', channel=0, note=base, time=960))
    for n in (7, 12, 16):
        lead.append(mido.Message('note_off', channel=0, note=base + n, time=0))
    for n in (12, 14, 19):
        lead.append(mido.Message('note_on', channel=0, note=base + n, velocity=110, time=360))
        lead.append(mido.Message('note_off', channel=0, note=base + n, time=120))
    for n in (5, 9, 12):
        lead.append(mido.Message('note_on', channel=0, note=base + n, velocity=90, time=t if n != 5 else 480))
        t = 0
    lead.append(mido.Message('note_off', channel=0, note=base + 5, time=1200))
    for n in (9, 12):
        lead.append(mido.Message('note_off', channel=0, note=base + n, time=0))
    pad = mido.MidiTrack()
    m.tracks.append(pad)
    pad += [mido.Message('program_change', channel=1, program=STRINGS, time=240),
            mido.Message('control_change', channel=1, control=7, value=70, time=0)]
    for n in (43, 50, 59):
        pad.append(mido.Message('note_on', channel=1, note=n, velocity=70, time=0))
    pad.append(mido.Message('note_off', channel=1, note=43, time=3600))
    for n in (50, 59):
        pad.append(mido.Message('note_off', channel=1, note=n, time=0))
    m.save(path)


def files(outdir, only=None):
    """[(number, name, path)] for every type (or those in only), written to outdir."""
    os.makedirs(outdir, exist_ok=True)
    out = []
    for (msb, lsb), (num, name) in sorted(P.TYPES.items(), key=lambda kv: kv[1][0]):
        if only and num not in only:
            continue
        path = os.path.join(outdir, "efx_%02d.mid" % num)
        make(path, msb, lsb, name)
        out.append((num, name, path))
    return out


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
    if not args:
        print(__doc__)
        return 2
    only = {int(x) for x in opt["types"].split(",")} if opt.get("types") else None
    for num, name, path in files(args[0], only):
        print("%02d %-20s %s" % (num, name, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
