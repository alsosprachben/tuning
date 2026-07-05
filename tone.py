#!/usr/bin/env python

"""
Copyright Ben Woolley 2010.
All rights reserved.
"""

from tonelib import *


class Pyth:
    r1 = 1.0
    r2 = 4.0 / 3
    r3 = 5.0 / 7

    note_a = 1.0 / 1
    note_d = 4.0 / 3
    note_f = 5.0 / 7

    up1 = 1.0 / 1
    up2 = 2.0 / 1
    up3 = 3.0 / 2
    up4 = 4.0 / 3
    up5 = 5.0 / 4
    up6 = 6.0 / 5

    down1 = 1.0 / 1
    down2 = 1.0 / 2
    down3 = 2.0 / 3
    down4 = 3.0 / 4
    down5 = 4.0 / 5
    down6 = 5.0 / 6

    bass = 1.0 / 2 / 2 / 2

    h1 = 2.0 / 2
    h2 = 3.0 / 2
    h3 = 5.0 / 2
    h4 = 12.0 / 2


class BassPartial(BasePartial):
    nps = 3

    def __init__(self, f, v=1.0, db=0.0):
        BasePartial.__init__(self, v, db)
        self.base_frequency = f

    def frequency(self, second):
        self.attack_second.set(second - (second % (1.0 / self.nps)))
        self.release_second.set(second - (second % (1.0 / self.nps)) + (0.90 / self.nps))

        omode = int(second * 4) % 2
        bmode = int(second * 2) % 6
        if omode == 0:
            o = 1.0
        else:
            o = 2.0

        if bmode == 2:
            b = 4.0 / 3
            if o == 2.0:
                o = 5.0 / 3
        elif bmode == 3:
            b = 3.0 / 2
            if o == 2.0:
                o = 7.0 / 4
        elif bmode == 4:
            b = 3.0 / 2
        elif bmode == 5:
            b = 3.0 / 4
        else:
            b = 1.0
        return self.base_frequency * o * b


class WeirdPartial(BasePartial):
    nps = 4

    def __init__(self, f, v=1.0, db=0.0):
        BasePartial.__init__(self, v, db)
        self.base_frequency = f

    def frequency(self, second):
        self.attack_second.set(second - (second % (1.0 / self.nps)))
        self.release_second.set(second - (second % (1.0 / self.nps)) + (0.90 / self.nps))

        omode = int(second * 4) % 2
        if omode == 0:
            o = 3.0 / 2
        else:
            o = 1.0

        mode = int(second * 9) % 3
        if mode == 0:
            top = 2
            bottom = 1
        if mode == 1:
            top = 3.0 / 2
            bottom = 3.0 / 2
        elif mode == 2:
            top = 1
            bottom = 2

        return self.base_frequency * (float(int((second % 3) * 9 + top)) / int((second % 3) * 9 + bottom)) * o * 2 ** (
                (second) / 3)


