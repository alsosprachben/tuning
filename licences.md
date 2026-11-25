# Licences: what the voices were fitted to, and what blocks a sale

Clavitone ships no recordings. Every voice is a model whose numbers were
FITTED to, or MEASURED on, recordings that their makers shared. Those numbers
are what ship, so a source's licence still matters:

- **CC0 and public domain**: no conditions. We credit them anyway, as thanks.
- **CC BY**: free for commercial use if the source is named: author, title,
  link, licence, and a note that we changed it (we measured it; the sound is
  our model). The Credits page does this (`credits.py` → `ui/credits.json`).
- **CC BY-SA**: as CC BY, plus share-alike for adaptations. A fitted number
  is very likely not an adaptation of the recording, but this is the one
  open question to put to a lawyer before the store.
- **NC (non-commercial), ND (no derivatives), access conditions, EULAs that
  forbid commercial use or analysis**: these BLOCK A SALE while their numbers
  are in the build. Each is an issue below, with what to do about it.

The full findings behind each issue's alternatives (every link, licence quote
and rejection) are in `licence_research/`.

The register of every source is `credits.py`; `examples/gm_coverage.py
--about` writes the Credits page from it, and fails if a voice's notes name a
source the register doesn't hold.

## Open issues

**Policy (Ben, 2026-11-20): no licence requests.** We never ask a rights
holder for permission or a written grant ("they will ask for a revenue
share"). Every issue below closes by an openly licensed source or our own
recording, and the "ask ..." alternatives are dropped. The drum machines
take the TR-8 route (MckAudio's CC0 recordings of a Roland TR-8 playing:
808, 909, 707, 606) and, for the 606, the Behringer RD-6 recordings (CC0).

Status: `open` until the voice is refitted to an open source, the rights
holder grants commercial use in writing, or the voice is left out of the
store build.

### L1. Electric Piano 1 (Rhodes): jRhodes3d — CC BY-NC (samples) — CLOSED 2026-11-23

- **Source (was):** Jeffrey Learman's jRhodes3d, a 1977 Mark I recorded off
  the harp connector (samples CC BY-NC).
- **What derived from it:** the Rhodes fit (`examples/rhodes_fit.py`), the
  register level.
- **Status:** CLOSED. The tine and pickup are now millimetres
  (`tonelib.RhodesProperties`): the tine's length from the Rhodes service
  manual's chart, the voicing gap from its ch. 4, the swing from CBS's patent
  US 4,040,321, the decay from Shear's thesis (UCSB 2011); only the pole's
  size and face and the tine's rest, and the register's level, are fitted --
  to tim.kahn's Mark II (Freesound pack 3957, CC BY 4.0;
  `RHODES_REF=timkahn examples/rhodes_fit.py fit|register`). jRhodes3d stays
  on disk, read only by `rhodes_fit.py` without RHODES_REF, for comparison.

### L2. Electric guitars (GM 26-31): Fraunhofer IDMT-SMT-Guitar — CC BY-NC-ND 4.0 — CLOSED 2026-11-23

- **Source (was):** Fraunhofer IDMT's guitar set, DI, the Ibanez 2820 neck humbucker.
- **What derived from it:** the electric guitars' string, pickups, mute and
  harmonics (`JazzGuitar` and the clean, muted, overdriven, distortion and
  harmonics programs that share it; `examples/egtr_fit.py`).
- **Status:** CLOSED. Every number refitted, each approved by Ben's ear:
  - the string and the Jazz Guitar (26): Guitar-TECHS (Zenodo 14963133, CC BY
    4.0), P2's neck humbucker, DI;
  - the Clean Guitar (27): its coil's load from its circuit
    (`examples/strat_coil.py`), the pick from 26;
  - Overdrive and Distortion (29, 30): 26's fit moved to the bridge by
    geometry, checked (not fitted) on Guitar-TECHS' P1;
  - the palm mute (28) and harmonics (31): Guitar-TECHS' P2 technique takes,
    DI (the harmonics' pluck with the DI's hum and hiss taken out).
  IDMT-SMT-Guitar is no longer read (`egtr_fit.TECHNIQUE_SOURCE = "techs"`;
  the IDMT staging stays only for the basses, L3).

### L3. Electric basses (GM 33, 34, 36, 37): Fraunhofer IDMT-SMT-Bass — CC BY-NC-ND 4.0 — CLOSED 2026-11-23

- **Source (was):** Fraunhofer IDMT's bass set, DI, three basses.
- **What derived from it:** `FingeredBass` and the picked and slap basses
  built on it (`examples/egtr_fit.py`).
- **Status:** CLOSED. Nothing of IDMT's is read:
  - the string from its physics (`examples/bass_physics.py`): Issanchou's
    string losses, Zollner's bearing conductance, the winding's loss and each
    string's core from the stretch, fitted to quartertone's Gretsch (Freesound
    pack 14708, CC BY 4.0) and FreePats' Yamaha RBX (CC0) -- and played the
    same way in every engine;
  - the pickups' load from their circuit (`examples/jbass_coil.py`, Fender's
    published coil inductances);
  - the finger against the pick on FreePats' same bass; the pick the
    guitar's (Guitar-TECHS, L2);
  - the damp a variable (`damp_dbs`), set by ear;
  - slap and pop from a simulation of the string against its frets
    (`examples/fret_contact.py`, baked to `fretcontact_data.py`).

