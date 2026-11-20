# Openly licensed replacements for the restricted keyboard and bell fits

Researched 2026-11-20. Every licence below was read on the source's own page (Freesound sound page, Wikimedia Commons file page or API extmetadata, GitHub README, or the author's site). The quotes are copied from those pages. Freesound sets the licence **per sound**, so before fitting from a pack, check the licence of every file you use (one sound per pack was checked here).

Acceptable: CC0, public domain, "copyrighted free use", CC BY (any version), and CC BY-SA (marked **SA** below). Rejected sources and the reasons are listed at the end.

---

## 1. Wurlitzer 200A (replacing Pianobook BaltiWurli)

**1a. Greg Sullivan, "Wurlitzer EP200" (the instrument is an EP203W, from the 200 series): best for velocity layers**
- Author's page: http://www.sullivang.net/home. Licence there: *"Licensing (updated 21-Oct-2026): All these instruments I host here now have Creative Commons Attribution 4.0 International licensing. (CC BY 4.0)"*.
- SFZ/FLAC copy: https://github.com/sfzinstruments/GregSullivan.E-Pianos. Its README says *"This work is licensed under a Creative Commons Attribution 3.0 Unported License"* and *"with the author permission with the request for attribution"*. The Discord GM bank's copy of the CP80 instead says "CC0", so the sources disagree. Go by the author's own page (CC BY 4.0) and credit Greg Sullivan.
- Instrument page: http://www.sullivang.net/wurlitzer-ep203w-electric-piano-for-gigasampler-gigastudio. It says *"Most samples have been recorded at 4 different velocities (pp, mp, f, and ff)"*. Version 1.1 dates from 16 May 1999, and the uncompressed set is 8.7 MB.
- Contents (from the SFZ and the repo tree): 42 FLAC files covering A1–A6 (MIDI 33–96), about every 4–6 semitones, in pp/mp/f/ff layers. Some layers are missing; for example, the top pp uses the mp files. Files I probed are 44.1 kHz, 16-bit mono, and last 2.2 s (Db4 f) and 5.6 s (A1 ff). The tails look cut short. The recording chain (DI or mic) is not stated.
- Fitness: good for attack spectra, the pickup's bark, and how the spectrum changes with velocity. It is weak for ring decay (short files), and the chain is unknown. It is the only open Wurlitzer set I found with several velocities.

**1b. OldBassMan, "Wurlitzer 200a" pack on Freesound (13 sounds): best for a DI-like tone**
- Pack: https://freesound.org/people/OldBassMan/packs/5726/. Sound checked: https://freesound.org/people/OldBassMan/sounds/88000/, licence **"Attribution 4.0"**.
- Description: *"My Wurlitzer 200a Sampled thru a Lundal Transformer and a real Tube Preamp"* and *"not bad tuned (You still can retune 3 or 4 Samples a little bit)"*.
- Contents: single notes D3, F#3, D4, F#4, A#4, D5, F#5, A#5, D6, F#6, A#6, D7, plus one more (12 listed, 13 in the facet count). That is roughly every major third over D3–D7. Files are 48 kHz, 24-bit mono WAV of about 7 s each. There is one velocity.
- Fitness: good for the line-level tone of a 200A and its decay over about 7 s. The transformer and tube preamp colour the sound mildly. There is only one dynamic, so velocity laws would have to come from 1a.

Recommendation: fit tone and decay to 1b and the velocity deltas to 1a. Nothing with a clean DI and several velocities exists under an open licence. Fallback reference: Pfeifle & Münster, "Tone Production of the Wurlitzer and Rhodes E-Pianos" (Springer, *Current Research in Systematic Musicology* vol. 4, DOI 10.1007/978-3-319-47292-8_3), which has measurements of the reed and the electrostatic pickup. I did not confirm that it is open access.

## 2. Yamaha CP-70/CP-80 (replacing Pianobook David's CP70)

