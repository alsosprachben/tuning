#!/usr/bin/env python3
"""Fit the sung voices (GM 52 Choir Aahs, GM 53 Voice Oohs) to VocalSet's long
tones (CC BY 4.0, measured only; ~/Documents/refs/vocalset, sources.md).

    python3 -I examples/choir_fit.py survey      each take's pitch, vibrato, level
    python3 -I examples/choir_fit.py env         the vowel's envelope by voice type,
                                                 recorded against ours

VocalSet: twenty conservatory singers (nine women, eleven men), each holding a
note on each vowel straight, forte, pp and messa di voce. "a" is GM 52's "ah",
"u" is GM 53's "oo". The readme names every singer's voice type, which is what
VOICE_BODIES claims to know -- so each body's formants can be checked against
the singers who are that body, not a pitch's guess at them.

A HELD NOTE SAMPLES THE TRACT ONLY AT ITS HARMONICS, and a soprano's are
hundreds of Hz apart. The vibrato is what fills the gaps: each harmonic sweeps
+/- its depth across the resonance, so every frame's harmonics are a new set of
samples of one fixed filter. Pooled over the take, and over the singers of one
voice type (who sing different notes), they draw the envelope.
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import voicefit as V

REFS = os.path.expanduser("~/Documents/refs/vocalset/FULL")
# readme-anon.txt's voice types; "(?)" there is kept as a note, not a guess
TYPES = {"f1": "soprano", "f2": "soprano", "f3": "soprano", "f4": "soprano",
         "f5": "mezzo", "f6": "soprano", "f7": "soprano", "f8": "mezzo",
         "f9": "soprano", "m1": "baritone", "m2": "tenor", "m3": "tenor",
         "m4": "bass", "m5": "baritone", "m6": "baritone", "m7": "tenor",
         "m8": "bass", "m9": "countertenor", "m10": "bass", "m11": "tenor"}
UNSURE = {"m4", "m7"}            # readme: bass(?), tenor(?)
TECHS = ("straight", "forte", "pp", "messa")
FR, HOP = 4096, 1024


def takes():
    for p in sorted(glob.glob(os.path.join(REFS, "*", "long_tones", "*", "*_long_*_[au].wav"))):
        b = os.path.basename(p)[:-4].split("_")
        if b[2] in TECHS:
            yield p, b[0], b[2], b[3]


def _hs(X, sr, N, c):
    """Harmonic sum: log h1..h6 at each candidate pitch c."""
    L = np.log(X + 1e-9)
    L -= L.mean()
    return sum(L[np.minimum((k * c * N / sr).astype(int), len(L) - 1)] for k in range(1, 7))


def notes(x, sr):
    """A long-tone take is SEVERAL notes, rising -- sometimes each its own
    breath (m2's straight "a": ~125, ~253, ~335 Hz), sometimes legato with no
    gap at all (f2's pp "u": ~277, ~565, ~760). So notes are found by PITCH:
    a frame's pitch counts where autocorrelation and the harmonic sum agree
    within 50 cents (each alone slips an octave: autocorrelation up on a loud
    top note, the harmonic sum down on a quiet one), within 40 dB of the
    take's loudest; a note is a run whose running-median pitch stays within
    150 cents of the run's start, at least 1.2 s, trimmed 0.3 s each end for
    the scoop and the release. Returns [(a, b, f0)]."""
    N = 1 << 15
    c = np.arange(70.0, 1200.0, 0.5)
    pk = np.abs(x).max()
    fr = []
    for i in range(0, len(x) - FR, HOP):
        seg = x[i:i + FR]
        r = np.sqrt(np.mean(seg * seg))
        if r < pk * 10 ** (-40 / 20.0):
            fr.append(np.nan); continue
        ac = V.detect_f0(seg, sr, 70.0, 1400.0)
        hs = c[int(np.argmax(_hs(np.abs(np.fft.rfft(seg * np.hanning(FR), N)), sr, N, c)))]
        fr.append(hs if ac and abs(1200 * np.log2(ac / hs)) < 50 else np.nan)
    st = 12 * np.log2(np.asarray(fr) / 440.0)
    w = max(3, int(0.3 * sr / HOP)) | 1
    med = np.array([np.nanmedian(st[max(0, i - w // 2):i + w // 2 + 1])
                    if np.isfinite(st[max(0, i - w // 2):i + w // 2 + 1]).sum() > w // 2 else np.nan
                    for i in range(len(st))])
    out, i, n = [], 0, len(med)
    while i < n:
        if not np.isfinite(med[i]):
            i += 1; continue
        j = i
        while j + 1 < n and np.isfinite(med[j + 1]) and abs(med[j + 1] - med[i]) < 1.5:
            j += 1
        a2, b2 = i * HOP + int(0.3 * sr), j * HOP + FR - int(0.3 * sr)
        if b2 - a2 > int(0.6 * sr):
            out.append((a2, b2, float(440.0 * 2 ** (np.nanmedian(st[i:j + 1]) / 12))))
        i = j + 1
    return out


def track(x, sr, a, b, f0n):
    """Per frame: f0 from h1-h6's peaks within +/-150 cents of the note,
    weighted by their power; and the frame's rms."""
    N = 1 << 15
    f = np.fft.rfftfreq(N, 1.0 / sr)
    out = []
    for i in range(a, b - FR, HOP):
        seg = x[i:i + FR]
        X = np.abs(np.fft.rfft(seg * np.hanning(FR), N))
        num = den = 0.0
        for k in range(1, 7):
            w = (f > k * f0n * 2 ** -0.125) & (f < k * f0n * 2 ** 0.125)
            if not w.any():
                break
            j = np.flatnonzero(w)[np.argmax(X[w])]
            p = X[j] ** 2
            num += p * f[j] / k
            den += p
        if den > 0:
            out.append((i, num / den, float(np.sqrt(np.mean(seg * seg)))))
    return out


def vibrato(f0s, sr):
    """Depth (cents, peak = sqrt2 x rms after detrending) and rate (Hz)."""
    c = 1200 * np.log2(np.asarray(f0s) / np.median(f0s))
    w = max(3, int(round(1.0 * sr / HOP)))              # 1 s trend out
    w = min(w, len(c) // 2 * 2 - 1)
    c = c - np.convolve(c, np.ones(w) / w, "same")
    c = c[w:-w] if len(c) > 3 * w else c
    P = np.abs(np.fft.rfft(c * np.hanning(len(c)), 8 * len(c))) ** 2
    fr = np.fft.rfftfreq(8 * len(c), HOP / sr)
    s = (fr > 3.0) & (fr < 9.0)
    return float(np.sqrt(2) * c.std()), float(fr[s][np.argmax(P[s])])


def survey():
    rows = []
    for p, s, tech, vow in takes():
        x, sr = V.mono(p)
        for a, b, f0n in notes(x, sr):
            tr = track(x, sr, a, b, f0n)
            if len(tr) < 20:
                continue
            f0 = float(np.median([t[1] for t in tr]))
            dep, rate = vibrato([t[1] for t in tr], sr)
            midi = 69 + 12 * np.log2(f0 / 440.0)
            rows.append(dict(singer=s, type=TYPES[s], tech=tech, vowel=vow, f0=f0,
                             midi=float(midi), vib_cents=dep, vib_hz=rate,
                             secs=(b - a) / sr, span=(a / sr, b / sr), path=p))
            print("  %-4s %-12s %-8s %s  f0 %6.1f (midi %5.1f)  vib %5.1f c @ %.2f Hz  %4.1f s"
                  % (s, TYPES[s] + ("?" if s in UNSURE else ""), tech, vow, f0, midi, dep, rate,
                     (b - a) / sr), flush=True)
    return rows


EDGES = 100.0 * 2 ** (np.arange(0, 38) / 6.0)          # 1/6 octave, 100 Hz-7.5 kHz
MODEL = os.path.expanduser("~/Documents/refs/vocalset/model")
PROG = {"a": 52, "u": 53}
# readme type -> the VOICE_BODIES part ours sings it as (no bass-baritone there)
PART = {"soprano": "soprano", "mezzo": "mezzo", "countertenor": "countertenor",
        "tenor": "tenor", "baritone": "baritone", "bass": "bass"}


def ladder_frame(x, sr, i, f0):
    N = 1 << 15
    f = np.fft.rfftfreq(N, 1.0 / sr)
    X = np.abs(np.fft.rfft(x[i:i + FR] * np.hanning(FR), N)) ** 2
    hs = []
    for k in range(1, 200):
        fk = k * f0
        if fk > min(EDGES[-1], 0.45 * sr):
            break
        w = (f > fk - 0.25 * f0) & (f < fk + 0.25 * f0)
        hs.append((fk, X[w].max()))
    tot = sum(p for _, p in hs) + 1e-30
    return [(fk, 10 * np.log10(p / tot + 1e-30)) for fk, p in hs]


def ladder(x, sr, a, b, f0n):
    """[(Hz, dB re the frame's harmonic power)] for every harmonic of every
    frame below 7.5 kHz: the vowel's filter, sampled where the voice is."""
    return [h for i, f0, _ in track(x, sr, a, b, f0n) for h in ladder_frame(x, sr, i, f0)]


def binned(samples):
    F = np.array([s[0] for s in samples]); G = np.array([s[1] for s in samples])
    out = []
    for lo, hi in zip(EDGES, EDGES[1:]):
        m = (F >= lo) & (F < hi)
        out.append(float(np.median(G[m])) if m.sum() >= 8 else np.nan)
    return np.array(out)


def render_note(prog, part, key, out, secs=4.0, vel=90):
    import mido
    import wave
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("track_name", name=part, time=0))
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=prog, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=vel, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    # BY PATH: the renderer reads the declared part from the FILE's track names
    # (_voice_parts reopens it), and handed a MidiFile it finds none -- every
    # note then sang the body its pitch infers, whatever the track said.
    mid = out[:-4] + ".mid"
    m.save(mid)
    L, R = B.render(mid)[:2]
    os.remove(mid)
    x = 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64))
    x = x / max(np.abs(x).max(), 1e-12) * 0.5
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(B.SR)
    w.writeframes((x * 32767).astype("<i2").tobytes()); w.close()


