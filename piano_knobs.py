"""THE PIANOS' KNOBS: the physical controls a player turns on a piano voice
(the GrandPianoProperties family -- the grand, the upright, the honky-tonk,
the electric grand), each a few of the class's own attributes, in the
player's terms and units.

A knob's value is absolute (the felt's log10 stiffness, the strike point's
ratio, cents, dB, Hz); a part's setting becomes, for each key's class, an
OFFSET or a RATIO against the class at key 60 -- so a variation whose keys
are other classes moves each the same way. The native engine applies the
same transforms to a copy of the class (live.cpp nv_voicing_apply); this
module is the reference it is checked against (examples/piano_knobs_check.py).

    knobs_of(cls)               -> {index: value}: the knobs cls has, at its values
    transforms(cls, values)     -> (t[N_KNOBS], mask): a setting against cls
    piano_class(base, t, mask)  -> base with the transforms applied (cached)
"""

HAMMER, WEAR, STRIKE, UNISON, LID, BOARD, PICKUP = range(7)
N_KNOBS = 7
NAMES = ('hammer', 'wear', 'strike', 'unison', 'lid', 'board', 'pickup')
# (how a knob's value moves the class: an offset, or a ratio)
OFFSET = frozenset((HAMMER, LID))

_BOARD = {'GrandPianoProperties': 0, 'UprightPianoProperties': 1, 'ElectricGrandProperties': 2}


def _board_kind(cls):
    for k in cls.__mro__:
        if 'soundboard_gain' in k.__dict__:
            return _BOARD.get(k.__name__)
    return None


def _family(cls):
    import tonelib as T
    return issubclass(cls, T.GrandPianoProperties) and bool(getattr(cls, 'hammer_model', False))


def knobs_of(cls):
    """The knobs cls has and its value of each (live.cpp nv_voicing_knobs)."""
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


_MADE = {}


def piano_class(base, t, mask):
    """base with transforms (t, mask) applied: a subclass, made once (its
    section_salt_name kept, so its draws are base's)."""
    if not mask or not _family(base):
        return base
    key = (base, tuple(t), mask)
    got = _MADE.get(key)
    if got is not None:
        return got
    a = {'section_salt_name': getattr(base, 'section_salt_name', None) or base.__name__}
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
    got = type('%s_voiced%d' % (base.__name__, len(_MADE)), (base,), a)
    _MADE[key] = got
    return got
