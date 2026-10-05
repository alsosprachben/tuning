#!/usr/bin/env python3
"""Does the streaming renderer render what the whole table renders, bit for bit?

    python3 examples/streamcheck.py FILE.mid [SECONDS]
    python3 examples/streamcheck.py --passes

Each file (or its first SECONDS, bitident's excerpt) is rendered twice: by
streamrender.render -- notes emitted, windows rendered as they complete, rows
let go -- and by prepare() + synth_window on the whole table. The main mix and
the reverb send must be byte-identical; the peak number of live rows is the
stream's memory, against the table's.

--passes writes and checks a file built to drive every pass the stream
reproduces together: a clavinet's tone section (CC1), an e-piano's tremolo
(CC1), tremolo strings, the chorus (CC93) and a cabinet voice, with channels
sending differently to the reverb (CC91), so the send bus is rendered too.
"""
import os
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import blockrender as B                                 # noqa: E402
import streamrender as S                                # noqa: E402

PASSES = ((0, 7, {1: 90}), (1, 4, {1: 100, 93: 70}), (2, 44, {93: 90}),
          (3, 48, {93: 60, 91: 100}), (4, 61, {}))


def passes_file():
    import mido
    m = mido.MidiFile(ticks_per_beat=480)
    for ch, prog, ccs in PASSES:
        tr = mido.MidiTrack()
        m.tracks.append(tr)
        tr.append(mido.Message('program_change', channel=ch, program=prog, time=0))
        for cc, v in ccs.items():
            tr.append(mido.Message('control_change', channel=ch, control=cc, value=v, time=0))
        for n in (60, 64, 67, 72):
            tr.append(mido.Message('note_on', channel=ch, note=n, velocity=96, time=0))
            tr.append(mido.Message('note_off', channel=ch, note=n, time=240))
        for n in (48, 55, 64):
            tr.append(mido.Message('note_on', channel=ch, note=n, velocity=90, time=0))
        tr.append(mido.Message('note_off', channel=ch, note=48, time=1920))
        tr.append(mido.Message('note_off', channel=ch, note=55, time=0))
        tr.append(mido.Message('note_off', channel=ch, note=64, time=0))
    path = os.path.join(tempfile.mkdtemp(prefix="streamcheck_"), "passes.mid")
    m.save(path)
    return path


def check(name, f, tuner="hybridmean:440"):
    t = time.time()
    try:
        Ls, Rs, s = S.render(f, tuner, send=True)
    except S.NotStreamable as e:
        print("%s: not streamed yet (the %s pass)" % (name, e))
        return True
    ts = time.time() - t
    t = time.time()
    p = B.prepare(f, tuner)
    Lw, Rw = B.synth_window(p, 0, p['N'])
    tw = time.time() - t
    same = Ls.tobytes() == Lw.tobytes() and Rs.tobytes() == Rw.tobytes()
    # the send, as blockrender's own second render makes it
    g = np.ones(p['P'], np.float32)
    for c, v in p['reverb_send'].items():
        g[p['mch'] == c] = v
    p['aL'] = p['aL'] * g
    p['aR'] = p['aR'] * g
    bl = np.zeros(p['N'], np.float32)
    br = np.zeros(p['N'], np.float32)
    B.synth_partials(p, 0, p['N'], 0, p['P'], bl, br)
    mg = B.master_curve(p.get('mvol'), 0, p['N'])
    if mg is not None:
        bl *= mg
        br *= mg
    send_same = s.SL.tobytes() == bl.tobytes() and s.SR.tobytes() == br.tobytes()
    print("%s: %d rows, at most %d live; streamed %.1fs, whole %.1fs; mix %s, send %s"
          % (name, p['P'], s.peak_live, ts, tw, "identical" if same else "DIFFERS",
             "identical" if send_same else "DIFFERS"))
    return same and send_same


def main(argv):
    if "--passes" in argv:
        return 0 if check("passes", passes_file()) else 1
    f = argv[1]
    name = os.path.basename(f)
    if len(argv) > 2:
        from bitident import excerpt
        f = excerpt(f, float(argv[2]))
        name += " (first %ss)" % argv[2]
    return 0 if check(name, f) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
