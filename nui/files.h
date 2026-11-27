#ifdef __APPLE__
#include <TargetConditionals.h>
#endif
// THE FILES CARD (the retired web interface's): a MIDI file on this machine -- found in its
// folders, checked (what it reads as, the file check's findings, a mode
// worth trying, the MT-32's or the mux's report), played live (the parts
// its own, one per channel), or rendered offline: as heard (the live
// engine) or at best quality (the file renderer, then the room's tail), in
// the mode chosen (what the file says, GM, a Sound Canvas map, MT-32). An
// AUDIO file (MP3, WAV, FLAC -- our renders among them) is played instead,
// beside what the keyboard plays, at its own level (audioplay.cpp): the
// controls change to a player's.
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
    float seek_drag = -1;               // (the position bar dragged: its place, till let go)
};
static FilesUi g_fl;

static const std::vector<std::pair<std::string, std::string>> FL_MODES = {
    {"auto", N_("AUTO")}, {"gm", "GM"}, {"ours", N_("GS: OURS")}, {"sc55", "GS: SC-55"}, {"sc88", "GS: SC-88"},  // i18n-skip
    {"sc88pro", "GS: SC-88Pro"}, {"sc8850", "GS: SC-8850"}, {"cm64", N_("GS: INIT CM-64")}, {"mt32", "MT-32"},  // i18n-skip
    {"cm64u", "CM-64"}, {"names", N_("ORCHESTRA BY NAMES")}};
