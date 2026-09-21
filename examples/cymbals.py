#!/usr/bin/env python3
"""The cymbal family and the cuica, so they can be heard rather than only measured.

    python3 examples/cymbals.py [outdir]
    python3 examples/cymbals.py --dynamics [outdir]
    python3 examples/cymbals.py --bend [outdir]
    python3 examples/cymbals.py --cuica [outdir]
    python3 examples/cymbals.py --ride [outdir]

examples/cymbal_check.py established that a cymbal's modes do not bend -- 203
isolated partials across the Iowa family, every group under a cent, where the
voice was asserting sixteen. This renders what that voice actually sounds like.

--dynamics is the one the bend question was really about: the same crash from
pp to ff. What changes is BRIGHTNESS and how long the bright part lasts, not
pitch. A cymbal's high modes decay far faster than its low ones, so its
spectrum falls more than an octave through the ring -- measured, 1400 to 2100
cents -- and that, not a nonlinearity, is the "drift" a cymbal really has.

--bend is the A/B for the change: the same strokes with the old tension_bend of
0.007 against the measured 0.0. The claim is that nothing worth having is lost,
and the way to check a claim like that is to listen to both.

--cuica is the other instrument in here, and the one that was most wrong: it
was a struck membrane, and a cuica is a FRICTION drum. Listen for the squeak at
each onset -- that is the membrane's own inharmonic modes being pulled into a
harmonic tone by the friction drive -- and for the glide, which is the player's
other hand pressing the head. The two GM notes deliberately glide opposite
ways, so an alternating figure sounds like the instrument talking.

--ride is a played pattern rather than isolated strokes, because a ride is an
instrument you keep time on and a single stroke says nothing about that.
"""
import io
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido

TPB = 480
DRUM_CH = 9

# GM percussion notes, and what each one is in percussion_map.py.
FAMILY = (
    (49, 'crash1',    'Crash Cymbal 1 -- 17" plate'),
    (57, 'crash2',    'Crash Cymbal 2 -- the bigger, lower one'),
    (55, 'splash',    'Splash -- small, fast, gone'),
    (52, 'chinese',   'Chinese -- the trashy one'),
    (51, 'ride',      'Ride Cymbal 1 -- the 20" plate, struck on the bow'),
    (53, 'ridebell',  'Ride Bell -- the ping, at ratio 8.1 of the lowest mode'),
    (42, 'hihat_cl',  'Closed Hi-Hat'),
    (46, 'hihat_op',  'Open Hi-Hat'),
    (44, 'hihat_pd',  'Pedal Hi-Hat -- the foot, not the stick'),
)
DYNAMICS = (30, 60, 95, 127)


def _env():
    env = dict(os.environ)
    env.setdefault('TUNING_ROOM', 'chamber')
    env.setdefault('TUNING_MASTER_DB', '-12')
    return env


def _render(mid, out, env, root):
    r = subprocess.run([sys.executable, os.path.join(root, 'blockrender.py'), mid, out],
                       env=env, cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        return None
    return r.stdout


# 120 bpm at TPB ticks a beat, so this many ticks is one second.
TICKS_S = TPB * 2


def _track(ev, tail_s=10.0):
    """Lay out timed events, and KEEP THE RING.

    blockrender sizes the render as the MIDI's own length plus one second
    (`N = int(total*SR) + SR`), and a crash rings for ten. So every one of these
    files was ending 1.1 s after the last stroke with the tail chopped off --
    which on a cymbal throws away most of the instrument, and all of the thing
    these renders are for: the spectrum falling more than an octave through the
    ring. A silent event at the end buys the time back."""
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    ev = sorted(ev, key=lambda kv: kv[0])
    end = ev[-1][0] + int(tail_s * TICKS_S)
    ev = ev + [(end, mido.Message('note_off', note=1, velocity=0, channel=DRUM_CH))]
    last = 0
    for tick, msg in ev:
        msg.time = tick - last; last = tick
        tr.append(msg)
    return m


def _strokes(events, gap_s=2.5, tail_s=10.0):
    """One track of percussion strokes, spaced so each rings before the next.

    A cymbal is one_shot, so the note-off decides nothing -- it rings for as
    long as the voice says it does, which is why these are spaced in SECONDS
    and not by note length."""
    ev = []
    for i, (note, vel) in enumerate(events):
        t = int(i * gap_s * TICKS_S)
        ev.append((t, mido.Message('note_on', note=note, velocity=vel, channel=DRUM_CH)))
        ev.append((t + 60, mido.Message('note_off', note=note, velocity=0, channel=DRUM_CH)))
    return _track(ev, tail_s)


def family(outdir):
    """Every cymbal in the set, three strokes each, so they can be told apart."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ev = []
    t = 0.0
    for note, _name, _why in FAMILY:
        for k in range(2):
            tick = int(t * TICKS_S)
            ev.append((tick, mido.Message('note_on', note=note, velocity=100, channel=DRUM_CH)))
            ev.append((tick + 60, mido.Message('note_off', note=note, velocity=0, channel=DRUM_CH)))
            t += 1.1 if k == 0 else 3.4      # a pair, then room for it to ring out
    mid = os.path.join(outdir, 'cymbals-family.mid')
    _track(ev, 10.0).save(mid)
    out = mid[:-4] + '.wav'
    t0 = time.time()
    if _render(mid, out, _env(), root) is None:
        return 1
    print("  %s  %.1fs" % (out, time.time() - t0))
    print("  two strokes each, in this order:")
    for _n, name, why in FAMILY:
        print("     %-10s %s" % (name, why))
    return 0


def dynamics(outdir):
    """One crash from pp to ff. Brightness moves; pitch does not."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mid = os.path.join(outdir, 'cymbals-dynamics.mid')
    _strokes([(49, v) for v in DYNAMICS], 4.0).save(mid)
    out = mid[:-4] + '.wav'
    if _render(mid, out, _env(), root) is None:
        return 1
    print("  %s" % out)
    print("  crash 1 at velocity %s -- four seconds apart, and ten at the end,"
          % ", ".join(str(v) for v in DYNAMICS))
    print("  so each one rings out rather than being cut off")
    print("  what should change is how BRIGHT it is and how long the bright part")
    print("  lasts. If you hear the pitch move, the measurement was wrong.")
    return 0


def bend(outdir):
    """The A/B for the change: the old asserted bend against the measured zero."""
    import contextlib
    import tonelib as T
    import blockrender as B
    import numpy as np
    os.environ.setdefault('TUNING_ROOM', 'chamber')
    os.environ.setdefault('TUNING_MASTER_DB', '-12')
    mid = os.path.join(outdir, 'cymbals-bend.mid')
    _strokes([(49, v) for v in (60, 127)] + [(51, 100), (55, 127)], 4.0).save(mid)
    import wave
    for val, tag in ((0.007, 'old-0.007'), (0.0, 'measured-0.0')):
        was = T.CymbalProperties.tension_bend
        T.CymbalProperties.tension_bend = val
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r = B.render(mid)
        finally:
            T.CymbalProperties.tension_bend = was
        sig = next(e for e in r if isinstance(e, np.ndarray) and e.ndim >= 1 and len(e) > 10000)
        if sig.ndim == 1:
            sig = np.column_stack([sig, sig])
        out = os.path.join(outdir, 'cymbals-bend-%s.wav' % tag)
        w = wave.open(out, 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.clip(sig, -1, 1) * 32767).astype('<i2').tobytes()); w.close()
        print("  %-52s tension_bend %.3f" % (out, val))
    print("  the same four strokes both times, rendered in one process so nothing")
    print("  else can differ. 16 cents of pitch bloom against none.")
    return 0


