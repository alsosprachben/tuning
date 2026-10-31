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

#include <cmath>
#include <cstring>

#include "nv.h"

namespace nv {

static double pymin(double a, double b) { return b < a ? b : a; }
static double pymax(double a, double b) { return b > a ? b : a; }

}  // namespace nv

extern "C" {

// What a voice class is to a note's setup: the constructor's constants and
// the class's VoiceSnap, the attack/release/chiff laws, the tension bend and
// the hammer's knock (strike_noise_db). "_set" flags carry Python's None.
typedef struct {
    VoiceInit init;
    VoiceSnap tmpl;
    double chiff_max_valve_time;
    int release_valve_set;
    double release_valve_time;
    double speech_cycles;
    int legato_set;
    double legato_attack_s;
    double attack_fraction_max;
    int release_fraction_set;
    double release_fraction_max;
    int slur_cuts_release;
    int chiff_width_set;
    double chiff_width, chiff_width_cycles;
    double chiff_volume, chiff_cycle, chiff_release, sustain_jitter;
    double cbw0, cbw1;                  // chiff_bandwidth or RAND_GRAN, chiff_bandwidth_hz or 0
    double tension_bend_power;
    int tension_bend_slurs;
    double tension_settle_time, tension_settle_cutoff;
    int tension_log;
    double tbend_cut_scale;
    double sustain_level;
    int reflection_order;
    int n_strike;                       // the knock's bands (0: none)
    double strike_hz[32], strike_db[32];
    double strike_noise_dbs;
    int strike_span_set;
    double strike_span_lo, strike_span_hi;
    double strike_octave_db;            // strike_noise_octave_db, else strike_noise_slope
    double strike_fade_s, strike_len_s, strike_at_s, strike_cal_db;
} NoteClass;

// A note, as its file and channel give it, and the emitter's state for it.
typedef struct {
    double f0, pan, vel, chan_vol, effort, on, off, nx;
    int has_nx, mcut, slurred, slur_out;
    double detune_lo, detune_hi;        // string_detune_range, the honky-tonk's wheel applied
    int soft_pedal_down, fixed_touch;
    double sr, retrigger_fade, channel, br, nyq_om;
    double sv[2], sound_vib_depth_cents, vibrato_delay, gl[3];
    double fx, mk, fm_omega, fm_phase;
    double room_bands[9];
    int reflect, no_reflections;        // the emitter's REFLECT, and no_reflections before the note
    // for nv_song_play: the note's key in its file, and its key-up
    long long ch;
    int note, damper_pedal;
    double key_off;
} NoteIn;

// What the note's setup worked out, beside its rows.
typedef struct {
    int n_knock, n_tone, n_phantom;
    double non, noff, fade, rel, chiff, jitter_scale;
    double dl, dr, li, ri, pos_x, pos_z, B;
    double cv, cc, crl, sjit, csc;
    double tb[3], cbw[2];
} NoteOut;

// blockrender._build_note's piano path, from the voice's construction to
// its phantom partials: the note's rows into rows (cap of them), qacc[18]
// and *azimuth carried; rs the global random stream (NULL: a scratch one).
// The room's image sources for the voice's position (img etc.) are the
// caller's. Returns the rows written, -1 if the store was too small.
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
    t.cv = K->chiff_volume; t.cc = K->chiff_cycle; t.crl = K->chiff_release; t.csc = f0 / 440.0;
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
        double bon = non + K->strike_at_s * SR + 0.0 * SR;
        ToneIn tk = t;
        tk.gain = s.gain; tk.B = 0.0; tk.sjit = 0.0; tk.reflect = 0;
        tk.cbw0 = -0.25; tk.cbw1 = 0.0;
        int k = nv_strike(&s, &tk, K->n_strike, K->strike_hz, K->strike_db, reg, 0.0, K->strike_cal_db, slr,
                          sfade, slen, bon, s.position_x, rows, cap, qacc, azimuth);
        if (k < 0)
            return -1;
        out->n_knock = k;
        total += k;
        no_refl = 0;
    }

    // THE TONE (_note_stops, one stop at gain 1)
    int reflect = n->reflect && !no_refl && K->reflection_order;
    t.gain = 1.0; t.B = B; t.sjit = K->sustain_jitter; t.reflect = reflect;
    t.cbw0 = K->cbw0; t.cbw1 = K->cbw1;
    double trans[3 * 1025];
    int ntr = 0;
    if (s.max_harmonic + 1 > 1025)
        return -1;
    int k = nv_tone(&s, &t, reflect ? nimg : 0, nsurf, surf, img, mir, rows + NCOLS * total, cap - total,
                    trans, &ntr, qacc, azimuth);
    if (k < 0)
        return -1;
    out->n_tone = k;
    total += k;

    // THE PHANTOM PARTIALS (_note_phantoms)
    t.gain = s.gain; t.B = 0.0; t.sjit = 0.0;
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
    out->cv = t.cv; out->cc = t.cc; out->crl = t.crl; out->sjit = K->sustain_jitter; out->csc = t.csc;
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
    n->off = nv_song_note_off(song, n->ch, n->note, n->on, n->key_off, n->damper_pedal, n->mcut,
                              n->retrigger_fade, band);
    n->has_nx = nv_song_next_same(song, n->ch, n->note, n->on, &n->nx);
    if (!n->has_nx)
        n->nx = 0.0;
    n->soft_pedal_down = nv_song_soft_at(song, n->ch, n->on);
    return nv_note(K, n, rs, nimg, nsurf, surf, img, mir, rows, cap, qacc, azimuth, out);
}

}  // extern "C"
