#!/usr/bin/env python3
"""A metal arrangement of a WTC fugue (Ben's idea: Book 2's F minor; then the
E minor, wtc2f10, by the same method -- --effects).

    python3 examples/wtc_metal.py [wtc2f12] [--bpm 84]
    python3 examples/wtc_metal.py [wtc2f12] --chord-out    # no rhythm part: the leads
                                                           # chord out where they meet
    python3 examples/wtc_metal.py [wtc2f12] --one-guitar   # ONE distorted guitar plays
                                                           # both upper voices, let ring
    python3 examples/wtc_metal.py [wtc2f12] --trade        # TWO distortion guitars: the top
                                                           # and the bottom, trading the middle
    python3 examples/wtc_metal.py [wtc2f12] --manual       # ...traded by hand, passage by
                                                           # passage (MANUAL below)
    python3 examples/wtc_metal.py [wtc2f12] --manual --drums metal|fusion
    python3 examples/wtc_metal.py [wtc2f12] --effects      # the hand-traded guitars with
                                                           # slides, vibrato, entry scoops
    python3 examples/wtc_metal.py [wtc2f12] --effects --room-mics   # ...each amp with a
                                                           # close mic and a room mic

From the urtext's notation MIDI (wtc_fugue.py writes it), in strict time --
no baroque rubato; metal is tight:

  bass voice      FRETLESS BASS (GM 35), an octave down -- a 5-string, whose
                  low B takes the fugue's C2 as C1. Centre.
  upper voices    OVERDRIVEN GUITAR (GM 29), CC1 = 127: offline CC1 is the
                  amp's gain knob, drive = amp_drive x 4 x CC1/127, so 4.45
                  becomes ~18 -- past the distortion guitar's own 14.4. Alto
                  left of centre, soprano right.
  power chords    DISTORTION GUITAR (GM 30), double-tracked hard left and
                  right as metal rhythm guitars are, voiced root-fifth-octave
                  in the low guitar register (E2-D#3), chugging eighths, the
                  beat accented; the second track a few ms late and a touch
                  softer, which is what double-tracking is. The ROOT is the
                  beat's HARMONY: every sounding note weighted by how long it
                  sounds (the bass note double), the best-fitting major or
                  minor triad, the previous root kept unless another fits
                  clearly better. The first pass took the lowest note sounding,
                  which in a fugue is as often a passing tone as a root, and
                  the chords wandered with the voice-leading (Ben: "not sure
                  where they come from"). The chart is written beside the mix.

A MIX, as qkbttl02's is: the bass, the leads and the power chords rendered
apart and summed at loudness targets (lib.loudness), the leads on top. In one
render six distorted notes a chug buried two single-note leads.

Equal temperament (frets), the studio room, the amps close-miked. Writes
~/Downloads/bwx-renders/wtc/<name>_metal.{mid,mp3}.
"""
import math
import os
import sys

TARGETS = {'leads': 0.0, 'bass': -2.0, 'chords': -6.0}      # dB against the leads
# THE KEY'S OWN ROOTS, preferred: a chromatic root has to be clearly supported
# by the notes to win. F minor's, with the raised seventh (E) for its dominant.
KEYS = {'wtc2f12': {5, 7, 8, 10, 0, 1, 3, 4}, 'wtc2f10': {4, 6, 7, 9, 11, 0, 2, 3},
        'wtc2f04': {1, 3, 4, 6, 8, 9, 11, 0}}
# EACH FUGUE'S METER AND PICKUP, in quarters, and its tempo. The E minor is
# in 2/2 from a quarter's upbeat; CCARH's *MM130 runs it in 2:39, where a
# recording runs 3:00 -- 116. The C# minor is 12/16, a bar of three quarters;
# its *MM84 would run 2:32 where the fugue takes about two minutes -- a dotted
# eighth at 72, ♩=108.
METER = {'wtc2f12': 2, 'wtc2f10': 4, 'wtc2f04': 3}
PICKUP = {'wtc2f10': 1}
BPM = {'wtc2f12': 84.0, 'wtc2f10': 116.0, 'wtc2f04': 108.0}
# THE VOICES' CHANNELS: 0 bottom, 1 middle, 2 top. Where the kern splits a
# voice for a chord it writes the extra notes on channels 3 and up; each goes
# to the voice sounding nearest it in pitch, unless the piece says otherwise.
VOICE_OF = {'wtc2f12': {0: 0, 1: 1, 2: 2, 3: 2}}
NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

# THE FUGUE'S ARCHITECTURE, for the drums: where the subject enters, and the
# bars that lead into an entry (the fills). Bars 1-4 are the subject alone.
STRUCTURE = {'wtc2f12': dict(entries=(5, 12, 29, 41, 51, 75), fills=(28, 50, 74),
                             bass_subject=((12, 17), (41, 42)),
                             climax=((43, 49), (79, 84)), full_from=12)}
KIT = {'metal': 16, 'fusion': 8}          # GM drum sets: Power, Room
DRUM_TARGET = {'metal': -3.0, 'fusion': -5.0}


