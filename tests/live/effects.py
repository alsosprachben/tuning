#!/usr/bin/env python3
"""THE EFFECTS: that what checks.py compares moves the sound at all.

Two engines agreeing on an input neither of them received is no check --
the GS system effects' live checks once passed identical while the reader
had absorbed every message they tested. So each feature here is rendered
and MEASURED: a segment's level, its balance above 1.5 kHz (the head
model's ILD; pan reads there), its pitches -- against what the feature must
do, in both engines where both render it live.

    python3 tests/live/effects.py [--only=NAME,...] [--logs=DIR]

  rx_file      GS receive settings in a file (blockrender, with the stage
               and without): layering, Rx volume, master pan, Rx notes
  drums_live   GS drum NRPNs / drum setup live (nvlive vs live.Live, each
               measured): level, Rx note on, pan, pitch
  vsense_live  GS velocity sense and key range live
  mpe_file     MPE in a file (blockrender): each note's bend, the manager's
               bend, volume and pressure
  mpe_live     MPE live (nvlive vs live.Live, each measured): the pitches
  rhythm_live  USE FOR RHYTHM PART live: a channel's part a kit and back
  drum_delay_live  a drum key's own GS delay send live

Exit 0 when every effect is there in every engine measured.
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MIDI = os.path.join(HERE, "midi")
SR = 48000
NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def hp(x, sr=SR):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(4, 1500, 'hp', fs=sr, output='sos'), x, axis=0)


def level(x, a, b, sr=SR):
    i, j = int(a * sr), int(b * sr)
    return 10 * np.log10(np.mean(np.asarray(x[i:j], np.float64) ** 2) + 1e-30)


def ild(x, a, b, sr=SR):
    h = hp(np.asarray(x, np.float64), sr)
    i, j = int(a * sr), int(b * sr)
    return 10 * np.log10((np.mean(h[i:j, 0] ** 2) + 1e-30) / (np.mean(h[i:j, 1] ** 2) + 1e-30))


def centroid(x, a, sr=SR, n=4096):
    i = int(a * sr)
    s = np.abs(np.fft.rfft(np.asarray(x[i:i + n], np.float64).mean(1) * np.hanning(n)))
    f = np.fft.rfftfreq(n, 1.0 / sr)
    return float((s * f).sum() / (s.sum() + 1e-30))


def pitches(x, a, sr=SR, k=3, lo=90.0, hi=480.0):
    """The k strongest peaks in [lo, hi] Hz at time a, as note numbers."""
    i = int(a * sr)
    w = np.asarray(x[i:i + 8192], np.float64)
    w = (w.mean(1) if w.ndim > 1 else w) * np.hanning(len(w))
    s = np.abs(np.fft.rfft(w, 65536))
    f = np.fft.rfftfreq(65536, 1.0 / sr)
    idx = np.where((f > lo) & (f < hi))[0]
    pk = [q for q in idx[1:-1] if s[q] > s[q - 1] and s[q] > s[q + 1]]
    pk = sorted(pk, key=lambda q: -s[q])[:k]
    return sorted(int(round(69 + 12 * np.log2(f[q] / 440.0))) for q in pk)


def pitch_cents(x, a, b, sr=SR, lo=150.0, hi=320.0, n=2048):
    """The strongest peak in [lo, hi] Hz, window by window from a to b, in
    cents from its median: a vibrato's swing."""
    m = np.asarray(x, np.float64)
    m = m.mean(1) if m.ndim > 1 else m
    f = np.fft.rfftfreq(32768, 1.0 / sr)
    idx = np.where((f > lo) & (f < hi))[0]
    out = []
    for i in range(int(a * sr), int(b * sr) - n, n // 2):
        s = np.abs(np.fft.rfft(m[i:i + n] * np.hanning(n), 32768))
        q = idx[np.argmax(s[idx])]
        y0, y1, y2 = np.log(s[q - 1:q + 2] + 1e-30)
        out.append(f[q] + (y0 - y2) / (2.0 * (y0 - 2.0 * y1 + y2)) * (f[1] - f[0]))
    c = 1200.0 * np.log2(np.asarray(out) / np.median(out))
    return float(np.percentile(c, 95) - np.percentile(c, 5))


def level_swing(x, a, b, sr=SR, n=480):
    """How far the level moves, 10 ms window by window from a to b: the
    90th less the 10th percentile, in dB -- a tremolo's swing."""
    m = np.asarray(x, np.float64)
    m = m.mean(1) if m.ndim > 1 else m
    i, j = int(a * sr), int(b * sr)
    e = [10 * np.log10(np.mean(m[k:k + n] ** 2) + 1e-30) for k in range(i, j - n, n)]
    return float(np.percentile(e, 90) - np.percentile(e, 10))


def echo_rises(x, a, b, sr=SR, w=0.05):
    """The level's rises summed, 50 ms window by window from a to b, in dB:
    each echo's return (a decay alone has none)."""
    m = np.asarray(x, np.float64)
    m = m.mean(1) if m.ndim > 1 else m
    e = [10 * np.log10(np.mean(m[int(t * sr):int((t + w) * sr)] ** 2) + 1e-30) for t in np.arange(a, b, w)]
    return float(sum(max(0.0, q - p) for p, q in zip(e, e[1:])))


def wav(path):
    from scipy.io import wavfile
    sr, x = wavfile.read(path)
    return sr, x.astype(np.float64)


def render_py(mid, out, off_receive=False):
    """blockrender's render of mid (its receive stage off: gsrx's sysex read as none)."""
    code = ("import sys, runpy; sys.path.insert(0, %r)\n" % ROOT
            + ("import gsrx; gsrx.Receive.sysex = lambda self, d: None\n" if off_receive else "")
            + "sys.argv = ['blockrender.py', %r, %r]\n" % (mid, out)
            + "runpy.run_path(%r, run_name='__main__')\n" % os.path.join(ROOT, "blockrender.py"))
    subprocess.check_call([sys.executable, "-c", code], cwd=ROOT, stdout=subprocess.DEVNULL)
    return wav(out)


# (a pitch measured live is at A = 440: the live check's default tuner is
# hybrid, whose reference is a baroque 415 -- every note a semitone down)
A440 = ["--tuner=hybrid440"]


def live_pair(mid, secs, args, logs, tag):
    """nvlive_check on mid, both sides kept: (live.Live's, nvlive's) blocks."""
    keep = os.path.join(logs, "keep_" + tag)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "examples", "nvlive_check.py"), mid, str(secs)]
                       + args + ["--keep=" + keep], cwd=ROOT, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    return np.load(os.path.join(keep, "py.npy")), np.load(os.path.join(keep, "nv.npy")), last


