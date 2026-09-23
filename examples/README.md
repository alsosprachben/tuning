# examples

The scripts that build the renders, kept.

Every one of these started as a shell pipeline in `/tmp`, and the throwaway
versions are why the same mistakes kept coming back. Three in particular:

- **Dropping the conductor track.** In an engraving export, track 0 usually has
  no notes -- only the tempo map -- so it looks like an empty track worth
  cutting. Cut it and everything else plays at the 120 bpm default. That is
  what "the accompaniment is exactly twice as fast as the voices" was.
- **Selecting parts by name.** This Requiem engraving has four empty staves
  named Treble/Alto/Tenor/Bass sitting next to the four that hold the notes.
  A choir part is one with notes *and* lyrics.
- **Comparing renders made under different settings.** An A/B is only worth
  anything if one thing changed. `lib.sing()` takes the tract as a flag so
  both sides come off the same source render.

`lib.py` handles those once. `lib.bands()` is there because comparing two
renders by ear alone has hidden a 20 dB spectral difference more than once,
and comparing them by a single broadband number has hidden the opposite.

## Scripts

| script | what it builds |
|---|---|
| `say.py` | a single-voice MIDI singing given phonemes: `hamlet` ("To be or not to be") and `daisy` (the 1961 IBM 704 demonstration). Reproduces both originals event-for-event. |
| `choral.py` | The general driver: any lyric-bearing score. Splits choir from everything else, renders each the way it has to be rendered, sums dry and puts the hall over the pair. `--choir-only`, `--both` (formant vs tube), `--choir-db N`. |
| `lacrimosa_choir.py` | Mozart, Requiem K.626, Lacrimosa -- a named entry point into `choral.py`. |
| `dies_irae.py` | Mozart, Requiem K.626, Dies Irae. Same, and the reason `--choir-db` exists. |
| `organ.py` | A registered organ score, by the recipe BWV 542 v7 used: church room in BOTH the render and the tail, `hybrid` tuner, -12 dB for headroom. |
| `buxwv161.py` | Buxtehude's Passacaglia as one long crescendo -- the way passacaglias are played. Registration changes at the key changes, found from the ostinato itself. |
| `hammond.py` | A Hammond through a driven Leslie, rendered at four amp drives with nothing else changed. The valve stage is the only variable, so the sweep from clean to overdrive is what is being listened to. |
| `tubeamp_check.py` | What the valve stage actually does, measured rather than asserted: transfer curve, harmonic orders, energy conservation, intermodulation share, and cost. Needs no score. |
| `rhodes.py` | The electric pianos, a Rhodes (GM 4) and a Wurlitzer (GM 5). `--pair` renders the same passage on both, which is the point of having two: one mechanism, and the only real difference is the pickup's curve -- a bell curve whose harmonics fall off a cliff against a 1/d pole whose harmonics fall off geometrically. `--voicing` sweeps the tine's rest position in the magnet's field, which is the falsifiable one: centred, the fundamental disappears and the pickup answers an octave up. `--velocity` plays one phrase at four velocities, because on this voice velocity changes the sound more than the volume. `--control` renders with the pickup's curve bypassed -- a pure sine -- which is what everything else here has to be judged against. `--tremolo` puts the mod wheel up, which on this voice is a stereo pan between the suitcase's two amplifiers and so vanishes in mono. |
| `gm_coverage.py` | How complete each of the 128 GM patches is, 0 to 4, written to `coverage.md`. The class column is read out of `patch_map` so it cannot drift; the ratings are curated in the script. |
| `coverage_html.py` | Renders the same data as the published coverage page, so the page and the table cannot drift apart. Writes `coverage.html`. |
| `grand.py` | The piano bank. An electric grand (GM 2, a CP-70) against the acoustic one, `--honky` for GM 3 at three wheel positions, and `--bright` for GM 1 at four dynamics -- where the gap is widest at pp, because a hard hammer does not need to be hit hard. `--register` is the test: the same figure low, where the short case makes its bass up to twelve times stiffer, and two octaves up, where both pianos use a string of the same length and only the missing soundboard is left. |
| `clavinet.py` | A clavinet (GM 7). `--tone` sweeps the four tone rockers on CC1, darkest to brightest; `--compare` renders the same figure on the harpsichord it used to be. Both are bright keyboard strings and they are not the same instrument. |
| `cymbals.py` | The cymbal family rendered so it can be heard: every plate in the GM set, `--dynamics` for one crash from pp to ff (what moves is brightness, not pitch), `--ride` for a played pattern rather than isolated strokes, and `--bend` for the A/B between the old asserted pitch bloom and the measured zero. |
| `cymbal_check.py` | Do a cymbal's modes bend when it is struck harder? Tracks individual isolated partials by phase derivative across the Iowa cymbal family -- 203 of them -- and finds the drift under a cent, where the class once asserted sixteen. Checks the probe against planted bends first, and shows what DOES drift: the centroid, by more than an octave, which is differential decay. |
| `rhodes_check.py` | The voice's own amplitude and decay laws printed beside the Hamburg measurements: the tonebar fit against ISMA 2014 Table 1, the octave test, the k*D decay law, and what a note costs. No score and no render. |
| `guitar.py` | An electric guitar at four amp drives; `--family` renders all six electrics (GM 26-31); `--fret` plays a phrase with the position shifts left in, which is what fret noise (GM 120) is for; `--acoustic` renders the two acoustics, the measured nylon (GM 24) and the steel-string (GM 25) that borrows its body; `--calibrate` measures the peak a hard strum (and a dug-in low E) makes, so `amp_reference` means something for the guitar and the bass. The passage plays soft and then dug-in, because on this voice that is audible. |
| `guitar_check.py` | The pickup's comb against its geometry, the cabinet's response, why power chords work, and the proof that playing harder breaks up. Needs no score. |
| `levels.py` | How loud each plucked voice is, rendered and measured against the grand piano in its own register. Written after the electric bass shipped 23 dB too quiet. Needs no score. |
| `scotland.py` | Scotland the Brave on the bagpipe voice: the chanter's nine notes, the drones under the whole tune, and grace notes as the instrument's ONLY articulation. `--sharp` renders it where a pipe band actually plays. |
| `riffsym.py` | Ben's own 2001 piece in its three guitar orchestrations (`--all` for all seven). The A/B set to re-render whenever the electric guitar or bass voices move. Reads `~/Downloads/midi`, or `--src DIR`. |
| `reeds.py` | GM 20-23, the free reeds. A free reed has no resonator behind it -- which is what separates an accordion from a pipe organ's reed rank, the class all four used to render as. `--check` measures without rendering. |
| `pipes.py` | GM 72-79. A flue instrument is decided by three things -- open or closed tube, how the jet is aimed, and how much breath misses -- and the four that sat on a generic base differ in all three. A pan pipe is stopped, so it overblows at the twelfth. |
| `ethnic.py` | GM 104-111: six mechanisms that were three classes. A banjo is steel over a drumhead, a shamisen adds the sawari buzz, a kalimba is a plucked cantilever at 1 : 6.267 : 17.55 -- not a bar and not a string. |
| `strings45.py` | GM 44, 45, 46. Pizzicato and harp were the generic plucked string, which has no `formants` at all, so both were rendering with no body whatsoever. Tremolo strings were rendering identically to GM 40. |
| `bass.py` | GM 32 acoustic bass, and GM 43 contrabass -- the same instrument, already measured one bank away. `--arco` is the argument: the same walking line plucked and bowed, one box, two excitations. `--family` for the set. |
| `brass61.py` | GM 61 Brass Section, and the seam between its three measured bodies. It was already routing per register; what was wrong is that it handed over at a SINGLE NOTE, and one semitone across the C4 break moved the spectrum 13.2 dB. |
| `synthbass.py` | GM 38, 39: an oscillator under a resonant low-pass. The third family caught by the generic-plucked-string hole, after the pizzicato section and the harp. |
| `synthbrass.py` | GM 62, 63: a sawtooth through a resonant filter. They sat on the abstract ACOUSTIC brass base -- a bore, a register centre, an effort tilt -- which a synthesiser has none of. 62 is the bright stab, 63 the slower one, which is the SC-55's reading and the only grounding GM gives. |
| `synthstrings.py` | GM 50, 51: a string MACHINE, not a section. Both were routing to the measured string bodies, so they rendered identically to GM 48. The chorus IS the instrument -- fixed offsets swept slowly, against a section's per-note drawn spread. |
| `leads.py` | GM 80-87, the one family that can be EXACT. A sawtooth is not an approximation of anything: it IS the harmonic series at 1/n. The one place an additive engine has an advantage over sampling rather than a handicap. |
| `pads.py` | GM 88-95. All eight were one bowed-string class. What makes a pad a pad is the swell; what separates the eight is that GM's own names point at eight different mechanisms. |
| `effects.py` | GM 96-103, built on the pads -- because most of these ARE pads with one property pushed to the front. Rain echoes, crystal is the most inharmonic voice in the bank, atmosphere breathes, goblins wobble 55 cents. |
| `steelpan_check.py` | Does the modelled pan COUPLE like a real one? Runs the analysis that was run on a real recording (Freesound 742254, CC0). The 1:2:3 tuning was never in doubt; what is measured is the other 23%. |
| `pedal.py` | The damper pedal offline. A three-note file with the pedal held and one without came back BIT-IDENTICAL. Two things have to be true and the second is easy to miss: a pedalled note rings until the pedal lifts, but no longer than until that same string is struck again -- 2658 of Ondine's 4579 pedalled notes, the common case. |
| `bend.py` | Pitch bend offline, and the test that separates its two meanings: does the wheel ever MOVE while the channel sounds? If not it is a temperament and goes on `f0`, so a harpsichord gets it too; if it does it is a gesture and the kernel integrates it. Sankey's twelve channels against A-Team's 200-cent sweep in 57 ms. |
| `tuning_sysex.py` | Writes a temperament into a MIDI file as GM2 Scale/Octave Tuning Adjust -- what Sankey's twelve channels of static bend were a workaround for. Also shows what the message CANNOT carry: a stretched octave, because every C is forced to the same offset. |
| `pipes_live.py` | The bagpipe through the LIVE engine, driven headlessly block by block so what it writes is what the keyboard plays. Four passes with the mod wheel at 0, 42, 85, 127 -- chanter alone, one tenor, two, the full set. Written because Ben played it and the wheel gave vibrato. |

