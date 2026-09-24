/* The live room: partitioned convolution, in two tiers, with no latency.

   roomtail.py convolves a finished render with the room's impulse response in
   one enormous FFT, which is right offline and impossible live: the tail is
   2.5-3 s, some 150 000 taps at 48 kHz, and the audio thread has 2.67 ms per
   128-frame block.

   ONE TIER WAS CORRECT AND TOO SLOW. Uniform partitioned overlap-save -- the IR
   cut into one-block partitions, each transformed once, and every block a
   multiply-add against a frequency-domain delay line of the last P input
   spectra -- matched overlap_add to 7e-7 and cost 0.4 ms per channel in the
   hall. The time is memory: every block streams all P spectra, about 2 MB,
   and that is proportional to the IR's length whatever the block size.

   SO TWO TIERS. The head, the IR's first D = 2L samples, runs uniformly in
   one-block partitions (32 of them at B = 128): cheap, and it is what gives
   zero latency. The rest runs in partitions of L = M blocks (M = 16, L = 2048)
   whose contribution is not needed until D samples after its input -- one
   whole segment later than the segment it is computed from -- so its work is
   SPREAD over the M blocks of that segment, a sixteenth of the partitions each.
   The streamed memory per block falls by about M, and nothing is late:
   segment s's input is complete at (s+1)L, its output is due at (s+2)L, and
   the last chunk of its work runs in the block before that. (Gardner's
   non-uniform scheme, with the tail's work time-distributed rather than
   threaded, so the cost is flat and deterministic.)

   The FFT is a plain iterative radix-2 complex transform on real input. The
   multiply-add loops are written over split real/imaginary arrays so they
   vectorise; that is where the time goes.

   Nothing here knows about rooms. live.py builds the IR with roomtail.build_ir
   and modal_ir, the same functions the file renderer's tail uses, so the two
   renderers hear the same room by construction.
*/
#include <stdlib.h>
#include <string.h>
#include <math.h>

typedef struct {
    int N, K;              /* size, bins kept (N/2+1) */
    float *wre, *wim;      /* N/2 twiddles */
    int *rev;
    float *tre, *tim;      /* N scratch */
} plan_t;

typedef struct {
    int P, K;              /* partitions, bins */
    int head;
    float *Hre, *Him, *Xre, *Xim;   /* P*K each */
} fdl_t;

typedef struct {
    int B, M, L, D;        /* block, blocks per segment, segment (M*B), head length (2L) */
    long nb;               /* blocks processed */
    plan_t p1, p2;         /* 2B and 2L point transforms */
    fdl_t t1, t2;          /* head tier, tail tier */
    float *buf1;           /* 2B: previous block, current block */
    float *seg;            /* 3L: ring of the last three input segments */
    float *acc2re, *acc2im;/* K2: the tail's running sum for one segment */
    float *fifo;           /* 4L: the tail's output, ahead of time */
    float *acc1re, *acc1im;/* K1 scratch */
    float *tmp2;           /* 2L: the tail tier's input, preallocated -- no malloc per block */
    int has_tail;
} conv_t;

static int plan_init(plan_t *p, int N)
{
    int bits = 0;
    while ((1 << bits) < N) bits++;
    if ((1 << bits) != N) return 0;
    p->N = N; p->K = N / 2 + 1;
    p->wre = malloc(sizeof(float) * N / 2); p->wim = malloc(sizeof(float) * N / 2);
    p->rev = malloc(sizeof(int) * N);
    p->tre = malloc(sizeof(float) * N); p->tim = malloc(sizeof(float) * N);
    for (int k = 0; k < N / 2; k++) {
        p->wre[k] = (float)cos(-2.0 * M_PI * k / N);
        p->wim[k] = (float)sin(-2.0 * M_PI * k / N);
    }
    for (int i = 0; i < N; i++) {
        int r = 0;
        for (int b = 0; b < bits; b++) if (i & (1 << b)) r |= 1 << (bits - 1 - b);
        p->rev[i] = r;
    }
    return 1;
}

static void plan_free(plan_t *p)
{
    free(p->wre); free(p->wim); free(p->rev); free(p->tre); free(p->tim);
}

