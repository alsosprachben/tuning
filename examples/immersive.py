#!/usr/bin/env python3
"""An object render to a 7.1.4 bed and an MPEG-H file, for a real room.

    python3 examples/immersive.py OBJECTS_DIR DRY.wav OUTDIR LAYOUT.yaml
            (e.g. examples/brother_714.yaml)
            [--room church] [--br 1024000] [--clean]

--clean deletes each intermediate once the next stage has it (the object WAVs
after the ADM BWF, the direct bed after the mix, the decoded check after the
check): a 12-minute piece is 6 GB of objects and 6 GB of ADM, and without it
both sit on disk with everything after them.

OBJECTS_DIR is `blockrender --objects DIR --by-source --no-reflect`; DRY.wav is
the same score rendered the ordinary way (stereo, with its .room.json), which
sets the levels. LAYOUT.yaml names the room's twelve speakers in EAR's format
(ear.core.layout.load_real_layout), channel numbers in CICP 19 order.

    objects --admbwf--> ADM BWF --ear-render, the room's real angles--> direct bed
    stereo dry, mid --roomtail.build_ir, 11 decorrelated channels--> diffuse hall
    direct + hall --48 kHz--> 7.1.4 PCM --libmpeghe, CICP 19--> MPEG-H (MHM1 in MP4)
    MP4 --libmpegh--> PCM, compared channel by channel against what went in

WHY A BED AND NOT OBJECTS. The receiver plays a CICP 19 bed's twelve channels
straight to its twelve speakers. Room correction (Dirac, Audyssey) fixes time,
level and response, not angle, so the panning has to be done for the angles the
speakers actually stand at -- which EAR does from LAYOUT.yaml. Objects would
hand the panning to the receiver, which knows the speakers' roles but not their
angles, and would pan for nominal ones.

WHY THE OBJECTS ARE DRY OF REFLECTIONS. An object is mono at one position, so a
source's first-order images rendered into it would arrive from the source and
not from the walls. They are left out and the hall comes from every speaker.

THE ROOM IS DIFFUSE BY DEFINITION (see roomtail.py), so it is not panned: each
of the eleven full-range speakers gets its own noise realisation of the same
IR, which is what decorrelates them. Fed from the stereo dry's mid, scaled so
the eleven carry the same total reverberant energy the stereo pair did.

LEVELS. The direct bed is scaled so its energy over all speakers equals the
stereo dry's over two, so the direct-to-room balance is the stereo render's.
The LFE is silent: the models are full range, and a summed low-pass would
double the bass the receiver's bass management already routes.

The encoder and decoder are Ittiam's (github.com/ittiam-systems/libmpeghe and
libmpegh), built in ~/src; EAR is the EBU's renderer, `pip install ear` in
~/src/earvenv (pinned setuptools<81: it still imports pkg_resources).
"""
import json
import math
import os
import struct
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SRC = os.path.expanduser('~/src')
EAR = os.path.join(SRC, 'earvenv', 'bin', 'ear-render')
ENC = os.path.join(SRC, 'libmpeghe', 'build', 'bin', 'MPEGHEncoder')
DEC = os.path.join(SRC, 'libmpegh', 'cbuild', 'ia_mpeghd_testbench')

LFE = 3                     # CICP 19: L R C LFE Lsr Rsr Lss Rss Lv Rv Lvr Rvr
EAR_HEADROOM_DB = 12.0      # EAR writes integer PCM, which clips
OUT_SR = 48000
BLOCK = 1 << 18


def wav_info(path):
    """(format tag, channels, rate, bits, data offset, frames) of a WAV/BW64."""
    with open(path, 'rb') as fh:
        fh.seek(12)
        fmt = None
        while True:
            head = fh.read(8)
            if len(head) < 8:
                raise SystemExit("%s: no data chunk" % path)
            tag, size = head[:4], struct.unpack('<I', head[4:])[0]
            if tag == b'fmt ':
                b = fh.read(size)
                fmt = struct.unpack('<HHIIHH', b[:16])
                if size & 1:
                    fh.seek(1, 1)
            elif tag == b'data':
                ftag, ch, sr, _, align, bits = fmt
                return ftag, ch, sr, bits, fh.tell(), size // align
            else:
                fh.seek(size + (size & 1), 1)


