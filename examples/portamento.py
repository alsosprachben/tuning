#!/usr/bin/env python3
"""Portamento: a mechanism moving at a speed.

    python3 examples/portamento.py [outdir]     # render the demonstrations
    python3 examples/portamento.py --check      # measure only, no render

GM 2 asks for three portamento controllers and this renderer answered none of
them until now. The reason to do it is not conformance -- it is that a glide is
the one gesture where a physical model has something to say a sampler cannot.

WHAT ROLAND ACTUALLY SPECIFIES, because two of the three are ambiguous and the
SC-55 manual is a scan with no text layer (sources.md). The VE-GS Pro MIDI
Implementation is the same GS control set with the text intact:

  CC5   "adjusts the RATE of pitch change ... A value of 0 results in the
        fastest change", initial value 0. RATE, not time -- so a wide interval
        takes proportionally longer, which is also what a hand does. The curve
        from the byte to a real speed is not published by anyone; it is chosen
        in tonelib.porta_semitone_time and written down in midi.md.
  CC65  "0-63 = OFF, 64-127 = ON" -- the same switch point the three pedals
        collapse half-pedalling at.
  CC84  the data byte is a SOURCE NOTE NUMBER. It fires once, and it works with
        CC65 off: Roland's Example 2 sends it with nothing sounding at all and
        still glides. Both of Roland's examples are reproduced byte for byte
        below, because they are the only worked cases from a primary source.

AND A GLIDE IS A LENGTH MOVING, NOT A PITCH MOVING. A trombone slide, a finger
on a string and a slide whistle's plunger all change a LENGTH, and f is 1/L. So
one hand speed is not one number of cents per second: going up the glide
ACCELERATES in cents and going down it DECELERATES, by the same amount, from
the same hand. That asymmetry is measured here, and it is the whole difference
between this and a synthesiser's portamento -- which is also modelled, on the
voices that are synthesisers, because a lag circuit has no arm.
"""
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mido
import blockrender as B
import tonelib as T

RATE = 44100
TUNER = 'hybrid440'


# ----------------------------------------------------------------- the probe
#
# INSTRUMENT BEFORE YOU ACCUSE. Every wrong answer this feature produced while
# it was being built came from the measurement, not the renderer -- the first
# version of this probe read a trombone's glide as running BACKWARDS at 154,000
# cents per second. Two things fixed it and both are load-bearing:
#
#   1. the phase is unwrapped ONCE and differentiated, with no per-hop
#      reference. Rebuilding a demodulation reference from n=0 at each hop is
#      the error that has misread every sweep in this codebase's history;
#   2. the estimate and the closed form it is compared against are smoothed by
#      the SAME kernel, so whatever the smoother does to one it does to both.
#
# Checked against a planted glide before it is allowed near a render. On the
# parameters used below it recovers one to about 4 cents, which is the floor
# any statement about the renderer has to clear.

def inst_freq(x, sr, lo, hi, smooth_ms=8.0):
    """Instantaneous frequency of the one partial inside [lo, hi]."""
    n = len(x)
    X = np.fft.fft(x)
    f = np.fft.fftfreq(n, 1.0 / sr)
    X[(np.abs(f) < lo) | (np.abs(f) > hi)] = 0.0
    h = np.zeros(n)
    h[0] = 1.0
    if n % 2 == 0:
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[1:(n + 1) // 2] = 2.0
    ph = np.unwrap(np.angle(np.fft.ifft(X * h)))
    return smooth(np.gradient(ph) * sr / (2.0 * np.pi), sr, smooth_ms)


def smooth(a, sr, ms):
    k = int(ms * sr / 1000.0)
    k += 1 - k % 2
    return np.convolve(a, np.ones(k) / k, mode='same')


def glide_curve(ft, g, tau, cut, t):
    """What the kernel is supposed to be doing: 1/(1 + g*e^(-t/tau))."""
    return ft / (1.0 + g * np.exp(-np.minimum(t, cut) / tau))


def probe_floor(ft, g, tau, cut, seconds=1.8):
    """Plant that curve as a pure tone and see what the probe makes of it."""
    t = np.arange(int(seconds * RATE)) / float(RATE)
    te = np.minimum(t, cut)
    # phase = 2*pi*ft*(t + tau*ln((1 + g e^{-te/tau})/(1 + g))), the exact
    # integral of the curve above -- the same one synthkernel.c adds.
    ph = 2.0 * np.pi * ft * (t + tau * np.log((1.0 + g * np.exp(-te / tau))
                                              / (1.0 + g)))
    fi = inst_freq(np.sin(ph), RATE, ft / (1.0 + g) * 0.7, ft * 1.25)
    want = smooth(glide_curve(ft, g, tau, cut, t), RATE, 8.0)
    m = (t > 0.03) & (t < seconds - 0.3)
    e = 1200.0 * np.log2(fi[m] / want[m])
    return float(np.abs(e).max()), float(np.sqrt((e ** 2).mean()))


# ------------------------------------------------------------------ the files

def write_wav(path, L, R):
    a = np.stack([np.clip(L, -1.0, 1.0), np.clip(R, -1.0, 1.0)], axis=1)
    w = wave.open(path, 'wb')
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes((a * 32767.0).astype('<i2').tobytes())
    w.close()


def write_midi(path, program, events, ch=0):
    m = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.Message('program_change', channel=ch, program=program, time=0))
    for msg, dt in events:
        msg.channel = ch
        msg.time = dt
        tr.append(msg)
    m.save(path)
    return path


