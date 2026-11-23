"""Indian (Hindustani) intonation: SYSTEMS of swara positions and the RAGAS that
choose among the swaras, for a tuner whose tonic (Sa) moves.

    raga:<system>[/<raga>]@<Sa key>[:<Sa Hz>]      e.g.  raga:bel_todi/todi@c#
                                                         raga:just5/yaman@d:146.8

A SYSTEM is twelve positions in cents above Sa, one per swara (Sa, komal re,
Re, komal ga, Ga, Ma, tivra Ma, Pa, komal dha, Dha, komal ni, Ni), each with
its spread where one was measured and its source. A RAGA is which of the twelve
it uses (a thaat's scale); the swaras it omits stay in the tuner's table, so
every key still has a pitch -- the raga matters to the meend, whose detents are
the raga's swaras only (tonelib.meend_ratio).

WHAT THE MEASUREMENTS SAY, which is why there is more than one system. Measured
Hindustani intonation does not sit on one just table:
  - Serra, Koduri, Miron & Serra, ISMIR 2011 ("Assessing the tuning of sung
    Indian classical music", 133 Hindustani vocal recordings): the stable
    intervals correlate better with equal temperament (r 0.72) than with
    just intonation (0.64) -- hence `et` is a system here and not a strawman;
  - Bel 1988 (bolprocessor.org/raga-intonation, Todi, 8 occurrences each):
    Todi sits near PYTHAGOREAN positions, its commas narrowed (ga 294,
    dha 792, Ni 1107), spread 3-10 cents -- `bel_todi`;
  - the 5-limit table (`just5`) and the 3-limit one (`pythagorean`) are the
    two classical theories, carried as theory and labelled so.
Measured per-raga systems (sung_<raga>, MEASURED_PREFIX) are written by
examples/rrd_swaras.py from the Raga Recognition Dataset's Hindustani pitch
tracks (CC BY 4.0), since 2026-11-23; Saraga's (CC BY-NC-SA, dropped
2026-11-22: licences.md L5) only locally, by examples/saraga_swaras.py. The
interfaces show a "measured ragas" list only when there are some.

A SECONDARY TUNING, not the render's. blockrender's `eastern=` and live's
--eastern give the classes that declare tuning_family = 'indian' this table
while the rest of the ensemble keeps its own -- and by default Sa sits at the
primary tuner's own pitch for its key, so Sa coincides with the Western
instruments. examples/raga_compat.py ranks the systems by how they clash with
the Western notes they sound against.
"""
from math import log2

# a measured raga's system and raga keys begin so (the interfaces list them apart)
MEASURED_PREFIX = "sung_"

# swara index -> name, for reports
SWARAS = ("Sa", "re", "Re", "ga", "Ga", "Ma", "Ma'", "Pa", "dha", "Dha", "ni", "Ni")


def _c(r):
    return 1200.0 * log2(r)


SYSTEMS = {
    "just5": dict(
        cents=tuple(_c(r) for r in (1, 16 / 15, 9 / 8, 6 / 5, 5 / 4, 4 / 3, 45 / 32, 3 / 2,
                                    8 / 5, 5 / 3, 9 / 5, 15 / 8)),
        sd=None, kind="theory",
        source="5-limit just intonation (the asymmetric table tunelib.JustTuner carries)"),
    "pythagorean": dict(
        cents=tuple(_c(r) for r in (1, 256 / 243, 9 / 8, 32 / 27, 81 / 64, 4 / 3, 729 / 512,
                                    3 / 2, 128 / 81, 27 / 16, 16 / 9, 243 / 128)),
        sd=None, kind="theory",
        source="3-limit (Pythagorean): fifths and fourths only"),
    "et": dict(
        cents=tuple(100.0 * k for k in range(12)),
        sd=None, kind="published",
        source="equal temperament; Serra, Koduri, Miron & Serra, ISMIR 2011: 133 Hindustani "
               "vocal recordings correlate r 0.72 with it against 0.64 with just"),
    "bel_todi": dict(
        # Sa, re 95, Re -, ga 294, Ga -, Ma -, Ma' 606, Pa (3/2), dha 792, Dha -, ni -, Ni 1107;
        # the swaras Todi does not use are the Pythagorean table's, which Bel
        # finds its measured ones nearest
        cents=(0.0, 95.0, _c(9 / 8), 294.0, _c(81 / 64), _c(4 / 3), 606.0, _c(3 / 2),
               792.0, _c(27 / 16), _c(16 / 9), 1107.0),
        sd=(0.0, 4.0, None, 4.0, None, None, 10.0, None, 3.0, None, None, 6.0),
        kind="measured",
        source="Bel 1988 (Melodic Movement Analyser), raga Todi, 8 occurrences a swara: "
               "re 95 (4), ga 294 (4), Ma' 606 (10), dha 792 (3), Ni 1107 (6) -- "
               "bolprocessor.org/raga-intonation; the rest Pythagorean, which Todi sits nearest"),
}

