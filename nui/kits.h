// THE KITS CARD: the drum library beside the pads (Ben 2026-11-26: "a drum
// library card separate from the drum buttons") -- the kits, a tap putting
// one on the selected part; the kit's keys, a tap playing one; and the key:
// what it is (about.json's notes), or, on a user set (GS's two), where its
// sound comes from and its own pitch, level, pan and mute (GS 21's 01, 02,
// 04, 08 -- the settings the engine honours; its sends, group and note-off
// switch it does not, so they are not offered). Shares the DRUMS card's
// state (drums.h: the kit's keys, the key last touched).
#pragma once

#include "drums.h"

namespace nui {

struct KitsUi {
    std::map<std::string, float> scroll;
    bool edited = false;                // (a value changed by a drag: the key struck when it ends)
};
static KitsUi g_kits;

inline void draw_kits(App &a)
{
    DrumsUi &D = g_drums;
    KitsUi &KU = g_kits;
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    if ((int)num(&D.d, "row", -1) != a.row) {
        J r = call(a, "{\"call\":\"drums\",\"open\":1,\"sets\":" + std::string(D.sets.is(J::ARR) ? "0" : "1") + "}");
        if (const J *x = r.get("drums"))
            drums_take(a, *x);
    }
    const bool IP = a.tab, PH = a.ph;
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = IP ? (PH ? 818 : 1113) : 1886, HY = PH ? 120 : IP ? 224 : 356;
    const float Y0 = PH ? 160 : IP ? 262 : 404, Y1 = card_y1(a) - (PH ? 2 : 0);
    const float TX = heading(a, X0, HY, T("KITS"), "kits");
    if (!D.d.is(J::OBJ))
        return;
    const std::string part_name = str(&D.d, "part");
    const bool drums = flag(&D.d, "drums"), user = D.d.get("user") != nullptr;
    const int kit = (int)num(&D.d, "kit", -1);
    const float bh = PH ? 40 : 44, by = PH ? HY - 8 : HY - 10, B = 21;
    float bx = X1;
    {
        const std::string lab = T("DRUMS \xe2\x96\xb8");
        const float w = text_w(a, a.bold, B, lab) + 28;
        bx -= w;
        if (button(a, "ktpads", bx, by, w, bh, lab, false, true, B))
            a.card = "drums";
        bx -= 8;
    }
    {
        std::string sub = TF("part {0} \xc2\xb7 {1}", {pad2(a.row + 1), part_name});
        if (drums) {
            const int ch = (int)num(&D.d, "channel", -1);
            sub += " \xc2\xb7 " + TF("channel {0}", {std::to_string(ch < 0 ? 10 : ch + 1)});
        }
        text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, sub, bx - TX - 4));
    }
    auto strike = [&](int key) {
        call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(key) + ",\"v\":100}");
        call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(key) + ",\"v\":0}");
    };

    // THE KITS: a tap puts one on the part
    const float KW = PH ? 178 : IP ? 220 : 300, KL = PH ? 232 : IP ? 300 : 440, gap = PH ? 8 : 12;
    const float KR = IP ? 48 : 40, KB = IP ? 44 : 36;   // (a row; its chip)
    std::vector<const Patch *> kits;
    for (const Patch &p : L.patches)
        if (p.drums)
            kits.push_back(&p);
    {
        const int tap = scroll_list(a, "kits", X0, Y0, KW, Y1 - Y0, (int)kits.size(), KR, KU.scroll["kits"], [&](int i, float y) {
            const Patch &p = *kits[(size_t)i];
            const bool cur = p.program == kit && drums;
            const bool pend = L.picking == p.pick;
            look::chip(a, X0, y, KW - 8, KB, cur);
            if (pend)
                frame(a, X0, y, KW - 8, KB, LCD, 6, 1.5f);
            const float ty = y + (KB - a.lh(14)) / 2, nx = IP ? 36 : 50;
            text(a, a.font, 14, X0 + 8, ty, cur ? LCD_BG : LCD, std::to_string(p.program));
            text(a, a.font, 14, X0 + nx, ty, cur ? LCD_BG : SILK, fit(a, a.font, 14, p.name, KW - nx - 16));
        });
        if (tap >= 0) {
            L.picking = kits[(size_t)tap]->pick;
            call(a, "{\"call\":\"part_pick\",\"row\":" + std::to_string(a.row) + ",\"pick\":" + std::to_string(L.picking) + "}");
        }
        if (L.picking >= 0 && drums)
            for (const Patch *p : kits)
                if (p->pick == L.picking && p->program == kit)
                    L.picking = -1;
    }
    const float LX = X0 + KW + gap, DX = LX + KL + gap, DW = X1 - DX;
    if (!drums) {
        const auto ls = wrap(a, a.font, 21, TF("{0} is not a drum set. Choose a kit for part {1} from the list.",
                                               {part_name.empty() ? std::string(T("This part")) : part_name, pad2(a.row + 1)}), X1 - LX - 20);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 21, LX + 10, Y0 + 10 + i * (a.lh(21) + 6), SILK_DIM, ls[i]);
        return;
    }

    // THE KIT's KEYS: a tap chooses one, and plays it
    std::vector<const DrumKey *> shown;
    for (const auto &k : D.keys)
        if (!user || (k.key >= 27 && k.key <= 87) || !k.name.empty())
            shown.push_back(&k);
    {
        const int tap = scroll_list(a, "kitkeys", LX, Y0, KL, Y1 - Y0, (int)shown.size(), KR, KU.scroll["kitkeys"], [&](int i, float y) {
            const DrumKey &k = *shown[(size_t)i];
            const bool on = D.sel == k.key, unset = user && k.name.empty();
            look::chip(a, LX, y, KL - 8, KB, on);
            const float ty = y + (KB - a.lh(14)) / 2;
            const std::string nn = note_name_sharp(k.key), kk = std::to_string(k.key);
            const float nw = IP ? 52 : 58, kw = IP ? 34 : 38;
            text(a, a.bold, 14, LX + 8, ty, on ? LCD_BG : LCD, nn);
            text(a, a.font, 14, LX + 8 + nw, ty, on ? LCD_BG : SILK_DIM, kk);
            text(a, a.font, 14, LX + 8 + nw + kw, ty, on ? LCD_BG : unset ? SILK_DIM : SILK,
                 fit(a, a.font, 14, unset ? std::string(T("not set")) : k.name, KL - nw - kw - 24));
        });
        if (tap >= 0) {
            const int k = shown[(size_t)tap]->key;
            if (D.sel != k)
                D.browse = -1;
            D.sel = D.touched = k;
            strike(k);
        }
    }

    // THE KEY: what it is; a user set's, its sound and its own settings
    look::tray(a, DX, Y0, DW, Y1 - Y0, 9);
    const float LH = a.lh(14) + (IP ? 3 : 4), PX = DX + 12, PW = DW - 24;
    if (D.sel < 0) {
        const auto ls = wrap(a, a.font, 14, T("Choose a key, here or on the pads, for what it is."), PW);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, PX, Y0 + 12 + i * LH, LCD_DIM, ls[i]);
        return;
    }
    DrumKey *ep = nullptr;
    for (auto &k : D.keys)
        if (k.key == D.sel)
            ep = &k;
    DrumKey e0;
    e0.key = D.sel;
    DrumKey &e = ep ? *ep : e0;
    float y = Y0 + 10;
    if (!user) {
        for (const auto &l : wrap(a, a.bold, 14, note_name_sharp(e.key) + "  " + std::to_string(e.key) + "  " + e.name, PW)) {
            text(a, a.bold, 14, PX, y, SILK, l);
            y += LH;
        }
        const J *rn = drum_note(L.about, kit, e.key);
        const std::string w = rn && rn->is(J::STR) ? rn->s : std::string(T("its own sound"));
        for (const auto &l : wrap(a, a.font, 14, w, PW)) {
            if (y + LH > Y1)
                break;
            text(a, a.font, 14, PX, y + 4, w.rfind("stand-in", 0) == 0 ? LCD : SILK_DIM, l);   // i18n-skip (the engine's note, compared)
            y += LH;
        }
        return;
    }
    // (a user set's key)
    const int u = (int)num(&D.d, "user");
    auto usend = [&](int code, int v) {
        call(a, "{\"call\":\"udrum_set\",\"set\":" + std::to_string(u) + ",\"key\":" + std::to_string(D.sel) +
                    ",\"code\":" + std::to_string(code) + ",\"v\":" + std::to_string(v) + "}");
    };
    const int ss = e.skey >= 0 ? e.set : -1;
    std::string ssname = TF("set {0}", {std::to_string(ss)});
    if (D.sets.is(J::ARR))
        for (const J &x : D.sets.a)
            if ((int)x.a[0].d() == ss)
                ssname = x.a[1].s;
    {
        const float kx = heading(a, PX, y, TF("KEY {0}", {note_name_sharp(D.sel)}), "drums:user");   // i18n-skip (a help key)
        text(a, a.font, 14, kx, y, LCD, std::to_string(D.sel));
        y += std::max(LH, 22.0f) + 6;     // (past the heading's ? ring)
        text(a, a.font, 14, PX, y, SILK_DIM,
             fit(a, a.font, 14, e.skey >= 0 ? TF("Plays {0} from {1}.", {e.name, ssname}) : std::string(T("No sound yet: choose one below.")), PW));
        y += LH + 4;
    }
    if (e.skey >= 0) {                  // (its own settings, once it has a sound)
        const float fh = PH ? 44 : IP ? 46 : 52, fg = 6, fw = (PW - 3 * fg) / 4;
        bool ended = false;
        auto fld = [&](const char *id, float fx, int code, int &val, int dflt, int lo, int hi, int off, const std::string &label,
                       const std::string &shown_) {
            float v = (float)(val >= 0 ? val - off : dflt);
            const int f = lcd_field(a, id, fx, y, fw, fh, v, (float)lo, (float)hi, label, shown_, false);
            if ((f & K_CHANGED) && (int)v + off != val) {
                val = (int)v + off;
                usend(code, val);
                KU.edited = true;
                if (!(f & K_ACTIVE))
                    ended = true;
            }
            if (f & K_ENDED)
                ended = true;
        };
        const int pitch = e.play >= 0 ? e.play - e.skey : 0;
        fld("ktpitch", PX, 0x01, e.play, 0, std::max(-24, -e.skey), std::min(24, 127 - e.skey), e.skey, T("PITCH"), signed_text(pitch));
        fld("ktlevel", PX + fw + fg, 0x02, e.level, 127, 0, 127, 0, T("LEVEL"),
            e.level >= 0 ? std::to_string(e.level) : std::string("\xe2\x80\x94"));
        fld("ktpan", PX + 2 * (fw + fg), 0x04, e.pan, 64, 0, 127, 0, T("PAN"),
            e.pan < 0 ? std::string("\xe2\x80\x94") : e.pan == 0 ? std::string(T("random")) : pan_text(e.pan));
        if (button(a, "ktmute", PX + 3 * (fw + fg), y, fw, fh, T("MUTE"), e.rxon == 0, true)) {
            e.rxon = e.rxon == 0 ? 1 : 0;
            usend(0x08, e.rxon);
        }
        if (ended && KU.edited) {
            KU.edited = false;
            strike(D.sel);
        }
        y += fh + 10;
    }
    // ...and where its sound comes from: a set, then its key
    if (!D.sets.is(J::ARR))
        return;
    const int bs = D.browse >= 0 ? D.browse : ss;
    const J *set = nullptr;
    for (const J &x : D.sets.a)
        if ((int)x.a[0].d() == bs)
            set = &x;
    y += 4;
    text(a, a.bold, 14, PX, y, SILK_DIM, T("ITS SOUND FROM"));
    y += LH;
    const float lh = Y1 - 8 - y, cw = (PW - 8) / 2, LR = IP ? 48 : 30, LB = IP ? 44 : 27;
    const int ns = (int)D.sets.a.size();
    const int ts = scroll_list(a, "uksets", PX, y, cw, lh, ns, LR, KU.scroll["uksets"], [&](int i, float yy) {
        const J &x = D.sets.a[(size_t)i];
        const bool on = (int)x.a[0].d() == bs;
        look::chip(a, PX, yy, cw - 8, LB, on);
        text(a, a.font, 14, PX + 6, yy + (LB - a.lh(14)) / 2, on ? LCD_BG : SILK, fit(a, a.font, 14, x.a[1].s, cw - 20));
    });
    if (ts >= 0)
        D.browse = (int)D.sets.a[(size_t)ts].a[0].d();
    const float kx0 = PX + cw + 8;
    if (!set) {
        text(a, a.font, 14, kx0, y + 6, SILK_DIM, T("Choose a set."));
        return;
    }
    const J &sk = set->a[2];
    const int tk = scroll_list(a, "ukkeys", kx0, y, cw, lh, (int)sk.a.size(), LR, KU.scroll["ukkeys"], [&](int i, float yy) {
        const J &x = sk.a[(size_t)i];
        const bool on = (int)set->a[0].d() == ss && (int)x.a[0].d() == e.skey;
        look::chip(a, kx0, yy, cw - 8, LB, on);
        const std::string nn = note_name_sharp((int)x.a[0].d());
        text(a, a.bold, 14, kx0 + 6, yy + (LB - a.lh(14)) / 2, on ? LCD_BG : SILK, nn);
        text(a, a.font, 14, kx0 + 22 + text_w(a, a.bold, 14, nn), yy + (LB - a.lh(14)) / 2, on ? LCD_BG : SILK_DIM,
             fit(a, a.font, 14, x.a[1].s, cw - 40 - text_w(a, a.bold, 14, nn)));
    });
    if (tk >= 0) {
        usend(0x0B, (int)set->a[0].d());
        usend(0x0C, (int)sk.a[(size_t)tk].a[0].d());
        strike(D.sel);
        J rr = call(a, "{\"call\":\"drums\"}");
        if (const J *x = rr.get("drums"))
            drums_take(a, *x);
    }
}

}  // namespace nui
