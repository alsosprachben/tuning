"""The valve's input sum on the GPU (ampkernel.cl): tubeamp._synth's
sum a cos(2 pi f t + p), for a file render (gpurender.Gpu.amp_sum, on its own
context) and for live's fine-pass workers (valvefine, on a context of their
own). A module of its own so a worker imports OpenCL and numpy, not the
synthesiser, and builds only this program -- not gpukernel's.
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


class AmpGpu:
    """One context (a given one, or the first GPU's), one queue, amp_sum's
    program built on first use."""

    J, NL = 128, 32     # amp_sum's factoring: sample = J*(NL*h + l) + j

    def __init__(self, ctx=None, q=None):
        import pyopencl as cl
        self.cl = cl
        if ctx is None:
            gpus = [d for p in cl.get_platforms() for d in p.get_devices()
                    if d.type & cl.device_type.GPU]
            if not gpus:
                raise RuntimeError("no OpenCL GPU (is intel-opencl-icd installed?)")
            ctx = cl.Context([gpus[0]])
        self.ctx = ctx
        self.q = q if q is not None else cl.CommandQueue(ctx)
        self.k = None

    def amp_sum(self, a, f, p, n, fs):
        """sum a cos(2 pi f t + p), t = arange(n)/fs, as float64. The phasor
        tables are made in double here, so float32 only ever carries a value
        under 1 and its rounding sits about 140 dB under the sum, where the
        valve's products are 60-90 dB down."""
        cl = self.cl
        if self.k is None:
            self.k = cl.Kernel(cl.Program(self.ctx, open(os.path.join(HERE, "ampkernel.cl")).read()).build(),
                               "amp_sum")
        J, NL = self.J, self.NL
        K = len(f)
        nb = -(-n // J)
        nh = -(-nb // NL)
        w = 2.0 * np.pi * np.asarray(f, float) / fs
        cx = lambda ph: np.ascontiguousarray(np.exp(1j * ph).astype(np.complex64))      # noqa: E731
        tabs = (cx(np.outer(np.arange(nh) * float(J * NL), w) + p) * np.asarray(a, np.float32),
                cx(np.outer(np.arange(NL) * float(J), w)),
                cx(np.outer(w, np.arange(J))))
        mf = cl.mem_flags
        bufs = [cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=v) for v in tabs]
        out = np.empty(nb * J, np.float32)
        ob = cl.Buffer(self.ctx, mf.WRITE_ONLY, out.nbytes)
        self.k(self.q, (J, nb), None, np.int32(K), np.int32(J), np.int32(NL), *bufs, ob)
        cl.enqueue_copy(self.q, out, ob)
        return out[:n].astype(np.float64)
