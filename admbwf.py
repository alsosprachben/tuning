#!/usr/bin/env python3
"""Write the object renders out as an ADM BWF file.

`blockrender.py --objects` gives a mono signal per source and a manifest of
where each one sits. That is everything an object-based format needs, but as
loose files it is nothing a renderer can open. ADM BWF is the format that
carries both: a plain multichannel WAV with two extra RIFF chunks --

    chna   binds each WAV channel to an audioTrackUID
    axml   the ADM metadata itself (ITU-R BS.2076), as XML

and it is the one worth writing because it is the common input to everything
else. Dolby's renderer ingests it, and so do the MPEG-H authoring tools, which
matters because neither Atmos nor MPEG-H can be encoded from here: Atmos needs
a licensed encoder, and Fraunhofer's open MPEG-H release is a decoder. ADM BWF
is an open ITU standard with no such gate, so this is the furthest the pipeline
can go on its own -- and far enough, since it is what the licensed tools eat.

Coordinates. The model puts the listener at the origin with +x right, +y
forward and +z up, in metres. ADM's polar convention has azimuth 0 ahead and
**positive to the LEFT**, so the sign flips; elevation is above the horizontal;
distance is normalised against a reference rather than given in metres.

Usage:
    python3 admbwf.py OBJECTS_DIR OUT.wav [--bits 24] [--name "..."]
"""

import glob
import json
import math
import os
import struct
import sys
import wave

import numpy as np

TYPE_OBJECTS = '0003'


