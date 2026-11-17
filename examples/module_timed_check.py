#!/usr/bin/env python3
"""Does the apps' MIDI path (nv_host_midi_at, each message stamped with its
frame) go through the module mode? The live engine opened in this process
(the library, as the Mac and iOS apps open it), the module set through the
window's own call (nv_ui_call), a file sent in at its times, the blocks
rendered here.
    python3 examples/module_timed_check.py LIVE.nvx [FILE.mid] [MODE]
(default ~/Music/mt32/mt32_demo.mid in mt32: the MT-32's report must list
its custom timbres, the output must sound)"""
import ctypes, json, os, sys, time, numpy as np, mido
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import native
d = native.lib()
d.nv_host_open_args.restype = ctypes.c_void_p
d.nv_host_open_args.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int]
for f_ in ("nv_host_start", "nv_host_close", "nv_host_block", "nv_host_rate"): getattr(d, f_).argtypes = [ctypes.c_void_p]
d.nv_host_render.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
d.nv_host_midi_at.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_longlong]
d.nv_ui_watch_new.restype = ctypes.c_void_p
d.nv_ui_call.restype = ctypes.c_void_p
d.nv_ui_call.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
d.nv_ui_free.argtypes = [ctypes.c_void_p]
def call(h, w, q):
    p = d.nv_ui_call(h, w, json.dumps(q).encode()); s = ctypes.string_at(p).decode(); d.nv_ui_free(p); return json.loads(s)
nvx = sys.argv[1]
mid = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/Music/mt32/mt32_demo.mid')
mode = sys.argv[3] if len(sys.argv) > 3 else 'mt32'
av = [b"nvlive", nvx.encode(), b"--program=0", b"--reg-sync", b"--no-governor", b"--cpu"]
eb = ctypes.create_string_buffer(256)
h = d.nv_host_open_args(len(av), (ctypes.c_char_p * len(av))(*av), eb, 256)
assert h, eb.value
d.nv_host_start(h)
w = d.nv_ui_watch_new()
print(call(h, w, {"call": "module", "mode": mode})["module"]["mode"])
blk, sr = d.nv_host_block(h), d.nv_host_rate(h)
L = np.zeros(blk, np.float32); R = np.zeros(blk, np.float32)
out = []
# let the setup run (the module's parts built): render silence while busy
for i in range(4000):
    d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
    if i % 50 == 0 and not call(h, w, {"call": "module"})["module"]["busy"]: break
    time.sleep(0.005)
start = 0
evs = []
t = 0.0
for msg in mido.MidiFile(mid):
    t += msg.time
    if not msg.is_meta: evs.append((t, bytes(msg.bytes())))
nb = int((evs[-1][0] + 3) * sr) // blk
e = 0
for b in range(nb):
    while e < len(evs) and int(evs[e][0] * sr) // blk <= b:
        by = evs[e][1]; d.nv_host_midi_at(h, by, len(by), -1); e += 1
    d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
    out.append(np.stack([L.copy(), R.copy()], 1))
x = np.concatenate(out)
m = call(h, w, {"call": "module"})["module"]
print("eff", m["eff"], "| report:", m["report"])
prof = [float(np.sqrt((x[int(a*sr):int((a+4)*sr)]**2).mean())) for a in range(0, 40, 4)]
print("rms", " ".join("%.3f" % v for v in prof))
ok = max(prof) > 0.001 and (mode not in ('mt32', 'cm64u') or any('custom timbre' in r for r in m["report"]))
print("module timed: %s" % ("ok" if ok else "FAILED"))
sys.exit(0 if ok else 1)
