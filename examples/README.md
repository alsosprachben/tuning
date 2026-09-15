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
| `lacrimosa_choir.py` | Mozart, Requiem K.626, Lacrimosa -- choir alone with the Latin text, from a MusicXML score. `--both` renders the formant and tube tracts for comparison. |

```
python3 examples/say.py daisy /tmp/daisy.mid
python3 singpass.py /tmp/daisy.mid /tmp/daisy.wav --lang english --tube

python3 examples/lacrimosa_choir.py ~/Downloads/MozartLacrimosaSATB.mxl /tmp --both
```

## Scores are not included

`lacrimosa_choir.py` takes a score you supply. The music is Mozart and long out
of copyright, but a particular engraving is somebody's work and is not
redistributed from here.

**The Sankey corpus is a stricter case.** John Sankey's terms permit
redistributing his MIDI with his notice, but state that audio "must be derived
from the MIDI files using my matching soundfont on a SoundBlaster 32". Renders
of that corpus made with this renderer are therefore **personal use only and
must not be distributed.** `NOTICE.txt` sits beside the corpus.

## Not yet ported

The Dies irae and the Neptune chorus (with its receding all-female registration)
were built the same throwaway way and are not here yet.
