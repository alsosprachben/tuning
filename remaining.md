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

The cap is settled too: the run keeps CC5's time and gives way only to leave
the arrival max(60 ms, 20%) of the note, and a gliss too short to run is
counted rather than silently dropped. A notated "between" gliss, if ever wanted
from a score, should be an explicit per-part setting on the file renderer and
never a heuristic.

**One refinement not attempted.** Technique 2, "move arbitrarily the valves
while blowing through the harmonics", would wander the valve order instead of
walking the chromatic fingerings. It needs a reason to prefer one path over
another, and there isn't one yet.

## General MIDI 2

In: Scale/Octave tuning by SysEx, CC93 chorus, CC91 reverb (file only),
portamento, mono/poly mode, RPN 5 modulation depth range, Master Volume, Fine
and Coarse Tuning, the CC71–78 sound controllers, and **bank select**, with the
drum sets and GM 2's drum/melodic switch. What is left:

| | state | note |
|---|---|---|
| ~128 variation sounds | resolved and latched, then played as the capital tone; not yet carried to the voice (below) | one at a time, in `patch_map.VARIATIONS`, when a file or a player wants one |
| drum sets | **stopped here, deliberately**: Electronic (24) and Brush (40) built; the rest play Standard | see below |
| reverb *type* / chorus *type* SysEx | sends work, types cannot be chosen | one physical room; may stay a knowing deviation |
| CC91 live | file only | new DSP on the audio thread — a convolver or an FDN, not a port |

**RPN 3 and 4 are done, as the `gm2` tuner's store** (`mts.py`, and see
`midi.md`). One thing is left from that work: **offline, a tuning select or a
real-time single-note change reaches a sounding note only from its next
onset.** The spec says it should move at once, and live does. The file renderer
prints a count when this happens.

**Bank select was not load-bearing here.** This file used to call it the
structural gap, and for GM 2 files it is. But the corpus has none: it contains
no SysEx, 39 of its 42 CC0 messages are 0, and the other three are XG's drum
bank. What it did use was drum SETS, by program change alone, and only
`thememat`/`thememix` asked for one that exists (Electronic, for one reverse
cymbal). So the wiring went in with the one set that is heard. Variations wait
to be asked for.

**Drum sets went as far as Electronic and Brush, and stop there.** Electronic
is the one set the corpus asks for, and Brush is the SC-55's jazz set, built
because Jazz on the SC-55 IS Standard. The rest play Standard, and here is what
building one would take:

| set | SC-55 program | notes it changes (p.70–71) | what it would take |
|---|---|---|---|
| Room | 8 | the six toms | a smaller-room tom, which is mostly a shorter ring |
| Power | 16 | kick, snare, the six toms | gated and compressed rock drums; the gate exists now |
| TR-808 | 25 | 19 notes: kick, rim, snare, the six toms, the three hats, cymbal, cowbell, three congas, maracas, claves | a whole circuit kit: bridged-T resonators and the six-square hats |
| Orchestra | 48 | hats and ride moved to 27–30, concert bass drums and snares, castanets, timpani across 41–53, two concert cymbals, applause on 88 | the timpani voice already exists; the rest is a concert kit |
| SFX | 56 | from 39 up, all effects (p.71) | sound effects, not drums |
| CM-64/32L | 127 | the MT-32's map | a different map, not a set |

The SC-88 and SC-88 Pro add more (STANDARD 2 and 3, TR-707, TR-909, Ethnic and
others; SC-88 Pro manual p.163), and corpus files send 1, 29, 30 and 49, which
are those numbers. But on the SC-55 they are not sets, and at least 49 — in
Ben's `monocas` pieces — was never chosen: a 1990s sequencer wrote it. So they
play Standard, and a later map belongs behind an explicit setting (the SC-88
Pro's own MAP button, or CC32 per part), never inferred from a program number.

**When the first variation is built,** thread it through: `resolve_patch`
already returns it, but neither renderer carries it yet. It needs to go on
blockrender's note snapshot, next to the program, and into live's `Patch` key
`(program, drums, tuner)`. Building that plumbing with an empty table would be
code that does nothing.

**CC71–78 are done** — see `midi.md`. Their laws are chosen rather than
published. If the GM 2 specification comes to hand (the sound-controller
defaults are RP-021), check them against it, and check whether CC121 should
reset them. Both renderers assume it doesn't.

## The panel's controls and routes

Built (README, "Controls a keyboard doesn't have"). Two things were left out on
purpose:

- **A key as a pedal.** On a keyboard that sends only notes, the natural
  momentary control is a key it can spare, such as the bottom A held as
  sustain. A route source of `('note', n)` would do it with the same
  held-while-down logic the wheel uses: note-on puts the pedal down, note-off
  lifts it, and the note itself is consumed. It was not asked for, and it takes
  a key away from the music.
- **Routes in the file renderer.** They are a property of the player's
  keyboard, not the score, so `blockrender.py` doesn't see them. A file that
  wants sustain writes CC64.

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