def cc(n, v):
    return mido.Message('control_change', control=n, value=v)


def note(n, on=True, vel=100):
    return (mido.Message('note_on', note=n, velocity=vel) if on
            else mido.Message('note_off', note=n, velocity=0))


def roland_example_1(path, program, cc5):
    """90 3C 40 / B0 54 3C / 90 40 40 / 80 3C 40 / 80 40 40.

    Roland's result column: C4 on, no change, "glide from C4 to E4", no change,
    E4 off. The note-off of C4 does nothing BECAUSE THAT VOICE IS THE E4 NOW --
    which is the part of CC84 that is easy to miss and is quoted in midi.md.
    """
    return write_midi(path, program, [
        (cc(5, cc5), 0), (note(60), 0), (cc(84, 60), 480),
        (note(64), 0), (note(60, False), 0), (note(64, False), 1920)])


def roland_example_2(path, program, cc5):
    """B0 54 3C / 90 40 40 / 80 40 40, with nothing sounding at all.

    Roland: "E4 is played with glide from C4 to E4". No CC65 anywhere, which is
    the case that proves CC84 is not a modifier on the switch.
    """
    return write_midi(path, program, [
        (cc(5, cc5), 0), (cc(84, 60), 0),
        (note(64), 0), (note(64, False), 1920)])


def pair(path, program, cc5, a, b):
    """Two notes under CC65, so the second glides from the first."""
    return write_midi(path, program, [
        (cc(5, cc5), 0), (cc(65, 127), 0),
        (note(a), 0), (note(a, False), 960),
        (note(b), 0), (note(b, False), 1920)])


# --------------------------------------------------------------- measurements

def one_partial(mid, tuner=TUNER):
    """Render ONE partial of the file, so the probe has one thing to track.

    A TROMBONE IS NOT A SINE. Measuring a glide off the full voice was the
    first wrong answer here: 142 partials, mode lock and chiff inside one
    analysis band read as a pitch running backwards. Silencing everything but
    the fundamental asks the question that was actually meant -- does the
    KERNEL move this partial the way the table told it to -- and leaves whether
    the voice sounds right to the ear, which is where it belongs.
    """
    p = B.prepare(mid, tuner)
    nf = np.asarray(p['nf'])
    gb = np.asarray(p['gb'])
    # THE GLIDING NOTE'S FUNDAMENTAL, not the file's lowest partial. Roland's
    # Example 1 sounds a C4 before the E4 that glides, so "lowest" picked the
    # note that does NOT move and the measurement reported, correctly and
    # uselessly, that nothing had happened.
    pool = np.nonzero(gb != 0.0)[0]
    if len(pool) == 0:
        pool = np.arange(len(nf))
    keep = int(pool[np.argmin(nf[pool])])
    for k in ('aL', 'aR', 'aM'):
        z = np.zeros_like(p[k])
        z[keep] = p[k][keep]
        p[k] = np.ascontiguousarray(z)
    for k in ('vd', 'tbav', 'cv', 'sj'):
        p[k] = np.ascontiguousarray(np.zeros_like(p[k]))
    # FROM THE NOTE'S OWN ONSET, because that is the clock the kernel glides
    # on: trel is ns - non, per partial. Roland's Example 1 sounds a C4 for
    # half a second first, and measuring that file from sample zero compared
    # the glide against a formula running half a second ahead of it -- which
    # read as 1168 cents of renderer error and was 1168 cents of my own.
    non = int(np.asarray(p['non'])[keep])
    n = non + int(1.9 * RATE)
    L, R = B.synth_window(p, 0, n)
    x = (L.astype(np.float64) + R)[non:] / 2.0
    return x, float(nf[keep]), float(p['gb'][keep]), float(p['gt'][keep]), \
        float(p['gc'][keep])


