#!/usr/bin/env python3
"""Audit an MT-32-era MIDI file before rendering it as GM.

Sequences written for the Roland MT-32 (and its LA-synthesis relatives) look
like General MIDI but are not, and the ways they differ all present as *voice*
problems -- an instrument too loud, too quiet, or the wrong timbre -- which
invites a fix in the renderer's gain tables that is really chasing a
file-preparation bug.  This reports the file-level causes so they can be ruled
out first.

What it checks, and why each one has bitten us:

  shadowed programs   Several program_change messages for one channel at tick 0,
                      in different tracks.  Only the last survives; the others
                      are what the file *says* it wants.  Holst's Neptune stacks
                      Oboe, Harp and VoiceOoh on channel 5.

  reused channels     One channel carrying two different instruments at
                      different times.  MT-32 sequences do this constantly to
                      stay inside the part limit.  Profiled by note density and
                      duration per window: a stretch of 0.06 s notes spanning
                      four octaves is figuration, a stretch of 2 s notes inside
                      three semitones is a held voice, and no single GM program
                      is right for both.

  drum-channel pitch  Channel 9 is percussion in GM, but an MT-32 file may put a
                      real pitched part there.  Jupiter's timpani were written
                      as G2-G3 on channel 9 and came out as toms and hi-hats.
                      Track names are the tell, so they are printed.

  controller sharing  Two tracks writing controllers to the same channel fight,
                      last write wins, and the dynamics end up wrong for one of
                      them.

  extreme CC7         GM reads volume as 40*log10(v/127), so small values are
                      drastic: CC7=5 is -56 dB, effectively silence.  Worth
                      seeing before concluding a voice is broken.

  range vs program    Notes outside what the assigned instrument can play --
                      a chorus part running to E8, say -- means the program is
                      wrong, not the voice.

Usage:  python3 mt32check.py FILE.mid [FILE.mid ...]
"""

import sys
import statistics
from collections import defaultdict

import mido

GM_NAMES = [
    "AcGrPiano", "BrAcPiano", "ElGrPiano", "HonkyTonk", "ElPiano1", "ElPiano2",
    "Harpsi", "Clav", "Celesta", "Glocken", "MusicBox", "Vibra", "Marimba",
    "Xylo", "TubeBell", "Dulcimer", "DrawOrgan", "PercOrgan", "RockOrgan",
    "ChurchOrg", "ReedOrgan", "Acordion", "Harmonica", "TangoAcd", "NylonGtr",
    "SteelGtr", "JazzGtr", "CleanGtr", "MutedGtr", "OverdrvGtr", "DistGtr",
    "GtrHarm", "AcBass", "FngrBass", "PickBass", "FretlessB", "SlapBass1",
    "SlapBass2", "SynBass1", "SynBass2", "Violin", "Viola", "Cello",
    "Contrabas", "TremStr", "PizzStr", "Harp", "Timpani", "StrEns1", "StrEns2",
    "SynStr1", "SynStr2", "ChoirAah", "VoiceOoh", "SynVoice", "OrchHit",
    "Trumpet", "Trombone", "Tuba", "MutedTrp", "FrHorn", "BrasSect",
    "SynBrass1", "SynBrass2", "SopSax", "AltoSax", "TenorSax", "BariSax",
    "Oboe", "EngHorn", "Bassoon", "Clarinet", "Piccolo", "Flute", "Recorder",
    "PanFlute", "Blownbtl", "Shakuhach", "Whistle", "Ocarina", "Lead1Square",
    "Lead2Sawth", "Lead3Calio", "Lead4Chiff", "Lead5Charg", "Lead6Voice",
    "Lead7Fifth", "Lead8Bass", "Pad1NewAge", "Pad2Warm", "Pad3Poly",
    "Pad4Choir", "Pad5Bowed", "Pad6Metal", "Pad7Halo", "Pad8Sweep",
    "FX1Rain", "FX2Sndtrk", "FX3Crystal", "FX4Atmosp", "FX5Bright",
    "FX6Goblins", "FX7Echoes", "FX8SciFi", "Sitar", "Banjo", "Shamisen",
    "Koto", "Kalimba", "Bagpipe", "Fiddle", "Shanai", "TinkleBell",
    "Agogo", "SteelDrums", "Woodblock", "TaikoDrum", "MelodicTom",
    "SynthDrum", "RevCymbal", "GtrFretNz", "BreathNoise", "Seashore",
    "BirdTweet", "TelephRing", "Helicopter", "Applause", "Gunshot",
]

