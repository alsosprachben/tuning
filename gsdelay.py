"""The GS DELAY: the SC-88's system delay, as Roland defines it.

One digital line, three taps. The CENTER tap reads it at Delay Time Center and
feeds back into its input (Delay Feedback, -64..+63: a negative value feeds
the center back inverted); the LEFT and RIGHT taps read the same line at their
ratios of that time (4-500%). So what reaches tap t on the k-th time round is

    x(t - tau_t - k * tau_C) * fb^k,     k = 0, 1, 2, ...

and each tap is its own output: center in the middle of the field, left and
right at its sides -- the device's outputs, not the source's position. Ten
macros set all ten parameters (SC-8850 owner's manual, "About Delay Type");
a file may then change any one (40 01 50-5A).

The repeats are made as the renderer makes the MF-104M's (mf104.py): copies
of each sending note's partial rows, later and quieter, so they are exact,
alias-free and in the same table as everything else -- the delay is a
device, the copies are what it outputs. A part's DELAY SEND (CC94, or its
SysEx 40 1x 2C) scales what goes in, and a drum key's own (NRPN 1F, 41 m9 rr)
multiplies it.

WHAT ROLAND GIVES AND WHAT IS CHOSEN. The time table, the ratios' resolution,
the macros' values and the parameter ranges are Roland's. The level laws are
not given; levels are taken as linear amplitudes over 127 (DELAY LEVEL's 64,
the macros' value, a half) and feedback as v/64 per pass. PRE-LPF 0-7 is a
first-order low-pass on what enters, its corner chosen: 12 kHz halved every
1.5 steps (7 -> 470 Hz). Delay -> reverb (40 01 5A) is not yet a send of its
own: the repeats stand where the delay's outputs do and take the room.
"""
import math

REPEAT_FLOOR = 10.0 ** (-60.0 / 20.0)   # a repeat this far under the note's loudest partial ends it
MAX_REPEATS = 64

# THE TEN MACROS (SC-8850 owner's manual, p.84): level, pre-LPF, time C (ms),
# ratio L, ratio R (%), level C, L, R, feedback, to reverb
MACROS = {
    0: (64, 0, 340, 4, 4, 127, 0, 0, 16, 0),      # Delay 1
    1: (64, 0, 550, 4, 4, 127, 0, 0, 16, 0),      # Delay 2
    2: (64, 0, 1000, 4, 4, 127, 0, 0, 8, 0),      # Delay 3
    3: (64, 0, 130, 4, 4, 127, 0, 0, 8, 0),       # Delay 4
    4: (64, 0, 500, 50, 100, 0, 125, 60, 10, 0),  # Pan Delay 1
    5: (64, 0, 700, 50, 100, 0, 125, 60, 7, 0),   # Pan Delay 2
    6: (64, 0, 1000, 50, 100, 0, 120, 64, 9, 0),  # Pan Delay 3
    7: (64, 0, 260, 50, 100, 0, 120, 64, 8, 0),   # Pan Delay 4
    8: (64, 0, 700, 50, 100, 0, 114, 60, -3, 36), # Delay to Reverb
    9: (64, 0, 750, 88, 133, 97, 127, 67, -24, 0),  # Pan Repeat
}
NAMES = ("Delay 1", "Delay 2", "Delay 3", "Delay 4", "Pan Delay 1", "Pan Delay 2",
         "Pan Delay 3", "Pan Delay 4", "Delay to Reverb", "Pan Repeat")
# the SysEx addresses (40 01 aa) -> parameter
PARAM = {0x50: 'macro', 0x51: 'pre_lpf', 0x52: 'time', 0x53: 'ratio_l', 0x54: 'ratio_r',
         0x55: 'level_c', 0x56: 'level_l', 0x57: 'level_r', 0x58: 'level', 0x59: 'feedback',
         0x5A: 'to_reverb'}
# THE OUTPUTS ARE THE SPEAKERS: the module's left and right outputs, heard
# where a hard pan is (tonelib.stage_angle: +-30 degrees, ITU-R BS.775) --
# 2 m x tan 30 either side of a listener 2 m away. They were +-4 m (63
# degrees), the stage pan had before it was a turn.
OUTPUT_X = {'c': 0.0, 'l': -2.0 * math.tan(math.pi / 6.0), 'r': 2.0 * math.tan(math.pi / 6.0)}
SIDES = ('c', 'l', 'r')     # the field's middle and sides (a pan of 0, -1, +1)


