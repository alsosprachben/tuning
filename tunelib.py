#!/usr/bin/env python

"""
Copyright Ben Woolley 2010.
All rights reserved.

f *= ((18.0/17) + 1.0/1563.562862)
f = f * (18.0/17) + 1.0/1160.2814104929753

f = f * 4 / 3 + 0.00469652366

Just as each philosopher must overcome Plato, each composer must overcome Bach.

Presenting: "Method for The Dynamic Tuning of Music by Evaluating The Possible Harmonic Interval Ratios for Low Harmonic Entropy"

Generate an interval index by going through all intervals between all harmonics in a harmonic series of max_octaves (5):
    for each pythagorean interval, populate an equal-tempered interval index with each possibly-corresponding pythagorean interval. 
    
For each interval, from lowest to highest, create a graph branching on possible fundamentals.

Find the "most consonant (harmonically unioned/joined) path" through the graph, using the cost function:
    Keep a set of unique fundamentals used up to that point, associated with the number of harmonics to the fundamental's first note. 
    Each unique fundamental costs the number of harmonics to its first note.
    [optimization] Traverse first the ratios that do not introduce a new fundamental.
    
Tune the set of ratios by tuning the fundamental of the first interval to Pythagorean tuning to bias for fundamental movements of 4ths and 5ths.
Tune where C4 is 256. Since the tuning itself is rational, using a tuning that aligns on bits will keep more bits lining up.

To deal with sustained notes:
    Where notes are sustained, tune relative to the lowest sustained note.
    Do not allow pitch updates to pressed/sustained notes.
    (This moves the comma from the frequency domain to the time domain, as the commas cause the tuning base to shift over time.)
    [todo] Only allow the tuning solver to traverse the ratios which line up on the sustained note values.

[todo] To deal with music designed with counterpoint: emulate the qualities assumed by counterpoint. That is, bias for the consonance of the intervals declared consonant by counterpoint. To deal with comma drift, bias the dissonant intervals to drift the comma back into place.

[todo] Alternative way to deal with comma shift: when a new fundamental is added, bias in favor of least comma drift, then tonal accuracy. 
"""

from tonelib import *
import linearcomma
import math
from inharmonicity import *

def note2EqualRatio(npo, note):
    return 2 ** (float(note) / npo)    

def ratio2EqualNote(npo, r):
    from math import log
    #print r, npo
    return log(float(r)) * npo / log(2)


# THE PITCH THE WHOLE SYNTH TUNES TO. Every tuner here carries its own A -- 440
# for the modern ones (equal, just, linear, Bechstein), 415 for the baroque
# (hybrid, Werckmeister, meantone, Pythagorean, well, Sankey) -- and derives
# middle C from it, and
# the path-generated tuners rescale their whole table so A4 lands there. That is
# a per-temperament decision baked into each class, which is right for what a
# temperament IS but leaves no way to say "play this at A=432" or "at C=256"
# without editing the classes.
#
# set_reference() overrides all of them at once, and takes either end of the
# question: a= names the frequency of A4 (midi 69), c= the frequency of middle C
# (midi 60). They are the same statement from different ends -- C=256 is
# A=430.54 in equal temperament and something else in every other one, which is
# exactly why it has to be expressed as a note and a frequency rather than
# converted to an A behind the caller's back.
_REFERENCE = None            # (midi_note, frequency) or None to leave tuners alone


def set_reference(a=None, c=None):
    """Tune everything to a= (the pitch of A4) or c= (the pitch of middle C).

    Call with neither to go back to each temperament's own reference. Returns
    the (midi_note, frequency) pair in force. Invalidates the cached tables, so
    it can be called between renders.
    """
    global _REFERENCE
    if a is not None and c is not None:
        raise ValueError("set_reference: give a= or c=, not both")
    if a is None and c is None:
        _REFERENCE = None
    else:
        _REFERENCE = (69, float(a)) if a is not None else (60, float(c))
    _invalidate_tables()
    return _REFERENCE


def reference():
    """The (midi_note, frequency) reference in force, or None."""
    return _REFERENCE


def _invalidate_tables():
    """PathTuner caches its table per class; the reference scales that table."""
    seen = set()
    def walk(cls):
        if cls in seen: return
        seen.add(cls)
        if hasattr(cls, "_table"): cls._table = None
        for sub in cls.__subclasses__(): walk(sub)
    for name in list(globals()):
        obj = globals()[name]
        if isinstance(obj, type) and hasattr(obj, "_table"): walk(obj)


class BaseTuner:
    A = 440

    def in_cache(self):
        return False

    def __init__(self, sustain = None, notes_per_octave = 12, min_octaves = 5):
        self.npo = float(notes_per_octave)
        # The reference is a NOTE and a frequency, so A=432 and C=256 are the
        # same mechanism: divide out this temperament's own ratio for that note.
        # A4 is 9 semitones above middle C, which is where the bare 9 came from.
        ref = _REFERENCE
        if ref is None:
            self.C = float(self.A) / self.note2Ratio(9)
        else:
            self.C = float(ref[1]) / self.note2Ratio(ref[0] - 60)
        
        self.notes = []

    def addNote(self, note):
        self.notes.append(int(note))

    def tune(self, step = 1000, max_i = 10000):
        return

    def note2Ratio(self, interval):
        return note2EqualRatio(self.npo, interval)

    def noteFrequencies(self):
        return [(note, self.C * self.note2Ratio(note)) for note in sorted(self.notes)]

def compute_intervals(comma_spread):
    comma_n = 3 ** 12
    comma_d = 2 ** 12 * 2 ** 7
    comma = float(comma_n) / comma_d

    def comma_part(part):
        return comma ** (1.0 / part)

    if not comma_spread:
        return []
        
    ratios = [
        [0, 1.0],
    ]
    for note, i_n, i_d, part in comma_spread:
        last_note, last_ratio = ratios[-1]
        
        ratio = [
            last_note + note,
            last_ratio * float(i_n) / i_d * (comma_part(part) if part else 1),
        ]
        
        # normalize
        if ratio[0] > 12:
            ratio[0] -= 12
            ratio[1] /= 2
            
        if ratio[0] == 12: continue
        ratios.append(ratio)
        
    return dict(ratios)


class TwelveTuner(BaseTuner):
    def __init__(self, sustain = None, notes_per_octave = 12, min_octaves = 5):
        if hasattr(self, "stretch_interval"):
            self.stretch = self.stretch_interval
        else:
            self.stretch = 1.0
        
        if (notes_per_octave == 12):
            BaseTuner.__init__(self, 12)
        else:
            raise Exception("Notes per octave must be 12.")
                    
    comma_spread = []
    intervals = []
        
    def note2Ratio(self, note):
        octave_adjust = 1.0
        while note < 0 or note > 11:
            if note < 0:
                note += 12
                octave_adjust /= (2 * self.stretch)
            elif note > 11:
                note -= 12
                octave_adjust *= (2 * self.stretch)
                
        return self.intervals[note] * octave_adjust

class StretchTuner(TwelveTuner):
    A = 415

    # (12 5th / 7 8ths) for one octave == stretch tuning octave interval that aligns with the pythagorean comma
    stretch_interval = stretch_interval

    intervals = dict([
       pyth(0, 0, stretch_interval), # 0 C
       pyth(1, 0, stretch_interval), # 7 G
       pyth(2, 1, stretch_interval), # 2 D
       pyth(3, 1, stretch_interval), # 9 A
       pyth(4, 2, stretch_interval), # 4 E
       pyth(5, 2, stretch_interval), # 11 B
       pyth(6, 3, stretch_interval), # 6 F#
       pyth(7, 4, stretch_interval), # 1 C#
       pyth(8, 4, stretch_interval), # 8 G#
       pyth(9, 5, stretch_interval), # 3 D#
       pyth(10, 5, stretch_interval), # 10 A#
       pyth(11, 6, stretch_interval), # 5 F
    ])