# THE TEN THAATS (Bhatkhande): which swaras a raga of each uses, as a 12-mask,
# Sa first. A raga named here takes its thaat's swaras; a raga-specific
# omission (Marwa leaves out Pa) is written out.
_S, _r, _R, _g, _G, _M, _Mt, _P, _d, _D, _n, _N = range(12)
RAGAS = {
    "bilaval": (_S, _R, _G, _M, _P, _D, _N),
    "kalyan": (_S, _R, _G, _Mt, _P, _D, _N),
    "yaman": (_S, _R, _G, _Mt, _P, _D, _N),
    "khamaj": (_S, _R, _G, _M, _P, _D, _n),
    "kafi": (_S, _R, _g, _M, _P, _D, _n),
    "asavari": (_S, _R, _g, _M, _P, _d, _n),
    "bhairavi": (_S, _r, _g, _M, _P, _d, _n),
    "bhairav": (_S, _r, _G, _M, _P, _d, _N),
    "purvi": (_S, _r, _G, _Mt, _P, _d, _N),
    "marwa": (_S, _r, _G, _Mt, _D, _N),
    "todi": (_S, _r, _g, _Mt, _P, _d, _N),
}

_KEYS = {"c": 0, "c#": 1, "db": 1, "d": 2, "d#": 3, "eb": 3, "e": 4, "f": 5,
         "f#": 6, "gb": 6, "g": 7, "g#": 8, "ab": 8, "a": 9, "a#": 10, "bb": 10, "b": 11}


def parse(spec):
    """'raga:<system>[/<raga>]@<key>[:<Sa Hz>]' -> (system, raga or None, key 0-11, Sa Hz or None)."""
    s = spec.strip().lower()
    if s.startswith("raga:"):
        s = s[5:]
    hz = None
    if "@" not in s:
        raise ValueError("%r: Sa is required, e.g. raga:just5@c#" % spec)
    body, at = s.split("@", 1)
    if ":" in at:
        at, h = at.split(":", 1)
        hz = float(h)
    system, _, raga = body.partition("/")
    if system not in SYSTEMS:
        raise ValueError("unknown system %r; one of %s" % (system, ", ".join(sorted(SYSTEMS))))
    if raga and raga not in RAGAS:
        raise ValueError("unknown raga %r; one of %s" % (raga, ", ".join(sorted(RAGAS))))
    if at not in _KEYS:
        raise ValueError("unknown Sa key %r" % at)
    return system, (raga or None), _KEYS[at], hz


def swaras(system, raga=None):
    """The detents: [(swara index, cents re Sa)] of the raga's swaras -- the
    named raga's, else the system's own if it is a measured raga's, else all
    twelve."""
    c = SYSTEMS[system]["cents"]
    # a measured system is its raga's: sung_todi brings Todi's swaras
    use = RAGAS[raga] if raga else (RAGAS.get(system) or range(12))
    return [(i, c[i]) for i in use]


def sa_note(key):
    """The MIDI note of Sa for a key: the octave from middle C up."""
    return 60 + key


def table(spec, sa_hz=None):
    """{midi: Hz} for all 128 keys under SPEC, Sa at its key's note in the
    octave from middle C, at SA_HZ (spec's own, else this argument, else equal
    temperament's A440 pitch for that key)."""
    system, _, key, hz = parse(spec)
    c = SYSTEMS[system]["cents"]
    sa = sa_note(key)
    f_sa = hz or sa_hz or 440.0 * 2.0 ** ((sa - 69) / 12.0)
    out = {}
    for n in range(128):
        d = n - sa
        octv, deg = divmod(d, 12)
        out[n] = f_sa * 2.0 ** (octv + c[deg] / 1200.0)
    return out


def tuner_class(spec):
    """A tunelib-style tuner for SPEC, so raga:... also works as a primary
    tuner name (midilib.set_tuner)."""
    import tunelib
    tab = table(spec)

    class IndianTuner(tunelib.BaseTuner):
        __doc__ = "Indian intonation: %s." % spec
        SPEC = spec

        def __init__(self, *a, **k):
            self.notes = []
            self.npo = 12.0

        def noteFrequencies(self):
            # notes are re middle C (midilib.middle_c = 60)
            return [(n, tab[n + 60]) for n in sorted(self.notes) if 0 <= n + 60 < 128]

    return IndianTuner


