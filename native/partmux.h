// ORCHESTRA BY TRACK NAMES: mt32mux.py, line for line (examples/
// partmux_check.py reads mt32mux's output file and this pass's tracks and
// compares them). A file of its era names its parts on its tracks and plays
// them on MT-32 patch numbers that mean something else entirely (Saturn's
// harps on Contrabass, its horns on SlapBass1), and carries more parts than
// channels by sharing them. So each part takes the GM program its NAME says,
// and the parts are coloured onto the channels so that no two on one ever
// sound the same pitch at once -- each note stamped with its program and its
// part's CC7/CC11/pan a tick before it, which the onset snapshots (the file
// render's notes; live's stamped channels). mt32mux.py's docstring and
// comments have the files that taught each rule.
//
// Included by midi.cpp (namespace nv, after Msg): mux() takes each track's
// messages as read_track left them (absolute ticks) and returns the tracks of
// the file mt32mux would write -- a meta track, then one track per part.
#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace partmux {

// Orchestral part names as sequencers write them, to GM programs: matched on
// a lowercased substring, longest first (ties in this order: mt32mux's dict)
static const std::pair<const char *, int> NAME_TO_GM[] = {
    {"piccolo", 72}, {"bass flute", 73}, {"alto flute", 73}, {"flute", 73},
    {"english horn", 69}, {"cor anglais", 69}, {"bass oboe", 69}, {"heckelphone", 69},
    {"oboe", 68},
    {"bass clarinet", 71}, {"clarinet", 71}, {"basset", 71},
    {"doublebassoon", 70}, {"double bassoon", 70}, {"contra bassoon", 70},
    {"contrabassoon", 70}, {"contrbassoon", 70}, {"bassoon", 70},
    {"soprano sax", 64}, {"alto sax", 65}, {"tenor sax", 66}, {"bari sax", 67},
    {"horn", 60}, {"cornet", 56}, {"trumpet", 56},
    {"bass trombone", 57}, {"trombone", 57}, {"euphonium", 58}, {"tuba", 58},
    {"timpani", 47}, {"timp", 47},
    {"tubular bell", 14}, {"chime", 14}, {"bell", 14},
    {"glockenspiel", 9}, {"celesta", 8}, {"celeste", 8},
    {"xylophone", 13}, {"marimba", 12}, {"vibraphone", 11},
    {"harp", 46}, {"organ", 19}, {"piano", 0},
    {"violin", 40}, {"viola", 41}, {"violoncello", 42}, {"cello", 42},
    {"double bass", 43}, {"doublebass", 43}, {"contrabass", 43}, {"bass", 43},
    {"chorus", 52}, {"choir", 52}, {"soprano", 52}, {"alto", 52}, {"voice", 53},
};

// Names that mean the GM drum map, which stays on channel 10
static const char *const PERCUSSIVE[] = {
    "percussion", "drum", "kit", "cymbal", "snare", "tom", "hi-hat", "hihat", "rhythm", "battery", "triangle",
    "tambourine", "castanet", "gong", "tam-tam",
};

static const int GM_PERCUSSION_CHANNEL = 9;
static const int STAMP_LEAD = 2;        // ticks between the program change and its note

// The GM programs whose voice reads its stops from the channel (filecheck.h's
// list: patch_map's registerable), so a part on one keeps a channel alone
static bool is_registerable(int p)
{
    return p == 6 || (p >= 16 && p <= 20) || p == 55;
}

static std::string lower(std::string s)
{
    for (char &c : s)
        c = (char)tolower((unsigned char)c);
    return s;
}

// Python's str.strip() over latin-1
static std::string strip(const std::string &s)
{
    static const char WS[] = " \t\n\r\v\f\x1c\x1d\x1e\x1f\x85\xa0";
    const size_t a = s.find_first_not_of(WS, 0, sizeof WS - 1);
    if (a == std::string::npos)
        return "";
    const size_t b = s.find_last_not_of(WS, std::string::npos, sizeof WS - 1);
    return s.substr(a, b - a + 1);
}

typedef std::vector<std::pair<long long, int>> Line;        // (tick, value), a controller's timeline
typedef std::map<int, Line> CCs;

struct NoteT {
    long long on, off;
    int note, vel;
    bool operator<(const NoteT &o) const
    {
        return std::tie(on, off, note, vel) < std::tie(o.on, o.off, o.note, o.vel);
    }
};

struct Part {
    size_t track = 0;
    std::string name;
    std::vector<int> progs;
    std::shared_ptr<CCs> cc;    // (shared by the pieces of a split track, as mt32mux's dict is)
    std::vector<NoteT> notes;
    bool was_drum = false;
    int from_ch = 0;
    bool percussive = false;
    int program = 0;
    std::string why;
};

