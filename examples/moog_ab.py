#!/usr/bin/env python3
"""A/B the Moog voices against the additive ones they replace.

    python3 examples/moog_ab.py [GM ...] [--out DIR]

For GM 80 and 81 (or those named): a phrase on the lead -- running quarters,
then long notes, so the filter contour is heard both snapping on each key and
settling under a held one -- rendered on the old additive lead
(TUNING_MOOG=0) and on the Moog, the Moog's level matched to the old one
(lib.loudness), both in the studio. Only the voice differs. A bass is
played two octaves down, where it lives; a pad plays chords.
"""
import os
import sys

import mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

TPB = 480
# (beat, note, beats): a run, a leap, and three held notes
PHRASE = ([(i * 0.5, n, 0.5) for i, n in enumerate([60, 62, 64, 65, 67, 69, 71, 72,
                                                    71, 69, 67, 65, 64, 62, 60, 55])]
          + [(8.0, 60, 2.0), (10.0, 67, 2.0), (12.0, 72, 4.0), (16.5, 48, 3.0)])


# A PAD IS HEARD IN CHORDS: four held, then the same four struck on the
# beat, so both the swell and the front are heard, and poly voices overlap.
CHORDS = [(48, 55, 60, 64), (45, 52, 57, 60), (41, 48, 53, 57), (43, 50, 55, 59)]
CHORD_PHRASE = ([(i * 4.0, n, 4.0) for i, c in enumerate(CHORDS) for n in c]
                + [(16.0 + i * 1.0, n, 0.9) for i, c in enumerate(CHORDS * 2) for n in c]
                + [(24.0, n, 6.0) for n in CHORDS[0]])
CHORDAL = {50, 51, 54, 88, 89, 90, 91, 92, 93, 94, 95, 97, 99, 100, 101, 103}

# where each program is played, in semitones from the phrase as written
REGISTER = {38: -24, 39: -24}


def phrase(prog, path):
    shift = REGISTER.get(prog, 0)
    m = mido.MidiFile(ticks_per_beat=TPB)
    t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(100)))
    t.append(mido.Message('program_change', channel=0, program=prog))
    ev = []
    for b, n, d in (CHORD_PHRASE if prog in CHORDAL else PHRASE):
        ev.append((int(b * TPB), 1, mido.Message('note_on', channel=0, note=n + shift, velocity=100)))
        ev.append((int((b + d) * TPB) - 10, 0, mido.Message('note_off', channel=0, note=n + shift, velocity=0)))
    ev.sort(key=lambda e: (e[0], e[1]))
    last = 0
    for tick, _k, msg in ev:
        t.append(msg.copy(time=tick - last)); last = tick
    m.save(path)


def main(argv):
    args = argv[1:]
    out = os.path.expanduser('~/Downloads/moog_ab')
    if '--out' in args:
        i = args.index('--out'); out = os.path.expanduser(args[i + 1]); del args[i:i + 2]
    progs = [int(a) for a in args] or [80, 81]
    os.makedirs(out, exist_ok=True)
    env = {'TUNING_ROOM': 'studio', 'TUNING_MASTER_DB': '-14'}
    for prog in progs:
        mid = os.path.join(out, '%d.mid' % prog)
        phrase(prog, mid)
        wavs = {}
        for tag, moog in (('A_additive', '0'), ('B_moog', '1')):
            w = os.path.join(out, '%d_%s.dry.wav' % (prog, tag))
            lib.render_plain(mid, w, tuner='even', extra_env=dict(env, TUNING_MOOG=moog))
            wavs[tag] = w
        ref = lib.loudness(wavs['A_additive'])
        for tag, w in wavs.items():
            db = ref - lib.loudness(w)
            stem = os.path.join(out, '%d_%s' % (prog, tag))
            lib.sum_wavs([w], stem + '.gain.wav', gains=[10 ** (db / 20.0)])
            lib.merge_room([os.path.splitext(w)[0] + '.room.json'], stem + '.gain.room.json')
            lib.roomtail(stem + '.gain.wav', stem + '.wav', env={'TUNING_ROOM': 'studio'})
            print('  %s  (%+.1f dB to match)' % (lib.mp3(stem + '.wav'), db), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
