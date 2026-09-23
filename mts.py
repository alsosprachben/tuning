"""The MIDI Tuning Standard: a store of 128-key tables, and its SysEx.

    import mts
    store = mts.TuningStore()          # bank 0 holds the built-in tuners
    store.select(ch, bank=0, program=6)   # werckmeister, by RPN 0/4 and 0/3
    hz = store.table_for(ch)[note]

WHY THIS EXISTS. GM 2's Scale/Octave message carries twelve cents, one per pitch
class, repeated up the compass -- which is a temperament and nothing more. It
cannot say "the octaves are stretched", and eleven of this renderer's twenty
tuners fit in it while nine do not (midi.md). An MTS table is 128 KEYS at
100/16384 of a cent, so every one of the twenty fits exactly, `stretch` and
`dynamic` included: blockrender.tuning_table already solves each of them to a
fixed 128-key table, and that table is what goes in a dump.

ONLY THE `gm2` TUNER HONOURS ANY OF THIS. Choosing a tuner is choosing who owns
the tuning: under `hybrid` the renderer's temperament rules and a file's dump is
ignored; under `gm2` the file is in charge, starting from equal temperament at
A440 -- GM's power-on state. Ben's decision, and the reason there is a tuner
called `gm2` rather than a store bolted onto all of them.

THE SOURCE is the MMA's "MIDI Tuning Updated Specification" (MTS, with the
CA-020 bank/dump and CA-021/RP-020 scale/octave extensions), read in full.
Everything below is checked against it, and three things in it are worth
knowing because they are not what a reader would guess:

  - A TUNING PROGRAM OR BANK SELECT MOVES SOUNDING NOTES. "This change takes
    effect immediately and must occur without audible artifacts (notes-off,
    resets, re-triggers, glitches, etc.) if any affected notes are sounding."
    The first draft of this module applied it from the next note, like a
    program change. It is not like a program change.
  - THE ORIGINAL DUMP'S CHECKSUM IS UNRELIABLE, by the spec's own account:
    "various manufacturers have implemented that checksum differently, and it
    is now recommended that receivers may ignore the checksum in that message"
    -- so 08 01 is accepted whatever its checksum, while 08 04/05/06 are held
    to "successively XOR'ing the bytes in the message, excluding the F0, F7,
    and the checksum field", AND'ed with 7F.
  - THE SPEC'S OWN EXAMPLE TABLE HAS A TYPO. "00 00 01 = 8.2104 Hz" is 7.3
    cents above 00 00 00, where one step of the word is 0.0061 cents; its own
    "45 00 01 = 440.0016 Hz" is exactly one step. Every other example agrees
    with the definition to within 0.01 cents (the top of the table drifts by
    rounding). This codec follows the DEFINITION, and the selftest checks the
    examples against it with that one entry named.

"Standard mappings of 'common' tunings to program numbers are not being
proposed at this time" -- so the built-in order below is this renderer's own,
and RP-020's one suggestion is honoured: bank 0, preset 0 is equal temperament.
"""
import math

import numpy as np

# ------------------------------------------------------------------ the word
#
# One key is three bytes: xx the semitone at or below the frequency, and yy zz
# fourteen bits of the hundred cents above it. 16384 steps of a semitone is
# 0.0061 cents, which is finer than anything a listener or a tuner here can
# tell apart -- the reason every table round-trips "exactly" in practice.
FRACTION_STEPS = 16384
NO_CHANGE = (0x7F, 0x7F, 0x7F)      # "reserved to indicate ... a 'no change' condition"
_A4_HZ = 440.0


def _note_float(hz):
    """MIDI note number of a frequency, as a real number (A4 = 69 at 440)."""
    return 69.0 + 12.0 * math.log2(float(hz) / _A4_HZ)


def hz_to_word(hz):
    """(xx, yy, zz) for a frequency. Clamped to the range the word can hold."""
    n = _note_float(hz)
    xx = int(math.floor(n))
    frac = n - xx
    f = int(round(frac * FRACTION_STEPS))
    if f >= FRACTION_STEPS:          # rounding carried into the next semitone
        xx += 1
        f = 0
    if xx < 0:
        return (0, 0, 0)
    if xx > 127 or (xx == 127 and f >= FRACTION_STEPS - 1):
        # 7F 7F 7F is reserved for "no change", so the top word stops short.
        return (0x7F, 0x7F, 0x7E)
    # "0xxxxxxx 0abcdefg 0hijklmn": yy carries the MORE significant seven.
    return (xx, (f >> 7) & 0x7F, f & 0x7F)


def word_to_hz(xx, yy, zz):
    """The frequency a word encodes, or None for the no-change word."""
    if (xx, yy, zz) == NO_CHANGE:
        return None
    n = xx + ((yy << 7) | zz) / float(FRACTION_STEPS)
    return _A4_HZ * 2.0 ** ((n - 69.0) / 12.0)


def equal_table():
    """GM's power-on tuning: equal temperament at A440, all 128 keys."""
    return np.array([_A4_HZ * 2.0 ** ((k - 69) / 12.0) for k in range(128)],
                    dtype=np.float64)