### L4. Biwa Stroke (GS 120.12): PARADISEC HDF1-SB33 — CC BY-NC-SA 4.0 and access conditions

- **Source:** Hugh de Ferranti's satsuma biwa recordings at PARADISEC. The
  access conditions say commercial enterprises may not include the data in
  models, beyond the NC licence.
- **What derived from it:** `tonelib.BiwaProperties` (`examples/pluck_fit.py
  --voice=biwa`). The audio stays local and is never sent anywhere.
- **Status:** CLOSED 2026-11-23 (Ben: "Approved"). The tape is no longer read;
  every number it gave is replaced. The open strokes (Takahisa Suda's own CC BY
  videos, INAH's CC BY concert; `examples/biwa_open.py`) were too few and too
  roomy to fit the ring, so the instrument is physics (Ben: "Contact model. Go
  with the physics"): the sawari simulated (`examples/sawari_contact.py`,
  Taguti's model, Acoust. Sci. & Tech. 29(3) 2008, with the silk's measured
  stiffness) and baked per key (`sawari_data.py`, `tonelib.SawariContact`, in
  every engine: the SAWR export section); the silk's losses and Taguti's
  two-resonance body fitted to Taguti & Tohnai's anechoic unshaved nut (Acoust.
  Sci. & Tech. 22(3) 2001), the strong sawari then predicted. The bachi's knock
  on the belly is fitted to the open strokes (credited). The release is the
  shamisen's; the level is held at the old voice's (bank balance).
- **Alternatives (checked 2026-11-20):** nothing open fits a model. The only
  open biwa audio is 23 s of compressed video ("Biwa intro - 2022 8 31",
  Wikimedia Commons, CC BY 3.0), enough to check the sawari buzz, not to fit
  decays. Freesound, archive.org and Europeana hold none under an open licence.
  The way out is a new recording: single plucks by a player, released CC0.
- **Second search (2026-11-20):** CC BY biwa playing on YouTube: a two-hour
  Kumamoto event with satsuma, chikuzen and higo biwa in chapters; players'
  own channels (Tetsuya Shimokawa, chikuzen; Takahisa Suda, satsuma); a
  satsuma concert on Mexico's national museum channel (INAH), the best
  provenance; and the full concert behind the Commons clip. Japan's National
  Diet Library has 1920s Nagata Kinshin satsuma-biwa records marked public
  domain ("may be reused freely"): narrow-band 78s with voice. Lossy YouTube
  audio fits below ~15 kHz; strokes between the singing are fittable.

### L5. The 27 measured raga tunings: Saraga 1.5 Hindustani — CC BY-NC-SA 4.0

- **Source:** the CompMusic Saraga dataset (Zenodo 4301737), its recordings'
  pitch, by `examples/saraga_swaras.py`.
- **What derives from it:** the `saraga_*` tunings in `ragas.py`, shown on the
  Tuning card under their raga names. These are tables taken straight from the
  data, the most direct derivation of any issue here.
- **Status:** CLOSED BY DROPPING (Ben, 2026-11-22), and since 2026-11-23
  MEASURED AGAIN FROM AN OPEN SOURCE: 29 ragas (`sung_*` in `ragas.py`,
  `examples/rrd_swaras.py`) from the Raga Recognition Dataset's Hindustani
  pitch tracks (Zenodo 7278506, CC BY 4.0; read in place by
  `examples/rrd_stage.py`), by Serra 2011's rule as before. Unlike Saraga's,
  its recordings do not say which have a harmonium, so none are left out.
  Marva (4 swaras clear) is not written. `examples/saraga_swaras.py` stays,
  for local study only (its data since deleted).
- **Alternatives (checked 2026-11-20):**
  1. The Indian Art Music Raga Recognition Dataset's features (Zenodo
     7278506, CC BY 4.0): pitch contours, tonic and nyas segments for 300
     Hindustani recordings in 30 ragas, the same kind of data
     `saraga_swaras.py` reads. Check its raga list against ours.
  2. Published measurements, cited as facts: Bel 1988 (Todi: re 95, ga 294,
     ma# 606, ni 1107, averaged over performances), Levy 1982, Jairazbhoy &
     Stone 1963, Datta et al. 2006.
  3. CompMusic's own uploads on Freesound (CC BY and CC0 alap, sarod and
     vocal takes) to measure ourselves.
  - Rejected: Saraga's annotations are under the same NC licence as its audio;
    IndRaga (CC BY 4.0) has restricted files.

### L6. Rabab (GS 105.8): a Freesound upload that is a GarageBand loop — doubtful CC0 — CLOSED 2026-11-23

- **Source (was):** belamalta10's "3 continents" (Freesound 513846), its rubab
  opening a GarageBand loop the uploader could not put under CC0.