def check_against_formula(mid, label, tuner=TUNER):
    x, ft, g, tau, cut = one_partial(mid, tuner)
    if g == 0.0:
        print("   %-26s no glide asked for" % label)
        return None
    t = np.arange(len(x)) / float(RATE)
    fi = inst_freq(x, RATE, ft / (1.0 + g) * 0.7, ft * 1.25)
    want = smooth(glide_curve(ft, g, tau, cut, t), RATE, 8.0)
    m = (t > 0.03) & (t < 1.6)
    e = 1200.0 * np.log2(fi[m] / want[m])
    floor = probe_floor(ft, g, tau, cut)
    print("   %-26s g=%+.4f tau=%.3f s" % (label, g, tau))
    # LIKE FOR LIKE: the probe against the formula at the SAME instants, not
    # against the endpoints it is not being asked about. Early in a fast glide
    # the smoother lags by design, and comparing its first sample to the source
    # pitch would report that lag as a renderer error.
    print("        at 30 ms %8.3f Hz (formula %8.3f), at 1.6 s %8.3f Hz (target %8.3f)"
          % (fi[m][0], want[m][0], fi[m][-1], ft))
    print("        vs the closed form: worst %6.2f c, rms %5.2f"
          "   (probe's own floor %.2f / %.2f)"
          % (np.abs(e).max(), np.sqrt((e ** 2).mean()), floor[0], floor[1]))
    return fi, t, ft, g, tau, cut


def asymmetry(outdir):
    """THE HEADLINE: up and down are not mirror images, and by how much.

    A hand settling toward a position covers the same travel either way, so the
    two glides take the same TIME -- that much is symmetric and it is why the
    speed law is written in length and not in cents. What is NOT symmetric is
    the shape. Frequency is 1/L, so as the length shrinks the same remaining
    travel is worth more cents: an upward glide LINGERS near its target and a
    downward one arrives sooner.

    Measured as the time to cover half the interval IN CENTS, in units of tau,
    which is the shape with the duration divided out. A lag circuit settles
    exponentially in pitch and gives ln2 = 0.693 in both directions; the number
    below straddles it, and the gap is the model.
    """
    print("\n UP AND DOWN ARE NOT MIRROR IMAGES, AND HERE IS THE GAP")
    print("   Same interval, same travel, same duration -- different curve.")
    print("   Time to reach the halfway point in cents, in units of tau:\n")
    rows = []
    for label, a, b in (("up   C4 -> E4", 60, 64), ("down E4 -> C4", 64, 60)):
        mid = pair(os.path.join(outdir, 'porta_%s.mid'
                                % label.split()[0]), 57, 64, a, b)
        x, ft, g, tau, cut = one_partial(mid)
        t = np.arange(len(x)) / float(RATE)
        fi = inst_freq(x, RATE, min(ft, ft / (1.0 + g)) * 0.7,
                       max(ft, ft / (1.0 + g)) * 1.25)
        # from the render, not from the formula: the start is where the glide
        # actually began and the end is the target it actually reached.
        f0, f1 = ft / (1.0 + g), ft
        half = f0 * (f1 / f0) ** 0.5
        seg = np.nonzero(t > 0.02)[0]
        k = seg[np.argmin(np.abs(fi[seg] - half))]
        rows.append((label, tau, t[k] - 0.0, (t[k]) / tau,
                     -np.log((np.sqrt(1.0 + g) - 1.0) / g)))
    print("   %-14s %9s %11s %12s %12s"
          % ("", "tau", "t(half)", "measured", "closed form"))
    for lab, tau, th, meas, exact in rows:
        print("   %-14s %7.3f s %9.3f s %12.3f %12.3f"
              % (lab, tau, th, meas, exact))
    print("   %-14s %9s %11s %12.3f %12s"
          % ("a lag circuit", "-", "-", np.log(2.0), "ln 2"))
    print("\n   The circuit sits between the two, which is what it means for")
    print("   an arm and a capacitor to settle in different coordinates.")


