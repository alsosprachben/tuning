#!/usr/bin/env python3
"""Sung vowels: the phoneme a syllable holds, and the formants that make it.

A vowel IS a formant triple -- that is the whole of what distinguishes our
"aah" from our "ooh" -- so a choir that knows its text can sing the text. This
module is the front half: text to vowel. tonelib's _VocalBody is the back half,
vowel to sound, and it already transposes any vowel to any body, so a boy
singing /i/ falls out of the two together with no extra work.

WHY THESE THREE LANGUAGES. Ecclesiastical Latin and Italian share one
five-vowel system and are very nearly phonetic -- the spelling tells you the
sound, which is exactly what English does not do. German is close behind: more
vowels, including the front-rounded pair, but still regular. English would need
a pronouncing dictionary and is deliberately not attempted here.

WHAT A SYLLABLE GIVES A NOTE. Its NUCLEUS, and only that. A singer holds the
vowel for the note's length and puts the consonants around it -- before the
beat at the front, at the very end at the back -- so for the purpose of
choosing formants a syllable is its vowel and nothing else. A diphthong
resolves to its FIRST element for the same reason: "mein" is held on /a/ and
only turns toward /i/ as it leaves.

Formant values are the Peterson & Barney measurement set where they overlap
with it (which is where tonelib's existing three came from -- /u/ and /e/ are
its values exactly), extended with the standard continental vowels.
"""

# (F1, F2, F3) in Hz, for an adult male tract. _VocalBody scales these to
# whatever body is singing.
# (centre, bandwidth, amplitude) per formant, for an adult male tract --
# tonelib's _VocalBody scales all of it to whatever body is singing. Centres
# are Peterson & Barney where they overlap it; bandwidths widen with openness
# and the upper formants weaken as the vowel closes, which is why "oo" is dark.
VOWELS = {
    'a': ((730.0, 130.0, 1.00), (1090.0,  90.0, 0.55), (2440.0, 130.0, 0.22)),
    'E': ((530.0, 120.0, 1.00), (1840.0, 220.0, 0.55), (2480.0, 260.0, 0.25)),
    'e': ((390.0, 110.0, 1.00), (2100.0, 240.0, 0.50), (2600.0, 260.0, 0.22)),
    # /i/ lives on the WIDTH of the F1-F2 gap -- lowest F1 of any vowel,
    # highest F2, and F3 close above it so the two read as one bright
    # cluster. Pushed a little past the textbook values, which are an
    # average over speakers rather than a clear sung 'ee'.
    # A FORMANT MUST BE WIDER THAN THE HARMONIC SPACING or it can fall
    # BETWEEN two harmonics and simply not sound: at 110 Hz wide, F2 here
    # covered 2465-2575 while an F4 puts its harmonics at 2443 and 2792,
    # and the /i/ lost its F2 altogether. Real voices are saved from this
    # by vibrato and by a section never agreeing on the pitch; a synthetic
    # one has to be told.
    'i': ((250.0, 110.0, 1.00), (2520.0, 260.0, 0.62), (3150.0, 280.0, 0.30)),
    'O': ((570.0, 110.0, 1.00), ( 840.0, 100.0, 0.50), (2410.0, 140.0, 0.16)),
    'o': ((400.0,  95.0, 1.00), ( 750.0, 100.0, 0.46), (2400.0, 140.0, 0.14)),
    'u': ((300.0,  90.0, 1.00), ( 870.0, 100.0, 0.42), (2240.0, 140.0, 0.12)),
    'y': ((300.0, 110.0, 1.00), (1750.0, 220.0, 0.40), (2200.0, 240.0, 0.14)),
    'P': ((400.0, 110.0, 1.00), (1550.0, 210.0, 0.45), (2200.0, 240.0, 0.16)),
    '@': ((500.0, 120.0, 1.00), (1500.0, 110.0, 0.45), (2500.0, 140.0, 0.18)),
    'A': ((600.0, 130.0, 1.00), (1300.0, 110.0, 0.48), (2500.0, 140.0, 0.18)),
    # /ʌ/ -- the "u" in "sun". Holst's manuscript of Neptune gave his offstage
    # chorus no vowel at all; Imogen Holst added "Sing throughout to the sound
    # of 'u' in 'sun'" for the 1971 Faber revision, from memory of her father's
    # rehearsals and matching what he had written for the hidden choir in
    # Savitri. It is neither "ah" nor "oo", which are the two things a wordless
    # chorus usually gets rendered as.
    'V': ((640.0, 120.0, 1.00), (1190.0, 200.0, 0.52), (2390.0, 250.0, 0.20)),
}

