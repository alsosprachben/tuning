#!/usr/bin/env python3
"""The Messenger's performance controls, measured on Ben's own unit.

    python3 examples/messenger_perf.py TEST [--card 2] [--port Messenger]

What its manual's Appendix A puts on MIDI beside the knobs the model already
has -- the switches below the envelopes, HOLD, GLIDE, LFO 2 -- played over
MIDI and recorded back through the USB mixer (messenger_fit's rig), so the
model can do what the hardware does rather than what the manual's words
suggest. Each test prints what it measured and leaves its takes in
$TMPDIR/messenger_fit.

Tests:
  trig   MULTI-TRIG (CC114) off and on: a second key pressed while the first
         is held -- does the amp contour start again? -- and which key
         sounds (key priority), and what sounds when the newer is let go.
  hold   HOLD (CC73): a note released with it on, then HOLD let go.
  glide  GLIDE RATE (CC5) across its travel: a legato octave, the time the
         pitch takes to get most of the way.
  vel    F ENV VEL (CC80) and A ENV VEL (CC81): level and brightness against
         velocity, each switch off and on.
  lfo2   LFO 2 (CC27 rate; CC116 pitch, 117 cutoff, 118 amp; the mod wheel
         its depth): its rate law and how far it swings at full wheel.
  loop   F ENV LOOP (CC112), A ENV LOOP (CC113): the contour cycling -- its
         period against the attack and decay it runs through.
"""
import os
import sys
import time

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import messenger_fit as F
import moog as MG

SR = F.SR


def cc(rig, c, v):
    import mido
    rig.out.send(mido.Message('control_change', channel=0, control=c, value=int(v)))
    time.sleep(0.01)


def env_db(y, ms=5.0):
    """The take's level, dB, every ms."""
    w = max(1, int(SR * ms / 1000.0))
    n = len(y) // w
    e = np.sqrt((y[:n * w].reshape(n, w) ** 2).mean(axis=1)) + 1e-9
    return 20.0 * np.log10(e)


def f0_track(y, lo, hi, ms=5.0):
    """The fundamental's frequency every ms, in [lo, hi] Hz (band, then the
    analytic signal's phase)."""
    sos = butter(3, [lo, hi], btype='band', fs=SR, output='sos')
    z = hilbert(sosfiltfilt(sos, y))
    f = np.diff(np.unwrap(np.angle(z))) * SR / (2 * np.pi)
    w = max(1, int(SR * ms / 1000.0))
    n = len(f) // w
    return np.median(f[:n * w].reshape(n, w), axis=1)


# THE TESTS' PANEL: the calibration panel (one saw, filter open), the amp
# contour given an attack and decay long enough to see start again
TRIG = dict(F.CAL, a_attack=0.55, a_decay=0.55, a_sustain=0.45, a_release=0.35)


def test_trig(rig):
    out = {}
    for mt in (0, 127):
        rig.panel(TRIG)
        cc(rig, 114, mt)

        def play(g):
            import mido
            g.played.append(time.monotonic() - g.t0)
            g.out.send(mido.Message('note_on', channel=0, note=57, velocity=100))     # A3, held
            time.sleep(1.5)
            g.played.append(time.monotonic() - g.t0)
            g.out.send(mido.Message('note_on', channel=0, note=64, velocity=100))     # E4 over it
            time.sleep(1.5)
            g.played.append(time.monotonic() - g.t0)
            g.out.send(mido.Message('note_off', channel=0, note=64, velocity=0))      # E4 up: A3 still down
            time.sleep(1.5)
            g.out.send(mido.Message('note_off', channel=0, note=57, velocity=0))
        y = rig.take('trig_%d' % mt, 6.0, play)
        e = env_db(y)
        t1, t2, t3 = rig.played
        k = lambda t: int(t * 200)
        # the level just before the second key, its peak in the 400 ms after
        before = e[k(t2) - 20:k(t2)].mean()
        after = e[k(t2):k(t2) + 80].max()
        p1 = F.pitch(y[int((t1 + 0.6) * SR):int((t1 + 1.3) * SR)])
        p2 = F.pitch(y[int((t2 + 0.6) * SR):int((t2 + 1.3) * SR)])
        p3 = F.pitch(y[int((t3 + 0.6) * SR):int((t3 + 1.3) * SR)])
        b3 = e[k(t3) - 20:k(t3)].mean()
        a3 = e[k(t3):k(t3) + 80].max()
        out[mt] = (before, after, p1, p2, p3, b3, a3)
        print('MULTI-TRIG %s: second key: %.1f dB before, peak %.1f dB in 400 ms after (%+.1f)  '
              '| pitches %.1f, %.1f, then %.1f Hz | newer key up: %.1f -> peak %.1f (%+.1f)'
              % ('on ' if mt else 'off', before, after, after - before, p1, p2, p3, b3, a3, a3 - b3))
    return out


