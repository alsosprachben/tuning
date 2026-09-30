#!/usr/bin/env python3
"""Hear what the Moog's panel does: one phrase, on the saw lead, per setting.

    python3 examples/moog_demo.py [--out DIR]

Each setting is knob positions over the patch (TUNING_MOOG_PANEL, moog.py),
rendered in the studio at the same level as the plain patch:

    plain      the saw lead as it ships
    lfo        LFO 1 on the cutoff: a 5 Hz triangle, 2 octaves, from the key
    sync       OSC 2 alone, hard-synced a fifth up (+7 st): the synced lead
    whistle    the oscillators off, RESONANCE fully up: the ladder's own sine
    noise      the noise oscillator alone through the ladder and its contour
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import moog_ab

SETTINGS = {
    'plain': {},
    'lfo': dict(lfo1_rate=0.8403, lfo1_depth=0.8333, lfo1_reset=True, lfo1_shape=0),
    'sync': dict(osc1_level=0.0, osc2_level=1.0, sync=True, osc2_freq=1.0, cutoff=0.7),
    'whistle': dict(osc1_level=0.0, osc2_level=0.0, resonance=1.0, eg_amount=0.5, kb_track=1.0,
                    cutoff=0.45),
    'noise': dict(osc1_level=0.0, osc2_level=0.0, noise_level=1.0),
}


def main(argv):
    args = argv[1:]
    out = os.path.expanduser('~/Downloads/moog_demo')
    if '--out' in args:
        out = os.path.expanduser(args[args.index('--out') + 1])
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, 'phrase.mid')
    moog_ab.phrase(81, mid)
    env = {'TUNING_ROOM': 'studio', 'TUNING_MASTER_DB': '-14'}
    ref = None
    for name, knobs in SETTINGS.items():
        w = os.path.join(out, '%s.dry.wav' % name)
        lib.render_plain(mid, w, tuner='even', extra_env=dict(env, TUNING_MOOG_PANEL=json.dumps(knobs)))
        loud = lib.loudness(w)
        ref = loud if ref is None else ref
        stem = os.path.join(out, name)
        lib.sum_wavs([w], stem + '.gain.wav', gains=[10 ** ((ref - loud) / 20.0)])
        lib.merge_room([os.path.splitext(w)[0] + '.room.json'], stem + '.gain.room.json')
        lib.roomtail(stem + '.gain.wav', stem + '.wav', env={'TUNING_ROOM': 'studio'})
        print('  %s' % lib.mp3(stem + '.wav'), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
