#!/usr/bin/env python3

from midilib import *
import midilib

class SampleProgress:
    def __init__(self, sample_rate, channel, second_width = 0.1):
        self.sample_rate = sample_rate
        self.second_width = second_width
        self.sample_pos = 0
        self.second_pos = 0.0
        self.channel = channel

    def inc(self):
        self.sample_pos += 1

        second_pos = float(self.sample_pos) / self.sample_rate
        if second_pos > self.second_pos + self.second_width:
            self.second_pos = int(second_pos / self.second_width) * self.second_width
            # Progress goes straight to stderr so it is visible even when
            # the errlog debug channel is quiet (see TUNING_VERBOSE).
            import sys
            sys.stderr.write("Generated %.1f seconds on channel %i.\n" % (self.second_pos, self.channel))
            sys.stderr.flush()

def perform(q, filename, sample_rate, sample_depth, sample_packing, channel, tuner = "stretch"):
    import random
    global sampler
    random.seed(a=0)

    midilib.set_tuner(tuner)
    p = SampleProgress(sample_rate, channel, 0.1)

    sampler = SynthSampler(channel, sample_rate, sample_depth, sample_packing)
    zero_sample = sampler.packing.pack(0)
    channels = Channels(filename, sampler)

    i = 0
    while True:
        channels.updateTime(float(i) / sample_rate)
        sample = sampler.sample(i)
        q.put(sample)
        p.inc()
        if not channels.remaining() and not sampler.remaining() and sample == zero_sample:
            break

        i += 1

    q.put(None)
    
    while True:
        q.put(zero_sample)
        p.inc()

if __name__ == '__main__':
    import sys

    args = sys.argv[1:]
    if len(args) < 2 or args[0] in ("-h", "--help"):
        sys.stderr.write(
            "usage: midi.py <input.mid> <output-base> [tuner]\n"
            "\n"
            "Renders <input.mid> to <output-base>.raw: headerless stereo audio,\n"
            "32-bit signed integer, 44100 Hz. Convert to WAV with:\n"
            "  sox -t raw -r 44100 -b 32 -c 2 -e signed-integer <output-base>.raw <output-base>.wav\n"
            "\n"
            "tuner selects the adaptive tuning temperament (default: stretch):\n"
            "  %s\n" % ", ".join(sorted(midilib.tuner_registry)))
        sys.exit(2)

    midifile = args[0]
    wavfile = args[1]
    tuner = args[2] if len(args) > 2 else "stretch"
    midilib.set_tuner(tuner)  # validate the name before spawning workers

    sample_rate = 44100
    #sample_rate = 8000
    #sample_rate = 96000
    #sample_depth = 16
    sample_depth = 32
    #sample_packing = "h"
    sample_packing = "i"

    from multiprocessing import Process, Queue
    from queue import Empty
    from collections import deque
    from midilib import errlog
    from struct import Struct

    # Bounded queues: a channel that finishes early pads with silence while
    # its sibling still renders; without a bound it floods memory doing so.
    left_q = Queue(maxsize=8192)
    right_q = Queue(maxsize=8192)

    left_process =  Process(target=perform, args=(left_q, midifile, sample_rate, sample_depth, sample_packing, 0, tuner))
    right_process = Process(target=perform, args=(right_q, midifile, sample_rate, sample_depth, sample_packing, 1, tuner))

    def q_get(q, process, channel):
        # Bail out if a render worker dies instead of blocking forever.
        while True:
            try:
                return q.get(timeout=5)
            except Empty:
                if not process.is_alive():
                    sys.stderr.write("Render worker for channel %i died; aborting.\n" % channel)
                    sys.exit(1)

    try:
        left_process.start()
        right_process.start()

        out = open(wavfile + ".raw", "wb")

        i = 0
        left_finished = False
        right_finished = False

        left, right = q_get(left_q, left_process, 0), q_get(right_q, right_process, 1)
        while not left_finished or not right_finished:
            if left is None:
                left_finished = True
                left = q_get(left_q, left_process, 0)

            if right is None:
                right_finished = True
                right = q_get(right_q, right_process, 1)

            out.write(left + right)
            if i % 8192 == 0:
                out.flush()
                errlog("i = %i" % i)

            i += 1
            left, right = q_get(left_q, left_process, 0), q_get(right_q, right_process, 1)

        errlog("%r" % ([left, right]))
        out.flush()
        errlog("i = %i" % i)
        out.close()
    except KeyboardInterrupt:
        left_process.terminate()
        right_process.terminate()
    finally:
        left_process.terminate()
        right_process.terminate()
        left_process.join()
        right_process.join()

