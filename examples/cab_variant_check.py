#!/usr/bin/env python3
"""Is the engine's cabinet variant (nv_cab_variant) the export's would-be class?

    python3 examples/cab_variant_check.py

Each amplified voice through each cabinet it offers: native.note_class of
patch_map.cabinet_class against nv_cab_variant of the voice's own, byte for
byte (the organ pointer aside: a separately made class's own).
"""
import ctypes, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import native as N, patch_map as P
L = N.lib()
t = N.cab_terms(); L.nv_cab_terms(len(t)//36, (ctypes.c_double*len(t))(*t))
sz = ctypes.sizeof(N.NoteClass)
bad = ok = 0
for p in range(128):
    for v in [0] + sorted(vv for (pp, vv) in dict.keys(P.VARIATIONS) if pp == p):
        base = P.variation_class(p, v) if v else P.PROGRAM_CLASS.get(p)
        if not isinstance(base, type) or not P.amplified(base): continue
        kb = N.note_class(base)
        if kb is None: continue
        for c in P.cab_choices(base):
            kd = N.note_class(P.cabinet_class(base, c))
            got = L.nv_cab_variant(ctypes.addressof(kb), c)
            gb = ctypes.string_at(got, sz); wb = ctypes.string_at(ctypes.addressof(kd), sz)
            off = N.NoteClass.organ.offset; gb = gb[:off] + wb[off:off+8] + gb[off+8:]
            if gb == wb: ok += 1
            else:
                bad += 1
                if bad <= 5:
                    g = N.NoteClass.from_buffer_copy(gb); w = N.NoteClass.from_buffer_copy(wb)
                    diffs = [i for i in range(sz) if gb[i] != wb[i]]
                    print("differ", p, v, P.CAB_CHOICES[c], len(diffs), "bytes, first at", diffs[:4], "gain", g.tmpl.gain, w.tmpl.gain)
print("identical", ok, "differ", bad)