static int value_at(const Line &tl, long long tick, int dflt)
{
    int v = dflt;
    for (const auto &e : tl) {
        if (e.first > tick)
            break;
        v = e.second;
    }
    return v;
}

static std::pair<int, const char *> program_for(const std::string &name, const std::vector<int> &own)
{
    static std::vector<std::pair<std::string, int>> keys;
    if (keys.empty()) {
        for (const auto &k : NAME_TO_GM)
            keys.push_back({k.first, k.second});
        std::stable_sort(keys.begin(), keys.end(), [](const auto &a, const auto &b) { return a.first.size() > b.first.size(); });
    }
    const std::string low = lower(name);
    for (const auto &k : keys)
        if (low.find(k.first) != std::string::npos)
            return {k.second, "name"};
    if (!own.empty())
        return {own.back(), "declared"};
    return {0, "default"};
}

template <class MsgT>
static std::vector<Part> read_parts(const std::vector<std::vector<const MsgT *>> &tracks)
{
    std::vector<Part> parts;
    for (size_t ti = 0; ti < tracks.size(); ti++) {
        std::string name;
        std::vector<int> progs;
        std::vector<std::pair<long long, int>> pcs;
        auto cc = std::make_shared<CCs>();
        std::map<int, std::vector<std::pair<long long, int>>> held;
        std::vector<NoteT> notes;
        bool drum = false;
        int minch = 99;
        for (const MsgT *m : tracks[ti]) {
            const long long now = m->tick;
            if (m->status == 0xFF) {
                if (m->meta == 0x03)
                    name = strip(std::string(m->data.begin(), m->data.end()));
                continue;
            }
            if (m->status == 0xF0)
                continue;
            const int kind = m->status & 0xF0, ch = m->status & 0x0F;
            if (kind == 0xC0) {
                progs.push_back(m->d0);
                pcs.push_back({now, m->d0});
            } else if (kind == 0xB0) {
                (*cc)[m->d0].push_back({now, m->d1});
            } else if (kind == 0x90 && m->d1) {
                held[m->d0].push_back({now, m->d1});
                minch = std::min(minch, ch);
                drum = drum || ch == GM_PERCUSSION_CHANNEL;
            } else if (kind == 0x80 || kind == 0x90) {
                auto it = held.find(m->d0);
                if (it != held.end() && !it->second.empty()) {
                    const auto ov = it->second.front();
                    it->second.erase(it->second.begin());
                    notes.push_back({ov.first, now, m->d0, ov.second});
                }
            }
        }
        if (notes.empty())
            continue;
        std::sort(notes.begin(), notes.end());
        Part part;
        part.track = ti;
        part.name = name.empty() ? "trk" + std::to_string(ti) : name;
        part.progs = progs;
        part.cc = cc;
        part.notes = notes;
        part.was_drum = drum;
        part.from_ch = minch == 99 ? 0 : minch;
        std::vector<std::pair<long long, int>> cuts;
        for (const auto &x : pcs)
            if (x.first > notes[0].on)
                cuts.push_back(x);
        // (name.split('/'), each stripped)
        std::vector<std::string> pieces;
        {
            size_t a = 0;
            for (;;) {
                const size_t b = name.find('/', a);
                pieces.push_back(strip(name.substr(a, b == std::string::npos ? std::string::npos : b - a)));
                if (b == std::string::npos)
                    break;
                a = b + 1;
            }
        }
        bool all_named = true;
        for (const auto &p : pieces)
            all_named = all_named && !p.empty();
        // SPLIT ONLY WHERE THE NAME SAYS SO: one piece of an "A/B" name per instrument
        if (cuts.empty() || pieces.size() != cuts.size() + 1 || !all_named) {
            parts.push_back(part);
            continue;
        }
        int start = -1;
        for (const auto &x : pcs)
            if (x.first <= notes[0].on)
                start = x.second;
        std::vector<std::pair<long long, int>> segs{{0, start}};
        segs.insert(segs.end(), cuts.begin(), cuts.end());
        for (size_t k = 0; k < segs.size(); k++) {
            const long long t0 = segs[k].first;
            const bool last = k + 1 >= segs.size();
            const long long t1 = last ? 0 : segs[k + 1].first;
            std::vector<NoteT> mine;
            for (const auto &n : notes)
                if (n.on >= t0 && (last || n.on < t1))
                    mine.push_back(n);
            if (mine.empty())
                continue;
            Part q = part;
            q.name = pieces[k];
            q.progs.clear();
            if (segs[k].second >= 0)
                q.progs.push_back(segs[k].second);
            q.notes = mine;
            parts.push_back(q);
        }
    }
    return parts;
}

