#!/usr/bin/env python3
"""Fit a Moog panel to the synth riff of Journey's "Separate Ways".

    python3 examples/sepways_fit.py REF.wav [PANEL_JSON] [--start 2.8 --end 9.9]
    python3 examples/sepways_fit.py --riff OUT.wav [PANEL_JSON] [--single]
    python3 examples/sepways_fit.py --preset [NAME]      # live, presets.json

REF.wav is a private capture of the record's opening (not in the repo); the
riff plays nearly alone there: an E chord -- E4, B4, E5 -- as eighth notes at
about 133 bpm. The panel (JSON knob values over the saw lead's, moog.PANEL) is
rendered on the same chord, and both are measured the same way:

  envelope    each note's level every 10 ms, re its peak, averaged over notes
  brightness  spectral centroid, and the energy above 2 kHz against below, at
              0-180 ms after onset (the filter envelope)
  shape       third-octave spectrum 15 ms in (the cutoff, and any resonance)

Jonathan Cain played it on a Jupiter-8; players' reconstructions say two saws
~8-10 cents apart, a 24 dB low-pass, filter envelope, fast attack. The record
says more: it BRIGHTENS over the first ~70 ms and holds, and shows no
resonance peak.

--riff renders the opening itself, transcribed from the capture on a strict
eighth grid (133 bpm), as Ben hears it and the spectrum confirms: on the beats
E5 B4 F#5 B4 G5 B4 B4 B4, against a low E4 on every off-beat, each note held a
quarter so the two voices overlap -- they never really stop (the record is
only 6 dB down when the next note comes; gated eighths were 22 dB down), and
the hall carries each one on after it.
Played twice, ending on the downbeat where the band comes in.
"""
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BPM, CHORD, NOTE_S = 133.0, (64, 71, 76), 0.20
CHORUS = 0
ROOM = "hall"
# the fit: ONE saw -- OSC2 at unison; Ben hears no detune on the record, and
# the pitch wobble and width it does have are uncorrelated left and right,
# which no chorus or detune makes: they are the room. The 4-pole low-pass open
# past the riff's harmonics, no resonance, a ~50 ms filter rise, and the
# amplifier a brass contour that fades all the way out (decay and release
# 1.8 s, sustain 0: 12 dB down at 420 ms, as the record). No filter decay: the
# record does not darken as it fades. Rendered in the hall with roomtail's
# late field: the high notes' tails, averaged, then follow the record's within
# a few dB to 1 s (narrower: L/R correlation 0.52, the record's 0.17).
FIT = {"mode": 0, "osc1_wave": 0.5, "osc2_wave": 0.5, "osc1_level": 0.8, "osc2_level": 0.8, "osc2_freq": 0.5, "resonance": 0.0, "kb_track": 0.0, "f_attack": 0.0913, "a_attack": 0.0, "a_decay": 0.6076, "a_sustain": 0.2254, "a_release": 0.6076, "cutoff": 0.85, "eg_amount": 0.3, "f_decay": 0.4, "f_sustain": 1.0}


def read(path):
    w = wave.open(path)
    r, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    a = np.frombuffer(w.readframes(w.getnframes()), {2: '<i2', 4: '<i4'}[sw]).astype(float)
    a = a.reshape(-1, ch).mean(1) / (32768.0 if sw == 2 else 2147483648.0)
    return a, r


def measure(x, r):
    hop = int(0.005 * r)
    e = np.array([np.sum(x[i:i + hop] ** 2) for i in range(0, len(x) - hop, hop)])
    le = 10 * np.log10(e + 1e-12)
    d = np.diff(le)
    ons = [i for i in range(2, len(d) - 2) if d[i] > 3 and le[i + 1] > le.max() - 30
           and d[i] == d[i - 2:i + 3].max()]
    on = []
    for o in ons:
        if not on or o - on[-1] > 25:
            on.append(o)
    L = 40
    env = np.mean([le[o:o + L] - le[o:o + L].max() for o in on if o + L < len(le)], 0)[::2]
    N = 2048
    win = np.hanning(N)
    f = np.fft.rfftfreq(N, 1 / r)

    def spec(t):
        return np.mean([np.abs(np.fft.rfft(win * x[o * hop + int(t * r):o * hop + int(t * r) + N])) ** 2
                        for o in on if o * hop + int(t * r) + N < len(x)], 0)
    bright = []
    for t in (0.0, 0.02, 0.04, 0.07, 0.1, 0.14, 0.18):
        sp = spec(t)
        bright.append(((f * sp).sum() / sp.sum(),
                       10 * np.log10(sp[f > 2000].sum() / sp[(f > 100) & (f < 2000)].sum())))
    sp = spec(0.015)
    bands = 250 * 2 ** (np.arange(0, 19) / 3.0)
    lv = np.array([10 * np.log10(sp[(f >= b / 2 ** (1 / 6)) & (f < b * 2 ** (1 / 6))].mean() + 1e-20)
                   for b in bands])
    # THE CHORD'S HARMONICS, which the melody over it cannot disturb: the
    # energy within 1% of each harmonic of E4 (both oscillators, either side
    # of it), over the whole stretch -- their fall is the filter's, alone
    S = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    F = np.fft.rfftfreq(len(x), 1 / r)
    f0 = F[(F > 320) & (F < 345)][np.argmax(S[(F > 320) & (F < 345)])]
    harm = np.array([10 * np.log10(S[np.abs(F - k * f0) < 0.012 * k * f0].sum() + 1e-30) for k in range(1, 17)])
    return len(on), env, bright, bands, lv - lv.max(), harm - harm[0]


