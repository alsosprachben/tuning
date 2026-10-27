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

import numpy as np
import re

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
    # (the series pairs as the coverage table writes them: "OD -> Chorus")
    TYPES.setdefault(_k, _nm.replace(" \u2192 ", " -> ").replace("\u2192 ", " -> "))
TYPES[(0x02, 0x0C)] = "Rotary Multi"
_TABLE_NAME = {TYPES[_k]: _nm for _k, (_n, _nm) in _P.TYPES.items()}   # ours -> the table's
BUILT = {"GTR Multi 1", "GTR Multi 2", "GTR Multi 3", "Overdrive", "Distortion",
         "Stereo-EQ", "Space D", "Stereo Chorus", "Hexa Chorus", "Tremolo Chorus", "3D Chorus"}
CHORUS_TYPES = ("Space D", "Stereo Chorus", "Hexa Chorus", "Tremolo Chorus", "3D Chorus", "Stereo Flanger")
DELAY_TYPES = ("Stereo Delay", "Mod Delay", "3 Tap Delay", "4 Tap Delay", "Tm Ctrl Delay", "3D Delay")
BUILT |= set(DELAY_TYPES)
BUILT |= {"Rotary", "Rotary Multi", "Tremolo", "Auto Pan"}
BUILT |= {"Stereo Flanger", "3D Manual", "3D Auto", "2 Pitch Shifter", "Fb P.Shifter"}
SERIES_TYPES = ("OD -> Chorus", "OD -> Flanger", "OD -> Delay", "DS -> Chorus", "DS -> Flanger",
                "DS -> Delay", "Cho -> Delay", "FL -> Delay", "EH -> Chorus", "EH -> Flanger",
                "EH -> Delay", "Cho -> Flanger")
BUILT |= set(SERIES_TYPES) | {"Clean Gt Multi 1", "Bass Multi"}
BUILT |= {"Clean Gt Multi 2", "Rhodes Multi", "Keyboard Multi"}
# THE PARALLEL TYPES ("Cho / Delay" ...): the part into two branches, each its
# stage, its pan and its level, summed. Branch A is the part's own rows;
# branch B a copy of them on a VIRTUAL CHANNEL (the part's + VIRT), so every
# per-channel pass -- the valve, the chorus, the delay, the Leslie, the moving
# filter -- takes each branch as a part of its own. A branch's Level where
# Roland prints none: 96, as OD1's. Chosen.
PARALLEL_TYPES = ("Cho / Delay", "FL / Delay", "Cho / Flanger", "OD1 / OD2", "OD / Rotary", "OD / Phaser",
                  "OD / AutoWah", "PH / Rotary", "PH / AutoWah")
BUILT |= set(PARALLEL_TYPES)
VIRT = 1 << 16
# A TONE'S OWN MIX CHANNEL (blockrender): a part's later tones -- a program
# change to another instrument -- each on the part's channel + TONE_SEG x k,
# so what a tone brings to its channel (its amp, cabinet, Leslie, tremolo,
# its own insertion effect) is that tone's alone. part_of gives the PART
# back (the MIDI channel: its sends, the file's effect, its stem), a parallel
# type's branch B (+ VIRT) included.
TONE_SEG = 1 << 8


def part_of(mch):
    """The part (MIDI channel) a mix channel belongs to: an int, or an array."""
    import numpy as np
    if np.ndim(mch) == 0:
        return (int(mch) % VIRT) % TONE_SEG
    return (np.asarray(mch).astype(np.int64) % VIRT) % TONE_SEG
BRANCH_LEVEL = 96
_BRANCH_PREFIX = {"Cho": "Cho", "Delay": "Dly", "FL": "FL", "Flanger": "FL", "OD1": "OD1", "OD2": "OD2",
                  "OD": "OD", "Rotary": "RT", "Phaser": "PH", "PH": "PH", "AutoWah": "AW"}
# THE KEYBOARD MULTI's RING MODULATOR: its Mod Freq 0-127 onto 10 Hz-5 kHz,
# logarithmically (116 Hz at its default 50); Roland prints none. Chosen.
RM_HZ = (10.0, 5000.0)


def rm_hz(v):
    lo, hi = RM_HZ
    return lo * (hi / lo) ** (max(0, min(127, int(v))) / 127.0)
BUILT |= {"Phaser", "Auto Wah", "Step Flanger", "Humanizer"}
BUS_TYPES = ("Lo-Fi 1", "Lo-Fi 2", "Compressor", "Limiter", "Enhancer", "Gate Reverb", "Reverb")
BUILT |= {"Spectrum"}
# SPECTRUM's eight fixed bands (the SC-8850 manual's frequencies); its Width
# (Q, the same for all) where unprinted 2.0, the middle. Chosen.
SPECTRUM_HZ = (250.0, 500.0, 1000.0, 1250.0, 2000.0, 3150.0, 4000.0, 8000.0)
BUILT |= set(BUS_TYPES)

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
# THE EFFECT CONTROLLERS (SC-8850 OM, "EFX C.Src1, 2"): a source each -- Off,
# CC1-95, channel aftertouch, bend -- and a depth -100..+100 % (40H none), the
# first moving the parameter each type marks +, the second the one marked #
CTL_SRC1, CTL_DEP1, CTL_SRC2, CTL_DEP2 = 0x1B, 0x1C, 0x1D, 0x1E
SRC_CAF, SRC_BEND = 0x60, 0x61


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
        if CTL_SRC1 <= a <= CTL_DEP2:
            return ('ctl', a, int(d[7]))
        return None
    if d[4] in (0x40, 0x50) and d[5] >> 4 == 4 and d[6] == 0x22:
        blk = d[5] & 0x0F
        ch = (9 if blk == 0 else (blk - 1 if blk <= 9 else blk)) + (16 if d[4] == 0x50 else 0)
        return ('part', ch, bool(d[7]))
    return None


def fresh_state():
    """The EFX after a reset (GS Reset, GM System On): Thru, the sends at the
    module's own (reverb 40)."""
    return dict(type=(0, 0), p={}, send={SEND_REV: 40, SEND_CHO: 0, SEND_DLY: 0},
                ctl={CTL_SRC1: 0, CTL_DEP1: 0x40, CTL_SRC2: 0, CTL_DEP2: 0x40}, cv={})


def apply(st, ev, parts=None):
    """One of parse()'s events onto a state, in place -- a type change puts
    the parameters back to the type's, a reset all of it (and, given the
    set of parts on the EFX, takes them off, as the module does)."""
    if ev[0] == 'reset':
        st.clear(); st.update(fresh_state())
        if parts is not None:
            parts.clear()
    elif ev[0] == 'type':
        st['type'] = ev[1]
        st['p'] = {}
    elif ev[0] == 'param':
        st['p'][ev[1]] = ev[2]
    elif ev[0] == 'send':
        st['send'][ev[1]] = ev[2]
    elif ev[0] == 'ctl':
        st.setdefault('ctl', {})[ev[1]] = ev[2]
    elif ev[0] == 'cv':                 # a controller's value: ('cv', source code, 0-127)
        st.setdefault('cv', {})[ev[1]] = ev[2]
    elif ev[0] == 'part' and parts is not None:
        (parts.add if ev[2] else parts.discard)(ev[1])
    return st


def state_at(events, t):
    """The EFX at time t from parse()'s events [(t, ('type'|'param'|'send'|
    'reset', ...))]: {'type': (msb, lsb), 'p': {n: v}, 'send': {addr: v}}. A
    type change puts the parameters back to the type's (unknown here: the
    model's own), as the module does; a reset puts all back."""
    st = fresh_state()
    for et, ev in events:
        if et > t + 1e-9:
            break
        apply(st, ev)
    return st


def tone_state(ty, params=None):
    """The EFX state a TONE carries (tonelib's insertion_efx): its type, its
    parameters over the type's own, no sends of its own."""
    st = fresh_state()
    apply(st, ('type', tuple(ty)))
    for n, v in (params or {}).items():
        apply(st, ('param', n, v))
    return st


def tone_events(ty, params=None, part=0):
    """A tone's effect as a TIMELINE of its own (tone_state's, set at 0 with
    the part on it): what the setups read over a file -- filter_setup,
    rotary_setup, bus_setup -- where no event in the file assigns the part."""
    ev = [(0.0, ('type', tuple(ty)))] + [(0.0, ('param', n, v)) for n, v in (params or {}).items()]
    return ev + [(0.0, ('part', part_of(part), True))]


