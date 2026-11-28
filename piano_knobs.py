"""THE PIANOS' KNOBS (and the electric guitars' and basses' since: PICK,
STRINGS): the physical controls a player turns on a piano voice
(the GrandPianoProperties family -- the grand, the upright, the honky-tonk,
the electric grand), each a few of the class's own attributes, in the
player's terms and units: the felt's stiffness, the felt left over a worn
hammer's hard layer, the strike point, the unison's spread, the lid, the
soundboard's top, the electric grand's piezo.

A knob's value is absolute (the felt's log10 stiffness, the strike point's
ratio, cents, dB, Hz); a part's setting becomes, for each key's class, an
OFFSET or a RATIO against the class at key 60 -- so a variation whose keys
are other classes moves each the same way. The native engine applies the
same transforms to a copy of the class (live.cpp nv_voicing_apply); this
module is the reference it is checked against (examples/piano_knobs_check.py).

    knobs_of(cls)               -> {index: value}: the knobs cls has, at its values
    transforms(cls, values)     -> (t[N_KNOBS], mask): a setting against cls
    piano_class(base, t, mask)  -> base with the transforms applied (cached)
    voicing(base, felt=..., ...) -> the attributes of base moved by knobs given
                                   as moves (an offset for felt and lid, else a
                                   ratio): a variation as knob positions
"""

HAMMER, WEAR, STRIKE, UNISON, LID, BOARD, PICKUP = range(7)
# THE ELECTRIC PIANOS' (ElectricPianoProperties, played natively: native.ep_voice):
# TINE the Rhodes tine's rest off the pole's centre (pickup_offset, in the
# pole's half-widths), GAP the tine to the pickup (pickup_gap, ditto), SWING
# the hammer's swing (pickup_deflection), TONEBAR its bell (tonebar_gains),
# REED the Wurlitzer reed's rest off the plate's plane (pickup_offset, slot widths)
TINE, GAP, SWING, TONEBAR, REED = range(7, 12)
# THE ELECTRIC GUITARS' AND BASSES' (ElectricGuitarProperties, played natively:
# native.electric_voice, not a Clavinet): PICK where the pick strikes the
# string (strike_point, a share of the string from the bridge, at the open
# string -- a fret moves it as it moves the note's), STRINGS the string's own
# loss, the part that grows with frequency: fresh strings ring bright, old
# ones go dead (harmonic_decay_db; a bass whose decay is its string's physics,
# the winding's visco-elastic loss, winding_loss -- where grime and wear sit)
PICK, STRINGS = 12, 13
# ...and TONE, the tone pot: the share of its resistance in circuit (tone_turn,
# 1 full up; the coil's circuit tonelib._tone_pot_gain), where the class has a
# coil's resonance and a tone control
TONE = 14
# THE HARPSICHORDS' (a registered HarpsiBase: its stops ranks of their own
# strings): PLUCK where every jack's quill plucks, the instrument's whole
# character (strike_point, every rank's by the same ratio, so the nasal upper
# 8' stays nearer the bridge than the lower); DAMPER how long the jacks'
# felts take to stop a string (release_valve_time: VCSL's four harpsichords
# 19-68 ms, four regulations) -- every rank's, and the free strings'
PLUCK, DAMPER = 15, 16
N_KNOBS = 17
# (their names in a session -- nv_host::VK_NAMES -- and on the VOICE card:
# FELT the felt's stiffness, log10 of its K; FELT LEFT the soft felt over a
# worn hammer's hard layer, mm at the worn keys -- thin, a soft felt bottoms
# out on it and brightens; thick, a fresh hammer that never does)
NAMES = ('felt', 'felt_left', 'strike', 'unison', 'lid', 'board', 'pickup',
         'tine', 'gap', 'swing', 'tonebar', 'reed', 'pick', 'strings', 'tone', 'pluck', 'damper')
# (how a knob's value moves the class: an offset, or a ratio)
OFFSET = frozenset((HAMMER, LID, TINE, REED))

_BOARD = {'GrandPianoProperties': 0, 'UprightPianoProperties': 1, 'ElectricGrandProperties': 2}


def _board_kind(cls):
    for k in cls.__mro__:
        if 'soundboard_gain' in k.__dict__:
            return _BOARD.get(k.__name__)
    return None


def _family(cls):
    import tonelib as T
    return issubclass(cls, T.GrandPianoProperties) and bool(getattr(cls, 'hammer_model', False))


