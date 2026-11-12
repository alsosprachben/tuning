#!/usr/bin/env python3
"""The Sound Canvas's display: what a GS file shows on it.

Falcom's and Konami's files (among others) write to the module's own LCD as
they play -- a line of text in the instrument area, and pictures on the 16 x
16 dot matrix the part level bars normally fill. The SC-88 Pro's manual
(Appendix, MODEL ID = 45H, "Display data") gives the messages, a DT1 to
model 45H (F0 41 dev 45 12 aa aa aa data.. sum F7):

  10 00 00  1-32 ASCII (20-7F)   the text: "temporarily displayed in the
                                 INSTRUMENT display area ... If more than 16
                                 characters are received, the display will
                                 automatically be scrolled"
  10 0p 00  64 bytes             dot data, page 2p-1 (p 1-5)
  10 0p 40  64 bytes             dot data, page 2p
  10 20 00  00-0A                the page to show (00 the level bars) for...
  10 20 01  00-0F                ...the display time, 0-7.2 s (0.48 s a
                                 step; 06, 2.88 s, by default)

A page's 64 bytes are its 16 rows in four strips of columns: d00-d15 columns
1-5 (bit 4 the leftmost), d16-d31 columns 6-10, d32-d47 columns 11-15, and
d48-d63 column 16 (bit 4 alone). A page is stored; page 1 is also shown at
once. The text is shown for the display time as well (the manual says only
"temporarily").

Both live engines read these (live._sysex, native/slab.cpp) and both panels
draw them (livetui.draw_display, native/panel.h); the sound is untouched.
"""

PAGES = 10
STEP_S = 0.48               # a display-time step
DEFAULT_TIME = 6            # 2.88 s


def parse(d):
    """A display message's event, or None (not one, or its sum wrong):
    ('text', str), ('dots', p, offset, bytes), ('page', n), ('time', steps).
    d is the exclusive's bytes without F0 and F7."""
    d = tuple(d)
    if len(d) < 9 or d[0] != 0x41 or d[2] != 0x45 or d[3] != 0x12:
        return None
    a, body, cs = d[4:7], d[7:-1], d[-1]
    if (sum(a) + sum(body) + cs) % 128 != 0 or a[0] != 0x10 or not body:
        return None
    if a[1] == 0x00 and a[2] == 0x00:
        return ('text', ''.join(chr(b) for b in body[:32] if 0x20 <= b <= 0x7F))
    if 1 <= a[1] <= 5:
        return ('dots', a[1], a[2], tuple(b & 0x1F for b in body))
    if a[1] == 0x20 and a[2] == 0x00:
        return ('page', min(PAGES, body[0])) if len(body) == 1 else ('page_time', min(PAGES, body[0]), body[1] & 0x0F)
    if a[1] == 0x20 and a[2] == 0x01:
        return ('time', body[0] & 0x0F)
    return None


