#!/usr/bin/env python3
"""MIDI 2.0: the Universal MIDI Packet, the MIDI 1.0 <-> 2.0 translation, and
the two file forms.

    python3 ump.py --selftest

THE SOURCE is the MIDI Association / AMEI core specifications (the 2025-12-18
bundle), read for this and not kept in the repo:

  M2-104-UM v1.1.2  UMP Format & MIDI 2.0 Protocol -- the packet layouts
                    (Appendix F), per-note pitch (7.4.12-7.4.15), the
                    translation rules (Appendix D)
  M2-116-U  v1.0    MIDI Clip File -- "SMF2CLIP", Delta Clockstamps, Start and
                    End of Clip

WHAT THIS MODULE IS FOR. Both renderers were written against MIDI 1.0 through
mido, and neither changes shape for MIDI 2.0: a MIDI 2.0 event is DECODED here
into the same message shape they already read (`Ev`, which answers to mido's
field names), with its full resolution kept as a float in MIDI 1 units --
velocity and controllers 0..127, pitch bend -8192..8191. What MIDI 2.0 adds and
MIDI 1.0 has no message for (per-note pitch, per-note bend, per-note
management) arrives as new `Ev` types.

THE EXACTNESS RULE, which is what lets MIDI 1.0 pass through all of this and
come out bit-identical. The spec's translation "shall yield the same output as
the input data when translating MIDI 1.0 -> MIDI 2.0 -> MIDI 1.0" (D.1.2), and
its min-center-max upscale is a pure function of the 7-bit value. So a 32-bit
value that IS the upscale of some 7-bit value decodes to that integer, exactly,
and anything else decodes through the inverse of the same curve. A keyboard
bridged to MIDI 2.0 therefore reaches the engine as the very numbers it sent.
"""
import math
import struct

# ------------------------------------------------------------ scaling (D.1)

def scale_up(v, src, dst):
    """Min-center-max upscale, the spec's own algorithm (D.1.3): a plain shift
    up to the centre, the value's low bits repeated to fill beyond it."""
    shift = dst - src
    out = v << shift
    if v <= 1 << (src - 1):
        return out
    rb = src - 1
    rv = v & ((1 << rb) - 1)
    rv = rv << (shift - rb) if shift > rb else rv >> (rb - shift)
    while rv:
        out |= rv
        rv >>= rb
    return out


def scale_down(v, src, dst):
    """Downscale: cut off the low bits (D.1.4)."""
    return v >> (src - dst)


def to_m1(x, src, dst=7):
    """A `src`-bit MIDI 2.0 value in `dst`-bit MIDI 1 units.

    An exact upscale of a `dst`-bit value comes back as that INTEGER; anything
    else is a float on the inverse min-center-max curve, which is linear below
    the centre (a shift) and linear from centre to maximum above it.
    """
    v = x >> (src - dst)
    if scale_up(v, dst, src) == x:
        return v
    cs, cd = 1 << (src - 1), 1 << (dst - 1)
    if x <= cs:
        return x / float(1 << (src - dst))
    return cd + (x - cs) * (cd - 1) / float((1 << src) - 1 - cs)


def bend_to_m1(x):
    """A 32-bit pitch bend in mido's units, -8192..8191."""
    v = to_m1(x, 32, 14)
    return v - 8192


def pitch_q(x, frac_bits):
    """A Pitch 7.9 / 7.25 value in semitones (MIDI note units, A440 12-TET)."""
    return x / float(1 << frac_bits)


def semitones_to_q(p, frac_bits):
    return max(0, min((128 << frac_bits) - 1, int(round(p * (1 << frac_bits)))))


# ------------------------------------------------------------ packets (App. F)

WORDS = {0: 1, 1: 1, 2: 1, 3: 2, 4: 2, 5: 4, 6: 1, 7: 1, 8: 2, 9: 2, 0xA: 2,
         0xB: 3, 0xC: 3, 0xD: 4, 0xE: 4, 0xF: 4}


def split(words):
    """A flat word stream into packets, by each one's message type."""
    out, i = [], 0
    while i < len(words):
        n = WORDS[(words[i] >> 28) & 0xF]
        out.append(tuple(words[i:i + n]))
        i += n
    return out


