#!/usr/bin/env python3
"""The siren's ROTOR, measured: how fast air spins it up and how slowly it
coasts down, and how loud it is at each speed.

    python3 -I examples/siren_fit.py track FILE [T0 T1]   pitch and level, every 50 ms
    python3 -I examples/siren_fit.py fit                   the rotor's constants

The model (siren.py, plan stage 3): the rotor's speed w, in units of its top
speed at full pressure, driven by the pressure p (0..1):

    dw/dt = a p (wmax(p) - w) - b w

Held at full pressure it winds up onto a w_inf = a/(a+b) with time constant
1/(a+b); let go (p = 0) it coasts down as exp(-b t). The pitch is holes x w x
the top revolutions, so log-pitch falls at b per second in the coast -- read
straight off the track, whatever the holes.

THE TRACKER is a harmonic sum: for each candidate f0, the summed magnitude of
its first eight harmonics, less the half-way points between them (so the
octave below, whose odd harmonics fall on nothing, does not win). A siren's
series is strong in h2, which is where a plain peak-picker jumps.
"""
import os
import sys

import numpy as np

REF = os.path.expanduser("~/Documents/refs")
FIRE = os.path.join(REF, "freesound/siren/819369__sapperlapje__fire-truck-siren.wav")
WHISTLE = [os.path.join(REF, "vcsl/siren_whistle/Main_SirenWhistle-%s.wav" % n)
           for n in ("002", "005", "008", "009", "010")]


def load(path):
    from scipy.io import wavfile
    sr, x = wavfile.read(path)
    x = np.asarray(x, np.float64)
    if x.ndim > 1:
        x = x.mean(1)
    return x / (np.abs(x).max() + 1e-12), sr


def track(x, sr, fmin=60.0, fmax=2500.0, hop_s=0.05, win_s=0.1):
    """[(t, f0 Hz, level dB)]"""
    n = int(win_s * sr)
    hop = int(hop_s * sr)
    N = 1 << 16
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    cands = fmin * 2 ** (np.arange(0, int(48 * np.log2(fmax / fmin))) / 48.0)
    out = []
    w = np.hanning(n)
    for i in range(0, len(x) - n, hop):
        seg = x[i:i + n] * w
        lvl = 10 * np.log10((seg ** 2).mean() + 1e-20)
        X = np.abs(np.fft.rfft(seg, N))
        idx = lambda f: np.clip(np.round(f / (sr / N)).astype(int), 0, len(X) - 1)
        score = np.zeros(len(cands))
        for h in range(1, 9):
            score += X[idx(cands * h)] - 0.5 * X[idx(cands * (h - 0.5))]
        f0 = cands[int(np.argmax(score))]
        # refine on h1's own peak
        k = idx(np.array([f0]))[0]
        lo, hi = max(1, k - 3), min(len(X) - 2, k + 3)
        k = lo + int(np.argmax(X[lo:hi + 1]))
        a, b, c = np.log(X[k - 1] + 1e-12), np.log(X[k] + 1e-12), np.log(X[k + 1] + 1e-12)
        d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        out.append((i / sr, (k + d) * sr / N, lvl))
    return np.array(out)


def show(path, t0=None, t1=None):
    x, sr = load(path)
    tr = track(x, sr)
    for t, f, l in tr:
        if (t0 is None or t >= t0) and (t1 is None or t <= t1):
            print("  %6.2f s  %7.1f Hz  %6.1f dB" % (t, f, l))


def coast_rate(tr, t0, t1):
    """log-pitch slope (1/s) and level-vs-log-pitch slope (dB per octave) over t0..t1"""
    m = (tr[:, 0] >= t0) & (tr[:, 0] <= t1)
    t, f, l = tr[m, 0], tr[m, 1], tr[m, 2]
    b = -np.polyfit(t, np.log(f), 1)[0]
    s = np.polyfit(np.log2(f), l, 1)[0]
    return b, s


