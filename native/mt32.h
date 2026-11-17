// A REAL MT-32 / CM-64 (TUNING_MT32=mt32 or cm64): what the unit itself does
// with a file written for it, beyond what a Sound Canvas does. A Sound
// Canvas in its CM-64 map ignores the family's exclusives ("this unit's
// settings will not change", SC-88Pro OM p.115) and plays channel 1 as a
// piano; the unit honours them, and listens where its parts are set to.
// From Roland's MT-32 MIDI Implementation (v1.02 1988, v2.00) and the
// CM-32L's (1989): this pass reads them, in file order, and says each as a
// message our engine already reads -- before the Init CM-64 pass, which
// still sets the parts (the MT-32 set, the CM-64/32L kit, the CM-32P) and
// mirrors every pan.
//
//   CHANNELS   parts 1-8 on channels 2-9, the rhythm part on 10 (System
//              area 10 00 0D-15 moves them; 16 OFF; a part moved gets Reset
//              All Controllers and All Notes Off, the CM-32L's rule). Each
//              part plays on our channel for it: part n on n+1, rhythm on
//              10 -- channel 1 silent. A CM-64's CM-32P parts on 11-16 as
//              they come; an MT-32 has none, so nothing plays there.
//   PATCHES    a program change looks up the Patch Memory (05 00 00): its
//              timbre (group A/B: the MT-32 set's tone; Memory: a custom
//              timbre, below), key shift (RPN 2), fine tune (RPN 1), bend
//              range (RPN 0), reverb switch (CC91 0/64). Patch Temp (03 00
//              00) sets a part's the same way, and its OUTPUT LEVEL (CC7)
//              and PANPOT (0-14, 14 left, as the unit's CC10 127 is).
//   TIMBRES    a custom LA timbre (Timbre Temp 04 / 02, Timbre Memory 08)
//              plays OUR VOICE NEAREST ITS NAME (its 10 characters): an
//              MT-32 set name it equals, else the orchestral names mt32mux
//              reads (partmux.h). No LA synthesis, no Roland sound fitted.
//   RHYTHM     Rhythm Setup (03 01 10, 4 bytes a key): each key's level,
//              pan and reverb switch as GS drum NRPNs (1A, 1C, 1D). A key
//              given another rhythm timbre is NOT followed (Roland's
//              documents do not give the timbres' order) -- reported.
//   SYSTEM     master volume and master tune (432.1-457.6 Hz) as the
//              universal master messages; reverb mode / time / level as
//              GS's reverb (Room, Hall, Plate, Tap delay -> Room 1, Hall 1,
//              Plate, Delay: by intent). Partial reserve: our voices are
//              not rationed. 7F: all parameters back to power-on.
//   NOTES      melodic keys outside 12-108 folded by octaves (v2.00);
//              rhythm keys outside 24-87 (MT-32) / 24-108 (CM-32L) dropped;
//              aftertouch not received; CC 124-127 all notes off; only the
//              unit's controllers received (1, 6/38, 7, 10, 11, 64,
//              100/101, 121, 123); the rhythm part takes no pan and no
//              program change.
//
// Roland's documents do not give the factory per-patch settings beyond the
// timbre, nor the reverb defaults: patches start at key shift 0, fine tune
// 0, bend range 12 (Init CM-64's), reverb on; reverb as the init leaves it.
#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace mt32 {

