"""The ensemble tones built 2026-10-26 (patch_map's SC88_CHEAP and SC8850_CHEAP:
strings, choirs and voices, orchestra hits), each selected as a GS file
selects it on the SC-8850 map (CC0 the bank, CC32 4), a short phrase apiece:
strings and choirs chords, a solo voice a line, the hits and the scat
syllables stabs. GROUP o strings, p choirs, q the voices' syllables, r hits,
s and t brass, u the trombones and tubas as single lines.
Writes OUT/ensemble_GROUP.wav (and _room.wav). The player is
examples/synths_demo.py's.

    python3 examples/ensemble_demo.py OUT GROUP
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

TEMPO = 116.0
RIFF = [(0, 0.5), (0, 0.5), (12, 0.5), (0, 0.5), (10, 0.5), (0, 0.5), (7, 0.5), (5, 0.5)]
LINE = [(0, 1), (2, 1), (4, 1), (7, 1), (9, 2), (7, 2)]
CHORDS = [((0, 4, 7, 11), 2), ((5, 9, 12, 16), 2), ((2, 5, 9, 12), 2), ((7, 11, 14, 17), 2)]
STABS = [((0,), 1), ((0,), 1), ((3,), 1), ((5,), 1), ((0,), 2)]
# trance offbeats: Am F C G, a chord on each off-beat
TRANCE = [(ch, 0.5) for c in ((0, 3, 7, 12), (-4, 0, 3, 8), (-9, -5, 0, 3), (-2, 2, 5, 10)) for ch in ((), c) * 4]
# (program, SC-8850 bank, name, phrase, root), by group: the ensemble tones
# built 2026-10-26 (patch_map SC88_CHEAP / SC8850_CHEAP) -- strings, choirs
# and voices, hits
GROUPS = {
    "o": [(48, 3, 'Cello sect.', 'chords', 60),
          (48, 4, 'Bright Str.2', 'chords', 60),
          (48, 5, 'Bright Str.3', 'chords', 60),
          (48, 6, 'Quad Strings', 'chords', 60),
          (48, 7, 'Mild Strings', 'chords', 60),
          (48, 12, 'Strings+Horn', 'chords', 60),
          (48, 13, 'Str.+Flute', 'chords', 60),
          (48, 14, 'Choir Str.2', 'chords', 60),
          (48, 15, 'Choir Str.3', 'chords', 60),
          (48, 17, 'St.Strings 2', 'chords', 60),
          (48, 18, 'St.Strings 3', 'chords', 60),
          (48, 19, 'Orchestra 3', 'chords', 60),
          (48, 20, 'Orchestra 4', 'chords', 60),
          (48, 32, 'Oct Strings1', 'chords', 60),
          (48, 33, 'Oct Strings2', 'chords', 60),
          (48, 34, 'ContraBsSect', 'chords', 60),
          (49, 2, 'SlowStrings3', 'chords', 60),
          (49, 11, 'St.Slow Str2', 'chords', 60),
          (49, 12, 'S.Str+Choir', 'chords', 60),
          (49, 13, 'S.Str+Choir2', 'chords', 60)],
    "p": [(52, 10, 'Church Choir', 'chords', 60),
          (52, 11, 'Boys Choir 1', 'chords', 60),
          (52, 12, 'Boys Choir 2', 'chords', 60),
          (52, 13, 'St.BoysChoir', 'chords', 60),
          (52, 14, 'Rich Choir', 'chords', 60),
          (52, 16, 'Choir Hahs', 'chords', 60),
          (52, 33, 'Male Aah+Str', 'chords', 60),
          (53, 1, 'Chorus Oohs', 'chords', 60),
          (53, 2, 'Voice Oohs 2', 'line', 60),
          (53, 3, 'Chorus Oohs2', 'chords', 60),
          (53, 4, 'OohsCodeMaj7', 'chords', 60),
          (53, 5, 'OohsCodeSus4', 'chords', 60),
          (53, 6, 'Jazz Scat', 'line', 60),
          (53, 9, 'JzVoice Dat', 'stabs', 60),
          (53, 10, 'JzVoice Bap', 'stabs', 60),
          (53, 11, 'JzVoice Dow', 'stabs', 60),
          (53, 12, 'JzVoice Thum', 'stabs', 60)],
    "q": [(53, 16, 'VoiceLah Fem', 'line', 60),
          (53, 17, 'ChorusLahFem', 'chords', 60),
          (53, 18, 'VoiceLuh Fem', 'line', 60),
          (53, 19, 'ChorusLuhFem', 'chords', 60),
          (53, 20, 'VoiceLan Fem', 'line', 60),
          (53, 21, 'ChorusLanFem', 'chords', 60),
          (53, 22, 'VoiceAah Fem', 'line', 60),
          (53, 23, 'VoiceUuh Fem', 'line', 60),
          (53, 24, 'Fem Lah&Lan', 'chords', 60),
          (53, 32, 'VoiceWah Mal', 'line', 60),
          (53, 33, 'ChorusWahMal', 'chords', 60),
          (53, 34, 'VoiceWoh Mal', 'line', 60),
          (53, 35, 'ChorusWohMal', 'chords', 60),
          (53, 36, 'VoiceAah Mal', 'line', 60),
          (53, 37, 'VoiceOoh Mal', 'line', 60)],
    "r": [(55, 11, 'Perc. Hit', 'stabs', 60),
          (55, 12, 'Shock Wave', 'stabs', 60),
          (55, 13, 'Bounce Hit', 'stabs', 60),
          (55, 14, 'Drill Hit', 'stabs', 60),
          (55, 15, 'Thrill Hit', 'stabs', 60),
          (55, 17, 'Techno Hit', 'stabs', 60),
          (55, 18, 'Dist. Hit', 'stabs', 60),
          (55, 20, 'Bit Hit', 'stabs', 60),
          (55, 21, 'Bim Hit', 'stabs', 60),
          (55, 22, 'Technorg Hit', 'stabs', 60),
          (55, 23, 'Rave Hit', 'stabs', 60),
          (55, 24, 'Strings Hit', 'stabs', 60),
          (55, 25, 'Stack Hit', 'stabs', 60),
          (55, 26, 'Industry Hit', 'stabs', 60),
          (55, 27, 'Clap Hit', 'stabs', 60)],
    # brass (patch_map SC88_CHEAP / SC8850_CHEAP, MAP_TONES' Synth Horn)
    "s": [(56, 2, 'Trumpet', 'line', 60),
          (56, 4, 'Trumpet & Nz', 'line', 60),
          (56, 16, '4th Trumpets', 'line', 60),
          (56, 26, 'Warm Tp.2', 'line', 60),
          (56, 27, 'Twin Tp.', 'line', 60),
          (56, 32, 'Syn. Trumpet', 'line', 60),
          (57, 2, 'Twin bones', 'chords', 48),
          (57, 3, 'Bones & Tuba', 'chords', 48),
          (57, 8, 'Bs. Trombone', 'chords', 48),
          (57, 16, 'Euphonium', 'chords', 48),
          (58, 8, 'Tuba + Horn', 'chords', 48),
          (59, 1, 'Cup Mute Tp', 'line', 60),
          (59, 3, 'MuteTrumpet3', 'line', 60),
          (59, 8, 'Muted Horns', 'line', 60),
          (60, 2, 'Horn + Orche', 'chords', 60),
          (60, 9, 'Dual Horns', 'line', 60),
          (60, 16, 'Synth Horn', 'line', 60),
          (60, 24, 'F.Horn Rip', 'stabs', 60),
          (61, 1, 'Brass ff', 'chords', 60)],
    "t": [(61, 2, 'Bones Sect.', 'chords', 60),
          (61, 3, 'St. Brass ff', 'chords', 60),
          (61, 4, 'Quad Brass1', 'chords', 60),
          (61, 5, 'Quad Brass2', 'chords', 60),
          (61, 9, 'Brass 3', 'chords', 60),
          (61, 10, 'Brass sfz', 'stabs', 60),
          (61, 12, 'Brass sfz 2', 'stabs', 60),
          (61, 14, 'FatPop Brass', 'chords', 60),
          (61, 17, 'Trumpet Fall', 'stabs', 60),
          (61, 24, 'Octave Brass', 'chords', 60),
          (61, 25, 'Brass + Reed', 'chords', 60),
          (61, 26, 'Fat + Reed', 'chords', 60),
          (61, 32, 'Orch Brass', 'chords', 60),
          (61, 33, 'Orch Brass 2', 'chords', 60),
          (61, 35, 'St.FatPopBrs', 'chords', 60),
          (61, 36, 'St.Orch Brs', 'chords', 60),
          (61, 37, 'St.Orch Brs2', 'chords', 60),
          (61, 38, 'St.Orch Brs3', 'chords', 60)],
    # the trombones and tubas again as single lines (u): a chord on Twin
    # bones is eight trombones, which read as a section
    "u": [(57, 2, 'Twin bones', 'line', 48), (57, 3, 'Bones & Tuba', 'line', 48), (57, 8, 'Bs. Trombone', 'line', 36),
          (57, 16, 'Euphonium', 'line', 48), (58, 8, 'Tuba + Horn', 'line', 36), (61, 2, 'Bones Sect.', 'line', 48)],
}
TONES = GROUPS["o"]


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / TEMPO), time=0))
    # GS Reset
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    ev = []
    t = 0.0
    for prog, lsb, _name, phrase, root in TONES:
        ev.append((t - 0.25, 0, ("cc", 0, lsb)))
        ev.append((t - 0.25, 1, ("cc", 32, 4)))
        ev.append((t - 0.25, 2, ("pc", prog)))
        b = t
        if phrase == "riff":
            seq = [((d,), l) for d, l in RIFF] * 2
        elif phrase == "line":
            seq = [((d,), l) for d, l in LINE]
        elif phrase == "chords":
            seq = CHORDS
        elif phrase == "trance":
            seq = TRANCE
        else:
            seq = STABS
        for notes, length in seq:
            dur = length * (0.9 if phrase not in ("stabs", "trance") else 0.45)
            for d in notes:
                ev.append((b, 3, ("on", root + d, 100)))
                ev.append((b + dur, 4, ("off", root + d)))
            b += length
        t = b + 1.5
    ev.sort(key=lambda e: (e[0], e[1]))
    now = 0
    for beat, _o, m in ev:
        tk = int(round((beat + 0.5) * 480))
        if m[0] == "cc":
            msg = mido.Message("control_change", channel=0, control=m[1], value=m[2], time=tk - now)
        elif m[0] == "pc":
            msg = mido.Message("program_change", channel=0, program=m[1], time=tk - now)
        elif m[0] == "on":
            msg = mido.Message("note_on", channel=0, note=m[1], velocity=m[2], time=tk - now)
        else:
            msg = mido.Message("note_off", channel=0, note=m[1], velocity=0, time=tk - now)
        tr.append(msg)
        now = tk
    tr.append(mido.MetaMessage("end_of_track", time=480 * 4))
    return mf


def main(argv):
    global TONES
    out = argv[1]
    grp = argv[2] if len(argv) > 2 else "o"
    TONES = GROUPS[grp]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "ensemble_%s.wav" % grp)
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)
    t = 0.0
    for prog, lsb, name, phrase, _root in TONES:
        n = {"riff": 8, "line": 8, "chords": 8, "stabs": 6, "trance": 16}[phrase]
        print("  %5.1f s  %s (SC-8850 %d.%d)" % (t * 60.0 / TEMPO, name, prog, lsb))
        t += n + 1.5
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
