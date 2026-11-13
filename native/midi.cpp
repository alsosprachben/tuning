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
#include "gsrx.h"
#include "mpe.h"

namespace nv {

struct Msg {
    long long tick;             // absolute, then relative
    int status, d0, d1;         // a channel message's bytes; status 0xFF meta, 0xF0 sysex
    int meta;                   // a meta event's type
    std::vector<uint8_t> data;  // a meta event's or a sysex's bytes
    int port = 0;               // its track's MIDI port (FF 21), a two-port file's: its channels + 16 x it
    // THE PARTS' RECEIVE SETTINGS (gsrx.h): 0 every reader's; 1 the message as
    // sent, the live part's only (it receives it itself: host.cpp's stage);
    // 2 a part's copy as it receives it, the file render's only
    int rx = 0;
    bool direct = false;        // a part's own (a part parameter's, the CM-64 map's): no channel to route
};

// A GS PART PARAMETER that a MIDI message carries (parse_gs_part): its channel
// and port, and the channel messages it is (status kind, d0, d1); false if it is none
static bool gs_part_msgs(const std::vector<uint8_t> &d, int *ch, int *port, std::vector<std::array<int, 3>> &out)
{
    out.clear();
    if (!(d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && (d[4] == 0x40 || d[4] == 0x50)))
        return false;
    int hi = d[5] >> 4;
    if (hi != 1 && hi != 2 && hi != 4)
        return false;
    int blk = d[5] & 0x0F;
    *ch = blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk);
    *port = d[4] == 0x50 ? 1 : 0;
    int a = d[6], v = d[7];
    auto C = [&](int cc, int val) { out.push_back({0xB0, cc, std::max(0, std::min(127, val))}); };
    auto rpn = [&](int lsb, int msb6, int lsb38, bool fine) {
        C(101, 0);
        C(100, lsb);
        C(6, msb6);
        if (fine)
            C(38, lsb38);
        C(101, 127);
        C(100, 127);
    };
    static const int TONE_MODIFY[8] = {76, 77, 74, 71, 73, 75, 72, 78};     // (GS_TONE_MODIFY_CC)
    if (hi == 4) {                      // TONE MAP NUMBER: CC32
        if (a != 0x00 || v > 4)
            return false;
        C(32, v);
    } else if (hi == 2) {               // the controllers' destinations: the bend range, LFO1's pitch depth
        if (a == 0x10)
            rpn(0, std::max(0, std::min(24, v - 0x40)), 0, true);
        else if (a == 0x04) {
            double ct = v * 600.0 / 127.0;
            rpn(5, (int)floor(ct / 100.0), (int)nearbyint(fmod(ct, 100.0) * 128.0 / 100.0), true);
        } else
            return false;
    } else if (a == 0x00 && d.size() >= 9) {    // TONE NUMBER: CC0, then the program
        C(0, v);
        out.push_back({0xC0, d[8], 0});
    } else if (a == 0x13) {             // MONO/POLY
        if (v == 0)
            C(126, 1);
        else
            C(127, 0);
    } else if (a == 0x16) {             // PITCH KEY SHIFT: RPN 2
        rpn(2, 64 + std::max(-24, std::min(24, v - 0x40)), 0, false);
    } else if (a == 0x19) {
        C(7, v);                        // PART LEVEL
    } else if (a == 0x1C) {
        C(10, v ? v : 64);              // PART PANPOT (0 random: centre)
    } else if (a == 0x21) {
        C(93, v);                       // CHORUS SEND
    } else if (a == 0x22) {
        C(91, v);                       // REVERB SEND
    } else if (a == 0x2C) {
        C(94, v);                       // DELAY SEND
    } else if (a == 0x2A && d.size() >= 10) {   // PITCH FINE TUNE: RPN 1, MSB LSB
        rpn(1, v, d[8], true);
    } else if (a >= 0x30 && a <= 0x37) {
        C(TONE_MODIFY[a - 0x30], v);    // TONE MODIFY 1-8: the sound controllers
    } else {
        return false;
    }
    return true;
}

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
    // MPE's ZONES over time (blockrender's mpe_ev): at each MCM that changed
    // one, every channel in MPE and its (group, side) -- prepare's _manager
    std::vector<std::pair<double, std::map<int, std::pair<int, int>>>> mpe;
    // THE SOUND CANVAS'S DISPLAY (gsdisplay): its messages (model 45H) and
    // their times, for the render's text (OUT.display.txt); nothing sounds of them
    struct Disp {
        double t;
        std::vector<uint8_t> d;
    };
    std::vector<Disp> disp;
    std::vector<PitchEv> pitch;
    std::vector<Note> notes;
    std::vector<CCEv> ccs;      // in message order
    std::vector<PwEv> pws;
    std::vector<CCEv> ats;      // ats: each channel's aftertouch (D0) and CC121's 0, in message order
    std::vector<CCEv> pts;      // pts: each key's polytouch (A0: cc its key), in message order
    std::vector<std::pair<int, int>> progs;     // (channel, program) changes, for the caller
    double total = 0.0;
    int gs = 0;                 // a Roland GS exclusive before the first note (gs_setup: the file speaks GS)
    // THE GS SETUP by the first note (gs_setup), a reset back to none: the
    // reverb's, chorus's and delay's parameters (40 01 xx: address -> value,
    // a macro the rest gone), the EQ's (40 02 0-3), each part's EQ switch
    std::map<int, int> gs_rv, gs_ch, gs_dl, gs_eq, gs_sw;
    // THE DRUM INSTRUMENTS' OWN (dedit: GS_DRUM_NRPN), in message order: the
    // channel (-1 every one), key (-1 a reset), parameter (0 pitch, 1 level,
    // 2 pan, 3 reverb, 4 chorus, 5 delay) and value (pitch about 0)
    // THE USER DRUM SETS (parse_gs_user_drum: 21 dp kk vv): (set 0/1, key) ->
    // its parameters as sent, by number (1 play note ... C source note); the
    // whole file's, as Python's uset
    std::map<std::pair<int, int>, std::map<int, int>> uset;
    struct DEdit {
        int ch;
        double t;
        int key, par, v;
    };
    std::vector<DEdit> dedit;
    // THE CONTROLLER MATRIX's sums as they move (_cmx_upd's cmx): kind 0
    // amp, 1 tva, 2 pitch, 3 cutoff, 4 tvf, 5 rate, 6 vib; channel, time, value
    struct CmxEv {
        int kind, ch;
        double t, v;
    };
    std::vector<CmxEv> cmx;
    // THE INSERTION EFFECT's timeline (gsefx.parse), a reset an event too:
    // kind 0 a reset, 1 the type (a msb, b lsb), 2 a parameter (a 1-20, b),
    // 3 a send (a its address, b), 4 an effect controller's (a, b), 5 a
    // part's assign (a its channel, b on), 6 a source's value (a its
    // source: a CC, 0x60 aftertouch, 0x61 bend; b)
    struct Efx {
        double t;
        int kind, a, b;
    };
    std::vector<Efx> efx;
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
            int kind = m.status & 0xF0, ch = (m.status & 0x0F) + 16 * m.port;
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
static std::vector<int> g_map_kits;     // (nv_midi_map_kits)
static bool g_map_kits_set = false;
static bool g_map_kits_play = false;    // (nv_midi_map_kits_play: the export has their tables)
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
    // A TWO-PORT FILE (PortedMidi): each track's messages its port's, a
    // part's exclusive at port B as port A would read it (40 / 50 swapped)
    bool ported = false;
    for (const Msg &m : all)
        ported = ported || (m.status == 0xFF && m.meta == 0x21 && !m.data.empty() && m.data[0]);
    if (ported) {
        for (size_t ti = 0; ti < starts.size(); ti++) {
            size_t a = starts[ti], b = ti + 1 < starts.size() ? starts[ti + 1] : all.size();
            int port = 0;
            for (size_t i = a; i < b; i++) {
                Msg &m = all[i];
                if (m.status == 0xFF && m.meta == 0x21 && !m.data.empty())
                    port = m.data[0];
                m.port = port;
                const std::vector<uint8_t> &d = m.data;
                if (port && m.status == 0xF0 && d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12
                    && (d[4] == 0x40 || d[4] == 0x50) && ((d[5] & 0xF0) == 0x10 || (d[5] & 0xF0) == 0x20
                                                          || (d[5] & 0xF0) == 0x40))
                    m.data[4] ^= 0x10;
            }
        }
        // ...its legato over the merged stream (the Python's one merged track)
        std::vector<Msg> merged(all);
        std::stable_sort(merged.begin(), merged.end(), [](const Msg &a, const Msg &b) { return a.tick < b.tick; });
        legato_ticks(merged, std::vector<size_t>{0}, tpb, P.legato);
    } else {
        legato_ticks(all, starts, tpb, P.legato);
    }
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
    {
        // ...EACH GS PART PARAMETER's MESSAGES after it (blockrender's _inj:
        // read next, in order, through the same code)
        std::vector<Msg> ex;
        ex.reserve(msgs.size());
        std::vector<std::array<int, 3>> pm;
        for (const Msg &m : msgs) {
            ex.push_back(m);
            int pch, pport;
            if (m.status != 0xF0 || !gs_part_msgs(m.data, &pch, &pport, pm))
                continue;
            for (const auto &x : pm) {
                Msg y{0, x[0] | pch, x[1], x[2], 0, {}};
                y.port = pport;
                y.direct = true;
                ex.push_back(y);
            }
        }
        msgs.swap(ex);
    }
    // THE CM-64 SOUND MAP (blockrender.CM64, TUNING_CM64=1): "Init CM-64"'s
    // messages before the file's (cm64_init: each part's bank, its SC-55
    // map, program, level, pan, sends and bend range 12), and every pan a
    // CM-64's, mirrored (cm64_pan); its own exclusives change nothing, below
    const char *cm64e = getenv("TUNING_CM64");
    const bool cm64 = cm64e && !strcmp(cm64e, "1");
    if (cm64) {
        static const int PARTS[16][3] = {{127, 0, 64}, {127, 68, 54}, {127, 48, 54}, {127, 95, 54}, {127, 78, 54},
                                         {127, 41, 18}, {127, 3, 91}, {127, 110, 1}, {127, 122, 127}, {0, 127, 64},
                                         {126, 27, 64}, {126, 29, 81}, {126, 0, 64}, {126, 37, 99}, {126, 13, 27},
                                         {126, 46, 45}};
        auto pan = [](int v) { return std::max(0, std::min(127, 128 - v)); };
        std::vector<Msg> ex;
        for (int ch = 0; ch < 16; ch++) {
            auto cc = [&](int c, int v) {
                ex.push_back(Msg{0, 0xB0 | ch, c, v, 0, {}});
                ex.back().direct = true;
            };
            if (ch != 9) {
                cc(0, PARTS[ch][0]);
                cc(32, 1);
            }
            ex.push_back(Msg{0, 0xC0 | ch, PARTS[ch][1], 0, 0, {}});
            ex.back().direct = true;
            cc(7, 100); cc(10, pan(PARTS[ch][2])); cc(91, 64); cc(93, 0);
            cc(101, 0); cc(100, 0); cc(6, 12); cc(38, 0); cc(101, 127); cc(100, 127);
        }
        for (Msg m : msgs) {
            if ((m.status & 0xF0) == 0xB0 && m.d0 == 10)
                m.d1 = pan(m.d1);
            ex.push_back(m);
        }
        msgs.swap(ex);
    }
    {
        // THE PARTS' RECEIVE SETTINGS (blockrender's _stream, gsrx): once a file
        // sets one, each channel message as the parts take it -- the message
        // as sent kept for the live part (rx 1), each part's copy for the file
        // (rx 2, at the same tick); untouched while none is set
        GsReceive rc(32);
        std::vector<Msg> ex;
        ex.reserve(msgs.size());
        std::vector<std::pair<int, int>> pans, to;
        bool any = false;
        for (const Msg &m : msgs) {
            if (m.status == 0xF0) {
                const std::vector<uint8_t> &d = m.data;
                const int k = rc.sysex(d, pans);
                const bool gm = d.size() >= 4 && d[0] == 0x7E && d[2] == 0x09 && (d[3] == 0x01 || d[3] == 0x03);
                const bool gsr = d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12
                                 && ((d[4] == 0x40 && d[5] == 0x00 && d[6] == 0x7F && d[7] == 0x00)
                                     || (d[4] == 0x00 && d[5] == 0x00 && d[6] == 0x7F));
                if (k < 0 && (gm || gsr))
                    rc.reset();
                any = any || k >= 0;
                ex.push_back(m);
                for (const auto &pv : pans) {
                    Msg y{0, 0xB0 | (pv.first % 16), 10, pv.second, 0, {}};
                    y.port = pv.first / 16;
                    y.rx = 2;
                    ex.push_back(y);
                }
                continue;
            }
            const int kind = m.status & 0xF0;
            if (!any || m.status == 0xFF || m.direct || kind < 0x80 || kind > 0xE0 || rc.plain()) {
                ex.push_back(m);
                continue;
            }
            const int ch = (m.status & 0x0F) + 16 * m.port;
            rc.route(ch, kind, m.d0, m.d1, to);
            Msg o = m;
            o.rx = 1;
            ex.push_back(o);
            for (const auto &pv : to) {
                Msg y = m;
                y.tick = 0;
                y.status = kind | (pv.first % 16);
                y.port = pv.first / 16;
                if (kind == 0xB0)
                    y.d1 = pv.second;
                y.rx = 2;
                ex.push_back(y);
            }
        }
        msgs.swap(ex);
    }

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
    // ...its VELOCITY SENSE and KEY RANGE (parse_gs_part_state: vsd, vso, klo, khi), its TONE
    // MAP-0 (the map CC32 0 means on it), and a drum part's map (_rmap: 0 MAP1, 1 MAP2)
    std::map<int, std::array<int, 4>> gsstate;
    std::map<int, int> map0, rmap;
    long seq = 0;
    bool seen_note = false;
    // ...the EFX as it stands while reading (_efxst, _efxparts): a
    // controller that is one of its effect controllers' sources, on a part
    // on it, joins the timeline as that source's value (gsefx 'cv')
    // THE CONTROLLER MATRIX (ctrlmatrix, blockrender's _cmx): each part's
    // table, a source (0 mod, 1 bend, 2 cat, 3 pat, 4 cc1, 5 cc2, 100 + n
    // a CC) and destination (GS_DESTS's 0-10) to a depth, in the order set
    // (a reset's: the mod wheel's 47 cents, the bend's 2 semitones); the
    // seven sums it keeps (amp, tva, pitch, cutoff, tvf, rate, vib) as last
    // read -- any that moves from rest is a pass the engine lacks (-8)
    struct Cmx {
        std::vector<std::pair<std::pair<int, int>, double>> gs;
        int cc1 = 16, cc2 = 17;
        void reset()
        {
            gs.clear();
            gs.push_back({{0, 4}, 10 * 600.0 / 127.0});
            gs.push_back({{1, 0}, 2.0});
            cc1 = 16; cc2 = 17;
        }
        void set(int src, int dest, double dep)
        {
            for (auto &e : gs)
                if (e.first.first == src && e.first.second == dest) {
                    e.second = dep;
                    return;
                }
            gs.push_back({{src, dest}, dep});
        }
    };
    std::map<int, Cmx> cmx;
    std::map<int, std::array<double, 7>> cmx_last;
    std::map<int, int> cat_now, bend_now;
    std::map<int, std::map<int, int>> pat_now;
    const char *mve = getenv("TUNING_MOD_VIBRATO");
    const bool modvib = mve && *mve && strcmp(mve, "0") && strcmp(mve, "off");
    auto cmx_upd = [&](double t, int ch) {
        auto mi = cmx.find(ch);
        if (mi == cmx.end())
            return;
        // (cells(): CC1 and CC2 resolved, zero cells left out, equal keys summed)
        std::vector<std::pair<std::pair<int, int>, double>> cl;
        for (const auto &e : mi->second.gs) {
            int src = e.first.first == 4 ? 100 + mi->second.cc1 : e.first.first == 5 ? 100 + mi->second.cc2
                                                                                      : e.first.first;
            if (!e.second)
                continue;
            bool got = false;
            for (auto &o : cl)
                if (o.first.first == src && o.first.second == e.first.second) {
                    o.second = o.second + e.second;
                    got = true;
                }
            if (!got)
                cl.push_back({{src, e.first.second}, 0.0 + e.second});
        }
        auto &c = ctrl[ch];
        auto val = [&](int src) {
            if (src == 0)
                return (c.count(1) ? c[1] : 0) / 127.0;
            if (src == 2)
                return (cat_now.count(ch) ? cat_now[ch] : 0) / 127.0;
            if (src == 1)
                return (bend_now.count(ch) ? bend_now[ch] : 0) / 8192.0;
            if (src == 3) {
                auto pk = pat_now.find(ch);
                if (pk == pat_now.end() || pk->second.empty())
                    return 0.0;
                int mx = 0;
                for (auto &kv : pk->second)
                    mx = std::max(mx, kv.second);
                return mx / 127.0;
            }
            if (src >= 100)
                return (c.count(src - 100) ? c[src - 100] : 0) / 127.0;
            return 0.0;
        };
        auto sum = [&](int dest, int skip) {
            double s = 0.0;
            for (const auto &o : cl)
                if (o.first.second == dest && o.first.first != skip)
                    s = s + o.second * val(o.first.first);
            return s;
        };
        std::array<double, 7> now = {
            std::max(0.0, 1.0 + sum(2, -1)), std::max(0.0, std::min(1.0, sum(6, -1) + sum(10, -1))), sum(0, 1),
            sum(1, -1), std::max(0.0, sum(5, -1) + sum(9, -1)), sum(3, -1),
            std::max(0.0, sum(4, modvib ? -1 : 0) + sum(8, modvib ? -1 : 0))};
        auto li = cmx_last.find(ch);
        std::array<double, 7> last = li != cmx_last.end() ? li->second
                                                          : std::array<double, 7>{1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
        for (int q = 0; q < 7; q++)
            if (fabs(now[q] - last[q]) > 1e-9)
                P.cmx.push_back(Parsed::CmxEv{q, ch, t, now[q]});
        cmx_last[ch] = now;
    };
    int efx_src[2] = {0, 0};
    std::map<int, int> efx_cvv;
    std::set<int> efx_on;
    auto efx_cv = [&](double t, int ch, int src, int v) {
        if (!efx_on.count(ch) || (src != efx_src[0] && src != efx_src[1]))
            return;
        auto it = efx_cvv.find(src);
        if (it != efx_cvv.end() && it->second == v)
            return;
        efx_cvv[src] = v;
        P.efx.push_back(Parsed::Efx{t, 6, src, v});
    };
    if (cm64)                               // (the CM-64 map's mod wheel depth, each part's matrix: 4 cents)
        for (int ch = 0; ch < 16; ch++) {
            auto mi = cmx.find(ch);
            if (mi == cmx.end()) {
                mi = cmx.emplace(ch, Cmx()).first;
                mi->second.reset();
            }
            mi->second.set(0, 4, 4.0);
            cmx_upd(t, ch);
        }
    // MPE (blockrender's _mpe): the zones in force, and the messages they
    // imply, read next through the same code (its _inj: a manager's control
    // copied to its members, a mode message to each member, the resets an
    // MCM causes), the file's next after them
    MpeZones mpe;
    std::vector<Msg> inj;
    size_t inj_at = 0, mi_at = 0;
    // (the message as sent, for the live part alone -- it reads MPE and the
    // receive settings itself: a message the file's reading drops or copies)
    auto live_only = [&](const Msg &x) {
        const int lk = x.status & 0xF0, lc = (x.status & 0x0F) + 16 * x.port;
        if (lk == 0xC0)
            P.events.push_back(LiveEv{t, 5, lc, x.d0, 0});
        else if (lk == 0xB0)
            P.events.push_back(LiveEv{t, 2, lc, x.d0, x.d1});
        else if (lk == 0xE0)
            P.events.push_back(LiveEv{t, 4, lc, ((x.d1 << 7) | x.d0) - 8192, 0});
        else if (lk == 0x90 && x.d1 > 0) {
            seen_note = true;
            P.events.push_back(LiveEv{t, 0, lc, x.d0, x.d1});
        } else if (lk == 0x80 || lk == 0x90)
            P.events.push_back(LiveEv{t, 1, lc, x.d0, 0});
        else if (lk == 0xD0)
            P.events.push_back(LiveEv{t, 3, lc, x.d0, 0});
        else if (lk == 0xA0)
            P.events.push_back(LiveEv{t, 7, lc, x.d0, x.d1});
    };
    while (true) {
        Msg m_;
        bool injected = false;
        if (inj_at < inj.size()) {
            m_ = inj[inj_at++];
            injected = true;
            if (inj_at == inj.size()) {
                inj.clear();
                inj_at = 0;
            }
        } else if (mi_at < msgs.size())
            m_ = msgs[mi_at++];
        else
            break;
        const Msg &m = m_;
        seq++;
        double delta = m.tick > 0 ? m.tick * (tempo * 1e-6 / tpb) : 0.0;
        t += delta;
        if (m.rx == 1) {                        // (the message as sent: the live part's alone)
            seq--;
            live_only(m);
            continue;
        }
        const bool live_ev = m.rx != 2 && !injected;    // (a part's copy, MPE's: the file render's alone)
        // MPE's ROUTING (blockrender's): on a member, a zone-wide control
        // ignored (2.3.1), a mode message to every member when it is on the
        // lowest, program change and poly pressure ignored (2.3.3, 2.2.7); on
        // the manager, a control change copied to every member but those
        // _MPE_NOT_FANNED, and CC126/127 ignored
        if (mpe && !injected && m.status >= 0x80 && m.status < 0xF0) {
            const int mc = (m.status & 0x0F) + 16 * m.port, mk = m.status & 0xF0;
            if (mpe.zone_of(mc)) {
                bool drop = false;
                if (mpe.is_member(mc)) {
                    if (mk == 0xB0) {
                        const int c0 = m.d0;
                        if (c0 == 126 || c0 == 127) {
                            if (mc == mpe.lowest_member(mc))
                                for (int m2 : mpe.members(mc)) {
                                    Msg y = m;
                                    y.tick = 0;
                                    y.status = 0xB0 | (m2 & 15);
                                    y.port = m2 / 16;
                                    inj.push_back(y);
                                }
                            drop = true;
                        } else if (!(c0 == 74 || c0 == 6 || c0 == 38 || c0 == 96 || c0 == 97 || c0 == 98 || c0 == 99
                                     || c0 == 100 || c0 == 101 || c0 == 120 || c0 == 121 || c0 == 123))
                            drop = true;
                    } else if (mk == 0xC0 || mk == 0xA0)
                        drop = true;
                } else if (mk == 0xB0) {
                    if (m.d0 == 126 || m.d0 == 127)
                        drop = true;
                    else if (!mpe_not_fanned(m.d0))
                        for (int m2 : mpe.members(mc)) {
                            Msg y = m;
                            y.tick = 0;
                            y.status = 0xB0 | (m2 & 15);
                            y.port = m2 / 16;
                            inj.push_back(y);
                        }
                }
                if (drop) {
                    if (live_ev)
                        live_only(m);
                    continue;
                }
            }
        }
        if (m.status == 0xFF) {
            if (m.meta == 0x51 && m.data.size() == 3)
                tempo = (m.data[0] << 16) | (m.data[1] << 8) | m.data[2];
            continue;
        }
        if (m.status == 0xF0) {
            const std::vector<uint8_t> &d = m.data;
            // WHAT LIVE READS ITSELF, the file's setup aside (live._sysex): the
            // system effects (40 01 30-5A), the EQ (40 02 0x, a part's 4p 20),
            // a part's receive settings (1p 02-12, 14, 1F, 20) and master pan
            // (40 00 06) -- an event of their own for the live part, which the
            // parse below would leave it none of (nvlive --test, nvlive_check)
            if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && (d[4] == 0x40 || d[4] == 0x41 || d[4] == 0x21)) {
                const int a5 = d[5], a6 = d[6];
                const bool sys = a5 == 0x01 && a6 >= 0x30 && a6 <= 0x5A;
                const bool eq = (a5 == 0x02 && a6 <= 3) || ((a5 >> 4) == 4 && a6 == 0x20);
                const bool rx = (a5 >> 4) == 1 && ((a6 >= 0x02 && a6 <= 0x12) || a6 == 0x14 || a6 == 0x1F || a6 == 0x20
                                                   || a6 == 0x1A || a6 == 0x1B || a6 == 0x1D || a6 == 0x1E);
                const bool mp = a5 == 0x00 && a6 == 0x06;
                const bool ctl = (a5 >> 4) == 2;           // (...the controller matrix's cells)
                if (sys || eq || rx || mp || ctl || d[4] == 0x41 || d[4] == 0x21) {   // (...drum setup, user drum sets: live's)
                    P.events.push_back(LiveEv{t, 6, -1, (int)P.sysex.size(), 0});
                    P.sysex.push_back(d);
                }
            }
            if (d.size() >= 6 && d[0] == 0x7F && d[2] == 0x09 && d[3] >= 1 && d[3] <= 3) {
                P.events.push_back(LiveEv{t, 6, -1, (int)P.sysex.size(), 0});     // (GM2's controller matrix: live's)
                P.sysex.push_back(d);
            }
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
                std::array<double, 12> &sc = gsscale[ch2];
                size_t a = d[6] - 0x40, nbody = d.size() - 8;      // (the values, without the checksum)
                for (size_t i = 0; i < nbody && a + i < 12; i++)
                    sc[a + i] = (double)d[7 + i] - 64.0;
                if (!seen_note)
                    P.gs = 1;
                P.sotas[ch2].push_back(std::make_pair(t, sc));
                continue;
            }
            // GS's USE FOR RHYTHM PART (parse_gs_rhythm_part): the channel a
            // drum part (either map) or a melodic one, its program kept
            if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && (d[4] == 0x40 || d[4] == 0x50)
                && (d[5] >> 4) == 1 && d[6] == 0x15) {
                int blk = d[5] & 0x0F;
                int ch2 = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0);
                drums[ch2] = d[7] != 0;
                if (d[7])
                    rmap[ch2] = d[7] - 1;
                if (d[7])
                    bsel[ch2] = 0;              // (_var: a drum part's no variation)
                if (!seen_note)
                    P.gs = 1;
                continue;
            }
            // THE GS SYSTEM EFFECTS and EQ (gs_setup): read by the first note, after it nothing
            if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12
                && ((d[4] == 0x40 && (d[5] == 0x01 || d[5] == 0x02))
                    || ((d[4] == 0x40 || d[4] == 0x50) && (d[5] >> 4) == 4 && d[6] == 0x20))) {
                if (!seen_note) {
                    P.gs = 1;
                    int a = d[6], v = d[7];
                    if (d[4] == 0x40 && d[5] == 0x01) {
                        std::map<int, int> *g = a >= 0x38 && a <= 0x40 ? &P.gs_ch
                                                : a >= 0x50 && a <= 0x5A ? &P.gs_dl
                                                : a == 0x30 || (a >= 0x33 && a <= 0x35) ? &P.gs_rv : nullptr;
                        if (g && (a == 0x38 || a == 0x50 || a == 0x30))
                            g->clear();         // (a macro sets them all)
                        if (g)
                            (*g)[a] = v;
                    } else if (d[4] == 0x40 && d[5] == 0x02) {
                        if (a <= 3)
                            P.gs_eq[a] = v;
                    } else {
                        int blk = d[5] & 0x0F;
                        P.gs_sw[(blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0)] = v != 0;
                    }
                }
                continue;
            }
            // THE CONTROLLER MATRIX's (ctrlmatrix.parse): a GS part's 2p aa
            // (its source row, its destination), GM2's 09 0s cells
            if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && (d[4] == 0x40 || d[4] == 0x50)
                && (d[5] >> 4) == 2) {
                int blk = d[5] & 0x0F, row = d[6] >> 4, col = d[6] & 0x0F, v = d[7];
                int ch2 = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0);
                if (row <= 5 && col <= 10) {
                    double dep = col == 0 ? (double)std::max(-24, std::min(24, v - 0x40))
                                 : col == 1 ? (v - 0x40) * 9600.0 / 64.0
                                 : col == 2 ? (v > 0x40 ? (v - 0x40) / 63.0 : (v - 0x40) / 64.0)
                                 : (col == 3 || col == 7) ? (v - 0x40) * 10.0 / 64.0
                                 : (col == 4 || col == 8) ? v * 600.0 / 127.0
                                 : (col == 5 || col == 9) ? v * 2400.0 / 127.0
                                 : v / 127.0;
                    auto mi = cmx.find(ch2);
                    if (mi == cmx.end()) {
                        mi = cmx.emplace(ch2, Cmx()).first;
                        mi->second.reset();
                    }
                    mi->second.set(row, col, dep);
                    cmx_upd(t, ch2);
                    if (!seen_note)
                        P.gs = 1;
                    continue;
                }
            }
            if (d.size() >= 6 && d[0] == 0x7F && d[2] == 0x09 && d[3] >= 1 && d[3] <= 3) {
                static const int GM2D[6] = {0, 1, 2, 4, 5, 6};
                int ch2 = d[4] & 0x0F, src = d[3] == 1 ? 2 : d[3] == 2 ? 3 : -1;
                size_t i = 5;
                if (d[3] == 3 && d.size() >= 7) {
                    src = 100 + d[5];
                    i = 6;
                }
                bool any = false;
                if (src >= 0)
                    for (; i + 1 < d.size(); i += 2) {
                        int pp = d[i], rr = d[i + 1];
                        if (pp >= 6)
                            continue;
                        double dep = pp == 0 ? (double)std::max(-24, std::min(24, rr - 0x40))
                                     : pp == 1 ? -9600.0 + rr * (9600.0 + 9450.0) / 127.0
                                     : pp == 2 ? rr / 64.0 - 1.0
                                     : pp == 3 ? rr * 600.0 / 127.0
                                     : pp == 4 ? rr * 2400.0 / 127.0
                                     : rr / 127.0;
                        auto mi = cmx.find(ch2);
                        if (mi == cmx.end()) {
                            mi = cmx.emplace(ch2, Cmx()).first;
                            mi->second.reset();
                        }
                        mi->second.set(src, GM2D[pp], dep);
                        any = true;
                    }
                if (any) {
                    cmx_upd(t, ch2);
                    continue;
                }
            }
            // MASTER PAN (40 00 06): read -- live offsets every part's pan by it
            // (live._gs_rx_part); a file render does not yet, as Python's
            if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && d[4] == 0x40 && d[5] == 0x00
                && d[6] == 0x06) {
                if (!seen_note)
                    P.gs = 1;
                continue;
            }
            // THE SOUND CANVAS'S DISPLAY (model 45H): kept for the render's
            // text, and nothing else -- Python reads no sound in it either
            if (d.size() >= 4 && d[0] == 0x41 && d[2] == 0x45 && d[3] == 0x12) {
                P.disp.push_back(Parsed::Disp{t, d});
                continue;
            }
            // THE INSERTION EFFECT (gsefx.parse: 40 03 aa, a part's 4p 22),
            // its timeline kept whole -- what each note's onset finds
            if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12) {
                int k = -1, a = 0, b = 0;
                if (d[4] == 0x40 && d[5] == 0x03) {
                    int ad = d[6];
                    if (ad == 0x00 && d.size() >= 9)
                        k = 1, a = d[7], b = d[8];
                    else if (ad >= 0x03 && ad <= 0x16)
                        k = 2, a = ad - 0x02, b = d[7];
                    else if (ad >= 0x17 && ad <= 0x19)
                        k = 3, a = ad, b = d[7];
                    else if (ad >= 0x1B && ad <= 0x1E)
                        k = 4, a = ad, b = d[7];
                    if (k < 0)
                        continue;           // (an address gsefx.parse does not read: nothing, as Python's)
                } else if ((d[4] == 0x40 || d[4] == 0x50) && (d[5] >> 4) == 4 && d[6] == 0x22) {
                    int blk = d[5] & 0x0F;
                    k = 5, a = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0), b = d[7] != 0;
                }
                if (k >= 0) {
                    if (!seen_note)
                        P.gs = 1;
                    P.efx.push_back(Parsed::Efx{t, k, a, b});
                    P.events.push_back(LiveEv{t, 6, -1, (int)P.sysex.size(), 0});     // (the live part's too)
                    P.sysex.push_back(d);
                    if (k == 4 && (a == 0x1B || a == 0x1D))
                        efx_src[a == 0x1D] = b;
                    else if (k == 5 && b)
                        efx_on.insert(a);
                    else if (k == 5)
                        efx_on.erase(a);
                    continue;
                }
            }
            if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12) {
                const bool pblk = (d[4] == 0x40 || d[4] == 0x50) && ((d[5] >> 4) == 1 || (d[5] >> 4) == 2
                                                                   || (d[5] >> 4) == 4);
                const int blk = d[5] & 0x0F;
                const int pc = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0);
                // A PART's VELOCITY SENSE and KEY RANGE (1A, 1B, 1D, 1E)
                if (pblk && (d[5] >> 4) == 1 && d.size() >= 9
                    && (d[6] == 0x1A || d[6] == 0x1B || d[6] == 0x1D || d[6] == 0x1E)) {
                    auto it = gsstate.find(pc);
                    if (it == gsstate.end())
                        it = gsstate.emplace(pc, std::array<int, 4>{64, 64, 0, 127}).first;
                    it->second[d[6] == 0x1A ? 0 : d[6] == 0x1B ? 1 : d[6] == 0x1D ? 2 : 3] = d[7];
                    if (!seen_note)
                        P.gs = 1;
                    continue;
                }
                // ...its TONE MAP-0 NUMBER (4p 01, a map 1-4)
                if (pblk && (d[5] >> 4) == 4 && d[6] == 0x01 && d[7] >= 1 && d[7] <= 4) {
                    map0[pc] = d[7];
                    continue;
                }
                // ...the controller matrix's CC1 and CC2 numbers (1p 1F/20)
                if (pblk && (d[5] >> 4) == 1 && (d[6] == 0x1F || d[6] == 0x20)) {
                    auto mi = cmx.find(pc);
                    if (mi == cmx.end()) {
                        mi = cmx.emplace(pc, Cmx()).first;
                        mi->second.reset();
                    }
                    (d[6] == 0x1F ? mi->second.cc1 : mi->second.cc2) = d[7];
                    cmx_upd(t, pc);
                    continue;
                }
                // A USER DRUM SET's key (21 dp kk vv: set p, its parameter d):
                // another set's key and its own settings (user_drum), the file's whole
                if (d[4] == 0x21 && (d[5] >> 4) <= 1 && (d[5] & 0x0F) >= 1 && (d[5] & 0x0F) <= 12) {
                    P.uset[std::make_pair(d[5] >> 4, (int)d[6])][d[5] & 0x0F] = d[7];
                    continue;
                }
                // A DRUM MAP's SETUP (41/51 mp kk vv): every channel of its port
                // playing the map, as its drum instruments' edits
                if ((d[4] == 0x41 || d[4] == 0x51) && (d[5] >> 4) <= 1) {
                    // (note, level, group, pan, sends, the receive switches: the
                    // song's dst parameters -- 0 pitch, 1 level, 2 pan, 3-5 the sends,
                    // 6 rx note on, 7 the exclusive group, 8 rx note off)
                    static const int PAR[10] = {-1, 0, 1, 7, 2, 3, 4, 8, 6, 5};
                    int pn = d[5] & 0x0F, par = pn < 10 ? PAR[pn] : -1;
                    if (par >= 0) {
                        int key = d[6], v = par == 0 ? d[7] - d[6] : d[7], mp2 = d[5] >> 4;
                        int base = d[4] == 0x51 ? 16 : 0;
                        for (int c = base; c < base + 16; c++) {
                            auto di = drums.find(c);
                            bool isd = di != drums.end() ? di->second != 0 : (c % 16 == PERCUSSION_CHANNEL);
                            if (isd && (rmap.count(c) ? rmap[c] : 0) == mp2)
                                P.dedit.push_back(Parsed::DEdit{c, t, key, par, v});
                        }
                    }
                    continue;
                }
                // ...and a part parameter: its messages follow it (gs_part_msgs);
                // any other the loop leaves, as Python's
                if (pblk) {
                    if (!seen_note)
                        P.gs = 1;
                    continue;
                }
            }
            if (cm64 && d.size() >= 3 && d[0] == 0x41 && d[2] == 0x16)
                continue;               // (the CM-64's own -- the MT-32 family's, 16H: changes nothing, as on a Sound Canvas)
            if (!(lvl || gs))
                return -4;              // any other exclusive: not a GM file's
            if (gs && !seen_note) {     // (a GS reset: the setup back to none)
                P.gs_rv.clear(); P.gs_ch.clear(); P.gs_dl.clear(); P.gs_eq.clear(); P.gs_sw.clear();
            }
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
            gsstate.clear();
            map0.clear();
            rmap.clear();
            P.pitch.push_back(PitchEv{-1, t, seq, 9, 0.0});
            P.snd.push_back(CCEv{-1, t, -1, 0});
            P.dedit.push_back(Parsed::DEdit{-1, t, -1, -1, 0});     // (the drum instruments' own: reset)
            P.efx.push_back(Parsed::Efx{t, 0, 0, 0});              // (the insertion effect's: reset)
            efx_src[0] = efx_src[1] = 0;
            efx_cvv.clear();
            efx_on.clear();
            cat_now.clear(); bend_now.clear(); pat_now.clear();
            for (auto &mc : cmx)
                mc.second.reset();
            for (auto &mc : cmx)
                cmx_upd(t, mc.first);
            rfmsb.clear(); rrange.clear(); rmod.clear(); rfine.clear(); rcoarse.clear(); rtp.clear(); rtb.clear();
            continue;
        }
        int ch = (m.status & 0x0F) + 16 * m.port, kind = m.status & 0xF0;
        auto is_drums = [&](int c) {
            if (mpe && mpe.is_member(c))        // (a member is never a drum channel)
                return false;
            auto it = drums.find(c);
            return it != drums.end() ? it->second != 0 : (c % 16 == PERCUSSION_CHANNEL);
        };
        if (kind == 0xC0) {
            // THE BANK (tonelib.resolve_patch): ignored after GM 1's System On;
            // MSB 120 a drum set, 121 GM 2's tone by its LSB; a drum channel
            // stays one; else GS's variation, read in the map CC32 names
            // (or, at 0, TUNING_MAP's)
            int msb = bmsb.count(ch) ? bmsb[ch] : 0, lsb = blsb.count(ch) ? blsb[ch] : 0;
            auto m0 = map0.find(ch);
            int mp = lsb ? lsb : m0 != map0.end() ? m0->second : default_map, dr = is_drums(ch), bs = 0;
            if (!rxbank)
                ;
            else if (msb == 120)
                dr = 1;
            else if (msb == 121) {
                dr = 0;
                bs = lsb ? 1 + 640 + lsb : 0;
            } else if (!dr)
                bs = msb ? 1 + 128 * (mp >= 1 && mp <= 4 ? mp : 0) + msb : 0;
            int dprog = m.d0;
            if (dr && msb != 120 && mp) {
                // a drum set read in the part's map (kit_in_map): the map's own
                // set where it has one -- 128 m + p, else (maps 1, 2) 384 + p --
                // its drum program 128 + its index (the export's MKIT), else the program
                if (!g_map_kits_set)
                    return -5;
                int own = -1;
                for (size_t j = 0; j < g_map_kits.size() && own < 0; j++)
                    if (g_map_kits[j] == 128 * mp + m.d0)
                        own = (int)j;
                for (size_t j = 0; j < g_map_kits.size() && own < 0; j++)
                    if ((mp == 1 || mp == 2) && g_map_kits[j] == 3 * 128 + m.d0)
                        own = (int)j;
                if (own >= 0 && !g_map_kits_play)
                    return -5;
                if (own >= 0)
                    dprog = 128 + own;
            }
            drums[ch] = dr;
            bsel[ch] = bs;
            if (dr)         // "When the Drum Set is changed, DRUM SETUP PARAMETER values will all be initialized"
                P.dedit.push_back(Parsed::DEdit{ch, t, -1, -1, 0});
            P.banked |= rxbank && (msb || lsb);     // (a bank, or a map: live's not yet)
            prog[ch] = dr ? dprog : m.d0;
            P.progs.push_back(std::make_pair(ch, m.d0));
            if (!drums[ch]) {
                P.chprogs.push_back(std::make_pair(ch, m.d0));  // (a drum set is no organ's program)
                P.chbsel.push_back(bs);
            }
            if (live_ev)
                P.events.push_back(LiveEv{t, 5, ch, m.d0, 0});
        } else if (kind == 0xB0) {
            int cc = m.d0, v = m.d1;
            P.ccs.push_back(CCEv{ch, t, cc, v});
            if (cc >= 1 && cc <= 95)
                efx_cv(t, ch, cc, v);
            if (live_ev)
                P.events.push_back(LiveEv{t, 2, ch, cc, v});
            if (cc >= 71 && cc <= 78)
                P.snd.push_back(CCEv{ch, t, cc, v});
            if (cc == 0)
                bmsb[ch] = v;
            else if (cc == 32)
                blsb[ch] = v;
            ctrl[ch][cc] = v;
            cmx_upd(t, ch);
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
                P.ats.push_back(CCEv{ch, t, -1, 0});        // (not polytouch: live keeps it)
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
                    for (int q = 0; q < 6; q++)
                        if (nt->second.first == DRUM[q] && cc == 6)    // (a drum instrument's own: dedit)
                            P.dedit.push_back(Parsed::DEdit{ch, t, nt->second.second, q, q == 0 ? v - 64 : v});
                    static const int GSN[8][3] = {{1, 0x08, 76}, {1, 0x09, 77}, {1, 0x0A, 78}, {1, 0x20, 74},
                                                  {1, 0x21, 71}, {1, 0x63, 73}, {1, 0x64, 75}, {1, 0x66, 72}};
                    for (auto &g : GSN)
                        if (nt->second == std::make_pair(g[0], g[1]) && cc == 6)
                            P.snd.push_back(CCEv{ch, t, g[2], v});
                    continue;
                }
                if (it->second == std::make_pair(0, 6)) {
                    // THE MPE CONFIGURATION MESSAGE (2.2.1): the zones; a
                    // reset on every channel whose zone changed (2.2.3); the
                    // bend ranges, 2 on the manager and 48 on members (2.2.5)
                    std::set<int> chg;
                    if (cc == 6 && mpe.mcm(ch, v, chg)) {
                        P.mpe.push_back(std::make_pair(t, mpe.channels()));
                        for (int x : chg) {
                            Msg y{0, 0xB0 | (x & 15), 121, 0, 0, {}};
                            inj.push_back(y);
                        }
                        if (mpe.zone_of(ch)) {
                            rrange[ch] = MPE_MANAGER_BEND;
                            P.pitch.push_back(PitchEv{ch, t, seq, 1, rrange[ch]});
                            for (int m2 : mpe.members(ch)) {
                                rrange[m2] = MPE_MEMBER_BEND;
                                P.pitch.push_back(PitchEv{m2, t, seq, 1, rrange[m2]});
                            }
                        }
                    }
                    continue;
                }
                // DATA ENTRY into the RPN selected (tonelib's rpn_*)
                std::pair<int, int> sel = it->second;
                if (sel == std::make_pair(0, 0)) {
                    double cur = getd(rrange, ch, BEND_RANGE_SEMITONES);
                    rrange[ch] = cc == 6 ? (double)v : (double)(long)cur + v / 100.0;
                    P.pitch.push_back(PitchEv{ch, t, seq, 1, rrange[ch]});
                    if (mpe && mpe.is_member(ch))           // (one range for the zone's members, 2.2.5)
                        for (int m2 : mpe.members(ch))
                            if (m2 != ch) {
                                rrange[m2] = rrange[ch];
                                P.pitch.push_back(PitchEv{m2, t, seq, 1, rrange[ch]});
                            }
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
            if (live_ev)
                P.events.push_back(LiveEv{t, 4, ch, ((m.d1 << 7) | m.d0) - 8192, 0});
            efx_cv(t, ch, 0x61, ((m.d1 << 7) | m.d0) >> 7);
            bend_now[ch] = ((m.d1 << 7) | m.d0) - 8192;
            cmx_upd(t, ch);
        } else if (kind == 0x90 && m.d1 > 0) {
            seen_note = true;
            if (live_ev)
                P.events.push_back(LiveEv{t, 0, ch, m.d0, m.d1});
            auto &c = ctrl[ch];
            Note n;
            n.ch = ch; n.note = m.d0; n.on = t; n.off = 0.0; n.vel = m.d1;
            {
                // A GS PART'S KEY RANGE (outside it the part does not sound) and
                // its VELOCITY SENSE: depth scales the velocity (64 as is), offset moves it
                auto gi = gsstate.find(ch);
                if (gi != gsstate.end()) {
                    const auto &g = gi->second;
                    if (!(g[2] <= m.d0 && m.d0 <= g[3]))
                        continue;
                    if (g[0] != 64 || g[1] != 64)
                        n.vel = std::max(1, std::min(127, (int)nearbyint(m.d1 * g[0] / 64.0 + g[1] - 64)));
                }
            }
            n.v7 = (c.count(7) ? c[7] : GM_DEFAULT_VOLUME) / 127.0;
            n.v11 = (c.count(11) ? c[11] : GM_DEFAULT_EXPRESSION) / 127.0;
            {
                // (the controller matrix's amplitude, where a matrix routes
                // one: in the expression, which chan_vol squares -- cv)
                auto li = cmx_last.find(ch);
                if (li != cmx_last.end() && li->second[0] != 1.0)
                    n.v11 = n.v11 * pow(li->second[0], 0.5);
            }
            n.pan = ((c.count(10) ? c[10] : GM_DEFAULT_PAN) - 64) / 63.0;
            // (a member plays its manager's program: blockrender's _cur_prog)
            const int pch = mpe && mpe.is_member(ch) ? mpe.manager_of(ch) : ch;
            n.prog = prog.count(pch) ? prog[pch] : 0;
            n.drum = is_drums(pch);
            n.bsel = n.drum || !bsel.count(pch) ? 0 : bsel[pch];
            if (pch != ch && !n.drum
                && std::find(P.chprogs.begin(), P.chprogs.end(), std::make_pair(ch, n.prog)) == P.chprogs.end()) {
                P.chprogs.push_back(std::make_pair(ch, n.prog));
                P.chbsel.push_back(n.bsel);
            }
            P.banked |= n.bsel != 0;
            on[std::make_pair(ch, m.d0)].push_back(n);
        } else if (kind == 0x80 || kind == 0x90) {
            if (live_ev)
                P.events.push_back(LiveEv{t, 1, ch, m.d0, 0});
            auto &q = on[std::make_pair(ch, m.d0)];
            if (!q.empty()) {
                Note n = q.front();
                q.erase(q.begin());
                n.off = t;
                P.notes.push_back(n);
            }
        }
        else if (kind == 0xD0) {
            P.ats.push_back(CCEv{ch, t, -1, m.d0});     // the channel's aftertouch (ats)
            if (live_ev)
                P.events.push_back(LiveEv{t, 3, ch, m.d0, 0});      // (the live part's too)
            efx_cv(t, ch, 0x60, m.d0);
            cat_now[ch] = m.d0;
            cmx_upd(t, ch);
        }
        else if (kind == 0xA0) {
            P.pts.push_back(CCEv{ch, t, m.d0, m.d1});   // a key's polytouch (pts)
            if (live_ev)
                P.events.push_back(LiveEv{t, 7, ch, m.d0, m.d1});   // (the live part's too: a siren's air)
            pat_now[ch][m.d0] = m.d1;
            cmx_upd(t, ch);
        }
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
// THE DRUM INSTRUMENTS' OWN (dedit): edit i's channel, key, parameter, value
// (iv) and time; the count
int nv_midi_n_dedit(void *p) { return (int)((nv::Parsed *)p)->dedit.size(); }
// USER DRUM SET s's key (0 or 1: GS's sets 65 and 66, programs 64 and 65):
// its parameters by number (iv[1..12]) and a bit a parameter set, 0 none
// MPE: channel ch's manager at time t (blockrender's _manager over the
// zones' history, mpe_ev): -1 outside MPE; ch itself where it manages
int nv_midi_mpe_manager(void *p, int ch, double t)
{
    const nv::Parsed &P = *(const nv::Parsed *)p;
    const std::map<int, std::pair<int, int>> *z = nullptr;
    for (const auto &e : P.mpe) {
        if (e.first <= t + 1e-9)
            z = &e.second;
        else
            break;
    }
    if (!z)
        return -1;
    auto it = z->find(ch);
    if (it == z->end())
        return -1;
    return 16 * it->second.first + (it->second.second == 0 ? 0 : 15);
}

