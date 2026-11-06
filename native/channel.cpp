// channel.cpp -- the native engine's CHANNELS: a file's controller events
// and notes in, the questions a note asks of its channel answered.
//
// blockrender's channel passes for the pedals and the note list, as the
// note loop reads them:
//
//   damper pedal (CC64)   _prep_damper_pedal: its down/up spans (64 the
//                         switch point), and, where the channel ever stands
//                         between 0 and 127, its values (half-pedalling)
//   sostenuto (CC66)      _prep_sostenuto_soft: the keys down when it went
//                         down, held to its rise
//   soft pedal (CC67)     ...in at a note's onset or not
//   all sound off         _prep_sound_off: CC120, 126, 127
//   the next strike       _next_same: when this key is struck again
//
// and _note_pedal's arithmetic on them: a note's end once the pedals have
// had their say (Song::note_off). The half-pedal's contact law is damper.py's
// (band, contact). Events keep the file's order within a tick (in_order: a
// stable sort on the time alone).

#include <algorithm>
#include <cstdio>
#include <array>
#include <cmath>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "pycompat.h"          // a stroke train's random.Random, sum()

namespace nv {

static double pymin(double a, double b) { return b < a ? b : a; }
static double pymax(double a, double b) { return b > a ? b : a; }

// damper.py
namespace damper {
const double BAND_TREBLE[2] = {24.0, 88.0};
const double BAND_BASS[2] = {40.0, 104.0};
const int LOW_KEY = 21;

static void band(int key, int top, double *lo, double *hi)
{
    double x = pymin(pymax((key - LOW_KEY) / (double)(top - LOW_KEY > 1 ? top - LOW_KEY : 1), 0.0), 1.0);
    *lo = BAND_BASS[0] + (BAND_TREBLE[0] - BAND_BASS[0]) * x;
    *hi = BAND_BASS[1] + (BAND_TREBLE[1] - BAND_BASS[1]) * x;
}

static double contact(int p, int key, int top)
{
    if (key >= top)
        return 0.0;
    double lo, hi;
    band(key, top, &lo, &hi);
    double x = pymin(pymax(((double)p - lo) / (hi - lo), 0.0), 1.0);
    return 1.0 - x * x * (3.0 - 2.0 * x);
}
}  // namespace damper

struct CC {
    double t;
    int cc, v;
};

typedef std::pair<double, double> Span;

// One channel's controllers, as the note loop asks of them.
struct Channel {
    std::vector<CC> ccs;                // in the file's order, then in_order
    std::vector<Span> ped, sost, soft;  // CC64, 66, 67 down/up spans
    std::vector<double> pv_t;           // a half-pedalled channel's CC64 times...
    std::vector<int> pv_v;              // ...and values (empty: a switch)
    std::vector<double> soff;           // all sound off, sorted

    std::vector<Span> spans(int cc, double total) const
    {
        std::vector<Span> segs;
        bool down = false;
        double dn = 0.0;
        for (const CC &e : ccs) {
            if (e.cc != cc)
                continue;
            if (e.v >= 64 && !down) {
                down = true;
                dn = e.t;
            } else if (e.v < 64 && down) {
                segs.push_back(Span(dn, e.t));
                down = false;
            }
        }
        if (down)
            segs.push_back(Span(dn, total));
        return segs;
    }

    void finish(double total)
    {
        std::stable_sort(ccs.begin(), ccs.end(), [](const CC &a, const CC &b) { return a.t < b.t; });
        ped = spans(64, total);
        sost = spans(66, total);
        soft = spans(67, total);
        bool half = false;
        for (const CC &e : ccs)
            if (e.cc == 64) {
                pv_t.push_back(e.t);
                pv_v.push_back(e.v);
                if (e.v > 0 && e.v < 127)
                    half = true;
            }
        if (!half) {
            pv_t.clear();
            pv_v.clear();
        }
        for (const CC &e : ccs)     // sorted() of the file-order times: the same set
            if (e.cc == 120 || e.cc == 126 || e.cc == 127)
                soff.push_back(e.t);
        std::sort(soff.begin(), soff.end());
    }

    // _damper_falls: when the damper lands for a key released at t
    double damper_falls(double t) const
    {
        // bisect_right(segs, (t, 1e18)) - 1: the last span starting at or before t
        int i = (int)(std::upper_bound(ped.begin(), ped.end(), Span(t, 1e18)) - ped.begin()) - 1;
        if (i >= 0 && ped[i].first <= t && t < ped[i].second)
            return ped[i].second;
        return t;
    }

    // _damper_lands: (when this key's damper lands, released at t; whether
    // the pedal stood in its band on the way)
    double damper_lands(double t, int key, int top, double total, bool *in_band) const
    {
        *in_band = false;
        int i = (int)(std::upper_bound(pv_t.begin(), pv_t.end(), t) - pv_t.begin()) - 1;
        double tt = t;
        int v = i >= 0 ? pv_v[i] : 0;
        for (int j = i;; j++) {
            if (j > i) {
                if (j >= (int)pv_t.size())
                    break;
                tt = pv_t[j];
                v = pv_v[j];
            }
            double k = damper::contact(v, key, top);
            if (k >= 1.0)
                return tt;
            if (k > 0.0)
                *in_band = true;
        }
        return pymax(total, t);
    }

    bool soft_at(double t) const
    {
        for (const Span &s : soft)
            if (s.first <= t && t < s.second)
                return true;
        return false;
    }

    // _sound_off: the first all-sound-off strictly after t (has: one exists)
    double sound_off(double t, bool *has) const
    {
        auto it = std::upper_bound(soff.begin(), soff.end(), t);
        *has = it != soff.end();
        return *has ? *it : 0.0;
    }
};

struct NoteKey {
    long long ch;
    int note;
    double on;
    bool operator<(const NoteKey &o) const
    {
        if (ch != o.ch)
            return ch < o.ch;
        if (note != o.note)
            return note < o.note;
        return on < o.on;
    }
};

struct Ev {
    long long ch;
    int note;
    double on, off;
    int vel;
    double v7, v11, pan, trim;          // the channel's CC7, CC11, CC10 at its onset; its program's trim
    int prog, drum;                     // its program, and whether a drum set's
    double ratio = 1.0;                 // a stroke's pitch (stroke_pitch: a bell tree's bar)
    int inner = 0;                      // a ridge after a scrape's first (inner_ridge: it chokes nothing)
    // a throat's pulse (stroke_tilt, stroke_mouth, stroke_morph): NaN, none
    double tilt = NAN, mouth = NAN, morph = NAN;
    int stroked = 0;                    // one of a gesture's strokes (_prep_strokes' _stroked)
    int mcut = 0, mslur = 0;            // mono mode's: cut by the next, arrived by a slur
    // a valved gliss's step (_GLISS): its level, the smear, the step it
    // arrives from (-1 none) and the step's time; gl 0 not one
    int gl = 0, gl_prev = -1;
    double gl_lv = 1.0, gl_sm = 0.0, gl_dt = 0.0;
    int slot = -1;                      // its variation's slot (bank select: K[NV_K_VAR + 128 x slot + key]), -1 none
    int kover = -1;                     // its class's own index in K (a drone's: _DRONE_PC), -1 none
    // its class's index in K: a drum set's key, a variation's, a program's
    int kidx() const
    {
        return kover >= 0 ? kover : drum ? NV_K_DRUMS + 128 * prog + note
                                         : slot >= 0 ? NV_K_VAR + 128 * slot + note : 128 * prog + note;
    }
    // ...and the TONE it is on its part (_TONE_SEGS' key: the program, or
    // the variation -- a layered one's each layer -- as its own)
    int tone() const { return slot >= 0 ? 1024 + slot : prog; }
};

// A file's channels and notes.
struct Song {
    std::map<long long, Channel> ch;
    std::vector<Ev> notes;
    // BANK SELECT (nv_song_vars): each entry's layers (slot, semitones,
    // lowest and highest velocity) and trim; GS's table [map][program][msb],
    // GM 2's [program][lsb] -- entry 0 the capital tone
    std::vector<std::vector<std::array<int, 4>>> vls;
    std::vector<double> vtrim;
    std::vector<int> vgs, vgm2;
    // each channel's keys as the file wrote them (_prep_choir_parts reads
    // the notes before a layered variation or a stroke expands them)
    std::map<long long, std::vector<int>> wkeys;
    // the last note's bank (the reader's bsel): its variation's slot -- a
    // LAYERED one (patch_map.LAYERED) the note again for each layer, at its
    // semitones, where the key is on the keyboard and the velocity in its
    // range (_prep_strokes, before anything else sees the note); 0 refused
    // (no table), 1 played
    int bank(int bsel)
    {
        if (vgs.empty())
            return 0;
        Ev e = notes.back();
        if (e.prog < 0 || e.prog > 127)
            return 1;
        int en = bsel <= 640 ? vgs[((size_t)((bsel - 1) / 128) * 128 + e.prog) * 128 + (bsel - 1) % 128]
                             : vgm2[(size_t)e.prog * 128 + (bsel - 641)];
        if (en <= 0)
            return 1;                       // (a variation not built: the capital, as a Sound Canvas)
        notes.pop_back();
        for (const auto &l : vls[en]) {
            int k = e.note + l[1];
            if (k < 0 || k > 127 || e.vel < l[2] || e.vel > l[3])
                continue;
            Ev x = e;
            x.note = k;
            x.slot = l[0];
            x.trim = vtrim[en];
            notes.push_back(x);
        }
        return 1;
    }
    std::map<NoteKey, double> next_same, sost_held;
    std::map<long long, int> vbase;     // each channel's median velocity (_vbase)
    std::map<long long, int> parts;     // a sung part's voice part, by its track's name (nv_voice_body)
    // the rows of each played note that is a gesture's stroke (nv_prepare's:
    // blockrender's stroke_rows), [first, end)
    std::vector<std::pair<long long, long long>> stroke_rows;
    // a reed organ's notes struck with its Tremolo stop drawn (by note), and
    // their rows (_HT_ROWS, nv_prepare's)
    mutable std::vector<char> htrem_note;
    std::vector<std::pair<long long, long long>> htrem_rows;
    // the rotating speakers (_LESLIE_CH): each channel as its first Leslie
    // note came, and how it starts (1 chorale, 2 tremolo)
    std::vector<std::pair<long long, int>> leslie;
    // a voice's tremolos (_TREM_CH, an ordinary voice's): each channel's
    // (rate, depth, stereo, scatter), the first note's to set one
    std::vector<std::pair<long long, std::vector<double>>> trems;
    // the speaker cabinets (_CAB_CH): each channel's, its first note's to have one
    std::vector<std::pair<long long, const NoteClass *>> cabs;
    std::vector<std::pair<long long, int>> clavs;      // (_CLAV_CH: a Clavinet's channel, its rockers)
    // the valve amplifiers (_AMP_CH): each channel as its first amplified
    // note came, its voice's drive, and whether it is on a rotor
    std::vector<std::pair<long long, std::pair<double, int>>> amp;
    std::vector<std::pair<double, double>> amp_cfg;     // (its reference peak, 0 none; its imbalance)
    // ...and of each note's bellows push (blockrender's push_rows), [first, end)
    std::vector<std::pair<long long, long long>> push_rows;
    // ...and of each jack's key-up click (blockrender's rel_jacks): first, end, rank, offset (s)
    std::vector<double> rel_jacks;
    // ...and each note's key-up rows, [first, end) (blockrender's rel_rows)
    std::vector<long long> rel_rows;
    // ...and its grains' (_GRAIN_ROWS: live keeps their own onsets), [first, end)
    std::vector<long long> grain_rows;
    double total = 0.0;
    // ITS TUNING: the file's table, a channel's MIDI Tuning Standard tables
    // from their times (_MTS_TL), its fixed bend (_BTUN) and octave tuning (_OTUN)
    std::vector<double> freq = std::vector<double>(128, 0.0);
    std::map<long long, std::vector<std::pair<double, std::vector<double>>>> mts;
    std::map<long long, double> btun;
    std::map<long long, std::vector<double>> otun;
    std::map<long long, int> fader;     // channels whose fader is a row (_LROW): their volume 1
    // THE DRUM SETS (percussion_for_note at kit_for_program): each drum
    // program's key, its pitch (0: no drum the engine knows) and its seat
    std::vector<double> kit_f0, kit_seat;
    // ...and its EXCLUSIVE CLASSES (percussion_map.choke_group): each drum
    // program's key, the keys a strike on it stops (bits, two words), and
    // from them (finish) each drum channel's key's later strikes that stop
    // it (_prep_exclusive_classes' choke_at)
    std::vector<unsigned long long> kit_choke;
    std::map<std::pair<long long, int>, std::vector<double>> choke_at;
    // ITS SLURS: _legato_ticks' (channel, key, k), and from them (finish)
    // each note's -- slurred, and a slur leaving it (_prep_slur_out)
    std::set<std::tuple<long long, int, int>> legato;
    std::vector<char> slurred, slur_out;
    // ITS SOUND CONTROLS (sndev, and gmon's resets: ch -1, cc -1), in the
    // file's order
    struct Snd {
        long long ch;
        double t;
        int cc, v;
    };
    std::vector<Snd> snd;
    std::vector<long long> mix;     // each note's mix channel (nv_song_mix), made at the first ask
    // ITS MOOGS' ROWS (_MOOG_FT, _MOOG_KN, _MOOG_KROW): each layer of each
    // Moog note its filter row, in the notes' order; the knob rows, one a
    // channel and panel (a row's slot 9 its index)
    std::vector<std::array<double, 30>> mft;
    std::vector<std::array<double, 9>> mkn;
    std::map<std::pair<long long, std::array<double, 9>>, int> mkrow;
    // ...and each filter row's panel, onset, release and end (its pitch and
    // shape rows: moog.pitch_rows, shape_rows)
    std::vector<const MoogLayer *> mlay;
    std::vector<std::array<double, 3>> mspan;
    // ...and THE MF-104M's notes (_MF104): each layer's rows and its panel
    struct Mf {
        long long r0, r1;
        const MoogLayer *L;
    };
    std::vector<Mf> mf104;
    // ...and a channel whose cutoff or resonance moves (_kn_moves): one knob
    // row a channel, class and layer, its knobs at each of the channel's
    // sound controls (_MOOG_KVAR: grid point, knob row)
    std::map<std::tuple<long long, const void *, int>, int> mkmove;
    std::map<int, std::vector<std::pair<long long, std::array<double, 9>>>> mkvar;

