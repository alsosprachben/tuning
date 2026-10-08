#!/usr/bin/env python3
"""List or pull single members out of a zip on a web server, by HTTP range.

    python3 examples/remote_zip.py URL                 # list members
    python3 examples/remote_zip.py URL OUTDIR REGEX    # extract the matching ones

A sample library is gigabytes and a fit wants a few dozen of its files: the zip
central directory says where each member is, and a server that takes Range
requests hands over just those bytes.
"""
import io
import os
import re
import struct
import sys
import urllib.request
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor


class HTTPFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, method="HEAD")
        self.size = int(urllib.request.urlopen(req).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        req = urllib.request.Request(self.url, headers={"Range": "bytes=%d-%d" % (self.pos, end)})
        data = urllib.request.urlopen(req).read()
        self.pos += len(data)
        return data

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def fetch(url, info, out):
    """One member in ONE range request: its local header, then its data.
    zipfile's own reader seeks before every small read, and over HTTP each
    of those is a round trip."""
    if os.path.exists(out):
        return out
    a = info.header_offset
    b = a + 30 + len(info.orig_filename.encode()) + 1024 + info.compress_size
    req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (a, b)})
    raw = urllib.request.urlopen(req).read()
    n, e = struct.unpack("<HH", raw[26:30])
    data = raw[30 + n + e:30 + n + e + info.compress_size]
    if info.compress_type == zipfile.ZIP_DEFLATED:
        data = zlib.decompress(data, -15)
    elif info.compress_type != zipfile.ZIP_STORED:
        raise ValueError("compression %d" % info.compress_type)
    with open(out + ".part", "wb") as f:
        f.write(data)
    os.rename(out + ".part", out)
    return out


def main(argv):
    z = zipfile.ZipFile(io.BufferedReader(HTTPFile(argv[1]), buffer_size=1 << 20))
    if len(argv) < 4:
        for i in z.infolist():
            print("%10d  %s" % (i.file_size, i.filename))
        return 0
    rx = re.compile(argv[3])
    todo = [(i, os.path.join(argv[2], os.path.basename(i.filename)))
            for i in z.infolist() if rx.search(i.filename) and not i.is_dir()]
    with ThreadPoolExecutor(8) as ex:
        for out in ex.map(lambda t: fetch(argv[1], *t), todo):
            print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