inline std::string fl_mode_label(const std::string &k)
{
    for (const auto &m : FL_MODES)
        if (m.first == k)
            return T(m.second);
    return k == "gs" ? "GS" : k;
}
inline std::string fl_report_title(const std::string &m)
{
    return m == "names" ? T("Its parts, by their names") : m == "mt32" ? T("What the MT-32 does with it") : m == "cm64u" ? T("What the CM-64 does with it") : "";
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
extern "C" int nui_pick_available(void);
extern "C" void nui_pick_midi(void);
extern "C" int nui_pick_take(char *path, int cap);
// (Best Quality's file export, missing: where it goes -- iOS's Documents, beside the sound data)
#if defined(__APPLE__) && TARGET_OS_IPHONE
static const char *FL_NO_EXPORT = N_("Best quality needs the file render's data: file-export.nvx in Clavitone's Documents.");
#else
static const char *FL_NO_EXPORT = N_("Best quality needs the file render's data (file-export.nvx beside the live data); see Help: Files.");
#endif
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
inline bool fl_is_audio(const std::string &p)
{
    std::string l = p;
    for (char &c : l)
        c = (char)tolower((unsigned char)c);
    auto ends = [&](const char *x) { size_t k = strlen(x); return l.size() > k && l.compare(l.size() - k, k, x) == 0; };
    return ends(".mp3") || ends(".wav") || ends(".flac");
}
inline void fl_report(App &a);
// A FILE CHOSEN: a MIDI file read and checked; an audio file opened in the player
inline void fl_select(App &a, const std::string &p)
{
    FilesUi &F = g_fl;
    F.sel = p;
    F.rep_for.clear();
    F.scroll_find = 0;
    F.seek_drag = -1;
    if (fl_is_audio(p)) {
        J r = call(a, "{\"call\":\"audio_open\",\"path\":" + jstr(p) + "}");
        F.info = J();
        if (!flag(&r, "ok") && r.get("error")) {
            F.info = sess::obj();
            F.info.o["audio_err"] = sess::str(str(&r, "error"));
        }
        fl_take(r);
        return;
    }
    J r = call(a, "{\"call\":\"file_info\",\"path\":" + jstr(p) + "}");
    F.info = r.get("info") ? *r.get("info") : J();
    fl_report(a);
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
    // (the iPad's: its card from y 210 to card_y1 + 6, two pages -- choosing the file; playing and rendering it.
    //  The phone's the same two, the card's height: what scrolls there is buttons alone -- the file's
    //  panel, a MIDI file's play and render; an audio file's player, its bar and its level, fits)
    const bool IP = a.tab, PH = a.ph;
    static int page = 0;
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = IP ? (PH ? 818 : 1113) : 1886, Y0 = PH ? 160 : IP ? 266 : 394, Y1 = card_y1(a),
                HY = PH ? 120 : IP ? 224 : 356;
    const float LH = a.lh(14) + (IP ? 3 : 4), B21 = IP ? 21 : 14, BB = IP ? 44 : 34;
    const float TX = heading(a, X0, HY, T("FILES"), "files");
    if (PH) {
        const int h = phone_pages(a, "flppage", TX, {T("CHOOSE"), T("PLAY")}, page);
        if (h >= 0)
            page = h;
    } else if (IP)
        for (int pg = 0; pg < 2; pg++) {
            const std::string id = "flpage" + std::to_string(pg);
            if (button(a, id.c_str(), page_kx(a, 2, pg, 300), 216, page_kw(a, 2), 44, pg ? T("PLAY") : T("CHOOSE"), page == pg, true, 21))
                page = pg;
        }
    const bool ok = flag(&F.info, "ok");
    const J *au = F.f.get("audio");                 // (the audio player: an audio file chosen)
    const bool aud = !F.sel.empty() && fl_is_audio(F.sel);
    const J *pl = F.f.get("player"), *rd = F.f.get("render");
    const bool playing = flag(pl, "busy"), rendering = flag(rd, "busy");
    if (playing)
        text(a, a.font, 14, PH ? 420 : IP ? 700 : TX, HY + 1, OWN, fit(a, a.font, 14, TF("playing {0}", {str(pl, "name")}), PH ? 390 : IP ? 400 : 900));

    // THE FOLDERS
    const float BW = IP ? 360 : 560, FR = IP ? 48 : 36, FB = IP ? 44 : 32;
    if (!IP || page == 0) {
    look::tray(a, X0, Y0, BW, Y1 - Y0, 9);
    heading(a, X0 + 12, Y0 + 10, T("FOLDERS"), "fl:browse");   // i18n-skip (the help key)
    const std::string parent = str(&F.list, "parent"), home = str(&F.list, "home");
    if (button(a, "flup", X0 + 12, Y0 + 34, 90, IP ? 44 : 36, T("\xe2\x96\xb2 UP"), false, !parent.empty(), B21) && !parent.empty())
        fl_go(a, parent);
    if (button(a, "flhome", X0 + 108, Y0 + 34, 100, IP ? 44 : 36, T("MUSIC"), false, true, B21)) {
        const std::string m = str(&F.list, "music");
        fl_go(a, m.empty() ? home + "/Music" : m);
    }
    // THE SYSTEM's PICKER (iOS: iCloud Drive, On My iPad, a USB drive): a MIDI
    // file copied in (Documents/MIDI) and chosen here, its folder shown
    const bool picker = nui_pick_available() != 0;
    if (picker && button(a, "flpick", X0 + BW - 112, Y0 + 34, 100, IP ? 44 : 36, T("FILES\xe2\x80\xa6"), false, true, B21))
        nui_pick_midi();
    {
        char pk[2048];
        if (nui_pick_take(pk, (int)sizeof pk) && pk[0]) {
            const std::string p = pk;
            fl_go(a, p.substr(0, p.rfind('/')));
            fl_select(a, p);
        }
    }
    std::string d = F.dir;
    if (!home.empty() && d.rfind(home, 0) == 0)
        d = "~" + d.substr(home.size());
    // (a long path: its end)
    while (d.size() > 3 && text_w(a, a.font, 14, d) > BW - (picker ? 360 : 240))
        d = "\xe2\x80\xa6" + d.substr(d[0] == '\xe2' ? 4 : 1);
    text(a, a.font, 14, X0 + 220, Y0 + 34 + ((IP ? 44 : 36) - a.lh(14)) / 2, LCD, d);
    const J *es = F.list.get("entries");
    const int ne = es && es->is(J::ARR) ? (int)es->a.size() : 0;
    const int tap = scroll_list(a, "flentries", X0 + 12, Y0 + (IP ? 88 : 80), BW - 24, Y1 - Y0 - (IP ? 100 : 92), ne, FR, F.scroll, [&](int i, float y) {
        const J &e = es->a[(size_t)i];
        const bool dir = flag(&e, "dir");
        const std::string p = F.dir + "/" + str(&e, "name");
        const bool on = p == F.sel;
        look::chip(a, X0 + 12, y, BW - 32, FB, on);
        text(a, a.font, 14, X0 + 22, y + (FB - a.lh(14)) / 2, on ? LCD_BG : dir ? LCD : SILK,
             fit(a, a.font, 14, (dir ? "\xe2\x96\xb8 " : flag(&e, "audio") ? "\xe2\x99\xaa " : "") + str(&e, "name"), BW - 56));
    });
    if (!ne)
        text(a, a.font, 14, X0 + 12, Y0 + 86, SILK_DIM, T("No folders, MIDI or audio files here."));
    if (tap >= 0) {
        const J &e = es->a[(size_t)tap];
        const std::string p = F.dir + "/" + str(&e, "name");
        if (flag(&e, "dir"))
            fl_go(a, p);
        else
            fl_select(a, p);
    }

    }
    // THE FILE: what it is, the check, the mode
    const float FX = X0 + BW + 10, FW = IP ? X1 - FX : 740, PX = IP ? X0 : FX + FW + 10, PW = X1 - PX;
    if (!IP || page == 0) {
    look::tray(a, FX, Y0, X1 - FX, Y1 - Y0, 9);
    const float fx_ = heading(a, FX + 12, Y0 + 10, T("THE FILE"), "fl:file");   // i18n-skip (the help key)
    if (!F.sel.empty())
        text(a, a.font, 14, fx_, Y0 + 11, LCD,
             fit(a, a.font, 14, F.sel.substr(F.sel.rfind('/') + 1), FW - 140));
    std::string about;
    if (F.sel.empty())
        about = T("Choose a MIDI or audio file on the left.");
    else if (aud) {
        const std::string ae = str(&F.info, "audio_err");
        const double sr = num(au, "sr");
        const int ch = (int)num(au, "ch");
        char hz[32];
        snprintf(hz, sizeof hz, "%.1f kHz", sr / 1000.0);
        const std::string chn = ch == 1 ? std::string(T("mono")) : ch == 2 ? std::string(T("stereo"))
                                : TF("{0} channels (the first two played)", {std::to_string(ch)});
        about = !ae.empty() ? TF("It cannot be played: {0}.", {ae})
              : str(au, "path") != F.sel ? std::string(T("Opening it\xe2\x80\xa6"))
              : IP ? TF("Audio, {0} long \xc2\xb7 {1} \xc2\xb7 {2}. It plays beside what you play, at its own level: on the PLAY page.",
                        {mmss(num(au, "len")), std::string(hz), chn})
                   : TF("Audio, {0} long \xc2\xb7 {1} \xc2\xb7 {2}. It plays beside what you play, at its own level, on the right.",
                        {mmss(num(au, "len")), std::string(hz), chn});
    }
    else if (!F.info.is(J::OBJ))
        about = T("Reading it\xe2\x80\xa6");
    else if (!ok)
        about = TF("It cannot be read: {0}.", {T(str(&F.info, "err"))});
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
        const std::string say = det == "gs" ? "GS" : det == "gm" ? "GM" : det == "cm64" ? T("GS (Init CM-64: an MT-32 file on a Sound Canvas)")
                              : det == "mt32" ? "MT-32" : det == "names" ? T("an orchestra by track names") : det;
        const std::string chs_ = nch == 1 ? TF("{0} channel ({1})", {std::to_string(nch), cl}) : TF("{0} channels ({1})", {std::to_string(nch), cl});
        const std::string pcs_ = np == 1 ? TF("{0} program change", {std::to_string(np)}) : TF("{0} program changes", {std::to_string(np)});
        about = TF("{0} long \xc2\xb7 {1} \xc2\xb7 {2}. It reads as {3}: {4}.", {mmss(num(&F.info, "total")), chs_, pcs_, say, T(str(&F.info, "why"))});
    }
    PhoneBodyScope fbody(a, PH, "flfile", FX + 2, Y0 + 32, X1 - 2, Y1 - 2);   // (the phone's: buttons alone, scrolling)
    float y = Y0 + 36;
    for (const auto &l : wrap(a, a.font, 14, about, FW - 24)) {
        text(a, a.font, 14, FX + 12, y, SILK_DIM, l);
        y += LH;
    }
    if (!aud) {                         // (an audio file: no mode, no check)
    const std::string sug = str(&F.info, "suggest");
    if (ok && !sug.empty() && fl_eff() != sug)
        for (const auto &l : wrap(a, a.font, 14, TF("Worth trying {0}: {1}.", {fl_mode_label(sug), T(str(&F.info, "suggest_why"))}), FW - 24)) {
            text(a, a.font, 14, FX + 12, y, OWN, l);
            y += LH;
        }
    y += 8;
    heading(a, FX + 12, y, T("MODE"), "fl:mode");   // i18n-skip (the help key)
    y += 22;
    {
        std::vector<std::string> w;
        std::vector<bool> lit;
        for (const auto &m : FL_MODES) {
            w.push_back(T(m.second) + (m.first == "auto" && ok ? ": " + fl_mode_label(str(&F.info, "detected")) : ""));
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
        const int hv = mt ? flow_buttons(a, "flvel", FX + 12, y, FW - 24, {TF("MT-32 VELOCITY {0}", {vel ? T("ON") : T("OFF")})}, {vel}) : -1;
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
        const std::string t = std::string(F.find_open ? "\xe2\x96\xbe " : "\xe2\x96\xb8 ") +
                              (nf == 1 ? TF("The file check: {0} thing to know", {std::to_string(nf)})
                                       : TF("The file check: {0} things to know", {std::to_string(nf)}));
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
        const std::string t = std::string(F.rep_open ? "\xe2\x96\xbe " : "\xe2\x96\xb8 ") + (nr ? rt : TF("{0}: nothing to report", {rt}));
        if (button(a, "flrep", FX + 12, y, FW - 24, BB, t))
            F.rep_open = !F.rep_open;
        y += 40;
        if (F.rep_open && nr)
            lines_box(a, "flrepbox", FX + 12, y, FW - 24, bh - 8, F.rep, F.scroll_rep);
    }
    }

    }
    // PLAY LIVE (the iPad's a page of its own, the file named at its top)
    if (IP && page == 0)
        return;
    if (IP) {
        look::tray(a, X0, Y0, X1 - X0, Y1 - Y0, 9);
    } else
        rect(a, PX - 6, Y0 + 12, 1, Y1 - Y0 - 24, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
    // (the phone's MIDI file: play and render, buttons alone, scrolling; an audio file's player fits)
    PhoneBodyScope pbody(a, PH && !aud, "flplay", X0 + 2, Y0 + 2, X1 - 2, Y1 - 2);
    float py = Y0 + 10;
    if (IP) {
        text(a, a.font, 21, PX + 8, py, LCD, F.sel.empty() ? std::string(T("No file chosen: choose one on the CHOOSE page."))
                                                         : fit(a, a.font, 21, F.sel.substr(F.sel.rfind('/') + 1), PW - 24));
        py += a.lh(21) + 14;
    }
    if (aud) {                          // THE PLAYER: an audio file, beside what is played
        heading(a, PX + 8, py, T("PLAYER"), "fl:audio");   // i18n-skip (the help key)
        py += 26;
        const bool here = str(au, "path") == F.sel, pl = here && flag(au, "playing");
        const double len = num(au, "len"), at = F.seek_drag >= 0 ? F.seek_drag : num(au, "at");
        if (button(a, "flaplay", PX + 8, py, 160, 44, pl ? T("PAUSE") : T("PLAY"), pl, here && len > 0, B21) && here)
            fl_take(call(a, std::string("{\"call\":\"audio_play\",\"on\":") + (pl ? "0" : "1") + "}"));
        if (button(a, "flastop", PX + 176, py, 110, 44, T("STOP"), false, here && (pl || at > 0), B21)) {
            fl_take(call(a, "{\"call\":\"audio_play\",\"on\":0}"));
            fl_take(call(a, "{\"call\":\"audio_seek\",\"at\":0}"));
        }
        text(a, a.font, 21, PX + 304, py + (44 - a.lh(21)) / 2, LCD, mmss(at) + " / " + mmss(len));
        py += 62;
        // (its place: a bar to drag, the file sought where it is let go)
        const float bx = PX + 8, bw = PW - 150, bh = 40;
        ImGui::SetCursorScreenPos(P(a, bx, py));
        ImGui::InvisibleButton("flaseek", ImVec2(bw * a.k, bh * a.k));
        if (ImGui::IsItemActive() && here && len > 0) {
            const float mx = (ImGui::GetIO().MousePos.x - a.org.x) / a.k;
            F.seek_drag = (float)(std::max(0.0, std::min(1.0, (double)(mx - bx) / bw)) * len);
        }
        if (ImGui::IsItemDeactivated() && F.seek_drag >= 0) {
            fl_take(call(a, "{\"call\":\"audio_seek\",\"at\":" + std::to_string(F.seek_drag) + "}"));
            F.seek_drag = -1;
        }
        const float fr = len > 0 ? (float)std::min(1.0, at / len) : 0.0f;
        rect(a, bx, py + bh / 2 - 4, bw, 8, IM_COL32(0x2b, 0x2f, 0x34, 255), 4);
        rect(a, bx, py + bh / 2 - 4, bw * fr, 8, F.seek_drag >= 0 ? OWN : LCD, 4);
        rect(a, bx + bw * fr - 6, py + bh / 2 - 14, 12, 28, F.seek_drag >= 0 ? OWN : SILK, 4);
        // (its level: a fader at the right, 0 dB its detent)
        {
            static float lv = 0;
            static bool held = false;
            const int fl_ = fader(a, "flalevel", PX + PW - 70, Y0 + (PH ? 40 : IP ? 90 : 130), PH ? Y1 - Y0 - 100 : IP ? 240 : 170, lv, -30, 6, 0.5f, {0.0f},
                                  T("LEVEL"), (lv > 0 ? "+" : "") + std::to_string((int)std::lround(lv)) + " dB");
            if (fl_ & K_CHANGED)
                fl_take(call(a, "{\"call\":\"audio_level\",\"db\":" + std::to_string(lv) + "}"));
            held = (fl_ & K_ACTIVE) != 0;
            if (!held)
                lv = (float)num(au, "level_db");
        }
        py += bh + 20;
        for (const auto &l : wrap(a, a.font, 14, T("It plays through the same output as the keyboard, mixed beside it: "
                                                   "play along, or listen back to a render."), PW - 170)) {
            text(a, a.font, 14, PX + 8, py, SILK_DIM, l);
            py += LH;
        }
        return;
    }
    heading(a, PX + 8, py, T("PLAY LIVE"), "fl:play");   // i18n-skip (the help key)
    py += 26;
    if (button(a, "flplay", PX + 8, py, 160, 44, T("PLAY LIVE"), false, ok && !playing, B21) && ok && !playing)
        fl_take(call(a, "{\"call\":\"file_play\",\"path\":" + jstr(F.sel) + ",\"mode\":" + jstr(F.mode) + "}"));
    if (button(a, "flstop", PX + 176, py, 110, 44, T("STOP"), false, playing, B21) && playing)
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
            const std::string msg = T(str(pl, "msg")), stage = T(str(pl, "stage")), md = str(pl, "mode");
            st = !msg.empty() ? msg
                 : playing ? stage + " (" + (md == "gs" ? std::string(T("GS, the Setup card's standard")) : fl_mode_label(md)) + ")"
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
    heading(a, PX + 8, py, T("RENDER OFFLINE"), "fl:render");   // i18n-skip (the help key)
    py += 26;
    const bool fx_ok = flag(&F.f, "file_export");
    auto render = [&](const char *kind, bool whole) {
        fl_take(call(a, "{\"call\":\"file_render\",\"path\":" + jstr(F.sel) + ",\"mode\":" + jstr(F.mode) + ",\"kind\":\"" + kind +
                            "\",\"whole\":" + (whole ? "1" : "0") + "}"));
    };
    const float rbw = (PW - 24 - 16) / 3;
    if (button(a, "flheard", PX + 8, py, rbw, 44, T("AS HEARD"), false, ok && !rendering, B21) && ok && !rendering)
        render("heard", false);
    if (button(a, "flbest", PX + 16 + rbw, py, rbw, 44, T("BEST QUALITY"), false, ok && !rendering && fx_ok, B21) && ok && !rendering && fx_ok)
        render("best", false);
    if (button(a, "flrstop", PX + 24 + 2 * rbw, py, rbw, 44, T("STOP RENDER"), false, rendering, B21) && rendering)
        fl_take(call(a, "{\"call\":\"file_render_stop\"}"));
    py += 56;
    {
        std::string st;
        if (rd) {
            const std::string msg = str(rd, "msg"), last = str(rd, "last");
            // (the file renderer's place in the song: its percent, its time and the end)
            const double at_ = num(rd, "at"), len_ = num(rd, "len");
            const std::string where = len_ > 0 ? " \xc2\xb7 " + std::to_string((int)(100.0 * at_ / len_)) + "% \xc2\xb7 " +
                                                 mmss(at_) + " / " + mmss(len_) : "";
            st = rendering ? str(rd, "name") + ": " + T(str(rd, "stage")) + "\xe2\x80\xa6 " + mmss(num(rd, "secs")) + where +
                                 (last.empty() ? "" : " \xc2\xb7 " + last)
                 : !msg.empty() ? str(rd, "name") + ": " + (msg == "rendered" ? TF("{0} in {1}", {T(msg), mmss(num(rd, "secs"))}) : T(msg)) + "."
                 : !fx_ok ? T(FL_NO_EXPORT) : "";
        }
        for (const auto &l : wrap(a, a.font, 14, st, PW - 24)) {
            text(a, a.font, 14, PX + 8, py, SILK_DIM, l);
            py += LH;
        }
        // (a best render that cannot stream: ask)
        const std::string ask = str(rd, "ask");
        if (rd && !rendering && !ask.empty()) {
            py += 6;
            std::string q = (ask == "refused" ? T("Best quality cannot render it") : T("It cannot be streamed yet")) + std::string(": ") + str(rd, "ask_why") + "." +
                            (ask == "whole" ? " " + std::string(T("The whole render holds the entire song in memory, which a long song may not fit in.")) : std::string());
            for (const auto &l : wrap(a, a.font, 14, q, PW - 24)) {
                text(a, a.font, 14, PX + 8, py, OWN, l);
                py += LH;
            }
            float bx = PX + 8;
            if (ask == "whole") {
                if (button(a, "flwhole", bx, py + 4, IP ? 330 : 260, IP ? 44 : 40, T("RENDER WHOLE ANYWAY"), false, true, B21))
                    render("best", true);
                bx += IP ? 338 : 268;
            }
            if (button(a, "flinstead", bx, py + 4, IP ? 380 : 300, IP ? 44 : 40, T("RENDER AS HEARD INSTEAD"), false, true, B21))
                render("heard", false);
            py += 52;
        }
        const std::string out = str(rd, "out");
        if (rd && !rendering && str(rd, "msg") == "rendered" && !out.empty()) {
            py += 6;
            for (const auto &l : wrap(a, a.font, 14, TF("Saved to {0}", {out}), PW - 24)) {
                text(a, a.font, 14, PX + 8, py, LCD, l);
                py += LH;
            }
            if (button(a, "flplayit", PX + 8, py + 6, IP ? 200 : 160, IP ? 44 : 40, T("PLAY IT"), false, true, B21)) {
                fl_go(a, out.substr(0, out.rfind('/')));        // (its folder, and the player)
                fl_select(a, out);
            }
            py += 56;
        }
    }
    // (the caution under the render buttons and what they said, not at the card's foot)
    const auto warn = wrap(a, a.font, 14, T("Rendering while you play can cause dropouts: both use the processors. A render that needs more memory than is free is stopped."), PW - 24);
    float wy = PH ? py + 12 : std::min(py + 12, Y1 - 12 - warn.size() * LH);   // (the phone's: under them, its body scrolling to it)
    for (const auto &l : warn) {
        text(a, a.font, 14, PX + 8, wy, LCD_DIM, l);
        wy += LH;
    }
}

}  // namespace nui
