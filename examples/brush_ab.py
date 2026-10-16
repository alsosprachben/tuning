#!/usr/bin/env python3
"""The Brush set (program 40 on the drum channel) for the ear.

    python3 -I examples/brush_ab.py [OUTDIR]          # default ~/Downloads/brush_ab

Writes three files, the two grooves LOUDNESS-matched (K-weighted, as
examples/tr808_ab.py):
  ours.mp3    eight bars of brushes in a slow swing -- a swirl on every beat,
              taps on the swung eighths, slaps on the accents, Standard's
              kick feathered and hi-hat foot on 2 and 4 -- then each note alone
  gu.mp3      the same file through GeneralUser GS's Brush set (timidity:
              measured only, a local reference, never redistributed)
  pairs.mp3   Swirly Drums' tap and dig (CC0), each then ours; GeneralUser's
              swirl (the gesture it was fitted to), then ours
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
import tr808_ab as A          # noqa: E402  (finish: reverb and loudness)

TPB = 480
GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
SWIRLY = os.path.expanduser("~/Documents/refs/swirly_drums_karoryfer")
A.LOUD_DB = -32.0      # neither file may clip


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 84), time=0))
    tr.append(mido.Message("program_change", channel=9, program=40, time=0))
    ev, q = [], TPB
    swing = int(q * 2 / 3)
    for bar in range(8):
        t0 = bar * 4 * q
        for b in range(4):
            ev.append((t0 + b * q, 40, 80))                       # the swirl, each beat
            ev.append((t0 + b * q + swing, 38, 55 + (b % 2) * 10))   # the swung "and"
            if b in (1, 3):
                ev.append((t0 + b * q, 44, 70))                   # hi-hat foot, 2 and 4
            ev.append((t0 + b * q, 36, 40))                       # kick, feathered
        if bar % 2 == 1:
            ev.append((t0 + 3 * q + swing, 39, 100))              # a slap to end the phrase
        if bar == 7:
            ev += [(t0 + 2 * q + k * (q // 3), 38, 60 + 6 * k) for k in range(6)]
    t = 8 * 4 * q + 2 * q
    ev.append((t, 39, 110)); ev.append((t, 36, 70))
    t += 6 * q
    for n in (38, 39, 40):
        ev.append((t, n, 100)); t += 3 * q
    msgs = sorted([(at, 1, n, v) for at, n, v in ev] + [(at + 60, 0, n, 0) for at, n, _v in ev])
    now = 0
    for at, on, n, v in msgs:
        tr.append(mido.Message("note_on" if on else "note_off", channel=9, note=n,
                               velocity=max(1, min(127, v)), time=at - now)); now = at
    tr.append(mido.MetaMessage("end_of_track", time=8 * q))
    m.save(path)


def pairs(out, d):
    from scipy.io import wavfile
    import tr808_fit as F
    import elkit_fit as E           # after tr808_fit, which sets E.KIT = 25 on import
    E.KIT = 40
    sr = 44100
    gap = np.zeros(int(0.4 * sr))
    chunks = []

    def swirly(p):
        a, _ = E.read(p)
        b, _ = E.read(p.replace("_top.wav", "_btm.wav"))
        n = min(len(a), len(b))
        return a[:n] + b[:n]
    refs = ((38, swirly(os.path.join(SWIRLY, "snare_main", "snare_hit_vl8_rr1_top.wav"))),
            (39, swirly(os.path.join(SWIRLY, "snare_dig", "snare_dig_vl3_rr1_top.wav"))),
            (40, E.theirs(GU, 40, d)[0]))
    for n, y in refs:
        x, _ = E.ours(n, d)
        for z in (y, x):
            z = np.asarray(z, float)
            z = z[max(0, F.onset(z) - 100):][:int(1.6 * sr)]
            z = 0.5 * z / (np.sqrt(np.mean(z[:int(0.3 * sr)] ** 2)) * 6 + 1e-12)
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
    out = args[0] if args else os.path.expanduser("~/Downloads/brush_ab")
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "brush.mid")
    build(mid)
    env = dict(os.environ, TUNING_REFLECT="0")
    subprocess.check_call([sys.executable, os.path.join(HERE, "blockrender.py"), mid,
                           os.path.join(out, "ours.dry.wav"), "hybrid"], env=env, cwd=HERE)
    A.finish(os.path.join(out, "ours.dry.wav"), os.path.join(out, "ours.mp3"))
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "k.cfg")
        with open(cfg, "w") as f:
            f.write("drumset 40\n")
            for n in range(27, 88):
                f.write('%d %%font "%s" 128 40 %d\n' % (n, GU, n))
        subprocess.check_call(["timidity", "-c", cfg, "-Ow", "-o", os.path.join(out, "gu.dry.wav"),
                               "-s", "44100", "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        A.finish(os.path.join(out, "gu.dry.wav"), os.path.join(out, "gu.mp3"))
        pairs(os.path.join(out, "pairs.mp3"), d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