class Effects(object):
    def __init__(self):
        self.bad = 0

    def expect(self, what, ok, detail):
        print("  %-58s %s  %s" % (what, "ok" if ok else "MISSING", detail), flush=True)
        self.bad += not ok


def rx_file(E, logs):
    mid = os.path.join(MIDI, "gsrx.mid")
    sr, on = render_py(mid, os.path.join(logs, "rx_on.wav"))
    _, off = render_py(mid, os.path.join(logs, "rx_off.wav"), off_receive=True)
    seg = [(k * 0.375 + 0.05, k * 0.375 + 0.30) for k in range(7)]
    L = lambda x, k: level(x, seg[k][0], seg[k][1], sr)
    I = lambda x, k: ild(x, seg[k][0], seg[k][1], sr)
    E.expect("part 2 received on channel 1: layered", L(on, 1) - L(on, 0) > 1.0,
             "%+.1f dB" % (L(on, 1) - L(on, 0)))
    E.expect("Rx volume off: CC7 30 not taken", L(on, 3) - L(off, 3) > 10.0,
             "%+.1f dB against the stage off" % (L(on, 3) - L(off, 3)))
    E.expect("master pan 32: to the left", I(on, 4) - I(off, 4) > 1.5,
             "ILD %+.1f against %+.1f dB" % (I(on, 4), I(off, 4)))
    E.expect("Rx note messages off: silent", L(off, 6) - L(on, 6) > 10.0,
             "%+.1f dB under the stage off" % (L(off, 6) - L(on, 6)))


