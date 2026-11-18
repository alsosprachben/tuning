// THE FILES CARD (ui/app.js's): a MIDI file on this machine -- found in its
// folders, checked (what it reads as, the file check's findings, a mode
// worth trying, the MT-32's or the mux's report), played live (the parts
// its own, one per channel), or rendered offline: as heard (the live
// engine) or at best quality (the file renderer, then the room's tail), in
// the mode chosen (what the file says, GM, a Sound Canvas map, MT-32).
#pragma once

#include "app.h"
#include "tuning.h"

namespace nui {

struct FilesUi {
    bool open = false;
    J list, f, info, rep;               // (the folder; the player and render; the chosen file's check; its report)
    std::string dir, sel, mode = "auto", rep_for;
    float scroll = 0, scroll_find = 0, scroll_rep = 0;
    bool find_open = false, rep_open = true;
};
static FilesUi g_fl;

static const std::vector<std::pair<std::string, std::string>> FL_MODES = {
    {"auto", "AUTO"}, {"gm", "GM"}, {"ours", "GS: OURS"}, {"sc55", "GS: SC-55"}, {"sc88", "GS: SC-88"}, {"sc88pro", "GS: SC-88PRO"},
    {"sc8850", "GS: SC-8850"}, {"cm64", "GS: INIT CM-64"}, {"mt32", "MT-32"}, {"cm64u", "CM-64"}, {"names", "ORCHESTRA BY NAMES"}};
inline std::string fl_mode_label(const std::string &k)
{
    for (const auto &m : FL_MODES)
        if (m.first == k)
            return m.second;
    return k == "gs" ? "GS" : k;
}
inline std::string fl_report_title(const std::string &m)
{
    return m == "names" ? "Its parts, by their names" : m == "mt32" ? "What the MT-32 does with it" : m == "cm64u" ? "What the CM-64 does with it" : "";
}
// (the check's and the mux's lines count channels from 0: shown from 1)
inline std::string fl_ch(const std::string &x)
{
    std::string o;
    for (size_t i = 0; i < x.size();) {
        if (x.compare(i, 2, "ch") == 0 && (i == 0 || !isalnum((unsigned char)x[i - 1])) && i + 2 < x.size() && isdigit((unsigned char)x[i + 2])) {
            size_t j = i + 2;
            int n = 0;
            while (j < x.size() && isdigit((unsigned char)x[j]))
                n = n * 10 + (x[j++] - '0');
            if (j >= x.size() || !isalnum((unsigned char)x[j])) {
                o += "channel " + std::to_string(n + 1);
                i = j;
                continue;
            }
        }
        o += x[i++];
    }
    return o;
}
inline std::string mmss(double s)
{
    char b[16];
    snprintf(b, sizeof b, "%d:%02d", (int)(s / 60), (int)std::fmod(s, 60));
    return b;
}
inline void fl_take(const J &r)
{
    FilesUi &F = g_fl;
    if (const J *l = r.get("list")) {
        F.list = *l;
        F.dir = str(l, "dir");
    }
    if (const J *f = r.get("files"))
        F.f = *f;
}
inline void fl_go(App &a, const std::string &dir)
{
    g_fl.scroll = 0;
    fl_take(call(a, "{\"call\":\"files\",\"open\":1,\"dir\":" + jstr(dir) + "}"));
}
inline void files_card(App &a, bool open)
{
    FilesUi &F = g_fl;
    if (open == F.open)
        return;
    F.open = open;
    const char *d0 = getenv("NUI_DIR");            // (the first folder: NUI_DIR's, else the engine's own choice)
    const std::string dir = F.dir.empty() && d0 ? d0 : F.dir;
    fl_take(call(a, open ? "{\"call\":\"files\",\"open\":1,\"dir\":" + jstr(dir) + "}" : std::string("{\"call\":\"files\",\"open\":0}")));
}
// the mode a file plays in: AUTO's is what it found
inline std::string fl_eff()
{
    FilesUi &F = g_fl;
    return F.mode == "auto" && flag(&F.info, "ok") ? str(&F.info, "detected") : F.mode;
}
inline void fl_report(App &a)
{
    FilesUi &F = g_fl;
    const std::string md = fl_eff();
    if (F.sel.empty() || fl_report_title(md).empty() || F.rep_for == F.sel + "|" + md)
        return;
    J r = call(a, "{\"call\":\"file_info\",\"path\":" + jstr(F.sel) + ",\"mode\":" + jstr(md) + "}");
    if (const J *i = r.get("info")) {
        F.rep = i->get("report") ? *i->get("report") : sess::arr();
        F.rep_for = F.sel + "|" + md;
        F.scroll_rep = 0;
    }
}

// LINES in a box that scrolls under a finger (wrapped)
inline void lines_box(App &a, const char *id, float x, float y, float w, float h, const J &lines, float &scroll)
{
    std::vector<std::string> ls;
    if (lines.is(J::ARR))
        for (const J &l : lines.a) {
            const auto wl = wrap(a, a.font, 14, "\xc2\xb7 " + fl_ch(l.is(J::STR) ? l.s : ""), w - 24);
            ls.insert(ls.end(), wl.begin(), wl.end());
        }
    rect(a, x, y, w, h, IM_COL32(0x17, 0x19, 0x1c, 255), 6);
    ImVec2 tap;
    scroll_area(a, id, x, y, w, h, ls.size() * 18.0f + 12, scroll, tap);
    dl()->PushClipRect(P(a, x, y), P(a, x + w, y + h), true);
    for (size_t i = 0; i < ls.size(); i++)
        text(a, a.font, 14, x + 10, y + 6 + i * 18 - scroll, SILK, ls[i]);
    dl()->PopClipRect();
}

inline void draw_files(App &a)
{
    FilesUi &F = g_fl;
    if (!F.list.is(J::OBJ)) {           // (the first folder: NUI_DIR's, else the engine's own choice)
        const char *d0 = getenv("NUI_DIR");
        fl_go(a, F.dir.empty() && d0 ? d0 : F.dir);
    }
    // (the iPad's: its card from y 210 to 734, two pages -- choosing the file; playing and rendering it)
    const bool IP = a.tab;
    static int page = 0;
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, Y0 = IP ? 266 : 394, Y1 = IP ? 728 : 1056, HY = IP ? 224 : 356;
    const float LH = a.lh(14) + (IP ? 3 : 4), B21 = IP ? 21 : 14, BB = IP ? 44 : 34;
    const float TX = heading(a, X0, HY, "FILES", "files");
    if (IP)
        for (int pg = 0; pg < 2; pg++) {
            const std::string id = "flpage" + std::to_string(pg);
            if (button(a, id.c_str(), 300 + pg * 196, 216, 190, 44, pg ? "PLAY" : "CHOOSE", page == pg, true, 21))
                page = pg;
        }
    const bool ok = flag(&F.info, "ok");
    const J *pl = F.f.get("player"), *rd = F.f.get("render");
    const bool playing = flag(pl, "busy"), rendering = flag(rd, "busy");
    if (playing)
        text(a, a.font, 14, IP ? 700 : TX, HY + 1, OWN, fit(a, a.font, 14, "playing " + str(pl, "name"), IP ? 400 : 900));

    // THE FOLDERS
    const float BW = IP ? 360 : 560, FR = IP ? 48 : 36, FB = IP ? 44 : 32;
    if (!IP || page == 0) {
    rect(a, X0, Y0, BW, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
    frame(a, X0, Y0, BW, Y1 - Y0, EDGE, 9, 1);
    heading(a, X0 + 12, Y0 + 10, "FOLDERS", "fl:browse");
    const std::string parent = str(&F.list, "parent"), home = str(&F.list, "home");
    if (button(a, "flup", X0 + 12, Y0 + 34, 90, IP ? 44 : 36, "\xe2\x96\xb2 UP", false, !parent.empty(), B21) && !parent.empty())
        fl_go(a, parent);
    if (button(a, "flhome", X0 + 108, Y0 + 34, 100, IP ? 44 : 36, "MUSIC", false, true, B21)) {
        const std::string m = str(&F.list, "music");
        fl_go(a, m.empty() ? home + "/Music" : m);
    }
    std::string d = F.dir;
    if (!home.empty() && d.rfind(home, 0) == 0)
        d = "~" + d.substr(home.size());
    // (a long path: its end)
    while (d.size() > 3 && text_w(a, a.font, 14, d) > BW - 240)
        d = "\xe2\x80\xa6" + d.substr(d[0] == '\xe2' ? 4 : 1);
    text(a, a.font, 14, X0 + 220, Y0 + 34 + ((IP ? 44 : 36) - a.lh(14)) / 2, LCD, d);
    const J *es = F.list.get("entries");
    const int ne = es && es->is(J::ARR) ? (int)es->a.size() : 0;
    const int tap = scroll_list(a, "flentries", X0 + 12, Y0 + (IP ? 88 : 80), BW - 24, Y1 - Y0 - (IP ? 100 : 92), ne, FR, F.scroll, [&](int i, float y) {
        const J &e = es->a[(size_t)i];
        const bool dir = flag(&e, "dir");
        const std::string p = F.dir + "/" + str(&e, "name");
        const bool on = p == F.sel;
        rect(a, X0 + 12, y, BW - 32, FB, on ? LCD : IM_COL32(0x26, 0x2a, 0x2e, 255), 5);
        text(a, a.font, 14, X0 + 22, y + (FB - a.lh(14)) / 2, on ? LCD_BG : dir ? LCD : SILK,
             fit(a, a.font, 14, (dir ? "\xe2\x96\xb8 " : "") + str(&e, "name"), BW - 56));
    });
    if (!ne)
        text(a, a.font, 14, X0 + 12, Y0 + 86, SILK_DIM, "No folders or MIDI files here.");
    if (tap >= 0) {
        const J &e = es->a[(size_t)tap];
        const std::string p = F.dir + "/" + str(&e, "name");
        if (flag(&e, "dir"))
            fl_go(a, p);
        else {
            F.sel = p;
            F.rep_for.clear();
            J r = call(a, "{\"call\":\"file_info\",\"path\":" + jstr(p) + "}");
            F.info = r.get("info") ? *r.get("info") : J();
            F.scroll_find = 0;
            fl_report(a);
        }
    }

    }
    // THE FILE: what it is, the check, the mode
    const float FX = X0 + BW + 10, FW = IP ? X1 - FX : 740, PX = IP ? X0 : FX + FW + 10, PW = X1 - PX;
    if (!IP || page == 0) {
    rect(a, FX, Y0, X1 - FX, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
    frame(a, FX, Y0, X1 - FX, Y1 - Y0, EDGE, 9, 1);
    const float fx_ = heading(a, FX + 12, Y0 + 10, "THE FILE", "fl:file");
    if (!F.sel.empty())
        text(a, a.font, 14, fx_, Y0 + 11, LCD,
             fit(a, a.font, 14, F.sel.substr(F.sel.rfind('/') + 1), FW - 140));
    std::string about;
    if (F.sel.empty())
        about = "Choose a MIDI file on the left.";
    else if (!F.info.is(J::OBJ))
        about = "Reading it\xe2\x80\xa6";
    else if (!ok)
        about = "It cannot be read: " + str(&F.info, "err") + ".";
    else {
        const J *chs = F.info.get("channels");
        std::string cl;
        int nch = 0;
        if (chs && chs->is(J::ARR))
            for (const J &c : chs->a) {
                cl += (cl.empty() ? "" : ", ") + std::to_string((int)c.d() + 1);
                nch++;
            }
        const int np = (int)num(&F.info, "programs");
        const std::string det = str(&F.info, "detected");
        const std::string say = det == "gs" ? "GS" : det == "gm" ? "GM" : det == "cm64" ? "GS (Init CM-64: an MT-32 file on a Sound Canvas)"
                              : det == "mt32" ? "MT-32" : det == "names" ? "an orchestra by track names" : det;
        about = mmss(num(&F.info, "total")) + " long \xc2\xb7 " + std::to_string(nch) + " channel" + (nch == 1 ? "" : "s") + " (" + cl + ") \xc2\xb7 " +
                std::to_string(np) + " program change" + (np == 1 ? "" : "s") + ". It reads as " + say + ": " + str(&F.info, "why") + ".";
    }
    float y = Y0 + 36;
    for (const auto &l : wrap(a, a.font, 14, about, FW - 24)) {
        text(a, a.font, 14, FX + 12, y, SILK_DIM, l);
        y += LH;
    }
    const std::string sug = str(&F.info, "suggest");
    if (ok && !sug.empty() && fl_eff() != sug)
        for (const auto &l : wrap(a, a.font, 14, "Worth trying " + fl_mode_label(sug) + ": " + str(&F.info, "suggest_why") + ".", FW - 24)) {
            text(a, a.font, 14, FX + 12, y, OWN, l);
            y += LH;
        }
    y += 8;
    heading(a, FX + 12, y, "MODE", "fl:mode");
    y += 22;
    {
        std::vector<std::string> w;
        std::vector<bool> lit;
        for (const auto &m : FL_MODES) {
            w.push_back(m.second + (m.first == "auto" && ok ? ": " + fl_mode_label(str(&F.info, "detected")) : ""));
            lit.push_back(F.mode == m.first);
        }
        const int h = flow_buttons(a, "flmode", FX + 12, y, FW - 24, w, lit);
        if (h >= 0) {
            F.mode = FL_MODES[(size_t)h].first;
            fl_report(a);
        }
        // (the MT-32's velocity acts only in the MT-32's modes -- AUTO's when it finds an MT-32 file: shown there alone)
        const std::string em_ = fl_eff();
        const bool mt = em_ == "cm64" || em_ == "mt32" || em_ == "cm64u" || em_ == "names";
        const bool vel = !F.f.get("mt32_vel") || flag(&F.f, "mt32_vel");
        const int hv = mt ? flow_buttons(a, "flvel", FX + 12, y, FW - 24, {std::string("MT-32 VELOCITY ") + (vel ? "ON" : "OFF")}, {vel}) : -1;
        if (hv == 0)
            fl_take(call(a, std::string("{\"call\":\"file_opts\",\"mt32_vel\":") + (vel ? "0" : "1") + "}"));
    }
    // the file check's findings, and the mode's report: each opened or shut, its lines in a box
    const J *fd = ok ? F.info.get("findings") : nullptr;
    const int nf = fd && fd->is(J::ARR) ? (int)fd->a.size() : 0;
    const std::string em = fl_eff(), rt = fl_report_title(em);
    const bool has_rep = !rt.empty() && F.rep_for == F.sel + "|" + em;
    const float avail = Y1 - 12 - y - (nf ? 40 : 0) - (has_rep ? 40 : 0);
    const int opened = (nf && F.find_open) + (has_rep && F.rep_open);
    const float bh = opened ? std::max(60.0f, avail / opened) : 0;
    if (nf) {
        const std::string t = std::string(F.find_open ? "\xe2\x96\xbe " : "\xe2\x96\xb8 ") + "The file check: " + std::to_string(nf) +
                              " thing" + (nf == 1 ? "" : "s") + " to know";
        if (button(a, "flfind", FX + 12, y, FW - 24, BB, t))
            F.find_open = !F.find_open;
        y += 40;
        if (F.find_open) {
            lines_box(a, "flfindbox", FX + 12, y, FW - 24, bh - 8, *fd, F.scroll_find);
            y += bh;
        }
    }
    if (has_rep) {
        const int nr = F.rep.is(J::ARR) ? (int)F.rep.a.size() : 0;
        const std::string t = std::string(F.rep_open ? "\xe2\x96\xbe " : "\xe2\x96\xb8 ") + rt + (nr ? "" : ": nothing to report");
        if (button(a, "flrep", FX + 12, y, FW - 24, BB, t))
            F.rep_open = !F.rep_open;
        y += 40;
        if (F.rep_open && nr)
            lines_box(a, "flrepbox", FX + 12, y, FW - 24, bh - 8, F.rep, F.scroll_rep);
    }

    }
    // PLAY LIVE (the iPad's a page of its own, the file named at its top)
    if (IP && page == 0)
        return;
    if (IP) {
        rect(a, X0, Y0, X1 - X0, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
        frame(a, X0, Y0, X1 - X0, Y1 - Y0, EDGE, 9, 1);
    } else
        rect(a, PX - 6, Y0 + 12, 1, Y1 - Y0 - 24, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
    float py = Y0 + 10;
    if (IP) {
        text(a, a.font, 21, PX + 8, py, LCD, F.sel.empty() ? std::string("No file chosen: choose one on the CHOOSE page.")
                                                         : fit(a, a.font, 21, F.sel.substr(F.sel.rfind('/') + 1), PW - 24));
        py += a.lh(21) + 14;
    }
    heading(a, PX + 8, py, "PLAY LIVE", "fl:play");
    py += 26;
    if (button(a, "flplay", PX + 8, py, 160, 44, "PLAY LIVE", false, ok && !playing, B21) && ok && !playing)
        fl_take(call(a, "{\"call\":\"file_play\",\"path\":" + jstr(F.sel) + ",\"mode\":" + jstr(F.mode) + "}"));
    if (button(a, "flstop", PX + 176, py, 110, 44, "STOP", false, playing, B21) && playing)
        fl_take(call(a, "{\"call\":\"file_stop\"}"));
    {
        const double pos = num(pl, "pos"), tot = num(pl, "total") > 0 ? num(pl, "total") : num(&F.info, "total");
        const float bx = PX + 298, bw = PW - 298 - 16;
        rect(a, bx, py + 16, bw, 12, IM_COL32(0x15, 0x17, 0x1a, 255), 6);
        if (playing && tot > 0)
            rect(a, bx, py + 16, (float)(bw * std::min(1.0, pos / tot)), 12, LCD, 6);
        if (playing)
            text(a, a.font, 14, bx, py + 32, LCD, mmss(pos) + " / " + mmss(tot));
    }
    py += 58;
    {
        std::string st;
        if (pl) {
            const std::string msg = str(pl, "msg"), stage = str(pl, "stage"), md = str(pl, "mode");
            st = !msg.empty() ? msg
                 : playing ? stage + " (" + (md == "gs" ? std::string("GS, the Setup card's standard") : fl_mode_label(md)) + ")"
                 : !stage.empty() ? str(pl, "name") + ": " + stage + "." : "";
        }
        for (const auto &l : wrap(a, a.font, 14, st, PW - 24)) {
            text(a, a.font, 14, PX + 8, py, SILK_DIM, l);
            py += LH;
        }
    }
    if (playing || rendering)
        a.animate = true;

    // RENDER OFFLINE
    py += 16;
    heading(a, PX + 8, py, "RENDER OFFLINE", "fl:render");
    py += 26;
    const bool fx_ok = flag(&F.f, "file_export");
    auto render = [&](const char *kind, bool whole) {
        fl_take(call(a, "{\"call\":\"file_render\",\"path\":" + jstr(F.sel) + ",\"mode\":" + jstr(F.mode) + ",\"kind\":\"" + kind +
                            "\",\"whole\":" + (whole ? "1" : "0") + "}"));
    };
    const float rbw = (PW - 24 - 16) / 3;
    if (button(a, "flheard", PX + 8, py, rbw, 44, "AS HEARD", false, ok && !rendering, B21) && ok && !rendering)
        render("heard", false);
    if (button(a, "flbest", PX + 16 + rbw, py, rbw, 44, "BEST QUALITY", false, ok && !rendering && fx_ok, B21) && ok && !rendering && fx_ok)
        render("best", false);
    if (button(a, "flrstop", PX + 24 + 2 * rbw, py, rbw, 44, "STOP RENDER", false, rendering, B21) && rendering)
        fl_take(call(a, "{\"call\":\"file_render_stop\"}"));
    py += 56;
    {
        std::string st;
        if (rd) {
            const std::string msg = str(rd, "msg"), last = str(rd, "last");
            st = rendering ? str(rd, "name") + ": " + str(rd, "stage") + "\xe2\x80\xa6 " + mmss(num(rd, "secs")) + (last.empty() ? "" : " \xc2\xb7 " + last)
                 : !msg.empty() ? str(rd, "name") + ": " + msg + (msg == "rendered" ? " in " + mmss(num(rd, "secs")) : "") + "."
                 : !fx_ok ? "Best quality needs nvlive started with --file-export." : "";
        }
        for (const auto &l : wrap(a, a.font, 14, st, PW - 24)) {
            text(a, a.font, 14, PX + 8, py, SILK_DIM, l);
            py += LH;
        }
        // (a best render that cannot stream: ask)
        const std::string ask = str(rd, "ask");
        if (rd && !rendering && !ask.empty()) {
            py += 6;
            std::string q = (ask == "refused" ? "Best quality cannot render it" : "It cannot be streamed yet") + std::string(": ") + str(rd, "ask_why") + "." +
                            (ask == "whole" ? " The whole render holds the entire song in memory, which a long song may not fit in." : "");
            for (const auto &l : wrap(a, a.font, 14, q, PW - 24)) {
                text(a, a.font, 14, PX + 8, py, OWN, l);
                py += LH;
            }
            float bx = PX + 8;
            if (ask == "whole") {
                if (button(a, "flwhole", bx, py + 4, IP ? 330 : 260, IP ? 44 : 40, "RENDER WHOLE ANYWAY", false, true, B21))
                    render("best", true);
                bx += IP ? 338 : 268;
            }
            if (button(a, "flinstead", bx, py + 4, IP ? 380 : 300, IP ? 44 : 40, "RENDER AS HEARD INSTEAD", false, true, B21))
                render("heard", false);
            py += 52;
        }
        const std::string out = str(rd, "out");
        if (rd && !rendering && str(rd, "msg") == "rendered" && !out.empty()) {
            py += 6;
            for (const auto &l : wrap(a, a.font, 14, "Saved to " + out, PW - 24)) {
                text(a, a.font, 14, PX + 8, py, LCD, l);
                py += LH;
            }
        }
    }
    const auto warn = wrap(a, a.font, 14, "Rendering while you play can cause dropouts, since both use the processors; a render that needs more memory than is free beside the engine is stopped.", PW - 24);
    float wy = Y1 - 12 - warn.size() * LH;
    for (const auto &l : warn) {
        text(a, a.font, 14, PX + 8, wy, LCD_DIM, l);
        wy += LH;
    }
}

}  // namespace nui
