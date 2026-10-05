#!/usr/bin/env python3
"""Wagner, Die Walkuere: the Ride of the Valkyries -- from BitMidi to an mp3.

    python3 examples/valkyries.py [OUTDIR]     # default ~/Downloads/valkyries

Played straight, as the September renders were (their scripts lived in a
scratch directory and were lost with it): the file's own notes, velocities and
controllers, with two programs corrected -- the brass channel was on Synth
Brass 2, the contrabass on String Ensemble. Also written: the strings alone
(the first and second strings and the basses), so the sweeps can be heard
without the brass over them.

THE SWEEPS are the strings' rapid figures, written as streams of very short
notes: 88% of the first strings' notes are under 120 ms (median 55 ms), and
at tpb 48 about half follow the last with no gap or one of a tick or two. So
what they sound like is the ONSET of a tiny note on a bowed section: the slur
rule (a note contiguous in ticks with the one before -- gap <= max(1,
tpb/64) -- gets a 12 ms onset instead of 100), the per-register measured
bodies with their crossfades, and each player's own vibrato.

The hall at -3 dB wet ("the 3 dB target seems to work well"); hybridmean at
A = 440 (the September renders were plain hybrid, at the baroque 415).
"""
import os
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://bitmidi.com/uploads/31411.mid"
ROOM, WET, TUNER, MASTER_DB = "hall", "-3", "hybridmean:440", "-12"
FIX = {2: (63, 61, "the brass was on Synth Brass 2"),
       5: (48, 43, "the contrabass was on String Ensemble")}
STRINGS = (0, 1, 5)            # Strings I, Strings II (tremolo), contrabass


def run(cmd, env=None):
    print("  $ " + " ".join(cmd))
    subprocess.check_call(cmd, env=dict(os.environ, **(env or {})))


def fixed(src, dst):
    """The two programs corrected, and the file's REVERB SENDS DROPPED. This
    renderer reads CC91 as a distance (CC91/40 times the nominal one), and the
    file's sequencer set 64-100 everywhere -- every section 1.6 to 2.5 times
    farther back, the brass furthest -- written for a GM synth's reverb knob.
    In the hall that was boomy (Ben: "It is very boomy"); without them every
    section stands at the hall's own distance."""
    m = mido.MidiFile(src)
    for tr in m.tracks:
        out, carry = mido.MidiTrack(), 0
        for msg in tr:
            if msg.type == 'program_change' and msg.channel in FIX and msg.program == FIX[msg.channel][0]:
                msg.program = FIX[msg.channel][1]
            if msg.type == 'control_change' and msg.control == 91:
                carry += msg.time
                continue
            out.append(msg.copy(time=msg.time + carry))
            carry = 0
        tr[:] = out
    m.save(dst)


def only_channels(src, dst, keep):
    """Every track, with the channel messages of other channels taken out (the
    time they carried passed on) -- tempo and meta stay."""
    m = mido.MidiFile(src)
    for tr in m.tracks:
        out, carry = mido.MidiTrack(), 0
        for msg in tr:
            if not msg.is_meta and hasattr(msg, 'channel') and msg.channel not in keep:
                carry += msg.time
                continue
            out.append(msg.copy(time=msg.time + carry))
            carry = 0
        tr[:] = out
    m.save(dst)


def render(mid, name, out):
    env = {"TUNING_ROOM": ROOM, "TUNING_WET": WET, "TUNING_MASTER_DB": MASTER_DB}
    P = lambda f: os.path.join(out, f)            # noqa: E731
    run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, P(name + ".dry.wav"), TUNER], env)
    run([sys.executable, os.path.join(HERE, "roomtail.py"), P(name + ".dry.wav"), P(name + ".wav")], env)
    run(["sox", P(name + ".wav"), P(name + ".norm.wav"), "gain", "-n", "-1"])
    run(["lame", "-b", "320", "-h", "--quiet", "--tt", "Ride of the Valkyries" + (
        " (strings)" if "strings" in name else ""), "--ta", "Wagner", "--tl", "Die Walkuere",
        P(name + ".norm.wav"), P(name + ".mp3")])
    for f in (name + ".dry.wav", name + ".norm.wav", name + ".dry.room.json", name + ".dry.send.wav"):
        if os.path.exists(P(f)):
            os.remove(P(f))
    print("  -> %s" % P(name + ".mp3"))


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/valkyries")
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "wag_valk_bm.mid")
    if not os.path.exists(src):
        run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", src, URL])
    mid = os.path.join(out, "valkyries.mid")
    fixed(src, mid)
    strings = os.path.join(out, "valkyries_strings.mid")
    only_channels(mid, strings, STRINGS)
    render(mid, "valkyries", out)
    render(strings, "valkyries_strings", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