```
python3 examples/say.py daisy /tmp/daisy.mid
python3 singpass.py /tmp/daisy.mid /tmp/daisy.wav --lang english --tube

python3 examples/lacrimosa_choir.py ~/Downloads/MozartLacrimosaSATB.mxl /tmp --both
python3 examples/lacrimosa_choir.py ~/Downloads/MozartLacrimosaSATB.mxl /tmp --orchestra
python3 examples/organ.py ~/Downloads/buxtehude_passacaglia_registered.mid /tmp

python3 examples/tubeamp_check.py
python3 examples/hammond.py /tmp

python3 examples/guitar_check.py
python3 examples/levels.py
python3 examples/riffsym.py
python3 examples/grand.py --compare /tmp
python3 examples/grand.py --register /tmp
python3 examples/grand.py --honky /tmp
python3 examples/grand.py --bright /tmp
python3 examples/clavinet.py --tone /tmp
python3 examples/clavinet.py --compare /tmp
python3 examples/gm_coverage.py
python3 examples/cymbal_check.py
python3 examples/cymbals.py /tmp
python3 examples/cymbals.py --dynamics /tmp
python3 examples/cymbals.py --ride /tmp
python3 examples/cymbals.py --bend /tmp
python3 examples/rhodes_check.py
python3 examples/rhodes.py /tmp
python3 examples/rhodes.py --voicing /tmp
python3 examples/rhodes.py --velocity /tmp
python3 examples/rhodes.py --control /tmp
python3 examples/rhodes.py --tremolo /tmp
python3 examples/rhodes.py --pair /tmp
python3 examples/guitar.py --calibrate
python3 examples/guitar.py /tmp
python3 examples/guitar.py --family /tmp
python3 examples/guitar.py --fret /tmp
python3 examples/guitar.py --acoustic /tmp
```

