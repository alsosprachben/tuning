#!/usr/bin/env python3
"""The peak a six-string strum at velocity 100 makes into the valve (guitar.py
--calibrate's measure), per GM program: OLD=<dir holding an older tonelib.py and
patch_map.py> to measure those. A refit that changes a guitar's spectrum
holds this peak by its initial_gain, so the amplifier is driven as voiced.

    python3 examples/calib_peak.py 29 30
"""
import os, sys, io, contextlib, tempfile
if os.environ.get("OLD"):
    sys.path[:0] = [os.environ["OLD"], "."]; import tonelib, patch_map; print(tonelib.__file__)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(HERE, "examples")); sys.path.insert(1, HERE)
import guitar as G, tubeamp as TA
out=tempfile.mkdtemp()
for prog in map(int, sys.argv[1:]):
    st={}
    orig=TA.emit
    def emit(*a, **k):
        r=orig(*a, **k); st.update(k.get('stats') or {}); return r
    TA.emit=emit
    with contextlib.redirect_stdout(io.StringIO()):
        G._calib_one(out, prog, "g%d"%prog, G.BIG_CHORD)
    TA.emit=orig
    print(prog, "%.6g" % st['peak'])
