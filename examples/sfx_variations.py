#!/usr/bin/env python3
"""The GS SFX variations (patch_map.SFX_VARIATIONS) against their SFX-set keys.

    python3 examples/sfx_variations.py check           each variation at C4 vs its kit key
    python3 examples/sfx_variations.py ab OUT.mp3 [PROG.BANK ...]

A variation is the SFX set's own sound played from the keyboard, C4 at the
kit's pitch, so at C4 it must BE the kit key: same level, same spectrum. `check`
renders both, held 3 s at velocity 100, and prints the level difference and the
log-spectrum distance (1/3-octave bands, energy-weighted, dB rms), and the pitch
step a fifth up moves the spectrum by (expected 7 semitones where the sound is
pitched).

`ab`, per variation: the kit key, then the variation at C4, a fifth up, an
octave down, and -- for a held texture -- held 8 s, to hear it keep going.
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import blockrender as B  # noqa: E402
import patch_map as PM  # noqa: E402


def midi(events, length_s):
    """events: [(t_s, kind, ch, a, b)] kind 'cc', 'pc', 'on', 'off'"""
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))   # 960 ticks/s
    last = 0
    for at, kind, ch, a, b in sorted(events, key=lambda e: (e[0], e[1] != "cc", e[1] != "pc")):
        tick = int(round(at * 960))
        dt, last = tick - last, tick
        if kind == "cc":
            t.append(mido.Message("control_change", channel=ch, control=a, value=b, time=dt))
        elif kind == "pc":
            t.append(mido.Message("program_change", channel=ch, program=a, time=dt))
        elif kind == "at":
            t.append(mido.Message("aftertouch", channel=ch, value=a, time=dt))
        else:
            t.append(mido.Message("note_on" if kind == "on" else "note_off", channel=ch, note=a,
                                  velocity=b if kind == "on" else 0, time=dt))
    t.append(mido.MetaMessage("end_of_track", time=int(length_s * 960) - last if int(length_s * 960) > last else 0))
    return m


def render(m):
    L, R = B.render(m)[:2]
    return np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)


def kit_take(key, hold, vel=100):
    return render(midi([(0, "pc", 9, 56, 0), (0.1, "on", 9, key, vel), (0.1 + hold, "off", 9, key, 0)], hold + 4))


def var_take(prog, bank, note, hold, vel=100):
    return render(midi([(0, "cc", 0, 0, bank), (0, "pc", 0, prog, 0),
                        (0.1, "on", 0, note, vel), (0.1 + hold, "off", 0, note, 0)], hold + 4))


def bands(x):
    """energy in 1/3-octave bands, 40 Hz-16 kHz"""
    # both channels' power: a kit key is panned and a melodic part is not,
    # and the mono sum would read the pan (and decorrelation) as colour
    X = sum(np.abs(np.fft.rfft(x[:, c], 1 << 20)) ** 2 for c in range(x.shape[1]))
    fr = np.fft.rfftfreq(1 << 20, 1.0 / B.SR)
    edges = 40.0 * 2 ** (np.arange(0, 28) / 3.0)
    return edges, np.array([X[(fr >= a) & (fr < b)].sum() for a, b in zip(edges[:-1], edges[1:])]) + 1e-30


def band_db_rms(a, b):
    """energy-weighted dB rms between two band spectra, levels matched"""
    _, ea = bands(a)
    _, eb = bands(b)
    w = (ea + eb) / (ea + eb).sum()
    d = 10 * np.log10(ea / ea.sum()) - 10 * np.log10(eb / eb.sum())
    return float(np.sqrt((w * d ** 2).sum()))


def level_db(x):
    return 10 * np.log10((x ** 2).sum() + 1e-30)


def _logspec(x):
    """dB power on a 1/48-octave grid, 20 Hz-20 kHz, both channels"""
    X = sum(np.abs(np.fft.rfft(x[:, c], 1 << 20)) ** 2 for c in range(x.shape[1]))
    fr = np.fft.rfftfreq(1 << 20, 1.0 / B.SR)
    g = 20.0 * 2 ** (np.arange(0, 48 * 10) / 48.0)
    e = np.array([X[(fr >= a) & (fr < b)].sum() for a, b in zip(g[:-1], g[1:])]) + 1e-30
    return 10 * np.log10(e)


def shift_st(a, b):
    """how far b's spectrum sits above a's, semitones: the lag of best
    correlation of their log-frequency spectra (energy-weighted)"""
    sa, sb = _logspec(a), _logspec(b)
    best, lag = -1e30, 0
    for k in range(-48 * 2, 48 * 2 + 1):          # +-2 octaves, 1/4-semitone steps
        u = sa[max(0, -k):len(sa) - max(0, k)]
        v = sb[max(0, k):len(sb) - max(0, -k)]
        w = np.maximum(u, v) - max(u.max(), v.max()) + 60.0
        w = np.clip(w, 0, None)
        c = (w * (u - (w * u).sum() / w.sum()) * (v - (w * v).sum() / w.sum())).sum() / w.sum()
        c /= np.sqrt((w * (u - (w * u).sum() / w.sum()) ** 2).sum() / w.sum()
                     * (w * (v - (w * v).sum() / w.sum()) ** 2).sum() / w.sum()) + 1e-30
        if c > best:
            best, lag = c, k
    return lag / 4.0


def check(only=None):
    print("  prog.bank  name              key   level var-kit   spectrum dB rms   a fifth up moves")
    for (p, v), key in sorted(PM.SFX_VARIATIONS.items()):
        if only and (p, v) not in only:
            continue
        k = kit_take(key, 3.0)
        a = var_take(p, v, 60, 3.0)
        up = var_take(p, v, 67, 3.0)
        print("  %3d.%-2d     %-16s  %3d   %+6.2f dB        %5.2f            %+5.1f st"
              % (p, v, PM.VARIATION_NAMES[(p, v)], key, level_db(a) - level_db(k),
                 band_db_rms(a, k), shift_st(a, up)), flush=True)


def ab(out, only=None):
    from scipy.io import wavfile
    chunks = []
    gap = np.zeros((int(0.6 * B.SR), 2))
    for (p, v), key in sorted(PM.SFX_VARIATIONS.items()):
        if only and (p, v) not in only:
            continue
        cls = PM.VARIATIONS[(p, v)]
        held = getattr(cls, "held_texture", False)
        parts = [kit_take(key, 1.0), var_take(p, v, 60, 1.0), var_take(p, v, 67, 1.0), var_take(p, v, 48, 1.0)]
        if held:
            parts.append(var_take(p, v, 60, 8.0))
        for x in parts:
            # trim the trailing silence each take was given
            e = np.abs(x).max(1)
            nz = np.flatnonzero(e > e.max() * 1e-3)
            chunks += [x[:nz[-1] + int(0.1 * B.SR)] if len(nz) else x, gap]
        chunks.append(gap)
        print("  %d.%d %s" % (p, v, PM.VARIATION_NAMES[(p, v)]), flush=True)
    w = np.concatenate(chunks)
    w = 0.9 * w / np.abs(w).max()
    wav = out[:-4] + ".wav"
    wavfile.write(wav, B.SR, (w * 32767).astype(np.int16))
    subprocess.check_call(["lame", "--quiet", "-V2", wav, out])
    print("  -> " + out)


def _only(args):
    return {tuple(int(x) for x in a.split(".")) for a in args} or None


if __name__ == "__main__":
    if sys.argv[1] == "check":
        check(_only(sys.argv[2:]))
    else:
        ab(sys.argv[2], _only(sys.argv[3:]))