def render(panel):
    import mido
    d = tempfile.mkdtemp(prefix="sepways_")
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=int(60e6 / BPM), time=0))
    t.append(mido.Message('program_change', program=81, time=0))
    step = 240                          # an eighth
    on = int(round(NOTE_S / (60.0 / BPM / 2) * step))
    for k in range(24):
        for i, n in enumerate(CHORD):
            t.append(mido.Message('note_on', note=n, velocity=100, time=0 if i else (step - on if k else 0)))
        for i, n in enumerate(CHORD):
            t.append(mido.Message('note_off', note=n, time=on if i == 0 else 0))
    mid = os.path.join(d, "riff.mid")
    m.save(mid)
    out = os.path.join(d, "riff.wav")
    env = dict(os.environ, TUNING_MOOG_PANEL=json.dumps(panel), TUNING_REFLECT="0")
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, out, "even"],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    return out


BEATS = (76, 71, 78, 71, 79, 71, 71, 71)       # E B F# B G B B B, over E4 off-beats


def riff(panel, out, chorus=0, pan=None, late_ms=0.0):
    """The opening: pickup, the phrase twice, the downbeat held."""
    import mido
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=int(60e6 / BPM), time=0))
    t.append(mido.Message('program_change', program=81, time=0))
    if pan is not None:
        t.append(mido.Message('control_change', control=10, value=pan, time=0))
    if chorus:                                   # the record's studio chorus (CC93)
        t.append(mido.Message('control_change', control=93, value=chorus, time=0))
    step = 240
    hold = int(round(2 * step * 0.96))                       # a quarter, near legato
    ev = []
    for k, top in enumerate(BEATS * 2):
        ev.append((2 * k * step, hold, (top,)))
        ev.append(((2 * k + 1) * step, hold, (64,)))
    ev.append((32 * step, 4 * step, (64, 71, 76)))           # where the band enters
    msgs = []
    for at, dur, notes in ev:
        msgs += [(at, 1, n) for n in notes] + [(at + dur, 0, n) for n in notes]
    now = 0
    lead = int(round(late_ms / 1000.0 * BPM / 60.0 * 480))
    for at, on, n in sorted(msgs):
        at += lead
        t.append(mido.Message('note_on' if on else 'note_off', note=n, velocity=100 if on else 0,
                              time=at - now))
        now = at
    d = tempfile.mkdtemp(prefix="sepways_")
    mid = os.path.join(d, "riff.mid")
    m.save(mid)
    env = dict(os.environ, TUNING_MOOG_PANEL=json.dumps(panel))
    env.setdefault("TUNING_ROOM", ROOM)
    dry = os.path.join(d, "riff.wav")
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, dry, "even"],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), dry, out],
                   env=env, check=True, stdout=subprocess.DEVNULL)


# DOUBLE-TRACKED. Each channel of the record holds its own pair of lines,
# the same in both halves of the riff -- E4's harmonics stacked in cents: the
# right 0 and -10, the left -5 and -8.5 -- so the riff was played twice, each
# pass a two-oscillator voice of its own detune, panned apart; which is also
# why left and right are nearly uncorrelated (0.17). The left pass sits ~5
# cents flat of the right and comes ~7 ms later. TUNE and OSC 2 FREQ are both
# +-7 semitones about 0.5: a cent is 1/1400 of the knob.
PASSES = ((88, 0.0, -10.0, 0.0), (39, -8.5, 3.5, 7.0))  # (CC10, tune c, osc2 c, late ms)


