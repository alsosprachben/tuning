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
Measured per-raga systems are added by examples/saraga_swaras.py (Saraga 1.5,
measured only), as saraga_<raga>.

A SECONDARY TUNING, not the render's. blockrender's `eastern=` and live's
--eastern give the classes that declare tuning_family = 'indian' this table
while the rest of the ensemble keeps its own -- and by default Sa sits at the
primary tuner's own pitch for its key, so Sa coincides with the Western
instruments. examples/raga_compat.py ranks the systems by how they clash with
the Western notes they sound against.
"""
from math import log2

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
    # a measured system is its raga's: saraga_todi brings Todi's swaras
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


# --- MEASURED: examples/saraga_swaras.py --write ---
SYSTEMS.update({
    "saraga_abhogi": dict(
        cents=(0.0, 100.0, 199.4, 298.3, 400.0, 489.0, 600.0, 699.8, 800.0, 895.7, 985.7, 1100.0),
        sd=(11.0, None, 11.8, 11.9, None, 10.4, None, 10.5, None, 11.8, 12.8, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 74778 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_ahir_bhairav": dict(
        cents=(0.0, 102.7, 200.0, 300.0, 387.5, 494.0, 600.0, 701.6, 800.0, 894.2, 997.4, 1100.0),
        sd=(7.5, 11.0, None, None, 9.2, 11.2, None, 8.1, None, 9.8, 10.7, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 120265 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_bairagi": dict(
        cents=(0.0, 98.0, 200.0, 300.0, 400.0, 498.9, 600.0, 701.2, 800.0, 900.0, 998.6, 1100.0),
        sd=(8.3, 10.0, None, None, None, 8.8, None, 7.7, None, None, 10.0, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 113608 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_bhairav": dict(
        cents=(0.0, 100.0, 205.1, 300.0, 395.5, 477.4, 600.0, 705.4, 800.0, 900.0, 1000.0, 1100.0),
        sd=(11.4, None, 12.7, None, 12.8, 13.2, None, 12.2, None, None, None, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 22075 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_bhimpalas": dict(
        cents=(0.0, 100.0, 206.3, 305.3, 400.0, 496.0, 600.0, 702.2, 800.0, 895.5, 994.4, 1100.0),
        sd=(8.7, None, 11.0, 12.2, None, 11.5, None, 10.0, None, 10.5, 12.5, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 2 recording(s), 112303 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_bilaskhani_todi": dict(
        cents=(0.0, 98.1, 200.0, 294.1, 400.0, 496.4, 600.0, 703.3, 794.1, 900.0, 995.0, 1100.0),
        sd=(7.5, 10.6, None, 10.2, None, 10.5, None, 7.8, 10.5, None, 12.2, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 39533 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_des": dict(
        cents=(0.0, 100.0, 207.0, 300.0, 400.0, 503.7, 600.0, 703.9, 800.0, 900.0, 1000.0, 1106.2),
        sd=(8.7, None, 9.5, None, None, 9.6, None, 8.6, None, None, None, 9.7),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 32357 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_dhani": dict(
        cents=(0.0, 100.0, 200.0, 319.3, 400.0, 483.3, 600.0, 701.9, 800.0, 900.0, 1009.7, 1100.0),
        sd=(11.8, None, None, 13.3, None, 12.0, None, 12.1, None, None, 13.2, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 2 recording(s), 55110 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_gaud_malhar": dict(
        cents=(0.0, 100.0, 210.9, 300.0, 398.4, 498.1, 600.0, 700.4, 800.0, 903.8, 1000.0, 1100.0),
        sd=(7.6, None, 8.7, None, 9.7, 9.4, None, 8.7, None, 10.0, None, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 40457 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_jog": dict(
        cents=(0.0, 100.0, 200.0, 299.8, 394.9, 498.3, 600.0, 705.2, 800.0, 900.0, 999.7, 1100.0),
        sd=(9.0, None, None, 9.9, 10.0, 10.3, None, 9.7, None, None, 10.8, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 2 recording(s), 345091 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_kalyan": dict(
        cents=(0.0, 100.0, 205.4, 300.0, 391.6, 500.0, 602.7, 700.2, 800.0, 900.0, 1000.0, 1103.1),
        sd=(10.7, None, 10.4, None, 9.7, None, 11.0, 9.9, None, None, None, 11.6),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 59298 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_kedar": dict(
        cents=(0.0, 100.0, 197.3, 300.0, 400.0, 497.8, 600.7, 700.7, 800.0, 895.1, 1000.0, 1100.7),
        sd=(9.7, None, 11.5, None, None, 9.4, 10.3, 9.2, None, 9.5, None, 10.6),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 58863 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_khamaj": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 398.6, 497.7, 600.0, 700.7, 800.0, 892.1, 997.5, 1108.5),
        sd=(11.4, None, None, None, 11.7, 11.0, None, 10.9, None, 10.9, 11.1, 11.0),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 25447 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_kirwani": dict(
        cents=(0.0, 100.0, 206.2, 307.1, 400.0, 504.3, 600.0, 707.6, 786.8, 900.0, 1000.0, 1099.0),
        sd=(9.8, None, 11.4, 10.5, None, 11.6, None, 9.9, 12.4, None, None, 9.6),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 32812 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_lagan_gandhar": dict(
        cents=(0.0, 100.0, 217.2, 300.0, 384.6, 500.0, 600.0, 701.6, 800.0, 900.0, 1013.8, 1066.6),
        sd=(9.1, None, 12.3, None, 12.7, None, None, 7.9, None, None, 11.6, 12.7),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 106108 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_lalat": dict(
        cents=(0.0, 92.7, 200.0, 300.0, 393.3, 499.1, 601.0, 701.5, 796.8, 900.0, 1000.0, 1100.0),
        sd=(6.9, 11.9, None, None, 9.1, 8.5, 10.5, 7.3, 9.8, None, None, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 36614 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_maajh_khamaj": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 398.4, 495.5, 600.0, 696.0, 800.0, 888.2, 1000.0, 1100.0),
        sd=(9.1, None, None, None, 11.8, 11.7, None, 12.9, None, 10.9, None, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 8455 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_madhukauns": dict(
        cents=(0.0, 100.0, 200.0, 294.6, 400.0, 500.0, 596.8, 699.7, 800.0, 900.0, 998.7, 1100.0),
        sd=(7.9, None, None, 11.6, None, None, 8.9, 8.7, None, None, 9.9, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 50421 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_malkauns": dict(
        cents=(0.0, 100.0, 200.0, 313.8, 400.0, 498.2, 600.0, 700.0, 803.8, 900.0, 1004.2, 1100.0),
        sd=(9.7, None, None, 12.2, None, 10.1, None, None, 12.0, None, 12.9, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 77718 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_marwa": dict(
        cents=(0.0, 89.9, 200.0, 300.0, 400.0, 500.0, 598.1, 700.0, 800.0, 887.3, 1000.0, 1100.2),
        sd=(8.0, 10.3, None, None, None, None, 11.0, None, None, 9.7, None, 10.7),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 40231 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_mishra_kalingada": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 392.5, 499.6, 600.0, 695.7, 822.9, 900.0, 1000.0, 1100.0),
        sd=(11.2, None, None, None, 11.9, 12.3, None, 8.5, 12.1, None, None, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 27065 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_miya_malhar": dict(
        cents=(0.0, 100.0, 204.1, 300.0, 400.0, 496.6, 609.3, 705.3, 800.0, 900.0, 985.3, 1103.1),
        sd=(7.5, None, 10.3, None, None, 12.7, 10.6, 8.1, None, None, 12.3, 10.1),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 53920 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_puriya_dhanashree": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 390.0, 500.0, 602.4, 701.0, 800.0, 900.0, 1000.0, 1101.3),
        sd=(11.2, None, None, None, 7.4, None, 9.4, 8.1, None, None, None, 10.4),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 29305 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_rageshri": dict(
        cents=(0.0, 100.0, 200.0, 300.0, 400.6, 506.9, 600.0, 700.0, 800.0, 900.0, 998.5, 1100.0),
        sd=(12.0, None, None, None, 10.5, 10.3, None, None, None, 10.9, 11.2, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 48320 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_saraswati": dict(
        cents=(0.0, 100.0, 202.2, 300.0, 400.0, 500.0, 598.9, 701.7, 800.0, 892.5, 1001.7, 1100.0),
        sd=(8.9, None, 11.2, None, None, None, 9.5, 9.2, None, 10.1, 11.0, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 1 recording(s), 21897 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_todi": dict(
        cents=(0.0, 107.8, 200.0, 306.0, 400.0, 500.0, 600.0, 699.3, 807.2, 900.0, 1000.0, 1100.0),
        sd=(11.6, 12.7, None, 12.6, None, None, None, 9.8, 11.6, None, None, None),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 2 recording(s), 180116 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
    "saraga_yaman_kalyan": dict(
        cents=(0.0, 100.0, 196.4, 300.0, 396.1, 500.0, 602.6, 703.6, 800.0, 900.0, 1000.0, 1103.4),
        sd=(8.3, None, 11.0, None, 10.0, None, 9.9, 7.7, None, None, None, 9.8),
        kind="measured",
        source="Saraga 1.5 Hindustani (CC BY-NC-SA 4.0): 2 recording(s), 77061 stable frames (Serra 2011's rule, no harmonium); unsounded swaras equal-tempered"),
})
RAGAS.update({
    "saraga_abhogi": (0, 2, 3, 5, 7, 9, 10),
    "saraga_ahir_bhairav": (0, 1, 4, 5, 7, 9, 10),
    "saraga_bairagi": (0, 1, 5, 7, 10),
    "saraga_bhairav": (0, 2, 4, 5, 7),
    "saraga_bhimpalas": (0, 2, 3, 5, 7, 9, 10),
    "saraga_bilaskhani_todi": (0, 1, 3, 5, 7, 8, 10),
    "saraga_des": (0, 2, 5, 7, 11),
    "saraga_dhani": (0, 3, 5, 7, 10),
    "saraga_gaud_malhar": (0, 2, 4, 5, 7, 9),
    "saraga_jog": (0, 3, 4, 5, 7, 10),
    "saraga_kalyan": (0, 2, 4, 6, 7, 11),
    "saraga_kedar": (0, 2, 5, 6, 7, 9, 11),
    "saraga_khamaj": (0, 4, 5, 7, 9, 10, 11),
    "saraga_kirwani": (0, 2, 3, 5, 7, 8, 11),
    "saraga_lagan_gandhar": (0, 2, 4, 7, 10, 11),
    "saraga_lalat": (0, 1, 4, 5, 6, 7, 8),
    "saraga_maajh_khamaj": (0, 4, 5, 7, 9),
    "saraga_madhukauns": (0, 3, 6, 7, 10),
    "saraga_malkauns": (0, 3, 5, 8, 10),
    "saraga_marwa": (0, 1, 6, 9, 11),
    "saraga_mishra_kalingada": (0, 4, 5, 7, 8),
    "saraga_miya_malhar": (0, 2, 5, 6, 7, 10, 11),
    "saraga_puriya_dhanashree": (0, 4, 6, 7, 11),
    "saraga_rageshri": (0, 4, 5, 9, 10),
    "saraga_saraswati": (0, 2, 6, 7, 9, 10),
    "saraga_todi": (0, 1, 3, 7, 8),
    "saraga_yaman_kalyan": (0, 2, 4, 6, 7, 11),
})