def solo(cls, **over):
    """The program's class as ONE singer: VocalSet records one, and seven
    singers a few cents apart smear a high harmonic over several bins, which
    reads 3-8 dB dark at h24 under a peak-picker that sees one of them."""
    return type("Solo", (cls,), dict(dict(section_players=1), **over))


def ours(vt, vowel, key, over=None, tag=""):
    import patch_map
    d = MODEL + tag
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "%s_%s_%d.wav" % (vt, vowel, key))
    if not os.path.exists(p):
        prog = PROG[vowel]
        keep = patch_map.PROGRAM_CLASS.get(prog)
        base = patch_map.property_class_for_program(prog)
        patch_map.PROGRAM_CLASS[prog] = (type("Section", (base,), dict(over or {})) if vt == "choir"
                                         else solo(base, **(over or {})))
        try:
            render_note(prog, PART.get(vt, ""), key, p)
        finally:
            patch_map.PROGRAM_CLASS[prog] = keep
    x, sr = V.mono(p)
    a, b = int(0.8 * sr), int(3.6 * sr)
    return ladder(x, sr, a, b, 440.0 * 2 ** ((key - 69) / 12.0))


def recorded(techs=("straight", "forte", "pp")):
    """{(type, vowel): [(f0 of the note, frame f0, k, dB re frame)]}, cached."""
    cache = os.path.join(MODEL, "rec_%s.npz" % "_".join(techs))
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        return z["rec"].item()
    rec = {}
    for p, s, tech, vow in takes():
        if tech not in techs:
            continue
        x, sr = V.mono(p)
        for a, b, f0n in notes(x, sr):
            rows = rec.setdefault((TYPES[s], vow), [])
            for i, f0, _ in track(x, sr, a, b, f0n):
                for fk, db in ladder_frame(x, sr, i, f0):
                    rows.append((f0n, f0, round(fk / f0), db))
        print("  measured %s %s %s" % (s, tech, vow), flush=True)
    rec = {k: np.array(v) for k, v in rec.items()}
    os.makedirs(MODEL, exist_ok=True)
    np.savez(cache, rec=np.array(rec, dtype=object))
    return rec


