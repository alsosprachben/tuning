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
    'E': ((530.0, 110.0, 1.00), (1840.0, 110.0, 0.55), (2480.0, 140.0, 0.25)),
    'e': ((390.0, 100.0, 1.00), (2100.0, 110.0, 0.50), (2600.0, 140.0, 0.22)),
    'i': ((270.0,  80.0, 1.00), (2290.0, 100.0, 0.45), (3010.0, 150.0, 0.20)),
    'O': ((570.0, 110.0, 1.00), ( 840.0, 100.0, 0.50), (2410.0, 140.0, 0.16)),
    'o': ((400.0,  95.0, 1.00), ( 750.0, 100.0, 0.46), (2400.0, 140.0, 0.14)),
    'u': ((300.0,  90.0, 1.00), ( 870.0, 100.0, 0.42), (2240.0, 140.0, 0.12)),
    'y': ((300.0,  90.0, 1.00), (1750.0, 110.0, 0.40), (2200.0, 140.0, 0.14)),
    'P': ((400.0, 100.0, 1.00), (1550.0, 110.0, 0.45), (2200.0, 140.0, 0.16)),
    '@': ((500.0, 120.0, 1.00), (1500.0, 110.0, 0.45), (2500.0, 140.0, 0.18)),
    'A': ((600.0, 130.0, 1.00), (1300.0, 110.0, 0.48), (2500.0, 140.0, 0.18)),
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
    # key: (volume, cycle, width_s, centre_hz, power, bandwidth_hz)
    #
    # CENTRE IS IN HERTZ, not in harmonic number -- the same distinction the
    # harpsichord's body needed. A fricative's friction band is a property of
    # the constriction, fixed where it is however high the singer sings, so it
    # belongs on the frequency axis like a formant and not on the harmonic axis
    # like a pluck comb. Given as harmonics it drifts: one span lands at 6 kHz
    # for a bass and 14 kHz for a soprano, and only one of those is an /s/.
    #
    # BANDWIDTH matters as much. Left at its default the chiff wash is WHITE --
    # every partial's noise spread flat across the spectrum -- which throws the
    # centre away again and piles the energy above 8 kHz, where no consonant
    # lives. A bounded bandwidth keeps the friction where the constriction put it.
    's':  (0.99, 0.95, 0.120, 6200.0, 1.0, 1400.0),
    'z':  (0.90, 0.70, 0.090, 5600.0, 1.0, 1400.0),
    'S':  (0.99, 0.95, 0.130, 3200.0, 1.0, 1400.0),   # "sc"/"sch", lower than /s/
    'f':  (0.85, 0.60, 0.100, 4000.0, 1.2, 1400.0),
    'v':  (0.55, 0.45, 0.080, 3400.0, 1.2, 1400.0),
    'h':  (0.48, 0.40, 0.070, 2000.0, 1.5,  900.0),
    't':  (0.99, 0.90, 0.015, 4200.0, 1.0, 1400.0),   # plosives: a click
    'k':  (0.95, 0.85, 0.018, 2600.0, 1.0,  900.0),
    'p':  (0.80, 0.70, 0.015, 1400.0, 1.2,  500.0),
    'd':  (0.70, 0.55, 0.012, 3400.0, 1.2, 1400.0),
    'g':  (0.65, 0.50, 0.014, 2200.0, 1.2,  900.0),
    'b':  (0.55, 0.45, 0.012, 1200.0, 1.4,  500.0),
    'tS': (0.99, 0.90, 0.060, 3000.0, 1.0,  900.0),
    'dZ': (0.90, 0.65, 0.050, 2600.0, 1.0,  900.0),
    'r':  (0.55, 0.40, 0.035, 1500.0, 2.0,  500.0),
    'l':  (0.24, 0.20, 0.025, 1100.0, 2.0,  500.0),   # approximants barely rustle
    'm':  (0.19, 0.18, 0.030,  700.0, 2.0,  500.0),   # nasals: low and soft
    'n':  (0.24, 0.20, 0.030,  900.0, 2.0,  500.0),
    'J':  (0.26, 0.22, 0.032, 1000.0, 2.0,  500.0),
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
