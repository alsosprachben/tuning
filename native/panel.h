// panel.h -- nvlive's panel: live's (livetui.py) for the one native piano.
//
// What live's panel has that a native piano has too, laid out and keyed as
// live's: the header (the stream, the MIDI port, the real-time lamp), the
// part, the GLOBALS (master, headroom, limiter, bend range, mod depth,
// aftertouch, the GPU, the room's tail), the CONTROLS & ROUTES (live.Route:
// r adds one through live's own questions -- from, to, how a key holds,
// replace or keep, which channel -- d deletes, a key learnt by pressing it)
// and the OUTPUT at the bottom (the stereo meter with its fall and hold, the
// block's time against its budget, underruns, partials shed and sounding,
// the pedals). Tab moves between the panes, the arrows (or hjkl) select and
// adjust, - and + (_ and + by five) adjust, P is panic, ? the keys, q quits.
//
// The patch picker (p) lists every program, its variations and the drum
// sets; x is the insertion effect (livetui.pick_efx): the part on it or off,
// its type by Roland's families, each parameter as his panel prints it, the
// two controllers and the sends -- each sent as the GS message a file would
// carry.
//
// Not live's: the patch tree, layers and splits, a tone's own effect shown,
// the synth, presets and scenes (one part, its program picked here or by MIDI),
// and the room itself (the voices are packed in the export's room; its tail
// can be turned off).
//
// No curses: ANSI escapes on a raw terminal, so it runs wherever nvlive does.
// The panel runs on its own thread; what it changes it POSTS (Host::post),
// done by the audio thread between two blocks, as live's panel posts.

#ifndef NV_PANEL_H
#define NV_PANEL_H

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <termios.h>
#include <thread>
#include <unistd.h>
#include <vector>

extern "C" const char *nv_raga_system_name(int i);                  // (tuner.cpp: the Eastern tuning's choices)
extern "C" const char *nv_raga_name(int i, int *n, const int **idx);

