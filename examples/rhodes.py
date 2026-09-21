#!/usr/bin/env python3
"""The electric pianos: the voicing screw, and what velocity really does.

    python3 examples/rhodes.py [outdir]
    python3 examples/rhodes.py --voicing [outdir]
    python3 examples/rhodes.py --velocity [outdir]
    python3 examples/rhodes.py --control [outdir]
    python3 examples/rhodes.py --tremolo [outdir]
    python3 examples/rhodes.py --pair [outdir]

GM 4 rendered as a Steinway B until now, which is wrong in every particular: a
Rhodes has no strings, no soundboard and no unison trios. It is a struck steel
tine read by a magnetic pickup, and -- measured with a high-speed camera at
38 kfps -- the tine vibrates as a PURE SINE. Every harmonic you hear is made by
the pickup. See tonelib.ElectricPianoProperties and sources.md.

    tine (one sine) -> PICKUP WAVESHAPER -> cabinet -> room

--voicing is the falsifiable one, and the reason to build this script rather
than just listen. The tine's rest position in the magnet's field is the one
adjustment a technician makes on the real instrument, and the measurements say
that with the tine CENTRED the fundamental disappears and the pickup answers an
octave up. This renders the same passage at four offsets so that can be heard
happening, from a hollow octave to a full fundamental.

--velocity plays one phrase at four velocities. The claim under test is the
paper's: "velocity sensitivity is to be distinguished by a change in volume to
lesser extent than in sound". The growl should arrive faster than the loudness.

--pair renders the same passage on both electric pianos, which is the point
of having two: they share one mechanism and differ only in the pickup's curve.
A Rhodes' magnet is a bell curve, so its harmonics fall off a cliff -- bell. A
Wurlitzer's plate is a capacitor and its capacitance goes as 1/d, which is a
pole, so they fall off geometrically at about 9 dB a harmonic -- bark. Nothing
else is changed between the two renders except the curve, the speaker and the
fact that a Wurlitzer has no tonebar.

--tremolo puts the wheel up. The suitcase's panel calls it vibrato and it is
not one -- it is a stereo PAN between the cabinet's two amplifiers, so it is
audible in the room and vanishes entirely if you sum to mono. CC1 sets depth,
which is the panel's own control; a file with no CC1 gets none, because that is
where the knob sits when nobody has touched it.

--control renders with the waveshaper bypassed -- the tine alone, a pure sine.
Nothing about the harmonics means anything until this one is confirmed dull.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido

PROGRAM = 4             # GM 4, Electric Piano 1
WURLITZER = 5           # GM 5, Electric Piano 2
TPB = 480

# The voicing screw, in units of the magnet's field width. 0.0 is the measured
# extreme: a symmetric field crossed twice a cycle answers at twice the pitch.
VOICINGS = (0.0, 0.10, 0.30, 0.60)
VELOCITIES = (35, 65, 95, 127)


def _render(mid, out, env, root):
    r = subprocess.run([sys.executable, os.path.join(root, 'blockrender.py'),
                        mid, out], env=env, cwd=root,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        return None
    return r.stdout


def _env():
    env = dict(os.environ)
    env.setdefault('TUNING_ROOM', 'chamber')
    env.setdefault('TUNING_MASTER_DB', '-12')
    return env


def passage(velocity=None, program=PROGRAM):
    """A Rhodes figure: soft chords, then the same thing dug into.

    Written low-to-middle on purpose. The growl is a bass-register effect --
    "best audible in the lower register where the tines have a larger
    deflection" -- so a part written in the top octave would hide the very
    thing this voice was built to get right.
    """
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.Message('program_change', program=program, channel=0, time=0))
    ev = []
    # Fmaj7 - Bb9 - Ebmaj7 - Abmaj7, twice: once soft, once dug into.
    chords = (((41, 57, 60, 64), 0), ((46, 58, 62, 65), 1),
              ((39, 55, 58, 62), 2), ((44, 56, 60, 63), 3))
    for rep, vel in enumerate((55, 112) if velocity is None else (velocity, velocity)):
        for notes, beat in chords:
            t = (rep * 4 + beat) * TPB
            for i, n in enumerate(notes):
                # rolled a little, as a hand lands
                ev.append((t + i * 9, mido.Message('note_on', note=n, velocity=vel, channel=0)))
                ev.append((t + TPB - 30, mido.Message('note_off', note=n, velocity=0, channel=0)))
    # and a tail to hear the growl decay into the bell
    ev.append((8 * TPB, mido.Message('note_on', note=41, velocity=120, channel=0)))
    ev.append((8 * TPB + 6 * TPB, mido.Message('note_off', note=41, velocity=0, channel=0)))
    ev.sort(key=lambda kv: kv[0])
    last = 0
    for tick, msg in ev:
        msg.time = tick - last; last = tick
        tr.append(msg)
    return m


def voicing(outdir):
    """The same passage at four tine positions. The claim is audible at 0.00."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for off in VOICINGS:
        mid = os.path.join(outdir, 'rhodes-voicing-%.2f.mid' % off)
        passage().save(mid)
        out = mid[:-4] + '.wav'
        env = _env(); env['TUNING_EP_VOICING'] = '%g' % off
        t0 = time.time()
        if _render(mid, out, env, root) is None:
            return 1
        print("  %.2f  %-44s %4.1fs%s" % (off, out, time.time() - t0,
              "   <- centred: the fundamental should be gone" if off == 0.0 else ""))
    return 0


