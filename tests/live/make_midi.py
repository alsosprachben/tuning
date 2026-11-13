#!/usr/bin/env python3
"""The test files whose maker is kept: python3 tests/live/make_midi.py [NAME ...]

Writes into tests/live/midi/ (the older files there are fixtures as they
were made). Each is short and states one thing per segment; the segments'
times are what effects.py measures at.
"""
import os
import sys

import mido

MIDI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midi")


def gs(addr, v):
    """A Roland DT1 to address addr (3 bytes), its checksum."""
    a = list(addr) + [v]
    return mido.Message('sysex', data=[0x41, 0x10, 0x42, 0x12] + a + [(128 - sum(a) % 128) % 128])


def one_track():
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=500000))
    return mid, tr


def gsrx_2port():
    """Two ports: port B's part 2 received on port B's channel 1 (layered),
    master pan 32, then a CC10 under it -- port B's parts as port A's."""
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    A, B = mido.MidiTrack(), mido.MidiTrack()
    mid.tracks += [A, B]
    A.append(mido.MetaMessage('midi_port', port=0, time=0))
    A.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    A.append(gs([0x40, 0x00, 0x7F], 0x00))
    B.append(mido.MetaMessage('midi_port', port=1, time=0))

    def chord(tr, ch, gap):
        for i, n in enumerate((60, 64, 67)):
            tr.append(mido.Message('note_on', channel=ch, note=n, velocity=90, time=gap if i == 0 else 0))
        for i, n in enumerate((60, 64, 67)):
            tr.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=360 if i == 0 else 0))
    B.append(mido.Message('program_change', channel=0, program=0, time=0))
    B.append(mido.Message('program_change', channel=1, program=0, time=0))
    chord(B, 0, 20)
    B.append(gs([0x40, 0x12, 0x02], 0x00))
    chord(B, 0, 0)
    A.append(gs([0x40, 0x00, 0x06], 0x20))
    A[-1].time = 20 + 360 * 2
    chord(B, 0, 0)
    B.append(mido.Message('control_change', channel=0, control=10, value=100, time=0))
    chord(B, 0, 0)
    B.append(mido.Message('note_on', channel=0, note=60, velocity=0, time=480))
    return mid


def drumnrpn():
    """Snare and hi-hat: as the set has them; snare level 40 (NRPN); hi-hat
    Rx note on off (drum setup); a drum set change; hi-hat level 127; a GS
    reset."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr.append(mido.Message('program_change', channel=9, program=0))

    def hit(gap):
        tr.append(mido.Message('note_on', channel=9, note=38, velocity=100, time=gap))
        tr.append(mido.Message('note_on', channel=9, note=42, velocity=100, time=0))
        tr.append(mido.Message('note_off', channel=9, note=38, velocity=0, time=60))
        tr.append(mido.Message('note_off', channel=9, note=42, velocity=0, time=0))

    def nrpn(msb, lsb, v):
        for c, x in ((99, msb), (98, lsb), (6, v)):
            tr.append(mido.Message('control_change', channel=9, control=c, value=x))
    hit(20)
    nrpn(0x1A, 38, 40)
    hit(300)
    tr.append(gs([0x41, 0x08, 42], 0x00))
    hit(300)
    tr.append(mido.Message('program_change', channel=9, program=0, time=300))
    hit(0)
    nrpn(0x1A, 42, 127)
    hit(300)
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr[-1].time = 300
    hit(0)
    tr.append(mido.Message('note_on', channel=9, note=38, velocity=0, time=960))
    return mid


def drumnrpn2():
    """Drum pitch and pan: snare plain, +5, -7 and panned to 20; low tom
    panned to 110 and +7 by drum setup's PLAY NOTE; after a GS reset."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr.append(mido.Message('program_change', channel=9, program=0))

    def nrpn(msb, lsb, v, gap=0):
        for i, (c, x) in enumerate(((99, msb), (98, lsb), (6, v))):
            tr.append(mido.Message('control_change', channel=9, control=c, value=x, time=gap if i == 0 else 0))

    def hit(n, gap):
        tr.append(mido.Message('note_on', channel=9, note=n, velocity=100, time=gap))
        tr.append(mido.Message('note_off', channel=9, note=n, velocity=0, time=60))
    hit(38, 20)
    nrpn(0x18, 38, 64 + 5, gap=420)
    hit(38, 60)
    nrpn(0x18, 38, 64 - 7, gap=420)
    nrpn(0x1C, 38, 20)
    hit(38, 60)
    tr.append(gs([0x41, 0x04, 45], 110))
    tr[-1].time = 420
    hit(45, 60)
    tr.append(gs([0x41, 0x01, 45], 52))
    tr[-1].time = 420
    hit(45, 60)
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr[-1].time = 420
    hit(38, 60)
    hit(45, 0)
    tr.append(mido.Message('note_on', channel=9, note=38, velocity=0, time=960))
    return mid


