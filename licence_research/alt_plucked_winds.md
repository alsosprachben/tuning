# Openly licensed replacement recordings: plucked strings, flugelhorn, feedback, biwa, rubab

Searched 2026-11-20. I read every licence below on the source's own page: the Freesound sound page, the Commons file page or API, the archive.org item metadata, the GitHub LICENSE or readme, the YouTube watch page's "License" row, or the NDL record. Nothing here is taken from a catalogue or from memory.

How each source states its licence:
- **Freesound:** the sound page's licence link, e.g. "Creative Commons 0" → http://creativecommons.org/publicdomain/zero/1.0/, or "Attribution 4.0" → https://creativecommons.org/licenses/by/4.0/.
- **YouTube:** the watch page's metadata row reads `License: "Creative Commons Attribution license (reuse allowed)"`. On YouTube this means CC BY 3.0.
  - Caveat: the licence is chosen by the uploader. Check that the uploader is the performer or the person who filmed it (noted per item).
  - Caveat: downloading from YouTube is governed by YouTube's own terms. The CC licence covers the work, not YouTube's download terms.
  - Ingest: use the best audio stream (opus, about 130–160 kb/s). It is lossy, so fit below about 15 kHz and avoid fitting noise floors.
- **Commons:** the file page's licence template, quoted from extmetadata `LicenseShortName`.

Legend: **[OK]** = CC0, PD or CC BY. **[SA]** = CC BY-SA (acceptable, but the attribution and share-alike obligation must be honoured). **[X]** = rejected, with the reason.

---

## 1. Lap steel / Hawaiian steel guitar (replaces Pianobook Lapsteel Articulations)

No openly licensed lap-steel multisample exists: none on Freesound, VCSL, VSCO, FreePats, sfzinstruments, Iowa or Philharmonia. The best material is demonstration recordings:

