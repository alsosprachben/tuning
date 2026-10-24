#!/usr/bin/env python3
"""The Roland TR-808's voices, as partials.

The Simmons SDS-V is simmons.py: one voice board, every drum a patch on it.
The 808 is not one board but a set of circuits, each instrument its own, made
of a few kinds of stage. Two kinds of voice cover all of them, and every
instrument is a PATCH -- a panel of knobs -- on one of the two:

THE CIRCUITS (~/Documents/refs, sources.md: the TR-808 Service Notes, 1981;
Werner/Abel/Smith on the bass drum, DAFx-14, and the cymbal, ICMC 2014;
Werner's thesis, 2016):

  RESONATORS  (bass drum, snare, toms, congas, rim shot, claves)
    trigger pulse (~1 ms) --> BRIDGED-T band-pass in an op-amp's feedback --+
                                                                            +--> out
    noise (white, or pink on the toms) --> filter --> VCA (own envelope) ---+

    The bridged-T rings at its tuning and decays by its Q. The drum's whole
    character is in how it starts: the pulse rings it from rest, and for the
    bass drum the network's time constant is halved while the pulse lasts --
    the first cycle runs at more than an octave above the tuning (the
    "punch", ~6 ms), and leakage through the envelope gives a slow pitch
    "sigh" down onto the tuning. On the toms and congas two diodes conduct at
    the strike, so the pitch starts a little high and falls as the ring dies.
    The snare is two bridged-Ts (TONE balances them) and SNAPPY, high-passed
    noise on its own envelope; the toms mix in pink noise ("artificial
    reverberation", the service notes); the rim shot is two networks through a
    transistor "swing" VCA that adds harmonics.

  METAL  (cymbal, open and closed hi-hat, cowbell)
    six Schmitt-trigger square oscillators --> band-pass filters --> a VCA each
    --> high-pass --> out

    Summed, the six make the dense inharmonic cluster; the band-passes keep
    only their upper harmonics. The cymbal splits them into bands decaying at
    different rates (the highest shortest); each hat takes the high band
    through its own VCA and high-pass; the cowbell is two of the six through a
    band-pass, its envelope an abrupt early drop and then a tail.

WHAT THE KERNEL DOES WITH IT (all existing machinery):

  a resonator      a partial at its frequency, decaying at its own rate
                   (mode_decays); its output stage's harmonics beside it
  the first cycle  a partial at JUMP x the tuning, dying in a few ms: the
                   halved time constant's cycle (or the pulse's, on a tom)
  the sigh         the pitch-linear sweep (tension_log), one time constant
  noise            strike_noise_layers: one layer, the filter's shape over
                   third-octave bands, falling at its envelope's rate
  the click        the strike table (strike_noise_db), falling CLICK_DBS
  the oscillators  each a PULSE (the measured unit's carry even harmonics:
                   not 50% duty), its harmonics at |sin(pi k d)| / k
  the bands        each harmonic's gain through each band's filter; its two
                   loudest bands become the partial's two-stage decay (the
                   kernel's aftersound: a share at a second rate), exact for
                   two bands and what a third adds at that frequency dropped

NOT MODELLED: the swing VCAs' intermodulation (a dense floor between the
cymbal's partials -- NOISE in a metal patch stands in for it); the bridged-T's
own nonlinearity beyond the jump; accent (velocity is level, as every voice).

THE KNOBS ARE IN PHYSICAL UNITS -- Hz, seconds, dB -- as simmons.py's are: the
808's own knobs (TONE, DECAY, SNAPPY, TUNING) are positions on an unmeasured
law, and Michael Fischer's recordings give each patch the place a position
lands it (examples/tr808_fit.py).
"""
import math

