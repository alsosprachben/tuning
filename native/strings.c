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

/* zlib's crc32 of n bytes (tonelib's per-key draws are seeded by it) */
static unsigned long organ_crc32(const char *b, size_t n)
{
    unsigned long c = 0xFFFFFFFFUL;
    for (size_t i = 0; i < n; i++) {
        c ^= (unsigned char)b[i];
        for (int k = 0; k < 8; k++)
            c = (c >> 1) ^ (0xEDB88320UL & (0UL - (c & 1UL)));
    }
    return c ^ 0xFFFFFFFFUL;
}

#define NV_KEY_LO 21
#define NV_KEY_HI 109           /* register.KEYS: range(21, 109) */

/* a merge sort on f, stable, as numpy's argsort(kind='stable') */
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
    return nv_strings_og(c0, tmpl, NULL, table, pan, chan_vol, sr, out, tmp, cap);
}

/* tonelib.choir_partial_hz by the choir's (buffed: plain) name */
static double choir_beat_hz(const OrganSpec *og, const char *name, int key, int m)
{
    char b[64];
    int n = snprintf(b, sizeof b, "%s|%d|%d|beat", name, key, m);
    PyRandom g;
    pyr_seed(&g, (long long)organ_crc32(b, (size_t)n));
    double u = pyr_uniform(&g, og->beat_lo, og->beat_hi);
    return u * (pyr_random(&g) < 0.5 ? 1.0 : -1.0);
}

/* ...and with a harpsichord's CHOIRS (og's string_choirs; NULL or none: a
 * piano's one row): a key's series per choir -- its own class's string (a
 * choir's pipe, else the host's), at its footage and its own few cents,
 * its own wire and its partials a little off it -- each mode's string
 * choir * 16 + its unison (register.CHOIR) */
int nv_strings_og(const VoiceInit *c0, const VoiceSnap *tmpl, const OrganSpec *og, const double *table, double pan,
                  double chan_vol, double sr, StringMode *out, StringMode *tmp, int cap)
{
    VoiceInit c = *c0;
    c.soft_pedal_down = 0;              /* the free strings are all there: una corda moves the hammer */
    int n = 0;
    int nch = og && og->n_choir ? og->n_choir : 1;
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
        for (int ci = 0; ci < nch; ci++) {
        const int choired = og && og->n_choir;
        VoiceSnap cv_;
        const VoiceSnap *cp = &v;
        double cr = 1.0, cB = B;
        if (choired) {
            if (og->choir_pipe[ci] >= 0) {      /* its own class's string (_isolated) */
                const OrganPipe *pp = &og->pipe[og->choir_pipe[ci]];
                VoiceInit pc = pp->init;
                pc.soft_pedal_down = 0;
                VoiceNote po;
                nv_voice_init(&pc, &pp->tmpl, f0, pan, 1.0, chan_vol, 0.0, NULL, &cv_, &po);
                cp = &cv_;
            }
            cr = og->choir_bname[ci][0] ? og->choir_ratio[ci] * pow(2.0, og->choir_cents[ci][key] / 1200.0)
                                        : og->choir_ratio[ci];
            if (og->choir_bname[ci][0])
                cB = B * og->choir_stiff[ci][key];
        }
        for (int m = 1; m < v.max_harmonic + 1; m++) {
            double hh[2];
            if (!nv_string_partial(&v, f0, cr, m, cB, hh))
                break;
            double hf = hh[1];
            if (choired && og->choir_beat[ci])
                hf += choir_beat_hz(og, og->choir_bname[ci], key, m);
            if (hf > sr / 2)
                break;
            if (nv_harmonic_volume(cp, m) == 0.0)
                continue;
            double pd[4];
            nv_partial_decay(cp, f0, m, pd);        /* dbps, logr, aftL, logrA */
            double sf[5], sa[5];
            int ss[5], ns = 0;
            ss[ns] = 16 * ci; sf[ns] = hf; sa[ns] = pd[3] > 0 ? pd[3] : pd[1]; ns++;
            double uv[20];
            int nu = nv_unison_voices(&v, f0, m, pd[0], uv);
            for (int ui = 0; ui < nu; ui++) {
                double up[2], af[2];
                nv_unison_partial(hf, uv[5 * ui + 1], uv[5 * ui + 2], uv[5 * ui + 3], up);
                if (up[0] <= 0 || up[0] > sr / 2)
                    continue;
                nv_aftersound(&v, f0, uv[5 * ui + 3], af);
                ss[ns] = 16 * ci + ui + 1; sf[ns] = up[0];
                sa[ns] = af[1] > 0 ? log(db_ratio(af[1])) : up[1];
                ns++;
            }
            /* (a piano's board; a harpsichord's body is its FormantBody) */
            double w = (v.board_kind || !v.fbody ? soundboard_gain(&v, hf) : bore_gain(&v, hf))
                       * nv_radiation_gain(&v, hf, 0.0, 0);
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