def m2(status, group, ch, b3, b4, data):
    return ((0x4 << 28) | (group << 24) | (status << 20) | (ch << 16)
            | (b3 << 8) | b4, data & 0xFFFFFFFF)


def m2_note_on(g, ch, note, vel16, attr_type=0, attr=0):
    return m2(0x9, g, ch, note, attr_type, (vel16 << 16) | attr)


def m2_note_off(g, ch, note, vel16, attr_type=0, attr=0):
    return m2(0x8, g, ch, note, attr_type, (vel16 << 16) | attr)


def m2_cc(g, ch, index, data):
    return m2(0xB, g, ch, index, 0, data)


def m2_program(g, ch, program, bank=None):
    if bank is None:
        return m2(0xC, g, ch, 0, 0, program << 24)
    return m2(0xC, g, ch, 0, 1, (program << 24) | (bank[0] << 8) | bank[1])


def m2_rpn(g, ch, bank, index, data, assignable=False):
    return m2(0x3 if assignable else 0x2, g, ch, bank, index, data)


def m2_pitch_bend(g, ch, data):
    return m2(0xE, g, ch, 0, 0, data)


def m2_per_note_bend(g, ch, note, data):
    return m2(0x6, g, ch, note, 0, data)


def m2_per_note_ctrl(g, ch, note, index, data, assignable=False):
    return m2(0x1 if assignable else 0x0, g, ch, note, index, data)


def m2_per_note_mgmt(g, ch, note, detach=False, reset=False):
    return m2(0xF, g, ch, note, (2 if detach else 0) | (1 if reset else 0), 0)


def m2_poly(g, ch, note, data):
    return m2(0xA, g, ch, note, 0, data)


def m2_chan_pressure(g, ch, data):
    return m2(0xD, g, ch, 0, 0, data)


def sysex7(g, data):
    """SysEx without its F0/F7 into 64-bit MT 3 packets, six bytes each."""
    data = list(data)
    chunks = [data[i:i + 6] for i in range(0, len(data), 6)] or [[]]
    out = []
    for i, c in enumerate(chunks):
        st = 0 if len(chunks) == 1 else (1 if i == 0 else (3 if i == len(chunks) - 1 else 2))
        b = c + [0] * (6 - len(c))
        out.append(((0x3 << 28) | (g << 24) | (st << 20) | (len(c) << 16) | (b[0] << 8) | b[1],
                    (b[2] << 24) | (b[3] << 16) | (b[4] << 8) | b[5]))
    return out


def utility(status, data):
    return ((status << 20) | (data & 0xFFFFF),)


def dctpq(tpq):
    return utility(0x3, tpq)


def delta_clockstamp(ticks):
    return utility(0x4, ticks)


def stream(status, form=0):
    return ((0xF << 28) | (form << 26) | (status << 16), 0, 0, 0)


START_OF_CLIP, END_OF_CLIP = 0x20, 0x21


def set_tempo(g, us_per_quarter):
    """Flex Data Set Tempo: 10-nanosecond units per quarter note (7.5.3)."""
    return ((0xD << 28) | (g << 24) | (1 << 20), int(round(us_per_quarter * 100)), 0, 0)


# ------------------------------------------------------------ decoding

class Ev(object):
    """A decoded event, answering to mido's field names so both renderers read
    it as they read a mido message. `channel` is flat: group * 16 + channel."""
    __slots__ = ("type", "channel", "note", "velocity", "value", "control",
                 "pitch", "program", "data", "attr_pitch", "semitones",
                 "detach", "reset", "group", "time")

    def __init__(self, type, **kw):
        self.type = type
        for k in self.__slots__[1:]:
            setattr(self, k, kw.get(k))

    def __repr__(self):
        return "Ev(%s)" % ", ".join("%s=%r" % (k, getattr(self, k)) for k in self.__slots__
                                    if getattr(self, k) is not None)


