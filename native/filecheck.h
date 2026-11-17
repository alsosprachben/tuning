// THE FILE CHECK: mt32check.py's audit of an MT-32-era file before it is
// played as GM, line for line (its findings word for word, so the two can be
// compared on the same files: examples/filecheck_check.py). A file written
// for an MT-32 looks like General MIDI and is not, and the ways it differs
// all present as VOICE problems -- too loud, too quiet, the wrong timbre --
// which invite a fix in the voice that is really a fix to the file. This
// reports the file's causes first (mt32check.py's docstring has the cases
// and the files that taught them).
//
// Included by midi.cpp (namespace nv, after Msg): check_file() reads each
// track's messages as read_track left them -- absolute ticks, the file's own
// channels -- as mido gives mt32check its tracks.
#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <vector>

namespace filecheck {

static const char *const GM_NAMES[128] = {
    "AcGrPiano", "BrAcPiano", "ElGrPiano", "HonkyTonk", "ElPiano1", "ElPiano2",
    "Harpsi", "Clav", "Celesta", "Glocken", "MusicBox", "Vibra", "Marimba",
    "Xylo", "TubeBell", "Dulcimer", "DrawOrgan", "PercOrgan", "RockOrgan",
    "ChurchOrg", "ReedOrgan", "Acordion", "Harmonica", "TangoAcd", "NylonGtr",
    "SteelGtr", "JazzGtr", "CleanGtr", "MutedGtr", "OverdrvGtr", "DistGtr",
    "GtrHarm", "AcBass", "FngrBass", "PickBass", "FretlessB", "SlapBass1",
    "SlapBass2", "SynBass1", "SynBass2", "Violin", "Viola", "Cello",
    "Contrabas", "TremStr", "PizzStr", "Harp", "Timpani", "StrEns1", "StrEns2",
    "SynStr1", "SynStr2", "ChoirAah", "VoiceOoh", "SynVoice", "OrchHit",
    "Trumpet", "Trombone", "Tuba", "MutedTrp", "FrHorn", "BrasSect",
    "SynBrass1", "SynBrass2", "SopSax", "AltoSax", "TenorSax", "BariSax",
    "Oboe", "EngHorn", "Bassoon", "Clarinet", "Piccolo", "Flute", "Recorder",
    "PanFlute", "Blownbtl", "Shakuhach", "Whistle", "Ocarina", "Lead1Square",
    "Lead2Sawth", "Lead3Calio", "Lead4Chiff", "Lead5Charg", "Lead6Voice",
    "Lead7Fifth", "Lead8Bass", "Pad1NewAge", "Pad2Warm", "Pad3Poly",
    "Pad4Choir", "Pad5Bowed", "Pad6Metal", "Pad7Halo", "Pad8Sweep",
    "FX1Rain", "FX2Sndtrk", "FX3Crystal", "FX4Atmosp", "FX5Bright",
    "FX6Goblins", "FX7Echoes", "FX8SciFi", "Sitar", "Banjo", "Shamisen",
    "Koto", "Kalimba", "Bagpipe", "Fiddle", "Shanai", "TinkleBell",
    "Agogo", "SteelDrums", "Woodblock", "TaikoDrum", "MelodicTom",
    "SynthDrum", "RevCymbal", "GtrFretNz", "BreathNoise", "Seashore",
    "BirdTweet", "TelephRing", "Helicopter", "Applause", "Gunshot",
};

// The GM programs whose voice reads CC11 as drawn stops (patch_map's
// PROGRAM_CLASS[p].registerable: the harpsichord, the organs, the orchestra
// hit's registered layers) -- examples/filecheck_check.py asserts it current
static bool registerable(int p)
{
    return p == 6 || (p >= 16 && p <= 20) || p == 55;
}

// Playable compass per program, MIDI notes: generous, to catch a part on
// the wrong program, not to police a composer at the extremes
static bool range_of(int p, int &lo, int &hi)
{
    static const int R[][3] = {
        {40, 55, 103}, {41, 48, 93}, {42, 36, 81}, {43, 28, 67}, {46, 24, 104}, {47, 40, 55},
        {51, 48, 84}, {52, 48, 84}, {53, 48, 84}, {56, 54, 87}, {57, 40, 77}, {58, 28, 65},
        {59, 54, 87}, {60, 34, 77}, {68, 58, 92}, {69, 52, 84}, {70, 34, 75}, {71, 50, 91},
        {72, 74, 108}, {73, 60, 96},
    };
    for (const auto &r : R)
        if (r[0] == p) {
            lo = r[1];
            hi = r[2];
            return true;
        }
    return false;
}

static const int GATE = 12;     // notes below this per window are too few to characterise

static std::string fmt(const char *f, ...) __attribute__((format(printf, 1, 2)));
static std::string fmt(const char *f, ...)
{
    char b[4096];
    va_list ap;
    va_start(ap, f);
    vsnprintf(b, sizeof b, f, ap);
    va_end(ap);
    return b;
}

static std::string lower(std::string s)
{
    for (char &c : s)
        c = (char)tolower((unsigned char)c);
    return s;
}

static std::string join(const std::vector<std::string> &v, const char *sep)
{
    std::string o;
    for (size_t i = 0; i < v.size(); i++)
        o += (i ? sep : "") + v[i];
    return o;
}

static double median(std::vector<double> v)
{
    std::sort(v.begin(), v.end());
    const size_t n = v.size();
    return n % 2 ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2.0;
}

struct Result {
    std::vector<std::string> findings;
    bool muxed = false;         // every note stamped with its own program (_multiplexed)
    bool master = false;        // a 'Master Parameters' track: an MT-32 file
};

// tracks: each track's messages (absolute ticks, read_track's)
template <class MsgT>
static Result check(const std::vector<std::vector<const MsgT *>> &tracks, int tpb)
{
    Result R;
    // _seconds_fn: tick -> seconds through every tempo change (mido's tick2second)
    std::vector<std::pair<long long, long long>> tempos;
    for (const auto &tr : tracks)
        for (const MsgT *m : tr)
            if (m->status == 0xFF && m->meta == 0x51 && m->data.size() >= 3)
                tempos.push_back({m->tick, ((long long)m->data[0] << 16) | (m->data[1] << 8) | m->data[2]});
    std::sort(tempos.begin(), tempos.end());
    if (tempos.empty() || tempos[0].first > 0)
        tempos.insert(tempos.begin(), {0, 500000});
    auto t2s = [&](long long tick, long long tempo) { return (double)tick * ((double)tempo * 1e-6 / tpb); };
    auto sec = [&](long long tick) {
        double total = 0.0;
        long long prev = 0, cur = tempos[0].second;
        for (const auto &tp : tempos) {
            if (tp.first >= tick)
                break;
            total += t2s(tp.first - prev, cur);
            prev = tp.first;
            cur = tp.second;
        }
        return total + t2s(tick - prev, cur);
    };

    // _gather
    std::map<int, std::vector<std::tuple<double, double, int>>> notes;     // (onset, duration, note)
    std::map<int, std::vector<std::tuple<double, int, std::string>>> programs;
    std::map<int, std::vector<std::pair<double, int>>> volumes, expression;
    std::map<int, std::set<std::string>> names;
    std::map<int, std::set<size_t>> ctrl_tracks;
    std::vector<std::string> track_names;
    for (size_t ti = 0; ti < tracks.size(); ti++) {
        std::string label;
        std::map<std::pair<int, int>, std::vector<long long>> held;
        for (const MsgT *m : tracks[ti]) {
            const long long now = m->tick;
            if (m->status == 0xFF) {
                if (m->meta == 0x03) {
                    std::string nm(m->data.begin(), m->data.end());
                    // (mido's name.strip())
                    const size_t a = nm.find_first_not_of(" \t\r\n\v\f"), b = nm.find_last_not_of(" \t\r\n\v\f");
                    label = a == std::string::npos ? "" : nm.substr(a, b - a + 1);
                    track_names.push_back(label);
                }
                continue;
            }
            if (m->status == 0xF0)
                continue;
            const int kind = m->status & 0xF0, ch = m->status & 0x0F;
            if (kind == 0xC0) {
                programs[ch].push_back({sec(now), m->d0, label});
            } else if (kind == 0xB0) {
                ctrl_tracks[ch].insert(ti);
                if (m->d0 == 7)
                    volumes[ch].push_back({sec(now), m->d1});
                else if (m->d0 == 11)
                    expression[ch].push_back({sec(now), m->d1});
            } else if (kind == 0x90 && m->d1) {
                held[{ch, m->d0}].push_back(now);
                if (!label.empty())
                    names[ch].insert(label);
            } else if (kind == 0x80 || kind == 0x90) {
                auto it = held.find({ch, m->d0});
                if (it != held.end() && !it->second.empty()) {
                    const long long on = it->second.front();
                    it->second.erase(it->second.begin());
                    notes[ch].push_back({sec(on), sec(now) - sec(on), m->d0});
                }
            }
        }
    }
    // _multiplexed: a program change a tick or two before at least 90% of notes
    {
        long long stamped = 0, n = 0;
        for (const auto &tr : tracks) {
            std::map<int, long long> pending;
            for (const MsgT *m : tr) {
                if (m->status >= 0xF0)
                    continue;
                const int kind = m->status & 0xF0, ch = m->status & 0x0F;
                if (kind == 0xC0) {
                    pending[ch] = m->tick;
                } else if (kind == 0x90 && m->d1) {
                    n++;
                    auto it = pending.find(ch);
                    if (m->tick - (it == pending.end() ? -999 : it->second) <= 4)
                        stamped++;
                }
            }
        }
        R.muxed = n > 0 && stamped >= 0.9 * n;
    }
    for (const auto &nm : track_names)
        R.master = R.master || lower(nm).rfind("master parameters", 0) == 0;

    auto &F = R.findings;
    const bool muxed = R.muxed;
    const double window = 60.0;
    std::set<int> chans;
    for (const auto &kv : notes)
        chans.insert(kv.first);
    for (const auto &kv : programs)
        chans.insert(kv.first);
    for (const int ch : chans) {
        const auto &pr = programs[ch];
        const auto &nt = notes[ch];
        const bool chosen = !pr.empty();
        const int cp = chosen ? std::get<1>(pr.back()) : -1;
        std::vector<std::string> parts(names[ch].begin(), names[ch].end());

        // -- programs that never take effect
        std::vector<std::tuple<double, int, std::string>> at_zero;
        for (const auto &p : pr)
            if (std::get<0>(p) <= 0.0)
                at_zero.push_back(p);
        if (at_zero.size() > 1 && !muxed) {
            std::vector<std::string> sh;
            for (size_t i = 0; i + 1 < at_zero.size(); i++) {
                const int p = std::get<1>(at_zero[i]);
                const std::string &t = std::get<2>(at_zero[i]);
                sh.push_back(fmt("%d %s%s", p, p < 128 ? GM_NAMES[p] : "?", t.empty() ? "" : (" [" + t + "]").c_str()));
            }
            F.push_back(fmt("ch%d: %d program changes at tick 0; only the last takes effect. Shadowed: %s",
                            ch, (int)at_zero.size(), join(sh, ", ").c_str()));
        }

        // -- one channel, two instruments
        if (!nt.empty() && !muxed) {
            std::vector<std::tuple<double, std::string, int, double>> seen;
            double span = std::get<0>(nt[0]);
            for (const auto &x : nt)
                span = std::max(span, std::get<0>(x));
            double start = 0.0;
            while (start < span) {
                std::vector<double> durs;
                int lo = 999, hi = -1;
                for (const auto &x : nt)
                    if (start <= std::get<0>(x) && std::get<0>(x) < start + window) {
                        durs.push_back(std::get<1>(x));
                        lo = std::min(lo, std::get<2>(x));
                        hi = std::max(hi, std::get<2>(x));
                    }
                if ((int)durs.size() >= GATE) {
                    const double med = median(durs);
                    const int spread = hi - lo;
                    const char *kind = med <= 0.15 && spread >= 18 ? "figuration"
                                     : med >= 1.0 && spread <= 8  ? "sustained" : nullptr;
                    if (kind)
                        seen.push_back({start, kind, (int)durs.size(), med});
                }
                start += window;
            }
            std::set<std::string> kinds;
            for (const auto &s : seen)
                kinds.insert(std::get<1>(s));
            if (kinds.size() > 1) {
                std::vector<std::string> det;
                for (const auto &s : seen)
                    det.push_back(fmt("%.0f-%.0fs %s (%d notes, median %.3fs)", std::get<0>(s), std::get<0>(s) + window,
                                      std::get<1>(s).c_str(), std::get<2>(s), std::get<3>(s)));
                F.push_back(fmt("ch%d carries both figuration and sustained writing -- one program cannot be right "
                                "for both: %s", ch, join(det, "; ").c_str()));
            }
        }

        // -- pitched material on the drum channel
        if (ch == 9 && !nt.empty()) {
            std::set<int> ps;
            for (const auto &x : nt)
                ps.insert(std::get<2>(x));
            const int lo = *ps.begin(), hi = *ps.rbegin();
            if (ps.size() >= 5 && hi - lo <= 24)
                F.push_back(fmt("ch9 (GM percussion) holds %d notes across %d pitches spanning %d semitones -- looks "
                                "like a pitched part. Tracks: %s", (int)nt.size(), (int)ps.size(), hi - lo,
                                parts.empty() ? "(unnamed)" : join(parts, ", ").c_str()));
            std::vector<std::string> strangers;
            for (const auto &n : parts) {
                const std::string l = lower(n);
                bool kit = false;
                for (const char *w : {"perc", "drum", "kit", "cymb", "snare", "tom", "hat", "rhythm", "batt"})
                    kit = kit || l.find(w) != std::string::npos;
                if (!kit)
                    strangers.push_back("'" + n + "'");
            }
            if (!strangers.empty())
                F.push_back(fmt("ch9 (GM percussion) carries named instrument part%s %s -- GM will read their pitches "
                                "as kit sounds. Check the score before deleting them as stray drums.",
                                strangers.size() == 1 ? "" : "s", join(strangers, ", ").c_str()));
        }

        // -- controller fights
        if (ctrl_tracks[ch].size() > 1 && names[ch].size() > 1 && !muxed)
            F.push_back(fmt("ch%d: %d tracks write controllers to it (last write wins), and it carries %d named parts "
                            "-- their dynamics will be wrong for one of them: %s", ch, (int)ctrl_tracks[ch].size(),
                            (int)names[ch].size(), join(parts, ", ").c_str()));

        // -- volumes that mean silence, only where a note sounds under them
        std::vector<double> onsets;
        for (const auto &x : nt)
            onsets.push_back(std::get<0>(x));
        std::sort(onsets.begin(), onsets.end());
        auto vols = volumes[ch];
        std::sort(vols.begin(), vols.end());
        for (size_t i = 0; i < vols.size(); i++) {
            const double when = vols[i].first;
            const int value = vols[i].second;
            if (value > 16)
                continue;
            const double until = i + 1 < vols.size() ? vols[i + 1].first : INFINITY;
            bool under = false;
            for (const double o : onsets)
                under = under || (when <= o && o < until);
            if (!under)
                continue;
            F.push_back(fmt("ch%d: CC7=%d from %.1fs is %s in GM, and notes sound under it", ch, value, when,
                            value ? fmt("%.0f dB", 40 * std::log10(value / 127.0)).c_str() : "silence"));
        }

        // -- CC11 swept on a registered voice (a stop bitfield, not expression)
        if (chosen && !expression[ch].empty() && !nt.empty()) {
            std::set<int> vals;
            for (const auto &e : expression[ch])
                vals.insert(e.second);
            if (registerable(cp) && vals.size() > 6) {
                std::vector<std::string> first;
                for (int v : vals) {
                    if (first.size() == 5)
                        break;
                    first.push_back(std::to_string(v));
                }
                F.push_back(fmt("ch%d: %d CC11 events with %d distinct values (%s...) -- this voice reads CC11 as a "
                                "STOP BITFIELD, so these draw ranks rather than set a level", ch,
                                (int)expression[ch].size(), (int)vals.size(), join(first, ", ").c_str()));
            }
        }

        // -- notes the assigned instrument cannot play
        int lo, hi;
        if (chosen && !nt.empty() && range_of(cp, lo, hi) && !muxed) {
            int out = 0, wlo = 999, whi = -1;
            for (const auto &x : nt) {
                const int n = std::get<2>(x);
                out += n < lo || n > hi;
                wlo = std::min(wlo, n);
                whi = std::max(whi, n);
            }
            if (out > std::max(4.0, 0.02 * (double)nt.size())) {
                std::vector<std::string> fits;
                for (size_t i = 0; i + 1 < at_zero.size(); i++) {
                    const int p = std::get<1>(at_zero[i]);
                    int plo, phi;
                    if (range_of(p, plo, phi) && plo <= wlo && phi >= whi)
                        fits.push_back(fmt("%d %s", p, GM_NAMES[p]));
                }
                std::string hint;
                if (!fits.empty())
                    hint = "  The file's own shadowed program " + join(fits, " / ") + " covers it -- try that first.";
                else if (names[ch].empty())
                    hint = "  No track on this channel is named, so a name-driven remap had nothing to go on.";
                F.push_back(fmt("ch%d: %d of %d notes lie outside %s (%d-%d); written range is %d-%d -- wrong program?%s",
                                ch, out, (int)nt.size(), GM_NAMES[cp], lo, hi, wlo, whi, hint.c_str()));
            }
        }
    }
    return R;
}

}  // namespace filecheck
