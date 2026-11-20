#!/usr/bin/env python3
"""BEN'S WURLITZER, MEASURED: the survey takes of his c.1968-70 Wurlitzer
console (~/Documents/refs/wurlitzer_ben, SESSION.md says what each holds)
read into numbers -- every tab's harmonics by key, the generator's tuning and
octaves, whether two ranks on one key lock in phase, the sustains' release
decay, the chimes' partials, the Ssh-Boom drum, the vibrato, the four
Spectra-Tone settings and the couplers.

    python3 examples/wurlitzer_survey.py [REFDIR] [--json=OUT.json]

The recordings are Ben's own (his organ, his mic): ours outright. Windows are
the takes' events as found by ear and level (SESSION.md); within a window each
held note is found by its level, so a window may hold fewer notes than keys
when a key was silent.
"""
import json
import os
import sys
import wave

import numpy as np

SR = 48000
REF = os.path.expanduser("~/Documents/refs/wurlitzer_ben")


def load(take, ref):
    w = wave.open(os.path.join(ref, "survey%s.wav" % take))
    return np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2)[:, 0] / 32768.0


def db(v):
    return 20 * np.log10(np.maximum(v, 1e-12))


def runs(x, a, b, rel=22.0, min_len=0.35):
    """the held notes in [a, b): runs of 50 ms frames within REL dB of the window's loudest"""
    hop = SR // 20
    i0, i1 = int(a * SR), int(b * SR)
    r = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(i0, i1 - hop, hop)])
    lv = db(r)
    floor = np.percentile(lv, 10)
    on = (lv > lv.max() - rel) & (lv > floor + 8)      # (a quiet tab: its notes against the room, not the loudest)
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            if (j - i) * hop / SR >= min_len:
                out.append((a + i * hop / SR, a + j * hop / SR))
            i = j
        else:
            i += 1
    return out


def peak_freq(S, f, lo, hi):
    """the strongest bin in [lo, hi], refined by a parabola through its neighbours"""
    i0, i1 = np.searchsorted(f, lo), np.searchsorted(f, hi)
    k = i0 + int(np.argmax(S[i0:i1]))
    if 0 < k < len(S) - 1:
        a, b, c = np.log(S[k - 1] + 1e-20), np.log(S[k] + 1e-20), np.log(S[k + 1] + 1e-20)
        d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        return f[k] + d * (f[1] - f[0]), S[k]
    return f[k], S[k]


def spectrum(seg, f_expect, nh=12):
    """f0 near F_EXPECT (within 5%: the organ sits ~30 cents flat), and
    harmonics 1..NH in dB re the strongest"""
    n = len(seg)
    S = np.abs(np.fft.rfft(seg * np.hanning(n), 4 * n))
    f = np.fft.rfftfreq(4 * n, 1 / SR)
    f0, _ = peak_freq(S, f, f_expect * 0.95, f_expect * 1.05)
    h = []
    for k in range(1, nh + 1):
        if k * f0 > SR / 2 - 200:
            h.append(np.nan)
            continue
        _, a = peak_freq(S, f, k * f0 * 0.99, k * f0 * 1.01)
        h.append(a)
    h = np.array(h)
    return f0, db(h / np.nanmax(h))


def band_env(x, a, b, fc, step=0.01, n=4096):
    """the level at FC (one partial), every STEP s"""
    out = []
    win = np.hanning(n)
    f = np.fft.rfftfreq(4 * n, 1 / SR)
    for t in np.arange(a, b, step):
        s = x[int(t * SR):int(t * SR) + n]
        if len(s) < n:
            break
        S = np.abs(np.fft.rfft(s * win, 4 * n))
        j = np.searchsorted(f, fc)
        out.append(S[j - 6:j + 7].max() * 2 / n)
    return np.arange(len(out)) * step + a, db(np.array(out))


def cents(f, ref):
    return 1200 * np.log2(np.maximum(f, 1e-9) / ref)


C3 = 130.81  # equal temperament, A440 (the organ is ~30 cents under)