static void fft(plan_t *p, float *re, float *im, int inverse)
{
    int N = p->N;
    for (int i = 0; i < N; i++) {
        int j = p->rev[i];
        if (j > i) {
            float t = re[i]; re[i] = re[j]; re[j] = t;
            t = im[i]; im[i] = im[j]; im[j] = t;
        }
    }
    for (int len = 2; len <= N; len <<= 1) {
        int half = len >> 1, step = N / len;
        for (int s = 0; s < N; s += len) {
            for (int k = 0; k < half; k++) {
                float wr = p->wre[k * step];
                float wi = inverse ? -p->wim[k * step] : p->wim[k * step];
                int a = s + k, b = a + half;
                float xr = re[b] * wr - im[b] * wi;
                float xi = re[b] * wi + im[b] * wr;
                re[b] = re[a] - xr; im[b] = im[a] - xi;
                re[a] += xr;        im[a] += xi;
            }
        }
    }
}

static void rfft(plan_t *p, const float *x, float *ore, float *oim)
{
    for (int i = 0; i < p->N; i++) { p->tre[i] = x[i]; p->tim[i] = 0.0f; }
    fft(p, p->tre, p->tim, 0);
    memcpy(ore, p->tre, sizeof(float) * p->K);
    memcpy(oim, p->tim, sizeof(float) * p->K);
}

/* Inverse of a K-bin half spectrum held in re/im (length N, overwritten). */
static void irfft_inplace(plan_t *p, float *re, float *im)
{
    int N = p->N, K = p->K;
    for (int b = 1; b < N - K + 1; b++) { re[N - b] = re[b]; im[N - b] = -im[b]; }
    fft(p, re, im, 1);
}

static int fdl_init(fdl_t *f, plan_t *p, const float *ir, int len, int part)
{
    f->P = (len + part - 1) / part; if (f->P < 1) f->P = 1;
    f->K = p->K; f->head = 0;
    size_t pk = (size_t)f->P * f->K;
    f->Hre = calloc(pk, sizeof(float)); f->Him = calloc(pk, sizeof(float));
    f->Xre = calloc(pk, sizeof(float)); f->Xim = calloc(pk, sizeof(float));
    if (!f->Hre || !f->Him || !f->Xre || !f->Xim) return 0;
    float *s = calloc(p->N, sizeof(float));
    for (int q = 0; q < f->P; q++) {
        memset(s, 0, sizeof(float) * p->N);
        for (int i = 0; i < part && q * part + i < len; i++) s[i] = ir[q * part + i];
        rfft(p, s, f->Hre + (size_t)q * f->K, f->Him + (size_t)q * f->K);
    }
    free(s);
    return 1;
}

static void fdl_free(fdl_t *f) { free(f->Hre); free(f->Him); free(f->Xre); free(f->Xim); }

/* acc += sum over partitions [q0, q1) of X[head - q] * H[q] */
static void fdl_mac(fdl_t *f, int q0, int q1, float *are, float *aim)
{
    int K = f->K, P = f->P;
    for (int q = q0; q < q1; q++) {
        int x = f->head - q; if (x < 0) x += P;
        const float *xr = f->Xre + (size_t)x * K, *xi = f->Xim + (size_t)x * K;
        const float *hr = f->Hre + (size_t)q * K, *hi = f->Him + (size_t)q * K;
        for (int b = 0; b < K; b++) {
            are[b] += xr[b] * hr[b] - xi[b] * hi[b];
            aim[b] += xr[b] * hi[b] + xi[b] * hr[b];
        }
    }
}

void conv_reset(conv_t *c);

conv_t *conv_new(const float *ir, int len, int B, int M)
{
    conv_t *c = calloc(1, sizeof(conv_t));
    if (!c) return NULL;
    c->B = B; c->M = M; c->L = M * B; c->D = 2 * c->L;
    if (!plan_init(&c->p1, 2 * B) || !plan_init(&c->p2, 2 * c->L)) { free(c); return NULL; }
    int head = len < c->D ? len : c->D;
    if (!fdl_init(&c->t1, &c->p1, ir, head, B)) return NULL;
    c->has_tail = len > c->D;
    if (c->has_tail && !fdl_init(&c->t2, &c->p2, ir + c->D, len - c->D, c->L)) return NULL;
    c->buf1 = calloc(2 * B, sizeof(float));
    c->seg = calloc(3 * (size_t)c->L, sizeof(float));
    c->acc2re = calloc(2 * (size_t)c->L, sizeof(float)); c->acc2im = calloc(2 * (size_t)c->L, sizeof(float));
    c->fifo = calloc(4 * (size_t)c->L, sizeof(float));
    c->acc1re = calloc(2 * B, sizeof(float)); c->acc1im = calloc(2 * B, sizeof(float));
    c->tmp2 = calloc(2 * (size_t)c->L, sizeof(float));
    /* TOUCH EVERY PAGE NOW, not on the audio thread. calloc hands back pages
       the kernel has not mapped yet, and the first write to each one faults --
       measured, that put 6-12 ms blocks into the chapel and church the first
       time the tail's delay line wrapped round, against a 2.67 ms budget. */
    conv_reset(c);
    return c;
}