def drums_live(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "drumnrpn.mid"), 4,
                             ["--drums", "--program=0", "--programs"], logs, "drum1")
    print("  (drumnrpn: %s)" % last)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        p = level(x, 0.02, 0.3)
        E.expect("%s: snare level 40 quieter" % side, level(x, 0.40, 0.70) < p - 3.0,
                 "%+.1f dB" % (level(x, 0.40, 0.70) - p))
        E.expect("%s: hi-hat Rx note on off silent" % side, level(x, 0.74, 1.05) < p - 10.0,
                 "%+.1f dB" % (level(x, 0.74, 1.05) - p))
        E.expect("%s: back after a drum set change" % side, abs(level(x, 1.08, 1.40) - p) < 1.5,
                 "%+.1f dB" % (level(x, 1.08, 1.40) - p))
    py, nv, last = live_pair(os.path.join(MIDI, "drumnrpn2.mid"), 4,
                             ["--drums", "--program=0", "--programs"], logs, "drum2")
    print("  (drumnrpn2: %s)" % last)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        i0 = ild(x, 0.021, 0.271)
        E.expect("%s: snare panned to 20 left" % side, ild(x, 1.146, 1.396) > i0 + 3.0,
                 "ILD %+.1f against %+.1f dB" % (ild(x, 1.146, 1.396), i0))
        E.expect("%s: tom panned to 110 right" % side, ild(x, 1.708, 1.958) < 0.0,
                 "ILD %+.1f dB" % ild(x, 1.708, 1.958))
        c0, c1 = centroid(x, 1.708), centroid(x, 2.271)
        E.expect("%s: tom +7 semitones (drum setup) higher" % side, c1 > 1.2 * c0,
                 "%.0f -> %.0f Hz" % (c0, c1))


def vsense_live(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "gsvsense.mid"), 3, ["--program=0"] + A440, logs, "vsense")
    print("  (gsvsense: %s)" % last)
    seg = [(0.05 + k * 0.375, 0.30 + k * 0.375) for k in range(5)]
    for side, x in (("live.Live", py), ("nvlive", nv)):
        L = [level(x, a, b) for a, b in seg]
        E.expect("%s: depth 32 softer" % side, L[1] < L[0] - 2.0, "%+.1f dB" % (L[1] - L[0]))
        E.expect("%s: offset +36 louder" % side, L[2] > L[0] + 0.5, "%+.1f dB" % (L[2] - L[0]))
        # (the strongest pitch, once the chord before has faded: its tail rings on)
        E.expect("%s: key range 62-66: E alone" % side, pitches(x, seg[3][0] + 0.15, k=1) == [64],
                 "%s" % pitches(x, seg[3][0] + 0.15, k=3))
        E.expect("%s: back after a GS reset" % side, abs(L[4] - L[0]) < 1.5, "%+.1f dB" % (L[4] - L[0]))


MPE_AT = ((0.46, [62, 64, 66]), (0.90, [63, 65, 67]), (1.75, [64, 65, 68]), (2.15, [49, 64, 68]))


def mpe_file(E, logs):
    sr, x = render_py(os.path.join(MIDI, "mpe_zone.mid"), os.path.join(logs, "mpe.wav"))
    for t, want in MPE_AT:
        got = pitches(x, t, sr)
        E.expect("file: the zone's pitches at %.2f s" % t, got == want, "%s, want %s" % (got, want))
    _, a = render_py(os.path.join(MIDI, "mpe", "a_plain.mid"), os.path.join(logs, "mpe_a.wav"))
    _, h = render_py(os.path.join(MIDI, "mpe", "h_mgrat.mid"), os.path.join(logs, "mpe_h.wav"))
    _, c = render_py(os.path.join(MIDI, "mpe", "c_mvol.mid"), os.path.join(logs, "mpe_c.wav"))
    d1, d2 = level(h, 0.6, 1.0, sr) - level(a, 0.6, 1.0, sr), level(c, 0.6, 1.0, sr) - level(a, 0.6, 1.0, sr)
    E.expect("file: the manager's pressure on its members", d1 > 1.5, "%+.1f dB" % d1)
    E.expect("file: the manager's volume on its members", d2 < -1.5, "%+.1f dB" % d2)


