// midi.cpp -- the native engine's FILE READER: a Standard MIDI File in, a
// Song's events out, as blockrender.parse makes them for a General MIDI file.
//
// Two layers, both exact:
//
//   the file      mido's: each track's events (running status; meta events
//                 do not set it, sysex does), the tracks merged by a stable
//                 sort on absolute tick, end-of-track deltas carried to the
//                 next event, each delta in seconds at the tempo in force
//                 (tick * (tempo * 1e-6 / ticks_per_beat)) and the times a
//                 running float sum, in that order -- so every onset is the
//                 Python's to the bit
//   the channels  blockrender.parse for a GM file: notes paired first in
//                 first out per key, each with its velocity, the channel's
//                 CC7, CC11 and pan at its onset and its program; every
//                 controller in message order; the pitch wheel; CC121's
//                 resets; GM System On and GS Reset
//
// A file this does not read as parse would -- ports, any other system
// exclusive (GS parts, drum setup, tuning, the controller matrix), banks,
// MPE, a type 2 file -- is refused (nv_midi_read returns < 0) and Python
// reads it.

#include <algorithm>
#include <array>
#include <cstdint>
#include <cmath>
#include <cstring>
#include <map>
#include <utility>
#include <vector>

#include "nv.h"

namespace nv {

struct Msg {
    long long tick;             // absolute, then relative
    int status, d0, d1;         // a channel message's bytes; status 0xFF meta, 0xF0 sysex
    int meta;                   // a meta event's type
    std::vector<uint8_t> data;  // a meta event's or a sysex's bytes
};

struct Reader {
    const uint8_t *p, *end;
    bool ok = true;

    int byte()
    {
        if (p >= end) {
            ok = false;
            return 0;
        }
        return *p++;
    }

