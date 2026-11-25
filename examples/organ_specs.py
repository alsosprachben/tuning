#!/usr/bin/env python3
"""THE ORGANS THE BUILD KNOWS (examples/organ_build.py --organ=NAME): each a
description -- its host voice in tonelib and how it is played, its stops (each
a class, the construction it is simulated from, its rank), where its data
lives, and its voicing school (how the voicer regulates it). The scripts of
the build (organ_bake, organ_levels, organ_regulate) read the one chosen
(ORGAN_BUILD in the environment, which organ_build sets; default "baroque").

A new organ (Ben: "for when we want to build the romantic one") is a new
entry: its host class and stop classes in tonelib, its stops' constructions
in fluepipe_sim / reedpipe_sim, its own data files, its voicing.
"""
import os

# class -> (fluepipe_sim.STOPS key, the rank's name on GM 19, writes speech?,
# its level: "hold" = where the console has it (set by ear), "sim" = the
# simulated pipe's radiated level against the simulated principal 8's, both
# on the same wind -- for the ranks whose level was a recording's balance)
BAROQUE_CLASSES = {
    "FlueOrganProperties": ("principal", "principal 8", True, "hold"),
    "PrincipalOctave4Properties": ("octave", "octave 4", False, "hold"),
    "PrincipalOctave2Properties": ("superoctave", "super octave 2", False, "hold"),
    "OrganQuintProperties": ("quint", "quint 2-2/3", True, "hold"),
    "OrganPrincipal16Properties": ("principal16", "principal 16", True, "hold"),
    "OrganQuint513Properties": ("quint513", "quint 5-1/3", True, "hold"),
    "OrganGedaktProperties": ("gedakt", "flute 8", "modes", "hold"),
    "OrganBourdonProperties": ("bourdon16", "bourdon 16", "modes", "hold"),
    "OrganKoppelfluteProperties": ("rohrflute", "koppelflute 4", "modes", "sim"),
    "OrganWaldfluteProperties": ("waldflute", "waldflute 2", "modes", "sim"),
    "OrganNazardProperties": ("rohrflute", "nazard 2-2/3", "modes", "sim"),
    "OrganTierceProperties": ("tierce", "tierce 1-3/5", "modes", "sim"),
    "OrganSubbassProperties": ("subbass16", "subbass 16", "modes", "sim"),
    "OrganGambaProperties": ("gamba", "gamba 8", "modes", "sim"),
    "OrganCelesteProperties": ("gamba", "celeste 8", "modes", "sim"),
    # THE REEDS (examples/reedpipe_sim.py: the beating tongue against its
    # resonator's modes, in time; tone and speech both from it)
    "OrganTrumpetProperties": ("reed:trumpet", "trumpet 8", "reed", "hold"),
    "OrganClarionProperties": ("reed:clarion", "reed 4", "reed", "hold"),
    "OrganCromorneProperties": ("reed:cromorne", "reed 8", "reed", "hold"),
    "OrganBassonProperties": ("reed:basson", "reed 16", "reed", "hold"),
    "OrganTrompetteProperties": ("reed:trompette", "trompette 8", "reed", "sim"),
    "OrganOboeProperties": ("reed:oboe", "oboe 8", "reed", "sim"),
    "OrganContrabassoonProperties": ("reed:contrabassoon", "contrabassoon 32", "reed", "sim"),
    "OrganVoxHumanaProperties": ("reed:voxhumana", "vox humana 8", "reed", "sim"),
}


ORGANS = {
    # GM 19's church organ: the lean European console of 25 stops, Audsley's
    # constructions, regulated even (Ben 2026-11-24/25)
    "baroque": dict(
        host="FlueOrganProperties", program=19, bank=0,
        classes=BAROQUE_CLASSES,
        reference_class="FlueOrganProperties", reference_rank="principal 8",
        bare="organ_bare_tables.json", regulation="organ_regulation.json",
        # where a rank's balance was set by ear, written keys: the manuals', the Pedal's
        level_keys=(48, 60, 72), pedal_level_keys=(36, 43, 48), pedal_division="Pedal",
        # stops whose level is by ear alone (the simulation not credible): tables as they are
        held=("OrganVoxHumanaProperties",),
        # THE VOICING SCHOOL (organ_regulate): the reference loudness, phons an
        # octave up the compass, how far a voicer can move a pipe
        ref_spl=72.0, treble_ascendancy_db=0.0, reg_max_db=12.0,
    ),
}


def name():
    return os.environ.get("ORGAN_BUILD", "baroque")


def current():
    """The chosen organ's description."""
    return ORGANS[name()]
