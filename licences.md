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

The register of every source is `credits.py`; `examples/gm_coverage.py
--about` writes the Credits page from it, and fails if a voice's notes name a
source the register doesn't hold.

## Open issues

Status: `open` until the voice is refitted to an open source, the rights
holder grants commercial use in writing, or the voice is left out of the
store build.

### L1. Electric Piano 1 (Rhodes): jRhodes3d — CC BY-NC (samples)

- **Source:** Jeffrey Learman's jRhodes3d, a 1977 Mark I recorded off the harp
  connector. The samples are CC BY-NC; the control files and clips are CC0, and
  "music made with it" is CC0, but that clause covers music, not a model.
- **What derives from it:** `tonelib` Rhodes fit (`examples/rhodes_fit.py`),
  the EP register levels, and the cabinet notes that cite it.
- **Status:** open.
- **Alternatives (checked 2026-11-20):**
  1. tim.kahn, "C_S Fender Rhodes Mark II", Freesound pack 3957, CC BY 4.0:
     53 notes from E1, ~12 s each, a Mark II Stage 73 through a Bellari tube
     preamp. One dynamic. The only open full-range Rhodes found: fits the
     spectrum and decay per note, not the velocity law.
  2. NSynth (CC BY 4.0) keyboard_electronic notes: five velocities, but 16 kHz
     and 4 s, instruments unnamed. For checking a velocity law only.
  - Rejected: Pianobook's "Matt's Fender Rhodes" (ideal, DI; no licence
    stated), Keenan's Rhodes bass (CC0, an emulation, C4-E6 only).

### L2. Electric guitars (GM 26-31): Fraunhofer IDMT-SMT-Guitar — CC BY-NC-ND 4.0

- **Source:** Fraunhofer IDMT's guitar set, DI, the Ibanez 2820 neck humbucker.
- **What derives from it:** the electric guitars' string, pickups, mute and
  harmonics (`JazzGuitar` and the clean, muted, overdriven, distortion and
  harmonics programs that share it; `examples/egtr_fit.py`).
- **Status:** open. ND as well as NC: even a research licence wouldn't allow
  an adaptation.
- **Alternatives (checked 2026-11-20):** no open hollow-body set exists.
  1. Guitar-TECHS (Zenodo 14963133, CC BY 4.0): 138 single notes per player,
     true DI at 48 kHz; an EVH Wolfgang on the NECK HUMBUCKER (solid body) and
     an Ibanez PF300 on the bridge. The neck humbucker is the jazz pickup; the
     hollow body's resonance would stay our model's.
  2. FreePats "Clean Electric Guitar" (CC0): a Fender, bridge pickup, DI.
  - Rejected: MedleyDB (CC BY-NC-SA), EGDB (no licence), IDMT effects set.

### L3. Electric basses (GM 33, 34, 36, 37): Fraunhofer IDMT-SMT-Bass — CC BY-NC-ND 4.0

- **Source:** Fraunhofer IDMT's bass set, DI, three basses.
- **What derives from it:** `FingeredBass` and the picked and slap basses
  built on it (`examples/egtr_fit.py`).
