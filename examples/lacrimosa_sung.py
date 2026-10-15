#!/usr/bin/env python3
"""Mozart, Requiem K.626, Lacrimosa: the orchestra, and the choir SINGING the
Latin, its parts declared.

    python3 examples/lacrimosa_sung.py [OUTDIR] [--parts=treble,countertenor,tenor,bass]

Built the way the September renders were (they ran inline; this keeps it):

  1  learnchoralmusic.co.uk's Requiem No. 7 (07-lacri.mid): the orchestra and
     a textless choir on channels 4-7. Choir to GM 52, strings to 48; the
     tempo to 190/130 of the file's; the accompaniment 6.8 dB down by CC7 and
     the top two voices up 3 and 1 dB, so the choir leads as a choir does;
     and the strings 6 dB further down again (CHOIR_DB), by ear.
  2  the choir REPLACED by the MusicXML engraving's voices, which carry the
     Latin (~/msconv/lacr_voices.mid, from MozartLacrimosaSATB.mxl): both
     are exactly 30 bars, so the ticks scale bar for bar onto the file's
     tempo map.
  3  the voices' velocities to the original choir's mean and spread (76, sd
     15.8): the engraving's shape, the original's balance against this
     orchestra -- the engraving's pp sat 23 dB down.
  4  each part named as --parts says (TUNING_VOICE_PARTS, by channel), and the
     whole file rendered once through blockrender, which sings each syllable's
     vowel on that part's body (vowels.VOWELS through _sung_formants: the
     singer's cluster, a woman's weaker one, a countertenor's 0.10), the
     consonants, the breath and the effort with it. Church, -3 dB wet.

Default parts: soprano, countertenor, tenor, bass -- the alto line on a man.
"""
import os
import statistics
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "http://www.learnchoralmusic.co.uk/Mozart/Requiem/07-lacri.mid"
VOICES = os.path.expanduser("~/msconv/lacr_voices.mid")
CHOIR, STRINGS = (4, 5, 6, 7), (8, 11, 12, 13)
TEMPO, ACCOMP_DB, LIFT_DB = 190 / 130.0, -6.8, {4: 3.0, 5: 1.0}
# THE CHOIR 6 dB FURTHER FORWARD (Ben, on the first render: "the orchestra is
# too loud relative to the choir"). Taken off the strings' CC7, not added to
# the voices' velocity: a velocity is also EFFORT (effort_tilt), and the
# choir should be louder, not pushed.
CHOIR_DB = 6.0
TGT_MEAN, TGT_SD = 76.0, 15.8
ROOM, WET, TUNER = "church", "-3", "even"


def cc7(v, db):
    return max(1, min(127, int(round(v * 10 ** (db / 20.0)))))


def orchestra(src):
    m = mido.MidiFile(src)
    seen = set()
    for tr in m.tracks:
        for x in tr:
            if x.type == "program_change":
                if x.channel in CHOIR:
                    x.program = 52
                elif x.channel in STRINGS:
                    x.program = 48
            elif x.type == "set_tempo":
                x.tempo = int(round(x.tempo * TEMPO))
            elif x.type == "control_change" and x.control == 7:
                if x.channel in STRINGS:
                    x.value = cc7(x.value, ACCOMP_DB - CHOIR_DB); seen.add(x.channel)
                elif x.channel in LIFT_DB:
                    x.value = cc7(x.value, LIFT_DB[x.channel])
    for ch in sorted(set(STRINGS) - seen):
        m.tracks[0].insert(0, mido.Message("control_change", channel=ch, control=7,
                                           value=cc7(127, ACCOMP_DB - CHOIR_DB), time=0))
    return m


def graft(orch, sing, parts):
    """The orchestra's own tracks without its choir, then the sung voices on
    channels 4-7, scaled bar for bar onto the orchestra's ticks."""
    scale = orch.ticks_per_beat / sing.ticks_per_beat
    out = mido.MidiFile(type=1, ticks_per_beat=orch.ticks_per_beat)
    for tr in orch.tracks:
        ev, t, prev = [], 0, 0
        for x in tr:
            t += x.time
            if hasattr(x, "channel") and x.channel in CHOIR:
                continue
            ev.append(x.copy(time=t - prev)); prev = t
        if ev:
            out.tracks.append(mido.MidiTrack(ev))
    k = 0
    for tr in sing.tracks:
        if not any(x.type == "note_on" and x.velocity > 0 for x in tr):
            continue
        ch = CHOIR[k]
        ev = [mido.MetaMessage("track_name", name=parts[k].capitalize(), time=0),
              mido.Message("program_change", channel=ch, program=52, time=0)]
        t, prev = 0.0, 0
        for x in tr:
            t += x.time
            if x.is_meta and x.type in ("set_tempo", "time_signature", "key_signature", "track_name"):
                continue
            if x.type == "program_change":
                continue
            tk = int(round(t * scale))
            y = x.copy(time=tk - prev); prev = tk
            if hasattr(y, "channel"):
                y.channel = ch
            ev.append(y)
        out.tracks.append(mido.MidiTrack(ev))
        k += 1
    v = [x.velocity for tr in out.tracks for x in tr
         if x.type == "note_on" and x.velocity > 0 and x.channel in CHOIR]
    mu, sd = statistics.mean(v), statistics.pstdev(v)
    for tr in out.tracks:
        for x in tr:
            if x.type == "note_on" and x.velocity > 0 and x.channel in CHOIR:
                x.velocity = max(1, min(127, int(round(TGT_MEAN + (x.velocity - mu) * TGT_SD / sd))))
    return out


def run(cmd, env):
    print("  $ " + " ".join(cmd), flush=True)
    subprocess.check_call(cmd, env=env)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/lacrimosa_sung")
    parts = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--parts=")),
                 ["soprano", "countertenor", "tenor", "bass"])
    tag = next((a.split("=", 1)[1] for a in argv if a.startswith("--tag=")), "_".join(parts))
    dl = os.path.join(out, "download")              # the download in its own folder
    os.makedirs(dl, exist_ok=True)
    src = os.path.join(dl, "07-lacri.mid")
    if not os.path.exists(src):
        subprocess.check_call(["curl", "-sfL", "--max-time", "60", "-o", src, URL])
    mid = os.path.join(out, "lacrimosa_%s.mid" % tag)
    graft(orchestra(src), mido.MidiFile(VOICES), parts).save(mid)
    env = dict(os.environ, TUNING_ROOM=ROOM, TUNING_WET=WET, TUNING_LYRIC_LANG="latin",
               TUNING_VOICE_PARTS=",".join("%d=%s" % (c, p) for c, p in zip(CHOIR, parts)))
    P = lambda f: os.path.join(out, "lacrimosa_%s%s" % (tag, f))       # noqa: E731
    run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, P(".dry.wav"), TUNER], env)
    run([sys.executable, os.path.join(HERE, "roomtail.py"), P(".dry.wav"), P(".wav")], env)
    run(["sox", P(".wav"), P(".norm.wav"), "gain", "-n", "-1"], env)
    run(["lame", "-b", "320", "-h", "--quiet", "--tt", "Lacrimosa (%s)" % ", ".join(parts),
         "--ta", "Mozart", "--tl", "Requiem K.626", P(".norm.wav"), P(".mp3")], env)
    for f in (".dry.wav", ".dry.send.wav", ".norm.wav", ".wav"):
        if os.path.exists(P(f)):
            os.remove(P(f))
    print("  -> " + P(".mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