# Digraphs first, longest match wins. The value is the HELD vowel.
LATIN = [('ae', 'E'), ('oe', 'E'), ('au', 'a'), ('eu', 'E'), ('qu', None),
         ('y', 'i'), ('a', 'a'), ('e', 'E'), ('i', 'i'), ('o', 'O'), ('u', 'u')]

ITALIAN = [('ai', 'a'), ('au', 'a'), ('ei', 'E'), ('eu', 'E'), ('ia', 'a'),
           ('ie', 'E'), ('io', 'O'), ('iu', 'u'), ('oi', 'O'), ('ua', 'a'),
           ('ue', 'E'), ('ui', 'u'), ('uo', 'O'),
           ('a', 'a'), ('e', 'E'), ('i', 'i'), ('o', 'O'), ('u', 'u')]

GERMAN = [('ei', 'a'), ('ai', 'a'), ('eu', 'O'), ('au', 'a'),
          ('ie', 'i'), ('ah', 'a'), ('eh', 'e'), ('ih', 'i'), ('oh', 'o'),
          ('uh', 'u'), ('aa', 'a'), ('ee', 'e'), ('oo', 'o'),
          ('ae', 'E'), ('oe', 'P'), ('ue', 'y'),
          ('ä', 'E'), ('ö', 'P'), ('ü', 'y'),
          ('a', 'a'), ('e', 'E'), ('i', 'i'), ('o', 'O'), ('u', 'u')]

RULES = {'latin': LATIN, 'italian': ITALIAN, 'german': GERMAN}


# The tract shape a consonant is RELEASED from, by place of articulation --
# the classic formant "locus". The vowel is approached from here rather than
# arrived at from nowhere, and the direction F2 travels out of the constriction
# is a primary cue to which consonant it was: a labial starts F2 low and rises,
# an alveolar starts it high and falls into a back vowel, a velar starts high
# and close to F3. Without them a consonant is a noise stuck on the front of a
# vowel instead of a gesture the vowel comes out of.
LOCUS = {
    'labial':   ((400.0, 150.0, 1.00), ( 800.0, 220.0, 0.50), (2200.0, 260.0, 0.18)),
    'alveolar': ((350.0, 140.0, 1.00), (1750.0, 240.0, 0.55), (2600.0, 260.0, 0.22)),
    'velar':    ((350.0, 140.0, 1.00), (2000.0, 240.0, 0.60), (2400.0, 260.0, 0.28)),
    'palatal':  ((320.0, 130.0, 1.00), (2100.0, 240.0, 0.58), (2900.0, 260.0, 0.24)),
    'glottal':  ((500.0, 180.0, 1.00), (1500.0, 300.0, 0.40), (2500.0, 300.0, 0.18)),
}
PLACE = {
    'p':'labial','b':'labial','m':'labial','f':'labial','v':'labial',
    't':'alveolar','d':'alveolar','n':'alveolar','s':'alveolar','z':'alveolar',
    'l':'alveolar','r':'alveolar',
    'k':'velar','g':'velar',
    'S':'palatal','tS':'palatal','dZ':'palatal','J':'palatal',
    'h':'glottal',
}


def locus_of(consonant):
    """The tract shape a consonant releases from, or None."""
    return LOCUS.get(PLACE.get(consonant))


