"""The stream's two fallbacks, forced (no file reaches either today):

1. a harmonium (GM 20, two reeds and its Tremolo stop drawn) whose stop
   sounds at two settings on one channel -- the keys from middle C up a voice
   of its own rate and depth -- streamed and whole, byte for byte, and each
   row's sidebands at its own note's rate, not the channel's last note's;
2. a chorus channel whose partials all sit where no copy fits under Nyquist:
   its dry share comes down all the same, in chorus.expand and the stream's
   _chorus alike.

    python3 examples/streamfallback_check.py      (from the repo root)
"""
import math
import os
import sys

import numpy as np

HERE = os.getcwd()
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import blockrender as B                                 # noqa: E402
import streamrender as S                                # noqa: E402
import streamcheck as SC                                # noqa: E402

def _harmonium_file(path):
    """the harmonium's file: CC43 cor anglais + flute, CC44 the Tremolo (bit
    11), notes below and above middle C overlapping"""
    import mido
    mf = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.Message('program_change', channel=0, program=20))
    tr.append(mido.Message('control_change', channel=0, control=43, value=1 | 16))
    tr.append(mido.Message('control_change', channel=0, control=44, value=16))
    ev = []
    for j, (k, d) in enumerate(((48, 1400), (64, 900), (55, 1200), (67, 1000), (52, 700), (72, 1300))):
        ev.append((240 + j * 420, 1, mido.Message('note_on', channel=0, note=k, velocity=90)))
        ev.append((240 + j * 420 + d, 0, mido.Message('note_on', channel=0, note=k, velocity=0)))
    ev.sort(key=lambda e: (e[0], e[1]))
    now = 0
    for t, _, m in ev:
        tr.append(m.copy(time=t - now))
        now = t
    tr.append(mido.Message('note_off', channel=0, note=60, time=960))
    mf.save(path)


bad = 0
# ---- 1. the harmonium ----
import tonelib as T                                     # noqa: E402
base = B.property_class_for_note
Hi = type("ReedOrganHiTrem", (T.ReedOrganFreeProperties,), dict(stop_tremolo_hz=6.3, stop_tremolo_depth=0.41))


def two(prog, key, *a, **k):
    c = base(prog, key, *a, **k)
    return Hi if c is T.ReedOrganFreeProperties and key >= 60 else c


B.property_class_for_note = two
import tremolo as TR                                    # noqa: E402
_exp = TR.expand
rates = set()


def rec(A, channels, sr, cols, rows=None, meta=None, cfgs=None):
    for c in (cfgs or ()):
        if c is not None:
            rates.add(tuple(c[:2]))
    return _exp(A, channels, sr, cols, rows=rows, meta=meta, cfgs=cfgs)


TR.expand = rec
import tempfile                                         # noqa: E402
f = os.path.join(tempfile.mkdtemp(), "harmonium.mid")
_harmonium_file(f)
# THE MIX, streamed and whole (streamcheck's own comparison; the send is
# streamcheck's to judge)
Ls, Rs, st_ = S.render(f, "hybridmean:440", send=True)
p_ = B.prepare(f, "hybridmean:440")
Lw, Rw = B.synth_window(p_, 0, p_['N'])
ok = Ls.tobytes() == Lw.tobytes() and Rs.tobytes() == Rw.tobytes()
print("harmonium, two tremolos on a channel: %d rows; streamed and whole: mix %s"
      % (p_['P'], "identical" if ok else "DIFFERS"))
TR.expand = _exp
print("   the notes' settings, whole and streamed: %s" % sorted(rates))
if len(rates) < 2:
    print("   (the file did not sound the stop at both settings: no test)")
    bad += 1
bad += not ok
B.property_class_for_note = base
# ...and the rows' own settings, read directly: two rows on one channel at two
# rates, each row's sidebands at its own (the whole table and the stream both
# pass through expand, so their agreeing above does not show this)
srr = float(B.SR)
tc = ["om", "nf", "p0", "p0R", "aL", "aR", "aM", "vd", "vr", "vp", "mch", "non"]
TA = {k: [0.0, 0.0] for k in tc}
TA["nf"] = [440.0, 880.0]
TA["om"] = [2.0 * math.pi * f / srr for f in TA["nf"]]
TA["aL"] = [0.5, 0.5]; TA["aR"] = [0.5, 0.5]; TA["aM"] = [0.5, 0.5]
TA["mch"] = [0, 0]
c1, c2 = (5.0, 0.3, 0.0), (6.3, 0.41, 0.0)
TR.expand(TA, {0: c2}, srr, tc, cfgs=[c1, c2])
side = sorted({round(abs(o - TA["om"][j]) * srr / (2.0 * math.pi), 6)
               for o in TA["om"][2:] for j in range(2) if abs(abs(o - TA["om"][j]) * srr / (2.0 * math.pi) - 5.65) < 1.0})
print("   rows' own rates, read directly: sidebands at %s Hz" % side)
bad += side != [5.0, 6.3]

# ---- 2. the chorus, no copy under Nyquist ----
import chorus as CH                                     # noqa: E402
sr = float(B.SR)
n = 6
cols = ["om", "nf", "p0", "p0R", "aL", "aR", "aM", "vd", "vr", "vp", "mch", "non"]
nf = np.full(n, 0.4999 * sr)                            # (up a few cents: past Nyquist)
A = {k: [0.0] * n for k in cols}
A["nf"] = list(nf)
A["om"] = list(2.0 * math.pi * nf / sr)
A["aL"] = [0.5] * n; A["aR"] = [0.25] * n; A["aM"] = [0.3] * n
A["mch"] = [0] * n
spec = {0: (0.5, (6.0, 9.0))}
made = CH.expand(A, spec, sr, cols)
want = 0.5 * (1.0 - 0.5) ** 0.5
print("chorus, no copy under Nyquist: %d copies; dry %s" % (made, "down" if A["aL"][0] == want else "UNCHANGED"))
bad += made != 0 or A["aL"][0] != want
st = S.Stream.__new__(S.Stream)
st.B = B
st.made, st.dried = {}, set()
part = {k: np.array([0.0] * n) for k in cols}
part["nf"] = nf.copy(); part["om"] = 2.0 * math.pi * nf / sr
part["aL"] = np.full(n, 0.5); part["aR"] = np.full(n, 0.25); part["aM"] = np.full(n, 0.3)
part["mch"] = np.zeros(n, np.int64)
part["key"] = np.zeros((n, 4), np.int64); part["klen"] = np.full(n, 4, np.int64)
st._chorus([part], spec)
same = part["aL"][0] == A["aL"][0] and part["aR"][0] == A["aR"][0] and part["aM"][0] == A["aM"][0]
print("   ...the stream's _chorus the same: %s" % ("yes" if same else "NO"))
bad += not same
print("%d failed" % bad)
sys.exit(1 if bad else 0)