# A TONE's OWN BUS (Bit Hit's Lo-Fi, Comp Clav.'s compressor): keyed by its
# mix channel past this, as a part's bus is keyed by the part -- so a bus
# takes only that tone's rows, not the part's other tones'
TONE_BUS = 1 << 24


def bus_mask(mch, keys):
    """Rows (their mix channels) on any of these buses: a part's key takes
    every tone of the part, a tone's (TONE_BUS + mix channel) its own."""
    import numpy as np
    mch = np.asarray(mch).astype(np.int64)
    parts = [k for k in keys if k < TONE_BUS]
    tones = [k - TONE_BUS for k in keys if k >= TONE_BUS]
    return np.isin(part_of(mch), parts) | np.isin(mch, tones)


def message(ev, dev=0x10):
    """The GS DT1 SysEx data (without F0/F7) for an EFX event -- parse()'s
    inverse: what the live panel sends, so a setting made there is the
    message a file would carry."""
    if ev[0] == 'type':
        body = [0x40, 0x03, 0x00, ev[1][0], ev[1][1]]
    elif ev[0] == 'param':
        body = [0x40, 0x03, 0x02 + int(ev[1]), int(ev[2])]
    elif ev[0] in ('send', 'ctl'):
        body = [0x40, 0x03, int(ev[1]), int(ev[2])]
    elif ev[0] == 'part':
        ch = int(ev[1]) % 16
        blk = 0 if ch == 9 else (ch + 1 if ch < 9 else ch)
        body = [0x50 if ev[1] >= 16 else 0x40, 0x40 | blk, 0x22, 1 if ev[2] else 0]
    else:
        raise ValueError(ev)
    return [0x41, dev, 0x42, 0x12] + body + [(128 - sum(body) % 128) % 128]


def printed_value(name, n, v):
    """A parameter's value as Roland's panel shows it: through its value
    table (*k) where it has one, a choice by its name, +-12 dB for a gain
    (34-4C), else the number."""
    for _k, (_n, nm) in _P.TYPES.items():
        if TYPES.get(_k) == name:
            x = _P.PARAMS[nm].get(n)
            break
    else:
        return str(v)
    if x is None:
        return str(v)
    enc = x[4]
    if x[0] == "Gate Time":                         # 5-500 ms (the SC-8850's), as chain() reads it
        return "%d ms" % (5 * (min(99, int(v)) + 1))
    if enc.startswith("*"):
        t = _P.VALUE_TABLES[int(enc[1:])][max(0, min(127, int(v)))]
        ms = "m" in x[1] and t not in ("Bypass",)
        return str(t) + (" ms" if ms else "")
    if "/" in x[1] and " - " not in x[1]:
        ch = [c.strip() for c in x[1].split("/")]
        return ch[int(v)] if 0 <= int(v) < len(ch) else ch[-1] if int(v) == 127 else str(v)
    if enc == "34 - 4C":
        return "%+d dB" % (int(v) - 64)
    import re
    if "D>" in x[1] or "D=E" in x[1]:                 # a Balance: dry against effect
        v = int(v)
        return "D=E" if v == 64 else ("D>%dE" % (2 * v) if v < 64 else "D%d<E" % (2 * (127 - v)))
    m = re.match(r"^\s*([0-9A-F]{2})\s*-\s*([0-9A-F]{2})\s*$", enc)
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", x[1])
    if m and x[1].strip().startswith("-") and len(nums) >= 2:
        # a signed range on its own codes (Coarse 28-4C onto -24..+12): linear
        e0, e1 = int(m.group(1), 16), int(m.group(2), 16)
        lo, hi = float(nums[0]), float(nums[-1])
        val = lo + (max(e0, min(e1, int(v))) - e0) * (hi - lo) / float(e1 - e0)
        return "%+d%s" % (round(val), "%" if "%" in x[1] else "")
    m = re.match(r"^\s*(\d+)\s*-\s*\d+(\s*-\s*\d+)?\s*$", x[1])
    if m and not enc.startswith("00 - 7F"):          # numbered choices: "1-2-6", "1-5"
        return str(int(v) + int(m.group(1)))
    if "L63" in x[1]:
        return "C" if v == 64 else ("L%d" % (64 - v) if v < 64 else "R%d" % (v - 64))
    return str(v)


# ROLAND'S FAMILIES OF TYPES, by their numbers (the SC-8850 OM, "Insertion
# Effect Types"): the live panel's type tree
CATEGORIES = (("Tone colour (filters)", 1, 4), ("Distortion", 5, 6), ("Modulation", 7, 13),
              ("Compression", 14, 15), ("Chorus", 16, 20), ("Delay and reverb", 21, 28),
              ("Pitch", 29, 30), ("3D and Lo-Fi", 31, 34), ("Two in series", 35, 46),
              ("Three or more in series", 47, 55), ("Two in parallel", 56, 64))


def numbered():
    """[(Roland's number 1-64, (msb, lsb), our name)], in his order."""
    return sorted((n, k, TYPES[k]) for k, (n, _nm) in _P.TYPES.items() if n and k in TYPES)


def param_range(name, n):
    """The raw values parameter n of a type takes: (lo, hi) or a list of
    the codes a choice takes (Speed's 00/7F) -- from its data code."""
    for _k, (_n, nm) in _P.TYPES.items():
        if TYPES.get(_k) == name:
            x = _P.PARAMS[nm].get(n)
            break
    else:
        return (0, 127)
    enc = (x[4] if x else "").replace(" ", "")
    if "/" in enc:
        try:
            return [int(h, 16) for h in enc.split("/")]
        except ValueError:
            return (0, 127)
    if "-" in enc and not enc.startswith("*"):
        try:
            lo, hi = (int(h, 16) for h in enc.split("-"))
            return (lo, hi)
        except ValueError:
            pass
    return (0, 127)


def marks(name):
    """{'+': n, '#': n}: the parameters a type's two effect controllers move."""
    for _k, (_n, nm) in _P.TYPES.items():
        if TYPES.get(_k) == name:
            return {x[5]: n for n, x in _P.PARAMS[nm].items() if x[5] in ('+', '#')}
    return {}


def source_of(st, which):
    """(source code, depth -1..1) of effect controller `which` (1, 2), or None."""
    c = st.get('ctl') or {}
    src = int(c.get(CTL_SRC1 if which == 1 else CTL_SRC2, 0))
    if not src:
        return None
    dep = max(-1.0, min(1.0, (int(c.get(CTL_DEP1 if which == 1 else CTL_DEP2, 0x40)) - 0x40) / 63.0))
    return src, dep


def controlled(name, n, v, st):
    """Parameter n of type `name` at raw value v, as its effect controller
    moves it: "setting value + value from controller x depth (%)/100" of the
    parameter's whole range, clamped (a choice of two, Rotary's Speed, by
    halves)."""
    mk = marks(name)
    for which, m in ((1, '+'), (2, '#')):
        if mk.get(m) != n:
            continue
        so = source_of(st, which)
        if so is None:
            continue
        src, dep = so
        cv = (st.get('cv') or {}).get(src, 64 if src == SRC_BEND else 0)
        rg = param_range(name, n)
        lo, hi = (min(rg), max(rg)) if isinstance(rg, list) else rg
        x = float(v) + (hi - lo) * (cv / 127.0) * dep
        x = max(lo, min(hi, x))
        if isinstance(rg, list):
            return min(rg, key=lambda r: abs(r - x))
        return int(round(x))
    return v


_USED = {}       # the last chain()'s parameters as it read them: {n: value}


def in_effect(st):
    """{n: value} each parameter of the state's type stands at -- the file's,
    else Roland's printed default, else the model's chosen one: what the
    panel shows, as chain() reads them."""
    chain(st)
    return dict(_USED)


def params(name):
    """[(n, its name, its range as printed, its default raw value)] of a
    type, from Roland's table -- the panel's rows."""
    for _k, (_n, nm) in _P.TYPES.items():
        if TYPES.get(_k) == name:
            return [(n, x[0], x[1], x[3] if x[3] is not None else DEFAULTS.get(_k, {}).get(n))
                    for n, x in sorted(_P.PARAMS[nm].items())]
    return []


