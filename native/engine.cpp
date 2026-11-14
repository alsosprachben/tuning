// engine.cpp -- the native engine: a NOTE in, its rows out.
//
// The first piece of the engine the C core (voice.c, tone.c) is a part of.
// A note arrives as what the file and its channel say about it (NoteIn: its
// pitch, velocity, channel volume and pan, its times once the pedal has had
// its say, the channel's rows and room) and leaves as rows, as
// blockrender._build_note's piano path makes them -- with no Python voice
// object: the voice is built here (nv_voice_init), the note's times and
// bends worked out from it (the attack and release laws, the chiff, the
// tension bend), then its hammer knock (nv_strike), its tone (nv_tone) and
// its phantom partials (nv_phantom), into one row store.
//
// What a class is to a note (NoteClass) is filled once per class by
// native.py; the file and channel state (NoteIn) by blockrender for now --
// the channel passes are the next part of the engine to port.
//
// Bit for bit the Python's: built with gcc's C core under the same flags
// (no fused multiply-adds, no builtins), with Python's tie order for
// max/min (pymax/pymin below) and its ** as libm's pow.

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <map>
#include <set>
#include <tuple>
#include <vector>

#include "nv.h"
#include "pycompat.h"          // a flam's random.Random

namespace nv {

static double pymin(double a, double b) { return b < a ? b : a; }
static double pymax(double a, double b) { return b > a ? b : a; }

// numpy.interp for one x on ascending xp (a quantile table): fp's ends past
// them, the point where x falls on one, else the line between (slope first)
static double np_interp1(double x, const double *xp, const double *fp, int n)
{
    if (x > xp[n - 1])
        return fp[n - 1];
    if (x < xp[0])
        return fp[0];
    int j = 0;
    while (j + 1 < n && xp[j + 1] <= x)
        j++;
    if (j == n - 1 || xp[j] == x)
        return fp[j];
    const double slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]);
    return slope * (x - xp[j]) + fp[j];
}

// A RECORD's CLICKS to t_end s (blockrender._record_clicks): (t, dB,
// balance) on one timeline, drawn a revolution at a time from a seed of that
// revolution (random.Random(0xD15C0 + rev)) -- each of the last revolution's
// clicks clicking again a revolution on with rec_pr's probability, its
// level moved +-1 dB, its balance kept, then round(rate x rev_per) new ones:
// a level from the quantiles (or uniform under flam_db), a time uniform in
// the revolution, a balance over the quarter turn. Kept for the process and
// extended, as Python's _RECORD (one key a voice's settings)
static const std::vector<std::array<double, 3>> &record_clicks(const NoteClass *K, double t_end)
{
    struct Tl {
        std::vector<std::array<double, 3>> clicks, last;
        long rev = 0;
    };
    static std::map<std::vector<double>, Tl> tls;
    std::vector<double> key{K->flam_rate, K->rec_per, K->rec_pr, K->flam_db, (double)K->n_rq};
    for (int q = 0; q < K->n_rq; q++) {
        key.push_back(K->rec_qx[q]);
        key.push_back(K->rec_qy[q]);
    }
    Tl &st = tls[key];
    const double per = K->rec_per, pr = K->rec_pr;
    while ((double)st.rev * per < t_end + per) {
        const long r = st.rev;
        PyRandom rr;
        pyr_seed(&rr, 0xD15C0 + r);
        std::vector<std::array<double, 3>> nw;
        for (const auto &c : st.last)
            if (pyr_random(&rr) < pr) {
                const double l = c[1] + pyr_uniform(&rr, -1.0, 1.0);
                nw.push_back({c[0] + per, l, c[2]});
            }
        const long n = (long)nearbyint(K->flam_rate * per);
        for (long q = 0; q < n; q++) {
            const double u = pyr_random(&rr);
            const double lv = K->n_rq ? np_interp1(100.0 * u, K->rec_qx, K->rec_qy, K->n_rq) : -K->flam_db * u;
            const double t = (double)r * per + pyr_random(&rr) * per;
            nw.push_back({t, lv, pyr_uniform(&rr, 0.0, 0.5 * M_PI)});
        }
        st.clicks.insert(st.clicks.end(), nw.begin(), nw.end());
        st.last.clear();
        for (const auto &c : nw)
            if ((double)r * per <= c[0] && c[0] < (double)(r + 1) * per)
                st.last.push_back(c);
        st.rev++;
    }
    return st.clicks;
}

}  // namespace nv

