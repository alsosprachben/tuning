# Openly licensed replacements: Hammond, French harmonium, multitrack choir

Research date 2026-11-20. Every licence below was read on the source's own page in this session
and is quoted as shown there. Acceptable = CC0 / PD / CC BY / CC BY-SA (SA flagged).

---

## 3. Choir with per-singer tracks (current: Dagstuhl ChoirSet, CC BY-NC-SA) — FOUND

### 3.1 Choral Singing Dataset (CSD), Cuesta et al. 2018 — **versions v2 and v3 are CC BY 4.0** (best)
- v3: https://zenodo.org/records/1286570 — "Version v3", "Published June 10, 2018", licence field:
  **"Creative Commons Attribution 4.0 International"**. File `ChoralSingingDataset.zip`, 937.3 MB,
  md5 `f7b33b763187be309631a65d09402c99`, download available.
- v2: https://zenodo.org/records/1286487 — "v2", "Published June 10, 2018", licence
  **"Creative Commons Attribution 4.0 International"**, same zip name, md5 `43dffaabfb8415c0ce86e8a4da56e974`.
- TRAP: later versions were relicensed. v5 (https://zenodo.org/records/1286485 and /records/2649950,
  "Published April 24, 2019") reads **"Creative Commons Attribution Non Commercial 4.0 International"**.
  Zenodo's DOI "latest" link resolves to the NC version. Download the v3 (or v2) file explicitly by
  record id, record its md5, and save a snapshot of the v3 record page (e.g. Wayback) as licence
  evidence. CC 4.0 grants are irrevocable for the copies released under them (CC BY 4.0 §2(a)(1)),
  so the v2/v3 files stay CC BY even though the dataset is NC today.
- Contents (record description): individual recordings of **16 singers of the Anton Bruckner Choir,
  Barcelona**, recorded in groups of four (one group per SATB section, 4 singers per section),
  **"individual close microphones with cardioid polar pattern"**, video conductor for sync;
  3 a cappella pieces: Bruckner *Locus Iste*, Guerrero *Niño Dios*, Catalan *El Rossinyol*;
  frame-wise f0 + note annotations, semi-synced MIDI; range 87–783 Hz; notes 0.15–6.21 s (mean 0.84 s).
  (Check v3's README for which annotations are in that version; v5 is 1.1 GB vs 937 MB, so v5 added material.)
- Attribution required: cite Cuesta, Gómez, Martorell, Loáiciga, "Analysis of Intonation in Unison
  Choir Singing", ICMPC 15 (Graz 2018).
- Fitness: **excellent for exactly the missing measurement** — 4 singers per section singing the same
  line simultaneously on close mics → per-singer detune, vibrato rate/extent/phase spread, onset
  spread inside a section. Close cardioids in one room have some bleed (not larynx mics); use the
  f0 annotations and check bleed per track. Amateur choir (good for "real section" statistics).

### 3.2 Cantoría Dataset — **version record 5851070 is CC BY 4.0** (second)
- https://zenodo.org/records/5851070 — "Version 1.0.0", "Published January 14, 2022", licence
  **"Creative Commons Attribution 4.0 International"**, file `CantoriaDataset_v1.0.0.zip`
  861.3 MB, md5 `93672d152aa08f4a739dcc8c2817d53b`. Page says a newer version exists.
- TRAP: the newer record https://zenodo.org/records/5878677 (also labelled 1.0.0, 863.2 MB,
  md5 `16dd44822ebb4aa487d3f9de7727235a`) reads **"Creative Commons Attribution Non Commercial 4.0
  International"**. Take the 5851070 file.
- Contents: professional SATB vocal quartet Cantoría (Iberian Golden Age polyphony); organ reference
  track recorded first, then **"each singer was recorded separately"**, 11 songs; individual tracks,
  SATB mixes with/without organ, pYIN + CREPE f0. Mic not stated.
- Fitness: clean isolated professional voices (per-singer vibrato, onset, intonation vs. a fixed
  reference), but **one singer per part and overdubbed**, so no within-section unison spread.
  Good secondary source for vibrato statistics of trained voices; not a substitute for CSD.

### 3.3 LM-SSD (Larynx Microphone Singer-Songwriter Dataset), Schwär et al. TISMIR 2024 — CC BY 4.0
- https://zenodo.org/records/20287765 licence field **"Creative Commons Attribution 4.0 International"**;
  project page https://audiolabs-erlangen.de/resources/MIR/LM-SVR: **"The recordings in LM-SSD are
  available under the Creative Commons Attribution 4.0 International (CC BY 4.0) license."**
  Page warns some songs are covers (composition licence) — irrelevant if only fitted numbers ship.
