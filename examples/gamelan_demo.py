"""The SC-8850's Gamelan sets (programs 55 and 56; percussion_gs.SELISIR) in a
kebyar-like texture, played once in Gamelan 1 (UNT's own pelog selisir) and
again in Gamelan 2 (the same, equal-tempered): an eight-beat gong cycle --
the gong wadon opening it, the lanang every other, the kempur at its middle,
the kajar on every beat -- the pokok on the jublag, the jegogan on every
other tone, the penyacah an octave up, the pemade's two parts interlocking in
sixteenths (polos and sangsih), the reyong off the beat, the kendang wadon and
lanang interlocking with the kelontuk's strokes, the ceng-ceng driving, the
kopyak's accents. Writes OUT/gamelan.wav (and _room.wav).

    python3 examples/gamelan_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

TEMPO = 104.0
CYCLE = 8
CYCLES = 4
# the pokok, as the jublag's key index (0-4), one tone a beat
POKOK = (1, 3, 4, 2, 0, 2, 3, 1)
# each instrument's lowest key
JEGOGAN, JUBLAG, PENYACAH, PEMADE, REYONG = 50, 55, 60, 67, 77


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / TEMPO), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    ev = []

    def hit(b, n, v, dur=0.4):
        ev.append((b, 1, n, v))
        ev.append((b + dur, 0, n, 0))
    sec = CYCLE * CYCLES + 4
    for s, prog in enumerate((54, 55)):
        s0 = s * sec
        ev.append((s0 - 0.5, 2, prog, 0))
        for c in range(CYCLES):
            c0 = s0 + c * CYCLE
            hit(c0, 43 if c % 2 == 0 else 44, 110, 3.0)
            hit(c0 + CYCLE / 2, 49, 96, 2.0)
            for b in range(CYCLE):
                t = c0 + b
                m = POKOK[b]
                m2 = POKOK[(b + 1) % CYCLE]
                hit(t, 48, 72)
                hit(t, JUBLAG + m, 92, 0.9)
                hit(t, PENYACAH + m, 80, 0.9)
                if b % 2 == 0:
                    hit(t, JEGOGAN + m, 100, 1.8)
                # the pemade's kotekan: the four sixteenths' tones, polos on
                # the 1st and 3rd, sangsih on the 2nd and 4th
                line = (m + 5, min(m + 6, 9), m + 5, min(m2 + 5, 9))
                for q, k in enumerate(line):
                    hit(t + q * 0.25, PEMADE + k, 86 if q % 2 == 0 else 78, 0.3)
                # the reyong off the beat, two kettles
                hit(t + 0.5, REYONG + m + 4, 82, 0.3)
                hit(t + 0.5, REYONG + min(m + 6, 11), 76, 0.3)
                # the kendang: the wadon on the beat, the lanang between
                hit(t, 36, 96 if b % 2 == 0 else 80)
                hit(t + 0.5, 37, 88)
                if b % 4 == 3:
                    hit(t + 0.75, 40, 84)
                    hit(t + 0.25, 41, 74)
                if b == CYCLE - 1:
                    hit(t + 0.75, 38, 100)
                if c % 2 == 1 and b == 2:
                    hit(t + 0.5, 39, 90)
                if b == 5:
                    hit(t + 0.25, 42, 80)
                # the ceng-ceng's sixteenths, the beat accented
                for q in range(4):
                    hit(t + q * 0.25, 45, 88 if q == 0 else 60, 0.15)
            hit(c0 + 3.5, 47, 96, 0.1)
            hit(c0 + 7.5, 46, 104, 1.0)
        hit(s0 + CYCLES * CYCLE, 43, 112, 3.5)
        hit(s0 + CYCLES * CYCLE, JEGOGAN + POKOK[0], 100, 3.0)
    ev.sort(key=lambda e: (e[0], e[1] != 2, e[1]))
    now = 0
    for beat, kind, n, v in ev:
        tk = int(round((beat + 0.5) * 480))
        if kind == 2:
            m = mido.Message("program_change", channel=9, program=n, time=tk - now)
        else:
            m = mido.Message("note_on", channel=9, note=n, velocity=v, time=tk - now)
        tr.append(m)
        now = tk
    tr.append(mido.MetaMessage("end_of_track", time=480 * 6))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "gamelan.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
