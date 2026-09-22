#!/usr/bin/env python3
"""Scotland the Brave, on the bagpipe voice.

    python3 examples/scotland.py [outdir]

THE MELODY IS RECONSTRUCTED FROM MEMORY and is a common setting rather than a
sourced one; the rhythm and contour are right and a piper would quarrel with
details. Anything here is easy to correct -- the tune is one list below.

The point of the file is the VOICE, and three things about it are worth seeing
on a real tune rather than on a scale.

THE NINE NOTES. A Highland chanter has nine and no more: Low G, Low A, B, C#,
D, E, F#, High G, High A. There is no chromaticism, no octave key and no way to
play outside them, which is why pipe tunes are shaped the way they are and why
a fixed drone is not a limitation. Every note below is checked against that set.

GRACE NOTES ARE THE ARTICULATION, NOT ORNAMENT. This is the part a transcription
usually loses. A bagpipe reed sounds continuously -- there is no tonguing, no
stopping and no way to put a gap between two notes -- so TWO OF THE SAME NOTE IN
A ROW WOULD BE ONE LONG NOTE. A piper separates them by flicking a higher finger
for a few milliseconds, and that flick is the only articulation the instrument
has. Every repeated pitch here gets one, because without it the tune is wrong in
a way that has nothing to do with taste.

The doubling on a strong beat is the same device used for emphasis rather than
for separation, and the birl and the throw are longer versions of it. Only the
single grace note is used here: it is what the tune cannot do without.

THE DRONES belong to the part (see tonelib.BagpipeProperties), so they sound
under the whole tune from the first note to the last, and the two tenors beat
slowly against each other -- drone lock. CC1 corks them: 0 for the chanter
alone, 64 for the voiced default.

PITCH. A real chanter sounds around 470-480 Hz for its "A", well sharp of
concert, and the drones are tuned to the chanter rather than to a fork. This
renders at concert pitch so it sits with everything else in the bank; --sharp
renders it where a pipe band actually plays, drones and all.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import mido

# The chanter, as MIDI notes. Low A is written A and sounds nearer B flat.
LG, LA, B, C, D, E, F, HG, HA = 67, 69, 71, 73, 74, 76, 78, 79, 81
CHANTER = {LG, LA, B, C, D, E, F, HG, HA}

# (pitch, beats). A march: heavily dotted, which is most of the character.
TUNE = [
    # Hark! when the night is falling
    (LA, .5),
    (D, .75), (B, .25), (D, .5), (B, .5), (LA, 1),
    (F, .75), (LA, .25), (F, .5), (LA, .5), (D, 1),
    # hear, hear the pipes are calling
    (E, .75), (D, .25), (E, .5), (F, .5), (HG, 1),
    (F, .75), (D, .25), (E, 1.5),
    # loudly and proudly calling
    (D, .75), (B, .25), (D, .5), (B, .5), (LA, 1),
    (F, .75), (LA, .25), (F, .5), (LA, .5), (D, 1),
    # down through the glen
    (E, .75), (F, .25), (HG, .5), (E, .5), (D, 1),
    (B, .75), (LA, .25), (LA, 2),
    # There where the hills are sleeping
    (D, .75), (E, .25), (F, .5), (HG, .5), (HA, 1),
    (HG, .75), (F, .25), (E, .5), (D, .5), (B, 1),
    (D, .75), (B, .25), (D, .5), (E, .5), (F, 1),
    (E, .75), (D, .25), (B, 1.5),
    # now feel the blood a-leaping
    (LA, .75), (B, .25), (D, .5), (F, .5), (E, 1),
    (D, .75), (B, .25), (LA, .5), (F, .5), (LA, 1),
    (D, .75), (E, .25), (F, .5), (E, .5), (D, 1),
    (B, .75), (LA, .25), (LA, 2),
]

# THE GRACE NOTE FOR A GIVEN MELODY NOTE. A piper flicks a finger ABOVE the note
# being separated -- high G over most of the scale, high A over high G, and D
# over the bottom of it. The exact choice is idiomatic; what matters is that it
# is higher than the note and very short.
def grace_for(pitch):
    if pitch >= HG:
        return HA
    if pitch <= B:
        return D
    return HG


def build(sharp=False):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=545000, time=0))   # a march
    tr.append(mido.Message("program_change", channel=0, program=109, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    # CC1 64: the drones as voiced. 0 would cork them.
    tr.append(mido.Message("control_change", channel=0, control=1, value=64, time=0))
    if sharp:
        # A real chanter's A is nearer 470 Hz than 440. Pitch bend is a whole
        # channel offset, so the drones go sharp with it -- which is right,
        # since they are tuned to the chanter and not to a fork.
        tr.append(mido.Message("pitchwheel", channel=0, pitch=2730, time=0))  # ~+2/3 tone

    GRACE = 26          # ticks: about 30 ms at this tempo. A flick, not a note.
    prev = None
    pending = 0         # ticks of rest owed to the next event
    for pitch, beats in TUNE:
        assert pitch in CHANTER, "note %d is not on the chanter" % pitch
        dur = int(480 * beats)
        # A REPEATED PITCH MUST BE SEPARATED, because the reed never stops.
        if prev == pitch:
            g = grace_for(pitch)
            tr.append(mido.Message("note_on", channel=0, note=g, velocity=96, time=pending))
            tr.append(mido.Message("note_off", channel=0, note=g, velocity=0, time=GRACE))
            pending = 0
            dur -= GRACE
        tr.append(mido.Message("note_on", channel=0, note=pitch, velocity=100, time=pending))
        tr.append(mido.Message("note_off", channel=0, note=pitch, velocity=0, time=dur))
        pending = 0
        prev = pitch
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def main(argv):
    sharp = "--sharp" in argv
    argv = [a for a in argv if a != "--sharp"]
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    tag = "scotland-sharp" if sharp else "scotland"
    mid = os.path.join(outdir, tag + ".mid")
    out = os.path.join(outdir, tag + ".wav")
    build(sharp).save(mid)
    n = sum(1 for _ in TUNE)
    reps = sum(1 for i in range(1, len(TUNE)) if TUNE[i][0] == TUNE[i - 1][0])
    print("  %d notes, %d of them repeated pitches that needed a grace note" % (n, reps))
    env = dict(os.environ)
    env.setdefault("TUNING_ROOM", "hall")       # pipes are an outdoor instrument
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