def ride(outdir):
    """A ride pattern, because a single stroke says nothing about a ride."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ev = []
    for bar in range(4):
        for beat in range(4):
            t = (bar * 4 + beat) * TPB
            # bow on the beat, bell on 3, and the off-beats lighter
            ev.append((t, 53 if beat == 2 else 51, 104 if beat == 0 else 88))
            ev.append((t + TPB // 2, 51, 62))
        if bar in (1, 3):
            ev.append(((bar * 4 + 3) * TPB + TPB // 2, 49, 118))   # a crash to end the phrase
    out_ev = []
    for t, n, v in sorted(ev):
        out_ev.append((t, mido.Message('note_on', note=n, velocity=v, channel=DRUM_CH)))
        out_ev.append((t + 40, mido.Message('note_off', note=n, velocity=0, channel=DRUM_CH)))
    mid = os.path.join(outdir, 'cymbals-ride.mid')
    _track(out_ev, 10.0).save(mid)
    out = mid[:-4] + '.wav'
    if _render(mid, out, _env(), root) is None:
        return 1
    print("  %s" % out)
    print("  four bars: bow on the beats, bell on three, crashes ending the phrases")
    return 0


def cuica(outdir):
    """A cuica figure: the two notes alternating, then each on its own."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ev = []
    t = 0.0
    # The talking figure. The mute rises into pitch and the open falls away from
    # it, so alternating them is the gesture the instrument is known for.
    for n in (78, 79, 78, 79, 78, 78, 79):
        tick = int(t * TICKS_S)
        ev.append((tick, mido.Message('note_on', note=n, velocity=106, channel=DRUM_CH)))
        ev.append((tick + 200, mido.Message('note_off', note=n, velocity=0, channel=DRUM_CH)))
        t += 0.42
    t += 1.4
    for n in (79, 79, 78, 78):
        tick = int(t * TICKS_S)
        ev.append((tick, mido.Message('note_on', note=n, velocity=118, channel=DRUM_CH)))
        ev.append((tick + 320, mido.Message('note_off', note=n, velocity=0, channel=DRUM_CH)))
        t += 1.6
    mid = os.path.join(outdir, 'cuica.mid')
    _track(ev, 4.0).save(mid)
    out = mid[:-4] + '.wav'
    if _render(mid, out, _env(), root) is None:
        return 1
    print("  %s" % out)
    print("  a talking figure, then open twice and mute twice on their own.")
    print("  the squeak at each onset is the membrane locking into a harmonic tone")
    return 0


def main(argv):
    mode = next((a[2:] for a in argv[1:] if a.startswith('--')), None)
    args = [a for a in argv[1:] if not a.startswith('--')]
    outdir = args[0] if args else os.path.expanduser('~/Downloads/cymbals')
    os.makedirs(outdir, exist_ok=True)
    return {'dynamics': dynamics, 'bend': bend, 'ride': ride,
            'cuica': cuica}.get(mode, family)(outdir)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