def env(over=None, tag=""):
    """Each voice type's vowel, recorded against ours (one singer), per 1/6
    octave."""
    rec = recorded()
    res = {}
    for (vt, vow), smp in sorted(rec.items()):
        mod = []
        keys = sorted(set(int(round(69 + 12 * np.log2(f / 440.0))) for f in smp[:, 0]))
        for k in keys:
            mod += ours(vt, vow, k, (over or {}).get(vow), tag)
        smp = [(r[1] * r[2], r[3]) for r in smp]
        R, M = binned(smp), binned(mod)
        res[(vt, vow)] = (R, M)
        ok = np.isfinite(R) & np.isfinite(M)
        print("\n== %s \"%s\"  (keys %s)  rms %.1f dB over %d bands"
              % (vt, vow, keys, np.sqrt(np.mean((R[ok] - M[ok]) ** 2)), ok.sum()))
        print("   band Hz    rec    ours   ours-rec")
        for lo, hi, r, m_ in zip(EDGES, EDGES[1:], R, M):
            if np.isfinite(r) or np.isfinite(m_):
                d = m_ - r
                print("   %6.0f  %6.1f  %6.1f   %+6.1f %s" % ((lo * hi) ** 0.5, r, m_, d,
                      ("+" if d > 0 else "-") * min(25, int(abs(d) / 2)) if np.isfinite(d) else ""))
    return res


# THE FIT. A harmonic leaves the model at k^-ad x bore_gain(k f0) (series_volume
# is k^-ad to 1%), so the vowel can be refitted in closed form at every
# recorded frame's own harmonics -- vibrato samples ours where it sampled the
# singer. What a one-singer render adds on top (2-6 dB dark at the top) is
# carried as a fixed per-harmonic residual, read once from renders.
NF = 4                          # formants fitted: F1, F2, F3 and the singer's
# Each formant kept in its own region (Hz, for the ensemble-average body), or
# Powell trades them: unbounded, "ah"'s F2 left for 3.5 kHz and a fourth
# formant went to 7.9 kHz to chase the top bands.
RANGES = {"a": ((500, 1100), (900, 1600), (1900, 2800), (2500, 3800)),
          "u": ((220, 500), (550, 1100), (1900, 2800), (2500, 3800))}
