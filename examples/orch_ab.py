#!/usr/bin/env python3
"""The Orchestra set (program 48 on the drum channel) for the ear.

    python3 -I examples/orch_ab.py [OUTDIR]           # default ~/Downloads/orch_ab

Writes three files, the two grooves LOUDNESS-matched (K-weighted, as
examples/tr808_ab.py):
  ours.mp3    sixteen bars of concert percussion -- timpani on tonic and
              dominant with a roll, bass drum and clashes on the downbeats,
              a snare's march figure and a roll, castanets, hi-hats, a
              crescendo to a final clash -- then applause, then each new note
              alone
  gu.mp3      the same file through GeneralUser GS's Orchestra set (timidity:
              measured only, a local reference, never redistributed)
  pairs.mp3   each fitted note's VCSL hit (examples/orch_fit.py), then ours
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
ALONE = (36, 35, 38, 39, 41, 45, 48, 53, 57, 59, 27, 29, 30)
A.LOUD_DB = -39.0     # the crescendo ends 12 dB over the groove: neither file may clip


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 96), time=0))
    tr.append(mido.Message("program_change", channel=9, program=48, time=0))
    ev, q, e8, s16 = [], TPB, TPB // 2, TPB // 4
    for bar in range(16):
        t0 = bar * 4 * q
        loud = 50 + bar * 4
        # timpani: tonic (c = 48) and dominant (G = 43), a roll into bar 8 and 16
        ev += [(t0, 48 if bar % 2 == 0 else 43, loud + 10), (t0 + 2 * q, 43 if bar % 2 == 0 else 48, loud)]
        if bar in (7, 15):
            ev += [(t0 + 2 * q + k * s16 // 2, 43, loud - 10 + k) for k in range(16)]
        # bass drum on the downbeat; a clash every four bars
        ev.append((t0, 36 if bar % 4 == 0 else 35, loud + 15))
        if bar % 4 == 0:
            ev.append((t0, 59 if bar % 8 == 0 else 57, loud + 20))
        # the snare's march figure, rolling in bars 12-15
        if 4 <= bar < 12:
            ev += [(t0 + q, 38, loud), (t0 + q + 3 * s16, 40, loud - 15), (t0 + 3 * q, 38, loud)]
        elif bar >= 12:
            ev += [(t0 + k * s16 // 2, 38 if k % 2 else 40, 40 + bar * 3 + k // 4) for k in range(32)]
        # castanets and hats in the middle
        if 6 <= bar < 10:
            ev += [(t0 + k * e8, 39, 70) for k in range(8)]
            ev += [(t0 + q * k, 27 if k % 2 else 28, 60) for k in range(4)] + [(t0 + 3 * q + e8, 29, 70)]
        if 8 <= bar < 12:
            ev += [(t0 + q * k, 30, 70) for k in range(4)]
    t = 16 * 4 * q
    ev += [(t, 36, 127), (t, 59, 127), (t, 57, 120), (t, 41, 120), (t, 53, 120)]
    t += 6 * q
    ev.append((t, 88, 100))
    t += 8 * q
    for n in ALONE:
        ev.append((t, n, 105)); t += 3 * q
    msgs = sorted([(at, 1, n, v) for at, n, v in ev] + [(at + 60, 0, n, 0) for at, n, _v in ev])
    now = 0
    for at, on, n, v in msgs:
        tr.append(mido.Message("note_on" if on else "note_off", channel=9, note=n,
                               velocity=max(1, min(127, v)), time=at - now)); now = at
    tr.append(mido.MetaMessage("end_of_track", time=8 * q))
    m.save(path)


def pairs(out, d):
    from scipy.io import wavfile
    import elkit_fit as E
    import orch_fit as O
    import tr808_fit as F
    E.KIT = 48
    sr = 44100
    gap = np.zeros(int(0.4 * sr))
    chunks = []
    for n in (36, 35, 38, 59, 57):
        y, _ = O.load(os.path.join(O.VCSL, O.HITS[n]))
        x, _ = E.ours(n, d)
        for z in (y, x):
            z = np.asarray(z, float)
            z = z[max(0, F.onset(z) - 100):][:int(3.0 * sr)]
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
    out = args[0] if args else os.path.expanduser("~/Downloads/orch_ab")
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "orch.mid")
    build(mid)
    # the groove's loudness is read over its first 16 bars (tr808_ab reads 8 at
    # 100 bpm: the same span in seconds is 16 bars' first ~19 s here)
    env = dict(os.environ, TUNING_REFLECT="0")
    subprocess.check_call([sys.executable, os.path.join(HERE, "blockrender.py"), mid,
                           os.path.join(out, "ours.dry.wav"), "hybrid"], env=env, cwd=HERE)
    A.finish(os.path.join(out, "ours.dry.wav"), os.path.join(out, "ours.mp3"))
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "k.cfg")
        with open(cfg, "w") as f:
            f.write("drumset 48\n")
            for n in range(27, 89):
                f.write('%d %%font "%s" 128 48 %d\n' % (n, GU, n))
        subprocess.check_call(["timidity", "-c", cfg, "-Ow", "-o", os.path.join(out, "gu.dry.wav"),
                               "-s", "44100", "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        A.finish(os.path.join(out, "gu.dry.wav"), os.path.join(out, "gu.mp3"))
        pairs(os.path.join(out, "pairs.mp3"), d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
