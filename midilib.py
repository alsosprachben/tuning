#!/usr/bin/env python

from tunelib import *

middle_c = 60

import os
import struct

"""
Copyright Ben Woolley 2010.
All rights reserved.
"""

from patches import patches
from patch_map import property_class_for_program

# Python 3 compatibility: indexing bytes yields int, where Python 2 yielded
# str. Accept both so the byte-level MIDI parsing below works unchanged.
_builtin_ord = ord
def ord(c):
    return c if isinstance(c, int) else _builtin_ord(c)

# Tuning system used for the adaptive retuning of sounding notes.
# Select by name with set_tuner(); defaults to the stretch temperament.
tuner_registry = {
    "stretch": StretchTuner,
    "even": EvenTuner,
    "linear": LinearTuner,
    "linear5": Linear5Tuner,
    "pyth": PythTuner,
    "just": JustTuner,
    "well": WellTuner,
    "linearwell": LinearWellTuner,
    "bechstein": BechsteinTuner,
    "dynamic": Tuner,
}
tuner_class = StretchTuner

# Tonal center governor for the dynamic tuner. Common-tone anchoring alone
# lets commas pump the pitch level without bound (a I-vi-ii-V cycle drifts
# a syntonic comma per pass, and the anchor note changes chord to chord).
# The governor measures each solution's implied center against a fixed
# reference grid, follows it at a bounded rate so nothing jumps, and leaks
# it back toward the grid a little every event, so sustained notes glide
# by at most a few cents while the pitch level stays moored.
TUNING_FOLLOW_CENTS = float(os.environ.get("TUNING_FOLLOW_CENTS", "3.0"))
TUNING_RECENTER_CENTS = float(os.environ.get("TUNING_RECENTER_CENTS", "1.0"))

def set_tuner(name):
    global tuner_class
    key = name.lower()
    if key not in tuner_registry:
        raise ValueError("unknown tuner %r; choose from: %s"
                         % (name, ", ".join(sorted(tuner_registry))))
    tuner_class = tuner_registry[key]

def notename(n):
    n = int(n + .5)
    o = n / 12
    return "%i %s" % (
            o - 1,
            {
                0:  "C",
                1:  "C#/Db",
                2:  "D",
                3:  "D#/Eb",
                4:  "E",
                5:  "F",
                6:  "F#/Gb",
                7:  "G",
                8:  "G#/Ab",
                9:  "A",
                10: "A#/Bb",
                11: "B",
            }[n - o * 12],
        )

def p(o):
    import pprint
    return pprint.pformat(o, depth=2)
    
def h(o):
    s = ""
    for char in o:
        i = ord(char)
        if i > 16:
            s += hex(i)[2:] + " "
        else:
            s += "0" + hex(i)[2:] + " "
    return s

dictstr = lambda s: (s.__class__.__name__  + ": " if hasattr(s, "__class__") else "") + (p(s.__dict__) if hasattr(s, "__dict__") else "None")


class ChannelEvent:
    class NoteOff:
        def __init__(self, t, midi_channel, note, velocity):
            self.time = t
            self.midi_channel = midi_channel
            self.note = note
            self.velocity = velocity
            
    class NoteOn:
        def __init__(self, t, midi_channel, note, velocity):
            self.time = t
            self.midi_channel = midi_channel
            self.note = note
            self.velocity = velocity
    
    class NoteAftertouch:
        def __init__(self, t, midi_channel, note, pressure):
            self.time = t
            self.midi_channel = midi_channel
            self.note = note
            self.pressure = pressure
    
    class Controller:    
        def __init__(self, t, midi_channel, control, value):
            self.time = t
            self.midi_channel = midi_channel
            self.control = control
            self.value = value
    
    class ProgramChange:
        def __init__(self, t, midi_channel, program, unused):
            self.time = t
            self.midi_channel = midi_channel
            self.program = program
            
    class ChannelAftertouch:
        def __init__(self, t, midi_channel, pressure, unused):
            self.time = t
            self.midi_channel = midi_channel
            self.pressure = pressure
    
    class PitchBend:
        def __init__(self, t, midi_channel, lsb, msb):
            self.time = t
            self.midi_channel = midi_channel
            self.lsb = lsb
            self.msb = msb
            self.value = (float(self.lsb|(self.msb<<7)) / 8192) - 1
    
    classes = {
        0x8: NoteOff,
        0x9: NoteOn,
        0xA: NoteAftertouch,
        0xB: Controller,
        0xC: ProgramChange,
        0xD: ChannelAftertouch,
        0xE: PitchBend,
    }

    def __init__(self, t, message_type, midi_channel, arg1, arg2):
        self.time = t
        self.message_type = message_type
        self.midi_channel = midi_channel
        self.arg1 = arg1
        self.arg2 = arg2
        
        self.event = self.classes.get(self.message_type, lambda a, b, c, d: None)(self.time, self.midi_channel, self.arg1, self.arg2)
        