**2a. Greg Sullivan, "Yamaha CP80 Electric Grand" v1.3: the only acceptable source found**
- Licence: the same author's page and statement as 1a, CC BY 4.0, *"All these instruments I host here now have Creative Commons Attribution 4.0 International licensing."* (http://www.sullivang.net/home). The GitHub copy says CC BY 3.0. Instrument page: http://www.sullivang.net/yamaha-cp80-electric-grand-instrument-for-gigasamplergigastudio.
- Contents: a CP80 the author rented over Christmas 1998, with *"Tone controls set to neutral"* and four layers (pp/mp/f/ff). The GitHub copy (https://github.com/sfzinstruments/GregSullivan.E-Pianos/tree/master/CP80) has 81 FLAC files, D#1–C#7, about every 3–4 semitones, with some layers missing. Files I probed are 44.1 kHz, 16-bit mono: D3 ff runs 22.8 s and C4 mp runs 7.0 s. The D3 ff envelope swells and dips over about 8 s, which looks like natural beating between the unison strings rather than a loop. The 7 Hz tremolo was a Gigastudio setting, not something in the audio. The pickup or mic chain is not stated.
- Fitness: usable for the CP's string partials, unison beating and how the spectrum changes with velocity, over a long ring. Its main weaknesses are the age of the recording (1998, 16-bit) and the unknown chain. It is a CP-80, not a CP-70, but both use the same piezo-pickup string design.
- No CC0/CC BY CP-70 recording exists that I could find. The search covered Freesound, Commons, Zenodo, sfzinstruments, FreePats and VCSL.

## 3. Hammered dulcimer (replacing Pianobook Lite Hammered Dulcimer)

Nothing good exists. The best available:

**3a. iternetcone, "Multi-sampled Hammered Dulcimer" (Freesound, 15 sounds)**
- Pack: https://freesound.org/people/iternetcone/packs/19445/. Sound checked: https://freesound.org/people/iternetcone/sounds/342925/, licence **"Attribution 4.0"**. The description reads *"I Sampled my Dulcimer."*
- Contents: single notes D, E, F, F#, G, A, High C and High D, plus C, C# and D scales and one glissando. Files are 48 kHz, 16-bit stereo; the checked file is 8.1 s. The range looks like about an octave and a half, with one dynamic and no documentation.
- Fitness: limited. It gives the ring, the two-bridge course structure and the knock for a handful of notes. It cannot give a full range or any velocity behaviour.

**3b. batchku, "India Santoor" (Freesound, 12–15 sounds), as a related instrument**
- Sound: https://freesound.org/people/batchku/sounds/10677/, licence **"Creative Commons 0"**. Description: *"recordings of an indian santoor, especially rolls plaid on single notes; pitch is indicated in file name, recorded using multiple K&K contact microphones"*.
- Contents: rolls (tremolo), not single strikes, on 12 pitches from A#3 to A#5. Files are 44.1 kHz, 24-bit stereo, about 11 s, from contact pickups.
- Fitness: low for the knock and attack. The ends of the rolls ring out and could give per-course decay and detuning on a related instrument.

Fallback: keep the existing model structure (free string bank, two bridges, fifth partner) and refit it only to 3a. Or record a dulcimer, since a single session would beat anything published. Commons, VCSL, VSCO, FreePats, sfzinstruments (its GM 16 Dulcimer is a dummy sine) and Zenodo have nothing.

## 4. Harpsichord registers (replacing Pianobook Harpsimachord)

**4a. VCSL "Harpsichord, English" (a Zuckermann kit): has a separate LUTE stop. CC0**
- https://github.com/sgossner/VCSL. Licence: *"This collection is under a Creative Commons 0 license."* *"Essentially it's Public Domain- you can do whatever you want with these sounds."*
- Contents: `Chordophones/Zithers/Harpsichord, English/Sustains/Lute/ZuckermannKitHarpsi_Lute_Sus_*` (28 files, A#0–E5 in VCSL note names), with matching `Normal` sustains and `Lute` and `Normal` releases. Files are 24-bit WAV.
- Fitness: good. It is a real lute-stop row (the plucking point near the nut) with a same-instrument Normal row for comparison, so the lute stop can be fitted as a difference from the 8′.

**4b. VCSL "Harpsichord, Flemish": two rows, `High` and `Low` (HarpsiRH_High_Far_* and HarpsiRH_Low_Far_*). CC0, same licence**
- High covers F#1–C6 (26 files) and Low covers F#0–C5 (28 files), with releases for both. Files are 24-bit stereo, 44.1 kHz, about 5–6 s in the middle.
- I measured High C#4 against Low C4. Both sound at the same octave. In both, the file named "C4" sounds at 523 Hz, an octave above standard MIDI naming: VCSL appears to use the C3 = middle C convention, and this applies to both rows. Neither is therefore a 4′. They are most likely the two 8′ choirs or the two manuals, but VCSL does not document this. If they are distinct 8′ choirs, this is the open source for the upper (second) 8′. Confirm by comparing the plucking-point comb notches of the two rows.
- The French, Italian and "Unk" VCSL harpsichords each have a single row (`Harpsi2_Normal`, `stop1`, `Harpsi4_Sus_Main`).

**4′ register: no openly licensed recording exists.** VSCO 2 CE has no harpsichord. SSO's "4′" is under CC Sampling Plus 1.0 and its sources are unclear. Fallback: build the 4′ as a separately scaled string set from the physics (half the length, its own plucking ratio), checked against the 8′ fits. Kram's IMSLP comparison of sampled harpsichords lists only commercial 8′+4′ sets.

## 5. Hohner Clavinet D6 (replacing the Aalto ICMC 2011 examples)

**5a. Markus Ruffing, "Hohner Clavinet D6.ogg" (Wikimedia Commons): the only acceptable source found**
- https://commons.wikimedia.org/wiki/File:Hohner_Clavinet_D6.ogg. Licence: *"The copyright holder of this work allows anyone to use it **for any purpose**"* (category "Copyrighted free use"). The page credits *"Aufgenommen und gespielt von Markus Ruffing."*
- Contents: *"Hohner Clavinet D6 gespielt mit unterschiedlichen Pickup-Einstellungen"* ("played with different pickup settings"). It is 101 s of playing, not isolated notes, as Ogg Vorbis at about 96 kbps, 44.1 kHz stereo. The recording chain is not stated, though it is probably DI.
- Fitness: poor for per-note fitting because it is lossy and musical. It is useful for checking pickup-selector settings (neck/bridge, combined, out of phase) by ear and with long-term spectra, and for isolated note tails where they occur.

No open single-note D6 set exists. Freesound has nothing real. The "Keyboard Legacy D6" freebie on Payhip states no licence, and the Polyphone "clavinet.sf2" is a 21 kB E-mu sample whose provenance is unclear. Fallback: keep the DAFx-12/ICMC geometry, which is published physics and not audio, and fit to 5a only for pickup-combination timbre. Otherwise record or borrow a D6. You could also ask Aalto (Välimäki's group) to put their examples under CC BY.

## 6. Large church/tower bell (replacing Pianobook St. Kathrin's bell)

**6a. "ND G1 Emmanuel.ogg": the bourdon of Notre-Dame de Paris (about 13 t). CC0**
- https://commons.wikimedia.org/wiki/File:ND_G1_Emmanuel.ogg. Licence: *"This file is made available under the Creative Commons CC0 1.0 Universal Public Domain Dedication"*.
- Description: *"Tonaufnahme der tontiefsten Glocke der Nôtre-Dame de Paris vor dem Feuer vom 15. April 2019"* ("recording of the lowest bell of Notre-Dame before the fire"). It is 189 s of Ogg Vorbis at 160 kbps, 44.1 kHz stereo, uploaded and normalised by Rongaman. The page does not say whether the bell is swung or hammered, where the mic was, or which device was used.
- Fitness: the best large bell with a clean licence, and long enough for hum and prime decays. It is lossy, and if the bell was swung the strikes overlap. Listen before fitting.

**6b. "Clopot 25T – Catedralei Mântuirii Neamului (București).wav": the 25-tonne bell of the People's Salvation Cathedral. CC BY-SA 4.0 (SA)**
- https://commons.wikimedia.org/wiki/File:Clopot_25T_-_Catedralei_M%C3%A2ntuirii_Neamului_(Bucure%C8%99ti).wav. Licence: *"This file is licensed under the Creative Commons Attribution-Share Alike 4.0 International license."* Author: MIHAIL, 25 Nov 2018.
- Contents: *"Sound is recorded with Canon Legria. Wav 24, PCM S24 LE, Stereo 44.1 KHz"*. 0:00–1:04 was recorded beside the bell and 1:04–3:09 below it. The file is 189 s and lossless.
- Fitness: the most suitable file for fitting: lossless, close, very large bell, two mic positions. Its weaknesses are a camcorder mic and probably swinging rather than hammer strikes. The licence is ShareAlike: confirm that shipping only fitted numbers raises no SA obligation, and attribute.

**6c. HMTSCCSound, "bec low bell solo.wav" (Bethesda Church, Saratoga Springs NY). CC0**
- https://freesound.org/people/HMTSCCSound/sounds/554655/. Licence: **"Creative Commons 0"**.
- Description: *"four-bell tower at Bethesda Church, Saratoga Springs NY USA – lowest bell rung once softly by rope."* *"Long tail fade to silence at the end."* *"SM58 up in the tower to Behringer USB interface to Audacity, trimmed and amplified."* WAV, 44.1 kHz, 16-bit stereo, 31.9 s.
- Fitness: an ideal recording (one strike, close mic, full ring-out, lossless), but the bell is probably far smaller than St. Kathrin's. Use it to check partial ratios and decays per partial, not size.

Also acceptable but weaker:
- Commons "Bourdon Marie (Notre-Dame de Paris) 1.ogg" and "2.ogg": CC BY-SA 3.0 (SA), NemesisIII. The new 6 t bell was recorded while on display in the nave in Feb 2013, so it is dry of the tower but has strong church echo. Each is about 25–29 s at 500 kbps Vorbis. https://commons.wikimedia.org/wiki/File:Bourdon_Marie_(Notre-Dame_de_Paris)_1.ogg
- Commons "Pummerin.ogg" (Vienna, about 20 t): **Public domain**, 14 s, 80 kbps. https://commons.wikimedia.org/wiki/File:Pummerin.ogg
- Commons "141225 MF Susanna solo.ogg" (Munich Frauenkirche tenor bell, about 8 t): CC BY-SA 4.0 (SA), a 586 s swinging solo. https://commons.wikimedia.org/wiki/File:141225_MF_Susanna_solo.ogg
- Freesound daytripper "Tollbell – 9 strikes.wav": **CC0**, a "Large bell with 9 strikes. 4 seconds between strikes; long tail. 24 bit wav, 44100". The bell is not named. https://freesound.org/people/daytripper/sounds/118851/
- Commons category "Audio files of church bells ringing 1 time" has 37 single hour-strikes, all CC BY-SA 4.0. They are small French village bells recorded at a distance, as Ogg.

Fallback for the physics: published bell partial tables (hum, prime, tierce, quint, nominal) from the bell-founding literature. Commons also has "Jonathan Harvey – Winchester Cathedral bell spectrum.mid" (CC BY-SA 3.0), a MIDI approximation of a tenor bell's spectrum. No bell-ringing society publishes openly licensed single-bell recordings that I could find.

---

## Rejected (checked on the source)
- **Pianobook packs** (BaltiWurli, David's CP70, Harpsimachord, Lite Hammered Dulcimer): no pack page states any CC licence. They link only the general "Terms and Conditions for Pianobook Library and Website use". A search for any Pianobook pack under a CC licence found none.
- **Sonimusicae "Blanchet 1720"** (two 8′ choirs plus a lute stop, ideal in content): the licence says *"It is forbidden to sell this soundbank or to insert the samples in any commercial application. It is forbidden to modify the samples"*. Not acceptable.
- **Sonimusicae "Ghent Carillon"**: the samples come from bimbam.be, whose terms cannot be verified (the domain is now for sale).
- **SSO harpsichord (4′/8′)**: under CC Sampling Plus 1.0, with sources not mapped per instrument.
- **sfzinstruments "Clavecin"**: no licence; it was converted from a GigaSampler set.
- **sfzinstruments "G-Town Church Sampling Project"**: CC Sampling Plus 1.0, and it contains no bells.
- **loofa "Clavecin" (Freesound)**: CC BY-NC 4.0.
- **Payhip "Keyboard Legacy D6"**: no licence stated.
- **Polyphone "clavinet.sf2"**: an E-mu-origin sample; the page says "give credit" but the provenance is unclear.
- **FreePats**: has no Wurlitzer, CP, clavinet, harpsichord or dulcimer.
- **VSCO 2 CE**: has none of these instruments.
- **Discord SFZ GM bank**: its GM 3 is the same Greg Sullivan CP80 and is marked "CC0" there, which conflicts with the author's page. Its Clavinet, Dulcimer, Harpsichord and Tubular Bells are dummy sines.
