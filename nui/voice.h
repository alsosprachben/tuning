// THE VOICE CARD (Ben, 2026-11-27: knobs for an instrument's physical
// properties, as synths have knobs -- "a huge selling feature of physical
// modeling"): the selected part's voice as the physics it is modelled by,
// each knob a physical variable in the player's terms and units. Pianos
// first (the GrandPianoProperties family: piano_knobs.py) -- the felt's
// stiffness, the felt left over a worn hammer's hard layer, the strike
// point, the unison's spread, the lid, the soundboard's top, the electric
// grand's piezo. A knob's value is the variation's own until turned; turned,
// the part's own (its colour), the patch rebuilt through it -- heard from the
// next note; a double-tap puts it back. The engine's calls: voicing (the card
// open: its knobs pushed as they change), voicing_set, voicing_forget.
#pragma once

#include <cmath>

#include "app.h"
#include "widgets.h"

namespace nui {

struct VoiceUi {
    bool open = false;
    J st;                               // ("voicing": row, part, program, variation, building, knobs[...])
    // (a knob let go: shown at its value until the engine has it)
    std::map<int, std::pair<double, double>> mine;     // (knob -> value, until)
    double acted = -1e9;                // (when a knob was last set or put back: a rebuild then is the knobs')
};
static VoiceUi g_voice;

inline void voice_take(App &a, const J &st)
{
    if ((int)num(&st, "row", -1) == a.row)
        g_voice.st = st;
}
// the card up or down (nui.cpp): the engine pushes the knobs only while it is open
inline void voice_card(App &a, bool open)
{
    VoiceUi &V = g_voice;
    if (open == V.open)
        return;
    V.open = open;
    J r = call(a, std::string("{\"call\":\"voicing\",\"open\":") + (open ? "1" : "0") + "}");
    if (const J *p = r.get("voicing"))
        voice_take(a, *p);
}

// a knob's words as the engine says them (uiapi's voicing_of), for a value being turned
inline std::string voice_words(const std::string &name, double v, double cap)
{
    char t[48];
    if (name == "felt")
        snprintf(t, sizeof t, "x%.2g", std::pow(10.0, v - cap));
    else if (name == "felt_left")
        snprintf(t, sizeof t, "%.2f mm", v);
    else if (name == "strike" || name == "pick")
        snprintf(t, sizeof t, "1/%.1f", 1.0 / std::max(1e-6, v));
    else if (name == "unison")
        snprintf(t, sizeof t, "%.1f c", v);
    else if (name == "lid")
        snprintf(t, sizeof t, "%+.1f dB", v);
    else if (name == "tine" || name == "reed")
        snprintf(t, sizeof t, "%.0f%%", 100.0 * v);
    else if (name == "gap")
        snprintf(t, sizeof t, "%.2f mm", v * 1.7568);      // (uiapi's RHODES_POLE_MM)
    else if (name == "swing" || name == "strings")
        snprintf(t, sizeof t, "x%.2f", v / std::max(1e-12, cap));
    else if (name == "tonebar")
        snprintf(t, sizeof t, "%+.1f dB", 20.0 * std::log10(std::max(1e-9, v / std::max(1e-9, cap))));
    else
        snprintf(t, sizeof t, "%.1f kHz", v / 1000.0);
    return t;
}
inline const char *voice_label(const std::string &name)
{
    if (name == "felt") return N_("FELT");
    if (name == "felt_left") return N_("FELT LEFT");
    if (name == "strike") return N_("STRIKE POINT");
    if (name == "unison") return N_("UNISON");
    if (name == "lid") return N_("LID");
    if (name == "board") return N_("SOUNDBOARD");
    if (name == "tine") return N_("TINE OFFSET");
    if (name == "reed") return N_("REED OFFSET");
    if (name == "gap") return N_("PICKUP GAP");
    if (name == "swing") return N_("HAMMER SWING");
    if (name == "tonebar") return N_("TONE BAR");
    if (name == "pick") return N_("PICK");
    if (name == "strings") return N_("STRING AGE");
    return N_("PICKUP");
}
inline const char *voice_about(const std::string &name)
{
    if (name == "felt") return N_("The hammer felt's stiffness. Harder is brighter.");
    if (name == "felt_left") return N_("Soft felt over a worn hammer's hard layer. Thin, a hard blow reaches it and rings bright.");
    if (name == "strike") return N_("Where the hammer meets the string. Each place silences its own partials.");
    if (name == "unison") return N_("How far a note's strings are tuned apart.");
    if (name == "lid") return N_("The lid: shut is darker, open is brighter.");
    if (name == "board") return N_("The highest the soundboard radiates.");
    if (name == "tine") return N_("The tine's rest off the pickup's centre. Centred is a thin bell; off centre, warm with bark.");
    if (name == "reed") return N_("The reed's rest off the plate's slot. Further off, more bark at every touch.");
    if (name == "gap") return N_("The tine to the pickup. Closer is louder and barks sooner.");
    if (name == "swing") return N_("How far the hammer throws the tine or reed. Wider barks and buzzes.");
    if (name == "tonebar") return N_("The tone bar's ring in the attack: the bell.");
    if (name == "pick") return N_("Where the pick strikes the string. Near the bridge is bright and thin; toward the neck, round.");
    if (name == "strings") return N_("How fast the strings lose their highs. Fresh strings ring bright; old ones go dull."); 
    return N_("The piezo pickup's top.");
}

inline void draw_voice(App &a)
{
    VoiceUi &V = g_voice;
    if ((int)num(&V.st, "row", -1) != a.row) {
        J r = call(a, "{\"call\":\"voicing\",\"open\":1,\"row\":" + std::to_string(a.row) + "}");
        if (const J *p = r.get("voicing"))
            voice_take(a, *p);
    }
    const bool IP = a.tab, PH = a.ph;
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = PH ? 818 : IP ? 1113 : 1886, HY = PH ? 120 : IP ? 224 : 356;
    const float TX = heading(a, X0, HY, T("VOICE"), "voice");
    const J *ks = V.st.get("knobs");
    const std::string part = str(&V.st, "part");
    const bool building = num(&V.st, "building", 0) != 0;
    // (the part, and what is happening: a rebuild through a setting just made)
    {
        const float ty = PH ? HY - a.lh(14) * 0.5f : HY + 4;
        float x = TX + 16;
        text(a, a.font, 14, x, ty, SILK_DIM, part);
        x += text_w(a, a.font, 14, part) + 18;
        if (building && ImGui::GetTime() - V.acted < 30.0)     // (a program's own build is not the card's to tell)
            text(a, a.font, 14, x, ty, LCD, T("BUILDING THE NEW SOUND..."));
    }
    if (!ks || !ks->is(J::ARR) || ks->a.empty()) {
        const float y = PH ? 180 : IP ? 290 : 440;
        const auto ls = wrap(a, a.font, 21, T("This voice has no physical knobs yet. Pianos, electric pianos and electric guitars and basses have them first; other families follow."), X1 - X0 - 40);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 21, X0 + 20, y + i * (a.lh(21) + 4), SILK_DIM, ls[i]);
        return;
    }
    const int n = (int)ks->a.size();
    const float W = X1 - X0, cw = W / n;
    const float KS = PH ? 64 : IP ? 84 : 110;
    const float ky = PH ? 172 + KS / 2 : IP ? 300 + KS / 2 : 470 + KS / 2;
    bool any_own = false;
    const double now = ImGui::GetTime();
    for (int i = 0; i < n; i++) {
        const J &k = ks->a[(size_t)i];
        const int kn = (int)num(&k, "k", -1);
        const std::string name = str(&k, "name");
        double v = num(&k, "v", 0), lo = num(&k, "lo", 0), hi = num(&k, "hi", 1);
        const double cap = num(&k, "cap", 0);
        const bool lg = num(&k, "log", 0) != 0 && lo > 0;
        bool own = num(&k, "own", 0) != 0;
        auto mt = V.mine.find(kn);
        if (mt != V.mine.end()) {
            if (now < mt->second.second && std::fabs(mt->second.first - v) > 1e-9 * std::max(1.0, std::fabs(v))) {
                v = mt->second.first;
                own = true;
            } else
                V.mine.erase(mt);
        }
        any_own = any_own || own;
        auto to01 = [&](double x) {
            const double t = lg ? std::log(x / lo) / std::log(hi / lo) : (x - lo) / (hi - lo);
            return (float)std::max(0.0, std::min(1.0, t));
        };
        auto from01 = [&](float t) { return lg ? lo * std::pow(hi / lo, (double)t) : lo + (hi - lo) * t; };
        float v01 = to01(v);
        const std::string id = "voice_k" + name;
        const float cx = X0 + cw * (i + 0.5f);
        static std::map<int, float> drag;   // (a knob being turned: its position, the words follow it)
        auto dg = drag.find(kn);
        if (dg != drag.end())
            v01 = dg->second;
        const double shown = from01(v01);
        const int f = knob(a, id.c_str(), cx, ky, KS, v01, T(voice_label(name)),
                           voice_words(name, dg != drag.end() ? shown : v, cap), false, {}, cw - 10, own);
        if (f & K_ACTIVE)
            drag[kn] = v01;
        if ((f & K_ENDED) || ((f & K_CHANGED) && !(f & K_ACTIVE))) {
            const double nv = from01(v01);
            drag.erase(kn);
            V.mine[kn] = {nv, now + 4.0};
            V.acted = now;
            call(a, "{\"call\":\"voicing_set\",\"row\":" + std::to_string(a.row) + ",\"k\":" + std::to_string(kn) +
                        ",\"v\":" + jnum(nv) + "}");
        } else if (!(f & K_ACTIVE))
            drag.erase(kn);
        if (f & K_RESET) {
            drag.erase(kn);
            V.mine.erase(kn);
            V.acted = now;
            call(a, "{\"call\":\"voicing_forget\",\"row\":" + std::to_string(a.row) + ",\"k\":" + std::to_string(kn) + "}");
        }
        {                                   // (what it is, under it)
            const float ay = ky + KS / 2 + 14 + 2 * (a.lh(14) + 2) + (PH ? 6 : 10);
            const auto ls = wrap(a, a.font, 14, T(voice_about(name)), cw - 16);
            const float room = (PH ? card_y1(a) - 46 : IP ? card_y1(a) - 70 : 960) - ay;
            const size_t most = (size_t)std::max(1.0f, room / (a.lh(14) + 2));
            for (size_t j = 0; j < ls.size() && j < most; j++)
                text_c(a, a.font, 14, cx, ay + j * (a.lh(14) + 2), SILK_DIM, ls[j]);
        }
    }
    // (every knob back to the variation's, where any is the part's own)
    if (any_own) {
        const float bw = PH ? 200 : 260, bh = PH ? 40 : 46, by = PH ? card_y1(a) - bh : IP ? card_y1(a) - bh - 10 : 980;
        if (button(a, "voice_back", X1 - bw, by, bw, bh, T("ALL AS THE VOICE"), false, true, PH ? 14 : 21)) {
            V.acted = ImGui::GetTime();
            V.mine.clear();
            call(a, "{\"call\":\"voicing_forget\",\"row\":" + std::to_string(a.row) + ",\"k\":-1}");
        }
    }
}

}  // namespace nui