def mechanisms():
    """Which voices glide, by what, and how far."""
    import patch_map
    print("\n WHAT EACH VOICE GLIDES WITH")
    print("   A controller is a question put to an instrument, and instruments")
    print("   decline. This is the same table damper_pedal and touch_sensitive")
    print("   belong to.\n")
    groups = {}
    for p in range(128):
        c = patch_map.property_class_for_program(p)
        m = getattr(c, 'glide_mechanism', None)
        groups.setdefault(m, []).append(p)
    for m in ('slide', 'stop', 'valve', 'circuit', None):
        ps = groups.get(m, [])
        if not ps:
            continue
        # EVERY REACH IN THE GROUP, not the first one's. A mechanism is not one
        # number: 'stop' covers a violinist's hand position and a fretless bass
        # neck, and reporting the first program's reach for both said 12
        # semitones for the violins, which is not a hand position by any
        # stretch and is the kind of wrong number a table invites.
        reaches = sorted({getattr(patch_map.property_class_for_program(p),
                                  'glide_reach_semitones', None) for p in ps},
                         key=lambda r: (r is None, r))
        name = m or '(refuses)'
        show = ", ".join("unbounded" if r is None else "%g st" % r
                         for r in reaches)
        print("   %-10s %3d programs  reach %s" % (name, len(ps), show))
        if m:
            print("              %s" % ", ".join(str(p) for p in ps[:16])
                  + (" ..." if len(ps) > 16 else ""))
    print("\n   'valve' reaches only as far as the LIP for now -- a brass gliss")
    print("   past a tone is a walk through the harmonic series, not a longer")
    print("   sweep, and rendering it as one would be a worse answer than")
    print("   rendering it clean. The lattice is brass_fingering's to answer.")


def speed_law():
    print("\n CC5 IS A RATE, WHICH MEANS A WIDE GLIDE TAKES LONGER")
    print("   Roland's word. A hand holds a SPEED, so the time it needs is the")
    print("   distance divided by it; a lag capacitor holds a TIME and does not")
    print("   know how far the voltage moved. They agree at a semitone around")
    print("   A440, so CC5 means one thing until the interval opens up.\n")
    print("   %5s %13s %13s %16s" % ("CC5", "semitone", "octave (hand)",
                                     "octave (circuit)"))
    for v in (0, 32, 64, 96, 127):
        a = 440.0
        print("   %5d %11.3f s %11.3f s %14.3f s"
              % (v, T.glide_tau(v, a * 2 ** (1 / 12.0), a),
                 T.glide_tau(v, a * 2.0, a),
                 T.glide_tau(v, a * 2.0, a, 'circuit')))
    print("\n   AND THE SAME INTERVAL TAKES LONGER LOW THAN HIGH, because the")
    print("   distance is a LENGTH: a semitone down in the pedal register is")
    print("   far more slide than a semitone at the top of the staff. Nothing")
    print("   put that in; it is what 1/f does. CC5 = 64, one semitone:\n")
    for hz, what in ((880.0, "A5, high on the staff"),
                     (440.0, "A4, the reference"),
                     (110.0, "A2, trombone country"),
                     (55.0, "A1, the pedal register")):
        print("      %-24s %7.1f Hz   %6.1f ms"
              % (what, hz, 1000.0 * T.glide_tau(64, hz * 2 ** (1 / 12.0), hz)))