// channel_cc: the file's combined per-channel controller timelines
template <class MsgT>
static std::map<int, CCs> channel_cc(const std::vector<std::vector<const MsgT *>> &tracks)
{
    std::map<int, CCs> out;
    for (const auto &tr : tracks)
        for (const MsgT *m : tr)
            if (m->status < 0xF0 && (m->status & 0xF0) == 0xB0)
                out[m->status & 0x0F][m->d0].push_back({m->tick, m->d1});
    for (auto &ch : out)
        for (auto &c : ch.second)
            std::sort(c.second.begin(), c.second.end());
    return out;
}

// seed_parts: each part starts from the channel's state at its first note,
// then its own automation -- or, writing no volume of its own, the channel's
static void seed_parts(std::vector<Part> &parts, std::map<int, CCs> &combined)
{
    for (Part &p : parts) {
        const long long first = p.notes[0].on;
        for (const auto &cd : {std::pair<int, int>{7, 100}, std::pair<int, int>{10, 64}}) {
            const int ctrl = cd.first, dflt = cd.second;
            Line chan;
            auto ci = combined.find(p.from_ch);
            if (ci != combined.end()) {
                auto li = ci->second.find(ctrl);
                if (li != ci->second.end())
                    chan = li->second;
            }
            std::sort(chan.begin(), chan.end());
            Line &mine = (*p.cc)[ctrl];
            Line srt = mine;
            std::sort(srt.begin(), srt.end());
            Line own;
            for (const auto &e : srt)
                if (e.first >= first)
                    own.push_back(e);
            if (ctrl == 7 && mine.empty()) {
                Line nl{{0, value_at(chan, first, dflt)}};
                for (const auto &e : chan)
                    if (e.first > first)
                        nl.push_back(e);
                mine = nl;
                continue;
            }
            Line nl{{0, value_at(chan, first, dflt)}};
            nl.insert(nl.end(), own.begin(), own.end());
            mine = nl;
        }
    }
}

static long long collisions(const std::vector<NoteT> &a, const std::vector<NoteT> &b)
{
    // (by pitch: the pairs mt32mux counts, without its all-pairs loop)
    std::map<int, std::vector<const NoteT *>> bp;
    for (const auto &y : b)
        bp[y.note].push_back(&y);
    long long n = 0;
    for (const auto &x : a) {
        auto it = bp.find(x.note);
        if (it == bp.end())
            continue;
        for (const NoteT *y : it->second)
            n += x.on < y->off && x.off > y->on;
    }
    return n;
}

struct Colouring {
    std::vector<int> assign;
    long long before = 0, left = 0;
};

// colour: greedy by conflict degree; registerable voices a channel alone,
// percussion the drum channel
static Colouring colour(const std::vector<Part> &parts, const std::vector<int> &channels)
{
    const size_t n = parts.size();
    std::vector<std::vector<long long>> C(n, std::vector<long long>(n, 0));
    for (size_t i = 0; i < n; i++)
        for (size_t j = i + 1; j < n; j++)
            C[i][j] = C[j][i] = collisions(parts[i].notes, parts[j].notes);
    std::vector<int> assign(n, -1);
    std::vector<int> free(channels);
    for (size_t i = 0; i < n; i++)
        if (is_registerable(parts[i].program) && !free.empty()) {
            assign[i] = free.front();
            free.erase(free.begin());
        }
    for (size_t i = 0; i < n; i++)
        if (assign[i] < 0 && parts[i].was_drum && parts[i].percussive)
            assign[i] = GM_PERCUSSION_CHANNEL;
    std::vector<size_t> order;
    for (size_t i = 0; i < n; i++)
        if (assign[i] < 0)
            order.push_back(i);
    auto degree = [&](size_t i) {
        long long d = 0;
        for (size_t j = 0; j < n; j++)
            d += C[i][j] != 0;
        return d;
    };
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) { return degree(a) > degree(b); });
    for (const size_t i : order) {
        bool placed = false;
        for (const int ch : free) {
            bool ok = true;
            for (size_t j = 0; j < n && ok; j++)
                ok = assign[j] != ch || C[i][j] == 0;
            if (ok) {
                assign[i] = ch;
                placed = true;
                break;
            }
        }
        if (!placed && !free.empty()) {
            int best = free.front();
            long long bc = -1;
            for (const int ch : free) {
                long long c = 0;
                for (size_t j = 0; j < n; j++)
                    if (assign[j] == ch)
                        c += C[i][j];
                if (bc < 0 || c < bc) {
                    bc = c;
                    best = ch;
                }
            }
            assign[i] = best;
        }
    }
    Colouring R;
    R.assign = assign;
    for (size_t i = 0; i < n; i++)
        for (size_t j = i + 1; j < n; j++) {
            R.before += C[i][j];
            if (assign[i] == assign[j])
                R.left += C[i][j];
        }
    return R;
}

// MT-32 velocity -> GM (mt32mux's 'scummvm': round(3/4 v + 32), Python's
// round half to even)
static int scummvm(int v)
{
    const double x = std::nearbyint(0.75 * v + 32);
    return std::max(1, std::min(127, (int)x));
}

