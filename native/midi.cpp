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
#include <limits>
#include <set>
#include <cstdint>
#include <cmath>
#include <cstring>
#include <map>
#include <string>
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
    int mcut = 0, mslur = 0;    // mono mode's: cut off by the next (_MONO_CUT), arrived by a slur (_MONO_SLUR)
    // its bank (resolve_patch): 0 the capital, 1 + 128 x map + msb GS's
    // (the map 0-4 as variation_tables keys it), 1 + 640 + lsb GM 2's
    int bsel = 0;
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
// 4 the pitch wheel (a: -8192..8191), 5 a program change (a: the program)
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
    std::vector<std::pair<int, int>> chprogs;  // ch_progs: a melodic channel's program changes, in message order
    std::vector<int> chbsel;    // ...each one's bank (Note.bsel)
    std::map<int, int> parts;   // _voice_parts: a channel's voice part, by its track's name (nv_voice_body)
    int master = 0;             // a master message (parse_master): every channel's pitch stream then
    int master_vol = 0;         // ...a master volume under full
    int banked = 0;             // a note on a bank (Note.bsel): the file renderer's, not live's yet
    // _mvol: each master volume (time, seq, gain), and each GM System On's full (1.0)
    std::vector<std::tuple<double, long, double>> mvol;
    // sotas: each channel's scale/octave tuning, (time, twelve cents) as sent
    std::map<int, std::vector<std::pair<double, std::array<double, 12>>>> sotas;
    // MTS (parse_mts): each dump or single-note change, in message order --
    // (time, seq), its bank and program, 128 Hz (NaN: keep)
    struct Mts {
        double t;
        long seq;
        int bank, prog;
        std::array<double, 128> hz;
    };
    std::vector<Mts> mts;
    std::vector<std::vector<uint8_t>> sysex;    // the live part's exclusives (events of type 6), as read
};

}  // namespace nv