- **Status:** CLOSED. The colour refitted to Rich Ermlick's six-minute solo
  ("Rich Ermlick plays the Afghan Ru'bab", YouTube o-_CUFyHZ98, CC BY as its
  uploader marks it; `RABAB_REF=ermlick examples/rabab_fit.py --fit`); the
  decay and the plectrum's stop as Ben voiced them (the solo's sympathetic
  strings hold every note, so its decay cannot be read). Ben: fine.

### L7. Pianobook libraries — Pianobook's terms forbid it: CLOSED 2026-11-22

- **The terms** (pianobook.co.uk/terms-conditions, section 5): the samples are
  licensed "only within your own newly-created sound recording(s)"; the
  licence "expressly forbids resale or other distribution of the Products or
  their derivatives, either as they exist in the library, ... or mixed,
  combined, filtered, re-synthesised or otherwise edited, for use as sounds
  ... or patches in a sampler, microchip, computer or any sample playback
  device", and "Products may not be used in or in relation to any competitive
  products that are sold". A model fitted to them, sold as an instrument, is
  what this clause is written against.
- **What derives from them:**
- **Harpsichord 4': rebuilt 2026-11-22 from physics** -- plucked at twice
  the 8''s fraction (0.23), the 8''s VCSL laws at its pitch, its level by
  Ben's ear: APPROVED ("Sounds good"); the Harpsimachord credit gone. With
  it every voice is off Pianobook's libraries.
- **Tonewheel organ: rebuilt 2026-11-22 off the L102:** the 16', 5 1/3' and
  1 3/5' on the CC0 B3 packs' own drawbar law (-2.8 dB an octave: 1.38,
  0.94, 0.53); the spinet speaker from a 12" paper cone's physics, Ben's
  "Breakup" over a plain piston; the percussion's decay from the service
  manuals' circuit (C31 0.33 uF, R57/R58), its levels by Ben's ear. The
  Hammond L102 credit gone; L9 closed with it.
- **Status:** CLOSED 2026-11-22, and the last remnant 2026-11-24: the Taisho
  Koto's top, trio detune and pick sweep had stayed on Chanson's pack after its
  2026-11-20 refit, and its drone stop on the pack's drone takes -- now the top
  and detune on msx2plus's CC0 take, the sweep by Ben's ear, the drone from the
  voice's own laws (A/B approved: "Sounds good"); the Pianobook credit gone. No
  voice reads a Pianobook library. The record of each refit:
  - **Refitted 2026-11-20** (A/Bs in ~/Music/licence_refits): Taisho Koto
    to msx2plus's taishogoto (CC0) and the harpsichord's lute stop back to
    VCSL's English Lute row (CC0) -- both APPROVED by Ben's ear. The
    harpsichord's upper 8' to VCSL's Flemish pair (CC0), 2026-11-22: APPROVED
    ("They sound good"; harpsi_upper8_{old,new}.mp3). Electric
    Grand to Greg Sullivan's CP80 (CC BY 4.0), the wound bass's attack then
    fitted (cp80_wound_fit.py), its levels GeneralUser's (0f4a6ac): APPROVED
    2026-11-22 (Ben: "works great"); the old fit's text and credit gone, the
    Electric Grand off this list. Electric Piano 2 refitted 2026-11-22 to
    OldBassMan's 200A (CC BY 4.0) and Sullivan's EP203W (CC BY 4.0), the
    action's knock MODELLED (no open recording of it exists), at the low of
    three levels: APPROVED 2026-11-22 ("It all sounds good"); BaltiWurli's
    credit gone, Electric Piano 2 off this list. Church Bell refitted
    2026-11-22 to the lowest bell of Bethesda Church, Saratoga Springs
    (HMTSCCSound, Freesound 554655, CC0; church_bell_fit.py), its click
    fixed (a 4 ms rise): APPROVED ("Click is gone"); St Kathrin's credit
    gone. Guitar Feedback (30.8, 31.8) refitted 2026-11-22 to SpeedY's
    distorted F4 (Freesound 11805, CC0) and airlynx99's amp-feedback takes
    (Freesound pack 1365, CC0), the loop's partial chosen physically (its
    gain round the loop: bridge drive, pickup comb, damping, cabinet, the
    takes' coupling band): APPROVED ("Awesome. This is great"); the Gretsch
    and Feedbacker credits gone. Dulcimer rebuilt 2026-11-22: fitted to
    iternetcone's takes (Freesound pack 19445, CC BY 4.0; C4-D5), the bass
    bridge's stiffness and the layout from Musicmakers' published 17/16 kit
    charts, the decay from string physics (the board's conductance by ear:
    "Keep the long one"), the halo held past the takes: APPROVED; Kemp's
    credit gone. Flugel Horn rebuilt 2026-11-22 FROM PHYSICS as a difference
    from our Iowa-fitted trumpet (bell, cup, bore, the attack of a
    low-back-pressure bore), each choice by Ben's ear (a trumpet player):
    APPROVED ("Go with that one"); the Dusty Flugelhorn credit gone. Each other voice's notes still name
    the old source beside the new until Ben approves and the old fit's text
    goes.
