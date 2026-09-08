#!/usr/bin/env python3
"""Put the soloist in FRONT rather than merely louder.

Raising a part's CC7 scales its direct sound and its share of the reverberant
field together: that is a player blowing harder from the same chair, and it
arrives louder and exactly as wet. Moving a player FORWARD is a different
thing. The reverberant field of a room is uniform and set by the total power
radiated into it, not by where the source stands, so a closer source gives more
direct sound while feeding the room the same amount. Closer is louder AND
drier, and that difference is the whole reason a soloist is placed at the front
of a stage rather than told to play harder.

So: render the soloist and the band as separate stems, add the boost to the
soloist's DIRECT only, and take the tail from the unboosted sum.

    out = band + G*solo + tail(band + solo)

recede.py is this same mechanism run backwards, for a source that walks away.

This exists because the renderer has no solo/section distinction of its own:
a GM violin is ViolinProperties, which is seven players, and there is no
program number that means "one of these". Until there is, the soloist has to
be separated after the fact by channel, which is what SOLO_CH is.

Usage: soloforward.py IN.mid SOLO_CH OUT.wav GAIN_DB [ROOM]
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from roomtail import read_wav, write_wav


def main(argv):
    if len(argv) < 5:
        print(__doc__.strip().splitlines()[-1])
        return 2
    inp, solo_ch, outp = argv[1], int(argv[2]), argv[3]
    gain_db = float(argv[4])
    room = argv[5] if len(argv) > 5 else 'chapel'
    env = dict(os.environ, TUNING_ROOM=room)
    # Stems are summed before the tail is taken, so the sum has to survive at
    # the same headroom a single render would need. Overridable, because a
    # dense piece may want more.
    env.setdefault('TUNING_MASTER_DB', '-12')

    tmp = tempfile.mkdtemp(prefix='soloforward.')
    try:
        stems = os.path.join(tmp, 'stems')
        subprocess.run([sys.executable, os.path.join(HERE, 'blockrender.py'),
                        inp, os.path.join(tmp, 'all.wav'), 'hybrid',
                        '--stems', stems], env=env, check=True)
        base = os.path.splitext(os.path.basename(inp))[0]
        solo, parts, sr, found = None, [], 44100, []
        for f in sorted(glob.glob(os.path.join(stems, base + '.ch*.wav'))):
            ch = int(os.path.basename(f).split('.ch')[1][:2])
            found.append(ch)
            a, sr = read_wav(f)
            if ch == solo_ch:
                solo = a
            else:
                parts.append(a)
        if solo is None:
            print("channel %d produced no stem; this piece has %s"
                  % (solo_ch, ", ".join(str(c) for c in found) or "none"))
            return 1

        n = min([len(solo)] + [len(a) for a in parts])
        solo = solo[:n]
        band = np.zeros_like(solo)
        for a in parts:
            band += a[:n]

        # The tail is excited by what the players actually radiate. The boost is
        # a POSITION, not more power, so it must not appear here.
        wet_in = os.path.join(tmp, 'sum.wav')
        write_wav(wet_in, band + solo, sr)
        subprocess.run([sys.executable, os.path.join(HERE, 'roomtail.py'),
                        wet_in, os.path.join(tmp, 'wet.wav')],
                       env=env, check=True)
        wet, _ = read_wav(os.path.join(tmp, 'wet.wav'))
        wet = wet[:n] - (band + solo)          # the tail alone

        out = band + 10.0 ** (gain_db / 20.0) * solo + wet
        write_wav(outp, out, sr)
        print("  solo ch%d %+.1f dB of DIRECT only; tail from the unboosted sum"
              % (solo_ch, gain_db))
        print("  peak %.3f -> %s" % (np.abs(out).max(), outp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
