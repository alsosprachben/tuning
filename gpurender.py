"""The GPU renderer's two halves: the block setup on the CPU, the samples on the GPU.

A live block is two kinds of work (voicedesc.h): once a partial, the setup --
amplitude, chiff fade, vibrato and bends, the Moog's ladder on its grid, the
phasor's anchor, which is where the doubles are -- and then once a sample, the
oscillator and everything that turns with it. BlockTables runs the first on
the CPU (voice_block, the very source synth_voice runs, OpenMP across
partials) into a table of descriptors; Gpu runs the second over that table
with OpenCL (gpukernel.cl). Without OpenCL the same descriptors run through
the C reference (voice_samples), which is how a machine without a GPU still
checks the setup.

live.GpuRenderer drives both, one block at a time.
"""
import ctypes
import os
import zlib

import numpy as np

import blockrender as B

HERE = os.path.dirname(os.path.abspath(__file__))

# voicedesc.h's structs, field for field (checked against the C and the GPU
# compiler's sizeof when the library and the program load)
VDESC = np.dtype([("chk_hi", "u8"), ("chk_lo", "u8"), ("nk_hi", "u8"), ("nk_lo", "u8"), ("nseed", "u8"),
                  ("ns", "i4"), ("ne", "i4"), ("kind", "i4"), ("flags", "i4"), ("cell", "i4"), ("kn", "i4"),
                  ("ka", "i4"), ("knR", "i4"), ("kaR", "i4"), ("kpad", "i4"),
                  ("zLr", "f4"), ("zLi", "f4"), ("zRr", "f4"), ("zRi", "f4"), ("winst", "f4"),
                  ("mL0", "f4"), ("mL1", "f4"), ("mR0", "f4"), ("mR1", "f4"),
                  ("aL", "f4"), ("aR", "f4"), ("aLp", "f4"), ("aRp", "f4"),
                  ("jfa", "f4"), ("cc", "f4"), ("swp", "f4"), ("kgL", "f4"), ("kgR", "f4"),
                  ("za", "f4", 12), ("lg", "f4", 5), ("xr", "f4")])
VCELL = np.dtype([("s0", "i4"), ("s1", "i4"), ("sb", "i4"), ("nsb", "i4"),
                  ("g", "f4", 4), ("c", "f4", 4), ("z", "f4", 4), ("wc", "f4"),
                  ("z1r", "f4"), ("z1i", "f4"), ("th1", "f4"), ("fmkI", "f4"),
                  ("B", "f4", 16), ("pad", "f4", 3)])
VSB = np.dtype([("g0r", "f4"), ("g0i", "f4"), ("dgr", "f4"), ("dgi", "f4"),
                ("pzr", "f4"), ("pzi", "f4"), ("th", "f4"), ("pad", "f4")])

VD_NOISE, VD_SHAPE, VD_FMO, VD_FMS, VD_PM = 1, 2, 4, 8, 16
# a group of a file's window (gpukernel.cl voices_win): descriptors [d0, d1),
# its block's offset into the window
VGROUP = np.dtype([("d0", "i4"), ("d1", "i4"), ("off", "i4"), ("pad", "i4")])