struct Result {
    std::vector<std::string> report;    // mt32mux's printout: a line per part
    long long before = 0, left = 0;
    int nparts = 0, nchans = 0;
};

// mux: the tracks of mt32mux's output file (vel: its velocity map, 'scummvm' or none)
template <class MsgT>
static std::vector<std::vector<MsgT>> mux(const std::vector<std::vector<const MsgT *>> &tracks, bool vel, Result &R)
{
    std::vector<Part> parts = read_parts(tracks);
    auto combined = channel_cc(tracks);
    seed_parts(parts, combined);
    for (Part &p : parts) {
        const std::string low = lower(p.name);
        p.percussive = false;
        for (const char *w : PERCUSSIVE)
            p.percussive = p.percussive || low.find(w) != std::string::npos;
        if (p.percussive && p.was_drum) {
            p.program = -1;
            p.why = "drum map";
        } else {
            auto pf = program_for(p.name, p.progs);
            p.program = pf.first;
            p.why = pf.second;
        }
    }
    std::vector<int> channels;
    for (int c = 0; c < 16; c++)
        if (c != GM_PERCUSSION_CHANNEL)
            channels.push_back(c);
    Colouring K = colour(parts, channels);

    std::vector<std::vector<MsgT>> out;
    // the meta track: every meta event but the names, in tick order
    // (fix_end_of_track: one end of track, at the last)
    {
        std::vector<MsgT> meta;
        long long last = 0;
        for (const auto &tr : tracks)
            for (const MsgT *m : tr)
                if (m->status == 0xFF && m->meta != 0x03) {
                    last = std::max(last, m->tick);
                    if (m->meta != 0x2F)
                        meta.push_back(*m);
                }
        std::stable_sort(meta.begin(), meta.end(), [](const MsgT &a, const MsgT &b) { return a.tick < b.tick; });
        MsgT e{last, 0xFF, 0, 0, 0x2F, {}};
        meta.push_back(e);
        out.push_back(meta);
    }
    std::vector<std::pair<long long, MsgT>> evs;
    for (size_t i = 0; i < parts.size(); i++) {
        const Part &p = parts[i];
        const int ch = K.assign[i];
        evs.clear();
        auto msg = [&](long long t, int st, int a, int b) { evs.push_back({t, MsgT{t, st | ch, a, b, 0, {}}}); };
        const CCs &cc = *p.cc;
        static const Line none;
        auto line = [&](int c) -> const Line & { auto it = cc.find(c); return it == cc.end() ? none : it->second; };
        Line c11 = line(11);
        std::sort(c11.begin(), c11.end());
        for (const NoteT &n : p.notes) {
            if (ch != GM_PERCUSSION_CHANNEL)
                msg(std::max(0LL, n.on - STAMP_LEAD), 0xC0, p.program, 0);
            msg(std::max(0LL, n.on - 1), 0xB0, 7, value_at(line(7), n.on, 100));
            if (!c11.empty())
                msg(std::max(0LL, n.on - 1), 0xB0, 11, value_at(c11, n.on, 127));
            if (!line(10).empty())
                msg(std::max(0LL, n.on - 1), 0xB0, 10, value_at(line(10), n.on, 64));
            msg(n.on, 0x90, n.note, vel ? scummvm(n.vel) : n.vel);
            msg(n.off, 0x80, n.note, 0);
        }
        std::stable_sort(evs.begin(), evs.end(), [](const auto &a, const auto &b) { return a.first < b.first; });
        std::vector<MsgT> tr;
        MsgT nm{0, 0xFF, 0, 0, 0x03, std::vector<uint8_t>(p.name.begin(), p.name.end())};
        tr.push_back(nm);
        long long last = 0;
        for (const auto &e : evs) {
            tr.push_back(e.second);
            last = std::max(last, e.first);
        }
        MsgT eot{last, 0xFF, 0, 0, 0x2F, {}};
        tr.push_back(eot);
        out.push_back(tr);

        int lo = 127, hi = 0;
        for (const auto &x : p.notes) {
            lo = std::min(lo, x.note);
            hi = std::max(hi, x.note);
        }
        char b[256];
        const std::string what = p.program < 0 ? "drum map" : std::to_string(p.program) + " (" + p.why + ")";
        snprintf(b, sizeof b, "ch%-3d %-22.22s %-11s %5d notes  %3d-%-3d", ch, p.name.c_str(), what.c_str(),
                 (int)p.notes.size(), lo, hi);
        R.report.push_back(b);
    }
    R.before = K.before;
    R.left = K.left;
    R.nparts = (int)parts.size();
    std::vector<int> used(K.assign);
    std::sort(used.begin(), used.end());
    R.nchans = (int)(std::unique(used.begin(), used.end()) - used.begin());
    return out;
}

}  // namespace partmux
