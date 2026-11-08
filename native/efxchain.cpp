// efxchain.cpp -- A FILE'S OR A LIVE PART'S INSERTION EFFECT (gsefx.chain):
// the type's records (NV_FXN doubles each, nv.h) from its setting -- its
// type (msb, lsb), its parameters (p[1..20], -1 unset), its sends (40 03
// 17-19), its controllers (1B-1E) and their sources' values -- as nvrender
// builds each chain of a file's timeline and nvlive each of a live part's.
// A parallel type's branch B its own record (recb, *has_b), before A's.
// Returns 0, -1 where the type is not built (gsefx.BUILT), -3 where it is
// refused here (*why).
//
// X: the export's EFX block (K_EFX: the built codes, the native types'
// records -- their parameter numbers, defaults, marks and ranges -- the
// laws, the cabinets, the value tables); SR the render's rate.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>

#include "nv.h"

extern "C" int nv_efx_chain(const double *X, double SR, int msb, int lsb, const int *p, const int *snd,
                            const int *ctl, int ncv, const int *cv_src, const int *cv_val, double *rec,
                            double *recb, int *has_b, const char **why)
{
    std::map<int, int> cvv;                 // (each source's value, 'cv')
    for (int q = 0; q < ncv; q++)
        cvv[cv_src[q]] = cv_val[q];
    *has_b = 0;
    *why = "";
    const int code = msb * 128 + lsb;
    bool built = false;
    for (int q = 0; q < (int)X[0] && q < 128; q++)
        built = built || (int)X[1 + q] == code;
    if (!built)
        return -1;
    const double *D = nullptr;
    const int NK = (int)X[130], W = (int)X[131], DF = 3 + NK, MK = DF + 20;
    for (int q = 0; q < (int)X[129] && q < NV_EFX_NAT; q++)
        if ((int)X[132 + W * q] == code)
            D = X + 132 + W * q;
    auto refuse = [&](const char *w) {
        *why = w;
        return -3;
    };
    if (!D)
        return refuse("type");
    const int kind = (int)D[1];
    const bool bass = D[2] != 0.0;
    // (EFX_KEYS's order)
    enum { kLevel, kDrive, kAmpSw, kLowGain, kHiGain, kCmpAtck, kCmpSus, kCmpLevel, kCmpSw, kODSel, kODDrive,
           kODAmpSw, kODSw, kEQL, kEQMF, kEQMQ, kEQMG, kEQH, kODL, kODH, kCFSel, kCFRate, kCFDepth, kCFFb,
           kCFMix, kDlyTime, kDlyFb, kDlyMix, kEHSens, kTPSw, kAzimuth, kSpeed, kTurn, kClockwise, kAttack,
           kSustain, kPostGain, kType, kPreDly, kTime, kHFDamp, kBalance, kGateTime, kLBal, kPreDly1, kPreDly2,
           kPan1, kPan2, kCoarse1, kFine1, kCoarse2, kFine2, kPan, kPCoarse, kPFine, kFeedback, kWahFil,
           kWahMan, kWahPeak, kWahSw, kRate, kDepth, kPhase, kPreFilter, kCutoff, kPreDlyDev, kDepthDev,
           kPanDev, kChoRate, kChoDepth, kTremRate, kTremSep, kModWave, kModRate, kModDepth, kLowFreq,
           kHiFreq, kM1Freq, kM1Q, kM1Gain, kM2Freq, kM2Q, kM2Gain, kBand1, kBand2, kBand3, kBand4, kBand5,
           kBand6, kBand7, kBand8, kWidth, kDlyTmL, kDlyTmR, kFbMode, kPhaseL, kPhaseR, kDlyTmC, kDlyLevC,
           kDlyLevL, kDlyLevR, kDlyTm1, kDlyTm2, kDlyTm3, kDlyTm4, kDlyLev1, kDlyLev2, kDlyLev3, kDlyLev4,
           kModPhase, kManual, kReso, kMix, kFilType, kSens, kPeak, kPolarity, kStepRate, kDriveSw, kVowel,
           kAccel, kLoFiType, kPostFilter, kThreshold, kRatio, kRelease, kEHMix, kTPSel, kTPModWV, kTPModRT,
           kTPModDep, kAWSw, kAWFilter, kAWPeak, kAWMan, kAWDepth, kAWRate, kPHMix, kPHReso, kPHMan, kPHDepth,
           kPHRate, kLowSlow, kLowFast, kLowAccl, kLowLevel, kHiSlow, kHiFast, kHiAccl, kHiLevel, kSeparate,
           kRTLSlow, kRTLFast, kRTLoAccl, kRTLoLev, kRTHSlow, kRTHFast, kRTHiAccl, kRTHiLev, kRTSept,
           kRTSpeed, kRMMod, kRMBal, kPSCoarse, kPSFine, kPSBal, kRDetune, kRNzLev, kWPSel, kWPLPF, kWPLevel,
           kDiscType, kDiscLPF, kDiscNzLev, kHumType, kHumLPF, kHumLevel, kMS, kPanMono, kDSDrive, kDSAmpSw,
           kChoDly, kChoBal, kFLRate, kFLDepth, kFLDly, kFLBal, kFLFb, kDlyBal, kDlyHF, kOD1Drive, kOD1Sel,
           kOD1AmpSw, kOD2Drive, kOD2Sel, kOD2AmpSw, kAWSens, kAWPol, kChoLevel, kFLLevel, kDlyLevel,
           kODLevel, kOD1Level, kOD2Level, kRTLevel, kPHLevel, kAWLevel, kChoPan, kFLPan, kDlyPan, kODPan,
           kOD1Pan, kOD2Pan, kRTPan, kPHPan, kAWPan };
    auto has = [&](int key) { return D[3 + key] != 0.0; };
    // ...AND ITS CONTROLLERS' (gsefx.controlled): a + or # parameter at
    // "setting value + value from controller x depth (%)/100" of its
    // whole range, clamped and rounded, where its controller has a source
    const bool marked = ctl[0] != 0 || ctl[2] != 0;
    bool choice = false;
    auto controlled = [&](int n, int v) {
        for (int w = 0; w < 2; w++) {
            if ((int)D[MK + w] != n)
                continue;
            int src = ctl[2 * w];
            if (!src)
                continue;
            double dep = std::max(-1.0, std::min(1.0, (ctl[2 * w + 1] - 0x40) / 63.0));
            auto it = cvv.find(src);
            int cv = it != cvv.end() ? it->second : (src == 0x61 ? 64 : 0);
            double lo = D[MK + 2 + 2 * w], hi = D[MK + 3 + 2 * w];
            const int cho = (int)D[MK + 6 + w];
            if (lo < 0.0) {
                choice = true;              // (an export from before its choices)
                return v;
            }
            double x = (double)v + (hi - lo) * (cv / 127.0) * dep;
            x = std::max(lo, std::min(hi, x));
            if (cho) {                      // A CHOICE: the nearest code, the first of a tie
                int best = (int)lo;
                double bd = fabs(lo - x);
                for (int c = (int)lo + 1; c <= (int)hi; c++) {
                    if (cho == 2 && c != (int)hi)
                        continue;
                    double d = fabs((double)c - x);
                    if (d < bd) {
                        bd = d;
                        best = c;
                    }
                }
                return best;
            }
            return (int)nearbyint(x);       // (round: half to even)
        }
        return v;
    };
    auto g = [&](int key, int d) {      // the file's, the type's, ours -- and its controller's
        int n = (int)D[3 + key];
        if (!n)
            return d;
        int v = p[n] >= 0 ? p[n] : D[DF + n - 1] >= 0.0 ? (int)D[DF + n - 1] : d;
        if (marked && (n == (int)D[MK] || n == (int)D[MK + 1]))
            v = controlled(n, v);
        return v;
    };
    const double *L = X + 132 + NV_EFX_NAT * W;
    const double *T6 = L + 30 + 66, *AZ = T6 + 128, *T1 = AZ + 128, *T8 = T1 + 128;    // (value tables *6, *13, *1, *8)
    const double *T9 = T8 + 128 + 512;      // (*9, past the pans' places: a pre-filter's cutoff)
    const double *T2 = T8 + 128 + NV_EFX_PANS_TO_DEG + 2 * 5, *T3 = T2 + 128, *T4 = T3 + 128;  // (delay times)
    const double *T12 = T4 + 128, *T14 = T12 + 128;     // (a phaser's Manual, Hz; the Humanizer's Accel)
    auto clamp = [](int v) { return v < 0 ? 0 : v > 127 ? 127 : v; };
    auto od_gain = [&](int v, bool ds) {
        double x = clamp(v) / 127.0, lo = ds ? L[2] : L[0], hi = ds ? L[3] : L[1];
        return pow(10.0, (lo + (hi - lo) * x) / 20.0);
    };
    auto gain_db = [](int v) { return (double)std::max(-12, std::min(12, v - 64)); };
    double r[NV_FXN] = {};
    std::vector<double> par_b;              // (a parallel type's branch B: its record, before A's)
    r[21] = -1.0;
    r[33] = 1.0;                            // (a bus's dry and effect levels: the effect alone)
    r[31] = M_PI;                           // (its chorus's right output's LFO phase: GS_TAPS's)
    auto balance = [&](int v, double *dw) { // (gsefx.balance: "D>xE" up to D=E, past it "D x<E")
        v = clamp(v);
        if (v <= 0x40) {
            dw[0] = 1.0;
            dw[1] = std::min(1.0, 2.0 * v / 127.0);
        } else {
            dw[0] = std::min(1.0, 2.0 * (127 - v) / 127.0);
            dw[1] = 1.0;
        }
    };
    r[0] = g(kLevel, 127) / 127.0;
    const double mk = pow(10.0, L[4] / 20.0);
    if (kind == 4 || kind == 6) {
        // THE PART PLACED IN 3D: its angle the type's Azimuth, and 3D
        // Auto's turning at its Speed (turns a second), clockwise +
        double turn = 0.0;
        if (kind == 6 && g(kTurn, 1))           // (AUTO_TURN, AUTO_CLOCKWISE)
            turn = T6[clamp(g(kSpeed, 25))] * (g(kClockwise, 1) ? 1.0 : -1.0);
        r[22] = 1.0;
        r[23] = AZ[clamp(g(kAzimuth, 62))];
        r[24] = turn;
    } else if (kind == 5) {
        // A PART'S OWN BUS, the Compressor (efxbus.make's 'comp'): its
        // threshold from Sustain, ratio 8, attack from Attack, release
        // 150 ms, its makeup Post Gain's 6 dB steps
        double a = g(kAttack, 72) / 127.0;
        double att = 0.001 + 0.049 * a;
        r[25] = 2.0;
        r[26] = -10.0 - 30.0 * g(kSustain, 100) / 127.0;
        r[27] = 8.0;
        r[28] = exp(-1.0 / std::max(1.0, att * SR));
        r[29] = exp(-1.0 / std::max(1.0, 0.15 * SR));
        r[30] = pow(10.0, 6.0 * g(kPostGain, 0) / 20.0);
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind >= 11 && kind <= 16) {
        // THE CHORUS TYPES (gsefx._chorus): Space D 11, Stereo Chorus 12,
        // Hexa Chorus 13, Tremolo Chorus 14, 3D Chorus 15, Stereo Flanger
        // 16 -- the pre-delay and rate from Roland's tables (*1, *6), the
        // depth as the system chorus's swing (a flanger's an eighth of the
        // system law's, its feedback the comb's depth); two outputs apart by
        // their Phase, or the Hexa Chorus's six voices spread in delay,
        // depth and pan by its Dev parameters, or the 3D Chorus's two past
        // the speakers; a pre-filter's low pass; Balance its share
        const bool fl = kind == 16;
        const int kr = has(kRate) ? kRate : kChoRate, kd = has(kDepth) ? kDepth : kChoDepth;
        double rate = T6[clamp(g(kr, 8))];
        double swing = (g(kd, 64) + 1) / 3.2 / 1000.0 / 2.0 * (fl ? 1.0 / 8.0 : L[7]);
        double pd = T1[clamp(g(kPreDly, 10))];
        double pre = (std::isnan(pd) ? 0.0 : pd) / 1000.0;
        double lpf = 0.0;
        if (has(kPreFilter) && g(kPreFilter, 0) == 1) {     // (the LPF; its HPF is not built)
            double c = T9[clamp(g(kCutoff, 127))];
            lpf = std::isnan(c) ? 0.0 : c;
        }
        r[14] = 1.0;
        r[15] = pre + swing;
        r[16] = rate;
        r[17] = 2.0 * M_PI * rate * swing;
        r[18] = fl ? std::max(-0.98, std::min(0.98, (g(kFeedback, 104) - 64) * 2.0 / 100.0)) : 0.0;
        r[19] = lpf;
        r[20] = 0.0;
        r[21] = g(kBalance, 64) / 127.0;
        r[31] = has(kPhase) ? (2.0 * g(kPhase, (int)(180.0 / 2.0))) * (M_PI / 180.0)    // (math.radians)
                            : 180.0 * (M_PI / 180.0);                                   // (CHORUS_PHASE_DEG)
        if (kind == 13) {                   // (its voices' Devs: Pan, Pre Dly, Depth; the printed defaults)
            r[87] = 1.0;
            r[88] = clamp(g(kPanDev, 16));
            r[89] = g(kPreDlyDev, 5);
            r[90] = g(kDepthDev, 0x40 + 2);
        } else if (kind == 15) {
            r[87] = 2.0;
        }
        if (kind == 14) {                   // ITS TREMOLO (TREMOLO_CHORUS_DEPTH: half), stereo by Trem Sep
            r[55] = 2.0;
            r[56] = T6[clamp(g(kTremRate, 60))];
            r[57] = 0.5;
            r[58] = g(kTremSep, 96) > 0 ? 1.0 : 0.0;
        }
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind == 17 || kind == 18) {
        // TREMOLO, AUTO PAN: ROLAND'S DEPTH DIPS THE LEVEL (1 - d .. 1); the
        // tremolo pass swings about its carrier, so the part is taken down
        // to the swing's middle and the swing measured from there -- its
        // wave (WAVES, Mod Wave), Auto Pan's the right ear's opposite
        double d = g(kModDepth, 96) / 127.0;
        double mid = 1.0 - 0.5 * d;
        r[0] *= mid;
        r[55] = 1.0;
        r[56] = T6[clamp(g(kModRate, 60))];
        r[57] = 0.5 * d / mid;
        r[58] = kind == 18 ? 1.0 : 0.0;
        r[59] = std::min(4, g(kModWave, 2));
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind >= 21 && kind <= 26) {
        // THE DELAY TYPES (gsefx._delay): gsdelay taps (time, level, side,
        // period) -- each time through its own value table (*2, *3, *4),
        // its default the type's, else 0 -- the feedback, HF Damp a low
        // pass; the Stereo and Mod Delay's two loops at their own periods,
        // a phase their tap's sign, Fb Mode the ping-pong; the 3 Tap's
        // centre, left and right, the 3D Delay's past the speakers; the 4
        // Tap's across the field (FOUR_TAP_SIDES: the pans' table's 1, 43,
        // 85, 127); Tm Ctrl's one, at its pan -- a silent tap dropped, the
        // effect at its Balance's share over the dry (DRY_FLOOR)
        auto sec = [&](const double *T, int key) {
            double x = T[clamp(g(key, 0))];
            return (std::isnan(x) ? 0.0 : x) / 1000.0;
        };
        double tp[4][4];
        int nt = 0;
        auto tap = [&](double t, double lv, int sd, double per) {
            tp[nt][0] = t; tp[nt][1] = lv; tp[nt][2] = sd; tp[nt][3] = per;
            nt++;
        };
        if (kind == 21 || kind == 22) {
            double tl = sec(T4, kDlyTmL), tr = sec(T4, kDlyTmR);
            tap(tl, g(kPhaseL, 0) ? -1.0 : 1.0, 0, tl);
            tap(tr, g(kPhaseR, 0) ? -1.0 : 1.0, 1, tr);
        } else if (kind == 23 || kind == 26) {
            const double *T = kind == 23 ? T2 : T4;
            double tc = sec(T, kDlyTmC);
            tap(sec(T, kDlyTmC), g(kDlyLevC, 127) / 127.0, 2, tc);      // (TAP_LEVEL)
            tap(sec(T, kDlyTmL), g(kDlyLevL, 127) / 127.0, kind == 23 ? 0 : 300, tc);
            tap(sec(T, kDlyTmR), g(kDlyLevR, 127) / 127.0, kind == 23 ? 1 : 301, tc);
        } else if (kind == 24) {
            static const int FOUR[4] = {101, 143, 185, 227};
            const int kt[4] = {kDlyTm1, kDlyTm2, kDlyTm3, kDlyTm4}, kl[4] = {kDlyLev1, kDlyLev2, kDlyLev3, kDlyLev4};
            double t1 = sec(T2, kDlyTm1);
            for (int j = 0; j < 4; j++)
                tap(sec(T2, kt[j]), g(kl[j], 127) / 127.0, FOUR[j], t1);
        } else {
            double t = sec(T3, kDlyTime);
            tap(t, 1.0, g(kPan, 64) != 64 ? 100 + clamp(g(kPan, 64)) : 2, t);
        }
        double hf = T8[clamp(g(kHFDamp, 127))];
        double dw[2];
        balance(g(kBalance, 37), dw);
        const double DRY_FLOOR = 1e-3, dk = std::max(dw[0], DRY_FLOOR);
        r[34] = 2.0;
        r[96] = dw[1] / dk;                 // (level: the effect over the dry)
        r[97] = std::max(-0.98, std::min(0.98, (g(kFeedback, 64) - 64) * 2.0 / 100.0));
        r[98] = std::isnan(hf) ? 0.0 : hf;  // (Bypass: none)
        r[99] = tp[0][3];                   // (tc: the first tap's period, a silent one's too)
        int kept = 0;
        for (int j = 0; j < nt; j++) {
            if (tp[j][1] == 0.0)
                continue;
            double *T = r + 101 + 5 * kept++;
            T[0] = tp[j][0]; T[1] = tp[j][1]; T[2] = tp[j][2]; T[3] = tp[j][3]; T[4] = 1.0;
        }
        r[100] = kept;
        r[121] = (kind == 21 || kind == 22) && g(kFbMode, 0) ? 1.0 : 0.0;
        if (kind == 22) {                   // (the Mod Delay's LFO: Mod Rate *6, efx_swing, Mod Phase)
            r[122] = T6[clamp(g(kModRate, 12))];
            r[123] = (g(kModDepth, 21) + 1) / 3.2 / 1000.0 / 2.0 * L[7];
            r[124] = (2.0 * g(kModPhase, 45)) * (M_PI / 180.0);
        }
        r[0] *= dk;
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind >= 27 && kind <= 30) {
        // THE MOVING FILTERS (gsefx._filter, efxfilter): the type and its
        // parameters, and this setting's control (r[128]: 1 a sweep --
        // base Hz, octaves, rate, up (NaN: a phaser, about its base), Sens
        // octaves; 2 a flanger's line -- base s, swing s, rate, step rate;
        // 3 the Humanizer's vowel -- which, its glide)
        const double WAH_HZ0 = 200.0, WAH_HZ1 = 4000.0, WAH_Q0 = 0.7, WAH_Q1 = 12.0;
        auto wah_hz = [&](int v) { return WAH_HZ0 * pow(WAH_HZ1 / WAH_HZ0, clamp(v) / 127.0); };
        auto wah_q = [&](int v) { return WAH_Q0 * pow(WAH_Q1 / WAH_Q0, clamp(v) / 127.0); };
        r[50] = 1.0;
        if (kind == 27) {                   // PHASER: four all-passes about its Manual (PHASER_OCT)
            r[51] = 1.0;
            r[52] = g(kMix, 64) / 127.0;
            r[53] = 0.9 * g(kReso, 16) / 127.0;
            r[134] = 4.0;                   // (PHASER_STAGES)
            r[128] = 1.0;
            r[129] = T12[clamp(g(kManual, 36))];
            r[130] = 2.0 * g(kDepth, 64) / 127.0;
            r[131] = T6[clamp(g(kRate, 16))];
            r[132] = NAN;
            r[133] = 0.0;
        } else if (kind == 28) {            // AUTO WAH: up (or down) from its Manual, and by Sens (AUTOWAH_OCT, _SENS_OCT)
            r[51] = g(kFilType, 1) == 0 ? 2.0 : 3.0;
            r[52] = wah_q(g(kPeak, 62));
            r[53] = 1.0;
            r[128] = 1.0;
            r[129] = wah_hz(g(kManual, 68));
            r[130] = 3.0 * g(kDepth, 72) / 127.0;
            r[131] = T6[clamp(g(kRate, 40))];
            r[132] = g(kPolarity, 1) ? 1.0 : 0.0;
            r[133] = 3.0 * g(kSens, 0) / 127.0;
        } else if (kind == 29) {            // STEP FLANGER: a moving comb, its line stepped at Step Rate
            double pd = T1[clamp(g(kPreDly, 10))];
            r[51] = 4.0;
            r[52] = g(kBalance, 64) / 127.0;
            r[53] = std::max(-0.98, std::min(0.98, (g(kFeedback, 79) - 64) * 2.0 / 100.0));
            r[128] = 2.0;
            r[129] = (std::isnan(pd) ? 0.0 : pd) / 1000.0;
            r[130] = (g(kDepth, 95) + 1) / 3.2 / 1000.0 / 2.0 * (1.0 / 8.0);    // (efx_swing, a flanger's)
            r[131] = T6[clamp(g(kRate, 5))];
            r[132] = T6[clamp(g(kStepRate, 54))];
        } else {                            // HUMANIZER: its vowel's formants, gliding at its Accel; its drive
            double acc = T14[clamp(g(kAccel, 64))];
            if (std::isnan(acc) || acc == 0.0)
                acc = 8.0;                  // (table_value(14, ...) or 8.0)
            r[51] = 5.0;
            r[52] = 0.15;                   // (VOWEL_FLOOR)
            r[53] = 1.5;
            r[128] = 3.0;
            r[129] = std::min(4, g(kVowel, 0));
            r[130] = 0.5 * pow(0.03, acc / 15.0);
            if (g(kDriveSw, 0)) {
                r[1] = od_gain(g(kDrive, 48), false);
                r[0] *= mk;
            }
        }
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind == 34 || kind == 35) {
        // ROTARY (gsefx._rotary): the part through our Leslie -- each
        // rotor's slow and fast speeds (*6), its spin times from its
        // Accl (*14: accl_tau, coasting down 1.4 times slower), the two
        // rotors' levels against the louder, the speed the file asks
        // for, Separate the microphones' angle apart. The ROTARY MULTI's
        // (its RT parameters) after its OD -- the valve's gain stage, no
        // guitar cabinet: the Leslie is the speaker -- and its EQ
        const bool mu = kind == 35;
        auto tau = [&](int key, int d) { return exp(1.7226 - 0.1566 * T14[clamp(g(key, d))]); };
        r[140] = 1.0;
        r[141] = T6[clamp(g(mu ? kRTLSlow : kLowSlow, 6))];
        r[142] = T6[clamp(g(mu ? kRTLFast : kLowFast, 113))];
        r[143] = T6[clamp(g(mu ? kRTHSlow : kHiSlow, 17))];
        r[144] = T6[clamp(g(mu ? kRTHFast : kHiFast, 120))];
        r[145] = tau(mu ? kRTLoAccl : kLowAccl, 24);
        r[146] = 1.4 * r[145];
        r[147] = tau(mu ? kRTHiAccl : kHiAccl, 88);
        r[148] = 1.4 * r[147];
        const int llv = g(mu ? kRTLoLev : kLowLevel, 127), hlv = g(mu ? kRTHiLev : kHiLevel, 64);
        const double top = (double)std::max(std::max(llv, hlv), 1);
        r[149] = llv / top;
        r[150] = hlv / top;
        r[151] = g(mu ? kRTSpeed : kSpeed, 0) != 0 ? 1.0 : 0.0;
        r[152] = M_PI * g(mu ? kRTSept : kSeparate, 96) / 127.0;
        r[6] = 1.0;
        if (mu) {
            if (g(kODSw, 1)) {
                r[1] = od_gain(g(kODDrive, 13), false);
                r[0] *= mk;
            }
            r[7] = gain_db(g(kEQL, 64));
            r[8] = L[13 + clamp(g(kEQMF, 72)) / 8];
            r[9] = L[8 + std::min(4, g(kEQMQ, 1))];
            r[10] = gain_db(g(kEQMG, 64));
            r[11] = gain_db(g(kEQH, 64));
        } else {
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        }
    } else if (kind == 38) {
        // THE PARALLEL PAIRS (gsefx.PARALLEL_TYPES): branch A's stage on the
        // part's own rows, branch B's on a copy of them on its virtual
        // channel (nv_play's, as _par_close) -- each stage by its names
        // (gsefx._stage) at its Level (BRANCH_LEVEL), each at its Pan
        // (pan_gains); B from the base, as A (ob = dict(out))
        // (stages: 0 Cho, 1 FL, 2 Dly, 3 OD, 4 OD1, 5 OD2, 6 RT, 7 PH, 8 AW)
        static const int PAIRS[9][2] = {{0, 2}, {1, 2}, {0, 1}, {4, 5}, {3, 6}, {3, 7}, {3, 8}, {7, 6}, {7, 8}};
        static const int LEV[9] = {kChoLevel, kFLLevel, kDlyLevel, kODLevel, kOD1Level, kOD2Level, kRTLevel,
                                   kPHLevel, kAWLevel};
        static const int PAN[9] = {kChoPan, kFLPan, kDlyPan, kODPan, kOD1Pan, kOD2Pan, kRTPan, kPHPan, kAWPan};
        if (lsb > 8)
            return refuse("type");
        auto fbk = [](int v) { return std::max(-0.98, std::min(0.98, (v - 64) * 2.0 / 100.0)); };
        auto ms = [&](const double *T, int key, int d) {
            double v = T[clamp(g(key, d))];
            return (std::isnan(v) ? 0.0 : v) / 1000.0;
        };
        auto stage = [&](double *o, int s) {
            if (s <= 1) {                   // a chorus or flanger (gs_copies: Bal its share)
                const bool fl = s == 1;
                const double rate = T6[clamp(g(fl ? kFLRate : kChoRate, 8))];
                const double swing = (g(fl ? kFLDepth : kChoDepth, 64) + 1) / 3.2 / 1000.0 / 2.0
                                     * (fl ? 1.0 / 8.0 : L[7]);
                o[14] = 1.0;
                o[15] = ms(T1, fl ? kFLDly : kChoDly, 10) + swing;
                o[16] = rate;
                o[17] = 2.0 * M_PI * rate * swing;
                o[18] = fl ? fbk(g(kFLFb, 104)) : 0.0;
                o[19] = 0.0;
                o[20] = 0.0;
                o[21] = g(fl ? kFLBal : kChoBal, 64) / 127.0;
            } else if (s == 2) {            // a delay (one tap, *4; Bal its dry and effect; HF *8)
                const double t = ms(T4, kDlyTime, 111), hf = T8[clamp(g(kDlyHF, 127))];
                double dw[2];
                balance(g(kDlyBal, 37), dw);
                o[34] = 1.0;
                o[35] = dw[1] / std::max(dw[0], 1e-3);
                o[36] = fbk(g(kDlyFb, 80));
                o[37] = std::isnan(hf) ? 0.0 : hf;
                o[38] = t;
                o[39] = 1.0;
                const double t1[5] = {t, 1.0, 2.0, t, 1.0};
                std::copy(t1, t1 + 5, o + 40);
                o[0] *= std::max(dw[0], 1e-3);
            } else if (s <= 5) {            // an OD (the valve's gain stage, its cabinet)
                const int kd = s == 3 ? kODDrive : s == 4 ? kOD1Drive : kOD2Drive;
                const int ks = s == 3 ? kODSel : s == 4 ? kOD1Sel : kOD2Sel;
                const int ka = s == 3 ? kODAmpSw : s == 4 ? kOD1AmpSw : kOD2AmpSw;
                o[1] = od_gain(g(kd, 48), g(ks, 0) != 0);
                o[0] *= mk;
                if (g(ka, 1))
                    o[2] = 1.0;
            } else if (s == 6) {            // a rotary (the Rotary Multi's RT)
                auto tau = [&](int key, int d) { return exp(1.7226 - 0.1566 * T14[clamp(g(key, d))]); };
                o[140] = 1.0;
                o[141] = T6[clamp(g(kRTLSlow, 6))];
                o[142] = T6[clamp(g(kRTLFast, 113))];
                o[143] = T6[clamp(g(kRTHSlow, 17))];
                o[144] = T6[clamp(g(kRTHFast, 120))];
                o[145] = tau(kRTLoAccl, 24);
                o[146] = 1.4 * o[145];
                o[147] = tau(kRTHiAccl, 88);
                o[148] = 1.4 * o[147];
                const int llv = g(kRTLoLev, 127), hlv = g(kRTHiLev, 64);
                const double top = (double)std::max(std::max(llv, hlv), 1);
                o[149] = llv / top;
                o[150] = hlv / top;
                o[151] = g(kRTSpeed, 0) != 0 ? 1.0 : 0.0;
                o[152] = M_PI * g(kRTSept, 96) / 127.0;
            } else if (s == 7) {            // a phaser (efxfilter: PHASER_OCT, PHASER_STAGES)
                o[50] = 1.0;
                o[51] = 1.0;
                o[52] = g(kPHMix, 64) / 127.0;
                o[53] = 0.9 * g(kPHReso, 16) / 127.0;
                o[134] = 4.0;
                o[128] = 1.0;
                o[129] = T12[clamp(g(kPHMan, 36))];
                o[130] = 2.0 * g(kPHDepth, 64) / 127.0;
                o[131] = T6[clamp(g(kPHRate, 16))];
                o[132] = NAN;
                o[133] = 0.0;
            } else {                        // an auto wah (wah_q, wah_hz; AUTOWAH_OCT, AUTOWAH_SENS_OCT)
                o[50] = 1.0;
                o[51] = g(kAWFilter, 1) == 0 ? 2.0 : 3.0;
                o[52] = 0.7 * pow(12.0 / 0.7, clamp(g(kAWPeak, 62)) / 127.0);
                o[53] = 1.0;
                o[134] = 0.0;
                o[128] = 1.0;
                o[129] = 200.0 * pow(4000.0 / 200.0, clamp(g(kAWMan, 68)) / 127.0);
                o[130] = 3.0 * g(kAWDepth, 72) / 127.0;
                o[131] = T6[clamp(g(kAWRate, 40))];
                o[132] = g(kAWPol, 1) ? 1.0 : 0.0;
                o[133] = 3.0 * g(kAWSens, 0) / 127.0;
            }
            o[0] *= std::max(g(LEV[s], 96), 1) / 127.0;
        };
        auto pan_gains = [&](int v, double *lr) {
            const double th = (clamp(v) - 64) / 63.0 * 0.25 * M_PI + 0.25 * M_PI;
            lr[0] = sqrt(2.0) * cos(th);
            lr[1] = sqrt(2.0) * sin(th);
        };
        const int sa = PAIRS[lsb][0], sb = PAIRS[lsb][1];
        par_b.assign(r, r + NV_FXN);
        stage(r, sa);
        stage(par_b.data(), sb);
        double pa[2], pb[2];
        pan_gains(g(PAN[sa], 64), pa);
        pan_gains(g(PAN[sb], 64), pb);
        r[208] = 1.0;
        r[209] = (par_b[0] * (par_b[1] != 0.0 ? par_b[1] : 1.0))
                 / std::max(r[0] * (r[1] != 0.0 ? r[1] : 1.0), 1e-12);     // (B's level against A's)
        r[210] = pa[0];
        r[211] = pa[1];
        r[212] = pb[0];
        r[213] = pb[1];
    } else if (kind == 37) {
        // THE SERIES PAIRS (gsefx: OD/DS -> Chorus/Flanger/Delay, Cho/FL
        // -> Delay, EH -> ..., Cho -> Flanger): each stage by its names --
        // the Enhancer the part's bus (after the rest, as there), the
        // drive the valve's gain stage and its cabinet, the chorus or
        // flanger the chain's device (Bal its share), Cho -> Flanger's
        // flanger a moving comb after the copies (Step Flanger's, no
        // steps), the delay one tap (*4, Bal its dry and effect, HF *8)
        auto fbk = [](int v) { return std::max(-0.98, std::min(0.98, (v - 64) * 2.0 / 100.0)); };
        auto ms = [&](const double *T, int key, int d) {
            double v = T[clamp(g(key, d))];
            return (std::isnan(v) ? 0.0 : v) / 1000.0;
        };
        if (has(kEHSens)) {
            r[25] = 5.0;
            r[26] = exp(-2.0 * M_PI * 2000.0 / SR);
            r[27] = 1.0 + 15.0 * g(kEHSens, 64) / 127.0;
            r[28] = g(kEHMix, 64) / 127.0;
        }
        for (int ds = 0; ds < 2; ds++) {
            const int kdr = ds ? kDSDrive : kODDrive, ksw = ds ? kDSAmpSw : kODAmpSw;
            if (!has(kdr))
                continue;
            r[1] = od_gain(g(kdr, 48), ds == 1);
            r[0] *= mk;
            if (g(ksw, 1))
                r[2] = 1.0;
        }
        for (int fl = 0; fl < 2; fl++) {
            const int kra = fl ? kFLRate : kChoRate, kde = fl ? kFLDepth : kChoDepth;
            const int kdl = fl ? kFLDly : kChoDly, kba = fl ? kFLBal : kChoBal;
            if (fl && has(kChoRate) && has(kFLRate)) {
                r[50] = 1.0;
                r[51] = 4.0;
                r[52] = g(kFLBal, 64) / 127.0;
                r[53] = fbk(g(kFLFb, 104));
                r[128] = 2.0;
                r[129] = ms(T1, kFLDly, 16);
                r[130] = (g(kFLDepth, 24) + 1) / 3.2 / 1000.0 / 2.0 * (1.0 / 8.0);
                r[131] = T6[clamp(g(kFLRate, 11))];
                r[132] = NAN;
                continue;
            }
            if (!has(kra))
                continue;
            const double rate = T6[clamp(g(kra, 8))];
            const double swing = (g(kde, 64) + 1) / 3.2 / 1000.0 / 2.0 * (fl ? 1.0 / 8.0 : L[7]);
            r[14] = 1.0;
            r[15] = ms(T1, kdl, 10) + swing;
            r[16] = rate;
            r[17] = 2.0 * M_PI * rate * swing;
            r[18] = fl ? fbk(g(kFLFb, 104)) : 0.0;
            r[19] = 0.0;
            r[20] = 0.0;
            r[21] = g(kba, 64) / 127.0;
        }
        if (has(kDlyTime)) {
            const double t = ms(T4, kDlyTime, 106);
            double dw[2];
            balance(g(kDlyBal, 37), dw);
            const double hf = T8[clamp(g(kDlyHF, 127))];
            r[34] = 1.0;
            r[35] = dw[1] / std::max(dw[0], 1e-3);
            r[36] = fbk(g(kDlyFb, 80));
            r[37] = std::isnan(hf) ? 0.0 : hf;
            r[38] = t;
            r[39] = 1.0;
            const double t1[5] = {t, 1.0, 2.0, t, 1.0};
            std::copy(t1, t1 + 5, r + 40);
            r[0] *= std::max(dw[0], 1e-3);
        }
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind == 36) {
        // LO-FI 2 (gsefx: its unprinted defaults no detune, white, the
        // noises silent and unfiltered, LP, 50 Hz, stereo, the effect
        // alone): a part's bus (efxbus.LoFi2) -- its Type, the filter
        // after (Fil Type, Cutoff: the export's Butterworths), the radio,
        // the noises' levels and low passes (*11, 0 Bypass), M/S, Pan
        const double *T11 = T14 + 128, *BW = T11 + 128, *BAND = BW + 128 * 12;
        auto lp = [&](int key) { double v = T11[clamp(g(key, 127))]; return std::isnan(v) ? 0.0 : v; };
        const int fil = g(kFilType, 0), cut = clamp(g(kCutoff, 32));
        r[25] = 6.0;
        r[176] = std::max(1, std::min(6, g(kLoFiType, 1) + 1)) - 1;
        r[177] = fil;
        r[178] = g(kRDetune, 0);
        r[179] = g(kRNzLev, 64);
        r[180] = g(kWPSel, 0);
        r[181] = lp(kWPLPF);
        r[182] = g(kWPLevel, 0);
        r[183] = std::max(0, std::min(3, g(kDiscType, 0)));
        r[184] = lp(kDiscLPF);
        r[185] = g(kDiscNzLev, 0);
        r[186] = g(kHumType, 0);
        r[187] = lp(kHumLPF);
        r[188] = g(kHumLevel, 0);
        r[189] = g(kMS, 1);
        r[190] = g(kPanMono, 64);
        for (int q = 0; q < 6; q++) {
            r[191 + q] = BW[12 * cut + (fil == 1 ? 0 : 6) + q];
            r[197 + q] = BAND[q];
        }
        double dw[2];
        balance(g(kBalance, 127), dw);
        r[32] = dw[0];
        r[33] = dw[1];
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind >= 31 && kind <= 33) {
        // THE BUSES (efxbus.make): LO-FI 1 the tone's Lo-Fi bus (its Type
        // a held rate and bits, its Pre and Post Filter one-pole corners,
        // LOFI_*), dry against effect by Balance; LIMITER the Compressor's
        // (its Threshold, Ratio, Release, Post Gain's 6 dB steps, a 1 ms
        // attack); ENHANCER its own: the top octaves above 2 kHz saturated
        // by Sens and mixed back by Mix
        if (kind == 31) {
            static const double RATE[9] = {32000, 22050, 16000, 12000, 11025, 8000, 6000, 5000, 4000};
            static const int BITS[9] = {14, 12, 11, 10, 9, 8, 7, 6, 5};
            static const double FHZ[6] = {0.0, 8000.0, 6000.0, 4000.0, 2500.0, 1500.0};
            const int k = std::max(1, std::min(9, g(kLoFiType, 5) + 1)) - 1;
            const int pre = std::max(1, std::min(6, g(kPreFilter, 1) + 1)) - 1;
            const int post = std::max(1, std::min(6, g(kPostFilter, 1) + 1)) - 1;
            r[25] = 1.0;
            r[26] = SR / RATE[k];
            r[27] = pow(2.0, -(double)(BITS[k] - 1));
            r[28] = FHZ[pre] != 0.0 ? exp(-2.0 * M_PI * FHZ[pre] / SR) : 0.0;
            r[29] = FHZ[post] != 0.0 ? exp(-2.0 * M_PI * FHZ[post] / SR) : 0.0;
            double dw[2];
            balance(g(kBalance, 127), dw);
            r[32] = dw[0];
            r[33] = dw[1];
        } else if (kind == 32) {
            static const double RATIO[4] = {1.5, 2.0, 4.0, 100.0};
            const double rel = 0.01 * pow(100.0, g(kRelease, 16) / 127.0);
            r[25] = 2.0;
            r[26] = -60.0 * (1.0 - g(kThreshold, 85) / 127.0);
            r[27] = RATIO[std::min(3, g(kRatio, 2))];
            r[28] = exp(-1.0 / std::max(1.0, 0.001 * SR));
            r[29] = exp(-1.0 / std::max(1.0, rel * SR));
            r[30] = pow(10.0, 6.0 * g(kPostGain, 0) / 20.0);
        } else {
            r[25] = 5.0;
            r[26] = exp(-2.0 * M_PI * 2000.0 / SR);         // (ENH_HZ)
            r[27] = 1.0 + 15.0 * g(kSens, 64) / 127.0;
            r[28] = g(kMix, 64) / 127.0;
        }
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind == 19) {
        // STEREO-EQ: its shelves at their chosen corners, two mids
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[8] = L[13 + clamp(g(kM1Freq, 72)) / 8];
        r[9] = L[8 + std::min(4, g(kM1Q, 1))];
        r[10] = gain_db(g(kM1Gain, 64));
        r[11] = gain_db(g(kHiGain, 64));
        r[60] = std::min(1, g(kLowFreq, 0)) ? 400.0 : 200.0;
        r[61] = std::min(1, g(kHiFreq, 0)) ? 8000.0 : 4000.0;
        r[62] = 1.0;
        r[63] = L[13 + clamp(g(kM2Freq, 56)) / 8];
        r[64] = L[8 + std::min(4, g(kM2Q, 1))];
        r[65] = gain_db(g(kM2Gain, 64));
    } else if (kind == 20) {
        // SPECTRUM: a static filter, eq_gain's mids at SPECTRUM_HZ, no shelves
        static const double SPECTRUM_HZ[8] = {250.0, 500.0, 1000.0, 1250.0, 2000.0, 3150.0, 4000.0, 8000.0};
        r[6] = 1.0;
        r[60] = 400.0;
        r[61] = 4000.0;
        r[62] = 8.0;
        const double q = L[8 + std::min(4, g(kWidth, 2))];
        for (int j = 0; j < 8; j++) {
            r[63 + 3 * j] = SPECTRUM_HZ[j];
            r[64 + 3 * j] = q;
            r[65 + 3 * j] = gain_db(g(kBand1 + j, 64));
        }
    } else if (kind == 9 || kind == 10) {
        // THE PITCH SHIFTERS (gsdelay taps that move each repeat's pitch):
        // 2 Pitch Shifter's two voices at their own pitch, delay and pan,
        // L.Bal between them, no feedback; Fb P.Shifter's one, spiralling
        // by its ratio round its feedback -- the effect at its Balance's
        // share over the dry (DRY_FLOOR), in the GS delay's place, sent whole
        auto pre = [&](int key, int d) {    // (table *1, ms -> s; Bypass 0)
            double v = T1[clamp(g(key, d))];
            return (std::isnan(v) ? 0.0 : v) / 1000.0;
        };
        auto side = [&](int key) { return g(key, 64) != 64 ? 100.0 + clamp(g(key, 64)) : 2.0; };
        auto semis = [&](int co, int fi) {  // (gsefx.semitones)
            return pow(2.0, (co - 0x40) / 12.0 + (fi - 0x40) * 2.0 / 1200.0);
        };
        double dw[2], *T = r + 40;
        int nt;
        double fb;
        if (kind == 9) {
            double lab[2];
            balance(g(kLBal, 64), lab);
            const double t1[5] = {pre(kPreDly1, 0), lab[0], side(kPan1), 1.0, semis(g(kCoarse1, 71), g(kFine1, 62))};
            const double t2[5] = {pre(kPreDly2, 0), lab[1], side(kPan2), 1.0, semis(g(kCoarse2, 59), g(kFine2, 66))};
            std::copy(t1, t1 + 5, T);
            std::copy(t2, t2 + 5, T + 5);
            nt = 2;
            fb = 0.0;
        } else {
            double t = pre(kPreDly, 95);
            const double t1[5] = {t, 1.0, side(kPan), t, semis(g(kPCoarse, 71), g(kPFine, 64))};
            std::copy(t1, t1 + 5, T);
            nt = 1;
            fb = std::max(-0.98, std::min(0.98, (g(kFeedback, 84) - 64) * 2.0 / 100.0));
        }
        balance(g(kBalance, 64), dw);
        const double DRY_FLOOR = 1e-3, dk = std::max(dw[0], DRY_FLOOR);
        r[34] = 1.0;
        r[35] = dw[1] / dk;                 // (level: the effect over the dry)
        r[36] = fb;
        r[37] = 0.0;                        // (no line filter)
        r[38] = std::max(T[0], 1e-3);       // (tc: the first tap's time)
        r[39] = nt;
        r[0] *= dk;
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind == 7 || kind == 8) {
        // A PART'S OWN BUS, a reverb (efxbus.Reverb, GateReverb: native/efxrev.c's):
        // Reverb's type, pre-delay, Time and HF damp; Gate Reverb's type,
        // pre-delay and gate time (5 ms a step, 5-500 ms); dry against effect by Balance
        r[25] = kind == 7 ? 3.0 : 4.0;
        r[26] = g(kType, 0);
        double pd = T1[clamp(g(kPreDly, kind == 7 ? 112 : 5))];
        r[27] = std::isnan(pd) ? 0.0 : pd;
        if (kind == 7) {
            r[28] = g(kTime, 120);
            r[29] = T8[clamp(g(kHFDamp, 104))];     // (NaN: Bypass, 20 kHz)
        } else {
            r[28] = 5.0 * (std::min(99, g(kGateTime, 12)) + 1);
        }
        balance(g(kBalance, kind == 7 ? 64 : 32), r + 32);
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else if (kind == 1 || kind == 2) {
        r[1] = od_gain(g(kDrive, 48), kind == 2);
        r[0] *= mk;
        if (g(kAmpSw, 1))
            r[2] = 1.0;
        r[6] = 1.0;
        r[7] = gain_db(g(kLowGain, 64));
        r[11] = gain_db(g(kHiGain, 64));
    } else {
        if (has(kCmpSw) && g(kCmpSw, 1)) {
            double sus = g(kCmpSus, 64) / 127.0;
            r[3] = 1.0 / (1.0 + 3.0 * sus);
            r[4] = g(kCmpLevel, 64) / 64.0;
            r[5] = L[5] * g(kCmpAtck, 70) / 127000.0;
        }
        if (has(kODDrive) && g(kODSw, 1)) {
            r[1] = od_gain(g(kODDrive, 48), g(kODSel, 0) != 0);
            r[0] *= mk;
            if (g(kODAmpSw, 1))
                r[2] = bass ? 2.0 : 1.0;
        }
        if (has(kEQL)) {
            r[6] = 1.0;
            r[7] = gain_db(g(kEQL, 64));
            r[8] = L[13 + clamp(g(kEQMF, 64)) / 8];
            r[9] = L[8 + std::min(4, g(kEQMQ, 1))];
            r[10] = gain_db(g(kEQMG, 64));
            r[11] = gain_db(g(kEQH, 64));
        } else if (has(kODL)) {
            r[6] = 1.0;
            r[7] = gain_db(g(kODL, 64));
            r[11] = gain_db(g(kODH, 64));
        }
        if (has(kCFRate)) {
            // (cf_device: rate2, efx_swing, feedback; a chorus 10 ms, a flanger 1 ms)
            bool fl = g(kCFSel, 0) != 0;
            double rate = 0.05 * (clamp(g(kCFRate, 8)) + 1);
            double swing = (g(kCFDepth, 40) + 1) / 3.2 / 1000.0 / 2.0 * (fl ? 1.0 / 8.0 : L[7]);
            r[14] = 1.0;
            r[15] = (fl ? 0.001 : 0.010) + swing;
            r[16] = rate;
            r[17] = 2.0 * M_PI * rate * swing;
            r[18] = std::max(-0.98, std::min(0.98, (g(kCFFb, 64) - 64) * 2.0 / 100.0));
            r[19] = 0.0;
            r[20] = g(kCFMix, 0) / 127.0;
        }
        // CLEAN GT MULTI 2's AUTO WAH (unprinted: on, up), the RHODES MULTI's
        // PHASER (efxfilter, gsefx._filter: Rate2 their rates)
        auto rate2 = [&](int v) { return 0.05 * (clamp(v) + 1); };
        if (has(kAWMan) && g(kAWSw, 1)) {
            r[50] = 1.0;
            r[51] = g(kAWFilter, 1) == 0 ? 2.0 : 3.0;
            r[52] = 0.7 * pow(12.0 / 0.7, clamp(g(kAWPeak, 40)) / 127.0);     // (wah_q)
            r[53] = 1.0;
            r[128] = 1.0;
            r[129] = 200.0 * pow(4000.0 / 200.0, clamp(g(kAWMan, 55)) / 127.0); // (wah_hz)
            r[130] = 3.0 * g(kAWDepth, 80) / 127.0;
            r[131] = rate2(g(kAWRate, 29));
            r[132] = 1.0;
            r[133] = 0.0;
        } else if (has(kPHMan)) {
            const double *T12 = T8 + 128 + NV_EFX_PANS_TO_DEG + 2 * 5 + 3 * 128;
            r[50] = 1.0;
            r[51] = 1.0;
            r[52] = g(kPHMix, 64) / 127.0;
            r[53] = 0.9 * g(kPHReso, 16) / 127.0;
            r[134] = 4.0;                   // (PHASER_STAGES)
            r[128] = 1.0;
            r[129] = T12[clamp(g(kPHMan, 36))];
            r[130] = 2.0 * g(kPHDepth, 32) / 127.0;
            r[131] = rate2(g(kPHRate, 16));
            r[132] = NAN;
            r[133] = 0.0;
        }
        if (has(kEHSens)) {                 // ...its Enhancer: the part's bus (efxbus.Enhancer)
            r[25] = 5.0;
            r[26] = exp(-2.0 * M_PI * 2000.0 / SR);
            r[27] = 1.0 + 15.0 * g(kEHSens, 64) / 127.0;
            r[28] = g(kEHMix, 64) / 127.0;
        }
        if (has(kTPSw) && g(kTPSw, 1)) {    // ...its Tremolo/Pan (unprinted: on, Trem, the sine): the Tremolo type's
            double d = g(kTPModDep, 64) / 127.0;
            double mid = 1.0 - 0.5 * d;
            r[0] *= mid;
            r[55] = 1.0;
            r[56] = rate2(g(kTPModRT, 60));
            r[57] = 0.5 * d / mid;
            r[58] = g(kTPSel, 0) ? 1.0 : 0.0;
            r[59] = std::min(4, g(kTPModWV, 2));
        }
        if (has(kWahMan) && g(kWahSw, 1)) {
            // GTR MULTI 3's WAH (efxfilter): its pedal held where Wah Man
            // puts it, a band or low pass by Wah Fil, Peak its Q (WAH_HZ, WAH_Q)
            r[50] = 1.0;
            r[51] = g(kWahFil, 1) == 0 ? 2.0 : 3.0;
            r[52] = 0.7 * pow(12.0 / 0.7, clamp(g(kWahPeak, 10)) / 127.0);
            r[53] = 1.0;
            r[54] = 200.0 * pow(4000.0 / 200.0, clamp(g(kWahMan, 60)) / 127.0);
        }
        if (has(kDlyTime)) {
            // THE MULTI's OWN DELAY, as the GS delay's repeats: one tap, 0-635
            // ms (5 ms a step), its feedback 0-127, its mix
            int t = g(kDlyTime, 60), f = g(kDlyFb, 32), x = g(kDlyMix, 0);
            if (x) {
                r[34] = 1.0;
                r[35] = x / 127.0;
                r[36] = f / 128.0;
                r[37] = 0.0;
                r[38] = t * 0.005;
                r[39] = 1.0;
                const double t1[5] = {t * 0.005, 1.0, 2.0, t * 0.005, 1.0};
                std::copy(t1, t1 + 5, r + 40);
            }
        }
        if (has(kRMMod)) {
            // THE KEYBOARD MULTI's RING MODULATOR, PITCH SHIFTER AND DELAY
            // in series (_keyboard_multi), its taps unrolled by prepare
            // (gsd_expand): the modulator's Hz (RM_HZ: 10-5000 on a log
            // line), each stage's dry and effect by its Balance, the
            // shift's ratio, the delay's (its own, above: 1 its level,
            // feedback and time), the part at its all-dry path's level
            double rdw[2], pdw[2];
            balance(g(kRMBal, 15), rdw);
            balance(g(kPSBal, 30), pdw);
            const double base = std::max(rdw[0] * pdw[0], 1e-3);        // (DRY_FLOOR)
            r[160] = r[34];
            r[161] = 10.0 * pow(5000.0 / 10.0, clamp(g(kRMMod, 50)) / 127.0);
            r[162] = rdw[0];
            r[163] = rdw[1];
            r[164] = pdw[0];
            r[165] = pdw[1];
            r[166] = pow(2.0, (g(kPSCoarse, 71) - 0x40) / 12.0 + (g(kPSFine, 64) - 0x40) * 2.0 / 1200.0);
            r[167] = base;
            r[34] = 3.0;
            r[0] *= base;
        }
    }
    if (choice)
        return refuse("controller on a choice");
    r[12] = snd[0];
    r[13] = snd[2];
    memcpy(rec, r, sizeof r);
    if (!par_b.empty()) {                   // (branch B's record: nvrender puts it just before A's)
        par_b[12] = snd[0];
        par_b[13] = snd[2];
        std::copy(par_b.begin(), par_b.end(), recb);
        *has_b = 1;
    }
    return 0;
}

// A GS EXCLUSIVE AS THE INSERTION EFFECT's EVENT (gsefx.parse; the
// reader's): d the bytes after F0 (41 dev 42 12 addr... data sum). Its
// kind (1 type, 2 parameter, 3 send, 4 controller, 5 a part's assign) and
// values in *k, *a, *b -- the part's channel 0-15, port B's +16; 0 where
// it is not one.
extern "C" int nv_efx_parse(const unsigned char *d, int n, int *k, int *a, int *b)
{
    if (n < 8 || d[0] != 0x41 || d[2] != 0x42 || d[3] != 0x12)
        return 0;
    if (d[4] == 0x40 && d[5] == 0x03) {
        const int ad = d[6];
        if (ad == 0x00 && n >= 9)
            *k = 1, *a = d[7], *b = d[8];
        else if (ad >= 0x03 && ad <= 0x16)
            *k = 2, *a = ad - 0x02, *b = d[7];
        else if (ad >= 0x17 && ad <= 0x19)
            *k = 3, *a = ad, *b = d[7];
        else if (ad >= 0x1B && ad <= 0x1E)
            *k = 4, *a = ad, *b = d[7];
        else
            return 0;
        return 1;
    }
    if ((d[4] == 0x40 || d[4] == 0x50) && (d[5] >> 4) == 4 && d[6] == 0x22) {
        const int blk = d[5] & 0x0F;
        *k = 5;
        *a = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0);
        *b = d[7] != 0;
        return 1;
    }
    return 0;
}