def peak_hz(x, a, b, lo, hi, sr=SR):
    """The strongest peak in [lo, hi] Hz over a..b, to a fraction of a cent
    (zero-padded, the peak's parabola on log magnitudes)."""
    m = np.asarray(x, np.float64)
    m = m.mean(1) if m.ndim > 1 else m
    w = m[int(a * sr):int(b * sr)]
    n = 1 << 20
    s = np.abs(np.fft.rfft(w * np.hanning(len(w)), n))
    f = np.fft.rfftfreq(n, 1.0 / sr)
    idx = np.where((f > lo) & (f < hi))[0]
    q = idx[np.argmax(s[idx])]
    y0, y1, y2 = np.log(s[q - 1:q + 2] + 1e-30)
    return float(f[q] + (y0 - y2) / (2.0 * (y0 - 2.0 * y1 + y2)) * (f[1] - f[0]))


def cents(f, ref):
    return 1200.0 * np.log2(f / ref)


def m2_file(E, logs):
    """MIDI 2.0's per-note pitch (m2_pernote.midi2), in the file render (at
    its own rate, 44.1 kHz) -- nvrender's is identical to it (checks.py
    midi2_files)."""
    sr, x = render_py(os.path.join(MIDI, "m2_pernote.midi2"), os.path.join(logs, "m2.wav"))
    e_et = 440.0 * 2 ** ((64 - 69) / 12.0)
    e0, e1 = peak_hz(x, 0.3, 0.95, 315, 340, sr), peak_hz(x, 2.2, 2.95, 315, 340, sr)
    E.expect("file: Pitch 7.25's table, the E at 12-TET", abs(cents(e0, e_et)) < 1.0, "%+.2f cents" % cents(e0, e_et))
    E.expect("file: the third alone settles to the just 5:4 (-13.69 cents)", abs(cents(e1, e0) + 13.69) < 1.0,
             "%+.2f cents" % cents(e1, e0))
    # (each against the same key in the first chord, at 12-TET: a piano's
    # unison strings bias a peak's reading a cent or two, key by key)
    ej, gj = peak_hz(x, 4.3, 5.9, 315, 340, sr), peak_hz(x, 4.3, 5.9, 380, 405, sr)
    g0 = peak_hz(x, 0.3, 0.95, 380, 405, sr)
    E.expect("file: Pitch 7.9 on each Note On: the just chord's E and G", abs(cents(ej, e0) + 13.69) < 1.0
             and abs(cents(gj, g0) - 1.955) < 1.0, "E %+.2f, G %+.2f cents" % (cents(ej, e0), cents(gj, g0)))
    w = pitch_cents(x, 7.3, 7.95, sr, lo=480, hi=560)
    E.expect("file: the flute's own per-note bend, half its 1-semitone range", w > 70.0, "%.0f cents swing" % w)
    d_et = 440.0 * 2 ** ((62 - 69) / 12.0)
    dq, dr = peak_hz(x, 10.7, 11.45, 280, 310, sr), peak_hz(x, 11.7, 12.45, 280, 310, sr)
    E.expect("file: a quarter-tone D (Pitch 7.25 62.5), then reset to the tuner's", abs(cents(dq, d_et) - 50.0) < 2.0
             and abs(cents(dr, d_et)) < 10.0, "%+.1f, then %+.1f cents" % (cents(dq, d_et), cents(dr, d_et)))


