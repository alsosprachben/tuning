#!/usr/bin/env python3
"""Prepare an MT-32-era MIDI file by giving every part its own patch.

`blockrender.parse()` snapshots the program AND the controllers at note-on:

    on.setdefault((msg.channel, msg.note), []).append(
        (t, msg.velocity, cv(msg.channel), ch_prog.get(msg.channel, 0)))

so a note is detached from its channel the moment it starts. Put a
`program_change` and a `CC7` a tick or two before every note and one channel
can carry any number of instruments, each with its own sound and its own
dynamics. The 16-channel limit stops being a limit.

What is left is one constraint, and it is not the program: note_on and note_off
are paired by `(channel, note)`, so two parts may share a channel only if they
never sound the SAME PITCH at the same time. Choosing an assignment is
therefore a graph colouring, not a series of painful merges.

That difference is the whole point of this tool. Preparing Holst's Saturn by
hand meant deciding which two of its 27 parts to sacrifice -- the English Horn
was folded into the oboes and the tuba nearly went into the trombones, which
would have truncated 28 of its 60 notes. Coloured instead, all 27 parts fit
with **no** truncation at all, which is better than the source file managed:
Harp 1 and Harp 2 shared a channel there and collided on 340 unisons, and the
horns on another 149.

Two things are not free:

  registerable voices  an organ reads CC11 as a live per-channel stop bitfield
                       at render time, which is channel state and cannot be
                       stamped per note. Those parts get a channel to
                       themselves.

  the drum channel     channel 9 is percussion by note number in GM. Tracks
                       that belong there stay; pitched parts stranded there --
                       Jupiter's timpani, Saturn's bells -- are moved off, and
                       are the reason to run mt32check.py first.

Usage:
    python3 mt32mux.py IN.mid OUT.mid [--dry-run] [--name NAME=PROGRAM ...]
"""

import sys
from collections import defaultdict

import mido

try:
    from patch_map import property_class_for_program
except ImportError:                                    # standalone use
    property_class_for_program = None

# Orchestral part names as sequencers actually write them, to GM programs.
# Matched on a lowercased substring, longest first, so "bass clarinet" wins
# over "clarinet" and "bass trombone" over "trombone".
NAME_TO_GM = {
    'piccolo': 72, 'bass flute': 73, 'alto flute': 73, 'flute': 73,
    'english horn': 69, 'cor anglais': 69, 'bass oboe': 69, 'heckelphone': 69,
    'oboe': 68,
    'bass clarinet': 71, 'clarinet': 71, 'basset': 71,
    # These must out-length 'doublebass'/'contrabass' below, or a
    # DoubleBassoon is read as a double bass -- which is what happened to
    # Jupiter's until the longest-match order was tested against it.
    'doublebassoon': 70, 'double bassoon': 70, 'contra bassoon': 70,
    'contrabassoon': 70, 'contrbassoon': 70, 'bassoon': 70,
    'soprano sax': 64, 'alto sax': 65, 'tenor sax': 66, 'bari sax': 67,
    'horn': 60, 'cornet': 56, 'trumpet': 56,
    'bass trombone': 57, 'trombone': 57, 'euphonium': 58, 'tuba': 58,
    'timpani': 47, 'timp': 47,
    'tubular bell': 14, 'chime': 14, 'bell': 14,
    'glockenspiel': 9, 'celesta': 8, 'celeste': 8,
    'xylophone': 13, 'marimba': 12, 'vibraphone': 11,
    'harp': 46, 'organ': 19, 'piano': 0,
    'violin': 40, 'viola': 41, 'violoncello': 42, 'cello': 42,
    'double bass': 43, 'doublebass': 43, 'contrabass': 43, 'bass': 43,
    'chorus': 52, 'choir': 52, 'soprano': 52, 'alto': 52, 'voice': 53,
}

# Names that mean the GM drum map, which stays on channel 9.
PERCUSSIVE = ('percussion', 'drum', 'kit', 'cymbal', 'snare', 'tom',
              'hi-hat', 'hihat', 'rhythm', 'battery', 'triangle',
              'tambourine', 'castanet', 'gong', 'tam-tam')

GM_PERCUSSION_CHANNEL = 9
STAMP_LEAD = 2          # ticks between the program_change and its note