1. **[OK] "E9 Pedal Steel Guitar Tuning, strings 1–10"** + **"E9 tuning-Nashville standard ten string pedal steel"** + **"Pedal Steel demo of E9 sound"** + **"Sound of a Steel guitar playing Hawaiian music"**, all by Eagledj on Wikimedia Commons.
   - Links:
     - https://commons.wikimedia.org/wiki/File:E9_Pedal_Steel_Guitar_Tuning,_strings_1%E2%80%9310.ogg
     - https://commons.wikimedia.org/wiki/File:E9_tuning-Nashville_standard_ten_string_pedal_steel.ogg
     - https://commons.wikimedia.org/wiki/File:Pedal_Steel_demo_of_E9_sound.ogg
     - https://commons.wikimedia.org/wiki/File:Sound_of_a_Steel_guitar_playing_Hawaiian_music.ogg
   - Licences: "CC0" (http://creativecommons.org/publicdomain/zero/1.0/) for the strings 1–10 clip, the E9 demo and the Hawaiian clip; "Public domain" for the Nashville-tuning file. All are marked "Own work".
   - Contents:
     - The strings 1–10 clip is 13 s: ten open strings plucked one at a time, B–D–E–F#–G#–B–D–G#–D#–F#, which gives single notes.
     - The Nashville-tuning file is 18 s.
     - The demos are 17.6 s and 22.6 s, the last in Hawaiian style with bar slides.
   - Fitness: the single open strings are clean per-string decays from a steel's magnetic pickup and string set, and the Hawaiian clip shows the bar slides and vibrato. It is a pedal steel, not a lap steel, but string, bar and pickup physics are the same. **Best pick.** Ogg is lossy.
2. **[OK] Make Noise, "Drop of Sun Pedal Steel Morphagene Reel with Mike Johnson"** (Freesound): https://freesound.org/people/makenoisemusic/sounds/762569/
   - Licence: "Creative Commons 0".
   - Contents: 2:10 of WAV at 48 kHz/32-bit, stereo. Description: "Pedal steel played by Mike Johnson. Recorded and engineered by Mike Johnson at Drop of Sun Studios… Formatted… for use in the Make Noise Morphagene." Studio-quality phrases and swells, cut into splices.
   - Fitness: best audio quality available, with real bar slides and volume swells. Use it for the slide and vibrato law and for the pickup's spectral tilt. Check whether the splices were edited.
3. **[OK] YouTube "1939 Kalamazoo KEH Gibson-made lap steel"** (M Reidsma): https://www.youtube.com/watch?v=OskIvnBM4P8
   - Licence: "Creative Commons Attribution license (reuse allowed)" (CC BY 3.0).
   - Contents: 2:19 solo demo by the owner (the uploader), a real 1930s lap steel with a Charlie Christian pickup, noodling with bar slides.
   - Fitness: a true lap steel through an amp, with slides. Good for the pickup and bar character, though the recording is lossy.
   - Alternates:
     - Scott F. Hall's solo lap-steel performances, CC BY on his own channel: https://www.youtube.com/watch?v=REGCGMsXDwE
     - DaveB11th, Jerry Byrd Frypan in C6, CC BY: https://www.youtube.com/watch?v=3a_bs-WtX0Q (may carry a backing track).
   - Also [SA]/[OK]: Commons "Pedal steel guitar demo.opus" (CC BY 3.0, 89 s, BEAG music) and "Steel guitar solo in Ryūkōka.ogg" (CC BY 4.0, 10 s; provenance thin, as "own work" of what may be an old record).
   - Also: marvman "Slide Guitar bits 1" on Freesound (CC0) is bottleneck slide on an *acoustic* guitar, not a steel: https://freesound.org/people/marvman/packs/2440/

Verdict: usable. Fit the per-string decays from the Eagledj open strings and the slide behaviour from the Make Noise reel and the Kalamazoo demo.

## 2. 12-string acoustic guitar (replaces Pianobook Fender 12 String)

No open multisample exists.
- [X] Polyphone "401 12 string" is labelled "public domain" but its own page says the "Samples first published in Proteus 1 - pop/rock (E-mu…)": a ROM rip.
- [X] sfzinstruments "OvationGuitar (mw1 for 12-string)" states no licence.

The candidates:

1. **[SA] Commons "Vladan Kuzmanović - Bravoure For 12 String Guitar.ogg"**: https://commons.wikimedia.org/wiki/File:Vladan_Kuzmanovi%C4%87_-_Bravoure_For_12_String_Guitar.ogg
   - Licence: "CC BY-SA 4.0", by the composer and performer ("Own work").
   - Contents: 7.5 min solo 12-string piece in A-flat major.
   - Fitness: the longest clean solo 12-string recording available. Isolated notes and phrase ends give the octave-pair and unison-pair beating and the course detune. Ogg is lossy.
2. **[OK] YouTube "Breedlove ECO Pursuit Exotic S 12-String TONE Demo (NO Talking)"** (Guitar Chalk): https://www.youtube.com/watch?v=CftYJUh4bEY
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: 5:27 "audio only demo": strums, chords and single lines, no talking.
   - Fitness: good for the strum model (pick through courses, octave-string brightness).
   - Alternate: Jack Isidore, "12 String Guitar Fingerstyle Solo - Takamine EG523SC-12", CC BY, 2:01, "recorded with microfone, for the pure acoustic sound", own composition: https://www.youtube.com/watch?v=is0Tv5YJILY
3. **[OK] Freesound CC0 fragments:**
   - Zesty17 "12 String Eb.wav", open Eb strums with harmonics: https://freesound.org/people/Zesty17/sounds/669114/
   - kvgarlic "12StringGuitarLongFade.wav", a G chord looped (so the decay is not natural): https://freesound.org/people/kvgarlic/sounds/135829/
   - markiboy123 "12 String Waves.wav": https://freesound.org/people/markiboy123/sounds/422047/
   - All three are "Creative Commons 0". They are short and useful only for cross-checks.

Verdict: no per-note set. The best path is to fit the course model (unison and octave detune, octave-string level, pick order) on top of an existing 6-string acoustic fit, using Kuzmanović for single-course decays and Breedlove for strums.

## 3. Mandolin, single plucked notes (replaces Pianobook Eclectic Mandolin)

No openly licensed per-note mandolin multisample exists.
- [X] sfzinstruments "Terkelsen.Mandolin" has no licence ("Converted from the original GigaSampler version by S. Christian Collins").
- [X] Polyphone "Mandolino" is labelled "public domain", but its page gives author "unknown", only the uploader "bottrop" and no provenance. Treat it as an unverified licence.

The candidates:

1. **Philharmonia Orchestra sound samples: mandolin.** https://philharmonia.co.uk/audio-sound-samples/
   - **Not a CC licence.** The page says: "You are free to use these samples as you wish, including releasing them as part of a commercial work. The only restriction is that they must not be sold or made available 'as is' (i.e. as samples or as a sampler instrument)."
   - Contents: single mandolin notes recorded by Philharmonia players (MP3, per the site). I could not verify the note list; the zip URL returned 404 today.
   - Fitness: it is the only true per-note mandolin set found. Shipping fitted numbers is not making the samples available "as is", so the terms appear compatible, but it falls outside the CC0/BY list you asked for. **You decide.**
2. **[OK] Freesound "Homestyle Mandolin matched set"** (lucasgonze): https://freesound.org/people/lucasgonze/packs/5866/
   - Licence: "Creative Commons 0".
   - Contents: 11 AIFF cues, 44.1 kHz/16-bit mono, from 1 s to about 1 min. Description: "The music is a roundback mandolin from 1900 improvising in the key of G."
   - Fitness: solo, dry and lossless. Note ends and the slower phrases give the paired-course beating and decays. **Best CC option.**
3. **[OK] YouTube "Perretti mandolin demo"** (tavymusic, the restorer): https://www.youtube.com/watch?v=28fvtE57FJo
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: 9:25 demo of a restored Neapolitan mandolin.
   - Also:
     - Commons "Schneewalzer.ogg", CC0, concert mandolin, 30 s, "mit leichtem Echoeffekt" (light echo): https://commons.wikimedia.org/wiki/File:Schneewalzer.ogg
     - "1916 Gibson F-4 Mandolin.", CC BY, 41 s: https://www.youtube.com/watch?v=MwNvjrcRtHQ
   - Not usable for tone: Department64 "Mandolin Tones" (CC BY) is stone and tailpiece effects only.

## 4. Taishogoto (replaces Pianobook Taishogoto): good options exist

1. **[OK] Freesound "multisampled taishogoto"** (msx2plus): https://freesound.org/people/msx2plus/sounds/678381/
   - Licence: "Creative Commons 0".
   - Contents: "recordings of every note on a taishogoto". One 3:00.8 WAV at 48 kHz/16-bit, stereo, 33 MB.
   - Fitness: **a direct replacement.** Cut it per note, then fit the keyed-string decays and the buzz from the key pressing on the string.
2. **[OK] Freesound "Japan_Taishogoto_Amateur_Improvisation.wav"** (RutgerMuller): https://freesound.org/people/RutgerMuller/sounds/365261/
   - Licence: "Creative Commons 0".
   - Contents: 5:05 WAV at 96 kHz/24-bit, Zoom H2n MS stereo. Includes the drone string ("felt more indian… because of the drone-string").
   - Fitness: high resolution. Use it for the drone-string sympathy and for playing gestures.
3. **[OK] Freesound "taisho-g"** (severak): https://freesound.org/people/severak/sounds/808539/
   - Licence: "Creative Commons 0".
   - Contents: a 1.8 s G note "from internal piezo microphone". It is the pickup's output, not the air sound, so use it only as a cross-check.

## 5. Ektara / gopichand (replaces Pianobook The Ektara)

No clean single-note recording exists. Freesound, Commons audio and archive.org turned up only NC material, e.g. the Sanatan Das Baul items are BY-NC-ND. The closest:

1. **[OK] YouTube "Etnochowa. Solo na jednej strunie. Ektara punjab sound"**: https://www.youtube.com/watch?v=RKdUcrhzmgM
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: a 29 s solo on one string, unaccompanied.
   - Fitness: the only isolated ektara found. It is labelled "punjab sound" (closer to a tumbi), so neck-squeeze bends may be absent.
2. **[OK] YouTube "Iktara"** (dchucksster): https://www.youtube.com/watch?v=F6IrnHr3WhQ
   - Licence: CC BY ("Creative Commons Attribution license (reuse allowed)").
   - Contents: 4:55 of "Three young baul singers play the iktaara and sing" at the Kumortully Ghats, Kolkata. Outdoors, with voices.
   - Fitness: genuine Baul gopichand playing, including the bent-neck pitch swoops, but it carries voice and ambience. Usable for the pitch-bend law and the attack, not for clean spectra.
3. **[SA] Commons "Jat Gelo Jat Gelo Bole - Baul performance by Nupur Nadia of Lalon Academy, Kushtia at Bangla WikiConference 2026.webm"**: https://commons.wikimedia.org/wiki/File:Jat_Gelo_Jat_Gelo_Bole_-_Baul_performance_by_Nupur_Nadia_of_Lalon_Academy,_Kushtia_at_Bangla_WikiConference_2026.webm
   - Licence: "CC BY-SA 4.0".
   - Contents: "A female Baul singer leads the song while playing the ektara, accompanied by harmonium…"
   - Fitness: the ektara is mixed with voice and harmonium, so this is a reference only.

Fallback: build the ektara as a single-string pluck on a gourd and skin body, with the pitch-squeeze law taken from dchucksster's swoops. A self-recorded take would beat all of these.

## 6. Flugelhorn (replaces Pianobook Dusty Flugelhorn)

No openly licensed flugelhorn multisample exists anywhere I looked:
- Iowa MIS lists only Horn, Bb Trumpet, Tenor and Bass Trombone, and Tuba for brass.
- VSCO-2-CE has F Horn, OldTrombone, Tenor Trombone, Trumpet and Tuba.
- VCSL has no brass besides didgeridoo.
- Philharmonia does not list flugelhorn.
- The Freesound "flugelhorn" hits are mostly spam-tagged trumpet (Vlad99's "VG Trumpet").

What exists:

1. **[OK] YouTube "Thein Flügelhorn 4 Ventile Präsentation / 4 valves Flugelhorn presentation"** (Poxymedon): https://www.youtube.com/watch?v=srxHjxXZHQ0
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: a 14:05 presentation from a channel devoted to "the scientific study of the rare instruments: 4-valve flugelhorn…". It most likely includes range and timbre demonstrations; I did not watch it, so check its contents.
   - Fitness: potentially the best range and dynamics source. Lossy.
2. **[SA] Commons "Short flugelhorn excerpt.ogg"** + **"Trumpet playing short excerpt for comparison with flugelhorn.ogg"** (Ovinus Real):
   - Links:
     - https://commons.wikimedia.org/wiki/File:Short_flugelhorn_excerpt.ogg
     - https://commons.wikimedia.org/wiki/File:Trumpet_playing_short_excerpt_for_comparison_with_flugelhorn.ogg
   - Licence: "CC BY-SA 4.0".
   - Contents: two 36 s clips of the same improvised tune, "B3 to F4, concert", one on flugelhorn and one on trumpet ("I played the same tune… so that the reader can better understand the difference").
   - Fitness: **ideal for a differential fit.** You already have an Iowa trumpet model, so fit the flugelhorn as the trumpet plus the spectral difference measured between the two takes. Same player, same room. It covers only the middle register.
3. **[OK] Freesound "Taps for the Fallen"** (composingatnight): https://freesound.org/people/composingatnight/sounds/693767/
   - Licence: "Creative Commons 0".
   - Contents: 1:03, 48 kHz/32-bit, "Taps on flugelhorn in a memorial with flagpole and birds". Long sustained bugle-call notes (G, C, E), recorded outdoors.
   - Also:
     - pietermelisse "Flugelhorn-trumpet.mp3", "Attribution 4.0", 20 s comparison: https://freesound.org/people/pietermelisse/sounds/656169/
     - RetiredBrass "Egid Glassl rotary Flugelhorn in C", CC BY, 1:24; a vintage, unusual instrument: https://www.youtube.com/watch?v=xmkAR9pD0q8

Fallback: derive the flugelhorn from the Iowa trumpet fit (conical bore: darker spectrum, softer attack), calibrated against the paired Ovinus takes and checked across the range with the Thein presentation.

## 7. Electric guitar feedback (replaces Pianobook Gretsch Feedback and The Feedbacker)

1. **[OK] Freesound "Dist_Feedback_G-3rd_str_10th_fret.wav"** (SpeedY): https://freesound.org/people/SpeedY/sounds/11805/
   - Licence: "Creative Commons 0".
   - Contents: 23 s, 44.1 kHz/16-bit mono: "Feedback from the open G (3rd) string on the 10th fret which is an F note".
   - Fitness: **exactly the gesture**, a fretted note blooming into feedback through a distorted amp. Lossless, with a known pitch.
2. **[OK] Freesound "Amp Feedback" pack** (airlynx99): https://freesound.org/people/airlynx99/packs/1365/
   - Licence: "Creative Commons 0".
   - Contents: Feedback1–6.wav, 44.1 kHz/16-bit stereo. Description: "Feedback recorded from an amp with a guitar."
   - Fitness: several takes, good for the variation in bloom time and in which partial locks.
   - Also:
     - stomachache "feedback.WAV", CC0: https://freesound.org/people/stomachache/sounds/49282/
     - HenKonen "Feedback noises", CC0: https://freesound.org/people/HenKonen/sounds/757200/
3. **[OK] Commons "Guitar amp feedback - low rumble.ogg"** (Skimel): https://commons.wikimedia.org/wiki/File:Guitar_amp_feedback_-_low_rumble.ogg
   - Licence: "CC BY 4.0".
   - Contents: 21 s with a documented chain: "Godin artisan ST… Line 6 Helix… send out to Fender Rumble 100 amp (to get the physical larsen effect)". Real acoustic feedback through a modelled preamp.
   - Also [OK]: YouTube "Guitar Feedback" (Marxho), CC BY, 3:12: https://www.youtube.com/watch?v=WEd1-MS8odE
   - For the Gretsch body: **[OK] Karoryfer "Black And Green Guitars"** (https://github.com/sfzinstruments/karoryfer.black-and-green-guitars)
     - Licence: the LICENSE file is "CC0 1.0 Universal".
     - Contents: 430 "twang" samples of a "green Gretsch Anniversary" and a Hofner Club, with dynamics, round-robins, hammer-ons and releases.
     - Its "feedback" is *synthesized* (`sample=*sine` in feedback_pitched.sfz) plus two noise beds (fb_bkg.wav, fb_micro.wav). Use it for the Gretsch's string and pickup fit and take the feedback bloom from items 1–2.

## 8a. Japanese biwa: second pass. Openly licensed sources DO exist.

1. **[OK] YouTube "耳なし芳一 Ten.高橋淳、Biwa 久保田晶子"** (Shion Sahara): https://www.youtube.com/watch?v=mMiKbV_wvgA
   - Licence: "Creative Commons Attribution license (reuse allowed)". The composer's channel, from a concert at Tiara Koto, 2022-08-31.
   - Contents: 8:35 of tenor plus biwa (Akiko Kubota). Commons already holds the 23 s solo biwa intro as **[OK] "Biwa intro - 2022 8 31.webm"**, "CC BY 3.0": https://commons.wikimedia.org/wiki/File:Biwa_intro_-_2022_8_31.webm
   - Fitness: concert-hall audio. The intro and the interludes are biwa alone. I believe this is the one the first pass found.
2. **[OK] YouTube "披HIRAKI~肥後の琵琶師橋口桂介氏 復元琵琶御披露目会~"** (琵琶語りのコタロウ): https://www.youtube.com/watch?v=1E-L2pq5G34
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: 2 h 04 min of a 2026-02-11 event at the Shimada Museum, Kumamoto. Chapters include 1:12:21 「薩摩琵琶 城山」 (satsuma), 1:30:24 「筑前琵琶 秋風故郷山」 (chikuzen) and 1:42:58 「肥後琵琶 餅酒合戦」 (higo), plus talk segments about building the instrument.
   - Fitness: **all three biwa types in one CC BY source.** They are narrated or sung pieces, but they contain instrumental passages. The talk segments may include isolated plucks; check.
3. **[OK] Biwa players' own channels and an institution:**
   - Tetsuya Shimokawa, 「祇園精舎(筑前琵琶)」, chikuzen, 60 s, the performer's own channel, CC BY: https://www.youtube.com/watch?v=kV5lgpoRBkc
   - Takahisa Suda (Tsuruta-ryū satsuma biwa), own channel, CC BY:
     - 「絃月の会」, 3:43: https://www.youtube.com/watch?v=4GEqbkQpPi8
     - school lecture with satsuma-biwa performance, 5:25: https://www.youtube.com/watch?v=34PTSFEmptE
     - Kunōzan Tōshōgū offering, 1:45: https://www.youtube.com/watch?v=myYZddh4PBA
   - Museo Nacional de las Culturas del Mundo (INAH), "June Museum Night Biwa", CC BY, 2:45: https://www.youtube.com/watch?v=4UYOOzfrfKI
     - Contents: a "Biwa de Satsuma" concert by Yuuka Yamana, Tsuruta school.
     - An institutional uploader is the strongest provenance among the YouTube items.
4. **[OK] NDL Historical Recordings (Rekion), Nagata Kinshin satsuma-biwa SP records**:
   - Examples: 「薩摩琵琶：石童丸（二）」 https://ndlsearch.ndl.go.jp/en/books/R100000039-I8276335 (https://dl.ndl.go.jp/pid/8276335) and 「薩摩琵琶：常陸丸（四）」 https://ndlsearch.ndl.go.jp/en/books/R100000039-I8274145
   - Status: "Rights (production): pdm"; access "インターネット公開". NDL's reuse page: "Content for which the Use status is インターネット公開（保護期間満了） is in the public domain and may be reused freely… you need not contact the National Diet Library" (please credit NDL).
   - Fitness: legally the cleanest, but these are acoustic-era 78s: narrow band, surface noise, with voice. Good for the sawari buzz envelope and pitch bends, poor for spectra above about 4 kHz.
   - Note: some other biwa SPs at NDL are 「国立国会図書館内限定公開」 (viewable only inside the NDL), so check each record.
- [X] PARADISEC (de Ferranti) is NC, as already known.
- [X] archive.org "The Bard And The Biwa" is an audio drama, not biwa music.

## 8b. Afghan rubab: second pass

1. **[OK] YouTube "Rich Ermlick plays the Afghan Ru'bab"** (Journal of Lifestyle Medicine): https://www.youtube.com/watch?v=o-_CUFyHZ98
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: 6:14 *solo* Afghan rubab at the Pittsburgh Public Market (2014), with ambient noise.
   - Fitness: the cleanest solo rubab found. The sympathetic-string ring and the attacks are audible; room noise limits fitting the noise floor.
2. **[OK] YouTube "Rubab, By Manzoor Jan"** (uploader Jarajo Zirak): https://www.youtube.com/watch?v=bb1RI5iFKCQ
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: 4:06, 2012: "Ustad Manzoor playing Rubab, a very young talented Hazara boy play Rubab." Solo.
   - Caveat: the uploader is not the performer. San José State University's exhibit also lists it with Rights "CC BY".
3. **[OK] YouTube "Ay Nay Nawa - Afghani Folk Song - GECA & Guests"** (Geneva Camerata): https://www.youtube.com/watch?v=1tUWeiGQ_GU
   - Licence: "Creative Commons Attribution license (reuse allowed)".
   - Contents: 9:17 live concert with "Khaled Arman, rubab", a leading Afghan rubab player, together with voice and ensemble.
   - Fitness: professional instrument and playing, but mixed with the ensemble. Use any exposed solo passages.
- [X] archive.org "LPMR MOHAMMAD OMAR" is marked "publicdomain/mark", but it is a radio show playing the 1974 commercial disc *Virtuoso from Afghanistan*, so the mark is false.
- [X] archive.org "UstadShaida" and "UstadQaseem" are marked CC0 by a third party who uploaded commercial recordings (mostly vocal).
- [X] archive.org a-gt-85, "Acoustic String Instrument Sample Library" (CC BY 4.0), is "lofied" MPC loops containing "a mongolian Rubab": wrong instrument and processed.
- [X] Freesound belamalta10 "3 continents" is marked CC0, but its rubab is from "GarageBand's loop library", so the uploader cannot dedicate it.
- [X] Smithsonian Folkways and Aga Khan Music Initiative (Homayun Sakhi): commercial, ℗ Smithsonian Folkways, no open licence.
- [X] CREM-CNRS "Rubab Solo" (Folkways 1961): metadata only.
- [X] British Library Sounds: no open licence found, and downloads unavailable.
- Not the same instrument: Wojtek Szpociński's Pamiri rubab and MED-EL's Uzbek rubob are CC BY but different instruments.

---

## Summary table (best pick per item)

| Item | Best pick | Licence | Per-note? |
|---|---|---|---|
| Lap steel | Eagledj E9 open strings + Hawaiian clip (Commons), plus the Make Noise pedal-steel reel | CC0 / PD | open strings only |
| 12-string | Kuzmanović "Bravoure" (Commons) + Breedlove demo (YT) | BY-SA / BY | no |
| Mandolin | lucasgonze Homestyle set (Freesound); Philharmonia if its custom terms are acceptable | CC0 / custom | no (Philharmonia: yes) |
| Taishogoto | msx2plus "multisampled taishogoto" | CC0 | **yes** |
| Ektara | Etnochowa solo + dchucksster Baul (YT) | CC BY | no |
| Flugelhorn | Ovinus flugel/trumpet pair (Commons) + Thein presentation (YT) | BY-SA / BY | no; fit as a delta from trumpet |
| Feedback | SpeedY CC0 note-into-feedback + airlynx99 x6; Karoryfer Gretsch for the body | CC0 | takes |
| Biwa | HIRAKI event (3 biwa types) + Suda / Shimokawa / INAH (YT); NDL PD SPs | CC BY / PD | no |
| Rubab | Rich Ermlick solo + Manzoor Jan (YT) | CC BY | no |