// THE CHAIN's EQ at frequency f (gsefx.eq_gain; nvrender's EQ pass): its
// record's shelves (r[7], r[11]) at their corners (r[60], r[61]: 400 Hz and
// 4 kHz where unset), its mid (r[8]-r[10]) and a type's more (r[62] of
// them from r[63], three each), linear
extern "C" double nv_efx_eq_gain(const double *fc, double f)
{
    const double lo_hz = fc[60] != 0.0 ? fc[60] : 400.0, hi_hz = fc[61] != 0.0 ? fc[61] : 4000.0;
    double x = f / lo_hz, y = f / hi_hz;
    x = x * x;
    y = y * y;
    double db = fc[7] / (1.0 + x) + fc[11] * y / (1.0 + y);
    const int nm = 1 + (int)fc[62];
    for (int j = 0; j < nm; j++) {
        const double *m = j == 0 ? fc + 8 : fc + 63 + 3 * (j - 1);
        const double mf = m[0], q = m[1], mg = m[2];
        if (mf != 0.0 && mg != 0.0) {
            double u = q * (f / mf - mf / (f + 1e-6 * (f <= 0.0 ? 1.0 : 0.0)));
            db += mg / (1.0 + u * u);
        }
    }
    return pow(10.0, db / 20.0);
}