# ---------------------------------------------------------------- consonants
# A consonant is noise, and the renderer already makes onset noise: chiff. So a
# consonant is chosen by how much, for how long, and WHERE IN THE SPECTRUM --
# which is what separates /s/ from /f/ from /m/.
#
#   volume : how much noise rides the onset
#   cycle  : how far the phase is scattered -- this is what MAKES it noise. The
#            kernel multiplies the chiff by it, so a volume with no cycle is
#            silence, which is exactly the bug this table was written with.
#   width  : burst length in seconds. Plosives are a click, fricatives a hiss --
#            /t/ is over in 15 ms where /s/ runs 120.
#   span   : which harmonics carry it. Harmonic h gets 1/(1+((h-1)/span)**power),
#            so a SMALL span keeps the noise low (a "chuff", for /m/ /b/) and a
#            large one lets it reach the top of the series, which is where the
#            sibilants live.
#
# The honest limit: chiff noise rides the harmonic series, so it is pitch-linked
# where a real /s/ is pitch-independent friction at 5-8 kHz. A wide span puts
# the energy high, which is approximately right and is not the same thing.
CONSONANTS = {
    # key: (volume, width_s, centre_hz, bandwidth_hz, elasticity)
    #
    # ELASTICITY is how far the segment follows the local tempo. Segments do
    # all lengthen as the music slows, but NOT equally: the competing-
    # constraints account of speech timing has every segment resisting
    # departure from a preferred duration, with the long ones changing
    # markedly and the short ones acting as "phonetic anchors". A fricative is
    # held friction and stretches; a plosive is a ballistic gesture and does
    # not -- nobody sings a 200 ms /t/ however slow the Larghetto. So
    # 0 = fixed, 1 = fully proportional, and the plosives sit near the floor.
    #
    # CENTRE IN HERTZ, because a fricative's friction band is a property of the
    # constriction and sits where it sits however high the singer is -- the
    # same distinction the harpsichord's body needed against its pluck comb.
    #
    # AND THE BANDS ARE WIDE. A narrow band is quasi-periodic and still reads
    # as a pitch: measured, 1400 Hz at 6200 gives a periodicity of 0.36, and
    # 3000 Hz gives 0.09. Real friction is broad; only the nasals, which have
    # an actual resonating cavity behind them, are narrow.
    's': (1.00, 0.120, 6200.0, 3600.0, 0.55),   # the brightest thing a voice does
    'z': (0.70, 0.090, 5600.0, 3400.0, 0.55),
    'S': (1.00, 0.130, 3200.0, 2400.0, 0.55),   # "sc"/"sch": lower, and that IS the difference
    'f': (0.65, 0.100, 4000.0, 4000.0, 0.50),   # weak and very broad
    'v': (0.45, 0.080, 3400.0, 3400.0, 0.50),
    'h': (0.40, 0.070, 1800.0, 2400.0, 0.45),
    # THE THREE STOP CLASSES DIFFER IN SHAPE, not just in centre. A velar
    # burst is COMPACT -- a narrow mid peak, which is exactly why /k/ and /g/
    # sound dark. An alveolar is diffuse-RISING, broad and high; a labial
    # diffuse-FALLING, broad and low. One broad band for all three made the
    # velars top-heavy: a wide band at 2.6 kHz carries as much 4 kHz as an /s/.
    # Voiced stops are weaker and darker than their voiceless partners too --
    # the folds are already going, so the pressure drop behind the closure is
    # smaller.
    't': (0.95, 0.030, 3800.0, 3400.0, 0.15),   # alveolar: diffuse-rising
    'k': (0.78, 0.032, 1750.0, 1100.0, 0.15),   # velar: compact, narrow, dark
    'p': (0.62, 0.026, 1100.0, 1500.0, 0.15),   # labial: diffuse-falling
    'd': (0.42, 0.024, 2700.0, 2600.0, 0.15),
    'g': (0.38, 0.026, 1450.0, 1000.0, 0.15),
    'b': (0.34, 0.022,  900.0, 1300.0, 0.15),
    'tS': (0.95, 0.060, 3000.0, 2400.0, 0.40),
    'dZ': (0.70, 0.050, 2600.0, 2200.0, 0.40),
    'r': (0.45, 0.035, 1500.0,  900.0, 0.30),
    'l': (0.22, 0.028, 1100.0,  800.0, 0.30),   # approximants barely rustle
    'm': (0.20, 0.035,  700.0,  600.0, 0.35),   # nasals resonate, so they stay narrow
    'n': (0.24, 0.035,  900.0,  650.0, 0.35),
    'J': (0.26, 0.035, 1000.0,  700.0, 0.35),
}



# Spelling to consonant, longest match first. Ecclesiastical Latin and Italian
# share nearly all of this; the c/g-before-front-vowel rule is the main event.
_FRONT = 'eiyæœ'