# ----------------------------------------------------------------- the codec
#
# mido hands sysex over WITHOUT F0 and F7, so every offset below starts at the
# universal id (7E or 7F). Sub-id 1 is 08, MIDI Tuning, for all of these.

def _checksum(body):
    """XOR of every byte but F0, F7 and the checksum itself, AND 7F -- the rule
    the extensions give for every dump. Sent on 08 01 too, where the spec
    tells receivers they may ignore it."""
    c = 0
    for b in body:
        c ^= b
    return c & 0x7F


def parse_mts(data):
    """A parsed MTS message, or None if this is not one we read.

      ('dump',   bank, program, name, table)   table: 128 floats, NaN = keep
      ('single', bank, program, {key: hz}, realtime)

    Bank is 0 for the forms that carry none. The per-channel Scale/Octave
    ADJUST messages (08 08 / 08 09) are not read here -- they have their own
    parser, parse_sota, and work under every tuner -- but the Scale/Octave
    DUMPS (08 05 / 08 06) are, because they write a preset into the store.
    """
    d = tuple(data)
    if len(d) < 4 or d[0] not in (0x7E, 0x7F) or d[2] != 0x08:
        return None
    sub = d[3]
    if sub in (0x05, 0x06) and d[0] == 0x7E:
        # F0 7E dd 08 05 bb tt name[16] [xx]*12 cs F7         (-64..+63 cents)
        # F0 7E dd 08 06 bb tt name[16] [xx yy]*12 cs F7  (+/-100 cents, 2 byte)
        # A scale/octave preset: twelve offsets from EQUAL TEMPERAMENT, repeated
        # in every octave, stored as the 128-key table it amounts to.
        n = 12 if sub == 0x05 else 24
        if len(d) < 6 + 16 + n + 1:
            return None
        bank, prog = d[4], d[5]
        name = bytes(d[6:22]).decode('ascii', 'replace').rstrip(' \x00')
        body = d[22:22 + n]
        if _checksum(d[:22 + n]) != d[22 + n]:
            return None
        if sub == 0x05:
            cents = [float(b) - 64.0 for b in body]
        else:
            cents = [((body[2 * i] << 7 | body[2 * i + 1]) - 8192) / 8192.0 * 100.0
                     for i in range(12)]
        et = equal_table()
        table = np.array([et[k] * 2.0 ** (cents[k % 12] / 1200.0)
                          for k in range(128)])
        return ('dump', bank, prog, name, table)
    if sub in (0x01, 0x04) and d[0] == 0x7E:
        # 01: F0 7E dd 08 01 tt name[16] (xx yy zz)*128 cs F7
        # 04: F0 7E dd 08 04 bb tt name[16] (xx yy zz)*128 cs F7
        off = 4
        bank = 0
        if sub == 0x04:
            bank = d[off]; off += 1
        need = off + 1 + 16 + 384 + 1
        if len(d) < need:
            return None
        prog = d[off]; off += 1
        name = bytes(d[off:off + 16]).decode('ascii', 'replace').rstrip(' \x00')
        off += 16
        words = d[off:off + 384]
        cs = d[off + 384]
        # 08 01's checksum is ignored, as the spec recommends; 08 04's is held.
        if sub == 0x04 and _checksum(d[:off + 384]) != cs:
            return None
        table = np.full(128, np.nan)
        for k in range(128):
            hz = word_to_hz(*words[3 * k:3 * k + 3])
            if hz is not None:
                table[k] = hz
        return ('dump', bank, prog, name, table)
    if (sub == 0x02 and d[0] == 0x7F) or sub == 0x07:
        # 02: F0 7F dd 08 02 tt ll (kk xx yy zz)*ll F7        -- real-time only
        # 07: F0 7F dd 08 07 bb tt ll ... F7   real-time: "WILL affect currently
        #     sounding notes"; F0 7E ...: non-real-time, "will NOT update the
        #     currently sounding notes".
        off = 4
        bank = 0
        if sub == 0x07:
            bank = d[off]; off += 1
        if len(d) < off + 2:
            return None
        prog, ll = d[off], d[off + 1]
        off += 2
        keys = {}
        for i in range(ll):
            q = d[off + 4 * i: off + 4 * i + 4]
            if len(q) < 4:
                break
            hz = word_to_hz(q[1], q[2], q[3])
            if hz is not None:
                keys[q[0]] = hz
        return ('single', bank, prog, keys, d[0] == 0x7F)
    return None


def bulk_dump_message(table, program, name='', bank=None, device=0x7F):
    """The bytes BETWEEN F0 and F7 for a whole 128-key table.

    `table` is anything indexable by key (a list, an array, or blockrender's
    tuning_table dict); a key it does not have is sent as no-change.
    """
    if bank is None:
        body = [0x7E, device, 0x08, 0x01, program & 0x7F]
    else:
        body = [0x7E, device, 0x08, 0x04, bank & 0x7F, program & 0x7F]
    nm = (name or '')[:16].ljust(16)
    body += [ord(c) & 0x7F for c in nm]
    for k in range(128):
        try:
            hz = table[k]
        except (KeyError, IndexError):
            hz = None
        if hz is None or not (hz > 0.0):
            body += list(NO_CHANGE)
        else:
            body += list(hz_to_word(hz))
    body.append(_checksum(body))
    return body


