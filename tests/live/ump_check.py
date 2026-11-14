#!/usr/bin/env python3
"""native/ump.h against ump.py and alsaump.py: python3 tests/live/ump_check.py

nvlive's MIDI 2.0 inputs, each against the Python it ports:

  bridge    the keyboard's MIDI 1.0 through the bridge (--midi2, --midi2-pitch)
            -- ump.Midi1to2 then ump.decode, as live._bridge has it -- on a
            sequence of notes, controllers, RPNs and NRPNs (the per-note bend
            range among them), bank select and a program, the controllers the
            MIDI 2.0 Protocol ignores; and with just:C's pitch on every key
  timeline  a Clip File's and a raw UMP stream's packets and times (--midi2-play:
            ump.timeline)
  decode    every packet of those files (live.on_ump's ump.decode): the MIDI 2.0
            demo's 32-bit values at the nearest MIDI 1.0 number, as nvlive takes them
  alsa      a MIDI 2.0 port in the ALSA sequencer (--ump): alsaump's packets
            sent to it, received word for word (skipped where alsa-lib or the
            kernel has no UMP)

Prints each with its word; exits 1 if any differs.
"""
import math
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
import mido  # noqa: E402
import ump as U  # noqa: E402


def ev_tuple(e):
    """ump.Ev -> the host's (type, channel, a, b, value), as nvlive queues it."""
    t = e.type
    if t == "note_on":
        return (0, e.channel, e.note, e.velocity, e.attr_pitch if e.attr_pitch is not None else math.nan)
    if t == "note_off":
        return (1, e.channel, e.note, None, math.nan)        # (its velocity: read by nothing)
    if t == "control_change":
        return (2, e.channel, e.control, e.value, math.nan)
    if t == "aftertouch":
        return (3, e.channel, e.value, 0, math.nan)
    if t == "pitchwheel":
        return (4, e.channel, e.pitch, 0, math.nan)
    if t == "program_change":
        return (5, e.channel, e.program, 0, math.nan)
    if t == "polytouch":
        return (7, e.channel, e.note, e.value, math.nan)
    if t == "pn_pitch":
        return (8, e.channel, e.note, 0, e.semitones)
    if t == "pn_bend":
        return (8, e.channel, e.note, 1, e.value)
    if t == "pn_bend_range":
        return (8, e.channel, 0, 2, e.semitones)
    if t == "pn_mgmt":
        return (8, e.channel, e.note, 3 | (16 if e.reset else 0) | (32 if e.detach else 0), 0.0)
    if t == "sysex":
        return (6,) + tuple(e.data)
    return None


def near(v):
    """A value at the nearest MIDI 1.0 number (half away from zero: llround)."""
    return int(math.floor(v + 0.5)) if v >= 0 else -int(math.floor(-v + 0.5))


def native_lines(out):
    rows, ign = [], None
    for ln in out.splitlines():
        p = ln.split()
        if p[0] == "ignored":
            ign = int(p[1])
        elif p[0] == "6":
            rows.append(tuple(int(x) for x in p))
        else:
            v = float(p[4])
            rows.append((int(p[0]), int(p[1]), int(p[2]), int(p[3]), v))
    return rows, ign


def same(py, nv, round_values=False):
    if len(py) != len(nv):
        return False
    for a, b in zip(py, nv):
        if round_values and a[0] != 6:          # (a value, a pressure, a wheel: the nearest number)
            a = tuple(near(x) if i in (2, 3) and isinstance(x, float) else x for i, x in enumerate(a))
        if a[0] == 6 or b[0] == 6:
            if a != b:
                return False
            continue
        if a[:3] != b[:3]:
            return False
        if a[3] is not None and a[3] != b[3]:
            return False
        if a[0] in (2, 3, 4, 7) and round_values:
            continue
        if math.isnan(a[4]) != math.isnan(b[4]) or (not math.isnan(a[4]) and a[4] != b[4]):
            return False
    return True


def bridge_seq():
    M = mido.Message
    cc = lambda c, v, ch=0: M("control_change", channel=ch, control=c, value=v)
    return [
        M("note_on", channel=0, note=60, velocity=100), M("note_on", channel=0, note=60, velocity=0),
        cc(1, 64), cc(0, 121), cc(32, 2), M("program_change", channel=0, program=10),
        cc(101, 0), cc(100, 0), cc(6, 12), cc(38, 0),                      # RPN 0/0: the bend range
        cc(101, 0), cc(100, 7), cc(6, 3), cc(38, 64),                      # RPN 0/7: the per-note bend range
        cc(99, 1), cc(98, 8), cc(6, 70), M("note_on", channel=1, note=64, velocity=90),   # an NRPN, sent by the note
        cc(38, 5),                                                         # a CC38 with no CC6 held: the latest MSB
        cc(6, 20), cc(6, 21),                                              # a CC6 sends the one held
        cc(96, 0), cc(97, 0), cc(88, 10),                                  # the MIDI 2.0 Protocol's ignored
        M("aftertouch", channel=2, value=33), M("polytouch", channel=2, note=61, value=77),
        M("pitchwheel", channel=3, pitch=-1234), M("pitchwheel", channel=3, pitch=8191),
        M("note_off", channel=0, note=62, velocity=40),
        cc(101, 127), cc(100, 127), cc(6, 9),                              # RPN null: nothing sent
        cc(101, 0), cc(100, 2), cc(6, 66),                                 # held to the end: flushed
    ]


