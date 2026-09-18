#!/usr/bin/env python3
"""Shared machinery for the example renders.

Every render in this directory was first done as a throwaway shell pipeline,
and the throwaway versions are why the same three mistakes kept recurring:
dropping the conductor track (the piece then plays at the 120 bpm default,
which reads as "the accompaniment is exactly twice as fast"), guessing which
tracks are the choir, and comparing two renders made under different settings.
Each of those is handled once, here.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def from_musicxml(src, dest=None):
    """Convert a MusicXML/.mxl score to MIDI with the MuseScore CLI.

    NOTE WHAT THIS LOSES: MuseScore's MIDI export throws slurs away -- it
    renders them as legato, so a phrase comes out 97% overlapped with runs of
    velocity 127 and no mark of where the phrasing was. If the articulation
    matters, keep the score and use rearticulate.py to put the slurs back.
    """
    dest = dest or os.path.splitext(src)[0] + '.mid'
    if os.path.exists(dest) and os.path.getmtime(dest) > os.path.getmtime(src):
        return dest
    exe = next((p for p in ('musescore', 'mscore', 'musescore4', 'mscore4')
                if _which(p)), None)
    if exe is None:
        raise SystemExit("no MuseScore CLI found; cannot convert %s" % src)
    subprocess.run([exe, '-o', dest, src], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


def _which(p):
    from shutil import which
    return which(p)


def describe(path):
    """Every track: name, notes, lyrics, channel, patch. Look before cutting."""
    import mido
    m = mido.MidiFile(path)
    out = []
    for i, t in enumerate(m.tracks):
        out.append({
            'i': i, 'name': t.name,
            'notes': sum(1 for e in t if e.type == 'note_on' and e.velocity > 0),
            'lyrics': sum(1 for e in t if e.type == 'lyrics'),
            'channels': sorted({e.channel for e in t if hasattr(e, 'channel')}),
            'programs': sorted({e.program for e in t if e.type == 'program_change'}),
        })
    return out


def take_tracks(src, dest, keep):
    """Write a MIDI with only `keep` (track indices) -- PLUS track 0.

    TRACK 0 IS THE CONDUCTOR and it is not optional. In a typical engraving
    export it holds no notes at all, only the tempo map and time signatures, so
    it looks like an empty track worth dropping. Drop it and everything that
    remains plays at the 120 bpm default.
    """
    import mido
    m = mido.MidiFile(src)
    o = mido.MidiFile(ticks_per_beat=m.ticks_per_beat)
    for i in ([0] + [k for k in keep if k != 0]):
        o.tracks.append(m.tracks[i])
    o.save(dest)
    return dest


def choir_tracks(path, min_lyrics=1):
    """Indices of the tracks that are a singing choir.

    A part is a choir part if it has notes AND lyrics. Names alone are not
    enough: engravings routinely carry empty staves named 'Soprano' next to the
    real ones, and this file has four of each.
    """
    return [t['i'] for t in describe(path)
            if t['notes'] > 0 and t['lyrics'] >= min_lyrics]


def sing(midi, out, lang='latin', tube=False, tuner='even', consonants=True,
         body=None, glide=None, dry=False, extra_env=None):
    """Render through singpass.py: flat source, then the tract as a filter."""
    env = dict(os.environ)
    if consonants:
        env['TUNING_CONSONANTS'] = '1'
    env.update(extra_env or {})
    cmd = [sys.executable, os.path.join(ROOT, 'singpass.py'), midi, out, tuner,
           '--lang', lang]
    if tube:
        cmd.append('--tube')
    if dry:
        cmd.append('--dry')
    if body:
        cmd += ['--body', str(body)]
    if glide:
        cmd += ['--glide', str(glide)]
    subprocess.run(cmd, check=True, env=env)
    return out


def mp3(src, dest=None, peak_db=-1.0, bitrate=192):
    dest = dest or os.path.splitext(src)[0] + '.mp3'
    subprocess.run(['sox', src, '-C', str(bitrate), dest,
                    'gain', '-n', str(peak_db)], check=True)
    return dest


def bands(path, edges=((200, 400), (400, 800), (800, 1600), (1600, 2800),
                       (2800, 4500), (4500, 8000))):
    """Average band energy in dB, referenced to the first band.

    Here because comparing two renders by EAR alone has repeatedly hidden a
    20 dB spectral difference, and comparing them by a single broadband number
    has repeatedly hidden the opposite.
    """
    import numpy as np
    from roomtail import read_wav
    x, sr = read_wav(path)
    x = x.mean(1).astype(float)
    N = 8192
    w = np.hanning(N)
    acc = np.zeros(N // 2 + 1)
    k = 0
    for s in range(0, len(x) - N, N * 2):
        seg = x[s:s + N]
        if (seg ** 2).mean() < 1e-8:
            continue
        acc += np.abs(np.fft.rfft(seg * w)) ** 2
        k += 1
    acc /= max(k, 1)
    f = np.fft.rfftfreq(N, 1.0 / sr)
    out = []
    ref = None
    for lo, hi in edges:
        m = (f > lo) & (f < hi)
        v = 10 * np.log10(acc[m].mean() + 1e-30)
        if ref is None:
            ref = v
        out.append((lo, hi, v - ref))
    return out


def merge_room(sidecars, dest):
    """Combine several stems' .room.json into one for the summed mix.

    Exactly, not approximately. Each band carries q -- direct energy over
    energy fed to the room -- and the direct energy itself, so the room share
    is energy/q, the two shares add across stems, and the combined q is their
    ratio. Roomtailing the stems separately and adding them would also be
    linear and would also be right; what is NOT right is taking one stem's q
    for the pair, which is what happens if a mix inherits whichever sidecar it
    finds first. A choir and a string section do not feed a hall alike.
    """
    import json
    bands = {}
    for path in sidecars:
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            for b in json.load(fh)['bands']:
                d, q = float(b['energy']), float(b['q']) or 1.0
                acc = bands.setdefault(b['hz'], [0.0, 0.0])
                acc[0] += d
                acc[1] += d / q
    if not bands:
        return None
    out = [{'hz': hz, 'q': (d / r) if r > 0.0 else 1.0, 'energy': d}
           for hz, (d, r) in sorted(bands.items())]
    with open(dest, 'w') as fh:
        json.dump({'bands': out}, fh, indent=1)
    return dest


def sum_wavs(paths, dest, gains=None, headroom_db=-1.0):
    """Add stems sample for sample, padding to the longest.

    Summing stems removes headroom that neither of them lacked: the Dies Irae's
    choir peaks at 0.47 and its orchestra at 0.34, and lifting the choir 7 dB
    to undo the exporter's flat velocities put the sum on the ceiling at one
    sample. One sample is nothing to hear, but it says the margin is gone and
    a bigger bar would clip in earnest -- so the sum is scaled to fit, which
    costs nothing downstream because roomtail is linear and the mp3 is
    normalised anyway.
    """
    import numpy as np
    from roomtail import read_wav, write_wav
    gains = gains or [1.0] * len(paths)
    acc = None
    sr = None
    for p, g in zip(paths, gains):
        x, sr = read_wav(p)
        x = x.astype(np.float64) * g
        if acc is None:
            acc = x
        elif len(x) > len(acc):
            x[:len(acc)] += acc
            acc = x
        else:
            acc[:len(x)] += x
    peak = float(np.abs(acc).max())
    ceiling = 10.0 ** (headroom_db / 20.0)
    if peak > ceiling:
        acc *= ceiling / peak
        print("  sum peaked at %.3f; scaled %.1f dB to fit"
              % (peak, 20.0 * np.log10(ceiling / peak)))
    write_wav(dest, acc.astype(np.float32), sr)
    return dest


def roomtail(src, dest, env=None):
    """Convolve the diffuse tail, using the sidecar beside `src`.

    Pass the SAME TUNING_ROOM the render used. blockrender builds the
    first-order images against one room and this builds the late field against
    another if you let it, which puts a hall's early reflections in front of a
    different hall's tail.
    """
    e = dict(os.environ)
    e.update(env or {})
    subprocess.run([sys.executable, os.path.join(ROOT, 'roomtail.py'),
                    src, dest], check=True, env=e)
    return dest


def render_plain(midi, out, tuner='even', lang=None, extra_env=None):
    """blockrender straight through -- for parts that are not sung.

    The tract pass in singpass.py filters the WHOLE file, so anything that is
    not a voice has to come this way. Running an orchestra through singpass
    puts the strings inside somebody's mouth.
    """
    env = dict(os.environ)
    if lang:
        env['TUNING_LYRIC_LANG'] = lang
    env.update(extra_env or {})
    subprocess.run([sys.executable, os.path.join(ROOT, 'blockrender.py'),
                    midi, out, tuner], check=True, env=env,
                   stdout=subprocess.DEVNULL)
    return out


def other_tracks(path, exclude):
    """Indices of tracks with notes that are not in `exclude` (and not 0)."""
    return [t['i'] for t in describe(path)
            if t['notes'] > 0 and t['i'] not in exclude and t['i'] != 0]


def overlap_balance(a, b, window=0.25, floor=0.06):
    """Median dB of `a` against `b`, measured ONLY where `a` is sounding.

    A ratio taken over a whole movement answers a question nobody asked. The
    Dies Irae's choir sings in 38% of it, so the orchestra's tutti bars drag
    the average down and report a balance that is not the one anyone hears.
    What matters is the two together.
    """
    import numpy as np
    from roomtail import read_wav
    x, sr = read_wav(a)
    y, _ = read_wav(b)
    n = min(len(x), len(y))
    x = x[:n].mean(1).astype(float)
    y = y[:n].mean(1).astype(float)
    w = int(window * sr)
    xs = np.array([np.sqrt((x[i:i + w] ** 2).mean()) for i in range(0, n - w, w)])
    ys = np.array([np.sqrt((y[i:i + w] ** 2).mean()) for i in range(0, n - w, w)])
    act = xs > xs.max() * floor
    if not act.any():
        return 0.0, 0.0
    r = 20 * np.log10(xs[act] / np.maximum(ys[act], 1e-12))
    return float(np.median(r)), float(act.mean())


def has_dynamics(path, min_distinct=4):
    """Which tracks carry real dynamics, and which are one flat velocity.

    Engraving exports often write a fixed velocity per staff -- LilyPond's
    Dies Irae gives every choir note 95 and every first violin 101 -- so
    summing stems at unit gain there preserves the EXPORTER'S defaults and
    calls them the composer's. Worth knowing before trusting a balance.
    """
    import mido
    out = {}
    for i, t in enumerate(mido.MidiFile(path).tracks):
        v = {e.velocity for e in t if e.type == 'note_on' and e.velocity > 0}
        if v:
            out[i] = (len(v) >= min_distinct, sorted(v))
    return out


def stop_names(program):
    """The ranks a program's pipe voice offers, in bit order."""
    import blockrender
    pc = blockrender.property_class_for_program(program)
    return [r[0] for r in pc(261.6, 0, 1, 1).stop_ranks]