def test_hold(rig):
    rig.panel(TRIG)
    cc(rig, 114, 0)

    def play(g):
        import mido
        cc(g, 73, 127)
        g.played.append(time.monotonic() - g.t0)
        g.out.send(mido.Message('note_on', channel=0, note=57, velocity=100))
        time.sleep(0.8)
        g.played.append(time.monotonic() - g.t0)
        g.out.send(mido.Message('note_off', channel=0, note=57, velocity=0))      # released, HOLD on
        time.sleep(1.5)
        g.played.append(time.monotonic() - g.t0)
        cc(g, 73, 0)                                                            # HOLD let go
        time.sleep(1.5)
    y = rig.take('hold', 4.5, play)
    e = env_db(y)
    t1, t2, t3 = rig.played
    k = lambda t: int(t * 200)
    print('HOLD: held %.1f dB; 1 s after the key up (HOLD on) %.1f dB; 1 s after HOLD off %.1f dB'
          % (e[k(t1 + 0.5):k(t1 + 0.7)].mean(), e[k(t2 + 1.0):k(t2 + 1.2)].mean(), e[k(t3 + 1.0):k(t3 + 1.2)].mean()))


def test_glide(rig):
    rows = []
    # (a TRIANGLE: no second harmonic for the tracker to take for the octave
    # the glide is going to; the first note struck with GLIDE at nothing, so it
    # does not glide in from the last take's)
    for v in (16, 32, 48, 64, 80, 96, 112, 127):
        rig.panel(dict(TRIG, osc1_wave=MG.TRI))
        cc(rig, 114, 0)
        cc(rig, 5, 0)
        cc(rig, 37, 0)

        def play(g, v=v):
            import mido
            g.played.append(time.monotonic() - g.t0)
            g.out.send(mido.Message('note_on', channel=0, note=45, velocity=100))     # A2
            time.sleep(1.0)
            cc(g, 5, v)
            time.sleep(0.2)
            g.played.append(time.monotonic() - g.t0)
            g.out.send(mido.Message('note_on', channel=0, note=57, velocity=100))     # A3, legato
            time.sleep(0.05)
            g.out.send(mido.Message('note_off', channel=0, note=45, velocity=0))
            time.sleep(3.5)
            g.out.send(mido.Message('note_off', channel=0, note=57, velocity=0))
        y = rig.take('glide_%d' % v, 5.5, play)
        t1, t2 = rig.played
        f = f0_track(y, 90.0, 300.0)
        a = f0_track(y[int(t1 * SR):int((t1 + 1.0) * SR)], 90.0, 300.0)
        f_lo = np.median(a[50:150])
        f_hi = np.median(f[int((t2 + 3.0) * 200):int((t2 + 3.3) * 200)])
        seg = f[int(t2 * 200):int((t2 + 3.3) * 200)]
        cents = 1200.0 * np.log2(np.maximum(seg, 1.0) / f_lo)
        span = 1200.0 * np.log2(f_hi / f_lo)
        def t_at(fr):
            i = np.flatnonzero(cents >= fr * span)
            return i[0] * 0.005 if len(i) else float('nan')
        t50, t90 = t_at(0.5), t_at(0.9)
        rows.append((v, t50, t90, f_lo, f_hi))
        print('GLIDE CC5=%3d: %.0f -> %.0f Hz; half way at %.3f s, 90%% at %.3f s (90/50 = %.2f)'
              % (v, f_lo, f_hi, t50, t90, t90 / t50 if t50 > 0 else float('nan')))
    return rows


