"""Put an extracted _prep_* pass back inline in _prepare (prep_extract's inverse)."""
import ast, re, sys, os
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'blockrender.py')
name = sys.argv[1]
L = open(SRC).read().split('\n')
a = next(i for i, l in enumerate(L) if l.startswith('def %s(' % name))
b = next(i for i in range(a + 1, len(L)) if L[i].startswith('def '))
fn = L[a:b]
d = next(i for i, l in enumerate(fn) if l.startswith('    """'))
e = d
while not (fn[e].rstrip().endswith('"""') and (e > d or fn[e].strip().count('"""') == 2)):
    e += 1
body = fn[e + 1:]
while body and body[-1] == '':
    body.pop()
r = [i for i, l in enumerate(body) if l.startswith('    return')]
if r:
    body = body[:r[-1]]
hit = next(i for i, l in enumerate(L) if '%s(' % name in l and not l.startswith('def'))
cs = hit
while cs > 0 and L[cs].startswith('        '):
    cs -= 1
ce = hit
while not L[ce].rstrip().endswith(')'):
    ce += 1
L2 = L[:a] + L[b:]
off = b - a
L2[cs - off:ce - off + 1] = body
src = '\n'.join(L2)
ast.parse(src)
open(SRC, 'w').write(src)
print('inlined %s: %d lines' % (name, len(body)))