def drums(style, st, ns, tpb, nbar, note):
    """The drum part, from the fugue's structure (see STRUCTURE).

    metal   the kit builds in with the voices; crash on every entry; closed
            hi-hat under the entries, ride in the episodes; the kick locks to
            the bottom guitar where it has the subject; half-time snare on
            beat 2; double kick only in the climaxes; tom fills into entries.
    fusion  the ride is the time, straight eighths, the bell on entries; hi-hat
            foot on the beats; cross-stick instead of a backbeat, ghost notes
            between; a light kick that answers; toms at the cadences."""
    bar, s16 = 2 * tpb, tpb // 4
    D = 9
    def hit(n, step, b, v):
        note(D, n, b * bar + step * s16, b * bar + step * s16 + s16, max(1, min(127, v)))
    inside = lambda b1, spans: any(a <= b1 <= z for a, z in spans)
    entries = set(st['entries'])
    since = 0
    for b in range(nbar):
        b1 = b + 1
        if b1 < st['entries'][0]:
            continue                                   # the subject alone
        light = b1 < st['full_from']
        if b1 in entries:
            since = 0
        episode = since >= 4 and b1 not in entries
        since += 1
        if b1 >= nbar:                                 # the final chord's bar
            hit(49, 0, b, 118); hit(57, 0, b, 110); hit(36, 0, b, 118)
            continue
        if b1 in st['fills'] and not light:
            toms = (50, 50, 48, 48, 47, 47, 45, 41) if style == 'metal' else (48, 38, 47, 38, 45, 38, 41, 38)
            for k, t in enumerate(toms):
                hit(t, k, b, (100 if style == 'metal' else 72) + (8 if k % 2 == 0 else 0))
            hit(36, 0, b, 100 if style == 'metal' else 70)
            continue
        if style == 'metal':
            if b1 in entries:
                hit(49, 0, b, 115)
            cym = 51 if episode else 42
            for k in range(0, 8, 2):
                if not (k == 0 and b1 in entries):
                    hit(cym, k, b, (95 if k % 4 == 0 else 75) - (30 if light else 0))
            if light:
                hit(36, 0, b, 70)
                continue
            hit(38, 4, b, 110)                           # half-time: beat 2
            if inside(b1, st['climax']):
                for k in range(8):
                    hit(36, k, b, 92 if k % 2 == 0 else 78)
            elif inside(b1, st['bass_subject']):
                for s_, e_, c_, n_ in ns:                  # the kick on the bottom guitar's notes
                    if c_ == 0 and b * bar <= s_ < (b + 1) * bar:
                        note(D, 36, s_, s_ + s16, 96)
            else:
                hit(36, 0, b, 100); hit(36, 3, b, 85)
        else:
            if b1 in entries:
                hit(49, 0, b, 92); hit(53, 0, b, 90)
            for k in range(0, 8, 2):
                if not (k == 0 and b1 in entries):
                    hit(53 if (k == 0 and episode) else 51, k, b, (74 if k % 4 == 0 else 60) - (20 if light else 0))
            hit(44, 0, b, 55); hit(44, 4, b, 55)       # hi-hat foot
            if light:
                continue
            hit(37, 4, b, 80)                             # cross-stick
            hit(38, 3, b, 32); hit(38, 7, b, 36)          # ghost notes
            hit(36, 0, b, 72); hit(36, 6, b, 58)          # a light, answering kick


# WHICH VOICE CARRIES EACH SUBJECT ENTRY (for the scoop into it): 0 bottom,
# 1 middle, 2 top.
ENTRY_VOICE = {'wtc2f12': {1: 2, 5: 1, 12: 0, 29: 1, 41: 0, 51: 1, 75: 1},
               'wtc2f10': {1: 2, 7: 1, 13: 0, 24: 2, 30: 1, 42: 0, 50: 1, 60: 2, 72: 0},
               # 48 (top) and 55 (bass) come in off a tied note, on the lower
               # neighbour: no scoop there
               'wtc2f04': {1: 0, 2: 2, 5: 1, 16: 2, 17: 1, 20: 0, 30: 1, 61: 1, 66: 1}}


