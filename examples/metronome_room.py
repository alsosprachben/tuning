#!/usr/bin/env python3
"""Ben's metronome against ours, with Ben's room put back on ours.

    python3 examples/metronome_room.py measure     the room, from the bell-off take
    python3 examples/metronome_room.py ab [OUTDIR]  recorded, then ours in the room
    python3 examples/metronome_room.py pattern [OUTDIR]  four bars, bell on one, dry then in the room

The model is fitted dry; the takes are a close mic in Ben's room, 10 x 10 ft
and full of things (Ben). Ours sounds tight beside them (Ben: "Can you add
room back so I can hear it that way?"). The room is MEASURED, not chosen:

  decay  after each tick of the bell-off take the knock is gone in tens of
         ms and what is left is the room. The energy envelope averaged over
         its 35 ticks, per octave, falls at a T60 of 0.26-0.36 s from 500 Hz
         to 8 kHz -- a small, absorbent room. (Its 250 Hz band reads 6.9 s:
         the video game next door, not the room; given 500 Hz's.)
  level  the tail at 20 ms against the tick's peak, per octave (-14 to -22
         dB): each band's share of the tail is set so OUR ticks, convolved,
         read the same at 20 ms.

The tail is noise in each octave decaying at its T60, from the first
reflection (3 ms: a 3 m room) -- the late field roomtail.py also draws as
noise; this room is too small and too cluttered to need its geometry.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, fftconvolve

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

BEN = os.path.expanduser("~/Documents/refs/metronome_ben")
SR = 48000
TICKS = [6.98, 8.52, 10.03, 11.60, 13.10, 14.68, 16.18, 17.75, 19.27, 20.87, 22.37, 23.98, 25.50,
         27.10, 28.62, 30.20, 31.71, 33.28, 34.78, 36.33, 37.84, 39.40, 40.93, 42.47, 43.98, 45.55,
         47.07, 48.62, 50.12, 51.67, 53.18, 54.75, 56.26, 57.84]
OCTAVES = (250, 500, 1000, 2000, 4000, 8000)
FIRST = 0.003


def mono(path):
    sr, a = wavfile.read(path)
    a = a.astype(float)
    if a.dtype != np.float32 and np.abs(a).max() > 2:
        a = a / 32768.0
    return (a.mean(1) if a.ndim > 1 else a), sr


def band(x, lo, sr):
    return sosfiltfilt(butter(4, [lo, min(2 * lo, 0.45 * sr)], "bandpass", fs=sr, output="sos"), x)


def envelope(x, sr, onsets, lo):
    """The octave's energy envelope averaged over the onsets, each aligned on
    its peak, in dB re that peak; 0.9 s."""
    y = band(x, lo, sr)
    env = []
    for t in onsets:
        i = int(t * sr)
        seg = y[max(0, i - int(0.01 * sr)):i + int(1.0 * sr)]
        p = int(np.argmax(np.abs(seg[:int(0.03 * sr)])))
        env.append(seg[p:p + int(0.9 * sr)] ** 2)
    n = min(len(e) for e in env)
    e = np.mean([e[:n] for e in env], axis=0)
    w = int(0.002 * sr)
    e = np.convolve(e, np.ones(w) / w, "same")
    db = 10 * np.log10(e + 1e-20)
    return db - db[:int(0.003 * sr)].max()


def measure():
    """{octave: (T60 s, tail at 20 ms dB re peak)} of the bell-off take."""
    x, sr = mono(os.path.join(BEN, "ben_take2.wav"))
    room = {}
    for lo in OCTAVES:
        db = envelope(x, sr, TICKS, lo)
        t = np.arange(len(db)) / sr
        floor = np.median(db[int(0.75 * sr):])
        at20 = db[int(0.02 * sr)]
        m = (t > 0.02) & (db > floor + 6) & (db < at20)
        t60 = -60.0 / np.polyfit(t[m], db[m], 1)[0] if m.sum() > 200 else None
        room[lo] = (t60, at20)
    if room[250][0] is None or room[250][0] > 1.0:     # the game, not the room:
        room[250] = room[500]                           # its decay and its level
    return room


def tail_ir(room, gains, sr, seconds=1.2, seed=0):
    """Noise per octave at its T60 and gain, from FIRST; a unit direct spike."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    h = np.zeros(n)
    for lo in OCTAVES:
        t60 = room[lo][0]
        nz = band(rng.standard_normal(n), lo, sr)
        nz /= np.sqrt(np.mean(nz ** 2))
        h += gains[lo] * nz * 10 ** (-3.0 * t / t60) * (t >= FIRST)
    h[0] = 1.0
    return h


def ours(key, d):
    import elkit_fit as E
    E.KIT = 56                # the SFX set (elkit_fit's own default is 24, the Electronic)
    x, sr = E.ours(key, d)
    x = np.asarray(x, float)
    return (x.mean(1) if x.ndim > 1 else x), sr


