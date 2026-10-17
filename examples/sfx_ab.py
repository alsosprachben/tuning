#!/usr/bin/env python3
"""The SFX set (program 56 on the drum channel) for the ear.

    python3 -I examples/sfx_ab.py [OUTDIR]           # default ~/Downloads/sfx_ab
    python3 -I examples/sfx_ab.py --vehicles [OUTDIR] # the vehicles (63-71)
    python3 -I examples/sfx_ab.py --rest [OUTDIR]     # the rest (39-62, 73-75)
    python3 -I examples/sfx_ab.py --ours [OUTDIR]     # ours alone, every key in order, as a file
                                                      # plays it (one render: the set's balance)

For each key fitted to a recording (examples/weather_fit.py: rain, thunder,
wind, stream; bubble from its recording's events): the recording -- a stretch
as long as the key's gate, from where it sounds, faded in and out -- then
ours, then GeneralUser GS's sample on the key (timidity: measured only, a
local reference, never redistributed). Each item level-matched by its rms:
the character is what is compared, the balance is elkit_balance's.
"""
import os
import subprocess
import sys
import tempfile
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")
os.environ["TUNING_REFLECT"] = "0"

GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
R = os.path.expanduser("~/Documents/refs/freesound")
KEYS = ((79, "rain/200273__jmbphilmes__rain-light-2-rural.wav"),
        (80, "thunder/446753__bluedelta__heavy-thunder-strike-no-rain-quadro.wav"),
        (81, "wind/117611__swiftoid__wind_howl2_stereo.wav"),
        (83, "stream/382322__sterferny__stream.wav"),
        (84, "bubbles/539823__ristooooo1__bubbles-001.wav"))
# the vehicles: (key, weather_fit voice) -- the recording read from the
# stretch it was fitted to (weather_fit.SEGMENT)
VEHICLES = ((63, "engine"), (66, "crash"), (68, "train"), (69, "jet"),
            (64, "skid"), (65, "carpass"), (67, "siren"), (71, "starship"))
# ...and the one weather_fit does not fit (no noise): its wind-up
SIREN = ("siren/819369__sapperlapje__fire-truck-siren.wav", (0.3, 2.3))
# THE REST (39-75), --rest: (key, the recording's file or None, its stretch).
# The struck ones a hit as examples/freesound_slice.py cut it; the High Q and
# Square Click have none (GeneralUser's sample is the reference: ours, then
# it). The applause and bubble again: Standard's vibraslap train and bell-tree
# cascade no longer play on them (percussion_map.rasp_strokes)
REST = ((39, None, None), (40, "slap/hits/slap_01.wav", None), (41, "scratch/610676__liftpizzas__scratch-4x.wav", (0.12, 0.55)),
        (42, "scratch/610676__liftpizzas__scratch-4x.wav", (0.4, 0.8)), (43, "sticks/hits/sticks_01.wav", None),
        (44, None, None), (45, "metronome/hits/metronome_01.wav", None), (46, "metronome/hits/bell_01.wav", None),
        (48, "guitarcut/hits/cutdown_01.wav", None), (49, "guitarcut/hits/cutup_01.wav", None),
        (50, "bassslap/hits/bassslap_01.wav", None), (51, "keyclick/hits/keyclick_01.wav", None),
        (59, "doorcreak/316683__alex_hears_things__slow-door-hinges_nm.wav", (0.55, 3.4)),
        (60, "door/hits/door_01.wav", None), (61, "scratch/128645__cityrocker__arrgh-scratch-wicked.wav", (0.05, 0.6)),
        (62, "windchime/hits/chime_01.wav", None),
        (73, "machinegun/693546__areniporgen__colt-m16a1.wav", (5.37, 6.9)),
        (74, "laser/819682__hotpin7__blaster-pew.wav", None),
        (75, "explosion/251401__felixblume__dynamite-explosion-in-the-mountain.wav", (0.0, 2.1)),
        (58, None, None), (84, "bubbles/539823__ristooooo1__bubbles-001.wav", None))


