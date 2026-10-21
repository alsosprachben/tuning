"""THE SC-88Pro's INSERTION EFFECT (EFX): one effect, of 64 types, that the
parts assigned to it pass through (40 4x 22), its type and twenty parameters
set by SysEx (40 03 00-16) and its own sends to the system reverb, chorus and
delay (40 03 17-19). A Sound Canvas file uses it to make a clean guitar a
driven one, or to put a rotary speaker on an organ.

AS OUR MODELS, NOT AS ROLAND'S DSP. Each stage of a type is mapped onto the
physical model this renderer already has for it, and Roland's numbers -- the
manuals' parameter lists and the Effect Data Table's encodings -- set it:

  OD / DS + amp   a GAIN STAGE in front of the part's valve (tubeamp on the
                  part's sum, every product, intermodulation between notes
                  included): its gain both drives the valve harder and comes
                  out as loudness, saturating at the valve's ceiling; then its
                  output stage (OD_MAKEUP_DB) and its speaker, cabinet.py
  compressor      the decay of what is played, slowed: compression above the
                  threshold divides an exponential decay's rate by the ratio,
                  which in the partial domain is exact -- each partial's logr
  EQ              each partial's gain at its own frequency, exactly
  chorus/flanger  chorus.gs_copies: a swept line read at two outputs, fed back
  level, sends    per note at its onset: the file automates them

This module is the parameters: the timeline (state_at), the encodings, and
chain(), which turns a type and its values into the stages above. Types not
yet built return None, and their parts play dry -- the coverage table says
which. Built: GTR Multi 1-3, Overdrive, Distortion.

WHAT IS CHOSEN rather than given: the gain laws (0-127 onto the stage's gain
in dB, distortion with more than overdrive) and its output makeup, the compressor's sustain
law, the EQ's shelf corners (400 Hz / 4 kHz), and the flanger's base delay.
Each says so where it is set.
"""
import math

# THE TYPES (SC-88Pro owner's manual, chapter 4): (MSB, LSB) -> name
TYPES = {
    (0x00, 0x00): "Thru", (0x01, 0x00): "Stereo-EQ", (0x01, 0x01): "Spectrum",
    (0x01, 0x02): "Enhancer", (0x01, 0x03): "Humanizer", (0x01, 0x10): "Overdrive",
    (0x01, 0x11): "Distortion", (0x01, 0x20): "Phaser", (0x01, 0x21): "Auto Wah",
    (0x01, 0x22): "Rotary", (0x01, 0x23): "Stereo Flanger", (0x01, 0x24): "Step Flanger",
    (0x01, 0x25): "Tremolo", (0x01, 0x26): "Auto Pan", (0x01, 0x30): "Compressor",
    (0x01, 0x31): "Limiter", (0x01, 0x40): "Hexa Chorus", (0x01, 0x41): "Tremolo Chorus",
    (0x01, 0x42): "Stereo Chorus", (0x01, 0x43): "Space D", (0x01, 0x44): "3D Chorus",
    (0x01, 0x50): "Stereo Delay", (0x01, 0x51): "Mod Delay", (0x01, 0x52): "3 Tap Delay",
    (0x01, 0x53): "4 Tap Delay", (0x01, 0x54): "Tm Ctrl Delay", (0x01, 0x55): "Reverb",
    (0x01, 0x56): "Gate Reverb", (0x01, 0x57): "3D Delay", (0x01, 0x60): "2 Pitch Shifter",
    (0x01, 0x61): "Fb P.Shifter", (0x01, 0x70): "3D Auto", (0x01, 0x71): "3D Manual",
    (0x01, 0x72): "Lo-Fi 1", (0x01, 0x73): "Lo-Fi 2",
    (0x03, 0x00): "Rotary Multi", (0x04, 0x00): "GTR Multi 1", (0x04, 0x01): "GTR Multi 2",
    (0x04, 0x02): "GTR Multi 3", (0x04, 0x03): "Clean Gt Multi 1",
    (0x04, 0x04): "Clean Gt Multi 2", (0x04, 0x05): "Bass Multi", (0x04, 0x06): "Rhodes Multi",
    (0x05, 0x00): "Keyboard Multi",
}
# ...ALL 64 (gs_efx_params, generated from Roland's own table by
# examples/gs_efx_table.py): the 20 above did not name -- the series pairs
# (02H xx) and the parallel ones (11H xx) -- under the table's names; and
# Rotary Multi also at 02H 0CH, the SC-88Pro table's misprint, should a file
# have followed it
import gs_efx_params as _P
for _k, (_n, _nm) in _P.TYPES.items():
    TYPES.setdefault(_k, _nm)
