"""The streaming file renderer: partials emitted note by note, rendered a window
at a time, so memory follows how many partials sound at once, not how long the
piece is.

blockrender.prepare() builds every partial of a piece before rendering a
sample, and Valkyries' table (16M partials) overflows a 7 GB machine. Its note
loop already runs in one global onset order and no note reads another's rows,
so prepare(..., sink=) hands each note's rows to a sink the moment they are
final -- when the next note flushes its sound controllers -- and the sink may
let them go.

This module grows in phases (see the plan): first the column that can drop its
past, and a counting sink that measures a piece's live partials without ever
holding its table.
"""
import os
from array import array

import numpy as np

# TUNING_STREAM_STATS=1: the store's rows held against still to sound, each window
_STATS = os.environ.get("TUNING_STREAM_STATS", "") not in ("", "0")


class PrefixCol:
    """A table column that can let go of its first rows.

    Indexed by GLOBAL row number, as the plain column it stands in for: len()
    is every row ever appended, A[k][i] and A[k][i0:i1] address rows by their
    place in the whole table -- which is how prepare()'s note loop addresses
    the note it is finishing. drop_to(k) frees every row before k. Stored in
    the same array type the plain column uses (blockrender._dcol), so a value
    rounds exactly as it would have."""

    __slots__ = ("a", "base", "append", "extend")

    def __init__(self, typecode):
        self.a = array(typecode)
        self.base = 0
        # the array's own methods, not a Python method around them: the note
        # loop appends tens of millions of values, and a wrapper call each
        # was a fifth of a streamed file's emission. drop_to deletes from the
        # same array, so these stay bound to it.
        self.append = self.a.append
        self.extend = self.a.extend

    def __len__(self):
        return self.base + len(self.a)

    def _i(self, i):
        if i < 0:
            i += len(self)
        if i < self.base:
            raise IndexError("row %d was already let go (the column starts at %d)" % (i, self.base))
        return i - self.base

    def __getitem__(self, i):
        if isinstance(i, slice):
            start, stop, step = i.indices(len(self))
            return self.a[self._i(start):stop - self.base:step]
        return self.a[self._i(i)]

    def __setitem__(self, i, v):
        if isinstance(i, slice):
            raise TypeError("PrefixCol: slice assignment is not used by the note loop")
        self.a[self._i(i)] = v

    def rows(self, i0, i1):
        """Rows [i0, i1) as a numpy array (a copy)."""
        return np.array(self.a[self._i(i0):i1 - self.base])

    def drop_to(self, k):
        """Let go of every row before k."""
        n = k - self.base
        if n > 0:
            del self.a[:n]
            self.base = k


def zend(rows, blk):
    """Where the kernel stops rendering each row (voice_partial.inc):
    noff + (long)relS + ceil(max(0, delL, delR)) + BLK."""
    dl = np.maximum(0.0, np.maximum(rows['delL'], rows['delR']))
    return (rows['noff'].astype(np.int64) + rows['re'].astype(np.float32).astype(np.int64)
            + np.ceil(dl).astype(np.int64) + blk)


class LiveCount:
    """A sink that measures, and keeps nothing: for every window of `w`
    samples, how many rows are live in it (onset before its end, kernel end
    after its start), from each note's rows as they are finished -- then lets
    them go. Memory is one note's rows and a histogram."""

    COLS = ("non", "noff", "re", "delL", "delR")

    def __init__(self, blk, w):
        self.blk, self.w = blk, w
        self.starts = {}          # window -> rows whose onset falls in it
        self.ends = {}            # window -> rows whose last window is it
        self.rows = 0
        self.notes = 0

    def __call__(self, A, i0, i1, next_on=None):
        if i1 > i0:
            r = {k: A[k].rows(i0, i1) for k in self.COLS}
            first = r['non'].astype(np.int64) // self.w
            last = (zend(r, self.blk) - 1) // self.w
            for d, k in ((self.starts, first), (self.ends, last)):
                u, c = np.unique(k, return_counts=True)
                for a, b in zip(u.tolist(), c.tolist()):
                    d[a] = d.get(a, 0) + b
            self.rows += i1 - i0
        self.notes += 1
        for k in A.values():
            k.drop_to(i1)

    def live(self):
        """Rows live in each window, from the first to the last."""
        if not self.starts:
            return np.zeros(0, np.int64)
        n = max(max(self.starts), max(self.ends)) + 1
        s = np.zeros(n + 1, np.int64); e = np.zeros(n + 1, np.int64)
        for a, b in self.starts.items():
            s[a] += b
        for a, b in self.ends.items():
            e[a + 1] += b
        return np.cumsum(s - e)[:n]


class WavOut:
    """A stereo WAV written as it renders, window by window -- the bytes
    blockrender.write_wav would write for the whole (32-bit, clipped,
    converted sample by sample)."""

    def __init__(self, path, sr):
        import wave
        self.w = wave.open(path, 'wb')
        self.w.setnchannels(2); self.w.setsampwidth(4); self.w.setframerate(sr)
        self.n = 0

    def write(self, L, R):
        st = np.empty(len(L) * 2, np.float64); st[0::2] = L; st[1::2] = R
        self.w.writeframes((np.clip(st, -1, 1) * 2147483647.0).astype('<i4').tobytes())
        self.n += len(L)

    def close(self):
        self.w.close()


class WavOutMono(WavOut):
    """blockrender.write_wav_mono's bytes, window by window."""

    def __init__(self, path, sr):
        import wave
        self.w = wave.open(path, 'wb')
        self.w.setnchannels(1); self.w.setsampwidth(4); self.w.setframerate(sr)
        self.n = 0

    def write(self, L, R=None):
        self.w.writeframes((np.clip(L, -1, 1) * 2147483647.0).astype('<i4').tobytes())
        self.n += len(L)


class NotStreamable(Exception):
    """The file needs something the stream does not reproduce: render it whole."""


class NeedLoudest(Exception):
    """A Leslie channel appeared: its sidebands need the whole file's loudest
    row, which a first, scanning run of the stream finds."""


# THE ORDER KEY. Every row carries its place in the whole table as a padded
# int64 vector, compared lexicographically, so a window's rows sort into the
# order prepare() would have left them in -- the order the kernel sums in.
#
#   note row           (0, row, 0, 0)
#   sympathetic copy   (1, channel rank, the group's first row, responder) + source
#   MF-104 repeat      (2, 0, 0, 0) + source + (repeat,)
#   amplifier product  (3, channel rank, the segment's start, product)
#   harmonium tremolo  (4, 0, 0, 0) + source + (sign,)
#   tremolo sideband   (5, 0, 0, 0) + source + (sign,)
#   chorus copy        (6, channel rank, cents index, 0) + source
#   Leslie sideband    (7, 0, 0, 0) + source + (lobe harmonic, sign)
#
# "+ source" is the source row's whole key: each pass walks the table in its
# order and appends at its end, so the table orders a pass's rows by these
# fields, in this nesting. Padding is -1; no row's key is a prefix of another's.
KW = 48


def _key(level0, src, slen, trail=None):
    """Keys for new rows: level0 (n, 4), then each source's key (its first
    slen fields), then `trail` (n, t). Returns (keys, lengths)."""
    n = len(level0)
    t = 0 if trail is None else trail.shape[1]
    width = 4 + (int(slen.max()) if n else 0) + t     # as wide as used: padding costs sorts
    keys = np.full((n, width), -1, np.int64)
    keys[:, :4] = level0
    lens = np.empty(n, np.int64)
    for L in np.unique(slen):
        m = slen == L
        if 4 + L + t > KW:
            raise RuntimeError("order key too deep (%d fields)" % (4 + L + t))
        keys[m, 4:4 + L] = src[m, :L]
        if t:
            keys[m, 4 + L:4 + L + t] = trail[m]
        lens[m] = 4 + L + t
    return keys, lens


