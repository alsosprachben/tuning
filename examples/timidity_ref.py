#!/usr/bin/env python3
"""Render a MIDI file through timidity with each reference GM SoundFont -- the
other implementations to compare ours against.

    python3 examples/timidity_ref.py FILE.mid [OUTDIR] [SF2 ...]

The fonts default to examples/kit_levels.py's: FluidR3 (Debian), GeneralUser
GS and MuseScore General (~/Documents/refs/soundfonts, sources.md). timidity
reads Debian's /etc/timidity/timidity.cfg before any -c file, and that maps
FluidR3 note by note -- so every program in bank 0 and every drum note in
drum sets 0 and 1 is mapped to the font explicitly, or all three renders come
out FluidR3. Each is rendered with timidity's own reverb and chorus (as a
player of that font hears it), normalized to -1 dB and written as a 320k mp3
named FILE_timidity_FONT.mp3.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

from kit_levels import DEFAULT_SF  # noqa: E402


def cfg_for(sf):
    lines = ["bank 0"] + ['%d %%font "%s" 0 %d' % (p, sf, p) for p in range(128)]
    for d in (0, 1):
        lines.append("drumset %d" % d)
        lines += ['%d %%font "%s" 128 0 %d' % (k, sf, k) for k in range(27, 88)]
    return "\n".join(lines) + "\n"


def main(argv):
    pos = [a for a in argv[1:]]
    mid = pos[0]
    out = pos[1] if len(pos) > 1 else os.path.expanduser("~/Downloads/sota")
    fonts = pos[2:] or [os.path.expanduser(s) for s in DEFAULT_SF]
    os.makedirs(out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(mid))[0]
    with tempfile.TemporaryDirectory() as d:
        for sf in fonts:
            name = os.path.splitext(os.path.basename(sf))[0]
            cfg, wav, norm = (os.path.join(d, name + x) for x in (".cfg", ".wav", "_n.wav"))
            with open(cfg, "w") as f:
                f.write(cfg_for(sf))
            subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", "44100", "--quiet=2", mid],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["sox", wav, "-b", "24", norm, "norm", "-1"], check=True)
            mp3 = os.path.join(out, "%s_timidity_%s.mp3" % (stem, name))
            subprocess.run(["lame", "-b", "320", "--quiet", norm, mp3], check=True)
            print("  -> %s" % mp3)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
