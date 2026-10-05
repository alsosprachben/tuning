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

    __slots__ = ("a", "base")

    def __init__(self, typecode):
        self.a = array(typecode)
        self.base = 0

    def __len__(self):
        return self.base + len(self.a)

    def append(self, x):
        self.a.append(x)

    def extend(self, xs):
        self.a.extend(xs)

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


class NotStreamable(Exception):
    """The file uses a pass the stream does not reproduce yet: render it whole."""


# the passes the stream reproduces, and those it does not yet (the plan's phases)
_UNSUPPORTED = ("sympathetic", "mf104", "tubeamp", "htremolo", "leslie")

# A ROW'S PLACE IN THE WHOLE TABLE, as six int64 fields, sorted with the first
# most significant: (pass, channel rank, cents index, source pass, source row,
# sign). Note rows are (0, 0, 0, 0, row, 0); a tremolo sideband (1, 0, 0, 0,
# its source row, 0 for + and 1 for -), as tremolo.expand appends them, row
# by row; a chorus copy (2, its channel's place in the chorus settings, its
# cents index, and its source's (pass, row, sign)), as chorus.expand appends
# them, channel by channel, offset by offset, row by row. Sorting a window's
# rows by these fields puts them in the order the whole table has them, and
# the kernel sums in table order -- so a window renders bit for bit.
KEYS = ("k_pass", "k_ch", "k_ci", "k_spass", "k_src", "k_sign")


