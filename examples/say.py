#!/usr/bin/env python3
"""Build a single-voice MIDI that sings a given text.

    python3 examples/say.py hamlet out.mid
    python3 examples/say.py daisy  out.mid
    python3 examples/say.py --list

A note's lyric is written as ONSET/VOWEL/CODA -- 't/u' is /tu/, '/O/r' is /Or/
with no onset, 'n/a/t' is /nat/. Vowel symbols are the keys of vowels.VOWELS
(a E e i O o u y P @ A V); consonants are the keys of vowels.CONSONANTS. The
phonemes are given directly rather than spelled, because these demos exist to
test the tract and an English grapheme-to-phoneme layer would put its own
mistakes between the model and the ear.

These two are kept because they are the shortest useful tests of the voice.
Hamlet is six syllables of ordinary English whose vowels a listener can name
without being told what to expect -- which is the whole difficulty with Latin
vowels. Daisy Bell is the 1961 IBM 704 demonstration: Kelly and Lochbaum's
tube model driven by Mathews' accompaniment, and the thing 2001 quotes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: F401  (puts the repo root on the path)

# (lyric, midi note, beats)
SONGS = {
    'hamlet': dict(
        part='Alto', bpm=50, velocity=88, time_signature=None,
        text="To be or not to be",
        notes=[('t/u', 67, 1.0), ('b/i', 65, 1.0), ('/O/r', 63, 1.0),
               ('n/a/t', 62, 1.0), ('t/u', 63, 0.5), ('b/i', 60, 3.0)]),
    'daisy': dict(
        part='Tenor', bpm=96, velocity=84, time_signature=(3, 4),
        text="Daisy, Daisy, give me your answer do. "
             "I'm half crazy all for the love of you.",
        notes=[('d/e', 74, 3.0), ('z/i', 71, 3.0), ('d/e', 67, 3.0),
               ('z/i', 62, 3.0), ('g/i/v', 64, 1.0), ('m/i', 66, 1.0),
               ('/O/r', 67, 1.0), ('/a/n', 64, 2.0), ('s/@/r', 67, 1.0),
               ('d/u', 62, 4.0), ('/a/m', 69, 3.0), ('h/a/f', 74, 3.0),
               ('k/e', 71, 3.0), ('z/i', 67, 3.0), ('/O/l', 64, 1.0),
               ('f/O/r', 66, 1.0), ('d/@', 67, 1.0), ('l/V/v', 69, 2.0),
               ('/V/v', 71, 1.0), ('/u', 69, 5.0)]),
}


def build(song, dest, ticks_per_beat=480, program=52):
    """Write the MIDI. `program` 52 is Choir Aahs, which is what voice_body()
    looks for -- a part with a different patch is not treated as a voice."""
    import mido
    m = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    t = mido.MidiTrack()
    m.tracks.append(t)
    # The track NAME is the part, and that is what picks the body: a Tenor and
    # an Alto get different tract lengths for the same written pitch.
    t.append(mido.MetaMessage('track_name', name=song['part'], time=0))
    t.append(mido.MetaMessage('set_tempo',
                              tempo=int(round(6e7 / song['bpm'])), time=0))
    if song['time_signature']:
        n, d = song['time_signature']
        t.append(mido.MetaMessage('time_signature', numerator=n, denominator=d,
                                  time=0))
    t.append(mido.Message('program_change', channel=0, program=program, time=0))
    delay = ticks_per_beat            # a beat of silence before the first note
    for lyric, note, beats in song['notes']:
        t.append(mido.MetaMessage('lyrics', text=lyric, time=delay))
        t.append(mido.Message('note_on', channel=0, note=note,
                              velocity=song['velocity'], time=0))
        t.append(mido.Message('note_off', channel=0, note=note, velocity=0,
                              time=int(round(beats * ticks_per_beat))))
        delay = 0
    m.save(dest)
    return dest


def main(argv):
    if '--list' in argv:
        for k, v in SONGS.items():
            print("  %-8s %-6s %3d bpm  %2d notes  %s"
                  % (k, v['part'], v['bpm'], len(v['notes']), v['text']))
        return 0
    if len(argv) < 3 or argv[1] not in SONGS:
        print(__doc__.strip()); return 2
    print("  %s -> %s" % (SONGS[argv[1]]['text'], build(SONGS[argv[1]], argv[2])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
