"""The controller matrix: which controller moves what, per channel, as a GS
module and a GM2 one route them.

A Sound Canvas routes six SOURCES -- the mod wheel, pitch bend, channel and
polyphonic aftertouch, and two assignable controllers "CC1" and "CC2" (their
numbers a part setting, 40 1x 1F / 20, 16 and 17 by default) -- to eleven
DESTINATIONS, each with its own depth per part (40 2x, the PART'S CONTROLLER
block; SC-8850 owner's manual, parameter address map):

    pitch       -24..+24 semitones          cutoff      -9600..+9600 cents
    amp         -100..+100 %                lfo1_rate   -10..+10 Hz
    lfo1_pitch  0..600 cents                lfo1_tvf    0..2400 cents
    lfo1_tva    0..100 %                    (and lfo2_rate, _pitch, _tvf, _tva)

GM2 says the same in its CONTROLLER DESTINATION SETTING (universal realtime
F0 7F dd 09 0s ..., SC-8850 owner's manual p.231): channel pressure (09 01),
polyphonic key pressure (09 02) or any controller 1-31, 64-95 (09 03) to
pitch (pp 0, -24..+24 semitones), filter cutoff (1, -9600..+9450 cents),
amplitude (2, 0..200 %), LFO pitch depth (3, 0..600 cents), LFO filter depth
(4, 0..2400) and LFO amplitude depth (5, 0..100 %). GM2's amplitude is
200 % at the top where GS's is +100 %: the same gain, twice the level.

So both land here as one table: {channel: {(source, destination): depth}}, a
source being 'mod', 'bend', 'cat', 'pat', or ('cc', n) -- GS's CC1 and CC2
resolved to the numbers the part assigns them. Each destination's DEPTH is in
its own unit at the source's full travel (a controller at 127, the bend at
its extreme, the pressure at 127); what a destination does with it is the
renderer's (blockrender: amp, lfo1_tva).
"""

# GS 40 2x: the source of each sixteen-address row, and the destination of
# each address within it
GS_SOURCES = {0x0: 'mod', 0x1: 'bend', 0x2: 'cat', 0x3: 'pat', 0x4: 'cc1', 0x5: 'cc2'}
GS_DESTS = ('pitch', 'cutoff', 'amp', 'lfo1_rate', 'lfo1_pitch', 'lfo1_tvf', 'lfo1_tva',
            'lfo2_rate', 'lfo2_pitch', 'lfo2_tvf', 'lfo2_tva')
# GM2 09 0s pp: its six destinations, the same names
GM2_DESTS = ('pitch', 'cutoff', 'amp', 'lfo1_pitch', 'lfo1_tvf', 'lfo1_tva')
GM2_SOURCES = {0x01: 'cat', 0x02: 'pat', 0x03: 'cc'}


def gs_depth(dest, v, src=None):
    """A GS 40 2x value in its destination's unit (the address map's ranges).
    The bend's pitch is its range, 0..24 (40H-58H); every other pitch control
    is 28H-58H about 40H."""
    if dest == 'pitch':
        return float(max(-24, min(24, v - 0x40)))
    if dest == 'cutoff':
        return (v - 0x40) * 9600.0 / 64.0
    if dest == 'amp':
        return (v - 0x40) / 63.0 if v > 0x40 else (v - 0x40) / 64.0
    if dest.endswith('_rate'):
        return (v - 0x40) * 10.0 / 64.0
    if dest.endswith('_pitch'):
        return v * 600.0 / 127.0
    if dest.endswith('_tvf'):
        return v * 2400.0 / 127.0
    if dest.endswith('_tva'):
        return v / 127.0
    raise ValueError(dest)


def gm2_depth(dest, v):
    """A GM2 09 0s range byte in its destination's unit (SC-8850 p.231)."""
    if dest == 'pitch':
        return float(max(-24, min(24, v - 0x40)))
    if dest == 'cutoff':
        return -9600.0 + v * (9600.0 + 9450.0) / 127.0
    if dest == 'amp':
        return v / 64.0 - 1.0                  # 0..200 %: the gain at the top, less one
    if dest == 'lfo1_pitch':
        return v * 600.0 / 127.0
    if dest == 'lfo1_tvf':
        return v * 2400.0 / 127.0
    if dest == 'lfo1_tva':
        return v / 127.0
    raise ValueError(dest)


# A reset's table: GS's own defaults (40 2x: the mod wheel's 10 into LFO1
# pitch, the bend's +2 semitones; every other cell at its centre or zero).
# GM2 adds nothing over these: its destinations reset to none, its mod wheel
# depth and bend range are RPNs, read where they always were
DEFAULTS = {('mod', 'lfo1_pitch'): 10 * 600.0 / 127.0, ('bend', 'pitch'): 2.0}
CC1_DEFAULT, CC2_DEFAULT = 16, 17


