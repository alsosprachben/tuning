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
python3 live.py --tui --port "USB Midi" --frames 32 --threads 3   # heavy polyphony
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
python3 live.py --selftest    # 61 behaviour checks, no audio or MIDI needed
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
| mod wheel | vibrato: 35 cents deeper **and 25% faster** at full (`mod_cents`, `mod_rate`) |
| mod wheel *on the organ* | **draws stops** in crescendo order: 8′ 4′ 2′ 2⅔ 16′ 5⅓ |
| aftertouch | crescendo, +8 dB and brighter together (`press_db`, `press_tilt`) |
| mod wheel *with layers* | each part answers in its own way at once — the organ layer draws stops while the string layer vibrates |
| sustain pedal (CC64) | holds the damper off (piano) |
| CC123 | all notes off — panic |

Pitch bend, mod wheel and aftertouch are all phase-continuous: they recompute the
partial's total phase and put the difference back into its anchor, so nothing
clicks. That includes the vibrato RATE, which sits inside the accumulated phase
as well as the depth — moving it without re-deriving the anchor steps every
partial by about 53 radians, eight whole cycles — **and the vibrato's own LFO
phase**, which is `2πr·t + vp` in absolute time, so a rate change moves it by
`2π(r1−r0)·t`. That one grows with the note's age (0.35 rad for one MIDI step on
a 5 s note, 44 rad for a full sweep) and lands on every partial of every player
at the same instant, which is audible as a shared lurch in an ensemble that is
built on never having one. `vp` is rotated so the LFO changes speed and carries
on from where it was.

On a **solo** voice the wheel gives each note of a chord its own vibrato phase
and rate (`solo_vibrato_spread`, ±3.5%), because a player can only sound one note
at a time — four notes on a trumpet patch are four trumpeters, and four
trumpeters do not lock. Resting depth stays 0, so it plays dead straight until
the wheel moves. Set the spread to **0** for one locked vibrato across
everything: right for a synth lead, and it turns the wheel into a tempo control.

On a section the wheel **deepens and quickens what each player was already
doing** rather than writing one value over all of them: seven violinists go from
3.7–4.8 cents at 4.8–6.3 Hz to 35–45 cents at 6.0–7.9 Hz, keeping their spread.
`section_vibrato_cents` must stay non-zero for that — at 0 a player has no depth,
rate or phase of their own for the wheel to take proportions from. A stop drawn mid-chord speaks as a **fresh pipe**, with its own attack.

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

Steady state, one 128-frame block with ten keys held (budget 2.67 ms):

| configuration | partials | median | load |
|---|---|---|---|
| trumpet | 320 | 0.84 ms | 31% |
| strings | 2 623 | 1.21 ms | 45% |
| strings + trumpet | 2 943 | 1.92 ms | 72% |
| 2× strings | 5 246 | 2.28 ms | 85% |
| 3× strings | 7 869 | 3.36 ms | **126%** |

**But the attack costs far more than the steady state**, and that is where a
click comes from. The chiff is a per-sample random phase on every partial — a
hash plus a `sincosf`, inside the sample loop — and it runs for the whole
attack. A six-note string chord:

| | attack blocks | steady state |
|---|---|---|
| cost per block | **2.5 ms** | 0.85 ms |

That is 92 ms spent at ~95% of budget while the chiff speaks, exactly when you
have six keys down. It bites hardest on the voices where the noise *is* the
sound: snare 3.0, brass 2.6, breath and seashore 2.4, flue organ 1.3.

### Threads

`--threads N` splits the partial table across cores and sums the results.
Partials are independent, the kernel accumulates into its buffers, and `ctypes`
releases the GIL, so it is genuinely parallel from Python.

| active partials | 1 thread | 3 threads | gain |
|---|---|---|---|
| 280 | 0.72 ms | 0.72 ms | 1.00× |
| 560 | 1.27 ms | 1.32 ms | 0.96× |
| 840 | 1.91 ms | 1.52 ms | 1.25× |
| 1 680 | 3.58 ms | 2.50 ms | 1.43× |
| 2 415 | 5.05 ms | 3.41 ms | 1.48× |

So it only engages above `PARALLEL_MIN` (700 occupied slots) — below that the
thread wakeups cost more than the split saves. 3 is usually the best number; the
panel has it as a live control, next to the `cpu` meter that tells you whether
you need it.

Two things this depends on. **The split must follow occupancy, not capacity**:
slots come off the front of the free list, so an even split of `[0, capacity)`
handed thread 0 every active partial and measured *slower* than one thread.
And **splitting changes the order of a float sum**, so the output differs from
the single-threaded path in its last bits — measured 2.5e-6 relative, −112 dB.
Offline rendering never comes through this path and stays bit-identical.

The kernel's own OpenMP does not help here: it parallelises over *time chunks*,
and `synth_window` passes `CHUNK = SR`, so a 128-frame block is one chunk.

### Real-time priority

Worth checking before blaming the synth:

```sh
ulimit -r        # 0 means the audio thread cannot ask for real-time priority
```

PipeWire's own `pw-data-loop` runs `RR` priority 20, but a PortAudio stream
going through the ALSA-compat shim lands on a plain `TS` thread. At 90% of
budget that is enough to click whenever something else wants the core.
`/etc/security/limits.d/25-pw-rlimits.conf` already grants `rtprio 95` to
`@pipewire`, so joining that group is the fix:

```sh
sudo usermod -aG pipewire "$USER"     # then log out and back in
```

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

## Render the corpus

```sh
./render-corpus.sh                # everything in corpus.txt, to ~/Downloads/bwx-renders
./render-corpus.sh a.mid b.mid    # just these
```

168 files, one at a time, to MP3. `corpus.txt` is the list. `TUNING_MASTER_DB=-14`
leaves room for the reverb and the final -1 dBFS normalise, and the reverb is one
hall for the whole set on purpose — these are comparison renders, and per-voice
spaces would make the survey uneven.

Serial rather than parallel: a parallel run was killed part-way once, and an even
survey matters more here than speed. About five seconds for a 90-second piece.