    long long vlq()
    {
        long long v = 0;
        for (;;) {
            int b = byte();
            if (!ok)
                return 0;
            v = (v << 7) | (b & 0x7F);
            if (b < 0x80)
                return v;
        }
    }
};

static int data_len(int status)
{
    switch (status & 0xF0) {
    case 0x80: case 0x90: case 0xA0: case 0xB0: case 0xE0:
        return 2;
    case 0xC0: case 0xD0:
        return 1;
    }
    return -1;
}

// mido's read_track: one track's events, ticks absolute (_to_abstime)
static bool read_track(Reader &r, std::vector<Msg> &out)
{
    if (r.end - r.p < 8 || memcmp(r.p, "MTrk", 4))
        return false;
    long long size = ((long long)r.p[4] << 24) | (r.p[5] << 16) | (r.p[6] << 8) | r.p[7];
    r.p += 8;
    const uint8_t *start = r.p;
    if (r.end - start < size)
        return false;
    Reader t{start, start + size};
    int last = -1;
    long long now = 0;
    while (t.p < t.end) {
        long long delta = t.vlq();
        int sb = t.byte();
        if (!t.ok)
            return false;
        int peek = -1;
        if (sb < 0x80) {
            if (last < 0)
                return false;
            peek = sb;
            sb = last;
        } else if (sb != 0xFF) {
            last = sb;
        }
        now += delta;
        Msg m{now, sb, 0, 0, 0, {}};
        if (sb == 0xFF) {
            m.meta = t.byte();
            long long n = t.vlq();
            if (!t.ok || t.end - t.p < n)
                return false;
            m.data.assign(t.p, t.p + n);
            t.p += n;
        } else if (sb == 0xF0 || sb == 0xF7) {
            long long n = t.vlq();
            if (!t.ok || t.end - t.p < n)
                return false;
            m.data.assign(t.p, t.p + n);
            t.p += n;
            if (!m.data.empty() && m.data[0] == 0xF0)
                m.data.erase(m.data.begin());
            if (!m.data.empty() && m.data.back() == 0xF7)
                m.data.pop_back();
            m.status = 0xF0;
        } else {
            int n = data_len(sb);
            if (n < 0)
                return false;           // system common or realtime in a file: not ours
            int b[2] = {0, 0};
            for (int i = 0; i < n; i++) {
                b[i] = (i == 0 && peek >= 0) ? peek : t.byte();
                if (b[i] > 127)
                    return false;
            }
            if (!t.ok)
                return false;
            m.d0 = b[0];
            m.d1 = b[1];
        }
        out.push_back(m);
    }
    r.p = start + size;
    return t.p == t.end;
}

struct Note {
    int ch, note;
    double on, off;
    int vel;
    double v7, v11, pan;
    int prog, drum;
};

struct CCEv {
    int ch;
    double t;
    int cc, v;
};

struct PwEv {
    int ch;
    double t;
    int pitch;
};

// an event as it came, for a live replay: 0 note-on, 1 note-off, 2 control,
// 4 the pitch wheel (a: -8192..8191)
struct LiveEv {
    double t;
    int type, ch, a, b;
};

// THE PITCH STREAM (blockrender.parse's _pwseq, rpns and gmon): what moves a
// channel's pitch ratio, each with its time and its message's place in the
// file (ties at one tick go by it): kind 0 the wheel, 1 the bend range, 2
// fine tuning (cents), 3 coarse (semitones), 5 the mod range, 6 and 7 MTS's
// program and bank, 9 GM System On or GS Reset (channel -1: every channel)
struct PitchEv {
    int ch;
    double t;
    long seq;
    int kind;
    double v;
};

struct Parsed {
    std::vector<LiveEv> events;     // the notes and controllers in message order
    std::vector<PitchEv> pitch;
    std::vector<Note> notes;
    std::vector<CCEv> ccs;      // in message order
    std::vector<PwEv> pws;
    std::vector<std::pair<int, int>> progs;     // (channel, program) changes, for the caller
    double total = 0.0;
    int gs = 0;                 // a Roland GS exclusive before the first note (gs_setup: the file speaks GS)
    std::vector<std::array<int, 3>> legato;    // _legato_ticks: (channel, key, k) slurred
    std::vector<CCEv> snd;      // sndev: CC71-78, and gmon (channel -1, cc -1), in message order
};

// _legato_ticks: the notes that begin contiguously with what their channel
// was playing before, judged in the file's ticks -- each track's notes paired
// first in first out, the spans sorted, a channel's notes sharing an onset
// one event, slurred where it starts within a 64th of a beat (a tick at
// least) of the end of the event before it; (channel, key, k), k the key's
// occurrence in onset order
static void legato_ticks(const std::vector<Msg> &all, const std::vector<size_t> &starts, int tpb,
                         std::vector<std::array<int, 3>> &out)
{
    double tol = std::max(1.0, tpb / 64.0);
    struct Span {
        long long on, off;
        int ch, note;
    };
    std::vector<Span> spans;
    for (size_t ti = 0; ti < starts.size(); ti++) {
        size_t a = starts[ti], b = ti + 1 < starts.size() ? starts[ti + 1] : all.size();
        std::map<std::pair<int, int>, std::vector<long long>> held;
        for (size_t i = a; i < b; i++) {
            const Msg &m = all[i];
            int kind = m.status & 0xF0, ch = m.status & 0x0F;
            if (m.status == 0xFF || m.status == 0xF0 || m.status == 0xF7)
                continue;
            if (kind == 0x90 && m.d1 > 0) {
                held[std::make_pair(ch, m.d0)].push_back(m.tick);
            } else if (kind == 0x80 || kind == 0x90) {
                auto it = held.find(std::make_pair(ch, m.d0));
                if (it != held.end() && !it->second.empty()) {
                    spans.push_back(Span{it->second.front(), m.tick, ch, m.d0});
                    it->second.erase(it->second.begin());
                }
            }
        }
    }
    std::sort(spans.begin(), spans.end(), [](const Span &x, const Span &y) {
        if (x.on != y.on) return x.on < y.on;
        if (x.off != y.off) return x.off < y.off;
        if (x.ch != y.ch) return x.ch < y.ch;
        return x.note < y.note;
    });
    std::map<std::pair<int, int>, int> seen;
    std::vector<int> order;                     // the channels as they first appear
    std::map<int, std::vector<Span>> per;
    for (const Span &s : spans) {
        if (!per.count(s.ch))
            order.push_back(s.ch);
        per[s.ch].push_back(s);
    }
    for (int ch : order) {
        const std::vector<Span> &v = per[ch];
        bool has_prev = false;
        long long prev = 0;
        size_t i = 0;
        while (i < v.size()) {
            size_t j = i;
            while (j < v.size() && v[j].on == v[i].on)
                j++;
            bool slur = has_prev && (double)(v[i].on - prev) <= tol;
            long long mx = v[i].off;
            for (size_t q = i; q < j; q++) {
                int &k = seen[std::make_pair(v[q].ch, v[q].note)];
                if (slur)
                    out.push_back({v[q].ch, v[q].note, k});
                k++;
                mx = std::max(mx, v[q].off);
            }
            prev = mx;
            has_prev = true;
            i = j;
        }
    }
}

static const int GM_DEFAULT_VOLUME = 100, GM_DEFAULT_EXPRESSION = 127, GM_DEFAULT_PAN = 64;
static const int PERCUSSION_CHANNEL = 9, CC84_CANCEL = 128;
static const double BEND_RANGE_SEMITONES = 2.0;     // tonelib's: GM's

// blockrender.parse for a GM file: < 0 where it would take a path this does not have
static int parse(const uint8_t *buf, long long len, Parsed &P)
{
    Reader r{buf, buf + len};
    if (len < 14 || memcmp(buf, "MThd", 4))
        return -1;
    long long hsize = ((long long)buf[4] << 24) | (buf[5] << 16) | (buf[6] << 8) | buf[7];
    int type = (buf[8] << 8) | buf[9], ntr = (buf[10] << 8) | buf[11], tpb = (buf[12] << 8) | buf[13];
    if (type == 2 || hsize < 6 || (tpb & 0x8000))
        return -2;
    r.p = buf + 8 + hsize;
    if (r.p > r.end)
        return -1;
    std::vector<Msg> all;
    std::vector<size_t> starts;
    for (int i = 0; i < ntr; i++) {
        starts.push_back(all.size());
        if (!read_track(r, all))
            return -1;
    }
    legato_ticks(all, starts, tpb, P.legato);
    // merge_tracks: a stable sort on absolute tick (tracks in file order),
    // then relative ticks; fix_end_of_track: end-of-track deltas carried on
    std::stable_sort(all.begin(), all.end(), [](const Msg &a, const Msg &b) { return a.tick < b.tick; });
    std::vector<Msg> msgs;
    long long prev = 0, accum = 0;
    for (Msg &m : all) {
        long long d = m.tick - prev;
        prev = m.tick;
        if (m.status == 0xFF && m.meta == 0x2F) {
            accum += d;
            continue;
        }
        m.tick = accum + d;
        accum = 0;
        msgs.push_back(m);
    }
    Msg eot{accum, 0xFF, 0, 0, 0x2F, {}};
    msgs.push_back(eot);

    long long tempo = 500000;
    double t = 0.0;
    std::map<int, std::map<int, int>> ctrl;     // channel -> control -> value
    std::map<int, int> prog, bmsb, blsb, drums;
    bool rxbank = true;
    std::map<std::pair<int, int>, std::vector<Note>> on;
    std::map<int, std::pair<int, int>> rsel;    // a channel's selected RPN, (MSB, LSB); absent: none
    // each channel's RPNs as data entry left them (parse's _rrange, _rfmsb,
    // _rfine, _rcoarse, _rmod, _rtp, _rtb; absent: power-on)
    std::map<int, double> rrange, rfine, rcoarse, rmod;
    std::map<int, int> rfmsb, rtp, rtb;
    auto getd = [](const std::map<int, double> &m, int c, double d) {
        auto it = m.find(c);
        return it != m.end() ? it->second : d;
    };
    long seq = 0;
    bool seen_note = false;
    for (const Msg &m : msgs) {
        seq++;
        double delta = m.tick > 0 ? m.tick * (tempo * 1e-6 / tpb) : 0.0;
        t += delta;
        if (m.status == 0xFF) {
            if (m.meta == 0x51 && m.data.size() == 3)
                tempo = (m.data[0] << 16) | (m.data[1] << 8) | m.data[2];
            else if (m.meta == 0x21 && !m.data.empty() && m.data[0])
                return -3;              // a second port: PortedMidi's
            continue;
        }
        if (m.status == 0xF0) {
            const std::vector<uint8_t> &d = m.data;
            int lvl = (d.size() >= 4 && d[0] == 0x7E && d[2] == 0x09) ? (d[3] == 0x01 ? 1 : d[3] == 0x03 ? 2 : 0) : 0;
            bool gs = d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12
                      && ((d[4] == 0x40 && d[5] == 0x00 && d[6] == 0x7F && d[7] == 0x00)
                          || (d[4] == 0x00 && d[5] == 0x00 && d[6] == 0x7F));
            if (!(lvl || gs))
                return -4;              // any other exclusive: not a GM file's
            if (!seen_note && d.size() >= 4 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12)
                P.gs = 1;
            rxbank = lvl != 1;
            bmsb.clear(); blsb.clear(); drums.clear(); prog.clear(); ctrl.clear(); rsel.clear();
            // BACK TO POWER-ON: every tuning the file set, from here (gmon)
            P.pitch.push_back(PitchEv{-1, t, seq, 9, 0.0});
            P.snd.push_back(CCEv{-1, t, -1, 0});
            rfmsb.clear(); rrange.clear(); rmod.clear(); rfine.clear(); rcoarse.clear(); rtp.clear(); rtb.clear();
            continue;
        }
        int ch = m.status & 0x0F, kind = m.status & 0xF0;
        auto is_drums = [&](int c) {
            auto it = drums.find(c);
            return it != drums.end() ? it->second != 0 : (c % 16 == PERCUSSION_CHANNEL);
        };
        if (kind == 0xC0) {
            int msb = bmsb.count(ch) ? bmsb[ch] : 0, lsb = blsb.count(ch) ? blsb[ch] : 0;
            if ((rxbank && (msb || lsb)) || (is_drums(ch) && lsb))
                return -5;              // a bank or a map: patch_map's
            drums[ch] = is_drums(ch);
            prog[ch] = m.d0;
            P.progs.push_back(std::make_pair(ch, m.d0));
        } else if (kind == 0xB0) {
            int cc = m.d0, v = m.d1;
            P.ccs.push_back(CCEv{ch, t, cc, v});
            P.events.push_back(LiveEv{t, 2, ch, cc, v});
            if (cc >= 71 && cc <= 78)
                P.snd.push_back(CCEv{ch, t, cc, v});
            if (cc == 0)
                bmsb[ch] = v;
            else if (cc == 32)
                blsb[ch] = v;
            ctrl[ch][cc] = v;
            if (cc == 121) {
                for (int rc : {64, 65, 66, 67})
                    P.ccs.push_back(CCEv{ch, t, rc, 0});
                bool mod = false;
                for (const CCEv &e : P.ccs)
                    if (e.ch == ch && e.cc == 1)
                        mod = true;
                if (mod)
                    P.ccs.push_back(CCEv{ch, t, 1, 0});
                P.ccs.push_back(CCEv{ch, t, 84, CC84_CANCEL});
                ctrl[ch][11] = 127;
                ctrl[ch][1] = 0;
                P.pws.push_back(PwEv{ch, t, 0});
                P.pitch.push_back(PitchEv{ch, t, seq, 0, 0.0});
                rsel[ch] = std::make_pair(127, 127);
            }
            if (cc == 98 || cc == 99) {
                rsel.erase(ch);
            } else if (cc == 101 || cc == 100) {
                auto it = rsel.find(ch);
                std::pair<int, int> cur = it != rsel.end() ? it->second : std::make_pair(127, 127);
                rsel[ch] = cc == 101 ? std::make_pair(v, cur.second) : std::make_pair(cur.first, v);
            } else if (cc == 6 || cc == 38) {
                auto it = rsel.find(ch);
                if (it == rsel.end() || it->second == std::make_pair(0, 6))
                    return -6;          // an NRPN's data (GS's), or MPE's configuration
                // DATA ENTRY into the RPN selected (tonelib's rpn_*)
                std::pair<int, int> sel = it->second;
                if (sel == std::make_pair(0, 0)) {
                    double cur = getd(rrange, ch, BEND_RANGE_SEMITONES);
                    rrange[ch] = cc == 6 ? (double)v : (double)(long)cur + v / 100.0;
                    P.pitch.push_back(PitchEv{ch, t, seq, 1, rrange[ch]});
                } else if (sel == std::make_pair(0, 1)) {
                    int msb = rfmsb.count(ch) ? rfmsb[ch] : 64;
                    if (cc == 6)
                        msb = v;
                    int lsb = cc == 38 ? v : 0;
                    rfmsb[ch] = msb;
                    rfine[ch] = (double)(((msb << 7) | lsb) - 8192) / 8192.0 * 100.0;
                    P.pitch.push_back(PitchEv{ch, t, seq, 2, rfine[ch]});
                } else if (sel == std::make_pair(0, 2)) {
                    if (cc == 6) {
                        rcoarse[ch] = (double)(v - 64);
                        P.pitch.push_back(PitchEv{ch, t, seq, 3, rcoarse[ch]});
                    }
                } else if (sel == std::make_pair(0, 5)) {
                    double cur = getd(rmod, ch, 0.0);
                    rmod[ch] = cc == 6 ? (double)v * 100.0
                                       : (double)(long)floor(cur / 100.0) * 100.0 + v * (100.0 / 128.0);
                    P.pitch.push_back(PitchEv{ch, t, seq, 5, rmod[ch]});
                } else if ((sel == std::make_pair(0, 3) || sel == std::make_pair(0, 4)) && cc == 6) {
                    (sel.second == 3 ? rtp : rtb)[ch] = v;
                    P.pitch.push_back(PitchEv{ch, t, seq, sel.second == 3 ? 6 : 7, (double)v});
                }
            } else if (cc == 96 || cc == 97) {
                // DATA INCREMENT / DECREMENT (tonelib.rpn_step): one unit of the
                // selected RPN's finest byte, posted as data entry would post it
                auto it = rsel.find(ch);
                if (it != rsel.end() && it->second.first == 0 && it->second.second <= 5) {
                    int l = it->second.second;
                    static const double ST[6][3] = {{0.01, 0.0, 127.99},
                                                    {100.0 / 8192.0, -100.0, 100.0 * 8191.0 / 8192.0},
                                                    {1.0, -64.0, 63.0},
                                                    {1.0, 0.0, 127.0},
                                                    {1.0, 0.0, 127.0},
                                                    {100.0 / 128.0, 0.0, 127.0 * 100.0 + 127.0 * 100.0 / 128.0}};
                    double cur = l == 0 ? getd(rrange, ch, BEND_RANGE_SEMITONES) : l == 1 ? getd(rfine, ch, 0.0)
                                 : l == 2 ? getd(rcoarse, ch, 0.0)
                                 : l == 3 ? (double)(rtp.count(ch) ? rtp[ch] : 0)
                                 : l == 4 ? (double)(rtb.count(ch) ? rtb[ch] : 0) : getd(rmod, ch, 0.0);
                    double nv = cur + (cc == 96 ? ST[l][0] : -ST[l][0]);
                    nv = std::max(ST[l][1], nv);
                    nv = std::min(ST[l][2], nv);
                    if (l == 2 || l == 3 || l == 4)
                        nv = (double)(long)nearbyint(nv);
                    static const int KIND[6] = {1, 2, 3, 6, 7, 5};
                    if (l == 0)
                        rrange[ch] = nv;
                    else if (l == 1) {
                        rfine[ch] = nv;
                        long code = (long)nearbyint(nv / 100.0 * 8192.0) + 8192;
                        rfmsb[ch] = (int)(std::max(0L, std::min(16383L, code)) >> 7);
                    } else if (l == 2)
                        rcoarse[ch] = nv;
                    else if (l == 3)
                        rtp[ch] = (int)nv;
                    else if (l == 4)
                        rtb[ch] = (int)nv;
                    else
                        rmod[ch] = nv;
                    P.pitch.push_back(PitchEv{ch, t, seq, KIND[l], nv});
                }
            }
        } else if (kind == 0xE0) {
            P.pws.push_back(PwEv{ch, t, ((m.d1 << 7) | m.d0) - 8192});
            P.pitch.push_back(PitchEv{ch, t, seq, 0, (double)(((m.d1 << 7) | m.d0) - 8192)});
            P.events.push_back(LiveEv{t, 4, ch, ((m.d1 << 7) | m.d0) - 8192, 0});
        } else if (kind == 0x90 && m.d1 > 0) {
            seen_note = true;
            P.events.push_back(LiveEv{t, 0, ch, m.d0, m.d1});
            auto &c = ctrl[ch];
            Note n;
            n.ch = ch; n.note = m.d0; n.on = t; n.off = 0.0; n.vel = m.d1;
            n.v7 = (c.count(7) ? c[7] : GM_DEFAULT_VOLUME) / 127.0;
            n.v11 = (c.count(11) ? c[11] : GM_DEFAULT_EXPRESSION) / 127.0;
            n.pan = ((c.count(10) ? c[10] : GM_DEFAULT_PAN) - 64) / 63.0;
            n.prog = prog.count(ch) ? prog[ch] : 0;
            n.drum = is_drums(ch);
            on[std::make_pair(ch, m.d0)].push_back(n);
        } else if (kind == 0x80 || kind == 0x90) {
            P.events.push_back(LiveEv{t, 1, ch, m.d0, 0});
            auto &q = on[std::make_pair(ch, m.d0)];
            if (!q.empty()) {
                Note n = q.front();
                q.erase(q.begin());
                n.off = t;
                P.notes.push_back(n);
            }
        }
        // polytouch (A0) and aftertouch (D0) carry no note or controller here
    }
    P.total = t;
    // MONO MODE (CC126) rewrites a channel's notes as one voice
    // (_prep_mono_mode): not here
    for (const CCEv &e : P.ccs)
        if (e.cc == 126)
            return -7;
    // ALL NOTES OFF and the channel-mode messages that carry it (CC123-127,
    // _prep_notes_off): each key held on the channel lifted at the first one
    // after its onset, if that comes before its own key-up
    std::map<int, std::vector<double>> aoff;
    for (const CCEv &e : P.ccs)
        if (e.cc >= 123 && e.cc <= 127)
            aoff[e.ch].push_back(e.t);
    for (auto &a : aoff) {
        std::sort(a.second.begin(), a.second.end());
        for (Note &n : P.notes)
            if (n.ch == a.first) {
                auto it = std::upper_bound(a.second.begin(), a.second.end(), n.on);
                if (it != a.second.end() && *it < n.off)
                    n.off = *it;
            }
    }
    return 0;
}

}  // namespace nv