def _fbits(x):
    """A non-negative float as an int64 that sorts as the float does."""
    return np.asarray(x, np.float64).view(np.int64)


def _take(r, ix):
    return {k: v[ix] for k, v in r.items()}


def _cat(parts):
    parts = [p for p in parts if p is not None and len(p['om'])]
    if not parts:
        return None
    out = {}
    for k in parts[0]:
        if k == 'key':                  # keys of different widths: padded with -1
            w = max(p['key'].shape[1] for p in parts)
            out[k] = np.concatenate([p[k] if p[k].shape[1] == w else
                                     np.pad(p[k], ((0, 0), (0, w - p[k].shape[1])), constant_values=-1)
                                     for p in parts])
        else:
            out[k] = np.concatenate([p[k] for p in parts])
    return out


def _lobe_fill(c):
    """A chunk with the Leslie's lobe columns: as it is, or on no rotor (one
    finished before the first Leslie row)."""
    if 'lsr' in c:
        return c
    import leslie as LE
    n = len(c['om'])
    return dict(c, **{k: np.full(n, v, dt) for k, dt, v in LE.LOBE_COLS})


def _mini(r, cols):
    """Rows as the lists a pass's expand() works on, in the whole table's order."""
    return {k: r[k].tolist() for k in cols}


def _appended(mini, r, cols, n0):
    """The rows a pass appended to `mini`, as arrays of the columns' own types
    (a float32 column rounds, as the whole table's typed column does on append)."""
    return {k: np.array(mini[k][n0:], dtype=r[k].dtype) for k in cols}


