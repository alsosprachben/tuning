#!/usr/bin/env python3
"""Level the GS sets' class voices (percussion_gs: 'c' specs) to the kit around
them: each key's loudest 150 ms at velocity 100, its trim (percussion_gs.LEVEL,
percussion_map.KIT_LEVEL's sense: an amplitude) set to hit its kind's target.

    gs_levels.py            each voice, its level and the trim it would take
    gs_levels.py --write    ...into percussion_gs.LEVEL

WHY: the throat voices (the Hoo, the Rhythm FX voices, the kakegoe) took the
SFX set's Kitty's gain and no trim -- 35-40 dB under the snare beside them,
fine in a demo normalised to itself and lost in a song -- and the Rhythm FX
synth effects sat 10-15 dB under the kit. Standard's snare and crash read
-31.5 dB here; the targets:

    drum   -32 dB   a drum, a wood, a clap
    gong   -28 dB   a gong (the Asian Gong's tam-tam reads -29.7)
    cymbal -30 dB
    voice  -34 dB   a voice or an effect

A voice within 3 dB of its target is left as it is.
"""
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

TARGET = {"drum": -32.0, "gong": -28.0, "cymbal": -30.0, "voice": -34.0}
KIND = {
    # the throat voices
    'High Hoo': 'voice', 'Low Hoo': 'voice', 'Hoo': 'voice', 'Yyoo Dude': 'voice',
    'Reverse Yyoo Dude': 'voice', 'Voice One': 'voice', 'Reverse Voice One': 'voice', 'Voice Two': 'voice',
    'Reverse Voice Two': 'voice', 'Voice Three': 'voice', 'Reverse Voice Three': 'voice', 'Voice Tah': 'voice',
    'Reverse Voice Tah': 'voice', 'Voice Ou': 'voice', 'Voice Au': 'voice', 'Voice Whey': 'voice',
    'Frog Voice': 'voice', 'Douby': 'voice', 'Reverse Douby': 'voice', 'Baert High': 'voice', 'Baert Low': 'voice',
    # the Asia set's dholak
    'Dholak 1': 'drum', 'Dholak 2': 'drum',
    # the Rhythm FX sets' effects
    'Techno Thip': 'voice', 'Pop Drop': 'voice', 'Syn. Drops': 'voice', 'Pipe': 'drum', 'Distortion Kick': 'drum',
    'Sub Marine': 'voice', 'Noise Attack': 'voice', 'Bounce': 'voice', 'Reverse Bounce': 'voice',
    'Distortion Knock': 'drum', 'Swish': 'voice', 'Velocity Noise FX': 'voice', 'Spark': 'voice',
    'Missile': 'voice', 'Space Birds': 'voice', 'Space Worms': 'voice', 'Tape Stop 1': 'voice',
    'Tape Stop 2': 'voice', 'Emergency !': 'voice', 'Calculating...': 'voice', 'Saw LFO Saw': 'voice',
    'Woody Slap': 'drum', 'Ice Block': 'drum', 'Metallic Percussion': 'drum', 'Modulated Bell': 'voice',
    'Alias': 'voice', 'Stereo Noise Clap': 'drum', 'Flying Monster': 'voice',
    # the Asia set's
    'Shou Luo': 'gong', 'Bend Gong': 'gong', 'Hu Yin Luo Low': 'gong', 'Hu Yin Luo Mid': 'gong',
    'Hu Yin Luo Mid 2': 'gong', 'Hu Yin Luo High': 'gong', 'Hu Yin Luo High 2': 'gong', 'Nao Bo': 'cymbal',
    'Xiao Bo': 'cymbal', 'Ban Gu': 'drum', 'Pai Ban': 'drum', 'Tang Gu': 'drum', 'Tang Gu Mute': 'drum',
    'Ohkawa': 'drum', 'High Kotsuzumi': 'drum', 'Low Kotsuzumi': 'drum', 'Wadaiko Rim': 'drum',
    'Small Taiko': 'drum', 'Shimedaiko': 'drum',
    'Buk': 'drum', 'Buk Rim': 'drum', 'Gengari p': 'gong', 'Gengari f': 'gong', 'Gengari Mute Low': 'drum',
    'Gengari Mute High': 'drum', 'Gengari Samll': 'gong', 'Jang-Gu Che': 'drum', 'Jang-Gu Kun': 'drum',
    'Jang-Gu Rim': 'drum', 'Jing p': 'gong', 'Jing f': 'gong', 'Jing Mute': 'gong',
    'MC-500 Beep 1': 'voice', 'MC-500 Beep 2': 'voice', 'Guitar Wah': 'voice', 'Guitar Slap': 'drum',
    'Chord Stroke Down': 'voice', 'Chord Stroke Up': 'voice', 'Biwa FX': 'voice', 'Phonograph Noise': 'voice',
    'Tape Rewind': 'voice', 'Bass Slide': 'voice', 'Pick Scrape': 'voice', 'Bird 2': 'voice',
    'Telephone 1': 'voice', 'Telephone 2': 'voice', 'Small Club 2': 'voice', 'Applause Wave': 'voice',
    'Eruption': 'voice', 'Big Shot': 'drum', 'Percussion Bang': 'drum', 'Small Club 1': 'voice',
    'LoFi Snare 1': 'drum', 'LoFi Snare 2': 'drum', 'LoFi Snare Rim': 'drum', 'Hip-Hop Claps': 'drum',
    'HipHop Snare 1': 'drum', 'HipHop Snare 2': 'drum', 'R&B Claps': 'drum', 'Jungle Snare': 'drum',
    'Jungle Snare Rim': 'drum', 'Jungle Crash': 'cymbal', 'Jungle Shaker': 'drum', 'Jungle Kick Roll': 'drum',
    'Jungle Snare Roll': 'drum', 'Techno Snare': 'drum', 'Rock Snare Dry': 'drum', 'TR-909 Claps': 'drum',
    'Fat Kick': 'drum', 'Comp Claps 2': 'drum',
    # the older break and techno voices (their sets' own, levelled too: Ben)
    'Hip-Hop Kick 1': 'drum', 'Hip-Hop Kick 2': 'drum', 'Rap Snare': 'drum', 'Hip-Hop Snare 2': 'drum',
    'Jungle Kick 1': 'drum', 'Jungle Kick 2': 'drum', 'Jungle Snare 1': 'drum', 'Jungle Snare 2': 'drum',
    'Jungle Hi-Hat': 'cymbal', 'Techno Kick 1': 'drum', 'Techno Kick 2': 'drum', 'Techno Snare 1': 'drum',
    'Techno Snare 2': 'drum', 'TR-909 Comp Kick': 'drum', 'Techno TR-808 Kick': 'drum', 'Techno TR-606 Snare 2': 'drum',
    # the SC-8850's Room and Jazz sets' own
    'Room Kick 1': 'drum', 'Room Kick 2': 'drum', 'Room Snare 1': 'drum', 'Room Snare 2': 'drum', 'Room Closed Hi-Hat 3': 'cymbal', 'Room Open Hi-Hat 3': 'cymbal',
    'Room Crash Cymbal': 'cymbal', 'Room Ride Cymbal': 'cymbal', 'Room Ride Bell': 'cymbal',
    'Jazz Low Tom 1': 'drum', 'Jazz Mid Tom 1': 'drum', 'Jazz Crash Cymbal': 'cymbal', 'Jazz Ride Cymbal': 'cymbal',
    'Jazz Ride Bell': 'cymbal',
    # the Gamelan sets': its drums, its bronze (each pitched instrument by its
    # middle key: FAMILY), its gongs and cymbals
    'Kendang Wadon': 'drum', 'Kendang Lanang': 'drum', 'Bebarongan': 'drum', 'Pelegongan': 'drum',
    'Kelontuk': 'drum', 'Kelontuk Mute': 'drum', 'Kelontuk Side': 'drum', 'Gamelan Gong Wadon': 'gong',
    'Gamelan Gong Lanang': 'gong', 'Kempur': 'gong', 'Kajar': 'drum', 'Ceng-Ceng': 'cymbal',
    'Kopyak Open': 'cymbal', 'Kopyak Mute': 'cymbal', 'Jegogan 3': 'drum', 'Jublag 3': 'drum',
    'Penyacah 4': 'drum', 'Pemade 5': 'drum', 'Reyong 6': 'drum',
    'Jingle Bell': 'cymbal', 'Req Dum': 'drum', 'Req Tik': 'drum', 'Bendir': 'drum', 'Udo Short': 'drum',
    'Udo Long': 'drum', 'Udo Slap': 'drum', 'Talking Drum': 'drum', 'Bend Talking Drum': 'drum',
    'Djembe': 'drum', 'Djembe Rim': 'drum', 'Conga Slide': 'drum', 'Open Pandiero': 'drum',
    'Mute Pandiero': 'drum', 'Tamborim': 'drum',
    'Tabla Te': 'drum', 'Tabla Na': 'drum', 'Tabla Tun': 'drum', 'Tabla Ge': 'drum', 'Tabla Ge Hi': 'drum',
    'Rama Cymbal Low': 'cymbal', 'Rama Cymbal High': 'cymbal', 'Sagat Open': 'cymbal', 'Sagat Closed': 'cymbal',
    **{'Gamelan Gong %d' % (i + 1): 'gong' for i in range(10)},
    **{'Gender %d' % (i + 1): 'drum' for i in range(5)},
    **{'Bonang %d' % (i + 1): 'drum' for i in range(5)},
}
# ...and a soft stroke's kind 6 dB under its loud one's
SOFT = {'Gengari p': 6.0, 'Jing p': 6.0}
# ONE TRIM FOR AN INSTRUMENT'S KEYS: a gamelan instrument levelled by its
# middle key, the trim given to every key of it, in both sets
FAMILY = {'%s %d' % (inst, mid): ['%s %d%s' % (inst, n, et) for n in range(1, count + 1) for et in ('', ' ET')]
          for inst, mid, count in (('Jegogan', 3, 5), ('Jublag', 3, 5), ('Penyacah', 4, 7), ('Pemade', 5, 10),
                                   ('Reyong', 6, 12))}