    // WHAT A PLAY APPENDS (nv_play), as it stood before the first: a play
    // again (register.cpp's, a bigger row store) rewinds to it
    struct PlayMark {
        bool set = false;
        size_t push, jacks, rel, grain, mft, mkn, mlay, mspan, mf;
        std::map<std::pair<long long, std::array<double, 9>>, int> mkrow;
        std::map<std::tuple<long long, const void *, int>, int> mkmove;
        std::map<int, std::vector<std::pair<long long, std::array<double, 9>>>> mkvar;
    } pmark;
    void play_mark()
    {
        PlayMark &m = pmark;
        if (!m.set) {
            m.set = true;
            m.push = push_rows.size(); m.jacks = rel_jacks.size(); m.rel = rel_rows.size();
            m.grain = grain_rows.size(); m.mft = mft.size(); m.mkn = mkn.size(); m.mlay = mlay.size();
            m.mspan = mspan.size(); m.mf = mf104.size();
            m.mkrow = mkrow; m.mkmove = mkmove; m.mkvar = mkvar;
            return;
        }
        push_rows.resize(m.push); rel_jacks.resize(m.jacks); rel_rows.resize(m.rel);
        grain_rows.resize(m.grain); mft.resize(m.mft); mkn.resize(m.mkn); mlay.resize(m.mlay);
        mspan.resize(m.mspan); mf104.resize(m.mf);
        mkrow = m.mkrow; mkmove = m.mkmove; mkvar = m.mkvar;
    }
    // ITS GLIDES (_prep_glide_sources, from finish): each note's source key, -1 none
    std::vector<int> glide_src;

    // ITS REGISTERED ORGANS (_prep_organ_rows: one a channel and family): the
    // organ's table, its ranks' gate rows from g0 and its swell row, its
    // stop word's events -- each rank's (time, target) and the swell's --
    // and each rank's wind row (_prep_wind_rows; -1 none)
    struct Organ {
        long long ch;
        const OrganSpec *spec;
        int g0, cr;
        std::vector<std::vector<std::pair<double, double>>> rank_ev;
        std::vector<std::pair<double, double>> swell_ev;
        std::vector<int> wrow;
    };
    std::vector<Organ> organs;
    int n_grows = 0;