def m2_organ_file(E, logs):
    """A note with a row of its own on an organ's chest rides the product of
    its row and the wind's (_prep_wind_combos): m2_organ.midi2's per-note
    pitch moving on GM 19 -- nvrender identical (checks.py midi2_files)."""
    sr, x = render_py(os.path.join(MIDI, "m2_organ.midi2"), os.path.join(logs, "m2_organ.wav"))
    et = lambda n: 440.0 * 2 ** ((n - 69) / 12.0)
    e0, e1 = peak_hz(x, 0.3, 0.95, 315, 340, sr), peak_hz(x, 2.2, 2.95, 315, 340, sr)
    E.expect("file, organ on its wind: the third settles to the just 5:4", abs(cents(e1, e0) + 13.69) < 1.0,
             "%+.2f cents" % cents(e1, e0))
    w = pitch_cents(x, 4.4, 6.3, sr, lo=500, hi=545)
    E.expect("file, organ on its wind: a top note's own per-note bend", w > 120.0, "%.0f cents swing" % w)
    g0, g1 = peak_hz(x, 7.05, 7.45, 380, 405, sr), peak_hz(x, 8.7, 9.4, 380, 405, sr)
    E.expect("file, organ on its wind: the wheel moves no pipe", abs(cents(g1, g0)) < 2.0, "%+.1f cents" % cents(g1, g0))


ASSIGN_AT = (("the default", 0.7, 1.4), ("SINGLE", 3.2, 3.9), ("FULL-MULTI", 5.7, 6.4),
             ("the drum part's default", 8.0, 9.0), ("the drum part SINGLE", 10.5, 11.5),
             ("after a GS reset", 13.2, 13.9))


def assign_expect(E, side, x, sr):
    """assign_mode.mid's levels after each second strike: SINGLE cuts the
    loud first note (only the soft one sounds on), the others let it ring."""
    L = [level(x, a, b, sr) for _n, a, b in ASSIGN_AT]
    E.expect("%s: ASSIGN MODE SINGLE cuts the key's sounding note" % side, L[1] < L[0] - 12.0,
             "%+.1f dB" % (L[1] - L[0]))
    E.expect("%s: FULL-MULTI lets it sound on, as the default" % side, abs(L[2] - L[0]) < 3.0,
             "%+.1f dB" % (L[2] - L[0]))
    E.expect("%s: the drum part SINGLE cuts a ringing crash" % side, L[4] < L[3] - 12.0, "%+.1f dB" % (L[4] - L[3]))
    E.expect("%s: a GS reset puts the default back" % side, abs(L[5] - L[0]) < 3.0, "%+.1f dB" % (L[5] - L[0]))


def assign_file(E, logs):
    """GS's ASSIGN MODE in the file render (nvrender identical: assign_files)."""
    sr, x = render_py(os.path.join(MIDI, "assign_mode.mid"), os.path.join(logs, "assign.wav"))
    assign_expect(E, "file", x, sr)


def assign_live(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "assign_mode.mid"), 16, ["--beside", "--programs"], logs, "assign")
    print("  (assign_mode: %s)" % last)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        assign_expect(E, side, x, SR)


def moog_cmx_file(E, logs):
    """A Moog under GS's controller matrix (moog_cmx.mid: the mod wheel into
    TVF cutoff, swept up and down across a held saw-lead note) in the file
    render -- its knobs following the matrix's cutoff; nvrender identical
    (checks.py moog_cmx)."""
    sr, x = render_py(os.path.join(MIDI, "moog_cmx.mid"), os.path.join(logs, "moog_cmx.wav"))
    c = lambda a, b: float(np.mean([centroid(x, t, sr, n=2048) for t in np.arange(a, b, 0.02)]))
    c0, c1, c2 = c(0.09, 0.17), c(0.45, 0.71), c(1.0, 1.1)
    E.expect("file: a Moog under the matrix's cutoff brightens with the wheel", c1 > 2.0 * c0,
             "%.0f -> %.0f Hz" % (c0, c1))
    E.expect("file: ...and darkens as it comes back", c2 < 0.7 * c1, "%.0f -> %.0f Hz" % (c1, c2))