class MetaEvent:

    class ChannelSpecific:
        channel_specific = True
        
    class ChannelGeneric:
        channel_specific = False

    class Sequence(ChannelSpecific):
        def __init__(self, t, bytes):
            self.time = t
            lsb, msb = ord(bytes[0]), ord(bytes[1])
            self.sequence = self.lsb|(self.msb<<8)

    class Text(ChannelSpecific):
        def __init__(self, t, bytes):
            self.time = t
            self.text = bytes
        
        def __str__(self):
            return self.__class__.__name__ + " (" + str(self.time) + "): " + self.text
            
    class Copyright(Text): pass
    class TrackName(Text): pass
    class InstrumentName(Text): pass
    class Lyrics(Text): pass
    class Marker(Text): pass
    class CuePoint(Text): pass
    
    class Channel(ChannelGeneric):
        def __init__(self, t, bytes):
           self.time = t
           self.midi_channel = ord(bytes[0])
    
    class EndOfTrack(ChannelGeneric):
        def __init__(self, t, bytes):
            self.time = t
    
    class Tempo(ChannelGeneric):
        microseconds_per_minute = 60000000
        
        def __init__(self, t = 0, bytes = None):
            self.time = t
            if bytes:
                b1, b2, b3 = ord(bytes[0]), ord(bytes[1]), ord(bytes[2])
                self.microseconds_per_beat = b3|(b2<<8)|(b1<<16)
            else:
                self.microseconds_per_beat = self.microseconds_per_minute / 120
            
            self.bpm = float(self.microseconds_per_minute) / self.microseconds_per_beat
    
    class SMPTEOffset(ChannelGeneric):
        def __init__(self, t, bytes):
            self.time = t
            self.framerate =(ord(bytes[0]) & 0b11000000) >> 6
            self.hour      = ord(bytes[0]) & 0b00111111
            self.min       = ord(bytes[1])
            self.sec       = ord(bytes[2])
            self.frame     = ord(bytes[3])
            self.subframe  = ord(bytes[4])
            
    class TimeSignature(ChannelGeneric):
        def __init__(self, t = 0, bytes = None):
            self.time = t
            if bytes:
                n, bd, metronome, clock32 = ord(bytes[0]), ord(bytes[1]), ord(bytes[2]), ord(bytes[3])
            else:
                n, bd, metronome, clock32 = 4, 2, 24, 8
            self.n = n
            self.d = 2 ** bd
            self.metronome = metronome
            self.clock32 = clock32
            
    class KeySignature(ChannelGeneric):
        def __init__(self, t = 0, bytes = None):
            self.time = t
            if bytes:
                self.key = struct.unpack('!b', bytes[0])[0]
                self.minor = bool(ord(bytes[1]))
            else:
                self.key = 0
                self.minor = False
            
    class SequencerSpecific(ChannelGeneric):
        def __init__(self, t, bytes):
            self.time = t
            self.bytes = bytes
            
    
    classes = {
        0x00: Sequence,
        0x01: Text,
        0x02: Copyright,
        0x03: TrackName,
        0x04: InstrumentName,
        0x05: Lyrics,
        0x06: Marker,
        0x07: CuePoint,
        
        0x20: Channel,
        0x2F: EndOfTrack,

        0x51: Tempo,
        0x54: SMPTEOffset,
        0x58: TimeSignature,
        0x59: KeySignature,
        0x7F: SequencerSpecific,
    }

    def __init__(self, t, message_type, data):
        self.time = t    
        self.message_type = message_type
        self.data = data

        self.event = self.classes.get(self.message_type, lambda a, b: None)(self.time, self.data)
    