FAMILY.update({n: [n, n + ' ET'] for n in ('Gamelan Gong Wadon', 'Gamelan Gong Lanang', 'Kempur', 'Kajar')})


# THE SAME DRUM ELSEWHERE: a voice that is Standard's in another room (the
# Room set's) or the same drum from another kit (the Jazz set's) sits where
# Standard's does -- by kind, the closed hat would be the open's level, and
# the live room's reflections lift a drum's loudest 150 ms 8-12 dB
MATCH = {'Room Kick 1': 36, 'Room Kick 2': 35, 'Room Snare 1': 38, 'Room Snare 2': 40, 'Room Closed Hi-Hat 3': 42, 'Room Open Hi-Hat 3': 46,
         'Room Crash Cymbal': 49, 'Room Ride Cymbal': 51, 'Room Ride Bell': 53,
         'Jazz Low Tom 1': 43, 'Jazz Mid Tom 1': 47, 'Jazz Crash Cymbal': 49, 'Jazz Ride Cymbal': 51,
         'Jazz Ride Bell': 53}


def level_of(kit, key):
    import mido
    import blockrender as B
    import percussion_map as P
    P._RING_CLASSES.clear()
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    if kit >= 128:      # a map's own set (128 x map + program): its CC32
        t.append(mido.Message("control_change", channel=9, control=32, value=kit // 128, time=0))
    t.append(mido.Message("program_change", channel=9, program=kit % 128, time=0))
    t.append(mido.Message("note_on", channel=9, note=key, velocity=100, time=240))
    t.append(mido.Message("note_off", channel=9, note=key, velocity=0, time=240))
    t.append(mido.MetaMessage("end_of_track", time=1920 * 2))
    L, R = B.render(m)[:2]
    y = np.asarray(L, np.float64)
    c = np.concatenate(([0.0], np.cumsum(y * y)))
    n = int(0.15 * B.SR)
    return 10 * np.log10((c[n:] - c[:-n]).max() / n + 1e-30)


def where(name):
    """(kit, key) of a set that plays NAME as a class voice."""
    import percussion_gs as G
    import percussion_map as P
    for which, keys in G.SETS.items():
        for key, nm in keys.items():
            # ...where it still plays (a later set -- the SC-8850's over a
            # native one -- can have put another voice on that key)
            if nm == name and P.KITS.get(G.SET_KIT[which], {}).get(key, ("",))[0] == name:
                return G.SET_KIT[which], key
    return None


def main(argv):
    import percussion_gs as G
    trims = {}
    for name, kind in KIND.items():
        spec = G.VOICE.get(name)
        if not spec or spec[0] != 'c':
            continue
        wk = where(name)
        if wk is None:
            continue
        lv = level_of(*wk)
        target = level_of(0, MATCH[name]) if name in MATCH else TARGET[kind] - SOFT.get(name, 0.0)
        d = target - lv
        cur = G.LEVEL.get(name, 1.0)
        new = round(cur * 10 ** (d / 20.0), 4) if abs(d) > 3.0 else cur
        print("  %-20s %-6s %6.1f dB  (target %.1f)  trim %s -> %s" % (name, kind, lv, target, cur, new))
        if new != cur:
            for n in FAMILY.get(name, [name]):
                trims[n] = new
    if "--write" in argv and trims:
        p = os.path.join(HERE, "percussion_gs.py")
        s = open(p).read()
        block = "LEVEL.update(%r)" % (trims,)
        marker = "# THE CLASS VOICES LEVELLED to the kit (examples/gs_levels.py)\n"
        if marker in s:
            s = re.sub(re.escape(marker) + r"LEVEL\.update\(\{.*?\}\)", lambda _: marker + "LEVEL.update(%r)" % (
                {**eval(re.search(re.escape(marker) + r"LEVEL\.update\((\{.*?\})\)", s, re.S).group(1)),
                 **trims},), s, flags=re.S)
        else:
            i = s.index("\n# A SOUND OF TWO VOICES")
            s = s[:i] + "\n" + marker + block + "\n" + s[i:]
        open(p, "w").write(s)
        print("  wrote %d trims" % len(trims))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