namespace panel {

// what the audio thread hands the panel after each block
struct Snap {
    long long n0 = 0;
    long blocks = 0, over = 0, underruns = 0;
    double ms_max = 0.0, ms_sum = 0.0;  // since the panel last looked
    long ms_n = 0;
    float peak[2] = {0.0f, 0.0f};       // since the panel last looked
    double eng[15] = {};                // nv_part_stats
    // the insertion effect when it last changed (nv_part_efx_state: empty
    // none in the export), its revision and why its chain is refused
    std::vector<int> efx;
    std::string efx_why;
    long efx_rev = -1;
    bool rt = false, rt_dropped = false;
};

// AN ON-SCREEN CONTROL (live's screen_controls): its control (CONTROLS' key:
// a CC, -1 the pitch wheel, -2 aftertouch, -3 mono), its channel (-1 every
// one), its value, its hotkey (0 none)
struct ScreenControl {
    int key = 0, channel = -1, value = 0, hotkey = 0;
};

// A PART as the PARTS pane shows it (livetui's row): its program, variation
// or drum set, its channel (-1 every one), keys, transpose, level, mute, its
// name; index its place in the host's list
struct PartRow {
    int index = 0, program = 0, var = 0;
    bool drums = false;
    int channel = -1, lo = 0, hi = 127, tr = 0;
    double level = 0.0;
    bool muted = false;
    bool touch_fixed = true;            // (live.Part.touch_fixed: its switch, else the patch's way)
    std::string name;
};

struct Host {
    std::function<Snap()> take;                                    // the latest, peaks and times reset
    // the build under way (done, total, what): false none -- a pick's bar
    std::function<bool(long &, long &, std::string &)> progress;
    std::function<std::pair<int, int>()> learnt;                  // a key pressed since learning was armed
    std::function<void(bool)> learn;                               // arm (or cancel) learning a key
    double rate = 48000.0, budget_ms = 2.67;
    long slots = 65536;                                            // the slab's (voices used of these)
    int frames = 128, program = 0, reg_modes = 0;
    std::string port, room, program_name, tuner;
    // the globals: master dB, headroom dB, limiter, bend range, mod depth,
    // aftertouch dB, the GPU (1 on), the room's tail (1 on)
    double g[14];
    // ...and THE ROOM (live's global 'room': live.ROOM_NAMES the export
    // carries, g[8] the index of the one now; a step asks the builder for it)
    std::vector<std::string> rooms;
    bool has_gpu = false, has_room = false;
    std::function<void(int, double)> set_global;                  // posted by the panel itself
    std::vector<std::array<int, 7>> routes;                        // the panel's copy (nv_rt_add's seven)
    std::function<void(const std::array<int, 7> &)> add_route;
    std::function<void(int)> del_route;
    std::function<void()> panic;                                   // every note off, now
    // AN ORGAN'S STOPS (live's panel: Patch.stop_rows): its ranks' names, the
    // rows as the panel lays them out (rank indices), which are drawn now,
    // and a stop drawn or put in (posted)
    std::vector<std::string> stop_names;
    std::vector<std::vector<int>> stop_rows;
    std::vector<std::vector<int>> stop_breaks;                     // each row's line breaks (the voice's groups)
    std::function<std::vector<char>()> drawn;
    std::function<void(int)> toggle_stop;
    // before each frame: the host brings what it changed itself up to date
    // (a program change from the keyboard: the program, its name, its stops)
    // and says what it has to say ("" nothing)
    std::function<std::string()> refresh;
    // THE PATCH PICKER: each program's name (0-127) and each drum set's (128 +
    // set; "" none), which are native here, whether the part is a drum set
    // now, and a program or set asked for (posted)
    std::vector<std::string> names;
    std::vector<char> native;
    bool kit = false;
    // ...and the variations under the programs (256 + j: program, key, name,
    // native), the part's own now (0 the capital tone)
    std::vector<std::array<int, 2>> vpv;
    std::vector<std::string> vnames;
    std::vector<char> vnative;
    int var = 0;
    std::function<void(int)> pick;
    std::function<void(const std::string &)> set_tuner;          // a tuner asked for (built, then swapped in)
    // THE EASTERN TUNING (livetui's E): the rig's spec ("" off), one asked
    // for (built, then swapped in), and whether a part's voice plays it now
    std::string eastern;
    std::function<void(const std::string &)> set_eastern;
    std::function<bool(int, bool)> east_part;
    // THE PARTS (livetui's PARTS pane): the rows, a part's columns set, one
    // layered, split, taken away (false: why), a program asked for a part
    std::function<std::vector<PartRow>()> parts;
    std::function<void(int, int, int, int, int, double, bool)> part_set;     // index, ch, lo, hi, tr, level, muted
    std::function<bool(int)> part_layer;
    std::function<bool(int, std::string &)> part_split, part_delete;
    std::function<void(int, int)> pick_part;                                 // index, sp
    std::function<void(int, bool)> part_touch;                               // index, fixed (livetui.toggle_touch)
    std::function<bool()> messenger_reads;                                   // (every part reads a Messenger's chart)
    std::function<void(bool)> messenger_read;
    // PRESETS AND SCENES (live's presets.json and scenes.json): saved under a
    // name, the names, one loaded or recalled -- each says what it did
    std::function<std::string(const std::string &)> save_preset, load_preset, save_scene, recall_scene;
    std::function<std::vector<std::string>()> preset_names, scene_names;
    // THE SYNTH (livetui's synth pane): a part's knobs on a layer (its layers,
    // 0 not a Moog), one turned, one put back to the patch's, the whole sent
    // to a Messenger (0: none to set); the Messenger's line; its firmware's
    // chart flipped (the new one's name)
    std::function<int(int, int, double *, char *)> synth_get;
    std::function<void(int, int, int, double)> synth_set;
    // AN ORGAN's DRIVE KNOB (livetui.organ_part, live.set_drive): read (out:
    // in use, the voice's, the knob's; 1 a tonewheel organ's), set (<0 the voice's)
    std::function<int(int, double *)> drive_get;
    std::function<void(int, double)> drive_set;
    // THE MIDI INPUTS (livetui.pick_inputs): each plugged in (its name, open
    // or not), one turned on or off (what to say), those open as the header names them
    std::function<std::vector<std::pair<std::string, bool>>()> inputs;
    std::function<std::string(int)> input_toggle;
    std::function<std::string()> port_label;
    std::function<void(int, int, int)> synth_forget;
    std::function<int(int)> synth_send;
    std::function<std::string()> messenger_line, messenger_firmware;
    // THE SOUND CANVAS'S DISPLAY (gsdisplay): its lines now -- the text's
    // 16-column window, then the page in half blocks -- or none
    std::function<std::vector<std::string>()> display;
    // THE ON-SCREEN CONTROLS (livetui's, the controls pane): the list (the
    // host's, saved with the session), one sent, a switch's state as the
    // engine has it on a channel
    std::vector<ScreenControl> *controls = nullptr;
    std::function<void(int, int, int)> control_send;                         // key, value, channel
    std::function<bool(int, int)> switch_on;                                 // key, channel
    // THE INSERTION EFFECT's tables (the export's EFXU: gsefx's numbered
    // types, families and each type's parameters), the GS exclusive the
    // panel sends (posted, as a file's), the channel the part listens on (-1
    // all), and the last controller moved (gsefx's source code: CC 1-95,
    // 0x60 aftertouch, 0x61 the wheel; and when, steady_clock ns)
    struct EfxType {
        int num, msb, lsb;
        std::string name;
    };
    struct EfxCat {
        int a, b;
        std::string name;
    };
    struct EfxParam {
        int n;
        std::string name;
        char mark;                      // '+' or '#': moved by that controller; '-' neither
        bool read;                      // the model reads it (gsefx.in_effect has it)
        int fresh;                      // its value in effect where none is set
        std::vector<int> vals;          // the raw values it takes
        std::vector<std::string> shown; // ...each as Roland's panel prints it
    };
    std::vector<EfxType> efx_types;
    std::vector<EfxCat> efx_cats;
    std::map<std::pair<int, int>, std::vector<EfxParam>> efx_params;
    std::function<void(const std::vector<uint8_t> &)> efx_send;
    std::function<std::pair<int, long long>()> last_ctl;
    int channel = -1;
};

// the export's EFXU into the host's tables (native_export.py's lines)
static void efx_tables(Host &H, const std::string &txt)
{
    auto split = [](const std::string &s, char d) {
        std::vector<std::string> f;
        size_t a = 0;
        for (size_t b; (b = s.find(d, a)) != std::string::npos; a = b + 1)
            f.push_back(s.substr(a, b - a));
        f.push_back(s.substr(a));
        return f;
    };
    for (const std::string &ln : split(txt, '\n')) {
        std::vector<std::string> f = split(ln, '\t');
        if (f[0] == "T" && f.size() == 5) {
            H.efx_types.push_back({atoi(f[1].c_str()), atoi(f[2].c_str()), atoi(f[3].c_str()), f[4]});
        } else if (f[0] == "C" && f.size() == 4) {
            H.efx_cats.push_back({atoi(f[1].c_str()), atoi(f[2].c_str()), f[3]});
        } else if (f[0] == "P" && f.size() == 10) {
            Host::EfxParam p{atoi(f[3].c_str()), f[4], f[5].empty() ? '-' : f[5][0], f[6] == "1", atoi(f[7].c_str()),
                             {}, split(f[9], '\x1f')};
            for (const std::string &v : split(f[8], ','))
                p.vals.push_back(atoi(v.c_str()));
            if (p.vals.size() == p.shown.size())
                H.efx_params[std::make_pair(atoi(f[1].c_str()), atoi(f[2].c_str()))].push_back(p);
        }
    }
}

// gsefx's addresses: the sends from the effect, its two controllers
static const int EFX_SEND[3] = {0x17, 0x18, 0x19};
static const int EFX_CTL_SRC1 = 0x1B, EFX_CTL_DEP1 = 0x1C, EFX_CTL_SRC2 = 0x1D, EFX_CTL_DEP2 = 0x1E;
static const int EFX_SRC_CAF = 0x60, EFX_SRC_BEND = 0x61;

// gsefx.message: the GS DT1 exclusive (no F0/F7) for an EFX setting --
// kind 't' type (a msb, b lsb), 'p' parameter (a 1-20, b), 's' a send or
// controller (a its address, b), 'c' a part (a channel, b on)
static std::vector<uint8_t> efx_message(char kind, int a, int b)
{
    std::vector<uint8_t> body;
    if (kind == 't') {
        body = {0x40, 0x03, 0x00, (uint8_t)a, (uint8_t)b};
    } else if (kind == 'p') {
        body = {0x40, 0x03, (uint8_t)(0x02 + a), (uint8_t)b};
    } else if (kind == 's') {
        body = {0x40, 0x03, (uint8_t)a, (uint8_t)b};
    } else {
        int ch = a % 16, blk = ch == 9 ? 0 : ch < 9 ? ch + 1 : ch;
        body = {(uint8_t)(a >= 16 ? 0x50 : 0x40), (uint8_t)(0x40 | blk), 0x22, (uint8_t)(b ? 1 : 0)};
    }
    int sum = 0;
    for (uint8_t x : body)
        sum += x;
    std::vector<uint8_t> m = {0x41, 0x10, 0x42, 0x12};
    m.insert(m.end(), body.begin(), body.end());
    m.push_back((uint8_t)((128 - sum % 128) % 128));
    return m;
}

// the state nv_part_efx_state wrote, read back
struct EfxView {
    bool has = false;
    int msb = 0, lsb = 0, p[21], snd[3] = {40, 0, 0}, ctl[4] = {0, 0x40, 0, 0x40};
    std::vector<int> parts;
    std::map<int, int> cv;
    int status = -1;
    explicit EfxView(const std::vector<int> &o)
    {
        for (int q = 0; q < 21; q++)
            p[q] = -1;
        if (o.size() < 31)
            return;
        has = true;
        msb = o[0];
        lsb = o[1];
        for (int q = 1; q <= 20; q++)
            p[q] = o[1 + q];
        for (int q = 0; q < 3; q++)
            snd[q] = o[22 + q];
        for (int q = 0; q < 4; q++)
            ctl[q] = o[25 + q];
        size_t i = 29, np = (size_t)o[i++];
        for (size_t q = 0; q < np && i < o.size(); q++)
            parts.push_back(o[i++]);
        size_t nc = i < o.size() ? (size_t)o[i++] : 0;
        for (size_t q = 0; q < nc && i + 1 < o.size(); q++, i += 2)
            cv[o[i]] = o[i + 1];
        status = i < o.size() ? o[i] : -1;
    }
};

// THE STOP KEYS, as livetui's on a US layout: row 0 the digits, row 1 the
// same keys shifted; rows 2 and 3 the same after the prefix (backtick: a
// window manager that keeps Alt never lets Alt+digit through)
static const char STOP_DIGITS[] = "123456789", STOP_SHIFTED[] = "!@#$%^&*(";
static const int STOP_PREFIX = '`';

// THE GLOBALS, by the host's numbers (nv_host_global's: 9 came last, mod
// rate), shown in livetui.GLOBALS' order (GLOBAL_ORDER)
static const int NGLOBALS = 14;
static const char *GLOBAL_NAMES[NGLOBALS] = {"master", "headroom", "limiter", "bend range", "mod depth", "aftertouch",
                                             "gpu", "room tail", "room", "mod rate", "metronome", "ring",
                                             "metro level", "standard"};
static const char *GLOBAL_UNITS[NGLOBALS] = {"dB", "dB", "", "st", "cents", "dB", "onoff", "onoff", "room", "%",
                                             "bpm", "ring", "dB", "std"};
static const double GLOBAL_RANGE[NGLOBALS][3] = {{-60.0, 0.0, 0.5}, {0.0, 24.0, 0.5}, {0.10, 1.00, 0.02},
                                                 {0.0, 24.0, 0.5}, {0.0, 200.0, 5.0}, {0.0, 24.0, 0.5},
                                                 {0.0, 1.0, 1.0}, {0.0, 1.0, 1.0}, {0.0, 0.0, 1.0},
                                                 {0.0, 1.5, 0.05}, {0.0, 300.0, 1.0}, {0.0, 16.0, 1.0},
                                                 {-40.0, 12.0, 0.5}, {0.0, 4.0, 1.0}};
// (livetui's order: mod rate after mod depth; the metronome, its ring and level last)
static const int GLOBAL_ORDER[NGLOBALS] = {0, 1, 2, 3, 4, 9, 5, 8, 6, 7, 10, 11, 12, 13};
static const char *STD_NAMES[5] = {"ours", "SC-55", "SC-88", "SC-88Pro", "SC-8850"};     // (livetui's)
static int global_pos(int i)
{
    for (int k = 0; k < NGLOBALS; k++)
        if (GLOBAL_ORDER[k] == i)
            return k;
    return 0;
}

// THE TUNERS (livetui.TUNERS, TUNER_NOTE): the name, what it is for
static const char *TUNERS[][2] = {
    {"hybrid440", "A=440, the default: the hybrid temperament at concert pitch"},
    {"hybrid", "A=415, the same temperament at baroque pitch"},
    {"hybridharm", "pure 2:1 octaves -- right for mode-locked pipes"},
    {"hybridharm440", "pure 2:1 octaves at concert pitch"},
    {"hybridmean", "the hybrid's chains bridged by a mean third: no wolf, pure octaves"},
    {"hybridmeanpiano", "hybridmean on a Steinway's stretched octaves, A=440"},
    {"stretchedhelmholtz", "two pure-fifth chains joined by inharmonic octaves, A=440"},
    {"gm2", "a GM 2 device: equal A=440, and the FILE owns the tuning (MTS)"},
    {"even", "equal temperament, A=440"},
    {"stretch", "pure fifths, the comma taken into stretched octaves, A=415"},
    {"werckmeister", "Werckmeister III, from Sankey's published cents, A=415"},
    {"sankey", "Sankey's consonance-found Scarlatti tuning, A=415"},
    {"meantone", "quarter-comma, A=415"},
    {"just", "pure ratios from the tonic"},
    {"pyth", "pure fifths"},
    {"well", "a circulating well temperament"},
    {"linear", "linear in cents"},
    {"linear5", "linear over five fifths"},
    {"linearwell", "linear well temperament"},
    {"bechstein", "measured from a Bechstein"},
    {"spiral", "the spiral of fifths, unclosed"},
    {"semi", "semitone-based"},
    {"dynamic", "solved once over the keyboard (only midi.py retunes per chord)"},
    {"path", "follows a written path of notes"},
    {"raga:et@c#", "Indian, Sa C#: equal (Serra 2011: sung Hindustani sits nearest it)"},
    {"raga:just5@c#", "Indian, Sa C#: 5-limit just (theory)"},
    {"raga:pythagorean@c#", "Indian, Sa C#: Pythagorean (theory)"},
    {"raga:bel_todi/todi@c#", "Indian, Sa C#: Todi as Bel measured it, near Pythagorean"}};
static const int NTUNERS = sizeof(TUNERS) / sizeof(TUNERS[0]);

// THE PARTS' COLUMNS (livetui.COLS, COL_W): what can be changed about a part,
// every one by the same - and +; Enter picks (patch, tuner) or takes a value
static const char *PCOLS[] = {"patch", "ch", "lo", "hi", "tr", "level", "tuner", "touch", "stops", "efx"};
static const int PCOL_W[] = {33, 4, 5, 5, 4, 8, 11, 6, 11, 5};
static const int NPCOLS = 10;
static const double LEVEL_DB_MIN = -60.0, LEVEL_DB_MAX = 24.0;   // (livetui's)

// ---- THE SYNTH PANE (livetui's SYNTH_KNOBS, synth_fmt) ----
// moog.PANEL's keys in its order (nv.h's NV_MK_*: native.MOOG_KNOBS, asserted equal)
static const char *MK_NAMES[51] = {
    "osc1_octave", "osc1_wave", "osc2_octave", "osc2_wave", "osc2_freq", "tune", "sub_wave", "osc1_level",
    "osc2_level", "sub_level", "noise_level", "cutoff", "resonance", "eg_amount", "kb_track", "mode", "res_bass",
    "f_attack", "f_decay", "f_sustain", "f_release", "a_attack", "a_decay", "a_sustain", "a_release", "glide", "sync",
    "lfo1_rate", "lfo1_shape", "lfo1_depth", "lfo1_dest", "lfo1_reset", "mod_amount", "mod_dest", "mf104_on",
    "mf104_time", "mf104_range", "mf104_feedback", "mf104_mix", "mf104_rate", "mf104_amount", "mf104_wave",
    "a_vel", "lfo2_rate", "lfo2_pitch", "lfo2_cut", "lfo2_amp", "f_loop", "a_loop", "f_vel", "multitrig"};
static int mk_index(const char *name)
{
    for (int k = 0; k < 51; k++)
        if (!strcmp(MK_NAMES[k], name))
            return k;
    return -1;
}
// (section, knob, label, kind), livetui.SYNTH_KNOBS
static const char *SYNTH_KNOBS[][4] = {
    {"OSC 1", "osc1_octave", "octave", "foot"}, {"OSC 1", "osc1_wave", "wave", "wave"},
    {"OSC 2", "osc2_octave", "octave", "foot"}, {"OSC 2", "osc2_wave", "wave", "wave"},
    {"OSC 2", "osc2_freq", "freq", "semi"}, {"OSC 2", "sync", "sync 1>2", "onoff"},
    {"MOD", "mod_amount", "amount", "modamt"}, {"MOD", "mod_dest", "dest", "moddest"},
    {"TUNE", "tune", "tune", "semi"}, {"GLIDE", "glide", "glide", "glide"}, {"SUB", "sub_wave", "wave", "subwave"},
    {"MIXER", "osc1_level", "osc 1", "level"}, {"MIXER", "osc2_level", "osc 2", "level"},
    {"MIXER", "sub_level", "sub", "level"}, {"MIXER", "noise_level", "noise", "level"},
    {"FILTER", "cutoff", "cutoff", "hz"}, {"FILTER", "resonance", "resonance", "level"},
    {"FILTER", "eg_amount", "eg amount", "oct"}, {"FILTER", "kb_track", "kb track", "track"},
    {"FILTER", "mode", "mode", "mode"}, {"FILTER", "res_bass", "res bass", "onoff"},
    {"F ENV", "f_attack", "attack", "atime"}, {"F ENV", "f_decay", "decay", "time"},
    {"F ENV", "f_sustain", "sustain", "sustain"}, {"F ENV", "f_release", "release", "time"},
    {"F ENV", "f_loop", "loop", "onoff"}, {"F ENV", "f_vel", "vel", "onoff"},
    {"A ENV", "a_attack", "attack", "atime"}, {"A ENV", "a_decay", "decay", "time"},
    {"A ENV", "a_sustain", "sustain", "sustain"}, {"A ENV", "a_release", "release", "time"},
    {"A ENV", "a_vel", "vel", "avel"}, {"A ENV", "a_loop", "loop", "onoff"},
    {"A ENV", "multitrig", "multi-trig", "onoff"},
    {"LFO 1", "lfo1_rate", "rate", "lfohz"}, {"LFO 1", "lfo1_shape", "shape", "lfoshape"},
    {"LFO 1", "lfo1_depth", "depth", "lfodepth"}, {"LFO 1", "lfo1_dest", "dest", "lfodest"},
    {"LFO 1", "lfo1_reset", "kb reset", "onoff"},
    {"LFO 2", "lfo2_rate", "rate", "lfo2hz"}, {"LFO 2", "lfo2_pitch", "pitch", "onoff"},
    {"LFO 2", "lfo2_cut", "cutoff", "onoff"}, {"LFO 2", "lfo2_amp", "amp", "onoff"},
    {"MF-104", "mf104_on", "delay", "onoff"}, {"MF-104", "mf104_time", "time", "mftime"},
    {"MF-104", "mf104_range", "range", "mfrange"}, {"MF-104", "mf104_feedback", "feedback", "mffb"},
    {"MF-104", "mf104_mix", "mix", "level"}, {"MF-104", "mf104_rate", "lfo rate", "mfhz"},
    {"MF-104", "mf104_amount", "lfo amount", "mfoct"}};
static const int NSYNTH = sizeof(SYNTH_KNOBS) / sizeof(SYNTH_KNOBS[0]);

// livetui.SYNTH_STEPS: a switch's positions (empty: a knob, 0..1)
static std::vector<double> synth_steps(const std::string &kind)
{
    if (kind == "foot") return {32, 16, 8, 4};
    if (kind == "track" || kind == "onoff" || kind == "mfrange") return {0, 1};
    if (kind == "avel") return {-1, 0, 1};
    if (kind == "mode" || kind == "lfoshape" || kind == "lfodest" || kind == "moddest") return {0, 1, 2, 3};
    return {};
}
static bool synth_centred(const std::string &kind)     // (livetui.SYNTH_CENTRED: a centre detent)
{
    return kind == "semi" || kind == "oct" || kind == "modamt" || kind == "lfodepth";
}

// moog.py's laws for the panel's words (and mf104.py's): the knob in its own terms
namespace moogfmt {
static double clip01(double v) { return std::max(0.0, std::min(1.0, v)); }
static double interp(double x, const double *xs, const double *ys, int n)     // (numpy.interp)
{
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    for (int i = 1; i < n; i++)
        if (x <= xs[i])
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
    return ys[n - 1];
}
static const double EG_V[11] = {0.0, 0.1, 0.2, 0.30000000000000004, 0.4, 0.5, 0.6000000000000001,
                                0.7000000000000001, 0.8, 0.9, 1.0};
static const double EG_LOG[11] = {-6.907755278982137, -4.006333684899388, -3.0966581921439515, -2.432693778341066,
                                  -1.8540604954254343, -1.3302921710046056, -0.8344803566765893,
                                  -0.3581045367483269, 0.128393214768399, 0.6376344706296865, 1.7369512327330598};
static double knob_tau(double v) { return exp(interp(clip01(v), EG_V, EG_LOG, 11)); }
static double knob_attack(double v) { return knob_tau(v) * 3.5361166995615254; }
static double knob_time(double v) { return 4.0 * knob_tau(v); }
static const double SUS_V[6] = {0.0, 0.25, 0.5, 0.75, 0.9, 1.0};
static const double SUS_TARGET[6] = {-0.055, 0.006, 0.23, 0.5466, 0.8015, 1.0};
static double sustain_level(double v) { return std::max(0.0, interp(clip01(v), SUS_V, SUS_TARGET, 6)); }
static double knob_cutoff(double v) { return 7.9 * pow(2.0, 11.38 * clip01(v)); }
static double knob_lfo_rate(double v) { return 0.05 * pow(870.0, clip01(v)); }
static const double CC9[9] = {0.0, 16.0 / 127, 32.0 / 127, 48.0 / 127, 64.0 / 127, 80.0 / 127, 96.0 / 127,
                              112.0 / 127, 1.0};
static double knob_lfo2_rate(double v)          // (moog.LFO2_HZ, log-interpolated)
{
    static const double H[9] = {0.023, 0.042, 0.20, 0.643, 1.50, 2.94, 5.08, 8.0, 11.72};
    double l[9];
    for (int i = 0; i < 9; i++)
        l[i] = log(H[i]);
    return exp(interp(clip01(v), CC9, l, 9));
}
static double knob_glide_tau(double v)          // (moog.GLIDE_TAU, log-interpolated; 0 none)
{
    static const double T[9] = {0.0021, 0.0045, 0.0110, 0.027, 0.062, 0.146, 0.355, 1.02, 5.03};
    double l[9];
    for (int i = 0; i < 9; i++)
        l[i] = log(T[i]);
    return v <= 0.0 ? 0.0 : exp(interp(clip01(v), CC9, l, 9));
}
static double cube(double v, double k)
{
    double x = clip01(v) - 0.5;
    return k * x * x * x;
}
static double eg_octaves(double v)
{
    double x = clip01(v) - 0.5;
    return 45.0 * x * fabs(x);
}
static double bipolar(double v, double span) { return (std::max(0.0, std::min(1.0, v)) - 0.5) * 2.0 * span; }
static const double TRI = 0.335, SAW = 0.5, SQUARE = 0.68, PULSE_MIN = 0.025, SUB_SQUARE = 0.3, SUB_PULSE_MIN = 0.0033;
static const char *LFO_SHAPES[4] = {"triangle", "sawtooth", "ramp", "square"};
static const char *LFO_DESTS[4] = {"cutoff", "osc 2 freq", "osc 1 wave", "sub wave"};
static const char *MOD_DESTS[4] = {"1>2 FM", "F ENV>OSC 2 FREQ", "F ENV>OSC 2 WAVE", "F ENV>SUB WAVE"};
static double mf_time(double v, int rng)
{
    const double lo = rng ? 0.08 : 0.04, hi = rng ? 0.8 : 0.4;
    return lo * pow(hi / lo, clip01(v));
}
}  // namespace moogfmt

// livetui.synth_fmt: a Messenger knob's value in the panel's own terms (the
// pedal's TIME against its RANGE, LFO 1's depth where it is sent: pn the panel)
static std::string synth_fmt(const std::string &kind, double v, const double *pn)
{
    using namespace moogfmt;
    char b[64];
    auto rnd = [](double x) { return (long)std::nearbyint(x); };      // (Python's round: half to even)
    if (kind == "mftime") {
        snprintf(b, sizeof b, "%ld ms", rnd(1000 * mf_time(v, (int)pn[mk_index("mf104_range")])));
    } else if (kind == "mfrange") {
        return (int)v ? "long" : "short";
    } else if (kind == "mffb") {
        snprintf(b, sizeof b, "%.2f", 0.98 * std::min(1.0, clip01(v) / 0.8));
    } else if (kind == "mfhz") {
        snprintf(b, sizeof b, "%.2f Hz", 0.05 * pow(50.0 / 0.05, clip01(v)));
    } else if (kind == "mfoct") {
        snprintf(b, sizeof b, "%.2f oct", 1.0 * clip01(v) / 0.9);
    } else if (kind == "foot") {
        snprintf(b, sizeof b, "%d'", (int)v);
    } else if (kind == "wave") {
        if (v < TRI - 1e-9) {
            snprintf(b, sizeof b, "fold %ld%%", rnd(100 * (TRI - v) / TRI));
        } else if (fabs(v - TRI) < 1e-9) {
            return "triangle";
        } else if (fabs(v - SAW) < 1e-9) {
            return "saw";
        } else if (fabs(v - SQUARE) < 1e-9) {
            return "square";
        } else if (v < SAW) {
            return "tri>saw";
        } else if (v < SQUARE) {
            return "saw>sq";
        } else {
            snprintf(b, sizeof b, "pulse %ld%%", rnd(100 * (0.5 - (0.5 - PULSE_MIN) * (v - SQUARE) / (1 - SQUARE))));
        }
    } else if (kind == "subwave") {
        if (fabs(v - SUB_SQUARE) < 1e-9)
            return "square";
        if (v < SUB_SQUARE)
            return v < 1e-9 ? "triangle" : "tri>sq";
        snprintf(b, sizeof b, "pulse %ld%%", rnd(100 * (0.5 - (0.5 - SUB_PULSE_MIN) * (v - SUB_SQUARE) / (1 - SUB_SQUARE))));
    } else if (kind == "semi") {
        snprintf(b, sizeof b, "%+.2f st", bipolar(v, 7.0));
    } else if (kind == "level") {
        snprintf(b, sizeof b, "%.2f", v);
    } else if (kind == "hz") {
        double f = knob_cutoff(v);
        if (f >= 1000)
            snprintf(b, sizeof b, "%.1f kHz", f / 1000.0);
        else
            snprintf(b, sizeof b, "%ld Hz", rnd(f));
    } else if (kind == "oct") {
        snprintf(b, sizeof b, "%+.1f oct", eg_octaves(v));
    } else if (kind == "track") {
        const double r3 = std::nearbyint(v * 1000.0) / 1000.0;
        return r3 == 0.0 ? "off" : r3 == 1.0 ? "1:1" : "2/3";
    } else if (kind == "mode") {
        static const char *M[4] = {"4P LP", "2P LP", "BP", "HP"};
        return M[std::max(0, std::min(3, (int)v))];
    } else if (kind == "onoff") {
        return v != 0.0 ? "on" : "off";
    } else if (kind == "lfohz") {
        snprintf(b, sizeof b, "%.2f Hz", knob_lfo_rate(v));
    } else if (kind == "lfo2hz") {
        snprintf(b, sizeof b, "%.2f Hz", knob_lfo2_rate(v));
    } else if (kind == "glide") {
        const double t = knob_glide_tau(v);
        if (t <= 0.0)
            return "off";
        if (t >= 1.0)
            snprintf(b, sizeof b, "%.2f s", t);
        else
            snprintf(b, sizeof b, "%ld ms", rnd(t * 1000));
    } else if (kind == "avel") {
        return v < 0.0 ? "voice" : v >= 0.5 ? "on" : "off";
    } else if (kind == "lfoshape") {
        return LFO_SHAPES[std::max(0, std::min(3, (int)v))];
    } else if (kind == "lfodepth") {
        const int dest = (int)pn[mk_index("lfo1_dest")];
        if (dest == 1)
            snprintf(b, sizeof b, "%+.2f oct", cube(v, 37.2));
        else if (dest >= 2)
            snprintf(b, sizeof b, "%+.3f", cube(v, 7.809694793536804));
        else
            snprintf(b, sizeof b, "%+.2f oct", cube(v, 87.0));
    } else if (kind == "lfodest") {
        return LFO_DESTS[std::max(0, std::min(3, (int)v))];
    } else if (kind == "moddest") {
        return MOD_DESTS[std::max(0, std::min(3, (int)v))];
    } else if (kind == "modamt") {
        snprintf(b, sizeof b, "%+.0f%%", bipolar(v, 100.0));
    } else if (kind == "sustain") {
        double lv = sustain_level(v);
        if (lv < 0.005)
            return "closed";
        snprintf(b, sizeof b, "%.0f%%", 100.0 * lv);
    } else if (kind == "time" || kind == "atime") {
        double t = kind == "atime" ? knob_attack(v) : knob_time(v);
        if (t >= 1.0)
            snprintf(b, sizeof b, "%.2f s", t);
        else
            snprintf(b, sizeof b, "%ld ms", rnd(t * 1000));
    } else {
        snprintf(b, sizeof b, "%.2f", v);
    }
    return b;
}

// live.CONTROLS: the destinations, in the panel's order, (key, label)
static const std::pair<int, const char *> CONTROLS[] = {
    {64, "sustain"}, {66, "sostenuto"}, {67, "soft"}, {65, "portamento"}, {-3, "mono"}, {1, "mod wheel"},
    {11, "expression"}, {7, "volume"}, {10, "pan"}, {5, "portamento time"}, {93, "chorus"},
    {81, "scanner (V/C)"}, {4, "crescendo"}, {12, "drive"}, {13, "detune"}, {18, "drones"}, {19, "mouth"},
    {20, "crank"}, {70, "tone (rockers)"}, {80, "rotor speed"}, {92, "tremolo depth"}, {74, "brightness"}, {71, "resonance"}, {73, "attack"}, {75, "decay"},
    {72, "release"}, {76, "vibrato rate"}, {77, "vibrato depth"}, {78, "vibrato delay"}, {-1, "pitch wheel"},
    {-2, "aftertouch"}};
static const int NCONTROLS = sizeof(CONTROLS) / sizeof(CONTROLS[0]);

// live.CONTROLS' defaults and kinds: each control's resting value, and
// switch, selector (the scanner's), bend, pressure or continuous
static int control_default(int key)
{
    switch (key) {
    case 11: case 18: return 127;
    case 7: return 100;
    case 12: return 32;
    case 13: return 64;
    case 10: case 74: case 71: case 73: case 75: case 72: case 76: case 77: case 78: return 64;
    }
    return 0;
}
static std::string control_kind(int key)
{
    if (key == 64 || key == 66 || key == 67 || key == 65 || key == -3) return "switch";
    if (key == 81) return "selector";
    if (key == -1) return "bend";
    if (key == -2) return "pressure";
    return "continuous";
}
// scanner.POSITIONS: the Hammond's vibrato/chorus selector (CC81), each one's start
static const char *SCAN_NAMES[7] = {"off", "V1", "V2", "V3", "C1", "C2", "C3"};
static const int SCAN_STARTS[7] = {0, 18, 37, 55, 73, 91, 110};
// THE KEYS A CONTROL MAY BE BOUND TO (livetui.HOTKEYS_FREE): what the panel
// does not use itself, in any pane -- a bound key fires from every pane
static const char HOTKEYS_FREE[] = "cefginouvwyz[];',./ACGHJKOQUVWYZ";     // (I: the MIDI inputs)

static bool control_switch(int key)
{
    return key == 64 || key == 66 || key == 67 || key == 65 || key == -3;
}

static const char *control_label(int key)
{
    for (auto &c : CONTROLS)
        if (c.first == key)
            return c.second;
    return nullptr;
}

// live.key_name: MIDI 60 is C4
static std::string key_name(int n)
{
    static const char *K[12] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
    return std::string(K[((n % 12) + 12) % 12]) + std::to_string(n / 12 - 1);
}

// livetui.parse_note: C1, F#2, Bb3, or 0-127; -1 not a key
static int parse_note(const std::string &s)
{
    if (s.empty())
        return -1;
    if (isdigit((unsigned char)s[0])) {
        int n = atoi(s.c_str());
        return n >= 0 && n <= 127 ? n : -1;
    }
    static const int base[7] = {9, 11, 0, 2, 4, 5, 7};      // A B C D E F G
    char c = (char)toupper((unsigned char)s[0]);
    if (c < 'A' || c > 'G')
        return -1;
    int n = base[c - 'A'];
    size_t i = 1;
    if (i < s.size() && (s[i] == '#' || s[i] == 'b')) {
        n += s[i] == '#' ? 1 : -1;
        i++;
    }
    if (i >= s.size())
        return -1;
    int oct = atoi(s.c_str() + i);
    n += 12 * (oct + 1);
    return n >= 0 && n <= 127 ? n : -1;
}

// live.Route.describe
static std::string describe(const std::array<int, 7> &r)
{
    std::string src;
    if (r[0] == 0) {
        const char *l = control_label(r[1]);
        src = l ? l : "CC" + std::to_string(r[1]);
    } else if (r[0] == 1) {
        src = r[1] == 0 ? "pitch ↑" : r[1] == 1 ? "pitch ↓" : "pitch ↕";
    } else if (r[0] == 2) {
        src = "aftertouch";
    } else {
        src = "key " + key_name(r[1]);
    }
    const char *d = control_label(r[2]);
    std::string dst = d ? d : std::to_string(r[2]);
    std::string how = control_switch(r[2]) ? (r[5] ? "toggle" : "held") : r[0] == 3 ? "velocity" : "scaled";
    return src + " → " + dst + "  " + how + "  " + (r[3] ? "keeps" : "replaces") + "  "
           + (r[4] < 0 ? "all" : "ch" + std::to_string(r[4] + 1));
}

// ---- the terminal ----------------------------------------------------------
// THE MOUSE (and a touchscreen, which a terminal hears as one; livetui's):
// button-event tracking -- presses, releases, drags with a button down, the
// wheel -- in SGR coordinates (ESC [ < b ; x ; y M, m for a release).
// TUNING_MOUSE=0 leaves the terminal's own.
static const char *MOUSE_ON = "\x1b[?1002h\x1b[?1006h";
static const char *MOUSE_OFF = "\x1b[?1006l\x1b[?1002l";
static const int KEY_MOUSE = 2000;      // (Term::key: a report, in Term::m)

// one report: kind press | release | drag | wheel, the button (0 left), the
// cell (x, y, from 0), and for the wheel dy (+1 up, -1 down)
struct Mouse {
    enum Kind { PRESS, RELEASE, DRAG, WHEEL } kind = PRESS;
    int button = 0, x = 0, y = 0, dy = 0;
};

struct Term {
    termios old{};
    bool on = false, mouse = false;
    int w = 80, h = 24;
    Mouse m;                            // the last report (key's KEY_MOUSE)