class Display:
    """The display's state: the dot memory, the display time, and what is
    showing since when (seconds, the caller's clock)."""

    def __init__(self):
        self.mem = {p: [0] * 128 for p in range(1, 6)}
        self.steps = DEFAULT_TIME
        self.text, self.text_at = '', None
        self.page, self.page_at = 0, None

    def apply(self, ev, now):
        kind = ev[0]
        if kind == 'text':
            self.text, self.text_at = ev[1], now
        elif kind == 'dots':
            _, p, off, body = ev
            m = self.mem[p]
            for i, b in enumerate(body):
                if off + i < 128:
                    m[off + i] = b
            if p == 1 and off < 0x40:           # page 1: shown at once
                self.page, self.page_at = 1, now
        elif kind in ('page', 'page_time'):
            if kind == 'page_time':
                self.steps = ev[2]
            self.page, self.page_at = ev[1], now
        elif kind == 'time':
            self.steps = ev[1]

    def hold(self):
        return self.steps * STEP_S

    def page_rows(self, n):
        """Page n (1-10): 16 rows of 16 bools, left to right."""
        m = self.mem[(n + 1) // 2]
        base = 0 if n % 2 else 0x40
        rows = []
        for r in range(16):
            row = []
            for c in range(16):
                s = c // 5
                b = m[base + 16 * s + r]
                row.append(bool(b & (0x10 >> (c % 5))) if s < 3 else bool(b & 0x10))
            rows.append(row)
        return rows

    def showing(self, now):
        """(text or None, page rows or None) on the display now."""
        h = self.hold()
        text = self.text if self.text_at is not None and now - self.text_at < h and self.text else None
        page = (self.page_rows(self.page) if self.page and self.page_at is not None and now - self.page_at < h
                else None)
        return text, page


def text_window(text, since, now, width=16, step=0.3):
    """The text as a 16-character window shows it: scrolled when longer."""
    if len(text) <= width:
        return text
    loop = text + "    "
    k = int(max(0.0, now - since) / step) % len(loop)
    return (loop + loop)[k:k + width]


def half_blocks(rows):
    """16 rows of dots as 8 lines of half-block characters."""
    out = []
    for r in range(0, len(rows), 2):
        top, bot = rows[r], rows[r + 1] if r + 1 < len(rows) else [False] * len(rows[r])
        out.append(''.join('█' if t and b else '▀' if t else '▄' if b else ' '
                           for t, b in zip(top, bot)))
    return out


def timeline(path):
    """A file's display as text: each moment the module would show something
    -- its text, or a dot page drawn in '#' and '.' -- with its time
    (mm:ss.cc) and how long it stays; [] where the file writes nothing to the
    display. Read in the file's own time (mido: its tempo map, its tracks
    merged)."""
    import mido
    d, out, t = Display(), [], 0.0
    for msg in mido.MidiFile(path):
        t += msg.time
        if msg.type != 'sysex':
            continue
        ev = parse(msg.data)
        if ev is None:
            continue
        was = (d.text_at, d.page_at)
        d.apply(ev, t)
        stamp = "[%02d:%05.2f]" % (int(t // 60), t % 60)
        if d.text_at != was[0]:
            out.append("%s text (%.2f s): %s" % (stamp, d.hold(), d.text))
        if d.page_at != was[1]:
            if d.page:
                out.append("%s page %d (%.2f s):" % (stamp, d.page, d.hold()))
                out += ["    " + ''.join('#' if v else '.' for v in row) for row in d.page_rows(d.page)]
            else:
                out.append("%s the level bars" % stamp)
    return out


def write_text(path, out):
    """timeline(path) into the file `out` (a render's sidecar, OUT.display.txt)
    -- nothing written, and nothing left, where the file shows nothing."""
    lines = timeline(path)
    if lines:
        with open(out, "w") as fh:
            fh.write("".join(l + "\n" for l in lines))
    return len(lines)


def selftest():
    def msg(addr, body):
        s = (128 - (sum(addr) + sum(body)) % 128) % 128
        return (0x41, 0x10, 0x45, 0x12) + tuple(addr) + tuple(body) + (s,)
    d = Display()
    ev = parse(msg((0x10, 0, 0), b"Hello"))
    assert ev == ('text', 'Hello'), ev
    d.apply(ev, 0.0)
    assert d.showing(1.0)[0] == 'Hello' and d.showing(3.0)[0] is None
    # page 1: the top-left dot and column 16's top dot, shown at once
    body = [0] * 64
    body[0] = 0x10
    body[48] = 0x10
    body[16 + 15] = 0x01                      # row 16, column 10
    d.apply(parse(msg((0x10, 1, 0), body)), 10.0)
    rows = d.showing(10.5)[1]
    assert rows[0][0] and rows[0][15] and rows[15][9] and sum(map(sum, rows)) == 3
    bad = msg((0x10, 0, 0), b"Hi")
    assert parse(bad[:-1] + ((bad[-1] + 1) % 128,)) is None
    d.apply(parse(msg((0x10, 0x20, 0x01), [0x0F])), 20.0)
    assert abs(d.hold() - 7.2) < 1e-9
    assert len(half_blocks(rows)) == 8 and half_blocks(rows)[0][0] == '▀'
    assert text_window("0123456789abcdefXYZ", 0.0, 0.0) == "0123456789abcdef"
    print("gsdisplay: ok")


if __name__ == "__main__":
    selftest()
