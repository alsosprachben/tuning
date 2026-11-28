// THE TUNING CARD (the retired web interface's): the rig's tuner (every part: the patches
// built again in it), grouped by what it is for; its shape drawn -- an
// octave's notes in cents from equal temperament, and how far each key
// strays across the keyboard (stretch); the Eastern tuning the Indian
// voices play (a raga system, a raga, Sa).
#pragma once

#include "app.h"
#include "drums.h"

namespace nui {

struct TuningUi {
    bool open = false, lists = false, measured = false;
    J t;                                // (tuning_of: tuner, now, shape {a4, cents[128]}, eastern)
    std::vector<std::pair<std::string, std::string>> tuners;
    std::vector<std::string> systems, ragas;
    std::string pending;                // (the tuner asked for, till the engine has it)
    std::string east_mine;              // (the eastern spec this screen set, held a moment)
    int scope = 0;                      // (the tiles choose for: 0 every part, the rig; 1 the selected part)
    int row = -1;                       // (the part THIS PART is about: the engine's answers')
    double east_until = 0;
    float scroll = 0;
    // (the KEY page: the key and bridge shown -- the playing chains' once the engine has them, else the last asked)
    int ckey = 0;                       // (the key, 0 C .. 11 B: chain one starts 3 fifths below it)
    double bridge = 386.3137138648348;  // (the bridge third, cents: 5:4)
    std::string chains_mine;            // (the chains name this screen set, held a moment)
    double chains_until = 0;
    int kpage = 0;                      // (the laptop's right tray: 0 the shape, 1 the Clavitone variants)
    std::string coct = "pure", croute = "fifth";    // (the octaves and route shown)
};
static TuningUi g_tn;

// TWO CHAINS, ANY BRIDGE (tunelib.ChainsTuner): chains/<bridge>@<start>.
// The key is chain one's fourth note, 3 fifths up from the start (tuning-lean
// HomeKey.lean, home_key: I, IV, V, iii and vi on pure fifths, all six chords'
// major thirds the bridge; B-flat's chains: G). Every design serves two keys
// a tritone apart, the far one with the mirror 3*1200 - 4P - X; and X above
// the midpoint 396.09 is the same tuning as its mirror on the key a tritone
// away (rotate_six). So the card's bridge runs from the schismatic third to
// the midpoint, and the key it names is always the better served
static const char *const CH_KEY[12] = {"C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"};
static const char *const CH_START[12] = {"c", "c#", "d", "eb", "e", "f", "f#", "g", "ab", "a", "bb", "b"};
inline double ch_P() { return 1200.0 * std::log2(1.5); }
inline double ch_mirror(double x) { return 3600.0 - 4.0 * ch_P() - x; }
struct ChainBridge {
    const char *spec, *name;            // (spec: the engine's name for it; "mean" sent as its mirror's key)
    double x;
};
inline const std::vector<ChainBridge> &chain_bridges()
{
    static const double P = ch_P();
    static const std::vector<ChainBridge> B = {{"helm", N_("Helmholtz"), 6000.0 - 8.0 * P},
                                               {"pure", N_("Pure"), 1200.0 * std::log2(1.25)},
                                               {"mean", N_("Mean"), ch_mirror(1200.0 * std::log2(std::sqrt(1.25 * 81.0 / 64.0)))},
                                               {"mid", N_("Even"), (3600.0 - 4.0 * P) / 2.0}};
    return B;
}
// A CHAINS NAME TAKEN APART (chains/<bridge>[/<octaves>[/<route>]]@<start>,
// or one of the old Clavitone tunings' names, which are variants of it): the
// bridge (cents, at most the midpoint), the key the card names, the octaves
// (pure, piano, middle, own: a class's law token is its own) and the route;
// false if not one
struct ChainSpec {
    double x = 0;
    int key = 0;
    std::string oct = "pure", route = "fifth";
};
inline std::string chains_alias(const std::string &name)
{
    std::string b = name.substr(0, name.find_first_of(":~"));
    for (char &c : b)
        c = (char)tolower((unsigned char)c);
    static const std::map<std::string, std::string> OLD = {
        {"hybrid", "chains/pure/piano/fourth@bb"}, {"hybrid440", "chains/pure/piano/fourth@bb"},
        {"hybridharm", "chains/pure/middle/fourth@bb"}, {"hybridharm440", "chains/pure/middle/fourth@bb"},
        {"hybridmean", "chains/mean@c"}, {"hybridmeanpiano", "chains/mean/piano@c"},
        {"stretchedhelmholtz", "chains/helm/piano/octaves@c"}};
    auto it = OLD.find(b);
    return it != OLD.end() ? it->second : b;
}
inline bool chains_parts(const std::string &name, ChainSpec *cs)
{
    std::string b = chains_alias(name);
    if (b.rfind("chains/", 0) != 0)
        return false;
    b = b.substr(7);
    int start = 0;
    if (const size_t at = b.find('@'); at != std::string::npos) {
        const std::string k = b.substr(at + 1);
        start = -1;
        for (int i = 0; i < 12; i++)
            if (k == CH_START[i])
                start = i;
        static const std::map<std::string, int> ALT = {{"db", 1}, {"d#", 3}, {"gb", 6}, {"g#", 8}, {"a#", 10}};
        if (auto it = ALT.find(k); start < 0 && it != ALT.end())
            start = it->second;
        if (start < 0)
            return false;
        b = b.substr(0, at);
    }
    std::vector<std::string> seg;
    for (size_t p = 0;;) {
        const size_t q = b.find('/', p);
        seg.push_back(b.substr(p, q == std::string::npos ? std::string::npos : q - p));
        if (q == std::string::npos)
            break;
        p = q + 1;
    }
    if (seg.size() > 3)
        return false;
    ChainSpec c;
    if (seg.size() > 1)
        c.oct = seg[1].find('=') != std::string::npos ? "own" : seg[1];
    if (seg.size() > 2)
        c.route = seg[2];
    if (c.oct != "pure" && c.oct != "piano" && c.oct != "middle" && c.oct != "own")
        return false;
    if (c.route != "fifth" && c.route != "fourth" && c.route != "octaves")
        return false;
    static const std::map<std::string, double> NAMED = {
        {"helm", 6000.0 - 8.0 * ch_P()}, {"pure", 1200.0 * std::log2(1.25)}, {"mid", (3600.0 - 4.0 * ch_P()) / 2.0},
        {"mean", 1200.0 * std::log2(std::sqrt(1.25 * 81.0 / 64.0))}, {"pyth", 1200.0 * std::log2(81.0 / 64.0)}};
    if (auto it = NAMED.find(seg[0]); it != NAMED.end())
        c.x = it->second;
    else {
        char *end = nullptr;
        c.x = strtod(seg[0].c_str(), &end);
        if (seg[0].empty() || *end)
            return false;
    }
    if (c.route == "octaves")                           // (no bridge third: on pure octaves, the helm's)
        c.x = NAMED.at("helm");
    c.key = (start + 21) % 12;
    if (c.x > (3600.0 - 4.0 * ch_P()) / 2.0 + 1e-9) {   // (the mirror: the same tuning on the key a tritone away)
        c.x = ch_mirror(c.x);
        c.key = (c.key + 6) % 12;
    }
    *cs = c;
    return true;
}
inline bool chains_parts(const std::string &name, double *x, int *key)
{
    ChainSpec c;
    if (!chains_parts(name, &c))
        return false;
    *x = c.x;
    *key = c.key;
    return true;
}
inline std::string chains_name(const ChainSpec &c)
{
    std::string spec;
    int sh = 0;
    for (const auto &cb : chain_bridges())
        if (std::fabs(c.x - cb.x) < 0.005) {
            spec = cb.spec;
            sh = spec == "mean" ? 6 : 0;            // (mean: its own bridge, from the key a tritone away -- exact)
        }
    if (c.route == "octaves")
        spec = "helm", sh = 0;
    if (spec.empty()) {
        char b[32];
        snprintf(b, sizeof b, "%.2f", c.x);
        spec = b;
    }
    std::string n = "chains/" + spec;
    if (c.oct != "pure" || c.route != "fifth")
        n += "/" + c.oct;
    if (c.route != "fifth")
        n += "/" + c.route;
    return n + "@" + CH_START[(c.key + 3 + sh) % 12];
}
inline std::string chains_name(double x, int key)
{
    ChainSpec c;
    c.x = x;
    c.key = key;
    return chains_name(c);
}
// THE CLAVITONE VARIANTS, by name: each its parameters (the old tunings, exactly)
struct ChainVariant {
    const char *name;
    const char *bridge;                 // (a chain_bridges spec)
    int key;
    const char *oct, *route;
};
inline const std::vector<ChainVariant> &chain_variants()
{
    static const std::vector<ChainVariant> V = {
        {N_("Baroque"), "pure", 7, "piano", "fourth"},                       // (hybrid440; hybrid at A 415)
        {N_("Romantic Meantone"), "mean", 3, "piano", "fifth"},              // (hybridmeanpiano)
        {N_("Stretched Helmholtz"), "helm", 9, "piano", "octaves"},          // (stretchedhelmholtz)
        {N_("Baroque for pipes"), "pure", 7, "middle", "fourth"},            // (hybridharm440)
        {N_("Romantic Meantone for pipes"), "mean", 3, "pure", "fifth"}};    // (hybridmean at 440)
    return V;
}
inline ChainSpec chain_variant_spec(const ChainVariant &v)
{
    ChainSpec c;
    for (const auto &cb : chain_bridges())
        if (std::string(cb.spec) == v.bridge)
            c.x = cb.x;
    c.key = v.key;
    c.oct = v.oct;
    c.route = v.route;
    return c;
}
// the variant a spec is (its index), else -1: on pure octaves the route is moot but for "octaves"
inline int chain_variant_of(const ChainSpec &c)
{
    const auto &V = chain_variants();
    for (size_t i = 0; i < V.size(); i++) {
        const ChainSpec v = chain_variant_spec(V[i]);
        const bool route = c.route == v.route || (c.oct == "pure" && v.oct == "pure" && c.route != "octaves" && v.route != "octaves");
        if (std::fabs(c.x - v.x) < 0.006 && c.key == v.key && c.oct == v.oct && route)
            return (int)i;
    }
    return -1;
}
// the bridge said: a named one's name, else its cents
inline std::string chains_bridge_words(double x)
{
    for (const auto &cb : chain_bridges())
        if (std::fabs(x - cb.x) < 0.005)
            return T(cb.name);
    char b[32];
    snprintf(b, sizeof b, "%.2f c", x);
    return b;
}
// THE MODEL (HybridMean.lean): each pitch class's fifth and major third,
// cents from pure (P, 5:4), for chain one from start. Fifths pure but the
// two gaps (positions 5 and 11); third i the sum of fifths i..i+3, less two octaves
inline void chains_model(double x, int start, double third[12], double fifth[12])
{
    const double P = 1200.0 * std::log2(1.5), L = 1200.0 * std::log2(1.25);
    double f[12];
    for (int k = 0; k < 12; k++)
        f[k] = k == 5 ? x + 2400.0 - 3.0 * P : k == 11 ? 6000.0 - 7.0 * P - x : P;
    for (int k = 0; k < 12; k++) {
        const int pc = (start + 7 * k) % 12;
        fifth[pc] = f[k] - P;
        third[pc] = f[k] + f[(k + 1) % 12] + f[(k + 2) % 12] + f[(k + 3) % 12] - 2400.0 - L;
    }
}

// THE TUNING PLAYING, READ (the shape's "fine": C4 to C5 in exact cents
// above C4, and "low": C3-C4): each pitch class's major third and fifth,
// cents from pure; its octaves pure or not; and, on pure octaves, whether it
// is two chains of pure fifths -- under any name (hybridmean, the
// Pythagorean) -- and if so its key and bridge, as the card names them
// (below the midpoint: the mirror)
struct Temper {
    bool ok = false, pure = false, chains = false, wide = false;   // (wide: a fifth wider than pure)
    int key = 0;
    double x = 0, a4 = 0, th[12] = {}, fi[12] = {};
};
inline Temper temper_of(const J *shape)
{
    Temper t;
    const J *f = shape ? shape->get("fine") : nullptr;
    if (!f || !f->is(J::ARR) || f->a.size() < 13)
        return t;
    double c[13];
    for (int i = 0; i < 13; i++) {
        if (!f->a[(size_t)i].is(J::NUM))
            return t;
        c[i] = f->a[(size_t)i].d();
    }
    const double oct = c[12], P = ch_P(), L = 1200.0 * std::log2(1.25);
    auto at = [&](int pc) { return pc < 12 ? c[pc] : c[pc - 12] + oct; };
    for (int p = 0; p < 12; p++) {
        t.fi[p] = at(p + 7) - c[p] - P;
        t.th[p] = at(p + 4) - c[p] - L;
        t.wide = t.wide || t.fi[p] > 1e-4;
    }
    t.ok = true;
    t.a4 = num(shape, "a4");
    t.pure = std::fabs(oct - 1200.0) < 1e-6 && std::fabs(num(shape, "low") - 1200.0) < 1e-6;
    if (!t.pure)
        return t;
    const double lo = 6000.0 - 8.0 * P, hi = 4.0 * P - 2400.0;
    for (int s0 = 0; s0 < 12 && !t.chains; s0++) {
        bool ok = true;
        for (int k = 0; k < 12 && ok; k++)
            if (k != 5 && k != 11)
                ok = std::fabs(t.fi[(s0 + 7 * k) % 12]) < 1e-5;
        const double x = t.th[(s0 + 14) % 12] + L;      // (position 2's third: the bridge)
        if (!ok || x < lo - 1e-5 || x > hi + 1e-5)
            continue;
        t.chains = true;
        t.key = (s0 + 21) % 12;
        t.x = x;
        if (x > (3600.0 - 4.0 * P) / 2.0 + 1e-9) {
            t.x = ch_mirror(x);
            t.key = (t.key + 6) % 12;
        }
    }
    return t;
}

// A TUNING's NAME AND LINE as a person reads them (about.json's tuners), else the engine's key and words
inline std::pair<std::string, std::string> tuner_words(const std::string &key, const std::string &engine_words)
{
    if (ChainSpec cs; chains_parts(key, &cs)) {
        const int v = chain_variant_of(cs);
        static const std::map<std::string, const char *> OCT = {{"pure", N_("pure octaves")}, {"piano", N_("a piano's octaves")},
                                                                {"middle", N_("a piano's middle octave, by 2:1")},
                                                                {"own", N_("each instrument's own octaves")}};
        const std::string oct = T(OCT.at(cs.oct));
        if (v >= 0)
            return {T(chain_variants()[(size_t)v].name), TF("in {0}; {1}", {CH_KEY[cs.key], oct})};
        return {TF("Clavitone in {0}", {CH_KEY[cs.key]}),
                cs.route == "octaves" ? TF("joined by three octaves; {0}", {oct}) : TF("bridge {0}; {1}", {chains_bridge_words(cs.x), oct})};
    }
    LibUi &L = g_lib;
    if (const J *ts = L.about.get("tuners"))
        if (const J *e = ts->get(key.c_str()); e && e->is(J::ARR) && e->a.size() >= 2)
            return {e->a[0].s, e->a[1].s};
    return {key, engine_words};
}
// an Eastern system's name: "Todi", "Yaman Kalyan" (its measured raga's)
inline std::string eastern_name(const std::string &k)
{
    static const std::map<std::string, std::string> M = {{"bel_todi", "Todi"}, {"et", N_("Equal")}, {"just5", N_("Just")}, {"pythagorean", "Pythagorean"}};
    if (auto it = M.find(k); it != M.end())
        return T(it->second);
    std::string s = k.rfind("sung_", 0) == 0 ? k.substr(5) : k;
    bool up = true;
    for (char &c : s) {
        if (c == '_')
            c = ' ';
        c = up ? (char)toupper((unsigned char)c) : c;
        up = c == ' ';
    }
    return s;
}
inline void tn_take(const J &r)
{
    TuningUi &T = g_tn;
    const J *t = r.get("tuning");
    if (!t)
        return;
    if (const J *ts = t->get("tuners"); ts && ts->is(J::ARR)) {
        T.lists = true;
        T.tuners.clear();
        T.systems.clear();
        T.ragas.clear();
        for (const J &x : ts->a)
            T.tuners.push_back({x.a[0].s, x.a.size() > 1 && x.a[1].is(J::STR) ? x.a[1].s : ""});
        if (const J *s = t->get("systems"); s && s->is(J::ARR))
            for (const J &x : s->a)
                T.systems.push_back(x.s);
        if (const J *s = t->get("ragas"); s && s->is(J::ARR))
            for (const J &x : s->a)
                T.ragas.push_back(x.s);
    }
    T.t = *t;
}
inline void tuning_card(App &a, bool open)
{
    TuningUi &T = g_tn;
    if (open == T.open)
        return;
    T.open = open;
    tn_take(call(a, std::string("{\"call\":\"tuning\",\"open\":") + (open ? "1" : "0") + ",\"lists\":" + (T.lists ? "0" : "1") + "}"));
}

// A SCROLLING AREA: a drag scrolls it, a still tap comes back as a point in its content
inline bool scroll_area(App &a, const char *id, float x, float y, float w, float h, float content, float &scroll, ImVec2 &tap)
{
    struct T {
        bool down = false, moved = false;
        ImVec2 p0{0, 0};
        float s0 = 0;
    };
    static std::map<std::string, T> ts;
    T &t = ts[id];
    scroll = std::max(0.0f, std::min(scroll, std::max(0.0f, content - h)));
    ImGui::SetCursorScreenPos(P(a, x, y));
    ImGui::InvisibleButton(id, ImVec2(w * a.k, h * a.k));
    const ImVec2 m = ImGui::GetIO().MousePos;
    const float mx = (m.x - a.org.x) / a.k, my = (m.y - a.org.y) / a.k;
    if (ImGui::IsItemHovered() && ImGui::GetIO().MouseWheel != 0)
        scroll = std::max(0.0f, std::min(std::max(0.0f, content - h), scroll - ImGui::GetIO().MouseWheel * 80));
    if (ImGui::IsItemActivated()) {
        t.down = true;
        t.moved = false;
        t.p0 = ImVec2(mx, my);
        t.s0 = scroll;
    }
    if (ImGui::IsItemActive() && t.down) {
        if (!t.moved && std::fabs(my - t.p0.y) * a.k > SLOP)
            t.moved = true;
        if (t.moved)
            scroll = std::max(0.0f, std::min(std::max(0.0f, content - h), t.s0 - (my - t.p0.y)));
    }
    bool tapped = false;
    if (ImGui::IsItemDeactivated() && t.down) {
        t.down = false;
        if (!t.moved) {
            tap = ImVec2(t.p0.x - x, t.p0.y - y + scroll);
            tapped = true;
        }
    }
    if (content > h) {
        const float bh = std::max(30.0f, h * h / content), by = y + (h - bh) * scroll / (content - h);
        rect(a, x + w - 4, by, 3, bh, SILK_DIM, 1);
    }
    return tapped;
}

// WORDS AS BUTTONS flowing along rows: the one hit (else -1); y advanced past them
inline int flow_buttons(App &a, const std::string &id, float x, float &y, float w, const std::vector<std::string> &words,
                        const std::vector<bool> &lit, float bh = 30, float ws = 0)
{
    float cx = x;
    int hit = -1;
    if (a.tab)                          // (fingers: 44 points the least each way, the words 3x unless asked)
        bh = std::max(bh, 44.0f);
    if (ws <= 0)
        ws = a.tab ? 21 : 14;
    for (size_t i = 0; i < words.size(); i++) {
        const float bw = std::max(a.tab ? 44.0f : 0.0f, text_w(a, a.font, ws, words[i]) + 18);
        if (cx > x && cx + bw > x + w) {
            cx = x;
            y += bh + 5;
        }
        const std::string bid = id + std::to_string(i);
        ImGui::SetCursorScreenPos(P(a, cx, y));
        if (ImGui::InvisibleButton(bid.c_str(), ImVec2(bw * a.k, bh * a.k)))
            hit = (int)i;
        tap_yields(a);
        const bool on = i < lit.size() && lit[i];
        look::chip(a, cx, y, bw, bh, on, ImGui::IsItemActive());
        text_c(a, a.font, ws, cx + bw / 2, y + (bh - a.lh(ws)) / 2, on ? LCD_BG : SILK, words[i]);
        cx += bw + 5;
    }
    y += bh + 8;
    return hit;
}

// "raga:<system>[/<raga>]@<sa>" taken apart, and put together
struct East {
    std::string system, raga, sa = "c#";
};
inline East east_parts(const std::string &e)
{
    East p;
    if (e.rfind("raga:", 0) != 0)
        return p;
    std::string b = e.substr(5);
    const size_t at = b.find('@');
    if (at != std::string::npos) {
        std::string sa = b.substr(at + 1);
        sa = sa.substr(0, sa.find(':'));
        if (!sa.empty())
            p.sa = sa;
        b = b.substr(0, at);
    }
    const size_t sl = b.find('/');
    p.system = b.substr(0, sl);
    if (sl != std::string::npos)
        p.raga = b.substr(sl + 1);
    return p;
}
inline std::string east_spec(const East &p)
{
    return p.system.empty() ? "" : "raga:" + p.system + (p.raga.empty() ? "" : "/" + p.raga) + "@" + p.sa;
}

// THE CLAVITONE VARIANTS (tunelib.ChainsTuner and ChainsPianoTuner): two
// chains of pure fifths, by name -- Baroque, Romantic Meantone, Stretched
// Helmholtz, and those for pipes -- each its parameters, all to be changed:
// the KEY (the chain's position 3: home_key), the BRIDGE third (Helmholtz to
// Even: above it a bridge is its mirror on the key a tritone away), the
// OCTAVES (pure; a piano's; a piano's middle by 2:1; each instrument's own)
// and the ROUTE between the chains on stretched octaves. Each key's third and
// fifth from pure under its chip: on pure octaves the model's, exact, the
// counts against their proved ceilings and the two keys served; on stretched
// ones the table's, read from C4 to C5. cur: the tuning the scope chose (the
// rig's, the part's own); plays: what the part plays; shape: its table's.
// part: 1 the variants and the keys, 2 the bridge, octaves and route, 3 both
// (the phone shows them a page each). A change asks for the name at once
inline void draw_chains(App &a, float X, float Y, float W, float H, const std::string &cur, const std::string &plays, const J *shape,
                        bool scope, int part = 3)
{
    TuningUi &T = g_tn;
    const bool PH = a.ph, IP = a.tab;
    look::tray(a, X, Y, W, H, 9);
    // (what plays: by its name -- the scope's choice, else what the part plays -- or, on pure octaves, by
    //  its table whatever its name; this screen's ask held a moment)
    const Temper tt = temper_of(shape);
    ChainSpec cs;
    bool playing;
    if (!T.chains_mine.empty() && ImGui::GetTime() < T.chains_until)
        playing = chains_parts(T.chains_mine, &cs);
    else if (chains_parts(cur, &cs) || chains_parts(plays, &cs))
        playing = true;
    else if ((playing = tt.ok && tt.chains)) {
        cs.x = tt.x;
        cs.key = tt.key;
    }
    if (playing && !a.K.active) {
        T.ckey = cs.key;
        T.bridge = cs.x;
        T.coct = cs.oct;
        T.croute = cs.route;
    }
    ChainSpec want;
    want.x = T.bridge;
    want.key = T.ckey;
    want.oct = T.coct;
    want.route = T.croute;
    const int var = playing ? chain_variant_of(want) : -1;
    const float hx = heading(a, X + 12, Y + 10, nui::T("CLAVITONE"), "tn:key");   // i18n-skip (a help key)
    text(a, a.font, 14, hx, Y + 11, LCD,
         fit(a, a.font, 14, !playing ? std::string(nui::T("two chains of pure fifths"))
                            : var >= 0 ? std::string(nui::T(chain_variants()[(size_t)var].name))
                                       : std::string(nui::T("your own variant")),
             W - (hx - X) - 12));
    const auto &B = chain_bridges();
    const float lo = (float)B.front().x, hi = (float)B.back().x;
    bool ask = false;
    const float kx = X + 12;
    float y = Y + 40;
    // (cents from pure: whole cents from 10 up -- five figures would crowd the laptop's columns)
    auto cents = [](double v) {
        char b[16];
        if (std::fabs(v) < 0.05)
            return std::string("0");
        snprintf(b, sizeof b, std::fabs(v) < 9.95 ? "%+.1f" : "%+.0f", v);
        return std::string(b);
    };
    const double half = 1200.0 * std::log2(81.0 / 80.0) / 2;
    if (part & 1) {
        // THE VARIANTS, by name
        {
            std::vector<std::string> w;
            std::vector<bool> lit;
            for (size_t i = 0; i < chain_variants().size(); i++) {
                w.push_back(nui::T(chain_variants()[i].name));
                lit.push_back((int)i == var);
            }
            const int h = flow_buttons(a, "tncv", kx, y, W - 24, w, lit, 30);
            if (h >= 0) {
                const ChainSpec v = chain_variant_spec(chain_variants()[(size_t)h]);
                T.bridge = v.x;
                T.ckey = v.key;
                T.coct = v.oct;
                T.croute = v.route;
                ask = true;
            }
        }
        // THE KEYS, and under each its third and fifth: on pure octaves the model's (exact); else the table's
        const float kw = (W - 24) / 12, kh = PH ? 40 : IP ? 44 : 38, ky = y;
        double th[12], fi[12];
        const bool stretched = playing ? (T.coct != "pure" && tt.ok && !tt.pure) : false;
        const bool table = (!playing || stretched) && tt.ok;
        if (table)
            for (int i = 0; i < 12; i++) {
                th[i] = tt.th[i];
                fi[i] = tt.fi[i];
            }
        else
            chains_model(T.bridge, (T.ckey + 3) % 12, th, fi);
        for (int i = 0; i < 12; i++) {
            const std::string id = "tnck" + std::to_string(i);
            if (button(a, id.c_str(), kx + i * kw + 2, ky, kw - 4, kh, CH_KEY[i], playing && i == T.ckey, true, PH ? 21 : 14)) {
                T.ckey = i;
                ask = true;
            }
            text_c(a, a.font, 14, kx + i * kw + kw / 2, ky + kh + 6, th[i] <= 1e-4 ? OWN : th[i] <= half + 1e-4 ? LCD : SILK_DIM, cents(th[i]));
            text_c(a, a.font, 14, kx + i * kw + kw / 2, ky + kh + 8 + a.lh(14), std::fabs(fi[i]) < 1e-4 ? SILK_DIM : LCD, cents(fi[i]));
        }
        y = ky + kh + 6 + 2 * a.lh(14) + 10;
        if (!PH) {                      // (the phone's card is too short for it: its help says it)
            for (const auto &l : wrap(a, a.font, 14, nui::T("under each key: its third, then its fifth, cents from pure"), W - 24)) {
                text(a, a.font, 14, kx, y, SILK_DIM, l);
                y += a.lh(14) + 3;
            }
            y += 7;
        }
        // THE COUNTS, and the two keys served (home_key, far_key)
        int n0 = 0, n8 = 0;
        for (int i = 0; i < 12; i++) {
            n0 += th[i] <= 1e-4;
            n8 += th[i] <= half + 1e-4;
        }
        const int far = (T.ckey + 6) % 12;
        const double P = ch_P();
        std::vector<std::pair<std::string, ImU32>> lines;
        // (the ceilings are proved for pure octaves with no fifth wider than pure)
        const bool proved = !table || (tt.pure && !tt.wide);
        const std::string counts = proved ? TF("{0} pure thirds (at most 4); {1} within half a comma (at most 8)", {std::to_string(n0), std::to_string(n8)})
                                          : TF("{0} pure thirds; {1} within half a comma", {std::to_string(n0), std::to_string(n8)});
        auto keyline = [&](int k, int gap) {    // (a key's I, IV and V thirds and its ii's fifth, from the readouts)
            const double t1 = th[k], t4 = th[(k + 5) % 12], t5 = th[(k + 7) % 12], ii = fi[(k + 2) % 12];
            const bool same = std::fabs(t1 - t4) < 0.05 && std::fabs(t1 - t5) < 0.05;
            const std::string t = same ? cents(t1) : cents(t1) + "/" + cents(t4) + "/" + cents(t5);
            (void)gap;
            return std::make_pair(TF("{0} major: I, IV, V thirds {1}; ii's fifth {2}", {CH_KEY[k], t, cents(ii)}),
                                  std::max({t1, t4, t5}) <= half + 1e-6 ? LCD : SILK_DIM);
        };
        if (!playing && tt.ok) {        // (another tuning: what it is, then its counts)
            const std::string nm = tuner_words(plays, "").first;
            lines.push_back({tt.pure ? TF("{0} is not two chains of pure fifths", {nm}) : TF("{0}: stretched octaves, read from C4 to C5", {nm}), SILK_DIM});
            lines.push_back({counts, LCD});
        } else {
            if (stretched)
                lines.push_back({nui::T("stretched octaves: read from C4 to C5"), SILK_DIM});
            else if (playing && T.coct == "own")
                lines.push_back({nui::T("each piano on its own strings; shown here on pure octaves"), SILK_DIM});
            lines.push_back({counts, LCD});
            lines.push_back(keyline(T.ckey, 0));
            if (!PH)                    // (the phone's card is short: the far key in the help)
                lines.push_back(keyline(far, 1));
            (void)P;
        }
        if (!playing)
            lines.push_back({scope ? nui::T("tap a variant or a key to play it on this part") : nui::T("tap a variant or a key to play it on every part"), OWN});
        for (const auto &l : lines)
            for (const auto &w : wrap(a, a.font, 14, l.first, W - 24)) {
                text(a, a.font, 14, kx, y, l.second, w);
                y += a.lh(14) + 3;
            }
        y += 8;
    }
    if (part & 2) {
        // THE BRIDGE: a knob, its named stops beside it (none on the octaves route: three octaves join the chains)
        const float rowh = PH ? 40 : IP ? 44 : 30;
        if (T.croute == "octaves") {
            text(a, a.bold, 14, kx, y, SILK, nui::T("BRIDGE THIRD"));
            for (const auto &w : wrap(a, a.font, 14, nui::T("none: three octaves join the chains (on pure octaves, Helmholtz's)"), W - 24)) {
                text(a, a.font, 14, kx + text_w(a, a.bold, 14, nui::T("BRIDGE THIRD")) + 12, y, SILK_DIM, w);
                y += a.lh(14) + 3;
            }
            y += 10;
        } else {
            float kcw = 0;
            for (const auto &cb : B)
                kcw = std::max(kcw, text_w(a, a.font, 14, nui::T(cb.name)));
            kcw = std::max({PH ? 76.0f : IP ? 100.0f : 84.0f, text_w(a, a.bold, 14, nui::T("BRIDGE THIRD")), kcw, text_w(a, a.font, 14, "407.82 c")}) + 12;
            const float ksz = PH ? 70 : IP ? 72 : 76, kcx = X + W - 12 - kcw / 2, kcy = y + ksz / 2;
            float v01 = (float)((T.bridge - lo) / (hi - lo));
            std::vector<float> dets;
            for (const auto &cb : B)
                dets.push_back((float)((cb.x - lo) / (hi - lo)));
            const int f = knob(a, "tnbridge", kcx, kcy, ksz, v01, nui::T("BRIDGE THIRD"), chains_bridge_words(lo + v01 * (hi - lo)), false, dets, 0, false);
            if (f & (K_CHANGED | K_RESET)) {
                double xb = std::round((lo + v01 * (double)(hi - lo)) * 100.0) / 100.0;
                for (const auto &cb : B)
                    if (std::fabs(xb - cb.x) < 0.006)
                        xb = cb.x;
                T.bridge = std::max(B.front().x, std::min(B.back().x, xb));
            }
            if ((f & (K_ENDED | K_RESET)) || ((f & K_CHANGED) && !(f & K_ACTIVE)))
                ask = true;
            // (the named bridges as buttons too, left of the knob: four across, or two by two)
            const float lw = kcx - kcw / 2 - 12 - kx;
            float nw = 0;
            for (const auto &cb : B)
                nw = std::max(nw, text_w(a, a.bold, PH ? 21 : 14, nui::T(cb.name)));
            const int cols = nw + 16 <= (lw - 3 * 6) / 4 ? 4 : 2;
            const float bh = PH ? 40 : IP ? 44 : 34, bw = (lw - (cols - 1) * 6) / cols;
            for (size_t i = 0; i < B.size(); i++) {
                const std::string id = "tncb" + std::to_string(i);
                if (button(a, id.c_str(), kx + (i % cols) * (bw + 6), y + (i / cols) * (bh + 6), bw, bh, nui::T(B[i].name),
                           playing && std::fabs(T.bridge - B[i].x) < 0.006, true, PH ? 21 : 14)) {
                    T.bridge = B[i].x;
                    ask = true;
                }
            }
            y = std::max(y + ((B.size() + cols - 1) / cols) * (bh + 6), kcy + ksz / 2 + 2 * a.lh(14) + 10);
        }
        // THE OCTAVES and THE ROUTE: chips, each row its word at the left
        static const std::vector<std::pair<const char *, const char *>> OCT = {
            {"pure", N_("pure, 2:1")}, {"piano", N_("a piano's")}, {"middle", N_("a piano's middle, by 2:1")}, {"own", N_("each instrument's own")}};
        static const std::vector<std::pair<const char *, const char *>> ROUTE = {
            {"fifth", N_("a fifth up, two octaves down")}, {"fourth", N_("an octave down, a fourth")}, {"octaves", N_("three octaves, no bridge")}};
        const float lab = std::max(text_w(a, a.bold, 14, nui::T("OCTAVES")), text_w(a, a.bold, 14, nui::T("ROUTE"))) + 14;
        auto row = [&](const char *word, const char *id, const std::vector<std::pair<const char *, const char *>> &opts, std::string &cur_) {
            text(a, a.bold, 14, kx, y + (rowh - a.lh(14)) / 2, SILK, nui::T(word));
            std::vector<std::string> w;
            std::vector<bool> lit;
            for (const auto &o : opts) {
                w.push_back(nui::T(o.second));
                lit.push_back(playing && cur_ == o.first);
            }
            const int h = flow_buttons(a, id, kx + lab, y, W - 24 - lab, w, lit, 30);
            if (h >= 0 && cur_ != opts[(size_t)h].first) {
                cur_ = opts[(size_t)h].first;
                ask = true;
            }
        };
        row(N_("OCTAVES"), "tnoct", OCT, T.coct);
        row(N_("ROUTE"), "tnrt", ROUTE, T.croute);
        if (T.coct == "pure")                           // (where the card has room: its help says it too)
            for (const auto &w : wrap(a, a.font, 14, nui::T("on pure octaves the routes are one tuning (but three octaves: Helmholtz's bridge)"), W - 24)) {
                if (y + a.lh(14) > Y + H - 6)
                    break;
                text(a, a.font, 14, kx, y, SILK_DIM, w);
                y += a.lh(14) + 3;
            }
    }
    if (ask) {
        ChainSpec c;
        c.x = T.bridge;
        c.key = T.ckey;
        c.oct = T.coct;
        c.route = T.croute;
        const std::string nm = chains_name(c);
        T.chains_mine = nm;
        T.chains_until = ImGui::GetTime() + 2.0;
        if (scope)
            tn_take(call(a, "{\"call\":\"part_tuner_set\",\"row\":" + std::to_string(a.row) + ",\"name\":\"" + nm + "\"}"));
        else {
            T.pending = nm;
            tn_take(call(a, "{\"call\":\"tuner_set\",\"name\":\"" + nm + "\"}"));
        }
    }
}

inline void draw_tuning(App &a)
{
    TuningUi &T = g_tn;
    if (!T.t.is(J::OBJ) || T.row != a.row) {
        T.row = a.row;
        tn_take(call(a, "{\"call\":\"tuning\",\"open\":1,\"lists\":" + std::string(T.lists ? "0" : "1") + ",\"row\":" +
                           std::to_string(a.row) + "}"));
    }
    // (the iPad's: its card from y 210 to card_y1 + 6, two pages -- the tuners and their shape; the Eastern tuning)
    const bool IP = a.tab, PH = a.ph;   // (the phone's: its card from 106, five pages -- the tuners, the Clavitone variants and their bridge, the shape, the Eastern)
    static int page = 0, tpage = 0;
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = IP ? (PH ? 818 : 1113) : 1886, Y0 = PH ? 160 : IP ? 266 : 394, Y1 = card_y1(a),
                HY = PH ? 120 : IP ? 224 : 356;
    const float LH = a.lh(14) + (IP ? 3 : 4);
    const float TX = heading(a, X0, HY, nui::T("TUNING"), "tuning");   // (nui::T: the card's T is its state)
    if (PH) {
        const int h = phone_pages(a, "tnppage", TX, {nui::T("TUNERS"), nui::T("CLAVITONE"), nui::T("BRIDGE THIRD"), nui::T("SHAPE"), nui::T("EASTERN")}, tpage);
        if (h >= 0)
            tpage = h;
    } else
        text(a, a.font, 14, TX, HY + 1, OWN, T.scope ? nui::T("this part") : nui::T("every part"));
    if (IP && !PH) {
        static const char *PN[3] = {N_("TUNERS"), N_("CLAVITONE"), N_("EASTERN")};
        for (int pg = 0; pg < 3; pg++) {
            const std::string id = "tnpage" + std::to_string(pg);
            if (button(a, id.c_str(), page_kx(a, 3, pg, 300), 216, page_kw(a, 3), 44, nui::T(PN[pg]), page == pg, true, 21))
                page = pg;
        }
    }
    if (!T.t.is(J::OBJ) || !T.lists)
        return;
    const std::string tuner = str(&T.t, "tuner"), now = str(&T.t, "now");
    if (T.pending == tuner)
        T.pending.clear();
    const bool building = tuner != now;
    // THIS PART (the selected one): its own choice ("" its instrument's,
    // "rig"), what it plays ("" the rig's), its instrument's own tuner
    const J *pt = T.t.get("part");
    const std::string p_own = str(pt, "own"), p_plays = str(pt, "plays"), p_nat = str(pt, "natural");
    const bool natural = num(&T.t, "natural", 1) != 0;
    const std::string info = T.scope ? TF("this part plays {0}", {tuner_words(p_plays.empty() ? now : p_plays, "").first})
                           : building ? TF("building the patches in {0}\xe2\x80\xa6", {tuner_words(tuner, "").first})
                                      : TF("playing {0}", {tuner_words(now, "").first});
    const std::string info_ = fit(a, a.font, 14, info, IP ? 300 : 540);
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info_), PH ? 147 : HY + 1, building ? OWN : SILK_DIM, info_);
    if (building)
        a.animate = true;

    // THE TUNERS, grouped by what they are for
    // (the Clavitone tunings are its variants, on their own tiles below: their old names kept off the list)
    static const std::vector<std::pair<const char *, std::vector<std::string>>> GROUPS = {
        {N_("Equal"), {"gm2", "even"}},
        {N_("Historical temperaments"), {"werckmeister", "sankey", "meantone", "stretch"}},
        {N_("Period pianos"), {"pleyel"}}};
    static const std::vector<std::string> CLAVITONE_OLD = {"hybrid", "hybrid440", "hybridharm", "hybridharm440", "hybridmean",
                                                            "hybridmeanpiano", "stretchedhelmholtz"};
    std::vector<std::pair<std::string, std::vector<const std::pair<std::string, std::string> *>>> groups;
    // (the card's own tiles, before the tuners: which parts the tiles choose
    // for; this part's two of its own; natural tunings on or off -- a key
    // with '@', its name and line after it, a tab between)
    static std::vector<std::pair<std::string, std::string>> mine;
    mine.clear();
    mine.reserve(32);                   // (the groups point into it: never past its reserve)
    const std::string pname = str(pt, "name");
    mine.push_back({"@every", std::string(nui::T("Every part")) + "\t" + nui::T("the rig's tuning, the parts' own unchosen")});
    mine.push_back({"@this", std::string(nui::T("This part")) + "\t" + (pname.empty() ? std::string() : pname)});
    mine.push_back({"@inst", std::string(nui::T("As the instrument")) + "\t" +
                                 (p_nat.empty() ? std::string(nui::T("none of its own: the rig's"))
                                  : !natural ? TF("{0}, while natural tunings are on", {tuner_words(p_nat, "").first})
                                             : tuner_words(p_nat, "").first)});
    mine.push_back({"@rig", std::string(nui::T("The rig's")) + "\t" + tuner_words(now, "").first});
    mine.push_back({"@nat1", std::string(nui::T("On")) + "\t" + nui::T("each instrument in its own tuning")});
    mine.push_back({"@nat0", std::string(nui::T("Off")) + "\t" + nui::T("every voice in the rig's tuning")});
    // CONCERT PITCH: A4 for every tuning (the parts' own follow the rig's A), or each its own
    static const std::vector<std::pair<int, const char *>> PITCHES = {
        {0, N_("each tuning's own A: 415 baroque, 440 modern")},
        {415, N_("baroque chamber pitch")}, {430, N_("the classical era's")}, {435, N_("the French diapason normal, 1859")},
        {440, N_("the modern standard")}, {442, N_("many orchestras today")}, {466, N_("Chorton: the North German organs")}};
    const double pitch = num(&T.t, "pitch");
    for (const auto &pp : PITCHES)
        mine.push_back({"@cp" + std::to_string(pp.first),
                        (pp.first ? "A = " + std::to_string(pp.first) : std::string(nui::T("Each tuning's own"))) + "\t" + nui::T(pp.second)});
    // THE CLAVITONE VARIANTS, by name (the CLAVITONE page has their parameters)
    const size_t cv0 = mine.size();
    for (size_t i = 0; i < chain_variants().size(); i++) {
        const ChainSpec v = chain_variant_spec(chain_variants()[i]);
        mine.push_back({"@cv" + std::to_string(i), std::string(nui::T(chain_variants()[i].name)) + "\t" + tuner_words(chains_name(v), "").second});
    }
    groups.push_back({N_("Which parts"), {&mine[0], &mine[1]}});
    if (T.scope)
        groups.push_back({N_("This part"), {&mine[2], &mine[3]}});
    else {
        groups.push_back({N_("Natural tunings"), {&mine[4], &mine[5]}});
        std::vector<const std::pair<std::string, std::string> *> cps2;
        for (size_t i = 6; i < cv0; i++)
            cps2.push_back(&mine[i]);
        groups.push_back({N_("A4 for every tuning"), cps2});
    }
    {
        std::vector<const std::pair<std::string, std::string> *> cvs;
        for (size_t i = cv0; i < mine.size(); i++)
            cvs.push_back(&mine[i]);
        groups.push_back({N_("Clavitone variants"), cvs});
    }
    std::set<std::string> named(CLAVITONE_OLD.begin(), CLAVITONE_OLD.end());
    for (const auto &g : GROUPS) {
        std::vector<const std::pair<std::string, std::string> *> v;
        for (const auto &n : g.second) {
            named.insert(n);
            for (const auto &t : T.tuners)
                if (t.first == n)
                    v.push_back(&t);
        }
        groups.push_back({g.first, v});
    }
    std::vector<const std::pair<std::string, std::string> *> raga, other;
    for (const auto &t : T.tuners)
        if (t.first.rfind("raga:", 0) == 0)
            raga.push_back(&t);
        else if (!named.count(t.first))
            other.push_back(&t);
    if (!T.scope)                       // (a raga: the rig's, every part -- the Eastern tuning is a part's)
        groups.push_back({N_("Indian, every part"), raga});
    groups.push_back({N_("Other systems"), other});
    const float LW = PH ? X1 - X0 : IP ? 600 : 1070, cols = IP && !PH ? 2 : 3, gap = 8, tw = (LW - 10 - gap * (cols - 1)) / cols, th = 64, hh = 30;
    // (the layout, then the touch, then the drawing)
    struct Tile {
        const std::pair<std::string, std::string> *t;
        float x, y;
    };
    std::vector<Tile> tiles;
    std::vector<std::pair<std::string, float>> heads;
    float cy = 0;
    for (const auto &g : groups) {
        if (g.second.empty())
            continue;
        heads.push_back({g.first, cy});
        cy += hh;
        for (size_t i = 0; i < g.second.size(); i++)
            tiles.push_back({g.second[i], (i % (int)cols) * (tw + gap), cy + (i / (int)cols) * (th + gap)});
        cy += ((g.second.size() + (int)cols - 1) / (int)cols) * (th + gap) + 6;
    }
    ImVec2 tap;
    if (PH ? tpage == 0 : (!IP || page == 0)) {
    if (scroll_area(a, "tnlist", X0, Y0, LW, Y1 - Y0, cy, T.scroll, tap))
        for (const Tile &t : tiles)
            if (tap.x >= t.x && tap.x < t.x + tw && tap.y >= t.y && tap.y < t.y + th) {
                const std::string &k = t.t->first;
                if (k == "@every" || k == "@this")
                    T.scope = k == "@this";
                else if (k.rfind("@cv", 0) == 0) {     // (a Clavitone variant: its name, for the scope)
                    const std::string nm = chains_name(chain_variant_spec(chain_variants()[(size_t)atoi(k.c_str() + 3)]));
                    T.chains_mine = nm;
                    T.chains_until = ImGui::GetTime() + 2.0;
                    if (T.scope)
                        tn_take(call(a, "{\"call\":\"part_tuner_set\",\"row\":" + std::to_string(a.row) + ",\"name\":\"" + nm + "\"}"));
                    else {
                        T.pending = nm;
                        tn_take(call(a, "{\"call\":\"tuner_set\",\"name\":\"" + nm + "\"}"));
                    }
                } else if (k.rfind("@cp", 0) == 0)
                    tn_take(call(a, "{\"call\":\"pitch_set\",\"hz\":" + k.substr(3) + "}"));
                else if (k == "@nat1" || k == "@nat0")
                    tn_take(call(a, std::string("{\"call\":\"natural_set\",\"on\":") + (k == "@nat1" ? "1" : "0") + "}"));
                else if (T.scope)       // (this part's: "" its instrument's, "rig", a tuner)
                    tn_take(call(a, "{\"call\":\"part_tuner_set\",\"row\":" + std::to_string(a.row) + ",\"name\":\"" +
                                        (k == "@inst" ? std::string() : k == "@rig" ? std::string("rig") : k) + "\"}"));
                else {
                    T.pending = k;
                    tn_take(call(a, "{\"call\":\"tuner_set\",\"name\":\"" + k + "\"}"));
                }
            }
    dl()->PushClipRect(P(a, X0, Y0), P(a, X0 + LW, Y1), true);
    for (const auto &h : heads) {
        std::string up = nui::T(h.first);
        for (char &c : up)
            c = (char)toupper((unsigned char)c);
        text(a, a.bold, 14, X0, Y0 + h.second - T.scroll + 8, SILK, up);
    }
    for (const Tile &t : tiles) {
        const float x = X0 + t.x, y = Y0 + t.y - T.scroll;
        if (y + th < Y0 || y > Y1)
            continue;
        const std::string &k = t.t->first;
        const bool special = k[0] == '@';
        bool cur, pend;
        if (special) {
            ChainSpec ccs;
            const bool isv = k.rfind("@cv", 0) == 0;
            cur = isv ? chains_parts(T.scope ? (p_own.empty() ? p_plays : p_own) : tuner, &ccs) && chain_variant_of(ccs) == atoi(k.c_str() + 3)
                : k.rfind("@cp", 0) == 0 ? std::fabs(pitch - atof(k.c_str() + 3)) < 0.005
                : k == "@every" ? !T.scope : k == "@this" ? T.scope != 0 : k == "@inst" ? p_own.empty()
                : k == "@rig" ? p_own == "rig" : k == "@nat1" ? natural : !natural;
            pend = false;
        } else if (T.scope) {
            cur = k == p_own;
            pend = false;
        } else {
            cur = k == tuner && !building;
            pend = (k == tuner && building) || k == T.pending;
        }
        look::chip(a, x, y, tw, th, cur);
        if (pend)
            frame(a, x, y, tw, th, LCD, 8, 2.0f);
        std::pair<std::string, std::string> nm;
        if (special) {
            const size_t tb = t.t->second.find('\t');
            nm = {t.t->second.substr(0, tb), tb == std::string::npos ? std::string() : t.t->second.substr(tb + 1)};
        } else
            nm = tuner_words(k, t.t->second);
        // (a name too long for one line takes two, its line one fewer)
        const auto ns = wrap_max(a, a.font, 14, nm.first, tw - 20, 2);
        for (size_t i = 0; i < ns.size(); i++)
            text(a, a.font, 14, x + 10, y + (IP ? 6 : 8) + i * LH, cur ? LCD_BG : LCD, ns[i]);
        const auto ls = wrap_max(a, a.font, 14, nm.second, tw - 20, 3 - ns.size());
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, x + 10, y + (IP ? 9 : 11) + (i + ns.size()) * LH, cur ? LCD_BG : SILK_DIM, ls[i]);
    }
    dl()->PopClipRect();

    // THE SHAPE: an octave in cents from equal temperament; each octave's stretch across the keyboard
    }
    const float SX = PH ? X0 : X0 + LW + 12, SW = X1 - SX, SH = IP ? Y1 - Y0 : 330;
    // YOUR KEY: the phone's and the iPad's a page; the laptop's the right column, by its two keys in the heading row
    const std::string scoped = T.scope ? p_own : tuner;
    // (what the scope plays, and its shape: this part's where it plays its own, else the rig's)
    const bool kpart = T.scope && pt && pt->get("shape");
    const J *kshape = kpart ? pt->get("shape") : T.t.get("shape");
    const std::string kplays = kpart ? p_plays : tuner;
    if (!IP) {
        static const char *KP[2] = {N_("SHAPE"), N_("CLAVITONE")};
        float kx_ = SX;
        for (int i = 0; i < 2; i++) {
            const float w = text_w(a, a.bold, 14, nui::T(KP[i])) + 36;
            if (button(a, (std::string("tnkpage") + std::to_string(i)).c_str(), kx_, HY - 6, w, 32, nui::T(KP[i]), T.kpage == i))
                T.kpage = i;
            kx_ += w + 6;
        }
        if (T.kpage == 1) {
            draw_chains(a, SX, Y0, SW, Y1 - Y0, scoped, kplays, kshape, T.scope != 0);
            return;
        }
    } else if (PH ? (tpage == 1 || tpage == 2) : page == 1) {
        draw_chains(a, X0, Y0, X1 - X0, Y1 - Y0, scoped, kplays, kshape, T.scope != 0, PH ? tpage : 3);
        return;
    }
    if (PH ? tpage == 3 : (!IP || page == 0)) {
    look::tray(a, SX, Y0, SW, SH, 9);
    const float tsx = heading(a, SX + 12, Y0 + 10, nui::T("THE TUNING"), "tn:shape");   // i18n-skip (a help key)
    // (this part's shape where it plays its own -- else the rig's)
    const bool pshape = T.scope && pt && pt->get("shape");
    const J *shape = pshape ? pt->get("shape") : T.t.get("shape");
    const double a4 = num(shape, "a4");
    text(a, a.font, 14, tsx, Y0 + 11, LCD, tuner_words(pshape ? p_plays : tuner, "").first + (a4 > 0 ? " \xc2\xb7 A4 = " + jnum(a4) + " Hz" : ""));
    const J *cents = shape ? shape->get("cents") : nullptr;
    auto cv = [&](int n, double &v) {
        if (!cents || !cents->is(J::ARR) || n >= (int)cents->a.size() || !cents->a[(size_t)n].is(J::NUM))
            return false;
        v = cents->a[(size_t)n].d();
        return true;
    };
    // (the phone's two graphs side by side: its page is wide, not tall)
    const float gx = SX + 14, gw = PH ? SW / 2 - 28 : SW - 28, gxb = PH ? SX + SW / 2 + 14 : gx;
    if (!cents || !cents->is(J::ARR)) {
        text(a, a.font, 14, gx, Y0 + 150, SILK_DIM, nui::T("this tuner has no fixed table (it follows the file or the music)"));
    } else {
        static const char *NN[12] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
        const float top = Y0 + 50, h1 = 96, mid = top + h1 / 2, sc = (h1 / 2) / 30, bw = gw / 12;
        text(a, a.font, 14, gx, Y0 + 32, SILK_DIM, nui::T("C4 to B4, cents from equal temperament"));
        rect(a, gx, mid, gw, 1, IM_COL32(0x3a, 0x3f, 0x45, 255), 0);
        for (int i = 0; i < 12; i++) {
            const float x = gx + i * bw;
            double v;
            if (cv(60 + i, v)) {
                const float hh_ = std::max(-h1 / 2, std::min(h1 / 2, (float)v * sc));
                rect(a, x + bw * 0.2f, hh_ > 0 ? mid - hh_ : mid, bw * 0.6f, std::max(1.0f, std::fabs(hh_)), LCD, 0);
                char b[16];
                snprintf(b, sizeof b, std::fabs(v) < 10 ? "%+.1f" : "%+.0f", v);
                text_c(a, a.font, 14, x + bw / 2, hh_ > 0 ? mid - hh_ - a.lh(14) - 3 : mid - hh_ + 3, SILK, b);
            }
            text_c(a, a.font, 14, x + bw / 2, top + h1 + 4, SILK_DIM, NN[i]);
        }
        // (the stretch's scale in a margin of its own at the right, clear of the octaves' names)
        const float top2 = PH ? top : top + h1 + 50, h2 = 90, mid2 = top2 + h2 / 2, sc2 = (h2 / 2) / 40, gw2 = gw - text_w(a, a.font, 14, "+40") - 12;
        text(a, a.font, 14, gxb, top2 - (PH ? 18 : 22), SILK_DIM, fit(a, a.font, 14, nui::T("A0 to C8: each octave's stretch from 2:1, in cents"), gw));
        rect(a, gxb, mid2, gw2, 1, IM_COL32(0x3a, 0x3f, 0x45, 255), 0);
        dl()->PathClear();
        for (int n = 21; n <= 108; n++) {
            double v, b;
            if (!cv(n, v) || !cv(60 + n % 12, b))
                continue;
            const float x = gxb + (n - 21) / 87.0f * gw2, yy = mid2 - std::max(-h2 / 2, std::min(h2 / 2, (float)(v - b) * sc2));
            dl()->PathLineTo(P(a, x, yy));
            if (n % 12 == 0)
                text_c(a, a.font, 14, x, top2 + h2 + 2, SILK_DIM, "C" + std::to_string(n / 12 - 1));
        }
        dl()->PathStroke(LCD, 0, 2.0f * a.k);
        text(a, a.font, 14, gxb + gw - text_w(a, a.font, 14, "+40"), top2, SILK_DIM, "+40");
        text(a, a.font, 14, gxb + gw - text_w(a, a.font, 14, "-40"), top2 + h2 - 14, SILK_DIM, "-40");
    }

    // THE EASTERN TUNING the Indian voices' parts play
    }
    if (PH ? tpage != 4 : IP && page != 2)
        return;
    // (the iPad's Eastern tuning a page across the card)
    const float EX = IP ? X0 : SX, EW = IP ? X1 - X0 : SW, EY = IP ? Y0 : Y0 + SH + 10;
    look::tray(a, EX, EY, EW, Y1 - EY, 9);
    text(a, a.font, 14, heading(a, EX + 12, EY + 10, nui::T("EASTERN TUNING"), "tn:east"), EY + 11, LCD, nui::T("the Indian voices' parts"));   // i18n-skip (a help key)
    if (!T.east_mine.empty() && ImGui::GetTime() > T.east_until)
        T.east_mine.clear();
    East p = east_parts(T.east_mine.empty() ? str(&T.t, "eastern") : T.east_mine);
    const bool measured = p.system.rfind("sung_", 0) == 0 || T.measured;
    bool changed = false;
    float ey = EY + 36;
    {
        std::vector<std::string> w = {nui::T("Off")};
        std::vector<bool> lit = {p.system.empty() && !T.measured};
        std::vector<std::string> sys;
        for (const auto &s : T.systems)
            if (s.rfind("sung_", 0) != 0) {
                sys.push_back(s);
                w.push_back(eastern_name(s));
                lit.push_back(s == p.system);
            }
        bool any_meas = false;          // (none ship now: licences.md L5 -- the button only when there are some)
        for (const auto &s : T.systems)
            any_meas = any_meas || s.rfind("sung_", 0) == 0;
        if (any_meas) {
            w.push_back(nui::T("measured ragas\xe2\x80\xa6"));
            lit.push_back(measured);
        }
        const int h = flow_buttons(a, "tnsys", EX + 12, ey, EW - 24, w, lit);
        if (h == 0) {
            p.system.clear();
            p.raga.clear();
            T.measured = false;
            changed = true;
        } else if (any_meas && h == (int)w.size() - 1) {
            T.measured = true;
        } else if (h > 0) {
            p.system = sys[(size_t)h - 1];
            T.measured = false;
            changed = true;
        }
    }
    if (measured) {
        std::vector<std::string> w, sys;
        std::vector<bool> lit;
        for (const auto &s : T.systems)
            if (s.rfind("sung_", 0) == 0) {
                w.push_back(eastern_name(s));
                sys.push_back(s);
                lit.push_back(s == p.system);
            }
        const int h = flow_buttons(a, "tnmeas", EX + 12, ey, EW - 24, w, lit, 26);
        if (h >= 0) {
            p.system = sys[(size_t)h];
            p.raga.clear();
            changed = true;
        }
    } else if (!p.system.empty()) {
        std::vector<std::string> w = {nui::T("No raga")};
        std::vector<bool> lit = {p.raga.empty()};
        for (const auto &r : T.ragas) {
            w.push_back(r);
            lit.push_back(r == p.raga);
        }
        const int h = flow_buttons(a, "tnraga", EX + 12, ey, EW - 24, w, lit, 26);
        if (h >= 0) {
            p.raga = h ? T.ragas[(size_t)h - 1] : "";
            changed = true;
        }
    }
    if (!p.system.empty()) {
        static const std::vector<std::string> SA = {"c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"};
        std::vector<std::string> w;
        std::vector<bool> lit;
        for (const auto &k : SA) {
            std::string u = k;
            u[0] = (char)toupper((unsigned char)u[0]);
            w.push_back(u);
            lit.push_back(k == p.sa);
        }
        text(a, a.bold, 14, EX + 12, ey + ((IP ? 44 : 30) - a.lh(14)) / 2, SILK, nui::T("SA"));
        const int h = flow_buttons(a, "tnsa", EX + 50, ey, EW - 62, w, lit, 30);
        if (h >= 0) {
            p.sa = SA[(size_t)h];
            changed = true;
        }
    }
    std::string sa_up = p.sa;
    if (!sa_up.empty())
        sa_up[0] = (char)toupper((unsigned char)sa_up[0]);
    std::string say;
    if (p.system.empty())
        say = nui::T("Off: the Indian instruments play the tuner above.");
    else {
        std::string sys = p.system;
        if (sys.rfind("sung_", 0) == 0) {
            sys = sys.substr(5);
            std::replace(sys.begin(), sys.end(), '_', ' ');
            sys = TF("raga {0} as measured", {sys});
        }
        say = p.raga.empty() ? TF("The Indian instruments' parts play {0}, Sa on {1} (unless the tuner above is itself Indian).", {sys, sa_up})
                             : TF("The Indian instruments' parts play {0}, raga {1}, Sa on {2} (unless the tuner above is itself Indian).",
                                  {sys, p.raga, sa_up});
    }
    for (const auto &l : wrap(a, a.font, 14, say, EW - 24)) {
        text(a, a.font, 14, EX + 12, ey, SILK_DIM, l);
        ey += LH;
    }
    if (changed) {
        T.east_mine = east_spec(p);
        T.east_until = ImGui::GetTime() + 1.5;
        tn_take(call(a, "{\"call\":\"eastern_set\",\"spec\":\"" + T.east_mine + "\"}"));
        if (T.east_mine.empty())
            T.east_mine = " ";          // (Off held too: a spec no system parses)
    }
}

}  // namespace nui
