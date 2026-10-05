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

    def __init__(self, send='auto', batch=None, loudest=None, scan=False, out=None, send_out=None):
        # out / send_out: WAV paths to write the mix and the reverb send to as
        # they render (blockrender's command line); otherwise they are kept,
        # whole, in L, R, SL, SR.
        # send: True renders the reverb send from the start; 'auto' only once
        # two channels heard so far send differently (blockrender keeps a send
        # bus only then) -- and if that is learnt after windows rendered
        # without it, the stream is `incomplete` and render() runs it again.
        self.want_send = send
        self.incomplete = False
        self.out_path, self.send_path = out, send_out
        # TUNING_STREAM_BATCH=1: a window at a time, the strictest test of
        # when the stream decides a window can no longer change
        self.batch = batch or int(os.environ.get('TUNING_STREAM_BATCH', self.BATCH))
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
        self.ht_seen = {}
        self.rotors = {}
        self.wi = 0

    # -- prepare's hooks ------------------------------------------------------
    def begin(self, ctx):
        B = ctx['mod']
        self.B, self.ctx = B, ctx
        self.N = ctx['N']
        self.W = B._chunk()
        if self.out_path:
            self.wout = WavOut(self.out_path, B.SR)
            self.wsend = WavOut(self.send_path, B.SR) if self.send_path else None
            self.L = self.R = self.SL = self.SR = None
        else:
            self.wout = self.wsend = None
            self.L = np.zeros(self.N, np.float32)
            self.R = np.zeros(self.N, np.float32)
            self.SL = np.zeros(self.N, np.float32)
            self.SR = np.zeros(self.N, np.float32)
        self.send = self.want_send
        self.cols = None
        self.mfdup = {}
        self.mf_last = 0

    def __call__(self, A, i0, i1, next_on):
        if self.cols is None:
            self.cols = list(A)
        if i1 > i0:
            r = {k: A[k].rows(i0, i1) for k in A}
            n = i1 - i0
            self.rows += n
            r['key'], r['klen'] = _key(np.stack([np.zeros(n, np.int64), np.arange(i0, i1),
                                                 np.zeros(n, np.int64), np.zeros(n, np.int64)], 1),
                                       np.zeros((n, 0), np.int64), np.zeros(n, np.int64))
            self.heard.update(int(c) for c in np.unique(r['mch']))
            self._note(r, i0, i1)
        for k in A:
            A[k].drop_to(i1)
        T = float('inf') if next_on is None else next_on
        self._advance(T)
        if next_on is None:
            self.flush()
        if not self.scan:
            limit = self._horizon(T)
            if next_on is None:
                self.N = max(self.N, self.mf_last + self.B.SR // 2) if self.mf_last else self.N
                self._grow(self.N)
            while (self.wi + self.batch) * self.W <= min(limit, self.N) or \
                    (next_on is None and self.wi * self.W < self.N):
                self.flush()
                self._render(self.wi, self.batch)
                self.wi += self.batch
            if next_on is None and self.wout is not None:
                self.wout.close()
                if self.wsend is not None:
                    self.wsend.close()

    # -- a note arrives -------------------------------------------------------
    def _note(self, r, i0, i1):
        fx = self.ctx['effects']
        if fx['leslie'] and self.loudest is None and not self.scan:
            raise NeedLoudest()
        mf = [(a - i0, b - i0, st) for a, b, st in fx['mf104'] if i0 <= a < i1]
        ht = [(a - i0, b - i0) for a, b in self.ctx['ht_rows'] if i0 <= a < i1]
        note = dict(r=r, mf=mf, ht=ht, wait=0)
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
                    self.store.append(out)

    def _pending_min(self):
        """The earliest onset any row not yet past passes 1-2 may have."""
        m = float('inf')
        for rows in self.buckets.values():
            for note, sel in rows:
                m = min(m, float(note['r']['non'][sel].min()))
        for note in self.notes:
            m = min(m, float(note['r']['non'].min()))
        return m

    def _amp_horizon(self, T):
        return min(T, self._pending_min())

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

    # -- 2. MF-104 ----------------------------------------------------------
    def _mf104(self, note):
        r = note['r']
        if note['mf']:
            import mf104 as MF
            mini = _mini(r, self.cols)
            n0 = len(r['om'])
            meta = []
            _, last = MF.expand(mini, note['mf'], self.B.SR, self.cols, dup_fx=self._mf_dup, meta=meta)
            self.mf_last = max(self.mf_last, last)
            for k in ('aL', 'aR', 'aM'):                    # the dry share, in place
                r[k] = np.array(mini[k][:n0], dtype=r[k].dtype)
            if meta:
                out = _appended(mini, r, self.cols, n0)
                src = np.array([x[0] for x in meta], np.int64)
                lvl = np.zeros((len(meta), 4), np.int64); lvl[:, 0] = 2
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
                keep = arrs['noff'] >= last - 1e-6
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
        # CHORUS (copies, and the dry share in place)
        if fx['chorus']:
            parts = [p for p in parts if p is not None]
            parts.append(self._chorus(parts, fx['chorus']))
        out = _cat(parts)
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
                  loudest=self.loudest, rotors=self.rotors)
        for k in ('vd', 'vr', 'vp'):                         # in place
            r[k] = np.array(mini[k][:n0], dtype=r[k].dtype)
        if not meta:
            return None
        out = _appended(mini, r, self.cols, n0)
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
        for ch, (send, cents) in channels.items():
            if send <= CH.FLOOR or not cents:
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
        sel = []
        for c in self.store:
            m = (c['nonL'] < w1) & (c['zend'] > w0)
            if m.any():
                sel.append({k: v[m] for k, v in c.items()})
        self.store = [c for c in self.store if c['zend'].max() > w1]
        n = w1 - w0
        if not sel:
            self._emit(w0, w1, np.zeros(n, np.float32), np.zeros(n, np.float32),
                       np.zeros(n, np.float32), np.zeros(n, np.float32))
            return
        rows = _cat(sel)
        order = np.lexsort(rows['key'].T[::-1])
        P = len(order)
        self.peak_live = max(self.peak_live, P)
        prep = dict(lib=self.ctx['lib'], P=P, N=self.N, nblk=self.ctx['nblk'], sh=self.ctx['sh'],
                    G=self.ctx['G'], S=self.ctx['S'], BR=self.ctx['BR'], BC=self.ctx['BC'],
                    knk=1, kb0=0, **self.ctx['moog_tables']())
        for k, dt in B.FINAL_DTYPES:
            prep[k] = np.ascontiguousarray(rows[k][order].astype(dt))
        L = np.zeros(n, np.float32); R = np.zeros(n, np.float32)
        SL = np.zeros(n, np.float32); SR_ = np.zeros(n, np.float32)
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
            rs = self.ctx['reverb']
            g = np.ones(P, np.float32)
            for c, v in rs.items():
                g[prep['mch'] == c] = v
            prep['aL'] = prep['aL'] * g
            prep['aR'] = prep['aR'] * g
            B.synth_partials(prep, w0, n, 0, P, SL, SR_)
        self._emit(w0, w1, L, R, SL, SR_)

    def _emit(self, w0, w1, L, R, SL, SR_):
        """synth_window's finishing on this window -- bursts, master fader,
        gain, clip; the send gets the fader alone -- and out to the arrays or
        the files."""
        B = self.B
        n = w1 - w0
        B._NG.mix(L, R, w0, self.ctx['cons_bursts'], B.SR)
        mg = B.master_curve(self.ctx['mvol'](), w0, n)
        if mg is not None:
            L *= mg; R *= mg
            SL *= mg; SR_ *= mg
        L *= T_master_gain(); R *= T_master_gain()
        np.clip(L, -1, 1, L); np.clip(R, -1, 1, R)
        if self.wout is not None:
            self.wout.write(L, R)
            if self.wsend is not None:
                self.wsend.write(SL, SR_)
        else:
            self.L[w0:w1] = L; self.R[w0:w1] = R
            self.SL[w0:w1] = SL; self.SR[w0:w1] = SR_

    def _split(self):
        rs = self.ctx['reverb']
        return len({rs.get(c, 1.0) for c in self.heard}) > 1 if rs else False


def T_master_gain():
    import tonelib as T
    return T.master_gain


def render(path, tuner, B=None, out=None, send_out=None, send='auto'):
    """A whole file, streamed: (L, R, the stream) -- or, given `out` (and
    `send_out`), written to those WAVs as it renders, and (None, None, the
    stream). Raises NotStreamable when the file needs what the stream does not
    reproduce. A file with a Leslie runs twice: a scanning run for the
    loudest row, then the render."""
    if B is None:
        import blockrender as B
    loudest = None
    while True:
        s = Stream(send=send, loudest=loudest, out=out, send_out=send_out)
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


def result(s):
    """What blockrender's main reads after a render (its _LAST_PREP): the room
    sidecar's bands, the sends, the channels heard, and the send bus."""
    room_q = [(f, (d / r) if r > 0.0 else 1.0, d) for f, (d, r) in zip(s.ctx['room_bands'], s.ctx['qacc'])]
    return dict(room_q=room_q, reverb_send=dict(s.ctx['reverb']),
                mch=np.array(sorted(s.heard), np.int32), N=s.N, total=s.ctx['total'],
                mvol=s.ctx['mvol'](),
                stream_send=None if s.send is not True else ((s.SL, s.SR) if s.SL is not None else s.send_path))