# The panel: a voice's defaults. A patch is a dict over these.
PANEL = {
    "circuit": "resonator",     # "resonator" or "metal"
    "attack_ms": None,          # the onset's ramp; None: the circuit's (1.7 ms, 0.3 metal)
    "gate_ms": None,            # the VCA closing here, whatever still rings (a 707's ROM
    "gate_release_ms": 15.0,    # take ending); None: every partial rings out. ...its close
    # ---- resonators
    "tune_hz": 56.0,            # the first bridged-T: the voice's pitch
    "tone_db": 0.0,             # ...its level (-100: a noise voice, the maracas)
    "decay_s": 0.3,             # ...to -60 dB
    "h2_db": -99.0,             # its output stage's harmonics, re it
    "h3_db": -99.0,
    "res": (),                  # more bridged-Ts: ((ratio, dB, decay_s), ...)
    "jump_ratio": 2.0,          # the strike's first cycle: its frequency re the tuning,
    "jump_db": -99.0,           # level re the tuning,
    "jump_ms": 2.0,             # and amplitude time constant,
    "jump_phase": 0.0,          # and where in its cycle it starts (radians)
    "tone_delay_ms": 0.0,       # the tuning's phase as though it began this late: the
                                # first cycle is the jump's, the ring resumes after it
    "bend_oct": 0.0,            # the sigh / the diodes: octaves above at the strike
    "bend_ms": 20.0,            # ...its time constant
    "sweep": "log",             # the bend's law: "log", falling evenly in pitch (an 808's
                                # exponential control voltage); "linear", in Hz (a 909's
                                # VCO, its current decaying into an integrator)
    "diodes": False,            # the toms' and congas' D80/D81: they conduct with the ring,
                                # so the bend's time IS the ring's (bend_ms ignored), and
                                # the harmonics they make die k times as fast as it
    "swing_db": None,           # the rim shot's SWING VCA (service notes Fig. 12): the
                                # tuning and the first of `res`, the second at this level
                                # re the first, summed and RECTIFIED -- their harmonics and
                                # intermodulation, every product decaying with its VCA
    "swing_bias": 0.0,          # where it conducts, re the sum's peak (0: half-wave)
    "swing_order": 5,           # products m f1 + n f2 kept, |m|, |n| <= this
    "tone_decay_s": None,       # with the swing: the tuning's own network's ring (decay_s
                                # is then the VCA's envelope; res's the second network's)
    "out_hp_hz": 0.0,           # the output high-pass (Sallen-Key; the rim shot's Q63)
    "out_hp_q": 0.707,
    "step_db": -99.0,           # the VCA envelope's step ringing that high-pass, re the
                                # tuning: a partial at its corner, gone in Q cycles
    # ---- metal
    "osc_hz": (),               # the oscillators that sound (a subset of the six)
    "osc_duty": 0.5,            # their duty (one for all)
    "max_hz": 18000.0,          # the highest harmonic kept
    "bands": (),                # ((centre Hz, Q, dB, decay_s), ...): a band-pass each, its VCA
    "hp_hz": 0.0,               # the output high-pass (2-pole), 0 = none
    "hp_q": 0.707,
    "after_db": -99.0,          # every partial's tail, re its start (the cowbell's two stages)
    "after_s": 1.0,             # ...to -60 dB
    # ---- noise (both)
    "noise_db": -99.0,          # a third-octave band's level at its peak, re the first partial
    "noise_tilt": 0.0,          # dB per octave (pink = -3 against white's 0)
    "noise_hp_hz": 20.0,        # high-pass
    "noise_lp_hz": 20000.0,     # low-pass
    "noise_order": 2,           # ...their poles (1: an RC each, the toms' noise)
    "noise_hp2_hz": 0.0,        # a second, resonant 2-pole high-pass (the maracas' Q68)
    "noise_hp2_q": 0.707,
    "noise_len_ms": None,       # its gate's length (the maracas); None: twice its decay
    "noise_bp": False,          # a METAL patch's noise follows its bands instead
    "noise_decay_s": 0.2,       # its envelope to -60 dB,
    "noise_rise_ms": 1.0,       # and its rise (the maracas' swells)
    "noise2_db": -99.0,         # a second noise layer, its own filter and envelope (a 909
    "noise2_tilt": 0.0,         # cymbal's bright bloom beside its early wash)
    "noise2_hp_hz": 20.0,
    "noise2_lp_hz": 20000.0,
    "noise2_decay_s": 0.2,
    "noise2_rise_ms": 1.0,
    "noise2_len_ms": None,
    # ---- the click (both)
    "click_db": -99.0,
    "click_hp_hz": 20.0,
    "click_lp_hz": 20000.0,
    "click_dbs": 400.0,         # amplitude dB/s
    "click_bursts": (),         # ((s, dB), ...): the click fired at each, a clap's
                                # bursts where its envelope generator puts them
    "click_tilt": 0.0,          # dB per octave (-6: the trigger pulse leaking through,
                                # its sinc's envelope -- the drums' skirt over ~1 kHz)
}

