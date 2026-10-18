#!/usr/bin/env python3
"""An object render to a 7.1.4 bed and an MPEG-H file, for a real room.

    python3 examples/immersive.py OBJECTS_DIR DRY.wav OUTDIR LAYOUT.yaml
            (e.g. examples/brother_714.yaml)
            [--room church] [--br 1024000] [--clean] [--no-early]
    python3 examples/immersive.py encode BED.714.wav OUT.mp4 [--br 576000]

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
not from the walls. They are rendered here instead (early_bed): each image of
each object, from the same tonelib.reflection_terms the stereo render uses --
its delay, what the wall kept and the air took per octave -- panned by EAR's
own point-source panner to where the IMAGE stands, behind and above included.
A receiver that neutralises its own room (Seth's does) leaves nothing to supply
these, and roomtail's IR starts its specular train at the second order on the
understanding that the first is drawn geometrically. --no-early leaves them out.

All six first-order images, without the renderer's 50 ms fusion cut. That cut
is a claim about a HEAD -- past it the binaural mix lets the diffuse tail carry
an image decorrelated -- and over twelve speakers the head is the listener's
own. In the hall at wet +2 it is what keeps the far side wall and the back wall
(87 ms, from behind), the two reflections only a surround array can place.
Omnidirectional: the object does not know its program (a channel carries
several parts), so the images are not coloured by the instrument's directivity.

THE ROOM IS DIFFUSE BY DEFINITION (see roomtail.py), so it is not panned: each
of the eleven full-range speakers gets its own noise realisation of the same
IR, which is what decorrelates them. Fed from the stereo dry's mid, scaled so
the eleven carry the same total reverberant energy the stereo pair did.

LEVELS. The direct bed with its early reflections is scaled so its energy over
all speakers equals the stereo dry's over two (which has its reflections too),
so the direct-to-room balance is the stereo render's.
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
EAR_PY = os.path.join(SRC, 'earvenv', 'bin', 'python')
ENC = os.path.join(SRC, 'libmpeghe', 'build', 'bin', 'MPEGHEncoder')
DEC = os.path.join(SRC, 'libmpegh', 'cbuild', 'ia_mpeghd_testbench')

LFE = 3                     # CICP 19: L R C LFE Lsr Rsr Lss Rss Lv Rv Lvr Rvr
EAR_HEADROOM_DB = 12.0      # EAR writes integer PCM, which clips
OUT_SR = 48000
BLOCK = 1 << 18
OCTAVES = (63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0)
IMAGE_TAPS = 1024           # each image's wall-and-air filter, linear phase

# EAR's panner for directions, in the earvenv: the layout as ear-render builds
# it (4+7+0 fitted to the real angles, then its upmix to the file's channels),
# so an image is panned exactly as an object at its place would be.
_PAN = r'''
import json, sys, warnings
warnings.simplefilter("ignore")
import numpy as np
from ear.core import bs2051, layout, point_source
from ear.core.geom import cart
spk, upmix = bs2051.get_layout("4+7+0").with_real_layout(
    layout.load_real_layout(open(sys.argv[1])))
full = [i for i, c in enumerate(spk.channels) if not c.is_lfe]
psp = point_source.configure(spk.without_lfe)
out = []
for az, el in json.load(sys.stdin):
    g = np.zeros(len(spk.channels))
    g[full] = psp.handle(cart(az, el, 1.0))
    out.append((np.asarray(upmix) @ g).tolist())
json.dump(out, sys.stdout)
'''


def pan_gains(layout, dirs):
    """(len(dirs), 12) speaker gains for [(az, el)] in ADM degrees."""
    r = subprocess.run([EAR_PY, '-c', _PAN, layout], input=json.dumps(dirs),
                       capture_output=True, text=True, check=True)
    return np.array(json.loads(r.stdout))


def image_fir(gains, sr):
    """A linear-phase FIR through per-octave gains (OCTAVES), interpolated in
    log frequency and held flat past the ends; its delay is IMAGE_TAPS/2."""
    n = IMAGE_TAPS
    f = np.fft.rfftfreq(n, 1.0 / sr)
    bands = [(b, g) for b, g in zip(OCTAVES, gains) if b <= sr / 2]
    lf = np.log(np.maximum(f, 1.0))
    H = np.interp(lf, np.log([b for b, _ in bands]), [g for _, g in bands])
    h = np.roll(np.fft.irfft(H, n), n // 2) * np.hanning(n)
    return h


def early_bed(objdir, layout, frames, sr, room, out, scale=1.0):
    """Every object's first-order images, panned to where each image stands,
    added into `out` (frames, 12) at `scale` (the direct bed's units: EAR's
    output gain). Returns how many images were placed."""
    os.environ['TUNING_ROOM'] = room
    import glob
    import tonelib as T
    man = json.load(open(glob.glob(os.path.join(objdir, '*.objects.json'))[0]))
    if man.get('sample_rate', sr) != sr:
        raise SystemExit("objects at %s Hz, bed at %d" % (man.get('sample_rate'), sr))
    props = T.StoppedPipeProperties(261.6, 0, 1, 1)
    props.directivity_radius = 0.0
    props.reflection_fusion_s = 0.0          # see the docstring: the head is real
    sy = man.get('radiation_distance_m', props.radiation_distance)

    per_obj, dirs = [], []
    for ob in man['objects']:
        sx, sz = ob.get('x_m', 0.0), ob.get('z_m', 0.0)
        imgs = {}
        for bi, fc in enumerate(OCTAVES):
            for g, d, im in props.reflection_terms(fc, sx, sy, sz):
                key = tuple(round(v, 3) for v in im)
                e = imgs.setdefault(key, [d, im, [0.0] * len(OCTAVES)])
                e[2][bi] = g
        lst = []
        for d, (ix, iy, iz), gains in imgs.values():
            r = math.sqrt(ix * ix + iy * iy + iz * iz) or 1e-9
            dirs.append((math.degrees(math.atan2(-ix, iy)),
                         math.degrees(math.asin(max(-1.0, min(1.0, iz / r))))))
            lst.append((d, gains, len(dirs) - 1))
        per_obj.append((ob, lst))
    P = pan_gains(layout, dirs)

    K = IMAGE_TAPS // 2
    placed = 0
    for ob, lst in per_obj:
        if not lst:
            continue
        L = max(int(round(d * sr)) for d, _, _ in lst) + IMAGE_TAPS
        h = np.zeros((L, 12))
        for d, gains, k in lst:
            a = int(round(d * sr))
            h[a:a + IMAGE_TAPS] += image_fir(gains, sr)[:, None] * P[k][None, :]
        placed += len(lst)
        f = os.path.join(objdir, ob['file'])
        info = wav_info(f)
        nfft = 1 << int(math.ceil(math.log2(BLOCK + L)))
        Hf = np.fft.rfft(h * scale, nfft, axis=0)
        for a in range(0, info[5], BLOCK):
            x = read_block(f, info, a, BLOCK)[:, 0]
            y = np.fft.irfft(np.fft.rfft(x, nfft)[:, None] * Hf, nfft, axis=0)[:len(x) + L - 1]
            # the filter's K samples of latency come off here, so an image's
            # delay is measured from the direct sound and not from the FIR
            lo = a - K
            s0 = max(0, -lo)
            s1 = min(len(y), frames - lo)
            if s1 > s0:
                out[lo + s0:lo + s1] += y[s0:s1].astype(np.float32)
    return placed, dirs


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


def hall(dry, chans, room, alloc):
    """The diffuse tail on decorrelated channels `chans`, from the stereo dry's
    mid, at the reverberant energy roomtail would give the stereo pair. Returns
    alloc(tail frames) -- a (frames, 12) float32 array -- holding the tail."""
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
    out = alloc(nt)
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


def bed(objdir, dry, outdir, layout, room, clean=False, early=True,
        shape_direct=None, shape_hall=None):
    """One render's 7.1.4 bed before normalising: the hall, plus the direct bed
    and its early reflections at the stereo dry's energy. A float32 memmap
    (frames, 12) in OUTDIR -- a nine-minute bed is 1.1 GB, on a 7 GB machine.

    shape_direct(a, block) and shape_hall(a, block) may return a reshaped
    block starting at frame a (called in order, so a filter may keep state):
    how a part that moves away during the piece is moved (neptune_714.py)."""
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(dry))[0].replace('.dry', '')
    adm = os.path.join(outdir, stem + '.adm.wav')
    import glob
    _man = glob.glob(os.path.join(objdir, '*.objects.json'))
    if not os.path.exists(adm) or not _man or os.path.getmtime(adm) < os.path.getmtime(_man[0]):
        run([sys.executable, os.path.join(ROOT, 'admbwf.py'), objdir, adm, '--bits', '24'])
    direct = os.path.join(outdir, stem + '.direct.wav')
    run([EAR, '-s', '4+7+0', '-l', layout, '--output-gain-db', '-%g' % EAR_HEADROOM_DB,
         '--fail-on-overload', adm, direct])
    if clean:
        os.remove(adm)
    di = wav_info(direct)
    sr, frames = di[2], di[5]

    # The first-order images, in the direct bed's units
    ef = os.path.join(outdir, stem + '.early.npy')
    ear = np.lib.format.open_memmap(ef, 'w+', np.float32, (frames, 12))
    if early:
        n, dirs = early_bed(objdir, layout, frames, sr, room, ear,
                            10 ** (-EAR_HEADROOM_DB / 20))
        behind = sum(1 for az, el in dirs if abs(az) > 90)
        above = sum(1 for az, el in dirs if el > 10)
        print("   early: %d images (%d behind, %d above), panned to where each stands"
              % (n, behind, above))
    if clean:
        for f in os.listdir(objdir):
            if f.endswith('.wav'):
                os.remove(os.path.join(objdir, f))

    # The direct bed and its reflections to the stereo dry's energy
    e_dir = np.zeros(12); e_ear = np.zeros(12); e_sum = np.zeros(12)
    for a in range(0, frames, BLOCK):
        b = read_block(direct, di, a, BLOCK)
        r = ear[a:a + len(b)]
        e_dir += np.sum(b ** 2, 0); e_ear += np.sum(r.astype(np.float64) ** 2, 0)
        e_sum += np.sum((b + r) ** 2, 0)
    e_dry = energy(dry)
    gd = math.sqrt(e_dry.sum() / e_sum.sum())
    print("   direct + early x%.3f (%+.1f dB) to the stereo dry's energy; early %+.1f dB on the direct"
          % (gd, 20 * math.log10(gd), 10 * math.log10(max(e_ear.sum(), 1e-30) / e_dir.sum())))
    print("   energy by speaker: " + " ".join("%+.1f" % (10 * math.log10(e / e_sum.sum() + 1e-30))
                                             for e in e_sum))

    full = [c for c in range(12) if c != LFE]
    mf = os.path.join(outdir, stem + '.bed.npy')
    mix, hsr = hall(dry, full, room,
                    lambda nt: np.lib.format.open_memmap(mf, 'w+', np.float32,
                                                         (max(nt, frames), 12)))
    if hsr != sr:
        raise SystemExit("direct bed at %d Hz, dry at %d" % (sr, hsr))
    if shape_hall:
        for a in range(0, len(mix), BLOCK):
            mix[a:a + BLOCK] = shape_hall(a, mix[a:a + BLOCK].astype(np.float64))
    for a in range(0, frames, BLOCK):
        b = (read_block(direct, di, a, BLOCK) + ear[a:a + BLOCK]) * gd
        if shape_direct:
            b = shape_direct(a, b)
        mix[a:a + len(b)] += b.astype(np.float32)
    mix[:, LFE] = 0.0
    del ear
    os.remove(ef)
    if clean:
        os.remove(direct)
    return mix, sr


def finish(mix, sr, outdir, stem, br, clean=False):
    """A bed to -1 dBFS, 48 kHz 24-bit PCM and MPEG-H, decoded back and checked."""
    peak = max(float(np.abs(mix[a:a + BLOCK]).max()) for a in range(0, len(mix), BLOCK))
    g = 10 ** (-1.0 / 20) / peak
    print("   peak %.3f -> -1 dBFS (x%.3f)" % (peak, g))
    bed44 = os.path.join(outdir, stem + '.714_%d.wav' % sr)
    write_wav(bed44, _Scaled(mix, g), sr)
    out = os.path.join(outdir, stem + '.714.wav')
    run(['sox', bed44, '-b', '24', out, 'rate', '-v', str(OUT_SR)])
    os.remove(bed44)
    mp4 = os.path.join(outdir, stem + '.mpegh.mp4')
    ok = encode_and_check(out, mp4, br, os.path.join(outdir, stem + '.decoded.wav'), clean)
    print("  -> %s\n  -> %s" % (mp4, out))
    return ok


class _Scaled:
    """An array times a gain, a slice at a time (write_wav slices)."""

    def __init__(self, x, g):
        self.x, self.g, self.shape = x, g, x.shape

    def __getitem__(self, k):
        return self.x[k] * self.g


def main(argv):
    if len(argv) < 5:
        print(__doc__.strip().splitlines()[2]); return 2
    objdir, dry, outdir, layout = argv[1:5]
    room = argv[argv.index('--room') + 1] if '--room' in argv else 'church'
    br = argv[argv.index('--br') + 1] if '--br' in argv else '1024000'
    clean = '--clean' in argv
    stem = os.path.splitext(os.path.basename(dry))[0].replace('.dry', '')
    mix, sr = bed(objdir, dry, outdir, layout, room, clean, early='--no-early' not in argv)
    ok = finish(mix, sr, outdir, stem, br, clean)
    del mix
    os.remove(os.path.join(outdir, stem + '.bed.npy'))
    return 0 if ok else 1


def encode_and_check(bed, mp4, br, back, clean=False):
    """BED (12 channels, CICP 19 order, 48 kHz) to MPEG-H, decoded back and
    compared speaker by speaker. The encoder's own defaults stand -- since
    the CLI options patch (Seth's player), Baseline profile, no m4ds box,
    the configuration repeated every 48 frames."""
    run([ENC, '-ifile:' + bed, '-ofile:' + mp4, '-cicp:19', '-op_fmt:3', '-br:' + br],
        stdout=subprocess.DEVNULL)
    run([DEC, '-ifile:' + mp4, '-ofile:' + back, '-pcmsz:24'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Each speaker back where it went in, and how close
    bi, ki = wav_info(bed), wav_info(back)
    names = 'L R C LFE Lsr Rsr Lss Rss Lv Rv Lvr Rvr'.split()
    a0 = min(10 * OUT_SR, bi[5] // 4)          # a short test piece has no minute 1
    m = min(60 * OUT_SR, bi[5] - a0)
    src = read_block(bed, bi, a0, m)
    # the codec delays: find it once, on the channel with most energy
    c0 = int(np.argmax(np.sum(src ** 2, 0)))
    lag = 0
    probe = read_block(back, ki, a0, m + 8192)
    xc = np.fft.irfft(np.fft.rfft(probe[:, c0], 2 * len(probe)) *
                      np.conj(np.fft.rfft(src[:, c0], 2 * len(probe))))
    lag = int(np.argmax(xc[:8192]))
    m = min(m, len(probe) - lag)
    src, dec = src[:m], probe[lag:lag + m]
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
    return ok


if __name__ == '__main__':
    # immersive.py encode BED.714.wav OUT.mp4 [--br N]: a bed already made,
    # encoded again (a new encoder) and checked
    if len(sys.argv) > 1 and sys.argv[1] == 'encode':
        _a = [x for x in sys.argv[2:] if not x.startswith('--')]
        _br = sys.argv[sys.argv.index('--br') + 1] if '--br' in sys.argv else '576000'
        _a = [x for x in _a if x != _br]
        sys.exit(0 if encode_and_check(_a[0], _a[1], _br, _a[1] + '.decoded.wav', clean=True) else 1)
    sys.exit(main(sys.argv))