def time_ms(v):
    """DELAY TIME CENTER 01-73H -> ms (VE-GS Pro MIDI Implementation's table)."""
    v = max(1, min(0x73, int(v)))
    for lo, t0, step in ((0x69, 500.0, 50.0), (0x5A, 200.0, 20.0), (0x50, 100.0, 10.0),
                         (0x46, 50.0, 5.0), (0x37, 20.0, 2.0), (0x2D, 10.0, 1.0),
                         (0x23, 5.0, 0.5), (0x14, 2.0, 0.2)):
        if v >= lo:
            return t0 + (v - lo) * step
    return v * 0.1


def time_value(ms):
    """The nearest DELAY TIME CENTER value for a time in ms (the macros give ms)."""
    return min(range(1, 0x74), key=lambda v: abs(time_ms(v) - ms))


def ratio_value(pct):
    """DELAY TIME RATIO, 01-78H at 100/24 % a step, for a percentage."""
    return max(1, min(0x78, int(round(pct * 24.0 / 100.0))))


def macro(m):
    """{param: data value} a macro sets."""
    lv, lpf, t, rl, rr, lc, ll, lr, fb, rv = MACROS[int(m) if int(m) in MACROS else 0]
    return dict(level=lv, pre_lpf=lpf, time=time_value(t), ratio_l=ratio_value(rl),
                ratio_r=ratio_value(rr), level_c=lc, level_l=ll, level_r=lr,
                feedback=fb + 64, to_reverb=rv)


def device(params):
    """The delay as the file set it: the macro's values (Delay 1 by default,
    as a GS reset leaves it), then each parameter the file sent after it."""
    p = macro(params.get('macro', 0))
    p.update({k: v for k, v in params.items() if k != 'macro'})
    tc = time_ms(p['time']) / 1000.0
    return dict(
        tc=tc,
        taps=[(tc * rr, lv / 127.0, side) for rr, lv, side in (
            (1.0, p['level_c'], 'c'),
            (p['ratio_l'] * 100.0 / 24.0 / 100.0, p['level_l'], 'l'),
            (p['ratio_r'] * 100.0 / 24.0 / 100.0, p['level_r'], 'r')) if lv > 0],
        level=p['level'] / 127.0,
        fb=(p['feedback'] - 64) / 64.0,
        lpf=(12000.0 * 2.0 ** (-p['pre_lpf'] / 1.5)) if p['pre_lpf'] else None,
        to_reverb=p['to_reverb'] / 127.0)


def lpf_gain(f_hz, fc):
    return 1.0 if not fc else 1.0 / math.sqrt(1.0 + (f_hz / fc) ** 2)


def repeats(dev, send, f_hz, sr, rel=1.0):
    """[(tap side, k, delay samples, gain)] for a partial at f_hz sent at
    `send` (0-1), until a repeat falls under REPEAT_FLOOR of the note's
    loudest partial (`rel`: this partial's level against that one)."""
    g0 = send * dev['level'] * lpf_gain(f_hz, dev['lpf'])
    out = []
    if g0 <= 0.0:
        return out
    fb = dev['fb']
    # AN INSERTION DELAY'S TAPS (gsefx._delay) may each loop at their own
    # period (a Stereo Delay's left and right), and a cross-feedback one
    # (ping-pong) answers each repeat from the other side
    cross = dev.get('cross')
    for tap in dev['taps']:
        tau, lv, side = tap[0], tap[1], tap[2]
        period = tap[3] if len(tap) > 3 else dev['tc']
        for k in range(MAX_REPEATS):
            g = g0 * lv * (fb ** k if k else 1.0)
            if abs(g) * rel < REPEAT_FLOOR or (k and fb == 0.0):
                break
            sd = side if not (cross and k % 2) else {'l': 'r', 'r': 'l'}.get(side, side)
            out.append((sd, k, int(round((tau + k * period) * sr)), g))
    return out


def _tap_of(dev, side):
    """The index of the tap at `side` (a pan or an angle, not c/l/r)."""
    for j, t in enumerate(dev['taps']):
        if t[2] == side:
            return j
    return 0