def program_for(name, own_programs):
    """The GM program for a part: what it is CALLED, else what it declared.

    A name is better evidence than a program byte in these files -- the
    programs are MT-32 patch numbers that mean something else entirely (Saturn
    puts its harps on Contrabass and its horns on SlapBass1), while the names
    are what the person at the sequencer typed.
    """
    low = (name or '').lower()
    for key in sorted(NAME_TO_GM, key=len, reverse=True):
        if key in low:
            return NAME_TO_GM[key], 'name'
    if own_programs:
        return own_programs[-1], 'declared'
    return 0, 'default'


def is_registerable(program):
    if property_class_for_program is None:
        return program in (16, 17, 18, 19, 20)         # the organs
    try:
        return bool(getattr(property_class_for_program(program),
                            'registerable', False))
    except Exception:
        return False


def read_parts(mid):
    """One entry per track that plays: name, own programs, controllers, notes."""
    parts = []
    for ti, track in enumerate(mid.tracks):
        name = ''
        progs = []
        cc = defaultdict(list)
        held = {}
        notes = []
        drum = False
        chans = set()
        now = 0
        for msg in track:
            now += msg.time
            if msg.type == 'track_name':
                name = msg.name.strip()
            elif msg.type == 'program_change':
                progs.append(msg.program)
            elif msg.type == 'control_change':
                cc[msg.control].append((now, msg.value))
            elif msg.type == 'note_on' and msg.velocity:
                held.setdefault(msg.note, []).append((now, msg.velocity))
                chans.add(msg.channel)
                drum = drum or msg.channel == GM_PERCUSSION_CHANNEL
            elif msg.type in ('note_off', 'note_on') and held.get(msg.note):
                on, vel = held[msg.note].pop(0)
                notes.append((on, now, msg.note, vel))
        if notes:
            parts.append({'track': ti, 'name': name or 'trk%d' % ti,
                          'progs': progs, 'cc': cc, 'notes': sorted(notes),
                          'was_drum': drum,
                          'from_ch': min(chans) if chans else 0})
    return parts


def channel_cc(mid):
    """The file's combined per-channel controller timelines -- what was really
    in force, which is not the same as what any one track wrote."""
    out = {}
    for track in mid.tracks:
        now = 0
        for msg in track:
            now += msg.time
            if msg.type == 'control_change':
                out.setdefault(msg.channel, {}).setdefault(msg.control, []).append(
                    (now, msg.value))
    for ch in out:
        for c in out[ch]:
            out[ch][c].sort()
    return out


def seed_parts(parts, combined):
    """Give each part the volume that was actually in force when it entered.

    Separating parts that shared a channel exposes anything a track wrote and
    another track then masked. Jupiter's Percussion track opens with CC7=5 and
    does not touch it again until 63 s -- inaudible in the original, because
    Timpani I shared the channel and set 124 at 21 s. Split them and the
    percussion plays its first 40 seconds at -56 dB.

    So each part starts from the combined channel state at its first note, and
    only then follows its own automation.
    """
    for p in parts:
        first = p['notes'][0][0]
        for ctrl, default in ((7, 100), (10, 64)):
            own = [e for e in sorted(p['cc'][ctrl]) if e[0] >= first]
            was = value_at(sorted(combined.get(p['from_ch'], {}).get(ctrl, [])),
                           first, default)
            p['cc'][ctrl] = [(0, was)] + own
    return parts


def collisions(a, b):
    """How often two parts hold the same pitch at the same time."""
    n = 0
    for x, y, p, _ in a:
        for u, v, q, _ in b:
            if p == q and x < v and y > u:
                n += 1
    return n


def colour(parts, channels):
    """Assign channels so that no two parts on one ever share a pitch.

    Greedy by conflict degree, which is enough here: orchestral parts conflict
    with their own doublings and almost nothing else, so the graph is sparse
    and the busiest part is the one that most needs first pick.
    """
    n = len(parts)
    C = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            C[i][j] = C[j][i] = collisions(parts[i]['notes'], parts[j]['notes'])

    assign = {}
    free = list(channels)
    # A registerable voice reads its stops from the channel, so it cannot share.
    for i, p in enumerate(parts):
        if is_registerable(p['program']) and free:
            assign[i] = free.pop(0)
    # Percussion keeps the drum channel.
    for i, p in enumerate(parts):
        if i not in assign and p['was_drum'] and p['percussive']:
            assign[i] = GM_PERCUSSION_CHANNEL

    order = sorted((i for i in range(n) if i not in assign),
                   key=lambda i: -sum(1 for j in range(n) if C[i][j]))
    for i in order:
        for ch in free:
            if all(assign.get(j) != ch or C[i][j] == 0 for j in range(n)):
                assign[i] = ch
                break
        else:
            assign[i] = min(free, key=lambda ch: sum(
                C[i][j] for j in range(n) if assign.get(j) == ch))
    left = sum(C[i][j] for i in range(n) for j in range(i + 1, n)
               if assign[i] == assign[j])
    before = sum(C[i][j] for i in range(n) for j in range(i + 1, n))
    return assign, before, left, C


