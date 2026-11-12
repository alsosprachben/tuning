// session.h -- live's session.json, read and written natively.
//
// THE SAME FILE PYTHON KEEPS (live.save_session / load_session): nvlive
// reads its setup from it at start and writes back what it owns -- the
// part's program, variation and drawn stops, the globals, the room, the
// routes, the insertion effect -- leaving every other key as it found it
// (the other parts, the synth, scenes, the Messenger), so a session moves
// between live.py and nvlive either way. Written as Python writes it:
// json.dump(indent=2, sort_keys=True), ASCII, a newline at the end, through
// a temporary file and a rename.
//
// A small JSON value: numbers keep the text they were read as, so a value
// nvlive does not change is written back exactly; one it sets is written as
// Python's repr would (an int bare, a float with its point).

#ifndef NV_SESSION_H
#define NV_SESSION_H

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

namespace sess {

struct J {
    enum T { NUL, BOOL, NUM, STR, ARR, OBJ } t = NUL;
    bool b = false;
    std::string num;                    // a number's text
    std::string s;                      // a string (UTF-8)
    std::vector<J> a;
    std::map<std::string, J> o;         // (sorted: sort_keys)

    bool is(T k) const { return t == k; }
    double d(double dflt = 0.0) const { return t == NUM ? strtod(num.c_str(), nullptr) : t == BOOL ? (b ? 1.0 : 0.0) : dflt; }
    long i(long dflt = 0) const { return t == NUM ? (long)llround(strtod(num.c_str(), nullptr)) : t == BOOL ? (long)b : dflt; }
    const J *get(const std::string &k) const
    {
        if (t != OBJ)
            return nullptr;
        auto it = o.find(k);
        return it == o.end() ? nullptr : &it->second;
    }
};

inline J null() { return J(); }
inline J boolean(bool v) { J j; j.t = J::BOOL; j.b = v; return j; }
inline J str(const std::string &v) { J j; j.t = J::STR; j.s = v; return j; }
inline J arr() { J j; j.t = J::ARR; return j; }
inline J obj() { J j; j.t = J::OBJ; return j; }
inline J integer(long v) { J j; j.t = J::NUM; j.num = std::to_string(v); return j; }

// a float as Python's repr: the shortest text that reads back the same, with
// a point (4.0, not 4)
inline J real(double v)
{
    J j;
    j.t = J::NUM;
    char b[40];
    for (int p = 1; p <= 17; p++) {
        snprintf(b, sizeof b, "%.*g", p, v);
        if (strtod(b, nullptr) == v)
            break;
    }
    std::string s = b;
    if (s.find_first_of(".eEn") == std::string::npos)
        s += ".0";
    j.num = s;
    return j;
}

// ---- reading ----
struct Reader {
    const std::string &x;
    size_t i = 0;
    bool ok = true;
    explicit Reader(const std::string &s) : x(s) {}
    void ws()
    {
        while (i < x.size() && (x[i] == ' ' || x[i] == '\n' || x[i] == '\r' || x[i] == '\t'))
            i++;
    }
    bool lit(const char *w)
    {
        size_t n = strlen(w);
        if (x.compare(i, n, w) != 0)
            return false;
        i += n;
        return true;
    }
    static void utf8(std::string &out, unsigned cp)
    {
        if (cp < 0x80) {
            out += (char)cp;
        } else if (cp < 0x800) {
            out += (char)(0xC0 | (cp >> 6));
            out += (char)(0x80 | (cp & 0x3F));
        } else if (cp < 0x10000) {
            out += (char)(0xE0 | (cp >> 12));
            out += (char)(0x80 | ((cp >> 6) & 0x3F));
            out += (char)(0x80 | (cp & 0x3F));
        } else {
            out += (char)(0xF0 | (cp >> 18));
            out += (char)(0x80 | ((cp >> 12) & 0x3F));
            out += (char)(0x80 | ((cp >> 6) & 0x3F));
            out += (char)(0x80 | (cp & 0x3F));
        }
    }
    unsigned hex4()
    {
        if (i + 4 > x.size()) {
            ok = false;
            return 0;
        }
        unsigned v = (unsigned)strtoul(x.substr(i, 4).c_str(), nullptr, 16);
        i += 4;
        return v;
    }
    std::string string()
    {
        std::string out;
        i++;                                    // (the opening quote)
        while (i < x.size() && x[i] != '"') {
            char c = x[i++];
            if (c != '\\') {
                out += c;
                continue;
            }
            if (i >= x.size())
                break;
            char e = x[i++];
            switch (e) {
            case 'n': out += '\n'; break;
            case 't': out += '\t'; break;
            case 'r': out += '\r'; break;
            case 'b': out += '\b'; break;
            case 'f': out += '\f'; break;
            case 'u': {
                unsigned cp = hex4();
                if (cp >= 0xD800 && cp < 0xDC00 && i + 1 < x.size() && x[i] == '\\' && x[i + 1] == 'u') {
                    i += 2;
                    unsigned lo = hex4();
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                }
                utf8(out, cp);
                break;
            }
            default: out += e;
            }
        }
        if (i >= x.size())
            ok = false;
        i++;                                    // (the closing quote)
        return out;
    }
    J value()
    {
        ws();
        J j;
        if (i >= x.size()) {
            ok = false;
            return j;
        }
        char c = x[i];
        if (c == '{') {
            j.t = J::OBJ;
            i++;
            ws();
            if (i < x.size() && x[i] == '}') {
                i++;
                return j;
            }
            while (ok) {
                ws();
                if (i >= x.size() || x[i] != '"') {
                    ok = false;
                    break;
                }
                std::string k = string();
                ws();
                if (i >= x.size() || x[i] != ':') {
                    ok = false;
                    break;
                }
                i++;
                j.o[k] = value();
                ws();
                if (i < x.size() && x[i] == ',') {
                    i++;
                    continue;
                }
                if (i < x.size() && x[i] == '}') {
                    i++;
                    break;
                }
                ok = false;
            }
        } else if (c == '[') {
            j.t = J::ARR;
            i++;
            ws();
            if (i < x.size() && x[i] == ']') {
                i++;
                return j;
            }
            while (ok) {
                j.a.push_back(value());
                ws();
                if (i < x.size() && x[i] == ',') {
                    i++;
                    continue;
                }
                if (i < x.size() && x[i] == ']') {
                    i++;
                    break;
                }
                ok = false;
            }
        } else if (c == '"') {
            j.t = J::STR;
            j.s = string();
        } else if (lit("true")) {
            j.t = J::BOOL;
            j.b = true;
        } else if (lit("false")) {
            j.t = J::BOOL;
        } else if (lit("null")) {
        } else if (c == 'N' || c == 'I' || (c == '-' && i + 1 < x.size() && x[i + 1] == 'I')) {
            ok = false;                         // (NaN, Infinity: never in a session)
        } else {
            size_t s0 = i;
            while (i < x.size() && strchr("+-0123456789.eE", x[i]))
                i++;
            if (i == s0)
                ok = false;
            j.t = J::NUM;
            j.num = x.substr(s0, i - s0);
        }
        return j;
    }
};

inline bool parse(const std::string &text, J &out)
{
    Reader r(text);
    out = r.value();
    r.ws();
    return r.ok && r.i == text.size();
}

// ---- writing, as json.dump(indent=2, sort_keys=True) ----
inline void quote(std::string &out, const std::string &s)
{
    out += '"';
    for (size_t i = 0; i < s.size();) {
        unsigned char c = (unsigned char)s[i];
        unsigned cp = c;
        int n = 1;
        if (c >= 0xF0 && i + 3 < s.size() + 1) {
            cp = ((c & 0x07u) << 18) | (((unsigned char)s[i + 1] & 0x3Fu) << 12) | (((unsigned char)s[i + 2] & 0x3Fu) << 6)
                 | ((unsigned char)s[i + 3] & 0x3Fu);
            n = 4;
        } else if (c >= 0xE0) {
            cp = ((c & 0x0Fu) << 12) | (((unsigned char)s[i + 1] & 0x3Fu) << 6) | ((unsigned char)s[i + 2] & 0x3Fu);
            n = 3;
        } else if (c >= 0xC0) {
            cp = ((c & 0x1Fu) << 6) | ((unsigned char)s[i + 1] & 0x3Fu);
            n = 2;
        }
        i += n;
        char b[16];
        if (cp == '"')
            out += "\\\"";
        else if (cp == '\\')
            out += "\\\\";
        else if (cp == '\n')
            out += "\\n";
        else if (cp == '\r')
            out += "\\r";
        else if (cp == '\t')
            out += "\\t";
        else if (cp == '\b')
            out += "\\b";
        else if (cp == '\f')
            out += "\\f";
        else if (cp < 0x20 || (cp >= 0x7F && cp < 0x10000)) {
            snprintf(b, sizeof b, "\\u%04x", cp);
            out += b;
        } else if (cp >= 0x10000) {             // (a surrogate pair, as ensure_ascii writes it)
            unsigned v = cp - 0x10000;
            snprintf(b, sizeof b, "\\u%04x\\u%04x", 0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF));
            out += b;
        } else {
            out += (char)cp;
        }
    }
    out += '"';
}