def _ep(cls):
    """1 a Rhodes, 2 a Wurlitzer -- as the engine plays them -- else 0."""
    import native as N
    return N.ep_kind(cls) if N.ep_voice(cls) else 0


def _guitar(cls):
    """An electric guitar or bass as the engine plays it (not a Clavinet)."""
    import native as N
    return bool(N.electric_voice(cls)) and not N.clav_voice(cls)


def _string_loss(cls):
    """STRINGS' attribute: the winding's loss where the decay is the string's physics."""
    if getattr(cls, 'string_physics', False) and getattr(cls, 'decay_physics', False):
        return 'winding_loss'
    return 'harmonic_decay_db'


def _harpsi(cls):
    """A registered harpsichord: its stops ranks of their own strings
    (the engine's organ with choirs)."""
    import tonelib as T
    return (isinstance(cls, type) and issubclass(cls, T.HarpsiBase) and bool(getattr(cls, 'registerable', False))
            and bool(getattr(cls, 'string_choirs', None)))


def knobs_of(cls):
    """The knobs cls has and its value of each (live.cpp nv_voicing_knobs)."""
    if _harpsi(cls):
        out = {}
        if cls.strike_point:
            out[PLUCK] = float(cls.strike_point)
        if cls.release_valve_time:
            out[DAMPER] = float(cls.release_valve_time)
        return out
    if _guitar(cls):
        # (no PICK where a slap or pop drives the string into its frets: the
        # contact's modes are the note's, not the pick's comb; no STRINGS on a
        # feedback voice, whose loop picks its partial by the strings' loss,
        # a table the export made: Feedback._fb_table)
        import native as N
        out = {}
        if not getattr(cls, 'fret_contact', None):
            out[PICK] = float(cls.strike_point)
        x = float(getattr(cls, _string_loss(cls)))
        if x > 0.0 and not N.feedback_voice(cls):
            out[STRINGS] = x
        if cls.pickup_resonance_hz and cls.tone_pot_ohms:
            out[TONE] = float(cls.tone_turn)
        return out
    ep = _ep(cls)
    if ep:
        out = {}
        if ep == 1:
            out[TINE] = float(cls.pickup_offset)
            out[GAP] = float(cls.pickup_gap)
            if cls.tonebar_gains and cls.tonebar_gains[0] > 0.0:
                out[TONEBAR] = float(cls.tonebar_gains[0])
        else:
            out[REED] = float(cls.pickup_offset)
        if cls.pickup_deflection > 0.0:
            out[SWING] = float(cls.pickup_deflection)
        return out
    if not _family(cls):
        return {}
    out = {HAMMER: float(cls.hammer_logk)}
    if cls.hammer_core_mm > 0.0 or cls.hammer_core_edge_mm > 0.0:
        out[WEAR] = float(cls.hammer_core_mm)
    sc = getattr(cls, 'strike_curve', None)
    out[STRIKE] = 1.0 / float(sc[0]) if sc else float(cls.strike_point)
    lo, hi = getattr(cls, 'string_detune_range', (0.0, 0.0))
    if hi > 0.0:
        out[UNISON] = float(hi)
    bk = _board_kind(cls)
    if bk == 0 and getattr(cls, 'lid_db', 0.0):
        out[LID] = float(cls.lid_db)
    if bk in (0, 1):
        out[BOARD] = float(cls.board_high_hz)
    if bk == 2:
        out[PICKUP] = float(cls.bridge_corner_hz)
    return out


def transforms(cls, values):
    """values {index: absolute value} against cls's own: (t, mask)."""
    have = knobs_of(cls)
    t, mask = [0.0] * N_KNOBS, 0
    for i, v in values.items():
        if i not in have:
            continue
        v0 = have[i]
        if i in OFFSET:
            t[i] = float(v) - v0
        elif v0 > 0.0:
            t[i] = float(v) / v0
        else:
            continue
        mask |= 1 << i
    return t, mask


