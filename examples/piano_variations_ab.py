"""A/B of the dark and bright piano variations voiced as VOICE-card knob
positions (patch_map: Piano 1d, Mild Piano, European Pf on the grand; Pop,
Rock, Dance Piano on the upright) against the same variations as a git
revision had them (by default HEAD: the old hammer-corner numbers), and the
plain voice they vary.

One phrase across the keyboard -- a soft bass and chord, a mf melody up to
the treble, a forte chord stack -- is written per tone (CC32 map, CC0
bank, program), rendered on the GPU through blockrender, then roomtail's
room. The "before" renders run with the revision's patch_map.py and
variation_desc.py ahead of this tree's on the path.

Writes OUT/NN_name_{before,after}.mp3 (and the plain voices once), and
OUT/ab.mp3: per variation, plain / before / after, a second apart.

    python3 examples/piano_variations_ab.py OUT [REV]
"""
import os
import subprocess
import sys
import tempfile

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('TUNING_GPU', '1')

# (name, map (CC32), bank (CC0), program)
TONES = [
    ("piano1", 0, 0, 0), ("piano1d", 0, 16, 0), ("mild", 0, 2, 0), ("european", 3, 16, 0),
    ("upright", 0, 0, 1), ("pop", 0, 1, 1), ("rock", 0, 2, 1), ("dance", 0, 16, 1),
]
PLAIN = {"piano1d": "piano1", "mild": "piano1", "european": "piano1",
         "pop": "upright", "rock": "upright", "dance": "upright"}


def phrase(path, cc32, bank, prog):
    """The phrase on one tone, after a GS reset."""
    mf = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    mf.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=600000))
    t.append(mido.Message('sysex', data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41]))
    t.append(mido.Message('control_change', control=0, value=bank, time=240))
    t.append(mido.Message('control_change', control=32, value=cc32))
    t.append(mido.Message('program_change', program=prog))
    ev = []                 # (beat, key, vel, beats)

    def chord(b, keys, vel, dur):
        ev.extend((b, k, vel, dur) for k in keys)
    chord(1, (36, 48), 50, 3.5)                       # soft bass and chord
    chord(1.5, (55, 60, 64), 45, 3)
    for i, k in enumerate((67, 72, 76, 79, 84, 88, 91, 96)):
        ev.append((5 + 0.5 * i, k, 80, 0.6))          # mf melody to the treble
    chord(9.5, (31, 43), 105, 3)                      # forte stack
    chord(9.5, (55, 59, 62, 67, 74, 79, 86), 112, 3)
    chord(13.5, (60, 64, 67, 72), 64, 3)              # mp middle chord
    msgs = []
    for b, k, v, d in ev:
        msgs.append((int(b * 480), 1, mido.Message('note_on', note=k, velocity=v)))
        msgs.append((int((b + d) * 480), 0, mido.Message('note_off', note=k, velocity=0)))
    msgs.sort(key=lambda m: (m[0], m[1]))
    now = 0
    for tk, _, m in msgs:
        t.append(m.copy(time=tk - now))
        now = tk
    t.append(mido.MetaMessage('end_of_track', time=960))
    mf.save(path)


def render(mid, wav, old_dir=None):
    env = dict(os.environ)
    code = ("import sys, runpy; sys.argv = ['blockrender.py', %r, %r]; "
            "runpy.run_path(%r, run_name='__main__')" % (mid, wav, os.path.join(HERE, "blockrender.py")))
    if old_dir:
        code = "import sys; sys.path.insert(0, %r); " % old_dir + code
    subprocess.run([sys.executable, "-c", code], cwd=HERE, check=True, stdout=subprocess.DEVNULL, env=env)
    room = wav[:-4] + "_room.wav"
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), wav, room], check=True,
                   stdout=subprocess.DEVNULL)
    return room


def main(argv):
    out = os.path.abspath(argv[1])
    rev = argv[2] if len(argv) > 2 else "HEAD"
    os.makedirs(out, exist_ok=True)
    old = tempfile.mkdtemp(prefix="pvab_old_", dir=out)
    for f in ("patch_map.py", "variation_desc.py"):
        src = subprocess.run(["git", "show", "%s:%s" % (rev, f)], cwd=HERE, check=True,
                             capture_output=True).stdout
        open(os.path.join(old, f), "wb").write(src)
    rooms = {}
    for n, (name, cc32, bank, prog) in enumerate(TONES):
        mid = os.path.join(out, "%02d_%s.mid" % (n, name))
        phrase(mid, cc32, bank, prog)
        sides = ("after",) if name not in PLAIN else ("before", "after")
        for side in sides:
            wav = os.path.join(out, "%02d_%s_%s.wav" % (n, name, side) if name in PLAIN
                               else "%02d_%s.wav" % (n, name))
            room = render(mid, wav, old if side == "before" else None)
            mp3 = room.replace("_room.wav", ".mp3")
            subprocess.run(["sox", room, "-C", "256", mp3], check=True)
            rooms[(name, side)] = room
            print("  %s %s: %s" % (name, side, mp3), flush=True)
    # (the listening order: per variation, its plain voice, before, after)
    gap = os.path.join(out, "gap.wav")
    subprocess.run(["sox", "-n", "-r", "44100", "-c", "2", gap, "trim", "0", "1.0"], check=True)
    seq = []
    for name, _, _, _ in TONES:
        if name in PLAIN:
            seq += [rooms[(PLAIN[name], "after")], gap, rooms[(name, "before")], gap, rooms[(name, "after")], gap, gap]
    subprocess.run(["sox"] + seq + ["-C", "256", os.path.join(out, "ab.mp3")], check=True)
    print("  all: %s" % os.path.join(out, "ab.mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