class MeantoneTuner(TwelveTuner):
    """Quarter-comma meantone -- the historical organ/harpsichord temperament,
    and still the usual choice for this repertoire today.

    Every fifth is narrowed by a quarter of the syntonic comma, so the fifth is
    the GEOMETRIC MEAN 5^(1/4) (696.58 c, -5.38 c from pure) and four of them
    stack to a PURE 5/4 major third. That is the trade: pure thirds bought by
    tempering every single fifth, with the leftover comma dumped on one interval
    -- the wolf between G# and Eb (~+35 c), which makes the remote keys unusable.

    Contrast with HybridTuner, which keeps its fifths RATIONAL and instead
    bridges separate fifth-chains with a rational third, absorbing the comma at
    the bridges rather than smearing it across every fifth (no geometric mean),
    and spreads the Pythagorean comma over stretched octaves. Octaves here are
    pure 2:1, which is correct for mode-locked pipes.
    """
    A = 415
    _fifth = 5.0 ** 0.25                       # quarter-comma tempered fifth
    # chain position of each pitch class, Eb(-3) .. G#(+8); wolf falls G#->Eb
    _chain = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: 7, 8: 8,
              5: -1, 10: -2, 3: -3}
    intervals = {}
    for _pc, _n in _chain.items():
        _r = _fifth ** _n
        while _r >= 2.0: _r /= 2.0
        while _r < 1.0:  _r *= 2.0
        intervals[_pc] = _r
    del _pc, _n, _r


class EvenTuner(TwelveTuner):
    # A440, BECAUSE EQUAL TEMPERAMENT IS THE MODERN ONE. This sat at 415 with
    # the baroque tuners, which made it the equal-tempered control for
    # Werckmeister and meantone -- reasonable, but it also made `even` the
    # wrong thing to reach for whenever the music is not Bach, and silently:
    # everything simply came out a semitone flat. The baroque control is now
    # `hybrid`, which is the tuner that was verified for baroque anyway.
    A = 440
    
    # Even Temperament
    # 440 * 2 ** (float(n) / 12)
    intervals = {
        0:  note2EqualRatio(12, 0),  # C
        1:  note2EqualRatio(12, 1),  # Db
        2:  note2EqualRatio(12, 2),  # D
        3:  note2EqualRatio(12, 3),  # Eb
        4:  note2EqualRatio(12, 4),  # E
        5:  note2EqualRatio(12, 5),  # F
        6:  note2EqualRatio(12, 6),  # F#
        7:  note2EqualRatio(12, 7),  # G
        8:  note2EqualRatio(12, 8),  # Ab
        9:  note2EqualRatio(12, 9),  # A
        10: note2EqualRatio(12, 10), # Bb
        11: note2EqualRatio(12, 11), # B
    }


class GM2Tuner(EvenTuner):
    """`gm2`: a General MIDI 2 device's tuning, which the FILE owns.

    Its own table is equal temperament at A440 -- GM's power-on state -- and it
    is that by construction, being EvenTuner, so a file that sends no tuning
    renders bit-identically to `even`. What makes it different is not in this
    class but in what it licenses: under `gm2`, and only under `gm2`, the
    renderers keep an MTS store (mts.TuningStore) and let the file fill it with
    Bulk Tuning Dumps and Single Note Tuning Changes and select from it per
    channel with RPN 0/3 and 0/4. Bank 0 comes pre-loaded with every tuner in
    the registry, in the frozen order of mts.BUILTIN_PROGRAMS.

    Under any other tuner the renderer's temperament is the choice, and a file's
    MTS is ignored: choosing a tuner is choosing who owns the tuning.
    """
    A = 440

    @staticmethod
    def store_for(warn=None):
        """A fresh store for one render or one live session."""
        import mts
        return mts.TuningStore(warn=warn)

class LinearTuner(TwelveTuner):
    A = 440
    
    # Even Temperament
    # Simitone interval defined as: f = f * (18.0/17) + 1.0/n where n = 1160.2814104929753
    intervals = {
        0:  1.00000000000, # C
        1:  1.05968538929, # Db
        2:  1.12288168384, # D
        3:  1.18979540748, # Eb
        4:  1.26064523251, # E
        5:  1.33566269430, # F
        6:  1.41509294797, # F#
        7:  1.49919556949, # G
        8:  1.58824540405, # Ab
        9:  1.68253346417, # A
        10: 1.78236788077, # Bb
        11: 1.88807491011, # B
    }

class Linear5Tuner(TwelveTuner):
    A = 415
    
    # Even Temperament
    # 5ths kept in octave, offset linear -0.0015222627465 (7153/4698926)
    intervals = {
        0:  1.00000000000, # C
        1:  1.05957446446, # Db
        2:  1.12233604019, # D
        3:  1.18935731272, # Eb
        4:  1.25996408541, # E
        5:  1.33536301700, # F
        6:  1.41479563628, # F#
        7:  1.49847773725, # G
        8:  1.58783943395, # Ab
        9:  1.68198179754, # A
        10: 1.78251370633, # Bb
        11: 1.88842386537, # B
    }
    intervals = {
        0:  1.0,
        1:  1.0595744644627303,
        2:  1.1223360401930143,
        3:  1.1893573127135859,
        4:  1.2599640854101555,
        5:  1.3353630169957984,
        6:  1.4147956362794392,
        7:  1.498477737253151,
        8:  1.5878394339472466,
        9:  1.6819817975426725,
        10: 1.7825137063235299,
        11: 1.8884238653683842,
    }
    intervals = linearcomma.even


class PythTuner(TwelveTuner):
    A = 415
    
    # Pythagorean Temperament
    intervals = {
        0:  1.0 /1,    # C
        1:  256.0/243, # Db
        2:  9.0/8,     # D
        3:  32.0/27,   # Eb
        4:  81.0/64,   # E
        5:  4.0/3,     # F
        6:  729.0/512, # F#
        7:  3.0/2,     # G
        8:  128.0/81,  # Ab
        9:  27.0/16,   # A
        10: 16.0/9,    # Bb
        11: 243.0/128, # B
    }


class JustTuner(TwelveTuner):
    A = 440
    
    # Just Intonation
    # Asymmetric scale from http://en.wikipedia.org/wiki/Just_intonation
    intervals = {
        0:  1.0 /1,  # C
        1:  16.0/15, # Db
        2:  9.0 /8,  # D
        3:  6.0 /5,  # Eb
        4:  5.0 /4,  # E
        5:  4.0 /3,  # F
        6:  45.0/32, # F#
        7:  3.0 /2,  # G
        8:  8.0 /5,  # Ab
        9:  5.0 /3,  # A
        10: 9.0 /5,  # Bb
        11: 15.0/8, # B
    }


class WellTuner(TwelveTuner):
    A = 415

    # "Well-Tempered"
    # From http://www.bach-cantatas.com/Articles/Das_Wohltemperirte_Clavier.htm
    # Temperament deduced from the apparent spiral notation on the title page of WTC.  
    comma_spread = [
                         # DO   C
        (7, 3, 2, -7),   # SOL  G
        (7, 3, 2, -7),   # RE   D
        (7, 3, 2, -7),   # LA   A
        (7, 3, 2, -7),   # ME   E
        (7, 3, 2, None), # SI   B
        (7, 3, 2, None), # FA#  F#
        (7, 3, 2, None), # DO#  C#
        (7, 3, 2, -14),  # SOL# G#
        (7, 3, 2, -14),  # MIb  Eb
        (7, 3, 2, -14),  # SIb  Bb
        (7, 3, 2, -14),  # FA   F
        (7, 3, 2, -7),   # DO   C
    ]
    intervals = compute_intervals(comma_spread)


class WerckmeisterTuner(TwelveTuner):
    """Werckmeister III, from the cents John Sankey published for his Bach.

    The Pythagorean comma is taken off FOUR fifths -- C-G, G-D, D-A and B-F# --
    a quarter each; every other fifth stays pure. That is what a *wohltemperirte*
    tuning is and why the word is not "equal": the common keys keep thirds close
    to pure while the remote ones are merely spicy rather than unusable, so each
    key has its own colour and the WTC's twenty-four are twenty-four different
    places instead of one place transposed. Equal temperament abolishes exactly
    that distinction, which is why playing this repertoire in it removes the
    argument the repertoire is making.

    These are Sankey's numbers rather than the textbook's. They agree with the
    canonical Werckmeister III (0, 90.225, 192.18, 294.135, ...) to within a
    tenth of a cent, so it is that temperament and not a variant -- but the
    point of using his table is that his sequences were played to it.
    """
    A = 415
    # STRETCH, from the instrument's own stiffness rather than a piano's.
    #
    # A temperament sets the twelve intervals inside an octave; the octave
    # itself is set by where the lower note's 2nd partial actually sits, which
    # stiffness pushes sharp by sqrt((1+4B)/(1+B)). Tuning octaves beat-free
    # against that is what stretch IS, and the two compose independently --
    # TwelveTuner.note2Ratio multiplies the octave by 2*stretch_interval and
    # leaves `intervals` alone.
    #
    # With B measured at 3.51e-5 on the VCSL harpsichords (see tonelib), that
    # comes to 1.0000526: +0.091 cents per octave, +0.46 cents across a 61-note
    # compass. Inaudible -- and that is the result, not a reason to omit it.
    # A HARPSICHORD BARELY NEEDS STRETCHING, which is why historical
    # temperaments for it are quoted as exact ratios and why one can be tuned
    # genuinely beat-free where a piano cannot. StretchTuner carries 1.0019377
    # for piano wire, some +3.35 cents per octave; borrowing that for a
    # harpsichord would be wrong by roughly 17 cents across the compass, and
    # wrong in a way that would sound like a badly tuned instrument rather than
    # like a modelling choice.
    stretch_interval = 1.0000526
    cents = (0.0, 90.2, 192.3, 294.1, 390.2, 498.1,
             588.3, 696.2, 792.2, 888.3, 996.1, 1092.2)
    intervals = {}
    for _pc, _c in enumerate(cents):
        intervals[_pc] = 2.0 ** (_c / 1200.0)
    del _pc, _c


