#!/usr/bin/env python3
"""Pitch bend in the file renderer: a tuning, a gesture, and the difference.

The file path ignored pitch bend completely -- a render with the wheel at full
deflection and one without came back BIT-IDENTICAL. What that threw away was
not only expression:

  A TUNING. John Sankey's bwv847.mid and bwv974.mid put one pitch class on
  each MIDI channel and one static pitch bend on each, which is a temperament
  written as twelve numbers. Rendered, every channel was landing on equal
  temperament and his tuning was going in the bin.

  A GESTURE. A-Team.mid sweeps a guitar 0 to +200 cents in 57 ms.

They need different machinery and they are separated on a test that has no
threshold in it: does the wheel ever MOVE while that channel is sounding? If
it does not, a fixed offset on f0 reproduces it exactly -- and a harpsichord,
which cannot bend a note, still gets its temperament. If it does, the note
needs a frequency that changes under it, which is a pair of per-block rows and
a term in the kernel.

This measures both, by tracking instantaneous frequency in the rendered audio
rather than by reading the partial table -- the table is what we asked for and
the audio is what came out.
"""
import math
import os
import sys

import mido
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import blockrender as B                                      # noqa: E402
import tonelib as T                                          # noqa: E402

SR = 48000
TPB = 480


def probe(path, program, bends, note=64, beats=8):
    """One long note on one channel, with `bends` as (beat, cents)."""
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=127, time=0))
    tr.append(mido.Message("note_on", channel=0, note=note, velocity=100, time=0))
    last = 0
    for beat, cents in bends:
        tick = int(beat * TPB)
        pitch = int(round(cents / 100.0 / T.BEND_RANGE_SEMITONES * 8192.0))
        tr.append(mido.Message("pitchwheel", channel=0,
                               pitch=max(-8192, min(8191, pitch)),
                               time=tick - last))
        last = tick
    tr.append(mido.Message("note_off", channel=0, note=note, velocity=0,
                           time=max(0, beats * TPB - last)))
    tr.append(mido.MetaMessage("end_of_track", time=TPB))
    m.save(path)
    return path


def track(a, f_hint, hop=256, win=2048):
    """Instantaneous frequency near f_hint, by phase difference between hops.

    THE REFERENCE RUNS ON ABSOLUTE TIME. Rebuilding exp(-i*w*n) from n=0 at
    every hop leaves the reference's own phase jump in the difference, and it
    reads back as frequency: measured on a note whose true fundamental was
    329.628 Hz, that bug reported 313.39 -- 87 cents flat, and a 200 cent sweep
    came out as 226. The partial table was right the whole time. Probes lie
    more often than renderers do.
    """
    w = np.hanning(win)
    out = []
    prev = None
    for s in range(0, len(a) - win, hop):
        n = np.arange(s, s + win)
        ref = np.exp(-2j * math.pi * f_hint * n / float(SR))
        z = complex(np.sum(a[s:s + win] * w * ref))
        if prev is not None and abs(z) > 1e-9 and abs(prev) > 1e-9:
            d = np.angle(z / prev)
            out.append((s / float(SR), f_hint + d * SR / (2 * math.pi * hop)))
        prev = z
    return out


def main():
    out = os.path.dirname(os.path.abspath(__file__))
    print("  pitch bend, measured in the rendered audio\n")

    # ---- a GESTURE: the wheel moves under a sounding note ------------------
    # 0 -> +200 cents over one beat, held, then back. A guitar can do this.
    sweep = [(1.0, 0.0), (1.25, 50.0), (1.5, 100.0), (1.75, 150.0),
             (2.0, 200.0), (4.0, 200.0), (4.5, 0.0)]
    p = probe(os.path.join(out, "bend_gesture.mid"), 29, sweep)
    L, R, tot, P, kdt = B.render(p, "even")
    a = (np.asarray(L) + np.asarray(R)) / 2.0
    prep = B._LAST_PREP
    f0 = float(np.asarray(prep["nf"])[np.asarray(prep["nf"]) > 0].min())
    tr = track(a, f0)
    print("  a GESTURE (overdriven guitar, %d partials on a bend row)"
          % int((np.asarray(prep["br"]) >= 0).sum()))
    # AGAINST THE NOTE'S OWN REST PITCH, not against f0. The claim is that the
    # wheel moves the pitch BY the amount asked, which is a ratio; and on an
    # overdriven guitar the strongest component near the nominal is not
    # necessarily the fundamental, so an absolute reading would be measuring
    # which partial the tracker locked onto rather than what the bend did.
    rest = min(tr, key=lambda e: abs(e[0] - 0.40))[1]
    print("     rest pitch %.2f Hz, and every reading is against it" % rest)
    for t_want, want in ((0.40, 0.0), (0.75, 100.0), (0.875, 150.0),
                         (1.00, 200.0), (1.50, 200.0), (2.40, 0.0)):
        got = min(tr, key=lambda e: abs(e[0] - t_want))
        c = 1200 * math.log2(max(got[1], 1e-9) / rest)
        print("     t=%.3f s   %8.2f Hz   %+7.1f cents   want %+6.1f   %s"
              % (got[0], got[1], c, want,
                 "ok" if abs(c - want) < 5.0 else "FAIL"))

    # ---- a TUNING: the wheel is set before the note and never moves --------
    # -9.77 cents, which is bwv847's C# channel. A harpsichord must take it.
    p = probe(os.path.join(out, "bend_tuning.mid"), 6, [(0.0, -9.77)])
    B.render(p, "even")
    prep = B._LAST_PREP
    nf = np.asarray(prep["nf"])
    lo = float(nf[nf > 0].min())
    ideal = B.tuning_table("even")[64]
    print("\n  a TUNING (harpsichord, which cannot bend)")
    print("     asked  -9.77 cents")
    print("     got   %+6.2f cents   (%d partials on a bend row -- a tuning needs none)"
          % (1200 * math.log2(lo / ideal), int((np.asarray(prep["br"]) >= 0).sum())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
