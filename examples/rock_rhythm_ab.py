#!/usr/bin/env python3
"""Rock Rhythm (GS 30.24) by palm-mute strength: one track of a file, a
window of it, rendered alone with the distortion guitar's strings muted at
several strengths, for the ear.

    python3 examples/rock_rhythm_ab.py FILE.mid TRACK START_S SECONDS OUT_DIR [S ...]

S is the mute's strength between GM 30's own strings (0) and GM 28's fitted
palm mute (1, IDMT-SMT-Guitar, a clean DI guitar): the decay rates are taken
geometrically between the two, the pick and the palm's low-pass linearly
(patch_map.palm_mute). Default strengths 0, 0.3 and 1. Every program change in the
track is kept, so the window plays what the file selects there -- the track
must select 30.24 for the strength to apply (it is installed as that tone).

WHY A STRENGTH. GM 28's fit is the physical damping of a clean palm mute; a
driven chug's audible length also depends on how hard the palm rests, which
is the player's choice. A distorted palm-muted open G (Freesound 12042,
CC0) swells over 150 ms, sags only ~11 dB/s for 300 ms and is let go at
0.55 s -- about 0.2-0.35 of GM 28's mute. One take cannot set it alone.
"""
import os
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B   # noqa: E402
import patch_map as P     # noqa: E402
import tonelib as T       # noqa: E402

def mute_attrs(s):
    """The distortion guitar's string settings at palm-mute strength s."""
    return P.palm_mute(s)


def window(path, track, t0, secs):
    """A file of one track's window [t0, t0 + secs) s, its state kept: every
    controller and program change before t0 sent at 0, notes cut at the end."""
    mf = mido.MidiFile(path)
    tempo = []
    for tr in mf.tracks:
        t = 0
        for m in tr:
            t += m.time
            if m.type == 'set_tempo':
                tempo.append((t, m.tempo))
    tempo.sort()

    def sec(tk):
        s, lt, tp = 0.0, 0, 500000
        for t, tv in tempo:
            if t >= tk:
                break
            s += (t - lt) * tp / mf.ticks_per_beat / 1e6
            lt, tp = t, tv
        return s + (tk - lt) * tp / mf.ticks_per_beat / 1e6

    out = mido.MidiFile(ticks_per_beat=mf.ticks_per_beat)
    meta = mido.MidiTrack()
    out.tracks.append(meta)
    tr = mido.MidiTrack()
    out.tracks.append(tr)
    ev, t, k0 = [], 0, None
    for m in mf.tracks[track]:
        t += m.time
        s = sec(t)
        if m.type == 'midi_port':
            continue                 # one track alone: its channel, port A
        if s < t0:
            if not m.is_meta and m.type not in ('note_on', 'note_off'):
                ev.append((0, m))
            continue
        if s >= t0 + secs:
            break
        if k0 is None:
            k0 = t
        ev.append((t - k0 + 1, m))
    for tk, tv in tempo:
        if sec(tk) <= t0:
            meta.append(mido.MetaMessage('set_tempo', tempo=tv, time=0))
    last = 0
    held = set()
    for tk, m in ev:
        tr.append(m.copy(time=tk - last))
        last = tk
        if m.type == 'note_on' and m.velocity:
            held.add((m.channel, m.note))
        elif m.type in ('note_on', 'note_off'):
            held.discard((m.channel, m.note))
    for ch, n in sorted(held):
        tr.append(mido.Message('note_off', channel=ch, note=n, time=0))
    return out


def main(argv):
    path, track, t0, secs, out = argv[1], int(argv[2]), float(argv[3]), float(argv[4]), argv[5]
    strengths = [float(v) for v in argv[6:]] or [0.0, 0.3, 1.0]
    name = os.path.splitext(os.path.basename(path))[0].lower()
    m = window(path, track, t0, secs)
    keep = P.VARIATIONS.get((30, 24))
    try:
        for s in strengths:
            P.VARIATIONS[(30, 24)] = type("RockRhythm_%d" % round(100 * s),
                                          (T.DistortionGuitarProperties,), mute_attrs(s))
            L, R = B.render(m, "even")[:2]
            f = os.path.join(out, "%s_t%d_mute%03d.wav" % (name, track, round(100 * s)))
            B.write_wav(f, L, R)
            print("  ", f)
    finally:
        if keep is None:
            P.VARIATIONS.pop((30, 24), None)
        else:
            P.VARIATIONS[(30, 24)] = keep
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
