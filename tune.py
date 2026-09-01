#!/usr/bin/env pypy3

"""
Copyright Ben Woolley 2010.
All rights reserved.
"""

from tunelib import *
        
class SimpleArpeggio(SynthSampler):
    def __init__(self, rate, depth, packing, channel, tones, seconds):
        SynthSampler.__init__(self, 0, rate, depth, packing)

        start = 0.0
        for frequency in tones:
            print("freq: ", frequency)
            tone = self.newTone(6, frequency, 0.0, start, None, GrandPianoProperties)
            tone.updateFrequency(frequency)
            tone.unrelease()
            errlog(vars(tone))
            
            start += float(seconds) / 3 / len(tones)
        

"""        
chords = [
    (0, [0, 2, 3, 7, 11]), # Cm3M7s2
    (0, [0, 1, 5, 8, 12]), # c#M7sC
    (7, [0, 7, 16, 22]),   # Gm7
    (0, [0, 7, 16, 24]),   # C
]
"""

class SampleProgress:
    def __init__(self, sample_rate, channel, second_width = 0.1):
        self.sample_rate = sample_rate
        self.second_width = second_width
        self.sample_pos = 0
        self.second_pos = 0.0
        self.channel = channel
        
    def inc(self):
        self.sample_pos += 1
        #errlog(self.sample_pos)
        
        second_pos = float(self.sample_pos) / self.sample_rate
        if second_pos > self.second_pos + self.second_width:
            self.second_pos = int(second_pos / self.second_width) * self.second_width
            errlog("Generated %.1f seconds on channel %i." % (self.second_pos, self.channel))



def perform(q, tuner, chords, sample_rate, sample_depth, sample_packing, channel):

    p = SampleProgress(sample_rate, channel, 0.1)

    for bass, chord in chords:
        tuned = tuner()
        for note in chord:
            errlog(bass - 24 + note)
            tuned.addNote(bass - 24 + note)
        tuned.tune(1000, max_i)
                    
        errlog(tuned.noteFrequencies()) 
        
        channel_sampler  = SimpleArpeggio(sample_rate, sample_depth, sample_packing, channel, [f for n, f in tuned.noteFrequencies()], seconds - (1.0/32))
        
        for i in range(0, int(sample_rate * seconds)):
            channel_sample = channel_sampler.sample(i)
            #q.put((channel, channel_sample))
            q.put(channel_sample)
            p.inc()
            

if __name__ == '__main__':
    from multiprocessing import Process, Queue
    from collections import deque

    chords = [
        (0, [0, 12, 24, 36, 48]),
        (24, [0, 4, 7, 12, 16]),
        (24, [0, 2, 9, 14, 17]),
        (23, [0, 3, 8, 15, 18]),
        (24, [0, 4, 7, 12, 16]),
        
        (24, [0, 4, 9, 16, 21]),
        (24, [0, 2, 6, 9, 14]),
        (23, [0, 3, 8, 15, 20]),
        (23, [0, 1, 5, 8, 13]),
        
        (21, [0, 3, 7, 10, 15]),
        (14, [0, 7, 12, 16, 22]),
        (19, [0, 4, 7, 12, 16]),
        (19, [0, 3, 9, 12, 18]),
        
        (17, [0, 4, 9, 16, 21]),
        (17, [0, 3, 9, 12, 18]),
        (16, [0, 3, 8, 15, 20]),
        (16, [0, 1, 5, 8, 13]),
        
        (14, [0, 3, 7, 10, 15]),
        (7, [0, 7, 12, 16, 22]),
        (12, [0, 4, 7, 12, 16]),
        (12, [0, 7, 10, 12, 16]),
        
        (5, [0, 12, 16, 19, 23]),
        (6, [0, 6, 15, 18, 21]),
        (8, [0, 9, 15, 16, 18]),
        (7, [0, 10, 12, 16, 19]),
        
        (7, [0, 9, 12, 17, 21]),
        (7, [0, 7, 12, 17, 22]),
        (7, [0, 7, 12, 16, 22]),
        (7, [0, 8, 14, 17, 23]),
        
        (7, [0, 9, 12, 17, 24]),
        (7, [0, 7, 12, 17, 22]),
        (7, [0, 7, 12, 16, 22]),
        (0, [0, 12, 19, 22, 28]),
        
        (0, [0, 12, 14, 17, 21, 24, 29]),
        (0, [0, 11, 26, 28, 29, 31, 35, 38, 41]),
        (0, [0, 12, 16, 19, 24]),        
    ]

    import sys
    sample_rate    = int(sys.argv[1])   if len(sys.argv) > 1 else 48000
    sample_depth   = int(sys.argv[2])   if len(sys.argv) > 2 else 16 
    sample_packing = sys.argv[3]        if len(sys.argv) > 3 else 'h'
    seconds        = float(sys.argv[4]) if len(sys.argv) > 4 else 3
    tuning         = sys.argv[5]        if len(sys.argv) > 5 else "auto"

    max_i = 30000

    performance_tuner = {
        "auto": Tuner,
        "even": EvenTuner,
        "just": JustTuner,
        "well": WellTuner,
        "pyth": PythTuner,
        "bech": BechsteinTuner,
        "stretch": StretchTuner,
    }[tuning]

    #q = Queue()
    #left_d  = deque()
    #right_d = deque()
    left_q = Queue()
    right_q = Queue()

    left_process =  Process(target=perform, args=(left_q, performance_tuner, chords, sample_rate, sample_depth, sample_packing, 0))
    right_process = Process(target=perform, args=(right_q, performance_tuner, chords, sample_rate, sample_depth, sample_packing, 1))

    try:
        left_process.start()
        right_process.start()

        out = open(tuning + ".raw", "wb")

        for i in range(0, int(sample_rate * seconds * len(chords))):
            out.write(left_q.get() + right_q.get())
            if i % 1024 == 0:
                out.flush()
                errlog("i = %i" % i)
                    
        out.close()
    except KeyboardInterrupt:
        left_process.terminate()
        right_process.terminate()
    finally:
        left_process.join()
        right_process.join()
        
    

        