// The MT-32's 128 tones (patch_map.MT32_SET's names, program order: group
// A 1-64, group B 1-64): GS bank 127
static const char *const SET[128] = {
    "Acou Piano 1", "Acou Piano 2", "Acou Piano 3", "Elec Piano 1", "Elec Piano 2", "Elec Piano 3", "Elec Piano 4",
    "Honkytonk", "Elec Org 1", "Elec Org 2", "Elec Org 3", "Elec Org 4", "Pipe Org 1", "Pipe Org 2", "Pipe Org 3",
    "Accordion", "Harpsi 1", "Harpsi 2", "Harpsi 3", "Clavi 1", "Clavi 2", "Clavi 3", "Celesta 1", "Celesta 2",
    "Syn Brass 1", "Syn Brass 2", "Syn Brass 3", "Syn Brass 4", "Syn Bass 1", "Syn Bass 2", "Syn Bass 3",
    "Syn Bass 4", "Fantasy", "Harmo Pan", "Chorale", "Glasses", "Soundtrack", "Atmosphere", "Warm Bell",
    "Funny Vox", "Echo Bell", "Ice Rain", "Oboe 2001", "Echo Pan", "Doctor Solo", "School Daze", "Bellsinger",
    "Square Wave", "Str Sect 1", "Str Sect 2", "Str Sect 3", "Pizzicato", "Violin 1", "Violin 2", "Cello 1",
    "Cello 2", "Contrabass", "Harp 1", "Harp 2", "Guitar 1", "Guitar 2", "Elec Gtr 1", "Elec Gtr 2", "Sitar",
    "Acou Bass 1", "Acou Bass 2", "Elec Bass 1", "Elec Bass 2", "Slap Bass 1", "Slap Bass 2", "Fretless 1",
    "Fretless 2", "Flute 1", "Flute 2", "Piccolo 1", "Piccolo 2", "Recorder", "Pan Pipes", "Sax 1", "Sax 2",
    "Sax 3", "Sax 4", "Clarinet 1", "Clarinet 2", "Oboe", "Engl Horn", "Bassoon", "Harmonica", "Trumpet 1",
    "Trumpet 2", "Trombone 1", "Trombone 2", "Fr Horn 1", "Fr Horn 2", "Tuba", "Brs Sect 1", "Brs Sect 2",
    "Vibe 1", "Vibe 2", "Syn Mallet", "Windbell", "Glock", "Tube Bell", "Xylophone", "Marimba", "Koto", "Sho",
    "Shakuhachi", "Whistle 1", "Whistle 2", "Bottleblow", "Breathpipe", "Timpani", "Melodic Tom", "Deep Snare",
    "Elec Perc 1", "Elec Perc 2", "Taiko", "Taiko Rim", "Cymbal", "Castanets", "Triangle", "Orche Hit",
    "Telephone", "Bird Tweet", "One Note Jam", "Water Bell", "Jungle Tune",
};

// the parts' power-on tones (Slap Bass 1, Str Sect 1, Brs Sect 1, Sax 1, Ice
// Rain, Elec Piano 1, Bottle Blow, Orche Hit: Init CM-64's parts 2-9)
static const int POWER_ON[8] = {68, 48, 95, 78, 41, 3, 110, 122};

// a timbre's name as shown (its 10 characters' padding off)
static std::string shown(const std::string &s)
{
    const size_t b = s.find_last_not_of(' ');
    return b == std::string::npos ? std::string() : s.substr(0, b + 1);
}

static std::string norm(const std::string &s)
{
    std::string o;
    for (char c : s)
        if (!isspace((unsigned char)c))
            o += (char)tolower((unsigned char)c);
    return o;
}

// OUR VOICE NEAREST A TIMBRE's NAME: (bank, program, how), bank -1 none
static void by_name(const std::string &nm, int &bank, int &prog, std::string &how)
{
    bank = -1;
    const std::string n = norm(nm);
    if (n.empty())
        return;
    for (int i = 0; i < 128; i++)
        if (norm(SET[i]) == n) {
            bank = 127;
            prog = i;
            how = std::string(SET[i]) + " (the MT-32 set)";
            return;
        }
    std::vector<std::pair<std::string, int>> keys;
    for (const auto &k : partmux::NAME_TO_GM)
        keys.push_back({k.first, k.second});
    std::stable_sort(keys.begin(), keys.end(), [](const auto &a, const auto &b) { return a.first.size() > b.first.size(); });
    std::string low;
    for (char c : nm)
        low += (char)tolower((unsigned char)c);
    for (const auto &k : keys)
        if (low.find(k.first) != std::string::npos) {
            bank = 0;
            prog = k.second;
            how = "GM " + std::to_string(k.second + 1) + " (by its name: '" + k.first + "')";
            return;
        }
}

struct State {
    int chan[9];                        // each part's channel (0-15; 16 OFF): parts 1-8, rhythm
    uint8_t pmem[128][8];               // the Patch Memory
    uint8_t ptemp[8][16];               // each part's Patch Temp
    std::string tmem[64], ttemp[8];     // the timbres' names: memory, each part's temp
    int rhythm_level = 100;
    int sys[0x17];
    void reset()
    {
        for (int p = 0; p < 8; p++)
            chan[p] = p + 1;
        chan[8] = 9;
        for (int n = 0; n < 128; n++) {
            const uint8_t d[8] = {(uint8_t)(n / 64), (uint8_t)(n % 64), 24, 50, 12, 0, 1, 0};
            std::copy(d, d + 8, pmem[n]);
        }
        for (int p = 0; p < 8; p++) {
            std::fill(ptemp[p], ptemp[p] + 16, 0);
            std::copy(pmem[POWER_ON[p]], pmem[POWER_ON[p]] + 8, ptemp[p]);
            ptemp[p][8] = 100;
            ptemp[p][9] = 7;
            ttemp[p].clear();
        }
        for (auto &t : tmem)
            t.clear();
        std::fill(sys, sys + 0x17, -1);
    }
};

