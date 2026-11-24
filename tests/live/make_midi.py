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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # (ump)


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


def mpe_zone(program=48):
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
        tr.append(mido.Message('program_change', channel=ch, program=program))
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


def assign_mode():
    """GS's ASSIGN MODE (40 1p 14), by the arranger's intent: strings on
    channel 1 struck loud (120), then soft (30) on the same key before the
    first is let go -- the loud note sounding on under the default; cut by
    the soft strike under SINGLE; sounding on under FULL-MULTI; a crash
    cymbal loud then soft on the drum part, at its default and then SINGLE;
    after a GS reset, the default again. Each segment 2.5 s."""
    mid, tr = one_track()
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))
    tr.append(mido.Message('program_change', channel=0, program=48))
    gap = [20]

    def strings(at_gap):
        tr.append(mido.Message('note_on', channel=0, note=60, velocity=120, time=at_gap))
        tr.append(mido.Message('note_on', channel=0, note=60, velocity=30, time=480))
        tr.append(mido.Message('note_off', channel=0, note=60, velocity=0, time=960))
        tr.append(mido.Message('note_off', channel=0, note=60, velocity=0, time=96))

    def crash(at_gap):
        tr.append(mido.Message('note_on', channel=9, note=49, velocity=127, time=at_gap))
        tr.append(mido.Message('note_off', channel=9, note=49, velocity=0, time=60))
        tr.append(mido.Message('note_on', channel=9, note=49, velocity=30, time=240))
        tr.append(mido.Message('note_off', channel=9, note=49, velocity=0, time=60))
    strings(20)                                         # 0.02 s: the default
    tr.append(gs([0x40, 0x11, 0x14], 0))                # channel 1 SINGLE
    tr[-1].time = 864
    strings(0)                                          # 2.5 s
    tr.append(gs([0x40, 0x11, 0x14], 2))                # ...FULL-MULTI
    tr[-1].time = 864
    strings(0)                                          # 5.0 s
    crash(864)                                          # 7.5 s: the drum part at its default
    tr.append(gs([0x40, 0x10, 0x14], 0))                # the drum part SINGLE
    tr[-1].time = 2040
    crash(0)                                            # 10.0 s
    tr.append(gs([0x40, 0x00, 0x7F], 0x00))             # GS reset: every part's default
    tr[-1].time = 2040
    tr.append(mido.Message('program_change', channel=0, program=48))
    strings(0)                                          # 12.5 s
    tr.append(mido.Message('note_on', channel=0, note=60, velocity=0, time=1920))
    return mid


def m2_pernote():
    """MIDI 2.0's PER-NOTE PITCH, a Clip File at MIDI 1.0's own values (each
    velocity and controller an exact upscale): a Pitch 7.25 table (every key
    its 12-TET pitch); a piano's C major triad whose third alone settles to
    the just 5:4 mid-note; the just chord from each Note On's Pitch 7.9; a
    flute whose per-note bend (range 1 semitone) wobbles under the channel's
    wheel rising; a quarter-tone D, then reset by per-note management."""
    import math
    import ump as U
    Q = 960                                 # a beat, 0.5 s
    sec = lambda x: int(round(x * 2 * Q))
    ev = []
    add = lambda t, pkt: ev.append((sec(t), pkt))
    vel = U.scale_up(96, 7, 16)
    add(0, U.m2_program(0, 0, 0))
    add(0, U.m2_program(0, 1, 73))
    add(0, U.m2_cc(0, 0, 7, U.scale_up(100, 7, 32)))
    for n in range(128):
        add(0, U.m2_per_note_ctrl(0, 0, n, U.RPNC_PITCH, U.semitones_to_q(n, 25)))
    for n in (60, 64, 67):                  # the third settles, root and fifth held
        add(0.02, U.m2_note_on(0, 0, n, vel))
        add(3.0, U.m2_note_off(0, 0, n, vel))
    for i in range(17):
        add(1.0 + i / 16.0, U.m2_per_note_ctrl(0, 0, 64, U.RPNC_PITCH, U.semitones_to_q(64 - 0.1369 * i / 16.0, 25)))
    add(3.5, U.m2_per_note_ctrl(0, 0, 64, U.RPNC_PITCH, U.semitones_to_q(64, 25)))
    for n, p in ((60, 60.0), (64, 64 - 0.1369), (67, 67 + 0.01955)):    # the just chord, each its own
        add(4.0, U.m2_note_on(0, 0, n, vel, attr_type=3, attr=U.semitones_to_q(p, 9)))
        add(6.0, U.m2_note_off(0, 0, n, vel))
    add(6.9, U.m2_rpn(0, 1, 0, 7, U.semitones_to_q(1.0, 25)))     # per-note bend range: 1 semitone
    add(7.0, U.m2_note_on(0, 1, 72, vel))
    for i in range(96):                     # its own wobble, 5 Hz, half its range
        b = 0.5 * math.sin(2 * math.pi * 5.0 * i / 32.0)
        add(7.25 + i / 32.0, U.m2_per_note_bend(0, 1, 72, max(0, min(0xFFFFFFFF, int(2 ** 31 + b * 2 ** 31)))))
    for i in range(17):                     # ...under the wheel rising a quarter of its way
        add(8.0 + i / 16.0, U.m2_pitch_bend(0, 1, U.scale_up(8192 + 128 * i, 14, 32)))
    add(10.0, U.m2_note_off(0, 1, 72, vel))
    add(10.2, U.m2_per_note_ctrl(0, 0, 62, U.RPNC_PITCH, U.semitones_to_q(62.5, 25)))
    add(10.5, U.m2_note_on(0, 0, 62, vel))  # a quarter-tone D...
    add(11.5, U.m2_per_note_mgmt(0, 0, 62, reset=True))     # ...back to the tuner's
    add(12.5, U.m2_note_off(0, 0, 62, vel))
    ev.sort(key=lambda e: e[0])
    return ev


