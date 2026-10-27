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
# ...and the others a tone's name asks for (gsefx.TYPES), at their own defaults
FX_PAN = ((0x01, 0x26), {})           # Auto Pan
FX_DELAY = ((0x01, 0x50), {})         # Stereo Delay
FX_LOFI = ((0x01, 0x72), {})          # Lo-Fi 1
FX_PHASER = ((0x01, 0x20), {})        # Phaser
FX_OD = ((0x01, 0x10), {})            # Overdrive


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
    # the Prophet VS's (its vector organ): a square with a triangle an octave
    # up, the filter open, a gate for a contour (2026-10-26)
    (16, 28): ("VS Organ", "MoogSquareLead",
               dict(osc1_wave=SQ, osc2_wave=TRI, osc2_octave=4, osc2_freq=0.5, osc2_level=0.6, sub_level=0.0,
                    cutoff=0.8, eg_amount=0.5, a_decay=0.6, a_sustain=1.0, a_release=0.08)),
    # a synth harpsichord: narrow pulses an octave apart, plucked shut
    (6, 32): ("Synth Harpsi", "MoogSquareLead",
              dict(osc1_wave=0.85, osc2_wave=0.85, osc2_octave=4, osc2_freq=0.5, osc2_level=0.6, sub_level=0.0,
                   cutoff=0.7, eg_amount=0.75, f_attack=0.0, f_decay=0.15, f_sustain=0.1, a_decay=0.6,
                   a_sustain=0.0, a_release=0.3)),
    # an analog clav: the Jupiter's clav (JP8 Clav. 1) on a plain pulse
    (7, 32): ("Analog Clav.", "MoogSynthBass1",
              dict(osc1_wave=0.82, osc2_level=0.0, sub_level=0.0, cutoff=0.6, eg_amount=0.75, f_attack=0.0,
                   f_decay=0.12, f_sustain=0.1, a_decay=0.3, a_sustain=0.1, a_release=0.15, kb_track=0.8)),
    # a synth harp: a plucked pulse ringing out
    # a synth shamisen: a plucked pulse, nasal, short
    (106, 8): ("Syn Shamisen", "MoogSquareLead",
               dict(osc1_wave=0.85, osc2_level=0.0, sub_level=0.0, cutoff=0.6, resonance=0.5, eg_amount=0.75,
                    f_attack=0.0, f_decay=0.12, f_sustain=0.0, a_decay=0.5, a_sustain=0.0, a_release=0.3)),
    (46, 16): ("Synth Harp", "MoogSquareLead",
               dict(osc1_wave=0.75, osc2_level=0.0, sub_level=0.0, cutoff=0.68, eg_amount=0.7, f_attack=0.0,
                    f_decay=0.3, f_sustain=0.0, a_decay=0.8, a_sustain=0.0, a_release=0.6)),
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

    # --- THE SC-88 PRO's OTHER LEADS (2026-10-26): what each name is, on
    # the capital's panel or the synth it names ---------------------------
    # a sine with a player's vibrato
    (80, 9): ("Sine Lead", "MoogSquareLead",
              dict(osc1_wave=TRI, osc2_level=0.0, sub_level=0.0, cutoff=0.5, resonance=0.0, eg_amount=0.5,
                   lfo1_dest=1, lfo1_depth=0.56, lfo1_rate=0.66)),
    # two narrow pulses a few cents apart
    (80, 24): ("Pulse Lead", "MoogSquareLead",
               dict(osc1_wave=0.85, osc2_wave=0.85, osc2_level=0.6, osc2_freq=c(5), sub_level=0.0, cutoff=0.72)),
    # PULSE-WIDTH MODULATION: a square whose width LFO 1 sweeps
    (81, 17): ("PM Lead", "MoogSawLead",
               dict(osc1_wave=SQ, osc2_level=0.0, lfo1_dest=2, lfo1_depth=0.78, lfo1_rate=0.5, cutoff=0.72)),
    # the Prophet-5's saws (P5 Square's pair), its contour closing to half
    (81, 33): ("P5 Saw Lead", "MoogSawLead",
               dict(osc2_level=0.8, osc2_wave=SAW, osc2_freq=c(6), sub_level=0.0, cutoff=0.68,
                    resonance=0.15, f_decay=0.3, f_sustain=0.5)),
    # a saw with its octave over it
    (81, 35): ("Oct Saw Lead", "MoogSawLead",
               dict(osc2_wave=SAW, osc2_octave=4, osc2_freq=c(3), osc2_level=0.6, cutoff=0.72)),
    # a sequencer's saw: plucked short, the filter snapping shut
    (81, 40): ("SequenceSaw1", "MoogSawLead",
               dict(osc2_level=0.0, cutoff=0.58, resonance=0.3, eg_amount=0.75, f_attack=0.0, f_decay=0.15,
                    f_sustain=0.2, a_decay=0.3, a_sustain=0.3, a_release=0.12)),
    (81, 41): ("SequenceSaw2", "MoogSawLead",
               dict(osc2_level=0.0, cutoff=0.55, resonance=0.5, eg_amount=0.78, f_attack=0.0, f_decay=0.12,
                    f_sustain=0.15, a_decay=0.25, a_sustain=0.25, a_release=0.12)),
    # the peak up, the contour opening it
    (81, 42): ("Reso Saw", "MoogSawLead",
               dict(osc2_level=0.0, cutoff=0.62, resonance=0.6, eg_amount=0.65, f_decay=0.35, f_sustain=0.4)),
    # CHEESE: two saws well apart under a quick vibrato -- the cheap lead
    (81, 43): ("Cheese Saw 1", "MoogSawLead",
               dict(osc2_freq=c(15), cutoff=0.7, lfo1_dest=1, lfo1_depth=0.57, lfo1_rate=0.66)),
    (81, 44): ("Cheese Saw 2", "MoogSawLead",
               dict(osc2_octave=4, osc2_freq=c(10), osc2_level=0.6, cutoff=0.72, lfo1_dest=1, lfo1_depth=0.57,
                    lfo1_rate=0.66)),
    # RHYTHMIC: LFO 1's square chopping the cutoff, five times a second
    (81, 45): ("Rhythmic Saw", "MoogSawLead",
               dict(osc2_level=0.0, cutoff=0.6, resonance=0.3, lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.72,
                    lfo1_rate=0.68)),
    # mad: two saws far apart and one modulating the other
    (83, 8): ("Mad Lead", "MoogChiffLead",
              dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(30), mod_dest=0, mod_amount=0.6, resonance=0.3,
                   cutoff=0.7)),
    # SYNC: OSC 2 restarting on OSC 1, its frequency swept by the contour --
    # the Prophet-5's (P5), fat (a sub under it), at a fifth, down a decay,
    # dirty (the peak up, into the charang's valve)
    (84, 16): ("P5 Sync Lead", "MoogSawLead",
               dict(sync=True, osc2_wave=SAW, osc2_freq=0.85, osc1_level=0.0, osc2_level=0.8, mod_dest=1,
                    mod_amount=0.68, f_decay=0.4, f_sustain=0.3, cutoff=0.75)),
    (84, 17): ("Fat SyncLead", "MoogSawLead",
               dict(sync=True, osc2_wave=SAW, osc2_freq=0.85, osc2_level=0.8, sub_level=0.5, mod_dest=1,
                    mod_amount=0.66, f_decay=0.4, f_sustain=0.4, cutoff=0.72)),
    (84, 18): ("Rock Lead", "MoogCharangLead",
               dict(osc1_wave=SAW, osc2_wave=SQ, osc2_freq=c(-7), cutoff=0.7, resonance=0.15)),
    (84, 19): ("5th DecaSync", "MoogSawLead",
               dict(sync=True, osc2_wave=SAW, osc2_freq=1.0, osc2_level=0.8, mod_dest=1, mod_amount=0.7,
                    f_decay=0.3, f_sustain=0.0, a_decay=0.5, a_sustain=0.4, cutoff=0.72)),
    (84, 20): ("Dirty Sync", "MoogCharangLead",
               dict(sync=True, osc2_wave=SAW, osc2_freq=0.85, osc2_level=0.8, mod_dest=1, mod_amount=0.66,
                    resonance=0.35, cutoff=0.68)),
    # the voice lead with a vibrato; LFO 1 walking its formant
    (85, 8): ("Vox Lead", "MoogVoiceLead", dict(lfo1_dest=1, lfo1_depth=0.56, lfo1_rate=0.66)),
    (85, 9): ("LFO Vox", "MoogVoiceLead", dict(lfo1_dest=0, lfo1_depth=0.7, lfo1_rate=0.55)),
    # fifths: plain, a clav's snap on a narrow pulse, and fourths
    (86, 2): ("5th Lead", "MoogFifthsLead", dict(cutoff=0.75)),
    (86, 3): ("5th Ana.Clav", "MoogFifthsLead",
              dict(osc1_wave=0.85, osc2_wave=0.85, cutoff=0.62, eg_amount=0.75, f_attack=0.0, f_decay=0.12,
                   f_sustain=0.1, a_decay=0.3, a_sustain=0.1, a_release=0.15)),
    (86, 8): ("4th Lead", "MoogFifthsLead", dict(osc2_freq=c(500), cutoff=0.75)),

    # --- THE SC-88 PRO's OTHER SYNTH BASSES (2026-10-26) --------------------
    (38, 5): ("P5 Bass", "MoogSynthBass1",
              dict(osc1_wave=SAW, osc2_wave=SQ, osc2_level=0.6, osc2_freq=c(6), cutoff=0.5, resonance=0.2,
                   eg_amount=0.72, f_decay=0.25, f_sustain=0.3)),
    # short and bright for an arpeggiator's run
    (38, 24): ("Arpeggio Bs", "MoogSynthBass1",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.52, resonance=0.35, eg_amount=0.8, f_decay=0.12,
                    f_sustain=0.1, a_decay=0.3, a_sustain=0.2, a_release=0.08)),
    (39, 5): ("Mg Oct Bass1", "MoogSynthBass2",
              mg(osc2_octave=16, osc2_level=0.7, cutoff=0.5, eg_amount=0.7, f_decay=0.3, f_sustain=0.3)),
    # cross modulation (1 -> 2 FM) for the wire's edge; synced for the second
    (39, 10): ("X Wire Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_wave=SAW, mod_dest=0, mod_amount=0.66, cutoff=0.55, eg_amount=0.7,
                    f_decay=0.25, f_sustain=0.3)),
    (39, 11): ("WireStr Bass", "MoogSynthBass2",
               dict(sync=True, osc2_wave=SAW, osc2_freq=0.8, mod_dest=1, mod_amount=0.66, cutoff=0.55,
                    eg_amount=0.7, f_decay=0.3, f_sustain=0.3)),
    (39, 12): ("Blip Bass", "MoogSynthBass2",
               dict(osc1_wave=SQ, osc2_level=0.0, cutoff=0.45, resonance=0.4, eg_amount=0.85, f_decay=0.06,
                    f_sustain=0.05, a_decay=0.2, a_sustain=0.1, a_release=0.06)),
    (39, 13): ("RubberBass 1", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.48, resonance=0.55, eg_amount=0.7, f_decay=0.3,
                    f_sustain=0.25, glide=0.08)),
    (39, 22): ("House Bass:", "MoogSynthBass2",
               dict(osc1_wave=SQ, osc2_wave=TRI, osc2_octave=16, osc2_level=0.6, cutoff=0.5, eg_amount=0.65,
                    f_decay=0.2, f_sustain=0.3, a_decay=0.4, a_sustain=0.5)),
    (39, 23): ("KG Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(8), cutoff=0.52, resonance=0.25, eg_amount=0.7)),
    (39, 24): ("Sync Bass", "MoogSynthBass2",
               dict(sync=True, osc2_wave=SAW, osc2_freq=0.82, mod_dest=1, mod_amount=0.66, cutoff=0.58,
                    eg_amount=0.6)),
    # random: LFO 1's square hopping the cutoff (no sample-and-hold here)
    (39, 26): ("RND Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.5, resonance=0.45, lfo1_dest=0, lfo1_shape=3,
                    lfo1_depth=0.72, lfo1_rate=0.62)),
    (39, 28): ("Bubble Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.47, resonance=0.6, lfo1_dest=0, lfo1_depth=0.7,
                    lfo1_rate=0.6)),

    # --- THE SC-88 PRO's OTHER SYNTH STRINGS, VOICES AND BRASS (2026-10-26)
    # stacked: saws in octaves; the 4th and the high's brighter, airier ones;
    # noise through the strings
    (50, 2): ("StackStrings", "MoogSynthStrings1",
              dict(osc2_octave=4, osc2_freq=c(-5), osc2_level=0.6, cutoff=0.68)),
    (50, 9): ("Syn.Strings4", "MoogSynthStrings1", dict(osc2_freq=c(-10), cutoff=0.72, a_attack=0.25)),
    (50, 16): ("High Strings", "MoogSynthStrings1",
               dict(osc1_octave=4, osc2_octave=4, osc2_freq=c(-8), cutoff=0.78, a_attack=0.2)),
    (50, 25): ("Noiz Strings", "MoogSynthStrings1", dict(noise_level=0.3, cutoff=0.66, a_attack=0.3)),
    (51, 1): ("Syn.Strings5", "MoogSynthStrings2", dict(osc2_freq=c(-12), cutoff=0.62, a_attack=0.35)),
    (51, 8): ("Air Strings", "MoogSynthStrings2", dict(noise_level=0.2, cutoff=0.7, a_attack=0.4, a_release=0.5)),
    # the VP-330's choir: its formant peak, slow, chorused
    (54, 16): ("VP330 Choir", "MoogSynthVoice",
               dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(6), cutoff=0.55, resonance=0.4, a_attack=0.35,
                    a_release=0.45, insertion_efx=JUNO_CHORUS2)),
    (54, 9): ("Silent Night", "MoogSynthVoice",
              dict(osc1_wave=TRI, osc2_wave=SAW, osc2_level=0.4, cutoff=0.5, resonance=0.3, a_attack=0.5,
                   a_release=0.6)),
    # a record's choir: the voice through Lo-Fi 1
    (54, 17): ("Vinyl Choir", "MoogSynthVoice", dict(a_attack=0.3, insertion_efx=FX_LOFI)),
    (62, 2): ("Stack Brass", "MoogSynthBrass1", dict(osc2_octave=4, osc2_freq=c(-6), osc2_level=0.6)),
    # the MKS-80's brass (the Super Jupiter's rack): the Jupiter's saws
    (62, 4): ("MKS Brass", "MoogSynthBrass1",
              jp(osc2_freq=c(-10), cutoff=0.5, eg_amount=0.7, f_attack=0.12, f_decay=0.4, f_sustain=0.5,
                 a_attack=0.04)),
    (63, 2): ("Warm Brass", "MoogSynthBrass2", dict(cutoff=0.45, eg_amount=0.6, f_attack=0.2)),
    (63, 10): ("Reso Brass", "MoogSynthBrass2", dict(resonance=0.5, eg_amount=0.7)),

    # --- THE SC-88 PRO's OTHER PADS AND SYNTH EFFECTS (2026-10-26) ----------
    (88, 2): ("New Age Pad", "MoogNewAgePad", dict(cutoff=0.6, a_attack=0.4)),
    (89, 8): ("Octave Pad", "MoogWarmPad", dict(osc2_octave=4, osc2_level=0.5)),
    (89, 9): ("Stack Pad", "MoogWarmPad", dict(osc2_octave=4, osc2_freq=c(-6), osc2_level=0.6, sub_level=0.3)),
    (90, 2): ("Polysynth 2", "MoogPolysynthPad", dict(osc2_freq=c(10), cutoff=0.6)),
    (90, 3): ("Poly King", "MoogPolysynthPad", dict(osc2_freq=c(12), cutoff=0.68, eg_amount=0.65, sub_level=0.3)),
    (90, 9): ("Octave Stack", "MoogPolysynthPad", dict(osc2_octave=4, osc2_level=0.6, cutoff=0.68)),
    (90, 10): ("Reso Stack", "MoogPolysynthPad", dict(osc2_octave=4, osc2_level=0.6, resonance=0.55, cutoff=0.58)),
    (90, 11): ("Techno Stack", "MoogPolysynthPad",
               dict(osc2_octave=4, osc2_level=0.6, cutoff=0.55, resonance=0.4, eg_amount=0.75, f_decay=0.2,
                    f_sustain=0.2, a_decay=0.4, a_sustain=0.3, a_release=0.2)),
    (91, 2): ("SC Heaven", "MoogChoirPad", dict(cutoff=0.62, a_attack=0.5, a_release=0.7)),
    (91, 8): ("Cosmic Voice", "MoogChoirPad", dict(lfo1_dest=0, lfo1_depth=0.66, lfo1_rate=0.3, a_attack=0.5)),
    (91, 9): ("Auh Vox", "MoogChoirPad", dict(resonance=0.45, cutoff=0.5, eg_amount=0.65, f_attack=0.3)),
    (91, 10): ("AuhAuh", "MoogChoirPad",
               dict(resonance=0.45, cutoff=0.5, lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.7, lfo1_rate=0.5)),
    (91, 11): ("Vocorderman", "MoogChoirPad",
               dict(osc1_wave=SAW, osc2_wave=SQ, osc2_level=0.6, resonance=0.5, cutoff=0.52, a_attack=0.05)),
    (92, 1): ("SoftBellPad", "MoogBowedPad",
              dict(osc1_wave=TRI, osc2_wave=TRI, osc2_freq=c(1400 * 0.5), mod_dest=0, mod_amount=0.6,
                   cutoff=0.6, a_attack=0.3)),
    (92, 3): ("7thBelPad", "MoogBowedPad",
              dict(osc1_wave=TRI, osc2_wave=TRI, osc2_freq=c(1000), osc2_level=0.6, cutoff=0.6, a_attack=0.3)),
    (94, 1): ("Vox Pad", "MoogHaloPad", dict(resonance=0.4, cutoff=0.52)),
    (94, 2): ("Vox Sweep", "MoogHaloPad",
              dict(resonance=0.45, cutoff=0.48, lfo1_dest=0, lfo1_depth=0.7, lfo1_rate=0.25)),
    (94, 8): ("Horror Pad", "MoogHaloPad",
              dict(osc2_freq=c(100), resonance=0.5, cutoff=0.45, lfo1_dest=1, lfo1_depth=0.62, lfo1_rate=0.5)),
    (95, 11): ("Bag Sweep", "MoogSweepPad", dict(osc2_freq=c(700), lfo1_rate=0.25)),
    (97, 3): ("Prologue 2", "MoogSoundtrackPad", dict(cutoff=0.55, a_attack=0.6)),
    (97, 4): ("Hols Strings", "MoogSoundtrackPad", dict(osc2_freq=c(-10), cutoff=0.6, a_attack=0.5)),
    (98, 10): ("Music Bell", "MoogCrystalFX", dict(cutoff=0.7)),
    (98, 11): ("Analog Bell", "MoogCrystalFX",
               dict(osc1_wave=SQ, osc2_wave=SQ, osc2_freq=c(700), mod_dest=0, mod_amount=0.66, cutoff=0.65)),
    (99, 7): ("Invisible", "MoogAtmosphereFX", dict(cutoff=0.5, a_attack=0.5, lfo1_dest=0, lfo1_depth=0.65,
                                                    lfo1_rate=0.3)),
    (99, 8): ("Pulsey Key", "MoogAtmosphereFX", dict(osc1_wave=0.85, osc2_wave=0.85, a_attack=0.0)),
    (100, 1): ("Shining Star", "MoogBrightnessFX", dict(cutoff=0.75, resonance=0.35)),
    (101, 3): ("Abduction", "MoogGoblinsFX", dict(mod_dest=1, mod_amount=0.75, lfo1_dest=1, lfo1_depth=0.7)),
    (101, 4): ("Auhbient", "MoogGoblinsFX", dict(resonance=0.45, cutoff=0.5, a_attack=0.6)),
    (101, 5): ("LFO Pad", "MoogGoblinsFX", dict(lfo1_dest=0, lfo1_depth=0.72, lfo1_rate=0.45)),
    (101, 6): ("Random Str", "MoogGoblinsFX", dict(lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.7, lfo1_rate=0.62)),
    (101, 7): ("Random Pad", "MoogGoblinsFX", dict(lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.7, lfo1_rate=0.55,
                                                  a_attack=0.4)),
    (101, 8): ("LowBirds Pad", "MoogGoblinsFX", dict(lfo1_dest=1, lfo1_depth=0.62, lfo1_rate=0.7, cutoff=0.5)),
    (101, 9): ("Falling Down", "MoogGoblinsFX", dict(mod_dest=1, mod_amount=0.25, f_decay=0.8, f_sustain=0.0)),
    (101, 10): ("LFO RAVE", "MoogGoblinsFX", dict(lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.72, lfo1_rate=0.68)),
    (101, 11): ("LFO Horror", "MoogGoblinsFX", dict(lfo1_dest=1, lfo1_depth=0.68, lfo1_rate=0.55)),
    (101, 12): ("LFO Techno", "MoogGoblinsFX", dict(lfo1_dest=0, lfo1_shape=1, lfo1_depth=0.72, lfo1_rate=0.66,
                                                     resonance=0.45)),
    (101, 13): ("Alternative", "MoogGoblinsFX", dict(osc2_freq=c(600), lfo1_dest=0, lfo1_depth=0.65)),
    (101, 14): ("UFO FX", "MoogGoblinsFX", dict(lfo1_dest=1, lfo1_depth=0.75, lfo1_rate=0.72)),
    (101, 15): ("Gargle Man", "MoogGoblinsFX", dict(resonance=0.55, lfo1_dest=0, lfo1_depth=0.72, lfo1_rate=0.72)),
    (101, 16): ("Sweep FX", "MoogGoblinsFX", dict(resonance=0.5, eg_amount=0.85, f_attack=0.6, f_decay=0.8)),
    (102, 8): ("Pan Sequence", "MoogEchoesFX", dict(a_attack=0.0, a_decay=0.3, a_sustain=0.2,
                                                    insertion_efx=FX_PAN)),
    (102, 9): ("Aqua", "MoogEchoesFX", dict(resonance=0.45, lfo1_dest=0, lfo1_depth=0.66, lfo1_rate=0.4)),
    (103, 9): ("Silky Pad", "MoogSciFiFX", dict(cutoff=0.6, a_attack=0.5, resonance=0.0)),
    (103, 16): ("New Century", "MoogSciFiFX", dict(osc2_freq=c(700), cutoff=0.6)),
    (103, 17): ("7th Atmos.", "MoogSciFiFX", dict(osc2_freq=c(1000), osc2_level=0.6, a_attack=0.4)),
    (103, 18): ("Galaxy Way", "MoogSciFiFX", dict(lfo1_dest=0, lfo1_depth=0.68, lfo1_rate=0.25, a_attack=0.5)),
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
    # the SC-88 Pro's Transbrass where the SC-88 had VeloBrass 2: a brass
    # swelling slowly open, two saws well apart
    (3, 63, 17): ("Transbrass", "MoogSynthBrass2",
                  dict(osc2_freq=c(15), cutoff=0.48, eg_amount=0.75, f_attack=0.25, f_decay=0.6, f_sustain=0.4)),
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

    # --- THE SC-8850's OTHER LEADS (2026-10-26) ---------------------------
    # squares: two sines; a square into the valve; the 303's square through
    # its Distortion (TB_DIST) -- the peak higher, its saw beside; a square
    # and a saw; the Jupiter's narrowest pulse; the ARP 2600's ring
    # modulator (read as 1 -> 2 FM: sum and difference sidebands); the 303's
    # saw distorted; hip-hop's portamento leads; a fast pulse-width sweep
    (80, 11): ("Twin Sine", "MoogSquareLead",
               dict(osc1_wave=TRI, osc2_wave=TRI, osc2_level=0.8, osc2_freq=c(8), sub_level=0.0, cutoff=0.5,
                    resonance=0.0, eg_amount=0.5)),
    (80, 19): ("Dist Square", "MoogCharangLead", dict(osc1_wave=SQ, osc2_level=0.0, cutoff=0.72)),
    (80, 20): ("303SquarDst1", "MoogSquareLead",
               tb(osc1_wave=SQ, insertion_efx=TB_DIST, a_sustain=1.0, a_release=0.2)),
    (80, 21): ("303SquarDst2", "MoogSquareLead",
               tb(osc1_wave=SQ, resonance=0.7, cutoff=0.6, insertion_efx=TB_DIST, a_sustain=1.0, a_release=0.2)),
    (80, 22): ("303 Mix Sqr", "MoogSquareLead",
               tb(osc1_wave=SQ, osc2_wave=SAW, osc2_level=0.6, a_sustain=1.0, a_release=0.2)),
    (80, 23): ("Dual Sqr&Saw", "MoogSquareLead",
               dict(osc1_wave=SQ, osc2_wave=SAW, osc2_level=0.8, osc2_freq=c(6), sub_level=0.0, cutoff=0.72)),
    (80, 28): ("JP8 PulseLd3", "MoogSquareLead",
               jp(osc1_wave=0.92, osc2_wave=0.92, osc2_freq=c(-8), cutoff=0.72, resonance=0.2, a_sustain=1.0,
                  a_release=0.2)),
    (80, 29): ("260RingLead", "MoogSquareLead",
               dict(osc1_wave=SQ, osc2_wave=SQ, osc2_level=0.8, osc2_freq=c(350), mod_dest=0, mod_amount=0.7,
                    sub_level=0.0, cutoff=0.75)),
    (80, 30): ("303DistLead", "MoogSquareLead",
               tb(osc1_wave=SAW, insertion_efx=TB_DIST, a_sustain=1.0, a_release=0.2)),
    (80, 32): ("HipHop SinLd", "MoogSquareLead",
               dict(osc1_wave=TRI, osc2_level=0.0, sub_level=0.0, glide=0.12, cutoff=0.5, eg_amount=0.5)),
    (80, 33): ("HipHop SqrLd", "MoogSquareLead",
               dict(osc1_wave=SQ, osc2_level=0.0, sub_level=0.0, glide=0.12, cutoff=0.6)),
    (80, 34): ("HipHop PlsLd", "MoogSquareLead",
               dict(osc1_wave=0.85, osc2_level=0.0, sub_level=0.0, glide=0.12, cutoff=0.62)),
    (80, 35): ("Flux Pulse", "MoogSquareLead",
               dict(osc1_wave=0.8, osc2_level=0.0, lfo1_dest=2, lfo1_depth=0.8, lfo1_rate=0.62, resonance=0.3,
                    cutoff=0.68)),
    # the calliope's: a pure blown tone, and one breathier
    (82, 8): ("LM Pure Lead", "MoogCalliopeLead", dict(osc1_wave=TRI, noise_level=0.05, cutoff=0.6)),
    (82, 9): ("LM Blow Lead", "MoogCalliopeLead", dict(osc1_wave=TRI, noise_level=0.3, a_attack=0.05, cutoff=0.6)),
    # the chiff lead's: a saw and a square; the stacks in unison (the
    # supersaw's spread, fewer and narrower); forceful, its contour wide;
    # two squares apart
    (83, 2): ("Hybrid Lead", "MoogChiffLead",
              dict(osc1_wave=SAW, osc2_wave=SQ, osc2_level=0.8, osc2_freq=c(5), cutoff=0.72)),
    (83, 3): ("Unison SqrLd", "MoogChiffLead", dict(osc1_wave=SQ, osc2_level=0.0, cutoff=0.72),
              dict(moog_unison=dict(SUPERSAW, voices=5, cents=15.0, drift_cents=12.0))),
    (83, 4): ("FatSolo Lead", "MoogChiffLead", dict(osc1_wave=SAW, osc2_level=0.0, sub_level=0.5, cutoff=0.72),
              dict(moog_unison=dict(SUPERSAW, voices=3, cents=12.0, drift_cents=10.0))),
    (83, 5): ("ForcefulLead", "MoogChiffLead",
              dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(8), cutoff=0.66, eg_amount=0.75, f_decay=0.3,
                   f_sustain=0.5, resonance=0.25)),
    (83, 6): ("Oct.UnisonLd", "MoogChiffLead",
              dict(osc1_wave=SAW, osc2_wave=SAW, osc2_octave=4, osc2_freq=0.5, osc2_level=0.6, cutoff=0.75),
              dict(moog_unison=dict(SUPERSAW, voices=5, cents=15.0, drift_cents=12.0))),
    (83, 7): ("Unison SawLd", "MoogChiffLead", dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.75),
              dict(moog_unison=dict(SUPERSAW, voices=5, cents=15.0, drift_cents=12.0))),
    (83, 9): ("CrowdingLead", "MoogChiffLead", dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.75),
              dict(moog_unison=dict(SUPERSAW, cents=40.0))),
    (83, 10): ("Double Sqr.", "MoogChiffLead",
               dict(osc1_wave=SQ, osc2_wave=SQ, osc2_level=0.8, osc2_freq=c(10), cutoff=0.7)),
    # the charang's: fed back (1 -> 2 FM); Roland's GR guitar synths (GR-300's
    # squares) fat, windy, mellow, and with a pulse; dance guitars through
    # the valve; two synced oscillators; the D-50's brass lead (LA); the
    # ARP 2600's saw over its sub
    (84, 2): ("FB.Charang", "MoogCharangLead", dict(mod_dest=0, mod_amount=0.6)),
    (84, 3): ("Fat GR Lead", "MoogSawLead",
              dict(osc1_wave=SQ, osc2_wave=SQ, osc2_octave=4, osc2_freq=c(6), sub_level=0.4, cutoff=0.66)),
    (84, 4): ("Windy GR Ld", "MoogSawLead",
              dict(osc1_wave=SQ, osc2_wave=SQ, osc2_octave=4, osc2_freq=0.5, noise_level=0.3, cutoff=0.65)),
    (84, 5): ("Mellow GR Ld", "MoogSawLead",
              dict(osc1_wave=SQ, osc2_wave=SQ, osc2_octave=4, osc2_freq=0.5, cutoff=0.55, resonance=0.0)),
    (84, 6): ("GR & Pulse", "MoogSawLead",
              dict(osc1_wave=SQ, osc2_wave=0.85, osc2_octave=8, osc2_freq=c(5), cutoff=0.66)),
    (84, 11): ("Dance Dst.Gt", "MoogCharangLead",
               dict(osc1_wave=SAW, osc2_wave=SQ, osc2_freq=c(-5), cutoff=0.7, a_decay=0.5, a_sustain=0.6)),
    (84, 12): ("DanceDst.Gt2", "MoogCharangLead",
               dict(osc1_wave=SAW, osc2_wave=SQ, osc2_freq=c(-5), cutoff=0.66, resonance=0.35, a_decay=0.5,
                    a_sustain=0.6)),
    (84, 21): ("DualSyncLead", "MoogSawLead",
               dict(sync=True, osc2_wave=SAW, osc2_freq=0.8, osc2_level=0.8, sub_level=0.4, mod_dest=1,
                    mod_amount=0.64, cutoff=0.72),
               dict(moog_unison=dict(SUPERSAW, voices=2, cents=10.0, drift_cents=6.0))),
    (84, 22): ("LA Brass Ld", "MoogSawLead",
               d50(osc2_level=0.6, osc2_freq=c(8), f_attack=0.1, eg_amount=0.65, cutoff=0.6, a_sustain=0.9)),
    (84, 25): ("2600 Sub Osc", "MoogSawLead", dict(osc2_level=0.0, sub_level=0.6, cutoff=0.7)),
    # the voice lead's: another solo voice, and with a second detuned
    (85, 1): ("Solo Vox 2", "MoogVoiceLead", dict(cutoff=0.6, lfo1_dest=1, lfo1_depth=0.55, lfo1_rate=0.64)),
    (85, 10): ("Vox Lead 2", "MoogVoiceLead", dict(osc2_freq=c(8), lfo1_dest=1, lfo1_depth=0.56, lfo1_rate=0.66)),
    # fifths on narrow pulses
    (86, 4): ("5th Pulse", "MoogFifthsLead", dict(osc1_wave=0.85, osc2_wave=0.85, cutoff=0.72)),

    # the JX-8P's organ: the Juno's voice, two squares an octave apart and the
    # sub, through its chorus
    (16, 30): ("JX-8P Organ", "MoogSquareLead",
               juno(osc1_wave=SQ, osc1_level=0.8, osc2_wave=SQ, osc2_octave=4, osc2_level=0.5, sub_level=0.3,
                    cutoff=0.82, eg_amount=0.5, a_decay=0.6, a_sustain=1.0, a_release=0.08,
                    insertion_efx=JUNO_CHORUS1)),

    # synth clavs: ringing (1 -> 2 FM's sidebands), distorted, and the JP-8000's
    # (a supersaw plucked shut)
    (7, 36): ("SynRingClav.", "MoogSynthBass1",
              dict(osc1_wave=SQ, osc2_wave=SQ, osc2_freq=c(700), mod_dest=0, mod_amount=0.66, cutoff=0.62,
                   eg_amount=0.75, f_decay=0.12, f_sustain=0.1, a_decay=0.3, a_sustain=0.1, a_release=0.15)),
    (7, 37): ("SynDistClav.", "MoogSynthBass1",
              dict(osc1_wave=0.82, osc2_level=0.0, cutoff=0.62, eg_amount=0.75, f_decay=0.12, f_sustain=0.1,
                   a_decay=0.3, a_sustain=0.1, a_release=0.15, insertion_efx=TB_DIST)),
    (7, 38): ("JP8000 Clav.", "MoogSynthBass1",
              dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.62, eg_amount=0.75, f_decay=0.12, f_sustain=0.1,
                   a_decay=0.3, a_sustain=0.1, a_release=0.15),
              dict(moog_unison=dict(SUPERSAW, voices=5, cents=15.0, drift_cents=12.0))),

    # an FM slap (a bass's thumb on 1 -> 2 FM, the contour snapping) and a synth
    # yang qin (a struck pulse, bright and short)
    (37, 8): ("FM Slap", "MoogSynthBass2",
              dict(osc1_wave=TRI, osc2_wave=TRI, mod_dest=0, mod_amount=0.68, cutoff=0.6, eg_amount=0.8,
                   f_decay=0.1, f_sustain=0.2, a_decay=0.4, a_sustain=0.3)),
    (46, 26): ("SynthYangQin", "MoogSquareLead",
               dict(osc1_wave=0.82, osc2_wave=TRI, osc2_octave=4, osc2_level=0.5, cutoff=0.72, eg_amount=0.75,
                    f_decay=0.12, f_sustain=0.0, a_decay=0.5, a_sustain=0.0, a_release=0.4)),

    # --- THE SC-8850's OTHER SYNTH BASSES (2026-10-26) ----------------------
    # jungle's: a sine held long and low
    (38, 21): ("Jungle Bass", "MoogSynthBass1",
               dict(osc1_wave=TRI, osc2_level=0.0, sub_level=0.5, cutoff=0.42, resonance=0.0, eg_amount=0.5,
                    a_decay=0.8, a_sustain=0.8, a_release=0.2)),
    (38, 22): ("Square Bass", "MoogSynthBass1", dict(osc1_wave=SQ, osc2_level=0.0, cutoff=0.5, eg_amount=0.65)),
    (38, 23): ("Square Bass2", "MoogSynthBass1",
               dict(osc1_wave=SQ, osc2_level=0.0, cutoff=0.48, resonance=0.45, eg_amount=0.72, f_decay=0.2)),
    # a saw with a hit on its front: the contour thrown wide and shut
    (38, 32): ("Hit&Saw Bass", "MoogSynthBass1",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.45, eg_amount=0.9, f_decay=0.05, f_sustain=0.3)),
    # ring modulation, read as 1 -> 2 FM (its sum and difference sidebands)
    (38, 33): ("Ring Bass", "MoogSynthBass1",
               dict(osc1_wave=SQ, osc2_wave=SQ, osc2_freq=c(700), mod_dest=0, mod_amount=0.68, cutoff=0.55)),
    # a sine with a click: a triangle's few harmonics let through for an instant
    (38, 34): ("AtkSineBass", "MoogSynthBass1",
               dict(osc1_wave=TRI, osc2_level=0.0, cutoff=0.4, eg_amount=0.9, f_decay=0.04, f_sustain=0.0,
                    resonance=0.0)),
    (38, 35): ("OB sine Bass", "MoogSynthBass1",
               ob(osc1_wave=TRI, osc2_level=0.0, cutoff=0.45, a_decay=0.8, a_sustain=0.7, a_release=0.15)),
    (38, 36): ("Auxiliary Bs", "MoogSynthBass1",
               dict(osc1_wave=SAW, osc2_wave=SQ, osc2_octave=16, osc2_level=0.5, cutoff=0.5, eg_amount=0.6)),
    # the 303's square through its Distortion: plain, the peak up, darker
    (38, 40): ("303SqDistBs", "MoogSynthBass1", tb(osc1_wave=SQ, insertion_efx=TB_DIST)),
    (38, 41): ("303SqDistBs2", "MoogSynthBass1", tb(osc1_wave=SQ, resonance=0.7, insertion_efx=TB_DIST)),
    (38, 42): ("303SqDistBs3", "MoogSynthBass1", tb(osc1_wave=SQ, cutoff=0.52, eg_amount=0.75, insertion_efx=TB_DIST)),
    # reversed: swelling in to its end, as a tape played backwards
    (38, 43): ("303Sqr.Rev", "MoogSynthBass1",
               tb(osc1_wave=SQ, a_attack=0.35, a_decay=0.3, a_sustain=0.0, f_attack=0.35, f_decay=0.2,
                  f_sustain=0.0, a_release=0.04)),
    (38, 44): ("TeeBee", "MoogSynthBass1", tb(osc1_wave=SAW)),
    # an FM bell's clang under a bass's body
    (39, 14): ("Syn Bell Bs", "MoogSynthBass2",
               dict(osc1_wave=TRI, osc2_wave=TRI, osc2_freq=c(1400 * 0.5), mod_dest=0, mod_amount=0.7,
                    cutoff=0.6, eg_amount=0.6, f_decay=0.3, a_decay=0.6, a_sustain=0.4)),
    (39, 15): ("Odd Bass", "MoogSynthBass2", dict(osc1_wave=SQ, osc2_wave=SQ, osc2_freq=c(-5), cutoff=0.52)),
    (39, 30): ("Sync Bass 2", "MoogSynthBass2",
               dict(sync=True, osc2_wave=SAW, osc2_freq=0.9, mod_dest=1, mod_amount=0.7, cutoff=0.6,
                    resonance=0.2)),
    (39, 31): ("Pulse Mix Bs", "MoogSynthBass2",
               dict(osc1_wave=0.85, osc2_wave=SQ, osc2_level=0.7, osc2_freq=c(4), cutoff=0.5)),
    (39, 32): ("MG Dist Bass", "MoogSynthBass2", mg(cutoff=0.5, eg_amount=0.7, insertion_efx=TB_DIST)),
    (39, 33): ("Seq Bass 2", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_level=0.0, cutoff=0.5, resonance=0.4, eg_amount=0.78, f_decay=0.12,
                    f_sustain=0.15, a_decay=0.25, a_sustain=0.2, a_release=0.08)),
    # a third over the bass
    (39, 34): ("3rd Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_wave=SAW, osc2_freq=c(400), osc2_level=0.6, cutoff=0.55)),
    (39, 35): ("MG Oct Bass", "MoogSynthBass2", mg(osc2_octave=16, osc2_level=0.8, cutoff=0.48)),
    (39, 36): ("SlowEnvBass", "MoogSynthBass2",
               dict(osc1_wave=SAW, cutoff=0.42, resonance=0.3, eg_amount=0.7, f_attack=0.3, f_decay=0.4,
                    f_sustain=0.6)),
    (39, 37): ("Mild Bass", "MoogSynthBass2",
               dict(osc1_wave=TRI, osc2_wave=SAW, osc2_level=0.4, cutoff=0.45, resonance=0.0, eg_amount=0.55)),
    (39, 38): ("DistEnvBass", "MoogSynthBass2",
               dict(osc1_wave=SAW, cutoff=0.45, resonance=0.4, eg_amount=0.8, f_decay=0.2, f_sustain=0.2,
                    insertion_efx=TB_DIST)),
    (39, 39): ("MG LightBass", "MoogSynthBass2", mg(cutoff=0.58, eg_amount=0.6, osc2_level=0.5)),
    (39, 40): ("DistSynBass", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc2_wave=SQ, osc2_level=0.6, cutoff=0.55, insertion_efx=TB_DIST)),
    # its pitch rising onto the note (the contour on OSC 2's pitch, from under)
    (39, 41): ("Rise Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, osc1_level=0.0, osc2_wave=SAW, osc2_level=0.8, mod_dest=1, mod_amount=0.38,
                    f_decay=0.15, f_sustain=0.0, cutoff=0.55)),
    (39, 42): ("Cyber Bass", "MoogSynthBass2",
               dict(osc1_wave=SQ, osc2_wave=SAW, mod_dest=0, mod_amount=0.62, cutoff=0.5, resonance=0.5,
                    eg_amount=0.75, f_decay=0.2)),

    # --- THE SC-8850's OTHER SYNTH STRINGS, VOICES AND BRASS (2026-10-26) --
    (50, 4): ("Chorus Str.", "MoogSynthStrings1", dict(insertion_efx=JUNO_CHORUS2)),
    (50, 10): ("Syn.Strings6", "MoogSynthStrings1", dict(osc2_freq=c(-14), cutoff=0.6, a_attack=0.3)),
    (50, 11): ("Syn.Strings7", "MoogSynthStrings1", dict(osc2_octave=4, osc2_level=0.5, cutoff=0.7)),
    (50, 12): ("LoFi Strings", "MoogSynthStrings1", dict(insertion_efx=FX_LOFI)),
    # the cutoff sweeping slowly over an orchestra of saws
    (51, 3): ("FilteredOrch", "MoogSynthStrings2",
              dict(cutoff=0.5, resonance=0.25, lfo1_dest=0, lfo1_depth=0.7, lfo1_rate=0.25, a_attack=0.2)),
    (51, 4): ("JP Saw Str.", "MoogSynthStrings2",
              jp(osc2_freq=c(-14), cutoff=0.7, eg_amount=0.5, a_attack=0.3, a_decay=0.6, a_sustain=1.0,
                 a_release=0.4)),
    (51, 6): ("DistStrings", "MoogSynthStrings2", dict(insertion_efx=TB_DIST)),
    (51, 7): ("JUNOFullStr.", "MoogSynthStrings2",
              juno(cutoff=0.68, eg_amount=0.5, a_attack=0.3, a_decay=0.6, a_sustain=1.0, a_release=0.45)),
    (51, 9): ("Atk Syn Str.", "MoogSynthStrings2", dict(a_attack=0.0, eg_amount=0.7, f_decay=0.2, f_sustain=0.6)),
    (51, 10): ("StraightStr.", "MoogSynthStrings2", dict(osc2_freq=0.5, cutoff=0.66)),
    (54, 1): ("SynVox 2", "MoogSynthVoice", dict(resonance=0.45, cutoff=0.5)),
    (54, 2): ("SynVox 3", "MoogSynthVoice", dict(resonance=0.35, cutoff=0.6, lfo1_dest=1, lfo1_depth=0.56,
                                                  lfo1_rate=0.64)),
    (54, 10): ("Syn.Voice 2", "MoogSynthVoice", dict(osc2_freq=c(10), cutoff=0.55)),
    # the JX-8P's: a formant on two pulses, a slow rise
    (54, 18): ("JX8P Vox", "MoogSynthVoice",
               dict(osc1_wave=0.75, osc2_wave=0.75, osc2_freq=c(7), cutoff=0.52, resonance=0.45, a_attack=0.3)),
    (62, 18): ("OctSynBrass2", "MoogSynthBrass1", dict(osc2_octave=16, osc2_level=0.6)),
    # a band-pass brass: the ladder's band mode
    (62, 19): ("BPF Brass", "MoogSynthBrass1", dict(mode=2, cutoff=0.6, resonance=0.3)),
    (63, 3): ("Synth Brass3", "MoogSynthBrass2", dict(osc2_freq=c(10), cutoff=0.52)),
    (63, 4): ("Sync Brass", "MoogSynthBrass2",
              dict(sync=True, osc2_wave=SAW, osc2_freq=0.8, mod_dest=1, mod_amount=0.64)),
    (63, 5): ("Fat SynBrass", "MoogSynthBrass2", dict(osc2_freq=c(14), sub_level=0.4)),
    (63, 6): ("DeepSynBrass", "MoogSynthBrass2", dict(osc2_octave=16, osc2_level=0.6, cutoff=0.45)),
    (63, 11): ("DistSqrBrass", "MoogSynthBrass2", dict(osc1_wave=SQ, osc2_wave=SQ, insertion_efx=TB_DIST)),
    (63, 12): ("JP8000SawBrs", "MoogSynthBrass2", dict(osc2_level=0.0, eg_amount=0.65, f_attack=0.15),
               dict(moog_unison=SUPERSAW)),

    # --- THE SC-8850's OTHER PADS AND SYNTH EFFECTS (2026-10-26) ------------
    (88, 4): ("Fantasia 3", "MoogNewAgePad", dict(osc2_freq=c(1200 + 700), cutoff=0.62)),
    (88, 5): ("Fantasia 4", "MoogNewAgePad", dict(cutoff=0.66, resonance=0.25)),
    (88, 6): ("After D !", "MoogNewAgePad", dict(cutoff=0.6, a_attack=0.3, insertion_efx=FX_DELAY)),
    # the ARP 2600's: its harmonics brought up by the peak
    (88, 7): ("260HarmPad", "MoogNewAgePad", dict(resonance=0.55, cutoff=0.6)),
    (89, 6): ("OB Soft Pad2", "MoogWarmPad", ob(osc2_wave=SAW, osc2_freq=c(12), cutoff=0.5, a_attack=0.4,
                                                  a_release=0.5)),
    (89, 10): ("Human Pad", "MoogWarmPad", dict(resonance=0.4, cutoff=0.5, a_attack=0.5)),
    (89, 11): ("Sync Brs.Pad", "MoogWarmPad", dict(sync=True, osc2_wave=SAW, osc2_freq=0.75, mod_dest=1,
                                                    mod_amount=0.6, a_attack=0.3)),
    (89, 12): ("Oct.PWM Pad", "MoogWarmPad", dict(osc1_wave=SQ, osc2_wave=SQ, osc2_octave=4, lfo1_dest=2,
                                                   lfo1_depth=0.78, lfo1_rate=0.4)),
    (89, 13): ("JP Soft Pad", "MoogWarmPad", jp(osc2_freq=c(-12), cutoff=0.55, eg_amount=0.5, a_attack=0.4,
                                                 a_decay=0.8, a_sustain=1.0, a_release=0.5)),
    (90, 4): ("Super Poly", "MoogPolysynthPad", dict(osc2_level=0.0), dict(moog_unison=SUPERSAW)),
    (90, 12): ("Pulse Stack", "MoogPolysynthPad", dict(osc1_wave=0.85, osc2_wave=0.85, osc2_octave=4)),
    # rave: octaves stacked, the filter snapping
    (90, 13): ("TwinOct.Rave", "MoogPolysynthPad",
               dict(osc2_octave=4, osc2_level=0.7, sub_level=0.4, eg_amount=0.75, f_decay=0.2, f_sustain=0.3)),
    (90, 14): ("Oct.Rave", "MoogPolysynthPad", dict(osc2_octave=4, osc2_level=0.7, eg_amount=0.75, f_decay=0.2,
                                                     f_sustain=0.3)),
    (90, 15): ("Happy Synth", "MoogPolysynthPad", dict(osc2_freq=c(400), osc2_level=0.6, cutoff=0.68)),
    (90, 16): ("ForwardSweep", "MoogPolysynthPad", dict(eg_amount=0.8, f_attack=0.5, f_decay=0.6, f_sustain=0.6)),
    (90, 17): ("ReverseSweep", "MoogPolysynthPad", dict(eg_amount=0.2, f_attack=0.5, f_decay=0.6, f_sustain=0.6)),
    (90, 24): ("Minor Rave", "MoogPolysynthPad", dict(osc2_freq=c(300), osc2_level=0.7, eg_amount=0.75,
                                                       f_decay=0.2, f_sustain=0.3)),
    (91, 4): ("Water Space", "MoogChoirPad", dict(lfo1_dest=0, lfo1_depth=0.66, lfo1_rate=0.35, insertion_efx=FX_DELAY)),
    (91, 5): ("Cold Space", "MoogChoirPad", dict(cutoff=0.7, resonance=0.3, a_attack=0.5)),
    (91, 6): ("Noise Peaker", "MoogChoirPad", dict(noise_level=0.5, resonance=0.6, cutoff=0.55)),
    (91, 12): ("Holy Voices", "MoogChoirPad", dict(cutoff=0.58, a_attack=0.6, a_release=0.8,
                                                    insertion_efx=JUNO_CHORUS2)),
    (93, 4): ("Special Rave", "MoogMetallicPad", dict(osc2_octave=4, eg_amount=0.75, f_decay=0.2, f_sustain=0.3)),
    (93, 5): ("Metal Pad 2", "MoogMetallicPad", dict(mod_amount=0.7)),
    (94, 9): ("SynVox Pad", "MoogHaloPad", dict(resonance=0.45, cutoff=0.5, a_attack=0.4)),
    (94, 10): ("SynVox Pad 2", "MoogHaloPad", dict(resonance=0.5, cutoff=0.55, osc2_freq=c(8), a_attack=0.4)),
    (94, 11): ("Breath&Rise", "MoogHaloPad", dict(noise_level=0.35, eg_amount=0.8, f_attack=0.8, f_sustain=0.8)),
    (94, 12): ("Tears Voices", "MoogHaloPad", dict(resonance=0.45, cutoff=0.52, lfo1_dest=1, lfo1_depth=0.56,
                                                    lfo1_rate=0.6)),
    (95, 2): ("Ambient BPF", "MoogSweepPad", dict(mode=2, resonance=0.4)),
    (95, 3): ("Sync Pad", "MoogSweepPad", dict(sync=True, osc2_wave=SAW, osc2_freq=0.75, mod_dest=1, mod_amount=0.6)),
    (95, 4): ("Warriors", "MoogSweepPad", dict(osc2_freq=c(700), resonance=0.4)),
    (95, 12): ("Sweep Pipe", "MoogSweepPad", dict(osc1_wave=TRI, osc2_wave=TRI, noise_level=0.15)),
    (95, 13): ("Sweep Stack", "MoogSweepPad", dict(osc2_octave=4, osc2_level=0.6)),
    (95, 14): ("Deep Sweep", "MoogSweepPad", dict(osc2_octave=16, osc2_level=0.7, cutoff=0.45)),
    (95, 15): ("Stray Pad", "MoogSweepPad", dict(osc2_freq=c(30), lfo1_rate=0.2)),
    (96, 5): ("Saw Impulse", "MoogRainFX", dict(osc1_wave=SAW, eg_amount=0.85, f_decay=0.08, f_sustain=0.0,
                                                  a_decay=0.4, a_sustain=0.0)),
    (96, 6): ("Strange Str.", "MoogRainFX", dict(osc2_freq=c(600), mod_dest=0, mod_amount=0.6, a_attack=0.3)),
    (96, 7): ("FastFWD Pad", "MoogRainFX", dict(lfo1_dest=0, lfo1_depth=0.7, lfo1_rate=0.72)),
    (97, 5): ("HistoryWave", "MoogSoundtrackPad", dict(lfo1_dest=0, lfo1_depth=0.66, lfo1_rate=0.2, a_attack=0.6)),
    # bells: blown (noise on the attack), hyper (FM up), the Jupiter's, the
    # bottom of the range
    (98, 12): ("Blow Bell", "MoogCrystalFX", dict(noise_level=0.25, a_attack=0.05)),
    (98, 13): ("Hyper Bell", "MoogCrystalFX", dict(mod_dest=0, mod_amount=0.75)),
    (98, 21): ("JP Bell", "MoogCrystalFX", jp(osc1_wave=TRI, osc2_wave=TRI, osc2_freq=c(1400 * 0.5),
                                               mod_dest=0, mod_amount=0.66, a_decay=0.8, a_sustain=0.0,
                                               a_release=0.6)),
    (98, 23): ("Bottom Bell", "MoogCrystalFX", dict(osc1_octave=16, osc2_octave=16, cutoff=0.6)),
    (99, 10): ("Heaven Atmos", "MoogAtmosphereFX", dict(cutoff=0.65, a_attack=0.5, insertion_efx=JUNO_CHORUS2)),
    (100, 3): ("Brass Star", "MoogBrightnessFX", dict(osc1_wave=SAW, osc2_wave=SAW, eg_amount=0.7, f_attack=0.15)),
    # the D-50's: its Retour, its wind, its bell
    (100, 5): ("D-50 Retour", "MoogBrightnessFX", d50(osc2_level=0.6, osc2_freq=c(7), a_attack=0.3)),
    (100, 6): ("SouthernWind", "MoogBrightnessFX", d50(noise_level=0.35, a_attack=0.5, lfo1_dest=0, lfo1_depth=0.65,
                                                        lfo1_rate=0.25)),
    (100, 7): ("SymbolicBell", "MoogBrightnessFX", d50(osc1_wave=TRI, osc2_wave=TRI, osc2_level=0.7,
                                                        osc2_freq=c(1400 * 0.5), mod_dest=0, mod_amount=0.66)),
    (101, 17): ("LM Has Come", "MoogGoblinsFX", dict(mod_dest=1, mod_amount=0.7, lfo1_dest=0, lfo1_depth=0.7)),
    (101, 18): ("FallinInsect", "MoogGoblinsFX", dict(mod_dest=1, mod_amount=0.3, lfo1_dest=1, lfo1_depth=0.65,
                                                       lfo1_rate=0.75)),
    (101, 19): ("LFO Oct.Rave", "MoogGoblinsFX", dict(osc2_octave=4, lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.72,
                                                       lfo1_rate=0.68)),
    (101, 20): ("Just Before", "MoogGoblinsFX", dict(eg_amount=0.8, f_attack=0.7, a_attack=0.6)),
    (101, 21): ("RND Fl.Chord", "MoogGoblinsFX", dict(osc2_freq=c(700), lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.7,
                                                       lfo1_rate=0.6)),
    (101, 22): ("RandomEnding", "MoogGoblinsFX", dict(lfo1_dest=1, lfo1_shape=3, lfo1_depth=0.7, lfo1_rate=0.6)),
    (101, 23): ("Random Sine", "MoogGoblinsFX", dict(osc1_wave=TRI, osc2_wave=TRI, lfo1_dest=1, lfo1_shape=3,
                                                      lfo1_depth=0.7, lfo1_rate=0.62)),
    (101, 24): ("EatingFilter", "MoogGoblinsFX", dict(resonance=0.6, lfo1_dest=0, lfo1_shape=1, lfo1_depth=0.74,
                                                       lfo1_rate=0.6)),
    (101, 25): ("Noise&SawHit", "MoogGoblinsFX", dict(osc1_wave=SAW, noise_level=0.5, eg_amount=0.85, f_decay=0.08,
                                                       a_decay=0.4, a_sustain=0.0)),
    (101, 28): ("Dirty Stack", "MoogGoblinsFX", dict(osc2_octave=4, insertion_efx=TB_DIST)),
    (101, 29): ("Big Blue", "MoogGoblinsFX", dict(osc2_octave=16, osc2_level=0.6, cutoff=0.5, a_attack=0.5)),
    (101, 30): ("Static Hit", "MoogGoblinsFX", dict(noise_level=0.6, a_decay=0.3, a_sustain=0.0)),
    (101, 31): ("Atl.Mod.FX", "MoogGoblinsFX", dict(mod_dest=0, mod_amount=0.72, lfo1_dest=1, lfo1_depth=0.65)),
    (101, 32): ("Acid Copter", "MoogGoblinsFX", tb(osc1_wave=SAW, lfo1_dest=0, lfo1_shape=3, lfo1_depth=0.72,
                                                   lfo1_rate=0.72, a_sustain=1.0)),
    (102, 7): ("Echo SynBass", "MoogEchoesFX", dict(osc1_octave=16, osc2_octave=16, a_decay=0.4, a_sustain=0.3,
                                                     insertion_efx=FX_DELAY)),
    (102, 10): ("Panning Lead", "MoogEchoesFX", dict(a_attack=0.0, insertion_efx=FX_PAN)),
    (102, 11): ("PanningBrass", "MoogEchoesFX", dict(eg_amount=0.7, f_attack=0.15, insertion_efx=FX_PAN)),
    (103, 2): ("Star Mind", "MoogSciFiFX", dict(lfo1_dest=0, lfo1_depth=0.66, lfo1_rate=0.3, insertion_efx=FX_DELAY)),
    (103, 3): ("Star Dust", "MoogSciFiFX", dict(noise_level=0.3, cutoff=0.7)),
    (103, 4): ("Rep.Trance", "MoogSciFiFX", dict(osc2_level=0.0, a_decay=0.3, a_sustain=0.2,
                                                 insertion_efx=FX_DELAY), dict(moog_unison=SUPERSAW)),
    (103, 5): ("Etherality", "MoogSciFiFX", dict(cutoff=0.6, a_attack=0.6, insertion_efx=JUNO_CHORUS2)),
    (103, 6): ("Mystic Pad", "MoogSciFiFX", dict(resonance=0.4, lfo1_dest=0, lfo1_depth=0.65, lfo1_rate=0.25)),
    (103, 10): ("Dream Pad 2", "MoogSciFiFX", dict(cutoff=0.58, a_attack=0.5)),
    (103, 11): ("Silky Pad 2", "MoogSciFiFX", dict(cutoff=0.62, a_attack=0.5, osc2_freq=c(8))),
    (103, 19): ("Rising OSC.", "MoogSciFiFX", dict(mod_dest=1, mod_amount=0.3, f_attack=0.8, f_sustain=1.0)),
}
