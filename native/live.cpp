// live.cpp -- the native engine's LIVE side. First piece: a key's TEMPLATE.
//
// live.py makes each key's note once, at each velocity it is played at, and
// stamps it into the slab at every press (Slab.stamp_cols); a template is
// blockrender.prepare of a one-note file (live.Voice._raw_template): tempo
// one beat a second, the program, CC7 and CC11 at 127, the key down at 0 and
// up at 1 s, the track ending a second later -- with fixed touch on and the
// register off (the slab has its own: LiveChannel). nv_template builds that
// file's bytes here and runs them through the engine (midi.cpp, channel.cpp,
// prepare.cpp): the template's table, bit for bit the Python's.
//
// Its derived fields (live's masks, hrel, dur, fa_at...) are arithmetic on
// these columns: the slab's port takes them.

#include <cstdint>
#include <vector>

#include "pycompat.h"

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
void nv_midi_free(void *p);
double nv_midi_total(void *p);
void nv_midi_song(void *p, void *song, const double *trim);
void *nv_song_new(void);
void nv_song_free(void *s);
void nv_song_tuning(void *s, long long ch, double t, const double *freq);
void nv_song_finish(void *s, double total);
long long nv_prepare(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                     PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind, double scale,
                     double full_db_s, double residual, double beta, long long blk, double total, double ring_floor,
                     double ring_max, double *out, double knee_db, double ln10_20, double xdec_nepers, double SR,
                     void **dm, int with_register);
}

namespace nv {
namespace live {

static void vlq(std::vector<uint8_t> &b, uint32_t v)
{
    uint8_t t[5];
    int n = 0;
    t[n++] = v & 0x7F;
    while (v >>= 7)
        t[n++] = 0x80 | (v & 0x7F);
    while (n)
        b.push_back(t[--n]);
}

// _raw_template's file, as mido saves it (type 1, 480 ticks a beat, one track)
static std::vector<uint8_t> one_note(int program, int note, int vel, int ch)
{
    std::vector<uint8_t> tr;
    auto ev = [&](uint32_t dt, std::initializer_list<uint8_t> bytes) {
        vlq(tr, dt);
        tr.insert(tr.end(), bytes);
    };
    ev(0, {0xFF, 0x51, 0x03, 0x0F, 0x42, 0x40});                     // set_tempo 1000000
    ev(0, {(uint8_t)(0xC0 | ch), (uint8_t)program});
    ev(0, {(uint8_t)(0xB0 | ch), 7, 127});
    ev(0, {(uint8_t)(0xB0 | ch), 11, 127});
    ev(0, {(uint8_t)(0x90 | ch), (uint8_t)note, (uint8_t)vel});
    ev(480, {(uint8_t)(0x80 | ch), (uint8_t)note, 0});
    ev(480, {0xFF, 0x2F, 0x00});
    std::vector<uint8_t> f = {'M', 'T', 'h', 'd', 0, 0, 0, 6, 0, 1, 0, 1, 0x01, 0xE0, 'M', 'T', 'r', 'k'};
    uint32_t n = (uint32_t)tr.size();
    f.push_back(n >> 24); f.push_back(n >> 16); f.push_back(n >> 8); f.push_back(n);
    f.insert(f.end(), tr.begin(), tr.end());
    return f;
}

}  // namespace live
}  // namespace nv

extern "C" {

// A key's template: program, key and velocity on channel 0 (a drum set's
// on GM's percussion channel: not here -- piano only), the tuning freq[128],
// trim[256] (a GM file's: patch_map.program_trim, melodic then drum), the
// engine's constants in tmpl (its fixed_touch set, as live builds templates)
// and the rest as nv_prepare's. The rows in *rowsp (nv_buf_free), out[] as
// nv_prepare's. Returns the rows, or < 0 (the file refused, a note not the
// engine's).
long long nv_template(const NoteClass *const *K, const NoteIn *tmpl, const double *freq, const double *trim,
                      int program, int note, int vel, double **rowsp, const int *kind, double scale, double full_db_s,
                      double residual, double beta, long long blk, double ring_floor, double ring_max, double *out,
                      double knee_db, double ln10_20, double xdec_nepers, double SR, void **dm)
{
    std::vector<uint8_t> f = nv::live::one_note(program, note, vel, 0);
    int err = 0;
    void *m = nv_midi_read(f.data(), (long long)f.size(), &err);
    if (!m)
        return -1000000001LL;
    void *song = nv_song_new();
    nv_song_tuning(song, -1, 0.0, freq);
    nv_midi_song(m, song, trim);
    double total = nv_midi_total(m);
    nv_song_finish(song, total);
    PyRandom rs;
    pyr_seed(&rs, 0);                       // _prepare's random.seed(0)
    double qacc[18] = {0}, az = 0.0;
    long long P = nv_prepare(song, K, tmpl, nullptr, 0, &rs, rowsp, qacc, &az, kind, scale, full_db_s, residual,
                             beta, blk, total, ring_floor, ring_max, out, knee_db, ln10_20, xdec_nepers, SR, dm, 0);
    nv_song_free(song);
    nv_midi_free(m);
    return P;
}

}  // extern "C"
