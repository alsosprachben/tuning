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


def c(cents):
    """OSC 2 FREQ for an offset in cents."""
    return 0.5 + cents / 1400.0


SC88_SYNTH = {
    # --- basses ---------------------------------------------------------
    (35, 4): ("SynFretless", "MoogSynthBass1",
              dict(osc1_wave=0.45, osc2_level=0.0, sub_level=0.4, cutoff=0.50, resonance=0.2,
                   eg_amount=0.6, a_attack=0.09, glide=0.25)),
    (38, 1): ("Syn.Bass101", "MoogSynthBass1",
              dict(osc1_wave=SAW, osc2_level=0.0, sub_level=0.6, sub_wave=0.3, cutoff=0.52,
                   resonance=0.15, f_decay=0.22, f_sustain=0.3)),
    (38, 9): ("TB303 Bass", "MoogSynthBass1",
              dict(osc1_wave=SAW, osc2_level=0.0, sub_level=0.0, cutoff=0.45, resonance=0.7,
                   eg_amount=0.85, f_decay=0.2, f_sustain=0.0, res_bass=False, glide=0.1)),
    (38, 10): ("Tekno Bass", "MoogSynthBass1",
               dict(osc1_wave=SQ, osc2_level=0.0, cutoff=0.5, resonance=0.55, eg_amount=0.8,
                    f_decay=0.12, f_sustain=0.1)),
    (38, 16): ("Reso SHBass", "MoogSynthBass1",
               dict(osc1_wave=SAW, osc2_level=0.0, sub_level=0.4, cutoff=0.5, resonance=0.6,
                    eg_amount=0.75, f_decay=0.3, f_sustain=0.2)),
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
               dict(osc1_wave=0.75, sub_level=0.5, cutoff=0.5, resonance=0.25, f_decay=0.25, f_sustain=0.3)),
    (39, 18): ("SH101Bass 2", "MoogSynthBass2",
               dict(osc1_wave=SAW, sub_level=0.5, cutoff=0.47, resonance=0.5, f_decay=0.18, f_sustain=0.15)),
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
               dict(osc2_level=0.0, sub_level=0.4, cutoff=0.62, resonance=0.3, eg_amount=0.75,
                    f_decay=0.25, f_sustain=0.35)),
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
    (39, 21): ("Spike Bass", "MoogSynthBass2",
               dict(osc1_wave=SAW, sub_level=0.4, cutoff=0.45, resonance=0.55, eg_amount=0.85,
                    f_decay=0.1, f_sustain=0.1)),
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
