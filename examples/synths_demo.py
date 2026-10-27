"""The synth tones built 2026-10-26 (sc88_synth: SC88_SYNTH's SC-88 Pro ones,
SC8850_SYNTH's, MAP_SYNTH's Transbrass) -- leads, basses, strings, voices,
brass, pads, effects -- each selected as a GS file selects it on the SC-8850
map (CC0 the bank, CC32 4), a short phrase apiece: basses a riff, the held
ones chords, leads and bells a line. 20 tones a GROUP (a, b, ...). Writes
OUT/synths_GROUP.wav (and _room.wav).

    python3 examples/synths_demo.py OUT GROUP
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
# (program, SC-8850 bank, name, phrase, root), by group: every synth tone built
# 2026-10-26 but the JP-8000 set (examples/jp8000_demo.py), in program order
GROUPS = {
    "a": [(38, 5, 'P5 Bass', 'riff', 36),
          (38, 21, 'Jungle Bass', 'riff', 36),
          (38, 22, 'Square Bass', 'riff', 36),
          (38, 23, 'Square Bass2', 'riff', 36),
          (38, 24, 'Arpeggio Bs', 'riff', 36),
          (38, 32, 'Hit&Saw Bass', 'riff', 36),
          (38, 33, 'Ring Bass', 'riff', 36),
          (38, 34, 'AtkSineBass', 'riff', 36),
          (38, 35, 'OB sine Bass', 'riff', 36),
          (38, 36, 'Auxiliary Bs', 'riff', 36),
          (38, 40, '303SqDistBs', 'riff', 36),
          (38, 41, '303SqDistBs2', 'riff', 36),
          (38, 42, '303SqDistBs3', 'riff', 36),
          (38, 43, '303Sqr.Rev', 'riff', 36),
          (38, 44, 'TeeBee', 'riff', 36),
          (39, 5, 'Mg Oct Bass1', 'riff', 36),
          (39, 10, 'X Wire Bass', 'riff', 36),
          (39, 11, 'WireStr Bass', 'riff', 36),
          (39, 12, 'Blip Bass', 'riff', 36),
          (39, 13, 'RubberBass 1', 'riff', 36)],
    "b": [(39, 14, 'Syn Bell Bs', 'riff', 36),
          (39, 15, 'Odd Bass', 'riff', 36),
          (39, 22, 'House Bass:', 'riff', 36),
          (39, 23, 'KG Bass', 'riff', 36),
          (39, 24, 'Sync Bass', 'riff', 36),
          (39, 26, 'RND Bass', 'riff', 36),
          (39, 28, 'Bubble Bass', 'riff', 36),
          (39, 30, 'Sync Bass 2', 'riff', 36),
          (39, 31, 'Pulse Mix Bs', 'riff', 36),
          (39, 32, 'MG Dist Bass', 'riff', 36),
          (39, 33, 'Seq Bass 2', 'riff', 36),
          (39, 34, '3rd Bass', 'riff', 36),
          (39, 35, 'MG Oct Bass', 'riff', 36),
          (39, 36, 'SlowEnvBass', 'riff', 36),
          (39, 37, 'Mild Bass', 'riff', 36),
          (39, 38, 'DistEnvBass', 'riff', 36),
          (39, 39, 'MG LightBass', 'riff', 36),
          (39, 40, 'DistSynBass', 'riff', 36),
          (39, 41, 'Rise Bass', 'riff', 36),
          (39, 42, 'Cyber Bass', 'riff', 36)],
    "c": [(50, 2, 'StackStrings', 'chords', 60),
          (50, 4, 'Chorus Str.', 'chords', 60),
          (50, 9, 'Syn.Strings4', 'chords', 60),
          (50, 10, 'Syn.Strings6', 'chords', 60),
          (50, 11, 'Syn.Strings7', 'chords', 60),
          (50, 12, 'LoFi Strings', 'chords', 60),
          (50, 16, 'High Strings', 'chords', 60),
          (50, 25, 'Noiz Strings', 'chords', 60),
          (51, 1, 'Syn.Strings5', 'chords', 60),
          (51, 3, 'FilteredOrch', 'chords', 60),
          (51, 4, 'JP Saw Str.', 'chords', 60),
          (51, 6, 'DistStrings', 'chords', 60),
          (51, 7, 'JUNOFullStr.', 'chords', 60),
          (51, 8, 'Air Strings', 'chords', 60),
          (51, 9, 'Atk Syn Str.', 'chords', 60),
          (51, 10, 'StraightStr.', 'chords', 60),
          (54, 1, 'SynVox 2', 'chords', 60),
          (54, 2, 'SynVox 3', 'chords', 60),
          (54, 9, 'Silent Night', 'chords', 60),
          (54, 10, 'Syn.Voice 2', 'chords', 60)],
    "d": [(54, 16, 'VP330 Choir', 'chords', 60),
          (54, 17, 'Vinyl Choir', 'chords', 60),
          (54, 18, 'JX8P Vox', 'chords', 60),
          (62, 2, 'Stack Brass', 'chords', 60),
          (62, 4, 'MKS Brass', 'chords', 60),
          (62, 18, 'OctSynBrass2', 'chords', 60),
          (62, 19, 'BPF Brass', 'chords', 60),
          (63, 2, 'Warm Brass', 'chords', 60),
          (63, 3, 'Synth Brass3', 'chords', 60),
          (63, 4, 'Sync Brass', 'chords', 60),
          (63, 5, 'Fat SynBrass', 'chords', 60),
          (63, 6, 'DeepSynBrass', 'chords', 60),
          (63, 10, 'Reso Brass', 'chords', 60),
          (63, 11, 'DistSqrBrass', 'chords', 60),
          (63, 12, 'JP8000SawBrs', 'chords', 60),
          (63, 17, 'Transbrass', 'chords', 60),
          (80, 9, 'Sine Lead', 'line', 72),
          (80, 11, 'Twin Sine', 'line', 72),
          (80, 19, 'Dist Square', 'line', 72),
          (80, 20, '303SquarDst1', 'line', 72)],
    "e": [(80, 21, '303SquarDst2', 'line', 72),
          (80, 22, '303 Mix Sqr', 'line', 72),
          (80, 23, 'Dual Sqr&Saw', 'line', 72),
          (80, 24, 'Pulse Lead', 'line', 72),
          (80, 28, 'JP8 PulseLd3', 'line', 72),
          (80, 29, '260RingLead', 'line', 72),
          (80, 30, '303DistLead', 'line', 72),
          (80, 32, 'HipHop SinLd', 'line', 72),
          (80, 33, 'HipHop SqrLd', 'line', 72),
          (80, 34, 'HipHop PlsLd', 'line', 72),
          (80, 35, 'Flux Pulse', 'line', 72),
          (81, 17, 'PM Lead', 'line', 72),
          (81, 33, 'P5 Saw Lead', 'line', 72),
          (81, 35, 'Oct Saw Lead', 'line', 72),
          (81, 40, 'SequenceSaw1', 'line', 72),
          (81, 41, 'SequenceSaw2', 'line', 72),
          (81, 42, 'Reso Saw', 'line', 72),
          (81, 43, 'Cheese Saw 1', 'line', 72),
          (81, 44, 'Cheese Saw 2', 'line', 72),
          (81, 45, 'Rhythmic Saw', 'line', 72)],
    "f": [(82, 8, 'LM Pure Lead', 'line', 72),
          (82, 9, 'LM Blow Lead', 'line', 72),
          (83, 2, 'Hybrid Lead', 'line', 72),
          (83, 3, 'Unison SqrLd', 'line', 72),
          (83, 4, 'FatSolo Lead', 'line', 72),
          (83, 5, 'ForcefulLead', 'line', 72),
          (83, 6, 'Oct.UnisonLd', 'line', 72),
          (83, 7, 'Unison SawLd', 'line', 72),
          (83, 8, 'Mad Lead', 'line', 72),
          (83, 9, 'CrowdingLead', 'line', 72),
          (83, 10, 'Double Sqr.', 'line', 72),
          (84, 2, 'FB.Charang', 'riff', 48),
          (84, 3, 'Fat GR Lead', 'riff', 48),
          (84, 4, 'Windy GR Ld', 'riff', 48),
          (84, 5, 'Mellow GR Ld', 'riff', 48),
          (84, 6, 'GR & Pulse', 'riff', 48),
          (84, 11, 'Dance Dst.Gt', 'riff', 48),
          (84, 12, 'DanceDst.Gt2', 'riff', 48),
          (84, 16, 'P5 Sync Lead', 'riff', 48),
          (84, 17, 'Fat SyncLead', 'riff', 48)],
    "g": [(84, 18, 'Rock Lead', 'riff', 48),
          (84, 19, '5th DecaSync', 'riff', 48),
          (84, 20, 'Dirty Sync', 'riff', 48),
          (84, 21, 'DualSyncLead', 'riff', 48),
          (84, 22, 'LA Brass Ld', 'riff', 48),
          (84, 25, '2600 Sub Osc', 'riff', 48),
          (85, 1, 'Solo Vox 2', 'line', 72),
          (85, 8, 'Vox Lead', 'line', 72),
          (85, 9, 'LFO Vox', 'line', 72),
          (85, 10, 'Vox Lead 2', 'line', 72),
          (86, 2, '5th Lead', 'line', 72),
          (86, 3, '5th Ana.Clav', 'line', 72),
          (86, 4, '5th Pulse', 'line', 72),
          (86, 8, '4th Lead', 'line', 72),
          (88, 2, 'New Age Pad', 'chords', 60),
          (88, 4, 'Fantasia 3', 'chords', 60),
          (88, 5, 'Fantasia 4', 'chords', 60),
          (88, 6, 'After D !', 'chords', 60),
          (88, 7, '260HarmPad', 'chords', 60),
          (89, 6, 'OB Soft Pad2', 'chords', 60)],
    "h": [(89, 8, 'Octave Pad', 'chords', 60),
          (89, 9, 'Stack Pad', 'chords', 60),
          (89, 10, 'Human Pad', 'chords', 60),
          (89, 11, 'Sync Brs.Pad', 'chords', 60),
          (89, 12, 'Oct.PWM Pad', 'chords', 60),
          (89, 13, 'JP Soft Pad', 'chords', 60),
          (90, 2, 'Polysynth 2', 'chords', 60),
          (90, 3, 'Poly King', 'chords', 60),
          (90, 4, 'Super Poly', 'chords', 60),
          (90, 9, 'Octave Stack', 'chords', 60),
          (90, 10, 'Reso Stack', 'chords', 60),
          (90, 11, 'Techno Stack', 'chords', 60),
          (90, 12, 'Pulse Stack', 'chords', 60),
          (90, 13, 'TwinOct.Rave', 'chords', 60),
          (90, 14, 'Oct.Rave', 'chords', 60),
          (90, 15, 'Happy Synth', 'chords', 60),
          (90, 16, 'ForwardSweep', 'chords', 60),
          (90, 17, 'ReverseSweep', 'chords', 60),
          (90, 24, 'Minor Rave', 'chords', 60),
          (91, 2, 'SC Heaven', 'chords', 60)],
    "i": [(91, 4, 'Water Space', 'chords', 60),
          (91, 5, 'Cold Space', 'chords', 60),
          (91, 6, 'Noise Peaker', 'chords', 60),
          (91, 8, 'Cosmic Voice', 'chords', 60),
          (91, 9, 'Auh Vox', 'chords', 60),
          (91, 10, 'AuhAuh', 'chords', 60),
          (91, 11, 'Vocorderman', 'chords', 60),
          (91, 12, 'Holy Voices', 'chords', 60),
          (92, 1, 'SoftBellPad', 'chords', 60),
          (92, 3, '7thBelPad', 'chords', 60),
          (93, 4, 'Special Rave', 'chords', 60),
          (93, 5, 'Metal Pad 2', 'chords', 60),
          (94, 1, 'Vox Pad', 'chords', 60),
          (94, 2, 'Vox Sweep', 'chords', 60),
          (94, 8, 'Horror Pad', 'chords', 60),
          (94, 9, 'SynVox Pad', 'chords', 60),
          (94, 10, 'SynVox Pad 2', 'chords', 60),
          (94, 11, 'Breath&Rise', 'chords', 60),
          (94, 12, 'Tears Voices', 'chords', 60),
          (95, 2, 'Ambient BPF', 'chords', 60)],
    "j": [(95, 3, 'Sync Pad', 'chords', 60),
          (95, 4, 'Warriors', 'chords', 60),
          (95, 11, 'Bag Sweep', 'chords', 60),
          (95, 12, 'Sweep Pipe', 'chords', 60),
          (95, 13, 'Sweep Stack', 'chords', 60),
          (95, 14, 'Deep Sweep', 'chords', 60),
          (95, 15, 'Stray Pad', 'chords', 60),
          (96, 5, 'Saw Impulse', 'chords', 60),
          (96, 6, 'Strange Str.', 'chords', 60),
          (96, 7, 'FastFWD Pad', 'chords', 60),
          (97, 3, 'Prologue 2', 'chords', 60),
          (97, 4, 'Hols Strings', 'chords', 60),
          (97, 5, 'HistoryWave', 'chords', 60),
          (98, 10, 'Music Bell', 'line', 72),
          (98, 11, 'Analog Bell', 'line', 72),
          (98, 12, 'Blow Bell', 'line', 72),
          (98, 13, 'Hyper Bell', 'line', 72),
          (98, 21, 'JP Bell', 'line', 72),
          (98, 23, 'Bottom Bell', 'line', 72),
          (99, 7, 'Invisible', 'chords', 60)],
    "k": [(99, 8, 'Pulsey Key', 'chords', 60),
          (99, 10, 'Heaven Atmos', 'chords', 60),
          (100, 1, 'Shining Star', 'line', 72),
          (100, 3, 'Brass Star', 'line', 72),
          (100, 5, 'D-50 Retour', 'line', 72),
          (100, 6, 'SouthernWind', 'line', 72),
          (100, 7, 'SymbolicBell', 'line', 72),
          (101, 3, 'Abduction', 'chords', 60),
          (101, 4, 'Auhbient', 'chords', 60),
          (101, 5, 'LFO Pad', 'chords', 60),
          (101, 6, 'Random Str', 'chords', 60),
          (101, 7, 'Random Pad', 'chords', 60),
          (101, 8, 'LowBirds Pad', 'chords', 60),
          (101, 9, 'Falling Down', 'chords', 60),
          (101, 10, 'LFO RAVE', 'chords', 60),
          (101, 11, 'LFO Horror', 'chords', 60),
          (101, 12, 'LFO Techno', 'chords', 60),
          (101, 13, 'Alternative', 'chords', 60),
          (101, 14, 'UFO FX', 'chords', 60),
          (101, 15, 'Gargle Man', 'chords', 60)],
    "l": [(101, 16, 'Sweep FX', 'chords', 60),
          (101, 17, 'LM Has Come', 'chords', 60),
          (101, 18, 'FallinInsect', 'chords', 60),
          (101, 19, 'LFO Oct.Rave', 'chords', 60),
          (101, 20, 'Just Before', 'chords', 60),
          (101, 21, 'RND Fl.Chord', 'chords', 60),
          (101, 22, 'RandomEnding', 'chords', 60),
          (101, 23, 'Random Sine', 'chords', 60),
          (101, 24, 'EatingFilter', 'chords', 60),
          (101, 25, 'Noise&SawHit', 'chords', 60),
          (101, 28, 'Dirty Stack', 'chords', 60),
          (101, 29, 'Big Blue', 'chords', 60),
          (101, 30, 'Static Hit', 'chords', 60),
          (101, 31, 'Atl.Mod.FX', 'chords', 60),
          (101, 32, 'Acid Copter', 'chords', 60),
          (102, 7, 'Echo SynBass', 'chords', 60),
          (102, 8, 'Pan Sequence', 'chords', 60),
          (102, 9, 'Aqua', 'chords', 60),
          (102, 10, 'Panning Lead', 'chords', 60),
          (102, 11, 'PanningBrass', 'chords', 60)],
    "m": [(103, 2, 'Star Mind', 'chords', 60),
          (103, 3, 'Star Dust', 'chords', 60),
          (103, 4, 'Rep.Trance', 'chords', 60),
          (103, 5, 'Etherality', 'chords', 60),
          (103, 6, 'Mystic Pad', 'chords', 60),
          (103, 9, 'Silky Pad', 'chords', 60),
          (103, 10, 'Dream Pad 2', 'chords', 60),
          (103, 11, 'Silky Pad 2', 'chords', 60),
          (103, 16, 'New Century', 'chords', 60),
          (103, 17, '7th Atmos.', 'chords', 60),
          (103, 18, 'Galaxy Way', 'chords', 60),
          (103, 19, 'Rising OSC.', 'chords', 60)],
}
TONES = GROUPS["a"]


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
    grp = argv[2] if len(argv) > 2 else "a"
    TONES = GROUPS[grp]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "synths_%s.wav" % grp)
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