def read_block(path, info, start, n):
    """Frames [start, start+n) as float64, shape (n, channels)."""
    ftag, ch, sr, bits, off, frames = info
    n = max(0, min(n, frames - start))
    w = bits // 8
    with open(path, 'rb') as fh:
        fh.seek(off + start * ch * w)
        b = fh.read(n * ch * w)
    if ftag == 3 and bits == 32:
        return np.frombuffer(b, '<f4').reshape(n, ch).astype(np.float64)
    if bits == 24:
        u = np.frombuffer(b, np.uint8).reshape(-1, 3).astype(np.int32)
        v = (u[:, 0] | (u[:, 1] << 8) | (u[:, 2] << 16))
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        return (v / 8388607.0).reshape(n, ch)
    if bits == 32:
        return (np.frombuffer(b, '<i4') / 2147483647.0).reshape(n, ch)
    if bits == 16:
        return (np.frombuffer(b, '<i2') / 32767.0).reshape(n, ch)
    raise SystemExit("%s: %d-bit format %d" % (path, bits, ftag))


def write_wav(path, x, sr, bits=24):
    """(frames, channels) floats to a plain PCM WAV, written a block at a time."""
    n, ch = x.shape
    w = bits // 8
    size = n * ch * w
    with open(path, 'wb') as fh:
        fh.write(b'RIFF' + struct.pack('<I', 36 + size + (size & 1)) + b'WAVE')
        fh.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, ch, sr, sr * ch * w, ch * w, bits))
        fh.write(b'data' + struct.pack('<I', size))
        for a in range(0, n, BLOCK):
            v = np.clip(x[a:a + BLOCK], -1.0, 1.0)
            if bits == 24:
                q = (v * 8388607.0).astype('<i4')
                fh.write(q.view(np.uint8).reshape(-1, 4)[:, :3].tobytes())
            else:
                fh.write((v * 32767.0).astype('<i2').tobytes())
        if size & 1:
            fh.write(b'\x00')


def energy(path, chans=None):
    """Sum of squares per channel, streamed."""
    info = wav_info(path)
    e = np.zeros(info[1])
    for a in range(0, info[5], BLOCK):
        e += np.sum(read_block(path, info, a, BLOCK) ** 2, 0)
    return e