    void enter()
    {
        tcgetattr(0, &old);
        termios t = old;
        t.c_lflag &= ~(ICANON | ECHO);
        t.c_cc[VMIN] = 0;
        t.c_cc[VTIME] = 0;
        tcsetattr(0, TCSANOW, &t);
        fputs("\x1b[?1049h\x1b[?25l", stdout);       // the alternate screen, no cursor
        const char *tm = getenv("TUNING_MOUSE");
        mouse = !(tm && !strcmp(tm, "0"));
        if (mouse)
            fputs(MOUSE_ON, stdout);
        fflush(stdout);
        on = true;
    }

    void leave()
    {
        if (!on)
            return;
        if (mouse)
            fputs(MOUSE_OFF, stdout);
        fputs("\x1b[?25h\x1b[?1049l", stdout);
        fflush(stdout);
        tcsetattr(0, TCSANOW, &old);
        on = false;
    }

    void size()
    {
        winsize ws{};
        if (ioctl(1, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0) {
            w = ws.ws_col;
            h = ws.ws_row;
        }
    }

    // the rest of an SGR mouse report, after ESC [ <: KEY_MOUSE (in m), or -1
    // (a report cut short or not one: dropped)
    int mouse_report()
    {
        std::string body;
        for (int i = 0; i < 24; i++) {
            fd_set f;
            FD_ZERO(&f);
            FD_SET(0, &f);
            timeval t{0, 20000};
            unsigned char c;
            if (select(1, &f, nullptr, nullptr, &t) <= 0 || read(0, &c, 1) != 1)
                return -1;
            if (c == 'M' || c == 'm') {
                int b, x, y;
                if (sscanf(body.c_str(), "%d;%d;%d", &b, &x, &y) != 3)
                    return -1;
                m = Mouse();
                m.button = b & 3;
                m.x = x - 1;
                m.y = y - 1;
                if (b & 64) {                       // the wheel: 64 up, 65 down
                    m.kind = Mouse::WHEEL;
                    m.dy = (b & 1) == 0 ? 1 : -1;
                } else {
                    m.kind = c == 'm' ? Mouse::RELEASE : (b & 32) ? Mouse::DRAG : Mouse::PRESS;
                }
                return KEY_MOUSE;
            }
            body += (char)c;
        }
        return -1;
    }

    // one key within ms (-1 none): arrows as 1000+ (up down right left), shift-tab 1004,
    // page up and down 1005-1006, home and end 1007-1008; a mouse report KEY_MOUSE (in m)
    int key(int ms)
    {
        fd_set f;
        FD_ZERO(&f);
        FD_SET(0, &f);
        timeval tv{ms / 1000, (ms % 1000) * 1000};
        if (select(1, &f, nullptr, nullptr, &tv) <= 0)
            return -1;
        unsigned char c;
        if (read(0, &c, 1) != 1)
            return -1;
        if (c != 27)
            return c;
        unsigned char s[2];
        timeval t2{0, 20000};
        FD_ZERO(&f);
        FD_SET(0, &f);
        if (select(1, &f, nullptr, nullptr, &t2) <= 0 || read(0, &s[0], 1) != 1)
            return 27;
        if (s[0] != '[' && s[0] != 'O')
            return 27;
        if (read(0, &s[1], 1) != 1)
            return 27;
        if (s[0] == '[' && s[1] == '<')
            return mouse_report();
        if (s[1] >= '1' && s[1] <= '8') {           // ESC [ n ~: page up 5, down 6, home 1/7, end 4/8
            unsigned char t;
            if (read(0, &t, 1) != 1 || t != '~')
                return 27;
            return s[1] == '5' ? 1005 : s[1] == '6' ? 1006 : (s[1] == '1' || s[1] == '7') ? 1007
                                                            : (s[1] == '4' || s[1] == '8') ? 1008 : 27;
        }
        switch (s[1]) {
        case 'H': return 1007;
        case 'F': return 1008;
        case 'A': return 1000;
        case 'B': return 1001;
        case 'C': return 1002;
        case 'D': return 1003;
        case 'Z': return 1004;
        }
        return 27;
    }
};

// ---- the panel -------------------------------------------------------------
struct Panel {
    Host &H;
    Term T;
    // THE PANES, livetui's order: the parts, the globals, the controls and routes
    enum { P_PARTS = 0, P_GLOBALS = 1, P_ROUTES = 2, P_SYNTH = 3, NPANES = 4 };
    int srow = 0, slayer = 0;           // the synth pane's knob and layer (livetui's srow, slayer)
    double spn[51] = {};                // the selected part's panel as last read, its own knobs
    char sown[51] = {};
    int snl = 0;                        // (its layers; 0 not a Moog)
    int pane = P_PARTS;
    int grow = 0, crow = 0;
    int prow = 0, pcol = 0;             // the PARTS pane's row and column (livetui's row, col)
    std::vector<PartRow> prows;         // the parts as last drawn
    bool help = false;
    bool stop_bank = false;             // the stop prefix pressed: the next stop key is rows 3-4's
    std::string msg;
    std::chrono::steady_clock::time_point msg_until;
    std::string out;                    // the frame being drawn
    Snap s;
    double lev[2] = {-90.0, -90.0}, hold[2] = {-90.0, -90.0};
    std::chrono::steady_clock::time_point held_at[2];
    std::deque<double> cpu;             // the load, its worst each 0.2 s (livetui._cpu_hist)
    double cpu_acc = 0.0;
    int cpu_n = 0;
    std::chrono::steady_clock::time_point last;
    int nrow = 0, nlimit = 1 << 30;     // rows drawn; the last the panes may have
    std::map<std::string, std::pair<long, std::chrono::steady_clock::time_point>> health;
    // WHAT A TAP DOES (livetui.hit): this frame's rows and columns, each an
    // action -- drawn later is on top
    enum HitKind { H_PANE, H_KEY, H_GLOBAL, H_GBAR, H_STOP, H_ROUTE, H_CELL, H_KNOB, H_KBAR };
    struct Hit {
        int y, x0, x1;
        HitKind kind;
        int a, b;
    };
    std::vector<Hit> hits;
    int drag_global = -1, drag_y = 0;  // a global being dragged: up is more
    int drag_cell = -1;                 // ...or a part's cell (its column)
    int drag_knob = -1;                 // ...or a synth knob
    bool quit = false;

    explicit Panel(Host &h) : H(h) {}

    void hit(int y, int x0, int x1, HitKind k, int a = 0, int b = 0) { hits.push_back(Hit{y, x0, x1, k, a, b}); }
    const Hit *hit_at(int y, int x) const
    {
        for (auto it = hits.rbegin(); it != hits.rend(); ++it)
            if (it->y == y && it->x0 <= x && x < it->x1)
                return &*it;
        return nullptr;
    }

    // cells on the screen a drawn string takes: its escapes none
    static int vcols(const std::string &x)
    {
        int n = 0;
        for (size_t i = 0; i < x.size(); i++) {
            if (x[i] == '\x1b') {
                while (i + 1 < x.size() && !isalpha((unsigned char)x[i + 1]))
                    i++;
                i++;
                continue;
            }
            n += ((unsigned char)x[i] & 0xC0) != 0x80;
        }
        return n;
    }

    void say(const std::string &m, double secs = 3.0)
    {
        msg = m;
        msg_until = std::chrono::steady_clock::now() + std::chrono::milliseconds((long)(secs * 1000));
    }

    // -- drawing --
    std::string C(const char *what) const
    {
        if (!strcmp(what, "accent")) return "\x1b[38;5;45m";
        if (!strcmp(what, "accent2")) return "\x1b[38;5;141m";
        if (!strcmp(what, "dim")) return "\x1b[38;5;244m";
        if (!strcmp(what, "label")) return "\x1b[38;5;250m";
        if (!strcmp(what, "value")) return "\x1b[38;5;255m\x1b[1m";
        if (!strcmp(what, "ok")) return "\x1b[38;5;78m";
        if (!strcmp(what, "warn")) return "\x1b[38;5;214m";
        if (!strcmp(what, "bad")) return "\x1b[38;5;203m";
        if (!strcmp(what, "sel")) return "\x1b[7m";
        if (!strcmp(what, "faint")) return "\x1b[38;5;238m";
        // a stop's button (livetui's btn, btnkey): raised grey, its key dimmer;
        // drawn, filled in the accent
        if (!strcmp(what, "btn")) return "\x1b[38;5;252;48;5;237m";
        if (!strcmp(what, "btnkey")) return "\x1b[38;5;243;48;5;237m";
        if (!strcmp(what, "btnon")) return "\x1b[38;5;234;48;5;45m\x1b[1m";
        return "";
    }

    void line(const std::string &txt)
    {
        if (nrow >= nlimit)
            return;                         // (past the panes' rows: the bottom's)
        out += txt + "\x1b[0m\x1b[K" + (nrow + 1 < T.h ? "\r\n" : "");    // (the last row: no newline, no scroll)
        nrow++;
    }

    // cells on the screen a string takes (UTF-8: a code point each)
    static int cols(const std::string &x)
    {
        int n = 0;
        for (unsigned char c : x)
            n += (c & 0xC0) != 0x80;
        return n;
    }

    // ...cut to n cells, at a code point
    static std::string fit(const std::string &x, int n)
    {
        size_t i = 0;
        for (int k = 0; i < x.size(); i++)
            if (((unsigned char)x[i] & 0xC0) != 0x80 && k++ == n)
                break;
        return x.substr(0, i);
    }

    // ONE SIDE OF THE STEREO METER (livetui.level_meter): dB over -48..0,
    // each cell coloured by where it sits (green to -18, amber to -6, red
    // above), the held peak a bright tick, the level in figures after it
    std::string level_meter(const char *lab, double db, double hold_db, int n) const
    {
        static const char *E8[8] = {" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉"};
        const double fl = -48.0;
        double f = std::max(0.0, std::min(1.0, (db - fl) / -fl)), hf = std::max(0.0, std::min(1.0, (hold_db - fl) / -fl));
        auto zone = [&](int c) {
            double top = fl + (-fl) * (c + 1) / n;
            return top <= -18.0 ? C("ok") : top <= -6.0 ? C("warn") : C("bad");
        };
        std::vector<std::string> cell(n);
        int full = (int)(f * n);
        for (int c = 0; c < n; c++)
            cell[c] = c < full ? zone(c) + "█"
                      : (c == full && f * n - full > 0.0) ? zone(c) + E8[std::min(7, (int)((f * n - full) * 8))]
                                                          : C("faint") + "·";
        int hi = std::min(n - 1, (int)(hf * n));
        if (hold_db > -90.0 && hi >= full)
            cell[hi] = zone(hi) + "\x1b[1m│\x1b[22m";
        std::string m = C("label") + lab + " ";
        for (auto &x : cell)
            m += x;
        char b[16];
        snprintf(b, sizeof b, db > -90.0 ? " %6.1f" : "   -inf", db);
        return m + "\x1b[0m" + b;
    }

    void rule(const std::string &name, bool here, const std::string &right = "", int to_pane = -1)
    {
        if (to_pane >= 0)
            hit(nrow, 0, 4 + cols(name), H_PANE, to_pane);
        int n = T.w - 6 - (int)name.size() - (int)right.size();
        std::string bar;
        for (int i = 0; i < std::max(2, n); i++)
            bar += "─";
        line((here ? C("accent") + "\x1b[1m" : C("dim")) + "── " + name + " " + "\x1b[0m" + C("dim") + bar
             + " " + right);
    }

    static std::string bar(double frac, int width)
    {
        frac = std::max(0.0, std::min(1.0, frac));
        int full = (int)(frac * width * 8 + 0.5);
        static const char *P[8] = {"", "▏", "▎", "▍", "▌", "▋", "▊", "▉"};
        std::string b;
        for (int i = 0; i < width; i++) {
            int k = full - 8 * i;
            b += k >= 8 ? "█" : k > 0 ? P[k] : "·";
        }
        return b;
    }

    std::string fmt_global(int i) const
    {
        char b[32];
        double v = H.g[i];
        if (!strcmp(GLOBAL_UNITS[i], "onoff"))
            return v >= 0.5 ? "on" : "off";
        if (!strcmp(GLOBAL_UNITS[i], "std"))
            return STD_NAMES[std::max(0, std::min(4, (int)std::lround(v)))];
        if (!strcmp(GLOBAL_UNITS[i], "room")) {
            int k = (int)v;
            return k >= 0 && k < (int)H.rooms.size() ? H.rooms[k] : "-";
        }
        if (i == 2)
            snprintf(b, sizeof b, "%.2f", v);
        else if (!strcmp(GLOBAL_UNITS[i], "cents"))             // (livetui.fmt's)
            snprintf(b, sizeof b, "%.0f c", v);
        else if (!strcmp(GLOBAL_UNITS[i], "%"))
            snprintf(b, sizeof b, "+%.0f%%", v * 100.0);
        else if (!strcmp(GLOBAL_UNITS[i], "bpm") && v <= 0.0)
            return "off";
        else if (!strcmp(GLOBAL_UNITS[i], "bpm"))
            snprintf(b, sizeof b, "%d bpm", (int)std::lround(v));
        else if (!strcmp(GLOBAL_UNITS[i], "ring") && v <= 0.0)
            return "no bell";
        else if (!strcmp(GLOBAL_UNITS[i], "ring"))
            snprintf(b, sizeof b, "bell /%d", (int)std::lround(v));
        else if (!strcmp(GLOBAL_UNITS[i], "dB"))
            snprintf(b, sizeof b, "%+.1f dB", v);
        else
            snprintf(b, sizeof b, "%.1f %s", v, GLOBAL_UNITS[i]);
        return b;
    }