def set_stops(src, dest, draw, verbose=True):
    """Redraw an organ's registration: {channel: [rank names]}.

    A channel's value may instead be [(seconds, [names]), ...], which is a
    REGISTRATION THAT CHANGES, and usually the honest answer. One mask for a
    five-minute praeludium is not what a player does: the Mixtur that earns
    its place on the ascending run before the ending does not earn it in bar
    one, and left drawn throughout it is simply a thick piece.

    The stop word is 14 bits, CC11 carrying the low seven and CC43 the high
    seven, indexed against the voice's own stop_ranks. NOTE THAT CC11 IS NOT
    EXPRESSION on a pipe voice -- it is half the stop word, and treating it as
    a volume curve draws stops instead of shaping a line.

    A channel given an empty list is REMOVED, not silenced. A silent channel
    still builds its partials and gates them to nothing, which costs the same
    to render as playing it.
    """
    import mido
    prog = {}
    for t in mido.MidiFile(src).tracks:
        for e in t:
            if e.type == 'program_change':
                prog[e.channel] = e.program
    m = mido.MidiFile(src)
    tempo = next((e.tempo for t in m.tracks for e in t
                  if e.type == 'set_tempo'), 500000)
    tps = m.ticks_per_beat * 1e6 / tempo        # ticks per second
    out = mido.MidiFile(ticks_per_beat=m.ticks_per_beat, type=m.type)
    for t in m.tracks:
        chans = {e.channel for e in t if hasattr(e, 'channel')}
        ch = next(iter(chans)) if len(chans) == 1 else None
        if ch is not None and ch in draw and not draw[ch]:
            if verbose:
                print("  ch%-2d dropped (no stops drawn)" % ch)
            continue
        nt = mido.MidiTrack()
        nt.name = t.name
        carry = 0
        for e in t:
            if e.type == 'control_change' and e.control in (11, 43):
                if ch in draw:
                    carry += e.time       # keep the timing, drop the event
                    continue
            if carry:
                e = e.copy(time=e.time + carry)
                carry = 0
            nt.append(e)
        if ch in draw:
            names = stop_names(prog.get(ch, 19))
            spec = draw[ch]
            if spec and not isinstance(spec[0], tuple):
                spec = [(0.0, spec)]

            def word(ns):
                v = 0
                for n in ns:
                    if n not in names:
                        raise SystemExit("ch%d has no %r stop; it has %s"
                                         % (ch, n, names))
                    v |= 1 << names.index(n)
                return v

            # absolute ticks, so changes can be dropped in by the clock
            abst = []
            acc = 0
            for e in nt:
                acc += e.time
                abst.append(acc)
            items = list(zip(abst, nt))
            for sec, ns in spec:
                tick = int(round(sec * tps))
                w = word(ns)
                items.append((tick, mido.Message('control_change', channel=ch,
                                                 control=11, value=w & 0x7F)))
                items.append((tick, mido.Message('control_change', channel=ch,
                                                 control=43,
                                                 value=(w >> 7) & 0x7F)))
                if verbose:
                    print("  ch%-2d at %6.1f s  %s" % (ch, sec, ', '.join(ns)))
            # program change must still precede the stops it applies to
            items.sort(key=lambda r: (r[0], 0 if r[1].type == 'program_change'
                                      else 1))
            nt = mido.MidiTrack()
            nt.name = t.name
            prev = 0
            for tick, e in items:
                nt.append(e.copy(time=tick - prev))
                prev = tick
        out.tracks.append(nt)
    out.save(dest)
    return dest
