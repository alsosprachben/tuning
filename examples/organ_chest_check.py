#!/usr/bin/env python3
"""The chest's wind, measured on a held pipe: the Tremulant, and the sag.

    python3 examples/organ_chest_check.py [WIND] [--keep DIR]

Two renders on the church organ (program 19), dry and register off, and the
held pipe's fundamental tracked through them (its instantaneous frequency
and level, by a band around it):

  tremulant   principal 8 and the Tremulant (bit 13) on a held A4: the swing's
              rate, its depth in cents and dB, and that pitch and level move
              together (pressure up: sharp and louder).
  sag         a held F#4 on the plenum (WIND, default 1), and at 1.5 s a
              five-note chord low in the bass: the pitch the chord's draw
              pulls from the held pipe, at its deepest and once settled.

What to expect is wind.py's arithmetic -- a flue goes as p**0.0375 -- so the
printout gives both. The numbers the model starts from are for the ear.
"""
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def score(path, bits, chord_at=None, chord=(), held=69):
    import mido
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", program=19, time=0))
    t.append(mido.Message("control_change", control=11, value=bits & 0x7F, time=0))
    t.append(mido.Message("control_change", control=43, value=(bits >> 7) & 0x7F, time=0))
    t.append(mido.Message("note_on", note=held, velocity=100, time=10))
    now = 10
    if chord_at is not None:
        tk = int(chord_at * 960)
        for i, n in enumerate(chord):
            t.append(mido.Message("note_on", note=n, velocity=100, time=(tk - now) if i == 0 else 0))
        now = tk
    end = 4 * 960
    t.append(mido.Message("note_off", note=held, time=end - now))
    for n in chord:
        t.append(mido.Message("note_off", note=n, time=0))
    m.save(path)


def render(mid, wav, wind):
    env = dict(os.environ, TUNING_REFLECT="0", TUNING_WIND=str(wind), TUNING_REGISTER="0")
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, wav, "even"],
                   env=env, check=True, stdout=subprocess.DEVNULL)


def track(wav, f0, band=0.03):
    """The held pipe's frequency (cents re its median) and level (dB) per sample."""
    from scipy.signal import butter, sosfiltfilt, hilbert
    w = wave.open(wav)
    sr, n, sw, ch = w.getframerate(), w.getnframes(), w.getsampwidth(), w.getnchannels()
    raw = w.readframes(n)
    if sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        x = ((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) << 8 >> 8).astype(float)
    else:
        x = np.frombuffer(raw, {2: np.int16, 4: np.int32}[sw]).astype(float)
    x = x.reshape(-1, ch).mean(1)
    sos = butter(4, [f0 * (1 - band), f0 * (1 + band)], btype='band', fs=sr, output='sos')
    a = hilbert(sosfiltfilt(sos, x))
    f = np.diff(np.unwrap(np.angle(a))) * sr / (2 * np.pi)
    return sr, f, 20 * np.log10(np.abs(a)[1:] + 1e-12)


def main(argv):
    a = [x for x in argv[1:] if not x.startswith("--")]
    wind = a[0] if a else "1"
    d = argv[argv.index("--keep") + 1] if "--keep" in argv else tempfile.mkdtemp(prefix="organchest_")
    os.makedirs(d, exist_ok=True)
    import tonelib as T
    pc = T.FlueOrganProperties
    f0 = 440.0

    # the Tremulant
    mid, wav = os.path.join(d, "tremulant.mid"), os.path.join(d, "tremulant.wav")
    score(mid, (1 << 13) | 1)
    render(mid, wav, 0)
    sr, f, lv = track(wav, f0, 0.07)
    s = slice(int(1.2 * sr), int(3.8 * sr))
    c = 1200 * np.log2(f[s] / np.median(f[s]))
    g = lv[s] - np.median(lv[s])
    fr = np.fft.rfftfreq(len(c), 1.0 / sr)
    rate = fr[1 + np.argmax(np.abs(np.fft.rfft(c - c.mean()))[1:])]
    dep = pc.tremulant_depth
    ec = 1200 * np.log2((1 + dep) ** pc.wind_pitch_exp / (1 - dep) ** pc.wind_pitch_exp)
    eg = 20 * np.log10((1 + dep) ** pc.wind_level_exp / (1 - dep) ** pc.wind_level_exp)
    print("tremulant: %.2f Hz (%.2f), %.1f cents p-p (%.1f), %.2f dB p-p (%.2f), pitch~level r=%.2f"
          % (rate, pc.tremulant_hz, np.percentile(c, 99.5) - np.percentile(c, 0.5), ec,
             np.percentile(g, 99.5) - np.percentile(g, 0.5), eg, np.corrcoef(c, g)[0, 1]))

    # the sag: the plenum (bits 0-7 and the bourdon) and a chord in the bass
    plenum = 0xFF | (1 << 12)
    # F#4 held, F major low: no partial of the plenum's on the chord within
    # 5.6% of the held pipe's fundamental, so its band hears only it
    chord, held = (41, 48, 53, 57, 60), 66
    mid, wav = os.path.join(d, "sag.mid"), os.path.join(d, "sag.wav")
    score(mid, plenum, 1.5, chord, held)
    render(mid, wav, wind)
    sr, f, _ = track(wav, 440.0 * 2 ** ((held - 69) / 12.0))
    k = int(0.05 * sr)
    sm = np.convolve(f, np.ones(k) / k, mode='same')        # under the turbulence's flutter
    pre = np.median(sm[int(0.9 * sr):int(1.45 * sr)])
    win = sm[int(1.56 * sr):int(2.1 * sr)]                  # past the chord's own attack
    dip = 1200 * np.log2(win.min() / pre)
    held_c = 1200 * np.log2(np.median(sm[int(3.0 * sr):int(3.8 * sr)]) / pre)
    # wind.py's own arithmetic on the same draw, without the wander
    import wind as W
    ranks = [r for i, r in enumerate(pc.stop_ranks) if (plenum >> i) & 1 and r[1] is not None]

    def units(n):
        fn = 440.0 * 2 ** ((n - 69) / 12.0)
        return sum(W.pipe_draw(fn * q) for r in ranks
                   for q in (r[1] if isinstance(r[1], (list, tuple)) else [r[1]]))
    blk = 512 / 44100.0
    nb = int(4.0 / blk)
    dem = np.full(nb, units(held))
    i0 = int(1.5 / blk)
    dem[i0:] += sum(units(n) for n in chord)
    wd = W.Wind(pc, blk, scale=float(wind))
    wd.wander_rms = 0.0
    pm = 1200 * pc.wind_pitch_exp * np.log2(wd.blocks(dem, np.zeros(nb))[:, 0])
    print("sag (TUNING_WIND=%s), %.0f units of draw: deepest %.2f cents at %.2f s after the chord, "
          "settled %.2f; the model %.2f at %.2f s, settled %.2f"
          % (wind, dem[-1], dip, 0.06 + np.argmin(win) / sr, held_c,
             pm[i0:].min() - pm[i0 - 2], np.argmin(pm[i0:]) * blk, pm[-1] - pm[i0 - 2]))
    print("  renders in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