    void draw()
    {
        T.size();
        out = "\x1b[H";
        nrow = 0;
        nlimit = std::max(1, T.h - 5);
        hits.clear();
        char b[256];
        // the header
        snprintf(b, sizeof b, "%.0f kHz · %d frames · %.1f ms", H.rate / 1000.0, H.frames, H.budget_ms);
        std::string lamp = s.rt ? C("ok") + "● RT18" : s.rt_dropped ? C("bad") + "● rt dropped"
                                                                          : C("dim") + "● rt off";
        const std::string pl = H.port_label ? H.port_label() : H.port;
        {                                       // (a tap on the inputs: I)
            const int px = 1 + cols("◆ tuning native  ") + cols(b) + 3;
            hit(nrow, px, px + cols(pl), H_KEY, 'I');
        }
        line(" " + C("accent") + "\x1b[1m◆ tuning native\x1b[0m  " + C("dim") + b + "   " + pl + "   " + lamp
             + (H.eastern.empty() ? std::string() : "   " + C("accent2") + "eastern " + H.eastern));
        // THE PARTS (livetui's PARTS pane): a row a part, its columns; the
        // selected cell in the selection's colour, a muted part dim
        if (H.parts)
            prows = H.parts();
        prow = std::max(0, std::min(prow, (int)prows.size() - 1));
        rule("PARTS", pane == P_PARTS, std::to_string(prows.size()) + (prows.size() == 1 ? " part" : " parts"), P_PARTS);
        {
            std::string hd = "   #  ";
            for (int c = 0; c < NPCOLS; c++) {
                std::string t = PCOLS[c];
                hd += t + std::string(std::max(1, PCOL_W[c] - cols(t)), ' ');
            }
            line(C("label") + hd);
        }
        for (size_t i = 0; i < prows.size(); i++) {
            const PartRow &r = prows[i];
            const bool sel = (int)i == prow, here = pane == P_PARTS && sel;
            std::string row = (here ? C("accent") : C("faint")) + (sel ? "▌" : " ") + "\x1b[0m ";
            snprintf(b, sizeof b, "%2zu", i + 1);
            row += (here ? C("accent") + "\x1b[1m" : C("dim")) + b + "\x1b[0m  ";
            hit(nrow, 0, 6, H_CELL, (int)i, -1);
            int x = 6;
            for (int c = 0; c < NPCOLS; c++) {
                std::string t = part_cell(r, c);
                t = fit(t, PCOL_W[c] - 1);
                std::string at = r.muted ? C("dim") : c == 0 ? C("accent2") : C("label");
                if (here && c == pcol)
                    at = C("sel");
                else if (here)
                    at += "\x1b[1m";
                row += at + t + std::string(PCOL_W[c] - cols(t), ' ') + "\x1b[0m";
                hit(nrow, x, x + PCOL_W[c], H_CELL, (int)i, c);
                x += PCOL_W[c];
            }
            if (r.muted)
                row += C("warn") + "muted";
            line(row);
        }
        line("   " + C("dim") + "room " + H.room
             + (H.reg_modes ? " · register " + std::to_string(H.reg_modes) + " string modes" : " · no register"));
        // the insertion effect: its type, the part on it or not, and why it
        // is not heard where it is refused here (x opens it)
        if (!s.efx.empty()) {
            EfxView v(s.efx);
            std::string nm = efx_name(v.msb, v.lsb), st;
            if (nm != "Thru") {
                st = efx_on(v) ? "   part on it" : "   part not on it";
                if (v.status == -3)
                    st += C("warn") + "   not native live: " + s.efx_why;
                else if (v.status != 0)
                    st += C("warn") + "   not built live";
            }
            line("   " + C("label") + "efx  " + C("value") + nm + "\x1b[0m" + C("dim") + st + C("dim") + "   (x)");
        }
        // the globals
        if (pane == P_SYNTH)
            draw_synth();
        if (pane == P_PARTS || pane == P_GLOBALS || (pane == P_ROUTES && T.h > 34)) {
            rule("GLOBALS", pane == P_GLOBALS, "←→ -+ adjust", P_GLOBALS);
            int half = (NGLOBALS + 1) / 2;
            for (int r = 0; r < half; r++) {
                std::string row;
                for (int c = 0; c < 2; c++) {
                    const int pos = r + c * half;
                    if (pos >= NGLOBALS)
                        continue;
                    const int i = GLOBAL_ORDER[pos];
                    bool here = pane == P_GLOBALS && grow == pos;
                    bool na = (i == 6 && !H.has_gpu) || (i == 7 && !H.has_room) || (i == 8 && H.rooms.empty());
                    double lo = GLOBAL_RANGE[i][0], hi = i == 8 ? (double)H.rooms.size() - 1.0 : GLOBAL_RANGE[i][1];
                    snprintf(b, sizeof b, "%-11s", GLOBAL_NAMES[i]);
                    std::string cell = std::string(here ? C("accent") + " ▸ \x1b[1m" : "   ") + "\x1b[0m"
                                       + (here ? C("accent") + "\x1b[1m" : C("label")) + b + "\x1b[0m";
                    snprintf(b, sizeof b, "%9s ", na ? "-" : fmt_global(i).c_str());
                    cell += C("value") + b + "\x1b[0m";
                    const int x0 = vcols(row), xb = x0 + vcols(cell);
                    hit(nrow, x0, xb, H_GLOBAL, i);         // (the name and value: select it)
                    hit(nrow, xb, xb + 12, H_GBAR, i);      // (the bar: set it where touched)
                    cell += (here ? C("accent") : C("accent2")) + bar(hi > lo ? (H.g[i] - lo) / (hi - lo) : 0.0, 12)
                            + "\x1b[0m";
                    row += cell + "   ";
                }
                line(row);
            }
        }
        // an organ's stops: drawn in the accent, the rest dim, each with its key
        if (!H.stop_names.empty() && pane != P_SYNTH) {
            rule("STOPS", false, stop_bank ? "rows 3-4: press a stop key" : "1-9  shift  ` then a key: rows 3-4");
            // THE STOPS AS BUTTONS (livetui.stops_grid): one width for every
            // stop, so the columns line up down the whole registration; each
            // key row starts its own line, wrapped where the screen ends; a
            // blank line between key rows where there is room
            std::vector<char> dr = H.drawn();
            auto key_of = [](size_t r, size_t i) {
                return i < 9 && r < 4 ? std::string(r >= 2 ? "`" : "") + (r % 2 ? STOP_SHIFTED[i] : STOP_DIGITS[i])
                                      : std::string();
            };
            const int X0 = 3, GAP = 1;
            int bw = 8;
            for (size_t r = 0; r < H.stop_rows.size(); r++)
                for (size_t i = 0; i < H.stop_rows[r].size(); i++) {
                    int ri = H.stop_rows[r][i];
                    std::string nm = ri >= 0 && ri < (int)H.stop_names.size() ? H.stop_names[ri] : "?";
                    std::string k = key_of(r, i);
                    bw = std::max(bw, cols(k) + (k.empty() ? 0 : 1) + cols(nm) + 2);
                }
            bw = std::min(bw, std::max(8, T.w - X0 - 2));
            const int per = std::max(1, (T.w - X0 - 2 + GAP) / (bw + GAP));
            // each key row's lines: [first, end) runs of its stops, a new one at
            // a voice's break or where the screen ends
            auto brk = [&](size_t r, size_t i) {
                return r < H.stop_breaks.size()
                       && std::find(H.stop_breaks[r].begin(), H.stop_breaks[r].end(), (int)i) != H.stop_breaks[r].end();
            };
            std::vector<std::vector<std::pair<size_t, size_t>>> runs(H.stop_rows.size());
            int nlines = 0;
            for (size_t r = 0; r < H.stop_rows.size(); r++) {
                size_t a = 0;
                for (size_t i = 1; i <= H.stop_rows[r].size(); i++)
                    if (i == H.stop_rows[r].size() || brk(r, i) || (int)(i - a) == per) {
                        runs[r].push_back(std::make_pair(a, i));
                        a = i;
                    }
                nlines += (int)runs[r].size();
            }
            // (the routes below keep their rows: blank lines only where they fit)
            const bool gaps = nrow + nlines + (int)H.stop_rows.size() - 1 + 3 + (int)H.routes.size() <= nlimit;
            for (size_t r = 0; r < H.stop_rows.size(); r++) {
                if (r && gaps)
                    line("");
                for (const auto &run : runs[r]) {
                    const size_t i0 = run.first;
                    std::string row(X0, ' ');
                    for (size_t i = i0; i < run.second; i++) {
                        int ri = H.stop_rows[r][i];
                        bool on = ri >= 0 && ri < (int)dr.size() && dr[ri];
                        std::string k = key_of(r, i);
                        std::string nm = ri >= 0 && ri < (int)H.stop_names.size() ? H.stop_names[ri] : "?";
                        std::string txt = " " + (k.empty() ? "" : k + " ") + nm;
                        while (cols(txt) < bw)
                            txt += " ";
                        const int x = X0 + (int)(i - i0) * (bw + GAP);
                        hit(nrow, x, x + bw, H_STOP, ri);
                        std::string face = on ? C("btnon") : C("btn");
                        if (!k.empty())                 // (the key dimmer on a raised button)
                            row += face + " " + (on ? "" : C("btnkey")) + k + face + txt.substr(1 + k.size());
                        else
                            row += face + txt;
                        row += "\x1b[0m" + std::string(GAP, ' ');
                    }
                    line(row);
                }
            }
        }
        // the routes
        // (the globals and the routes each in their pane; both where the screen has the room)
        if (pane == P_ROUTES || (pane != P_SYNTH && T.h > 34)) {
            // (livetui.draw_controls: the on-screen controls, then the routes)
            rule("CONTROLS & ROUTES", pane == P_ROUTES, "", P_ROUTES);
            const int nc = ctl_count();
            line(std::string(" ") + (pane == P_ROUTES ? C("accent2") : C("dim")) + "\x1b[1mon screen\x1b[0m     " + C("dim")
                 + (nc ? "a add   space toggle   -/+ step   enter value   b hotkey" : "none yet -- tab here and press a"));
            for (int i = 0; i < nc; i++) {
                const ScreenControl &c = (*H.controls)[i];
                const bool here = pane == P_ROUTES && crow == i;
                const char *lab = control_label(c.key);
                char hd[64];
                snprintf(hd, sizeof hd, "%s %-16s ch %-3s", here ? ">" : " ", lab ? lab : "?",
                         c.channel < 0 ? "all" : std::to_string(c.channel + 1).c_str());
                std::string row = std::string(here ? C("sel") : "") + hd + "\x1b[0m ";
                const std::string kind = control_kind(c.key);
                if (kind == "switch") {
                    const bool on = H.switch_on && H.switch_on(c.key, c.channel);
                    row += on ? C("ok") + "\x1b[1m\x1b[7m ON \x1b[0m" : C("dim") + " off\x1b[0m";
                } else if (kind == "selector") {
                    int pos = 0;
                    for (int q = 0; q < 7; q++)
                        if (c.value >= SCAN_STARTS[q])
                            pos = q;
                    for (int q = 0; q < 7; q++)
                        row += (here ? C("ok") : "") + (q == pos ? std::string("[") + SCAN_NAMES[q] + "]" : std::string(" ") + SCAN_NAMES[q] + " ")
                               + "\x1b[0m ";
                } else {
                    const double lo = kind == "bend" ? -8192 : 0, hi = kind == "bend" ? 8191 : 127;
                    char vb[16];
                    snprintf(vb, sizeof vb, "%5d ", c.value);
                    row += (here ? C("ok") : "") + vb + bar((c.value - lo) / (hi - lo), 16) + "\x1b[0m";
                }
                if (c.hotkey)
                    row += "   " + C("warn") + "key " + std::string(1, (char)c.hotkey) + "\x1b[0m";
                hit(nrow, 0, T.w, H_ROUTE, i);
                line(row);
            }
            line(std::string(" ") + (pane == P_ROUTES ? C("accent2") : C("dim")) + "\x1b[1mroutes\x1b[0m        " + C("dim")
                 + "r add   d delete  -- a route rewrites the keyboard's own controls before the engine sees them");
            if (H.routes.empty())
                line("   " + C("dim") + "none: every control means what it says");
            for (size_t i = 0; i < H.routes.size(); i++) {
                bool here = pane == P_ROUTES && crow == nc + (int)i;
                hit(nrow, 0, T.w, H_ROUTE, nc + (int)i);
                line(std::string(here ? C("accent") + " ▸ " : "   ") + "\x1b[0m" + (here ? C("value") : C("label"))
                     + describe(H.routes[i]));
            }
        }
        // THE HELP (?), over the panes: the bottom stays where it is
        if (help) {
            out = "\x1b[H";                 // (the panes drawn above: not shown)
            nrow = 0;
            hits.clear();                   // (a tap anywhere closes it)
            line(" " + C("accent") + "\x1b[1m◆ tuning native\x1b[0m  " + C("dim") + "keys   (any key closes)");
            line("");
            line("   tab / shift-tab   parts -> globals -> controls and routes -> synth");
            line("   up down (k j)     select a part, a global or a route");
            line("   parts: left right a column, - + change it (_ + coarse), enter pick or type a value");
            line("          a layer (same keys, same channel), s split, d delete, m mute");
            line("   globals: left right - +  adjust (_ + by five)");
            line("   S L               a preset saved, loaded (presets.json, live's)");
            line("   synth: up down a knob, - + turn (_ + coarse), space the patch's, 0 zero, D defaults,");
            line("          B the other layer, T the panel to the Messenger, F its firmware's chart");
            line("   N R               a scene (each channel's controls) saved, recalled (scenes.json)");
            line("   a                 an on-screen control: a pedal, a CC, the wheel, aftertouch, or MONO --");
            line("                     switched either way, mono stops what the channel holds (the spec's rule)");
            line("   space - + enter   toggle a switch (else back to its default), step it, type a value");
            line("   b                 bind it a hotkey -- it works from every pane");
            line("   r                 add a route (from, to, how, replace or keep, channel)");
            line("   d                 delete the selected control or route");
            line("   p                 the patch: every program, its variations, the drum sets; / to search");
            line("   t                 the tuner: every temperament live has; the patches built again in it");
            line("   E                 the EASTERN tuning: a raga system and Sa for every Indian voice");
            line("   x                 the insertion effect: the part on it, its type, parameters, controllers, sends");
            line("   I                 the MIDI inputs (or tap the port's name): enter turns each on or off -- several, merged");
            line("   P                 panic: every note off, now");
            line("   q                 quit (routes added here are kept beside the export)");
            line("");
            line("   the mouse or a touch: tap a pane's title, a global (drag it up or down, or");
            line("   the wheel, to change it; tap its bar to set it), a stop, a route, a key below;");
            line("   in a list, tap a row to take it");
        }
        // THE OUTPUT SECTION SITS ON THE BOTTOM (livetui.draw_meters), where it
        // does not move as the panes grow: the stereo meter, the peak, the CPU's
        // last seconds as a sparkline, the voices, the health -- then the
        // message line and the pane's keys
        nlimit = 1 << 30;
        while (nrow < T.h - 5)
            line("");
        rule("OUTPUT", false);
        auto now = std::chrono::steady_clock::now();
        double dt = std::chrono::duration<double>(now - last).count();
        last = now;
        for (int c = 0; c < 2; c++) {
            double db = s.peak[c] > 1e-9 ? 20.0 * log10(s.peak[c]) : -90.0;
            lev[c] = std::max(db, lev[c] - 20.0 * dt);                 // the fall: 20 dB a second
            if (lev[c] >= hold[c] || std::chrono::duration<double>(now - held_at[c]).count() > 1.5) {
                hold[c] = lev[c];                                       // the hold: 1.5 s at the top
                held_at[c] = now;
            }
        }
        const int mn = T.w >= 118 ? 26 : 12, px = mn + 13;
        const double pk = std::max(hold[0], hold[1]);
        // (the CPU: the block's worst against its budget, the worst of each 0.2 s)
        cpu_acc = std::max(cpu_acc, s.ms_max / std::max(H.budget_ms, 1e-9));
        if (++cpu_n >= 2) {
            cpu.push_back(cpu_acc);
            cpu_acc = 0.0;
            cpu_n = 0;
        }
        const int x = px + 15, sw = std::max(6, std::min(50, T.w - x - 33));
        while ((int)cpu.size() > sw)
            cpu.pop_front();
        static const char *SP[8] = {"▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"};
        std::string spark;
        for (double v : cpu)
            spark += (v < 0.5 ? C("ok") : v < 0.85 ? C("warn") : C("bad"))
                     + SP[std::max(0, std::min(7, (int)(std::min(1.0, v) * 7.999)))];
        auto pad = [&](std::string t, int to) {         // (to the column: fixed places, as livetui's)
            int n = cols(t);
            return t + std::string(std::max(1, to - n), ' ');
        };
        double mean = s.ms_n ? s.ms_sum / s.ms_n : 0.0, load = s.ms_max / std::max(H.budget_ms, 1e-9);
        snprintf(b, sizeof b, "%5.2f/%.2f ms  max %5.1f", mean, H.budget_ms, s.ms_max);
        std::string r1 = pad(" " + level_meter("L", lev[0], hold[0], mn), px + 1);
        r1 += C("label") + "peak " + (pk > -0.1 ? C("bad") : C("value"));
        char pb[16];
        snprintf(pb, sizeof pb, pk > -90.0 ? "%+.1f dB" : "  -inf", pk);
        r1 = pad(r1 + pb + "\x1b[0m", x + 1) + C("label") + "cpu " + spark + std::string(sw - (int)cpu.size() + 1, ' ')
             + (load > 0.85 ? C("bad") : C("value")) + b + "\x1b[0m  "
             + (s.eng[4] > 0.5 ? C("accent2") + "\x1b[1mgpu" : C("dim") + "cpu");
        line(r1);
        // the voices, and the health: each count not zero, amber (red, the ones
        // that lose notes) for 10 s after it rose, then grey (livetui's)
        std::string r2 = pad(" " + level_meter("R", lev[1], hold[1], mn), px + 1);
        r2 = pad(r2 + (pk > -0.1 ? C("bad") + "\x1b[1mCLIP\x1b[0m" : ""), x + 1);
        {                                       // (the count right-aligned to the slab's width: the text after it stays put)
            const int dw = snprintf(nullptr, 0, "%ld", H.slots);
            snprintf(b, sizeof b, "%*.0f/%ld", dw, s.eng[0], H.slots);
        }
        r2 += C("label") + "voices " + (s.eng[0] > 0.9 * H.slots ? C("bad") : C("value")) + b + "\x1b[0m";
        r2 = pad(r2, x + 23);
        struct Hk { const char *key, *lab; double v; bool worse; };
        const Hk hk[] = {{"under", "under", (double)s.underruns, false}, {"late", "late", (double)s.over, false},
                         {"drop", "drop", s.eng[3], true}, {"pshed", "shed", s.eng[2], false}};
        std::string items;
        bool fresh = false;
        for (const Hk &k : hk) {
            long v = (long)k.v;
            auto it = health.find(k.key);
            if (it == health.end())
                it = health.emplace(k.key, std::make_pair(0L, now - std::chrono::hours(1))).first;
            if (v > it->second.first)
                it->second = std::make_pair(v, now);
            else if (v < it->second.first)
                it->second.first = v;
            if (v) {
                bool recent = std::chrono::duration<double>(now - it->second.second).count() < 10.0;
                fresh = fresh || recent;
                items += (recent ? (k.worse ? C("bad") : C("warn")) : C("dim")) + k.lab + " " + std::to_string(v)
                         + "\x1b[0m  ";
            }
        }
        r2 += (fresh ? C("warn") : C("ok")) + "● \x1b[0m" + (items.empty() ? C("ok") + "clean\x1b[0m" : items);
        // (the native panel's own: the pedals, dim, after the health)
        snprintf(b, sizeof b, "   pedal %s sost %s mono %s bend %+.0f", s.eng[7] >= 127 ? "●" : s.eng[7] > 0 ? "◐" : "○",
                 s.eng[8] > 0.5 ? "●" : "○", s.eng[9] > 0.5 ? "●" : "○", s.eng[14]);
        line(r2 + C("dim") + b);
        // THE MESSAGE LINE: a build under way (its bar, as livetui's builder's),
        // else the newest message for its time
        long pd = 0, pt = 0;
        std::string pn;
        if (H.progress && H.progress(pd, pt, pn)) {
            const int W = 20;
            double fr = (double)pd / std::max(pt, 1L);
            std::string bar;
            for (int i = 0; i < W; i++)
                bar += i < (int)(fr * W) ? C("accent") + "█" : C("faint") + "─";
            snprintf(b, sizeof b, " %d%%", (int)(fr * 100));
            line(" " + C("accent") + "\x1b[1m◌ building " + pn + "\x1b[0m  " + bar + "\x1b[0m" + C("accent") + b);
        } else if (now < msg_until) {
            line(" " + C("ok") + msg);
        } else {
            line("");
        }
        // THE PANE'S KEYS (livetui.PANE_KEYS): always there, on the last line
        static const char *KP[][2] = {{"tab", "pane"}, {"↑↓", "part"}, {"←→", "column"}, {"-/+", "change"},
                                      {"⏎", "pick"}, {"a", "layer"}, {"s", "split"}, {"d", "del"}, {"m", "mute"},
                                      {"S/L", "preset"}, {"N/R", "scene"}, {"?", "help"}, {"q", "quit"}};
        static const char *KS[][2] = {{"tab", "pane"}, {"↑↓", "knob"}, {"-/+", "turn"}, {"space", "patch's"},
                                      {"0", "zero"}, {"D", "defaults"}, {"B", "layer"}, {"M", "Messenger"},
                                      {"T", "send"}, {"?", "help"}, {"q", "quit"}};
        static const char *K0[][2] = {{"tab", "pane"}, {"↑↓", "global"}, {"←→ -/+", "change"}, {"p", "patch"},
                                      {"t", "tuner"}, {"E", "eastern"}, {"x", "efx"}, {"P", "panic"}, {"?", "help"},
                                      {"q", "quit"}};
        static const char *K1[][2] = {{"tab", "pane"}, {"a", "control"}, {"r", "route"}, {"d", "del"}, {"space", "toggle"},
                                      {"-/+", "step"}, {"⏎", "value"}, {"b", "hotkey"}, {"?", "help"}, {"q", "quit"}};
        std::string kl = " ";
        int kx = 1;
        // WHAT A TAP ON A HINT PRESSES (livetui.HINT_CODES; q is not here: a
        // stray tap must not quit) -- a pair, each half its own
        auto codes = [](const std::string &k) -> std::vector<int> {
            if (k == "tab") return {9};
            if (k == "↑↓") return {1000, 1001};
            if (k == "←→ -/+") return {1003, 1002};
            if (k == "←→") return {1003, 1002};
            if (k == "-/+") return {'-', '='};
            if (k == "⏎") return {13};
            if (k == "S/L") return {'S', 'L'};
            if (k == "space") return {' '};
            if (k == "N/R") return {'N', 'R'};
            if (k == "q") return {};
            if (cols(k) == 1) return {(unsigned char)k[0]};
            return {};
        };
        auto add = [&](const char *k, const char *w) {
            int n = cols(k) + cols(w) + 4;
            if (kx + n >= T.w - 1)
                return;
            std::vector<int> cs = codes(k);
            const int y = nrow, kn = cols(k), end = kx + kn + 1 + cols(w);
            if (cs.size() == 1) {
                hit(y, kx, end, H_KEY, cs[0]);
            } else if (cs.size() == 2) {
                int half = std::max(1, kn / 2);
                hit(y, kx, kx + half, H_KEY, cs[0]);
                hit(y, kx + kn - half, end, H_KEY, cs[1]);
            }
            kl += C("accent") + k + " " + C("dim") + w + "\x1b[0m   ";
            kx += n;
        };
        if (pane == P_PARTS)
            for (auto &kv : KP)
                add(kv[0], kv[1]);
        else if (pane == P_SYNTH)
            for (auto &kv : KS)
                add(kv[0], kv[1]);
        else if (pane == P_GLOBALS)
            for (auto &kv : K0)
                add(kv[0], kv[1]);
        else
            for (auto &kv : K1)
                add(kv[0], kv[1]);
        line(kl);
        out += "\x1b[J";
        // THE SOUND CANVAS'S DISPLAY (livetui.draw_display): a box at the top
        // right while the module would show something, over what is there
        if (H.display && T.w >= 60 && T.h >= 14) {
            const std::vector<std::string> dl = H.display();
            if (!dl.empty()) {
                const int x = T.w - 20;
                auto at = [&](int r, const std::string &s) {
                    out += "\x1b[" + std::to_string(r) + ";" + std::to_string(x) + "H" + s + "\x1b[0m";
                };
                at(3, C("dim") + "┌─ SC display ─────┐");
                for (size_t i = 0; i < dl.size(); i++)
                    at(4 + (int)i, C("dim") + "│ " + C("value") + "\x1b[1m" + dl[i]
                                       + std::string(std::max(0, 16 - cols(dl[i])), ' ') + "\x1b[0m" + C("dim") + " │");
                at(4 + (int)dl.size(), C("dim") + "└──────────────────┘");
            }
        }
        fwrite(out.data(), 1, out.size(), stdout);
        fflush(stdout);
    }