- Contents: 4 amateur singers + guitar, >3.5 h, 11 songs, larynx mic AND clean close mic per take.
  Singers appear to be recorded per take (not a simultaneous section).
- Fitness: larynx signal gives very clean per-singer f0/jitter/vibrato and a source-vs-radiated pair;
  pop singers, not choir. Useful for source-model and vibrato-shape fitting, not for section spread.

### 3.4 VocalSet (already used, CC BY 4.0)
Solo professional singers (20 singers, 17 techniques), no ensemble takes. It can still supply the
*between-singer* distribution of vibrato rate/extent and formant placement for the same exercise and
key (stack 4 same-voice-type singers as a synthetic section), but not the coupling that happens in a
real unison (singers adjusting to each other). Use CSD v3 for that.

### Rejected (licence verified on own page)
| Dataset | Licence as shown | Page |
|---|---|---|
| Dagstuhl ChoirSet v1.2, 1.2.2, 1.2.3 | "Creative Commons Attribution Non Commercial Share Alike 4.0 International" | zenodo 4607766, 4608395, 3897181, 3956666 |
| ESMUC Choir Dataset (12 singers, close mics, Schütz/Haydn/Heiller) | "Creative Commons Attribution Non Commercial 4.0 International" | zenodo 5848990 and 5848989 |
| CSD v5 | "...Non Commercial 4.0 International" | zenodo 1286485 / 2649950 |
| Cantoría (record 5878677) | "...Non Commercial 4.0 International" | zenodo 5878677 |
| MedleyVox | CC BY-NC-SA 4.0 (Zenodo 7984549, per search; NC anyway) | zenodo 7984549 |
| GVM 2016 Georgian (3 singers, headset + larynx mics) | CC BY-NC-ND 4.0 per audiolabs ThroatMics page (search result) | audiolabs-erlangen.de/resources/MIR/2018-ISMIR-LBD-ThroatMics |
| Erkomaishvili dataset | CC BY-NC 4.0 (zenodo 6900514, per search) | — |
| Bach10 | instruments not voices; download behind a form, no open licence stated | — |
| Cambridge-MT library (has e.g. Don Camillo Choir multitracks) | FAQ: "educational" use; commercial research needs contributor's permission | cambridge-mt.com/ms/mtk-faq (main page 403 to fetcher) |
| jaCappella | paper limits sharing processed audio to research | arXiv 2211.16028 |
| Barbershop Quartets / Bach Chorales (Schramm 2017) | not publicly available | — |
Note: a search engine claimed Dagstuhl is CC BY 4.0 — that is the **TISMIR article's** licence, not the data's.

### Citable published measurements (facts; usable whatever the data licence)
- **Ternström 1991**, "Perceptual evaluations of voice scatter in unison choir sounds", STL-QPSR 32:041–049:
  pitch scatter = SD over voices of each voice's mean F0 per tone; listeners preferred **0–5 cents**,
  tolerated up to **~14 cents** SD (as summarised by Chandna, Cuesta & Gómez, arXiv 2009.09875, and by
  Frontiers in Psychology 2023 doi 10.3389/fpsyg.2023.1220904: "would tolerate a 14 cents standard deviation").
- **Ternström 2002**, "Choir acoustics – an overview of scientific research published to date",
  TMH-QPSR 43:1–8: measured within-section dispersion varied **2–60 cents, typically 20–30 cents**;
  notes the measure cannot separate vibrato from real disagreement.
- **Jers & Ternström 2005**, "Intonation analysis of a multi-channel choir recording", TMH-QPSR 47(1):1–6:
  16 singers on individual mics; dispersion **25–30 cents** (as cited in Cuesta et al., arXiv 1904.05086).
- **Cuesta et al. 2018** (CSD): dispersion **20–30 cents** for all sections, largest in **bass**, smallest
  in sopranos; Table 3 of arXiv 1904.05086 reproduces per-section means ≈ S 20, A 22–23, T 22, B 26
  cents; per piece ≈ Locus Iste 19, Niño Dios 21, El Rossinyol 28 cents (text extraction slightly
  garbled — verify against the PDF before quoting).