# The MIDI 2.0 Protocol replaces these compound sequences with unified messages,
# and "Devices receiving the MIDI 2.0 Protocol should ignore Control Change
# messages with indexes of 0, 6, 32, 38, 98, 99, 100, and 101" (7.4.6). 96/97
# "have no RPN/NRPN related function in the MIDI 2.0 Protocol" (D.3.3), and 88
# is the MIDI 1.0 high-resolution velocity prefix, which "shall not be used".
M2_IGNORED_CC = frozenset((0, 6, 32, 38, 88, 96, 97, 98, 99, 100, 101))
# Controllers the engine reads as an INTEGER -- a table index, a bitmask, a note
# number -- so a MIDI 2.0 value is taken at its top seven bits, which is also
# what the spec says of CC84 and CC126 (7.4.6.1).
M2_INT_CC = frozenset((5, 10, 43, 44, 84, 126))
RPN_PER_NOTE_BEND_RANGE = (0, 7)
RPNC_PITCH = 3


def decode(pkt, sysex_buf=None):
    """One UMP packet -> a list of Ev, in MIDI 1 units (see to_m1).

    MIDI 2.0's unified messages are unrolled into the MIDI 1.0 sequence the
    engine already handles -- an RPN into 101/100/6/38, a program with a bank
    into 0/32/program -- carrying the same values the MIDI 1.0 bytes would, so
    one handler serves both. Returns [] for what the engine has no use for.
    `sysex_buf` is a dict the caller keeps, to reassemble multi-packet SysEx.
    """
    w0 = pkt[0]
    mt = (w0 >> 28) & 0xF
    g = (w0 >> 24) & 0xF
    st = (w0 >> 20) & 0xF
    ch = g * 16 + ((w0 >> 16) & 0xF)
    b3 = (w0 >> 8) & 0x7F
    b4 = w0 & 0xFF
    if mt == 0x2:
        return _decode_m1(g, (w0 >> 16) & 0xFF, b3, w0 & 0x7F)
    if mt == 0x3:
        n = (w0 >> 16) & 0xF
        raw = [(w0 >> 8) & 0xFF, w0 & 0xFF] + [(pkt[1] >> s) & 0xFF for s in (24, 16, 8, 0)]
        buf = sysex_buf if sysex_buf is not None else {}
        if st in (0, 1):
            buf[g] = []
        buf.setdefault(g, []).extend(raw[:n])
        if st in (0, 3):
            data = tuple(buf.pop(g, []))
            return [Ev("sysex", data=data, group=g)]
        return []
    if mt == 0xD and ((w0 >> 8) & 0xFF, w0 & 0xFF) == (0, 0):
        return [Ev("set_tempo", value=pkt[1] / 100.0)]
    if mt != 0x4:
        return []
    d = pkt[1]
    E = lambda t, **k: Ev(t, channel=ch, group=g, **k)
    if st == 0x9:
        vel = to_m1(d >> 16, 16)
        # "a velocity value of zero does not function as a Note Off" (7.4.2);
        # the translation to MIDI 1.0 replaces a zero with 1, and so does this.
        vel = vel if vel >= 1 else 1
        ap = pitch_q(d & 0xFFFF, 9) if b4 == 3 else None
        return [E("note_on", note=b3, velocity=vel, attr_pitch=ap)]
    if st == 0x8:
        return [E("note_off", note=b3, velocity=to_m1(d >> 16, 16))]
    if st == 0xA:
        return [E("polytouch", note=b3, value=to_m1(d, 32))]
    if st == 0xD:
        return [E("aftertouch", value=to_m1(d, 32))]
    if st == 0xE:
        return [E("pitchwheel", pitch=bend_to_m1(d))]
    if st == 0xB:
        if b3 in M2_IGNORED_CC:
            return [E("ignored", control=b3)]
        v = (d >> 25) if b3 in M2_INT_CC else to_m1(d, 32)
        return [E("control_change", control=b3, value=v)]
    if st == 0xC:
        out = []
        if b4 & 1:
            out += [E("control_change", control=0, value=(d >> 8) & 0x7F),
                    E("control_change", control=32, value=d & 0x7F)]
        return out + [E("program_change", program=(d >> 24) & 0x7F)]
    if st in (0x2, 0x3):
        if st == 0x2 and (b3, b4 & 0x7F) == RPN_PER_NOTE_BEND_RANGE:
            return [E("pn_bend_range", semitones=pitch_q(d, 25))]
        v14 = d >> 18
        sel = (101, 100) if st == 0x2 else (99, 98)
        return [E("control_change", control=sel[0], value=b3),
                E("control_change", control=sel[1], value=b4 & 0x7F),
                E("control_change", control=6, value=v14 >> 7),
                E("control_change", control=38, value=v14 & 0x7F)]
    if st == 0x6:
        return [E("pn_bend", note=b3, value=(d - 0x80000000) / float(0x80000000))]
    if st == 0x0 and b4 == RPNC_PITCH:
        return [E("pn_pitch", note=b3, semitones=pitch_q(d, 25))]
    if st == 0xF:
        return [E("pn_mgmt", note=b3, detach=bool(b4 & 2), reset=bool(b4 & 1))]
    return [E("ignored", control=None)]


