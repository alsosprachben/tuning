// THE SHAPING PASS: a name as stored (logical order, maybe decomposed) made
// into what Dear ImGui draws -- one glyph per codepoint, left to right:
//   - composed (NFC) where code7 has the letter: "Cafe" + U+0301 -> "Café";
//   - Arabic joined: each letter its isolated, initial, medial or final form
//     (the presentation forms code7 draws), lam-alef its ligature;
//   - right-to-left runs (Hebrew, Arabic) reversed, numbers inside them kept
//     left to right, brackets mirrored (a reduced Unicode bidi algorithm,
//     enough for one line: no embeddings or isolates);
//   - a mark kept after its letter, where bdf.h draws it over that letter.
// Used where text is drawn or measured (app.h text, text_w; look.h
// lcd_text), never where it is stored, cut or compared: fit() and wrap() cut
// the logical string, and its cut is then shaped.
#pragma once

#include <algorithm>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace nui {

#include "shape_tables.inc"

template <size_t N, size_t M>
inline const uint32_t *sh_find(const uint32_t (&t)[N][M], uint32_t cp)     // (ranges by their first, lo..hi)
{
    size_t lo = 0, hi = N;
    while (lo < hi) {
        size_t mid = (lo + hi) / 2;
        if (t[mid][1] < cp)
            lo = mid + 1;
        else
            hi = mid;
    }
    return lo < N && t[lo][0] <= cp && cp <= t[lo][1] ? t[lo] : nullptr;
}
// (code7's Private Use page for Devanagari: U+E900 + a consonant's offset its
//  half form (स् U+E938); U+E980.. marks (the reph र्, the rakaar ्र); U+E9A0..
//  the ligatures क्ष ज्ञ त्र श्र)
static const uint32_t SH_DEVA_HALF = 0xE900, SH_REPH = 0xE980, SH_RAKAAR = 0xE981, SH_DEVA_LIG = 0xE9A0;
inline bool sh_is_mark(uint32_t cp)
{
    return (cp >= 0xE980 && cp <= 0xE98F) || sh_find(SH_MARK, cp) != nullptr;
}
inline int sh_bidi(uint32_t cp)
{
    const uint32_t *r = sh_find(SH_BIDI, cp);
    return r ? (int)r[2] : 0;
}
inline const uint32_t *sh_arabic(uint32_t cp)
{
    size_t n = sizeof SH_ARABIC / sizeof SH_ARABIC[0];
    auto it = std::lower_bound(SH_ARABIC, SH_ARABIC + n, cp, [](const uint32_t (&e)[6], uint32_t c) { return e[0] < c; });
    return it != SH_ARABIC + n && (*it)[0] == cp ? *it : nullptr;
}
inline uint32_t sh_compose(uint32_t a, uint32_t b)
{
    size_t n = sizeof SH_COMPOSE / sizeof SH_COMPOSE[0];
    auto it = std::lower_bound(SH_COMPOSE, SH_COMPOSE + n, std::make_pair(a, b), [](const uint32_t (&e)[3], std::pair<uint32_t, uint32_t> k) {
        return e[0] != k.first ? e[0] < k.first : e[1] < k.second;
    });
    return it != SH_COMPOSE + n && (*it)[0] == a && (*it)[1] == b ? (*it)[2] : 0;
}

inline void sh_decode(const std::string &s, std::vector<uint32_t> &out)
{
    for (size_t i = 0; i < s.size();) {
        unsigned char c = (unsigned char)s[i];
        uint32_t cp;
        int n;
        if (c < 0x80)
            cp = c, n = 1;
        else if ((c & 0xE0) == 0xC0)
            cp = c & 0x1F, n = 2;
        else if ((c & 0xF0) == 0xE0)
            cp = c & 0x0F, n = 3;
        else if ((c & 0xF8) == 0xF0)
            cp = c & 0x07, n = 4;
        else
            cp = 0xFFFD, n = 1;
        if (i + n > s.size())
            n = 1, cp = 0xFFFD;
        for (int k = 1; k < n; k++)
            cp = cp << 6 | ((unsigned char)s[i + k] & 0x3F);
        out.push_back(cp);
        i += n;
    }
}
inline void sh_encode(uint32_t cp, std::string &o)
{
    if (cp < 0x80)
        o += (char)cp;
    else if (cp < 0x800)
        o += (char)(0xC0 | cp >> 6), o += (char)(0x80 | (cp & 0x3F));
    else if (cp < 0x10000)
        o += (char)(0xE0 | cp >> 12), o += (char)(0x80 | (cp >> 6 & 0x3F)), o += (char)(0x80 | (cp & 0x3F));
    else
        o += (char)(0xF0 | cp >> 18), o += (char)(0x80 | (cp >> 12 & 0x3F)), o += (char)(0x80 | (cp >> 6 & 0x3F)),
            o += (char)(0x80 | (cp & 0x3F));
}