def expand(A, notes, sr, cols, place, meta=None):
    """Add each sending note's repeats to the partial table A, in place.
    notes: [(first row, end row, device, send)]. place(side, f_hz) gives an
    output's ear gains and delays at that frequency, (gL, gR, dL, dR) in
    samples -- the field's middle or a side, as a pan of 0 or +-1 places a
    source. Returns (rows added, the latest sample any copy may still sound)."""
    if not notes:
        return 0, 0
    keys = list(cols)
    extra = {k: [] for k in keys}
    made, last = 0, 0
    tpi = 2.0 * math.pi
    for i0, i1, dev, send in notes:
        lv = [max(abs(float(A['aL'][i])), abs(float(A['aR'][i]))) for i in range(i0, i1)]
        top = max(lv) if lv else 0.0
        for i in range(i0, i1):
            row = {k: A[k][i] for k in keys}
            om = float(row['om'])
            f = om * sr / tpi
            rel = lv[i - i0] / top if top > 0.0 else 0.0
            for side, k, d, g in repeats(dev, send, f, sr, rel):
                gl, gr, dl, dr = place(side, f)
                c = dict(row)
                c['non'] = row['non'] + d
                c['noff'] = row['noff'] + d
                c['nfr'] = float(c['non']) - math.floor(float(c['non']))
                # the copy leaves at the output, not at the source: its ears'
                # delays are the output's, its phase the line's
                c['delL'], c['delR'] = dl, dr
                c['p0'] = -om * (float(c['non']) + dl) + (float(row['p0']) + om * (float(row['non']) + float(row['delL'])))
                c['p0R'] = -om * (float(c['non']) + dr) + (float(row['p0R']) + om * (float(row['non']) + float(row['delR'])))
                if float(row.get('fmw', 0.0)) != 0.0:
                    c['fmp'] = row['fmp'] - float(row['fmw']) * d
                    c['fmpR'] = row['fmpR'] - float(row['fmw']) * d
                if float(row.get('vd', 0.0)) != 0.0:     # the note's own vibrato, delayed
                    c['vp'] = row['vp'] - tpi * float(row['vr']) * d / sr
                m = abs(float(row['aM']))
                c['aL'] = m * g * gl
                c['aR'] = m * g * gr
                c['aM'] = row['aM'] * g
                for kk in keys:
                    extra[kk].append(c[kk])
                # (an insertion delay's tap between or past the outputs, or its
                # modulation: the line's LFO on the copy, free-running)
                if dev.get('mod'):
                    mr, mswing, mph = dev['mod']
                    c['vd'] = min(0.5, 2.0 * math.pi * mr * mswing)
                    c['vr'] = mr
                    c['vp'] = (tpi * mr * float(c['non']) / sr + (mph if side == 'r' else 0.0)) % tpi
                if meta is not None:
                    meta.append((i, (SIDES.index(side) if side in SIDES else
                                     len(SIDES) + _tap_of(dev, side)) * MAX_REPEATS + k))
                made += 1
                last = max(last, int(c['noff']) + int(math.ceil(float(row.get('re', 0.0)))))
    for kk in keys:
        A[kk].extend(extra[kk])
    return made, last


def selftest():
    fails = []

    def check(name, ok, detail=""):
        print("  %-62s %s%s" % (name, "ok" if ok else "FAIL", ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    check("the time table: 01H 0.1 ms, 61H 340 ms (the default), 73H 1 s",
          time_ms(1) == 0.1 and time_ms(0x61) == 340.0 and time_ms(0x73) == 1000.0
          and all(time_ms(v + 1) > time_ms(v) for v in range(1, 0x73)))
    d = device({'macro': 4})
    check("Pan Delay 1: left at 250 ms, right at 500, no center, feedback +10",
          [(round(t * 1000), s) for t, _, s in d['taps']] == [(250, 'l'), (500, 'r')]
          and abs(d['fb'] - 10 / 64.0) < 1e-9)
    r = repeats(device({'macro': 0}), 1.0, 1000.0, 48000)
    check("Delay 1: repeats every 340 ms at a quarter of the last (feedback +16)",
          [x[2] for x in r[:3]] == [16320, 32640, 48960]
          and abs(r[1][3] / r[0][3] - 0.25) < 1e-9)
    check("negative feedback inverts every other repeat (Pan Repeat)",
          any(x[3] < 0 for x in repeats(device({'macro': 9}), 1.0, 1000.0, 48000)))
    check("a file's own time after the macro wins",
          abs(device({'macro': 0, 'time': 0x50})['tc'] - 0.1) < 1e-9)
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
