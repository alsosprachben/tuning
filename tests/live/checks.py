#!/usr/bin/env python3
"""THE VALIDATIONS: native against Python, file and live, every check this
port is held to -- then the effects (effects.py: that what was compared
moves the sound at all), the corpus and the selftest.

    python3 tests/live/checks.py [--only=NAME,...] [--skip=NAME,...] [--logs=DIR]
                                 [--state=FILE] [--corpus] [--selftest] [--effects]
                                 [--cap=3500M] [--list]

Each check runs on its own, in order, one at a time (they are heavy: a
native export is ~1 GB, a check's Python side as much again), each under a
memory cap (systemd-run's scope, where there is one -- --cap=0 for none) and
its own log (--logs, default tests/live/logs/). A check passes when it exits
0 and its last line says identical (nvrender_check's "0 differ", the host's
"0 failed"). --state=FILE keeps each result as it comes and skips those
already there on a rerun: an interrupted night resumes where it stopped.
It stops (exit 3) before a check if live.py or nvlive is playing -- the
machine is the player's first.

The MIDI files are tests/live/midi/ (made by make_midi.py where their maker
is kept; the older ones are fixtures as they were made). A few checks read
outside files (a piece of Ben's, files with a Leslie on CC80): their path
from the environment, the check skipped where it is absent.
"""
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MIDI = os.path.join(HERE, "midi")

# OUTSIDE FILES: (environment variable, default path)
EXTERNAL = {
    "BWX10": ("TUNING_TEST_BWX10", "~/Downloads/bwx10_core.mid"),
    "QKB_CC80": ("TUNING_TEST_QKB_CC80", "~/Downloads/midi/qkbttl02_cc80.mid"),
    "GRUNGE_CC80": ("TUNING_TEST_GRUNGE_CC80", "~/Downloads/midi/grunge_cc80.mid"),
    "ROUKA_CC80": ("TUNING_TEST_ROUKA_CC80", "~/Music/draculax/mpp6/ROUKA_cc80.mid"),
}
# ...and Holst's planets as mt32mux prepared them (examples/planets.py: a
# part a patch, stamped before each note) -- TUNING_TEST_PLANETS, the folder
for _pl in ("mercury", "venus", "mars", "jupiter", "saturn", "uranus"):
    EXTERNAL[_pl.upper()] = ("TUNING_TEST_PLANET_" + _pl.upper(),
                             os.path.join(os.environ.get("TUNING_TEST_PLANETS", "~/Downloads/planets_2026-10-14"),
                                          _pl, _pl + "_mux.mid"))

