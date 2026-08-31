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
from patch_map import property_class_for_program, property_class_for_note
from percussion_map import percussion_for_note, GM_PERCUSSION_CHANNEL

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
    "meantone": MeantoneTuner,   # quarter-comma: pure 3rds, every 5th tempered, wolf G#-Eb
    "well": WellTuner,
    "linearwell": LinearWellTuner,
    "bechstein": BechsteinTuner,
    "dynamic": Tuner,
    # Experimental path.py tree generators (fixed full-keyboard tunings whose
    # octaves follow the Steinway-B inharmonicity to the 2nd partial).
    "hybrid": HybridTuner,
    # ...and the same temperament on PURE 2:1 octaves, for mode-locked pipes
    # (an organ has no sharp 2nd partial to chase, so a stretched octave beats).
    "hybridharm": HybridHarmonicTuner,
    "spiral": SpiralTuner,
    "semi": SemiTuner,
    "path": PathNotesTuner,
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

# One-pole time constant (seconds) for smoothing the live organ registration
# (swell CC7, drawn stops CC11, crescendo CC4) so coarse 7-bit steps don't
# zipper. ~15 ms reads as an instant but glitch-free stop change / swell.
from math import exp as _reg_exp
REG_SMOOTH_TAU = float(os.environ.get("REG_SMOOTH_TAU", "0.015"))

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
                # signed sharp/flat count; go through the ord shim (which
                # tolerates both bytes-as-int and str) rather than
                # struct.unpack, which requires a bytes-like object.
                key = ord(bytes[0])
                self.key = key - 256 if key > 127 else key
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

        # Advance the live organ registration (swell / drawn stops / crescendo)
        # toward its CC targets. Runs every sample; organ channels only.
        for channel in self.channels.values():
            channel.stepRegistration(delta)

    def pullEnqueuedEvents(self):
        self.updateEvents(self.q.event_batch())

    def onNotes(self):
        on = []
        for midi_channel in self.channels:
            if midi_channel == GM_PERCUSSION_CHANNEL:
                # Drums carry no pitch; keep them out of the tuning solve.
                continue
            for n, voices in self.channels[midi_channel].notes.items():
                if any(v.off_time is None for v in voices):
                    on.append(n)

        return on

    def syncReleases(self):
        for midi_channel in self.channels:
            for voices in self.channels[midi_channel].notes.values():
                for note in voices:
                    note.syncRelease()

    def syncTunings(self):
        for midi_channel in self.channels:
            if midi_channel == GM_PERCUSSION_CHANNEL:
                # Fixed-frequency drums; a colliding pitched note number on
                # another channel must not retune them.
                continue
            for n, voices in self.channels[midi_channel].notes.items():
                if n in self.tunings:
                    for note in voices:
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
            self.tuneNotes()          # re-solve the temperament and sync all voices
        elif any(v.tone is not None and v.tone.frequency is None
                 for ch in self.channels.values() for vs in ch.notes.values() for v in vs):
            # voice-per-note added a new same-pitch voice; give the fresh tone its
            # pitch/partials from the current tunings (the set didn't change).
            self.syncTunings()
        

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

        self.scanNoteDurations(events)

        self.pullEnqueuedEvents()

    def scanNoteDurations(self, events):
        """Pair note-ons with their note-offs to record each note's length in
        seconds (tracking tempo), so an attack can cap its onset fade to the
        note and fast notes still articulate. Stored per channel keyed by
        (note, on_tick)."""
        tpb = self.midi.head.ticks_per_beat
        if not tpb:
            return
        tempo = 500000.0  # microseconds per beat (120 bpm) until a Tempo event
        sec = 0.0
        last_tick = 0
        pending = {}  # (channel, note) -> [on_tick, on_sec] FIFO
        for tick, ev in sorted(events, key=lambda te: te[0]):
            sec += (tick - last_tick) / tpb * (tempo / 1e6)
            last_tick = tick
            inner = getattr(ev, "event", None)
            if isinstance(ev, MetaEvent):
                if isinstance(inner, MetaEvent.Tempo):
                    tempo = float(inner.microseconds_per_beat)
                continue
            if not isinstance(ev, ChannelEvent):
                continue
            cls = inner.__class__
            is_on = cls is ChannelEvent.NoteOn and inner.velocity > 0
            is_off = cls is ChannelEvent.NoteOff or (
                cls is ChannelEvent.NoteOn and inner.velocity == 0)
            if is_on:
                pending.setdefault((inner.midi_channel, inner.note), []).append((tick, sec))
            elif is_off:
                stack = pending.get((inner.midi_channel, inner.note))
                if stack:
                    on_tick, on_sec = stack.pop(0)
                    ch = self.channels.get(inner.midi_channel)
                    if ch is not None:
                        ch.note_durations[(inner.note, on_tick)] = sec - on_sec


