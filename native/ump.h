// ump.h -- MIDI 2.0 LIVE (ump.py, live.py's on_ump and _bridge, alsaump.py):
// a Clip File or raw UMP stream read into timed packets (ump.read,
// ump.timeline) for --midi2-play; a packet decoded into the engine's events
// (ump.decode); the keyboard's MIDI 1.0 carried as MIDI 2.0 (ump.Midi1to2,
// composed with decode: what the engine receives of it), a pitch table
// putting every key's own pitch on its Note On (ump.pitch_table); and a
// MIDI 2.0 client of the ALSA sequencer (alsaump.UmpClient), libasound
// loaded at run time.
//
// The events are the host's (type, channel, a, b, value): 0 note-on (a the
// key, b the velocity, value its Pitch 7.9 or NAN), 1 note-off, 2 control,
// 3 channel pressure, 4 the wheel (a, -8192..8191), 5 a program change,
// 6 an exclusive (its bytes), 7 a key's pressure, 8 MIDI 2.0's per-note
// messages (a the note, b the kind as the slab's Ev has it -- 0 Pitch 7.25,
// 1 per-note bend, 2 its range, 3 per-note management with reset 16 and
// detach 32, 4 ignored -- the value). Channels are flat: group x 16 +
// channel. A value MIDI 1.0 has no number for (MIDI 2.0's own resolution)
// is taken at the nearest: the engine's controllers are MIDI 1.0's.
#ifndef NV_UMP_H
#define NV_UMP_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace nv {
namespace ump {

static const int WORDS[16] = {1, 1, 1, 2, 2, 4, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4};

// ump.scale_up: min-center-max (M2-104 D.1.3)
inline unsigned long long scale_up(unsigned long long v, int src, int dst)
{
    const int shift = dst - src;
    unsigned long long out = v << shift;
    if (v <= (1ULL << (src - 1)))
        return out;
    const int rb = src - 1;
    unsigned long long rv = v & ((1ULL << rb) - 1);
    rv = shift > rb ? rv << (shift - rb) : rv >> (rb - shift);
    while (rv) {
        out |= rv;
        rv >>= rb;
    }
    return out;
}

// ump.to_m1, taken at the nearest MIDI 1.0 number
inline int to_m1(unsigned long long x, int src, int dst)
{
    const unsigned long long q = x >> (src - dst);
    if (scale_up(q, dst, src) == x)
        return (int)q;
    const double cs = (double)(1ULL << (src - 1)), cd = (double)(1ULL << (dst - 1));
    const double f = x <= (1ULL << (src - 1)) ? x / (double)(1ULL << (src - dst))
                                               : cd + (x - cs) * (cd - 1) / ((double)((1ULL << src) - 1) - cs);
    const int top = (1 << dst) - 1;
    return std::max(0, std::min(top, (int)std::lround(f)));
}

struct Ev {
    int type, ch, a, b;
    double v = NAN;
    std::vector<uint8_t> x;
};

// ump.decode: one packet -> events (sx: a multi-packet SysEx by group;
// ignored: what the engine has no use for, counted)
inline void decode(const uint32_t *pk, std::map<int, std::vector<uint8_t>> &sx, std::vector<Ev> &out,
                   long long *ignored)
{
    const uint32_t w0 = pk[0];
    const int mt = w0 >> 28 & 0xF, g = w0 >> 24 & 0xF, st = w0 >> 20 & 0xF;
    const int ch = g * 16 + (w0 >> 16 & 0xF), b3 = w0 >> 8 & 0x7F, b4 = w0 & 0xFF;
    auto E = [&](int type, int a, int b) { out.push_back(Ev{type, ch, a, b}); };
    if (mt == 0x2) {
        const int kind = w0 >> 16 & 0xF0, d2 = w0 & 0x7F;
        if (kind == 0x90)
            E(d2 ? 0 : 1, b3, d2);
        else if (kind == 0x80)
            E(1, b3, d2);
        else if (kind == 0xA0)
            E(7, b3, d2);
        else if (kind == 0xB0)
            E(2, b3, d2);
        else if (kind == 0xC0)
            E(5, b3, 0);
        else if (kind == 0xD0)
            E(3, b3, 0);
        else if (kind == 0xE0)
            E(4, (b3 | d2 << 7) - 8192, 0);
        return;
    }
    if (mt == 0x3) {
        const int n = w0 >> 16 & 0xF;
        const uint8_t raw[6] = {(uint8_t)(w0 >> 8), (uint8_t)w0, (uint8_t)(pk[1] >> 24), (uint8_t)(pk[1] >> 16),
                                (uint8_t)(pk[1] >> 8), (uint8_t)pk[1]};
        if (st == 0 || st == 1)
            sx[g].clear();
        auto &b = sx[g];
        b.insert(b.end(), raw, raw + std::min(n, 6));
        if (st == 0 || st == 3) {
            Ev e{6, -1, 0, 0};
            e.x = b;
            sx.erase(g);
            out.push_back(e);
        }
        return;
    }
    if (mt != 0x4)
        return;                                 // (a tempo, a clockstamp, a stream message: a file's timing)
    const uint32_t d = pk[1];
    auto P = [&](int note, int kind, double v) {
        Ev e{8, ch, note, kind};
        e.v = v;
        out.push_back(e);
    };
    static const int IGN[] = {0, 6, 32, 38, 88, 96, 97, 98, 99, 100, 101};
    if (st == 0x9) {
        const int vel = to_m1(d >> 16, 16, 7);
        Ev e{0, ch, b3, vel >= 1 ? vel : 1};    // ("a velocity value of zero does not function as a Note Off")
        if (b4 == 3)
            e.v = (d & 0xFFFF) / 512.0;
        out.push_back(e);
    } else if (st == 0x8) {
        E(1, b3, to_m1(d >> 16, 16, 7));
    } else if (st == 0xA) {
        E(7, b3, to_m1(d, 32, 7));
    } else if (st == 0xD) {
        E(3, to_m1(d, 32, 7), 0);
    } else if (st == 0xE) {
        E(4, to_m1(d, 32, 14) - 8192, 0);
    } else if (st == 0xB) {
        for (int c : IGN)
            if (c == b3) {
                if (ignored)
                    ++*ignored;
                return;
            }
        const bool integer = b3 == 5 || b3 == 10 || b3 == 43 || b3 == 44 || b3 == 84 || b3 == 126;
        E(2, b3, integer ? (int)(d >> 25) : to_m1(d, 32, 7));
    } else if (st == 0xC) {
        if (b4 & 1) {
            E(2, 0, d >> 8 & 0x7F);
            E(2, 32, d & 0x7F);
        }
        E(5, d >> 24 & 0x7F, 0);
    } else if (st == 0x2 || st == 0x3) {
        if (st == 0x2 && b3 == 0 && (b4 & 0x7F) == 7) {
            P(0, 2, d / 33554432.0);            // RPN 0/7: the per-note bend range (Pitch 7.25)
            return;
        }
        const int v14 = (int)(d >> 18);
        E(2, st == 0x2 ? 101 : 99, b3);
        E(2, st == 0x2 ? 100 : 98, b4 & 0x7F);
        E(2, 6, v14 >> 7);
        E(2, 38, v14 & 0x7F);
    } else if (st == 0x6) {
        P(b3, 1, ((double)d - 2147483648.0) / 2147483648.0);
    } else if (st == 0x0 && b4 == 3) {
        P(b3, 0, d / 33554432.0);               // Registered Per-Note #3: Pitch 7.25
    } else if (st == 0xF) {
        P(b3, 3 | (b4 & 1 ? 16 : 0) | (b4 & 2 ? 32 : 0), 0.0);
    } else if (ignored) {
        ++*ignored;
    }
}

// ump.read + ump.timeline: a Clip File or raw UMP stream -> (absolute
// seconds, packet), the slots' own seconds summed; false if it is neither
inline bool read_timeline(const std::vector<uint8_t> &f, std::vector<std::pair<double, std::vector<uint32_t>>> &out)
{
    const size_t len = f.size();
    auto be32 = [&](size_t i) {
        return (uint32_t)f[i] << 24 | (uint32_t)f[i + 1] << 16 | (uint32_t)f[i + 2] << 8 | f[i + 3];
    };
    double t = 0.0;
    if (len >= 12 && !memcmp(f.data(), "UMPRAW02", 8)) {
        size_t i = 12;
        while (i + 14 <= len) {
            uint64_t bits = (uint64_t)be32(i) << 32 | be32(i + 4);
            double ds;
            memcpy(&ds, &bits, 8);
            const int n = f[i + 12] << 8 | f[i + 13];
            i += 14;
            t += ds;
            for (int q = 0; q < n && i < len; q++) {
                const int k = f[i++];
                if (i + 4 * (size_t)k > len)
                    return false;
                std::vector<uint32_t> pk;
                for (int w = 0; w < k; w++)
                    pk.push_back(be32(i + 4 * w));
                i += 4 * (size_t)k;
                if (!(pk.size() == 1 && pk[0] == 0))
                    out.push_back({t, pk});
            }
        }
        return true;
    }
    if (len < 8 || memcmp(f.data(), "SMF2CLIP", 8))
        return false;
    int tpq = 960;
    double tempo = 500000.0;
    bool started = false, slot = false;
    size_t w = 8;
    while (w + 4 <= len) {
        const uint32_t w0 = be32(w);
        const int mt = w0 >> 28 & 0xF, k = WORDS[mt];
        if (w + 4 * (size_t)k > len)
            break;
        std::vector<uint32_t> pk;
        for (int q = 0; q < k; q++)
            pk.push_back(be32(w + 4 * q));
        w += 4 * (size_t)k;
        if (mt == 0x0) {
            const int st = w0 >> 20 & 0xF;
            if (st == 0x3)
                tpq = (w0 & 0xFFFF) ? (int)(w0 & 0xFFFF) : tpq;
            else if (st == 0x4 && started) {
                const long long dt = w0 & 0xFFFFF;
                t += dt > 0 ? dt * (tempo * 1e-6 / tpq) : 0.0;
                slot = true;
            }
            continue;
        }
        if (mt == 0xF) {
            const int st = w0 >> 16 & 0x3FF;
            if (st == 0x20)
                started = true;
            else if (st == 0x21)
                break;
            continue;
        }
        if (mt == 0xD && (w0 >> 8 & 0xFF) == 0 && (w0 & 0xFF) == 0)
            tempo = pk[1] / 100.0;
        if (started && slot)
            out.push_back({t, pk});
    }
    return true;
}

// ump.pitch_table: "just:C" (each key its five-limit ratio above the tonic
// below it, the tonic its 12-TET pitch) or "et"; false if neither
struct PitchTable {
    int kind = 0, tonic = 0;                    // 0 none, 1 et, 2 just
    bool parse(const std::string &spec)
    {
        std::string s;
        for (char c : spec)
            if (c != ' ')
                s += (char)toupper((unsigned char)c);
        if (s == "ET") {
            kind = 1;
            return true;
        }
        if (s.compare(0, 5, "JUST:") != 0)
            return false;
        static const std::pair<const char *, int> NAMES[] = {
            {"C", 0}, {"C#", 1}, {"DB", 1}, {"D", 2}, {"D#", 3}, {"EB", 3}, {"E", 4}, {"F", 5}, {"F#", 6},
            {"GB", 6}, {"G", 7}, {"G#", 8}, {"AB", 8}, {"A", 9}, {"A#", 10}, {"BB", 10}, {"B", 11}};
        for (auto &n : NAMES)
            if (s.substr(5) == n.first) {
                kind = 2;
                tonic = n.second;
                return true;
            }
        return false;
    }
    double pitch(int note) const
    {
        static const double JUST_5[12] = {1.0, 16 / 15.0, 9 / 8.0, 6 / 5.0, 5 / 4.0, 4 / 3.0,
                                          45 / 32.0, 3 / 2.0, 8 / 5.0, 5 / 3.0, 9 / 5.0, 15 / 8.0};
        if (kind == 1)
            return (double)note;
        const int k = ((note - tonic) % 12 + 12) % 12;
        return (double)(note - k) + 12.0 * log2(JUST_5[k]);
    }
};

// THE BRIDGE (ump.Midi1to2 then ump.decode, as live._bridge has them): the
// keyboard's MIDI 1.0 events in, what the engine receives of their MIDI 2.0
// out. A data entry (CC6) held until its CC38, a new selection, any other
// message or the timeout (flush: live's M2_HOLD_S); then the RPN or NRPN as
// the four controllers -- RPN 0/7 the per-note bend range; bank select held
// for the program change; CC88/96/97 the MIDI 2.0 Protocol's ignored; with
// a pitch table each Note On its key's Pitch 7.9
struct Bridge {
    bool on = false;
    PitchTable pt;
    std::map<int, std::pair<int, int>> bank;
    struct Sel {
        bool nrpn;
        int msb, lsb;
    };
    std::map<int, Sel> sel;
    std::map<int, std::map<int, int>> sel_part;
    std::map<int, int> d6;
    std::vector<int> pending;                   // (in the order held: a dict's)
    long long ignored = 0;

