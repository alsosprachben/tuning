#!/usr/bin/env python3
"""How loud each GM voice is, against two reference soundfonts.

    python3 examples/voice_levels.py [PROGRAM ...] [--out DIR]
    python3 examples/voice_levels.py --all [--drums]     # every GM program, every GM drum

With --all / --drums the table is SORTED by the biggest difference from
MuseScore, and aligned not to one voice but to the MEDIAN difference across
everything measured: the piano turned out to be a poor anchor (Debian's map
gives it amp=29), and a median is what "system-wide" can mean without trusting
any single voice. Drums are one GM drum note each, eight hits at velocity 100
on channel 10. Results go to OUT/levels.json as well.

Every program plays the same phrase -- a held C3-E3-G3-C4 chord, then a scale
C4 to C5 -- at velocity 100, through three engines:

    ours       blockrender, the studio room at its own distance
    musescore  MuseScore's MS Basic soundfont (snap run musescore -o)
    timidity   Debian's FluidR3 map, per-program amp and all

and each is measured K-weighted (lib.loudness, the gated median) against the
GRAND PIANO in the same engine: the most standardised GM voice, and one
instrument where the kit is a mixture. The kit is reported too.

CC7 = 127 and nothing else. On our organs (GM 16-19) CC7 is not a fader but
the swell, fully open at 127; on every other voice (v7*v11)^2 is unity there.
At the GM default of 100 the organs would read 4.15 dB hot against everything
else for that reason alone -- which is what the first comparison did. CC11 is
not sent: on the organs it is the stop word.

A verdict needs both references to agree within 3 dB; otherwise the row says
"no verdict" rather than averaging two opinions that disagree.
"""
import os
import subprocess
import sys

import mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

DEFAULT = [0, 16, 17, 18, 19, 80, 81, 82, 83, 84, 85, 86, 87, 115]
AGREE_DB = 3.0
KIT = 'kit'


def phrase(prog, path):
    """The test phrase for one program ('kit' for the standard kit, or
    'd<note>' for one GM drum note)."""
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=500000))
    if isinstance(prog, str) and prog.startswith('d'):
        ch, n = 9, int(prog[1:])
        t.append(mido.Message('control_change', channel=ch, control=7, value=127))
        for i in range(8):
            t.append(mido.Message('note_on', channel=ch, note=n, velocity=100))
            t.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=480))
    elif prog == KIT:
        ch = 9
        t.append(mido.Message('control_change', channel=ch, control=7, value=127))
        # kick, snare, closed hat: two bars of eighths
        seq = []
        for i in range(16):
            hits = [42]
            if i % 4 == 0: hits.append(36)
            if i % 4 == 2: hits.append(38)
            seq.append(hits)
        for hits in seq:
            for n in hits:
                t.append(mido.Message('note_on', channel=ch, note=n, velocity=100))
            t.append(mido.Message('note_off', channel=ch, note=hits[0], velocity=0, time=240))
            for n in hits[1:]:
                t.append(mido.Message('note_off', channel=ch, note=n, velocity=0))
    else:
        ch = 0
        t.append(mido.Message('program_change', channel=ch, program=prog))
        t.append(mido.Message('control_change', channel=ch, control=7, value=127))
        chord = (48, 52, 55, 60)
        for n in chord:
            t.append(mido.Message('note_on', channel=ch, note=n, velocity=100))
        t.append(mido.Message('note_off', channel=ch, note=chord[0], velocity=0, time=1440))
        for n in chord[1:]:
            t.append(mido.Message('note_off', channel=ch, note=n, velocity=0))
        for n in (60, 62, 64, 65, 67, 69, 71, 72):
            t.append(mido.Message('note_on', channel=ch, note=n, velocity=100))
            t.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=480))
    t.append(mido.MetaMessage('end_of_track', time=480))
    m.save(path)


def render(engine, mid, wav):
    if engine == 'ours':
        lib.render_plain(mid, wav, tuner='even', extra_env={'TUNING_ROOM': 'studio'})
    elif engine == 'musescore':
        subprocess.run(['snap', 'run', 'musescore', '-o', wav, mid], capture_output=True,
                       env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), timeout=300)
    else:
        subprocess.run(['timidity', '-EFreverb=0', '-EFchorus=0', '-Ow', '-o', wav, mid],
                       capture_output=True)
    return lib.loudness(wav) if os.path.exists(wav) and os.path.getsize(wav) > 1000 else None


