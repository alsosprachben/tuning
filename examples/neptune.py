#!/usr/bin/env python3
"""Holst, The Planets: Neptune -- from CRM114's MIDI to a finished mp3.

    python3 examples/neptune.py [OUTDIR]        # default ~/Downloads/neptune

Every step that made the September renders, which lived only in a scratch
directory and were lost with it; the rule about build scripts is why this
file exists.

THE FILE (classicalmidi.co.uk, "HolstNeptuneOrchestral.mid", sequenced by
CRM114) is written for an MT-32's way of thinking: thirty-one tracks on
fifteen channels, most channels carrying three tracks with three programs at
tick 0, of which a GM synth hears only the last (mt32check lists them). The
TRACK is the part, so mt32mux reads it that way: each track keeps its own
program and its own volume, stamped before every note, and the parts are
coloured onto channels so that no two sharing one ever sound the same pitch.
Five tracks declare no program or one their notes contradict; those come from
each track's profile (OVERRIDE). This is the version Ben approved as
neptune_tool -- the hand-built one that followed it took each channel's last
volume for all three of its tracks and brought the harps and celesta in about
8 dB under it.

THE ENDING. Holst asks for the offstage women's chorus to repeat its bar
"until the sound is lost in the distance". The file stops at 455 s; the
chorus's last bar (Cm6 against E major six, two parts) is repeated twelve
times, broadening 4.92 -> 5.80 s, with one continuous diminuendo 30 -> 6
across the file's own bars and the repeats. Wordless, as Holst writes it: the
vowel is /V/ (vowels.py), Chorus I the sopranos and Chorus II the altos.

THE RECESSION is by DISTANCE and by volume, as Ben asked ("did you do both?"):
from 445 to 524 s the chorus's direct sound falls 40 dB and darkens
(recede.py), while its share of the hall falls 28 dB. Each half -- band and
chorus -- gets its room tail from its own render's .room.json, at TUNING_WET
+2 dB ("wetter is probably better for Neptune ... do it at wet 2"). The last
render lost both of those; this restores them.
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import mt32mux as M                                    # noqa: E402
from roomtail import read_wav, write_wav               # noqa: E402

URL = "https://www.classicalmidi.co.uk/music2/HolstNeptuneOrchestral.mid"
# hybridmean -- the hybrid's two chains of pure fifths bridged by the mean
# third, so no wolf -- at a modern orchestra's A = 440 (plain "hybrid", which
# the September renders used, is at the baroque 415: a semitone flat for Holst)
ROOM, WET, TUNER = "hall", "2", "hybridmean:440"
RECEDE = (445.0, 524.0, -40.0, -28.0)       # start s, end s, direct dB, hall share dB

# What the tool cannot know from an unnamed file: trk18 and trk20 declare no
# program at all, and three more declare something their notes contradict.
OVERRIDE = {'trk18': 46, 'trk20': 46, 'trk25': 8, 'trk28': 46, 'trk29': 43}
LABEL = {'trk22': 'Organ pedal', 'trk23': 'Chorus I', 'trk24': 'Chorus II',
         'trk9': 'Contrabass', 'trk8': 'Bassoon', 'trk15': 'Cello', 'trk29': 'Contrabass II'}
# Holst's bar, as two chords per part (sopranos, altos)
ENDING = {'trk23': ([60, 65, 75, 79], [59, 64, 76, 80]),
          'trk24': ([63, 69, 72], [61, 68, 73])}
VOICES = {'Chorus I': 'soprano', 'Chorus II': 'alto'}


def run(cmd, env=None):
    print("  $ " + " ".join(cmd))
    subprocess.check_call(cmd, env=dict(os.environ, **(env or {})))


def build_midi(src, dst):
    mid = mido.MidiFile(src)
    tpb = mid.ticks_per_beat
    parts = M.seed_parts(M.read_parts(mid), M.channel_cc(mid))
    for p in parts:
        low = p['name'].lower()
        p['percussive'] = False
        if low in OVERRIDE:
            p['program'], p['why'] = OVERRIDE[low], 'profile'
        else:
            p['program'], p['why'] = M.program_for(p['name'], p['progs'])

    tempos = sorted((t, msg.tempo) for tr in mid.tracks
                    for t, msg in _abs(tr) if msg.type == 'set_tempo')
    if not tempos or tempos[0][0] > 0:
        tempos.insert(0, (0, 500000))

    def sec(tk):
        s, pt, cur = 0.0, 0, tempos[0][1]
        for tt, tp in tempos:
            if tt >= tk:
                break
            s += mido.tick2second(tt - pt, tpb, cur)
            pt, cur = tt, tp
        return s + mido.tick2second(tk - pt, tpb, cur)

    def tick(x):
        lo, hi = 0, 4 * 10 ** 6
        while lo < hi:
            m = (lo + hi) // 2
            if sec(m) < x:
                lo = m + 1
            else:
                hi = m
        return lo

    # the ending: Holst's bar, repeated twelve times and broadening
    t0, prevbar, starts = 454.93, 4.92, []
    for k in range(1, 13):
        bar = 4.92 + (5.80 - 4.92) * (k - 1) / 11
        t0 = t0 + (4.92 if k == 1 else prevbar)
        prevbar = bar
        starts.append((t0, bar))
    for p in parts:
        if p['name'] not in ENDING:
            continue
        a, b = ENDING[p['name']]
        for s, bar in starts:
            A, B, E = tick(s), tick(s + bar * 0.6), tick(s + bar)
            p['notes'] += [(A, B - 8, n, 30) for n in a] + [(B, E - 8, n, 26) for n in b]
        p['notes'].sort()
    # one continuous diminuendo, 30 -> 6, over the file's last bars and the repeats
    onsets = sorted({on for p in parts if p['name'] in ENDING
                     for on, _, _, _ in p['notes'] if sec(on) >= 439.0})
    V = {tk: max(5, int(round(30 * (6 / 30) ** (i / (len(onsets) - 1)))))
         for i, tk in enumerate(onsets)}
    for p in parts:
        if p['name'] in ENDING:
            p['notes'] = [(on, off, n, V.get(on, v)) for on, off, n, v in p['notes']]
    for p in parts:
        p['name'] = LABEL.get(p['name'], p['name'])

    assign, before, left, _ = M.colour(parts, [c for c in range(16) if c != 9])
    print("  %d parts over %d channels, %d overlaps (%d if all shared)"
          % (len(parts), len(set(assign.values())), left, before))
    print("  ending: %d chorus chords %.0f-%.0f s, velocity %d -> %d"
          % (len(onsets), sec(onsets[0]), sec(onsets[-1]), V[onsets[0]], V[onsets[-1]]))
    M.build(mid, parts, assign).save(dst)
    return {p['name']: assign[i] for i, p in enumerate(parts) if p['name'] in VOICES}


def _abs(track):
    t = 0
    for msg in track:
        t += msg.time
        yield t, msg


def split(src, keep_chorus, dst):
    """The chorus apart from the band, by PART: mt32mux writes each part as its
    own named track, and colours parts that never meet onto one channel -- so
    a split by channel would take other instruments along with the choruses
    (it did: 878 notes where the choruses have 549). The tempo track goes to
    both."""
    m = mido.MidiFile(src)
    out = mido.MidiFile(type=1, ticks_per_beat=m.ticks_per_beat)
    for i, tr in enumerate(m.tracks):
        name = next((x.name for x in tr if x.type == 'track_name'), None)
        if i == 0 or (name in VOICES) == keep_chorus:
            out.tracks.append(tr)
    out.save(dst)
    n = sum(1 for tr in out.tracks for x in tr if x.type == 'note_on' and x.velocity)
    print("  %-22s %5d notes" % (os.path.basename(dst), n))


def pad(*xs):
    n = max(len(x) for x in xs)
    return [np.pad(x, ((0, n - len(x)), (0, 0))) for x in xs]


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/neptune")
    os.makedirs(out, exist_ok=True)
    P = lambda name: os.path.join(out, name)        # noqa: E731
    src = P("neptune_crm.mid")
    if not os.path.exists(src):
        run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", src, URL])

    print("building the MIDI")
    chorus = build_midi(src, P("neptune_tool.mid"))
    chans = set(chorus.values())
    split(P("neptune_tool.mid"), False, P("neptune_band.mid"))
    split(P("neptune_tool.mid"), True, P("neptune_chorus.mid"))

    env = {"TUNING_ROOM": ROOM, "TUNING_WET": WET}
    voc = {"TUNING_VOCALISE": ",".join("%d=V" % c for c in sorted(chans)),
           "TUNING_VOICE_PARTS": ",".join("%d=%s" % (c, VOICES[n]) for n, c in sorted(chorus.items()))}
    br = os.path.join(HERE, "blockrender.py")
    print("rendering")
    run([sys.executable, br, P("neptune_band.mid"), P("np_band.wav"), TUNER], env)
    run([sys.executable, br, P("neptune_chorus.mid"), P("np_chorus.wav"), TUNER], dict(env, **voc))

    print("the room: each half from its own render's measurements")
    rt = os.path.join(HERE, "roomtail.py")
    run([sys.executable, rt, P("np_band.wav"), P("np_band_wet.wav")], env)
    run([sys.executable, rt, P("np_chorus.wav"), P("np_chorus_wet.wav")], env)

    t0, t1, direct_db, hall_db = RECEDE
    print("the chorus recedes: direct %+.0f dB, its hall %+.0f dB, %.0f-%.0f s" % (direct_db, hall_db, t0, t1))
    run([sys.executable, os.path.join(HERE, "recede.py"), P("np_band.wav"), P("np_chorus.wav"),
         P("np_recede.wav"), str(t0), str(t1), str(direct_db)], env)

    band, sr = read_wav(P("np_band.wav"))
    bwet, _ = read_wav(P("np_band_wet.wav"))
    cho, _ = read_wav(P("np_chorus.wav"))
    cwet, _ = read_wav(P("np_chorus_wet.wav"))
    rec, _ = read_wav(P("np_recede.wav"))
    band, bwet, cho, cwet, rec = pad(band, bwet, cho, cwet, rec)
    t = np.arange(len(band)) / float(sr)
    frac = np.clip((t - t0) / (t1 - t0), 0.0, 1.0)[:, None]
    # the band with its hall; the chorus's own hall, fading; the chorus's
    # direct sound as recede.py moved it away (its output is the band plus it)
    mix = bwet + (cwet - cho) * 10.0 ** (frac * hall_db / 20.0) + (rec - band)
    pk = np.abs(mix).max()
    write_wav(P("neptune.wav"), mix * (0.98 / pk) if pk > 0.98 else mix, sr)

    mp3 = P("neptune.mp3")
    run(["sox", P("neptune.wav"), P("np_norm.wav"), "norm", "-1"])
    run(["lame", "-b", "320", "-h", "--quiet", "--tt", "Neptune, the Mystic", "--ta", "Holst",
         "--tl", "The Planets", P("np_norm.wav"), mp3])
    for f in ("np_band.wav", "np_band_wet.wav", "np_chorus.wav", "np_chorus_wet.wav",
              "np_recede.wav", "np_norm.wav", "np_band.room.json", "np_chorus.room.json",
              "np_band.send.wav", "np_chorus.send.wav"):
        if os.path.exists(P(f)):
            os.remove(P(f))
    print("  -> %s" % mp3)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