def double(panel, out, chorus=0):
    """Both passes, each in the hall, summed."""
    parts = []
    d = tempfile.mkdtemp(prefix="sepways2_")
    for i, (pan, tune, osc2, late) in enumerate(PASSES):
        p = dict(panel, tune=0.5 + tune / 1400.0, osc2_freq=0.5 + osc2 / 1400.0)
        parts.append(os.path.join(d, "pass%d.wav" % i))
        riff(p, parts[-1], chorus, pan, late)
    subprocess.run(["sox", "-m"] + parts + [out], check=True)


def preset(name="separate-ways"):
    """The double-tracked riff as a live preset: two Moog parts layered over
    the whole keyboard, one per pass, each with its pass's panel and its own
    pan pot (live.Part.pan), in the hall. Written to presets.json. The left
    pass's 7 ms lag is the second player's timing and is not in it."""
    sys.path.insert(0, HERE)
    import live
    parts = []
    for pan, tune, osc2, _late in PASSES:
        synth = dict(FIT, tune=0.5 + tune / 1400.0, osc2_freq=0.5 + osc2 / 1400.0)
        parts.append(dict(program=81, drums=False, tuner="even", channel=None, lo=0, hi=127,
                          transpose=0, level_db=-3.0, muted=False, drawn=[],
                          synth=synth, synth_units=5, pan=pan))
    d = live.load_presets()
    d[name] = dict(parts=parts, room=ROOM, master_db=-9.3, headroom_db=8.0, bend_range=2.0,
                   mod_cents=35.0, press_db=8.0, press_tilt=0.3, thresh=0.7, mod_rate=0.25,
                   controls=[], routes=[], chanstate=[])
    tmp = live.PRESET_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, live.PRESET_PATH)
    print("preset %r -> %s" % (name, live.PRESET_PATH))


def main(argv):
    if '--preset' in argv:
        i = argv.index('--preset')
        preset(argv[i + 1] if len(argv) > i + 1 else "separate-ways")
        return 0
    if '--riff' in argv:
        rest = [x for x in argv[1:] if x != '--riff']
        ch = int(argv[argv.index('--chorus') + 1]) if '--chorus' in argv else CHORUS
        rest = [x for x in rest if x not in ('--chorus', str(ch), '--single')]
        (double if '--single' not in argv else riff)(
            json.loads(rest[1]) if len(rest) > 1 else FIT, rest[0], ch)
        return 0
    a = [x for x in argv[1:] if not x.startswith('--')]
    ref = a[0]
    panel = json.loads(a[1]) if len(a) > 1 else {}
    t0 = float(argv[argv.index('--start') + 1]) if '--start' in argv else 2.8
    t1 = float(argv[argv.index('--end') + 1]) if '--end' in argv else 9.9
    x, r = read(ref)
    R = measure(x[int(t0 * r):int(t1 * r)], r)
    y, ry = read(render(panel))
    M = measure(y, ry)
    print("notes: reference %d, render %d" % (R[0], M[0]))
    print("envelope dB every 10 ms\n  ref " + ' '.join('%4.0f' % v for v in R[1]) +
          "\n  us  " + ' '.join('%4.0f' % v for v in M[1]))
    print("brightness  (ms: ref centroid / >2k ratio  |  ours)")
    for t, (rc, rh), (mc, mh) in zip((0, 20, 40, 70, 100, 140, 180), R[2], M[2]):
        print("  %3d   %5.0f Hz %+5.1f dB  |  %5.0f Hz %+5.1f dB" % (t, rc, rh, mc, mh))
    print("third-octaves 15 ms in (dB re max)")
    print("  Hz  " + ' '.join('%5.0f' % b for b in R[3]))
    print("  ref " + ' '.join('%5.0f' % v for v in R[4]))
    print("  us  " + ' '.join('%5.0f' % v for v in M[4]))
    print("  shape error (rms over 300 Hz-6 kHz): %.1f dB" %
          np.sqrt(np.mean(((R[4] - M[4])[(R[3] >= 300) & (R[3] <= 6000)]) ** 2)))
    print("E4's harmonics 1-16 (dB re the fundamental)")
    print("  ref " + ' '.join('%4.0f' % v for v in R[5]))
    print("  us  " + ' '.join('%4.0f' % v for v in M[5]))
    print("  harmonic error (rms, 2-16): %.1f dB" % np.sqrt(np.mean((R[5][1:] - M[5][1:]) ** 2)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