struct Report {
    std::vector<std::string> lines;
    std::set<std::string> seen;
    void say(const std::string &s)
    {
        if (seen.insert(s).second)
            lines.push_back(s);
    }
};

// THE UNIT, a message at a time (feed, in order; finish at the end): a
// file's messages (absolute ticks) or live input as it comes -- each one
// heard as the unit hears it, said as our messages into OUT. No look-ahead:
// the same state machine serves the file reader (apply) and live input
// (the module mode)
template <class MsgT>
struct Unit {
    State S;
    bool cm64 = false;
    int n_excl = 0;
    Report R;
    std::vector<MsgT> *out = nullptr;
    long long now = 0;
    // per part, what was last sent (so a patch re-selected sends only what moved)
    int sent_ks[9], sent_ft[9], sent_bend[9], sent_rev[9];
    std::map<int, long> dropped;        // channel -> notes no part received
    std::set<std::pair<int, int>> held; // (our channel, key) sounding: a moved part's let go by name
    long rhythm_out = 0;
    int rhythm_hi = 87;
    explicit Unit(bool cm) : cm64(cm)
    {
        S.reset();
        std::fill(sent_ks, sent_ks + 9, 24);
        std::fill(sent_ft, sent_ft + 9, 50);
        std::fill(sent_bend, sent_bend + 9, 12);
        std::fill(sent_rev, sent_rev + 9, 1);
        rhythm_hi = cm64 ? 108 : 87;
    }
    void emit(int ch, int st, int a, int b) { out->push_back(MsgT{now, st | ch, a, b, 0, {}}); }
    void ex(std::vector<uint8_t> d) { out->push_back(MsgT{now, 0xF0, 0, 0, 0, d}); }
    void gs(int a1, int a2, int a3, int v)
    {
        const int cs = (128 - (a1 + a2 + a3 + v) % 128) % 128;
        ex({0x41, 0x10, 0x42, 0x12, (uint8_t)a1, (uint8_t)a2, (uint8_t)a3, (uint8_t)v, (uint8_t)cs});
    }
    static int outch(int p) { return p < 8 ? p + 1 : 9; }
    void rpn(int ch, int lsb, int msb, int l)
    {
        emit(ch, 0xB0, 101, 0); emit(ch, 0xB0, 100, lsb); emit(ch, 0xB0, 6, msb); emit(ch, 0xB0, 38, l);
        emit(ch, 0xB0, 101, 127); emit(ch, 0xB0, 100, 127);
    }
    // A PATCH on part p (group, number, key shift, fine tune, bend, assign, reverb)
    void patch(int p, const uint8_t *d, const std::string &why)
    {
        const int ch = outch(p);
        int bank = -1, prog = 0;
        std::string how;
        if (d[0] <= 1) {
            bank = 127;
            prog = d[0] * 64 + (d[1] & 63);
        } else if (d[0] == 2) {
            const std::string &nm = S.tmem[d[1] & 63];
            by_name(nm, bank, prog, how);
            if (bank < 0)
                R.say("part " + std::to_string(p + 1) + ": custom timbre i" + std::to_string((d[1] & 63) + 1)
                      + (nm.empty() ? "" : " '" + shown(nm) + "'") + " matched no voice: kept the part's tone");
            else
                R.say("part " + std::to_string(p + 1) + ": custom timbre '" + shown(nm) + "' -> " + how);
        } else {
            R.say("part " + std::to_string(p + 1) + ": a rhythm timbre as its patch: not followed");
        }
        if (bank >= 0) {
            emit(ch, 0xB0, 0, bank);
            emit(ch, 0xB0, 32, 1);
            emit(ch, 0xC0, prog, 0);
        }
        const int ks = std::min(48, (int)d[2]), ft = std::min(100, (int)d[3]), bend = std::min(24, (int)d[4]),
                  rev = d[6] ? 1 : 0;
        if (ks != sent_ks[p]) {
            rpn(ch, 2, 64 + ks - 24, 0);
            sent_ks[p] = ks;
        }
        if (ft != sent_ft[p]) {
            const int v = std::max(0, std::min(16383, 8192 + (int)lround((ft - 50) / 100.0 * 8192.0)));
            rpn(ch, 1, v >> 7, v & 127);
            sent_ft[p] = ft;
        }
        if (bend != sent_bend[p]) {
            rpn(ch, 0, bend, 0);
            sent_bend[p] = bend;
        }
        if (rev != sent_rev[p]) {
            emit(ch, 0xB0, 91, rev ? 64 : 0);
            sent_rev[p] = rev;
        }
        (void)why;
    }
    int part_of(int c) const
    {
        for (int p = 0; p < 9; p++)
            if (S.chan[p] == c)
                return p;
        return -1;
    }