def at(events, ch, t):
    """The chain part `ch` hears at t, or None: a virtual channel (ch >=
    VIRT) the parallel type's branch B of its part's."""
    base = part_of(ch)
    if not assigned(events, base, t):
        return None
    c = chain(state_at(events, t))
    if c is None or ch < VIRT:
        return c
    return (c.get('par') or {}).get('B')


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


def table_value(k, v):
    """The value table *k's entry at v (Roland's data table), as a number."""
    x = _P.VALUE_TABLES[k][max(0, min(127, int(v)))]
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def printed(name, key):
    """A parameter's default as the table prints it ("+2"), as a number, or None."""
    for _k, (_n, nm) in _P.TYPES.items():
        if TYPES.get(_k) == name:
            for x in _P.PARAMS[nm].values():
                if x[0] == key and x[2] is not None:
                    try:
                        return float(x[2].replace("m", ""))
                    except ValueError:
                        return None
    return None


# THE CHORUS TYPES' VOICES, where Roland gives no number: Space D's and the
# Stereo Chorus's two outputs' LFOs half a turn apart when the file sends no
# Phase (its default prints only its range); a Hexa Chorus's Pre Dly Dev in
# steps of 0.5 ms; the Tremolo Chorus's tremolo at half depth. Chosen.
CHORUS_PHASE_DEG = 180.0
HEXA_DLY_STEP_MS = 0.5
TREMOLO_CHORUS_DEPTH = 0.5


# THE INSERTION EFFECTS' DEPTH (their choruses and flangers, 0-127): read at
# first as the system chorus's law, (v+1)/3.2 ms of swing peak to peak -- but
# the types' own defaults sit far up that scale (the Stereo Chorus's 111: a
# 17.5 ms swing, its copies +-84 cents at 0.45 Hz, the goblins Ben heard on
# JC Chorus Gt), so their scale is finer: EFX_DEPTH_SCALE of it -- 0.2, Ben's
# ear, between the A/B's 1/4 and 1/8 (JC Chorus Gt, LP Chorus, ChorusJazzBs
# and SENSATIO's Space Voice on Space D): the Stereo Chorus's 111 a 3.5 ms
# swing, its copies +-17 cents at 0.45 Hz. THE CHORUSES ONLY: a flanger's
# swing stays an eighth of the system law's (its comb in the flanging range),
# unheard by Ben at the new scale. TUNING_EFX_DEPTH_SCALE for an A/B.
EFX_DEPTH_SCALE = float(__import__("os").environ.get("TUNING_EFX_DEPTH_SCALE", "0.2"))


def efx_swing(depth, flanger=False):
    """An insertion chorus's or flanger's swing, seconds either way."""
    return (int(depth) + 1) / 3.2 / 1000.0 / 2.0 * (1.0 / 8.0 if flanger else EFX_DEPTH_SCALE)


def _chorus(name, g, pn):
    """A chorus type's device for chorus.gs_copies, with its voices (taps:
    (side, LFO phase, extra delay s, depth factor)): the pre-delay and the
    rate from Roland's tables (*1, *6), the depth as the system chorus's
    swing; Space D and the Stereo Chorus two outputs apart by their Phase,
    the Hexa Chorus six voices spread in delay, depth and pan by its Dev
    parameters, the 3D Chorus's two placed wider than the speakers."""
    rate = table_value(6, g("Rate" if "Rate" in pn else "Cho Rate", 8))
    depth = g("Depth" if "Depth" in pn else "Cho Depth", 64)
    # a flanger's swing an eighth of the system law's, as cf_device's, so its
    # comb stays in the flanging range; its feedback the comb's depth
    swing = efx_swing(depth, name == "Stereo Flanger")
    fb = 0.0
    if name == "Stereo Flanger":
        fb = feedback(g("Feedback", 104))
    pre = (table_value(1, g("Pre Dly", 10)) or 0.0) / 1000.0
    ph = math.radians(2.0 * g("Phase", int(CHORUS_PHASE_DEG / 2.0))) if "Phase" in pn \
        else math.radians(CHORUS_PHASE_DEG)
    if name == "Hexa Chorus":
        dd = g("Pre Dly Dev", printed(name, "Pre Dly Dev") or 0)
        dv = (g("Depth Dev", 0x40 + int(printed(name, "Depth Dev") or 0)) - 0x40) / 20.0
        pd = g("Pan Dev", printed(name, "Pan Dev") or 0) / 20.0
        taps = [(pd * (2.0 * k / 5.0 - 1.0), 2.0 * math.pi * k / 6.0,
                 HEXA_DLY_STEP_MS * dd * (k / 5.0 - 0.5) / 1000.0, max(0.0, 1.0 + dv * (k / 5.0 - 0.5)))
                for k in range(6)]
    elif name == "3D Chorus":
        taps = [(('deg', -60.0), 0.0, 0.0, 1.0), (('deg', 60.0), math.pi, 0.0, 1.0)]
    else:
        taps = [('l', 0.0, 0.0, 1.0), ('r', ph, 0.0, 1.0)]
    lpf = None
    if "Pre Filter" in pn and g("Pre Filter", 0) == 1:      # the LPF; its HPF is not built
        lpf = table_value(9, g("Cutoff", 127))
    return dict(tau=pre + swing, rate=rate, vd=2.0 * math.pi * rate * swing, fb=fb, level=1.0,
                lpf=lpf, taps=taps)


def balance(v):
    """(dry, effect) levels of an insertion type's Balance, 0-127, as the
    table labels its scale: "D>xE" the dry whole and the effect at x/127
    (x = 2v) up to D=E (40H), both whole; past it "D x<E", the effect whole
    and the dry at x/127."""
    v = max(0, min(127, int(v)))
    if v <= 0x40:
        return 1.0, min(1.0, 2.0 * v / 127.0)
    return min(1.0, 2.0 * (127 - v) / 127.0), 1.0


# THE DELAY TYPES' TAPS where Roland prints no default: the 3 and 4 Tap's
# levels whole, the 4 Tap's taps spread across the field (left to right,
# 1 to 4), the 3D Delay's sides at 60 degrees. Chosen.
TAP_LEVEL = 127
FOUR_TAP_SIDES = (-1.0, -1.0 / 3.0, 1.0 / 3.0, 1.0)
DRY_FLOOR = 1e-3          # an effect-only balance keeps its rows, just under hearing


def _delay(name, g, pn, sec):
    """A delay type's device for gsdelay (taps (seconds, level, side,
    period), feedback, its HF damping as a low-pass, the Mod Delay's
    modulation, a cross-feedback's ping-pong), and its Balance."""
    fb = feedback(g("Feedback", 64))
    hf = table_value(8, g("HF Damp", 127))           # Bypass: none
    if name in ("Stereo Delay", "Mod Delay"):
        tl, tr = sec("Dly Tm L"), sec("Dly Tm R")
        sl = -1.0 if g("Phase L", 0) else 1.0
        sr_ = -1.0 if g("Phase R", 0) else 1.0
        taps = [(tl, sl, 'l', tl), (tr, sr_, 'r', tr)]
    elif name in ("3 Tap Delay", "3D Delay"):
        sides = ('c', 'l', 'r') if name == "3 Tap Delay" else ('c', ('deg', -60.0), ('deg', 60.0))
        taps = [(sec("Dly Tm " + k), g("Dly Lev " + k, TAP_LEVEL) / 127.0, sd, sec("Dly Tm C"))
                for k, sd in zip("CLR", sides)]
    elif name == "4 Tap Delay":
        taps = [(sec("Dly Tm %d" % j), g("Dly Lev %d" % j, TAP_LEVEL) / 127.0, FOUR_TAP_SIDES[j - 1],
                 sec("Dly Tm 1")) for j in range(1, 5)]
    else:                                             # Tm Ctrl Delay: one tap, placed
        t = sec("Dly Time")
        taps = [(t, 1.0, (g("EFX Pan", 64) - 64) / 63.0 if g("EFX Pan", 64) != 64 else 'c', t)]
    dev = dict(tc=taps[0][3], taps=[x for x in taps if x[1] != 0.0], level=1.0, fb=fb,
               lpf=hf, to_reverb=0.0)
    if name == "Stereo Delay" or name == "Mod Delay":
        dev['cross'] = bool(g("Fb Mode", 0))
    if name == "Mod Delay":
        dev['mod'] = (table_value(6, g("Mod Rate", 12)), efx_swing(g("Mod Depth", 21)),
                      math.radians(2.0 * g("Mod Phase", 45)))
    return dev


