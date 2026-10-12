#!/usr/bin/env python3
"""Measured swara positions per raga, from Saraga 1.5's Hindustani pitch tracks.

    python3 examples/saraga_swaras.py                 report every raga
    python3 examples/saraga_swaras.py --write         and write the measured ones into ragas.py
    python3 examples/saraga_swaras.py --harmonium     include the harmonium-accompanied tracks

THE DATA (sources.md "Saraga"; Zenodo 4301737, CC BY-NC-SA 4.0): 108 recordings,
each a predominant-pitch track (4.4 ms frames, Hz) and its tonic. MEASURED ONLY:
the numbers kept here are cents, never the audio, which was never extracted.

THE METHOD, Serra, Koduri, Miron & Serra (ISMIR 2011)'s:
  - pitch in cents above the tonic, folded into one octave;
  - STABLE regions only: a frame is kept where the 400 ms window around it has
    a standard deviation under 20 cents (a held swara, not a glide);
  - tracks accompanied by a HARMONIUM are left out, as Serra did -- a fixed
    equal-tempered instrument pulls the voice toward its own tuning
    (--harmonium keeps them, for comparison).
Per raga, every kept frame of every recording pooled; a swara is one the raga
SOUNDS when its histogram has a true local peak within 45 cents of its
equal-tempered place carrying 1% of the stable frames (peaks()); its position
is measured from the measured Sa, with its spread and count. A raga is
written (as saraga_<raga>, a system and the raga of its sounded swaras) with
five swaras or more, each 400 stable frames (~2 s) or more.
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import ragas  # noqa: E402

ROOT = os.path.expanduser("~/Documents/refs/saraga/saraga1.5_hindustani")
HOP = 0.0044444
WIN = int(round(0.4 / HOP))


def tracks(harmonium=False):
    """[(raga common name, title, cents array of stable frames)]."""
    out = []
    for js in sorted(glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True)):
        base = js[:-5]
        if not (os.path.exists(base + ".pitch.txt") and os.path.exists(base + ".ctonic.txt")):
            continue
        meta = json.load(open(js))
        rg = [r.get("common_name") for r in meta.get("raags", []) if r.get("common_name")]
        if len(rg) != 1:
            continue                    # a ragamala or none: no one raga to read
        inst = {a.get("instrument", {}).get("name", "").lower() for a in meta.get("artists", [])}
        if "harmonium" in inst and not harmonium:
            continue
        tonic = float(open(base + ".ctonic.txt").read().split()[0])
        p = np.loadtxt(base + ".pitch.txt")
        f = p[:, 1]
        c = np.where(f > 0, 1200.0 * np.log2(np.maximum(f, 1e-9) / tonic), np.nan)
        # the 400 ms window's SD, frame by frame (voiced frames only)
        ok = np.isfinite(c)
        cz = np.where(ok, c, 0.0)
        k = np.ones(WIN)
        n = np.convolve(ok.astype(float), k, "same")
        s1 = np.convolve(cz, k, "same")
        s2 = np.convolve(cz * cz, k, "same")
        mean = s1 / np.maximum(n, 1)
        sd = np.sqrt(np.maximum(s2 / np.maximum(n, 1) - mean * mean, 0.0))
        stable = ok & (n >= 0.9 * WIN) & (sd < 20.0)
        out.append((rg[0], meta.get("title", ""), np.mod(c[stable], 1200.0)))
    return out


def peaks(cents):
    """{swara: (cents re Sa, sd, frames)} for the swaras the raga SOUNDS: a
    histogram peak (1-cent bins, 11-cent smoothing) that is a true local
    maximum within 45 cents of the swara's equal-tempered place and carries 1%
    of the stable frames within 25 cents of it. Measured from the measured Sa
    (the tonic annotation sits a few cents off it)."""
    h = np.bincount(np.clip(np.round(cents).astype(int), 0, 1199), minlength=1200).astype(float)
    hs = np.convolve(np.concatenate([h[-5:], h, h[:5]]), np.ones(11) / 11.0, "same")[5:-5]
    total = len(cents)
    raw = {}
    for i in range(12):
        idx = np.arange(100 * i - 45, 100 * i + 46) % 1200
        cand = [j for j in idx if hs[j] >= hs[(j - 10) % 1200] and hs[j] >= hs[(j + 10) % 1200]]
        if not cand:
            continue
        j = max(cand, key=lambda q: hs[q])
        pk = float(j if not (i == 0 and j > 600) else j - 1200)
        d = (cents - pk + 600.0) % 1200.0 - 600.0
        near = d[np.abs(d) <= 25.0]
        if len(near) < 0.01 * total:
            continue
        raw[i] = (pk + float(np.mean(near)), float(np.std(near)), int(len(near)))
    if 0 not in raw:
        return {}
    sa = raw[0][0]
    return {i: ((v[0] - sa) % 1200.0 if i else 0.0, v[1], v[2]) for i, v in raw.items()}


def main(argv):
    harm = "--harmonium" in argv
    T = tracks(harm)
    by = {}
    for rg, title, c in T:
        by.setdefault(rg.lower(), []).append((title, c))
    found = {}
    print("  %d tracks with one raga%s; %d ragas" % (len(T), "" if harm else " (no harmonium)", len(by)))
    for rg in sorted(by, key=lambda r: -sum(len(c) for _, c in by[r])):
        recs = by[rg]
        c = np.concatenate([x for _, x in recs])
        pk = peaks(c)
        line = " ".join("%s %.0f(%.0f)" % (ragas.SWARAS[i], v[0], v[1]) for i, v in sorted(pk.items()))
        print("  %-22s %2d rec %7d frames  %s" % (rg[:22], len(recs), len(c), line))
        if len(pk) >= 5 and min(v[2] for v in pk.values()) >= 400:
            found[rg.replace(" ", "_")] = (pk, len(recs))
    if "--write" in argv and found:
        write(found, harm)
    return 0


def write(found, harm):
    """Each measured raga as a system (its unsounded swaras equal-tempered,
    sd None) and its swaras as a raga, below a marker in ragas.py."""
    p = os.path.join(HERE, "ragas.py")
    s = open(p).read()
    mark = "# --- MEASURED: examples/saraga_swaras.py --write ---"
    if mark in s:
        s = s[:s.index(mark)].rstrip("\n") + "\n"
    et = ragas.SYSTEMS["et"]["cents"]
    lines = ["", "", mark, "SYSTEMS.update({"]
    for key, (pk, nrec) in sorted(found.items()):
        cents = tuple(round(pk[i][0], 1) if i in pk else et[i] for i in range(12))
        sd = tuple(round(pk[i][1], 1) if i in pk else None for i in range(12))
        n = sum(v[2] for v in pk.values())
        lines.append('    "saraga_%s": dict(' % key)
        lines.append("        cents=%r," % (cents,))
        lines.append("        sd=%r," % (sd,))
        lines.append('        kind="measured",')
        lines.append('        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): %d recording(s), %d stable frames '
                     '(Serra 2011\'s rule, %s); unsounded swaras equal-tempered"),' % (
                         nrec, n, "harmonium tracks included" if harm else "no harmonium"))
    lines.append("})")
    lines.append("RAGAS.update({")
    for key, (pk, _) in sorted(found.items()):
        lines.append('    "saraga_%s": %r,' % (key, tuple(sorted(pk))))
    lines.append("})")
    open(p, "w").write(s + "\n".join(lines) + "\n")
    print("  wrote %d systems into ragas.py" % len(found))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