// (does it need the pass at all: a mark, a right-to-left or Arabic letter)
inline bool sh_needs(const std::vector<uint32_t> &u)
{
    for (uint32_t c : u)
        if (c >= 0x300 && (sh_is_mark(c) || sh_bidi(c) == 1 || sh_bidi(c) == 2 || sh_bidi(c) == 4 ||
                           (c >= 0x900 && c <= 0x97F) || c == 0x0E33))
            return true;
    return false;
}

// ARABIC JOINING, in logical order: each letter's form from whether it joins
// the letter before it and the one after (marks between are transparent)
inline void sh_arabic_join(std::vector<uint32_t> &u)
{
    auto jt = [](uint32_t c) -> int {          // ('U' none, 'R', 'D', 'C'; 'T' a mark; 0 not Arabic)
        if (c == 0x200D)
            return 'C';
        if (sh_is_mark(c))
            return 'T';
        const uint32_t *e = sh_arabic(c);
        return e ? (int)e[1] : 0;
    };
    const size_t n = u.size();
    std::vector<int> t(n);
    for (size_t i = 0; i < n; i++)
        t[i] = jt(u[i]);
    auto prev = [&](size_t i) -> int {          // (the nearest letter before, past the marks)
        while (i-- > 0)
            if (t[i] != 'T')
                return t[i];
        return 0;
    };
    auto next = [&](size_t i) -> int {
        for (size_t k = i + 1; k < n; k++)
            if (t[k] != 'T')
                return t[k];
        return 0;
    };
    std::vector<uint32_t> o;
    o.reserve(n);
    for (size_t i = 0; i < n; i++) {
        const uint32_t *e = sh_arabic(u[i]);
        if (!e || t[i] == 'C') {
            o.push_back(u[i]);
            continue;
        }
        const int p = prev(i), x = next(i);
        const bool jp = (p == 'D' || p == 'C') && (t[i] == 'R' || t[i] == 'D');
        // (lam then alef: one ligature, final if the lam is joined to the letter before)
        if (u[i] == 0x0644 && i + 1 < n) {
            uint32_t lig = 0;
            for (auto &la : SH_LAMALEF)
                if (la[0] == u[i + 1])
                    lig = la[1];
            if (lig) {
                o.push_back(jp ? lig + 1 : lig);
                i++;
                continue;
            }
        }
        const bool jn = (t[i] == 'D') && (x == 'R' || x == 'D' || x == 'C');
        uint32_t f = jp && jn ? e[5] : jp ? e[3] : jn ? e[4] : e[2];
        o.push_back(f ? f : u[i]);
    }
    u.swap(o);
}