// whether the file has MPE at all (an MCM that made a zone)
int nv_midi_has_mpe(void *p) { return ((const nv::Parsed *)p)->mpe.empty() ? 0 : 1; }

int nv_midi_user_drum(void *p, int set, int key, int *iv)
{
    const auto &u = ((nv::Parsed *)p)->uset;
    auto it = u.find(std::make_pair(set, key));
    if (it == u.end())
        return 0;
    int m = 0;
    for (const auto &kv : it->second) {
        m |= 1 << kv.first;
        iv[kv.first] = kv.second;
    }
    return m;
}
void nv_midi_dedit(void *p, int i, int *iv, double *t)
{
    const auto &e = ((nv::Parsed *)p)->dedit[i];
    iv[0] = e.ch; iv[1] = e.key; iv[2] = e.par; iv[3] = e.v;
    *t = e.t;
}

// THE CONTROLLER MATRIX's sums as they move: event i's kind and channel (iv),
// time and value (dv); the count
int nv_midi_n_cmx(void *p) { return (int)((nv::Parsed *)p)->cmx.size(); }
void nv_midi_cmx(void *p, int i, int *iv, double *dv)
{
    const auto &e = ((nv::Parsed *)p)->cmx[i];
    iv[0] = e.kind; iv[1] = e.ch;
    dv[0] = e.t; dv[1] = e.v;
}