// THE TUNING EXCLUSIVES, one parser for the file and the live part (the bytes
// between F0 and F7). 1 master (blockrender.parse_master: GS's 40 00 00/04/05,
// the universal 7F dd 04 01/03/04): iv[0] 1 volume (dv[0] its gain), 2 fine
// (cents), 3 coarse (semitones). 2 MTS (mts.parse_mts: 08 01/04 bulk dumps,
// 05/06 scale dumps, 02/07 single-note changes): iv[0] bank, iv[1] program,
// iv[2] a real-time single-note change, hz[128] (NaN: keep). 3 an MTS message
// not read (nothing). 4 GM 2's scale/octave tuning (parse_sota): iv[0] the
// channels (a bit each), dv[12] the cents. 0 none of these.
extern "C" int nv_tuning_excl(const uint8_t *d, int n, int *iv, double *dv, double *hz)
{
    const double NANV = std::numeric_limits<double>::quiet_NaN();
    // MASTER
    bool gsh = n >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && d[4] == 0x40 && d[5] == 0x00;
    if (gsh && d[6] == 0x04) {
        iv[0] = 1;
        dv[0] = pow((double)((d[7] << 7) | d[7]) / 16383.0, 2.0);
        return 1;
    }
    if (gsh && d[6] == 0x05) {
        iv[0] = 3;
        dv[0] = (double)(std::max(0x28, std::min(0x58, (int)d[7])) - 0x40);
        return 1;
    }
    if (gsh && d[6] == 0x00 && n >= 11) {
        int nib = (d[7] & 15) << 12 | (d[8] & 15) << 8 | (d[9] & 15) << 4 | (d[10] & 15);
        iv[0] = 2;
        dv[0] = (double)(std::max(0x18, std::min(0x7E8, nib)) - 0x400) / 10.0;
        return 1;
    }
    if (!gsh && n >= 6 && d[0] == 0x7F && d[2] == 0x04) {
        int ll = d[4], mm = d[5];
        if (d[3] == 0x01) {
            iv[0] = 1;
            dv[0] = pow((double)std::max(0, std::min(16383, (mm << 7) | ll)) / 16383.0, 2.0);
            return 1;
        }
        if (d[3] == 0x03) {
            iv[0] = 2;
            dv[0] = (double)(((mm << 7) | ll) - 8192) / 8192.0 * 100.0;
            return 1;
        }
        if (d[3] == 0x04) {
            iv[0] = 3;
            dv[0] = (double)(mm - 64);
            return 1;
        }
    }
    // MTS
    if (n >= 4 && (d[0] == 0x7E || d[0] == 0x7F) && d[2] == 0x08
        && (d[3] == 0x01 || d[3] == 0x02 || d[3] == 0x04 || d[3] == 0x05 || d[3] == 0x06 || d[3] == 0x07)) {
        auto word = [&](int xx, int yy, int zz) {
            if (xx == 0x7F && yy == 0x7F && zz == 0x7F)
                return NANV;                        // no change
            double nn = xx + ((yy << 7) | zz) / 16384.0;
            return 440.0 * pow(2.0, (nn - 69.0) / 12.0);
        };
        auto xsum = [&](int m) {
            int c = 0;
            for (int i = 0; i < m; i++)
                c ^= d[i];
            return c & 0x7F;
        };
        for (int k = 0; k < 128; k++)
            hz[k] = NANV;
        iv[2] = 0;
        int sub = d[3];
        if ((sub == 0x05 || sub == 0x06) && d[0] == 0x7E) {
            int m = sub == 0x05 ? 12 : 24;
            if (n >= 6 + 16 + m + 1 && xsum(22 + m) == d[22 + m]) {
                iv[0] = d[4];
                iv[1] = d[5];
                double c[12];
                for (int i = 0; i < 12; i++)
                    c[i] = sub == 0x05 ? (double)d[22 + i] - 64.0
                                       : (double)(((d[22 + 2 * i] << 7) | d[23 + 2 * i]) - 8192) / 8192.0 * 100.0;
                for (int k = 0; k < 128; k++)
                    hz[k] = 440.0 * pow(2.0, (k - 69) / 12.0) * pow(2.0, c[k % 12] / 1200.0);
                return 2;
            }
        } else if ((sub == 0x01 || sub == 0x04) && d[0] == 0x7E) {
            int off = 4;
            iv[0] = 0;
            if (sub == 0x04)
                iv[0] = d[off++];
            if (n >= off + 1 + 16 + 384 + 1) {
                iv[1] = d[off++];
                off += 16;
                if (!(sub == 0x04 && xsum(off + 384) != d[off + 384])) {
                    for (int k = 0; k < 128; k++)
                        hz[k] = word(d[off + 3 * k], d[off + 3 * k + 1], d[off + 3 * k + 2]);
                    return 2;
                }
            }
        } else if ((sub == 0x02 && d[0] == 0x7F) || sub == 0x07) {
            int off = 4;
            iv[0] = 0;
            if (sub == 0x07)
                iv[0] = d[off++];
            if (n >= off + 2) {
                iv[1] = d[off];
                int ll = d[off + 1];
                off += 2;
                for (int i = 0; i < ll && off + 4 * i + 4 <= n; i++) {
                    int k = d[off + 4 * i];
                    double f = word(d[off + 4 * i + 1], d[off + 4 * i + 2], d[off + 4 * i + 3]);
                    if (!std::isnan(f) && k >= 0 && k < 128)
                        hz[k] = f;
                }
                iv[2] = d[0] == 0x7F;
                return 2;
            }
        }
        return 3;
    }
    // GM 2's SCALE/OCTAVE TUNING
    if (n >= 7 && (d[0] == 0x7E || d[0] == 0x7F) && d[2] == 0x08 && (d[3] == 0x08 || d[3] == 0x09)) {
        int nb = n - 7;
        if (d[3] == 0x08 ? nb < 12 : nb < 24)
            return 0;
        for (int i = 0; i < 12; i++)
            dv[i] = d[3] == 0x08 ? (double)d[7 + i] - 64.0
                                 : (double)(((d[7 + 2 * i] << 7) | d[8 + 2 * i]) - 8192) / 8192.0 * 100.0;
        int m = 0;
        for (int b = 0; b < 2; b++)
            if (d[4] & (1 << b))
                m |= 1 << (14 + b);
        for (int b = 0; b < 7; b++) {
            if (d[5] & (1 << b))
                m |= 1 << (7 + b);
            if (d[6] & (1 << b))
                m |= 1 << b;
        }
        iv[0] = m;
        return 4;
    }
    return 0;
}

