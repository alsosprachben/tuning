# tuning — a physically modelled synthesiser

Additive synthesis where every voice is built from what the instrument physically
does: air columns that mode-lock, bells that will not radiate below their flare
cutoff, bars tuned by undercutting, membranes that go sharp when struck hard.
There are no samples. The reasoning behind each voice lives in `tonelib.py`'s
comments and in the commit messages, which are the real documentation; this file
is only how to run it.

Two front ends share one C kernel (`synthkernel.c`): an offline renderer and a
live one. The kernel renders any absolute sample range statelessly, which is what
makes both possible from the same code.

## Play it live

Needs `python3-rtmidi` and `python3-pyaudio` (both apt).

Set the low-latency quantum **once per session** — it is a system-wide PipeWire
setting and does not persist:

```sh
pw-metadata -n settings 0 clock.force-quantum 64     # restore with 0
```

Then pick a voice:

```sh
python3 live.py --port "USB Midi" --frames 32 --program 0    # piano
python3 live.py --port "USB Midi" --frames 32 --program 19   # church organ
python3 live.py --port "USB Midi" --frames 32 --program 56   # trumpet
python3 live.py --port "USB Midi" --frames 32 --drums        # GM percussion
python3 live.py --port "USB Midi" --frames 32 --program 48 --headroom 8   # strings
```

`--program` takes any GM number; `patch_map.py` decides which voice it routes to.
Ctrl-C stops.

```sh
python3 live.py --list        # MIDI input names, to fill in --port
python3 live.py --selftest    # 21 behaviour checks, no audio or MIDI needed
python3 live.py --latency     # MIDI-to-DAC timing, measured as you play
```

### Controls

| control | effect |
|---|---|
| velocity | loudness; on the piano also **timbre**, via eight velocity bands |
| pitch bend | ±2 semitones (`bend_range`) |
| mod wheel | vibrato, 35 cents at full (`mod_cents`) |
| mod wheel *on the organ* | **draws stops** in crescendo order: 8′ 4′ 2′ 2⅔ 16′ 5⅓ |
| aftertouch | crescendo, +8 dB and brighter together (`press_db`, `press_tilt`) |
| sustain pedal (CC64) | holds the damper off (piano) |
| CC123 | all notes off — panic |

Pitch bend, mod wheel and aftertouch are all phase-continuous: they recompute the
partial's total phase and put the difference back into its anchor, so nothing
clicks. A stop drawn mid-chord speaks as a **fresh pipe**, with its own attack.

### Two settings that matter

**`--frames`** is both the audio block and the kernel's control block. They must
be equal: the kernel is window-independent only for block-aligned windows,
because the mode-lock pitch transient is computed from the clipped window start.
128 is safe, 32 is fastest.

**`--headroom`** is dB held back before the soft limiter. A live stream cannot
peak-normalise the way every offline render does, and the voice gains were
calibrated assuming it — a single kick peaks at 0.568 alone. 4 dB is the default;
use 6–8 for organ or strings.

### Measured latency

MIDI-to-DAC on this machine, several hundred notes per setting, no underruns:

| quantum | `--frames` | MIDI + queue | audio buffer | total |
|---|---|---|---|---|
| 1024 | 128 | — | — | 23.9 ms |
| 128 | 128 | 2.8 | 15.9 | 18.6 ms |
| 128 | 64 | 1.1 | 13.2 | 14.5 ms |
| 64 | 32 | 0.8 | 10.6 | **11.6 ms** |

Rendering a block is 0.14–0.29 ms, 11–21% of budget — the synth is not what you
wait for. The remaining floor is the ALSA-compat shim into PipeWire; going below
it means a native PipeWire or JACK client instead of PortAudio-over-ALSA.

## Render a file

```sh
python3 blockrender.py IN.mid OUT.wav hybrid    # the fast C renderer
python3 play.py IN.mid hybrid                   # render, then play it
./render.sh IN.mid OUT hybrid                   # the pypy reference renderer
```

`render.sh` is the slow, readable implementation the C kernel is checked against;
they agree to a fraction of a dB, and that is the correctness anchor for every
voice.

The third argument is the temperament: `hybrid` (A=441, the default for most of
this work), `hybridharm` (pure octaves, right for mode-locked pipes), `even`,
`stretch`, `meantone` (all at A=415), `linear`, `just`, `pyth`, `well`,
`bechstein`, `spiral` and others — see `tuner_registry` in `midilib.py`.

`TUNING_MASTER_DB` sets the output gain (default −9.3). Offline renders are
peak-normalised downstream, so it mainly matters live.

Sample rate defaults to 44100 and is set with `blockrender.set_sample_rate()`;
the kernel compiles one `.so` per rate, so 48000 costs a one-off rebuild.

## Caveat

The batch scripts used to render the ~168-file corpus (`rb.sh`, `renderlist.txt`)
currently live in a session scratchpad and will not survive. They should move
into this repo if that corpus is to be rebuilt again.