def m2_live(E, logs):
    """MIDI 2.0's per-note pitch live (m2_pernote.midi2 through nvlive_check:
    live.Live's on_ump, nvlive's reader), both sides; the after-reset D the
    check's tuner's (A = 415: a semitone down)."""
    py, nv, last = live_pair(os.path.join(MIDI, "m2_pernote.midi2"), 14, ["--programs"], logs, "m2")
    print("  (m2_pernote live: %s)" % last)
    et = lambda n: 440.0 * 2 ** ((n - 69) / 12.0)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        e0, e1 = peak_hz(x, 0.3, 0.95, 315, 340), peak_hz(x, 2.2, 2.95, 315, 340)
        g0, gj, ej = peak_hz(x, 0.3, 0.95, 380, 405), peak_hz(x, 4.3, 5.9, 380, 405), peak_hz(x, 4.3, 5.9, 315, 340)
        E.expect("%s: Pitch 7.25's table, then the third settling" % side,
                 abs(cents(e0, et(64))) < 1.0 and abs(cents(e1, e0) + 13.69) < 1.0,
                 "%+.2f, %+.2f cents" % (cents(e0, et(64)), cents(e1, e0)))
        E.expect("%s: Pitch 7.9 on each Note On: the just E and G" % side,
                 abs(cents(ej, e0) + 13.69) < 1.0 and abs(cents(gj, g0) - 1.955) < 1.0,
                 "E %+.2f, G %+.2f cents" % (cents(ej, e0), cents(gj, g0)))
        w = pitch_cents(x, 7.3, 7.95, lo=480, hi=560)
        E.expect("%s: the flute's per-note bend" % side, w > 70.0, "%.0f cents swing" % w)
        dq, dr = peak_hz(x, 10.7, 11.45, 280, 310), peak_hz(x, 11.7, 12.45, 260, 310)
        E.expect("%s: a quarter-tone D, then reset to the tuner's" % side,
                 abs(cents(dq, et(62)) - 50.0) < 2.0 and abs(cents(dr, et(62)) + 100.0) < 10.0,
                 "%+.1f, then %+.1f cents" % (cents(dq, et(62)), cents(dr, et(62))))


def mpe_live(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "mpe_zone.mid"), 4, ["--programs"] + A440, logs, "mpe")
    print("  (mpe_zone live: %s)" % last)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        for t, want in MPE_AT:
            got = pitches(x, t)
            E.expect("%s: the zone's pitches at %.2f s" % (side, t), got == want, "%s, want %s" % (got, want))


def rhythm_live(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "rhythmpart.mid"), 3,
                             ["--beside", "--program=0", "--programs"] + A440, logs, "rhythm")
    print("  (rhythmpart: %s)" % last)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        a, b, c = pitches(x, 0.12), pitches(x, 0.93), pitches(x, 1.75)
        E.expect("%s: channel 1 a piano, then a kit, then a piano" % side,
                 a == [60, 64, 67] and b != [60, 64, 67] and c == [60, 64, 67], "%s %s %s" % (a, b, c))


def drum_delay_live(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "drumdelay.mid"), 5, ["--drums", "--program=0", "--programs"],
                             logs, "drumdelay")
    print("  (drumdelay: %s)" % last)
    # each hit 1.5 s apart; its echoes as the level's RISES from 0.1 s after
    # it to 1.4 s (the snare's ring and the hall only fall: a level over the
    # span read them too, and a hit without echoes was only 8 dB down)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        e = [echo_rises(x, t0 + 0.1, t0 + 1.4) for t0 in (0.021, 1.521, 3.021)]
        E.expect("%s: a key's delay send 127: echoes" % side, e[0] > 15.0, "rises %.1f dB" % e[0])
        E.expect("%s: a key's delay send 0: no echoes" % side, e[1] < 5.0, "rises %.1f dB" % e[1])
        E.expect("%s: a key's delay send 64: softer echoes" % side, 6.0 < e[2] < e[0] - 5.0,
                 "rises %.1f dB" % e[2])


