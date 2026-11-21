# The new upright (GM 1, and GM 3 by inheritance), 2026-11-21

Fitted against VSCO's upright takes; levels against GeneralUser GS's upright.
Values as baked into `tonelib.UprightPianoProperties`:

- `upright_final.setv`: the hammer (joint fit, Powell: `grand_hammer_fast.py`
  with `W_ABS=1 METHOD=powell`), the board, the decay (`decay_fit_any.py`).
- `velpts1.txt`: `hammer_vel_power_points` (`vel_growth.py`).
- `upright_pts4.txt`: `hammer_level_points` (`levels_vs_gu.py`, secant steps).
- `ring3.txt`: the case modes, `ring_db` with `ring_tuned = False`
  (`cabinet_low.py` finds them, `case_modes_measure.py` fits them; `cm_rec.txt`
  is the takes' reading).
- `ktab1.txt`, `kvp1.txt`: the knock by register (`knock_bright_grid.py`).

The scripts ran from the tuning tree's root with these files one level up
(`../`); `grand_noise.py` is the attack measures they share.
