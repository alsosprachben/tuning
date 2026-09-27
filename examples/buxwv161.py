#!/usr/bin/env python3
"""Buxtehude, Passacaglia in D minor BuxWV 161 -- as one long crescendo.

    python3 examples/buxwv161.py SCORE.mid [outdir]

SCORE is the four-channel score (buxtehude_passacaglia_registered.mid): 0 the
manual, 1 the pedal, 2 the pedal reed, 3 the manual reed. The reed channels
were written for program 20 when that was the reed organ; the reeds are on the
console now (GM 19, bits 8-11) and 20 is the harmonium, so every channel is
put on 19 here and the reeds drawn by their console names.

A passacaglia is not registered once and played. It is built: the organist
starts on the Positiv and adds through the piece, so the ostinato that opens
almost inaudibly is thundering by the close. BWV 582 is played this way by
everybody, and so is this.

The structure does the scheduling. The pedal states its 7-note ostinato 28
times, in four groups of seven, transposed D - F - A - D, each statement
10.9 seconds:

    D  var  1   1.8 s      A  var 15  170.9 s
    F  var  8  86.4 s      D  var 22  255.5 s

Registration changes go AT THE KEY CHANGES, which is where an organist puts
them, plus one at the four-voice chordal transition into the final section.
Nothing is ever taken away, which is what makes it a crescendo rather than a
sequence of registrations.

THE FIRST BRIGHTENING ADDS NOTHING. D minor is a stopped flute over a stopped
pedal; F major moves BOTH to the principal 8'. No rank is drawn -- a stopped
pipe and an open one are different sounds at the same pitch and the same
count, so the change of colour IS the change. Everything after that is
accumulation, and it can be because this step was not.

THE OPENING PEDAL IS THE STOPPED RANK, and the reason is measurable. A stopped
pipe has no even harmonics: on D2 its second partial is 132 dB down, so it is
very nearly the fundamental alone, which is what a Positiv registration wants
under it. The open principal is the opposite -- a full series with the second
only 6 dB down -- and the church's two first-order images land destructively
on that second partial (0.469 and 0.200, so 1 - 0.669 = -9.6 dB) and take it
out. What is left is a strong fundamental, no second, and a third at -9 dB,
which is within a decibel of the REED's own spectrum. Ben heard the opening
pedal as a reed and it was one, in every way that a spectrum can be.

UNDER IT, THE BOURDON 16'. Stopped 16' + stopped 8' is the classic quiet pedal:
the octave below gives the ground a floor without any of the open rank's
brightness. Nothing is taken away, so it stays drawn to the end.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import organ

# The seams, taken from the ostinato and from the texture.
#
# CHANGES GO AT THE KEY CHANGES. That is where an organist puts them, and the
# structure is built for it: the ostinato states itself 28 times in four groups
# of seven, transposed D - F - A - D. Changing inside a group instead puts a
# stop in the middle of a statement, which is the one place it never goes.
KEY = {'D1': 1.8, 'F': 86.4, 'A': 170.9, 'D2': 255.5}

# ...with one addition that is not a key change. Four-voice quarter-note chords
# arrive at 249.5 s and run to the D return -- measured, 4.1 voices at 487 ms,
# the steadiest stacked writing in the piece. It is a cadenza made of weight
# rather than of runs, and it is the approach to the final section, so the
# blaze starts there and arrives rather than switching on at the double bar.
WALL = 249.5
LAST = 320.9          # the 28th and final statement
# WHERE IN THE BAR A STOP IS DRAWN, and it is not a matter of taste.
#
# Drawing a stop while a note is held makes that note louder -- which is what
# a real organ does too, and is why an organist changes between notes. At
# 0.35 s before the downbeat, which is where this used to sit, EIGHT notes of
# the previous variation were still sounding and ended a quarter-second later:
# the old section's last chord swelled and stopped. Ben heard it as "the last
# note gets suddenly loud".
#
# Measured across the seams, anything from -100 ms to +50 ms catches ZERO
# held notes; -200 ms and earlier catches eight. The texture never rests --
# four voices minimum, all the way through -- so there is no silence to change
# in, only the instant where the old chord has released and the new has not
# yet spoken. 50 ms before the downbeat is inside that window and still leaves
# the controller ahead of the note-ons it applies to.
LEAD = 0.05


_SPANS = None


def at_raw(t):
    """When to draw, given what is sounding -- see lib.release_seam."""
    if _SPANS is None:
        return max(0.0, t - LEAD)
    return max(0.0, lib.release_seam(_SPANS, t))


RAW = {
    # manual flue
    0: [(0.0,           ['flute 8']),                              # Positiv
        (KEY['F'],  ['principal 8']),                                  # first brightening
        (KEY['A'],  ['principal 8', 'octave 4', 'super octave 2', 'quint 2-2/3']),
        (WALL,      ['principal 8', 'octave 4', 'super octave 2', 'quint 2-2/3', 'mixture III']),
        (KEY['D2'], ['principal 8', 'octave 4', 'super octave 2', 'quint 2-2/3', 'principal 16', 'quint 5-1/3', 'mixture III'])],
    # pedal flue
    1: [(0.0,           ['bourdon 16', 'flute 8']),               # stopped, not open
        (KEY['F'],  ['bourdon 16', 'principal 8']),                    # principal, with the manual
        (KEY['A'],  ['bourdon 16', 'principal 16', 'principal 8', 'octave 4']),
        (KEY['D2'], ['bourdon 16', 'principal 16', 'principal 8', 'octave 4', 'quint 5-1/3'])],
    # pedal reed: the weight, entering with the wall
    2: [(0.0,           []),
        (WALL,      ['reed 16']),
        (KEY['D2'], ['reed 16', 'reed 8'])],
    # manual reed: the last statement only
    3: [(0.0,           []),
        (LAST,      ['trumpet 8'])],
}


# THE ENCORE. The chords before the return are played as an encore: the
# variation before them slows into its half cadence on A, the organ stops
# long enough for the church to mostly empty, and the chords begin a tempo
# out of the quiet. The reed 16' and the Mixtur are drawn IN the pause, the
# one moment in the piece with nothing sounding to catch.
#
# The pause is the room's, measured: after the release the church tail is
# 27 dB down at 0.55 s and 42 dB down at 1.05 s, so 1.3 s is "mostly
# drained" without the thread snapping.
#
# And the piece ends with a ritardando through the last statement's cadence,
# its final chord held at the slower tempo.
#
# (start, end, tempo reached at end, whether it holds after): the tempo falls
# linearly across the window. Times are the score's own seconds, and on the
# beat exactly (132 bpm): a pause a hair late of the chord it precedes puts
# the chord in front of it.
BEAT = 0.454545
ENCORE = 549 * BEAT                  # the first chord, in the score
RITS = [(540 * BEAT, ENCORE, 0.75, False),    # the bar of the half cadence
        (720 * BEAT, 732 * BEAT, 0.70, True)] # the last run into the final chord
PAUSES = [(ENCORE, 1.3)]

# THE TEMPO. The file says 132, but that is the eighth: the beat is the quarter
# at 66, a bar of 3/4 every 2.7 s, and the piece ran 5:37. Recordings run 5:09
# (Viderø) to 6:43 (Havinga), median about 6:10; Ben heard it a little fast and
# asked for 4 bpm slower. At quarter = 62 it is about 5:58. Applied in the
# time map, so every time above stays in the score's own seconds.
SLOW = 66.0 / 62.0


def _stretch(a, b, lo, hold, t):
    """Extra seconds a rit adds up to score time t: the tempo r(u) falls
    linearly from 1 to lo across [a, b], and time is the integral of 1/r."""
    if t <= a:
        return 0.0
    k = (1.0 - lo) / (b - a)
    u = min(t, b) - a
    extra = -math.log(1.0 - k * u) / k - u
    if hold and t > b:
        extra += (t - b) * (1.0 / lo - 1.0)
    return extra


def warp_time(t, pre_pause=False):
    """Score seconds -> performed seconds. A note-off exactly AT a pause
    belongs before it (pre_pause); everything else there comes after."""
    out = SLOW * (t + sum(_stretch(a, b, lo, hold, t) for a, b, lo, hold in RITS))
    for p, dur in PAUSES:
        if t > p + 1e-4 or (abs(t - p) <= 1e-4 and not pre_pause):
            out += dur
    return out


def perform(src, dest):
    """The rits and the pause, written into the score's ticks at its one tempo
    (set_stops reads seconds off a single tempo, so the tempo map stays flat).
    A note held across a pause is cut there and struck again after it: the
    pedal A under the half cadence, which restarts with the first chord."""
    import mido
    m = mido.MidiFile(src)
    tempo = next((e.tempo for t in m.tracks for e in t if e.type == 'set_tempo'), 500000)
    spt = tempo / 1e6 / m.ticks_per_beat
    for ti, t in enumerate(m.tracks):
        ev, acc = [], 0
        for e in t:
            acc += e.time
            off = e.type == 'note_off' or (e.type == 'note_on' and e.velocity == 0)
            ev.append((acc * spt, off, e, len(ev)))
        # cut what is held when a pause arrives, and strike it again after,
        # unless the music strikes it there anyway. Counted, not paired: a
        # voice here can hold a note and strike it again before releasing it.
        extra = []
        for p, _ in PAUSES:
            held = {}
            for sec, off, e, _ in ev:
                if sec > p - 1e-4 and not (off and sec <= p + 1e-4):
                    break
                if e.type in ('note_on', 'note_off'):
                    key = (e.channel, e.note)
                    held[key] = held.get(key, 0) + (-1 if off else 1)
            struck = {(e.channel, e.note) for sec, off, e, _ in ev
                      if abs(sec - p) <= 1e-4 and e.type == 'note_on' and not off}
            for (ch, n), c in held.items():
                for _ in range(max(0, c)):
                    extra.append((p, True, mido.Message('note_off', channel=ch, note=n, velocity=0), -2))
                if c > 0 and (ch, n) not in struck:
                    extra.append((p, False, mido.Message('note_on', channel=ch, note=n, velocity=64), -1))
        ev += extra
        # by performed time, and within a tick in the file's own order: a
        # repeated note is written as its new Note On ahead of the old Note Off
        out = sorted(((int(round(warp_time(sec, pre_pause=off) / spt)), k, e)
                      for sec, off, e, k in ev), key=lambda r: (r[0], r[1]))
        nt = mido.MidiTrack(); last = 0
        for tick, _, e in out:
            nt.append(e.copy(time=tick - last)); last = tick
        m.tracks[ti] = nt
    m.save(dest)
    return dest


def to_console(src, dest):
    """Every channel on the console, GM 19: the reeds are its bits 8-11."""
    import mido
    m = mido.MidiFile(src)
    for t in m.tracks:
        for i, e in enumerate(t):
            if e.type == 'program_change' and e.program != 19:
                t[i] = e.copy(program=19)
    m.save(dest)
    return dest


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip()); return 2
    outdir = argv[2] if len(argv) > 2 else '.'
    os.makedirs(outdir, exist_ok=True)
    score = to_console(argv[1], os.path.join(outdir, 'buxwv161_console.mid'))
    global _SPANS, PLAN
    score = perform(score, os.path.join(outdir, 'buxwv161_performed.mid'))
    _SPANS = lib.note_spans(score)
    quiet = warp_time(ENCORE, pre_pause=True) + PAUSES[0][1] / 2
    PLAN = {ch: [(quiet if t == WALL else at_raw(warp_time(t)), ns) for t, ns in spec]
            for ch, spec in RAW.items()}
    graded = os.path.join(outdir, 'buxwv161_graded.mid')
    lib.set_stops(score, graded, PLAN)
    return organ.main([argv[0], graded, outdir])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
