"""Live's valve IN STEP, for the checks (livepart_check, nvlive_check).

live.Live answers its valve on threads -- the fast pass on one, the fine
pass in worker processes (valvefine) -- so when a chord's products land
depends on the machine. sync(lv) stops those threads and answers each job
as the pump posts it, both passes at once, on the CPU (tubeamp.GPU off; the
fine pass at valvefine's resolution): the next pump places the fast pass's
products, then the fine pass's over them -- the schedule the native part
keeps in step (native/slab.cpp's amp, its worker off).
"""
import time


class _Go(object):
    """An Event whose set() does the job at once; its wait() never wakes a worker."""

    def __init__(self, fn):
        self.fn = fn

    def set(self):
        self.fn()

    def clear(self):
        pass

    def wait(self, timeout=None):
        time.sleep(min(timeout or 0.0, 0.05))
        return False

    def is_set(self):
        return False


def sync(lv):
    import tubeamp as TA
    import valvefine as VF
    lv.amp_stop = True              # the workers end at their next wake
    TA.GPU[0] = None

    def coarse():
        job = lv.amp_job
        if job is None:
            return
        pid, key, src, f, am, ph, drive, when, ref, imb = job[:10]
        jid = job[10] if len(job) > 10 else None
        fc, ac, pc = TA.combine(f, am, ph)
        kw = {} if imb is None else {"imbalance": float(imb)}
        out = TA.emit(fc.tolist(), ac.tolist(), pc.tolist(), float(lv.rate), drive, window_s=TA.LIVE_WINDOW_S,
                      oversample=TA.LIVE_OVERSAMPLE, keep=TA.LIVE_KEEP, reference=ref, **kw)
        lv.amp_calls += 1
        lv.amp_out = (pid, key, src, out, when)
        lv.amp_out_jid = jid

    def fine():
        with lv.amp_fine_lock:
            if not lv.amp_fine_pending:
                return
            pid = max(lv.amp_fine_pending, key=lambda q: lv.amp_fine_pending[q][1])
            job, jid = lv.amp_fine_pending.pop(pid)
        if lv.amp_jid.get(pid) != jid:
            return
        _, key, src, f, am, ph, drive, when, ref, imb = job[:10]
        fc, ac, pc = TA.combine(f, am, ph)
        kw = {} if imb is None else {"imbalance": float(imb)}
        out = TA.emit(fc.tolist(), ac.tolist(), pc.tolist(), float(lv.rate), drive, window_s=VF.FINE_WINDOW_S,
                      oversample=VF.FINE_OVERSAMPLE, keep=VF.FINE_KEEP,
                      reference=None if ref is None else float(ref), **kw)
        lv.amp_fine_results.append((jid, (pid, key, src, out, when)))

    lv.amp_go = _Go(coarse)
    lv.amp_fine_go = _Go(fine)