def parse(data, ch_of_block):
    """(channel, kind, payload) for a message the matrix reads, or None:
        ('cell', (source, dest, depth))  a destination's depth
        ('assign', (which, cc))          GS CC1/CC2's controller number
    `ch_of_block` maps a GS block nibble and its address byte (40 / 50) to a
    channel, as blockrender reads every part message."""
    d = tuple(data)
    # GS: 41 dd 42 12 4b 2p aa vv (the controller block), 4b 1p 1F/20 vv
    if len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12 and d[4] in (0x40, 0x50):
        ch = ch_of_block(d[5] & 0x0F, d[4])
        if d[5] >> 4 == 2:
            row, col = d[6] >> 4, d[6] & 0x0F
            if row in GS_SOURCES and col < len(GS_DESTS):
                dest = GS_DESTS[col]
                return ch, 'cell', (GS_SOURCES[row], dest, gs_depth(dest, d[7]))
        elif d[5] >> 4 == 1 and d[6] in (0x1F, 0x20):
            return ch, 'assign', ('cc1' if d[6] == 0x1F else 'cc2', int(d[7]))
        return None
    # GM2: 7F dd 09 0s 0n [cc] pp rr [pp rr ...]
    if len(d) >= 6 and d[0] == 0x7F and d[2] == 0x09 and d[3] in GM2_SOURCES:
        ch = d[4] & 0x0F
        src = GM2_SOURCES[d[3]]
        i = 5
        if src == 'cc':
            if len(d) < 7:
                return None
            src = ('cc', int(d[5]))
            i = 6
        cells = []
        while i + 1 < len(d):
            pp, rr = d[i], d[i + 1]
            if pp < len(GM2_DESTS):
                cells.append((src, GM2_DESTS[pp], gm2_depth(GM2_DESTS[pp], rr)))
            i += 2
        return (ch, 'cells', tuple(cells)) if cells else None
    return None


class Matrix(object):
    """One channel's routing as a file sets it over time: apply() each parsed
    message in order; cells() the table in force, CC1/CC2 resolved."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.gs = dict(DEFAULTS)
        self.cc_of = {'cc1': CC1_DEFAULT, 'cc2': CC2_DEFAULT}

    def apply(self, kind, payload):
        if kind == 'cell':
            src, dest, dep = payload
            self.gs[(src, dest)] = dep
        elif kind == 'cells':
            for src, dest, dep in payload:
                self.gs[(src, dest)] = dep
        elif kind == 'assign':
            which, cc = payload
            self.cc_of[which] = cc

    def cells(self):
        """{(source, dest): depth}, CC1/CC2 as ('cc', n); zero cells left out."""
        out = {}
        for (src, dest), dep in self.gs.items():
            if src in ('cc1', 'cc2'):
                src = ('cc', self.cc_of[src])
            if dep:
                out[(src, dest)] = out.get((src, dest), 0.0) + dep
        return out


def selftest():
    import sys
    fails = []

    def check(name, ok, detail=""):
        print("  %s %s%s" % ("ok  " if ok else "FAIL", name, ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)
    blk = lambda b, a: (9 if b == 0 else (b - 1 if b <= 9 else b)) + (16 if a == 0x50 else 0)   # noqa: E731
    # GS: part 6's mod wheel into LFO1 TVA at 50 (River)
    r = parse((0x41, 0x10, 0x42, 0x12, 0x40, 0x26, 0x06, 50, 0), blk)
    check("GS 40 26 06 = 50 is part 6's mod -> LFO1 TVA, 39%",
          r == (5, 'cell', ('mod', 'lfo1_tva', 50 / 127.0)), str(r))
    # GS: CC1 amplitude at +100 % on part 8, and its controller number
    r = parse((0x41, 0x10, 0x42, 0x12, 0x40, 0x28, 0x42, 0x7F, 0), blk)
    check("GS 40 28 42 = 7F is part 8's CC1 -> amp, +100 %", r[2][:2] == ('cc1', 'amp') and abs(r[2][2] - 1.0) < 1e-9)
    m = Matrix()
    m.apply(*r[1:])
    check("...resolved to CC16 by default", (('cc', 16), 'amp') in m.cells(), str(m.cells()))
    m.apply('assign', ('cc1', 20))
    check("...and to the part's assigned number", (('cc', 20), 'amp') in m.cells())
    check("a reset's table: the mod wheel's 47 cents of vibrato, the bend's 2 semitones",
          abs(Matrix().cells()[('mod', 'lfo1_pitch')] - 47.24) < 0.01 and Matrix().cells()[('bend', 'pitch')] == 2.0)
    # GM2: channel 3's channel pressure into amplitude at 200 % and LFO amp depth
    r = parse((0x7F, 0x7F, 0x09, 0x01, 0x02, 0x02, 0x7F, 0x05, 0x40), blk)
    check("GM2 09 01: channel pressure -> amp (top 200 %) and LFO amplitude depth (50 %)",
          r[0] == 2 and r[2][0][:2] == ('cat', 'amp') and abs(r[2][0][2] - 0.984) < 0.01
          and r[2][1][:2] == ('cat', 'lfo1_tva') and abs(r[2][1][2] - 0.504) < 0.01, str(r))
    r = parse((0x7F, 0x7F, 0x09, 0x03, 0x00, 0x10, 0x00, 0x4C), blk)
    check("GM2 09 03: CC16 -> pitch +12 semitones", r == (0, 'cells', ((('cc', 16), 'pitch', 12.0),)), str(r))
    check("not a matrix message: None", parse((0x41, 0x10, 0x42, 0x12, 0x40, 0x16, 0x19, 0x40), blk) is None)
    print("\n  %s" % ("all passed" if not fails else "FAILED: %s" % ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