def gsvsense():
    """A chord at velocity 100: plain; velocity sense depth 32; offset 100;
    keyboard range 62-66 (E alone); after a GS reset."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))

    def chord(gap, vel=100):
        for i, n in enumerate((60, 64, 67)):
            tr.append(mido.Message('note_on', channel=0, note=n, velocity=vel, time=gap if i == 0 else 0))
        for i, n in enumerate((60, 64, 67)):
            tr.append(mido.Message('note_off', channel=0, note=n, velocity=0, time=300 if i == 0 else 0))
    chord(20)
    tr.append(gs([0x40, 0x11, 0x1A], 32))
    chord(60)
    tr.append(gs([0x40, 0x11, 0x1A], 64))
    tr.append(gs([0x40, 0x11, 0x1B], 100))
    chord(60)
    tr.append(gs([0x40, 0x11, 0x1B], 64))
    tr.append(gs([0x40, 0x11, 0x1D], 62))
    tr.append(gs([0x40, 0x11, 0x1E], 66))
    chord(60)
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr[-1].time = 60
    chord(0)
    tr.append(mido.Message('note_on', channel=0, note=60, velocity=0, time=960))
    return mid


def mpe_zone():
    """MPE: a Lower Zone of 7 members (MCM); a chord a note a member, member
    1 gliding up a whole tone and 3 down a semitone, 2 pressed and
    brightened; the manager's volume (fanned), bend (+1 st), CC74 and
    pressure; a member's CC7 (ignored); a new MCM of 3 (channels 5-8 leave,
    reset); a chord, member 2 down 16 st; channel 6 outside the zone."""
    mid, tr = one_track()

    def cc(ch, c, v, t=0):
        tr.append(mido.Message('control_change', channel=ch, control=c, value=v, time=t))
    cc(0, 101, 0); cc(0, 100, 6); cc(0, 6, 7); cc(0, 101, 127); cc(0, 100, 127)
    for ch in range(0, 8):
        tr.append(mido.Message('program_change', channel=ch, program=48))
    for i, (ch, n) in enumerate(((1, 60), (2, 64), (3, 67))):
        tr.append(mido.Message('note_on', channel=ch, note=n, velocity=90, time=120 if i == 0 else 0))
    for k in range(1, 9):
        tr.append(mido.Message('pitchwheel', channel=1, pitch=int(8191 * k / 8 * 2 / 48), time=40))
        tr.append(mido.Message('pitchwheel', channel=3, pitch=int(-8192 * k / 8 * 1 / 48), time=0))
        tr.append(mido.Message('aftertouch', channel=2, value=min(127, 16 * k), time=0))
        cc(2, 74, 64 + 7 * k)
    cc(0, 7, 70, 240)
    tr.append(mido.Message('pitchwheel', channel=0, pitch=4096, time=120))
    cc(1, 7, 20, 120)
    cc(0, 74, 100, 120)
    tr.append(mido.Message('aftertouch', channel=0, value=90, time=120))
    for ch, n in ((1, 60), (2, 64), (3, 67)):
        tr.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=240 if ch == 1 else 0))
    tr.append(mido.Message('pitchwheel', channel=0, pitch=0, time=0))
    cc(0, 101, 0, 120); cc(0, 100, 6); cc(0, 6, 3); cc(0, 101, 127); cc(0, 100, 127)
    for i, (ch, n) in enumerate(((1, 62), (2, 65), (3, 69))):
        tr.append(mido.Message('note_on', channel=ch, note=n, velocity=80, time=60 if i == 0 else 0))
    tr.append(mido.Message('pitchwheel', channel=2, pitch=-2730, time=240))
    for ch, n in ((1, 62), (2, 65), (3, 69)):
        tr.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=480 if ch == 1 else 0))
    tr.append(mido.Message('note_on', channel=5, note=48, velocity=90, time=60))
    tr.append(mido.Message('note_off', channel=5, note=48, velocity=0, time=480))
    tr.append(mido.Message('note_on', channel=0, note=40, velocity=0, time=480))
    return mid


def _mpe_variant(extra):
    """mpe/: the zone and a chord, one thing more (the bisection's files)."""
    mid, tr = one_track()

    def cc(ch, c, v, t=0):
        tr.append(mido.Message('control_change', channel=ch, control=c, value=v, time=t))
    cc(0, 101, 0); cc(0, 100, 6); cc(0, 6, 7); cc(0, 101, 127); cc(0, 100, 127)
    for ch in range(0, 8):
        tr.append(mido.Message('program_change', channel=ch, program=48))
    for i, (ch, n) in enumerate(((1, 60), (2, 64), (3, 67))):
        tr.append(mido.Message('note_on', channel=ch, note=n, velocity=90, time=120 if i == 0 else 0))
    extra(tr, cc)
    for ch, n in ((1, 60), (2, 64), (3, 67)):
        tr.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=480 if ch == 1 else 0))
    tr.append(mido.Message('note_on', channel=0, note=40, velocity=0, time=480))
    return mid


