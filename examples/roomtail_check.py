#!/usr/bin/env python3
"""Does native/nvroomtail write what roomtail.py writes? Byte for byte:

    python3 examples/roomtail_check.py [--export=PATH] [--long]

Each case a dry WAV and its sidecar (IN.room.json, IN.send.wav) as a render
leaves them, given to both: roomtail.py (the reference) and nvroomtail (its
rooms from a live export's LROOMS -- --export, else the cached live export
nvlive_check makes). The cases: a blockrender render in the hall (44.1 kHz);
then made here at 48 kHz -- the studio and the booth (small rooms, their
modes ringing), the chapel, a GS reverb's level and time on the chamber, the
plate, the delay (its feedback), the pan delay, outdoors (no tail), a send
bus, a uniform send, a loud mix (the peak over full scale: scaled), 16- and
24-bit input; --long a minute of it (many segments). Exits 1 if any differs.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def write(path, a, sr, bits=32):
    import wave
    w = wave.open(path, "wb")
    w.setnchannels(2)
    w.setsampwidth(bits // 8)
    w.setframerate(sr)
    c = np.clip(a, -1, 1).reshape(-1)
    if bits == 32:
        w.writeframes((c * 2147483647.0).astype("<i4").tobytes())
    elif bits == 16:
        w.writeframes((c * 32767.0).astype("<i2").tobytes())
    else:
        v = (c * 8388607.0).astype("<i4")
        b = np.stack([(v & 0xFF), (v >> 8) & 0xFF, (v >> 16) & 0xFF], 1).astype(np.uint8)
        w.writeframes(b.tobytes())
    w.close()


def music(sr, secs, seed=3, amp=0.3):
    """a few struck tones, decaying, left and right apart"""
    rng = np.random.default_rng(seed)
    n = int(secs * sr)
    t = np.arange(n) / sr
    x = np.zeros((n, 2))
    for k in range(int(secs * 3)):
        t0, f = rng.uniform(0, secs - 0.5), rng.choice([110.0, 220.0, 330.0, 440.0, 660.0, 990.0])
        m = t >= t0
        e = np.exp(-(t[m] - t0) * 3.0)
        s = sum(np.sin(2 * np.pi * f * h * (t[m] - t0)) / h for h in (1, 2, 3, 5))
        pan = rng.uniform(0.2, 0.8)
        x[m, 0] += amp * e * s * (1 - pan)
        x[m, 1] += amp * e * s * pan
    return x


def sidecar(path, room, extra=None, bands=True):
    d = {"bands": [{"hz": f, "q": q, "energy": 1e-3 if bands else 0.0}
                   for f, q in zip((63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0),
                                   (1.0, 1.1, 1.3, 1.6, 2.2, 3.1, 4.5, 6.0, 8.0))],
         "send": {}, "room_name": room, "tail_gain": 1.0, "tail_time": 1.0}
    d.update(extra or {})
    json.dump(d, open(path, "w"), indent=1)


def main(argv):
    import native as N
    import nvlive_check as NC
    exe = N.build_nvroomtail()
    tmp = tempfile.mkdtemp(prefix="roomtailchk")
    xp = next((a.split("=", 1)[1] for a in argv if a.startswith("--export=")), None) or NC.live_export(tmp, "hall")
    secs = 60.0 if "--long" in argv else 4.0
    sr = 48000
    cases = []
    # a render's own, in the hall
    br = os.path.join(tmp, "br.wav")
    subprocess.check_call([sys.executable, os.path.join(HERE, "blockrender.py"),
                           os.path.join(HERE, "tests", "live", "midi", "chords3.mid"), br], stdout=subprocess.DEVNULL)
    cases.append(("a blockrender render, the hall (44.1 kHz)", br))

    def made(name, room, extra=None, x=None, bits=32, send=None, bands=True):
        p = os.path.join(tmp, name + ".wav")
        write(p, music(sr, secs) if x is None else x, sr, bits)
        sidecar(os.path.splitext(p)[0] + ".room.json", room, extra, bands)
        if send is not None:
            write(os.path.splitext(p)[0] + ".send.wav", send, sr)
        return p
    for room in ("studio", "booth", "chapel", "church"):
        cases.append(("%s (48 kHz)" % room, made(room, room)))
    cases.append(("the chamber, a GS reverb's level 0.6 and time 1.3",
                  made("gs", "chamber", {"tail_gain": 0.6, "tail_time": 1.3})))
    cases.append(("the plate, its time 0.8", made("plate", "plate", {"tail_time": 0.8})))
    cases.append(("the delay, feedback 70", made("delay", "delay", {"delay_fb": 70})))
    cases.append(("the pan delay", made("pdelay", "pan_delay")))
    cases.append(("outdoors (no tail)", made("out", "outdoors")))
    x = music(sr, secs)
    cases.append(("a send bus (the chamber)", made("bus", "chamber", x=x, send=x * np.array([0.3, 1.4]))))
    cases.append(("a uniform send 0.5 (the hall)", made("usend", "hall", {"send": {"0": 0.5, "3": 0.5}})))
    cases.append(("a loud mix: the peak over full scale, scaled", made("loud", "grand_hall", x=music(sr, secs, amp=1.6))))
    cases.append(("16-bit input, no bands measured", made("b16", "hall", bits=16, bands=False)))
    cases.append(("24-bit input", made("b24", "large_chamber", bits=24)))
    bad = 0
    for what, p in cases:
        py, nat = p[:-4] + ".py.wav", p[:-4] + ".nat.wav"
        r1 = subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), p, py], capture_output=True, text=True)
        r2 = subprocess.run([exe, p, nat, "--export=" + xp], capture_output=True, text=True)
        same = r1.returncode == 0 and r2.returncode == 0 and open(py, "rb").read() == open(nat, "rb").read()
        detail = ""
        if not same:
            if r1.returncode or r2.returncode:
                detail = (r1.stderr + r2.stderr)[-300:]
            else:
                import roomtail as RT
                a, _ = RT.read_wav(py)
                b, _ = RT.read_wav(nat)
                detail = "lengths %d / %d" % (len(a), len(b)) if len(a) != len(b) else \
                    "%d samples differ, at most %.3g" % (int((a != b).sum()), float(np.abs(a - b).max()))
        bad += not same
        print("  %-62s %s  %s" % (what, "identical" if same else "DIFFERS", detail), flush=True)
    print("nvroomtail: %d of %d differ" % (bad, len(cases)))
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