def save_m2(name, ev):
    import ump as U
    U.write_clip(os.path.join(MIDI, name + ".midi2"), ev, tpq=960)


def m2_organ():
    """A PIPE ORGAN ON ITS CHEST's WIND (GM 19: the wind rows), its notes with
    rows of their own riding both (_prep_wind_combos): a Pitch 7.25 table;
    a C major triad whose third settles to the just 5:4; a top note's own
    per-note bend; the channel's wheel moving under a held chord."""
    import math
    import ump as U
    Q = 960
    sec = lambda x: int(round(x * 2 * Q))
    ev = []
    add = lambda t, pkt: ev.append((sec(t), pkt))
    vel = U.scale_up(96, 7, 16)
    add(0, U.m2_program(0, 0, 19))
    for n in range(128):
        add(0, U.m2_per_note_ctrl(0, 0, n, U.RPNC_PITCH, U.semitones_to_q(n, 25)))
    for n in (60, 64, 67):
        add(0.02, U.m2_note_on(0, 0, n, vel))
        add(3.0, U.m2_note_off(0, 0, n, vel))
    for i in range(17):
        add(1.0 + i / 16.0, U.m2_per_note_ctrl(0, 0, 64, U.RPNC_PITCH, U.semitones_to_q(64 - 0.1369 * i / 16.0, 25)))
    add(3.5, U.m2_per_note_ctrl(0, 0, 64, U.RPNC_PITCH, U.semitones_to_q(64, 25)))
    add(4.0, U.m2_note_on(0, 0, 72, vel))
    for i in range(64):
        b = 0.5 * math.sin(2 * math.pi * 5.0 * i / 32.0)
        add(4.25 + i / 32.0, U.m2_per_note_bend(0, 0, 72, max(0, min(0xFFFFFFFF, int(2 ** 31 + b * 2 ** 31)))))
    add(6.5, U.m2_note_off(0, 0, 72, vel))
    for n in (55, 59, 62):
        add(7.0, U.m2_note_on(0, 0, n, vel))
        add(9.5, U.m2_note_off(0, 0, n, vel))
    for i in range(17):
        add(7.5 + i / 16.0, U.m2_pitch_bend(0, 0, U.scale_up(8192 + 128 * i, 14, 32)))
    add(10.0, U.m2_pitch_bend(0, 0, U.scale_up(8192, 14, 32)))
    ev.sort(key=lambda e: e[0])
    return ev


M2_MAKERS = {"m2_pernote": m2_pernote, "m2_organ": m2_organ}
# MIDI 1.0 fixtures as MIDI 2.0 (ump.midi1_to_clip): (source, name, raw UMP)
M2_CONVERTED = (("gsvsense", "m2_gsvsense", False), ("mpe_zone", "m2_mpe_zone_raw", True))

def dense_pedal():
    """HEAVY PLAYING, for the block budget (CPU against GPU): the sustain pedal
    down and fast arpeggios over six octaves, 16 notes a second at forte for
    20 s, the pedal changed every 4 s -- hundreds of strings ringing at once,
    as Ben's heaviest playing piles them up."""
    mid, tr = one_track()
    keys = [n for n in range(28, 101) if n % 12 in (0, 4, 7, 11, 2)]
    t = 0
    tr.append(mido.Message('control_change', channel=0, control=64, value=127, time=10))
    for i in range(320):
        k = keys[(i * 7) % len(keys)]
        tr.append(mido.Message('note_on', channel=0, note=k, velocity=96 + (i % 5) * 6, time=0 if i == 0 else 15))
        tr.append(mido.Message('note_off', channel=0, note=k, velocity=0, time=15))
        if i % 64 == 63:
            tr.append(mido.Message('control_change', channel=0, control=64, value=0, time=0))
            tr.append(mido.Message('control_change', channel=0, control=64, value=127, time=6))
    tr.append(mido.Message('control_change', channel=0, control=64, value=0, time=480))
    return mid


def stab_chords():
    """THICK STACCATO PUNCHES, for the note-on step's cost: a ten-note chord
    struck four times a second at forte for 12 s, each held 90 ms -- every
    stab starting thousands of partials in one block (Ben: "a thick chord a
    bunch in staccato punches" went over budget in the app)."""
    mid, tr = one_track()
    keys = [36, 43, 48, 52, 55, 60, 64, 67, 72, 76]
    for i in range(48):
        for j, k in enumerate(keys):
            tr.append(mido.Message('note_on', channel=0, note=k, velocity=110, time=(10 if i == 0 else 154) if j == 0 else 0))
        for j, k in enumerate(keys):
            tr.append(mido.Message('note_off', channel=0, note=k, velocity=0, time=86 if j == 0 else 0))
    return mid


