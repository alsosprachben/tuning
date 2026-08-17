#!/usr/bin/env python3
"""Play a MIDI straight to the audio device via the block synth engine.

Now that synthesis runs ~40-60x faster than playback, we can play instead of
writing a wav. This builds the partial table, synthesises the piece (a fraction
of a second for the kernel; the one-time build dominates startup), normalises to
-1 dBFS, and streams raw stereo to `aplay`/`play`/`pw-play`, whose buffer paces
playback in real time. The kernel is windowed (synth_window renders any absolute
range, statelessly), so a future live/interactive front-end can synthesise
per audio block instead of pre-rendering -- this player just doesn't need to.

Usage: play.py IN.mid [tuner]   (tuner default: hybrid)
"""
import sys, time, shutil, subprocess
import numpy as np
import blockrender as B

SR = 44100
CHUNK = 8192          # samples per write; aplay's buffer provides the pacing

def player_cmd():
    if shutil.which("aplay"):
        return ["aplay", "-q", "-f", "S32_LE", "-r", str(SR), "-c", "2", "-"]
    if shutil.which("play"):
        return ["play", "-q", "-t", "raw", "-e", "signed", "-b", "32", "-r", str(SR), "-c", "2", "-"]
    if shutil.which("pw-play"):
        return ["pw-play", "--format=s32", "--rate=%d" % SR, "--channels=2", "-"]
    sys.exit("no audio player found (need aplay, play, or pw-play)")

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: play.py IN.mid [tuner]")
    path = sys.argv[1]; tuner = sys.argv[2] if len(sys.argv) > 2 else "hybrid"

    sys.stderr.write("preparing %s (%s) ...\n" % (path, tuner)); sys.stderr.flush()
    t0 = time.time()
    prep = B.prepare(path, tuner)
    L, R = B.synth_window(prep, 0, prep["N"])
    peak = float(max(np.abs(L).max(), np.abs(R).max())) or 1.0
    g = 10 ** (-1.0 / 20.0) / peak                 # normalise to -1 dBFS
    st = np.empty(len(L) * 2, np.float32)
    st[0::2] = np.clip(L * g, -1, 1); st[1::2] = np.clip(R * g, -1, 1)
    data = (st * 2147483647.0).astype("<i4")
    sys.stderr.write("ready: %d partials, %.1fs audio, %.2fs to build+synth -- playing\n"
                     % (prep["P"], prep["total"], time.time() - t0)); sys.stderr.flush()

    proc = subprocess.Popen(player_cmd(), stdin=subprocess.PIPE)
    try:
        for i in range(0, len(L), CHUNK):
            proc.stdin.write(data[i * 2:(i + CHUNK) * 2].tobytes())
            sys.stderr.write("\r  %5.1f / %.1f s" % (i / SR, prep["total"])); sys.stderr.flush()
        proc.stdin.close(); proc.wait()
        sys.stderr.write("\n")
    except KeyboardInterrupt:
        proc.terminate(); sys.stderr.write("\nstopped\n")
    except BrokenPipeError:
        pass

if __name__ == "__main__":
    main()
