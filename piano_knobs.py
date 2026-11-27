"""THE PIANOS' KNOBS: the physical controls a player turns on a piano voice
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
N_KNOBS = 12
# (their names in a session -- nv_host::VK_NAMES -- and on the VOICE card:
# FELT the felt's stiffness, log10 of its K; FELT LEFT the soft felt over a
# worn hammer's hard layer, mm at the worn keys -- thin, a soft felt bottoms
# out on it and brightens; thick, a fresh hammer that never does)
NAMES = ('felt', 'felt_left', 'strike', 'unison', 'lid', 'board', 'pickup',
         'tine', 'gap', 'swing', 'tonebar', 'reed')
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


def knobs_of(cls):
    """The knobs cls has and its value of each (live.cpp nv_voicing_knobs)."""
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
    return a


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
    if not mask or not (_family(base) or _ep(base)):
        return base
    key = (base, tuple(t), mask)
    got = _MADE.get(key)
    if got is not None:
        return got
    a = dict(_attrs(base, t, mask), section_salt_name=getattr(base, 'section_salt_name', None) or base.__name__)
    got = type('%s_voiced%d' % (base.__name__, len(_MADE)), (base,), a)
    _MADE[key] = got
    return got
