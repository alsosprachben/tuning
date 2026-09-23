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
import percussion_map as PM

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

# Every tuner in midilib.tuner_registry. This list was hand-kept and had drifted
# four entries short of the registry -- hybrid440, the general default, among
# them -- so it is now the registry, in the order the picker wants.
TUNERS = ["hybrid440", "hybrid", "hybridharm", "hybridharm440", "gm2", "even",
          "stretch", "werckmeister", "sankey", "meantone", "just", "pyth",
          "well", "linear", "linear5", "linearwell", "bechstein", "spiral",
          "semi", "dynamic", "path"]

# One line each, so the picker says what a temperament is for rather than only
# what it is called. These are the working notes from midilib/tunelib, not a
# claim about historical practice.
TUNER_NOTE = {
    "hybrid440":  "A=440, the default: the hybrid temperament at concert pitch",
    "hybrid":     "A=415, the same temperament at baroque pitch",
    "hybridharm": "pure 2:1 octaves -- right for mode-locked pipes",
    "hybridharm440": "pure 2:1 octaves at concert pitch",
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
            self.label, self.frac = label, 0.0
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

COLS = ("patch", "ch", "lo", "hi", "tr", "level", "tuner", "stops")
COL_W = {"patch": 24, "ch": 4, "lo": 5, "hi": 5, "tr": 4, "level": 8,
         "tuner": 11, "stops": 11}

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
)

# THE KEYS A PANEL CONTROL MAY BE BOUND TO: everything the panel does not
# already use, in any pane, since a bound key fires from every pane. Space is
# the controls pane's own toggle, so it is not offered.
HOTKEYS_FREE = (set("cefginoptuvwxyz0[];',./")
                | (set("ABCDEFGHIJKMNOQRTUVWXYZ") - set("SLP")))