- **Alternatives (checked 2026-11-20; Freesound licenses each sound, so check
  every file before fitting it):**
  - **Wurlitzer:** Greg Sullivan's "Wurlitzer EP200" (an EP203W;
    github sfzinstruments/GregSullivan.E-Pianos), CC BY 4.0 on his own site
    (updated 21-Oct-2026; the README says 3.0: credit him either way). THIN:
    42 takes but only ~11 keys A1-Ab6 (four velocities on some), median
    2.2 s, and LOOPED ("clean up the audible loop artifacts" is on his own
    to-do list): attack and early decay only. Velocity behaviour. Plus OldBassMan's "Wurlitzer 200a"
    (Freesound pack 5726, CC BY 4.0): 13 notes D3-D7, ~7 s, through a
    transformer and tube preamp, so DI-like. Tone and decay.
  - **Electric Grand:** Greg Sullivan's CP80 (same licence): 81 notes D#1-C#7,
    four velocities, long (D3 ff 22.8 s), with the unison beating. A CP-80,
    not a CP-70; no open CP-70 exists.
  - **Dulcimer:** weak. iternetcone's "Multi-sampled Hammered Dulcimer"
    (Freesound pack 19445, CC BY 4.0): ~8 single notes over an octave and a
    half, one dynamic. batchku's santoor (CC0) is rolls on contact mics.
  - **Harpsichord lute stop:** VCSL's English harpsichord has its own Lute
    row (CC0), beside the Normal row we already fit. A direct replacement.
    **Upper 8':** VCSL's Flemish harpsichord has High and Low rows at the same
    pitch, probably its two 8' choirs (undocumented). **4':** no open
    recording anywhere; model it as a separately scaled string set.
  - **Church Bell:** Notre-Dame's bourdon Emmanuel (Commons, CC0, 189 s,
    lossy; swung or struck to check by ear); the 25-tonne Bucharest cathedral
    bell (Commons, CC BY-SA 4.0, 24-bit WAV, close); HMTSCCSound's "bec low
    bell solo" (Freesound, CC0, one strike, full ring-out, a smaller bell).
  - **Tonewheel drawbars and speaker:** see L9.
  - **Taisho Koto:** a direct replacement. msx2plus's "multisampled
    taishogoto" (Freesound, CC0): every note, 48 kHz. Also RutgerMuller's
    improvisation (CC0, 96 kHz, with the drone string).
  - **Hawaiian Guitar: rebuilt 2026-11-22 from physics** (no lap-steel
    multisample is open): the decay from published steel-string losses
    (Issanchou et al., JSV 2017 / JASA 2018) on GHS's lap-steel E set at
    Fender's 22.5" scale plus Pate et al.'s solid-body mounting (JASA 2014);
    the tone from the circuit (tone knob down: 505 Hz, Q 0.56); open strings
    tuned true; the sympathy's level by Ben's ear (halved). Eagledj's steel
    clips (Commons, CC0) heard as references. APPROVED ("Sounds good"); the
    Lapsteel Articulations credit gone.
  - **12-string Guitar: refitted 2026-11-22** from physics and played
    recordings, on our Iowa-fitted steel-string: the courses' detune read off
    markiboy123's "12 String Waves" (Freesound 422047, CC0; six melody notes,
    unison pairs 7.2 cents) and its and Kuzmanović's "Bravoure" (Commons, CC
    BY-SA 4.0; low notes, octave strings 9.9 cents), the octave string's
    level by physics, the pick the mandolin's (Philharmonia-fitted).
    APPROVED by ear ("Sounds good"); the Fender 12 String credit gone.
  - **Mandolin: refitted 2026-11-22** to the Philharmonia's free samples
    (every note G3-A6). Their licence: "free to use these samples as you
    wish, including releasing them as part of a commercial work", the only
    restriction not to sell them or make them available "as is" (as samples
    or a sampler instrument); we ship fitted numbers only. Their site's
    general terms (clause 4: site content for personal, non-commercial use
    without written permission) sit beside it; Ben's reading: the samples
    page's licence IS that written permission, and their invitation to share
    projects made with them is an opportunity. APPROVED by ear ("Sounds even
    better than the old"); the Eclectic Mandolin credit gone.
  - **Gopichant: refitted 2026-11-22** from open recordings
    (examples/ektara_open.py): the scoop from dchucksster's Baul singers
    (YouTube, CC BY: 342 plucks, 230 cents under, held ~0.2 s and let go by
    0.3 s), the string, decay and colour from Etnochowa's one-string solo
    (YouTube, CC BY; labelled "Punjab sound", likely a tumbi). Ben chose to
    keep it the gopichand, with the Baul timing. The Ektara credit gone.
  - **Flugel Horn:** no open multisample anywhere. Fit it as a difference from
    the Iowa trumpet: one player's flugelhorn and trumpet takes of one tune
    (Commons, CC BY-SA 4.0); a "Taps" take (Freesound, CC0) for held notes.
  - **Guitar Feedback:** good. SpeedY's note blooming into feedback (Freesound,
    CC0, 23 s, lossless), airlynx99's six feedback takes (Freesound, CC0), a
    Commons take with its chain documented (CC BY 4.0); Karoryfer's "Black And
    Green Guitars" (CC0, 430 notes of a Gretsch) for the body.