# --- MEASURED: examples/rrd_swaras.py --write ---
SYSTEMS.update({
    "sung_abhogi": dict(
        cents=(0.0, 100.0, 201.3, 300.7, 400.0, 497.0, 600.0, 700.0, 800.0, 893.8, 1000.0, 1100.0),
        sd=(10.1, None, 11.4, 11.6, None, 9.7, None, None, None, 11.1, None, None),
        kind="measured",
        source="Ābhōgī: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 364139 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_ahira_bhairav": dict(
        cents=(0.0, 98.6, 200.0, 300.0, 390.8, 496.7, 600.0, 700.0, 800.0, 894.2, 995.4, 1100.0),
        sd=(9.6, 11.2, None, None, 11.0, 10.4, None, 9.1, None, 11.2, 11.2, None),
        kind="measured",
        source="Ahira bhairav: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 396074 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_alahaiya_bilaval": dict(
        cents=(0.0, 100.0, 203.9, 300.0, 395.2, 493.1, 600.0, 705.7, 800.0, 904.1, 1000.0, 1105.2),
        sd=(10.6, None, 12.3, None, 11.6, 11.7, None, 10.7, None, 12.0, None, 11.2),
        kind="measured",
        source="Alahaiyā bilāval: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 337025 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_bagesri": dict(
        cents=(0.0, 100.0, 201.9, 304.5, 400.0, 499.6, 600.0, 700.0, 800.0, 892.5, 994.4, 1100.0),
        sd=(9.5, None, 11.5, 12.5, None, 9.6, None, None, None, 11.0, 11.7, None),
        kind="measured",
        source="Bāgēśrī: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 539025 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_bairagi": dict(
        cents=(0.0, 99.8, 200.0, 300.0, 400.0, 499.1, 600.0, 700.6, 800.0, 900.0, 1000.4, 1100.0),
        sd=(9.6, 10.9, None, None, None, 9.5, None, 8.8, None, None, 10.3, None),
        kind="measured",
        source="Bairāgi: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 405212 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_basant": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 392.4, 500.1, 598.6, 701.5, 801.4, 900.0, 1000.0, 1104.4),
        sd=(9.4, None, None, None, 11.1, 10.7, 10.9, 10.9, 11.0, None, None, 11.5),
        kind="measured",
        source="Basant: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 243902 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_bhairav": dict(
        cents=(0.0, 98.9, 200.0, 300.0, 391.8, 490.6, 600.0, 701.3, 797.1, 900.0, 1000.0, 1101.3),
        sd=(10.3, 11.7, None, None, 11.5, 12.1, None, 9.7, 10.1, None, None, 12.4),
        kind="measured",
        source="Bhairav: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 334095 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_bhup": dict(
        cents=(0.0, 100.0, 204.3, 300.0, 393.1, 500.0, 600.0, 702.6, 800.0, 896.3, 1000.0, 1100.0),
        sd=(10.1, None, 11.9, None, 11.5, None, None, 9.9, None, 12.0, None, None),
        kind="measured",
        source="Bhūp: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 374780 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_bihag": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 396.1, 500.0, 608.8, 706.2, 800.0, 900.0, 1000.0, 1102.4),
        sd=(9.8, None, None, None, 10.4, None, 12.4, 9.9, None, None, None, 10.9),
        kind="measured",
        source="Bihāg: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 412548 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_bilasakhani_todi": dict(
        cents=(0.0, 101.8, 200.0, 300.4, 400.0, 494.9, 600.0, 701.7, 800.8, 900.0, 994.7, 1100.0),
        sd=(9.1, 10.2, None, 10.3, None, 11.0, None, 8.7, 10.7, None, 12.2, None),
        kind="measured",
        source="Bilāsakhānī tōḍī: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 482607 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_darbari": dict(
        cents=(0.0, 100.0, 199.9, 303.6, 400.0, 498.7, 600.0, 700.6, 800.6, 900.6, 997.7, 1100.0),
        sd=(9.2, None, 10.9, 12.4, None, 10.7, None, 9.3, 12.4, 10.5, 11.8, None),
        kind="measured",
        source="Darbāri: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 630065 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_des": dict(
        cents=(0.0, 100.0, 199.0, 300.0, 385.7, 493.8, 600.0, 697.7, 800.0, 901.1, 1001.4, 1101.1),
        sd=(9.4, None, 11.6, None, 12.4, 11.6, None, 11.3, None, 11.8, 13.1, 11.4),
        kind="measured",
        source="Dēś: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 160226 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_gaud_malhar": dict(
        cents=(0.0, 100.0, 205.4, 300.0, 394.8, 497.0, 600.0, 700.5, 800.0, 889.6, 1000.0, 1099.5),
        sd=(9.4, None, 11.7, None, 11.2, 10.7, None, 10.5, None, 10.7, None, 10.7),
        kind="measured",
        source="Gauḍ malhār: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 412874 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_hamsadhvani": dict(
        cents=(0.0, 100.0, 205.0, 300.0, 395.0, 500.0, 600.0, 703.0, 800.0, 900.0, 1000.0, 1098.0),
        sd=(9.7, None, 11.6, None, 10.7, None, None, 8.9, None, None, None, 10.6),
        kind="measured",
        source="Hamsadhvāni: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 233599 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_jog": dict(
        cents=(0.0, 100.0, 200.0, 302.3, 394.2, 497.9, 600.0, 703.9, 800.0, 900.0, 999.7, 1100.0),
        sd=(9.4, None, None, 11.7, 10.6, 10.8, None, 10.1, None, None, 10.8, None),
        kind="measured",
        source="Jōg: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 623162 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_kedar": dict(
        cents=(0.0, 100.0, 198.2, 300.0, 400.0, 498.4, 601.6, 700.4, 800.0, 894.4, 1000.0, 1100.0),
        sd=(9.1, None, 11.1, None, None, 10.2, 11.2, 9.2, None, 10.5, None, None),
        kind="measured",
        source="Kēdār: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 300926 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_khamaj": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 398.8, 498.8, 600.0, 701.5, 800.0, 898.4, 997.7, 1104.4),
        sd=(9.4, None, None, None, 10.5, 11.1, None, 9.0, None, 11.0, 10.7, 11.5),
        kind="measured",
        source="Khamāj: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 138549 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_lalit": dict(
        cents=(0.0, 98.9, 200.0, 300.0, 395.1, 497.8, 596.0, 700.0, 799.0, 900.0, 1000.0, 1103.4),
        sd=(9.7, 11.3, None, None, 11.3, 10.4, 11.3, None, 11.1, None, None, 10.6),
        kind="measured",
        source="Lalit: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 768765 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_madhukauns": dict(
        cents=(0.0, 100.0, 200.0, 304.4, 400.0, 500.0, 603.4, 701.6, 800.0, 900.0, 1004.9, 1087.8),
        sd=(9.4, None, None, 12.0, None, None, 11.4, 9.8, None, None, 11.6, 10.4),
        kind="measured",
        source="Madhukauns: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 281427 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_madhuvanti": dict(
        cents=(0.0, 100.0, 204.9, 299.7, 400.0, 500.0, 604.4, 702.5, 800.0, 900.0, 1000.0, 1104.2),
        sd=(10.3, None, 11.4, 11.5, None, None, 11.0, 10.2, None, None, None, 11.3),
        kind="measured",
        source="Madhuvanti: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 516814 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_malkauns": dict(
        cents=(0.0, 100.0, 200.0, 292.8, 400.0, 498.4, 600.0, 703.8, 802.5, 900.0, 1003.2, 1100.0),
        sd=(9.6, None, None, 12.0, None, 10.5, None, 10.1, 11.2, None, 12.1, None),
        kind="measured",
        source="Mālkauns: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 629143 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_marubihag": dict(
        cents=(0.0, 100.0, 206.4, 300.0, 393.7, 499.6, 604.9, 702.5, 800.0, 898.4, 1000.0, 1105.0),
        sd=(9.3, None, 10.9, None, 10.3, 10.9, 10.7, 9.5, None, 11.0, None, 10.4),
        kind="measured",
        source="Mārūbihāg: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 520599 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_miyan_malhar": dict(
        cents=(0.0, 100.0, 205.9, 300.0, 400.0, 498.5, 600.0, 703.1, 800.0, 913.1, 1000.4, 1103.4),
        sd=(10.4, None, 11.5, None, None, 13.1, None, 10.1, None, 11.0, 12.2, 11.1),
        kind="measured",
        source="Miyān malhār: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 625938 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_puriya_dhanasri": dict(
        cents=(0.0, 101.8, 200.0, 300.0, 390.4, 500.0, 600.9, 701.8, 795.6, 900.0, 1000.0, 1102.0),
        sd=(9.1, 12.1, None, None, 10.6, None, 11.2, 10.0, 10.4, None, None, 10.7),
        kind="measured",
        source="Puriyā dhanaśrī: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 406457 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_ragesri": dict(
        cents=(0.0, 100.0, 199.2, 300.0, 398.1, 498.3, 600.0, 700.0, 800.0, 896.3, 997.5, 1100.0),
        sd=(9.8, None, 12.1, None, 10.9, 11.1, None, None, None, 11.2, 11.5, None),
        kind="measured",
        source="Rāgēśrī: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 366725 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_sri": dict(
        cents=(0.0, 100.1, 200.0, 300.0, 390.3, 500.0, 603.3, 700.4, 801.0, 900.0, 1000.0, 1103.3),
        sd=(9.3, 11.1, None, None, 11.3, None, 11.0, 9.8, 11.2, None, None, 10.8),
        kind="measured",
        source="Śrī: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 971259 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_suddh_sarang": dict(
        cents=(0.0, 100.0, 204.9, 300.0, 400.0, 501.8, 606.4, 701.7, 800.0, 900.0, 1000.0, 1105.2),
        sd=(9.0, None, 11.1, None, None, 9.8, 11.3, 9.2, None, None, None, 11.0),
        kind="measured",
        source="Śuddh sāraṅg: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 324339 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_todi": dict(
        cents=(0.0, 102.6, 200.0, 300.3, 400.0, 500.0, 604.0, 697.8, 800.2, 900.0, 1000.0, 1103.1),
        sd=(10.8, 12.0, None, 12.5, None, None, 11.5, 10.4, 11.1, None, None, 11.7),
        kind="measured",
        source="Tōḍī: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 650025 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
    "sung_yaman_kalyan": dict(
        cents=(0.0, 100.0, 203.3, 300.0, 393.8, 500.0, 604.9, 702.9, 800.0, 897.6, 1000.0, 1099.5),
        sd=(9.6, None, 11.5, None, 10.6, None, 11.5, 9.1, None, 10.7, None, 10.5),
        kind="measured",
        source="Yaman kalyāṇ: the Raga Recognition Dataset (Gulati et al. 2016, CC BY 4.0), 10 recording(s), 524888 stable frames (Serra 2011's rule; harmonium tracks not told apart); unsounded swaras equal-tempered"),
})
RAGAS.update({
    "sung_abhogi": (0, 2, 3, 5, 9),
    "sung_ahira_bhairav": (0, 1, 4, 5, 7, 9, 10),
    "sung_alahaiya_bilaval": (0, 2, 4, 5, 7, 9, 11),
    "sung_bagesri": (0, 2, 3, 5, 9, 10),
    "sung_bairagi": (0, 1, 5, 7, 10),
    "sung_basant": (0, 4, 5, 6, 7, 8, 11),
    "sung_bhairav": (0, 1, 4, 5, 7, 8, 11),
    "sung_bhup": (0, 2, 4, 7, 9),
    "sung_bihag": (0, 4, 6, 7, 11),
    "sung_bilasakhani_todi": (0, 1, 3, 5, 7, 8, 10),
    "sung_darbari": (0, 2, 3, 5, 7, 8, 9, 10),
    "sung_des": (0, 2, 4, 5, 7, 9, 10, 11),
    "sung_gaud_malhar": (0, 2, 4, 5, 7, 9, 11),
    "sung_hamsadhvani": (0, 2, 4, 7, 11),
    "sung_jog": (0, 3, 4, 5, 7, 10),
    "sung_kedar": (0, 2, 5, 6, 7, 9),
    "sung_khamaj": (0, 4, 5, 7, 9, 10, 11),
    "sung_lalit": (0, 1, 4, 5, 6, 8, 11),
    "sung_madhukauns": (0, 3, 6, 7, 10, 11),
    "sung_madhuvanti": (0, 2, 3, 6, 7, 11),
    "sung_malkauns": (0, 3, 5, 7, 8, 10),
    "sung_marubihag": (0, 2, 4, 5, 6, 7, 9, 11),
    "sung_miyan_malhar": (0, 2, 5, 7, 9, 10, 11),
    "sung_puriya_dhanasri": (0, 1, 4, 6, 7, 8, 11),
    "sung_ragesri": (0, 2, 4, 5, 9, 10),
    "sung_sri": (0, 1, 4, 6, 7, 8, 11),
    "sung_suddh_sarang": (0, 2, 5, 6, 7, 11),
    "sung_todi": (0, 1, 3, 6, 7, 8, 11),
    "sung_yaman_kalyan": (0, 2, 4, 6, 7, 9, 11),
})