# Bandwidth floors (Hz): a tract's losses do not allow narrower, and the fit
# went to 40-100 Hz on F3, which under a 5 Hz vibrato would whistle.
BW_MIN = (60.0, 80.0, 100.0, 150.0)
TOP_HZ = 5000.0                 # above it the takes reach their floor and breath
# Falsetto is a different SOURCE, not a different tract: the countertenor sat
# 12-20 dB bright across the whole spectrum in the shared fit, which no tract
# ratio can do. Measured on its own, not in the shared vowel.
SHARED = ("soprano", "mezzo", "tenor", "baritone", "bass")
KEYS0 = ("formants", "formant_floor", "tonal_dampening", "bore_corner_hz",
         "female_top_formant")


def current(vow):
    import patch_map
    c = patch_map.property_class_for_program(PROG[vow])
    return {k: getattr(c, k) for k in KEYS0} | {"bore_order": c.bore_order,
            "octave_dampening": c.octave_dampening, "frequency_x": c(261.6).frequency_x,
            "singers_formant_hz": c.singers_formant_hz}


def body(P, ratio, f0n, cluster=1.0):
    """_sung_formants for a declared part (its VOICE_CLUSTER gain on every
    formant above F2), then _formant_tune."""
    out = []
    fm = P["formants"]
    for i, (c, bw, a) in enumerate(fm):
        if ratio > 1.0 and i >= 2 and c * ratio >= P["singers_formant_hz"]:
            a = a * P["female_top_formant"]
        out.append((c * ratio, bw * ratio, a * (cluster if i >= 2 else 1.0)))
    c, bw, a = out[0]
    if f0n > c:
        new = min(f0n, out[1][0] * 0.8)
        if new > c:
            out[0] = (new, bw * (new / c) ** 0.5, a)
    return out


def analytic(P, ratio, f0n, f0, k, cluster=1.0):
    """dB of each sample's harmonic before the frame's normalisation."""
    ad = P["tonal_dampening"] + np.log2(f0n / P["frequency_x"]) * P["octave_dampening"]
    f = k * f0
    g = np.full_like(f, P["formant_floor"])
    for fn in np.unique(f0n):
        m = f0n == fn
        for c, bw, a in body(P, ratio, fn, cluster):
            d = (f[m] - c) / (bw * 0.5)
            g[m] += a / (1.0 + d * d)
    g /= 1.0 + (f / P["bore_corner_hz"]) ** P["bore_order"]
    return 20 * np.log10(g + 1e-30) - 20 * ad * np.log10(k)


def framenorm(db, fid):
    tot = np.bincount(fid, 10 ** (db / 10.0))
    return db - 10 * np.log10(tot[fid] + 1e-30)


def build_groups(vow, vts, P0):
    """The recorded samples of each voice type in VTS on VOW, with the
    one-singer render's residual against the closed form at P0."""
    import tonelib as T
    rec = recorded()
    groups = []
    for (vt, v), smp in sorted(rec.items()):
        if v != vow or vt not in vts:
            continue
        smp = smp[smp[:, 2] <= 64]                   # max_harmonic, below
        f0n, f0, k, db = smp.T
        _, fid = np.unique(np.c_[f0n, f0], axis=0, return_inverse=True)
        fid = fid.ravel()
        ratio = T.VOICE_BODIES[PART[vt]]
        cluster = T.VOICE_CLUSTER.get(PART[vt], 1.0)
        # the one-singer render's residual against the closed form, per key, per k
        res = np.zeros(len(k))
        for key in np.unique(np.round(69 + 12 * np.log2(f0n / 440.0))):
            fk = 440.0 * 2 ** ((key - 69) / 12.0)
            r = np.array(ours(vt, vow, int(key)))
            kk = np.round(r[:, 0] / fk)
            an = analytic(P0, ratio, np.full(len(kk), fk), np.full(len(kk), fk), kk, cluster)
            an -= 10 * np.log10(np.sum(10 ** (np.unique(an) / 10.0)))
            ks = np.unique(kk)
            rk = np.array([np.median(r[kk == q, 1]) for q in ks])
            ak = np.array([an[kk == q][0] for q in ks])
            sel = np.round(69 + 12 * np.log2(f0n / 440.0)) == key
            res[sel] = np.interp(k[sel], ks, rk - ak)
        band = np.digitize(k * f0, EDGES) - 1
        band[k * f0 > TOP_HZ] = -1
        groups.append(dict(vt=vt, f0n=f0n, f0=f0, k=k, db=db, fid=fid, ratio=ratio,
                           cluster=cluster, res=res, band=band))
    return groups


