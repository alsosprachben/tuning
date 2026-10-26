"""THE SC-88 MAP'S SYNTH TONES ON THE MOOG (Roland's SC-88Pro owner's manual,
its instrument list; examples/gs_maps.py, gs_inventory.md): 77 variations of
the synth programs, each the capital's Messenger panel with what makes the
tone itself changed -- voiced from what each is (a TB-303's resonant slide, an
SH-101's pulse and sub, a poly brass, OB strings, FM bells), starting points
for Ben's ear and his Messenger, not measurements.

PANEL UNITS are moog.PANEL's, the hardware's knobs (moog.py): cutoff 7.9 Hz *
2^(11.38 v) (0.53 = 500 Hz, 0.61 = 1 kHz, 0.70 = 2 kHz, 0.79 = 4 kHz);
resonance self-oscillating from 0.8; contour times on knob_time (0.09 = 50 ms,
0.22 = 0.2 s, 0.36 = 0.5 s, 0.49 = 1 s) and attacks on attack_knob (0.15 =
0.1 s, 0.38 = 0.5 s); OSC 2 FREQ 0.5 + cents/1400; waves TRI 0.335, SAW 0.5,
SQUARE 0.68 (narrower pulses up to 1); EG AMOUNT bipolar about 0.5; LFO 1
rate 0.34 = 0.5 Hz, 0.55 = 2 Hz, 0.68 = 5 Hz; its destination 0 cutoff, 1
OSC 2 pitch, 2 OSC wave; its DEPTH a cube about 0.5 (on the cutoff 0.6 = 0.09
octave, 0.68 = 0.5, 0.75 = 1.4; on OSC 2's pitch 0.58 = 23 cents, 0.6 = 45;
on the wave 0.8 = 0.2 of its travel); MOD destination 0 is 1->2 FM.

{(program, bank): (GS name, the capital's Moog class, panel changes)}; the
two whose capital is not a Moog (35, 55) name the Moog voice they start from.
"""
SAW, SQ, TRI = 0.5, 0.68, 0.335
# THE SUPERSAW (moog.unison), fitted to a player's JD-Xi SuperSaw take (CC0,
# Freesound 573045; examples/supersaw_fit.py FIT): seven voices spread as the
# JP-8000's, the outermost +/-25 cents, each drifting +/-30 cents at its own
# 0.1-4 Hz, the sides 0.61 of the centre, the stereo 0.4 open
SUPERSAW = dict(voices=7, cents=25.31, mix=0.613, drift_cents=30.49, drift_hz=(0.1, 3.955), width=0.3954)


def c(cents):
    """OSC 2 FREQ for an offset in cents."""
    return 0.5 + cents / 1400.0


# THE JUPITER-8: the panel fitted to Jonathan Cain's on the record (examples/
# sepways_fit.py FIT: two saws through the open 4-pole low-pass, no resonance,
# a ~90 ms filter rise, the brass contour fading out) -- one pass of it, OSC 2
# at its -10 cents (the record's doubling was the mix's; the chorus is ours,
# Ben). The SC-88's Jupiter tones are it with what their names change.
JUPITER = {"mode": 0, "osc1_wave": SAW, "osc2_wave": SAW, "osc1_level": 0.8, "osc2_level": 0.8,
           "osc2_freq": c(-10), "resonance": 0.0, "kb_track": 0.0, "f_attack": 0.0913, "a_attack": 0.0,
           "a_decay": 0.6076, "a_sustain": 0.2254, "a_release": 0.6076, "cutoff": 0.85, "eg_amount": 0.3,
           "f_decay": 0.4, "f_sustain": 1.0}


def jp(**changes):
    return dict(JUPITER, **changes)


# THE MINIMOOG: the panel fitted to a Model D's held bass (examples/
# minimoog_fit.py: Garzul's, CC0, at C1 and C4, 2.8 dB rms over both): two
# shark-tooth waves -- the triangle skewed toward the saw, the Model D's own
# -- the second an octave up and a little louder, 1.4 cents sharp (its
# harmonics beat at k x 0.21 Hz at C4); the 4-pole low-pass open at 3.7 kHz,
# a touch of resonance, no key tracking (the two notes, three octaves apart,
# say off). The SC-88's MG tones are it with what their names change.
MINIMOOG = {"mode": 0, "osc1_wave": 0.404, "osc2_wave": 0.414, "osc1_level": 0.8, "osc2_level": 0.852,
            "osc1_octave": 8, "osc2_octave": 4, "osc2_freq": c(1.4), "sub_level": 0.0, "noise_level": 0.0,
            "cutoff": 0.78, "resonance": 0.065, "kb_track": 0.0, "eg_amount": 0.5, "a_attack": 0.0,
            "a_sustain": 1.0, "a_release": 0.15}


def mg(**changes):
    return dict(MINIMOOG, **changes)


# THE OBERHEIM: the panel fitted to an OB-8's held chords (examples/
# obx_fit.py: Analogist's "jungle pad", CC0, ten four-note chords, 2.25 dB rms):
# a saw and a second wave just short of one, a little under it, at unison
# (its partials do not split: under 2 cents); the 2-POLE low-pass, the
# Oberheim's own (the 4-pole fits 0.9 dB worse), at 665 Hz on middle C and
# tracking the key (the Dbmaj7 at two octaves says on), a touch of
# resonance. The SC-88's OB tones are it with what their names change.
OBERHEIM = {"mode": 1, "osc1_wave": 0.501, "osc2_wave": 0.448, "osc1_level": 0.8, "osc2_level": 0.669,
            "osc1_octave": 8, "osc2_octave": 8, "osc2_freq": c(1.5), "sub_level": 0.0, "noise_level": 0.0,
            "cutoff": 0.562, "resonance": 0.071, "kb_track": 1.0, "eg_amount": 0.5, "a_attack": 0.0,
            "a_sustain": 1.0, "a_release": 0.3}


def ob(**changes):
    return dict(OBERHEIM, **changes)


# THE JUNO: the panel fitted to a Juno-6's own notes (examples/juno_fit.py:
# Modular Samples, CC0, sampled key by key). One DCO a voice, so the two
# oscillators are its pulse (OSC 1, where LFO 1's PWM lands) and its saw (OSC
# 2) at exact unison -- no detune, no drift -- with the square SUB (0.3);
# the 4-pole IR3109. Fitted on the PW Pluck, every C from C2 to C6 over its
# whole pluck (3.1 dB rms on the harmonics, the contour 0.8 octave, the
# amplifier 0.5 dB): the saw with the pulse under it, the filter opened 5.6
# octaves and closing over ~2.4 s, all but no key tracking (the Juno's KYBD
# slider is continuous, and so is the kernel's), the amplifier falling 1.6 s.
# Its chorus is the tone's own insertion effect: Stereo Chorus at the Juno's
# CHORUS I (0.5 Hz; JUNO_CHORUS2 is II, 0.8 Hz), its DEPTH 7, not the type's
# 111 (a 17.5 ms sweep, +-95 cents): the takes' own chorus moves a copy about
# 6 cents (examples/juno_fit.py --chorus: the dry and the copy beat at 0.003-
# 0.007 x each harmonic's frequency -- 0.75 Hz at 131 Hz, 15 at 2 kHz), as the
# Juno-60's BBD does, a triangle sweeping 1.7-5.4 ms at 0.51 Hz.
JUNO_CHORUS1 = ((0x01, 0x42), {4: 9, 5: 7})
JUNO_CHORUS2 = ((0x01, 0x42), {4: 15, 5: 7})
JUNO = {"mode": 0, "osc1_wave": 0.715, "osc1_level": 0.46, "osc2_wave": SAW, "osc2_level": 1.0,
        "osc1_octave": 8, "osc2_octave": 8, "osc2_freq": 0.5, "sub_wave": 0.3, "sub_level": 0.0,
        "noise_level": 0.0, "resonance": 0.015, "kb_track": 0.022, "cutoff": 0.323, "eg_amount": 0.854,
        "f_attack": 0.058, "f_decay": 0.671, "f_sustain": 0.0, "a_attack": 0.0, "a_decay": 0.583,
        "a_sustain": 0.081, "a_release": 0.2, "mod_amount": 0.5, "lfo1_depth": 0.5,
        "insertion_efx": JUNO_CHORUS1}


