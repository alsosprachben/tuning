"""A drum set's notes against the Standard notes they replace.

    python3 examples/drumset_check.py [SET]      # default 24, Electronic

For each note the set changes: loudness (the loudest 150 ms, RMS in dB) and
how long the note takes to fall 40 dB from its peak, for the set and for
Standard. A set is a different instrument, not a quieter or longer one, so
the loudness should land near Standard's -- a kit whose kick is 12 dB under
the snare is a mix problem, not a sound -- while the length is allowed to be
the set's own.
"""
import os
import sys

import mido
import numpy as np

sys.path.insert(0, os.getcwd())
import blockrender as B                  # noqa: E402
import percussion_map as PM              # noqa: E402


def note_file(program, note, vel=100, hold=1.5):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=9, program=program, time=0))
    tr.append(mido.Message("note_on", channel=9, note=note, velocity=vel, time=0))
    tr.append(mido.Message("note_off", channel=9, note=note, velocity=0,
                           time=int(hold * 960)))
    return m


def measure(program, note, hold):
    L, R = B.render(note_file(program, note, hold=hold))[:2]
    x = np.asarray(L, np.float64) + np.asarray(R, np.float64)
    sr = B.SR
    # THE LOUDEST 150 ms, not the first: a struck drum's loudest window IS its
    # first, but a brush swirl swells in over 120 ms and would read quiet.
    n150, hop = int(0.15 * sr), int(0.01 * sr)
    rms = 20 * np.log10(max(np.sqrt(np.mean(x[i:i + n150] ** 2))
                            for i in range(0, max(1, min(len(x), 2 * sr) - n150), hop))
                        + 1e-12)
    w = int(0.005 * sr)
    env = np.sqrt(np.convolve(x ** 2, np.ones(w) / w, 'same')) + 1e-12
    pk = int(np.argmax(env))
    below = np.nonzero(20 * np.log10(env[pk:] / env[pk]) < -40)[0]
    t40 = (below[0] / sr) if len(below) else len(x) / sr
    peak_t = pk / sr
    return rms, t40, peak_t


def main():
    kit = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    if kit not in PM.KITS:
        sys.exit("set %d is not built" % kit)
    print("  note  %-18s %8s %8s   %-16s %8s %8s   %6s" %
          (PM.DRUM_SETS.get(kit, kit), "dB", "t-40", "Standard", "dB", "t-40", "diff"))
    for note in sorted(PM.KITS[kit]):
        name = PM.KITS[kit][note][0]
        hold = 1.5 if note != 52 else 1.0
        a = measure(kit, note, hold)
        b = measure(0, note, hold)
        print("  %4d  %-18s %8.1f %7.2fs   %-16s %8.1f %7.2fs   %+6.1f%s" %
              (note, name, a[0], a[1], PM.PERCUSSION[note][0][:16], b[0], b[1],
               a[0] - b[0], "   (peak at %.2fs)" % a[2] if a[2] > 0.2 else ""))


if __name__ == "__main__":
    main()
