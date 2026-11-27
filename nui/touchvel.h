// HOW HARD A TOUCH PLAYS: the player's choice, one for the Keys card and the
// Drums pads (the Setup card's), and either card its own if asked
//   - FIXED: every note the one velocity;
//   - POSITION: where the finger lands -- the key's front edge, the pad's top
//     the hard end (REVERSE swaps it) -- over a range, through a curve (SOFT
//     wants the hard end to play loud, HARD plays loud sooner).
// Kept in the session's "ui" (ui_set "touch"). Later ways (a tap's jolt, the
// finger's contact, the Pencil's pressure) are more modes here.
// And THE FINGERS: each finger holds what it landed on (a key, a pad); what it
// struck is let go when it lifts -- or, on the keys, slides to another.
#pragma once

#include <cmath>
#include <cstring>
#include <map>

#include "app.h"
#include "tuning.h"
#include "widgets.h"

namespace nui {

struct TouchVel {
    std::string mode = "position";      // "fixed" | "position"
    int fixed = 100;
    int lo = 30, hi = 127;
    std::string curve = "linear";       // "soft" | "linear" | "hard"
    bool flip = false;
};
struct TouchPrefs {
    TouchVel all;
    bool keys_own = false, drums_own = false;
    TouchVel keys, drums;
    std::string slide = "glide";        // (the Keys card's finger drawn along a held key: "glide" -- a glissando,
                                        //  each key it crosses struck -- "bend", or "press": aftertouch)
    int last_v = -1;                    // (the last note's velocity, shown on the cards)
};
static TouchPrefs g_touch;

inline J touch_json(const TouchVel &t)
{
    J o = sess::obj();
    o.o["mode"] = sess::str(t.mode);
    o.o["fixed"] = sess::integer(t.fixed);
    o.o["lo"] = sess::integer(t.lo);
    o.o["hi"] = sess::integer(t.hi);
    o.o["curve"] = sess::str(t.curve);
    o.o["flip"] = sess::boolean(t.flip);
    return o;
}
inline void touch_from(TouchVel &t, const J *o)
{
    if (!o || !o->is(J::OBJ))
        return;
    const std::string m = str(o, "mode"), c = str(o, "curve");
    if (m == "fixed" || m == "position")
        t.mode = m;
    if (c == "soft" || c == "linear" || c == "hard")
        t.curve = c;
    t.fixed = std::max(1, std::min(127, (int)num(o, "fixed", t.fixed)));
    t.lo = std::max(1, std::min(127, (int)num(o, "lo", t.lo)));
    t.hi = std::max(1, std::min(127, (int)num(o, "hi", t.hi)));
    t.flip = flag(o, "flip");
}
// (from hello's "ui")
inline void touch_load(const J *ui)
{
    TouchPrefs &P = g_touch;
    const J *t = ui && ui->is(J::OBJ) ? ui->get("touch") : nullptr;
    if (!t || !t->is(J::OBJ))
        return;
    touch_from(P.all, t->get("all"));
    touch_from(P.keys, t->get("keys"));
    touch_from(P.drums, t->get("drums"));
    P.keys_own = flag(t, "keys_own");
    const std::string sl = str(t, "keys_slide");
    if (sl == "glide" || sl == "bend" || sl == "press")
        P.slide = sl;
    P.drums_own = flag(t, "drums_own");
}
inline void touch_save(App &a)
{
    const TouchPrefs &P = g_touch;
    J t = sess::obj();
    t.o["all"] = touch_json(P.all);
    t.o["keys"] = touch_json(P.keys);
    t.o["drums"] = touch_json(P.drums);
    t.o["keys_own"] = sess::boolean(P.keys_own);
    t.o["drums_own"] = sess::boolean(P.drums_own);
    t.o["keys_slide"] = sess::str(P.slide);
    call(a, "{\"call\":\"ui_set\",\"key\":\"touch\",\"value\":" + sess::dump(t) + "}");
}
// (the settings a card plays by: its own, or Setup's)
inline const TouchVel &touch_for(const char *card)
{
    const TouchPrefs &P = g_touch;
    if (!strcmp(card, "keys") && P.keys_own)
        return P.keys;
    if (!strcmp(card, "drums") && P.drums_own)
        return P.drums;
    return P.all;
}
// a touch's velocity by these settings: depth 0 the soft end, 1 the hard
inline int touch_velocity_by(const TouchVel &t, float depth)
{
    if (t.mode == "fixed")
        return t.fixed;
    float d = std::max(0.0f, std::min(1.0f, depth));
    if (t.flip)
        d = 1 - d;
    const float g = t.curve == "soft" ? 1.6f : t.curve == "hard" ? 0.6f : 1.0f;
    return std::max(1, std::min(127, (int)std::lround(t.lo + (t.hi - t.lo) * std::pow(d, g))));
}
inline int touch_velocity(const char *card, float depth)
{
    const int v = touch_velocity_by(touch_for(card), depth);
    g_touch.last_v = v;
    return v;
}
// (a card's heading: how it plays now -- "vel 100", "vel 30-127")
inline std::string touch_says(const char *card)
{
    const TouchVel &t = touch_for(card);
    char b[48];
    if (t.mode == "fixed")
        snprintf(b, sizeof b, "%d", t.fixed);
    else
        snprintf(b, sizeof b, "%d\xe2\x80\x93%d", t.flip ? t.hi : t.lo, t.flip ? t.lo : t.hi);
    return b;
}

// THE SETTINGS' PANEL: the ways as chips, then the way's own values; on a
// card (card set), AS SETUP first -- own then false while it is lit. y moves
// past it; true when anything changed (saved by the caller: touch_save)
inline bool touch_panel(App &a, const std::string &id, TouchVel &t, bool *own, float x, float &y, float w)
{
    bool ch = false;
    const bool IP = a.tab;
    const float fh = IP ? 46 : 52, fw = IP ? 130 : 150, gap = 8;
    {
        std::vector<std::string> w_ = {T("FIXED"), T("POSITION")};
        std::vector<bool> lit = {t.mode == "fixed", t.mode == "position"};
        if (own) {
            w_.insert(w_.begin(), T("AS SETUP"));
            lit.insert(lit.begin(), !*own);
            if (!*own)
                lit[1] = lit[2] = false;
        }
        const int h = flow_buttons(a, id + "mode", x, y, w, w_, lit);
        if (h >= 0) {
            const int m = own ? h - 1 : h;
            if (own)
                *own = m >= 0;
            if (m >= 0)
                t.mode = m == 0 ? "fixed" : "position";
            ch = true;
        }
    }
    if (own && !*own) {                 // (as Setup: what that is, said)
        const TouchVel &s = g_touch.all;
        text(a, a.font, 14, x, y, SILK_DIM, s.mode == "fixed" ? TF("Setup's: fixed, velocity {0}.", {std::to_string(s.fixed)})
                                                              : TF("Setup's: by position, {0} to {1}.", {std::to_string(s.lo), std::to_string(s.hi)}));
        y += a.lh(14) + 8;
        return ch;
    }
    auto field = [&](const std::string &fid, float fx, int &val, int lo, int hi, const std::string &label) {
        float v = (float)val;
        const int f = lcd_field(a, (id + fid).c_str(), fx, y, fw, fh, v, (float)lo, (float)hi, label, std::to_string((int)v), false);
        if ((f & K_CHANGED) && (int)v != val) {
            val = (int)v;
            ch = true;
        }
    };
    if (t.mode == "fixed") {
        field("fixed", x, t.fixed, 1, 127, T("VELOCITY"));
        y += fh + gap;
        return ch;
    }
    field("lo", x, t.lo, 1, 127, T("SOFT END"));
    field("hi", x + fw + gap, t.hi, 1, 127, T("HARD END"));
    y += fh + gap;
    {
        const std::vector<std::string> cw = {TC("curve", "SOFT"), TC("curve", "LINEAR"), TC("curve", "HARD"), T("REVERSE")};
        const std::vector<bool> lit = {t.curve == "soft", t.curve == "linear", t.curve == "hard", t.flip};
        const int h = flow_buttons(a, id + "curve", x, y, w, cw, lit);
        if (h == 3)
            t.flip = !t.flip;
        else if (h >= 0)
            t.curve = h == 0 ? "soft" : h == 1 ? "linear" : "hard";
        ch |= h >= 0;
    }
    return ch;
}

// THE FINGERS on a card's keys or pads
struct Fingers {
    std::map<unsigned long long, int> held;     // (a finger -- or the mouse, ~0 -- and what it holds)
    std::map<int, int> down;                    // (a key and how many fingers hold it)
};
// now: each finger on the card and what it is over (with its velocity, were it struck there);
// slide: a finger moved onto another lets the old one go and strikes the new (the keys' glissando)
template <class On, class Off>
inline void fingers_step(Fingers &F, const std::map<unsigned long long, std::pair<int, int>> &now, bool slide, On on, Off off)
{
    for (auto it = F.held.begin(); it != F.held.end();) {
        auto n = now.find(it->first);
        if (n == now.end() || (slide && n->second.first != it->second)) {
            if (--F.down[it->second] <= 0) {
                off(it->second);
                F.down.erase(it->second);
            }
            it = F.held.erase(it);
        } else
            ++it;
    }
    for (const auto &n : now)
        if (!F.held.count(n.first) && n.second.first >= 0) {
            F.held[n.first] = n.second.first;
            if (F.down[n.second.first]++ == 0)
                on(n.second.first, n.second.second);
        }
}
template <class Off>
inline void fingers_release(Fingers &F, Off off)
{
    for (const auto &d : F.down)
        if (d.second > 0)
            off(d.first);
    F.down.clear();
    F.held.clear();
}

}  // namespace nui
