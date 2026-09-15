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
    tube = '--tube' in argv or os.environ.get('TUNING_TRACT_TUBE') == '1'
    body = float(argv[argv.index('--body') + 1]) if '--body' in argv else 1.0

    import blockrender as B, vowels as W, vocaltract as VT, vocaltube as VU
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
    # THE TRACT COMES OUT OF THE CONSTRICTION. A point at the consonant's
    # locus just before each vowel means the formants TRAVEL into the vowel
    # rather than appearing at it -- which is the transition that makes a
    # consonant sound attached to its syllable.
    timeline = []
    for t, v, *rest in rows[ch]:
        if v not in W.VOWELS: continue
        if tube and v not in VU.SHAPES: continue
        con = rest[0] if rest else None
        loc = W.locus_of(con) if con else None
        # The locus must sit FURTHER BACK than the glide is wide, or the
        # move into it and the move out of it overlap and it is averaged
        # away -- which is what happened at 45 ms against a 70 ms glide:
        # the loci were all present and changed nothing.
        if tube:
            place = W.PLACE.get(con) if con else None
            if place in VU.SHAPES:
                timeline.append((max(0.0, t - glide * 1.35), VU.shape_of(place)))
            timeline.append((t, VU.shape_of(v)))
        else:
            if loc: timeline.append((max(0.0, t - glide * 1.35), loc))
            timeline.append((t, W.VOWELS[v]))
    timeline.sort(key=lambda r: r[0])
    print("  %d syllables on channel %d, glide %.0f ms, %s tract%s" % (
        len(timeline), ch, glide * 1000, "TUBE" if tube else "formant",
        (", %.1f cm" % (VU.TRACT_CM * body)) if tube else ""))

    x, sr = read_wav(tmp)
    y = VT.apply(x, sr, timeline, glide=glide, tube=tube,
                 tract_cm=VU.TRACT_CM * body)
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
