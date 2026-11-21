
## The afternoon (2026-11-21): case modes, lid, decay, strike curve, phase

Baked into `tonelib.GrandPianoProperties` ("THE GRAND, FURTHER"). The measures:
`case_modes_measure.py` / `modes_by_key.py` (the case's modes: `gring2.txt`),
`knock_bright_grid.py` (the soft bass's knock: `gkvp1.txt`), `grand_by_hz.py`
(the lid: every register short at 1-8 kHz, in Hz), `band_env.py` /
`decay_env_fit.py` (each band's beat-averaged level over 3 s: highs sustain,
the treble's drain), `swell_probe.py` (the unison pumping the bass),
`robust_ladder.py` / `ladder_score2.py` / `strike_fit2.py` (partial ladders
with f0 and B searched together -- the old ladder lost the bass's partials;
the strike curve), `phaser_probe3.py` / `sweep_track.py` / `inharm_resid.py`
(the one-way sweep: the hammer's phase, and partials off the stiff law by
their own ~0.5 cent), `bass_bright.py` / `tenor_noise.py` (the loud tenor's
snare: the worn layer back to 10^18), `levels_vs_gu.py` (`gpts1.txt`).
