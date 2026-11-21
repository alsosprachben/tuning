# The Electric Grand's refit to Greg Sullivan's CP80 (2026-11-20)

The working scripts behind `tonelib.ElectricGrandProperties` as banked. Run them from the tuning root, as `python3 examples/cp80_refit/NAME.py ...`. They use `examples/upright_fit.py --ref=cp80`'s readers.

**Measuring and scoring**
- `cp80_score.py VARIANT`: the spectrum, T20 decay and attack measures. Its `GRAND` list names what the voice now takes from the grand.
- `cp80_knock.py`: the attack's sub-fundamental thump and the noise between harmonics, recording against ours.
- `cp80_bass.py`, `cp80_lp.py`: the third-octave balance in the bass, and of the hard layer.
- `cp80_room.py`: the colour by absolute frequency, recording minus ours, from every partial. This is what showed the 790 Hz dip.

**Fitting**
- `cp80_knockfit.py DBS`: the knock's fall rate, with the strike table refitted at each value.
- `cp80_grandfit.py PARAMS MAXFEV`: the spectrum fit on the grand-based model. Settings come in through the `SETV`, `PH` and `SG` environment variables.
- `cp80_strings.py VALUES GAINS`: the second string's level against the takes' beating.
- `cp80_eqfit.py`: the dip and roll-off, fitted to `cp80_room.py`'s curve. It renders nothing.

**Listening**
- `cp80_variant_ab.py OUT.wav`: the A/B of the version banked here.