def _attrs(base, t, mask):
    """The class attributes transforms (t, mask) give base."""
    a = {}
    if mask >> HAMMER & 1:
        a['hammer_logk'] = base.hammer_logk + t[HAMMER]
    if mask >> WEAR & 1:
        a['hammer_core_mm'] = base.hammer_core_mm * t[WEAR]
        a['hammer_core_edge_mm'] = base.hammer_core_edge_mm * t[WEAR]
    if mask >> STRIKE & 1:
        sc = getattr(base, 'strike_curve', None)
        if sc:
            a['strike_curve'] = tuple(x / t[STRIKE] for x in sc)
        else:
            a['strike_point'] = base.strike_point * t[STRIKE]
    if mask >> UNISON & 1:
        lo, hi = base.string_detune_range
        a['string_detune_range'] = (lo * t[UNISON], hi * t[UNISON])
    if mask >> LID & 1:
        a['lid_db'] = base.lid_db + t[LID]
    if mask >> BOARD & 1:
        a['board_high_hz'] = base.board_high_hz * t[BOARD]
    if mask >> PICKUP & 1:
        a['bridge_corner_hz'] = base.bridge_corner_hz * t[PICKUP]
    # (the electric pianos': pickup_gap and pickup_deflection set as they are,
    # not through the Rhodes' millimetres -- a class naming those recomputes
    # both, and a variation's own swing would go)
    if mask >> TINE & 1:
        a['pickup_offset'] = base.pickup_offset + t[TINE]
    if mask >> REED & 1:
        a['pickup_offset'] = base.pickup_offset + t[REED]
    if mask >> GAP & 1:
        a['pickup_gap'] = base.pickup_gap * t[GAP]
    if mask >> SWING & 1:
        a['pickup_deflection'] = base.pickup_deflection * t[SWING]
    if mask >> TONEBAR & 1:
        a['tonebar_gains'] = tuple(g * t[TONEBAR] for g in base.tonebar_gains)
    if mask >> PICK & 1:
        a['strike_point'] = base.strike_point * t[PICK]
    if mask >> STRINGS & 1:
        n = _string_loss(base)
        a[n] = getattr(base, n) * t[STRINGS]
    if mask >> TONE & 1:
        a['tone_turn'] = base.tone_turn * t[TONE]
    if mask >> PLUCK & 1:
        a['strike_point'] = base.strike_point * t[PLUCK]
    if mask >> DAMPER & 1:
        a['release_valve_time'] = base.release_valve_time * t[DAMPER]
    if _harpsi(base) and mask & (1 << PLUCK | 1 << DAMPER):
        # (its other ranks' strings, each its own class: the same moves --
        # live.cpp nv_voicing_apply_organ's, on the organ's pipes)
        def rk(c):
            return _rank_class(c, t, mask) if isinstance(c, type) else c
        a['stop_ranks'] = [tuple(rk(x) if j >= 3 else x for j, x in enumerate(r)) for r in base.stop_ranks]
        a['string_choirs'] = tuple(tuple(rk(x) if j >= 2 else x for j, x in enumerate(c)) for c in base.string_choirs)
    return a


def _rank_class(c, t, mask):
    """A harpsichord rank's string class c with the pluck and damper moved."""
    key = (c, tuple(t), mask & (1 << PLUCK | 1 << DAMPER))
    got = _MADE.get(key)
    if got is None:
        # (its draws the plain rank's: the organ takes its spectrum through
        # tonelib.rank_spectrum, a subclass named for it, "...Rank")
        a = {'section_salt_name': getattr(c, 'section_salt_name', None) or c.__name__ + "Rank"}
        if mask >> PLUCK & 1 and c.strike_point:
            a['strike_point'] = c.strike_point * t[PLUCK]
        if mask >> DAMPER & 1 and c.release_valve_time:
            a['release_valve_time'] = c.release_valve_time * t[DAMPER]
        got = _MADE[key] = type('%s_voiced%d' % (c.__name__, len(_MADE)), (c,), a)
    return got


def voicing(base, **moves):
    """base's attributes moved by knobs named as in NAMES -- felt and lid an
    offset (log10 K, dB), the rest a ratio: a variation written as the knob
    positions it is (patch_map's dark and bright pianos)."""
    t, mask = [0.0] * N_KNOBS, 0
    have = knobs_of(base)
    for n, x in moves.items():
        i = NAMES.index(n)
        if i not in have:
            raise ValueError("%s has no %s knob" % (base.__name__, n))
        t[i] = float(x)
        mask |= 1 << i
    return _attrs(base, t, mask)


_MADE = {}


def piano_class(base, t, mask):
    """base with transforms (t, mask) applied: a subclass, made once (its
    section_salt_name kept, so its draws are base's)."""
    if not mask or not (_family(base) or _ep(base) or _guitar(base) or _harpsi(base)):
        return base
    key = (base, tuple(t), mask)
    got = _MADE.get(key)
    if got is not None:
        return got
    a = dict(_attrs(base, t, mask), section_salt_name=getattr(base, 'section_salt_name', None) or base.__name__)
    got = type('%s_voiced%d' % (base.__name__, len(_MADE)), (base,), a)
    _MADE[key] = got
    return got
