#!/usr/bin/env python3
"""Align a score to a performance of it, by pitch sequence.

A performance and its score play the same notes in the same order, but not at
the same times and not in the same NUMBER: a player ornaments, and every added
note shifts everything after it. So the two cannot be matched by index, and they
cannot be matched by time either.

Banded Needleman-Wunsch over the pitch sequences. The first version of this was
a greedy two-pointer, which managed 97% of Bach's first movement and 59% of his
second -- a greedy walk that guesses wrong at an ornament never recovers, and
the Andante is the ornate one. A DP keeps every alternative alive and takes the
best path; the band keeps it cheap, because two performances of one piece never
stray far from the diagonal. Half a second for 2700 notes, and 96-100% matched.

BOTH FILES MUST COVER THE SAME MUSIC. The band follows the diagonal, so a
single movement's score against a whole three-movement performance aligns at
53% and not 99% -- not a failure of the method, a failure to segment first.
registrate.py splits by the silences between movements before calling this.

Usage: scorealign.py SCORE.mid PERF.mid     (reports the match rate)
"""
import sys

MATCH, MISMATCH, GAP = 2.0, -2.0, -1.0


def align(a_pitch, b_pitch, band=250):
    """[(i, j)] pairing indices of a_pitch to b_pitch, in order."""
    n, m = len(a_pitch), len(b_pitch)
    NEG = float('-inf')
    ptr = [dict() for _ in range(n + 1)]

    def jrange(i):
        c = int(i * m / max(n, 1))
        return max(0, c - band), min(m, c + band)

    lo0, hi0 = jrange(0)
    prev = {j: GAP * j for j in range(lo0, hi0 + 1)}
    for j in range(lo0, hi0 + 1):
        ptr[0][j] = 'L'
    for i in range(1, n + 1):
        lo, hi = jrange(i)
        cur = {}
        for j in range(lo, hi + 1):
            best, how = NEG, None
            if j - 1 in prev:
                s = prev[j - 1] + (MATCH if a_pitch[i-1] == b_pitch[j-1] else MISMATCH)
                if s > best: best, how = s, 'D'
            if j in prev:
                s = prev[j] + GAP
                if s > best: best, how = s, 'U'
            if j - 1 in cur:
                s = cur[j - 1] + GAP
                if s > best: best, how = s, 'L'
            if how is None:
                continue
            cur[j] = best; ptr[i][j] = how
        prev = cur
    i = n
    j = max(prev, key=lambda k: prev[k]) if prev else 0
    pairs = []
    while i > 0 and j > 0:
        how = ptr[i].get(j)
        if how == 'D':
            if a_pitch[i-1] == b_pitch[j-1]:
                pairs.append((i-1, j-1))
            i -= 1; j -= 1
        elif how == 'U': i -= 1
        elif how == 'L': j -= 1
        else: break
    return pairs[::-1]


def note_stream(path, by_track=False):
    """[(seconds, pitch, track, velocity)] for one MIDI, in time order."""
    import mido
    m = mido.MidiFile(path)
    tpb = m.ticks_per_beat
    tempo = 500000
    for tr in m.tracks:
        for x in tr:
            if x.type == 'set_tempo':
                tempo = x.tempo
                break
    spt = tempo / 1e6 / tpb
    out = []
    voiced = [t for t in m.tracks if any(x.type == 'note_on' for x in t)]
    for si, tr in enumerate(voiced):
        t = 0
        for x in tr:
            t += x.time
            if x.type == 'note_on' and x.velocity > 0:
                out.append((t * spt, x.note, si, x.velocity))
    return sorted(out)


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[-1])
        return 2
    A = note_stream(argv[1]); B = note_stream(argv[2])
    P = align([x[1] for x in A], [x[1] for x in B])
    print("  score %d notes, performance %d -> %d matched (%.0f%% of the score)"
          % (len(A), len(B), len(P), 100.0 * len(P) / max(len(A), 1)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
