#!/usr/bin/env python3
"""Measured swara positions per raga, from the Indian Art Music Raga
Recognition Dataset's Hindustani pitch tracks (Gulati, Serra, Ganguli,
Senturk & Serra, ISMIR 2016; Zenodo record 7278506, CC BY 4.0) -- since
2026-11-23 in Saraga's place (CC BY-NC-SA, licences.md L5).

    python3 examples/rrd_stage.py "^RagaDataset/Hindustani/features/.*\\.(pitch|tonicFine)$"   (once)
    python3 examples/rrd_swaras.py                 report every raga
    python3 examples/rrd_swaras.py --write         and write the measured ones into ragas.py

THE DATA: 300 recordings, 30 ragas, ten each -- each a predominant-pitch track
(time, Hz) and its tonic (tonicFine, Hz); the audio is not part of it.

THE METHOD, Serra, Koduri, Miron & Serra (ISMIR 2011)'s, as
examples/saraga_swaras.py had it (its peaks() reused): pitch in cents above
the tonic, folded into one octave; STABLE frames only (the 400 ms window
around a frame under 20 cents sd); per raga, every recording's stable frames
pooled, a swara one the raga SOUNDS when its histogram has a true local peak
within 45 cents of its equal-tempered place carrying 1% of them. Unlike
Saraga's, this dataset does not say which recordings have a harmonium, so
none can be left out: its equal-tempered pull is in the pool. A raga is
written (as sung_<raga>) with five swaras or more, each 400 stable frames or
more.
"""
import glob
import json
import os
import sys
import unicodedata

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
import ragas  # noqa: E402
from saraga_swaras import peaks  # noqa: E402

ROOT = os.path.expanduser("~/Documents/refs/rrd/RagaDataset/Hindustani")
MARK = "# --- MEASURED: examples/rrd_swaras.py --write ---"


def raga_names():
    m = json.load(open(os.path.join(ROOT, "_info_", "ragaId_to_ragaName_mapping.json")))
    return m


def key_of(name):
    """A raga's name as a system key: its letters without diacritics."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")


def tracks():
    """[(raga id, recording, cents of its stable frames)]."""
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "features", "*", "*", "*", "*.pitch"))):
        rid = p.split(os.sep)[-4]
        tf = p[:-len(".pitch")] + ".tonicFine"
        if not os.path.exists(tf):
            continue
        tonic = float(open(tf).read().split()[0])
        d = np.loadtxt(p)
        hop = float(np.median(np.diff(d[:200, 0])))
        win = int(round(0.4 / hop))
        f = d[:, 1]
        c = np.where(f > 0, 1200.0 * np.log2(np.maximum(f, 1e-9) / tonic), np.nan)
        ok = np.isfinite(c)
        cz = np.where(ok, c, 0.0)
        k = np.ones(win)
        n = np.convolve(ok.astype(float), k, "same")
        s1 = np.convolve(cz, k, "same")
        s2 = np.convolve(cz * cz, k, "same")
        mean = s1 / np.maximum(n, 1)
        sd = np.sqrt(np.maximum(s2 / np.maximum(n, 1) - mean * mean, 0.0))
        stable = ok & (n >= 0.9 * win) & (sd < 20.0)
        out.append((rid, os.path.basename(p)[:-6], np.mod(c[stable], 1200.0)))
    return out


def main(argv):
    names = raga_names()
    T = tracks()
    by = {}
    for rid, title, c in T:
        by.setdefault(rid, []).append((title, c))
    found = {}
    print("  %d recordings, %d ragas" % (len(T), len(by)))
    for rid in sorted(by, key=lambda r: -sum(len(c) for _, c in by[r])):
        recs = by[rid]
        c = np.concatenate([x for _, x in recs])
        pk = peaks(c)
        nm = names.get(rid, rid)
        line = " ".join("%s %.0f(%.0f)" % (ragas.SWARAS[i], v[0], v[1]) for i, v in sorted(pk.items()))
        print("  %-22s %2d rec %7d frames  %s" % (nm[:22], len(recs), len(c), line))
        if len(pk) >= 5 and min(v[2] for v in pk.values()) >= 400:
            found[key_of(nm)] = (pk, len(recs), nm)
    if "--write" in argv and found:
        write(found)
    return 0


def write(found):
    """Each measured raga as a system (its unsounded swaras equal-tempered,
    sd None) and its swaras as a raga, below a marker in ragas.py."""
    p = os.path.join(HERE, "ragas.py")
    s = open(p).read()
    if MARK in s:
        s = s[:s.index(MARK)].rstrip("\n") + "\n"
    et = ragas.SYSTEMS["et"]["cents"]
    lines = ["", "", MARK, "SYSTEMS.update({"]
    for key, (pk, nrec, nm) in sorted(found.items()):
        cents = tuple(round(pk[i][0], 1) if i in pk else et[i] for i in range(12))
        sd = tuple(round(pk[i][1], 1) if i in pk else None for i in range(12))
        n = sum(v[2] for v in pk.values())
        lines.append('    "%s%s": dict(' % (ragas.MEASURED_PREFIX, key))
        lines.append("        cents=%r," % (cents,))
        lines.append("        sd=%r," % (sd,))
        lines.append('        kind="measured",')
        lines.append('        source="%s: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), %d '
                     'recording(s), %d stable frames (Serra 2011\'s rule; harmonium tracks not told apart); '
                     'unsounded swaras equal-tempered"),' % (nm, nrec, n))
    lines.append("})")
    lines.append("RAGAS.update({")
    for key, (pk, _, _) in sorted(found.items()):
        lines.append('    "%s%s": %r,' % (ragas.MEASURED_PREFIX, key, tuple(sorted(pk))))
    lines.append("})")
    open(p, "w").write(s + "\n".join(lines) + "\n")
    print("  wrote %d systems into ragas.py" % len(found))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