TYPES[(0x02, 0x0C)] = "Rotary Multi"
BUILT = {"GTR Multi 1", "GTR Multi 2", "GTR Multi 3", "Overdrive", "Distortion"}

# ---------------------------------------------------------------- encodings
# (SC-88Pro owner's manual, "Effect data table", p.183)


def rate1(v):
    """Rate1, Hz: 0.05 a step to 5.00, then 0.1 to 7.0, then 0.5 to 10."""
    v = max(0, min(127, int(v)))
    if v <= 0x63:
        return 0.05 * (v + 1)
    if v <= 0x77:
        return 5.0 + 0.1 * (v - 0x63)
    return min(10.0, 7.0 + 0.5 * (v - 0x77))


def rate2(v):
    """Rate2, Hz: 0.05 a step, 0.05 to 6.40 -- the guitar multis' CF Rate
    (the data table's *7). Rate1 (rate1) goes on to 10 Hz past 63H; read
    with it, a chain's chorus at 7FH turned at 10 Hz, not 6.40."""
    return 0.05 * (max(0, min(127, int(v))) + 1)


# EACH TYPE'S OWN DEFAULTS (SC-88Pro owner's manual, the Chapter 8 data table;
# the SC-8850's prints the same): what a type change sets, before the file
# sends a parameter of its own -- the value between a row's range ("0 - 80 -
# 127"). A row that prints only its range has its default at one end and
# does not say which, and a switch prints none: those keep chain()'s own.
# By parameter number (1-20 = address 03H-16H).
DEFAULTS = {TYPES[_k]: {n: x[3] for n, x in _P.PARAMS[_nm].items() if x[3] is not None}
            for _k, (_n, _nm) in _P.TYPES.items()}


EQ_FREQS = (200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000,
            5000, 6300)