# (name, take, window, sounding footage factor vs 8', manual)
TABS = [
    # upper, Solo + Accent on (take 2)
    ("Tibia 16'", "2", (9, 17), 0.5, "upper"), ("Bass Clarinet 16'", "2", (20, 28.5), 0.5, "upper"),
    ("Trombone 16'", "2", (31, 39), 0.5, "upper"), ("Flute 8'", "2", (42, 50), 1, "upper"),
    ("Diapason 8'", "2", (52.5, 61), 1, "upper"), ("String 8'", "2", (63.5, 72), 1, "upper"),
    ("Clarinet 8'", "2", (74.5, 83.5), 1, "upper"), ("Oboe 8'", "2", (86.5, 95.5), 1, "upper"),
    ("Trumpet 8'", "2", (98, 107), 1, "upper"), ("Kinura 8'", "2", (110, 118), 1, "upper"),
    ("Quint 5-1/3'", "2", (120.5, 129.5), 1.5, "upper"), ("Clarinet 4'", "2", (132.5, 142), 2, "upper"),
    # lower, Solo + Lower Keyboard Volume Full (take 8)
    ("Melodia 8' (plain)", "8", (15, 24), 1, "lower"), ("Melodia 8' (Solo)", "8", (27, 37.5), 1, "lower"),
    ("Melodia 8'", "8", (41, 51), 1, "lower"), ("Geigen Diapason 8'", "8", (55, 65), 1, "lower"),
    ("Viole 8'", "8", (69, 79.5), 1, "lower"), ("Lower Trombone 8'", "8", (82, 92.5), 1, "lower"),
    ("Vox Humana 8'", "8", (96.5, 110), 1, "lower"), ("Cornet 8'", "8", (112.5, 124), 1, "lower"),
    ("Lower Quint 5-1/3'", "8", (127, 139), 1.5, "lower"),
]
# pedals: low C, G, C (take 6: Normal and Medium pedal volume; take 7: Bourdon at Full, C G C G C)
PEDALS = [
    ("Bourdon 16' (Normal)", "6", (8, 25.5), 0.25), ("Principal 16' (Normal)", "6", (27.5, 44.5), 0.25),
    ("Pedal Flute 8' (Normal)", "6", (46, 59), 0.5), ("String Bass 8' (Normal)", "6", (61, 73.5), 0.5),
    ("Bourdon 16' (Medium)", "6", (139.5, 152.5), 0.25), ("Principal 16' (Medium)", "6", (153.5, 168), 0.25),
    ("Pedal Flute 8' (Medium)", "6", (169.8, 183), 0.5), ("String Bass 8' (Medium)", "6", (183.8, 197.5), 0.5),
    ("Bourdon 16' (Full)", "7", (5.5, 26.5), 0.25),
]


def tabs_report(xs, out):
    print("== TABS: harmonics 1-12 (dB re strongest), level, f0 and its tuning vs A440 ==")
    rows = []
    for name, take, (a, b), fac, man in TABS + [(n, t, w, f, "pedal") for n, t, w, f in PEDALS]:
        x = xs[take]
        notes = runs(x, a, b)
        for k, (s, e) in enumerate(notes):
            seg = x[int((s + 0.25) * SR):int((e - 0.1) * SR)]
            lvl = db(np.sqrt((seg ** 2).mean()))
            # which key: from the sounding pitch, nearest C or G of the series
            Sq = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
            fq = np.fft.rfftfreq(len(seg), 1 / SR)
            # expected fundamentals for the window's keys
            if man == "pedal":
                keys = [C3 / 4 * fac * 4 * m for m in ((1, 1.5, 2, 3, 4) if take == "7" else (1, 1.5, 2))]
            else:
                keys = [C3 * fac * m for m in (1, 2, 4)]
            # the keys were played in order: as many notes as keys means the k-th is the k-th key;
            # otherwise (a silent key) the expected key whose fundamental, 2nd and 3rd carry most energy
            best, fexp = -1, keys[0]
            if len(notes) == len(keys):
                best, fexp = 0, keys[k] * 0.983
            for kf in (keys if best < 0 else []):
                kf2 = kf * 0.983
                e_ = sum(Sq[max(np.searchsorted(fq, h * kf2) - 3, 0):np.searchsorted(fq, h * kf2) + 4].max()
                         for h in (1, 2, 3))
                if e_ > best:
                    best, fexp = e_, kf2
            f0, h = spectrum(seg, fexp)
            et = 440 * 2 ** (round(12 * np.log2(f0 / 440)) / 12)
            rows.append(dict(tab=name, take=take, t=round(s, 2), f0=round(float(f0), 2),
                             cents_vs_a440=round(float(cents(f0, et)), 1), level_dbfs=round(float(lvl), 1),
                             harmonics_db=[None if np.isnan(v) else round(float(v), 1) for v in h]))
            print("%-24s t%s %6.1fs  f0 %7.2f (%+5.1f c)  %5.1f dBFS  %s" % (
                name, take, s, f0, cents(f0, et), lvl, " ".join("%4.0f" % v if not np.isnan(v) else "   ." for v in h)))
    out["tabs"] = rows
    # THE GENERATOR: the same note name on every tab and octave
    print("\n== THE GENERATOR: every note's f0 folded to the C3 octave (a divider organ gives one value per note name) ==")
    folded = sorted((r["f0"] / 2 ** np.floor(np.log2(r["f0"] / 125.0)), r["tab"], r["f0"]) for r in rows)
    cs = [f for f, _, _ in folded if abs(cents(f, 128.43)) < 50]
    gs = [f for f, _, _ in folded if abs(cents(f, 192.6)) < 50]
    for nm, v in (("C", cs), ("G", gs)):
        if v:
            v = np.array(v)
            print("  %s: %d notes, folded f0 mean %.3f Hz, spread %.2f cents (sd)" % (nm, len(v), v.mean(),
                                                                                     np.std(cents(v, v.mean()))))
            out["generator_" + nm] = dict(n=len(v), mean_hz=round(float(v.mean()), 3),
                                          sd_cents=round(float(np.std(cents(v, v.mean()))), 2))
    return rows