    void send_param(int ch, int lsb, std::vector<Ev> &out)
    {
        auto pi = std::find(pending.begin(), pending.end(), ch);
        if (pi != pending.end())
            pending.erase(pi);
        auto s = sel.find(ch);
        auto m = d6.find(ch);
        if (s == sel.end() || m == d6.end() || (s->second.msb == 127 && s->second.lsb == 127))
            return;
        const int v14 = (m->second << 7) | lsb;
        if (!s->second.nrpn && s->second.msb == 0 && s->second.lsb == 7) {
            Ev e{8, ch, 0, 2};
            e.v = scale_up((unsigned long long)v14, 14, 32) / 33554432.0;
            out.push_back(e);
            return;
        }
        out.push_back(Ev{2, ch, s->second.nrpn ? 99 : 101, s->second.msb});
        out.push_back(Ev{2, ch, s->second.nrpn ? 98 : 100, s->second.lsb});
        out.push_back(Ev{2, ch, 6, v14 >> 7});
        out.push_back(Ev{2, ch, 38, v14 & 0x7F});
    }
    void flush(int ch, std::vector<Ev> &out)
    {
        if (std::find(pending.begin(), pending.end(), ch) != pending.end())
            send_param(ch, 0, out);
    }
    void flush_all(std::vector<Ev> &out)
    {
        std::vector<int> p(pending);
        for (int c : p)
            flush(c, out);
    }
    // a MIDI 1.0 event (the host's type, channel, a, b) -> the engine's
    void feed(int type, int ch, int a, int b, std::vector<Ev> &out)
    {
        if (type == 2 && a == 38 && std::find(pending.begin(), pending.end(), ch) != pending.end()) {
            send_param(ch, b, out);
            return;
        }
        if (type == 2 && (a == 6 || a == 38 || (a >= 98 && a <= 101))) {
            if (a == 6) {
                flush(ch, out);
                d6[ch] = b;
                pending.push_back(ch);
                return;
            }
            if (a == 38) {                      // (no CC6 held: the latest CC6 is still the MSB)
                if (d6.count(ch))
                    send_param(ch, b, out);
                return;
            }
            flush(ch, out);
            auto &part = sel_part[ch];
            part[a] = b;
            if (a == 101 || a == 100) {
                part.erase(99);
                part.erase(98);
                sel[ch] = Sel{false, part.count(101) ? part[101] : 0, part.count(100) ? part[100] : 0};
            } else {
                part.erase(101);
                part.erase(100);
                sel[ch] = Sel{true, part.count(99) ? part[99] : 0, part.count(98) ? part[98] : 0};
            }
            d6.erase(ch);                       // (a new selection: a data entry must follow it)
            return;
        }
        flush_all(out);                         // (anything else sends a held data entry first)
        if (type == 0) {
            Ev e{0, ch, a, b};
            if (pt.kind) {
                const double p = pt.pitch(a);
                const long long q = std::max(0LL, std::min((128LL << 9) - 1, (long long)std::llround(p * 512.0)));
                e.v = q / 512.0;
            }
            out.push_back(e);
        } else if (type == 2 && (a == 0 || a == 32)) {
            auto &bk = bank[ch];
            (a == 0 ? bk.first : bk.second) = b;
        } else if (type == 2 && (a == 88 || a == 96 || a == 97)) {
            ignored++;
        } else if (type == 5) {
            auto bi = bank.find(ch);
            if (bi != bank.end()) {
                out.push_back(Ev{2, ch, 0, bi->second.first});
                out.push_back(Ev{2, ch, 32, bi->second.second});
            }
            out.push_back(Ev{5, ch, a, b});
        } else {
            out.push_back(Ev{type, ch, a, b});
        }
    }
};

// alsaump.UmpClient: a MIDI 2.0 client of the ALSA sequencer, one port
// ("MIDI 2.0 in") that the kernel converts any MIDI 1.0 sender's events
// into UMP for. libasound loaded at run time; the event struct as alsa-lib
// 1.2.11's snd_seq_ump_event_t (32 bytes, UMP flag bit 5)
struct AlsaUmp {
    struct UmpEvent {
        uint8_t type, flags, tag, queue;
        uint32_t time[2];
        uint8_t src_client, src_port, dst_client, dst_port;
        uint32_t ump[4];
    };
    struct Addr {
        uint8_t client, port;
    };
    struct PollFd {
        int fd;
        short events, revents;
    };
    void *h = nullptr, *seq = nullptr;
    int client = -1, port = -1;
    int (*open_)(void **, const char *, int, int) = nullptr;
    int (*close_)(void *) = nullptr;
    int (*client_id)(void *) = nullptr;
    int (*set_name)(void *, const char *) = nullptr;
    int (*set_version)(void *, int) = nullptr;
    int (*create_port)(void *, const char *, unsigned, unsigned) = nullptr;
    int (*connect_from_)(void *, int, int, int) = nullptr;
    int (*parse_address)(void *, Addr *, const char *) = nullptr;
    int (*ump_input)(void *, UmpEvent **) = nullptr;
    int (*poll_count)(void *, short) = nullptr;
    int (*poll_fds)(void *, PollFd *, unsigned, short) = nullptr;
    std::string err;