def _decode_m1(g, status, d1, d2):
    """MT 2: MIDI 1.0 channel voice carried in UMP. Plain MIDI 1.0 values."""
    kind, ch = status & 0xF0, g * 16 + (status & 0xF)
    E = lambda t, **k: Ev(t, channel=ch, group=g, **k)
    if kind == 0x90:
        return [E("note_on" if d2 else "note_off", note=d1, velocity=d2)]
    if kind == 0x80:
        return [E("note_off", note=d1, velocity=d2)]
    if kind == 0xA0:
        return [E("polytouch", note=d1, value=d2)]
    if kind == 0xB0:
        return [E("control_change", control=d1, value=d2)]
    if kind == 0xC0:
        return [E("program_change", program=d1)]
    if kind == 0xD0:
        return [E("aftertouch", value=d1)]
    if kind == 0xE0:
        return [E("pitchwheel", pitch=(d1 | (d2 << 7)) - 8192)]
    return []


# ------------------------------------------------------------ MIDI 1 -> 2 (D.3)

class Midi1to2(object):
    """MIDI 1.0 messages (mido) in, MIDI 2.0 Protocol UMP packets out.

    The Default Translation of Appendix D.3, rule for rule. The one thing the
    spec leaves to the translator is WHEN a held data entry goes out: it names
    three triggers (a CC38, a later CC6, a new RPN/NRPN selection) and allows
    a timeout. This one also sends it before ANY other message -- so an RPN is
    always in force before the note that follows it, exactly as it was in the
    MIDI 1.0 stream, and a file converted offline and a keyboard bridged live
    come out alike. `flush()` is the timeout.
    """

    def __init__(self, group=0, pitch_of=None):
        self.group = group
        # pitch_of(channel, note) -> semitones or None: when given, every Note
        # On carries it as a Pitch 7.9 attribute -- a MIDI 1.0 keyboard playing
        # in an intonation of its own (see pitch_table).
        self.pitch_of = pitch_of
        self.bank = {}          # ch -> [msb, lsb], once a CC0 or CC32 arrives
        self.sel = {}           # ch -> ('rpn'|'nrpn', msb, lsb)
        self.sel_part = {}      # ch -> {cc: value} for 98-101 as they arrive
        self.d6 = {}            # ch -> latest CC6 value (held, D.3.3)
        self.pending = {}       # ch -> CC6 not yet sent

    def _send_param(self, ch, lsb):
        s = self.sel.get(ch)
        msb = self.d6.get(ch)
        self.pending.pop(ch, None)
        if s is None or msb is None or (s[1], s[2]) == (127, 127):
            return []
        v = scale_up((msb << 7) | lsb, 14, 32)
        return [m2_rpn(self.group, ch, s[1], s[2], v, assignable=(s[0] == 'nrpn'))]

    def flush(self, ch=None):
        """Send any held data entry -- the spec's timeout."""
        out = []
        for c in ([ch] if ch is not None else list(self.pending)):
            if c in self.pending:
                out += self._send_param(c, 0)
        return out

    def feed(self, msg):
        g, t = self.group, msg.type
        ch = getattr(msg, "channel", None)
        out = []
        if t == "control_change" and msg.control == 38 and ch in self.pending:
            return self._send_param(ch, msg.value)
        if t == "control_change" and msg.control in (6, 38, 98, 99, 100, 101):
            if msg.control == 6:
                out += self.flush(ch)
                self.d6[ch] = msg.value
                self.pending[ch] = True
                return out
            if msg.control == 38:
                # A CC38 with no CC6 held: the latest CC6 is still the MSB.
                return self._send_param(ch, msg.value) if ch in self.d6 else []
            out += self.flush(ch)
            part = self.sel_part.setdefault(ch, {})
            part[msg.control] = msg.value
            if msg.control in (101, 100):
                part.pop(99, None); part.pop(98, None)
                self.sel[ch] = ('rpn', part.get(101, 0), part.get(100, 0))
            else:
                part.pop(101, None); part.pop(100, None)
                self.sel[ch] = ('nrpn', part.get(99, 0), part.get(98, 0))
            # A new selection: a data entry must follow it.
            self.d6.pop(ch, None)
            return out
        # Anything else sends a held data entry first, on every channel: the
        # order across channels is part of the stream too.
        out += self.flush()
        if t == "note_on":
            if msg.velocity == 0:
                return out + [m2_note_off(g, ch, msg.note, 0x8000)]
            p = self.pitch_of(ch, msg.note) if self.pitch_of else None
            if p is not None:
                return out + [m2_note_on(g, ch, msg.note, scale_up(msg.velocity, 7, 16),
                                         3, semitones_to_q(p, 9))]
            return out + [m2_note_on(g, ch, msg.note, scale_up(msg.velocity, 7, 16))]
        if t == "note_off":
            return out + [m2_note_off(g, ch, msg.note, scale_up(msg.velocity, 7, 16))]
        if t == "polytouch":
            return out + [m2_poly(g, ch, msg.note, scale_up(msg.value, 7, 32))]
        if t == "aftertouch":
            return out + [m2_chan_pressure(g, ch, scale_up(msg.value, 7, 32))]
        if t == "pitchwheel":
            return out + [m2_pitch_bend(g, ch, scale_up(msg.pitch + 8192, 14, 32))]
        if t == "control_change":
            if msg.control in (0, 32):
                b = self.bank.setdefault(ch, [0, 0])
                b[0 if msg.control == 0 else 1] = msg.value
                return out
            return out + [m2_cc(g, ch, msg.control, scale_up(msg.value, 7, 32))]
        if t == "program_change":
            bank = tuple(self.bank[ch]) if ch in self.bank else None
            return out + [m2_program(g, ch, msg.program, bank)]
        if t == "sysex":
            return out + sysex7(g, msg.data)
        return out