class SysExEvent:
    
    class SysEx:
        def __init__(self, t, message_type, data):
            self.time = t
            self.message_type = message_type
            self.data = data
    
    classes = {
        0xF0: SysEx,
        0xF7: SysEx,
    }

    def __init__(self, t, message_type, data):
        self.time = t
        self.message_type = message_type
        self.data = data

        self.event = self.classes.get(self.message_type, lambda a, b, c: None)(self.time, self.message_type, self.data)


class Midi:
    __str__ = dictstr

    class InvalidChunk(Exception):
        pass

    class Chunk:
        __str__ = dictstr

        class HeadChunk:
            magic = 0x4D546864 # "MThd"
            __str__ = dictstr

            microseconds_per_minute = 60000000
            
            def setTempo(self, microseconds_per_beat):
                self.bpm = self.microseconds_per_minute / microseconds_per_beat
                self.ticks_per_second = self.ticks_per_beat * self.bpm / 60

            def __init__(self, contents):
                if len(contents) != 6:
                    raise Exception("Head chunk length not 6.")
                
                self.format_type, self.track_count, self.time_division = struct.unpack("!3H", contents)
                self.time_division_type = self.time_division & 0x8000
                self.time_division_value = self.time_division & 0x7fff
                
                if self.time_division_type == 0:
                    self.ticks_per_beat = self.time_division_value
                    self.setTempo(self.microseconds_per_minute / 120)
                else:
                    self.fps = self.time_division_value & 0x7f00
                    self.ticks_per_frame = self.time_division_value & 0x007f
                    self.ticks_per_second = self.fps * self.ticks_per_frame
                    
                #print str(self)
                
                if self.format_type != 1:
                    raise Exception("Only able to understand midi format 1, not %i" % self.format_type)

        class TrackChunk:
            magic = 0x4D54726B # "MTrk"
            __str__ = dictstr

            class TrackData:
                __str__ = dictstr
                def __init__(self, data):
                    self.data = data
                    self.time = 0
                    self.pos = 0
                    self.last_pos = 0
                    self.last_event_data = 0
                    
                def unread(self):
                    self.pos = self.last_pos

                def readByte(self):
                    self.last_pos = self.pos
                    b = ord(self.data[self.pos])
                    self.pos += 1
                    return b
                    
                def readBytes(self, count):
                    self.last_pos = self.pos
                    s = self.data[self.pos:self.pos+count]
                    self.pos += count
                    return s
                    
                def readData(self):
                    self.last_pos = self.pos
                    s = ""
                    while True:
                        b = self.readByte()
                        if b & 0x80:
                            self.unread()
                            break
                        else:
                            s += chr(b)
                            
                    return s
                    
                def readVarInt(self):
                    #print repr(self.data[self.pos:4])
                    self.last_pos = self.pos
                    i = 0
                    start = self.pos
                    bytes = []
                    while ord(self.data[self.pos]) & 0x80:
                        #print ord(self.data[self.pos])
                        bytes.append(ord(self.data[self.pos]) & 0b01111111)
                        #i |= ord(self.data[self.pos]) << ((self.pos - start) * 7)
                        self.pos += 1
                    
                    #print ord(self.data[self.pos])
                    bytes.append(ord(self.data[self.pos]) & 0b01111111)
                    #i |= ord(self.data[self.pos]) << ((self.pos - start) * 7)
                    self.pos += 1
                    
                    shift = 0
                    #print bytes
                    for b in reversed(bytes):
                        i |= b << (shift * 7)
                        shift += 1
                    
                    #print "varint", i, self.pos - start
                    #print i
                    return i
                    
                    
                class Event:
                    __str__ = dictstr
                    def __init__(self, data):
                        self.begin = data.pos
                        self.data = data
                        
                        self.delta = self.data.readVarInt()
                        self.data.time += self.delta
                        self.time = self.data.time
                        
                        self.event_data = self.data.readByte()
                        if self.event_data & 0x80:
                            self.abridged = False
                            self.data.last_event_data = self.event_data
                        else:
                            self.abridged = True
                            self.event_data = self.data.last_event_data
                            self.data.unread()
                            
                        if self.event_data == 0xFF or self.event_data == 0xF7 or self.event_data == 0xF0:
                            self.meta_command = self.data.readByte()
                            self.field_len = self.data.readVarInt()
                            self.field_data = self.data.readBytes(self.field_len)
                            self.event_command = 0
                            self.event_channel = 0
                            self.arg1 = 0
                            self.arg2 = 0
                            if self.event_data == 0xFF:
                                self.event = MetaEvent(self.time, self.meta_command, self.field_data)
                            else:
                                self.event = SysExEvent(self.time, self.meta_command, self.field_data)
                        else:
                            self.meta_command = 0
                            self.field_len = 0
                            self.field_data = ""
                            self.event_command = (self.event_data & 0x7F) >> 4
                            self.event_channel = self.event_data & 0xF
                            self.arg1 = self.data.readByte()
                            if not (
                                (self.event_command | 0b1000) == 0xC
                             or (self.event_command | 0b1000) == 0xD
                            ):
                                self.arg2 = self.data.readByte()
                            else:
                                self.arg2 = None
                            self.event = ChannelEvent(self.time, self.event_command | 0b1000, self.event_channel, self.arg1, self.arg2)
                            
                        self.desc = dictstr(self.event)
                        #self.parameters = self.data.readData()
                        self.end = self.data.pos
                        try:
                            self.hex = h(self.data.data[self.begin:self.end])
                        except Exception as e:
                            import sys
                            print(e, self.begin, self.end, len(self.data.data))
                            sys.exit()
                        #print self.data.pos
                        
                        


            def generate_events(self, contents):
                td = Midi.Chunk.TrackChunk.TrackData(contents)
                try:
                    while True:
                        yield Midi.Chunk.TrackChunk.TrackData.Event(td)
                except IndexError:
                    # PEP 479: end of track data must not raise StopIteration
                    return
                        

            def __init__(self, contents):
                self.events = self.generate_events(contents)

        class UnknownChunk:
            magic = 0x0
            __str__ = dictstr

            def __init__(self, contents):
                pass



        def __init__(self, f):
            self.f = f
            import os
            self.head = f.read(8)
            if len(self.head) != 8:
                #print "Invalid chunk of len %i '%s'" % (len(self.head), self.head)
                raise StopIteration
                
            self.id = 0
            self.size = 0
            self.parse()
            
        def parse(self):
            self.id, self.size = struct.unpack("!2L", self.head)
            #print repr(self.head), self.id, self.size
            body = self.f.read(self.size)
            
            self.contents = {
                Midi.Chunk.HeadChunk.magic: Midi.Chunk.HeadChunk,
                Midi.Chunk.TrackChunk.magic: Midi.Chunk.TrackChunk,
            }.get(self.id, Midi.Chunk.UnknownChunk)(body)
            

    def __init__(self, filename):
        self.filename = filename
        self.f = open(filename, "rb")
        self.parse()
        
    def parse(self):
        self.chunks = self.parsechunks()
        self.tracks = []
        for chunk in self.chunks:
            if chunk.contents.magic is Midi.Chunk.HeadChunk.magic:
                self.head = chunk.contents
            elif chunk.contents.magic is Midi.Chunk.TrackChunk.magic:
                self.tracks.append(chunk)
        
    
    def parsechunks(self):
        while True:
            try:
                yield Midi.Chunk(self.f)
            except StopIteration:
                # PEP 479: StopIteration signaling EOF must not escape a generator
                return
            

