/* organ.c -- a registered organ's note in C: blockrender._note_stops' path
 * for a voice with stop_ranks (the church organ), included by tone.c for
 * its emitter. Bit for bit the Python's rows, checked by check mode.
 *
 * Every rank of the organ is emitted, drawn or not -- its gate row opens
 * and shuts it, so a stop drawn mid-note speaks on the keys still down. A
 * rank's colour is its borrowed spectrum's (rank_spectrum: a voice built at
 * the key's pitch), its measured tables read at the rank's own pitch; its
 * speech, chiff and release are its speech class's (rank_speech_own_pitch:
 * timed by its own pitch); its first partial stands at its place in the case
 * (spiral_spatial). Then the bellows' push: every pipe that speaks
 * overshoots (bellows_push_every_note), a transient copy of each row.
 */

/* SynthProperties.speech_time(fixed, f) for a pipe */
static double pipe_speech(const OrganPipe *p, double fixed, double f)
{
    if (p->speech_cycles > 0.0 && f > 0.0)
        return fixed + p->speech_cycles / f;
    return fixed;
}

/* SynthProperties.chiff_time(f, speech) for a pipe */
static double pipe_chiff_time(const OrganPipe *p, double f, double speech)
{
    if (!p->chiff_width_set && p->chiff_width_cycles <= 0.0)
        return speech;
    double w = p->chiff_width_set ? p->chiff_width : speech;
    if (p->chiff_width_cycles > 0.0 && f > 0.0)
        w = pymin(w, p->chiff_width_cycles / f);
    return w;
}

/* tonelib.bellows_push_weight(cls, h, f0) */
static double push_weight(const OrganPipe *p, double h, double f0)
{
    double g = p->push_gain;
    if (g <= 0.0)
        return 0.0;
    double rdb = 0.0;                           /* _push_register_db */
    if (p->n_push_reg) {
        int last = p->n_push_reg - 1;
        if (f0 <= p->push_reg[0][0])
            rdb = p->push_reg[0][1];
        else if (f0 >= p->push_reg[last][0])
            rdb = p->push_reg[last][1];
        else
            for (int i = 0; i < last; i++) {
                double fa = p->push_reg[i][0], da = p->push_reg[i][1];
                double fb = p->push_reg[i + 1][0], db = p->push_reg[i + 1][1];
                if (f0 <= fb) {
                    rdb = da + (db - da) * log(f0 / fa) / log(fb / fa);
                    break;
                }
            }
    }
    g *= pow(10.0, rdb / 20.0);
    if (p->push_band_set) {
        double hc = p->push_band[0], wo = p->push_band[1];
        if (h < 1.5)
            return 0.0;
        return g * exp(-0.5 * pow(log(h / hc) / log(2.0) / wo, 2.0));
    }
    double tilt = p->push_tilt + p->push_tilt_oct * log(pymax(f0, 1e-9) / 440.0) / log(2.0);
    return g * pow(pymax(h, 1.0), pymax(tilt, 0.0));
}

/* tonelib.bellows_push_rate(cls, w): dB/s */
static double push_rate(const OrganPipe *p, double w)
{
    double d0 = p->push_dbs, g = p->push_gain;
    double eps = pow(10.0, p->push_settle_db / 20.0);
    if (g <= eps || w <= eps)
        return d0;
    return d0 * log(w / eps) / log(g / eps);
}

/* pipe i's voice at the key, as the rank borrows it */
static void organ_build(const OrganSpec *og, int i, double f0, const NoteIn *n, double av, VoiceSnap *pv, char *built)
{
    VoiceInit c = og->pipe[i].init;
    c.fixed_touch = n->fixed_touch;
    c.soft_pedal_down = n->soft_pedal_down;
    VoiceNote o;
    nv_voice_init(&c, &og->pipe[i].tmpl, f0, n->pan, av, n->chan_vol, 0.0, NULL, &pv[i], &o);
    built[i] = 1;
}