void conv_free(conv_t *c)
{
    if (!c) return;
    fdl_free(&c->t1); if (c->has_tail) fdl_free(&c->t2);
    plan_free(&c->p1); plan_free(&c->p2);
    free(c->buf1); free(c->seg); free(c->acc2re); free(c->acc2im); free(c->fifo);
    free(c->acc1re); free(c->acc1im); free(c->tmp2);
    free(c);
}

/* One block: B samples in, B samples out. */
void conv_process(conv_t *c, const float *in, float *out)
{
    int B = c->B, M = c->M, L = c->L;
    /* ---- the head: uniform, every block ---- */
    memmove(c->buf1, c->buf1 + B, sizeof(float) * B);
    memcpy(c->buf1 + B, in, sizeof(float) * B);
    fdl_t *t1 = &c->t1;
    t1->head = (t1->head + 1) % t1->P;
    rfft(&c->p1, c->buf1, t1->Xre + (size_t)t1->head * t1->K, t1->Xim + (size_t)t1->head * t1->K);
    for (int b = 0; b < 2 * B; b++) { c->acc1re[b] = 0.0f; c->acc1im[b] = 0.0f; }
    fdl_mac(t1, 0, t1->P, c->acc1re, c->acc1im);
    irfft_inplace(&c->p1, c->acc1re, c->acc1im);
    float s1 = 1.0f / (float)(2 * B);
    for (int i = 0; i < B; i++) out[i] = c->acc1re[B + i] * s1;

    if (!c->has_tail) { c->nb++; return; }

    /* ---- the tail: segments of L, their work spread over M blocks ---- */
    long s_cur = c->nb / M;
    int k = (int)(c->nb % M);
    memcpy(c->seg + (size_t)(s_cur % 3) * L + (size_t)k * B, in, sizeof(float) * B);
    long w = s_cur - 1;                 /* the segment completed last */
    fdl_t *t2 = &c->t2;
    if (w >= 0) {
        if (k == 0) {
            /* [segment w-1, segment w] -> the delay line */
            float *tmp = c->tmp2;
            if (w >= 1) memcpy(tmp, c->seg + (size_t)((w - 1) % 3) * L, sizeof(float) * L);
            else memset(tmp, 0, sizeof(float) * L);
            memcpy(tmp + L, c->seg + (size_t)(w % 3) * L, sizeof(float) * L);
            t2->head = (t2->head + 1) % t2->P;
            rfft(&c->p2, tmp, t2->Xre + (size_t)t2->head * t2->K, t2->Xim + (size_t)t2->head * t2->K);
            for (int b = 0; b < 2 * L; b++) { c->acc2re[b] = 0.0f; c->acc2im[b] = 0.0f; }
        }
        int q0 = (int)((long)t2->P * k / M), q1 = (int)((long)t2->P * (k + 1) / M);
        fdl_mac(t2, q0, q1, c->acc2re, c->acc2im);
        if (k == M - 1) {
            irfft_inplace(&c->p2, c->acc2re, c->acc2im);
            float s2 = 1.0f / (float)(2 * L);
            size_t at = (size_t)(((w + 2) * L) % (4L * L));
            for (int i = 0; i < L; i++)
                c->fifo[(at + i) % (4 * (size_t)L)] += c->acc2re[L + i] * s2;
        }
    }
    size_t t = (size_t)((c->nb * B) % (4L * L));
    for (int i = 0; i < B; i++) {
        size_t j = (t + i) % (4 * (size_t)L);
        out[i] += c->fifo[j];
        c->fifo[j] = 0.0f;
    }
    c->nb++;
}

void conv_reset(conv_t *c)
{
    size_t pk1 = (size_t)c->t1.P * c->t1.K;
    memset(c->t1.Xre, 0, sizeof(float) * pk1); memset(c->t1.Xim, 0, sizeof(float) * pk1);
    if (c->has_tail) {
        size_t pk2 = (size_t)c->t2.P * c->t2.K;
        memset(c->t2.Xre, 0, sizeof(float) * pk2); memset(c->t2.Xim, 0, sizeof(float) * pk2);
    }
    memset(c->buf1, 0, sizeof(float) * 2 * c->B);
    memset(c->seg, 0, sizeof(float) * 3 * (size_t)c->L);
    memset(c->fifo, 0, sizeof(float) * 4 * (size_t)c->L);
    c->nb = 0;
}