# ------------------------------------------------------------ pitch tables

# FIVE-LIMIT JUST INTONATION on a tonic: the ratios every theory text gives for
# the major/minor chromatic set (the tritone as 45/32, the minor seventh as 9/5).
JUST_5 = (1.0, 16 / 15, 9 / 8, 6 / 5, 5 / 4, 4 / 3, 45 / 32, 3 / 2, 8 / 5, 5 / 3, 9 / 5, 15 / 8)
NOTE_NAMES = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5,
              "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}


def pitch_table(spec):
    """'just:C' -> a pitch_of(channel, note) for Midi1to2. The tonic keeps its
    12-TET pitch; every other key is its just ratio above the tonic below it.
    'et' gives every note its own 12-TET pitch -- the path, with nothing moved."""
    spec = spec.strip()
    if spec.lower() == "et":
        return lambda ch, note: float(note)
    kind, _, tonic = spec.partition(":")
    if kind.lower() != "just" or tonic.upper() not in NOTE_NAMES:
        raise ValueError("pitch table: 'just:<tonic>' (e.g. just:C, just:Eb) or 'et'")
    t = NOTE_NAMES[tonic.upper()]

    def pitch_of(ch, note):
        k = (note - t) % 12
        return float(note - k) + 12.0 * math.log2(JUST_5[k])
    return pitch_of


# ------------------------------------------------------------ files

CLIP_MAGIC = b"SMF2CLIP"


