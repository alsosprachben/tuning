"""The controller matrix (ctrlmatrix.py) on one held note, measured and
rendered: a GS mod wheel into LFO1 amplitude depth (40 21 06 = 127), the
wheel swept 0 -> 127 -> 0 over 4 s; the same through GM2's Controller
Destination Setting (F0 7F 7F 09 03 00 01 05 7F); and CC16 into amplitude at
+100 % (40 21 42 = 7F), stepped 0 -> 127 half way through.

    python3 examples/ctrlmatrix_demo.py [OUT]     measure (and write OUT/ctrlmatrix.wav)
"""
import os
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B        # noqa: E402


def _gs(addr, val):
    body = list(addr) + [val]
    return mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12] + body + [(128 - sum(body) % 128) % 128])


def held(setup, ccs, secs=4.0, program=48):
    """A GS file: reset, `setup` messages, one held C4 on part 1 (strings: a
    plain voice -- an organ's CC11 is its stop word, with rows of its own), `ccs` [(s, cc, v)]."""
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(_gs((0x40, 0x00, 0x7F), 0x00))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    for m in setup:
        tr.append(m)
    ev = [(0.25, mido.Message("note_on", channel=0, note=60, velocity=100))]
    ev += [(0.25 + s, mido.Message("control_change", channel=0, control=c, value=v)) for s, c, v in ccs]
    ev.append((0.25 + secs, mido.Message("note_off", channel=0, note=60, velocity=0)))
    ev.sort(key=lambda e: e[0])
    now = 0
    for t, m in ev:
        tick = int(round(t * 960))
        tr.append(m.copy(time=tick - now))
        now = tick
    return mf


def sweep():
    return [(k * 0.04, 1, int(round(127 * (1 - abs(k * 0.04 - 2.0) / 2.0)))) for k in range(101)]


def depth_at(x, sr, t0, t1, hz=B.TREMOLO_MATRIX_HZ):
    """The tremolo's depth in [t0, t1): the envelope's swing at its rate."""
    seg = x[int(t0 * sr):int(t1 * sr)]
    n = int(0.005 * sr)
    e = np.sqrt(np.convolve(seg * seg, np.ones(n) / n, "same"))[::n]
    t = np.arange(len(e)) * 0.005
    c, s = np.cos(2 * np.pi * hz * t), np.sin(2 * np.pi * hz * t)
    a = 2 * np.hypot(np.mean((e - e.mean()) * c), np.mean((e - e.mean()) * s))
    return a / max(e.mean(), 1e-12)


def rms_db(x, sr, t0, t1):
    seg = x[int(t0 * sr):int(t1 * sr)]
    return 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12)


def pitch_hz(x, sr, t0, t1, lo=150.0, hi=600.0):
    """The strongest frequency in [t0, t1), lo-hi Hz, parabolically refined."""
    seg = x[int(t0 * sr):int(t1 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 18))
    f = np.fft.rfftfreq(1 << 18, 1.0 / sr)
    b = np.flatnonzero((f > lo) & (f < hi))
    k = b[np.argmax(X[b])]
    a, m, c = np.log(X[k - 1:k + 2] + 1e-20)
    return f[k] + 0.5 * (a - c) / (a - 2 * m + c) * (f[1] - f[0])


def vibrato_cents(x, sr, t0, t1, f0):
    """The pitch's spread (cents rms) over 40 ms frames in [t0, t1)."""
    fs = [pitch_hz(x, sr, t, t + 0.08, f0 * 0.9, f0 * 1.1) for t in np.arange(t0, t1 - 0.08, 0.04)]
    return float(np.std(1200 * np.log2(np.array(fs) / np.mean(fs))))