def _member_glide(bends=False, press=False):
    def go(tr, cc):
        for k in range(1, 9):
            tr.append(mido.Message('pitchwheel', channel=1, pitch=int(8191 * k / 8 * 2 / 48) if bends else 0,
                                   time=40))
            if press:
                tr.append(mido.Message('aftertouch', channel=2, value=min(127, 16 * k)))
                cc(2, 74, 64 + 7 * k)
    return go


MPE_VARIANTS = {
    "a_plain": _member_glide(),
    "b_bends": _member_glide(bends=True),
    "c_mvol": lambda tr, cc: (_member_glide()(tr, cc), cc(0, 7, 70, 240)),
    "d_press": _member_glide(press=True),
    "e_mgrbend": lambda tr, cc: tr.append(mido.Message('pitchwheel', channel=0, pitch=4096, time=240)),
    "f_m3neg": lambda tr, cc: [tr.append(mido.Message('pitchwheel', channel=3, pitch=int(-8192 * k / 8 * 1 / 48),
                                                      time=40)) for k in range(1, 9)],
    "g_mcc74": lambda tr, cc: cc(0, 74, 100, 240),
    "h_mgrat": lambda tr, cc: tr.append(mido.Message('aftertouch', channel=0, value=90, time=240)),
    "i_memcc7": lambda tr, cc: cc(1, 7, 20, 240),
}

