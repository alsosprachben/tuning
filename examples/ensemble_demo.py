"""The ensemble tones built 2026-10-26 (patch_map's SC88_CHEAP and SC8850_CHEAP:
strings, choirs and voices, orchestra hits), each selected as a GS file
selects it on the SC-8850 map (CC0 the bank, CC32 4), a short phrase apiece:
strings and choirs chords, a solo voice a line, the hits and the scat
syllables stabs. GROUP o strings, p choirs, q the voices' syllables, r hits,
s and t brass, u the trombones and tubas as single lines,
v and w the organs, accordions, harmonicas and bandoneons.
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
    # the organs, accordions, harmonicas, bandoneons (v, w)
    "v": [(16, 2, 'Ful Organ 1', 'chords', 60),
          (16, 3, 'Ful Organ 2', 'chords', 60),
          (16, 4, 'Ful Organ 3', 'chords', 60),
          (16, 5, 'Ful Organ 4', 'chords', 60),
          (16, 6, 'Ful Organ 5', 'chords', 60),
          (16, 7, 'Ful Organ 6', 'chords', 60),
          (16, 9, 'Organ o', 'chords', 60),
          (16, 10, 'Ful Organ 7', 'chords', 60),
          (16, 11, 'Ful Organ 8', 'chords', 60),
          (16, 12, 'Ful Organ 9', 'chords', 60),
          (16, 19, 'Farf Organ', 'chords', 60),
          (16, 27, 'Hybrid Organ', 'chords', 60),
          (16, 28, 'VS Organ', 'chords', 60),
          (16, 29, 'Digi Church', 'chords', 60),
          (16, 30, 'JX-8P Organ', 'chords', 60),
          (16, 31, 'FM Organ', 'chords', 60),
          (16, 48, '5th Organ', 'chords', 60),
          (17, 1, 'Jazz Organ', 'chords', 60),
          (17, 2, 'E.Organ 16+2', 'chords', 60),
          (17, 3, 'Jazz Organ 2', 'chords', 60)],
    "w": [(17, 4, 'Jazz Organ 3', 'chords', 60),
          (17, 5, 'Jazz Organ 4', 'chords', 60),
          (17, 6, 'Jazz Organ 5', 'chords', 60),
          (17, 7, 'Jazz Organ 6', 'chords', 60),
          (17, 9, 'Octave Organ', 'chords', 60),
          (17, 33, 'Perc.Organ 2', 'chords', 60),
          (17, 34, 'Perc.Organ 3', 'chords', 60),
          (17, 35, 'Perc.Organ 4', 'chords', 60),
          (18, 17, 'Rock Organ 1', 'chords', 60),
          (18, 18, 'Rock Organ 2', 'chords', 60),
          (19, 33, 'Theater Org.', 'chords', 60),
          (20, 8, 'Wind Organ', 'chords', 60),
          (21, 9, 'Dist. Accord', 'chords', 60),
          (21, 16, 'Cho. Accord', 'chords', 60),
          (21, 24, 'Hard Accord', 'chords', 60),
          (21, 25, 'Soft Accord', 'chords', 60),
          (22, 8, 'B.Harp Basic', 'line', 72),
          (22, 9, 'B.Harp Suppl', 'line', 72),
          (23, 8, 'Bandoneon 2', 'chords', 60),
          (23, 16, 'Bandoneon 3', 'chords', 60)],
    # the keyboards and chromatic percussion (x), guitars (y), basses and strings (z), reeds and pipes (aa)
    "x": [(0, 1, 'UprightPiano', 'chords', 60),
          (0, 2, 'Mild Piano', 'chords', 60),
          (0, 9, 'Mild Piano w', 'chords', 60),
          (0, 24, 'Piano + Str.', 'chords', 60),
          (0, 25, 'Piano + Str2', 'chords', 60),
          (0, 26, 'Piano+Choir1', 'chords', 60),
          (0, 27, 'Piano+Choir2', 'chords', 60),
          (1, 1, 'Pop Piano', 'chords', 60),
          (1, 2, 'Rock Piano', 'chords', 60),
          (1, 9, 'Rock Piano w', 'chords', 60),
          (4, 9, 'Cho. E.Piano', 'chords', 60),
          (4, 10, 'SilentRhodes', 'chords', 60),
          (4, 17, 'Dist E.Piano', 'chords', 60),
          (5, 1, 'E.Piano 3', 'chords', 60),
          (5, 9, 'Detuned EP 3', 'chords', 60),
          (6, 1, 'Harpsichord2', 'chords', 60),
          (6, 2, 'Harpsichord3', 'chords', 60),
          (6, 32, 'Synth Harpsi', 'chords', 60),
          (7, 1, 'Clav. 2', 'chords', 60),
          (7, 2, 'Atk Clav.1', 'chords', 60),
          (7, 3, 'Atk Clav.2', 'chords', 60),
          (7, 8, 'Comp Clav.', 'chords', 60)],
    "x2": [(7, 16, 'Reso Clav.', 'chords', 60),
           (7, 17, 'Phase Clav', 'chords', 60),
           (7, 24, 'Clav.o', 'chords', 60),
           (7, 32, 'Analog Clav.', 'chords', 60),
           (7, 36, 'SynRingClav.', 'chords', 60),
           (7, 37, 'SynDistClav.', 'chords', 60),
           (7, 38, 'JP8000 Clav.', 'chords', 60),
           (8, 1, 'Pop Celesta', 'chords', 60),
           (10, 1, 'Music Box 2', 'chords', 60),
           (10, 8, 'St.Music Box', 'chords', 60),
           (11, 9, 'Vibraphones', 'chords', 60),
           (13, 8, 'Xylophone w', 'chords', 60),
           (14, 10, 'Church Bell2', 'chords', 60),
           (14, 16, 'Tubularbellw', 'chords', 60),
           (15, 2, 'Santur 3', 'chords', 60),
           (15, 16, 'Zither 1', 'chords', 60),
           (15, 17, 'Zither 2', 'chords', 60),
           (15, 24, 'Dulcimer', 'chords', 60)],
    "y": [(25, 10, 'Atk Steel Gt', 'chords', 60),
          (25, 17, 'Mandolin 2', 'chords', 60),
          (25, 18, 'MandolinTrem', 'chords', 60),
          (27, 1, 'Clean Half', 'chords', 60),
          (27, 2, 'Open Hard 1', 'chords', 60),
          (27, 3, 'Open Hard 2', 'chords', 60),
          (27, 5, 'Atk CleanGt.', 'chords', 60),
          (27, 9, 'JC Chorus Gt', 'chords', 60),
          (27, 16, 'TC FrontPick', 'chords', 60),
          (27, 17, 'TC Rear Pick', 'chords', 60),
          (27, 18, 'TC Clean ff', 'chords', 60),
          (27, 19, 'TC Clean 2:', 'chords', 60),
          (27, 20, 'LP Rear Pick', 'chords', 60),
          (27, 21, 'LP Rear 2', 'chords', 60),
          (27, 22, 'LP RearAtack', 'chords', 60),
          (27, 24, 'Chung Ruan', 'chords', 60),
          (27, 25, 'Chung Ruan 2', 'chords', 60),
          (28, 2, 'TC Muted Gt.', 'chords', 60),
          (29, 1, 'Overdrive 2', 'chords', 60),
          (29, 2, 'Overdrive 3', 'chords', 60),
          (29, 5, 'Attack Drive', 'chords', 60),
          (29, 8, 'LP OverDrvGt', 'chords', 60)],
    "y2": [(29, 9, 'LP OverDrv:', 'chords', 60),
           (29, 10, 'LP Half Drv', 'chords', 60),
           (29, 11, 'LP Half Drv2', 'chords', 60),
           (29, 12, 'LP Chorus', 'chords', 60),
           (30, 3, 'Distortion:', 'chords', 60),
           (30, 4, 'Dist.Fast', 'chords', 60),
           (30, 5, 'Attack Dist', 'chords', 60),
           (31, 9, 'Gt.Feedback2', 'stabs', 60),
           (31, 24, 'E.Bass Harm.', 'stabs', 60)],
    "z": [(32, 1, 'Rockabilly', 'line', 36),
          (32, 8, 'Wild A.Bass', 'line', 36),
          (32, 9, 'Atk A.Bass', 'line', 36),
          (32, 16, 'Bass + OHH', 'line', 36),
          (33, 3, 'Jazz Bass 2', 'line', 36),
          (33, 4, 'Rock Bass', 'line', 36),
          (33, 5, 'Heart Bass', 'line', 36),
          (33, 6, 'AttackFinger', 'line', 36),
          (33, 8, 'ChorusJazzBs', 'line', 36),
          (33, 16, 'F.Bass/Harm.', 'line', 36),
          (34, 2, 'Picked Bass3', 'line', 36),
          (34, 3, 'Picked Bass4', 'line', 36),
          (34, 4, 'Double Pick', 'line', 36),
          (34, 16, 'P.Bass/Harm.', 'line', 36),
          (35, 8, 'Wood+FlessBs', 'line', 36),
          (36, 1, 'Slap Pop', 'line', 36),
          (36, 9, 'Unison Slap', 'line', 36),
          (37, 1, 'Slap Bass 3', 'line', 36),
          (37, 8, 'FM Slap', 'line', 36),
          (40, 1, 'Violin Atk:', 'line', 60),
          (41, 1, 'Viola Atk.:', 'line', 55),
          (42, 1, 'Cello Atk.:', 'line', 43)],
    "z2": [(44, 2, 'Trem Str.St.', 'chords', 60),
           (44, 10, 'SuspenseStr2', 'chords', 60),
           (45, 1, 'Vcs&Cbs Pizz', 'line', 48),
           (45, 2, 'Chamber Pizz', 'line', 48),
           (45, 3, 'St.Pizzicato', 'line', 48),
           (45, 8, 'Solo Pizz.', 'line', 48),
           (45, 17, 'StringsSpic.', 'line', 48),
           (46, 1, 'Harp&Strings', 'chords', 55),
           (46, 2, 'Harp St.', 'chords', 55),
           (46, 8, 'Uillean Harp', 'chords', 55),
           (46, 16, 'Synth Harp', 'chords', 55),
           (46, 25, 'Yang Qin 2', 'chords', 55),
           (46, 26, 'SynthYangQin', 'chords', 55)],
    "aa": [(64, 8, 'Soprano Exp.', 'line', 67),
           (65, 9, 'Grow Sax', 'line', 60),
           (65, 16, 'AltoSax + Tp', 'line', 60),
           (65, 17, 'Sax Section', 'line', 60),
           (66, 1, 'Tenor Sax', 'line', 55),
           (66, 9, 'St.Tenor Sax', 'line', 55),
           (67, 1, 'Bari. Sax', 'line', 48),
           (67, 8, 'Bari & Tenor', 'line', 48),
           (68, 8, 'Oboe Exp.', 'line', 67),
           (68, 16, 'Multi Reed', 'line', 67),
           (71, 16, 'Multi Wind', 'line', 60),
           (71, 17, 'Quad Wind', 'line', 60),
           (72, 8, 'Nay', 'line', 67),
           (72, 9, 'Nay Tremolo', 'line', 67),
           (72, 16, 'Di', 'line', 67),
           (73, 2, 'Flute Exp.', 'line', 72),
           (73, 8, 'Flute + Vln', 'line', 72),
           (73, 9, 'Pipe & Reed', 'line', 72),
           (73, 17, 'Indian Flute', 'line', 72),
           (75, 16, 'Zampona', 'line', 72),
           (75, 17, 'Zampona Atk', 'line', 72),
           (75, 24, 'Tin Whistle', 'line', 72)],
    "aa2": [(75, 25, 'TinWhtsle Nm', 'line', 72),
            (75, 26, 'TinWhtsle Or', 'line', 72),
            (77, 1, 'Shakuhachi:', 'line', 67),
            (78, 1, 'Whistle 2', 'line', 79)],
    # the ethnic tones (ab)
    "ab": [(104, 3, 'Sitar 3', 'line', 60), (104, 4, 'Sitar/Drone', 'line', 60), (104, 5, 'Sitar 4', 'line', 60),
           (105, 9, 'San Xian', 'line', 60), (105, 28, 'Oud+Strings', 'chords', 55), (105, 32, 'Pi Pa', 'line', 67),
           (106, 8, 'Syn Shamisen', 'line', 60), (107, 1, 'Gu Zheng', 'chords', 60), (107, 19, 'Kanoon+Choir', 'chords', 60),
           (107, 24, 'Oct Harp', 'chords', 60), (108, 8, 'Sanza', 'line', 67), (110, 8, 'Er Hu', 'line', 67),
           (110, 9, 'Gao Hu', 'line', 74), (111, 24, 'Mizmar', 'line', 67), (111, 32, 'Suona 1', 'line', 67),
           (111, 33, 'Suona 2', 'line', 67)],
    # the fitted ethnic voices (ac): the bodhran open and muted, played as a
    # pitched part at its recorded F#2; the didgeridoo's drone, held
    # the insertion choruses (ad): their depth law's A/B (TUNING_EFX_DEPTH_SCALE)
    "ad": [(27, 9, 'JC Chorus Gt', 'chords', 60), (29, 12, 'LP Chorus', 'chords', 60),
           (33, 8, 'ChorusJazzBs', 'line', 36)],
    "ac": [(108, 9, 'Bodhran', 'jig', 42), (108, 10, 'Bodhran Mute', 'jig', 42),
           (109, 8, 'Didgeridoo', 'drone', 36)],
    # the percussive tones (af, af3: hits and the gamelan; af2: the menus up 16 keys)
    "af": [(112, 12, 'Jang-Gu', 'stabs', 60),
           (113, 16, 'Tambourine', 'stabs', 60),
           (114, 1, 'Island Mlt', 'line', 60),
           (115, 16, 'Angklung', 'line', 60),
           (115, 17, 'Angkl Rhythm', 'line', 60),
           (115, 24, 'Finger Snaps', 'stabs', 60),
           (115, 32, '909 HandClap', 'stabs', 60),
           (116, 1, 'Small Taiko', 'stabs', 60),
           (116, 16, 'Jungle BD', 'stabs', 60),
           (116, 17, 'Techno BD', 'stabs', 60),
           (116, 18, 'Bounce', 'stabs', 60),
           (117, 16, 'Rash SD', 'stabs', 60),
           (117, 17, 'House SD', 'stabs', 60),
           (117, 18, 'Jungle SD', 'stabs', 60),
           (117, 19, '909 SD', 'stabs', 60),
           (118, 11, '606 Tom', 'stabs', 60),
           (118, 12, '909 Tom', 'stabs', 60),
           (119, 2, 'Reverse Cym3', 'stabs', 60),
           (112, 13, 'Jegogan', 'line', 60),
           (112, 14, 'Jublag', 'line', 60),
           (112, 15, 'Pemade', 'line', 60),
           (112, 17, 'Kajar', 'stabs', 60),
           (112, 18, 'Kelontuk', 'stabs', 60),
           (112, 19, 'Kelontuk Mt', 'stabs', 60)],
    "af3": [(112, 20, 'Kelontuk Sid', 'stabs', 60),
            (112, 21, 'Kopyak Op', 'stabs', 60),
            (112, 22, 'Kopyak Mt', 'stabs', 60),
            (112, 23, 'Ceng Ceng', 'stabs', 60),
            (112, 24, 'Reyoung', 'line', 60),
            (112, 25, 'Kempur', 'stabs', 60),
            (116, 24, 'KendangWadon', 'stabs', 60),
            (116, 25, 'Bebarongan', 'stabs', 60),
            (116, 26, 'Pelegongan', 'stabs', 60),
            (116, 27, 'Dholak 1', 'stabs', 60),
            (116, 28, 'Dholak 2', 'stabs', 60),
            (112, 32, 'Jngl Crash', 'stabs', 60),
            (116, 32, 'Jngl BD Roll', 'stabs', 60),
            (117, 24, 'Jngl SD Roll', 'stabs', 60),
            (116, 9, 'ConcertBD Mt', 'stabs', 60),
            (117, 2, 'Real Tom 2', 'stabs', 60),
            (117, 3, 'Jazz Tom', 'stabs', 60),
            (117, 4, 'Brush Tom', 'stabs', 60),
            (119, 3, 'Reverse Cym4', 'stabs', 60),
            (119, 26, 'Rev.Tom 3', 'stabs', 60),
            (119, 27, 'Rev.Tom 4', 'stabs', 60),
            (118, 13, '606 Dist.Tom', 'stabs', 60)],
    "af2": [(116, 40, 'Kick Menu 1', 'menu', 36),
            (116, 41, 'Kick Menu 2', 'menu', 36),
            (116, 42, 'Kick Menu 3', 'menu', 36),
            (116, 43, 'Kick Menu 4', 'menu', 36),
            (117, 40, 'SD Menu 1', 'menu', 36),
            (117, 41, 'SD Menu 2', 'menu', 36),
            (117, 42, 'SD Menu 3', 'menu', 36),
            (117, 43, 'SD Menu 4', 'menu', 36),
            (117, 44, 'SD Menu 5', 'menu', 36),
            (112, 40, 'Crash Menu', 'menu', 36),
            (112, 41, 'RideCym Menu', 'menu', 36),
            (112, 42, 'RideBellMenu', 'menu', 36),
            (115, 40, 'HandClapMenu', 'menu', 36),
            (119, 40, 'Rev.SD Menu1', 'menu', 36),
            (119, 41, 'Rev.SD Menu2', 'menu', 36),
            (119, 42, 'Rev.SD Menu3', 'menu', 36),
            (119, 43, 'Rev.BD Menu1', 'menu', 36),
            (119, 44, 'Rev.BD Menu2', 'menu', 36),
            (119, 45, 'Rev.BD Menu3', 'menu', 36),
            (119, 46, 'Rev.ClapMenu', 'menu', 36)],
    # the SFX tones (ag, ag3, ag4: one-shots; ag2: the menus up 16 keys)
    "ag": [(120, 9, 'Bartok Pizz.', 'stabs', 60),
           (120, 10, 'Guitar Slap', 'stabs', 60),
           (120, 11, 'Chord Stroke', 'stabs', 60),
           (122, 6, 'Wind 2', 'stabs', 60),
           (124, 8, 'ScratchKey', 'stabs', 60),
           (124, 9, 'TapeRewind', 'stabs', 60),
           (125, 11, 'Perc. Bang', 'stabs', 60),
           (126, 7, 'Small Club', 'stabs', 60),
           (126, 8, 'ApplauseWave', 'stabs', 60),
           (126, 16, 'Voice One', 'stabs', 60),
           (126, 17, 'Voice Two', 'stabs', 60),
           (126, 18, 'Voice Three', 'stabs', 60),
           (126, 19, 'Voice Tah', 'stabs', 60),
           (126, 20, 'Voice Whey', 'stabs', 60),
           (127, 4, 'Eruption', 'stabs', 60),
           (120, 22, 'A.Bs.Mute Nz', 'stabs', 60),
           (120, 23, 'A.Bs.TouchNz', 'stabs', 60),
           (120, 24, 'A.Bs.AtackNz', 'stabs', 60),
           (120, 25, 'TC Up Nz', 'stabs', 60),
           (120, 26, 'TC DownMt.Nz', 'stabs', 60),
           (120, 27, 'TC UpMt.Nz', 'stabs', 60),
           (120, 28, 'TC Down Nz', 'stabs', 60),
           (120, 29, 'DstGT.Up Nz', 'stabs', 60),
           (120, 30, 'DstGT.DwnNz1', 'stabs', 60),
           (120, 31, 'DstGT.DwnNz2', 'stabs', 60),
           (120, 32, 'DstGT.MuteNz', 'stabs', 60),
           (120, 34, 'Gt.StrokeNz5', 'stabs', 60),
           (120, 35, 'StlGt.SldNz1', 'stabs', 60),
           (120, 36, 'StlGt.SldNz2', 'stabs', 60),
           (120, 37, 'StlGt.SldNz3', 'stabs', 60)],
    "ag3": [(120, 38, 'StlGt.SldNz4', 'stabs', 60),
            (120, 39, 'Gt.StrokeNz1', 'stabs', 60),
            (120, 40, 'Gt.StrokeNz2', 'stabs', 60),
            (120, 41, 'Gt.StrokeNz3', 'stabs', 60),
            (120, 42, 'Gt.StrokeNz4', 'stabs', 60),
            (121, 3, 'Fl.Breath 1', 'stabs', 60),
            (121, 4, 'Fl.Breath 2', 'stabs', 60),
            (121, 5, 'Fl.Breath 3', 'stabs', 60),
            (121, 6, 'Vox Breath 1', 'stabs', 60),
            (121, 7, 'Vox Breath 2', 'stabs', 60),
            (121, 8, 'Trombone Nz', 'stabs', 60),
            (121, 9, 'Trumpet Nz', 'stabs', 60),
            (122, 7, 'Cricket', 'stabs', 60),
            (123, 6, 'Growl 2', 'stabs', 60),
            (123, 7, 'Fancy Animal', 'stabs', 60),
            (123, 8, 'Seal', 'stabs', 60),
            (124, 12, 'Scratch 3', 'stabs', 60),
            (124, 13, 'Scratch 4', 'stabs', 60),
            (124, 14, 'Scratch 5', 'stabs', 60),
            (124, 15, 'Scratch 6', 'stabs', 60),
            (124, 16, 'Scratch 7', 'stabs', 60),
            (125, 13, 'Glass & Glam', 'stabs', 60),
            (125, 14, 'Ice Ring', 'stabs', 60),
            (125, 15, 'Over Blow', 'stabs', 60),
            (125, 16, 'Crack Bottle', 'stabs', 60),
            (125, 17, 'Pour Bottle', 'stabs', 60),
            (125, 18, 'Soda', 'stabs', 60),
            (125, 19, 'Open CD Tray', 'stabs', 60),
            (125, 20, 'Audio Switch', 'stabs', 60),
            (125, 22, 'SL 1', 'stabs', 60)],
    "ag4": [(125, 23, 'SL 2', 'stabs', 60),
            (125, 24, 'Car Engine 2', 'stabs', 60),
            (125, 25, 'Car Horn', 'stabs', 60),
            (125, 26, 'Boeeeen', 'stabs', 60),
            (125, 27, 'R.Crossing', 'stabs', 60),
            (125, 28, 'Compresser', 'stabs', 60),
            (125, 29, 'Sword Boom!', 'stabs', 60),
            (125, 30, 'Sword Cross', 'stabs', 60),
            (125, 31, 'Stab! 1', 'stabs', 60),
            (125, 32, 'Stab! 2', 'stabs', 60),
            (126, 9, 'BabyLaughing', 'stabs', 60),
            (126, 22, 'Voice Kikit', 'stabs', 60),
            (126, 23, 'Voice ComeOn', 'stabs', 60),
            (126, 24, 'Voice Aou', 'stabs', 60),
            (126, 25, 'Voice Oou', 'stabs', 60),
            (126, 26, 'Voice Hie', 'stabs', 60),
            (127, 6, 'Explosion 2', 'stabs', 60),
            (122, 16, 'Pink Noise', 'stabs', 60),
            (125, 12, 'Burner', 'stabs', 60),
            (120, 13, 'Biwa Tremolo', 'stabs', 60),
            (124, 11, 'MC-500 Beep', 'stabs', 60)],
    "ag2": [(120, 8, 'Gt. FX Menu', 'menu', 36),
            (120, 16, 'A.Bs.Nz Menu', 'menu', 36),
            (120, 17, 'D.Gt.Nz Menu', 'menu', 36),
            (120, 18, 'E.Gt.NzMenu1', 'menu', 36),
            (120, 19, 'E.Gt.NzMenu2', 'menu', 36),
            (120, 20, 'G.StrokeMenu', 'menu', 36),
            (120, 21, 'Gt.SlideMenu', 'menu', 36),
            (121, 2, 'Brth Nz Menu', 'menu', 36),
            (125, 21, 'Key Typing', 'menu', 36)],
    # the uilleann pipes (ae): a reel in D, the drones under it
    "ae": [(109, 9, 'Uillean Pipe', 'reel', 62), (109, 10, 'UillnPipe Nm', 'reel', 62),
           (109, 11, 'UillnPipe Or', 'reel', 62)],
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
        elif phrase == "jig":
            # a jig's 6/8, the tipper's down-up-down and the accents' rests
            seq = [((0,), 1 / 3.0)] * 3 + [((0,), 2 / 3.0), ((0,), 1 / 3.0)] + [((0,), 1 / 3.0)] * 6 + \
                  [((0,), 1 / 3.0)] * 3 + [((0,), 2 / 3.0), ((0,), 1 / 3.0)] + [((0,), 1.0)] * 2
        elif phrase == "drone":
            seq = [((0,), 16.0)]
        elif phrase == "menu":
            # a menu's keys, one after another: each its own drum
            seq = [((d,), 0.5) for d in range(16)]
        elif phrase == "reel":
            # two bars of a reel in D, in quavers, ending on the long D
            seq = [((d,), 0.5) for d in (0, 2, 4, 7, 9, 7, 4, 7, 12, 9, 7, 4, 2, 0, 2, 4,
                                         7, 4, 7, 9, 12, 14, 12, 9, 7, 9, 7, 4)] + [((0,), 2.0)]
        else:
            seq = STABS
        for notes, length in seq:
            dur = length * (1.0 if phrase == "reel" else 0.9 if phrase not in ("stabs", "trance", "jig", "menu") else 0.45)
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
        n = {"riff": 8, "line": 8, "chords": 8, "stabs": 6, "trance": 16, "jig": 8, "drone": 16, "reel": 16, "menu": 8}[phrase]
        print("  %5.1f s  %s (SC-8850 %d.%d)" % (t * 60.0 / TEMPO, name, prog, lsb))
        t += n + 1.5
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