class SankeyTuner(TwelveTuner):
    """John Sankey's Scarlatti tuning, found by consonance analysis.

    Not deduced from a treatise but SEARCHED for: Sankey and Sethares scored
    candidate tunings against the actual chords Scarlatti writes, using a
    consonance measure over the harpsichord's own partials, and kept what the
    music liked best (J. Acoust. Soc. Am. 101(4):2332-2337, 1997). What came
    back resembles a tuning d'Alembert published in 1752, which is a better
    result than agreeing with a treatise chosen in advance -- the music and the
    document independently point at the same place.

    C-E is a PURE 5:4 (386.3 c) and the fifth is meantone-ish at 696.8 c, so the
    home keys have meantone's pure thirds; but the chromatic notes depart from
    quarter-comma (85.6 against 76.0 for the minor second, 787.5 against 772.6
    for the minor sixth), which is what buys back the remote keys that
    quarter-comma's wolf makes unplayable. Scarlatti goes to those keys
    constantly, so a strict meantone cannot be what he tuned to.
    """
    A = 415
    stretch_interval = 1.0000526     # see WerckmeisterTuner: the same strings
    cents = (0.0, 85.6, 193.4, 291.4, 386.3, 498.0,
             584.7, 696.8, 787.5, 888.7, 994.9, 1086.5)
    intervals = {}
    for _pc, _c in enumerate(cents):
        intervals[_pc] = 2.0 ** (_c / 1200.0)
    del _pc, _c


class LinearWellTuner(TwelveTuner):
    A = 415
    
    # "Well-Tempered" as WellTuner, but using linear comma spreads, not logarithmic.
    intervals = {
        0: 1.0,
        1: 1.0600901508876619,
        2: 1.1225016216431984,
        3: 1.1901030413918179,
        4: 1.2603159459917965,
        5: 1.3363675432089936,
        6: 1.4153570608839696,
        7: 1.4985723552246848,
        8: 1.5887075815561775,
        9: 1.6823247876894825,
        10: 1.7837269173124117,
        11: 1.8890462742123797,
    }
    intervals = linearcomma.well

class BechsteinTuner(TwelveTuner):
    A = 440

    # From http://www.bach1722.com/
    # Temperament found on the 1898 Bechstein piano of the Cathedral of Savona.
    comma_spread = [
                         # DO   C
        (7, 3, 2, -4),   # SOL  G
        (7, 3, 2, -4),   # RE   D
        (7, 3, 2, -4),   # LA   A
        (7, 3, 2, -4),   # ME   E
        (7, 3, 2, None), # SI   B
        (7, 3, 2, None), # FA#  F#
        (7, 3, 2, None), # DO#  C#
        (7, 3, 2, 12),   # SOL# G#
        (7, 3, 2, 12),   # MIb  Eb
        (7, 3, 2, 12),   # SIb  Bb
        (7, 3, 2, None), # FA   F
        (7, 3, 2, -4),   # DO   C
    ]
    intervals = compute_intervals(comma_spread)


# --- Experimental path.py tuning generators (../path/path.py) ---------------
# The classes above are adaptive/parametric twelve-tone temperaments. These wrap
# the tree-based generators in ../path/path.py (HybridNotes, SpiralNotes, ...) as
# fixed full-keyboard tuners: the generator is built once and its per-MIDI-note
# frequencies are served by lookup. HybridNotes and its kin stretch their octaves
# along the empirical Steinway-B inharmonicity model -- the very model
# tonelib.GrandPianoProperties renders its partials with (identical a,b,c,d,e) -- so an octave
# is placed exactly on the lower note's 2nd partial. Rendered with the piano
# patch, the octave's fundamental then coincides with that partial and does not
# beat. That alignment is the whole point of using these here.

_PATH_MODULE = None


def _load_path_module():
    global _PATH_MODULE
    if _PATH_MODULE is None:
        import os, importlib.util
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "path", "path.py")
        spec = importlib.util.spec_from_file_location("path_gen", p)
        _PATH_MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PATH_MODULE)
    return _PATH_MODULE


class PathTuner(BaseTuner):
    """Fixed full-keyboard tuning read from a path.py generator class.

    A = None keeps the generator's native pitch, so the synth computes each
    note's inharmonicity from exactly the frequency the generator tuned against
    (exact 2nd-partial/octave alignment). Set A to rescale the whole table so
    A4 == A (e.g. 415 for baroque pitch), at the cost of a sub-cent alignment
    drift, since the empirical coefficient is frequency-dependent.
    """
    A = None
    generator_name = None
    generator_args = ()
    middle_c = 60
    _table = None    # class-cached {absolute_midi: frequency}

    def __init__(self, *args, **kwargs):
        self.notes = []
        cls = type(self)
        # cls.__dict__, not cls._table: the latter resolves through the MRO, so
        # a subclass that overrides _build_table() (HybridHarmonicTuner) would
        # find its PARENT's already-built table, see it is not None, and skip
        # building its own -- silently serving the parent's tuning under the
        # subclass's name. Only bites when both are built in one process.
        if cls.__dict__.get('_table') is None:
            cls._table = cls._build_table()

    @classmethod
    def _build_table(cls):
        gen = getattr(_load_path_module(), cls.generator_name)(*cls.generator_args)
        table = {n: float(note.f) for n, note in enumerate(gen.notes)
                 if getattr(note, "f", None)}
        ref = _REFERENCE if _REFERENCE is not None else (
              (69, cls.A) if cls.A is not None else None)
        if ref is not None and table.get(ref[0]):
            s = float(ref[1]) / table[ref[0]]
            table = {n: f * s for n, f in table.items()}
        return table

    def in_cache(self):
        return True

    def tune(self, step=1000, max_i=10000):
        return

    def _freq(self, midi):
        t = type(self)._table
        if midi in t:
            return t[midi]
        # Outside the generator's tuned range: extrapolate by pure 2:1 octaves
        # from the nearest tuned note of the same pitch class.
        for k in range(1, 10):
            if midi - 12 * k in t:
                return t[midi - 12 * k] * (2.0 ** k)
            if midi + 12 * k in t:
                return t[midi + 12 * k] / (2.0 ** k)
        if _REFERENCE is not None:
            return float(_REFERENCE[1]) * 2.0 ** ((midi - _REFERENCE[0]) / 12.0)
        base = self.A or 440.0
        return float(base) * 2.0 ** ((midi - 69) / 12.0)

    def noteFrequencies(self):
        mc = type(self).middle_c
        return [(note, self._freq(note + mc)) for note in sorted(self.notes)]


class HybridTuner(PathTuner):
    # A415: THIS IS THE BAROQUE TUNER, verified by ear as the one for baroque,
    # so it carries baroque pitch. Path-generated tuners set A to None by
    # default, which means "use the generator's own frequencies" -- those put
    # A4 at 441.04, near modern pitch by accident rather than by decision.
    # Naming it rescales the whole table so A4 lands there, which is what the
    # reference comment at the top of this file describes.
    #
    # HybridHarmonicTuner inherits this, deliberately: it is the same
    # temperament on pure octaves, for pipes rather than strings, and a pipe
    # organ of the period is no less at 415 than a harpsichord is.
    A = 415
    generator_name = "HybridNotes"


