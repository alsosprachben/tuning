// hostint.h -- the native live host's internals, shared by libnative's
// host.cpp and nvlive.cpp while nvlive's main() moves into the library
// (host.h is the C API it grows into): the export's constants, the export
// as read, and its reader.
#ifndef NV_HOSTINT_H
#define NV_HOSTINT_H
#include <array>
#include <map>
#include <string>
#include <vector>
#include "nv.h"

namespace nvh {
// the export's constants (native_export.py's order)
enum { K_SR, K_BLK, K_CHUNK, K_MASTER, K_RING_FLOOR, K_RING_MAX, K_XDEC, K_REG_SCALE, K_FULL, K_RESIDUAL, K_BETA,
       K_KNEE, K_LN10_20, K_RETRIGGER, K_NYQ_OM, K_SVDC, K_FIXED_TOUCH, K_REFLECT, K_BANDS, K_SH = K_BANDS + 9,
       K_PRESS_DB = K_SH + 4, K_THRESH, K_BEND_RANGE, K_TAU, K_FADER_TAIL, K_STAMP_S, K_STAMPED_SHARE,
       K_BEND_SEMIS, K_GM_VOL, K_GM_EXPR, K_GSPLACE, K_MAPKITS = K_GSPLACE + 13, K_EFX = K_MAPKITS + 33 };

// A RECORD IN THE MAPPED EXPORT (read_export maps the file copy-on-write):
// only the pages touched are in memory, and only those a host writes (a
// class's organ, its struck layer, a room's fields) are its own copies
struct Mapped {
    unsigned char *p = nullptr;
    size_t n = 0;
    unsigned char *data() { return p; }
    const unsigned char *data() const { return p; }
    size_t size() const { return n; }
};
// ...and an array of records in it (the organs')
template <class T> struct MappedArr {
    T *p = nullptr;
    size_t n = 0;
    T &operator[](size_t i) { return p[i]; }
    const T &operator[](size_t i) const { return p[i]; }
    T *data() { return p; }
    const T *data() const { return p; }
    size_t size() const { return n; }
    bool empty() const { return n == 0; }
    T *begin() { return p; }
    T *end() { return p + n; }
    const T *begin() const { return p; }
    const T *end() const { return p + n; }
};

struct Export {
    void *map = nullptr;                  // the whole file, mapped (MAP_PRIVATE)
    size_t map_n = 0;
    // LP3D: live.pan_at's head (z, distance, radius, sound speed)
    double p3d[4] = {0.0, 0.0, 0.0, 0.0};
    bool has_p3d = false;
    // LROOMS: every room live can switch to -- the class records' byte
    // ranges a room sets, how many classes, the device tails' filters, and
    // each room's name, whether it reflects, its tail's spec and (where it
    // reflects) every class's ranges in it
    struct RoomData {
        std::string name;
        bool reflect = true;
        std::vector<double> spec;
        std::vector<uint8_t> fields;
    };
    std::vector<std::pair<int, int>> room_rng;
    int room_ncls = 0;
    std::vector<double> room_dev;
    std::vector<RoomData> rooms;
    std::vector<double> k, freq, trim, pan;
    std::vector<Mapped> classes;          // (each in the map, csz bytes)
    std::vector<int> cmap, kind, fin;     // cmap: the programs' keys, then the drum sets'
    std::vector<double> kit_f0, kit_seat;
    std::vector<unsigned long long> kit_choke;
    std::vector<int> kit_skind;
    std::vector<double> kit_spar;
    // MKIT: the maps' own drum sets (a drum program 128 + j: percussion_map's
    // id mk_ids[j]), their keys' classes; MKNM their names
    std::vector<int> mk_ids, mk_map;
    std::vector<std::string> mk_names;
    std::string room, libs[3];
    MappedArr<OrganSpec> organs;          // ORGA: the registered organs' tables (in the map)
    // VARS: bank select (the file renderer's): each slot's classes at each key, each
    // entry's layers (slot, semitones, velocities), trims and class, GS's and GM 2's tables
    struct VarEnt {
        std::vector<std::array<int, 4>> ls;
        double trim[2] = {1.0, 1.0};
        int pcls = -1;
    };
    std::vector<int> vmap, vgs, vgm2, dmap;    // ...and DRON: K's drone region
    std::vector<int> vslot_v;                   // each slot's variation key (live.Patch.variation)
    // VNAM: the variations the picker offers: program, key, name
    std::vector<std::array<int, 2>> vpv;
    std::vector<std::string> vnames;
    std::string efxu;                           // EFXU: the panel's insertion-effect tables (panel::efx_tables)
    std::vector<std::array<int, 10>> vpart;     // VLIV: each one's live record, as part[]'s
    std::vector<std::array<int, 12>> vdrn;      // VDRN: a voice's own drone patch (program, variation, its record)
    std::vector<double> mtab;                   // MTAB: moog.py's tables by knob position (nv_moog_tables)
    std::vector<VarEnt> vents;
    struct Stops {
        std::vector<std::string> names;
        std::vector<std::vector<int>> rows;
        std::vector<std::vector<int>> breaks;   // each row's line breaks: a new line at its stop i
    } stops[128];                         // LSTOP: an organ program's ranks and the panel's stop rows
    std::vector<int> cls_organ, prog_organ;   // each class's organ, each program's (-1 none, -2 not the engine's)
    std::vector<double> les;              // LESL: the rotating speaker's constants
    std::string lobe_lib;                 // ...and synth_voice_lobe's library
    std::vector<double> scan;             // SCAN: the scanner's constants and tables
    double beta = 0.0, headroom = 1.0;
    int part[128][10];
    bool live = false;
    // LREG: each program's free strings (live's register), M 0 for none
    struct Reg {
        int M = 0;
        std::vector<StringMode> modes;
        double d[9];            // kappa knock fall floor beta rel full_db_s residual ln10_20
        int i[3];               // damper_top, dampers, block
        int note[128];
        std::vector<unsigned char> cinit, csnap;    // nv_strings' VoiceInit and VoiceSnap: the bank at another tuner
    } reg[128];
    // LGPU: live's GPU renderer -- its setup's builds, gpukernel.cl's directory, GPU_MIN (and at 64 frames or fewer)
    std::string gpu_lib, gpu_damp_lib, gpu_dir;
    int gpu_min[2] = {1000, 2000};
    bool gpu = false;
    // LROOM: live's convolver, the room's late tail (n stereo samples) and its modes' (m; 0 none)
    std::string conv_lib;
    std::vector<float> ir, mir;
    bool has_room = false;
    // LROUTE: the session's routes, nv_rt_add's seven each
    std::vector<std::array<int, 7>> routes;
    // LPROG: what a program change needs -- each program's strings' identity
    // (-1 no part), a harpsichord's choirs for its register, its names
    struct Prog {
        int sid = -1;
        std::vector<long> cbr;
        double cross = 1.0;
        std::vector<int> buffs;
        std::string name, kit;
    } prog[128];
    bool has_prog = false;
};


// the export (native_export.py --live) into E: false if it is not one of this build's
bool read_export(const char *path, Export &E);
}  // namespace nvh
#endif
