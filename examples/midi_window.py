"""A window of a MIDI file, start to end seconds, for listening to one passage
or rendering its stems. Each track is cut on its own, so a two-port file keeps
its ports (one merged track put every part on the last port named): what comes
before the window that is not a note (port, programs, controllers, SysEx,
tempo) is kept at the window's start in its order, so the parts sound as they
do there; notes begun before it are dropped, and the ones still held at the end
are closed.

    python3 examples/midi_window.py IN.mid OUT.mid START END
"""
import sys
import mido


def _tick_at(mid, seconds):
    """The tick at `seconds`, from the file's tempo map."""
    t, tick, tempo = 0.0, 0, 500000
    for msg in mido.merge_tracks(mid.tracks):
        dt = mido.tick2second(msg.time, mid.ticks_per_beat, tempo)
        if t + dt > seconds:
            return tick + mido.second2tick(seconds - t, mid.ticks_per_beat, tempo)
        t += dt
        tick += msg.time
        if msg.type == 'set_tempo':
            tempo = msg.tempo
    return tick


def window(path, start, end):
    mid = mido.MidiFile(path, clip=True)
    k0, k1 = round(_tick_at(mid, start)), round(_tick_at(mid, end))
    out = mido.MidiFile(type=1, ticks_per_beat=mid.ticks_per_beat)
    for tr in mid.tracks:
        o = mido.MidiTrack()
        out.tracks.append(o)
        tick, last, held = 0, k0, set()
        for msg in tr:
            tick += msg.time
            if msg.type == 'end_of_track' or tick > k1:
                break
            note = msg.type in ('note_on', 'note_off')
            if tick < k0:
                if not note:
                    o.append(msg.copy(time=0))
                continue
            if note:
                on = msg.type == 'note_on' and msg.velocity > 0
                key = (msg.channel, msg.note)
                if not on and key not in held:
                    continue
                (held.add if on else held.discard)(key)
            o.append(msg.copy(time=tick - last))
            last = tick
        for i, (ch, n) in enumerate(sorted(held)):
            o.append(mido.Message('note_off', channel=ch, note=n, time=(k1 - last) if i == 0 else 0))
        o.append(mido.MetaMessage('end_of_track', time=0))
    return out


if __name__ == '__main__':
    window(sys.argv[1], float(sys.argv[3]), float(sys.argv[4])).save(sys.argv[2])