// THE BIDI ORDER of one line: levels from the classes (W1-W7, N1-N2, I1-I2),
// then runs reversed from the highest level (L2), each letter's marks kept
// after it; brackets in a right-to-left run mirrored
// (base: the line's direction -- 0 left to right, the interface's (English,
//  its lists left-aligned: a Hebrew name keeps its .mid at the end); 1 right
//  to left; -1 from its first strong letter, as a paragraph on its own)
inline void sh_bidi_order(std::vector<uint32_t> &u, int base = 0)
{
    enum { L = 0, Rr = 1, AL = 2, EN = 3, AN = 4, ES = 5, ET = 6, CS = 7, N = 8, NSM = 9 };
    const size_t n = u.size();
    std::vector<int> t(n);
    for (size_t i = 0; i < n; i++) {
        t[i] = sh_is_mark(u[i]) ? NSM : sh_bidi(u[i]);
        if (base < 0 && (t[i] == L || t[i] == Rr || t[i] == AL))
            base = t[i] == L ? 0 : 1;
    }
    if (base < 0)
        base = 0;
    const int sos = base ? Rr : L;
    for (size_t i = 0; i < n; i++)                          // W1: a mark takes the class before it
        if (t[i] == NSM)
            t[i] = i ? t[i - 1] : sos;
    int strong = sos;                                       // W2, W3
    for (size_t i = 0; i < n; i++) {
        if (t[i] == L || t[i] == Rr || t[i] == AL)
            strong = t[i];
        if (t[i] == EN && strong == AL)
            t[i] = AN;
    }
    for (size_t i = 0; i < n; i++)
        if (t[i] == AL)
            t[i] = Rr;
    for (size_t i = 1; i + 1 < n; i++) {                    // W4
        if (t[i] == ES && t[i - 1] == EN && t[i + 1] == EN)
            t[i] = EN;
        else if (t[i] == CS && (t[i - 1] == EN || t[i - 1] == AN) && t[i + 1] == t[i - 1])
            t[i] = t[i - 1];
    }
    for (size_t i = 0; i < n; i++) {                        // W5: ET beside EN
        if (t[i] != ET)
            continue;
        size_t j = i;
        while (j < n && t[j] == ET)
            j++;
        if ((i > 0 && t[i - 1] == EN) || (j < n && t[j] == EN))
            for (size_t k = i; k < j; k++)
                t[k] = EN;
        i = j - 1;
    }
    for (size_t i = 0; i < n; i++)                          // W6
        if (t[i] == ES || t[i] == ET || t[i] == CS)
            t[i] = N;
    strong = sos;                                           // W7
    for (size_t i = 0; i < n; i++) {
        if (t[i] == L || t[i] == Rr)
            strong = t[i];
        if (t[i] == EN && strong == L)
            t[i] = L;
    }
    auto dir = [](int c) { return c == L ? L : Rr; };       // (numbers count as R for the neutrals)
    // N0: a bracket pair takes one direction -- the line's if a letter inside
    // has it; else the other if a letter inside has that and so does the
    // context before the pair -- so "(2)" stays a pair beside Hebrew
    {
        std::vector<std::pair<size_t, size_t>> pairs;
        std::vector<std::pair<uint32_t, size_t>> open;
        for (size_t i = 0; i < n; i++) {
            if (t[i] != N)
                continue;
            const uint32_t c = u[i];
            if (c == '(' || c == '[' || c == '{')
                open.push_back({c, i});
            else if (c == ')' || c == ']' || c == '}') {
                const uint32_t want = c == ')' ? '(' : c == ']' ? '[' : '{';
                for (size_t k = open.size(); k-- > 0;)
                    if (open[k].first == want) {
                        pairs.push_back({open[k].second, i});
                        open.resize(k);
                        break;
                    }
            }
        }
        std::sort(pairs.begin(), pairs.end());
        const int e = base ? Rr : L;
        for (auto &pr : pairs) {
            bool same = false, other = false;
            for (size_t k = pr.first + 1; k < pr.second; k++) {
                if (t[k] == N || t[k] >= 0x100)
                    continue;
                (dir(t[k]) == e ? same : other) = true;
            }
            int d = -1;
            if (same)
                d = e;
            else if (other) {
                int before = sos;
                for (size_t k = pr.first; k-- > 0;)
                    if (t[k] != N && t[k] < 0x100) {
                        before = dir(t[k]);
                        break;
                    }
                d = before != e ? before : e;
            }
            if (d >= 0) {
                t[pr.first] = t[pr.second] = d;
                for (size_t k = pr.second + 1; k < n && sh_is_mark(u[k]); k++)
                    t[k] = d;
            }
        }
    }
    for (size_t i = 0; i < n; i++) {                        // N1, N2
        if (t[i] != N)
            continue;
        size_t j = i;
        while (j < n && t[j] == N)
            j++;
        const int a = i ? dir(t[i - 1]) : sos, b = j < n ? dir(t[j]) : sos;
        const int d = a == b ? a : (base ? Rr : L);
        for (size_t k = i; k < j; k++)
            t[k] = d == L ? 0x100 : 0x101;                  // (resolved neutrals, marked)
        i = j - 1;
    }
    std::vector<int> lv(n);
    int maxl = base;
    for (size_t i = 0; i < n; i++) {
        int c = t[i] == 0x100 ? L : t[i] == 0x101 ? Rr : t[i];
        if (base == 0)
            lv[i] = c == L ? 0 : c == Rr ? 1 : 2;
        else
            lv[i] = c == Rr ? 1 : 2;
        maxl = std::max(maxl, lv[i]);
    }
    // (clusters: a letter and the marks after it, moved as one)
    std::vector<std::pair<size_t, size_t>> cl;
    for (size_t i = 0; i < n; i++) {
        if (i && sh_is_mark(u[i]) && !cl.empty())
            cl.back().second = i + 1;
        else
            cl.push_back({i, i + 1});
    }
    const int minodd = 1;
    for (int l = maxl; l >= minodd; l--) {
        for (size_t i = 0; i < cl.size(); i++) {
            if (lv[cl[i].first] < l)
                continue;
            size_t j = i;
            while (j < cl.size() && lv[cl[j].first] >= l)
                j++;
            std::reverse(cl.begin() + i, cl.begin() + j);
            i = j;
        }
    }
    std::vector<uint32_t> o;
    o.reserve(n);
    for (auto &c : cl)
        for (size_t k = c.first; k < c.second; k++) {
            uint32_t cp = u[k];
            if (lv[k] & 1)
                for (auto &m : SH_MIRROR)
                    if (m[0] == cp) {
                        cp = m[1];
                        break;
                    }
            o.push_back(cp);
        }
    u.swap(o);
}

