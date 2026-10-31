/* strings.c -- the register's STRING BANK in C: register.Strings for a
 * piano (one row of strings: no choirs, courses, key bridges or buffs), bit
 * for bit. Included by tone.c, after voice.c.
 *
 * Every key A0..C8 the tuning has: its voice as the register builds it
 * (_isolated: velocity 1, no effort, the soft pedal up, the global random
 * stream untouched -- a piano's pitch error is its key's own), and for each
 * harmonic the note loop would emit (string_partial, harmonic_volume) its
 * string and each unison string (unison_voices, unison_partial) as a mode:
 * frequency (times the key's pitch error), decay (the aftersound's where it
 * has one), the bridge's weight (soundboard_gain * radiation_gain), each
 * ear's shadow (hrtf_gain), the ears' delays and the key's place. Sorted by
 * frequency (stably), the weights over their largest. */

#define NV_KEY_LO 21
#define NV_KEY_HI 109           /* register.KEYS: range(21, 109) */

typedef struct {
    int n;
    long long *key, *string, *harm;
    double *f, *alpha, *w, *hl, *hr, *dl, *dr, *px, *W;
} StringBank;

typedef struct {
    long long key, string, harm;
    double f, alpha, w, hl, hr, dl, dr, px;
} StringMode;

/* insertion sort's stable cousin: a merge sort on f, as numpy's argsort(kind='stable') */
static void modes_sort(StringMode *a, StringMode *tmp, int n)
{
    if (n < 2)
        return;
    int h = n / 2;
    modes_sort(a, tmp, h);
    modes_sort(a + h, tmp, n - h);
    int i = 0, j = h, k = 0;
    while (i < h && j < n)
        tmp[k++] = (a[j].f < a[i].f) ? a[j++] : a[i++];
    while (i < h)
        tmp[k++] = a[i++];
    while (j < n)
        tmp[k++] = a[j++];
    for (k = 0; k < n; k++)
        a[k] = tmp[k];
}

/* The bank for a class (c, tmpl) at a tuning (table[128], 0 where the
 * tuner has no such key), pan and channel volume: into out (cap modes).
 * Returns the modes, -1 if more than cap. */
int nv_strings(const VoiceInit *c0, const VoiceSnap *tmpl, const double *table, double pan, double chan_vol,
               double sr, StringMode *out, StringMode *tmp, int cap)
{
    VoiceInit c = *c0;
    c.soft_pedal_down = 0;              /* the free strings are all there: una corda moves the hammer */
    int n = 0;
    for (int key = NV_KEY_LO; key < NV_KEY_HI; key++) {
        double f0 = table[key];
        if (f0 == 0.0)
            continue;
        VoiceSnap v;
        VoiceNote o;
        nv_voice_init(&c, tmpl, f0, pan, 1.0, chan_vol, 0.0, NULL, &v, &o);
        double B = c.inharmonicity_dynamic ? o.B : o.inharmonicity_coefficient;
        double pj = 1.0 + o.pitch_jitter;
        double li = o.left_incidence, ri = o.right_incidence;
        double dl = o.left_hrtf_delay * sr, dr = o.right_hrtf_delay * sr;
        double px = v.position_x;
        for (int m = 1; m < v.max_harmonic + 1; m++) {
            double hh[2];
            if (!nv_string_partial(&v, f0, 1.0, m, B, hh))
                break;
            double hf = hh[1];
            if (hf > sr / 2)
                break;
            if (nv_harmonic_volume(&v, m) == 0.0)
                continue;
            double pd[4];
            nv_partial_decay(&v, f0, m, pd);        /* dbps, logr, aftL, logrA */
            double sf[5], sa[5];
            int ss[5], ns = 0;
            ss[ns] = 0; sf[ns] = hf; sa[ns] = pd[3] > 0 ? pd[3] : pd[1]; ns++;
            double uv[20];
            int nu = nv_unison_voices(&v, f0, m, pd[0], uv);
            for (int ui = 0; ui < nu; ui++) {
                double up[2], af[2];
                nv_unison_partial(hf, uv[5 * ui + 1], uv[5 * ui + 2], uv[5 * ui + 3], up);
                if (up[0] <= 0 || up[0] > sr / 2)
                    continue;
                nv_aftersound(&v, f0, uv[5 * ui + 3], af);
                ss[ns] = ui + 1; sf[ns] = up[0];
                sa[ns] = af[1] > 0 ? log(db_ratio(af[1])) : up[1];
                ns++;
            }
            double w = soundboard_gain(&v, hf) * nv_radiation_gain(&v, hf, 0.0, 0);
            double hl = nv_hrtf_gain(&v, hf, li), hr = nv_hrtf_gain(&v, hf, ri);
            for (int i = 0; i < ns; i++) {
                if (n >= cap)
                    return -1;
                StringMode *q = out + n++;
                q->key = key; q->string = ss[i]; q->harm = m;
                q->f = sf[i] * pj; q->alpha = sa[i]; q->w = w;
                q->hl = hl; q->hr = hr; q->dl = dl; q->dr = dr; q->px = px;
            }
        }
    }
    modes_sort(out, tmp, n);
    double wmax = 0.0;
    for (int i = 0; i < n; i++)
        if (i == 0 || out[i].w > wmax)
            wmax = out[i].w;
    double d = wmax > 1e-30 ? wmax : 1e-30;
    for (int i = 0; i < n; i++)
        out[i].w = out[i].w / d;
    return n;
}
