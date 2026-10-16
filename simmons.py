#!/usr/bin/env python3
"""A Simmons SDS-V voice, as partials.

The Moog Messenger is moog.py; this is the drum synthesiser the SC-55's
Electronic set (and GM's "Synth Drum") stands for. Built the same way: the
circuit's stages, each made something done to partials, and every drum that
plays it a PATCH -- a panel of knobs -- on the one engine.

THE CIRCUIT (~/Documents/refs: the SDSV-DIY manual's corrected voice board,
Aly James's VSDSX manual, sources.md):

    VCO -- a TRIANGLE ----- passive low-pass ("something similar to sine") --+
                                                                           mix -> BODY VCA --+
    noise -- SSM2044 4-pole low-pass ("NOISE": its cutoff) --+------------+                   +-> out
                                                              +-- CLICK VCA (short) ----------+

  TONE      the VCO's pitch, where the bend ENDS
  BEND      one envelope added to the VCO's exponential CV: the pitch starts
            BEND octaves up and falls evenly in pitch to TONE. Its time is the
            DECAY knob's -- the same envelope -- and a portion of it moves the
            noise filter's cutoff too (not on the snare). On the toms a second
            output follows how hard the pad is struck.
  DECAY     the BODY VCA: tone and noise together, one envelope
  NOISE     the filter's cutoff; NOISE TONE, the body's noise against the tone
  CLICK     the filtered noise through its own short VCA, beside the body

WHAT THE KERNEL DOES WITH IT (all existing machinery, so live has it through
its templates):

  the triangle   its odd harmonics at 1/k^2, times the passive low-pass at
                 each one's frequency (tone_partials)
  the bend       tonelib's pitch-linear sweep (tension_log), b = 2^BEND - 1,
                 its time constant BEND_RATIO x the body's
  the body VCA   every tone partial and every noise band decays at the body's
                 rate (amplitude dB/s = 60 / DECAY)
  the moving     each third-octave noise band its own extra decay: the 4-pole
  noise filter   filter's gain at that band falling as the cutoff falls,
                 fitted over the body's first 30 dB (noise_layers). The one
                 approximation: a cutoff sweeping past a band is not an
                 exponential in it
  the click      the strike: the same filtered spectrum at the cutoff's peak,
                 falling CLICK_DBS

NOT MODELLED: ATK, the few-ms pitch kick on the attack (the kernel's sweep has
one time constant; the click carries the attack instead); the triangle's
circuit harmonics and its clipping when driven; the filter's resonance (the
SDS-V's bass and toms ran with none).

THE KNOBS ARE IN PHYSICAL UNITS -- Hz, octaves, seconds, dB -- not pot
positions: there is no SDS-V here to measure a knob law on, so a position
would claim a calibration no one has made.
"""
import math

import numpy as np

# The panel, a voice's defaults. A patch is a dict over these.
PANEL = {
    "tone_hz": 110.0,        # TONE: where the bend ends
    "tone_lp_hz": 400.0,     # the triangle's passive low-pass (fixed in the circuit)
    "bend_oct": 1.0,         # BEND: octaves above TONE at the strike (negative: up)
    "bend_ratio": 0.5,       # the bend's time constant over the body's
    "bend_velocity": False,  # the toms' second output: the bend follows the strike
    "decay_s": 0.6,          # DECAY: the body to -60 dB
    "noise_hz": 2000.0,      # NOISE: the filter's cutoff at rest
    "noise_bend_oct": 1.0,   # how far the bend envelope opens it at the strike
    "noise_db": -20.0,       # NOISE TONE: a noise band's level against the tone's fundamental
    "click_db": -20.0,       # CLICK: the click's bands against the tone's fundamental
    "click_dbs": 300.0,      # how fast the click falls (amplitude dB/s)
}

HARMONICS = (1, 3, 5, 7, 9, 11)                      # a triangle: odd, 1/k^2
BANDS = tuple(100.0 * 2 ** (k / 3.0) for k in range(21))   # 100 Hz - 10 kHz, third octaves


def panel_of(patch):
    out = dict(PANEL)
    out.update(patch or {})
    return out


