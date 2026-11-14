#!/usr/bin/env python3
"""The user drum set editor (livetui's U, nvlive's): python3 tests/live/udrum_panel_check.py

The editor sets a user set's key by sending the GS message a sequencer would
(41 10 42 12 21 dp rr vv: live.udrum_send, nvlive's udrum_queue), and a
preset and the session keep the sets as [set, key, code, value] rows sent
again when loaded (live.udrum_from / udrum_recall; nvlive's the same).
Checked:

  bytes     the editor's messages are the very exclusives userdrums.mid
            carries -- the file whose effects (the 808's kick, a snare up two,
            a hat panned, an open hat not received) tests/live/effects.py
            measures in live.Live and nvlive -- so what it sends is heard
  live      live.Live: the editor's calls reach the set; a preset holds it;
            loaded on another Live, the same
  names     the live export's DKEY (nvlive's sets and key names) as livetui
            names them (drum_key_name)
  nvlive    nvlive --test playing userdrums.mid: the session's user_drums
            live's udrum_from; that session loaded by nvlive (a file with
            none) and saved again, the same

Exits 1 if any check fails.
"""
import json
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))
os.environ.setdefault("TUNING_NATIVE_TONE", "off")
import mido  # noqa: E402


def sections(path):
    """An export's sections: {tag: bytes} (those written tag, length, bytes)."""
    out = {}
    data = open(path, "rb").read()
    at = data.find(b"DKEY")
    if at >= 0:
        n = struct.unpack("<i", data[at + 4:at + 8])[0]
        out["DKEY"] = data[at + 8:at + 8 + n]
    return out


def main():
    bad, n = 0, 0

    def check(what, ok, detail=""):
        nonlocal bad, n
        n += 1
        bad += not ok
        print("  %-66s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    import percussion_map as PM

    def drain_apply(lv):
        with lv.lock:
            ev = [m for _t, m in lv.events]
            lv.events.clear()
        for m in ev:
            if m.type == "sysex":
                lv._sysex(0, m)
        return ev

    # THE BYTES
    lv = L.Live(program=0, rate=48000, frames=128)
    f = mido.MidiFile(os.path.join(HERE, "midi", "userdrums.mid"))
    file_msgs = [m for tr in f.tracks for m in tr if m.type == "sysex" and B.parse_gs_user_drum(m.data)]
    codes = {v: k for k, v in L.Live.UDRUM_CODES.items()}
    for m in file_msgs:
        s, k, par, v = B.parse_gs_user_drum(m.data)
        lv.udrum_send(s, k, par, v)
    sent = drain_apply(lv)
    check("the editor's messages: userdrums.mid's %d exclusives byte for byte" % len(file_msgs),
          len(file_msgs) >= 8 and [tuple(m.data) for m in sent] == [tuple(m.data) for m in file_msgs])
    check("...every one a setting the editor offers",
          all(B.parse_gs_user_drum(m.data)[2] in L.Live.UDRUM_CODES for m in file_msgs), "%s" % sorted(codes))

    # LIVE: state, a preset, loaded again
    st = lv.udrum_state(0)
    check("live.Live: the editor's calls reach the set",
          st.get(36, {}).get('src_set') == 25 and st.get(38, {}).get('note') == 42 and st.get(46, {}).get('rxon') == 0,
          "%s" % {k: st[k] for k in sorted(st)})
    rows = L.preset_from(lv)["user_drums"]
    lv2 = L.Live(program=0, rate=48000, frames=128)
    L.udrum_recall(lv2, rows)
    drain_apply(lv2)
    check("live.Live: a preset keeps the sets (%d rows); loaded, the same" % len(rows),
          lv2.uset == lv.uset and len(rows) == sum(len(d) for d in lv.uset.values()))
    lv2.gs_reset()
    drain_apply(lv2)
    check("live.Live: a GS reset leaves them (the module's memory)", lv2.uset == lv.uset)

    # THE NAMES, in the live export
    import nvlive_check as NC
    import native as N
    tmp = tempfile.mkdtemp(prefix="udpanel")
    nvx = NC.live_export(tmp, "hall")
    got = sections(nvx).get("DKEY", b"").decode("utf-8").split("\n")
    want = []
    for k in sorted(PM.DRUM_SETS):
        if k >= 128 or k in B.USER_DRUM_SETS:
            continue
        want.append("S\t%d\t%s" % (k, PM.drum_set_name(k)))
        for nn in range(128):
            import livetui as TUI
            nm = TUI.drum_key_name(nn, k)
            if nm:
                want.append("K\t%d\t%d\t%s" % (k, nn, nm))
    check("the live export's sets and key names: livetui's (%d lines)" % len(want), got == want,
          "%s" % [(a, b) for a, b in zip(got, want) if a != b][:3])

    # NVLIVE: the session's sets, and that session loaded
    nvl = N.build_nvlive()
    plain = mido.MidiFile(ticks_per_beat=480)
    tp = mido.MidiTrack()
    plain.tracks.append(tp)
    tp.append(mido.Message("note_on", channel=0, note=60, velocity=90, time=48))
    tp.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=240))
    fp = os.path.join(tmp, "plain.mid")
    plain.save(fp)

    def nv_session(fm, sess, secs):
        subprocess.run([nvl, nvx, "--test", fm, os.path.join(tmp, "o.wav"), "--program=0", "--seconds=%g" % secs,
                        "--cpu", "--no-register", "--session=" + sess], check=True, capture_output=True)
        return json.load(open(sess)).get("user_drums")

    s1 = os.path.join(tmp, "s1.json")
    got = nv_session(os.path.join(HERE, "midi", "userdrums.mid"), s1, 6.0)
    lv3 = L.Live(program=0, rate=48000, frames=128)
    for m in file_msgs:
        lv3._sysex(0, m)
    want = L.udrum_from(lv3)
    check("nvlive: the session's user drum sets as live's (%d rows)" % len(want), got == want,
          "\n    nv %s\n    py %s" % (got, want) if got != want else "")
    s2 = os.path.join(tmp, "s2.json")
    with open(s1) as fh:
        js = json.load(fh)
    with open(s2, "w") as fh:
        json.dump(js, fh)
    got2 = nv_session(fp, s2, 1.5)
    check("nvlive: that session loaded (a file with none), saved again: the same", got2 == want, "%s" % got2)
    print("user drum set editor: %d checked, %d failed" % (n, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
