#!/usr/bin/env python3
"""The drums' VOLUME against velocity, put back on the kit's square law.

    python3 -I examples/drum_volume.py            # measure: each voice's law, untrimmed and as is
    python3 -I examples/drum_volume.py --write    # set each voice's strike_volume_trim_db

Velocity is both EFFORT and VOLUME (Ben: "our drums use velocity for effort,
but we probably need a volume aspect, too"). A hat's effort is its wash: a
plate struck harder is noisier (HiHatProperties.strike_noise_slope, measured on
Iowa's cymbals), and the wash is most of a hat's sound, so the effort was
setting its volume too -- at velocity 60 a closed hat sat 28.5 dB under its
127, where the kick and snare sit 13 and GeneralUser GS's hat 12. A groove's
offbeat hats all but vanished. Every other drum was measured too, and eight
more sat 3-7 dB under the law at velocity 60 by the same kind of effort law
(the crashes' and splash's wash and bloom, the low bongo's and conga's
stroke): the two crashes, the splash, the low bongo and conga, and the three
cymbals built on the crashes (the reverse cymbal, the concert cymbals), each
measured with its own trim cleared, after the crash it inherits from.

So the effort keeps its timbre and the volume is measured and trimmed: each
hat is rendered at seven velocities with no trim, its level read (K-weighted,
its loudest 150 ms, as drumset_check reads one) against its own at 127, and
the trim is what puts it on the square law, 40 log10(v / 127) dB -- where the
kick and snare already sit -- ANCHORED AT VELOCITY 100, the velocity the kit
was levelled at: the trim there is 0, so the hat keeps its balanced level and
the law turns about it (its 127 ~5 dB softer than before, its soft strokes
far louder). Read dry.
"""
import os
import re
import sys
import tempfile
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")
os.environ["TUNING_REFLECT"] = "0"

V = (127, 100, 85, 70, 60, 45, 30, 15)
# (set, note, class): a base before the classes built on it
VOICES = ((0, 42, "ClosedHiHatProperties"), (0, 44, "PedalHiHatProperties"),
          (0, 46, "OpenHiHatProperties"), (0, 49, "CrashCymbal1Properties"),
          (0, 57, "CrashCymbal2Properties"), (0, 55, "SplashCymbalProperties"),
          (0, 61, "BongoLowProperties"), (0, 64, "CongaLowProperties"),
          (24, 52, "ReverseCymbalProperties"), (48, 59, "ConcertCymbal1Properties"),
          (48, 57, "ConcertCymbal2Properties"))


def level(kit, note, vel, d):
    import mido
    import blockrender as B
    from elkit_balance import k150
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.Message("program_change", channel=9, program=kit, time=0))
    t.append(mido.Message("note_on", channel=9, note=note, velocity=vel, time=240))
    t.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=60))
    t.append(mido.MetaMessage("end_of_track", time=3840))     # a crash rings: 4 s
    p = os.path.join(d, "h.mid")
    m.save(p)
    L, R = B.render(p)[:2]
    return k150(0.5 * (np.asarray(L) + np.asarray(R)), B.SR)


def law(kit, note, d):
    lv = [level(kit, note, v, d) for v in V]
    return np.array(lv) - lv[0]


def main(argv):
    import tonelib as T
    import percussion_map as P
    want = 40.0 * np.log10(np.array(V) / 127.0)
    trims = {}
    with tempfile.TemporaryDirectory() as d:
        for kit, note, name in VOICES:
            cls = getattr(T, name)
            own = vars(cls).get("strike_volume_trim_db")
            cls.strike_volume_trim_db = ()
            P._RING_CLASSES.clear()
            raw = law(kit, note, d)
            # ANCHORED AT VELOCITY 100, where the kit was levelled (kit_levels.py,
            # drumset_check.py): the hat keeps that level, the law turns about it
            t100 = float(np.interp(100, V[::-1], (want - raw)[::-1]))
            trims[name] = tuple((v, round(float(w - r - t100), 1)) for v, w, r in zip(V, want, raw))
            print("%2d/%d %-24s untrimmed %s" % (kit, note, name, " ".join("v%d %+.1f" % (v, x) for v, x in zip(V, raw))))
            cls.strike_volume_trim_db = trims[name] if "--write" in argv else (own or ())
            P._RING_CLASSES.clear()
            print("%2d/%d %-24s now       %s" % (kit, note, "", " ".join("v%d %+.1f" % (v, x) for v, x in zip(V, law(kit, note, d)))))
    print("   the square law:        %s" % " ".join("v%d %+.1f" % (v, x) for v, x in zip(V, want)))
    if "--write" in argv:
        path = os.path.join(HERE, "tonelib.py")
        s = open(path).read()
        for name, tr in trims.items():
            i = s.index("class %s(" % name)
            end = s.index("\nclass ", i + 1)
            body = re.sub(r"\n    # VOLUME ON THE SQUARE LAW.*?strike_volume_trim_db = [^\n]*\n", "\n",
                          s[i:end], flags=re.S)
            body = body.rstrip("\n") + (
                "\n    # VOLUME ON THE SQUARE LAW (examples/drum_volume.py): dB at each velocity\n"
                "    strike_volume_trim_db = %r\n\n\n" % (tr,))
            s = s[:i] + body + s[end:]
        open(path, "w").write(s)
        print("   wrote %s" % ", ".join(trims))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
