#!/usr/bin/env python3
"""What the wind does in real organ pipes, measured from a sample set.

    python3 examples/organ_wind_measure.py SETDIR [ODF] [--stops NAME,...] [--per-pipe]

SETDIR is a GrandOrgue sample set unpacked (Lars Palo's Pitea School of Music
set, CC BY-SA 2.5, in ~/Documents/refs/organ/pitea -- see sources.md), ODF its
organ definition (default PiteaMHS.organ: the base organ; the "extended" one
adds samples digitally re-worked to match). Its .wav files are WavPack; sox
reads them.

For every single-pipe stop (mixtures and cornets have several pipes a key and
are skipped), every pipe, over its steady sustain:

  noise     the power BETWEEN the partials (each partial's line and a few of
            its widths taken out) against the tone's, in third octaves and in
            all, and the band where it peaks -- the jet's turbulence, by
            Verge et al. a dipole at the jet's instability Strouhal number
  floor     the same bands in the release sample's last moments: the room,
            the blower and the recording, taken out of the noise
  skirts    each strong partial's power just outside its line against in it
  wander    the pitch (cents RMS) and level (dB RMS) of the strongest partial
            through the sustain, a slow linear drift taken out: the wind
  attack    the noise between partials in the first 80 ms against the
            sustain's: the chiff

THE SET WAS NOISE-REDUCED (Nick Appleton's Noise Reduce, by its own notes):
a fixed profile of the room's noise was subtracted from every sample. The
steady wind noise measured here is therefore a LOWER BOUND, and where it sits
near that profile it may be gone; the wander, the skirts and the attack, and
the noise's trend with the pipe's size where it stands clear of the room,
survive. The levels the model is given are set by ear (Ben's choice).

The two microphones' spectra are averaged as POWERS: summing the channels
first would cancel part of the room's decorrelated noise and flatter the
floor.
"""
import os
import re
import subprocess
import sys

import numpy as np

FAMILIES = (                       # by the stop's name, first match wins
    ("reed", r"TRUMPET|BASUN|CLAIRON|CROMORNE|CLARINET|BASSON|OBO|KONTRABASUN|REGAL|DULCIAN"),
    ("string", r"GAMB|SALICION|VIOL|CELEST|FUGARA"),
    ("flute", r"GEDA|GEDACK|POMMER|BORD|SUBBAS|FL|QUINTAD|NAZARD|ROHR|SPETS|SPITZ"),
    ("principal", r"PRINCIPAL|OKTAVA|OCTAV|PRESTANT|KVINTA|QUINT|TERS"),
)
SKIP = r"MIXTUR|CORNET|SCHARF|CYMBEL|SESQUI"
FOOT = {"32": 0.25, "16": 0.5, "8": 1.0, "4": 2.0, "2": 4.0, "1": 8.0,
        "2 2/3": 3.0, "2⅔": 3.0, "1 3/5": 5.0, "1⅗": 5.0, "1 1/3": 6.0}


def family(name):
    if re.search(SKIP, name, re.I):
        return None
    for fam, pat in FAMILIES:
        if re.search(pat, name, re.I):
            return fam
    return None


def footage(name):
    """The stop's pitch against 8', from its name: 4' -> 2, 2 2/3' -> 3 ..."""
    m = re.search(r"(\d+(?:\s?\d/\d)?)\s*'", name)
    if m:
        k = m.group(1).replace("  ", " ")
        if k in FOOT:
            return FOOT[k]
        try:
            return 8.0 / float(eval(k.replace(" ", "+")))
        except Exception:
            pass
    m = re.search(r"(\d)(\d\d)$", name)          # PEDOktava8 / POSKvinta223 style
    return 1.0