    // registration_blocks' events for an organ on channel ch: its stop word
    // (and the crescendo, and the swell) from the channel's controllers, a
    // program change to another of its tones recalling that tone's default
    // (recalls: the notes' programs, prog_organ[program] their organ)
    void organ_add(long long ch, const OrganSpec *spec, const OrganSpec *const *prog_organ)
    {
        Organ o;
        o.ch = ch;
        o.spec = spec;
        o.g0 = n_grows;
        o.cr = (int)organs.size();
        n_grows += spec->n_rank;
        int nr = spec->n_rank;
        o.rank_ev.assign(nr, {});
        o.wrow.assign(nr, -1);
        // the recalls: the channel's notes by onset, a tone of this family whose default differs
        std::vector<int> idx;
        for (size_t i = 0; i < notes.size(); i++)
            if (notes[i].ch == ch)
                idx.push_back((int)i);
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return notes[a].on < notes[b].on; });
        std::vector<std::pair<double, int>> recalls;
        int ds = spec->default_stops;
        for (int i : idx) {
            const Ev &e = notes[i];
            const OrganSpec *q = (e.prog >= 0 && e.prog < 128 && !e.drum) ? prog_organ[e.prog] : nullptr;
            if (q && q->family == spec->family) {
                if (q->default_stops != ds) {
                    recalls.push_back(std::make_pair(e.on - 1e-4, q->default_stops));
                    ds = q->default_stops;
                }
            }
        }
        int nw = spec->n_wccs;
        int wb[4];
        for (int i = 0; i < nw; i++)
            wb[i] = (spec->default_stops >> (7 * i)) & 0x7F;
        double cres = 0.0, vol = 1.0;
        auto emit = [&](double t) {
            long long mask = 0;
            for (int i = 0; i < nw; i++)
                mask |= (long long)wb[i] << (7 * i);
            int nd = (int)(cres * spec->n_order + 1e-9);
            for (int ri = 0; ri < nr; ri++) {
                bool drawn = false;
                for (int q = 0; q < nd && q < spec->n_order; q++)
                    if (spec->order[q] == ri)
                        drawn = true;
                o.rank_ev[ri].push_back(std::make_pair(t, ((mask >> ri) & 1) || drawn ? 1.0 : 0.0));
            }
            o.swell_ev.push_back(std::make_pair(t, vol));
        };
        emit(0.0);
        struct Ce {
            double t;
            int cc, v;
        };
        std::vector<Ce> ev;
        const Channel *C = get(ch);
        if (C)
            for (const CC &e : C->ccs)
                ev.push_back(Ce{e.t, e.cc, e.v});
        for (auto &r : recalls)
            ev.push_back(Ce{r.first, -1, r.second});
        if (!recalls.empty())
            std::stable_sort(ev.begin(), ev.end(), [](const Ce &a, const Ce &b) { return a.t < b.t; });
        for (const Ce &e : ev) {
            int wi = -1;
            for (int i = 0; i < nw; i++)
                if (spec->wccs[i] == e.cc) {
                    wi = i;
                    break;
                }
            if (e.cc == -1) {
                for (int i = 0; i < nw; i++)
                    wb[i] = (e.v >> (7 * i)) & 0x7F;
            } else if (wi >= 0)
                wb[wi] = e.v;
            else if (e.cc == 4)
                cres = e.v / 127.0;
            else if (e.cc == 7 && spec->swells)
                vol = e.v / 127.0;
            else
                continue;
            emit(e.t);
        }
        organs.push_back(std::move(o));
    }

    const OrganSpec *prog_organ[128] = {nullptr};

    // onepole_blocks: events (the first the default) at the nblk block centres
    static void onepole(const std::vector<std::pair<double, double>> &ev, long nblk, int blk, double sr, double tau,
                        float *out)
    {
        double v = ev[0].second;
        long b = 0;
        for (size_t k = 0; k < ev.size(); k++) {
            double t0 = k == 0 ? 0.0 : ev[k].first, target = ev[k].second;
            double t1 = k + 1 < ev.size() ? ev[k + 1].first : 1e18;
            for (long q = 0; q < nblk; q++) {
                double bc = ((double)q + 0.5) * blk / sr;
                if (bc >= t0 && bc < t1)
                    out[q] = (float)(target + (v - target) * exp(-(bc - t0) / tau));
            }
            if (t1 < 1e17)
                v = target + (v - target) * exp(-(t1 - t0) / tau);
            (void)b;
        }
    }

    // the wind rows' places (_prep_chest_wind, _prep_wind_rows): each
    // channel's first organ, a pipe organ's, with its shared wind or its
    // Tremulant drawn: a row a family of its ranks, from row0; the count
    int organ_wind_rows(int row0)
    {
        int r = row0;
        std::set<long long> seen;
        for (Organ &o : organs) {
            if (seen.count(o.ch))
                continue;
            seen.insert(o.ch);
            const OrganSpec *sp = o.spec;
            if (!sp->wind)
                continue;
            bool trem = false;
            if (sp->trem_rank >= 0)
                for (auto &e : o.rank_ev[sp->trem_rank])
                    if (e.second >= 0.5)
                        trem = true;
            trem = trem && sp->trem_class_depth > 0.0;
            if (!(sp->wsc != 0.0 || trem))
                continue;
            std::vector<std::pair<double, double>> fams;
            std::vector<int> frow;
            for (int ri = 0; ri < sp->n_rank; ri++) {
                if (sp->rank[ri].n_ratio == 0)
                    continue;
                std::pair<double, double> ab(sp->fam_a[ri], sp->fam_b[ri]);
                int f = -1;
                for (size_t q = 0; q < fams.size(); q++)
                    if (fams[q] == ab)
                        f = (int)q;
                if (f < 0) {
                    fams.push_back(ab);
                    frow.push_back(r++);
                    f = (int)fams.size() - 1;
                }
                o.wrow[ri] = frow[f];
            }
        }
        return r - row0;
    }

    const Organ *organ_of(long long ch, int family) const
    {
        for (const Organ &o : organs)
            if (o.ch == ch && o.spec->family == family)
                return &o;
        return nullptr;
    }

    // _snd_d: CC71-78's d (sound_offset) in force on channel c at t, 0 none
    void sound_at(long long c, double t, double *d) const
    {
        for (int i = 0; i < 8; i++)
            d[i] = 0.0;
        for (const Snd &e : snd) {
            if (e.ch != c && e.ch != -1)
                continue;
            if (e.t > t + 1e-9)
                break;
            if (e.cc < 0)
                for (int i = 0; i < 8; i++)
                    d[i] = 0.0;
            else
                d[e.cc - 71] = ((double)e.v - 64.0) / 64.0;
        }
    }

    // bisect.bisect_right(a, (t, 128)) on a list of (time, value) pairs
    static int bisect_tv(const std::vector<std::pair<double, int>> &a, double t)
    {
        int lo = 0, hi = (int)a.size();
        while (lo < hi) {
            int mid = (lo + hi) / 2;
            if (t < a[mid].first || (t == a[mid].first && 128 < a[mid].second))
                hi = mid;
            else
                lo = mid + 1;
        }
        return lo;
    }

    // _porta_cc5_at: the CC5 in force on channel c at t (0 before any)
    int cc5_at(long long c, double t) const
    {
        const Channel *C = get(c);
        if (!C)
            return 0;
        std::vector<std::pair<double, int>> ev;
        for (const CC &e : C->ccs)
            if (e.cc == 5)
                ev.push_back(std::make_pair(e.t, e.v));
        if (ev.empty())
            return 0;
        int i = bisect_tv(ev, t) - 1;
        return i >= 0 ? ev[i].second : 0;
    }

    // _prep_glide_sources: where each note glides from -- the channel's
    // latest CC84 since its last note (spent once, CC84_CANCEL none), else
    // under CC65 its last note's key from a strictly earlier onset
    // _prep_gliss, its valved part: a note a valve's class glides to
    // (glide_mech 3, _GLIDE_SRC) over two semitones or more, as the run it
    // walks -- a step a semitone from the source, evenly over its CC5's time
    // (glide_tau 'slide', PORTA_SETTLE_TAUS; a real hold left to land on:
    // max(GLISS_ARRIVAL_S, GLISS_ARRIVAL_FRAC of it)), each its level
    // (quietest in the middle, by the smear CC5 opens) and the step before
    // it; the note proper from where the run arrives. A run under 12 ms a
    // step plays clean. The steps after the rest, as the Python appends
    // them; what follows the gliss in the Python (the slurs' occurrences,
    // next_same) made again on them, the glide sources carried
    // THE DRONES (_prep_phrase_spans, _DRONE_PC): each channel's phrases --
    // its notes by onset, a gap past its programs' part_break_s (2 s) a new
    // one -- and where a program's class has drones, under each phrase the
    // ones its first CC1 leaves uncorked (round(cc / 127 x n); all without
    // one), from its first note-on (each a microsecond after the last) to
    // its last note-off, at the phrase's first note's velocity, levels and
    // program, each its own class; appended in channel, phrase, drone order
    bool drones_done = false;
    int drones(const NoteClass *const *K)
    {
        if (drones_done)
            return 0;
        drones_done = true;
        std::vector<long long> chs;
        std::map<long long, std::vector<int>> byc;
        for (size_t i = 0; i < notes.size(); i++) {
            if (!byc.count(notes[i].ch))
                chs.push_back(notes[i].ch);
            byc[notes[i].ch].push_back((int)i);
        }
        std::vector<Ev> add;
        for (long long c : chs) {
            const std::vector<int> &ix = byc[c];
            const NoteClass *bpc = nullptr;
            double gap = NAN;
            for (int i : ix) {
                // (the PROGRAM's class, property_class_for_program: a drone's
                // own key on the part still has the chanter's drones)
                const Ev &e = notes[i];
                if (e.drum || e.prog < 0 || e.prog > 127)
                    continue;
                const NoteClass *k = K[e.slot >= 0 ? NV_K_VAR + 128 * e.slot + 60 : 128 * e.prog + 60];
                if (!k)
                    continue;
                if (std::isnan(gap))
                    gap = k->part_break_s;
                else if (gap != k->part_break_s)
                    return -1;                  // (programs whose phrases break differently: Python's set order)
                if (k->n_drone) {
                    if (bpc && bpc != k)
                        return -1;              // (two drone classes on one channel: Python's set order)
                    bpc = k;
                }
            }
            if (!bpc || notes[ix[0]].drum)
                continue;
            if (std::isnan(gap))
                gap = 2.0;
            std::vector<std::pair<double, double>> on_off;
            for (int i : ix)
                on_off.push_back(std::make_pair(notes[i].on, notes[i].off));
            std::sort(on_off.begin(), on_off.end());
            std::vector<std::pair<double, double>> ph;
            for (auto &p : on_off) {
                if (!ph.empty() && p.first - ph.back().second <= gap)
                    ph.back().second = std::max(ph.back().second, p.second);
                else
                    ph.push_back(p);
            }
            int nd = bpc->n_drone;
            auto it = ch.find(c);
            if (it != ch.end())
                for (const CC &e : it->second.ccs)
                    if (e.cc == 1) {
                        nd = (int)nearbyint(e.v / 127.0 * bpc->n_drone);
                        break;
                    }
            for (auto &p : ph) {
                int first = -1;
                for (int i : ix)
                    if (p.first <= notes[i].on && notes[i].on <= p.second && (first < 0 || notes[i].on < notes[first].on))
                        first = i;
                for (int d = 0; d < nd; d++) {
                    Ev x = notes[first];
                    x.note = bpc->drone_note[d];
                    x.on = p.first + 1e-6 * d;
                    x.off = p.second;
                    x.kover = bpc->drone_k[d];
                    x.ratio = 1.0;              // (none of the first note's stroke: the drone's own note and onset)
                    x.inner = 0;
                    x.tilt = x.mouth = x.morph = NAN;
                    x.slot = -1;
                    x.mcut = x.mslur = 0;
                    x.gl = 0;
                    x.stroked = 0;
                    add.push_back(x);
                }
            }
        }
        if (add.empty())
            return 0;
        for (const Ev &x : add) {
            notes.push_back(x);
            glide_src.push_back(-1);
        }
        // (the slurs again -- the note loop counts a drone's occurrence, and
        // _SLUR_OUT reads them -- but not next_same: _prepare's was made
        // before the drones, so a tenor is not cut by its twin)
        mix.clear();
        slurs();
        return 0;
    }

    // _GLISS_DROP: every note of e's (channel, key, onset)
    void drop_key(std::vector<char> &drop, const Ev &e) const
    {
        for (size_t j = 0; j < notes.size(); j++)
            if (notes[j].ch == e.ch && notes[j].note == e.note && notes[j].on == e.on)
                drop[j] = 1;
    }

    bool gliss_done = false;
    void gliss(const NoteClass *const *K)
    {
        if (gliss_done)
            return;
        gliss_done = true;
        std::vector<Ev> steps;
        std::vector<char> drop(notes.size(), 0);
        std::vector<int> gsrc_keep;
        bool any = false;
        for (size_t i = 0; i < notes.size(); i++) {
            const Ev &e = notes[i];
            int gs = i < glide_src.size() ? glide_src[i] : -1;
            if (gs < 0 || e.drum || e.prog < 0 || e.prog > 127)
                continue;
            const NoteClass *k = K[e.kidx()];
            if (!k || k->glide_mech != 3)
                continue;
            int step = e.note > gs ? 1 : -1;
            std::vector<int> path;
            for (int p = gs; p != e.note; p += step)
                path.push_back(p);
            if (path.size() < 2 || e.off - e.on <= 0.0)
                continue;
            int cc5 = cc5_at(e.ch, e.on);
            const std::vector<double> &F = table(e.ch, e.on);
            double ft = F[e.note], fs = F[gs];
            double v = pymin(127.0, pymax(0.0, (double)cc5)) / 127.0;
            double t1 = k->porta_fast * pow(k->porta_slow / k->porta_fast, v);
            double T = pymax(1e-4, t1 * fabs(1.0 / fs - 1.0 / ft) / k->porta_d_semi) * k->porta_settle;
            double dur = e.off - e.on;
            T = pymin(T, dur - pymax(0.06, 0.2 * dur));      // GLISS_ARRIVAL_S, GLISS_ARRIVAL_FRAC
            double dt = T > 0.0 ? T / (double)path.size() : 0.0;
            if (dt < 0.012)
                continue;                   // faster than a valve moves: played clean
            double sm = pymin(1.0, pymax(0.0, cc5 / 127.0));
            int n = (int)path.size();
            for (int q = 0; q < n; q++) {
                double t0 = e.on + q * dt;
                double mid = 1.0 - fabs((q + 0.5) / n * 2.0 - 1.0);
                Ev x = e;
                x.note = path[q];
                x.on = t0;
                x.off = t0 + dt * 1.35;
                x.gl = 1;
                x.gl_lv = 1.0 - 0.45 * sm * mid;
                x.gl_sm = sm;
                x.gl_prev = q ? path[q - 1] : -1;
                x.gl_dt = dt;
                steps.push_back(x);
            }
            Ev x = e;
            x.on = e.on + T;
            x.gl = 1;
            x.gl_lv = 1.0;
            x.gl_sm = sm;
            x.gl_prev = path.back();
            x.gl_dt = dt;
            steps.push_back(x);
            // (the Python drops every note of this (channel, key, onset))
            drop_key(drop, e);
            any = true;
        }
        // A FALL IS A GLISS DOWN (fall_cents: _prep_gliss's falls): the note
        // held fall_at_s, then down the lattice a semitone a step over fall_s,
        // each step fading fall_fade_db across the run; a key let go before
        // the fall begins releases as any note does
        const size_t nn = notes.size();
        for (size_t i = 0; i < nn; i++) {
            const Ev &e = notes[i];
            if (drop[i] || e.drum || e.prog < 0 || e.prog > 127)
                continue;
            const NoteClass *k = K[e.kidx()];
            if (!k || !k->fall_cents)
                continue;
            double tf = e.on + k->fall_at_s;
            if (e.off <= tf)
                continue;
            int ns = (int)nearbyint(k->fall_cents / 100.0);
            ns = ns > 2 ? ns : 2;
            double dt = k->fall_s / ns;
            drop_key(drop, e);
            Ev x = e;
            x.off = tf;
            steps.push_back(x);
            for (int q = 0; q < ns; q++) {
                int p = e.note - 1 - q;
                if (p < 0)
                    break;
                double t0 = tf + q * dt;
                Ev y = e;
                y.note = p;
                y.on = t0;
                y.off = t0 + dt * 1.35;
                y.gl = 1;
                y.gl_lv = pow(10.0, -k->fall_fade_db * (double)(q + 1) / ns / 20.0);
                y.gl_sm = k->fall_smear;
                y.gl_prev = e.note - q;
                y.gl_dt = dt;
                steps.push_back(y);
            }
            any = true;
        }
        // ...AND A RIP, the fall's mirror (rip_cents): from the onset up the
        // lattice from rip_cents below over rip_s, crescendoing from
        // rip_start_db under; the note proper from where the run arrives
        for (size_t i = 0; i < nn; i++) {
            const Ev &e = notes[i];
            if (drop[i] || e.drum || e.prog < 0 || e.prog > 127)
                continue;
            const NoteClass *k = K[e.kidx()];
            if (!k || !k->rip_cents)
                continue;
            int ns = (int)nearbyint(k->rip_cents / 100.0);
            ns = ns > 2 ? ns : 2;
            double T = k->rip_s;
            if (e.off <= e.on + T)
                continue;                   // a note shorter than its rip: played plain
            double dt = T / ns;
            drop_key(drop, e);
            for (int q = 0; q < ns; q++) {
                int p = e.note - ns + q;
                if (p < 0)
                    continue;
                double t0 = e.on + q * dt;
                Ev y = e;
                y.note = p;
                y.on = t0;
                y.off = t0 + dt * 1.35;
                y.gl = 1;
                y.gl_lv = pow(10.0, -k->rip_start_db * (double)(ns - q) / ns / 20.0);
                y.gl_sm = k->rip_smear;
                y.gl_prev = q ? p - 1 : -1;
                y.gl_dt = dt;
                steps.push_back(y);
            }
            Ev y = e;
            y.on = e.on + T;
            y.gl = 1;
            y.gl_lv = 1.0;
            y.gl_sm = k->rip_smear;
            y.gl_prev = e.note - 1;
            y.gl_dt = dt;
            steps.push_back(y);
            any = true;
        }
        if (!any)
            return;
        std::vector<Ev> out;
        std::vector<int> gs2;
        for (size_t i = 0; i < notes.size(); i++)
            if (!drop[i]) {
                out.push_back(notes[i]);
                gs2.push_back(i < glide_src.size() ? glide_src[i] : -1);
            }
        for (const Ev &x : steps) {
            out.push_back(x);
            gs2.push_back(-1);              // (the lattice replaces the smooth glide)
        }
        notes.swap(out);
        glide_src.swap(gs2);
        mix.clear();
        slurs();
        next_same.clear();
        std::vector<int> idx(notes.size());
        for (size_t i = 0; i < idx.size(); i++)
            idx[i] = (int)i;
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return -notes[a].on < -notes[b].on; });
        std::map<std::pair<long long, int>, double> seen;
        for (int i : idx) {
            const Ev &e = notes[i];
            auto kk = std::make_pair(e.ch, e.note);
            auto it = seen.find(kk);
            if (it != seen.end())
                next_same[NoteKey{e.ch, e.note, e.on}] = it->second;
            seen[kk] = e.on;
        }
    }

    void glides()
    {
        std::map<long long, std::vector<std::pair<double, double>>> on;     // CC65's spans
        std::map<long long, std::vector<std::pair<double, int>>> ctl;       // CC84's
        for (auto &c : ch) {
            double dn = -1.0;
            bool down = false;
            for (const CC &e : c.second.ccs) {
                if (e.cc == 84)
                    ctl[c.first].push_back(std::make_pair(e.t, e.v));
                if (e.cc != 65)
                    continue;
                if (e.v >= 64 && !down) {
                    dn = e.t;
                    down = true;
                } else if (e.v < 64 && down) {
                    on[c.first].push_back(std::make_pair(dn, e.t));
                    down = false;
                }
            }
            if (down)
                on[c.first].push_back(std::make_pair(dn, total));
        }
        glide_src.assign(notes.size(), -1);
        std::vector<int> idx;
        for (size_t i = 0; i < notes.size(); i++)
            if (!notes[i].inner && !notes[i].stroked)
                idx.push_back((int)i);
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) {
            const Ev &x = notes[a], &y = notes[b];
            if (x.on != y.on)
                return x.on < y.on;
            if (x.ch != y.ch)
                return x.ch < y.ch;
            return x.note < y.note;
        });
        std::map<long long, std::pair<double, int>> prev;     // the channel's last note started
        std::map<long long, int> used;                          // ...and its last CC84 spent
        for (int i : idx) {
            const Ev &e = notes[i];
            int src = -1;
            auto ct = ctl.find(e.ch);
            if (ct != ctl.end()) {
                int j = bisect_tv(ct->second, e.on) - 1;
                auto u = used.find(e.ch);
                if (j >= 0 && j != (u == used.end() ? -1 : u->second)) {
                    auto pv = prev.find(e.ch);
                    if (pv == prev.end() || ct->second[j].first >= pv->second.first) {
                        used[e.ch] = j;
                        if (ct->second[j].second != 128)
                            src = ct->second[j].second;
                    }
                }
            }
            if (src < 0) {
                bool down = false;
                auto o = on.find(e.ch);
                if (o != on.end())
                    for (const auto &sg : o->second)
                        if (sg.first <= e.on && e.on < sg.second) {
                            down = true;
                            break;
                        }
                auto pv = prev.find(e.ch);
                if (down && pv != prev.end() && pv->second.first < e.on)
                    src = pv->second.second;
            }
            if (src >= 0 && src != e.note)
                glide_src[i] = src;
            auto pv = prev.find(e.ch);
            if (pv == prev.end() || e.on >= pv->second.first)
                prev[e.ch] = std::make_pair(e.on, e.note);
        }
    }

    bool in_group(int prog, int key, int k) const
    {
        const unsigned long long *m = &kit_choke[2 * (128 * prog + key)];
        return (m[k >> 6] >> (k & 63)) & 1ULL;
    }

    void exclusive_classes()
    {
        choke_at.clear();
        if (kit_choke.empty())
            return;
        // the notes in a choke group, by channel and key, and the set each
        // (channel, key) was last struck in
        std::map<std::pair<long long, int>, int> kit_on;
        std::map<std::pair<long long, int>, std::vector<double>> ons;
        for (const Ev &e : notes) {
            if (!e.drum || e.prog < 0 || e.prog > 127)
                continue;
            const unsigned long long *m = &kit_choke[2 * (128 * e.prog + e.note)];
            if (!(m[0] | m[1]))
                continue;
            auto k = std::make_pair(e.ch, e.note);
            kit_on[k] = e.prog;
            if (!e.inner)
                ons[k].push_back(e.on);
        }
        for (auto &a : ons) {
            int prog = kit_on[a.first];
            std::vector<double> later;
            for (auto &b : ons)
                if (b.first.first == a.first.first && in_group(prog, a.first.second, b.first.second))
                    later.insert(later.end(), b.second.begin(), b.second.end());
            std::sort(later.begin(), later.end());
            choke_at[a.first] = later;
        }
    }

    // The notes in the note loop's order (onset, channel, key), each key's
    // k-th a slur where legato has it; and a note a slurred onset on its
    // channel follows, sounding up to it or ending within 20 ms before
    void slurs()
    {
        size_t n = notes.size();
        slurred.assign(n, 0);
        slur_out.assign(n, 0);
        if (legato.empty())
            return;
        std::vector<int> idx(n);
        for (size_t i = 0; i < n; i++)
            idx[i] = (int)i;
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) {
            const Ev &x = notes[a], &y = notes[b];
            if (x.on != y.on) return x.on < y.on;
            if (x.ch != y.ch) return x.ch < y.ch;
            return x.note < y.note;
        });
        std::map<std::pair<long long, int>, int> occ;
        std::map<long long, std::vector<double>> sl_on;
        for (int i : idx) {
            int &k = occ[std::make_pair(notes[i].ch, notes[i].note)];
            if (legato.count(std::make_tuple(notes[i].ch, notes[i].note, k))) {
                slurred[i] = 1;
                sl_on[notes[i].ch].push_back(notes[i].on);
            }
            k++;
        }
        for (auto &v : sl_on)
            std::sort(v.second.begin(), v.second.end());
        for (size_t i = 0; i < n; i++) {
            auto it = sl_on.find(notes[i].ch);
            if (it == sl_on.end())
                continue;
            auto q = std::upper_bound(it->second.begin(), it->second.end(), notes[i].on);
            if (q != it->second.end() && notes[i].off >= *q - 0.02)
                slur_out[i] = 1;
        }
        // (the Python's is a set of (channel, key, onset): two strikes of one
        // key at one onset share it -- either one's slur leaves both)
        std::map<std::tuple<long long, int, double>, char> by_key;
        for (size_t i = 0; i < n; i++)
            if (slur_out[i])
                by_key[std::make_tuple(notes[i].ch, notes[i].note, notes[i].on)] = 1;
        for (size_t i = 0; i < n; i++)
            if (!slur_out[i] && by_key.count(std::make_tuple(notes[i].ch, notes[i].note, notes[i].on)))
                slur_out[i] = 1;
    }

    // A STRUCK OR SCRAPED GESTURE'S STROKES (percussion_map.rasp_strokes, as
    // _prep_strokes expands them): each drum note whose set's key has a
    // gesture (kind[q]: 1 a rasp, 2 a cascade, 3 an impact train, 4 a roll,
    // 5 a pattern, 6 a voice's pulses; par[NV_SPAR q..])
    // replaced by its strokes -- each its own onset, end, velocity
    // (max(1, int(velocity x level))), pitch and, past the first, an inner
    // ridge. AND A KEY THAT ALSO STRIKES ANOTHER'S SOUND (key_layers:
    // par[NV_SPAR (q + 1) - 4] of them, the keys after): each struck as
    // the note is, before it, as _prep_strokes expands them
    void strokes(const int *kind, const double *par, const NoteClass *const *K = nullptr)
    {
        std::vector<Ev> out;
        for (const Ev &e : notes) {
            bool in = e.drum && e.prog >= 0 && e.prog < 128 && e.note >= 0 && e.note < 128;
            int q = 128 * e.prog + e.note, kn = e.note;
            // ...A MELODIC SFX's (sfx_strokes_of): its kit key's table, the key its generator's
            const NoteClass *mk = (!e.drum && K) ? K[e.kidx()] : nullptr;
            bool mel = mk && mk->sfx_prog >= 0 && e.note >= 0 && e.note < 128;
            if (mel) {
                kn = mk->sfx_key >= 0 ? mk->sfx_key : e.note;
                q = 128 * mk->sfx_prog + kn;
            }
            for (int l = 0; in && l < (int)par[NV_SPAR * (q + 1) - 4]; l++) {
                Ev x = e;
                x.note = (int)par[NV_SPAR * (q + 1) - 3 + l];
                out.push_back(x);
            }
            int kd = (in || mel) ? kind[q] : 0;
            if (!kd) {
                out.push_back(e);
                continue;
            }
            const double *p = par + NV_SPAR * q;
            if (kd == 6) {
                // a voice's pulses: each its tilt, mouth and vowel too
                std::vector<std::array<double, 7>> vs;
                voiced(kn, e.on, p, vs);
                for (size_t k = 0; k < vs.size(); k++) {
                    Ev x = e;
                    x.on = vs[k][0];
                    x.off = vs[k][1];
                    long v = (long)(e.vel * vs[k][2]);
                    x.vel = (int)(v > 1 ? v : 1);
                    x.ratio = 1.0;
                    x.inner = k > 0;
                x.stroked = 1;
                    x.stroked = 1;
                    x.tilt = vs[k][4]; x.mouth = vs[k][5]; x.morph = vs[k][6];
                    out.push_back(x);
                }
                continue;
            }
            std::vector<std::array<double, 4>> st;     // (on, off, level, pitch)
            if (kd == 1)
                rasp(e.on, e.off, p, st);
            else if (kd == 2)
                cascade(e.on, e.off, p, st);
            else if (kd == 3)
                train(kn, e.on, p, st);
            else if (kd == 4)
                roll(kn, e.on, e.off, p, st);
            else
                pattern(e.on, p, st);
            for (size_t k = 0; k < st.size(); k++) {
                Ev x = e;
                x.on = st[k][0];
                x.off = st[k][1];
                long v = (long)(e.vel * st[k][2]);
                x.vel = (int)(v > 1 ? v : 1);
                x.ratio = st[k][3] != 1.0 ? st[k][3] : 1.0;
                x.inner = k > 0;
                x.stroked = 1;
                out.push_back(x);
            }
        }
        notes.swap(out);
    }

    static double shape_db(const double *shape, int n, double frac)
    {
        double x = frac * n - 0.5;
        if (x <= 0.0)
            return shape[0];
        if (x >= n - 1)
            return shape[n - 1];
        int i = (int)x;
        return shape[i] + (shape[i + 1] - shape[i]) * (x - i);
    }

    // the guiro's ridges: (dur, n, shape's length, its dB...)
    static void rasp(double on, double off, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double dur = p[0];
        int n = (int)p[1], ns = (int)p[2];
        double span = off > on ? pymax(dur, (off - on) * 0.5) : dur;
        if (n < 2) {
            out.push_back({on, on + span, 1.0, 1.0});
            return;
        }
        std::vector<double> w;
        for (int k = 0; k < n - 1; k++) {
            double frac = k / (double)(n - 1);
            double g = 1.260 - 0.330 * frac;
            if (frac > 0.80)
                g += 0.62 * (frac - 0.80) / 0.20;
            w.push_back(g);
        }
        double scale = span / pysum(w.data(), (int)w.size());
        double t = on;
        for (int k = 0; k < n; k++) {
            double frac = k / (double)(n - 1);
            double jitter = ((double)(((unsigned long long)k * 2654435761ULL) % 1000ULL) / 1000.0 - 0.5) * 0.05;
            double level = (0.318 + 0.400 * frac) / 0.638;
            if (frac > 0.80)
                level *= 1.0 - 0.30 * (frac - 0.80) / 0.20;
            if (ns)
                level *= pow(10.0, shape_db(p + 3, ns, frac) / 40.0);
            double step = (k < n - 1 ? w[k] : w.back()) * scale;
            out.push_back({t + step * jitter, t + step * 0.9, level, 1.0});
            t += step;
        }
    }

    // the bell tree's sweep: (span, n, semitones)
    static void cascade(double on, double off, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double span = p[0], semis = p[2];
        int n = (int)p[1];
        if (off > on)
            span = pymax(span, (off - on) * 0.6);
        for (int k = 0; k < n; k++) {
            double frac = n > 1 ? k / (double)(n - 1) : 0.0;
            double t = on + span * pow(frac, 0.85);
            double jitter = ((double)(((unsigned long long)k * 2654435761ULL) % 1000ULL) / 1000.0 - 0.5) * 0.35
                            * (span / (n > 1 ? n : 1));
            double level = 0.55 + 0.45 * pow(1.0 - fabs(frac - 0.45) / 0.55, 2.0);
            double ratio = pow(2.0, semis * frac / 12.0);
            out.push_back({pymax(on, t + jitter), t + span / n, level, ratio});
        }
    }

    // a held roll (_snare_roll): (rate, bounces, bounce s, bounce dB, the
    // other hand's dB, jitter, scatter dB, the least span, the body's, the
    // first stroke's and the last's dB) -- every bounce a stroke, sorted
    static void roll(int note, double on, double off, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double rate = p[0], bounce_s = p[2], bounce_db = p[3], hand_db = p[4], jit = p[5], sc = p[6];
        double body_db = p[8], first_db = p[9], last_db = p[10];
        int bounces = (int)p[1];
        PyRandom r;
        pyr_seed(&r, (long long)note * 7919LL + (long long)nearbyint(on * 1e4));
        double span = pymax(p[7], off - on);
        double last_t = span - 0.5 / rate;      // the last stroke lands as it ends
        size_t first = out.size();
        auto stroke = [&](double t, double base, int nb) {
            for (int b = 0; b < nb; b++) {
                double tb = t + b * bounce_s * (1.0 + pyr_uniform(&r, -0.15, 0.15));
                double db = base - bounce_db * b + pyr_uniform(&r, -sc, sc);
                out.push_back({on + tb, on + tb + 0.8 * bounce_s, pow(10.0, db / 40.0), 1.0});
            }
        };
        int k = 0;
        double t = 0.0;
        while (t < last_t) {
            double hand = k % 2 ? -hand_db : 0.0;
            stroke(t, k == 0 ? first_db : body_db + hand, bounces);
            k++;
            t = k / rate + pyr_uniform(&r, -jit, jit) / rate;
        }
        stroke(pymax(last_t, 0.0), last_db, 2);
        std::sort(out.begin() + first, out.end());
    }

    // a set's pattern (_pattern): (n, then each stroke's time, dB, semitones
    // and length -- NaN: to the next, the last 0.3 s)
    static void pattern(double on, const double *p, std::vector<std::array<double, 4>> &out)
    {
        int n = (int)p[0];
        for (int k = 0; k < n; k++) {
            const double *st = p + 1 + 4 * k;
            double end = !std::isnan(st[3]) ? st[0] + st[3] : k + 1 < n ? st[4] : st[0] + 0.3;
            out.push_back({on + st[0], on + end, pow(10.0, st[1] / 40.0), pow(2.0, st[2] / 12.0)});
        }
    }

    // a contour's value at t ((s, value) pairs, n of them: _voiced's along)
    static double along(const double *pts, int n, double t)
    {
        if (t <= pts[0])
            return pts[1];
        for (int i = 0; i + 1 < n; i++) {
            double ta = pts[2 * i], sa = pts[2 * i + 1], tb = pts[2 * i + 2], sb = pts[2 * i + 3];
            if (t <= tb)
                return sa + (sb - sa) * (t - ta) / (tb - ta);
        }
        return pts[2 * n - 1];
    }

    // a pitch's shape (native.stroke_spec): 0, bend octaves, time constant;
    // or 1, n, its (s, semitones) contour -- the octaves it moves at t; the
    // numbers it took
    static int shape_at(const double *p, double t, double *oct)
    {
        if (p[0] == 0.0) {
            *oct = p[1] * exp(-t / p[2]);
            return 3;
        }
        int n = (int)p[1];
        *oct = along(p + 2, n, t) / 12.0;
        return 2 + 2 * n;
    }

    // a voice's pulses (_voiced): (f0, dur, rise, fall dB, jitter, shimmer
    // dB, the shape, n syllables of (time, dB, semitones, own: 0 or 1 and
    // its shape and length), then the bright, mouth, level and morph
    // contours, n pairs each) -- each pulse (on, off, level, 1, its tilt,
    // mouth and vowel: NaN where the stroke names none)
    static void voiced(int note, double on, const double *p, std::vector<std::array<double, 7>> &out)
    {
        PyRandom r;
        pyr_seed(&r, (long long)note * 7919LL + (long long)nearbyint(on * 1e4));
        double f0 = p[0], dur = p[1], rise = p[2], fall_db = p[3], jitter = p[4], shimmer = p[5];
        double oct;
        const double *shape = p + 6;
        int c = 6 + shape_at(shape, 0.0, &oct);
        int nsyl = (int)p[c++];
        const double *syl = p + c;
        // skip past the syllables to the contours
        for (int s = 0; s < nsyl; s++) {
            c += 3;
            if (p[c++] != 0.0) {
                c += shape_at(p + c, 0.0, &oct);
                c++;
            }
        }
        const double *ct[4];
        int cn[4];
        for (int i = 0; i < 4; i++) {
            cn[i] = (int)p[c];
            ct[i] = p + c + 1;
            c += 1 + 2 * cn[i];
        }
        const double *bright = ct[0], *mouth = ct[1], *level = ct[2], *morph = ct[3];
        const double *q = syl;
        for (int s = 0; s < nsyl; s++) {
            double ts = q[0], db = q[1], semis = q[2];
            const double *sh = shape;
            double dn = dur;
            q += 3;
            if (*q++ != 0.0) {
                sh = q;
                q += shape_at(q, 0.0, &oct);
                dn = *q++;
            }
            double t = 0.0;
            while (t < dn) {
                shape_at(sh, t, &oct);
                double f = f0 * pow(2.0, semis / 12.0 + oct);
                double env = cn[2] ? along(level, cn[2], t)
                    : t < rise ? 20.0 * log10(pymax(t / rise, 0.03)) : -fall_db * (t - rise) / pymax(dn - rise, 1e-6);
                double per = pymax(0.3, pyr_gauss(&r, 1.0, jitter)) / f;
                double lvl = db + env + (shimmer != 0.0 ? pyr_gauss(&r, 0.0, shimmer) : 0.0);
                double tilt = NAN, mo = NAN, mr = NAN;
                if (cn[3]) {
                    tilt = cn[0] ? along(bright, cn[0], t) : 0.0;
                    mo = cn[1] ? along(mouth, cn[1], t) : 1.0;
                    mr = along(morph, cn[3], t);
                } else if (cn[1]) {
                    tilt = cn[0] ? along(bright, cn[0], t) : 0.0;
                    mo = along(mouth, cn[1], t);
                } else if (cn[0]) {
                    tilt = along(bright, cn[0], t);
                }
                out.push_back({on + ts + t, on + ts + t + per, pow(10.0, lvl / 40.0), 1.0, tilt, mo, mr});
                t += per;
            }
        }
    }

    // the vibraslap's impacts (_impact_train): (rate, secs, fall dB, jitter,
    // scatter dB, the strike's dB, side_db set, side_db, side_slope)
    static void train(int note, double on, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double rate = p[0], secs = p[1], fall = p[2], jit = p[3], sc = p[4], strike = p[5];
        bool has_side = p[6] != 0.0;
        double side_db = p[7], side_slope = p[8];
        PyRandom r;
        pyr_seed(&r, (long long)note * 1000003LL + (long long)nearbyint(on * 1e4));
        int n = (int)(rate * secs);
        for (int k = 0; k < n; k++) {
            double t = (k + pyr_uniform(&r, -jit, jit)) / rate;
            double swing = -fall * t / secs;
            double far = (has_side && k % 2) ? pymax(0.0, -swing - side_db) * side_slope : 0.0;
            double level = pow(10.0, (swing - far + pyr_uniform(&r, -sc, sc) + (k == 0 ? strike : 0.0)) / 20.0);
            double t0 = pymax(0.0, t);
            out.push_back({on + t0, on + t0 + 0.9 / rate, level, pow(2.0, pyr_uniform(&r, -0.1, 0.1))});
        }
    }

    void finish(double total_)
    {
        total = total_;
        exclusive_classes();
        slurs();
        for (auto &c : ch)
            c.second.finish(total);
        glides();
        // _next_same: the notes by onset, latest first (stable), each key's
        // next strike the one seen before it
        std::vector<int> idx(notes.size());
        for (size_t i = 0; i < idx.size(); i++)
            idx[i] = (int)i;
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return -notes[a].on < -notes[b].on; });
        std::map<std::pair<long long, int>, double> seen;
        for (int i : idx) {
            const Ev &e = notes[i];
            auto k = std::make_pair(e.ch, e.note);
            auto it = seen.find(k);
            if (it != seen.end())
                next_same[NoteKey{e.ch, e.note, e.on}] = it->second;
            seen[k] = e.on;
        }
        // _vbase: each channel's median velocity, sorted()[len // 2]
        std::map<long long, std::vector<int>> vs;
        for (const Ev &e : notes)
            vs[e.ch].push_back(e.vel);
        for (auto &v : vs) {
            std::sort(v.second.begin(), v.second.end());
            vbase[v.first] = v.second[v.second.size() / 2];
        }
        // _SOST_HELD: each sostenuto span catches the keys down as it went down
        for (auto &c : ch)
            for (const Span &s : c.second.sost)
                for (const Ev &e : notes)
                    if (e.ch == c.first && e.on <= s.first && s.first < e.off) {
                        NoteKey k{e.ch, e.note, e.on};
                        auto it = sost_held.find(k);
                        sost_held[k] = pymax(s.second, it == sost_held.end() ? 0.0 : it->second);
                    }
    }

    // _F: this channel's 128-key table at t
    const std::vector<double> &table(long long c, double t) const
    {
        auto it = mts.find(c);
        if (it == mts.end() || it->second.empty())
            return freq;
        const auto &tl = it->second;
        int i = 0;
        for (int j = 0; j < (int)tl.size(); j++)        // bisect_right on the starts, of t + 1e-9
            if (tl[j].first <= t + 1e-9)
                i = j + 1;
        i -= 1;
        return tl[i > 0 ? i : 0].second;
    }

    // THE SECONDARY TUNING (FREQ_E: an 'indian' class's table, empty none),
    // and the raga in force (T.raga_sa_note, -1 none; T.raga_spec's swaras)
    std::vector<double> freq_e;
    std::map<long long, std::vector<unsigned char>> sym_drv;    // each mix channel's strings' driver (_SYM_CH)
    std::map<NoteKey, std::pair<double, double>> meend;         // _MEEND_AT: (its ratio at Note On, its row or -1)
    int raga_sa = -1;
    bool raga_on = false;
    std::vector<double> raga_sw;
    const std::vector<double> &note_table(long long c, double t, bool indian) const
    {
        return indian && !freq_e.empty() ? freq_e : table(c, t);
    }

    // _note_class_and_pitch for a melodic note with none of its extras (no
    // per-note pitch, MPE, meend, sounding octaves, scale or brass law): f0
    // A CLASS'S OWN SCALE (scale_cents, _note_class_and_pitch): the tonic the
    // table's tonic note x the sounding octaves x the bend x the octave
    // tuning, in that order; a degree the scale has, the tonic x its cents
    double scaled(long long c, int note, double on, const NoteClass *K, double f0) const
    {
        const int st = K->scale_tonic;
        double tonic = note_table(c, on, K->indian != 0)[st] * (K->sounding_oct != 0.0 ? pow(2.0, K->sounding_oct) : 1.0);
        auto b = btun.find(c);
        tonic = tonic * ((b != btun.end() && b->second != 0.0) ? b->second : 1.0);
        auto o = otun.find(c);
        tonic = tonic * ((o != otun.end() && !o->second.empty()) ? pow(2.0, o->second[st % 12] / 1200.0) : 1.0);
        for (int q = 0; q < K->scale_n; q++)
            if (K->scale_off[q] == note - st)
                return tonic * pow(2.0, K->scale_c[q] / 1200.0);
        return f0;
    }

    double pitch(long long c, int note, double on, bool indian = false, double so = 0.0) const
    {
        double f0 = note_table(c, on, indian)[note];
        auto me = meend.find(NoteKey{c, note, on});
        if (me != meend.end())
            f0 *= me->second.first;         // this note's meend at Note On
        if (so != 0.0)
            f0 *= pow(2.0, so);             // its voice's sounding octaves (a helicopter's rotor)
        auto b = btun.find(c);
        if (b != btun.end() && b->second != 0.0)
            f0 *= b->second;
        auto o = otun.find(c);
        if (o != otun.end() && !o->second.empty())
            f0 *= pow(2.0, o->second[note % 12] / 1200.0);
        return f0;
    }

    const Channel *get(long long c) const
    {
        auto it = ch.find(c);
        return it == ch.end() ? nullptr : &it->second;
    }

    // _note_pedal, the sostenuto and all sound off on a note's key-up (the
    // one-shot extension and the choke are the caller's): its end.
    // damper_pedal: the voice has dampers; mcut: a mono note cut by the next.
    // *band: a half-pedalled note that meets the band (its damper track is
    // the caller's).
    double note_off(long long c, int note, double on, double off, bool damper_pedal, bool mcut,
                    double retrigger_fade, bool *band) const
    {
        *band = false;
        const Channel *C = get(c);
        auto nx_it = next_same.find(NoteKey{c, note, on});
        bool has_nx = nx_it != next_same.end();
        double nx = has_nx ? nx_it->second : 0.0;
        if (damper_pedal && !mcut && C && !C->pv_t.empty()) {
            const int top = 128;
            double land = C->damper_lands(off, note, top, total, band);
            if (has_nx && land > off)
                land = pymin(land, pymax(off, nx - retrigger_fade));
            if (!(land > off))
                *band = false;
            off = pymax(off, land);
        } else if (damper_pedal && !mcut) {
            double rel = C ? C->damper_falls(off) : off;
            if (rel > off) {
                if (has_nx)
                    rel = pymin(rel, pymax(off, nx - retrigger_fade));
                off = rel;
            }
        }
        auto sh = sost_held.find(NoteKey{c, note, on});
        if (sh != sost_held.end() && sh->second > off && damper_pedal && !mcut) {
            double h = sh->second;
            if (has_nx)
                h = pymin(h, pymax(off, nx - retrigger_fade));
            off = pymax(off, h);
        }
        bool has_sf = false;
        double sf = C ? C->sound_off(on, &has_sf) : 0.0;
        if (has_sf && sf < off)
            off = pymax(on + retrigger_fade, sf);
        return off;
    }
};

}  // namespace nv