def run(cmd, **kw):
    print("  $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def hall(dry, chans, room, length_of):
    """The diffuse tail on decorrelated channels `chans`, from the stereo dry's
    mid, at the reverberant energy roomtail would give the stereo pair. Returns
    the mix array, (length_of(tail frames), 12) float32, holding the tail."""
    os.environ['TUNING_ROOM'] = room
    import roomtail as RT
    import tonelib as T
    info = wav_info(dry)
    x = read_block(dry, info, 0, info[5])
    sr = info[2]
    props = T.StoppedPipeProperties(261.6, 0, 1, 1)
    band_q = None
    side = os.path.splitext(dry)[0] + '.room.json'
    if os.path.exists(side):
        d = json.load(open(side))
        band_q = {b['hz']: b['q'] for b in d['bands'] if b.get('energy', 0) > 0}
    n_out = len(chans)
    ir, bands, onset = RT.build_ir(props, sr, q=2.0, seed=0, channels=n_out, band_q=band_q)
    # stereo: channel c of the tail is x_c * ir_c, so its energy is the pair's.
    # Here every channel is fed the mid, so n_out of them would carry n_out/2
    # times that, less the decorrelation the mid already lost.
    e_pair = float(np.sum(x ** 2))
    mid = x.mean(1)
    e_mid = float(np.sum(mid ** 2))
    g = math.sqrt(e_pair / (n_out * max(e_mid, 1e-30)))
    del x
    nt = len(mid) + len(ir) - 1
    out = np.zeros((length_of(nt), 12), np.float32)
    for i, c in enumerate(chans):
        y = RT.overlap_add(mid * g, ir[:, i])[:nt]
        out[:len(y), c] = y
        del y
    print("   hall: %d channels from the mid, %.2f s IR, x%.3f to the pair's energy"
          % (n_out, len(ir) / sr, g))
    for f, t60, ratio in bands:
        if f <= sr / 2:
            print("     %6.0f Hz  T60 %.2f s  room %+5.1f dB on the direct"
                  % (f, t60, 10 * math.log10(ratio)))
    return out, sr


def main(argv):
    if len(argv) < 5:
        print(__doc__.strip().splitlines()[2]); return 2
    objdir, dry, outdir, layout = argv[1:5]
    room = argv[argv.index('--room') + 1] if '--room' in argv else 'church'
    br = argv[argv.index('--br') + 1] if '--br' in argv else '1024000'
    clean = '--clean' in argv
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(dry))[0].replace('.dry', '')

    adm = os.path.join(outdir, stem + '.adm.wav')
    import glob
    _man = glob.glob(os.path.join(objdir, '*.objects.json'))
    if not os.path.exists(adm) or not _man or os.path.getmtime(adm) < os.path.getmtime(_man[0]):
        run([sys.executable, os.path.join(ROOT, 'admbwf.py'), objdir, adm, '--bits', '24'])
    if clean:
        for f in os.listdir(objdir):
            if f.endswith('.wav'):
                os.remove(os.path.join(objdir, f))
    direct = os.path.join(outdir, stem + '.direct.wav')
    run([EAR, '-s', '4+7+0', '-l', layout, '--output-gain-db', '-%g' % EAR_HEADROOM_DB,
         '--fail-on-overload', adm, direct])

    # The direct bed to the stereo dry's energy
    e_dir = energy(direct)
    e_dry = energy(dry)
    gd = math.sqrt(e_dry.sum() / e_dir.sum())
    print("   direct bed x%.3f (%+.1f dB) to the stereo dry's energy" % (gd, 20 * math.log10(gd)))
    print("   direct energy by speaker: " + " ".join("%+.1f" % (10 * math.log10(e / e_dir.sum() + 1e-30))
                                                     for e in e_dir))

    di = wav_info(direct)
    full = [c for c in range(12) if c != LFE]
    mix, sr = hall(dry, full, room, lambda nt: max(nt, di[5]))
    if di[2] != sr:
        raise SystemExit("direct bed at %d Hz, dry at %d" % (di[2], sr))
    for a in range(0, di[5], BLOCK):
        b = read_block(direct, di, a, BLOCK)
        mix[a:a + len(b)] += (b * gd).astype(np.float32)
    if clean:
        os.remove(direct)
    mix[:, LFE] = 0.0
    peak = max(float(np.abs(mix[a:a + BLOCK]).max()) for a in range(0, len(mix), BLOCK))
    g = 10 ** (-1.0 / 20) / peak
    mix *= g
    print("   peak %.3f -> -1 dBFS (x%.3f)" % (peak, g))

    bed44 = os.path.join(outdir, stem + '.714_%d.wav' % sr)
    write_wav(bed44, mix, sr)
    del mix
    bed = os.path.join(outdir, stem + '.714.wav')
    run(['sox', bed44, '-b', '24', bed, 'rate', '-v', str(OUT_SR)])
    os.remove(bed44)

    mp4 = os.path.join(outdir, stem + '.mpegh.mp4')
    run([ENC, '-ifile:' + bed, '-ofile:' + mp4, '-cicp:19', '-op_fmt:3', '-br:' + br],
        stdout=subprocess.DEVNULL)
    back = os.path.join(outdir, stem + '.decoded.wav')
    run([DEC, '-ifile:' + mp4, '-ofile:' + back, '-pcmsz:24'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Each speaker back where it went in, and how close
    bi, ki = wav_info(bed), wav_info(back)
    names = 'L R C LFE Lsr Rsr Lss Rss Lv Rv Lvr Rvr'.split()
    a0 = 10 * OUT_SR
    m = min(60 * OUT_SR, bi[5] - a0)
    src = read_block(bed, bi, a0, m)
    # the codec delays: find it once, on the channel with most energy
    c0 = int(np.argmax(np.sum(src ** 2, 0)))
    lag = 0
    probe = read_block(back, ki, a0, m + 8192)
    xc = np.fft.irfft(np.fft.rfft(probe[:, c0], 2 * len(probe)) *
                      np.conj(np.fft.rfft(src[:, c0], 2 * len(probe))))
    lag = int(np.argmax(xc[:8192]))
    dec = probe[lag:lag + m]
    print("   decoded: %d channels at %d Hz, codec delay %d samples" % (ki[1], ki[2], lag))
    ok = ki[1] == 12
    for c in range(12):
        es = float(np.sum(src[:, c] ** 2))
        if es == 0:
            ed = float(np.sum(dec[:, c] ** 2))
            print("     %-4s silent in, %s out" % (names[c], "silent" if ed < 1e-9 else "%.1e" % ed))
            continue
        r = float(np.corrcoef(src[:, c], dec[:, c])[0, 1])
        snr = 10 * math.log10(es / max(float(np.sum((src[:, c] - dec[:, c]) ** 2)), 1e-30))
        # normalised: the speakers share the hall and much of the direct sound,
        # so a raw dot product picks the LOUDEST correlated channel, not its own
        best = int(np.argmax([abs(np.corrcoef(src[:, c], dec[:, k])[0, 1])
                              if np.any(dec[:, k]) else 0.0 for k in range(ki[1])]))
        ok &= best == c
        print("     %-4s r %.4f  SNR %5.1f dB  best match %s" % (names[c], r, snr, names[best]))
    print("   channel order %s" % ("intact" if ok else "SCRAMBLED"))
    if clean:
        os.remove(back)
    print("  -> %s\n  -> %s\n  -> %s" % (mp4, bed, adm))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
