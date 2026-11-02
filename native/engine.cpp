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
    double av = pow(n->vel / 127.0, 2.0);
    VoiceSnap s;
    VoiceNote o;
    nv_voice_init(&c, &K->tmpl, n->f0, n->pan, av, n->chan_vol, n->effort, rs, &s, &o);
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

    int total = 0, no_refl = n->no_reflections;

    // THE HAMMER'S KNOCK (_note_strike_noise): noise rows, no images
    out->n_knock = 0;
    if (K->n_strike) {
        double sf0 = K->strike_span_set ? pymin(pymax(f0, K->strike_span_lo), K->strike_span_hi) : f0;
        double reg = K->strike_octave_db * log2(pymax(sf0, 1.0) / 440.0);
        double slr = log(10.0) / 20.0 * K->strike_noise_dbs;
        double sfade = pymax(1.0, K->strike_fade_s * SR);
        double slen = K->strike_len_s * SR;
        // A FLAM (strike_flam > 1): that many strikes, each at its own offset
        // and level, drawn from the note (random.Random of its onset, key and
        // channel), the first at the onset and the loudest at the table's
        double boff[64], bdb[64];
        int nb = 1;
        boff[0] = bdb[0] = 0.0;
        if (K->n_flam > 1) {
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
            int k = nv_strike(&s, &tk, K->n_strike, K->strike_hz, K->strike_db, reg, bdb[b], K->strike_cal_db,
                              slr, sfade, slen, bon, s.position_x, rows + NCOLS * total, cap - total, qacc, azimuth);
            if (k < 0)
                return -1;
            out->n_knock += k;
            total += k;
        }
        no_refl = 0;
    }

    // THE ROOM'S IMAGES of the voice where it stands (_images_for)
    int nsurf_[64], surf_[64 * 8];
    double img_[3 * 64], mir_[3 * 64];
    if (nimg < 0) {
        if (n->order > 8)
            return -2;
        nimg = nv_images(n->planes, n->order, s.position_x * 1.0, s.radiation_distance * 1.0, s.position_z * 1.0,
                         64, nsurf_, surf_, img_, mir_);
        if (nimg < 0)
            return -2;                      // more than 64 images: not the engine's
        nsurf = nsurf_; surf = surf_; img = img_; mir = mir_;
    }

    // THE TONE (_note_stops, one stop at gain 1)
    int reflect = n->reflect && !no_refl && K->reflection_order;
    t.gain = 1.0; t.B = B; t.sjit = o.sustain_jitter; t.reflect = reflect;
    t.cbw0 = K->cbw0; t.cbw1 = K->cbw1;
    t.pjit = K->pjit; t.sps = K->sps; t.dur = dur; t.ssc = K->ssc;
    double trans[3 * 1025];
    int ntr = 0;
    if (s.max_harmonic + 1 > 1025)
        return -2;
    double sjit_last = o.sustain_jitter;        // (the note's sjit after its partials)
    int k = nv_tone_rs(&s, &t, reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total, cap - total,
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

    out->non = non; out->noff = noff; out->fade = fade; out->rel = rel; out->chiff = chiff;
    out->jitter_scale = t.jitter_scale;
    out->dl = t.dl; out->dr = t.dr; out->li = t.li; out->ri = t.ri;
    out->pos_x = s.position_x; out->pos_z = s.position_z; out->B = B;
    out->cv = t.cv; out->cc = t.cc; out->crl = t.crl; out->sjit = sjit_last; out->csc = t.csc;
    memcpy(out->tb, tb, sizeof tb);
    out->cbw[0] = K->cbw0; out->cbw[1] = K->cbw1;
    return total;
}

// A note as its FILE gives it: its channel's answers (native/channel.cpp's
// Song) for its end once the pedals have had their say, its key's next
// strike and the soft pedal at its onset, then nv_note. n's off, nx and
// soft pedal are written; *band: a half-pedalled note that meets the band.
int nv_song_play(void *song, const NoteClass *K, NoteIn *n, PyRandom *rs,
                 int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
                 double *rows, int cap, double *qacc, double *azimuth, NoteOut *out, int *band)
{
    if (K->one_shot && K->gate_time > 0.0)  // ...unless it is gated: it stops where the gate closes
        n->key_off = K->held_texture ? nv::pymax(n->key_off, n->on + K->gate_time) : n->on + K->gate_time;
    else if (K->one_shot)               // a one-shot rings out on its own decay
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
    if (n->from_song) {
        // its pitch and level from the file, not the caller
        double pl[6];
        int r = nv_song_pitch_level(song, n->song_index, K->init.effort_tilt != 0.0, pl);
        if (!r)
            return -2;
        n->f0 = pl[0]; n->vel = pl[1]; n->pan = pl[2]; n->chan_vol = pl[3]; n->effort = pl[4];
        if (r == 2)
            n->seat = pl[5];            // a drum: its seat in its set
    }
    return nv_note(K, n, rs, nimg, nsurf, surf, img, mir, rows, cap, qacc, azimuth, out);
}

// A SONG PLAYED: every note, in the note loop's order (by onset, channel and
// key, stably), each through nv_song_play with its class (K[128 * program +
// key], a drum set's from K[NV_K_DRUMS + ...]; every note must have one) -- the rows of the whole song's notes.
// tmpl: the emitter's constants for every note (rate, fades, Nyquist, the
// room's bands, REFLECT, the glide, vibrato and sound rows' rest state);
// br[channel]: the channel's bend (or fader) row, -1 none. The global random
// stream from rs, carried note to note; qacc and *azimuth too. *nrows the
// rows written. Returns the notes played; -(1 + i) where note i is not the
// engine's (no class, or nv_note's -2); NV_TOO_SMALL if the store was.
int nv_play(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr, PyRandom *rs,
            double *rows, long long cap, double *qacc, double *azimuth, long long *nrows, int *played,
            long long *row0, int *bands, double *offs)
{
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
        n.vel = iv[1];
        n.damper_pedal = k->damper_pedal;
        n.mcut = 0; n.slurred = 0; n.slur_out = 0;
        int sl[2];
        if (nv_song_slur(song, i, sl)) {        // the file's slurs (_legato_ticks, _prep_slur_out)
            n.slurred = sl[0];
            n.slur_out = sl[1];
        }
        n.channel = (double)ch;
        n.br = (ch >= 0 && ch < nbr) ? br[ch] : -1.0;
        n.from_song = 1; n.song_index = i;
        double det = 1.0;
        int c1;
        if (k->detune_wheel && nv_song_first_cc(song, ch, 1, &c1))
            det = c1 / 64.0;
        n.detune_lo = k->detune_lo * det; n.detune_hi = k->detune_hi * det;
        memcpy(n.planes, k->room_planes, sizeof n.planes);
        n.order = k->room_order;
        n.no_reflections = 0;
        NoteOut out;
        int band = 0;
        long long left = cap - total;
        int r = nv_song_play(song, k, &n, rs, -1, nullptr, nullptr, nullptr, nullptr, rows + NCOLS * total,
                             (int)(left > 0x7fffffff ? 0x7fffffff : left), qacc, azimuth, &out, &band);
        if (r == -1)
            return NV_TOO_SMALL;
        if (r < 0)
            return -(1 + i);
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
