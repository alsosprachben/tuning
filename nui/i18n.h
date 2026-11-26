// THE INTERFACE'S LANGUAGE: every text a player reads is written in English
// in the source, wrapped -- T("PARTS") -- and looked up in the language's
// table, ui/lang/<code>.json ({"English": "translation", ...}, keyed by the
// English as gettext's catalogues are); a text the table lacks stays English.
//   T("...")            a text as it is drawn
//   TF("... {0} ...", {a, b})   a text with values, {n} in the order the
//                       language puts them (Japanese reorders them)
//   N_("...")           a text kept in a list (a static array of labels):
//                       marked for the catalogue, translated where it is
//                       drawn, T(list[i]) -- so a language chosen later
//                       reaches it too
// The catalogue's English (ui/lang/strings.txt) and each table's checks are
// examples/i18n_strings.py's. The language is the session's "language" (the
// Setup card's LANGUAGE row), "auto" the system's first that has a table.
#pragma once

#include <cstring>
#include <initializer_list>
#include <string>
#include <unordered_map>

#include "../native/session.h"

#define N_(s) s

namespace nui {

struct I18n {
    std::string code = "en";                                  // (the language drawn)
    std::unordered_map<std::string, std::string> t;           // (English -> its translation)
    // (a literal's address -> its English and its text, for T() each frame; the English kept and compared,
    //  so a passing buffer that reuses an address is looked up again, never given another's text)
    std::unordered_map<const char *, std::pair<std::string, const char *>> seen;
    unsigned gen = 1;                                         // (bumped at each change: what caches text checks it)
};
inline I18n &i18n()
{
    static I18n I;
    return I;
}

// THE LANGUAGES with a table, by their own names (the Setup card's row)
struct Lang {
    const char *code, *name;
};
inline const Lang *langs(int *n)
{
    static const Lang L[] = {{"en", "English"}, {"ja", "\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e"}, {"de", "Deutsch"},
                             {"fr", "Fran\xc3\xa7" "ais"}, {"es", "Espa\xc3\xb1ol"}};
    *n = (int)(sizeof L / sizeof L[0]);
    return L;
}
inline bool lang_known(const std::string &c)
{
    int n;
    const Lang *L = langs(&n);
    for (int i = 0; i < n; i++)
        if (c == L[i].code)
            return true;
    return false;
}

// (a language's table into the catalogue: English has none; false if the file is missing)
inline bool i18n_load(const std::string &ui_dir, const std::string &code)
{
    I18n &I = i18n();
    I.t.clear();
    I.seen.clear();
    I.gen++;
    I.code = code;
    if (code == "en" || code.empty()) {
        I.code = "en";
        return true;
    }
    sess::J j;
    if (!sess::load(ui_dir + "/lang/" + code + ".json", j) || !j.is(sess::J::OBJ))
        return false;
    for (const auto &kv : j.o)
        if (kv.first.rfind("_", 0) != 0 && kv.second.is(sess::J::STR) && !kv.second.s.empty())
            I.t[kv.first] = kv.second.s;
    return true;
}

inline const char *T(const char *en)
{
    I18n &I = i18n();
    if (I.t.empty() || !en)
        return en;
    auto s = I.seen.find(en);
    if (s != I.seen.end() && strcmp(s->second.first.c_str(), en) == 0)
        return s->second.second == s->second.first.c_str() ? en : s->second.second;
    auto it = I.t.find(en);
    auto &e = I.seen[en];
    e.first = en;
    e.second = it == I.t.end() ? e.first.c_str() : it->second.c_str();
    return it == I.t.end() ? en : e.second;
}
inline std::string T(const std::string &en)
{
    I18n &I = i18n();
    if (I.t.empty())
        return en;
    auto it = I.t.find(en);
    return it == I.t.end() ? en : it->second;
}

// (a text with values: {0} {1} ... replaced in the translation's own order)
inline std::string TF(const char *en, std::initializer_list<std::string> args)
{
    const std::string f = T(en);
    std::string o;
    o.reserve(f.size() + 16);
    for (size_t i = 0; i < f.size(); i++) {
        if (f[i] == '{' && i + 2 < f.size() && f[i + 1] >= '0' && f[i + 1] <= '9' && f[i + 2] == '}') {
            const size_t k = (size_t)(f[i + 1] - '0');
            if (k < args.size())
                o += *(args.begin() + k);
            i += 2;
        } else
            o += f[i];
    }
    return o;
}

}  // namespace nui
