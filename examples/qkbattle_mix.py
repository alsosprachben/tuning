#!/usr/bin/env python3
"""Ben's qkbttl02 (a 1990s sound-card piece) remixed so every part is heard.

    python3 examples/qkbattle_mix.py [SRC.mid] [outdir]

WHY IT NEEDS A MIX. The file's CC7 values were set by ear on a 90s sound card,
whose synth leads were far hotter than these voices. Rendered here, each part
alone and K-weighted (ITU BS.1770, the loudness the ear hears), relative to
the drums:

    rock organ +5.1   drawbar +2.9   drums 0   pipe organ -6.4   piano -8.4
    saw lead -13.3    woodblock -17.2          square lead -21.1

The two leads carry the tunes and sit 13-21 dB under the drums and 18-26 dB
under the organs.

WHY NOT CC7. The first version rewrote each channel's CC7 and the organs did
not move: on the drawbar, rock and church organs CC7 is the SWELL PEDAL (the
organ path in blockrender), which has a floor and is not a fader -- measured,
the rock organ asked for -3 dB came out +16. So the balance is made the way
choral.py makes a choir's: each part rendered DRY on its own, measured, summed
at the gain that puts it on its TARGET, and the hall given once to the sum
with the stems' room sidecars merged.

TARGETS are dB against the drums: the leads on top, the drums just under,
organs and piano behind, the woodblock as colour. A starting point for the
ear, not a measurement.

THE LESLIES, STOPPED. GM 18 ships with its rotor running fast
(RockOrganProperties.leslie_fast) and the file sends no CC1 on that channel,
so it spun all the way through; the drawbar's CC1s, written as vibrato for the
sound card, flicked its rotor between speeds. Both now have CC1 = 0, below 42
the half-moon at STOP (leslie.zone): steady organs. On a rotor voice CC1 is
not the amp's drive, so the overdrive is unchanged. That is the only change
made to the MIDI.
"""
import math
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, 'examples'))
import lib  # noqa: E402

