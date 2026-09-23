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
python3 live.py --selftest    # 413 behaviour checks, no audio or MIDI needed
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
| pitch bend *on a Leslie voice* | the **half-moon switch**: flick up or down to step stop → chorale → tremolo |
| mod wheel *on an amplified voice* | the **gain knob** — the Leslie's swell pedal, or a guitar amp's own gain |
| sustain pedal (CC64) | holds the damper off, on voices that have dampers |
| soft pedal (CC67) | *una corda* — the hammer reaches one string fewer |
| CC120 | all sound off — **the panic**; CC123 only lifts the keys |

**A Hammond has neither wheel**, so both are free for the controls it does
have. The tonewheels run off a synchronous motor, so the pitch is the mains and
there is nothing to bend; and a pitch wheel springs back to centre, which is the
wrong shape for a knob but the right one for a three-position switch read as
EDGE events — a flick steps the ladder, the spring return re-arms it. The mod
wheel then takes the swell pedal, which on a real rig sits in FRONT of a
fixed-gain amplifier: opening it is how a player makes the Leslie break up.

The wheel is gated on the voice HAVING an amplifier, not on having a rotor —
they were the same thing only because the Hammond was the first voice with one.
On a guitar the pitch wheel therefore stays a bend, which is what a guitar
wants. The distortion is computed off the audio thread and stamped on it — one
`tubeamp.emit` is about 7 ms and a 128-frame block is 2.9 — so it arrives a
block or two after the chord.

**How hard you play drives the amp too**, on a voice that sets `amp_reference`.
A Hammond's keys are on or off and its swell pedal sits in front of the
amplifier, so there the wheel is the whole story; a guitar's dynamics go into
the valve, and rendered, an 18 dB difference in picking produces 22.7 to
32.6 dB of difference in distortion. See `examples/guitar_check.py`.

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

## What MIDI it understands

The table under *Controls* above is about the panel — what a knob does to a
voice. This is the protocol: **twenty-six controllers in each, and CC91 in a file**,
plus program change, both aftertouches, the wheel and SysEx — GM System On,
GM 2 Scale/Octave Tuning, and Master Volume, Fine and Coarse Tuning.

| | |
|---|---|
| both renderers | CC1, CC5, CC6, CC7, CC10, CC11, CC38, CC64–CC67, CC84, CC93, CC96–CC101, CC120, CC121, CC123–CC127 |
| file only | CC91 |

That covers GM Level 1, plus GM 2's Scale/Octave tuning, chorus and reverb
sends, portamento, mono/poly mode, modulation depth range (RPN 5) and the
master controls. `midi.md` has the whole surface —
what each message does, what a voice is allowed to refuse, why the pitch wheel
is two different controls depending on whether it moves, and why a glide is a
length rather than a pitch. `remaining.md` has what is still missing, chiefly
GM 2's bank select and the brass glissando's harmonic lattice.

## Render a file

```sh
python3 blockrender.py IN.mid OUT.wav hybrid    # the fast C renderer
python3 play.py IN.mid hybrid                   # render, then play it
./render.sh IN.mid OUT hybrid                   # the pypy reference renderer
```

`render.sh` is the slow, readable implementation the C kernel is checked against;
they agree to a fraction of a dB, and that is the correctness anchor for every
voice.

The third argument is the temperament. `hybrid440` is the default, and
`hybrid` is the same temperament at the baroque A=415. `hybridharm` has pure
octaves, which is right for mode-locked pipes. Then there's `even` (A=440),
`stretch`, `meantone`, `werckmeister`, `sankey` (these at A=415), `linear`,
`just`, `pyth`, `well`, `bechstein`, `spiral` and others — see `tuner_registry`
in `midilib.py`.

**`gm2`** is the one to use when the *file* should own the tuning. It starts at
equal temperament, A=440, and obeys the file's MIDI Tuning Standard messages:
128-key dumps, single-note changes, and program selection by RPN. Every tuner
above is pre-loaded as a program. `examples/tuning_sysex.py --mts` writes any of
them into a file, stretched octaves and all. See `midi.md`.

`TUNING_MASTER_DB` sets the output gain (default −9.3). Offline renders are
peak-normalised downstream, so it mainly matters live.

Sample rate defaults to 44100 and is set with `blockrender.set_sample_rate()`;
the kernel compiles one `.so` per rate, so 48000 costs a one-off rebuild.

**The file renderer reads controls too** — ten of them, the pedals included,
and it reads them with an advantage the live engine does not have: it can see
the whole file before it renders a sample. That is how a damper knows, at the
note's onset, how long the note will end up ringing, and how the una corda
shift is a decision about which strings the hammer reaches rather than a gain
applied afterwards. `midi.md` lists what it answers and what it leaves to
`live.py`. A channel that sends CC91 also gets a `.send.wav` bus beside the
wav, which `roomtail.py` picks up on its own.

## Render the corpus

```sh
./render-corpus.sh                    # everything in corpus.txt, to ~/Downloads/bwx-renders
./render-corpus.sh a.mid b.mid        # just these
ROOM=church ./render-corpus.sh ...    # a different building
```

168 files, one at a time, to MP3. `corpus.txt` is the list.

**One room, told to both halves.** `TUNING_ROOM` is exported once, so
`blockrender` computes the first-order images against it and `roomtail.py`
convolves the diffuse field of the *same* room — reading the `.room.json`
sidecar the render leaves beside the wav, so the tail uses the directivity the
render actually measured rather than a scalar. This replaced a `sox reverb`
tacked on the end, which was a hall's early reflections in front of a reverb
unit's tail: two different rooms. `hall` by default; an organ wants `church`,
and that is not a reverb setting but a building four times the volume with a
tenth the absorption.

`TUNING_MASTER_DB=-14` leaves room for the tail and the final -1 dBFS
normalise — 2 dB lower than a single piece needs, because a survey has to hold
the loudest thing in the corpus, which since the electric guitars landed is an
overdriven one.

Serial rather than parallel: a parallel run was killed part-way once, and an
even survey matters more here than speed. A clean 90-second piece is about five
seconds. **A voice with a valve amplifier is not** — GM 18 and GM 26–31 emit
distortion partials in bulk, and `bwx37` is 31 seconds of audio, 95,000
partials and 1.6× realtime. A corpus with guitars in it is a much longer run.