class Stream:
    """prepare(..., sink=Stream()) renders the file as its notes are emitted.

    Each finished note's rows go through the per-row passes (clavinet tone,
    tremolo, chorus, cabinet, in the whole-table order), into a store of rows
    still to sound; every window of whole chunks (blockrender._chunk) the
    notes so far can no longer add to is rendered from the rows live in it,
    sorted into table order, exactly as synth_window renders that chunk of the
    whole table -- bursts, master fader, gain and clip included -- and the rows
    that have ended let go. The reverb send, when the file has one, is a second
    render of each window at each channel's send, as blockrender's send pass.

    Memory is the live rows, not the piece."""

    # WINDOWS RENDERED TOGETHER: the kernel spreads a call's chunks across its
    # threads, and one window is one chunk -- one thread. Eight at a time
    # renders as fast as the whole file did, each chunk exactly as before.
    BATCH = 8

    def __init__(self, send='auto', batch=None):
        # send: True renders the reverb send from the start; 'auto' only once
        # two channels heard so far send differently (blockrender writes a send
        # bus only then) -- and if that comes after windows already rendered
        # without it, the stream is `incomplete` and render() runs it again
        self.want_send = send
        self.batch = batch or self.BATCH
        self.heard = set()          # channels with rows: blockrender's "what actually sounds"
        self.rows_total = 0         # rows rendered, effect copies included
        self.incomplete = False
        self.pending = []           # finished chunks not yet in the store
        self.store = []             # chunks of rows still to sound
        self.rows = 0               # note rows emitted
        self.made = {}              # chorus: channel -> copies made (the dry rule's check)
        self.dried = set()          # chorus: channels whose rows took the dry share
        self.peak_live = 0

    # -- prepare's hooks ------------------------------------------------------
    def begin(self, ctx):
        # the module that is running prepare(): blockrender, or __main__ when
        # blockrender.py is the script -- one copy of its settings, not two
        B = ctx['mod']
        self.B = B
        self.ctx = ctx
        self.N = ctx['N']
        self.W = B._chunk()
        self.L = np.zeros(self.N, np.float32)
        self.R = np.zeros(self.N, np.float32)
        self.send = self.want_send
        self.SL = np.zeros(self.N, np.float32)
        self.SR = np.zeros(self.N, np.float32)
        self.wi = 0                 # the next window to render

    def __call__(self, A, i0, i1, next_on):
        fx = self.ctx['effects']
        for k in _UNSUPPORTED:
            if fx[k]:
                raise NotStreamable(k)
        if i1 > i0:
            r = {k: A[k].rows(i0, i1) for k in A}
            for k in A:
                A[k].drop_to(i1)
            self.rows += i1 - i0
            r.update({k: np.zeros(i1 - i0, np.int64) for k in KEYS})
            r['k_src'][:] = np.arange(i0, i1)
            self.heard.update(int(c) for c in np.unique(r['mch']))
            out = self._passes(r)
            self.rows_total += len(out['om'])
            self.pending.append(out)
        else:
            for k in A:
                A[k].drop_to(i1)
        # every window ending at or before the next note's onset is complete
        limit = self.N if next_on is None else min(next_on, self.N)
        while (self.wi + self.batch) * self.W <= limit or (next_on is None and self.wi * self.W < self.N):
            self._render(self.wi, self.batch)
            self.wi += self.batch

    # -- the per-row passes, in blockrender's order ---------------------------
    def _passes(self, r):
        import tonelib as T
        fx = self.ctx['effects']
        # CLAVINET TONE: a filter on each row's frequency, in place
        for ch, setting in fx['clavinet'].items():
            sel = r['mch'] == ch
            if sel.any():
                g = T.clav_tone_gain(r['nf'][sel].astype(np.float64), setting)
                for col in ('aL', 'aR', 'aM'):
                    v = r[col]; v[sel] *= g
        parts = [r]
        tr = self._tremolo(r, fx['tremolo'])
        if tr is not None:
            parts.append(tr)
        ch_out = self._chorus(parts, fx['chorus'])
        if ch_out is not None:
            parts.append(ch_out)
        out = {k: np.concatenate([p[k] for p in parts]) for k in r} if len(parts) > 1 else r
        # CABINET: a loudspeaker's gain on each row's frequency, in place
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
        out['zend'] = self._zend(out)
        out['nonL'] = out['non'].astype(np.int64)
        return out

    def _tremolo(self, r, channels):
        """tremolo.expand's sideband pairs for these rows."""
        import math
        import random as _random
        import tremolo as TR
        if not TR.ENABLED or not channels:
            return None
        n = len(r['om'])
        src, sgn, dws, phs, halfs, stereos = [], [], [], [], [], []
        mch, pl = r['mch'], r['pl']
        for i in range(n):
            cfg = channels.get(int(mch[i]))
            if cfg is None:
                continue
            if len(cfg) == 4:
                rate, depth, stereo, scatter = cfg
            else:
                rate, depth, stereo = cfg
                scatter = 0.0
            if depth <= 0.0 or rate <= 0.0:
                continue
            ph = 0.0
            if scatter > 0.0:
                rng = _random.Random(0x7E30 + int(mch[i]) * 977 + int(pl[i]))
                rate = rate * (1.0 + scatter * rng.uniform(-1.0, 1.0))
                ph = rng.uniform(0.0, 2.0 * math.pi)
            dw = 2.0 * math.pi * rate / self.B.SR
            for si, sign in enumerate((1.0, -1.0)):
                src.append(i); sgn.append(si)
                dws.append(sign * dw); phs.append(sign * ph if ph else None)
                halfs.append(0.5 * depth); stereos.append(stereo)
        if not src:
            return None
        src = np.array(src)
        out = {k: v[src].copy() for k, v in r.items()}
        out['om'] = r['om'][src] + np.array(dws)
        ph = np.array([0.0 if p is None else p for p in phs])
        hasph = np.array([p is not None for p in phs])
        if hasph.any():
            out['p0'][hasph] = r['p0'][src][hasph] + ph[hasph]
            out['p0R'][hasph] = r['p0R'][src][hasph] + ph[hasph]
        half = np.array(halfs); st = np.array(stereos, bool)
        out['aL'] = r['aL'][src] * half
        out['aR'] = r['aR'][src] * np.where(st, -half, half)
        out['aM'] = np.where(st, 0.0, r['aM'][src] * half)
        for k in KEYS:
            out[k] = np.zeros(len(src), np.int64)
        out['k_pass'][:] = 1
        out['k_src'][:] = r['k_src'][src]
        out['k_sign'][:] = np.array(sgn)
        return out

    def _chorus(self, parts, channels):
        """chorus.expand's copies of these rows (note rows and their tremolo
        sidebands), and the dry share taken from them, in place."""
        import chorus as CH
        if not channels:
            return None
        order = list(channels)          # insertion order: as the whole pass walks them
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
                    o['om'] = om * ratio
                    o['nf'] = p['nf'][keep].astype(np.float64) * ratio
                    o['p0'] = p0 * ratio - om * ratio * CH.DELAY_S[ci % len(CH.DELAY_S)] * self.B.SR
                    o['p0R'] = p0R * ratio - om * ratio * CH.DELAY_S[ci % len(CH.DELAY_S)] * self.B.SR
                    o['aL'] = p['aL'][keep] * wet
                    o['aR'] = p['aR'][keep] * wet
                    o['aM'] = p['aM'][keep] * wet
                    o['vd'] = np.full(len(keep), CH.SWEEP_DEPTH, np.float64)
                    o['vr'] = np.full(len(keep), CH.SWEEP_HZ[ci % len(CH.SWEEP_HZ)], np.float64)
                    o['vp'] = np.full(len(keep), 2.0 * np.pi * (ci / float(len(cents))), np.float64)
                    o['k_pass'] = np.full(len(keep), 2, np.int64)
                    o['k_ch'] = np.full(len(keep), order.index(ch), np.int64)
                    o['k_ci'] = np.full(len(keep), ci, np.int64)
                    o['k_spass'] = p['k_pass'][keep].copy()
                    o['k_src'] = p['k_src'][keep].copy()
                    o['k_sign'] = p['k_sign'][keep].copy()
                    outs.append(o)
                    made += len(keep)
            self.made[ch] = self.made.get(ch, 0) + made
            # the dry share, which chorus.expand takes when ANY copy has been
            # made by then -- assumed here, checked at the end (check_chorus)
            if dry != 1.0:
                self.dried.add(ch)
                for p, rows in zip(parts, sels):
                    if len(rows):
                        for col in ('aL', 'aR', 'aM'):
                            p[col][rows] = p[col][rows] * dry
        if not outs:
            return None
        return {k: np.concatenate([o[k] for o in outs]) for k in outs[0]}

    def check_chorus(self):
        """chorus.expand dries a channel only once some copy exists (its
        `made` counts across the channels walked so far). Every file has had
        one; a file where a dried channel came first and made none would not
        stream exactly, and is reported, not hidden."""
        chans = self.ctx['effects']['chorus']
        total = 0
        for ch in chans:
            total += self.made.get(ch, 0)
            if ch in self.dried and total == 0:
                raise RuntimeError("chorus: channel %d dried before any copy existed" % ch)

    # -- the store and the windows --------------------------------------------
    def _zend(self, r):
        f4 = np.float32
        dl = np.maximum(f4(0.0), np.maximum(r['delL'].astype(f4), r['delR'].astype(f4)))
        return (r['noff'].astype(np.int64) + r['re'].astype(f4).astype(np.int64)
                + np.ceil(dl).astype(np.int64) + self.B.BLK)

    def _render(self, wi, nw=1):
        """Windows wi .. wi+nw-1 in one kernel call."""
        B = self.B
        if self.pending:
            self.store.extend(self.pending)
            self.pending = []
        w0 = wi * self.W
        w1 = min(self.N, w0 + nw * self.W)
        if w1 <= w0:
            return
        sel = []
        for c in self.store:
            m = (c['nonL'] < w1) & (c['zend'] > w0)
            if m.any():
                sel.append({k: v[m] for k, v in c.items()})
        # the rows that will never sound again go
        self.store = [c for c in self.store if c['zend'].max() > w1]
        if not sel:
            return
        rows = {k: np.concatenate([s[k] for s in sel]) for k in sel[0]}
        order = np.lexsort(tuple(rows[k] for k in reversed(KEYS)))
        P = len(order)
        self.peak_live = max(self.peak_live, P)
        prep = dict(lib=self.ctx['lib'], P=P, N=self.N, nblk=self.ctx['nblk'], sh=self.ctx['sh'],
                    G=self.ctx['G'], S=self.ctx['S'], BR=self.ctx['BR'], BC=self.ctx['BC'],
                    knk=1, kb0=0, **self.ctx['moog_tables']())
        for k, dt in B.FINAL_DTYPES:
            prep[k] = np.ascontiguousarray(rows[k][order].astype(dt))
        n = w1 - w0
        L = np.zeros(n, np.float32); R = np.zeros(n, np.float32)
        B.synth_partials(prep, w0, n, 0, P, L, R)
        # synth_window's own finishing, on this window
        B._NG.mix(L, R, w0, self.ctx['cons_bursts'], B.SR)
        mg = B.master_curve(self.ctx['mvol'](), w0, n)
        if mg is not None:
            L *= mg; R *= mg
        L *= T_master_gain(); R *= T_master_gain()
        np.clip(L, -1, 1, L); np.clip(R, -1, 1, R)
        self.L[w0:w1] = L; self.R[w0:w1] = R
        if self.send == 'auto' and self._split():
            self.send = True
            self.incomplete = wi > 0
        if self.send is True:
            # THE SEND: the same rows at each channel's send, as the whole
            # table's second render takes them (aL, aR in float32 times g)
            rs = self.ctx['reverb']
            g = np.ones(P, np.float32)
            for c, v in rs.items():
                g[prep['mch'] == c] = v
            prep['aL'] = prep['aL'] * g
            prep['aR'] = prep['aR'] * g
            SL = np.zeros(n, np.float32); SR_ = np.zeros(n, np.float32)
            B.synth_partials(prep, w0, n, 0, P, SL, SR_)
            if mg is not None:
                SL *= mg; SR_ *= mg
            self.SL[w0:w1] = SL; self.SR[w0:w1] = SR_