BANDS = tuple(25.0 * 2 ** (k / 3.0) for k in range(30))    # 25 Hz - 12.8 kHz, third octaves
BANDS = BANDS + (16000.0,)
MAX_PARTIALS = 400


def panel_of(patch):
    out = dict(PANEL)
    out.update(patch or {})
    return out


def dbs(decay_s):
    """A -60 dB time as amplitude dB/s."""
    return 60.0 / max(decay_s, 1e-4)


def lp2_db(f, fc):
    return -10.0 * math.log10(1.0 + (f / fc) ** 4)


def hp2_db(f, fc, q=0.707):
    """A 2-pole high-pass, its resonance q at fc."""
    if fc <= 0.0:
        return 0.0
    x = f / fc
    return 20.0 * math.log10(x * x / math.sqrt((1.0 - x * x) ** 2 + (x / q) ** 2) + 1e-12)


def bp_db(f, fc, q):
    """A 2-pole band-pass, 0 dB at fc."""
    x = f / fc
    return -10.0 * math.log10(1.0 + (q * (x - 1.0 / x)) ** 2)


def hp1_db(f, fc):
    return -10.0 * math.log10(1.0 + (fc / f) ** 2) if fc > 0.0 else 0.0


def lp1_db(f, fc):
    return -10.0 * math.log10(1.0 + (f / fc) ** 2)


def _noise_table(p, hp, lp, level, extra=None):
    out = []
    one = p.get("noise_order", 2) == 1
    for hz in BANDS:
        db = (level + p["noise_tilt"] * math.log2(hz / 1000.0)
              + (hp1_db(hz, hp) + lp1_db(hz, lp) if one else hp2_db(hz, hp) + lp2_db(hz, lp))
              + hp2_db(hz, p.get("noise_hp2_hz", 0.0), p.get("noise_hp2_q", 0.707)))
        if extra is not None:
            db += extra(hz)
        out.append((round(hz), round(db, 2)))
    return tuple(out)


def _band_gain(p, f, b):
    fc, q, db, _dec = b
    return 10 ** ((db + bp_db(f, fc, q) + hp2_db(f, p["hp_hz"], p["hp_q"])) / 20.0)


def metal_partials(p):
    """(Hz, gain, decay_s, after share, after decay_s) for each oscillator
    harmonic the bands let through: each harmonic's two loudest bands."""
    out = []
    for f0 in p["osc_hz"]:
        k = 1
        while k * f0 <= p["max_hz"]:
            f = k * f0
            a = abs(math.sin(math.pi * k * p["osc_duty"])) / k
            if a > 1e-6:
                gs = sorted(((a * _band_gain(p, f, b), b[3]) for b in p["bands"]), reverse=True)
                if gs:
                    g1, d1 = gs[0]
                    g2, d2 = gs[1] if len(gs) > 1 else (0.0, 1.0)
                    if p["after_db"] > -90.0:            # one envelope's two stages
                        g2, d2 = g1 * 10 ** (p["after_db"] / 20.0), p["after_s"]
                        g1 = g1 - g2 if g1 > g2 else g1
                    tot = g1 + g2
                    if tot > 0.0:
                        # the faster band is the first stage, the slower its tail
                        if d2 < d1 and p["after_db"] <= -90.0:
                            g1, d1, g2, d2 = g2, d2, g1, d1
                        out.append((f, tot, d1, g2 / tot, d2))
            k += 1
    if not out:
        return out
    top = max(g for _f, g, *_ in out)
    out = [o for o in out if o[1] > top * 10 ** (-72 / 20.0)]          # under -72 dB: nothing heard
    out.sort(key=lambda o: -o[1])
    out = out[:MAX_PARTIALS]
    out.sort(key=lambda o: o[0])
    return out


