#!/usr/bin/env python3
"""A/B for a harpsichord stop: the recording's notes, then the model's.

    harpsi_ab.py ab STOP_DIR OUT.wav [--stop=lute] [--note-s=1.6]  recording, then model, key by key
    harpsi_ab.py notes STOP_DIR OUT.wav [--stop=lute]   the recorded stop, key by key
    harpsi_ab.py model OUT.wav [--stop=lute]            the model, the same keys
    harpsi_ab.py piece MID OUT.wav [--stop=lute] [--secs=30]

`model` and `piece` render with the tonelib this script is run from, so run
them from a worktree at HEAD for "before" and from the working tree for
"after". Each note is peak-normalised alike in all takes: the comparison is
colour and decay, not level (the stops' balance is stop_ranks' gains).
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import voicefit as V
from roomtail import write_wav

BITS = {"8": 0, "8-upper": 1, "4": 2, "lute": 3}


def mask(stop):
    """The stop word for STOP, or several joined by + (8+8-upper: both 8's)."""
    return sum(1 << BITS[s] for s in stop.split("+"))
KEYS = (36, 43, 48, 55, 60, 67, 72, 79, 84)
NOTE_S, GAP_S, SR = 1.6, 0.35, 48000


def fit_note(x, sr):
    from scipy.signal import resample_poly
    if sr != SR:
        x = resample_poly(x, SR, sr)
    i = max(0, V.onset(x, SR) - int(0.01 * SR))
    y = x[i:i + int(NOTE_S * SR)]
    y = np.pad(y, (0, int(NOTE_S * SR) - len(y)))
    f = int(0.08 * SR)
    y[-f:] *= np.linspace(1, 0, f)
    return 0.5 * y / max(np.abs(y).max(), 1e-12)


def join(notes):
    gap = np.zeros(int(GAP_S * SR))
    x = np.concatenate([np.concatenate([n, gap]) for n in notes])
    return np.stack([x, x], 1)


def recorded(stop_dir):
    """KEYS from the set, by sounding pitch (labels may sit an octave off)."""
    files = {}
    for p in glob.glob(os.path.join(stop_dir, "*.wav")):
        n = V.note_of(p)
        if n is not None:
            files[n] = p
    # the set's octave, as harpsi_fit.pairs finds it
    offs = []
    for n, p in files.items():
        x, sr = V.mono(p)
        f = V.detect_f0(V.steady(x, sr), sr)
        if f and np.isfinite(f) and f > 0:
            offs.append(round(np.log2(f / (440.0 * 2 ** ((n - 69) / 12.0)))))
    shift = 12 * int(np.median(offs))
    out = []
    for k in KEYS:
        p = files.get(k - shift)
        if p is None:                   # the nearest recorded key
            near = min(files, key=lambda n: abs(n + shift - k))
            p = files[near]
        x, sr = V.mono(p)
        out.append(fit_note(x, sr))
    return out


def render_mid(m):
    import blockrender as B
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


def model(stop):
    import mido
    out = []
    for k in KEYS:
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
        t.append(mido.Message("program_change", channel=0, program=6, time=0))
        t.append(mido.Message("control_change", channel=0, control=11, value=mask(stop), time=0))
        t.append(mido.Message("note_on", channel=0, note=k, velocity=100, time=10))
        t.append(mido.Message("note_off", channel=0, note=k, velocity=0, time=int(NOTE_S * 960)))
        x, sr = render_mid(m)
        out.append(fit_note(x, sr))
    return out


def piece(path, stop, secs):
    """The file as written, every channel the harpsichord with only STOP
    drawn, cut at SECS."""
    import mido
    src = mido.MidiFile(path)
    m = mido.MidiFile(type=src.type, ticks_per_beat=src.ticks_per_beat)
    chans = set()
    for tr in src.tracks:
        for msg in tr:
            if hasattr(msg, "channel"):
                chans.add(msg.channel)
    for i, tr in enumerate(src.tracks):
        nt = mido.MidiTrack()
        if i == 0:
            for c in sorted(chans - {9}):
                nt.append(mido.Message("program_change", channel=c, program=6, time=0))
                nt.append(mido.Message("control_change", channel=c, control=11,
                                       value=mask(stop), time=0))
        carry = 0
        for msg in tr:
            # the file's own program and CC11 would undo the registration
            if msg.type == "program_change" or (msg.type == "control_change" and msg.control in (11, 43)):
                carry += msg.time
                continue
            nt.append(msg.copy(time=msg.time + carry))
            carry = 0
        m.tracks.append(nt)
    x, sr = render_mid(m)
    x = x[:int(secs * sr)]
    f = int(0.5 * sr)
    x[-f:] *= np.linspace(1, 0, f)
    x = 0.5 * x / max(np.abs(x).max(), 1e-12)
    return np.stack([x, x], 1), sr


def main(argv):
    global NOTE_S
    opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    args = [a for a in argv[1:] if not a.startswith("--")]
    stop = opts.get("--stop", "lute")
    NOTE_S = float(opts.get("--note-s", NOTE_S))
    if args and args[0] == "ab":
        # NOTE BY NOTE: each key's recording, then the model's, then a rest
        # (Ben: "recording versus rendered, back to back, note by note")
        rest = np.zeros(int(0.6 * SR))
        x = np.concatenate([np.concatenate([r, np.zeros(int(GAP_S * SR)), m, rest])
                            for r, m in zip(recorded(args[1]), model(stop))])
        write_wav(args[2], np.stack([x, x], 1), SR)
    elif args and args[0] == "notes":
        write_wav(args[2], join(recorded(args[1])), SR)
    elif args and args[0] == "model":
        write_wav(args[1], join(model(stop)), SR)
    elif args and args[0] == "piece":
        x, sr = piece(args[1], stop, float(opts.get("--secs", 30)))
        write_wav(args[2], x, sr)
    else:
        print(__doc__.strip())
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