def guitar_mpe(notes, tpb, bpm, prog, pan, path, scoops):
    """One guitar as an MPE zone, with a guitarist's pitch.

    notes: [(start, end, voice, midi note)] in ticks, one guitar's. Each note
    gets a member channel so its pitch moves alone; the zone is ONE instrument
    (blockrender tags member notes with the manager, so both strings share one
    amplifier and intermodulate in it). Three effects, all pitch, no new notes:

      SLIDE    within a voice, a note leaping 3-7 semitones into a note at least
               twice as long slides into it, and the target is RE-PICKED on its
               own beat while the slide is still landing (Ben) -- a position
               shift on one string. A FRETTED slide (fret_slide): the hand moves
               evenly along the string, easing in and out, the frets turn that
               into a chromatic staircase, which quickens going up the neck
               where they crowd, and it takes ~28 ms a fret. The first version
               glided smoothly in pitch over a fixed 60 ms, a fretless sound.
      VIBRATO  a held note (0.54 s or more) gets finger vibrato after
               ~120 ms: UPWARD, as a guitar's is, growing to +35 cents at 5.5 Hz.
      SCOOP    the first note of each subject entry comes up from a tone below --
               on the WHAMMY BAR, so smooth: the bar pre-dipped and released,
               springing back fast and settling (an ease-out over ~90 ms). A
               bar knows no frets; a finger does (Ben).
    """
    import math as _m
    tps = tpb * bpm / 60.0                        # ticks per second
    # 45 ms a fret, and fully fretted: at 28 ms a fret with a quarter of the
    # glide blended in, the frets were not heard (Ben) -- measured, the
    # renderer holds a pitch step to within ~10 ms, which is all the rounding
    # a fretted slide needs, so the steps are left whole and given time.
    FRET_S, HOME = 0.045, 5                       # seconds a fret; the fret a slide starts near

    def fret_curve(t_beat, n, dep_len):
        """A fretted slide of n semitones around the target's beat t_beat:
        [(tick, semitones above the departure note)]. The hand's place along
        the string, d = 1 - 2^(-fret/12), moves on an eased S-curve; the pitch
        is the fret under the finger (quantised -- the renderer's own ~10 ms
        settling is the rounding). ~45 ms a fret; 40% of it before the beat,
        never more than 60% of the departure note, the rest after the pick."""
        w = FRET_S * abs(n) * tps + 0.02 * tps
        pre = min(0.4 * w, 0.6 * dep_len)
        t0 = t_beat - pre
        p0 = HOME + (0 if n > 0 else abs(n))       # stay on the neck either way
        d = lambda f: 1.0 - 2.0 ** (-f / 12.0)
        d0, d1 = d(p0), d(p0 + n)
        step = 0.004 * tps
        out, k, last = [], 0, None
        while k * step <= w:
            x = k * step / w
            x = x * x * (3 - 2 * x)
            semi = round(-12.0 * _m.log2(1.0 - (d0 + (d1 - d0) * x))) - p0
            if semi != last:
                out.append((t0 + k * step, float(semi))); last = semi
            k += 1
        out.append((t0 + w, float(n)))
        return out
    RANGE = 48.0                                  # the MPE member bend range
    # A NOTE HELD LONG ENOUGH TO VIBRATE, in seconds -- a hand's time, not the
    # beat's: a dotted eighth at the F minor's 84. Counted in beats, the E
    # minor's 116 gave every quarter note vibrato (330 notes against 67).
    VIB_S = 0.75 * 60.0 / 84.0
    by_voice = {}
    for n in sorted(notes):
        by_voice.setdefault(n[2], []).append(n)
    # SLIDES, and the note is RE-PICKED on its own beat (Ben): the finger leaves
    # before the beat, the target is picked ON it while the slide is still
    # landing, and finishes the frets from there. So every note stays a note;
    # a slide is a staircase shared between two of them.
    slide_in, slide_out = {}, {}                  # note -> (curve, the other note)
    for v, seq in by_voice.items():
        for a, b in zip(seq, seq[1:]):
            iv = b[3] - a[3]
            if b[0] - a[1] <= tpb // 16 and 3 <= abs(iv) <= 7 and (b[1] - b[0]) >= 2 * (a[1] - a[0]):
                curve = fret_curve(b[0], iv, a[1] - a[0])
                slide_out[a], slide_in[b] = curve, curve
    ev = []
    def pb(ch, t, st):
        ev.append((int(round(t)), 1, mido.Message('pitchwheel', channel=ch,
                                                   pitch=max(-8192, min(8191, int(round(st * 8192 / RANGE)))))))
    free_at = {c: 0 for c in range(1, 16)}
    slides = vibs = scooped = 0
    dt = 0.010 * tps                              # a bend event every 10 ms
    for n in sorted(notes):
        s0, e0, v, n0 = n
        ch = min(free_at, key=lambda c: free_at[c] if free_at[c] <= s0 else 1e18 + free_at[c])
        free_at[ch] = e0 + 1
        curve_in = slide_in.get(n)
        # where the pitch stands at the pick: mid-slide, or the whammy's dip
        start = 0.0
        if curve_in:
            iv = n0 - next(a for a, c in slide_out.items() if c is curve_in)[3]
            before = [st for t, st in curve_in if t <= s0]
            start = (before[-1] if before else 0.0) - iv   # relative to this note
        elif (s0, v) in scoops:
            start = -2.0
        pb(ch, s0 - 1, start)
        ev.append((s0, 2, mido.Message('note_on', channel=ch, note=n0, velocity=100)))
        ev.append((e0, 0, mido.Message('note_off', channel=ch, note=n0, velocity=0)))
        land = s0
        if curve_in:                              # the rest of the frets, on the new pick
            slides += 1
            for t, st in curve_in:
                if t > s0:
                    pb(ch, t, st - iv); land = max(land, t)
        elif (s0, v) in scoops:                   # the whammy bar, released into the note
            scooped += 1
            w = 0.090 * tps; k = 0
            while k * dt <= w:
                x = k * dt / w
                pb(ch, s0 + k * dt, -2.0 * (1.0 - x) ** 2); k += 1
            land = s0 + w
        curve_out = slide_out.get(n)
        if curve_out:                             # the frets before the next beat
            for t, st in curve_out:
                if t <= e0:
                    pb(ch, t, st)
        elif (e0 - land) >= VIB_S * tps:          # a held note: finger vibrato
            vibs += 1
            t = max(land, s0 + 0.120 * tps)
            while t < e0:
                age = (t - s0) / tps
                depth = 0.35 * min(1.0, max(0.0, (age - 0.12) / 0.28))
                pb(ch, t, depth * 0.5 * (1 - _m.cos(2 * _m.pi * 5.5 * (age - 0.12))))
                t += dt
    m = mido.MidiFile(ticks_per_beat=tpb)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm)))
    for msg in (mido.Message('control_change', channel=0, control=101, value=0),     # the MCM:
                mido.Message('control_change', channel=0, control=100, value=6),     # a lower zone
                mido.Message('control_change', channel=0, control=6, value=15),      # of 15 members
                mido.Message('program_change', channel=0, program=prog),
                mido.Message('control_change', channel=0, control=7, value=110),
                mido.Message('control_change', channel=0, control=10, value=pan)):
        tr.append(msg)
    ev.sort(key=lambda e: (e[0], e[1]))
    last = 0
    for t, _o, msg in ev:
        t = max(t, last)
        tr.append(msg.copy(time=t - last)); last = t
    m.save(path)
    return slides, vibs, scooped