extern "C" {

void *nv_song_new(void) { return new nv::Song(); }
void nv_song_free(void *s) { delete (nv::Song *)s; }

void nv_song_cc(void *s, long long ch, double t, int cc, int v)
{
    ((nv::Song *)s)->ch[ch].ccs.push_back(nv::CC{t, cc, v});
}

void nv_song_note(void *s, long long ch, int note, double on, double off, int vel, double v7, double v11,
                  double pan, double trim, int prog, int drum)
{
    ((nv::Song *)s)->notes.push_back(nv::Ev{ch, note, on, off, vel, v7, v11, pan, trim, prog, drum});
    ((nv::Song *)s)->wkeys[ch].push_back(note);
}

int nv_song_n_notes(void *s) { return (int)((nv::Song *)s)->notes.size(); }

// _prep_choir_parts' _tess: a channel's median key (the upper of two), in Hz
double nv_song_tess(void *s, long long ch)
{
    auto it = ((nv::Song *)s)->wkeys.find(ch);
    if (it == ((nv::Song *)s)->wkeys.end())
        return 0.0;
    std::vector<int> k = it->second;
    if (k.empty())
        return 0.0;
    std::sort(k.begin(), k.end());
    return 440.0 * pow(2.0, (k[k.size() / 2] - 69) / 12.0);
}

void nv_song_set_part(void *s, long long ch, int part) { ((nv::Song *)s)->parts[ch] = part; }

void nv_song_note_mono(void *s, int i, int mcut, int mslur)
{
    nv::Song *S = (nv::Song *)s;
    if (i >= 0 && i < (int)S->notes.size()) {
        S->notes[i].mcut = mcut;
        S->notes[i].mslur = mslur;
    }
}

void nv_song_gliss(void *s, const NoteClass *const *K) { ((nv::Song *)s)->gliss(K); }

int nv_song_drones(void *s, const NoteClass *const *K) { return ((nv::Song *)s)->drones(K); }

int nv_song_gliss_note(void *s, int i, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->notes.size() || !S->notes[i].gl)
        return 0;
    const nv::Ev &e = S->notes[i];
    out[0] = e.gl_lv; out[1] = e.gl_sm; out[2] = e.gl_prev; out[3] = e.gl_dt;
    return 1;
}