def fit_part(vt):
    """One declared part against the fitted vowels, both vowels at once: its
    tract ratio, a SOURCE slope offset (tonal_dampening, + is darker) and the
    gain on its cluster (every formant above F2). The vowels stay as fitted --
    this is what the part does differently, not a new vowel."""
    from scipy.optimize import minimize
    sets = []
    for vow in ("a", "u"):
        P0 = current(vow)
        sets += [(vow, P0, g) for g in build_groups(vow, (vt,), P0)]
    nb = len(EDGES) - 1

    def loss(x, report=False):
        ratio, dtd, cg = np.exp(x[0]), x[1], np.exp(x[2])
        L, out = 0.0, []
        for vow, P0, g in sets:
            P = dict(P0)
            P["tonal_dampening"] = P0["tonal_dampening"] + dtd
            m = framenorm(analytic(P, ratio, g["f0n"], g["f0"], g["k"], cg) + g["res"], g["fid"])
            e = m - g["db"]
            bands = []
            for b in range(nb):
                sl = g["band"] == b
                if sl.sum() < 8:
                    continue
                r, med = np.median(g["db"][sl]), np.median(e[sl])
                L += (1.0 if r > -45 else 0.3) * med * med
                bands.append(med)
            out.append((vow, bands))
        return (L, out) if report else L

    import tonelib as T
    x0 = np.array([np.log(T.VOICE_BODIES[PART[vt]]), 0.0, np.log(T.VOICE_CLUSTER.get(PART[vt], 1.0))])
    bounds = [(np.log(0.85), np.log(1.25)), (-0.8, 1.5), (np.log(0.02), np.log(2.0))]
    L0, rep0 = loss(x0, True)
    r = minimize(loss, x0, method="Powell", bounds=bounds, options=dict(xtol=1e-4, ftol=1e-7))
    L1, rep = loss(r.x, True)
    n = sum(len(b) for _, b in rep)
    print("== %s: weighted rms %.1f -> %.1f dB over %d bands" % (vt, np.sqrt(L0 / n), np.sqrt(L1 / n), n))
    print("   tract ratio %.3f (VOICE_BODIES %.2f)  source slope %+.3f (%+.1f dB/octave)  cluster x%.3f (%+.1f dB; VOICE_CLUSTER %.2f)"
          % (np.exp(r.x[0]), T.VOICE_BODIES[PART[vt]], r.x[1], -6.0206 * r.x[1], np.exp(r.x[2]),
             20 * np.log10(np.exp(r.x[2])), T.VOICE_CLUSTER.get(PART[vt], 1.0)))
    for (vow, b0), (_, b1) in zip(rep0, rep):
        print("   %s before " % vow + " ".join("%+.0f" % v for v in b0))
        print("   %s after  " % vow + " ".join("%+.0f" % v for v in b1))
    return r.x


def fit(vow, free_ratio=False):
    from scipy.optimize import minimize
    import tonelib as T
    P0 = current(vow)
    groups = build_groups(vow, SHARED, P0)
    nb = len(EDGES) - 1

    def unpack(x):
        P = dict(P0)
        fm = []
        for i in range(NF):
            c, bw, a = np.exp(x[3 * i:3 * i + 3])
            fm.append((c, bw, 1.0 if i == 0 else a))
        P["formants"] = tuple(fm)
        P["formant_floor"], P["bore_corner_hz"], P["female_top_formant"] = np.exp(x[3 * NF:3 * NF + 3])
        P["tonal_dampening"] = x[3 * NF + 3]
        return P

    def loss(x, report=False):
        P = unpack(x)
        L, out = 0.0, []
        for gi, g in enumerate(groups):
            ratio = np.exp(x[3 * NF + 4 + gi]) if free_ratio else g["ratio"]
            m = framenorm(analytic(P, ratio, g["f0n"], g["f0"], g["k"], g["cluster"]) + g["res"], g["fid"])
            e = m - g["db"]
            bands = []
            for b in range(nb):
                s = g["band"] == b
                if s.sum() < 8:
                    continue
                r = np.median(g["db"][s])
                med = np.median(e[s])
                w = 1.0 if r > -45 else 0.3
                L += w * med * med
                bands.append((b, r, med))
            out.append((g["vt"], bands))
        return (L, out) if report else L

    fm0 = list(P0["formants"])[:NF]
    while len(fm0) < NF:
        fm0.append((3000.0, 400.0, 0.1))
    x0 = np.r_[np.log(np.array(fm0)).ravel(), np.log([P0["formant_floor"], P0["bore_corner_hz"],
               P0["female_top_formant"]]), P0["tonal_dampening"]]
    if free_ratio:
        x0 = np.r_[x0, np.log([g["ratio"] for g in groups])]
    bounds = []
    for i, (lo, hi) in enumerate(RANGES[vow]):
        bounds += [(np.log(lo), np.log(hi)), (np.log(BW_MIN[i]), np.log(700.0)), (np.log(0.003), np.log(3.0))]
    bounds += [(np.log(0.001), np.log(0.5)), (np.log(2000.0), np.log(12000.0)),
               (np.log(0.05), np.log(1.0)), (0.6, 2.6)]     # a woman's cluster: weaker, never stronger
    if free_ratio:
        bounds += [(np.log(0.75), np.log(1.35))] * len(groups)
    x0 = np.clip(x0, [b[0] for b in bounds], [b[1] for b in bounds])
    L0 = loss(x0)
    r = minimize(loss, x0, method="Powell", bounds=bounds,
                 options=dict(maxiter=20000, xtol=1e-3, ftol=1e-6))
    P = unpack(r.x)
    L1, rep = loss(r.x, True)
    nband = sum(len(b) for _, b in rep)
    print("\n== %s: loss %.0f -> %.0f  (weighted rms %.1f -> %.1f dB over %d bands)"
          % (vow, L0, L1, np.sqrt(L0 / nband), np.sqrt(L1 / nband), nband))
    print("   formants = (%s)" % ", ".join("(%.0f, %.0f, %.3f)" % f for f in P["formants"]))
    print("   formant_floor %.4f  tonal_dampening %.3f  bore_corner_hz %.0f  female_top_formant %.3f"
          % (P["formant_floor"], P["tonal_dampening"], P["bore_corner_hz"], P["female_top_formant"]))
    if free_ratio:
        for gi, g in enumerate(groups):
            print("   %-12s tract ratio %.3f  (VOICE_BODIES %.2f)" % (g["vt"], np.exp(r.x[3 * NF + 4 + gi]), g["ratio"]))
    for vt, bands in rep:
        print("   %-12s " % vt + " ".join("%+.0f" % med for _, _, med in bands))
    return P