def main(argv):
    args = [a for a in argv[1:]]
    out = os.path.expanduser('~/Downloads/voice_levels')   # snap MuseScore writes only under ~
    if '--out' in args:
        i = args.index('--out'); out = os.path.expanduser(args[i + 1]); del args[i:i + 2]
    wide = '--all' in args or '--drums' in args
    progs = list(range(128)) if '--all' in args else [int(a) for a in args if not a.startswith('--')]
    if not progs and not wide:
        progs = DEFAULT
    drums = ['d%d' % n for n in range(35, 82)] if '--drums' in args else []
    os.makedirs(out, exist_ok=True)
    want = [0, KIT] + [p for p in progs if p != 0] + drums
    L = {}
    for p in want:
        mid = os.path.join(out, 'p%s.mid' % p); phrase(p, mid)
        L[p] = {e: render(e, mid, os.path.join(out, 'p%s.%s.wav' % (p, e)))
                for e in ('ours', 'musescore', 'timidity')}
        print('  measured %-4s %s' % (p, ', '.join('%s %s' % (e, 'fail' if v is None else '%.1f' % v)
                                                  for e, v in L[p].items())), flush=True)
    import json
    json.dump({str(k): v for k, v in L.items()}, open(os.path.join(out, 'levels.json'), 'w'), indent=1)
    import livetui
    names = dict(enumerate(livetui.GM))
    if not wide:
        rel = lambda p, e: (L[p][e] - L[0][e]) if L[p][e] is not None and L[0][e] is not None else None
        print('\n  against the grand piano, dB:')
        print('  %-4s %-28s %7s %9s %9s %9s  %s' % ('GM', 'voice', 'ours', 'MuseScore', 'TiMidity',
                                                     'offset', 'verdict'))
        for p in want[1:]:
            name = 'standard kit' if p == KIT else names.get(p, '') or ''
            o, m, t = rel(p, 'ours'), rel(p, 'musescore'), rel(p, 'timidity')
            refs = [v for v in (m, t) if v is not None]
            if o is None or not refs:
                verdict, off = 'no measurement', None
            elif len(refs) < 2:
                verdict, off = 'no verdict (one reference)', refs[0] - o
            elif abs(m - t) > AGREE_DB:
                verdict, off = 'no verdict (refs differ %.1f dB)' % abs(m - t), (m + t) / 2 - o
            else:
                off = (m + t) / 2 - o
                verdict = 'ok' if abs(off) <= 1.5 else ('%+d dB' % round(off))
            f = lambda v: '   --' if v is None else '%+7.1f' % v
            print('  %-4s %-28s %s %9s %9s %9s  %s' % (p, name[:28], f(o), f(m).strip().rjust(9),
                                                       f(t).strip().rjust(9),
                                                       ('--' if off is None else '%+.1f' % off).rjust(9), verdict))
        return 0
    # SYSTEM-WIDE: each reference aligned to ours by the median difference
    # over everything both measured, then every voice's residual, sorted.
    import statistics
    def resid(e):
        d = {p: L[p][e] - L[p]['ours'] for p in want
             if L[p]['ours'] is not None and L[p][e] is not None and L[p][e] > -200}
        med = statistics.median(d.values()) if d else 0.0
        return {p: v - med for p, v in d.items()}, med
    rm, _ = resid('musescore')
    rt, _ = resid('timidity')
    def label(p):
        if isinstance(p, str) and p.startswith('d'):
            import percussion_map as PM
            nm = PM.PERCUSSION.get(int(p[1:]), ('',))[0]
            return 'drum %s %s' % (p[1:], nm)
        return 'kit' if p == KIT else '%3d %s' % (p, names.get(p, ''))
    rows = sorted(rm, key=lambda p: -abs(rm[p]))
    print('\n  ours against MuseScore, aligned by the median over %d voices; sorted by |difference|' % len(rm))
    print('  (+ = MuseScore louder: ours would need raising)')
    print('  %-34s %9s %9s  %s' % ('voice', 'MuseScore', 'TiMidity', 'agree?'))
    for p in rows:
        m, t = rm[p], rt.get(p)
        agree = '' if t is None else ('yes' if (m > 0) == (t > 0) and abs(m - t) <= AGREE_DB else
                                      ('same sign' if (m > 0) == (t > 0) else 'no'))
        print('  %-34s %+9.1f %9s  %s' % (label(p)[:34], m, '--' if t is None else '%+.1f' % t, agree))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