def refusal(outdir):
    """A voice with no mechanism must render BIT-IDENTICALLY."""
    print("\n A VOICE THAT CANNOT GLIDE IS UNTOUCHED, TO THE BYTE")
    a = pair(os.path.join(outdir, 'porta_piano.mid'), 0, 64, 60, 64)
    b = write_midi(os.path.join(outdir, 'porta_piano_none.mid'), 0, [
        (note(60), 0), (note(60, False), 960),
        (note(64), 0), (note(64, False), 1920)])
    pa, pb = B.prepare(a, TUNER), B.prepare(b, TUNER)
    same = all(np.array_equal(np.asarray(pa[k]), np.asarray(pb[k]))
               for k in B.PARTIAL_COLS)
    print("   grand piano, with CC5/65 and without: partial tables %s"
          % ("identical" if same else "DIFFER -- wrong"))
    print("   (a hammer leaves the string; there is nothing to slide along)")


def step_groups(non, tol_ms=20.0):
    """Partials grouped by which STEP they belong to, not by exact onset.

    A note does not start at one instant: attack_jitter and the section's entry
    scatter give its partials onsets a few milliseconds apart, so grouping on
    the exact sample splits one step into several groups with different partial
    counts -- and then comparing their powers compares unequal sets. That error
    reported a 18 dB "half-valve dip" on a TROMBONE, which has no valves.
    """
    tol = tol_ms * RATE / 1000.0
    out = {}
    for i, t in enumerate(np.asarray(non)):
        key = next((k for k in out if abs(k - t) <= tol), int(t))
        out.setdefault(key, []).append(i)
    return out


def valve_lattice(outdir):
    """A valved gliss is a RUN through the harmonics, not a sweep across them."""
    import collections
    print("\n A TRUMPET DOES NOT SLIDE: IT RUNS THROUGH FINGERINGS")
    print("   Seven valve combinations and a lip, so the reachable pitches are")
    print("   a lattice. brass_fingering.py has held it all along -- it was")
    print("   written for intonation and answers this too.\n")
    for label, prog, v in (("trumpet, CC5=20 (a rip)", 56, 20),
                           ("trumpet, CC5=110 (half-valve)", 56, 110),
                           ("trombone, CC5=20 (the control)", 57, 20)):
        mid = write_midi(os.path.join(outdir, 'porta_gliss_%d_%d.mid'
                                      % (prog, v)), prog, [
            (cc(5, v), 0), (cc(65, 127), 0),
            (note(60), 0), (note(60, False), 480),
            (note(67), 0), (note(67, False), 1920)])
        p = B.prepare(mid, TUNER)
        nf, non = np.asarray(p['nf']), np.asarray(p['non'])
        gt, aM = np.asarray(p['gt']), np.asarray(p['aM'])
        g = step_groups(non)
        ts = sorted(g)
        f0s = [min(float(nf[i]) for i in g[t]) for t in ts]
        uniq = sorted({round(f, 2) for f in f0s})
        pw = [float(np.sum(aM[g[t]] ** 2)) for t in ts[2:]]
        dip = (10.0 * np.log10(min(pw) / max(pw[0], 1e-12))) if pw else 0.0
        print("   %-32s %2d pitches, tau %.4f s, dip %+5.1f dB"
              % (label, len(uniq), float(gt[g[ts[min(4, len(ts) - 1)]][0]]), dip))
    # THE RUNGS ARE FINGERED, NOT TEMPERED, which is the part that could not
    # have been faked: every semitone sits a few cents off equal, differently,
    # because that is where the valves actually put it.
    mid = write_midi(os.path.join(outdir, 'porta_gliss_rungs.mid'), 56, [
        (cc(5, 20), 0), (cc(65, 127), 0),
        (note(60), 0), (note(60, False), 480),
        (note(67), 0), (note(67, False), 1920)])
    p = B.prepare(mid, TUNER)
    nf, non = np.asarray(p['nf']), np.asarray(p['non'])
    g = step_groups(non)
    uniq = sorted({round(min(float(nf[i]) for i in g[t]), 3) for t in sorted(g)})
    print("\n   THE RUNGS ARE WHERE THE VALVES PUT THEM, not where equal")
    print("   temperament would. Steps of the run, in cents:\n")
    steps = [1200.0 * np.log2(uniq[i + 1] / uniq[i]) for i in range(len(uniq) - 1)]
    print("      " + "  ".join("%6.1f" % c for c in steps))
    print("      %s" % ("an equal semitone is 100.0 throughout; the spread here "
                        "is %.1f cents" % (max(steps) - min(steps))))


