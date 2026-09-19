#!/usr/bin/env python3
"""An electric guitar: the drive sweep, and the calibration behind it.

    python3 examples/guitar.py [outdir]
    python3 examples/guitar.py --family [outdir]
    python3 examples/guitar.py --fret [outdir]
    python3 examples/guitar.py --calibrate

GM 27 is the first electric to have its own voice (see
tonelib.ElectricGuitarProperties), and what makes it one is not a body -- it is
two combs, a magnet and an amplifier. The colour arrives downstream of the
string, from tubeamp and cabinet.py, which is where it comes from on the real
instrument.

    string -> pluck comb -> pickup comb -> AMP -> CABINET -> room

THE SWEEP. The same passage at four drives, nothing else changed. Unlike the
Hammond, this voice sets `amp_reference`, so the drive is measured against a
FIXED level rather than against each segment's own peak -- which means playing
harder genuinely breaks up more, and the passage below is written to show it:
the same phrase is played softly and then dug into.

--calibrate reports the peak a hard chord actually produces, in the renderer's
own amplitude units, which is what `amp_reference` has to be for drive 1.0 to
mean "the edge of breakup when you hit it hard". It calls tubeamp.emit itself,
so the number is measured by the code it calibrates and cannot drift from it.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido
import numpy as np

import blockrender as B
import tubeamp as TA

DRIVES = (0.0, 1.0, 2.0, 4.0)
PROGRAM = 27            # GM 27, Electric Guitar (clean)
# The family, and what distinguishes each from the one before it. Every one is
# the same string and the same speaker; what changes is where the pickup is,
# how fast the palm takes the energy out, and how hard the valve is worked.
FAMILY = ((26, "jazz", "neck humbucker, picked soft"),
          (27, "clean", "middle single coil"),
          (28, "muted", "palm at the bridge: decay, not filtering"),
          (29, "overdriven", "bridge pickup, stage worked"),
          (30, "distortion", "bridge humbucker, past the bias"),
          (31, "harmonics", "a finger on the node at 1/2"))
TPB = 480
SR = 44100.0

# A six-string E-minor-ish voicing, low to high: the whole instrument at once,
# which is what a hard strum drives the amplifier with.
BIG_CHORD = (40, 47, 52, 55, 59, 64)


def _track(tempo=100, program=PROGRAM):
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(tempo), time=0))
    tr.append(mido.Message('program_change', program=program, channel=0, time=0))
    return m, tr


def _chord(tr, notes, beats, vel):
    n = int(TPB * beats)
    for p in notes:
        tr.append(mido.Message('note_on', note=p, velocity=vel, channel=0, time=0))
    for i, p in enumerate(notes):
        tr.append(mido.Message('note_off', note=p, velocity=0, channel=0,
                               time=n if i == 0 else 0))


FRET_PROGRAM = 120      # GM 120, Guitar Fret Noise -- NOT GM 31, which is a
                        # guitar HARMONIC (a finger on a node). This is the
                        # squeak a hand makes shifting position.


def fret(outdir):
    """A phrase with the shifts left in, which is what fret noise is for.

    On a real guitar track the squeaks are not decoration -- they are the
    evidence that a hand moved, and they land in the GAPS, during the shift,
    not on the notes. So the phrase plays in one position, shifts, and plays in
    another, with a squeak covering each shift on its own channel.

    Rendered under the same room and master as the sweep, a mid squeak sits
    about 27 dB under a hard-picked chord: present, never competing.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(96), time=0))
    tr.append(mido.Message('program_change', program=PROGRAM, channel=0, time=0))
    tr.append(mido.Message('program_change', program=FRET_PROGRAM, channel=1, time=0))
    # (tick, kind, note, vel, length): a low phrase, a shift, a high phrase,
    # a shift back. The squeaks sit IN the shifts.
    ev = []
    t = 0
    for p in (40, 43, 45, 47):                  # first position
        ev.append((t, 0, p, 96, 200)); t += 240
    # LOW, because that is where the wound strings are. The note no longer
    # sets the squeak's band -- that is fixed at the hand's speed -- so all it
    # does now is choose how much winding there is to ride over, and a squeak
    # written up at G5 is a plain treble string, i.e. almost silent.
    ev.append((t + 20, 1, 41, 120, 150))        # the shift up: a fast squeak
    t += 300
    for p in (64, 67, 69, 71):                  # up the neck
        ev.append((t, 0, p, 100, 200)); t += 240
    ev.append((t + 20, 1, 45, 96, 170))         # the shift back: slower, softer
    t += 320
    for p in (40, 47, 52, 55, 59, 64):          # and a chord, hand arrived
        ev.append((t, 0, p, 112, 900))
    msgs = []
    for tick, ch, note, vel, length in ev:
        msgs.append((tick, mido.Message('note_on', note=note, velocity=vel, channel=ch)))
        msgs.append((tick + length, mido.Message('note_off', note=note, velocity=0, channel=ch)))
    msgs.sort(key=lambda kv: kv[0])
    last = 0
    for tick, msg in msgs:
        msg.time = tick - last; last = tick
        tr.append(msg)
    # AND THE SAME THING SOLOED. This phrase is fourteen guitar notes and two
    # squeaks, which is the right proportion for a guitar part and the wrong
    # one for judging a squeak -- played together it sounds like a guitar,
    # because it mostly is one. Anything this quiet has to be listenable on its
    # own before a balance against it means anything; choral.py has
    # --choir-only for the same reason.
    env = dict(os.environ)
    env.setdefault('TUNING_ROOM', 'chamber')
    env.setdefault('TUNING_MASTER_DB', '-12')
    outs = []
    for tag, drop in (('guitar-fret', None), ('guitar-fret-squeaks', 0)):
        mm = mido.MidiFile(ticks_per_beat=TPB)
        t2 = mido.MidiTrack(); mm.tracks.append(t2)
        for msg in tr:
            if drop is not None and getattr(msg, 'channel', None) == drop \
                    and msg.type in ('note_on', 'note_off'):
                # keep the timing, drop the sound: a note-on at velocity 0
                msg = msg.copy(velocity=0) if msg.type == 'note_on' else msg
            t2.append(msg.copy())
        mid = os.path.join(outdir, tag + '.mid')
        mm.save(mid)
        out = mid[:-4] + '.wav'
        r = subprocess.run([sys.executable, os.path.join(root, 'blockrender.py'),
                            mid, out, 'even'], env=env, cwd=root,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:]); print(r.stderr[-2000:]); return 1
        outs.append(out)
        print("  %s" % out)
    print("  play the second one to judge the squeak; the first to judge the mix")
    return 0