## A passacaglia is built, not registered

`buxwv161.py` is the worked example for a registration that CHANGES. A
passacaglia is played as one accumulation from Positiv to full -- BWV 582 the
same way -- so the question is only where the changes go, and the answer is
the key changes. The ostinato states itself 28 times in four groups of seven,
transposed D-F-A-D, which the script finds rather than assumes; F major is the
first brightening. One change is not a key change: four-voice quarter-note
chords at 249.5 s, measured as the steadiest stacked writing in the piece, a
cadenza of weight rather than of runs, walking into the final section.

Nothing is ever taken away. That is what makes it a crescendo instead of a
sequence of registrations, and it measures as +10.8 dB from the opening to the
close with the 2-4 kHz band up 21 dB.

## Why organ.py exists at all

BWV 542 v7 was three environment variables on a shell line, and reproducing it
for the next piece meant grepping a session transcript for the command. That is
the whole argument for this directory. The three that mattered:

- **the room has to be set TWICE**, once for `blockrender`'s first-order images
  and once for `roomtail`'s diffuse tail, and to the same value -- otherwise a
  hall's early reflections arrive in front of a studio's tail;
- **`hybrid`, not `hybridharm`** -- both were tried on BWV 542 and hybrid is
  the one that stuck;
- **-12 dB master**, because `roomtail` adds energy and a mix that peaks near
  full scale dry has nowhere to put its room.

