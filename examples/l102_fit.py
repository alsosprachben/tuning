#!/usr/bin/env python3
"""The tonewheel's drawbar LEVELS from a recording of each drawbar alone.

    python3 examples/l102_fit.py measure
    python3 examples/l102_fit.py fit          prints the stop_ranks gains to write
    python3 examples/l102_fit.py ab OUT.mp3   GM 16 before (the asserted gains) / after

Peter Corbett's Hammond L102 (Pianobook; ~/Documents/refs/hammond_l102,
sources.md): a 1960s spinet sampled dry, every upper drawbar ALONE
(Samples/Dbar1..9 = 16' .. 1', four round robins), its own speaker close-
miked. The pack we fitted the drawbars on (hammondman's, drawbar_fit.py)
never pulled the 16', 5 1/3' or 1 3/5', so their levels were asserted.

THE SAME WHEEL, NOT THE SAME KEY. A drawbar's level at a key is its gain
times its wheel's output times the speaker and the mic at its frequency;
compared with the 8' at the same key, the speaker and mic differ (another
frequency). Compared with the 8' at the key whose 8' IS that wheel -- the 16'
at key K with the 8' at K-12, the 5 1/3' with K+7 (a tonewheel fifth is
equal-tempered), the 4' with K+12 ... -- the wheel, its frequency, the speaker
and the mic are all the same, and the difference is the drawbar's gain alone.
Ours is read the same way, each drawbar rendered alone (drawbar_fit.render,
no Leslie: the L102 is dry), and the two compared.

The file names sit an octave under the 8' pitch: key K's 8' sounds at MIDI
K+12 (measured: the 16' at 261.8 Hz on "key 60").
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import drawbar_fit as DF  # noqa: E402
import tonelib as T  # noqa: E402

REF = os.path.expanduser("~/Documents/refs/hammond_l102/x/Hammond L102/Samples")
BARS = DF.BARS
SHIFT = (-12, 7, 0, 12, 19, 24, 28, 31, 36)      # the key whose 8' is this bar's wheel
KEYS = range(41, 85, 3)
FMAX = 4500.0                                     # under the foldback and the 1''s Nyquist edge


def rec_level(bar, key):
    """dB at the bar's frequency, the mean of its round robins (power)."""
    from scipy.io import wavfile
    ps = sorted(glob.glob(os.path.join(REF, "Dbar%d" % (bar + 1), "Dbar%d_%d_*.wav" % (bar + 1, key))))
    if not ps:
        return np.nan
    f = 440.0 * 2 ** ((key + 12 - 69) / 12.0) * T.TonewheelProperties.stop_ranks[bar][1]
    if f > FMAX:
        return np.nan
    acc = []
    for p in ps:
        sr, x = wavfile.read(p)
        x = x.astype(float)
        x = x.mean(1) if x.ndim > 1 else x
        seg = x[int(0.03 * sr):]
        N = 1 << 18
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
        fr = np.fft.rfftfreq(N, 1.0 / sr)
        b = np.abs(fr - f) < max(4.0, 0.02 * f)
        acc.append(X[b].max())
    return 10 * np.log10(np.mean(acc) + 1e-30)


_ours = {}


def our_level(bar, key):
    """Ours, this bar alone, at its own frequency (drawbar_fit's reader)."""
    k = (bar, key)
    if k not in _ours:
        mkey = key + 12
        f0 = 440.0 * 2 ** ((mkey - 69) / 12.0)
        if f0 * T.TonewheelProperties.stop_ranks[bar][1] > FMAX:
            _ours[k] = np.nan
        else:
            y, sr = DF.render(mkey, 0.6, leslie=False, stops=1 << bar)
            _ours[k] = DF.levels(y, sr, f0, 0.05, 0.5)[bar]
    return _ours[k]


def same_wheel(level):
    """{bar: [(key, level(bar, key) - level(8', key + shift))]}"""
    out = {}
    for i in range(len(BARS)):
        rows = []
        for key in KEYS:
            a, b = level(i, key), level(2, key + SHIFT[i])
            if np.isfinite(a) and np.isfinite(b):
                rows.append((key, a - b))
        out[i] = rows
    return out


