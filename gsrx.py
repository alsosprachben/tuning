"""THE PARTS' RECEIVE SETTINGS (GS) -- what a part takes of the channel
messages arriving, shared by live.Live and blockrender.parse so the two read
a sequencer's file the same way.

    40 1p 02      RX. CHANNEL: the MIDI channel part p plays (1-16 of its own
                  port, or OFF) -- two parts on one channel layer, a part on
                  none is silent ("Same as the Part Number" at a reset)
    40 1p 03-12   the Rx switches: pitch bend, channel pressure, program
                  change, control change (all of them), poly pressure, note
                  messages, RPN, NRPN, then CC1, 7, 10, 11, 64, 65, 66, 67
    40 1p 14      ASSIGN MODE (kept: a repeated note's retrigger)
    40 1p 1F/20   the CC1/CC2 CONTROLLER NUMBERS (kept: the matrix's sources)
    40 00 06      MASTER PAN: an offset on every part's pan (CC10), 64 none

(the SC-8850 and SC-88 Pro owner's manuals' parameter tables, the VE-GS
Pro MIDI implementation's -- "Rx. CHANNEL 1-16, OFF, Same as the Part
Number"; the SC-88 Pro's two ports: 40 is group A's parts and 50 group B's, as
blockrender.PortedMidi presents them -- a part receives its own port's
channels.) A GS reset or GM System On puts every setting back (reset).
"""
import mido

# each Rx switch's address (40 1p aa): a message type, or a controller
RX_TYPE = {"pitchwheel": 0x03, "aftertouch": 0x04, "program_change": 0x05, "polytouch": 0x07,
           "note_on": 0x08, "note_off": 0x08}
RX_CC = {1: 0x0B, 7: 0x0C, 10: 0x0D, 11: 0x0E, 64: 0x0F, 65: 0x10, 66: 0x11, 67: 0x12}


def part_of_block(blk):
    """A GS part block (40 1x's x) as the part's channel: block 0 is part 10,
    1-9 parts 1-9, A-F parts 11-16."""
    return 9 if blk == 0 else (blk - 1 if blk <= 9 else blk)


class Receive(object):
    """Every part's receive settings, by its channel: nparts 16 (live's one
    port) or 32 (a file's two: channel + 16 x port)."""

    def __init__(self, nparts=16, on_part=None):
        self.nparts = nparts
        # a message put on part p (0-31): a two-port file's own wrapper for
        # port B's (blockrender._PortMsg); mido's copy for one port
        self.on_part = on_part or (lambda m, p, **kw: m.copy(channel=p, **kw))
        self.reset()

    def reset(self):
        self.rx = list(range(16)) + list(range(16))     # each part's channel, 16 OFF
        self.rxsw = {}                  # part -> the Rx switches turned off
        self.sel = {}                   # part -> 'rpn' | 'nrpn', the last selected
        self.mpan = 64
        self.pan_raw = {}               # part -> its CC10 as sent (master pan offsets it)
        self.assign = {}
        self.ccnum = {}

    def plain(self):
        """True while nothing is set: every message passes as it is."""
        return (self.mpan == 64 and not self.rxsw
                and all(self.rx[p] == p % 16 for p in range(32)))

    def route(self, msg):
        """A CHANNEL MESSAGE AS THE PARTS RECEIVE IT: to each part of its port
        whose RX. CHANNEL is its channel, as that part's; dropped where that
        part's Rx switch for it is off (an RPN's or NRPN's data entry by the
        last parameter selected); a CC10 offset by master pan."""
        ch = msg.channel
        if ch >= self.nparts:
            return [msg]
        g, c = ch // 16, ch % 16
        if self.rx[ch] == c and not any(self.rx[16 * g + p] != p for p in range(16)):
            tg = [ch]
        else:
            tg = [16 * g + p for p in range(16) if self.rx[16 * g + p] == c]
        out = []
        for p in tg:
            m = msg if p == ch else self.on_part(msg, p)
            if self._drop(p, m):
                continue
            if m.type == "control_change" and m.control == 10:
                self.pan_raw[p] = m.value
                if self.mpan != 64:
                    m = self.on_part(m, p, value=max(0, min(127, m.value + self.mpan - 64)))
            out.append(m)
        return out

    def _drop(self, p, m):
        t = m.type
        if t == "control_change":
            c = m.control
            if c in (101, 100):
                self.sel[p] = 'rpn'
            elif c in (99, 98):
                self.sel[p] = 'nrpn'
        sw = self.rxsw.get(p)
        if not sw:
            return False
        if t != "control_change":
            return RX_TYPE.get(t) in sw
        c = m.control
        if 0x06 in sw:
            return True
        if c in (101, 100):
            return 0x09 in sw
        if c in (99, 98):
            return 0x0A in sw
        if c in (6, 38, 96, 97):
            sel = self.sel.get(p)
            return (sel == 'rpn' and 0x09 in sw) or (sel == 'nrpn' and 0x0A in sw)
        return RX_CC.get(c) in sw

    def sysex(self, d):
        """A part's receive setting (40/50 1p aa) or master pan (40 00 06),
        d the exclusive's data (F0 and F7 off): None where it is neither;
        else the pans to send again, [(part, CC10 value)] -- every part's at a
        new master pan, none otherwise."""
        d = tuple(d)
        if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12 and d[4] in (0x40, 0x50)):
            return None
        if d[4] == 0x40 and d[5] == 0x00 and d[6] == 0x06:
            self.mpan = max(1, min(127, int(d[7])))
            return [(p, max(0, min(127, self.pan_raw.get(p, 64) + self.mpan - 64)))
                    for p in range(self.nparts)]
        if d[5] >> 4 != 1:
            return None
        a = d[6]
        if not (a == 0x02 or 0x03 <= a <= 0x12 or a in (0x14, 0x1F, 0x20)):
            return None
        ch = part_of_block(d[5] & 0x0F) + (16 if d[4] == 0x50 else 0)
        if ch >= self.nparts:
            return []
        v = int(d[7])
        if a == 0x02:
            self.rx[ch] = v if v < 16 else 16
        elif a == 0x14:
            self.assign[ch] = v
        elif a in (0x1F, 0x20):
            self.ccnum[(ch, a)] = v
        else:
            sw = self.rxsw.setdefault(ch, set())
            if v:
                sw.discard(a)
            else:
                sw.add(a)
        return []

    def pan_msg(self, p, v):
        """Part p's CC10 at v (a new master pan's, sent again)."""
        return self.on_part(mido.Message("control_change", channel=p % 16, control=10, value=v), p)