def gm_samples(path, prog):
    """[(sample name, root key, rate, int16 data)] that bank 0's PROG plays."""
    import struct
    sys.path.insert(0, os.path.join(HERE, "examples"))
    from gm_release import _chunks, _recs, INST, SAMPLE
    b = open(path, "rb").read()
    d, smpl = None, None
    for cid, o, sz in _chunks(b, 12, len(b)):
        if cid == b"LIST" and b[o:o + 4] == b"pdta":
            d = {c.decode(): b[oo:oo + s_] for c, oo, s_ in _chunks(b, o + 4, o + sz)}
        if cid == b"LIST" and b[o:o + 4] == b"sdta":
            for c, oo, s_ in _chunks(b, o + 4, o + sz):
                if c == b"smpl":
                    smpl = oo
    phdr = _recs(d["phdr"], "<20sHHHIII", 38)
    pbag, pgen = _recs(d["pbag"], "<HH", 4), _recs(d["pgen"], "<HH", 4)
    inst, ibag, igen = _recs(d["inst"], "<20sH", 22), _recs(d["ibag"], "<HH", 4), _recs(d["igen"], "<HH", 4)
    shdr = _recs(d["shdr"], "<20sIIIIIBbHH", 46)

    def gens(gen, bag, i):
        return {g[0]: g[1] for g in gen[bag[i][0]:bag[i + 1][0]]}
    out, seen = [], set()
    for pi, h in enumerate(phdr[:-1]):
        if h[2] != 0 or h[1] != prog:
            continue
        for zb in range(h[3], phdr[pi + 1][3]):
            pg = gens(pgen, pbag, zb)
            if INST not in pg:
                continue
            ii = pg[INST]
            for zi in range(inst[ii][1], inst[ii + 1][1]):
                ig = gens(igen, ibag, zi)
                if SAMPLE not in ig or ig[SAMPLE] in seen:
                    continue
                seen.add(ig[SAMPLE])
                sh = shdr[ig[SAMPLE]]
                root = ig.get(58, sh[6])            # overridingRootKey
                if root > 127:
                    root = sh[6]
                data = np.frombuffer(b[smpl + 2 * sh[1]:smpl + 2 * sh[2]], "<i2").astype(float) / 32768
                out.append((sh[0].split(b"\0")[0].decode("latin1"), root, sh[5], data))
    return out


def gm(sets=None):
    """GM sets' choirs (ensembles, in a room) against ours as the section."""
    sys.path.insert(0, os.path.join(HERE, "examples"))
    from gm_release import SETS
    for vow, prog in sorted(PROG.items()):
        for name, path in SETS:
            if not path or not os.path.exists(path):
                continue
            rec, mod, keys = [], [], set()
            for sname, root, sr, x in gm_samples(path, prog):
                f0n = 440.0 * 2 ** ((root - 69) / 12.0)
                a, b = int(0.15 * sr), len(x) - FR
                if b - a < 4 * HOP:
                    continue
                for i, f0, _ in track(x, sr, a, b, f0n)[::2]:
                    rec += ladder_frame(x, sr, i, f0)
                keys.add(root)
            for k in sorted(keys):
                mod += ours("choir", vow, k, None, "_section")
            R, M = binned(rec), binned(mod)
            ok = np.isfinite(R) & np.isfinite(M)
            print("\n== GM %d \"%s\" %s  (roots %s)  rms %.1f dB" % (prog, vow, name, sorted(keys),
                  np.sqrt(np.mean((R[ok] - M[ok]) ** 2))))
            for lo, hi, r, m_ in zip(EDGES, EDGES[1:], R, M):
                if np.isfinite(r) and np.isfinite(m_) and (lo * hi) ** 0.5 > 200:
                    print("   %6.0f  %6.1f  %6.1f   %+6.1f" % ((lo * hi) ** 0.5, r, m_, m_ - r))