def test_detached(rig):
    """GLIDE between DETACHED notes: the first let go before the second."""
    rig.panel(dict(TRIG, osc1_wave=MG.TRI))
    cc(rig, 114, 0)
    cc(rig, 5, 0)

    def play(g):
        import mido
        g.out.send(mido.Message('note_on', channel=0, note=45, velocity=100))
        time.sleep(1.0)
        g.out.send(mido.Message('note_off', channel=0, note=45, velocity=0))
        cc(g, 5, 96)
        time.sleep(0.4)
        g.played.append(time.monotonic() - g.t0)
        g.out.send(mido.Message('note_on', channel=0, note=57, velocity=100))
        time.sleep(2.0)
        g.out.send(mido.Message('note_off', channel=0, note=57, velocity=0))
    y = rig.take('glide_detached', 4.0, play)
    t2 = rig.played[0]
    f = f0_track(y, 80.0, 300.0)
    print('GLIDE, detached (CC5 96): pitch 20, 100, 300, 600 ms after the second key: %s Hz'
          % ', '.join('%.0f' % f[int((t2 + d) * 200)] for d in (0.02, 0.1, 0.3, 0.6)))


# A FILTER CONTOUR TO HEAR: the corner low, the contour's amount high and
# held at its peak (sustain at the top), so its depth is the brightness
FVEL = dict(F.CAL, cutoff=0.35, eg_amount=0.85, f_attack=0.0, f_decay=0.6, f_sustain=1.0,
            a_attack=0.0, a_decay=0.5, a_sustain=1.0, a_release=0.3)


def bright(seg):
    """The share of the note's energy above 1 kHz, dB."""
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1.0 / SR)
    return 10.0 * np.log10(X[f > 1000.0].sum() / X.sum() + 1e-12)


def test_vel(rig):
    vels = (10, 25, 40, 60, 80, 100, 127)
    for sw, c, pan in (('A ENV VEL', 81, TRIG), ('F ENV VEL', 80, FVEL)):
        for on in (0, 127):
            rig.panel(dict(pan, a_attack=0.0, a_decay=0.5, a_sustain=1.0))
            cc(rig, 80, 0)
            cc(rig, 81, 0)
            cc(rig, c, on)

            def play(g):
                for v in vels:
                    g.note(57, 0.6, vel=v)
                    time.sleep(0.4)
            y = rig.take('vel_%d_%d' % (c, on), 0.4 + len(vels) * 1.0, play)
            lv, br = [], []
            for t in rig.played:
                seg = y[int((t + 0.25) * SR):int((t + 0.55) * SR)]
                lv.append(20.0 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12))
                br.append(bright(seg))
            print('%s %s: level %s dB | above 1 kHz %s dB' % (sw, 'on ' if on else 'off',
                  ' '.join('%6.1f' % x for x in lv), ' '.join('%6.1f' % x for x in br)))
    print('(velocities %s)' % ' '.join('%6d' % v for v in vels))


def test_lfo2(rig):
    """LFO 2 on the pitch at full mod wheel: its rate at each CC27 setting and
    its swing; then at half wheel (how the wheel scales it)."""
    def track(y, t):
        f = f0_track(y[int((t + 0.3) * SR):int((t + 3.3) * SR)], 150.0, 300.0)
        c = 1200.0 * np.log2(np.maximum(f, 1.0) / np.median(f))
        c = c[20:-20] - np.mean(c[20:-20])
        n = len(c)
        C = np.abs(np.fft.rfft(c * np.hanning(n), 16 * n))
        fr = np.fft.rfftfreq(16 * n, 0.005)
        m = (fr > 0.2) & (fr < 40.0)
        return fr[m][np.argmax(C[m])], np.percentile(c, 98) - np.percentile(c, 2)
    for rate in (0, 32, 64, 96, 127):
        for wheel in ((127, 64) if rate == 64 else (127,)):
            rig.panel(dict(TRIG, osc1_wave=MG.TRI, a_attack=0.0, a_sustain=1.0))
            cc(rig, 116, 127)
            cc(rig, 117, 0)
            cc(rig, 118, 0)
            cc(rig, 27, rate)
            cc(rig, 59, 0)
            cc(rig, 1, wheel)
            cc(rig, 33, 0)

            def play(g):
                g.note(57, 3.6)
            y = rig.take('lfo2_%d_%d' % (rate, wheel), 4.2, play)
            hz, sw = track(y, rig.played[0])
            print('LFO 2 RATE CC27=%3d, wheel %3d: %.2f Hz, pitch swing %.0f cents peak to peak' % (rate, wheel, hz, sw))
    cc(rig, 1, 0)
    cc(rig, 116, 0)


