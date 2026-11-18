#!/usr/bin/env python3
"""The engine's memory while it plays a file: what iOS would count against an
app, and what it would not.

    python3 examples/mem_measure.py EXPORT.nvx IN.mid [SECONDS] [-- nvlive args...]

Runs nvlive --test (no devices) on IN.mid with its program changes followed
(--programs), sampling /proc/PID/smaps_rollup every 0.2 s, and prints the
peaks and the end's:

  footprint   Private_Dirty + Swap: memory only this process holds and the
              system cannot drop -- iOS's phys_footprint (what jetsam kills
              by) counts the same; the budget is set against this
  rss         every page resident, clean mapped file pages too (the export
              mapped where it lies: the system drops those at will)
  anon        anonymous pages (heap, stacks)
  file_dirty  the export's pages written (copy on write): private, counted

and the export's own mapping alone (its line in /proc/PID/smaps): resident,
and dirty -- the classes and organs fixed up where they lie.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rollup(pid):
    out = {}
    try:
        for ln in open('/proc/%d/smaps_rollup' % pid):
            p = ln.split()
            if len(p) >= 2 and p[0].endswith(':') and p[1].isdigit():
                out[p[0][:-1]] = int(p[1])
    except OSError:
        return None
    return out


def export_map(pid, path):
    """The export's mapping: (resident kB, private dirty kB)."""
    rss = dirty = 0
    inside = False
    try:
        for ln in open('/proc/%d/smaps' % pid):
            p = ln.split()
            if p and '-' in p[0] and len(p) >= 5 and not p[0].endswith(':'):
                inside = len(p) >= 6 and os.path.realpath(p[-1]) == path
                continue
            if inside and p[0] == 'Rss:':
                rss += int(p[1])
            elif inside and p[0] == 'Private_Dirty:':
                dirty += int(p[1])
    except OSError:
        pass
    return rss, dirty


def main():
    a = sys.argv[1:]
    extra = []
    if '--' in a:
        i = a.index('--')
        a, extra = a[:i], a[i + 1:]
    if len(a) < 2:
        print(__doc__)
        return 2
    nvx, mid = os.path.realpath(a[0]), a[1]
    secs = a[2] if len(a) > 2 else '60'
    import tempfile
    fd, out = tempfile.mkstemp(suffix='.wav')
    os.close(fd)
    args = [os.path.join(HERE, 'nvlive'), nvx, '--test', mid, out, '--programs', '--seconds=' + secs] + extra
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                         env=dict(os.environ, NV_PATCH_SIZES='1'))
    peak = {}
    last = None
    t0 = time.time()
    while p.poll() is None:
        r = rollup(p.pid)
        if r:
            er, ed = export_map(p.pid, nvx)
            r = dict(r, export_rss=er, export_dirty=ed)
            r['footprint'] = r.get('Private_Dirty', 0) + r.get('Swap', 0)
            r['anon'] = r.get('Anonymous', 0)
            r['file_dirty'] = ed
            for k, v in r.items():
                peak[k] = max(peak.get(k, 0), v)
            last = r
        time.sleep(0.2)
    err = p.stderr.read()
    os.remove(out)
    if p.returncode:
        print(err[-2000:])
        print('nvlive exited %d' % p.returncode)
        return 1
    mb = lambda k: '%7.1f' % ((peak.get(k, 0)) / 1024.0)     # noqa: E731
    mbl = lambda k: '%7.1f' % (((last or {}).get(k, 0)) / 1024.0)     # noqa: E731
    print('%s (%s s, %.0f s wall)' % (os.path.basename(mid), secs, time.time() - t0))
    print('  MB            peak     end')
    for k in ('footprint', 'Rss', 'anon', 'file_dirty', 'export_rss'):
        print('  %-11s %s %s' % (k if k != 'Rss' else 'rss', mb(k), mbl(k)))
    for ln in err.splitlines():
        if 'patch' in ln or 'blocks ->' in ln:
            print('  ' + ln)
    return 0


if __name__ == '__main__':
    sys.exit(main())
