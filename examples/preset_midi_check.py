#!/usr/bin/env python3
"""A PRESET's SETUP MEASURE, Python's against the engine's.

    python3 examples/preset_midi_check.py [PRESETS.json ...] [--keep=DIR]

live.preset_midi and native's nv_preset_midi_file (hostsession.cpp) write
each preset in each PRESETS.json (default: the test presets below, and the
presets.json beside live.py if there is one) -- compared byte for byte, and
the file read back by mido and by blockrender's parser. The test presets
cover what the writer decides: a part with no channel taking the first free
one, a drum part on channel 10 and one made a rhythm part elsewhere, two
parts on one channel, a GS variation and a map's tone, a cabinet and a
pickup, a muted part, a level above unity (clamped), a pan, the scene's
controls and a controller matrix exclusive, a name outside ASCII; organs'
stops -- the church organ's 28-bit word with old rank names, the
harmonium's CC43-45, a drawbar variation, the harpsichord, none drawn;
Moog panels -- CC86's Messenger mode and the chart's CCs, the part's own
knobs over the voice's (a switch, a foot, a mode, the voice's own touch),
knobs in older units left as the voice's, knobs on a piano ignored.
"""
import ctypes
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

TEST = {
    "guitar rig": {
        "parts": [
            dict(program=27, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=0.0,
                 muted=False, pickup="bridge", cabinet="guitar412"),
            dict(program=33, drums=False, channel=None, lo=0, hi=47, transpose=-12, level_db=-6.0,
                 muted=False, pickup="neck"),
            dict(program=0, drums=True, channel=None, lo=0, hi=127, transpose=0, level_db=-3.0, muted=False),
        ],
        "chanstate": ["control_change channel=0 control=91 value=40 time=0",
                      "control_change channel=0 control=0 value=8 time=0",
                      "control_change channel=1 control=10 value=30 time=0",
                      "sysex data=(65,16,66,18,64,17,64,1,42) time=0"],
    },
    "organ été / split": {
        "parts": [
            dict(program=16, drums=False, channel=3, lo=0, hi=127, transpose=0, level_db=4.0,
                 muted=False, cabinet="leslie", bank=8),
            dict(program=4, drums=False, channel=3, lo=60, hi=127, transpose=0, level_db=0.0, muted=False),
            dict(program=128 + 25, drums=True, channel=5, lo=0, hi=127, transpose=0, level_db=-1.5,
                 muted=True),
            dict(program=0, drums=False, channel=9, lo=0, hi=127, transpose=0, level_db=-40.0,
                 muted=False, pan=100, bank=3 * 128 + 1),
        ],
    },
    "organs": {
        "parts": [
            dict(program=19, drums=False, channel=None, lo=36, hi=96, transpose=0, level_db=0.0, muted=False,
                 drawn=["principal 8", "mixture", "4", "trompette 8", "vox humana 8"]),
            dict(program=20, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=-2.0, muted=False,
                 drawn=["cor anglais 1", "musette", "expression"]),
            dict(program=16, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=0.0, muted=False,
                 bank=127, drawn=["16", "8", "4", "perc 3rd B3"]),
            dict(program=6, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=0.0, muted=False,
                 drawn=["8", "4"]),
            dict(program=19, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=0.0, muted=False,
                 drawn=[]),
        ],
    },
    "moog": {
        "parts": [
            dict(program=81, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=0.0, muted=False,
                 cabinet="guitar12", synth=dict(cutoff=0.31, resonance=0.62, sync=True, osc1_octave=16,
                                                mode=2, a_vel=-1.0), synth_units=6),
            dict(program=80, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=0.0, muted=False,
                 synth=dict(cutoff=0.9), synth_units=5),
            dict(program=0, drums=False, channel=None, lo=0, hi=127, transpose=0, level_db=0.0, muted=False,
                 synth=dict(cutoff=0.2), synth_units=6),
        ],
    },
    "empty": {},
}


def main(argv):
    opt = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True)
           for a in argv if a.startswith("--")}
    files = [a for a in argv if not a.startswith("--")]
    import live as L
    import mido
    import blockrender as B
    import native as N
    so = N.lib()
    so.nv_preset_midi_file.argtypes = [ctypes.c_void_p] + [ctypes.c_char_p] * 3
    # AN ENGINE for its organs' stops (host_api_check's way: opened, not started)
    from nvlive_check import cached_export
    nvx = cached_export(tempfile.mkdtemp(prefix="presetmidi_x"), None, True)      # (a live export)
    so.nv_host_open_args.restype = ctypes.c_void_p
    so.nv_host_open_args.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int]
    av = [b"nvlive", nvx.encode(), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register", b"--no-drums"]
    host = so.nv_host_open_args(len(av), (ctypes.c_char_p * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert host, "the host refused"
    so.nv_preset_midi_file.restype = ctypes.c_int
    tmp = opt.get("keep") or tempfile.mkdtemp(prefix="presetmidi")
    os.makedirs(tmp, exist_ok=True)
    sets = []
    tp = os.path.join(tmp, "test_presets.json")
    with open(tp, "w") as fh:
        json.dump(TEST, fh)
    sets.append(tp)
    if not files and os.path.exists(L.PRESET_PATH):
        sets.append(L.PRESET_PATH)
    sets += files
    bad = n = 0
    for path in sets:
        with open(path) as fh:
            d = json.load(fh)
        for k, (name, pre) in enumerate(sorted(d.items())):
            n += 1
            py = os.path.join(tmp, "py_%d.mid" % k)
            nv = os.path.join(tmp, "nv_%d.mid" % k)
            L.preset_midi(pre, name).save(py)
            rc = so.nv_preset_midi_file(host, path.encode(), name.encode("utf-8"), nv.encode())
            a = open(py, "rb").read()
            b = open(nv, "rb").read() if rc == 0 else b""
            word = "identical" if a == b else ("native refused" if rc else "DIFFER at byte %d"
                                              % next((i for i in range(min(len(a), len(b))) if a[i] != b[i]),
                                                     min(len(a), len(b))))
            m = mido.MidiFile(py)
            pcs = sum(1 for x in m.tracks[0] if x.type == "program_change")
            try:
                B.parse(py)
                parsed = "parsed"
            except Exception as e:      # (a file the renderer cannot read: a failure too)
                parsed = "parse failed: %s" % e
                word = word if word != "identical" else "identical but " + parsed
            bad += word != "identical"
            print("  %s / %s: %d bytes, %d parts set, %s, %s"
                  % (os.path.basename(path), name, len(a), pcs, parsed, word), flush=True)
    print("preset_midi: %d of %d identical" % (n - bad, n))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