    // a DT1's bytes landing in the unit's memory, then what they set
    void dt1(const std::vector<uint8_t> &d)
    {
        const int dev = d[1];
        const long a0 = ((long)d[4] << 14) | (d[5] << 7) | d[6];
        const size_t nb = d.size() - 8;         // (address, data, checksum)
        std::set<int> parts_patch, parts_lvl, parts_pan, parts_timbre, keys;
        bool chans = false, vol = false, tune = false, rev = false, reset = false, rlevel = false;
        for (size_t i = 0; i < nb; i++) {
            const long a = a0 + (long)i;
            const int v = d[7 + i];
            const int hi = (int)(a >> 14), mid = (int)((a >> 7) & 127), lo = (int)(a & 127);
            const long off = a & 0x3FFF;
            (void)mid;
            (void)lo;
            if (hi == 0x10 && off < 0x17) {
                S.sys[off] = v;
                if (off >= 0x0D && off <= 0x15) {
                    const int p = (int)off - 0x0D;
                    if (S.chan[p] != std::min(v, 16)) {
                        if (S.chan[p] < 16) {          // (the part's notes let go, its controllers reset)
                            // (each held note let go by its own note-off: the
                            // file reader pairs notes by their offs, not by
                            // All Notes Off, and its off would never come now)
                            for (auto it = held.begin(); it != held.end();)
                                if (it->first == outch(p)) {
                                    emit(it->first, 0x80, it->second, 0);
                                    it = held.erase(it);
                                } else {
                                    ++it;
                                }
                            emit(outch(p), 0xB0, 121, 0);
                            emit(outch(p), 0xB0, 123, 0);
                        }
                        S.chan[p] = std::min(v, 16);
                        chans = true;
                    }
                }
                vol = vol || off == 0x16;
                tune = tune || off == 0x00;
                rev = rev || (off >= 1 && off <= 3);
            } else if (hi == 0x03 && off < 0x80) {
                const int p = (int)(off >> 4), k = (int)(off & 15);
                S.ptemp[p][k] = (uint8_t)v;
                if (k <= 6)
                    parts_patch.insert(p);
                else if (k == 8)
                    parts_lvl.insert(p);
                else if (k == 9)
                    parts_pan.insert(p);
            } else if (hi == 0x03 && off >= 0x80 && off < 0x90) {
                if (off - 0x80 == 8) {
                    S.rhythm_level = v;
                    rlevel = true;
                }
            } else if (hi == 0x03 && off >= 0x90) {
                const int key = 24 + (int)((off - 0x90) / 4), k = (int)((off - 0x90) % 4);
                if (key <= 108) {
                    keys.insert(key * 4 + k);
                }
            } else if (hi == 0x04 || hi == 0x02) {
                // Timbre Temp: 04 by part (246 bytes each), 02 the part on the device's channel
                int p = -1;
                long o = off;
                if (hi == 0x04) {
                    p = (int)(off / 246);
                    o = off % 246;
                } else {
                    const int q = part_of(dev & 15);
                    p = q >= 0 && q < 8 ? q : -1;
                }
                if (p >= 0 && p < 8 && o < 10) {
                    if (S.ttemp[p].size() < 10)
                        S.ttemp[p].resize(10, ' ');
                    S.ttemp[p][(size_t)o] = (char)v;
                    parts_timbre.insert(p);
                }
            } else if (hi == 0x05) {
                const long n = off / 8;
                if (n < 128)
                    S.pmem[n][off % 8] = (uint8_t)v;
            } else if (hi == 0x08) {
                const long n = off / 256, o = off % 256;
                if (n < 64 && o < 10) {
                    if (S.tmem[n].size() < 10)
                        S.tmem[n].resize(10, ' ');
                    S.tmem[n][(size_t)o] = (char)v;
                }
            } else if (hi == 0x40) {
                // Write Request: a part's temp timbre to memory (00 00 + 2p), its patch (01 00 + 2p)
                if (off < 0x10 && off % 2 == 0 && v < 64)
                    S.tmem[v] = S.ttemp[off / 2];
                else if (off >= 0x80 && off < 0x90 && off % 2 == 0)
                    std::copy(S.ptemp[(off - 0x80) / 2], S.ptemp[(off - 0x80) / 2] + 8, S.pmem[v & 127]);
            } else if (hi == 0x7F) {
                reset = true;
            }
        }
        if (reset) {
            S.reset();
            R.say("all parameters reset (7F): the unit back to power-on");
            for (int p = 0; p < 8; p++)
                patch(p, S.ptemp[p], "reset");
            return;
        }
        for (int p : parts_patch)
            patch(p, S.ptemp[p], "patch temp");
        for (int p : parts_timbre) {
            int bank, prog;
            std::string how;
            by_name(S.ttemp[p], bank, prog, how);
            if (bank >= 0) {
                emit(outch(p), 0xB0, 0, bank);
                emit(outch(p), 0xB0, 32, 1);
                emit(outch(p), 0xC0, prog, 0);
                R.say("part " + std::to_string(p + 1) + ": its own timbre '" + shown(S.ttemp[p]) + "' -> " + how);
            } else {
                R.say("part " + std::to_string(p + 1) + ": its own timbre '" + shown(S.ttemp[p]) + "' matched no voice: kept its tone");
            }
        }
        for (int p : parts_lvl)
            emit(outch(p), 0xB0, 7, (int)lround(std::min(100, (int)S.ptemp[p][8]) * 127.0 / 100.0));
        for (int p : parts_pan)
            emit(outch(p), 0xB0, 10, (int)lround(std::min(14, (int)S.ptemp[p][9]) * 127.0 / 14.0));
        if (rlevel)
            emit(9, 0xB0, 7, (int)lround(std::min(100, S.rhythm_level) * 127.0 / 100.0));
        for (int kk : keys) {
            const int key = kk / 4, k = kk % 4;
            const long base = 0x90 + 4 * (key - 24);
            (void)base;
            const int v = d[7 + (size_t)(((3L << 14) + 0x90 + 4 * (key - 24) + k) - a0)];
            auto nrpn = [&](int msb, int val) {
                emit(9, 0xB0, 99, msb); emit(9, 0xB0, 98, key); emit(9, 0xB0, 6, val);
            };
            if (k == 0)
                R.say("rhythm key " + std::to_string(key) + ": given timbre " + std::to_string(v)
                      + ": not followed (the timbres' order is not in Roland's documents)");
            else if (k == 1)
                nrpn(0x1A, (int)lround(std::min(100, v) * 127.0 / 100.0));
            else if (k == 2)
                nrpn(0x1C, (int)lround(1 + (14 - std::min(14, v)) * 126.0 / 14.0));
            else
                nrpn(0x1D, v ? 127 : 0);
        }
        if (chans) {
            std::string s = "parts' channels:";
            for (int p = 0; p < 9; p++)
                s += (p == 8 ? " rhythm " : " ") + (S.chan[p] < 16 ? std::to_string(S.chan[p] + 1) : std::string("off"));
            R.say(s);
        }
        if (vol && S.sys[0x16] >= 0) {
            const int x = (int)lround(std::min(100, S.sys[0x16]) / 100.0 * 16383.0);
            ex({0x7F, 0x7F, 0x04, 0x01, (uint8_t)(x & 127), (uint8_t)(x >> 7)});
        }
        if (tune && S.sys[0] >= 0) {
            const double hz = 432.1 + S.sys[0] * (457.6 - 432.1) / 127.0;
            const double cents = 1200.0 * std::log2(hz / 440.0);
            const int x = std::max(0, std::min(16383, 8192 + (int)lround(cents / 100.0 * 8192.0)));
            ex({0x7F, 0x7F, 0x04, 0x03, (uint8_t)(x & 127), (uint8_t)(x >> 7)});
        }
        if (rev) {
            static const int MACRO[4] = {0, 3, 5, 6};       // Room, Hall, Plate, Tap delay
            if (S.sys[1] >= 0)
                gs(0x40, 0x01, 0x30, MACRO[std::min(3, S.sys[1])]);
            if (S.sys[3] >= 0)
                gs(0x40, 0x01, 0x33, (int)lround(std::min(7, S.sys[3]) * 127.0 / 7.0));
            if (S.sys[2] >= 0)
                gs(0x40, 0x01, 0x34, (int)lround(std::min(7, S.sys[2]) * 127.0 / 7.0));
        }
    }