# (part, track, drum notes or None, target dB against the rest of the kit).
# The kit is split so its hi-hats, bass drum and crashes can sit above the ride
# bell and guiro that make up most of it -- Ben, remembering the sound card:
# "the drums hi-hat and the bass and crashes were louder".
#
# Second pass, by Ben's ear: the drawbar "kind of above everything" and the
# square lead audible with it -- "the square and the drawbar are the climax";
# the rock organ "more of the initial layering", so behind; the piano "a lot
# louder, since it is part of the rhythmic percussion"; the pipe organ, which
# is the bass line (C1-D3), up a little with the bass drum.
KICK, HATS, CRASHES = {35, 36}, {42, 44, 46}, {49, 52, 55, 57}
RIDE = {51, 53, 59}
TOMS = {41, 43, 45, 47, 48, 50}
LIFTED = KICK | HATS | CRASHES
# Third pass: the ride "3 dB more". It is split from the rest of the kit and
# both are summed at the gain the whole rest-of-kit had, the ride 3 dB over it.
# The rest-of-kit stem that includes the ride is still rendered, as the
# REFERENCE everything else is measured against, so nothing else moves.
# Fourth pass: the tom fill in the last bar (57.0-58.0 s), "my favorite part",
# was buried -- the bass drum, crashes and saw lead all sat over it -- so the
# toms are split out too, 6 dB over the kit.
FIXED = [
    ('kit less ride', 1, ('rest', LIFTED | RIDE | TOMS), 0.0),
    ('ride',          1, RIDE,                           +3.0),
    ('toms',          1, TOMS,                          +12.0),   # +6 left them 6.5 dB under the bass drum
]
PARTS = [
    ('kit',         1, ('rest', LIFTED), 0.0),      # the reference: measured, not mixed
    ('bass drum',   1, KICK,     +4.0),
    ('hi-hats',     1, HATS,     +5.0),
    ('crashes',     1, CRASHES,  +1.0),      # +4 was too loud, by ear
    ('pipe organ',  2, None,     +4.0),      # -2, then 6 dB up by ear
    ('saw lead',    3, None,     +7.0),      # +1, then 6 dB up by ear
    ('drawbar',     4, None,     +9.0),      # +3, then 3 dB more twice by ear
    ('square lead', 5, None,     +8.0),      # +2, +5, then +8: its entrance must cut through
    ('piano',       6, None,     +1.0),
    ('rock organ',  7, None,     +1.0),      # -5, then 3 dB up twice by ear
    ('woodblock',   8, None,     -6.0),
]
REFERENCE = 'kit'              # the drums, less what is lifted out of them
# The two organs with a Leslie: the rock organ (GM 18, channel 9) and the
# drawbar (GM 16, channel 5). Both are made steady: every CC1 the file sends
# them is taken out -- on the drawbar it was written as vibrato for the sound
# card, which here is the half-moon flicking the rotor between speeds -- and
# CC1 = 0, the half-moon at STOP, goes in after the program change.
ROTOR_CHANNELS = (8, 4)
# THE PIPE ORGAN, which carries the bass line (C1-D3), with more stops pulled:
# the principal chorus with gravity -- principal 16', principal 8', octave 4',
# super octave 2' (bits 4, 0, 1, 2 of the church organ's stop word) -- where
# the file draws none and GM 19 plays its principal 8' alone. The stop word is
# CC11 (bits 0-6) and CC43 (7-13) on this voice.
PIPE_ORGAN_CH = 2
# CHORUS ON THE TWO SYNTH LEADS, as Ben's card gave them: CC93, the GM 2 / GS
# chorus send, half-way. The renderer plays it as copies detuned +/-7 cents and
# slowly swept (chorus.py) -- a chorus pedal in front of the voice.
CHORUS = {3: 64, 5: 64}          # channel -> CC93: the saw lead and the square lead
PIPE_STOPS = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 4)
# THE SMALLEST ROOM, for a produced sound rather than a concert: 'chamber', a
# furnished salon whose reverberation sits 3 dB under the direct sound
# (tonelib ROOM_PRESETS). Set for the stems' early reflections AND the tail.
ROOM = 'chamber'
# THE KIT FROM THE AUDIENCE'S SIDE (percussion_map.kit_pan): hi-hats right of
# centre, ride left. The file pans the drums to 24 as the hi-hats enter and
# sweeps back to 64 over the bar that ends them -- the climax, which Ben heard
# as the hi-hats moving from the left to the right. Only a kit with the hi-hat
# right of centre makes that sweep cross.
KIT_VIEW = 'audience'


def kweight(fs):
    """ITU-R BS.1770 K-weighting at any rate: the high shelf, then the RLB
    high-pass, from their analogue parameters."""
    G, Q, fc = 3.99984385397, 0.7071752369554193, 1681.9744509555319
    A = 10 ** (G / 40.0); w0 = 2 * math.pi * fc / fs; al = math.sin(w0) / (2 * Q)
    c = math.cos(w0); r = 2 * math.sqrt(A) * al
    b = [A * ((A + 1) + (A - 1) * c + r), -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - r)]
    a = [(A + 1) - (A - 1) * c + r, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - r]
    b1, a1 = [v / a[0] for v in b], [v / a[0] for v in a]
    Q2, fc2 = 0.5003270373253953, 38.13547087613982
    w0 = 2 * math.pi * fc2 / fs; al = math.sin(w0) / (2 * Q2); c = math.cos(w0)
    b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]; a = [1 + al, -2 * c, 1 - al]
    return b1, a1, [v / a[0] for v in b], [v / a[0] for v in a]


def loudness(wav, win=0.4, gate=-20.0):
    """K-weighted median loudness over the windows where the part is playing
    (within `gate` dB of its loudest): how loud it is when it is there."""
    from scipy.io import wavfile
    from scipy.signal import lfilter
    sr, x = wavfile.read(wav)
    x = x.astype(np.float64)
    if x.ndim == 1:
        x = x[:, None]
    b1, a1, b2, a2 = kweight(sr)
    y = lfilter(b2, a2, lfilter(b1, a1, x, axis=0), axis=0)
    n = int(win * sr); k = len(y) // n
    db = 10 * np.log10((y[:k * n].reshape(k, n, -1) ** 2).mean(1).sum(1) + 1e-30)
    return float(np.median(db[db > db.max() + gate]))