# THE ROTARY'S ACCELERATION (Accl 0-15): Roland gives no times. Taken
# through our Leslie's measured spin-ups at the type's own defaults -- the
# horn's Accl 11 its 1.0 s, the drum's Accl 3 its 3.5 s -- on a log line
# (5.6 s at 0, 0.5 s at 15); coasting down 1.4 times slower, as ours do.
def accl_tau(a):
    up = math.exp(1.7226 - 0.1566 * float(a))
    return up, 1.4 * up


def _rotary(name, g, pn):
    """A Rotary's rotors: (slow, fast) Hz for the drum (Low) and the horn (Hi),
    their spin times, their levels, and the speed the file asks for."""
    pre = "RT " if name == "Rotary Multi" else ""
    k = {"Low Slow": "L Slow", "Low Fast": "L Fast", "Low Accl": "Lo Accl", "Low Level": "Lo Lev",
         "Hi Slow": "H Slow", "Hi Fast": "H Fast", "Hi Accl": "Hi Accl", "Hi Level": "Hi Lev",
         "Speed": "Speed"} if pre else None
    n = (lambda key: pre + k[key]) if pre else (lambda key: key)
    lo = (table_value(6, g(n("Low Slow"), 6)), table_value(6, g(n("Low Fast"), 113)))
    hi = (table_value(6, g(n("Hi Slow"), 17)), table_value(6, g(n("Hi Fast"), 120)))
    acc = lambda key, d: table_value(14, g(n(key), d))
    llv, hlv = g(n("Low Level"), 127), g(n("Hi Level"), 64)
    top = float(max(llv, hlv, 1))
    # SEPARATE, the two microphones' spacing round the cabinet (leslie's
    # recorded rotary): Roland gives no units; 0-127 onto 0-180 degrees apart
    # (the default 96 at 136), chosen
    sepk = "RT Sept" if pre else "Separate"
    return dict(drum=lo, horn=hi, drum_tau=accl_tau(acc("Low Accl", 24)),
                horn_tau=accl_tau(acc("Hi Accl", 88)), levels=(llv / top, hlv / top),
                fast=bool(g(n("Speed"), 0)), separate=math.pi * g(sepk, 96) / 127.0)


def rotary_setup(events, ch):
    """A part's Rotary over the file (leslie's channel dict): each rotor's
    speed requests -- slow or fast as the type's Speed stands at each change
    of the timeline -- and the first setting's spin times and levels."""
    first, horn, drum = None, [], []
    for t in sorted({0.0} | {t for t, _ in events}):
        c = at(events, ch, t)
        rt = c.get('rotary') if c is not None else None
        if rt is None:
            continue
        first = first or rt
        horn.append((t, rt['horn'][1] if rt['fast'] else rt['horn'][0]))
        drum.append((t, rt['drum'][1] if rt['fast'] else rt['drum'][0]))
    if first is None:
        return None
    return dict(horn=horn, drum=drum, horn_tau=first['horn_tau'], drum_tau=first['drum_tau'],
                levels=first['levels'], separate=first['separate'])


