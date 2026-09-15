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
         body=None, glide=None, extra_env=None):
    """Render through singpass.py: flat source, then the tract as a filter."""
    env = dict(os.environ)
    if consonants:
        env['TUNING_CONSONANTS'] = '1'
    env.update(extra_env or {})
    cmd = [sys.executable, os.path.join(ROOT, 'singpass.py'), midi, out, tuner,
           '--lang', lang]
    if tube:
        cmd.append('--tube')
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