SINE = -0.5 * math.pi        # the kernel's partial is a cosine: this starts it at zero


_SWING = {}


def swing_products(r2, a2, bias, order):
    """The swing VCA: x = sin(w1 t) + a2 sin(r2 w1 t), conducting only above
    bias x its peak -- a transistor driven through a capacitor, on one
    polarity (service notes Fig. 12: "many high harmonic components"). Its
    output's components at m + n r2 (re w1), |m|, |n| <= order: ((ratio,
    amplitude re the largest), ...). Measured off the waveform itself, a
    second of it, cached."""
    import numpy as np
    key = (round(r2, 5), round(a2, 5), round(bias, 4), order)
    if key in _SWING:
        return _SWING[key]
    fs, f1 = 48000.0, 100.0                       # in units of the tuning: f1 = 1
    t = np.arange(int(0.25 * fs)) / fs
    x = np.sin(2 * np.pi * f1 * t) + a2 * np.sin(2 * np.pi * f1 * r2 * t)
    y = np.maximum(x - bias * (1.0 + a2), 0.0)
    w = np.hanning(len(t))
    y = (y - y.mean()) * w
    seen = {}
    for m in range(-order, order + 1):
        for n in range(0, order + 1):
            r = m + n * r2
            if r <= 0.05 or (n == 0 and m <= 0):
                continue
            k = round(r * 1e4)
            if k in seen:
                continue
            c = abs(np.dot(y, np.exp(-2j * np.pi * f1 * r * t))) * 2.0 / w.sum()
            seen[k] = (r, float(c))
    out = tuple(sorted(seen.values()))
    _SWING[key] = out
    return out


def swing_partials(p):
    """The swing VCA's output as decaying partials. Its two inputs ring down
    at their own rates (the second network, on the rim shot 3.6x up, far the
    faster), so the mix it rectifies changes as it decays and each product
    falls at its own rate: read off the rectifier at eight moments, scaled by
    the VCA's envelope, each product's decay the least-squares slope of its
    level over its first 40 dB. ((ratio, gain re the tuning at the strike,
    decay_s), ...)"""
    import numpy as np
    r2, db2, d2 = (float(v) for v in p["res"][0])
    d1 = p["tone_decay_s"] if p["tone_decay_s"] is not None else 10.0 * p["decay_s"]
    dv = p["decay_s"]
    span = 3.0 * min(d1, d2, dv) / 6.9078 * 6.9078 / 3.0        # to ~-60 dB of the fastest
    ts = np.linspace(0.0, max(span, 1e-3), 8)
    a20 = 10 ** (db2 / 20.0)
    lv = {}
    for t in ts:
        a1 = math.exp(-6.9078 * t / d1)
        a2 = a20 * math.exp(-6.9078 * t / d2) / a1          # the second re the first
        env = a1 * math.exp(-6.9078 * t / dv)               # homogeneous: scale out
        for r, c in swing_products(r2, round(a2, 4), p["swing_bias"], p["swing_order"]):
            lv.setdefault(round(r, 4), []).append(env * c)
    rows = []
    for r, cs in lv.items():
        cs = np.asarray(cs)
        if len(cs) != len(ts) or cs[0] <= 0.0:
            continue
        ok = cs > cs[0] * 1e-2
        if ok.sum() >= 2:
            slope = np.polyfit(ts[ok], 20 * np.log10(cs[ok]), 1)[0]      # dB/s, negative
            dec = 60.0 / max(-slope, 1.0)
        else:
            dec = ts[1]
        rows.append((r, float(cs[0]), dec))
    top = max((g for _r, g, _d in rows if _r == 1.0), default=max(g for _r, g, _d in rows))
    return [(r, g / top, d) for r, g, d in sorted(rows) if g > top * 1e-3]


