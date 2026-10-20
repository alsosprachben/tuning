#!/usr/bin/env python3
"""GS's synth variations as Messenger panels: 38.8 Synth Bass 3, 39.8 Synth
Bass 4, 50.8 Syn.Strings 3, 62.8 Synth Brass 3, 63.8 Synth Brass 4.

    python3 examples/messenger_variations.py target [VAR ...]   the GS sets' tones, measured
    python3 examples/messenger_variations.py probe STEP          a decoding panel to the Messenger
    python3 examples/messenger_variations.py ab OUTDIR [VAR ...]   the capital tone, then the variation
    python3 examples/messenger_variations.py presets BANK.syx N ...  the Messenger's preset N against
                                                                 ours from its decoded panel

THE MESSENGER'S PRESETS ARE SYSEX (its CONFIG 3.6 Send Current Preset, 3.7
Send All Presets), in a layout Moog does not document. It is decoded against
panels set here: STEP 0 puts every control the CC chart has at a LOW
position, and STEP b (1-5) moves the controls whose index has bit b-1 set to
a HIGH one -- each a dump after it (3.6), so every byte that changes names
its control by which dumps it moved in, and its values show the encoding.

Roland's SC-55 is not on this machine; GeneralUser GS and MuseScore General
both carry all five (GU calls 38.8 "Acid Bass", 39.8 "Beef FM Bass"). Each is
rendered through timidity, reverb and chorus off, and measured the way a
Messenger panel can be set:
  LEVEL   the 10 ms RMS envelope, dB re its peak (the amp contour)
  BRIGHT  the harmonic centroid over time, in harmonics (the filter contour:
          a sweep is the centroid rising and falling)
  PEAK    the harmonic standing most over its neighbours in the settled part,
          and by how much (the ladder's resonance)
  BEAT    the strongest slow beat on h1-h4 (two oscillators detuned)
"""
import os
import subprocess
import sys
import tempfile
import time

import mido
import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

REFS = os.path.expanduser("~/Documents/refs/soundfonts")
FONTS = (("GU", os.path.join(REFS, "GeneralUser-GS.sf2")),
         ("MS", os.path.join(REFS, "MuseScore_General.sf2")))
# variation: (program, bank, [(note, seconds held)], name)
VARS = {
    "38.8": (38, 8, [(33, 1.5), (45, 1.5)], "Synth Bass 3"),
    "39.8": (39, 8, [(33, 1.5), (45, 1.5)], "Synth Bass 4"),
    "50.8": (50, 8, [(48, 2.5), (60, 2.5)], "Syn.Strings 3"),
    "62.8": (62, 8, [(48, 1.5), (60, 1.5)], "Synth Brass 3"),
    "63.8": (63, 8, [(48, 2.0), (60, 2.0)], "Synth Brass 4"),
}
GAP = 1.0


def phrase_mid(prog, bank, notes, path, vel=100):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("control_change", channel=0, control=0, value=bank, time=0))
    t.append(mido.Message("program_change", channel=0, program=prog, time=0))
    first = 240
    for n, s in notes:
        t.append(mido.Message("note_on", channel=0, note=n, velocity=vel, time=first))
        t.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=int(s * 960)))
        first = int(GAP * 960)
    t.append(mido.MetaMessage("end_of_track", time=1920))
    m.save(path)


def target(font, var):
    """The font's take of the variation, mono at 48 kHz, and each note's
    (start, end) in seconds."""
    from scipy.signal import resample_poly
    prog, bank, notes, _ = VARS[var]
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "t.cfg")
        with open(cfg, "w") as f:
            f.write("bank %d\n%d %%font \"%s\" %d %d\n" % (bank, prog, font, bank, prog))
        mid, wav = os.path.join(d, "t.mid"), os.path.join(d, "t.wav")
        phrase_mid(prog, bank, notes, mid)
        subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", "48000",
                        "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sr, x = wavfile.read(wav)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    if sr != 48000:
        x = resample_poly(x, 48000, sr)
    spans, t = [], 0.25
    for n, s in notes:
        spans.append((n, t, t + s))
        t += s + GAP
    return x, spans


def harmonics(seg, f0, K=24, sr=48000):
    N = 1 << 16
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    out = []
    for k in range(1, K + 1):
        if k * f0 > 0.45 * sr:
            out.append(0.0)
            continue
        m = np.abs(f - k * f0) < 0.3 * f0
        out.append(float(X[m].max()) if m.any() else 0.0)
    return np.array(out)