class Note:
    def updateTuning(self, sampler, f, seconds):
        self.f = f
        self.tone.updateFrequency(self.f)

    def finished(self):
        if self.tone is None:
            # unmapped percussion note: nothing to play, retire immediately
            return True
        return self.off_time is not None and self.tone.finished()

    def cleanup(self):
        if self.tone:
            self.tone.remove()

    def release(self):
        self.off_time = self.event.time
        self.off_velocity = self.event.velocity
        # A one-shot voice (cymbal, struck percussion) ignores note-off and
        # rings out on its own decay; releasing it would impose an unnatural
        # linear fade cut. It still records off_time so cleanup can retire it
        # once the decay reaches the floor.
        if self.tone and not getattr(self.tone.property_class, "one_shot", False):
            self.tone.release()

    def unrelease(self):
        self.on_time = self.event.time
        self.on_velocity = self.event.velocity
        self.off_time = None
        self.off_velocity = 0
        if self.tone:
            self.tone.unrelease()

    def __init__(self, channel, f, n, pan, seconds, velocity=127):
        self.event = None
        self.channel = channel
        self.n = n
        
        self.f = 0
        self.pan = pan
        self.percussion = (self.channel.midi_channel == GM_PERCUSSION_CHANNEL)

        # MIDI amplitude standard (GM2 / DLS): velocity and the channel
        # Volume (CC7) x Expression (CC11) each scale amplitude as (v/127)^2.
        # Velocity is the per-note dynamic; CC7/CC11 are the channel/mix level.
        vol = min(1.0, self.channel.getControl("volume"))
        expr = min(1.0, self.channel.getControl("expression"))
        self.attack_volume = (velocity / 127.0) ** 2
        self.channel_volume = (vol * expr) ** 2

        # Shared note state (set before tone creation so both the pitched
        # and percussion paths, including early exits, have it).
        self.ref_count = 0
        self.on_time = None
        self.on_velocity = 0
        self.touch_time = None
        self.aftertouch = 0
        self.off_time = None
        self.off_velocity = 0

        if self.percussion:
            # Channel 10: the note number selects a drum, not a pitch. Give
            # it a fixed base frequency and drum timbre, and init the tone
            # now -- the tuner never sees these notes, so nothing else will.
            drum = percussion_for_note(n)
            if drum is None:
                self.tone = None
                return
            name, property_class, base_frequency, default_pan = drum
            self.f = base_frequency
            # Each drum has a default stereo position; the channel pan (CC10)
            # rotates the whole kit around it. Clamp to the legal pan range.
            drum_pan = max(-1.0, min(1.0, self.pan + default_pan))
            self.tone = self.channel.sampler.newTone(
                self.channel.midi_channel, base_frequency, drum_pan, seconds, None, property_class,
                self.attack_volume, self.channel_volume)
            self.tone.updateFrequency(base_frequency)
            return

        # Data-driven GM routing: every program maps to a physical-model
        # bucket in patch_map (0-based program numbers).
        # per NOTE, so an ensemble patch routes to the instrument whose
        # register the note is in -- see patch_map.property_class_for_note
        property_class = property_class_for_note(self.channel.program, self.n)

        # Organ voices take their channel level from the LIVE swell (CC7), applied
        # per partial at render time (SynthTone.sum_values), not baked here -- so
        # pass a neutral channel volume and let RegState.swell shape held notes.
        # (CC11 is repurposed as the stop bitfield for these voices, so it must
        # not fold into the amplitude either.)
        channel_volume = 1.0 if getattr(property_class, 'registerable', False) else self.channel_volume

        self.tone = self.channel.sampler.newTone(self.channel.midi_channel, f, self.pan, seconds, None,
                                                 property_class, self.attack_volume, channel_volume)

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
        if n.velocity == 0:
            return self.releaseNote(n, s)

        # Voice-per-note (what good samplers do): every note-on gets its own
        # independent Note/tone, kept in a per-pitch FIFO list. Overlapping
        # same-pitch notes each ring in full; a later note-off retires the
        # oldest still-sounding one (see releaseNote), so a stop that lands past
        # the next note's start retires the old voice instead of cutting the new.
        e = Note(self, None, n.note, self.getControl("pan"), s, n.velocity)
        e.event = n
        e.unrelease()   # strike this voice
        self.notes.setdefault(n.note, []).append(e)

        # Cap this articulation's onset fade to a fraction of the note's
        # length so short notes (trills, tonguing, rolls) don't smear under
        # a long valve/breath fade. Percussion is exempt: a struck drum rings
        # out on its own decay regardless of how briefly the key is held.
        if not e.percussion:
            duration = self.note_durations.get((n.note, n.time))
            if duration is not None and e.tone is not None:
                e.tone.set_max_fade(0.45 * duration)
            
    
    def releaseNote(self, n, s):
        # FIFO off-matching: retire the OLDEST voice of this pitch still
        # sounding. If none is unreleased, the note-off is stale (its voice was
        # already retired) -- swallow it rather than cut a live voice.
        for e in self.notes.get(n.note, ()):
            if e.off_time is None:
                e.event = n
                e.release()
                return
        errlog("PANIC !!! attempting to release a note already released")

            
    def updateNoteAftertouch(self, n, s):
        #print "pressing note", n.note, "on channel", self.midi_channel, "at", n.time, "with pressure", n.aftertouch
        
        for e in self.notes.get(n.note, ()):
            if e.off_time is None:
                e.touch_time = n.time
                e.aftertouch = n.aftertouch
        

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
        # Selecting an organ voice defaults its registration to the 8' Principal
        # (bit 0 of the CC11 stop bitfield). Expression otherwise defaults to full
        # (0x7F) -- which as a bitmask would draw every stop -- so reset it here so
        # an organ MIDI with no stop automation sounds as today's single 8' rank.
        if getattr(property_class_for_program(self.program), 'registerable', False):
            self.controls["expression"] = [0x01, 0x00]   # MSB=1 -> stop mask bit0 (8')

    def stepRegistration(self, dt):
        """Step this channel's live RegState toward its CC targets (organ voices
        only). swell <- CC7; the per-rank gate <- max(CC11 stop bitfield, CC4
        crescendo draw). One-pole smoothed so 7-bit steps don't zipper."""
        prop = property_class_for_program(self.program)
        if not getattr(prop, 'registerable', False):
            return
        ranks = prop.stop_ranks
        order = getattr(prop, 'crescendo_order', [r[0] for r in ranks])

        st = self.sampler.reg_state_for(self.midi_channel)
        swell_target = min(1.0, max(0.0, self.getControl("volume")))       # CC7
        mask = self.controls["expression"][0] | (self.controls["expression"][1] << 7)  # CC11 low7 | CC43 high
        cres = min(1.0, max(0.0, self.getControl("foot")))                # CC4 crescendo pedal
        ndrawn = int(cres * len(order) + 1e-9)                            # stops the pedal has rolled in
        drawn_by_cres = set(order[:ndrawn])

        targets = {}
        for i, r in enumerate(ranks):
            key = r[0]; bit = 1.0 if (mask >> i) & 1 else 0.0
            targets[key] = 1.0 if (bit or key in drawn_by_cres) else 0.0

        k = 1.0 - _reg_exp(-dt / REG_SMOOTH_TAU) if dt > 0.0 else 1.0
        st.swell += (swell_target - st.swell) * k
        gate = st.gate
        for key, target in targets.items():
            cur = gate.get(key, 0.0)
            gate[key] = cur + (target - cur) * k

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
        # Retire finished voices per pitch; drop pitches whose list empties.
        empty = []
        for pitch, voices in list(self.notes.items()):
            live = []
            for note in voices:
                if note.finished():
                    note.cleanup()
                else:
                    live.append(note)
            if live:
                self.notes[pitch] = live
            else:
                empty.append(pitch)
        for pitch in empty:
            del self.notes[pitch]
        
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
            "\n\t\t".join("%s: %s" % (note, ", ".join(notename(v.n) for v in self.notes[note])) for note in self.notes),
        )

    def __init__(self, sampler, midi_channel):
        self.sampler = sampler
        self.midi_channel = midi_channel
        self.notes = {}
        self.meta = []
        self.program = 0
        self.aftertouch = 0
        # (note, on_tick) -> duration in seconds, filled by a load-time scan
        # so attacks can cap their onset fade to the note length.
        self.note_durations = {}

        self.controls = {
                          # MSB  LSB
            "bank":       [0x00,0x00],
            "modulation": [0x00,0x00],
            "breath":     [0x00,0x00],
            "foot":       [0x00,0x00],
            "portamento": [0x00,0x00],
            "volume":     [0x7F,0x7F],   # CC7 default full (GM100 is a convention; full = no attenuation)
            "balance":    [0x40,0x00],
            "pan":        [0x40,0x00],
            "expression": [0x7F,0x7F],   # CC11 default full: unset expression must not silence the note
            
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