class EventQueue:
    def __init__(self, start = 0, events = []):
        from itertools import count
        from heapq import heapify
        self.counter = count(1)
        self.q = [(time, next(self.counter), event) for time, event in events]
        heapify(self.q)
        self.t = start
        
    def empty(self):
        return not self.q
        
    def _pop_time(self):
        return self.q[0][0]

    def _pop(self):
        from heapq import heappop
        return heappop(self.q)

    def add_event(self, time, event):
        from heapq import heappush
        heappush(self.q, [time, next(self.counter), event])
        
    def produce_events_until(self, time):
        while not self.empty() and self._pop_time() <= time:
            yield self._pop()[2]

    def update_time(self, t = None):
        if t is None:
            self.t = self._pop_time()
        else:
            self.t = int(t)
        
    def next_time(self):
        return self._pop_time() if not self.empty() else None
        
    def produce_events(self):
        for event in self.produce_events_until(self.t):
            yield event
            
    def event_batch(self):
        return [event for event in self.produce_events()]


class Channels:
    def noop(self, a, b):
        pass
        #print "noop", a, b

    def ticks_per_second(self):
        return self.midi.head.ticks_per_second

    def remaining(self):
        return not self.q.empty()
            
    def updateTime(self, s):
        delta = s - self.s
        self.s = s
        self.t += delta * self.ticks_per_second()
        
        self.q.update_time(self.t)
    
        self.pullEnqueuedEvents()

    def pullEnqueuedEvents(self):
        self.updateEvents(self.q.event_batch())

    def onNotes(self):
        on = []
        for midi_channel in self.channels:
            for n in self.channels[midi_channel].notes:
                note = self.channels[midi_channel].notes[n]
                if note.off_time is None:
                    on.append(n)
                    
        return on

    def syncReleases(self):
        for midi_channel in self.channels:
            for n in self.channels[midi_channel].notes:
                note = self.channels[midi_channel].notes[n]
                note.syncRelease()

    def syncTunings(self):
        for midi_channel in self.channels:
            for n in self.channels[midi_channel].notes:
                note = self.channels[midi_channel].notes[n]
                if n in self.tunings:
                    note.updateTuning(self.sampler, self.tunings[n], self.s)

    def recenterFrequencies(self, pairs):
        # Gradual tonal-center correction for the dynamic tuner.
        from math import log
        if not pairs:
            return pairs

        def cents(ratio):
            return 1200.0 * log(ratio) / log(2.0)

        # Implied center: mean deviation from an equal grid on C = 256 Hz.
        drift = sum(
            cents(f / (256.0 * 2.0 ** (note / 12.0)))
            for note, f in pairs
        ) / len(pairs)

        # Follow the solution's center at a bounded rate, then leak toward
        # the grid; sustained notes move by at most FOLLOW + RECENTER cents
        # per event, which reads as a slow glide rather than a jump.
        delta = drift - self.tonal_center
        delta = max(-TUNING_FOLLOW_CENTS, min(TUNING_FOLLOW_CENTS, delta))
        self.tonal_center += delta
        leak = max(-TUNING_RECENTER_CENTS, min(TUNING_RECENTER_CENTS, self.tonal_center))
        self.tonal_center -= leak

        shift = 2.0 ** ((self.tonal_center - drift) / 1200.0)
        errlog("tonal center: drift %+.2fc, held at %+.2fc, shifting %+.2fc"
               % (drift, self.tonal_center, cents(shift)))
        return [(note, f * shift) for note, f in pairs]

    def tuneNotes(self):
        self.tunings = {}
        if self.on_notes:
            #print self.on_notes
            if tuner_class is Tuner:
                tuned = Tuner(self.last_tuning)
            else:
                tuned = tuner_class()
            for note in self.on_notes:
                tuned.addNote(note - middle_c)
                
            if not tuned.in_cache():
                tuned.tune(1000, 30000)
            pairs = tuned.noteFrequencies()
            if isinstance(tuned, Tuner):
                pairs = self.recenterFrequencies(pairs)
            self.last_tuning = pairs
            frequencies = dict(pairs)
                
            for note in frequencies:
                self.tunings[note + middle_c] = frequencies[note]
            
            self.syncTunings()
        #print self.tunings

    def postEvents(self):
        notes = sorted(self.onNotes())
        if self.on_notes != notes:
            self.on_notes = notes
            self.tuneNotes()
        #self.syncReleases()
        #print ", ".join(notename(n) for n in self.on_notes)
        

    def updateEvents(self, events):
        had_events = False
        for event in events:
            had_events = True
            self.updateEvent(event)
            
        if had_events:
            self.postEvents()

    def updateEvent(self, e):
        self.event_switch.get(e.__class__, self.noop)(self, e)

    def updateSysEx(Self, s):
        pass

    def setChannel(self, m):
        self.meta_channel = m.midi_channel

    def setTempo(self, m):
        self.tempo = m
        self.midi.head.setTempo(m.microseconds_per_beat)
        #print "ticks_per_second", self.midi.head.ticks_per_second
        
    def setKey(self, m):
        self.key_sign = m
       
    def setTime(self, m):
        self.time_sign = m

    meta_switch = {
        MetaEvent.Channel:       setChannel,
        MetaEvent.Tempo:         setTempo,
        MetaEvent.KeySignature:  setKey,
        MetaEvent.TimeSignature: setTime,
    }

    def noop(self, a, b):
        pass
        #print "noop", a, b

    def updateMeta(self, m):
        if m.event and m.event.channel_specific:
            self.updateChannelMeta(m.event)
        else:
            self.meta_switch.get(m.event.__class__, self.noop)(self, m.event)        
        
    def updateChannel(self, c):
        self.channels[c.event.midi_channel].update(c.event, self.s)
        
    def updateChannelMeta(self, m):
        self.channels[self.meta_channel].updateMeta(m)


    event_switch = {
        ChannelEvent: updateChannel,
        MetaEvent:    updateMeta,
        SysExEvent:   updateSysEx,
    }

    def __init__(self, filename, sampler):
        self.midi = Midi(filename)
        self.sampler = sampler
        #print self.midi
        
        self.s = 0.0
        self.t = 0.0
        
        self.on_notes = []
        self.last_tuning = None
        self.tonal_center = 0.0
        
        events = []
        for track in self.midi.tracks:
            events.extend([(event.event.time, event.event) for event in track.contents.events])
        self.q = EventQueue(0, events)
        
        self.meta_channel = 0;
        
        self.tempo = MetaEvent.Tempo()
        self.key_sign = MetaEvent.KeySignature()
        self.time_sign =  MetaEvent.TimeSignature()
        
        self.channels = dict(
            list(zip(
                list(range(0, 16)),
                [
                    Channel(sampler, midi_channel)
                    for midi_channel
                    in range(0, 16)
                ]
            ))
        )
        
        self.pullEnqueuedEvents()