def velocity(outdir):
    """One phrase at four velocities: the growl should outrun the loudness."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for vel in VELOCITIES:
        mid = os.path.join(outdir, 'rhodes-vel-%03d.mid' % vel)
        passage(vel).save(mid)
        out = mid[:-4] + '.wav'
        t0 = time.time()
        if _render(mid, out, _env(), root) is None:
            return 1
        print("  v%-3d  %-44s %4.1fs" % (vel, out, time.time() - t0))
    return 0


def tremolo(outdir):
    """The wheel up, at three depths. A pan, so listen in the room, not in mono."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cc in (0, 48, 96, 127):
        m = passage()
        tr = m.tracks[0]
        tr.insert(1, mido.Message('control_change', control=1, value=cc,
                                  channel=0, time=0))
        mid = os.path.join(outdir, 'rhodes-trem-%03d.mid' % cc)
        m.save(mid)
        out = mid[:-4] + '.wav'
        if _render(mid, out, _env(), root) is None:
            return 1
        print("  CC1 %3d   %-44s%s" % (cc, out, "   <- the panel's rest position"
                                       if cc == 0 else ""))
    return 0


def pair(outdir):
    """Both electric pianos, same passage. One mechanism, two curves."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for prog, name, why in ((PROGRAM, 'rhodes', 'magnetic, a bell curve: harmonics fall off a cliff'),
                            (WURLITZER, 'wurlitzer', 'electrostatic 1/d, a pole: they fall off geometrically')):
        mid = os.path.join(outdir, 'ep-%d-%s.mid' % (prog, name))
        passage(program=prog).save(mid)
        out = mid[:-4] + '.wav'
        t0 = time.time()
        if _render(mid, out, _env(), root) is None:
            return 1
        print("  %-10s %-44s %4.1fs   %s" % (name, out, time.time() - t0, why))
    return 0


def control(outdir):
    """The tine on its own. Confirm this is dull before believing anything else.

    A pickup that does not bend is not a pickup: a linear flux hands back the
    sine it was given. If this render has harmonics in it, the harmonics in the
    others are not coming from where this voice says they are.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outs = []
    for tag, ctl in (('rhodes-control', '1'), ('rhodes-control-off', '0')):
        mid = os.path.join(outdir, tag + '.mid')
        passage().save(mid)
        out = mid[:-4] + '.wav'
        env = _env(); env['TUNING_EP_CONTROL'] = ctl
        if _render(mid, out, env, root) is None:
            return 1
        outs.append(out)
        print("  %-46s %s" % (out, "waveshaper BYPASSED" if ctl == '1' else "the voice"))
    print("  the first must be dull; if it is not, nothing else here is evidence")
    return 0


def main(argv):
    mode = None
    args = [a for a in argv[1:] if not a.startswith('--')]
    for a in argv[1:]:
        if a.startswith('--'):
            mode = a[2:]
    outdir = args[0] if args else os.path.expanduser('~/Downloads/rhodes')
    os.makedirs(outdir, exist_ok=True)
    if mode == 'voicing':
        return voicing(outdir)
    if mode == 'velocity':
        return velocity(outdir)
    if mode == 'control':
        return control(outdir)
    if mode == 'tremolo':
        return tremolo(outdir)
    if mode == 'pair':
        return pair(outdir)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mid = os.path.join(outdir, 'rhodes.mid')
    passage().save(mid)
    out = mid[:-4] + '.wav'
    t0 = time.time()
    if _render(mid, out, _env(), root) is None:
        return 1
    print("  %s  %.1fs" % (out, time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
