#!/usr/bin/env python3
"""The acoustic bass, and the bowed one it shares a body with.

    python3 examples/bass.py [outdir]
    python3 examples/bass.py --arco [outdir]
    python3 examples/bass.py --family [outdir]

GM 32 fell through to the generic plucked string -- which is not a FormantBody
and whose zero bore corner means no body is ever applied, so it was a bare
string in free air. But the instrument was already measured one bank away: GM
43 Contrabass is the SAME DOUBLE BASS, fitted against the Iowa recordings
across three registers. Arco against pizzicato is an excitation, not a body.

--arco is the point of that: the same walking line plucked (GM 32) and bowed
(GM 43). The box is identical in both -- the 93 Hz air resonance, the 1750 Hz
bridge region -- and everything you hear differing is the gesture. The bow
sustains because it keeps feeding the string; the pluck decays, and its high
partials go in a moment while the fundamental stays under them (measured on a
rendered E1: 800 Hz-3 kHz falls 73 dB by 1.2 s where 60-200 Hz falls 9).

--family puts it beside the five electric basses, which are a different
instrument entirely: a solid body has no box, so they get a pickup and a
speaker cabinet where this gets a resonator.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido

ACOUSTIC = 32
CONTRABASS = 43
TPB = 480
TICKS_S = TPB * 2          # 120 bpm


def _env():
    env = dict(os.environ)
    env.setdefault('TUNING_ROOM', 'chamber')
    env.setdefault('TUNING_MASTER_DB', '-12')
    return env


def _render(mid, out, root):
    r = subprocess.run([sys.executable, os.path.join(root, 'blockrender.py'), mid, out],
                       env=_env(), cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        return None
    return r.stdout


# A walking line, which is what GM 32 is for. Two bars of Bb, two of Eb, back to
# Bb, then a turnaround -- quarter notes, mostly stepwise, the way a bass player
# actually gets from one chord to the next.
WALK = [34, 36, 38, 41,  39, 38, 36, 34,  39, 41, 43, 46,  44, 43, 41, 39,
        34, 36, 38, 41,  43, 41, 39, 38,  36, 41, 34, 38,  41, 40, 39, 41]


def track(program, notes, per=0.5, gap=0.93, tail_s=4.0, vel=96):
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.Message('program_change', program=program, channel=0, time=0))
    ev = []
    for i, n in enumerate(notes):
        t = int(i * per * TICKS_S)
        v = vel + (6 if i % 4 == 0 else 0)          # a little weight on the beat
        ev.append((t, mido.Message('note_on', note=n, velocity=v, channel=0)))
        ev.append((t + int(per * gap * TICKS_S),
                   mido.Message('note_off', note=n, velocity=0, channel=0)))
    # blockrender sizes a render as the MIDI plus one second, and a bass rings
    # for longer than that
    ev.append((ev[-1][0] + int(tail_s * TICKS_S),
               mido.Message('note_off', note=1, velocity=0, channel=0)))
    ev.sort(key=lambda kv: kv[0])
    last = 0
    for tick, msg in ev:
        msg.time = tick - last; last = tick
        tr.append(msg)
    return m


def arco(outdir):
    """The same line plucked and bowed. The body is identical; the gesture is not."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for prog, name, why in ((ACOUSTIC, 'pizz', 'GM 32 -- plucked at the quarter point'),
                            (CONTRABASS, 'arco', 'GM 43 -- the same box, bowed')):
        mid = os.path.join(outdir, 'bass-%s.mid' % name)
        track(prog, WALK).save(mid)
        out = mid[:-4] + '.wav'
        t0 = time.time()
        if _render(mid, out, root) is None:
            return 1
        print("  %-5s %-42s %4.1fs   %s" % (name, out, time.time() - t0, why))
    print("  the 93 Hz air resonance and the 1750 Hz bridge peak are the same")
    print("  numbers in both; what differs is how the string is set going")
    return 0


def family(outdir):
    """Beside the electrics, which have no box at all."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for prog, name, why in ((32, 'acoustic', 'a wooden box, measured'),
                            (33, 'finger', 'solid body: pickup and cabinet'),
                            (34, 'pick', 'as 33, plectrum'),
                            (35, 'fretless', 'as 33, wood not fret wire')):
        mid = os.path.join(outdir, 'bass-fam-%s.mid' % name)
        track(prog, WALK[:16]).save(mid)
        out = mid[:-4] + '.wav'
        if _render(mid, out, root) is None:
            return 1
        print("  %-9s %-42s %s" % (name, out, why))
    return 0


def main(argv):
    mode = next((a[2:] for a in argv[1:] if a.startswith('--')), None)
    args = [a for a in argv[1:] if not a.startswith('--')]
    outdir = args[0] if args else os.path.expanduser('~/Downloads/bass')
    os.makedirs(outdir, exist_ok=True)
    if mode == 'arco':
        return arco(outdir)
    if mode == 'family':
        return family(outdir)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mid = os.path.join(outdir, 'bass.mid')
    track(ACOUSTIC, WALK).save(mid)
    out = mid[:-4] + '.wav'
    if _render(mid, out, root) is None:
        return 1
    print("  %s" % out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