namespace nv {

static int tuning_excl(const uint8_t *d, int n, int *iv, double *dv, double *hz)
{
    return nv_tuning_excl(d, n, iv, dv, hz);
}

// _prep_mono_mode: MONO MODE (CC126 on, CC127 or GM System On off), each
// channel in it a single voice -- a key pressed takes the voice (the one it
// had cut, the handoff a slur), a key lifted that has it hands it back to
// the last key still held (a slur), or lets it go. Its notes rewritten as
// the spans the voice spent on each key, after the others, the way the
// Python appends them (the song sorts them stably after)
static void mono_mode(Parsed &P)
{
    std::vector<double> gm;
    for (const CCEv &e : P.snd)
        if (e.ch == -1 && e.cc == -1)
            gm.push_back(e.t);
    std::vector<int> chans;             // in the order their controllers first came (ccs' keys)
    for (const CCEv &e : P.ccs)
        if (std::find(chans.begin(), chans.end(), e.ch) == chans.end())
            chans.push_back(e.ch);
    std::vector<char> in_mono(P.notes.size(), 0);
    std::vector<Note> mono_notes;
    bool any = false;
    for (int c : chans) {
        std::vector<std::pair<double, bool>> mode;
        for (const CCEv &e : P.ccs)
            if (e.ch == c && (e.cc == 126 || e.cc == 127))
                mode.emplace_back(e.t, e.cc == 126);
        for (double t : gm)
            mode.emplace_back(t, false);
        std::stable_sort(mode.begin(), mode.end(), [](const std::pair<double, bool> &a,
                                                      const std::pair<double, bool> &b) { return a.first < b.first; });
        bool on = false;
        for (auto &m : mode)
            on = on || m.second;
        if (!on)
            continue;
        std::vector<std::pair<double, double>> spans;
        bool open = false;
        double st = 0.0;
        for (auto &m : mode) {
            if (m.second && !open) {
                st = m.first;
                open = true;
            } else if (!m.second && open) {
                spans.emplace_back(st, m.first);
                open = false;
            }
        }
        if (open)
            spans.emplace_back(st, P.total + 1.0);
        auto mono_at = [&](double t) {
            for (auto &s : spans)
                if (s.first <= t && t < s.second)
                    return true;
            return false;
        };
        std::vector<int> mine;
        for (size_t i = 0; i < P.notes.size(); i++)
            if (P.notes[i].ch == c && mono_at(P.notes[i].on))
                mine.push_back((int)i);
        if (mine.empty())
            continue;
        any = true;
        for (int i : mine)
            in_mono[i] = 1;
        // releases before presses at one instant (a key lifted as the next
        // goes down is no overlap), each list in the notes' order
        struct E {
            double t;
            int kind, n;
        };
        std::vector<E> ev;
        for (int i : mine)
            ev.push_back(E{P.notes[i].on, 1, i});
        for (int i : mine)
            ev.push_back(E{P.notes[i].off, 0, i});
        std::stable_sort(ev.begin(), ev.end(), [](const E &a, const E &b) {
            return a.t != b.t ? a.t < b.t : a.kind < b.kind;
        });
        std::vector<int> stack;
        bool have = false;
        int cur_n = -1;
        double cur_t = 0.0;
        bool cur_slur = false;
        auto emit = [&](int src, double start, double end, bool slur, bool cut) {
            if (end - start <= 1e-9)
                return;
            Note x = P.notes[src];
            x.ch = c;
            x.on = start;
            x.off = end;
            x.mslur = slur;
            x.mcut = cut;
            mono_notes.push_back(x);
        };
        for (const E &e : ev) {
            const Note &nn = P.notes[e.n];
            if (e.kind == 1) {
                if (have)
                    emit(cur_n, cur_t, e.t, cur_slur, true);
                std::vector<int> ns;
                for (int x : stack)
                    if (P.notes[x].note != nn.note)
                        ns.push_back(x);
                ns.push_back(e.n);
                stack.swap(ns);
                cur_slur = have;
                cur_n = e.n;
                cur_t = e.t;
                have = true;
            } else {
                bool top = have && P.notes[cur_n].note == nn.note;
                std::vector<int> ns;
                for (int x : stack)
                    if (P.notes[x].note != nn.note)
                        ns.push_back(x);
                stack.swap(ns);
                if (!top)
                    continue;           // already replaced: nothing sounds for it
                if (!stack.empty()) {
                    emit(cur_n, cur_t, e.t, cur_slur, true);
                    cur_n = stack.back();       // back to the key still down
                    cur_t = e.t;
                    cur_slur = true;
                } else {
                    emit(cur_n, cur_t, e.t, cur_slur, false);
                    have = false;
                }
            }
        }
    }
    if (!any)
        return;
    std::vector<Note> keep;
    for (size_t i = 0; i < P.notes.size(); i++)
        if (!in_mono[i])
            keep.push_back(P.notes[i]);
    keep.insert(keep.end(), mono_notes.begin(), mono_notes.end());
    P.notes.swap(keep);
}

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
    // _voice_parts: each track's first name (track or instrument), and each
    // channel a message of it speaks on after that -- the first track that
    // names a part for a channel declares it
    for (size_t ti = 0; ti < starts.size(); ti++) {
        size_t a = starts[ti], b = ti + 1 < starts.size() ? starts[ti + 1] : all.size();
        std::string name;
        for (size_t i = a; i < b; i++) {
            const Msg &m = all[i];
            if (m.status == 0xFF) {
                if ((m.meta == 0x03 || m.meta == 0x04) && name.empty())
                    name.assign(m.data.begin(), m.data.end());
                continue;
            }
            if (m.status == 0xF0 || m.status == 0xF7)
                continue;
            int ch = m.status & 0x0F;
            if (!name.empty() && !P.parts.count(ch)) {
                int part = nv_voice_body(name.c_str());
                if (part)
                    P.parts[ch] = part;
            }
        }
    }
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
    std::map<int, int> prog, bmsb, blsb, drums, bsel;
    // the map CC32 0 reads its bank in (blockrender.DEFAULT_MAP: TUNING_MAP)
    const char *tmap = getenv("TUNING_MAP");
    const int default_map = tmap && *tmap ? atoi(tmap) : 0;
    bool rxbank = true;
    std::map<std::pair<int, int>, std::vector<Note>> on;
    std::map<int, std::pair<int, int>> rsel;    // a channel's selected RPN, (MSB, LSB); absent: none
    std::map<int, std::pair<int, int>> nsel;    // ...and NRPN (_nsel); absent: none
    // each channel's RPNs as data entry left them (parse's _rrange, _rfmsb,
    // _rfine, _rcoarse, _rmod, _rtp, _rtb; absent: power-on)
    std::map<int, double> rrange, rfine, rcoarse, rmod;
    std::map<int, int> rfmsb, rtp, rtb;
    auto getd = [](const std::map<int, double> &m, int c, double d) {
        auto it = m.find(c);
        return it != m.end() ? it->second : d;
    };
    std::map<int, std::array<double, 12>> gsscale;     // each GS part's scale tuning, as held
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
            // THE TUNING EXCLUSIVES (tuning_excl): master, MTS, GM 2's scale --
            // each also an event for the live part (6, the bytes kept), as
            // live._sysex reads it; a master volume only refused at less than full
            {
                int ti[4];
                double td[12], th[128];
                int tk = tuning_excl(d.data(), (int)d.size(), ti, td, th);
                if (tk) {
                    if (tk == 1) {
                        bool gsh = d[0] == 0x41;
                        if (!seen_note && gsh)
                            P.gs = 1;
                        P.master = 1;
                        if (ti[0] == 1) {
                            P.mvol.push_back(std::make_tuple(t, seq, td[0]));
                            if (td[0] != 1.0)
                                P.master_vol = 1;
                        }
                        else if (ti[0] > 1)
                            P.pitch.push_back(PitchEv{-2, t, seq, ti[0] == 2 ? 10 : 11, td[0]});
                    } else if (tk == 2) {
                        Parsed::Mts e;
                        e.t = t;
                        e.seq = seq;
                        e.bank = ti[0];
                        e.prog = ti[1];
                        for (int k = 0; k < 128; k++)
                            e.hz[k] = th[k];
                        P.mts.push_back(e);
                    } else if (tk == 4) {
                        std::array<double, 12> c;
                        for (int i = 0; i < 12; i++)
                            c[i] = td[i];
                        for (int ch2 = 0; ch2 < 16; ch2++)
                            if (ti[0] & (1 << ch2))
                                P.sotas[ch2].push_back(std::make_pair(t, c));
                    }
                    if (tk != 3) {
                        P.events.push_back(LiveEv{t, 6, -1, (int)P.sysex.size(), 0});
                        P.sysex.push_back(d);
                    }
                    continue;               // (an MTS message not read: nothing, as Python's)
                }
            }
            // ...AND GS's SCALE TUNING C..B (parse_gs_part_state: 40 1p 40-4B,
            // one note or several), the part's scale held and sent whole
            if (d.size() >= 9 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && (d[4] == 0x40 || d[4] == 0x50)
                && (d[5] >> 4) == 1 && d[6] >= 0x40 && d[6] <= 0x4B) {
                int blk = d[5] & 0x0F;
                int ch2 = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0);
                if (d[4] == 0x50)
                    return -3;          // (port B: PortedMidi's)
                std::array<double, 12> &sc = gsscale[ch2];
                size_t a = d[6] - 0x40, nbody = d.size() - 8;      // (the values, without the checksum)
                for (size_t i = 0; i < nbody && a + i < 12; i++)
                    sc[a + i] = (double)d[7 + i] - 64.0;
                if (!seen_note)
                    P.gs = 1;
                P.sotas[ch2].push_back(std::make_pair(t, sc));
                continue;
            }
            if (!(lvl || gs))
                return -4;              // any other exclusive: not a GM file's
            if (!seen_note && d.size() >= 4 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12)
                P.gs = 1;
            rxbank = lvl != 1;
            bmsb.clear(); blsb.clear(); drums.clear(); prog.clear(); bsel.clear(); ctrl.clear(); rsel.clear(); nsel.clear();
            P.mvol.push_back(std::make_tuple(t, seq, 1.0));      // (the master volume back to full)
            P.events.push_back(LiveEv{t, 6, -1, (int)P.sysex.size(), 0});     // (the live part's too)
            P.sysex.push_back(d);
            // BACK TO POWER-ON: every tuning the file set, from here (gmon) --
            // each channel's scale at 0, the GS part's scale held cleared
            for (auto &so : P.sotas)
                so.second.push_back(std::make_pair(t, std::array<double, 12>{}));
            gsscale.clear();
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
            // THE BANK (tonelib.resolve_patch): ignored after GM 1's System On;
            // MSB 120 a drum set, 121 GM 2's tone by its LSB; a drum channel
            // stays one; else GS's variation, read in the map CC32 names
            // (or, at 0, TUNING_MAP's)
            int msb = bmsb.count(ch) ? bmsb[ch] : 0, lsb = blsb.count(ch) ? blsb[ch] : 0;
            int mp = lsb ? lsb : default_map, dr = is_drums(ch), bs = 0;
            if (!rxbank)
                ;
            else if (msb == 120)
                dr = 1;
            else if (msb == 121) {
                dr = 0;
                bs = lsb ? 1 + 640 + lsb : 0;
            } else if (!dr)
                bs = msb ? 1 + 128 * (mp >= 1 && mp <= 4 ? mp : 0) + msb : 0;
            if (dr && msb != 120 && mp)
                return -5;              // a drum set read in a map (kit_in_map): patch_map's
            drums[ch] = dr;
            bsel[ch] = bs;
            P.banked |= rxbank && (msb || lsb);     // (a bank, or a map: live's not yet)
            prog[ch] = m.d0;
            P.progs.push_back(std::make_pair(ch, m.d0));
            if (!drums[ch]) {
                P.chprogs.push_back(std::make_pair(ch, m.d0));  // (a drum set is no organ's program)
                P.chbsel.push_back(bs);
            }
            P.events.push_back(LiveEv{t, 5, ch, m.d0, 0});
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
                // ...unless it is one of GS's eight sound NRPNs, the same
                // controls as CC71-78 under an older address (_nsel)
                auto nt = nsel.find(ch);
                std::pair<int, int> n0 = nt != nsel.end() ? nt->second : std::make_pair(127, 127);
                nsel[ch] = cc == 99 ? std::make_pair(v, n0.second) : std::make_pair(n0.first, v);
            } else if (cc == 101 || cc == 100) {
                nsel.erase(ch);
                auto it = rsel.find(ch);
                std::pair<int, int> cur = it != rsel.end() ? it->second : std::make_pair(127, 127);
                rsel[ch] = cc == 101 ? std::make_pair(v, cur.second) : std::make_pair(cur.first, v);
            } else if (cc == 6 || cc == 38) {
                auto it = rsel.find(ch);
                if (it == rsel.end()) {
                    // AN NRPN's data: GS's sound NRPNs as their CC71-78; a
                    // drum instrument's own (GS_DRUM_NRPN) Python's; any
                    // other nothing
                    auto nt = nsel.find(ch);
                    if (nt == nsel.end())
                        continue;
                    static const int DRUM[] = {0x18, 0x1A, 0x1C, 0x1D, 0x1E, 0x1F};
                    for (int d : DRUM)
                        if (nt->second.first == d && cc == 6)
                            return -6;
                    static const int GSN[8][3] = {{1, 0x08, 76}, {1, 0x09, 77}, {1, 0x0A, 78}, {1, 0x20, 74},
                                                  {1, 0x21, 71}, {1, 0x63, 73}, {1, 0x64, 75}, {1, 0x66, 72}};
                    for (auto &g : GSN)
                        if (nt->second == std::make_pair(g[0], g[1]) && cc == 6)
                            P.snd.push_back(CCEv{ch, t, g[2], v});
                    continue;
                }
                if (it->second == std::make_pair(0, 6))
                    return -6;          // MPE's configuration
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
            n.bsel = n.drum || !bsel.count(ch) ? 0 : bsel[ch];
            P.banked |= n.bsel != 0;
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
    mono_mode(P);
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

// MTS message i (parse_mts): its time and seq, bank and program, 128 Hz (NaN: keep)
int nv_midi_n_mts(void *p) { return (int)((nv::Parsed *)p)->mts.size(); }
void nv_midi_mts(void *p, int i, double *t, long *seq, int *bank, int *prog, double *hz)
{
    const nv::Parsed::Mts &e = ((nv::Parsed *)p)->mts[i];
    *t = e.t;
    *seq = e.seq;
    *bank = e.bank;
    *prog = e.prog;
    for (int k = 0; k < 128; k++)
        hz[k] = e.hz[k];
}

// _prep_octave_tuning for channel ch: 1 and its twelve cents (out) if a
// scale is in force at its first note (the last at or before it, by time,
// stably; else the first sent) and not all 0, else 0
int nv_midi_otun(void *p, int ch, double *out)
{
    const nv::Parsed *P = (nv::Parsed *)p;
    auto it = P->sotas.find(ch);
    if (it == P->sotas.end() || it->second.empty())
        return 0;
    double f = INFINITY;
    for (const nv::Note &n : P->notes)
        if (n.ch == ch && n.on < f)
            f = n.on;
    if (f == INFINITY)
        return 0;
    std::vector<std::pair<double, std::array<double, 12>>> ev = it->second;
    std::stable_sort(ev.begin(), ev.end(), [](const std::pair<double, std::array<double, 12>> &a,
                                              const std::pair<double, std::array<double, 12>> &b) {
        return a.first < b.first;
    });
    const std::array<double, 12> *tab = &ev[0].second;
    for (auto r = ev.rbegin(); r != ev.rend(); ++r)
        if (r->first <= f + 1e-6) {
            tab = &r->second;
            break;
        }
    bool any = false;
    for (int i = 0; i < 12; i++) {
        out[i] = (*tab)[i];
        any = any || fabs(out[i]) > 1e-9;
    }
    return any ? 1 : 0;
}

// _mvol: the master volume's steps (sample, gain) into s, g (cap), in the
// file's order (time, then place); their count, 0 for a file that only ever
// says "full"
int nv_midi_mvol(void *p, double sr, long long *s, double *g, int cap)
{
    const nv::Parsed *P = (nv::Parsed *)p;
    std::vector<std::tuple<double, long, double>> mv = P->mvol;
    std::stable_sort(mv.begin(), mv.end(), [](const std::tuple<double, long, double> &a,
                                              const std::tuple<double, long, double> &b) {
        return std::get<0>(a) < std::get<0>(b) || (std::get<0>(a) == std::get<0>(b) && std::get<1>(a) < std::get<1>(b));
    });
    bool any = false;
    for (auto &e : mv)
        any = any || !(fabs(std::get<2>(e) - 1.0) < 1e-12);
    if (!any)
        return 0;
    int n = 0;
    for (auto &e : mv) {
        if (n < cap) {
            s[n] = (long long)nearbyint(std::get<0>(e) * sr);
            g[n] = std::get<2>(e);
        }
        n++;
    }
    return n;
}

// a tuning exclusive (master, scale/octave, MTS) in the file: 1, else 0
int nv_midi_tuning_excl(void *p)
{
    const nv::Parsed *P = (nv::Parsed *)p;
    return P->master || !P->sotas.empty() || !P->mts.empty() ? 1 : 0;
}

// a master message (1), a master volume under full (2), none (0)
int nv_midi_master(void *p)
{
    const nv::Parsed *P = (nv::Parsed *)p;
    return P->master_vol ? 2 : P->master ? 1 : 0;
}
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
// exclusive i (an event of type 6's a): its bytes into out (cap), its length
int nv_midi_sysex(void *p, int i, uint8_t *out, int cap)
{
    const nv::Parsed *P = (nv::Parsed *)p;
    if (i < 0 || i >= (int)P->sysex.size())
        return -1;
    const std::vector<uint8_t> &b = P->sysex[i];
    for (int k = 0; k < (int)b.size() && k < cap; k++)
        out[k] = b[k];
    return (int)b.size();
}

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

// note i's bank (Note.bsel: 0 the capital); any note's (a file live does not play yet)
int nv_midi_note_bsel(void *p, int i) { return ((nv::Parsed *)p)->notes[i].bsel; }
int nv_midi_banked(void *p) { return ((nv::Parsed *)p)->banked; }
int nv_midi_chprog_bsel(void *p, int i) { return ((nv::Parsed *)p)->chbsel[i]; }

// ch_progs: the program changes on melodic channels, in message order
int nv_midi_n_chprogs(void *p) { return (int)((nv::Parsed *)p)->chprogs.size(); }
void nv_midi_chprog(void *p, int i, int *iv)
{
    iv[0] = ((nv::Parsed *)p)->chprogs[i].first;
    iv[1] = ((nv::Parsed *)p)->chprogs[i].second;
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
    for (const nv::Note &n : P->notes) {
        int n0 = nv_song_n_notes(song);
        nv_song_note(song, n.ch, n.note, n.on, n.off, n.vel, n.v7, n.v11, n.pan,
                     trim[(n.drum ? 128 : 0) + n.prog], n.prog, n.drum);
        if (n.bsel)
            nv_song_note_bank(song, n.bsel);    // its variation: its slot, or its layers
        if (n.mcut || n.mslur)
            for (int j = n0; j < nv_song_n_notes(song); j++)
                nv_song_note_mono(song, j, n.mcut, n.mslur);
    }
    for (const auto &l : P->legato)
        nv_song_legato(song, l[0], l[1], l[2]);
    for (const nv::CCEv &e : P->snd)
        nv_song_snd(song, e.ch, e.t, e.cc, e.v);
    for (const auto &pt : P->parts)
        nv_song_set_part(song, pt.first, pt.second);
}

}  // extern "C"
