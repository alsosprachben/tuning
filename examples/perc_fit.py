#!/usr/bin/env python3
"""Fit a struck hand-percussion voice (tonelib.MeasuredStrokeProperties) to
VSCO-2 Community Edition's recordings.

    python3 examples/perc_fit.py INST [--modes] [--scatter] [--model] [--fit [--maxfev=N]]

INST is one of INSTS below. REFS is ~/Documents/refs/vsco2 (sources.md):
VSCO-2 CE (Versilian Studios, CC0), stereo 44.1 kHz, the two channels summed
in power.

  --modes    the instrument's modes from its loudest strokes, 10-150 ms:
             every peak the highest within +-1.5%, within FLOOR dB of the
             strongest, in the instrument's band -- as (ratio to the note's
             pitch, dB re the strongest, amplitude dB/s read between two
             windows). The DRUM_MODES the class carries.
             (--group=NAME: from that group's strokes instead of the loudest)
  --scatter  how much two takes of one stroke differ, band by band (1/48
             octave, 3-16 kHz or the instrument's band), against the model's
             -- what mode_scatter_db is set from (the tambourine's lesson:
             strokes rendered alike read as one ringing thing)
  --model    the band-by-time grid, recorded against our render
  --fit      the decay, strike and noise, the band trim solved inside, and
             the modes' flatness in the instrument's band
  --write    with --fit: the result written into the class (write_fit)
  --attack   with --fit: the attack refit (ATTACK_REFIT), the onset's time free
  --trim3[=N]  N passes (3) refining the class's band_trim_db in third
             octaves, written into tonelib.py
  --env      10 ms envelope, recorded against the model
  --grain    noise or clicks: the shake's kurtosis and 1 ms spread, recorded,
             as a shaped noise would read, and the model
  --level    the level a refit is held at (velocity 100, loudest 150 ms),
             at the fit's note length and at 1.5 s

The grid is examples/crash_fit.py's, on windows sized to these (most are
40 dB down by 0.3-0.6 s). The files are trimmed close at both ends, so a
cell past a file's end reads -200 and weighs nothing; there is no clean
pre-onset silence to read a floor from.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import crash_fit as C  # noqa: E402
from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/vsco2")
_V1 = "VSCO 1 Percussion/"


def _vtag(p):
    m = re.search(r"_v(\d)_", os.path.basename(p))
    return int(m.group(1)) if m else 0


def _dyn(p):
    m = re.search(r"_(ppp|pp|p|mp|mf|f|ff|fff)[_.\d]", os.path.basename(p))
    return m.group(1) if m else ""


# A HAND DRUM'S NOISE IS ITS SLAP, NOT ITS HEAD. The head's modes ring clean
# (mode_jitter 0: jitter redraws a mode's phase nf * bandwidth times a second,
# and on a loud 216 Hz head that is ~24 clicks a second -- the open conga's
# first fit crackled 34 dB); the slap's partials, dense as the snare's wires
# (click_per_band 24), carry the noise, and the noise is judged where it
# lives, 1-8 kHz -- under 4 kHz the head's modes are all the flatness reads.
DRUM_PARAMS = ("slow_share", "slow_dbs", "click_cal_db", "click_dbs", "click_stroke_slope",
               "chiff_volume", "chiff_width", "chiff_bandwidth", "sustain_jitter")

# a rattle's own numbers in percussion_map. Not its one impact's decay or
# noise: rung ~8 ms (PERCUSSION_RING), an impact is over before they act --
# the cabasa's moved its render by 1e-3 of its peak -- so a rattle's colour is
# all in band_trim_db
RATTLE_PARAMS = ("@rattle_rate", "@impact_ring", "@rattle_fall", "@settle_s", "@settle_db", "@rise_s")
# a shake as shaped noise: its envelope, and the note length it was played at
SHAKE_PARAMS = ("rise_s", "settle_s", "settle_db", "@shake_s")

# THE ATTACK REFIT (--attack): the voices whose onset spiked where the takes
# build -- on the 1 ms step since the snare's onset rule, their top fell 10-25
# dB after the first 3 ms where the takes' rises (Ben: "some of the percussion
# ... seems to need the attack re-fitted"). The taiko's method: the attack
# judged by dynamic (contrast and early treble), the trims kept in the render,
# the onset's time free.
ATTACK_REFIT = ("agogo_hi", "agogo_lo", "conga_open", "conga_low", "bongo_hi", "bongo_lo")

# note, files, how they group into soft/mid/loud (None: one group), the
# modes' band and floor, the flatness band
# the SFX keys whose low body rings free (ring_scale), judged from 31 Hz: the
# guitar's cuts and the bass slap
LOW_RING = (48, 49, 50)
# ...and those that are a BURST OF NOISE, not a body (tonelib.ShakenNoiseProperties
# with a fixed length): a punch, a footstep, a bark, a hoof. As modes their
# click series rang half a second past takes gone in 30-150 ms -- unseen by the
# grid, whose windows past a take's end are not scored (Ben: "quite bad").
# Their envelope fitted here, their spectrum by --trim3
BURST = (54, 56, 76, 77)
BURST_PARAMS = ("rise_s", "settle_s", "settle_db", "shake_min_s")
_JAZZ = os.path.expanduser("~/Documents/refs/jazz_kit_soneproject/wav/")
_OCT31 = (31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
_JAZZ_T = ((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25), (0.25, 0.40))
INSTS = {
    "cowbell":   dict(note=56, glob="Percussion/Cowbell1_Hit_v*_Sum.wav",
                      groups=lambda p: {1: "soft", 2: "mid", 3: "mid", 4: "loud"}[_vtag(p)],
                      band=(300, 16000), floor=-30, flat=(1000, 12000),
                      # clean bell modes and a dense, noisy strike from 400 Hz, as
                      # the drums (DRUM_PARAMS), judged on the attack's contrast too
                      params=DRUM_PARAMS, contrast=True),
    "agogo_hi":  dict(note=67, glob=_V1 + "varMetal/various/agogoBell2_*.wav",
                      groups=lambda p: {"mp": "soft", "mf": "loud"}[_dyn(p)],
                      band=(500, 16000), floor=-30, flat=(1000, 12000)),
    "agogo_lo":  dict(note=68, glob=_V1 + "varMetal/various/agogoBell3_*.wav",
                      groups=lambda p: {"f": "soft", "ff": "loud"}[_dyn(p)],
                      band=(300, 16000), floor=-30, flat=(1000, 12000)),
    "conga_mute": dict(note=62, glob="Percussion/Quinto-Tap1_v*_Sum.wav", groups=None,
                       band=(150, 4000), floor=-25, flat=(1000, 8000),
                      params=DRUM_PARAMS),
    "conga_open": dict(note=63, glob="Percussion/Quinto-HitN_v*_Sum.wav",
                       groups=lambda p: {1: "soft", 2: "mid", 3: "loud"}[_vtag(p)],
                       band=(150, 4000), floor=-40, flat=(1000, 8000),
                       params=DRUM_PARAMS),
    "conga_low": dict(note=64, glob="Percussion/Conga-HitN_v*_Sum.wav",
                      groups=lambda p: {1: "soft", 2: "mid", 3: "loud"}[_vtag(p)],
                      band=(120, 4000), floor=-40, flat=(1000, 8000),
                      params=DRUM_PARAMS),
    "bongo_hi":  dict(note=60, glob=_V1 + "drums/other/Bongos/HighBongo*.wav", groups=None,
                      band=(120, 6000), floor=-25, flat=(1000, 8000),
                      params=DRUM_PARAMS),
    # the SINGLE strokes only: maraca1 and 4 are two strokes, 3 three quick hits
    # THE SHAKES ARE NOISE (tonelib.ShakenNoiseProperties; --grain): their
    # envelope is fitted here, their spectrum by --trim3 into noise_bands. A
    # shake lasts half its note, so the stroke's length is fitted as the note's
    # (@shake_s: the hold that makes it), the convention left alone.
    # the SINGLE strokes only: maraca1 and 4 are two strokes, 3 three quick hits
    "maracas":   dict(note=70, glob=_V1 + "varWood/maraca[25].wav", groups=None,
                      band=(1000, 16000), floor=-20, flat=(1000, 12000),
                      hold=0.228, params=SHAKE_PARAMS),
    # one twist each: cabasa_4 has two more bursts after its first, 5 is two
    # strokes. A twist swells in ~40 ms, scrapes ~150 ms and settles 40 dB in
    # 0.3 s
    "cabasa":    dict(note=69, glob=_V1 + "varMetal/various/cabasa_[1236].wav", groups=None,
                      band=(1000, 16000), floor=-20, flat=(1000, 12000),
                      hold=0.223, params=SHAKE_PARAMS),
    # a periodic train of pin strikes, 2.4-3.5 s whatever the note
    # (percussion_map.PERCUSSION_TRAIN): windows out to 2.4 s
    "vibraslap": dict(note=58, glob=_V1 + "varWood/vibraslap[0-9].wav", groups=None,
                      band=(300, 16000), floor=-20, flat=(1000, 12000), hold=0.25,
                      T=((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25),
                         (0.25, 0.50), (0.50, 1.00), (1.0, 1.6), (1.6, 2.4)),
                      # (the chiff stays white: narrowed to 0.04 of each partial it
                      # took 125-250 Hz, 40-60 dB down, from +10-17 dB to +-3, but
                      # lost the takes' flatness at 1-12 kHz, 0.34 -> 3.0 dB)
                      # @train_side(_slope): the far side of the swing dropping out
                      # (percussion_map.PERCUSSION_TRAIN, examples/vibraslap_swing.py)
                      # @noise_level, strike_noise_dbs: the pins' clatter as strike
                      # noise (the chiff off), its table refined by --trim3
                      trim_attr="strike_noise_db",
                      params=("decay_db", "harmonic_decay_db", "@noise_level", "strike_noise_dbs",
                              "@impact_ring", "@train_secs", "@train_fall", "@train_scatter",
                              "@train_strike", "@train_side", "@train_side_slope", "attack_time")),
    # Iowa's two mf scrapes (sources.md: iowa_guiro), 27 and 33 ridges over
    # 126 and 151 ms: the short guiro's one rip (PERCUSSION_RASP 73); the long
    # guiro is the same body and ridges. Its chiff was white, as the
    # vibraslap's was -- each ridge's noise spread to the bottom octaves.
    # @rasp_secs: the takes scrape at full level to ~170 ms, then the hand
    # deadens them (20 dB in ~30 ms); with the scrape held at 0.13 s the fit
    # rang each ridge 0.32 s to fill the gap, 9-17 dB long after it -- and
    # past the scrape, the takes' room and hiss at -67 to -80 dB, where ours
    # is silent: clipped at -60 (crash_fit.CLIP). The note is short (0.2 s)
    # so the scrape's own length governs
    "guiro":     dict(note=73, glob=os.path.expanduser("~/Documents/refs/iowa_guiro/guiro.*.mf.wav"),
                      groups=None, band=(500, 16000), floor=-25, flat=(1000, 12000), hold=0.2,
                      T=((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.100),
                         (0.100, 0.150), (0.150, 0.250), (0.25, 0.50)),
                      clip=-60.0, trim_attr="strike_noise_db",
                      # its noise as strike noise (@noise_level, strike_noise_dbs),
                      # the chiff off: see tonelib.GuiroProperties
                      params=("harmonic_decay_db", "@noise_level", "strike_noise_dbs",
                              "@impact_ring", "@rasp_secs", "attack_time")),
    # THE JAZZ SET (kit 32): soneproject's kit in a jazz bar (Freesound pack
    # 25895, CC0; sources.md: jazz_kit_soneproject), a Zoom H1 in the room --
    # so the takes' floor clipped (crash_fit.CLIP) and judged to 0.4 s. Its
    # files group by their suffix: the kick at two tunings (-6 ~70 Hz, -7 ~46),
    # the snare bright (-4/-5/-6) and dark (-9: its 174 Hz mode on top, the
    # wires 7-8 dB further down). The clipped takes left out (exclude)
    "jazz_kick1": dict(kit=32, exclude=('kick1fg-6', 'kick21a-6'), merge=0.12, max_modes=12, note=36, glob=_JAZZ + "kick*6.wav", groups=None,
                       band=(40, 3000), floor=-35, flat=(500, 4000), edges=_OCT31, T=_JAZZ_T, clip=-60.0,
                       params=DRUM_PARAMS),
    "jazz_kick2": dict(kit=32, exclude=('kick2bg-7', 'kick2ea7'), merge=0.12, max_modes=12, note=35, glob=_JAZZ + "kick*7.wav", groups=None,
                       band=(30, 3000), floor=-35, flat=(500, 4000), edges=_OCT31, T=_JAZZ_T, clip=-60.0,
                       params=DRUM_PARAMS),
    "jazz_snare1": dict(kit=32, exclude=('snare14g5',), merge=0.04, max_modes=16, note=38, glob=_JAZZ + "snare*[456].wav", groups=None,
                        band=(120, 6000), floor=-30, flat=(1000, 12000), T=_JAZZ_T, clip=-60.0,
                        params=DRUM_PARAMS),
    "jazz_snare2": dict(kit=32, merge=0.04, max_modes=16, note=40, glob=_JAZZ + "snare4*9.wav", groups=None,
                        band=(120, 6000), floor=-30, flat=(1000, 12000), T=_JAZZ_T, clip=-60.0,
                        params=DRUM_PARAMS),
    # ...its two toms (the SC-8850's Jazz toms), struck with sticks: the low
    # ~101 Hz (tom1c-f -6, tom7a-d), the rack ~162 Hz (tom20-23 -6, tom70-72);
    # the short bright -9 and tom4x takes (rim or brush) left out, and the
    # clipped tom21a-6
    "jazz_tom_low": dict(kit=32, merge=0.04, max_modes=10, note=43, glob=_JAZZ + "tom[17][a-f]*.wav", groups=None,
                         band=(60, 3000), floor=-35, flat=(500, 4000), T=_JAZZ_T, clip=-60.0,
                         params=DRUM_PARAMS),
    "jazz_tom_high": dict(kit=32, exclude=('tom21a-6',), merge=0.04, max_modes=10, note=47,
                          glob=_JAZZ + "tom[27][0-3]*.wav", groups=None,
                          band=(100, 4000), floor=-35, flat=(500, 4000), T=_JAZZ_T, clip=-60.0,
                          params=DRUM_PARAMS),
    # GS key 82, Shaker: Camo's shaker in VSCO 2 CE, eight single shakes of
    # 0.16-0.27 s (CC0), shaped noise as the maracas and cabasa (SHAKE_PARAMS,
    # then --trim3 into its noise_bands)
    "shaker":    dict(note=82, glob=_V1 + "varWood/Camo's Shaker/shake*.wav", groups=None,
                      band=(1000, 16000), floor=-20, flat=(1000, 12000),
                      hold=0.3, params=SHAKE_PARAMS),
    "bongo_lo":  dict(note=61, glob=_V1 + "drums/other/Bongos/LowBongo*.wav", groups=None,
                      band=(120, 6000), floor=-25, flat=(1000, 8000),
                      params=DRUM_PARAMS),
    # hello_flowers' timbales (freesound 41196, CC0), one hit a file as
    # examples/freesound_slice.py cut them: the free strokes, the player's
    # own mix of centre and edge. A metal shell, one head, sticks: the ring
    # reaches to ~4 kHz, so the modes are read to 6
    "timbale_hi": dict(note=65, glob=os.path.expanduser("~/Documents/refs/freesound/timbales/hits/high_*.wav"),
                       groups=None, band=(150, 6000), floor=-30, flat=(1000, 8000),
                       params=DRUM_PARAMS),
    # ring_scale free on the low drum: Ben, "slightly more metallic than the
    # recording", and from 150 to 500 ms its 1 and 4 kHz rang 11 and 15 dB
    # long (examples/stroke_ab.py timbale_lo --bands)
    "timbale_lo": dict(note=66, glob=os.path.expanduser("~/Documents/refs/freesound/timbales/hits/low_*.wav"),
                       groups=None, band=(150, 6000), floor=-30, flat=(1000, 8000),
                       params=DRUM_PARAMS + ("ring_scale",)),
    # plotzki's samba surdo (freesound 36127, CC0), as freesound_slice.py
    # cut it: three open strokes, three muted. The grid's octaves from 31 Hz,
    # as the taiko's: the head is at 67 Hz. The open strokes are cut at the
    # next beat (0.55 s), and the take's other drum (~120 Hz) rings into
    # their last 150 ms: judged to 0.4 s. ring_scale free, as the taiko's:
    # held at the modes' own rates, 0.5-8 kHz rang 5-13 dB long from 60 to
    # 250 ms (9.0 dB)
    "surdo_open": dict(note=87, glob=os.path.expanduser("~/Documents/refs/freesound/surdo/hits/open_*.wav"),
                       groups=None, band=(40, 3000), floor=-35, flat=(500, 4000),
                       edges=(31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000),
                       T=((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25),
                          (0.25, 0.40)),
                       params=DRUM_PARAMS + ("ring_scale",)),
    # the muted stroke: the open drum's modes, the hand where it lands
    # (tonelib.SurdoMuteProperties). Fitted: the beater's strike -- held at
    # the open stroke's, 0.25-8 kHz read 10-25 dB over the takes in the first
    # 60 ms -- and the hand's slap. Judged through the hand, to 0.30 s
    "surdo_mute": dict(note=86, glob=os.path.expanduser("~/Documents/refs/freesound/surdo/hits/mute_*.wav"),
                       groups=None, band=(40, 3000), floor=-35, flat=(500, 4000),
                       edges=(31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000),
                       T=((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.20),
                          (0.20, 0.26), (0.26, 0.30)),
                       # LEVELS ONLY. With the rates free too, the fit held the
                       # beater ringing (20 dB/s) and the slap undying (1e-5) to
                       # fill the take's remainder under the hand, which the
                       # gate's release, ending in silence, cannot: the slap's
                       # rate is read off the take (350 dB/s), the beater's is
                       # the open stroke's
                       flat_weight=0.0, params=("click_cal_db", "attack_time", "strike_noise_cal_db")),
    # GM 116, a PROGRAM: VSCO's "giant ethnic" drum struck with sticks, as a
    # taiko is with bachi -- a barrel drum at 65.9 Hz, ringing 0.3-0.6 s to
    # -40 dB, its loud strokes leaning on modes at 109 and 131 Hz. Fitted at
    # note 36 (C2, 65.4 Hz), the nearest; the class carries its modes as
    # ratios, so every note is this drum retuned. Ten strokes, ppp to fff.
    "taiko":     dict(program=116, note=36, f0=65.9,
                      glob=_V1 + "drums/other/ethnic/giant/sticks/EthnicLargeSticks_hit_*.wav",
                      groups=lambda p: {"ppp": "soft", "pp": "soft", "p": "soft", "mp": "mid", "mf": "mid",
                                        "f": "loud", "fff": "loud"}[_dyn(p)],
                      # flatness where a stick stroke still speaks: over 1-8 kHz
                      # the pp-ppp takes are their own noise floor (0.34)
                      band=(40, 4000), floor=-35, flat=(500, 4000),
                      # the grid's octaves from 31 Hz: from 125 it never saw the
                      # drum, whose fundamental and strike modes lie at 66-131
                      edges=(31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000),
                      # THE FIRST 250 ms ONLY, and the strike and the modes' rates
                      # HELD: judged to 0.9 s, the fit rang the strike's noise
                      # 0.4 s (click_dbs 73-87) and sped the modes (ring_scale
                      # 1.41) to imitate the takes' late energy -- their ROOM,
                      # 0.8-4 kHz holding 7 dB under its early level in every
                      # band -- and dry, that is a trash can (Ben). The hall is
                      # ours to add; the strike dies as a stick's does.
                      T=((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25)),
                      # ring_scale free: the modes' own rates, read through a
                      # +-1.5% band, ring half as fast as the bands they sit in
                      # fall (250-500 Hz: 110-150 dB/s against ~220)
                      # NO FLATNESS TERM: the takes read 0.10, 0.016 and 0.08 at
                      # soft, mid and loud -- their noise, not the drum's -- and
                      # chasing it held the strike ringing (click_dbs 71) and the
                      # trims at +-30 dB
                      flat_weight=0.0,
                      # THE ATTACK, judged (Ben: "a little bit of a click on the
                      # attack that is not on the recording ... the tap a little
                      # softer"): the top fell 32 dB from the first 3 ms where
                      # the takes fall 0.7, the first 5 ms' treble -14 dB re the
                      # body against -40 -- so the contrast term on, and the
                      # onset's time free (it was the class's 1 ms)
                      contrast=True, attack_groups=True,
                      # the trims kept in the render: solved on paper, they boosted
                      # the low modes 30 dB AFTER the fit had judged the attack
                      # without them -- and that boost, switched on in 1 ms, is
                      # the click. The onset held at 6 ms (the takes rise 10)
                      # the trims kept in the render, the attack judged on what plays
                      keep_trim=True,
                      params=tuple(k for k in DRUM_PARAMS if k != "click_dbs")),
    # THE SFX SET'S STRUCK SOUNDS (program 56 on the drum channel; SC-55
    # p.71), Freesound recordings (CC0; sources.md) cut one hit a file by
    # examples/freesound_slice.py sfx. Their keys are the SFX set's; the
    # sticks, slap and metronome play Standard's 28, 31, 33-34 as well
    **{name: dict(kit=56, note=note, glob=os.path.expanduser(
        "~/Documents/refs/freesound/%s/hits/%s_*.wav" % (folder, hit)),
        groups=None, band=band, floor=-30, flat=flat,
        # the guitar's cuts and the bass slap ring free (ring_scale): held at
        # the modes' own rates, their body's 65-100 Hz rang 0.6-0.8 s where the
        # takes are gone by 0.2-0.6 -- a tom (Ben: "seem like drums")
        params=(BURST_PARAMS if note in BURST else
                DRUM_PARAMS + (("ring_scale",) if note in LOW_RING else ())),
        # a burst's noise_bands fitted (--trim3) from its band's foot, a punch's
        # and a hoof's thud under 250 Hz
        trim_lo=band[0],
        # ...judged from 31 Hz, as the surdo is: from 125 the grid never saw
        # the body it was to damp (ring_scale stayed at 1)
        **({"edges": (31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)}
           if note in LOW_RING + BURST else {}))
       for name, note, folder, hit, band, flat in (
           ("sfx_slap", 40, "slap", "slap", (100, 8000), (500, 8000)),
           ("sfx_sticks", 43, "sticks", "sticks", (500, 16000), (1000, 16000)),
           ("sfx_metronome", 45, "../metronome_ben", "metronome", (500, 16000), (1000, 16000)),
           # Ben's bell from 600 Hz: under it the take holds a video game in the
           # next room (220-480 Hz), which the trim fitted as bell (+43 dB at 566)
           ("sfx_bell", 46, "../metronome_ben", "bell", (600, 16000), (1000, 16000)),
           ("sfx_cutdown", 48, "guitarcut", "cutdown", (100, 8000), (500, 8000)),
           ("sfx_cutup", 49, "guitarcut", "cutup", (100, 8000), (500, 8000)),
           ("sfx_bassslap", 50, "bassslap", "bassslap", (40, 4000), (500, 8000)),
           ("sfx_keyclick", 51, "keyclick", "keyclick", (200, 8000), (500, 8000)),
           ("sfx_door", 60, "door", "door", (40, 4000), (500, 8000)),
           ("sfx_chime", 62, "windchime", "chime", (300, 16000), (1000, 16000)),
           # the human and animal keys'
           ("sfx_punch", 54, "punch", "punch", (40, 4000), (500, 8000)),
           ("sfx_footstep", 56, "footsteps", "footstep", (100, 8000), (500, 8000)),
           ("sfx_bark", 76, "dog", "bark", (200, 8000), (500, 8000)),
           ("sfx_hoof", 77, "horse", "hoof", (100, 8000), (500, 8000)))},
}

C.EDGES = (125, 250, 500, 1000, 2000, 4000, 8000, 16000)
C.T = ((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25),
       (0.25, 0.40), (0.40, 0.70))
C.CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(C.EDGES[:-1], C.EDGES[1:]))
C.COL_W = np.array([0.3] + [1.0] * (len(C.T) - 1))
_render = C.render
HOLD = [1.0]
# A PROGRAM'S VOICE, not a drum note's (the taiko, GM 116): rendered on a
# melodic channel at the note nearest the recorded pitch -- PROG[0] is the
# program, None for a drum note
PROG = [None]


def _render_program(note, vel, secs):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=PROG[0], time=0))
    t.append(mido.Message("note_on", channel=0, note=note, velocity=vel, time=0))
    t.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return [np.asarray(L, np.float64), np.asarray(R, np.float64)], B.SR


C.render = lambda note, vel, secs=None: (_render_program if PROG[0] is not None else _render)(
    note, vel, HOLD[0] if secs is None else secs)


def inst_class(spec):
    """The class a fit adjusts: a drum note's, or the program's at its note."""
    import percussion_map as PM
    if "program" in spec:
        import patch_map
        return patch_map.property_class_for_note(spec["program"], spec["note"])
    if "kit" in spec:
        return PM.KITS[spec["kit"]][spec["note"]][1]
    return PM.PERCUSSION[spec["note"]][1]


def inst_f0(spec):
    import percussion_map as PM
    if "f0" in spec:
        return spec["f0"]
    return (PM.KITS[spec["kit"]] if "kit" in spec else PM.PERCUSSION)[spec["note"]][2]
C.PARAMS = ("slow_share", "slow_dbs", "click_cal_db", "click_dbs",
            "click_stroke_slope", "chiff_volume", "chiff_width", "chiff_bandwidth",
            "mode_jitter", "sustain_jitter")
C.FLOOR = {"slow_share": 0.005, "click_stroke_slope": 0.05, "click_cal_db": 1.0}
# where a class leaves a fitted knob at None (the module's default): a white
# chiff's bandwidth starts narrow; an attack starts at the valve time a None
# takes (tonelib: chiff_max_valve_time, 4 ms); a chiff's width, 10 ms
C.START = {"chiff_bandwidth": 0.05, "attack_time": 0.004, "chiff_width": 0.01}


def files(inst):
    # ...less the takes a spec excludes (clipped ones: their harmonics are the
    # converter's, and a fit chases them)
    ex = INSTS[inst].get("exclude", ())
    return sorted(p for p in glob.glob(os.path.join(REFS, INSTS[inst]["glob"]))
                  if os.path.basename(p)[:-4] not in ex)


def load(p):
    a, sr = read(p)
    a = np.pad(a.astype(np.float64), ((0, sr), (0, 0)))
    return [a[:, 0], a[:, 1]], sr


def strokes(inst):
    g = INSTS[inst]["groups"]
    out = []
    for p in files(inst):
        chs, sr = load(p)
        out.append(("all" if g is None else g(p), C.level(chs, sr), C.grid(chs, sr), p))
    return out


def grouped(ss):
    names = [g for g in C.GROUPS if any(s[0] == g for s in ss)] or ["all"]
    top = max(np.mean([s[1] for s in ss if s[0] == g]) for g in names)
    out = {}
    for g in names:
        rr = [s for s in ss if s[0] == g]
        gs = np.array([s[2] - s[2].max() for s in rr])
        m = np.where((gs < -100).any(0), -200.0, gs.mean(0))
        out[g] = (float(np.mean([s[1] for s in rr])) - top, m, [s[3] for s in rr])
    return out


GROUP = [None]       # --group=NAME: read the modes off that group, not the loudest


def modes(inst, f0):
    spec = INSTS[inst]
    lo, hi = spec["band"]
    ss = strokes(inst)
    gs = grouped(ss)
    loud = gs[GROUP[0] or list(gs)[-1]][2]
    win = ((0.01, 0.15), (0.02, 0.06), (0.10, 0.20))
    acc = [0.0, 0.0, 0.0]
    for p in loud:
        chs, sr = load(p)
        x = chs[0] + chs[1]
        t0 = C.onset([x], sr)
        for k, (a0, a1) in enumerate(win):
            seg = x[t0 + int(a0 * sr):t0 + int(a1 * sr)]
            acc[k] = acc[k] + np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)) ** 2 / len(seg)
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    A = 10 * np.log10(acc[0] + 1e-30)
    b = np.flatnonzero((f > lo) & (f < hi))
    pk = [i for i in b if A[i] >= A[(f > f[i] * 0.985) & (f < f[i] * 1.015)].max()]
    top = max(A[i] for i in pk)
    pk = [i for i in pk if A[i] > top + spec["floor"]]
    # NEAR-DUPLICATES, merged (spec "merge": a ratio): a mode smeared by the
    # stroke's glide, or a room's hump, reads as a run of peaks a percent
    # apart -- the jazz kick's 40-44 Hz came out as seven "modes" -- and two
    # steady copies of one mode beat. The strongest of each run is kept; then
    # the strongest max_modes
    mg = spec.get("merge")
    if mg:
        keep = []
        for i in sorted(pk, key=lambda i: -A[i]):
            if all(abs(f[i] / f[j] - 1.0) > mg for j in keep):
                keep.append(i)
        pk = sorted(keep[:spec.get("max_modes", len(keep))])
    out = []
    for i in pk:
        out.append((float(f[i] / f0), float(A[i] - top), mode_rate(loud, f[i])))
    return out


def mode_rate(paths, fm):
    """One mode's amplitude dB/s, read off its own envelope: band-passed
    +-1.5% around it, 5 ms RMS, the line through its first 35 dB down from
    its peak (from 10 ms, the strike's own crack out of the way), the median
    over the strokes. The two-window reading this replaces could not tell a
    mode's decay from its neighbour's, and the fit then scaled them all by
    one number -- the uniform ring that let the congas' highs hang on."""
    from scipy.signal import butter, sosfiltfilt
    rates = []
    for p in paths:
        chs, sr = load(p)
        x = chs[0] + chs[1]
        t0 = C.onset([x], sr)
        sos = butter(2, [fm * 0.985, fm * 1.015], btype="band", fs=sr, output="sos")
        y = sosfiltfilt(sos, x[t0:])
        n = int(0.005 * sr)
        e = np.sqrt(np.convolve(y * y, np.ones(n) / n, "valid")[::n])
        db = 20 * np.log10(e + 1e-12)
        t = np.arange(len(db)) * 0.005
        k0 = max(2, int(np.argmax(db[2:])) + 2)
        k1 = k0 + int(np.argmax(db[k0:] < db[k0] - 35.0)) if (db[k0:] < db[k0] - 35.0).any() else len(db)
        if k1 - k0 < 4:
            continue
        slope = np.polyfit(t[k0:k1], db[k0:k1], 1)[0]
        rates.append(-slope)
    return float(max(10.0, np.median(rates))) if rates else 40.0


def bands_db(x, sr, t0, lo, hi, a=0.01, b=0.10):
    seg = x[t0 + int(a * sr):t0 + int(b * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 15)) ** 2
    f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
    e = 2 ** np.arange(np.log2(lo), np.log2(hi), 1 / 48.0)
    return np.array([10 * np.log10(X[(f >= p) & (f < q)].sum() + 1e-30) for p, q in zip(e[:-1], e[1:])])


def stroke_diff(specs):
    S = [s - s.mean() for s in specs]
    return float(np.mean([np.std(S[i] - S[j]) for i in range(len(S)) for j in range(i + 1, len(S))]))


def scatter(inst):
    """Two takes of one stroke against each other, and four model strokes."""
    spec = INSTS[inst]
    lo, hi = spec["band"]
    by = {}
    for p in files(inst):
        key = re.sub(r"_rr\d|\d(?=\.wav$)|_\d(?=\.wav$)", "", os.path.basename(p))
        by.setdefault(key, []).append(p)
    rec = []
    for key, ps in by.items():
        if len(ps) > 1:
            sp = []
            for p in ps:
                chs, sr = load(p)
                x = chs[0] + chs[1]
                sp.append(bands_db(x, sr, C.onset([x], sr), lo, hi))
            rec.append(stroke_diff(sp))
    import mido
    import tempfile
    import blockrender as B
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    for k in range(4):
        ch = 0 if PROG[0] is not None else 9
        if k == 0 and PROG[0] is not None:
            t.append(mido.Message("program_change", channel=0, program=PROG[0], time=0))
        t.append(mido.Message("note_on", channel=ch, note=spec["note"], velocity=100, time=0 if k == 0 else 900))
        t.append(mido.Message("note_off", channel=ch, note=spec["note"], velocity=0, time=60))
    path = tempfile.mktemp(suffix=".mid")
    m.save(path)
    L, R = B.render(path)[:2]
    x = np.asarray(L, np.float64) + np.asarray(R, np.float64)
    step = B.SR
    sp = [bands_db(x, B.SR, C.onset([x[i:i + step]], B.SR) + i, lo, hi) for i in range(0, 4 * step, step)]
    return (float(np.mean(rec)) if rec else None), stroke_diff(sp)


def flatness(chs, sr, lo, hi):
    t0 = C.onset(chs, sr)
    x = sum(chs)
    seg = x[t0 + int(0.03 * sr):t0 + int(0.15 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 14)) ** 2
    f = np.fft.rfftfreq(1 << 14, 1.0 / sr)
    P = X[(f > lo) & (f < hi)] + 1e-30
    return float(np.exp(np.mean(np.log(P))) / np.mean(P))


_TRAIN_SLOT = {"@train_secs": 1, "@train_fall": 2, "@train_scatter": 4, "@train_strike": 5,
               "@train_side": 6, "@train_side_slope": 7}
_RATTLE_SLOT = {"@settle_s": 3, "@settle_db": 4, "@accent_s": 5, "@accent_db": 6, "@rise_s": 7, "@settle_thin": 8}


def _get(cls, note, k):
    import percussion_map as PM
    if k == "@shake_s":
        return HOLD[0] * cls.shake_frac
    if k == "@rattle_rate":
        span, n = PM.PERCUSSION_RATTLE[note][:2]
        return n / span
    if k == "@rasp_secs":
        return PM.PERCUSSION_RASP[note][0]
    if k == "@noise_level":
        return 10.0 ** (cls.strike_noise_cal_db / 20.0)
    if k == "@impact_ring":
        return PM.PERCUSSION_RING[note]
    if k == "@rattle_fall":
        r = PM.PERCUSSION_RATTLE[note]
        return r[2] if len(r) > 2 else 0.75
    if k in _TRAIN_SLOT:
        return PM.PERCUSSION_TRAIN[note][_TRAIN_SLOT[k]]
    if k in _RATTLE_SLOT:
        return PM.PERCUSSION_RATTLE[note][_RATTLE_SLOT[k]]
    return getattr(cls, k)


def _set(cls, note, k, v):
    """A class attribute, or one of the rattle's own numbers in the map
    (whose per-note ring classes are cached, so the cache goes)."""
    import percussion_map as PM
    if k == "@shake_s":
        HOLD[0] = float(v) / cls.shake_frac
    elif k == "@rattle_rate":
        span = PM.PERCUSSION_RATTLE[note][0]
        PM.PERCUSSION_RATTLE[note] = (span, max(2, int(round(v * span)))) + tuple(PM.PERCUSSION_RATTLE[note][2:])
    elif k == "@rattle_fall":
        r = list(PM.PERCUSSION_RATTLE[note])
        r[2] = min(0.99, float(v))
        PM.PERCUSSION_RATTLE[note] = tuple(r)
    elif k in _TRAIN_SLOT:
        r = list(PM.PERCUSSION_TRAIN[note])
        r[_TRAIN_SLOT[k]] = float(v)
        PM.PERCUSSION_TRAIN[note] = tuple(r)
    elif k in _RATTLE_SLOT:
        r = list(PM.PERCUSSION_RATTLE[note])
        r[_RATTLE_SLOT[k]] = float(v)
        PM.PERCUSSION_RATTLE[note] = tuple(r)
    elif k == "@noise_level":          # the strike's table moved, as a gain (dB can be < 0)
        cls.strike_noise_cal_db = 20.0 * np.log10(max(float(v), 1e-6))
    elif k == "@rasp_secs":            # the scrape longer, its ridges as dense
        secs, n = PM.PERCUSSION_RASP[note]
        PM.PERCUSSION_RASP[note] = (float(v), max(2, int(round(v * n / secs))))
    elif k == "@impact_ring":
        PM.PERCUSSION_RING[note] = float(v)
        PM._RING_CLASSES.clear()
    else:
        setattr(cls, k, float(v))


def crackle(y, sr):
    """The largest rise, in dB, from one 5 ms step to the next in the tail
    (after 40 ms, above 700 Hz, while within 60 dB of the peak). A decaying
    stroke barely rises at all (VSCO's: 1-9 dB); the open conga's first
    fit rose 34 -- crackle from a jitter the grid and the flatness, both
    averages over windows, could not see."""
    from scipy.signal import butter, sosfiltfilt
    t0 = C.onset([y], sr)
    hp = sosfiltfilt(butter(4, 700, btype="high", fs=sr, output="sos"), y)[t0:t0 + int(0.5 * sr)]
    n = int(0.005 * sr)
    e = 10 * np.log10(np.convolve(hp * hp, np.ones(n) / n, "valid")[::n] + 1e-30)
    e = e - e.max()
    d = np.diff(e)[8:]
    live = e[9:] > -60
    d = d[live[:len(d)]] if live[:len(d)].any() else d
    return float(d.max()) if len(d) else 0.0


def contrast(y, sr):
    """How far the top (above 3 kHz) falls from the strike's first 3 ms to
    5-15 ms, in dB: what makes an attack sharp. VSCO's cowbell falls 4.7
    (the mean of its eight takes); the first fit's fell 2.3, its modes'
    jitter keeping the top ringing -- Ben: "not as sharp of an attack, and a
    bit more modal"."""
    from scipy.signal import butter, sosfiltfilt
    t0 = C.onset([y], sr)
    h = sosfiltfilt(butter(4, 3000, btype="high", fs=sr, output="sos"), y)
    a = np.mean(h[t0:t0 + int(0.003 * sr)] ** 2)
    b = np.mean(h[t0 + int(0.005 * sr):t0 + int(0.015 * sr)] ** 2)
    return float(10 * np.log10((a + 1e-30) / (b + 1e-30)))


def early_treble(y, sr):
    """The first 5 ms above 2 kHz against the body's first 50 ms under 500
    Hz, dB: how much a stroke's strike stands out of it. VSCO's taiko: -21
    at fff to -59 at pp; ours, onset 1 ms under +30 dB trims, -14 at every
    velocity -- the low modes switched on in a millisecond splatter."""
    from scipy.signal import butter, sosfiltfilt
    t0 = C.onset([y], sr)
    h = sosfiltfilt(butter(4, 2000, btype="high", fs=sr, output="sos"), y)
    lo = sosfiltfilt(butter(4, 500, btype="low", fs=sr, output="sos"), y)
    return float(10 * np.log10((np.mean(h[t0:t0 + int(0.005 * sr)] ** 2) + 1e-30)
                               / (np.mean(lo[t0:t0 + int(0.05 * sr)] ** 2) + 1e-30)))


def fit(inst, recs, rflat, vels, maxfev):
    from scipy.optimize import minimize
    import percussion_map as PM
    spec = INSTS[inst]
    note = spec["note"]
    cls = inst_class(spec)
    if not spec.get("keep_trim"):
        cls.band_trim_db = ()
    x0 = [max(float(C.START[k] if _get(cls, note, k) is None else _get(cls, note, k)),
              C.FLOOR.get(k, 1e-3)) for k in C.PARAMS]
    rcrack = max(crackle(sum(load(p)[0]), 44100) for p in files(inst))
    rcon = float(np.mean([contrast(sum(load(p)[0]), 44100) for p in files(inst)])) if spec.get("contrast") else None
    # ...or BY DYNAMIC (attack_groups): each group's contrast and early treble
    # against ours at its velocity -- a stick's brightness grows with force,
    # and the loudest stroke alone let the soft ones click
    rgrp = None
    if spec.get("attack_groups"):
        gs = grouped(strokes(inst))
        rgrp = [(float(np.mean([contrast(sum(load(p)[0]), 44100) for p in gs[g][2]])),
                 float(np.mean([early_treble(sum(load(p)[0]), 44100) for p in gs[g][2]]))) for g in gs]
    best = [1e9, None, None]

    def f(z):
        vals = np.exp(z) * np.array(x0)
        for k, v in zip(C.PARAMS, vals):
            _set(cls, note, k, v)
        model, mflat, mcrack, matk = [], [], 0.0, []
        for v in vels:
            chs, sr = C.render(note, v)
            model.append(C.norm(C.grid(chs, sr)))
            mflat.append(flatness(chs, sr, *spec["flat"]))
            mcrack = max(mcrack, crackle(sum(chs), sr))
            if rgrp is not None:
                matk.append((contrast(sum(chs), sr), early_treble(sum(chs), sr)))
        econ = abs(contrast(sum(chs), sr) - rcon) if rcon is not None else 0.0
        if rgrp is not None:
            econ = float(np.sqrt(np.mean([(a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                                          for a, b in zip(matk, rgrp)]) / 2.0))
        e, trim = C.score(model, recs)
        ef = float(np.sqrt(np.mean(np.square(10 * np.log10(np.array(mflat) / np.array(rflat))))))
        ef *= spec.get("flat_weight", 1.0)
        ec = max(0.0, mcrack - rcrack)
        tot = float(np.sqrt(e * e + ef * ef + ec * ec + econ * econ))
        if tot < best[0]:
            best[:] = [tot, vals, trim]
            print("   %6.3f dB (grid %.2f flat %.2f crackle %.1f attack %.1f)  %s  trim %s" % (
                tot, e, ef, ec, econ, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(C.PARAMS, vals)),
                " ".join("%+.1f" % t for t in trim)), flush=True)
        return tot
    n = len(C.PARAMS)
    simplex = np.vstack([np.zeros(n)] + [0.4 * np.eye(n)[i] * (1 if i % 2 else -1) for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                      "adaptive": True})
    return best


# GRAIN: is a shake noise, or clicks? Each band's signal is divided by its own
# 20 ms RMS (the shake's swell and settle out of the way) where that is within
# 20 dB of its peak, and read two ways: the kurtosis of what is left (3 for
# Gaussian noise; a train of separable clicks reads far higher) and the spread
# in dB of its 1 ms energies. NOISE is the same band's spectrum with random
# phases -- what a shaped noise in its place would read. A recording near the
# noise row needs no events; one above it has clicks a noise would lose.
GRAIN_BANDS = ((1000, 4000), (4000, 16000))


def _grain(x, sr, lo, hi):
    from scipy.signal import butter, sosfiltfilt
    t0 = C.onset([x], sr)
    y = sosfiltfilt(butter(4, [lo, hi], btype="band", fs=sr, output="sos"), x[t0:t0 + int(1.0 * sr)])
    w = int(0.02 * sr)
    slow = np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-12
    live = slow > slow.max() * 0.1
    live[:int(0.01 * sr)] = False
    z = (y / slow)[live]
    k = float(np.mean(z ** 4) / np.mean(z ** 2) ** 2)
    n = int(0.001 * sr)
    e = np.array([np.mean(z[i:i + n] ** 2) for i in range(0, len(z) - n, n)])
    return k, float(np.std(10 * np.log10(e + 1e-12)))


def _noise_like(x, sr, seed):
    t0 = C.onset([x], sr)
    seg = x[t0:t0 + int(1.0 * sr)]
    X = np.abs(np.fft.rfft(seg))
    ph = np.random.default_rng(seed).uniform(0, 2 * np.pi, len(X))
    return np.concatenate((np.zeros(t0), np.fft.irfft(X * np.exp(1j * ph), len(seg))))


def grain(inst):
    rec = [sum(load(p)[0]) for p in files(inst)]
    mod = [sum(C.render(INSTS[inst]["note"], v)[0]) for v in (60, 90, 120)]
    rows = (("recorded", rec), ("noise", [_noise_like(x, 44100, i) for i, x in enumerate(rec)]),
            ("model", mod))
    print("%-10s" % "" + "".join("  %5d-%-5d Hz: kurt 1ms dB" % b for b in GRAIN_BANDS))
    for name, xs in rows:
        cells = []
        for lo, hi in GRAIN_BANDS:
            g = np.array([_grain(x, 44100, lo, hi) for x in xs])
            cells.append("%20.1f %6.1f" % (g[:, 0].mean(), g[:, 1].mean()))
        print("%-10s" % name + "".join(cells))


def held_level(note, hold):
    """The level a voice is held at when refitted: velocity 100, its loudest
    150 ms, one note of the given length (C.level)."""
    chs, sr = C.render(note, 100, hold)
    return C.level(chs, sr)


def envelope(inst, n=40, ms=10):
    """10 ms windows, dB re each stroke's energy, recorded against the model
    (velocities 60, 90, 120 at the fit's note length), power-averaged."""
    def env(x, sr):
        t0 = C.onset([x], sr)
        k = int(ms / 1000.0 * sr)
        e = np.array([np.mean(x[t0 + i * k:t0 + (i + 1) * k] ** 2) for i in range(n)])
        return 10 * np.log10(e / e.sum() + 1e-12)

    def avg(rows):
        return 10 * np.log10(np.mean(10 ** (np.array(rows) / 10), 0))
    r = avg([env(sum(load(p)[0]), 44100) for p in files(inst)])
    m = avg([env(sum(C.render(INSTS[inst]["note"], v)[0]), 44100) for v in (60, 90, 120)])
    print("%d ms windows, dB re the stroke's energy" % ms)
    print("rec   " + " ".join("%4.0f" % v for v in r))
    print("model " + " ".join("%4.0f" % v for v in m))
    print("diff  " + " ".join("%+4.0f" % v for v in m - r))
    w = r > -40
    print("rms diff where the recording is within 40 dB: %.2f dB" % np.sqrt(np.mean((m - r)[w] ** 2)))


# THIRD OCTAVES. The octave trim cannot reach inside an octave: the maracas
# came out 4-15 dB strong at 450 Hz and 1.8-2.3 kHz with every octave matched
# (Ben heard it as low end). So the colour is matched again on a third-octave
# long-term spectrum, each band's error added to the class's band_trim_db,
# clipped to 12 dB a pass; under 250 Hz only cut (what little a recording
# has there is room and handling, and a boost would chase it).
_E3 = 2 ** np.arange(np.log2(100), np.log2(20000), 1 / 3.0)
_C3 = np.sqrt(_E3[:-1] * _E3[1:])


def ltas3(chs, sr, dur=1.5, edges=None):
    edges = _E3 if edges is None else edges
    x = sum(chs)
    t0 = C.onset([x], sr)
    seg = x[t0:t0 + int(dur * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 17)) ** 2
    f = np.fft.rfftfreq(1 << 17, 1.0 / sr)
    b = np.array([X[(f >= lo) & (f < hi)].sum() for lo, hi in zip(edges[:-1], edges[1:])])
    return 10 * np.log10(b / b.sum() + 1e-30)


def trim3(inst, passes):
    """Refine the class's band_trim_db in third octaves, writing each pass
    into tonelib.py -- or a shaken noise's noise_bands, which ARE its
    spectrum (no body under them to trim)."""
    import percussion_map as PM
    note = INSTS[inst]["note"]
    cls = inst_class(INSTS[inst])
    path = os.path.join(HERE, "tonelib.py")
    # a band reaching under 100 Hz (a punch's, a hoof's thud): the grid carried
    # down by whole thirds, so the bands over 100 Hz stay where they were
    lo = INSTS[inst].get("trim_lo", 250)
    k = max(0, int(np.ceil(3 * np.log2(100.0 / lo)))) if lo < 100 else 0
    E3 = np.concatenate([_E3[0] * 2.0 ** (-np.arange(k, 0, -1) / 3.0), _E3])
    C3 = np.sqrt(E3[:-1] * E3[1:])
    r = np.mean([ltas3(*load(p), edges=E3) for p in files(inst)], 0)
    keep = (C3 >= lo) & (C3 <= 14000)
    attr = "noise_bands" if getattr(cls, "shake_noise", False) else "band_trim_db"
    # ...or the strike's own noise table, where the noise is what is wrong
    attr = INSTS[inst].get("trim_attr", attr)
    for it in range(passes + 1):
        m = np.mean([ltas3(*C.render(note, v), edges=E3) for v in (60, 90, 120)], 0)
        d = r - m
        k = int(np.argmax(np.abs(d * keep)))
        print("pass %d  rms(model-rec) 250-14k %.2f dB  worst %+.1f at %.0f Hz" % (
            it, np.sqrt(np.mean(d[keep] ** 2)), -d[k], C3[k]), flush=True)
        if it == passes:
            break
        old = getattr(cls, attr) or ((1000.0, 0.0),)
        of, od = np.array([p[0] for p in old], float), np.array([p[1] for p in old], float)
        pts = tuple((float(cf), float(np.interp(np.log(cf), np.log(of), od)
                                      + (np.clip(dd, -12, 12) if kk else min(0.0, dd))))
                    for cf, dd, kk in zip(C3, d, keep) if min(160, lo) <= cf <= 16000)
        setattr(cls, attr, pts)
        PM._RING_CLASSES.clear()
        s = open(path).read()
        a, b = _class_block(s, cls.__name__)
        txt = "    %s = (" % attr + ", ".join("(%.0f, %.1f)" % p for p in pts) + ")"
        blk = s[a:b]
        if re.search(r"^    %s = " % attr, blk, re.M):
            blk = re.sub(r"^    %s = .*$" % attr, lambda _: txt, blk, flags=re.M)
        else:
            blk = blk + "\n" + txt
        open(path, "w").write(s[:a] + blk + s[b:])
    print("model - rec  " + " ".join("%.0f:%+.1f" % (cf, -dd) for cf, dd in zip(C3, d)))


def _class_block(src, cls):
    """(start, end) of class CLS's block in tonelib.py's source: to its first
    top-level line. Ending it at the next "\n\n\nclass" ran a class followed by
    a comment banner (the Jazz kick 2, before the struck bars') on into the
    next class, and its modes were written there."""
    a = src.index("class %s(" % cls)
    m = re.search(r"\n(?=[^\s\n])", src[a + 1:])
    b = a + 1 + m.start() if m else len(src)
    while src[b - 1] == "\n" and src[b - 2] == "\n":
        b -= 1
    return a, b - 1 if src[b - 1] == "\n" else b


def write_fit(inst, spec, vals, trim):
    """--write: the fitted class attributes into tonelib.py, each replaced in
    the class's own block or added to it; band_trim_db the solved trim, ADDED
    to the class's own where the fit kept it in the render (keep_trim). @-
    parameters (the map's own numbers) are printed, not written."""
    cls = inst_class(spec).__name__
    path = os.path.join(HERE, "tonelib.py")
    src = open(path).read()
    a, b = _class_block(src, cls)
    blk = src[a:b]
    for k, v in zip(C.PARAMS, vals):
        if k.startswith("@"):
            continue
        line = "    %s = %.6g" % (k, v)
        if re.search(r"^    %s = " % k, blk, re.M):
            blk = re.sub(r"^    %s = [^#\n]*" % k, lambda _: line + "  ", blk, count=1, flags=re.M)
        else:
            blk = blk + "\n" + line
    old = dict(getattr(inst_class(spec), "band_trim_db", ()) or ()) if spec.get("keep_trim") else {}
    pts = tuple((round(c), round(float(t) + float(old.get(round(c), 0.0)), 1)) for c, t in zip(C.CENTRES, trim))
    txt = "    band_trim_db = %s" % (pts,)
    if re.search(r"^    band_trim_db = ", blk, re.M):
        blk = re.sub(r"^    band_trim_db = .*$", lambda _: txt, blk, count=1, flags=re.M)
    else:
        blk = blk + "\n" + txt
    open(path, "w").write(src[:a] + blk + src[b:])
    for f in glob.glob(os.path.join(HERE, "__pycache__", "tonelib.*.pyc")):
        os.remove(f)
    print("    written to %s" % cls)


def write_modes(spec, ms):
    """--modes --write: the modes read into the class's DRUM_MODES."""
    cls = inst_class(spec).__name__
    path = os.path.join(HERE, "tonelib.py")
    src = open(path).read()
    a, b = _class_block(src, cls)
    blk = src[a:b]
    txt = "    DRUM_MODES = (%s)" % ", ".join("(%.4f, %.1f, %.0f)" % m for m in ms)
    if re.search(r"^    DRUM_MODES = ", blk, re.M):
        blk = re.sub(r"^    DRUM_MODES = .*$", lambda _: txt, blk, count=1, flags=re.M)
    else:
        blk = blk + "\n" + txt
    open(path, "w").write(src[:a] + blk + src[b:])
    print("    written to %s" % cls)


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    inst = pos[0]
    spec = INSTS[inst]
    if "params" in spec:
        C.PARAMS = spec["params"]
    if "--attack" in argv:
        spec = dict(spec, contrast=True, attack_groups=True, keep_trim=True)
        INSTS[inst] = spec
        C.PARAMS = tuple(spec.get("params", C.PARAMS)) + ("attack_time",)
    C.CLIP = spec.get("clip")
    if "T" in spec:
        C.T = spec["T"]
        C.COL_W = np.array([0.3] + [1.0] * (len(C.T) - 1))
    if "edges" in spec:
        C.EDGES = spec["edges"]
        C.CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(C.EDGES[:-1], C.EDGES[1:]))
    HOLD[0] = float(next((a.split("=")[1] for a in argv if a.startswith("--hold=")), spec.get("hold", 1.0)))
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import percussion_map as PM
    PROG[0] = spec.get("program")
    C.KIT = spec.get("kit", 0)      # a drum note in another set (the SFX set's)
    f0 = inst_f0(spec)
    if "--modes" in argv:
        GROUP[0] = next((a.split("=")[1] for a in argv if a.startswith("--group=")), None)
        ms = modes(inst, f0)
        print("== %s: %d modes over %.1f Hz" % (inst, len(ms), f0))
        print("    DRUM_MODES = (%s)" % ", ".join("(%.4f, %.1f, %.0f)" % m for m in ms))
        if "--write" in argv:
            write_modes(spec, ms)
        return 0
    if "--level" in argv:
        for h in (HOLD[0], 1.5):
            print("%d hold %.2f: %.2f dB" % (spec["note"], h, held_level(spec["note"], h)))
        return 0
    if "--env" in argv:
        envelope(inst)
        return 0
    if "--grain" in argv:
        grain(inst)
        return 0
    trim = next((a for a in argv if a.startswith("--trim3")), None)
    if trim:
        trim3(inst, int(trim.split("=")[1]) if "=" in trim else 3)
        return 0
    if "--scatter" in argv:
        r, m = scatter(inst)
        print("== %s: takes of one stroke differ %s dB; the model's strokes %.1f dB" % (
            inst, "%.1f" % r if r is not None else "--", m))
        return 0
    ss = strokes(inst)
    gs = grouped(ss)
    print("== %s, %d strokes: %s" % (inst, len(ss), "  ".join(
        "%s %.0f" % (os.path.basename(p)[:24], l - max(s[1] for s in ss)) for _, l, _, p in ss)))
    cache = {}
    names = list(gs)
    if "--fit" in argv:
        if names == ["all"]:
            vels = [100]
        else:
            vels = [C.model_velocity(spec["note"], gs[g][0], cache) for g in names]
        recs = []
        rflat = []
        for g in names:
            r = C.norm(np.where(gs[g][1] < -100, -200.0, gs[g][1]))
            recs.append(np.where(gs[g][1] < -100, -200.0, r))
            rflat.append(float(np.mean([flatness(*load(p), *spec["flat"]) for p in gs[g][2]])))
        print("== fit at velocities %s, recorded flatness %s" % (vels, " ".join("%.3f" % x for x in rflat)),
              flush=True)
        e, vals, trim = fit(inst, recs, rflat, vels, int(next(
            (a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 300)))
        print("   BEST %.3f dB" % e)
        for k, v in zip(C.PARAMS, vals):
            print("    %s = %.6g" % (k, v))
        print("    band_trim_db = (%s)" % ", ".join("(%.0f, %.1f)" % (c, t) for c, t in zip(C.CENTRES, trim)))
        if "--write" in argv:
            write_fit(inst, spec, vals, trim)
        return 0
    for g in names:
        drop, gr, _ = gs[g]
        C.show("recorded %s (%.1f dB)" % (g, drop), gr)
        if "--model" in argv:
            v = 100 if g == "all" else C.model_velocity(spec["note"], drop, cache)
            chs, sr = C.render(spec["note"], v)
            m = C.grid(chs, sr)
            C.show("model v%d, minus recorded" % v, np.where(gr < -100, np.nan, (m - m.max()) - gr))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