# the three gains before the L102 (asserted), for the A/B
BEFORE = {0: 1.00, 1: 0.85, 6: 0.52}
REGS = (("16' + 8'", 0b000000101), ("888 (16' 5-1/3' 8')", 0b000000111),
        ("8' + 1-3/5'", 0b001000100), ("all nine", 0b111111111))


def phrase(B, mask):
    """GM 16 as it plays (the rotor on chorale), the registration on CC11 (the
    low seven drawbars) and CC43 (the high two): a held C major, then a line."""
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=16, time=0))
    t.append(mido.Message("control_change", channel=0, control=11, value=mask & 0x7F, time=0))
    t.append(mido.Message("control_change", channel=0, control=43, value=(mask >> 7) & 0x7F, time=0))
    ev = [(0, 960 * 2, n) for n in (48, 60, 64, 67)]
    t0 = 960 * 2
    for k, n in enumerate((72, 71, 69, 67, 69, 72, 76, 74)):
        ev.append((t0 + k * 240, t0 + k * 240 + 220, n))
    ev.append((t0 + 8 * 240, t0 + 8 * 240 + 960, 72))
    ev.append((t0 + 8 * 240, t0 + 8 * 240 + 960, 60))
    msgs = sorted([(a, "on", n) for a, _, n in ev] + [(b_, "off", n) for _, b_, n in ev], key=lambda r: (r[0], r[1] == "on"))
    last = 0
    for at, kind, n in msgs:
        t.append(mido.Message("note_on" if kind == "on" else "note_off", channel=0, note=n,
                              velocity=96 if kind == "on" else 0, time=at - last))
        last = at
    t.append(mido.MetaMessage("end_of_track", time=960))
    L, R = B.render(m)[:2]
    return np.stack([np.asarray(L, float), np.asarray(R, float)], 1), B.SR


def ab(out):
    import subprocess
    import blockrender as B
    from scipy.io import wavfile
    after = list(T.TonewheelProperties.stop_ranks)
    before = [(r[0], r[1], BEFORE.get(i, r[2])) + tuple(r[3:]) for i, r in enumerate(after)]
    chunks = []
    gap = None
    for name, mask in REGS:
        pair = []
        for ranks in (before, after):
            T.TonewheelProperties.stop_ranks = ranks
            x, sr = phrase(B, mask)
            pair.append(x)
        T.TonewheelProperties.stop_ranks = after
        pk = max(np.abs(p_).max() for p_ in pair)
        gap = np.zeros((int(0.8 * sr), 2))
        chunks += [pair[0] / pk, gap, pair[1] / pk, gap, gap]
        print("  %s" % name, flush=True)
    w = 0.9 * np.concatenate(chunks)
    wav = out[:-4] + ".wav"
    wavfile.write(wav, sr, (w * 32767).astype(np.int16))
    subprocess.check_call(["lame", "--quiet", "-V2", wav, out])
    print("  -> " + out)


def main(argv):
    if argv[1:2] == ["ab"]:
        return ab(argv[2])
    rec = same_wheel(rec_level)
    print("  the drawbar re the 8' on the same wheel, dB (median over keys, and its spread)")
    if argv[1:2] == ["measure"]:
        for i, b in enumerate(BARS):
            d = np.array([v for _, v in rec[i]])
            if len(d):
                print("    %-6s recorded %+6.1f  (iq %.1f, %d keys)" % (b, np.median(d), np.subtract(*np.percentile(d, [75, 25])), len(d)))
        return 0
    ours = same_wheel(our_level)
    print("    bar     recorded   ours   -> gain x   stop_ranks now -> fitted")
    for i, b in enumerate(BARS):
        dr = dict(rec[i])
        do = dict(ours[i])
        ks = sorted(set(dr) & set(do))
        if not ks:
            print("    %-6s no common keys" % b)
            continue
        r = np.median([dr[k] for k in ks])
        o = np.median([do[k] for k in ks])
        g = 10 ** ((r - o) / 20.0)
        amp = T.TonewheelProperties.stop_ranks[i][2]
        print("    %-6s %+7.1f  %+7.1f   %+5.1f dB    %.2f -> %.2f   (%d keys, rec iq %.1f)"
              % (b, r, o, r - o, amp, amp * g, len(ks),
                 np.subtract(*np.percentile([dr[k] for k in ks], [75, 25]))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
