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

Then either open the panel:

```sh
python3 live.py --tui --port "USB Midi" --frames 32
python3 live.py --tui --port "USB Midi" --frames 32 --preset kit-and-strings
```

or name one voice and play it straight away:

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
python3 live.py --selftest    # 31 behaviour checks, no audio or MIDI needed
python3 live.py --latency     # MIDI-to-DAC timing, measured as you play
```

## The panel

`--tui` is the same engine with a synthesiser interface over it: pick patches,
balance them, and **layer and split them across the keyboard** without leaving
the program.

The engine is multi-timbral. A **part** is one patch listening on one channel
over one range of keys, so two parts over the same keys is a *layer* and two over
different keys is a *split*. Each row of the table is a part; the columns are
what you can change about it, and the same two keys change every one of them.

| key | what it does |
|---|---|
| `tab` | move between the part table and the controls |
| arrows / `hjkl` | select a part, and a column within it |
| `-` `+` | change the selected cell (`_` and shifted `+` are coarse) |
| `enter` | **acts on the highlighted column** — `patch`, `tuner` and `stops` open a picker; `ch`, `lo`, `hi`, `tr`, `level` take a typed value (ranges accept `C3` as well as `48`) |
| `a` | **layer**: duplicate this part over the same keys |
| `s` | **split**: halve this part's range into two parts |
| `d` / `m` | remove / mute this part |
| `1`..`9` | on an organ part, draw or retire that stop |
| `-` `+` on `stops` | add and retire ranks in the organ's own crescendo order |
| `S` / `L` | save / load a preset |
| `P` | panic: all notes off |
| `?` / `q` | help / quit |

### Stops

The mod wheel is a crescendo pedal on an organ part, and it walks
`crescendo_order` — which deliberately **does not contain every rank**. The reed
organ's `trumpet` and the flue organ's `flute` and `mixture` are registration
choices, not places a crescendo passes through, so no amount of wheel will reach
them. Three ways to draw a rank by hand:

- `enter` on the **stops** column — every rank listed by name, `space` toggles,
  and each says whether the crescendo can reach it
- the **digit** printed next to the rank on the line under the selected part
- `-` / `+` on the stops column, which walks the crescendo order first and then
  the hand-drawn ranks

Any single rank can stand alone, so a reed organ on nothing but its `trumpet` is
one keystroke away. The tuner is per part too, so a mode-locked organ layer can
sit on `hybridharm` while the strings above it stay on `hybrid`.

**Patch and tuner changes build templates** (0.02 s for a kit, 0.67 s for the
piano's eight velocity bands) and run on a worker thread with a progress bar.
Everything else — channel, range, transpose, level, mute, stops — is a single
attribute write and takes effect on the next MIDI event.

Presets live in `presets.json`, next to the code. They are **data**: a part list
plus the control settings. A voice is still only ever defined in `tonelib.py`, so
there is no sound the engine can make that the repo does not describe in code.

### Controls

| control | effect |
|---|---|
| velocity | loudness; on the piano also **timbre**, via eight velocity bands |
| pitch bend | ±2 semitones (`bend_range`) |
| mod wheel | vibrato, 35 cents at full (`mod_cents`) |
| mod wheel *on the organ* | **draws stops** in crescendo order: 8′ 4′ 2′ 2⅔ 16′ 5⅓ |
| aftertouch | crescendo, +8 dB and brighter together (`press_db`, `press_tilt`) |
| mod wheel *with layers* | each part answers in its own way at once — the organ layer draws stops while the string layer vibrates |
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

**Headroom is not a fader.** It is applied when a note is stamped, so it changes
notes started after it and leaves everything already sounding alone. The panel's
`master` is the real one: `synth_window` reads `T.master_gain` every block, so it
moves what is already ringing. Master is capped at **0 dB** on purpose —
`synth_window` hard-clips to ±1 *after* the master gain and *before*
`Live.limit` ever sees the block, so above unity you clip inside the kernel where
the soft limiter cannot help.

### How much will it carry

One 128-frame block, measured with ten keys held (budget 2.67 ms):

| configuration | partials | median | load |
|---|---|---|---|
| trumpet | 320 | 0.84 ms | 31% |
| strings | 2 623 | 1.21 ms | 45% |
| strings + trumpet | 2 943 | 1.92 ms | 72% |
| 2× strings | 5 246 | 2.28 ms | 85% |
| 3× strings | 7 869 | 3.36 ms | **126%** |

So roughly **6 000 active partials** is the ceiling — two string sections
layered, or a string section with anything else on top. Bigger blocks do not
help: doubling `--frames` doubles the budget and the work together. The panel's
`cpu` meter reports the real figure per block and turns red before notes start
dropping, which the drop counter can only tell you afterwards.

The slab holds 16384 partials by default (`--capacity`); a layered string section
runs ~260 partials per key.

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

**The GIL is what makes background building possible.** PyAudio's callback is a
Python callback, so it needs the GIL, and `blockrender.prepare()` is pure Python
and holds it. At the default 5 ms switch interval — longer than the 2.67 ms
block budget — rebuilding the piano bank while playing measured **2.50
underruns/s**. `sys.setswitchinterval(0.0005)` in `live.py` takes that to
**0.00**, at no measurable cost to latency. If it ever stops being enough the
answer is `multiprocessing` with `spawn` and shared memory, not `fork`: forking a
process that has a live PortAudio callback thread inherits mutexes held by
threads that do not exist in the child.

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
