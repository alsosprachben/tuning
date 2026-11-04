"""live's patch builder in step, for the checks.

live.Live builds a program change's voice on a thread of its own
(_patch_worker): it points the part at the new patch at once (posted, done
after the next block's events) and warms it as it can -- timing no check can
match. sync(lv) stops that thread; build(lv) then does its work for every
request queued so far, in its order: the patch made (or found in live's
cache), the swap posted, the patch warmed whole. It returns the patches it
swapped in, [(part, patch)], so the other side can post the same swap
before the same block.
"""


def sync(lv):
    lv.patch_stop = True
    lv.patch_thread.join(5.0)


def build(lv):
    import live as L
    got = []
    while lv.patch_reqs:
        pid, want = lv.patch_reqs.popleft()
        if any(p == pid for p, _ in lv.patch_reqs):
            continue                # (coalesced: only the last of a run is built)
        part = next((q for q in lv.parts if q.pid == pid), None)
        if part is None:
            continue
        with L._PATCH_LOCK:
            patch = L._PATCHES.get(want)
            if patch is None:
                patch = L.Patch(*want)
                L._PATCHES[want] = patch
            L._PATCHES.move_to_end(want)
        lv.post(lambda n0, _p=part, _b=patch: lv._swap_patch(_p, _b, n0))
        L.pin_patches({q.patch.key for q in lv.parts} | {want})
        patch.warm()
        got.append((part, patch))
    return got
