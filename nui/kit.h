// THE CONTROLS (ui/kit.js's, natively): knob, fader, display field, jog dial
// -- one gesture for all of them, made for fingers:
//
//   drag        up or right turns it up; the whole range is TRAVEL design px
//   fine        a second finger resting anywhere: ten times finer
//   detent      a named position (a centre, 0 dB) holds for DETENT px
//   double-tap  back to the default (the reset)
//   long-press  held still LONG_S: the control's sheet, its value to type
//
// Each draws itself from a value it is given; what the finger does comes
// back as flags, so values pushed by the engine never fight a finger (the
// app holds an edited value a moment: App::held).
#pragma once

#include <cmath>
#include <functional>
#include <map>
#include <string>
#include <vector>

#include "imgui.h"
#include "imgui_internal.h"

namespace nui {

static const float TRAVEL = 220.0f, FINE = 10.0f, DETENT = 14.0f, SLOP = 6.0f;
static const double TAP_S = 0.30, LONG_S = 0.55;

enum { K_CHANGED = 1, K_TAP = 2, K_RESET = 4, K_ENDED = 8, K_ACTIVE = 16, K_LONG = 32 };

struct Range {
    float lo = 0, hi = 1, step = 0, travel = TRAVEL;
    std::vector<float> detents;
};

// the gesture's state: one finger on one control at a time (the rest resting: fine)
struct Kit {
    ImGuiID active = 0;
    ImVec2 p0{0, 0};
    float base = 0, k = 1.0f;
    bool moved = false, was_fine = false, long_fired = false;
    double t0 = 0;
    int fingers = 0;                    // (fingers down now, from SDL's touch events)
    std::map<ImGuiID, double> last_tap;
    std::string bubble;
    ImVec2 bubble_at{0, 0};
    bool fine() const { return fingers >= 2; }
};

// raw design px of drag -> value, flat for DETENT px at each detent (kit.js's valueOf)
inline float value_of(const Range &g, float base, float r)
{
    const float per = (g.hi - g.lo) / g.travel;
    float v = base + r * per;
    for (float d : g.detents) {
        const float at = (d - base) / per;
        if (r > at && at >= 0)
            v = r - at < DETENT ? d : v - DETENT * per;
        else if (r < at && at <= 0)
            v = at - r < DETENT ? d : v + DETENT * per;
    }
    v = std::max(g.lo, std::min(g.hi, v));
    if (g.step > 0)
        v = g.lo + std::round((v - g.lo) / g.step) * g.step;
    return v;
}

// THE GESTURE over a rectangle (screen px): v moved by the finger; flags back.
// axis: 0 both (up + right), 1 vertical only
inline int gesture(Kit &K, const char *id, ImVec2 a, ImVec2 b, float &v, const Range &g, int axis = 0)
{
    ImGui::SetCursorScreenPos(a);
    ImGui::PushID(id);
    ImGui::InvisibleButton("g", ImVec2(std::max(1.0f, b.x - a.x), std::max(1.0f, b.y - a.y)));
    const ImGuiID me = ImGui::GetItemID();
    ImGui::PopID();
    int out = 0;
    const ImVec2 m = ImGui::GetIO().MousePos;
    if (ImGui::IsItemActivated()) {
        K.active = me;
        K.p0 = m;
        K.base = v;
        K.moved = false;
        K.was_fine = K.fine();
        K.t0 = ImGui::GetTime();
        K.long_fired = false;
    }
    if (ImGui::IsItemActive() && K.active == me) {
        out |= K_ACTIVE;
        const float dx = (m.x - K.p0.x) / K.k, dy = (K.p0.y - m.y) / K.k;
        if (!K.moved && !K.long_fired && std::hypot(dx, dy) * K.k >= SLOP)
            K.moved = true;
        if (!K.moved && !K.long_fired && ImGui::GetTime() - K.t0 >= LONG_S) {   // (held still: the sheet)
            K.long_fired = true;
            out |= K_LONG;
        }
        if (K.moved) {
            const bool f = K.fine();
            if (f != K.was_fine) {              // (fine on or off mid-drag: from here, no jump)
                K.base = v;
                K.p0 = m;
                K.was_fine = f;
            } else {
                const float d = axis == 1 ? dy : dy + dx;
                const float nv = value_of(g, K.base, d / (f ? FINE : 1.0f));
                if (nv != v) {
                    v = nv;
                    out |= K_CHANGED;
                }
            }
            K.bubble_at = m;
        }
    }
    if (ImGui::IsItemDeactivated() && K.active == me) {
        out |= K_ENDED;
        if (!K.moved && !K.long_fired) {
            const double now = ImGui::GetTime();
            auto it = K.last_tap.find(me);
            if (it != K.last_tap.end() && now - it->second < TAP_S) {
                out |= K_RESET;
                K.last_tap.erase(it);
            } else {
                out |= K_TAP;
                K.last_tap[me] = now;
            }
        }
        K.active = 0;
        K.bubble.clear();
    }
    return out;
}

// THE JOG DIAL's turn (kit.js's dial): steps of 15 degrees (45 fine)
struct Dial {
    ImGuiID active = 0;
    float last = 0, acc = 0, rot = 0;
};
// A DIAL TURNED FROM A ZONE (the phone's corner wheel): a touch in the rect z0-z1
// turns D by its angle round c -- zones sharing one D, the one touched turning it
inline int dial_zone(Kit &K, Dial &D, const char *id, ImVec2 c, ImVec2 z0, ImVec2 z1, float per_deg = 12.0f)
{
    if (z1.x - z0.x < 4 || z1.y - z0.y < 4)
        return 0;
    ImGui::SetCursorScreenPos(z0);
    ImGui::PushID(id);
    ImGui::InvisibleButton("z", ImVec2(z1.x - z0.x, z1.y - z0.y));
    const ImGuiID me = ImGui::GetItemID();
    ImGui::PopID();
    const ImVec2 m = ImGui::GetIO().MousePos;
    const float ang = std::atan2(m.y - c.y, m.x - c.x) * 180.0f / 3.14159265f;
    int steps = 0;
    if (ImGui::IsItemActivated()) {
        D.active = me;
        D.last = ang;
        D.acc = 0;
    }
    if (ImGui::IsItemActive() && D.active == me) {
        float d = ang - D.last;
        D.last = ang;
        if (d > 180)
            d -= 360;
        if (d < -180)
            d += 360;
        D.rot += d;
        D.acc += d;
        const float per = K.fine() ? 3 * per_deg : per_deg;
        while (D.acc >= per) {
            D.acc -= per;
            steps++;
        }
        while (D.acc <= -per) {
            D.acc += per;
            steps--;
        }
    }
    if (ImGui::IsItemDeactivated() && D.active == me)
        D.active = 0;
    return steps;
}
inline int dial(Kit &K, Dial &D, const char *id, ImVec2 c, float r)
{
    ImGui::SetCursorScreenPos(ImVec2(c.x - r, c.y - r));
    ImGui::PushID(id);
    ImGui::InvisibleButton("d", ImVec2(2 * r, 2 * r));
    const ImGuiID me = ImGui::GetItemID();
    ImGui::PopID();
    const ImVec2 m = ImGui::GetIO().MousePos;
    const float ang = std::atan2(m.y - c.y, m.x - c.x) * 180.0f / 3.14159265f;
    int steps = 0;
    if (ImGui::IsItemActivated()) {
        D.active = me;
        D.last = ang;
        D.acc = 0;
    }
    if (ImGui::IsItemActive() && D.active == me) {
        float d = ang - D.last;
        D.last = ang;
        if (d > 180)
            d -= 360;
        if (d < -180)
            d += 360;
        D.rot += d;
        D.acc += d;
        const float per = K.fine() ? 45.0f : 15.0f;
        while (D.acc >= per) {
            D.acc -= per;
            steps++;
        }
        while (D.acc <= -per) {
            D.acc += per;
            steps--;
        }
    }
    if (ImGui::IsItemDeactivated())
        D.active = 0;
    return steps;
}

}  // namespace nui
