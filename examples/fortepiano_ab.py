"""THE FORTEPIANO AGAINST THE GRAND, for the ear (tonelib.PleyelProperties at
0.40, against Piano 1): a performance file played on each -- the grand as
it is, the fortepiano in the same tuning, and the fortepiano as a Paris
tuner of the 1840s would have left it (the pleyel tuner: the French aural
procedure on its own strings, A3 = 217.5) -- and a touch ladder, C2 C4 C6
at velocities 30 60 90 120, the grand's and the fortepiano's in turn, to
hear the felt give way to the leather.

Each file gets a GS reset, then the tone on every channel (CC0, PC) ahead of
its first note. GPU renders through blockrender, then roomtail's room.

    python3 examples/fortepiano_ab.py PERFORMANCE.mid OUT [TUNER]   (TUNER: the grand's, default hybrid440)
"""
import os
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('TUNING_GPU', '1')
GS_RESET = [0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41]


def on_tone(src, dst, bank):
    """src with a GS reset and (bank, program 0) on every channel it uses, first."""
    mf = mido.MidiFile(src)
    chans = sorted({m.channel for t in mf.tracks for m in t if hasattr(m, 'channel')}) or [0]
    head = [mido.Message('sysex', data=GS_RESET, time=0)]
    for c in chans:
        head += [mido.Message('control_change', channel=c, control=0, value=bank, time=0),
                 mido.Message('control_change', channel=c, control=32, value=0, time=0),
                 mido.Message('program_change', channel=c, program=0, time=0)]
    # (the reset's settle: the first track's first event pushed 240 ticks on)
    out = mido.MidiFile(ticks_per_beat=mf.ticks_per_beat, type=mf.type)
    for i, t in enumerate(mf.tracks):
        nt = mido.MidiTrack()
        if i == 0:
            nt.extend(head)
            first = True
            for m in t:
                if m.type == 'program_change' or (m.type == 'control_change' and m.control in (0, 32)):
                    continue
                if first:
                    m = m.copy(time=m.time + 240)
                    first = False
                nt.append(m)
        else:
            nt.extend(m for m in t if not (m.type == 'program_change'
                                           or (m.type == 'control_change' and m.control in (0, 32))))
        out.tracks.append(nt)
    out.save(dst)


def ladder(dst, bank):
    mf = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    mf.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=500000))
    t.append(mido.Message('sysex', data=GS_RESET))
    t.append(mido.Message('control_change', control=0, value=bank, time=240))
    t.append(mido.Message('program_change', program=0))
    gap = 0
    for key in (36, 60, 84):
        for vel in (30, 60, 90, 120):
            t.append(mido.Message('note_on', note=key, velocity=vel, time=gap + 240))
            t.append(mido.Message('note_off', note=key, velocity=0, time=960))
            gap = 0
        gap = 480
    t.append(mido.MetaMessage('end_of_track', time=1920))
    mf.save(dst)


def render(mid, out_mp3, tuner):
    wav = out_mp3[:-4] + ".wav"
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, wav, tuner], cwd=HERE, check=True,
                   stdout=subprocess.DEVNULL)
    room = wav[:-4] + "_room.wav"
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), wav, room], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["sox", room, "-C", "256", out_mp3], check=True)
    for f in (wav, room):
        os.remove(f)
    print("  " + out_mp3, flush=True)


def main(argv):
    src, out = argv[1], os.path.abspath(argv[2])
    tuner = argv[3] if len(argv) > 3 else 'hybrid440'
    os.makedirs(out, exist_ok=True)
    name = os.path.splitext(os.path.basename(src))[0][:40]
    for bank, who in ((0, 'grand'), (40, 'fortepiano')):
        mid = os.path.join(out, "ladder_%s.mid" % who)
        ladder(mid, bank)
        render(mid, os.path.join(out, "ladder_%s.mp3" % who), tuner)
    for bank, who, tn in ((0, 'grand', tuner), (40, 'fortepiano', tuner), (40, 'fortepiano_pleyel_tuning', 'pleyel')):
        mid = os.path.join(out, "%s_%s.mid" % (name, who))
        on_tone(src, mid, bank)
        render(mid, os.path.join(out, "%s_%s.mp3" % (name, who)), tn)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