def pairs_report(x, out):
    """Flute 8' + another rank on one key (take 3): a shared generator gives a steady sum; two
    free oscillators beat. The level of each partial over the hold, after its first half second."""
    print("\n== FLUTE 8' PAIRS (C4 held): each partial's level wander over the hold ==")
    res = []
    for a, b in ((16.9, 23.7), (31.1, 39.2), (46.2, 53.5), (58.2, 64.8)):
        line = []
        for fc in (64.2, 128.4, 192.6, 256.8, 385.2, 513.6, 770.4, 1027.2):
            t, e = band_env(x, a + 0.6, b - 0.4, fc, step=0.02, n=8192)
            if e.max() < -75:
                continue
            line.append((fc, float(e.mean()), float(np.percentile(e, 95) - np.percentile(e, 5))))
        res.append(dict(t=a, partials=[dict(hz=fc, level_db=round(m, 1), wander_db=round(w, 2)) for fc, m, w in line]))
        print("  %5.1fs  " % a + "  ".join("%4.0fHz %4.0fdB ±%.1f" % (fc, m, w / 2) for fc, m, w in line))
    out["pairs"] = res


def release(x, a, b, fc):
    """the release of a held note: its partial's level, the plateau, the moment it leaves it, and the
    decay rate (dB/s) fitted from 3 dB down to 8 dB above the floor"""
    t, e = band_env(x, a, b, fc, step=0.005, n=2048)
    k = int(np.argmax(e))
    floor = np.median(np.sort(e)[:max(len(e) // 6, 5)])
    plateau = np.median(e[max(k - 10, 0):k + 10])
    # release onset: the last frame within 3 dB of the plateau after the peak
    above = np.nonzero(e[k:] > plateau - 3)[0]
    r0 = k + int(above[-1]) if len(above) else k
    end = next((i for i in range(r0, len(e)) if e[i] < floor + 8), len(e))
    fit = [(t[i], e[i]) for i in range(r0, end)]
    if len(fit) < 4:
        return None
    tt, ee = np.array(fit).T
    slope = np.polyfit(tt, ee, 1)[0]
    return dict(release_at=round(float(t[r0]), 2), plateau_db=round(float(plateau), 1), floor_db=round(float(floor), 1),
                decay_db_per_s=round(float(slope), 1), t60_s=round(float(-60 / slope), 2) if slope < 0 else None,
                fit_span_db=round(float(ee[0] - ee[-1]), 1))


def sustain_report(x3, x4, out):
    print("\n== SUSTAIN: the release after the key is let go ==")
    res = {}
    for name, x, a, b, fc in (("Upper Short (Flute 8', C4)", x3, 71.5, 80, 256.8),
                              ("Upper Medium (2nd note)", x3, 95.5, 104, 256.8),
                              ("Upper Long", x3, 114, 124, 256.8),
                              ("Pedal On (take 3)", x3, 159.5, 164.4, 128.4),
                              ("Pedal Long (take 3)", x3, 164.3, 172, 128.4),
                              ("Lower Sustain (Melodia C4)", x4, 15, 20.4, 256.8),
                              ("Pedal On (take 4b)", x4, 20.4, 24.3, 128.4),
                              ("Pedal Long (take 4b)", x4, 24.3, 33, 128.4)):
        r = release(x, a, b, fc)
        res[name] = r
        if r:
            print("  %-28s %6.1f dB/s  T60 %5s s  (fitted over %4.1f dB)" % (name, r["decay_db_per_s"], r["t60_s"], r["fit_span_db"]))
        else:
            print("  %-28s (no release found)" % name)
    out["sustain"] = res


def chimes_report(x, out):
    """three chime strikes (take 5): the partials in the first 0.3 s, and each one's decay"""
    print("\n== CHIMES: partials (Hz, dB re strongest) and their decay rates ==")
    res = []
    for a in (13.6, 19.7, 27.0):
        seg = x[int(a * SR):int((a + 0.4) * SR)]
        n = len(seg)
        S = np.abs(np.fft.rfft(seg * np.hanning(n), 8 * n))
        f = np.fft.rfftfreq(8 * n, 1 / SR)
        S[f < 150] = 0
        pk = []
        Sc = S.copy()
        for _ in range(7):
            k = int(np.argmax(Sc))
            pk.append((f[k], S[k]))
            Sc[max(k - 80, 0):k + 80] = 0
        pk.sort()
        top = max(p[1] for p in pk)
        parts = []
        for fc, amp in pk:
            if db(amp / top) < -30:
                continue
            t, e = band_env(x, a, a + 5.5, fc, step=0.02, n=4096)
            k = int(np.argmax(e))
            sel = [(t[i], e[i]) for i in range(k, len(e)) if e[i] > e[k] - 35]
            slope = np.polyfit(*np.array(sel).T, 1)[0] if len(sel) > 5 else np.nan
            parts.append(dict(hz=round(float(fc), 1), db=round(float(db(amp / top)), 1), decay_db_per_s=round(float(slope), 1)))
        res.append(dict(t=a, partials=parts))
        print("  %5.1fs  " % a + "  ".join("%7.1fHz %4.0fdB %5.1fdB/s" % (p["hz"], p["db"], p["decay_db_per_s"]) for p in parts))
    out["chimes"] = res


def drum_report(x, out):
    print("\n== SSH-BOOM: pedal drum and cymbal ==")
    res = []
    for a, kind in ((44.3, "drum"), (47.3, "drum"), (49.9, "drum"), (55.4, "drum"), (64.7, "cymbal")):
        seg = x[int(a * SR):int((a + (0.6 if kind == "drum" else 2.0)) * SR)]
        n = len(seg)
        S = np.abs(np.fft.rfft(seg * np.hanning(n), 4 * n))
        f = np.fft.rfftfreq(4 * n, 1 / SR)
        lo = np.searchsorted(f, 30)
        k = lo + int(np.argmax(S[lo:]))
        cen = float((S * f).sum() / S.sum())
        hop = SR // 200
        env = db(np.array([np.sqrt((seg[i:i + hop] ** 2).mean()) for i in range(0, n - hop, hop)]))
        pk = int(np.argmax(env))
        t20 = next((i - pk for i in range(pk, len(env)) if env[i] < env[pk] - 20), None)
        r = dict(t=a, kind=kind, peak_hz=round(float(f[k]), 1), centroid_hz=round(cen), peak_dbfs=round(float(env[pk]), 1),
                 to_minus20db_ms=None if t20 is None else t20 * 5)
        res.append(r)
        print("  %5.1fs %-6s peak %6.1f Hz  centroid %5d Hz  -20 dB after %s ms" % (a, kind, r["peak_hz"], r["centroid_hz"], r["to_minus20db_ms"]))
    out["ssh_boom"] = res


def modulation(x, a, b, fc):
    """a partial's frequency (cents) and level (dB) over time: rate and peak-to-peak depth of each"""
    n = 4096
    ts, fs, ams = [], [], []
    for t in np.arange(a, b - 0.1, 0.01):
        s = x[int(t * SR):int(t * SR) + n]
        S = np.abs(np.fft.rfft(s * np.hanning(n), 8 * n))
        f = np.fft.rfftfreq(8 * n, 1 / SR)
        fk, ak = peak_freq(S, f, fc * 0.96, fc * 1.04)
        fs.append(fk)
        ams.append(db(ak))
    fs, ams = np.array(fs), np.array(ams)

    def rate(v):
        v = v - v.mean()
        V = np.abs(np.fft.rfft(v * np.hanning(len(v)), 16384))
        fr = np.fft.rfftfreq(16384, 0.01)
        lo = np.searchsorted(fr, 0.4)
        return float(fr[lo + int(np.argmax(V[lo:np.searchsorted(fr, 12)]))])
    c = cents(fs, np.median(fs))
    return dict(fm_hz=round(rate(c), 2), fm_pp_cents=round(float(np.percentile(c, 95) - np.percentile(c, 5)), 1),
                am_hz=round(rate(ams), 2), am_pp_db=round(float(np.percentile(ams, 95) - np.percentile(ams, 5)), 1))


def vibrato_spectra_report(x, out):
    print("\n== VIBRATO (Flute 8', C4) ==")
    v = {}
    for name, a, b in (("slow", 89.5, 94.5), ("fast, depth full", 99.5, 105.0)):
        v[name] = modulation(x, a, b, 256.8)
        print("  %-17s FM %5.2f Hz %5.1f cents p-p   AM %5.2f Hz %4.1f dB p-p" % (name, v[name]["fm_hz"], v[name]["fm_pp_cents"], v[name]["am_hz"], v[name]["am_pp_db"]))
    out["vibrato"] = v
    print("\n== SPECTRA-TONE (lower C4, upper G4 C5 E5): each note's modulation ==")
    st = {}
    for name, a, b in (("Lower", 141.5, 150.5), ("Upper", 157.5, 165.8), ("Chorus", 172.0, 181.0), ("Cathedral", 189.5, 199.5)):
        st[name] = {}
        line = []
        for note, fc in (("C4 lower", 256.8), ("G4", 385.2), ("C5", 513.6), ("E5", 647.0)):
            m = modulation(x, a, b, fc)
            st[name][note] = m
            line.append("%s FM %4.2fHz %4.1fc AM %4.2fHz %4.1fdB" % (note, m["fm_hz"], m["fm_pp_cents"], m["am_hz"], m["am_pp_db"]))
        print("  %-9s " % name + " | ".join(line))
    out["spectra_tone"] = st


def couplers_report(x, out):
    print("\n== COUPLERS (Flute 8' C4 + the coupled octave): the added partial's level re the 8' ==")
    res = {}
    for name, a, b, fc in (("16'", 285.8, 287.9, 128.4), ("4'", 294.0, 296.0, 513.6), ("2'", 301.3, 303.6, 1027.2)):
        seg = x[int(a * SR):int(b * SR)]
        n = len(seg)
        S = np.abs(np.fft.rfft(seg * np.hanning(n), 4 * n))
        f = np.fft.rfftfreq(4 * n, 1 / SR)
        _, a8 = peak_freq(S, f, 250, 263)
        _, ac = peak_freq(S, f, fc * 0.97, fc * 1.03)
        res[name] = round(float(db(ac / a8)), 1)
        print("  %-4s  %+5.1f dB" % (name, res[name]))
    out["couplers"] = res


def main(argv):
    ref = next((a for a in argv if not a.startswith("--")), REF)
    js = next((a.split("=", 1)[1] for a in argv if a.startswith("--json=")), None)
    xs = {t: load(t, ref) for t in ("2", "3", "4b", "5", "6", "7", "8")}
    out = {}
    tabs_report(xs, out)
    pairs_report(xs["3"], out)
    sustain_report(xs["3"], xs["4b"], out)
    chimes_report(xs["5"], out)
    drum_report(xs["5"], out)
    vibrato_spectra_report(xs["5"], out)
    couplers_report(xs["5"], out)
    if js:
        with open(js, "w") as f:
            json.dump(out, f, indent=1)
        print("\n%s written" % js)


if __name__ == "__main__":
    main(sys.argv[1:])