# A FILE IS A LIST OF SLOTS: (delta ticks, delta seconds, [packets]). One slot
# is one Delta Clockstamp and what follows it. Converting a MIDI 1.0 file gives
# every MIDI 1.0 message a slot of its own -- a NOOP stands in for a message
# that produced no packet (a meta event, a held CC6) -- so a reader adding up
# seconds adds up exactly the terms mido does, and the renderer sees the same
# note times to the last bit. Seconds are mido's formula: ticks * (tempo * 1e-6
# / tpq), and 0 for a zero delta.

NOOP = (0,)


def tick_seconds(dt, tempo_us, tpq):
    return dt * (tempo_us * 1e-6 / tpq) if dt > 0 else 0


def slots_from_events(events):
    """[(absolute tick, packet)] in presentation order -> slots (seconds None)."""
    out, last = [], None
    for tick, pkt in events:
        if last is not None and tick == last:
            out[-1][2].append(pkt)
        else:
            out.append((tick - (last or 0), None, [pkt]))
            last = tick
    return out


def write_clip(path, slots, tpq=960, us_per_quarter=500000):
    """A MIDI Clip File (M2-116): header, configuration (DCTPQ, tempo), Start
    of Clip, the slots, End of Clip. A Delta Clockstamp precedes every UMP; a
    gap past 20 bits is bridged with a NOOP, as 3.2.2 says. `slots` may also be
    [(absolute tick, packet)], as a sequencer would hand it over."""
    if slots and len(slots[0]) == 2:
        slots = slots_from_events(slots)
    words = []

    def at(dt):
        while dt > 0xFFFFF:
            words.extend(delta_clockstamp(0xFFFFF)); words.extend(NOOP)
            dt -= 0xFFFFF
        words.extend(delta_clockstamp(dt))

    at(0); words.extend(dctpq(tpq))
    at(0); words.extend(set_tempo(0, us_per_quarter))
    at(0); words.extend(stream(START_OF_CLIP))
    for dt, _ds, pkts in slots:
        at(dt)
        for pkt in (pkts or [NOOP]):
            words.extend(pkt)
    at(0); words.extend(stream(END_OF_CLIP))
    with open(path, "wb") as f:
        f.write(CLIP_MAGIC + struct.pack(">%dI" % len(words), *words))


RAW_MAGIC = b"UMPRAW02"


def write_raw(path, slots, tpq=960):
    """A raw UMP stream: the tick rate (u32), then each slot as (delta seconds,
    float64; delta ticks, u32; packet count, u16) and its packets. Not a
    standard -- a capture form for tests and tools, which keeps both clocks,
    and the tick grid they were counted on, so nothing is re-derived."""
    with open(path, "wb") as f:
        f.write(RAW_MAGIC + struct.pack(">I", tpq))
        for dt, ds, pkts in slots:
            pkts = pkts or [NOOP]
            f.write(struct.pack(">dIH", ds or 0.0, dt or 0, len(pkts)))
            for pkt in pkts:
                f.write(struct.pack(">B%dI" % len(pkt), len(pkt), *pkt))


def is_ump_file(data):
    return data[:8] in (CLIP_MAGIC, RAW_MAGIC)


def read(data):
    """Either form -> (slots, facts). Slots are (delta ticks, delta seconds,
    [packets]) in order; facts {'clip', 'tpq'}. A Clip File's seconds follow
    its Set Tempo messages, which stay in their slots as packets."""
    if data[:8] == RAW_MAGIC:
        tpq = struct.unpack_from(">I", data, 8)[0]
        out, i = [], 12
        while i < len(data):
            ds, dt, n = struct.unpack_from(">dIH", data, i); i += 14
            pkts = []
            for _ in range(n):
                k = data[i]; i += 1
                pkts.append(tuple(struct.unpack_from(">%dI" % k, data, i))); i += 4 * k
            out.append((dt, ds, [p for p in pkts if p != NOOP]))
        return out, {"clip": False, "tpq": tpq}
    if data[:8] != CLIP_MAGIC:
        raise ValueError("not a MIDI Clip File or raw UMP stream")
    n = (len(data) - 8) // 4
    words = struct.unpack(">%dI" % n, data[8:8 + 4 * n])
    tpq, tempo, started = 960, 500000.0, False
    out, cur = [], None
    for pkt in split(list(words)):
        w0 = pkt[0]
        mt = (w0 >> 28) & 0xF
        if mt == 0x0:
            st = (w0 >> 20) & 0xF
            if st == 0x3:
                tpq = (w0 & 0xFFFF) or tpq
            elif st == 0x4 and started:
                dt = w0 & 0xFFFFF
                cur = (dt, tick_seconds(dt, tempo, tpq), [])
                out.append(cur)
            continue
        if mt == 0xF:
            s = (w0 >> 16) & 0x3FF
            if s == START_OF_CLIP:
                started = True
            elif s == END_OF_CLIP:
                break
            continue
        if mt == 0xD and ((w0 >> 8) & 0xFF, w0 & 0xFF) == (0, 0):
            tempo = pkt[1] / 100.0          # 10 ns units -> microseconds
        if started and cur is not None:
            cur[2].append(tuple(pkt))
    # A slot made only of a gap-bridging NOOP carries time and nothing else.
    return out, {"clip": True, "tpq": tpq}