int nv_song_mono(void *s, int i, int *mcut, int *mslur)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->notes.size())
        return 0;
    *mcut = S->notes[i].mcut;
    *mslur = S->notes[i].mslur;
    return 1;
}

int nv_song_part(void *s, long long ch)
{
    const auto &m = ((nv::Song *)s)->parts;
    auto it = m.find(ch);
    return it == m.end() ? 0 : it->second;
}

// a sound controller (CC71-78) on channel ch at t, in the file's order; ch -1
// and cc -1: GM System On or GS Reset, every channel's back to 64
void nv_song_snd(void *s, long long ch, double t, int cc, int v)
{
    ((nv::Song *)s)->snd.push_back(nv::Song::Snd{ch, t, cc, v});
}

// whether channel ch has a sound controller of its own (CC71-78, or GS's
// sound NRPNs): a Moog there turns its knobs (moog.apply_gm, Python's)
int nv_song_snd_any(void *s, long long ch)
{
    for (const nv::Song::Snd &e : ((nv::Song *)s)->snd)
        if (e.ch == ch && e.cc >= 0)
            return 1;
    return 0;
}

// _kn_moves: whether channel ch's cutoff or resonance (CC74, CC71) changes
// after it is first set -- events at more than one time (to the microsecond)
int nv_song_snd_moves(void *s, long long ch)
{
    std::set<std::string> ts;           // (round(t, 6): the exact value's decimal, as %.6f is)
    for (const nv::Song::Snd &e : ((nv::Song *)s)->snd)
        if (e.ch == ch && (e.cc == 71 || e.cc == 74)) {
            char b[64];
            snprintf(b, sizeof b, "%.6f", e.t);
            ts.insert(b);
        }
    return ts.size() > 1;
}

// A MOOG NOTE's layer's filter row (moog.ft_row, its slot 9 the layer's), on
// channel ch with knob row kn: the knob row found or added for the channel
// (_MOOG_KROW) and set in slot 9, the filter row added. The next filter row's
// index, before: nv_song_moog_n
int nv_song_moog_n(void *s) { return (int)((nv::Song *)s)->mft.size(); }

// a Moog row's 30 values (FT), 0 where there is no row i
int nv_song_moog_ft(void *s, int i, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->mft.size())
        return 0;
    for (int j = 0; j < 30; j++)
        out[j] = S->mft[i][j];
    return 1;
}

void nv_song_moog_add(void *s, long long ch, const double *ft, const double *kn, const MoogLayer *L, double a0,
                      double toff, double end)
{
    nv::Song *g = (nv::Song *)s;
    g->mlay.push_back(L);
    g->mspan.push_back({a0, toff, end});
    std::array<double, 9> k;
    std::copy(kn, kn + 9, k.begin());
    auto key = std::make_pair(ch, k);
    auto it = g->mkrow.find(key);
    int row;
    if (it == g->mkrow.end()) {
        row = (int)g->mkn.size();
        g->mkrow[key] = row;
        g->mkn.push_back(k);
    } else {
        row = it->second;
    }
    std::array<double, 30> f;
    std::copy(ft, ft + 30, f.begin());
    f[9] = (double)row;
    g->mft.push_back(f);
}

// ...A MOVING CHANNEL's (_kn_moves): the filter row on the knob row of its
// channel, class (cls) and layer, made the first time -- the base panel L's
// knobs as the channel's sound controls stand at 0 and at each of its
// events and GM resets (_kn_at: their offsets and the class's bias, those it
// answers, mask), each at its grid point (int(t * sr) // 128)
void nv_song_moog_add_moving(void *s, long long ch, const double *ft, const MoogLayer *L, const void *cls,
                             int layer, const double *bias, int mask, double sr, double a0, double toff, double end)
{
    nv::Song *g = (nv::Song *)s;
    auto key = std::make_tuple(ch, cls, layer);
    auto it = g->mkmove.find(key);
    int row;
    if (it == g->mkmove.end()) {
        auto kn_at = [&](double t) {
            double d[8];
            g->sound_at(ch, t, d);
            for (int q = 0; q < 8; q++) {
                d[q] += bias[q];
                if (!((mask >> q) & 1))
                    d[q] = 0.0;
            }
            MoogLayer La;
            nv_moog_apply(L, d, &La);
            std::array<double, 9> k;
            std::copy(La.kn, La.kn + 9, k.begin());
            return k;
        };
        std::set<double> ts;
        bool own = false;
        for (const nv::Song::Snd &e : g->snd)
            own = own || e.ch == ch;
        for (const nv::Song::Snd &e : g->snd)
            if (e.ch == ch || (own && e.ch == -1 && e.cc == -1))
                ts.insert(e.t);
        row = (int)g->mkn.size();
        g->mkmove[key] = row;
        std::array<double, 9> k0 = kn_at(0.0);
        g->mkn.push_back(k0);
        auto &tl = g->mkvar[row];
        tl.push_back(std::make_pair(0LL, k0));
        for (double t : ts)
            tl.push_back(std::make_pair((long long)(t * sr) / 128, kn_at(t)));
    } else {
        row = it->second;
    }
    g->mlay.push_back(L);
    g->mspan.push_back({a0, toff, end});
    std::array<double, 30> f;
    std::copy(ft, ft + 30, f.begin());
    f[9] = (double)row;
    g->mft.push_back(f);
}

// A NOTE'S LAYER THROUGH THE MF-104M (_MF104): its rows [r0, r1) and its panel;
// the i-th of them (returns 0 past the last; i < 0: how many)
void nv_song_add_mf104(void *s, long long r0, long long r1, const MoogLayer *L)
{
    ((nv::Song *)s)->mf104.push_back(nv::Song::Mf{r0, r1, L});
}

int nv_song_mf104(void *s, int i, long long *r0, long long *r1, const MoogLayer **L)
{
    nv::Song *g = (nv::Song *)s;
    if (i < 0)
        return (int)g->mf104.size();
    if (i >= (int)g->mf104.size())
        return 0;
    *r0 = g->mf104[i].r0;
    *r1 = g->mf104[i].r1;
    *L = g->mf104[i].L;
    return 1;
}