// THE MODULE's INSERTION EFFECT, LIVE (live.Live.efx, efx_parts): its
// setting as gsefx.apply keeps it -- a reset Thru with every part off, a
// type its parameters unset -- the parts on it, and its chain, built again
// when the setting changes (efx_rev)
namespace {
struct EfxLive {
    const double *X;
    double SR;
    int msb = 0, lsb = 0, p[21], snd[3] = {40, 0, 0}, ctl[4] = {0, 0x40, 0, 0x40};
    std::map<int, int> cvv;
    std::vector<int> parts;                 // (channels on it)
    long rev = 0, built_rev = -1;
    int status = -1;                        // (the chain's: 0 built, -1 none, -3 refused)
    const char *why = "";
    double rec[NV_FXN], recb[NV_FXN];
    int has_b = 0;
    EfxLive(const double *X_, double SR_) : X(X_), SR(SR_)
    {
        for (int q = 0; q < 21; q++)
            p[q] = -1;
    }
    void apply(int k, int a, int b)
    {
        if (k == 0) {
            msb = lsb = 0;
            for (int q = 0; q < 21; q++)
                p[q] = -1;
            snd[0] = 40; snd[1] = 0; snd[2] = 0;
            ctl[0] = 0; ctl[1] = 0x40; ctl[2] = 0; ctl[3] = 0x40;
            cvv.clear();
            parts.clear();
        } else if (k == 1) {
            msb = a;
            lsb = b;
            for (int q = 0; q < 21; q++)
                p[q] = -1;
        } else if (k == 2 && a >= 1 && a <= 20) {
            p[a] = b;
        } else if (k == 3) {
            snd[a - 0x17] = b;
        } else if (k == 4) {
            ctl[a - 0x1B] = b;
        } else if (k == 6) {
            cvv[a] = b;
        } else if (k == 5) {
            auto it = std::find(parts.begin(), parts.end(), a);
            if (b && it == parts.end())
                parts.push_back(a);
            else if (!b && it != parts.end())
                parts.erase(it);
        }
        rev++;
    }
    bool on(int ch) const { return std::find(parts.begin(), parts.end(), ch) != parts.end(); }
    // THE TIMELINE (live.efx_events, _efx_event): each setting as it came,
    // past 64 compacted to a snapshot of what stood two seconds before the
    // newest (its type, parameters, sends, controllers, sources, the parts
    // on it) and what came after -- what a part's moving filter reads
    struct Ev {
        double t;
        int k, a, b;
    };
    std::vector<Ev> evs;
    void event(double t, int k, int a, int b)
    {
        apply(k, a, b);
        evs.push_back(Ev{t, k, a, b});
        if (evs.size() <= 64)
            return;
        const double cut = t - 2.0;
        EfxLive R(X, SR);
        std::vector<Ev> snap;
        for (const Ev &e : evs)
            if (e.t <= cut)
                R.apply(e.k, e.a, e.b);
        snap.push_back(Ev{cut, 1, R.msb, R.lsb});
        for (int q = 1; q <= 20; q++)
            if (R.p[q] >= 0)
                snap.push_back(Ev{cut, 2, q, R.p[q]});
        for (int q = 0; q < 3; q++)
            snap.push_back(Ev{cut, 3, 0x17 + q, R.snd[q]});
        for (int q = 0; q < 4; q++)
            snap.push_back(Ev{cut, 4, 0x1B + q, R.ctl[q]});
        for (const auto &kv : R.cvv)
            snap.push_back(Ev{cut, 6, kv.first, kv.second});
        std::vector<int> ps = R.parts;
        std::sort(ps.begin(), ps.end());
        for (int c : ps)
            snap.push_back(Ev{cut, 5, c, 1});
        for (const Ev &e : evs)
            if (e.t > cut)
                snap.push_back(e);
        evs.swap(snap);
    }
    // gsefx.at(events, ch, t): the chain part ch hears at t into rec (0),
    // where it is on the effect then and its type built (-1 not, -3 refused)
    int chain_at(double t, int ch, double *out)
    {
        EfxLive R(X, SR);
        for (const Ev &e : evs) {
            if (e.t > t + 1e-9)
                break;
            R.apply(e.k, e.a, e.b);
        }
        if (!R.on(ch))
            return -1;
        const double *r = R.chain();
        if (!r)
            return R.status;
        memcpy(out, r, sizeof(double) * NV_FXN);
        return 0;
    }
    const double *chain()
    {
        if (built_rev != rev) {
            built_rev = rev;
            std::vector<int> cs, cv_;
            for (const auto &kv : cvv) {
                cs.push_back(kv.first);
                cv_.push_back(kv.second);
            }
            status = nv_efx_chain(X, SR, msb, lsb, p, snd, ctl, (int)cs.size(), cs.data(), cv_.data(), rec, recb,
                                  &has_b, &why);
        }
        return status == 0 ? rec : nullptr;
    }
};
}  // namespace

