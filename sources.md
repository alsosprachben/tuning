# Reference recordings

The measured numbers in `~/repos/tuning/tonelib.py` — ring times, mode ratios,
harmonic levels — come from these files. Anything in the code that says
"measured" or "Iowa" traces back here. Anything that does **not** say so is an
assertion of mine, and the last section lists which those are.

## Source

**University of Iowa Electronic Music Studios, Musical Instrument Samples (MIS)**
<https://theremin.music.uiowa.edu/MIS.html>

This is the same collection the piano's hammer model was already calibrated
against (see `Steinway.strike_depth` in `tonelib.py`, which cites "the Iowa
reference, an ff sample").

Recording conditions, from the per-instrument pages:

| | |
|---|---|
| Location | Anechoic Chamber, University of Iowa |
| Microphone | Neumann KM 84 cardioid (pre-2012 sets) |
| Mixer / recorder | Mackie 1402-VLZ, Panasonic SV-3800 DAT |
| Format | 16-bit, 44.1 kHz (pre-2012); 24-bit/96 kHz, 3 mics (2012 onward) |

Anechoic matters: the decay times measured below are the *instrument's*, with no
room in them. That is why the gunshot work could treat the hall separately.

**Licence.** The site states the recordings are "freely available" and have been
used "in over 270 research papers", and invites donations to the studio. I did
not find an explicit licence text, so treat attribution to the University of Iowa
EMS as required and re-distribution as unsettled. These files are kept outside
the git repos for that reason as well as for size (426 MB).

## What was downloaded

Base URL: `https://theremin.music.uiowa.edu/sound files/MIS/` (note the space in
the path — it must be percent-encoded as `%20` when fetching).

| file here | source path | used for |
|---|---|---|
| `marimba_C4B4.aif` | `Percussion/Marimba/Marimba.yarn.mf.C4B4.aif` | ring, modes, overtone decay |
| `xylophone_C5B5.aif` | `Percussion/Xylophone/xylophone.hardrubber.mf.C5B5.aif` | ring, modes, strike overtone |
| `vibraphone_C4B4.aif` | `Percussion/Vibraphone/Vibraphone.sustain.mf.C4B4.aif` | modes (ring not measurable) |
| `bells_C6B6.aif` | `Percussion/Bells/bells.plastic.mf.C6B6.aif` | ring, 2nd partial ratio |
| `flute.aiff` | `Woodwinds/flute/Flute.nonvib.mf.C5B5.aiff` | harmonic spectrum |
| `oboe.aiff` | `Woodwinds/oboe/Oboe.mf.C4B4.aiff` | harmonic spectrum, formant |
| `clarinet.aiff` | `Woodwinds/Bbclarinet/BbClar.mf.C4B4.aiff` | odd/even harmonic structure |
| `bassoon.aiff` | `Woodwinds/bassoon/Bassoon.mf.C3B3.aiff` | formant + antiresonance |
| `bassoon_c4.aiff` | `Woodwinds/bassoon/Bassoon.mf.C4B4.aiff` | second register, joint fit |
| `horn.aiff` | `Brass/frenchhorn/Horn.mf.C2B2.aiff` | bell cutoff, joint fit |
| `horn_c4.aiff` | `Brass/frenchhorn/Horn.mf.C4B4.aiff` | **held-out validation** |
| `trombone.aiff` | `Brass/tenortrombone/TenorTrombone.mf.C3B3.aiff` | harmonic spectrum |
| `tuba.aiff` | `Brass/tuba/Tuba.mf.C2B2.aiff` | harmonic spectrum |
| `tp_E3B3.aiff` | `Brass/Bbtrumpet/Trumpet.novib.mf.E3B3.aiff` | joint fit |
| `tp_C4B4.aiff` | `Brass/Bbtrumpet/Trumpet.novib.mf.C4B4.aiff` | held-out check |
| `tp_C5B5.aiff` | `Brass/Bbtrumpet/Trumpet.novib.mf.C5B5.aiff` | joint fit |

Each `.aif`/`.aiff` was converted to 32-bit mono WAV for analysis:

```sh
curl -sS "https://theremin.music.uiowa.edu/sound%20files/MIS/<path>" -o NAME.aiff
sox NAME.aiff -c 1 -b 32 -e signed-integer NAME.wav
```

A file holds one chromatic octave: twelve separate strokes or notes with silence
between, so every measurement begins by segmenting it.

## How each quantity was measured

**Segmentation.** A 20 ms RMS envelope with a Schmitt trigger — the level must
fall back below 2% of peak before another onset can be detected. A plain
threshold gave 478 "strokes" in a 12-note vibraphone file, triggering on decay
ripple.

**Ring time (T60).** Backward Schroeder integration of the energy, then a
straight-line fit between −5 and −25 dB, extrapolated to −60. Two corrections
were needed and both mattered:

- *Truncate at the noise floor first.* Once the instrument decays into the floor
  the energy curve flattens, and a fit that includes the flat part reports an
  enormous decay. Uncorrected this claimed a **xylophone rings 6.37 s**, which is
  absurd for the driest instrument in the orchestra. Floor is estimated from the
  quietest fifth of the tail; integration stops where the signal falls to 10 dB
  above it.
- *Match the frame rate to the instrument.* 20 ms frames cannot resolve a
  xylophone (4 ms used instead), and a glockenspiel rings past the next stroke,
  so its ring was taken from the final stroke with the rest of the file to decay
  into.

**Mode ratios.** Peak-picking against the *known* pitch of the stroke, not the
strongest partial. Picking the strongest peak failed on every instrument with a
weak fundamental — it reported the oboe's f0 as 1299 Hz and the bassoon's as
523 Hz. Pitch is now found by autocorrelation, and even that needs a sensible
search range: the trumpet C5 file came back an octave low until `fmin` was
raised.

**Harmonic levels.** FFT over the middle half of a sustained note (skipping
attack and release), peak within ±3% of each expected harmonic, expressed in dB
relative to the fundamental.

**Strike vs sustain.** Two windows, 0–40 ms and 0.1–0.5 s, compared separately.
This distinction found the xylophone result: its twelfth is +9.4 dB *above* the
fundamental at the strike and −29.5 dB below it by the sustain. A single static
figure would have averaged that away.

## The methodological lesson

Fitting a filter to one note and stopping is not enough, and I nearly shipped a
model that proved it.

The horn's bell high-pass, fitted to C2 alone, gave a 0.8 dB rms fit — excellent.
Tested against `horn_c4.aiff`, which was held back for exactly this purpose, it
predicted the C4 spectrum **23.6 dB wrong, in the wrong direction**. A fixed
filter returns one gain at 392 Hz regardless of which note produced that partial,
so it cannot tilt upward at C2 and downward at C4. The tilt is not all filter:
the source simplifies with register. Fitted jointly to both registers, 3.3 dB.

Every filter fitted here to a *single* register — oboe, tuba, trombone,
saxophones — carries that same risk and should get a second register before it is
trusted as far as the horn and trumpet are.

## What is still assertion, not measurement

- **Vibraphone ring.** Its strokes overlap in the only available file, and the
  one isolated stroke measures 33.7 s, which is the noise floor inflating the fit
  again. The value in the code is mine.
- **Timpani, entirely.** The Iowa collection has no timpani. Its modes are from
  published membrane acoustics; its ring and level are mine.
- **All gains.** The Iowa instruments were recorded on different dates with
  unknown mixer gain, so relative level between instruments is not meaningful
  here. These recordings were used for spectrum and decay only — never for
  balance. The equal-velocity balance in `tonelib.py` remains a convention I
  chose, not a measurement.
- **Celesta, music box, saxophone formants, marimba's third mode**, and the
  clarinet's exact even-harmonic depth: placed by argument between measured
  neighbours, not measured directly.
- **The steelpan's upper ratios and its ring.** Its 1:2:3 tuning and its mode
  LEVELS are now measured against a CC0 recording (see below); the four upper
  ratios and the decay are still mine.

## Strings (added later)

| file here | source path | used for |
|---|---|---|
| `violin_D4A4.aiff` | `Strings/violin/Violin.arco.mf.sulD.D4A4.aiff` | vibrato, harmonic spectrum |
| `violin_G3B3.aiff` | `Strings/violin/Violin.arco.mf.sulG.G3B3.aiff` | vibrato |
| `cello_C2Ab2.aiff` | `Strings/cello/Cello.arco.mf.sulC.C2Ab2.aiff` | low-register spectrum |
| `cello_D3B3.aiff` | `Strings/cello/Cello.arco.mf.sulD.D3B3.aiff` | mid-register spectrum |

These are **solo** instruments, anechoic. They can calibrate one player's spectrum,
vibrato and harmonicity; they say nothing about `section_players`,
`section_spread_cents`, `section_width_m` or `section_onset_ms`, which remain
assertions.

**f0 detection had to be rebuilt before any of it counted.** A spectral peak
locked onto the 2nd or 3rd harmonic — a violin's fundamental is often not its
loudest partial — and reported a cello C2 file as 176-422 Hz when C2-Ab2 is
65-104. Autocorrelation on a short steady window past the attack, parabolic-
interpolated, validated first on synthetic tones with a deliberately weak
fundamental (within 0.2 cents) and on synthetic vibrato (rate within 0.35 Hz,
depth within 1.3 cents).

**Vibrato, 37 steady notes:** rate median 4.72 Hz (10-90%: 2.99-8.33), depth
median +/-7.4 cents (10-90%: 4.0-13.5). Ours: 4.6-6.4 Hz, +/-3.5-5.0 per player.
A soloist vibrates wider than a section player, so a shallower model figure is
defensible; the rate range is narrower than the measured spread.

**Harmonicity.** The Iowa violin's partials sit inside a +/-3% window at every
harmonic to 16 — exactly harmonic, as a bowed string must be. Ours were stretched
to B ~ 4e-4 (a piano bass string): `inharmonicity_coefficient = 0.0` on
BowedStringProperties was dead, because `inharmonicity_dynamic = True` is
inherited from BlownPipeProperties and the renderers answer it by overwriting the
coefficient. Fixed.

**Spectrum, h2-h12 mean difference (ours minus Iowa):** cello C2 -1.0 dB, cello
D3 +1.5 dB, violin D4 **-6.0 dB**. Two differences are real and unmodelled:

- *The bridge hill.* The Iowa violin plateaus at h5-h8 (-10 to -17 dB) where ours
  falls monotonically (-18 to -26). At D4 that is 1.5-2.3 kHz, the violin body's
  broad bridge resonance. We have `bore_corner_hz = 3000` -- a lowpass, not a
  resonance. `FormantBody` already provides Lorentzian poles for the vocal
  voices and is the machinery for it.
- *A weak fundamental down low.* Iowa's cello C2 has its fundamental **11.2 dB
  below** the strongest partial; ours is the strongest. A body that small cannot
  radiate 65 Hz efficiently. Nothing in the string voice models that rolloff.

## Brass, refitted

The four brass voices had each been set from one or two observations, and the
errors compounded. Refitted over h1-h12 against their own recordings by grid
search on (tonal_dampening, bore_corner_hz, bell_cutoff_hz, bell_order):

| | RMS before | after | h1 err | h2-h12 mean |
|---|---|---|---|---|
| tuba | 11.56 dB | **1.25** | -0.2 | +0.8 |
| horn | 8.01 | **1.65** | -0.8 | +1.0 |
| trombone | 3.55 | **1.02** | -1.9 | +0.1 |
| trumpet | 5.29 | **1.06** | +0.6 | -0.1 |

Ben heard the trombone as mellow next to the tuba and trumpet. It was not: the
trombone was the CLOSEST of the four to right, and the tuba was 21 dB hot at h12
(-8.9 where the recording says -29.8). A too-bright tuba makes an accurate
trombone sound dull.

Two structural errors this exposed:

- `bell_cutoff_hz` was 230 Hz on the trombone, BELOW the tuba's 390, when a
  trombone bell is about half a tuba's diameter and its cutoff must therefore be
  higher. It had been fitted to one observation (h3 sitting 7.5 dB over the
  fundamental at C3), which three free knobs can satisfy in many wrong ways. The
  family now runs in the order its bells do: trumpet 1600 > trombone 900 > horn
  and tuba 390.
- Every brass fundamental was 5-13 dB too strong. The bell was doing its job --
  40 dB of suppression at h1 on the trumpet -- but the SOURCE behind it was too
  fundamental-heavy for the bell to correct. Raising bell_order with
  tonal_dampening fixed both together; neither could alone.

`initial_gain` is trimmed per voice by the energy the fit moved (+0.83 tuba,
-0.29 horn, +2.93 trombone, +0.37 trumpet) so the fit changes COLOUR and not
LEVEL: the equal-velocity balance across the orchestra predates it. Verified --
total energy per voice is unchanged to two decimals.

### Brass, refitted ACROSS registers

The first refit used one file per voice and was wrong away from it. Extra
registers downloaded so each could be fitted jointly:

| file here | source path |
|---|---|
| `tbn_E2B2.aiff` | `Brass/tenortrombone/TenorTrombone.mf. E2B2.aiff` (note the space) |
| `tbn_C4B4.aiff` | `Brass/tenortrombone/TenorTrombone.mf.C4B4.aiff` |
| `tuba_C1B1.aiff` | `Brass/tuba/Tuba.mf.C1B1.aiff` |
| `tuba_C3C4.aiff` | `Brass/tuba/Tuba.mf.C3C4.aiff` |

Coordinate descent over (tonal_dampening, octave_dampening, bore_corner_hz,
bell_cutoff_hz, bell_order), scored as RMS over h1-h12 across every register at
once:

| | RMS all registers | worst single register |
|---|---|---|
| tuba | 3.03 -> 1.80 dB | C3C4 4.67 -> 1.29 |
| horn | 9.59 -> 4.79 | C4B4 **13.47 -> 6.32** |
| trombone | 3.78 -> 1.74 | C4B4 6.19 -> 2.48 |
| trumpet | 3.92 -> 1.52 | E3B3 5.85 -> 1.51 |

`octave_dampening` comes out NEGATIVE for the trombone and trumpet (-0.10):
brighter with pitch and effort, which is what a brass instrument does and what a
single-register fit cannot see. The horn stays the worst fit at 4.79 dB -- it has
only two registers and its timbre changes more across them than this model shape
can follow.

**The horn is not in the brass section.** Measured at the same register (C4-B4)
the Iowa horn's spectral centroid is 492 Hz against the Iowa trombone's 891: a
real horn is 45% darker than a real trombone. Correct for a horn, and wrong for
the middle of a section, where it read as a hole. GM 61 is trumpets and
trombones; the horn keeps program 60.

### Viola and double bass, measured

These two were the last interpolations in the string family — the viola scaled
from the violin by body length, the bass from the cello. Both now measured.

| file here | source path |
|---|---|
| `viola_C3B3.aiff` | `Strings/viola/Viola.arco.sulC.mf.C3B3.aiff` |
| `viola_C4B4.aiff` | `Strings/viola/Viola.arco.sulC.mf.C4B4.aiff` |
| `viola_C5B5.aiff` | `Strings/viola/Viola.arco.sulA.mf.C5B5.aiff` |
| `bass_E1B1.aiff` | `Strings/doublebass/Bass.arco.mf.sulE.E1B1.aiff` |
| `bass_C2B2.aiff` | `Strings/doublebass/Bass.arco.mf.sulA.C2B2.aiff` |
| `bass_C3B3.aiff` | `Strings/doublebass/Bass.arco.mf.sulG.C3B3.aiff` |

(The viola files are named `arco.sulX.mf.RANGE` — dynamic AFTER the string, not
before it as every other family does.)

**Three of five interpolated resonance positions were wrong.**

| | interpolated | measured |
|---|---|---|
| viola bridge hill | 1950 Hz | 1920-2283, +10.7 dB — close |
| viola low body | 600 Hz | 480-679 is a DIP; peaks at 430 and 1030 |
| bass lowest | 105 Hz | 85-101, +8.4 dB — close |
| bass middle | 480 Hz | 480-571 is a DIP; peak at 190, +8.4 |
| bass upper | 1150 Hz | 1142-1358 is flat; peak at 1615-1920, +6.6 |

Scaling by body length got the *lowest* resonance and the *bridge hill* about
right, and put the middle ones on top of actual dips.

Fitted jointly across all three registers, formant AMPLITUDES included: shape
alone stalled at 7.6 dB, because amplitudes read off a pooled spectrum are in the
wrong scale for a model that has its own tilt underneath them.

| | RMS h1-h12 |
|---|---|
| viola | 7.56 -> **4.65 dB** |
| double bass | 7.77 -> **4.24 dB** |

which puts them in family with the cello (4.95) rather than the violin (2.03).
On the bass the fit reduced the 190 and 880 poles to almost nothing (0.06, 0.03):
what carries that instrument is the 93 Hz body and the 1750 Hz upper resonance.

`initial_gain` trimmed -0.52 dB (viola) and +1.01 dB (bass) so the fit changes
colour and not level.

### Woodwinds, fitted across registers

| file here | source path |
|---|---|
| `clar_D3B3.aiff` | `Woodwinds/Bbclarinet/BbClar.mf.D3B3.aiff` |
| `clar_C5B5.aiff` | `Woodwinds/Bbclarinet/BbClar.mf.C5B5.aiff` |
| `clar_C6B6.aiff` | `Woodwinds/Bbclarinet/BbClar.mf.C6B6.aiff` |
| `flute_B3B4.aiff` | `Woodwinds/flute/Flute.nonvib.mf.B3B4.aiff` |
| `flute_C6B6.aiff` | `Woodwinds/flute/Flute.nonvib.mf.C6B6.aiff` |
| `oboe_Bb3B3.aiff` | `Woodwinds/oboe/Oboe.mf.Bb3B3.aiff` |
| `oboe_C5B5.aiff` | `Woodwinds/oboe/Oboe.mf.C5B5.aiff` |

| | RMS h1-h12, before -> after |
|---|---|
| clarinet | 16.10 -> **6.61 dB** (4 registers) |
| flute | 9.27 -> **3.28** (3 registers) |
| oboe | 10.14 -> **4.55** (3 registers) |

**The clarinet's even-harmonic depth is no longer an assertion, but it cannot be
a constant either.** -26.5 dB came from one register, where the evens really are
24-38 dB down; across the clarion and altissimo the same number left the voice
12 dB too bright. A clarinet overblows at the TWELFTH, so an even harmonic of the
sounding pitch in the chalumeau is an odd harmonic of the tube in the clarion --
one number cannot describe both, and -8.0 is the compromise. The residual sits
near 6-7 dB in every register rather than being large in one, which is the
signature of a model shape running out, not of a mis-set knob.

The clarinet also had NO lowpass at all (`bore_corner_hz = 0`), which is what let
its top run away.

**A measurement bug found here invalidated an earlier reading.** The harmonic
peak-picker used `|f - h*f0| < 0.03*f0` -- an absolute window 3% of the
FUNDAMENTAL wide, not of the harmonic. On a stretched series that misses
everything above about h3, and it read the flute as 22 dB TOO DARK when the truth
was that it is too BRIGHT. Only the flute was affected: brass, clarinet, oboe and
the single-player strings are all exactly harmonic, verified.

Saxophone `tonal_dampening`, `octave_dampening`, `formant_floor` and
`initial_gain` are now PINNED at their pre-fit values. They used to be inherited
from the oboe, and there is no saxophone recording here -- a measured fit for one
instrument should not silently redefine an unmeasured one.

### Saxophone, measured

The last wind family with no reference at all, and the one whose formants
sources.md listed as an assertion.

| file here | source path |
|---|---|
| `sax_s_Ab3B3.aiff` | `Woodwinds/sopranosaxophone/SopSax.NoVib.mf.Ab3B3.aiff` |
| `sax_s_C4B4.aiff` | `Woodwinds/sopranosaxophone/SopSax.NoVib.mf.C4B4.aiff` |
| `sax_s_C5B5.aiff` | `Woodwinds/sopranosaxophone/SopSax.NoVib.mf.C5B5.aiff` |
| `sax_a_Db3B3.aiff` | `Woodwinds/altosaxophone/AltoSax.NoVib.mf.Db3B3.aiff` |
| `sax_a_C4B4.aiff` | `Woodwinds/altosaxophone/AltoSax.NoVib.mf.C4B4.aiff` |
| `sax_a_C5Ab5.aiff` | `Woodwinds/altosaxophone/AltoSax.NoVib.mf.C5Ab5.aiff` |

**The asserted formant positions were right.** 900 and 2000 Hz, placed by bore
size between the bassoon and the oboe, against measured peaks at ~870 (+8.0 dB)
and ~1850 (+4.4). What was wrong was the tilt: h2-h12 ran 7-10 dB hot. Two
features were missing — a third resonance near 3100 (+5.1) and a DIP at
1200-1427 (-7.6), which needs an antiformant since a list of poles can only add.

**Fitted on both instruments together.** Fitting the soprano alone and holding
the alto out gave soprano 3.07 dB and alto 6.07; fitting both gives 3.78 and
4.77. One class covers programs 64-67, so the compromise that serves the family
beats the fit that serves one member — and the corpus only plays the soprano, so
65-67 would otherwise have silently inherited a soprano.

### Guitar, measured -- and identified

The instrument had to be identified before it could be used. Iowa's guitar page
documents NOTHING about it: the only prose on the page is the site-wide donation
notice and the file format note. GM has three acoustic guitars (24 nylon, 25
steel, 26 jazz) and they are not interchangeable, so the choice was measured.

| file here | source path |
|---|---|
| `gtr_sulE.E2B2.aiff`  | `Piano_Other/guitar/Guitar.mf.sulE.E2B2.mono.aif` |
| `gtr_sulE.C3B3.aiff`  | `Piano_Other/guitar/Guitar.mf.sulE.C3B3.mono.aif` |
| `gtr_sulA.A2B2.aiff`  | `Piano_Other/guitar/Guitar.mf.sulA.A2B2.mono.aif` |
| `gtr_sulA.C3B3.aiff`  | `Piano_Other/guitar/Guitar.mf.sulA.C3B3.mono.aif` |
| `gtr_sulD.D3B3.aiff`  | `Piano_Other/guitar/Guitar.mf.sulD.D3B3.mono.aif` |
| `gtr_sulD.C4Ab4.aiff` | `Piano_Other/guitar/Guitar.mf.sulD.C4Ab4.mono.aif` |
| `gtr_sulG.G3B3.aiff`  | `Piano_Other/guitar/Guitar.mf.sulG.G3B3.mono.aif` |
| `gtr_sulG.C4B4.aiff`  | `Piano_Other/guitar/Guitar.mf.sulG.C4B4.mono.aif` |
| `gtr_sulB.B3.aiff`    | `Piano_Other/guitar/Guitar.mf.sulB.B3.mono.aif` |
| `gtr_sulB.C4B4.aiff`  | `Piano_Other/guitar/Guitar.mf.sulB.C4B4.mono.aif` |
| `gtr_sul_E.E4B4.aiff` | `Piano_Other/guitar/Guitar.mf.sul_E.E4B4.mono.aif` |
| `gtr_sul_E.C5B5.aiff` | `Piano_Other/guitar/Guitar.mf.sul_E.C5B5.mono.aif` |

**It is nylon.** Two independent lines agree. The files are named in classical
`sul` notation, six strings at 19 frets each. And over the six OPEN strings
(full length, so no fret confound) the h2-h8 energy relative to h1 runs

    E2 +25.2   A2 -3.5   D3 +3.7   G3 +0.4   B3 -6.0   E4 -9.8 dB

with nothing above 8 kHz anywhere (-46 to -61 dB relative to total). The top two
strings are the DARKEST on the instrument. Plain steel trebles are the brightest
strings on a steel-string acoustic, and its bronze-wound basses put real energy
past 8 kHz; dark fundamental-dominant trebles over rich wound basses is the
classical guitar's signature.

**A test that does NOT work, recorded so it is not tried again.** The obvious
discriminator is where the wound/plain boundary sits -- a classical winds E-A-D
and leaves G-B-E plain, a steel-string winds E-A-D-G and leaves only B-E. Three
of Iowa's strings overlap at C4-Ab4, so they can be compared at identical
pitches, and they give D -14.8, G -12.9, B -5.3 dB. But at a FIXED PITCH the
lower string is fretted further up the neck, and that dulls it whatever it is
wound with. The confound is the same size as the effect. Discarded.

**The licence question in this file is settled.** Iowa states the samples "may be
downloaded and used for any projects, without restrictions." Attribution to the
University of Iowa Electronic Music Studios is still the decent thing.

**What the fit found: the plucked voice had no body at all.**
`PluckedStringProperties` is a function of harmonic NUMBER alone, so it produced
the same ladder at every pitch -- 1 dB of variation from E2 to E4 -- where the
real instrument moves enormously across its range because its resonances stay
put while the harmonics slide through. Pooling every harmonic of every note by
ABSOLUTE frequency, the model was up to 19.7 dB too quiet at 216 Hz and 10 dB
too loud above 7 kHz.

**A HARMONIC LADDER ALONE DOES NOT CONSTRAIN A PLUCKED STRING, and the first fit
here was wrong because of it.** The harmonics run out long before the instrument
does: on the low E, h32 is still only 2.6 kHz, so everything above that is
extrapolation. The first fit scored 10.13 dB on the ladder -- a big win over the
body-less 15.78 -- and rolled the top off so hard that the broadband energy above
4 kHz landed 19 dB below the recording. THE METRIC IMPROVED WHILE THE SOUND GOT
WORSE, and it was caught by ear on an isolated render, not by any number I was
watching.

Two things had to change. The noise floor was being estimated as the median above
15 kHz OF THE ANALYSIS WINDOW ITSELF, which on a decaying pluck is signal, not
floor; it masked out real harmonics and left about 18 per note. Iowa's true floor
is -92 to -133 dBFS and its SNR above 8 kHz is +52 to +85 dB, so that content is
real, and measured against the file's quietest passage a median of 32 harmonics
per note survive. And the objective now carries the BROADBAND energy above 2, 4
and 8 kHz over 100 ms from the pluck on the six open strings -- an integral,
which has the signal-to-noise that the individual high harmonics do not.

    vs the Iowa guitar        h1-h32 shape     >2/4/8 kHz energy
      no body (as it was)        15.78 dB          14.17 dB
      ladder-only fit            10.13             17.68     <- worse
      shipped                    11.38              4.79

1.25 dB of ladder given up for 12.9 dB of top end; the >8 kHz error comes out at
0.30 dB. Per-note gain removed throughout, so the shape column measures colour
and never level.

**The pluck comb is PINNED, not fitted, and this is the same trap again.**
Letting `plucked_harmonic` and `pluck_dampening` float scored better by driving
`plucked_harmonic` past the last fitted harmonic, which DELETES the comb rather
than fitting it. A player working up a chromatic scale
moves the plucking point note to note, so POOLING AVERAGES THE COMB AWAY. The
optimiser was fitting the measurement, not the instrument. 1.1 dB left on the
table to keep the physics.

Programs 25-31 deliberately keep the body-less family base. A steel-string is a
measurably different instrument and 26-31 are electrics, whose colour is an
amplifier's rather than a box's -- the saxophone rule again: a measured fit for
one instrument must not silently redefine an unmeasured one.

### Clarinet family, measured -- three instruments to find one law

The clarinet's own docstring had recorded the defect and stopped there: one
`even_harmonic_db` cannot describe both the chalumeau and the clarion, because
the instrument overblows at the TWELFTH, so the residual sat near 6-7 dB in
every register at once. This is the fix, and it needed the family.

| file here | source path |
|---|---|
| `clar_bb_D3B3/C4B4/C5B5/C6B6.aiff` | `Woodwinds/Bbclarinet/BbClar.mf.<range>.aiff` |
| `clar_bb_silence.aiff`             | `Woodwinds/Bbclarinet/BbClar.ambient.silence.aiff` |
| `clar_eb_G3B3/C4B4/C5B5/C6B6.aiff` | `Woodwinds/Ebclarinet/EbClar.mf.<range>.aiff` |
| `clar_eb_silence.aiff`             | `Woodwinds/Ebclarinet/EbClar.ambient.silence.aiff` |
| `clar_bs_Db2Bb2/B2Bb3/B3Bb4/B4Bb5.aiff` | `Woodwinds/bassclarinet/BassClarinet.mf.<range>.aiff` |

**Iowa ships an `ambient.silence` recording for the Bb and Eb.** That is the
right noise floor, and it is what the guitar should have used. Use it.

**Iowa names transposing instruments by SOUNDING pitch.** Verified by measuring
the first note of six files against the filename: `BbClar.mf.C4B4` starts at 258
Hz, `BassClarinet.mf.Db2Bb2` at 68 Hz. No transposition correction.

**The measurement.** Even-minus-odd balance, 133 notes, concert C#2 to B6:

    below C3   -25.3 dB        C5-C6      +4.5 dB
    C3-C4      -14.9           above C6   +8.1
    C4-C5       -5.9           +8.33 dB per octave

A 33 dB swing that CHANGES SIGN -- above C5 a clarinet's even harmonics are
STRONGER than its odd ones. The old -8.0 constant is right only around C4-C5 and
left the model +14.8 dB out at the bottom and -11.1 at the top.

**Why three instruments and not one.** The balance tracks ABSOLUTE FREQUENCY, not
each instrument's own register break: the bass clarinet crosses zero at the same
concert pitch as the Bb (~480 Hz) rather than an octave lower, where its own
chalumeau/clarion transition actually sits. One instrument cannot separate those
two hypotheses -- they are the same curve on a single instrument. This is the
first fit here where the extra instruments bought a LAW rather than more data.

**Fitted on the Bb alone** (GM 71 is a Bb clarinet, and it spans 3.3 octaves and
four registers by itself), with the Eb and bass HELD OUT ENTIRELY:

                          shape      HF   even/odd
    Bb          before     8.55   13.45      9.21
    Bb          after      8.45    4.16      5.10
    Eb + bass   before     8.54   22.09     10.06     <- never seen
    Eb + bass   after      9.65   10.70      5.16

Both targeted quantities roughly halve on instruments the fit never saw.
Register error is now within +/-2.4 dB everywhere. Aggregate shape drifts 1.1 dB
on the held-out pair, as expected: the bore cutoff was fitted to the Bb.

**The even/odd balance had to go in the OBJECTIVE explicitly.** A first attempt
left it to the aggregate shape RMS, which barely feels it -- that fit flattened
the register slope correctly (26 dB span down to 8) and then sat 6 dB BIASED,
trading one systematic error for another. Same lesson as the guitar's top end: if
a quantity is the point of the fit, put it in the objective.

`max_harmonic` went 32 -> 64: h32 is only 2.6 kHz on the bass clarinet's bottom
notes, where the recording carries 39 harmonics clear of the floor.

### Flute family, measured -- and a NEGATIVE result worth keeping

| file here | source path |
|---|---|
| `fl_fl_B3B4/C5B5/C6B6/C7.aiff` | `Woodwinds/flute/Flute.nonvib.mf.<range>.aiff` |
| `fl_al_G3B3/C4B4/C5B5/C6G6.aiff` | `Woodwinds/altoflute/AltoFlute.mf.<range>.aiff` |
| `fl_bs_C3B3/C4B4/C5Bb5.aiff` | `Woodwinds/bassflute/BassFlute.mf.<range>.aiff` |

No `ambient.silence` take exists for the flutes, so the floor comes from each
file's own quietest 200 ms. Use the NONVIB flute: vibrato smears the harmonics.

**THE FLUTE HAS NO REGISTER LAW, and that is the finding.** Running the same
test that paid off on the clarinet -- measure the quantity across three
instruments of a family and see whether it tracks absolute pitch -- gives a flat
answer here. Spectral tilt sits near -15 dB per doubling of harmonic across all
four octaves; the three instruments agree closely at the same concert pitch
(261.6 Hz: bass -15.5, alto -15.5, concert -12.5); and the slope against pitch
is only -0.45 dB/octave with the three instruments disagreeing on its SIGN.

Physically that is what an open pipe should do. The clarinet's law comes from a
stopped cylinder ceasing to be stopped as the tonehole lattice opens; a flute is
open at both ends in every register and has no such transition.

So `octave_dampening = 0.3` was a register dependence in the MODEL that is not in
the INSTRUMENT. The independent fit put it at -0.013. That is the useful kind of
negative result: a measurement predicted a parameter value before the optimiser
was run, and the optimiser agreed.

Fitted on the CONCERT flute alone (GM 73), alto and bass held out entirely:

                          shape      HF
    concert     before     5.62    7.39
    concert     after      5.75    3.63
    alto+bass   before     7.36   12.11    <- never seen
    alto+bass   after      6.52    6.68

Broadband error halves on the fitted instrument and both held-out ones, and the
held-out shape improves as well. Concert-flute shape goes 0.13 dB the wrong way,
which is the price of the top end being right.

### The low instruments: routing a patch to the instrument that can play the note

A General MIDI patch is a FAMILY. "Clarinet" below sounding D3 is a bass
clarinet part -- a Bb clarinet has no such notes -- and "Trombone" below C2 is a
bass trombone's. Those notes used to be the small instrument extrapolated into a
register it does not have, which is exactly the register a composer reaches for
the big one. `SOLO_SPLIT` in patch_map now routes nine solo patches by note.

| file here | source path |
|---|---|
| `clar_bs_Db2Bb2/B2Bb3/B3Bb4/B4Bb5.aiff` | `Woodwinds/bassclarinet/BassClarinet.mf.<range>.aiff` |
| `tb_bs_Db1B1/C2B2/C3B3/C4G4.aiff` | `Brass/basstrombone/BassTrombone.mf.<range>.aiff` |
| `tb_tn_E2B2/C3B3/C4B4/C5.aiff` | `Brass/tenortrombone/TenorTrombone.mf.<range>.aiff` |
| `fl_al_G3B3/C4B4/C5B5/C6G6.aiff` | `Woodwinds/altoflute/AltoFlute.mf.<range>.aiff` |
| `fl_bs_C3B3/C4B4/C5Bb5.aiff` | `Woodwinds/bassflute/BassFlute.mf.<range>.aiff` |
| `hn_Bb1B1/C2B2/C4B4/C5F5.aiff` | `Brass/frenchhorn/Horn.mf.<range>.aiff` |

Note the space in `TenorTrombone.mf. E2B2.aiff` and `BassTrombone.mf. Db1B1.aiff`
-- URL-encode it as `%20` or the fetch 404s.

**Two rules decide the boundaries, and both are Ben's.**

Each boundary is the MAIN instrument's lowest NORMALLY-WRITTEN note, so the main
instrument keeps every note a part could actually be written for and the
substitute appears only where it physically stops. That caught one error: the
trombone was switching at E2, but nearly every orchestral tenor has an F
attachment and parts are routinely written to C2. The tenor now holds to C2 --
four semitones below anything Iowa recorded for it. Extrapolating a fitted model
that far beats changing instrument where a player would not, which means
"measured everywhere" and "correct instrument everywhere" are not the same goal.

And it is DOWNWARD ONLY. A high tuba note is still a tuba. Below the bottom is
impossible -- the string is not there, the tube cannot be lengthened -- so a
part written there is unambiguously for another instrument. Above the top is
merely hard: players go there, and it should sound like that instrument
straining rather than turn into a smaller one.

**COVERAGE IS OF THE KEYBOARD, NOT OF THE COLLECTION.** Sizing this work by
corpus notes says clarinet 240, trombone 59, flute ZERO -- and the flute split
looks like dead code. That is the wrong question now that live.py exists: a
player can select any patch and play the whole keyboard. A corpus is a sample;
an instrument is a promise.

**Results.** Each low voice was fitted to its OWN recording, never guessed from
its sibling:

    BassClarinetProperties   Bb class 11.27 / 16.37 dB -> 9.95 / 3.72
    BassTromboneProperties   tenor class HF 5.90 -> 4.11
    AltoFluteProperties      6.62 / 5.75 -> 6.60 / 5.37   (narrow fit)
    BassFluteProperties      6.40 / 7.67 -> 5.54 / 5.27   (narrow fit)

The bass clarinet independently wants `even_harmonic_db_per_octave` = 7.331
against the Bb clarinet's 6.794 -- the register law holding on a SECOND
instrument, fitted separately, which is the strongest evidence it is physics.

The two flutes get NARROW fits -- corner, cutoff, order, ceiling only, tilt
inherited -- because the family measurement found no register law and
near-identical tilt across all three. The alto's gain is honestly marginal and
its docstring says so; it is there because it is the right instrument for
G3-A#3, not because it rescues a number.

**A NEAR MISS WORTH RECORDING.** The bass trombone first scored HF 11.98 ->
10.62 and looked not worth its own class. That was an artefact: `max_harmonic`
had been PINNED at 96 in its fit, and at C#1 that truncates the instrument at
3.3 kHz. With both classes given enough harmonics the real answer appeared --
tenor 5.90, bass 4.11. ALWAYS CHECK A DISAPPOINTING FIT FOR A CEILING YOU
IMPOSED YOURSELF before concluding the effect is not there.

`max_harmonic` now scales with how low an instrument plays, chosen so each
reaches about the same ABSOLUTE frequency: tenor trombone 96 (7.9 kHz at E2),
horn 128 (7.4 kHz at Bb1), bass clarinet 128, bass trombone 256 (8.9 kHz at
C#1). The old value of 32 came from `StoppedPipeProperties` -- an ORGAN PIPE
base class -- and it was silently truncating every brass voice.

### French horn, re-measured across four registers

Four registers of `Horn.mf` (Bb1B1, C2B2, C4B4, C5F5, 32 notes) against the two
the previous fit used, which had left it the weakest brass fit on record.
HF 17.24 -> 4.75 dB, shape 6.32 -> 6.75.

**Iowa has NO mf take for C3-B3** -- only pp and ff -- so the fit interpolates
across the middle of the range. Mixing the ff take in would have put a different
dynamic's spectrum into an mf fit, which is a worse error than the gap.

**bore_order = 0.50 is PHYSICS I first misread as a degenerate fit.** The
optimiser drove it to its lower bound and I assumed it was exploiting a
degeneracy, as the guitar's pluck comb had been. It was not: viscothermal wall
losses in a tube scale as the SQUARE ROOT of frequency (Kirchhoff), and a horn
is 5.5 m of tubing, so sqrt(f) is the law it was reaching for. The error surface
is flat between 0.4 and 0.5 (HF 4.42 vs 4.48), so the physical value is free.
The other brass still carry steeper exponents that nobody has checked this way
-- and a tuba is longer than a horn, so it should want it more.

Decomposed: the harmonic ceiling alone gives 17.24 -> 7.78, and keeping the old
800 Hz bore while taking every other fitted value leaves 13.58. Both parts real.

### Effort: the pp/mf/ff axis, and the first use of Iowa's dynamics

Every fit in this file until now used `mf` alone. Iowa records pp, mf and ff for
every instrument, and that is the EFFORT axis -- how hard the player is working,
which is a timbre change first and a level change second.

Measured as tilt-of-the-harmonic-ladder against level, per note, across both
dynamic steps:

    tenor trombone  +0.68 dB of flattening per dB of level   66 pairs   r 0.66
    French horn     +0.44                                    46 pairs   r 0.35
    Bb clarinet     +0.13                                    75 pairs   r 0.29

That family split IS the result: brass blooms with effort and a clarinet very
nearly does not, which is most of what makes brass sound like brass. Before
this, velocity was a pure GAIN for every wind, brass and bowed voice in the
model -- only the piano's hammer changed colour with force.

`effort` is dB of level deviation from the dynamic a class was fitted at, so mf
stays the neutral point and every existing fit is untouched at effort 0.

**DRIVE IT FROM A RELATIVE SIGNAL, NEVER ABSOLUTE VELOCITY.** Ben's correction,
and it would have gone badly wrong: in real MIDI a track's velocities are
largely set to BALANCE that instrument against the others, not to say how hard
the player is blowing. Map brightness to raw velocity and every conservatively
mixed brass part goes permanently dull -- and it looks like a bad spectral fit
rather than a bad premise. Offline, effort is `40*log10(vel / channel median)`.
On heroic~1 both trombone parts sit at a constant velocity 120 and the driver
correctly produces ZERO effort; across the collection 69 of 94 eligible parts
are flat like that.

Which is why the LIVE path is where this pays. live.py already turned aftertouch
into tilt, but `press_tilt` was one chosen constant of 0.30 -- a ratio of 0.226
for every voice, less than half a trombone's and nearly double a clarinet's. It
is now the measured value per voice, grouped per NOTE because SOLO_SPLIT makes
one clarinet part two instruments. Unmeasured families keep the old constant
rather than losing the effect, since effort_tilt 0.0 would switch aftertouch
colouring off entirely.

STILL UNMEASURED: trumpet, tuba, the saxophones and the double reeds all have
full pp/mf/ff at Iowa and none of them has been done. The trumpet and tuba
currently inherit the 0.55 brass centre; the reeds sit at 0.0 and fall back.

### A test that does NOT work: upper-range effort from Iowa

Recorded so it is not attempted again. The question is what an instrument should
sound like ABOVE its normal range -- a tuba at MIDI 80 -- since SOLO_SPLIT fixes
the bottom of every patch and nothing fixes the top.

Iowa cannot answer it. It records each instrument across its normal range only,
because that is what players play, so there is no reference for the region in
question and any model built there is an assertion.

Two checks first said there was no defect to fix anyway. Spectral tilt gets
DARKER toward the top of every instrument measured (tenor trombone -1.9 ->
-16.4, horn -1.6 -> -19.6) -- harmonics running past a fixed bore roll-off,
which a linear octave_dampening already expresses -- and the curvature has no
consistent sign across seven instruments. And the model's own residual is not
concentrated at the top: clarinet 10.21/7.23/6.27 by thirds of its range, flute
6.00/5.30/5.31, trombone 4.10/5.12/5.71. Mixed.

The effort axis is the principled route instead: a note above the range is the
instrument pinned at the top of a MEASURED effort curve, not a guess about
territory nobody recorded.

### The pipe family: three bodies, and a patch the organ had borrowed

No new recordings. This is a MODELLING correction found by listening, and the
only classes in tonelib whose numbers are asserted rather than fitted.

Programs 72-79 were collapsing to TWO voices. Everything open-piped (flute,
recorder, shakuhachi, whistle, piccolo) shared one; the pan flute, blown bottle
and ocarina shared the stopped-pipe voice, which is the ORGAN base class.

**A vessel flute is not a pipe.** An ocarina and a blown bottle are Helmholtz
resonators: the air in the neck moves as a lump against the springiness of the
air in the cavity, a mass on a spring. ONE resonance, no series above it, which
is why an ocarina is close to a pure tone. Giving them a stopped pipe gave them
the odd-harmonic spectrum of an organ rank. At C5 the three bodies now read:

    73 Flute      (open pipe)   h1:+0  h2:-9   h3:-15  h4:-20
    75 Pan Flute  (stopped)     h1:+0  h3:-20  h5:-30  h7:-36   <- odd only
    79 Ocarina    (vessel)      h1:+0  h2:-22  h3:-37  h4:-47

The pan flute keeps the stopped voice, correctly: a pan pipe IS closed at the
bottom.

**Same body, different EDGE.** An ocarina has a fipple -- a moulded windway
aiming breath at a sharp labium, as a recorder does -- which couples efficiently,
so the tone dominates and it sings. Blowing across a bottle has no windway and
no labium: a turbulent jet across an opening, most of which never couples into
the resonance. So a bottle is mostly BREATH with a weak tone inside it, the
chiff carries the sound rather than starting it, and it SUSTAINS because you
keep blowing. Measured on the built voices, energy away from the harmonic peaks
over the first 200 ms:

    79 Ocarina         0.0% inharmonic   noise/tone -37.8 dB
    75 Pan Flute       0.0%                         -35.3
    73 Flute           0.1%                         -32.8
    76 Blown Bottle   15.7%                          -7.3
   121 Breath Noise   29.8%                          -3.7

GM 121 is the reference for a chiff standing alone -- breath with no note in it
at all -- and the bottle's chiff_volume of 2.0 sits deliberately under its 2.4.

**79 had been the organ's flue rank.** The Bach files here write program 79 on
every track, 7714 notes across 15 files, and the code honoured that. Ben's call:
BE A SUPERSET OF GENERAL MIDI. If a file orchestrates an organ out of wind
patches, let it -- whoever made it chose those patches knowing how they sound on
real gear, and an ocarina is a soft pure tone, which is exactly why it reads as
a flue rank. Giving them a real ocarina serves that intent better than lending
them our organ, and it means selecting "Ocarina" on the live TUI stops handing
you a stopped pipe.

**The piccolo cascade** used the FLUTE's bottom note, which made programs 72 and
73 the same mapping and sent a low piccolo note straight to a bass flute two
octaves down. It is now the piccolo's own D5, so a low piccolo part descends
piccolo -> flute -> alto -> bass. Nothing audible changes yet: Iowa has no
piccolo, so 72 and 73 still share OpenPipeProperties. What changed is what the
routing MEANS, and what a fitted PiccoloProperties would hang from.

`VesselFluteProperties` and its two children are NOT MEASURED and say so in
their docstrings. Iowa has no ocarina and no bottle. Every other class in
tonelib is fitted to a recording; these come from how the instruments are
played. If a reference turns up, they are the ones to fit.

### The patch was only read at the END of the file

Found because Ben said the four vessel/pipe voices "all sound the same". They
did, and the voices were not the reason.

`blockrender.parse()` kept `ch_prog` as ONE program per channel, overwritten by
each program_change, and the note loop read `ch_prog.get(ch, 0)` at render time.
So every note on a channel rendered with whatever patch that channel happened to
END on. A demo file switching program four times on one channel rendered all
twenty notes with the fourth.

Not just a test-file problem. **passac.mid cycles channel 0 through strings,
recorder, clarinet, trumpet, drawbar organ and music box, and all 2161 of its
notes were rendering as strings.** 2799 notes across three files in the
collection were being played on the wrong instrument, and had been for as long
as this code existed.

The patch is now SNAPSHOTTED AT NOTE-ON, exactly as the CC7/CC11/CC10 values
beside it already were, and travels with the note.

That exposed a second bug immediately. The organ registration rows were built
from `ch_prog` too, so a channel that is an organ for only PART of a piece had
no rows -- and once notes carried their own patch, its organ notes raised a
KeyError instead of silently borrowing the wrong voice. `parse()` now returns
every program a channel used and the registration pass builds rows for the first
registerable one. Channel 0 of passac.mid is a drawbar organ for one section.

**TWO PROCESS FAILURES HERE, both worth not repeating.**

`cmp` against a MISSING file reports "differs", and twice in one session that
produced a false conclusion: once during the class rename (sending me hunting a
behaviour change that did not exist) and once here, where the after-render had
crashed and "passac differs, as it must" was reported from a file that was never
written. ALWAYS check both files exist before comparing.

And four "different" voices were sent for listening without ever checking they
produced different partial counts -- a two-line check that would have caught the
program-change bug before Ben had to. The same applies to silence: an earlier
pair of renders was trimmed from a window where the instrument was not playing,
normalised silence to silence, and shipped. CHECK THE RENDER HAS CONTENT AND
DIFFERS BEFORE SENDING IT.

### Percussion: what Iowa can serve, and what it cannot

431 files across eight pages -- cymbals (162), hand percussion (74), gongs and
tam-tams (55), crotales (50), tambourines (39), found objects -- all at pp/mf/ff.

**THERE IS NO DRUM KIT.** No snare, no bass drum, no toms. That is 9630 of the
collection's 12781 percussion notes, and it is not a gap measurement can close.
Iowa serves about 25% of what actually gets played.

| file here | source path |
|---|---|
| `hp_5.5wb/6.5wb/8.5wb/10wb.mf.aiff` | `Percussion/hand percussion/woodblocks/<n>wb.mf.aif` |
| `hp_clave1/2/3.mf.aiff` | `Percussion/hand percussion/claves/clave<n>.mf.aif` |
| `hp_castanet1/2.mf.aiff` | `Percussion/hand percussion/castanets/castanet<n>.mf.aif` |
| `hp_6triangle/8triangle.mf.aiff` | `Percussion/hand percussion/triangles/<n>triangle.mf.aif` |
| `hp_guiro.away/toward.mf.aiff` | `Percussion/hand percussion/guiro/guiro.<dir>.mf.aif` |
| `cr_<pitch>.ff.aiff` (25) | `Percussion/crotales/crotale.<pitch>.ff.aif` |
| `cy_ride.{pp,mf,ff}.aiff`, `cy_ridebell.*`, `cy_ride_bow` | `Percussion/cymbals/suspended cymbals/stick/21ride.stick.{normal,bell}.<dyn>.aif`, `.../bowed/` |
| `hh_{normal,footclose,footsplash,shoulder,bell}.<dyn>.aiff` | `Percussion/cymbals/hihat/hihat.<take>.<dyn>.aif` |
| `cy_{13,17,18,20}crash.<dyn>.aiff` | `Percussion/cymbals/suspended cymbals/stick/<n>crash.stick.normal.<dyn>.aif` |
| `cy_splash.<dyn>.aiff` | `Percussion/cymbals/suspended cymbals/stick/splash.stick.normal.<dyn>.aif` |
| `cy_{16,19,20}chinese.<dyn>.aiff` | `Percussion/cymbals/suspended cymbals/stick/<n>chinese.stick.normal.<dyn>.aif` |
| `oc_{15_bandaturka,17_medheavy,18_french,18_germanic,18_viennese}.<dyn>.aiff` | `Percussion/cymbals/crash cymbals/<name>.<dyn>.aif` |

**THE ROOM BELONGS TO THE INSTRUMENT AND TO WHERE YOU STAND.** These lived only
in a notes file and are now `render-space.sh` in the tuning repo:

| space | chain | for |
|---|---|---|
| `nave` | `pad 0 6 reverb 92 12 100 100 18 -2.0` | an organ a few rows back -- Ben's pick for BWV 542 |
| `far` | `pad 0 7 reverb 96 10 100 100 12 -0.5` | across the building; the lines wash |
| `cath` | `pad 0 6 reverb 88 15 100 100 28 -3.5` | the closer cathedral, more definition |
| `chamber` | `pad 0 5 reverb 60 20 100 100 0 -6.0` | a piano's room |
| `corpus` | `pad 0 4 reverb 45 25 85 100 20 -6.0` | one hall for the whole survey, deliberately even |

Distance is not just more decay: standing further back weakens the direct sound
against the reverberant field AND shortens the gap before the reflections, so
pre-delay comes DOWN as wet goes up -- 28 ms at `cath`, 18 at `nave`, 12 at
`far`. HF damping falls with it, because a stone room keeps its top.

`vol` is set by texture density, not by a flat number: the tail sums onto peaks
that are already hot. A dense flue+reed registration needs 0.5 where a light one
takes 0.9. Check `sox FILE -n stats` -- **Flat factor must be 0.00**.

**TWO SAMPLE RATES ARE IN PLAY AND THEY ARE NOT THE SAME ONE.** blockrender.SR
defaults to **44100** -- offline rendering stays there, and only live.py calls
set_sample_rate(48000). These reference files were converted to **48000** with
sox. So a rendered .raw is 44.1k and a reference .raw is 48k, and reading either
at the other's rate is an 8.8% error: frequencies read a semitone and a half
high, times an eighth short. Every mp3 rendered during the cymbal work was
converted with `sox -r 48000` and so played sharp and fast until Ben heard it in
monocas2 -- 201 s of music delivered as 184.7.

The effect on the FITS was small, because 8.8% is a fraction of a band width:
the crashes' strike-profile error was 5.27 and 3.06 dB as fitted against 5.51
and 3.28 measured correctly. The effect on LISTENING was not small at all.

Convert renders with `-r 44100`, references with `-r 48000`, and check a render's
duration against the MIDI's `.length` before trusting anything measured from it.

**THE CLASH PAIR IS THE ONLY PROPERLY-HIT CRASH IN THE COLLECTION.** The line
below is still right about which takes carry the kit PLATE, but not about which
carry the kit GESTURE. Measured as spectral flatness, the five orchestral clash
takes against the 17" suspended crash struck with a stick:

|  | strike | 0.1-0.3 s | ring |
|---|---|---|---|
| orchestral clash ff | 0.323 | 0.135 | 0.020 |
| 17" stick crash ff | 0.167 | 0.044 | 0.002 |
| ratio | 1.9x | 3.1x | **10x** |

and the clash is 12 dB louder besides. Ben, by ear, before any of this was
measured: "the noise is not wet enough by an order of magnitude." In the ring it
is exactly an order of magnitude. The suspended stick takes are a percussionist
CONTROLLING a cymbal; a crash in a drum kit is the clash gesture. So the mode
set comes from the suspended plate of the right size and the noise trajectory
comes from the clash.

**KIT CYMBALS ARE THE `stick.normal` TAKES, not the `orchcrash` ones.** Iowa's
crash-cymbal page is the orchestral CLASH pair -- two plates struck together --
which is a different instrument from a suspended cymbal hit with a stick, and
GM 49/52/55/57 mean the latter. The suspended set also carries `.bow`, `.mallet`,
`.roll` and `.chokecrash` takes of the same plates.

**THE pp TAKES OF THE CRASHES ARE UNUSABLE FOR SPECTRUM.** They sit 1.3 to 7.2 dB
above their own noise floor (measured against the last 0.5 s of each file), so a
band profile taken from them is mostly room. Read that way they appear to say a
cymbal brightens enormously from pp to ff; between mf and ff, which do have SNR,
brightness moves by a median 0.02 dB per dB of level. A hard crash is the same
sound louder, and what identifies it is the ATTACK: 1.33-1.67 ms from the strike
to within 3 dB of peak, against 17.0 ms for the model before this was measured.
`cy_splash` is the exception with usable pp (21.4 dB SNR).

**HAND PERCUSSION.** Every GM note involved was wrong and one was missing:
claves 800 -> 990 Hz, hi woodblock 760 -> 1400, low woodblock 620 -> 780, mute
triangle 1040 -> 1900, open triangle 1000 -> 1500, castanets unmapped -> 1290.

The four woodblocks give **f1 x size = 7700 Hz-inches** almost exactly (10" 778,
8.5" 853, 6.5" 1234, 5.5" 1406), and that scaling law is what settles which is
"hi" and which is "low" -- the table had the large block's pitch under both.

The triangle ring time was the largest error: measured T60 is 12.8 s on the 8"
and 30.0 s on the 6", against a table that said 0.60 and 1.50. Set to 2.0 and
6.0, a deliberate departure from the measurement -- a 30 s tail on a repeating
note is a slab of partials that never releases -- and labelled as one.

**CROTALES are a PLATE, and the only one in the mallet family.** A free circular
plate runs 1 : 2.08 : 3.41 where a free bar runs 1 : 2.76 : 5.40; the set
measures 1 : 2.03 : 3.38. Ring time halves every 10.3 semitones, 12.4 s at C6 to
2.5 s at C8. GM has no crotale, but percussion note 84 (Belltree) was unmapped
and a belltree is the same object in a different mounting. The set also sounds
+6 to +32 cents sharp of nominal; left alone, that is this set's tuning.

### The guiro: four rounds of measuring the right thing in the wrong window

Worth writing up in full, because every wrong answer was a WINDOW error rather
than a physics error, and each one survived because the next check could not see
the quantity that was wrong.

**Round 1 -- the wash.** Ben: "the clicks have too much static/jitter."
Spectral flatness of one stroke (1.0 = white noise): Iowa clave 0.0002, Iowa
woodblock 0.0000, Iowa guiro 0.0044; ours 0.244, 0.167, 0.489. The guiro was on
NoiseDrumProperties, a dense inharmonic stack meant to approximate a hiss, and
the wood class itself carried chiff_volume 0.65 with sustain_jitter 1.0.
Reducing the partial count does nothing -- 44 harmonics or 4, flatness stays
near 0.22 -- because it was never the harmonic stack.

**Round 2 -- one class for three instruments.** Ben: "now the guiro sounds very
tonal, like a high pitch flute." Tuning the wash to the CLAVE's 0.0002 made the
guiro as pure as a clave, and nine clean pitched tocks in a tenth of a second
sum into a held tone. The guiro is measurably an order of magnitude noisier than
the clave beside it and needed its own class.

**Round 3 -- the ring, and a decay fitted through the noise floor.** Ben: "you
hold the guiro with your hand, so it deadens the block." Correct, and it caught
a measurement of mine: I had reported the final ridge ringing 340-522 ms, from
fitting a decay line across a range that ran into the noise floor. The envelope
says -10 dB in 3-5 ms and -20 in 15-21, against a woodblock's 26 and 50 and a
clave's 53 and 62. It is the SHORTEST wooden sound in the kit.

**Round 4 -- the rate, which no spectral measure can see.** Ben: "it still does
not sound like anything in particular. Maybe look at the waveform directly."
That instruction was worth more than the three rounds before it. A 2 ms impact
envelope finds 27 and 33 ridges over 126 and 151 ms -- a 4.2-4.5 ms gap, about
230 per second. We were running 9 ridges at 13.8 ms, a third of the density. The
earlier 13 ms came from peak-picking a 64-sample envelope at a 20% threshold,
which finds every third ridge and reports the gap between THOSE. The ear hears a
scrape as a RATE, and at a third speed it is a stutter rather than a rip -- and
no amount of getting the body right fixes a gesture at the wrong tempo.

**Round 5 -- the comb.** Ben: "the tonality might be caught in the ridge phase
lock... probably need to only look at the tail ridge for the whole impulse, and
avoid looking at the repeated sections in the frequency domain." Exactly right.
A scrape is a periodic impulse train at ~230 Hz, so its spectrum is the body's
response CONVOLVED WITH A COMB at multiples of the ridge rate. The mode set
measured that way ran 1.000 1.072 1.179 1.273 and then nothing until 2.002 -- and
that gap is where a comb null sits, not where a gourd is quiet. Measured again
from the 50 ms of free decay after the last ridge, keeping only modes present in
BOTH takes within 3%, 19 of 30 peaks survive and they fill in exactly the region
the comb had emptied.

**The flick.** Ben: "I was taught to speed up as I swipe, by flicking to the
side." The Iowa player does it too. Pooled, by position through the stroke, the
gap runs 1.227 / 1.077 / 0.998 / 0.985 / 1.132 of the median and the level 0.348
/ 0.398 / 0.442 / 0.605 / 0.505 -- an 11% acceleration with a +4.3 dB swell,
then both reverse over the last fifth as the hand lifts. rasp_strokes had the
level EXACTLY BACKWARDS, and its docstring said so in words: "a scrape starts
hard, eases through the middle and lifts at the end."

Coefficients are set to reproduce those five buckets rather than a least-squares
line: a line across the whole stroke is dragged flat by the lift and understates
the acceleration by two thirds. Same class of error as the comb -- fitting the
wrong window averages away the thing you are after.

NOT MODELLED: Ben, "there is a bit of a rotation to it". A real flick changes the
contact ANGLE as it travels, so the ridge timbre should shift through the stroke
and not just its rate and level. Nothing here has a per-stroke timbre axis.

### mode_ratios, and the bodies whose modes are not multiples of anything

The mechanism the guiro forced, and the most reusable thing to come out of this.

Everything in tonelib built a harmonic series and then bent it:
inharmonicity_coefficient stretches it, bar_modes picks whole-numbered members
out of it. Both assume a body's modes are RELATED to each other. A struck plate,
a slotted gourd, a cymbal, a tam-tam: their modes are set by a two-dimensional
boundary and fall where they fall.

`mode_ratios` is a tuple of measured multiples of the fundamental with
`mode_gains` beside it; partial m sits at f0*mode_ratios[m-1]. m stays the mode
INDEX, so series_volume, harmonic_decay, chiff_harmonic_gain and unison_voices
keep working. None means the old behaviour.

THREE PLACES ASSUMED f = f0 * m: the partial-frequency computation in both
renderers, harmonic_volume (which evaluates the bore filter at the partial's
frequency), and NoisyPercussionMixin._hf_rolloff. In the reference the placement
rides inharmonic_stretch, because SimplePartial stores the integer index and
computes base*harmonic*stretch itself -- so a measured mode is a stretch of
ratio/m.

db_ratio now SATURATES rather than raising OverflowError. Above about 3080 dB/s
the exponent leaves a double's range; it bit on a PERCUSSION_RING under 12 ms
and again on a mode set indexed far enough out to solve to a huge rate.

### Membranes and the timpani: physics where there is no recording

**A DRUM'S MODES ARE THE BESSEL ZEROS**, and this is the one body in the file
that needs no recording at all -- it is analytic. Every membrane was building a
mildly stretched harmonic series:

    ideal circular membrane   1.000  1.593  2.136  2.295  2.653  2.917  3.155
    what we built             1.000  2.031  3.124  4.310  5.620  7.085  8.736

It matters more here than almost anywhere, because a harmonic series HAS a
pitch: modelling a tom as one models away the one thing that separates a drum
from a note. The file already knew -- MembraneDrumProperties' docstring said "a
free circular membrane's modes are 1 : 1.59 : 2.14 : 2.30 : 2.65 ... which is
why a tom has no definite pitch" -- but the engine had no way to say it.

**The timpani is the opposite case and was never wrong.** The kettle's air
loading pulls the (m,1) modes toward 2:3:4:5:6 of a missing fundamental, which
is why a timpano has definite pitch. It had been placing them through
unison_voices with max_harmonic = 1, a workaround its own docstring explained
("the engine's stretch cannot make a half-integer ratio"), and that reads as a
single partial if you skim it. It is now on mode_ratios like everything else,
with the decay coefficients re-derived because the old code scaled decay by
RATIO and mode_ratios indexes by mode NUMBER: 10.5 12.9 15.1 17.3 19.5 dB/s
became 10.5 12.8 15.1 17.4 19.7.

Its ratios also moved off the idealisation. 1 : 1.5 : 2 : 2.5 : 3 is the
textbook; real kettledrums measure near 1 : 1.50 : 1.97 : 2.44 : 2.90, the upper
modes slightly FLAT, and that compression is part of why a timpano still reads
as a drum rather than a pitched pipe.

**LEVELS: what changed and what it cost.** Moving off exact whole numbers cost
1.39 dB of PEAK while leaving the energy alone (short-term loudness -0.34 dB,
K-weighted -0.19) -- because exact harmonics re-align in phase at every strike
and the measured ratios never quite do. That phase incoherence is the physics
working, and the attack is most of a struck drum's loudness, so the trim came
back by peak rather than RMS. Restoring a lost crest with gain necessarily lifts
the body too: the sustain sits 1.15 dB above the original, and the only way to
have both would be to restore an idealisation to win a level match.

A further +3 dB is BEN'S EAR against the orchestra, not a measurement, and it is
on its own line in the class for that reason. At equal velocity the timpani now
peaks 6 dB over the strings and 9 over a trumpet.

**THE RATIOS ARE PHYSICS; THE GAINS ARE JUDGEMENT.** No drum kit exists in this
collection, so nothing in the membrane family is fitted to a recording. Same
footing as the ocarina and the blown bottle.

**Still on the noise-approximation approach, and unchecked against anything:**
the snare (4527 notes) and the hi-hats (~875). A snare IS genuinely broadband --
the wires are a real noise source -- so it is not the error the wood turned out
to be, but nobody has measured it.


## Harpsichord — VCSL (added after the Iowa gap was found)

Iowa has **no harpsichord**. Its families are woodwind, brass, strings,
percussion and "piano/other", where other is guitar, balloon pops and found
objects — piano and guitar are the only keyboard and plucked instruments in the
collection. So `HarpsiBase` and its children had no measured reference at all.

**Versilian Community Sample Library (VCSL)**, <https://github.com/sgossner/VCSL>
— **CC0**, so unlike the Iowa files there is no redistribution question. Five
harpsichords, 461 files, 48 kHz / 24-bit stereo, kept outside the repo for size.

| set | notes | what it is |
|---|---|---|
| English Normal / "Lute" | 28 / 28 | Zuckermann kit, 1970s |
| Flemish Low / High | 28 / 26 | two registers |
| French | 30 | |
| Italian stop1 | 32 | |
| Unk | 61 | widest compass |

Every instrument records its **releases separately from its sustains**, which is
why the damper could be fitted at all: it is isolated rather than needing to be
subtracted out of a whole note.

### Measured

**`HarpsiBase.release_valve_time = 0.055`** — time for the damper to take the
first 20 dB, from the envelope peak of the isolated release: French 19 ms, Unk
42, Flemish 57, English 68; mean 47, sd 30. The previous value was 0.0, which
gated every note to silence in ~7 ms.

**`HarpsichordProperties.strike_point = 0.115` — CONFIRMED, not changed.** The
pluck fraction fitted from the comb, averaged over every note of each set:

| set | beta | 1/beta | fit r |
|---|---|---|---|
| English Normal | 0.1200 | 8.3 | 0.55 |
| English "Lute" | 0.1195 | 8.4 | 0.69 |
| Flemish Low | 0.1210 | 8.3 | 0.62 |
| Italian | 0.0970 | 10.3 | 0.65 |
| Unk | 0.0975 | 10.3 | 0.60 |
| Flemish High | 0.0870 | 11.5 | 0.59 |
| French | 0.0485 | 20.6 | 0.35 |

mean 0.0986 (1/10.1), sd 0.024. The existing 0.115 sits inside that and on the
English/Flemish cluster, so this promotes it from assertion to measurement
without moving it. The French outlier has the worst fit and is the set already
shown to be the most reverberant here — a room-washed comb, not a different
instrument.

### What the recordings will NOT support, and why

They are not anechoic, and there is one mic position per instrument, so a room
cannot be subtracted. What makes anything separable is that **room decay is
common across notes in a band and string decay is not**: in a fixed 890–1120 Hz
band the French sustains decay at −11.4, −10.5 and −10.6 dB/s for C3, C4 and C5,
and three different strings do not agree to within a dB. That is the room.

So only the FAST stage of the release is fitted. The slow tail running several
hundred ms reads as the soundboard but is largely their room, and fitting it
would import it into the instrument for our own room model to double.

Per-instrument usability, measured rather than assumed: the French is
room-dominated even in its early window (early slopes −20.8/−19.6/−19.9 dB/s
across three notes — again too equal to be strings). The Flemish is explicitly
the `Far` mic. **The English (Zuckermann) varies most with pitch and is the only
set I would trust for string decay.**

### Not what it says on the tin

VCSL's English **"Lute"** is a **buff stop**, not a lute stop. A lute stop is a
second jack row plucking near the nut, which moves the comb; this leaves the
comb untouched (beta 0.1200 vs 0.1195) and halves the decay:

| note | Normal to −40 dB | "Lute" to −40 dB |
|---|---|---|
| C3 | 4.25 s | 2.25 s |
| C4 | 1.98 s | 1.25 s |
| C5 | 1.07 s | 0.32 s |

Comb unchanged, decay collapsed: felt on the strings. `HarpsiLuteProperties`
already models it that way and is correct. It also means this pair gives no
pluck-point contrast — a true lute stop is still unmeasured.

### Fitted with `voicefit.py`, and what would not fit

`voicefit.py` is the committed version of the throwaway scripts every earlier
calibration used. Subcommands `decay`, `inharm`, `comb`, `ratio`; it reproduces
the two results above (comb: English 0.1150, Flemish 0.1200) before being trusted
with anything new.

**`inharmonicity_coefficient` 1.200e-4 -> 3.51e-5.** Regressing `(f_m/m)^2` on
`m^2` over 195 notes from six sets:

| set | median B |
|---|---|
| English | 3.63e-5 |
| Italian | 4.38e-5 |
| Unk | 2.67e-5 |
| French | 2.41e-5 |
| Flemish Low | 2.39e-5 |

pooled median 3.51e-5, IQR 2.19e-5 – 8.16e-5; **89% of every note measured fell
below the value that stood in the class.** This is the one fit these recordings
support unconditionally, because partial FREQUENCIES are immune to reverberation,
so five instruments agreeing across five rooms is real agreement. Round-tripped:
rendering with 3.510e-5 and re-measuring returns 3.512e-5, sd 1.5e-7.

**Decay: measured, NOT changed.** The fitted triple (decay_db 5.44,
harmonic_decay_db 0.86, decay_register_slope 0.54) is no better than the standing
3.2 / 1.5 / 0.42 — rms residual 11.37 against 11.26 dB/s, and worse in three
registers of four. The residual is as large as the quantity, so the data does not
constrain the law.

The reason is physical rather than a limit of the recordings: **per-partial decay
is not linear in m and nothing about a real string says it should be.** Partials
couple individually to soundboard modes, so within one C4 the measured rates run
5.8, 8.4, 40.1, 7.6, 10.0, 8.3 dB/s for m = 1,2,3,5,6,7. The model's linear law is
a smooth approximation to something intrinsically scattered, and three parameters
cannot be improved against scatter of that size. The standing values already sit
inside it.

An earlier claim of mine that the voice "rings twice too long" came from
broadband time-to-−40 dB, which is dominated by the fastest-decaying partials and
is not the m = 1 rate the parameter controls. Measured per partial, C4 m = 1 comes
back at 3.88 dB/s against the model's 3.84.

**Buff ratio: measured, NOT changed.** `HarpsiLuteProperties` implies a decay
ratio of (11.0+3.0)/(3.2+1.5) = 2.98. Broadband gives 1.89 / 1.58 / 3.34 at
C3/C4/C5 and the per-partial `ratio` fit a median of 2.71 (sd 3.77 — too noisy to
refine anything). The standing value is inside the measurement.

This is the room-free measurement of the set: two stops of one instrument in one
room, so dividing removes the room exactly. It is worth knowing that even *that*
was not precise enough to move a parameter.

### Still assertions after all this

`initial_gain` (no SPL reference or known gain — the files are level-set for a
sampler), directivity (one mic, one angle), soundboard formants (not attempted),
register coupling and sympathetic resonance (isolated notes, isolated registers),
and the decay parameters above, which are now *consistent with* measurement
rather than derived from it.

### Soundboard and radiation

**`formants = ((490.0, 350.0, 0.40),)`, `formant_floor = 0.50`.** Measured with
`voicefit.py formants`: the comb method run on the other axis. A pluck comb and a
series tilt are fixed in HARMONIC NUMBER; a body resonance is fixed in FREQUENCY.
So dividing each partial by what the source model predicts, removing anything
smooth in m, and pooling by frequency finds the body and washes the source out.

| set | body region |
|---|---|
| English | 449 Hz +5.2 dB, 566 Hz +3.4 |
| Italian | 283 +9.1, 224 +7.2, 356 +5.3, 449 +3.8, 566 +4.0 |
| Unk | 224 +3.9 |

All three show one broad region between 200 and 600 Hz with a dip above it,
which is where a harpsichord's soundboard and case cavity live. They differ
because they are different bodies. Fitted to the English as a single pole.

`bore_corner_hz = 40000` is placed above the audible band deliberately: it exists
only to open the formant path (`harmonic_volume` returns early on a zero corner,
so a body with no corner is silently no body), and the measurement was detrended
in harmonic number so it CANNOT see a smooth high-frequency rolloff. Asserting
one would be inventing a number.

**Verified only partly, and this is weaker than the inharmonicity fit.** The body
does reach the ladder -- for f0 = 245 the partial at 490 Hz comes out +3.0 dB on
m=1 and +4.4 dB on m=4, against the measured +5.2 -- but re-measuring a RENDER
with `voicefit formants` does not recover the pole, because the analysis divides
by an assumed source model that is not exactly the renderer's. Inharmonicity
round-tripped to 0.06%; this did not round-trip at all. Treat the body as
measured in the recordings and plausible in the model rather than as confirmed
end to end.

**`directivity_radius = 0.15` is a GUESS and marked as one.** One microphone at
one angle cannot measure a polar pattern; nothing in this set constrains it. The
reasoning: a harpsichord soundboard is ~1.8 x 0.8 m tapering, some 0.9 m2, and a
rigid piston of that area would have a = 0.54 m and beam into a 22-degree lobe by
1 kHz, which no harpsichord does -- a soundboard is not rigid and above its first
modes only a fraction radiates coherently. The piston model saturates near 12 dB
of directivity index whatever the radius (0.08 m gives 9.9 dB at 4 kHz, 0.54
gives 12.0), so the radius chooses the TRANSITION and not the strength; 0.15 puts
ka = 1 at 364 Hz and keeps the bass omnidirectional.

It matters more than a polar plot suggests, because Q sets the reverberant send:
this voice previously radiated equally in every direction at every frequency, so
its room was uniformly wet. Measured through a render, Q now runs 1.08 at 250 Hz
to 8.77 at 4 kHz -- bass-wet and treble-dry, as a room is.

### Stretch

`WerckmeisterTuner.stretch_interval = 1.0000526`, derived from the measured B by
sqrt((1+4B)/(1+B)) -- where the lower note's 2nd partial actually sits, which is
what octaves are tuned beat-free against.

That is **+0.091 cents per octave, +0.46 across a 61-note compass**, and the
smallness is the result rather than a reason to leave it out: a harpsichord
barely needs stretching, which is why historical temperaments for it are quoted
as exact ratios and why one can be tuned genuinely beat-free where a piano
cannot. For comparison StretchTuner carries 1.0019377 for piano wire, +3.35 cents
per octave; borrowing that for a harpsichord would be wrong by some 17 cents
across the compass.

### The mechanism, not the string

**`release_click_*` on HarpsiBase.** A harpsichord's key coming up does two
things at once, and they separate on the test that separated everything else
here: a string event follows the note, a mechanical one does not.

Measured on the isolated VCSL release recordings, spectrum by octave band across
C2-C5:

| band | spread across notes | what it is |
|---|---|---|
| 150 – 1200 Hz | 5.6 – 7.6 dB | the damper arriving on the string — follows the note |
| 2.4k – 9.6k | 2.2 – 4.6 dB | the jack falling back — the same whatever was played |

The first was already modelled by the release fade. The second was not modelled
at all, and it is not quiet: the release event sits **-12.5 to -17.5 dB under the
note it ends**, with a spectral centroid holding between 2909 and 5068 Hz
whatever the pitch.

It cannot be done with chiff. Chiff is jittered phase ON the note's partials, so
it wears the note's spectrum and fades out with it — right for a pipe's speech,
wrong for a piece of wood dropping. Measured through the renderer, `chiff_release`
moves the post-note-off peak by 0.2 dB between 0.0 and 2.0: the mechanism exists
and is inert, because it scales phase noise on partials the release envelope is
simultaneously removing.

So it is emitted as what it is — a separate short event at note-off, at fixed
frequencies, riding the note's gain so a quiet note clicks quietly. Round-tripped
through the renderer by DIFFERENCING a render against one with the click off,
because the 55 ms damper is louder than the click for the whole window and hides
it in a direct measurement:

| | rendered | measured |
|---|---|---|
| level under the sustain | -15.0 dB | -12.5 .. -17.5 |
| spectral centroid | 3867 Hz | ~3900 |
| -20 dB in | 32.7 ms | ~33 |

`release_click_db = -39.6`, not the -15.6 the recordings show, because it rides
`gain` — the factor before the harmonic ladder — rather than the note's audible
peak. The five modes are a stand-in for a small wooden object being dropped,
placed to land the centroid, not a claim about anything's modes. The decay comes
from the shortest measured fall; the longer readings are the note's own upper
partials still ringing in the same band.

Off for all 101 voice classes but the four harpsichords.

### Brightness

Comparing 2-8 kHz content against the note's own peak found our render at
-21.8 dB where the recordings sit at -6.0 (C3) and -7.0 (C4). A room recording
carries LESS high frequency than an anechoic model, not more, so the gap was real
and if anything understated.

**`tonal_dampening` 1.55 -> 0.75**, grid-searched through the renderer so the body
and the power renormalisation sit inside the loop:

| tonal_dampening | ladder rms | 2-8 kHz error |
|---|---|---|
| 1.00 | 8.65 dB | -3.8 dB |
| 0.85 | 6.65 | -2.2 |
| **0.75** | **5.15** | **-1.2** |
| 0.65 | 8.17 | -0.3 |
| 0.55 | 6.48 | +0.6 |

Judged on the ladder AND on broadband brightness, because a ladder-only fit is
one of the four standing failure modes: the ladder alone bottoms in the same
place but is noisy and non-monotonic -- the renormalisation moves the very
fundamental the ladder is measured against -- while brightness is monotonic and
settles it. Ladder rms 17.52 dB -> 5.15.

    m           1     2     3     4     5     6     7     8    ...   16
    recordings  0.0  +3.3  -4.6  -4.1  -9.7  -8.5 -15.0 -14.9        -24.4
    before      0.0   0.0  -9.4  -8.6 -18.2 -18.5 -30.0 -35.6        -48.5
    after       0.0  +5.2  +3.6  +1.7  -6.0  -0.3 -15.2 -19.2        -27.1

A harpsichord is not 1/n^2, which is what 1.55 was reaching for. The recordings
put the SECOND harmonic ABOVE the fundamental -- +3.3 dB pooled, +9.4 in the bass
-- and that weak fundamental is what the instrument is recognised by.

The sibling registers shifted by the same -0.80 (upper manual 1.30 -> 0.50, buff
2.40 -> 1.60). They were set RELATIVE to the old base, so holding them fixed
would have made the upper manual duller than the lower and inverted a
relationship tuned by ear.

The recordings' own ladder scatters 12-20 dB note to note, so 5 dB rms is near
what this data resolves and is not a claim of 5 dB accuracy. The comb is
unaffected: re-measuring a render returns strike_point 0.1150 at r = 1.00.

### Registration, and a 24 dB bug it found

Building a demo that draws each stop in turn (`harpsi_stops`: the C major
Invention played six times, CC11 = 1, 2, 3, 5, 7, 8) exposed something no
single-registration render could have.

`initial_gain` had been balance-normalised on `HarpsichordProperties` ALONE. Its
own comment said that was safe because "these voices play alone" -- true of a GM
patch, false the moment stops are drawn. `HarpsiUpperProperties` and
`HarpsiLuteProperties` still carried the inherited 1/50, leaving the upper manual
and the buff **23.9 dB under the lower 8'**: inaudible in a coupled registration,
and a 24 dB drop when either was selected alone. Moved to `HarpsiBase`, where
every rank inherits it; the relative balance is `stop_ranks`' own gains and
belongs there.

After, measured per 18-second block:

| registration | CC11 | rms vs 8' | 2-8 kHz vs peak |
|---|---|---|---|
| 8' lower | 1 | ref | -11.5 dB |
| 8' upper | 2 | -2.7 dB | -5.4 |
| both 8' | 3 | +4.4 | -7.7 |
| 8' + 4' | 5 | +2.7 | -11.3 |
| grand jeu | 7 | +6.2 | -6.7 |
| lute / buff | 8 | -10.9 | -18.4 |

The upper manual is 6 dB brighter than the lower at the same level, which is the
pluck point doing it: `strike_point` 0.045 against 0.115, a quill catching the
string near the nut. That is the comb measurement of the previous section heard
rather than plotted.

Nothing in the 135-file Sankey corpus drives any of this -- it contains zero
controller events of any kind -- so registration has to be supplied.


## The Sankey corpus (MIDI, not recordings) — and its terms

Not a measurement source for the voice, but the provenance belongs here with
everything else, because two tuners came out of it and because its terms
constrain what may be done with renders.

**What it is.** 135 MIDI files, essentially the complete Bach keyboard works,
hand-played by John Sankey on a MIDI keyboard, from
<http://www.jsbach.net/midi/sankey/>. Kept outside the repo; `NOTICE.txt` sits
beside them.

**What was measured from it**, which is the reason it is documented at all:

- The files are NOT quantised: only 27% of onsets fall on even a 1/96-beat grid,
  and there is one tempo event in BWV 971, so the ritardando at its end is
  played rather than programmed.
- The channels are not voices, they are PITCH CLASSES. Each carries a fixed
  pitch bend, and those bends are Werckmeister III's deviations from equal
  temperament to the cent (F#/A -11.72, C#/E -9.77, G#/B -7.81, D -7.71, Eb
  -5.86, Bb -3.91, G -3.78, F -1.95, C 0.00). The temperament is IN the file.
- This renderer ignores pitch bend entirely, so `werckmeister` is not an
  embellishment on these files — without it they would silently play equal.
- The playing is legato: notes are held 98.5% of the way to the next in the same
  register, 7.3% detached, 98.1% duty cycle. That is his reading, and it is why
  a note-off gate went unheard here for so long.
- Zero controller events in all 135 files, so nothing drives registration.

**Terms** (<http://www.johnsankey.ca/copyright.html>). The MIDI may be freely
copied and redistributed with his notice attached, and modified freely FOR
PERSONAL USE. But: *"If the distribution format is any form of audio, it must be
derived from the MIDI files using my matching soundfont on a SoundBlaster 32 or
100% compatible system."*

So renders made here are personal use and permitted; **distributing them is
not**, because they are a physical model and not his soundfont. His stated
reason, cross-referenced to his own pages on sustain and consonance, is that he
wants his tuning and sustain heard as intended.

His Scarlatti is a separate matter and is NOT obtainable this way: his site
offers his own edition (176 sonatas as zipped PostScript, k001-k176, typeset in
LilyPond) and third-party MP3s, but the MIDI is at Classical Archives behind a
subscription. The `sankey` tuner exists for it regardless.

### His own instrument — `ross.sf2`, and `HarpsiRossProperties`

<http://www.johnsankey.ca/data/ross.sf2> — the soundfont he recorded through,
995 KB, converted from his original SoundBlaster SBK by Awave (its INFO chunk
carries Creative's boilerplate copyright, not his). **Three unlooped samples**,
44.1 kHz: E3 6.23 s, A4 2.87 s, B5 2.17 s.

**It is a different harpsichord from the one we fitted.**

    m =                    1     2      3      4      6      8     16
    Sankey's own        0.0   -5.0   -7.0   -6.7  -10.5  -21.6  -27.7
    VCSL English        0.0   +3.3   -4.6   -4.1   -8.5  -14.9  -24.4
    our model           0.0   +5.2   +3.6   +1.7   -0.3  -19.2  -27.1

Strong fundamental where the Zuckermann kit has a weak one, and 36% longer ring.
`HarpsichordProperties` is not wrong; it is faithful to a bright 1970s kit.

**It independently confirms the inharmonicity.** B = 3.23e-5 here against the
3.51e-5 fitted from six VCSL sets — a different instrument, a different decade,
a different measurement chain, agreeing to 8%. That is the strongest evidence
yet that the number is the instrument's and not the dataset's.

**What pitch he played at — and a correction.** The raw samples sit near A=426
(426.8, 426.5, 425.6), and I first reported that as his instrument's pitch. It
is not: the bank's instrument zones declare them as E3/A4/B5 and apply a
fineTune of +71/+70/+73 cents, which puts playback near **A = 444**. His MIDI
then adds Werckmeister's own -11.72 cents on A, so his recordings sound at about
**A = 441** -- essentially modern pitch, not baroque.

His pitch bends carry no global offset, which is what settles it: C is exactly
0.00 and every other class is negative, to a maximum of -11.72 cents. That is a
temperament defined downward from C, not a transposition.

So `werckmeister` at A=415 renders his Bach a semitone below where he played it.
415 remains the conventional baroque choice and the house default across the
historical tuners; `blockrender IN OUT werckmeister a=441` matches him instead.

**Fitted** into `HarpsiRossProperties`: the decay level and register slope
(D(415) 3.46 against the base's 4.70, slope 0.536 from D = 2.16/3.21/5.68 at
160/427/955 Hz) and the inharmonicity. Round-tripped: E3 renders 2.11 against a
measured 2.16, A4 3.47 against 3.21.

**Not fitted, and the class is thin because of it.** His ladder is not a 1/n^k
tilt -- m=2 alone wants `tonal_dampening` 1.4, m=8 wants 0.75, and it turns back
up at m=12. That is body and comb structure and three samples cannot separate
them, so the tilt keeps the base's value rather than take a number that would
only look like a measurement. `strike_point` is set explicitly to the 8' lower
manual's 0.115 as a STAND-IN: HarpsiBase leaves it None and inheriting that
would have dropped the voice onto the legacy comb path without saying so.

Selected with `TUNING_HARPSI=ross` (or `zuckermann` for the default). An env
switch and not a stop, because a stop is a register of one instrument and this
is a whole other instrument.

**Licence, again.** Fitting a model to his soundfont does not make renders
distributable: his terms require distributed audio to be "derived from the MIDI
files using my matching soundfont on a SoundBlaster 32 or 100% compatible
system", and a physical model is not that soundfont however well it is fitted.
Whether "derived" was meant to reach a model fitted to it is a question for him,
not for us to decide by assuming the generous reading.

## Engraved scores as a source of articulation (added for the Bumblebee)

Every sequence of a piece carries someone's articulation, and it is usually
either absent or invented. The composer's is in the score, and a score
engraved by Sibelius or Finale and published as PDF is not a picture: the
noteheads are font glyphs at exact coordinates, the staff lines are stroked
paths, the slurs are beziers. That makes it symbolic data, readable by
arithmetic.

`pdfmus.py` interprets the content stream; `scorepdf.py` turns it into pitches
and slur groups; `rearticulate.py` transfers the slurs onto a sequence of the
same music.

### What was taken, for Rimsky-Korsakov's "Flight of the Bumblebee"

| quantity | source | check |
|---|---|---|
| notes, parts, arco/pizz | IMSLP orchestral MIDI, 12 named tracks | aligned against the engraving |
| slurs | the engraving (31 arcs on the flute alone) | endpoints bracket noteheads |
| tempo | the engraving's `Vivace q=180` | file said a flat 120 |
| key | the engraving | file was the Johnson arr., +5 semitones |

Score: IMSLP99876, a Sibelius engraving in Inkpen2, 23 pages, 17 staves.
Sequence: IMSLP872813 `PMLP3170-Bumble_bee.mid`. Both public domain.

Glyph vocabulary of that engraving, established by behaviour rather than
assumed: **9** filled notehead, **20** open notehead, **5/6/10** sharp / flat /
natural, **3/7/8** treble / bass / C clef, **4, 8, 12, 13** rests. Rests and
clefs sit at a fixed height; noteheads vary. That is the discriminator.

### The check that makes it trustworthy

Decoded parts were aligned against the independent sequence by pitch, with
`scorealign.py`. Agreement was total -- flute 543/543, clarinet 223/223,
bassoon 113/113, cor anglais 41/41, oboe 19/19, horn 36/36, **zero pitch
mismatches anywhere**. A misread pitch grid cannot survive that: it would show
as a systematic interval error across a whole staff. This is the difference
between reading an engraving and running OMR over a scan -- the failure mode
is loud, not plausible.

### What the engraving would not give

- **Duration.** Inkpen2 draws beams as glyphs, not as strokable rectangles, so
  note values are not directly recoverable. Taken from the sequence instead,
  which is what the alignment validates.
- **String slurs.** This engraver slurred the winds and *not one string part* --
  common shorthand where the strings double a wind line, and invisible unless
  you go looking. Violin I carries the bee line for whole pages with no slur
  drawn over it. Read literally, that would have made the violins spiccato
  against a legato flute; parts without engraved slurs fall back to the
  grammar the engraved ones use.

Rimsky's grain, measured from the flute: groups of **8, 16 and 32** -- one, two
and four bars, dominated by the 2-bar slur (12 of 31). The sequence had joined
the same line into runs of 33, 65 and 81, i.e. across slur boundaries.

### mt32check earns its place again

The sequence carried two program changes at tick 0 on six channels, and only
the last takes effect. Every string part would have rendered **pizzicato
throughout** -- including the violins carrying the bee line `con sord.` -- and
the horns as muted trumpet. The file's own first program was right in all six
cases. Nothing about this is audible until it is rendered, and by then it
sounds like a choice.

## The early reflections comb the pedal register

Ben, on BuxWV 161: "the first D pedal is definitely not a flue pipe. It is a
reed. I can hear it." He was right about the sound and it was neither the
registration nor the voice.

Isolated, a D2 on the flue organ's 8' rank:

| | h1 | h2 | h3 | h4 | h5 |
|---|---|---|---|---|---|
| `harmonic_volume` says | 0.0 | -6.0 | -9.5 | -15.6 | -15.6 |
| rendered, reflections off | 0.0 | **-7.2** | -9.9 | -12.2 | -14.4 |
| rendered, reflections on | 0.0 | **-16.4** | -9.1 | -9.2 | -17.1 |

The voice is right to within a decibel until the room touches it. With the
first-order images in, the second harmonic loses 9 dB -- and a spectrum of
strong fundamental, no second and a healthy third is a REED. The flue pipe is
being pushed onto the reed's own spectrum by the room, in the one register
where it is audible as a change of stop rather than of colour.

It is not the mono sum: left and right each measure -16.4 alone.

The mechanism is NOT that the early field is sparse, which is what this
section said before anyone tested it.

`image_sources` only ever built first order, so the claim was untested. It now
builds any order, and the answer is no:

| order | distinct images | survive | D2's second harmonic |
|---|---|---|---|
| 0 (no room) | - | - | -12.0 dB |
| 1 | 6 | 3 | **-21.4** |
| 2 | 24 | 5 | -21.5 |
| 3 | 62 | 5 | -21.5 |

Second order adds two early reflections and moves the notch by 0.1 dB, for 33%
more partials (2028 to 2707). Third order adds 38 more images and not one
survives. No band of the spectrum moves by more than 0.71 dB. So
`reflection_order` stays at 1, and the extra machinery stays available and
unused.

TWO REASONS IT CANNOT WORK, both worth knowing before trying it again:

- `reflection_fusion_s` is 50 ms, and past it an image is dropped because the
  diffuse tail carries that energy decorrelated instead of as a replica. In a
  hall, nearly every higher-order image is late: at third order, 57 of 62 are
  past the limit. The early field is not sparse because the order is low, it is
  sparse because the room is big.
- A notch made by ONE strong early arrival cannot be filled by later, weaker
  ones. The floor bounce here is -6.6 dB at 2.06 ms, which is most of the
  effect, and it is not a modelling artefact -- source and listener at the same
  height over a floor 1.2 m down is the geometry of every seated audience, and
  a floor-bounce notch is what they hear.

What WAS wrong, and was the whole of what Ben heard, is the section below: the
flue's harmonic slope. Fixing that fixed the pedal. The comb is real.

A LATENT BUG FOUND ON THE WAY. Mirroring in two perpendicular planes commutes,
so floor+left+floor lands exactly where left alone does: at third order, 186
sequences reach 62 distinct positions. Enumerating by sequence therefore emits
one floor bounce five times, five times too loud, charged whatever absorption
the last sequence happened to carry. Images are now deduplicated by POSITION,
keeping the first (shortest, so physically real) sequence to reach each. At
order 1 there are no duplicates, so this was invisible until the order moved.

Worth noting for any bass voice, not only the organ: the comb sits where it
sits in HERTZ, so it lands on a different harmonic of every pitch, and it bites
hardest where the harmonics are closest together -- the bottom of the compass.

## The flue organ's harmonic slope is too shallow

Measured on a single D2, each rank alone, no room at all, fitted over the first
eight partials:

| rank | slope |
|---|---|
| flue 8' (principal) | **-6.2 dB/octave** |
| reed 8' (odd partials) | -6.3 dB/octave |
| real open principal, literature | -10 to -14 dB/octave |

`bore_corner_hz` is 0 for the organ, so `harmonic_volume` short-circuits and
the spectrum is `series_volume` alone -- amplitude proportional to 1/m raised
to `tonal_dampening`, which `OrganProperties` sets to 1.4. The relation comes
out linear: slope = -6.02 * dampening + 2.2, so 1.4 gives -6.2 and the real
range wants 2.2 to 2.6.

THE PARAMETER IS SHARED WITH THE REED AND SHOULD NOT BE. At 1.4 the reed
measures -6.3 dB/oct, which is RIGHT -- a reed stop is genuinely brighter than
a principal, and that is most of what distinguishes them. Moving the family
value would fix the flue by breaking the reed. The correction belongs on
`FlueOrganProperties` alone.

APPLIED, on `FlueOrganProperties` alone, at 2.2 (-11.0 dB/oct). Ben's ear on
the A/B: "much better". The Passacaglia's 2.8-4.5 kHz band falls 5.5 dB and
4.5-8 kHz falls 9.0 dB, with everything below 1.6 kHz within half a decibel.
The reed keeps the family's 1.4, which is not an error to be corrected but
the other half of the distinction.

Note the interaction with the previous section: a shallow slope puts more
energy in the upper partials, which is exactly where the sparse early field
combs. The two faults compound, and the brightness was audible first.

## GM 16, 17 and 18 render as a pipe organ

`property_class_for_program` sends Drawbar Organ (16), Percussive Organ (17)
and Rock Organ (18) to `FlueOrganProperties`, the same class as Church Organ
(19). There is no tonewheel voice in the repertoire at all.

That matters for more than naming. A Hammond is not a pipe: its partials are
near-pure sines at fixed drawbar ratios with no speech transient, its attack is
a key click rather than a pipe building a standing wave, and its harmonic
content does not fall off with a pipe's slope because it does not come from a
pipe. Rendering one as a Principal gets every one of those wrong -- and it is
the voice a Leslie belongs on.

## What a Leslie needs, and what is already here

`leslie.py` carries the geometry. Measured for the church room, a 1 kHz partial
leaving the cabinet:

| path | azimuth | rotor phase |
|---|---|---|
| direct | +0.2 deg | -0.2 deg |
| image 1 | +80.3 deg | -80.3 deg |
| image 2 | +90.0 deg | -90.0 deg |

The images modulate up to 90 degrees out of phase with the direct sound: when
the horn points at the listener it is side-on to that wall, and the reverse a
quarter-turn later. THAT is the effect. The direct and reflected sound beat
against each other at the rotor rate with a phase relationship the ROOM sets,
which is why a Leslie sounds different in every room and why a static early-
reflection network cannot reproduce it.

Already present, and enough for the Doppler with no kernel change:
per-partial sinusoidal FM with an independent phase, integrated on an ABSOLUTE
clock -- a rotor angle is shared by every note and must not restart at note-on.
Reflections are already separate partials, each carrying the source's
directivity at its own departure angle, so each can take its own rotor phase.

Missing: a tonewheel voice (above), and per-partial amplitude modulation. The
second is not a new primitive, since AM of a sinusoid is three partials:
(1 + m cos(wt+p)) sin(Wt) = sin(Wt) + (m/2)[sin((W+w)t+p) + sin((W-w)t-p)].
Every partial becomes three, which the partial count can afford.

Physical figures the module produces: Doppler +-35 cents at the horn (a 0.17 m
throw at 6.6 Hz), level swing +-6% at 110 Hz rising to +-84% at 6 kHz -- the
spectrum breathing at the rotor rate, which is what separates a Leslie from a
tremolo.

## The tube amp: where a power series stops, and what to do instead

Distortion products are partials, so the amplifier does not need a sample-domain
stage: a nonlinearity applied to a sum of cosines makes more cosines, at sums
and differences of the inputs, with amplitudes that follow from the transfer
function's power series. `tubeamp.py` emits them, and it runs BEFORE
`leslie.expand`, which is how the amp ends up upstream of the rotor -- the order
a real cabinet has -- without leaving the partial domain.

PER-PARTIAL HARMONICS WOULD NOT DO. Measured on a tempered Hammond chord
through a soft clipper, only 27% of the distortion energy lands on harmonics of
the inputs; **73% is intermodulation between them**. Distortion-as-harmonics is
true of one tone and false of a chord, and a Hammond is a chord machine even
when one key is down, because every drawbar is another tonewheel.

WHY IT IS AFFORDABLE. A four-note chord on nine drawbars has 1015 partials but
only **84 distinct frequencies** -- the tonewheels are shared. And a third-order
product's amplitude is `A_i*A_j*A_k`, so weak partials make cubically weak
products:

| strongest K kept | products | distortion energy |
|---|---|---|
| 10 | 880 | 51.7% |
| 14 | 2,240 | 76.0% |
| **20** | **6,160** | **91.6%** |
| all 36 | 33,744 | 98.6% |

Verified against the real 3/2-law valve on two tones: every predicted product
within 5% except where 4th and 5th order land in the same bin (15%). And on
twenty partials the predicted total distortion sits within 3.5 dB of the true
figure. With a balanced pair the even orders vanish by **150-170 dB** while the
third order is untouched, which is push-pull doing what push-pull does.

WHERE IT STOPS. The series is an expansion about the operating point and holds
only inside the grid bias:

| drive | 3 orders | 5 orders | 9 orders | 15 orders |
|---|---|---|---|---|
| 0.8 | 0.7% | 0.2% | 0.0% | 0.0% |
| 1.0 | 2.6% | 1.5% | 0.8% | 0.4% |
| 1.6 | 3.3% | 5.5% | 23.4% | **132.3%** |

Past the bias it does not lose accuracy, it DIVERGES -- more orders are worse,
not better -- because the tube cuts off there and a power series about zero
cannot have a corner. So the first version clamped drive at 1.0, and modelled
the bend rather than the clip.

That clamp was the SERIES' limit, not the amplifier's, and the distinction
matters because the clip is what Leslie overdrive is. Two things stood in the
way, and they are independent:

- **Convergence.** The radius really is the bias, so drive 1.0 is exactly the
  edge -- that part of the old claim stands. Nor does a better fit rescue it:
  Taylor is stuck at 120% error on a hard clipper *forever*, because a clipper
  is exactly linear near zero, so every derivative above the first vanishes
  there and the series never learns the corner exists. Fitting over the range
  instead does converge -- Chebyshev reaches 5.8% at order 9, with **odd-only**
  coefficients, which is the square wave falling out of the arithmetic.
- **Combinatorics.** Which fixing convergence does nothing about. A clip's
  energy lives in the high orders: hard-clipping a tonewheel chord puts 4.0%
  of the distortion energy in third order, **46.7% in fifth and 41.9% in
  seventh**. Fifth order over twenty partials is ~680,000 terms and seventh is
  ~42 million. And truncating harder does not save it -- the captured fraction
  goes as `f^n`, so keeping the strongest 8 parents captures 48.8% of third
  order but only 30.3% of fifth. High orders need the same parents or more.

BOTH ARE PROPERTIES OF EXPANDING, NOT OF THE PROBLEM. So `tubeamp` now
evaluates the curve instead: synthesise the segment's partials, apply the valve
per sample, subtract the linear part, transform, and read the products off the
residual. One FFT finds every order at once, for any transfer function, with no
radius of convergence and nothing enumerated. Measured on a four-note chord it
emits 100.2-100.9% of the true distortion energy and reproduces its 1/12-octave
spectrum to 10-15%, in 56 ms a segment.

THE CURVE NEEDED A CEILING BEFORE IT COULD CLIP. Cutoff alone is half a
clipper: past the bias one half stops conducting and the other keeps growing as
`v^1.5`, so the stage went EXPANSIVE -- slope 0.718 at drive 1 rising back to
1.008 by drive 3. A real stage also runs out at the top, when the plate voltage
swings down and the load line reaches the knee, so each half's current now
passes through a soft ceiling. The slope falls monotonically and stays fallen:
0.94, 0.62, 0.43, 0.07 at drives 0.5, 1, 2, 4. Rendered, that is -24.6 dB of
distortion at drive 1, -12.5 at 2 and -3.3 at 4, with the level dropping 1.9 dB
across the sweep -- the compression and the clip being the same ceiling.

WHY IT WORKS AS WELL AS IT DOES, WHICH WAS A SURPRISE. Counting terms is
misleading; what matters is how many distinct FREQUENCIES they land on, and
those collapse. Drawbar ratios are tempered approximations to integers -- the
"third harmonic" is 2.9966 -- and sums and differences of near-integers are
near-integers, so the products fall onto a near-harmonic lattice:

| voicing | order | terms | distinct freqs | clusters 10c apart |
|---|---|---|---|---|
| 1 key | 7 | 403,779 | 7,969 | 610 |
| triad | 5 | -- | 1,155,020 | **1,113** |
| triad + 7th | 5 | -- | 5,068,131 | **1,153** |

The frequency count explodes and the cluster count does not, because equal
temperament keeps cross-products between different keys on the same lattice
too. Five million lines inside eleven hundred groups is about a thousand lines
per cluster, all beating against each other -- a dense chorus around a definite
pitch, which is what the growl is, and which is why it has pitch at all.

TWO THINGS THAT LOOK RIGHT AND ARE NOT.

The residual is **not stationary**: distortion fires at the crests where the
partials happen to align, and a one-second window holds only a handful of
those, so whether a crest lands under the window's taper or its flat changes
the apparent energy. Measured, the window-weighted total ran 29% over the true
residual power and the first version duly emitted 131% of the distortion
present. The distribution has to come from the FFT and the LEVEL from the
time domain, where no window is involved.

And emitting each cluster as several detuned partials carrying its measured
width -- which is the obvious way to put the beating back -- makes it WORSE:
waveform error went from 59.5% to 70.2% on a chord. The sub-partials get
subdivision frequencies and mismatched phases, and detuning that is merely
arbitrary is worse than none. One partial carrying the cluster's whole energy
at its own peak is better, and what a cluster costs is therefore the beating
inside it. No noise bed recovers that either: noise is uncorrelated with the
source and a cluster is not.

A MISTAKE WORTH KEEPING. The first version normalised the signal into the
valve's units by SUMMING the partial amplitudes -- the all-in-phase worst case,
which a dense sum never reaches. That underdrove the stage by about a factor of
two, and a factor of two at the input is a factor of eight in every third-order
product: the amplifier measured 50 dB down and did nothing audible. With the
crest factor a random-phase sum actually has (about 3x rms) the same drive gives
**25 dB down**, which is an amplifier being worked. The model was right and the
level it was fed was not. The numerical path does not have to guess at a crest
factor at all -- it synthesises the signal, so it measures the peak.

## The electric guitar: two combs, a magnet and a speaker

`patch_map` had said for a long time, and correctly, that "26-31 are electrics,
whose colour is an amplifier's, not a box's" -- and left them on the bodyless
plucked-string base because there was no amplifier to give them. GM 27 now has
its own voice. 25 does not and should not: it is an ACOUSTIC steel-string, a
different instrument, and unmeasured.

WHAT MAKES IT AN ELECTRIC IS THAT THERE ARE TWO COMBS. A string plucked at
fraction p feeds mode n with `|sin(n*pi*p)|`; a pickup at fraction q READS mode
n with `|sin(n*pi*q)|`, because a magnetic pickup senses the string at a point.
So an electric is the pluck comb the harpsichord already models, times a second
comb at the pickup, and the interaction of the two is most of what a guitarist
means by tone. The numbers are a Stratocaster's geometry, which is measurable:
648 mm scale, middle pickup 100 mm from the bridge (0.154), coil ~9 mm (0.014).

THE SERIES IS 1/n, NOT 1/n^2, AND THE MAGNET IS WHY. A plucked string's
DISPLACEMENT modes go as 1/n^2. A pickup's output is -dPhi/dt, so it reads
VELOCITY: another factor of n. Net 1/n -- a solid body is brighter than its
unplugged self because of the magnet, not the wood. Written as
`tonal_dampening = 2.0` plus `pickup_velocity`, so the two terms stay separable.

THE CABINET IS A PASS, NOT A BODY, and that ordering is the whole design.
`FormantBody` is already a loudspeaker in everything but name -- resonances,
antiresonances, a top corner, a low cutoff, power-normalised -- but a body is
applied in `harmonic_volume`, while a note's partials are being built, which is
BEFORE the amplifier pass. Put the cabinet there and it filters the clean
signal while every distortion product bypasses it. So `cabinet.py` runs on the
finished table, between `tubeamp.expand` and `leslie.expand`:

    string -> pluck comb -> pickup comb -> AMP -> CABINET -> room

Measured on the rendered guitar at drive 4, cabinet against none, matched at
800-2000 Hz: **-14.3 dB in 5-10 kHz, -19.9 dB above 10 kHz, and +3.0 dB at
2-5 kHz**. Bite up, fizz down. That is the difference between an overdriven
amplifier and a wasp, and it costs one gain per partial, because in the partial
domain a cabinet is a table lookup rather than a convolution.

PLAYING HARDER HAS TO BREAK UP, and it did not. `tubeamp.emit` normalised each
segment to its own peak, which divides the playing level out completely --
measured, distortion sat 21.89 dB under the signal at every input level across
24 dB. That is RIGHT for a Hammond, whose keys are on or off and whose swell
pedal sits in front of the amplifier, and wrong for anything with a picking
hand. `amp_reference` fixes it: a fixed peak, measured by rendering a hard
six-string strum (0.0655 in renderer units), that `drive` is taken against.
Rendered, an 18 dB difference in playing now produces 22.7 to 32.6 dB of
difference in distortion. `None` keeps the old behaviour, and the Hammond
keeps it.

WHY POWER CHORDS WORK, WHICH NOBODY TOLD IT. Distortion energy landing more
than 25 cents from any sounding partial -- products that beat against the chord
rather than reinforce it:

| interval | ratio | rough |
|---|---|---|
| octave | 2:1 | **0.3%** |
| fifth | 3:2 | **16.7%** |
| fourth | 4:3 | 21.0% |
| major sixth | 5:3 | 24.3% |
| tritone | 45:32 | 26.2% |
| major third | 5:4 | **27.3%** |
| minor third | 6:5 | 27.9% |

An octave is free, a fifth is about half as rough as a third, and everything
else lands in between. That is the power chord, arrived at from a transfer
function and a string -- nothing in the model was told which intervals survive
overdrive. The metric has a limit worth stating: a minor SECOND scores low for
the wrong reason, because its own partials are dense enough that everything is
near something, so it is not comparable and is not listed.

THE PREAMP IS SINGLE-ENDED, AND THAT IS WHY IT IS WARM. `tubeamp`'s default
stage is a balanced push-pull pair, which cancels its even orders exactly --
measured, h2 129 dB down -- and what is left is odd, which is a square wave,
which is a fuzz box. A guitar amplifier's gain stages are single valves with
nothing to cancel against: at `imbalance` 1.0 the same curve puts h2 15.8 dB
down, ABOVE its own third. So the electrics carry `amp_imbalance`, rising with
gain from 0.25 on the clean voice to 0.80 on the distortion one, and the
roughness table above is measured through the stage the instrument actually
has rather than through the default.

THE OTHER FIVE, and what separates them. It is not five fitted voices -- it is
one instrument with the pickup moved, the palm put down, or the gain turned up:

| GM | voice | pickup | drive | imbalance | h1 decay |
|---|---|---|---|---|---|
| 26 | jazz | 0.230+0.258 neck humbucker | 0.20 | 0.35 | 1.0 dB/s |
| 27 | clean | 0.154 middle single coil | 0.35 | 0.25 | 1.0 |
| 28 | muted | 0.100 bridge | 0.80 | 0.50 | **38.0** |
| 29 | overdriven | 0.100 bridge | 1.20 | 0.60 | 1.0 |
| 30 | distortion | 0.049+0.077 bridge humbucker | 3.00 | 0.80 | 1.0 |
| 31 | harmonics | 0.154, touched at 1/2 | 0.25 | 0.25 | 1.0 |

Rendered on one passage, each at its own drive, against the same passage with
the amplifier out: centroid 252 / 325 / 626 / 502 / 801 / 226 Hz and distortion
-26.7 / -24.6 / -14.7 / -8.1 / -4.8 / -36.1 dB. Distortion is monotonic in
`amp_drive`, as it must be; the brightness ordering is pickup geometry, because
a neck humbucker nulls h4, h8 and h12 at once while a bridge one does not reach
its first null until h16.

TWO OF THEM NEEDED A MECHANISM, not a number. A palm mute is a DAMPER, so it is
a decay rate and not a filter: 38 dB/s on the fundamental against 1, and 94 on
the 8th. The attack is undamped, because the palm cannot act before the pick
does -- that ORDER is the sound, and a voice that merely rolled the treble off
would get the chug and lose the click. And a guitar harmonic is a touched NODE:
rest a finger at 1/k and every mode without a node there is killed, so
`harmonic_touch` DELETES modes where a comb only weights them. The mth partial
heard is then string mode m*k, which is where the pluck comb and the pickup
comb must be read as well. Measured, it takes the fundamental's share of the
series from 21.5% to 60.2%, which is the glassiness.

## Guitar fret noise is a different patch from guitar harmonics

Two things that sound like they might be the same and are not. GM 31 is a
guitar HARMONIC -- a finger resting on a node so that most of the string cannot
speak. GM 120 is fret noise: the squeak a hand makes shifting position, which
on a real guitar track is most of what tells you a human is playing it. The
repo had the first and, for 120, fell through `_fill(120, 127, MalletProperties)`
to a struck bar -- fixed modes and a decay, where this has a swept fundamental
and a duration set by the hand. Its neighbours 121 and 122 had their own
classes already, so it was a hole rather than a policy.

THE BAND IS FIXED, AND THE FIRST VERSION GOT THAT WRONG. A round-wound string
is a helix, and a fingertip riding over the windings crosses a ridge every
winding pitch -- so the squeak's frequency is slide speed over winding pitch,
roughly 700 Hz to 3 kHz, and has NOTHING to do with the note being fretted. The
first version let the note set the band on the argument that the note could
stand in for hand speed. It cannot: written into a guitar part the squeak then
lands on a musical pitch, in the middle of the guitar's own register, and is
heard as another note. Measured, 58% of its energy sat in 300-700 Hz. Ben,
hearing it: *"it just sounds like a regular guitar, not frets."*

So the band is a FORMANT, the mechanism this codebase already has for
resonances that stay put while the harmonics slide through. Measured on the
model, the centroid is **1541 Hz at a 110 Hz fundamental and 1330 Hz three
octaves up** -- essentially fixed -- where breath, which has no band to keep,
moves 1849 to 3520 Hz with its note.

THE WASH HAD TO BE BANDED, NOT TURNED DOWN, and this is the part worth keeping.
The chiff that makes a scrape out of a buzz defaults to spraying white noise
from every partial regardless of where that partial sits, and shaping its LEVEL
does not fix it. Three renders:

| | 700 Hz - 3 kHz | above 6 kHz | centroid | periodicity |
|---|---|---|---|---|
| wash unbanded | 12% | **72%** | 10.9 kHz | 0.03 |
| wash off | **99.6%** | 0.0% | 1.8 kHz | **0.91** |
| wash banded | 84% | 3.8% | 2.3 kHz | 0.12 |

The partial table was 99.6% correct in all three; only the render differed,
because the noise was being made everywhere. And switching the wash off puts it
back in band and turns it into a TONE -- 0.91 is the "which is a beep" failure
`noisegen.py` records for fricatives built out of partials. The two failures
sit on either side and neither is a matter of degree; `chiff_bandwidth` is the
only thing that gets both. `tonelib.py` already carried the same finding for a
sibilant: "THE WASH MUST GET THE BAND, not merely a roll-off... the model put
92% of an /s/ between 5 and 7.5 kHz and the render came back with a centroid of
1233 Hz, which is not a sibilant, it is a rustle."

A RELATED TRAP: heavy inharmonicity and a band are incompatible. `harmonic_volume`
evaluates the body filter at `f0*m`, not where stiffness has actually put the
partial, so at the 45x the breath and gunshot voices use, a partial nominally at
8.8 kHz sounds at 43 and the band is applied to a frequency it is nowhere near.
Those two can use 45x precisely because they want no band at all. This uses 3x.

THE GLIDE WAS ALREADY MODELLED, as the piano's tension bloom -- it has exactly
the shape a position shift has, starting displaced and settling exponentially,
because a hand is fastest when it leaves and stops when it arrives. What the
piano did not need was the range: the bend was capped at a literal 0.04 "so an
extreme-bass fff can't bend absurdly", 68 cents, where a slide sweeps most of an
octave. That cap is now `tension_bend_max` and is a no-op for everything that
had the literal. Rendered, an A5 at velocity 110 falls 1051 -> 987 -> 901 Hz
through the note; at velocity 50 only 876 -> 831, because `attack_volume` scales
the bend -- a hard note is a long fast shift and a soft one a short one.

ONLY WOUND STRINGS SQUEAK. The plain trebles have no helix to ride over, so
`octave_gain` takes 9 dB an octave out as the part climbs into the register
where the strings would be plain -- measured, 18 dB across two octaves.

WHICH MAKES WHERE IT IS WRITTEN MATTER MORE THAN THE GAIN. Peak against peak
against the guitar beside it, a squeak on a low wound string at a hard shift
sits about 21 dB under; the SAME voice written up at G5 sits 36 dB under,
because there is no winding up there and the model says so. The first demo
wrote them at G5 and D5 and they were inaudible, which is the model being
right and the part being wrong -- raising the gain to rescue a treble squeak
would put a bass one over the note.

Levelled by ear from there: 14.6 dB under was "a bit too loud", which is the
same judgement the recordings make -- fret noise is evidence that a hand moved,
not a part. The level is linear in `initial_gain`, so that is the one knob.

(And a measurement worth not repeating: "about 27 dB under a hard chord" came
from comparing a 0.3 s squeak's RMS with a 1.6 s sustained chord's RMS. A
transient against a held note is not like-for-like; peak against peak is.)

## The electric basses are the guitar on a longer string

GM 33-37. Not new physics -- two combs, a magnet reading velocity, no body --
so they are `ElectricGuitarProperties` with the geometry of a different
instrument and a cabinet built for a different job. What actually differs:

| GM | voice | what makes it that | pickup | strike |
|---|---|---|---|---|
| 33 | fingered | the base: a broad soft fingertip over the neck pickup | 0.191 | 0.12 / depth 0.55 |
| 34 | picked | a plectrum is HARD and NARROW, and played nearer the bridge | 0.191 | 0.09 / **0.90** |
| 35 | fretless | the string stops on WOOD, which is lossy | 0.191 | 0.12 / 0.45 |
| 36 | slap | the thumb drives the string onto the frets | 0.081 | **0.06 / 1.00** |
| 37 | popped | convention, not measurement: slap 2 taken as the harder one | 0.081 | 0.06 / 1.00 |

Measured on a low E, the mean harmonic of the series: fingered **2.6**, picked
**3.2**, fretless 2.5, slap **5.4**. The pick/finger difference is the right
hand and nothing else, which is what those two GM slots actually are.

FRETLESS IS A TERMINATION, NOT A FILTER, and this is the one worth stating. A
fretted note ends on hard metal wire, which reflects the high partials almost
perfectly; a fretless note ends on fingerboard timber under a fingertip, which
does not. So the harmonics GO rather than never arriving -- h8 decays at
32 dB/s against the fretted 8, on an identical spectrum. Darkening the voice
instead would take the top off the ATTACK, where on a real fretless it is
plainly present; the "mwah" is the loss, not the absence.

A SLAP IS A COLLISION and this approximates it rather than modelling it. The
thumb drives the string onto the frets and it rattles back off; each contact is
nearly an impulse, and an impulse is broadband. A moving boundary condition is
not something this engine can say, so what it says instead is the consequence:
a hard, narrow, near point-source excitation, whose first comb null is past the
16th harmonic rather than at the 8th. That gets the brightness. It does not get
the rattle, which is a separate sound and wants `noisegen`.

THE CABINET IS A DIFFERENT BOX, not the guitar's scaled down. A low E is 41 Hz
and its FUNDAMENTAL is the note, so `bass410` reaches -4.9 dB at 45 Hz where
`guitar12` is -10.4; and its presence peak is -0.4 dB at 2.5 kHz where the
guitar's is +6.4, because that peak is what makes a guitar bite and on a bass
it would only honk. The amplifier runs at a quarter of the guitar's drive:
distortion moves energy UP, and a clipped bass loses the fundamental it is
there to supply.

AND THREE ARE LEFT ALONE. 32 "Acoustic Bass" is an upright -- a large wooden
box with its own radiating body, which is the one thing a solid-body has not
got -- and it is unmeasured; 38 and 39 are synth basses with no string, no
pickup and no cabinet. Modelling either would be flattery.

## A channel fader is not in front of the amplifier

`chan_vol` is CC7*CC11 squared and it multiplies into every partial's gain
(`tonelib.py`, `gain = ... * attack_volume * channel_volume`), so by the time
`tubeamp` reads `aM` the mixer has already been applied. Turning a channel down
was therefore making the valve distort LESS, which is not what a fader does:
the amplifier is on the instrument's signal path and the fader is after it.

Found on Riffsym, whose rhythm guitars sit at CC7 87 and velocity 100. They
were reaching the valve at 0.370 of the reference where the lead, at CC7 127,
reached 0.787 -- so a nominal `amp_drive` of 3.0 was rendering as about 1.1,
and the DISTORTION voice was arriving at the OVERDRIVEN setting, on the two
parts that carry the riff.

The fix is to scale `amp_reference` by the same `chan_vol`. The drive then
depends only on how hard the strings are hit, and the products still come out
at the faded level because they scale with the input. Verified on one chord at
two fader settings: CC7 127 and CC7 64 differ by 12.0 dB of level -- exactly
(127/64)^2 -- and by **0.0 dB of distortion ratio**, both -8.6 dB.

VELOCITY IS NOT TAKEN OUT, and must not be. How hard a string is struck IS how
hard the valve is driven; that is what `amp_reference` exists to express. A
fader is a different kind of number, and the distinction is the whole fix.

## Where "drive 1.0" sits, and who gets to set it

`amp_reference` was measured at velocity 127 -- as hard as MIDI can say -- so
the nominal `amp_drive` was only reachable by a note played at maximum, and no
real file does that. Riffsym writes all 727 of its notes at velocity 100, and
`attack_volume` is `(vel/127)^2`, so its distortion guitars sat at **0.620** of
nominal for ever: a 4.1 dB shortfall that never moved, on every amplified voice
in the corpus.

So the reference is now measured at velocity 100. drive 1.0 means the edge of
breakup at NORMAL playing, and digging in goes PAST it -- which is how an
amplifier is actually set up: you put your usual touch where you want it and
let the hard notes exceed it. Guitar 0.0655 -> **0.0406**, bass 0.0264 ->
**0.0164**. The Hammond is untouched, having no reference at all: its keys are
on or off, so there is no "normal touch" to calibrate to.

AND A FILE CAN NOW SET THE KNOB OFFLINE. CC1 was the gain control live and
ignored offline, so a part could ask for a setting when played and not when
rendered. It is now `amp_drive * 4.0 * cc/127` in both -- unquantised offline,
because there is no recompute to economise on -- taken from the FIRST CC1 on
the channel, since offline the drive is a setting rather than a control being
moved. Measured on GM 27 at velocity 100: CC1 absent -30.1 dB, 16 -37.8,
64 -20.1, 127 -11.2.

NOT FOR A ROTOR, though, and that asymmetry is deliberate. Offline CC1 is the
Leslie half-moon and the organ renders depend on it; live resolved the clash by
moving the half-moon to the pitch wheel, which offline has no reason to do
because there is no wheel to move. The selftest checks the two mappings agree
to within one of live's quantisation steps, since they are two implementations
of one number.

## Six GM programs were pointing at the wrong kind of instrument

Not fits, not tunings -- category errors, where a program fell through a
`_fill` to a family base that makes a different physical claim. The voice that
models each one was already in `tonelib.py`, fitted for the drum kit on channel
10 and reachable from a melodic channel like any other. 115 Woodblock had been
pointed at one long ago and its neighbours were left behind.

| GM | was | is | what changed |
|---|---|---|---|
| 15 Dulcimer | plucked string | `HammeredDulcimer` | **struck**, not plucked |
| 112 Tinkle Bell | struck bar | `Crotale` | small tuned bells; rings where a bar does not |
| 113 Agogo | struck bar | `Agogo` | the class was named for it |
| 116 Taiko | struck bar | `MembraneDrum` | a drum, not a bar |
| 117 Melodic Tom | struck bar | `TomTom` | likewise, and pitched |
| 126 Applause | struck bar | `Applause` | noise, the same error fret noise was |

A DRUM THUMPS AND A BAR RINGS, which is the audible content of most of it: a
melodic tom's fundamental now decays at **70 dB/s** where the bar it had been
gave it **4**. Applause goes from a mean harmonic of 1.2 -- a near-sine with a
couple of modes -- to 5.1, which is noise. Agogo brightens from 1.2 to 3.0,
because agogo bells are bright metal and a marimba bar is not.

THEY KEEP `one_shot`, and that is deliberate: a struck drum or bell ignores the
stick being lifted, so note length is the file's opinion rather than the
instrument's. The same argument `NoiseDrumProperties` already records for the
kit -- "GM sequencers write arbitrary drum note lengths".

A HAMMERED DULCIMER IS STRUCK, which is the distinction the class hierarchy is
built on; its cousin the psaltery is the plucked one. And a dulcimer hammer is
a bare wooden spoon, narrow and hard at every dynamic, so the strike comb's
notch never fills the way a piano's felt fills it -- the harpsichord quill's
argument arrived at from the other direction. Each note is a COURSE of two to
four strings never quite in tune, which is the shimmer, and nothing dampens it.

FOUR WERE LEFT AS BARS, each for a reason. 114 Steel Drums is a tuned pan, a
shaped metal dome with tuned areas, which nothing here models; 118 Synth Drum
has no physical referent; 119 Reverse Cymbal needs a BACKWARDS envelope and
there is no mechanism for one; and 123-125 (bird, telephone, helicopter) want
voices of their own, as 120 fret noise did.

## The steelpan, built from the instrument's design

BUILT FROM THE DESIGN, THEN CHECKED. Iowa's percussion is marimba, xylophone,
vibraphone and bells; VCSL's Struck Idiophones has forty-one entries -- anvils,
brake drums, slit drums, gongs -- and no steel pan. So the voice was written
first from the instrument's design, on the footing the toms set: the ratios are
physics, the gains are judgement.

Then it was checked against **Freesound 742254** (sciencewithmike, CC0, 28 min,
48 kHz/24-bit mono, "various sounds from the steel drum"), which turned out to
contain 408 strikes with over a second of clearance, of which 79 have 1.5 s
before and 2 s after. Forty were analysed; 26 are dominated by a single note.

THE SPLIT WAS EXACTLY THE ONE THE CLASS PREDICTED. Every RATIO held and every
GAIN was wrong by 20-30 dB:

| | asserted | measured |
|---|---|---|
| mode 2 / f0 | 2.000 | **1.9978** (-2 cents) |
| mode 3 / f0 | 3.000 | **2.9972** (-2 cents) |
| above mode 3 | untuned | untuned: 128 partials spread 3.2x to 9.2x |
| mode 2 level | -1.9 dB | **-29 dB** (10th-90th: -36 to -16) |
| mode 3 level | -6.0 dB | **-37 dB** (-48 to -27) |
| upper levels | -16 to -31 dB | **-43 dB** |

"The octave is nearly as loud as the fundamental, which is where the
instrument's brightness comes from" was the assertion, and it is wrong by
27 dB. The fundamental is the strongest peak in 20 of 20 strikes where all
three modes could be read: the tuned modes are exactly where the maker put them
and they are QUIET. Nor is it an envelope effect, which was the obvious escape
-- the upper modes measure 24-30 dB down in every window from the first 80 ms
out to 1.5 s, so they are not strong in the attack and fading.

THE TUNING IS THE PHYSICS, and it is unusual enough to be the whole reason the
voice is shaped this way. A steelpan's overtones are HARMONIC BY INTENTION: the
panmaker hammers each dished note area until its principal modes sit at the
fundamental, the OCTAVE and the TWELFTH -- 1 : 2 : 3 -- and tunes them by ear
one at a time. That is a design intention rather than a property of the shape,
and it is why a steelpan sounds sweet and pitched where a gong, which is the
same steel and nearly the same geometry, does not. It is also why a mode SET is
the right shape here and a harmonic series with a comb is not: the maker put
the modes where they are.

So `mode_ratios` opens `1.000, 2.000, 3.000` exactly, and the selftest requires
it: if those stop being exact the voice has stopped being a steelpan and become
a bell.

ABOVE THE TUNED THREE, NOTHING IS TUNED. Nobody hammers those, so they sit at
no particular ratio and supply shimmer rather than pitch. The four upper ratios
are PLACEHOLDERS -- deliberately non-integer so they shimmer instead of
reinforcing, and deliberately not precise, because four decimal places would be
four invented decimal places. They are the first thing a recording replaces.

THE RING IS THE SECOND. `one_shot` means note-off is ignored, so the decay
alone decides how long a note lives. It is NOT, as assumed first, what decides
whether a fast run turns to mush: measured on a fifteen-note run at 150 bpm the
buildup from first note to last is +7.7 dB at decay 2.0 and +7.1 dB at both 3.0
and 6.0 -- over a second and a half the decay barely enters into it, and that
buildup is simply what a ringing instrument does. What it really sets is ring
LENGTH: 12.5 s to -40 dB at 2.0, 9.5 at 3.0, 5.6 at 6.0. A tenor pan rings for
seconds and not for ten of them, so it is 5.0, which is 6.5 s.

SYMPATHETIC COUPLING IS A QUARTER OF THE SOUND, and the recording says so
numerically: across 40 isolated strikes a median of **23%** of the peak energy
is not a harmonic of the note struck. It shows up as partials at 0.75, 0.80,
1.33 and 1.50 of the fundamental -- fourths, thirds and fifths, which are
musical intervals and not modes, because they are the neighbouring note areas
answering through the shared steel. A quarter of what you hear is notes nobody
hit. This engine has no cross-note coupling, so that quarter is missing, and it
is now the largest known gap in the voice rather than a suspicion.

Still not modelled either: thin steel struck hard is nonlinear, so the pitch
moves as the note settles. `tension_bend` could express it; the direction and
size were not measured here.

## Which of a steelpan's neighbours are really ringing

The coupling histogram raised a problem: a major second at 27% against a fifth
at 20%, where a model built on distance round the cycle of fifths says the
fifth -- ONE step, the area physically next door -- should dominate. Fitting
that would have meant making the coupling RISE with distance, which is not a
thing that happens.

The test that settles it is to ask whether each non-harmonic partial is a NOTE.
A steelpan note is tuned 1:2:3 by the maker, so a genuinely sounding neighbour
must carry its own octave and twelfth; peak-picking noise will not.

| interval | carries own 8ve | own 12th | level | |
|---|---|---|---|---|
| P4 | **76%** | **84%** | -29.5 dB | a note |
| P5 | **74%** | 54% | -25.7 dB | a note |
| M2 | 58% | 32% | -32.6 dB | part |
| M3 | 56% | 30% | -34.4 dB | part |
| m2 | **3%** | 25% | -37.8 dB | **not a note** |
| TT | **4%** | **0%** | -37.1 dB | **not a note** |
| m3 | 11% | 22% | -39.9 dB | **not a note** |
| m6 | 8% | 12% | -38.2 dB | **not a note** |

The partials that behave like sounding notes are overwhelmingly the FOURTH and
the FIFTH -- one step round the cycle, which is the area next to the one that
was struck. The intervals that disagreed with the spatial model are the ones
that are not notes at all: 3-11% carry any mode structure, and they sit 10 dB
below the ones that do.

THE SPATIAL PATHWAY IS CONFIRMED in its main claim, and the earlier note that
the model "over-weights one-step intervals" was wrong -- the target was
contaminated, not the model. What remains unsettled is the finer shape: M2
against M6 against M7 moves substantially with how the analysis is sliced,
which is about what one 28-minute recording of one instrument through a lossy
preview can support. It is not fitted, and should not be.

## The sitar, and why sympathetic strings need just intonation

GM 104, asserted throughout -- neither collection has a sitar (Iowa's plucked
instruments are guitar and piano; VCSL's Composite Chordophones are two harps
and a strumstick), so the SHAPE follows from how the instrument is built and
the LEVELS are guesses. The steelpan is the cautionary tale: its ratios were
right and every one of its gains was wrong by 25 to 30 dB when a recording
turned up.

THE JAWARI IS THE SOUND. A sitar's bridge is a wide gently curved plate rather
than a knife edge, and the string rests along it. As the string swings its
contact point MIGRATES along the curve, so the speaking length changes every
cycle -- a boundary moving at the string's own frequency, generating energy
high in the series continuously rather than only at the pluck. That is why a
sitar keeps buzzing where a guitar's attack is bright and then dulls.
Approximated here as a shallow roll-off plus an unusually FLAT decay across the
harmonics; the second is the part a merely bright plucked string would not give.

AND THE STRINGS UNDERNEATH ONLY RING IF THE MUSIC IS JUST. This is the
interesting result. Coincidence resonance needs the driver's partial to land
INSIDE the responder's resonance, and the width of that resonance comes from
the decay: a sitar string ringing 7 s has a mode 0.1 Hz wide, a Q near 2800.
An equal-tempered fifth is two cents narrow of a just one, which at these
frequencies is several bandwidths. Measured on the model, the coupling of a
taraf string a fifth below the played note:

| tuner | coupling | |
|---|---|---|
| equal | 0.005 - 0.014 | essentially nothing |
| just | **0.467** where the interval is exact | **35 dB stronger** |
| hybrid | 0.025 - 0.468 | wherever it happens to be exact |

Rendered on the same eight notes, `even` emits 6,300 sympathetic partials --
octaves, essentially -- and `just` emits **33,082**, which is the fifths,
fourths and sixths joining in. Counted as responders rather than partials it is
9 against 56. So a sitar rendered in equal temperament is a dry sitar,
and that is not a defect in the model -- it is why the instruments that carry
sympathetic strings belong to musics that do not temper. A sitar's taraf are
tuned by ear against a drone, and the drone is what makes them ring.

THE TUNER'S TONIC IS SA, and that is the tuner's constraint rather than the
instrument's. Indian classical tunes the twelve swaras in just intonation
against a fixed Sa, and `tunelib.JustTuner` is exactly that ratio set --
16/15, 9/8, 6/5, 5/4, 4/3, 45/32, 3/2, 8/5, 5/3, 9/5, 15/8 -- but with its
tonic nailed to C. The first version put Sa at C#, the common concert pitch for
a sitar, which meant the taraf were tuned to intervals that were not pure:
measured from C# the fourth is 21.5 cents off where from C it is the just 2.0.
A real sitarist puts Sa where they like and retunes the taraf to match, which
would need a tuner whose tonic moves.

AND THE RESPONDERS HAVE TO BE AT THEIR OWN TUNED PITCHES. They were being
placed an EQUAL-tempered interval from the driver -- `f0 * 2**(s/12)` -- which
is two cents from the just pitch and, at Q 2800, several bandwidths. So only
the octave ever coincided, because an equal-tempered octave is also a just one,
and the just tuner bought nothing except a louder octave. Taking the string's
frequency from the tuning table instead is what turns 9 responders into 56.

HOW LOUD, AND IT IS A GUESS. The coupling gain has no measurement behind it,
and the steelpan is the precedent for how that usually goes. Measured on the
rendered passage, the first value put the taraf **5.6 dB** under the played
string -- which is two instruments rather than one with a halo. It is now
14.9 dB under; 0.20 gives -10.5 and 0.07 gives -19.7, so the knob is roughly
linear in dB.

Worth checking and reassuring: they do NOT accumulate. Nothing damps a taraf
and every note adds nine more ringing for seven seconds, so the obvious fear is
a wash that climbs through a passage. Measured second by second it sits at a
steady -5.7 dB relative to the melody rather than rising -- the strings reach a
balance because they decay at the same rate the melody feeds them.

WHAT THE FIRST DRAFT GOT WRONG, since Q is entirely a function of decay: it had
the string ringing 32 seconds, which put the modes at Q 12000 and made
everything couple to nothing, in every tuning. 7 s is a sitar. The lesson
generalises -- in this engine an unphysical decay silently becomes an
unphysical resonance, and only sympathetic coupling makes that visible.

## Which tuners are at which pitch

`tunelib` gives every temperament its own A, and the split is now by period
rather than by accident:

| A440 (modern) | A415 (baroque) |
|---|---|
| equal, just, linear, Bechstein | **hybrid**, **hybridharm**, Werckmeister, meantone, Pythagorean, well, Sankey |

TWO THINGS MOVED. `even` was at 415, which made it the equal-tempered control
for Werckmeister and meantone -- defensible, but it also made `even` the wrong
thing to reach for whenever the music is not Bach, and wrong *silently*: a
render simply came out a semitone flat and nothing said so. It caught this
session twice, once for an hour, because an analysis that assumed A440 found
every partial a semitone from where it looked.

And `hybrid`/`hybridharm` had no A at all. Path-generated tuners take
`A = None` to mean "use the generator's own frequencies", which put A4 at
441.04 -- near modern pitch by accident rather than by decision. They are the
tuners verified by ear FOR BAROQUE, so they now carry baroque pitch, and naming
A rescales the whole table so A4 lands there.

The baroque equal-tempered control is therefore `hybrid` rather than `even`,
which is the tuner that should have been playing that part all along.

AND THE TEMPERAMENT IS NOT THE PITCH. Those are two questions and one attribute
was answering both, so wanting the hybrid temperament meant accepting baroque
pitch with it. `hybrid440` and `hybridharm440` are the same ratios -- measured,
0.0000 cents of difference across 25 notes, a pure transposition -- with A4 at
440. A modern instrument playing a well-tempered scale is not a contradiction;
it is most pianos.

**`hybrid440` is now the general default** for `blockrender`, `play.py`,
`soloforward.py`, the live TUI and `render-corpus.sh`. `examples/organ.py`
stays on `hybrid` at 415 deliberately and says so: that recipe is Bach on an
organ, and baroque pitch is part of it.

A LATENT BUG THIS EXPOSED. `HybridHarmonicTuner._build_table` derived its
pure-octave table by calling `HybridTuner._build_table()` BY NAME, so it always
used HybridTuner's reference pitch rather than its own. Harmless while every
hybrid shared one A; wrong the moment one did not, and `hybridharm440` duly
came out at 415 while saying 440. It calls the base implementation with `cls`
now.

BLAST RADIUS, and it is not small: every `even` render moves up a semitone and
every `hybrid` render down about 101 cents. `hybrid` is the default for
`render-corpus.sh` and for `blockrender` itself, so the whole corpus re-pitches.
`set_reference(a=...)` still overrides all of it per render, and
`TUNING_REFERENCE` exposes that from the command line.

---

## The electric pianos: GM 4, and everything you hear is the pickup

GM 4 and 5 were swept up by `_fill(0, 7, GrandPianoProperties)` and rendered as
a Steinway B -- stretched strings, a soundboard, a hammer low-pass, phantom
longitudinal partials. A Rhodes has no strings, no soundboard and no unison
trios, so none of that is true of it. GM 4 now has its own voice.

**The sources**, and they are unusually good ones:

- M. Muenster and F. Pfeifle, *Non-Linear Behaviour in Sound Production of the
  Rhodes Piano*, ISMA 2014, Le Mans, pp. 247-252.
- F. Pfeifle and M. Muenster, *Tone Production of the Wurlitzer and Rhodes
  E-Pianos*, DAGA 2017, Kiel, pp. 556-558.

Both are Hamburg, and both are measurements rather than models: a Vision
Research Phantom v711 high-speed camera at 38,000-44,127 fps tracking the tine
itself, a PCB 352C23 piezo accelerometer on the tonebar, and a Kistler impulse
hammer -- with the instrument's own direct out recorded simultaneously.

### Four findings, and each one changes the model

**1. The tine vibrates as a PURE SINE.** Four points tracked along a struck
tine, plus the transverse and longitudinal directions compared: "after an
extremely short transient the tine vibrates in a perfect sinusoidal motion
without appearance of higher harmonics", and "there are no further eigenmodes
than the lowest". So there are no cantilever overtones to model here -- not
6.267, not 17.55. One mode. A voice built on the cantilever series would have
been building the wrong instrument out of correct physics.

**2. Every harmonic you hear is made by the PICKUP.** "The presented
measurements... lead to the conclusion that the primary mechanical exciters are
secondary for the sound production of both instruments and their specific
timbres are influenced primarily by the specific pickup system." The magnet is
a wedge-shaped frustum, and the FEM model in the DAGA paper shows its field has
"an approximate bell curve characteristic". So the tine swinging through it is
a waveshaper:

    Phi(u) = exp(-(u/w)^2),   u(t) = x0 + A sin(wt),   V = -dPhi/dt

**3. The tonebar is NOT tuned to the tine.** "Opposed to common belief, the tine
and tonebar are not alike in pitch or resonance frequency. Their fundamental
resonance frequencies are several hundred to more than 1400 cents apart." The
tine *enslaves* it -- the tonebar is driven at the tine's frequency, perfectly
in phase or anti-phase -- so its own eigenfrequencies "are not present in the
sound, they only appear in the transient". It is the glockenspiel-like attack
and nothing else. Table 1 of ISMA 2014 gives nine measured pairs:

| tine Hz | 79 | 118 | 176 | 263 | 393 | 588 | 880 | 1316 | 1969 |
|---|---|---|---|---|---|---|---|---|---|
| tonebar f0 Hz | 51 | 69 | 79 | 105 | 138 | 183 | 140 | 145 | 222 |
| phase | anti | anti | in | in | in | anti | anti | anti | in |

fitted here as `tonebar_hz = 10.06 * f0**0.4066`, 16% rms. The fit's value is
not its accuracy -- a transient's pitch is not its point -- but that it carries
the measured *divergence*: the tonebar is at 0.75 of the tine at the bottom of
the compass and 0.11 at the top, so no fixed ratio could do it.

**4. Velocity is a timbre control more than a volume control.** "Velocity
sensitivity is to be distinguished by a change in volume to lesser extent than
in sound. Playing softly the fundamental comes up, playing harder the more and
more growl appears." And the growl is register-dependent: "best audible in the
lower register of the rhodes where the tines have a larger deflection."

### Two things fall out of the curve, and both were verified

**Centre the tine and the fundamental disappears.** A symmetric field crossed
twice per cycle answers at twice the pitch: "when aligned perfectly centered,
the produced sound behind the pickup is twice the fundamental of the tine". At
`pickup_offset = 0.0` the fundamental measures 297 dB under the octave; at 0.30
it is 9.2 dB over it, and at 0.60, 24.2 dB. That is the voicing screw a
technician actually turns, and `TUNING_EP_VOICING` exposes it
(`examples/rhodes.py --voicing`).

**Harmonic k grows as A^k, so harmonic k decays k times as fast.** Fitted
log-log slopes of harmonic amplitude against deflection: 0.992, 1.995, 2.993,
3.995, 4.994, 5.995 against a wanted 1..6. And *this engine's decay law already
is that* --

    base = decay_db + harmonic_decay_db * h * (h ** harmonic_decay_dampening)

is exactly `k*D` when `decay_db` and `harmonic_decay_dampening` are zero. So the
growl fading into a bell as the note rings -- the Rhodes' whole signature --
costs nothing, needs no time-varying spectrum and no work at render time.
Measured on a struck low F at full velocity, the harmonics above the
fundamental run `-0.2 dB` at the attack, then `-6.4`, `-14.3` and `-20.1` over
the next three seconds.

### Why this does not go near the tube amp

`tubeamp` exists because distortion of a *chord* is not distortion of its notes
-- only 27% of the distortion energy lands on harmonics of the inputs. None of
that applies here. The pickup reads ONE tine, so its nonlinearity is one note's
own curve, and a waveshaped sine gives back an exactly harmonic series. The
whole thing is therefore an amplitude law in `series_volume()` and a decay law,
with no new renderer machinery at all. `amp_drive` stays at 0: a suitcase has a
power amp that can be pushed, but the growl is the pickup, and giving the voice
a valve as well would count the same nonlinearity twice.

**What did NOT carry over from the electric guitars, contrary to expectation:**
the pickup machinery. `pickup_points` is `|sin(n*pi*q)|`, a *string's* standing
wave sampled at a point in space. A tine has one mode and one pickup, and what
shapes this sound is the field's shape against *displacement* -- a different
physical quantity. What did carry over is the cabinet pass, the per-partial
decay law, the `series_volume` override pattern and the patch_map wiring.

### The control

A pickup that does not bend is not a pickup: `TUNING_EP_CONTROL=1` makes the
flux linear, so it hands back the sine it was given. Measured on the same
struck low F, the harmonics above the fundamental sit at **-75.9 dB** with the
waveshaper bypassed against **-2.1 dB** with it in. Seventy-four decibels of
this voice's harmonic content comes from the pickup, which is the paper's claim
put the only way it can be falsified.

### The tremolo, which is a pan

The Rhodes suitcase's panel calls it vibrato and it is not one -- it is the
signal swinging between two amplifiers. `tremolo.py` gets both that and a
Wurlitzer's true amplitude tremolo out of one mechanism, because AM is a
sideband pair (the argument `leslie.py` makes) and **a pan is that same pair
with the sign flipped in one ear**. So a stereo pan costs exactly what a mono
tremolo costs, and one minus sign is the whole difference between the two
instruments.

It also follows that the mono sum of a pan vibrato is flat, which is true of
the instrument: a suitcase heard down one microphone has no vibrato at all.
Measured, offline and live: each ear swings 11.5 dB at 5.5 Hz, 180.0 degrees
apart, with 0.18 dB left in the mono sum.

CC1 sets depth, and there is no conflict with the wheel's other jobs: the
amp-drive path is gated on `amp_drive > 0` and this voice has none, and a tine
has nothing that could be given a pitch vibrato anyway.

### GM 5, the Wurlitzer: one mechanism, a different curve

Built second, once the shared waveshaper was confirmed. It is not a Rhodes with
a filter on it -- it is a different instrument that happens to work the same
way, and three things follow from the curve alone.

**A pole does not fall off a cliff.** "Analogous to a capacitor microphone, the
capacity varies inversely proportional to the distance between the electrodes"
(DAGA 2017), so `Phi(u) = 1/(1+u)`. A Gaussian is entire, so the Rhodes'
harmonics collapse faster and faster; `1/d` has a pole, so its harmonics fall
off GEOMETRICALLY. Measured on the two voices at C4, velocity 127:

| | h2 | h3 | h4 | h5 | h6 | h7 | h8 |
|---|---|---|---|---|---|---|---|
| Rhodes | -7.1 | -23.0 | -41.2 | -57.2 | -81.7 | -- | -- |
| Wurlitzer | -4.5 | -11.5 | -19.5 | -28.1 | -37.1 | -46.2 | -55.6 |

The Rhodes' steps grow from 7 dB to 24; the Wurlitzer's stay between 5 and 9.
That straight line in dB is the bark, and it is the whole difference.

**A one-sided plate is asymmetric wherever the reed sits.** A Rhodes' magnet is
symmetric about the tine, which is why centring it kills the fundamental and
why voicing it is a real adjustment a technician makes. A Wurlitzer's plate is
on ONE side, so at rest position 0 -- where the tine loses its fundamental
entirely -- the reed still puts out h1 6.4 dB over h2. There is no centred case
to find, and `pickup_offset` survives as the gap rather than as a voicing screw.

**No tonebar.** "The reeds vibrate freely, providing a surface area large enough
to produce a measurable change in capacitance." There is no second prong and no
resonator, so `tonebar_gains` is empty and there is nothing to make the Rhodes'
glockenspiel-like attack. It also rings shorter: 3.1 s to -40 dB at C4 against
the Rhodes' 5.2.

Its speaker is the other half of why it sounds like itself. `WurlitzerInternal`
is a pair of 4x6" drivers in a plastic lid: -14 dB at 80 Hz where the suitcase
is at 0, so the reed's fundamental is already on the slope through most of the
compass and what you hear is its harmonics. **The bark is partly the speaker.**

And its tremolo is a true amplitude tremolo rather than a pan, because it has
one amplifier and one pair of speakers. Rendered at full wheel, both voices
swing about 9-10 dB per ear at 5.5 Hz -- but the Rhodes' two ears are 180
degrees apart and its mono sum swings 0.16 dB, while the Wurlitzer's are in
phase and its mono sum swings the full 9.10 dB. One mechanism, one sign.

**A NOTE ON THE SENSING CONVENTION**, since it decides the whole voice. Taken as
charge on a fixed-voltage plate the signal follows C and therefore 1/d, which is
the sentence the paper writes and what is modelled. Taken at constant charge the
voltage follows d instead and is LINEAR -- a condenser microphone's whole
virtue. The paper is explicit that the pickup is what shapes this instrument's
timbre and that "higher velocity results in a richer harmonic sound", which only
the first reading gives, so that is the one followed. It is an interpretation of
a circuit, not a measurement of one, and it is the weakest joint in this voice.

Also not modelled, and the paper names both: "non-exponential decay
characteristics and beating of higher partials". This voice decays
exponentially, per partial, at k*D like its sibling. The beating would need the
reed's own higher modes, and the same paper's camera says the motion is
"approximately sinusoidal", so the measurement does not say where it comes from.

### Still to do
- **The longitudinal transient is approximated.** The papers attribute the
  bright part of the attack to longitudinal waves converting to transverse at
  the tine/tonebar T-joint -- "10-15 times faster than transverse waves". That
  is carried here as two asserted tonebar modes at 12x and 24x, which is the
  one place in this voice where a number is not measured.
- **No recording has been fitted against.** Built from theory first, as the
  steelpan was. Freesound 536266 is a CC0 chromatic Rhodes but carries a
  deliberate stereo delay and heavy effects, so it is a poor measurement
  target; a dry single note would have to be found.

---

## Which way a struck thing bends

A follow-on from the Rhodes. Ben asked whether the pitch drift a piano has
should be the same on a metal bar, which is the right question: the mechanism
was being applied by instrument family rather than by what actually sets the
pitch.

**The rule is what provides the restoring force, not struck versus plucked.**

- **Tuned BY tension** -- strings and membranes. Pitch goes as sqrt(T), and
  striking displaces the string or head, which lengthens it, which raises T. So
  they bloom SHARP and settle. Piano 0.008, timpani 0.016, kick 0.045, toms
  0.030. Measured on the render, a grand piano's C3 starts **+10.4 cents** and
  settles over about 0.85 s.
- **Curved plates** -- cymbals, gongs, and the steelpan. No tension, but the
  curvature couples bending to mid-plane strain, so amplitude changes the
  stiffness.
- **Straight bars free at an end** -- glockenspiel, vibraphone, marimba,
  xylophone, celesta, music box, tubular bell, and the Rhodes tine. No tension
  and no curvature: nothing a mallet does changes the stiffness, so no bend at
  all. Measured on the render, the tine comes out at **+0.2 cents**, and its
  partial table carries exactly zero frequency modulation of any kind.

### The steelpan bends the other way, and the sign is not a guess

A pan note area is a shallow curved shell. For an oscillator with both a
quadratic and a cubic nonlinearity,

    w(a) = w0 * [1 + (3*a3/(8*w0^2) - 5*a2^2/(12*w0^4)) * a^2]

the quadratic coefficient enters **squared, with a minus sign**, so curvature
always softens whatever its sign, while the cubic stretching term of a flat
plate hardens. A pan is curvature-dominated -- and that is not an assumption
imported for the occasion, it is the reason `SteelPanProperties` exists at all:
the maker tunes the note areas 1:2:3 precisely *because* the quadratic term
pumps energy from the fundamental into 2f and 3f. A voice cannot claim that
tuning and simultaneously claim a hardening nonlinearity.

So `tension_bend = -0.004`, about 7 cents flat at full velocity in the middle
register, settling in 60 ms.

### The magnitude is asserted, and here is exactly why

I tried to measure it off Freesound 742254, the same CC0 recording the pan's
mode gains and coupling came from, and **could not**. The reason is the
instrument itself: a pan's fundamental is beaten on continuously by the
neighbouring note areas that this very class models as sympathetic responders.
Measured on that recording, a struck E4 has D4 and F#4 ringing 36-42 Hz away
and sometimes only 2.3 dB down, so the fundamental's instantaneous frequency
wanders several cents at all times, strike or no strike.

Averaged over 24 isolated strikes, by phase derivative on a narrow band:

| window | mean | bootstrap 95% CI |
|---|---|---|
| 4 ms | -1.4 cents | -6.4 .. +4.0 |
| 25 ms | +2.9 | -0.3 .. +6.4 |
| 60 ms | +14.9 | +4.4 .. +28.6 |
| 450 ms | -5.5 | -16.7 .. +2.7 |

and split by strike force: +3.0, +2.2, -9.2 cents, correlation with level
**-0.30**. A settling bloom must converge on its own reference and this does
not; the trace wanders in both directions throughout. That is not a small
effect measured imprecisely, it is no measurement at all. **-0.004 is chosen to
sit comfortably inside what that recording could not have seen** -- half what
the 17" crash carries -- in the direction the shell demands.

### Two probe failures worth recording

Both cost real time and both made correct code look wrong.

1. **A brick-wall analysis band has time smear.** The +-15 Hz filter used to
   isolate the fundamental has an impulse response about 67 ms long, and the
   pan's settle time is 60 ms -- so the bend was invisible through it, and the
   first render check read the bend as *positive and larger at low velocity*.
   The fix is the discipline that keeps working: render the A/B, bend on
   against bend off, with the same probe, so the smear cancels. Done that way
   the difference is -1.3, -3.9, -9.8, -2.1, -3.2 cents through the attack at
   velocity 127 against -0.1, -0.8, -2.1, -0.5, -0.6 at velocity 60 -- the
   right sign, and scaling with `attack_volume` as it should.
2. **A parabolic peak interpolator divides by a NEGATIVE denominator.** At a
   spectral maximum `y0 - 2*y1 + y2 < 0`; clamping it to `+1e-30` produced
   frequencies of order -1e29 Hz. Guard on the magnitude, not the sign.

### And the cymbal, remeasured: its modes do not bend at all

`CymbalProperties` carried **+0.007**, about 16 cents at ff, citing "+7.8 cents
at ff against -2.0 at mf, and -24.9 on the hardest-hit take". Three numbers that
disagree in sign are not a measurement of an effect. Remeasured on the same
Iowa takes -- `examples/cymbal_check.py`, which is in the repo so this can be
rerun -- tracking individual **well-isolated** partials by phase derivative:

| family | partials | median drift |
|---|---|---|
| crash / chinese / splash (16 files) | 96 | **+0.03 cents** |
| ride and ride bell | 36 | -0.27 |
| hi-hat | 13 | +0.39 |
| orchestral clash pairs | 58 | +0.61 |

203 partials, every group under a cent, no correlation with strike level
(-0.08), and mf indistinguishable from ff. `tension_bend = 0.0`.

**The method matters, and it is why the first answer was wrong.** A spectral
peak estimator is biased by a decaying amplitude and dragged by neighbouring
modes decaying at different rates -- which is precisely a cymbal, whose modes
sit as little as 15 Hz apart. The phase derivative of a narrowly banded
analytic signal does not care about the envelope at all. And the probe was
checked against planted bends BEFORE being believed about their absence:
+10.0 cents came back +9.53, +5.0 came back +4.83, -10.0 came back -9.66, and
zero came back -0.00.

**What the old number was actually seeing was the SPECTRUM, not the modes.** A
cymbal's bright modes decay far faster than its low ones, so on these same
files the centroid falls **1400 to 2100 cents** through the ring while every
individual partial stands still. That is differential decay, which
`harmonic_decay_db` already does, and it needs no nonlinearity anywhere.

**And the shallow-shell argument did not rescue it.** A domed plate should
SOFTEN, so the old value had the wrong sign as well as the wrong size -- but
the measurement says the honest answer is neither. The effect goes as amplitude
squared, and an orchestral stick stroke never reaches the regime where a
cymbal's nonlinearity speaks; that regime is real, it is just not orchestral
playing. **Predicting that the old value was wrong is not the same as
predicting the right one, and the theory only did the first.**

Removing it costs nothing that was doing work: the model's brightening from
velocity 70 to 127 goes from +98 cents to +84.

### ...and the decay that was standing in for it is an order out. NOT FIXED.

Removing the bend exposed the real problem. Rendered and measured against the
reference with identical windows and band, the model's spectrum falls **275
cents** through the ring where a real 17" crash falls **1614 to 2126**. A
cymbal's actual "drift" IS its differential decay, and the parameter carrying
it is badly wrong. **An attempt to fit it was made and REVERTED**; what follows
is what was learned, because the next person will want it.

**THE REFERENCES ARE WEAK HITS, and Ben asked whether that was accounted for.**
For a *decay* fit it is testable rather than assumed, so it was tested:

| band | mf | ff |
|---|---|---|
| 800-2000 Hz | 3.5 dB/s | 3.2 dB/s |
| 2000-4000 Hz | 5.0 dB/s | 6.2 dB/s |

Decay is level-independent across the dynamics that have SNR, which is what
linear damping predicts and what "a hard crash is the same sound louder"
already said from the spectral side. **So a decay law fitted to stick takes
would carry to a harder stroke.** That part of the plan was sound. (The
pitch-bend conclusion above is the one genuinely bounded by the dynamics.)

**The measured curve, which stands and is worth having.** Individual modes
cannot be isolated above about 5 kHz -- the field is too dense -- so this is
octave-band energy decay in dB/s, and `examples/cymbal_check.py` reproduces it:

| voice | 354 Hz | 707 | 1414 | 2828 | 5657 |
|---|---|---|---|---|---|
| crash 1 (17"+18") | 8.7 | 5.5 | 7.8 | 10.9 | 17.0 |
| crash 2 (20"+13") | 6.9 | 9.7 | 7.3 | 12.2 | 20.3 |
| chinese | 2.3 | 6.6 | 9.8 | 16.1 | 20.8 |
| splash | -- | -- | 19.7 | 26.3 | 35.4 |
| ride | 4.2 | 3.3 | 3.6 | 14.2 | 21.9 |
| ride bell | 6.0 | 8.5 | 6.2 | 22.0 | 26.1 |

Fitted as `rate(f) = floor + k*log2(f/peak)^2` that gives, for crash 1, peak 815
floor 6.33 k 1.39 at 0.49 dB/s rms -- against a shipped 2000 / 20 / 8, three to
fourteen times too fast, with its slowest decay at 2 kHz where the measurement
says the decay is still falling toward the bass. **No hi-hat band rings long
enough to fit a slope to**, so they could not be fitted at all.

### Why it was reverted, which is the useful part

**DECAY AND `mode_gains` ARE ONE FIT, NOT TWO.** The `mode_gains` tables are
measured amplitudes fitted with the OLD decay in place. Changing the decay alone
moved the attack spectrum, which is the half you hear:

| band | reference | before | after | after - ref |
|---|---|---|---|---|
| 250-500 | -10.4 | -18.3 | -11.1 | -0.6 |
| 500-1000 | -15.7 | -16.9 | -11.4 | **+4.2** |
| 1000-2000 | -12.1 | -6.9 | -3.9 | **+8.2** |
| 2000-4000 | -4.1 | -6.0 | -7.3 | -3.1 |
| 4000-8000 | -6.2 | -6.0 | -8.9 | -2.7 |
| 8000-14000 | -7.5 | -5.8 | -9.0 | -1.5 |

Band rms over the attack went 4.03 dB to 4.18: the change improved the SETTLED
trajectory and made the ATTACK worse, and a crash is the 2-14 kHz bands. Ben, by
ear, immediately: *"They all now sound weirdly dark. Like they lost half their
crash."* The old too-fast decay had been masking a low-mid amplitude excess;
removing the mask left the excess standing.

**Re-fitting `mode_gains` against the new decay converges for the crashes and
DIVERGES for the rest.** Damped per-band iteration, four passes, band rms:

| voice | before | after |
|---|---|---|
| Crash 1 | 4.18 | **0.20** |
| Crash 2 | 5.69 | **0.81** |
| Chinese | 8.97 | 3.19 |
| Splash | 5.92 | *7.28* |
| Ride | 9.63 | *17.41* |
| Ride bell | 8.24 | *11.32* |

Two voices land far better than they ever have; three get worse. A method that
improves a third of a family and damages half of it is not a fit, so the whole
decay change was reverted and the cymbals are back where they were.

**What the next attempt needs:** fit `mode_gains` and the ring law TOGETHER
rather than in sequence, against BOTH windows rather than one, and find out why
per-band iteration runs away on the ride and the splash before trusting it
anywhere. The measured curve above is the target and does not need remeasuring.

**And the lesson, which is the one this repo keeps relearning:** the change was
validated on the settled spectrum, where it was a clear win, and not on the
attack, where it was a loss. Half a validation is how a fit comes to fit the
measurement instead of the instrument.

---

## The cuica: the one voice where the MECHANISM was wrong

From the coverage audit, ten patches were being played by a voice of the wrong
physical kind. Most are the wrong size or the wrong family. The cuica was the
worst of them, because nothing about a struck membrane is true of it.

**Sources.** The Wikipedia article and the summary literature on friction drums,
plus the standard acoustics line, which is the one that matters: *"Rubbing the
bamboo rod gives a primitive saw-toothed excitation, similar to a bowed violin
string, which is connected to the center of a membrane which modifies and
radiates the sound"*, and *"the pitch is increased or decreased by changing the
pressure on the head"*. A thin stick is tied to the INSIDE CENTRE of the head
and stroked with a damp cloth; stick-slip drives the stick and the stick drives
the membrane.

Three consequences, and the old voice had none of them.

### It is bowed, not struck

A cuica sustains while it is rubbed, so `decay_db` and `harmonic_decay_db` are
zero exactly as they are on a bowed string and an organ pipe, and
`tonal_dampening` is 1.0 because a sawtooth's harmonics go as 1/n. The voice was
`MembraneDrumProperties` -- a struck onset with a fast decay -- which models the
wrong thing entirely. It is also NOT placed under `PercussionProperties`, whose
docstring reads "struck onset... fast decay"; the attributes that base would
have supplied are written out on the class instead, because inheriting them
would mean claiming it is struck in order to borrow defaults.

### Driven at the centre, so most of the drum cannot speak

**Every membrane mode with an angular node has a node at the centre of the
head.** (1,1), (2,1), (3,1) and the rest are exactly where the stick is tied, so
a centre drive cannot excite any of them. What is left is the axisymmetric
series alone, `j(0,n)/j(0,1)`:

    1.000   2.295   3.598   4.903   6.209

`MembraneDrumProperties` hands out the full Bessel set -- twelve modes including
1.593 and 2.136 -- and on a cuica none of those exist. This is the sharpest of
the three claims and it costs nothing to honour.

### And because it is driven, it mode-locks

The same argument the organ pipes make: a nonlinearly driven oscillator pulls
its passive resonances into one exactly periodic waveform, so the STEADY tone is
harmonic and the passive inharmonicity is an ONSET TRANSIENT. So this voice has
no `mode_ratios` -- that would assert the passive modes sound forever -- and
carries the departure in `mode_lock_spread` instead.

**The engine's existing lock law fits a Bessel series almost exactly.** Fitting
`spread * x/(1+x)`, `x = (h/knee)^2` to those five axisymmetric ratios gives
`mode_lock_spread = 0.2748`, `mode_lock_knee = 1.8522`, reproducing them as
2.296, 3.597, 4.905, 6.208 -- **rms 0.0004**. That was a pleasant surprise: the
law was written for the mild inharmonicity of a pipe's open-end correction and
it happens to describe a membrane's wildly inharmonic modes just as well.

Measured on the render, the mute cuica's onset partials sit at ratios
1 : 2.204 : 3.438 -- partway to the membrane's 2.295 : 3.598, as they should be
in a window straddling a 60 ms lock -- and its settled partials at
1 : 2.010 : 3.022. **The squeak at the onset of a cuica is a membrane becoming a
harmonic tone**, and that is most of what makes it recognisable.

### The pitch is the other hand

A finger pressed near the centre raises the head tension, and a membrane's pitch
goes as sqrt(T) -- which is `tension_bend` exactly. On every other voice in this
file that bend is a small attack transient; on a cuica it IS the instrument, so
it is an order of magnitude larger (~155 cents against a piano's 14) and
`tension_bend_slope` is zero, because the glide is a finger and not a register.

**Which way each note glides is a CHOICE, not a measurement.** GM gives two
notes and says nothing about what they do, so they are set to glide in opposite
directions -- the mute rises into pitch, the open falls away from it -- which is
what makes an alternating 78/79 figure sound like the instrument talking. Any
real player does both on either note.

### What it is not

**NO REFERENCE.** Iowa has no cuica and no friction drum of any kind, so this
sits at 2 in `coverage.md`: the mechanism above is measured physics taken from
the literature, and every number below it is asserted. In particular the two
pitches (420 Hz mute, 260 Hz open, against 340/300 before) and the glide
magnitudes are choices. The stick-slip drive itself is modelled only by its
RESULT -- a sawtooth spectrum -- and not as a friction oscillator, so the voice
cannot squeal, break up or ride the way a real one does under a heavy hand.

`examples/cymbals.py --cuica` renders the talking figure.

---

## The clavinet: the tangent is the termination

GM 7 was played by `HarpsichordProperties`, which is plucked, wooden, and --
with `pickup_points = ()` and `pickup_velocity = False` -- carries no magnet at
all. A clavinet is a struck steel string read by magnetic pickups, so almost
nothing about that voice was true of it. The last of the piano family's
category errors.

**Source.** Gabrielli, Valimaki et al., *A digital waveguide-based approach for
Clavinet modeling and synthesis*, EURASIP JASP 2013, plus the standard
description: **"the rubber tip strikes the string and traps it against a metal
stud, or anvil, for the duration of the note, splitting the string into speaking
and nonspeaking parts, with the motion of the former transduced by the
pickups."**

### The strike point IS the string's end, and that is the buzz

A piano is struck at about 1/7 of its speaking length and a harpsichord plucked
at 0.115: both get a comb with a NOTCH inside the audible range, placed to kill
the sour 7th. A clavinet is excited essentially AT THE END of the length it goes
on to sound, so `|sin(n*pi*p)|` with p small **rises** with harmonic number
instead of notching, and its first null lands at the 29th partial against a
piano's 7th. A weak fundamental and strong upper partials.

Measured on the render at C4, energy above the fundamental: **+10.5 dB for the
clavinet against +7.0 for the harpsichord**, with the clavinet's peak at the 3rd
partial and the harpsichord's at the 2nd. And a hard tangent does not fill its
notch the way piano felt does, so `strike_fills_with_force` is False -- the same
argument the dulcimer's wooden hammer gets from the other direction.

### The pickup fraction moves with pitch, which no other voice here does

The pickups sit at the bridge end at a FIXED PHYSICAL POSITION while the
speaking length is set per note by where that note's tangent lands. On a guitar
the nut is fixed, so a pickup stays at one fraction of the string for every
note; on a clavinet the same magnet is a fifth of the way up a treble string and
a fifteenth of the way up a bass one. Measured on the class, the fraction runs
**0.084 at C2 to 0.193 at C6**, moving the comb's first null from the 13th
partial down to the 5th. `pickup_points` is therefore computed per instance in
`__init__`, the way the Rhodes computes its tonebar ratio.

**This is the voice the electric guitar's pickup machinery was actually built
for.** The Rhodes could not use it -- a tine has one mode and no standing wave
to sample, which was the correction that work turned up -- but a clavinet is a
plain string with a magnet under it, which is exactly what `|sin(n*pi*q)|`
describes, and `pickup_velocity`'s +6 dB/octave is the same magnet.

### The click is the machine

The paper again: **"the mechanical noise generated by the key, its rebound, and
the tangent hitting the anvil masked the striking portion of the tone nearly
entirely."** So the attack is carried as 6 ms of broadband noise rising with
velocity (`strike_noise_slope`), not as a string transient.

### What is asserted

**NO REFERENCE.** There is no clavinet in the Iowa set and no usable isolated
recording of one: the CC0 material on Freesound is loops, riffs and synth
imitations. So this sits at 2 in `coverage.md` alongside the Rhodes -- mechanism
from the literature, numbers estimated. The two that matter most are the string
scale (0.22 m at C4 falling as `f^-0.30`, giving 0.38 m at the bottom of the
compass and 0.13 m at the top) and the pickup's 28 mm from the bridge, since
between them they set where every comb null lands. The stiffness, 1.1e-04, is
estimated as more than a harpsichord's long thin wire and far less than a
piano's wound bass.

### The rockers, on CC1

Six switches sit left of a D6's keyboard, and they are not one control but two.
**"Brilliant and Treble activate a high-pass filter, while Medium and Soft
activate a low-pass filter"**; the remaining pair, AB/CD, select which of the two
pickups is heard -- one above the strings near the bridge, one below.

**Only the four tone rockers are on the wheel, and the split is not arbitrary.**
A filter is a function of FREQUENCY, so it scales partials that already exist
and one function serves both paths: `clav_tone_gain(hz, setting)` is called by
the offline pass over the finished table and by the live per-block gain. A
PICKUP SELECTION is a function of HARMONIC NUMBER -- it moves the comb -- which
is a different amplitude for every partial of every note and therefore a
property of the template. It cannot be applied to a note already sounding
without rebuilding it, so it wants a bank axis and is left for a third pass.

CC1 sweeps the four darkest to brightest with all four up in the middle, which
is the panel's own vocabulary:

| CC1 | rocker | | rendered attack centroid |
|---|---|---|---|
| 0 | soft | low-pass 1.2 kHz | 673 Hz |
| 32 | medium | low-pass 3 kHz | 855 Hz |
| 64 | flat | all four up | 1049 Hz |
| 96 | treble | high-pass 400 Hz | 1314 Hz |
| 127 | brilliant | high-pass 900 Hz | 1623 Hz |

**The corners are estimated. The names are the instrument's.**

Live it runs 656, 862, 1082, 1397 and 1732 Hz -- within 7% of the offline pass,
which is the agreement worth having, since the two take different routes. And
because it is a preamp filter it **reaches notes already ringing**: flipping the
wheel to "soft" mid-note takes a sounding C3 from 860 Hz to 377. That is what a
rocker does; the filter is downstream of every vibrating string. Unlike the
tremolo it needs no work in the callback, because a fixed filter only changes
when the wheel does.

A file with no CC1 gets the panel at rest. `TUNING_CLAV` overrides it for
renders of material that carries no modulation.

**A probe failure, and the same one as last time in a new costume.** The first
live reading had the ladder BACKWARDS -- brilliant darkest, soft brightest --
and showed the wheel doing nothing to a ringing note. The slab was right all
along: the probe stamped every note at absolute sample 0 while the stream clock
advanced, so each reading after the first played from the middle of its own
envelope. One fresh instrument per reading, or `apply(lv.n)`, and the ladder
came out monotonic. Both times this session the wrong-window mistake has looked
exactly like a real inversion in the model.

**A probe failure worth recording**, because it nearly sent this voice the wrong
way: the first spectral comparison put the clavinet DARKER than the harpsichord
and showed a comb null at the 5th partial where the class says the 8th. Both
were the probe. The test MIDI's note-offs accumulate into the deltas, so its
four notes start at 0, 0.96, 1.92 and 2.88 s rather than on the beat, and the
window was reading C3's even harmonics as C4's. Find the onsets; do not assume
them from the score.

---

## The electric grand: what can be derived, and what must not be

GM 2 was the acoustic grand -- literally the same class object, not even a
subclass. A Yamaha CP-70 has "the same frame, action and frame construction as
an acoustic piano, but with SHORTER STRINGS", and "pick-ups on each note
INSTEAD OF A SOUNDBOARD". There is no recording of one here, so everything
below is derived or it is nothing.

### The stretch, and a prediction with a knee in it

For a stiff string `B = pi^2 Q d^2 / (64 rho L^4 f0^2)`, so at fixed pitch and
gauge **B goes as 1/L^4** and a string shortened by k has k^4 the
inharmonicity. The inherited voice carries a **Steinway B** fit: a seven-foot
concert grand, the longest strings in the catalogue and the least inharmonic
thing it could have been handed.

The shape of the departure is derivable too. At constant stress `f0*L` is
fixed, so a piano's speaking length follows `L = C/f` **until the case runs
out** -- and two pianos of different size can only differ where the shorter one
BINDS. With `C = 162 m*Hz` (a grand's C4 string is about 0.62 m), a 211 cm
Steinway binds below 83 Hz and a CP-70's 120 cm case below 154:

| band | ratio | B multiplier |
|---|---|---|
| above 154 Hz | 1.00 | **1.0 -- identical** |
| 83 to 154 Hz | climbing | rises as f^-4 |
| below 83 Hz | 1.857 | **11.9, and capped** |

**That is a falsifiable prediction rather than a tilt:** an electric grand's
stretch departs from a concert grand's ONLY in the bottom octave and a half,
and is identical above D#3. It reaches B = 3.8e-03 in the bass, which is where
the literature puts a spinet -- the derivation lands there without having been
aimed. Rendered, E1's 8th partial sits **+50 cents** sharp against the acoustic
grand's +2.

### The soundboard, taken apart term by term

The inherited `soundboard_gain` is three things and a CP-70 has none of them:

- a body resonance at 240 Hz -- **gone**, there is no body;
- a sub-bass term `1/(1+(35/f)^2)`, which is explicitly a BOARD'S POOR
  RADIATION at low frequency -- **gone**, a piezo has no such loss. This is the
  one that matters: the inherited voice was throwing away bass the instrument
  keeps, which is backwards for something whose signature is a thick clean
  bottom that engineers cut rather than lift. Measured on the class, 35 Hz
  against 400 Hz is **+0.2 dB here where the board gives -8.3**;
- a top roll-off at 2.6 kHz -- **moved to 4 kHz**, because a pickup reaches
  higher than a board radiates. The direction is defensible; the number is an
  estimate and the only one in this voice with nothing behind it.

### The derivation that was NOT spent, which is the point

The transverse force a string exerts on its bridge is T times the slope there,
so for mode n it goes as `n*A_n`: **+6 dB per octave**, certain, and the same
tilt a magnetic pickup gets by a different route.

**It is implemented and set to zero.** The `A_n` it would multiply is this
engine's generic `1/n^1.1` string tilt, not a measured displacement spectrum,
and stacking a full octave-doubling on top of it measured **+11 dB across
1-4 kHz and +15 at the top** against the acoustic grand. A real CP-70 is thick
and clean, not brilliant. The physics that rescues the derivation is that a
piezo sits under a MASSIVE WOODEN BRIDGE whose mechanical mobility falls with
frequency -- real, and not quantifiable from anything here. So
`bridge_force_power = 0.0`, with the law recorded on the class: setting it to
1.0 and then choosing a corner that cancels it again would be fitting a free
parameter to a target that does not exist.

This is the same discipline the cymbal fit failed: a factor that looks derivable
in isolation is not, if the thing it multiplies was fitted jointly with
something else.

### Two incidental findings

**Level is not linear in `initial_gain` for a piano.** Measured across a decade,
it runs at **38.8 dB per decade where a plain gain gives 20** -- the phantom
partials are sum-tones whose amplitude goes as the product of two partials'
amplitudes, so they scale as the SQUARE of the voice gain. Inheriting the
acoustic grand's 0.0718 leaves this 3.5 dB under one; solved, it wants 0.0885.

**And a probe failure with a new cause: stale bytecode.** A calibration loop
wrote `initial_gain`, re-rendered, and got IDENTICAL results for two different
values. Python caches `.pyc` on (mtime, size), and the loop was writing
same-length values inside one second, so the subprocess reused stale bytecode.
Clear `__pycache__` and space the writes when sweeping a constant by rewriting
source.

**Not verified:** how many strings per note a CP-70 uses. The unison behaviour
is inherited from the acoustic grand unchanged and unchecked.

---

## The honky-tonk, which needed no new mechanism at all

GM 3 was the acoustic grand unchanged. A honky-tonk is that piano badly tuned,
and the grand ALREADY models a real unison properly: one string at pitch and two
more mistuned around it, drawn per note from `string_detune_range`, straddling
so the note itself stays in tune. So the whole voice is one number.

| | range | beating at A4 |
|---|---|---|
| grand | 0.5 to 1.7 cents | 0.43 Hz -- a shimmer |
| honky-tonk | 8 to 20 cents | 2.0 to 5.1 Hz -- a wobble |

**THE BEAT RATE IS NOT SET ANYWHERE.** Two strings a fixed number of CENTS
apart beat at a rate proportional to pitch, so one range gives 0.75 Hz at C2 and
11.5 Hz at C6 -- slow and fat in the bass, fast and nervous at the top, which is
how a neglected piano sounds. Measured on the render, A4 went from 0.67 Hz at
1.0 dB to **4.00 Hz at 4.1 dB**, against a predicted 4.14.

Two more things came for free. **The bass does not wobble**, because the
stringing is a single wound monochord at the bottom and there is no second
string to mistune -- which is true of the real instrument too. And **the note
stays in tune**: the main string is at pitch and carries the gain, so the
gain-weighted centre sits 1.8 cents off even with strings at -16 and +9.

### CC1 is how far out of tune, and the axis already existed

Ben: *"Maybe the mod wheel can control how detuned it is. With a default in the
middle?"* It fits better than it had any right to. The live template cache has a
third axis, built for the Leslie half-moon, and that axis is **literally "the
CC1 value to build this template with"** -- `_raw_template` injects a CC1
message into the one-note MIDI it synthesises. So a wheel can drive a
template-level parameter with no new machinery:

    CC1   0   A4 unison  [415.0]                  one string, just tuned
    CC1  64   A4 unison  [411.0, 415.0, 419.7]    -16.9 / +19.3 cents
    CC1 127   A4 unison  [407.0, 415.0, 424.3]    -33.5 / +38.3 cents

64 is the default AND what a file with no CC1 gets, so the corpus needs no
edits. The three positions are pre-warmed, because a miss on this axis would be
a dropped note rather than a wrong sound.

**AND IT CANNOT REACH A RINGING NOTE, unlike the clavinet's rockers.** A
filter is a function of frequency and scales partials that already exist; a
detune is IN those partials' frequencies, so it is a different template. Notes
keep the tuning they were struck with -- which is what a piano does, since
nobody retunes a ringing string.

### Two probe failures, both the same shape

**The wheel silently did nothing at first.** The CC1 was read in the
per-channel block that runs AFTER the note loop has already built every note,
so the scale was always its default. The three templates were distinct cache
keys with identical contents, which is exactly what that looks like. Resolve a
per-note parameter where it is USED, not where the other channel settings are
gathered.

**And the wobble measured 58 dB deep on every position, identically.** That was
an envelope probe over a sustained chord whose cubic detrend could not remove
the decay, so it measured the note dying rather than the strings beating. The
clean measurement is the one on a single held note with a narrow band around one
partial. A chord is not a good place to measure a beat.

### Not done

`string_gain = (0.28, 0.20)` is inherited, so the extras sit under the main
string and the unison swings about 9 dB rather than nulling. Raising it would
make the wobble DEEPER as well as wider. That is a separate knob with a separate
argument and it was left alone.

---

## The bright acoustic piano, and what GM actually specifies

Ben asked what the precedent is -- whether GM 1 means a console piano or a
different kind of instrument. Worth answering before building anything, and the
answer is mostly negative.

**GM specifies nothing.** The Level 1 list (1991) is a naming convention so
files play recognisably across modules; it names no instrument, no timbre and
no reference for ANY program, including program 0. A claim surfaced in search
that Bright Acoustic is "based on a Yamaha C7" -- the GM Level 2 spec page says
no such thing and it is not repeated here. Roland's SC-55 manual, the de facto
reference implementation, is a scanned PDF with no text layer, so its patch
naming could not be checked from a primary source either.

**What GM does say is in Level 2's bank variations**, and it is informative:
"Wide Acoustic Grand" (bank 1) and "Dark Acoustic Grand" (bank 2) are
variations OF program 1. So brightness and darkness are, in GM's own
vocabulary, a TIMBRAL AXIS ON ONE INSTRUMENT. Bright sits at its own program
number only because the 1991 numbering was frozen before those banks existed.

**And it is certainly not an upright.** Nothing in GM suggests one; there is no
upright anywhere in the 128.

### A voicing is a hammer, and both halves were already modelled

Needling felt softens it and lacquer hardens it. That changes two things:

- **CONTACT TIME, which IS the hammer's low-pass.** `hammer_corner_hz` is that
  corner and already shortens with force, which is why the grand brightens when
  it is dug into. Hard felt starts shorter: 0.14 ms against 0.25.
- **HOW MUCH THE FELT SPREADS.** A soft hammer flattens under force, widening
  its contact patch and filling the strike comb's notch -- which is why a
  piano's sour 7th disappears at ff. A hard one barely spreads and keeps the
  notch at every dynamic. This was a BOOLEAN, `strike_fills_with_force`, which
  is the felt-versus-quill distinction; it is now `strike_fill_fraction` as
  well, defaulting to 1.0. Verified: exactly one class in the whole set departs
  from that default.

### The hammer alone could not be heard, and that was the finding

Built as a pure voicing it measured +2.5 dB above 2 kHz at pp, falling to +1.7
at ff. Ben, on the render: *"I can't hear a difference between grand and
bright."*

He was right, and the ceiling says he had to be. Removing the hammer's low-pass
**entirely** buys only **+4.0 dB** above the 8th partial, so +2.4 was already
60% of the theoretical maximum and no amount of voicing could have been
audible. The board owns the top:

| | 1 kHz | 2 kHz | 4 kHz | 8 kHz |
|---|---|---|---|---|
| soundboard | -2.6 dB | -6.4 | **-12.1** | -19.6 |
| hammer at 4 kHz | -0.6 | -2.3 | **-6.9** | -15.3 |

**AND THE REASON THE BOARD WAS LEFT ALONE WAS WRONG.** It was left alone on the
grounds that `board_high_hz` had been fitted with the rest of the piano, so
moving it would be changing half of a joint fit -- the cymbal ring decay's
mistake. It had not been fitted. This file's own *"Still assertions after all
this"* list includes **"soundboard formants (not attempted)"**, and those
parameters carry no measurement. The lesson was applied to something that is
not a joint fit, and it cost a voice nobody could hear.

### So the board moves too, and it stops being only a voicing

`board_high_hz` 2600 -> 5500 and `board_body_gain` 0.6 -> 0.30. A stiffer,
thinner, differently braced board radiates higher and carries less wooden
warmth, and that is what actually separates the makers whose names get attached
to the word "bright". Both sides are assertions, so there is no fit to break --
but a different board is a different INSTRUMENT, so the class should be read as
"a brighter piano" rather than "the same piano voiced", and it says so.

Rendered on a chord, as a share of the whole note:

| | 80-400 Hz | 400-2k | 2k-6k | 6k-14k |
|---|---|---|---|---|
| grand | -1.6 dB | -5.2 | -33.7 | -61.0 |
| bright | -1.9 | -4.5 | **-27.9** | **-47.6** |

+7 dB at 2-6 kHz and +14 at 6-14, with the bass essentially untouched.
Rebalanced afterwards, because cutting the warmth took 2.5 dB of level with it:
`initial_gain` 0.0932, solved on the render at 21.8 dB per decade of that knob
rather than 20 -- the phantom partials being sum-tones that scale as its square,
the same super-linearity the CP-70 turned up.

**The velocity character survives the change**, which is the part worth having:
+7.7 dB at pp against +6.7 at ff, and the bright piano opens 1.0 dB from pp to
ff where the grand opens 2.0. A hard hammer is already bright and has less to
open into -- the tone stops being something the hand controls.

### An open item this turned up, larger than the voice itself

GM 0's two halves describe different pianos. Ben: *"I used my piano for where
the wound strings and 3 string note started. I don't know Steinway B, but I
found an empirical model of the Steinway B, and used that for inharmonicity,
since I didn't measure my upright grand."*

So the stringing breaks are a measured upright's and the inharmonicity is a
borrowed 211 cm concert grand's. The `L^4` argument derived for the CP-70
applies unchanged: an upright's longest string is about 1.15 m against a
Steinway B's 1.95, so **if GM 0 is meant to be that upright its bass is
under-stretched by up to 8.3x** -- A0's 8th partial would move from +17 cents to
+138. Above about 141 Hz the two agree, because above the knee both use a string
of the same length.

NOT ACTED ON. It needs a decision that is not a measurement: whether GM 0 is a
concert grand that borrowed an upright's string breaks, or an upright wearing a
concert grand's stretch. Either way one half is wrong, and the machinery to fix
it exists.
