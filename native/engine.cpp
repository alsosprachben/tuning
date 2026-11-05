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
#include <cmath>
#include <cstring>
#include <map>
#include <vector>

#include "nv.h"
#include "pycompat.h"          // a flam's random.Random

namespace nv {

static double pymin(double a, double b) { return b < a ? b : a; }
static double pymax(double a, double b) { return b > a ? b : a; }

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
    if (n->slurred && K->legato_set)
        at = pymin(at, K->legato_attack_s);
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
    t.jitter_scale = (1.0 + o.pitch_jitter) * 1.0;
    t.nyq_om = n->nyq_om;
    t.dl = o.left_hrtf_delay * SR; t.dr = o.right_hrtf_delay * SR;
    t.pos_x0 = t.pos_x_props = s.position_x;
    t.pos_z = s.position_z;
    t.channel = n->channel;
    memcpy(t.tb, tb, sizeof tb);
    memcpy(t.gl, n->gl, sizeof t.gl);
    memcpy(t.sv, n->sv, sizeof t.sv);
    t.sound_vib_depth_cents = n->sound_vib_depth_cents; t.vibrato_delay = n->vibrato_delay;
    t.br = n->br; t.fx = n->fx; t.mk = n->mk; t.fm_omega = n->fm_omega; t.fm_phase = n->fm_phase;
    t.listener_distance = c.listener_distance; t.head_radius = c.head_radius; t.pan_angle = o.pan_angle;
    memcpy(t.room_bands, n->room_bands, sizeof t.room_bands);
    t.rev = K->played_backwards;            // (em.reverse: its rows emitted backwards)
    t.rev_n0 = non; t.rev_arr = noff;
    memcpy(t.planes, n->planes, sizeof t.planes);
    t.order = n->order;
    t.dist = n->dist;
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
        double boff[64], bdb[64], bgl[64], bgr[64];
        int nb = 1;
        boff[0] = bdb[0] = 0.0;
        for (int b = 0; b < 64; b++)
            bgl[b] = bgr[b] = 1.0;
        if (K->n_ft) {
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
        } else if (K->n_flam > 1) {
            if (K->n_flam > 64)
                return -2;
            PyRandom fr;
            pyr_seed(&fr, (long long)nearbyint(n->on * 1e6) * 131 + (long long)n->note * 7 + n->ch);
            nb = K->n_flam;
            for (int b = 0; b < nb; b++) {
                boff[b] = pyr_uniform(&fr, 0.0, K->flam_s);
                bdb[b] = -pyr_uniform(&fr, 0.0, K->flam_db);
            }
            double t0 = boff[0], l0 = bdb[0];
            for (int b = 1; b < nb; b++) {
                t0 = pymin(t0, boff[b]);
                l0 = pymax(l0, bdb[b]);
            }
            for (int b = 0; b < nb; b++) {
                boff[b] -= t0;
                bdb[b] -= l0;
            }
        }
        ToneIn tk = t;
        tk.gain = s.gain; tk.B = 0.0; tk.sjit = 0.0; tk.reflect = 0;
        tk.cbw0 = -0.25; tk.cbw1 = 0.0;
        out->n_knock = 0;
        for (int b = 0; b < nb; b++) {
            double bon = non + K->strike_at_s * SR + boff[b] * SR;
            int k = nv_strike_bal(&s, &tk, K->n_strike, K->strike_hz, K->strike_db, reg, bdb[b], K->strike_cal_db,
                                  slr, sfade, slen, bon, s.position_x, bgl[b], bgr[b], rows + NCOLS * total,
                                  cap - total, qacc, azimuth);
            if (k < 0)
                return -1;
            out->n_knock += k;
            total += k;
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

    // THE TONE (_note_stops, one stop at gain 1): its partials radiate as themselves
    t.radius = 0.0;
    t.has_radius = 0;
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
        r = nv_song_pitch_level(song, n->song_index, K->init.effort_tilt != 0.0, pl);
        if (!r)
            return -2;
        n->f0 = pl[0]; n->vel = pl[1]; n->pan = pl[2]; n->chan_vol = pl[3]; n->effort = pl[4];
        if (K->brass && r == 1)             // the horn's intonation, from its fingering
            n->f0 *= pow(2.0, brass_cents(n->f0, K->brass == 2) / 1200.0);
        if (K->organ && K->organ->swells)   // an organ's CC7 is its swell, its CC11 its stop word: 1, trimmed
            n->chan_vol = 1.0 * nv_song_note_trim(song, n->song_index);
        if (r == 2)
            n->seat = pl[5];            // a drum: its seat in its set
    }
    if (K->one_shot && K->gate_time > 0.0)  // ...unless it is gated: it stops where the gate closes
        n->key_off = K->held_texture ? nv::pymax(n->key_off, n->on + K->gate_time) : n->on + K->gate_time;
    else if (K->one_shot && r == 1)     // a melodic one-shot (a bar, a bell) rings until it is gone
        n->key_off = nv::pymax(n->key_off, n->on + one_shot_ring(K, n, rs));
    else if (K->one_shot)               // a one-shot rings out on its own decay (a kit's: the flat hold)
        n->key_off = nv::pymax(n->key_off, n->on + K->one_shot_hold);
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
    (void)k;                    // (a voice's own reverb_distance: none is the engine's -- native.note_class)
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
int nv_play(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr, PyRandom *rs,
            double *rows, long long cap, double *qacc, double *azimuth, long long *nrows, int *played,
            long long *row0, int *bands, double *offs)
{
    nv_refl_memo_reset();                   // (each _prepare its own _RNORM)
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
    std::map<long long, double> push_t0;    // each channel's bellows' push, when it began (_PUSH_T0)
    PyRandom rnd;                           // tonelib.RND_STREAM, as prepare reseeds it
    pyr_seed(&rnd, 0);
    double carry_radius = NAN;              // the emitter's radius note to note (an organ's last pipe)
    for (int j = 0; j < nn; j++) {
        int i = order[j];
        long long ch;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &ch, iv, dv);
        const NoteClass *k = (iv[2] < 0 || iv[2] > 127) ? nullptr : K[(iv[3] ? NV_K_DRUMS : 0) + 128 * iv[2] + iv[0]];
        if (!k)
            return -(1 + i);
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
        n.channel = (double)nv_song_mix(song, i);      // (its tone's mix channel: em.channel)
        if (k->organ && (long long)n.channel != ch)
            return -(1 + i);                    // (an organ after another tone on its channel: its tremolo's Python's)
        n.br = (ch >= 0 && ch < nbr) ? br[ch] : -1.0;
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
        if (k->organ) {                     // A REGISTERED ORGAN: its ranks as its registration leaves them
            // (one that bends: only a hit's, whose ranks ride no chest -- the
            // note's own bend row, nv_song_organ_note's br)
            if ((k->bendable && !k->tmpl.hit_n) || !nv_song_organ_note(song, i, k->organ->family, &n))
                return -(1 + i);
        }
        n.from_song = 1; n.song_index = i;
        n.dist = song_dist(song, ch, dv[0], n.sr, k);  // its distance: its part's CC91 (_src_dist)
        n.sung_hz = nv_song_tess(song, ch);     // a sung part's tessitura, its declared part (_prep_choir_parts)
        n.part = nv_song_part(song, ch);
        double pv[3];
        nv_song_note_voice(song, i, pv);    // a throat's pulse: its tilt, mouth and vowel
        n.stroke_tilt = pv[0]; n.stroke_mouth = pv[1]; n.stroke_morph = pv[2];
        double det = 1.0;
        int c1;
        if (k->detune_wheel && nv_song_first_cc(song, ch, 1, &c1))
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
        if (src >= 0 && k->glide_mech) {
            if (k->glide_mech == 3 && std::abs(iv[0] - src) >= 2)
                return -(1 + i);            // a valved gliss: a run of notes (_prep_gliss), Python's
            double tab[128];
            nv_song_table(song, ch, dv[0], tab);
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
        long long left = cap - total;
        int r = nv_song_play(song, k, &n, rs, -1, nullptr, nullptr, nullptr, nullptr, rows + NCOLS * total,
                             (int)(left > 0x7fffffff ? 0x7fffffff : left), qacc, azimuth, &out, &band);
        if (r == -1)
            return NV_TOO_SMALL;
        if (r < 0)
            return -(1 + i);
        carry_radius = out.radius;
        // CC71, 74, 75 ON THE NOTE (_snd_finish): its rows' decay by CC75's
        // time scale, its colour by sound_shape over its partials, the power
        // kept -- live's law (Slab's reshape) on the finished rows (doubles, as
        // the table keeps them till its cast). Not a Moog's (its knobs), nor the bellows' push
        // (_push_finish's, made after)
        if (k->init.kind != 6 && (has[0] || has[3] || has[4]) && r - out.n_push > 0) {
            enum { cAL = 3, cAR = 4, cAM = 5, cNF = 11, cLOGR = 17, cLOGRA = 18 };
            long m = (long)(r - out.n_push);
            double *rw = rows + NCOLS * total;
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
                long long m = push_rows(k, out.f0, dt, sfa, n.sr, rows + NCOLS * total, r,
                                        rows + NCOLS * (total + r), left - r);
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
        if (played) {
            played[j] = i;
            row0[j] = total;
        }
        if (bands) {
            bands[j] = band;            // a half-pedalled note meeting the band: its track
            offs[j] = n.off;            // ...and where its damper lands (its end)
        }
        total += r;
    }
    *nrows = total;
    return nn;
}

}  // extern "C"