DCS = os.path.expanduser("~/Documents/refs/dagstuhl/DagstuhlChoirSet")


def dcs_f0(stem, singer):
    """CREPE on the singer's LARYNX microphone (a contact mic: no crosstalk
    from the rest of the choir): (t, f0, confidence), 10 ms."""
    p = os.path.join(DCS, "annotations_csv_F0_CREPE", "%s_%s_LRX.csv" % (stem, singer))
    return np.loadtxt(p, delimiter=",") if os.path.exists(p) else None


def section():
    """Dagstuhl's full choir, two singers a part, against the aligned score:
    how far apart two singers of one part sit on the same note, each one's
    vibrato and slow wander inside a note, and how far apart they start."""
    pairs, vib, wander, entry = {}, {}, {}, {}
    for sc in sorted(glob.glob(os.path.join(DCS, "annotations_csv_scorerepresentation",
                                            "*_FullChoir_*_Stereo_STM_?.csv"))):
        b = os.path.basename(sc)
        stem, part = b.split("_Stereo_STM_")[0], b[-5]
        tr = [dcs_f0(stem, part + n) for n in "12"]
        if any(t is None for t in tr):
            continue
        score = np.atleast_2d(np.loadtxt(sc, delimiter=","))
        prev_end = -1.0
        for on, off, midi in score:
            # the middle of the note: past the onset's scoop, before the release
            a, z = on + 0.15, off - 0.1
            meds = []
            for i, t in enumerate(tr):
                m = (t[:, 0] >= a) & (t[:, 0] < z) & (t[:, 2] > 0.6)
                if m.sum() < 15:
                    meds.append(None); continue
                c = 1200 * np.log2(t[m, 1] / 440.0) - 100 * (midi - 69)
                c = c[np.abs(c - np.median(c)) < 150]          # an octave slip, a bad frame
                if len(c) < 15:
                    meds.append(None); continue
                meds.append(float(np.median(c)))
                if z - a >= 0.8 and len(c) >= 60:
                    w = 25                                     # 0.25 s: vibrato out, wander kept
                    trend = np.convolve(c, np.ones(w) / w, "same")[w:-w]
                    v = (c[w:-w] - trend)
                    P = np.abs(np.fft.rfft(v * np.hanning(len(v)), 8 * len(v))) ** 2
                    fr = np.fft.rfftfreq(8 * len(v), 0.01)
                    sel = (fr > 3) & (fr < 9)
                    vib.setdefault(part, []).append((np.sqrt(2) * v.std(), fr[sel][np.argmax(P[sel])]))
                    wander.setdefault(part, []).append(trend.max() - trend.min())
            if None not in meds:
                pairs.setdefault(part, []).append(meds[0] - meds[1])
            # an ENTRY: the note follows a rest of 0.3 s or more in this part
            if on - prev_end >= 0.3:
                st = []
                for t in tr:
                    m = (t[:, 0] >= on - 0.3) & (t[:, 0] < on + 0.4) & (t[:, 2] > 0.6)
                    st.append(t[m, 0][0] if m.any() else None)
                if None not in st:
                    entry.setdefault(part, []).append(st[0] - st[1])
            prev_end = off
    print("  part  notes  pair diff sd (c)  per-singer sd  |  vibrato depth c (med, IQR)  rate Hz  |  wander c  |  entries  |dt| ms med, 90%")
    for part in "SATB":
        d = np.array(pairs.get(part, [np.nan]))
        d = d - np.median(d)                    # a steady offset between two singers is a voice, not scatter
        # ROBUST: a wrong note, an octave slip or a misaligned score note is
        # hundreds of cents and is not intonation (the basses' raw sd was 424)
        d = d[np.abs(d) < 100]
        sd = 1.4826 * np.median(np.abs(d))
        v = np.array(vib.get(part, [(np.nan, np.nan)]))
        e = np.abs(np.array(entry.get(part, [np.nan]))) * 1000
        print("  %s   %5d  %6.1f            %6.1f        |  %5.1f (%4.1f-%4.1f)             %4.2f    |  %5.1f     |  %3d  %5.0f  %5.0f"
              % (part, len(d), sd, sd / np.sqrt(2), np.median(v[:, 0]),
                 np.percentile(v[:, 0], 25), np.percentile(v[:, 0], 75), np.median(v[:, 1]),
                 np.median(wander.get(part, [np.nan])), len(e), np.median(e), np.percentile(e, 90)))
    allv = np.concatenate([np.array(vib[p]) for p in vib])
    print("  rates: 10-90%% %.2f-%.2f Hz;  depth 10-90%% %.1f-%.1f c"
          % (np.percentile(allv[:, 1], 10), np.percentile(allv[:, 1], 90),
             np.percentile(allv[:, 0], 10), np.percentile(allv[:, 0], 90)))
    for part in "SATB":
        d = np.array(pairs.get(part, [np.nan]))
        print("  %s  two singers' steady offset %+.1f c (median of %d notes)" % (part, np.median(d), len(d)))


