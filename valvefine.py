"""The live valve's FINE PASS, in processes of their own (live.py: Live's
_amp_fine_* and LIVE_FINE_VALVE).

tubeamp.emit at the file renderer's resolution -- a one-second window and 400
products, which resolve the intermodulation products a few Hz apart whose
beating is a distortion's shimmer -- for each chord a live part holds. Run
here and not on a thread: its arithmetic held the audio process's lock and
the fast pass behind it missed the lookahead. A module of its own so a worker
imports the valve and numpy, not the synthesiser.

Oversampled once, not twice: tubeamp's own notes measured 1 and 4 giving the
same error to four figures, 2 kept only as margin; once halves the time a
chord waits for its shimmer.

ON THE GPU where there is one (ampgpu, its own small context: the amp's
program alone, not the synthesiser's): a six-note chord's products in 9 ms
rather than 54, the same to 127 dB, and the cores left to the audio -- the
loop spreads over every one. TUNING_GPU_AMP=0, or no GPU, keeps the loop; a
job the GPU fails is done again on the loop.
"""
import os

FINE_WINDOW_S = 1.0
FINE_KEEP = 400
FINE_OVERSAMPLE = 1


def serve(conn):
    """A worker: (fc, ac, pc, rate, drive, reference, imbalance) in, the
    products out -- ("ok", [(f, a, phase)]) or ("err", why). None stops it."""
    import tubeamp as _TA
    gpu = None
    if os.environ.get("TUNING_GPU_AMP", "1") != "0":
        try:
            import ampgpu
            gpu = ampgpu.AmpGpu()
        except Exception:                          # noqa: BLE001 -- no GPU: the loop
            gpu = None
    while True:
        job = conn.recv()
        if job is None:
            return
        fc, ac, pc, rate, drive, ref, imb = job
        try:
            kw = {} if imb is None else {"imbalance": float(imb)}
            args = (fc, ac, pc, rate, drive)
            kw.update(window_s=FINE_WINDOW_S, oversample=FINE_OVERSAMPLE, keep=FINE_KEEP, reference=ref)
            _TA.GPU[0] = gpu
            try:
                out = _TA.emit(*args, **kw)
            except Exception:                      # noqa: BLE001 -- the loop, and the CPU from now on
                if gpu is None:
                    raise
                gpu = _TA.GPU[0] = None
                out = _TA.emit(*args, **kw)
            conn.send(("ok", out))
        except Exception as e:                     # noqa: BLE001 -- reported, not raised
            conn.send(("err", "%s: %s" % (type(e).__name__, e)))