// filter row i's panel (*L) and its note's onset, release and end (a0t[3])
int nv_song_moog_rows(void *s, int i, const MoogLayer **L, double *a0t)
{
    nv::Song *g = (nv::Song *)s;
    if (i < 0 || i >= (int)g->mlay.size())
        return 0;
    *L = g->mlay[i];
    for (int q = 0; q < 3; q++)
        a0t[q] = g->mspan[i][q];
    return 1;
}

// the filter rows and knob rows as the kernel reads them (float32, flat):
// how many filter rows, knob rows, and each knob row's entries (knk, from
// grid point kb0: one, a table with no moving row) -- a moving row's from
// its first change to the last of any (blockrender's KN), a constant row
// the same entry throughout; out NULL just counts
int nv_song_moog_tables(void *s, float *ft, float *kn, int *nkn, long *knk, long *kb0)
{
    nv::Song *g = (nv::Song *)s;
    long k0 = 0, nk = 1;
    if (!g->mkvar.empty()) {
        long long lo = 0, hi = 0;
        bool first = true;
        for (auto &rv : g->mkvar)
            for (size_t q = 1; q < rv.second.size(); q++) {
                long long gp = rv.second[q].first;
                lo = first || gp < lo ? gp : lo;
                hi = first || gp > hi ? gp : hi;
                first = false;
            }
        k0 = (long)std::max(0LL, lo - 1);
        nk = (long)(hi - k0 + 1);
    }
    if (ft)
        for (size_t r = 0; r < g->mft.size(); r++)
            for (int j = 0; j < 30; j++)
                ft[30 * r + j] = (float)g->mft[r][j];
    if (kn) {
        for (size_t r = 0; r < g->mkn.size(); r++)
            for (long e = 0; e < nk; e++)
                for (int j = 0; j < 9; j++)
                    kn[(r * nk + e) * 9 + j] = (float)g->mkn[r][j];
        for (auto &rv : g->mkvar) {
            const auto &tl = rv.second;
            float *row = kn + (size_t)rv.first * nk * 9;
            std::array<double, 9> cur = tl[0].second;
            for (auto &e : tl)
                if (e.first <= k0)
                    cur = e.second;
            for (long e = 0; e < nk; e++)
                for (int j = 0; j < 9; j++)
                    row[e * 9 + j] = (float)cur[j];
            for (auto &e : tl)
                if (e.first > k0)
                    for (long x = e.first - k0; x < nk; x++)
                        for (int j = 0; j < 9; j++)
                            row[x * 9 + j] = (float)e.second[j];
        }
    }
    *nkn = (int)g->mkn.size();
    *knk = nk;
    *kb0 = k0;
    return (int)g->mft.size();
}

// CC71-78's d in force on channel ch at t (d[0] CC71's), 0 none
void nv_song_sound(void *s, long long ch, double t, double *d) { ((nv::Song *)s)->sound_at(ch, t, d); }

// numpy's default_rng(seed).standard_normal(n) (native/npyrandom.c)
extern "C" void nv_npy_normals(unsigned long long seed, long n, double *out);

// A REGISTERED ORGAN on channel ch (_prep_organ_rows, in its order: the
// channels as ch_progs has them, each its organs as its programs bring
// them), its table spec; prog_organ[program]: each program's organ, NULL
// none (the recalls). Its registration's events, from the finished song
void nv_song_organ(void *s, long long ch, const OrganSpec *spec, const OrganSpec *const *prog_organ)
{
    nv::Song *S = (nv::Song *)s;
    for (int p = 0; p < 128; p++)
        S->prog_organ[p] = prog_organ[p];
    S->organ_add(ch, spec, prog_organ);
}

int nv_song_n_organs(void *s) { return (int)((nv::Song *)s)->organs.size(); }

// whether an organ's tremolo would sound -- its Tremolo stop drawn at any
// time, or its wheel's on a channel that moves CC1 (tremolo.expand, Python's)
int nv_song_organ_tremolo(void *s)
{
    nv::Song *S = (nv::Song *)s;
    for (const auto &o : S->organs) {
        if (o.spec->htrem_rank >= 0)
            for (auto &x : o.rank_ev[o.spec->htrem_rank])
                if (x.second >= 0.5)
                    return 1;
        int v;
        if (o.spec->wheel_trem > 0.0 && nv_song_first_cc(s, o.ch, 1, &v))
            return 1;
    }
    return 0;
}

// note i's program trim (the factor its channel volume carries)
double nv_song_note_trim(void *s, int i) { return ((nv::Song *)s)->notes[i].trim; }
int nv_song_n_grows(void *s) { return ((nv::Song *)s)->n_grows; }

// the wind rows from row0 (_prep_chest_wind's channels, a row a family): how many
int nv_song_organ_wind_rows(void *s, int row0) { return ((nv::Song *)s)->organ_wind_rows(row0); }

// THE ORGANS' ROWS, the song's length known: each rank's gate and each
// organ's swell (onepole_blocks of their events, nblk each, in G and S);
// sh the swell law (_prep_swell_law: the first organ's whose floor is under
// 1, else the last's; sh left as given with none) -- ONE LAW A RENDER, EVERY
// ORGAN ITS OWN LEVEL: an organ whose law is another has its row re-mapped
// so the law gives the level its own would,
//     L = f_i + (1 - f_i) s^p_i,   s' = ((L - f_g) / (1 - f_g))^(1/p_g)
// (open where the law has no range)
int nv_song_organ_rows(void *s, long nblk, int blk, double sr, double tau, float *G, float *S, double *sh)
{
    nv::Song *Sg = (nv::Song *)s;
    const double *law = nullptr, *first = nullptr;
    std::vector<std::pair<long, const double *>> laws;      // (its swell row, its law), in the organs' order
    for (const auto &o : Sg->organs) {
        for (int ri = 0; ri < o.spec->n_rank; ri++)
            nv::Song::onepole(o.rank_ev[ri], nblk, blk, sr, tau, G + (long)(o.g0 + ri) * nblk);
        nv::Song::onepole(o.swell_ev, nblk, blk, sr, tau, S + (long)o.cr * nblk);
        if (!o.spec->swells)
            continue;
        law = o.spec->swell_law;
        laws.emplace_back((long)o.cr, law);
        if (!first && law[0] < 1.0)
            first = law;
    }
    const double *use = first ? first : law;
    if (use) {
        for (int q = 0; q < 4; q++)
            sh[q] = use[q];
        const double fg = use[0], pg = use[1];
        auto clip = [](double x) { return x < 0.0 ? 0.0 : (x > 1.0 ? 1.0 : x); };
        for (auto &lw : laws) {
            const double fi = lw.second[0], pi = lw.second[1];
            if (fi == fg && pi == pg)
                continue;
            float *row = S + lw.first * nblk;
            for (long q = 0; q < nblk; q++) {
                double L = fi + (1.0 - fi) * pow(clip((double)row[q]), pi);
                row[q] = fg < 1.0 ? (float)pow(clip((L - fg) / (1.0 - fg)), 1.0 / pg) : 1.0f;
            }
        }
    }
    return 0;
}

static double wind_sat(double x, double m) { return m > 0.0 ? m * tanh(x / m) : x; }

// THE CHEST'S WIND (_prep_chest_wind, wind.Wind.blocks, wind.pitch_level):
// for each channel organ_wind_rows gave rows, its pipes' demand under their
// gates (G), the pressure block by block -- the wander (numpy's normals,
// seeded by the channel), the sag and the regulator, the Tremulant -- and a
// row a family: its ratio (BR, nblk), its phase (BC, nblk) and its level at
// the block edges (BL, nblk + 1), in organ_wind_rows' order
void nv_song_organ_wind(void *s, long nblk, int blk, double sr, const float *G, float *BR, double *BC, float *BL)
{
    nv::Song *Sg = (nv::Song *)s;
    std::set<long long> seen;
    int row = 0;
    for (const auto &o : Sg->organs) {
        if (seen.count(o.ch))
            continue;
        seen.insert(o.ch);
        const OrganSpec *sp = o.spec;
        int any = 0;
        for (int ri = 0; ri < sp->n_rank; ri++)
            any |= o.wrow[ri] >= 0;
        if (!any)
            continue;
        // the demand: every note of this organ's class on the channel, each rank under its gate
        std::vector<double> dem(nblk + 1, 0.0);
        for (const auto &e : Sg->notes) {
            if (e.ch != o.ch || e.drum || e.prog < 0 || e.prog > 127 || Sg->prog_organ[e.prog] != sp)
                continue;
            double f = 440.0 * pow(2.0, (e.note - 69) / 12.0);
            long b0 = std::min(nblk, (long)(e.on * sr / blk)), b1 = std::min(nblk, (long)(e.off * sr / blk) + 1);
            if (b1 <= b0)
                continue;
            for (int ri = 0; ri < sp->n_rank; ri++) {
                const OrganRank &rk = sp->rank[ri];
                if (rk.n_ratio == 0)
                    continue;
                double d[8];
                for (int q = 0; q < rk.n_ratio; q++)
                    d[q] = pow(std::max(f * rk.ratio[q], 8.0) / sp->unit_hz, sp->draw_exp);
                double w = pysum(d, rk.n_ratio);
                const float *g = G + (long)(o.g0 + ri) * nblk;
                float wf = (float)w;        // (numpy: a Python float times a float32 row is float32)
                for (long b = b0; b < b1; b++)
                    dem[b] += (double)(wf * g[b]);
            }
        }
        // the Tremulant's draw, a step a block
        std::vector<double> trem(nblk, 0.0);
        if (sp->trem_rank >= 0)
            for (auto &e : o.rank_ev[sp->trem_rank])
                for (long b = 0; b < nblk; b++)
                    if (((double)b + 0.5) * blk / sr >= e.first)
                        trem[b] = e.second;
        // the pressure (Wind.blocks), SUB 8 points a block
        std::vector<double> p((size_t)nblk * 9);
        std::vector<double> noise;
        if (sp->wander_rms > 0.0) {
            noise.resize(nblk);
            nv_npy_normals(0x5EED + (unsigned long long)o.ch, nblk, noise.data());
        }
        double w1 = 0.0, w2 = 0.0, s1 = 0.0, s2 = 0.0, d1 = 0.0, r1 = 0.0, te = 0.0, tph = 0.0;
        bool was_on = false;
        auto dev = [&]() {
            double d = s1 - (sp->has_ra ? sp->reg_restore * r1 : 0.0);
            return wind_sat(d, sp->sag_max);
        };
        for (long b = 0; b < nblk; b++) {
            double w0 = w2;
            if (!noise.empty()) {
                w1 = sp->wa * w1 + (1.0 - sp->wa) * noise[b];
                w2 = sp->wa * w2 + (1.0 - sp->wa) * w1;
            }
            double s0 = dev();
            if (sp->sag_per_unit > 0.0) {
                double sn = sp->c1 * s1 + sp->c2 * s2 + sp->g * d1;
                s2 = s1;
                s1 = sn;
                d1 = dem[b] * sp->sag_per_unit;
                if (sp->has_ra)
                    r1 = sp->ra * r1 + (1.0 - sp->ra) * s1;
            }
            double sv1 = dev();
            bool on = trem[b] >= 0.5;
            if (on && !was_on && te < 1e-4)
                tph = 0.0;
            was_on = on;
            double tgt = on ? 1.0 : 0.0;
            double e0 = te;
            te = tgt + (te - tgt) * sp->tdecay;
            if (!on && te < 1e-6)
                te = 0.0;
            bool tr = e0 > 0.0 || te > 0.0;
            for (int j = 0; j <= 8; j++) {
                double fr = j / 8.0;
                double wv = (w0 + (w2 - w0) * fr) * (sp->wgain * sp->wander_rms);
                double sv = s0 + (sv1 - s0) * fr;
                double tv = 0.0;
                if (tr) {
                    double ev = e0 + (te - e0) * fr;
                    tv = sp->trem_depth * ev * sin(2.0 * M_PI * (tph + sp->trem_hz * sp->blk_s * fr));
                }
                p[(size_t)b * 9 + j] = 1.0 + wv - sv + tv;
            }
            tph = fmod(tph + sp->trem_hz * sp->blk_s, 1.0);
        }
        // a row a family (pitch_level): the ratio, its phase, the level at the edges
        std::vector<std::pair<double, double>> fams;
        for (int ri = 0; ri < sp->n_rank; ri++) {
            if (o.wrow[ri] < 0)
                continue;
            std::pair<double, double> ab(sp->fam_a[ri], sp->fam_b[ri]);
            if (std::find(fams.begin(), fams.end(), ab) != fams.end())
                continue;
            fams.push_back(ab);
            float *R = BR + (long)row * nblk;
            double *Cc = BC + (long)row * nblk;
            float *L = BL + (long)row * (nblk + 1);
            double acc = 0.0;
            for (long b = 0; b < nblk; b++) {
                double sum = pow(p[(size_t)b * 9], ab.first);
                for (int j = 1; j < 8; j++)
                    sum = sum + pow(p[(size_t)b * 9 + j], ab.first);
                R[b] = (float)(sum / 8.0);
                Cc[b] = acc;
                acc += ((double)R[b] - 1.0) * blk;
                L[b] = (float)pow(p[(size_t)b * 9], ab.second);
            }
            L[nblk] = (float)pow(p[(size_t)(nblk - 1) * 9 + 8], ab.second);
            row++;
        }
    }
}