def locus_midi(out, take="DCS_LI_FullChoir_Take01", prog=52, tempo_scale=1.0,
               names=("Soprano", "Alto", "Tenor", "Bass")):
    """Bruckner's Locus iste from Dagstuhl's time-aligned score (the take's
    own timing, so the recording and ours line up), one named track a part."""
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=960)          # 120 bpm: 1920 ticks/s
    for part, name in zip("SATB", names):
        sc = np.atleast_2d(np.loadtxt(os.path.join(DCS, "annotations_csv_scorerepresentation",
                                                   "%s_Stereo_STM_%s.csv" % (take, part)), delimiter=","))
        ev = []
        for on, off, midi in sc:
            ev.append((on * tempo_scale, 1, int(midi)))
            ev.append((off * tempo_scale, 0, int(midi)))
        ev.sort()
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.MetaMessage("track_name", name=name, time=0))
        t.append(mido.Message("program_change", channel="SATB".index(part), program=prog, time=0))
        now = 0
        for at, kind, k in ev:
            tick = int(round(at * 1920))
            t.append(mido.Message("note_on", channel="SATB".index(part), note=k,
                                  velocity=80 if kind else 0, time=tick - now))
            now = tick
    m.save(out)


def ab(out_dir, roots, tags, names=("Soprano", "Alto", "Tenor", "Bass")):
    """Locus iste rendered once per tree (a copy of HEAD against the working
    one: blockrender's workers are spawned, so a class patched in this process
    would not reach them), the hall at -3 dB wet, hybridmean at 440."""
    import subprocess
    os.makedirs(out_dir, exist_ok=True)
    mid = os.path.join(out_dir, "locus_iste_%s.mid" % names[1].lower())
    locus_midi(mid, names=names)
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_WET="-3", TUNING_MASTER_DB="-12")
    for root, tag in zip(roots, tags):
        P = lambda f: os.path.join(out_dir, "locus_%s%s" % (tag, f))       # noqa: E731
        subprocess.check_call([sys.executable, os.path.join(root, "blockrender.py"), mid,
                               P(".dry.wav"), "hybridmean:440"], env=env, cwd=root)
        subprocess.check_call([sys.executable, os.path.join(HERE, "roomtail.py"),
                               P(".dry.wav"), P(".wav")], env=env)
        subprocess.check_call(["sox", P(".wav"), P(".norm.wav"), "gain", "-n", "-1"])
        subprocess.check_call(["lame", "-b", "256", "--quiet", P(".norm.wav"), P(".mp3")])
        for f in (".dry.wav", ".norm.wav", ".wav"):
            os.remove(P(f))
        print("  -> %s" % P(".mp3"), flush=True)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "survey"
    if cmd == "survey":
        rows = survey()
        for vt in sorted(set(r["type"] for r in rows)):
            rr = [r for r in rows if r["type"] == vt and r["tech"] != "messa"]
            print("  %-12s n %2d  midi %4.1f-%4.1f  vibrato %4.1f c (%.1f-%.1f) @ %.2f Hz"
                  % (vt, len(rr), min(r["midi"] for r in rr), max(r["midi"] for r in rr),
                     np.median([r["vib_cents"] for r in rr]),
                     min(r["vib_cents"] for r in rr), max(r["vib_cents"] for r in rr),
                     np.median([r["vib_hz"] for r in rr])))
        return 0
    if cmd == "part":
        for vt in argv[2:]:
            fit_part(vt)
        return 0
    if cmd == "fit":
        free = "--free-ratio" in argv
        for vow in [a for a in argv[2:] if not a.startswith("--")] or ("a", "u"):
            fit(vow, free)
        return 0
    if cmd == "ab":
        # choir_fit.py ab OUTDIR TAG=ROOT [TAG=ROOT ...]
        # --alto=NAME declares the alto line as another part (Countertenor)
        alto = next((a.split("=", 1)[1] for a in argv if a.startswith("--alto=")), "Alto")
        pairs = [a.split("=", 1) for a in argv[3:] if not a.startswith("--")]
        ab(argv[2], [r for _, r in pairs], [t for t, _ in pairs], ("Soprano", alto, "Tenor", "Bass"))
        return 0
    if cmd == "section":
        section()
        return 0
    if cmd == "gm":
        gm()
        return 0
    if cmd == "env":
        env()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