def resonator_partials(p):
    """(ratio, gain, decay_s, phase) re the tuning. A network rung from rest
    starts at zero, as a SINE: a cosine's start is a step, and its click is
    broadband (a conga's first 5 ms 15-25 dB over the 808's above 1 kHz). The
    tuning and its harmonics are then delayed by TONE_DELAY, and the jump
    turned by JUMP_PHASE."""
    g0 = 10 ** (p["tone_db"] / 20.0)
    d = p["decay_s"]
    ph = lambda r: SINE - 2.0 * math.pi * r * p["tune_hz"] * p["tone_delay_ms"] / 1000.0
    if p["swing_db"] is not None and p["res"]:
        out = [(r, g0 * a, dd, ph(r)) for r, a, dd in
               swing_partials(dict(p, res=((p["res"][0][0], p["swing_db"], p["res"][0][2]),)))]
        out.sort(key=lambda o: (o[0] != 1.0, o[0]))          # the tuning first: the note's pitch
        if not out or out[0][0] != 1.0:
            out.insert(0, (1.0, 1e-6, d, ph(1.0)))
    else:
        # the diodes' harmonics: the k-th grows as the k-th power of the
        # ring, so falls k times as many dB a second
        dk = (lambda k: d / k) if p["diodes"] else (lambda k: d)
        out = [(1.0, g0, d, ph(1.0)),
               (2.0, g0 * 10 ** (p["h2_db"] / 20.0), dk(2), ph(2.0)),
               (3.0, g0 * 10 ** (p["h3_db"] / 20.0), dk(3), ph(3.0))]
        for r, db, dr in p["res"]:
            out.append((float(r), 10 ** (db / 20.0), float(dr), SINE))
    if p["jump_db"] > -90.0:
        out.append((p["jump_ratio"], 10 ** (p["jump_db"] / 20.0), 6.9078 * p["jump_ms"] / 1000.0,
                    SINE + p["jump_phase"]))
    if p["step_db"] > -90.0 and p["out_hp_hz"] > 0.0:
        # a resonant high-pass hit by a step rings at its corner, its
        # amplitude falling e-fold in Q / (pi f)
        tau = p["out_hp_q"] / (math.pi * p["out_hp_hz"])
        out.append((p["out_hp_hz"] / p["tune_hz"], 10 ** (p["step_db"] / 20.0), 6.9078 * tau, 0.0))
    if p["out_hp_hz"] > 0.0:
        out = [(r, g * 10 ** (hp2_db(r * p["tune_hz"], p["out_hp_hz"], p["out_hp_q"]) / 20.0), dd, pp)
               if i < len(out) - (1 if p["step_db"] > -90.0 else 0) else (r, g, dd, pp)
               for i, (r, g, dd, pp) in enumerate(out)]
    return out[:1] + [o for o in out[1:] if o[1] > 1e-5]     # the tuning stays: the note's pitch


def base_hz(patch):
    """The frequency a kit plays this patch at: its partials' reference."""
    p = panel_of(patch)
    if p["circuit"] == "metal":
        return float(p["osc_hz"][0]) if p["osc_hz"] else 440.0
    return float(p["tune_hz"])


