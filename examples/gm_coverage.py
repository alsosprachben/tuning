#!/usr/bin/env python3
"""How complete is each of the 128 GM patches? Writes coverage.md.

    python3 examples/gm_coverage.py [outfile]

THE CLASS COLUMN IS READ FROM THE CODE, so it cannot drift: it asks
patch_map the same question blockrender asks. The RATING is a judgement and
lives in RATED below, where it can be argued with.

The scale, and how each rung was decided:

  0  nothing -- no voice at all. (Nothing scores 0: every program resolves
     to something. That is not the same as every program being served.)
  1  a general class -- this patch is played by a shared base, or by another
     instrument's voice standing in for it. Some stand-ins are reasonable
     (an Electric Grand is a string piano) and some are category errors
     (a Telephone Ring is not a mallet). The note says which.
  2  a specific class built from theory -- the instrument has its own voice,
     derived from how it works, with nothing heard or measured against it.
  3  ...and calibrated by ear -- Ben listened and the numbers moved.
  4  ...and fitted against a RECORDING of the instrument, or against the
     family law measured on its close relatives (the sax law is measured on
     soprano and alto; the flute law across bass, alto and concert).

WHAT COUNTS AS A RECORDING, since that is the line that matters: audio of the
instrument that was analysed and fitted against. Published measurements of an
instrument -- the Rhodes' high-speed camera papers, say -- are better than
theory but are NOT audio, so those voices sit at 2 with a note. The point of
the scale is to show where the model has been contradicted by reality, and only
a recording can do that.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import patch_map

GM = """Acoustic Grand Piano,Bright Acoustic Piano,Electric Grand Piano,Honky-tonk Piano,
Electric Piano 1,Electric Piano 2,Harpsichord,Clavinet,Celesta,Glockenspiel,Music Box,
Vibraphone,Marimba,Xylophone,Tubular Bells,Dulcimer,Drawbar Organ,Percussive Organ,
Rock Organ,Church Organ,Reed Organ,Accordion,Harmonica,Tango Accordion,
Acoustic Guitar (nylon),Acoustic Guitar (steel),Electric Guitar (jazz),
Electric Guitar (clean),Electric Guitar (muted),Overdriven Guitar,Distortion Guitar,
Guitar Harmonics,Acoustic Bass,Electric Bass (finger),Electric Bass (pick),
Fretless Bass,Slap Bass 1,Slap Bass 2,Synth Bass 1,Synth Bass 2,Violin,Viola,Cello,
Contrabass,Tremolo Strings,Pizzicato Strings,Orchestral Harp,Timpani,String Ensemble 1,
String Ensemble 2,Synth Strings 1,Synth Strings 2,Choir Aahs,Voice Oohs,Synth Choir,
Orchestra Hit,Trumpet,Trombone,Tuba,Muted Trumpet,French Horn,Brass Section,
Synth Brass 1,Synth Brass 2,Soprano Sax,Alto Sax,Tenor Sax,Baritone Sax,Oboe,
English Horn,Bassoon,Clarinet,Piccolo,Flute,Recorder,Pan Flute,Blown Bottle,
Shakuhachi,Whistle,Ocarina,Lead 1 (square),Lead 2 (sawtooth),Lead 3 (calliope),
Lead 4 (chiff),Lead 5 (charang),Lead 6 (voice),Lead 7 (fifths),Lead 8 (bass+lead),
Pad 1 (new age),Pad 2 (warm),Pad 3 (polysynth),Pad 4 (choir),Pad 5 (bowed),
Pad 6 (metallic),Pad 7 (halo),Pad 8 (sweep),FX 1 (rain),FX 2 (soundtrack),
FX 3 (crystal),FX 4 (atmosphere),FX 5 (brightness),FX 6 (goblins),FX 7 (echoes),
FX 8 (sci-fi),Sitar,Banjo,Shamisen,Koto,Kalimba,Bag pipe,Fiddle,Shanai,Tinkle Bell,
Agogo,Steel Drums,Woodblock,Taiko Drum,Melodic Tom,Synth Drum,Reverse Cymbal,
Guitar Fret Noise,Breath Noise,Seashore,Bird Tweet,Telephone Ring,Helicopter,
Applause,Gunshot""".replace("\n", "").split(",")

# program: (rating, note). The note earns the rating or explains the gap.
RATED = {
 0:(4,"Iowa samples; Steinway B inharmonicity fit, soundboard and stretch measured"),
 1:(2,"the grand voiced HARD: shorter hammer contact, felt that spreads half as much. Tells most at pp"),
 2:(2,"a CP-70: short strings so 12x the bass stretch, no soundboard, a piezo on the bridge. Derived, no reference"),
 3:(2,"the grand with the tuner's hand off: the unison range widened from under 2 cents to 8-20, CC1 scales it"),
 4:(2,"Rhodes. Built on two papers' high-speed-camera measurements, but NO audio fitted"),
 5:(2,"Wurlitzer. Same machinery, 1/d pickup; no audio fitted"),
 6:(4,"VCSL recordings"),
 7:(2,"its own voice: struck at the anvil, magnetic pickups whose fraction climbs with pitch. No reference"),
 8:(2,"struck steel plate, felt hammer"),
 9:(4,"Iowa orchestra bells"),
 10:(2,"plucked steel comb tooth. Its docstring claims a cantilever; its numbers are a free-free bar"),
 11:(4,"Iowa vibraphone. The motor tremolo that gives it its name is NOT modelled"),
 12:(4,"Iowa marimba"),
 13:(4,"Iowa xylophone"),
 14:(2,"tubes at 2:3:4:5"),
 15:(2,"struck steel courses; the stiffness is estimated"),
 16:(3,"tonewheel + Leslie, worked over extensively by ear"),
 17:(3,"tonewheel, percussive tap"),
 18:(3,"tonewheel, overdriven"),
 19:(3,"flue pipes; registration built on Geer and judged by ear"),
 20:(2,"FreeReedProperties: a tongue through a slot, no resonator -- not the pipe organ reed RANK all four used to be"),
 21:(2,"AccordionProperties: musette, the reed banks deliberately offset ~16 cents"),
 22:(2,"HarmonicaProperties: one free reed inside a cupped-hand formant pair"),
 23:(2,"TangoAccordionProperties: the same box tuned DRY (~3 cents), which is what a bandoneon is"),
 24:(4,"Iowa classical guitar, six strings measured sul A/B/D/E/G"),
 25:(2,"the measured classical's body with a steel string on it: less damping, a pick, 35% more stretch"),
 26:(3,"electric family: pluck comb x pickup comb, amp and cabinet; judged by ear"),
 27:(3,"as 26 -- the reference voice of the family"),
 28:(3,"as 26, palm mute"),
 29:(3,"as 26, driven harder"),
 30:(3,"as 26, driven hardest"),
 31:(3,"as 26, touched harmonics"),
 32:(2,"the upright PLUCKED: GM 43's measured body with a plucked base, comb at the quarter point"),
 33:(3,"electric bass family, cabinet and amp; judged by ear"),
 34:(3,"as 33, pick"),
 35:(3,"as 33, fretless -- loses its top rather than starting without it"),
 36:(3,"as 33, slap"),
 37:(3,"as 33, pop"),
 38:(2,"a sawtooth under a resonant low-pass; the filter shuts while the amplitude holds, which is the pluck. Was the generic plucked string, i.e. no body and no filter"),
 39:(2,"a SQUARE under a higher, more resonant filter -- odd harmonics only, so hollow where 38 is full, and an exact distinction rather than a tuned one"),
 40:(4,"Iowa violin"),
 41:(4,"Iowa viola, fitted across registers"),
 42:(4,"Iowa cello"),
 43:(4,"Iowa double bass"),
 44:(2,"tremolo_bow(): the articulation applied to whichever body the register picks -- amplitude modulation, per-player rate and phase"),
 45:(2,"pizzicato(): the MEASURED body of whichever instrument the register picks, plucked -- and the ring scales with register, 2.35 s at E1 to 0.42 at E5"),
 46:(2,"Harp: plucked in toward the middle (the comb nulls at h2.6, which is why it is mellow) and anchored into the board, so it rings"),
 47:(2,"analytic: the Bessel zeros of a clamped circular membrane. No recording exists in the set"),
 48:(3,"four MEASURED bodies (Iowa violin/viola/cello/bass) routed per register, each in a section; the ensemble treatment is theory"),
 49:(2,"its own slow-bowed class"),
 50:(2,"a string MACHINE: one oscillator per key and a bucket-brigade chorus -- three copies at FIXED offsets, each swept at 0.35-0.85 Hz. Had rendered identically to GM 48"),
 51:(2,"as 50, slower swell (300 ms) and a wider chorus. Darker and slower is one decision: an envelope that opens gently never reaches as far up the series"),
 52:(3,"vocal tract and formants; Ben's ear on the consonant balance"),
 53:(3,"as 52"),
 54:(2,"its own class, theory"),
 55:(2,"its own class, theory"),
 56:(4,"Iowa trumpet, three registers"),
 57:(4,"Iowa tenor and bass trombone, refitted across registers"),
 58:(4,"Iowa tuba"),
 59:(2,"its own class; the mute is theory"),
 60:(4,"Iowa horn, re-measured across four registers and pp/mf/ff"),
 61:(3,"brass_section over three MEASURED bodies (Iowa trumpet/trombone/tuba), five players each, crossfaded across the range handovers -- the hard break moved the spectrum 13.2 dB in one semitone and now moves 2.7"),
 62:(2,"a sawtooth through a RESONANT filter, leaning trumpet-bright (resonance 1400 Hz); not the acoustic brass base, which carries a bore and a horn's intonation"),
 63:(2,"the same synth leaning horn-soft (resonance 420 Hz, slower front); deliberately NOT tuned onto GM 60, which is itself synthesised -- resemblance there would be redundancy"),
 64:(4,"Iowa soprano sax"),
 65:(4,"Iowa alto sax"),
 66:(4,"the sax law, measured on soprano and alto and transposed"),
 67:(4,"as 66"),
 68:(4,"Iowa oboe"),
 69:(4,"the conical reed law measured on the oboe; its close relative"),
 70:(4,"Iowa bassoon"),
 71:(4,"Iowa clarinet family -- Bb, Eb and bass, to find one register law"),
 72:(4,"the flute law, measured across bass, alto and concert flute"),
 73:(4,"Iowa flute (nonvib -- vibrato smears the harmonics)"),
 74:(2,"a fipple DUCT: the windway is built in, so the jet is identical every time and the tone is purer than the flute's by 3 dB at h2"),
 75:(2,"a CLOSED tube (odd harmonics, already right) that had no breath at all -- StoppedPipe ships sustain_jitter 0, so it rendered as an organ's Gedackt"),
 76:(2,"its own class, theory"),
 77:(2,"a knife-edge notch and the breathiest voice in the family; meri/kari belong on a controller and are not modelled"),
 78:(2,"CATEGORY CORRECTION: a human whistle is a Helmholtz resonator, not a pipe -- one resonance tuned by the tongue, and nearly a sine (h2 -33 dB)"),
 79:(2,"its own class -- a vessel flute, theory"),
 80:(3,"a square EXACTLY: odd harmonics at 1/n, checked against the closed form to 6e-17. The section that had been making it a supersaw is off"),
 81:(3,"a sawtooth EXACTLY: every harmonic at 1/n, to 1e-17"),
 82:(3,"a TRIANGLE exactly -- odd harmonics at 1/n^2, which is why it is the soft one. The GM name misleads: a real calliope is a steam whistle organ"),
 83:(2,"a saw with the organ's own chiff on the front, which is what the patch is named for"),
 84:(2,"a saw through the valve the electric guitars use; amp_reference scales with its gain"),
 85:(2,"an oscillator behind vocal formants (an open /a/ from vowels.py). FormantBody had to be wired in by hand -- the saw bypasses bore_gain"),
 86:(3,"the waveform and its fifth, +700.0 cents exactly -- TEMPERED, since a GM oscillator is offset in semitones"),
 87:(3,"the waveform and an octave below, -1200.0 cents; a ratio of 2 in any temperament"),
 104:(2,"its own class; sympathetic strings and jawari, but the responder set is ASSERTED -- no recording"),
 105:(2,"steel over a DRUMHEAD: a membrane is light and damped, so it cannot radiate below 380 Hz and it empties the string fast. Thin, quick and bright are one fact"),
 106:(2,"the same head, plus a SAWARI buzz modelled as the sitar models its jawari, and a wide bachi that fills its own comb notch"),
 107:(2,"long slack silk over a light WOODEN box: the banjo's opposite in every way. Movable bridges mean uniform, very low inharmonicity across the compass"),
 108:(2,"a plucked CANTILEVER, 1 : 6.267 : 17.55 -- not the mallet base's struck bar. The Rhodes tine's ratios, undamped, so the overtones ping above the note"),
 109:(2,"the DRONES: fixed at 220/110 Hz whatever the melody does, which no other voice here can do. They restart per note, and sources.md says why"),
 110:(4,"the measured violin, given solo treatment"),
 111:(2,"a CONE, so the even harmonics the chanter's class suppressed come back -- a shawm is an oboe's geometry, not a bagpipe's"),
 112:(4,"Iowa crotales, 25 pitches"),
 113:(2,"its own class, theory"),
 114:(4,"built from the instrument's design, then corrected against Freesound 742254"),
 115:(4,"Iowa woodblocks"),
 116:(2,"the membrane drum class"),
 117:(2,"the tom class"),
 118:(1,"the generic mallet base. CATEGORY ERROR"),
 119:(1,"the generic mallet base. CATEGORY ERROR: this needs a BACKWARDS envelope"),
 120:(3,"its own class -- slide, squeak and position shift; reworked against Ben's ear"),
 121:(2,"its own class, theory"),
 122:(2,"its own class, theory"),
 123:(1,"the generic mallet base. CATEGORY ERROR"),
 124:(1,"the generic mallet base. CATEGORY ERROR: US ringback is 440+480 Hz gated"),
 125:(1,"the generic mallet base. CATEGORY ERROR"),
 126:(2,"its own class, theory"),
 127:(2,"its own class, theory"),
}
for p in range(88, 104):
    RATED[p] = (1, "one BowedStringProperties serves all sixteen pads and FX")
# ...and 88-95 no longer do. GM's own names point at eight MECHANISMS, and each
# class has one the others do not; see tonelib.SynthPadProperties. 96-103 are
# still the shared voice.
RATED.update({
 88:(2,"glassy: partials slightly STRETCHED (B=0.00035), so it shimmers where 93 clangs"),
 89:(2,"the plain one, deliberately: a low cutoff and a wide chorus and nothing else -- the pad you put underneath something"),
 90:(2,"really a poly patch: the only pad with a front fast enough (45 ms) to play chords in time"),
 91:(2,"vocal formants, an open /O/ from vowels.py's own table, widened because a section's formants average many tracts"),
 92:(2,"bowed glass: the longest swell in the family (420 ms) over a high narrow body. NOT a bowed string -- GM 48/49 are that"),
 93:(2,"INHARMONIC, 18x the glassy pad's stretch -- the one pad distinction that is physics and not filtering. Capped at 14 partials, since the stretch grows as h^2"),
 94:(2,"hollow: ODD HARMONICS ONLY, an exact distinction, with an airy formant high above it"),
 95:(2,"the filter sweep IS the patch: h16 falls at 120 dB/s against the other pads' 18. The sweep back UP is not modelled, and says so"),
 96:(2,"glassy droplets: the only voice with BOTH a stretch and repeated attacks"),
 97:(2,"the widest chorus and the longest swell (550 ms) in the bank -- its character is WIDTH where the warm pad's is weight"),
 98:(2,"the most inharmonic voice here, B=0.0105, capped at ten partials because the stretch grows as h^2"),
 99:(2,"BREATH: sustain_jitter at the pan pipe's value, the only voice in these sixteen to use it"),
 100:(2,"the hardest front (12 ms) with nothing rolled off above it -- quick AND wide open, where the polysynth pad is merely quick"),
 101:(2,"a deep slow WOBBLE, 55 cents where a violinist uses 5, so it reads as an unstable instrument rather than expression -- and dark, because a wobble on a bright sound is a broken synth"),
 102:(2,"four repeated ATTACKS 160 ms apart at falling gain. NOT a delay line, and sources.md records how far short it falls and why"),
 103:(2,"odd harmonics AND a deep sweep: two exact mechanisms stacked rather than a new one"),
})

# ---- channel 10, the percussion note map --------------------------------
# Iowa's percussion pages carry cymbals, crotales and hand percussion -- and NO
# DRUM KIT AT ALL: no snare, no bass drum, no toms, which is 9630 of the
# collection's 12781 percussion notes. So this table splits almost exactly along
# that line, and the classes that have no reference say so themselves.
PERC_RATED = {
 35:(3,"no reference -- Iowa has no drum kit. Analytic membrane, pitch tuned by ear"),
 36:(3,"as 35, tuned higher"),
 37:(2,"its own class, theory"),
 38:(3,"NO REFERENCE, and it says so. Analytic Bessel modes plus the snare wires; ear"),
 39:(2,"its own class, theory"),
 40:(1,"the acoustic snare at a different pitch; an electric snare is a different instrument"),
 41:(2,"floor tom, analytic membrane"),
 42:(4,"Iowa hi-hat, five takes"),
 43:(2,"as 41, higher"),
 44:(4,"Iowa hi-hat, foot-close take"),
 45:(2,"tom, analytic membrane"),
 46:(4,"Iowa hi-hat, open"),
 47:(2,"as 45, higher"),
 48:(2,"high tom, analytic membrane"),
 49:(4,"Iowa 17\" suspended crash, stick on the bow"),
 50:(2,"as 48, higher"),
 51:(4,"Iowa 21\" ride, bow"),
 52:(4,"Iowa chinese, 16/19/20\""),
 53:(4,"Iowa ride bell -- the ping is mode 8.1, not the fundamental"),
 54:(2,"generic noise body, but its own rattle: 14 jingles. Iowa HAS tambourines; they were not taken"),
 55:(4,"Iowa splash"),
 56:(2,"its own class, theory"),
 57:(4,"Iowa 20\" and 13\" suspended crash"),
 58:(2,"generic noise body with its own rattle"),
 59:(4,"GM wants two rides and Iowa has one; this is that measurement on a larger plate"),
 60:(1,"one MembraneDrum serves eleven notes, 60-66 and 78-79 and 86-87, differing only in pitch"),
 61:(1,"as 60"), 62:(1,"as 60"), 63:(1,"as 60"), 64:(1,"as 60"),
 65:(1,"as 60"), 66:(1,"as 60"),
 67:(2,"its own class, theory"),
 68:(2,"as 67, lower"),
 69:(2,"its own class -- a shaken rattle, theory"),
 70:(2,"its own class -- a shaken rattle, theory"),
 71:(3,"NO REFERENCE, and it says so. Ben on the first version: the whistles were noise driven"),
 72:(3,"as 71, longer"),
 73:(4,"Iowa guiro, both directions -- four rounds of measuring the right thing in the wrong window"),
 74:(4,"as 73, the long scrape"),
 75:(4,"Iowa claves, three pairs"),
 76:(4,"Iowa woodblocks, four sizes"),
 77:(4,"as 76, the low block"),
 78:(2,"its own FRICTION voice: sawtooth drive, axisymmetric modes only, mode-locked, glides up into pitch"),
 79:(2,"as 78, lower and gliding the other way. No reference -- Iowa has no friction drum"),
 80:(4,"Iowa triangles, 6\" and 8\""),
 81:(4,"as 80, undamped"),
 84:(4,"the measured crotales, cascaded -- 22 of them over 30 units"),
 85:(4,"Iowa castanets"),
 86:(1,"MembraneDrum again; a surdo is a different drum from a bongo"),
 87:(1,"as 86"),
}

FAMILY = [(0,"Piano"),(8,"Chromatic Percussion"),(16,"Organ"),(24,"Guitar"),(32,"Bass"),
          (40,"Strings"),(48,"Ensemble"),(56,"Brass"),(64,"Reed"),(72,"Pipe"),
          (80,"Synth Lead"),(88,"Synth Pad"),(96,"Synth Effects"),(104,"Ethnic"),
          (112,"Percussive"),(120,"Sound Effects")]
LEVEL = {0:"nothing", 1:"general class", 2:"specific, theory",
         3:"specific, theory + ear", 4:"specific, reference audio"}


def _class_name(p):
    """What program p actually renders as -- asked of the ROUTER, not the map.

    This column used to read `patch_map.property_class_for_program`, which is
    the no-note FALLBACK. Several programs are a FAMILY and are routed per note:
    the bowed and pizzicato ensembles, the brass section, and the solo winds
    whose bottom octave is a different instrument. For all of those the fallback
    is one member of the family, so the doc reported GM 61 as `Trombone` and
    called it a 1 -- "the trombone stands in for the whole section" -- when the
    code had routed it to trumpet, trombone and tuba sections for some time.

    The same mistake GM 32 and GM 44 both punished in the renderer, made here in
    the thing that is supposed to report on it. Ask the router.
    """
    # Probe every band a split can carve: BOWED_SPLIT breaks at 36/48/60 and
    # BRASS_SPLIT at 40/60, so sampling only low/middle/high missed the viola
    # and the trombone and reported a four-way split as a two-way one.
    names = []
    for c in (patch_map.property_class_for_note(p, n)
              for n in (30, 38, 44, 54, 64, 84)):
        n = c.__name__.replace("Properties", "")
        # A blended or sectioned class is named for what it is made of.
        for suffix in ("Section", "Tremolo", "Pizz"):
            n = n.replace(suffix, "")
        if "To" in n:                      # a crossfade sits between two
            n = n.split("To")[0]
        if n and n not in names:
            names.append(n)
    if len(names) == 1:
        return names[0]
    return "/".join(names) + " by register"


def percussion_table():
    """Channel 10. A separate specification from the 128 programs, and the place
    where the reference corpus divides most sharply."""
    import percussion_map as PM
    L = ["## Channel 10: the percussion note map\n"]
    ph = {k: 0 for k in range(5)}
    for n in PERC_RATED:
        ph[PERC_RATED[n][0]] += 1
    tot = len(PERC_RATED)
    L.append("%d notes, 35 to 87. Iowa's percussion pages carry cymbals, crotales and"
             % tot)
    L.append("hand percussion and **no drum kit at all** -- no snare, no bass drum, no")
    L.append("toms, which is 9630 of that collection's 12781 percussion notes. This table")
    L.append("splits almost exactly along that line.\n")
    L.append("| rating | notes | share |")
    L.append("|---|---|---|")
    for k in range(5):
        if ph[k]:
            L.append("| %d %s | %d | %d%% |" % (k, LEVEL[k], ph[k], round(100 * ph[k] / tot)))
    L.append("")
    L.append("| # | note | class | | notes |")
    L.append("|---|---|---|---|---|")
    for n in sorted(PERC_RATED):
        name, cls = PM.PERCUSSION[n][0], PM.PERCUSSION[n][1].__name__
        r, note = PERC_RATED[n]
        L.append("| %d | %s | `%s` | **%d** | %s |"
                 % (n, name, cls.replace("Properties", ""), r, note))
    L.append("")
    return "\n".join(L)


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'coverage.md')
    fams = dict(FAMILY)
    L = []
    L.append("# GM coverage\n")
    L.append("How complete each of the 128 GM patches is. Generated by")
    L.append("`examples/gm_coverage.py`, which reads the class column out of `patch_map`")
    L.append("so it cannot drift; the ratings live in that script and can be argued with.\n")
    L.append("| | meaning |")
    L.append("|---|---|")
    for k in range(5):
        L.append("| **%d** | %s |" % (k, LEVEL[k]))
    L.append("")
    L.append("4 means the voice was fitted against a RECORDING of the instrument, or")
    L.append("against a family law measured on its close relatives. Published measurements")
    L.append("that are not audio -- the Rhodes' high-speed-camera papers -- are better than")
    L.append("theory but cannot contradict the model the way a recording can, so those")
    L.append("voices sit at 2 and say so.\n")
    hist = {k: 0 for k in range(5)}
    for p in range(128):
        hist[RATED[p][0]] += 1
    L.append("## Where it stands\n")
    L.append("| rating | patches | share |")
    L.append("|---|---|---|")
    for k in range(5):
        L.append("| %d %s | %d | %d%% |" % (k, LEVEL[k], hist[k], round(100 * hist[k] / 128)))
    L.append("")
    cat = [p for p in range(128) if "CATEGORY ERROR" in RATED[p][1]]
    L.append("**%d patches are played by a voice of the wrong physical kind** "
             "(marked CATEGORY ERROR below): %s.\n"
             % (len(cat), ", ".join("%d %s" % (p, GM[p]) for p in cat)))
    L.append(percussion_table())
    for start, name in FAMILY:
        L.append("## %d-%d %s\n" % (start, start + 7, name))
        L.append("| # | patch | class | | notes |")
        L.append("|---|---|---|---|---|")
        for p in range(start, start + 8):
            cls = _class_name(p)
            r, note = RATED[p]
            L.append("| %d | %s | `%s` | **%d** | %s |"
                     % (p, GM[p], cls.replace("Properties", ""), r, note))
        L.append("")
    open(out, 'w').write("\n".join(L) + "\n")
    print("  wrote %s" % out)
    print("  %s" % "  ".join("%d:%d" % (k, hist[k]) for k in range(5)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
