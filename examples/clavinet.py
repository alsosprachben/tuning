#!/usr/bin/env python3
"""A clavinet, and the harpsichord it used to be.

    python3 examples/clavinet.py [outdir]
    python3 examples/clavinet.py --compare [outdir]
    python3 examples/clavinet.py --tone [outdir]

GM 7 was played by HarpsichordProperties -- plucked, wooden, and carrying no
pickup at all. A clavinet is a struck steel string trapped against an anvil by
a rubber tangent and read by magnets, and the tangent IS the string's
termination, so its comb rises through the audible range instead of notching
inside it. That is the buzz. See tonelib.ClavinetProperties and sources.md.

--tone sweeps the panel. Six rocker switches sit left of a D6's keyboard and
four of them are the tone section -- "Brilliant and Treble activate a high-pass
filter, while Medium and Soft activate a low-pass filter" -- so CC1 sweeps those
four, darkest to brightest, with all four up in the middle. Rendered, the
attack centroid runs 673, 855, 1049, 1314, 1623 Hz across the five positions.
The other two rockers, AB/CD, choose which pickup is heard; they change the
COMB rather than filtering it, so they are not on the wheel.

--compare renders the same figure on both, which is the point: they are both
bright keyboard strings and they are not the same instrument. Listen low, where
the pickup sits a fifteenth of the way up the string and the comb's first null
is above the 13th partial, and then high, where the same magnet is a fifth of
the way up and the null has come down to the 5th.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido

CLAVINET = 7
HARPSICHORD = 6
TPB = 480


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


def passage(program=CLAVINET):
    """A clavinet part: a riff low down where the instrument lives, then the
    same shape two octaves up, then a chord to hear the comb across a register.

    Written short and hard. A clavinet has no sustain to speak of -- the anvil
    is lossy and the yarn damper is immediate -- so long notes say nothing
    about it that short ones do not say better.
    """
    m = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.Message('program_change', program=program, channel=0, time=0))
    ev = []
    riff = ((0, 40, 112), (1, 40, 74), (2, 47, 104), (3, 45, 88),
            (4, 40, 118), (5, 52, 96), (6, 50, 100), (7, 47, 84))
    for rep, (shift, vel_k) in enumerate(((0, 1.0), (24, 0.92))):
        for step, note, vel in riff:
            t = int((rep * 8 + step) * TPB / 2)
            v = max(30, min(127, int(vel * vel_k)))
            ev.append((t, mido.Message('note_on', note=note + shift, velocity=v, channel=0)))
            ev.append((t + TPB // 4, mido.Message('note_off', note=note + shift,
                                                  velocity=0, channel=0)))
    # and a chord spanning three octaves, to hear the comb move with pitch
    t = 17 * TPB // 2
    for n in (40, 52, 64, 76):
        ev.append((t, mido.Message('note_on', note=n, velocity=108, channel=0)))
        ev.append((t + TPB, mido.Message('note_off', note=n, velocity=0, channel=0)))
    ev.sort(key=lambda kv: kv[0])
    last = 0
    for tick, msg in ev:
        msg.time = tick - last; last = tick
        tr.append(msg)
    return m


def tone(outdir):
    """The five rocker positions on one figure. CC1 is written into each file."""
    import tonelib as T
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    n = len(T.CLAV_TONE)
    for i, (name, corner, order, high) in enumerate(T.CLAV_TONE):
        cc = int(round(i / (n - 1.0) * 127))
        m = passage()
        m.tracks[0].insert(1, mido.Message('control_change', control=1, value=cc,
                                           channel=0, time=0))
        mid = os.path.join(outdir, 'clav-tone-%d-%s.mid' % (i, name))
        m.save(mid)
        out = mid[:-4] + '.wav'
        if _render(mid, out, root) is None:
            return 1
        what = ("flat -- all four rockers up" if corner <= 0 else
                "%s-pass at %.0f Hz" % ("high" if high else "low", corner))
        print("  CC1 %3d  %-10s %-44s %s" % (cc, name, out, what))
    return 0


def compare(outdir):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for prog, name, why in ((CLAVINET, 'clavinet', 'struck at the anvil, read by magnets'),
                            (HARPSICHORD, 'harpsichord', 'plucked, wooden, no pickup')):
        mid = os.path.join(outdir, 'clav-%s.mid' % name)
        passage(prog).save(mid)
        out = mid[:-4] + '.wav'
        t0 = time.time()
        if _render(mid, out, root) is None:
            return 1
        print("  %-12s %-46s %4.1fs   %s" % (name, out, time.time() - t0, why))
    return 0


def main(argv):
    mode = next((a[2:] for a in argv[1:] if a.startswith('--')), None)
    args = [a for a in argv[1:] if not a.startswith('--')]
    outdir = args[0] if args else os.path.expanduser('~/Downloads/clavinet')
    os.makedirs(outdir, exist_ok=True)
    if mode == 'compare':
        return compare(outdir)
    if mode == 'tone':
        return tone(outdir)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mid = os.path.join(outdir, 'clavinet.mid')
    passage().save(mid)
    out = mid[:-4] + '.wav'
    if _render(mid, out, root) is None:
        return 1
    print("  %s" % out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
