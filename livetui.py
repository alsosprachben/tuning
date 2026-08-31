#!/usr/bin/env python3
"""A synthesiser interface for live.py.

The engine is multi-timbral (see live.Part); this is the panel that drives it.
curses, from the standard library, because the repo has no UI dependency and
should not grow one for this.

TWO KINDS OF EDIT, and the difference is the whole design:

  - CHEAP edits -- channel, key range, transpose, level, mute, stops -- are a
    single attribute write on a live Part. They take effect on the next MIDI
    event, and they happen inline.

  - EXPENSIVE edits -- program, drums, tuner -- need a Bank, which is 0.02-0.67 s
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

TUNERS = ["hybrid", "hybridharm", "even", "stretch", "meantone", "just", "pyth",
          "well", "linear", "linear5", "linearwell", "bechstein", "spiral",
          "semi", "dynamic", "path"]

# One line each, so the picker says what a temperament is for rather than only
# what it is called. These are the working notes from midilib/tunelib, not a
# claim about historical practice.
TUNER_NOTE = {
    "hybrid":     "A=441, the default for most of this work",
    "hybridharm": "pure 2:1 octaves -- right for mode-locked pipes",
    "even":       "equal temperament, A=415",
    "stretch":    "equal, with the piano's stretched octaves",
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
    "dynamic":    "retunes as it plays, by common tone",
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

    def progress(self, bank, frac):
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

GLOBALS = (
    ("master",     "dB",   -60.0,  0.0, 0.5),
    ("headroom",   "dB",     0.0, 24.0, 0.5),
    ("limiter",    "",       0.10, 1.00, 0.02),
    ("bend range", "st",     0.0, 24.0, 0.5),
    ("mod depth",  "cents",  0.0, 200.0, 5.0),
    ("aftertouch", "dB",     0.0, 24.0, 0.5),
    ("at tilt",    "",       0.0,  1.5, 0.05),
    ("threads",    "x",      1.0,  8.0, 1.0),
)


class TUI:
    def __init__(self, live, port_name):
        self.live = live
        self.port_name = port_name
        self.builder = Builder(); self.builder.start()
        self.row = 0
        self.col = 0
        self.pane = 0           # 0 = parts, 1 = globals
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
                L.mod_cents, L.press_db, L.press_tilt,
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
            L.press_db = v
        elif i == 6:
            L.press_tilt = v
        else:
            # A new worker pool, swapped in by one atomic assignment. The old
            # one is told to stop; its threads are daemons and exit on their own.
            k = int(round(v))
            if k != L.renderer.K:
                old = L.renderer
                L.renderer = LV.Renderer(L.slab, L.frames, k)
                L.slab.dirty = True
                old.close()

    # ---- edits that need a bank --------------------------------------------
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
            specs = [dict(program=56, drums=False, tuner="hybrid", lo=0, hi=127)]
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
            p.level_db = max(-60.0, min(12.0, p.level_db + delta * (3.0 if big else 0.5)))
        elif col == "stops":
            # -/+ adds and removes ranks in the organ's own crescendo order, so
            # the column behaves like every other one; enter is where you pick
            # ranks by name, including the ones no crescendo reaches.
            if p.organ:
                order = [r for r in p.bank.cres_order] + \
                        [r for r in p.bank.rank_names if r not in p.bank.cres_order]
                k = len([r for r in order if r in p.drawn])
                k = max(1, min(len(order), k + delta))
                self.live.set_stops(p, set(order[:k]))

    def toggle_stop(self, i):
        p = self.sel()
        if p is None or not p.organ:
            return
        names = p.bank.rank_names
        if not 0 <= i < len(names):
            return
        want = set(p.drawn)
        want.symmetric_difference_update({names[i]})
        self.live.set_stops(p, want)

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
            p.level_db = max(-60.0, min(12.0, v))

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
        names = p.bank.rank_names
        cres = set(p.bank.cres_order)
        labels = ["%-9s %s" % (r, "crescendo" if r in cres else "hand-drawn only")
                  for r in names]
        got = self.multi_menu(scr, "stops for part %d" % (self.row + 1), labels,
                              {i for i, r in enumerate(names) if r in p.drawn})
        if got is None:
            return
        self.live.set_stops(p, {names[i] for i in got})

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
        items = ["-- drum kit (GM percussion)"] + \
                ["%3d  %s" % (i, GM[i]) for i in range(len(GM))]
        start = 0 if p.drums else p.program + 1
        pick = self.menu(scr, "patch for part %d" % (self.row + 1), items, start)
        if pick is None:
            return
        if pick == 0:
            self.change_patch(drums=True)
        else:
            self.change_patch(program=pick - 1)

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
        keys = ("tab pane   arrows move   -/+ change   enter patch   a layer   "
                "s split   d del   m mute   S/L preset   ? help   q quit")
        self.addstr(scr, h - 1, 1, keys, C("dim"))
        if self.help:
            self.draw_help(scr)
        scr.refresh()

    def cell(self, p, c):
        if c == "patch":
            return ("-- drum kit" if p.drums
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
            return " ".join(r for r in p.bank.rank_names if r in p.drawn) or "none"
        return ""

    def stops_str(self, p):
        """Numbered, so the digit that toggles a rank is written next to it."""
        out = []
        for i, r in enumerate(p.bank.rank_names):
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
            "  tab / shift-tab   move between the part table and the controls",
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
            "controls",
            "  master            capped at 0 dB: above unity the kernel hard-clips",
            "                    before the soft limiter can see the block",
            "  headroom          applies to NOTES STARTED AFTER IT, not to the mix",
            "  threads           splits the partial table across cores. It only",
            "                    engages when the block is big enough to be worth",
            "                    it; 3 is usually best. Watch the cpu meter.",
            "",
            "presets",
            "  S save   L load   -- presets.json, data only; voices live in tonelib.py",
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
        if c == ord("?"):
            self.help = True
        elif c == 9:                                    # tab
            self.pane = 1 - self.pane
        elif c == curses.KEY_BTAB:
            self.pane = 1 - self.pane
        elif c in (curses.KEY_UP, ord("k")):
            if self.pane == 0:
                self.row = max(0, self.row - 1)
            else:
                self.grow = max(0, self.grow - 1)
        elif c in (curses.KEY_DOWN, ord("j")):
            if self.pane == 0:
                self.row = min(max(0, len(self.parts()) - 1), self.row + 1)
            else:
                self.grow = min(len(GLOBALS) - 1, self.grow + 1)
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
                    # never get a note-off it answers.
                    for k in [k for k in list(self.live.slab.live) if k[0] == p.pid]:
                        self.live.slab.oneshot.pop(k, None)
                        self.live.slab.release(k, self.live.n)
        elif c == ord("S"):
            self.save_preset(scr)
        elif c == ord("L"):
            self.load_preset(scr)
        elif c == ord("P"):
            # panic, the one thing you want when something drones
            for k in list(self.live.slab.live):
                self.live.slab.oneshot.pop(k, None)
                self.live.slab.release(k, self.live.n)
            self.live.down.clear(); self.live.pedalled.clear()
            self.say("all notes off")
        elif ord("1") <= c <= ord("9"):
            self.toggle_stop(c - ord("1"))
        return True

    def bump(self, delta, big=False):
        if self.pane == 0:
            self.adjust(delta, big)
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
        return "drum kit"
    p = spec.get("program", 0)
    return GM[p] if p < len(GM) else str(p)


def fmt(v, unit):
    if unit == "x":
        return "%d thread%s" % (int(v), "" if int(v) == 1 else "s")
    if unit == "dB":
        return "%+.1f dB" % v
    if unit == "cents":
        return "%.0f c" % v
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