def single_note_message(keys, program, bank=None, device=0x7F, realtime=True):
    """The bytes for a single-note change, {key: hz}.

    Real-time unless `realtime=False`, which needs a bank: the non-real-time
    form exists only as 08 07, the CA-020 extension.
    """
    items = sorted(keys.items())[:127]
    if bank is None:
        if not realtime:
            raise ValueError("a non-real-time single-note change needs a bank")
        body = [0x7F, device, 0x08, 0x02, program & 0x7F, len(items)]
    else:
        body = [0x7F if realtime else 0x7E, device, 0x08, 0x07,
                bank & 0x7F, program & 0x7F, len(items)]
    for k, hz in items:
        body += [k & 0x7F] + list(hz_to_word(hz))
    return body


# ------------------------------------------------------------- the built-ins
#
# BANK 0, EQUAL TEMPERAMENT FIRST, AND FROZEN. A file that selects program 6
# expects Werckmeister III tomorrow as well as today, so this order is a public
# interface and must never be reordered: a new tuner is only ever APPENDED.
# Documented in midi.md for anyone writing a file against it.
#
# Each is built at that tuner's own reference pitch: selecting `hybrid` drops
# the channel to A415, because that is what `hybrid` is.
BUILTIN_PROGRAMS = (
    'even',                                          # 0  GM power-on
    'hybrid', 'hybridharm', 'hybrid440', 'hybridharm440',       # 1-4
    'stretch', 'werckmeister', 'sankey', 'meantone', 'well',    # 5-9
    'pyth', 'just', 'linear', 'linear5', 'linearwell', 'bechstein',  # 10-15
    'spiral', 'semi', 'path', 'dynamic',             # 16-19
)


def builtin_table(name):
    """A registry tuner as 128 Hz, or None if it cannot be built here.

    The path-generated tuners load ../path from outside this repository; if
    that is not present their slots fall back to equal temperament, and the
    caller is told rather than handed a silent substitute.
    """
    import midilib
    import blockrender
    saved = midilib.tuner_class      # tuning_table sets the global; put it back
    try:
        t = blockrender.tuning_table(name)
    except Exception:
        return None
    finally:
        midilib.tuner_class = saved
    if len(t) < 128:
        return None
    return np.array([t[k] for k in range(128)], dtype=np.float64)


class TuningStore(object):
    """Banks x programs of 128-key tables, and which one each channel uses.

    A program nobody has loaded sounds equal temperament. A dump into a
    built-in slot replaces it for the rest of the render or session: the store
    is the device's memory, and a file that writes to program 6 has changed
    program 6.
    """

    def __init__(self, warn=None):
        self._tables = {}            # (bank, program) -> 128 floats
        self._sel = {}               # channel -> (bank, program)
        self._warn = warn or (lambda msg: None)
        self._missing = set()

    # -- the store
    def table(self, bank, program):
        key = (int(bank), int(program))
        t = self._tables.get(key)
        if t is not None:
            return t
        if key[0] == 0 and key[1] < len(BUILTIN_PROGRAMS):
            name = BUILTIN_PROGRAMS[key[1]]
            t = builtin_table(name)
            if t is None:
                if name not in self._missing:
                    self._missing.add(name)
                    self._warn("MTS built-in %d (%s) could not be built here; "
                               "it sounds equal temperament" % (key[1], name))
                t = equal_table()
        else:
            t = equal_table()
        self._tables[key] = t
        return t

    def load(self, msg):
        """Apply a parse_mts() result. Returns the (bank, program) it touched."""
        kind, bank, prog = msg[0], msg[1], msg[2]
        cur = self.table(bank, prog).copy()
        if kind == 'dump':
            new = msg[4]
            keep = np.isnan(new)
            cur[~keep] = new[~keep]
        elif kind == 'single':
            for k, hz in msg[3].items():
                if 0 <= k < 128:
                    cur[k] = hz
        self._tables[(bank, prog)] = cur
        return (bank, prog)

    # -- the channels
    def select(self, ch, bank=None, program=None):
        b, p = self._sel.get(ch, (0, 0))
        if bank is not None:
            b = int(bank)
        if program is not None:
            p = int(program)
        self._sel[ch] = (b, p)

    def selection(self, ch):
        return self._sel.get(ch, (0, 0))

    def reset_selections(self):
        """GM System On: every channel back to program 0 of bank 0.

        The TABLES are kept. A mode reset is not a memory wipe, and a file that
        loads its tunings once and then resets for the performance should not
        lose them. The MTS spec says nothing about GM System On, so this is a
        judgement, and it is the one that loses nothing.
        """
        self._sel.clear()

    def table_for(self, ch):
        return self.table(*self.selection(ch))
