#!/usr/bin/env python3
"""Stage the Indian Art Music Raga Recognition Dataset's features (Gulati,
Serra, Ganguli, Senturk, Serra 2016; Zenodo record 7278506, CC BY 4.0) --
without downloading its 3.6 GB zip: the zip read in place over HTTP range
requests (its central directory, then only the members asked for), into
~/Documents/refs/rrd.

    python3 -I examples/rrd_stage.py --list [PATTERN]      the members (matching PATTERN)
    python3 -I examples/rrd_stage.py PATTERN [...]         extract the matching members
"""
import io
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile

URL = ("https://zenodo.org/api/records/7278506/files/"
       "Indian%20Art%20Music%20Raga%20Recognition%20Dataset%20(features).zip/content")
OUT = os.path.expanduser("~/Documents/refs/rrd")


class HTTPRange(io.RawIOBase):
    """A seekable read-only file over HTTP range requests (blocks cached)."""
    BLOCK = 1 << 20

    def __init__(self, url):
        self.url, self.pos, self.cache = url, 0, {}
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req) as r:
            self.size = int(r.headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _block(self, b):
        if b not in self.cache:
            a = b * self.BLOCK
            z = min(self.size, a + self.BLOCK) - 1
            req = urllib.request.Request(self.url, headers={"Range": "bytes=%d-%d" % (a, z)})
            with urllib.request.urlopen(req) as r:
                self.cache[b] = r.read()
            if len(self.cache) > 64:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[b]

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.size:
            b, o = divmod(self.pos, self.BLOCK)
            chunk = self._block(b)[o:o + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def main(argv):
    z = zipfile.ZipFile(HTTPRange(URL))
    names = z.namelist()
    if argv[:1] == ["--list"]:
        pat = re.compile(argv[1]) if len(argv) > 1 else None
        hits = [i for i in z.infolist() if not pat or pat.search(i.filename)]
        for i in hits[:200]:
            print(i.file_size, i.filename)
        print("%d of %d members, %.1f MB" % (len(hits), len(names), sum(i.file_size for i in hits) / 1e6))
        return 0
    pats = [re.compile(a) for a in argv]
    want = [i for i in z.infolist() if not i.is_dir() and any(p.search(i.filename) for p in pats)]
    # ...each member's compressed bytes in ONE request, three at a time (eight met Zenodo's 429) (a
    # member a block at a time ran 1.5 h for 300 pitch tracks); one already
    # here at its full size is kept
    todo = [i for i in want if not (os.path.exists(os.path.join(OUT, i.filename))
                                   and os.path.getsize(os.path.join(OUT, i.filename)) == i.file_size)]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(3) as ex:
        for k, name in enumerate(ex.map(fetch, todo), 1):
            if k % 25 == 0 or k == len(todo):
                print("  %d / %d" % (k, len(todo)), flush=True)
    print("extracted %d members (%d already here) to %s" % (len(todo), len(want) - len(todo), OUT))
    return 0


def fetch(info):
    """One member: its local header, then its data, in one range request each."""
    import struct
    import zlib

    def get(a, n):
        import time
        for k in range(6):                      # (a dropped read: again, after a moment)
            try:
                req = urllib.request.Request(URL, headers={"Range": "bytes=%d-%d" % (a, a + n - 1)})
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = r.read()
                if len(d) == n:
                    return d
            except urllib.error.HTTPError as e:
                if e.code == 429 and k < 5:     # (Zenodo's rate limit: its own wait, else a minute)
                    time.sleep(float(e.headers.get("Retry-After") or 60) + 1.0)
                    continue
                if k == 5:
                    raise
            except Exception:
                if k == 5:
                    raise
            time.sleep(2.0 * (k + 1))
        raise IOError("short read at %d" % a)
    h = get(info.header_offset, 30)
    nl, xl = struct.unpack("<HH", h[26:30])
    data = get(info.header_offset + 30 + nl + xl, info.compress_size)
    if info.compress_type == zipfile.ZIP_DEFLATED:
        data = zlib.decompressobj(-15).decompress(data)
    elif info.compress_type != zipfile.ZIP_STORED:
        raise ValueError("compression %d" % info.compress_type)
    if len(data) != info.file_size or (zlib.crc32(data) & 0xffffffff) != info.CRC:
        raise ValueError("%s: size or CRC wrong" % info.filename)
    dst = os.path.join(OUT, info.filename)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst + ".part", "wb") as f:
        f.write(data)
    os.replace(dst + ".part", dst)
    return info.filename


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
