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
Measured per-raga systems (saraga_<raga>) were added by
examples/saraga_swaras.py from Saraga 1.5 -- CC BY-NC-SA, so none ships:
dropped 2026-11-22 (licences.md L5); an open source to measure them again
is listed there. The interfaces show a "measured ragas" list only when
there are some.

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