// AN ORGAN NOTE'S RANKS (note i of the song; its organ's family): each
// rank's gate row, when it speaks (rank_speak_sec), whether it is drawn only
// after the key lifted, or pushed in before the key-up, and its bend row --
// its chest's wind where it has one, else the note's own (n->br); the swell
// row. 0 if its channel has no such organ
int nv_song_organ_note(void *s, int i, int family, NoteIn *n)
{
    const nv::Song *S = (nv::Song *)s;
    const nv::Ev &e = S->notes[i];
    const nv::Song::Organ *o = S->organ_of(e.ch, family);
    if (!o)
        return 0;
    double on = n->on, koff = n->key_off, br = n->br;
    for (int ri = 0; ri < o->spec->n_rank; ri++) {
        const auto &ev = o->rank_ev[ri];
        n->rank_gr[ri] = o->g0 + ri;
        // rank_speak_sec(events, on, 0.0)
        double cur = 0.0;
        for (auto &x : ev) {
            if (x.first <= on)
                cur = x.second;
            else
                break;
        }
        double sp = NAN;
        if (cur >= 0.5)
            sp = on + 0.0;
        else
            for (auto &x : ev)
                if (x.first > on && x.second >= 0.5) {
                    sp = x.first + 0.0;
                    break;
                }
        n->rank_sp[ri] = sp;
        n->rank_skip[ri] = !std::isnan(sp) && sp > on && sp >= koff;
        if (o->spec->rank[ri].only_drawn) {     // (nothing until its channel draws it: not there at all)
            bool any = false;
            for (auto &x : ev)
                any = any || x.second >= 0.5;
            if (!any)
                n->rank_skip[ri] = 1;
        }
        double doff = 0.0;                      // (drawn at the key-up: its jack clicks)
        for (auto &x : ev) {
            if (x.first <= koff)
                doff = x.second;
            else
                break;
        }
        n->rank_drawn_off[ri] = doff >= 0.5;
        n->rank_rel1[ri] = 0;
        if (!std::isnan(sp)) {
            double drawn = 0.0;
            for (auto &x : ev) {
                if (x.first <= koff)
                    drawn = x.second;
                else
                    break;
            }
            n->rank_rel1[ri] = drawn < 0.5;
        }
        // (em.bend_row: a rank with pipes and the note in its range takes its
        // wind's row, and every rank after keeps it until the next does)
        const OrganRank &rk = o->spec->rank[ri];
        if (rk.n_ratio && e.note >= rk.lo && e.note <= rk.hi && o->wrow[ri] >= 0)
            br = (double)o->wrow[ri];
        n->rank_br[ri] = br;
    }
    n->organ_cr = o->cr;
    // a reed organ's effect stops at its onset (stop_drawn_at): the
    // Expression's bellows (the note's CC11), the Percussion
    auto drawn_at = [&](int ri) {
        if (ri < 0)
            return false;
        double cur = 0.0;
        for (auto &x : o->rank_ev[ri]) {
            if (x.first <= on)
                cur = x.second;
            else
                break;
        }
        return cur >= 0.5;
    };
    n->organ_hx = drawn_at(o->spec->expr_rank) ? e.v11 : NAN;
    n->organ_perc = drawn_at(o->spec->perc_rank);
    // ...and its Tremolo stop (_HTREM_CH: the notes struck with it drawn)
    if (S->htrem_note.size() < S->notes.size())
        S->htrem_note.resize(S->notes.size(), 0);
    S->htrem_note[i] = o->spec->expr_rank >= 0 && o->spec->htrem_depth > 0.0 && drawn_at(o->spec->htrem_rank);
    return 1;
}

// A LESLIE'S CHANNEL, as its first note on a rotating speaker arrives (kind:
// 1 starting on chorale, 2 on tremolo); a channel already there is left
void nv_song_add_leslie(void *s, long long ch, int kind)
{
    nv::Song *S = (nv::Song *)s;
    for (const auto &x : S->leslie)
        if (x.first == ch)
            return;
    S->leslie.push_back(std::make_pair(ch, kind));
}

// AN AMPLIFIER'S CHANNEL, as its first amplified note arrives (its voice's
// amp_drive, and whether the voice is on a rotor); a channel already there is left
void nv_song_add_amp(void *s, long long ch, double drive, int rotor, double reference, double imbalance)
{
    nv::Song *S = (nv::Song *)s;
    for (const auto &x : S->amp)
        if (x.first == ch)
            return;
    S->amp.push_back(std::make_pair(ch, std::make_pair(drive, rotor)));
    S->amp_cfg.push_back(std::make_pair(reference, imbalance));
}

// the amplifier channel k's reference peak (0 none) and its valve's imbalance
void nv_song_amp_cfg(void *s, int k, double *reference, double *imbalance)
{
    const nv::Song *S = (nv::Song *)s;
    *reference = S->amp_cfg[k].first;
    *imbalance = S->amp_cfg[k].second;
}

// the amplifier channel k's drive (*ch, *rotor), or how many with k < 0
double nv_song_amp(void *s, int k, long long *ch, int *rotor)
{
    const nv::Song *S = (nv::Song *)s;
    if (k < 0)
        return (double)S->amp.size();
    *ch = S->amp[k].first;
    *rotor = S->amp[k].second.second;
    return S->amp[k].second.first;
}

// A VOICE'S TREMOLO on a channel (rate, depth, stereo, scatter), the first
// to arrive; a channel already set is left
void nv_song_add_trem(void *s, long long ch, const double *cfg)
{
    nv::Song *S = (nv::Song *)s;
    for (const auto &x : S->trems)
        if (x.first == ch)
            return;
    S->trems.push_back(std::make_pair(ch, std::vector<double>(cfg, cfg + 4)));
}

// A CABINET on a channel (its first note's voice's); a channel already set is left
void nv_song_add_cab(void *s, long long ch, const NoteClass *k)
{
    nv::Song *S = (nv::Song *)s;
    for (const auto &x : S->cabs)
        if (x.first == ch)
            return;
    S->cabs.push_back(std::make_pair(ch, k));
}

// A CLAVINET's TONE ROCKERS on a channel (CLAV_TONE's index); a channel already set is left
void nv_song_add_clav(void *s, long long ch, int setting)
{
    nv::Song *S = (nv::Song *)s;
    for (const auto &x : S->clavs)
        if (x.first == ch)
            return;
    S->clavs.push_back(std::make_pair(ch, setting));
}

// the rockers: channels and settings; how many
int nv_song_clavs(void *s, long long *ch, int *setting, int cap)
{
    const nv::Song *S = (nv::Song *)s;
    int n = (int)S->clavs.size();
    for (int q = 0; q < n && q < cap; q++) {
        ch[q] = S->clavs[q].first;
        setting[q] = S->clavs[q].second;
    }
    return n;
}

// the cabinets: channels and the classes carrying them; how many
int nv_song_cabs(void *s, long long *ch, const NoteClass **k, int cap)
{
    const nv::Song *S = (nv::Song *)s;
    int n = (int)S->cabs.size();
    for (int q = 0; q < n && q < cap; q++) {
        ch[q] = S->cabs[q].first;
        k[q] = S->cabs[q].second;
    }
    return n;
}

// the voices' tremolos: channels and (rate, depth, stereo, scatter) each; how many
int nv_song_trems(void *s, long long *ch, double *cfg, int cap)
{
    const nv::Song *S = (nv::Song *)s;
    int n = (int)S->trems.size();
    for (int q = 0; q < n && q < cap; q++) {
        ch[q] = S->trems[q].first;
        std::copy(S->trems[q].second.begin(), S->trems[q].second.end(), cfg + 4 * q);
    }
    return n;
}

// the Leslie channel k's (its kind; *ch), or how many with k < 0
int nv_song_leslie(void *s, int k, long long *ch)
{
    const nv::Song *S = (nv::Song *)s;
    if (k < 0)
        return (int)S->leslie.size();
    *ch = S->leslie[k].first;
    return S->leslie[k].second;
}

// a channel's controller cc, in order (in_order): times and values, how many
int nv_song_ccs(void *s, long long ch, int cc, double *t, int *v, int cap)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    int n = 0;
    if (!C)
        return 0;
    for (const nv::CC &e : C->ccs)
        if (e.cc == cc) {
            if (n < cap) {
                t[n] = e.t;
                v[n] = e.v;
            }
            n++;
        }
    return n;
}

// note i struck with its reed organ's Tremolo stop drawn
int nv_song_htrem(void *s, int i)
{
    const nv::Song *S = (nv::Song *)s;
    return i >= 0 && i < (int)S->htrem_note.size() && S->htrem_note[i];
}

void nv_song_add_htrem_rows(void *s, long long a, long long b)
{
    ((nv::Song *)s)->htrem_rows.push_back(std::make_pair(a, b));
}

// the stop's rows, [first, end) a note (ab: 2 each), how many
int nv_song_n_htrem_rows(void *s, long long *ab, int cap)
{
    const nv::Song *S = (nv::Song *)s;
    int n = (int)S->htrem_rows.size();
    for (int q = 0; q < n && q < cap; q++) {
        ab[2 * q] = S->htrem_rows[q].first;
        ab[2 * q + 1] = S->htrem_rows[q].second;
    }
    return n;
}

// THE ORGANS' TREMOLOS (tremolo.expand's channels), each channel's
// (rate, depth, stereo, scatter) in cfg (4 a channel, ch[] its channel):
// which = 0 the Tremolo stops' (_HTREM_CH: the stop's rate and depth, mono),
// 1 the wheels' (_note_tremolo: the voice's tremolo at its depth times the
// channel's first CC1, none without one). How many.
int nv_song_organ_tremolos(void *s, int which, int *ch, double *cfg, int cap)
{
    nv::Song *S = (nv::Song *)s;
    int n = 0;
    for (const auto &o : S->organs) {
        const OrganSpec *sp = o.spec;
        double hz = 0.0, dep = 0.0, st = 0.0, sc = 0.0;
        if (which == 0) {
            if (sp->expr_rank < 0 || sp->htrem_depth <= 0.0)
                continue;
            hz = sp->htrem_hz;
            dep = sp->htrem_depth;
        } else {
            int v;
            if (sp->wheel_trem <= 0.0 || !nv_song_first_cc(s, o.ch, 1, &v))
                continue;
            hz = sp->wtrem_hz;
            dep = sp->wheel_trem * (v / 127.0);
            st = sp->wtrem_stereo ? 1.0 : 0.0;
            sc = sp->wtrem_scatter;
            if (dep <= 0.0)
                continue;
        }
        if (n < cap) {
            ch[n] = (int)o.ch;
            cfg[4 * n] = hz; cfg[4 * n + 1] = dep; cfg[4 * n + 2] = st; cfg[4 * n + 3] = sc;
        }
        n++;
    }
    return n;
}

// note i's glide: the key it glides from (-1 none), and through *cc5 the CC5 in force at its onset
int nv_song_glide(void *s, int i, int *cc5)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->glide_src.size() || S->glide_src[i] < 0)
        return -1;
    *cc5 = S->cc5_at(S->notes[i].ch, S->notes[i].on);
    return S->glide_src[i];
}

// note i one of a gesture's strokes (_stroked)
int nv_song_stroked(void *s, int i) { return ((nv::Song *)s)->notes[i].stroked; }

// a jack's click rows, [first, end), its rank and offset (rel_jacks)
void nv_song_add_rel_jack(void *s, long long a, long long b, int rank, double jo)
{
    std::vector<double> &v = ((nv::Song *)s)->rel_jacks;
    v.push_back((double)a); v.push_back((double)b); v.push_back((double)rank); v.push_back(jo);
}

// a note's grains' rows, [first, end) (_GRAIN_ROWS); and all of them, n pairs into ab (NULL: count)
void nv_song_add_grain_rows(void *s, long long a, long long b)
{
    std::vector<long long> &v = ((nv::Song *)s)->grain_rows;
    v.push_back(a);
    v.push_back(b);
}

int nv_song_n_grain_rows(void *s, long long *ab, int cap)
{
    const std::vector<long long> &v = ((nv::Song *)s)->grain_rows;
    int n = (int)(v.size() / 2);
    for (int k = 0; ab && k < n && k < cap; k++) {
        ab[2 * k] = v[2 * k];
        ab[2 * k + 1] = v[2 * k + 1];
    }
    return n;
}

// a note's key-up rows, [first, end) (rel_rows)
void nv_song_add_rel_rows(void *s, long long a, long long b)
{
    std::vector<long long> &v = ((nv::Song *)s)->rel_rows;
    v.push_back(a);
    v.push_back(b);
}

int nv_song_n_rel_rows(void *s, long long *out, int cap)
{
    const std::vector<long long> &v = ((nv::Song *)s)->rel_rows;
    int n = (int)v.size() / 2;
    for (int k = 0; k < 2 * n && k < 2 * cap; k++)
        out[k] = v[k];
    return n;
}

int nv_song_n_rel_jacks(void *s, double *out, int cap)
{
    const std::vector<double> &v = ((nv::Song *)s)->rel_jacks;
    int n = (int)v.size() / 4;
    for (int k = 0; k < 4 * n && k < 4 * cap; k++)
        out[k] = v[k];
    return n;
}

// a note's push rows, [first, end), as nv_play made them (push_rows)
void nv_song_add_push_rows(void *s, long long a, long long b)
{
    ((nv::Song *)s)->push_rows.push_back(std::make_pair(a, b));
}

int nv_song_n_push_rows(void *s, long long *ab, int cap)
{
    const nv::Song *S = (nv::Song *)s;
    int n = (int)S->push_rows.size();
    for (int k = 0; k < n && k < cap; k++) {
        ab[2 * k] = S->push_rows[k].first;
        ab[2 * k + 1] = S->push_rows[k].second;
    }
    return n;
}

// the stroke notes' rows, [first, end), as nv_prepare found them
void nv_song_add_stroke_rows(void *s, long long a, long long b)
{
    ((nv::Song *)s)->stroke_rows.push_back(std::make_pair(a, b));
}

int nv_song_n_stroke_rows(void *s, long long *ab, int cap)
{
    const nv::Song *S = (nv::Song *)s;
    int n = (int)S->stroke_rows.size();
    for (int k = 0; k < n && k < cap; k++) {
        ab[2 * k] = S->stroke_rows[k].first;
        ab[2 * k + 1] = S->stroke_rows[k].second;
    }
    return n;
}

// note i as given: (channel, key, velocity, program, drum) ints; (on, off) doubles
void nv_song_vars(void *s, int nent, const int *nls, const int *ls, const double *trim, const int *gs, const int *gm2)
{
    nv::Song *g = (nv::Song *)s;
    g->vls.assign(nent, {});
    g->vtrim.assign(trim, trim + nent);
    for (int e = 0, q = 0; e < nent; e++)
        for (int l = 0; l < nls[e]; l++, q++)
            g->vls[e].push_back(std::array<int, 4>{ls[4 * q], ls[4 * q + 1], ls[4 * q + 2], ls[4 * q + 3]});
    g->vgs.assign(gs, gs + 5 * 128 * 128);
    g->vgm2.assign(gm2, gm2 + 128 * 128);
}