def steady_organ(src, dest):
    """The source with both organs' rotors stopped: their CC1s removed (the
    time each carried passes to the next event) and CC1 = 0 after each
    program change."""
    m = mido.MidiFile(src)
    for tr in m.tracks:
        out = mido.MidiTrack()
        carry = 0
        for e in tr:
            if e.type == 'control_change' and e.control == 1 and e.channel in ROTOR_CHANNELS:
                carry += e.time
                continue
            if carry:
                e = e.copy(time=e.time + carry); carry = 0
            out.append(e)
            if e.type == 'program_change' and e.channel in ROTOR_CHANNELS:
                out.append(mido.Message('control_change', channel=e.channel,
                                        control=1, value=0, time=0))
            if e.type == 'program_change' and e.channel in CHORUS:
                out.append(mido.Message('control_change', channel=e.channel,
                                        control=93, value=CHORUS[e.channel], time=0))
            if e.type == 'program_change' and e.channel == PIPE_ORGAN_CH:
                for cc, v in ((11, PIPE_STOPS & 0x7F), (43, PIPE_STOPS >> 7)):
                    out.append(mido.Message('control_change', channel=e.channel,
                                            control=cc, value=v, time=0))
        tr[:] = out
    m.save(dest)
    return dest


# THE DRAWBAR'S SHAKE. Ben's file flicks the mod wheel to 127 for a fifth of a
# second on the held chord that ends the hi-hat bar (43.54 s) and again at
# 46.04 s -- on his card, CC1 was vibrato depth, and the flick was meant to
# sound "similar to a trumpet shake". Here CC1 on a drawbar is the Leslie's
# half-moon (and is taken out, to keep the organ steady), and the file
# renderer does not play mod-wheel vibrato at all, so the shake is put back on
# the drawbar's own stem: a pitch vibrato over exactly the spans the wheel was
# up, at GM 2's default modulation depth (RPN 0/5: 50 cents) and 6.5 Hz, faded
# in and out over 15 ms so it does not click.
SHAKE_CENTS, SHAKE_HZ, SHAKE_FADE_S = 50.0, 6.5, 0.015


def wheel_spans(src, channel):
    """[(start s, end s)] where CC1 on `channel` is above zero."""
    m = mido.MidiFile(src)
    t, up, out = 0.0, None, []
    for e in m:
        t += e.time
        if e.type == 'control_change' and e.control == 1 and e.channel == channel:
            if e.value > 0 and up is None:
                up = t
            elif e.value == 0 and up is not None:
                out.append((up, t)); up = None
    return out


def shake(wav, dest, spans):
    """A pitch vibrato over `spans`, made by a modulated delay: a delay that
    swings by A*sin(2*pi*f*t) shifts the pitch by up to 2*pi*f*A, so
    A = (2**(cents/1200) - 1) / (2*pi*f)."""
    from scipy.io import wavfile
    sr, x = wavfile.read(wav)
    y = x.astype(np.float64).copy()
    amp = (2 ** (SHAKE_CENTS / 1200.0) - 1) / (2 * math.pi * SHAKE_HZ) * sr   # samples
    for a, b in spans:
        i0, i1 = int(a * sr), min(len(x), int(b * sr))
        n = np.arange(i0, i1)
        tt = (n - i0) / float(sr)
        fade = np.minimum(1.0, np.minimum(tt, (i1 - n) / float(sr)) / SHAKE_FADE_S)
        d = amp * fade * np.sin(2 * math.pi * SHAKE_HZ * tt)
        src = n - amp - d                       # a constant lag, swinging around it
        k = np.floor(src).astype(int); fr = src - k
        k = np.clip(k, 0, len(x) - 2)
        for c in range(y.shape[1]):
            v = x[:, c].astype(np.float64)
            y[i0:i1, c] = v[k] * (1 - fr) + v[k + 1] * fr
    wavfile.write(dest, sr, y.astype(x.dtype))
    return dest


