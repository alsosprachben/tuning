#!/usr/bin/env python3
"""Test files for every tone and drum set the coverage page lists -- the
program coverage set (examples/tone_coverage.py runs them).

    python3 examples/gs_tone_files.py OUTDIR [--stages=GM1,GM2,...] [--per=16]

The tones are native_coverage's, stage by stage (each stage only what the one
before did not bring): GM 1's 128, GM 2's variations, the MT-32's map, then
the Sound Canvas maps' variations. Each file plays PER of them in turn on
channel 1 -- its bank select and program change, then a phrase over the
keyboard (a low note, a held chord at middle C, notes climbing to C7) and a
gap for its tail -- so a check of the file is a check of each tone, and of
the program changes between them, as a keyboard sends them. A stage's
files start as its standard is entered: GM 1's and the maps' with a GS reset
(the map in CC32), GM 2's with GM 2 System On (CC0 121, CC32 its LSB), the
MT-32's with a GS reset and CC0 127. The drum sets: one file a set, on
channel 10, its program change (a map's set by CC32) and then every key it
defines, one at a time, soft and hard.

Deterministic: the same bytes every run. tones(STAGES) and kits(STAGES) list
what there is; files() writes them and returns a manifest -- each file's
tones (or set) and where in it each tone starts.
"""
import os
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

TPB = 480                   # (120 bpm: 960 ticks a second)
SEC = 2 * TPB
SPAN = 3.2                  # seconds a tone: its phrase, then its tail
GS_RESET = (0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41)
GM2_ON = (0x7E, 0x7F, 0x09, 0x03)
# the phrase: (start s, length s, keys, velocity)
PHRASE = ((0.05, 0.40, (36,), 90), (0.45, 0.30, (48,), 100), (0.80, 0.80, (60, 64, 67), 80),
          (1.70, 0.25, (72,), 110), (2.00, 0.25, (84,), 70), (2.30, 0.20, (96,), 100))
DRUM_STEP = 0.15


def tones(stages=None):
    """[(stage, program, key, name, msb, lsb)] -- native_coverage's tones, each
    with the bank select that reaches it (msb None: a program change alone)."""
    import patch_map as P
    import livetui as LT
    import native_coverage as NC
    out, seen = [], set()
    for stage, src in NC.STAGES:
        if src is None:
            ts = [(p, 0, LT.GM[p], None, None) for p in range(128)]
        elif src == 'gm2':
            ts = sorted({(p, P.gm2_bank(p, l), P.GM2_NAMES[(p, l)], 121, l) for (p, l) in P.GM2_NAMES
                         if l and P.gm2_bank(p, l)})
        elif src == 'mt32':
            ts = [(p, 127, P.VARIATION_NAMES[(p, 127)], 127, 0) for p in range(128)]
        elif src == 'cm64':
            ts = []
        else:
            ts = sorted({(p, P.map_bank(p, b, src), P.MAP_NAMES[src][(p, b)], b, src) for (p, b) in P.MAP_NAMES[src]
                         if b and P.map_bank(p, b, src)})
        new = []
        for t in ts:
            if (t[0], t[1]) not in seen:
                seen.add((t[0], t[1]))
                new.append(t)
        if stages is None or stage in stages:
            out += [(stage,) + t for t in new]
    return out


def kits(stages=None):
    """[(stage, set, name, keys)] -- native_coverage's drum sets (a map's past
    127: 128 x its map + program), each with the keys it defines."""
    import percussion_map as PM
    import native_coverage as NC
    out, seen = [], set()
    for stage, src in NC.STAGES:
        if src is None:
            ks = [0]
        elif src == 'gm2':
            ks = [0, 8, 16, 24, 25, 32, 40, 48, 56]
        elif src == 'mt32':
            ks = [(127, "MT-32 rhythm part", set(PM.CM32L_DRUMS))]
        elif src == 'cm64':
            ks = [(127, "CM-32L sound effects", set(PM.KITS[127]) - set(PM.CM32L_DRUMS))]
        else:
            ks = sorted({PM.kit_in_map(s, src) for s in PM.DRUM_SETS if s < 128})
        for k in ks:
            if not isinstance(k, tuple):
                if k in seen:
                    continue
                seen.add(k)
            if stages is not None and stage not in stages:
                continue
            if isinstance(k, tuple):
                s, name, only = k
            else:
                s, name, only = k, PM.drum_set_name(k if k < 128 else k % 128), None
            kit = PM.kit_for_program(s)
            keys = [n for n in range(128) if PM.percussion_for_note(n, kit) and (only is None or n in only)]
            out.append((stage, s, name, keys))
    return out


def _sysex(tr, data, t):
    tr.append(mido.Message('sysex', data=list(data), time=t))


def _abs_track(events):
    """A track from (seconds, order, message) at absolute times."""
    tr = mido.MidiTrack()
    last = 0
    for sec, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        tick = int(round(sec * SEC))
        tr.append(msg.copy(time=tick - last))
        last = tick
    return tr