- **Chandna, Cuesta, Gómez 2020** (arXiv 2009.09875, on CSD): inter-singer F0 deviation **0–50 cents,
  mean ≈ 20 cents**; voicing-onset/offset spread across a section **≈ 0.1 s** (S 0.134±0.039, A 0.093,
  T 0.100±0.021, B 0.124±0.021 s).

---

## 2. French harmonium with separate registers (current: Silvestre's Debain set, no licence) — NOTHING ACCEPTABLE FOUND

Searched: GrandOrgue sample-set wiki (github.com/GrandOrgue/grandorgue/wiki/Sample-sets), Lars Palo's
download page, Piotr Grabowski, Freesound (harmonium / reed organ / pump organ, CC0 and all), Wikimedia
Commons audio search, VCSL tree, archive.org via search.

- **Lars Palo (familjenpalo.se/vpo/download)**: all pipe organs (Bureå, Kalvträsk, Piteå, Norrfjärden,
  Bygdsiljum, Jukkasjärvi); **no harmonium**. Licence there: "licensed under a Creative Commons
  Attribution-ShareAlike 2.5 license, Swedish jurisdiction"; Norrfjärden 2023 "CC BY-SA 4.0 International".
  (Relevant to the pipe organ, which already uses Piteå; not to the harmonium.)
- **GrandOrgue wiki**: no harmonium entry with a stated open licence; only free-reed listed is a
  diatonic accordion (no licence). The one licence stated on the page is CC BY-NC-SA 3.0 (Virtual-Organs.nl).
