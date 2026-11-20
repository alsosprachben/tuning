#!/usr/bin/env python3
"""THE DIVIDER ORGAN'S TABS, READ OFF BEN'S WURLITZER (tonelib
DividerOrganProperties): for each tab, its harmonic series at the three keys it
was recorded on (C3, C4, C5: mode_gains_points at the SOUNDING pitch), all on
one scale -- the Flute 8' at C4 -- so the tabs' levels against each other and
up the keyboard are the organ's own; and each note's onset (attack time, the
key click's burst) and its release with no sustain drawn.

    python3 examples/wurlitzer_fit.py [REFDIR] [--json=OUT] [--py]

--py prints the tables as tonelib wants them. The takes (Ben's own organ and
microphone: ours) are in ~/Documents/refs/wurlitzer_ben; SESSION.md and
examples/wurlitzer_survey.py say what each holds. The upper tabs are take 2's
(every Solo and the Accent on: level boosts only, +5 dB, the tone unchanged --
take 1 against take 2), so the quiet reeds stand clear of the room.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wurlitzer_survey as WS        # noqa: E402

SR = WS.SR
NH = 32                 # harmonics read (or to 12 kHz, whichever is lower)
FLOOR_DB = 8.0          # a harmonic under the room's floor by less than this is not read: 0

# (tab, take, window, footage factor vs 8') -- the upper tabs a 60's Organ draws on
UPPER = [t for t in WS.TABS if t[4] == "upper"]


def table(seg, f0):
    """harmonics 1..NH (linear amplitude, a sine of peak 1 reads 1), each against the room's floor
    beside it: a harmonic not FLOOR_DB clear of it reads 0"""
    n = len(seg)
    w = np.hanning(n)
    S = np.abs(np.fft.rfft(seg * w, 4 * n)) * 2 / w.sum()
    f = np.fft.rfftfreq(4 * n, 1 / SR)
    out = []
    for k in range(1, NH + 1):
        fk = k * f0
        if fk > 12000:
            out.append(0.0)
            continue
        _, a = WS.peak_freq(S, f, fk * 0.99, fk * 1.01)
        # the floor: the median between this harmonic and its neighbours
        lo, hi = np.searchsorted(f, fk + 0.25 * f0), np.searchsorted(f, fk + 0.75 * f0)
        fl = np.median(S[lo:hi]) if hi > lo else 0.0
        out.append(float(a) if WS.db(a) - WS.db(fl) > FLOOR_DB else 0.0)
    return out


def onset(x, s, f0):
    """the note's start: the rise of its fundamental's band (10 -> 90 % of the held level, ms), and
    the key click: the energy over 4 kHz in the first 15 ms against the held note's over 4 kHz (dB)"""
    t, e = WS.band_env(x, max(s - 0.15, 0), s + 0.4, f0, step=0.001, n=1024)
    held = np.median(e[-100:])
    lin = 10 ** ((e - held) / 20)
    i10 = next((i for i in range(len(lin)) if lin[i] > 0.1), None)
    i90 = next((i for i in range(len(lin)) if lin[i] > 0.9), None)
    rise = (i90 - i10) if (i10 is not None and i90 is not None) else None
    t0 = t[i10] if i10 is not None else s
    N = int(0.8 * SR)
    i0 = int((t0 - 0.2) * SR)
    X = np.fft.rfft(x[i0:i0 + N], N)
    fx = np.fft.rfftfreq(N, 1 / SR)
    X[fx < 4000] = 0
    hp = np.fft.irfft(X, N)
    burst = hp[int(0.2 * SR):int(0.215 * SR)]
    steady = hp[int(0.45 * SR):int(0.75 * SR)]
    click = WS.db(np.sqrt((burst ** 2).mean())) - WS.db(np.sqrt((steady ** 2).mean()))
    return rise, float(click)


def main(argv):
    ref = next((a for a in argv if not a.startswith("--")), WS.REF)
    js = next((a.split("=", 1)[1] for a in argv if a.startswith("--json=")), None)
    x2 = WS.load("2", ref)
    rows = {}
    for name, take, (a, b), fac, man in UPPER:
        notes = WS.runs(x2, a, b)
        keys = [WS.C3 * fac * m * 0.983 for m in (1, 2, 4)]
        if len(notes) < 3:          # (a silent key: the String's C3) -- the lowest keys are the missing ones
            print("%s: %d notes, not 3: taken as the top %d keys" % (name, len(notes), len(notes)))
            keys = keys[3 - len(notes):]
        got = []
        for k, (s, e) in enumerate(notes):
            seg = x2[int((s + 0.3) * SR):int((e - 0.12) * SR)]
            f0, _ = WS.spectrum(seg, keys[k])
            tb = table(seg, f0)
            rise, click = onset(x2, s, f0)
            # the release, sustain off: the fundamental's fall after the key
            rel = WS.release(x2, s, e + 1.0, f0)
            got.append(dict(t=round(s, 2), f0=round(float(f0), 2), table=tb, rise_ms=rise,
                            click_db=round(click, 1), release=rel))
        rows[name] = got
    # ONE SCALE: the Flute 8' at C4 -- its held amplitude (the root of its table's power)
    ref_pow = np.sqrt(sum(a * a for a in rows["Flute 8'"][1]["table"]))
    print("== the tabs on one scale (Flute 8' at C4 = 0 dB): level, rise, click, release ==")
    for name, got in rows.items():
        for g in got:
            p = np.sqrt(sum(a * a for a in g["table"]))
            g["level_db"] = round(float(WS.db(p / ref_pow)), 1)
            r = g["release"] or {}
            print("%-18s %7.2f Hz  %+6.1f dB  rise %4s ms  click %+5.1f dB  release %s dB/s" % (
                name, g["f0"], g["level_db"], g["rise_ms"], g["click_db"], r.get("decay_db_per_s")))
    if js:
        with open(js, "w") as fh:
            json.dump(rows, fh, indent=1)
    if "--py" in argv:
        print("\n# --- tonelib: each tab's mode_gains_points (sounding Hz, gains on the Flute 8' C4 scale) ---")
        for name, got in rows.items():
            print("# %s" % name)
            print("    mode_gains_points = (")
            for g in got:
                vals = [a / ref_pow for a in g["table"]]
                while vals and vals[-1] == 0.0:
                    vals.pop()
                print("        (%.2f, (%s))," % (g["f0"], ", ".join("%.5f" % v for v in vals)))
            print("    )")


if __name__ == "__main__":
    main(sys.argv[1:])