def live_agrees(outdir):
    """The two renderers must write the SAME three floats.

    Not the same audio measured twice -- the same numbers. Both paths hand the
    kernel gb/gt/gc per partial and the kernel is one piece of C, so if the
    columns match the rendering matches by construction. That is a stronger
    statement than any spectrum comparison and it is also the cheaper one; the
    tuning and CC93 work both ended up here after trying it the other way.

    It is also the check that would have caught the real risk in the live path,
    which is not the arithmetic but the PLUMBING: templates are keyed on (note,
    velocity bucket) and carry no glide, so gb/gt/gc are zeroed at stamp time
    and written afterwards. Forget the write and live is silently straight.
    """
    import live as L
    print("\n THE TWO RENDERERS WRITE THE SAME THREE FLOATS")
    mid = pair(os.path.join(outdir, 'porta_agree.mid'), 57, 64, 60, 64)
    p = B.prepare(mid, TUNER)
    gb = np.asarray(p['gb'])
    off = [float(np.asarray(p[k])[np.nonzero(gb != 0.0)[0][0]])
           for k in ('gb', 'gt', 'gc')]
    lv = L.Live(program=57, rate=RATE, frames=128, verbose=False, tuner=TUNER)
    lv.warm()

    def pump(blocks=4):
        # on_midi QUEUES; apply() is what hands a message to the engine, on the
        # audio thread's own clock. Sending without pumping looks exactly like
        # a feature that does not work, which is how this function first read.
        for _ in range(blocks):
            n0 = lv.n
            lv.apply(n0)
            lv.renderer.render(n0, 128)
            lv.n = n0 + 128

    def say(m):
        m.channel = 0
        lv.on_midi(m)

    say(cc(5, 64)); say(cc(65, 127)); say(note(60)); pump()
    say(note(60, False)); say(note(64)); pump()
    a = lv.slab.a
    idx = np.nonzero(np.asarray(a['gb']) != 0.0)[0]
    if len(idx) == 0:
        print("   live wrote NO glide -- the stamp did not happen")
        return
    liv = [float(np.asarray(a[k])[idx[0]]) for k in ('gb', 'gt', 'gc')]
    print("   %-6s %14s %14s %12s" % ("", "file", "live", "difference"))
    for name, o, l in zip(('gb', 'gt', 'gc'), off, liv):
        print("   %-6s %14.9f %14.9f %12.2e" % (name, o, l, abs(o - l)))
    print("   %d of live's partials are gliding" % len(idx))


def render(outdir):
    print("\n RENDERS")
    jobs = [
        ('porta_trombone_slow.mid', 57, 96, 'trombone, a slow slide'),
        ('porta_trombone_fast.mid', 57, 32, 'trombone, a quick one'),
        ('porta_violin.mid', 40, 80, 'violin, the same figure on a stopped string'),
        ('porta_lead.mid', 81, 80, 'saw lead, where the glide is a circuit'),
    ]
    for name, prog, v, what in jobs:
        mid = write_midi(os.path.join(outdir, name), prog, [
            (cc(5, v), 0), (cc(65, 127), 0),
            (note(60), 0), (note(60, False), 480),
            (note(64), 0), (note(64, False), 480),
            (note(62), 0), (note(62, False), 480),
            (note(67), 0), (note(67, False), 1440)])
        out = mid.replace('.mid', '.wav')
        L, R, total, P, kdt = B.render(mid, TUNER)
        write_wav(out, L, R)
        print("   %-44s %s (%d partials)" % (what, os.path.basename(out), P))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    outdir = args[0] if args else os.path.expanduser('~/Downloads/portamento')
    check = '--check' in sys.argv
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    print("\n ROLAND'S TWO WORKED EXAMPLES, BYTE FOR BYTE")
    print("   The only cases specified by a primary source.\n")
    check_against_formula(roland_example_1(
        os.path.join(outdir, 'porta_roland1.mid'), 57, 64),
        "Example 1 (C4 down, CC84)")
    check_against_formula(roland_example_2(
        os.path.join(outdir, 'porta_roland2.mid'), 57, 64),
        "Example 2 (nothing sounding)")
    mechanisms()
    speed_law()
    asymmetry(outdir)
    refusal(outdir)
    valve_lattice(outdir)
    live_agrees(outdir)
    if not check:
        render(outdir)
    print()


if __name__ == '__main__':
    main()