def test_loop(rig):
    """A ENV LOOP: the amp contour cycling -- its period against attack+decay."""
    for at, de in ((0.4, 0.4), (0.5, 0.5), (0.4, 0.6), (0.6, 0.4)):
        rig.panel(dict(TRIG, a_attack=at, a_decay=de, a_sustain=0.0, a_release=0.3))
        cc(rig, 113, 127)

        def play(g):
            g.note(57, 4.0)
        y = rig.take('loop_%g_%g' % (at, de), 4.6, play)
        e = env_db(y, 2.0)
        t = rig.played[0]
        seg = e[int(t * 500):int((t + 4.0) * 500)]
        seg = seg - seg.mean()
        n = len(seg)
        S = np.abs(np.fft.rfft(seg * np.hanning(n), 16 * n))
        fr = np.fft.rfftfreq(16 * n, 0.002)
        m = (fr > 0.2) & (fr < 50.0)
        hz = fr[m][np.argmax(S[m])]
        ta, td = MG.knob_attack(at), MG.knob_time(de) / 4.0
        print('A ENV LOOP attack %.2f decay %.2f (model: attack %.3f s, decay tau %.3f s): cycles at %.2f Hz '
              '= period %.3f s; level swing %.1f dB' % (at, de, ta, td, hz, 1.0 / hz, np.percentile(seg, 98) - np.percentile(seg, 2)))
    cc(rig, 113, 0)


def test_lfo2slow(rig):
    """LFO 2's slow end: long holds so a cycle or more fits."""
    for rate in (0, 16, 32, 48, 80, 112):
        hold = {0: 24.0, 16: 16.0, 32: 10.0, 48: 6.0}.get(rate, 4.0)
        rig.panel(dict(TRIG, osc1_wave=MG.TRI, a_attack=0.0, a_sustain=1.0))
        for c, v in ((116, 127), (117, 0), (118, 0), (27, rate), (59, 0), (1, 127), (33, 0)):
            cc(rig, c, v)

        def play(g):
            g.note(57, hold)
        y = rig.take('lfo2s_%d' % rate, hold + 0.6, play)
        t = rig.played[0]
        f = f0_track(y[int((t + 0.3) * SR):int((t + hold - 0.2) * SR)], 100.0, 450.0)
        c = 1200.0 * np.log2(np.maximum(f, 1.0) / np.median(f))
        c = c[20:-20] - np.mean(c[20:-20])
        # zero crossings upward of the smoothed swing -> period
        k = np.convolve(c, np.ones(9) / 9, 'same')
        up = np.where((k[:-1] < 0) & (k[1:] >= 0))[0] * 0.005
        per = np.median(np.diff(up)) if len(up) > 2 else float('nan')
        print('LFO 2 RATE CC27=%3d: %d upward crossings, period %.3f s = %.3f Hz, swing %.0f cents'
              % (rate, len(up), per, 1.0 / per, np.percentile(c, 99) - np.percentile(c, 1)))
    cc(rig, 1, 0)
    cc(rig, 116, 0)