# THE CHECKS: (name, tool in examples/, its arguments, environment) -- an
# argument "@x.mid" is tests/live/midi/x.mid, "$NAME" an outside file
CHECKS = [
    # files: nvrender against blockrender
    ("files", "nvrender_check.py", ["@native/organ_beside_variation.mid", "@native/user_drum_sets.mid",
                                    "@native/meend_variations.mid", "@native/layered_registered.mid",
                                    "@native/mf104_bend.mid", "@probe_organ/d00_16.mid",
                                    "@probe_organ/g_16_0.mid", "@probe_organ/c08_16.mid"], {}),
    ("cm64", "nvrender_check.py", ["@native/cm64_mode.mid"], {"TUNING_CM64": "1", "TUNING_MAP": "1"}),
    ("leslie_cc80", "nvrender_check.py", ["$QKB_CC80", "$GRUNGE_CC80", "$ROUKA_CC80", "30"], {}),
    ("mt32mux_planets", "nvrender_check.py", ["$MERCURY", "$VENUS", "$MARS", "$JUPITER", "$SATURN", "$URANUS"],
     {}),
    ("gs_part_files", "nvrender_check.py", ["@gsrx.mid", "@gsrx_2port.mid", "@gsvsense.mid", "@userdrums.mid",
                                            "@drumdelay.mid", "@drumnrpn.mid", "@drumnrpn2.mid", "@rhythmpart.mid",
                                            "@cmx_live.mid"],
     {}),
    ("two_organs", "nvrender_check.py", ["@two_organs.mid"], {}),
    ("midi2_files", "nvrender_check.py", ["@m2_pernote.midi2", "@m2_gsvsense.midi2", "@m2_mpe_zone_raw.midi2",
                                            "@m2_organ.midi2", "@mpe_organ.mid"], {}),
    ("assign_files", "nvrender_check.py", ["@assign_mode.mid", "18"], {}),
    ("moog_cmx", "nvrender_check.py", ["@moog_cmx.mid"], {}),
    # a part's speaker and pickup (CC83, CC85: after the program change that
    # puts them back), a channel's Messenger mode (CC86), presets' setup measures
    ("choices_files", "nvrender_check.py", ["@pk_reset.mid", "@pk_strat_bridge.mid", "@pk_clav_anti.mid",
                                            "@pk_ibanez_inside.mid", "@cab_gt412.mid", "@cab_org16les.mid",
                                            "@msgr_mode.mid", "@setup_guitar_rig.mid", "@setup_organ_full.mid",
                                            "@setup_moog.mid", "4"], {}),
    ("preset_midi", "preset_midi_check.py", [], {}),
    ("mpe_files", "nvrender_check.py", ["@mpe_zone.mid", "@mpe/a_plain.mid", "@mpe/b_bends.mid",
                                        "@mpe/c_mvol.mid", "@mpe/d_press.mid", "@mpe/e_mgrbend.mid",
                                        "@mpe/f_m3neg.mid", "@mpe/g_mcc74.mid", "@mpe/h_mgrat.mid",
                                        "@mpe/i_memcc7.mid"], {}),
    # live: nvlive against live.Live, block for block
    ("w_organ", "nvlive_check.py", ["@wheel/organ.mid", "9", "--program=16"], {}),
    ("w_rockorgan", "nvlive_check.py", ["@wheel/rockorgan.mid", "6", "--program=18"], {}),
    ("w_crescendo", "nvlive_check.py", ["@wheel/crescendo.mid", "9", "--program=19"], {}),
    ("w_drive", "nvlive_check.py", ["@wheel/drive.mid", "9", "--program=29"], {}),
    ("w_tremolo", "nvlive_check.py", ["@wheel/tremolo.mid", "9", "--program=4"], {}),
    ("w_rockers", "nvlive_check.py", ["@wheel/rockers.mid", "9", "--program=7"], {}),
    ("w_drones", "nvlive_check.py", ["@wheel/drones.mid", "9", "--program=109"], {}),
    ("cm32p", "nvlive_check.py", ["@cm32p.mid", "7", "--programs"], {}),
    ("eastern", "nvlive_check.py", ["@eastern.mid", "6", "--program=104",
                                    "--eastern-at=3.2:raga:bel_todi/todi@c#"], {}),
    ("rolls", "nvlive_check.py", ["@rolls.mid", "14", "--drums", "--program=0", "--programs"], {}),
    ("kits", "nvlive_check.py", ["@kits.mid", "20", "--drums", "--program=0", "--programs"], {}),
    ("calc1", "nvlive_check.py", ["@calc1.mid", "3", "--programs"], {}),
    ("mt32set", "nvlive_check.py", ["@mt32set.mid", "14", "--programs"], {}),
    ("layered", "nvlive_check.py", ["@layered.mid", "12", "--programs"], {}),
    ("openring", "nvlive_check.py", ["@openring.mid", "7", "--program=28", "--bank=1"], {}),
    ("switching", "nvlive_check.py", ["@fast.mid", "31", "--programs"], {}),
    ("piano", "nvlive_check.py", ["$BWX10", "10", "--program=0"], {}),
    ("organ", "nvlive_check.py", ["$BWX10", "10", "--program=19"], {}),
    ("host", "host_api_check.py", ["$BWX10"], {}),
    ("gs_reverb", "nvlive_check.py", ["@gsreverb.mid", "6", "--program=0"], {}),
    ("gs_eq", "nvlive_check.py", ["@gseq.mid", "6", "--program=0"], {}),
    ("gs_eq48", "nvlive_check.py", ["@gseq.mid", "6", "--program=48"], {}),
    ("gs_chorus", "nvlive_check.py", ["@gschorus.mid", "5", "--program=0"], {}),
    ("gs_chorus48", "nvlive_check.py", ["@gschorus.mid", "5", "--program=48"], {}),
    ("gs_delay", "nvlive_check.py", ["@gsdelay.mid", "9", "--program=0"], {}),
    ("gs_efxmix", "nvlive_check.py", ["@gsefxmix.mid", "7", "--program=0"], {}),
    ("gs_resetsends", "nvlive_check.py", ["@gsresetsends.mid", "5", "--program=0"], {}),
    ("gs_rx", "nvlive_check.py", ["@gsrx.mid", "6", "--program=0"], {}),
    ("gs_rx16", "nvlive_check.py", ["@gsrx.mid", "6", "--program=16"], {}),
    ("gs_vsense", "nvlive_check.py", ["@gsvsense.mid", "3", "--program=0"], {}),
    ("gm_chorus", "nvlive_check.py", ["@gmchorus.mid", "6", "--program=0"], {}),
    ("gm_chorus48", "nvlive_check.py", ["@gmchorus.mid", "6", "--program=48"], {}),
    ("top_octave", "nvlive_check.py", ["@topoctave.mid", "5", "--program=0"], {}),
    ("dep1", "nvlive_check.py", ["@chords3.mid", "5", "--program=4", "--bank=8"], {}),
    ("chorus_gt", "nvlive_check.py", ["@chords3.mid", "5", "--program=27", "--bank=8"], {}),
    ("honkytonk", "nvlive_check.py", ["@wheel/honkytonk.mid", "8", "--program=3"], {}),
    ("drum_nrpn", "nvlive_check.py", ["@drumnrpn.mid", "4", "--drums", "--program=0", "--programs"], {}),
    ("drum_nrpn_pitch_pan", "nvlive_check.py", ["@drumnrpn2.mid", "4", "--drums", "--program=0",
                                                "--programs"], {}),
    ("mpe_live", "nvlive_check.py", ["@mpe_zone.mid", "4", "--programs"], {}),
    ("cmx_live", "nvlive_check.py", ["@cmx_live.mid", "7", "--program=81", "--programs"], {}),
    ("m2_live", "nvlive_check.py", ["@m2_pernote.midi2", "14", "--programs"], {}),
    ("assign_live", "nvlive_check.py", ["@assign_mode.mid", "16", "--beside", "--programs"], {}),
    ("ump_inputs", "../tests/live/ump_check.py", [], {}),
    ("input_watch", "../tests/live/input_watch_check.py", [], {}),
    ("cmx_panel", "../tests/live/cmx_panel_check.py", [], {}),
    ("udrum_panel", "../tests/live/udrum_panel_check.py", [], {}),
    ("pull", "../tests/live/pull_check.py", [], {}),
    ("pull_dense", "../tests/live/pull_check.py", ["@dense_pedal.mid", "12"], {}),
    ("parts_presets", "../tests/live/parts_presets_check.py", [], {}),
    ("stops", "../tests/live/stops_check.py", [], {}),
    ("tuning", "../tests/live/tuning_check.py", [], {}),
    ("efx", "../tests/live/efx_check.py", [], {}),
    ("synth_globals", "../tests/live/synth_globals_check.py", [], {}),
    ("cmx_host", "../tests/live/cmx_host_check.py", [], {}),
    ("udrum_host", "../tests/live/udrum_host_check.py", [], {}),
    ("controls_routes", "../tests/live/controls_routes_check.py", [], {}),
    ("busy_workers", "../tests/live/busy_check.py", [], {}),
    ("allocations", "../tests/live/alloc_check.py", [], {}),
    ("user_drums_live", "nvlive_check.py", ["@userdrums.mid", "4", "--drums", "--program=0", "--programs"], {}),
    ("user_set_part", "nvlive_check.py", ["@userdrums.mid", "4", "--drums", "--program=64"], {}),
    ("drum_delay", "nvlive_check.py", ["@drumdelay.mid", "5", "--drums", "--program=0", "--programs"], {}),
    ("rhythm_part", "nvlive_check.py", ["@rhythmpart.mid", "3", "--beside", "--program=0", "--programs"], {}),
    ("pk_reset_live", "nvlive_check.py", ["@pk_reset.mid", "4", "--program=0", "--programs"], {}),
    ("msgr_mode_live", "nvlive_check.py", ["@msgr_mode.mid", "3", "--program=0", "--programs"], {}),
    ("setup_moog_live", "nvlive_check.py", ["@setup_moog.mid", "4", "--program=0", "--programs"], {}),
    ("setup_rig_live", "nvlive_check.py", ["@setup_guitar_rig.mid", "4", "--program=0", "--programs"], {}),
]