class Note:
    def updateTuning(self, sampler, f, seconds):
        self.f = f
        self.tone.updateFrequency(self.f)

    def finished(self):
        return self.off_time is not None and self.tone and self.tone.finished()

    def cleanup(self):
        if self.tone:
            self.tone.remove()

    def release(self):
        self.off_time = self.event.time
        self.off_velocity = self.event.velocity
        if self.tone:
            self.tone.release()

    def unrelease(self):
        self.on_time = self.event.time
        self.on_velocity = self.event.velocity
        self.off_time = None
        self.off_velocity = 0
        if self.tone:
            self.tone.unrelease()

    def inc(self, n):
        self.ref_count += 1
        self.event = n
        self.unrelease()

    def dec(self, n):
        self.ref_count -= 1
        self.event = n
        self.release()

    def __init__(self, channel, f, n, pan, seconds):
        self.event = None
        self.channel = channel
        self.n = n
        
        self.f = 0
        self.pan = pan

        # Data-driven GM routing: every program maps to a physical-model
        # bucket in patch_map (0-based program numbers).
        property_class = property_class_for_program(self.channel.program)

        self.tone = self.channel.sampler.newTone(self.channel.midi_channel, f, self.pan, seconds, None, property_class)

        self.ref_count = 0
        
        self.on_time = None
        self.on_velocity = 0
        
        self.touch_time = None
        self.aftertouch = 0
        
        self.off_time = None
        self.off_velocity = 0

    def __str__(self):
        return str(self.__dict__)

