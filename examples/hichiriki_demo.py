"""GS 111.16 Hichiriki in gaijinbuzz's phrases (Freesound 680565, CC0): each
phrase from silence, then slurred on (the next note starts before the last
lets go, which blockrender reads as legato) -- E5 to D5, D5 up to E5, E5 down
to D5 and C#5. Writes OUT_DIR/hichiriki_phrases.wav (and _room.wav), and
prints ours' pitch at each note's start: the enbai, 230 cents under, on a
phrase's first note and on no slur.

    python3 examples/hichiriki_demo.py OUT_DIR
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
from efx_demo import _sx     # noqa: E402

# (start s, MIDI note, length s): phrases with a breath between
PHRASES = [[(0.0, 76, 3.8), (3.8, 74, 3.0)],
           [(7.6, 74, 2.0), (9.6, 76, 3.0)],
           [(13.4, 76, 2.4), (15.8, 74, 1.0), (16.8, 73, 2.6)]]
SLUR = 0.03     # each slurred note overlaps the last by this much


def phrase_file():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))                      # GS reset
    tr.append(mido.Message("control_change", channel=0, control=0, value=16))
    tr.append(mido.Message("control_change", channel=0, control=32, value=3))
    tr.append(mido.Message("program_change", channel=0, program=111))
    ev = []
    for ph in PHRASES:
        for k, (t, n, d) in enumerate(ph):
            ev.append((t, 1, n))
            ev.append((t + d + (SLUR if k + 1 < len(ph) else 0.0), 0, n))
    ev.sort()
    now = 0.0
    for t, on, n in ev:
        dt = int(round((t - now) * 960))
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100 if on else 0, time=dt))
        now += dt / 960.0
    return mf


def pitch_at(x, sr, t, f, secs=0.6):
    """Ours' fundamental, cents re f, every 50 ms from t."""
    out = []
    win = int(0.05 * sr)
    N = 1 << 16
    ff = np.fft.rfftfreq(N, 1 / sr)
    band = (ff > f * 0.8) & (ff < f * 1.12)
    for k in range(int(secs / 0.05)):
        s = int((t + k * 0.05) * sr)
        Y = np.abs(np.fft.rfft(x[s:s + win] * np.hanning(win), N))
        out.append(1200 * np.log2(ff[band][np.argmax(Y[band])] / f))
    return out


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(phrase_file())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    x = 0.5 * (L + R)
    for ph in PHRASES:
        for k, (t, n, d) in enumerate(ph):
            f = 440.0 * 2 ** ((n - 69) / 12.0)
            print("  %5.2f s %s %d: %s" % (t, "phrase" if k == 0 else "slur  ", n,
                                           " ".join("%+.0f" % c for c in pitch_at(x, B.SR, t, f))))
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "hichiriki_phrases.wav")
    B.write_wav(f, L * g, R * g)
    fr = os.path.splitext(f)[0] + "_room.wav"
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f, fr], check=True,
                   stdout=subprocess.DEVNULL)
    print("  " + fr)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