A fourth has since joined them: if the score sets CC91, `roomtail` picks up the
send bus on its own and the same command line produces a different tail. That
is the intent, and it is worth knowing when a render will not reproduce.

## Voices and everything else do not render the same way

`singpass.py` filters the WHOLE file -- it is a source-filter pass over a
vocal stem, so an orchestra sent through it is played inside a singer's
mouth. Anything unsung goes through `blockrender` directly (`lib.render_plain`).

Which means a full piece is two renders that have to be put back together,
and the trap there is the room. `blockrender` computes first-order images
only and writes a `.room.json` sidecar saying what the piece fed the hall per
band; the diffuse tail is `roomtail`'s convolution over the sum. Stems are
therefore summed DRY and given the hall once, with their sidecars merged
(`lib.merge_room`) -- a choir and a string section do not feed a room alike,
and a mix that inherits whichever sidecar it found first gets the wrong one.

**CC91 travels in that sidecar too**, and it is the one thing the stem path
cannot fully honour. A reverb send here is a DISTANCE from the microphone, so
`blockrender` writes a per-channel `send` map beside the bands and a
`.send.wav` bus alongside the wav. `merge_room` carries the map through and
warns if two stems disagree -- because once they are summed there are no
channels left to weight, and a summed mix can only stand at one distance. If
the stems genuinely want different ones, render the bus rather than the sum.

## Scores are not included

`lacrimosa_choir.py` takes a score you supply. The music is Mozart and long out
of copyright, but a particular engraving is somebody's work and is not
redistributed from here.

**The Sankey corpus is a stricter case.** John Sankey's terms permit
redistributing his MIDI with his notice, but state that audio "must be derived
from the MIDI files using my matching soundfont on a SoundBlaster 32". Renders
of that corpus made with this renderer are therefore **personal use only and
must not be distributed.** `NOTICE.txt` sits beside the corpus.

## Check for dynamics before trusting a balance

`choral.py` sums the stems at unit gain, which preserves whatever the score
notated -- but engraving exports often notate nothing. LilyPond's Dies Irae
gives every choir note velocity 95 and every first violin 101, one flat value
per staff. Summed as-is that puts the choir 6 dB UNDER the orchestra where the
two play together, and presents an exporter's default as Mozart's balance.

So the script prints each track's velocity spread, and reports the balance
measured only WHERE THE CHOIR SINGS -- that movement is 38% choral, so a ratio
over the whole thing answers a question nobody asked. `--choir-db` then states
the correction out loud rather than burying it in a gain.

Two kinds of number end up in that flag, and they should not be confused.
The Dies Irae's `7` repairs a file with no dynamics at all. The Lacrimosa's
`4` does not repair anything -- that score has real dynamics, eight to ten
velocities across the choir -- it is a balance judgement, made because the
median was fine (+1.3 dB) while the tenth percentile sat at -8.5, under the
strings in exactly the quiet writing the movement is made of. Report the
percentiles, not the mean: a median can be right while the piece is wrong.

## Not yet ported

Neptune's receding all-female chorus. It has no text -- Holst writes it
wordless -- so it needs the registration and the recession, not this pipeline.