def voice_attrs(patch):
    """What a tonelib class needs to play this patch."""
    p = panel_of(patch)
    attrs = {"tension_log": p["sweep"] == "log", "tension_bend_slope": 0.0, "chiff_volume": 0.0,
             # the attack: a resonator rung up over the trigger pulse, the
             # metal at once (tonelib.TR808Properties)
             "chiff_max_valve_time": (p["attack_ms"] / 1000.0 if p["attack_ms"] is not None
                                      else 0.0003 if p["circuit"] == "metal" else 0.0017),
             "harmonic_decay_db": 0.0, "strike_noise_slope": 0.0, "strike_noise_fade_s": 0.001}
    if p["circuit"] == "metal":
        parts = metal_partials(p)
        f0 = p["osc_hz"][0] if p["osc_hz"] else 440.0
        g0 = max((g for _f, g, *_ in parts), default=1.0)
        attrs.update(
            mode_ratios=tuple(f / f0 for f, *_ in parts),
            mode_gains=tuple(g / g0 for _f, g, *_ in parts),
            mode_decays=tuple(dbs(d) / 2.0 for _f, _g, d, _a, _ad in parts),
            mode_after=tuple((a, dbs(ad) / 2.0) for _f, _g, _d, a, ad in parts),
            mode_phases=tuple(0.0 for _ in parts),
            tension_bend=0.0, tension_bend_max=0.0, tension_bend_power=0.0,
            tension_settle_time=0.01, tension_settle_cutoff=1.0)
        extra = None
        if p["noise_bp"] and p["bands"]:
            extra = lambda hz: 20.0 * math.log10(max(_band_gain(p, hz, b) for b in p["bands"]) + 1e-9)
    else:
        parts = resonator_partials(p)
        b = 2 ** p["bend_oct"] - 1.0
        # the diodes conduct with the ring: the bend settles as it decays
        bend_s = p["decay_s"] / 6.9078 if p["diodes"] else p["bend_ms"] / 1000.0
        attrs.update(
            mode_ratios=tuple(r for r, _g, _d, _p in parts),
            mode_gains=tuple(g for _r, g, _d, _p in parts),
            mode_decays=tuple(dbs(d) / 2.0 for _r, _g, d, _p in parts),
            mode_after=tuple((0.0, 0.0) for _ in parts),
            mode_phases=tuple(ph for _r, _g, _d, ph in parts),
            tension_bend=b, tension_bend_max=abs(b), tension_bend_power=0.0,
            tension_settle_time=bend_s,
            tension_settle_cutoff=max(1.0, 2.0 * p["decay_s"]))
        extra = None
    if p["gate_ms"] is not None:
        attrs["gate_time"] = p["gate_ms"] / 1000.0
        attrs["release_valve_time"] = p["gate_release_ms"] / 1000.0
    attrs["max_harmonic"] = len(attrs["mode_ratios"])
    attrs["decay_db"] = attrs["mode_decays"][0] if attrs["mode_decays"] else 30.0
    layers = ()
    if p["noise_db"] > -90.0:
        layers = ((_noise_table(p, p["noise_hp_hz"], p["noise_lp_hz"], p["noise_db"], extra),
                   p["noise_rise_ms"] / 1000.0, round(dbs(p["noise_decay_s"]), 2),
                   (p["noise_len_ms"] / 1000.0 if p["noise_len_ms"] is not None
                    else 2.0 * p["noise_decay_s"])),)
    if p["noise2_db"] > -90.0:
        q = dict(p, noise_tilt=p["noise2_tilt"], noise_order=2, noise_hp2_hz=0.0)
        layers += ((_noise_table(q, p["noise2_hp_hz"], p["noise2_lp_hz"], p["noise2_db"], extra),
                    p["noise2_rise_ms"] / 1000.0, round(dbs(p["noise2_decay_s"]), 2),
                    (p["noise2_len_ms"] / 1000.0 if p["noise2_len_ms"] is not None
                     else 2.0 * p["noise2_decay_s"])),)
    attrs["strike_noise_layers"] = layers
    if p["click_db"] > -90.0:
        attrs["strike_noise_db"] = _noise_table(dict(p, noise_tilt=p["click_tilt"], noise_order=2,
                                                     noise_hp2_hz=0.0),
                                                p["click_hp_hz"], p["click_lp_hz"], p["click_db"])
    else:
        attrs["strike_noise_db"] = tuple((round(hz), -120.0) for hz in BANDS)
    attrs["strike_noise_dbs"] = p["click_dbs"]
    if p["click_bursts"]:
        attrs["strike_flam_times"] = tuple((float(t), float(db)) for t, db in p["click_bursts"])
    attrs["strike_noise_len_s"] = 0.25
    return attrs