def host_of(m):
    """A mido message as the host's MidiParse hands it on (type, ch, a, b)."""
    t = m.type
    if t == "note_on":
        return (0 if m.velocity else 1, m.channel, m.note, m.velocity)
    if t == "note_off":
        return (1, m.channel, m.note, m.velocity)
    if t == "control_change":
        return (2, m.channel, m.control, m.value)
    if t == "aftertouch":
        return (3, m.channel, m.value, 0)
    if t == "pitchwheel":
        return (4, m.channel, m.pitch, 0)
    if t == "program_change":
        return (5, m.channel, m.program, 0)
    if t == "polytouch":
        return (7, m.channel, m.note, m.value)


def main():
    tmp = tempfile.mkdtemp(prefix="umpcheck")
    exe = os.path.join(tmp, "ump_check")
    subprocess.check_call(["g++", "-std=c++17", "-O1", os.path.join(HERE, "ump_check.cpp"), "-o", exe, "-ldl"])
    bad = 0
    n = [0]

    def say(what, ok, detail=""):
        nonlocal bad
        print("  %-62s %s  %s" % (what, "ok" if ok else "DIFFERS", detail), flush=True)
        bad += not ok
        n[0] += 1

    # THE BRIDGE
    for spec in (None, "just:C", "et"):
        tr = U.Midi1to2(pitch_of=U.pitch_table(spec) if spec else None)
        py, ign, sx = [], 0, {}
        for m in bridge_seq():
            for pkt in tr.feed(m):
                for e in U.decode(pkt, sx):
                    if e.type == "ignored":
                        ign += 1
                    elif ev_tuple(e) is not None:
                        py.append(ev_tuple(e))
        for pkt in tr.flush():
            py.extend(ev_tuple(e) for e in U.decode(pkt, sx) if ev_tuple(e) is not None)
        inp = "".join("%d %d %d %d\n" % host_of(m) for m in bridge_seq())
        r = subprocess.run([exe, "bridge"] + ([spec] if spec else []), input=inp, capture_output=True, text=True)
        nv, nign = native_lines(r.stdout)
        say("bridge%s: %d events" % (" " + spec if spec else "", len(py)),
            r.returncode == 0 and same(py, nv) and ign == nign, "(ignored %s, native %s)" % (ign, nign))

    # THE FILES: timeline and decode
    demo = os.path.join(tmp, "midi2_demo.midi2")
    subprocess.check_call([sys.executable, os.path.join(ROOT, "examples", "midi2_demo.py"), demo],
                          stdout=subprocess.DEVNULL)
    files = [os.path.join(HERE, "midi", n) for n in ("m2_pernote.midi2", "m2_mpe_zone_raw.midi2",
                                                    "m2_gsvsense.midi2")] + [demo]
    for f in files:
        name = os.path.basename(f)
        tl = U.timeline(U.read(open(f, "rb").read())[0])
        r = subprocess.run([exe, "timeline", f], capture_output=True, text=True)
        rows = [ln.split() for ln in r.stdout.splitlines()]
        ok = r.returncode == 0 and len(rows) == len(tl) and all(
            float(a[0]) == t and tuple(int(w) for w in a[1:]) == tuple(p) for a, (t, p) in zip(rows, tl))
        say("timeline %s: %d packets" % (name, len(tl)), ok)
        py, ign, sx = [], 0, {}
        for _t, p in tl:
            for e in U.decode(p, sx):
                if e.type == "ignored":
                    ign += 1
                elif ev_tuple(e) is not None:
                    py.append(ev_tuple(e))
        inp = "".join(" ".join(str(w) for w in p) + "\n" for _t, p in tl)
        r = subprocess.run([exe, "decode"], input=inp, capture_output=True, text=True)
        nv, nign = native_lines(r.stdout)
        say("decode %s: %d events" % (name, len(py)),
            r.returncode == 0 and same(py, nv, round_values=(f == demo)) and ign == nign,
            "(ignored %s, native %s)%s" % (ign, nign, " at the nearest MIDI 1.0 value" if f == demo else ""))

    # THE ALSA PORT
    try:
        import alsaump
        sender = alsaump.UmpClient("ump_check_send", port_name="out")
    except Exception as e:
        print("  alsa: skipped (%s)" % e)
        print("ump: %d checked, %d failed" % (n[0], bad))
        return 1 if bad else 0
    p = subprocess.Popen([exe, "alsa", "3"], stdout=subprocess.PIPE, text=True)
    first = p.stdout.readline().split()
    if first[0] != "address":
        say("alsa: a MIDI 2.0 port", False, " ".join(first))
        p.kill()
        return 1
    dest = tuple(int(x) for x in first[1].split(":"))
    time.sleep(0.2)
    pkts = [U.m2_note_on(0, 0, 60, U.scale_up(100, 7, 16), 3, U.semitones_to_q(60.25, 9)),
            U.m2_per_note_bend(0, 0, 60, 0x90000000), U.m2_cc(0, 1, 11, 0x12345678),
            U.m2_note_off(0, 0, 60, 0x8000)]
    for pk in pkts:
        sender.send(pk, dest)
    out, _ = p.communicate(timeout=10)
    got = [tuple(int(w) for w in ln.split()[1:]) for ln in out.splitlines() if ln.startswith("ump")]
    say("alsa: %d UMPs to port %s, received word for word" % (len(pkts), first[1]),
        got == [tuple(x) for x in pkts], "(got %d)" % len(got))
    sender.close()
    print("ump: %d checked, %d failed" % (n[0], bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
