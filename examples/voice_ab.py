#!/usr/bin/env python3
"""A/B a voice's level in context, before recalibrating it.

    python3 examples/voice_ab.py [GM ...] [--out DIR]

For each candidate from voice_levels.py's system-wide table: eight bars in C --
a grand piano on the chords (I vi IV V, twice), a finger bass on the roots, and
the candidate in its natural role (melody, chords, or bass roots for timpani).
A is the candidate at its current level; B at the level both reference
soundfonts agree on. Every part is rendered on its own and summed at a gain, so
the candidate's level is the ONLY thing that differs, and each version gets the
same studio room (lib.merge_room + roomtail).
"""
import os
import sys

import mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

# GM program: (suggested change in dB, role), from voice_levels.py --all --drums
CANDIDATES = {
    104: (+14.0, 'melody'),    # Sitar
    79:  (+10.0, 'melody'),    # Ocarina
    105: (+8.0, 'melody'),     # Banjo
    107: (+8.0, 'melody'),     # Koto
    26:  (+8.0, 'melody'),     # Electric Guitar (jazz)
    62:  (+6.0, 'melody'),     # Synth Brass 1
    63:  (+7.0, 'melody'),     # Synth Brass 2
    85:  (+5.0, 'melody'),     # Lead 6 (voice)
    114: (-14.0, 'melody'),    # Steel Drums
    9:   (-7.0, 'melody'),     # Glockenspiel
    47:  (-10.0, 'bass'),      # Timpani
    18:  (-4.5, 'chords'),     # Rock Organ
}
TPB = 480
CHORDS = [(48, 52, 55), (45, 48, 52), (41, 45, 48), (43, 47, 50)] * 2        # C Am F G
MELODY = [67, 69, 72, 71, 69, 67, 64, 67,  69, 72, 76, 74, 72, 71, 69, 67,
          64, 65, 67, 69, 72, 71, 69, 67,  65, 67, 69, 71, 72, 74, 71, 72]    # quarters
ROOTS = [36, 33, 29, 31] * 2


def track(prog, ch, events):
    """events: [(beat, note, beats)] -> a one-part MIDI file."""
    m = mido.MidiFile(ticks_per_beat=TPB)
    t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=600000))
    t.append(mido.Message('program_change', channel=ch, program=prog))
    t.append(mido.Message('control_change', channel=ch, control=7, value=100))
    ev = []
    for b, n, d in events:
        ev.append((int(b * TPB), 1, mido.Message('note_on', channel=ch, note=n, velocity=90)))
        ev.append((int((b + d) * TPB) - 5, 0, mido.Message('note_off', channel=ch, note=n, velocity=0)))
    ev.sort(key=lambda e: (e[0], e[1]))
    last = 0
    for tick, _k, msg in ev:
        t.append(msg.copy(time=tick - last)); last = tick
    return m


def parts(role):
    piano = [(i * 4, n, 4) for i, c in enumerate(CHORDS) for n in c]
    bass = [(i * 4, r, 4) for i, r in enumerate(ROOTS)]
    if role == 'melody':
        cand = [(i, n, 1) for i, n in enumerate(MELODY)]
    elif role == 'chords':
        cand = [(i * 4, n + 12, 4) for i, c in enumerate(CHORDS) for n in c]
    else:                                            # timpani: roots, rolled in quarters
        cand = [(i * 4 + q, r + 12, 1) for i, r in enumerate(ROOTS) for q in range(4)]
    return piano, bass, cand


def main(argv):
    args = argv[1:]
    out = os.path.expanduser('~/Downloads/voice_ab')
    if '--out' in args:
        i = args.index('--out'); out = os.path.expanduser(args[i + 1]); del args[i:i + 2]
    progs = [int(a) for a in args] or list(CANDIDATES)
    os.makedirs(out, exist_ok=True)
    import livetui
    env = {'TUNING_ROOM': 'studio', 'TUNING_MASTER_DB': '-14'}
    for prog in progs:
        db, role = CANDIDATES.get(prog, (0.0, 'melody'))
        name = livetui.GM[prog].replace(' ', '_').replace('(', '').replace(')', '')
        piano, bass, cand = parts(role)
        wavs = []
        for tag, p, ch, evs in (('piano', 0, 0, piano), ('bass', 33, 1, bass), ('cand', prog, 2, cand)):
            mid = os.path.join(out, '%d.%s.mid' % (prog, tag))
            track(p, ch, evs).save(mid)
            wav = os.path.join(out, '%d.%s.wav' % (prog, tag))
            lib.render_plain(mid, wav, tuner='even', extra_env=env)
            wavs.append(wav)
        for label, g in (('A_current', 0.0), ('B_%+gdB' % db, db)):
            stem = os.path.join(out, '%03d_%s_%s' % (prog, name, label))
            lib.sum_wavs(wavs, stem + '.dry.wav', gains=[0.5, 0.5, 0.5 * 10 ** (g / 20.0)])
            lib.merge_room([os.path.splitext(w)[0] + '.room.json' for w in wavs], stem + '.dry.room.json')
            lib.roomtail(stem + '.dry.wav', stem + '.wav', env={'TUNING_ROOM': 'studio'})
            print('  %s' % lib.mp3(stem + '.wav'), flush=True)
            for ext in ('.dry.wav', '.wav', '.dry.room.json'):
                if os.path.exists(stem + ext):
                    os.remove(stem + ext)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