class WeirdToneLeft(BaseTone, BaseSampler):
    def __init__(self, rate, depth, packing, frequency, v=1.0, db=0):
        BaseSampler.__init__(self, rate, depth, packing)

        partial_count = 20
        volume = v / partial_count
        self.partials = [
            WeirdPartial(frequency * Pyth.up1 * Pyth.h1, volume, db * Pyth.h1),
            # WeirdPartial(frequency * Pyth.up1 * Pyth.h2, volume, db * Pyth.h2),
            WeirdPartial(frequency * Pyth.up1 * Pyth.h3, volume, db * Pyth.h3),
            # WeirdPartial(frequency * Pyth.up1 * Pyth.h4, volume, db * Pyth.h4),

            WeirdPartial(frequency * Pyth.down4 * Pyth.h1, volume, db * Pyth.h1),
            # WeirdPartial(frequency * Pyth.down4 * Pyth.h2, volume, db * Pyth.h2),
            WeirdPartial(frequency * Pyth.down4 * Pyth.h3, volume, db * Pyth.h3),
            # WeirdPartial(frequency * Pyth.down4 * Pyth.h4, volume, db * Pyth.h4),

            WeirdPartial(frequency * Pyth.up5 * Pyth.h1, volume, db * Pyth.h1),
            # WeirdPartial(frequency * Pyth.up5 * Pyth.h2, volume, db * Pyth.h2),
            WeirdPartial(frequency * Pyth.up5 * Pyth.h3, volume, db * Pyth.h3),
            # WeirdPartial(frequency * Pyth.up5 * Pyth.h4, volume, db * Pyth.h4),

            BassPartial(frequency * Pyth.bass * 1, volume * 1, db * 1),
            BassPartial(frequency * Pyth.bass * 3, volume * 2, db * 2),
            BassPartial(frequency * Pyth.bass * 5, volume * 1, db * 3),
            BassPartial(frequency * Pyth.bass * 7, volume * 2, db * 4),
            BassPartial(frequency * Pyth.bass * 9, volume * 1, db * 5),
            BassPartial(frequency * Pyth.bass * 11, volume * 2, db * 6),
            BassPartial(frequency * Pyth.bass * 13, volume * 1, db * 7),
            BassPartial(frequency * Pyth.bass * 15, volume * 2, db * 8),
        ]


class WeirdToneRight(BaseTone, BaseSampler):
    def __init__(self, rate, depth, packing, frequency, v=1.0, db=0):
        BaseSampler.__init__(self, rate, depth, packing)

        partial_count = 20
        volume = v / partial_count
        self.partials = [
            # WeirdPartial(frequency * Pyth.up1 * Pyth.h1, volume, db * Pyth.h1),
            WeirdPartial(frequency * Pyth.up1 * Pyth.h2, volume, db * Pyth.h2),
            # WeirdPartial(frequency * Pyth.up1 * Pyth.h3, volume, db * Pyth.h3),
            WeirdPartial(frequency * Pyth.up1 * Pyth.h4, volume, db * Pyth.h4),

            # WeirdPartial(frequency * Pyth.down4 * Pyth.h1, volume, db * Pyth.h1),
            WeirdPartial(frequency * Pyth.down4 * Pyth.h2, volume, db * Pyth.h2),
            # WeirdPartial(frequency * Pyth.down4 * Pyth.h3, volume, db * Pyth.h3),
            WeirdPartial(frequency * Pyth.down4 * Pyth.h4, volume, db * Pyth.h4),

            # WeirdPartial(frequency * Pyth.up5 * Pyth.h1, volume, db * Pyth.h1),
            WeirdPartial(frequency * Pyth.up5 * Pyth.h2, volume, db * Pyth.h2),
            # WeirdPartial(frequency * Pyth.up5 * Pyth.h3, volume, db * Pyth.h3),
            WeirdPartial(frequency * Pyth.up5 * Pyth.h4, volume, db * Pyth.h4),

            BassPartial(frequency * Pyth.bass * 1, volume * 2, db * 1),
            BassPartial(frequency * Pyth.bass * 3, volume * 1, db * 2),
            BassPartial(frequency * Pyth.bass * 5, volume * 2, db * 3),
            BassPartial(frequency * Pyth.bass * 7, volume * 1, db * 4),
            BassPartial(frequency * Pyth.bass * 9, volume * 2, db * 5),
            BassPartial(frequency * Pyth.bass * 11, volume * 1, db * 6),
            BassPartial(frequency * Pyth.bass * 13, volume * 2, db * 7),
            BassPartial(frequency * Pyth.bass * 15, volume * 1, db * 8),
        ]


import sys

sample_rate = int(sys.argv[1])
sample_depth = int(sys.argv[2])
sample_packing = sys.argv[3]
seconds = float(sys.argv[4])

left_channel = WeirdToneLeft(sample_rate, sample_depth, sample_packing, 300, 1.0, 3)
right_channel = WeirdToneRight(sample_rate, sample_depth, sample_packing, 300, 1.0, 3)

for i in range(0, int(sample_rate * seconds)):
    sys.stdout.write(left_channel.sample(i))
    sys.stdout.write(right_channel.sample(i))