def juno(**changes):
    return dict(JUNO, **changes)


# THE TB-303: the panel fitted to a TB-303's own note (examples/tb303_fit.py:
# DJMini's, CC0, C3 held; laffik's TD-3, its clone, swept by hand for the
# slope). One VCO, OSC 1 alone, no key tracking. Its pluck, from the
# resonant peak traced every 5 ms and fitted with the engine's own contour
# (0.03 octave rms): rising 29 ms to ~1.6 kHz, falling back to 693 Hz -- 1.15
# octaves over a 721 Hz cutoff, decay 0.30 s, no sustain. Held, the
# 4-pole at resonance 0.62 matches the 303's harmonics within 4.1 dB rms;
# the diode ladder's broader peak (its 6th harmonic 14 dB up on ours) is
# what is left. The VCA holds while the gate does. The 2-pole fits 5 dB worse.
TB303 = {"mode": 0, "osc1_wave": 0.45, "osc1_level": 1.0, "osc2_level": 0.0, "osc2_freq": 0.5,
         "sub_level": 0.0, "noise_level": 0.0, "kb_track": 0.0, "resonance": 0.62, "res_bass": False,
         "cutoff": 0.572, "eg_amount": 0.66, "f_attack": 0.073, "f_decay": 0.275, "f_sustain": 0.0,
         "a_attack": 0.0, "a_decay": 0.297, "a_sustain": 0.825, "a_release": 0.08,
         "mod_amount": 0.5, "lfo1_depth": 0.5}
TB_DIST = ((0x01, 0x11), {})          # the Distortion insertion type, as the module's own


def tb(**changes):
    return dict(TB303, **changes)


# THE SH-101: the Juno-6's fitted voice (JUNO) without its chorus -- the
# SH-101 is the same Roland voice, one VCO (its pulse, OSC 1; its saw, OSC 2;
# the square SUB) into the same IR3109 4-pole. No clean SH-101 note exists
# under CC0 (examples/sh101 refs: a bassline with its knobs moving, and
# resonance sweeps); the sweeps say what the engine's contour already does
# (exponential in octaves, the self-oscillation fading ~17 dB/s). Held as a
# bass plays: the amplifier at 0.8 after its decay.
SH101 = dict({k: v for k, v in JUNO.items() if k != "insertion_efx"}, a_decay=0.6, a_sustain=0.8)


def sh(**changes):
    return dict(SH101, **changes)


# THE SH-5: read, not fitted, from xanthorp's sample-and-hold patterns
# (examples/sh5_fit.py: no held note under CC0; each S&H step a note at its
# own cutoff -- 9 dB rms over 106 steps, the five takes likely five patches):
# what the steps agree on, a saw-like OSC 1, the second VCO an octave under
# at about half, a moderate peak. The 24 dB low-pass, as the SH-5 has (the
# steps could not tell its slope from the 2-pole's: 0.3 dB).
SH5 = {"mode": 0, "osc1_wave": 0.548, "osc1_level": 0.8, "osc2_wave": 0.521, "osc2_level": 0.44,
       "osc1_octave": 8, "osc2_octave": 16, "osc2_freq": c(3), "sub_level": 0.0, "noise_level": 0.0,
       "resonance": 0.414, "kb_track": 0.5, "a_attack": 0.0, "a_sustain": 1.0, "a_release": 0.2,
       "mod_amount": 0.5, "lfo1_depth": 0.5}


def sh5(**changes):
    return dict(SH5, **changes)


# THE CS: the panel fitted to a Yamaha CS-30L's bass (examples/cs_fit.py:
# Modular Samples, CC0, keys C2-C4 sounding, every frame of the held note):
# a near-saw into a dark low-pass its contour opens 3.6 octaves and settles
# half-way (5.0 dB rms on the harmonics, 0.31 octave on the contour, 2.2 dB
# on the amplifier), no key tracking. The 2-pole, the CS series' own 12 dB --
# the takes agree (0.1 dB better than the 4-pole) but cannot decide it. Its
# Saw pack, the filter open, is the engine's saw within a dB of 1/k.
CS = {"mode": 1, "osc1_wave": 0.558, "osc1_level": 1.0, "osc2_level": 0.0, "osc2_freq": 0.5,
      "sub_level": 0.0, "noise_level": 0.0, "resonance": 0.0, "kb_track": 0.0, "cutoff": 0.331,
      "eg_amount": 0.784, "f_attack": 0.059, "f_decay": 0.479, "f_sustain": 0.527, "a_attack": 0.027,
      "a_decay": 0.6, "a_sustain": 1.0, "a_release": 0.15, "mod_amount": 0.5, "lfo1_depth": 0.5}


def cs(**changes):
    return dict(CS, **changes)


# THE D-50: voiced, not fitted -- the one CC0 D-50 take that holds a note
# (agerven's supersquare, examples/d50 refs) gives its two partials' detune:
# every harmonic split 15 cents (they beat at 0.0087 x the harmonic's
# frequency: 8.9 Hz at 989, 17.3 at 1978); its filter is LFO-swept through
# the take and its chorus is under the beating, so neither is measured. A
# saw partial pair, the digital TVF as the 4-pole, a held contour, and the
# D-50's chorus as a moderate Stereo Chorus (depth 12: a guess, deeper than
# the Juno's measured 7).
D50_CHORUS = ((0x01, 0x42), {4: 10, 5: 12})
D50 = {"mode": 0, "osc1_wave": SAW, "osc1_level": 0.8, "osc2_wave": SAW, "osc2_level": 0.0, "osc2_octave": 8,
       "osc2_freq": c(15), "sub_level": 0.0, "noise_level": 0.0, "resonance": 0.1, "kb_track": 0.5,
       "cutoff": 0.72, "eg_amount": 0.62, "f_attack": 0.0, "f_decay": 0.6, "f_sustain": 0.6, "a_attack": 0.0,
       "a_decay": 0.6, "a_sustain": 1.0, "a_release": 0.3, "mod_amount": 0.5, "lfo1_depth": 0.5,
       "insertion_efx": D50_CHORUS}


def d50(**changes):
    return dict(D50, **changes)