int nv_organ_tone(const OrganSpec *og, const VoiceSnap *host, const ToneIn *t, const NoteIn *n, int note,
                  int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
                  double *rows, int cap, double *qacc, double *azimuth, double *fin)
{
    Rows R = {rows, 0, cap};
    const double sr = t->sr, f0 = t->f0;
    const OrganPipe *hp = &og->pipe[0];
    /* each pipe's voice at the key (rank_spectrum(cls)(f0, pan, av, chan_vol)) */
    VoiceSnap *pv = (VoiceSnap *)malloc(sizeof(VoiceSnap) * (og->n_pipe > 0 ? og->n_pipe : 1));
    char built[24] = {0};
    double av = (og->pipe[0].init.touch_sensitive || !n->fixed_touch) ? pow(n->vel / 127.0, 2.0) : 1.0;
    int seg_row[33];
    const OrganPipe *seg_pipe[33];
    double seg_f0[33];
    int nseg = 0;
    seg_row[0] = 0; seg_pipe[0] = hp; seg_f0[0] = f0; nseg = 1;
    double terms[9 * 64], rterms[9 * 64];
    static _Thread_local int r_nsurf[64], r_surf[64 * 8];
    static _Thread_local double r_img[64 * 3], r_mir[64 * 3];
    double VB0[3] = {0.0, 5.5, 0.0};
    ToneIn tr = *t;
    double pos_x = t->pos_x0;
    int ret = 0;
    fin[0] = t->li; fin[1] = t->ri; fin[2] = t->dl; fin[3] = t->dr; fin[4] = NAN; fin[5] = 0.0;
#define VOICE(i) (built[i] ? &pv[i] : (organ_build(og, i, f0, n, av, pv, built), &pv[i]))
    for (int ri = 0; ri < og->n_rank; ri++) {
        const OrganRank *rk = &og->rank[ri];
        if (rk->n_ratio == 0)
            continue;                               /* a stop with no pipes (the tremulant) */
        if (note < rk->lo || note > rk->hi)
            continue;                               /* outside its key range */
        const VoiceSnap *spv = rk->spec >= 0 ? VOICE(rk->spec) : NULL;
        const OrganPipe *spp = rk->spec >= 0 ? &og->pipe[rk->spec] : NULL;
        const VoiceSnap *tsrc = spv ? spv : host;
        /* its pipe: named, or the borrowed spectrum where that is a pipe, else the host */
        const VoiceSnap *rp = host;
        const OrganPipe *rpp = hp;
        if (rk->pipe >= 0) {
            rp = VOICE(rk->pipe);
            rpp = &og->pipe[rk->pipe];
        } else if (spv && spp->rank_is_pipe) {
            rp = spv;
            rpp = spp;
        }
        int own = og->own_pitch;
        const VoiceSnap *sc = host;
        const OrganPipe *scp = hp;
        if (rp != host) {
            sc = rp;
            scp = rpp;
        } else if (own && spv && spp->rank_speech) {
            sc = spv;
            scp = spp;
        }
        double rmin = rk->ratio[0];
        if (rk->compound)
            for (int q = 1; q < rk->n_ratio; q++)
                rmin = rk->ratio[q] < rmin ? rk->ratio[q] : rmin;
        double f0s = own ? f0 * (rk->compound ? rmin : rk->ratio[0]) : f0;
        if (own && nseg < 33) {                     /* _PUSH_SEG: its rows push as its speech class */
            seg_row[nseg] = R.n; seg_pipe[nseg] = scp; seg_f0[nseg] = f0s;
            nseg++;
        }
        const VoiceSnap *cpv = sc != host ? sc : rp;
        const OrganPipe *cpp = sc != host ? scp : rpp;
        double cv_r = cpv != host ? cpp->chiff_volume : t->cv;
        double cc_r = cpv != host ? cpp->chiff_cycle : t->cc;
        double fade_r = t->fade, rel_r = t->rel, chiff_r = t->chiff;
        if (sc != host || f0s != f0) {
            double ha = pipe_speech(hp, hp->attack_set ? hp->attack_time : hp->chiff_max_valve_time, f0);
            double hr = pipe_speech(hp, hp->release_set ? hp->release_valve_time : hp->chiff_max_valve_time, f0);
            double ra = pipe_speech(scp, scp->attack_set ? scp->attack_time : scp->chiff_max_valve_time, f0s);
            double rr = pipe_speech(scp, scp->release_set ? scp->release_valve_time : scp->chiff_max_valve_time, f0s);
            fade_r = ha > 0 ? t->fade * (ra / ha) : t->fade;
            rel_r = hr > 0 ? t->rel * (rr / hr) : t->rel;
            double hc = pipe_chiff_time(hp, f0, ha);
            chiff_r = hc > 0 ? t->chiff * (pipe_chiff_time(scp, f0s, ra) / hc) : t->chiff;
        }
        if (n->organ_perc && rk->perc)              /* the Percussion stop's hammer: min(attack, hammer) */
            fade_r = pymin(fade_r, pymax(1e-4, pymin(og->perc_attack_s, og->afm * t->dur)) * sr);
        double gr = n->rank_gr[ri], cr = n->organ_cr;
        tr.br = n->rank_br[ri];                     /* its chest's wind */
        double non_r = t->non;
        if (n->rank_skip[ri])
            continue;                               /* drawn after the key lifted */
        if (n->rank_rel1[ri])
            rel_r = 1.0;                            /* pushed in before the key-up */
        if (!isnan(n->rank_sp[ri]))
            non_r = (n->rank_sp[ri] + 0.0) * sr;
        /* its place in the case, for its first partial */
        if (og->spiral) {
            double op = host->octave_position;
            double parity = fmod(rint(12.0 * op), 2.0) == 0.0 ? 1.0 : -1.0;
            double rx = og->spiral_m * sin(2.0 * PI * op + og->spiral_phase) + og->drift_m * op + rk->sp_off
                        + rk->sp_split * parity;
            double e[4];
            hrtf_at(host, t, rx, t->pos_z, t->listener_distance, e);
            tr.li = e[0]; tr.ri = e[1];
            tr.dl = e[2] * sr; tr.dr = e[3] * sr;
            pos_x = rx;
        }
        double ceiling = rpp->pipe_ceiling_hz;
        /* a mixture's footages: its composition at this pitch, or its own */
        double subs[8];
        int nsub = rk->n_ratio, comp = 0;
        for (int q = 0; q < nsub; q++)
            subs[q] = rk->ratio[q];
        if (rk->compound && rk->n_comp) {
            int c = 0;
            for (int q = 0; q < rk->n_comp; q++)
                if (f0 >= rk->comp_hz[q])
                    c = q;
            nsub = rk->comp_n[c];
            for (int q = 0; q < nsub; q++)
                subs[q] = rk->comp_r[c][q];
            comp = 1;
        }
        /* the register's tables at the rank's pitch */
        int use_tab = tsrc->kind == 2 && (tsrc->n_pts || tsrc->low_set);
        for (int si = 0; si < nsub; si++) {
            double sub = subs[si], eff = sub;
            double rtab[64];
            int nrtab = 0, tab = 0;
            if (!rk->compound && use_tab && rk->ratio[0] != 1.0) {
                nrtab = nv_mode_gains_at(tsrc, f0 * rk->ratio[0], rtab);
                tab = 1;
            } else if (rk->compound && tsrc->kind == 2 && tsrc->n_pts && sub != 1.0) {
                nrtab = nv_mode_gains_at(tsrc, f0 * sub, rtab);
                tab = 1;
            }
            if (ceiling != 0.0 && !comp && rk->compound && sub >= 2.0 && f0 * sub > ceiling) {
                if (rpp->truncate)
                    continue;
                while (f0 * eff > ceiling && eff >= 2.0)
                    eff *= 0.5;
            }
            if (rk->detune[note] != 0.0)                /* the tuner left this rank a little out (rank_detune) */
                eff *= pow(2.0, rk->detune[note] / 1200.0);
            for (int m = 1; m < host->max_harmonic + 1; m++) {
                double hh[2];
                if (!nv_string_partial(host, f0, eff, m, t->B, hh))
                    break;
                double h = hh[0], hf = hh[1];
                if (hf > sr / 2)
                    break;
                double hv = nv_harmonic_volume(tsrc, m);
                if (tab)
                    hv = (m - 1 < tsrc->n_mm && tsrc->mm_gain[m - 1] > 0)
                         ? hv * ((m - 1 < nrtab ? rtab[m - 1] : 0.0) / tsrc->mm_gain[m - 1]) : 0.0;
                if (hv == 0.0)
                    continue;
                double pfade = fade_r;
                double she = scp->speech_harmonic_exp;
                if (scp->speech_harmonic_exp_per_octave != 0.0)
                    she = pymin(0.0, she + scp->speech_harmonic_exp_per_octave * log2(pymax(f0s, 1.0) / 415.0));
                if (she != 0.0 && m > 1)
                    pfade = pymax(1.0, fade_r * pow((double)(scp->sh_cap ? (m < scp->sh_cap ? m : scp->sh_cap) : m),
                                                    -she));
                double prel = rel_r;
                if (own)
                    prel = rel_r * (m <= 1 ? 1.0 : rk->rel_band[note][m <= 4 ? 0 : m <= 8 ? 1 : 2]);
                double pd[4];
                nv_partial_decay(rp, f0, m, pd);
                double rhz = f0 * eff, radius = 0.0;
                if (og->pipe_radius) {                  /* the pipe's own aperture (pipe_radius) */
                    radius = rhz <= 0.0 ? 0.0 : og->sound_speed / (og->pipe_scale_divisor * rhz);
                    tr.radius = radius;
                    tr.has_radius = 1;
                } else {
                    tr.radius = 0.0;
                    tr.has_radius = 0;
                }
                double gM = hv * rk->gain * nv_radiation_gain(host, hf, radius, og->pipe_radius);
                if (!isnan(n->organ_hx))                /* the Expression stop (harmonium_expression_gain) */
                    gM *= pow(h > 1.0 ? h : 1.0, og->expr_tilt * (n->organ_hx - 1.0));
                double gL = gM * nv_hrtf_gain(host, hf, tr.li), gR = gM * nv_hrtf_gain(host, hf, tr.ri);
                double cvp = cv_r * nv_chiff_harmonic_gain(cpv, h);
                memcpy(tr.tb, t->tb, sizeof tr.tb);
                if (og->mode_lock_spread > 0.0) {
                    double mlo = 0.0;
                    if (m > 1) {
                        double x = pow((double)m / og->mode_lock_knee, 2.0);
                        mlo = og->mode_lock_spread * (x / (1.0 + x));
                    }
                    if (mlo != 0.0) {
                        tr.tb[0] = mlo; tr.tb[1] = og->mode_lock_time; tr.tb[2] = og->mode_lock_time * 6.0;
                    }
                }
                double VB[3];
                if (!nv_voice_vibrato(host, f0, 0, VB)) {
                    VB[0] = VB0[0]; VB[1] = VB0[1]; VB[2] = VB0[2];
                }
                int nt_ = 0;
                if (tr.reflect) {
                    if (pos_x == t->pos_x_props || !og->spiral)
                        nt_ = note_terms(host, &tr, hf, pos_x, t->pos_z, nimg, nsurf, surf, img, mir, terms);
                    else {
                        int ni = nv_images(t->planes, t->order, pos_x * 1.0, host->room[0] * 1.0, t->pos_z * 1.0, 64,
                                           r_nsurf, r_surf, r_img, r_mir);
                        if (ni < 0 || t->order > 8) {
                            ret = -2;
                            goto done;
                        }
                        nt_ = note_terms(host, &tr, hf, pos_x, t->pos_z, ni, r_nsurf, r_surf, r_img, r_mir, rterms);
                        memcpy(terms, rterms, sizeof(double) * 9 * (nt_ > 0 ? nt_ : 0));
                    }
                    if (nt_ < 0) {
                        ret = -2;
                        goto done;
                    }
                }
                if (!emit(host, &tr, &R, qacc, azimuth, terms, nt_, 2 * PI * hf / sr, gL, gR, gM, hf, non_r + 0.0,
                          t->noff, pfade, prel, chiff_r, pd[1], pd[3], pd[2], rpp == hp ? t->sustain_level
                          : rpp->sustain_level, cvp, cc_r, t->crl, t->sjit, t->csc, gr, cr, 0.0, 0.0, VB, pos_x, 0)) {
                    ret = -1;
                    goto done;
                }
                pos_x = t->pos_x_props;             /* em.pos_x, back at the voice's place after each harmonic */
            }
        }
    }
    /* THE BELLOWS' PUSH (_push_finish): each row again, at its weight */
    fin[5] = (double)R.n;                      /* (where the push begins) */
    {
        int end = R.n, si = 0;
        for (int j = 0; j < end; j++) {
            while (si + 1 < nseg && seg_row[si + 1] <= j)
                si++;
            const OrganPipe *p = seg_pipe[si];
            if (p->push_gain == 0.0)
                continue;
            double fa = p->push_rise_s * sr;
            double *src = rows + NCOLS * j;
            double w = push_weight(p, src[11] / pymax(seg_f0[si], 1e-9), seg_f0[si]);
            double env = 1.0;
            if (w * env <= 1e-4)
                continue;
            double *r = row_new(&R);
            if (!r) {
                ret = -1;
                goto done;
            }
            memcpy(r, src, sizeof(double) * NCOLS);
            r[3] *= w * env; r[4] *= w * env; r[5] *= w * env;
            r[14] = fa;
            r[17] = push_rate(p, w) * log(10.0) / 20.0;
            r[18] = 0.0; r[19] = 0.0; r[20] = 0.0;
        }
    }
    fin[5] = (double)(R.n - fin[5]);           /* (the push's rows, the last) */
    fin[0] = tr.li; fin[1] = tr.ri; fin[2] = tr.dl; fin[3] = tr.dr;
    if (tr.has_radius)
        fin[4] = tr.radius;
    ret = R.n;
done:
#undef VOICE
    free(pv);
    return ret;
}