def windup_tau(tr, t0, t1):
    """time constant of log-pitch rising onto its plateau over t0..t1"""
    m = (tr[:, 0] >= t0) & (tr[:, 0] <= t1)
    t, f = tr[m, 0], tr[m, 1]
    finf = np.median(f[-max(3, len(f) // 6):])
    y = np.log(np.maximum(1e-6, 1.0 - f / finf * 0.999))
    ok = f < 0.95 * finf
    return -1.0 / np.polyfit(t[ok], y[ok], 1)[0], finf




def live_take(kit_key=67, hold=5.5, total=20.0, vel=110, program=56, drums=True, bank=0,
              events=()):
    """A siren played on live.py's engine, block by block (its own callback),
    as a player would: note on, held, off; `events` are (t, mido message)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import mido
    import live as LV
    if drums:
        lv = LV.Live(program=program, rate=48000, frames=128, drums=True, verbose=False)
    else:
        lv = LV.Live(program=0, rate=48000, frames=128, verbose=False)
        lv.set_parts([LV.Part(LV.patch_for(program, False, "hybrid440", variation=bank))])
    patch = lv.parts[0].patch
    b = patch.bucket(vel)
    for sp in patch.speeds:
        if (kit_key, b, sp) not in patch.templates:
            t = patch._raw_template(kit_key, patch.bucket_vel(b), sp)
            if t is not None:
                patch.templates[(kit_key, b, sp)] = t
    ch = 9 if drums else 0
    evs = sorted([(0.0, mido.Message("note_on", channel=ch, note=kit_key, velocity=vel)),
                  (hold, mido.Message("note_off", channel=ch, note=kit_key, velocity=0))]
                 + [(t, m) for t, m in events], key=lambda e: e[0])
    out = []
    n = 0
    for i in range(int(total * 48000) // 128):
        while evs and evs[0][0] * 48000 <= n:
            lv.on_midi(evs.pop(0)[1])
        buf, _f = lv.callback(None, 128, None, 0)
        out.append(np.frombuffer(buf, np.float32))
        n += 128
    lv.shutdown()
    y = np.concatenate(out).reshape(-1, 2)
    return y, 48000


# THE A/B, in sections (each a list of events for sfx_variations.midi):
def _ab_sections():
    S = []
    # the fire siren (SFX 67): held as the recording's driver held it, then let
    # coast to silence; then pumped -- pressed, let go, pressed again
    S.append(("fire siren: held 5.5 s, then its coast",
              [(0, "pc", 9, 56, 0), (0.0, "on", 9, 67, 110), (5.5, "off", 9, 67, 0)], 30.0))
    S.append(("fire siren: pumped",
              [(0, "pc", 9, 56, 0)] + sum([[(t, "on", 9, 67, 110), (t + 1.6, "off", 9, 67, 0)]
                                           for t in (0.0, 3.0, 6.0)], []), 20.0))
    hv = [(0, "cc", 0, 0, 5), (0, "pc", 0, 125, 0)]
    S.append(("double siren: C4 held at full air", hv + [(0.0, "on", 0, 60, 127), (3.5, "off", 0, 60, 0)], 4.5))
    S.append(("double siren: the wail (pressed, let go, pressed before it stops)",
              hv + sum([[(t, "on", 0, 60, 127), (t + d, "off", 0, 60, 0)]
                        for t, d in ((0.0, 1.2), (1.8, 0.8), (3.0, 1.5), (5.0, 0.6))], []), 7.0))
    # aftertouch as the air: struck soft, then pressed in
    S.append(("double siren: struck soft, then aftertouch swells the air",
              hv + [(0.0, "on", 0, 60, 60)]
              + [(0.5 + 0.05 * k, "at", 0, min(127, 4 * k), 0) for k in range(33)]
              + [(4.5, "off", 0, 60, 0)], 5.5))
    # the crank: the wheel turned from 0 to the half spacing and back
    S.append(("double siren: the crank (mod wheel) 0 -> top -> 0, both 12-rows",
              hv + [(0.0, "on", 0, 60, 127)]
              + [(1.0 + 0.05 * k, "cc", 0, 1, int(127 * (k / 60.0 if k <= 60 else (120 - k) / 60.0)))
                 for k in range(121)] + [(8.0, "off", 0, 60, 0)], 9.0))
    for name, w in (("lower 12 alone", 0b0000100), ("8 + 12: a fifth", 0b0000101),
                    ("12 + 15: a major third", (0b0000100, 0b1000000)), ("all eight rows", (0x7F, 1))):
        w43, w44 = (w, 0) if isinstance(w, int) else w
        S.append(("double siren stops: " + name,
                  hv + [(0, "cc", 0, 43, w43), (0, "cc", 0, 44, w44), (0.0, "on", 0, 60, 127),
                        (2.5, "off", 0, 60, 0)], 3.2))
    return S


def ab(out):
    import subprocess
    from scipy.io import wavfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sfx_variations as V
    import blockrender as B
    chunks = []
    for name, ev, length in _ab_sections():
        x = V.render(V.midi(ev, length))
        chunks += [x, np.zeros((int(1.0 * B.SR), 2))]
        print("  " + name, flush=True)
    w = np.concatenate(chunks)
    w = 0.9 * w / np.abs(w).max()
    wav = out[:-4] + ".wav"
    wavfile.write(wav, B.SR, (w * 32767).astype(np.int16))
    subprocess.check_call(["lame", "--quiet", "-V2", wav, out])
    print("  -> " + out)


if __name__ == "__main__":
    if sys.argv[1] == "track":
        show(sys.argv[2], *(float(v) for v in sys.argv[3:5]))
    elif sys.argv[1] == "ab":
        ab(sys.argv[2])