SC88_SYNTH = {
    # --- the Jupiter-8's (JUPITER: fitted on the record) -------------------
    # its clav: a narrow pulse, the filter snapping shut, a short body
    (7, 33): ("JP8 Clav. 1", "MoogSynthBass1",
              jp(osc1_wave=0.85, osc2_wave=0.85, cutoff=0.62, eg_amount=0.75, f_attack=0.0, f_decay=0.12,
                 f_sustain=0.1, a_decay=0.3, a_sustain=0.1, a_release=0.15, kb_track=0.8)),
    # ...brighter and edged with resonance
    (7, 35): ("JP8 Clav. 2", "MoogSynthBass1",
              jp(osc1_wave=0.9, osc2_wave=0.9, cutoff=0.68, resonance=0.4, eg_amount=0.7, f_attack=0.0,
                 f_decay=0.1, f_sustain=0.15, a_decay=0.3, a_sustain=0.1, a_release=0.15, kb_track=0.8)),
    # the Jupiter-4's: one oscillator a voice, a resonant snap
    (38, 3): ("JP-4 Bass", "MoogSynthBass1",
              jp(osc2_level=0.0, cutoff=0.5, resonance=0.35, eg_amount=0.75, f_attack=0.0, f_decay=0.2,
                 f_sustain=0.15, a_decay=0.5, a_sustain=0.4, a_release=0.15)),
    # the Jupiter-8's: both saws, the second an octave down, a punch
    (38, 4): ("JP-8 Bass", "MoogSynthBass1",
              jp(osc2_octave=16, cutoff=0.52, eg_amount=0.7, f_attack=0.0, f_decay=0.25, f_sustain=0.25,
                 a_decay=0.5, a_sustain=0.5, a_release=0.15)),
    # "JPMG": the Jupiter's bass with the Minimoog's sub under it (read)
    (38, 6): ("JPMG Bass", "MoogSynthBass1",
              jp(osc2_octave=16, sub_level=0.5, cutoff=0.5, eg_amount=0.7, f_attack=0.0, f_decay=0.25,
                 f_sustain=0.3, a_decay=0.5, a_sustain=0.5, a_release=0.15)),
    # its strings: the saws spread wider, swelling, held
    (50, 3): ("JP Strings", "MoogSynthStrings1",
              jp(osc2_freq=c(-14), cutoff=0.72, eg_amount=0.0, a_attack=0.3, a_decay=0.6, a_sustain=1.0,
                 a_release=0.4)),
    # its square lead
    (80, 18): ("JP-8 Square", "MoogSquareLead",
               jp(osc1_wave=SQ, osc2_wave=SQ, cutoff=0.75, a_sustain=1.0, a_release=0.2)),
    # its pulse leads, narrower, the second edged with resonance
    (80, 25): ("JP8 PulseLd1", "MoogSquareLead",
               jp(osc1_wave=0.82, osc2_wave=0.82, cutoff=0.75, a_sustain=1.0, a_release=0.2)),
    (80, 26): ("JP8 PulseLd2", "MoogSquareLead",
               jp(osc1_wave=0.9, osc2_wave=0.9, cutoff=0.7, resonance=0.3, a_sustain=1.0, a_release=0.2)),
    # bass and lead: a saw over a square an octave down
    (87, 4): ("JP8 BsLead 1", "MoogBassLead",
              jp(osc2_wave=SQ, osc2_octave=16, cutoff=0.7, a_sustain=0.8, a_release=0.25)),
    (87, 5): ("JP8 BsLead 2", "MoogBassLead",
              jp(osc2_wave=SQ, osc2_octave=16, cutoff=0.65, resonance=0.35, eg_amount=0.5, f_decay=0.3,
                 f_sustain=0.5, a_sustain=0.8, a_release=0.25)),
    # its square pad: swelling, held, slow to go
    (92, 2): ("JP8 Sqr Pad", "MoogBowedPad",
              jp(osc1_wave=SQ, osc2_wave=SQ, osc2_freq=c(-12), cutoff=0.68, eg_amount=0.0, a_attack=0.4,
                 a_decay=0.6, a_sustain=1.0, a_release=0.5)),

    # --- basses ---------------------------------------------------------
    (35, 4): ("SynFretless", "MoogSynthBass1",
              dict(osc1_wave=0.45, osc2_level=0.0, sub_level=0.4, cutoff=0.50, resonance=0.2,
                   eg_amount=0.6, a_attack=0.09, glide=0.25)),
    (38, 1): ("Syn.Bass101", "MoogSynthBass1",
              sh(osc1_level=0.0, osc2_level=1.0, sub_level=0.6, cutoff=0.52, resonance=0.15, eg_amount=0.75,
                 f_attack=0.0, f_decay=0.22, f_sustain=0.3)),
    (38, 9): ("TB303 Bass", "MoogSynthBass1",
              dict(osc1_wave=SAW, osc2_level=0.0, sub_level=0.0, cutoff=0.45, resonance=0.7,
                   eg_amount=0.85, f_decay=0.2, f_sustain=0.0, res_bass=False, glide=0.1)),
    (38, 10): ("Tekno Bass", "MoogSynthBass1",
               dict(osc1_wave=SQ, osc2_level=0.0, cutoff=0.5, resonance=0.55, eg_amount=0.8,
                    f_decay=0.12, f_sustain=0.1)),
    (38, 16): ("Reso SHBass", "MoogSynthBass1",
               sh(osc1_level=0.0, osc2_level=1.0, sub_level=0.4, cutoff=0.5, resonance=0.6, eg_amount=0.75,
                  f_attack=0.0, f_decay=0.3, f_sustain=0.2)),
    (39, 1): ("Syn.Bass201", "MoogSynthBass2",
              dict(osc1_wave=0.62, sub_level=0.6, cutoff=0.52, resonance=0.2, f_decay=0.25, f_sustain=0.4)),
    (39, 2): ("ModularBass", "MoogSynthBass2",
              dict(osc1_wave=SAW, osc2_level=0.8, osc2_wave=SAW, osc2_octave=16, osc2_freq=c(6),
                   sub_level=0.0, cutoff=0.5, resonance=0.3, eg_amount=0.8, f_decay=0.3, f_sustain=0.2)),
    (39, 3): ("Seq Bass", "MoogSynthBass2",
              dict(osc1_wave=0.8, sub_level=0.3, cutoff=0.48, resonance=0.45, f_decay=0.12, f_sustain=0.0,
                   a_decay=0.25, a_sustain=0.3)),
    (39, 9): ("X Wire Bass", "MoogSynthBass2",
              dict(osc1_level=0.3, osc2_level=1.0, osc2_wave=SAW, sync=True, osc2_freq=0.8,
                   sub_level=0.4, cutoff=0.6, eg_amount=0.75)),
    (39, 16): ("Rubber Bass", "MoogSynthBass2",
               dict(osc1_wave=0.42, sub_level=0.6, cutoff=0.45, resonance=0.35, eg_amount=0.7,
                    f_decay=0.35, f_sustain=0.4, glide=0.05)),
    (39, 17): ("SH101Bass 1", "MoogSynthBass2",
               sh(osc1_wave=0.75, osc1_level=0.8, osc2_level=0.0, sub_level=0.5, cutoff=0.5, resonance=0.25,
                  eg_amount=0.75, f_attack=0.0, f_decay=0.25, f_sustain=0.3)),
    (39, 18): ("SH101Bass 2", "MoogSynthBass2",
               sh(osc1_level=0.0, osc2_level=1.0, sub_level=0.5, cutoff=0.47, resonance=0.5, eg_amount=0.75,
                  f_attack=0.0, f_decay=0.18, f_sustain=0.15)),
    # --- the D-50's (D50: voiced; its partials' detune measured) -----------
    # one saw partial, through its chorus
    (81, 28): ("D-50 Saw", "MoogSawLead", d50()),
    # the pair: two saw partials 15 cents apart, as the D-50's structure is
    (81, 11): ("D-50 Fat Saw", "MoogSawLead", d50(osc2_level=0.8)),
    # its organ: a square partial and another an octave up, the filter open,
    # a gate (the organ's capital is no Moog: the square lead's)
    (16, 25): ("D-50 Organ", "MoogSquareLead",
               d50(osc1_wave=SQ, osc2_wave=SQ, osc2_level=0.5, osc2_octave=4, osc2_freq=0.5, cutoff=0.85,
                   eg_amount=0.5, a_release=0.08)),
    # --- the CS's (CS: fitted to a CS-30L's bass) ---------------------------
    # its bass, the fitted patch, its second voice a few cents off
    (38, 2): ("CS Bass", "MoogSynthBass1", cs(osc2_wave=0.558, osc2_level=0.7, osc2_octave=8, osc2_freq=c(6))),
    # its saw, the filter open: the Saw pack
    (81, 30): ("CS Saw", "MoogSawLead", cs(osc1_wave=SAW, cutoff=0.85, eg_amount=0.5)),
    # the CS-80's lead: a saw, the filter swelling open and holding, an edge
    # of resonance
    (81, 18): ("CS Saw Lead", "MoogSawLead",
               cs(osc1_wave=SAW, cutoff=0.6, resonance=0.2, eg_amount=0.65, f_attack=0.15, f_decay=0.6,
                  f_sustain=0.6, a_release=0.25)),
    # --- the SH-5's (SH5: read from its sample-and-hold steps) -------------
    # its brass: both VCOs at the key a few cents apart, the ladder swelling
    # open and settling as brass does
    (62, 3): ("SH-5 Brass", "MoogSynthBrass1",
              sh5(osc2_octave=8, osc2_freq=c(8), osc2_level=0.7, cutoff=0.5, eg_amount=0.72, f_attack=0.2,
                  f_decay=0.5, f_sustain=0.5, a_attack=0.06)),
    # its bass-lead: the octave stack as read, a plucked contour held
    (87, 6): ("SH-5 Bs.Lead", "MoogBassLead",
              sh5(cutoff=0.55, eg_amount=0.72, f_attack=0.0, f_decay=0.3, f_sustain=0.35)),
    # the square and the saw together over the sub, a snappier contour
    (39, 20): ("SH101 Bass 3", "MoogSynthBass2",
               sh(osc1_wave=SQ, osc1_level=0.6, osc2_level=0.6, sub_level=0.4, cutoff=0.45, resonance=0.35,
                  eg_amount=0.8, f_attack=0.0, f_decay=0.15, f_sustain=0.1, a_decay=0.4, a_sustain=0.4)),
    (39, 19): ("Smooth Bass", "MoogSynthBass2",
               dict(osc1_wave=TRI, sub_level=0.5, cutoff=0.5, resonance=0.0, eg_amount=0.6,
                    a_attack=0.05, f_sustain=0.7)),
    # --- strings, voice, brass, hit --------------------------------------
    (50, 1): ("OB Strings", "MoogSynthStrings1",
              dict(osc2_freq=c(12), cutoff=0.70, resonance=0.1, f_attack=0.25, a_attack=0.25)),
    (54, 8): ("Syn.Voice", "MoogSynthVoice",
              dict(lfo1_dest=2, lfo1_depth=0.8, lfo1_rate=0.45)),
    (55, 16): ("Lo Fi Rave", "MoogSynthBrass1",
               dict(osc1_wave=SQ, osc2_wave=SAW, osc2_freq=1.0, noise_level=0.1, cutoff=0.62,
                    resonance=0.3, f_attack=0.0, a_attack=0.0, a_decay=0.3, a_sustain=0.0, a_release=0.2)),
    (62, 1): ("Poly Brass", "MoogSynthBrass1",
              dict(osc2_freq=c(10), f_attack=0.08, eg_amount=0.8, cutoff=0.55)),
    (62, 9): ("Quack Brass", "MoogSynthBrass1",
              dict(resonance=0.55, f_decay=0.2, f_sustain=0.4, eg_amount=0.85)),
    # --- leads: square (80) ---------------------------------------------
    (80, 1): ("Square", "MoogSquareLead",
              dict(sub_level=0.0, cutoff=0.75, resonance=0.0, eg_amount=0.55)),
    (80, 2): ("Hollow Mini", "MoogSquareLead",
              dict(osc1_wave=0.6, osc2_level=0.6, osc2_wave=TRI, osc2_octave=16, sub_level=0.0,
                   cutoff=0.6, resonance=0.2)),
    (80, 3): ("Mellow FM", "MoogSquareLead",
              dict(osc1_wave=TRI, osc2_wave=TRI, osc2_level=0.8, osc1_level=0.0, sub_level=0.0,
                   mod_dest=0, mod_amount=0.58, cutoff=0.7)),
    (80, 4): ("CC Solo", "MoogSquareLead",
              dict(lfo1_dest=1, lfo1_depth=0.58, lfo1_rate=0.67, osc2_level=0.8, osc2_wave=SQ,
                   cutoff=0.68)),
    (80, 5): ("Shmoog", "MoogSquareLead",
              dict(glide=0.15, resonance=0.3, cutoff=0.62)),
    (80, 6): ("LM Square", "MoogSquareLead",
              dict(osc1_wave=0.8, sub_level=0.3, cutoff=0.7)),
    (80, 8): ("Sine Wave", "MoogSquareLead",
              dict(osc1_wave=TRI, sub_level=0.0, cutoff=0.55, resonance=0.0, eg_amount=0.5)),
    # --- leads: saw (81) ------------------------------------------------
    (81, 1): ("Saw", "MoogSawLead",
              dict(osc2_level=0.0, cutoff=0.75, resonance=0.0, eg_amount=0.55)),
    (81, 2): ("Pulse Saw", "MoogSawLead",
              dict(osc2_wave=0.85, osc2_freq=c(4))),
    (81, 3): ("Feline GR", "MoogSawLead",
              dict(eg_amount=0.85, f_decay=0.36, f_sustain=0.4, resonance=0.45, glide=0.05)),
    (81, 4): ("Big Lead", "MoogSawLead",
              dict(osc2_freq=c(15), sub_level=0.5, cutoff=0.68)),
    (81, 5): ("Velo Lead", "MoogSawLead",
              dict(resonance=0.25, eg_amount=0.8)),
    (81, 6): ("GR-300", "MoogSawLead",
              dict(osc1_wave=SQ, osc2_wave=SQ, osc2_octave=4, osc2_freq=0.5, cutoff=0.65)),
    (81, 7): ("LA Saw", "MoogSawLead",
              dict(noise_level=0.15, f_decay=0.12, eg_amount=0.85)),
    (81, 8): ("Doctor Solo", "MoogSawLead",
              dict(lfo1_dest=1, lfo1_depth=0.58, lfo1_rate=0.66, cutoff=0.62)),
    (81, 16): ("Waspy Synth", "MoogSawLead",
               dict(sync=True, osc2_freq=0.8, resonance=0.35, cutoff=0.7)),
    # --- other leads ------------------------------------------------------
    (82, 1): ("Vent Synth", "MoogCalliopeLead",
              dict(noise_level=0.25, osc1_wave=TRI, cutoff=0.6)),
    (82, 2): ("PurePanLead", "MoogCalliopeLead",
              dict(osc1_wave=TRI, noise_level=0.15, a_attack=0.06, cutoff=0.55)),
    (84, 8): ("Dist.Lead", "MoogCharangLead",
              dict(osc1_wave=SAW, osc2_wave=SAW, cutoff=0.7, resonance=0.2)),
    (86, 1): ("Big Fives", "MoogFifthsLead",
              dict(sub_level=0.5, cutoff=0.66)),
    (87, 1): ("Big & Raw", "MoogBassLead",
              dict(osc1_wave=SAW, osc2_wave=SQ, osc2_octave=16, cutoff=0.65, resonance=0.25)),
    (87, 2): ("Fat & Perky", "MoogBassLead",
              dict(osc1_wave=SQ, sub_level=0.6, f_decay=0.15, eg_amount=0.85, resonance=0.3)),
    # --- pads -------------------------------------------------------------
    (88, 1): ("Fantasia 2", "MoogNewAgePad",
              dict(mf104_on=True, mf104_time=0.55, mf104_feedback=0.4, mf104_mix=0.35)),
    (89, 1): ("Thick Pad", "MoogWarmPad",
              dict(sub_level=0.5, osc2_freq=c(14))),
    (89, 2): ("Horn Pad", "MoogWarmPad",
              dict(f_attack=0.2, a_attack=0.2, eg_amount=0.75, cutoff=0.5)),
    (89, 3): ("RotaryStrng", "MoogWarmPad",
              dict(lfo1_dest=0, lfo1_depth=0.68, lfo1_rate=0.72, cutoff=0.6)),
    (89, 4): ("Soft Pad", "MoogWarmPad",
              dict(cutoff=0.49, a_attack=0.45, f_attack=0.45)),
    (90, 1): ("80'sPolySyn", "MoogPolysynthPad",
              dict(osc2_freq=c(8), f_decay=0.3, f_sustain=0.5, eg_amount=0.7, cutoff=0.6)),
    (91, 1): ("Heaven II", "MoogChoirPad",
              dict(mf104_on=True, mf104_time=0.6, mf104_feedback=0.45, mf104_mix=0.35)),
    (93, 1): ("Tine Pad", "MoogMetallicPad",
              dict(a_decay=0.55, a_sustain=0.4)),
    (93, 2): ("Panner Pad", "MoogMetallicPad",
              dict(key_pan_spread=0.6, lfo1_dest=0, lfo1_depth=0.66, lfo1_rate=0.3)),
    (95, 1): ("Polar Pad", "MoogSweepPad",
              dict(lfo1_rate=0.3)),
    (95, 8): ("Converge", "MoogSweepPad",
              dict(mod_dest=1, mod_amount=0.45)),
    (95, 9): ("Shwimmer", "MoogSweepPad",
              dict(lfo1_dest=2, lfo1_depth=0.8, lfo1_rate=0.45)),
    (95, 10): ("CelestialPd", "MoogSweepPad",
               dict(osc2_octave=4, mf104_on=True, mf104_time=0.6, mf104_mix=0.35)),
    # --- FX pads and bells ------------------------------------------------
    (96, 1): ("Harmo Rain", "MoogRainFX",
              dict(osc2_freq=0.5, cutoff=0.66)),
    (96, 2): ("AfricanWood", "MoogRainFX",
              dict(osc2_level=0.0, osc1_level=1.0, cutoff=0.55, resonance=0.6, eg_amount=0.85,
                   f_decay=0.1, a_decay=0.2, mf104_feedback=0.25, mf104_mix=0.25)),
    (96, 8): ("Clavi Pad", "MoogRainFX",
              dict(osc1_wave=0.85, f_decay=0.15, eg_amount=0.8, a_sustain=0.7)),
    (97, 1): ("Ancestral", "MoogSoundtrackPad",
              dict(cutoff=0.5)),
    (97, 2): ("Prologue", "MoogSoundtrackPad",
              dict(cutoff=0.62, mf104_on=True, mf104_time=0.55, mf104_mix=0.3)),
    (97, 8): ("Rave", "MoogSoundtrackPad",
              dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(25), a_attack=0.0, f_attack=0.0,
                   a_decay=0.35, a_sustain=0.3, cutoff=0.65)),
    (98, 1): ("Syn Mallet", "MoogCrystalFX", dict(a_decay=0.4, mod_amount=0.58)),
    # "soft" is the strike, not the level: the filter opened half as far
    # (eg_amount), a little lower, a 0.04 attack -- centroid 5.3 -> 3.0 kHz on
    # Tokei's part; Ben chose it by ear (C) over a plain -4 dB
    (98, 2): ("SoftCrystal", "MoogCrystalFX", dict(mod_amount=0.6, cutoff=0.55, eg_amount=0.55,
                                                   a_attack=0.04)),
    (98, 4): ("Loud Glock", "MoogCrystalFX", dict(mod_amount=0.66, cutoff=0.75)),
    (98, 6): ("Clear Bells", "MoogCrystalFX", dict(mod_amount=0.62, a_decay=0.65)),
    (98, 7): ("X'mas Bell", "MoogCrystalFX", dict(mod_amount=0.68, osc2_freq=0.85)),
    (98, 8): ("Vibra Bells", "MoogCrystalFX", dict(lfo1_dest=1, lfo1_depth=0.58, lfo1_rate=0.62)),
    (98, 9): ("Digi Bells", "MoogCrystalFX", dict(mod_amount=0.7, a_decay=0.5)),
    (98, 16): ("ChoralBells", "MoogCrystalFX", dict(osc1_level=0.6, a_sustain=0.3)),
    (98, 17): ("Air Bells", "MoogCrystalFX", dict(noise_level=0.15, a_attack=0.05)),
    (99, 1): ("Warm Atmos", "MoogAtmosphereFX", dict(cutoff=0.52)),
    (99, 4): ("HollowRels.", "MoogAtmosphereFX", dict(osc1_wave=SQ, a_release=0.6)),
    (99, 6): ("Ambient Pad", "MoogAtmosphereFX",
              dict(a_attack=0.5, f_attack=0.5, mf104_on=True, mf104_time=0.65, mf104_mix=0.35)),
    (101, 1): ("Goblinson", "MoogGoblinsFX", dict(lfo1_rate=0.62)),
    (101, 2): ("50's Sci-Fi", "MoogGoblinsFX",
               dict(osc1_level=0.0, osc2_level=1.0, osc2_wave=TRI, glide=0.4, lfo1_dest=1, lfo1_depth=0.6,
                    lfo1_rate=0.66,
                    cutoff=0.6)),
    (102, 1): ("Echo Bell", "MoogEchoesFX",
               dict(osc1_wave=TRI, osc2_wave=TRI, mod_dest=0, mod_amount=0.62, a_sustain=0.0, a_decay=0.5)),
    (102, 2): ("Echo Pan", "MoogEchoesFX",
               dict(osc1_wave=TRI, osc2_level=0.0, noise_level=0.12, a_attack=0.05)),
    (102, 6): ("Water Piano", "MoogEchoesFX",
               dict(mod_dest=0, mod_amount=0.58, a_decay=0.5, a_sustain=0.2)),
    (103, 1): ("StarTheme 2", "MoogSciFiFX", dict(lfo1_rate=0.55, resonance=0.5)),
    # --- THE SC-88Pro MAP'S, that our GS files play (gs_maps.py; the notes
    # each file gives the tone in brackets) -------------------------------
    # a square lead with a resonant edge and a little glide (storm_pro, 429)
    (80, 10): ("KG Lead", "MoogSquareLead",
               dict(osc2_level=0.7, osc2_wave=SQ, osc2_freq=c(7), sub_level=0.0, cutoff=0.65,
                    resonance=0.35, glide=0.08)),
    # a Prophet-5's two squares, a touch apart, its contour closing to half (River, 15)
    (80, 16): ("P5 Square", "MoogSquareLead",
               dict(osc2_level=0.8, osc2_wave=SQ, osc2_freq=c(6), sub_level=0.0, cutoff=0.66,
                    resonance=0.15, f_decay=0.3, f_sustain=0.5)),
    # an SH-101: one saw and its square sub, a snappy resonant contour (SuwaFF, 1216)
    (81, 29): ("SH-101 Saw", "MoogSawLead",
               sh(osc1_level=0.0, osc2_level=1.0, sub_level=0.4, cutoff=0.62, resonance=0.3, eg_amount=0.75,
                  f_attack=0.0, f_decay=0.25, f_sustain=0.35, a_sustain=1.0, a_release=0.2)),
    # a Juno's saw and pulse, the pulse's width swept by the LFO, detuned (SuwaFF, storm_pro: 2177)
    (87, 3): ("JUNO Rave", "MoogBassLead",
              dict(osc1_wave=SAW, osc2_wave=SQ, osc2_octave=8, osc2_freq=c(18), sub_level=0.3,
                   lfo1_dest=2, lfo1_depth=0.75, lfo1_rate=0.55, cutoff=0.66, resonance=0.2)),
    # the new-age pad's swell with an FM bell on its front (River, 40)
    (88, 3): ("Bell Heaven", "MoogNewAgePad",
              dict(mod_dest=0, mod_amount=0.6, a_decay=0.6, a_sustain=0.4)),
    # stacked saws, an octave over them, a sub under (SuwaFF, 1056)
    (90, 8): ("Power Stack", "MoogPolysynthPad",
              dict(osc1_wave=SAW, osc2_wave=SAW, osc2_octave=4, osc2_freq=c(8), sub_level=0.5,
                   cutoff=0.66, resonance=0.15)),
    # an Oberheim's two saws as a stab: a punch of filter, a short body (storm_pro, 1066)
    (100, 2): ("OB Stab", "MoogBrightnessFX",
               dict(osc2_freq=c(12), cutoff=0.55, eg_amount=0.8, f_decay=0.2, f_sustain=0.3,
                    a_attack=0.0, a_decay=0.3, a_sustain=0.2, a_release=0.15)),
    # the synth drum's falling tone without its noise, closed down nearer a sine (storm_pro, 216)
    (118, 10): ("Sine Perc.", "MoogSynthDrum",
                dict(noise_level=0.0, cutoff=0.5, resonance=0.0, a_decay=0.4)),
    # a resonant spike on a fast contour (River, 180)
    # a dreamy pad: two saws ten cents apart swelling in, the ladder breathing
    # on a slow LFO, a long release, the MF-104M's echo behind it (SENSATIO,
    # 28; its capital the Sci-Fi FX, so it starts from the warm pad)
    (103, 8): ("Dream Pad", "MoogWarmPad",
               dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(10), cutoff=0.58, resonance=0.15,
                    a_attack=0.45, f_attack=0.4, a_release=0.55, lfo1_dest=0, lfo1_depth=0.64,
                    lfo1_rate=0.3, mf104_on=True, mf104_time=0.6, mf104_feedback=0.4, mf104_mix=0.3)),
    # soft brass: the synth brass with its ladder lower and its swell slower
    (63, 1): ("Soft Brass", "MoogSynthBrass2",
              dict(cutoff=0.48, eg_amount=0.6, a_attack=0.2, f_attack=0.25)),
    # white noise: the noise oscillator alone, the ladder open, no contour
    # (sysex_01 192, River 72, SuwaFF 3); Seashore's capital is the ocean drum,
    # so it starts from the Atmosphere FX's panel, which has the noise
    (122, 17): ("White Noise", "MoogAtmosphereFX",
                dict(osc1_level=0.0, osc2_level=0.0, sub_level=0.0, noise_level=1.0, cutoff=1.0,
                     resonance=0.0, eg_amount=0.5, a_attack=0.0, a_sustain=1.0, a_release=0.1)),
    (39, 21): ("Spike Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, sub_level=0.4, cutoff=0.45, resonance=0.55, eg_amount=0.85,
                    f_decay=0.1, f_sustain=0.1)),
    # --- the Minimoog's (MINIMOOG: fitted to a Model D's held bass) ---------
    # its bass, the fitted patch itself
    (39, 4): ("MG Bass", "MoogSynthBass2", mg()),
    # the second oscillator an octave UNDER, the ladder lower and plucked
    (39, 6): ("MG Oct Bass2", "MoogSynthBass2",
              mg(osc2_octave=16, cutoff=0.6, eg_amount=0.7, f_attack=0.0, f_decay=0.3, f_sustain=0.35)),
    # a blip: the contour flicks OSC 2's pitch and snaps the ladder shut, a short body
    (39, 7): ("MG Blip Bs:", "MoogSynthBass2",
              mg(cutoff=0.55, eg_amount=0.75, f_attack=0.0, f_decay=0.1, f_sustain=0.1, mod_dest=1,
                 mod_amount=0.58, a_decay=0.3, a_sustain=0.3)),
    # OSC 2 a fifth up, at the key's footage
    (39, 25): ("MG 5th Bass", "MoogSynthBass2", mg(osc2_octave=8, osc2_freq=c(700), cutoff=0.68)),
    # the "wow": a resonant ladder opened slowly by the contour and falling back,
    # its bass kept (RES BASS: the resonance cost it 8 dB)
    (39, 27): ("WowMG Bass", "MoogSynthBass2",
               mg(cutoff=0.45, resonance=0.45, res_bass=True, eg_amount=0.8, f_attack=0.15, f_decay=0.35,
                  f_sustain=0.3)),
    # a narrow pulse on both, at unison, the ladder edged with resonance
    (80, 27): ("MG Reso. Pls", "MoogSquareLead",
               mg(osc1_wave=0.8, osc2_wave=0.8, osc2_octave=8, osc2_freq=c(5), cutoff=0.62, resonance=0.55)),
    # its saws: two at unison, a few cents apart
    (81, 24): ("MG Saw 1", "MoogSawLead", mg(osc1_wave=SAW, osc2_wave=SAW, osc2_octave=8, osc2_freq=c(5), cutoff=0.72)),
    # ...the octave stack kept, the ladder lower and opened by the contour
    (81, 25): ("MG Saw 2", "MoogSawLead",
               mg(osc1_wave=SAW, osc2_wave=SAW, cutoff=0.66, eg_amount=0.65, f_decay=0.4, f_sustain=0.5)),
    # the lead: saws a little wider apart, an edge of resonance, a glide
    (81, 31): ("MG Saw Lead", "MoogSawLead",
               mg(osc1_wave=SAW, osc2_wave=SAW, osc2_octave=8, osc2_freq=c(7), cutoff=0.7, resonance=0.2,
                  glide=0.05)),
    # unison: the saws wide apart and the sub under them
    (81, 34): ("MG unison", "MoogSawLead",
               mg(osc1_wave=SAW, osc2_wave=SAW, osc2_octave=8, osc2_freq=c(15), sub_level=0.4, cutoff=0.7)),
    # --- the Oberheim's (OBERHEIM: fitted to an OB-8's held chords) --------
    # its brass: two saws apart (Analogist's detuned takes split ~15 cents),
    # the 2-pole ladder swelling open and settling, a soft attack
    (63, 9): ("OB Brass", "MoogSynthBrass2",
              ob(osc2_wave=SAW, osc2_freq=c(12), cutoff=0.5, eg_amount=0.7, f_attack=0.15, f_decay=0.5,
                 f_sustain=0.5, a_attack=0.05)),
    # two squares, a little apart
    (80, 17): ("OB Square", "MoogSquareLead", ob(osc1_wave=SQ, osc2_wave=SQ, osc2_freq=c(6), cutoff=0.65)),
    # its saws: both saws, a few cents apart, the ladder a little more open
    (81, 26): ("OB Saw 1", "MoogSawLead", ob(osc2_wave=SAW, osc2_freq=c(7), cutoff=0.66)),
    # ...wider apart, the contour opening the ladder on each note
    (81, 27): ("OB Saw 2", "MoogSawLead",
               ob(osc2_wave=SAW, osc2_freq=c(12), cutoff=0.6, eg_amount=0.65, f_decay=0.4, f_sustain=0.5)),
    # the lead: an edge of resonance (its bass kept: RES BASS) and a glide
    (81, 32): ("OB Saw Lead", "MoogSawLead",
               ob(osc2_wave=SAW, osc2_freq=c(9), cutoff=0.68, resonance=0.2, res_bass=True, glide=0.05)),
    # --- the Juno's (JUNO: fitted to a Juno-6's notes) ---------------------
    # its organ: the square pulse and the sub, the filter open, a gate for a
    # contour, CHORUS II (the organ's capital is no Moog: the square lead's)
    (16, 26): ("JUNO Organ", "MoogSquareLead",
               juno(osc1_wave=SQ, osc1_level=0.8, osc2_level=0.0, sub_level=0.5, cutoff=0.85, eg_amount=0.5,
                    a_decay=0.6, a_sustain=1.0, a_release=0.08, insertion_efx=JUNO_CHORUS2)),
    # its strings, from the Open Pad's oscillators (its pulse, saw and sub:
    # 0.85 / 0.48, 0.66, 0.42; 8 dB rms, the PWM and chorus moving them): the
    # filter open, a 0.25 s swell, the pulse's width swept by LFO 1, CHORUS I
    (51, 2): ("JUNO Strings", "MoogSynthStrings2",
              juno(osc1_wave=0.854, osc1_level=0.478, osc2_level=0.659, sub_level=0.419, resonance=0.27,
                   cutoff=0.8, eg_amount=0.5, a_attack=0.3, a_decay=0.6, a_sustain=1.0, a_release=0.45,
                   lfo1_dest=2, lfo1_depth=0.68, lfo1_rate=0.4)),
    # the sub up front: the pulse and the square an octave under it, held
    (84, 24): ("JUNO Sub Osc", "MoogSquareLead",
               juno(osc1_wave=SQ, osc1_level=0.6, osc2_level=0.5, sub_level=0.9, cutoff=0.6, eg_amount=0.62,
                    f_decay=0.5, f_sustain=0.4, a_decay=0.6, a_sustain=1.0)),
    # the Sine Pluck: the ladder ringing alone an octave over the key (it
    # tracks 1:1), falling 22 dB a second -- the oscillators off; FM off
    (98, 20): ("JUNO Bell", "MoogCrystalFX",
               juno(osc1_level=0.0, osc2_level=0.0, sub_level=0.0, resonance=1.0, kb_track=1.0, cutoff=0.532,
                    eg_amount=0.5, mod_amount=0.5, a_decay=0.581, a_sustain=0.0, a_release=0.581)),
    # --- the TB-303's (TB303: fitted to a TB-303's note) --------------------
    # a second voicing: the peak lower, the decay longer
    (38, 11): ("TB303 Bass 2", "MoogSynthBass1", tb(resonance=0.5, f_decay=0.36)),
    # a kick under it: OSC 2 a triangle at the key, its pitch thrown up 1.5
    # octaves by the contour and falling with it -- the kick's sweep, ~185 Hz
    # down to the fundamental on a C2
    (38, 12): ("Kicked TB303", "MoogSynthBass1",
               tb(osc2_wave=TRI, osc2_level=0.9, osc2_octave=8, mod_dest=1, mod_amount=0.65)),
    # its saw, plain, a little more open and less resonant
    (38, 13): ("TB303 Saw Bs", "MoogSynthBass1", tb(osc1_wave=SAW, cutoff=0.6, resonance=0.45)),
    # rubbery: a slower, shallower sweep, the peak softer
    (38, 14): ("Rubber303 Bs", "MoogSynthBass1", tb(cutoff=0.55, resonance=0.45, eg_amount=0.62, f_decay=0.45)),
    # the peak pushed up and the sweep deeper
    (38, 15): ("Reso 303 Bs", "MoogSynthBass1", tb(resonance=0.7, eg_amount=0.72)),
    # its square (the 303's, made from the saw)
    (38, 17): ("303 Sqr Bs", "MoogSynthBass1", tb(osc1_wave=SQ)),
    # through distortion, the module's own Distortion type
    (38, 18): ("TB303 DistBs", "MoogSynthBass1", tb(insertion_efx=TB_DIST)),
    # the 303 as a lead: held, the sweep longer
    (83, 1): ("TB Lead", "MoogSawLead", tb(osc1_wave=SAW, cutoff=0.62, f_decay=0.4, a_sustain=1.0, a_release=0.2)),
    # acid through the charang's valve: the 303's saw and peak, held
    (84, 9): ("Acid Guitar1", "MoogCharangLead", tb(osc1_wave=SAW, a_sustain=1.0, a_release=0.2)),
    # ...its square, the peak higher
    (84, 10): ("Acid Guitar2", "MoogCharangLead", tb(osc1_wave=SQ, resonance=0.68, a_sustain=1.0, a_release=0.2)),
}




