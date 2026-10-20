"""Is a change to the file renderer bit-identical on the corpus?

    python3 examples/bitident.py HASHFILE [SECONDS] [file.mid ...] [options]
    (--grep=REGEX --gs --program=N --kit=N --list --against=FILE; see USAGE)

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


def _sends_gs(mid):
    """Any Roland GS SysEx (41 dd 42 ...): the Sound Canvas files."""
    for tr in mid.tracks:
        for m in tr:
            if m.type == 'sysex' and len(m.data) > 3 and m.data[0] == 0x41 and m.data[2] == 0x42:
                return True
    return False


def _programs(mid):
    """({melodic programs}, {drum-channel programs}) the file selects --
    channel 10 as drums, as most of the corpus is (a GS rhythm part moved
    elsewhere counts as melodic here: a selector, not the renderer)."""
    mel, kit = set(), set()
    for tr in mid.tracks:
        for m in tr:
            if m.type == 'program_change':
                (kit if m.channel == 9 else mel).add(m.program)
    return mel, kit


def select(files, grep=None, gs=False, program=None, kit=None):
    """The files that match every selector given."""
    import re as _re
    out = []
    for p in files:
        if grep and not _re.search(grep, p):
            continue
        if gs or program is not None or kit is not None:
            try:
                mid = mido.MidiFile(p, clip=True)
            except Exception:
                continue
            if gs and not _sends_gs(mid):
                continue
            mel, kits = _programs(mid)
            if program is not None and program not in mel:
                continue
            if kit is not None and kit not in kits:
                continue
        out.append(p)
    return out


def against(out, golden):
    """Compare a hash file with a reference: (moved, same, new) basenames."""
    def rd(p):
        d = {}
        for l in open(p):
            f = l.split()
            if len(f) >= 2:
                d[f[1]] = f[0]
        return d
    a, b = rd(out), rd(golden)
    moved = sorted(k for k in a if k in b and a[k] != b[k])
    same = sorted(k for k in a if k in b and a[k] == b[k])
    new = sorted(k for k in a if k not in b)
    return moved, same, new


USAGE = """    python3 examples/bitident.py HASHFILE [SECONDS] [file.mid ...] [options]

  --from=PATH      select from a directory's .mid files (recursively) or a
                   list file, instead of corpus.txt -- the GS test files,
                   which are local material and not in the corpus
  --grep=REGEX     only files whose path matches
  --gs             only files that send Roland GS SysEx (the Sound Canvas files)
  --program=N      only files that select melodic program N (0-based)
  --kit=N          only files that select drum set N on channel 10 (0-based)
  --list           print the selection and stop
  --against=FILE   compare with a reference hash file: what moved, what did not
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opt = dict(a[2:].split('=', 1) if '=' in a else (a[2:], '') for a in sys.argv[1:] if a.startswith('--'))
    if not args and 'list' not in opt:
        print(USAGE)
        return 2
    out = args[0] if args else None
    seconds = float(args[1]) if len(args) > 1 else 20.0
    pool = opt.get('from')
    if args[2:]:
        files = args[2:]
    elif pool and os.path.isdir(pool):
        files = sorted(os.path.join(d, n) for d, _, ns in os.walk(pool) for n in ns
                       if n.lower().endswith(('.mid', '.midi')))
    else:
        files = [l.split()[0] for l in open(pool or os.path.join(HERE, 'corpus.txt'))
                 if l.strip() and not l.startswith('#')]
    files = select(files, grep=opt.get('grep') or None, gs='gs' in opt,
                   program=int(opt['program']) if 'program' in opt else None,
                   kit=int(opt['kit']) if 'kit' in opt else None)
    if 'list' in opt:
        for p in files:
            print(p)
        print("%d file(s)" % len(files))
        return 0
    with open(out, 'w') as f:
        for p in files:
            L, R = B.render(excerpt(p, seconds))[:2]
            h = hashlib.sha1(np.asarray(L, np.float32).tobytes()
                             + np.asarray(R, np.float32).tobytes()).hexdigest()
            f.write('%s %s\n' % (h, os.path.basename(p)))
            f.flush()
    if opt.get('against'):
        moved, same, new = against(out, opt['against'])
        print("against %s: %d moved, %d bit-identical, %d not in it" % (
            os.path.basename(opt['against']), len(moved), len(same), len(new)))
        for k in moved:
            print("  moved  %s" % k)
    return 0


if __name__ == '__main__':
    sys.exit(main())