def lp1_db(f, fc):
    """The passive one-pole low-pass, dB."""
    return -10.0 * math.log10(1.0 + (f / fc) ** 2)


def lp4_db(f, fc):
    """The SSM2044 at no resonance as a 4-pole low-pass (Butterworth-flat), dB."""
    return -10.0 * math.log10(1.0 + (f / fc) ** 8)


def body_dbs(p):
    """The body VCA's fall, amplitude dB/s."""
    return 60.0 / max(p["decay_s"], 1e-3)


def body_tau(p):
    """...as an amplitude time constant, s."""
    return p["decay_s"] / math.log(1000.0)


def bend_tau(p):
    return p["bend_ratio"] * body_tau(p)


def tone_partials(p):
    """(ratio, gain re the fundamental) of the filtered triangle at TONE."""
    f0 = p["tone_hz"]
    ref = lp1_db(f0, p["tone_lp_hz"])
    return tuple((float(k), 10 ** ((lp1_db(k * f0, p["tone_lp_hz"]) - ref) / 20.0) / k ** 2)
                 for k in HARMONICS)


def cutoff_at(p, t):
    """The noise filter's cutoff t seconds after the strike: the bend
    envelope's portion added to its CV, so it falls evenly in pitch."""
    return p["noise_hz"] * 2 ** (p["noise_bend_oct"] * math.exp(-t / bend_tau(p)))


def noise_layers(p):
    """The body's noise as strike_noise_layers: one third-octave band a layer,
    ((Hz, dB re the note's gain),), rise s, fall dB/s, length s. Each band
    starts at the filter's gain at the cutoff's peak and falls at the body's
    rate plus how fast that gain falls as the cutoff comes down, fitted over
    the body's first 30 dB."""
    if p["noise_db"] <= -90.0:
        return ()
    T = p["decay_s"] / 2.0
    ts = np.linspace(0.0, T, 24)
    out = []
    for hz in BANDS:
        g = np.array([lp4_db(hz, cutoff_at(p, t)) for t in ts])
        slope = -float(np.polyfit(ts, g, 1)[0])        # dB/s the filter takes off
        out.append((((round(hz), round(p["noise_db"] + float(g[0]), 2)),), 0.001,
                    round(body_dbs(p) + max(0.0, slope), 2), 2.0 * p["decay_s"]))
    return tuple(out)


def click_table(p):
    """The click: the filtered noise at the cutoff's peak, as strike_noise_db."""
    fc = cutoff_at(p, 0.0)
    return tuple((round(hz), round(p["click_db"] + lp4_db(hz, fc), 2)) for hz in BANDS)


def voice_attrs(patch):
    """What a tonelib class needs to play this patch."""
    p = panel_of(patch)
    parts = tone_partials(p)
    D = body_dbs(p) / 2.0                 # tonelib's D: a POWER ratio's dB/s
    return {
        "mode_ratios": tuple(r for r, _ in parts),
        "mode_gains": tuple(g for _, g in parts),
        "max_harmonic": len(parts),
        "mode_decays": tuple(D for _ in parts),     # one VCA: every partial alike
        "decay_db": D,
        "harmonic_decay_db": 0.0,
        "tension_log": True,
        "tension_bend": max(0.0, 2 ** p["bend_oct"] - 1.0) if p["bend_oct"] >= 0 else 2 ** p["bend_oct"] - 1.0,
        "tension_bend_max": abs(2 ** p["bend_oct"] - 1.0),
        "tension_bend_slope": 0.0,
        "tension_bend_power": 1.0 if p["bend_velocity"] else 0.0,
        "tension_settle_time": bend_tau(p),
        "tension_settle_cutoff": max(1.0, 2.0 * p["decay_s"]),
        "strike_noise_db": click_table(p),
        "strike_noise_dbs": p["click_dbs"],
        "strike_noise_len_s": 0.25,
        "strike_noise_fade_s": 0.001,
        "strike_noise_slope": 0.0,
        "strike_noise_layers": noise_layers(p),
        "chiff_volume": 0.0,
    }