class Channel:
    control_map = {
        0x0: "bank",
        0x1: "modulation",
        0x2: "breath",
        0x4: "foot",
        0x5: "portamento",
        0x7: "volume",
        0x8: "balance",
        0xA: "pan",
        0xB: "expression",
    }
    msb_mask = 0x00
    lsb_mask = 0x20
    
    toggle_map = {
        0x0: "damper",
        0x1: "portamento",
        0x2: "sostenudo",
        0x3: "soft",
        0x4: "legato",
        0x5: "hold",
    }
    toggle_mask = 0x40

    def attackNote(self, n, s):
        #print "attacking note", n.note, "on channel", self.midi_channel, "at", n.time, "with velocity", n.velocity

        if n.velocity == 0:
            return self.releaseNote(n, s)
        
        if n.note not in self.notes:
            e = Note(self, None, n.note, self.getControl("pan"), s)
            self.notes[n.note] = e
        else:
            e = self.notes[n.note]
            
        e.inc(n)
            #errlog("attackNote ref_count %i, %i" % (e.ref_count, e.tone.partials[0].ref_count))
            
    
    def releaseNote(self, n, s):
        #print "releasing note", n.note, "on channel", self.midi_channel, "at", n.time, "with velocity", n.velocity
        
        if n.note in self.notes:
            e = self.notes[n.note]
            e.dec(n)
        else:
            errlog("PANIC !!! attempting to release a note already released")

            
    def updateNoteAftertouch(self, n, s):
        #print "pressing note", n.note, "on channel", self.midi_channel, "at", n.time, "with pressure", n.aftertouch
        
        if n.note in self.notes:
            e = self.notes[n.note]
            e.touch_time = n.time
            e.aftertouch = n.aftertouch
        #print str(self)
        

    def updateControl(self, c, s):
        if   c.control - self.lsb_mask in self.control_map:
            self.controls[self.control_map[c.control - self.lsb_mask]][1] = c.value
        elif c.control - self.msb_mask in self.control_map:
            self.controls[self.control_map[c.control - self.msb_mask]][0] = c.value
        elif c.control - self.toggle_mask in self.toggle_map:
            self.toggles[self.toggle_map[c.control - self.toggle_mask]] = c.value > 64 
            
        #print "channel", c.midi_channel, "control update:", str(c.__dict__), "\n", str(self)
        
    def updateProgram(self, c, s):
        self.program = c.program
        
    def updateAftertouch(self, c, s):
        self.aftertouch = c.pressure
        
    def bendPitch(self, c, s):
        self.controls["pitch"] = (c.msb, c.lsb)
        
    switch = {
        ChannelEvent.NoteOn: attackNote,
        ChannelEvent.NoteOff: releaseNote,
        ChannelEvent.NoteAftertouch: updateNoteAftertouch,
        
        ChannelEvent.Controller: updateControl,
        ChannelEvent.ProgramChange: updateProgram,
        ChannelEvent.ChannelAftertouch: updateAftertouch,
        ChannelEvent.PitchBend: bendPitch,
    }

    def update(self, c, s):
        self.cleanup_notes(c.time)
        self.switch[c.__class__](self, c, s)
        
    def cleanup_notes(self, t):
        #return
        #print "cleaning up at", t
        to_remove = []
        for n in self.notes:
            note = self.notes[n]
            """
            if not (note.off_time is None):
                #print "note %i is released" % n
                if t - note.off_time and note.tone is not None and note.tone.finished():
                """
            if note.finished():
                    #print "note %i is off" % n
                    note.cleanup()
                    to_remove.append(n)
                    
        for n in to_remove:
            del self.notes[n]
        
    signed_controls = set(["balance", "pan", "pitch",])
    def getControl(self, name):
        msb, lsb = self.controls[name]
        if name in self.signed_controls:
            return (float(lsb|(msb<<7)) / 8192) - 1
        else:
            return (float(lsb|(msb<<7)) / 16383)
        
    def getToggle(self, name):
        return self.toggles[name]

    def updateMeta(self, m):
        self.meta.append(m)

    def __str__(self):
        return "Channel %i state:\n\tMeta: %s\n\tInstrument: %s (%i)\n\tAftertouch: %i\n\tControls: \n\t\t%s\n\tToggles: \n\t\t%s\n\tNotes: \n\t\t%s\n\t" % (
            self.midi_channel,
            ", ".join(str(meta) for meta in self.meta),
            patches[self.program],
            self.program,
            self.aftertouch,
            "\n\t\t".join("%s: %s" % (name, str(self.getControl(name))) for name in self.controls),
            "\n\t\t".join("%s: %s" % (name, str(self.getToggle(name)))  for name in self.toggles),
            "\n\t\t".join("%s: %s" % (note, notename(self.notes[note].n))  for note in self.notes),
        )

    def __init__(self, sampler, midi_channel):
        self.sampler = sampler
        self.midi_channel = midi_channel
        self.notes = {}
        self.meta = []
        self.program = 0
        self.aftertouch = 0

        self.controls = {
                          # MSB  LSB
            "bank":       [0x00,0x00],
            "modulation": [0x00,0x00],
            "breath":     [0x00,0x00],
            "foot":       [0x00,0x00],
            "portamento": [0x00,0x00],
            "volume":     [0xA0,0x00],
            "balance":    [0x40,0x00],
            "pan":        [0x40,0x00],
            "expression": [0x00,0x00],
            
            "pitch":      [0x40,0x00],
        }
        
        self.toggles = {
            "damper":     False,
            "portamento": False,
            "sostenudo":  False,
            "soft":       False,
            "legato":     False,
            "hold":       False,
        }