class Stream:
    """prepare(..., sink=Stream()) renders the file as its notes are emitted.

    The passes run as they do on the whole table, and in its order, each as
    soon as nothing to come can change what it sees:

      1. sympathetic strings: an onset bucket once no later note can join it;
      2. MF-104 repeats: a note's, once its buckets are done (the strings copy
         its rows before the pedal dries them);
      3. the amplifier: a segment of a channel once no row still to come can
         start before it ends -- from its own copy of the rows it reads;
      4. clavinet tone, harmonium tremolo, tremolo, chorus, cabinet and the
         Leslie, row by row, on every row as it becomes final;

    and every window of whole chunks (blockrender._chunk) no pending row can
    reach is rendered from the rows live in it, sorted by their order keys
    into the whole table's order -- bit for bit synth_window's render of it,
    bursts, master fader, gain and clip included. The reverb send is a second
    render of each window when the channels heard send differently.

    Memory is what is sounding, plus what the amplifier holds."""

    BATCH = 8
    # A BATCH HAS A ROW BUDGET (TUNING_STREAM_ROWS): a batch whose windows
    # sound more rows than this renders in halves, down to a window at a time.
    # Its rows are copied three times over (selected, joined, sorted) and set
    # up for the kernel, about 2 KB each: SENSATIO's 8 s at 3:12 sounded 1.5M
    # rows, the render reached 4.2 GB and was stopped. Batching only groups
    # windows, so the samples are the same (TUNING_STREAM_BATCH=1 is the
    # strictest case of it).
    ROW_BUDGET = 300_000

    def __init__(self, send='auto', batch=None, loudest=None, scan=False, out=None, send_out=None,
                 stems=None, gpu=None):
        # out / send_out: WAV paths to write the mix and the reverb send to as
        # they render (blockrender's command line); otherwise they are kept,
        # whole, in L, R, SL, SR.
        # send: True renders the reverb send from the start; 'auto' only once
        # two channels heard so far send differently (blockrender keeps a send
        # bus only then) -- and if that is learnt after windows rendered
        # without it, the stream is `incomplete` and render() runs it again.
        # gpu: a gpurender.Gpu -- the windows' samples on it (gpurender.
        # FileRenderer), held to the CPU at 1e-5, not bit for bit; the send in
        # the same pass, the kernel's send bus being the GPU's anyway
        self.gpu = gpu
        self.want_send = send
        self.incomplete = False
        self.out_path, self.send_path = out, send_out
        # stems: dict(objects=bool, by='channel'|'source', outdir, base) --
        # one signal per part instead of the mix, each written as it renders
        self.stems = stems
        self.groups = {}            # group -> dict(out=writer, path, bursts)
        self.part_stats = {}        # group -> [rows, sum w, sum w*px, sum w*pz, sum px, sum pz]
        # TUNING_STREAM_BATCH=1: a window at a time, the strictest test of
        # when the stream decides a window can no longer change
        self.batch = batch or int(os.environ.get('TUNING_STREAM_BATCH', self.BATCH))
        self.row_budget = int(os.environ.get('TUNING_STREAM_ROWS', self.ROW_BUDGET))
        self.loudest = loudest      # the Leslie's (a scanning run finds it)
        self.scan = scan            # scanning: no render, just the loudest row
        self.scan_max = 0.0
        self.heard = set()
        self.rows = 0
        self.rows_total = 0
        self.peak_live = 0
        self.made = {}
        self.dried = set()
        self.notes = []             # notes waiting on their sympathetic buckets
        self.buckets = {}           # bucket -> [(note, local rows)]
        self.amp = {}               # channel -> dict(rows=..., edge=...)
        self.ready = []             # rows final for the per-row passes
        self.store = []             # rows through every pass, still to sound
        self._shadow = []           # (rows, last end, bytes) a chunk the old rule would hold
        self.ht_seen = {}
        self.rotors = {}
        self.wi = 0

    # -- prepare's hooks ------------------------------------------------------
    def begin(self, ctx):
        B = ctx['mod']
        self.B, self.ctx = B, ctx
        # THE CONSONANTS, EXPANDED AS THEIR CHANNELS SOUND. prepare's bursts
        # are raw until a channel's first note gives them a source (seats,
        # room images); the whole-file path expands them all at the end, and
        # the stream had been mixing them raw -- which crashed on every file
        # with lyrics. Each is expanded by prepare's own function the moment
        # its source exists, so it comes out as the whole-file path's; and no
        # window is rendered past a burst still waiting (_burst_hold).
        self.xb = {}                  # burst index -> its emissions
        self.xbl = []                 # the expanded bursts, in index order
        self.N = ctx['N']
        self.W = B._chunk()
        if self.stems is not None:
            self.wout = self.wsend = None
            self.L = self.R = self.SL = self.SR = None
            self.send = False
        elif self.out_path:
            self.wout = WavOut(self.out_path, B.SR)
            self.wsend = WavOut(self.send_path, B.SR) if self.send_path else None
            self.L = self.R = self.SL = self.SR = None
        else:
            self.wout = self.wsend = None
            self.L = np.zeros(self.N, np.float32)
            self.R = np.zeros(self.N, np.float32)
            self.SL = np.zeros(self.N, np.float32)
            self.SR = np.zeros(self.N, np.float32)
        if self.stems is None:
            self.send = self.want_send
        self.cols = None
        self.mfdup = {}
        self.mf_last = 0
        self.ring_last = 0          # where the last partial dies (blockrender.ring_last)
        self.reg = {}               # channel -> register.Channel, in first-strike order
        self.reg_next = {}          # channel -> its next strike to feed

    def __call__(self, A, i0, i1, next_on):
        if self.cols is None:
            self.cols = list(A)
            self.dtypes = None
        if self.dtypes is None and i1 > i0:
            self.dtypes = {k: A[k].rows(i0, i0 + 1).dtype for k in A}
        if i1 > i0:
            r = {k: A[k].rows(i0, i1) for k in A}
            n = i1 - i0
            self.rows += n
            r['key'], r['klen'] = _key(np.stack([np.zeros(n, np.int64), np.arange(i0, i1),
                                                 np.zeros(n, np.int64), np.zeros(n, np.int64)], 1),
                                       np.zeros((n, 0), np.int64), np.zeros(n, np.int64))
            self.heard.update(int(c) for c in np.unique(r['mch']))
            self.ring_last = max(self.ring_last, self.B.ring_last(r))
            self._note(r, i0, i1)
            self._register_feed(r, i0, i1)
        for k in A:
            A[k].drop_to(i1)
        T = float('inf') if next_on is None else next_on
        # the register FIRST: the passes below read the horizon its pending
        # rows hold, and at the end the amplifier must see it released
        self._register(T)
        self._advance(T)
        if next_on is None:
            self.flush()
        if not self.scan:
            limit = self._horizon(T)
            if next_on is None:
                self.N = max(self.N, self.mf_last + self.B.SR // 2) if self.mf_last else self.N
                self.N = max(self.N, min(self.ring_last + self.B.BLK,
                                         int((self.ctx['total'] + self.B.RING_MAX) * self.B.SR)))
                self._grow(self.N)
            self._expand_bursts(next_on is None)
            limit = min(limit, self._burst_hold())
            while (self.wi + self.batch) * self.W <= min(limit, self.N) or \
                    (next_on is None and self.wi * self.W < self.N):
                self.flush()
                self._render(self.wi, self.batch)
                self.wi += self.batch
            if next_on is None and self.wout is not None:
                self.wout.close()
                if self.wsend is not None:
                    self.wsend.close()
            if next_on is None and self.stems is not None:
                for g in self.groups.values():
                    g['out'].close()

    # -- a note arrives -------------------------------------------------------
    def _note(self, r, i0, i1):
        fx = self.ctx['effects']
        if fx['leslie'] and self.loudest is None and not self.scan:
            import leslie as LE
            if not LE.KERNEL_LOBE:     # the sidebands' budget is the file's loudest row
                raise NeedLoudest()
        mf = [(a - i0, b - i0, st) for a, b, st in fx['mf104'] if i0 <= a < i1]
        gsd = [(a - i0, b - i0, dv, sd) for a, b, dv, sd in fx.get('gsdelay', ()) if i0 <= a < i1]
        ht = [(a - i0, b - i0) for a, b in self.ctx['ht_rows'] if i0 <= a < i1]
        note = dict(r=r, mf=mf, gsd=gsd, ht=ht, wait=0)
        sym = fx['sympathetic']
        if sym:
            for ch in sym:
                rows = np.flatnonzero(r['mch'] == ch)
                if len(rows):
                    bks = np.rint(r['non'][rows].astype(np.float64) / 64.0).astype(np.int64)
                    for bk in np.unique(bks):
                        self.buckets.setdefault(int(bk), []).append((note, rows[bks == bk]))
                        note['wait'] += 1
        self.notes.append(note)

    def _advance(self, T):
        """Every pass, as far as what is known allows."""
        # 1. sympathetic: buckets no note to come can add to
        done = [b for b in self.buckets if T == float('inf') or 64 * b + 32 < T]
        for b in sorted(done):
            self._sympathetic(self.buckets.pop(b))
        # 2. MF-104, and the note's rows on to the amplifier and the rest
        keep = []
        for note in self.notes:
            if note['wait'] > 0:
                keep.append(note)
            else:
                self._mf104(note)
        self.notes = keep
        # 3. the amplifier's segments that nothing to come can reach
        self._amplifier(self._amp_horizon(T))
        # 4. the per-row passes, in batches (flush() runs them before a render)
        if sum(len(r['om']) for r in self.ready) >= self.CHAIN_ROWS:
            self.flush()

    CHAIN_ROWS = 20000

    def flush(self):
        """The per-row passes, on every row final so far."""
        if self.ready:
            rows = _cat(self.ready)
            self.ready = []
            out = self._chain(rows)
            if out is not None:
                self.rows_total += len(out['om'])
                if self.scan:
                    self.scan_max = max(self.scan_max, float(np.max(np.abs(out['aM']))))
                else:
                    out['zend'] = self._zend(out)
                    out['nonL'] = out['non'].astype(np.int64)
                    if self.stems is not None:
                        self._count_group_rows(out)
                    self.store.append(out)
                    if _STATS:      # the old rule's chunk, whole, until its last row ends
                        self._shadow.append((len(out['om']), int(out['zend'].max()),
                                             sum(v.nbytes for v in out.values())))

    def _pending_min(self):
        """The earliest onset any row not yet past passes 1-2 may have."""
        m = float('inf')
        for C in self.reg.values():
            m = min(m, C.pending_min())
        for rows in self.buckets.values():
            for note, sel in rows:
                m = min(m, float(note['r']['non'][sel].min()))
        for note in self.notes:
            m = min(m, float(note['r']['non'].min()))
        return m

    def _amp_horizon(self, T):
        return min(T, self._pending_min())

    def _expand_bursts(self, final=False):
        raw = self.ctx.get('cons_bursts') or ()
        if len(self.xb) == len(raw):
            return
        src, expand = self.ctx['cons_src'], self.ctx['cons_expand']
        grew = False
        for i, b in enumerate(raw):
            if i not in self.xb and (final or b[8] in src):
                self.xb[i] = expand(i, b)
                grew = True
        if grew:
            self.xbl = [self.xb[i] for i in sorted(self.xb)]

    def _burst_hold(self):
        """Render no further than a quarter second before the earliest burst
        whose channel has not sounded yet (a seat's scatter and ear delay
        move an emission by milliseconds, never by that)."""
        raw = self.ctx.get('cons_bursts') or ()
        h = float('inf')
        if len(self.xb) < len(raw):
            for i, b in enumerate(raw):
                if i not in self.xb:
                    h = min(h, b[0] - self.B.SR // 4)
        return h

    def _horizon(self, T):
        """Windows ending at or before this can be rendered: no row still in
        a pass can start before it."""
        h = self._amp_horizon(T)
        for st in self.amp.values():
            nxt = st.get('next')
            if nxt is not None:
                h = min(h, nxt)
        return h if h == float('inf') else int(np.floor(h))

    # -- 1. sympathetic strings ------------------------------------------------
    def _sympathetic(self, entries):
        import sympathetic as SY
        parts = [_take(note['r'], sel) for note, sel in entries]
        for note, _ in entries:
            note['wait'] -= 1
        r = _cat(parts)
        order = np.lexsort(r['key'].T[::-1])
        r = _take(r, order)
        mini = _mini(r, self.cols)
        n0 = len(r['om'])
        meta = []
        SY.expand(mini, self.ctx['effects']['sympathetic'], self.B.SR, self.cols,
                  table=self.ctx['F'], meta=meta)
        if not meta:
            return
        out = _appended(mini, r, self.cols, n0)
        chs = list(self.ctx['effects']['sympathetic'])
        m = np.array(meta, dtype=object)
        src = np.array([x[3] for x in meta], np.int64)
        lvl = np.stack([np.full(len(meta), 1, np.int64),
                        np.array([chs.index(x[0]) for x in meta], np.int64),
                        r['key'][[x[1] for x in meta], 1],       # the group's first row
                        np.array([x[2] for x in meta], np.int64)], 1)
        out['key'], out['klen'] = _key(lvl, r['key'][src], r['klen'][src])
        self._final(out)

    # -- 1b. the free-string register ------------------------------------------
    # register.Channel works incrementally already: fed each strike as its note
    # arrives, advanced to the next onset, it hands out the rows nothing to come
    # can change -- the same object, run the same way, that the whole table
    # runs to the end at once. Their keys put them after every sympathetic row
    # and before MF-104, channel by channel, (phase, seq) within.
    REG_RANK0 = 1000000

    def _register_feed(self, r, i0, i1):
        recs = self.ctx['effects'].get('register') or {}
        if not recs:
            return
        import register as RG
        B = self.B
        cols = B.PARTIAL_COLS + ('az', 'dr')
        for ch, R in recs.items():
            k = self.reg_next.get(ch, 0)
            st = R['strikes']
            while k < len(st) and st[k]['rows'][1] is not None and st[k]['rows'][1] <= i1:
                x = st[k]
                a, b = x['rows'][0] - i0, x['rows'][1] - i0
                if ch not in self.reg:
                    self.reg[ch] = RG.channel_for(ch, R, B.SR, B.BLK, cols,
                                                  self.ctx['effects']['register_scale'],
                                                  self.ctx['effects']['register_strings'],
                                                  keep=False)
                rows = {c: r[c][a:b] for c in cols}
                if x.get('gr') is not None:      # its drawn ranks only (blockrender._strike_rows)
                    keep = np.isin(rows['gr'], x['gr'])
                    rows = {c: v[keep] for c, v in rows.items()}
                self.reg[ch].strike(x['key'], x['on'], x['held'], x['av'], rows, x.get('plucked'),
                                    [x['grc'][int(g)] for g in rows['gr']] if x.get('grc') else None)
                k += 1
            self.reg_next[ch] = k

    def _register(self, T):
        for rank, (ch, C) in enumerate(self.reg.items()):
            C.advance(T)
            recs = C.take()
            if not recs:
                continue
            n = len(recs)
            out = {c: np.array([x['row'][c] for x in recs], dtype=self.dtypes[c])
                   for c in self.cols}
            lvl = np.stack([np.full(n, 1, np.int64), np.full(n, self.REG_RANK0 + rank, np.int64),
                            np.array([x['phase'] for x in recs], np.int64),
                            np.array([x['seq'] for x in recs], np.int64)], 1)
            out['key'], out['klen'] = _key(lvl, np.zeros((n, 0), np.int64), np.zeros(n, np.int64))
            self._final(out)

    # -- 2. MF-104 ----------------------------------------------------------
    def _mf104(self, note):
        r = note['r']
        if note['mf'] or note['gsd']:
            import mf104 as MF
            import gsdelay as GSD
            mini = _mini(r, self.cols)
            n0 = len(r['om'])
            meta, gmeta = [], []
            if note['mf']:
                _, last = MF.expand(mini, note['mf'], self.B.SR, self.cols, dup_fx=self._mf_dup, meta=meta)
                self.mf_last = max(self.mf_last, last)
            if note['gsd']:
                # the GS delay's repeats, after the MF-104M's, of the dry rows
                _, last = GSD.expand(mini, note['gsd'], self.B.SR, self.cols, self.B.gsd_place, meta=gmeta)
                self.mf_last = max(self.mf_last, last)
            for k in ('aL', 'aR', 'aM'):                    # the dry share, in place
                r[k] = np.array(mini[k][:n0], dtype=r[k].dtype)
            meta = meta + gmeta
            if meta:
                out = _appended(mini, r, self.cols, n0)
                src = np.array([x[0] for x in meta], np.int64)
                lvl = np.zeros((len(meta), 4), np.int64); lvl[:, 0] = 2
                lvl[len(meta) - len(gmeta):, 0] = 3        # the GS delay's: their own level
                out['key'], out['klen'] = _key(lvl, r['key'][src], r['klen'][src],
                                               np.array([[x[1]] for x in meta], np.int64))
                out['ht'] = np.zeros(len(src), bool)
                self._final(out, ht=False)
        r['ht'] = np.zeros(len(r['om']), bool)
        for a, b in note['ht']:
            r['ht'][a:b] = True
        self._final(r, ht=None)

    def _mf_dup(self, fx, d):
        """blockrender's _mf_dup: a repeat's Moog row, its pitch and shape rows D later."""
        import mf104 as MF
        FT, MPI, MKI = self.ctx['moog_ft'], self.ctx['moog_mpi'], self.ctx['moog_mki']
        ft = FT[fx]
        fl = int(ft[12])
        if not fl & (1 | 14):
            return None
        if (fx, d) not in self.mfdup:
            g = d // MF.GRID
            FT.append(list(ft))
            mpi = list(MPI[fx])
            if fl & 1:
                mpi[1] += g
            MPI.append(mpi)
            mki = list(MKI[fx])
            if fl & 14:
                mki[1] += g
            MKI.append(mki)
            self.mfdup[(fx, d)] = len(FT) - 1
        return self.mfdup[(fx, d)]

    def _final(self, rows, ht=False):
        """Rows past passes 1-2: a copy to the amplifier if it hears them, and
        on to the per-row passes."""
        if 'ht' not in rows:
            rows['ht'] = np.zeros(len(rows['om']), bool)
        amp = self.ctx['effects']['tubeamp']
        import tubeamp as TA
        if amp and TA.ENABLED:
            for ch in amp:
                m = (rows['mch'] == ch) & (rows['dr'] > 0.5)
                if m.any():
                    st = self.amp.setdefault(ch, dict(rows=None, edge=None, next=None))
                    st['rows'] = _cat([st['rows'], {k: v[m].copy() for k, v in rows.items()}])
        self.ready.append(rows)

    # -- 3. the amplifier ------------------------------------------------------
    def _amplifier(self, H):
        import tubeamp as TA
        amp = self.ctx['effects']['tubeamp']
        if not amp or not TA.ENABLED:
            return
        chs = list(amp)
        for ch, st in self.amp.items():
            drive = amp[ch]
            r = st['rows']
            if r is None or drive <= 0.0:
                continue
            order = np.lexsort(r['key'].T[::-1])
            r = st['rows'] = _take(r, order)
            arrs = dict(non=r['non'].astype(float), noff=r['noff'].astype(float),
                        om=r['om'].astype(float), aM=r['aM'].astype(float), p0=r['p0'].astype(float))
            e = [arrs['non'], arrs['noff']]
            if st['edge'] is not None:
                e.append(np.array([st['edge']]))
            edges = np.unique(np.concatenate(e))
            if st['edge'] is not None:
                edges = edges[edges >= st['edge']]
            rows = np.arange(len(r['om']))
            mini = None
            outs = []
            last = st['edge']
            for a, b in zip(edges[:-1], edges[1:]):
                if b > H:
                    break
                if len(rows) >= 2:
                    if mini is None:
                        mini = _mini(r, self.cols)
                    n0 = len(mini['om'])
                    meta = []
                    extra = {k: [] for k in self.cols}
                    TA.segment(mini, arrs, rows, ch, drive, a, b, self.B.SR, self.cols, extra,
                               references=self.ctx['amp_ref'], imbalances=self.ctx['amp_imb'], meta=meta)
                    if meta:
                        o = {k: np.array(extra[k], dtype=r[k].dtype) for k in self.cols}
                        lvl = np.stack([np.full(len(meta), 3, np.int64),
                                        np.full(len(meta), chs.index(ch), np.int64),
                                        np.full(len(meta), int(_fbits(a)), np.int64),
                                        np.array([x[2] for x in meta], np.int64)], 1)
                        o['key'], o['klen'] = _key(lvl, np.zeros((len(meta), 0), np.int64),
                                                   np.zeros(len(meta), np.int64))
                        o['ht'] = np.zeros(len(meta), bool)
                        outs.append(o)
                last = b
            st['edge'] = last
            if last is not None:
                # A ROW ENDING AT THE EDGE IS DONE. A segment [a, b] hears the
                # rows with noff >= b (tubeamp.segment), and every segment to
                # come ends past this edge, so such a row is in none of them.
                # Kept, it held `next` at its own end until the channel played
                # again: a guitar part falling silent froze the whole render
                # there, and every row after piled up (Tokei, reaped at 2:08).
                keep = arrs['noff'] > last + 1e-6
                st['rows'] = _take(r, np.flatnonzero(keep)) if keep.any() else None
            # where the next products can start: the segment after the last
            # one made begins AT its end (or at the first edge, if none yet)
            if st['rows'] is None:
                st['next'] = None
            else:
                st['next'] = last if last is not None else float(edges[0])
            for o in outs:
                self.ready.append(o)

    # -- 4. the per-row passes ---------------------------------------------------
    def _chain(self, r):
        import tonelib as T
        fx = self.ctx['effects']
        order = np.lexsort(r['key'].T[::-1])
        r = _take(r, order)
        # CLAVINET TONE, in place
        for ch, setting in fx['clavinet'].items():
            sel = r['mch'] == ch
            if sel.any():
                g = T.clav_tone_gain(r['nf'][sel].astype(np.float64), setting)
                for col in ('aL', 'aR', 'aM'):
                    v = r[col]; v[sel] *= g
        parts = [r]
        # HARMONIUM TREMOLO: the notes played with the stop drawn
        if fx['htremolo'] and r['ht'].any():
            for ch, v in fx['htremolo'].items():
                self.ht_seen.setdefault(ch, set()).add(tuple(v))
            parts.append(self._tremolo(r, fx['htremolo'], 4, rows=r['ht']))
        # TREMOLO
        if fx['tremolo']:
            src = _cat(parts)
            parts.append(self._tremolo(src, fx['tremolo'], 5))
        # THE SCANNER (scanner.apply): vibrato puts a channel's rows on its
        # band rows through the circuit's gains; chorus makes them the dry
        # share and adds the scanned copies
        if fx.get('scanner'):
            import scanner as SCN
            parts = [p for p in parts if p is not None]
            outs = []
            order = list(fx['scanner'])
            for ch, (rws, depth, chorus) in fx['scanner'].items():
                for p in parts:
                    sel = np.flatnonzero((p['mch'] == ch) & (p['br'] < 0))
                    if not len(sel):
                        continue
                    o = SCN.apply(p, sel, rws, depth, chorus, self.B.SR)
                    if o is None:
                        continue
                    src = o.pop('_src')
                    lvl = np.zeros((len(src), 4), np.int64)
                    lvl[:, 0] = 7; lvl[:, 1] = order.index(ch); lvl[:, 2] = np.arange(len(src))
                    o['key'], o['klen'] = _key(lvl, p['key'][src], p['klen'][src])
                    o['ht'] = np.zeros(len(src), bool)
                    outs.append(o)
            if outs:
                parts.append(_cat(outs))
        # CHORUS (copies, and the dry share in place)
        if fx['chorus']:
            parts = [p for p in parts if p is not None]
            parts.append(self._chorus(parts, fx['chorus']))
        out = _cat(parts)
        # THE INSERTION EFFECT's EQ, after its valve, in place (gsefx.eq_gain)
        if fx.get('efxeq'):
            import gsefx as GSX
            for ch, eq in fx['efxeq'].items():
                sel = out['mch'] == ch
                if sel.any():
                    g = GSX.eq_gain(out['nf'][sel].astype(np.float64), eq)
                    for col in ('aL', 'aR', 'aM'):
                        v = out[col]; v[sel] *= g
        # CABINET, in place
        import cabinet as CAB
        for ch, name in fx['cabinet'].items():
            cab = CAB.get(name)
            if cab is None:
                continue
            sel = out['mch'] == ch
            if sel.any():
                g = cab.gain(out['nf'][sel].astype(np.float64))
                for col in ('aL', 'aR', 'aM'):
                    v = out[col]; v[sel] *= g
        if self.scan:
            return out
        # LESLIE (its vibrato in place, sidebands appended)
        if fx['leslie']:
            out = _cat([out, self._leslie(out, fx['leslie'])])
        return out

    def _tremolo(self, r, channels, passno, rows=None):
        import tremolo as TR
        o = np.lexsort(r['key'].T[::-1])
        r = _take(r, o)
        mini = _mini(r, self.cols)
        n0 = len(r['om'])
        meta = []
        TR.expand(mini, channels, self.B.SR, self.cols,
                  rows=None if rows is None else list(r['ht']), meta=meta)
        if not meta:
            return None
        out = _appended(mini, r, self.cols, n0)
        src = np.array([x[0] for x in meta], np.int64)
        lvl = np.zeros((len(meta), 4), np.int64); lvl[:, 0] = passno
        out['key'], out['klen'] = _key(lvl, r['key'][src], r['klen'][src],
                                       np.array([[x[1]] for x in meta], np.int64))
        out['ht'] = np.zeros(len(src), bool)
        return out

    def _leslie(self, r, channels):
        import leslie as LE
        for ch in channels:
            if ch not in self.rotors:
                self.rotors.update(LE.make_rotors({ch: channels[ch]}))
        mini = _mini(r, self.cols)
        n0 = len(r['om'])
        meta = []
        LE.expand(mini, channels, self.B.SR, self.cols, meta=meta,
                  loudest=self.loudest, rotors=self.rotors, place=self.B.gsd_place)
        # in place: the rotor's vibrato, and the cabinet's colour on each row
        # (leslie.cabinet_gain) -- which the old copy-back dropped, so a stream
        # render had the cabinet on the sidebands alone and prepare() on all
        for k in ('vd', 'vr', 'vp', 'aL', 'aR', 'aM'):
            r[k] = np.array(mini[k][:n0], dtype=r[k].dtype)
        # ...and a recorded Rotary's mic A, in place (leslie._to_mic): its
        # phase, its ears' delays from its speaker, its angle to the rotors
        if any(isinstance(v, dict) and v.get('separate') is not None for v in channels.values()):
            for k in ('p0', 'p0R', 'delL', 'delR', 'az'):
                r[k] = np.array(mini[k][:n0], dtype=r[k].dtype)
        # the kernel's lobe (leslie.lobe_columns), on every row of the chunk
        lobe = 'lsr' in mini
        if lobe:
            for k, dt, _ in LE.LOBE_COLS:
                r[k] = np.asarray(mini[k][:n0], dt)
        if not meta:
            return None
        out = _appended(mini, r, self.cols, n0)
        if lobe:
            for k, dt, _ in LE.LOBE_COLS:
                out[k] = np.asarray(mini[k][n0:], dt)
        src = np.array([x[0] for x in meta], np.int64)
        lvl = np.zeros((len(meta), 4), np.int64); lvl[:, 0] = 7
        out['key'], out['klen'] = _key(lvl, r['key'][src], r['klen'][src],
                                       np.array([[x[1], x[2]] for x in meta], np.int64))
        out['ht'] = np.zeros(len(src), bool)
        return out

    def _chorus(self, parts, channels):
        """chorus.expand's copies of these rows, and the dry share taken from
        them, in place."""
        import chorus as CH
        order = list(channels)
        outs = []
        for ch, spec in channels.items():
            send, cents = spec[0], spec[1]
            if (send <= CH.FLOOR and not len(spec) > 3) or not cents:
                continue
            if len(spec) > 2 and spec[2] == 'pair':
                # a DETUNED PAIR (chorus._pair): the rows down and left, a
                # copy up and right, each at half power, the copy delayed
                lo, hi = 2.0 ** (cents[0] / 1200.0), 2.0 ** (cents[1] / 1200.0)
                (gl0, gr0), (gl1, gr1) = CH.pair_side(-1), CH.pair_side(+1)
                made = 0
                for p in parts:
                    rows = np.flatnonzero(p['mch'] == ch)
                    if not len(rows):
                        continue
                    keep = rows[p['nf'][rows].astype(np.float64) * hi < self.B.SR * 0.5]
                    if len(keep):
                        o = {k: v[keep].copy() for k, v in p.items()}
                        om, p0, p0R = p['om'][keep], p['p0'][keep], p['p0R'][keep]
                        dl = CH.DELAY_S[0]
                        o['om'] = om * hi
                        o['nf'] = p['nf'][keep].astype(np.float64) * hi
                        o['p0'] = p0 * hi - om * hi * dl * self.B.SR
                        o['p0R'] = p0R * hi - om * hi * dl * self.B.SR
                        o['aL'] = p['aL'][keep] * gl1
                        o['aR'] = p['aR'][keep] * gr1
                        o['aM'] = p['aM'][keep] * 0.5 ** 0.5
                        lvl = np.zeros((len(keep), 4), np.int64)
                        lvl[:, 0] = 6; lvl[:, 1] = order.index(ch); lvl[:, 2] = 0
                        o['key'], o['klen'] = _key(lvl, p['key'][keep], p['klen'][keep])
                        o['ht'] = np.zeros(len(keep), bool)
                        outs.append(o)
                        made += len(keep)
                    p['om'][rows] = p['om'][rows] * lo
                    p['nf'][rows] = p['nf'][rows] * lo
                    p['p0'][rows] = p['p0'][rows] * lo
                    p['p0R'][rows] = p['p0R'][rows] * lo
                    p['aL'][rows] = p['aL'][rows] * gl0
                    p['aR'][rows] = p['aR'][rows] * gr0
                    p['aM'][rows] = p['aM'][rows] * 0.5 ** 0.5
                self.made[ch] = self.made.get(ch, 0) + made
                continue
            if len(spec) > 2 and spec[2] == 'gs':
                # A SOUND CANVAS FILE'S CHORUS (chorus.gs_copies), as the
                # whole table makes it
                made = 0
                dry = 1.0
                sels = [np.flatnonzero(p['mch'] == ch) for p in parts]
                drys = []
                for p, rows in zip(parts, sels):
                    if not len(rows):
                        drys.append(None)
                        continue
                    # (an insertion effect's mix follows the file: a share per row)
                    sh = spec[3](p['non'][rows]) if len(spec) > 3 else send
                    cps, dry = CH.gs_copies(p, rows, cents, sh, self.B.SR, self.B.gsd_place)
                    drys.append(dry if cps else None)
                    for ci, o, sel in cps:
                        rk = rows[sel]
                        lvl = np.zeros((len(rk), 4), np.int64)
                        lvl[:, 0] = 6; lvl[:, 1] = order.index(ch); lvl[:, 2] = 1000 + ci
                        o['key'], o['klen'] = _key(lvl, p['key'][rk], p['klen'][rk])
                        o['ht'] = np.zeros(len(rk), bool)
                        outs.append(o)
                        made += len(rk)
                self.made[ch] = self.made.get(ch, 0) + made
                for p, rows, dry in zip(parts, sels, drys):
                    if dry is not None and len(rows) and np.any(np.asarray(dry) != 1.0):
                        self.dried.add(ch)
                        for col in ('aL', 'aR', 'aM'):
                            p[col][rows] = (p[col][rows] * dry).astype(p[col].dtype)
                continue
            wet = (send / float(len(cents))) ** 0.5
            dry = (1.0 - send) ** 0.5
            sels = [np.flatnonzero(p['mch'] == ch) for p in parts]
            if not any(len(s) for s in sels):
                continue
            made = 0
            for ci, c in enumerate(cents):
                ratio = 2.0 ** (c / 1200.0)
                for p, rows in zip(parts, sels):
                    keep = rows[p['nf'][rows].astype(np.float64) * ratio < self.B.SR * 0.5]
                    if not len(keep):
                        continue
                    o = {k: v[keep].copy() for k, v in p.items()}
                    om, p0, p0R = p['om'][keep], p['p0'][keep], p['p0R'][keep]
                    dl = CH.DELAY_S[ci % len(CH.DELAY_S)]
                    o['om'] = om * ratio
                    o['nf'] = p['nf'][keep].astype(np.float64) * ratio
                    o['p0'] = p0 * ratio - om * ratio * dl * self.B.SR
                    o['p0R'] = p0R * ratio - om * ratio * dl * self.B.SR
                    o['aL'] = p['aL'][keep] * wet
                    o['aR'] = p['aR'][keep] * wet
                    o['aM'] = p['aM'][keep] * wet
                    o['vd'] = np.full(len(keep), CH.SWEEP_DEPTH, np.float64)
                    o['vr'] = np.full(len(keep), CH.SWEEP_HZ[ci % len(CH.SWEEP_HZ)], np.float64)
                    o['vp'] = np.full(len(keep), 2.0 * np.pi * (ci / float(len(cents))), np.float64)
                    lvl = np.zeros((len(keep), 4), np.int64)
                    lvl[:, 0] = 6; lvl[:, 1] = order.index(ch); lvl[:, 2] = ci
                    o['key'], o['klen'] = _key(lvl, p['key'][keep], p['klen'][keep])
                    o['ht'] = np.zeros(len(keep), bool)
                    outs.append(o)
                    made += len(keep)
            self.made[ch] = self.made.get(ch, 0) + made
            if dry != 1.0:
                self.dried.add(ch)
                for p, rows in zip(parts, sels):
                    if len(rows):
                        for col in ('aL', 'aR', 'aM'):
                            p[col][rows] = p[col][rows] * dry
        return _cat(outs)

    def check(self):
        """What the stream assumed, checked against what the file turned out to be."""
        chans = self.ctx['effects']['chorus']
        total = 0
        for ch in chans:
            total += self.made.get(ch, 0)
            if ch in self.dried and total == 0:
                raise NotStreamable("chorus: a channel dried before any copy existed")
        for ch, seen in self.ht_seen.items():
            final = tuple(self.ctx['effects']['htremolo'].get(ch, ()))
            if seen != {final}:
                raise NotStreamable("harmonium tremolo settings changed mid-file")

    # -- the store and the windows --------------------------------------------
    def _zend(self, r):
        f4 = np.float32
        dl = np.maximum(f4(0.0), np.maximum(r['delL'].astype(f4), r['delR'].astype(f4)))
        return (r['noff'].astype(np.int64) + r['re'].astype(f4).astype(np.int64)
                + np.ceil(dl).astype(np.int64) + self.B.BLK)

    def _grow(self, n):
        if self.L is None:
            return
        if n > len(self.L):
            for k in ('L', 'R', 'SL', 'SR'):
                a = getattr(self, k)
                b = np.zeros(n, np.float32); b[:len(a)] = a
                setattr(self, k, b)

    def _render(self, wi, nw=1):
        """Windows wi .. wi+nw-1 in one kernel call."""
        B = self.B
        w0 = wi * self.W
        w1 = min(self.N, w0 + nw * self.W)
        if w1 <= w0:
            return
        if nw > 1 and sum(int(((c['nonL'] < w1) & (c['zend'] > w0)).sum())
                          for c in self.store) > self.row_budget:
            h = nw // 2
            self._render(wi, h)
            self._render(wi + h, nw - h)
            return
        sel = []
        for c in self.store:
            m = (c['nonL'] < w1) & (c['zend'] > w0)
            if m.any():
                sel.append({k: v[m] for k, v in c.items()})
        # A CHUNK KEEPS ONLY ITS ROWS STILL TO SOUND. It was kept whole until
        # its LAST row ended -- and a chunk is 20 000 rows of everything
        # finished together, so nearly every one held some long row (a held
        # string, the bass, a cymbal's ring, its reflections) and waited on it
        # with every column of every row long done: memory grew with the
        # piece, and Tokei's full render was reaped for it. A row whose end is
        # past can sound in no later window, and the rows are sorted by key
        # before every render, so dropping them changes no sample. Compacted
        # once half a chunk is done, so each row is copied a few times at most.
        if _STATS:
            # what the store holds against what is still to sound: the rows
            # whole chunks would keep (the old rule: until a chunk's last row
            # ends), the rows kept now, and the rows actually still sounding
            self._shadow = [x for x in self._shadow if x[1] > w1]
            _old = sum(x[0] for x in self._shadow)
            _oldb = sum(x[2] for x in self._shadow)
            _held = sum(len(c['zend']) for c in self.store)
            _alive = sum(int((c['zend'] > w1).sum()) for c in self.store)
            _by = sum(sum(v.nbytes for v in c.values()) for c in self.store)
            print("  stream at %6.1f s: rows held %8d (%5.0f MB), still to sound %8d; "
                  "whole chunks would hold %8d (%5.0f MB)" % (w1 / self.B.SR, _held, _by / 2 ** 20, _alive,
                                                              _old, _oldb / 2 ** 20),
                  flush=True)
        keep = []
        for c in self.store:
            alive = c['zend'] > w1
            if not alive.any():
                continue
            if 2 * int(alive.sum()) < len(alive):
                c = {k: v[alive] for k, v in c.items()}
            keep.append(c)
        self.store = keep
        n = w1 - w0
        if self.stems is not None:
            return self._render_stems(w0, w1, sel)
        if not sel:
            self._emit(w0, w1, np.zeros(n, np.float32), np.zeros(n, np.float32),
                       np.zeros(n, np.float32), np.zeros(n, np.float32))
            return
        if any('lsr' in c for c in sel):
            sel = [_lobe_fill(c) for c in sel]
        rows = _cat(sel)
        order = np.lexsort(rows['key'].T[::-1])
        P = len(order)
        self.peak_live = max(self.peak_live, P)
        prep = dict(lib=self.ctx['lib'], P=P, N=self.N, nblk=self.ctx['nblk'], sh=self.ctx['sh'],
                    G=self.ctx['G'], S=self.ctx['S'], BR=self.ctx['BR'], BC=self.ctx['BC'], BL=self.ctx.get('BL'),
                    knk=1, kb0=0, **self.ctx['moog_tables']())
        for k, dt in B.FINAL_DTYPES:
            prep[k] = np.ascontiguousarray(rows[k][order].astype(dt))
        self._lobe_prep(prep, rows, order)
        self._filter_prep(prep)
        bus = self.ctx['effects'].get('bus')
        if not bus:
            L, R, SL, SR_ = self._synth(prep, wi, w0, w1)
            self._emit(w0, w1, L, R, SL, SR_)
            return
        # A PART WITH A BUS OF ITS OWN (efxbus) renders apart, through its
        # processors -- kept across windows, fed silence where it has no rows,
        # so the stream is the whole table's one continuous pass
        import efxbus as EB
        mch = np.asarray(prep['mch'])
        on = np.isin(mch, list(bus))
        L, R, SL, SR_ = self._synth(B.prep_rows(prep, ~on), wi, w0, w1)
        procs = self.__dict__.setdefault('_busp', {})
        for ch, spec in bus.items():
            if ch not in procs:
                procs[ch] = (EB.Bus(spec, B.SR, T_master_gain()), EB.Bus(spec, B.SR, T_master_gain()))
            m = mch == ch
            if m.any():
                bL, bR, bSL, bSR = self._synth(B.prep_rows(prep, m), wi, w0, w1)
            else:
                bL = bR = bSL = bSR = np.zeros(n, np.float32)
            oL, oR = procs[ch][0].process(bL, bR, w0)
            sL, sR = procs[ch][1].process(bSL, bSR, w0)
            L = L + oL; R = R + oR; SL = SL + sL; SR_ = SR_ + sR
        self._emit(w0, w1, L, R, SL, SR_)

    def _synth(self, prep, wi, w0, w1):
        """A window's samples of these rows: (L, R, SL, SR), the send rendered
        where the channels heard send differently -- on the GPU or the CPU."""
        B = self.B
        n = w1 - w0
        P = prep['P']
        if self.gpu is not None and P:
            import gpurender as GR
            g = self.B.send_weights(self.ctx['reverb'], self.ctx.get('reverb_steps'),
                                    prep['mch'], prep['non'])
            if self.send == 'auto' and self._split():
                self.send = True
            return GR.FileRenderer(prep, self.gpu).render(w1, send_w=g, n0=w0)
        L = np.zeros(n, np.float32); R = np.zeros(n, np.float32)
        SL = np.zeros(n, np.float32); SR_ = np.zeros(n, np.float32)
        if not P:
            return L, R, SL, SR_
        B.synth_partials(prep, w0, n, 0, P, L, R)
        # THE SEND, A SECOND RENDER of the same rows at each channel's send, as
        # blockrender's own send pass makes it. NOT the kernel's send bus in
        # the same call: under -ffast-math switching that on contracts the
        # mix's multiply-adds differently, and the mix moved by an ulp (the
        # corpus hashes with it). Rendered once the channels heard send
        # differently, which is when blockrender keeps a send at all.
        if self.send == 'auto' and self._split():
            self.send = True
            self.incomplete = wi > 0
        if self.send is True:
            g = B.send_weights(self.ctx['reverb'], self.ctx.get('reverb_steps'),
                               prep['mch'], prep['non'])
            prep['aL'] = prep['aL'] * g
            prep['aR'] = prep['aR'] * g
            B.synth_partials(prep, w0, n, 0, P, SL, SR_)
        return L, R, SL, SR_

    def _filter_prep(self, prep):
        """A moving filter's columns and control table (blockrender.filter_prep),
        the table built again only when a channel joins or the length grows."""
        chans = self.ctx['effects'].get('filter')
        if not chans:
            return
        key = (tuple(chans), self.N)
        if getattr(self, '_fct_key', None) != key:
            import efxfilter as EF
            import leslie as LE
            self._fct = EF.table(chans, self.N, self.B.SR, LE.rotor_grid(self.B.BLK))[0]
            self._fct_key = key
        import efxfilter as EF
        import leslie as LE
        for k, v in EF.columns(prep['mch'], chans).items():
            prep[k] = np.ascontiguousarray(v)
        prep['FCT'] = self._fct
        if prep.get('LANG') is None:
            for k, dt, v in LE.LOBE_COLS:
                prep[k] = np.full(len(prep['mch']), v, dt)
            prep['LANG'] = np.zeros((1, 1), np.float32)

    def _lobe_prep(self, prep, rows, ix):
        """The Leslie's lobe for the kernel: its columns, and the rotors'
        angles (leslie.angle_table) -- built for the file's length, again only
        when a channel joins or the length grows, so every window reads one
        table, the whole table's."""
        if 'lsr' not in rows:
            return
        import leslie as LE
        for k, dt, _ in LE.LOBE_COLS:
            prep[k] = np.ascontiguousarray(rows[k][ix].astype(dt))
        chans = self.ctx['effects']['leslie']
        key = (tuple(chans), self.N)
        if getattr(self, '_lang_key', None) != key:
            self._lang = LE.angle_table(chans, self.rotors, self.N, self.B.SR, self.B.BLK)
            self._lang_key = key
        prep['LANG'] = self._lang

    # -- stems and objects -------------------------------------------------------
    def _group_keys(self, rows):
        if self.stems['by'] == 'source':
            return [tuple(x) for x in np.stack([rows['mch'].astype(np.int64), rows['pl'].astype(np.int64),
                                                rows['gr'].astype(np.int64)], 1).tolist()]
        return [(int(c),) for c in rows['mch'].tolist()]

    def _group(self, key, w0):
        """A part's writer, opened -- and, if it first sounds now, given the
        windows before (its channel's bursts, which can start before its first
        partial, through the fader, gain and clip, as the whole render's)."""
        import os
        g = self.groups.get(key)
        if g is None:
            ch = key[0]
            path = os.path.join(self.stems['outdir'], '.%s.part%s.wav' % (
                self.stems['base'], '_'.join('%d' % k for k in key)))
            out = (WavOutMono if self.stems['objects'] else WavOut)(path, self.B.SR)
            g = self.groups[key] = dict(out=out, path=path, rows=0, ch=ch,
                                        w=0.0, wx=0.0, wz=0.0, n=0, sx=0.0, sz=0.0)
            for a in range(0, w0, self.W * self.batch):
                b = min(w0, a + self.W * self.batch)
                self._stem_emit(g, a, b, np.zeros(b - a, np.float32), np.zeros(b - a, np.float32))
        return g

    def _render_stems(self, w0, w1, sel):
        B = self.B
        n = w1 - w0
        done = set()
        if sel:
            if any('lsr' in c for c in sel):
                sel = [_lobe_fill(c) for c in sel]
            rows = _cat(sel)
            order = np.lexsort(rows['key'].T[::-1])
            rows = _take(rows, order)
            gk = self._group_keys(rows)
            uniq = {}
            for i, k in enumerate(gk):
                uniq.setdefault(k, []).append(i)
            base = dict(lib=self.ctx['lib'], N=self.N, nblk=self.ctx['nblk'], sh=self.ctx['sh'],
                        G=self.ctx['G'], S=self.ctx['S'], BR=self.ctx['BR'], BC=self.ctx['BC'], BL=self.ctx.get('BL'),
                        knk=1, kb0=0, **self.ctx['moog_tables']())
            for k, ix in uniq.items():
                g = self._group(k, w0)
                ix = np.array(ix)
                prep = dict(base, P=len(ix))
                for c, dt in B.FINAL_DTYPES:
                    prep[c] = np.ascontiguousarray(rows[c][ix].astype(dt))
                self._lobe_prep(prep, rows, ix)
                self._filter_prep(prep)
                if self.stems['objects']:          # subset(objectify=True)'s rules
                    prep['aL'] = prep['aR'] = np.ascontiguousarray(prep['aM'])
                    prep['p0R'] = np.ascontiguousarray(prep['p0'])
                    z = np.zeros(len(ix), np.float32)
                    prep['delL'] = z; prep['delR'] = z.copy()
                L = np.zeros(n, np.float32); R = np.zeros(n, np.float32)
                B.synth_partials(prep, w0, n, 0, len(ix), L, R)
                self._stem_emit(g, w0, w1, L, R)
                done.add(k)
        for k, g in self.groups.items():       # parts with nothing sounding: their bursts
            if k not in done:
                self._stem_emit(g, w0, w1, np.zeros(n, np.float32), np.zeros(n, np.float32))

    def _stem_emit(self, g, w0, w1, L, R):
        B = self.B
        n = w1 - w0
        B._NG.mix(L, R, w0, [b for b in self.xbl if int(b[5]) == g['ch']], B.SR)
        mg = B.master_curve(self.ctx['mvol'](), w0, n)
        if mg is not None:
            L *= mg; R *= mg
        L *= T_master_gain(); R *= T_master_gain()
        np.clip(L, -1, 1, L); np.clip(R, -1, 1, R)
        g['out'].write(L, R)

    def _count_group_rows(self, out):
        """Each part's rows, and its amplitude-weighted position (the
        manifest's), as the rows become final."""
        gk = self._group_keys(out)
        idx = {}
        for i, k in enumerate(gk):
            idx.setdefault(k, []).append(i)
        aM = out['aM'].astype(np.float32).astype(np.float64)
        px = out['px'].astype(np.float32).astype(np.float64)
        pz = out['pz'].astype(np.float32).astype(np.float64)
        for k, ix in idx.items():
            st = self.part_stats.setdefault(k, [0, 0.0, 0.0, 0.0, 0.0, 0.0])
            ix = np.array(ix)
            st[0] += len(ix)
            st[1] += aM[ix].sum(); st[2] += (px[ix] * aM[ix]).sum(); st[3] += (pz[ix] * aM[ix]).sum()
            st[4] += px[ix].sum(); st[5] += pz[ix].sum()

    def _emit(self, w0, w1, L, R, SL, SR_):
        """synth_window's finishing on this window -- bursts, master fader,
        gain, clip; the send gets the fader and the gain, not the clip -- and
        out to the arrays or the files."""
        B = self.B
        n = w1 - w0
        B._NG.mix(L, R, w0, self.xbl, B.SR)
        mg = B.master_curve(self.ctx['mvol'](), w0, n)
        if mg is not None:
            L *= mg; R *= mg
            SL *= mg; SR_ *= mg
        L *= T_master_gain(); R *= T_master_gain()
        # THE SEND AT THE MIX'S GAIN. roomtail convolves it against the mix as
        # written, master gain and all; without it the room stood 9-14 dB too
        # loud (the master's own dB) on every file whose channels sent
        # differently -- A-Team's band, once its gun stood back.
        SL *= T_master_gain(); SR_ *= T_master_gain()
        np.clip(L, -1, 1, L); np.clip(R, -1, 1, R)
        if self.wout is not None:
            self.wout.write(L, R)
            if self.wsend is not None:
                self.wsend.write(SL, SR_)
        else:
            self.L[w0:w1] = L; self.R[w0:w1] = R
            self.SL[w0:w1] = SL; self.SR[w0:w1] = SR_

    def _split(self):
        rs, st = self.ctx['reverb'], self.ctx.get('reverb_steps')
        return len(self.B.send_values(rs, st, self.heard)) > 1 if (rs or st) else False


def T_master_gain():
    import tonelib as T
    return T.master_gain


def render(path, tuner, B=None, out=None, send_out=None, send='auto', gpu=None):
    """A whole file, streamed: (L, R, the stream) -- or, given `out` (and
    `send_out`), written to those WAVs as it renders, and (None, None, the
    stream). Raises NotStreamable when the file needs what the stream does not
    reproduce. A file with a Leslie runs twice: a scanning run for the
    loudest row, then the render."""
    if B is None:
        import blockrender as B
    loudest = None
    while True:
        s = Stream(send=send if gpu is None else True, loudest=loudest, out=out,
                   send_out=send_out, gpu=gpu)
        try:
            info = B.prepare(path, tuner, sink=s)
        except NeedLoudest:
            sc = Stream(scan=True)
            B.prepare(path, tuner, sink=sc)
            loudest = max(sc.scan_max, 1e-12)
            continue
        if s.incomplete:            # the send was needed after all: again, with it
            send = True
            continue
        break
    s.check()
    s.info = info
    return s.L, s.R, s


def render_stems(path, tuner, outdir, objects=False, by='channel', B=None):
    """--stems / --objects, streamed: each part written to its own WAV in
    outdir as it renders (named as blockrender names them, once every part is
    known). Returns (the stream, [(key, position or None, file, partials)])."""
    import os
    if B is None:
        import blockrender as B
    base = os.path.splitext(os.path.basename(path))[0]
    stems = dict(objects=objects, by=by, outdir=outdir, base=base)
    loudest = None
    while True:
        s = Stream(loudest=loudest, stems=stems)
        try:
            s.info = B.prepare(path, tuner, sink=s)
        except NeedLoudest:
            sc = Stream(scan=True)
            B.prepare(path, tuner, sink=sc)
            loudest = max(sc.scan_max, 1e-12)
            continue
        break
    s.check()
    parts = []
    seen = {}
    for key in sorted(s.groups):
        g = s.groups[key]
        ch = key[0]
        st = s.part_stats.get(key, [0, 0.0, 0.0, 0.0, 0.0, 0.0])
        if by == 'source':
            i = seen[ch] = seen.get(ch, -1) + 1
            name = "%s.ch%02d.s%02d" % (base, ch, i)
            pos = ((st[2] / st[1], st[3] / st[1]) if st[1] > 0 else
                   (st[4] / max(st[0], 1), st[5] / max(st[0], 1)))
        else:
            name = "%s.ch%02d" % (base, ch)
            pos = None
        f = os.path.join(outdir, name + ".wav")
        os.replace(g['path'], f)
        parts.append((ch, pos, f, st[0]))
    return s, parts


def result(s):
    """What blockrender's main reads after a render (its _LAST_PREP): the room
    sidecar's bands, the sends, the channels heard, and the send bus."""
    room_q = [(f, (d / r) if r > 0.0 else 1.0, d) for f, (d, r) in zip(s.ctx['room_bands'], s.ctx['qacc'])]
    return dict(room_q=room_q, reverb_send=dict(s.ctx['reverb']), reverb_steps=dict(s.ctx.get('reverb_steps') or {}),
                mch=np.array(sorted(s.heard), np.int32), N=s.N, total=s.ctx['total'],
                mvol=s.ctx['mvol'](),
                stream_send=None if s.send is not True else ((s.SL, s.SR) if s.SL is not None else s.send_path))