int nv_song_note_bank(void *s, int bsel) { return ((nv::Song *)s)->bank(bsel); }

int nv_song_kidx(void *s, int i) { return ((nv::Song *)s)->notes[i].kidx(); }

int nv_song_tone(void *s, int i) { return ((nv::Song *)s)->notes[i].tone(); }

void nv_song_get_note(void *s, int i, long long *ch, int *iv, double *dv)
{
    const nv::Ev &e = ((nv::Song *)s)->notes[i];
    *ch = e.ch;
    iv[0] = e.note; iv[1] = e.vel; iv[2] = e.prog; iv[3] = e.drum;
    dv[0] = e.on; dv[1] = e.off;
}

// NOTE i's MIX CHANNEL (the note loop's em.channel, gsefx.TONE_SEG): a
// channel's first program keeps the channel, each other one heard on it --
// in the note loop's order (onset, channel, key), every note counted -- is
// ch + 256 x its place. What belongs to the TONE keys on it (an amp, a
// cabinet, a rotor, a tremolo, a scanner); what belongs to the part reads
// ch % 256 (gsefx.part_of)
long long nv_song_mix(void *s, int i)
{
    nv::Song *g = (nv::Song *)s;
    if (g->mix.size() != g->notes.size()) {
        size_t nn = g->notes.size();
        std::vector<int> order(nn);
        for (size_t q = 0; q < nn; q++)
            order[q] = (int)q;
        std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
            const nv::Ev &x = g->notes[a], &y = g->notes[b];
            if (x.on != y.on)
                return x.on < y.on;
            if (x.ch != y.ch)
                return x.ch < y.ch;
            return x.note < y.note;
        });
        g->mix.assign(nn, 0);
        std::map<long long, std::vector<int>> tones;
        for (int q : order) {
            const nv::Ev &e = g->notes[q];
            std::vector<int> &tl = tones[e.ch];
            size_t ti = std::find(tl.begin(), tl.end(), e.tone()) - tl.begin();
            if (ti == tl.size())
                tl.push_back(e.tone());
            g->mix[q] = e.ch + (ti ? 256LL * (long long)(ti % 256) : 0LL);
        }
    }
    return i >= 0 && i < (int)g->mix.size() ? g->mix[i] : -1;
}

// note i's pulse, a throat's (Ev: tilt, mouth, morph; NaN none)
void nv_song_note_voice(void *s, int i, double *out)
{
    const nv::Ev &e = ((nv::Song *)s)->notes[i];
    out[0] = e.tilt; out[1] = e.mouth; out[2] = e.morph;
}

// the held-key end the sostenuto gives this note, if it caught it
int nv_song_sost(void *s, long long ch, int note, double on, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    auto it = S->sost_held.find(nv::NoteKey{ch, note, on});
    if (it == S->sost_held.end())
        return 0;
    *out = it->second;
    return 1;
}

// _F: the channel's 128-key table at t
void nv_song_table(void *s, long long ch, double t, double *out)
{
    const std::vector<double> &tab = ((nv::Song *)s)->table(ch, t);
    for (int k = 0; k < 128; k++)
        out[k] = tab[k];
}

double nv_song_total(void *s) { return ((nv::Song *)s)->total; }

// the damper pedal's down/up spans (seconds), up to cap; the count
int nv_song_ped_spans(void *s, long long ch, double *out, int cap)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    if (!C)
        return 0;
    int n = (int)C->ped.size();
    for (int i = 0; i < n && i < cap; i++) {
        out[2 * i] = C->ped[i].first;
        out[2 * i + 1] = C->ped[i].second;
    }
    return n;
}

// a half-pedalled channel's CC64 (times, values), up to cap; 0 for a switch
int nv_song_pedal_values(void *s, long long ch, double *t, int *v, int cap)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    if (!C)
        return 0;
    int n = (int)C->pv_t.size();
    for (int i = 0; i < n && i < cap; i++) {
        t[i] = C->pv_t[i];
        v[i] = C->pv_v[i];
    }
    return n;
}

// damper.contact
double nv_damper_contact(int p, int key, int top) { return nv::damper::contact(p, key, top); }

// the channel's first value of controller cc in time order (in_order), if any
int nv_song_first_cc(void *s, long long ch, int cc, int *v)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    if (!C)
        return 0;
    for (const nv::CC &e : C->ccs)
        if (e.cc == cc) {
            *v = e.v;
            return 1;
        }
    return 0;
}

// the file's tuning (ch < 0, at 0) or a channel's MTS table from t
int nv_song_raga_sa(void *s) { return ((nv::Song *)s)->raga_sa; }

void nv_song_eastern(void *s, const double *freq_e, int raga_on, int sa, const double *sw, int nsw)
{
    nv::Song *S = (nv::Song *)s;
    S->freq_e.clear();
    if (freq_e)
        S->freq_e.assign(freq_e, freq_e + 128);
    S->raga_on = raga_on != 0;
    S->raga_sa = sa;
    S->raga_sw.assign(sw, sw + (nsw > 0 ? nsw : 0));
}

void *nv_song_sym_driver(void *s, long long mix, int size)
{
    nv::Song *S = (nv::Song *)s;
    if (S->sym_drv.count(mix))
        return nullptr;
    std::vector<unsigned char> &b = S->sym_drv[mix];
    b.assign((size_t)size, 0);
    return b.data();
}

const void *nv_song_sym_get(void *s, long long mix)
{
    nv::Song *S = (nv::Song *)s;
    auto it = S->sym_drv.find(mix);
    return it == S->sym_drv.end() ? nullptr : it->second.data();
}

void nv_song_sym_reset(void *s) { ((nv::Song *)s)->sym_drv.clear(); }

// a play's start (nv_play): the song's play-made rows as they were before the first
void nv_song_play_mark(void *s) { ((nv::Song *)s)->play_mark(); }

void nv_song_meend(void *s, long long ch, int note, double on, double r0, double row)
{
    ((nv::Song *)s)->meend[nv::NoteKey{ch, note, on}] = std::make_pair(r0, row);
}

int nv_song_meend_row(void *s, int i, double *row)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->notes.size())
        return 0;
    auto it = S->meend.find(nv::NoteKey{S->notes[i].ch, S->notes[i].note, S->notes[i].on});
    if (it == S->meend.end())
        return 0;
    *row = it->second.second;
    return 1;
}

int nv_song_has_eastern(void *s) { return !((nv::Song *)s)->freq_e.empty(); }
int nv_song_raga_sw(void *s, double *sw) {
    const nv::Song *S = (nv::Song *)s;
    if (!S->raga_on)
        return -1;
    for (size_t i = 0; i < S->raga_sw.size(); i++)
        sw[i] = S->raga_sw[i];
    return (int)S->raga_sw.size();
}

void nv_song_note_table(void *s, long long ch, double t, int indian, double *out)
{
    const std::vector<double> &tab = ((nv::Song *)s)->note_table(ch, t, indian != 0);
    for (int k = 0; k < 128; k++)
        out[k] = tab[k];
}

void nv_song_tuning(void *s, long long ch, double t, const double *freq)
{
    nv::Song *S = (nv::Song *)s;
    if (ch < 0)
        S->freq.assign(freq, freq + 128);
    else
        S->mts[ch].push_back(std::make_pair(t, std::vector<double>(freq, freq + 128)));
}

void nv_song_channel(void *s, long long ch, double btun, const double *otun, int fader)
{
    nv::Song *S = (nv::Song *)s;
    if (btun != 0.0)
        S->btun[ch] = btun;
    if (otun)
        S->otun[ch] = std::vector<double>(otun, otun + 12);
    if (fader)
        S->fader[ch] = 1;
}

// The drum sets' keys: f0[128 * program + key] (0 where the engine has no
// drum) and seat[...] (the drum's pan in its set)
void nv_song_kits(void *s, const double *f0, const double *seat)
{
    nv::Song *S = (nv::Song *)s;
    S->kit_f0.assign(f0, f0 + 16384);
    S->kit_seat.assign(seat, seat + 16384);
}

// A note's pitch and level as its channel gives them: f0, velocity, pan,
// channel volume ((CC7 CC11)^2, its program's trim; 1 under a fader row),
// effort (40 log10 of its velocity over the channel's median, +-12, where
// the voice has an effort tilt), and a drum's seat in its set. The note by
// its index in the song's notes (two can share a key, an onset and a
// key-up). 0 if there is no such note (or a drum the sets lack); 2 for a
// drum: its pitch its set's, not a tuning's.
int nv_song_pitch_level_k(void *s, int i, int effort_tilt, int indian, double *out)
{
    return nv_song_pitch_level_ks(s, i, effort_tilt, indian, 0.0, out);
}

int nv_song_pitch_level_kc(void *s, int i, int effort_tilt, const NoteClass *K, double *out)
{
    int r = nv_song_pitch_level_ks(s, i, effort_tilt, K->indian, K->sounding_oct, out);
    const nv::Song *S = (nv::Song *)s;
    if (r == 2 && K->sounding_oct != 0.0)
        out[0] *= pow(2.0, K->sounding_oct);   // a drum's sounding octaves (the helicopter's rotor), after its stroke's pitch
    if (r == 1 && K->scale_n && K->scale_tonic >= 0 && K->scale_tonic < 128)
        out[0] = S->scaled(S->notes[i].ch, S->notes[i].note, S->notes[i].on, K, out[0]);
    return r;
}

int nv_song_pitch_level_ks(void *s, int i, int effort_tilt, int indian, double so, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->notes.size())
        return 0;
    long long ch = S->notes[i].ch;
    int note = S->notes[i].note;
    double on = S->notes[i].on;
    const nv::Ev &e = S->notes[i];
    int r = 1;
    out[5] = 0.0;
    if (e.drum) {
        int q = 128 * e.prog + note;
        if (S->kit_f0.empty() || e.prog < 0 || e.prog > 127 || S->kit_f0[q] == 0.0)
            return 0;
        out[0] = S->kit_f0[q] * e.ratio;
        out[5] = S->kit_seat[q];
        r = 2;
    } else {
        out[0] = S->pitch(ch, note, on, indian != 0, so);
    }
    out[1] = e.vel;
    out[2] = e.pan;
    double cv = pow(e.v7 * e.v11, 2.0);
    if (S->fader.count(ch))
        cv = 1.0;
    out[3] = cv * e.trim;
    double eff = 0.0;
    auto vb = S->vbase.find(ch);
    int b = vb != S->vbase.end() ? vb->second : 0;
    if (!b)
        b = e.vel;
    if (effort_tilt && e.vel && b)
        eff = nv::pymax(-12.0, nv::pymin(12.0, 40.0 * log10(e.vel / (double)b)));
    out[4] = eff;
    return r;
}

int nv_song_pitch_level(void *s, int i, int effort_tilt, double *out)
{
    return nv_song_pitch_level_k(s, i, effort_tilt, 0, out);
}

void nv_song_finish(void *s, double total) { ((nv::Song *)s)->finish(total); }

double nv_song_note_off(void *s, long long ch, int note, double on, double off, int damper_pedal, int mcut,
                        double retrigger_fade, int *band)
{
    bool b = false;
    double r = ((nv::Song *)s)->note_off(ch, note, on, off, damper_pedal, mcut, retrigger_fade, &b);
    *band = b;
    return r;
}

int nv_song_soft_at(void *s, long long ch, double t)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    return C && C->soft_at(t);
}

// The drum sets' gestures expanded into their strokes (Song::strokes;
// before nv_song_finish, after the passes that read the notes as written)
void nv_song_strokes_k(void *s, const NoteClass *const *K, const int *kind, const double *par)
{
    ((nv::Song *)s)->strokes(kind, par, K);
}

double nv_song_note_ratio(void *s, int i)
{
    const nv::Song *S = (nv::Song *)s;
    return (i >= 0 && i < (int)S->notes.size()) ? S->notes[i].ratio : 1.0;
}

void nv_song_strokes(void *s, const int *kind, const double *par)
{
    ((nv::Song *)s)->strokes(kind, par);
}

// Note i a stroke of a struck or scraped gesture (_prep_strokes): its pitch
// ratio, and whether it is a ridge after the scrape's first
void nv_song_note_stroke(void *s, int i, double ratio, int inner)
{
    nv::Song *S = (nv::Song *)s;
    if (i >= 0 && i < (int)S->notes.size()) {
        S->notes[i].ratio = ratio;
        S->notes[i].inner = inner;
    }
}

// A slurred note, as _legato_ticks found it: channel ch's key's k-th (before nv_song_finish)
void nv_song_legato(void *s, long long ch, int note, int k)
{
    ((nv::Song *)s)->legato.insert(std::make_tuple(ch, note, k));
}

// Note i's slurs: out[0] it is slurred, out[1] a slur leaves it. 0 past the notes
int nv_song_slur(void *s, int i, int *out)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->slurred.size())
        return 0;
    out[0] = S->slurred[i];
    out[1] = S->slur_out[i];
    return 1;
}

// The drum sets' exclusive classes: choke[2 * (128 * program + key) + w],
// bit k of word w set where a strike on key stops key 64 w + k (before
// nv_song_finish)
void nv_song_chokes(void *s, const unsigned long long *choke)
{
    ((nv::Song *)s)->kit_choke.assign(choke, choke + 2 * 16384);
}

// Where a later strike in its exclusive class stops this note (the first
// past its onset): 1 and *out, else 0
int nv_song_choke(void *s, long long ch, int note, double on, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    auto it = S->choke_at.find(std::make_pair(ch, note));
    if (it == S->choke_at.end())
        return 0;
    for (double t : it->second)
        if (t > on + 1e-4) {
            *out = t;
            return 1;
        }
    return 0;
}

int nv_song_next_same(void *s, long long ch, int note, double on, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    auto it = S->next_same.find(nv::NoteKey{ch, note, on});
    if (it == S->next_same.end())
        return 0;
    *out = it->second;
    return 1;
}

}  // extern "C"