def eq_freq(v):
    """EQ Freq, Hz: third-octave steps every 8 values, 200 Hz - 6.3 kHz."""
    return float(EQ_FREQS[max(0, min(127, int(v))) // 8])


def gain_db(v):
    """A -12..+12 dB gain, about 40H."""
    return float(max(-12, min(12, int(v) - 64)))


def feedback(v):
    """-98..+98 %, 2 % a step about 40H, as a fraction."""
    return max(-0.98, min(0.98, (int(v) - 64) * 2.0 / 100.0))


EQ_Q = (0.5, 1.0, 2.0, 4.0, 9.0)

# ------------------------------------------------------------------ timeline
# the EFX's own addresses: 40 03 aa
SEND_REV, SEND_CHO, SEND_DLY = 0x17, 0x18, 0x19


def parse(data):
    """('type', (msb, lsb)) / ('param', n 1-20, v) / ('send', addr, v) for an
    EFX message (40 03 aa), ('part', channel, on) for a part's EFX assign
    (4b 4p 22, b 0 port A / 5 port B), or None."""
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12):
        return None
    if d[4:6] == (0x40, 0x03):
        a = d[6]
        if a == 0x00 and len(d) >= 9:
            return ('type', (int(d[7]), int(d[8])))
        if 0x03 <= a <= 0x16:
            return ('param', a - 0x02, int(d[7]))
        if a in (SEND_REV, SEND_CHO, SEND_DLY):
            return ('send', a, int(d[7]))
        return None
    if d[4] in (0x40, 0x50) and d[5] >> 4 == 4 and d[6] == 0x22:
        blk = d[5] & 0x0F
        ch = (9 if blk == 0 else (blk - 1 if blk <= 9 else blk)) + (16 if d[4] == 0x50 else 0)
        return ('part', ch, bool(d[7]))
    return None


def state_at(events, t):
    """The EFX at time t from parse()'s events [(t, ('type'|'param'|'send'|
    'reset', ...))]: {'type': (msb, lsb), 'p': {n: v}, 'send': {addr: v}}. A
    type change puts the parameters back to the type's (unknown here: the
    model's own), as the module does; a reset puts all back."""
    st = dict(type=(0, 0), p={}, send={SEND_REV: 40, SEND_CHO: 0, SEND_DLY: 0})
    for et, ev in events:
        if et > t + 1e-9:
            break
        if ev[0] == 'reset':
            st = dict(type=(0, 0), p={}, send={SEND_REV: 40, SEND_CHO: 0, SEND_DLY: 0})
        elif ev[0] == 'type':
            st['type'] = ev[1]
            st['p'] = {}
        elif ev[0] == 'param':
            st['p'][ev[1]] = ev[2]
        elif ev[0] == 'send':
            st['send'][ev[1]] = ev[2]
    return st


def assigned(events, ch, t):
    """Is part `ch` on the EFX at t? (its last assign, and none after a reset)"""
    on = False
    for et, ev in events:
        if et > t + 1e-9:
            break
        if ev[0] == 'reset':
            on = False
        elif ev[0] == 'part' and ev[1] == ch:
            on = ev[2]
    return on


# ------------------------------------------------------------------- chains
AMP_TYPES = ("Small", "BltIn", "2-Stk", "3-Stk")
LOW_SHELF_HZ, HIGH_SHELF_HZ = 400.0, 4000.0     # chosen: the guitar EQs' corners are not given


# THE OD STAGE IS A PEDAL: gain into a ceiling. Two stages in series MULTIPLY
# -- a pedal's gain scales what reaches the amp -- and an overdrive's gain
# comes out as LOUDNESS until the stage saturates. The first law ADDED a
# drive (0.3-2.0) to the voice's own valve drive: Tokei's OD at 30 took GM
# 29's 4.45 to 5.15, +1.3 dB, so the stage did almost nothing, and our valve
# being unity-gain for small signals, its Level (Konami's 40-50, made to tame
# a clipped full-scale sample) cut a signal that had never been boosted: the
# guitars sat quiet against the SC-88Pro (Ben, by ear on Tokei).
# CHOSEN, Roland gives neither: the gain in dB, overdrive 0-20, distortion
# 6-30 (a Tube Screamer spans about +6 to +40); the output makeup is what a
# clipped stage gains over its input, a peak-normalised sample's crest factor
# brought down by the clip -- 6 dB first, then 3 by Ben's ear on Tokei's
# guitars (6 put the section 9.7 dB over the old law; "lower the gain"). The
# drive the gain makes there (GM 29's 4.45 x 1.72 at Konami's 30) he heard as
# right: Crazy Train's crunch, a little less smashed.
OD_DB = (0.0, 20.0)
DS_DB = (6.0, 30.0)
OD_MAKEUP_DB = 3.0
PEDAL_AMP_DRIVE = 1.0     # the amp an OD stage drives where the voice has none: at its edge


def od_gain(v, dist):
    """The OD/DS stage's gain (linear) for Roland's 0-127."""
    x = max(0, min(127, int(v))) / 127.0
    lo, hi = DS_DB if dist else OD_DB
    return 10.0 ** ((lo + (hi - lo) * x) / 20.0)


# THE COMPRESSOR'S ATTACK (Cmp Atck, the guitar multis' p1, 70 by default):
# "the time over which the sound will rise after it is input" (SC-88Pro
# manual) -- each note's onset, risen over it. Roland gives no times: 0-127
# onto 0-CMP_ATTACK_MS is chosen. The one documented thing in Tokei's chain
# that would hide a MIDI guitar's tracking glitches (2-23 ms notes): a note
# that ends before it has risen. 0 leaves every onset as it was.
CMP_ATTACK_MS = 40.0


def param_numbers(name):
    """{parameter name: its number 1-20} for a type, from Roland's table."""
    for _k, (_n, nm) in _P.TYPES.items():
        if TYPES.get(_k) == name:
            return {x[0]: n for n, x in _P.PARAMS[nm].items()}
    return {}


_PN = {}


def chain(st):
    """The stages a state's type makes, or None where the type is not built:
    {'name', 'drive' (or None), 'cabinet' (or None), 'comp': decay factor,
    gain and attack seconds (or None), 'eq': (low dB, mid Hz, Q, mid dB, high dB) (or None), 'cf':
    chorus device and mix (or None), 'level', 'sends'} -- 'od_gain' the OD
    stage's gain in front of the valve (or None), 'level' its output level
    with the OD's makeup in it.

    EACH STAGE BY ITS PARAMETERS' NAMES (Roland's table, gs_efx_params): a
    type with an "OD Drive" has an overdrive, one with "CF Rate" a chorus or
    flanger, one with "Dly Time" a delay -- whatever number the type gives
    them -- so the multis and the series and parallel pairs are built from
    the same stages. A parameter the file has not sent is the type's default
    (DEFAULTS), else the stage's own."""
    name = TYPES.get(tuple(st['type']))
    if name not in BUILT:
        return None
    p = st['p']
    dflt = DEFAULTS.get(name, {})
    pn = _PN.get(name)
    if pn is None:
        pn = _PN[name] = param_numbers(name)

    def g(key, d):                     # the file's, the type's, ours
        n = pn.get(key)
        return d if n is None else p.get(n, dflt.get(n, d))
    out = dict(name=name, od_gain=None, cabinet=None, comp=None, eq=None, cf=None, dly=None,
               level=g("Level", 127) / 127.0, sends=dict(st['send']))
    mk = 10.0 ** (OD_MAKEUP_DB / 20.0)
    if name in ("Overdrive", "Distortion"):
        out['od_gain'] = od_gain(g("Drive", 48), name == "Distortion")
        out['level'] *= mk
        if g("Amp Sw", 1):
            out['cabinet'] = 'guitar12'
        out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        return out
    if "Cmp Sw" in pn and g("Cmp Sw", 1):
        sus = g("Cmp Sus", 64) / 127.0
        # chosen: sustain 0-127 slows the decay up to fourfold, the level its
        # makeup (64 none)
        out['comp'] = (1.0 / (1.0 + 3.0 * sus), g("Cmp Level", 64) / 64.0,
                       CMP_ATTACK_MS * g("Cmp Atck", 70) / 127000.0)
    if "OD Drive" in pn and g("OD Sw", 1):
        out['od_gain'] = od_gain(g("OD Drive", 48), bool(g("OD Sel", 0)))
        out['level'] *= mk
        if g("OD Amp Sw", 1):
            out['cabinet'] = 'guitar12'
    if "EQ L Gain" in pn:
        out['eq'] = (gain_db(g("EQ L Gain", 64)), eq_freq(g("EQ M Fq", 64)), EQ_Q[min(4, g("EQ M Q", 1))],
                     gain_db(g("EQ M Gain", 64)), gain_db(g("EQ H Gain", 64)))
    elif "OD L Gain" in pn:           # the OD's own low and high gains
        out['eq'] = (gain_db(g("OD L Gain", 64)), None, None, 0.0, gain_db(g("OD H Gain", 64)))
    if "CF Rate" in pn:
        out['cf'] = (cf_device(bool(g("CF Sel", 0)), g("CF Rate", 8), g("CF Depth", 40), g("CF Fb", 64)),
                     g("CF Mix", 0) / 127.0)
    if "Dly Time" in pn:
        # the chain's own delay, as the GS delay's repeats (gsdelay): one tap,
        # 0-635 ms (5 ms a step), its feedback 0-127, its mix
        t, f, x = g("Dly Time", 60), g("Dly Fb", 32), g("Dly Mix", 0)
        if x:
            out['dly'] = dict(tc=t * 0.005, taps=[(t * 0.005, 1.0, 'c')], level=x / 127.0,
                              fb=f / 128.0, lpf=None, to_reverb=0.0)
    return out


def mix_share(events, ch, sr):
    """share(non samples) -> the chain's chorus/flanger wet share at each row's
    onset, for part `ch`: its CF Mix then (0-127) as the system chorus's send
    is taken (a^2 / (1 + a^2)), 0 where the part is off the EFX."""
    import numpy as np
    ts = sorted({0.0} | {t for t, _ in events})
    vals = []
    for t in ts:
        c = chain(state_at(events, t)) if assigned(events, ch, t) else None
        a = c['cf'][1] if (c is not None and c['cf'] is not None) else 0.0
        vals.append(a * a / (1.0 + a * a))
    ts, vals = np.array(ts), np.array(vals)

    def share(non):
        i = np.searchsorted(ts, np.asarray(non, np.float64) / sr, side='right') - 1
        return vals[np.clip(i, 0, len(vals) - 1)]
    return share


def cf_device(flanger, rate, depth, fb):
    """The chain's chorus or flanger as chorus.gs_copies's device: rate from
    the table, depth as the system chorus's swing, feedback +-98 %. The base
    delay is chosen -- a chorus 10 ms, a flanger 1 ms -- and a flanger's swing
    an eighth of a chorus's, so its comb stays in the flanging range."""
    r = rate2(rate)
    swing = (int(depth) + 1) / 3.2 / 1000.0 / 2.0 / (8.0 if flanger else 1.0)
    return dict(tau=(0.001 if flanger else 0.010) + swing, rate=r,
                vd=2.0 * math.pi * r * swing, fb=feedback(fb), level=1.0, lpf=None)


def eq_gain(f, eq):
    """The chain's EQ at frequency f (a number or an array), linear: first-
    order shelves at the chosen corners and a peaking mid (RBJ's magnitude,
    its Q and gain). It is AFTER the OD and its amp, as the chains have it
    (GTR Multi 2: Cmp, OD, EQ, CF) -- applied with the cabinet, to the valve's
    products too (blockrender's and streamrender's speaker pass)."""
    lo, mf, q, mg, hi = eq
    x = (f / LOW_SHELF_HZ) ** 2
    y = (f / HIGH_SHELF_HZ) ** 2
    db = lo / (1.0 + x) + hi * y / (1.0 + y)
    if mf and mg:
        u = q * (f / mf - mf / (f + 1e-6 * (f <= 0)))
        db += mg / (1.0 + u * u)
    return 10.0 ** (db / 20.0)


def selftest():
    fails = []

    def check(name, ok, detail=""):
        print("  %-62s %s%s" % (name, "ok" if ok else "FAIL", ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    check("Rate1: 0.05 Hz at 00, 0.45 at 08, 5.00 at 63, 10 at 7F",
          abs(rate1(0) - 0.05) < 1e-9 and abs(rate1(8) - 0.45) < 1e-9
          and abs(rate1(0x63) - 5.0) < 1e-9 and rate1(0x7F) == 10.0)
    check("the table (gs_efx_params): all 64 types; GTR Multi 1's defaults as checked by hand",
          len({n for n, _ in _P.TYPES.values()} - {0}) == 64
          and DEFAULTS["GTR Multi 1"] == {1: 100, 2: 80, 3: 100, 6: 80, 9: 69, 10: 74, 13: 8, 14: 30,
                                         15: 102, 16: 40, 17: 60, 18: 34, 19: 15, 20: 110}
          and TYPES[(0x03, 0x00)] == TYPES[(0x02, 0x0C)] == "Rotary Multi")
    check("Rate2, the guitar multis' CF Rate: 0.45 Hz at 08, 6.40 at 7F (not Rate1's 10)",
          abs(rate2(8) - 0.45) < 1e-9 and abs(rate2(0x7F) - 6.40) < 1e-9
          and abs(cf_device(False, 0x7F, 40, 64)['rate'] - 6.40) < 1e-9)
    _d = chain(dict(type=(4, 0), p={}, send={}))
    _e = chain(dict(type=(4, 0), p={20: 127}, send={}))
    check("a type comes up at Roland's own defaults: GTR Multi 1's level 110 of 127",
          abs(_d['level'] / _e['level'] - 110 / 127.0) < 1e-9
          and abs(_d['comp'][2] - CMP_ATTACK_MS * 100 / 127000.0) < 1e-12,
          "(level %.3f against %.3f at 127)" % (_d['level'], _e['level']))
    check("EQ Freq: 200 Hz at 00, 2 kHz at 56H, 6.3 kHz at 7F",
          eq_freq(0) == 200 and eq_freq(0x56) == 2000 and eq_freq(0x7F) == 6300)
    ev = [(0.0, ('type', (4, 1))), (0.0, ('param', 20, 40)), (5.0, ('param', 20, 100))]
    check("the timeline: Tokei's GTR Multi 2 at level 40, then 100 at 5 s",
          state_at(ev, 1.0)['p'][20] == 40 and state_at(ev, 6.0)['p'][20] == 100
          and chain(state_at(ev, 1.0))['name'] == "GTR Multi 2")
    c = chain(dict(type=(4, 1), p={5: 0, 6: 30, 9: 1, 20: 127}, send={}))
    check("the OD is a gain: Tokei's overdrive at 30 +4.7 dB, a distortion more; "
          "its makeup in the level",
          abs(20 * math.log10(c['od_gain']) - 20.0 * 30 / 127) < 1e-9
          and od_gain(30, True) > od_gain(30, False)
          and abs(20 * math.log10(c['level']) - OD_MAKEUP_DB) < 1e-9)
    check("an unbuilt type has no chain (its parts play dry)",
          chain(dict(type=(0x01, 0x22), p={}, send={})) is None)
    e = (0.0, 2000.0, 2.0, 6.0, 0.0)
    check("the mid EQ peaks at its frequency, at its gain",
          abs(20 * math.log10(eq_gain(2000.0, e)) - 6.0) < 0.3
          and 20 * math.log10(eq_gain(500.0, e)) < 1.0)
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