def playing():
    """live.py or nvlive playing (the player's machine first)."""
    for pat in (["-x", "nvlive"], ["-f", r"^python3? [^ ]*(livetui|/live)\.py"]):
        if subprocess.run(["pgrep"] + pat, stdout=subprocess.DEVNULL).returncode == 0:
            return True
    return False


def resolve(args):
    """The arguments with @ and $ resolved; None where an outside file is absent."""
    out = []
    for a in args:
        if a.startswith("@"):
            a = os.path.join(MIDI, a[1:])
        elif a.startswith("$"):
            var, dflt = EXTERNAL[a[1:]]
            a = os.path.expanduser(os.environ.get(var, dflt))
            if not os.path.exists(a):
                return None
        out.append(a)
    return out


def passed(rc, last):
    return rc == 0 and bool(re.search(r"\bidentical\b|\b0 differ\b|\b0 failed\b", last))


def capped(cmd, cap, env):
    """cmd under systemd-run's memory cap where there is one; else (macOS)
    under examples/memcap.py's, the group's footprint watched."""
    if cap in ("0", ""):
        return cmd
    if not shutil.which("systemd-run"):
        mb = float(cap[:-1]) * (1024 if cap[-1] in "Gg" else 1) if cap[-1] in "MmGg" else float(cap) / 1048576.0
        return [sys.executable, os.path.join(ROOT, "examples", "memcap.py"), "--cap=%g" % mb, "--"] + cmd
    pre = ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=" + cap, "-p", "MemorySwapMax=0"]
    for k, v in env.items():
        pre += ["-E", "%s=%s" % (k, v)]
    return pre + cmd


