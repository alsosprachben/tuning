"""live's register with its worker in step, for the checks.

live.Live runs its register (the free strings: register.LiveChannel) in a
worker process that answers a few blocks later, as it can -- timing no
check can match. sync(lv, part) gives a Live a worker that answers each job
as it is sent (register.LiveWorker, in this process), so a reply is placed
at the first pump after its job: what native/slab.cpp's piano does. The
register runs on the CPU here (live enables it only with the GPU). Its
builds see the module state a fresh worker process has: tonelib's
honky_detune at 1.0, whatever this process's template builds left there.
"""


def sync(lv, part):
    import register as RG
    W = RG.LiveWorker()

    def answer(m):
        if m[0] == 'built':
            lv.reg_info[m[1]] = m[2]
        elif m[0] == 'error':
            raise RuntimeError(m[2])
        else:
            lv.reg_out.append(m)

    class SyncGo(object):
        """reg_go: each job the audio thread queues, answered as it is sent."""
        def set(self):
            import tonelib as T
            while lv.reg_jobs:
                job = lv.reg_jobs.popleft()
                was = T.honky_detune
                T.honky_detune = 1.0
                try:
                    W.handle(job, answer)
                finally:
                    T.honky_detune = was

        def clear(self):
            pass

        def wait(self, t=None):
            return False

    lv.reg_enabled = True
    lv._reg_start = lambda: setattr(lv, 'reg_proc', True)
    lv.reg_go = SyncGo()
    lv._reg_ask(part)