# THE LOOP. This is game music: it loops. The file ends its music at the end of
# bar 20 and then, a few bars later, sounds one lone note -- a MARKER, there so
# that the sound card would keep rendering until the last crash and the reverb
# had died away, and the loop could be cut from a recording. So: cut at the
# loop point (the end of the bar where the music ends), take everything that
# rings on after it -- stopping short of the marker, which must not be heard --
# and add it onto the start, where it would be sounding under the next pass.
# Played end to start, the join is then seamless. A WAV, because an MP3's
# encoder delay and padding would put a gap in every repeat.


def loop_points(src):
    """(loop point, marker onset), in seconds: the loop point is the end of
    the bar in which the music (every note but the marker) ends, and the
    marker is the file's last note-on."""
    m = mido.MidiFile(src)
    tpb, tempo, bar = m.ticks_per_beat, 500000, None
    notes = []                                   # (on tick, off tick)
    for tr in m.tracks:
        t, held = 0, {}
        for e in tr:
            t += e.time
            if e.type == 'set_tempo':
                tempo = e.tempo
            elif e.type == 'time_signature' and bar is None:
                bar = tpb * 4 * e.numerator // e.denominator
            elif e.type == 'note_on' and e.velocity > 0:
                held[(e.channel, e.note)] = t
            elif e.type in ('note_on', 'note_off') and (e.channel, e.note) in held:
                notes.append((held.pop((e.channel, e.note)), t))
    notes.sort()
    marker_on = notes[-1][0]
    end = max(off for on, off in notes[:-1])
    loop = -(-end // bar) * bar                  # up to the bar line
    sec = lambda tick: tick * tempo / 1e6 / tpb  # one tempo in this file
    return sec(loop), sec(marker_on), loop // bar


def make_loop(wav, dest, loop_s, marker_s):
    """The loop: [0, loop) with [loop, marker) added onto its start."""
    from scipy.io import wavfile
    sr, x = wavfile.read(wav)
    # TO FLOAT IN [-1, 1] FIRST. The mix is 32-bit integer PCM; written back
    # as float without this, every sample is hundreds of millions and a float
    # WAV's range is +/-1, so the whole loop clipped into a square wave.
    if np.issubdtype(x.dtype, np.integer):
        x = x.astype(np.float64) / float(np.iinfo(x.dtype).max + 1)
    else:
        x = x.astype(np.float64)
    L, M = int(round(loop_s * sr)), int(round(marker_s * sr))
    y = x[:L].copy()
    tail = x[L:M]
    n = min(len(tail), L)
    y[:n] += tail[:n]
    peak = np.abs(y).max()
    if peak > 1.0:
        y /= peak                     # the fold can add up past full scale
    wavfile.write(dest, sr, y.astype(np.float32))
    after = 20 * np.log10(np.abs(tail[-int(0.5 * sr):]).max() / np.abs(x).max() + 1e-12)
    return dest, len(tail) / float(sr), after


def only_notes(path, track, keep):
    """Keep only the drum notes in `keep` -- a set, or ('rest', dropped) for
    every note NOT in `dropped` -- carrying the time of what is dropped to
    what follows."""
    rest = isinstance(keep, tuple) and keep[0] == 'rest'
    drop = keep[1] if rest else None
    m = mido.MidiFile(path)
    tr = m.tracks[track]
    out = mido.MidiTrack(); carry = 0
    for e in tr:
        if e.type in ('note_on', 'note_off'):
            ok = (e.note not in drop) if rest else (e.note in keep)
            if not ok:
                carry += e.time
                continue
        if carry:
            e = e.copy(time=e.time + carry); carry = 0
        out.append(e)
    m.tracks[track] = out
    m.save(path)
    return path


def main(argv):
    src = os.path.expanduser(argv[1] if len(argv) > 1 else '~/Downloads/midi/qkbttl02.mid')
    outdir = os.path.expanduser(argv[2] if len(argv) > 2 else '~/Downloads/bwx-renders/qkbttl02_mix')
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    mid = steady_organ(src, os.path.join(outdir, stem + '_steady.mid'))
    env = {'TUNING_MASTER_DB': '-14', 'TUNING_ROOM': ROOM, 'TUNING_KIT_VIEW': KIT_VIEW}
    wavs, lufs = {}, {}
    for name, t, notes, _ in PARTS + FIXED:
        tag = name.replace(' ', '-')
        smid = os.path.join(outdir, '%s.%s.mid' % (stem, tag))
        lib.take_tracks(mid, smid, [t])
        if notes is not None:
            only_notes(smid, 1, notes)          # take_tracks puts the part at index 1
        wav = os.path.join(outdir, '%s.%s.%s%s.wav' % (stem, tag, ROOM,
                                                     '.' + KIT_VIEW if notes is not None else ''))
        # RENDER ONLY WHAT CHANGED, by content: the stem MIDIs are rewritten on
        # every run, so their times say nothing, and a full render is fifteen
        # minutes where a change of gains alone should take seconds.
        import hashlib
        digest = hashlib.sha1(open(smid, 'rb').read() + repr(sorted(env.items())).encode()).hexdigest()
        mark = wav + '.src'
        if not (os.path.exists(wav) and os.path.exists(mark) and open(mark).read() == digest):
            lib.render_plain(smid, wav, tuner='even', extra_env=env)
            open(mark, 'w').write(digest)
        wavs[name], lufs[name] = wav, loudness(wav)
    spans = wheel_spans(src, 4)
    if spans:
        wavs['drawbar'] = shake(wavs['drawbar'], wavs['drawbar'].replace('.wav', '.shake.wav'), spans)
        # the sidecar goes with it
        import shutil
        shutil.copy(os.path.splitext(wavs['drawbar'].replace('.shake', ''))[0] + '.room.json',
                    os.path.splitext(wavs['drawbar'])[0] + '.room.json')
        print("  drawbar shake at %s" % ", ".join("%.2f-%.2f s" % s_ for s_ in spans))
    ref = lufs[REFERENCE]
    names, gains = [], []
    for name, _t, _n, target in PARTS:
        now = lufs[name] - ref
        g = target - now
        print("  %-13s %+6.1f dB -> %+5.1f  (gain %+6.1f dB)" % (name, now, target, g))
        if name != REFERENCE:
            names.append(name); gains.append(10 ** (g / 20.0))
    for name, _t, _n, g in FIXED:
        print("  %-13s at the kit's gain %+.1f dB" % (name, g))
        names.append(name); gains.append(10 ** (g / 20.0))
    dry = os.path.join(outdir, '%s_mix12.%s.dry.wav' % (stem, ROOM))
    lib.sum_wavs([wavs[n] for n in names], dry, gains=gains)
    lib.merge_room([os.path.splitext(wavs[n])[0] + '.room.json' for n in names],
                   os.path.splitext(dry)[0] + '.room.json')
    wet = os.path.join(outdir, '%s_mix12.%s.wav' % (stem, ROOM))
    lib.roomtail(dry, wet, env={'TUNING_ROOM': ROOM})
    print("  -> %s" % lib.mp3(wet))
    loop_s, marker_s, bars = loop_points(src)
    lw, tail_s, residue = make_loop(wet, wet.replace('.wav', '.loop.raw.wav'), loop_s, marker_s)
    final = wet.replace('.wav', '.loop.wav')
    subprocess.run(['sox', lw, '-b', '16', final, 'gain', '-n', '-1'], check=True)
    os.unlink(lw)
    print("  loop: %d bars, %.4f s; %.2f s of tail folded onto the start, its last "
          "half second %.0f dB under the peak -> %s" % (bars, loop_s, tail_s, residue, final))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
