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
from inharmonicity import *

def note2EqualRatio(npo, note):
    return 2 ** (float(note) / npo)    

def ratio2EqualNote(npo, r):
    from math import log
    #print r, npo
    return log(float(r)) * npo / log(2)


class BaseTuner:
    A = 440

    def in_cache(self):
        return False

    def __init__(self, sustain = None, notes_per_octave = 12, min_octaves = 5):
        self.npo = float(notes_per_octave)
        self.C = float(self.A) / self.note2Ratio(9)
        
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
    A = 415
    
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
# tonelib.Steinway renders its partials with (identical a,b,c,d,e) -- so an octave
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
        if cls._table is None:
            cls._table = cls._build_table()

    @classmethod
    def _build_table(cls):
        gen = getattr(_load_path_module(), cls.generator_name)(*cls.generator_args)
        table = {n: float(note.f) for n, note in enumerate(gen.notes)
                 if getattr(note, "f", None)}
        if cls.A is not None and table.get(69):
            s = float(cls.A) / table[69]
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
        base = self.A or 440.0
        return float(base) * 2.0 ** ((midi - 69) / 12.0)

    def noteFrequencies(self):
        mc = type(self).middle_c
        return [(note, self._freq(note + mc)) for note in sorted(self.notes)]


class HybridTuner(PathTuner):
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
        base = HybridTuner._build_table()
        if 60 not in base:
            return base
        ref = {i: base[60 + i] / base[60] for i in range(12) if 60 + i in base}
        if len(ref) < 12:
            return base
        c4 = base[60]
        return {n: c4 * ref[(n - 60) % 12] * (2.0 ** ((n - 60 - ((n - 60) % 12)) // 12))
                for n in range(128)}


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

