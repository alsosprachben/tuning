#!/usr/bin/env python3
"""The harmonium's registers, one passage through each registration (GM 20).

    python3 examples/harmonium_registers_demo.py OUTDIR [--tree DIR]

A four-bar cadence in C -- the left hand in the bass half (to E4), a melody in
the treble (from F4), as a harmonium's split asks -- played once per
registration, in the chapel (TUNING_ROOM=church, 3 dB under the direct):

  1  Cor anglais + Flute            the foundation, both halves
  2  Bourdon 16 + Clarinette 16     the front organ's 16'
  3  Basson + Hautbois              the solo reeds
  4  Violoncelle + Musette          the Debain's other two (new)
  5  Sourdine + Hautbois            a treble solo over the muted bass (new)
  6  Cor anglais + Voix celeste     the celeste's two rows beating
  7  Cor anglais + Musette, Tremolo the Debain's tremolo on its Musette
  8  every reed

The stop word is CC43/44/45 (tonelib ReedOrganFreeProperties.stop_word_ccs),
sent at each section's start. --tree renders with another checkout's
blockrender (a before: its missing stops sound as nothing).
"""
import os
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import lib  # noqa: E402

REGS = [
    ("foundation", ["cor anglais 1", "flute 1"]),
    ("16 foot", ["bourdon 2", "clarinette 2"]),
    ("solo reeds", ["basson 4", "hautbois 4"]),
    ("violoncelle and musette", ["violoncelle", "musette"]),
    ("sourdine under hautbois", ["sourdine", "hautbois 4"]),
    ("celeste", ["cor anglais 1", "celeste"]),
    ("musette with tremolo", ["cor anglais 1", "musette", "tremolo"]),
    ("every reed", ["cor anglais 1", "bourdon 2", "clairon 3", "basson 4", "flute 1",
                    "clarinette 2", "fifre 3", "hautbois 4", "celeste", "violoncelle",
                    "sourdine", "musette"]),
]
# (beats, bass chord notes, melody notes [(beats, note)]) -- I vi IV V I
BARS = [
    ([48, 55, 60, 64], [(1, 76), (1, 79), (1, 77), (1, 76)]),
    ([45, 52, 57, 60], [(1.5, 72), (0.5, 74), (2, 76)]),
    ([41, 53, 57, 60], [(1, 77), (1, 81), (1, 79), (1, 77)]),
    ([43, 50, 55, 59], [(2, 74), (1, 71), (1, 74)]),
    ([36, 48, 55, 64], [(4, 72)]),
]
NAMES = ["cor anglais 1", "bourdon 2", "clairon 3", "basson 4", "flute 1", "clarinette 2",
         "fifre 3", "hautbois 4", "celeste", "expression", "percussion", "tremolo",
         "violoncelle", "sourdine", "musette"]
TPB, BPM = 480, 66


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0))
    t.append(mido.Message("program_change", channel=0, program=20, time=0))
    ev = []
    beat = 0.0
    for _, stops in REGS:
        w = sum(1 << NAMES.index(s) for s in stops)
        for i, cc in enumerate((43, 44, 45)):
            ev.append((beat - 0.25, 0, mido.Message("control_change", channel=0, control=cc,
                                                    value=(w >> (7 * i)) & 0x7F)))
        for chord, mel in BARS:
            for n in chord:
                ev.append((beat, 1, mido.Message("note_on", channel=0, note=n, velocity=90)))
                ev.append((beat + 3.9, 0, mido.Message("note_off", channel=0, note=n, velocity=0)))
            b = beat
            for d, n in mel:
                ev.append((b, 1, mido.Message("note_on", channel=0, note=n, velocity=90)))
                ev.append((b + d - 0.05, 0, mido.Message("note_off", channel=0, note=n, velocity=0)))
                b += d
            beat += 4
        beat += 2          # a breath between registrations
    ev.sort(key=lambda e: (e[0], e[1]))
    now = 0
    for b, _, msg in ev:
        tick = max(0, int(round(b * TPB)))
        msg.time = tick - now
        now = tick
        t.append(msg)
    m.save(path)


def main(argv):
    pos = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] != "--tree"]
    out = pos[0] if pos else os.path.expanduser("~/Downloads/harmonium_registers")
    tree = argv[argv.index("--tree") + 1] if "--tree" in argv else ROOT
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "harmonium_registers.mid")
    build(mid)
    stem = "harmonium_registers" + ("" if tree == ROOT else "_before")
    wav = os.path.join(out, stem + ".wav")
    env = dict(os.environ, TUNING_ROOM="church", TUNING_WET="-3", TUNING_MASTER_DB="-12")
    subprocess.check_call([sys.executable, os.path.join(tree, "blockrender.py"), mid, wav], env=env, cwd=tree)
    print("  ->", lib.mp3(wav))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
