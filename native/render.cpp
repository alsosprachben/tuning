// render.cpp -- the native engine's RENDER: a table to audio, as
// blockrender.synth_window does it for the whole file on the CPU.
//
// The kernel itself is synthkernel.c, built by blockrender in three libraries
// that each define synth_voice (the plain one; -DXDEC_KERNEL's
// synth_voice_xdec for a burst falling more than 20 dB a block;
// -DDAMP_KERNEL's synth_voice_damp for a half-pedalled row), so they are
// handed in as function pointers -- the same code, the same flags. Here: the
// rows routed among them as synth_partials routes the whole table (the
// damped rows; of the rest, the fast bursts; the rest plain -- each set in
// table order, gathered contiguous), then the master gain (in float32, as
// numpy multiplies a float32 buffer by a Python float) and the clip.
//
// A piano song's table only, for now: no consonant bursts, no master volume
// curve, no bus, Moog, Leslie or filter rows (render.cpp refuses them).

#include <cstdint>
#include <cstring>
#include <vector>

extern "C" {

// synthkernel.c's synth_voice (and _xdec: the same arguments)
typedef void (*voice_fn)(
    float *outL, float *outR, long n0, long winlen, int BLK, int nblk, int P,
    const double *omega, const double *ph0L, const double *ph0R,
    const float *ampL, const float *ampR, const float *nomfreq,
    const long *non, const long *noff, const float *fadeS, const float *relS, const float *chiffS,
    const float *logr, const float *logrA, const float *aftL, const float *susL,
    const float *chVol, const float *chCyc, const float *chRel, const float *susJit, const float *chScale,
    const float *chBW, const float *tbav, const float *tau, const float *tcut,
    const float *gbav, const float *gtau, const float *gcut,
    const float *vdep, const float *vrate, const float *vph, const float *vdl,
    const float *delL, const float *delR,
    const int *grow, const int *crow, const float *G, const float *S,
    const int *brow, const float *BR, const double *BC, const float *BL,
    const int *fxr, const float *FT, const float *KN, long knk, long kb0,
    const float *ampLp, const float *ampRp, const int *mkr,
    const int *MPI, const double *MPC, const float *MPR, const int *MKI, const float *MPK,
    const double *fmw, const double *fmp, const double *fmpR,
    float sfloor, float spow, float shmax, float shref, long CHUNK,
    const float *sendW, float *outSL, float *outSR);

// ...and synth_voice_damp: those, then the rows' tracks
typedef void (*damp_fn)(
    float *outL, float *outR, long n0, long winlen, int BLK, int nblk, int P,
    const double *omega, const double *ph0L, const double *ph0R,
    const float *ampL, const float *ampR, const float *nomfreq,
    const long *non, const long *noff, const float *fadeS, const float *relS, const float *chiffS,
    const float *logr, const float *logrA, const float *aftL, const float *susL,
    const float *chVol, const float *chCyc, const float *chRel, const float *susJit, const float *chScale,
    const float *chBW, const float *tbav, const float *tau, const float *tcut,
    const float *gbav, const float *gtau, const float *gcut,
    const float *vdep, const float *vrate, const float *vph, const float *vdl,
    const float *delL, const float *delR,
    const int *grow, const int *crow, const float *G, const float *S,
    const int *brow, const float *BR, const double *BC, const float *BL,
    const int *fxr, const float *FT, const float *KN, long knk, long kb0,
    const float *ampLp, const float *ampRp, const int *mkr,
    const int *MPI, const double *MPC, const float *MPR, const int *MKI, const float *MPK,
    const double *fmw, const double *fmp, const double *fmpR,
    float sfloor, float spow, float shmax, float shref, long CHUNK,
    const float *sendW, float *outSL, float *outSR,
    const int *dk, const float *dg, const float *DM, const long *DMO, const long *DMB, const long *DMN);

// The table, column by column in prepare's final types (FINAL_DTYPES):
// d[0..2] om p0 p0R (float64); f[] the float32 columns in VCOLS_F order; l[0..1]
// non noff (int64); i[0..3] gr cr br (int32, and dk); damper tracks or NULL.
enum { F_aL, F_aR, F_nf, F_fa, F_re, F_ch, F_logr, F_logrA, F_aft, F_sus, F_cv, F_cc, F_crl, F_sj, F_csc, F_cbw,
       F_tbav, F_tau, F_tcut, F_gb, F_gt, F_gc, F_vd, F_vr, F_vp, F_vdl, F_delL, F_delR, F_dg, NF };
enum { I_gr, I_cr, I_br, I_dk, NI };

struct Gather {
    std::vector<double> d[3];
    std::vector<float> f[NF];
    std::vector<long> l[2];
    std::vector<int> i[NI];
};

static void gather(Gather &g, const std::vector<long long> &rows, double *const *d, float *const *f, long *const *l,
                   int *const *ii, bool damp)
{
    size_t n = rows.size();
    for (int c = 0; c < 3; c++) {
        g.d[c].resize(n);
        for (size_t k = 0; k < n; k++)
            g.d[c][k] = d[c][rows[k]];
    }
    for (int c = 0; c < NF; c++) {
        if (c == F_dg && !damp)
            continue;
        g.f[c].resize(n);
        for (size_t k = 0; k < n; k++)
            g.f[c][k] = f[c][rows[k]];
    }
    for (int c = 0; c < 2; c++) {
        g.l[c].resize(n);
        for (size_t k = 0; k < n; k++)
            g.l[c][k] = l[c][rows[k]];
    }
    for (int c = 0; c < NI; c++) {
        if (c == I_dk && !damp)
            continue;
        g.i[c].resize(n);
        for (size_t k = 0; k < n; k++)
            g.i[c][k] = ii[c][rows[k]];
    }
}

// The whole table [0, N) into L, R (zeroed here): plain, fast bursts, damped
// rows through their kernels (sv, sx, sd), then master gain and clip. G, S,
// BR, BC the table's swell, chest and bend rows; sh its shutter's four;
// CHUNK the kernel's chunk; xdec_nepers, SR: _xdec_rows' test. DM etc. NULL
// for a table with no damper tracks.
int nv_render(void *sv, void *sx, void *sd, long N, int BLK, int nblk, long long P, double *const *d,
              float *const *f, long *const *l, int *const *ii, const float *G, const float *S, const float *BR,
              const double *BC, const float *noRows, const float *sh, long CHUNK, double xdec_nepers, double SR,
              double master_gain, const float *DM, const long *DMO, const long *DMB, const long *DMN, float *L,
              float *R)
{
    memset(L, 0, sizeof(float) * N);
    memset(R, 0, sizeof(float) * N);
    bool has_dm = DM != nullptr;
    // _xdec_rows: falling more than XDEC_NEPERS a block, no sustain, no gate,
    // and (with tracks) no track -- on the final float32 columns, numpy's float32
    auto xdec = [&](long long r) {
        float lr = f[F_logr][r];
        bool m = f[F_sus][r] <= 0 && f[F_aft][r] <= 0 && (float)(lr * (float)BLK) > (float)(xdec_nepers * SR)
                 && ii[I_gr][r] < 0;
        if (has_dm)
            m = m && ii[I_dk][r] < 0;
        return m;
    };
    std::vector<long long> plain, fast, damped;
    for (long long r = 0; r < P; r++) {
        if (has_dm && ii[I_dk][r] >= 0)
            damped.push_back(r);
        else if (xdec(r))
            fast.push_back(r);
        else
            plain.push_back(r);
    }
    if (has_dm && damped.empty())
        has_dm = false;
    auto call = [&](voice_fn fn, damp_fn dfn, const std::vector<long long> &rows, bool damp) {
        if (rows.empty())
            return;
        Gather g;
        gather(g, rows, d, f, l, ii, damp);
        int n = (int)rows.size();
        auto F = [&](int c) { return g.f[c].data(); };
        if (!damp)
            fn(L, R, 0, N, BLK, nblk, n, g.d[0].data(), g.d[1].data(), g.d[2].data(), F(F_aL), F(F_aR), F(F_nf),
               g.l[0].data(), g.l[1].data(), F(F_fa), F(F_re), F(F_ch), F(F_logr), F(F_logrA), F(F_aft), F(F_sus),
               F(F_cv), F(F_cc), F(F_crl), F(F_sj), F(F_csc), F(F_cbw), F(F_tbav), F(F_tau), F(F_tcut), F(F_gb),
               F(F_gt), F(F_gc), F(F_vd), F(F_vr), F(F_vp), F(F_vdl), F(F_delL), F(F_delR), g.i[I_gr].data(),
               g.i[I_cr].data(), G, S, g.i[I_br].data(), BR, BC, nullptr, nullptr, noRows, noRows, 1, 0, nullptr,
               nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, sh[0], sh[1],
               sh[2], sh[3], CHUNK, nullptr, nullptr, nullptr);
        else
            dfn(L, R, 0, N, BLK, nblk, n, g.d[0].data(), g.d[1].data(), g.d[2].data(), F(F_aL), F(F_aR), F(F_nf),
                g.l[0].data(), g.l[1].data(), F(F_fa), F(F_re), F(F_ch), F(F_logr), F(F_logrA), F(F_aft), F(F_sus),
                F(F_cv), F(F_cc), F(F_crl), F(F_sj), F(F_csc), F(F_cbw), F(F_tbav), F(F_tau), F(F_tcut), F(F_gb),
                F(F_gt), F(F_gc), F(F_vd), F(F_vr), F(F_vp), F(F_vdl), F(F_delL), F(F_delR), g.i[I_gr].data(),
                g.i[I_cr].data(), G, S, g.i[I_br].data(), BR, BC, nullptr, nullptr, noRows, noRows, 1, 0, nullptr,
                nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, sh[0],
                sh[1], sh[2], sh[3], CHUNK, nullptr, nullptr, nullptr, g.i[I_dk].data(), F(F_dg), DM, DMO, DMB,
                DMN);
    };
    if (has_dm) {
        call((voice_fn)sv, nullptr, plain, false);
        call((voice_fn)sx, nullptr, fast, false);
        call(nullptr, (damp_fn)sd, damped, true);
    } else if (!fast.empty()) {
        std::vector<long long> keep;
        for (long long r = 0; r < P; r++)
            if (!xdec(r))
                keep.push_back(r);
        call((voice_fn)sv, nullptr, keep, false);
        call((voice_fn)sx, nullptr, fast, false);
    } else {
        call((voice_fn)sv, nullptr, plain, false);
    }
    // the master gain, float32 (numpy: a float32 buffer times a Python float), and the clip
    float g = (float)master_gain;
    for (long k = 0; k < N; k++) {
        L[k] = L[k] * g;
        R[k] = R[k] * g;
        L[k] = L[k] < -1.0f ? -1.0f : (L[k] > 1.0f ? 1.0f : L[k]);
        R[k] = R[k] < -1.0f ? -1.0f : (R[k] > 1.0f ? 1.0f : R[k]);
    }
    return 0;
}

}  // extern "C"
