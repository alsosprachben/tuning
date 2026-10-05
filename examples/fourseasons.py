#!/usr/bin/env python3
"""Vivaldi, The Four Seasons (Op. 8 Nos. 1-4) -- from classicalmidi.co.uk's set
to four mp3s, one per season.

    python3 examples/fourseasons.py [OUTDIR]       # default ~/Downloads/fourseasons

THE FILES are classicalmidi.co.uk's Four Seasons set (music2/2631vivaldi.zip),
twelve movement files, gp_v01 .. gp_v12: Spring 1-3, Summer 4-6, Autumn 7-9,
Winter 10-12. Cleaned into cl_01 .. cl_12 as the September renders were: the
synth-string pad the sequencer laid under the band (GM 50) is dropped -- an
eighteenth-century string band has no pad, and it was a third of the notes --
and the acoustic bass (GM 32, a jazz pizzicato) becomes a contrabass (43). The September renders (v6, v7) were made from a script in a
scratch directory, which a reboot took with it; this is that script, kept.

THE SOLOIST IN FRONT. A GM violin is a section, and there is no program that
means "one of them", so the solo part -- channel 2, or 12 in Autumn's finale --
is rendered as its own stem and brought 10 dB forward in DIRECT sound only, the
room's tail taken from the unboosted sum (soloforward.py): closer is louder AND
drier, which is why a soloist stands at the front rather than playing harder.
Autumn's slow movement (cl_08, the sleeping drunkards) has no soloist and is
rendered plain.

THE ROOM is the chapel -- the Pieta, where the Op. 8 concertos were played --
at the master's -12 dB of headroom. All twelve at hybrid440: the September
renders had the slow movement at plain `hybrid`, A = 415, a semitone under the
eleven soloforward rendered at 440.

Each season is its three movements with two seconds between them, normalised
as a whole so their balance holds.
"""
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://www.classicalmidi.co.uk/music2/2631vivaldi.zip"
ROOM, MASTER_DB, TUNER, FORWARD_DB, GAP_S = "chapel", "-12", "hybrid440", "10", 2.0
SOLO = {n: 2 for n in range(1, 13)}
SOLO[9] = 12                    # Autumn's finale: the soloist is on channel 12
SOLO[8] = None                  # Autumn's Adagio molto: no soloist
SEASONS = (("spring", "La primavera", (1, 2, 3)), ("summer", "L'estate", (4, 5, 6)),
           ("autumn", "L'autunno", (7, 8, 9)), ("winter", "L'inverno", (10, 11, 12)))


def run(cmd, env=None):
    print("  $ " + " ".join(cmd))
    subprocess.check_call(cmd, env=dict(os.environ, **(env or {})))


def clean(src, dst):
    """The pad's channels out (their time carried on), the bass a contrabass."""
    import mido
    m = mido.MidiFile(src)
    prog = {}
    for tr in m.tracks:
        for msg in tr:
            if msg.type == 'program_change':
                prog.setdefault(msg.channel, msg.program)
    pad = {c for c, p in prog.items() if p == 50}
    out = mido.MidiFile(ticks_per_beat=m.ticks_per_beat, type=m.type)
    for tr in m.tracks:
        nt, carry = mido.MidiTrack(), 0
        for msg in tr:
            if hasattr(msg, 'channel') and msg.channel in pad:
                carry += msg.time
                continue
            msg = msg.copy(time=msg.time + carry)
            carry = 0
            if msg.type == 'program_change' and msg.program == 32:
                msg.program = 43
            nt.append(msg)
        out.tracks.append(nt)
    out.save(dst)


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/fourseasons")
    os.makedirs(out, exist_ok=True)
    P = lambda f: os.path.join(out, f)            # noqa: E731
    if not os.path.exists(P("cl_12.mid")):
        z = P("2631vivaldi.zip")
        if not os.path.exists(z):
            run(["curl", "-sfL", "--max-time", "120", "-A", "Mozilla/5.0", "-o", z, URL])
        with zipfile.ZipFile(z) as zf:
            zf.extractall(out)
        for n in range(1, 13):
            clean(P("gp_v%02d.mid" % n), P("cl_%02d.mid" % n))
    env = {"TUNING_ROOM": ROOM, "TUNING_MASTER_DB": MASTER_DB}
    for n in range(1, 13):
        mid, wav = P("cl_%02d.mid" % n), P("mv%02d.wav" % n)
        if os.path.exists(wav):
            continue
        if SOLO[n] is not None:
            run([sys.executable, os.path.join(HERE, "soloforward.py"), mid, str(SOLO[n]), wav,
                 FORWARD_DB, ROOM], env)
        else:
            dry = P("mv%02d.dry.wav" % n)
            run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, dry, TUNER], env)
            run([sys.executable, os.path.join(HERE, "roomtail.py"), dry, wav], env)
            for f in (dry, P("mv%02d.dry.room.json" % n), P("mv%02d.dry.send.wav" % n)):
                if os.path.exists(f):
                    os.remove(f)
    run(["sox", "-n", "-r", "44100", "-c", "2", "-b", "32", P("gap.wav"), "trim", "0", str(GAP_S)])
    for name, title, mv in SEASONS:
        parts = []
        for i, n in enumerate(mv):
            parts += ([P("gap.wav")] if i else []) + [P("mv%02d.wav" % n)]
        run(["sox"] + parts + [P(name + ".wav")])
        run(["sox", P(name + ".wav"), "-b", "24", P(name + ".norm.wav"), "gain", "-n", "-1"])
        run(["lame", "-b", "320", "-h", "--quiet", "--tt", "%s (%s)" % (name.capitalize(), title),
             "--ta", "Vivaldi", "--tl", "The Four Seasons", P(name + ".norm.wav"), P(name + ".mp3")])
        for f in (name + ".wav", name + ".norm.wav"):
            os.remove(P(f))
        print("  -> %s" % P(name + ".mp3"))
    for n in range(1, 13):
        os.remove(P("mv%02d.wav" % n))
    os.remove(P("gap.wav"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
