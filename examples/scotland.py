#!/usr/bin/env python3
"""Scotland the Brave, from a sourced score, on the bagpipe voice.

    python3 examples/scotland.py [outdir]
    python3 examples/scotland.py --sharp [outdir]
    python3 examples/scotland.py --check

THE SCORE IS PARSED, NOT REMEMBERED. An earlier version of this file carried a
melody reconstructed from memory, which is exactly the habit this repo distrusts
everywhere else. The ABC below is quoted verbatim from the John Chambers
collection (trillian.mit.edu/~jc/music/abc, marked C:Trad., O:Scotland) and the
notes are read out of it by code, so the score is the source of truth and any
error is visible as text rather than hidden in a list of MIDI numbers.

OUT OF COPYRIGHT. The tune's earliest known printing is the Utah Musical
Bouquet, January 1878, so the melody has been public domain for a century. Cliff
Hanley's 1950 LYRICS are still in copyright and are not used -- this is the tune
alone.

IT IS THE SONG SETTING, AND A CHANTER CANNOT PLAY IT. That is not a defect of
the source; it is a fact about the instrument, and it is why a separate pipe
setting exists. Measured on the parsed notes:

    the song spans 16 semitones, D4 to F#5
    a Highland chanter spans 14, Low G to High A

Two semitones too wide, at every transposition -- and the chanter's scale fixes
the transposition anyway, since the tonic must land on Low A for the other eight
notes to fall on fingerholes. So the pipe version is an ADAPTATION, not a
transposition, and this file makes that adaptation mechanically: transpose up a
fifth, then take the nearest note the chanter actually has.

AND THE ADAPTATION CHECKS OUT AGAINST WHAT PIPERS PLAY. Three notes cannot be
taken literally, and all three land where the tradition puts them:

    C# -> G natural   the flat seventh, which is what a chanter has instead of
                      a leading tone, and what a piper plays there
    e, f -> High A    the top of the instrument

Which produces, without being told to, the one documented feature of the pipe
setting: IN THE BAGPIPE VERSION THE SECOND HALF STARTS ON THE TOP A. It does
here, from the mapping alone.

GRACE NOTES ARE THE ARTICULATION, NOT ORNAMENT. A bagpipe reed sounds
continuously -- no tonguing, no stopping, no way to put a gap between two notes
-- so two of the same note in a row would be ONE LONG NOTE. A piper separates
them by flicking a higher finger for a few milliseconds, and that flick is the
instrument's entire articulation. Every repeated pitch here gets one. After the
chanter mapping there are far more of them than the source has, because the
mapping folds distinct high notes onto the same High A.

THE DRONES belong to the part (tonelib.BagpipeProperties), so they sound under
the whole tune and the two tenors beat slowly against each other. CC1 corks
them. --sharp renders at the pitch a pipe band actually plays, around 470 Hz
for the chanter's A rather than 440, with the drones going sharp alongside,
since they are tuned to the chanter and not to a fork.
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import mido

# Verbatim from the John Chambers ABC collection. X:19009, R:Reel, C:Trad.,
# O:Scotland, M:2/4, L:1/8, Q:1/4=120, K:D. Header fields are recorded here and
# the parser below assumes them rather than reading them, which is why they are
# written out: if the source is ever replaced, these must be checked.
ABC_M, ABC_L, ABC_Q, ABC_K = "2/4", "1/8", 120, "D"
ABC = """
"D"D2 D3/2E1/2|FD FA|d2 "G"d3/2d1/2|"D"dA "D7"FD|"G"G2 B3/2G/2|"D"FA FD|"E7"E2 (A3/2B1/2)|"A7"AG FE|"D"D2 (D3/2E/2)|
FD FA|d2 "G"d3/2d1/2|"D"dA "D7"FD|"G"G2 B3/2G/2|"D"FA "Bm"FD|"E7"E2 "A7"D3/2D1/2|"D"D4||
"A7"e2 e3/2e1/2|ec A2|"D"d2 f3/2e1/2|dB A2|"Bm"d2 dd|"F#m"c2 dc|"E7"Bd cB|"A7"AG FE|
"D"D2 (D3/2E1/2)|FD FA|d2 "G"d3/2d1/2|"D"dA "D7"FD|"G"G2 B3/2G1/2|"D"FA "Bm"FD|"Em"E2 "A7"D3/2D1/2|"D"D4|
"""

# The nine notes of a Highland chanter, as MIDI. Low G, Low A, B, C#, D, E, F#,
# High G, High A. The High G is NATURAL -- there is no leading tone, which is
# the whole reason the song setting has to be adapted rather than transposed.
LG, LA, B, C, D, E, F, HG, HA = 67, 69, 71, 73, 74, 76, 78, 79, 81
CHANTER = (LG, LA, B, C, D, E, F, HG, HA)

_DEG = {'C': 60, 'D': 62, 'E': 64, 'F': 65, 'G': 67, 'A': 69, 'B': 71}


def parse_abc(abc=ABC):
    """The subset this tune uses: notes, lengths, bars, slurs, chord symbols."""
    s = re.sub(r'"[^"]*"', '', abc)              # chord symbols above the stave
    s = s.replace('(', '').replace(')', '').replace('\\', '')
    out = []
    for m in re.finditer(r'([A-Ga-g])(\d+/\d+|/\d+|\d+)?', s):
        letter, L = m.group(1), m.group(2)
        n = _DEG[letter.upper()] + (12 if letter.islower() else 0)
        if letter.upper() in ('F', 'C'):
            n += 1                                # K:D
        if L is None:
            d = 1.0
        elif L.startswith('/'):
            d = 1.0 / float(L[1:])
        elif '/' in L:
            a, b = L.split('/'); d = float(a) / float(b)
        else:
            d = float(L)
        out.append((n, d))                        # d in units of L:1/8
    return out


def to_chanter(n):
    """Up a fifth, so the tonic lands on Low A -- then the nearest fingerhole."""
    n += 7
    return min(CHANTER, key=lambda c: (abs(c - n), c))


def grace_for(pitch):
    """A piper flicks a finger ABOVE the note being separated."""
    if pitch >= HG:
        return HA
    if pitch <= B:
        return D
    return HG


def build(sharp=False):
    src = parse_abc()
    tune = [(to_chanter(n), d) for n, d in src]
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / ABC_Q), time=0))
    tr.append(mido.Message("program_change", channel=0, program=109, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    tr.append(mido.Message("control_change", channel=0, control=1, value=64, time=0))
    if sharp:
        tr.append(mido.Message("pitchwheel", channel=0, pitch=2730, time=0))

    EIGHTH = 240            # ticks, since L:1/8 and tpb=480 is a quarter
    GRACE = 26              # about 30 ms: a flick, not a note
    prev = None
    for pitch, d in tune:
        dur = int(EIGHTH * d)
        if prev == pitch:
            g = grace_for(pitch)
            tr.append(mido.Message("note_on", channel=0, note=g, velocity=96, time=0))
            tr.append(mido.Message("note_off", channel=0, note=g, velocity=0, time=GRACE))
            dur -= GRACE
        tr.append(mido.Message("note_on", channel=0, note=pitch, velocity=100, time=0))
        tr.append(mido.Message("note_off", channel=0, note=pitch, velocity=0, time=dur))
        prev = pitch
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    src = parse_abc()
    tune = [(to_chanter(n), d) for n, d in src]
    beats = sum(d for _, d in src)
    print("\n  parsed %d notes, %g eighths = %g bars of %s\n"
          % (len(src), beats, beats / 4, ABC_M))
    lo, hi = min(n for n, _ in src), max(n for n, _ in src)
    print("  the SONG setting spans MIDI %d to %d -- %d semitones" % (lo, hi, hi - lo))
    print("  a CHANTER spans %d to %d -- %d semitones" % (LG, HA, HA - LG))
    print("  so it is %d semitone(s) too wide, at any transposition, and the"
          % ((hi - lo) - (HA - LG)))
    print("  chanter's scale fixes the transposition anyway. It is an")
    print("  ADAPTATION, not a transposition.\n")
    moved = sorted({(a, to_chanter(a)) for a, _ in src if a + 7 != to_chanter(a)})
    print("  the notes a chanter cannot take literally, and where they go:")
    names = {79: "High G (the flat seventh)", 81: "High A (the top)"}
    for s_, d_ in moved:
        print("    %3d  (+7 = %3d)  ->  %3d   %s" % (s_, s_ + 7, d_, names.get(d_, "")))
    assert all(n in CHANTER for n, _ in tune)
    print("\n  every note is on the chanter after mapping.")
    # the one documented feature of the pipe setting
    acc, idx = 0.0, 0
    for i, (_, d) in enumerate(src):
        acc += d
        if acc >= 64:                    # 16 bars of 2/4
            idx = i + 1
            break
    print("\n  the second half begins on MIDI %d, and High A is %d."
          % (tune[idx][0], HA))
    print("  Documented of the pipe setting: \"the second half starts on the")
    print("  top A\". It does, from the mapping alone -- nothing here was told.")
    reps = sum(1 for i in range(1, len(tune)) if tune[i][0] == tune[i - 1][0])
    print("\n  %d repeated pitches need a grace note to be heard as two notes"
          % reps)
    print("  (the source has %d; the mapping folds high notes onto High A)"
          % sum(1 for i in range(1, len(src)) if src[i][0] == src[i - 1][0]))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    sharp = "--sharp" in argv
    argv = [a for a in argv if a != "--sharp"]
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    tag = "scotland-sharp" if sharp else "scotland"
    mid = os.path.join(outdir, tag + ".mid")
    out = os.path.join(outdir, tag + ".wav")
    build(sharp).save(mid)
    env = dict(os.environ)
    env.setdefault("TUNING_ROOM", "hall")        # pipes are an outdoor instrument
    env.setdefault("TUNING_MASTER_DB", "-12")
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "blockrender.py"),
                        mid, out, "even"], env=env, cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:]); return 1
    print("  %5.1fs -> %s" % (time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