    // -- questions --
    // a menu over the bottom of the screen: the index, or -1 (Esc, q) --
    // opened on start, the rows head marks headings (never chosen), a long
    // one scrolled
    int menu(const std::string &title, const std::vector<std::string> &items, int start = 0,
             const std::vector<char> &head = {})
    {
        const int n = (int)items.size();
        auto is_head = [&](int i) { return i < (int)head.size() && head[i]; };
        auto step = [&](int at, int d) {
            for (int j = at + d; j >= 0 && j < n; j += d)
                if (!is_head(j))
                    return j;
            return at;
        };
        int at = std::max(0, std::min(start, n - 1));
        if (is_head(at))
            at = step(at, 1);
        while (true) {
            T.size();
            int win = std::max(3, T.h - 4), top = std::max(0, std::min(at - win / 2, n - win));
            std::string m = "\x1b[H\x1b[2J " + C("accent") + "\x1b[1m" + title + "\x1b[0m\r\n";
            for (int i = top; i < std::min(n, top + win); i++)
                m += is_head(i) ? C("accent2") + "   " + items[i] + "\x1b[0m\x1b[K\r\n"
                                : std::string(i == at ? C("sel") + " ▸ " : "   ") + items[i] + "\x1b[0m\x1b[K\r\n";
            m += C("dim") + "\r\n   ↑↓ choose  enter take  esc back\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            if (c == KEY_MOUSE) {
                // A TAP ON A ROW takes it (Enter); on the foot, back; the wheel moves
                const Mouse &mm = T.m;
                if (mm.kind == Mouse::WHEEL) {
                    at = step(at, -mm.dy);
                } else if (mm.kind == Mouse::PRESS) {
                    int k = mm.y - 1;
                    if (k >= 0 && k < win && top + k < n && !is_head(top + k))
                        return top + k;
                    if (mm.y >= std::min(n - top, win) + 2)
                        return -1;
                }
                continue;
            }
            if (c == 1000 || c == 'k')
                at = step(at, -1);
            else if (c == 1001 || c == 'j')
                at = step(at, 1);
            else if (c == 10 || c == 13)
                return at;
            else if (c == 27 || c == 'q')
                return -1;
        }
    }

    // a line typed: the text, or false (Esc)
    bool prompt(const std::string &label, std::string &got)
    {
        got.clear();
        while (true) {
            std::string m = "\x1b[H\x1b[2J " + C("accent") + label + "\x1b[0m" + got + "\x1b[K";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            if (c == 27)
                return false;
            if (c == 10 || c == 13)
                return true;
            if ((c == 127 || c == 8) && !got.empty())
                got.pop_back();
            else if (c >= 32 && c < 127)
                got += (char)c;
        }
    }

    // a key pressed on the keyboard: (channel, note), or (-1, -1) (Esc)
    std::pair<int, int> learn_key()
    {
        H.learn(true);
        std::string m = "\x1b[H\x1b[2J " + C("accent") + "press the key on the keyboard" + "\x1b[0m" + C("dim")
                        + "   (esc: back)\x1b[0m";
        fwrite(m.data(), 1, m.size(), stdout);
        fflush(stdout);
        while (true) {
            auto got = H.learnt();
            if (got.first >= 0)
                return got;
            if (T.key(50) == 27) {
                H.learn(false);
                return std::make_pair(-1, -1);
            }
        }
    }

    // livetui.add_route, its questions in its order
    void add_route()
    {
        static const char *SOURCES[] = {"mod wheel", "pitch wheel, pushed up", "pitch wheel, pulled down",
                                        "pitch wheel, either way", "aftertouch", "sustain pedal (CC64)",
                                        "expression pedal (CC11)", "another CC, by number", "a key: press it",
                                        "a key: by name (C1, 36)"};
        int i = menu("route FROM", std::vector<std::string>(SOURCES, SOURCES + 10));
        if (i < 0)
            return;
        int src = 0, arg = 0, learned_ch = -1;
        std::string t;
        switch (i) {
        case 0: src = 0; arg = 1; break;
        case 1: src = 1; arg = 0; break;
        case 2: src = 1; arg = 1; break;
        case 3: src = 1; arg = 2; break;
        case 4: src = 2; break;
        case 5: src = 0; arg = 64; break;
        case 6: src = 0; arg = 11; break;
        case 7: {
            if (!prompt("CC number (0-119): ", t))
                return;
            int n = isdigit((unsigned char)(t.empty() ? 'x' : t[0])) ? atoi(t.c_str()) : -1;
            if (n < 0 || n > 119) {
                say("not a controller: " + t);
                return;
            }
            src = 0;
            arg = n;
            break;
        }
        case 8: {
            auto got = learn_key();
            if (got.first < 0)
                return;
            src = 3;
            arg = got.second;
            learned_ch = got.first;
            break;
        }
        default: {
            if (!prompt("key (C1, F#2, or 0-127): ", t))
                return;
            int n = parse_note(t);
            if (n < 0) {
                say("not a key: " + t);
                return;
            }
            src = 3;
            arg = n;
        }
        }
        std::vector<std::string> to;
        for (auto &c : CONTROLS)
            to.push_back(c.second);
        int j = menu("route TO", to);
        if (j < 0)
            return;
        int dst = CONTROLS[j].first;
        if ((src == 0 && arg == dst) || (src == 1 && dst == -1) || (src == 2 && dst == -2)) {
            say("a control routed to itself does nothing");
            return;
        }
        int latch = 0;
        if (src == 3 && control_switch(dst)) {
            int h = menu("the key", {"held while down (a pedal)", "toggle: each press flips it"});
            if (h < 0)
                return;
            latch = h == 1;
        }
        int k = menu("and the original",
                     {"replace it (the source stops doing what it did)", "keep it (the source does both)"});
        if (k < 0)
            return;
        int ch = -1;
        std::string q = learned_ch >= 0
                            ? "listen on channel (blank = " + std::to_string(learned_ch + 1) + ", 'all' = all): "
                            : "listen on channel (1-16, blank = all): ";
        if (!prompt(q, t))
            return;
        if (t.empty())
            ch = learned_ch;
        else if (t != "all") {
            int c = atoi(t.c_str());
            if (c < 1 || c > 16) {
                say("not a channel: " + t);
                return;
            }
            ch = c - 1;
        }
        std::array<int, 7> r = {src, arg, dst, k == 1, ch, latch, 1};
        H.add_route(r);
        H.routes.push_back(r);
        crow = ctl_count() + (int)H.routes.size() - 1;
        say("route " + describe(r));
    }

    // THE PATCH: one list of every program under its family's heading, then
    // the drum sets -- opened on the part's own, the arrows (page up/down,
    // home/end) through all of it, Enter takes one; "/" searches every
    // program and set by the words typed. A voice not native here is listed
    // dim and cannot be picked.
    void pick_patch()
    {
        static const char *FAM[16] = {"Piano", "Chromatic Percussion", "Organ", "Guitar", "Bass", "Strings",
                                      "Ensemble", "Brass", "Reed", "Pipe", "Synth Lead", "Synth Pad",
                                      "Synth Effects", "Ethnic", "Percussive", "Sound Effects"};
        // (the selected part's: the first's when there are no rows)
        const bool have_row = !prows.empty() && H.pick_part;
        const PartRow pr = have_row ? prows[prow] : PartRow();
        const int hp = have_row ? pr.program : H.program, hv = have_row ? pr.var : H.var;
        const bool hk = have_row ? pr.drums : H.kit;
        int here = (hk ? 128 : 0) + hp;
        for (size_t j = 0; j < H.vpv.size() && hv && !hk; j++)
            if (H.vpv[j][0] == hp && H.vpv[j][1] == hv)
                here = 256 + (int)j;
        auto nat = [&](int sp) {
            return sp >= 256 ? sp - 256 < (int)H.vnative.size() && H.vnative[sp - 256]
                             : sp >= 0 && sp < (int)H.native.size() && H.native[sp];
        };
        auto label = [&](int sp) {
            char b[200];
            if (sp >= 256) {                    // (a variation: under its program, its bank)
                const auto &pv = H.vpv[sp - 256];
                snprintf(b, sizeof b, "%s     %3d.%-3d  %-28s%s", sp == here ? "● " : "  ", pv[0], pv[1] & 127,
                         H.vnames[sp - 256].c_str(), nat(sp) ? "" : "  (not native)");
            } else {
                snprintf(b, sizeof b, "%s%s%3d  %-28s%s", sp == here ? "● " : "  ", sp >= 128 ? "set " : "",
                         sp & 127, sp < (int)H.names.size() ? H.names[sp].c_str() : "?", nat(sp) ? "" : "  (not native)");
            }
            return std::string(b);
        };
        // the whole list: (sp, or -1 a heading), its text
        std::vector<int> ids0;
        std::vector<std::string> rows0;
        for (int sp = 0; sp < 256; sp++) {
            bool kit = sp >= 128;
            if (kit && !(sp < (int)H.names.size() && !H.names[sp].empty()))
                continue;
            if ((!kit && sp % 8 == 0) || (kit && (ids0.empty() || ids0.back() < 128))) {
                ids0.push_back(-1);
                rows0.push_back(kit ? "── Drum sets" : std::string("── ") + FAM[sp / 8]);
            }
            ids0.push_back(sp);
            rows0.push_back(label(sp));
            const int stdm = std::max(0, std::min(4, (int)std::lround(H.g[13])));
            for (size_t j = 0; j < H.vpv.size() && !kit; j++)     // (its variations under it: the standard's, and GS's own)
                if (H.vpv[j][0] == sp && ((H.vpv[j][1] >> 7) == 0 || (H.vpv[j][1] >> 7) == stdm)) {
                    ids0.push_back(256 + (int)j);
                    rows0.push_back(label(256 + (int)j));
                }
        }
        pick_list(std::string("patch   (standard ") + STD_NAMES[std::max(0, std::min(4, (int)std::lround(H.g[13])))] + ")",
                  ids0, rows0, here, nat, [&](int id) {
            const std::string what = id >= 256 ? std::to_string(H.vpv[id - 256][0]) + "."
                                                 + std::to_string(H.vpv[id - 256][1] & 127) + " " + H.vnames[id - 256]
                                               : (id >= 128 ? "drum set " : "program ") + std::to_string(id & 127)
                                                 + " " + H.names[id];
            if (!nat(id)) {
                say(what + " is not native here");
                return false;
            }
            if (id != here) {
                if (have_row)
                    H.pick_part(pr.index, id);
                else
                    H.pick(id);
                say((have_row && prows.size() > 1 ? "part " + std::to_string(prow + 1) + ": " : std::string())
                    + "asked for " + what + " (built if new, then swapped in)");
            }
            return true;
        });
    }

    // THE TUNER (livetui's TUNER column, its picker): every tuner live has,
    // each with what it is for; Enter (a tap) asks for it -- the patches
    // built again in it on the builder, the bar while they build
    void pick_tuner()
    {
        std::vector<int> ids{-1};
        std::vector<std::string> rows{"── Western"};
        int here = 0;
        for (int i = 0; i < NTUNERS; i++) {
            if (!strncmp(TUNERS[i][0], "raga:", 5) && (i == 0 || strncmp(TUNERS[i - 1][0], "raga:", 5))) {
                ids.push_back(-1);
                rows.push_back("── Indian (a raga's intonation, Sa on C#)");
            }
            char b[200];
            snprintf(b, sizeof b, "%s%-22s %s", H.tuner == TUNERS[i][0] ? "● " : "  ", TUNERS[i][0], TUNERS[i][1]);
            ids.push_back(i);
            rows.push_back(b);
            if (H.tuner == TUNERS[i][0])
                here = i;
        }
        pick_list("tuner", ids, rows, here, [](int) { return true; }, [&](int id) {
            if (H.tuner != TUNERS[id][0]) {
                H.set_tuner(TUNERS[id][0]);
                say(std::string("tuner ") + TUNERS[id][0] + " -- every patch built again in it");
            }
            return true;
        });
    }

    // THE EASTERN TUNING (livetui.pick_eastern): a SYSTEM of swara positions
    // (theory, Bel's Todi, the 27 measured from Saraga), a RAGA (its swaras:
    // the meend's detents) and where SA sits -- every part whose voice is an
    // Indian instrument plays it, the rest keep their own tuner
    // THE MIDI INPUTS (livetui.pick_inputs): each plugged in, enter turns it
    // on or off -- several at once, merged -- the list read again each time
    // round (a device plugged in shows); Esc closes
    void pick_inputs()
    {
        int i = 0;
        for (;;) {
            const std::vector<std::pair<std::string, bool>> ins = H.inputs();
            std::vector<std::string> items;
            for (const auto &x : ins)
                items.push_back((x.second ? "[x] " : "[ ] ") + x.first);
            items.push_back("rescan");
            const int got = menu("MIDI inputs (enter: on / off)", items, std::min(i, (int)items.size() - 1));
            if (got < 0)
                return;
            i = got;
            if (got < (int)ins.size())
                say(H.input_toggle(got));
        }
    }

    void pick_eastern()
    {
        static const char *SW[12] = {"Sa", "re", "Re", "ga", "Ga", "Ma", "Ma'", "Pa", "dha", "Dha", "ni", "Ni"};
        static const char *KEYS[12] = {"c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"};
        std::vector<std::string> systems, ragas;
        for (int i = 0; nv_raga_system_name(i); i++)
            systems.push_back(nv_raga_system_name(i));
        std::stable_sort(systems.begin(), systems.end(), [](const std::string &a, const std::string &b) {
            bool sa = !a.compare(0, 7, "saraga_"), sb = !b.compare(0, 7, "saraga_");
            return sa != sb ? sb : a < b;
        });
        for (int i = 0; nv_raga_name(i, nullptr, nullptr); i++)
            if (strncmp(nv_raga_name(i, nullptr, nullptr), "saraga_", 7))
                ragas.push_back(nv_raga_name(i, nullptr, nullptr));
        std::sort(ragas.begin(), ragas.end());
        // ...where it stands now ("raga:<system>[/<raga>]@<key>")
        std::string cur = H.eastern, cs, cr;
        int ck = 1;
        if (!cur.compare(0, 5, "raga:")) {
            std::string b = cur.substr(5), k;
            size_t at = b.find('@');
            if (at != std::string::npos) {
                k = b.substr(at + 1, b.find(':', at) == std::string::npos ? std::string::npos : b.find(':', at) - at - 1);
                b = b.substr(0, at);
            }
            size_t sl = b.find('/');
            cs = b.substr(0, sl);
            cr = sl == std::string::npos ? "" : b.substr(sl + 1);
            for (int i = 0; i < 12; i++)
                if (k == KEYS[i])
                    ck = i;
        }
        std::vector<std::string> items{"off -- every part on its own tuner"};
        int start = 0;
        for (size_t i = 0; i < systems.size(); i++) {
            items.push_back(systems[i]);
            if (systems[i] == cs)
                start = (int)i + 1;
        }
        int pick = menu("Eastern tuning: system", items, start);
        if (pick < 0)
            return;
        if (pick == 0) {
            H.set_eastern("");
            say("Eastern tuning off: every part on its own tuner");
            return;
        }
        const std::string system = systems[pick - 1];
        bool own = false;
        for (int i = 0; nv_raga_name(i, nullptr, nullptr); i++)
            own = own || system == nv_raga_name(i, nullptr, nullptr);
        std::vector<std::string> ritems{own ? "(its own swaras)" : "(all twelve swaras)"};
        int rstart = 0;
        for (size_t q = 0; q < ragas.size(); q++) {
            int n = 0;
            const int *idx = nullptr;
            for (int i = 0; nv_raga_name(i, nullptr, nullptr); i++)
                if (ragas[q] == nv_raga_name(i, nullptr, nullptr))
                    nv_raga_name(i, &n, &idx);
            std::string row = ragas[q];
            row.resize(std::max<size_t>(row.size(), 10), ' ');
            for (int j = 0; j < n; j++)
                row += std::string(" ") + SW[idx[j]];
            ritems.push_back(row);
            if (ragas[q] == cr)
                rstart = (int)q + 1;
        }
        int rp = menu("Eastern tuning: raga (the meend's detents)", ritems, rstart);
        if (rp < 0)
            return;
        std::vector<std::string> kitems;
        for (const char *k : KEYS) {
            std::string u = k;
            for (char &ch : u)
                ch = (char)toupper((unsigned char)ch);
            kitems.push_back(u);
        }
        int kp = menu("Eastern tuning: Sa", kitems, ck);
        if (kp < 0)
            return;
        std::string spec = "raga:" + system + (rp ? "/" + ragas[rp - 1] : std::string()) + "@" + KEYS[kp];
        H.set_eastern(spec);
        say("Eastern tuning " + spec + ": the Indian voices' parts built again in it");
    }

