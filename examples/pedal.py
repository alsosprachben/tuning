#!/usr/bin/env python3
"""The damper pedal, offline: does it hold, and does a re-strike re-damp?

The file renderer ignored CC64 completely -- a three-note file with the pedal
held and one without came back BIT-IDENTICAL, max diff 0.00e+00. Ravel's
Ondine carries 1271 damper events and the pedal is down for 93% of its 343
seconds, so it was rendering entirely dry.

Two things have to be true, and the second is the one that is easy to get
wrong:

  1. a key released under the pedal goes on ringing until the pedal comes up;
  2. ...but no longer than until THAT SAME STRING IS STRUCK AGAIN. There is
     only one string per pitch, and two copies of it do not sum, they BEAT.
     Measured on ondine.mid, 2658 of 4579 pedalled notes would otherwise run
     past their own next onset -- the common case, not an edge.

Both are checked here from the partial table rather than by ear, because the
table has exact numbers in it and a spectrogram does not.
"""
import os
import sys

import mido
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import blockrender as B                                      # noqa: E402

SR = 48000
TPB = 480
TEMPO = 500000          # 0.5 s per beat


def _file(path, msgs, pedal=True):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=TEMPO, time=0))
    tr.append(mido.Message("program_change", channel=0, program=0, time=0))
    if pedal:
        tr.append(mido.Message("control_change", channel=0,
                               control=64, value=127, time=0))
    for msg in msgs:
        tr.append(msg)
    tr.append(mido.MetaMessage("end_of_track", time=TPB * 4))
    m.save(path)
    return path


def _groups(prep, hz, tol=1.0):
    """(onset, end) per strike of the partial nearest `hz`, in seconds."""
    nf = np.asarray(prep["nf"])
    non = np.asarray(prep["non"])
    noff = np.asarray(prep["noff"])
    sel = np.abs(nf - hz) < tol
    out = []
    for s in sorted(set(non[sel].tolist())):
        m = sel & (non == s)
        out.append((s / float(SR), float(noff[m].max()) / SR))
    return out


def main():
    out = os.path.dirname(os.path.abspath(__file__))
    print("  the damper pedal, from the partial table\n")

    # ---- 1. it holds -------------------------------------------------------
    notes = [mido.Message("note_on", channel=0, note=60, velocity=100, time=0),
             mido.Message("note_off", channel=0, note=60, velocity=0, time=240),
             mido.Message("control_change", channel=0,
                          control=64, value=0, time=TPB * 4)]
    dry = B.prepare(_file(os.path.join(out, "pedal_dry.mid"), notes[:2],
                          pedal=False), "hybrid440")
    wet = B.prepare(_file(os.path.join(out, "pedal_held.mid"), notes), "hybrid440")
    f0 = min(f for f in np.asarray(dry["nf"]) if f > 0)
    d_end = _groups(dry, f0)[0][1]
    w_end = _groups(wet, f0)[0][1]
    print("  a key released under the pedal keeps ringing")
    print("     dry    ends %.3f s" % d_end)
    print("     pedal  ends %.3f s   %s" % (w_end, "ok" if w_end > d_end + 0.5
                                            else "FAIL"))

    # ---- 2. ...and a re-strike re-damps ------------------------------------
    two = [mido.Message("note_on", channel=0, note=60, velocity=100, time=0),
           mido.Message("note_off", channel=0, note=60, velocity=0, time=240),
           mido.Message("note_on", channel=0, note=60, velocity=100, time=720),
           mido.Message("note_off", channel=0, note=60, velocity=0, time=240),
           mido.Message("control_change", channel=0,
                        control=64, value=0, time=TPB * 6)]
    p = B.prepare(_file(os.path.join(out, "pedal_restrike.mid"), two), "hybrid440")
    g = _groups(p, f0)
    strikes = sorted({round(a, 2) for a, _ in g})
    print("\n  ...but only until that same string is struck again")
    for a, b in sorted(g):
        print("     onset %.3f s  ends %.3f s" % (a, b))
    if len(strikes) >= 2:
        first_end = max(b for a, b in g if round(a, 2) == strikes[0])
        second = strikes[1]
        gap = second - first_end
        print("     first ends %.3f, second strikes %.3f -> gap %.4f s  %s"
              % (first_end, second, gap,
                 "ok, one steal-fade" if -1e-6 <= gap < 0.01 else "FAIL"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
