# What is not built

`README.md` says what this is, `sources.md` where the physics came from,
`midi.md` the control surface, `coverage.md` how faithful each of the 128
programs is. This file is the other side of `coverage.md`: what is known to be
missing, what was deliberately left, and enough design to pick each one up
without re-deriving it.

Two things it is not. It is not a wish list — every entry is something already
worked out far enough to know what it would cost. And it is not a defect log:
things that are simply wrong get fixed, not filed.

## The brass glissando lattice

The largest designed-and-unbuilt thing here, and the reason this file exists.

Portamento shipped with `glide_mechanism` on 49 programs. Four of them —
trumpet, muted trumpet, horn and tuba — carry `'valve'`, and a valved gliss is
**not a slower slide**. Ben, who plays these:

> When we brass players glissando, we do it in many ways. 1. move cleanly from
> one fingering to another, and blow through the harmonics. 2. move arbitrarily
> the valves while blowing through the harmonics. 3. pressing down half way on
> one of the valves to interfere with harmonic alignment, while muffling the
> gliss, in between. 4. backing off the mouthpiece for a similar effect, to
> allow for more lip sway, as blowing through the harmonics.
>
> Maybe the speed controller can control how straight or slurred the glissando
> is across the harmonics?

**What is built today is technique 4 and only that.** `glide_reach_semitones =
2.0` on `BrassProperties` is the lip's sway; anything wider plays clean. That
is a deliberate gap rather than an approximation, because a brass gliss past a
tone is a different gesture and a smooth sweep would sound like a trombone
played by a trumpet.

### The lattice already exists

`brass_fingering.py` was written for INTONATION — valve combinations run sharp,
the harmonic series is not the temperament — and it happens to contain exactly
what a glissando needs:

| | |
|---|---|
| `INSTRUMENTS` | `open_hz`, usable `partials`, which `valves` exist |
| `COMBOS` | the seven combinations, in the order a player prefers them |
| `COMBOS_4` | eleven, for the tuba's fourth valve |
| `_length_ratio(combo)` | what that combination does to the tube |
| `fingering(hz, instrument)` | `(partial, combo, cents_error, actual_hz)` |

A reachable pitch is `partial × open_hz / _length_ratio(combo)`. The set of them
is the lattice, and a gliss walks it.

### The path, and why it is a chromatic run and not a sweep

Technique 1 — the common one — is a chromatic run using the standard fingering
for each semitone. `fingering()` already returns the pitch that fingering
**actually produces**, which is a few cents off equal temperament and differs
per step. So the gliss is a staircase of real, slightly-out-of-tune pitches,
and that microscopic wobble is part of what makes it recognisable. Nothing has
to be invented: walk the semitones between source and target, ask `fingering()`
for each, and take the `actual_hz` it gives back.

### CC5 stops being a speed and becomes a straightness

This is Ben's suggestion and it is the interesting part. On a `valve` voice:

| CC5 | technique | what it sounds like |
|---|---|---|
| low | 1 | clean steps, each a real fingered pitch |
| mid | 2 | steps, but the valve order wanders |
| high | 3 / 4 | half-valve: the steps smeared toward a line, **and quieter** |

The level dip matters. Half-valving breaks the harmonic alignment, so the note
loses support in the middle of the gliss — that dip is the audible tell, and a
smear without it would just sound like a portamento with extra steps.

The smear itself is a crossfade between the staircase and the continuous
length-linear path the other mechanisms already use.

### What it would cost

**The kernel cannot do a staircase with the glide term it has.** `gbav/gtau/gcut`
render one smooth reciprocal settle; arbitrary shapes need rows, and rows are
per-block-per-note, which `midi.md` explains is ~3 GB on a busy file.

The honest implementation is therefore not a kernel change at all: **emit the
gliss as a short sequence of note-groups** in `blockrender`'s build loop, one
per lattice step, each with `legato_attack_s` so it does not re-articulate, and
each carrying a small `gb` glide between steps as the smear opens up. That is
what the model actually says is happening — a run of real pitches — so the
renderer emitting real notes is not a workaround.

Live is harder and should follow, not lead: those note-groups have to be
scheduled ahead on the audio thread, which nothing here does yet.

### One question still open

Does the gliss occupy the space *between* two notes, or the attack *of* the
second one? A rip into a note and a gliss between two notes are different
gestures and a player does both. The controller does not distinguish them, so
this is a choice, and it should be made deliberately rather than falling out of
where the code happens to sit.

## General MIDI 2

Four of GM 2's features are in: Scale/Octave tuning by SysEx, CC93 chorus,
CC91 reverb (file only), and portamento. What is left:

| | state | note |
|---|---|---|
| **Bank Select, CC0/CC32** | nothing reads them | the structural one — everything below it depends on this |
| ~128 variation sounds | none | addressed by CC0=121 + CC32 |
| 9 drum kits | one kit | addressed by CC0=120 |
| channel 11 as a second drum part | no | falls out of bank select |
| CC71–78 sound controllers | none | **needs a design first**, see below |
| CC124–127 mono/poly mode | none | mono makes portamento's source note unambiguous |
| RPN 3, 4, 5 | only 0/0, 0/1, 0/2 | tuning program/bank select, modulation depth range |
| Master Volume / Fine / Coarse SysEx | none | small and mechanical |
| reverb *type* / chorus *type* SysEx | sends work, types cannot be chosen | one physical room; may stay a knowing deviation |
| CC91 live | file only | new DSP on the audio thread — a convolver or an FDN, not a port |

**Bank select is load-bearing.** GM 2's whole extended sound set is addressed
through it, and without it a GM 2 file's variations collapse silently onto the
Level 1 program — the failure mode you cannot hear. Note that `live.py`'s `Bank`
class is the **template cache** keyed on `(program, drums, tuner)` and has
nothing to do with MIDI bank select; one of the two will need renaming before
the other is built, or it will cost somebody an hour.

**CC71–78 is not a protocol job.** "Brightness" and "filter resonance" are knobs
on a subtractive synth; a physical model has no filter to turn. They would have
to land on something real — `effort_tilt` for brightness, the actual mechanism's
attack and decay for 72/73/75 — and voices would refuse them the way they refuse
a bend. That is a conversation before it is an implementation.

## Known and deliberately not fixed

**`WhistleProperties` is defined twice** — `tonelib.py:12830` on
`OcarinaProperties` (the samba/referee whistle) and `tonelib.py:13132` on
`VesselFluteProperties` (a human whistle). Python keeps the later one, so GM 78
gets the human whistle. **GM 78 is the slide whistle**, whose entire mechanism
is a glide, so this is both a shadowed definition and the wrong instrument. It
was found while writing portamento and deliberately not fixed inside that
change; a slide whistle wants `glide_mechanism = 'slide'` and an unbounded
reach, and it wants to be its own class.

**`_sysex` re-programs the Parts that exist and creates none.** A real GM module
is sixteen-part multitimbral; a Part here is an explicit assignment with a
channel, key range, level and registration, and manufacturing sixteen would
demolish a hand-built split and cut every held note. That is a knowing deviation
and is recorded in the method's own docstring.

**GM 0's stringing.** Whether program 0 should carry a console piano's
inharmonicity rather than the Steinway B's is a decision, not a defect, and it
is Ben's to make. `sources.md` has the evidence: GM specifies nothing about any
program, and Level 2's own bank variations treat brightness as a timbral axis on
one instrument rather than a different piano.

**No true delay line, and no rising envelope segment.** Both have been wanted
more than once. Neither is blocking anything.