def value_at(timeline, tick, default):
    v = default
    for at, val in timeline:
        if at > tick:
            break
        v = val
    return v


def build(mid, parts, assign):
    out = mido.MidiFile(type=1, ticks_per_beat=mid.ticks_per_beat)

    meta = mido.MidiTrack()
    evs = []
    for track in mid.tracks:
        now = 0
        for msg in track:
            now += msg.time
            if msg.is_meta and msg.type != 'track_name':
                evs.append((now, msg))
    evs.sort(key=lambda x: x[0])
    prev = 0
    for at, msg in evs:
        meta.append(msg.copy(time=at - prev))
        prev = at
    out.tracks.append(meta)

    for i, p in enumerate(parts):
        ch = assign[i]
        track = mido.MidiTrack()
        track.append(mido.MetaMessage('track_name', name=p['name'], time=0))
        evs = []
        for on, off, note, vel in p['notes']:
            # Everything this note needs, immediately before it.
            if ch != GM_PERCUSSION_CHANNEL:
                evs.append((max(0, on - STAMP_LEAD),
                            mido.Message('program_change', channel=ch,
                                         program=p['program'], time=0)))
            evs.append((max(0, on - 1),
                        mido.Message('control_change', channel=ch, control=7,
                                     value=value_at(p['cc'][7], on, 100), time=0)))
            if p['cc'][10]:
                evs.append((max(0, on - 1),
                            mido.Message('control_change', channel=ch, control=10,
                                         value=value_at(p['cc'][10], on, 64), time=0)))
            evs.append((on, mido.Message('note_on', channel=ch, note=note,
                                         velocity=vel, time=0)))
            evs.append((off, mido.Message('note_off', channel=ch, note=note,
                                          velocity=0, time=0)))
        evs.sort(key=lambda x: x[0])
        prev = 0
        for at, msg in evs:
            track.append(msg.copy(time=int(at - prev)))
            prev = at
        out.tracks.append(track)
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[-1])
        return 2
    inp, outp = argv[1], argv[2]
    dry = '--dry-run' in argv
    overrides = {}
    for i, a in enumerate(argv):
        if a == '--name' and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition('=')
            overrides[k.strip().lower()] = int(v)

    mid = mido.MidiFile(inp)
    parts = seed_parts(read_parts(mid), channel_cc(mid))
    for p in parts:
        low = p['name'].lower()
        p['percussive'] = any(w in low for w in PERCUSSIVE)
        if low in overrides:
            p['program'], p['why'] = overrides[low], 'override'
        elif p['percussive'] and p['was_drum']:
            p['program'], p['why'] = -1, 'drum map'
        else:
            p['program'], p['why'] = program_for(p['name'], p['progs'])

    channels = [c for c in range(16) if c != GM_PERCUSSION_CHANNEL]
    assign, before, left, _ = colour(parts, channels)

    print("== %s -> %s" % (inp, outp))
    print("   %d parts over %d channels" % (len(parts), len(set(assign.values()))))
    print("   same-pitch overlaps: %d if every part shared, %d as assigned"
          % (before, left))
    for i, p in enumerate(parts):
        lo = min(n for _, _, n, _ in p['notes'])
        hi = max(n for _, _, n, _ in p['notes'])
        print("   ch%-3d %-22s %-11s %5d notes  %3d-%-3d"
              % (assign[i], p['name'][:22],
                 'drum map' if p['program'] < 0 else
                 '%d (%s)' % (p['program'], p['why']),
                 len(p['notes']), lo, hi))
    if left:
        print("   NOTE: %d overlaps remain -- those notes will truncate each"
              " other. Split the part or accept it." % left)
    if not dry:
        build(mid, parts, assign).save(outp)
        print("   written")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
