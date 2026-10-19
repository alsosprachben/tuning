#!/usr/bin/env python3
"""Native Instruments' compressed wave (.ncw) to plain samples, so a Kontakt-
only pack can be MEASURED (never redistributed: decode into the pack's own
refs folder, read, fit).

    python3 -I examples/ncw.py FILE.ncw [OUT.wav]     decode one
    python3 -I examples/ncw.py --check DIR            decode every .ncw with a
                                                      .wav twin beside it, compare

THE FORMAT, as read off files whose plain WAV ships beside them (the
Feedbacker pack: its every NCW decodes to its WAV sample for sample):

  header, 120 bytes, little-endian:
    u32 magic (0xD69EA801)   u32 version
    u16 channels             u16 bits per sample
    u32 sample rate          u32 frames
    u32 block table offset   u32 data offset     u32 data size
  then the block table: u32 offsets (from the data offset), one per block
  of 512 frames.
  each block, per channel: 16 bytes --
    u32 magic (0x3E9A0C16)   i32 base value
    i16 bits                 u16 flags (1 = mid/side)   u32 pad
  and the channel's 512 values packed LSB-first:
    bits > 0: DELTAS of that width -- s[0] = base, s[i+1] = s[i] + d[i]
    bits < 0: ABSOLUTE values of |bits| width
    bits = 0: raw, at the file's bits per sample
"""
import os
import struct
import sys

import numpy as np

MAGIC = 0xD69EA801
BLOCK_MAGIC = 0x3E9A0C16
BLOCK = 512


def _unpack(buf, nbits, n, signed=True):
    """n LSB-first nbits-wide integers from buf."""
    bits = np.unpackbits(np.frombuffer(buf, np.uint8), bitorder="little")[:n * nbits]
    v = bits.reshape(n, nbits).astype(np.int64) @ (1 << np.arange(nbits, dtype=np.int64))
    if signed:
        v = np.where(v >= 1 << (nbits - 1), v - (1 << nbits), v)
    return v


def read(path):
    """(int32 array [frames, channels], sample rate, bits per sample)."""
    b = open(path, "rb").read()
    magic, _ver, ch, bps, sr, nfr, tab, dat, _size = struct.unpack("<IIHHIIIII", b[:32])
    if magic != MAGIC:
        raise ValueError("%s: not an NCW (magic %08x)" % (path, magic))
    nblk = -(-nfr // BLOCK)         # the table also holds the end's offset
    offs = struct.unpack("<%dI" % nblk, b[tab:tab + 4 * nblk])
    out = np.zeros((nblk * BLOCK, ch), np.int64)
    for k, o in enumerate(offs):
        p = dat + o
        ms = False
        for c in range(ch):
            bm, base, nb, flags, _ = struct.unpack("<IihHI", b[p:p + 16])
            if bm != BLOCK_MAGIC:
                raise ValueError("%s: block %d channel %d: bad magic %08x" % (path, k, c, bm))
            p += 16
            if nb > 0:
                n = nb * BLOCK // 8
                d = _unpack(b[p:p + n], nb, BLOCK)
                s = base + np.concatenate(([0], np.cumsum(d[:-1])))
            elif nb < 0:
                n = -nb * BLOCK // 8
                s = _unpack(b[p:p + n], -nb, BLOCK)
            else:
                n = bps * BLOCK // 8
                s = _unpack(b[p:p + n], bps, BLOCK)
            out[k * BLOCK:(k + 1) * BLOCK, c] = s
            ms = ms or bool(flags & 1)
            p += n
        if ms and ch == 2:
            m, sd = out[k * BLOCK:(k + 1) * BLOCK, 0].copy(), out[k * BLOCK:(k + 1) * BLOCK, 1].copy()
            out[k * BLOCK:(k + 1) * BLOCK, 0] = m + sd
            out[k * BLOCK:(k + 1) * BLOCK, 1] = m - sd
    return out[:nfr].astype(np.int32), sr, bps


def write_wav(path, x, sr, bps):
    """x int32 [frames, channels] at bps bits, as a PCM WAV."""
    ch = x.shape[1]
    w = bps // 8
    raw = x.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :w].tobytes()
    hdr = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(raw), b"WAVE", b"fmt ", 16, 1, ch,
                      sr, sr * ch * w, ch * w, bps, b"data", len(raw))
    open(path, "wb").write(hdr + raw)


def _wav_ints(path):
    from scipy.io import wavfile
    sr, y = wavfile.read(path)
    y = np.asarray(y)
    if y.ndim == 1:
        y = y[:, None]
    if y.dtype == np.int32:
        y = y >> 8          # scipy reads 24-bit into the top of an int32
    return y.astype(np.int64), sr


def check(root):
    bad = 0
    n = 0
    for d, _, fs in os.walk(root):
        for f in sorted(fs):
            if not f.endswith(".ncw"):
                continue
            twin = os.path.join(d, f[:-4] + ".wav")
            if not os.path.exists(twin):
                continue
            x, sr, bps = read(os.path.join(d, f))
            y, sr2 = _wav_ints(twin)
            if bps == 16:
                y = y.astype(np.int64)
            ok = x.shape == y.shape and sr == sr2 and np.array_equal(x, y)
            n += 1
            bad += not ok
            print("  %-4s %s  (%s, %d bit, %d Hz%s)" % ("ok" if ok else "DIFF", f, x.shape, bps, sr,
                  "" if ok or x.shape != y.shape else ", max diff %d" % np.abs(x - y).max()))
    print("  %d of %d decode to their WAV exactly" % (n - bad, n))
    return bad == 0


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        sys.exit(0 if check(sys.argv[2]) else 1)
    x, sr, bps = read(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1][:-4] + ".wav"
    write_wav(out, x, sr, bps)
    print("  %s: %d frames x %d, %d bit, %d Hz -> %s" % (sys.argv[1], x.shape[0], x.shape[1], bps, sr, out))