# THE OTHER MAPS' OWN SYNTH TONES (patch_map's map switch, bank select LSB):
# where a map holds a different tone under a number than ours does. Keyed
# (map, program, bank); map 1 the SC-55mkII's map, 2 the SC-88's.
MAP_SYNTH = {
    (1, 62, 16): ("Analog Brs1", "MoogSynthBrass1",
                  dict(osc2_freq=c(14), f_attack=0.2, eg_amount=0.7, cutoff=0.5, a_attack=0.12)),
    (1, 63, 16): ("Analog Brs2", "MoogSynthBrass2",
                  dict(osc2_freq=c(18), f_attack=0.3, a_attack=0.2, cutoff=0.47,
                       lfo1_dest=1, lfo1_depth=0.57, lfo1_rate=0.6)),
    (2, 39, 8): ("Beef FMBass", "MoogSynthBass2",
                 dict(osc1_wave=TRI, osc2_wave=TRI, osc2_level=1.0, osc2_octave=8, osc2_freq=0.5,
                      osc1_level=0.0, mod_dest=0, mod_amount=0.66, sub_level=0.6, cutoff=0.58,
                      resonance=0.1, f_decay=0.25, f_sustain=0.35)),
}


# THE SC-8850 MAP'S OWN SYNTH TONES, the GM 2 sound set's (patch_map.gm2_bank
# finds a GM 2 tone by name): {(program, bank): (name, the capital's Moog
# class, panel changes)}, voiced from what each name is -- starting points for
# Ben's ear, as SC88_SYNTH's. A slot an earlier map used for another tone is
# keyed under the SC-8850's map (patch_map: 128 x 4 + bank). An optional
# fourth field is the class's own settings over its base's (moog_unison).
SC8850_SYNTH = {
    # a clavinet's bite from a narrow pulse: a sharp filter blip, a short body
    (7, 39): ("Pulse Clav", "MoogSynthBass1",
              dict(osc1_wave=0.88, osc2_level=0.0, sub_level=0.0, cutoff=0.6, resonance=0.25, eg_amount=0.7,
                   f_decay=0.1, f_sustain=0.1, a_decay=0.3, a_sustain=0.15, kb_track=0.8)),
    # the same pulse a bass: the clav's snap over a sub
    (38, 19): ("Clavi Bass", "MoogSynthBass1",
               dict(osc1_wave=0.85, osc2_level=0.0, sub_level=0.35, cutoff=0.5, resonance=0.3, eg_amount=0.75,
                    f_decay=0.1, f_sustain=0.1, a_decay=0.35, a_sustain=0.2)),
    # a bass struck, not blown: the filter thrown wide for an instant and shut
    (38, 20): ("Hammer", "MoogSynthBass1",
               dict(osc1_wave=SAW, osc2_level=0.0, sub_level=0.5, cutoff=0.44, resonance=0.3, eg_amount=0.92,
                    f_decay=0.06, f_sustain=0.12, a_decay=0.4, a_sustain=0.35)),
    # a pulse bass with a click on its front: the contour's attack the whole tone
    (39, 29): ("Attack Pulse", "MoogSynthBass2",
               dict(osc1_wave=0.8, sub_level=0.3, cutoff=0.5, resonance=0.2, eg_amount=0.9, f_decay=0.05,
                    f_sustain=0.25)),
    # a vocal pad from two detuned saws, a resonant formant-like peak, slow
    (54, 19): ("Analog Voice", "MoogSynthVoice",
               dict(osc1_wave=SAW, osc2_wave=SAW, osc2_level=0.9, osc2_freq=c(8), cutoff=0.55, resonance=0.35,
                    a_attack=0.3, a_release=0.36, lfo1_dest=1, lfo1_depth=0.57, lfo1_rate=0.6)),
    # a polysynth brass, polished (the Prophet's): a moderate swell, detuned
    (62, 8): ("Pro Brass", "MoogSynthBrass1",
              dict(osc2_freq=c(10), f_attack=0.15, eg_amount=0.6, cutoff=0.55, a_attack=0.08)),
    # the OB-Xa's stab ("Jump"): bright detuned saws, a fast front, short
    (62, 5): ("Jump Brass", "MoogSynthBrass1",
              dict(osc2_freq=c(12), f_attack=0.05, eg_amount=0.55, cutoff=0.6, a_attack=0.02, a_release=0.12)),
    # brass sforzando: a hard filter peak and a fall to a held tone
    (63, 8): ("SynBrass sfz", "MoogSynthBrass2",
              dict(eg_amount=0.85, f_attack=0.03, f_decay=0.3, f_sustain=0.25, a_attack=0.02, cutoff=0.5)),
    # a saw lead played as a singer: rounder, a gentle glide
    (81, 36): ("Natural Lead", "MoogSawLead",
               dict(cutoff=0.58, resonance=0.1, glide=0.05, a_attack=0.06)),
    # a sequencer's saw: plucked by its contour, resonant
    (81, 46): ("SequencedSaw", "MoogSawLead",
               dict(f_decay=0.15, f_sustain=0.1, a_decay=0.3, a_sustain=0.2, resonance=0.4, eg_amount=0.7)),
    # a hard-synced lead: OSC 2 sweeping against OSC 1, wiry
    (84, 1): ("Wire Lead", "MoogCharangLead",
              dict(osc1_level=0.3, osc2_level=1.0, osc2_wave=SAW, sync=True, osc2_freq=0.8, cutoff=0.65,
                   eg_amount=0.6)),
    # near a sine: triangles through a low ladder, a slow swell
    (89, 5): ("Sine Pad", "MoogWarmPad",
              dict(osc1_wave=TRI, osc2_wave=TRI, osc2_freq=c(4), cutoff=0.5, resonance=0.0)),
    # the JD-800's airy choir: saws and noise, the cutoff drifting slowly
    (91, 3): ("Itopia", "MoogChoirPad",
              dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(7), cutoff=0.55, resonance=0.2, a_attack=0.4,
                   lfo1_dest=0, lfo1_depth=0.62, lfo1_rate=0.3)),

    # --- THE JP-8000's and its saw stacks: a fourth field, the class's own
    # settings -- moog_unison, the supersaw (SUPERSAW, fitted to a player's
    # JD-Xi take: examples/supersaw_fit.py; Ben: "Supersaw sounds great") ----
    # the supersaw itself: one saw a voice, open, held
    (81, 15): ("JP SuperSaw", "MoogSawLead",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.95, resonance=0.0, eg_amount=0.5, kb_track=1.0,
                    a_attack=0.0, a_sustain=1.0, a_release=0.3),
               dict(moog_unison=SUPERSAW)),
    # the JP-8000's plain saw, as a player's take reads it (Freesound 275439,
    # CC0: "a real Roland JP-8000 Saw wave"): its harmonics 5-8 dB under a 1/k
    # saw's from the 2nd on -- the fundamental stood up, as a triangle at the
    # pitch beside the saw does (the init patch's second oscillator)
    (81, 10): ("JP8000 Saw", "MoogSawLead",
               dict(osc1_wave=SAW, osc2_wave=TRI, osc2_freq=0.5, osc2_level=0.6, cutoff=0.95, resonance=0.0,
                    eg_amount=0.5, a_sustain=1.0, a_release=0.25)),
    # two saws a dozen cents apart: the Jupiter's (JUPITER) and the Oberheim's
    (81, 13): ("JP DoubleSaw", "MoogSawLead",
               jp(osc2_freq=c(-12), cutoff=0.8, eg_amount=0.5, a_sustain=1.0, a_release=0.25)),
    (81, 12): ("OB DoubleSaw", "MoogSawLead",
               ob(osc2_wave=SAW, osc2_level=0.8, osc2_freq=c(-12), cutoff=0.7, a_release=0.25)),
    # FAT: a smaller stack -- three saws, then five -- under the saw lead's own
    (81, 9): ("Fat Saw Lead", "MoogSawLead", dict(osc2_level=0.0),
              dict(moog_unison=dict(SUPERSAW, voices=3, cents=12.0, drift_cents=10.0))),
    (81, 14): ("FatSawLead 2", "MoogSawLead", dict(osc2_level=0.0),
               dict(moog_unison=dict(SUPERSAW, voices=5, cents=18.0, drift_cents=18.0))),
    # techno's: the supersaw closed down, its filter snapping open on each key
    (81, 47): ("Techno Saw", "MoogSawLead",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.6, resonance=0.35, eg_amount=0.75, f_attack=0.0,
                    f_decay=0.2, f_sustain=0.3, a_sustain=1.0, a_release=0.2),
               dict(moog_unison=SUPERSAW)),
    # TWM, the JP-8000's triangle wave modulation: a triangle whose shape LFO 1
    # turns (the panel's wave modulation), a second a few cents off
    (80, 7): ("JP8000 TWM", "MoogSquareLead",
              dict(osc1_wave=TRI, osc2_wave=TRI, osc2_freq=c(-6), osc2_level=0.6, cutoff=0.8, resonance=0.0,
                   eg_amount=0.5, lfo1_dest=2, lfo1_depth=0.8, lfo1_rate=0.55, a_sustain=1.0, a_release=0.2)),
    # its FEEDBACK oscillator, a saw fed back on itself -- read as 1 -> 2 FM
    # on a saw pair, a buzzing, phasing edge
    (84, 26): ("JP8000Fd Osc", "MoogCharangLead",
               dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(3), mod_dest=0, mod_amount=0.62, cutoff=0.8)),
    # its distortion lead: the supersaw, smaller, into the charang's valve
    (80, 31): ("JP8000DistLd", "MoogCharangLead",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.75, resonance=0.2),
               dict(moog_unison=dict(SUPERSAW, voices=5, cents=15.0, drift_cents=15.0))),
    # its fifths: the fifths lead's saws (OSC 2 a fifth up) stacked
    (86, 5): ("JP 5th Saw", "MoogFifthsLead", dict(cutoff=0.8, a_sustain=1.0),
              dict(moog_unison=dict(SUPERSAW, voices=5, cents=15.0, drift_cents=15.0))),
    (86, 6): ("JP8000 5thFB", "MoogFifthsLead", dict(cutoff=0.8, mod_dest=0, mod_amount=0.6, a_sustain=1.0)),
}