def family(outdir):
    """The same passage on all six electrics, so they can be told apart.

    Each voice's own amp_drive is used -- no TUNING_AMP_DRIVE -- because the
    drive IS part of what distinguishes them, and overriding it would render
    six voices that differ only in their pickups.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for prog, name, why in FAMILY:
        mid = os.path.join(outdir, 'guitar-%d-%s.mid' % (prog, name))
        passage(prog).save(mid)
        out = mid[:-4] + '.wav'
        env = dict(os.environ)
        env.pop('TUNING_AMP_DRIVE', None)
        env.setdefault('TUNING_ROOM', 'chamber')
        env.setdefault('TUNING_MASTER_DB', '-12')
        t0 = time.time()
        r = subprocess.run([sys.executable,
                            os.path.join(root, 'blockrender.py'), mid, out,
                            'even'], env=env, cwd=root,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:]); print(r.stderr[-2000:]); return 1
        amp = [l for l in r.stdout.splitlines() if 'tube amp' in l]
        print("  %2d %-11s %-38s %4.1fs  %s"
              % (prog, name, why, time.time() - t0,
                 amp[0].split(',')[-1].strip() if amp else 'clean'))
    return 0


def passage(program=PROGRAM):
    """Single notes, then chords, then the same phrase soft and then dug into.

    The third section is the one this voice exists for: a guitar's dynamics go
    INTO the amplifier, so the quiet pass must be cleaner than the loud one
    without anything being changed but the velocity.
    """
    m, tr = _track(program=program)
    for p in (40, 47, 52, 55, 59, 64, 59, 55):      # a line, one note at a time
        _chord(tr, [p], 0.5, 100)
    _chord(tr, [40, 47, 52], 2.0, 100)              # a power chord: root, 5th, octave
    _chord(tr, [40, 44, 47], 2.0, 100)              # the same root with a MAJOR THIRD
    for vel in (45, 127):                           # soft, then dug in
        for p in (40, 47, 52, 55):
            _chord(tr, [p], 0.25, vel)
        _chord(tr, BIG_CHORD, 3.0, vel)
    return m


# What "played normally" means, per instrument. A guitar's is a six-string
# strum; a bass's is a low E with its octave, because a bass plays lines and
# not chords and calibrating it on a six-note voicing would set the reference
# to something it never does.
#
# AT VELOCITY 100, NOT 127, and that is the point of the number. drive 1.0 has
# to mean "the edge of breakup at NORMAL playing", so that digging in goes
# PAST it -- which is how an amplifier is set up: you put your usual touch
# where you want it and the hard notes exceed it. Calibrated at 127 instead,
# nominal drive was only reachable by playing as hard as MIDI can say, and
# every real file fell short: Riffsym writes all 727 of its notes at velocity
# 100, so its distortion guitars ran at 0.787 of nominal for ever.
CALIB_VEL = 100
CALIB = ((27, 'guitar', BIG_CHORD), (34, 'bass', (28, 40)))


def calibrate(outdir):
    """What peak does playing hard actually make, in renderer units?"""
    for prog, name, notes in CALIB:
        print("  %s (GM %d):" % (name, prog))
        _calib_one(outdir, prog, name, notes)
    return 0


def _calib_one(outdir, prog, name, notes):
    m, tr = _track(program=prog)
    _chord(tr, notes, 4.0, CALIB_VEL)
    path = os.path.join(outdir, '%s-calib.mid' % name)
    m.save(path)
    A = B.prepare(path, 'even')
    mch = np.asarray(A['mch'])
    rows = np.flatnonzero(mch == 0)
    # Direct sound only, as the amplifier pass does: a reflection is the room's
    # copy of what the valve already made, not another input to it.
    dl = (np.asarray(A['delL'], float)[rows]
          + np.asarray(A['delR'], float)[rows])
    rows = rows[dl <= dl.min() + 2.0]
    om = np.asarray(A['om'], float)[rows]
    aM = np.asarray(A['aM'], float)[rows]
    p0 = np.asarray(A['p0'], float)[rows]
    non = np.asarray(A['non'], float)[rows]
    a = int(np.median(non)) + int(0.05 * SR)     # just after the strum lands
    f = om * SR / (2.0 * np.pi)
    ph = p0 + om * a
    f, aM, ph = TA.combine(f, aM, ph)
    keep = np.argsort(-aM)[:TA.KEEP_PARTIALS]
    st = {}
    TA.emit(f[keep].tolist(), aM[keep].tolist(), ph[keep].tolist(), SR, 1.0,
            stats=st)
    print("    %d partials, %d distinct frequencies" % (len(rows), len(f)))
    print("    peak = %.6g   ->   amp_reference = %.6g" % (st['peak'], st['peak']))
    print("    (drive 1.0 then means the edge of breakup when it is hit that")
    print("     hard; a soft note reaches far less of the curve.)")
    return 0


def main(argv):
    if '--fret' in argv:
        i = argv.index('--fret')
        out = argv[i + 1] if len(argv) > i + 1 else '.'
        os.makedirs(out, exist_ok=True)
        return fret(out)
    if '--family' in argv:
        out = argv[argv.index('--family') + 1] if len(argv) > argv.index('--family') + 1 else '.'
        os.makedirs(out, exist_ok=True)
        return family(out)
    if '--calibrate' in argv:
        out = os.environ.get('TMPDIR', '/tmp')
        os.makedirs(out, exist_ok=True)
        return calibrate(out)
    outdir = argv[1] if len(argv) > 1 else '.'
    os.makedirs(outdir, exist_ok=True)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mid = os.path.join(outdir, 'guitar.mid')
    passage().save(mid)
    print("score: %s" % mid)
    for d in DRIVES:
        out = os.path.join(outdir, 'guitar-drive%g.wav' % d)
        env = dict(os.environ)
        env['TUNING_AMP_DRIVE'] = str(d)
        env.setdefault('TUNING_ROOM', 'chamber')
        env.setdefault('TUNING_MASTER_DB', '-12')
        t0 = time.time()
        r = subprocess.run([sys.executable,
                            os.path.join(root, 'blockrender.py'), mid, out,
                            'even'], env=env, cwd=root,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-3000:]); print(r.stderr[-3000:]); return 1
        note = [l.strip() for l in r.stdout.splitlines()
                if 'tube amp' in l or 'cabinet' in l]
        print("  drive %-4g %5.1fs  %s" % (d, time.time() - t0, "; ".join(note)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
