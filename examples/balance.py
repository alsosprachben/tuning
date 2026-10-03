"""Balance a multi-part MIDI against two standard GM sets, then mix it in a hall.

Every part (one track of an mt32mux build) is rendered on its own, here and
through MuseScore's MS Basic and TiMidity's FluidR3, and measured K-weighted
while it plays (lib.loudness). Each reference is aligned to ours by its median
difference over every part, so only a part out of line with the rest moves; it
moves by the references' mean when they agree within AGREE_DB, by the smaller
of the two when they agree only on the direction, and not at all when they
point opposite ways ("no verdict"). By-ear moves go on top. The stems are summed
at those gains and the hall given once to the sum, from their merged room
sidecars. Used by mars.py and jupiter.py.
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import lib                                         # noqa: E402

AGREE_DB = 3.0
REFS = ("musescore", "timidity")
VOICE_CODE = ("tonelib.py", "blockrender.py", "synthkernel.c", "moog.py")


def reference(engine, mid, wav):
    """The same part through a standard GM synth: MuseScore's MS Basic, or
    TiMidity's FluidR3 -- dry, no reverb or chorus. Cached beside the stem."""
    key = __import__("hashlib").sha1(open(mid, "rb").read()).hexdigest()
    mark = wav + ".src"
    if not (os.path.exists(wav) and os.path.exists(mark) and open(mark).read() == key):
        if engine == "musescore":
            subprocess.run(["snap", "run", "musescore", "-o", wav, mid], capture_output=True,
                           env=dict(os.environ, QT_QPA_PLATFORM="offscreen"), timeout=600)
        else:
            subprocess.run(["timidity", "-EFreverb=0", "-EFchorus=0", "-Ow", "-o", wav, mid],
                           capture_output=True)
        if os.path.exists(wav):
            open(mark, "w").write(key)
    return lib.loudness(wav) if os.path.exists(wav) and os.path.getsize(wav) > 1000 else None


def balance(mux, out, env, tuner, ear=None, pin=()):
    """Every part rendered on its own, here and by both references; each part
    moved by how far its loudness against the others differs from theirs."""
    m = mido.MidiFile(mux)
    parts = [(i, next((x.name for x in tr if x.type == "track_name"), "trk%d" % i))
             for i, tr in enumerate(m.tracks) if any(x.type == "note_on" for x in tr)]
    rows = []
    for i, name in parts:
        tag = "%02d-%s" % (i, "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-"))
        stem = lib.take_tracks(mux, os.path.join(out, "stem.%s.mid" % tag), [i])
        wav = os.path.join(out, "stem.%s.wav" % tag)
        # RENDER ONLY WHAT CHANGED, by content: the stem MIDIs are rewritten on
        # every run, so their times say nothing (a re-mix re-rendered every
        # stem); the key is the stem, the settings and the voice code
        import hashlib
        key = hashlib.sha1(open(stem, "rb").read() + repr((tuner, sorted(env.items()))).encode()
                           + b"".join(open(os.path.join(HERE, f), "rb").read() for f in VOICE_CODE)).hexdigest()
        mark = wav + ".src"
        if not (os.path.exists(wav) and os.path.exists(mark) and open(mark).read() == key):
            lib.render_plain(stem, wav, tuner=tuner, extra_env=env)
            open(mark, "w").write(key)
        ours = lib.loudness(wav)
        refs = {e: reference(e, stem, os.path.join(out, "ref.%s.%s.wav" % (tag, e))) for e in REFS}
        rows.append([name, wav, ours, refs])
    # align each engine to ours by the MEDIAN difference over every part, so
    # only a part out of line with the rest moves, not the whole orchestra
    off = {e: float(np.median([r[3][e] - r[2] for r in rows if r[3][e] is not None])) for e in REFS}
    print("\n  part                      ours    %s   %s    move" % tuple(e[:9] for e in REFS))
    for r in rows:
        c = {e: (r[3][e] - r[2] - off[e]) if r[3][e] is not None else None for e in REFS}
        ok = [v for v in c.values() if v is not None]
        if r[0] in pin:                 # a part balanced by ear: the references do not move it
            r.append(0.0); note = "  pinned"
        elif len(ok) == 2 and abs(ok[0] - ok[1]) <= AGREE_DB:
            r.append(sum(ok) / 2.0); note = ""
        elif len(ok) == 2 and ok[0] * ok[1] > 0:
            # both the SAME WAY, by different amounts: the smaller of the two.
            # Waiting for agreement left Jupiter's timpani and glockenspiel
            # 7-16 dB hot, both references saying so
            r.append(min(ok, key=abs)); note = "  the references differ in amount: the smaller"
        else:
            r.append(0.0); note = "  no verdict: the references disagree"
        if r[0] in (ear or {}):
            r[4] += ear[r[0]]; note += "  %+.0f by ear" % ear[r[0]]
        print("  %-24s %6.1f   %+6.1f   %+6.1f    %+5.1f dB%s" % (
            r[0][:24], r[2], c["musescore"] if c["musescore"] is not None else float("nan"),
            c["timidity"] if c["timidity"] is not None else float("nan"), r[4], note))
    return rows




def mix(rows, out, name, env, title, artist, album):
    """The stems at their gains, the hall once on the sum, an mp3."""
    P = lambda f: os.path.join(out, f)            # noqa: E731
    wavs = [r[1] for r in rows]
    lib.sum_wavs(wavs, P(name + ".dry.wav"), gains=[10.0 ** (r[4] / 20.0) for r in rows])
    lib.merge_room([w.replace(".wav", ".room.json") for w in wavs], P(name + ".dry.room.json"))
    lib.roomtail(P(name + ".dry.wav"), P(name + ".wav"), env)
    subprocess.check_call(["sox", P(name + ".wav"), P(name + ".norm.wav"), "gain", "-n", "-1"])
    subprocess.check_call(["lame", "-b", "320", "-h", "--quiet", "--tt", title, "--ta", artist,
                           "--tl", album, P(name + ".norm.wav"), P(name + ".mp3")])
    for f in (name + ".dry.wav", name + ".norm.wav", name + ".dry.room.json"):
        if os.path.exists(P(f)):
            os.remove(P(f))
    import json
    json.dump([{"part": r[0], "ours": r[2], "refs": r[3], "move_db": r[4]} for r in rows],
              open(P(name + ".balance.json"), "w"), indent=1)
    return P(name + ".mp3")
