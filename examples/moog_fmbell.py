#!/usr/bin/env python3
"""The FM-bell experiment: can 1->2 FM make the inharmonic voices?

    python3 examples/moog_fmbell.py [--out DIR]

GM 93 (metallic pad) and 98 (crystal) are the additive bank's inharmonic
voices -- stretched partials whose upper modes die first. A Moog player makes
metal with FM at a ratio off the whole numbers instead. For each program this
renders the additive voice (TUNING_MOOG=0) and a few Moog panels over the
class's patch (TUNING_MOOG_PANEL), on moog_ab's phrase, every one level-matched
to the additive, in the studio -- so the ear compares mechanisms, not levels.
Ben's verdicts are recorded with the candidates below.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import moog_ab

TRITONE = 0.5 + 600.0 / 1400.0
# Round 1, the ratio (Ben: "beat" for 93, "anchored" for 98):
#   93 tritone: osc2_octave=8, osc2_freq=TRITONE, mod_amount=0.7, osc1_level=0.35
#   98 tritone: osc2_octave=8, mod_amount=0.5 + 2/6, osc1_level=0.0
# Round 2, the RING, once the ladder hears each sideband at its own frequency
# (synthkernel.c, fm_sidebands): a filter contour that opens on the strike and
# closes as it rings -- the mellowing a struck bell has and a fixed FM index
# alone does not -- against the fixed filter of round 1. Ben: the mellow ones,
# now the classes' own patches.
CANDIDATES = {
    93: [('beat_mellow', {}),
         ('beat', dict(cutoff=0.85, eg_amount=0.5, f_attack=0.0, f_decay=0.6, f_sustain=1.0))],
    98: [('anchored_mellow', {}),
         ('anchored', dict(cutoff=0.85, eg_amount=0.5, f_attack=0.0, f_decay=0.6, f_sustain=1.0))],
}


def main(argv):
    args = argv[1:]
    out = os.path.expanduser('~/Downloads/moog_fmbell')
    if '--out' in args:
        i = args.index('--out'); out = os.path.expanduser(args[i + 1]); del args[i:i + 2]
    os.makedirs(out, exist_ok=True)
    env = {'TUNING_ROOM': 'studio', 'TUNING_MASTER_DB': '-14'}
    for prog, cands in CANDIDATES.items():
        mid = os.path.join(out, '%d.mid' % prog)
        moog_ab.phrase(prog, mid)
        runs = [('A_additive', dict(env, TUNING_MOOG='0'))]
        # the candidates were written in the first model's knob units, before
        # the Messenger was measured: converted as the patches were
        import moog as MG
        import patch_map as P
        ctx = MG.panel_of(P.property_class_for_note(prog, 60))
        runs += [('B_%s' % name, dict(env, TUNING_MOOG='1',
                                      TUNING_MOOG_PANEL=json.dumps(MG.convert_v1(over, context=ctx))))
                 for name, over in cands]
        wavs = {}
        for tag, e in runs:
            w = os.path.join(out, '%d_%s.dry.wav' % (prog, tag))
            lib.render_plain(mid, w, tuner='even', extra_env=e)
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