# Playable compass per program, as MIDI note numbers.  Deliberately generous --
# this is here to catch a part that is on the wrong program, not to police
# a composer writing at the extremes.
RANGES = {
    40: (55, 103), 41: (48, 93), 42: (36, 81), 43: (28, 67),   # strings
    46: (24, 104),                                             # harp
    47: (40, 55),                                              # timpani
    51: (48, 84), 52: (48, 84),                                # choir/voice
    53: (48, 84),
    56: (54, 87), 57: (40, 77), 58: (28, 65), 59: (54, 87),    # brass
    60: (34, 77),
    68: (58, 92), 69: (52, 84), 70: (34, 75), 71: (50, 91),    # winds
    72: (74, 108), 73: (60, 96),
}

GATE = 12  # notes below this per window are too few to characterise


def _seconds_fn(mid):
    """Return tick -> seconds, honouring every tempo change in the file."""
    tempos = []
    for track in mid.tracks:
        now = 0
        for msg in track:
            now += msg.time
            if msg.type == 'set_tempo':
                tempos.append((now, msg.tempo))
    tempos.sort()
    if not tempos or tempos[0][0] > 0:
        tempos.insert(0, (0, 500000))

    def sec(tick):
        total, prev, cur = 0.0, 0, tempos[0][1]
        for at, tempo in tempos:
            if at >= tick:
                break
            total += mido.tick2second(at - prev, mid.ticks_per_beat, cur)
            prev, cur = at, tempo
        return total + mido.tick2second(tick - prev, mid.ticks_per_beat, cur)

    return sec


def _gather(mid, sec):
    """Collect per-channel notes, programs, controllers and track names."""
    notes = defaultdict(list)          # channel -> [(onset, duration, note)]
    programs = defaultdict(list)       # channel -> [(seconds, program, track)]
    volumes = defaultdict(list)        # channel -> [(seconds, value)]
    names = defaultdict(set)           # channel -> {track name}
    ctrl_tracks = defaultdict(set)     # channel -> {track index writing CC}
    track_names = []

    for ti, track in enumerate(mid.tracks):
        now = 0
        label = ''
        held = {}
        for msg in track:
            now += msg.time
            if msg.type == 'track_name':
                label = msg.name.strip()
                track_names.append(label)
            elif msg.type == 'program_change':
                programs[msg.channel].append((sec(now), msg.program, label))
            elif msg.type == 'control_change':
                ctrl_tracks[msg.channel].add(ti)
                if msg.control == 7:
                    volumes[msg.channel].append((sec(now), msg.value))
            elif msg.type == 'note_on' and msg.velocity:
                held.setdefault((msg.channel, msg.note), []).append(now)
                if label:
                    names[msg.channel].add(label)
            elif msg.type in ('note_off', 'note_on'):
                stack = held.get((msg.channel, msg.note))
                if stack:
                    on = stack.pop(0)
                    notes[msg.channel].append(
                        (sec(on), sec(now) - sec(on), msg.note))
    return notes, programs, volumes, names, ctrl_tracks, track_names


def _character(window):
    """Call a window of notes 'figuration', 'sustained', or neither."""
    median = statistics.median(d for _, d, _ in window)
    spread = max(n for _, _, n in window) - min(n for _, _, n in window)
    if median <= 0.15 and spread >= 18:
        return 'figuration'
    if median >= 1.0 and spread <= 8:
        return 'sustained'
    return None