def run_limited(cmd, secs, **kw):
    """subprocess.run under a time limit: GNU timeout where there is one (as
    always on Linux), else (macOS) subprocess's own -- 124 when it ran out."""
    if shutil.which("timeout"):
        return subprocess.run(["timeout", str(secs)] + cmd, **kw)
    try:
        return subprocess.run(cmd, timeout=secs, **kw)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124)


def main(argv):
    opt = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else "") for a in argv if a.startswith("--")}
    if "list" in opt:
        for name, tool, args, env in CHECKS:
            print("%-22s %s %s" % (name, tool, " ".join(args)))
        return 0
    only = set(filter(None, opt.get("only", "").split(",")))
    skip = set(filter(None, opt.get("skip", "").split(",")))
    logs = opt.get("logs") or os.path.join(HERE, "logs")
    os.makedirs(logs, exist_ok=True)
    state = opt.get("state")
    done = {}
    if state and os.path.exists(state):
        for ln in open(state):
            m = re.match(r"(\S+) \(exit (-?\d+)\): (.*)", ln.rstrip("\n"))
            if m:
                done[m.group(1)] = (int(m.group(2)), m.group(3))
    cap = opt.get("cap", "3500M")
    env0 = dict(os.environ)
    if "NV_EXPORT_CACHE" not in env0:
        env0["NV_EXPORT_CACHE"] = os.path.join(logs, "nvx")
    os.makedirs(env0["NV_EXPORT_CACHE"], exist_ok=True)
    fails = 0

    def record(name, rc, last):
        line = "%s (exit %d): %s" % (name, rc, last)
        print(line, flush=True)
        if state:
            with open(state, "a") as f:
                f.write(line + "\n")

    for name, tool, args, env in CHECKS:
        if (only and name not in only) or name in skip:
            continue
        if name in done:
            rc, last = done[name]
            fails += not passed(rc, last)
            print("%s (exit %d): %s  [earlier]" % (name, rc, last))
            continue
        a = resolve(args)
        if a is None:
            print("%s: skipped (an outside file is absent)" % name)
            continue
        if playing():
            print("playing: stopped before %s" % name)
            return 3
        e = dict(env0, **env)
        cmd = capped([sys.executable, os.path.join(ROOT, "examples", tool)] + a, cap, dict(env, NV_EXPORT_CACHE=e["NV_EXPORT_CACHE"]))
        log = os.path.join(logs, name + ".log")
        t0 = time.time()
        with open(log, "w") as f:
            rc = run_limited(cmd, 5400, cwd=ROOT, env=e, stdout=f, stderr=subprocess.STDOUT).returncode
        lines = [ln for ln in open(log).read().strip().splitlines() if not ln.startswith("memcap:")]
        last = (lines or [""])[-1]                      # (memcap.py's peak: its own line, after the check's)
        fails += not passed(rc, last)
        record(name, rc, last + "  (%.0f s)" % (time.time() - t0))
    if "effects" in opt and not (only and "effects" not in only):
        if playing():
            print("playing: stopped before the effects")
            return 3
        rc = subprocess.run([sys.executable, os.path.join(HERE, "effects.py"), "--logs=" + logs], cwd=ROOT,
                            env=env0).returncode
        fails += rc != 0
    if "corpus" in opt:
        if playing():
            print("playing: stopped before the corpus")
            return 3
        cst = os.path.join(logs, "corpus.state")
        rc = subprocess.run([os.path.join(ROOT, "examples", "corpus_check.sh"), cst, "20"], cwd=ROOT, env=env0,
                            stdout=open(os.path.join(logs, "corpus.log"), "w"), stderr=subprocess.STDOUT).returncode
        tally = {}
        for ln in open(cst) if os.path.exists(cst) else ():
            w = (ln.split("\t") + [""])[1].split(" ")[0]
            tally[w] = tally.get(w, 0) + 1
        record("corpus", rc, "  ".join("%s %d" % kv for kv in sorted(tally.items())))
        fails += rc != 0 or set(tally) - {"identical"} != set()
    if "selftest" in opt:
        if playing():
            print("playing: stopped before the selftest")
            return 3
        log = os.path.join(logs, "selftest.log")
        cmd = capped([sys.executable, os.path.join(ROOT, "live.py"), "--selftest"], cap, {})
        rc = run_limited(cmd, 7200, cwd=ROOT, env=env0, stdout=open(log, "w"),
                         stderr=subprocess.STDOUT).returncode
        txt = open(log).read()
        record("selftest", rc, "%d ok, %d FAIL" % (txt.count(" ok"), txt.count(" FAIL")))
    print("%d failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