class TUI:
    def __init__(self, live, port_name):
        self.live = live
        self.port_name = port_name
        self.builder = Builder(); self.builder.start()
        self.row = 0
        self.col = 0
        self.pane = 0           # 0 = parts, 1 = globals, 2 = controls
        self.crow = 0           # selected row in the controls pane
        self.grow = 0           # selected global
        self.meter = 0.0
        self.message = ""
        self.msg_until = 0.0
        self.help = False
        self._colors = {}

    # ---- helpers ------------------------------------------------------------
    def say(self, msg, secs=3.0):
        self.message = msg
        self.msg_until = time.monotonic() + secs

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
                float(L.renderer.K))[i]

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
        else:
            # A new worker pool, swapped in by one atomic assignment. The old
            # one is told to stop; its threads are daemons and exit on their own.
            k = int(round(v))
            if k != L.renderer.K:
                old = L.renderer
                L.renderer = LV.Renderer(L.slab, L.frames, k)
                L.slab.dirty = True
                old.close()

    # ---- edits that need a patch --------------------------------------------
    def rebuild(self, label, specs):
        """Replace the whole part set from a list of spec dicts, off-thread."""
        def job(progress):
            parts = [LV.Part.from_dict(s, progress) for s in specs]
            self.live.set_parts(parts)
        self.builder.submit(label, job)

    def specs(self):
        return [p.to_dict() for p in self.parts()]

    def change_patch(self, delta=None, program=None, drums=None):
        p = self.sel()
        if p is None:
            return
        specs = self.specs()
        s = specs[self.row]
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
                    return
            else:
                n = s["program"] + delta
                if n < 0:
                    s["drums"] = True
                elif n > 127:
                    return
                else:
                    s["program"] = n
        s["drawn"] = []          # a new patch has its own stops
        self.rebuild(patch_label(s), specs)

    def change_tuner(self, delta):
        p = self.sel()
        if p is None:
            return
        specs = self.specs()
        s = specs[self.row]
        i = (TUNERS.index(s["tuner"]) if s["tuner"] in TUNERS else 0) + delta
        s["tuner"] = TUNERS[max(0, min(len(TUNERS) - 1, i))]
        self.rebuild("%s / %s" % (patch_label(s), s["tuner"]), specs)

    def add_part(self):
        specs = self.specs()
        if not specs:
            specs = [dict(program=56, drums=False, tuner="hybrid440", lo=0, hi=127)]
        else:
            specs.insert(self.row + 1, dict(specs[self.row]))
        self.rebuild("layer", specs)
        self.row += 1
        self.say("layered -- same keys, same channel; change its patch or zone")

    def del_part(self):
        specs = self.specs()
        if len(specs) <= 1:
            self.say("the last part cannot be removed")
            return
        specs.pop(self.row)
        self.rebuild("remove part", specs)
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
        specs = self.specs()
        upper = dict(specs[self.row])
        specs[self.row]["hi"] = mid
        upper["lo"] = mid + 1
        specs.insert(self.row + 1, upper)
        self.rebuild("split", specs)
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
        elif col == "stops":
            # -/+ adds and removes ranks in the organ's own crescendo order, so
            # the column behaves like every other one; enter is where you pick
            # ranks by name, including the ones no crescendo reaches.
            if p.organ:
                order = [r for r in p.patch.cres_order] + \
                        [r for r in p.patch.rank_names if r not in p.patch.cres_order]
                k = len([r for r in order if r in p.drawn])
                k = max(1, min(len(order), k + delta))
                self.live.request_stops(p, set(order[:k]))

    def toggle_stop(self, i):
        p = self.sel()
        if p is None or not p.organ:
            return
        names = p.patch.rank_names
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
                self.addstr(scr, h - 1, 0, (label + buf)[:w - 1], curses.A_BOLD)
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

    def menu(self, scr, title, items, start=0):
        """A centred picker. Returns an index, or None if cancelled."""
        scr.keypad(True)
        i = start
        while True:
            h, w = scr.getmaxyx()
            n = min(len(items), max(3, h - 8))
            top = max(0, min(i - n // 2, len(items) - n))
            bw = min(w - 4, max(len(title) + 4, max((len(x) for x in items), default=10) + 8))
            y0 = max(0, (h - n) // 2 - 1)
            x0 = max(0, (w - bw) // 2)
            for y in range(y0 - 1, y0 + n + 2):
                self.addstr(scr, y, x0, " " * bw, curses.A_REVERSE)
            self.addstr(scr, y0 - 1, x0 + 2, title[:bw - 4], curses.A_REVERSE | curses.A_BOLD)
            for k in range(n):
                j = top + k
                mark = ">" if j == i else " "
                txt = " %s %-*s" % (mark, bw - 5, items[j][:bw - 5])
                self.addstr(scr, y0 + k, x0, txt[:bw],
                            curses.A_REVERSE | (curses.A_BOLD if j == i else 0))
            self.addstr(scr, y0 + n + 1, x0 + 2,
                        "enter select   esc cancel"[:bw - 4], curses.A_REVERSE)
            scr.refresh()
            c = scr.getch()
            if c == -1:
                continue
            if c in (curses.KEY_UP, ord("k")):
                i = max(0, i - 1)
            elif c in (curses.KEY_DOWN, ord("j")):
                i = min(len(items) - 1, i + 1)
            elif c == curses.KEY_PPAGE:
                i = max(0, i - n)
            elif c == curses.KEY_NPAGE:
                i = min(len(items) - 1, i + n)
            elif c in (10, 13):
                return i
            elif c == 27 or c == ord("q"):
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
        else:
            self.type_value(scr, col)

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
        start = TUNERS.index(p.tuner) if p.tuner in TUNERS else 0
        pick = self.menu(scr, "temperament for part %d" % (self.row + 1),
                         ["%-12s %s" % (t, TUNER_NOTE.get(t, "")) for t in TUNERS],
                         start)
        if pick is None or TUNERS[pick] == p.tuner:
            return
        specs = self.specs()
        specs[self.row]["tuner"] = TUNERS[pick]
        self.rebuild("%s / %s" % (patch_label(specs[self.row]), TUNERS[pick]), specs)

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
        names = p.patch.rank_names
        cres = set(p.patch.cres_order)
        labels = ["%-9s %s" % (r, "crescendo" if r in cres else "hand-drawn only")
                  for r in names]
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
            bw = min(w - 4, max(len(title) + 6,
                                max((len(x) for x in items), default=10) + 10))
            y0 = max(0, (h - n) // 2 - 1)
            x0 = max(0, (w - bw) // 2)
            for y in range(y0 - 1, y0 + n + 2):
                self.addstr(scr, y, x0, " " * bw, curses.A_REVERSE)
            self.addstr(scr, y0 - 1, x0 + 2, title[:bw - 4],
                        curses.A_REVERSE | curses.A_BOLD)
            for k in range(n):
                j = top + k
                txt = " %s [%s] %-*s" % (">" if j == i else " ",
                                         "x" if j in chosen else " ",
                                         bw - 9, items[j][:bw - 9])
                self.addstr(scr, y0 + k, x0, txt[:bw],
                            curses.A_REVERSE | (curses.A_BOLD if j == i else 0))
            self.addstr(scr, y0 + n + 1, x0 + 2,
                        "space toggle   enter accept   esc cancel"[:bw - 4],
                        curses.A_REVERSE)
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

    def pick_patch(self, scr):
        p = self.sel()
        if p is None:
            return
        # The drum SETS first, by the SC-55's names: on a drum part the program
        # is the set. One not built says so, and plays Standard.
        sets = sorted(PM.DRUM_SETS)
        items = ["-- %s kit" % PM.drum_set_name(k) for k in sets] + \
                ["%3d  %s" % (i, GM[i]) for i in range(len(GM))]
        start = (sets.index(p.program) if p.drums and p.program in sets
                 else 0 if p.drums else len(sets) + p.program)
        pick = self.menu(scr, "patch for part %d" % (self.row + 1), items, start)
        if pick is None:
            return
        if pick < len(sets):
            self.change_patch(drums=True, program=sets[pick])
        else:
            self.change_patch(program=pick - len(sets))

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
        self.addstr(scr, y, 0, "-" * (w - 1), C("dim"))
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
        y = 0

        # header
        self.addstr(scr, y, 1, "tuning", curses.A_BOLD | C("cyan"))
        self.addstr(scr, y, 8, "%d Hz   %d frames   %.1f ms/block"
                    % (L.rate, L.frames, s["budget_ms"]), C("dim"))
        self.addstr(scr, y, max(40, w - len(self.port_name) - 2),
                    self.port_name[:max(0, w - 42)], C("dim"))
        y += 1
        self.addstr(scr, y, 0, "-" * (w - 1), C("dim"))
        y += 1

        # parts
        hdr = "   #  " + "".join("%-*s" % (COL_W[c], c) for c in COLS)
        self.addstr(scr, y, 0, hdr[:w - 1],
                    curses.A_BOLD | (C("cyan") if self.pane == 0 else C("dim")))
        y += 1
        for i, p in enumerate(self.parts()):
            if y >= h - 12:
                break
            here = (self.pane == 0 and i == self.row)
            self.addstr(scr, y, 0, "%s %2d " % (">" if here else " ", i + 1),
                        curses.A_BOLD if here else 0)
            x = 6
            for ci, c in enumerate(COLS):
                txt = self.cell(p, c)
                at = 0
                if here and ci == self.col:
                    at = curses.A_REVERSE
                elif here:
                    at = curses.A_BOLD
                if p.muted:
                    at |= C("dim")
                self.addstr(scr, y, x, "%-*s" % (COL_W[c], txt[:COL_W[c] - 1]), at)
                x += COL_W[c]
            if p.muted:
                self.addstr(scr, y, x, "muted", C("dim"))
            y += 1
            # The full registration goes UNDERNEATH the selected row, not off to
            # the right of it: at x=70 on an 80-column terminal it was clipped
            # clean off the screen, which is no way to show a registration.
            if here and p.organ and y < h - 12:
                self.addstr(scr, y, 6, self.stops_str(p), C("yellow"))
                y += 1
        y += 1

        if self.pane == 2:
            y = self.draw_controls(scr, y, w, h - 6)
        else:
            y = self.draw_globals(scr, y, w, h)

        self.draw_meters(scr, y, w, h, s)

    def draw_globals(self, scr, y, w, h):
        C = self.C
        # keyboard map
        y = self.draw_keyboard(scr, y, w)
        y += 1

        # globals
        self.addstr(scr, y, 0, "-" * (w - 1), C("dim"))
        y += 1
        for i, (name, unit, lo, hi, step) in enumerate(GLOBALS):
            if y >= h - 4:
                break
            v = self.get_global(i)
            here = (self.pane == 1 and i == self.grow)
            half = (len(GLOBALS) + 1) // 2
            col = 0 if i < half else (w // 2)
            row = y + (i if i < half else i - half)
            self.addstr(scr, row, col + 2, "%-11s" % name,
                        curses.A_REVERSE if here else 0)
            self.addstr(scr, row, col + 14, "%8s" % fmt(v, unit),
                        curses.A_BOLD if here else 0)
            self.addstr(scr, row, col + 24, bar(v, lo, hi, 14),
                        C("green") if here else C("dim"))
        y += (len(GLOBALS) + 1) // 2
        return y

    def draw_meters(self, scr, y, w, h, s):
        C = self.C
        L = self.live
        # meters
        self.addstr(scr, y, 0, "-" * (w - 1), C("dim"))
        y += 1
        self.meter = max(s["last_peak"], self.meter * 0.80)
        pk = s["peak"]
        pcol = "red" if pk > 0.99 else ("yellow" if pk > 0.85 else "green")
        self.addstr(scr, y, 2, "out")
        self.addstr(scr, y, 6, bar(self.meter, 0.0, 1.0, 22), C(pcol))
        self.addstr(scr, y, 30, "%.3f  peak %.3f" % (self.meter, pk), C(pcol))
        use = s["used"] / float(s["cap"])
        self.addstr(scr, y, 52, "voices %5d/%d" % (s["used"], s["cap"]),
                    C("red") if use > 0.9 else 0)
        y += 1
        load = s["render_ms"] / max(s["budget_ms"], 1e-9)
        lcol = "red" if load > 0.7 else ("yellow" if load > 0.4 else "dim")
        self.addstr(scr, y, 2, "cpu")
        self.addstr(scr, y, 6, bar(load, 0.0, 1.0, 22), C(lcol))
        self.addstr(scr, y, 30, "%.2f/%.2f ms  max %.2f%s"
                    % (s["render_ms"], s["budget_ms"], s["render_max"],
                       ("  x%d" % s["threads"]) if s["threads"] > 1 else ""), C(lcol))
        ws = L.wheel_state()
        if ws:
            self.addstr(scr, y + 1, 2, "mod")
            self.addstr(scr, y + 1, 6,
                        "wheel %3d%%  vibrato %5.1f-%5.1f c at %4.2f-%4.2f Hz   cc1 x%d last %d"
                        % (int(ws["wheel"] * 100), ws["cents_lo"], ws["cents_hi"],
                           ws["rate_lo"], ws["rate_hi"], ws["cc1"], ws["cc1_last"]),
                        C("cyan") if ws["wheel"] > 0 else C("dim"))
        bad = s["under"] + s["drop"] + s["err"] + s["miss"]
        self.addstr(scr, y, 52, "under %d  drop %d  err %d  stuck %d  miss %d"
                    % (s["under"], s["drop"], s["err"], s["stuck"], s["miss"]),
                    C("red") if bad else C("dim"))
        y += 1

        # builder / message / help line
        if self.builder.busy():
            lab = self.builder.label or "building"
            self.addstr(scr, h - 2, 2, "building %s  %s  %d%%"
                        % (lab, bar(self.builder.frac, 0, 1, 20),
                           int(self.builder.frac * 100)), C("yellow") | curses.A_BOLD)
        elif self.builder.error:
            self.addstr(scr, h - 2, 2, "build failed: " + self.builder.error, C("red"))
        elif s["last_error"]:
            self.addstr(scr, h - 2, 2, "last error: " + s["last_error"], C("red"))
        elif time.monotonic() < self.msg_until:
            self.addstr(scr, h - 2, 2, self.message, C("green"))
        keys = (("tab pane   a control   r route   d del   space toggle   "
                 "-/+ step   enter value   b hotkey   ? help   q quit")
                if self.pane == 2 else
                ("tab pane   arrows move   -/+ change   enter patch   a layer   "
                 "s split   d del   m mute   S/L preset   ? help   q quit"))
        self.addstr(scr, h - 1, 1, keys, C("dim"))
        if self.help:
            self.draw_help(scr)
        scr.refresh()

    def cell(self, p, c):
        if c == "patch":
            return ("-- %s kit" % PM.drum_set_name(p.program) if p.drums
                    else "%3d %s" % (p.program, GM[p.program] if p.program < len(GM) else "?"))
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
            return p.tuner
        if c == "stops":
            if not p.organ:
                return "-"
            return " ".join(r for r in p.patch.rank_names if r in p.drawn) or "none"
        return ""

    def stops_str(self, p):
        """Numbered, so the digit that toggles a rank is written next to it."""
        out = []
        for i, r in enumerate(p.patch.rank_names):
            out.append("%d[%s]" % (i + 1, r) if r in p.drawn else "%d %s " % (i + 1, r))
        return "stops  " + " ".join(out)

    def draw_keyboard(self, scr, y, w):
        """Which part answers which key. The point of a split is that you can see
        it, so this is drawn from the parts themselves rather than described."""
        lo, hi = 21, 108
        width = max(20, min(w - 8, 88))
        def col(n):
            return 4 + int((n - lo) * (width - 1) / float(hi - lo))
        self.addstr(scr, y, 0, " " * (w - 1))
        self.addstr(scr, y, 0, "  " + note_name(lo), self.C("dim"))
        self.addstr(scr, y, 4 + width + 1, note_name(hi), self.C("dim"))
        line = [" "] * (width + 1)
        for i, p in enumerate(self.parts()):
            if p.muted:
                continue
            a, b = col(max(lo, p.lo)), col(min(hi, p.hi))
            for x in range(max(0, a - 4), min(width, b - 4) + 1):
                line[x] = "=" if line[x] == " " else "#"     # # = layered
        self.addstr(scr, y, 4, "".join(line), self.C("cyan"))
        y += 1
        # a label under each part's own span
        for i, p in enumerate(self.parts()):
            if p.muted or y >= scr.getmaxyx()[0] - 12:
                continue
            a = col(max(lo, p.lo))
            nm = ("kit" if p.drums else GM[p.program].split()[0]) if not p.organ else "organ"
            self.addstr(scr, y, a, "|%d %s" % (i + 1, nm),
                        self.C("dim") if i != self.row else self.C("cyan"))
            y += 1
        return y

    def draw_help(self, scr):
        lines = [
            "parts",
            "  tab / shift-tab   parts -> globals -> controls and routes",
            "  up down           select a part          left right  select a column",
            "  - +               change the selected cell   (with shift: coarse)",
            "  enter             acts on the HIGHLIGHTED COLUMN:",
            "                      patch / tuner / stops -> a picker",
            "                      ch, lo, hi, tr, level -> type a value",
            "  a                 LAYER: duplicate this part over the same keys",
            "  s                 SPLIT: halve this part's range into two parts",
            "  d                 remove this part        m   mute / unmute",
            "  1..9              on an organ part, draw or retire that stop",
            "",
            "stops",
            "  the mod wheel walks the crescendo order, which does NOT contain",
            "  every rank -- the reed organ's trumpet and the flue organ's flute",
            "  and mixture are hand-drawn only. enter on the stops column, or the",
            "  digit next to the name under the selected row.",
            "",
            "globals",
            "  master            capped at 0 dB: above unity the kernel hard-clips",
            "                    before the soft limiter can see the block",
            "  headroom          applies to NOTES STARTED AFTER IT, not to the mix",
            "  threads           splits the partial table across cores. It only",
            "                    engages when the block is big enough to be worth",
            "                    it; 3 is usually best. Watch the cpu meter.",
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
            "presets",
            "  S save   L load   -- presets.json, data only; voices live in tonelib.py",
            "  a preset carries its on-screen controls and routes too",
            "",
            "  patch and tuner changes build templates on a worker thread;",
            "  everything else takes effect on the next MIDI event.",
            "",
            "  ?  close this        q  quit",
        ]
        h, w = scr.getmaxyx()
        bw = min(w - 4, max(len(x) for x in lines) + 4)
        y0 = max(0, (h - len(lines)) // 2 - 1)
        x0 = max(0, (w - bw) // 2)
        for k in range(-1, len(lines) + 1):
            self.addstr(scr, y0 + k, x0, " " * bw, curses.A_REVERSE)
        for k, ln in enumerate(lines):
            self.addstr(scr, y0 + k, x0 + 2, ln[:bw - 4],
                        curses.A_REVERSE | (curses.A_BOLD if ln and ln[0] != " " else 0))

    # ---- input --------------------------------------------------------------
    def key(self, scr, c):
        if self.help:
            self.help = (c not in (ord("?"), 27, ord("q")))
            return True
        if c == ord("q"):
            return False
        if c == 27:
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
            self.pane = (self.pane + 1) % 3
        elif c == curses.KEY_BTAB:
            self.pane = (self.pane - 1) % 3
        elif c in (curses.KEY_UP, ord("k")):
            if self.pane == 0:
                self.row = max(0, self.row - 1)
            elif self.pane == 1:
                self.grow = max(0, self.grow - 1)
            else:
                self.crow = max(0, self.crow - 1)
        elif c in (curses.KEY_DOWN, ord("j")):
            if self.pane == 0:
                self.row = min(max(0, len(self.parts()) - 1), self.row + 1)
            elif self.pane == 1:
                self.grow = min(len(GLOBALS) - 1, self.grow + 1)
            else:
                self.crow = min(max(0, len(self.ctl_rows()) - 1), self.crow + 1)
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
        elif c == ord("S"):
            self.save_preset(scr)
        elif c == ord("L"):
            self.load_preset(scr)
        elif c == ord("P"):
            # panic, the one thing you want when something drones
            self.live.panic()
            self.say("all notes off")
        elif ord("1") <= c <= ord("9"):
            self.toggle_stop(c - ord("1"))
        return True

    def bump(self, delta, big=False):
        if self.pane == 0:
            self.adjust(delta, big)
        elif self.pane == 2:
            self.ctl_bump(delta, big)
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
        try:
            curses.start_color(); curses.use_default_colors()
            for i, name in enumerate(("red", "green", "yellow", "cyan")):
                curses.init_pair(i + 1, (curses.COLOR_RED, curses.COLOR_GREEN,
                                         curses.COLOR_YELLOW, curses.COLOR_CYAN)[i], -1)
            self._colors = {"red": curses.color_pair(1), "green": curses.color_pair(2),
                            "yellow": curses.color_pair(3), "cyan": curses.color_pair(4),
                            "dim": curses.A_DIM}
        except curses.error:
            self._colors = {}
        while True:
            self.draw(scr)
            c = scr.getch()
            if c == -1:
                continue
            if c == curses.KEY_RESIZE:
                continue
            if not self.key(scr, c):
                return

    def C(self, name):
        return self._colors.get(name, 0)


def patch_label(spec):
    if spec.get("drums"):
        return "%s kit" % PM.drum_set_name(spec.get("program", 0))
    p = spec.get("program", 0)
    return GM[p] if p < len(GM) else str(p)


def fmt(v, unit):
    if unit == "x":
        return "%d thread%s" % (int(v), "" if int(v) == 1 else "s")
    if unit == "dB":
        return "%+.1f dB" % v
    if unit == "cents":
        return "%.0f c" % v
    if unit == "%":
        return "+%.0f%%" % (v * 100.0)
    if unit == "st":
        return "%.1f st" % v
    return "%.2f" % v


def bar(v, lo, hi, n):
    f = 0.0 if hi <= lo else max(0.0, min(1.0, (v - lo) / (hi - lo)))
    k = int(round(f * n))
    return "#" * k + "-" * (n - k)


def run(live, port_name):
    """Open audio and MIDI, then hand the terminal to curses."""
    pa, stream = LV.open_stream(live, live.rate, live.frames)
    port = mido.open_input(port_name, callback=live.on_midi)
    ui = TUI(live, port_name)
    stream.start_stream()
    try:
        curses.wrapper(ui.loop)
    except KeyboardInterrupt:
        pass
    finally:
        ui.builder.stop = True
        stream.stop_stream(); stream.close(); pa.terminate(); port.close()
        s = live.stats()
        sys.stderr.write("  peak %.3f  underruns %d  dropped %d  errors %d  "
                         "stuck %d  miss %d  max render %.2f ms\n"
                         % (s["peak"], s["under"], s["drop"], s["err"],
                            s["stuck"], s["miss"], s["render_max"]))
        if s["last_error"]:
            sys.stderr.write("  last error: %s\n" % s["last_error"])
    return 0
