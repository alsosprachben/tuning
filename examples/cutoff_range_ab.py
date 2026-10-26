"""A/B of the cutoff's range: one file rendered with a full CC74 / GS TVF
cutoff NRPN (they are one parameter on a Sound Canvas: SC-8850 owner's
manual, "TVF Cutoff (=NRPN# 32/CC#74)") moving a synth panel's cutoff
+/-N octaves, for N in OCTAVES. GM 2 leaves the amount to the
manufacturer (v1.2a, 3.3.14) and Roland does not publish one, so the ear
decides: a file whose sweeps were drawn on the hardware (Uramach's
Beethoven 9 finale, SC-88 Pro) sounds meant at the right range.

Writes OUT/NAME_cutN.wav, _room.wav and .mp3 for each N, GPU, with the
file's mod-wheel vibrato on (TUNING_MOD_VIBRATO=1).

    python3 examples/cutoff_range_ab.py FILE.mid OUT [N ...]   (default 2 4 8)
"""
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE]
os.environ.setdefault('TUNING_GPU', '1')
os.environ.setdefault('TUNING_MOD_VIBRATO', '1')

import moog as M          # noqa: E402

OCTAVES = (2.0, 4.0, 8.0)


def knob_span(octaves):
    """The knob distance (moog.GM_SOUND's span) that moves the cutoff by
    `octaves` from the middle of the knob: its law is exponential, so one
    measurement of octaves per knob unit holds anywhere."""
    per = math.log2(M.knob_cutoff(0.75) / M.knob_cutoff(0.25)) / 0.5
    return octaves / per


def main(argv):
    src, out = argv[1], argv[2]
    octs = [float(a) for a in argv[3:]] or OCTAVES
    os.makedirs(out, exist_ok=True)
    name = os.path.splitext(os.path.basename(src))[0]
    for n in octs:
        span = knob_span(n)
        wav = os.path.join(out, "%s_cut%g.wav" % (name, n))
        code = ("import sys, runpy, moog; moog.GM_SOUND['brightness'] = ('cutoff', %r); "
                "sys.argv = ['blockrender.py', %r, %r]; "
                "runpy.run_path(%r, run_name='__main__')" % (span, src, wav, os.path.join(HERE, "blockrender.py")))
        subprocess.run([sys.executable, "-c", code], cwd=HERE, check=True, stdout=subprocess.DEVNULL)
        room = wav[:-4] + "_room.wav"
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), wav, room], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["sox", room, "-C", "256", room[:-4] + ".mp3"], check=True)
        print("  +/-%g octaves (knob span %.3f): %s" % (n, span, room[:-4] + ".mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