# THE MIDDLE VOICE, TRADED BY HAND (Ben: "make the decision on each note
# yourself"). A guitarist playing two lines needs one of them to be easy, so
# the middle goes to the guitar with a FREE HAND -- its own line resting, held
# or repeating a note -- and to the one close to it in register (a reach past
# an octave and a half is not a hand); where the middle has the SUBJECT it
# goes where it can be played clean. A plays the top voice, B the bottom.
# (first bar, last bar, guitar, why)
MANUAL = {'wtc2f12': [
    (5, 11, 'B', "the answer enters; B's bass has not come in yet, and A is in "
                 "running sixteenths above it"),
    (12, 17, 'A', "the bass enters with the subject, so B's hand is taken; A's "
                  "top holds long notes (C5 for three bars) over the middle"),
    (18, 28, 'A', "the middle is sparse held notes (G4, F4, Eb4) a finger can "
                  "hold under A's line; from B's Bb2 they are out of reach"),
    (29, 33, 'A', "the subject in the middle (Ab4 Eb4 Eb4 Eb4) under A's held "
                  "Eb5 and D5; B is running in the bass"),
    (34, 42, 'A', "the top rests and holds, the middle sits F4-Eb5; the bass "
                  "is two octaves down and busy -- and takes the subject at 41"),
    (43, 49, 'A', "the middle climbs to Gb5 in long values while B runs "
                  "sixteenths; A's top is broken, a free hand"),
    (50, 55, 'B', "the middle drops to G3-C4 with the subject at 51, right over "
                  "B's repeated C3 pedal: one hand, both lines"),
    (56, 71, 'A', "back up to Gb4-E5 under A's long notes and rests; B's bass "
                  "is repeated notes an octave and more below"),
    (72, 74, 'B', "the middle falls to F3-Eb4, onto B's held Db3 and Gb3"),
    (75, 83, 'A', "the last subject entry in the middle (C5 F4 F4 F4) under "
                  "A's repeated Db5 -- then held notes under the coda's runs"),
    (84, 85, 'B', "the cadence: the middle's F4 is the top voice's F4, which "
                  "one guitar cannot play twice -- so B takes it, and the final "
                  "chord is both guitars"),
],
# The E minor: a long subject (a turn figure, a leap to the sixth, a triplet
# run), nine entries, and a middle voice that roams from A#2 to E5 -- so it
# changes hands more often than the F minor's did.
'wtc2f10': [
    (1, 11, 'B', "the answer enters at 7 (D4-G4); B's bass is silent until "
                 "12 and A runs triplets above it"),
    (12, 23, 'A', "the bass takes the subject at 13; the middle holds half "
                  "notes and suspensions (E4-A4) under A's long notes, and in "
                  "21-23 A holds while the middle runs, then runs while it holds"),
    (24, 29, 'B', "the top has the subject; the middle drops to E3-F#4, into "
                  "the bass's register, over B's halves and quarters"),
    (30, 36, 'A', "the subject in the middle (F#4-D5) under A's halves and "
                  "quarters; B's bass runs triplets"),
    (37, 39, 'B', "B's bass holds F#4, D4, B3 most of each bar, a third to a "
                  "sixth under the middle, while A runs in 37 and 39"),
    (40, 55, 'A', "the middle climbs to F#5, out of B's reach; the bass has the "
                  "subject at 42; at 46-49 the top and middle hold fourths "
                  "together (F#4/C#4, G4/D4, A4/E4); the middle's subject at 50 "
                  "goes where A's top rests and dips under it"),
    (56, 58, 'B', "A runs triplets across two octaves; B's bass walks in "
                  "quarters a third to a sixth under the middle"),
    (59, 59, 'A', "the top rests after two notes, and the middle's run down "
                  "to G#3 goes to the free hand; B's bass is running too"),
    (60, 61, 'B', "the top has the subject; the middle holds A3 and runs "
                  "C3-A3, crossing the bass -- one hand, both lines, low"),
    (62, 63, 'A', "the middle jumps up to D5-A4 in half notes, a third to a "
                  "sixth under A's subject; B's bass runs"),
    (64, 64, 'B', "the middle runs down to G#3 over B's slow bass (D3 F3 E3 "
                  "D#3 E3); A's top is running"),
    (65, 67, 'A', "A holds A4 and G4 while the middle runs and holds B3; B's "
                  "bass runs triplets"),
    (68, 70, 'B', "B's bass holds B2 for a bar, then the middle goes BELOW it "
                  "(A#2, B2 half notes): a pedal on the low string under the bass"),
    (71, 77, 'A', "the middle rests, then returns at B4 over the bass's "
                  "final subject (72), so B's hand is taken; A's top holds under "
                  "the middle's halves and suspensions"),
    (78, 78, 'B', "the middle climbs from D#3 right over B's held B2"),
    (79, 82, 'A', "the middle climbs E4-B4 in half notes near A's held top; "
                  "B's B2 pedal figure is two octaves down"),
    (83, 84, 'B', "the middle drops to F#3, then runs over B's held B3"),
    (85, 86, 'A', "the cadence: the middle's G#3 is the Picardy third, on A "
                  "under its closing E4, over B's octave E"),
],
# The C# minor: a gigue in 12/16, the subject a run of sixteenths, a second
# figure (a leaping, dotted one) from 33. Every voice runs somewhere in almost
# every bar, so the middle goes to whichever guitar's own line is SLOW there --
# it trades most of the three, and in 25-29 and 50-54 the guitars hand a run
# across bar by bar, which is what twin guitars do.
'wtc2f04': [
    (1, 7, 'B', "the middle's subject at 5 (C#4-G#4) over B's bass in dotted "
                "quarters; A's top would cross it (D#4 in bar 6)"),
    (8, 11, 'A', "the middle holds C4, C#4, B3 under A's top; B's bass runs"),
    (12, 14, 'B', "the middle drops to B2-B3, into the bass's register, over "
                  "B's slow notes"),
    (15, 16, 'A', "the middle runs up to G#4, two octaves over B's D#2; A's "
                  "top is in dotted quarters just above it"),
    (17, 19, 'B', "the answer enters mid-bar over B's held C#4, then B's bass "
                  "moves in dotted quarters; A's top is still running the subject"),
    (20, 24, 'A', "the bass takes the subject in E major and runs; the middle "
                  "holds B4, A4, G#4 under A's slow top"),
    (25, 25, 'B', "the middle's dotted figure over B's own, a sixth apart; A runs"),
    (26, 26, 'A', "the middle runs from C#5 under A's slow top; B's bass trills"),
    (27, 27, 'B', "the bass rests, so the run goes to B's free hand; A's top "
                  "is in dotted rhythm"),
    (28, 29, 'A', "the middle slows (B4, A4, F#4) under A's long notes; B runs"),
    (30, 31, 'B', "the subject in the middle over B's held F#3 and dotted "
                  "quarters; A's top has sixteenths"),
    (32, 32, 'A', "B's bass trills, so the subject's last bar goes to A, "
                  "holding G#4 and F#4"),
    (33, 35, 'B', "A's top brings the second figure; the middle answers it at "
                  "34 over B's bass walking in dotted quarters"),
    (36, 41, 'A', "the middle jumps up to B4-C#5 and holds, too far over B's "
                  "running bass; A's top is slow, then runs over the middle's "
                  "held G#4"),
    (42, 46, 'B', "the middle comes down to A#3-F4 over B's dotted quarters; "
                  "A's top runs"),
    (47, 47, 'A', "the middle's short run leads to A's held C#5; B runs"),
    (48, 49, 'B', "the subject is in A's top, so the middle goes over B's slow "
                  "bass (F#3 F3 E3)"),
    (50, 51, 'A', "A's top slows, a sixth over the middle; B's A2 is two "
                  "octaves under it"),
    (52, 52, 'B', "the middle's chromatic descent (D4 C#4 C4 B3) and B's bass, "
                  "both in dotted quarters: chords on one guitar; A runs"),
    (53, 53, 'A', "A holds A4 over the middle's run; B runs too"),
    (54, 54, 'B', "the middle runs low (F#3-B3) over B's dotted quarters; A runs"),
    (55, 56, 'A', "the bass has the subject; the middle holds and runs under "
                  "A's slow top"),
    (57, 67, 'B', "B's bass slows, then holds G#3 for two bars (59-60) and "
                  "again under the middle's last subject entry (66); the "
                  "middle stays low, A3-D#4, while A's top runs"),
    (68, 71, 'A', "B's bass runs to the end; the middle holds F#4, then moves "
                  "in dotted quarters under A's top; the final chord's E#4 on "
                  "A with its C#5, over B's C#2"),
]}

import mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = os.path.expanduser('~/Downloads/bwx-renders/wtc')


def notes_of(m):
    """[(start tick, end tick, channel, note)] from a MIDI file."""
    out = []
    for t in m.tracks:
        a, on = 0, {}
        for e in t:
            a += e.time
            if e.type == 'note_on' and e.velocity > 0:
                on[(e.channel, e.note)] = a
            elif e.type in ('note_off', 'note_on') and (e.channel, e.note) in on:
                out.append((on.pop((e.channel, e.note)), a, e.channel, e.note))
    return out


def voices(ns, table=None):
    """The notes with each channel made its voice: 0 bottom, 1 middle, 2 top."""
    if table:
        return [(s, e, table.get(c, 2), n) for s, e, c, n in ns]
    main_ = [x for x in ns if x[2] <= 2]
    out = list(main_)
    for s, e, c, n in ns:
        if c > 2:                    # a divisi: the voice sounding nearest in pitch
            near = [(abs(n2 - n), c2) for s2, e2, c2, n2 in main_ if s2 <= s < e2 or s <= s2 < e]
            out.append((s, e, min(near)[1] if near else (0 if n < 55 else 2), n))
    return sorted(out)


def harmony(ns, beat, tpb, prev, diatonic=None):
    """The beat's chord, as (root pitch class, 'maj'/'min'), or prev."""
    w = [0.0] * 12
    lo = {}
    for s, e, _c, n in ns:
        ov = min(e, beat + tpb) - max(s, beat)
        if ov > 0:
            w[n % 12] += ov
            lo[n] = ov
    if not lo:
        return prev
    w[min(lo) % 12] += lo[min(lo)]                   # the bass note, double
    best, score = prev, None
    for root in range(12):
        for q, third in (('maj', 4), ('min', 3)):
            tones = {root, (root + third) % 12, (root + 7) % 12}
            sc = sum(w[p] for p in tones) - 0.5 * sum(w[p] for p in range(12) if p not in tones)
            sc += 0.1 * tpb if prev and root == prev[0] else 0.0   # hold unless clearly better
            if diatonic is not None and root not in diatonic:
                sc -= 0.25 * tpb
            if score is None or sc > score:
                best, score = (root, q), sc
    return best


# A STUDIO GUITAR RECORDING: each amp on a close mic for the attack and a
# room mic a few metres back for the air, blended. (distance m, gain dB)
MICS = {'close': (0.5, 0.0), 'room': (3.0, -6.0)}