extern "C" {

// A file's bytes -> a parse (nv_midi_* below read it), or NULL with *err the
// reason (-1 a malformed file, -2 type 2, -3 ports, -4 an exclusive, -5 a
// bank, -6 an NRPN or MPE, -7 mono mode). The notes are parse's after
// _prep_notes_off.
void *nv_midi_read(const uint8_t *buf, long long len, int *err)
{
    nv::Parsed *P = new nv::Parsed();
    *err = nv::parse(buf, len, *P);
    if (*err < 0) {
        delete P;
        return nullptr;
    }
    return P;
}

void nv_midi_free(void *p) { delete (nv::Parsed *)p; }

double nv_midi_total(void *p) { return ((nv::Parsed *)p)->total; }
int nv_midi_gs(void *p) { return ((nv::Parsed *)p)->gs; }
int nv_midi_n_notes(void *p) { return (int)((nv::Parsed *)p)->notes.size(); }
int nv_midi_n_ccs(void *p) { return (int)((nv::Parsed *)p)->ccs.size(); }
int nv_midi_n_pws(void *p) { return (int)((nv::Parsed *)p)->pws.size(); }
int nv_midi_n_events(void *p) { return (int)((nv::Parsed *)p)->events.size(); }

// the pitch stream (PitchEv): how many; event i -- iv (channel, kind), its
// message's place, its time and its value
int nv_midi_n_pitch(void *p) { return (int)((nv::Parsed *)p)->pitch.size(); }

void nv_midi_pitch(void *p, int i, int *iv, long *seq, double *t, double *v)
{
    const nv::PitchEv &e = ((nv::Parsed *)p)->pitch[i];
    iv[0] = e.ch; iv[1] = e.kind;
    *seq = e.seq;
    *t = e.t;
    *v = e.v;
}

// event i in message order: (type, channel, a, b), *t its time (s)
void nv_midi_event(void *p, int i, int *iv, double *t)
{
    const nv::LiveEv &e = ((nv::Parsed *)p)->events[i];
    iv[0] = e.type; iv[1] = e.ch; iv[2] = e.a; iv[3] = e.b;
    *t = e.t;
}

// note i: (channel, key, velocity, program, drum) ints; (on, off, v7, v11, pan) doubles
void nv_midi_note(void *p, int i, int *iv, double *dv)
{
    const nv::Note &n = ((nv::Parsed *)p)->notes[i];
    iv[0] = n.ch; iv[1] = n.note; iv[2] = n.vel; iv[3] = n.prog; iv[4] = n.drum;
    dv[0] = n.on; dv[1] = n.off; dv[2] = n.v7; dv[3] = n.v11; dv[4] = n.pan;
}

void nv_midi_cc(void *p, int i, int *iv, double *t)
{
    const nv::CCEv &e = ((nv::Parsed *)p)->ccs[i];
    iv[0] = e.ch; iv[1] = e.cc; iv[2] = e.v;
    *t = e.t;
}

void nv_midi_pw(void *p, int i, int *iv, double *t)
{
    const nv::PwEv &e = ((nv::Parsed *)p)->pws[i];
    iv[0] = e.ch; iv[1] = e.pitch;
    *t = e.t;
}

// The parse into a song (native/channel.cpp's): its controllers and notes,
// each note's channel volume trimmed by trim[program] (trim[128 + program]
// for a drum set: patch_map.program_trim's, as the caller's file asks).
void nv_midi_song(void *p, void *song, const double *trim)
{
    const nv::Parsed *P = (nv::Parsed *)p;
    for (const nv::CCEv &e : P->ccs)
        nv_song_cc(song, e.ch, e.t, e.cc, e.v);
    for (const nv::Note &n : P->notes)
        nv_song_note(song, n.ch, n.note, n.on, n.off, n.vel, n.v7, n.v11, n.pan,
                     trim[(n.drum ? 128 : 0) + n.prog], n.prog, n.drum);
    for (const auto &l : P->legato)
        nv_song_legato(song, l[0], l[1], l[2]);
    for (const nv::CCEv &e : P->snd)
        nv_song_snd(song, e.ch, e.t, e.cc, e.v);
}

}  // extern "C"