def centroid(x, sr, t0, t1):
    seg = x[int(t0 * sr):int(t1 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1.0 / sr)
    return float((f * X).sum() / X.sum())


def two_notes(setup, ccs, program=81):
    """Two struck notes on part 1 (a saw lead: a filter that answers), the
    second after `ccs`."""
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(_gs((0x40, 0x00, 0x7F), 0x00))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    for m in setup:
        tr.append(m)
    ev = [(0.25, mido.Message("note_on", channel=0, note=60, velocity=100)),
          (1.0, mido.Message("note_off", channel=0, note=60, velocity=0)),
          (2.25, mido.Message("note_on", channel=0, note=60, velocity=100)),
          (3.0, mido.Message("note_off", channel=0, note=60, velocity=0))]
    ev += [(s, mido.Message("control_change", channel=0, control=c, value=v)) for s, c, v in ccs]
    ev.sort(key=lambda e: e[0])
    now = 0
    for t, m in ev:
        tick = int(round(t * 960))
        tr.append(m.copy(time=tick - now))
        now = tick
    return mf


def with_pressure(mf, at):
    """mf with channel pressure events [(s, v)] on part 1."""
    tr = mf.tracks[0]
    ev, t = [], 0
    for m in tr:
        t += m.time
        ev.append((t, m))
    ev += [(int(round((0.25 + s) * 960)), mido.Message("aftertouch", channel=0, value=v)) for s, v in at]
    ev.sort(key=lambda e: e[0])
    tr.clear()
    now = 0
    for tk, m in ev:
        tr.append(m.copy(time=tk - now))
        now = tk
    return mf


def phase2():
    """The matrix's other destinations, measured."""
    sr = B.SR
    out = {}
    # GM2 channel pressure -> pitch +2 semitones (09 01 0n 00 42)
    mf = with_pressure(held([mido.Message("sysex", data=[0x7F, 0x7F, 0x09, 0x01, 0x00, 0x00, 0x42])], []),
                       [(0.0, 0), (2.0, 127)])
    L, R = B.render(mf)[:2]
    x = np.asarray(L, float) + np.asarray(R, float)
    f1, f2 = pitch_hz(x, sr, 1.0, 2.1), pitch_hz(x, sr, 2.6, 4.0)
    out["pitch"] = 1200 * np.log2(f2 / f1)
    print("pitch: GM2 channel pressure 0 -> 127, routed +2 semitones: %+.0f cents (+200 wanted)" % out["pitch"])
    # GS CAf -> LFO1 pitch depth (40 21 24 = 0x10: 76 cents)
    mf = with_pressure(held([_gs((0x40, 0x21, 0x24), 0x10)], [], program=73), [(0.0, 0), (2.0, 127)])
    L, R = B.render(mf)[:2]
    x = np.asarray(L, float) + np.asarray(R, float)
    print("vibrato: GS aftertouch -> LFO1 pitch depth: %.1f cents rms before, %.1f after"
          % (vibrato_cents(x, sr, 1.0, 2.2, 261.6), vibrato_cents(x, sr, 2.6, 4.0, 261.6)))
    # GS CC1 (CC16) -> TVF cutoff +4800 cents (40 21 41 = 0x60)
    mf = two_notes([_gs((0x40, 0x21, 0x41), 0x60)], [(1.5, 16, 127)])
    L, R = B.render(mf)[:2]
    x = np.asarray(L, float) + np.asarray(R, float)
    print("cutoff: GS CC16 -> TVF cutoff +4800 cents, a note before and after: centroid %.0f Hz, %.0f Hz"
          % (centroid(x, sr, 0.3, 0.9), centroid(x, sr, 2.3, 2.9)))
    # the church organ: CC16 -> amplitude +100 %, the wheel -> its tremolo
    mf = held([_gs((0x40, 0x21, 0x42), 0x7F)], [(0.0, 16, 0), (2.0, 16, 127)], program=19)
    L, R = B.render(mf)[:2]
    x = np.asarray(L, float) + np.asarray(R, float)
    print("organ amplitude: %.1f dB before, %.1f after (+6.0 wanted)" % (rms_db(x, sr, 1.25, 2.15), rms_db(x, sr, 2.6, 4.0)))
    mf = held([_gs((0x40, 0x21, 0x06), 0x7F)], sweep(), program=19)
    L, R = B.render(mf)[:2]
    x = np.asarray(L, float) + np.asarray(R, float)
    print("organ tremolo:  " + "  ".join("%.2f s %.2f" % (t, depth_at(x, sr, t, t + 0.5)) for t in (0.35, 2.0, 3.75)))


def main(argv):
    if "--phase2" in argv:
        phase2()
        return 0
    sr = B.SR
    gs = held([_gs((0x40, 0x21, 0x06), 0x7F)], sweep())
    gm2 = held([mido.Message("sysex", data=[0x7F, 0x7F, 0x09, 0x03, 0x00, 0x01, 0x05, 0x7F])], sweep())
    amp = held([_gs((0x40, 0x21, 0x42), 0x7F)], [(0.0, 16, 0), (2.0, 16, 127)])
    plain = held([], sweep())
    out = {}
    for name, mf in (("gs", gs), ("gm2", gm2), ("amp", amp), ("plain", plain)):
        L, R = B.render(mf)[:2]
        out[name] = np.asarray(L, float) + np.asarray(R, float)
    print("tremolo depth (wheel 0 at 0.25 s, 127 at 2.25 s, 0 again at 4.25 s):")
    for name in ("gs", "gm2", "plain"):
        print("  %-5s" % name + "  ".join("%.2f s %.2f" % (t, depth_at(out[name], sr, t, t + 0.5))
                                        for t in (0.35, 1.0, 2.0, 3.0, 3.75)))
    print("amplitude: CC16 0 -> 127 at 2.25 s, routed +100 %%: %.1f dB before, %.1f after (+6.0 wanted)"
          % (rms_db(out["amp"], sr, 1.25, 2.15), rms_db(out["amp"], sr, 2.6, 4.0)))
    if len(argv) > 1:
        os.makedirs(argv[1], exist_ok=True)
        gap = np.zeros(int(0.5 * sr))
        y = np.concatenate([out["plain"], gap, out["gs"], gap, out["amp"]])
        y *= 10 ** (-1 / 20.0) / np.abs(y).max()
        f = os.path.join(argv[1], "ctrlmatrix.wav")
        B.write_wav(f, y, y)
        print("  " + f + "  (no routing, the wheel into tremolo, CC16 into amplitude)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