def aligned_zeros(n, dtype):
    """n records of dtype in page-aligned memory, a whole number of pages: what
    the Iris will read in place (CL_MEM_USE_HOST_PTR) rather than copy. The
    array may hold more than n."""
    dtype = np.dtype(dtype)
    # whole pages AND whole records: a 176-byte descriptor does not divide
    # most page multiples, so the count is rounded to lcm(4096, size)
    import math
    per = math.lcm(4096, dtype.itemsize) // dtype.itemsize
    n = max(-(-max(n, 1) // per) * per, per)
    nbytes = n * dtype.itemsize
    raw = np.zeros(nbytes + 4096, np.uint8)
    off = (-raw.ctypes.data) % 4096
    return raw[off:off + nbytes].view(dtype)


def moog_grid(blk):
    """synth_voice's grid: MOOG_GRID samples when the block is a multiple of it."""
    return 128 if (blk % 128 == 0 and blk // 128 <= 64) else blk


class BlockTables:
    """The descriptors for one block, from voice_block. The tables grow when a
    block asks for more cells or sidebands than they hold, and the block is
    set up again -- never a write past their end."""

    def __init__(self, nthreads=4):
        self.lib = B.ensure_gpu_lib()
        s = (ctypes.c_int * 3)()
        self.lib.voice_sizes(s)
        if (s[0], s[1], s[2]) != (VDESC.itemsize, VCELL.itemsize, VSB.itemsize):
            raise RuntimeError("voicedesc.h and gpurender.py disagree on the layout: C %s, numpy %s"
                               % (tuple(s), (VDESC.itemsize, VCELL.itemsize, VSB.itemsize)))
        self.nthreads = int(nthreads)
        # page-aligned, so the GPU reads them where voice_block wrote them
        self.D = aligned_zeros(1024, VDESC)
        self.C = aligned_zeros(1024, VCELL)
        self.SB = aligned_zeros(1 << 14, VSB)
        self.counts = np.zeros(2, np.int32)
        self.nact = self.ncell = self.nsb = 0

    def setup(self, prep, idx, n0, send, args=None, nb=1, D=None):
        """Descriptors for the partials idx (int64 slot numbers) over nb blocks
        from n0, which must be a multiple of B.BLK: D[blk*len(idx) + i]. args:
        B._voice_args for prep, made once by a caller that sets up many
        blocks; D: the table to write (else this one's own, grown to fit)."""
        nact = len(idx)
        if D is None:
            if nact * nb > len(self.D):
                self.D = aligned_zeros(max(nact * nb, 2 * len(self.D)), VDESC)
            D = self.D
        P = prep['P']
        sl = lambda k: prep[k]                     # noqa: E731
        vp = ctypes.c_void_p
        while True:
            r = self.lib.voice_block(
                ctypes.c_long(n0), *(args or B._voice_args(prep, sl, P)),
                prep['sw'].ctypes.data_as(ctypes.POINTER(ctypes.c_float)), int(bool(send)),
                idx.ctypes.data_as(ctypes.POINTER(ctypes.c_long)), nact,
                vp(D.ctypes.data), vp(self.C.ctypes.data), len(self.C),
                vp(self.SB.ctypes.data), len(self.SB), self.nthreads,
                self.counts.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), int(nb))
            if r == 0:
                break
            nc, ns = int(self.counts[0]), int(self.counts[1])
            if nc > len(self.C):
                self.C = aligned_zeros(2 * nc, VCELL)
            if ns > len(self.SB):
                self.SB = aligned_zeros(2 * ns, VSB)
        self.nact, self.ncell, self.nsb = nact, int(self.counts[0]), int(self.counts[1])

    def samples_c(self, n0, frames, send):
        """The sample pass in C (voice_samples): (L, R, SL, SR), unscaled."""
        out = [np.zeros(frames, np.float32) for _ in range(4)]
        fp = lambda x: x.ctypes.data_as(ctypes.POINTER(ctypes.c_float))    # noqa: E731
        vp = ctypes.c_void_p
        self.lib.voice_samples(ctypes.c_long(n0), B.BLK, self.nact, vp(self.D.ctypes.data),
                               vp(self.C.ctypes.data), vp(self.SB.ctypes.data),
                               fp(out[0]), fp(out[1]),
                               fp(out[2]) if send else None, fp(out[3]) if send else None)
        return out


class Gpu:
    """The OpenCL half: one context, one queue, the program built once and its
    kernel kept (a cl.Kernel made per call was the GPU bench's whole fixed
    cost).

    THE TABLES ARE NOT COPIED. On the Iris the GPU and the CPU share memory, and
    a buffer made over page-aligned host memory (CL_MEM_USE_HOST_PTR) is read in
    place: voice_block writes the descriptors and the kernel reads those very
    bytes. Copying them was 0.14 ms a block at 4 500 partials, and mapping them
    in and out 0.1 ms a map -- either as much as the kernel. A buffer is made
    again only when its table grows (a new array), and the kernel's arguments
    are set once and then only the block's own (n0, the count) each time:
    pyopencl's conversion of the full set was 0.08 ms."""

    LK, LG = 16, 8          # a work-group: 16 samples by 8 groups of descriptors

    def __init__(self, device=None):
        import pyopencl as cl
        self.cl = cl
        dev = device
        if dev is None:
            gpus = [d for p in cl.get_platforms() for d in p.get_devices()
                    if d.type & cl.device_type.GPU]
            if not gpus:
                raise RuntimeError("no OpenCL GPU (is intel-opencl-icd installed?)")
            dev = gpus[0]
        self.device = dev
        self.name = dev.name
        self.ctx = cl.Context([dev])
        self.q = cl.CommandQueue(self.ctx)
        src = open(os.path.join(HERE, "gpukernel.cl")).read()
        # the header comes in through -I, so pyopencl's cache cannot see it
        # change: its checksum goes into the source the cache keys on
        hdr = open(os.path.join(HERE, "voicedesc.h")).read()
        src = "// voicedesc.h %08x\n" % zlib.crc32(hdr.encode()) + src
        self.prg = cl.Program(self.ctx, src).build(options=["-I", HERE])
        self.k = cl.Kernel(self.prg, "voices")
        sz = np.zeros(3, np.int32)
        b = cl.Buffer(self.ctx, cl.mem_flags.WRITE_ONLY, sz.nbytes)
        k = cl.Kernel(self.prg, "sizes")
        k.set_args(b)
        cl.enqueue_nd_range_kernel(self.q, k, (1,), None)
        cl.enqueue_copy(self.q, sz, b)
        if tuple(sz) != (VDESC.itemsize, VCELL.itemsize, VSB.itemsize):
            raise RuntimeError("the GPU compiler lays voicedesc.h out as %s, the host as %s"
                               % (tuple(sz), (VDESC.itemsize, VCELL.itemsize, VSB.itemsize)))
        self.k.set_arg(10, cl.LocalMemory(4 * self.LG * self.LK * 4))
        self.over = {}          # table name -> (the host array, its buffer)
        self.acc = None
        self.res = None
        self.shape = None

    def _over(self, i, name, arr):
        """Argument i: a buffer over arr, made again only when arr is new."""
        held = self.over.get(name)
        if held is None or held[0] is not arr:
            cl = self.cl
            raw = arr.view(np.uint8)
            b = cl.Buffer(self.ctx, cl.mem_flags.READ_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=raw)
            self.over[name] = (arr, b)
            self.k.set_arg(i, b)

    def samples(self, tab, n0, frames, send):
        """The sample pass on the GPU over tab's descriptors: (L, R, SL, SR)."""
        cl = self.cl
        nd = tab.nact
        self._over(6, "D", tab.D)
        self._over(7, "C", tab.C)
        self._over(8, "S", tab.SB)
        # enough groups to fill the device; a whole number of work-groups
        per = max(2, -(-nd // 1024))
        groups = max(1, -(-nd // per))
        groups = -(-groups // self.LG) * self.LG
        NG = groups // self.LG
        shape = (NG, frames)
        if self.shape != shape:
            self.acc = cl.Buffer(self.ctx, cl.mem_flags.WRITE_ONLY, 4 * NG * frames * 4)
            self.res = np.empty((4, NG, frames), np.float32)
            self.k.set_arg(9, self.acc)
            self.k.set_arg(2, np.int32(frames))
            self.k.set_arg(3, np.int32(moog_grid(frames)))
            self.shape = shape
        self.k.set_arg(0, np.int32(nd))
        self.k.set_arg(1, np.int32(per))
        self.k.set_arg(4, np.uint64(n0))
        self.k.set_arg(5, np.int32(1 if send else 0))
        lk = self.LK if frames % self.LK == 0 else 1
        cl.enqueue_nd_range_kernel(self.q, self.k, (frames, groups), (lk, self.LG))
        cl.enqueue_copy(self.q, self.res, self.acc)        # blocking: the block is done
        out = self.res.sum(1)
        return [out[c] for c in range(4)]


class _Window:
    """One window's tables, in page-aligned memory the GPU reads in place,
    and the buffers over them. Two take turns, so one can be filled while the
    GPU reads the other."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.D = aligned_zeros(1 << 16, VDESC)
        self.C = aligned_zeros(1 << 12, VCELL)
        self.S = aligned_zeros(1 << 14, VSB)
        self.G = aligned_zeros(1 << 12, VGROUP)
        self.bufs = {}
        self.pending = None             # (event, result, window start, its blocks' work-groups)

    def buf(self, name):
        cl = __import__("pyopencl")
        arr = getattr(self, name)
        held = self.bufs.get(name)
        if held is None or held[0] is not arr:
            held = (arr, cl.Buffer(self.ctx, cl.mem_flags.READ_ONLY | cl.mem_flags.USE_HOST_PTR,
                                   hostbuf=arr.view(np.uint8)))
            self.bufs[name] = held
        return held[1]

    def room(self, name, n, cap=None):
        """The table `name`, grown (contents kept) to hold n records -- by
        doubling, but past `cap` records only as far as asked."""
        arr = getattr(self, name)
        if n > len(arr):
            grow = 2 * len(arr) if cap is None else min(2 * len(arr), cap)
            new = aligned_zeros(max(n, grow), arr.dtype)
            new[:len(arr)] = arr
            setattr(self, name, new)
        return getattr(self, name)


class FileRenderer:
    """A whole file on the GPU: blockrender.synth_window's work for --gpu.

    The file is walked a WINDOW of blocks at a time. For each block the
    partials sounding in it are found by onset (a sweep over the table sorted
    by note-on), set up by voice_block exactly as live's are, and the silent
    ones dropped; the window's blocks then go to the GPU in one launch
    (voices_win), every work-group within one block. The file's 512-sample
    blocks are why the descriptors carry a carrier anchor every V_SUB (128)
    samples (voicedesc.h).

    THE TWO HALVES OVERLAP: two windows' tables take turns, and while the GPU
    renders one the CPU sets up the next. voice_block's arguments -- the
    table's 45 columns as pointers -- are made once a render, not once a block.

    Not bit-identical to the CPU render -- the phasors are evaluated, not
    turned, and summed in another order -- so it is never the default: the
    corpus and bitident stay on synth_window's CPU path.
    """

    LK, LG = 16, 8

    # A ROW LEAVES THE ACTIVE SET WHEN IT FALLS SILENT, not at its note's end:
    # a one-shot's rows (a gong, a crash, every reflection and bloom copy of
    # them) run to a long nominal noff, and every window set up a descriptor
    # for each of them, every block -- on Tokei's gong roll a row's nominal
    # span was 7.9 s (median) and its audible one 1.5 s, the active set 2.3x
    # what sounds, and the descriptor table (rows x blocks) with it. Under
    # RETIRE_FLOOR -- -120 dB, 20 dB under the renderer's RING_FLOOR, so that
    # tens of thousands retired together still sum far under hearing -- a row
    # is done. The CPU path keeps every row (its hashes are the corpus's).
    RETIRE_FLOOR = 1e-6
    BEND_RETIRE_FLOOR = 3e-7         # rows on a bend row: see _audible_end
    # A WINDOW'S DESCRIPTORS HAVE A BUDGET: active rows x blocks, 184 bytes
    # each. Tokei at 3:44 had ~590 000 rows sounding, and 32 blocks of them
    # asked for a table past the 3.25 GB the Iris allocates in one buffer --
    # the render died there after 55 minutes (and two such tables, one a
    # window, are what a 7.5 GB laptop cannot hold). Past the budget a window
    # takes fewer blocks, down to one: memory bounded however dense the file.
    DESC_BUDGET = 768 << 20

    def __init__(self, prep, gpu=None, window_blocks=32, setup_threads=None):
        cl = __import__("pyopencl")
        self.cl = cl
        if B.BLK % 128 or B.BLK > 4 * 128:
            raise ValueError("the GPU file renderer needs a block of 128..512 samples (V_SUB anchors)")
        self.prep = prep
        self.gpu = gpu or Gpu()
        self.k = cl.Kernel(self.gpu.prg, "voices_win")
        self.k.set_arg(9, cl.LocalMemory(4 * self.LG * self.LK * 4))
        self.W = int(window_blocks)
        # every core for the descriptors (voice_block is OpenMP); 4 was
        # half this laptop's
        self.tab = BlockTables(setup_threads or os.cpu_count() or 4)
        non = np.asarray(prep['non'], np.int64)
        self.order = np.argsort(non, kind='stable')
        self.onset = non[self.order]
        # as voice_partial.inc ends a partial: noff + (long)relS + the later
        # ear's delay, rounded up + BLK
        dl = np.maximum(0.0, np.maximum(np.asarray(prep['delL'], np.float32),
                                        np.asarray(prep['delR'], np.float32)))
        self.end = (np.asarray(prep['noff'], np.int64)
                    + np.asarray(prep['re'], np.float32).astype(np.int64)
                    + np.ceil(dl).astype(np.int64) + B.BLK)
        self.end = np.minimum(self.end, self._audible_end(prep, non, dl))
        self.wins = [_Window(self.gpu.ctx), _Window(self.gpu.ctx)]

    def _audible_end(self, prep, non, dl):
        """Each row's last sample above RETIRE_FLOOR (BEND_RETIRE_FLOOR for a
        row on a bend row), from its level and its
        two decay rates (the kernel's law, as blockrender.ring_last reads
        it); a row that never falls (a sustain, no decay) keeps its end."""
        P = len(non)
        g = lambda k: np.asarray(prep[k], np.float64)[:P]     # noqa: E731
        a = np.maximum(np.abs(g('aL')), np.abs(g('aR')))
        # A BEND ROW CHANGES A ROW'S LEVEL ONLY THROUGH BL (voice_partial.inc:
        # BLrow, a wind's level or a tremulant, multiplying the law) -- the
        # pitch itself leaves it alone. So such a row retires by its own law
        # times the most BL it will meet from its onset on: an upper bound,
        # and 1 where there is no BL at all. Kept to the nominal end instead,
        # half of Tokei's setup (51% of its block descriptors) was rows on a
        # pitch-bend row ringing on below -120 dB.
        #
        # ...AT THEIR OWN FLOOR, BEND_RETIRE_FLOOR. 89% of Tokei's rows ride a
        # bend row, so their retirement sets the GPU's agreement with the CPU,
        # and it follows the floor (the residue is the retired rows' sum,
        # ~25 000 at once): measured on its first 20 s against the CPU,
        # never retired 25.1 s and -102 dB; 3e-8 24.2 s, -99; 1e-7 21.7 s,
        # -90; 3e-7 15.6 s, -79; 1e-6 14.7 s, -68. 3e-7 is the curve's knee:
        # nearly all the speed, inside the paths' usual -66..-80 dB.
        lift = np.ones(P)
        Fr = np.full(P, float(self.RETIRE_FLOOR))
        if 'br' in prep:
            br = np.asarray(prep['br'])[:P]
            on = br >= 0
            Fr[on] = self.BEND_RETIRE_FLOOR
            BL = prep.get('BL')
            if BL is not None and on.any():
                sm = np.maximum.accumulate(np.asarray(BL)[:, ::-1], axis=1)[:, ::-1]
                bb = np.minimum(np.asarray(non)[on] // B.BLK, sm.shape[1] - 1)
                lift[on] = np.maximum(sm[br[on], bb], 0.0)
        # a moving filter can lift a row too, at most fmx (efxfilter.peak)
        if prep.get('FCT') is not None and 'fmx' in prep:
            lift = lift * np.where(np.asarray(prep['fsr'])[:P] >= 0, np.asarray(prep['fmx'], np.float64)[:P], 1.0)
        # a rotor row's lobe peaks at lnm times its level (leslie.lobe_columns)
        if prep.get('LANG') is not None:
            lift = lift * np.where(np.asarray(prep['lsr'])[:P] >= 0, np.asarray(prep['lnm'], np.float64)[:P], 1.0)
        a = a * lift
        sl, af, lr, lrA = g('sus'), g('aft'), g('logr'), g('logrA')
        F = Fr

        # A ROW THAT GROWS (a negative rate: a reversed voice's swell, begun
        # 100 dB under its arrival) is never silent for good, however far
        # under the floor it starts: it keeps its nominal end. Retired at its
        # onset, a reversed hat lost its whole swell and was a click.
        def t_to(c, rate):
            with np.errstate(divide='ignore', invalid='ignore'):
                return np.where(rate < 0.0, np.inf,
                                np.where(c <= F, 0.0, np.where(rate > 0.0, np.log(np.maximum(c, F) / F)
                                                               / np.where(rate > 0.0, rate, 1.0), np.inf)))
        t = np.maximum(t_to((1.0 - sl) * (1.0 - af) * a, lr), t_to((1.0 - sl) * af * a, lrA))
        t = np.where(sl * a > F, np.inf, t)
        # ...but only where the row's level IS that law: a Moog row's comes
        # from its filter (fx), an organ's gate and swell (gr) -- those keep
        # their nominal end (a bend row's BL is bounded above, in `lift`)
        for k in ('fx', 'gr'):
            if k in prep:
                t = np.where(np.asarray(prep[k])[:P] >= 0, np.inf, t)
        big = np.iinfo(np.int64).max // 4
        return np.where(np.isfinite(t), non + (np.minimum(t, 1e6) * B.SR).astype(np.int64)
                        + np.ceil(dl).astype(np.int64) + 2 * B.BLK, big)

    def render(self, N, send_w=None, n0=0):
        """Samples [n0, N): (L, R, SL, SR), unscaled -- synth_partials' output.
        send_w: per-partial send weights (the reverb bus), or None. n0, a
        multiple of the block: where to start (the stream renders a batch of
        windows at a time)."""
        prep, BLK, W = self.prep, B.BLK, self.W
        assert n0 % BLK == 0
        self.n0 = n0
        send = send_w is not None
        prep['sw'] = (np.ascontiguousarray(send_w, np.float32) if send
                      else np.zeros(1, np.float32))
        self.args = B._voice_args(prep, lambda k: prep[k], prep['P'])
        out = np.zeros((4, N - n0), np.float32)
        mg = moog_grid(BLK)
        nb = -(-N // BLK)
        self.ptr, self.active = 0, np.zeros(0, np.int64)
        turn = 0
        wb = n0 // BLK
        while wb < nb:
            w = self.wins[turn]
            if w.pending:                   # this window's last launch, done first
                self._collect(w, out, N)
            # the window may come back shorter than asked (DESC_BUDGET)
            ng, blk_wg, wb1 = self._fill(w, wb, min(nb, wb + W), send)
            if ng:
                self._launch(w, wb, ng, blk_wg, mg, send)
            turn ^= 1
            wb = wb1
        for w in self.wins:
            if w.pending:
                self._collect(w, out, N)
        return out[0], out[1], out[2], out[3]

    def _fill(self, w, b0, b1, send):
        """Set up blocks [b0, b1) into window w's tables, in ONE call
        (voice_block over nb blocks): (groups, work-groups per block).

        The window's partials are every one sounding anywhere in it -- the
        sweep runs once a window, not once a block -- and a partial silent in a given block
        is a kind-0 row, which voice_pack packs away in C: pruning them in
        Python, block by block, was two thirds of the render."""
        prep, BLK, t = self.prep, B.BLK, self.tab
        nb = b1 - b0
        w0, w1 = b0 * BLK, b1 * BLK
        hi = np.searchsorted(self.onset, w1, 'left')
        if hi > self.ptr:
            self.active = np.concatenate([self.active, self.order[self.ptr:hi]])
            self.ptr = hi
        if len(self.active):
            self.active = self.active[self.end[self.active] > w0]
        nact = len(self.active)
        if not nact:
            return 0, [0] * nb, b1
        cap = max(nact, self.DESC_BUDGET // VDESC.itemsize)
        if nact * nb > cap:
            # fewer blocks, so the table stays inside its budget (rows that
            # begin after the shortened window are already in the active set,
            # silent in these blocks -- kind 0, packed away)
            nb = max(1, cap // nact)
            b1 = b0 + nb
        D = w.room('D', nact * nb, cap=cap)
        t.C, t.SB = w.C, w.S                # the window's own, so the GPU may
        t.setup(prep, self.active, w0, send, self.args, nb=nb, D=D)   # read the last
        w.C, w.S = t.C, t.SB                # (grown, if the window needed more)
        m = np.zeros(nb, np.int32)
        t.lib.voice_pack(ctypes.c_void_p(D.ctypes.data), nact, nb,
                         m.ctypes.data_as(ctypes.POINTER(ctypes.c_int)))
        # each block's sounding rows split into groups, padded to whole
        # work-groups: enough to fill the device, a sum short enough
        m = m.astype(np.int64)
        per = np.maximum(2, -(-m // 256))
        gn = -(-m // per)
        gn = -(-gn // self.LG) * self.LG
        ng = int(gn.sum())
        if not ng:
            return 0, [0] * nb, b1
        G = w.room('G', ng)
        blk = np.repeat(np.arange(nb), gn)
        j = np.arange(ng) - np.repeat(np.cumsum(gn) - gn, gn)
        pb, mb = per[blk], m[blk]
        g = G[:ng]
        g['d0'] = blk * nact + np.minimum(mb, j * pb)
        g['d1'] = blk * nact + np.minimum(mb, (j + 1) * pb)
        g['off'] = blk * BLK
        return ng, list(gn // self.LG), b1

    def _launch(self, w, wb, ng, blk_wg, mg, send):
        cl, BLK = self.cl, B.BLK
        nwg = ng // self.LG
        acc = cl.Buffer(self.gpu.ctx, cl.mem_flags.WRITE_ONLY, 4 * nwg * BLK * 4)
        self.k.set_args(np.int32(BLK), np.int32(mg), np.uint64(wb * BLK), np.int32(1 if send else 0),
                        w.buf('G'), w.buf('D'), w.buf('C'), w.buf('S'), acc,
                        self.cl.LocalMemory(4 * self.LG * self.LK * 4))
        cl.enqueue_nd_range_kernel(self.gpu.q, self.k, (BLK, ng), (self.LK, self.LG))
        res = np.empty((4, nwg, BLK), np.float32)
        ev = cl.enqueue_copy(self.gpu.q, res, acc, is_blocking=False)
        w.pending = (ev, res, wb, blk_wg)

    def _collect(self, w, out, N):
        """Wait for window w's launch and add its blocks into out."""
        BLK = B.BLK
        ev, res, wb, blk_wg = w.pending
        ev.wait()
        w.pending = None
        # each block's work-groups summed: a block with none is silent
        s0 = 0
        for j, n in enumerate(blk_wg):
            if n:
                a = (wb + j) * BLK - self.n0
                e = min(N - self.n0, a + BLK)
                out[:, a:e] += res[:, s0:s0 + n, :e - a].sum(1)
            s0 += n