    // ONE MESSAGE heard (its tick its time): what it becomes, into o
    void feed(const MsgT &m0, std::vector<MsgT> &o)
    {
        out = &o;
        now = m0.tick;
        if (m0.status == 0xFF) {
            out->push_back(m0);
            return;
        }
        if (m0.status == 0xF0) {
            const auto &d = m0.data;
            if (d.size() >= 3 && d[0] == 0x41 && d[2] == 0x16) {
                n_excl++;
                const long a = d.size() >= 7 ? (((long)d[4] << 14) | (d[5] << 7) | d[6]) : 0;
                if (d.size() >= 9 && d[3] == 0x12 && (a >> 14) >= 0x50 && (a >> 14) <= 0x52)
                    R.say("CM-32P exclusives (the PCM parts' settings): not followed");
                else if (d.size() >= 9 && d[3] == 0x12)
                    dt1(d);
                return;
            }
            if (d.size() >= 3 && d[0] == 0x41 && d[2] == 0x14) {
                n_excl++;
                R.say("D-50 exclusives: not followed");
                return;
            }
            out->push_back(m0);
            return;
        }
        const int c = m0.status & 0x0F, kind = m0.status & 0xF0;
        int p = part_of(c);
        if (p < 0) {
            if (cm64 && c >= 10) {              // (a CM-64's CM-32P part, as it comes)
                out->push_back(m0);
                return;
            }
            if (kind == 0x90 && m0.d1)
                dropped[c]++;
            return;
        }
        MsgT m = m0;
        const int oc = outch(p);
        m.status = kind | oc;
        if (kind == 0x80 || kind == 0x90) {
            if (p < 8) {
                while (m.d0 < 12)
                    m.d0 += 12;
                while (m.d0 > 108)
                    m.d0 -= 12;
            } else if (m.d0 < 24 || m.d0 > rhythm_hi) {
                rhythm_out += kind == 0x90 && m.d1;
                return;
            }
            if (kind == 0x90 && m.d1)
                held.insert({oc, m.d0});
            else
                held.erase({oc, m.d0});
            out->push_back(m);
        } else if (kind == 0xB0) {
            int cc = m.d0;
            if (cc >= 124)
                cc = 123;
            static const std::set<int> RX = {1, 6, 7, 10, 11, 38, 64, 100, 101, 121, 123};
            if (!RX.count(cc) || (p == 8 && cc == 10))
                return;
            m.d0 = cc;
            out->push_back(m);
        } else if (kind == 0xC0) {
            if (p == 8)
                return;
            std::copy(S.pmem[m.d0 & 127], S.pmem[m.d0 & 127] + 7, S.ptemp[p]);
            patch(p, S.ptemp[p], "program change");
        } else if (kind == 0xE0) {
            out->push_back(m);
        }
        // (0xA0, 0xD0: aftertouch, not received)
    }

    // AT THE END: what was dropped, into the report
    void finish()
    {
        for (const auto &kv : dropped)
            R.say(std::to_string(kv.second) + " notes on channel " + std::to_string(kv.first + 1)
                  + ": no MT-32 part listens there");
        if (rhythm_out)
            R.say(std::to_string(rhythm_out) + " rhythm notes outside the MT-32's drum keys (24-" + std::to_string(rhythm_hi)
                  + "): not played");
    }
};

// One file's messages (absolute ticks) through the unit: returns them as
// it would hear them, our channels and our messages
template <class MsgT>
static std::vector<MsgT> apply(const std::vector<MsgT> &in, bool cm64, int &n_excl, Report &R)
{
    Unit<MsgT> u(cm64);
    std::vector<MsgT> out;
    for (const MsgT &m : in)
        u.feed(m, out);
    u.finish();
    n_excl += u.n_excl;
    R = u.R;
    return out;
}

}  // namespace mt32
