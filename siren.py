"""THE SIREN'S ROTOR: one model for both renderers (as moog.py is for the
Messenger's pitch rows), so a file and a live part agree.

A siren is a disc of holes spinning in a jet of air: its pitch is holes x
revolutions per second, so its pitch IS the rotor's speed, and its speed is a
mechanical thing with inertia. Measured (examples/siren_fit.py):

  THE FIRE SIREN (SFX 67; freesound 819369): a motor winds it up and its rotor
  is its own fan. One equation fits the whole gesture to 33 cents rms --

      du/dt = a p (W sqrt(p) - u) - b u

  u the speed in units of its steady speed at full drive (the key's pitch), p
  the drive 0..1. Wound up at p = 1: onto u = 1 with time constant 1/(a+b) =
  1.23 s (733 Hz plateau); let go (p = 0): it coasts as exp(-b t), b = 0.091
  /s, eleven seconds a factor e. A drag growing with speed fitted to zero. Its
  level follows its speed (it pumps its own air): flat to half speed, then a
  knee -- (u/uk)^n / (1 + (u/uk)^n), uk 0.452, n 3.8, 1.1 dB rms over the
  coast -- so the wail fades as it falls.

  THE HELMHOLTZ DOUBLE SIREN (GS 125.5): fed with air from outside, as the
  siren whistle (VCSL) is -- breath winds it up in ~0.6 s and it sings only
  while blown: the tone is the air through the holes, and it stops with the
  air while the disc coasts on, silent. Played again before it stops, it
  starts from the speed it still has: the wail.

The drive's square root: a jet's speed goes as the square root of its
pressure, and the rotor turns toward the jet's speed. W makes u = 1 at p = 1.

ROWS, as the renderers read them (blockrender BR/BC/BL): per block the mean
speed ratio, per block edge the level. The phase is summed from the ratio
by the caller exactly as bend_blocks sums it, so a row is a chirp and never a
click.
"""
import math

# (a, b, level law). a and b per second.
FIRE = dict(a=0.723, b=0.0908, uk=0.452, n=3.8, air_tau=0.0)
HELMHOLTZ = dict(a=1.50, b=0.17, uk=0.0, n=0.0, air_tau=0.04)
MODELS = {"fire": FIRE, "helmholtz": HELMHOLTZ}

# where a coasting fire siren is let go: its level this far under full
FLOOR_DB = 60.0
# under this speed a disc chops nothing: the Helmholtz siren's tone fades in
# from standstill over it (u^2 / (u^2 + U_LOW^2))
U_LOW = 0.12


def w_top(m):
    """W, so that u settles on 1 at full drive: a(W - 1) = b."""
    return (m["a"] + m["b"]) / m["a"]


def step(u, p, dt, m):
    """The speed after dt seconds at a steady drive p (exact: the equation is
    linear in u for a fixed p)."""
    k = m["a"] * p + m["b"]
    if k <= 0.0:
        return u
    target = m["a"] * p * w_top(m) * math.sqrt(max(p, 0.0)) / k
    return target + (u - target) * math.exp(-k * dt)


def mean_over(u, p, dt, m):
    """The mean speed over dt from u at drive p (the block's mean ratio)."""
    k = m["a"] * p + m["b"]
    if k <= 0.0 or dt <= 0.0:
        return u
    target = m["a"] * p * w_top(m) * math.sqrt(max(p, 0.0)) / k
    return target + (u - target) * (1.0 - math.exp(-k * dt)) / (k * dt)


def fire_level(u, m=FIRE):
    """A self-pumped siren's amplitude at speed u, 1 at full speed."""
    if u <= 0.0:
        return 0.0
    x = (u / m["uk"]) ** m["n"]
    x1 = (1.0 / m["uk"]) ** m["n"]
    return math.sqrt((x / (1.0 + x)) / (x1 / (1.0 + x1)))


def blown_level(u, air):
    """An air-fed siren's amplitude: the jet's speed (the square root of the
    air's pressure), the disc chopping it once it turns."""
    return math.sqrt(max(air, 0.0)) * (u * u / (u * u + U_LOW * U_LOW))


def air_step(air, p, dt, m):
    """The chest's pressure following the key's (a short valve: air_tau)."""
    tau = m["air_tau"]
    if tau <= 0.0:
        return p
    return p + (air - p) * math.exp(-dt / tau)


def coast_time(u, m=FIRE, floor_db=FLOOR_DB):
    """Seconds until a coasting fire siren is FLOOR_DB under full."""
    lo, hi = 0.0, 600.0
    if fire_level(u, m) <= 10.0 ** (-floor_db / 20.0):
        return 0.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if fire_level(u * math.exp(-m["b"] * mid), m) > 10.0 ** (-floor_db / 20.0):
            lo = mid
        else:
            hi = mid
    return hi


class Rotor:
    """One siren's state, stepped a block at a time: speed, the chest's air."""

    def __init__(self, kind, u=0.0, air=0.0):
        self.m = MODELS[kind]
        self.kind = kind
        self.u = float(u)
        self.air = float(air)

    def block(self, p, dt):
        """Advance dt seconds at drive p: (mean speed over the block, level at
        its start, level at its end)."""
        l0 = self.level()
        r = mean_over(self.u, p, dt, self.m)
        self.u = step(self.u, p, dt, self.m)
        self.air = air_step(self.air, p, dt, self.m)
        return r, l0, self.level()

    def level(self):
        if self.kind == "fire":
            return fire_level(self.u, self.m)
        return blown_level(self.u, self.air)

    def coast(self, dt):
        """Let it run dt seconds with no air (between two presses)."""
        self.u *= math.exp(-self.m["b"] * dt)
        self.air = air_step(self.air, 0.0, dt, self.m)


# THE CRANK: the upper chest turned against the lower, by the mod wheel. A turn
# of half a hole's spacing on the 12-hole rows (pi/12 of a revolution) puts
# their fundamentals in antiphase -- Helmholtz's demonstration -- so the wheel's
# travel is that half spacing: 0..180 degrees on the 12-row's fundamental.
CRANK_MAX = math.pi / 12.0


def crank_angle(cc1):
    return CRANK_MAX * max(0, min(127, int(cc1))) / 127.0


def crank_samples(theta, f_rev, sr):
    """The upper disc's extra phase as samples of the note's own time (the BC
    term the kernel multiplies by each partial's om): an angle theta of the
    chest shifts a row of H holes' harmonic h by h H theta, and that partial's
    om is h H 2 pi f_rev / sr -- so theta / (2 pi f_rev / sr) for every one."""
    return theta * sr / (2.0 * math.pi * f_rev)
