# examples

The scripts that build the renders, kept.

Every one of these started as a shell pipeline in `/tmp`, and the throwaway
versions are why the same mistakes kept coming back. Three in particular:

- **Dropping the conductor track.** In an engraving export, track 0 usually has
  no notes -- only the tempo map -- so it looks like an empty track worth
  cutting. Cut it and everything else plays at the 120 bpm default. That is
  what "the accompaniment is exactly twice as fast as the voices" was.
- **Selecting parts by name.** This Requiem engraving has four empty staves
  named Treble/Alto/Tenor/Bass sitting next to the four that hold the notes.
  A choir part is one with notes *and* lyrics.
- **Comparing renders made under different settings.** An A/B is only worth
  anything if one thing changed. `lib.sing()` takes the tract as a flag so
  both sides come off the same source render.

`lib.py` handles those once. `lib.bands()` is there because comparing two
renders by ear alone has hidden a 20 dB spectral difference more than once,
and comparing them by a single broadband number has hidden the opposite.

## Scripts

| script | what it builds |
|---|---|
| `say.py` | a single-voice MIDI singing given phonemes: `hamlet` ("To be or not to be") and `daisy` (the 1961 IBM 704 demonstration). Reproduces both originals event-for-event. |
| `choral.py` | The general driver: any lyric-bearing score. Splits choir from everything else, renders each the way it has to be rendered, sums dry and puts the hall over the pair. `--choir-only`, `--both` (formant vs tube), `--choir-db N`. |
| `lacrimosa_choir.py` | Mozart, Requiem K.626, Lacrimosa -- a named entry point into `choral.py`. |
| `dies_irae.py` | Mozart, Requiem K.626, Dies Irae. Same, and the reason `--choir-db` exists. |

```
python3 examples/say.py daisy /tmp/daisy.mid
python3 singpass.py /tmp/daisy.mid /tmp/daisy.wav --lang english --tube

python3 examples/lacrimosa_choir.py ~/Downloads/MozartLacrimosaSATB.mxl /tmp --both
python3 examples/lacrimosa_choir.py ~/Downloads/MozartLacrimosaSATB.mxl /tmp --orchestra
```

## Voices and everything else do not render the same way

`singpass.py` filters the WHOLE file -- it is a source-filter pass over a
vocal stem, so an orchestra sent through it is played inside a singer's
mouth. Anything unsung goes through `blockrender` directly (`lib.render_plain`).

Which means a full piece is two renders that have to be put back together,
and the trap there is the room. `blockrender` computes first-order images
only and writes a `.room.json` sidecar saying what the piece fed the hall per
band; the diffuse tail is `roomtail`'s convolution over the sum. Stems are
therefore summed DRY and given the hall once, with their sidecars merged
(`lib.merge_room`) -- a choir and a string section do not feed a room alike,
and a mix that inherits whichever sidecar it found first gets the wrong one.

## Scores are not included

`lacrimosa_choir.py` takes a score you supply. The music is Mozart and long out
of copyright, but a particular engraving is somebody's work and is not
redistributed from here.

**The Sankey corpus is a stricter case.** John Sankey's terms permit
redistributing his MIDI with his notice, but state that audio "must be derived
from the MIDI files using my matching soundfont on a SoundBlaster 32". Renders
of that corpus made with this renderer are therefore **personal use only and
must not be distributed.** `NOTICE.txt` sits beside the corpus.

## Check for dynamics before trusting a balance

`choral.py` sums the stems at unit gain, which preserves whatever the score
notated -- but engraving exports often notate nothing. LilyPond's Dies Irae
gives every choir note velocity 95 and every first violin 101, one flat value
per staff. Summed as-is that puts the choir 6 dB UNDER the orchestra where the
two play together, and presents an exporter's default as Mozart's balance.

So the script prints each track's velocity spread, and reports the balance
measured only WHERE THE CHOIR SINGS -- that movement is 38% choral, so a ratio
over the whole thing answers a question nobody asked. `--choir-db` then states
the correction out loud rather than burying it in a gain.

## Not yet ported

Neptune's receding all-female chorus. It has no text -- Holst writes it
wordless -- so it needs the registration and the recession, not this pipeline.