def measure(x, n, t0, t1, sr=48000):
    f0 = 440.0 * 2 ** ((n - 69) / 12.0)
    a, b = int(t0 * sr), int((t1 + 0.6) * sr)
    y = x[a:b]
    hop = int(0.01 * sr)
    rms = np.array([np.sqrt((y[i:i + hop] ** 2).mean()) for i in range(0, len(y) - hop, hop)])
    lvl = 20 * np.log10(rms / (rms.max() + 1e-12) + 1e-9)
    win = int(max(0.05, 4.0 / f0) * sr)
    cents = []
    for ms in (10, 40, 80, 150, 300, 600, 1000):
        s = int(ms / 1000.0 * sr)
        if s + win > len(y):
            cents.append(float("nan"))
            continue
        h = harmonics(y[s:s + win], f0) ** 2
        k = np.arange(1, len(h) + 1)
        cents.append(float((h * k).sum() / (h.sum() + 1e-20)))
    s = int(min(0.6, (t1 - t0) * 0.6) * sr)
    h = 20 * np.log10(harmonics(y[s:s + int(0.3 * sr)], f0) + 1e-9)
    stand = [h[k] - 0.5 * (h[k - 1] + h[k + 1]) for k in range(1, len(h) - 1)]
    pk = int(np.argmax(stand))
    return dict(lvl=lvl, bright=cents, peak=(pk + 2, stand[pk]), h=h - h.max())


def show(var):
    prog, bank, notes, name = VARS[var]
    print("== %s %s" % (var, name))
    for tag, font in FONTS:
        x, spans = target(font, var)
        for n, t0, t1 in spans:
            m = measure(x, n, t0, t1)
            L = m["lvl"]
            idx = [0, 1, 2, 3, 5, 10, 20, 40, 80, int((t1 - t0) * 100) - 1, int((t1 - t0) * 100) + 10,
                   int((t1 - t0) * 100) + 30]
            print("  %s n%-3d level(0,10,20,30,50,100,200,400,800ms,end,+100,+300) %s"
                  % (tag, n, " ".join("%4.0f" % L[i] if i < len(L) else "  - " for i in idx)))
            print("         bright(10,40,80,150,300,600,1000ms) %s   peak h%d +%.1f dB"
                  % (" ".join("%5.1f" % c for c in m["bright"]), m["peak"][0], m["peak"][1]))
            print("         settled h1-16 %s" % " ".join("%4.0f" % v for v in m["h"][:16]))


# THE LAYOUT, as decoded (probe, 2026-10-19, Ben's Messenger on 1.1.0): in a
# Send Current Preset dump each knob is three bytes, a 16-bit value in 4+6+6
# bits under a 0x40 marker -- 0..8191 for a knob (v+1)/8192 of its travel,
# signed +-8191 about the centre for a bipolar one. A Send All Presets dump is
# a 58-byte header and the same layout every 961 bytes (offset o of preset k
# at o + 58 + 961 k). SYNC and KB TRACKING moved no byte; RES BASS only a
# byte that also moved with everything (a checksum's): not read.
KNOB_AT = {139: "tune", 142: "osc1_wave", 145: "osc1_level", 148: "osc2_freq", 151: "osc2_wave",
           154: "osc2_level", 157: "sub_wave", 160: "sub_level", 163: "mod_amount",
           166: "noise_level", 172: "cutoff", 175: "resonance", 178: "eg_amount",
           184: "f_attack", 187: "f_decay", 190: "f_sustain", 193: "f_release",
           196: "a_attack", 199: "a_decay", 202: "a_sustain", 205: "a_release",
           211: "lfo1_rate", 214: "lfo1_depth"}
BIPOLAR = ("tune", "osc2_freq", "mod_amount", "eg_amount", "lfo1_depth")
# switches: (byte, its values' step) -> the panel's position
SWITCH_AT = {"osc1_octave": (98, 4), "osc2_octave": (99, 1), "mode": (102, 1),
             "mod_dest": (101, 4), "lfo1_shape": (105, 1), "lfo1_dest": (107, 4)}


def word(b):
    v = ((b[0] & 0x0F) << 12) | (b[1] << 6) | b[2]
    return v - 0x10000 if v & 0x8000 else v


