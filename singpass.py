#!/usr/bin/env python3
"""Render a sung part through the source-filter model.

  1. the renderer makes the SOURCE: glottal buzz, pitch, vibrato, section
     spread, room -- with no tract (TUNING_VOCAL_FLAT=1)
  2. vocaltract.py applies the tract as a filter that moves between syllables
  3. the consonants are already noise and ride along unchanged

ONE TRACT PER PART, which is why this renders STEMS rather than a mix. A bass
and a treble do not share a throat: VOICE_BODIES puts them 30% apart in length
-- 19.0 cm against 14.6 -- and filtering a mixed stem can only apply one of
them to all of it, so every part was being sung down a 17.5 cm male tract.
blockrender's stems are a row selection over the same partial table and sum
back to the mix sample for sample, so each part can be filtered with its own
tract and its own words and added up with nothing lost.

Each part also gets ITS OWN lyric timeline now. The old path took whichever
channel had the most syllables and applied that trajectory to everything,
which is only right when the parts move together.

A channel with no lyrics passes through untouched, so this no longer needs a
voice-only file: an orchestra can come along and arrive unfiltered.

Usage: singpass.py IN.mid OUT.wav [tuner] [--lang latin] [--glide 0.07]
"""
import os, shutil, subprocess, sys
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
    dry = '--dry' in argv
    body = float(argv[argv.index('--body') + 1]) if '--body' in argv else 1.0

    import blockrender as B, vowels as W, vocaltract as VT, vocaltube as VU
    from roomtail import read_wav, write_wav

    import tonelib as T

    env = dict(os.environ, TUNING_VOCAL_FLAT='1', TUNING_LYRIC_LANG=lang)
    stems = outp + '.stems'
    subprocess.run([sys.executable, os.path.join(HERE, 'blockrender.py'),
                    inp, outp + '.ignored.wav', tuner, '--stems', stems],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    import json
    base = os.path.splitext(os.path.basename(inp))[0]
    with open(os.path.join(stems, base + '.objects.json')) as fh:
        man = json.load(fh)['objects']

    rows = B._lyric_vowels(inp, lang)
    parts = B._declared_voice_parts() or B._voice_parts(inp)

    acc = None
    sr = None
    for rec in man:
        ch = rec['channel']
        x, sr = read_wav(os.path.join(stems, rec['file']))
        name = parts.get(ch) if parts else None
        # voice_body() returns the PART it recognised, not a number; the
        # number is VOICE_BODIES' business. Tokenised, so "bassoon" is not
        # a bass.
        part = T.voice_body(name) if name else None
        ratio = T.VOICE_BODIES.get(part) if part else None
        # THE RATIO SCALES FORMANTS, SO THE LENGTH IS ITS RECIPROCAL. A bass
        # sits at 0.92 -- formants 8% low -- which is a tract 8% LONGER, not
        # shorter. Inverting this by hand once gave every bass a boy's throat.
        cm = VU.TRACT_CM / ratio if ratio else VU.TRACT_CM
        cm *= body
        line = [r for r in rows.get(ch, [])]
        if not line:
            print("  ch%-3d %-10s no words -- passes through" % (ch, part or ''))
            y = x
        else:
            timeline = []
            for t, v, *rest in line:
                if v not in W.VOWELS: continue
                if tube and v not in VU.SHAPES: continue
                con = rest[0] if rest else None
                if tube:
                    place = W.PLACE.get(con) if con else None
                    if place in VU.SHAPES:
                        timeline.append((max(0.0, t - glide * 1.35),
                                         VU.shape_of(place)))
                    timeline.append((t, VU.shape_of(v)))
                else:
                    loc = W.locus_of(con) if con else None
                    if loc:
                        timeline.append((max(0.0, t - glide * 1.35), loc))
                    timeline.append((t, W.VOWELS[v]))
            timeline.sort(key=lambda r: r[0])
            print("  ch%-3d %-10s %3d syllables, tract %.1f cm"
                  % (ch, part or '(unnamed)', len(timeline), cm))
            y = VT.apply(x, sr, timeline, glide=glide, tube=tube, tract_cm=cm)
            a = float(np.sqrt((x.astype(np.float64) ** 2).mean()))
            b = float(np.sqrt((y.astype(np.float64) ** 2).mean()))
            if b > 1e-9:
                y = (y * (a / b)).astype(np.float32)
        if acc is None:
            acc = np.zeros_like(y, dtype=np.float64)
        n = min(len(acc), len(y))
        acc[:n] += y[:n]
    if acc is None:
        print("  nothing rendered"); return 1
    y = acc.astype(np.float32)
    tmp = os.path.join(stems, base + '.room.json')

    side = tmp
    if dry or not os.path.exists(side):
        write_wav(outp, y, sr)
        if os.path.exists(side):
            # KEEP THE SIDECAR when the room is deferred. A dry stem is only
            # useful if what it fed the room travels with it -- otherwise the
            # mix it lands in has to guess, and roomtail falls back to a
            # scalar Q that is wrong by whatever this piece actually radiated.
            shutil.copyfile(side, os.path.splitext(outp)[0] + '.room.json')
        elif not dry:
            print("  no %s -- rendered DRY" % os.path.basename(side))
    else:
        # THE ROOM GOES AFTER THE TRACT, because the tract is part of the
        # voice: source, then tract, then lips, and only then a hall. Putting
        # it first would filter the reverberation with the singer's vowel.
        #
        # blockrender computes only the first-order images; the diffuse tail is
        # roomtail's convolution, and singpass never ran it -- which is why
        # every sung render so far has been nearly dry, one image per partial
        # and nothing else.
        #
        # THE SIDECAR SURVIVES THE FILTER. room_q is a RATIO per band, direct
        # energy over energy fed to the room, and the tract multiplies both by
        # the same thing -- so a figure measured on the unfiltered source is
        # still the right one here. It would NOT survive anything that treats
        # the direct and reverberant shares differently.
        mid = os.path.splitext(outp)[0] + '.dry.wav'
        write_wav(mid, y, sr)
        shutil.copyfile(side, os.path.splitext(mid)[0] + '.room.json')
        subprocess.run([sys.executable, os.path.join(HERE, 'roomtail.py'),
                        mid, outp], check=True)
        for p in (mid, os.path.splitext(mid)[0] + '.room.json'):
            if os.path.exists(p):
                os.remove(p)
    shutil.rmtree(stems, ignore_errors=True)
    for p in (outp + '.ignored.wav',):
        if os.path.exists(p):
            os.remove(p)
    print("  wrote %s" % outp)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
