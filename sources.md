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

### Open, and measured: the voice is too dull

Comparing 2–8 kHz content against the note's own peak:

    our render     -21.8 dB
    VCSL C3         -6.0 dB
    VCSL C4         -7.0 dB

**About 15 dB short in the brilliance region.** A room recording should have LESS
high frequency than an anechoic model, not more, so the gap is real and if
anything understated — though a sample library may have been brightened, which
this cannot rule out. The knob is `tonal_dampening = 1.55`, and moving it changes
the character of a voice Ben has tuned by ear, so it is recorded here and left
alone rather than adjusted on one measurement.