def stops(setdir, odf):
    """[(stop name, family, footage ratio, [(midi, path), ...])] of single-pipe stops."""
    t = open(os.path.join(setdir, odf), encoding="utf-8", errors="replace").read()
    out = []
    for m in re.finditer(r"^\[(Stop\d+)\]\s*\n(.*?)(?=^\[)", t, re.M | re.S):
        body = m.group(2)
        nm = re.search(r"^Name=(.*)$", body, re.M)
        if not nm:
            continue
        name = nm.group(1).strip()
        fam = family(name)
        if fam is None:
            continue
        pipes = []
        for pm in re.finditer(r"^Pipe\d+=(.*)$", body, re.M):
            v = pm.group(1).strip()
            if v.startswith("REF:") or not v:
                continue
            path = os.path.join(setdir, v.replace("\\", os.sep))
            km = re.match(r"(\d+)-", os.path.basename(path))
            if km and os.path.exists(path):
                pipes.append((int(km.group(1)), path))
        if pipes:
            out.append((name, fam, footage(name), pipes))
    return out


def read(path):
    """Stereo float samples (sox reads the set's WavPack) and the rate."""
    r = int(subprocess.run(["soxi", "-r", path], capture_output=True, text=True).stdout)
    ch = int(subprocess.run(["soxi", "-c", path], capture_output=True, text=True).stdout)
    d = subprocess.run(["sox", path, "-t", "f32", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(d, np.float32).astype(float).reshape(-1, ch), r


def psd(x, r):
    """Power spectrum, the channels' powers averaged."""
    n = len(x)
    w = np.hanning(n)
    S = np.mean([np.abs(np.fft.rfft(x[:, c] * w)) ** 2 for c in range(x.shape[1])], 0)
    return S / np.sum(w ** 2), np.fft.rfftfreq(n, 1.0 / r)


def find_f0(S, f, guess):
    """The fundamental near the expected one: the best harmonic sum within a
    quarter tone of guess (a stopped pipe's even harmonics are weak, so the
    sum is over every harmonic, odd and even)."""
    best, bf = -1.0, guess
    for c in np.linspace(guess * 2 ** (-0.5 / 12), guess * 2 ** (0.5 / 12), 61):
        k = np.arange(1, int(min(f[-1], 8000) / c) + 1)
        s = np.sum(np.interp(k * c, f, S))
        if s > best:
            best, bf = s, c
    # refine on the strongest of the first harmonics
    k = int(np.argmax([np.interp(j * bf, f, S) for j in range(1, 6)])) + 1
    sel = np.abs(f - k * bf) < 0.02 * k * bf
    if sel.any():
        i = np.flatnonzero(sel)[np.argmax(S[sel])]
        if 0 < i < len(S) - 1:              # parabolic interpolation on the log
            a, b, c = np.log(S[i - 1] + 1e-30), np.log(S[i] + 1e-30), np.log(S[i + 1] + 1e-30)
            d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
            bf = (f[i] + d * (f[1] - f[0])) / k
    return bf


BANDS = 100.0 * 2 ** (np.arange(0, 23) / 3.0)          # third octaves, 100 Hz .. 16 kHz


def width(k, f0, df):
    """A partial's line: the widest of 4 bins, 2 Hz and 5 cents of it -- a
    pipe's partials hold to about a cent, and their own spread is not wind."""
    return max(4.0 * df, 2.0, 0.003 * k * f0)


def lines(f, f0, df):
    """Bins on a partial's line, and in its skirt (one to six line widths out)."""
    on = np.zeros(len(f), bool)
    skirt = np.zeros(len(f), bool)
    for k in range(1, int(f[-1] / f0) + 1):
        w = width(k, f0, df)
        d = np.abs(f - k * f0)
        on |= d < w
        skirt |= (d >= w) & (d < 6 * w)
    return on, skirt


def measure_pipe(path, rel_path, f0_guess):
    x, r = read(path)
    mono = x.mean(1)
    hop = int(0.005 * r)
    env = np.sqrt(np.convolve(mono ** 2, np.ones(hop) / hop, "same"))
    on = int(np.argmax(env > env.max() * 0.1))
    # THE PLATEAU, not the file: a sample carries its own release and decay
    # after the steady tone (Pitea's, about the last second and a half), and
    # a window into it measured the decay as "wander" and its tail as "noise"
    lv = 20 * np.log10(env[::hop] + 1e-12)
    i0 = (on + int(0.4 * r)) // hop
    if i0 >= len(lv) - 4:
        return None
    plateau = np.median(lv[i0:i0 + max(4, int(1.5 * r) // hop)])
    drop = np.flatnonzero(lv[i0:] < plateau - 3.0)
    i1 = i0 + (drop[0] if len(drop) else len(lv) - i0)
    s0, s1 = on + int(0.4 * r), i1 * hop - int(0.15 * r)
    if s1 - s0 < int(0.8 * r):
        return None
    seg = x[s0:s1]
    S, f = psd(seg, r)
    df = f[1] - f[0]
    f0 = find_f0(S, f, f0_guess)
    on_l, skirt = lines(f, f0, df)
    tone = S[on_l].sum()
    off = ~on_l & (f > 50)
    out = dict(f0=f0, tone_db=10 * np.log10(tone + 1e-30))
    # noise density between the partials, per third octave, and its floor
    band_noise = np.full(len(BANDS), np.nan)
    for i, b in enumerate(BANDS):
        sel = off & (f >= b / 2 ** (1 / 6)) & (f < b * 2 ** (1 / 6))
        if sel.sum() > 3:
            # the band's noise power, as if no lines were taken out of it
            band_noise[i] = S[sel].mean() * np.sum((f >= b / 2 ** (1 / 6)) & (f < b * 2 ** (1 / 6)))
    floor = np.full(len(BANDS), np.nan)
    if rel_path and os.path.exists(rel_path):
        xr, rr = read(rel_path)
        tail = xr[-int(0.3 * rr):]
        Sr, fr = psd(tail, rr)
        for i, b in enumerate(BANDS):
            sel = (fr >= b / 2 ** (1 / 6)) & (fr < b * 2 ** (1 / 6))
            if sel.any():
                floor[i] = Sr[sel].mean() * np.sum((f >= b / 2 ** (1 / 6)) & (f < b * 2 ** (1 / 6)))
    clean = np.where(np.isnan(floor), band_noise, np.maximum(band_noise - floor, 0.0))
    noise = np.nansum(clean)
    out["noise_db"] = 10 * np.log10(noise / tone + 1e-30)
    out["floor_db"] = 10 * np.log10(np.nansum(floor) / tone + 1e-30) if not np.all(np.isnan(floor)) else np.nan
    out["peak_hz"] = float(BANDS[int(np.nanargmax(clean))]) if np.nansum(clean) > 0 else np.nan
    out["band_db"] = 10 * np.log10(clean / tone + 1e-30)
    # skirts: the strongest partials' power just outside the line, against in it
    sk = []
    for k in range(1, int(min(f[-1], 6000) / f0) + 1):
        w = width(k, f0, df)
        d = np.abs(f - k * f0)
        line = S[d < w].sum()
        if line < tone * 1e-3:
            continue
        sk.append(S[(d >= w) & (d < 6 * w)].sum() / line)
    out["skirt_db"] = 10 * np.log10(np.median(sk) + 1e-30) if sk else np.nan
    # wander: the strongest partial's frequency and level through the sustain
    k = int(np.argmax([np.interp(j * f0, f, S) for j in range(1, 8)])) + 1
    fk = k * f0
    N = int(2 ** np.ceil(np.log2(max(8 * r / fk, 2048))))
    hopw = N // 4
    fr_ = np.fft.rfftfreq(N, 1.0 / r)
    sel = np.abs(fr_ - fk) < 0.03 * fk
    cents, lev = [], []
    win = np.hanning(N)
    for i in range(0, len(seg) - N, hopw):
        P = np.abs(np.fft.rfft(seg[i:i + N].mean(1) * win)) ** 2
        j = np.flatnonzero(sel)[np.argmax(P[sel])]
        a, b, c = np.log(P[j - 1] + 1e-30), np.log(P[j] + 1e-30), np.log(P[j + 1] + 1e-30)
        dd = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        cents.append(1200 * np.log2((fr_[j] + dd * (fr_[1] - fr_[0])) / fk))
        lev.append(10 * np.log10(P[sel].sum() + 1e-30))
    if len(cents) > 8:
        t = np.arange(len(cents))
        cents = np.asarray(cents) - np.polyval(np.polyfit(t, cents, 1), t)
        lev = np.asarray(lev) - np.polyval(np.polyfit(t, lev, 1), t)
        out["wander_c"] = float(np.std(cents))
        out["wander_db"] = float(np.std(lev))
    else:
        out["wander_c"] = out["wander_db"] = np.nan
    # the attack's noise between partials, against the sustain's
    a0, a1 = on, on + int(0.08 * r)
    if a1 - a0 > 256:
        Sa, fa = psd(x[a0:a1], r)
        on_a, _ = lines(fa, f0, fa[1] - fa[0])
        offa = ~on_a & (fa > 50)
        out["attack_db"] = 10 * np.log10(Sa[offa].mean() / max(S[off].mean(), 1e-30) + 1e-30)
    else:
        out["attack_db"] = np.nan
    return out


def release_for(path):
    """A sustain sample's release: the set keeps them in rel*/ beside it."""
    d, b = os.path.split(path)
    rels = sorted(x for x in os.listdir(d) if x.startswith("rel") and os.path.isdir(os.path.join(d, x)))
    for rd in rels[::-1]:                              # the longest release last
        p = os.path.join(d, rd, b)
        if os.path.exists(p):
            return p
    return None


def main(argv):
    takes = ("--stops", "--every")                    # options with a value
    a = [x for i, x in enumerate(argv[1:], 1)
         if not x.startswith("--") and argv[i - 1] not in takes]
    setdir = a[0]
    odf = a[1] if len(a) > 1 else "PiteaMHS.organ"
    only = None
    if "--stops" in argv:
        only = [s.strip().upper() for s in argv[argv.index("--stops") + 1].split(",")]
    per_pipe = "--per-pipe" in argv
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 6
    rows = []
    for name, fam, ratio, pipes in stops(setdir, odf):
        if only and not any(o in name.upper() for o in only):
            continue
        for midi, path in pipes[::every]:
            guess = 440.0 * 2 ** ((midi - 69) / 12.0) * ratio
            try:
                m = measure_pipe(path, release_for(path), guess)
            except Exception as e:
                print("  %s %s: %s" % (name, os.path.basename(path), e), file=sys.stderr)
                continue
            if m is None:
                continue
            m.update(stop=name, fam=fam, midi=midi)
            rows.append(m)
            if per_pipe:
                print("  %-14s %-9s %3d %7.1f Hz  noise %6.1f dB (floor %6.1f), peak %6.0f Hz, "
                      "skirt %6.1f dB, wander %.2f c / %.2f dB, attack %+5.1f dB"
                      % (name, fam, midi, m["f0"], m["noise_db"], m["floor_db"], m["peak_hz"],
                         m["skirt_db"], m["wander_c"], m["wander_db"], m["attack_db"]))
    # the summary: each family, by octave of the pipe's own pitch
    print("\nwind noise between the partials, re the tone (dB), by family and octave"
          " -- a LOWER BOUND, the set being noise-reduced")
    print("  %-10s %8s %6s %10s %10s %9s %9s %9s %6s" % ("family", "octave", "pipes", "noise dB",
                                                      "peak Hz", "skirt dB", "wander c", "wander dB",
                                                      "attack"))
    for fam in ("principal", "flute", "string", "reed"):
        fr = [m for m in rows if m["fam"] == fam]
        for lo in (32.7, 65.4, 130.8, 261.6, 523.3, 1046.5, 2093.0, 4186.0):
            g = [m for m in fr if lo <= m["f0"] < 2 * lo]
            if not g:
                continue
            med = lambda k: np.nanmedian([m[k] for m in g])        # noqa: E731
            print("  %-10s %4.0f-%-4.0f %5d %10.1f %10.0f %9.1f %9.2f %9.2f %+6.1f"
                  % (fam, lo, 2 * lo, len(g), med("noise_db"), med("peak_hz"), med("skirt_db"),
                     med("wander_c"), med("wander_db"), med("attack_db")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
