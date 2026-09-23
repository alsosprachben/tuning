# What is not built

`README.md` says what this is, `sources.md` where the physics came from,
`midi.md` the control surface, `coverage.md` how faithful each of the 128
programs is. This file is the other side of `coverage.md`: what is known to be
missing, what was deliberately left, and enough design to pick each one up
without re-deriving it.

Two things it is not. It is not a wish list — every entry is something already
worked out far enough to know what it would cost. And it is not a defect log:
things that are simply wrong get fixed, not filed.

## The brass glissando lattice — file renderer done, live not

Built for `blockrender.py`; see `midi.md` for what it does and `sources.md` for
the physical account. What remains is **live**: the run is a sequence of
note-groups, and scheduling those ahead on the audio thread is something the
engine does not do for anything yet. Until it does, live glides a valved voice
only as far as the lip reaches and plays anything wider clean, so the two paths
agree to two semitones and diverge deliberately past it.

**Settled: the gliss takes the head of the note it arrives at**, and the
arrival is late by the length of the run. Three reasons, and the first is
decisive. Roland's text puts the glide at the note-on — a note after portamento
*"will change continuously in pitch, starting from the pitch of the Source Note
Number"* — so a file that uses CC65 or CC84 has already chosen this. Live can
only do it this way: a gliss *between* two notes has to start before the second
note-on, which means knowing it is coming. And a file that wants the arrival on
the beat can put the note-on earlier; the renderer does what the bytes say.

What is still worth revisiting is the cap: the run is limited to **half the
note**, so on a short note a slow gliss is squeezed and CC5 means something
different depending on note length. An absolute cap would keep CC5's meaning
fixed. A notated "between" gliss, if ever wanted from a score, should be an
explicit per-part setting on the file renderer and never a heuristic.

**One refinement not attempted.** Technique 2, "move arbitrarily the valves
while blowing through the harmonics", would wander the valve order instead of
walking the chromatic fingerings. It needs a reason to prefer one path over
another, and there isn't one yet.

## General MIDI 2

In: Scale/Octave tuning by SysEx, CC93 chorus, CC91 reverb (file only),
portamento, mono/poly mode, RPN 5 modulation depth range, and Master Volume,
Fine and Coarse Tuning. What is left:

| | state | note |
|---|---|---|
| **Bank Select, CC0/CC32** | nothing reads them | the structural one — everything below it depends on this |
| ~128 variation sounds | none | addressed by CC0=121 + CC32 |
| 9 drum kits | one kit | addressed by CC0=120 |
| channel 11 as a second drum part | no | falls out of bank select |
| CC71–78 sound controllers | none | **needs a design first**, see below |
| CC121 in a file | live only | a file that resets its controllers mid-piece |
| legato attack, live | file only | live mono re-articulates every note; the pitch path is right |
| reverb *type* / chorus *type* SysEx | sends work, types cannot be chosen | one physical room; may stay a knowing deviation |
| CC91 live | file only | new DSP on the audio thread — a convolver or an FDN, not a port |

**RPN 3 and 4 are done, as the `gm2` tuner's store** (`mts.py`, and see
`midi.md`). Three things are left from that work:

- **Data increment and decrement (CC96/97)** are defined by the MTS text as a
  way to step the tuning program and bank. This renderer reads neither for any
  RPN.
- **Offline, a tuning select or a real-time single-note change reaches a
  sounding note only from its next onset.** The spec says it should move at
  once, and live does. The file renderer prints a count when this happens.
- **Sympathetic resonance reads the base table**, not a channel's MTS table.

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

~~`WhistleProperties` is defined twice.~~ **Fixed** — the percussion class is
`SambaWhistleProperties` now, and a general check refuses any two classes in
`tonelib.py` sharing a name.

Two corrections to what this file said before. The casualty was **percussion
71/72**, not GM 78: the referee's whistle was being built from the human
whistle's class, 80 partials where it wanted 5598. And **GM 78 is not a slide
whistle** — its own docstring argues the point, and it is right: the SC-55
sound every file was written for is a human whistle, a tin whistle would
duplicate the recorder two programs earlier, and the specification places 78
between the shakuhachi and the ocarina rather than with the flutes.

Worth knowing for next time: fixing it moved the render by **half a decibel**.
The voice is mostly broadband air either way, so a seventy-fold change in the
partial table was nearly inaudible — which is exactly why the collision
survived as long as it did.

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