def excerpt(path, secs, seg=None):
    import weather_fit as W
    x, sr = W.load(path, seg)
    w = int(0.05 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    a = int(np.argmax(e > e.max() * 0.3))           # where it sounds
    x = x[a:a + int(max(secs, 0.6) * sr)]
    r = np.linspace(0, 1, int(0.03 * sr))
    x[:len(r)] *= r
    x[-len(r):] *= r[::-1]
    return x


def ours_in_order(out):
    """Every key of the set, low to high, each after the last has rung out,
    in ONE render on the drum channel -- the levels the set plays at."""
    import mido
    import percussion_map as P
    import blockrender as B
    from scipy.io import wavfile
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))      # 960 ticks a second
    t.append(mido.Message("program_change", channel=9, program=56, time=0))
    gap = 0
    for key in sorted(P.KITS[56]):
        ring = P.KIT_GATE[56].get(key, 1.0) + 0.6
        t.append(mido.Message("note_on", channel=9, note=key, velocity=100, time=gap))
        t.append(mido.Message("note_off", channel=9, note=key, velocity=0, time=60))
        gap = int(ring * 960) - 60
        print("  %d %s" % (key, P.KITS[56][key][0]))
    t.append(mido.MetaMessage("end_of_track", time=gap + 960))
    L, R = B.render(m)[:2]
    w = np.stack([np.asarray(L, float), np.asarray(R, float)], 1)
    w = 0.9 * w / np.abs(w).max()
    dry = os.path.join(out, "ours.dry.wav")
    wavfile.write(dry, B.SR, (w * 32767).astype(np.int16))
    subprocess.check_call(["lame", "-b", "256", "--quiet", dry, os.path.join(out, "sfx_ours.mp3")])
    os.remove(dry)
    print("  -> " + os.path.join(out, "sfx_ours.mp3"))


def main(argv):
    from scipy.io import wavfile
    import elkit_fit as E
    import percussion_map as P
    E.KIT = 56
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/sfx_ab")
    import weather_fit as W
    if "--ours" in argv:
        ours_in_order(out)
        return 0
    if "--rest" in argv:
        keys = list(REST)
        name = "rest.mp3"
        only = next((a.split("=")[1] for a in argv if a.startswith("--keys=")), None)
        if only:
            # --keys=48,49: just those, into their own file
            keys = [k for k in keys if str(k[0]) in only.split(",")]
            name = "keys_%s.mp3" % only.replace(",", "_")
    elif "--vehicles" in argv:
        keys = [(k,) + (SIREN if v == "siren" else (W.VOICES[v][2], W.SEGMENT.get(v))) for k, v in VEHICLES]
        name = "vehicles.mp3"
    else:
        keys = [(k, p, None) for k, p in KEYS]
        name = "weather.mp3"
    os.makedirs(out, exist_ok=True)
    sr = 44100
    gap = np.zeros(int(0.5 * sr))
    chunks = []
    with tempfile.TemporaryDirectory() as d:
        for key, path, seg in keys:
            secs = P.KIT_GATE[56].get(key, 2.0)
            items = [excerpt(os.path.join(R, path), max(secs, 1.0), seg)] if path else []
            for f in (E.ours, lambda n, dd: E.theirs(GU, n, dd)):
                x, _ = f(key, d)
                x = np.asarray(x, float)
                a = int(np.argmax(np.abs(x) > np.abs(x).max() * 0.01))
                items.append(x[a:a + int((secs + 0.6) * sr)])
            for z in items:
                z = 0.25 * z / (np.sqrt(np.mean(z ** 2)) * 4 + 1e-12)
                chunks += [z, gap]
            chunks.append(gap)
    w = np.concatenate(chunks)
    w = 0.9 * w / np.abs(w).max()
    dry = os.path.join(out, "pairs.dry.wav")
    wavfile.write(dry, sr, (w * 32767).astype(np.int16))
    subprocess.check_call(["lame", "-b", "256", "--quiet", dry, os.path.join(out, name)])
    os.remove(dry)
    print("  -> " + os.path.join(out, name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