def calibrate(room, dry, sr):
    """Each octave's tail gain so the model's ticks, convolved, read the
    recording's level at 20 ms. The tick's onset is found in the dry render."""
    on = [int(np.argmax(np.abs(dry) > 0.1 * np.abs(dry).max())) / sr]
    gains = {lo: 0.05 for lo in OCTAVES}
    for _ in range(4):
        wet = fftconvolve(dry, tail_ir(room, gains, sr))[:len(dry) + sr]
        for lo in OCTAVES:
            got = envelope(wet, sr, on, lo)[int(0.02 * sr)]
            gains[lo] *= 10 ** ((room[lo][1] - got) / 20.0)
    return gains


def ab(out):
    os.makedirs(out, exist_ok=True)
    room = measure()
    with tempfile.TemporaryDirectory() as d:
        click, sr = ours(45, d)
        bell, _ = ours(46, d)
    gains = calibrate(room, click, sr)
    h = tail_ir(room, gains, sr)
    items = []
    from scipy.signal import resample_poly
    from math import gcd
    rec_t, rsr = mono(os.path.join(BEN, "hits", "metronome_01.wav"))
    rec_b, _ = mono(os.path.join(BEN, "hits", "bell_06.wav"))
    if rsr != sr:                                       # the takes are 48 kHz, the render 44.1
        g = gcd(sr, rsr)
        rec_t, rec_b = (resample_poly(z, sr // g, rsr // g) for z in (rec_t, rec_b))
    for rec, dry, secs in ((rec_t, click, 1.2), (rec_b, bell, 4.0)):
        a = int(np.argmax(np.abs(dry) > 0.01 * np.abs(dry).max()))
        wet = fftconvolve(dry[a:], h)[:int(secs * sr)]
        for z in (rec[:int(secs * sr)], wet):
            z = z / (np.sqrt(np.mean(z ** 2)) + 1e-12) * 0.06
            items += [z, np.zeros(int(0.6 * sr))]
        items.append(np.zeros(int(0.4 * sr)))
    w = np.concatenate(items)
    w = 0.9 * w / np.abs(w).max()
    dry_path = os.path.join(out, "metronome_room.wav")
    wavfile.write(dry_path, sr, (np.stack([w, w], 1) * 32767).astype(np.int16))
    mp3 = os.path.join(out, "metronome_room.mp3")
    subprocess.check_call(["lame", "--quiet", "-V2", dry_path, mp3])
    print("room:", " ".join("%d Hz %.2f s %+.0f dB" % (lo, room[lo][0], room[lo][1]) for lo in OCTAVES))
    print("  -> " + mp3)


def pattern(out, bpm=80.0, bars=4):
    """The bell key on beat one, the click on two to four -- the SFX set
    (46/45) then Standard (34/33) -- dry, as the bank plays, then in Ben's
    room: the tick inside the bell beat should sound as the plain ticks do."""
    import mido
    import blockrender as B
    os.makedirs(out, exist_ok=True)
    os.environ.setdefault("TUNING_REFLECT", "0")
    room = measure()
    chunks = []
    for kit, bell, click in ((56, 46, 45), (0, 34, 33)):
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / bpm), time=0))
        t.append(mido.Message("program_change", channel=9, program=kit, time=0))
        gap = 240
        for b in range(bars * 4):
            n = bell if b % 4 == 0 else click
            t.append(mido.Message("note_on", channel=9, note=n, velocity=100, time=gap))
            t.append(mido.Message("note_off", channel=9, note=n, velocity=0, time=60))
            gap = 480 - 60
        t.append(mido.MetaMessage("end_of_track", time=480 * 4))
        L, R = B.render(m)[:2]
        x = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
        sr = B.SR
        chunks.append(x)
    with tempfile.TemporaryDirectory() as d:
        click, sr = ours(45, d)
    h = tail_ir(room, calibrate(room, click, sr), sr)
    wet = [fftconvolve(x, h)[:len(x)] for x in chunks]
    pk = max(np.abs(np.concatenate(chunks + wet)).max(), 1e-9)
    gap = np.zeros(int(1.0 * sr))
    w = np.concatenate([chunks[0], gap, chunks[1], gap, gap, wet[0], gap, wet[1]]) * (0.9 / pk)
    path = os.path.join(out, "metronome_pattern.wav")
    wavfile.write(path, sr, (np.stack([w, w], 1) * 32767).astype(np.int16))
    mp3 = path[:-4] + ".mp3"
    subprocess.check_call(["lame", "--quiet", "-V2", path, mp3])
    print("  -> " + mp3)


if __name__ == "__main__":
    if sys.argv[1] == "measure":
        for lo, (t60, at20) in measure().items():
            print("%5d Hz  T60 %.2f s  tail at 20 ms %+.1f dB re the tick" % (lo, t60, at20))
    elif sys.argv[1] == "pattern":
        pattern(sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Downloads/metronome_ab"))
    else:
        ab(sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Downloads/metronome_ab"))
