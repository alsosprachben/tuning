"""NATURAL TUNINGS, for the ear (tonelib natural_tuner; blockrender natural=):
each piece in its instruments' own tunings, at the rig's A, and again with
every voice in the rig's tuner (natural=0) -- the same file, the same tuner
(hybrid440 unless given), only the instruments' own temperaments between them.

  harpsichord   a fugue on the harpsichord (GM 6): the hybrid mean
  organ         the same fugue on the church organ (GM 19): the hybrid mean
  fortepiano    a performance on the fortepiano (0.40): the pleyel, at the
                rig's A (its own 435 only as a part's choice)
  mixed         the fugue's upper two voices on the harpsichord, the lower
                two on strings (GM 48: the rig's tuner) -- the shared A
                holding the two together

Each file gets a GS reset, then its tones on their channels ahead of the
first note. GPU renders through blockrender, then roomtail's room.

    python3 examples/natural_tuning_ab.py FUGUE.mid PERFORMANCE.mid OUT [TUNER]
"""
import os
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('TUNING_GPU', '1')
GS_RESET = [0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41]


def on_tones(src, dst, tones):
    """src with a GS reset and each channel's (bank, program) -- tones[ch], else
    tones[None] -- first; its own program and bank changes dropped."""
    mf = mido.MidiFile(src)
    chans = sorted({m.channel for t in mf.tracks for m in t if hasattr(m, 'channel')}) or [0]
    head = [mido.Message('sysex', data=GS_RESET, time=0)]
    for c in chans:
        bank, prog = tones.get(c, tones.get(None))
        head += [mido.Message('control_change', channel=c, control=0, value=bank, time=0),
                 mido.Message('control_change', channel=c, control=32, value=0, time=0),
                 mido.Message('program_change', channel=c, program=prog, time=0)]
    out = mido.MidiFile(ticks_per_beat=mf.ticks_per_beat, type=mf.type)
    for i, t in enumerate(mf.tracks):
        nt = mido.MidiTrack()
        if i == 0:
            nt.extend(head)
        first = i == 0
        for m in t:
            if m.type == 'program_change' or (m.type == 'control_change' and m.control in (0, 32)):
                continue
            if first:                       # (the reset's settle: the first event 240 ticks on)
                m = m.copy(time=m.time + 240)
                first = False
            nt.append(m)
        out.tracks.append(nt)
    out.save(dst)


def render(mid, out_mp3, tuner, natural):
    wav = out_mp3[:-4] + ".wav"
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, wav, tuner, "natural=%d" % natural],
                   cwd=HERE, check=True, stdout=subprocess.DEVNULL)
    room = wav[:-4] + "_room.wav"
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), wav, room], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["sox", room, "-C", "256", out_mp3], check=True)
    for f in (wav, room):
        os.remove(f)
    print("  " + out_mp3, flush=True)


def main(argv):
    fugue, perf, out = argv[1], argv[2], os.path.abspath(argv[3])
    tuner = argv[4] if len(argv) > 4 else 'hybrid440'
    os.makedirs(out, exist_ok=True)
    pieces = [("harpsichord", fugue, {None: (0, 6)}),
              ("organ", fugue, {None: (0, 19)}),
              ("fortepiano", perf, {None: (40, 0)}),
              ("mixed", fugue, {0: (0, 6), 1: (0, 6), None: (0, 48)})]
    for name, src, tones in pieces:
        mid = os.path.join(out, "%s.mid" % name)
        on_tones(src, mid, tones)
        for nat, who in ((1, "natural"), (0, "rig")):
            render(mid, os.path.join(out, "%s_%s.mp3" % (name, who)), tuner, nat)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
