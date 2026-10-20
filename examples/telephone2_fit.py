#!/usr/bin/env python3
"""GS 124.1 "Telephone 2": an ELECTRONIC TONE RINGER, fitted to GeneralUser
GS's own tone (no recording of the SC-55's; as the orchestra hit was).

    python3 examples/telephone2_fit.py measure     GU's ringer, read
    python3 examples/telephone2_fit.py fit         the panel, by grid

What GU plays (C4, the key it rings at its own pitch): two tones a fifth
apart, 1824 and 2732 Hz, switching every 34 ms (a 14.6 Hz warble), the upper
~10 dB under the lower; each nearly pure (A: h2 -11, h3 -28 dB; B: h2 -35);
ringing as long as the key is held, gone ~50 ms after it. That is a tone
ringer chip: an oscillator, a square LFO switching its pitch, and a piezo
disc whose resonance favours the lower tone -- a small synth, so the Moog
plays it: OSC 2, LFO 1 square on the pitch, the ladder as BAND PASS standing
in for the disc.
"""
import json
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

SF = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
F_A, F_B, RATE = 1824.0, 2732.0, 14.6
SR = 48000


def gu_take():
    with tempfile.TemporaryDirectory() as d:
        cfg, mid, wav = (os.path.join(d, n) for n in ("t.cfg", "t.mid", "t.wav"))
        open(cfg, "w").write('bank 1\n124 %%font "%s" 1 124\n' % SF)
        m = mido.MidiFile(ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("control_change", control=0, value=1))
        t.append(mido.Message("program_change", program=124))
        t.append(mido.Message("note_on", note=60, velocity=100, time=240))
        t.append(mido.Message("note_off", note=60, velocity=0, time=int(2.0 * 960)))
        t.append(mido.MetaMessage("end_of_track", time=960))
        m.save(mid)
        subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", str(SR), "-EFreverb=d",
                        "-EFchorus=d", "--quiet=2", mid], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sr, x = wavfile.read(wav)
    x = x.astype(float)
    x = x.mean(1) if x.ndim > 1 else x
    return x / np.abs(x).max()


def phases(x):
    """(A's h1-4 dB re its h1, B's, B's level re A's, the switch rate Hz) of
    a take: its 5 ms frames split by which tone is sounding (zero crossings),
    the middle of each run's spectrum averaged."""
    from scipy.signal import butter, sosfiltfilt
    on = np.flatnonzero(np.abs(x) > 0.05)
    s = x[on[0] + int(0.1 * SR):on[0] + int(1.6 * SR)]
    hop = int(0.005 * SR)
    y = sosfiltfilt(butter(4, [1300, 3300], btype="band", fs=SR, output="sos"), s)
    zc = np.flatnonzero((y[:-1] < 0) & (y[1:] >= 0))
    fr = []
    for i in range(0, len(s) - hop, hop):
        z = zc[(zc >= i) & (zc < i + hop)]
        fr.append((len(z) - 1) / ((z[-1] - z[0]) / SR) if len(z) > 2 else 0.0)
    fr = np.array(fr)
    isb = fr > np.sqrt(F_A * F_B)
    out = {}
    for tag, mask, f0 in (("A", ~isb, F_A), ("B", isb, F_B)):
        P = None
        for i in np.flatnonzero(mask[1:-1] & mask[:-2] & mask[2:]) + 1:
            seg = s[i * hop - 240:i * hop + 480]
            X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 15)) ** 2
            P = X if P is None else P + X
        f = np.fft.rfftfreq(1 << 15, 1.0 / SR)
        h = [10 * np.log10(P[(f > k * f0 * 0.95) & (f < k * f0 * 1.05)].max() + 1e-20) for k in range(1, 5)]
        out[tag] = np.array(h)
        out[tag + "n"] = mask.sum()
    sw = np.flatnonzero(np.diff(isb.astype(int)) != 0)
    rate = (len(sw) - 1) / 2.0 / ((sw[-1] - sw[0]) * hop / SR) if len(sw) > 2 else 0.0
    return out["A"] - out["A"][0], out["B"] - out["B"][0], out["B"][0] - out["A"][0], rate


def ours(panel):
    import patch_map as P
    import sfx_variations as V
    os.environ["TUNING_MOOG_PANEL"] = json.dumps(panel)
    try:
        x = V.render(V.midi([(0, "cc", 0, 0, 1), (0, "pc", 0, 124, 0), (0.25, "on", 0, 60, 100),
                             (2.25, "off", 0, 60, 0)], 2.8)).mean(1)
    finally:
        os.environ.pop("TUNING_MOOG_PANEL", None)
    import messenger_variations as MV
    x = MV.to48(x)                  # the renderer's 44.1 kHz, read here at 48
    return x / (np.abs(x).max() + 1e-12)


def score(t, o):
    return float(np.sqrt(np.mean(np.concatenate([(t[0] - o[0])[1:] ** 2, (t[1] - o[1])[1:] ** 2,
                                                  [(t[2] - o[2]) ** 2 * 4]]))))


def fit():
    import moog as MG
    t = phases(gu_take())
    print("  GU: A %s  B %s  B re A %.1f dB  %.1f Hz" % (np.round(t[0]), np.round(t[1]), t[2], t[3]))
    best = None
    for wave in (MG.SAW, 0.6):
        for res in (0.35, 0.42, 0.5):
            for off in (-0.25, 0.0, 0.15):
                pan = panel(wave, res, off)
                o = phases(ours(pan))
                s = score(t, o)
                print("    wave %.3f res %.2f corner %+.1f oct: A %s B %s B-A %.1f rate %.1f -> %.2f"
                      % (wave, res, off, np.round(o[0][1:]), np.round(o[1][1:]), o[2], o[3], s), flush=True)
                if best is None or s < best[0]:
                    best = (s, wave, res, off)
    print("  best: wave %.3f resonance %.2f corner %+.1f oct (%.2f dB)" % (best[1], best[2], best[3], best[0]))
    print("  panel:", json.dumps(panel(*best[1:])))


def panel(wave, res, off):
    """The ringer's panel: OSC 2 at the key (LFO 1's pitch destination is OSC 2
    FREQ, on the Messenger), LFO 1 a square on its pitch up a
    fifth at RATE, the ladder a band pass `off` octaves from the lower tone."""
    import moog as MG
    import tonelib as T
    f0 = 261.6256 * 2 ** T.MoogTelephone2.sounding_octaves
    return dict(osc2_wave=wave, osc1_level=0.0, osc2_level=1.0, osc2_freq=0.5, sub_level=0.0, noise_level=0.0,
                mode=MG.BP, kb_track=1.0, resonance=res, eg_amount=0.5,
                cutoff=MG.cutoff_knob(F_A * 2 ** off / (f0 / MG.KB_REF_HZ)),
                f_attack=0.0, f_decay=0.4, f_sustain=1.0, f_release=0.05,
                a_attack=0.0, a_decay=0.4, a_sustain=1.0, a_release=0.08,
                lfo1_shape=3, lfo1_dest=1, lfo1_rate=MG.lfo_rate_knob(RATE),
                lfo1_depth=MG.lfo_pitch_knob(np.log2(F_B / F_A)), lfo1_reset=True,
                mod_amount=0.5)


if __name__ == "__main__":
    if sys.argv[1] == "measure":
        t = phases(gu_take())
        print("  GU: A %s  B %s  B re A %.1f dB  %.1f Hz" % (np.round(t[0]), np.round(t[1]), t[2], t[3]))
    else:
        fit()