def rhythmpart():
    """USE FOR RHYTHM PART on part 1 (a piano on channel 1, nvlive_check
    --beside): a chord; part 1 to MAP1 -- its kick, snare and hat; back to
    melodic -- the chord again."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))

    def notes(gap, ns, ch=0):
        for i, n in enumerate(ns):
            tr.append(mido.Message('note_on', channel=ch, note=n, velocity=100, time=gap if i == 0 else 0))
        for i, n in enumerate(ns):
            tr.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=300 if i == 0 else 0))
    notes(20, (60, 64, 67))
    tr.append(gs([0x40, 0x11, 0x15], 0x01))
    notes(480, (36, 38, 42))
    tr.append(gs([0x40, 0x11, 0x15], 0x00))
    notes(480, (60, 64, 67))
    tr.append(mido.Message('note_on', channel=0, note=60, velocity=0, time=960))
    return mid


def two_organs():
    """Two organs with swell laws of their own: a church organ (19) on
    channel 1 and a drawbar organ (16) on channel 2, a chord each, each
    channel's CC7 (its swell) moving under it -- one law per render, every
    organ's own level (blockrender._prep_swell_law)."""
    mid, tr = one_track()
    tr.append(mido.Message('program_change', channel=0, program=19))
    tr.append(mido.Message('program_change', channel=1, program=16))
    for i, (ch, n) in enumerate(((0, 48), (0, 55), (0, 60), (1, 64), (1, 67), (1, 72))):
        tr.append(mido.Message('note_on', channel=ch, note=n, velocity=90, time=20 if i == 0 else 0))
    for k in range(12):
        tr.append(mido.Message('control_change', channel=0, control=7, value=127 - 8 * k, time=80))
        tr.append(mido.Message('control_change', channel=1, control=7, value=40 + 7 * k, time=0))
    for i, (ch, n) in enumerate(((0, 48), (0, 55), (0, 60), (1, 64), (1, 67), (1, 72))):
        tr.append(mido.Message('note_off', channel=ch, note=n, velocity=0, time=240 if i == 0 else 0))
    tr.append(mido.Message('note_on', channel=0, note=40, velocity=0, time=960))
    return mid


