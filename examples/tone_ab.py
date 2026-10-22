#!/usr/bin/env python3
"""A GS tone at several settings, in a file's own context, for the ear: some
tracks of a window of the file, every track's setup kept -- ports, SysEx
(the EFX, the reverb, the parts), controllers, program changes -- and only
the chosen tracks' notes, so a tone is heard as the file plays it.

    python3 examples/tone_ab.py FILE.mid TRACKS START_S SECONDS OUT_DIR PROG.BANK \
        NAME='{"attr": value, ...}' [NAME='{...}' ...]

TRACKS is comma-separated track indices. Each NAME installs, as PROG.BANK,
GM PROG's voice with those class attributes (a "set" tone, patch_map's
SC88_CHEAP form), plus an optional "trim_db" (the level, over the program's
trim) and "_base" (the program whose voice it is a setting of, PROG's own
by default) or "_class" (a tonelib class to play instead, for a tone
with code of its own); '{}' is the program's voice as it is. Writes OUT_DIR/<file>_<NAME>.wav
at one common gain (the loudest take's peak to -1 dB), so levels compare.
--room adds the room's tail as a full render has it (roomtail.py, from the
sidecar the render leaves: the bands it radiated, each part's send, the GS
room), to OUT_DIR/<file>_<NAME>_room.wav.
"""
import json
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B   # noqa: E402
import patch_map as P     # noqa: E402


def window(path, tracks, t0, secs):
    """The file with only the window [t0, t0 + secs) s of the chosen tracks'
    notes: every other message kept AT ITS OWN TIME, so the setup (a GS reset
    in one track, the programs in others) happens in the file's order, and
    nothing after the window. Render it and drop the first t0 seconds.

    (Moving the setup to time 0 broke that order across tracks: Tokei's GS
    reset, sent at 0.07 s by one track, landed after other tracks' program
    changes and wiped them -- the strings played a piano.)"""
    mf = mido.MidiFile(path)
    tempo = []
    for tr in mf.tracks:
        t = 0
        for m in tr:
            t += m.time
            if m.type == 'set_tempo':
                tempo.append((t, m.tempo))
    tempo.sort()

    def sec(tk):
        s, lt, tp = 0.0, 0, 500000
        for t, tv in tempo:
            if t >= tk:
                break
            s += (t - lt) * tp / mf.ticks_per_beat / 1e6
            lt, tp = t, tv
        return s + (tk - lt) * tp / mf.ticks_per_beat / 1e6

    out = mido.MidiFile(ticks_per_beat=mf.ticks_per_beat)
    for ti, tr in enumerate(mf.tracks):
        keep = ti in tracks
        ev, t, held = [], 0, set()
        for m in tr:
            t += m.time
            s = sec(t)
            if s >= t0 + secs:
                break
            note = m.type in ('note_on', 'note_off')
            if m.type == 'end_of_track':
                continue
            if note:
                on = m.type == 'note_on' and m.velocity
                k = (m.channel, m.note)
                if on:
                    if not keep or s < t0:
                        continue
                    held.add(k)
                elif k in held:
                    held.discard(k)
                else:
                    continue
            ev.append((t, m))
        o = mido.MidiTrack()
        last = 0
        for tk, m in ev:
            o.append(m.copy(time=tk - last))
            last = tk
        for ch, n in sorted(held):
            o.append(mido.Message('note_off', channel=ch, note=n, time=0))
        out.tracks.append(o)
    return out


def sidecar(f):
    """The room sidecar a full render writes beside f (blockrender's main),
    from the last render: its bands' radiation, the sends of the parts that
    sound (one number where they agree, as there; their mean where they do
    not -- an A/B's parts mostly agree), and the GS room."""
    lp = B._LAST_PREP
    rq = lp.get('room_q')
    if not rq:
        return False
    rs = lp.get('reverb_send') or {}
    heard = sorted(set(int(c) for c in np.unique(lp['mch'])))
    vals = [rs.get(c, 1.0) for c in heard]
    v = float(np.mean(vals)) if vals else 1.0
    with open(os.path.splitext(f)[0] + '.room.json', 'w') as fh:
        json.dump(dict({'bands': [{'hz': a, 'q': q, 'energy': e} for a, q, e in rq],
                        'send': {str(c): v for c in heard}}, **dict(B._GS_ROOM)), fh, indent=1)
    return True


def main(argv):
    room = '--room' in argv
    argv = [a for a in argv if a != '--room']
    path, tracks = argv[1], {int(v) for v in argv[2].split(',')}
    t0, secs, out = float(argv[3]), float(argv[4]), argv[5]
    prog, bank = (int(v) for v in argv[6].split('.'))
    takes = []
    for a in argv[7:]:
        nm, js = a.split('=', 1)
        takes.append((nm, json.loads(js)))
    name = os.path.splitext(os.path.basename(path))[0].lower()
    m = window(path, tracks, t0, secs)
    keep_v = P.VARIATIONS.get((prog, bank))
    keep_t = P.VARIATION_TRIM_DB.get((prog, bank))
    got = []
    try:
        for nm, attrs in takes:
            attrs = dict(attrs)
            trim = attrs.pop('trim_db', 0.0)
            base = int(attrs.pop('_base', prog))     # the voice it is a setting of
            # through the program's own router (a section's registers, a
            # split), as a "set" tone is; one class name for every take, so
            # each take's random phases are the same draw and only the
            # settings differ -- the router's cache cleared between takes
            P._ROUTED_CLASSES.clear()
            cls = attrs.pop('_class', None)          # a tonelib class of its own, not a setting
            P.VARIATIONS[(prog, bank)] = (type("ToneAB", (getattr(__import__("tonelib"), cls),), attrs)
                                          if cls else P.routed_variation(base, "toneab", **attrs))
            P.VARIATION_TRIM_DB[(prog, bank)] = P.PROGRAM_TRIM_DB.get(prog, 0.0) + trim
            L, R = B.render(m, "even")[:2]
            k0 = int(t0 * B.SR)
            got.append((nm, np.asarray(L, float)[k0:], np.asarray(R, float)[k0:]))
            if room:
                sidecar(os.path.join(out, "%s_%s.wav" % (name, nm)))
            print("  %-12s %s" % (nm, attrs), flush=True)
    finally:
        for d, k, v in ((P.VARIATIONS, (prog, bank), keep_v), (P.VARIATION_TRIM_DB, (prog, bank), keep_t)):
            if v is None:
                d.pop(k, None)
            else:
                d[k] = v
    pk = max(max(np.abs(l).max(), np.abs(r).max()) for _, l, r in got)
    g = 10 ** (-1 / 20.0) / pk
    for nm, l, r in got:
        f = os.path.join(out, "%s_%s.wav" % (name, nm))
        B.write_wav(f, l * g, r * g)
        print("  %s  rms %.1f dB" % (f, 10 * np.log10(((l * l + r * r) / 2).mean() * g * g)))
        if room:
            subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                            os.path.splitext(f)[0] + "_room.wav"], check=True,
                           stdout=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
