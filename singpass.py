#!/usr/bin/env python3
"""Render a sung part through the source-filter model.

  1. the renderer makes the SOURCE: glottal buzz, pitch, vibrato, section
     spread, room -- with no tract (TUNING_VOCAL_FLAT=1)
  2. vocaltract.py applies the tract as a filter that moves between syllables
  3. the consonants are already noise and ride along unchanged

Usage: singpass.py IN.mid OUT.wav [tuner] [--lang latin] [--glide 0.07]
"""
import os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[-1]); return 2
    inp, outp = argv[1], argv[2]
    tuner = argv[3] if len(argv) > 3 and not argv[3].startswith('--') else 'even'
    lang = argv[argv.index('--lang') + 1] if '--lang' in argv else \
           os.environ.get('TUNING_LYRIC_LANG', 'latin')
    glide = float(argv[argv.index('--glide') + 1]) if '--glide' in argv else 0.070

    import blockrender as B, vowels as W, vocaltract as VT
    from roomtail import read_wav, write_wav

    env = dict(os.environ, TUNING_VOCAL_FLAT='1', TUNING_LYRIC_LANG=lang)
    tmp = outp + '.source.wav'
    subprocess.run([sys.executable, os.path.join(HERE, 'blockrender.py'),
                    inp, tmp, tuner], env=env, check=True,
                   stdout=subprocess.DEVNULL)

    rows = B._lyric_vowels(inp, lang)
    if not rows:
        print("  no lyrics; nothing to articulate"); return 1
    # every part sings the same text here, so one trajectory serves; take the
    # part with the most syllables
    ch = max(rows, key=lambda c: len(rows[c]))
    timeline = [(t, W.VOWELS[v]) for t, v, *_ in rows[ch] if v in W.VOWELS]
    print("  %d syllables on channel %d, glide %.0f ms" % (len(timeline), ch, glide * 1000))

    x, sr = read_wav(tmp)
    y = VT.apply(x, sr, timeline, glide=glide)
    # the tract filter changes the level; match the source's loudness
    a = float(np.sqrt((x.astype(np.float64) ** 2).mean()))
    b = float(np.sqrt((y.astype(np.float64) ** 2).mean()))
    if b > 1e-9: y = (y * (a / b)).astype(np.float32)
    write_wav(outp, y, sr)
    os.remove(tmp)
    print("  wrote %s" % outp)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