### L8. Choir (GM 52, 53): Dagstuhl ChoirSet — CC BY-NC-SA 4.0 — CLOSED 2026-11-23

- **Source (was):** Dagstuhl ChoirSet (every Zenodo version CC BY-NC-SA 4.0).
- **What derived from it:** the choir section's spread and each singer's
  vibrato (the voice itself is VocalSet's, CC BY 4.0).
- **Status:** CLOSED. The vibrato measured on the Choral Singing Dataset
  **v3** (Zenodo 1286570, CC BY 4.0, md5 f7b33b76...; record snapshot kept
  in ~/Documents/refs/csd_v3) by `examples/csd_section.py` (YIN per singer,
  the four of a part against their median): +/-11 cents, 4.2-5.8 Hz. The
  spread the published choirs' (Ternström 2002; Jers & Ternström 2005:
  20-30 cents), +/-24, as Ben's ear chose. `choir_fit.py section` still
  reads Dagstuhl locally, for comparison only.

### L9. Percussive Organ (GM 17): Indiginus Real Rotor Organ — EULA

- **The terms:** "You may not use the samples in this library to create and
  distribute any other sample pack or product."
- **What derives from it:** the B3 percussion tap's 2nd and 3rd harmonic decay.
- **Status:** CLOSED 2026-11-22. The tap's decay from Hammond's service
  manuals (HSM495: C31 0.33 uF through R58 4.7 M, R57 1.5 M across it for
  fast; the spinet manuals' "less than 1/2 second" to cut-off): ~110 dB/s;
  its level by Ben's ear ("B3 as the default, level is good"). The
  Indiginus credit gone.
- **Was:** open.
- **Alternatives (checked 2026-11-20):** no open isolated-percussion or
  single-drawbar takes exist (the free HamOrg library has them under a
  restrictive licence). Fallback: the Hammond service manual (HSM495) gives
  the percussion circuit (fast decay puts R57 across the slow resistor R58 to
  discharge C31 sooner, the level raised "about 50%"), so the decay constants
  follow from its RC values; setBfree's defaults (1.0 s fast, 4.0 s slow) as a
  check. Or record a B-3: a short session.
- **The speaker cabinet** (also from the L102, L7): Wikimedia Commons
  "LeslieCabinetSlowFastSlow.ogg", released into the public domain by its
  recordist: 26 s of a chord, slow to fast to slow, enough for the rotors'
  speeds and their acceleration.

### L10. No licence stated (all rights reserved by default)

- **Debain harmonium** (Jean-Pierre Silvestre's Hauptwerk set): the reed
  organ's registers (GS 20). CLOSED 2026-11-23 (Ben: "Sounds great"): every
  number it gave is replaced from physics. The reed is simulated
  (`examples/freereed_sim.py`: Millot & Baumann's free reed, St Hilaire's
  drive, checked against Puranik & Scavone's measured harmonium reed and
  Cottingham's reed-organ measurements); the stops are built as Mustel's
  *L'Orgue-Expressif ou Harmonium* (1903, public domain) describes them
  (`examples/harmonium_stops.py`) and baked (`examples/harmonium_bake.py`:
  series, speech, level); the celeste is Mustel's own +/- beats; the tremolo
  is a bellows, its rate Ben's by ear. The foundation stays donyaquick's (CC0).
  `examples/debain_registers.py` is retired and its credit removed.
- **Aalto clavinet** recordings: CLOSED 2026-11-22. The Clavinet (GM 7)
  rebuilt from the papers' published measurements of one D6 (EURASIP 2013,
  CC BY; ICMC 2011; DAFx-12: examples/clav_published.py) -- stiffness table,
  loop and ripple filters, scale, pickups, the release's drop -- with the
  tilt and the key-up by Ben's ear ("as close as we can get with the
  material we have"). clav_fit.py and the Aalto credit removed.
- **Drum machines (TR-808, TR-606, TR-707): CLOSED 2026-11-22.** All four
  machine kits refitted to MckAudio's TR-8 recordings (CC0); the 808's metal
  oscillators set from the service notes. Fischer's, Vargo's, bdu's and
  hyperreal's sets are no longer read, and their credits are gone.
- **The clavinet's listening reference:** Markus Ruffing's "Hohner Clavinet
  D6.ogg" (Commons, free use; ~/Documents/refs/clavinet_ruffing): dense
  riffs across the pickup settings, through a WAH (Ben heard it; a 9 dB swell
  darkening at 21.8-22.1 s), lossy -- feel and register, not tone.
- **Alternatives for the harmonium (checked 2026-11-20):** no openly licensed
  French harmonium with separate registers exists (Grabowski's free Emil
  Müller set records the stops separately but is "All Rights Reserved").
  Open but single-register: donyaquick's harmonium (Freesound, CC0, already
  used for GM 20), elankford's Yamaha pump organ (CC BY 3.0, black keys).
  Best: ask Silvestre (or Grabowski) for a written grant for fitted numbers;
  else fit the registers from their documented layouts with the CC0 reeds.
- **Status:** CLOSED 2026-11-23: every item above is closed (the clavinet
  and the drum machines 2026-11-22, the harmonium 2026-11-23).

### L11. TR-909 (Rob Roy / Jason Baker set) — CLOSED 2026-11-22

- The TR-909 kit and its ROM cymbals refitted to MckAudio's TR-8 recordings
  (CC0; Ben 2026-11-20: a played Roland recorded by its owner is fine).
  Baker's set is no longer read; its credit is gone.

### L12. Smaller questions

- **Ross harpsichord voicing** (`ross.sf2`, John Sankey): no licence for the
  soundfont. CLOSED 2026-11-22: the optional voicing (`TUNING_HARPSI=ross`,
  `HarpsiRossProperties`) and its credit removed; the default harpsichord
  (VCSL's, CC0) never used it.
  Open alternative: pjcohen's "Harpsichord" (Freesound, CC0, 60 notes
  D1-G#5, overhead mics, maker unstated).
- **TimGM6mb** (GPL-2): one of the references in the Orchestra Hit fit. Fitted
  numbers are unlikely to be a derivative work; easy to drop from the fit.
  DROPPED FROM THE FIT 2026-11-23 (Ben: "OK, drop it"): `examples/orchhit_fit.py`
  no longer reads its hit (EXCLUDE), and every number of the voice, its timpani
  and cymbal with them, was refitted on FluidR3's and GeneralUser's four
  (score 1344 -> 1157; Ben: "Orchestra Hit is good"). It is still one of the
  release consensus's four sets and a level reference.
  An open replacement: the US Marine Band's "Infernal Dance" from the
  Firebird (Commons, public domain as a US government recording), the passage
  the original Fairlight stab came from, though a wind-band arrangement; or a
  tutti chord chopped from the Marine Chamber Orchestra's Beethoven 1 (public
  domain, strings included).
- **GeneralUser GS**: its licence says some samples' origins are unknown
  (Collins reprograms presets to match Roland's; no per-sample sources). Our
  rule (Ben, 2026-11-24): recordings others made of an instrument are fine,
  raw samples lifted from a unit are not -- and GeneralUser's cannot be told
  apart. AUDITED 2026-11-24.
  REFITTED, nothing of GeneralUser's left (2026-11-24, each by Ben's ear):
  High Q and Square Click (from their names, on the TR-808 engine), Telephone
  2 (the MC34017 ringer chip's datasheet: 808/1010 Hz, 12.5 Hz), Burst Noise
  (radio static), the Starship (our noise and buzz) and the Gated SD (our
  acoustic snare and a gated room); the two-tone Electronic snare fitted to
  its sample, unused, removed. Their fit scripts retired (sfx808_fit.py,
  telephone2_fit.py, starship_ref.py; weather_fit.py's burst and starship,
  elkit_fit.py's gated and snare).
  STILL READ, for the lawyer -- measurements of its samples, no audio:
  levels (patch_map's trims, the kits' per-key gains, release times); the
  Orchestra Hit (one of the fit's two reference sets); the Brush Swirl's
  envelope; LiveRoom (two numbers); the Electronic toms' pitches and gates;
  the SFX set's gesture timings and held lengths (percussion_map.KIT_GATE);
  the Simmons hits chosen as closest to its (the voices fitted to the real
  Simmons takes).
- **VSCO 2 CE's upright piano** (Ivy Audio): CC0 through Versilian's grant
  (the repo's LICENSE is CC0; Info.txt: "Bearer is granted right to
  redistribute this sample set by Versilian Studios LLC"; Readme: "permitted
  to use these samples for ANY purpose. We ask that you do not sell the
  samples directly"). Fitted numbers aren't the samples: fine. Credit both.
  Versilian's own "Upright Nr1" is the fallback with no third party.
- **CC BY-SA** (the oud and traverso Commons files): see the share-alike
  question above. THE PITEÅ ORGAN (Lars Palo's GrandOrgue set, CC BY-SA 2.5 SE)
  NO LONGER APPLIES, 2026-11-24 (Ben: "physical modeling the way we did for the
  harmonium"): every pipe stop of GM 19 -- tone, speech, release, wind noise,
  levels, Mixture III, the celeste -- is simulated from its construction
  (Audsley's public-domain books; examples/fluepipe_sim.py, reedpipe_sim.py,
  pipe_impedance.py, organ_bake.py), judged by Ben's ear against our own
  renders, no recording compared. Its fit scripts retired, its credit removed.

### L13. Trademarks: other makers' names in ours

Not a licence question but a naming one (Ben, 2026-11-22: "the labels of a
brand of thing, how can we label that in a way that is legally okay?"). Not
legal advice: a lawyer reads this before sale.

- **The rule we follow: referential (nominative) use.** A maker's name may
  say WHAT a sound models when (1) the name is needed to say it, (2) only the
  word is used -- no logo, wordmark lettering, panel art, colour scheme or
  photo of theirs -- and (3) nothing suggests they made, approve or sponsor
  it. The name describes; it never names OUR product or feature. So "Kit 25,
  after the TR-808" or "modelled after the Leslie 122", in descriptive text;
  never a product, pack, preset bank or feature called by the mark alone.
  The music convention "after" is the right word for it.
- **Never:** "official", "authentic", "the real X", "licensed", "approved";
  logos, typefaces or panel layouts copied from theirs (the Moog card is
  laid out after the Messenger's controls: check it copies no artwork or
  lettering); the marks in our app name, icons, store keywords as our own.
- **The GS / MT-32 maps' names** ("808 Bass Drum", "TR-909" set, "Sound
  Canvas" modes) are Roland's published names for the slots a MIDI file
  calls for: identification, the same argument -- and our rule already
  (no-roland-sounds: Roland's NAMES only, never its sounds).
- **The disclaimer** (Credits screen, About, the store listing, the manual),
  after the established form (Line 6's):

  > All product names, trademarks and registered trademarks are the property
  > of their respective owners, who are in no way associated or affiliated
  > with Clavitone. They are used solely to identify the instruments whose
  > sounds were studied in building our models, and the MIDI standards'
  > named sounds a file asks for.

- **The marks, as of 2026-11-22** (counted in ui/about.json, ui/app.js,
  ui/help.js, nui/*.h, patch_map.py, percussion_map.py; owners to confirm
  before sale -- several have changed hands):
  - Roland: Roland, GS, Sound Canvas, SC-55/88/8850, MT-32, CM-64/32L,
    TR-808/909/707/606, TR-8, CR-78, Jupiter, Juno, JC-120.
  - Hammond: Hammond, Leslie.
  - Wurlitzer, Spectra-Tone; Rhodes; Fender, Stratocaster, Telecaster;
    Gibson's Les Paul; Hohner, Clavinet; Yamaha, CP-80 (one stale CP-70);
    Moog, Minimoog, Messenger; Simmons, SDS-V; Steinway; Mellotron; Oberheim;
    Vox; Fairlight.
  - Plain words, not marks: bandoneon, theremin, General MIDI (the MMA's
    standard's name). GeneralUser GS is a credited soundfont's name.
- **To fix before sale (labels that ARE the mark):**
  - Speaker choices: LESLIE, HAMMOND, JC-120, SPECTRA-TONE, ST CHORUS
    (patch_map.CAB_LABELS; nui/amp.h's headings "LESLIE", "SPECTRA-TONE").
    Give each a generic label (ROTARY, CONSOLE, TWIN 12, ROTATING CONES,
    CONES + CONSOLE) and say "after the Leslie 122" in its help text.
  - The "Moog" engine and card: call it what it is (the ladder synth; the
    Messenger card "after the Moog Messenger") -- the hardware Messenger
    itself, connected by MIDI, may be named: that is identifying a device.
  - Voice and patch names coined by us (not GS map names) that start with a
    mark: list and rename descriptively.
- **DONE 2026-11-22 (Ben: "do the trademark label pass"):**
  - Speaker choices: ROTARY, SPINET, 2x12 CLEAN, LID PAIR, CONE ROTOR, ROTOR
    CHORUS (patch_map.CAB_LABELS; both UIs' headings and notes); each
    one's words "after the Leslie 122" / "after a Hammond spinet's" / ...
  - Pickup panels: Three single coils, Two humbuckers, Two-coil bass,
    Keyboard, two pickups (PICKUP_FAMILIES; each with its "after"); the
    help's terms "After the Fender Stratocaster: ..." and so on.
  - Our variation 16.41: "60's Lower" (was "Wurlitzer Lower").
  - The picker's words (about.json, gm_coverage.referential): "Moog: ..."
    is "ladder synth: ..." (396), a sound led by a maker's name reads
    "after the ..." (183). The tables keep their shorthand; GS's own names
    are untouched (identification).
  - The disclaimer, in the Credits topic (both UIs).
- **DONE 2026-11-23 (Ben: "L13 next"):**
  - A maker's name is never a plain noun in our words. Help: "an organ's
    rotary speaker" (not "Leslie"), "the tine / reed electric piano", "a
    clav"; the speaker choices listed by their labels with each one's
    "after" (ROTARY after the Leslie 122, 2x12 CLEAN after the Roland
    JC-120, CONE ROTOR after the Wurlitzer Spectra-Tone, ...); the pickup
    switches "drawn after" the Stratocaster's, Jazz Bass's and Clavinet's.
    Pickers: "rotary slow/fast", "orchestra hit + drawbar organ", "after the
    TR-808: its mid tom", the terminal picker's "(after the Rhodes)"; GM
    program 7 is GM 1's own name, "Clavi".
  - THE CHECK: `examples/gm_coverage.py --about` fails on a mark used as a
    plain noun in the pickers' words (NOUN_MARKS, bare_marks); GS's drum
    names ("909 Snare 1") are identification and pass.
  - The synth panel's heading in both terminal UIs: "SYNTH" (was "MOOG
    MESSENGER"); the touch card was already SYNTH. "The Messenger" stays
    where it names the connected hardware (Setup, its CC mode): identifying
    a device.
  - THE MESSENGER CARD, the facts for a lawyer: the sections and their
    controls' places follow the Messenger's panel (LFO 1 with the left
    hand, oscillators, mixer, filter, envelopes; nui/synth.h, ui/app.js);
    everything drawn is ours -- our knobs with scopes, segmented switches,
    our theme, colours and fonts; no logo, artwork, lettering or wood; the
    controls carry generic function names. Whether the arrangement alone is
    trade dress is the lawyer's call.
  - THE OWNERS (web research 2026-11-23, mostly through USPTO mirrors --
    each to be checked in TSDR before sale):
    - Roland Corporation: Roland and its model names (GS, Sound Canvas,
      SC-55/88/8850, MT-32, CM-64/32L, TR-808 (US Reg. 6082363), 909, 707,
      606, TR-8, CR-78, Jupiter, Juno, JC-120, TB-303, SH-101, D-50).
    - Suzuki Musical Instrument Mfg. (Hammond Suzuki): Hammond, Leslie.
    - Wurlitzer: the family's brand company won the music and electronics
      categories back in 2021 (from Gibson/Baldwin); the current US
      registration for pianos and organs is unconfirmed. Spectra-Tone: its
      US registration expired 1984 (no owner).
    - Rhodes: Rhodes Music Group Ltd runs the brand (relaunch 2021); the US
      registration still lists the Joseph Brandstetter Trust. "Fender
      Rhodes" expired.
    - Fender Musical Instruments Corp.: Fender, Stratocaster, Telecaster,
      Jazz Bass, Precision Bass. Gibson Brands: Gibson, Les Paul.
    - Hohner: Hohner; Clavinet's US registration was cancelled in 2020.
    - Yamaha Corporation: Yamaha, CP-80, CS. Hoshino Gakki: Ibanez.
    - Moog Music Inc. (inMusic since June 2023): Moog, Minimoog, Messenger.
    - Simmons: Guitar Center (GTRC Services) since 2005-07.
    - Steinway Musical Instruments (Paulson & Co. since 2013).
    - Mellotron: Markus Resch on the US register (one museum page says
      otherwise: confirm). Oberheim: Tom Oberheim (returned 2019/2021).
    - Vox: Korg (Vox Amplification Ltd, since 1992). Fairlight: Blackmagic
      Design most likely (bought 2016; confirm in TSDR).
    - General MIDI: the MIDI Association and AMEI's specification; only its
      logos are claimed (we show none) -- say "the General MIDI
      specification", not a trademark.
- **Still open:** the store listing's and manual's copy of the disclaimer
  (neither is written yet: paste the paragraph above), the owners' TSDR
  check, and the lawyer's look at the whole (this section, the Messenger
  card's layout).

## Recording our own

- **Roland hardware:** a recording of a Roland machine PLAYING, made by its
  owner under a proper open licence, may be fitted. Data extracted from a
  Roland (ROM dumps, its factory samples) may not, and the voices of the
  sample-ROM machines (the TR-707, the 909's cymbals, the Sound Canvas) stay
  doubtful.
- **Ben's Wurlitzer organ (with pedals):** a transistor home organ we can
  record ourselves, and own outright. It suits the electric organs that
  aren't tonewheels: 60'sOrgan 1-3, Farf Organ, CheeseOrgan (all borrowing
  the tonewheel model today), Organ Bass from its pedals, and its own
  percussion and rotating speaker if it has them. It doesn't replace the
  Hammond L102's drawbars (a different generator), but a recording session
  could also take its percussion decay and vibrato.
- **Biwa, rubab, 4' harpsichord, real 808/909:** a player or an owner,
  recorded and released by us, closes each for good.

## About YouTube sources

A CC BY licence on YouTube is set by the uploader, who isn't always the
performer (the note says when). Downloading is also subject to YouTube's own
terms, and the audio is lossy, so fit below about 15 kHz.

## Corrections to the notes

- Freesound shows newer licences than the notes record: mrshoes (pan flute),
  UncleSigmund (shakuhachi) and reinsamba (cuica) are CC BY 4.0, not 3.0;
  luis_audp's uilleann pipes are CC BY 3.0.
- Two of the three jungle-roll takes (smileylovers 161427, a deleted user's
  347581) are CC BY 3.0, not CC0, and need credit.

## Not a problem for the app (recorded so nobody re-checks)

- **The Sankey corpus** (Bach MIDI, John Sankey): personal use; audio must
  come from his soundfont. It feeds demo renders, not the app. The `sankey`
  tuner reproduces a temperament (Werckmeister III), which is not his work.
- **Pergolesi, Stabat Mater** score (CC BY-NC-SA): a demo render only.
- **Roland**: names only, used nominatively (what a GS file asks for); no
  Roland module or sample was fitted (memory: no Roland sounds).