class HybridHarmonicTuner(HybridTuner):
    """The hybrid temperament on PURE 2:1 octaves.

    HybridTuner stretches its octaves to land on each note's sharp 2nd partial --
    right for a piano, whose free-decaying stiff strings really are inharmonic.
    A pipe is a driven, MODE-LOCKED oscillator: its steady tone is exactly
    harmonic, so there is no sharp 2nd partial to chase and a stretched octave
    would just beat with nothing to cancel it. This keeps the hybrid's
    within-octave temperament (meantone-flavoured -- a pure C-E third) and
    repeats it by exact 2:1, so pipes get pure thirds AND pure octaves.
    Use this for organ; use HybridTuner for piano/harpsichord.
    """
    @classmethod
    def _build_table(cls):
        # cls, NOT HybridTuner. Calling the parent by name built the stretched
        # table from HybridTuner's OWN reference pitch and then derived the
        # pure-octave table from that, so any subclass with a different A was
        # silently given the parent's -- which is exactly what happened to
        # HybridHarmonic440Tuner, sitting at 415 while saying 440. Harmless
        # while every hybrid shared one pitch, wrong as soon as one did not.
        base = PathTuner._build_table.__func__(cls)
        if 60 not in base:
            return base
        ref = {i: base[60 + i] / base[60] for i in range(12) if 60 + i in base}
        if len(ref) < 12:
            return base
        c4 = base[60]
        return {n: c4 * ref[(n - 60) % 12] * (2.0 ** ((n - 60 - ((n - 60) % 12)) // 12))
                for n in range(128)}



class HybridMeanTuner(PathTuner):
    """The hybrid's two chains of pure fifths, bridged by a MEAN third.

    Ben's construction. Chain one, C3-G-D-A-E-B5, and chain two, C#3-G#-D#-
    A#-F-C6, pure fifths both; the bridge is D4-F#4, and F#4 reaches chain
    two by a pure fourth to C#4. The hybrid bridges with a pure 5:4, which
    leaves one fifth 21.5 cents narrow -- the wolf. Here the bridge is the
    geometric mean of 5:4 and 81:64, 397.07 cents, half a syntonic comma wide,
    and the comma splits almost evenly over the two fifths between the chains:
    B-F# -10.75 and F-C -12.71. No wolf.

    The thirds: every third lies within a chain or crosses one gap. The eight
    that cross (D E A B, and Eb F Ab Bb) sit at +10.8 and +8.8 cents, between
    pure and equal (+13.7); the four inside a chain (C C# F# G) are
    Pythagorean, +21.5. Twelve thirds always average +13.7 in any closed
    12-note tuning, so this is choosing WHICH are good, and the mean bridge
    makes eight of them nearly alike.

    Pure octaves: it is for pipes, which are exactly harmonic.
    """
    A = 415

    @classmethod
    def _bridge(cls):
        return 1200.0 * math.log(math.sqrt(1.25 * 81.0 / 64.0), 2)

    @classmethod
    def _build_table(cls):
        P = 1200.0 * math.log(1.5, 2)
        X = cls._bridge()
        c = {}
        for i, n in enumerate((0, 7, 2, 9, 4, 11)):     # C G D A E B, pure
            c[n] = (i * P) % 1200.0
        c[6] = (c[2] + X) % 1200.0                      # the bridge, D-F#
        c[1] = (c[6] + P) % 1200.0                      # F#-C#, pure
        for i, n in enumerate((8, 3, 10, 5), 1):        # C# G# D# A# F, pure
            c[n] = (c[1] + i * P) % 1200.0
        ref = _REFERENCE if _REFERENCE is not None else (69, cls.A or 440.0)
        base = float(ref[1]) / 2.0 ** ((c[ref[0] % 12] + 1200.0 * (ref[0] // 12)) / 1200.0)
        return {n: base * 2.0 ** ((c[n % 12] + 1200.0 * (n // 12)) / 1200.0)
                for n in range(128)}


# TWO CHAINS, ANY BRIDGE (the Clavitone sequencer's model, tuning-lean
# HybridMean.lean): hybridmean's two chains of pure fifths on pure octaves,
# C G D A E B and F# C# G# D# A# F, with the bridge third D-F# a free value X
# in cents. Thirds on D A E B (2-5) are X exactly; on C G F# C# (0, 1, 6, 7)
# Pythagorean; on G# D# A# F (8-11) 3*1200 - 4P - X. The two gap fifths,
# B-F# and F-C, take the comma between them: X + 2400 - 3P and 6000 - 7P - X.
# No fifth is wider than pure exactly when 6000 - 8P <= X <= 4P - 2400 (the
# schismatic third to the Pythagorean). The bridge is a mirror (tuning-lean
# HomeKey.lean, rotate_six): X rotated six fifths is 3*1200 - 4P - X, so a
# bridge above the midpoint 396.09 is one below it on the key a tritone away.
# Named bridges:
CHAIN_BRIDGES = {
    "helm": lambda P: 6000.0 - 8.0 * P,                                  # schismatic (Helmholtz): 384.36
    "pure": lambda P: 1200.0 * math.log(1.25, 2),                        # 5:4 (the baroque hybrid's): 386.31
    "mid": lambda P: (3600.0 - 4.0 * P) / 2.0,                           # the mirror's midpoint: both keys alike, 396.09
    "mean": lambda P: 1200.0 * math.log(math.sqrt(1.25 * 81.0 / 64.0), 2),   # hybridmean's: 397.07
    "pyth": lambda P: 1200.0 * math.log(81.0 / 64.0, 2),                 # Pythagorean: 407.82
}


def chain_bridge(spec):
    """chains/<spec>'s bridge in cents: a CHAIN_BRIDGES name or a number; a
    ValueError past the range in which no fifth is wider than pure."""
    P = 1200.0 * math.log(1.5, 2)
    spec = str(spec).strip().lower()
    if spec in CHAIN_BRIDGES:
        return CHAIN_BRIDGES[spec](P)
    try:
        X = float(spec)
    except ValueError:
        raise ValueError("bad bridge %r: cents, or one of %s" % (spec, ", ".join(CHAIN_BRIDGES)))
    lo, hi = 6000.0 - 8.0 * P, 4.0 * P - 2400.0
    if not (lo - 1e-6 <= X <= hi + 1e-6):
        raise ValueError("bridge %r outside %.2f..%.2f cents (a fifth would be wider than pure)" % (spec, lo, hi))
    return X


class ChainsTuner(HybridMeanTuner):
    """Two chains of pure fifths on pure octaves, the bridge D-F# any third
    from the schismatic to the Pythagorean: `chains/pure@bb` (@ moves chain
    one's start, as every table's @KEY does; the key the chains favour, the
    one whose I, IV and V thirds are the bridge's, is the start's fourth fifth
    up: B-flat's G). At concert pitch."""
    A = 440
    bridge = "pure"

    @classmethod
    def _bridge(cls):
        return chain_bridge(cls.bridge)


_CHAINS = {}

# THE OCTAVES the chains are built on: pure (2:1, for pipes and harpsichords:
# ChainsTuner); a piano's -- every octave on the lower note's 2nd partial by
# path.py's fitted grand model, the fifths pure 3:2 (ChainsPianoTuner); or
# the piano-built middle octave repeated by pure 2:1 (as hybridharm is)
CHAIN_OCTAVES = ("pure", "piano", "middle", "own")
# ("own": each instrument's own strings -- resolved for a part's class to its
#  law's token, chain_law_token; unresolved, a class with no string law, pure)
# THE ROUTE from chain one to chain two, on a piano's octaves (each one of
# path.py's generators made general -- on pure octaves the routes are one):
#   fifth    the bridge third, a fifth up, two stretched octaves down (HybridMeanNotes)
#   fourth   the bridge third, a stretched octave down, a pure fourth down (HybridNotes)
#   octaves  no bridge third: chain two's top down three stretched octaves to
#            chain one (StretchedHelmholtzNotes; on pure octaves, the bridge helm)
CHAIN_ROUTES = ("fifth", "fourth", "octaves")


def chains_tuner(spec, octaves="pure", start=0, route="fifth"):
    """The class for chains/<spec>[/<octaves>[/<route>]]: on pure octaves one
    per spec (moved to a key by in_key, as any table; the octaves route is
    the helm bridge); on a piano's, one per (spec, octaves, route, start) --
    built from that start, since a stretched table moved a few keys up is
    not the same tuning built there."""
    spec = str(spec).strip().lower()
    chain_bridge(spec)
    if octaves == "own":
        octaves = "pure"
    law = None
    if octaves.startswith("b") and "=" in octaves:
        law = _chain_law(octaves)       # (a class's own strings: its law's token)
    elif octaves not in CHAIN_OCTAVES:
        raise ValueError("bad octaves %r in chains/%s/%s: one of %s" % (octaves, spec, octaves, ", ".join(CHAIN_OCTAVES)))
    if route not in CHAIN_ROUTES:
        raise ValueError("bad route %r in chains/%s/%s/%s: one of %s" % (route, spec, octaves, route, ", ".join(CHAIN_ROUTES)))
    if octaves == "pure":
        if route == "octaves":
            spec = "helm"
        key = (spec, "pure", "", 0)
    else:
        key = (spec, octaves, route, start)
    if key not in _CHAINS:
        nm = spec.replace(".", "_").replace("-", "m")
        if octaves == "pure":
            _CHAINS[key] = type("ChainsTuner_%s" % nm, (ChainsTuner,), {"_table": None, "bridge": spec})
        else:
            _CHAINS[key] = type("ChainsPianoTuner_%s_%d_%s_%d" % (nm, len(_CHAINS), route, start), (ChainsPianoTuner,),
                                {"_table": None, "bridge": spec, "start": start, "route": route,
                                 "middle": octaves == "middle", "law": law})
    return _CHAINS[key]


def _chain_shift(s):
    """the semitones a route's generator moves for start s: -6..5, so its
    notes stay in the registers the original tuned them in"""
    return s if s < 6 else s - 12


def _grand_model_B(x):
    """path.py's steinway_inharmonicity_coefficient_func: the fitted grand's
    coefficient, no floor"""
    a, b, c, d, e = 5.22964e-6, 1.21012e-6, 8.3666e-10, -0.007927, 0.429601
    return a + b * x + c * x * x + (d / x) + (e / (x * x))


def chain_law_token(cls):
    """A class's own strings as an octaves token for chains names, or None
    where it has no string law the engines both hold: b<law>[x]=<numbers> --
    law 0 the polynomial (InharmonicStringProperties, floor 27.5 Hz), 1 a
    two-part power law (the upright's, or a measured_B), 2 the electric
    grand's (the polynomial times (long/short)^4); x: the stiff string's law
    exactly (stretch_exact). As native.py exports it (VoiceInit.b_law)."""
    if not (isinstance(cls, type) and issubclass(cls, GrandPianoProperties)):
        return None
    own = next((k.__name__ for k in cls.__mro__ if 'inharmonicity_coefficient_for_frequency' in k.__dict__), None)
    x = "x" if getattr(cls, 'stretch_exact', False) else ""
    r = repr
    if own == 'UprightPianoProperties':
        (wk, wp), (pk, pp) = cls.wound_B, cls.plain_B
        return "b1%s=%s" % (x, ",".join(r(float(v)) for v in (wk, wp, pk, pp, cls.upright_break_hz)))
    if own == 'ElectricGrandProperties' and getattr(cls, 'measured_B', None):
        (wk, wp), (pk, pp), br = cls.measured_B
        return "b1%s=%s" % (x, ",".join(r(float(v)) for v in (wk, wp, pk, pp, br)))
    if own in ('InharmonicStringProperties', 'ElectricGrandProperties') and \
            getattr(cls, 'inharmonicity_floor_hz', 27.5) == 27.5:
        p = [cls.a, cls.b, cls.c, cls.d, cls.e]
        if own == 'ElectricGrandProperties':
            return "b2%s=%s" % (x, ",".join(r(float(v)) for v in p + [cls.scale_constant_hz_m, cls.reference_string_max_m,
                                                                         cls.case_string_max_m]))
        return "b0%s=%s" % (x, ",".join(r(float(v)) for v in p))
    return None


def _chain_law(tok):
    """a law token's (B(x), exact): the arithmetic of native/voice.c law_B"""
    try:
        head, nums = tok.split("=", 1)
        v = [float(t) for t in nums.split(",")]
        kind, exact = int(head[1]), head.endswith("x")
    except (ValueError, IndexError):
        raise ValueError("bad octaves %r: b<0|1|2>[x]=<numbers>" % tok)
    if kind == 1 and len(v) == 5:
        wk, wp, pk, pp, br = v
        return (lambda x: wk * float(x) ** wp if x < br else pk * float(x) ** pp), exact
    if kind in (0, 2) and len(v) == (5 if kind == 0 else 8):
        a, b, c, d, e = v[:5]

        def B(x):
            xl = max(float(x), 27.5)
            y = a + b * xl + c * xl * xl + (d / xl) + (e / (xl * xl))
            if kind == 2:
                f = max(float(x), 1e-6)
                long_, short = min(v[5] / f, v[6]), min(v[5] / f, v[7])
                y = y * (long_ / short) ** 4
            return y
        return B, exact
    raise ValueError("bad octaves %r: b<0|1|2>[x]=<numbers>" % tok)


class _ChainNotes:
    """path.py's Notes and Note.rel_tune, its arithmetic exactly, the octave
    law the caller's: B(x) and the first-order 2nd partial (path's) or the
    stiff string's exactly"""
    def __init__(self, law=None, exact=False):
        self.f = [None] * 150
        self.B = law or _grand_model_B
        self.exact = exact

    def ratio(self, coeff):
        if self.exact:
            return 2 * math.sqrt((1.0 + 4.0 * coeff) / (1.0 + coeff))
        return 2 * (1.0 + 0.5 * (2 ** 2 - 1) * coeff)

    def at(self, n, f):
        if self.f[n] is None:
            self.f[n] = float(f)

    def tune(self, child, parent, n, d, inh=False):
        if inh:
            base = float(self.f[parent]) * n / d
            if n >= d:
                f = base * (self.ratio(self.B(self.f[parent])) / 2)
            else:
                f = base / (self.ratio(self.B(base)) / 2)
        else:
            f = float(self.f[parent]) * n / d
        self.at(child, f)
        return child

    def fill(self, low=12, high=127):
        """HybridMeanNotes.init_octaves: up first, then down"""
        for n in range(low, high + 1):
            if self.f[n] is None and n - 12 >= 0 and self.f[n - 12] is not None:
                self.tune(n, n - 12, 2, 1, True)
        for n in range(high, low - 1, -1):
            if self.f[n] is None and self.f[n + 12] is not None:
                self.tune(n, n + 12, 1, 2, True)


def _chain_gen(spec, s, route, law=None):
    """the generator's {key: Hz} (before the reference) for a route from start
    s: path.py's generators' steps, moved by _chain_shift, on the octaves of
    law ((B(x), exact); None the fitted grand's, as path.py)"""
    g = _ChainNotes(*(law or (None, False)))
    T = g.tune
    if route == "fifth":                # HybridMeanNotes: chain one from C3 (s = 0)
        d = _chain_shift(s)
        n0 = 48 + d
        g.at(n0, 440.0 * 2 ** ((3 + d) / 12.0) / 4)
        for k in range(5):
            T(n0 + 7 * (k + 1), n0 + 7 * k, 3, 2)
        g.at(n0 + 18, g.f[n0 + 14] * _chain_ratio(spec))      # the bridge: position 2 up a third
        T(n0 + 25, n0 + 18, 3, 2)                               # a fifth up, two stretched octaves down
        T(n0 + 13, n0 + 25, 1, 2, True)
        T(n0 + 1, n0 + 13, 1, 2, True)
        for k in range(4):
            T(n0 + 1 + 7 * (k + 1), n0 + 1 + 7 * k, 3, 2)
        g.fill()
    elif route == "octaves":            # StretchedHelmholtzNotes: chain two from C#3 (s = 0)
        d = _chain_shift(s)
        c = 49 + d
        g.at(c, 440.0 * 2 ** ((-20 + d) / 12.0))
        T(c - 7, c, 2, 3)
        for _ in range(5):
            c = T(c + 7, c, 3, 2)
        for _ in range(3):
            c = T(c - 12, c, 1, 2, True)
        for _ in range(5):
            c = T(c + 7, c, 3, 2)
        g.fill()
    else:                               # HybridNotes: around the bridge's C4 (s = B-flat)
        d = _chain_shift((s + 2) % 12)
        C = 60 + d
        g.at(C, 440.0 * 2 ** ((3 + d) / 12.0) / 2)
        T(C - 7, C, 2, 3); T(C - 14, C - 7, 2, 3)               # F3, B-flat2
        T(C + 7, C, 3, 2); T(C + 14, C + 7, 3, 2); T(C + 21, C + 14, 3, 2)     # G4, D5, A5
        T(C + 12, C, 2, 1, True); T(C - 12, C, 1, 2, True)
        T(C + 5, C - 7, 2, 1, True); T(C + 17, C + 5, 2, 1, True)               # F4, F5
        T(C - 2, C - 14, 2, 1, True); T(C + 10, C - 2, 2, 1, True)              # B-flat3, 4
        T(C - 5, C + 7, 1, 2, True); T(C + 19, C + 7, 2, 1, True)               # G3, G5
        T(C + 2, C + 14, 1, 2, True); T(C - 10, C + 2, 1, 2, True)              # D4, D3
        T(C + 9, C + 21, 1, 2, True); T(C - 3, C + 9, 1, 2, True)               # A4, A3
        if spec == "pure":
            T(C + 4, C, 5, 4)                                   # (the bridge as HybridNotes writes it, to the bit)
        else:
            g.at(C + 4, g.f[C] * _chain_ratio(spec))
        T(C - 8, C + 4, 1, 2, True)                             # E3
        T(C - 13, C - 8, 3, 4)                                  # B2, a pure fourth down
        T(C - 6, C - 13, 3, 2); T(C + 1, C - 6, 3, 2); T(C + 8, C + 1, 3, 2); T(C + 15, C + 8, 3, 2)
        T(C + 16, C + 4, 2, 1, True)                            # E5
        T(C - 1, C - 13, 2, 1, True); T(C + 11, C - 1, 2, 1, True)              # B3, B4
        T(C + 6, C - 6, 2, 1, True); T(C + 18, C + 6, 2, 1, True)               # F#4, F#5
        T(C + 13, C + 1, 2, 1, True); T(C - 11, C + 1, 1, 2, True)              # C#5, C#3
        T(C + 20, C + 8, 2, 1, True); T(C - 4, C + 8, 1, 2, True)               # G#5, G#3
        T(C + 3, C + 15, 1, 2, True); T(C - 9, C + 3, 1, 2, True)               # D#4, D#3
        for n in [47, 46] + list(range(48, 58)):                # HybridNotes.init_octaves_low
            T(n + d - 24, T(n + d - 12, n + d, 1, 2, True), 1, 2, True)
        T(57 + d - 36, 57 + d - 24, 1, 2, True)
        for n in [70, 71] + list(range(72, 82)):                # ...and _high
            T(n + d + 24, T(n + d + 12, n + d, 2, 1, True), 2, 1, True)
        for n in (70, 71, 72):
            T(n + d + 36, n + d + 24, 2, 1, True)
    return {n: float(f) for n, f in enumerate(g.f) if f}


class ChainsPianoTuner(PathTuner):
    """Two chains of pure 3:2 fifths on a piano's stretched octaves, any
    bridge, start and route (_chain_gen); middle: its octave from C4
    repeated by pure 2:1, as HybridHarmonicTuner does. chains/mean/piano@c
    is hybridmeanpiano; chains/pure/piano/fourth@bb, hybrid440;
    chains/helm/piano/octaves@c, stretchedhelmholtz; chains/pure/middle/
    fourth@bb, hybridharm440."""
    A = 440
    bridge = "mean"
    start = 0
    route = "fifth"
    middle = False
    law = None                          # ((B(x), exact): a class's own strings; None the fitted grand's)

    @classmethod
    def _build_table(cls):
        table = _chain_gen(cls.bridge, cls.start, cls.route, cls.law)
        ref = _REFERENCE if _REFERENCE is not None else (69, cls.A)
        if table.get(ref[0]):
            k = float(ref[1]) / table[ref[0]]
            table = {n: f * k for n, f in table.items()}
        if cls.middle and all(60 + i in table for i in range(12)):
            c4 = table[60]
            r = [table[60 + i] / c4 for i in range(12)]
            table = {n: c4 * r[(n - 60) % 12] * 2.0 ** ((n - 60 - (n - 60) % 12) // 12) for n in range(128)}
        return table


def _chain_ratio(spec):
    """the bridge third as a ratio: the mean as HybridMeanNotes writes it (to
    the bit), the others from their cents"""
    if spec == "mean":
        return (80.0 * 81.0) ** 0.5 / 64.0
    return 2.0 ** (chain_bridge(spec) / 1200.0)


class HybridMeanPianoTuner(PathTuner):
    """hybridmean for a piano: the same chains and mean-3rd bridge, built in
    path.py (HybridMeanNotes) with every octave on the string's 2nd partial,
    by the Steinway B model.

    The stretched octaves take part of the comma themselves -- the circle of
    fifths spans seven octaves, and each cent of stretch is a cent the fifths
    need not lose. The bridge reaches chain two the long way round (Ben's
    path), F#4 up a 5th to C#5 and down two stretched octaves, so they take
    more of it: in the middle the two tempered fifths ease from -12.7 and
    -10.8 to about -8.7 and -7.3, the Pythagorean thirds drop toward +19, the
    eight bridged ones draw together at +10.8 to +12.6, and the whole sits
    2.4 cents RMS from a stretched equal temperament. The treble follows the
    Steinway stretch.

    A harpsichord's octaves stretch 0.1 cent: use hybridmean. A = 440, as a
    piano is; `:415` for a baroque one.
    """
    A = 440
    generator_name = "HybridMeanNotes"


class PleyelTuner(PathTuner):
    """THE PLEYEL TEMPERAMENT on a Pleyel's own strings (pleyel.py: Cordier's
    reconstruction of the French aural procedure -- the partition's thirds and
    sixths beating at the textbook rates, the sixth Ab-F like the third Db-F,
    10ths up, beatless octaves down) worked for the inharmonicity of
    tonelib.PleyelProperties, the 1840s grand: what a Paris tuner of Chopin's
    day would have left on that piano. A = 435, the pitch McNulty restored
    Chopin's last Pleyel to, set as the procedure sets it: the fork's A3 at
    217.5 (a reference given on the command line rescales it)."""
    A = 435
    # (the fork sets A3, the French LA2, as the procedure starts: its A4 is
    # then a 10th's work, a stretched octave above -- the fork's key, and its
    # pitch as a share of A)
    fork_note, fork_share = 57, 0.5

    _raw = None

    @classmethod
    def raw_table(cls):
        """The procedure's table before any pitch is set (native/tunertables.h
        holds it as it comes: examples/tuner_tables.py). Worked out once: a
        reference change rebuilds the table, not the procedure."""
        if PleyelTuner._raw is None:
            PleyelTuner._raw = PleyelTuner._solve()
        return dict(PleyelTuner._raw)

    @staticmethod
    def _solve():
        import pleyel
        import tonelib as _T
        p = _T.PleyelProperties
        B = lambda f: p.a + p.b * f + p.c * f * f + p.d / f + p.e / (f * f)
        return pleyel.tune(B, a4=440.0)

    @classmethod
    def _build_table(cls):
        ref = _REFERENCE if _REFERENCE is not None else (cls.fork_note, cls.A * cls.fork_share)
        table = cls.raw_table()
        if table.get(ref[0]):
            s = float(ref[1]) / table[ref[0]]
            table = {n: f * s for n, f in table.items()}
        return table


class StretchedHelmholtzTuner(PathTuner):
    """Ben's StretchedHelmholtz: two chains of pure 5ths, F#2-C6 and C3-B5,
    joined only by three inharmonic octaves, C6 back to C3 (path.py). On pipes
    it would be Pythagorean with the comma on B-F#; on a piano the stretched
    octaves of the wrap take part of it. Measured at C4 on the Steinway
    model: A, E, B and D major thirds within 5 cents of pure, B-F# the one
    tempered fifth (-15.6), the other thirds about +19. For music on the sharp
    side and in D, where F and Bb majors matter less. A = 440.
    """
    A = 440
    generator_name = "StretchedHelmholtzNotes"


class Hybrid440Tuner(HybridTuner):
    """The hybrid temperament at MODERN pitch.

    Same temperament, same stretched octaves, A4 at 440 instead of 415 -- and
    it exists because the temperament and the reference pitch are separate
    questions that were being answered by one attribute. `hybrid` is the tuner
    verified by ear for baroque, and it should stay at baroque pitch; but a
    great deal of what gets rendered here is not baroque, and those renders
    want this temperament at concert pitch rather than equal temperament or a
    semitone flat.

    A temperament is a set of RATIOS between the notes. Where A sits is a
    separate decision about the ensemble, and a modern instrument playing a
    well-tempered scale is not a contradiction -- it is most pianos.
    """
    A = 440


class HybridHarmonic440Tuner(HybridHarmonicTuner):
    """The pure-octave hybrid at modern pitch. See Hybrid440Tuner.

    For a mode-locked pipe on a modern organ, which is most organs a listener
    will have heard: an instrument built or restored to A440 is not thereby
    equal-tempered.
    """
    A = 440

class SpiralTuner(PathTuner):
    generator_name = "SpiralNotes"


class SemiTuner(PathTuner):
    generator_name = "SemiNotes"


class PathNotesTuner(PathTuner):
    generator_name = "PATHNotes"
    generator_args = (True, True)   # use_inharmonicity, temper_thirds


class PythagoreanRatio:
    def __init__(self, numerator, denominator = 1):
        self.n = int(numerator)
        self.d = int(denominator)
        
    def __str__(self):
        return "%i/%i" % (self.n, self.d)
        
    def __float__(self):
        return float(self.n) / self.d
        
    def __eq__(self, other):
        return self.n == other.n and self.d == other.d 
        #return float(self) == float(other)

class EqualIntervals:
    def __init__(self, notes_per_octave = 12, min_octaves = 5, proximity_cents = 5):
        self.npo = float(notes_per_octave)
        self.min_octaves = min_octaves
        self.proximity_cents = proximity_cents
        self.noteRatios = {}
        self.harmonicNotes = {}
        self.init()
        
    def __str__(self):
        s = ""
        for n in sorted(self.noteRatios):
            s += "%s: %s\n" % (n, ", ".join(str(i) for i in self.noteRatios[n])) 
        return s
        
    def addRatio(self, n, i):
        if n not in self.noteRatios:
            self.noteRatios[n] = []
            
        if i not in self.noteRatios[n]:
            self.noteRatios[n].append(i)
    
    def addHarmonicNote(self, h, n):
        if h not in self.harmonicNotes:
            self.harmonicNotes[h] = n
            
    def getRatios(self, n):
        o = 0
        while not n in self.noteRatios and n >= 0:
            n -= 12
            o += 1
        
        if n >= 0:
            if o > 0:
                return [PythagoreanRatio(r.n * 2 ** o, r.d) for r in self.noteRatios[n]]
            else:
                return self.noteRatios[n]
        else:
            raise IndexError("No ratio found.")
        
    def getHarmonicNote(self, h):
        if h in self.harmonicNotes:
            return self.harmonicNotes[h]
        else:
            return 0
        
    def init(self):
        hn = 1
        min_h = 2 ** self.min_octaves
        populated = False
        while not populated or hn < min_h:        
            hd = hn
            while hd > 0 and not populated:
                equal_n = ratio2EqualNote(self.npo, PythagoreanRatio(hn, hd))
                n = int(equal_n + .5)
                if abs(equal_n - n) * 100 > self.proximity_cents:
                    hd -= 1
                    continue
                
                self.addRatio(n, PythagoreanRatio(hn, hd))
                if hd == 1:
                    self.addHarmonicNote(hn, n)
                
                hd -= 1
            
                populated = True
                for n in range(0, 12):
                    try:
                        self.getRatios(n + 12 * max(self.min_octaves, 5))
                    except IndexError:
                        populated = False
                        break
                
            hn += 1
    

class SearchComplete: pass
class MaxIterationsReached: pass

class Tuner:
    _harmonic_cache = {}

    def __init__(self, sustain = None, notes_per_octave = 12, max_octaves = 4):
        self.sustain = sustain
        self.sustainMap = dict(self.sustain) if self.sustain else {}
        self.npo = float(notes_per_octave)
        self.max_octaves = max_octaves
        self._init_harmonics()
        self.notes = []
        self.intervals = None

        self.solutions = []        
        self.solution = None
        self.last_solution = None
        
    def getRatios(self):
        if self.solution:
            return self.solution.list_ratios()
        else:
            return []
        
    _result_cache = {}

    def _cache_key(self):
        # Sustained notes anchor the solution, so identical note sets in
        # different sustain contexts produce different frequencies; the key
        # must include the intersecting sustain or cache hits teleport the
        # whole chord to frequencies from an unrelated moment.
        notes = tuple(self.generate_notes())
        note_set = set(notes)
        sustained = tuple(
            (note, round(f, 4))
            for note, f in (self.sustain or [])
            if note in note_set
        )
        return (notes, sustained)

    def in_cache(self):
        return self._cache_key() in self._result_cache

    def noteFrequencies(self):
        lookup_key = self._cache_key()

        if lookup_key in self._result_cache:
            return self._result_cache[lookup_key]
        else:
            if self.solution:
                result = self.solution.noteFrequencies()
                self._result_cache[lookup_key] = result
                return result
            else:
                return []
        
    def _init_harmonics(self):
        if (self.npo, self.max_octaves) in self._harmonic_cache:
            self.harmonics = self._harmonic_cache[(self.npo, self.max_octaves)]
        else:
            self.harmonics = EqualIntervals(self.npo, self.max_octaves)
            self._harmonic_cache[(self.npo, self.max_octaves)] = self.harmonics
            errlog(self.harmonics)
            
        for n in range(0, 12 * (self.max_octaves + 2) + 1):
            errlog(("%i: " % n) + ", ".join(str(ratio) for ratio in self.harmonics.getRatios(n)))
        
    def addNote(self, note):
        self.notes.append(int(note))
            
    def generate_notes(self):
        return (note for note in sorted(self.notes))

    class Interval:
        def __init__(self, tuner, top, bottom, interval, ratios):
            self.tuner = tuner
            self.top = top
            self.bottom = bottom
            
            self.interval = self.top - self.bottom
            self.ratios = self.tuner.harmonics.getRatios(self.interval)
            
        def __str__(self):
            return ("%i - %i = %i: " % (self.top, self.bottom, self.interval)) + ", ".join("%s (-%i)" % (ratio, self.tuner.harmonics.getHarmonicNote(ratio.d) - self.bottom) for ratio in self.ratios)
            
    
    class Graph:
        def __init__(self, tuner, base_note = None):
            self.tuner = tuner
            self.base_note = base_note
            self.root = self.tuner.IntervalNode(tuner, None, -1, None)
            self.iterator = self.crawler()
        
        def crawler(self):
            for i in self.root.iterator:
                yield i
        
        def __str__(self):
            return str(self.root)
    
    class Solution:
        def __init__(self, node):
            self.node = node
            self.ratios = None
            
        def generate_ratios(self):
            parent = self.node
            while parent:
                if parent.ratio:
                    yield parent.ratio
                parent = parent.parent
        
        def list_ratios(self):
            if not self.ratios:
                self.ratios = list(reversed(list(self.generate_ratios())))
                
            return self.ratios
        
        def noteFrequencies3(self):
            ratios = self.list_ratios()
            notes = sorted(self.node.tuner.notes)
            tuned = EvenTuner()
            tuned.notes = notes
            bass_note = notes[0]

        

        def noteFrequencies(self):
            ratios = self.list_ratios()
            notes = sorted(self.node.tuner.notes)
            
            bass_frequency = None
            
            if self.node.tuner.sustain:
                #errlog("sustain")
                #errlog(self.node.tuner.sustain)
                sustained = [
                    (note, f)
                    for note, f
                    in self.node.tuner.sustain
                    if (note in notes)
                ]
            else:
                sustained = None
            #errlog("sustained %s" % (sustained))
            if sustained:
                # notes are sustained
                # Tune the bass so that the lowest sustained note sustains its pitch
                lowest_sustained_note, lowest_sustained_f = sustained[0]
                #errlog("lowest_sustained %s" % str(sustained[0]))
                bass_ratio = 1.0 / 1.0
                #errlog(ratios)
                r = [PythagoreanRatio(1, 1)]
                r.extend(ratios)
                for ratio, note in zip(r, notes):
                    #errlog("ratio, note = %s, %s" % (str(ratio), str(note)))
                    bass_ratio = bass_ratio * ratio.n / ratio.d
                    #errlog("bass_ratio = %s" % (str(bass_ratio)))
                    if lowest_sustained_note == note:
                        bass_frequency = lowest_sustained_f / bass_ratio
                        #errlog("adjusted bass_frequency: %s" % (bass_frequency))
                        #if bass_ratio != 1.0:
                        #    import sys
                        #    sys.exit()
                        break
            
            if not bass_frequency:
                # notes are not sustained
                # Tune the bass as a harmonic of the Pythagorean tuning of its fundamental.
                bass_d = ratios[0].d
                bass_note = notes[0]
                fundamental = bass_note - self.node.tuner.harmonics.getHarmonicNote(bass_d)
                bass_tuner = PythTuner()
                bass_tuner.C = 256.0
                bass_tuner.addNote(fundamental)
                #errlog(bass_tuner.noteFrequencies())
                #errlog(fundamental)
                fundamental_frequency = dict(bass_tuner.noteFrequencies())[fundamental]
                bass_frequency = fundamental_frequency * bass_d
            
            tones = [float(bass_frequency)]
            for ratio in ratios:
                #print ratio
                tones.append(tones[-1] * ratio.n / ratio.d)
                
            #if sustained:
            #    d = dict(zip(notes, tones))
            #    d.update(dict(sustained))
            #    tones = sorted(d.values())
            
            return list(zip(notes, tones))
            
            
        def __str__(self):
            return "ratios: %s\nfundamentals: %s\n" % (" to ".join(str(ratio) for ratio in self.list_ratios()), str(self.node.fundamentals))
            
            
    
    class IntervalNode:
        def __init__(self, tuner, parent, parent_depth, ratio):
            self.tuner = tuner
            self.parent = parent
            self.fundamentals = self.parent.fundamentals.copy() if self.parent else {}
            #self.fundamentals = set(self.parent.fundamentals) if self.parent else set()
            self.depth = parent_depth + 1
            self.ratio = ratio
            if self.ratio:
                fundamental = self.tuner.harmonics.getHarmonicNote(self.ratio.d) - self.parent.child_interval.bottom
                if fundamental not in self.fundamentals:
                    self.fundamentals[fundamental] = self.ratio.d
            #print self.depth
            #print self.tuner.list_intervals()
            self.sustainCount = None
            self.iterator = self.crawler()
        
        def crawler(self):
            if len(self.tuner.list_intervals()) > self.depth:
                self.child_interval = self.tuner.list_intervals()[self.depth]
                
                if self.sustainCount is None:
                    self.intersectedNotes = set(self.tuner.sustainMap.keys()) & set(self.tuner.notes)
                    self.sustain = [(note, self.tuner.sustainMap[note]) for note in sorted(self.tuner.notes) if note in self.intersectedNotes]
                    self.sustainMap = dict(self.sustain)
                    self.sustainCount = len(self.intersectedNotes)
                
                #errlog("intersectedNotes: %s" % str(self.intersectedNotes))
                #errlog("sustain         : %s" % str(self.sustain))
                #errlog("sustainMap      : %s" % str(self.sustainMap))
                
                sustainBottom = None
                if self.sustainCount > 1 and self.child_interval.top in self.intersectedNotes:
                    sustainTop = (self.child_interval.top, self.sustainMap[self.child_interval.top])
                    #errlog("sustainTop      : %s" % str(sustainTop))
                    for note, f in self.sustain:
                        if note == sustainTop[0]:
                            break
                        else:
                            sustainBottom = (note, f)
                            #errlog("sustainBottom   : %s" % str(sustainBottom))
    
                if sustainBottom:
                    sustainTopNote, sustainTopFrequency = sustainTop
                    sustainBottomNote, sustainBottomFrequency = sustainBottom
                    sustainRatio = float(sustainTopFrequency) / sustainBottomFrequency

                    #errlog("SustainRatio    : %s" % str(sustainRatio))
                    
                    sustainRatioDiff = 1.0
                    bottomInterval = self
                    while bottomInterval and bottomInterval.child_interval and bottomInterval.child_interval.top != sustainBottomNote:
                        #errlog(bottomInterval.child_interval.top)
                        #errlog(bottomInterval.child_interval.bottom)
                        if bottomInterval.ratio:
                            sustainRatioDiff = sustainRatioDiff * bottomInterval.ratio.n / bottomInterval.ratio.d
                        bottomInterval = bottomInterval.parent
                    #errlog("SustainRatioDiff: %s" % str(sustainRatio))
                         
                    possibleRatios = []
                    for ratio in self.child_interval.ratios:
                        #errlog(str(float(ratio.n) / ratio.d) + " == " + str(sustainRatio / sustainRatioDiff))
                        if float(ratio.n) / ratio.d == sustainRatio / sustainRatioDiff:
                            possibleRatios.append(ratio)
                    
                    #errlog("possibleRatios  : %s" % ", ".join(str(ratio) for ratio in possibleRatios))
                    
                    if not possibleRatios:
                        # this happens when the comma drifts too much -- this helps reset the comma
                        possibleRatios = self.child_interval.ratios
                        #errlog("possibleRatios  : %s" % ", ".join(str(ratio) for ratio in possibleRatios))
                    
                    #import sys
                    #sys.exit()
                    
                    for ratio in possibleRatios:
                        child = self.tuner.IntervalNode(self.tuner, self, self.depth, ratio)
                        for product in child.iterator:
                            yield product
                    
                else:
                    
                    better_ratios = []
                    worse_ratios = []
                    
                    for ratio in self.child_interval.ratios:
                        if self.parent:
                            fundamental = self.tuner.harmonics.getHarmonicNote(ratio.d) - self.parent.child_interval.bottom
                            if fundamental in self.fundamentals:
                                better_ratios.append(ratio)
                            else:
                                worse_ratios.append(ratio)
                        else:
                            worse_ratios.append(ratio)
                    
                    for ratio in better_ratios:
                        child = self.tuner.IntervalNode(self.tuner, self, self.depth, ratio)
                        for product in child.iterator:
                            yield product
                            
                    for ratio in worse_ratios:
                        child = self.tuner.IntervalNode(self.tuner, self, self.depth, ratio)
                        for product in child.iterator:
                            yield product
                                            
            else:
                self.child_interval = None
                self.children = None
                self.tuner.solutions.append(self.tuner.Solution(self))
                yield True
            
            
        def indent(self):
            return "\n" + "\t" * self.depth
            
        def __str__(self):
            if self.child_interval:
                return "%sratio: %s%sfundamentals: %s%schild_interval: %s%schildren: %s" % (self.indent(), str(self.ratio), self.indent(), str(self.fundamentals), self.indent(), str(self.child_interval), self.indent(), self.indent()  .join(str(child) for child in self.children) if self.children else "")
            else:
                return "%sratio: %s%sfundamentals: %s" % (self.indent(), str(self.ratio), self.indent(), str(self.fundamentals))
    
    def generate_intervals(self):
        notes = self.generate_notes()
        bottom = next(notes)
        try:
            while True:
                top = next(notes)
                
                interval = top - bottom
                ratios = self.harmonics.getRatios(interval)
                yield Tuner.Interval(self, top, bottom, interval, ratios)
                
                bottom = top
        except StopIteration:
            pass
            
    def list_intervals(self):
        if not self.intervals:
            self.intervals = list(self.generate_intervals())
        return self.intervals
            

    #shortest = lambda self, s: len(s.node.fundamentals)
    closest = lambda self, s: sum(s.node.fundamentals.values())
    
    def update_solution(self):
            #shorter_solutions = sorted(self.solutions, key=self.shortest)
            #short_len = len(shorter_solutions[0].node.fundamentals)
            #shortest_solutions = [solution for solution in shorter_solutions if len(solution.node.fundamentals) <= short_len]
            #closer_solutions = sorted(shortest_solutions, key=self.closest)
            self.solutions.sort(key=self.closest)
            self.last_solution = self.solution
            self.solution = self.solutions[0]

            if self.solution is not self.last_solution:
                errlog("New solution found.")
                #  we only need to keep around the best
                self.solutions = [self.solution]
                return True
            else:
                return False
    
    _best_solution_cache = {}
    
    def producer(self, step = 1000, max_i = 10000):
        #lookup_key = tuple(self.generate_notes())
        
        #if lookup_key in self._best_solution_cache:
        #    errlog("Found best solution in cache")
        #    yield self._best_solution_cache[lookup_key]
        #    yield SearchComplete
        #    return
        
        if verbose:
            errlog("Harmonic table initialized.")
            for interval in self.generate_intervals():
                errlog(interval)
            
        if len(self.notes) == 1:
            self.solution = Tuner.Solution(Tuner.IntervalNode(self, None, -1, None))
            self.solution.ratios = [PythagoreanRatio(1, 1)]
            yield self.solution
            yield SearchComplete
            return
            
        self.graph = self.Graph(self)
        errlog("Solution tree initialized.")
       
        i = 0
        for iteration in self.graph.iterator:
            i += 1
            if max_i and i > max_i:
                yield MaxIterationsReached
                break
                
            if i % step == 0:
                if verbose: errlog("Solutions searched: " + str(i))
                changed = self.update_solution()
                if changed:
                    #self._best_solution_cache[lookup_key] = self.solution
                    yield self.solution  
                    
        changed = self.update_solution()
        if changed:
            #self._best_solution_cache[lookup_key] = self.solution
            yield self.solution  
        yield SearchComplete
    
    def tune(self, step = 1000, max_i = 10000):
        p = self.producer(step, max_i)
        for solution in p:
            if solution is SearchComplete:
                errlog("Search complete.")
            elif solution is MaxIterationsReached:
                errlog("Max iterations reached.")
            else:
                if verbose: errlog("Best solution so far: " + str(solution))