// THE INSERTION EFFECT's timeline: event i's kind, a, b (iv) and time; the count
int nv_midi_n_efx(void *p) { return (int)((nv::Parsed *)p)->efx.size(); }
void nv_midi_efx(void *p, int i, int *iv, double *t)
{
    const auto &e = ((nv::Parsed *)p)->efx[i];
    iv[0] = e.kind; iv[1] = e.a; iv[2] = e.b;
    *t = e.t;
}

// THE MAPS' OWN DRUM SETS (percussion_map.KITS past 127), for kit_in_map:
// until they are given, any drum set read in a map is refused
// ...and whether the export carries their tables (MKIT): played, else refused
void nv_midi_map_kits_play(int on) { nv::g_map_kits_play = on != 0; }

void nv_midi_map_kits(const int *ids, int n)
{
    nv::g_map_kits.assign(ids, ids + n);
    nv::g_map_kits_set = true;
}

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

// the Sound Canvas's display messages (gsdisplay): how many, and the i-th --
// its bytes (*n of them) and its time, s
int nv_midi_display_n(void *p) { return (int)((nv::Parsed *)p)->disp.size(); }
const uint8_t *nv_midi_display(void *p, int i, int *n, double *t)
{
    const auto &v = ((nv::Parsed *)p)->disp[i];
    *n = (int)v.d.size();
    *t = v.t;
    return v.d.data();
}
int nv_midi_gs(void *p) { return ((nv::Parsed *)p)->gs; }

