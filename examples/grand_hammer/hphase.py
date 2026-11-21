import os
def install(C):
    import hammer as H, math
    def _mode_phase(self, m):
        got = self.__dict__.get('_hph')
        if got is None:
            fn, mass, K, p = self._hammer_felt()
            vel = int(round(127.0 * self.attack_volume ** 0.5))
            v0 = self.hammer_speed_lo * (self.hammer_speed_hi / self.hammer_speed_lo) ** ((max(1, min(127, vel)) - 1) / 126.0)
            L, Tn, Z = H.string_of(fn, *self._string_scale())
            F, dt = H.contact(fn, v0, mass, K, p, self.strike_point, L, Z, alpha=self.hammer_alpha,
                              tau=10.0 ** self.hammer_log_tau, core_x=self._core_mm(fn) * 1e-3,
                              core_K=10.0 ** self.hammer_core_logk)
            got = []
            for h in range(1, 401):
                w = 2 * math.pi * fn * h * dt; re = im = 0.0
                for i, x in enumerate(F):
                    re += x * math.cos(w * i); im += x * math.sin(w * i)
                got.append(-math.atan2(im, re))
                if fn * h > 12000: break
            self._hph = got
        return got[m - 1] if m - 1 < len(got) else 0.0
    C.mode_phase = _mode_phase