"""Is a change to the file renderer bit-identical on the corpus?

    python3 examples/bitident.py HASHFILE [SECONDS] [file.mid ...]

Renders the first SECONDS (default 20) of every file in corpus.txt -- or just
the files named -- through blockrender.render, and writes one line per file:
the SHA-1 of the left and right channels as float32. Run it once in a
worktree at the old commit and once in the working tree, then diff the two
files. A change that should move nothing must produce identical files; one
that should move a few must name exactly those.

WHY AN EXCERPT. A full corpus render runs at about realtime and takes hours;
twenty seconds of every file exercises every voice, every drum channel and
every program change the file makes early, which is where nearly all of them
make them. A change that only bites late in a piece will not be seen here --
say so when it matters, and render that file whole.

The excerpt is cut at a TICK, with every note still sounding closed at the
cut, so both trees render the same MIDI rather than each truncating its own
way.
"""
import hashlib
import os
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())          # the tree being tested, not this one
import blockrender as B                  # noqa: E402


def excerpt(path, seconds):
    """The first `seconds` of a MIDI file, notes closed at the cut."""
    mid = mido.MidiFile(path, clip=True)
    out = mido.MidiFile(type=mid.type, ticks_per_beat=mid.ticks_per_beat)
    # The cut in ticks: walk the merged stream for the tempo map.
    t = 0.0
    limit = None
    tick = 0
    tempo = 500000
    for msg in mido.merge_tracks(mid.tracks):
        dt = mido.tick2second(msg.time, mid.ticks_per_beat, tempo)
        if t + dt > seconds:
            limit = tick + msg.time
            break
        t += dt
        tick += msg.time
        if msg.type == 'set_tempo':
            tempo = msg.tempo
    for tr in mid.tracks:
        nt = mido.MidiTrack()
        now = 0
        last = 0
        held = set()
        for msg in tr:
            now += msg.time
            if limit is not None and now > limit:
                break
            nt.append(msg.copy(time=now - last))
            last = now
            if msg.type == 'note_on' and msg.velocity > 0:
                held.add((msg.channel, msg.note))
            elif msg.type in ('note_on', 'note_off'):
                held.discard((msg.channel, msg.note))
        end = limit if limit is not None else now
        for k, (ch, n) in enumerate(sorted(held)):
            nt.append(mido.Message('note_off', channel=ch, note=n, velocity=0,
                                   time=(end - last) if k == 0 else 0))
            last = end
        out.tracks.append(nt)
    return out


def main():
    out = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    files = sys.argv[3:] or [l.split()[0] for l in open(os.path.join(HERE, 'corpus.txt'))
                             if l.strip() and not l.startswith('#')]
    with open(out, 'w') as f:
        for p in files:
            L, R = B.render(excerpt(p, seconds))[:2]
            h = hashlib.sha1(np.asarray(L, np.float32).tobytes()
                             + np.asarray(R, np.float32).tobytes()).hexdigest()
            f.write('%s %s\n' % (h, os.path.basename(p)))
            f.flush()


if __name__ == '__main__':
    main()