def check(path, window=60.0):
    mid = mido.MidiFile(path)
    sec = _seconds_fn(mid)
    notes, programs, volumes, names, ctrl_tracks, track_names = _gather(mid, sec)

    print("== %s" % path)
    if any(n.lower().startswith('master parameters') for n in track_names):
        print("   MT-32 file (a 'Master Parameters' track is the tell)"
              " -- programs are not GM")

    findings = []

    for ch in sorted(set(notes) | set(programs)):
        chosen = programs[ch][-1] if programs[ch] else None
        label = ("%d %s" % (chosen[1], GM_NAMES[chosen[1]])
                 if chosen and chosen[1] < len(GM_NAMES) else "(none)")
        parts = sorted(names[ch])
        print("   ch%-3d %-18s %5d notes   %s"
              % (ch, label, len(notes[ch]),
                 ", ".join(parts[:3]) + (" ..." if len(parts) > 3 else "")))

        # -- programs that never take effect
        at_zero = [p for p in programs[ch] if p[0] <= 0.0]
        if len(at_zero) > 1:
            shadowed = ", ".join(
                "%d %s%s" % (p, GM_NAMES[p] if p < len(GM_NAMES) else '?',
                             " [%s]" % t if t else "")
                for _, p, t in at_zero[:-1])
            findings.append(
                "ch%d: %d program changes at tick 0; only the last takes "
                "effect. Shadowed: %s" % (ch, len(at_zero), shadowed))

        # -- one channel, two instruments
        if notes[ch]:
            seen = []
            span = max(o for o, _, _ in notes[ch])
            start = 0.0
            while start < span:
                win = [x for x in notes[ch] if start <= x[0] < start + window]
                if len(win) >= GATE:
                    kind = _character(win)
                    if kind:
                        seen.append((start, kind, len(win),
                                     statistics.median(d for _, d, _ in win)))
                start += window
            kinds = {k for _, k, _, _ in seen}
            if len(kinds) > 1:
                detail = "; ".join(
                    "%.0f-%.0fs %s (%d notes, median %.3fs)"
                    % (s, s + window, k, n, d) for s, k, n, d in seen)
                findings.append(
                    "ch%d carries both figuration and sustained writing -- "
                    "one program cannot be right for both: %s" % (ch, detail))

        # -- pitched material on the drum channel.  Two ways it shows up: the
        #    whole channel is one pitched part, or (worse, because the drums
        #    around it look fine) a named instrument shares the channel with a
        #    real kit.  Read the track names before the note numbers.
        if ch == 9 and notes[ch]:
            pitches = sorted({n for _, _, n in notes[ch]})
            if len(pitches) >= 5 and max(pitches) - min(pitches) <= 24:
                findings.append(
                    "ch9 (GM percussion) holds %d notes across %d pitches "
                    "spanning %d semitones -- looks like a pitched part. "
                    "Tracks: %s"
                    % (len(notes[ch]), len(pitches),
                       max(pitches) - min(pitches),
                       ", ".join(sorted(names[ch])) or "(unnamed)"))
            strangers = [n for n in sorted(names[ch])
                         if not any(w in n.lower() for w in
                                    ('perc', 'drum', 'kit', 'cymb', 'snare',
                                     'tom', 'hat', 'rhythm', 'batt'))]
            if strangers:
                findings.append(
                    "ch9 (GM percussion) carries named instrument part%s %s -- "
                    "GM will read their pitches as kit sounds. Check the score "
                    "before deleting them as stray drums."
                    % ("" if len(strangers) == 1 else "s",
                       ", ".join(repr(s) for s in strangers)))

        # -- controller fights
        if len(ctrl_tracks[ch]) > 1 and len(names[ch]) > 1:
            findings.append(
                "ch%d: %d tracks write controllers to it (last write wins), "
                "and it carries %d named parts -- their dynamics will be "
                "wrong for one of them: %s"
                % (ch, len(ctrl_tracks[ch]), len(names[ch]),
                   ", ".join(sorted(names[ch]))))

        # -- volumes that mean silence
        for when, value in volumes[ch]:
            if 0 < value <= 16:
                findings.append(
                    "ch%d: CC7=%d at %.1fs is %.0f dB in GM -- near silence"
                    % (ch, value, when, 40 * __import__('math').log10(value / 127)))
            elif value == 0:
                findings.append("ch%d: CC7=0 at %.1fs is silence" % (ch, when))

        # -- notes the assigned instrument cannot play.  When this fires, the
        #    file's own shadowed program is very often the right answer: a
        #    name-driven remapper has nothing to match on for an unnamed track
        #    and will assign something anyway.
        if chosen and notes[ch] and chosen[1] in RANGES:
            lo, hi = RANGES[chosen[1]]
            out = [n for _, _, n in notes[ch] if n < lo or n > hi]
            if len(out) > max(4, 0.02 * len(notes[ch])):
                written_lo = min(n for _, _, n in notes[ch])
                written_hi = max(n for _, _, n in notes[ch])
                fits = [p for _, p, _ in at_zero[:-1]
                        if p in RANGES
                        and RANGES[p][0] <= written_lo
                        and RANGES[p][1] >= written_hi]
                hint = ""
                if fits:
                    hint = ("  The file's own shadowed program %s covers it -- "
                            "try that first."
                            % " / ".join("%d %s" % (p, GM_NAMES[p]) for p in fits))
                elif not names[ch]:
                    hint = ("  No track on this channel is named, so a "
                            "name-driven remap had nothing to go on.")
                findings.append(
                    "ch%d: %d of %d notes lie outside %s (%d-%d); "
                    "written range is %d-%d -- wrong program?%s"
                    % (ch, len(out), len(notes[ch]),
                       GM_NAMES[chosen[1]], lo, hi,
                       written_lo, written_hi, hint))

    if findings:
        print("\n   %d finding%s:" % (len(findings), "" if len(findings) == 1 else "s"))
        for f in findings:
            print("     - %s" % f)
    else:
        print("\n   nothing to report")
    print()
    return findings


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    total = 0
    for path in argv[1:]:
        total += len(check(path))
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