def render_effects(name, ns, who, bar, pk, nbar, tpb, bpm, tag, room_mics=False):
    """The hand-traded two guitars, each an MPE zone with slides, vibrato and
    entry scoops; the same closing ritardando, the same mix."""
    import lib
    last = max(s for s, _e, _c, _n in ns)
    fin = pk + ((last - pk) // bar) * bar
    r0, r1, lo = fin - 2 * bar, fin, 0.70
    def warp(t):
        if t <= r0:
            return t
        u = min(t, r1) - r0
        k = (1.0 - lo) / (r1 - r0)
        out = r0 - math.log(1.0 - k * u) / k
        if t > r1:
            out += (t - r1) / lo
        return int(round(out))
    voice = lambda c: 0 if c == 0 else (1 if c == 1 else 2)
    A, B = [], []
    for s, e, c, n in ns:
        v = voice(c)
        g = 'A' if v == 2 else 'B' if v == 0 else ('A' if who[min(max(0, (s - pk) // bar), nbar - 1)] == 0 else 'B')
        (A if g == 'A' else B).append((warp(s), warp(e), v, n))
    scoops = set()
    for bar1, v in ENTRY_VOICE.get(name, {}).items():
        b0 = pk + (bar1 - 1) * bar
        first = min((s for s, _e, c, _n in ns if voice(c) == v and s >= b0), default=None)
        if first is not None:
            scoops.add((warp(first), v))
    mics = MICS if room_mics else {'close': MICS['close']}
    wavs, loud = {}, {}
    for g, notes, pan in (('guitar B', B, 36), ('guitar A', A, 92)):
        mid = os.path.join(OUT, '%s%s.%s.mid' % (name, tag, g.replace(' ', '-')))
        sl, vb, sc = guitar_mpe(notes, tpb, bpm, 30, pan, mid, scoops)
        print("  %s: %d slides, %d notes with vibrato, %d entry scoops" % (g, sl, vb, sc))
        for mname, (dist, _gdb) in mics.items():
            env = {'TUNING_ROOM': 'studio', 'TUNING_DISTANCE': str(dist), 'TUNING_MASTER_DB': '-14'}
            wav = mid[:-4] + '.%s.dry.wav' % mname
            lib.render_plain(mid, wav, tuner='even', extra_env=env)
            wet = mid[:-4] + '.%s.wav' % mname
            lib.roomtail(wav, wet, env={'TUNING_ROOM': 'studio', 'TUNING_DISTANCE': str(dist)})
            wavs[(g, mname)] = wet
        loud[g] = lib.loudness(wavs[(g, 'close')])      # the guitars balanced on the close mic
    gains = [10 ** ((loud['guitar A'] - loud[g]) / 20.0 + mics[m][1] / 20.0) for (g, m) in wavs]
    # each mic already has its room, at its own distance: sum them as they are
    wet = os.path.join(OUT, name + tag + '.wav')
    lib.sum_wavs(list(wavs.values()), wet, gains=gains)
    print("  mics: %s" % ', '.join('%s %.1f m %+.0f dB' % (k, d, g) for k, (d, g) in mics.items()))
    print("  -> %s" % lib.mp3(wet))
    return 0


def main(argv):
    args = argv[1:]
    name = next((a for a in args if a.startswith('wtc')), 'wtc2f12')
    # CHORD-OUT (Ben): no power-chord part at all. The two leads play their
    # lines, and wherever both attack TOGETHER each note becomes a power chord
    # -- note, fifth, octave -- so the harmony arrives where the voices meet.
    chord_out = '--chord-out' in args
    # ONE GUITAR (Ben): both upper voices on a single distorted guitar, and no
    # new notes. What a guitarist adds is SUSTAIN: a note left ringing into
    # the rest after it -- up to a beat, never past its own voice's next note
    # -- unless the other voice brings in a note a semitone or a tone away,
    # which distorted is mud and a player damps; and one string cannot hold
    # two different notes at the same pitch at once.
    one_guitar = '--one-guitar' in args
    # TRADE (Ben): two distortion guitars, one on the top voice, one on the
    # bottom (drop C for its C2s), and the middle voice traded between them
    # "when it makes the most sense harmonically". Per bar, the middle goes to
    # the guitar whose own line it sits better against -- on a distorted
    # guitar seconds, sevenths and tritones are mud, thirds and sixths fair,
    # fourths, fifths and octaves clean, each weighed by how long they sound,
    # plus a reach penalty past an octave and a half -- and the whole piece is
    # solved at once (dynamic programming) with a cost for every trade, so it
    # changes hands only where that is clearly better.
    effects = '--effects' in args
    manual = '--manual' in args or effects
    dstyle = args[args.index('--drums') + 1] if '--drums' in args else None
    trade = '--trade' in args or manual
    # what a trade costs against a bar of rub; lower trades more (1.5: 3 trades)
    switch = float(args[args.index('--switch') + 1]) if '--switch' in args else 1.5
    tag = ('_metal6' if effects else ('_metal5' + ('_%s' % dstyle if dstyle else '')) if manual else
           ('_metal4' if switch == 1.5 else '_metal4_switch%g' % switch) if trade else '_metal3' if one_guitar else
           '_metal2' if chord_out else '_metal')
    bpm = float(args[args.index('--bpm') + 1]) if '--bpm' in args else BPM.get(name, 84.0)
    src = mido.MidiFile(os.path.join(OUT, name + '.notation.mid'))
    tpb = src.ticks_per_beat
    ns = voices(notes_of(src), VOICE_OF.get(name))
    end = max(e for _s, e, _c, _n in ns)
    bar, pk = METER.get(name, 2) * tpb, PICKUP.get(name, 0) * tpb
    nbar = (end - pk) // bar + 1
    bi = lambda t: min(max(0, (t - pk) // bar), nbar - 1)   # a tick's bar, from 0

    ev = []                                   # (tick, order, message)
    def note(ch, n, t0, t1, v):
        ev.append((t0, 1, mido.Message('note_on', channel=ch, note=n, velocity=v)))
        ev.append((max(t0 + 1, t1), 0, mido.Message('note_off', channel=ch, note=n, velocity=0)))
    setup = []
    def ctl(ch, prog, pan, cc1=None):
        setup.extend([mido.Message('program_change', channel=ch, program=prog),
                      mido.Message('control_change', channel=ch, control=10, value=pan),
                      mido.Message('control_change', channel=ch, control=7, value=110)])
        if cc1 is not None:
            setup.append(mido.Message('control_change', channel=ch, control=1, value=cc1))

    # the voices: ch0 bass -> fretless (3), ch1 alto (1), ch2/ch3 soprano (2)
    ctl(3, 35, 64); ctl(1, 29, 40, 127); ctl(2, 29, 88, 127)
    lead_on = {}
    for s, e, c, n in ns:
        if c != 0:
            lead_on.setdefault(s, set()).add(1 if c == 1 else 2)
    together = {t for t, v in lead_on.items() if v == {1, 2}}
    if one_guitar:
        ctl(1, 30, 64)                                   # one guitar, centre
        upper = sorted((s, e, 1 if c == 1 else 2, n) for s, e, c, n in ns if c != 0)
        # LET RING, as a guitarist does across strings: a note keeps sounding
        # under what follows it -- in either voice -- for up to a beat, and is
        # damped the moment a note arrives that it would CLASH with: a second
        # or a seventh (distorted, those are mud), or the same pitch class,
        # which on a guitar is its own string being played again. What rings
        # on is what is consonant with it: thirds, fourths, fifths, sixths,
        # octaves -- the notes a player leaves down on the other strings.
        rung = 0
        for s, e, v, n in upper:
            limit = e + tpb
            clash = min((s2 for s2, _e2, _v2, n2 in upper
                         if e <= s2 < limit and (s2, n2) != (s, n)
                         and (abs(n2 - n) % 12 in (0, 1, 2, 10, 11))), default=limit)
            ring = max(e, clash)
            rung += ring > e
            note(1, n, s, ring, 100)
        for s, e, c, n in ns:
            if c == 0:
                note(3, n - 12, s, e, 100)
        print("  one guitar: %d notes, %d left ringing past their written value" % (len(upper), rung))
    if trade:
        ctl(1, 30, 36); ctl(2, 30, 92)                   # B (bottom) left, A (top) right
        roughness = {0: 0.1, 1: 1.0, 2: 0.8, 3: 0.4, 4: 0.4, 5: 0.1, 6: 0.9,
                     7: 0.05, 8: 0.4, 9: 0.4, 10: 0.8, 11: 1.0}
        def cost(bi, own):
            b0, b1 = pk + bi * bar, pk + (bi + 1) * bar
            mids = [(s, e, n) for s, e, c, n in ns if c == 1 and s < b1 and e > b0]
            mine = [(s, e, n) for s, e, c, n in ns if c in own and s < b1 and e > b0]
            k = 0.0
            for s, e, n in mids:
                for s2, e2, n2 in mine:
                    ov = min(e, e2, b1) - max(s, s2, b0)
                    if ov > 0:
                        iv = abs(n - n2)
                        k += ov / tpb * (roughness[iv % 12] + (0.5 if iv > 18 else 0.0))
            return k
        cA = [cost(b, {2, 3}) for b in range(nbar)]        # middle with the top
        cB = [cost(b, {0}) for b in range(nbar)]           # middle with the bottom
        SWITCH = switch
        best = [[cA[0], cB[0]]]; back = []
        for b in range(1, nbar):
            row, bk = [], []
            for j, cj in enumerate((cA[b], cB[b])):
                stay, move = best[-1][j], best[-1][1 - j] + SWITCH
                row.append(cj + min(stay, move)); bk.append(j if stay <= move else 1 - j)
            best.append(row); back.append(bk)
        j = 0 if best[-1][0] <= best[-1][1] else 1
        who = [j]
        for bk in reversed(back):
            j = bk[j]; who.append(j)
        who.reverse()                                    # 0 = A (top), 1 = B (bottom)
        if manual:
            who = [0] * nbar
            for b0, b1, g, _why in MANUAL[name]:
                for b in range(b0 - 1, min(b1, nbar)):
                    who[b] = 0 if g == 'A' else 1
        trades = sum(1 for a, b in zip(who, who[1:]) if a != b)
        for s, e, c, n in ns:
            if c == 0:
                note(1, n, s, e, 100)                    # B: the bottom, as written
            elif c in (2, 3):
                note(2, n, s, e, 100)                    # A: the top
            else:
                note(2 if who[bi(s)] == 0 else 1, n, s, e, 100)
        chart_trade = (['bars %d-%d: middle with %s -- %s' % (b0, b1, g, why)
                        for b0, b1, g, why in MANUAL[name]] if manual else
                       ['bar %3d: middle with %s' % (b + 1, 'A (top)' if w == 0 else 'B (bottom)')
                        for b, w in enumerate(who)])
        if dstyle:
            setup.append(mido.Message('program_change', channel=9, program=KIT[dstyle]))
            setup.append(mido.Message('control_change', channel=9, control=7, value=110))
            drums(dstyle, STRUCTURE[name], ns, tpb, nbar - 1, note)
            if dstyle == 'fusion':                     # the fretless, doubling B an octave down
                ctl(3, 35, 64)
                for s_, e_, c_, n_ in ns:
                    if c_ == 0:
                        note(3, n_ - 12, s_, e_, 96)
        if effects:
            return render_effects(name, ns, who, bar, pk, nbar, tpb, bpm,
                                  tag + ('_roommics' if '--room-mics' in args else ''),
                                  room_mics='--room-mics' in args)
        print("  trade: the middle changes hands %d times; with A in %d bars, with B in %d"
              % (trades, who.count(0), who.count(1)))
    for s, e, c, n in (ns if not (one_guitar or trade) else ()):
        if c == 0:
            note(3, n - 12, s, e, 100)
        else:
            ch = 1 if c == 1 else 2
            chord = (n, n + 7, n + 12) if chord_out and s in together else (n,)
            for k in chord:
                note(ch, k, s, e, 96)
    if chord_out:
        print("  the leads chord out at %d of %d lead onsets" % (len(together), len(lead_on)))

    # the power chords, double-tracked
    ctl(4, 30, 8); ctl(5, 30, 120)
    delay = int(round(0.008 * tpb * bpm / 60.0))          # ~8 ms: the second take
    eighth = tpb // 2
    chord, chart = None, []
    for beat in (range(0, end, tpb) if not (chord_out or one_guitar or trade) else ()):
        chord = harmony(ns, beat, tpb, chord, KEYS.get(name))
        if chord is None:
            continue
        chart.append((beat // tpb, chord))
        pc = chord[0]
        root = 40 + ((pc - 40) % 12)                      # E2..D#3
        for k in range(2):
            t0 = beat + k * eighth
            v = 112 if k == 0 else 96
            for ch, dt, dv in ((4, 0, 0), (5, delay, -6)):
                for n in (root, root + 7, root + 12):
                    note(ch, n, t0 + dt, t0 + dt + int(eighth * 0.8), v + dv)

    # THE ENDING BROADENS (Ben): the two bars before the final chord slow
    # linearly to 70%, and the chord is held at that tempo -- BuxWV 161's
    # shape. Ticks are warped, at one tempo, so the stems stay aligned.
    last = max(t for t, _o, m_ in ev if m_.type == 'note_on')
    fin = pk + ((last - pk) // bar) * bar                # the final chord's bar
    r0, r1, lo = fin - 2 * bar, fin, 0.70
    def warp(t):
        if t <= r0:
            return t
        u = min(t, r1) - r0
        k = (1.0 - lo) / (r1 - r0)
        out = r0 - math.log(1.0 - k * u) / k
        if t > r1:
            out += (t - r1) / lo
        return int(round(out))
    ev = [(warp(t), o, m_) for t, o, m_ in ev]
    ev.sort(key=lambda x: (x[0], x[1]))
    beats_per_bar = METER.get(name, 2)
    lines = (['(no power-chord part: the leads chord out where they meet)'] if chord_out else
             ['(one guitar, both upper voices, let ring)'] if one_guitar else
             ['(two guitars: A the top, B the bottom, the middle traded)'] + chart_trade if trade else [])
    for b, (root, q) in chart:
        if b % beats_per_bar == 0:
            lines.append('bar %3d:' % (b // beats_per_bar + 1))
        lines[-1] += '  %-4s' % (NAMES[root] + '5')          # a power chord: no third
    open(os.path.join(OUT, name + tag + '.chords.txt'), 'w').write('\n'.join(lines) + '\n')
    print("  chord chart: %s" % os.path.join(OUT, name + tag + '.chords.txt'))

    import lib
    groups = (dict([('guitar B', {1}), ('guitar A', {2})] + ([('drums', {9})] if dstyle else []) +
                   ([('bass', {3})] if dstyle == 'fusion' else [])) if trade else
              {'bass': {3}, 'leads': {1}} if one_guitar else
              {'bass': {3}, 'leads': {1, 2}} if chord_out else
              {'bass': {3}, 'leads': {1, 2}, 'chords': {4, 5}})
    env = {'TUNING_ROOM': 'studio', 'TUNING_DISTANCE': '0.5', 'TUNING_MASTER_DB': '-14'}
    wavs, loud = {}, {}
    for g, chans in groups.items():
        m = mido.MidiFile(ticks_per_beat=tpb)
        tr = mido.MidiTrack(); m.tracks.append(tr)
        tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm)))
        tr.extend(x for x in setup if x.channel in chans)
        last = 0
        for tick, _o, msg in ev:
            if msg.channel in chans:
                tr.append(msg.copy(time=tick - last)); last = tick
        mid = os.path.join(OUT, '%s%s.%s.mid' % (name, tag, g.replace(' ', '-'))); m.save(mid)
        wav = os.path.join(OUT, '%s%s.%s.wav' % (name, tag, g.replace(' ', '-')))
        lib.render_plain(mid, wav, tuner='even', extra_env=env)
        wavs[g], loud[g] = wav, lib.loudness(wav)
    gains = []
    for g in groups:
        ref = 'guitar A' if trade else 'leads'
        tgt = DRUM_TARGET[dstyle] if g == 'drums' else (-4.0 if (g == 'bass' and trade) else TARGETS.get(g, 0.0))
        db = tgt - (loud[g] - loud[ref])
        gains.append(10 ** (db / 20.0))
        print("  %-8s %+6.1f dB -> %+5.1f  (gain %+6.1f dB)" % (g, loud[g] - loud[ref], tgt, db))
    dry = os.path.join(OUT, name + tag + '.dry.wav')
    lib.sum_wavs([wavs[g] for g in groups], dry, gains=gains)
    lib.merge_room([os.path.splitext(wavs[g])[0] + '.room.json' for g in groups],
                   os.path.splitext(dry)[0] + '.room.json')
    wet = os.path.join(OUT, name + tag + '.wav')
    lib.roomtail(dry, wet, env={'TUNING_ROOM': 'studio', 'TUNING_DISTANCE': '0.5'})
    print("  -> %s" % lib.mp3(wet))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
