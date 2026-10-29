#!/usr/bin/env python3
"""A synthesiser interface for live.py.

The engine is multi-timbral (see live.Part); this is the panel that drives it.
curses, from the standard library, because the repo has no UI dependency and
should not grow one for this.

TWO KINDS OF EDIT, and the difference is the whole design:

  - CHEAP edits -- channel, key range, transpose, level, mute, stops -- are a
    single attribute write on a live Part. They take effect on the next MIDI
    event, and they happen inline.

  - EXPENSIVE edits -- program, drums, tuner -- need a Patch, which is 0.02-0.67 s
    of pure-Python template building. Those go to the Builder thread, never to
    the audio thread and never to the input loop, and the panel shows a progress
    bar while they run.

Nothing here touches tonelib.py. A voice is defined in one place, in code, and a
preset is data that arranges those voices -- so a sound that only exists because
the TUI is running is not a sound this project claims to have.
"""
import curses, locale, threading, collections, time, os, sys

import numpy as np
import mido
import tonelib as T
import live as LV
import moog as MG
import mf104 as MFD
import percussion_map as PM
import gsefx as GSX
import patch_map as PMAP
from variation_desc import VARIATION_DESC, CAPITAL_DESC

locale.setlocale(locale.LC_ALL, "")

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(n):
    return "%s%d" % (NOTE_NAMES[n % 12], n // 12 - 1)


# GM program names, so the patch picker says "Trumpet" and not just "56". The
# engine routes by patch_map; this list is only what to call them.
GM = """Acoustic Grand,Bright Acoustic,Electric Grand,Honky-tonk,Electric Piano 1,
Electric Piano 2,Harpsichord,Clavi,Celesta,Glockenspiel,Music Box,Vibraphone,
Marimba,Xylophone,Tubular Bells,Dulcimer,Drawbar Organ,Percussive Organ,Rock Organ,
Church Organ,Reed Organ,Accordion,Harmonica,Tango Accordion,Acoustic Guitar (nylon),
Acoustic Guitar (steel),Electric Guitar (jazz),Electric Guitar (clean),
Electric Guitar (muted),Overdriven Guitar,Distortion Guitar,Guitar Harmonics,
Acoustic Bass,Electric Bass (finger),Electric Bass (pick),Fretless Bass,Slap Bass 1,
Slap Bass 2,Synth Bass 1,Synth Bass 2,Violin,Viola,Cello,Contrabass,Tremolo Strings,
Pizzicato Strings,Orchestral Harp,Timpani,String Ensemble 1,String Ensemble 2,
Synth Strings 1,Synth Strings 2,Choir Aahs,Voice Oohs,Synth Voice,Orchestra Hit,
Trumpet,Trombone,Tuba,Muted Trumpet,French Horn,Brass Section,Synth Brass 1,
Synth Brass 2,Soprano Sax,Alto Sax,Tenor Sax,Baritone Sax,Oboe,English Horn,
Bassoon,Clarinet,Piccolo,Flute,Recorder,Pan Flute,Blown Bottle,Shakuhachi,Whistle,
Ocarina,Lead 1 (square),Lead 2 (sawtooth),Lead 3 (calliope),Lead 4 (chiff),
Lead 5 (charang),Lead 6 (voice),Lead 7 (fifths),Lead 8 (bass+lead),Pad 1 (new age),
Pad 2 (warm),Pad 3 (polysynth),Pad 4 (choir),Pad 5 (bowed),Pad 6 (metallic),
Pad 7 (halo),Pad 8 (sweep),FX 1 (rain),FX 2 (soundtrack),FX 3 (crystal),
FX 4 (atmosphere),FX 5 (brightness),FX 6 (goblins),FX 7 (echoes),FX 8 (sci-fi),
Sitar,Banjo,Shamisen,Koto,Kalimba,Bag pipe,Fiddle,Shanai,Tinkle Bell,Agogo,
Steel Drums,Woodblock,Taiko Drum,Melodic Tom,Synth Drum,Reverse Cymbal,
Guitar Fret Noise,Breath Noise,Seashore,Bird Tweet,Telephone Ring,Helicopter,
Applause,Gunshot""".replace("\n", "").split(",")

# ...AND WHAT A VOICE IS MODELLED ON, where that is one instrument a word can
# name (examples/gm_coverage.py has the measurements): shown in parentheses
# after the GM name -- "Electric Piano 1 (Rhodes)". Display only; GM itself
# stays the GM names (voice_ab.py makes file names of them).
MODELLED = {0: "Steinway", 2: "CP-70", 4: "Rhodes", 5: "Wurlitzer", 7: "Clavinet",
            16: "Hammond", 17: "Hammond", 18: "Hammond", 19: "Gr\u00f6nlund",
            26: "Ibanez", 27: "Stratocaster", 28: "Ibanez", 29: "Ibanez", 30: "Ibanez",
            80: "Moog", 81: "Moog", 107: "\u0110\u00e0n Tranh"}


def gm_label(p, v=0):
    if p >= len(GM):
        return "?"
    if v and (p, v) in PMAP.VARIATION_NAMES:
        # GS's own name for the variation -- and a map's own tone says whose
        nm = PMAP.VARIATION_NAMES[(p, v)]
        return nm + (" (%s)" % PMAP.MAP_LABELS[v >> 7] if v >> 7 in PMAP.MAP_LABELS else "")
    return GM[p] + (" (%s)" % MODELLED[p] if p in MODELLED else "")


def built_variations(p):
    """The GS variations under program p that are built (patch_map.VARIATIONS),
    in bank order: the ones a picker offers. Only GS's own (VARIATION_NAMES) --
    not a voice's internal bank (107.9, the taishogoto's drone string) -- and
    not bank 127, the MT-32 set: another instrument's tones on the same
    numbers, which the picker lists as a section of its own (mt32_tones)."""
    return sorted(v for (q, v) in PMAP.VARIATIONS
                  if q == p and v < 127 and (q, v) in PMAP.VARIATION_NAMES)


def map_tones():
    """{map: [(program, variation key)]}: each Sound Canvas map's OWN tones
    (patch_map.map_bank's 128 x map + bank), where it holds another tone
    than ours under a number. The picker lists them by map."""
    out = {}
    for (q, v) in sorted(PMAP.VARIATIONS):
        if v >> 7 in PMAP.MAP_LABELS and (q, v) in PMAP.VARIATION_NAMES:
            out.setdefault(v >> 7, []).append((q, v))
    return out


def mt32_tones():
    """[(program, MT-32 tone, what it plays)] of bank 127 (patch_map.MT32_SET)."""
    out = []
    for i, (nm, to) in enumerate(getattr(PMAP, "MT32_SET", ())):
        plays = ("kit key %d" % to[1]) if isinstance(to, tuple) else gm_label(to)
        out.append((i, nm, plays))
    return out


# THE PATCH PICKER AS A TREE (Ben: "a GM mode, an MT-32 mode, a Sound Canvas
# mode -- which version by level number and model"): a standard, then (for
# a Sound Canvas) its level, then the sixteen GM families, the programs, and
# the tones under each. A part keeps its standard (Part.std), so the picker
# opens where it is and the program keys step within it.
FAMILIES = ("Piano", "Chromatic Percussion", "Organ", "Guitar", "Bass", "Strings",
            "Ensemble", "Brass", "Reed", "Pipe", "Synth Lead", "Synth Pad",
            "Synth Effects", "Ethnic", "Percussive", "Sound Effects")
# a Sound Canvas level is its map (bank select LSB, patch_map.MAP_LABELS)
SC_LEVELS = {1: "SC-55 / SC-55mkII", 2: "SC-88", 3: "SC-88Pro", 4: "SC-8850"}


def sc_tone(p, b, m):
    """(variation key, what it plays) for tone p.b on the level-m Sound Canvas:
    the key a file's CC0 b / CC32 m selects (patch_map.map_bank), and None
    where we play that very tone -- else the voice it falls back to (the
    capital, as a Sound Canvas plays a number it has no tone at)."""
    k = PMAP.map_bank(p, b, m) if b else 0
    if b and (k == 0 or (p, k) not in PMAP.VARIATIONS):
        return 0, "plays %s" % gm_label(p)
    return k, None


def patch_tree():
    """The picker's tree: nodes dict(label, kids), leaves dict(label, pick),
    pick = (drums, program, variation key, standard)."""
    def row(i, b, name, note):
        return "%3d%-5s %-16s %s" % (i, (".%d" % b) if b else "", name, note or "")

    def families(std, leaves_of):
        return [dict(label="%-20s %3d-%d" % (f, 8 * k, 8 * k + 7),
                     kids=[dict(label=row(i, 0, GM[i], None), kids=leaves_of(i))
                           if len(leaves_of(i)) > 1 else leaves_of(i)[0]
                           for i in range(8 * k, 8 * k + 8)])
                for k, f in enumerate(FAMILIES)]

    def gm(i):
        return [dict(label=row(i, 0, GM[i], CAPITAL_DESC.get(i) or
                               (MODELLED[i] if i in MODELLED else None)),
                     pick=(False, i, 0, "gm"))]

    def sc(m):
        def leaves(i):
            out = [dict(label=row(i, 0, GM[i], CAPITAL_DESC.get(i)), pick=(False, i, 0, "sc%d" % m))]
            for b in sorted(b for (q, b) in PMAP.MAP_NAMES[m] if q == i):
                k, falls = sc_tone(i, b, m)
                d = VARIATION_DESC.get((i, k)) if k else None
                out.append(dict(label=row(i, b, PMAP.MAP_NAMES[m][(i, b)], falls or d),
                                pick=(False, i, k, "sc%d" % m)))
            return out
        return leaves

    tones = mt32_tones()
    mt = [dict(label="%3d-%-3d %s ..." % (8 * k, 8 * k + 7, tones[8 * k][1]),
               kids=[dict(label=row(i, 127, nm, "(plays %s)" % plays), pick=(False, i, 127, "mt32"))
                     for i, nm, plays in tones[8 * k:8 * k + 8]])
          for k in range(len(tones) // 8)]
    # (a map's own copy of a set -- the SC-88 Pro's, kept before the SC-8850
    # revised it -- is the set's number in that standard: kit_in_map picks it)
    kits = [dict(label="%3d %s" % (k, PM.drum_set_name(k)), pick=(True, k, 0, None))
            for k in sorted(PM.DRUM_SETS) if k < 128 or k == PM.SC88_TR808_909]
    return dict(label="patch", kids=[
        dict(label="General MIDI          128 programs", crumb="GM", kids=families("gm", gm)),
        dict(label="Sound Canvas          by level and model", crumb="Sound Canvas",
             kids=[dict(label="Level %d  %-18s (map %d)" % (m, SC_LEVELS[m], m),
                        crumb="Level %d %s" % (m, SC_LEVELS[m]),
                        kids=families("sc%d" % m, sc(m))) for m in sorted(SC_LEVELS)]),
        dict(label="MT-32 / CM-32L        its 128 tones (bank 127)", crumb="MT-32", kids=mt),
        dict(label="Drum kits             %d sets" % len(kits), crumb="Drum kits", kids=kits)])


def tree_leaves(node, path=(), up=()):
    """[(path of kid indices, the nodes above, leaf)] under node, in order."""
    out = []
    for j, k in enumerate(node.get("kids", ())):
        if "kids" in k:
            out += tree_leaves(k, path + (j,), up + (k,))
        else:
            out.append((path + (j,), up, k))
    return out


def leaf_crumb(up, leaf):
    """A leaf as a search lists it: its standard and level, then its row."""
    return " \u203a ".join([n["crumb"] for n in up if n.get("crumb")] + [leaf["label"].strip()])


def gm_label_short(p, width, v=0):
    """gm_label within a column: past it, the GM name's own qualifier goes
    and Electric/Acoustic shorten -- "E. Guitar (Stratocaster)" -- so the
    model still shows; the picker has the whole name."""
    s = gm_label(p, v)
    if len(s) <= width or v or p not in MODELLED:
        return s
    base = GM[p].split(" (")[0].replace("Electric ", "E. ").replace("Acoustic ", "A. ")
    return "%s (%s)" % (base, MODELLED[p])

# Every tuner in midilib.tuner_registry. This list was hand-kept and had drifted
# four entries short of the registry -- hybrid440, the general default, among
# them -- so it is now the registry, in the order the picker wants.
TUNERS = ["hybrid440", "hybrid", "hybridharm", "hybridharm440", "hybridmean", "hybridmeanpiano", "stretchedhelmholtz", "gm2", "even",
          "stretch", "werckmeister", "sankey", "meantone", "just", "pyth",
          "well", "linear", "linear5", "linearwell", "bechstein", "spiral",
          "semi", "dynamic", "path",
          # INDIAN INTONATION (ragas.py), Sa on C#: a part's own tuner, so the
          # sitar's part picks one while the rest keep theirs
          "raga:et@c#", "raga:just5@c#", "raga:pythagorean@c#", "raga:bel_todi/todi@c#"]

# One line each, so the picker says what a temperament is for rather than only
# what it is called. These are the working notes from midilib/tunelib, not a
# claim about historical practice.
TUNER_NOTE = {
    "hybrid440":  "A=440, the default: the hybrid temperament at concert pitch",
    "hybrid":     "A=415, the same temperament at baroque pitch",
    "hybridharm": "pure 2:1 octaves -- right for mode-locked pipes",
    "hybridharm440": "pure 2:1 octaves at concert pitch",
    "hybridmean": "the hybrid's chains bridged by a mean third: no wolf, pure octaves",
    "hybridmeanpiano": "hybridmean on a Steinway's stretched octaves, A=440",
    "stretchedhelmholtz": "two pure-fifth chains joined by inharmonic octaves, A=440",
    "gm2":        "a GM 2 device: equal A=440, and the FILE owns the tuning (MTS)",
    "werckmeister": "Werckmeister III, from Sankey's published cents, A=415",
    "sankey":     "Sankey's consonance-found Scarlatti tuning, A=415",
    "even":       "equal temperament, A=440",
    "stretch":    "pure fifths, the comma taken into stretched octaves, A=415",
    "meantone":   "quarter-comma, A=415",
    "just":       "pure ratios from the tonic",
    "pyth":       "pure fifths",
    "well":       "a circulating well temperament",
    "linear":     "linear in cents",
    "linear5":    "linear over five fifths",
    "linearwell": "linear well temperament",
    "bechstein":  "measured from a Bechstein",
    "spiral":     "the spiral of fifths, unclosed",
    "semi":       "semitone-based",
    "dynamic":    "solved once over the keyboard (only midi.py retunes per chord)",
    "path":       "follows a written path of notes",
    "raga:et@c#":          "Indian, Sa C#: equal (Serra 2011: sung Hindustani sits nearest it)",
    "raga:just5@c#":       "Indian, Sa C#: 5-limit just (theory)",
    "raga:pythagorean@c#": "Indian, Sa C#: Pythagorean (theory)",
    "raga:bel_todi/todi@c#": "Indian, Sa C#: Todi as Bel measured it, near Pythagorean",
}


def parse_note(s):
    """A note name or a MIDI number: \"C3\", \"F#4\", \"Bb2\" and \"48\" all read."""
    s = s.strip()
    if not s:
        raise ValueError(s)
    try:
        return int(s, 10)
    except ValueError:
        pass
    t = s[0].upper()
    if t not in "ABCDEFG":
        raise ValueError(s)
    i = 1
    step = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[t]
    while i < len(s) and s[i] in "#b\u266f\u266d":
        step += 1 if s[i] in "#\u266f" else -1
        i += 1
    octave = int(s[i:], 10)
    n = (octave + 1) * 12 + step
    if not 0 <= n <= 127:
        raise ValueError(s)
    return n


class Builder(threading.Thread):
    """One thread, so builds are serialised.

    blockrender.prepare() reseeds the global RNG, so two concurrent builds would
    race on it -- and two builds at once would be twice the GIL pressure on the
    audio callback for no gain.
    """
    daemon = True

    def __init__(self):
        threading.Thread.__init__(self)
        self.q = collections.deque()
        self.cv = threading.Condition()
        self.label = None       # what is building, for the panel
        self.frac = 0.0
        self.error = None
        self.stop = False

    def submit(self, label, fn):
        with self.cv:
            self.q.append((label, fn))
            self.cv.notify()

    def busy(self):
        return self.label is not None or bool(self.q)

    def progress(self, patch, frac):
        self.frac = frac

    def run(self):
        while not self.stop:
            with self.cv:
                while not self.q and not self.stop:
                    self.cv.wait(0.2)
                if self.stop:
                    return
                label, fn = self.q.popleft()
            # (a new job clears the last one's failure: it is old news, and
            # the panel's line is for what is happening now)
            self.label, self.frac, self.error = label, 0.0, None
            try:
                fn(self.progress)
            except Exception as e:
                self.error = "%s: %s" % (type(e).__name__, e)
            finally:
                self.label = None


# ---- the editable model -----------------------------------------------------
#
# A row is one Part. The columns are what you can change about it, and the same
# two keys (- and +) change every one of them, so there are no per-field modes to
# remember. PATCH and TUNER are the only columns that cost a build.

COLS = ("patch", "ch", "lo", "hi", "tr", "level", "tuner", "touch", "stops", "efx")
COL_W = {"patch": 33, "ch": 4, "lo": 5, "hi": 5, "tr": 4, "level": 8,
         "tuner": 11, "touch": 6, "stops": 11, "efx": 5}

# Which columns open a picker on enter, and which take a typed value. Every
# column answers enter with something -- it used to always open the patch
# picker, whatever was highlighted.
PICKERS = ("patch", "tuner", "stops")

# How far a part's level column can be pushed, in dB. The floor is effectively
# a mute; the ceiling used to be +12 and is +24 because balancing a rig against
# a loud voice needs the range -- an amplified guitar next to a quiet patch can
# want more than four times the gain.
#
# ABOVE UNITY IS NOT FREE, and the master column's note explains why:
# synth_window applies T.master_gain and hard-clips to +/-1 BEFORE Live.limit
# sees the block, so gain that overflows there clips inside the kernel where
# the soft limiter cannot help it. Use the headroom column with this one.
LEVEL_DB_MIN = -60.0
LEVEL_DB_MAX = 24.0

GLOBALS = (
    ("master",     "dB",   -60.0,  0.0, 0.5),
    ("headroom",   "dB",     0.0, 24.0, 0.5),
    ("limiter",    "",       0.10, 1.00, 0.02),
    ("bend range", "st",     0.0, 24.0, 0.5),
    ("mod depth",  "cents",  0.0, 200.0, 5.0),
    ("mod rate",   "%",      0.0,  1.5, 0.05),
    ("aftertouch", "dB",     0.0, 24.0, 0.5),
    # "at tilt" USED TO BE HERE and set a global aftertouch tilt. Aftertouch now
    # colours only voices with a measured effort law, each by its own amount
    # (Live._press_tilt), so that knob moved nothing -- a control that does
    # nothing is worse than no control.
    ("threads",    "x",      1.0,  8.0, 1.0),
    # THE ROOM: a building, not a reverb knob -- the early reflections every
    # template is built with AND the tail convolved onto the mix, both from the
    # same room. Stepping it re-builds the patches off the audio thread (the
    # sounding notes keep the old room) and crossfades the tail.
    ("room",       "room",   0.0,  float(len(LV.ROOM_NAMES) - 1), 1.0),
    # THE GPU: the samples rendered on it (gpurender.py), the CPU taking the
    # light blocks. Swapped like the threads, while notes sound.
    ("gpu",        "onoff",  0.0,  1.0, 1.0),
    # THE METRONOME (Live.set_metronome): Standard's click on every beat, its
    # bell every `ring` beats (0: none) -- struck on the audio thread at each
    # beat's own sample, from a drum part of its own the keyboard never plays.
    # 0 bpm is off; it steps from off straight to 20.
    ("metronome",  "bpm",    0.0, 300.0, 1.0),
    ("ring",       "ring",   0.0, 16.0, 1.0),
    ("metro level", "dB",  -40.0, 12.0, 0.5),
    # THE STANDARD: the Sound Canvas map a part's map 0 plays (Live.std_map;
    # --map) -- the banks a program change reads, the drum sets, and where the
    # patch picker opens. A file's CC32 or TONE MAP messages still pick per part
    ("standard",   "std",    0.0,  4.0, 1.0),
)
STD_NAMES = ("ours", "SC-55", "SC-88", "SC-88Pro", "SC-8850")

# THE KEYS A PANEL CONTROL MAY BE BOUND TO: everything the panel does not
# already use, in any pane, since a bound key fires from every pane. Space is
# the controls pane's own toggle, so it is not offered.
HOTKEYS_FREE = (set("cefginoptuvwxyz0[];',./")
                | (set("ABCDEFGHIJKMNOQRTUVWXYZ") - set("SLPNREX")))  # N/R: scenes; E: Eastern tuning; X: the EFX


# THE STOP KEYS: the digit row, and the same keys shifted. What shift+1 TYPES
# depends on the keyboard -- "!" on a US board, "!" on a UK one too but "@" is
# shift+' there, "!" on a German one but shift+2 is '"' -- and curses only ever
# sees the character. So the layout is read from the keymap itself: xkbcomp
# dumps the running X (or Xwayland) keymap, and each digit key's two levels are
# its two characters. Over ssh the keymap here is not the keyboard in front of
# the player, so that, and any failure, is a US board.
_US_SHIFTED = "!@#$%^&*("
_KEYSYM_CHARS = {
    "exclam": "!", "at": "@", "numbersign": "#", "dollar": "$", "percent": "%",
    "asciicircum": "^", "ampersand": "&", "asterisk": "*", "parenleft": "(",
    "parenright": ")", "quotedbl": '"', "apostrophe": "'", "grave": "`",
    "slash": "/", "equal": "=", "question": "?", "minus": "-", "underscore": "_",
    "plus": "+", "section": "\u00a7", "sterling": "\u00a3", "degree": "\u00b0",
    "eacute": "\u00e9", "egrave": "\u00e8", "ccedilla": "\u00e7",
    "agrave": "\u00e0", "currency": "\u00a4", "EuroSign": "\u20ac",
    "quoteleft": "`", "quoteright": "'", "less": "<", "greater": ">",
    "semicolon": ";", "colon": ":", "comma": ",", "period": ".",
    "bracketleft": "[", "bracketright": "]", "braceleft": "{", "braceright": "}",
    "backslash": "\\", "bar": "|", "asciitilde": "~",
}


def _keysym_char(name):
    if len(name) == 1:
        return name
    if len(name) == 5 and name[0] == "U":
        try:
            return chr(int(name[1:], 16))
        except ValueError:
            return None
    return _KEYSYM_CHARS.get(name)


def stop_keymap(dump=None):
    """{character: (row, index), ...} and {(row, index): label}: row 0 is the
    level that types the digit, row 1 the other one. `dump` is xkbcomp's
    output, for the selftest; None reads the running keymap."""
    import re
    import subprocess
    keys, labels = {}, {}
    for i in range(9):
        keys[str(i + 1)] = (0, i); labels[(0, i)] = str(i + 1)
        keys[_US_SHIFTED[i]] = (1, i); labels[(1, i)] = "\u21e7" + str(i + 1)
    if dump is None:
        if os.environ.get("SSH_CONNECTION") or not (os.environ.get("DISPLAY")
                                                    or os.environ.get("WAYLAND_DISPLAY")):
            return keys, labels, "us (assumed)"
        try:
            dump = subprocess.run(["xkbcomp", "-xkb", os.environ.get("DISPLAY", ":0"), "-"],
                                  capture_output=True, text=True, timeout=2).stdout
        except Exception:
            return keys, labels, "us (assumed)"
    got = {}
    for m in re.finditer(r"key <AE0([1-9])>\s*{[^\[]*\[\s*([^,\]]+?)\s*,\s*([^,\]]+?)\s*[,\]]", dump):
        got[int(m.group(1)) - 1] = (_keysym_char(m.group(2)), _keysym_char(m.group(3)))
    if len(got) != 9:
        return keys, labels, "us (assumed)"
    keys, labels = {}, {}
    for i in range(9):
        d = str(i + 1)
        lv0, lv1 = got[i]
        if lv1 == d and lv0:                 # AZERTY: the digit is the SHIFTED level
            keys[d] = (0, i); labels[(0, i)] = "\u21e7" + d
            keys[lv0] = (1, i); labels[(1, i)] = lv0
        else:
            keys[d] = (0, i); labels[(0, i)] = d
            if lv1:
                keys[lv1] = (1, i); labels[(1, i)] = "\u21e7" + d
    return keys, labels, "keymap"


STOP_KEYS, STOP_LABELS, STOP_KEYS_FROM = stop_keymap()
# THE KEY BEFORE A STOP KEY FOR THE THIRD AND FOURTH ROWS, as Alt is -- for a
# desktop whose window manager keeps Alt. Backtick: on no layout a digit-row
# level, so never a stop key itself.
STOP_PREFIX = "`"
# A panel control cannot be bound to a stop key -- nor to the synth pane's own
# keys (B layer, D defaults, F firmware, M Messenger, T send, 0 zero): a hotkey
# fires from every pane, ahead of the pane's own keys, and took them over.
SYNTH_PANE_KEYS = set("BDFMT0")
HOTKEYS_FREE = HOTKEYS_FREE - set(STOP_KEYS) - SYNTH_PANE_KEYS



class TUI:
    def __init__(self, live, port_name):
        self.live = live
        self.port_name = port_name
        self.builder = Builder(); self.builder.start()
        self.row = 0
        self.col = 0
        self.pane = 0           # 0 = parts, 1 = globals, 2 = controls, 3 = synth
        self.crow = 0           # selected row in the controls pane
        self.srow = 0           # selected knob on the synth panel
        self.slayer = 'a'       # which Messenger of a layered Moog it edits
        self.grow = 0           # selected global
        self.meter = 0.0
        self.message = ""
        self.msg_at = self.msg_until = 0.0
        self._err_seen = {}     # which error -> (its text, when it first showed)
        self.help = False
        self._colors = {}
        self._pairs = {}
        self.rich = False               # the 256-colour palette (init_theme)
        self._mlev = [0.0, 0.0]         # the stereo meter's fall
        self._mhold = [(0.0, 0.0), (0.0, 0.0)]   # its peak holds: (level, when)
        self._cpu_hist = collections.deque(maxlen=48)
        self._cpu_acc, self._cpu_n = 0.0, 0
        self._health = {}               # count -> (value, when it last rose)

    # ---- helpers ------------------------------------------------------------
    def say(self, msg, secs=3.0):
        self.message = msg
        self.msg_at = time.monotonic()
        self.msg_until = self.msg_at + secs

    def parts(self):
        return list(self.live.parts)

    def sel(self):
        ps = self.parts()
        if not ps:
            return None
        self.row = max(0, min(self.row, len(ps) - 1))
        return ps[self.row]

    def master_db(self):
        return 20.0 * float(np.log10(max(T.master_gain, 1e-12)))

    def get_global(self, i):
        L = self.live
        return (self.master_db(), L.headroom_db, L.thresh, L.bend_range,
                L.mod_cents, L.mod_rate, L.press_db,
                float(L.renderer.K),
                float(LV.ROOM_NAMES.index(L.room_name or "dry")),
                1.0 if isinstance(L.renderer, LV.GpuRenderer) else 0.0,
                float(L.metro_bpm), float(L.metro_ring), float(L.metro_level_db),
                float(L.std_map))[i]

    def set_global(self, i, v):
        L = self.live
        name, unit, lo, hi, step = GLOBALS[i]
        v = max(lo, min(hi, v))
        if i == 0:
            # Master is capped at unity ON PURPOSE. synth_window applies
            # T.master_gain and then hard-clips to +/-1, BEFORE Live.limit ever
            # sees the block -- so pushing past 0 dB clips inside the kernel
            # where the soft limiter cannot help.
            T.master_gain = 10.0 ** (v / 20.0)
        elif i == 1:
            L.headroom_db = v
            L.slab.headroom = 10.0 ** (-v / 20.0)
        elif i == 2:
            L.thresh = v
        elif i == 3:
            L.bend_range = v
        elif i == 4:
            L.mod_cents = v
        elif i == 5:
            L.mod_rate = v
        elif i == 6:
            L.press_db = v
        elif i == 8:
            name = LV.ROOM_NAMES[int(round(v))]
            if name != L.room_name:
                L.set_room(name)
                self.say("room: %s -- re-building the patches in it" % name)
        elif i == 10:
            # off and 20 bpm are neighbours: nothing slower is a metronome
            prev = L.metro_bpm
            if 0 < v < 20:
                v = 20.0 if prev < 20 else 0.0
            self.metronome(round(v), L.metro_ring)
        elif i == 11:
            self.metronome(L.metro_bpm, round(v))
        elif i == 12:
            L.set_metro_level(v)
        elif i == 13:
            L.std_map = int(round(v))
            L.dirty = True
            self.say("standard: %s -- program changes read its banks and drum sets; "
                     "the patch picker opens in it" % STD_NAMES[L.std_map])
        elif i == 9:
            on = v >= 0.5
            if on != isinstance(L.renderer, LV.GpuRenderer):
                new = LV.make_renderer(L.slab, L.frames, L.renderer.K, on)
                self.swap_renderer(new)
                if on and not isinstance(new, LV.GpuRenderer):
                    self.say("gpu: not available -- %s" % LV.GPU_ERROR)
        else:
            k = int(round(v))
            if k != L.renderer.K:
                self.swap_renderer(LV.make_renderer(L.slab, L.frames, k,
                                                    isinstance(L.renderer, LV.GpuRenderer)))

    def swap_renderer(self, new):
        """A new renderer (threads, gpu), made here -- a GPU context takes a
        while -- and SWAPPED BY THE AUDIO THREAD, between two blocks. It was
        swapped and the old one closed from here, while the callback could be
        inside the old one's render: it read live.renderer five times a block
        (two renderers in one block), and a worker told to stop mid-block
        returned without saying it was done -- the callback waiting on it for
        ever, the audio gone for good."""
        L = self.live

        def go(n0):
            old, L.renderer = L.renderer, new
            L.slab.dirty = True
            old.close()                  # no render of it is running: this is between blocks
        L.post(go)

    def metronome(self, bpm, ring):
        """Set the metronome. Its drum part is built the first time it is
        switched on -- off this thread and off the audio thread, by the builder
        that builds every patch -- and it starts once the part is ready."""
        L = self.live
        if bpm > 0 and L.metro_part is None:
            # one build, whatever is pressed while it runs: it starts on the
            # LATEST tempo and ring asked for
            self._metro_want = (bpm, ring)
            L.metro_ring = int(ring)
            if getattr(self, "_metro_building", False):
                return
            self._metro_building = True
            tuner = self.parts()[0].patch.tuner if self.parts() else "hybrid440"

            def job(progress):
                try:
                    part = L.build_metro_part(tuner, progress)
                    b, r = self._metro_want
                    L.set_metronome(b, r, part)
                finally:
                    self._metro_building = False
            self.builder.submit("metronome", job)
            self.say("metronome: building its click and bell")
        else:
            L.set_metronome(bpm, ring)

    # ---- edits that need a patch --------------------------------------------
    # WHAT A CHEAP EDIT WRITES straight onto a live Part (adjust, type_value,
    # mute, touch, M): carried onto the new parts when a rebuild lands, if it
    # was made while the rebuild was building
    CARRY = ("channel", "lo", "hi", "transpose", "level_db", "muted", "fixed_touch",
             "pan", "cc_map")

    def rebuild(self, label, edit):
        """Replace the whole part set, off-thread: `edit(specs)` -> the new
        specs (None: nothing to do), applied to the parts AS THEY ARE WHEN THE
        BUILD STARTS. It took a list made when the key was pressed, and the
        build swapped all of it in: pick part 1's patch, then part 2's before
        the first build landed, and part 1 went back; + twice stepped once.
        Now each queued edit sees the one before it. And what a cheap edit
        wrote onto the old parts while this built -- a level, a channel, a
        mute -- is carried onto the new ones (CARRY): the swap lost it."""
        def job(progress):
            before = self.specs()
            for i, s in enumerate(before):
                s["_row"] = i
            specs = edit([dict(s) for s in before])
            if specs is None:
                return
            parts = [LV.Part.from_dict(s, progress, getattr(self.live, "eastern", None)) for s in specs]
            now = self.specs()
            if len(now) == len(before):
                for p, s in zip(parts, specs):
                    r = s.get("_row")
                    if r is None:
                        continue
                    for k in self.CARRY:
                        # changed on the old part since the build began, and
                        # not by this edit itself
                        if now[r].get(k) != before[r].get(k) and s.get(k) == before[r].get(k):
                            setattr(p, k, now[r].get(k))
            self.live.set_parts(parts)
        self.builder.submit(label, job)

    def specs(self):
        return [p.to_dict() for p in self.parts()]

    def change_patch(self, delta=None, program=None, drums=None, bank=0, std=None):
        p = self.sel()
        if p is None:
            return
        row = self.row

        def edit(specs):
            if row >= len(specs):
                return None
            s = specs[row]
            if not self._patch_edit(s, delta, program, drums, bank, std):
                return None
            self.builder.label = patch_label(s)
            return specs
        # (the label the build starts under; its own, once it knows the patch)
        self.rebuild("part %d patch" % (row + 1), edit)

    def _patch_edit(self, s, delta, program, drums, bank, std):
        """change_patch's edit of one part's spec; False: nothing to change."""
        # A NEW PATCH IS ON ITS CAPITAL TONE unless a bank is asked for: stepping
        # programs leaves a variation, as a Sound Canvas's program buttons do
        s.pop("bank", None)
        if bank and drums is None and program is not None:
            s["bank"] = int(bank)
        # ...IN THE PART'S STANDARD (patch_tree): the picker sets it, and the
        # program keys step within it -- the MT-32's tones stay the MT-32's
        if std is not None:
            s.pop("std", None)
            if std != "gm":
                s["std"] = std
        if delta is not None and s.get("std") == "mt32" and not s.get("drums"):
            s["bank"] = 127
        if drums is not None:
            s["drums"] = drums
            if program is not None:
                s["program"] = program      # on a drum part, the drum SET
        elif program is not None:
            s["program"], s["drums"] = program, False
        else:
            # -1 steps off the bottom of the GM list into the drum kit, which is
            # where a kit belongs in a list of patches you scroll through.
            if s["drums"]:
                if delta > 0:
                    s["drums"], s["program"] = False, 0
                else:
                    return False
            else:
                n = s["program"] + delta
                if n < 0:
                    s["drums"] = True
                elif n > 127:
                    return False
                else:
                    s["program"] = n
        s["drawn"] = []          # a new patch has its own stops
        return True

    def change_tuner(self, delta):
        p = self.sel()
        if p is None:
            return
        row = self.row

        def edit(specs):
            if row >= len(specs):
                return None
            s = specs[row]
            i = (TUNERS.index(s["tuner"]) if s["tuner"] in TUNERS else 0) + delta
            s["tuner"] = TUNERS[max(0, min(len(TUNERS) - 1, i))]
            self.builder.label = "%s / %s" % (patch_label(s), s["tuner"])
            return specs
        self.rebuild("part %d tuner" % (row + 1), edit)

    def add_part(self):
        row = self.row

        def edit(specs):
            if not specs:
                return [dict(program=56, drums=False, tuner="hybrid440", lo=0, hi=127)]
            r = min(row, len(specs) - 1)
            specs.insert(r + 1, dict(specs[r]))
            return specs
        self.rebuild("layer", edit)
        self.row += 1
        self.say("layered -- same keys, same channel; change its patch or zone")

    def del_part(self):
        if len(self.parts()) <= 1:
            self.say("the last part cannot be removed")
            return
        row = self.row

        def edit(specs):
            if len(specs) <= 1 or row >= len(specs):
                return None
            specs.pop(row)
            return specs
        self.rebuild("remove part", edit)
        self.row = max(0, self.row - 1)

    def split_here(self):
        """Cut the selected part's range in two and give the upper half to a new
        part -- the fastest way to get a kit under a manual."""
        p = self.sel()
        if p is None:
            return
        mid = (p.lo + p.hi) // 2
        if mid <= p.lo or mid >= p.hi:
            self.say("range too small to split")
            return
        row = self.row

        def edit(specs):
            if row >= len(specs):
                return None
            upper = dict(specs[row])
            specs[row]["hi"] = mid
            upper["lo"] = mid + 1
            specs.insert(row + 1, upper)
            return specs
        self.rebuild("split", edit)
        self.say("split at %s -- now change the upper part's patch" % note_name(mid))

    # ---- cheap edits --------------------------------------------------------
    def adjust(self, delta, big=False):
        p = self.sel()
        if p is None:
            return
        col = COLS[self.col]
        step = delta * (12 if big and col in ("lo", "hi", "tr") else 1)
        if col == "patch":
            self.change_patch(delta * (8 if big else 1))
        elif col == "tuner":
            self.change_tuner(delta)
        elif col == "ch":
            # 0 is "every channel", which is what a single keyboard wants.
            c = 0 if p.channel is None else p.channel + 1
            c = max(0, min(16, c + delta))
            p.channel = None if c == 0 else c - 1
        elif col == "lo":
            p.lo = max(0, min(p.hi, p.lo + step))
        elif col == "hi":
            p.hi = max(p.lo, min(127, p.hi + step))
        elif col == "tr":
            p.transpose = max(-48, min(48, p.transpose + step))
        elif col == "level":
            p.level_db = max(LEVEL_DB_MIN,
                             min(LEVEL_DB_MAX,
                                 p.level_db + delta * (3.0 if big else 0.5)))
        elif col == "touch":
            self.toggle_touch(p)
        elif col == "stops":
            # -/+ adds and removes ranks in the organ's own crescendo order, so
            # the column behaves like every other one; enter is where you pick
            # ranks by name, including the ones no crescendo reaches.
            if p.organ:
                order = [r for r in p.patch.cres_order] + \
                        [r for r in p.patch.stop_display if r not in p.patch.cres_order]
                k = len([r for r in order if r in p.drawn])
                k = max(1, min(len(order), k + delta))
                self.live.request_stops(p, set(order[:k]))

    def toggle_stop(self, i, row=0):
        p = self.sel()
        if p is None or not p.organ:
            return
        rows = p.patch.stop_rows
        names = rows[row] if row < len(rows) else []
        if not 0 <= i < len(names):
            return
        want = set(p.drawn)
        want.symmetric_difference_update({names[i]})
        # Drawing a stop STAMPS -- it pops slots off the free list and leaves
        # `last_slots` behind for the very next line to read. Doing that from
        # here can hand the callback's own _draw a set of slots belonging to
        # something else, so it goes on the queue like everything else.
        self.live.request_stops(p, want)

    # ---- presets ------------------------------------------------------------
    def save_preset(self, scr):
        name = self.prompt(scr, "save preset as: ")
        if not name:
            return
        LV.save_preset(name, self.live)
        self.say("saved %r to %s" % (name, os.path.basename(LV.PRESET_PATH)))

    def save_scene(self, scr):
        """N: the channel controls as they are now, under a name."""
        name = self.prompt(scr, "save scene as: ")
        if not name:
            return
        n = LV.save_scene(name, self.live)
        self.say("scene %r: %d events -> %s" % (name, n, os.path.basename(LV.SCENE_PATH)))

    def recall_scene(self, scr):
        """R: put a named scene's channel controls back, on this setup."""
        d = LV.load_scenes()
        if not d:
            self.say("no scenes in %s yet -- N saves one" % os.path.basename(LV.SCENE_PATH))
            return
        names = sorted(d)
        pick = self.menu(scr, "recall scene", names)
        if pick is None:
            return
        n = LV.recall_scene(self.live, d[names[pick]])
        self.say("scene %r: %d events" % (names[pick], n))

    def free_hotkeys(self):
        """A preset or session from before N and R were the scene keys may have
        bound a control to one. The scene key wins, and says so."""
        lost = [c for c in self.live.screen_controls
                if c.get("hotkey") and c["hotkey"] not in HOTKEYS_FREE]
        for c in lost:
            c["hotkey"] = None
        if lost:
            self.say("hotkey unbound (now a panel key): %s"
                     % ", ".join(LV.CONTROL_BY_KEY[c["key"]][1] for c in lost), 6)

    def load_preset(self, scr):
        d = LV.load_presets()
        if not d:
            self.say("no presets in %s yet" % os.path.basename(LV.PRESET_PATH))
            return
        names = sorted(d)
        pick = self.menu(scr, "load preset", names)
        if pick is None:
            return
        pres = d[names[pick]]
        def job(progress):
            LV.apply_preset(self.live, pres, progress)
            self.free_hotkeys()
        self.builder.submit("preset %s" % names[pick], job)
        self.row = 0
        self.say("loading %r" % names[pick])

    # ---- little modal widgets ----------------------------------------------
    def prompt(self, scr, label):
        h, w = scr.getmaxyx()
        buf = ""
        scr.keypad(True)
        curses.curs_set(1)
        try:
            while True:
                scr.move(h - 1, 0); scr.clrtoeol()
                self.addstr(scr, h - 1, 0, label[:w - 1], self.C("accent") | curses.A_BOLD)
                self.addstr(scr, h - 1, len(label), buf[:max(0, w - 1 - len(label))] + "_",
                            self.C("value") | curses.A_BOLD)
                scr.refresh()
                c = scr.getch()
                if c == -1:
                    continue
                if c in (10, 13):
                    return buf.strip()
                if c == 27:
                    return None
                if c in (curses.KEY_BACKSPACE, 127, 8):
                    buf = buf[:-1]
                elif 32 <= c < 127 and len(buf) < 40:
                    buf += chr(c)
        finally:
            curses.curs_set(0)

    def menu(self, scr, title, items, start=0, nav=False, everywhere=None):
        """A centred picker. Returns an index, or None if cancelled.

        A TREE'S LEVEL (pick_patch): with nav, Left -- or Backspace outside a
        search -- returns "back" and Right is Enter; with everywhere (rows
        from the whole tree), a search lists those instead, and its pick
        comes back as ("found", row).

        AND A SEARCH (Ben: "control over tone means search and edit"): "/"
        starts one, typing narrows the list to the rows holding every word
        typed (any case: "slow str", "rhodes", "127 bell"), the arrows move
        within them, Enter picks, Backspace edits, Esc clears it (a second
        closes the menu). A heading row (a section of the patch list) stays
        out of a search's matches."""
        scr.keypad(True)
        i = start
        query, searching = "", False

        here = items

        def view():
            if not query:
                return list(range(len(here)))
            ws = query.lower().split()
            return [j for j, x in enumerate(here)
                    if not x.startswith("--") and all(w in x.lower() for w in ws)]
        while True:
            wide = bool(query) and everywhere is not None
            if (here is everywhere) != wide:
                here, i = (everywhere if wide else items), (0 if wide else start)
            vis = view()
            h, w = scr.getmaxyx()
            if vis and i not in vis:
                i = vis[0]
            pos = vis.index(i) if i in vis else 0
            n = min(max(len(vis), 1), max(3, h - 8))
            top = max(0, min(pos - n // 2, len(vis) - n))
            bw = min(w - 4, max(len(title) + 8, max((len(x) for x in here), default=10) + 8))
            y0 = max(0, (h - n) // 2 - 1)
            x0 = max(0, (w - bw) // 2)
            foot = (("/" + query + ("_" if searching else "") + "   %d found" % len(vis)) if (searching or query)
                    else "enter select   / search   esc cancel")
            self.box(scr, y0 - 1, x0, n + 3, bw, title, foot)
            if searching or query:
                self.addstr(scr, y0 + n + 1, x0 + 3, ("/" + query + ("_" if searching else ""))[:bw - 6],
                            self.C("accent") | curses.A_BOLD)
            for k in range(n):
                if top + k >= len(vis):
                    if not vis and k == 0:
                        self.addstr(scr, y0, x0 + 2, "(nothing matches)"[:bw - 4], self.C("dim"))
                    continue
                j = vis[top + k]
                txt = " %-*s" % (bw - 5, here[j][:bw - 5])
                at = (self.C("sel") | curses.A_BOLD if j == i else
                      self.C("label") if here[j].startswith("--") else self.C("text"))
                self.addstr(scr, y0 + k, x0 + 1, txt[:bw - 2], at)
            scr.refresh()
            c = scr.getch()
            if c == -1:
                continue
            if searching and 32 <= c < 127 and c != ord("/"):
                query += chr(c)
                continue
            if searching and c in (curses.KEY_BACKSPACE, 127, 8):
                query = query[:-1]
                continue
            if c == ord("/"):
                searching = True
                continue
            if c in (curses.KEY_UP, ord("k")):
                i = vis[max(0, pos - 1)] if vis else i
            elif c in (curses.KEY_DOWN, ord("j")):
                i = vis[min(len(vis) - 1, pos + 1)] if vis else i
            elif c == curses.KEY_PPAGE:
                i = vis[max(0, pos - n)] if vis else i
            elif c == curses.KEY_NPAGE:
                i = vis[min(len(vis) - 1, pos + n)] if vis else i
            elif c in (10, 13) or (nav and c == curses.KEY_RIGHT):
                if vis:
                    return ("found", i) if here is not items else i
            elif nav and (c == curses.KEY_LEFT or (c in (curses.KEY_BACKSPACE, 127, 8) and not searching)):
                return "back"
            elif c == 27:
                if searching or query:
                    query, searching = "", False      # first Esc: the search
                else:
                    return None
            elif c == ord("q") and not searching:
                return None

    def enter(self, scr):
        """Enter acts on the column you are actually standing in."""
        col = COLS[self.col]
        if col == "patch":
            self.pick_patch(scr)
        elif col == "tuner":
            self.pick_tuner(scr)
        elif col == "stops":
            self.pick_stops(scr)
        elif col == "touch":
            self.toggle_touch(self.sel())
        elif col == "efx":
            self.pick_efx(scr)
        else:
            self.type_value(scr, col)

    def toggle_touch(self, p):
        """FIXED TOUCH, on any part: on, velocity does not set its level; off,
        it does. Each patch starts its own way -- fixed for a key that only
        trips a jack or opens a valve, velocity for the rest."""
        if p is None:
            return
        p.fixed_touch = not p.touch_fixed()
        self.say("part %d: %s" % (self.row + 1, "fixed touch -- the key sets no level"
                                  if p.fixed_touch else "velocity sets the level"))
        self.live.dirty = True

    def type_value(self, scr, col):
        """Type a value into a numeric column. Ranges take a note name too, so
        \"C3\" and \"48\" both work."""
        p = self.sel()
        if p is None:
            return
        got = self.prompt(scr, "%s = " % col)
        if not got:
            return
        try:
            if col in ("lo", "hi"):
                v = parse_note(got)
            elif col == "level":
                v = float(got)
            else:
                v = int(got, 10)
        except (ValueError, TypeError):
            self.say("could not read %r as a %s" % (got, col))
            return
        if col == "ch":
            p.channel = None if v <= 0 else max(1, min(16, v)) - 1
        elif col == "lo":
            p.lo = max(0, min(p.hi, v))
        elif col == "hi":
            p.hi = max(p.lo, min(127, v))
        elif col == "tr":
            p.transpose = max(-48, min(48, v))
        elif col == "level":
            p.level_db = max(LEVEL_DB_MIN, min(LEVEL_DB_MAX, v))

    def pick_tuner(self, scr):
        p = self.sel()
        if p is None:
            return
        own = getattr(p, "base_tuner", p.tuner)
        start = TUNERS.index(own) if own in TUNERS else 0
        pick = self.menu(scr, "temperament for part %d" % (self.row + 1),
                         ["%-12s %s" % (t, TUNER_NOTE.get(t, "")) for t in TUNERS],
                         start)
        if pick is None or TUNERS[pick] == own:
            return
        row, tuner = self.row, TUNERS[pick]

        def edit(specs):
            if row >= len(specs):
                return None
            specs[row]["tuner"] = tuner
            return specs
        self.rebuild("%s / %s" % (p.label(), tuner), edit)

    def pick_eastern(self, scr):
        """THE EASTERN TUNING, the rig's secondary (ragas.py): a SYSTEM of swara
        positions (theory, Bel's Todi, the 27 measured from Saraga), a RAGA (its
        swaras: the meend's detents) and where SA sits. Every part whose voice
        is an Indian instrument plays it; the rest keep their own tuner, and a
        part given a raga in its temperament column keeps that one."""
        import ragas
        cur = getattr(self.live, "eastern", None)
        systems = sorted(ragas.SYSTEMS, key=lambda k: (k.startswith("saraga_"), k))
        items = ["off -- every part on its own tuner"] + [
            "%-26s %s" % (k, (ragas.SYSTEMS[k]["kind"] + ": " + ragas.SYSTEMS[k]["source"])[:60])
            for k in systems]
        try:
            cs, cr, ck, _ = ragas.parse(cur) if cur else (None, None, 1, None)
        except ValueError:
            cs, cr, ck = None, None, 1
        start = systems.index(cs) + 1 if cs in systems else 0
        pick = self.menu(scr, "Eastern tuning: system", items, start)
        if pick is None:
            return
        if pick == 0:
            self.live.set_eastern(None)
            self.say("Eastern tuning off: every part on its own tuner")
            return
        system = systems[pick - 1]
        own = system in ragas.RAGAS
        rg = [None] + sorted(r for r in ragas.RAGAS if not r.startswith("saraga_"))
        ritems = [("(its own swaras)" if own else "(all twelve swaras)")] + [
            "%-10s %s" % (r, " ".join(ragas.SWARAS[i] for i in ragas.RAGAS[r])) for r in rg[1:]]
        rp = self.menu(scr, "Eastern tuning: raga (the meend's detents)", ritems,
                       rg.index(cr) if cr in rg else 0)
        if rp is None:
            return
        keys = ("c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b")
        kp = self.menu(scr, "Eastern tuning: Sa", [k.upper() for k in keys], ck)
        if kp is None:
            return
        spec = "raga:%s%s@%s" % (system, "/" + rg[rp] if rg[rp] else "", keys[kp])
        self.live.set_eastern(spec)
        n = sum(1 for p in self.parts()
                if LV.tuner_for(p.program, p.drums, getattr(p, "base_tuner", p.tuner), spec) != getattr(p, "base_tuner", p.tuner))
        self.say("Eastern tuning %s: %d part(s) re-tuning" % (spec, n))

    def pick_stops(self, scr):
        """Draw stops by name.

        The mod wheel walks `crescendo_order`, which deliberately does NOT hold
        every rank -- the reed organ's `trumpet` and the flue organ's `flute` and
        `mixture` are not in it, so the wheel can never reach them. They are
        registration choices, not places a crescendo passes through, and this is
        where you make them.
        """
        p = self.sel()
        if p is None:
            return
        if not p.organ:
            self.say("%s has no stops -- they are an organ and harpsichord thing"
                     % (p.label()))
            return
        names = p.patch.stop_display
        cres = set(p.patch.cres_order)
        if cres:
            wd = max(len(r) for r in names)
            labels = ["%-*s  %s" % (wd, r, "crescendo" if r in cres else "hand-drawn only")
                      for r in names]
        else:
            # No crescendo: a harmonium, whose registers are split. Say which
            # half each one speaks in, and which knobs are not reeds at all.
            ranks = {rk[0]: rk for rk in p.patch.stop_ranks}
            ranks = [ranks[r] for r in names]
            def half(rk):
                if rk[1] is None:
                    return "effect"
                kr = rk[6] if len(rk) > 6 else None
                return ("bass" if kr[1] < 127 else "treble") if kr else ""
            labels = ["%-14s %s" % (rk[0], half(rk)) for rk in ranks]
        got = self.multi_menu(scr, "stops for part %d" % (self.row + 1), labels,
                              {i for i, r in enumerate(names) if r in p.drawn})
        if got is None:
            return
        self.live.request_stops(p, {names[i] for i in got})

    def multi_menu(self, scr, title, items, chosen):
        """A picker where space toggles and enter accepts. Returns a set of
        indices, or None if cancelled."""
        scr.keypad(True)
        chosen = set(chosen)
        i = 0
        while True:
            h, w = scr.getmaxyx()
            n = min(len(items), max(3, h - 8))
            top = max(0, min(i - n // 2, len(items) - n))
            bw = min(w - 4, max(len(title) + 8,
                                max((len(x) for x in items), default=10) + 10))
            y0 = max(0, (h - n) // 2 - 1)
            x0 = max(0, (w - bw) // 2)
            self.box(scr, y0 - 1, x0, n + 3, bw, title, "space toggle   enter accept   esc cancel")
            for k in range(n):
                j = top + k
                on = j in chosen
                txt = " %s %-*s" % ("\u25cf" if on else "\u25cb", bw - 7, items[j][:bw - 7])
                at = (self.C("sel") | curses.A_BOLD if j == i else
                      (self.C("accent") if on else self.C("text")))
                self.addstr(scr, y0 + k, x0 + 1, txt[:bw - 2], at)
            scr.refresh()
            c = scr.getch()
            if c == -1:
                continue
            if c in (curses.KEY_UP, ord("k")):
                i = max(0, i - 1)
            elif c in (curses.KEY_DOWN, ord("j")):
                i = min(len(items) - 1, i + 1)
            elif c == ord(" "):
                chosen.symmetric_difference_update({i})
            elif c in (10, 13):
                return chosen
            elif c == 27 or c == ord("q"):
                return None

    # ---- the insertion effect (gsefx; Live.efx, set through Live.efx_send) --
    def efx_channels(self, p):
        """The MIDI channels a part listens on: its own, or all for 'all'."""
        return set(range(16)) if p.channel is None else {p.channel}

    def _efx_wait(self, rev):
        """Let the audio thread apply what was sent (the panel's message
        queues as hardware's does) before the panel reads the state back."""
        t0 = time.monotonic()
        while self.live.efx_rev == rev and time.monotonic() - t0 < 0.1:
            time.sleep(0.005)

    def _efx_send(self, ev):
        rev = self.live.efx_rev
        self.live.efx_send(ev)
        self._efx_wait(rev)

    def pick_efx(self, scr):
        """THE INSERTION EFFECT, the Sound Canvas's: the selected part on or
        off it, its type, and each of its parameters at the value in effect
        (the file's, Roland's default, or ours where he prints none) -- each
        sent as the GS message a file would carry (Live.efx_send)."""
        p = self.sel()
        if p is None:
            return
        i = 0
        while True:
            st = self.live.efx
            name = GSX.TYPES.get(st['type'], "Thru")
            chans = self.efx_channels(p)
            on = chans <= self.live.efx_parts
            num = next((n for n, k, _ in GSX.numbered() if k == st['type']), 0)
            rows = [("part", "part %d (%s) on the EFX:  %s" % (
                        self.row + 1, "all channels" if p.channel is None else "channel %d" % (p.channel + 1),
                        "yes" if on else "no")),
                    ("type", "type:  %s" % ("%02d %s" % (num, name) if num else "Thru"))]
            if name != "Thru":
                eff = GSX.in_effect(st)
                rows.append((None, "-- parameters"))
                for n, nm, _rg, d in GSX.params(name):
                    v = eff.get(n, d if d is not None else 0)
                    rows.append((("param", n, nm, v), "%-16s %s" % (nm[:16], GSX.printed_value(name, n, v))))
                rows.append((None, "-- its controllers (a knob the instrument does not use)"))
                mk = GSX.marks(name)
                for which, mark, sa, da in ((1, '+', GSX.CTL_SRC1, GSX.CTL_DEP1), (2, '#', GSX.CTL_SRC2, GSX.CTL_DEP2)):
                    pn_ = mk.get(mark)
                    pname = next((nm for n, nm, _r, _d in GSX.params(name) if n == pn_), "-")
                    so = GSX.source_of(st, which)
                    desc = ("off" if so is None else "%s, %+d%%" % (self.src_label(so[0]), round(so[1] * 100)))
                    rows.append((("ctl", which, sa, da, pname), "%s %-13s %s" % (mark, pname[:13], desc)))
                rows.append((None, "-- sends from the EFX"))
                for a, nm in ((GSX.SEND_REV, "to reverb"), (GSX.SEND_CHO, "to chorus"), (GSX.SEND_DLY, "to delay")):
                    rows.append((("send", a, nm, st['send'].get(a, 0)), "%-16s %d" % (nm, st['send'].get(a, 0))))
            got = self.menu(scr, "insertion effect", [r[1] for r in rows], i)
            if got is None:
                return
            i = got
            what = rows[got][0]
            if what is None:
                continue
            if what == "part":
                for ch in sorted(chans):
                    self._efx_send(('part', ch, not on))
            elif what == "type":
                self.pick_efx_type(scr)
            elif what[0] == "param":
                self.edit_efx(scr, name, what)
            elif what[0] == "send":
                self.edit_efx(scr, name, what)
            elif what[0] == "ctl":
                self.pick_efx_ctl(scr, *what[1:])

    @staticmethod
    def src_label(code):
        return ("off" if not code else "CC%d" % code if code <= 95
                else "aftertouch" if code == GSX.SRC_CAF else "bend")

    def pick_efx_ctl(self, scr, which, sa, da, pname):
        """An effect controller: what drives the type's + (or #) parameter --
        LEARN (move the knob, pedal or wheel), or picked from the list -- and
        how far (depth). Each a GS message, as a file would carry it."""
        st = self.live.efx
        cur = int((st.get('ctl') or {}).get(sa, 0))
        opts = ["learn: move a knob, pedal or wheel now", "off"] + ["CC%d" % c for c in range(1, 96)] \
            + ["aftertouch", "bend", "depth: %+d%%" % round(((st.get('ctl') or {}).get(da, 0x40) - 64) / 63.0 * 100)]
        codes = [None, 0] + list(range(1, 96)) + [GSX.SRC_CAF, GSX.SRC_BEND, "depth"]
        start = codes.index(cur) if cur in codes else 1
        got = self.menu(scr, "%s moved by" % pname, opts, start)
        if got is None:
            return
        code = codes[got]
        if code == "depth":
            self.edit_efx(scr, "", ("send", da, "depth", (st.get('ctl') or {}).get(da, 0x40)),
                          as_kind="ctl")
            return
        if code is None:                               # learn
            t0 = time.monotonic()
            self.say("move the knob, pedal or wheel for %s ..." % pname, secs=5.0)
            scr.timeout(50)
            try:
                while time.monotonic() - t0 < 8.0:
                    lc = self.live.last_ctl
                    if lc is not None and lc[1] > t0:
                        code = lc[0]
                        break
                    if scr.getch() == 27:
                        return
                    self.draw(scr)
            finally:
                scr.timeout(50)                 # the main loop's redraw
            if code is None:
                self.say("nothing moved")
                return
        self._efx_send(('ctl', sa, code))
        if code and (st.get('ctl') or {}).get(da, 0x40) == 0x40:
            self._efx_send(('ctl', da, 0x7F))           # a source with no depth does nothing: +100%
        self.say("%s moved by %s" % (pname, self.src_label(code)))

    def pick_efx_type(self, scr):
        """The type, in Roland's families (gsefx.CATEGORIES): Enter or Right
        into a family, Left back, "/" searching every type by name."""
        allt = GSX.numbered()
        found = ["%02d %s   (%s)" % (n, nm, next(c for c, a, b in GSX.CATEGORIES if a <= n <= b))
                 for n, _k, nm in allt]
        cats = ["00 Thru"] + [c for c, _a, _b in GSX.CATEGORIES]
        cur = self.live.efx['type']
        cn = next((n for n, k, _ in allt if k == cur), 0)
        ci = next((j + 1 for j, (_c, a, b) in enumerate(GSX.CATEGORIES) if a <= cn <= b), 0)
        while True:
            got = self.menu(scr, "insertion effect type", cats, ci, nav=True, everywhere=found)
            if got in (None, "back"):
                return
            if isinstance(got, tuple):
                key = allt[got[1]][1]
                break
            if got == 0:
                key = (0, 0)
                break
            ci = got
            _c, a, b = GSX.CATEGORIES[got - 1]
            kids = [(n, k, nm) for n, k, nm in allt if a <= n <= b]
            start = next((j for j, (n, _k, _nm) in enumerate(kids) if n == cn), 0)
            sub = self.menu(scr, "insertion effect › " + _c, ["%02d %s" % (n, nm) for n, _k, nm in kids],
                            start, nav=True, everywhere=found)
            if sub is None:
                return
            if sub == "back":
                continue
            if isinstance(sub, tuple):
                key = allt[sub[1]][1]
            else:
                key = kids[sub][1]
            break
        if key != cur:
            self._efx_send(('type', key))
            self.say("EFX: %s" % GSX.TYPES.get(key, "Thru"))

    def edit_efx(self, scr, name, what, as_kind=None):
        """One parameter (or send), moved with Left/Right (PgUp/PgDn ten at a
        time) or typed as a raw 0-127; each move sent, so it is heard as it
        goes. Enter keeps it, Esc puts back what it was."""
        kind, n, nm, v0 = what
        kind = as_kind or kind
        rng = GSX.param_range(name, n) if kind == "param" else (0, 127)
        vals = list(rng) if isinstance(rng, list) else list(range(rng[0], rng[1] + 1))
        v = min(vals, key=lambda x: abs(x - v0))
        j = vals.index(v)
        show = ((lambda x: GSX.printed_value(name, n, x)) if kind == "param" else
                (lambda x: "%+d%%" % round((x - 64) / 63.0 * 100)) if kind == "ctl" else str)
        ev = ((lambda x: ('param', n, x)) if kind == "param" else
              (lambda x: ('ctl', n, x)) if kind == "ctl" else (lambda x: ('send', n, x)))
        scr.keypad(True)
        while True:
            h, w = scr.getmaxyx()
            line = " %s:  %s   (raw %d)   left/right, pgup/pgdn, digits, enter keep, esc back " % (
                nm, show(vals[j]), vals[j])
            self.addstr(scr, h // 2, max(0, (w - len(line)) // 2), line[:w - 1], curses.A_REVERSE | curses.A_BOLD)
            scr.refresh()
            c = scr.getch()
            k = j
            if c in (curses.KEY_RIGHT, ord("l"), ord("+"), ord("=")):
                k = min(len(vals) - 1, j + 1)
            elif c in (curses.KEY_LEFT, ord("h"), ord("-")):
                k = max(0, j - 1)
            elif c == curses.KEY_NPAGE:
                k = max(0, j - 10)
            elif c == curses.KEY_PPAGE:
                k = min(len(vals) - 1, j + 10)
            elif 48 <= c <= 57:
                got = self.prompt(scr, "%s raw value = %s" % (nm, chr(c)))
                # (Esc there is None: nothing typed is applied -- it set the
                # first digit, which was never meant)
                if got is not None:
                    try:
                        x = int(chr(c) + got, 10)
                        k = vals.index(min(vals, key=lambda y: abs(y - x)))
                    except ValueError:
                        pass
            elif c in (10, 13):
                return
            elif c == 27:
                if vals[j] != v0:
                    self._efx_send(ev(v0))
                return
            if k != j:
                j = k
                self._efx_send(ev(vals[j]))

    def pick_patch(self, scr):
        """THE PATCH, BY STANDARD (patch_tree): General MIDI, a Sound Canvas by
        level, the MT-32's tones, the drum kits -- Enter or Right goes in,
        Left or Backspace comes out, and "/" searches the whole tree from any
        level. It opens on the part's own patch, in the part's standard."""
        p = self.sel()
        if p is None:
            return
        tree = patch_tree()
        leaves = tree_leaves(tree)
        found = [leaf_crumb(up, lf) for _, up, lf in leaves]
        # ...a part with no standard of its own opens in THE STANDARD (the
        # globals pane's; Live.std_map), at its level of the Sound Canvas
        _std = getattr(p, "std", "gm")
        if _std == "gm" and self.live.std_map:
            _std = "sc%d" % self.live.std_map
        here = ((True, p.program % 128 if p.program >= 3 * 128 else p.program, 0, None) if p.drums else
                (False, p.program, p.variation, _std))
        path = (next((pa for pa, _, lf in leaves if lf["pick"] == here), None)
                # a patch picked by number, or saved before standards: its GM place
                or next((pa for pa, _, lf in leaves if lf["pick"][:3] == here[:3]), None)
                or (0,))
        node, stack = tree, []           # stack: (node above, the row we came in by)
        while True:
            d = len(stack)
            start = path[d] if d < len(path) else 0
            title = " \u203a ".join(["patch for part %d" % (self.row + 1)] +
                                    [n["crumb"] for n, _ in stack if n.get("crumb")] +
                                    ([node["crumb"]] if node.get("crumb") else []))
            got = self.menu(scr, title, [k["label"] for k in node["kids"]], start,
                            nav=True, everywhere=found)
            if got is None:
                return
            if got == "back":
                if not stack:
                    return
                node, j = stack.pop()
                path = path[:len(stack)] + (j,)
                continue
            if isinstance(got, tuple):        # a search's pick, from anywhere
                leaf = leaves[got[1]][2]
                break
            k = node["kids"][got]
            if "kids" not in k:
                leaf = k
                break
            # in: onto the patch's own row if this is its way, else the top
            if not (d < len(path) and path[d] == got):
                path = path[:d] + (got,)
            stack.append((node, got))
            node = k
        dr, prog, v, std = leaf["pick"]
        if dr:
            # the set as the standard has it (an SC-88 Pro standard: its own
            # Hip-Hop set, not the SC-8850's)
            self.change_patch(drums=True, program=PM.kit_in_map(prog, self.live.std_map) if prog < 128 else prog)
        else:
            self.change_patch(program=prog, bank=v, std=std)

    # ---- the controls pane -------------------------------------------------
    # A keyboard may send nothing but notes. This pane supplies what it lacks
    # (on-screen controls, sent through Live.inject exactly as hardware's would
    # arrive) and bends what it has (routes, which Live.on_midi applies to the
    # hardware before the engine sees it).
    #
    # A TERMINAL NEVER REPORTS A KEY BEING LET GO. curses hands over a key when
    # it goes down and says nothing when it comes up, so a computer key cannot
    # be held like a pedal: an on-screen switch LATCHES -- press to put it down,
    # press again to lift it. Held-while-pushed exists only on hardware, which
    # is what routing the pitch wheel onto sustain is for.

    ROUTE_SOURCES = (
        ("mod wheel", ("cc", 1)),
        ("pitch wheel, pushed up", ("bend", "up")),
        ("pitch wheel, pulled down", ("bend", "down")),
        ("pitch wheel, either way", ("bend", "both")),
        ("aftertouch", ("pressure",)),
        ("sustain pedal (CC64)", ("cc", 64)),
        ("expression pedal (CC11)", ("cc", 11)),
        ("another CC, by number", None),
        ("a key: press it", "learn"),
        ("a key: by name (C1, 36)", "name"),
    )

    def controls(self):
        return self.live.screen_controls

    def ctl_rows(self):
        """The pane's rows: the on-screen controls, then the routes."""
        return ([("ctl", i) for i in range(len(self.controls()))]
                + [("route", j) for j in range(len(self.live.routes))])

    def ctl_sel(self):
        rows = self.ctl_rows()
        if not rows:
            self.crow = 0
            return None
        self.crow = max(0, min(self.crow, len(rows) - 1))
        return rows[self.crow]

    def switch_on(self, key, ch):
        """The ENGINE's pedal state, not a copy: a CC121 or a GM System On from
        the keyboard lifts a pedal, and the lamp has to say so."""
        L = self.live
        ch = 0 if ch is None else ch
        if key == 64:
            return bool(L.pedal.get(ch))
        if key == 66:
            return ch in L.sost
        if key == 67:
            return bool(L.soft.get(ch))
        if key == 65:
            return bool(L.porta_on.get(ch))
        if key == "mono":
            return ch in L.mono
        return False

    def send_control(self, c, value):
        """Set an on-screen control and send it -- to every channel for 'all',
        since a part may listen on any of them."""
        key = c["key"]
        kind = LV.CONTROL_BY_KEY[key][2]
        lo, hi = (-8192, 8191) if kind == "bend" else (0, 127)
        c["value"] = int(max(lo, min(hi, value)))
        chans = range(16) if c.get("channel") is None else (c["channel"],)
        for ch in chans:
            self.live.inject(LV.control_message(key, c["value"], ch))

    def fire(self, c):
        """What a control's hotkey does: a switch toggles; a continuous control
        jumps between its default and full travel -- the mod wheel's vibrato on
        and off, say."""
        key = c["key"]
        _, label, kind, default = LV.CONTROL_BY_KEY[key]
        if kind == "switch":
            on = not self.switch_on(key, c.get("channel"))
            self.send_control(c, 127 if on else 0)
            self.say("%s %s" % (label, "down" if on else "up"))
        else:
            top = 8191 if kind == "bend" else 127
            self.send_control(c, default if c.get("value", default) != default else top)
            self.say("%s %d" % (label, c["value"]))

    def learn_key(self, scr):
        """Wait for the next key pressed on the keyboard: (channel, note), or
        None if cancelled or nothing came in ten seconds. The press does not
        play -- Live.learn_key swallows it and its release."""
        self.live.learn_key()
        self.say("press the key on your keyboard  (esc: cancel)", 11)
        t0 = time.monotonic()
        try:
            while time.monotonic() - t0 < 10.0:
                got = self.live.learned()
                if got is not None:
                    return got
                self.draw(scr)
                if scr.getch() == 27:
                    self.say("cancelled")
                    return None
            self.say("no key came in")
            return None
        finally:
            self.live.learn_cancel()

    def _channel_of(self, s):
        if s.lower() == "all":
            return None
        try:
            c = int(s)
        except ValueError:
            c = 0
        if not 1 <= c <= 16:
            self.say("not a channel: %s" % s)
            return False
        return c - 1

    def ask_channel(self, scr, what):
        """None for every channel; False if cancelled or not a channel."""
        s = self.prompt(scr, "%s channel (1-16, blank = all): " % what)
        if s is None:
            return False
        if s == "" or s.lower() == "all":
            return None
        try:
            ch = int(s)
        except ValueError:
            ch = 0
        if not 1 <= ch <= 16:
            self.say("not a channel: %s" % s)
            return False
        return ch - 1

    def add_control(self, scr):
        items = ["%-16s %s" % (lab, "cc%d" % k if isinstance(k, int) else k)
                 for k, lab, kind, d in LV.CONTROLS]
        i = self.menu(scr, "add an on-screen control", items)
        if i is None:
            return
        ch = self.ask_channel(scr, LV.CONTROLS[i][1])
        if ch is False:
            return
        key, label, kind, default = LV.CONTROLS[i]
        # It starts at its default and SENDS NOTHING: adding a control must not
        # change the sound until it is moved.
        self.controls().append(dict(key=key, channel=ch, value=default, hotkey=None))
        self.crow = len(self.controls()) - 1
        self.say("added %s" % label)

    def add_route(self, scr):
        i = self.menu(scr, "route FROM", [x[0] for x in self.ROUTE_SOURCES])
        if i is None:
            return
        src = self.ROUTE_SOURCES[i][1]
        learned_ch = None
        if src == "learn":
            got = self.learn_key(scr)
            if got is None:
                return
            learned_ch, n = got
            src = ("note", n)
        elif src == "name":
            s_ = self.prompt(scr, "key (C1, F#2, or 0-127): ")
            if s_ is None:
                return
            try:
                src = ("note", parse_note(s_))
            except ValueError:
                self.say("not a key: %s" % s_)
                return
        if src is None:
            s = self.prompt(scr, "CC number (0-119): ")
            if s is None:
                return
            try:
                n = int(s)
            except ValueError:
                n = -1
            if not 0 <= n <= 119:
                self.say("not a controller: %s" % s)
                return
            src = ("cc", n)
        j = self.menu(scr, "route TO", [c[1] for c in LV.CONTROLS])
        if j is None:
            return
        dst = LV.CONTROLS[j][0]
        if src[0] == "cc" and src[1] == dst or src[0] == dst:
            self.say("a control routed to itself does nothing")
            return
        latch = False
        if src[0] == "note" and LV.CONTROL_BY_KEY[dst][2] == "switch":
            h = self.menu(scr, "the key", [
                "held while down (a pedal)",
                "toggle: each press flips it"])
            if h is None:
                return
            latch = (h == 1)
        k = self.menu(scr, "and the original", [
            "replace it (the source stops doing what it did)",
            "keep it (the source does both)"])
        if k is None:
            return
        if learned_ch is not None:
            # The key's own channel is the natural answer; blank keeps it.
            s_ = self.prompt(scr, "listen on channel (blank = %d, 'all' = all): "
                             % (learned_ch + 1))
            if s_ is None:
                return
            ch = learned_ch if s_ == "" else self._channel_of(s_)
        else:
            ch = self.ask_channel(scr, "listen on")
        if ch is False:
            return
        r = LV.Route(src, dst, keep=(k == 1), channel=ch, latch=latch)
        self.live.set_routes(self.live.routes + (r,))
        self.crow = len(self.ctl_rows()) - 1
        self.say("route " + r.describe())

    def del_ctl_row(self):
        row = self.ctl_sel()
        if row is None:
            return
        kind, i = row
        if kind == "ctl":
            c = self.controls().pop(i)
            self.say("removed %s" % LV.CONTROL_BY_KEY[c["key"]][1])
        else:
            rs = list(self.live.routes)
            r = rs.pop(i)
            self.live.set_routes(rs)
            self.say("removed route " + r.describe())

    def bind_hotkey(self, scr):
        row = self.ctl_sel()
        if row is None or row[0] != "ctl":
            self.say("a hotkey belongs to an on-screen control")
            return
        c = self.controls()[row[1]]
        self.say("press the key for %s  (esc: none)" % LV.CONTROL_BY_KEY[c["key"]][1], 30)
        self.draw(scr)
        while True:
            k = scr.getch()
            if k != -1:
                break
        if k == 27:
            c["hotkey"] = None
            self.say("no hotkey")
            return
        ch = chr(k) if 0 < k < 256 else ""
        if ch not in HOTKEYS_FREE:
            self.say("%r is the panel's own key; free: %s"
                     % (ch or k, "".join(sorted(HOTKEYS_FREE))), 6)
            return
        for other in self.controls():
            if other is not c and other.get("hotkey") == ch:
                self.say("%r is already %s" % (ch, LV.CONTROL_BY_KEY[other["key"]][1]), 6)
                return
        c["hotkey"] = ch
        self.say("%r -> %s" % (ch, LV.CONTROL_BY_KEY[c["key"]][1]))

    def ctl_bump(self, delta, big=False):
        row = self.ctl_sel()
        if row is None or row[0] != "ctl":
            return
        c = self.controls()[row[1]]
        kind = LV.CONTROL_BY_KEY[c["key"]][2]
        if kind == "switch":
            if (delta > 0) != self.switch_on(c["key"], c.get("channel")):
                self.fire(c)
            return
        if kind == "selector":
            # a switch of several positions: its next one that way
            import scanner as SCN
            starts = [v for _n, v in SCN.POSITIONS]
            i = max(k for k, v in enumerate(starts) if c.get("value", 0) >= v)
            i = max(0, min(len(starts) - 1, i + (1 if delta > 0 else -1)))
            self.send_control(c, starts[i])
            self.say("%s %s" % (LV.CONTROL_BY_KEY[c["key"]][1], SCN.POSITIONS[i][0]))
            return
        step = (128 if kind == "bend" else 1) * (8 if big else 1)
        self.send_control(c, c.get("value", 0) + delta * step)

    def ctl_space(self):
        row = self.ctl_sel()
        if row is None or row[0] != "ctl":
            return
        c = self.controls()[row[1]]
        _, label, kind, default = LV.CONTROL_BY_KEY[c["key"]]
        if kind == "switch":
            self.fire(c)
        else:
            self.send_control(c, default)
            self.say("%s back to %d" % (label, default))

    def ctl_type(self, scr):
        row = self.ctl_sel()
        if row is None or row[0] != "ctl":
            return
        c = self.controls()[row[1]]
        _, label, kind, default = LV.CONTROL_BY_KEY[c["key"]]
        rng = "-8192..8191" if kind == "bend" else "0-127"
        s = self.prompt(scr, "%s (%s): " % (label, rng))
        if not s:
            return
        try:
            self.send_control(c, int(s))
        except ValueError:
            self.say("not a number: %s" % s)

    def draw_controls(self, scr, y, w, bottom):
        """The pane itself, between the part table and the meters."""
        C = self.C
        L = self.live
        self.rule(scr, y, w, "CONTROLS & ROUTES", self.pane == 2)
        y += 1
        rows = self.ctl_rows()
        sel = self.ctl_sel() if self.pane == 2 else None
        room = max(1, bottom - y - 2)
        top = max(0, min(self.crow - room // 2, len(rows) - room))
        shown = rows[top:top + room]

        def head(txt, hint):
            self.addstr(scr, y, 1, txt, curses.A_BOLD
                        | (C("cyan") if self.pane == 2 else C("dim")))
            self.addstr(scr, y, 16, hint, C("dim"))

        head("on screen", "a add   space toggle   -/+ step   enter value   b hotkey"
             if self.controls() else "none yet -- tab here and press a")
        y += 1
        for r in shown:
            if r[0] != "ctl":
                continue
            c = self.controls()[r[1]]
            key, label, kind, default = LV.CONTROL_BY_KEY[c["key"]]
            here = (r == sel)
            chs = "all" if c.get("channel") is None else str(c["channel"] + 1)
            self.addstr(scr, y, 0, (">" if here else " ") + " %-16s ch %-3s"
                        % (label, chs), curses.A_REVERSE if here else 0)
            if kind == "switch":
                on = self.switch_on(key, c.get("channel"))
                self.addstr(scr, y, 27, " ON " if on else " off",
                            (C("green") | curses.A_BOLD | curses.A_REVERSE) if on
                            else C("dim"))
            elif kind == "selector":
                import scanner as SCN
                pos = SCN.setting_from_cc(c.get("value", default))
                self.addstr(scr, y, 27, " ".join(("[%s]" % n if n == pos else " %s " % n)
                                                 for n, _v in SCN.POSITIONS),
                            C("green") if here else 0)
            else:
                v = c.get("value", default)
                lo, hi = (-8192, 8191) if kind == "bend" else (0, 127)
                self.addstr(scr, y, 27, "%5d %s" % (v, bar(v, lo, hi, 16)),
                            C("green") if here else 0)
            if c.get("hotkey"):
                self.addstr(scr, y, 52, "key %s" % c["hotkey"], C("yellow"))
            y += 1
        head("routes", "r add   d delete  -- a route rewrites the keyboard's own"
             " controls before the engine sees them")
        y += 1
        if not L.routes:
            self.addstr(scr, y, 3, "none: every control means what it says", C("dim"))
            y += 1
        for r in shown:
            if r[0] != "route":
                continue
            here = (r == sel)
            self.addstr(scr, y, 0, (">" if here else " ") + " "
                        + L.routes[r[1]].describe(),
                        curses.A_REVERSE if here else 0)
            y += 1
        return y

    # ---- drawing ------------------------------------------------------------
    def addstr(self, scr, y, x, s, attr=0):
        """curses raises at the last cell of the last line, and on any write off
        the screen. A panel that redraws 20 times a second must not die of a
        window resize."""
        h, w = scr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        try:
            scr.addnstr(y, x, s, max(0, w - x - 1), attr)
        except curses.error:
            pass

    def draw(self, scr):
        scr.erase()
        h, w = scr.getmaxyx()
        L = self.live
        s = L.stats()
        C = self.C
        # THE OUTPUT SECTION SITS ON THE BOTTOM (draw_meters), where it does
        # not move as parts come and go; everything else above it
        bottom = h - 5
        self.draw_header(scr, w, s)
        starting = getattr(L, "starting", False)
        self.rule(scr, 1, w, "PARTS", self.pane == 0,
                  right=("%d part%s" % (len(self.parts()), "" if len(self.parts()) == 1 else "s")))
        y = 2
        hdr = "   #  " + "".join("%-*s" % (COL_W[c], c) for c in COLS)
        self.addstr(scr, y, 0, hdr[:w - 1], C("label"))
        y += 1
        if not self.parts() and starting:
            self.addstr(scr, y, 6, "starting -- the parts appear when they are built", C("dim"))
            y += 1
        for i, p in enumerate(self.parts()):
            if y >= bottom - 6:
                break
            sel = i == self.row
            here = self.pane == 0 and sel
            # the part the other panes act on keeps its mark there, fainter
            self.addstr(scr, y, 0, "\u258c" if sel else " ",
                        C("accent") if here else C("faint"))
            self.addstr(scr, y, 2, "%2d" % (i + 1),
                        (C("accent") | curses.A_BOLD) if here else C("dim"))
            x = 6
            for ci, c in enumerate(COLS):
                txt = self.cell(p, c)
                if p.muted:
                    at = C("dim")
                elif c == "patch":
                    at = self.hue(p)
                else:
                    at = C("text")
                if here and ci == self.col:
                    at = C("sel")
                elif here:
                    at |= curses.A_BOLD
                self.addstr(scr, y, x, "%-*s" % (COL_W[c], txt[:COL_W[c] - 1]), at)
                x += COL_W[c]
            if p.muted:
                self.addstr(scr, y, x, "muted", C("warn"))
            y += 1
            # The full registration goes UNDERNEATH the selected row, not off to
            # the right of it: at x=70 on an 80-column terminal it was clipped
            # clean off the screen, which is no way to show a registration.
            if here and p.organ:
                for ln in self.stops_lines(p, max(20, w - 8)):
                    if y >= bottom - 6:
                        break
                    self.draw_stops_line(scr, y, 6, ln)
                    y += 1
        # THE INSERTION EFFECT: one for the module, the parts on it
        _ef = L.efx
        if _ef['type'] != (0, 0) or L.efx_parts:
            _on = ", ".join(str(c + 1) for c in sorted(L.efx_parts)) or "none"
            self.addstr(scr, y, 6, "EFX", C("accent2") | curses.A_BOLD)
            self.addstr(scr, y, 10, ("%s   channels %s   (X to edit)"
                                     % (GSX.TYPES.get(_ef['type'], "?"), _on))[:w - 12], C("accent2"))
            y += 1

        if self.pane == 2:
            self.draw_controls(scr, y, w, bottom)
        elif self.pane == 3:
            self.draw_synth(scr, y, w, bottom + 4)
        else:
            self.draw_globals(scr, y, w, bottom)
        self.draw_meters(scr, w, h, s)

    def draw_header(self, scr, w, s):
        """The top line: the name, the stream, the eastern tuning, the port,
        and a lamp for the audio thread's scheduling."""
        L, C = self.live, self.C
        self.addstr(scr, 0, 1, "\u25c6 tuning", C("accent") | curses.A_BOLD)
        self.addstr(scr, 0, 12, "%g kHz \u00b7 %d frames \u00b7 %.1f ms"
                    % (L.rate / 1000.0, L.frames, s["budget_ms"]), C("dim"))
        if getattr(L, "eastern", None):
            self.addstr(scr, 0, 46, ("eastern " + L.eastern)[:max(0, w - 90)], C("accent2"))
        rt = s.get("rt") or ""
        lamp = ("\u25cf " + rt) if rt else ""
        lcol = (C("ok") if rt.startswith("RT") else C("warn") if ("dropped" in rt or "refused" in rt)
                else C("dim"))
        pn = self.port_name + ("  " + L.midi2_label if L.midi2_label else "") \
            + ("  " + L.mpe_label() if L.mpe else "")
        xr = w - len(lamp) - 2
        if lamp:
            self.addstr(scr, 0, xr, lamp, lcol)
        self.addstr(scr, 0, max(46, xr - len(pn) - 3), pn[:max(0, xr - 49)], C("dim"))

    def draw_stops_line(self, scr, y, x, ln):
        """A registration line: the stops drawn ([name]) in the accent, the
        rest in grey, their keys dim."""
        import re
        C = self.C
        self.addstr(scr, y, x, ln, C("label"))
        for m in re.finditer(r"\[[^\]]*\]", ln):
            self.addstr(scr, y, x + m.start(), m.group(0), C("accent") | curses.A_BOLD)
        if ln.startswith("stops"):
            self.addstr(scr, y, x, "stops", C("dim"))

    def draw_globals(self, scr, y, w, bottom):
        C = self.C
        y = self.draw_keyboard(scr, y, w, bottom)
        if y >= bottom:
            return y
        self.rule(scr, y, w, "GLOBALS", self.pane == 1)
        y += 1
        half = (len(GLOBALS) + 1) // 2
        for i, (name, unit, lo, hi, step) in enumerate(GLOBALS):
            row = y + (i if i < half else i - half)
            if row >= bottom:
                continue
            v = self.get_global(i)
            here = (self.pane == 1 and i == self.grow)
            col = 0 if i < half else (w // 2)
            self.addstr(scr, row, col + 1, "\u25b8" if here else " ", C("accent"))
            self.addstr(scr, row, col + 3, "%-11s" % name,
                        (C("accent") | curses.A_BOLD) if here else C("label"))
            self.addstr(scr, row, col + 15, "%9s" % fmt(v, unit),
                        C("value") | (curses.A_BOLD if here else 0))
            self.track_bar(scr, row, col + 26, 0.0 if hi <= lo else (v - lo) / (hi - lo), 14,
                           C("accent") if here else C("accent2"))
        return y + half

    # ---- the synth panel (the fourth pane) ----------------------------------
    def synth_part(self):
        """The selected part, if it is a Moog, else None."""
        p = self.sel()
        return p if p is not None and p.moog() is not None else None

    def synth_layer(self, p):
        """The layer the pane edits: B only on a layered voice (moog.layers_of)."""
        return self.slayer if p is not None and self.slayer in MG.layers_of(p.moog()) else 'a'

    def synth_own(self, p):
        """The part's own knobs on the layer being edited."""
        return p.synth if self.synth_layer(p) == 'a' else p.synth_b

    def synth_value(self, p, knob):
        lay = self.synth_layer(p)
        return MG.panel_of(p.moog(), self.synth_own(p), lay)[knob]

    def synth_bump(self, delta, big=False):
        p = self.synth_part()
        if p is None:
            return
        knob, kind = SYNTH_KNOBS[self.srow][1], SYNTH_KNOBS[self.srow][3]
        v = self.synth_value(p, knob)
        steps = SYNTH_STEPS.get(kind)
        if steps:
            # a switch: its next position that way
            i = min(range(len(steps)), key=lambda j: abs(steps[j] - v))
            v = steps[max(0, min(len(steps) - 1, i + (1 if delta > 0 else -1)))]
        else:
            v = max(0.0, min(1.0, v + delta * (0.1 if big else 0.01)))
        self.live.set_synth(p, knob, v, layer=self.synth_layer(p))

    def synth_reset(self):
        """Back to what the patch has it at."""
        p = self.synth_part()
        if p is None:
            return
        knob = SYNTH_KNOBS[self.srow][1]
        lay = self.synth_layer(p)
        self.live.set_synth(p, knob, MG.panel_of(p.moog(), None, lay)[knob], layer=lay)
        self.synth_own(p).pop(knob, None)

    # A KNOB'S ZERO: nothing of it. A level, a time, the cutoff or the pedal's
    # mix to the bottom of its travel; a bipolar knob to its centre detent,
    # where it does nothing either way; a switch off. An octave, a shape or a
    # mode has no zero, and stays where it is.
    SYNTH_CENTRED = ("semi", "oct", "modamt", "lfodepth")

    def synth_zero(self):
        """The selected knob to its zero (space is the patch's setting)."""
        p = self.synth_part()
        if p is None:
            return
        sec, knob, label, kind = SYNTH_KNOBS[self.srow]
        if kind in self.SYNTH_CENTRED:
            v = 0.5
        elif kind == "onoff":
            v = False
        elif kind in SYNTH_STEPS:
            self.say("%s %s has no zero" % (sec, label))
            return
        else:
            v = 0.0
        self.live.set_synth(p, knob, v, layer=self.synth_layer(p))

    def synth_defaults(self):
        """Every knob on this layer back to what the patch has it at."""
        p = self.synth_part()
        if p is None:
            return
        lay = self.synth_layer(p)
        own = self.synth_own(p)
        base = MG.panel_of(p.moog(), None, lay)
        n = len(own)
        for knob in list(own):
            self.live.set_synth(p, knob, base[knob], layer=lay)
            own.pop(knob, None)
        self.say("part %d%s: %d knob%s back to the patch" % (
            self.row + 1, (" layer %s" % lay.upper()) if len(MG.layers_of(p.moog())) > 1 else "",
            n, "" if n == 1 else "s"))

    def synth_switch_layer(self):
        """A layered Moog's other Messenger (B), and back."""
        p = self.synth_part()
        if p is None or len(MG.layers_of(p.moog())) < 2:
            self.say("this voice is one Messenger -- no second layer")
            return
        self.slayer = 'b' if self.synth_layer(p) == 'a' else 'a'
        self.say("editing layer %s%s" % (self.slayer.upper(),
                                         "  (the Messenger plugged in is layer A)" if self.slayer == 'b' else ""))

    def synth_send(self):
        """Set the Messenger to this part's whole panel, now."""
        p = self.synth_part()
        if p is None:
            return
        n = self.live.messenger_sync(p)
        self.say(("part %d: %d CCs to the Messenger" % (self.row + 1, n)) if n
                 else "no Messenger to set (live.py --messenger PORT)")

    def synth_firmware(self):
        """Which firmware's CC chart the Messenger reads and sends: SUB WAVE
        moved from CC11 to CC71 in 1.0.7."""
        L = self.live
        fws = MG.FIRMWARES
        L.messenger_firmware = fws[(fws.index(L.messenger_firmware) + 1) % len(fws)]
        L.dirty = True
        self.say("the Messenger's chart: firmware %s (SUB WAVE on CC%s)"
                 % (L.messenger_firmware, "11" if L.messenger_firmware == "pre-1.0.7" else "71"))

    def synth_hardware(self):
        """Read the Messenger's own CC chart on this part's channel, or stop.
        One channel, named: a part that hears all sixteen cannot read one
        instrument's chart on every one of them. On a part that is not a
        Moog, the knobs turn its sound controllers (moog.MESSENGER_GM)."""
        p = self.sel()
        if p is None or p.drums:
            return
        if p.cc_map == "messenger":
            p.cc_map = "gm"
            self.say("part %d: General MIDI CCs again" % (self.row + 1))
        else:
            p.cc_map = "messenger"
            self.say("part %d reads a Messenger on %s" % (
                self.row + 1, "every channel" if p.channel is None else "channel %d" % (p.channel + 1)))
        self.live.dirty = True

    def draw_synth(self, scr, y, w, h):
        C = self.C
        self.rule(scr, y, w, "SYNTH", self.pane == 3)
        y += 1
        p = self.synth_part()
        if p is None:
            return self.draw_sound_controls(scr, y, w, h)
        _layered = len(MG.layers_of(p.moog())) > 1
        self.addstr(scr, y, 2, ("MOOG MESSENGER %s" % self.synth_layer(p).upper()) if _layered
                    else "MOOG MESSENGER", curses.A_BOLD | C("cyan"))
        self.addstr(scr, y, 20, ("part %d, %s  (layered -- B: the other)" if _layered else "part %d, %s")
                    % (self.row + 1, p.label()), C("dim"))
        hw = (("reads a Messenger on %s  (M: stop)"
               % ("every channel" if p.channel is None else "ch %d" % (p.channel + 1)))
              if p.cc_map == "messenger" else "M: read a Messenger's knobs")
        self.addstr(scr, y, max(50, w - len(hw) - 2), hw[:max(0, w - 52)],
                    C("green") if p.cc_map == "messenger" else C("dim"))
        y += 1
        half = (len(SYNTH_KNOBS) + 1) // 2
        last = [None, None]
        lay = self.synth_layer(p)
        pan = MG.panel_of(p.moog(), self.synth_own(p), lay)
        for i, (sec, knob, label, kind) in enumerate(SYNTH_KNOBS):
            c = 0 if i < half else 1
            row = y + (i if i < half else i - half)
            if row >= h - 4:
                continue
            x = 2 if c == 0 else max(40, w // 2)
            here = i == self.srow
            if sec != last[c]:
                self.addstr(scr, row, x, sec, curses.A_BOLD)
                last[c] = sec
            v = self.synth_value(p, knob)
            own = knob in self.synth_own(p)
            self.addstr(scr, row, x + 7, "%-10s" % label, curses.A_REVERSE if here else 0)
            self.addstr(scr, row, x + 18, "%10s" % synth_fmt(kind, v, pan),
                        (curses.A_BOLD if here else 0) | (C("yellow") if own else 0))
            if kind in self.SYNTH_CENTRED:
                self.addstr(scr, row, x + 29, signed_bar(v, 4), C("green") if here else C("dim"))
            elif kind not in SYNTH_STEPS:
                self.addstr(scr, row, x + 29, bar(v, 0.0, 1.0, 9), C("green") if here else C("dim"))
        # THE MESSENGER THIS PANEL SETS, if one is plugged in (--messenger)
        L = self.live
        row = y + half
        if row < h - 4:
            if L.messenger_port:
                txt = ("sets the Messenger on %s, %s chart  (T: send the panel  F: firmware)"
                       % (L.messenger_port, L.messenger_firmware))
                self.addstr(scr, row, 2, txt[:max(0, w - 4)], C("green"))
            else:
                self.addstr(scr, row, 2, "no Messenger to set (live.py --messenger PORT)"[:max(0, w - 4)],
                            C("dim"))
        return y + half + 2

    def draw_sound_controls(self, scr, y, w, h):
        """A part that is NOT a Moog: what its program answers of CC71-78,
        what each does on this instrument, where it stands on the channel,
        and the Messenger knob that turns it once the part reads one (M)."""
        C = self.C
        p = self.sel()
        if p is None or p.drums:
            self.addstr(scr, y, 2, "a drum part answers only decay -- the synth panel is for "
                        "a melodic part", C("dim"))
            return y + 2
        self.addstr(scr, y, 2, "CONTROLS", curses.A_BOLD | C("cyan"))
        self.addstr(scr, y, 12, "part %d, %s" % (self.row + 1, p.label()), C("dim"))
        reads = p.cc_map == "messenger"
        hw = (("Messenger knobs on %s  (M: stop)"
               % ("every channel" if p.channel is None else "ch %d" % (p.channel + 1)))
              if reads else "M: turn these from a Messenger's knobs")
        self.addstr(scr, y, max(50, w - len(hw) - 2), hw[:max(0, w - 52)],
                    C("green") if reads else C("dim"))
        y += 1
        # THE TWO WHEELS FIRST: what each is on this part (live.wheel_roles,
        # the CC1 branch's own answer), and where it stands
        L = self.live
        ch = 0 if p.channel is None else p.channel
        for name, meaning, at in (
                ("mod", L.mod_wheel_meaning(p), L.wheel_at.get(ch, 0) / 127.0),
                ("pitch", L.pitch_wheel_meaning(p), 0.5 + L.wheel.get(ch, 0) / 16384.0)):
            if y >= h - 4:
                break
            self.addstr(scr, y, 2, "%-5s" % name, C("dim"))
            self.addstr(scr, y, 8, signed_bar(at, 4) if name == "pitch" else bar(at, 0.0, 1.0, 9),
                        C("dim"))
            self.addstr(scr, y, 20, (meaning or "nothing on this voice")[:max(0, w - 22)],
                        0 if meaning else C("dim"))
            y += 1
        rows = self.live.part_controls(p)
        if not rows:
            self.addstr(scr, y, 2, "answers none of CC71-78: set up by its stops, or nothing a "
                        "player's knob reaches", C("dim"))
            return y + 2
        knob_of = {cc: k for k, cc in MG.MESSENGER_GM.items()}
        label = {k: ("%s %s" % (sec, lab)).upper() for sec, k, lab, _ in SYNTH_KNOBS}
        for name, cc, meaning, share, d in rows:
            if y >= h - 4:
                break
            self.addstr(scr, y, 2, "CC%d" % cc, C("dim"))
            self.addstr(scr, y, 8, "%-15s" % meaning, curses.A_BOLD if d else 0)
            self.addstr(scr, y, 24, signed_bar(0.5 + 0.5 * d, 4), C("green") if d else C("dim"))
            self.addstr(scr, y, 35, "%+4.0f" % (64 * d), C("yellow") if d else C("dim"))
            k = knob_of.get(cc)
            txt = (("<- %s" % label.get(k, k)) if k else "<- no Messenger knob")
            if share < 0.999:
                txt += "  (%d%% of the keys)" % round(100 * share)
            self.addstr(scr, y, 42, txt[:max(0, w - 44)],
                        (C("green") if reads else C("dim")) if k else C("dim"))
            y += 1
        return y + 1

    # THE KEYS, per pane: (key, what it does), drawn as a line of hints
    PANE_KEYS = {
        0: (("tab", "pane"), ("\u2191\u2193", "part"), ("\u2190\u2192", "column"), ("-/+", "change"),
            ("\u23ce", "pick"), ("a", "layer"), ("s", "split"), ("d", "del"), ("m", "mute"),
            ("S/L", "preset"), ("N/R", "scene"), ("?", "help"), ("q", "quit")),
        1: (("tab", "pane"), ("\u2191\u2193", "setting"), ("-/+", "change"), ("_/+", "coarse"),
            ("P", "panic"), ("S/L", "preset"), ("?", "help"), ("q", "quit")),
        2: (("tab", "pane"), ("a", "control"), ("r", "route"), ("d", "del"), ("space", "toggle"),
            ("-/+", "step"), ("\u23ce", "value"), ("b", "hotkey"), ("?", "help"), ("q", "quit")),
        3: (("tab", "pane"), ("\u2191\u2193", "knob"), ("-/+", "turn"), ("space", "patch's"),
            ("0", "zero"), ("D", "defaults"), ("B", "layer"), ("M", "Messenger"), ("T", "send"),
            ("?", "help"), ("q", "quit")),
    }

    def draw_meters(self, scr, w, h, s):
        """THE OUTPUT SECTION, on the bottom: the stereo meter in dB (green,
        amber, red; a peak held 1.5 s), the CPU's last seconds as a sparkline,
        the voices, and the health -- quiet unless something went wrong
        lately -- then the message line and the pane's keys."""
        C = self.C
        y = h - 5
        self.rule(scr, y, w, "OUTPUT")
        now = time.monotonic()
        lr = s.get("last_lr") or (s["last_peak"], s["last_peak"])
        # (laid out by the width: a narrow screen's meters and spark shorter)
        mn = 26 if w >= 118 else 12
        for k in (0, 1):
            m = max(lr[k], self._mlev[k] * 0.8)
            self._mlev[k] = m
            if m >= self._mhold[k][0] or now - self._mhold[k][1] > 1.5:
                self._mhold[k] = (m, now)
            self.level_meter(scr, y + 1 + k, 2, "LR"[k], m, self._mhold[k][0], mn)
        pk = s["peak"]
        px = mn + 13
        self.addstr(scr, y + 1, px, "peak", C("label"))
        self.addstr(scr, y + 1, px + 5, ("%+.1f dB" % level_db(pk)) if pk > 1e-6 else "  -inf",
                    C("bad") if pk > 0.99 else C("value"))
        if pk > 0.99:
            self.addstr(scr, y + 2, px, "CLIP", C("bad") | curses.A_BOLD)
        # THE CPU: the slot's share, its worst of each 0.2 s, over ~10 s
        load = s["render_ms"] / max(s["budget_ms"], 1e-9)
        self._cpu_acc = max(self._cpu_acc, load)
        self._cpu_n += 1
        if self._cpu_n >= 4:
            self._cpu_hist.append(self._cpu_acc)
            self._cpu_acc, self._cpu_n = 0.0, 0
        x = px + 15
        sw = max(6, min(self._cpu_hist.maxlen, w - x - 33))
        self.addstr(scr, y + 1, x, "cpu", C("label"))
        cells = [(SPARK[min(7, int(min(1.0, v) * 7.999))],
                  C("ok") if v < 0.5 else C("warn") if v < 0.85 else C("bad")) for v in self._cpu_hist]
        if cells:
            self.runs(scr, y + 1, x + 4, cells[-sw:])
        # FIXED WIDTHS, the engine a word of its own: "gpu" when this block
        # went to the GPU, "cpu" when it did not (the GPU takes a block only
        # above gpu_min occupied slots; or it is off). It was "(gpu)" or "gpu"
        # straight after the figures, and moved as they and it changed length
        fig = "%5.2f/%.2f ms  max %5.1f" % (s["render_ms"], s["budget_ms"], s["render_max"])
        fx = x + 5 + sw
        self.addstr(scr, y + 1, fx, fig, C("bad") if load > 0.85 else C("text"))
        on_gpu = bool(s.get("on_gpu"))
        self.addstr(scr, y + 1, fx + len(fig) + 2, "gpu" if on_gpu else "cpu",
                    (C("accent2") | curses.A_BOLD) if on_gpu else C("dim"))
        if s["threads"] > 1:
            self.addstr(scr, y + 1, fx + len(fig) + 6, "x%d" % s["threads"], C("dim"))
        use = s["used"] / float(max(s["cap"], 1))
        self.addstr(scr, y + 2, x, "voices", C("label"))
        self.addstr(scr, y + 2, x + 7, "%d/%d" % (s["used"], s["cap"]),
                    C("bad") if use > 0.9 else C("text"))
        # THE HEALTH: each count that is not zero, amber (red for the ones
        # that lose notes) for 10 s after it rose, then grey -- a record
        items, fresh = [], False
        for key, lab, worse in (("under", "under", False), ("late", "late", False), ("kicks", "kick", False),
                                ("drop", "drop", True), ("err", "err", True), ("stuck", "stuck", True),
                                ("miss", "miss", True), ("pshed", "shed", False), ("shed", "efx cut", False)):
            v = int(s.get(key) or 0)
            was = self._health.get(key, (0, -1e9))
            if v > was[0]:
                self._health[key] = was = (v, now)
            elif v < was[0]:
                self._health[key] = was = (v, was[1])
            if v:
                recent = now - was[1] < 10.0
                fresh = fresh or recent
                items.append(("%s %d" % (lab, v), (C("bad") if worse else C("warn")) if recent else C("dim")))
        hx = x + 22
        self.addstr(scr, y + 2, hx, "\u25cf", C("warn") if fresh else C("ok"))
        hx += 2
        if not items:
            self.addstr(scr, y + 2, hx, "clean", C("ok"))
        for txt, at in items:
            self.addstr(scr, y + 2, hx, txt, at)
            hx += len(txt) + 2

        # builder / message line
        if self.builder.busy():
            lab = self.builder.label or "building"
            self.addstr(scr, h - 2, 2, "\u25cc %s" % lab, C("accent") | curses.A_BOLD)
            bx = min(w - 30, 6 + len(lab))
            self.track_bar(scr, h - 2, bx, self.builder.frac, 20, C("accent"))
            self.addstr(scr, h - 2, bx + 21, "%d%%" % int(self.builder.frac * 100), C("accent"))
        else:
            # THE NEWEST OF: a build's failure, the engine's last error, a
            # message -- each for its time. The errors latched: neither was
            # ever cleared, so after one, no message showed again all session
            # ("press the key on your keyboard" among them). The health line's
            # err count stays, for the record.
            line = None
            for which, txt in (("build", self.builder.error), ("engine", s["last_error"])):
                was = self._err_seen.get(which)
                if txt and (was is None or was[0] != txt):
                    self._err_seen[which] = was = (txt, now)
                if txt and now - was[1] < self.ERR_SECS and (line is None or was[1] > line[0]):
                    line = (was[1], ("build failed: " if which == "build" else "last error: ") + txt, "bad")
            if now < self.msg_until and (line is None or self.msg_at >= line[0]):
                line = (self.msg_at, self.message, "ok")
            if line is not None:
                self.addstr(scr, h - 2, 2, line[1], C(line[2]))
        x = 1
        for k, what in self.PANE_KEYS.get(self.pane, ()):
            if x + len(k) + len(what) + 2 >= w - 1:
                break
            self.addstr(scr, h - 1, x, k, C("accent"))
            self.addstr(scr, h - 1, x + len(k) + 1, what, C("dim"))
            x += len(k) + len(what) + 4
        if self.help:
            self.draw_help(scr)
        scr.refresh()

    def level_meter(self, scr, y, x, lab, v, hold, n):
        """One side of the stereo meter: dB over METER_FLOOR_DB..0, each cell
        coloured by where it sits (green to -18, amber to -6, red above),
        the held peak a bright tick, the level in figures after it."""
        C = self.C
        fl = METER_FLOOR_DB
        f = max(0.0, min(1.0, (level_db(v) - fl) / -fl))
        hf = max(0.0, min(1.0, (level_db(hold) - fl) / -fl))

        def zone(c):
            top = fl + (-fl) * (c + 1) / n
            return C("ok") if top <= -18.0 else C("warn") if top <= -6.0 else C("bad")
        cells = []
        full = int(f * n)
        for c in range(n):
            if c < full:
                cells.append(("\u2588", zone(c)))
            elif c == full and f * n - full > 0.0:
                cells.append((BAR_EIGHTHS[min(7, int((f * n - full) * 8))], zone(c)))
            else:
                cells.append(("\u00b7", C("faint")))
        hi = min(n - 1, int(hf * n))
        if hold > 1e-6 and hi >= full:
            cells[hi] = ("\u2502", zone(hi) | curses.A_BOLD)
        self.addstr(scr, y, x, lab, C("label"))
        self.runs(scr, y, x + 2, cells)
        self.addstr(scr, y, x + 3 + n, ("%6.1f" % level_db(v)) if v > 1e-6 else "  -inf", C("text"))

    ERR_SECS = 10.0

    def cell(self, p, c):
        if c == "patch":
            return ("-- %s kit" % PM.drum_set_name(p.program) if p.drums
                    else "%3d.%d %s" % (p.program, p.variation, gm_label_short(
                        p.program, COL_W["patch"] - 7, p.variation)) if p.variation
                    else "%3d %s" % (p.program, gm_label_short(p.program, COL_W["patch"] - 5)))
        if c == "ch":
            return "all" if p.channel is None else str(p.channel + 1)
        if c == "lo":
            return note_name(p.lo)
        if c == "hi":
            return note_name(p.hi)
        if c == "tr":
            return "%+d" % p.transpose
        if c == "level":
            return "%+.1f dB" % p.level_db
        if c == "tuner":
            # a part sounding the rig's Eastern tuning says so (E sets it)
            if p.tuner != getattr(p, "base_tuner", p.tuner):
                return "E " + p.tuner.split(":", 1)[1].split("@")[0]
            return p.tuner
        if c == "touch":
            return "fixed" if p.touch_fixed() else "vel"
        if c == "stops":
            if not p.organ:
                return "-"
            return " ".join(r for r in p.patch.stop_display if r in p.drawn) or "none"
        if c == "efx":
            on = self.efx_channels(p) & self.live.efx_parts
            return "-" if not on else ("on" if on == self.efx_channels(p) else "some")
        return ""

    def stops_lines(self, p, width=80):
        """One line per key row, wrapped to the width: each stop with the key
        that toggles it written next to it, and the drawn ones bracketed."""
        lines = []
        for row, names in enumerate(p.patch.stop_row_lines):
            cur = "stops  " if row == 0 else "       "
            i = -1
            for r in names:
                if r == "|":
                    if cur.strip():
                        lines.append(cur.rstrip()); cur = "       "
                    continue
                i += 1
                # rows 2 and 3 are the same keys after the STOP_PREFIX key (or
                # Alt, where the window manager leaves Alt to the terminal)
                k = ((STOP_PREFIX if row >= 2 else "") + STOP_LABELS.get((row % 2, i), "")) if row < 4 else ""
                item = ("%s[%s]" % (k, r)) if r in p.drawn else ("%s %s " % (k, r))
                if len(cur) + len(item) + 1 > width and cur.strip():
                    lines.append(cur.rstrip()); cur = "       "
                cur += item + " "
            lines.append(cur.rstrip())
        return lines

    def stops_str(self, p):
        return "  ".join(self.stops_lines(p, 10 ** 6))

    def draw_keyboard(self, scr, y, w, bottom):
        """THE KEYBOARD: an 88-key piano where the screen is wide enough,
        each key held lit in the hue of the part that answers it (dimmer:
        held by the pedal), and under it each part's zone in its hue. On a
        narrow screen, the zones alone, as a strip."""
        if y >= bottom - 1:
            return y
        self.rule(scr, y, w, "KEYBOARD")
        y += 1
        lo, hi = 21, 108
        whites = [n for n in range(lo, hi + 1) if n % 12 not in BLACK_KEYS]
        if w < 2 * len(whites) + 8:
            return self.draw_zone_strip(scr, y, w, bottom)
        C = self.C
        x0 = max(2, (w - 2 * len(whites)) // 2)
        wi = {n: i for i, n in enumerate(whites)}

        def col(n):                       # a white key's left cell; a black key's one
            n = max(lo, min(hi, n))
            return x0 + (2 * wi[n] if n in wi else 2 * wi[n - 1] + 1)
        held = self.held_keys()
        iv, eb = C("ivory"), C("ebony")
        top = []
        bot = []
        for i, n in enumerate(whites):
            a = held.get(n, iv)
            top += [("\u2588", a), ("\u2588", a)]
            bot += [("\u2588", a), ("\u258c", a)]
        for n in range(lo + 1, hi + 1):
            if n % 12 in BLACK_KEYS:
                top[2 * wi[n - 1] + 1] = ("\u2588", held.get(n, eb))
        self.runs(scr, y, x0, top)
        self.runs(scr, y + 1, x0, bot)
        self.addstr(scr, y + 1, x0 - 3, "A0", C("faint"))
        self.addstr(scr, y + 1, x0 + 2 * len(whites) + 1, "C8", C("faint"))
        y += 2
        for i, p in enumerate(self.parts()):
            if y >= bottom - 1:
                break
            if p.muted:
                continue
            a, b = col(p.lo), col(p.hi) + (1 if max(lo, min(hi, p.hi)) in wi else 0)
            on = i == self.row
            at = self.hue(p) | (0 if on else curses.A_DIM)
            self.addstr(scr, y, a, "\u2501" * max(1, b - a + 1), at)
            nm = ("kit" if p.drums else GM[p.program]) if not p.organ else \
                 ("organ" if p.patch.cres_order else "harmonium")
            self.addstr(scr, y, a + 1, " %d %s " % (i + 1, nm[:max(4, b - a - 4)]), at | curses.A_BOLD)
            y += 1
        return y

    def draw_zone_strip(self, scr, y, w, bottom):
        """The narrow screen's keyboard: which part answers which key, as a
        strip from A0 to C8, a label under each part's span."""
        lo, hi = 21, 108
        width = max(20, min(w - 8, 88))

        def col(n):
            return 4 + int((n - lo) * (width - 1) / float(hi - lo))
        self.addstr(scr, y, 0, "  " + note_name(lo), self.C("faint"))
        self.addstr(scr, y, 4 + width + 1, note_name(hi), self.C("faint"))
        line = [" "] * (width + 1)
        for i, p in enumerate(self.parts()):
            if p.muted:
                continue
            a, b = col(max(lo, p.lo)), col(min(hi, p.hi))
            for x in range(max(0, a - 4), min(width, b - 4) + 1):
                line[x] = "\u2501" if line[x] == " " else "\u254b"     # crossed: layered
        self.addstr(scr, y, 4, "".join(line), self.C("accent2"))
        y += 1
        for i, p in enumerate(self.parts()):
            if p.muted or y >= bottom - 1:
                continue
            a = col(max(lo, p.lo))
            nm = ("kit" if p.drums else GM[p.program].split()[0]) if not p.organ else \
                 ("organ" if p.patch.cres_order else "harmonium")
            self.addstr(scr, y, a, "\u2570 %d %s" % (i + 1, nm),
                        self.hue(p) | (curses.A_BOLD if i == self.row else 0))
            y += 1
        return y

    def draw_help(self, scr):
        lines = [
            "parts",
            "  tab / shift-tab   parts -> globals -> controls and routes -> synth",
            "  up down           select a part          left right  select a column",
            "  - +               change the selected cell   (with shift: coarse)",
            "  enter             acts on the HIGHLIGHTED COLUMN:",
            "                      patch / tuner / stops -> a picker",
            "                      ch, lo, hi, tr, level -> type a value",
            "                      touch -> fixed / vel (enter or - +)",
            "  a                 LAYER: duplicate this part over the same keys",
            "  s                 SPLIT: halve this part's range into two parts",
            "  d                 remove this part        m   mute / unmute",
            "  1..9, shift+1..9  on an organ part, draw or retire that stop",
            "  X (or enter on    THE INSERTION EFFECT (the Sound Canvas's EFX):",
            "   the efx column)    this part on or off it, its type (Roland's",
            "                      families, / searches), each parameter -- heard",
            "                      as you move it; esc puts it back",
            "",
            "touch",
            "  fixed: a harpsichord, organ, harmonium or accordion ignores how",
            "  hard the key goes down -- the jack or the valve sets the level,",
            "  as on the instrument. vel: velocity sets it, as a GM module's",
            "  would. Fixed by default; every other voice always follows",
            "  velocity. (A file render always follows its velocities: there",
            "  they are the mix.)",
            "",
            "stops",
            "  the mod wheel walks the crescendo order, which does NOT contain",
            "  every rank -- the organ's flute 8, bourdon 16, mixture and reeds",
            "  are hand-drawn only. enter on the stops column, or the",
            "  key next to the name under the selected row: the digits for the",
            "  first row, shift and the digit for the second (the reeds); ` and",
            "  then the key for the third and fourth (Alt+digit does it too,",
            "  where the window manager lets Alt through).",
            "",
            "globals",
            "  master            capped at 0 dB: above unity the kernel hard-clips",
            "                    before the soft limiter can see the block",
            "  headroom          applies to NOTES STARTED AFTER IT, not to the mix",
            "  threads           splits the partial table across cores. It only",
            "                    engages when the block is big enough to be worth",
            "                    it; 3 is usually best. Watch the cpu meter.",
            "  gpu               renders the samples on the GPU (OpenCL); the CPU",
            "                    still sets each partial's block up and takes the",
            "                    light ones. The cpu line says which drew the block:",
            "                    gpu (teal) above ~1000 sounding slots, else cpu.",
            "",
            "on-screen controls and routes  (the third pane)",
            "  a                 add a control: any pedal, CC, the wheel, aftertouch,",
            "                    or MONO -- which, switched either way, stops",
            "                    everything the channel is holding (the spec's rule)",
            "  space             a switch: toggle it   anything else: back to default",
            "  - +  enter        step it (shift: by 8)   type a value",
            "  b                 bind a hotkey; it works from EVERY pane. Only keys",
            "                    the panel does not use itself are offered",
            "  r                 route one of the keyboard's controls onto another",
            "                    -- or a KEY: press it, or name it. On a pedal it is",
            "                    held while down, or toggles; on anything else it",
            "                    sets the control from velocity while held",
            "  d                 delete the selected control or route",
            "",
            "  switches LATCH: press to put the pedal down, press again to lift",
            "  it. A terminal never says when a key is let go, so a key cannot be",
            "  held like a pedal. For held-while-pushed, route the pitch wheel:",
            "  past half-way the pedal goes down, back under a fifth it lifts.",
            "  A route REPLACES its source unless you keep it -- the mod wheel",
            "  routed away takes vibrato, drones, drive and rockers with it.",
            "",
            "the synth panel  (the fourth pane: the selected part, if it is a Moog)",
            "  up down           select a knob     - + / left right  turn it",
            "                    (shift: ten times as far); a switch steps",
            "  space             back to where the patch has it",
            "  M                 read a Moog Messenger on the part's channel(s): its",
            "                    knobs turn these (its own CC chart, 14-bit), the",
            "                    wheel, pedal and volume stay General MIDI's",
            "  a knob you have moved shows yellow, and is saved with the part.",
            "  CC74 and CC71 move CUTOFF and RESONANCE, CC73/75/72 the amp",
            "  contour's attack, decay and release -- offsets, as on any synth.",
            "",
            "presets",
            "  S save   L load   -- presets.json, data only; voices live in tonelib.py",
            "  N save   R recall a SCENE: every channel's controls as MIDI events",
            "  E        the EASTERN tuning: a raga system and Sa for every Indian voice",
            "    (volume, pan, expression, CC91, sound controls, tuning, mono --",
            "    not the pedals or the wheel), recalled on top of this setup",
            "  the whole session is saved as you go and resumed next time;",
            "    live.py --fresh starts clean",
            "  a preset carries its on-screen controls and routes too",
            "",
            "  patch and tuner changes build templates on a worker thread;",
            "  everything else takes effect on the next MIDI event.",
            "",
            "  ?  close this        q  quit",
        ]
        h, w = scr.getmaxyx()
        bw = min(w - 4, max(len(x) for x in lines) + 6)
        y0 = max(1, (h - len(lines)) // 2)
        x0 = max(0, (w - bw) // 2)
        self.box(scr, y0 - 1, x0, len(lines) + 2, bw, "help", "? or esc closes")
        for k, ln in enumerate(lines):
            head = bool(ln) and ln[0] != " "
            self.addstr(scr, y0 + k, x0 + 3, ln[:bw - 6],
                        (self.C("accent") | curses.A_BOLD) if head else self.C("text"))

    # ---- input --------------------------------------------------------------
    def key(self, scr, c):
        if self.help:
            self.help = (c not in (ord("?"), 27, ord("q")))
            return True
        if c == ord("q"):
            return False
        if c == 27:
            # ALT+DIGIT is ESC then the digit, and read as two keys it toggled
            # the FIRST row's stop. The next key, if it is a stop key, is the
            # third row's (Alt+digit) or the fourth's (Alt+shift+digit): the
            # church organ's recorded Pitea ranks, bits 14 and up.
            n = scr.getch()
            if 0 < n < 0x110000 and chr(n) in STOP_KEYS:
                row, i = STOP_KEYS[chr(n)]
                self.toggle_stop(i, row + 2)
            return True     # never quit on ESC: a half-read arrow key is an ESC
        # A bound hotkey fires from ANY pane: a pedal you have to tab to first
        # is no pedal. bind_hotkey only ever hands out keys nothing else uses.
        if 0 < c < 256:
            for ctl in self.controls():
                if ctl.get("hotkey") == chr(c):
                    self.fire(ctl)
                    return True
        if c == ord("?"):
            self.help = True
        elif c == 9:                                    # tab
            self.pane = (self.pane + 1) % 4
        elif c == curses.KEY_BTAB:
            self.pane = (self.pane - 1) % 4
        elif c in (curses.KEY_UP, ord("k")):
            if self.pane == 0:
                self.row = max(0, self.row - 1)
            elif self.pane == 1:
                self.grow = max(0, self.grow - 1)
            elif self.pane == 3:
                self.srow = max(0, self.srow - 1)
            else:
                self.crow = max(0, self.crow - 1)
        elif c in (curses.KEY_DOWN, ord("j")):
            if self.pane == 0:
                self.row = min(max(0, len(self.parts()) - 1), self.row + 1)
            elif self.pane == 1:
                self.grow = min(len(GLOBALS) - 1, self.grow + 1)
            elif self.pane == 3:
                self.srow = min(len(SYNTH_KNOBS) - 1, self.srow + 1)
            else:
                self.crow = min(max(0, len(self.ctl_rows()) - 1), self.crow + 1)
        elif self.pane == 3 and c == ord(" "):
            self.synth_reset()
        elif self.pane == 3 and c == ord("M"):
            self.synth_hardware()
        elif self.pane == 3 and c == ord("T"):
            self.synth_send()
        elif self.pane == 3 and c == ord("B"):
            self.synth_switch_layer()
        elif self.pane == 3 and c == ord("0"):
            self.synth_zero()
        elif self.pane == 3 and c == ord("D"):
            self.synth_defaults()
        elif self.pane == 3 and c == ord("F"):
            self.synth_firmware()
        elif self.pane == 2 and c in (ord("a"), ord("r"), ord("d"), ord("b"),
                                      ord(" "), 10, 13):
            if c == ord("a"):
                self.add_control(scr)
            elif c == ord("r"):
                self.add_route(scr)
            elif c == ord("d"):
                self.del_ctl_row()
            elif c == ord("b"):
                self.bind_hotkey(scr)
            elif c == ord(" "):
                self.ctl_space()
            else:
                self.ctl_type(scr)
        elif c in (curses.KEY_LEFT, ord("h")):
            if self.pane == 0:
                self.col = max(0, self.col - 1)
            else:
                self.bump(-1)
        elif c in (curses.KEY_RIGHT, ord("l")):
            if self.pane == 0:
                self.col = min(len(COLS) - 1, self.col + 1)
            else:
                self.bump(1)
        elif c in (ord("-"), ord("_")):
            self.bump(-1, big=(c == ord("_")))
        elif c in (ord("="), ord("+")):
            self.bump(1, big=(c == ord("+")))
        elif c in (10, 13):
            if self.pane == 0:
                self.enter(scr)
        elif c == ord("a"):
            self.add_part()
        elif c == ord("s"):
            self.split_here()
        elif c == ord("d"):
            self.del_part()
        elif c == ord("m"):
            p = self.sel()
            if p is not None:
                p.muted = not p.muted
                if p.muted:
                    # A muted part must not leave its notes droning: they will
                    # never get a note-off it answers. ASKED FOR, not done here
                    # -- the slab has one writer and this is not it.
                    self.live.release_part(p.pid)
        elif c == ord("N"):
            self.save_scene(scr)
        elif c == ord("R"):
            self.recall_scene(scr)
        elif c == ord("S"):
            self.save_preset(scr)
        elif c == ord("L"):
            self.load_preset(scr)
        elif c == ord("E"):
            self.pick_eastern(scr)
        elif c == ord("X"):
            self.pick_efx(scr)
        elif c == ord("P"):
            # panic, the one thing you want when something drones
            self.live.panic()
            self.say("all notes off")
        elif c == ord(STOP_PREFIX):
            # THE THIRD AND FOURTH STOP ROWS WITHOUT ALT: Alt+digit reaches
            # them, but a window manager that keeps Alt for itself never lets it
            # through (Ben: "the alt key is taken by the window manager, so I
            # can't select half the stops"). The prefix, then the stop key.
            self.stop_bank = not getattr(self, "stop_bank", False)
            self.say("stops: rows 3 and 4 -- press a stop key" if self.stop_bank else "stops: rows 1 and 2")
        elif 0 < c < 0x110000 and chr(c) in STOP_KEYS:
            row, i = STOP_KEYS[chr(c)]
            if getattr(self, "stop_bank", False):
                self.stop_bank = False
                row += 2
            self.toggle_stop(i, row)
        return True

    def bump(self, delta, big=False):
        if self.pane == 0:
            self.adjust(delta, big)
        elif self.pane == 2:
            self.ctl_bump(delta, big)
        elif self.pane == 3:
            self.synth_bump(delta, big)
        else:
            name, unit, lo, hi, step = GLOBALS[self.grow]
            self.set_global(self.grow, self.get_global(self.grow)
                            + delta * step * (5 if big else 1))

    # ---- main loop ----------------------------------------------------------
    def loop(self, scr):
        curses.curs_set(0)
        # keypad(True) EXPLICITLY. curses.wrapper is documented to set it and
        # measurably did not here -- an arrow arrived as the three bytes 27, 91,
        # 66, so every arrow read as ESC and ESC quit the panel. Probed, not
        # assumed: see the keycode probe in the commit message.
        scr.keypad(True)
        scr.timeout(50)                 # 20 Hz redraw; supersedes nodelay
        # ESCAPE AT ONCE: curses holds a bare Esc for ESCDELAY (1000 ms) in
        # case an arrow key's sequence follows -- every Esc in a menu, prompt
        # or the effect editor answered a second late. A terminal sends a
        # sequence's bytes together; 25 ms is plenty to tell them apart.
        try:
            curses.set_escdelay(25)
        except (AttributeError, curses.error):
            pass
        self.init_theme()
        saved = time.monotonic()
        while True:
            self.draw(scr)
            # THE SESSION, saved as it changes: at most every 2 s, here on the
            # TUI thread -- never the audio or the MIDI one.
            if self.live.dirty and time.monotonic() - saved >= 2.0:
                LV.save_session(self.live)
                saved = time.monotonic()
            c = scr.getch()
            if c == -1:
                continue
            if c == curses.KEY_RESIZE:
                # A FULL REPAINT: after a resize curses' record of what is on
                # the screen is stale, and drawing only what changed left the
                # old layout's lines standing among the new (a tmux window
                # resized under the panel: the stops twice, the globals over
                # the meters)
                try:
                    curses.update_lines_cols()
                except AttributeError:
                    pass
                scr.clear()
                continue
            if not self.key(scr, c):
                return
            self.live.dirty = True

    def C(self, name):
        return self._colors.get(name, 0)

    # ---- the look ---------------------------------------------------------
    def init_theme(self):
        """THEME_256's roles as colour pairs where the terminal has 256
        colours, else the eight; and the old names (red, green, yellow,
        cyan, dim) the panes still use, mapped onto the roles."""
        self._colors, self._pairs, self.rich = {}, {}, False
        try:
            curses.start_color(); curses.use_default_colors()
        except curses.error:
            return
        if curses.COLORS >= 256 and curses.COLOR_PAIRS >= 64:
            self.rich = True
            for k, v in THEME_256.items():
                self._colors[k] = self.pair(v)
            self._colors["sel"] = self.pair(THEME_256["onaccent"], THEME_256["accent"])
        else:
            pr = {k: self.pair(c) for k, c in (("red", curses.COLOR_RED), ("green", curses.COLOR_GREEN),
                                               ("yellow", curses.COLOR_YELLOW), ("cyan", curses.COLOR_CYAN))}
            self._colors.update(text=0, value=curses.A_BOLD, label=0, dim=curses.A_DIM,
                                faint=curses.A_DIM, rule=curses.A_DIM, accent=pr["yellow"] | curses.A_BOLD,
                                accent2=pr["cyan"], ok=pr["green"], warn=pr["yellow"], bad=pr["red"],
                                ivory=0, ebony=curses.A_DIM, onaccent=0, sel=curses.A_REVERSE)
        self._colors.update(red=self._colors["bad"], green=self._colors["ok"],
                            yellow=self._colors["warn"], cyan=self._colors["accent2"])

    def pair(self, fg, bg=-1):
        """The colour pair for (fg, bg), made the first time it is asked for."""
        key = (fg, bg)
        got = self._pairs.get(key)
        if got is None:
            n = len(self._pairs) + 1
            try:
                if n >= curses.COLOR_PAIRS:
                    return 0
                curses.init_pair(n, fg, bg)
                got = curses.color_pair(n)
            except (curses.error, AttributeError):   # (no colour: curses not started)
                got = 0
            self._pairs[key] = got
        return got

    def hue(self, p):
        """A part's family hue (FAMILY_HUE): the table, its zone, its notes."""
        if not self.rich:
            return self.C("accent2")
        return self.pair(DRUM_HUE if p.drums else FAMILY_HUE[(p.program // 8) % 16])

    def rule(self, scr, y, w, title=None, on=False, right=None):
        """A section's rule, its title on it -- the accent when it is the pane."""
        self.addstr(scr, y, 0, "\u2500" * (w - 1), self.C("rule"))
        if title:
            self.addstr(scr, y, 2, " %s " % title,
                        (self.C("accent") | curses.A_BOLD) if on else self.C("label"))
        if right:
            self.addstr(scr, y, max(0, w - len(right) - 5), " %s " % right, self.C("dim"))

    def runs(self, scr, y, x, cells):
        """Cells [(char, attr)] as runs of one attr: fewer curses calls (the
        panel's drawing shares the interpreter's lock with the audio)."""
        i, n = 0, len(cells)
        while i < n:
            a = cells[i][1]
            j = i + 1
            while j < n and cells[j][1] == a:
                j += 1
            self.addstr(scr, y, x + i, "".join(c for c, _a in cells[i:j]), a)
            i = j

    def track_bar(self, scr, y, x, f, n, attr):
        """A bar over a faint track: how far, and how far it could go."""
        self.addstr(scr, y, x, "\u2500" * n, self.C("faint"))
        b = _bar(f, n).rstrip(" ")
        if b:
            self.addstr(scr, y, x, b, attr)

    def box(self, scr, top, left, hh, ww, title=None, foot=None):
        """A rounded box, cleared inside: the pickers, the help."""
        R = self.C("rule")
        self.addstr(scr, top, left, "\u256d" + "\u2500" * (ww - 2) + "\u256e", R)
        for y in range(top + 1, top + hh - 1):
            self.addstr(scr, y, left, "\u2502", R)
            self.addstr(scr, y, left + 1, " " * (ww - 2))
            self.addstr(scr, y, left + ww - 1, "\u2502", R)
        self.addstr(scr, top + hh - 1, left, "\u2570" + "\u2500" * (ww - 2) + "\u256f", R)
        if title:
            self.addstr(scr, top, left + 2, (" %s " % title)[:ww - 4], self.C("accent") | curses.A_BOLD)
        if foot:
            self.addstr(scr, top + hh - 1, left + 2, (" %s " % foot)[:ww - 4], self.C("dim"))

    def held_keys(self):
        """{note: attr} of the keys down (bright) and held by the pedal
        (dim), each in the hue of the part that answers it."""
        L = self.live
        for _ in range(3):
            try:
                down, ped = list(L.down), list(L.pedalled)
                break
            except RuntimeError:             # (the audio thread changed it mid-copy)
                continue
        else:
            return {}
        parts = [p for p in self.parts() if not p.muted]
        out = {}
        for keys, dim in ((ped, True), (down, False)):
            for k in keys:
                try:
                    ch, n = k[0], k[1]
                except (TypeError, IndexError):
                    continue
                p = next((p for p in parts if (p.channel is None or p.channel == ch)
                          and p.lo <= n <= p.hi), None)
                a = self.hue(p) if p is not None else self.C("accent")
                out[n] = a | (curses.A_DIM if dim else curses.A_BOLD)
        return out


def patch_label(spec):
    if spec.get("drums"):
        return "%s kit" % PM.drum_set_name(spec.get("program", 0))
    p = spec.get("program", 0)
    return gm_label(p, spec.get("bank", 0)) if p < len(GM) else str(p)


# THE MESSENGER'S KNOBS, laid out as its panel is: (section, moog.PANEL name,
# label, how it reads). A kind in SYNTH_STEPS is a switch; the rest turn 0..1.
SYNTH_KNOBS = (
    ("OSC 1", "osc1_octave", "octave", "foot"),
    ("OSC 1", "osc1_wave", "wave", "wave"),
    ("OSC 2", "osc2_octave", "octave", "foot"),
    ("OSC 2", "osc2_wave", "wave", "wave"),
    ("OSC 2", "osc2_freq", "freq", "semi"),
    ("OSC 2", "sync", "sync 1>2", "onoff"),
    ("MOD", "mod_amount", "amount", "modamt"),
    ("MOD", "mod_dest", "dest", "moddest"),
    ("TUNE", "tune", "tune", "semi"),
    ("SUB", "sub_wave", "wave", "subwave"),
    ("MIXER", "osc1_level", "osc 1", "level"),
    ("MIXER", "osc2_level", "osc 2", "level"),
    ("MIXER", "sub_level", "sub", "level"),
    ("MIXER", "noise_level", "noise", "level"),
    ("FILTER", "cutoff", "cutoff", "hz"),
    ("FILTER", "resonance", "resonance", "level"),
    ("FILTER", "eg_amount", "eg amount", "oct"),
    ("FILTER", "kb_track", "kb track", "track"),
    ("FILTER", "mode", "mode", "mode"),
    ("FILTER", "res_bass", "res bass", "onoff"),
    ("F ENV", "f_attack", "attack", "atime"),
    ("F ENV", "f_decay", "decay", "time"),
    ("F ENV", "f_sustain", "sustain", "sustain"),
    ("F ENV", "f_release", "release", "time"),
    ("A ENV", "a_attack", "attack", "atime"),
    ("A ENV", "a_decay", "decay", "time"),
    ("A ENV", "a_sustain", "sustain", "sustain"),
    ("A ENV", "a_release", "release", "time"),
    ("LFO 1", "lfo1_rate", "rate", "lfohz"),
    ("LFO 1", "lfo1_shape", "shape", "lfoshape"),
    ("LFO 1", "lfo1_depth", "depth", "lfodepth"),
    ("LFO 1", "lfo1_dest", "dest", "lfodest"),
    ("LFO 1", "lfo1_reset", "kb reset", "onoff"),
    # THE MF-104M ANALOG DELAY after it (mf104.py): Moog's own echo, saved with
    # the part and its preset like every knob here
    ("MF-104", "mf104_on", "delay", "onoff"),
    ("MF-104", "mf104_time", "time", "mftime"),
    ("MF-104", "mf104_range", "range", "mfrange"),
    ("MF-104", "mf104_feedback", "feedback", "mffb"),
    ("MF-104", "mf104_mix", "mix", "level"),
    ("MF-104", "mf104_rate", "lfo rate", "mfhz"),
    ("MF-104", "mf104_amount", "lfo amount", "mfoct"),
)
SYNTH_STEPS = {"foot": (32, 16, 8, 4), "track": (0.0, 1.0),
               "mode": (0, 1, 2, 3), "onoff": (False, True),
               "lfoshape": (0, 1, 2, 3), "lfodest": (0, 1, 2, 3), "moddest": (0, 1, 2, 3),
               "mfrange": (0, 1)}


def synth_fmt(kind, v, pan=None):
    """A Messenger knob's value, in the panel's own terms (the pedal's TIME
    reads against its RANGE, from the panel `pan`)."""
    if kind == "mftime":
        return "%d ms" % round(1000 * MFD.knob_time(v, int((pan or {}).get("mf104_range", 0))))
    if kind == "mfrange":
        return ("short", "long")[int(v)]
    if kind == "mffb":
        return "%.2f" % MFD.knob_feedback(v)
    if kind == "mfhz":
        return "%.2f Hz" % MFD.knob_rate(v)
    if kind == "mfoct":
        return "%.2f oct" % MFD.knob_amount(v)
    if kind == "foot":
        return "%d'" % int(v)
    if kind == "wave":
        if v < MG.TRI - 1e-9:
            return "fold %d%%" % round(100 * (MG.TRI - v) / MG.TRI)
        for at, nm in ((MG.TRI, "triangle"), (MG.SAW, "saw"), (MG.SQUARE, "square")):
            if abs(v - at) < 1e-9:
                return nm
        if v < MG.SAW:
            return "tri>saw"
        if v < MG.SQUARE:
            return "saw>sq"
        return "pulse %d%%" % round(100 * (0.5 - (0.5 - MG.PULSE_MIN) * (v - MG.SQUARE) / (1 - MG.SQUARE)))
    if kind == "subwave":
        if abs(v - MG.SUB_SQUARE) < 1e-9:
            return "square"
        if v < MG.SUB_SQUARE:
            return "triangle" if v < 1e-9 else "tri>sq"
        return "pulse %d%%" % round(100 * (0.5 - (0.5 - MG.SUB_PULSE_MIN) * (v - MG.SUB_SQUARE) / (1 - MG.SUB_SQUARE)))
    if kind == "semi":
        return "%+.2f st" % MG.bipolar(v, MG.SEMIS)
    if kind == "level":
        return "%.2f" % v
    if kind == "hz":
        f = MG.knob_cutoff(v)
        return ("%.1f kHz" % (f / 1000.0)) if f >= 1000 else "%d Hz" % round(f)
    if kind == "oct":
        return "%+.1f oct" % MG.eg_octaves(v)
    if kind == "track":
        return {0.0: "off", 1.0: "1:1"}.get(round(v, 3), "2/3")
    if kind == "mode":
        return ("4P LP", "2P LP", "BP", "HP")[int(v)]
    if kind == "onoff":
        return "on" if v else "off"
    if kind == "lfohz":
        return "%.2f Hz" % MG.knob_lfo_rate(v)
    if kind == "lfoshape":
        return MG.LFO_SHAPES[int(v)]
    if kind == "lfodepth":                # its reach where it is sent (a cube: moog.lfo_*_octaves)
        dest = int((pan or {}).get("lfo1_dest", 0))
        if dest == 1:
            return "%+.2f oct" % MG.lfo_pitch_octaves(v)
        if dest >= 2:
            return "%+.3f" % MG.lfo_wave_reach(v)
        return "%+.2f oct" % MG.lfo_cut_octaves(v)
    if kind == "lfodest":
        return MG.LFO_DESTS[int(v)]
    if kind == "moddest":
        return MG.MOD_DESTS[int(v)]
    if kind == "modamt":
        return "%+.0f%%" % MG.bipolar(v, 100.0)
    if kind == "sustain":                 # the level it holds: a steep law (moog.sustain_level)
        lv = MG.sustain_level(v)
        return "%.0f%%" % (100.0 * lv) if lv >= 0.005 else "closed"
    if kind in ("time", "atime"):         # an attack has its own law (moog.knob_attack)
        t = MG.knob_attack(v) if kind == "atime" else MG.knob_time(v)
        return ("%.2f s" % t) if t >= 1.0 else "%d ms" % round(t * 1000)
    return str(v)


def fmt(v, unit):
    if unit == "std":
        return STD_NAMES[int(round(v))]
    if unit == "room":
        return LV.ROOM_NAMES[int(round(v))]
    if unit == "x":
        return "%d thread%s" % (int(v), "" if int(v) == 1 else "s")
    if unit == "onoff":
        return "on" if v >= 0.5 else "off"
    if unit == "dB":
        return "%+.1f dB" % v
    if unit == "cents":
        return "%.0f c" % v
    if unit == "%":
        return "+%.0f%%" % (v * 100.0)
    if unit == "st":
        return "%.1f st" % v
    if unit == "bpm":
        return "off" if v <= 0 else "%d bpm" % int(round(v))
    if unit == "ring":
        return "no bell" if v <= 0 else "bell /%d" % int(round(v))
    return "%.2f" % v


# ---- THE LOOK ----------------------------------------------------------------
# A palette of ROLES, not colours: what a thing is -- a label, a value, the
# accent, a warning -- picks how it looks. The 256-colour cube where the
# terminal has it (TUI.init_theme), else the eight colours and attributes.
# Amber on a dark screen, as a hardware unit's display: values bright, their
# labels grey, the rules faint.
THEME_256 = dict(text=252, value=255, label=246, dim=243, faint=238, rule=240,
                 accent=215, accent2=73, ok=114, warn=214, bad=203,
                 ivory=253, ebony=236, onaccent=234)
# THE FAMILIES' HUES, one per GM family of eight (FAMILIES): the parts table,
# the keyboard's zones and the notes held in them, so a split reads at a glance
FAMILY_HUE = (223, 187, 179, 173, 137, 174, 175, 215, 150, 116, 81, 141, 105, 180, 144, 110)
DRUM_HUE = 167
BLACK_KEYS = (1, 3, 6, 8, 10)
SPARK = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
METER_FLOOR_DB = -48.0


def level_db(v):
    import math
    return 20.0 * math.log10(max(float(v), 1e-6))


# THE BARS, at eight steps a cell: recept's bar (../recept/bar.py, bar.js),
# a full block for each whole cell and one of the left-aligned eighths for
# the remainder. A bar growing LEFT (the negative half of a centred knob) has
# no right-aligned eighths to draw with, so, as recept does, its part cell is
# the complement drawn from the left.
BAR_FILL = "\u2588"
BAR_EIGHTHS = (" ", "\u258f", "\u258e", "\u258d", "\u258c", "\u258b", "\u258a", "\u2589")


def _bar(f, n, left=False):
    """A bar n cells wide filled to the fraction f (0..1)."""
    f = max(0.0, min(1.0, f))
    if left:
        f = 1.0 - f
    sn = f * n
    si = min(int(sn), n)
    sr = sn - si
    if si >= n:
        return (" " * n) if left else (BAR_FILL * n)
    if left:
        if sr == 0.0:                       # the edge on a cell boundary: that cell is full
            return " " * si + BAR_FILL * (n - si)
        return " " * si + BAR_EIGHTHS[min(7, int((1.0 - sr) * 8))] + BAR_FILL * (n - si - 1)
    return BAR_FILL * si + BAR_EIGHTHS[min(7, int(sr * 8))] + " " * (n - si - 1)


def bar(v, lo, hi, n):
    return _bar(0.0 if hi <= lo else (v - lo) / (hi - lo), n)


def signed_bar(v, n):
    """A centred knob, v in 0..1 with its detent at 0.5: n cells either side
    of a mark, filling away from it."""
    d = 2.0 * (max(0.0, min(1.0, v)) - 0.5)
    if d >= 0.0:
        return " " * n + "\u2502" + _bar(d, n)
    return _bar(-d, n, left=True) + "\u2502" + " " * n


def run(live, port_name, ump_client=None, start=None):
    """Open audio and MIDI, then hand the terminal to curses. With no
    `port_name` the MIDI arrives some other way -- the ALSA MIDI 2.0 client.
    `start(progress, say, step)`, if given, is the rig's own start (live.main:
    the room, the session, the warming), run as the panel's first build so
    the panel shows at once and the start's progress on it."""
    # STDERR TO A LOG while curses has the screen: what PyAudio, PortAudio or
    # a thread prints there was drawn over and lost (Ben's hang of 2026-10-28
    # left no word). live_stderr.log, next to live_dump.txt, appended per session.
    _log = open(os.path.join(os.path.dirname(os.path.abspath(LV.__file__)), "live_stderr.log"), "a", buffering=1)
    _log.write("==== session %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    sys.stderr.flush()
    _err_fd = os.dup(2)
    os.dup2(_log.fileno(), 2)
    # ...AND BACK, whatever fails: the stream, the MIDI port and the panel are
    # opened inside the try, so a keyboard unplugged or an audio device that
    # will not open says so on the terminal, not only in the log
    pa = stream = port = ui = None
    try:
        pa, stream = LV.open_stream(live, live.rate, live.frames)
        port = mido.open_input(port_name, callback=live.on_midi) if port_name else None
        ui = TUI(live, port_name or ("ALSA %s" % ump_client.address if ump_client else "no MIDI"))
        stream.start_stream()
        if start is not None:
            live.starting = True

            def job(progress):
                try:
                    start(progress, say=lambda m: ui.say(m, 6.0),
                          step=lambda lab: setattr(ui.builder, "label", "starting: " + lab))
                finally:
                    live.starting = False
                    # THE START'S OWN COUNTS GO: hundreds of underruns of
                    # silence while the patches built, read red for the whole
                    # session after (the health line counts what playing does)
                    live.underruns = 0
                    live.cb_ring.late2 = live.cb_ring.late4 = live.cb_ring.over = 0
                    live.render_max = 0.0
                ui.free_hotkeys()        # (the session's controls are in now)
            ui.builder.submit("starting", job)
        else:
            ui.free_hotkeys()
        curses.wrapper(ui.loop)
    except KeyboardInterrupt:
        pass
    finally:
        if ui is not None:
            ui.builder.stop = True
        live.stop_kicker()
        if stream is not None:
            stream.stop_stream(); stream.close()
        if pa is not None:
            pa.terminate()
        sys.stderr.flush()
        os.dup2(_err_fd, 2)
        os.close(_err_fd)
        if port:
            port.close()
        if ump_client:
            ump_client.close()
        LV.save_session(live)             # and once more on the way out
        s = live.stats()
        sys.stderr.write("  peak %.3f  underruns %d  dropped %d  errors %d  "
                         "stuck %d  miss %d  max render %.2f ms\n"
                         % (s["peak"], s["under"], s["drop"], s["err"],
                            s["stuck"], s["miss"], s["render_max"]))
        if s["last_error"]:
            sys.stderr.write("  last error: %s\n" % s["last_error"])
    return 0
