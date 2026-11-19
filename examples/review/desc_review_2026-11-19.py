# THE PROGRAM SUMMARIES REVIEWED (Ben, 2026-11-19): no repeat of the GM or GS
# name beside them, and each checked against its coverage note -- applied to
# variation_desc.py in place (run once; kept as the record of what changed)
import re, sys
f = 'variation_desc.py'; t = open(f).read()
CAP = {
 0: "Steinway B (VCSL)", 1: "an upright (VSCO 2), measured", 3: "the upright, unisons 8-20 c apart",
 4: "Fender Rhodes Mark I (1977)", 5: "Wurlitzer 200A: reed in a slot", 6: "English and Flemish (VCSL), 8'",
 8: "felt on steel plates", 9: "steel bars (Iowa)", 10: "a plucked steel comb", 11: "aluminium bars; the wheel its motor",
 12: "rosewood bars, dark (Iowa)", 13: "rosewood bars, bright (Iowa)", 14: "brass tubes, struck",
 15: "Kemp's 17/16 hammered dulcimer", 20: "harmonium: an 8' and a sharp 4'", 21: "Hohner on musette: wet reeds",
 22: "Hohner, cupped hands", 23: "1930 ELA bandoneon: octave reeds", 24: "classical guitar (Iowa)",
 25: "flat-top (GuitarSet), on a mic", 26: "Ibanez RG2820, neck humbucker", 27: "Stratocaster neck pickup, clean",
 28: "Ibanez, the mute measured", 29: "Ibanez bridge humbucker, crunch", 30: "Ibanez RG2820, bridge humbucker",
 31: "touched at a node (IDMT)", 32: "double bass, pizzicato (Iowa)", 33: "Jazz Bass pickups (IDMT)",
 34: "Jazz Bass pickups, a pick", 35: "two fretless basses, measured", 36: "the thumb (IDMT)", 37: "the popped pluck (IDMT)",
 40: "a section (Iowa violin)", 41: "a section (Iowa viola)", 42: "a section (Iowa cello)", 43: "a section (Iowa double bass)",
 44: "the section's bow shaking, 11 Hz", 45: "four sections plucked (Iowa)", 46: "plucked mid-string (VSCO 2)",
 47: "five kettledrums (VSCO 2)", 48: "four sections by register", 49: "the section swelling in, slow bow",
 52: "VocalSet singers: open \"ah\"", 53: "VocalSet singers: rounded \"oo\"", 55: "the Fairlight-era stab",
 56: "Iowa trumpet", 57: "Iowa tenor and bass trombones", 58: "Iowa tuba", 59: "Harmon mute, measured (VSCO 2)",
 60: "Iowa horn", 61: "trumpets, trombones, tuba by register", 64: "Iowa soprano", 65: "Iowa alto",
 66: "the sax law, transposed", 67: "the sax law, transposed", 68: "Iowa oboe", 69: "the oboe's reed law",
 70: "Iowa bassoon", 71: "Iowa clarinets: Bb, Eb, bass", 72: "the flute law, measured", 73: "Iowa flute, no vibrato",
 74: "baroque recorders (VCSL)", 75: "closed pipes, breathy", 76: "air across a bottle's neck", 77: "breath and edge",
 78: "a human whistle: Helmholtz", 79: "vessel flute (VCSL)", 104: "jawari + sympathetic strings",
 105: "five strings on a head", 106: "silk strings, sawari buzz", 107: "Vietnamese đàn tranh (VCSL)",
 108: "plucked tines (VCSL)", 109: "chanter + drones", 110: "one violin, solo", 111: "conical double reed (zurna proxy)",
 113: "two cone bells (VSCO 2)", 114: "steel pan, from its design", 115: "Iowa woodblocks",
 116: "big barrel drum, sticks", 117: "floor and rack tom by register", 122: "ocean drum (VCSL)",
 123: "falling chirps (sparrows)", 125: "blade passes and wash", 126: "three audiences clapping",
 127: "9 mm at 15 m: an N-wave",
}
VAR = {
 (14, 8): "St. Kathrin's, Gelting: 19 modes", (24, 8): "Ben's Luna, concert size", (25, 8): "Magner's Fender: octave courses",
 (107, 8): "keyed zither (a soprano)", (115, 8): "Iowa castanets, by pitch", (116, 8): "the orchestra set's drum, by pitch",
 (117, 1): "Standard set's tom, by pitch", (117, 9): "Room set's tom, by pitch", (118, 8): "a real 808's mid tom, fitted",
 (118, 9): "Simmons tom (Electronic set)",
 (119, 1): "Standard's crash 2, backwards", (119, 8): "Standard's snare, backwards", (119, 9): "Standard's snare 2, backwards",
 (119, 16): "Standard's kick, backwards", (119, 17): "the orchestra set's BD, backwards",
 (119, 24): "Standard's low tom, backwards", (119, 25): "Standard's high tom, backwards",
 (120, 1): "a muted strum on steel strings", (120, 2): "a hand slapping upright strings",
 (121, 1): "a sax key struck, not blown",
 (122, 1): "a Freesound rain, fitted", (122, 2): "a strike: rumble under 250 Hz", (122, 3): "a howl at 1 kHz on a rumble",
 (122, 4): "a brook's hiss and trickle", (122, 5): "eleven a second (Freesound)",
 (123, 1): "a bark as a throat", (123, 2): "horseshoe clicks, galloping", (123, 3): "the SFX set's birds",
 (124, 2): "a hinge's stick-slip", (124, 3): "a wooden door slammed", (124, 5): "metal tubes struck",
 (125, 1): "an idling engine (Freesound)", (125, 2): "a handbrake skid", (125, 3): "tyres on a wet road",
 (125, 4): "a crash with glass", (125, 6): "a freight train", (125, 7): "a jet's roar",
 (125, 8): "no recording: GU's patch", (125, 9): "a hiss and low bursts",
 (126, 1): "\"ho ho ho\"", (126, 2): "a girl's scream", (126, 3): "a fist on a body", (126, 4): "the ECG's waveform",
 (126, 5): "a hard shoe on stone", (126, 6): "the SFX set's applause",
 (127, 1): "the set's shot every 69 ms", (127, 2): "a square swept down", (127, 3): "a dynamite blast",
 (38, 9): "Moog: resonant, sliding", (38, 16): "Moog: the 101's resonant saw", (39, 17): "Moog: pulse + sub, as the 101",
 (39, 18): "Moog: resonant saw, as the 101", (50, 1): "Moog: wider pair, slower swell", (62, 1): "Moog: quicker blat, wider pair",
}
import variation_desc as V
def enc(s): return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
def oldenc(s): return [enc(s), '"' + s.replace('"', '\\"') + '"', "'" + s + "'"]
miss = []
def sub(key_pat, old, new):
    global t
    for o in oldenc(old) + [enc(old).encode('ascii','backslashreplace').decode()]:
        pat = re.compile(r'(^[ \t]*' + key_pat + r'\s*:\s*)' + re.escape(o) + r'(\s*,)', re.M)
        t2, n = pat.subn(lambda m: m.group(1) + enc(new) + m.group(2), t)
        if n == 1:
            t = t2; return True
    return False
for p, new in CAP.items():
    old = V.CAPITAL_DESC.get(p)
    if old is None:
        miss.append(('cap-not-in-CAPITAL_DESC', p, V.MODELLED.get(p))); continue
    if not sub(r'%d' % p, old, new): miss.append(('cap', p, old))
for (p, v), new in VAR.items():
    old = V.VARIATION_DESC[(p, v)]
    if not sub(r'\(%d,\s*%d\)' % (p, v), old, new): miss.append(('var', (p, v), old))
open(f, 'w').write(t)
print('missed', miss)
