#!/usr/bin/env python3
"""How loud each voice actually is, measured from rendered audio.

Run: python3 examples/levels.py            # the plucked family
     python3 examples/levels.py --all      # every program in the table

This script exists because of an error that survived for months and was caught
by Ben's ear rather than by anything in the repo: the electric bass was 23 dB
too quiet. Fourteen voices inherited PluckedStringProperties' generic
initial_gain = 0.02 and were never balance-normalised against anything, so the
family spanned 41 dB between its loudest and quietest member.

Nothing in the selftest suite measured absolute level. It has dozens of checks
on spectrum -- where a comb nulls, how fast a partial decays, which intervals
survive overdrive -- and on relationships between voices, and not one on how
loud a voice is. A voice could have been inaudible and every check would pass.

IT RENDERS. An earlier version of this script estimated level arithmetically
from the partial series at onset, which is far cheaper and was wrong by up to
80 dB: a bowed voice has almost no onset, the amplifier and cabinet are not in
the series, and max_harmonic truncates differently per voice. The whole point
of this measurement is to answer to something outside the model, so it measures
the audio the renderer actually produces.

A voice is measured in ITS OWN register against the grand piano playing the
same notes -- comparing a bass to a guitar at the same pitch measures the
register, not the voice.
"""
import argparse
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import mido
import numpy as np

import lib as _unused_guard  # noqa: F401  (examples/ is on the path)

VEL = 100                       # what Riffsym writes, and a normal touch
GUITAR_NOTES = (40, 52, 64)     # E2 E3 E4
BASS_NOTES = (28, 33, 40)       # E1 A1 E2
PIANO = 0

# GM number, label, register. The two MEASURED members are the anchors: the
# nylon guitar and the contrabass were fitted against recordings, so they are
# the only levels in the family that answer to something outside the model,
# and everything else is placed relative to them.
FAMILY = [
    (24, "Nylon guitar (measured)", GUITAR_NOTES),
    (25, "Steel guitar", GUITAR_NOTES),
    (26, "Jazz guitar", GUITAR_NOTES),
    (27, "Electric guitar", GUITAR_NOTES),
    (28, "Muted guitar", GUITAR_NOTES),
    (29, "Overdriven guitar", GUITAR_NOTES),
    (30, "Distortion guitar", GUITAR_NOTES),
    (31, "Harmonics", GUITAR_NOTES),
    (32, "Acoustic bass", BASS_NOTES),
    (33, "Bass finger", BASS_NOTES),
    (34, "Bass pick", BASS_NOTES),
    (35, "Fretless bass", BASS_NOTES),
    (36, "Slap bass", BASS_NOTES),
    (37, "Pop bass", BASS_NOTES),
    (43, "Contrabass (measured)", BASS_NOTES),
]


def one_note_midi(path, program, notes, vel=VEL, beats=2):
    """One note per bar at one velocity -- the whole register in one file."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=1000000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    # PIN THE CHANNEL VOLUME, rather than inherit whatever the renderer's
    # default happens to be. This measurement is a RATIO against the piano, so
    # a change in the default ought to cancel -- and it does not, because the
    # yardstick is not linear in it. A piano's phantom sum-tones go as the
    # PRODUCT of two partial amplitudes, so halving the source quarters them;
    # an amped voice slides down its valve curve and compresses less. Measured,
    # moving the default from 127 to GM's 100 moved this table by +1.0 dB on the
    # nylon guitar and +3.3 on the slap bass -- not a uniform shift, and nothing
    # about the instruments had changed.
    #
    # So the condition is stated here instead of assumed: full scale, where no
    # non-linear term is being exercised by the apparatus itself.
    tr.append(mido.Message("control_change", channel=0, control=7, value=127, time=0))
    tr.append(mido.Message("control_change", channel=0, control=11, value=127, time=0))
    for n in notes:
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=vel, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0,
                               time=480 * beats))
    tr.append(mido.MetaMessage("end_of_track", time=480))
    m.save(path)
    return path


def render(midi, out):
    subprocess.run([sys.executable, os.path.join(ROOT, "blockrender.py"),
                    midi, out, "even"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def note_rms(path, notes, beats=2, window=0.5):
    """RMS of the first `window` seconds of each note, averaged over notes.

    The window starts at the note's onset, which at 1 s per beat is
    i * beats seconds in. Measuring the whole file instead would weight the
    result by how fast each voice decays, which is a separate property.
    """
    w = wave.open(path, "rb")
    sr, ch, sw, n = (w.getframerate(), w.getnchannels(),
                     w.getsampwidth(), w.getnframes())
    raw = w.readframes(n)
    w.close()
    # blockrender writes 32-bit PCM; do not assume 16.
    dt = {1: np.uint8, 2: np.int16, 4: np.int32}[sw]
    a = np.frombuffer(raw, dtype=dt).astype(np.float64)
    if sw == 1:
        a -= 128.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    out = []
    for i in range(len(notes)):
        s0 = int(i * beats * sr)
        e0 = min(int((i * beats + window) * sr), len(a))
        if s0 >= len(a):
            break
        seg = a[s0:e0]
        if seg.size:
            out.append(float(np.sqrt((seg * seg).mean())))
    return sum(out) / len(out) if out else 0.0


def measure(program, notes, tmp):
    mid = os.path.join(tmp, "p%d.mid" % program)
    wav = os.path.join(tmp, "p%d.wav" % program)
    one_note_midi(mid, program, notes)
    render(mid, wav)
    return note_rms(wav, notes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="every program 0-127, not just the plucked family")
    args = ap.parse_args()

    rows = FAMILY
    if args.all:
        rows = [(p, "program %d" % p, GUITAR_NOTES) for p in range(128)]

    with tempfile.TemporaryDirectory() as tmp:
        # The reference is the grand piano in each register, rendered once.
        ref = {}
        for reg in {r[2] for r in rows}:
            ref[reg] = measure(PIANO, reg, tmp)

        print("  rendered level against the grand piano in the same register, "
              "velocity %d:\n" % VEL)
        print("   GM  voice                          dB")
        got = []
        for gm, label, reg in rows:
            v = measure(gm, reg, tmp)
            db = 20.0 * math.log10(max(v, 1e-9) / max(ref[reg], 1e-9))
            got.append((gm, label, db))
            print("   %2d  %-28s %6.1f" % (gm, label, db))

    if got:
        lo = min(got, key=lambda r: r[2])
        hi = max(got, key=lambda r: r[2])
        print("\n  spread %.1f dB, %s at %.1f to %s at %.1f"
              % (hi[2] - lo[2], lo[1], lo[2], hi[1], hi[2]))


if __name__ == "__main__":
    main()