def _tc(seconds):
    """ADM's hh:mm:ss.fffff."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return "%02d:%02d:%08.5f" % (h, m, s)


def polar(x, y, z, reference):
    """Metres in the model's frame to ADM azimuth/elevation/distance.

    Azimuth is positive anti-clockwise -- to the left -- where the model counts
    x positive to the right, so it is negated. Getting that backwards mirrors
    the whole stage and is not obvious from a spectrum.
    """
    r = math.sqrt(x * x + y * y + z * z) or 1e-9
    az = math.degrees(math.atan2(-x, y))
    el = math.degrees(math.asin(max(-1.0, min(1.0, z / r))))
    return az, el, max(0.0, min(1.0, r / reference if reference else 1.0))


def build_axml(objects, duration, sample_rate, bits, programme):
    """The ADM tree. One object per source, each with a single block: our
    sources hold still for the length of a render, so one audioBlockFormat
    covering the whole duration says exactly that. A source that moved would
    become a series of them, which is the shape the format is really for."""
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<ebuCoreMain xmlns="urn:ebu:metadata-schema:ebuCore_2015"'
         ' xmlns:dc="http://purl.org/dc/elements/1.1/">',
         ' <coreMetadata>', '  <format>',
         '   <audioFormatExtended version="ITU-R_BS.2076-2">']

    def esc(s):
        return (s.replace('&', '&amp;').replace('<', '&lt;')
                 .replace('>', '&gt;').replace('"', '&quot;'))

    L.append('    <audioProgramme audioProgrammeID="APR_1001"'
             ' audioProgrammeName="%s" start="%s" end="%s">'
             % (esc(programme), _tc(0.0), _tc(duration)))
    L.append('     <audioContentIDRef>ACO_1001</audioContentIDRef>')
    L.append('    </audioProgramme>')
    L.append('    <audioContent audioContentID="ACO_1001"'
             ' audioContentName="%s">' % esc(programme))
    for i in range(len(objects)):
        L.append('     <audioObjectIDRef>AO_%04d</audioObjectIDRef>' % (1001 + i))
    L.append('    </audioContent>')

    for i, ob in enumerate(objects):
        n = i + 1
        ao = 'AO_%04d' % (1001 + i)
        ap = 'AP_%s%04x' % (TYPE_OBJECTS, 0x1001 + i)
        ac = 'AC_%s%04x' % (TYPE_OBJECTS, 0x1001 + i)
        as_ = 'AS_%s%04x' % (TYPE_OBJECTS, 0x1001 + i)
        at = 'AT_%s%04x_01' % (TYPE_OBJECTS, 0x1001 + i)
        atu = 'ATU_%08x' % n
        name = esc(ob['name'])
        az, el, dist = ob['polar']

        L.append('    <audioObject audioObjectID="%s" audioObjectName="%s"'
                 ' start="%s" duration="%s">' % (ao, name, _tc(0.0), _tc(duration)))
        L.append('     <audioPackFormatIDRef>%s</audioPackFormatIDRef>' % ap)
        L.append('     <audioTrackUIDRef>%s</audioTrackUIDRef>' % atu)
        L.append('    </audioObject>')
        L.append('    <audioPackFormat audioPackFormatID="%s"'
                 ' audioPackFormatName="%s" typeDefinition="Objects"'
                 ' typeLabel="%s">' % (ap, name, TYPE_OBJECTS))
        L.append('     <audioChannelFormatIDRef>%s</audioChannelFormatIDRef>' % ac)
        L.append('    </audioPackFormat>')
        L.append('    <audioChannelFormat audioChannelFormatID="%s"'
                 ' audioChannelFormatName="%s" typeDefinition="Objects"'
                 ' typeLabel="%s">' % (ac, name, TYPE_OBJECTS))
        L.append('     <audioBlockFormat audioBlockFormatID="AB_%s%04x_00000001"'
                 ' rtime="%s" duration="%s">'
                 % (TYPE_OBJECTS, 0x1001 + i, _tc(0.0), _tc(duration)))
        L.append('      <cartesian>0</cartesian>')
        L.append('      <position coordinate="azimuth">%.4f</position>' % az)
        L.append('      <position coordinate="elevation">%.4f</position>' % el)
        L.append('      <position coordinate="distance">%.4f</position>' % dist)
        L.append('     </audioBlockFormat>')
        L.append('    </audioChannelFormat>')
        L.append('    <audioStreamFormat audioStreamFormatID="%s"'
                 ' audioStreamFormatName="%s" formatDefinition="PCM"'
                 ' formatLabel="0001">' % (as_, name))
        L.append('     <audioChannelFormatIDRef>%s</audioChannelFormatIDRef>' % ac)
        L.append('     <audioTrackFormatIDRef>%s</audioTrackFormatIDRef>' % at)
        L.append('    </audioStreamFormat>')
        L.append('    <audioTrackFormat audioTrackFormatID="%s"'
                 ' audioTrackFormatName="%s" formatDefinition="PCM"'
                 ' formatLabel="0001">' % (at, name))
        L.append('     <audioStreamFormatIDRef>%s</audioStreamFormatIDRef>' % as_)
        L.append('    </audioTrackFormat>')
        L.append('    <audioTrackUID UID="%s" sampleRate="%d" bitDepth="%d">'
                 % (atu, sample_rate, bits))
        L.append('     <audioTrackFormatIDRef>%s</audioTrackFormatIDRef>' % at)
        L.append('     <audioPackFormatIDRef>%s</audioPackFormatIDRef>' % ap)
        L.append('    </audioTrackUID>')

    L += ['   </audioFormatExtended>', '  </format>', ' </coreMetadata>',
          '</ebuCoreMain>', '']
    return "\n".join(L).encode('utf-8')


def build_chna(count):
    """One 40-byte entry per track, binding WAV channel n to its UID."""
    out = struct.pack('<HH', count, count)
    for i in range(count):
        n = i + 1
        out += struct.pack('<H', n)
        out += ('ATU_%08x' % n).encode('ascii').ljust(12, b'\x00')
        out += ('AT_%s%04x_01' % (TYPE_OBJECTS, 0x1001 + i)).encode('ascii').ljust(14, b'\x00')
        out += ('AP_%s%04x' % (TYPE_OBJECTS, 0x1001 + i)).encode('ascii').ljust(11, b'\x00')
        out += b'\x00'
    return out


def _chunk(tag, payload):
    pad = b'\x00' if len(payload) % 2 else b''
    return tag + struct.pack('<I', len(payload)) + payload + pad


def write_adm(path, signals, meta, sample_rate, bits=24, programme='render'):
    """Interleave the object signals and write the BWF with chna and axml."""
    n = min(len(s) for s in signals)
    ch = len(signals)
    duration = n / float(sample_rate)
    for ob in meta:
        ob['polar'] = polar(ob['x'], ob['y'], ob['z'], ob['reference'])

    frame = ch * (bits // 8)
    size = n * frame
    if size > 0xFFFFFFFF - (1 << 20):
        raise SystemExit(
            "%.1f GB of audio exceeds what a RIFF WAV can address; write fewer "
            "objects or a lower bit depth (RF64 is not implemented)."
            % (size / 1e9))

    # Interleave a second at a time. Materialising the whole thing first costs
    # channels * frames * 8 bytes -- 7.4 GB for a 40-object Neptune, which
    # thrashes long before it fails, so the first attempt simply appeared to
    # hang rather than reporting anything.
    fmt = struct.pack('<HHIIHH', 1, ch, sample_rate,
                      sample_rate * frame, frame, bits)
    head = (b'WAVE' + _chunk(b'fmt ', fmt)
            + _chunk(b'chna', build_chna(ch))
            + _chunk(b'axml', build_axml(meta, duration, sample_rate, bits, programme)))
    data_pad = size % 2
    riff = len(head) + 8 + size + data_pad
    step = sample_rate
    with open(path, 'wb') as fh:
        fh.write(b'RIFF' + struct.pack('<I', riff) + head)
        fh.write(b'data' + struct.pack('<I', size))
        buf = np.empty((step, ch), np.float64)
        for start in range(0, n, step):
            m = min(step, n - start)
            view = buf[:m]
            for i, s in enumerate(signals):
                view[:, i] = s[start:start + m]
            np.clip(view, -1.0, 1.0, view)
            if bits == 24:
                q = (view * 8388607.0).astype('<i4')
                fh.write(q.view(np.uint8).reshape(-1, 4)[:, :3].tobytes())
            elif bits == 32:
                fh.write((view * 2147483647.0).astype('<i4').tobytes())
            else:
                fh.write((view * 32767.0).astype('<i2').tobytes())
        if data_pad:
            fh.write(b'\x00')
    return n, ch, duration


def read_mono(path):
    """One channel of a WAV as floats. An object render is already mono; a stem
    is not, and averaging one would fold a placed source back to a point, so
    take the left channel and let the caller know it was not an object."""
    w = wave.open(path, 'rb')
    n, sw, sr, nch = (w.getnframes(), w.getsampwidth(),
                      w.getframerate(), w.getnchannels())
    data = w.readframes(n)
    w.close()
    if sw == 4:
        a = np.frombuffer(data, '<i4').astype(np.float64) / 2147483647.0
    elif sw == 2:
        a = np.frombuffer(data, '<i2').astype(np.float64) / 32767.0
    else:
        raise SystemExit("%s: unsupported sample width %d" % (path, sw))
    if nch != 1:
        raise SystemExit("%s has %d channels; ADM objects are mono -- render "
                         "with --objects, not --stems" % (path, nch))
    return a, sr


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[-1])
        return 2
    src, outp = argv[1], argv[2]
    bits = int(argv[argv.index('--bits') + 1]) if '--bits' in argv else 24
    name = argv[argv.index('--name') + 1] if '--name' in argv else \
        os.path.basename(outp).rsplit('.', 1)[0]

    manifests = glob.glob(os.path.join(src, '*.objects.json'))
    if not manifests:
        raise SystemExit("no *.objects.json in %s -- run blockrender with "
                         "--objects --by-source first" % src)
    man = json.load(open(manifests[0]))
    sr = man.get('sample_rate', 44100)
    ref = man.get('radiation_distance_m', 12.0)
    listener_y = man.get('listener_distance_m', 2.0)

    signals, meta = [], []
    for ob in man['objects']:
        f = os.path.join(src, ob['file'])
        if not os.path.exists(f):
            raise SystemExit("missing %s" % f)
        sig, fsr = read_mono(f)
        if fsr != sr:
            raise SystemExit("%s is %d Hz, manifest says %d" % (f, fsr, sr))
        signals.append(sig)
        meta.append({'name': ob['file'].rsplit('.', 1)[0],
                     'x': ob.get('x_m', 0.0), 'y': listener_y,
                     'z': ob.get('z_m', 0.0), 'reference': ref})

    n, ch, dur = write_adm(outp, signals, meta, sr, bits, name)
    print("== %s" % outp)
    print("   %d objects, %.1f s, %d Hz, %d-bit  (%.2f GB)"
          % (ch, dur, sr, bits, os.path.getsize(outp) / 1e9))
    print("   azimuth is positive to the LEFT, distance normalised to %.1f m" % ref)
    for ob in meta[:6]:
        az, el, d = ob['polar']
        print("     %-34s az %+7.2f  el %+6.2f  dist %.3f"
              % (ob['name'], az, el, d))
    if len(meta) > 6:
        print("     ... %d more" % (len(meta) - 6))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