    // A LIST TO PICK FROM (the patch's, the effect types'): rows under
    // headings (id -1), opened on here, the arrows (page up/down, home/end)
    // through it; "/" searches by the words typed; Enter hands the row's id to
    // accept, which closes the list by returning true. A row dim_not says
    // false of is drawn dim.
    void pick_list(const std::string &title, const std::vector<int> &ids0, const std::vector<std::string> &rows0,
                   int here, const std::function<bool(int)> &dim_not, const std::function<bool(int)> &accept)
    {
        int at = 0;
        for (size_t i = 0; i < ids0.size(); i++)
            if (ids0[i] == here)
                at = (int)i;
        std::string query;
        bool searching = false;
        while (true) {
            std::vector<int> ids;
            std::vector<std::string> rows;
            if (query.empty()) {
                ids = ids0;
                rows = rows0;
            } else {
                std::vector<std::string> ws;
                std::string w;
                for (char c : query + " ")
                    if (c == ' ') {
                        if (!w.empty())
                            ws.push_back(w);
                        w.clear();
                    } else {
                        w += (char)tolower((unsigned char)c);
                    }
                for (size_t i = 0; i < ids0.size(); i++) {
                    if (ids0[i] < 0)
                        continue;
                    std::string lo;
                    for (char c : rows0[i])
                        lo += (char)tolower((unsigned char)c);
                    bool ok = true;
                    for (auto &x : ws)
                        ok = ok && lo.find(x) != std::string::npos;
                    if (ok) {
                        ids.push_back(ids0[i]);
                        rows.push_back(rows0[i]);
                    }
                }
            }
            int n = (int)ids.size();
            at = std::max(0, std::min(at, n - 1));
            if (n && ids[at] < 0 && at + 1 < n)
                at++;                           // (never on a heading)
            T.size();
            int win = std::max(3, T.h - 4), top = std::max(0, std::min(at - win / 2, n - win));
            std::string m = "\x1b[H\x1b[2J " + C("accent") + "\x1b[1m" + title + "\x1b[0m" + C("dim") + "   "
                            + std::to_string(at + 1) + "/" + std::to_string(n) + "\x1b[0m\r\n";
            for (int i = top; i < std::min(n, top + win); i++) {
                if (ids[i] < 0) {
                    m += C("accent2") + rows[i] + "\x1b[0m\x1b[K\r\n";
                    continue;
                }
                m += std::string(i == at ? C("sel") + " ▸" : "  ") + (!dim_not(ids[i]) && i != at ? C("dim") : "")
                     + rows[i] + "\x1b[0m\x1b[K\r\n";
            }
            if (!n)
                m += C("dim") + "   (nothing matches)\x1b[0m\r\n";
            if (searching || !query.empty())
                m += C("accent") + "\x1b[1m /" + query + (searching ? "_" : "") + "\x1b[0m" + C("dim") + "   "
                     + std::to_string(n) + " found  esc clears\x1b[0m";
            else
                m += C("dim") + "   ↑↓ pgup pgdn  enter take  / search  esc cancel\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            if (c < 0)
                continue;
            if (c == KEY_MOUSE) {
                // A TAP ON A ROW takes it (Enter); on the foot, cancel; the wheel moves
                const Mouse &mm = T.m;
                if (mm.kind == Mouse::WHEEL && n) {
                    int j = std::max(0, std::min(n - 1, at - mm.dy));
                    while (j > 0 && j < n - 1 && ids[j] < 0)
                        j -= mm.dy;
                    if (ids[j] >= 0)
                        at = j;
                } else if (mm.kind == Mouse::PRESS) {
                    int k = mm.y - 1;
                    int shown = std::min(n - top, win);
                    if (k >= 0 && k < shown && ids[top + k] >= 0) {
                        at = top + k;
                        if (accept(ids[at]))
                            return;
                    } else if (mm.y >= shown + 1 + (n ? 0 : 1)) {
                        if (searching || !query.empty()) {
                            query.clear();
                            searching = false;
                        } else {
                            return;
                        }
                    }
                }
                continue;
            }
            if (searching && c >= 32 && c < 127 && c != '/') {
                query += (char)c;
                at = 0;
                continue;
            }
            if (searching && (c == 127 || c == 8)) {
                if (!query.empty())
                    query.pop_back();
                at = 0;
                continue;
            }
            auto step = [&](int d) {            // d rows, past headings
                int j = std::max(0, std::min(n - 1, at + d));
                while (j > 0 && j < n - 1 && ids[j] < 0)
                    j += d > 0 ? 1 : -1;
                if (ids.size() && ids[j] < 0)
                    j = at;
                at = j;
            };
            if (c == '/') {
                searching = true;
            } else if (c == 1000 || (!searching && c == 'k')) {
                step(-1);
            } else if (c == 1001 || (!searching && c == 'j')) {
                step(1);
            } else if (c == 1005) {
                step(-win);
            } else if (c == 1006) {
                step(win);
            } else if (c == 1007) {
                at = 0;
                step(0);
            } else if (c == 1008) {
                at = n - 1;
            } else if (c == 10 || c == 13) {
                if (n && ids[at] >= 0 && accept(ids[at]))
                    return;
            } else if (c == 27) {
                if (searching || !query.empty()) {
                    query.clear();              // first Esc: the search
                    searching = false;
                    at = 0;
                    for (size_t i = 0; i < ids0.size(); i++)
                        if (ids0[i] == here)
                            at = (int)i;
                } else {
                    return;
                }
            } else if (c == 'q' && !searching) {
                return;
            }
        }
    }

    // ---- THE ON-SCREEN CONTROLS (livetui's controls pane) ----
    int ctl_count() const { return H.controls ? (int)H.controls->size() : 0; }
    int ctl_rows() const { return ctl_count() + (int)H.routes.size(); }
    ScreenControl *ctl_sel()
    {
        return crow >= 0 && crow < ctl_count() ? &(*H.controls)[crow] : nullptr;
    }
    // livetui.send_control: set it, send it (every channel for 'all')
    void ctl_send(ScreenControl &c, int v)
    {
        const std::string kind = control_kind(c.key);
        c.value = kind == "bend" ? std::max(-8192, std::min(8191, v)) : std::max(0, std::min(127, v));
        if (H.control_send)
            H.control_send(c.key, c.value, c.channel);
    }
    // livetui.fire (a hotkey): a switch toggles; a continuous control jumps
    // between its default and full travel
    void ctl_fire(ScreenControl &c)
    {
        const std::string kind = control_kind(c.key);
        const char *lab = control_label(c.key);
        if (kind == "switch") {
            const bool on = !(H.switch_on && H.switch_on(c.key, c.channel));
            ctl_send(c, on ? 127 : 0);
            say(std::string(lab ? lab : "?") + (on ? " down" : " up"));
        } else {
            const int d = control_default(c.key), top = kind == "bend" ? 8191 : 127;
            ctl_send(c, c.value != d ? d : top);
            say(std::string(lab ? lab : "?") + " " + std::to_string(c.value));
        }
    }
    // a, b, space, enter, d (livetui's controls keys)
    void add_control()
    {
        if (!H.controls)
            return;
        std::vector<std::string> items;
        for (auto &c : CONTROLS) {
            char b[64];
            snprintf(b, sizeof b, "%-16s %s", c.second,
                     c.first >= 0 ? ("cc" + std::to_string(c.first)).c_str() : c.first == -3 ? "mono" : c.first == -1 ? "bend" : "pressure");
            items.push_back(b);
        }
        int i = menu("add an on-screen control", items);
        if (i < 0)
            return;
        std::string t;
        if (!prompt(std::string(CONTROLS[i].second) + " channel (1-16, blank = all): ", t))
            return;
        int ch = -1;
        if (!t.empty() && t != "all") {
            ch = atoi(t.c_str()) - 1;
            if (ch < 0 || ch > 15) {
                say("not a channel: " + t);
                return;
            }
        }
        // (it starts at its default and SENDS NOTHING: adding a control must
        // not change the sound until it is moved)
        H.controls->push_back(ScreenControl{CONTROLS[i].first, ch, control_default(CONTROLS[i].first), 0});
        crow = ctl_count() - 1;
        say(std::string("added ") + CONTROLS[i].second);
    }
    void ctl_bump(int delta, bool big)
    {
        ScreenControl *c = ctl_sel();
        if (!c)
            return;
        const std::string kind = control_kind(c->key);
        if (kind == "switch") {
            if ((delta > 0) != (H.switch_on && H.switch_on(c->key, c->channel)))
                ctl_fire(*c);
            return;
        }
        if (kind == "selector") {               // (its next position that way)
            int i = 0;
            for (int q = 0; q < 7; q++)
                if (c->value >= SCAN_STARTS[q])
                    i = q;
            i = std::max(0, std::min(6, i + (delta > 0 ? 1 : -1)));
            ctl_send(*c, SCAN_STARTS[i]);
            say(std::string(control_label(c->key)) + " " + SCAN_NAMES[i]);
            return;
        }
        ctl_send(*c, c->value + delta * (kind == "bend" ? 128 : 1) * (big ? 8 : 1));
    }
    void ctl_space()
    {
        ScreenControl *c = ctl_sel();
        if (!c)
            return;
        if (control_kind(c->key) == "switch") {
            ctl_fire(*c);
        } else {
            ctl_send(*c, control_default(c->key));
            say(std::string(control_label(c->key)) + " back to " + std::to_string(control_default(c->key)));
        }
    }
    void ctl_type()
    {
        ScreenControl *c = ctl_sel();
        if (!c)
            return;
        std::string t;
        const bool bend = control_kind(c->key) == "bend";
        if (!prompt(std::string(control_label(c->key)) + " (" + (bend ? "-8192..8191" : "0-127") + "): ", t) || t.empty())
            return;
        char *end = nullptr;
        long v = strtol(t.c_str(), &end, 10);
        if (!end || *end) {
            say("not a number: " + t);
            return;
        }
        ctl_send(*c, (int)v);
    }
    void bind_hotkey()
    {
        ScreenControl *c = ctl_sel();
        if (!c) {
            say("a hotkey belongs to an on-screen control");
            return;
        }
        std::string m = "\x1b[H\x1b[2J " + C("accent") + "press the key for " + control_label(c->key) + "\x1b[0m" + C("dim")
                        + "   (esc: none)\x1b[0m";
        fwrite(m.data(), 1, m.size(), stdout);
        fflush(stdout);
        int k;
        while ((k = T.key(1000)) < 0 || k == KEY_MOUSE) {
        }
        if (k == 27) {
            c->hotkey = 0;
            say("no hotkey");
            return;
        }
        if (k <= 0 || k > 127 || !strchr(HOTKEYS_FREE, k)) {
            say(std::string("that is the panel's own key; free: ") + HOTKEYS_FREE, 6);
            return;
        }
        for (auto &o : *H.controls)
            if (&o != c && o.hotkey == k) {
                say(std::string("'") + (char)k + "' is already " + control_label(o.key), 6);
                return;
            }
        c->hotkey = k;
        say(std::string("'") + (char)k + "' -> " + control_label(c->key));
    }
    void ctl_delete()
    {
        const int nc = ctl_count();
        if (crow < nc) {
            if (nc) {
                say(std::string("removed ") + control_label((*H.controls)[crow].key));
                H.controls->erase(H.controls->begin() + crow);
            }
        } else if (!H.routes.empty()) {
            int i = std::min(crow - nc, (int)H.routes.size() - 1);
            say("removed route " + describe(H.routes[i]));
            H.del_route(i);
            H.routes.erase(H.routes.begin() + i);
        }
        crow = std::max(0, std::min(crow, ctl_rows() - 1));
    }

    // ---- THE SYNTH PANE (livetui.draw_synth) ----
    // a centre-detent knob's bar (livetui.signed_bar): n cells either side of a mark
    static std::string signed_bar(double v, int n)
    {
        const double d = 2.0 * (std::max(0.0, std::min(1.0, v)) - 0.5);
        if (d >= 0.0)
            return std::string(n, ' ') + "│" + bar(d, n);
        std::string l;
        const int full = (int)std::lround(-d * n);
        for (int i = 0; i < n; i++)
            l += i >= n - full ? "█" : "·";
        return l + "│" + std::string(n, ' ');
    }
    const PartRow *synth_row() const { return prows.empty() ? nullptr : &prows[prow]; }
    void draw_synth()
    {
        rule("SYNTH", pane == P_SYNTH, "", P_SYNTH);
        const PartRow *r = synth_row();
        snl = r && H.synth_get ? H.synth_get(r->index, slayer, spn, sown) : 0;
        if (snl && slayer >= snl) {
            slayer = 0;
            snl = H.synth_get(r->index, slayer, spn, sown);
        }
        char b[200];
        // A TONEWHEEL ORGAN: its drive knob (livetui's, in draw_sound_controls)
        odrv = (!snl && r && !r->drums && H.drive_get) ? H.drive_get(r->index, odv) : 0;
        if (odrv == 1) {
            snprintf(b, sizeof b, "part %d, %s", prow + 1, r->name.c_str());
            line("  " + C("accent2") + "\x1b[1mORGAN\x1b[0m  " + C("dim") + b);
            snprintf(b, sizeof b, "%.2f", odv[0]);
            char vb[96];
            snprintf(vb, sizeof vb, "the valve before the rotors  (-/+ turn, space: the voice's %.2f)", odv[1]);
            line("  \x1b[7mdrive\x1b[0m " + C("ok") + bar(odv[0] / ORGAN_DRIVE_MAX, 9) + "\x1b[0m  \x1b[1m"
                 + (odv[2] >= 0.0 ? C("warn") : std::string()) + b + "\x1b[0m  " + C("dim") + vb);
            return;
        }
        if (!r || !snl) {
            line("   " + C("dim")
                 + (r && r->drums ? "a drum part answers only decay -- the synth panel is for a melodic part"
                                  : std::string("part ") + std::to_string(prow + 1) + (r ? ", " + r->name : "")
                                        + " is not a Moog: the synth panel turns a Moog's knobs"));
            return;
        }
        const bool layered = snl > 1;
        snprintf(b, sizeof b, "part %d, %s%s", prow + 1, r->name.c_str(), layered ? "  (layered -- B: the other)" : "");
        const bool reads = H.messenger_reads && H.messenger_reads();
        line("  " + C("accent2") + "\x1b[1m" + (layered ? std::string("MOOG MESSENGER ") + (slayer ? "B" : "A") : "MOOG MESSENGER")
             + "\x1b[0m  " + C("dim") + b + "   " + (reads ? C("ok") + "reads a Messenger on every part  (M: stop)"
                                                        : C("dim") + "M: read a Messenger's knobs"));
        const int half = (NSYNTH + 1) / 2, xw = std::max(40, T.w / 2);
        std::string last[2];
        for (int rr = 0; rr < half; rr++) {
            std::string row;
            int cx = 0;
            for (int c = 0; c < 2; c++) {
                const int i = rr + c * half;
                if (i >= NSYNTH)
                    continue;
                const int x = c ? xw : 2;
                if (cx < x) {
                    row += std::string(x - cx, ' ');
                    cx = x;
                }
                const std::string sec = SYNTH_KNOBS[i][0], kind = SYNTH_KNOBS[i][3];
                const int k = mk_index(SYNTH_KNOBS[i][1]);
                const bool here = i == srow, own = k >= 0 && sown[k];
                std::string t = sec != last[c] ? sec : "";
                last[c] = sec;
                row += "\x1b[1m" + t + "\x1b[0m" + std::string(7 - cols(t), ' ');
                char lab[16];
                snprintf(lab, sizeof lab, "%-10s", SYNTH_KNOBS[i][2]);
                row += std::string(here ? C("sel") : "") + lab + "\x1b[0m" + " ";
                const std::string v = k >= 0 ? synth_fmt(kind, spn[k], spn) : "-";
                char vb[32];
                snprintf(vb, sizeof vb, "%10s", fit(v, 10).c_str());
                row += std::string(here ? "\x1b[1m" : "") + (k >= 0 && sown[k] == 2 ? C("dim") : own ? C("warn") : C("value"))
                       + vb + "\x1b[0m" + (k >= 0 && sown[k] == 2 ? C("bad") + "*" + "\x1b[0m" : " ");
                hit(nrow, x, x + 29, H_KNOB, i);
                std::string bar_s;
                if (k >= 0 && synth_centred(kind))
                    bar_s = (here ? C("ok") : C("dim")) + signed_bar(spn[k], 4);
                else if (k >= 0 && synth_steps(kind).empty()) {
                    bar_s = (here ? C("ok") : C("dim")) + bar(spn[k], 9);
                    hit(nrow, x + 29, x + 38, H_KBAR, i);
                }
                row += bar_s + "\x1b[0m";
                cx = x + 29 + (bar_s.empty() ? 0 : 9);
                if (k >= 0 && synth_centred(kind))
                    cx = x + 29 + 9;
            }
            line(row);
        }
        // THE MESSENGER THIS PANEL SETS, if one is plugged in (--messenger-out)
        bool kept = false;
        for (int q = 0; q < 51; q++)
            kept = kept || sown[q] == 2;
        if (kept)
            line("  " + C("bad") + "*" + C("dim") + " the part's, not heard natively (an MF-104M under a moved pitch or shape) -- kept, and saved");
        const std::string ml = H.messenger_line ? H.messenger_line() : "";
        line("  " + (ml.empty() ? C("dim") + "no Messenger to set (nvlive --messenger-out=/dev/snd/midiCxDy)"
                                : C("ok") + ml));
    }

