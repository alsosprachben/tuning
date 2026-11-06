#!/usr/bin/env python3
"""Do native.py's ctypes mirrors lay their fields where native/nv.h does?

    python3 examples/struct_check.py

For every mirrored struct (NoteClass, VoiceSnap, VoiceInit, NoteIn, NoteOut,
ToneIn, ...), a C file printing offsetof() for each of the mirror's fields is
compiled against native/nv.h and its offsets compared with ctypes'. The
export only checks a struct's SIZE, so a field moved -- the same fields, in
another order -- passes it silently and the engine reads the wrong values.
Exit 1 where any field sits elsewhere.
"""
import ctypes
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main():
    import native as N
    mirrors = [(n, c) for n, c in vars(N).items()
               if isinstance(c, type) and issubclass(c, ctypes.Structure) and getattr(c, '_fields_', None)]
    tmp = tempfile.mkdtemp(prefix='structcheck')
    alias = {'PyRandomState': 'PyRandom'}       # (a mirror named otherwise than its C struct)
    got, unchecked = {}, []
    for name, c in mirrors:
        cn = alias.get(name, name)
        src = os.path.join(tmp, name + '.c')
        lines = ['#include <stdio.h>', '#include <stddef.h>', '#include "nv.h"', 'int main(void) {']
        for f in c._fields_:
            lines.append('    printf("%s %%zu\\n", offsetof(%s, %s));' % (f[0], cn, f[0]))
        lines.append('    printf("__size__ %%zu\\n", sizeof(%s));' % cn)
        lines.append('    return 0;\n}')
        open(src, 'w').write('\n'.join(lines) + '\n')
        exe = os.path.join(tmp, name)
        r = subprocess.run(['gcc', '-I', os.path.join(HERE, 'native'), src, '-o', exe], capture_output=True, text=True)
        if r.returncode:
            # (not a struct nv.h declares by that name -- and nothing else: a
            # header that does not compile checks no struct at all)
            if any('error:' in ln and "'%s'" % cn not in ln.replace('‘', "'").replace('’', "'")
                   for ln in r.stderr.split('\n')):
                print(r.stderr.strip())
                print('structs: nv.h does not compile (%s)' % name)
                return 1
            unchecked.append(name)
            continue
        for ln in subprocess.run([exe], capture_output=True, text=True, check=True).stdout.split('\n'):
            if ln:
                f, o = ln.split()
                got[(name, f)] = int(o)
    mirrors = [(n, c) for n, c in mirrors if n not in unchecked]
    if unchecked:
        print('  not checked (no such struct in nv.h): %s' % ', '.join(unchecked))
    bad = 0
    for name, c in mirrors:
        for f in c._fields_:
            o = getattr(c, f[0]).offset
            if got[(name, f[0])] != o:
                bad += 1
                if bad <= 20:
                    print('  %s.%s: C %d, ctypes %d' % (name, f[0], got[(name, f[0])], o))
        if got[(name, '__size__')] != ctypes.sizeof(c):
            bad += 1
            print('  %s: size C %d, ctypes %d' % (name, got[(name, '__size__')], ctypes.sizeof(c)))
    print('structs: %d mirrors, %d fields, %d misplaced' % (len(mirrors), sum(len(c._fields_) for _, c in mirrors), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