def make_tones(path, ts):
    """ts [(stage, program, key, name, msb, lsb)], one stage's: a file of
    them in turn; their start times (s)"""
    m = mido.MidiFile(ticks_per_beat=TPB)
    setup = mido.MidiTrack()
    m.tracks.append(setup)
    if ts[0][0] == "GM2":
        _sysex(setup, GM2_ON, 0)
    else:
        _sysex(setup, GS_RESET, 0)
    ev, starts, o = [], [], 0
    for i, (_stage, p, _key, _name, msb, lsb) in enumerate(ts):
        t0 = 0.25 + i * SPAN
        starts.append(t0)
        ch = 0
        sel = []
        if msb is not None:
            sel += [mido.Message('control_change', channel=ch, control=0, value=msb),
                    mido.Message('control_change', channel=ch, control=32, value=lsb)]
        elif i:
            sel += [mido.Message('control_change', channel=ch, control=0, value=0),
                    mido.Message('control_change', channel=ch, control=32, value=0)]
        sel.append(mido.Message('program_change', channel=ch, program=p))
        for msg in sel:
            ev.append((t0 - 0.2, o, msg))
            o += 1
        for at, ln, keys, vel in PHRASE:
            for k in keys:
                ev.append((t0 + at, o, mido.Message('note_on', channel=ch, note=k, velocity=vel)))
                o += 1
            for k in keys:
                ev.append((t0 + at + ln, o, mido.Message('note_off', channel=ch, note=k, velocity=64)))
                o += 1
    m.tracks.append(_abs_track(ev))
    m.save(path)
    return starts


def make_kit(path, stage, s, keys):
    """a drum set's file: its program change (a map's by CC32), each key in turn"""
    m = mido.MidiFile(ticks_per_beat=TPB)
    setup = mido.MidiTrack()
    m.tracks.append(setup)
    _sysex(setup, GM2_ON if stage == "GM2" else GS_RESET, 0)
    ev, o = [], 0
    if s >= 128:
        ev.append((0.05, o, mido.Message('control_change', channel=9, control=32, value=s // 128)))
        o += 1
    ev.append((0.05, o, mido.Message('program_change', channel=9, program=s % 128)))
    o += 1
    for i, k in enumerate(keys):
        t = 0.25 + i * DRUM_STEP
        ev.append((t, o, mido.Message('note_on', channel=9, note=k, velocity=70 if i % 2 else 110)))
        ev.append((t + 0.1, o + 1, mido.Message('note_off', channel=9, note=k, velocity=64)))
        o += 2
    m.tracks.append(_abs_track(ev))
    m.save(path)


def tone_seconds(n):
    """a file of n tones' length (s), its last tail in"""
    return 0.25 + n * SPAN + 0.5


def kit_seconds(nkeys):
    return 0.25 + nkeys * DRUM_STEP + 1.5


def files(outdir, stages=None, per=16, with_kits=True):
    """write the set; the manifest: [{file, path, kind "tones"|"kit", seconds,
    tones: [{stage, program, key, name, start}] | kit: {stage, set, name, keys}}]"""
    os.makedirs(outdir, exist_ok=True)
    man = []
    ts = tones(stages)
    for stage in dict.fromkeys(t[0] for t in ts):
        st = [t for t in ts if t[0] == stage]
        for j in range(0, len(st), per):
            batch = st[j:j + per]
            name = "tones_%s_%02d" % (stage.replace(" ", "").replace("-", "").lower(), j // per)
            path = os.path.join(outdir, name + ".mid")
            starts = make_tones(path, batch)
            man.append(dict(file=name, path=path, kind="tones", seconds=tone_seconds(len(batch)),
                            tones=[dict(stage=t[0], program=t[1], key=t[2], name=t[3], msb=t[4], lsb=t[5],
                                        start=s0) for t, s0 in zip(batch, starts)]))
    if with_kits:
        for stage, s, name, keys in kits(stages):
            if not keys:
                continue
            fn = "kit_%s_%d_%s" % (stage.replace(" ", "").replace("-", "").lower(), s,
                                   "".join(c for c in name.lower() if c.isalnum())[:16])
            path = os.path.join(outdir, fn + ".mid")
            make_kit(path, stage, s, keys)
            man.append(dict(file=fn, path=path, kind="kit", seconds=kit_seconds(len(keys)),
                            kit=dict(stage=stage, set=s, name=name, keys=len(keys))))
    return man


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
    if not args:
        print(__doc__)
        return 2
    stages = set(opt["stages"].split(",")) if opt.get("stages") else None
    man = files(args[0], stages, int(opt.get("per", 16)))
    for f in man:
        what = ("%d tones, %s .. %s" % (len(f["tones"]), f["tones"][0]["name"], f["tones"][-1]["name"])
                if f["kind"] == "tones" else "set %d %s, %d keys" % (f["kit"]["set"], f["kit"]["name"],
                                                                     f["kit"]["keys"]))
        print("%-32s %5.1f s  %s" % (f["file"], f["seconds"], what))
    print("%d files: %d tones, %d drum sets" % (len(man), sum(len(f.get("tones", ())) for f in man),
                                               sum(f["kind"] == "kit" for f in man)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