- **Piotr Grabowski, Harmonium Emil Müller** (piotrgrabowski.pl/harmonium-emil-muller/): free, German
  harmonium (Diapason 16', Diapason 8', Melodia 8', Viola 4', Flöte 4', Dulcet 8', Flöte 8'),
  but only "© 2026 Piotr Grabowski. All Rights Reserved." — **no licence → not acceptable**
  (could ask him: info@piotrgrabowski.pl; separate stops recorded, so a grant would make it the best candidate).
- **Silvestre's site (jepisi.re/harmoniums)**: "Debain-La Réunion" and "Composite-international"
  sets; no licence on the page — same problem as now.
- **VCSL (CC0)**: no harmonium/reed organ (only pipe organ, Renaissance organ, harmonicas).
- Freesound, best free-reed items (none French, none per-register):
  - donyaquick, "Harmonium Samples - All Keys and Drones" https://freesound.org/people/donyaquick/sounds/330410/
    — **"Creative Commons 0"**; Yale Euterpea Studio, 96 kHz, 7:37, EQ applied. Indian-style hand
    harmonium (has drones), single register. Fitness: free-reed physics (reed attack, beating,
    pressure buzz) only.
  - elankford, "Pump Organ - Sharps_Flats - Mid Octave.wav" https://freesound.org/people/elankford/sounds/95726/
    — **"Attribution 3.0"**; Yamaha pump organ (American suction type), black keys C3–C4, 12-sound pack.
    Fitness: weak — suction reed organ voicing differs from a French pressure harmonium.
- Wikimedia Commons: "C1 cis1 harmonium.ogg" (12 s, two notes, **CC BY-SA 3.0**), "Harmonium (C Major).wav"
  (4.7 s scale, **CC BY-SA 4.0**, Indian). Too thin to fit registers.

**Verdict:** no openly licensed recording of a French harmonium with separate registers exists in the
places searched. Fallbacks, best first:
1. Ask a rights holder for a written grant (Silvestre for the Debain set; Grabowski for the Emil Müller
   set) — numbers-only use, no audio redistribution.
2. Fit from physics + citable literature: Debain/Mustel register layout is documented (Bourdon 16'/
   Cor anglais 8' bass, Clairon 4'/Fifre 2', Basson 8'/Hautbois 8', Clarinette 16'/Flûte 8', Voix céleste
   detuned 8'), free-reed acoustics (J. Cottingham's free-reed papers; reed-cell resonance), and use
   donyaquick's CC0 harmonium for the shared reed-onset/buzz behaviour.
3. Record one (a playable Debain/Mustel/Alexandre is common in French churches and dealers).

---

## 1. Hammond tonewheel: single drawbars, percussion, cabinet (current: Pianobook L102; Indiginus RRO) — NOTHING ACCEPTABLE FOUND FOR SINGLE DRAWBARS / PERCUSSION

Searched: Freesound (drawbar, tonewheel, hammond percussion, leslie/rotary, CC0 filters), Commons
audio search, archive.org via search, sfzinstruments/GitHub, VCSL tree.

- Freesound: nothing single-drawbar or isolated-percussion. Only near-misses: r0cket_fuel
  "Drawbar_C_Chord.wav" (CC0 filter; a C on a Hammond, registration unstated); hammondman's packs
  ("tonewheel organ sound samples" 23 sounds; "Rok organ-Slow & Fast rotary notes" 17 sounds — already
  in use) are the only usable tonewheel set found.
- Wikimedia Commons:
  - "LeslieCabinetSlowFastSlow.ogg" https://commons.wikimedia.org/wiki/File:LeslieCabinetSlowFastSlow.ogg
    — **"I, the copyright holder of this work, release this work into the public domain."**
    Hammond chord, Leslie slow→fast→slow, ~26 s. Fitness: usable for **rotor acceleration/
    deceleration times and chorale/tremolo rates** (one chord, unknown Leslie model, 2005 upload).
  - "LezlieCabinetSequence.ogg" — public domain; 26 s sequence with three speed-ups; tagged
    "Synthetic sounds" too, so may not be a real cabinet — check by ear.
  - "Hammond Organ - Model A Medley.ogg" — **"Creative Commons Attribution 3.0 Unported"**; 1935 Model A
    with Leslie 122, 3:27 of music. Not fit for per-drawbar work.
- HamOrg (Michael Picher; chromatic samples of all nine drawbars from a modified CV, Fast/Slow
  percussion) would be ideal technically but is under the author's own licence agreement restricting
  redistribution — not open; not verified further.
- Leslie measurements: Smith, Serafin, Abel, Berners, DAFx 2002 — Leslie 600 horn IRs at 15° steps,
  © J. O. Smith, data not published openly (ccrma.stanford.edu/~jos/pasp05/Leslie_Free_Field_Horn_Measurements.html).
  TU Berlin directivity database (CC BY-SA 4.0, arXiv 2307.02110) has no organ/Leslie.

**Verdict:** no openly licensed single-drawbar or isolated-percussion recordings found. Fallbacks:
1. **Primary documentation (facts, citable)** — Hammond service manual (archive.org "HSM495-2016",
   https://archive.org/stream/HSM4952016/Hsm495-2016_djvu.txt): percussion borrows the 2nd or 3rd
   harmonic drawbar signal of the upper-manual B preset; the Fast tablet "shunts resistor R57 across the
   slow decay resistor (R58) reducing time for decay capacitor C31 to discharge", and fast also raises
   control-tube output "about 50%" to keep loudness equal; Soft shunts R46 across the output transformer;
   percussion steals the 8th-harmonic (1') drawbar on the upper manual; schematic RC values give the
   decay constants. Same manual lists tonewheel frequencies/ratios and wheel-level tables, i.e. the
   drawbar foldback and per-wheel structure can be fitted from documentation + hammondman's CC0 notes.
2. Reference implementation for parameters (GPL code; numbers are facts): setBfree man page defaults
   `osc.perc.fast` 1.0 s and `osc.perc.slow` 4.0 s decay (setBfree 0.7.5 man page; check current).
   Pekonen, Pihlajamäki, Välimäki, DAFx-11 "Computationally Efficient Hammond Organ Synthesis":
   model choices (not measurements) — key-click envelope 50 ms decay, percussion 70 ms constant
   decay, Leslie modulator 2 Hz slow / 6 Hz fast, treble 0.1 Hz above bass.
3. Record: a single-drawbar/percussion session on any working B-3/C-3/A-100 is short (9 drawbars ×
   a few keys + 4 percussion combinations); the PD Commons Leslie clip covers rotor ramps meanwhile.

---

## Summary ranking
1. Hammond: none acceptable for drawbars/percussion. Cabinet ramps: Commons "LeslieCabinetSlowFastSlow.ogg" (PD).
   Keep hammondman (CC0); fit percussion from the service-manual circuit; consider recording.
2. French harmonium: none acceptable. Ask Silvestre/Grabowski for a grant; CC0 donyaquick harmonium only for generic reed behaviour.
3. Choir: **CSD v3/v2 (CC BY 4.0, zenodo 1286570/1286487)** — 4 singers/section, close mics — replaces Dagstuhl;
   Cantoría record 5851070 (CC BY 4.0) and LM-SSD (CC BY 4.0) as secondary; plus the cited 20–30-cent figures.