    bool open(const char *name)
    {
        h = dlopen("libasound.so.2", RTLD_NOW);
        if (!h) {
            err = "cannot load libasound.so.2";
            return false;
        }
        open_ = (int (*)(void **, const char *, int, int))dlsym(h, "snd_seq_open");
        close_ = (int (*)(void *))dlsym(h, "snd_seq_close");
        client_id = (int (*)(void *))dlsym(h, "snd_seq_client_id");
        set_name = (int (*)(void *, const char *))dlsym(h, "snd_seq_set_client_name");
        set_version = (int (*)(void *, int))dlsym(h, "snd_seq_set_client_midi_version");
        create_port = (int (*)(void *, const char *, unsigned, unsigned))dlsym(h, "snd_seq_create_simple_port");
        connect_from_ = (int (*)(void *, int, int, int))dlsym(h, "snd_seq_connect_from");
        parse_address = (int (*)(void *, Addr *, const char *))dlsym(h, "snd_seq_parse_address");
        ump_input = (int (*)(void *, UmpEvent **))dlsym(h, "snd_seq_ump_event_input");
        poll_count = (int (*)(void *, short))dlsym(h, "snd_seq_poll_descriptors_count");
        poll_fds = (int (*)(void *, PollFd *, unsigned, short))dlsym(h, "snd_seq_poll_descriptors");
        if (!(open_ && close_ && client_id && set_name && set_version && create_port && connect_from_
              && parse_address && ump_input && poll_count && poll_fds)) {
            err = "alsa-lib is older than 1.2.10: no UMP sequencer API";
            return false;
        }
        if (open_(&seq, "default", 3 /* DUPLEX */, 1 /* NONBLOCK */) < 0) {
            err = "snd_seq_open failed";
            return false;
        }
        set_name(seq, name);
        if (set_version(seq, 2 /* UMP MIDI 2.0 */) < 0) {
            err = "this kernel's sequencer has no MIDI 2.0 clients";
            return false;
        }
        client = client_id(seq);
        port = create_port(seq, "MIDI 2.0 in", 1 | 2 | (1 << 5) | (1 << 6), (1 << 1) | (1 << 20));
        if (port < 0) {
            err = "snd_seq_create_simple_port failed";
            return false;
        }
        return true;
    }
    bool connect_from(const std::string &spec)
    {
        Addr a{0, 0};
        if (parse_address(seq, &a, spec.c_str()) < 0) {
            err = "no sequencer port " + spec;
            return false;
        }
        if (connect_from_(seq, port, a.client, a.port) < 0) {
            err = "cannot connect from " + spec;
            return false;
        }
        return true;
    }
    std::vector<int> fds()
    {
        std::vector<int> out;
        const int n = poll_count(seq, 1 /* POLLIN */);
        std::vector<PollFd> p((size_t)std::max(n, 0));
        if (n > 0)
            poll_fds(seq, p.data(), (unsigned)n, 1);
        for (auto &x : p)
            out.push_back(x.fd);
        return out;
    }
    // every UMP waiting now, without blocking
    void read_pending(std::vector<std::vector<uint32_t>> &out)
    {
        UmpEvent *ev = nullptr;
        while (ump_input(seq, &ev) >= 0 && ev) {
            if (ev->flags & (1 << 5)) {
                const int n = WORDS[ev->ump[0] >> 28 & 0xF];
                out.push_back(std::vector<uint32_t>(ev->ump, ev->ump + n));
            }
            ev = nullptr;
        }
    }
};

}  // namespace ump
}  // namespace nv

#endif