def moog_cmx():
    """A Moog (81, its saw lead) under GS's controller matrix: the mod wheel
    into TVF cutoff (40 21 01: +4800 cents at full), the wheel swept up and
    down across a held note -- the Moog's knobs following the matrix's
    cutoff (its filter row a timeline: _MOOG_KVAR)."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr.append(mido.Message('program_change', channel=0, program=81))
    tr.append(gs([0x40, 0x21, 0x01], 0x60))
    tr.append(mido.Message('note_on', channel=0, note=48, velocity=100, time=20))
    for k in list(range(0, 128, 16)) + list(range(127, -1, -16)):
        tr.append(mido.Message('control_change', channel=0, control=1, value=k, time=60))
    tr.append(mido.Message('note_off', channel=0, note=48, velocity=0, time=120))
    tr.append(mido.Message('note_on', channel=0, note=40, velocity=0, time=960))
    return mid


def drumdelay():
    """A drum key's own delay send: the GS delay on the drum channel (CC94
    100), a snare struck with its send 127 (the channel's), then 0, then 64
    (drum NRPN 1F) -- its echoes, then none, then softer."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr.append(mido.Message('program_change', channel=9, program=0))
    tr.append(mido.Message('control_change', channel=9, control=94, value=100))

    def hit(gap):
        tr.append(mido.Message('note_on', channel=9, note=38, velocity=110, time=gap))
        tr.append(mido.Message('note_off', channel=9, note=38, velocity=0, time=60))

    def nrpn(v):
        for c, x in ((99, 0x1F), (98, 38), (6, v)):
            tr.append(mido.Message('control_change', channel=9, control=c, value=x))
    hit(20)
    nrpn(0)
    hit(1380)
    nrpn(64)
    hit(1380)
    tr.append(mido.Message('note_on', channel=9, note=38, velocity=0, time=1920))
    return mid


def userdrums():
    """A USER DRUM SET (GS's set 65: program 64): key 36 the TR-808's kick (set
    25), 38 Standard's electric snare (40) its play note +2, 42 the Power
    set's hi-hat (16) panned to 20, 46 Standard's open hat not received, 49
    left unset; each struck in turn on channel 10."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))

    def ud(code, key, v):
        tr.append(gs([0x21, code, key], v))
    for key, sset, snote in ((36, 25, 36), (38, 0, 40), (42, 16, 42), (46, 0, 46)):
        ud(0x0B, key, sset)
        ud(0x0C, key, snote)
    ud(0x01, 38, 42)
    ud(0x04, 42, 20)
    ud(0x08, 46, 0)
    tr.append(mido.Message('program_change', channel=9, program=64))
    for i, k in enumerate((36, 38, 42, 46, 49, 36)):
        tr.append(mido.Message('note_on', channel=9, note=k, velocity=100, time=20 if i == 0 else 420))
        tr.append(mido.Message('note_off', channel=9, note=k, velocity=0, time=60))
    tr.append(mido.Message('note_on', channel=9, note=36, velocity=0, time=960))
    return mid


def cmx_live():
    """THE CONTROLLER MATRIX, one held note at a time on a Moog lead (81):
    plain; the mod wheel into amplitude at -100 %, the wheel at half;
    channel pressure into pitch +2 semitones, pressed full; CC1's number set
    to CC20 and CC1 into cutoff +4800 cents, CC20 full; after a GS reset;
    then the LFOs: pressure into LFO1 pitch (236 cents), pressed full; the mod
    wheel into LFO1 amplitude at 100 %, the wheel full."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr.append(mido.Message('program_change', channel=0, program=81))

    def note(gap):
        tr.append(mido.Message('note_on', channel=0, note=57, velocity=100, time=gap))
        tr.append(mido.Message('note_off', channel=0, note=57, velocity=0, time=600))
    note(20)
    tr.append(gs([0x40, 0x21, 0x02], 0x00))
    tr.append(mido.Message('control_change', channel=0, control=1, value=64, time=120))
    note(0)
    tr.append(mido.Message('control_change', channel=0, control=1, value=0, time=120))
    tr.append(gs([0x40, 0x21, 0x20], 0x42))
    tr.append(mido.Message('aftertouch', channel=0, value=127))
    note(0)
    tr.append(mido.Message('aftertouch', channel=0, value=0, time=120))
    tr.append(gs([0x40, 0x11, 0x1F], 20))
    tr.append(gs([0x40, 0x21, 0x41], 0x60))
    tr.append(mido.Message('control_change', channel=0, control=20, value=127))
    note(0)
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr[-1].time = 120
    tr.append(mido.Message('program_change', channel=0, program=81))
    note(0)
    tr.append(gs([0x40, 0x21, 0x24], 50))
    tr[-1].time = 120
    tr.append(mido.Message('aftertouch', channel=0, value=127))
    note(0)
    tr.append(mido.Message('aftertouch', channel=0, value=0, time=120))
    tr.append(gs([0x40, 0x21, 0x06], 0x7F))
    tr.append(mido.Message('control_change', channel=0, control=1, value=127))
    note(0)
    tr.append(mido.Message('control_change', channel=0, control=1, value=0, time=120))
    tr.append(mido.Message('note_on', channel=0, note=57, velocity=0, time=960))
    return mid


MAKERS = {"cmx_live": cmx_live, "userdrums": userdrums, "drumdelay": drumdelay, "moog_cmx": moog_cmx, "two_organs": two_organs, "rhythmpart": rhythmpart, "gsrx_2port": gsrx_2port, "drumnrpn": drumnrpn, "drumnrpn2": drumnrpn2, "gsvsense": gsvsense,
          "mpe_zone": mpe_zone}


def main(argv):
    want = set(argv)
    for name, fn in MAKERS.items():
        if not want or name in want:
            fn().save(os.path.join(MIDI, name + ".mid"))
            print(name)
    os.makedirs(os.path.join(MIDI, "mpe"), exist_ok=True)
    for name, ex in MPE_VARIANTS.items():
        if not want or name in want or "mpe" in want:
            _mpe_variant(ex).save(os.path.join(MIDI, "mpe", name + ".mid"))
            print("mpe/" + name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