def spectra(choice):
    """60's Organ 1 (bank 16) on a Spectra-Tone (CC83: patch_map.SPECTRA_CHOICES,
    10 the rotor, 11 Chorus): a chord held from 0.5 s on Theater (the rocker
    up), Cathedral at 3 s (CC80 0) -- the rotor's fall in about a second --
    Theater again at 6 s (its 13 s climb under the chord), a high C7 struck
    over it at 7 s and the chord's top lifted at 8 s; all off at 9.5 s."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('control_change', channel=0, control=0, value=16)),
          (0.0, mido.Message('program_change', channel=0, program=16)),
          (0.0, mido.Message('control_change', channel=0, control=83, value=choice)),
          (0.0, mido.Message('control_change', channel=0, control=80, value=127))]
    for k in (60, 64, 67, 72):
        ev.append((0.5, mido.Message('note_on', channel=0, note=k, velocity=100)))
    ev += [(3.0, mido.Message('control_change', channel=0, control=80, value=0)),
           (6.0, mido.Message('control_change', channel=0, control=80, value=127)),
           (7.0, mido.Message('note_on', channel=0, note=96, velocity=100)),
           (8.0, mido.Message('note_off', channel=0, note=72, velocity=0))]
    for k in (60, 64, 67, 96):
        ev.append((9.5, mido.Message('note_off', channel=0, note=k, velocity=0)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def spectra_sustain(choice):
    """60's Organ 1 on a Spectra-Tone (CC83 10 or 11) with SUSTAIN LONG drawn
    (bit 15 of its stop word: CC44 the bits 14-20, its default's Solo and
    Accent kept): a chord from 0.5 s lifted at 2.5 s, its tails ringing on
    their damper track -- still turning -- to 7 s; Cathedral at 4 s."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('control_change', channel=0, control=0, value=16)),
          (0.0, mido.Message('program_change', channel=0, program=16)),
          (0.0, mido.Message('control_change', channel=0, control=83, value=choice)),
          (0.0, mido.Message('control_change', channel=0, control=44, value=124 | 2)),
          (0.0, mido.Message('control_change', channel=0, control=80, value=127))]
    for k in (60, 67, 72, 84):
        ev += [(0.5, mido.Message('note_on', channel=0, note=k, velocity=100)),
               (2.5, mido.Message('note_off', channel=0, note=k, velocity=0))]
    ev.append((4.0, mido.Message('control_change', channel=0, control=80, value=0)))
    ev.append((7.0, mido.Message('control_change', channel=0, control=80, value=0)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def harmonium_stops():
    """GM 20, the harmonium's stops baked from their construction (licences.md
    L10): three registrations on its stop word (CC43 bits 0-6, CC44 7-13, CC45
    14+; stop_ranks' order), each a bass and a treble pair -- the default (Cor
    anglais + Flute); Bourdon, Clairon, Basson, Hautbois, Celeste; Clarinette,
    Fifre, Violoncelle, Sourdine, Musette with the tremolo. THEN THE EXPRESSION
    (CC44 4: the feet the wind, tonelib.harmonium_pressure): Basson + Hautbois
    soft (CC11 30) and loud (120), the loud with the tremolo, the feet moving
    under the last held pair (live's bellows)."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('program_change', channel=0, program=20))]
    regs = ((None, None, None), (2 | 4 | 8, 1 | 2, 0), (32 | 64, 16 | 32 | 64, 1))
    t = 0.2
    for cc43, cc44, cc45 in regs:
        if cc43 is not None:
            ev += [(t, mido.Message('control_change', channel=0, control=43, value=cc43)),
                   (t, mido.Message('control_change', channel=0, control=44, value=cc44)),
                   (t, mido.Message('control_change', channel=0, control=45, value=cc45))]
        for k in (48, 55, 72, 79):
            ev += [(t + 0.05, mido.Message('note_on', channel=0, note=k, velocity=100)),
                   (t + 1.6, mido.Message('note_off', channel=0, note=k, velocity=0))]
        t += 2.2
    for cc44, cc11 in ((1 | 4, 30), (1 | 4 | 8, 120)):
        ev += [(t, mido.Message('control_change', channel=0, control=43, value=8)),
               (t, mido.Message('control_change', channel=0, control=44, value=cc44)),
               (t, mido.Message('control_change', channel=0, control=45, value=0)),
               (t, mido.Message('control_change', channel=0, control=11, value=cc11))]
        for k in (48, 55, 72, 79):
            ev += [(t + 0.05, mido.Message('note_on', channel=0, note=k, velocity=100)),
                   (t + 1.6, mido.Message('note_off', channel=0, note=k, velocity=0))]
        t += 2.2
    ev += [(t - 1.4, mido.Message('control_change', channel=0, control=11, value=70)),
           (t - 1.0, mido.Message('control_change', channel=0, control=11, value=110))]
    ev.append((t + 0.5, mido.Message('control_change', channel=0, control=7, value=100)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def harmonium_wind():
    """GM 20's wind (wind.HarmoniumWind, step 5): the full registration's
    chord on the reservoir, drawing past the pumps (the sag), the player
    easing CC11 under it; the Expression drawn, a chord swelled by the feet
    (CC11 20 -> 127 -> 30); the treble's knee (CC22) at rest holding the
    treble pp while the feet push the bass, then fully in."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('program_change', channel=0, program=20))]
    cc = lambda t, c, v: ev.append((t, mido.Message('control_change', channel=0, control=c, value=v)))

    def chord(t0, t1, keys):
        for k in keys:
            ev.append((t0, mido.Message('note_on', channel=0, note=k, velocity=100)))
            ev.append((t1, mido.Message('note_off', channel=0, note=k, velocity=0)))
    for c, v in ((43, 127), (44, 1), (45, 0), (11, 127)):
        cc(0.1, c, v)
    chord(0.3, 4.0, (36, 43, 48, 55, 60, 64, 67, 72, 76, 79))
    cc(2.5, 11, 40)
    t = 4.6
    for c, v in ((43, 1 | 8 | 16), (44, 1 | 4), (11, 20)):
        cc(t, c, v)
    chord(t + 0.2, t + 5.0, (48, 55, 64, 72, 76))
    for i in range(21):
        cc(t + 0.4 + i * 0.1, 11, int(round(20 + 107 * i / 20)))
    for i in range(21):
        cc(t + 2.6 + i * 0.1, 11, int(round(127 - 97 * i / 20)))
    t = 10.2
    cc(t, 11, 20)
    cc(t, 22, 0)
    chord(t + 0.2, t + 4.5, (48, 55, 64, 72, 76))
    for i in range(21):
        cc(t + 0.4 + i * 0.1, 11, int(round(20 + 100 * i / 20)))
    cc(t + 3.0, 22, 127)
    ev.append((t + 5.0, mido.Message('control_change', channel=0, control=7, value=100)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def harmonium_boxes():
    """GM 20's boxes (tonelib.harmonium_box_*, step 5c): the back stops
    (Basson, Hautbois, Clairon, Fifre) on a chord under the Metaphone B+T,
    shut, and the Forte-Fixe B+T (CC45 bits 15-20); then the Forte-Expressif
    B+T under the Expression, the feet swelling a held chord past its 800 Pa
    and back; a Metaphone drawn on the treble alone under the swell."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('program_change', channel=0, program=20))]
    cc = lambda t, c, v: ev.append((t, mido.Message('control_change', channel=0, control=c, value=v)))

    def chord(t0, t1, keys):
        for k in keys:
            ev.append((t0, mido.Message('note_on', channel=0, note=k, velocity=100)))
            ev.append((t1, mido.Message('note_off', channel=0, note=k, velocity=0)))
    keys = (48, 55, 64, 72, 76)
    t = 0.2
    for c45 in (32 | 64, 0, 2 | 4):
        for c, v in ((43, 4 | 8 | 64), (44, 1), (45, c45), (11, 127)):
            cc(t, c, v)
        chord(t + 0.1, t + 2.0, keys)
        t += 2.5
    for c, v in ((43, 4 | 8 | 64), (44, 1 | 4), (45, 8 | 16), (11, 20)):
        cc(t, c, v)
    chord(t + 0.2, t + 5.0, keys)
    for i in range(21):
        cc(t + 0.4 + i * 0.1, 11, int(round(20 + 107 * i / 20)))
    cc(t + 2.6, 45, 8 | 16 | 64)                  # (the treble's Metaphone drawn under it: the next notes')
    chord(t + 3.0, t + 5.0, (79,))
    for i in range(16):
        cc(t + 3.4 + i * 0.1, 11, int(round(127 - 100 * i / 15)))
    ev.append((t + 5.5, mido.Message('control_change', channel=0, control=7, value=100)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def harmonium_prolong():
    """GM 20's Prolongement (CC46 bit 21: blockrender._prep_prolongement): C2
    latched through a treble chord (outside its octave: no release), G2
    taking over from it, G2 pressed again (absorbed: no new note), the stop
    pushed in (G2 released), C2 with it in (plain), and E2 latched to the end."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('program_change', channel=0, program=20))]
    cc = lambda t, c, v: ev.append((t, mido.Message('control_change', channel=0, control=c, value=v)))

    def note(t0, t1, k):
        ev.append((t0, mido.Message('note_on', channel=0, note=k, velocity=100)))
        ev.append((t1, mido.Message('note_off', channel=0, note=k, velocity=0)))
    cc(0.05, 46, 1)
    note(0.2, 0.5, 36)
    for k in (60, 64, 67):
        note(1.5, 2.0, k)
    note(2.5, 2.8, 43)
    note(3.5, 3.8, 43)
    cc(5.0, 46, 0)
    note(5.5, 5.8, 36)
    cc(6.0, 46, 1)
    note(6.2, 6.4, 40)
    ev.append((8.0, mido.Message('control_change', channel=0, control=7, value=100)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def harmonium_onset():
    """GM 20's onset (tonelib.harmonium_onset_delay, step 5e/5f): a phrase on
    the foundation with gentle keys (velocity 20) and sharp (127), each again
    with the Percussion (CC44 8: harmonium_percussion_rise), then sharp under
    the Expression (CC44 4) at a weak wind (CC11 30) and a strong one."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('program_change', channel=0, program=20))]
    cc = lambda t, c, v: ev.append((t, mido.Message('control_change', channel=0, control=c, value=v)))

    def phrase(t, vel):
        for i, k in enumerate((48, 60, 64, 72)):
            ev.append((t + 0.4 * i, mido.Message('note_on', channel=0, note=k, velocity=vel)))
            ev.append((t + 0.4 * i + 0.35, mido.Message('note_off', channel=0, note=k, velocity=0)))
        return t + 0.4 * 4 + 0.5
    t = 0.2
    for c44, vel in ((0, 20), (0, 127), (8, 20), (8, 127)):
        cc(t - 0.1, 43, 1 | 16)
        cc(t - 0.1, 44, c44)
        cc(t - 0.1, 11, 127)
        t = phrase(t, vel)
    for v11 in (30, 127):
        cc(t - 0.1, 44, 4)
        cc(t - 0.1, 11, v11)
        t = phrase(t, 127)
    ev.append((t + 0.5, mido.Message('control_change', channel=0, control=7, value=100)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def harmonium_grandjeu():
    """GM 20's Grand-Jeu (CC46 bit 1: tonelib.grand_jeu_on): a chord on the
    default registration; the Grand-Jeu drawn (every full stop, both halves,
    and the Forte-Expressifs) on the reservoir; then under the Expression, the
    feet swelling a held chord (the lids open past 800 Pa); the Grand-Jeu
    pushed in under a held chord (back to the knobs' own registration)."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('program_change', channel=0, program=20))]
    cc = lambda t, c, v: ev.append((t, mido.Message('control_change', channel=0, control=c, value=v)))

    def chord(t0, t1, keys=(48, 55, 64, 72, 76), vel=100):
        for k in keys:
            ev.append((t0, mido.Message('note_on', channel=0, note=k, velocity=vel)))
            ev.append((t1, mido.Message('note_off', channel=0, note=k, velocity=0)))
    chord(0.2, 2.2)
    cc(2.6, 46, 2)
    chord(2.8, 4.8)
    cc(5.2, 44, 4)
    cc(5.2, 11, 30)
    chord(5.4, 10.0)
    for i in range(21):
        cc(5.8 + 0.1 * i, 11, int(round(30 + 97 * i / 20)))
    cc(8.5, 46, 0)
    cc(8.5, 44, 0)
    chord(10.4, 12.4)
    ev.append((13.0, mido.Message('control_change', channel=0, control=7, value=100)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def taisho_course():
    """GS 107.8 Taisho Koto (licences.md L7, refitted on msx2plus's CC0 take):
    a phrase over its compass -- the courses, the pick's sweep by key -- with
    its drone struck (CC18 127: TaishoDroneProperties from the voice's laws)."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('control_change', channel=0, control=0, value=8)),
          (0.0, mido.Message('program_change', channel=0, program=107)),
          (0.0, mido.Message('control_change', channel=0, control=18, value=127))]
    for i, k in enumerate((50, 55, 62, 64, 67, 69, 71, 74, 76, 79)):
        ev.append((0.3 + 0.4 * i, mido.Message('note_on', channel=0, note=k, velocity=96)))
        ev.append((0.3 + 0.4 * i + 0.36, mido.Message('note_off', channel=0, note=k, velocity=0)))
    ev.append((6.5, mido.Message('control_change', channel=0, control=7, value=100)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def _timed(ev):
    mid, tr = one_track()
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def gu_refits_tones():
    """Two of the six voices once fitted to GeneralUser GS's samples,
    refitted 2026-11-24 (licences.md L12), on one channel: GS 124.1 Telephone
    2 (the MC34017 ringer) held, then 125.9 Burst Noise (radio static) held."""
    return _timed([(0.0, mido.Message('control_change', channel=0, control=0, value=1)),
                   (0.0, mido.Message('program_change', channel=0, program=124)),
                   (0.3, mido.Message('note_on', channel=0, note=60, velocity=100)),
                   (1.8, mido.Message('note_off', channel=0, note=60, velocity=0)),
                   (2.0, mido.Message('control_change', channel=0, control=0, value=9)),
                   (2.0, mido.Message('program_change', channel=0, program=125)),
                   (2.3, mido.Message('note_on', channel=0, note=60, velocity=100)),
                   (3.5, mido.Message('note_off', channel=0, note=60, velocity=0)),
                   (3.8, mido.Message('note_on', channel=0, note=67, velocity=80)),
                   (4.4, mido.Message('note_off', channel=0, note=67, velocity=0)),
                   (5.0, mido.Message('control_change', channel=0, control=7, value=100))])


def gu_refits_kits():
    """The other four, on the drum channel: the SFX set's High Q (39), Square
    Click (44) and Starship (71, held); the Electronic set's Gated SD (40) and
    the Power set's (38)."""
    ev = [(0.0, mido.Message('program_change', channel=9, program=56))]
    for at, k, v in ((0.3, 39, 100), (0.7, 44, 110), (1.1, 39, 70), (1.4, 44, 60)):
        ev += [(at, mido.Message('note_on', channel=9, note=k, velocity=v)),
               (at + 0.1, mido.Message('note_off', channel=9, note=k, velocity=0))]
    ev += [(1.8, mido.Message('note_on', channel=9, note=71, velocity=100)),
           (3.0, mido.Message('note_off', channel=9, note=71, velocity=0)),
           (3.3, mido.Message('program_change', channel=9, program=24))]
    for i, v in enumerate((100, 70, 120)):
        ev += [(3.5 + 0.6 * i, mido.Message('note_on', channel=9, note=40, velocity=v)),
               (3.6 + 0.6 * i, mido.Message('note_off', channel=9, note=40, velocity=0))]
    ev.append((5.4, mido.Message('program_change', channel=9, program=16)))
    for i, v in enumerate((110, 80)):
        ev += [(5.6 + 0.6 * i, mido.Message('note_on', channel=9, note=38, velocity=v)),
               (5.7 + 0.6 * i, mido.Message('note_off', channel=9, note=38, velocity=0))]
    ev.append((7.2, mido.Message('control_change', channel=9, control=7, value=100)))
    return _timed(ev)


def couplers(variation, steps):
    """A 60's organ manual (bank 16, program 16: 16 the upper's 60's Organ 1, 41
    the lower) holding a chord from 0.3 s while its COUPLER SWITCHES change
    (CC87, tonelib.COUPLER_CC: 1 8' Off, 2 16', 4 4', 8 2') at each step's
    time, a second chord struck at 5 s under the last; all off at 7.5 s."""
    mid, tr = one_track()
    ev = [(0.0, mido.Message('control_change', channel=0, control=0, value=variation)),
          (0.0, mido.Message('program_change', channel=0, program=16))]
    for k in (60, 64, 67):
        ev += [(0.3, mido.Message('note_on', channel=0, note=k, velocity=100)),
               (7.5, mido.Message('note_off', channel=0, note=k, velocity=0))]
    ev += [(5.0, mido.Message('note_on', channel=0, note=72, velocity=100)),
           (7.5, mido.Message('note_off', channel=0, note=72, velocity=0))]
    for at, v in steps:
        ev.append((at, mido.Message('control_change', channel=0, control=87, value=v)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960))
        msg.time = tk - now
        now = tk
        tr.append(msg)
    return mid


def clav_compass():
    """GM 7, the Clavinet, F1 to E6 a fourth apart at three velocities, then
    a chord: the published stiffness table and the wound/plain length law
    (tonelib.ClavinetProperties, native b_law 5) over the whole compass."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=7, time=0))
    for v in (40, 90, 127):
        for n in range(29, 89, 5):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=0))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=240))
    for n in (36, 48, 55, 64, 70, 88):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=0))
    tr.append(mido.Message("note_off", channel=0, note=36, velocity=0, time=1440))
    for n in (48, 55, 64, 70, 88):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    return mid


def feedback_held():
    """GS 30.8 and 31.8, the guitar held into feedback: notes across the
    compass held 3 s each (tonelib.Feedback._fb_table: the loop's partial by
    key, native fb_k), the distorted variation, then the clean one."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    for prog in (30, 31):
        tr.append(mido.Message("control_change", channel=0, control=0, value=8, time=0))
        tr.append(mido.Message("program_change", channel=0, program=prog, time=0))
        for n in (40, 45, 52, 57, 65, 76):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=120))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=1440))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def dulcimer_compass():
    """GM 15, the hammered dulcimer, D3 to F6 (its bass bridge's table by key,
    native b_law 4 with btab; its treble law; its bridge partners), each key
    left to ring under the next, then a chord."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=15, time=0))
    for n in (50, 52, 54, 55, 56, 57, 59, 62, 66, 69, 74, 79, 84, 89):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=480))
    for n in (50, 57, 62, 66):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=0))
    tr.append(mido.Message("note_off", channel=0, note=50, velocity=0, time=1920))
    for n in (57, 62, 66):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    return mid


def flugel_phrase():
    """GS 56.8, the flugelhorn: a phrase E3-C6 at three velocities -- its
    attack slower than the trumpet's, its upper harmonics later
    (speech_harmonic_exp, native sh_exp on a wind voice)."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("control_change", channel=0, control=0, value=8, time=0))
    tr.append(mido.Message("program_change", channel=0, program=56, time=0))
    for v in (50, 90, 120):
        for n in (52, 60, 67, 72, 79, 84):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=60))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=420))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def mandolin_compass():
    """GS 25.16-18, the mandolins: single notes G3-A6 at three velocities, then
    a chord (its courses, pick, open courses kicked through the bridge), on
    Mandolin, Mandolin 2 and MandolinTrem."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    for bank in (16, 17, 18):
        tr.append(mido.Message("control_change", channel=0, control=0, value=bank, time=0))
        tr.append(mido.Message("program_change", channel=0, program=25, time=0))
        for v in (40, 85, 125):
            for n in (55, 62, 69, 76, 81, 88, 93):
                tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=30))
                tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=330))
        for n in (55, 62, 71, 79):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=90, time=10))
        tr.append(mido.Message("note_off", channel=0, note=55, velocity=0, time=900))
        for n in (62, 71, 79):
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def guitar12_compass():
    """GS 25.8, the 12-string: single notes E2-C6 at three velocities (the
    octave courses below B3, the unison ones from it), then an open chord."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("control_change", channel=0, control=0, value=8, time=0))
    tr.append(mido.Message("program_change", channel=0, program=25, time=0))
    for v in (45, 90, 125):
        for n in (40, 47, 55, 59, 64, 71, 76, 84):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=30))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=420))
    for n in (40, 47, 52, 56, 59, 64):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=95, time=15))
    tr.append(mido.Message("note_off", channel=0, note=40, velocity=0, time=1400))
    for n in (47, 52, 56, 59, 64):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def hawaiian_compass():
    """GS 26.8, the lap steel: single notes E2-C6 at three velocities, long
    (its sustain), then an open-E chord (its open strings' sympathy)."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("control_change", channel=0, control=0, value=8, time=0))
    tr.append(mido.Message("program_change", channel=0, program=26, time=0))
    for v in (45, 90, 125):
        for n in (40, 52, 59, 64, 71, 76, 84):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=30))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=600))
    for n in (40, 47, 52, 56, 59, 64):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=95, time=10))
    tr.append(mido.Message("note_off", channel=0, note=40, velocity=0, time=2400))
    for n in (47, 52, 56, 59, 64):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def gopichant_compass():
    """GS 105.16, the gopichand: single notes C3-C5 at three velocities --
    its scoop (tension_log, by the stroke), its short ring on the skin."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("control_change", channel=0, control=0, value=16, time=0))
    tr.append(mido.Message("program_change", channel=0, program=105, time=0))
    for v in (40, 90, 127):
        for n in (48, 52, 55, 60, 64, 67, 72):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=30))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=420))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def tonewheel_spinet():
    """GM 16 and 17: the drawbar organ through its own speaker (the spinet's
    paper cone, its breakup), 888 000 000's 16' and 5 1/3' -- chords; then the
    percussive organ's tap, detached notes (the circuit's fast decay)."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=16, time=0))
    for chord in ((48, 55, 64), (53, 60, 69), (43, 59, 67, 74)):
        for n in chord:
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=0))
        tr.append(mido.Message("note_off", channel=0, note=chord[0], velocity=0, time=900))
        for n in chord[1:]:
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.Message("program_change", channel=0, program=17, time=120))
    for n in (48, 55, 60, 67, 72, 79):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=60))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=420))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def harpsi_four():
    """GM 6 with its 4' drawn (CC11 stop word 0b0101: the lower 8' + 4'), then
    the 4' alone (0b0100): single notes F2-F6 and a chord."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=6, time=0))
    for word in (0b0101, 0b0100):
        tr.append(mido.Message("control_change", channel=0, control=11, value=word, time=60))
        for n in (41, 53, 65, 77, 89):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=90, time=30))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=420))
        for n in (53, 60, 65, 69):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=90, time=0))
        tr.append(mido.Message("note_off", channel=0, note=53, velocity=0, time=900))
        for n in (60, 65, 69):
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def eguitars_six():
    """GM 26-31 refitted to Guitar-TECHS and physics (licences.md L2), each on
    its own channel in turn -- single notes E2-E5 at two velocities, then a
    chord (the drive) -- and GS 30.24, Rock Rhythm (palm_mute's 0.3, the
    interpolation between GM 30 and GM 28)."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    parts = [(ch, 26 + ch, 0) for ch in range(6)] + [(6, 30, 24)]
    for ch, prog, bank in parts:
        tr.append(mido.Message("control_change", channel=ch, control=0, value=bank, time=0))
        tr.append(mido.Message("program_change", channel=ch, program=prog, time=0))
    for ch, prog, bank in parts:
        lo = 52 if prog == 31 else 40
        for v in (60, 115):
            for n in (lo, lo + 12, lo + 24, 76):
                tr.append(mido.Message("note_on", channel=ch, note=n, velocity=v, time=20))
                tr.append(mido.Message("note_off", channel=ch, note=n, velocity=0, time=300))
        ch_notes = (40, 47, 52, 55, 59, 64)
        for n in ch_notes:
            tr.append(mido.Message("note_on", channel=ch, note=n, velocity=100, time=8))
        tr.append(mido.Message("note_off", channel=ch, note=ch_notes[0], velocity=0, time=960))
        for n in ch_notes[1:]:
            tr.append(mido.Message("note_off", channel=ch, note=n, velocity=0, time=0))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def basses_all():
    """GM 33-37, each on its own channel in turn (licences.md L3: the string
    from its physics, the hands from open recordings, slap and pop against
    the frets) -- E1 to G3 at three velocities, a held note each (its decay)
    and its damp."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    for ch in range(5):
        tr.append(mido.Message("program_change", channel=ch, program=33 + ch, time=0))
    for ch in range(5):
        for v in (40, 90, 125):
            for n in (28, 35, 40, 47, 55):
                tr.append(mido.Message("note_on", channel=ch, note=n, velocity=v, time=20))
                tr.append(mido.Message("note_off", channel=ch, note=n, velocity=0, time=260))
        tr.append(mido.Message("note_on", channel=ch, note=33, velocity=100, time=10))
        tr.append(mido.Message("note_off", channel=ch, note=33, velocity=0, time=1440))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def rhodes_compass():
    """GM 4, the Rhodes rebuilt in millimetres (licences.md L1): E1-E7 at
    three velocities (the swing linear in the hammer, the bark at forte), a
    held bass note (its h1 building), then a chord with the suitcase's
    vibrato (CC1)."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=4, time=0))
    for v in (40, 85, 125):
        for n in (28, 40, 52, 64, 76, 88, 100):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=20))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=300))
    tr.append(mido.Message("note_on", channel=0, note=29, velocity=110, time=10))
    tr.append(mido.Message("note_off", channel=0, note=29, velocity=0, time=1920))
    tr.append(mido.Message("control_change", channel=0, control=1, value=90, time=0))
    for n in (48, 55, 60, 64, 67):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=90, time=8))
    tr.append(mido.Message("note_off", channel=0, note=48, velocity=0, time=1920))
    for n in (55, 60, 64, 67):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


def biwa_compass():
    """GS 120.12, the biwa on its sawari (licences.md L4: SawariContact, its
    baked table): A2-A5 at two velocities, each left to ring (the fed share's
    slow fall), then a low note held."""
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.Message("control_change", channel=0, control=0, value=12, time=0))
    tr.append(mido.Message("control_change", channel=0, control=32, value=0, time=0))
    tr.append(mido.Message("program_change", channel=0, program=120, time=0))
    for v in (60, 120):
        for n in (45, 52, 57, 64, 69, 76, 81):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=20))
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=480))
    tr.append(mido.Message("note_on", channel=0, note=45, velocity=110, time=10))
    tr.append(mido.Message("note_off", channel=0, note=45, velocity=0, time=1920))
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=960))
    return mid


MAKERS = {"gu_refits_tones": gu_refits_tones, "gu_refits_kits": gu_refits_kits, "taisho_course": taisho_course, "harmonium_grandjeu": harmonium_grandjeu, "harmonium_onset": harmonium_onset, "harmonium_prolong": harmonium_prolong, "harmonium_boxes": harmonium_boxes, "harmonium_wind": harmonium_wind, "harmonium_stops": harmonium_stops, "biwa_compass": biwa_compass, "rhodes_compass": rhodes_compass, "basses_all": basses_all, "eguitars_six": eguitars_six, "stab_chords": stab_chords, "harpsi_four": harpsi_four, "tonewheel_spinet": tonewheel_spinet, "gopichant_compass": gopichant_compass, "hawaiian_compass": hawaiian_compass, "guitar12_compass": guitar12_compass, "flugel_phrase": flugel_phrase, "mandolin_compass": mandolin_compass, "dulcimer_compass": dulcimer_compass, "feedback_held": feedback_held, "clav_compass": clav_compass,
          "couplers_upper": lambda: couplers(16, ((1.5, 0), (2.5, 1 | 4), (3.5, 2), (4.5, 2 | 4 | 8), (6.0, 1 | 2 | 8))),
          "couplers_lower": lambda: couplers(41, ((1.5, 4), (3.0, 1 | 4), (4.5, 0), (6.0, 4))), "spectra_rotor": lambda: spectra(10), "spectra_chorus": lambda: spectra(11),
          "spectra_sustain": lambda: spectra_sustain(10), "spectra_sustain_chorus": lambda: spectra_sustain(11), "dense_pedal": dense_pedal, "assign_mode": assign_mode, "mpe_organ": lambda: mpe_zone(19), "cmx_live": cmx_live, "userdrums": userdrums, "drumdelay": drumdelay, "moog_cmx": moog_cmx, "two_organs": two_organs, "rhythmpart": rhythmpart, "gsrx_2port": gsrx_2port, "drumnrpn": drumnrpn, "drumnrpn2": drumnrpn2, "gsvsense": gsvsense,
          "mpe_zone": mpe_zone}


def main(argv):
    want = set(argv)
    for name, fn in MAKERS.items():
        if not want or name in want:
            fn().save(os.path.join(MIDI, name + ".mid"))
            print(name)
    for name, fn in M2_MAKERS.items():
        if not want or name in want:
            save_m2(name, fn())
            print(name + ".midi2")
    for src, name, raw in M2_CONVERTED:
        if not want or name in want:
            import ump as U
            U.midi1_to_clip(mido.MidiFile(os.path.join(MIDI, src + ".mid")), os.path.join(MIDI, name + ".midi2"),
                            raw=raw)
            print(name + ".midi2")
    os.makedirs(os.path.join(MIDI, "mpe"), exist_ok=True)
    for name, ex in MPE_VARIANTS.items():
        if not want or name in want or "mpe" in want:
            _mpe_variant(ex).save(os.path.join(MIDI, "mpe", name + ".mid"))
            print("mpe/" + name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