# THE TREMOLO'S WAVES as their Fourier series about their own mean, peak 1:
# (harmonic, coefficient, phase) -- Tri, Sqr, Sin, Saw1, Saw2 (Mod Wave 0-4)
_TRI = [(k, 8.0 / (math.pi * k) ** 2, 0.0) for k in (1, 3, 5, 7)]
_SQR = [(k, 4.0 / (math.pi * k) * (1 if (k // 2) % 2 == 0 else -1), 0.0) for k in (1, 3, 5, 7, 9)]
_SAW = [(k, 2.0 / (math.pi * k), (-1) ** (k + 1) * -math.pi / 2.0) for k in range(1, 7)]
WAVES = (_TRI, _SQR, [(1, 1.0, 0.0)], _SAW, [(k, c, p + math.pi) for k, c, p in _SAW])


def azimuth(v):
    """The 3D types' Azimuth (value table *13: "L168", "0", "R12",
    "L180(=R180)"), degrees, + to the right."""
    x = str(_P.VALUE_TABLES[13][max(0, min(127, int(v)))])
    m = re.match(r"([LR])(\d+)", x)
    return 0.0 if not m else float(m.group(2)) * (1.0 if m.group(1) == "R" else -1.0)


# 3D AUTO's turning where Roland prints no default: on, clockwise (+). Chosen.
AUTO_TURN, AUTO_CLOCKWISE = 1, 1


def semitones(coarse, fine):
    """A pitch shifter's ratio: Coarse -24..+12 semitones about 40H, Fine
    -100..+100 cents, 2 a step about 40H."""
    return 2.0 ** ((coarse - 0x40) / 12.0 + (fine - 0x40) * 2.0 / 1200.0)


# THE MOVING FILTERS' LAWS where Roland gives no numbers (efxfilter's own:
# WAH_HZ, WAH_Q, PHASER_STAGES): the Phaser's Depth 0-127 onto +-2 octaves of
# sweep, its Mix (unprinted) at the middle, its Reso onto 0-0.9; the Auto
# Wah's Depth onto 3 octaves up from its Manual, BPF and Up where unset; the
# Humanizer's Accel 0-15 onto a glide of 0.5 s down to 15 ms. Chosen.
PHASER_OCT, AUTOWAH_OCT = 2.0, 3.0
# THE AUTO WAH'S SENS: the filter opened by the part's own loudness as well as
# its LFO -- Sens 0-127 onto up to AUTOWAH_SENS_OCT octaves at a full
# envelope. The envelope is the part's NOTES' (velocity / 127, rising in
# 5 ms, falling as a struck note does while held, and quickly after its
# release; the loudest note at each moment), not its audio's: the filter is
# set before the part renders, and a note's envelope is the same in the
# stream as in the whole table. Chosen.
AUTOWAH_SENS_OCT = 3.0
WAH_ENV_ATTACK, WAH_ENV_HOLD, WAH_ENV_RELEASE = 0.005, 0.4, 0.06


def note_envelope(notes):
    """t (s, array) -> the part's envelope 0..1 from its notes (start, end,
    velocity): each note's level, the loudest at each moment."""
    nts = [(float(s), float(e), v / 127.0) for s, e, v in notes]

    def env(t):
        t = np.asarray(t, float)
        out = np.zeros(len(t))
        for s, e, a in nts:
            i0 = np.searchsorted(t, s)
            i1 = np.searchsorted(t, e + 8.0 * WAH_ENV_RELEASE)
            if i1 <= i0:
                continue
            tt = t[i0:i1]
            u = tt - s
            held = a * np.minimum(1.0, u / WAH_ENV_ATTACK) * np.exp(-u / WAH_ENV_HOLD)
            at_end = a * np.exp(-(e - s) / WAH_ENV_HOLD)
            lv = np.where(tt <= e, held, at_end * np.exp(-np.maximum(tt - e, 0.0) / WAH_ENV_RELEASE))
            out[i0:i1] = np.maximum(out[i0:i1], lv)
        return out
    return env


def _filter(name, g, pn):
    """A moving filter's spec (efxfilter): type, parameters, and its control
    while this setting stands -- ('sweep', base Hz, octaves, rate, up?),
    ('wah', Hz), ('comb', base s, swing s, rate, step rate), ('vowel', i, glide)."""
    import efxfilter as EF
    if name == "Phaser":
        return dict(ty=1, pa=g("Mix", 64) / 127.0, pb=0.9 * g("Reso", 16) / 127.0, pc=EF.PHASER_STAGES,
                    ctrl=('sweep', table_value(12, g("Manual", 36)), PHASER_OCT * g("Depth", 64) / 127.0,
                          table_value(6, g("Rate", 16)), None, 0.0))
    if name == "Auto Wah":
        return dict(ty=2 if g("Fil Type", 1) == 0 else 3, pa=EF.wah_q(g("Peak", 62)), pb=1.0, pc=0.0,
                    ctrl=('sweep', EF.wah_hz(g("Manual", 68)), AUTOWAH_OCT * g("Depth", 72) / 127.0,
                          table_value(6, g("Rate", 40)), bool(g("Polarity", 1)),
                          AUTOWAH_SENS_OCT * g("Sens", 0) / 127.0))
    if name == "GTR Multi 3":
        if not g("Wah Sw", 1):
            return None
        return dict(ty=2 if g("Wah Fil", 1) == 0 else 3, pa=EF.wah_q(g("Wah Peak", 10)), pb=1.0, pc=0.0,
                    ctrl=('wah', EF.wah_hz(g("Wah Man", 60))))
    if name == "Clean Gt Multi 2":
        if not g("AW Sw", 1):              # unprinted: on
            return None
        return dict(ty=2 if g("AW Filter", 1) == 0 else 3, pa=EF.wah_q(g("AW Peak", 40)), pb=1.0, pc=0.0,
                    ctrl=('sweep', EF.wah_hz(g("AW Man", 55)), AUTOWAH_OCT * g("AW Depth", 80) / 127.0,
                          rate2(g("AW Rate", 29)), True, 0.0))
    if name in ("Rhodes Multi", "Keyboard Multi"):
        return dict(ty=1, pa=g("PH Mix", 64) / 127.0, pb=0.9 * g("PH Reso", 16) / 127.0, pc=EF.PHASER_STAGES,
                    ctrl=('sweep', table_value(12, g("PH Man", 36)), PHASER_OCT * g("PH Depth", 32) / 127.0,
                          rate2(g("PH Rate", 16)), None, 0.0))
    if name == "Step Flanger":
        swing = efx_swing(g("Depth", 95), True)
        pre = (table_value(1, g("Pre Dly", 10)) or 0.0) / 1000.0
        return dict(ty=4, pa=g("Balance", 64) / 127.0, pb=feedback(g("Feedback", 79)), pc=0.0,
                    ctrl=('comb', pre, swing, table_value(6, g("Rate", 5)), table_value(6, g("Step Rate", 54))))
    if name == "Humanizer":
        acc = table_value(14, g("Accel", 64)) or 8.0
        return dict(ty=5, pa=EF.VOWEL_FLOOR, pb=1.5, pc=0.0,
                    ctrl=('vowel', min(4, g("Vowel", 0)), 0.5 * (0.03 ** (acc / 15.0))))
    return None


def bus_setup(events, ch, sr):
    """A part's bus over the file (efxbus.Bus's spec): the first setting's
    processor and mix, and the spans (samples) when the part is on it."""
    spans, first, start = [], None, None
    ts = sorted({0.0} | {t for t, _ in events})
    for i, t in enumerate(ts):
        c = at(events, ch, t)
        on = c is not None and c.get('bus') is not None
        if on and first is None:
            first = c
        if on and start is None:
            start = int(round(t * sr))
        if not on and start is not None:
            spans.append((start, int(round(t * sr)))); start = None
    if start is not None:
        spans.append((start, 1 << 62))
    if first is None:
        return None
    return dict(kind=first['bus'][0], kw=first['bus'][1], spans=spans,
                mix=first.get('bus_mix', (0.0, 1.0)))


def filter_setup(events, ch, notes=()):
    """A part's moving filter over the file (efxfilter.Channel): its type and
    parameters as first set, its control from each setting of the timeline,
    held until the next -- a sweep's LFO on the absolute clock, a wah's pedal
    where the file moved it, the Humanizer's vowels gliding at its Accel; an
    Auto Wah's Sens from the part's notes ((start, end, velocity))."""
    import efxfilter as EF
    segs = []
    for t in sorted({0.0} | {t for t, _ in events}):
        c = at(events, ch, t)
        f = c.get('filter') if c is not None else None
        if f is not None:
            segs.append((t, f))
    if not segs:
        return None
    f0 = segs[0][1]
    ts = np.array([t for t, _ in segs])
    kind = f0['ctrl'][0]
    env = note_envelope(notes) if any(f['ctrl'][0] == 'sweep' and f['ctrl'][5] for _, f in segs) else None
    if kind == 'vowel':
        vt = [t for t, _ in segs]
        fs = [EF.VOWEL_F[f['ctrl'][1]] for _, f in segs]
        rows = [EF.steps(vt, [x[k] for x in fs], glide=f0['ctrl'][2]) for k in range(3)]
        return EF.Channel(5, f0['pa'], f0['pb'], f0['pc'], lambda t: [r(t) for r in rows], rows=3)

    def control(t):
        t = np.asarray(t, float)
        i = np.clip(np.searchsorted(ts, t, side='right') - 1, 0, len(segs) - 1)
        out = np.empty(len(t))
        for k, (_, f) in enumerate(segs):
            m = i == k
            if not m.any():
                continue
            c, tt = f['ctrl'], t[m]
            if c[0] == 'sweep':
                lf = np.sin(2.0 * math.pi * c[3] * tt)
                if c[4] is None:                      # a phaser: about its Manual
                    out[m] = c[1] * 2.0 ** (c[2] * lf)
                else:                                 # an auto wah: up (or down) from it
                    oc = c[2] * 0.5 * (1.0 + lf)
                    if c[5] and env is not None:      # ...and by the part's loudness
                        oc = oc + c[5] * env(tt)
                    out[m] = c[1] * 2.0 ** ((1.0 if c[4] else -1.0) * oc)
            elif c[0] == 'wah':
                out[m] = c[1]
            else:                                     # a flanger's line, stepped or not
                held = tt if c[4] is None else np.floor(tt * c[4]) / c[4]
                out[m] = c[1] + c[2] * 0.5 * (1.0 + np.sin(2.0 * math.pi * c[3] * held))
        return out
    return EF.Channel(f0['ty'], f0['pa'], f0['pb'], f0['pc'], control)


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

    _USED.clear()

    _mk = marks(name) if (st.get('ctl') and any(st['ctl'].get(a) for a in (CTL_SRC1, CTL_SRC2))) else {}

    def g(key, d):                     # the file's, the type's, ours -- and its controller's
        n = pn.get(key)
        v = d if n is None else p.get(n, dflt.get(n, d))
        if n is not None:
            if _mk and n in _mk.values():
                v = controlled(name, n, v, st)
            _USED[n] = v
        return v
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
    if name in CHORUS_TYPES:
        out['cf'] = (_chorus(name, g, pn), 0.0)
        out['cf_share'] = g("Balance", 64) / 127.0
        out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        if name == "Tremolo Chorus":
            out['trem'] = (table_value(6, g("Trem Rate", 60)), TREMOLO_CHORUS_DEPTH,
                           g("Trem Sep", 96) > 0)
        return out
    if name in BUS_TYPES:
        # A PART'S OWN BUS (efxbus): rendered to its own buffer, processed,
        # added back -- its dry against its effect by Balance where it has one
        # (Lo-Fi's unprinted: the effect alone, chosen)
        if name == "Lo-Fi 1":
            out['bus'] = ('lofi', dict(lofi_type=g("Lo-Fi Type", 5) + 1, pre=g("Pre Filter", 1) + 1,
                                       post=g("Post Filter", 1) + 1))
            out['bus_mix'] = balance(g("Balance", 127))
        elif name == "Lo-Fi 2":
            # its unprinted defaults: no detune, white, the noises silent
            # and unfiltered, LP, 50 Hz, stereo, the effect alone. Chosen.
            lpf = lambda v: table_value(11, v)          # noqa: E731 (None: Bypass)
            out['bus'] = ('lofi2', dict(lofi_type=g("Lo-Fi Type", 1) + 1, fil_type=g("Fil Type", 0),
                                        cutoff=table_value(9, g("Cutoff", 32)) or 630.0,
                                        detune=g("R.Detune", 0), radio_nz=g("R.Nz Lev", 64),
                                        pink=g("W/P Sel", 0), wp_lpf=lpf(g("W/P LPF", 127)),
                                        wp_level=g("W/P Level", 0), disc_type=g("Disc Type", 0),
                                        disc_lpf=lpf(g("Disc LPF", 127)), disc_level=g("Disc Nz Lev", 0),
                                        hum_type=g("Hum Type", 0), hum_lpf=lpf(g("Hum LPF", 127)),
                                        hum_level=g("Hum Level", 0), stereo=g("M/S", 1),
                                        pan=g("Pan(Mono)", 64)))
            out['bus_mix'] = balance(g("Balance", 127))
        elif name == "Gate Reverb":
            # Gate Time 0-99 onto 5-500 ms (the SC-8850's range; 12 its 65 ms)
            out['bus'] = ('gate', dict(gtype=g("Type", 0), pre_ms=table_value(1, g("Pre Dly", 5)) or 0.0,
                                       gate_ms=5.0 * (min(99, g("Gate Time", 12)) + 1)))
            out['bus_mix'] = balance(g("Balance", 32))
        elif name == "Reverb":
            out['bus'] = ('reverb', dict(rtype=g("Type", 0), pre_ms=table_value(1, g("Pre Dly", 112)) or 0.0,
                                         time=g("Time", 120), damp_hz=table_value(8, g("HF Damp", 104))))
            out['bus_mix'] = balance(g("Balance", 64))
        elif name == "Compressor":
            out['bus'] = ('comp', dict(attack=g("Attack", 72), sustain=g("Sustain", 100),
                                       post_gain=g("Post Gain", 0)))
        elif name == "Limiter":
            out['bus'] = ('limit', dict(threshold=g("Threshold", 85), ratio=g("Ratio", 2),
                                        release=g("Release", 16), post_gain=g("Post Gain", 0)))
        else:
            out['bus'] = ('enh', dict(sens=g("Sens", 64), mix=g("Mix", 64)))
        out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        return out
    if name in ("Phaser", "Auto Wah", "Step Flanger", "Humanizer"):
        out['filter'] = _filter(name, g, pn)
        out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        if name == "Humanizer" and g("Drive Sw", 0):      # its drive before the vowel
            out['od_gain'] = od_gain(g("Drive", 48), False)
            out['level'] *= mk
        return out
    if name in ("3D Manual", "3D Auto"):
        # THE PART PLACED IN 3D: its angle the type's Azimuth (past the
        # speakers, behind) -- and 3D Auto's turning on at its Speed, each
        # note at the angle its onset finds (pos3d: degrees, turns a second)
        turn = 0.0
        if name == "3D Auto" and g("Turn", AUTO_TURN):
            turn = table_value(6, g("Speed", 25)) * (1.0 if g("Clockwise", AUTO_CLOCKWISE) else -1.0)
        out['pos3d'] = (azimuth(g("Azimuth", 62)), turn)
        return out
    if name in ("2 Pitch Shifter", "Fb P.Shifter"):
        # gsdelay taps that move each repeat's pitch (repeats_full): the
        # two voices at their own pitch, delay and pan, the L.Bal between
        # them; the feedback one's repeats spiralling by its ratio again
        pre = lambda key, d: (table_value(1, g(key, d)) or 0.0) / 1000.0
        side = lambda key: (g(key, 64) - 64) / 63.0 if g(key, 64) != 64 else 'c'
        if name == "2 Pitch Shifter":
            la, lb = balance(g("L.Bal", 64))
            taps = [(pre("Pre Dly 1", 0), la, side("EFX Pan 1"), 1.0,
                     semitones(g("Coarse 1", 71), g("Fine 1", 62))),
                    (pre("Pre Dly 2", 0), lb, side("EFX Pan 2"), 1.0,
                     semitones(g("Coarse 2", 59), g("Fine 2", 66)))]
            fb = 0.0
        else:
            t = pre("Pre Dly", 95)
            taps = [(t, 1.0, side("EFX Pan"), t, semitones(g("P.Coarse", 71), g("P.Fine", 64)))]
            fb = feedback(g("Feedback", 84))
        dry, wet = balance(g("Balance", 64))
        out['dly'] = dict(tc=max(taps[0][0], 1e-3), taps=taps, level=wet / max(dry, DRY_FLOOR), fb=fb,
                          lpf=None, to_reverb=0.0)
        out['level'] *= max(dry, DRY_FLOOR)
        out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        return out
    if name in ("Rotary", "Rotary Multi"):
        out['rotary'] = _rotary(name, g, pn)
        if name == "Rotary Multi":
            # its OD and EQ before the rotors: the OD the valve's gain stage
            # (no guitar cabinet -- the Leslie is the speaker), the EQ after
            if g("OD Sw", 1):
                out['od_gain'] = od_gain(g("OD Drive", 13), False)
                out['level'] *= mk
            out['eq'] = (gain_db(g("EQ L Gain", 64)), eq_freq(g("EQ M Fq", 72)), EQ_Q[min(4, g("EQ M Q", 1))],
                         gain_db(g("EQ M Gain", 64)), gain_db(g("EQ H Gain", 64)))
        else:
            out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        return out
    if name in ("Tremolo", "Auto Pan"):
        # ROLAND'S DEPTH DIPS THE LEVEL (1 - d .. 1); the tremolo pass swings
        # about its carrier, so the part is taken down to the swing's middle
        # and the swing measured from there
        d = g("Mod Depth", 96) / 127.0
        mid = 1.0 - 0.5 * d
        out['level'] *= mid
        out['trem'] = (table_value(6, g("Mod Rate", 60)), 0.5 * d / mid, name == "Auto Pan", 0.0,
                       WAVES[min(4, g("Mod Wave", 2))])
        out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        return out
    if name in DELAY_TYPES:
        def sec(key):                    # a time through its own value table, seconds
            n = pn[key]
            enc = next(x[4] for x in _P.PARAMS[_TABLE_NAME[name]].values() if x[0] == key)
            return (table_value(int(enc[1:]), g(key, dflt.get(n, 0))) or 0.0) / 1000.0
        dry, wet = balance(g("Balance", 37))
        dev = _delay(name, g, pn, sec)
        dev['level'] = wet / max(dry, DRY_FLOOR)
        out['dly'] = dev
        out['level'] *= max(dry, DRY_FLOOR)
        out['eq'] = (gain_db(g("Low Gain", 64)), None, None, 0.0, gain_db(g("Hi Gain", 64)))
        return out
    if name == "Spectrum":
        # a static filter: each partial's gain at its frequency (eq_gain's
        # mids, no shelves), as exact in the partials as the Stereo-EQ
        q = EQ_Q[min(4, g("Width", 2))]
        out['eq'] = (0.0, None, None, 0.0, 0.0, LOW_SHELF_HZ, HIGH_SHELF_HZ) + tuple(
            (hz, q, gain_db(g("Band %d" % (i + 1), 64))) for i, hz in enumerate(SPECTRUM_HZ))
        return out
    if name == "Stereo-EQ":
        out['eq'] = (gain_db(g("Low Gain", 64)), eq_freq(g("M1 Freq", 72)), EQ_Q[min(4, g("M1 Q", 1))],
                     gain_db(g("M1 Gain", 64)), gain_db(g("Hi Gain", 64)),
                     (200.0, 400.0)[min(1, g("Low Freq", 0))], (4000.0, 8000.0)[min(1, g("Hi Freq", 0))],
                     (eq_freq(g("M2 Freq", 56)), EQ_Q[min(4, g("M2 Q", 1))], gain_db(g("M2 Gain", 64))))
        return out
    if name in PARALLEL_TYPES:
        a, b = (_BRANCH_PREFIX[x.strip()] for x in name.split(" / "))
        ob = dict(out, sends=dict(out['sends']))
        for o, pre in ((out, a), (ob, b)):
            _stage(o, pre, g, pn, mk)
            o['level'] *= max(g(pre + " Level", BRANCH_LEVEL), 1) / 127.0
        out['par'] = dict(B=ob, pan=g(a + " Pan", 64), panB=g(b + " Pan", 64))
        return out
    if name in SERIES_TYPES:
        # THE SERIES PAIRS (OD/DS -> Chorus/Flanger/Delay, Cho/FL -> Delay):
        # each stage by its names, as the multis' -- the drive the valve's gain
        # stage and its cabinet, the chorus or flanger a gs_copies device
        # (Bal its share), the delay a gsdelay tap (Bal its dry and effect).
        # Our passes run the delay before the chorus, so "Cho -> Delay" runs
        # the other way about; a slow sweep sounds alike either way. The
        # Enhancer (EH -> ...) is the part's bus (efxbus), so it runs AFTER the
        # chorus, flanger or delay, the other way about too: it brightens the
        # copies as it would the source. Cho -> Flanger: the chorus the copies,
        # the flanger after them a moving comb (efxfilter, Step Flanger's
        # without the steps) on every row, the copies' too -- in its order.
        if "EH Sens" in pn:              # its Mix unprinted: the Enhancer's 64
            out['bus'] = ('enh', dict(sens=g("EH Sens", 64), mix=g("EH Mix", 64)))
        for od in ("OD", "DS"):
            if od + " Drive" in pn:
                out['od_gain'] = od_gain(g(od + " Drive", 48), od == "DS")
                out['level'] *= mk
                if g(od + " Amp Sw", 1):
                    out['cabinet'] = 'guitar12'
        for mod in ("Cho", "FL"):
            if mod == "FL" and "Cho Rate" in pn and "FL Rate" in pn:
                swing = efx_swing(g("FL Depth", 24), True)
                pre = (table_value(1, g("FL Dly", 16)) or 0.0) / 1000.0
                out['filter'] = dict(ty=4, pa=g("FL Bal", 64) / 127.0, pb=feedback(g("FL Fb", 104)), pc=0.0,
                                     ctrl=('comb', pre, swing, table_value(6, g("FL Rate", 11)), None))
                continue
            if mod + " Rate" in pn:
                rate = table_value(6, g(mod + " Rate", 8))
                swing = efx_swing(g(mod + " Depth", 64), mod == "FL")
                pre = (table_value(1, g(mod + " Dly", 10)) or 0.0) / 1000.0
                out['cf'] = (dict(tau=pre + swing, rate=rate, vd=2.0 * math.pi * rate * swing,
                                  fb=feedback(g("FL Fb", 104)) if mod == "FL" else 0.0, level=1.0, lpf=None), 0.0)
                out['cf_share'] = g(mod + " Bal", 64) / 127.0
        if "Dly Time" in pn:
            t = (table_value(4, g("Dly Time", 106)) or 0.0) / 1000.0
            dry, wet = balance(g("Dly Bal", 37))
            out['dly'] = dict(tc=t, taps=[(t, 1.0, 'c', t)], level=wet / max(dry, DRY_FLOOR),
                              fb=feedback(g("Dly Fb", 80)), lpf=table_value(8, g("Dly HF", 127)), to_reverb=0.0)
            out['level'] *= max(dry, DRY_FLOOR)
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
            out['cabinet'] = 'bass410' if name == "Bass Multi" else 'guitar12'
    if "EQ L Gain" in pn:
        out['eq'] = (gain_db(g("EQ L Gain", 64)), eq_freq(g("EQ M Fq", 64)), EQ_Q[min(4, g("EQ M Q", 1))],
                     gain_db(g("EQ M Gain", 64)), gain_db(g("EQ H Gain", 64)))
    elif "OD L Gain" in pn:           # the OD's own low and high gains
        out['eq'] = (gain_db(g("OD L Gain", 64)), None, None, 0.0, gain_db(g("OD H Gain", 64)))
    if "CF Rate" in pn:
        out['cf'] = (cf_device(bool(g("CF Sel", 0)), g("CF Rate", 8), g("CF Depth", 40), g("CF Fb", 64)),
                     g("CF Mix", 0) / 127.0)
    if name == "GTR Multi 3":
        out['filter'] = _filter(name, g, pn)     # its wah (efxfilter), before the OD
    if name in ("Clean Gt Multi 2", "Rhodes Multi", "Keyboard Multi"):
        out['filter'] = _filter(name, g, pn)     # an auto wah, or a phaser (efxfilter)
    if "EH Sens" in pn:
        # the Rhodes Multi's Enhancer: the part's bus, so AFTER its phaser and
        # chorus where Roland has it first -- it brightens their output alike
        out['bus'] = ('enh', dict(sens=g("EH Sens", 64), mix=g("EH Mix", 64)))
    if "TP Sw" in pn and g("TP Sw", 1):
        # its Tremolo/Pan (unprinted: on, Trem, the sine), as the Tremolo type's
        d = g("TP Mod Dep", 64) / 127.0
        mid = 1.0 - 0.5 * d
        out['level'] *= mid
        out['trem'] = (rate2(g("TP Mod RT", 60)), 0.5 * d / mid, bool(g("TP Sel", 0)), 0.0,
                       WAVES[min(4, g("TP Mod WV", 2))])
    if "Dly Time" in pn:
        # the chain's own delay, as the GS delay's repeats (gsdelay): one tap,
        # 0-635 ms (5 ms a step), its feedback 0-127, its mix
        t, f, x = g("Dly Time", 60), g("Dly Fb", 32), g("Dly Mix", 0)
        if x:
            out['dly'] = dict(tc=t * 0.005, taps=[(t * 0.005, 1.0, 'c')], level=x / 127.0,
                              fb=f / 128.0, lpf=None, to_reverb=0.0)
    if name == "Keyboard Multi":
        out['dly'] = _keyboard_multi(g, out['dly'], out)
    return out


def _stage(o, pre, g, pn, mk):
    """One branch's stage into chain dict o, by its parameters' prefix: a
    chorus or flanger (gs_copies), a delay (gsdelay), an OD (the valve and
    cabinet), a rotary (the Leslie), a phaser or auto wah (efxfilter)."""
    import efxfilter as EF
    if pre in ("Cho", "FL"):
        rate = table_value(6, g(pre + " Rate", 8))
        swing = efx_swing(g(pre + " Depth", 64), pre == "FL")
        dl = (table_value(1, g(pre + " Dly", 10)) or 0.0) / 1000.0
        o['cf'] = (dict(tau=dl + swing, rate=rate, vd=2.0 * math.pi * rate * swing,
                        fb=feedback(g("FL Fb", 104)) if pre == "FL" else 0.0, level=1.0, lpf=None), 0.0)
        o['cf_share'] = g(pre + " Bal", 64) / 127.0
    elif pre == "Dly":
        t = (table_value(4, g("Dly Time", 111)) or 0.0) / 1000.0
        dry, wet = balance(g("Dly Bal", 37))
        o['dly'] = dict(tc=t, taps=[(t, 1.0, 'c', t)], level=wet / max(dry, DRY_FLOOR),
                        fb=feedback(g("Dly Fb", 80)), lpf=table_value(8, g("Dly HF", 127)), to_reverb=0.0)
        o['level'] *= max(dry, DRY_FLOOR)
    elif pre in ("OD", "OD1", "OD2"):
        o['od_gain'] = od_gain(g(pre + " Drive", 48), bool(g(pre + " Sel", 0)))
        o['level'] *= mk
        sw = pre + " Amp Sw" if pre + " Amp Sw" in pn else pre + " Amp Sw Off/On"
        if g(sw, 1):
            o['cabinet'] = 'guitar12'
    elif pre == "RT":
        o['rotary'] = _rotary("Rotary Multi", g, pn)
    elif pre == "PH":
        o['filter'] = dict(ty=1, pa=g("PH Mix", 64) / 127.0, pb=0.9 * g("PH Reso", 16) / 127.0,
                           pc=EF.PHASER_STAGES,
                           ctrl=('sweep', table_value(12, g("PH Man", 36)), PHASER_OCT * g("PH Depth", 64) / 127.0,
                                 table_value(6, g("PH Rate", 16)), None, 0.0))
    elif pre == "AW":
        o['filter'] = dict(ty=2 if g("AW Filter", 1) == 0 else 3, pa=EF.wah_q(g("AW Peak", 62)), pb=1.0, pc=0.0,
                           ctrl=('sweep', EF.wah_hz(g("AW Man", 68)), AUTOWAH_OCT * g("AW Depth", 72) / 127.0,
                                 table_value(6, g("AW Rate", 40)), bool(g("AW Pol", 1)),
                                 AUTOWAH_SENS_OCT * g("AW Sens", 0) / 127.0))


def pan_gains(v):
    """A branch's Pan 0-127 (64 the middle) as gains on the two ears,
    constant power, whole at the middle -- a level across the ears, not a
    new place (the copy keeps its interaural delays). Chosen."""
    th = (max(0, min(127, int(v))) - 64) / 63.0 * 0.25 * math.pi + 0.25 * math.pi
    return math.sqrt(2.0) * math.cos(th), math.sqrt(2.0) * math.sin(th)


def _keyboard_multi(g, dly, out):
    """The Keyboard Multi's ring modulator, pitch shifter and delay in series
    (RM -> EQ -> PS -> PH -> Dly), unrolled into gsdelay taps: every path
    through them -- dry or either sideband, dry or shifted, direct or each
    repeat -- one tap of (delay, level, side, period, ratio, Hz), feedback
    none (the repeats are taps). The part itself is the all-dry path, at its
    level; each tap against it. The sidebands at half each (a product of
    sines); the PS Mode (its quality) is not modelled."""
    fm = rm_hz(g("RM Mod Freq 0 - 50 - 127", 50))
    rd, rw = balance(g("RM Bal", 15))
    pd, pw = balance(g("PS Bal", 30))
    r = semitones(g("PS Coarse", 71), g("PS Fine", 64))
    rm = [(rd, 1.0, 0.0), (0.5 * rw, 1.0, fm), (0.5 * rw, 1.0, -fm)]
    ps = [(pd, 1.0), (pw, r)]
    reps = [(0.0, 1.0)]
    if dly is not None:
        t, fb = dly['tc'], dly['fb']
        for k in range(64):
            lv = dly['level'] * fb ** k
            if lv < 1e-3:
                break
            reps.append(((k + 1) * t, lv))
    base = max(rd * pd, DRY_FLOOR)
    taps = []
    for a, _, hz in rm:
        for b, ratio in ps:
            for tau, c in reps:
                if hz == 0.0 and ratio == 1.0 and tau == 0.0:
                    continue                      # the part itself
                lv = a * b * c / base
                if lv > 1e-4:
                    taps.append((tau, lv, 'c', tau, ratio, hz * ratio))
    out['level'] *= base
    return dict(tc=max(1e-3, reps[-1][0]), taps=taps, level=1.0, fb=0.0, lpf=None, to_reverb=0.0)


def mix_share(events, ch, sr):
    """share(non samples) -> the chain's chorus/flanger wet share at each row's
    onset, for part `ch`: its CF Mix then (0-127) as the system chorus's send
    is taken (a^2 / (1 + a^2)), 0 where the part is off the EFX."""
    import numpy as np
    ts = sorted({0.0} | {t for t, _ in events})
    vals = []
    for t in ts:
        c = at(events, ch, t)
        if c is not None and c.get('cf_share') is not None:
            vals.append(c['cf_share'])        # a chorus type's Balance: dry against effect
            continue
        a = c['cf'][1] if (c is not None and c['cf'] is not None) else 0.0
        vals.append(a * a / (1.0 + a * a))
    ts, vals = np.array(ts), np.array(vals)

    def share(non):
        i = np.searchsorted(ts, np.asarray(non, np.float64) / sr, side='right') - 1
        return vals[np.clip(i, 0, len(vals) - 1)]
    return share


def chain_share(c):
    """share(non samples) -> a chain's own chorus/flanger wet share, held: for
    an effect a TONE carries (tone_state), which no event in the file
    assigns -- its Balance, or its CF Mix as mix_share takes it."""
    import numpy as np
    if c.get('cf_share') is not None:
        v = float(c['cf_share'])
    else:
        a = c['cf'][1] if c['cf'] is not None else 0.0
        v = a * a / (1.0 + a * a)
    return lambda non: np.full(np.shape(non), v)


def cf_device(flanger, rate, depth, fb):
    """The chain's chorus or flanger as chorus.gs_copies's device: rate from
    the table, depth as the system chorus's swing, feedback +-98 %. The base
    delay is chosen -- a chorus 10 ms, a flanger 1 ms -- and a flanger's swing
    an eighth of a chorus's, so its comb stays in the flanging range."""
    r = rate2(rate)
    swing = efx_swing(depth, flanger)
    return dict(tau=(0.001 if flanger else 0.010) + swing, rate=r,
                vd=2.0 * math.pi * r * swing, fb=feedback(fb), level=1.0, lpf=None)


def eq_gain(f, eq):
    """The chain's EQ at frequency f (a number or an array), linear: first-
    order shelves at the chosen corners and a peaking mid (RBJ's magnitude,
    its Q and gain). It is AFTER the OD and its amp, as the chains have it
    (GTR Multi 2: Cmp, OD, EQ, CF) -- applied with the cabinet, to the valve's
    products too (blockrender's and streamrender's speaker pass)."""
    lo, mf, q, mg, hi = eq[:5]
    # ...and, where a type sets them (Stereo-EQ), its shelves' corners and
    # more mids: (lo, mid Hz, Q, mid dB, hi, lo Hz, hi Hz, (mid Hz, Q, dB)...)
    x = (f / (eq[5] if len(eq) > 5 else LOW_SHELF_HZ)) ** 2
    y = (f / (eq[6] if len(eq) > 6 else HIGH_SHELF_HZ)) ** 2
    db = lo / (1.0 + x) + hi * y / (1.0 + y)
    for mf, q, mg in ((mf, q, mg),) + (tuple(eq[7:]) if len(eq) > 7 else ()):
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
    _nc = [v for k, v in sorted(TYPES.items()) if v != "Thru" and chain(dict(type=k, p={}, send={})) is None]
    check("every type builds a chain at its defaults (Thru none: its parts play dry)",
          not _nc and chain(dict(type=(0, 0), p={}, send={})) is None, "(%s)" % ", ".join(_nc))
    # THE EFFECT CONTROLLERS (SC-8850 OM p.130-131's examples): CC16 at +100%
    # moves Overdrive's Drive (its +) from 0 one for one; Rotary's Speed (its +)
    # is Slow below 64 and Fast from it; at -100% the Drive runs the other way
    _st = fresh_state(); _st['type'] = next(k for k, v in TYPES.items() if v == "Overdrive")
    for _e in (('param', 1, 0), ('ctl', CTL_SRC1, 16), ('ctl', CTL_DEP1, 0x7F)):
        apply(_st, _e)
    _dr = []
    for _cv in (0, 64, 127):
        apply(_st, ('cv', 16, _cv)); _dr.append(in_effect(_st)[1])
    apply(_st, ('ctl', CTL_DEP1, 0x00)); apply(_st, ('param', 1, 127)); _neg = in_effect(_st)[1]
    _sr = fresh_state(); _sr['type'] = next(k for k, v in TYPES.items() if v == "Rotary")
    for _e in (('ctl', CTL_SRC1, 16), ('ctl', CTL_DEP1, 0x7F)):
        apply(_sr, _e)
    _sp = []
    for _cv in (63, 64):
        apply(_sr, ('cv', 16, _cv)); _sp.append(chain(_sr)['rotary']['fast'])
    check("the effect controllers move a type's + parameter by Roland's law",
          _dr == [0, 64, 127] and _neg == 0 and _sp == [False, True]
          and parse(message(('ctl', CTL_SRC1, 16))) == ('ctl', CTL_SRC1, 16),
          "(Drive %s; at -100%% %d; Speed %s)" % (_dr, _neg, _sp))
    # the Auto Wah's Sens: its filter opened by the part's notes -- higher
    # just after a loud note's onset than before it and than long after
    _ev = [(0.0, ('type', (0x01, 0x21))), (0.0, ('param', 2, 127)), (0.0, ('param', 6, 0)),
           (0.0, ('part', 0, True))]
    _fc = filter_setup(_ev, 0, [(1.0, 1.5, 120)])
    _v = _fc.control(np.array([0.5, 1.02, 3.0])) if _fc is not None else [0, 0, 0]
    check("the Auto Wah's Sens opens its filter with the part's notes",
          _v[1] > 4.0 * _v[0] and abs(_v[2] - _v[0]) < 1.0,
          "(%.0f Hz before, %.0f at the onset, %.0f after)" % tuple(_v))
    e = (0.0, 2000.0, 2.0, 6.0, 0.0)
    check("the mid EQ peaks at its frequency, at its gain",
          abs(20 * math.log10(eq_gain(2000.0, e)) - 6.0) < 0.3
          and 20 * math.log10(eq_gain(500.0, e)) < 1.0)
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