extern "C" {


// blockrender._build_note's piano path, from the voice's construction to
// its phantom partials: the note's rows into rows (cap of them), qacc[18]
// and *azimuth carried; rs the global random stream (NULL: a scratch one).
// The room's image sources for the voice's position (img etc.) are the
// caller's, or with nimg < 0 the room's (nv_images, from n's walls). Returns
// the rows written: -1 if the store was too small, -2 if the note is not the
// engine's after all (more than 64 images, an order over 8).
int nv_note(const NoteClass *K, const NoteIn *n, PyRandom *rs,
            int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
            double *rows, int cap, double *qacc, double *azimuth, NoteOut *out)
{
    using nv::pymax;
    using nv::pymin;
    const double SR = n->sr;

    // THE VOICE (the Python's props = nt.pc(f0, pan, (vel/127)**2, chan_vol, effort))
    VoiceInit c = K->init;
    c.detune_lo = n->detune_lo;
    c.detune_hi = n->detune_hi;
    c.soft_pedal_down = n->soft_pedal_down;
    c.fixed_touch = n->fixed_touch;
    if (n->seat != 0.0)                 // a seat inside the instrument, at the angle its pan names
        c.seat_x = c.listener_distance * tan(nv_stage_angle(n->seat));
    memcpy(c.rnd_draws, n->rnd_draws, sizeof c.rnd_draws);
    if (c.vbody) {                      // a sung voice: its part's tessitura, and the part its file declares
        c.sung_hz = n->sung_hz;
        double pr, pc;
        if (n->part && nv_voice_part(n->part, &pr, &pc)) {
            c.part_set = 1;
            c.part_ratio = pr;
            c.part_cluster = pc;
        }
    }
    VoiceSnap s;
    VoiceNote o;
    nv_voice_init(&c, &K->tmpl, n->f0, n->pan, pow(n->vel / 127.0, 2.0), n->chan_vol, n->effort, rs, &s, &o);
    if (n->fx_set == 1 && n->fx_p3d)    // THE PART PLACED IN 3D (gsefx's pos3d): where its onset finds it
        nv_voice_turn(&c, &s, &o, n->fx_angle);
    if (n->press != 0.0)                // ...and its level: PRESS_DB x pressure (db_amplitude)
        nv_voice_regain(&c, &s, pow(10.0, 8.0 * n->press / 20.0));
    if (n->gliss_lv > 0.0 && n->gliss_lv != 1.0)
        nv_voice_regain(&c, &s, n->gliss_lv);   // HALF-VALVING LOSES SUPPORT (_GLISS: the step's level)
    if (n->sym_drv)                     // the driver of its channel's strings (_SYM_CH: this note's props)
        memcpy(n->sym_drv, &s, sizeof s);
    const double av = s.attack_volume;  // (an [RND] strike's, varied)
    if (s.throat) {
        // A THROAT'S PULSE (SfxThroatProperties), as the note sets it on the
        // voice it has built: its tilt, mouth and vowel (NaN: the class's),
        // and its breath, tilted with it
        if (!std::isnan(n->stroke_tilt))
            s.stroke_tilt_db = n->stroke_tilt;
        if (!std::isnan(n->stroke_mouth))
            s.formant_scale = n->stroke_mouth;
        if (!std::isnan(n->stroke_morph))
            s.formant_morph = n->stroke_morph;
        o.chiff_volume = s.breath_volume * pow(10.0, s.stroke_tilt_db / 20.0);
    }
    const double f0 = n->f0;
    double B = c.inharmonicity_dynamic ? o.B : o.inharmonicity_coefficient;
    double dur = n->off - n->on;

    // ITS TIMES: attack, release, chiff (speech_time, slur_attack, the caps)
    double at = o.attack_time;
    if (K->si_set)                      // a strike-in set by the hand (strike_in_s): soft to hard
        at = K->si0 + (K->si1 - K->si0) * pymin(1.0, pymax(0.0, n->vel / 127.0));
    if (n->slurred && K->legato_set)
        at = pymin(at, K->legato_attack_s);
    if (n->hammered) {                  // a hammer-on: a fingertip's onset (HAMMER_ATTACK_S)
        at = pymax(at, 0.012);
        if (n->reslur && K->legato_set)
            at = pymin(at, K->legato_attack_s);
    }
    double rt = K->release_valve_set ? K->release_valve_time : K->chiff_max_valve_time;
    if (K->speech_cycles > 0.0 && f0 > 0.0) {
        at = at + K->speech_cycles / f0;
        rt = rt + K->speech_cycles / f0;
    }
    if (n->snd_at != 0.0)               // CC73 and CC72, where the class answers them
        at *= n->snd_at;
    if (n->snd_rt != 0.0)
        rt *= n->snd_rt;
    double fade = pymax(1e-4, pymin(at, K->attack_fraction_max * dur)) * SR;
    double rel = pymax(1e-4, K->release_fraction_set ? pymin(rt, K->release_fraction_max * dur) : rt) * SR;
    if (n->slur_out && K->slur_cuts_release)
        rel = pymin(rel, pymax(n->retrigger_fade, K->legato_set ? K->legato_attack_s : 0.0) * SR);
    if (n->has_nx && n->nx > n->off)
        rel = pymin(rel, pymax(n->retrigger_fade, n->nx - n->off) * SR);
    if (n->mcut)
        rel = pymin(rel, n->retrigger_fade * SR);
    double ct = at;
    if (K->chiff_width_set || K->chiff_width_cycles > 0.0) {
        ct = K->chiff_width_set ? K->chiff_width : at;
        if (K->chiff_width_cycles > 0.0 && f0 > 0.0)
            ct = pymin(ct, K->chiff_width_cycles / f0);
    }
    double chiff = pymax(1e-4, pymin(ct, 0.45 * dur)) * SR;
    double non = (n->on + o.attack_jitter) * SR, noff = n->off * SR;

    // ITS BEND: the tension the strike raises (tension_stroke)
    double tb[3];
    double stroke = K->tension_bend_power == 1.0 ? av : pow(pymax(av, 0.0), K->tension_bend_power);
    tb[0] = o.tension_bend * stroke;
    if (n->slurred && !K->tension_bend_slurs)
        tb[0] = 0.0;
    tb[1] = K->tension_settle_time;
    tb[2] = K->tension_settle_cutoff;
    if (K->tension_log && tb[0] > -1.0) {
        tb[0] = log1p(tb[0]);
        tb[2] = -fabs(tb[2]) / K->tbend_cut_scale;
    }

    // THE EMITTER, as the note leaves it for its partials (_tone_in)
    ToneIn t;
    memset(&t, 0, sizeof t);
    t.f0 = f0;
    t.non = non; t.noff = noff; t.fade = fade; t.rel = rel; t.chiff = chiff;
    t.cv = o.chiff_volume; t.cc = K->chiff_cycle; t.crl = K->chiff_release; t.csc = f0 / 440.0;
    t.li = o.left_incidence; t.ri = o.right_incidence; t.sustain_level = K->sustain_level;
    t.gr = -1; t.cr = 0; t.sr = SR;
    t.jitter_scale = (1.0 + o.pitch_jitter) * (n->xp != 0.0 ? n->xp : 1.0);
    t.transposed = n->xp != 0.0 && n->xp != 1.0;  // (every frequency moved by the key: past Nyquist, dropped)
    t.nyq_om = n->nyq_om;
    t.hammer_on = n->hammer_on;
    t.dl = o.left_hrtf_delay * SR; t.dr = o.right_hrtf_delay * SR;
    t.pos_x0 = t.pos_x_props = s.position_x;
    t.pos_z = s.position_z;
    t.channel = n->channel;
    memcpy(t.tb, tb, sizeof tb);
    memcpy(t.gl, n->gl, sizeof t.gl);
    memcpy(t.sv, n->sv, sizeof t.sv);
    t.sound_vib_depth_cents = n->sound_vib_depth_cents; t.vibrato_delay = n->vibrato_delay;
    t.br = n->br; t.fx = n->fx; t.mk = n->mk; t.fm_omega = n->fm_omega; t.fm_phase = n->fm_phase;
    t.n_alias = n->n_alias;
    for (int q = 0; q < n->n_alias && q < 32; q++)
        t.alias_br[q] = n->alias_br[q];
    t.listener_distance = c.listener_distance; t.head_radius = c.head_radius; t.pan_angle = o.pan_angle;
    memcpy(t.room_bands, n->room_bands, sizeof t.room_bands);
    t.rev = K->played_backwards;            // (em.reverse: its rows emitted backwards)
    t.rev_n0 = non; t.rev_arr = noff;
    memcpy(t.planes, n->planes, sizeof t.planes);
    t.order = n->order;
    t.dist = n->dist;
    memcpy(t.gs_eq, n->gs_eq, sizeof t.gs_eq);
    memcpy(t.fx_comp, n->fx_comp, sizeof t.fx_comp);
    t.cls = (long long)(intptr_t)K;         // (its class: _refl_norm's memo key, type(props))
    if (s.sect_n > 1 && s.sect_seats) {     // A SECTION'S: the note's ears are its first player's desk's
        double e[4];
        nv_section_seat(&s, &t, 0, e);
        t.li = e[0]; t.ri = e[1];
        t.dl = e[2] * SR; t.dr = e[3] * SR;
    }

    int total = 0, no_refl = n->no_reflections;
    // THE EMITTER'S RADIUS AS THE LAST NOTE LEFT IT (an organ's last pipe):
    // what this note emits before its tone carries it, as the Python's em.radius
    if (!std::isnan(n->carry_radius)) {
        t.radius = n->carry_radius;
        t.has_radius = 1;
    }

    // THE HAMMER'S KNOCK (_note_strike_noise): noise rows, no images
    out->n_knock = 0;
    out->n_ft = 0;
    if (K->n_strike) {
        double sf0 = K->strike_span_set ? pymin(pymax(f0, K->strike_span_lo), K->strike_span_hi) : f0;
        double reg = K->strike_octave_db * log2(pymax(sf0, 1.0) / 440.0);
        double slr = log(10.0) / 20.0 * K->strike_noise_dbs;
        double sfade = pymax(1.0, K->strike_fade_s * SR);
        double slen = K->strike_len_s * SR;
        if (K->gate_time > 0.0 && K->one_shot)    // ...closed by a gate with the note
            slen = pymin(slen, pymax(1.0, noff - non));
        // A FLAM (strike_flam > 1): that many strikes, each at its own offset
        // and level, drawn from the note (random.Random of its onset, key and
        // channel), the first at the onset and the loudest at the table's
        // ...OR A CROWD (strike_flam_rate): round(rate x the note's length)
        // of them, two at least, through the whole note
        double fspan = K->flam_s;
        int nfl = K->n_flam;
        if (K->flam_rate > 0.0) {
            fspan = pymax(0.0, (noff - non) / SR);
            nfl = std::max(2, (int)nearbyint(K->flam_rate * fspan));
        }
        size_t cap_b = (size_t)std::max(64, nfl);
        std::vector<double> boff(cap_b, 0.0), bdb(cap_b, 0.0), bgl(cap_b, 1.0), bgr(cap_b, 1.0);
        std::vector<double> bpk;            // each burst's palms' pitch (a person's; 0 none)
        int nb = 1;
        if (K->flam_record && K->flam_rate > 0.0) {
            // A RECORD'S CLICKS (blockrender._record_clicks): ONE timeline for
            // the voice, every note sounding meets the same clicks at the
            // same instants -- those within it, in the timeline's order, each
            // at its drawn level (not renormalised) and in its own place in
            // the balance; none: one silent burst
            const std::vector<std::array<double, 3>> &rc = nv::record_clicks(K, noff / SR);
            const double a0 = non / SR, a1 = noff / SR;
            std::vector<std::array<double, 3>> got;
            for (const auto &c : rc)
                if (a0 <= c[0] && c[0] < a1)
                    got.push_back({c[0] - a0, c[1], c[2]});
            if (got.empty())
                got.push_back({0.0, -200.0, 0.25 * M_PI});
            nb = (int)got.size();
            boff.assign(nb, 0.0); bdb.assign(nb, 0.0); bgl.assign(nb, 1.0); bgr.assign(nb, 1.0);
            for (int b = 0; b < nb; b++) {
                boff[b] = got[b][0];
                bdb[b] = got[b][1];
                bgl[b] = sqrt(2.0) * cos(got[b][2]);
                bgr[b] = sqrt(2.0) * sin(got[b][2]);
            }
        } else if (K->n_ft) {
            // ...OR A MACHINE'S (strike_flam_times): its bursts where its
            // envelope put them, each in its own place in the balance
            nb = K->n_ft;
            for (int b = 0; b < nb; b++) {
                boff[b] = K->ft_t[b];
                bdb[b] = K->ft_db[b];
                if (K->ft_bal) {
                    bgl[b] = sqrt(2.0) * cos(K->ft_c[b]);
                    bgr[b] = sqrt(2.0) * sin(K->ft_c[b]);
                }
            }
        } else if (K->people_n > 0) {
            // ...OR A FEW PEOPLE (strike_flam_people): each at their own
            // steady rate, place and distance, in raggedly within 0.2 s,
            // stopping in the note's last third; each one's palms' pitch
            PyRandom pr;
            pyr_seed(&pr, (long long)nearbyint(n->on * 1e6) * 137 + (long long)n->note * 11 + n->ch);
            double pspan = pymax(0.0, (noff - non) / SR);
            std::vector<double> bt, bl, ba;
            for (int p = 0; p < K->people_n; p++) {
                double per = 1.0 / pyr_uniform(&pr, K->people_lo, K->people_hi);
                double plvl = -pyr_uniform(&pr, 0.0, K->people_db);
                double pang = pyr_uniform(&pr, 0.08, 0.92) * 0.5 * M_PI;
                double phz = K->pk_set ? K->pk_lo * pow(K->pk_hi / K->pk_lo, pyr_random(&pr)) : 0.0;
                double pt = pyr_uniform(&pr, 0.0, 0.2);
                double pend = pspan * pyr_uniform(&pr, 0.67, 1.0);
                while (pt < pend) {
                    bt.push_back(pt);
                    bl.push_back(plvl + pyr_gauss(&pr, 0.0, 1.0));
                    ba.push_back(pang);
                    bpk.push_back(phz);
                    pt += per * pymax(0.5, pyr_gauss(&pr, 1.0, K->people_jit));
                }
            }
            if (!bt.empty()) {
                double t0 = bt[0], l0 = bl[0];
                for (size_t b = 1; b < bt.size(); b++) {
                    t0 = pymin(t0, bt[b]);
                    l0 = pymax(l0, bl[b]);
                }
                nb = (int)bt.size();
                boff.assign(nb, 0.0); bdb.assign(nb, 0.0); bgl.assign(nb, 1.0); bgr.assign(nb, 1.0);
                for (int b = 0; b < nb; b++) {
                    boff[b] = bt[b] - t0;
                    bdb[b] = bl[b] - l0;
                    bgl[b] = sqrt(2.0) * cos(ba[b]);
                    bgr[b] = sqrt(2.0) * sin(ba[b]);
                }
            } else {
                nb = 1;
                boff[0] = bdb[0] = 0.0;
                bgl[0] = sqrt(2.0) * cos(0.25 * M_PI);
                bgr[0] = sqrt(2.0) * sin(0.25 * M_PI);
                bpk.assign(1, 0.0);
            }
        } else if (nfl > 1) {
            if (nfl > 64 && K->flam_rate <= 0.0)
                return -2;
            PyRandom fr;
            pyr_seed(&fr, (long long)nearbyint(n->on * 1e6) * 131 + (long long)n->note * 7 + n->ch);
            nb = nfl;
            for (int b = 0; b < nb; b++) {
                boff[b] = pyr_uniform(&fr, 0.0, fspan);
                // ...ITS LEVELS EXPONENTIAL in dB under the loudest (a reed's
                // crackle: random.expovariate, held within strike_flam_db)
                bdb[b] = K->flam_exp > 0.0 ? -pymin(-log(1.0 - pyr_random(&fr)) / (1.0 / K->flam_exp), K->flam_db)
                                           : -pyr_uniform(&fr, 0.0, K->flam_db);
            }
            double t0 = boff[0], l0 = bdb[0];
            for (int b = 1; b < nb; b++) {
                t0 = pymin(t0, boff[b]);
                l0 = pymax(l0, bdb[b]);
            }
            if (K->flam_exp > 0.0)
                t0 = 0.0;               // (a crackle keeps its draw's times: no click on the onset)
            for (int b = 0; b < nb; b++) {
                boff[b] -= t0;
                bdb[b] -= l0;
            }
        }
        ToneIn tk = t;
        tk.gain = s.gain; tk.B = 0.0; tk.sjit = 0.0; tk.reflect = 0;
        tk.cbw0 = -0.25; tk.cbw1 = 0.0;
        out->n_knock = 0;
        // A PERSON'S PALMS RINGING after each clap: the clap's colour at
        // their pitch (np.interp on log Hz) + peak dB + the register's, the
        // burst's and the calibration's, dying at 27.29 dB/s a hertz of width
        auto palm = [&](int b, double bd, double bon) -> int {
            double hz = bpk[b], x = log(hz), cdb;
            int nt_ = K->n_strike;
            if (x < log(K->strike_hz[0]))
                cdb = K->strike_db[0];
            else if (x > log(K->strike_hz[nt_ - 1]))
                cdb = K->strike_db[nt_ - 1];
            else {
                int j = 0;
                while (j < nt_ - 1 && !(x < log(K->strike_hz[j + 1])))
                    j++;
                double xj = log(K->strike_hz[j]);
                if (j == nt_ - 1 || x == xj)
                    cdb = K->strike_db[j];
                else {
                    double slope = (K->strike_db[j + 1] - K->strike_db[j]) / (log(K->strike_hz[j + 1]) - xj);
                    cdb = slope * (x - xj) + K->strike_db[j];
                }
            }
            double db = cdb + K->pk_db + reg + bd + K->strike_cal_db;
            double plr = log(10.0) / 20.0 * 27.29 * hz / K->pk_q;
            return nv_palm(&s, &tk, hz, db, plr, bon, slen, sfade, bgl[b], bgr[b], s.position_x,
                           rows + NCOLS * total, cap - total, qacc, azimuth);
        };
        for (int b = 0; b < nb; b++) {
            double bon = non + K->strike_at_s * SR + boff[b] * SR;
            int k = nv_strike_bal(&s, &tk, K->n_strike, K->strike_hz, K->strike_db, reg, bdb[b], K->strike_cal_db,
                                  slr, sfade, slen, bon, s.position_x, bgl[b], bgr[b], rows + NCOLS * total,
                                  cap - total, qacc, azimuth);
            if (k < 0)
                return -1;
            out->n_knock += k;
            total += k;
            if (b < (int)bpk.size() && bpk[b] > 0.0) {
                k = palm(b, bdb[b], bon);
                if (k < 0)
                    return -1;
                out->n_knock += k;
                total += k;
            }
        }
        // ...AND A SLOWER TAIL under it (strike_noise_tail): the bursts again,
        // quieter and longer -- a music box's comb buzzing under its pin's snap
        if (K->tail_set) {
            double tlr = log(10.0) / 20.0 * K->tail_dbs;
            for (int b = 0; b < nb; b++) {
                double bon = non + K->strike_at_s * SR + boff[b] * SR;
                int k = nv_strike_bal(&s, &tk, K->n_strike, K->strike_hz, K->strike_db, reg, bdb[b] + K->tail_db,
                                      K->strike_cal_db, tlr, sfade, slen, bon, s.position_x, bgl[b], bgr[b],
                                      rows + NCOLS * total, cap - total, qacc, azimuth);
                if (k < 0)
                    return -1;
                out->n_knock += k;
                total += k;
                if (b < (int)bpk.size() && bpk[b] > 0.0) {
                    k = palm(b, bdb[b] + K->tail_db, bon);
                    if (k < 0)
                        return -1;
                    out->n_knock += k;
                    total += k;
                }
            }
        }
        // ...AND MORE STRUCK THINGS THAN ONE (strike_noise_layers): each its
        // own rise, fall and length, from the note's onset
        for (int l = 0; l < K->n_layer; l++) {
            double llen = K->lay_len[l];
            if (K->gate_time > 0.0 && K->one_shot)
                llen = pymin(llen, pymax(1.0, noff - non) / SR);
            int k = nv_layer(&s, &tk, K->lay_n[l], K->lay_hz[l], K->lay_db[l], reg, pymax(1.0, K->lay_rise[l] * SR),
                             log(10.0) / 20.0 * K->lay_dbs[l], llen * SR, s.position_x, rows + NCOLS * total,
                             cap - total, qacc, azimuth);
            if (k < 0)
                return -1;
            out->n_knock += k;
            total += k;
        }
        no_refl = 0;
    }

    // THE BREATH (_note_breath_noise): the voice's noise held for the note
    if (K->n_bn) {
        ToneIn tb_ = t;
        tb_.gain = s.gain; tb_.B = 0.0; tb_.sjit = 0.0; tb_.reflect = 0;
        tb_.cbw0 = -0.25; tb_.cbw1 = 0.0;
        if (n->bbr_set)
            tb_.br = n->bbr;                    // (the breath's own row, wobbling)
        // (its table at this pitch: the low register's blended in by band, _breath_noise_rows)
        double bdb[64];
        for (int q = 0; q < K->n_bn; q++)
            bdb[q] = K->bn_db[q];
        if (K->bn_low_set) {
            double lo = K->bn_low_hz[0], hi = K->bn_low_hz[1], w;
            if (f0 <= lo)
                w = 1.0;
            else if (f0 >= hi)
                w = 0.0;
            else
                w = log(hi / f0) / log(hi / lo);
            if (w >= 1.0) {
                for (int q = 0; q < K->n_bn; q++)
                    bdb[q] = K->bn_low[q];      /* (the low table itself: its bands are the table's) */
            } else if (w > 0.0) {
                for (int q = 0; q < K->n_bn; q++)
                    bdb[q] = w * (std::isnan(K->bn_low[q]) ? K->bn_db[q] : K->bn_low[q]) + (1.0 - w) * K->bn_db[q];
            }
        }
        if (K->bn_oct != 0.0) {             // (breath_noise_at: across the register, d dB an octave)
            const double d = K->bn_oct * log(f0 / K->bn_ref) / log(2.0);
            for (int q = 0; q < K->n_bn; q++)
                bdb[q] = bdb[q] + d;
        }
        // (on a slur the player never stopped blowing: the legato attack, breath_noise_slur)
        double bfs = (n->slurred && K->bn_slur && K->legato_set) ? pymin(K->bn_fade_s, K->legato_attack_s)
                                                                 : K->bn_fade_s;
        int k = nv_breath(&s, &tb_, K->n_bn, K->bn_hz, bdb, K->bn_rows, pymax(1.0, bfs * SR),
                          s.position_x, rows + NCOLS * total, cap - total, qacc, azimuth);
        if (k < 0)
            return -1;
        out->n_knock += k;
        total += k;
        no_refl = 0;
    }

    // GRAINS (_note_grains): the beads, the drops, the bubbles -- on the
    // breath's swell where it has one, no images, no noise width
    out->grain0 = out->grain1 = total;
    if (K->n_grain) {
        ToneIn tg = t;
        tg.B = 0.0; tg.sjit = 0.0; tg.reflect = 0;
        tg.cbw0 = 0.0; tg.cbw1 = 0.0;
        if (n->bbr_set)
            tg.br = n->bbr;
        int k = nv_grains(&s, &tg, K->n_grain, K->grain,
                          (long long)nearbyint(n->on * 1e6) * 139 + (long long)n->note * 13 + n->ch, K->porta_settle,
                          s.position_x, rows + NCOLS * total, cap - total, qacc, azimuth);
        if (k < 0)
            return -1;
        out->n_knock += k;
        total += k;
        out->grain1 = total;
        no_refl = 0;
    }

    // TIMED NOISE BANDS (_note_noise_events: the heartbeat's blood flow),
    // beside the partials, its width the noise's, no images
    if (K->n_nev) {
        ToneIn te = t;
        te.cbw0 = -K->noise_rel; te.cbw1 = 0.0; te.reflect = 0;
        int k = nv_events(&s, &te, K->n_nev, K->nev, K->noise_rows, K->nev_ramp_s * SR, s.position_x,
                          rows + NCOLS * total, cap - total, qacc, azimuth);
        if (k < 0)
            return -1;
        out->n_knock += k;
        total += k;
        no_refl = 0;
    }

    // A SHAKE AS SHAPED NOISE (_note_shake_noise): in place of the tone
    if (K->shake) {
        ToneIn ts = t;
        ts.cbw0 = -K->noise_rel; ts.cbw1 = 0.0; ts.sjit = 0.0;
        int k = nv_shake(&s, &ts, K->n_nb, K->nb_hz, K->nb_db, K->noise_rows, n->held, K->shake_min_s,
                         K->shake_frac, K->shake_xfade_s, K->rise_s, K->settle_db, K->settle_s, s.position_x,
                         rows + NCOLS * total, cap - total, qacc, azimuth);
        if (k < 0)
            return -1;
        total += k;
        out->n_tone = 0;
        out->n_phantom = 0;
        out->non = non; out->noff = noff; out->fade = fade; out->rel = rel; out->chiff = chiff;
        out->jitter_scale = t.jitter_scale;
        out->dl = t.dl; out->dr = t.dr; out->li = t.li; out->ri = t.ri; out->radius = n->carry_radius;
        out->n_push = 0;
        out->f0 = f0;
        out->pos_x = s.position_x; out->pos_z = s.position_z; out->B = B;
        out->cv = t.cv; out->cc = t.cc; out->crl = t.crl; out->sjit = o.sustain_jitter; out->csc = t.csc;
        memcpy(out->tb, tb, sizeof tb);
        out->cbw[0] = K->cbw0; out->cbw[1] = K->cbw1;
        return total;
    }

    // THE ROOM'S IMAGES of the voice where it stands (_images_for)
    int nsurf_[64], surf_[64 * 8];
    double img_[3 * 64], mir_[3 * 64];
    if (nimg < 0) {
        if (n->order > 8)
            return -2;
        const double dm = n->dist > 0.0 ? n->dist : 1.0;     // (moved out along its ray: _src_dist)
        nimg = nv_images(n->planes, n->order, s.position_x * dm, s.radiation_distance * dm, s.position_z * dm,
                         64, nsurf_, surf_, img_, mir_);
        if (nimg < 0)
            return -2;                      // more than 64 images: not the engine's
        nsurf = nsurf_; surf = surf_; img = img_; mir = mir_;
    }

    int reflect = n->reflect && !no_refl && K->reflection_order;
    // A PRESSURE PULSE (_note_pulse: the gunshot's N-wave) in place of the
    // series, with its images
    if (K->pulse) {
        ToneIn tp = t;
        tp.gain = s.gain; tp.reflect = reflect;
        tp.cbw0 = K->cbw0; tp.cbw1 = K->cbw1;      // (the note's wash width, _CBW: chiff_bandwidth or RAND_GRAN)
        int k = nv_pulse(&s, &tp, f0, n->blk, K->pulse_lo_ms, K->pulse_hi_ms, K->pulse_peak, K->pulse_fmax,
                         K->pulse_taper, s.position_x, reflect ? nimg : 0, nsurf, surf, img, mir,
                         rows + NCOLS * total, cap - total, qacc, azimuth);
        if (k < 0)
            return -1;
        total += k;
        out->n_tone = 0;
        out->n_phantom = 0;
        out->non = non; out->noff = noff; out->fade = fade; out->rel = rel; out->chiff = chiff;
        out->jitter_scale = t.jitter_scale;
        out->dl = t.dl; out->dr = t.dr; out->li = t.li; out->ri = t.ri; out->radius = n->carry_radius;
        out->n_push = 0;
        out->f0 = f0;
        out->pos_x = s.position_x; out->pos_z = s.position_z; out->B = B;
        out->cv = t.cv; out->cc = t.cc; out->crl = t.crl; out->sjit = o.sustain_jitter; out->csc = t.csc;
        memcpy(out->tb, tb, sizeof tb);
        out->cbw[0] = K->cbw0; out->cbw[1] = K->cbw1;
        return total;
    }
    // A MOOG (blockrender._note_moog): its layers' partials in place of the
    // tone, each layer on its own filter row (n->fx the first's), and the
    // rows the kernel reads them by (moog.ft_row: the key's tracking, the
    // layer -- for the caller's knob row -- and the key)
    out->n_ft = 0;
    if (s.kind == 6) {
        const MoogSpec &M = K->moog;
        if (M.n_layer < 1 || M.n_layer > 2)
            return -2;
        ToneIn tm = t;
        tm.sjit = o.sustain_jitter;
        tm.reflect = n->reflect && K->reflection_order;     // (a noise band's own: none)
        tm.cbw0 = K->cbw0; tm.cbw1 = K->cbw1;
        int nm = 0;
        int neutral = nv_moog_neutral();        // (a live template: layer A, knob-neutral)
        int nl = neutral ? 1 : M.n_layer;
        for (int l = 0; l < nl; l++) {
            MoogLayer La;
            if (n->snd_moog)                    // its knobs as GM's sound controllers turn them
                nv_moog_apply(&M.L[l], n->snd_d, &La);
            const MoogLayer &L = n->snd_moog ? La : M.L[l];
            double mre = pymax(1.0, L.rel_span * SR);
            int k = neutral ? nv_moog_neutral_tone(&s, &tm, &L, n->fx + l, mre, nimg, nsurf, surf, img, mir,
                                                   rows + NCOLS * total, cap - total, qacc, azimuth)
                            : nv_moog_tone(&s, &tm, &L, n->fx + l, mre, nimg, nsurf, surf, img, mir,
                                           rows + NCOLS * total, cap - total, qacc, azimuth);
            if (k < 0)
                return -1;
            total += k;
            nm += k;
            out->lay_rows[l] = k;
            for (int j = 0; j < 30; j++)
                out->ft[l][j] = L.ft[j];
            out->ft[l][0] = pow(f0 / L.kb_ref_hz, L.kb_track);
            out->ft[l][9] = (double)l;
            out->ft[l][10] = f0;
            for (int j = 0; j < 9; j++)
                out->kn[l][j] = L.kn[j];
        }
        out->n_ft = nl;
        out->n_tone = nm;
        out->n_phantom = 0;
        out->n_click = 0;
        out->n_jack = 0;
        out->non = non; out->noff = noff; out->fade = fade; out->rel = rel; out->chiff = chiff;
        out->jitter_scale = t.jitter_scale;
        out->dl = t.dl; out->dr = t.dr; out->li = t.li; out->ri = t.ri; out->radius = n->carry_radius;
        out->n_push = 0;
        out->f0 = f0;
        out->pos_x = s.position_x; out->pos_z = s.position_z; out->B = B;
        out->cv = t.cv; out->cc = t.cc; out->crl = t.crl; out->sjit = o.sustain_jitter; out->csc = t.csc;
        memcpy(out->tb, tb, sizeof tb);
        out->cbw[0] = K->cbw0; out->cbw[1] = K->cbw1;
        return total;
    }
    // A STRUCK, PITCHED LAYER (_note_struck_layer: an orchestra hit's
    // timpani): that class's own modes at the note moved by octaves into its
    // range, its voice built there (drawing from the stream as its
    // constructor does), each mode at its level against the loudest, its own
    // rise and fall, a phase from the note's own stream
    if (K->sl_on && K->sl) {
        const NoteClass *L = K->sl;
        double ft = f0;
        while (ft >= K->sl_hi)
            ft *= 0.5;
        while (ft < K->sl_lo)
            ft *= 2.0;
        VoiceInit lc = L->init;
        lc.fixed_touch = n->fixed_touch;
        lc.soft_pedal_down = n->soft_pedal_down;
        VoiceSnap ls;
        VoiceNote lo;
        nv_voice_init(&lc, &L->tmpl, ft, n->pan, 1.0, n->chan_vol, 0.0, rs, &ls, &lo);
        int nm = K->sl_nm;
        double hv[64], hmax = 0.0;
        for (int m = 1; m <= nm && m <= 64; m++) {
            hv[m - 1] = nv_harmonic_volume(&ls, m);
            hmax = m == 1 ? hv[0] : pymax(hmax, hv[m - 1]);
        }
        if (!(nm > 0 && hmax > 0.0))
            hmax = 1.0;
        ToneIn tl = t;
        tl.reflect = reflect;
        tl.gain = 1.0; tl.sjit = 0.0;
        tl.cbw0 = K->cbw0; tl.cbw1 = K->cbw1;
        long long seed = (long long)nearbyint(n->on * 1e6) * 149 + (long long)n->note * 13 + n->ch;
        int k = nv_struck(&s, &tl, &ls, nm, ft, hv, hmax, K->sl_db, K->sl_rise, K->sl_dbs, seed,
                          reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total, cap - total, qacc, azimuth);
        if (k < 0)
            return k == -2 ? -2 : -1;
        out->n_knock += k;
        total += k;
    }
    // THE OTHER STRINGS (_note_ring): after the struck layer, before the
    // touch's modes and the tone, as the Python's; off the wheel (the fader's row)
    out->ring0 = out->ring1 = (int)total;
    if (K->ring_n && n->ring_on) {
        ToneIn tr = t;
        tr.reflect = reflect;
        tr.gain = 1.0; tr.sjit = 0.0;
        tr.cbw0 = K->cbw0; tr.cbw1 = K->cbw1;
        tr.br = n->fbr;
        PyRandom rr;
        pyr_seed(&rr, (long long)rint(n->on * 1e6) * 137 + n->note * 11 + n->ch);
        int k = nv_ring(&s, &tr, f0, K->ring_n, n->ring_f, K->ring_db, K->ring_dps, K->ring_skip,
                        K->ring_nown, K->ring_own, &rr,
                        reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total, cap - total, qacc, azimuth);
        if (k < 0)
            return -1;
        out->n_knock += k;
        total += k;
        out->ring1 = (int)total;
    }
    // A TOUCHED STRING'S OTHER MODES (blockrender's touch_leak_db): before
    // the tone, as the Python's (no breath or shake beside them: native.py)
    if (s.elec && s.touch > 1 && s.leak_set) {
        ToneIn tl = t;
        tl.reflect = reflect;
        tl.gain = 1.0; tl.sjit = 0.0;
        tl.cbw0 = K->cbw0; tl.cbw1 = K->cbw1;
        double fs = f0 / s.touch;
        double Bs = c.inharmonicity_dynamic ? (c.b_law == 3 ? c.law_k * pow(fs, c.law_p) : o.B)
                                            : o.inharmonicity_coefficient;
        PyRandom lr;
        pyr_seed(&lr, (long long)rint(n->on * 1e6) * 149 + n->note * 17 + n->ch);
        int k = nv_leak(&s, &tl, Bs, &lr, reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total,
                        cap - total, qacc, azimuth);
        if (k < 0)
            return -1;
        out->n_knock += k;
        total += k;
    }

    // THE TONE (_note_stops, one stop at gain 1): its partials radiate as
    // themselves -- an organ's from its first pipe on (organ.c sets each
    // pipe's): until then, the leakage before its first rank's partials,
    // the emitter's radius as the last note left it (Python's em.radius)
    if (!K->organ) {
        t.radius = 0.0;
        t.has_radius = 0;
    }
    t.gain = 1.0; t.B = B; t.sjit = o.sustain_jitter; t.reflect = reflect;
    t.cbw0 = K->cbw0; t.cbw1 = K->cbw1;
    t.pjit = K->pjit; t.sps = K->sps; t.dur = dur; t.ssc = K->ssc;
    t.pps_seed = (long long)nearbyint(n->on * 1e6) * 151 + (long long)n->note * 19 + n->ch;
    double trans[3 * 1025];
    int ntr = 0;
    if (s.max_harmonic + 1 > 1025)
        return -2;
    double sjit_last = o.sustain_jitter;        // (the note's sjit after its partials)
    int k;
    double fin[6] = {t.li, t.ri, t.dl, t.dr, NAN, 0.0};
    if (K->organ)                               // A REGISTERED ORGAN: its ranks, then their push
        k = nv_organ_tone(K->organ, &s, &t, n, rs, n->note, reflect ? nimg : 0, nsurf, surf, img, mir,
                          rows + NCOLS * total, cap - total, qacc, azimuth, fin);
    else
        k = nv_tone_rs(&s, &t, reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total, cap - total,
                       trans, &ntr, qacc, azimuth, rs, &sjit_last);
    if (k == -2)
        return -2;                          // a sign to draw and no stream
    if (k < 0)
        return -1;
    out->n_tone = k;
    total += k;

    // THE PHANTOM PARTIALS (_note_phantoms)
    t.gain = s.gain; t.B = 0.0; t.sjit = 0.0; t.pjit = 0; t.sps = 0.0;
    k = nv_phantom(&s, &t, trans, ntr, reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total,
                   cap - total, qacc, azimuth);
    if (k < 0)
        return -1;
    out->n_phantom = k;
    total += k;

    // THE KEY-UP'S CLICK (_note_release_click): the mechanism letting go, at
    // the note's end, the emitter as the note leaves it
    out->n_click = 0;
    out->n_jack = 0;
    if (K->n_click) {
        ToneIn tc = t;
        tc.li = fin[0]; tc.ri = fin[1]; tc.dl = fin[2]; tc.dr = fin[3];
        tc.radius = 0.0;
        tc.has_radius = 0;
        if (K->organ && !std::isnan(fin[4])) {
            tc.radius = fin[4];
            tc.has_radius = 1;
        }
        tc.reflect = reflect;
        tc.br = n->br;
        tc.cbw0 = K->cbw0; tc.cbw1 = K->cbw1;
        k = nv_click(&s, &tc, K, n, noff, reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total,
                     cap - total, qacc, azimuth, out);
        if (k < 0)
            return -1;
        total += k;
    }

    out->non = non; out->noff = noff; out->fade = fade; out->rel = rel; out->chiff = chiff;
    out->jitter_scale = t.jitter_scale;
    out->dl = fin[2]; out->dr = fin[3]; out->li = fin[0]; out->ri = fin[1];
    out->radius = K->organ ? fin[4] : (out->n_tone > 0 ? NAN : n->carry_radius);  // (an organ's last pipe; none past a tone)
    out->n_push = (int)fin[5];          // ...and its push's rows, the tone's last
    out->f0 = f0;
    out->pos_x = s.position_x; out->pos_z = s.position_z; out->B = B;
    out->cv = t.cv; out->cc = t.cc; out->crl = t.crl; out->sjit = sjit_last; out->csc = t.csc;
    memcpy(out->tb, tb, sizeof tb);
    out->cbw[0] = K->cbw0; out->cbw[1] = K->cbw1;
    return total;
}

// BRASS INTONATION FROM THE HORN (brass_fingering.cents_offset): the
// fingering a player would choose -- the lowest harmonic within 60 cents,
// in 25-cent bands, then the fewest valves -- and what that tube sounds,
// less the LIP_CORRECTION a player removes. Cents sharp of target.
static double brass_cents(double target, int tuba)
{
    static const double drop[5] = {0.0, 2.0, 1.0, 3.0, 5.0};
    static const int combos3[7][3] = {{0}, {2}, {1}, {1, 2}, {2, 3}, {1, 3}, {1, 2, 3}};
    static const int combos4[11][3] = {{0}, {2}, {1}, {1, 2}, {2, 3}, {4}, {2, 4}, {1, 4}, {1, 2, 4}, {2, 3, 4},
                                       {1, 2, 3}};
    const double semi = pow(2.0, 1.0 / 12.0);
    double open_hz = tuba ? 29.14 : 116.54;
    int nc = tuba ? 11 : 7;
    bool have = false;
    long long br0 = 0, br1 = 0, br2 = 0;
    double best_cents = 0.0;
    for (int h = 2; h <= 10; h++)
        for (int ci = 0; ci < nc; ci++) {
            const int *cb = tuba ? combos4[ci] : combos3[ci];
            double add[3];
            int len = 0;
            for (int j = 0; j < 3 && cb[j]; j++)
                add[len++] = pow(semi, drop[cb[j]]) - 1.0;
            double f = open_hz * h / (1.0 + (len ? pysum(add, len) : 0.0));
            double cents = 1200.0 * log2(target / f);
            if (fabs(cents) > 60.0)
                continue;
            long long r0 = (long long)py_floordiv(fabs(cents), 25.0), r1 = len, r2 = -h;
            if (!have || r0 < br0 || (r0 == br0 && (r1 < br1 || (r1 == br1 && r2 < br2)))) {
                have = true;
                br0 = r0; br1 = r1; br2 = r2;
                best_cents = -cents;
            }
        }
    return have ? best_cents * (1.0 - 0.80) : 0.0;
}

// HOW LONG A MELODIC ONE-SHOT IS HELD (blockrender.one_shot_ring): until
// its last partial is os_floor_db under the note's loudest -- each from its
// own level, through either stage of its decay -- between one_shot_hold and
// os_max_s. Its voice is the note's, built on a copy of the random stream
// (nv_note builds it again, drawing as the Python's props did once).
static double one_shot_ring(const NoteClass *K, const NoteIn *n, const PyRandom *rs)
{
    VoiceInit c = K->init;
    c.detune_lo = n->detune_lo;
    c.detune_hi = n->detune_hi;
    c.soft_pedal_down = n->soft_pedal_down;
    c.fixed_touch = n->fixed_touch;
    if (n->seat != 0.0)
        c.seat_x = c.listener_distance * tan(nv_stage_angle(n->seat));
    memcpy(c.rnd_draws, n->rnd_draws, sizeof c.rnd_draws);
    if (c.vbody) {                      // a sung voice: its part's tessitura, and the part its file declares
        c.sung_hz = n->sung_hz;
        double pr, pc;
        if (n->part && nv_voice_part(n->part, &pr, &pc)) {
            c.part_set = 1;
            c.part_ratio = pr;
            c.part_cluster = pc;
        }
    }
    PyRandom r = *rs;
    VoiceSnap s;
    VoiceNote o;
    nv_voice_init(&c, &K->tmpl, n->f0, n->pan, pow(n->vel / 127.0, 2.0), n->chan_vol, n->effort, &r, &s, &o);
    int top_m = s.max_harmonic ? s.max_harmonic : 8;
    if (top_m > 512)
        top_m = 512;
    double hv[513];
    int hm[513];
    int nh = 0;
    double top = 0.0;
    for (int m = 1; m <= top_m; m++) {
        double v = nv_harmonic_volume(&s, m);
        if (v != 0.0 && v > 0.0) {
            if (nh == 0 || v > top)
                top = v;
            hm[nh] = m;
            hv[nh++] = v;
        }
    }
    if (!nh)
        return K->one_shot_hold;
    double t = 0.0;
    for (int i = 0; i < nh; i++) {
        double room = K->os_floor_db + 20.0 * log10(hv[i] / top);
        if (room <= 0.0)
            continue;
        double pd[4];
        nv_partial_decay(&s, n->f0, hm[i], pd);        /* dbps, logr, aftL, logrA */
        if (pd[0] > 0)
            t = nv::pymax(t, room / pd[0]);
        double adbps = pd[3] * 20.0 / log(10.0);
        if (pd[2] > 0 && adbps > 0 && room + 20.0 * log10(pd[2]) > 0.0)
            t = nv::pymax(t, (room + 20.0 * log10(pd[2])) / adbps);
    }
    return nv::pymin(nv::pymax(t, K->one_shot_hold), K->os_max_s);
}

// A note as its FILE gives it: its channel's answers (native/channel.cpp's
// Song) for its end once the pedals have had their say, its key's next
// strike and the soft pedal at its onset, then nv_note. n's off, nx and
// soft pedal are written; *band: a half-pedalled note that meets the band.
int nv_song_play(void *song, const NoteClass *K, NoteIn *n, PyRandom *rs,
                 int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
                 double *rows, int cap, double *qacc, double *azimuth, NoteOut *out, int *band)
{
    int r = 0;
    if (n->from_song) {
        // its pitch and level from the file, not the caller
        double pl[6];
        r = nv_song_pitch_level_kc(song, n->song_index, K->init.effort_tilt != 0.0, K, pl);
        if (!r)
            return -2;
        n->f0 = pl[0]; n->vel = pl[1]; n->pan = pl[2]; n->chan_vol = pl[3]; n->effort = pl[4];
        if (n->press != 0.0)                // A KEY LEANED ON: PRESS_DB of effort (its level below)
            n->effort += 8.0 * n->press;
        if (K->brass && r == 1)             // the horn's intonation, from its fingering
            n->f0 *= pow(2.0, brass_cents(n->f0, K->brass == 2) / 1200.0);
        if (K->xf > 0.0 && r == 1) {        // A SOUND TRANSPOSED WHOLE (_XP): built at its kit's pitch
            n->xp = n->f0 / K->xf;
            n->f0 = K->xf;
            n->f0 *= nv_song_note_ratio(song, n->song_index);     // ...each stroke its own pitch (stroke_pitch)
        }
        if (K->organ && K->organ->swells)   // an organ's CC7 is its swell, its CC11 its stop word: 1, trimmed
            n->chan_vol = 1.0 * nv_song_note_trim(song, n->song_index);
        if (n->fx_set == 1) {               // ITS PART'S INSERTION EFFECT, the file's chain at its onset
            n->chan_vol *= n->fx_level;
            n->chan_vol *= n->fx_od != 0.0 ? n->fx_od : 1.0;
        } else if (n->fx_set == 0 && K->efx_set && r == 1 && !nv_moog_neutral()) {   // ITS OWN: its level, its OD stage's gain (not a live template's)
            n->chan_vol *= K->efx_level;
            n->chan_vol *= K->efx_od != 0.0 ? K->efx_od : 1.0;
        }
        if (r == 2)
            n->seat = pl[5];            // a drum: its seat in its set
        else if (K->key_pan_spread != 0.0)
            n->seat = K->key_pan_spread * (n->note - 60) / 30.0;   // a wide voice: its key's seat in the instrument
    }
    if (K->one_shot && K->gate_time > 0.0)  // ...unless it is gated: it stops where the gate closes
        n->key_off = K->held_texture ? nv::pymax(n->key_off, n->on + K->gate_time) : n->on + K->gate_time;
    else if (K->one_shot && r == 1)     // a melodic one-shot (a bar, a bell) rings until it is gone
        n->key_off = nv::pymax(n->key_off, n->on + one_shot_ring(K, n, rs));
    else if (K->one_shot)               // a one-shot rings out on its own decay (a kit's: the flat hold)
        n->key_off = nv::pymax(n->key_off, n->on + K->one_shot_hold);
    else if (K->tape_s > 0.0)           // A MELLOTRON's TAPE RUNS OUT: a key held past its strip falls silent
        n->key_off = nv::pymin(n->key_off, n->on + K->tape_s);
    if (n->siren_set)                   // A SIREN sounds while its rotor does (_SIREN_AT)
        n->key_off = nv::pymax(n->on + 1e-3, n->siren_end);
    if (K->osr_n && !K->one_shot)       // A PALM-MUTED OPEN STRING rings on till its string sounds again
        for (int q = 0; q < K->osr_n; q++)
            if ((double)n->note == K->osr_open[q]) {
                n->key_off = nv::pymax(n->key_off, nv_song_string_free(song, n->ch, n->note, n->on, K->osr_open,
                                                                       K->osr_n, K->osr_cap, 0.004));
                break;                  // (blockrender.RETRIGGER_FADE)
            }
    n->off = nv_song_note_off(song, n->ch, n->note, n->on, n->key_off, n->damper_pedal, n->mcut,
                              n->retrigger_fade, band);
    double ck;
    if (nv_song_choke(song, n->ch, n->note, n->on, &ck) && ck < n->off)
        n->off = ck;                        // an exclusive class: a later strike stops it
    n->has_nx = nv_song_next_same(song, n->ch, n->note, n->on, &n->nx);
    if (!n->has_nx)
        n->nx = 0.0;
    n->soft_pedal_down = nv_song_soft_at(song, n->ch, n->on);
    return nv_note(K, n, rs, nimg, nsurf, surf, img, mir, rows, cap, qacc, azimuth, out);
}

// THE BELLOWS' PUSH of a standalone voice (blockrender._push_finish with
// tonelib.bellows_push_weight, _rate, _env): each of the note's n rows
// again, at its partial's weight (by its harmonic number over f0, the tilt's
// law by octave) and the push's envelope dt seconds in (dt 0: a fresh push,
// rising over rise_s; past it, taken over at the slur's attack, sfa
// samples), falling at its own rate; into out (cap rows). The rows written,
// -1 if out was too small.
static long long push_rows(const NoteClass *k, double f0, double dt, double sfa, double sr, const double *src, long n,
                           double *out, long long cap)
{
    double eps = pow(10.0, k->push_settle_db / 20.0);
    double tilt = k->push_tilt + k->push_tilt_oct * log(nv::pymax(f0, 1e-9) / 440.0) / log(2.0);
    double fa = k->push_rise_s * sr;
    long long m = 0;
    for (long j = 0; j < n; j++) {
        const double *r = src + NCOLS * j;
        double h = r[11] / nv::pymax(f0, 1e-9);
        double g = k->push_gain * pow(10.0, 0.0 / 20.0);
        double w = g * pow(nv::pymax(h, 1.0), nv::pymax(tilt, 0.0));
        double rate = (k->push_gain <= eps || w <= eps) ? k->push_dbs
                                                        : k->push_dbs * log(w / eps) / log(k->push_gain / eps);
        double env = 1.0;
        if (dt > 0.0) {
            double rr = nv::pymax(k->push_rise_s, 1e-4);
            env = nv::pymin(1.0, dt / rr) * pow(10.0, -rate * dt / 20.0);
        }
        if (w * env <= 1e-4)
            continue;
        if (m >= cap)
            return -1;
        double *o = out + NCOLS * m;
        memcpy(o, r, sizeof(double) * NCOLS);
        o[3] *= w * env; o[4] *= w * env; o[5] *= w * env;
        o[14] = dt <= 0.0 ? fa : sfa;
        o[17] = rate * log(10.0) / 20.0;
        o[18] = 0.0; o[19] = 0.0; o[20] = 0.0;
        m++;
    }
    return m;
}

// blockrender's _src_dist: a note's distance as a multiple of its voice's
// own -- its part's first CC91 over GM's 40 or, where the part's CC91
// changes, the one in force at its onset (send_steps, step_at); else the
// voice's reverb_distance; else 1. At least 0.1.
static double song_dist(void *song, long long ch, double on, double sr, const NoteClass *k)
{
    long long part = ch % 256;
    int n = nv_song_ccs(song, part, 91, nullptr, nullptr, 0);
    double d = NAN;
    double ed;
    if (nv_song_efx_dist(song, part, on, &ed))
        return nv::pymax(0.1, ed);          // (a part's insertion effect: its send, not CC91's)
    if (n > 0) {
        std::vector<double> tt(n);
        std::vector<int> vv(n);
        nv_song_ccs(song, part, 91, tt.data(), vv.data(), n);
        d = vv[0] / 40.0;
        bool steps = false;
        for (int q = 1; q < n; q++)
            steps = steps || vv[q] != vv[0];
        if (steps) {
            // the last change at or before the onset's sample, before the first the first
            long long ns = (long long)nearbyint(on * sr);
            int q = -1;
            for (int j = 0; j < n; j++)
                if ((long long)nearbyint(tt[j] * sr) <= ns)
                    q = j;
            d = vv[q < 0 ? 0 : q] / 40.0;
        }
    }
    if (std::isnan(d) && k && k->rd_set)
        d = k->reverb_dist;     // ...else the voice's own (reverb_distance: the gunshot stands back)
    return std::isnan(d) ? 1.0 : nv::pymax(0.1, d);
}

// A SONG PLAYED: every note, in the note loop's order (by onset, channel and
// key, stably), each through nv_song_play with its class (K[128 * program +
// key], a drum set's from K[NV_K_DRUMS + ...]; every note must have one) -- the rows of the whole song's notes.
// tmpl: the emitter's constants for every note (rate, fades, Nyquist, the
// room's bands, REFLECT, the glide, vibrato and sound rows' rest state);
// br[channel]: the channel's fader row, -1 none; and, nbr 512, br[256 +
// channel] its bend row, which a voice that bends rides instead. The global random
// stream from rs, carried note to note; qacc and *azimuth too. *nrows the
// rows written. Returns the notes played; -(1 + i) where note i is not the
// engine's (no class, or nv_note's -2); NV_TOO_SMALL if the store was.
// WHY nv_play's last refusal (-(1 + i)): which of its checks, for the message
static const char *g_why = "";
extern "C" const char *nv_play_why(void) { return g_why; }
// A PARALLEL TYPE's copies: the table's column kinds (nv_play_full's: a copy
// is made of the rows as the table stores them; NULL makes none -- live's),
// and each copied note's own rows' end (its copy after them, to the next note's)
static const int *g_kind = nullptr;
static std::map<int, long long> g_own_end;
extern "C" void nv_play_set_kind(const int *kind) { g_kind = kind; }
extern "C" long long nv_play_own_end(int j, long long dflt)
{
    auto it = g_own_end.find(j);
    return it == g_own_end.end() ? dflt : it->second;
}

// THE STREAMING RENDER'S SINK (nv_play_set_sink): each note's rows handed
// over the moment they are final -- rows [i0, i1) in the whole table's
// numbering, at `at`, with the next note's onset as the song stores it (NAN
// after the last) -- after which the store is written from its start again,
// so it holds one note. NULL: the whole table, as before.
struct NvPlaySink {
    void *ctx;
    void (*note)(void *ctx, const double *at, long long i0, long long i1, double next_on);
};
static const NvPlaySink *g_sink = nullptr;
static int g_sink_ni = -1;              // (the song's note the sink is being handed)
extern "C" int nv_play_sink_note(void) { return g_sink_ni; }
void nv_play_set_sink(const void *s) { g_sink = (const NvPlaySink *)s; }
const void *nv_play_get_sink(void) { return g_sink; }
// WHAT A STREAM DOES NOT REPRODUCE (yet): every distinct thing met, in
// order, "; " between; the stream's caller renders the file whole instead
static char g_stream_why[1024];
void nv_stream_refuse(const char *why)
{
    if (strstr(g_stream_why, why))
        return;
    size_t n = strlen(g_stream_why);
    if (n && n + 2 < sizeof g_stream_why) {
        g_stream_why[n++] = ';';
        g_stream_why[n++] = ' ';
        g_stream_why[n] = 0;
    }
    for (size_t i = 0; n + 1 < sizeof g_stream_why && why[i]; i++)
        g_stream_why[n++] = why[i];
    g_stream_why[n] = 0;
}
const char *nv_stream_why(void) { return g_stream_why; }
void nv_stream_reset(void) { g_stream_why[0] = 0; }

int nv_play(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr, PyRandom *rs,
            double *rows, long long cap, double *qacc, double *azimuth, long long *nrows, int *played,
            long long *row0, int *bands, double *offs)
{
    nv_song_gliss(song, K);                 // the valved glisses walked (_prep_gliss), once
    nv_song_sym_reset(song);                // (the strings' drivers: this play's)
    nv_song_play_mark(song);                // (its rows, Moogs and echoes: this play's, a retry's too)
    nv_refl_memo_reset();                   // (each _prepare its own _RNORM)
    g_own_end.clear();
    int nn = nv_song_n_notes(song);
    std::vector<int> order(nn);
    std::vector<long long> chs(nn);
    std::vector<int> keys(nn);
    std::vector<double> ons(nn);
    for (int i = 0; i < nn; i++) {
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &chs[i], iv, dv);
        keys[i] = iv[0];
        ons[i] = dv[0];
        order[i] = i;
    }
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
        if (ons[a] != ons[b])
            return ons[a] < ons[b];
        if (chs[a] != chs[b])
            return chs[a] < chs[b];
        return keys[a] < keys[b];
    });
    long long total = 0;
    long long base = 0;                     // (the store's first row, in the table's numbering: a sink's)
    // THE SAME PLATE STRUCK AGAIN (fold_restrike; a gesture's plain strokes):
    // each note's next strike of its key (_next_same: the notes by onset,
    // latest first), the strokes with a shape of their own (by key and onset,
    // as stroke_pitch and stroke_tilt key them), and what each key's strike
    // leaves the next (_FOLD_STORE)
    const char *fev = getenv("TUNING_FOLD");
    const bool fold_on = !(fev && (!strcmp(fev, "0") || !strcmp(fev, "off") || !*fev));
    std::vector<double> next_same(nn, NAN);
    std::set<std::pair<int, double>> shaped;
    {
        std::vector<int> byon(nn);
        for (int q = 0; q < nn; q++)
            byon[q] = q;
        std::stable_sort(byon.begin(), byon.end(), [&](int a, int b) { return -ons[a] < -ons[b]; });
        std::map<std::pair<long long, int>, double> seen;
        std::map<std::pair<std::pair<long long, int>, double>, double> nx;
        for (int q : byon) {
            auto kk = std::make_pair(chs[q], keys[q]);
            auto it = seen.find(kk);
            if (it != seen.end())
                nx[std::make_pair(kk, ons[q])] = it->second;
            seen[kk] = ons[q];
            if (nv_song_stroked(song, q) && nv_song_note_shaped(song, q))
                shaped.insert(std::make_pair(keys[q], ons[q]));
        }
        for (int q = 0; q < nn; q++) {
            auto it = nx.find(std::make_pair(std::make_pair(chs[q], keys[q]), ons[q]));
            if (it != nx.end())
                next_same[q] = it->second;
        }
    }
    // (a plain stroke at t of note i's key and channel: a stroke there, no shape)
    std::map<std::tuple<long long, int, double>, int> stroke_at;
    for (int q = 0; q < nn; q++)
        if (nv_song_stroked(song, q))
            stroke_at[std::make_tuple(chs[q], keys[q], ons[q])] = 1;
    auto plain = [&](long long c, int key, double t) {
        return stroke_at.count(std::make_tuple(c, key, t)) && !shaped.count(std::make_pair(key, t));
    };
    std::map<std::pair<long long, int>, std::pair<double, std::vector<double>>> fold_store;
    nv_fold_begin(nullptr, 0, -1.0, 0.0);   // (no fold left over: a retry's, a refused note's)
    nv_fold_end(nullptr);
    std::map<long long, double> push_t0;    // each channel's bellows' push, when it began (_PUSH_T0)
    std::map<long long, double> ham_t0;     // each channel's last pick (_HAM_T0: hammer_legato)
    PyRandom rnd;                           // tonelib.RND_STREAM, as prepare reseeds it
    pyr_seed(&rnd, 0);
    double carry_radius = NAN;              // the emitter's radius note to note (an organ's last pipe)
    for (int j = 0; j < nn; j++) {
        int i = order[j];
        long long ch;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &ch, iv, dv);
        const NoteClass *k = (iv[2] < 0 || (iv[2] > 127 && !iv[3])) ? nullptr : K[nv_song_kidx(song, i)];
        if (!k) {
            g_why = "no class";
            return -(1 + i);
        }
        if (!nv_song_received(song, i))
            continue;                       // the kit told not to receive this key
        NoteIn n = *tmpl;
        n.ch = ch; n.note = iv[0]; n.on = dv[0]; n.key_off = dv[1];
        n.held = dv[1] - dv[0];             // how long the key was held
        n.vel = iv[1];
        n.damper_pedal = k->damper_pedal;
        n.mcut = 0; n.slurred = 0; n.slur_out = 0;
        int sl[2];
        if (nv_song_slur(song, i, sl)) {        // the file's slurs (_legato_ticks, _prep_slur_out)
            n.slurred = sl[0];
            n.slur_out = sl[1];
        }
        const int fsl = n.slurred;          // (the file's own: a hammer-on's)
        int ms = 0;
        {
            int mc = 0;                         // mono mode's handoffs (_MONO_CUT, _MONO_SLUR)
            nv_song_mono(song, i, &mc, &ms);
            n.mcut = mc;
            n.slurred = n.slurred || ms;
        }
        double glv[4];
        int is_gl = nv_song_gliss_note(song, i, glv);   // a valved gliss's step (_GLISS)
        n.gliss_lv = is_gl ? glv[0] : 0.0;
        if (is_gl)
            n.slurred = 1;                  // (not retongued: every step slurs)
        // A GUITAR'S LEGATO IS THE FRETTING HAND (hammer_legato): a note over
        // the one before hammered, carried on from the last pick; a picked
        // note starts the chain again
        n.hammered = 0; n.reslur = ms || is_gl; n.hammer_on = 0.0;
        if (k->hammer) {
            if (fsl && ham_t0.count(ch)) {
                n.hammered = 1;
                n.hammer_on = nv::pymax(0.0, dv[0] - ham_t0[ch]);
            } else {
                ham_t0[ch] = dv[0];
            }
        }
        n.channel = (double)nv_song_mix(song, i);      // (its tone's mix channel: em.channel)
        // the channel's fader -- not an organ's whose CC11 is its stop word and
        // CC7 its swell (its own rows: registration_blocks), as blockrender's
        // note takes em.fader_row
        n.br = (ch >= 0 && ch < nbr && !(k->organ && k->organ->swells)) ? br[ch] : -1.0;
        // (an MPE member's note rides its manager's fader: blockrender's _lk)
        double mpe_row = -1.0;
        int mpe_mgr = -1;
        const bool is_mpe = nv_song_mpe_of(song, i, &mpe_row, &mpe_mgr) != 0;
        if (is_mpe) {
            n.br = (mpe_mgr >= 0 && mpe_mgr < nbr && !(k->organ && k->organ->swells)) ? br[mpe_mgr] : -1.0;
            // AN MPE ZONE IS ONE INSTRUMENT: its amplifier, chorus and stem the
            // manager's channel (blockrender's em.channel = _mmgr)
            n.channel = (double)mpe_mgr;
        }
        n.fbr = n.br;                       // (the fader's: the other strings' row, off the wheel)
        n.sym_drv = k->sym_kind == 3 ? nv_song_sym_driver(song, (long long)n.channel, (int)sizeof(VoiceSnap))
                                     : nullptr;
        n.ring_on = 0;
        if (k->ring_n) {                    // ITS OTHER STRINGS, tuned as the notes are (_note_ring)
            double rtab[128];
            nv_song_note_table(song, ch, dv[0], k->indian, rtab);
            n.ring_on = 1;
            for (int q = 0; q < k->ring_n; q++) {
                double hf = k->ring_hz[q];
                int rk = (int)nearbyint(69.0 + 12.0 * log2(hf / 440.0));
                if (rk >= 0 && rk < 128 && rtab[rk] > 0.0)
                    hf = rtab[rk] * hf / (440.0 * pow(2.0, (rk - 69.0) / 12.0));
                n.ring_f[q] = hf;
            }
        }
        if (nbr > 256 && k->bendable && ch >= 0 && ch < 256 && br[256 + ch] >= 0.0)
            n.br = br[256 + ch];            // a voice that bends: its channel's bend row
        n.bbr_set = 0;
        if (nbr > 768 && ch >= 0 && ch < 256 && br[512 + ch] >= 0.0) {
            if (k->breath_p[5] > 0.0 || k->breath_p[0] > 0.0)
                n.br = br[512 + ch];        // the player's breath: the tone's level and pitch
            if (k->breath_p[2] > 0.0) {
                n.bbr_set = 1;              // ...and the breath noise's level, its own
                n.bbr = br[768 + ch];
            }
        }
        {
            double pnrow;
            if (nv_song_pn_row(song, i, &pnrow) && pnrow >= 0.0)
                n.br = pnrow;               // its own row: MIDI 2.0 per-note pitch that moves
        }
        if (is_mpe)
            n.br = mpe_row >= 0.0 ? mpe_row : n.fbr;   // MPE: the note's own row, or none (the fader's)
        double mrow;
        if (nv_song_meend_row(song, i, &mrow))
            n.br = mrow >= 0.0 ? mrow : n.fbr;  // the meend: the note's own row, or none (the fader's)
        double sir[3];
        n.siren_set = 0;
        if (nv_song_siren_of(song, i, sir)) {   // a siren's rotor: its row, its end
            n.br = sir[0];
            n.siren_set = 1;
            n.siren_end = sir[1];
        }
        n.n_alias = nv_song_alias_of(song, i, n.alias_br, 32);     // an aliasing sweep's rows, by harmonic
        if (k->organ) {                     // A REGISTERED ORGAN: its ranks as its registration leaves them
            // (one that bends: only a hit's, whose ranks ride no chest -- the
            // note's own bend row, nv_song_organ_note's br; or a siren's, whose
            // ranks ride its rotor's rows)
            bool bends = k->bendable && !k->tmpl.hit_n && !n.siren_set;
            if (bends || !nv_song_organ_note(song, i, k->organ->family, &n)) {
                g_why = bends ? "an organ that bends" : "no organ of its family on its channel";
                return -(1 + i);
            }
            if (n.siren_set && sir[2] >= 0.0)   // (a double siren: each row of holes on its own disc's row)
                for (int ri = 0; ri < k->organ->n_rank; ri++)
                    n.rank_br[ri] = (k->organ->siren_up >> ri) & 1 ? sir[2] : sir[0];
        }
        n.from_song = 1; n.song_index = i;
        n.press = nv_song_pressure(song, ch, iv[0], dv[0], dv[1]);    // (_pressure_of: to its key-up)
        if (is_mpe)                         // MPE: the louder of its own and its manager's (Appendix D)
            n.press = std::max(n.press, nv_song_pressure(song, mpe_mgr, -1, dv[0], dv[1]));
        n.dist = song_dist(song, ch, dv[0], n.sr, k);  // its distance: its part's CC91 (_src_dist)
        nv_song_gs_eq_of(song, ch % 256, n.gs_eq);     // the file's GS EQ, its part's (gsefx.part_of)
        {
            // ITS PART ON THE FILE'S INSERTION EFFECT (_EFXN): the chain its onset finds
            const double *fc = nullptr;
            int fx = nv_song_note_fx(song, i, &fc);
            n.fx_set = fx >= 0 ? 1 : fx == -2 ? 2 : 0;
            if (fx >= 0) {
                n.fx_level = fc[0];
                n.fx_od = fc[1];
                n.fx_comp[0] = fc[3]; n.fx_comp[1] = fc[4]; n.fx_comp[2] = fc[5];
                n.fx_p3d = fc[22] != 0.0;
                if (n.fx_p3d) {
                    // (math.radians(((az + 360 turn on + 180) % 360) - 180): Python's %, the divisor's sign)
                    double x = fmod(fc[23] + 360.0 * fc[24] * dv[0] + 180.0, 360.0);
                    if (x != 0.0 && x < 0.0)
                        x += 360.0;
                    n.fx_angle = (x - 180.0) * (M_PI / 180.0);
                }
            }
        }
        n.sung_hz = nv_song_tess(song, ch);     // a sung part's tessitura, its declared part (_prep_choir_parts)
        n.part = nv_song_part(song, ch);
        double pv[3];
        nv_song_note_voice(song, i, pv);    // a throat's pulse: its tilt, mouth and vowel
        n.stroke_tilt = pv[0]; n.stroke_mouth = pv[1]; n.stroke_morph = pv[2];
        double det = 1.0;
        int c1;
        if (k->detune_wheel && nv_song_first_cc(song, ch, NV_CC_DETUNE, &c1))
            det = c1 / 64.0;
        n.detune_lo = k->detune_lo * det; n.detune_hi = k->detune_hi * det;
        memcpy(n.planes, k->room_planes, sizeof n.planes);
        n.order = k->room_order;
        n.no_reflections = 0;
        // CC71-78 AT ITS ONSET (_snd_d), from the class's own starting point,
        // those it answers: its times and its vibrato here; its colour (CC71,
        // 74, 75) on its rows once they are made (_snd_finish, below)
        double sd[8];
        nv_song_sound(song, ch, dv[0], sd);
        bool has[8];
        for (int q = 0; q < 8; q++) {
            sd[q] += k->snd_bias[q];
            has[q] = ((k->snd_mask >> q) & 1) && sd[q] != 0.0;
        }
        // (a Moog's: its knobs, moog.apply_gm -- on a channel whose cutoff or
        // resonance does not move after it is first set, _kn_moves)
        n.snd_moog = 0;
        bool kmoves = false;                    // (its knob rows a timeline: _MOOG_KVAR)
        if (k->init.kind == 6) {
            kmoves = nv_song_snd_moves(song, ch) != 0;
            for (int q = 0; q < 8; q++) {
                n.snd_d[q] = has[q] ? sd[q] : 0.0;
                n.snd_moog = n.snd_moog || has[q];
            }
        }
        n.snd_rt = has[1] ? pow(k->snd_time_range, sd[1]) : 0.0;
        n.snd_at = has[2] ? pow(k->snd_time_range, sd[2]) : 0.0;
        n.sv[1] = has[5] ? pow(k->snd_rate_range, sd[5]) : tmpl->sv[1];
        n.sv[0] = has[6] ? sd[6] : tmpl->sv[0];
        n.vibrato_delay = has[7] ? nv::pymax(0.0, sd[7]) * k->snd_delay_s : tmpl->vibrato_delay;
        // ITS GLIDE (the note's portamento: _GLIDE_SRC), where its mechanism
        // reaches -- the tuning table's own ratio, at the CC5 in force
        int cc5 = 0, src = nv_song_glide(song, i, &cc5);
        // A GLISS STEP's SMEAR: each rung arrives from the one below, its
        // glide the step's time x the smear x 0.75 (_GLISS), where it is past 2 ms
        if (is_gl && glv[1] > 0.0 && glv[2] >= 0.0) {
            double stau = glv[3] * glv[1] * 0.75;
            double tab[128];
            nv_song_note_table(song, ch, dv[0], k->indian, tab);
            int pv = (int)glv[2];
            if (stau > 2e-3 && tab[pv] > 0.0) {
                n.gl[0] = tab[iv[0]] / tab[pv] - 1.0;
                n.gl[1] = stau;
                n.gl[2] = stau * k->porta_settle;
            }
        }
        if (n.gl[0] == 0.0 && src >= 0 && k->glide_mech) {
            double tab[128];
            nv_song_note_table(song, ch, dv[0], k->indian, tab);
            if (src < 128 && tab[src] > 0.0
                && (std::isnan(k->glide_reach) || std::abs(iv[0] - src) <= k->glide_reach + 1e-9)) {
                double ft = tab[iv[0]], fs = tab[src];
                double v = nv::pymin(127.0, nv::pymax(0.0, (double)cc5)) / 127.0;
                double t1 = k->porta_fast * pow(k->porta_slow / k->porta_fast, v);
                double tau = k->glide_mech == 2 ? nv::pymax(1e-4, t1)
                                                : nv::pymax(1e-4, t1 * fabs(1.0 / fs - 1.0 / ft) / k->porta_d_semi);
                n.gl[0] = ft / fs - 1.0;
                n.gl[1] = tau;
                n.gl[2] = tau * k->porta_settle;
            }
        }
        if (k->init.rnd) {                  // RandomStrike's draws, from the [RND] stream's
            n.rnd_draws[0] = pyr_gauss(&rnd, 0.0, k->init.rnd_level_db);
            n.rnd_draws[1] = pyr_gauss(&rnd, 0.0, k->init.rnd_effort_db);
            n.rnd_draws[2] = pyr_gauss(&rnd, 0.0, k->init.rnd_cents);
            n.rnd_draws[3] = pyr_uniform(&rnd, 0.0, k->init.rnd_timing_s);
        }
        n.carry_radius = carry_radius;
        // A MOOG: its filter rows from here (_MOOG_FT) -- where nothing turns
        // its knobs: GM's sound controllers on its channel are Python's (apply_gm)
        if (k->init.kind == 6)
            n.fx = (double)nv_song_moog_n(song);
        NoteOut out;
        int band = 0;
        long long left = cap - (total - base);
        // (the fold: this strike's take of the one before, and its own left to the next)
        bool fold_out = false;
        const bool folds = fold_on && (k->fold_restrike || plain(ch, iv[0], dv[0]));    // (a gong's, or a plain stroke)
        if (folds) {
            std::vector<double> fin;
            auto fs = fold_store.find(std::make_pair(ch, iv[0]));
            if (fs != fold_store.end()) {
                if (fabs(fs->second.first - dv[0]) < 1e-6)
                    fin = fs->second.second;
                fold_store.erase(fs);
            }
            double n2 = -1.0;
            const double nx2 = next_same[i];
            if (!std::isnan(nx2) && (k->fold_restrike || plain(ch, iv[0], nx2))) {
                n2 = (double)(long long)(nx2 * n.sr);
                const double at0 = k->init.attack_time != 0.0 ? k->init.attack_time : 0.004;
                nv_fold_begin(fin.data(), (int)(fin.size() / 8), n2, std::max(32.0, at0 * n.sr));
                fold_out = true;
                fold_store[std::make_pair(ch, iv[0])] = std::make_pair(nx2, std::vector<double>());
            } else {
                nv_fold_begin(fin.data(), (int)(fin.size() / 8), -1.0, 0.0);
            }
        }
        int r = nv_song_play(song, k, &n, rs, -1, nullptr, nullptr, nullptr, nullptr, rows + NCOLS * (total - base),
                             (int)(left > 0x7fffffff ? 0x7fffffff : left), qacc, azimuth, &out, &band);
        if (folds) {
            std::vector<double> fo((size_t)8 * nv_fold_pending());
            nv_fold_end(fo.empty() ? nullptr : fo.data());
            if (fold_out)
                fold_store[std::make_pair(ch, iv[0])].second = fo;
        }
        if (r == -1)
            return NV_TOO_SMALL;
        if (r < 0) {
            g_why = "the voice refused it";
            return -(1 + i);
        }
        carry_radius = out.radius;
        // CC71, 74, 75 ON THE NOTE (_snd_finish): its rows' decay by CC75's
        // time scale, its colour by sound_shape over its partials, the power
        // kept -- live's law (Slab's reshape) on the finished rows (doubles, as
        // the table keeps them till its cast). Not a Moog's (its knobs), nor the bellows' push
        // (_push_finish's, made after)
        if (k->init.kind != 6 && (has[0] || has[3] || has[4]) && r - out.n_push > 0) {
            enum { cAL = 3, cAR = 4, cAM = 5, cNF = 11, cLOGR = 17, cLOGRA = 18 };
            long m = (long)(r - out.n_push);
            double *rw = rows + NCOLS * (total - base);
            if (has[4]) {
                double kk = 1.0 / pow(k->snd_time_range, sd[4]);
                for (long j = 0; j < m; j++) {
                    rw[NCOLS * j + cLOGR] *= kk;
                    rw[NCOLS * j + cLOGRA] *= kk;
                }
            }
            if (has[3] || has[0]) {
                std::vector<double> nf(m), am(m), g(m);
                for (long j = 0; j < m; j++) {
                    nf[j] = rw[NCOLS * j + cNF];
                    am[j] = rw[NCOLS * j + cAM];
                }
                nv_sound_shape(k, nf.data(), m, has[3] ? sd[3] : 0.0, has[0] ? sd[0] : 0.0, (k->snd_mask >> 3) & 1,
                               k->snd_mask & 1, g.data());
                nv_normalise_power(am.data(), m, g.data());
                for (long j = 0; j < m; j++)
                    for (int c : {cAL, cAR, cAM})
                        rw[NCOLS * j + c] *= g[j];
            }
        }
        long long lr0 = total;                  // (its layers' rows, from its first: an MF-104M's)
        for (int l = 0; l < out.n_ft; l++) {   // (its layers' filter rows, each on its knob row)
            const MoogLayer &L = k->moog.L[l];
            if (L.mf_on && !nv_moog_neutral())  // (not into a live template: live stamps its own repeats)
                nv_song_add_mf104(song, lr0, lr0 + out.lay_rows[l], &L);
            lr0 += out.lay_rows[l];
            double rs = L.rel_span;
            if (n.snd_moog) {                   // (the release its knob turned: release_span)
                MoogLayer La;
                nv_moog_apply(&L, n.snd_d, &La);
                rs = La.rel_span;
            }
            if (kmoves)
                nv_song_moog_add_moving(song, ch, out.ft[l], &L, (const void *)k, l, k->snd_bias, k->snd_mask, n.sr,
                                        out.non, out.noff, out.noff + rs * n.sr + 4096.0);
            else
                nv_song_moog_add(song, ch, out.ft[l], out.kn[l], &L, out.non, out.noff,
                                 out.noff + rs * n.sr + 4096.0);
        }
        if (out.n_click)                    // the key-up's rows, the note's last (rel_rows)
            nv_song_add_rel_rows(song, total + r - out.n_click, total + r);
        if (out.grain1 > out.grain0)        // its grains' (_GRAIN_ROWS)
            nv_song_add_grain_rows(song, total + out.grain0, total + out.grain1);
        if (out.n_jack) {                   // each jack's click rows, the note's last (rel_jacks)
            long long j0 = total + r - out.n_click;
            for (int q = 0; q < out.n_jack; q++) {
                if (out.jack_rank[q] >= 0 && out.jack_n[q])
                    nv_song_add_rel_jack(song, j0, j0 + out.jack_n[q], out.jack_rank[q], out.jack_off[q]);
                j0 += out.jack_n[q];
            }
        }
        // A PLAYER'S BELLOWS (a standalone voice's push: _push_finish): a note
        // from silence pushes; a slur takes the push over where it stands
        if (k->push_gain > 0.0 && !k->organ) {
            double dt = -1.0, sfa = 0.0;
            if (!n.slurred) {
                push_t0[ch] = dv[0];
                dt = 0.0;
            } else if (push_t0.count(ch)) {
                dt = dv[0] - push_t0[ch];
                double at = k->init.attack_time;
                if (k->legato_set)
                    at = nv::pymin(at, k->legato_attack_s);     // (slur_attack)
                sfa = at * n.sr;
            }
            if (dt >= 0.0) {
                long long m = push_rows(k, out.f0, dt, sfa, n.sr, rows + NCOLS * (total - base), r,
                                        rows + NCOLS * (total + r - base), left - r);
                if (m < 0)
                    return NV_TOO_SMALL;
                if (m)
                    nv_song_add_push_rows(song, total + r, total + r + m);
                r += (int)m;
            }
        }
        if (out.n_push)                     // (an organ's push: the tone's last rows)
            nv_song_add_push_rows(song, total + out.n_knock + out.n_tone - out.n_push,
                                  total + out.n_knock + out.n_tone);
        // A PARALLEL TYPE's NOTE (gsefx.PARALLEL_TYPES, blockrender._par_close):
        // its rows branch A's, at A's pan; a copy of them as the table stores
        // them (cast), at branch B's level and pan, on the part's virtual
        // channel (+ gsefx.VIRT), after them
        long long cp = 0;
        {
            const double *fc = nullptr;
            if (g_kind && r > 0 && nv_song_note_fx(song, i, &fc) >= 0 && fc[208] != 0.0) {
                if (2 * (long long)r > left)
                    return NV_TOO_SMALL;
                enum { cAL = 3, cMCH = 6 };
                const double gb[3] = {fc[209] * fc[212], fc[209] * fc[213], fc[209] * 1.0};
                const double ga[2] = {fc[210], fc[211]};
                double *src = rows + NCOLS * (total - base), *dst = rows + NCOLS * (total + r - base);
                for (long long q = 0; q < r; q++) {
                    const double *s = src + NCOLS * q;
                    double *d = dst + NCOLS * q;
                    for (int c = 0; c < NCOLS; c++)
                        d[c] = g_kind[c] == 1 ? (double)(float)s[c] : g_kind[c] == 2 ? (double)(int32_t)s[c] : s[c];
                    d[cMCH] = (double)(ch + 65536);
                    for (int w = 0; w < 3; w++)         // (a float32 column scaled in float32: numpy's)
                        d[cAL + w] = g_kind[cAL + w] == 1 ? (double)((float)d[cAL + w] * (float)gb[w])
                                                          : d[cAL + w] * gb[w];
                }
                if (ga[0] != 1.0 || ga[1] != 1.0)      // (A's own pan, on its rows)
                    for (long long q = 0; q < r; q++)
                        for (int w = 0; w < 2; w++) {
                            double *v = src + NCOLS * q + cAL + w;
                            *v = (g_kind[cAL + w] == 1 ? (double)(float)*v : *v) * ga[w];
                        }
                g_own_end[j] = total + r;
                cp = r;
            }
        }
        if (played) {
            played[j] = i;
            row0[j] = total;
        }
        if (bands) {
            bands[j] = band;            // a half-pedalled note meeting the band: its track
            offs[j] = n.off;            // ...and where its damper lands (its end)
        }
        g_sink_ni = i;
        if (g_sink)
            g_sink->note(g_sink->ctx, rows + NCOLS * (total - base), total, total + r + cp,
                         j + 1 < nn ? ons[order[j + 1]] : NAN);
        total += r + cp;
        if (g_sink)
            base = total;
    }
    *nrows = total;
    return nn;
}

}  // extern "C"
