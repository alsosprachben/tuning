#!/usr/bin/env python3
"""The church organ's recorded ranks (bits 14-24), one registration at a time.

    python3 examples/organ_newstops_demo.py [OUTDIR]     # default ~/Downloads/organ_newstops

One short chorale phrase (four bars, four voices, its bass for the pedal
stops) played under each registration in turn, two seconds of silence
between, so each colour is heard alone: GM 19, the stop word written as the
file renderer reads it (CC11 | CC43<<7 | CC44<<14 | CC45<<21). The church at
Chorton's hybridmean, as the organ renders are.
"""
import os
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import tonelib as T  # noqa: E402

BIT = {r[0]: i for i, r in enumerate(T.FlueOrganProperties.stop_ranks)}


def word(*names):
    return sum(1 << BIT[n] for n in names)


# (label, manual stops, pedal stops or None)
REGS = [
    ("flute chorus 8 4 2", ("flute 8", "koppelflute 4", "waldflute 2"), None),
    ("sesquialtera solo over the flute 8", ("flute 8", "nazard 2-2/3", "tierce 1-3/5"), None),
    ("gamba 8", ("gamba 8",), None),
    ("gamba and celeste (they beat)", ("gamba 8", "celeste 8"), None),
    ("oboe 8", ("oboe 8",), None),
    ("vox humana with the tremulant", ("vox humana 8", "flute 8", "tremulant"), None),
    ("trompette 8", ("trompette 8",), None),
    ("principal 8 over the pedal's subbass 16", ("principal 8",), ("subbass 16",)),
    ("plenum over the pedal's 16 and 32", ("principal 8", "octave 4", "super octave 2", "mixture III"),
     ("subbass 16", "contrabassoon 32", "principal 8")),
]
# A Bach-ish chorale phrase in C: (soprano, alto, tenor), bass -- half notes
UPPER = [(72, 67, 64), (71, 67, 62), (69, 65, 60), (67, 64, 60), (69, 64, 60), (71, 67, 62),
         (72, 67, 64), (72, 67, 64)]
BASS = [48, 43, 41, 48, 45, 43, 36, 36]


def build(out):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    beat, half = 480, 960
    man, ped = mido.MidiTrack(), mido.MidiTrack()
    m.tracks += [man, ped]
    man.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 72), time=0))
    ev = {0: [], 1: []}
    t = 0
    for label, mstops, pstops in REGS:
        for ch, stops in ((0, mstops), (1, pstops or ())):
            w = word(*stops) if stops else 0
            for i, cc in enumerate((11, 43, 44, 45)):
                ev[ch].append((t, 0, mido.Message("control_change", channel=ch, control=cc,
                                                  value=(w >> (7 * i)) & 0x7F)))
        man_on = mstops is not None
        for k, (chord, b) in enumerate(zip(UPPER, BASS)):
            at = t + k * half + beat // 4
            for n in chord:
                ev[0] += [(at, 1, mido.Message("note_on", channel=0, note=n, velocity=80)),
                          (at + half - 30, 2, mido.Message("note_off", channel=0, note=n, velocity=0))]
            # the bass: on the manual when no pedal stop is drawn, else the pedal's
            ch = 1 if pstops else 0
            ev[ch] += [(at, 1, mido.Message("note_on", channel=ch, note=b, velocity=80)),
                       (at + half - 30, 2, mido.Message("note_off", channel=ch, note=b, velocity=0))]
        t += len(UPPER) * half + 2 * beat * 2
    for ch, tr in ((0, man), (1, ped)):
        tr.insert(0 if ch else 1, mido.Message("program_change", channel=ch, program=19, time=0))
        now = 0
        for at, _, msg in sorted(ev[ch], key=lambda e: (e[0], e[1])):
            tr.append(msg.copy(time=at - now)); now = at
    m.save(out)
    return [(label, i) for i, (label, _, _) in enumerate(REGS)]


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/organ_newstops")
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "newstops.mid")
    for label, i in build(mid):
        print("  %d  %s" % (i + 1, label))
    env = dict(os.environ, TUNING_ROOM="church", TUNING_WET="-3", TUNING_MASTER_DB="-12")
    P = lambda f: os.path.join(out, "newstops" + f)          # noqa: E731
    subprocess.check_call([sys.executable, os.path.join(HERE, "blockrender.py"), mid, P(".dry.wav"),
                           "hybridmean:466"], env=env)
    subprocess.check_call([sys.executable, os.path.join(HERE, "roomtail.py"), P(".dry.wav"), P(".wav")], env=env)
    subprocess.check_call(["sox", P(".wav"), P(".norm.wav"), "gain", "-n", "-1"])
    subprocess.check_call(["lame", "-b", "256", "--quiet", P(".norm.wav"), P(".mp3")])
    for f in (".dry.wav", ".dry.send.wav", ".norm.wav", ".wav"):
        if os.path.exists(P(f)):
            os.remove(P(f))
    print("  -> " + P(".mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