inline void dump(std::string &out, const J &j, int depth)
{
    const std::string pad(2 * (depth + 1), ' '), end(2 * depth, ' ');
    switch (j.t) {
    case J::NUL: out += "null"; break;
    case J::BOOL: out += j.b ? "true" : "false"; break;
    case J::NUM: out += j.num; break;
    case J::STR: quote(out, j.s); break;
    case J::ARR:
        if (j.a.empty()) {
            out += "[]";
            break;
        }
        out += "[\n";
        for (size_t k = 0; k < j.a.size(); k++) {
            out += pad;
            dump(out, j.a[k], depth + 1);
            out += k + 1 < j.a.size() ? ",\n" : "\n";
        }
        out += end + "]";
        break;
    case J::OBJ: {
        if (j.o.empty()) {
            out += "{}";
            break;
        }
        out += "{\n";
        size_t k = 0;
        for (const auto &kv : j.o) {
            out += pad;
            quote(out, kv.first);
            out += ": ";
            dump(out, kv.second, depth + 1);
            out += ++k < j.o.size() ? ",\n" : "\n";
        }
        out += end + "}";
        break;
    }
    }
}

inline std::string dump(const J &j)
{
    std::string out;
    dump(out, j, 0);
    return out + "\n";
}

// the file, or false (none, or one that will not parse)
inline bool load(const std::string &path, J &out)
{
    FILE *f = fopen(path.c_str(), "rb");
    if (!f)
        return false;
    std::string text;
    char b[65536];
    size_t n;
    while ((n = fread(b, 1, sizeof b, f)) > 0)
        text.append(b, n);
    fclose(f);
    return parse(text, out) && out.is(J::OBJ);
}

// written as Python's _save_json: a temporary file, then a rename
inline bool save(const std::string &path, const J &j)
{
    const std::string tmp = path + ".tmp", text = dump(j);
    FILE *f = fopen(tmp.c_str(), "wb");
    if (!f)
        return false;
    bool ok = fwrite(text.data(), 1, text.size(), f) == text.size();
    ok = (fclose(f) == 0) && ok;
    return ok && rename(tmp.c_str(), path.c_str()) == 0;
}

}  // namespace sess

#endif