- **Status:** open.
- **Alternatives (checked 2026-11-20):**
  1. quartertone, "BassGuitar-GretschElectromatic-multisampled", Freesound
     pack 14708, CC BY 4.0 (spot-check each note's licence): 250 finger-plucked
     notes, 8 velocity layers, direct to disk, 48 kHz. Tails past ~4 s are
     crossfade loops. A 30.3" short scale: check inharmonicity.
  2. FreePats "Clean Electric Bass" (CC0): a Yamaha RBX, fingered set; a
     long-scale second source if its notes are dry.
  - Rejected: Pianobook "Low Fat Bass Clean" (ideal; no licence stated).

### L4. Biwa Stroke (GS 120.12): PARADISEC HDF1-SB33 — CC BY-NC-SA 4.0 and access conditions

- **Source:** Hugh de Ferranti's satsuma biwa recordings at PARADISEC. The
  access conditions say commercial enterprises may not include the data in
  models, beyond the NC licence.
- **What derives from it:** `tonelib.BiwaProperties` (`examples/pluck_fit.py
  --voice=biwa`). The audio stays local and is never sent anywhere.
- **Status:** open.
- **Alternatives (checked 2026-11-20):** nothing open fits a model. The only
  open biwa audio is 23 s of compressed video ("Biwa intro - 2022 8 31",
  Wikimedia Commons, CC BY 3.0), enough to check the sawari buzz, not to fit
  decays. Freesound, archive.org and Europeana hold none under an open licence.
  The way out is a new recording: single plucks by a player, released CC0.

### L5. The 27 measured raga tunings: Saraga 1.5 Hindustani — CC BY-NC-SA 4.0

- **Source:** the CompMusic Saraga dataset (Zenodo 4301737), its recordings'
  pitch, by `examples/saraga_swaras.py`.
- **What derives from it:** the `saraga_*` tunings in `ragas.py`, shown on the
  Tuning card under their raga names. These are tables taken straight from the
  data, the most direct derivation of any issue here.
- **Status:** open. Bel's Todi, just, Pythagorean and equal don't depend on it.
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

### L6. Rabab (GS 105.8): a Freesound upload that is a GarageBand loop — doubtful CC0

- **Source:** belamalta10's "3 continents" (Freesound 513846), uploaded as CC0,
  but its rubab opening is an Apple GarageBand loop. Apple's loops may be used
  in music but not redistributed as loops, and the uploader couldn't put them
  under CC0, so the CC0 is not the uploader's to give.
- **What derives from it:** the rabab's numbers (`examples/rabab_fit.py`).
- **Status:** open.
- **Alternatives (checked 2026-11-20):** none clean. archive.org's
  "Acoustic String Instrument Sample Library" (CC BY 4.0) is deliberately
  lo-fi, of unknown origin, labelled "Mongolian rubab"; Barcroft45's "Rabab
  (Take 2)" (CC BY-SA 3.0, Jamendo) needs a listen to say what it is; the
  "CC0" uploads of Ustad Shaida are archival recordings a third party can't
  release. The way out is a new recording, as for the biwa.

### L7. Fourteen Pianobook libraries — Pianobook's terms forbid it

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
  - Electric Piano 2 (Wurlitzer 200A, BaltiWurli);
  - Electric Grand (David's CP-70; its SFZ key map is CC BY 4.0, the samples are not);
  - Dulcimer (Lite Hammered Dulcimer);
  - the harpsichord's upper 8', 4' and lute (Harpsimachord);
  - the tonewheel organ's 16', 5 1/3', 1 3/5', percussion and speaker (Hammond L102);
  - Church Bell (St Kathrin's bell);
  - Hawaiian Guitar (lap steel); 12-string Guitar (Fender 12 String);
  - Mandolin (Eclectic Mandolin); Taisho Koto (Taishogoto); Gopichant (The Ektara);
  - Flugel Horn (Dusty Flugelhorn);
  - Guitar Feedback (Gretsch Feedback and Feedbacker).
- **Status:** open, and the largest issue by count. Each samplist can grant
  permission; otherwise each voice needs another source. Alternatives not yet
  researched.

### L8. Choir (GM 52, 53): Dagstuhl ChoirSet — CC BY-NC-SA 4.0

- **Source:** every version on Zenodo is CC BY-NC-SA 4.0. The choir's
  coverage note gave only VocalSet's CC BY 4.0, which read as covering both;
  it now names Dagstuhl's own licence.
- **What derives from it:** the choir section's spread, each singer's detune
  and vibrato. The voice itself is fitted to VocalSet (CC BY 4.0), which is
  fine.
- **Status:** open. Alternatives not yet researched.

### L9. Percussive Organ (GM 17): Indiginus Real Rotor Organ — EULA

- **The terms:** "You may not use the samples in this library to create and
  distribute any other sample pack or product."
- **What derives from it:** the B3 percussion tap's 2nd and 3rd harmonic decay.
- **Status:** open.

### L10. No licence stated (all rights reserved by default)

- **Debain harmonium** (Jean-Pierre Silvestre's Hauptwerk set): the reed
  organ's registers (GS 20). His address is in the set's PDF; ask him.
- **Aalto clavinet** recordings: the Clavinet (GM 7). Ask the authors.
- **TR-606** (Ed Vargo's set): the TR-606 kit; and bdu's Freesound TR-606
  pack, a third party's re-upload under CC0.
- **TR-808** (Fischer's set): "ABSOLUTELY FREE", but no licence. The TR-808
  kit, and the 808 voices other sets borrow.
- **TR-707** (hyperreal): an anonymous uploader's "public domain".
- **Status:** open. Low risk for measured numbers, but a written yes is
  cheap to ask for.

### L11. TR-909 (Rob Roy / Jason Baker set) — "not for profit, no modification"

- **What derives from it:** the TR-909 kit, its cymbals by the ROM cymbal fit.
- **Status:** open.

### L12. Smaller questions

- **Ross harpsichord voicing** (`ross.sf2`, John Sankey): no licence for the
  soundfont. It feeds an optional voicing (`TUNING_HARPSI=ross`); leave it out
  of the store build or ask.
- **TimGM6mb** (GPL-2): one of the references in the Orchestra Hit fit. Fitted
  numbers are unlikely to be a derivative work; easy to drop from the fit.
- **GeneralUser GS**: its licence says some samples' origins are unknown. It
  sets levels (fine); where a voice was fitted to one of its samples (the
  Orchestra Hit, the Simmons hit picks) check that sample.
- **VSCO 2 CE's upright piano** (Ivy Audio): its Info.txt grants
  redistribution through Versilian rather than restating CC0. Credit both.
- **CC BY-SA** (the Piteå organ, the oud and traverso Commons files): see the
  share-alike question above.

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