    // the selected knob (livetui's synth_*): its part, layer, index and kind
    bool synth_sel(const PartRow *&r, int &k, std::string &kind)
    {
        r = synth_row();
        if (!r || !snl || !H.synth_set)
            return false;
        k = mk_index(SYNTH_KNOBS[srow][1]);
        kind = SYNTH_KNOBS[srow][3];
        return k >= 0;
    }
    // AN ORGAN's DRIVE (livetui.ORGAN_DRIVE_MAX, organ_part): its knob's
    // reading, its travel, a twentieth a step (a quarter)
    static constexpr double ORGAN_DRIVE_MAX = 3.0;
    int odrv = 0;
    double odv[3] = {0.0, 0.0, -1.0};
    // - and + (livetui.synth_bump): a switch its next position, a knob by a hundredth (a tenth)
    void synth_bump(int delta, bool big)
    {
        if (odrv == 1 && H.drive_set) {        // (an organ's drive knob)
            const PartRow *r = synth_row();
            const double v = std::max(0.0, std::min(ORGAN_DRIVE_MAX, odv[0] + delta * (big ? 0.25 : 0.05)));
            if (r) {
                odv[0] = odv[2] = std::round(v * 100.0) / 100.0;
                H.drive_set(r->index, odv[0]);
            }
            return;
        }
        const PartRow *r;
        int k;
        std::string kind;
        if (!synth_sel(r, k, kind))
            return;
        double v = spn[k];
        std::vector<double> st = synth_steps(kind);
        if (!st.empty()) {
            size_t i = 0;
            for (size_t j = 0; j < st.size(); j++)
                if (fabs(st[j] - v) < fabs(st[i] - v))
                    i = j;
            v = st[std::max(0, std::min((int)st.size() - 1, (int)i + (delta > 0 ? 1 : -1)))];
        } else {
            v = std::max(0.0, std::min(1.0, v + delta * (big ? 0.1 : 0.01)));
        }
        H.synth_set(r->index, slayer, k, v);
        spn[k] = v;                             // (the part has it at once: the next press steps from it)
        sown[k] = 1;
    }
    // a knob set where its bar was touched (livetui.set_by_bar's kbar)
    void synth_by_bar(int i, double f)
    {
        srow = i;
        const PartRow *r;
        int k;
        std::string kind;
        if (!synth_sel(r, k, kind) || !synth_steps(kind).empty())
            return;
        const double v = std::max(0.0, std::min(1.0, f));
        H.synth_set(r->index, slayer, k, v);
        spn[k] = v;
        sown[k] = 1;
    }
    // space, 0, D, B, T, F, M (livetui's synth keys)
    void synth_key(int c)
    {
        if (odrv == 1 && c == ' ' && H.drive_set) {     // (an organ's drive: the voice's again)
            if (const PartRow *r = synth_row()) {
                H.drive_set(r->index, -1.0);
                odv[0] = odv[1];
                odv[2] = -1.0;
            }
            return;
        }
        const PartRow *r;
        int k;
        std::string kind;
        const std::string sec = SYNTH_KNOBS[srow][0], lab = SYNTH_KNOBS[srow][2];
        if (c == 'B') {
            if (snl < 2) {
                say("this voice is one Messenger -- no second layer");
            } else {
                slayer ^= 1;
                say(std::string("editing layer ") + (slayer ? "B  (the Messenger plugged in is layer A)" : "A"));
            }
            return;
        }
        if (c == 'F') {
            if (H.messenger_firmware) {
                const std::string fw = H.messenger_firmware();
                say("the Messenger's chart: firmware " + fw + " (SUB WAVE on CC" + (fw == "pre-1.0.7" ? "11" : "71") + ")");
            }
            return;
        }
        if (c == 'M') {                         // livetui.synth_hardware: nvlive's for every part at once
            if (H.messenger_read && H.messenger_reads) {
                const bool on = !H.messenger_reads();
                H.messenger_read(on);
                say(on ? "every part reads a Messenger's knobs (its chart) -- M: General MIDI CCs again"
                       : "General MIDI CCs again");
            }
            return;
        }
        if (!synth_sel(r, k, kind))
            return;
        if (c == ' ') {                         // the patch's setting (livetui.synth_reset)
            H.synth_forget(r->index, slayer, k);
            sown[k] = 0;
        } else if (c == '0') {                  // its zero (livetui.synth_zero)
            double v;
            if (synth_centred(kind))
                v = 0.5;
            else if (kind == "onoff")
                v = 0.0;
            else if (!synth_steps(kind).empty()) {
                say(sec + " " + lab + " has no zero");
                return;
            } else
                v = 0.0;
            H.synth_set(r->index, slayer, k, v);
            spn[k] = v;
            sown[k] = 1;
        } else if (c == 'D') {                  // every knob on this layer back to the patch (livetui.synth_defaults)
            int n = 0;
            for (int q = 0; q < 51; q++)
                if (sown[q]) {
                    H.synth_forget(r->index, slayer, q);
                    sown[q] = 0;
                    n++;
                }
            say("part " + std::to_string(prow + 1) + (snl > 1 ? std::string(" layer ") + (slayer ? "B" : "A") : "") + ": "
                + std::to_string(n) + (n == 1 ? " knob" : " knobs") + " back to the patch");
        } else if (c == 'T') {                  // the whole panel to the Messenger (livetui.synth_send)
            say(H.synth_send && H.synth_send(r->index) ? "part " + std::to_string(prow + 1) + ": its panel to the Messenger"
                                                       : "no Messenger to set (nvlive --messenger-out=/dev/snd/midiCxDy)");
        }
    }

    // ---- THE PARTS (livetui's PARTS pane) ----
    // a cell's text (livetui.cell)
    std::string part_cell(const PartRow &r, int c) const
    {
        char b[160];
        switch (c) {
        case 0:
            if (r.drums)
                return "-- " + r.name + " kit";
            if (r.var)
                snprintf(b, sizeof b, "%3d.%d %s", r.program, r.var & 127, r.name.c_str());
            else
                snprintf(b, sizeof b, "%3d %s", r.program, r.name.c_str());
            return b;
        case 1: return r.channel < 0 ? "all" : std::to_string(r.channel + 1);
        case 2: return key_name(r.lo);
        case 3: return key_name(r.hi);
        case 4: snprintf(b, sizeof b, "%+d", r.tr); return b;
        case 5: snprintf(b, sizeof b, "%+.1f dB", r.level); return b;
        case 6:
            // a part sounding the rig's Eastern tuning says so (E sets it: livetui's)
            if (H.east_part && H.east_part(r.program, r.drums)) {
                std::string s = H.eastern.substr(H.eastern.compare(0, 5, "raga:") ? 0 : 5);
                return "E " + s.substr(0, s.find('@'));
            }
            return H.tuner;
        case 7: return r.touch_fixed ? "fixed" : "vel";
        case 8: {
            if (r.index != 0 || H.stop_names.empty() || !H.drawn)
                return "-";
            std::vector<char> dr = H.drawn();
            std::string t;
            for (const auto &row : H.stop_rows)
                for (int ri : row)
                    if (ri >= 0 && ri < (int)dr.size() && dr[ri])
                        t += (t.empty() ? "" : " ") + H.stop_names[ri];
            return t.empty() ? "none" : t;
        }
        case 9: {                               // (livetui: on, some of its channels, none)
            if (s.efx.empty())
                return "-";
            EfxView v(s.efx);
            int on = 0, n = 0;
            for (int ch = 0; ch < 16; ch++)
                if (r.channel == ch || (r.channel < 0 && !(r.index == 0 && ch == 9 && has_drums_beside()))) {
                    n++;
                    on += std::find(v.parts.begin(), v.parts.end(), ch) != v.parts.end();
                }
            return !on ? "-" : on == n ? "on" : "some";
        }
        }
        return "";
    }
    bool has_drums_beside() const
    {
        for (const auto &r : prows)
            if (r.drums && r.channel == 9)
                return true;
        return false;
    }

    // - and + on the selected cell (livetui.adjust): the next program (or set,
    // past those not native here), a channel, the keys (by twelve with _/+),
    // transpose, level (3 dB), the next tuner
    void part_adjust(int delta, bool big)
    {
        if (prows.empty() || !H.part_set)
            return;
        PartRow r = prows[prow];
        const int step = delta * (big && pcol >= 2 && pcol <= 4 ? 12 : 1);
        switch (pcol) {
        case 0: {
            if (!H.pick_part)
                return;
            const int base = r.drums ? 128 : 0;
            int sp = base + r.program;
            for (int k = 0; k < (big ? 8 : 1); k++) {
                int q = sp;
                do
                    q += delta > 0 ? 1 : -1;
                while (q >= base && q < base + 128 && !(q < (int)H.native.size() && H.native[q]));
                if (q < base || q >= base + 128)
                    break;
                sp = q;
            }
            if (sp != base + r.program) {
                H.pick_part(r.index, sp);
                say("part " + std::to_string(prow + 1) + ": " + (r.drums ? "set " : "program ") + std::to_string(sp & 127)
                    + " " + (sp < (int)H.names.size() ? H.names[sp] : "") + " (built if new, then swapped in)");
            }
            return;
        }
        case 1: {                               // (0 is every channel: what one keyboard wants)
            int c = r.channel < 0 ? 0 : r.channel + 1;
            c = std::max(0, std::min(16, c + delta));
            r.channel = c == 0 ? -1 : c - 1;
            break;
        }
        case 2: r.lo = std::max(0, std::min(r.hi, r.lo + step)); break;
        case 3: r.hi = std::max(r.lo, std::min(127, r.hi + step)); break;
        case 4: r.tr = std::max(-48, std::min(48, r.tr + step)); break;
        case 5: r.level = std::max(LEVEL_DB_MIN, std::min(LEVEL_DB_MAX, r.level + delta * (big ? 3.0 : 0.5))); break;
        case 6: {
            if (!H.set_tuner)
                return;
            int k = 0;
            for (int i = 0; i < NTUNERS; i++)
                if (H.tuner == TUNERS[i][0])
                    k = i;
            k = std::max(0, std::min(NTUNERS - 1, k + delta));
            if (H.tuner != TUNERS[k][0]) {
                H.set_tuner(TUNERS[k][0]);
                say(std::string("tuner ") + TUNERS[k][0] + " -- every patch built again in it");
            }
            return;
        }
        case 7: part_touch_toggle(r); return;
        case 8: say("stops: the buttons below, or their keys"); return;
        default: say("efx: x opens the insertion effect"); return;
        }
        H.part_set(r.index, r.channel, r.lo, r.hi, r.tr, r.level, r.muted);
        prows[prow] = r;                        // (so presses within a frame add up)
    }

    // FIXED TOUCH, on any part (livetui.toggle_touch): on, velocity does not
    // set its level; off, it does -- each patch starting its own way
    void part_touch_toggle(const PartRow &r)
    {
        if (!H.part_touch)
            return;
        const bool now = !r.touch_fixed;
        H.part_touch(r.index, now);
        prows[prow].touch_fixed = now;
        say("part " + std::to_string(prow + 1) + ": " + (now ? "fixed touch -- the key sets no level" : "velocity sets the level"));
    }

    // Enter on the selected cell: a picker (patch, tuner, the effect), or a
    // value typed (livetui's: every column answers Enter with something)
    void part_enter()
    {
        if (prows.empty())
            return;
        PartRow r = prows[prow];
        std::string t;
        switch (pcol) {
        case 0: if (H.pick || H.pick_part) pick_patch(); return;
        case 6: if (H.set_tuner) pick_tuner(); return;
        case 7: part_touch_toggle(r); return;
        case 8: say("stops: the buttons below, or their keys"); return;
        case 9: pick_efx(); return;
        case 1:
            if (!prompt("channel (1-16, or all): ", t))
                return;
            if (t == "all" || t.empty()) {
                r.channel = -1;
            } else {
                int c = atoi(t.c_str());
                if (c < 1 || c > 16) {
                    say("not a channel: " + t);
                    return;
                }
                r.channel = c - 1;
            }
            break;
        case 2:
        case 3: {
            if (!prompt(std::string(pcol == 2 ? "lowest" : "highest") + " key (C1, F#2, or 0-127): ", t))
                return;
            int n = parse_note(t);
            if (n < 0) {
                say("not a key: " + t);
                return;
            }
            if (pcol == 2)
                r.lo = std::min(n, r.hi);
            else
                r.hi = std::max(n, r.lo);
            break;
        }
        case 4:
            if (!prompt("transpose (semitones, -48 to 48): ", t))
                return;
            r.tr = std::max(-48, std::min(48, atoi(t.c_str())));
            break;
        case 5:
            if (!prompt("level (dB, -60 to 24): ", t))
                return;
            r.level = std::max(LEVEL_DB_MIN, std::min(LEVEL_DB_MAX, atof(t.c_str())));
            break;
        }
        H.part_set(r.index, r.channel, r.lo, r.hi, r.tr, r.level, r.muted);
        prows[prow] = r;
    }

    // S, L, N, R (livetui's): a preset saved and loaded, a scene saved and recalled
    void presets_key(int c)
    {
        std::string t;
        if (c == 'S' && H.save_preset) {
            if (prompt("save preset as: ", t) && !t.empty())
                say(H.save_preset(t));
        } else if (c == 'N' && H.save_scene) {
            if (prompt("save scene as: ", t) && !t.empty())
                say(H.save_scene(t));
        } else if ((c == 'L' && H.load_preset) || (c == 'R' && H.recall_scene)) {
            std::vector<std::string> ns = c == 'L' ? H.preset_names() : H.scene_names();
            if (ns.empty()) {
                say(c == 'L' ? "no presets in presets.json yet -- S saves one" : "no scenes in scenes.json yet -- N saves one");
                return;
            }
            int i = menu(c == 'L' ? "load preset" : "recall scene", ns);
            if (i >= 0) {
                say(c == 'L' ? H.load_preset(ns[i]) : H.recall_scene(ns[i]));
                if (c == 'L')
                    prow = 0;
            }
        }
    }

    // a, s, d, m (livetui's): layer, split, delete, mute
    void part_key(int c)
    {
        if (prows.empty())
            return;
        const PartRow r = prows[prow];
        std::string why;
        if (c == 'a' && H.part_layer) {
            if (H.part_layer(r.index)) {
                prow = (int)prows.size();
                say("layered -- same keys, same channel; change its patch or zone");
            }
        } else if (c == 's' && H.part_split) {
            if (H.part_split(r.index, why)) {
                say("split at " + key_name((r.lo + r.hi) / 2) + " -- now change the upper part's patch");
                prow = (int)prows.size();
            } else if (!why.empty()) {
                say(why);
            }
        } else if (c == 'd' && H.part_delete) {
            if (prows.size() <= 1)
                say("the last part cannot be removed");
            else if (H.part_delete(r.index, why))
                prow = std::max(0, prow - 1);
            else if (!why.empty())
                say(why);
        } else if (c == 'm' && H.part_set) {
            H.part_set(r.index, r.channel, r.lo, r.hi, r.tr, r.level, !r.muted);
            prows[prow].muted = !r.muted;
            say(std::string("part ") + std::to_string(prow + 1) + (r.muted ? " unmuted" : " muted"));
        }
    }