def user_drums_live(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "userdrums.mid"), 4, ["--drums", "--program=0", "--programs"],
                             logs, "userdrums")
    print("  (userdrums: %s)" % last)
    at = [0.021 + 0.5 * k for k in range(6)]        # (each hit 0.5 s after the last)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        L = [level(x, t, t + 0.3) for t in at]
        E.expect("%s: user set keys sound (36, 38, 42)" % side, min(L[0], L[1], L[2]) > L[4] + 15.0,
                 "%.1f %.1f %.1f against %.1f dB" % (L[0], L[1], L[2], L[4]))
        E.expect("%s: key 46 not received" % side, L[3] < L[0] - 15.0, "%+.1f dB" % (L[3] - L[0]))
        E.expect("%s: key 49 unset: silent" % side, L[4] < L[0] - 15.0, "%+.1f dB" % (L[4] - L[0]))
        E.expect("%s: key 42 panned to 20: left" % side, ild(x, at[2], at[2] + 0.3) > 2.0,
                 "ILD %+.1f dB" % ild(x, at[2], at[2] + 0.3))


def cmx_live_fx(E, logs):
    py, nv, last = live_pair(os.path.join(MIDI, "cmx_live.mid"), 7, ["--program=81", "--programs"] + A440, logs,
                             "cmx")
    print("  (cmx_live: %s)" % last)
    seg = [0.021 + 0.75 * k for k in range(7)]      # (each note 0.625 s, 0.125 s apart)
    for side, x in (("live.Live", py), ("nvlive", nv)):
        L = [level(x, t + 0.1, t + 0.5) for t in seg]
        p0, p2 = pitches(x, seg[0] + 0.15, k=1), pitches(x, seg[2] + 0.15, k=1)
        c0, c3 = centroid(x, seg[0] + 0.15), centroid(x, seg[3] + 0.15)
        E.expect("%s: mod wheel to amplitude -100 %%, wheel at half: quieter" % side, L[1] < L[0] - 3.0,
                 "%+.1f dB" % (L[1] - L[0]))
        E.expect("%s: pressure to pitch +2 st, pressed full: up 2" % side,
                 bool(p0) and bool(p2) and p2[0] - p0[0] == 2, "%s -> %s" % (p0, p2))
        E.expect("%s: CC20 (CC1's number) to cutoff: brighter" % side, c3 > 1.2 * c0, "%.0f -> %.0f Hz" % (c0, c3))
        E.expect("%s: back after a GS reset" % side, abs(L[4] - L[0]) < 1.5, "%+.1f dB" % (L[4] - L[0]))
        v0, v5 = pitch_cents(x, seg[0] + 0.15, seg[0] + 0.6), pitch_cents(x, seg[5] + 0.15, seg[5] + 0.6)
        # (+-236 cents: a 472-cent swing; the plain Moog lead's own reads ~40)
        E.expect("%s: pressure to LFO1 pitch 236 cents: a vibrato" % side, v5 > 350.0 and v0 < 100.0,
                 "%.0f -> %.0f cents" % (v0, v5))
        w0, w6 = level_swing(x, seg[0] + 0.15, seg[0] + 0.6), level_swing(x, seg[6] + 0.15, seg[6] + 0.6)
        E.expect("%s: mod wheel to LFO1 amplitude 100 %%: a tremolo" % side, w6 > 10.0 and w0 < 3.0,
                 "%.1f -> %.1f dB" % (w0, w6))


ALL = [("rx_file", rx_file), ("cmx_live", cmx_live_fx), ("user_drums_live", user_drums_live), ("drum_delay_live", drum_delay_live), ("rhythm_live", rhythm_live), ("drums_live", drums_live), ("vsense_live", vsense_live),
       ("mpe_file", mpe_file), ("moog_cmx_file", moog_cmx_file), ("assign_file", assign_file), ("assign_live", assign_live), ("m2_file", m2_file), ("m2_organ_file", m2_organ_file), ("m2_live", m2_live), ("mpe_live", mpe_live)]


def main(argv):
    opt = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else "") for a in argv if a.startswith("--")}
    only = set(filter(None, opt.get("only", "").split(",")))
    logs = opt.get("logs") or os.path.join(HERE, "logs")
    os.makedirs(logs, exist_ok=True)
    E = Effects()
    for name, fn in ALL:
        if only and name not in only:
            continue
        print(name)
        try:
            fn(E, logs)
        except Exception as e:          # (a render that failed: the effect is not shown)
            E.expect(name + ": rendered", False, repr(e))
    print("effects: %d missing" % E.bad)
    return 1 if E.bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