def timeline(slots):
    """Slots -> [(absolute seconds, packet)] for a player."""
    t, out = 0.0, []
    for _dt, ds, pkts in slots:
        t += ds
        out.extend((t, p) for p in pkts)
    return out


class UmpMidi(object):
    """A MIDI 2.0 file, shaped as the renderer reads a mido.MidiFile.

    Iterating gives decoded events (Ev) with .time the delta in seconds, as
    mido's iteration does; .tracks is one track with .time in ticks, for the
    renderer's legato pass; .ticks_per_beat is the clip's DCTPQ."""

    def __init__(self, data):
        self.slots, facts = read(data)
        self.ticks_per_beat = facts["tpq"]

    @classmethod
    def open(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    def _events(self, clock):
        buf = {}
        for dt, ds, pkts in self.slots:
            evs = []
            for p in pkts:
                evs.extend(decode(p, buf))
            first = ds if clock == "s" else dt
            if not evs:
                evs = [Ev("noop")]
            for k, e in enumerate(evs):
                e.time = first if k == 0 else 0
                yield e

    def __iter__(self):
        return self._events("s")

    @property
    def tracks(self):
        return [list(self._events("t"))]


def midi1_to_slots(mid):
    """A mido MidiFile -> slots, through Midi1to2: one slot per MIDI 1.0
    message, merged in presentation order as mido iterates it. A held data
    entry is sent in the slot of the message that holds it unless the next
    message shares its tick, when the translator sends it there -- either
    way at the tick MIDI 1.0 had it."""
    import mido
    tr = Midi1to2()
    tpq = mid.ticks_per_beat
    msgs = list(mido.merge_tracks(mid.tracks))
    slots, tempo = [], 500000
    for i, m in enumerate(msgs):
        ds = tick_seconds(m.time, tempo, tpq)
        if m.is_meta:
            pkts = [set_tempo(0, m.tempo)] if m.type == "set_tempo" else []
            if m.type == "set_tempo":
                tempo = m.tempo
        else:
            pkts = tr.feed(m)
        nxt = msgs[i + 1] if i + 1 < len(msgs) else None
        if tr.pending and (nxt is None or nxt.time > 0):
            pkts = pkts + tr.flush()
        slots.append((m.time, ds, pkts))
    return slots, tpq


def midi1_to_clip(mid, path, raw=False):
    """A mido MidiFile -> a Clip File, or a raw UMP stream, through Midi1to2."""
    slots, tpq = midi1_to_slots(mid)
    if raw:
        write_raw(path, slots, tpq=tpq)
    else:
        write_clip(path, slots, tpq=tpq)
    return slots


# ------------------------------------------------------------ selftest

def selftest():
    fails = []

    def check(name, ok, detail=""):
        print("  %-66s %s%s" % (name, "ok" if ok else "FAIL", ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    ex = [(10, 0x1400), (64, 0x8000), (87, 0xAEBA), (127, 0xFFFF), (1, 0x0200)]
    check("min-center-max matches the spec's own examples (D.1.3, D.3.1)",
          all(scale_up(v, 7, 16) == w for v, w in ex) and all(scale_down(w, 16, 7) == v for v, w in ex),
          "  (%s)" % ", ".join("%d->%#06x" % (v, scale_up(v, 7, 16)) for v, _ in ex))
    rt7 = all(scale_down(scale_up(v, 7, b), b, 7) == v and to_m1(scale_up(v, 7, b), b) == v
              for v in range(128) for b in (16, 32))
    rt14 = all(bend_to_m1(scale_up(v, 14, 32)) == v - 8192 for v in range(16384))
    check("MIDI 1 -> 2 -> 1 is exact for every 7-bit and 14-bit value",
          rt7 and rt14 and isinstance(to_m1(scale_up(100, 7, 32), 32), int))
    mono = [to_m1(x, 32) for x in range(0, 1 << 32, 1 << 22)] + [to_m1(0xFFFFFFFF, 32)]
    check("a true 32-bit value keeps its resolution, monotonically, 0..127",
          all(b >= a for a, b in zip(mono, mono[1:])) and mono[0] == 0 and mono[-1] == 127
          and not float(to_m1(0x80400000, 32)).is_integer())
    tr = Midi1to2()
    import mido
    M = mido.Message
    seq = [M("control_change", channel=1, control=101, value=0),
           M("control_change", channel=1, control=100, value=0),
           M("control_change", channel=1, control=6, value=12),
           M("note_on", channel=1, note=60, velocity=100)]
    pk = [p for m in seq for p in tr.feed(m)]
    evs = [e for p in pk for e in decode(p)]
    check("a lone CC6 goes out as one RPN, before the note that follows it",
          len(pk) == 2 and (pk[0][0] >> 20) & 0xF == 0x2
          and [e.control for e in evs[:4]] == [101, 100, 6, 38] and evs[2].value == 12
          and evs[3].value == 0 and evs[4].type == "note_on" and evs[4].velocity == 100)
    pk = tr.feed(M("control_change", channel=1, control=0, value=121)) + \
        tr.feed(M("control_change", channel=1, control=32, value=2)) + \
        tr.feed(M("program_change", channel=1, program=5))
    evs = [e for p in pk for e in decode(p)]
    check("bank select rides on the program change (D.3.4)",
          len(pk) == 1 and [(e.type, e.control, e.value, e.program) for e in evs] ==
          [("control_change", 0, 121, None), ("control_change", 32, 2, None),
           ("program_change", None, None, 5)])
    e = decode(tr.feed(M("note_on", channel=0, note=60, velocity=0))[0])[0]
    check("a MIDI 1.0 velocity-0 Note On becomes a Note Off at 0x8000 (D.3.1)",
          e.type == "note_off" and e.velocity == 64)
    e = decode(m2_note_on(0, 0, 60, 0x0100, 3, semitones_to_q(60.5, 9)))[0]
    check("a MIDI 2.0 velocity of 0 is still a Note On, and Pitch 7.9 decodes",
          e.type == "note_on" and e.velocity >= 1 and abs(e.attr_pitch - 60.5) < 1e-9)
    sx = (0x7E, 0x7F, 0x09, 0x01)
    buf = {}
    got = [x for p in sysex7(0, sx + sx + sx) for x in decode(p, buf)]
    check("SysEx travels as 7-bit UMPs and reassembles",
          len(got) == 1 and got[0].data == sx * 3)
    import os, tempfile
    fd, p = tempfile.mkstemp(suffix=".midi2"); os.close(fd)
    write_clip(p, [(0, m2_note_on(0, 0, 60, 0xFFFF)), (480, m2_note_off(0, 0, 60, 0)),
                   (480 + 0x100000, m2_note_on(0, 0, 62, 0x8000))], tpq=480, us_per_quarter=600000)
    slots, facts = read(open(p, "rb").read())
    os.unlink(p)
    tl = timeline(slots)
    ticks = [sum(s[0] for s in slots[:i + 1]) for i, s in enumerate(slots) if s[2]]
    check("a Clip File round-trips, a 20-bit clockstamp gap included",
          facts["tpq"] == 480 and [round(t, 6) for t, _ in tl] ==
          [0.0, 0.6, round((480 + 0x100000) * 0.6 / 480, 6)]
          and ticks == [0, 480, 480 + 0x100000])
    print("  all passed" if not fails else "  FAILED: " + ", ".join(fails))
    return not fails


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    print(__doc__)
