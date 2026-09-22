#!/usr/bin/env python3
"""An electric grand, and the acoustic one it used to be.

    python3 examples/grand.py [outdir]
    python3 examples/grand.py --compare [outdir]
    python3 examples/grand.py --register [outdir]

GM 2 was the acoustic grand -- the same class object, not even a subclass. A
Yamaha CP-70 has a real grand action and real strings with NO SOUNDBOARD and a
piezo under the bridge, and it is short: its bass strings are a twelfth as
stiff-tuned again as a concert grand's. See tonelib.ElectricGrandProperties.

--register IS THE TEST, and it is built to be able to fail. The derivation says
the two pianos' STRINGS differ only where the shorter case binds -- below about
154 Hz, which is D#3 -- and are the same length above it. So this renders one
figure twice: once in the bottom octave and a half and once two octaves up.

It also separates the voice's two claims, which is the useful part. Measured on
these renders, subtracting one piano from the other leaves:

    low    waveform correlation +0.353   residual  +1.1 dB
    high   waveform correlation +0.998   residual -14.7 dB

Low, the difference is as loud as the signal: that is the stretch, up to twelve
times a concert grand's. High, where the stretch is identical by construction,
what is left over is the OTHER change on its own -- the soundboard replaced by a
bridge pickup, which applies at every pitch. If the high pair showed a stretch
difference the scaling argument would be wrong; a residual at that level is the
board.

--compare plays a whole passage on both. Written low on purpose: a CP-70 part
that stays above D#3 is a demo of nothing.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido

ELECTRIC = 2
ACOUSTIC = 0
TPB = 480
TICKS_S = TPB * 2          # 120 bpm


def _env():
    env = dict(os.environ)
    env.setdefault('TUNING_ROOM', 'chamber')
    env.setdefault('TUNING_MASTER_DB', '-14')
    return env


def _render(mid, out, root):
    r = subprocess.run([sys.executable, os.path.join(root, 'blockrender.py'), mid, out],
                       env=_env(), cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        return None
    return r.stdout


def _track(program, ev, tail_s=6.0):
    """blockrender sizes a render as the MIDI plus one second, and a piano rings
    for longer than that. A silent event at the end buys the tail back."""
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.Message('program_change', program=program, channel=0, time=0))
    ev = sorted(ev, key=lambda kv: kv[0])
    ev = ev + [(ev[-1][0] + int(tail_s * TICKS_S),
                mido.Message('note_off', note=1, velocity=0, channel=0))]
    last = 0
    for tick, msg in ev:
        msg.time = tick - last; last = tick
        tr.append(msg)
    return m


def _notes(spec, shift=0):
    ev = []
    for beat, notes, vel, length in spec:
        t = int(beat * TPB)
        for n in notes:
            ev.append((t, mido.Message('note_on', note=n + shift, velocity=vel, channel=0)))
            ev.append((t + int(length * TPB),
                       mido.Message('note_off', note=n + shift, velocity=0, channel=0)))
    return ev


# A CP-70 part: octaves and fifths low down, which is where the instrument was
# used and -- not coincidentally -- the only register where it differs at all.
RIFF = [(0.0, (28, 40), 112, 0.9), (1.0, (28, 40), 78, 0.4),
        (1.5, (35, 47), 96, 0.9), (2.5, (33, 45), 88, 0.4),
        (3.0, (28, 40), 118, 1.4), (4.5, (31, 43), 100, 0.9),
        (5.5, (33, 45), 94, 0.4), (6.0, (26, 38), 120, 2.4)]


def passage(program=ELECTRIC):
    ev = _notes(RIFF)
    # then a sustained low chord, to hear the bass a soundboard cannot radiate
    t = 9.5
    ev += _notes([(t, (26, 33, 38, 45), 104, 3.2)])
    # and a mid-register answer, which should sound like any piano
    ev += _notes([(13.5, (57, 60, 64), 92, 1.4), (15.0, (55, 59, 62), 88, 2.4)])
    return _track(program, ev)


def compare(outdir):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for prog, name, why in ((ELECTRIC, 'electric', 'short strings, no board, bridge piezo'),
                            (ACOUSTIC, 'acoustic', 'a Steinway B with a soundboard')):
        mid = os.path.join(outdir, 'grand-%s.mid' % name)
        passage(prog).save(mid)
        out = mid[:-4] + '.wav'
        t0 = time.time()
        if _render(mid, out, root) is None:
            return 1
        print("  %-9s %-44s %4.1fs   %s" % (name, out, time.time() - t0, why))
    print("  written low on purpose -- above D#3 the two are the same instrument")
    return 0


def register(outdir):
    """The same figure low and high. The high pair is the control."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fig = [(0.0, (28, 40), 112, 0.9), (1.0, (35, 47), 100, 0.9),
           (2.0, (31, 43), 104, 0.9), (3.0, (28, 40), 118, 2.4)]
    for shift, where, expect in ((0, 'low', 'the case binds: up to 12x the stretch'),
                                 (24, 'high', 'CONTROL -- same string in both, so what is left is the board alone')):
        for prog, name in ((ELECTRIC, 'electric'), (ACOUSTIC, 'acoustic')):
            mid = os.path.join(outdir, 'grand-%s-%s.mid' % (where, name))
            _track(prog, _notes(fig, shift), 5.0).save(mid)
            out = mid[:-4] + '.wav'
            if _render(mid, out, root) is None:
                return 1
            print("  %-5s %-9s %s" % (where, name, out))
        print("        %s" % expect)
    return 0


def main(argv):
    mode = next((a[2:] for a in argv[1:] if a.startswith('--')), None)
    args = [a for a in argv[1:] if not a.startswith('--')]
    outdir = args[0] if args else os.path.expanduser('~/Downloads/grand')
    os.makedirs(outdir, exist_ok=True)
    if mode == 'compare':
        return compare(outdir)
    if mode == 'register':
        return register(outdir)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mid = os.path.join(outdir, 'grand.mid')
    passage().save(mid)
    out = mid[:-4] + '.wav'
    if _render(mid, out, root) is None:
        return 1
    print("  %s" % out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
