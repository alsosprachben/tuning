#!/usr/bin/env python3
"""The opening of Queen's "The Prophet's Song" as a demo of the koto, the
seashore and the electric guitars (a fan MIDI; not in the repo).

    python3 examples/prophet_demo.py IN.mid OUT.mid [beats=80]
    python3 examples/prophet_demo.py --whole MUXED.mid OUT.mid

then render OUT.mid as any file (blockrender.py OUT.mid OUT.wav).

THE WHOLE SONG shares channels the excerpt does not (Acc. Guitar 3 joins
Koto 2 on channel 1), so it goes through mt32mux first, each part its own
patch stamped per note:

    mt32mux.py IN.mid MUXED.mid --name "Koto 1=107" --name "Koto 2=107" --name "Bass=33"

(Bass, else the mux reads the name as a contrabass; the voices it takes to
53, Voice Oohs, a better singer than the file's synth lead.) --whole adds
the sea, as below, on a channel the mux leaves free.

The file's "Koto" tracks are GM 24 (nylon guitar), the nearest a GM set had:
they become the koto, 107. A track silent before the cut keeps only its
meta: its tick-0 program change would otherwise shadow the part sharing its
channel (Acc. Guitar 3 turned Koto 2 back into a nylon guitar, and Voice 2
the sea into a voice -- mt32check). Everything stops at BEATS (80: through
the band's entry at 71, ~41 s); a note still sounding there ends there, and
the last two beats fade on CC11.

THE SEA, which the record opens on and the file has no part for, is added on
channel 13 (no part uses it before the cut: "Voice 2" enters at beat 436):
alone, then faded out on CC11 over beats 4-8, gone before the koto's theme
(Ben: "too loud, and needs to fade out before the theme starts"). A fade
written on a held note, which the file renderer follows since THE CHANNEL
FADER (blockrender): before it, a note read CC7 and CC11 once, at its onset.
"""
import sys

import mido

KOTO_TRACKS = ("Koto 1", "Koto 2")
SEA_CH = 13
SEA_CC7 = 63                   # 8 dB under the 100 it first had: "too loud"


def _fade(ch, t0, t1, top=127, steps=16):
    return [(t0 + (t1 - t0) * i // steps, mido.Message("control_change", channel=ch, control=11,
                                                       value=int(round(top * (1 - i / float(steps))))))
            for i in range(steps + 1)]


def cut(src, dst, beats=80):
    m = mido.MidiFile(src)
    tpb = m.ticks_per_beat
    end = int(beats * tpb)
    out = mido.MidiFile(type=1, ticks_per_beat=tpb)
    for tr in m.tracks:
        koto = tr.name in KOTO_TRACKS
        ev, tick, held, chans = [], 0, {}, set()
        for msg in tr:
            tick += msg.time
            if tick > end:
                break
            if msg.type == "end_of_track":
                continue
            if koto and msg.type == "program_change":
                msg = msg.copy(program=107)
            if msg.type == "note_on" and msg.velocity > 0:
                held[(msg.channel, msg.note)] = True
            elif msg.type in ("note_off", "note_on"):
                held.pop((msg.channel, msg.note), None)
            if hasattr(msg, "channel"):
                chans.add(msg.channel)
            ev.append((tick, msg))
        if not any(m_.type == "note_on" and m_.velocity > 0 for _, m_ in ev):
            ev = [(t, m_) for t, m_ in ev if not hasattr(m_, "channel")]
            chans = set()
        for (c, n) in held:
            ev.append((end, mido.Message("note_off", channel=c, note=n, velocity=0)))
        if tr.name != "Drumkit":
            for c in chans:
                ev += _fade(c, end - 2 * tpb, end)
        out.tracks.append(_track(ev))
    out.tracks.append(_sea(tpb))
    out.save(dst)


def whole(src, dst):
    m = mido.MidiFile(src)
    used = {msg.channel for tr in m.tracks for msg in tr if hasattr(msg, "channel")}
    assert SEA_CH not in used, "the mux used channel %d" % SEA_CH
    m.tracks.append(_sea(m.ticks_per_beat))
    m.save(dst)


def _sea(tpb):
    return _track([
        (0, mido.MetaMessage("track_name", name="Seashore")),
        (0, mido.Message("program_change", channel=SEA_CH, program=122)),
        (0, mido.Message("control_change", channel=SEA_CH, control=7, value=SEA_CC7)),
        (0, mido.Message("note_on", channel=SEA_CH, note=60, velocity=90))]
        + _fade(SEA_CH, 4 * tpb, 8 * tpb)
        + [(8 * tpb, mido.Message("note_off", channel=SEA_CH, note=60, velocity=0))])


def _track(ev):
    tr = mido.MidiTrack()
    ev.sort(key=lambda e: e[0])
    last = 0
    for t, msg in ev:
        tr.append(msg.copy(time=t - last))
        last = t
    tr.append(mido.MetaMessage("end_of_track", time=0))
    return tr


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "--whole":
        whole(a[1], a[2])
    else:
        cut(a[0], a[1], float(a[2]) if len(a) > 2 else 80)
