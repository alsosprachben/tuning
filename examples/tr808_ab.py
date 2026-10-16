#!/usr/bin/env python3
"""The TR-808 set (program 25 on the drum channel) for the ear.

    python3 -I examples/tr808_ab.py [OUTDIR]          # default ~/Downloads/tr808_ab

Writes three files:
Both grooves are LOUDNESS-matched (K-weighted, LOUD_DB), not peak-normalized.

  ours.mp3    eight bars of an 808 groove -- kick, snare, sixteenth hats with
              an open one, rim shot and claves, cowbell, congas, a fill down
              the six toms, a cymbal to land on -- then each note alone
  fluid.mp3   the same file through FluidR3's TR-808 set (Fischer's own
              recordings, repitched on some toms; timidity, measured only, a
              local reference, never redistributed)
  pairs.mp3   each note's fitted hit from Michael Fischer's 808, then ours,
              level-matched -- the fit's own comparison (examples/tr808_fit.py)
"""
import os
import subprocess
import sys
import tempfile
import warnings

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")
TPB = 480
ALONE = (36, 37, 38, 41, 43, 45, 47, 48, 50, 42, 46, 49, 56, 62, 63, 64, 70, 75)
FLUID = "/usr/share/sounds/sf2/FluidR3_GM.sf2"


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 100), time=0))
    tr.append(mido.Message("program_change", channel=9, program=25, time=0))
    ev, s16 = [], TPB // 4
    for bar in range(8):
        t0 = bar * 4 * TPB
        for k in range(16):
            if k == 14:
                ev.append((t0 + k * s16, 46, 85))                  # the open hat, choked
            else:
                ev.append((t0 + k * s16, 42, 95 if k % 4 == 0 else 65))
        ev += [(t0, 36, 115), (t0 + 10 * s16, 36, 100)]
        if bar % 2:
            ev.append((t0 + 7 * s16, 36, 90))
        ev += [(t0 + 4 * s16, 38, 110), (t0 + 12 * s16, 38, 110)]
        if bar >= 2:
            ev += [(t0 + 3 * s16, 37, 80), (t0 + 11 * s16, 75, 80)]
        if bar >= 4:
            ev += [(t0 + 2 * s16, 56, 90), (t0 + 6 * s16, 56, 80), (t0 + 9 * s16, 62, 85),
                   (t0 + 13 * s16, 63, 85), (t0 + 15 * s16, 64, 90), (t0 + 5 * s16, 70, 70),
                   (t0 + 13 * s16, 70, 70)]
        if bar == 7:
            ev = [e for e in ev if not (e[0] >= t0 + 8 * s16 and e[1] in (38, 42, 46, 56, 62, 63, 64))]
            for k, n in enumerate((50, 48, 47, 45, 43, 41)):
                ev.append((t0 + 8 * s16 + k * s16 + (s16 if k > 3 else 0), n, 105))
    t = 8 * 4 * TPB
    ev.append((t, 36, 115)); ev.append((t, 49, 105))
    t += 6 * TPB
    for n in ALONE:
        ev.append((t, n, 105)); t += 2 * TPB
    msgs = sorted([(at, 1, n, v) for at, n, v in ev] + [(at + 60, 0, n, 0) for at, n, _v in ev])
    now = 0
    for at, on, n, v in msgs:
        tr.append(mido.Message("note_on" if on else "note_off", channel=9, note=n, velocity=v,
                               time=at - now)); now = at
    tr.append(mido.MetaMessage("end_of_track", time=4 * TPB))
    m.save(path)


LOUD_DB = -26.0      # the groove's K-weighted level, both files


def finish(dry, out):
    """Reverb, then the groove (its first eight bars) set to LOUD_DB
    K-weighted. LOUDNESS, NOT PEAK: peak-normalized, ours -- sharper
    transients for its loudness -- played ~6 dB under FluidR3's, and its kick
    read quieter for it (Ben: "Maybe it is the normalization")."""
    from scipy.io import wavfile
    from kit_levels import kweight
    wet = dry[:-8] + ".wet.wav"
    subprocess.check_call(["sox", dry, wet, "reverb", "30", "50", "50", "100", "0", "-9"])
    sr, x = wavfile.read(wet)
    x = x.astype(np.float64) / (32768.0 if x.dtype == np.int16 else 1.0)
    m = x.mean(1) if x.ndim > 1 else x
    groove = kweight(m[:int(8 * 4 * 0.6 * sr)], sr)
    g = 10 ** ((LOUD_DB - 10 * np.log10(np.mean(groove ** 2) + 1e-20)) / 20.0)
    y = x * g
    if np.abs(y).max() > 0.99:
        print("  (%s clips by %.1f dB at %.0f dB K: lowered)" % (os.path.basename(out),
              20 * np.log10(np.abs(y).max() / 0.99), LOUD_DB))
        y *= 0.99 / np.abs(y).max()
    norm = dry[:-8] + ".norm.wav"
    wavfile.write(norm, sr, (y * 32767).astype(np.int16))
    subprocess.check_call(["lame", "-b", "256", "--quiet", norm, out])
    for f in (dry, wet, norm):
        os.remove(f)
    print("  -> " + out)


def pairs(out, d):
    from scipy.io import wavfile
    import tr808_fit as F
    sr = 44100
    gap = np.zeros(int(0.35 * sr))
    chunks = []
    for n in ALONE:
        y, _ = F.hit(F.HITS[n])
        x, _ = F.ours(n, d)
        for z in (y, x):
            z = np.asarray(z, float)
            z = z[max(0, F.onset(z) - 100):][:int(1.4 * sr)]
            z = 0.5 * z / (np.sqrt(np.mean(z[:int(0.15 * sr)] ** 2)) * 6 + 1e-12)
            chunks += [z, gap]
        chunks.append(gap)
    w = np.concatenate(chunks)
    w = 0.9 * w / np.abs(w).max()
    dry = os.path.join(os.path.dirname(out), "pairs.dry.wav")
    wavfile.write(dry, sr, (w * 32767).astype(np.int16))
    subprocess.check_call(["lame", "-b", "256", "--quiet", dry, out])
    os.remove(dry)
    print("  -> " + out)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/tr808_ab")
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "groove.mid")
    build(mid)
    env = dict(os.environ, TUNING_REFLECT="0")
    subprocess.check_call([sys.executable, os.path.join(HERE, "blockrender.py"), mid,
                           os.path.join(out, "ours.dry.wav"), "hybrid"], env=env, cwd=HERE)
    finish(os.path.join(out, "ours.dry.wav"), os.path.join(out, "ours.mp3"))
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "k.cfg")
        with open(cfg, "w") as f:
            f.write("drumset 25\n")
            for n in range(27, 88):
                f.write('%d %%font "%s" 128 25 %d\n' % (n, FLUID, n))
        subprocess.check_call(["timidity", "-c", cfg, "-Ow", "-o", os.path.join(out, "fluid.dry.wav"),
                               "-s", "44100", "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finish(os.path.join(out, "fluid.dry.wav"), os.path.join(out, "fluid.mp3"))
        pairs(os.path.join(out, "pairs.mp3"), d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