# ---- DRIVE: a voice pushed into a desk or a distortion (the Techno set)
#
# A 1990s techno kick is a machine's kick driven until it clips: the mixing
# desk's channel, or a distortion box, run hot. A one-shot is a FIXED sound,
# so the driving is done once, here, through OUR valve (tubeamp.curve: the
# push-pull pair the organ and the guitars play through, drive in units of its
# grid bias -- 1 its edge of breakup, 2 a clip, 4 hard -- and a single-ended
# stage's even orders from its imbalance) -- and written as the voice's own
# partials. Its harmonics come strong while the drum is loud and die faster
# than it as it falls under the knee, and its own peak is held up while it
# clips: compression. Written as the circuit's partials, they ride the voice's
# sweep as real distortion does. The rest -- the second network, the noise --
# is held up by the same compression and not otherwise shaped: a guess, for
# the ear.

DRIVE_HARMONICS = (2, 3, 4, 5, 6, 7, 9, 11)
DRIVE_IMBALANCE = 0.3       # a desk channel's or a distortion box's single-ended stage


def _valve_harmonics(drive, a, ks, imbalance, n=1024):
    """|b_k| of the valve driven by a sine of amplitude a * drive (grid-bias
    units), for k in ks, re the stage's clean gain."""
    import numpy as np
    import tubeamp as _TA
    th = 2.0 * np.pi * (np.arange(n) + 0.5) / n
    y = _TA.curve(drive * a * np.sin(th), imbalance=imbalance) / (_TA.small_signal(imbalance=imbalance) * drive)
    # complex: an unbalanced stage's even orders land on the cosines
    return [abs(2.0 / n * complex(np.dot(y, np.exp(-1j * k * th)))) for k in ks]


def _fit_decay(ts, dbs_):
    """-60 dB time of a least-squares line through (t, dB)."""
    n = len(ts)
    mt, md = sum(ts) / n, sum(dbs_) / n
    s = sum((t - mt) * (d - md) for t, d in zip(ts, dbs_)) / max(sum((t - mt) ** 2 for t in ts), 1e-12)
    return 60.0 / max(-s, 1e-3)


def drive(patch, drive_, imbalance=DRIVE_IMBALANCE, steps=48):
    """The knobs that put `patch` (a resonator voice) through the valve at
    drive_: its decay held up by the compression, its harmonics -- even and
    odd -- as partials, each with its own fall, its other networks and noise
    held up as its tone is."""
    p = panel_of(patch)
    d = p["decay_s"]
    ks = (1,) + DRIVE_HARMONICS
    ts = [d * i / steps for i in range(steps + 1)]
    lv = [_valve_harmonics(drive_, 10 ** (-3.0 * t / d), ks, imbalance) for t in ts]
    ref = lv[0][0]
    db = [[20.0 * math.log10(max(v[j] / ref, 1e-9)) for v in lv] for j in range(len(ks))]
    # each partial over its first 40 dB down: the knee's hold, then its fall
    dec = []
    for j in range(len(ks)):
        use = [(t, x) for t, x in zip(ts, db[j]) if x > db[j][0] - 40.0]
        dec.append(_fit_decay([t for t, _ in use], [x for _, x in use]) if len(use) > 2 else d / ks[j])
    hold = dec[0] / d
    out = {"decay_s": round(dec[0], 4)}
    res = [(r, x, round(dd * hold, 4)) for r, x, dd in p["res"]]
    # beside the circuit's own h2 and h3 (its output stage's, which the drive
    # does not take away), held up as its tone is
    for j, k in enumerate(DRIVE_HARMONICS, start=1):
        if db[j][0] > -60.0:
            res.append((float(k), round(db[j][0], 2), round(dec[j], 4)))
    out["res"] = tuple(res)
    if p["noise_db"] > -90.0:
        out["noise_decay_s"] = round(p["noise_decay_s"] * hold, 4)
    return out