def test_lfo2dest(rig):
    """LFO 2 on the CUTOFF (the corner by noise in 0.25 s windows, as
    messenger_fit's) and on the AMP (the level), full and half wheel."""
    import messenger_fit as MF
    base = dict(MF.CAL, kb_track=0.0, resonance=0.0, osc1_level=0.0, noise_level=1.0,
                a_attack=0.0, a_sustain=1.0, f_sustain=0.0, eg_amount=0.5)
    rig.panel(dict(base, cutoff=1.0))
    for c, v in ((116, 0), (117, 0), (118, 0), (1, 0)):
        cc(rig, c, v)
    y = rig.take('lfo2_open', 2.0, lambda g: g.note(69, 1.4))
    t = rig.played[0]
    f, P0 = MF.psd(y[int((t + 0.25) * SR):int((t + 1.3) * SR)], 2048)
    band = (f > 25.0) & (f < 16000.0)
    open_h = MG.ladder_gain(f, MG.knob_cutoff(1.0), 0.0)
    for wheel in (127, 64, 32):
        rig.panel(dict(base, cutoff=0.5))
        for c, v in ((116, 0), (117, 127), (118, 0), (27, 32), (1, wheel)):
            cc(rig, c, v)
        y = rig.take('lfo2_cut_%d' % wheel, 7.0, lambda g: g.note(69, 6.3))
        t = rig.played[0]
        fcs = []
        for w in np.arange(t + 0.3, t + 6.0, 0.25):
            _f, P = MF.psd(y[int(w * SR):int((w + 0.25) * SR)], 2048)
            h = np.sqrt(P[band] / np.maximum(P0[band], 1e-30)) * open_h[band]
            fcs.append(MF.fit_ladder(h, f[band], k0=0)[0])
        o = np.log2(np.array(fcs) / MG.knob_cutoff(0.5))
        print('LFO 2 -> CUTOFF, wheel %3d: corner %.2f to %+.2f octaves about CUTOFF 0.5 (swing %.2f)'
              % (wheel, o.min(), o.max(), o.max() - o.min()))
    for wheel in (127, 64, 32):
        rig.panel(dict(TRIG, a_attack=0.0, a_sustain=1.0))
        for c, v in ((116, 0), (117, 0), (118, 127), (27, 64), (1, wheel)):
            cc(rig, c, v)
        y = rig.take('lfo2_amp_%d' % wheel, 4.2, lambda g: g.note(57, 3.6))
        t = rig.played[0]
        e = env_db(y, 2.0)
        seg = e[int((t + 0.4) * 500):int((t + 3.4) * 500)]
        lin = 10 ** (seg / 20.0)
        print('LFO 2 -> AMP, wheel %3d: level %.1f to %.1f dB (swing %.1f dB); linear min/max %.3f'
              % (wheel, seg.min(), seg.max(), seg.max() - seg.min(), lin.min() / lin.max()))
    cc(rig, 1, 0)
    cc(rig, 117, 0)
    cc(rig, 118, 0)


def test_loop2(rig):
    """A ENV LOOP with a SUSTAIN: does the loop pass through a release, and
    when does the decay end? The contour every 10 ms, saved for reading."""
    for at, de, su, re in ((0.3, 0.4, 0.6, 0.3), (0.3, 0.4, 0.6, 0.5), (0.3, 0.5, 0.3, 0.4), (0.3, 0.4, 0.0, 0.5)):
        rig.panel(dict(TRIG, a_attack=at, a_decay=de, a_sustain=su, a_release=re))
        cc(rig, 113, 127)
        name = 'loop2_%g_%g_%g_%g' % (at, de, su, re)
        y = rig.take(name, 6.6, lambda g: g.note(57, 6.0))
        e = env_db(y, 10.0)
        th = e.max() - 40
        up = np.where((e[:-1] < th) & (e[1:] >= th))[0] / 100.0
        print('A ENV LOOP A %.2f D %.2f S %.2f R %.2f: cycles %s s (model A %.3f, decay tau %.3f, release tau %.3f)'
              % (at, de, su, re, np.round(np.diff(up), 3), MG.knob_attack(at), MG.knob_tau(de), MG.knob_tau(re)))
    cc(rig, 113, 0)


def test_loopoff(rig):
    """A ENV LOOP after the key goes up: does the cycling stop?"""
    rig.panel(dict(TRIG, a_attack=0.3, a_decay=0.4, a_sustain=0.6, a_release=0.3))
    cc(rig, 113, 127)
    y = rig.take('loopoff', 6.0, lambda g: g.note(57, 2.2))
    e = env_db(y, 50.0)
    t = rig.played[0]
    print('key up at %.2f s; level every 0.1 s from the key:' % 2.2)
    print(' '.join('%.0f' % v for v in e[int(t * 20):int((t + 5.0) * 20):2]))
    cc(rig, 113, 0)


TESTS = dict(loopoff=test_loopoff, loop2=test_loop2, lfo2dest=test_lfo2dest, lfo2slow=test_lfo2slow, trig=test_trig, hold=test_hold, glide=test_glide, detached=test_detached, vel=test_vel,
             lfo2=test_lfo2, loop=test_loop)


def main(argv):
    if len(argv) < 2 or argv[1] not in TESTS:
        print(__doc__.strip())
        return 2
    card = int(argv[argv.index('--card') + 1]) if '--card' in argv else 2
    port = argv[argv.index('--port') + 1] if '--port' in argv else 'Messenger'
    rig = F.Rig(port=port, card=card)
    TESTS[argv[1]](rig)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