def onset_of(syllable, language='latin'):
    """The consonant a syllable STARTS with, as a CONSONANTS key, or None.

    Only the onset. A coda consonant belongs to the end of the note and is not
    modelled yet -- and in sung Latin the coda is usually carried over to the
    next syllable anyway.
    """
    if not syllable:
        return None
    s = _repair(str(syllable)).strip().lower()
    s = ''.join(c for c in s if c.isalpha() or c in 'äöü')
    if not s:
        return None
    two, one = s[:2], s[0]
    nxt = s[1:2]
    if language == 'phoneme':
        return parse_phoneme(syllable)[0]
    if language in ('latin', 'italian'):
        if two == 'sc' and s[2:3] in _FRONT: return 'S'
        if two == 'ch': return 'k'
        if two == 'gn': return 'J'
        if two == 'gl': return 'l'
        if one == 'c':  return 'tS' if nxt in _FRONT else 'k'
        if one == 'g':  return 'dZ' if nxt in _FRONT else 'g'
        if one == 'j':  return 'dZ'
        if one == 'q':  return 'k'
        if one == 'x':  return 'k'
    else:
        if s.startswith('sch'): return 'S'        # 3 chars, not 2
        if two in ('sp', 'st'): return 'S'        # initial sp-/st- are /sp/, /st/
        if two == 'ch': return 'h'
        if two == 'ts' or one == 'z': return 't'
        if one == 'w':  return 'v'
        if one == 'v':  return 'f'
        if one == 'j':  return 'l'
    return one if one in CONSONANTS else None


def coda_of(syllable, language='latin'):
    """The consonant a syllable ENDS with -- only for explicit transcription,
    since guessing a coda from spelling needs the same dictionary the onsets
    avoid."""
    if language != 'phoneme':
        return None
    return parse_phoneme(syllable)[2]


def consonant_of(syllable, language='latin'):
    return CONSONANTS.get(onset_of(syllable, language))


def _repair(text):
    """MIDI meta text is bytes, and mido hands it back decoded as latin-1 --
    but engravers write UTF-8, so an umlaut arrives as 'MÃ¼l' and matches
    nothing. Re-encoding and decoding recovers it; if the bytes were not UTF-8
    the round trip fails and the original is kept.
    """
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
        return text


def vowel_of(syllable, language='latin'):
    """The vowel a syllable is sung on, as a VOWELS key, or None.

    Scans left to right and takes the FIRST nucleus: a syllable has one, and
    anything after it belongs to the next note or to the coda.
    """
    if not syllable:
        return None
    s = _repair(str(syllable)).strip().lower()
    s = ''.join(c for c in s if c.isalpha() or c in 'äöü')
    if not s:
        return None
    if language == 'phoneme':
        return parse_phoneme(syllable)[1]
    rules = RULES.get(language, LATIN)
    i = 0
    while i < len(s):
        for seq, vow in rules:
            if s.startswith(seq, i):
                if vow is None:          # "qu": the u is not a nucleus
                    i += len(seq); break
                # German final -e is a schwa, not a full vowel
                if language == 'german' and seq == 'e' and i == len(s) - 1 and i > 0:
                    return '@'
                if language == 'german' and s.endswith('er') and i == len(s) - 2:
                    return 'A'
                return vow
        else:
            i += 1
    return None


def parse_phoneme(text):
    """'t/u' -> ('t', 'u', None);  '/O/r' -> (None, 'O', 'r').

    An explicit transcription, for when spelling will not do it. English needs
    a pronouncing dictionary and is not attempted by rule -- but a phrase that
    is written out phonetically needs no rules at all, which also makes any
    other language singable by transcribing it.

    onset / vowel / coda. The coda matters more than it looks: "not" without
    its final /t/ is "naw", and the word stops being the word.
    """
    parts = [p.strip() for p in str(text).split('/')]
    while len(parts) < 3: parts.append('')
    on, vow, coda = parts[0], parts[1], parts[2]
    return (on or None), (vow or None), (coda or None)


def formants_for(syllable, language='latin', default='a'):
    return VOWELS.get(vowel_of(syllable, language) or default)


if __name__ == '__main__':
    import sys
    tests = {
        'latin':   "Lacrimosa dies illa qua resurget ex favilla judicandus homo reus".split(),
        'italian': "Caro mio ben credimi almen senza di te languisce il cor".split(),
        'german':  "Das Wandern ist des Müllers Lust die Freude schöne Blümelein".split(),
    }
    for lang, words in tests.items():
        print("== %s" % lang)
        print("   " + "  ".join("%s:%s" % (w, vowel_of(w, lang)) for w in words))