// THE GS SETUP by the first note (gs_setup): which 0 the reverb's, 1 the
// chorus's, 2 the delay's (key their 40 01 address), 3 the EQ's (0-3), 4 a
// part's EQ switch (key its channel) -- 1 and *v where the file set it
int nv_midi_gs_setup(void *p, int which, int key, int *v)
{
    const nv::Parsed *P = (nv::Parsed *)p;
    const std::map<int, int> *m[5] = {&P->gs_rv, &P->gs_ch, &P->gs_dl, &P->gs_eq, &P->gs_sw};
    if (which < 0 || which > 4)
        return 0;
    auto it = m[which]->find(key);
    if (it == m[which]->end())
        return 0;
    *v = it->second;
    return 1;
}
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

// key's polytouch (blockrender's pts[(ch, key)]), as nv_midi_ats
int nv_midi_pts(void *p, int ch, int key, double *t, int *v, int cap)
{
    int n = 0;
    for (const auto &e : ((nv::Parsed *)p)->pts)
        if (e.ch == ch && e.cc == key) {
            if (t && n < cap) {
                t[n] = e.t;
                v[n] = e.v;
            }
            n++;
        }
    return n;
}

// channel ch's aftertouch (blockrender's ats[ch]): its times and values in
// message order, n of them into t and v (NULL: count)
int nv_midi_ats(void *p, int ch, double *t, int *v, int cap)
{
    int n = 0;
    for (const auto &e : ((nv::Parsed *)p)->ats)
        if (e.ch == ch) {
            if (t && n < cap) {
                t[n] = e.t;
                v[n] = e.v;
            }
            n++;
        }
    return n;
}
// channel ch's controller cc (blockrender's ccs[ch], that controller's), as nv_midi_ats
int nv_midi_ccs(void *p, int ch, int cc, double *t, int *v, int cap)
{
    int n = 0;
    for (const auto &e : ((nv::Parsed *)p)->ccs)
        if (e.ch == ch && e.cc == cc) {
            if (t && n < cap) {
                t[n] = e.t;
                v[n] = e.v;
            }
            n++;
        }
    return n;
}
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
                     trim[(n.drum ? 128 : 0) + (n.drum && n.prog > 127 ? 0 : n.prog)], n.prog, n.drum);
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
