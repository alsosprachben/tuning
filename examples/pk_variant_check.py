#!/usr/bin/env python3
"""Is the engine's pickup variant (nv_pk_variant, nv_variant) the export's would-be class?

    python3 examples/pk_variant_check.py

Each voice with a pickup switch through each choice it offers -- and through
each with a cabinet it offers -- native.note_class of patch_map's variant
class against the engine's, byte for byte. Aside: the organ pointer (a
separately made class's own) and the template note's own coil places, pick
and touch (pk_q, pk_sp, strike_point, touch: nv_voice_init sets each again
for every note, by its fret -- a Clavinet's coils by its length, a touched
harmonic's touch by what these coils hear best).
"""
import ctypes, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import native as N, patch_map as P
L = N.lib()
L.nv_pk_variant.restype = L.nv_variant.restype = L.nv_cab_variant.restype = ctypes.c_void_p
L.nv_pk_variant.argtypes = L.nv_variant.argtypes = [ctypes.c_void_p, ctypes.c_int]
t = N.cab_terms(); L.nv_cab_terms(len(t)//36, (ctypes.c_double*len(t))(*t))
sz = ctypes.sizeof(N.NoteClass)
off_org = N.NoteClass.organ.offset
PER_NOTE = [(N.NoteClass.tmpl.offset + getattr(N.VoiceSnap, f).offset, getattr(N.VoiceSnap, f).size)
            for f in ('pk_q', 'pk_sp', 'strike_point', 'touch')] + [(off_org, 8)]


def mask(b, w):
    for o, n in PER_NOTE:
        b = b[:o] + w[o:o + n] + b[o + n:]
    return b


bad = ok = 0
seen = set()
for p in range(128):
    for v in [0] + sorted(vv for (pp, vv) in dict.keys(P.VARIATIONS) if pp == p):
        base = P.variation_class(p, v) if v else P.PROGRAM_CLASS.get(p)
        if not isinstance(base, type) or base in seen or not P.pk_choices(base):
            continue
        seen.add(base)
        kb = N.note_class(base)
        if kb is None:
            continue
        for c in P.pk_choices(base):
            for cab in (0,) + tuple(P.cab_choices(base))[:2]:
                cls = P.pickup_class(base, c)
                if cab:
                    cls = P.cabinet_class(cls, cab)
                kd = N.note_class(cls)
                got = L.nv_variant(ctypes.addressof(kb), c << 4 | cab)
                gb, wb = ctypes.string_at(got, sz), ctypes.string_at(ctypes.addressof(kd), sz)
                if mask(gb, wb) == wb:
                    ok += 1
                    continue
                bad += 1
                if bad <= 8:
                    g, w = N.NoteClass.from_buffer_copy(gb), N.NoteClass.from_buffer_copy(wb)
                    diffs = [i for i in range(sz) if mask(gb, wb)[i] != wb[i]]
                    names = sorted({f for f, _ in N.VoiceSnap._fields_
                                    if any(N.NoteClass.tmpl.offset + getattr(N.VoiceSnap, f).offset <= i
                                           < N.NoteClass.tmpl.offset + getattr(N.VoiceSnap, f).offset
                                           + getattr(N.VoiceSnap, f).size for i in diffs)})
                    print("differ", p, v, base.__name__, P.PICKUP_CHOICES[c], P.CAB_CHOICES[cab],
                          len(diffs), "bytes", names[:8] or diffs[:6])
print("pickup variants: identical", ok, "differ", bad)