extern "C" void *nv_efx_live_new(const double *X, double SR) { return new EfxLive(X, SR); }
extern "C" void nv_efx_live_free(void *h) { delete (EfxLive *)h; }
extern "C" void nv_efx_live_apply(void *h, double t, int k, int a, int b) { ((EfxLive *)h)->event(t, k, a, b); }
extern "C" int nv_efx_live_parts(void *h) { return (int)((EfxLive *)h)->parts.size(); }

// gsefx.filter_setup's settings for part ch over the timeline: each time
// (0 and the events') whose chain has a moving filter of the first's family
// (vowels or not) -- its time, pedal Hz and control (kind, c1-c5), 8 each
// into seg; the first's type and parameters (ty, pa, pb, pc) into head.
// Their count, 0 none
extern "C" int nv_efx_live_filter(void *h, int ch, double *head, double *seg, int cap)
{
    EfxLive *E = (EfxLive *)h;
    std::vector<double> ts{0.0};
    for (const auto &e : E->evs)
        ts.push_back(e.t);
    std::sort(ts.begin(), ts.end());
    ts.erase(std::unique(ts.begin(), ts.end()), ts.end());
    std::vector<double> sc(NV_FXN);
    int n = 0;
    for (double t : ts) {
        if (E->chain_at(t, ch, sc.data()) != 0 || sc[50] == 0.0)
            continue;
        if (n && (sc[128] == 3.0) != (seg[2] == 3.0))
            continue;                   // (not the first's family: filter_setup drops it)
        if (!n) {
            head[0] = sc[51]; head[1] = sc[52]; head[2] = sc[53]; head[3] = sc[134];
        }
        if (n >= cap)
            break;
        double *s = seg + 8 * n++;
        s[0] = t;
        s[1] = sc[54];
        for (int q = 0; q < 6; q++)
            s[2 + q] = sc[128 + q];
    }
    return n;
}
extern "C" int nv_efx_live_on(void *h, int ch) { return ((EfxLive *)h)->on(ch); }
extern "C" long nv_efx_live_rev(void *h) { return ((EfxLive *)h)->rev; }

// the chain channel ch hears now (live._efx_for): its record, NULL where
// ch is not on the effect or its type is Thru, unbuilt or refused here
// (*status: 0, -1, -3; *why the refusal's)
extern "C" const double *nv_efx_live_chain(void *h, int ch, int *status, const char **why)
{
    EfxLive *E = (EfxLive *)h;
    if (!E->on(ch)) {
        *status = -1;
        return nullptr;
    }
    const double *r = E->chain();
    *status = E->status;
    *why = E->why;
    return r;
}

// ...its controllers' sources (gsefx: CC1-95, aftertouch, bend): the value
// of one, as a file's joins the timeline (live._efx_control) -- where it is
// one of the two and has moved
extern "C" void nv_efx_live_source(void *h, double t, int src, int v)
{
    EfxLive *E = (EfxLive *)h;
    if (src != E->ctl[0] && src != E->ctl[2])
        return;
    auto it = E->cvv.find(src);
    if (it != E->cvv.end() && it->second == v)
        return;
    E->event(t, 6, src, v);
}