// THAI: sara am (ำ) as its circle (ํ, a mark over the letter, under a tone
// mark) and sara aa (า), as Thai fonts draw it. Thai is stored in the order
// it is seen; its vowels above and below and its tone marks are marks.
inline void sh_thai(std::vector<uint32_t> &u)
{
    std::vector<uint32_t> o;
    o.reserve(u.size() + 2);
    for (uint32_t c : u) {
        if (c == 0x0E33)
            o.push_back(0x0E4D), o.push_back(0x0E32);
        else
            o.push_back(c);
    }
    u.swap(o);
}

// DEVANAGARI: each cluster -- consonants joined by viramas, then its vowel
// signs -- drawn as code7 can: a consonant before another its half form
// (or a visible virama where it has none), र before another the reph (a mark
// over the cluster's end), र after another the rakaar (a mark under it),
// क्ष ज्ञ त्र श्र their ligatures, and the short i (ि) moved before the cluster
inline bool sh_deva_cons(uint32_t c) { return (c >= 0x915 && c <= 0x939) || (c >= 0x958 && c <= 0x95F) || (c >= 0x978 && c <= 0x97F); }
inline bool sh_deva_has_half(uint32_t c)
{
    // (the consonants with a stem to drop; ङ छ ट ठ ड ढ द ह र have none, nor ऱ ड़ ढ़; code7t draws the rest)
    switch (c) {
    case 0x919: case 0x91B: case 0x91F: case 0x920: case 0x921: case 0x922: case 0x926: case 0x939: case 0x930:
    case 0x931: case 0x95C: case 0x95D:
        return false;
    }
    return sh_deva_cons(c);
}
inline void sh_devanagari(std::vector<uint32_t> &u)
{
    const uint32_t VIRAMA = 0x94D, NUKTA = 0x93C, RA = 0x930, I = 0x93F;
    std::vector<uint32_t> o;
    o.reserve(u.size() + 4);
    const size_t n = u.size();
    for (size_t i = 0; i < n;) {
        if (!sh_deva_cons(u[i])) {
            o.push_back(u[i++]);
            continue;
        }
        // (the cluster's consonants, each with its nukta)
        std::vector<std::pair<uint32_t, bool>> cs;
        bool dead = false;
        while (i < n && sh_deva_cons(u[i])) {
            bool nk = i + 1 < n && u[i + 1] == NUKTA;
            cs.push_back({u[i], nk});
            i += nk ? 2 : 1;
            if (i < n && u[i] == VIRAMA) {
                if (i + 1 < n && sh_deva_cons(u[i + 1])) {
                    i++;
                    continue;
                }
                dead = true;                    // (a virama ending the cluster: drawn)
                i++;
            }
            break;
        }
        // (its vowel signs and marks)
        std::vector<uint32_t> ms;
        bool short_i = false;
        while (i < n && ((u[i] >= 0x900 && u[i] <= 0x903) || (u[i] >= 0x93A && u[i] <= 0x94F && u[i] != VIRAMA) ||
                         (u[i] >= 0x955 && u[i] <= 0x957) || u[i] == 0x962 || u[i] == 0x963)) {
            if (u[i] == I)
                short_i = true;
            else
                ms.push_back(u[i]);
            i++;
        }
        const bool reph = cs.size() >= 2 && cs[0].first == RA && !cs[0].second;
        if (reph)
            cs.erase(cs.begin());
        if (short_i)
            o.push_back(I);
        for (size_t k = 0; k < cs.size(); k++) {
            const uint32_t c = cs[k].first;
            const bool last = k + 1 == cs.size();
            if (!last && !cs[k].second && !cs[k + 1].second) {
                const uint32_t d = cs[k + 1].first;
                uint32_t lig = c == 0x915 && d == 0x937 ? 0 : c == 0x91C && d == 0x91E ? 1 : c == 0x924 && d == RA ? 2
                             : c == 0x936 && d == RA ? 3 : 0xFF;
                if (lig != 0xFF) {
                    o.push_back(SH_DEVA_LIG + lig);
                    k++;
                    if (k + 1 < cs.size())
                        o.push_back(VIRAMA);
                    continue;
                }
                if (d == RA) {                   // (the rakaar: the consonant whole, its stroke under)
                    o.push_back(c);
                    o.push_back(SH_RAKAAR);
                    k++;
                    if (k + 1 < cs.size())
                        o.push_back(VIRAMA);
                    continue;
                }
            }
            if (last) {
                o.push_back(c);
                if (cs[k].second)
                    o.push_back(NUKTA);
            } else if (!cs[k].second && sh_deva_has_half(c))
                o.push_back(SH_DEVA_HALF + (c - 0x900));
            else {
                o.push_back(c);
                if (cs[k].second)
                    o.push_back(NUKTA);
                o.push_back(VIRAMA);
            }
        }
        if (dead)
            o.push_back(VIRAMA);
        for (uint32_t m : ms)
            o.push_back(m);
        if (reph)
            o.push_back(SH_REPH);
    }
    u.swap(o);
}

inline std::string shape_uncached(const std::string &s)
{
    std::vector<uint32_t> u;
    sh_decode(s, u);
    if (!sh_needs(u))
        return s;
    // NFC: a letter and the marks after it composed where a character is them
    std::vector<uint32_t> c;
    c.reserve(u.size());
    for (uint32_t cp : u) {
        uint32_t k;
        if (!c.empty() && sh_is_mark(cp) && (k = sh_compose(c.back(), cp)))
            c.back() = k;
        else
            c.push_back(cp);
    }
    sh_arabic_join(c);
    sh_thai(c);
    sh_devanagari(c);
    sh_bidi_order(c);
    std::string o;
    o.reserve(s.size() + 8);
    for (uint32_t cp : c)
        sh_encode(cp, o);
    return o;
}

inline std::string shape(const std::string &s)
{
    bool ascii = true;
    for (unsigned char ch : s)
        if (ch >= 0x80) {
            ascii = false;
            break;
        }
    if (ascii)
        return s;
    static std::unordered_map<std::string, std::string> cache;
    auto it = cache.find(s);
    if (it != cache.end())
        return it->second;
    if (cache.size() > 4096)
        cache.clear();
    return cache.emplace(s, shape_uncached(s)).first->second;
}

}  // namespace nui