    // ---- THE INSERTION EFFECT (livetui.pick_efx) ----
    std::string efx_name(int msb, int lsb) const
    {
        if (!msb && !lsb)
            return "Thru";
        for (const auto &t : H.efx_types)
            if (t.msb == msb && t.lsb == lsb)
                return t.name;
        char b[32];
        snprintf(b, sizeof b, "type %02X %02X", msb, lsb);
        return b;
    }
    int efx_num(int msb, int lsb) const
    {
        for (const auto &t : H.efx_types)
            if (t.msb == msb && t.lsb == lsb)
                return t.num;
        return 0;
    }
    // the channels the part listens on (livetui.efx_channels)
    std::vector<int> efx_channels() const
    {
        std::vector<int> c;
        for (int ch = 0; ch < 16; ch++)
            if (H.channel < 0 || H.channel == ch)
                c.push_back(ch);
        return c;
    }
    bool efx_on(const EfxView &v) const
    {
        for (int ch : efx_channels())
            if (std::find(v.parts.begin(), v.parts.end(), ch) == v.parts.end())
                return false;
        return true;
    }
    // the raw value a parameter stands at: the one set, else the one in
    // effect, moved by its controller (gsefx.controlled) where it has one
    int efx_value(const EfxView &v, const Host::EfxParam &p) const
    {
        int x = p.n >= 1 && p.n <= 20 && v.p[p.n] >= 0 ? v.p[p.n] : p.fresh;
        if (!p.read || p.mark == '-' || (!v.ctl[0] && !v.ctl[2]))
            return x;
        int which = p.mark == '+' ? 0 : 2, src = v.ctl[which];
        if (!src)
            return x;
        double dep = std::max(-1.0, std::min(1.0, (v.ctl[which + 1] - 0x40) / 63.0));
        auto it = v.cv.find(src);
        double cv = it != v.cv.end() ? it->second : src == EFX_SRC_BEND ? 64 : 0;
        int lo = *std::min_element(p.vals.begin(), p.vals.end()), hi = *std::max_element(p.vals.begin(), p.vals.end());
        double y = std::max((double)lo, std::min((double)hi, x + (hi - lo) * (cv / 127.0) * dep));
        if ((int)p.vals.size() == hi - lo + 1)
            return (int)nearbyint(y);
        int best = p.vals[0];
        for (int r : p.vals)
            if (fabs(r - y) < fabs(best - y))
                best = r;
        return best;
    }
    static std::string efx_printed(const Host::EfxParam &p, int x)
    {
        size_t k = 0;
        for (size_t i = 0; i < p.vals.size(); i++)
            if (abs(p.vals[i] - x) < abs(p.vals[k] - x))
                k = i;
        return p.shown.empty() ? std::to_string(x) : p.shown[k];
    }
    static std::string src_label(int code)
    {
        return !code ? "off" : code <= 95 ? "CC" + std::to_string(code) : code == EFX_SRC_CAF ? "aftertouch" : "bend";
    }
    // a setting sent, then the state seen back (live's _efx_wait: the audio
    // thread applies it as hardware's message, the panel reads it after)
    void efx_send(char kind, int a, int b)
    {
        long rev = s.efx_rev;
        H.efx_send(efx_message(kind, a, b));
        auto t0 = std::chrono::steady_clock::now();
        while (std::chrono::steady_clock::now() - t0 < std::chrono::milliseconds(100)) {
            Snap n = H.take();
            s.efx = n.efx;
            s.efx_why = n.efx_why;
            s.efx_rev = n.efx_rev;
            if (s.efx_rev != rev)
                break;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }

    void pick_efx()
    {
        if (!H.efx_send || s.efx.empty()) {
            say("the export has no insertion effect");
            return;
        }
        int i = 0;
        while (true) {
            EfxView v(s.efx);
            const std::string name = efx_name(v.msb, v.lsb);
            const int num = efx_num(v.msb, v.lsb);
            const bool on = efx_on(v);
            std::vector<std::string> rows;
            std::vector<char> head;
            std::vector<std::array<int, 3>> what;           // (kind, a, b): 0 part, 1 type, 2 param, 3 ctl, 4 send
            char b[160];
            auto add = [&](const std::string &r, int k, int a = 0, int c = 0) {
                rows.push_back(r);
                head.push_back(k < 0);
                what.push_back({k, a, c});
            };
            add(std::string("part on the EFX (") + (H.channel < 0 ? "all channels" : "channel " + std::to_string(H.channel + 1))
                    + "):  " + (on ? "yes" : "no"), 0);
            if (num)
                snprintf(b, sizeof b, "type:  %02d %s", num, name.c_str());
            else
                snprintf(b, sizeof b, "type:  %s", name.c_str());
            add(b, 1);
            auto pit = H.efx_params.find(std::make_pair(v.msb, v.lsb));
            if (name != "Thru" && pit != H.efx_params.end()) {
                const auto &ps = pit->second;
                add("-- parameters", -1);
                for (size_t q = 0; q < ps.size(); q++) {
                    snprintf(b, sizeof b, "%-16.16s %s", ps[q].name.c_str(), efx_printed(ps[q], efx_value(v, ps[q])).c_str());
                    add(b, 2, (int)q);
                }
                add("-- its controllers (a knob the instrument does not use)", -1);
                for (int which = 1; which <= 2; which++) {
                    char mk = which == 1 ? '+' : '#';
                    std::string pname = "-";
                    for (const auto &p : ps)
                        if (p.mark == mk)
                            pname = p.name;
                    int src = v.ctl[which == 1 ? 0 : 2], dep = v.ctl[which == 1 ? 1 : 3];
                    std::string desc = src ? src_label(src) + ", " : "off";
                    if (src) {
                        snprintf(b, sizeof b, "%+d%%", (int)nearbyint(std::max(-1.0, std::min(1.0, (dep - 0x40) / 63.0)) * 100));
                        desc += b;
                    }
                    snprintf(b, sizeof b, "%c %-13.13s %s", mk, pname.c_str(), desc.c_str());
                    add(b, 3, which);
                }
                add("-- sends from the EFX", -1);
                static const char *SN[3] = {"to reverb", "to chorus", "to delay"};
                for (int q = 0; q < 3; q++) {
                    snprintf(b, sizeof b, "%-16s %d", SN[q], v.snd[q]);
                    add(b, 4, q);
                }
            }
            std::string title = "insertion effect";
            if (v.status == -3)
                title += "   (not native live: " + s.efx_why + ")";
            else if (name != "Thru" && v.status != 0)
                title += "   (not built live)";
            int got = menu(title, rows, i, head);
            if (got < 0)
                return;
            i = got;
            const auto &w = what[got];
            if (w[0] == 0) {
                for (int ch : efx_channels())
                    efx_send('c', ch, !on);
            } else if (w[0] == 1) {
                pick_efx_type(v);
            } else if (w[0] == 2) {
                const auto &p = pit->second[w[1]];
                edit_efx(p.name, p.vals, [&](int x) { return efx_printed(p, x); }, efx_value(v, p),
                         [&](int x) { efx_send('p', p.n, x); });
            } else if (w[0] == 3) {
                std::string pname = "-";
                for (const auto &p : pit->second)
                    if (p.mark == (w[1] == 1 ? '+' : '#'))
                        pname = p.name;
                pick_efx_ctl(v, w[1], pname);
            } else if (w[0] == 4) {
                static const char *SN[3] = {"to reverb", "to chorus", "to delay"};
                std::vector<int> all(128);
                for (int x = 0; x < 128; x++)
                    all[x] = x;
                edit_efx(SN[w[1]], all, [](int x) { return std::to_string(x); }, v.snd[w[1]],
                         [&](int x) { efx_send('s', EFX_SEND[w[1]], x); });
            }
        }
    }

    // the type, under Roland's families; "/" searches every type by name
    void pick_efx_type(const EfxView &v)
    {
        std::vector<int> ids{-1, 0};
        std::vector<std::string> rows{"── 00", "  00 Thru"};
        for (const auto &c : H.efx_cats) {
            ids.push_back(-1);
            rows.push_back("── " + c.name);
            for (size_t j = 0; j < H.efx_types.size(); j++) {
                const auto &t = H.efx_types[j];
                if (t.num < c.a || t.num > c.b)
                    continue;
                char b[120];
                snprintf(b, sizeof b, "%s%02d %s   (%s)", t.msb == v.msb && t.lsb == v.lsb ? "● " : "  ", t.num,
                         t.name.c_str(), c.name.c_str());
                ids.push_back(1 + (int)j);
                rows.push_back(b);
            }
        }
        int here = 0;
        for (size_t j = 0; j < H.efx_types.size(); j++)
            if (H.efx_types[j].msb == v.msb && H.efx_types[j].lsb == v.lsb)
                here = 1 + (int)j;
        pick_list("insertion effect type", ids, rows, here, [](int) { return true; }, [&](int id) {
            int msb = id ? H.efx_types[id - 1].msb : 0, lsb = id ? H.efx_types[id - 1].lsb : 0;
            if (msb != v.msb || lsb != v.lsb) {
                efx_send('t', msb, lsb);
                say("EFX: " + efx_name(msb, lsb));
            }
            return true;
        });
    }

    // an effect controller (livetui.pick_efx_ctl): what moves its parameter
    // -- learnt (move the knob, pedal or wheel), or picked -- and how far
    void pick_efx_ctl(const EfxView &v, int which, const std::string &pname)
    {
        const int sa = which == 1 ? EFX_CTL_SRC1 : EFX_CTL_SRC2, da = which == 1 ? EFX_CTL_DEP1 : EFX_CTL_DEP2;
        const int cur = v.ctl[which == 1 ? 0 : 2], dep = v.ctl[which == 1 ? 1 : 3];
        std::vector<std::string> opts{"learn: move a knob, pedal or wheel now", "off"};
        std::vector<int> codes{-1, 0};
        for (int c = 1; c <= 95; c++) {
            opts.push_back("CC" + std::to_string(c));
            codes.push_back(c);
        }
        opts.push_back("aftertouch");
        codes.push_back(EFX_SRC_CAF);
        opts.push_back("bend");
        codes.push_back(EFX_SRC_BEND);
        char b[64];
        snprintf(b, sizeof b, "depth: %+d%%", (int)nearbyint((dep - 64) / 63.0 * 100));
        opts.push_back(b);
        codes.push_back(-2);
        int start = 1;
        for (size_t j = 0; j < codes.size(); j++)
            if (codes[j] == cur)
                start = (int)j;
        int got = menu(pname + " moved by", opts, start);
        if (got < 0)
            return;
        int code = codes[got];
        if (code == -2) {
            std::vector<int> all(128);
            for (int x = 0; x < 128; x++)
                all[x] = x;
            edit_efx("depth", all, [](int x) {
                char t[16];
                snprintf(t, sizeof t, "%+d%%", (int)nearbyint((x - 64) / 63.0 * 100));
                return std::string(t);
            }, dep, [&](int x) { efx_send('s', da, x); });
            return;
        }
        if (code == -1) {                               // learn
            long long t0 = std::chrono::duration_cast<std::chrono::nanoseconds>(
                               std::chrono::steady_clock::now().time_since_epoch()).count();
            std::string m = "\x1b[H\x1b[2J " + C("accent") + "move the knob, pedal or wheel for " + pname + "\x1b[0m"
                            + C("dim") + "   (esc: back)\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            auto until = std::chrono::steady_clock::now() + std::chrono::seconds(8);
            while (code < 0 && std::chrono::steady_clock::now() < until) {
                auto lc = H.last_ctl ? H.last_ctl() : std::make_pair(0, 0LL);
                if (lc.first && lc.second > t0)
                    code = lc.first;
                else if (T.key(50) == 27)
                    return;
            }
            if (code < 0) {
                say("nothing moved");
                return;
            }
        }
        efx_send('s', sa, code);
        if (code && dep == 0x40)
            efx_send('s', da, 0x7F);                    // (a source with no depth does nothing: +100%)
        say(pname + " moved by " + src_label(code));
    }

    // one value (livetui.edit_efx): left/right (page up/down by ten), digits a
    // raw value; each move sent, so it is heard as it goes; Enter keeps it,
    // Esc puts back what it was
    void edit_efx(const std::string &nm, const std::vector<int> &vals, const std::function<std::string(int)> &show,
                  int v0, const std::function<void(int)> &send)
    {
        size_t j = 0;
        for (size_t i = 0; i < vals.size(); i++)
            if (abs(vals[i] - v0) < abs(vals[j] - v0))
                j = i;
        const size_t j0 = j;
        while (true) {
            char b[200];
            snprintf(b, sizeof b, " %s:  %s   (raw %d)", nm.c_str(), show(vals[j]).c_str(), vals[j]);
            std::string m = "\x1b[H\x1b[2J" + C("sel") + "\x1b[1m" + b + "\x1b[0m\r\n\r\n" + C("dim")
                            + "   ←→ -+ step  pgup pgdn ten  digits a raw value  enter keep  esc back\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            size_t k = j;
            if (c == KEY_MOUSE) {
                if (T.m.kind == Mouse::PRESS)
                    return;                     // (a tap keeps it, as Enter)
                if (T.m.kind == Mouse::WHEEL)
                    k = T.m.dy > 0 ? std::min(vals.size() - 1, j + 1) : (j ? j - 1 : 0);
                c = -1;
            }
            if (c == 1002 || c == 'l' || c == '+' || c == '=')
                k = std::min(vals.size() - 1, j + 1);
            else if (c == 1003 || c == 'h' || c == '-')
                k = j ? j - 1 : 0;
            else if (c == 1006)
                k = j >= 10 ? j - 10 : 0;
            else if (c == 1005)
                k = std::min(vals.size() - 1, j + 10);
            else if (c >= '0' && c <= '9') {
                std::string got;
                if (prompt(nm + " raw value = " + std::string(1, (char)c), got)) {
                    int x = atoi((std::string(1, (char)c) + got).c_str());
                    for (size_t i = 0; i < vals.size(); i++)
                        if (abs(vals[i] - x) < abs(vals[k] - x))
                            k = i;
                }
            } else if (c == 10 || c == 13) {
                return;
            } else if (c == 27) {
                if (j != j0)
                    send(vals[j0]);
                return;
            }
            if (k != j) {
                j = k;
                send(vals[j]);
            }
        }
    }

    void adjust(int delta, bool big)
    {
        if (pane == P_PARTS) {
            part_adjust(delta, big);
            return;
        }
        if (pane == P_SYNTH) {
            synth_bump(delta, big);
            return;
        }
        if (pane == P_ROUTES) {
            ctl_bump(delta, big);
            return;
        }
        if (pane != P_GLOBALS)
            return;
        int i = GLOBAL_ORDER[grow];
        if ((i == 6 && !H.has_gpu) || (i == 7 && !H.has_room) || (i == 8 && H.rooms.empty())) {
            say(i == 6 ? "gpu: not available (--gpu at start)" : i == 7 ? "room tail: the export has none"
                                                                       : "room: the export carries no rooms");
            return;
        }
        const double hi = i == 8 ? (double)H.rooms.size() - 1.0 : GLOBAL_RANGE[i][1];
        double v = H.g[i] + delta * GLOBAL_RANGE[i][2] * (big && i != 8 ? 5 : 1);
        v = std::max(GLOBAL_RANGE[i][0], std::min(hi, v));
        if (i == 8 && v != H.g[i])
            say("room: " + H.rooms[(int)v] + " -- every patch built again in it, the tail crossfaded");
        if (i == 13 && v != H.g[i])
            say(std::string("standard: ") + STD_NAMES[(int)std::lround(v)]
                + " -- program changes read its banks; the patch picker opens in it");
        if (i == 10 && v > 0.0 && v < 20.0)     // (off and 20 bpm are neighbours: nothing slower is a metronome)
            v = H.g[i] < 20.0 ? 20.0 : 0.0;
        if (i == 2)
            v = std::round(v * 100.0) / 100.0;
        H.g[i] = v;
        H.set_global(i, v);
    }

    // a global set where its bar was touched (livetui.set_by_bar): f of its range
    void set_by_bar(int i, double f)
    {
        const double lo = GLOBAL_RANGE[i][0], hi = i == 8 ? (double)H.rooms.size() - 1.0 : GLOBAL_RANGE[i][1];
        const double st = i == 8 ? 1.0 : GLOBAL_RANGE[i][2];
        double want = lo + std::max(0.0, std::min(1.0, f)) * (hi - lo);
        int steps = (int)std::lround((want - H.g[i]) / st);
        if (steps)
            adjust(steps, false);
    }

    // what a tap, a drag, a release or the wheel does where it lands
    // (livetui.mouse): select (a pane's title, a global, a route); drag a
    // global up or down, or the wheel, to change it; tap its bar to set it; a
    // stop drawn or put in; a key hint is its key
    void mouse(const Mouse &m)
    {
        if (help) {
            if (m.kind == Mouse::PRESS)
                help = false;
            return;
        }
        if (m.kind == Mouse::RELEASE) {
            drag_global = drag_cell = drag_knob = -1;
            return;
        }
        if (m.kind == Mouse::DRAG) {
            if (drag_global >= 0 && m.y != drag_y) {
                pane = P_GLOBALS;
                grow = drag_global;
                adjust(drag_y - m.y, false);         // (up is more)
                drag_y = m.y;
            } else if (drag_cell >= 0 && m.y != drag_y) {
                pane = P_PARTS;
                pcol = drag_cell;
                adjust(drag_y - m.y, false);
                drag_y = m.y;
            } else if (drag_knob >= 0 && m.y != drag_y) {
                pane = P_SYNTH;
                srow = drag_knob;
                adjust(drag_y - m.y, false);
                drag_y = m.y;
            }
            return;
        }
        const Hit *h = hit_at(m.y, m.x);
        if (!h)
            return;
        if (m.kind == Mouse::WHEEL) {
            if (h->kind == H_GLOBAL || h->kind == H_GBAR) {
                pane = P_GLOBALS;
                grow = global_pos(h->a);
                adjust(m.dy, false);
            } else if (h->kind == H_ROUTE) {
                pane = P_ROUTES;
                crow = h->a;
                if (crow < ctl_count())
                    ctl_bump(m.dy, false);
            } else if (h->kind == H_CELL) {
                pane = P_PARTS;
                prow = h->a;
                if (h->b >= 0) {
                    pcol = h->b;
                    adjust(m.dy, false);
                }
            } else if (h->kind == H_KNOB || h->kind == H_KBAR) {
                pane = P_SYNTH;
                srow = h->a;
                adjust(m.dy, false);
            }
            return;
        }
        switch (h->kind) {                      // a press
        case H_PANE: pane = h->a; break;
        case H_KEY: press(h->a); break;
        case H_GLOBAL:
            pane = P_GLOBALS;
            grow = global_pos(h->a);
            drag_global = grow;
            drag_y = m.y;
            break;
        case H_GBAR:
            pane = P_GLOBALS;
            grow = global_pos(h->a);
            set_by_bar(h->a, (m.x - h->x0 + 0.5) / std::max(1, h->x1 - h->x0));
            drag_global = grow;
            drag_y = m.y;
            break;
        case H_STOP: toggle_stop(h->a); break;
        case H_ROUTE: {                         // a control or a route: selected; a control tapped again, space
            const bool was = pane == P_ROUTES && crow == h->a;
            pane = P_ROUTES;
            crow = h->a;
            if (was && crow < ctl_count())
                ctl_space();
            break;
        }
        case H_KNOB: {                          // a knob: selected; a switch tapped again, its next position
            const bool was = pane == P_SYNTH && srow == h->a;
            pane = P_SYNTH;
            srow = h->a;
            if (was && !synth_steps(SYNTH_KNOBS[h->a][3]).empty())
                synth_bump(1, false);
            drag_knob = h->a;
            drag_y = m.y;
            break;
        }
        case H_KBAR:                            // a knob's bar: set where touched
            pane = P_SYNTH;
            synth_by_bar(h->a, (m.x - h->x0 + 0.5) / std::max(1, h->x1 - h->x0));
            drag_knob = h->a;
            drag_y = m.y;
            break;
        case H_CELL: {                          // a part's cell: selected; tapped again, Enter
            const bool was = pane == P_PARTS && prow == h->a && (h->b < 0 || pcol == h->b);
            pane = P_PARTS;
            prow = h->a;
            if (h->b >= 0)
                pcol = h->b;
            if (was && h->b >= 0) {
                part_enter();
            } else if (h->b >= 0) {
                drag_cell = h->b;
                drag_y = m.y;
            }
            break;
        }
        }
    }

    void toggle_stop(int ri)
    {
        std::vector<char> dr = H.drawn();
        bool was = ri < (int)dr.size() && dr[ri];
        H.toggle_stop(ri);
        say(std::string(was ? "in: " : "drawn: ") + H.stop_names[ri]);
    }

    // a key, from the keyboard or a tapped hint
    void press(int c)
    {
                if (!help && H.controls && c > 0 && c < 128 && strchr(HOTKEYS_FREE, c)) {
                    for (auto &sc : *H.controls)       // A BOUND KEY, from every pane (livetui's)
                        if (sc.hotkey == c) {
                            ctl_fire(sc);
                            return;
                        }
                }
                if (help) {
                    help = false;
                } else if (c == 'q') {
                    quit = true;
                } else if (c == '?') {
                    help = true;
                } else if (c == 9) {
                    pane = (pane + 1) % NPANES;
                } else if (c == 1004) {
                    pane = (pane + NPANES - 1) % NPANES;
                } else if (c == 1000 || c == 'k') {
                    if (pane == P_PARTS)
                        prow = std::max(0, prow - 1);
                    else if (pane == P_SYNTH)
                        srow = std::max(0, srow - 1);
                    else if (pane == P_GLOBALS)
                        grow = std::max(0, grow - 1);
                    else
                        crow = std::max(0, crow - 1);
                } else if (c == 1001 || c == 'j') {
                    if (pane == P_PARTS)
                        prow = std::min(std::max(0, (int)prows.size() - 1), prow + 1);
                    else if (pane == P_SYNTH)
                        srow = std::min(NSYNTH - 1, srow + 1);
                    else if (pane == P_GLOBALS)
                        grow = std::min(NGLOBALS - 1, grow + 1);
                    else
                        crow = std::min(std::max(0, ctl_rows() - 1), crow + 1);
                } else if (pane == P_PARTS && (c == 1003 || c == 'h')) {
                    pcol = std::max(0, pcol - 1);       // (the parts: the arrows move along the columns)
                } else if (pane == P_PARTS && (c == 1002 || c == 'l')) {
                    pcol = std::min(NPCOLS - 1, pcol + 1);
                } else if (pane == P_PARTS && (c == 10 || c == 13)) {
                    part_enter();
                } else if (pane == P_PARTS && (c == 'a' || c == 's' || c == 'd' || c == 'm')) {
                    part_key(c);
                } else if (pane == P_SYNTH && (c == ' ' || c == '0' || c == 'D' || c == 'B' || c == 'T' || c == 'F' || c == 'M')) {
                    synth_key(c);
                } else if (c == 1003 || c == 'h' || c == '-' || c == '_') {
                    adjust(-1, c == '_');
                } else if (c == 1002 || c == 'l' || c == '=' || c == '+') {
                    adjust(1, c == '+');
                } else if (!H.stop_names.empty() && c == STOP_PREFIX) {
                    stop_bank = !stop_bank;
                    say(stop_bank ? "stops: rows 3 and 4 -- press a stop key" : "stops: rows 1 and 2");
                } else if (!H.stop_names.empty() && c > 0 && c < 128
                           && (strchr(STOP_DIGITS, c) || strchr(STOP_SHIFTED, c))) {
                    int row = strchr(STOP_DIGITS, c) ? 0 : 1;
                    int i = (int)((row ? strchr(STOP_SHIFTED, c) - STOP_SHIFTED : strchr(STOP_DIGITS, c) - STOP_DIGITS));
                    if (stop_bank) {
                        row += 2;
                        stop_bank = false;
                    }
                    if (row < (int)H.stop_rows.size() && i < (int)H.stop_rows[row].size())
                        toggle_stop(H.stop_rows[row][i]);
                } else if (c == 'p' && H.pick) {
                    pick_patch();
                } else if (c == 't' && H.set_tuner) {
                    pick_tuner();
                } else if (c == 'E' && H.set_eastern) {
                    pick_eastern();
                } else if (c == 'x' || c == 'X') {
                    pick_efx();
                } else if (c == 'I' && H.inputs && H.input_toggle) {
                    pick_inputs();
                } else if (c == 'S' || c == 'L' || c == 'N' || c == 'R') {
                    presets_key(c);
                } else if (c == 'P') {
                    H.panic();
                    say("all notes off");
                } else if (pane == P_ROUTES && c == 'r') {
                    add_route();
                } else if (pane == P_ROUTES && c == 'd') {
                    ctl_delete();
                } else if (pane == P_ROUTES && c == 'a') {
                    add_control();
                } else if (pane == P_ROUTES && c == 'b') {
                    bind_hotkey();
                } else if (pane == P_ROUTES && c == ' ') {
                    ctl_space();
                } else if (pane == P_ROUTES && (c == 10 || c == 13)) {
                    ctl_type();
                }
    }

    // the panel until q: drawn ten times a second, between keys
    void run(const std::function<bool()> &going)
    {
        T.enter();
        last = std::chrono::steady_clock::now();
        auto next = last;
        while (going() && !quit) {
            int c = T.key(20);
            if (c == KEY_MOUSE)
                mouse(T.m);
            else if (c >= 0)
                press(c);
            auto now = std::chrono::steady_clock::now();
            if (now >= next) {
                if (H.refresh) {
                    std::string m = H.refresh();
                    if (!m.empty())
                        say(m);
                }
                s = H.take();
                draw();
                next = now + std::chrono::milliseconds(100);
            }
        }
        T.leave();
    }
};

}  // namespace panel

#endif