def panel_from_preset(d, at=0):
    """A Messenger preset (a Send Current Preset dump's bytes from `at`) as
    this model's panel knobs."""
    import moog as MG
    out = {}
    for o, k in KNOB_AT.items():
        v = word(d[at + o:at + o + 3])
        out[k] = 0.5 + v / (2.0 * 8191) if k in BIPOLAR else (v + 1) / 8192.0
    out["tune"] += MG._TUNE_TRIM
    for k, (o, step) in SWITCH_AT.items():
        q = (int(d[at + o]) // step) & 3
        out[k] = MG.FOOT_CC[q] if k.endswith("octave") else q
    return out


def bank_presets(d):
    """[panel] of a Send All Presets dump, preset 1 first."""
    n = (len(d) - 58) // 961
    return [panel_from_preset(d, 58 + 961 * k) for k in range(n)]


def probe_controls():
    """[(CC, panel knob, kind)] the decoding moves, each with its index (1..):
    every control on the Messenger's chart this model reads."""
    import moog as MG
    return [(cc, e[0], e[1]) for cc, e in sorted(MG.MESSENGER_CC.items()) if e]


LOW = {"14": 0.25, "tune": 0.45, "7": 0.25, "foot": 16, "track": 0.0, "mode": 0, "onoff": False}
HIGH = {"14": 0.75, "tune": 0.55, "7": 0.75, "foot": 4, "track": 1.0, "mode": 2, "onoff": True}


def probe(step, port="Messenger"):
    import moog as MG
    name = next(n for n in mido.get_output_names() if port.lower() in n.lower())
    sent = []
    with mido.open_output(name) as out:
        for i, (cc, knob, kind) in enumerate(probe_controls(), 1):
            hi = step > 0 and (i >> (step - 1)) & 1
            v = (HIGH if hi else LOW)[kind]
            msb, lsb = MG.messenger_cc_value(kind, v)
            out.send(mido.Message("control_change", channel=0, control=cc, value=msb))
            if lsb is not None:
                out.send(mido.Message("control_change", channel=0, control=cc + 32, value=lsb))
            time.sleep(0.004)
            if step == 0 or hi:
                sent.append(knob)
    print("step %d: %d controls set%s" % (step, len(sent), "" if step == 0 else ": " + " ".join(sent)))


PRESET_NOTES = ((33, 1.2), (45, 1.2), (57, 1.2))


def hardware_take(num, notes=PRESET_NOTES, card=1, port="Messenger"):
    """The Messenger's own preset `num` (1-128), loaded by program change and
    played over MIDI, recorded through the A6 (examples/messenger_fit.Rig)."""
    import messenger_fit as MF
    rig = MF.Rig(port=port, card=card)
    rig.out.send(mido.Message("control_change", channel=0, control=0, value=0))
    rig.out.send(mido.Message("control_change", channel=0, control=32, value=0))
    rig.out.send(mido.Message("program_change", channel=0, program=num - 1))
    time.sleep(0.3)

    def play(r):
        for n, s in notes:
            r.note(n, s, vel=100)
            time.sleep(GAP)
    x = rig.take("preset%d" % num, sum(s + GAP for _, s in notes) + 0.5, play)
    t0 = MF.PREROLL + 0.5
    return x, [(n, t - rig.t0 * 0 + 0.0, s) for (n, s), t in zip(notes, rig.played)]


def hardware_from_cc(num, panel, notes=PRESET_NOTES, card=1, port="Messenger"):
    """The Messenger with preset `num` loaded and then its DECODED panel sent
    back over CC (only the controls decoded): the same as hardware_take if
    the decode holds the whole preset, different if the preset holds more."""
    import messenger_fit as MF
    import moog as MG
    rig = MF.Rig(port=port, card=card)
    rig.out.send(mido.Message("control_change", channel=0, control=0, value=0))
    rig.out.send(mido.Message("control_change", channel=0, control=32, value=0))
    rig.out.send(mido.Message("program_change", channel=0, program=num - 1))
    time.sleep(0.3)
    rig.panel(dict(MG.PANEL, **panel), knobs=set(panel))
    time.sleep(0.3)

    def play(r):
        for n, s in notes:
            r.note(n, s, vel=100)
            time.sleep(GAP)
    return rig.take("preset%d_cc" % num, sum(s + GAP for _, s in notes) + 0.5, play)


def ours_take(panel, notes=PRESET_NOTES, prog=38):
    """Ours from that panel: the same notes, the same lengths."""
    import json
    import sfx_variations as V
    env = dict(panel, kb_track=1.0, sync=False, res_bass=False)
    os.environ["TUNING_MOOG_PANEL"] = json.dumps(env)
    try:
        ev, t = [(0, "pc", 0, prog, 0)], 0.25
        for n, s in notes:
            ev += [(t, "on", 0, n, 100), (t + s, "off", 0, n, 0)]
            t += s + GAP
        x = V.render(V.midi(ev, t + 0.5)).mean(1)
    finally:
        os.environ.pop("TUNING_MOOG_PANEL", None)
    # THE RENDERER RUNS AT ITS OWN RATE (blockrender.SR, 44.1 kHz), the A6 at
    # 48: read as 48 kHz, ours played 146 cents sharp and 9% fast
    return to48(x), 0.25


def to48(x):
    import blockrender as B
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(48000, B.SR)
    return resample_poly(x, 48000 // g, B.SR // g, axis=0) if B.SR != 48000 else x


def presets_ab(syx, nums, out):
    """Per preset: the Messenger's take, then ours, written side by side."""
    d = np.frombuffer(open(syx, "rb").read(), dtype=np.uint8)[1:-1]
    P = bank_presets(d)
    for num in nums:
        hw, played = hardware_take(num)
        ob, _ = ours_take(P[num - 1])
        on = np.flatnonzero(np.abs(hw) > 0.05 * np.abs(hw).max())
        h0 = int(on[0]) if len(on) else 0
        oo = np.flatnonzero(np.abs(ob) > 0.05 * np.abs(ob).max())
        o0 = int(oo[0]) if len(oo) else 0
        seg = int(sum(s + GAP for _, s in PRESET_NOTES) * 48000)
        a = hw[h0:h0 + seg] / (np.abs(hw).max() + 1e-12)
        b = ob[o0:o0 + seg] / (np.abs(ob).max() + 1e-12)
        y = np.concatenate([a, np.zeros(int(0.8 * 48000)), b]) * 0.5
        path = os.path.join(out, "messenger_preset%02d_hw_vs_ours.wav" % num)
        wavfile.write(path, 48000, (y * 32767).astype(np.int16))
        print("  preset %d: %s" % (num, path))


# what each is heard in: a bass line two octaves down, stabs and a line for
# brass, held chords for strings -- (beat, note, beats), at 120
BASSLINE = [(i * 0.5, n, 0.4) for i, n in enumerate([33, 33, 45, 33, 36, 38, 40, 43,
                                                    33, 33, 45, 33, 31, 31, 43, 40])] + [(8.0, 33, 2.0)]
STABS = ([(b, n, 0.35) for b in (0.0, 1.0, 1.5, 3.0) for n in (55, 60, 64, 67)]
         + [(4.0 + i * 0.5, n, 0.45) for i, n in enumerate([67, 69, 71, 72, 74, 72, 71, 67])]
         + [(8.0, n, 2.0) for n in (48, 55, 60, 64, 67)])
PADS = [(b, n, 1.9) for b, ch in ((0, (48, 55, 60, 64)), (2, (45, 52, 57, 60)), (4, (41, 48, 53, 57)),
                                  (6, (43, 50, 55, 59))) for n in ch] + [(8.0, n, 3.0) for n in (48, 55, 60, 64, 67)]
AB_PHRASE = {"38.8": BASSLINE, "39.8": BASSLINE, "50.8": PADS, "62.8": STABS, "63.8": STABS}


def ab(var, out):
    """The capital tone, a bar's rest, then the variation: one normalisation."""
    import sfx_variations as V
    prog, bank, _, name = VARS[var]
    ph = AB_PHRASE[var]
    span = max(b + d for b, _, d in ph) * 0.5 + 1.5

    def take(bk):
        ev = [(0, "cc", 0, 0, bk), (0, "pc", 0, prog, 0)]
        for b, n, d in ph:
            ev += [(0.25 + b * 0.5, "on", 0, n, 96), (0.25 + (b + d) * 0.5, "off", 0, n, 0)]
        return V.render(V.midi(ev, span))
    a, b = to48(take(0)), to48(take(bank))
    pk = max(np.abs(a).max(), np.abs(b).max()) + 1e-12
    y = np.concatenate([a, np.zeros((int(1.0 * 48000), a.shape[1])), b]) / pk * 0.8
    path = os.path.join(out, "gs_%s_%s.wav" % (var.replace(".", "_"), name.replace(" ", "").replace(".", "")))
    wavfile.write(path, 48000, (y * 32767).astype(np.int16))
    print("  %s %s: %s" % (var, name, path))


if __name__ == "__main__":
    which = sys.argv[2:] or list(VARS)
    which = [w for w in which if w in VARS]
    if sys.argv[1] == "target":
        for v in which:
            show(v)
    elif sys.argv[1] == "ab":
        for v in [w for w in sys.argv[3:] if w in VARS] or list(VARS):
            ab(v, sys.argv[2])
    elif sys.argv[1] == "probe":
        probe(int(sys.argv[2]))
    elif sys.argv[1] == "presets":
        presets_ab(sys.argv[2], [int(v) for v in sys.argv[3:]],
                   os.environ.get("OUT", os.path.expanduser("~/Downloads")))
