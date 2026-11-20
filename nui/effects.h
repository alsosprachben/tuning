// THE EFFECTS CARD (ui/app.js's): the insertion effect (the Sound Canvas's
// EFX: one, for the parts put on it) -- its type by family, its parameters
// as knobs in Roland's own printed values, its sends -- and the system
// effects every part sends to (CC91, 93, 94) and the EQ. What a file sets
// comes back by the engine's effects push (while the card is open).
#pragma once

#include "app.h"
#include "library.h"
#include "widgets.h"

namespace nui {

// (a family's name as gsefx.CATEGORIES now says it -- an export made before
//  the shorter names still carries the long ones)
inline std::string fam_label(const std::string &n)
{
    static const std::map<std::string, std::string> M = {
        {"Tone colour (filters)", "Tone colour"}, {"Delay and reverb", "Delay, reverb"}, {"Two in series", "In series"},
        {"Three or more in series", "Multi-effects"}, {"Two in parallel", "In parallel"}};
    const auto it = M.find(n);
    return it == M.end() ? n : it->second;
}

struct FxParam {
    int n = 0, fresh = 0;
    std::string name;
    std::vector<int> vals;
    std::vector<std::string> shown;
};
struct FxType {
    int num = 0, msb = 0, lsb = 0;
    std::string name;
};
struct EffectsUi {
    bool open = false, tables = false;
    J e;                                // (effects_of: efx {msb, lsb, p, parts, send, why}, sys {rev, cho, dly, eq, room})
    std::vector<FxType> types;
    std::vector<std::pair<std::pair<int, int>, std::string>> fams;
    std::map<std::string, std::vector<FxParam>> params;   // "msb.lsb" -> its parameters
    int fam = -1;
    std::string about_of = "efx";
};
static EffectsUi g_fx;

inline void fx_tables(const J &t)
{
    EffectsUi &F = g_fx;
    F.tables = true;
    if (const J *fs = t.get("families"); fs && fs->is(J::ARR))
        for (const J &f : fs->a)
            F.fams.push_back({{(int)f.a[0].d(), (int)f.a[1].d()}, fam_label(f.a[2].s)});
    if (const J *ts = t.get("types"); ts && ts->is(J::ARR))
        for (const J &y : ts->a)
            F.types.push_back({(int)y.a[0].d(), (int)y.a[1].d(), (int)y.a[2].d(), y.a[3].s});
    if (const J *ps = t.get("params"); ps && ps->is(J::OBJ))
        for (const auto &kv : ps->o) {
            std::vector<FxParam> v;
            for (const J &p : kv.second.a) {
                FxParam q;
                q.n = (int)p.a[0].d();
                // (Roland's name; its manual's +/# marks for the effect controls left off,
                //  and "Hi" said as the EQ box says it)
                q.name = p.a[1].s;
                if (q.name.rfind("Hi ", 0) == 0)
                    q.name = "High " + q.name.substr(3);
                q.fresh = (int)p.a[3].d();
                for (const J &x : p.a[4].a)
                    q.vals.push_back((int)x.d());
                if (p.a.size() > 5 && p.a[5].is(J::ARR))
                    for (const J &x : p.a[5].a)
                        q.shown.push_back(x.is(J::STR) ? (x.s.rfind("+0 ", 0) == 0 || x.s == "+0" ? x.s.substr(1) : x.s) : "");
                v.push_back(q);
            }
            F.params[kv.first] = v;
        }
}
inline void fx_take(const J &r)
{
    if (const J *t = r.get("tables"))
        fx_tables(*t);
    if (const J *e = r.get("effects"))
        g_fx.e = *e;
}
inline void effects_card(App &a, bool open)
{
    EffectsUi &F = g_fx;
    if (open == F.open)
        return;
    F.open = open;
    fx_take(call(a, std::string("{\"call\":\"effects\",\"open\":") + (open ? "1" : "0") + ",\"tables\":" +
                        (F.tables ? "0" : "1") + "}"));
}

// what this screen just set stands a moment over the pushes
inline int fx_val(App &a, const std::string &key, int v)
{
    auto it = a.hold.find("fx:" + key);
    if (it != a.hold.end() && ImGui::GetTime() < it->second.second)
        return (int)it->second.first;
    return v;
}
inline void fx_mine(App &a, const std::string &key, int v) { a.hold["fx:" + key] = {(double)v, ImGui::GetTime() + 0.6}; }
inline void efx_send(App &a, const char *kind, int x, int y, const std::string &key = "")
{
    if (!key.empty())
        fx_mine(a, key, y);
    call(a, std::string("{\"call\":\"efx_send\",\"kind\":\"") + kind + "\",\"a\":" + std::to_string(x) + ",\"b\":" + std::to_string(y) + "}");
}
inline void sys_send(App &a, int hi, int lo, int v, const std::string &key)
{
    fx_mine(a, key, v);
    call(a, "{\"call\":\"sysfx_send\",\"hi\":" + std::to_string(hi) + ",\"lo\":" + std::to_string(lo) + ",\"v\":" + std::to_string(v) + "}");
}

// A KNOB OVER A LIST of values (each its own words): stepped by the list.
// Returns the flags; *picked the value moved to (else unchanged)
inline int list_knob(App &a, const std::string &id, float cx, float cy, float size, const std::vector<int> &vals,
                     const std::vector<std::string> &shown, int value, const std::string &label, bool centred, float lw,
                     int &picked, bool own = false)
{
    const int n = (int)vals.size();
    int idx = 0;
    for (int i = 0; i < n; i++)
        if (vals[(size_t)i] == value)
            idx = i;
    float v01 = n > 1 ? (float)idx / (n - 1) : 0;
    const std::string say = idx < (int)shown.size() ? shown[(size_t)idx] : std::to_string(n ? vals[(size_t)idx] : 0);
    int f = knob(a, id.c_str(), cx, cy, size, v01, label, say, centred, centred ? std::vector<float>{0.5f} : std::vector<float>{}, lw, own,
                 false);
    picked = value;
    if ((f & K_CHANGED) && n > 1) {
        const int i = (int)std::lround(v01 * (n - 1));
        picked = vals[(size_t)std::max(0, std::min(n - 1, i))];
    }
    // (a long-press: the value as its list numbers it, typed; the nearest taken)
    const std::string sk = id + "#list";
    if ((f & K_LONG) && n)
        open_sheet(a, sk, label.empty() ? std::string("Value") : label, say, vals[(size_t)idx], vals.front(), vals.back(), 0, "Value",
                   shown.empty() ? "" : "The number the module stores for it; the nearest one is taken.");
    double t;
    const int sf = take_sheet(a, sk, t);
    if ((sf & K_CHANGED) && n) {
        size_t best = 0;
        for (size_t i = 0; i < vals.size(); i++)
            if (std::fabs(vals[i] - t) < std::fabs(vals[best] - t))
                best = i;
        picked = vals[best];
        f |= K_CHANGED;
    }
    return f | (sf & K_RESET);
}
inline std::vector<int> irange(int lo, int hi)
{
    std::vector<int> v;
    for (int i = lo; i <= hi; i++)
        v.push_back(i);
    return v;
}
// (the most columns, up to most, in which every name fits its button whole)
inline int grid_cols(App &a, const std::vector<std::string> &names, float w, int most, float gap = 4)
{
    for (int c = most; c > 1; c--) {
        const float bw = (w - gap * (c - 1)) / c;
        bool ok = true;
        for (const auto &n : names)
            ok = ok && text_w(a, a.font, 14, n) <= bw - 12;
        if (ok)
            return c;
    }
    return 1;
}
// a row of choices: n buttons in a grid of cols; the lit one i
inline int choice_grid(App &a, const std::string &id, float x, float y, float w, int cols, float bh,
                       const std::vector<std::string> &names, int lit, float gap = 4)
{
    const float bw = (w - gap * (cols - 1)) / cols;
    int hit = -1;
    for (size_t i = 0; i < names.size(); i++) {
        const float bx = x + (i % cols) * (bw + gap), by = y + (i / cols) * (bh + gap);
        const std::string bid = id + std::to_string(i);
        ImGui::SetCursorScreenPos(P(a, bx, by));
        if (ImGui::InvisibleButton(bid.c_str(), ImVec2(bw * a.k, bh * a.k)))
            hit = (int)i;
        const bool on = (int)i == lit;
        look::chip(a, bx, by, bw, bh, on, ImGui::IsItemActive());
        text(a, a.font, 14, bx + 7, by + (bh - 14) / 2, on ? LCD_BG : SILK, fit(a, a.font, 14, names[i], bw - 12));
    }
    return hit;
}

inline void draw_effects(App &a)
{
    EffectsUi &F = g_fx;
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    // (the iPad's: its card from y 210 to card_y1 + 6, three pages -- the insertion's type, its parameters, the system effects)
    const bool IP = a.tab;
    static int page = 0;
    const bool show_type = !IP || page == 0, show_par = !IP || page == 1, show_sys = !IP || page == 2;
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, Y0 = IP ? 266 : 394, HY = IP ? 224 : 356, Y1 = card_y1(a);
    const float GH = IP ? 44 : 28, GR = GH + 4, LH = a.lh(14) + (IP ? 3 : 4);    // (a choice's height, its row)
    const float TX = heading(a, X0, HY, "EFFECTS", "effects");
    const J *p = part(a, a.row);
    if (p)
        text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, "part " + pad2(a.row + 1) + " \xc2\xb7 " + str(p, "name"), IP ? 160 : 900));
    if (IP)
        for (int pg = 0; pg < 3; pg++) {
            static const char *PN[3] = {"TYPE", "PARAMETERS", "SYSTEM"};
            const std::string id = "fxpage" + std::to_string(pg);
            if (button(a, id.c_str(), 340 + pg * 196, 216, 190, 44, PN[pg], page == pg, true, 21))
                page = pg;
        }
    const J *x = F.e.get("efx"), *y = F.e.get("sys");
    if (!x || !F.tables)
        return;
    const float aboutH = IP ? 30 : 44, YB = IP ? (page == 0 ? Y1 - aboutH - 8 : Y1) : Y1 - aboutH - 8;

    // THE INSERTION EFFECT
    const float IW = IP ? X1 - X0 : 780, IX = X0;
    if (show_type || show_par) {
    look::tray(a, IX, Y0, IW, YB - Y0, 9);
    }
    const int msb = (int)num(x, "msb"), lsb = (int)num(x, "lsb");
    const std::string key = std::to_string(msb) + "." + std::to_string(lsb);
    const FxType *type = nullptr;
    for (const FxType &t : F.types)
        if (t.msb == msb && t.lsb == lsb)
            type = &t;
    if (show_type || show_par) {
    const float ix = heading(a, IX + 12, Y0 + 12, "INSERTION EFFECT", "fx:ins");
    text(a, a.font, 21, ix, Y0 + (IP ? 10 : 8), LCD, type ? pad2(type->num) + " " + type->name : "00 Thru");
    // this part on it (every channel the part plays)
    std::vector<int> chans;
    const int pch = p ? (int)num(p, "channel", -1) : 0;
    if (pch < 0)
        chans = irange(0, 15);
    else
        chans = {pch};
    std::vector<int> on_it;
    if (const J *ps = x->get("parts"); ps && ps->is(J::ARR))
        for (const J &c : ps->a)
            on_it.push_back((int)c.d());
    bool on = true;
    for (int c : chans)
        on = on && std::find(on_it.begin(), on_it.end(), c) != on_it.end();
    if (button(a, "fxon", IX + IW - 222, Y0 + 6, 210, IP ? 44 : 34, "THIS PART ON IT", on, true, IP ? 21 : 14)) {
        for (int c : chans)
            efx_send(a, "c", c, on ? 0 : 1);
        std::vector<int> nv;
        for (int c : on_it)
            if (on ? std::find(chans.begin(), chans.end(), c) == chans.end() : true)
                nv.push_back(c);
        if (!on)
            for (int c : chans)
                if (std::find(nv.begin(), nv.end(), c) == nv.end())
                    nv.push_back(c);
        J arr = sess::arr();
        for (int c : nv)
            arr.a.push_back(sess::integer(c));
        F.e.o["efx"].o["parts"] = arr;  // (at once: the push confirms it)
    }
    std::string pl;
    for (int c : on_it)
        if (c < 16)
            pl += (pl.empty() ? "" : ", ") + std::to_string(c + 1);
    std::string pt = pl.empty() ? "No part is on it yet." : "On it: channel" + std::string(pl.find(',') != std::string::npos ? "s " : " ") + pl + ".";
    if (!str(x, "why").empty())
        pt += " Not played live: " + str(x, "why") + ".";
    text(a, a.font, 14, IX + 12, Y0 + (IP ? 32 : 46), SILK_DIM, fit(a, a.font, 14, pt, IW - (IP ? 260 : 24)));
    }
    // the families, then the family's types
    if (F.fam < 0) {
        F.fam = 0;
        if (type)
            for (size_t i = 0; i < F.fams.size(); i++)
                if (type->num >= F.fams[i].first.first && type->num <= F.fams[i].first.second)
                    F.fam = (int)i;
    }
    std::vector<std::string> fn;
    for (const auto &f : F.fams)
        fn.push_back(f.second);
    const float fy = Y0 + (IP ? 60 : 72);
    const int fcols = grid_cols(a, fn, IW - 24, IP ? 6 : 4);
    const int hf = show_type ? choice_grid(a, "fxfam", IX + 12, fy, IW - 24, fcols, GH, fn, F.fam) : -1;
    if (hf >= 0)
        F.fam = hf;
    std::vector<const FxType *> shown;
    std::vector<std::string> tn = {"00 Thru"};
    int lit = type ? -1 : 0;
    for (const FxType &t : F.types)
        if (t.num >= F.fams[(size_t)F.fam].first.first && t.num <= F.fams[(size_t)F.fam].first.second) {
            if (&t == type)
                lit = (int)shown.size() + 1;
            shown.push_back(&t);
            tn.push_back(pad2(t.num) + " " + t.name);
        }
    const float ty = fy + ((int)fn.size() + fcols - 1) / fcols * GR + (IP ? 8 : 10);
    const int tcols_ = grid_cols(a, tn, IW - 24, 4);
    const int ht = show_type ? choice_grid(a, "fxtype", IX + 12, ty, IW - 24, tcols_, GH, tn, lit) : -1;
    if (ht == 0)
        efx_send(a, "t", 0, 0);
    else if (ht > 0)
        efx_send(a, "t", shown[(size_t)ht - 1]->msb, shown[(size_t)ht - 1]->lsb);
    if (ht >= 0) {
        F.about_of = "efx";
        F.e.o["efx"].o["msb"] = sess::integer(ht ? shown[(size_t)ht - 1]->msb : 0);
        F.e.o["efx"].o["lsb"] = sess::integer(ht ? shown[(size_t)ht - 1]->lsb : 0);
    }
    // its parameters, and its sends (a column at the right)
    // (the knobs under the tallest family's types, so they stay put from family to family)
    int trows_max = 1;
    for (const auto &fm : F.fams) {
        std::vector<std::string> names = {"00 Thru"};
        for (const FxType &t : F.types)
            if (t.num >= fm.first.first && t.num <= fm.first.second)
                names.push_back(pad2(t.num) + " " + t.name);
        const int c = grid_cols(a, names, IW - 24, 4);
        trows_max = std::max(trows_max, ((int)names.size() + c - 1) / c);
    }
    const float ky0 = IP ? Y0 + 64 : ty + trows_max * GR + 14, kh = YB - ky0 - 8;
    const auto pit = F.params.find(key);
    const float SW_ = IP ? 140 : 112, PW = IW - 24 - SW_;
    if (!show_par) {
    } else if (pit == F.params.end() || pit->second.empty()) {
        rect(a, IX + 12, ky0 - 8, IW - 24, 1, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
        text(a, a.font, 14, IX + 12, ky0 + 6, SILK_DIM, "Thru: the parts on it play dry. Choose a type.");
    } else {
        rect(a, IX + 12, ky0 - 8, IW - 24, 1, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
        const auto &ps = pit->second;
        // (a Rotary type: one more cell, the part's ROOM / MICS -- how it is heard)
        const bool rotary = type && type->name.find("Rotary") != std::string::npos;
        const int cells = (int)ps.size() + (rotary ? 1 : 0);
        // (seven across, or six where that adds no row: wider cells for the labels)
        const int cols = cells > 7 && (cells + 5) / 6 == (cells + 6) / 7 ? 6 : 7, rows = std::max(1, (cells + cols - 1) / cols);
        const float cw = PW / cols, ch = std::min(IP ? 120.0f : 110.0f, kh / rows);
        const J *pv_ = x->get("p");
        for (size_t i = 0; i < ps.size(); i++) {
            const FxParam &q = ps[i];
            const int ev = pv_ && pv_->is(J::ARR) && q.n < (int)pv_->a.size() ? (int)pv_->a[(size_t)q.n].d() : -1;
            const int v = fx_val(a, "p" + std::to_string(q.n), ev >= 0 ? ev : q.fresh);
            const float cx = IX + 12 + (i % cols + 0.5f) * cw, cy = ky0 + (i / cols) * ch + 26;
            int picked;
            const int f = list_knob(a, "fxp" + std::to_string(q.n), cx, cy, IP ? 48 : 40, q.vals, q.shown, v, q.name, false, cw - 6, picked);
            if (f & K_ACTIVE)
                F.about_of = "efx";
            if (picked != v)
                efx_send(a, "p", q.n, picked, "p" + std::to_string(q.n));
            if (f & K_RESET)
                efx_send(a, "p", q.n, q.fresh, "p" + std::to_string(q.n));
        }
        if (rotary) {                   // THE ROTARY HEARD (the part's: the Stops card's switch too)
            const int i = (int)ps.size();
            const float cx = IX + 12 + (i % cols + 0.5f) * cw, cy = ky0 + (i / cols) * ch;
            const J *rv = p ? p->get("rotary") : nullptr;
            int mode = rv && rv->is(J::ARR) && rv->a.size() >= 2 ? (int)rv->a[0].d() : -1;
            const double spread = rv && rv->is(J::ARR) && rv->a.size() >= 2 ? rv->a[1].d() : -1.0;
            auto ht = a.hold.find("rotary");
            if (ht != a.hold.end() && ImGui::GetTime() < ht->second.second)
                mode = (int)std::floor(ht->second.first / 1000.0);
            const bool room = mode == 0;    // (a Rotary type's own way: two mics)
            const float bw = std::min(cw - 8, IP ? 110.0f : 88.0f), bh = IP ? 40 : 32;
            text_c(a, a.font, 14, cx, cy - 2, SILK_DIM, "HEARD");
            auto set = [&](int m) {
                a.hold["rotary"] = {m * 1000.0 + (spread < 0 ? 0.0 : spread + 1.0), ImGui::GetTime() + 0.6};
                call(a, "{\"call\":\"rotary_set\",\"row\":" + std::to_string(a.row) + ",\"mode\":" + std::to_string(m)
                            + ",\"spread\":" + jnum(spread) + "}");
            };
            if (button(a, "fxrroom", cx - bw / 2, cy + 16, bw, bh, "ROOM", room))
                set(0);
            if (button(a, "fxrmics", cx - bw / 2, cy + 20 + bh, bw, bh, "MICS", !room))
                set(1);
        }
        const float sx = IX + IW - 12 - SW_;
        rect(a, sx, ky0 - 4, 1, kh, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
        heading(a, sx + SW_ / 2 - 40, ky0 - 2, "SENDS", "fx:sends");
        static const char *SN[3] = {"Reverb", "Chorus", "Delay"};   // (under SENDS: to each)
        const J *sd = x->get("send");
        const float sh = (kh - 20) / 3;
        for (int i = 0; i < 3; i++) {
            const int ev = sd && sd->is(J::ARR) && i < (int)sd->a.size() ? (int)sd->a[(size_t)i].d() : 0;
            const int v = fx_val(a, "s" + std::to_string(i), ev);
            int picked;
            list_knob(a, "fxs" + std::to_string(i), sx + SW_ / 2, ky0 + 20 + i * sh + 22, IP ? 44 : 36, irange(0, 127), {}, v, SN[i], false, SW_ - 6, picked);
            if (picked != v)
                efx_send(a, "s", 0x17 + i, picked, "s" + std::to_string(i));
        }
    }

    // THE SYSTEM EFFECTS: reverb, chorus, delay, EQ (GS 40 01 3x/5x, 40 02 0x), two by two
    if (y && show_sys) {
        static const std::vector<std::string> REV = {"Room 1", "Room 2", "Room 3", "Hall 1", "Hall 2", "Plate", "Delay", "Pan Delay"};
        static const std::vector<std::string> CHO = {"Chorus 1", "Chorus 2", "Chorus 3", "Chorus 4", "FB Chorus", "Flanger", "Short Delay", "Short Delay FB"};
        static const std::vector<std::string> DLY = {"Delay 1", "Delay 2", "Delay 3", "Delay 4", "Pan Delay 1", "Pan Delay 2", "Pan Delay 3", "Pan Delay 4", "Delay to Rev", "Pan Repeat"};
        struct Kn {
            const char *name;
            int lo, v, a, z;
        };
        struct Box {
            const char *id, *name, *cc;
            const std::vector<std::string> *types;
            int type, lo;
            std::vector<Kn> knobs;
        };
        auto at = [&](const char *k, size_t i) {
            const J *v = y->get(k);
            return v && v->is(J::ARR) && i < v->a.size() ? (int)v->a[i].d() : 0;
        };
        std::vector<Box> boxes = {
            {"rev", "REVERB", "CC91", &REV, at("rev", 0), 0x30, {{"Level", 0x33, at("rev", 1), 0, 127}, {"Time", 0x34, at("rev", 2), 0, 127}}},
            {"cho", "CHORUS", "CC93", &CHO, at("cho", 0), 0x38,
             {{"Pre-LPF", 0x39, at("cho", 1), 0, 7}, {"Level", 0x3A, at("cho", 2), 0, 127}, {"Feedback", 0x3B, at("cho", 3), 0, 127},
              {"Delay", 0x3C, at("cho", 4), 0, 127}, {"Rate", 0x3D, at("cho", 5), 0, 127}, {"Depth", 0x3E, at("cho", 6), 0, 127}}},
            {"dly", "DELAY", "CC94", &DLY, at("dly", 0), 0x50,
             {{"Pre-LPF", 0x51, at("dly", 1), 0, 7}, {"Time", 0x52, at("dly", 2), 1, 0x73}, {"Ratio L", 0x53, at("dly", 3), 1, 0x78},
              {"Ratio R", 0x54, at("dly", 4), 1, 0x78}, {"Level C", 0x55, at("dly", 5), 0, 127}, {"Level L", 0x56, at("dly", 6), 0, 127},
              {"Level R", 0x57, at("dly", 7), 0, 127}, {"Level", 0x58, at("dly", 8), 0, 127}, {"Feedback", 0x59, at("dly", 9), 0, 127}}},
        };
        if (at("rev", 3) >= 0)
            boxes[0].knobs.push_back({"Feedback", 0x35, at("rev", 3), 0, 127});
        // (the top row shorter: the reverb's and chorus's knobs one row each; the delay's two)
        const float SX0 = IP ? X0 : IX + IW + 8, BW = (X1 - SX0 - 8) / 2, BH1 = IP ? 238 : 322;
        for (int bi = 0; bi < 4; bi++) {
            // (each column its own split: the reverb short over a tall delay, the chorus tall over the EQ)
            const float top_h = IP ? BH1 : (bi % 2 == 0 ? 214.0f : BH1);
            const float bx = SX0 + (bi % 2) * (BW + 8), by = bi < 2 ? Y0 : Y0 + top_h + 8,
                        BH = bi < 2 ? top_h : YB - by;
            look::tray(a, bx, by, BW, BH, 9);
            if (bi == 3) {   // THE EQ, of the whole mix
                text(a, a.font, 14, heading(a, bx + 12, by + 10, "EQ", "fx:eq"), by + 11, LCD, "the whole mix");
                std::vector<std::string> gsh;
                for (int g = 0x34; g <= 0x4C; g++)
                    gsh.push_back((g - 0x40 > 0 ? "+" : "") + std::to_string(g - 0x40) + " dB");
                struct Eq {
                    const char *name;
                    std::vector<int> vals;
                    std::vector<std::string> shown;
                    bool centred;
                } EQ[4] = {{"Low", {0, 1}, {"200 Hz", "400 Hz"}, false},
                           {"Low gain", irange(0x34, 0x4C), gsh, true},
                           {"High", {0, 1}, {"3 kHz", "6 kHz"}, false},
                           {"High gain", irange(0x34, 0x4C), gsh, true}};
                const float cw = (BW - 24) / 4;
                for (int k = 0; k < 4; k++) {
                    const int v = fx_val(a, "eq" + std::to_string(k), at("eq", (size_t)k));
                    int picked;
                    const int f = list_knob(a, "eq" + std::to_string(k), bx + 12 + (k + 0.5f) * cw, by + (IP ? 80 : 90), 52, EQ[k].vals,
                                            EQ[k].shown, v, EQ[k].name, EQ[k].centred, cw - 6, picked);
                    if (f & K_ACTIVE)
                        F.about_of = "eq";
                    if (picked != v)
                        sys_send(a, 2, k, picked, "eq" + std::to_string(k));
                }
                continue;
            }
            const Box &b = boxes[(size_t)bi];
            text(a, a.font, 14, heading(a, bx + 12, by + 10, b.name, std::string("fx:") + b.id), by + 11, LCD, b.cc);
            const int tv = fx_val(a, std::string(b.id) + "type", b.type);
            const int tcols = IP ? (bi == 2 ? 5 : 4) : bi == 0 ? 4 : bi == 1 ? 2 : 3;     // (the chorus's and delay's names are longer)
            const int th = choice_grid(a, std::string("st") + b.id, bx + 12, by + 34, BW - 24, tcols, IP ? GH : 26, *b.types, tv);
            if (th >= 0) {
                sys_send(a, 1, b.lo, th, std::string(b.id) + "type");
                F.about_of = b.id;
            }
            const int trows = ((int)b.types->size() + tcols - 1) / tcols;
            float ky = by + 34 + trows * (IP ? GR : 30) + 6;
            if (bi == 0 && b.type < 0) {
                for (const auto &l : wrap(a, a.font, 14, "No GS reverb set: the room is the panel's, " + str(y, "room") + ".", BW - 24)) {
                    text(a, a.font, 14, bx + 12, ky, SILK_DIM, l);
                    ky += LH;
                }
            }
            const int cols = IP && bi == 2 ? 9 : bi == 1 ? (IP ? 6 : 3) : 5, rows = ((int)b.knobs.size() + cols - 1) / cols;
            const float cw = (BW - 24) / cols, chh = (by + BH - ky) / std::max(1, rows);
            for (size_t k = 0; k < b.knobs.size(); k++) {
                const Kn &kn = b.knobs[k];
                const std::string kid = std::string(b.id) + std::to_string(kn.lo);
                const int v = fx_val(a, kid, kn.v);
                int picked;
                const int f = list_knob(a, kid, bx + 12 + (k % cols + 0.5f) * cw, ky + (k / cols) * chh + (IP ? 24 : 22), IP ? 44 : 36,
                                        irange(kn.a, kn.z), {}, v, kn.name, false, cw - 6, picked);
                if (f & K_ACTIVE)
                    F.about_of = b.id;
                if (picked != v)
                    sys_send(a, 1, kn.lo, picked, kid);
            }
        }
    }

    // WHAT IT IS: the insertion type's line, or the system effect touched's (on the iPad, with the type)
    if (!show_type)
        return;
    const float ay = Y1 - aboutH, aw = X1 - X0;
    look::tray(a, X0, ay, aw, aboutH, 8);
    std::string title, body;
    if (F.about_of == "efx") {
        if (!type) {
            text(a, a.font, 14, X0 + 12, ay + (aboutH - a.lh(14)) / 2, LCD_DIM, "Touch a type for what it is.");
            return;
        }
        title = type->name;
        if (const J *ef = L.about.get("efx"))
            body = str(ef, type->name.c_str());
    } else {
        static const std::map<std::string, std::pair<const char *, const char *>> N = {
            {"rev", {"Reverb", "Reverb (system)"}}, {"cho", {"Chorus", "Chorus (system)"}},
            {"dly", {"Delay", "Delay (system)"}}, {"eq", {"EQ", "EQ (system)"}}};
        const auto &nn = N.at(F.about_of);
        title = nn.first;
        if (const J *ef = L.about.get("effects"))
            body = str(ef, nn.second);
    }
    const float ly = ay + (aboutH - a.lh(14)) / 2;
    text(a, a.bold, 14, X0 + 12, ly, SILK, title);
    text(a, a.font, 14, X0 + 12 + text_w(a, a.bold, 14, title) + 14, ly, SILK_DIM, body);
}

}  // namespace nui