Stream._split = lambda self: len({self.ctx['reverb'].get(c, 1.0) for c in self.heard}) > 1 \
    if self.ctx['reverb'] else False


def T_master_gain():
    import tonelib as T
    return T.master_gain


def render(path, tuner, send='auto', B=None):
    """A whole file, streamed: (L, R, the stream). Raises NotStreamable when
    the file uses a pass the stream does not reproduce yet. s.SL/s.SR hold the
    reverb send when s.send is True (the channels heard send differently).
    B: the blockrender module to run (blockrender's own render passes itself)."""
    if B is None:
        import blockrender as B
    s = Stream(send=send)
    info = B.prepare(path, tuner, sink=s)
    if s.incomplete:                # the send was needed after all: again, with it
        s = Stream(send=True)
        info = B.prepare(path, tuner, sink=s)
    s.check_chorus()
    s.info = info
    return s.L, s.R, s


def result(s):
    """What blockrender's main reads after a render (its _LAST_PREP): the room
    sidecar's bands, the sends, the channels heard, and the send bus."""
    room_q = [(f, (d / r) if r > 0.0 else 1.0, d) for f, (d, r) in zip(s.ctx['room_bands'], s.ctx['qacc'])]
    return dict(room_q=room_q, reverb_send=dict(s.ctx['reverb']),
                mch=np.array(sorted(s.heard), np.int32), N=s.N, total=s.ctx['total'],
                mvol=s.ctx['mvol'](), stream_send=(s.SL, s.SR) if s.send is True else None)
