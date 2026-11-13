/* host.h -- THE NATIVE LIVE HOST as a library (live.Live's twin, over
   libnative's nv_part_* / nv_tcache_*): nvlive's own host, behind a C API a
   GUI (or nvlive's panel, or Python through ctypes) drives while it plays.
   The calls below are there; the rest of the plan (the globals, the parts,
   the patches, tuning, stops, routes, the insertion effect) follows.

   THREADS. nv_host_render is the audio thread's (the caller's own callback);
   the rest may be called from any other thread. Programs and rooms are
   built on the host's builder thread (nv_host_start), never on the
   caller's or the audio thread. */
#ifndef NV_HOST_H
#define NV_HOST_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct nv_host nv_host;

/* the export (native_export.py --live) opened and its first part built, from
   nvlive's options (argv[0] the export; --program=N, --drums, --reg-sync ...);
   NULL when it cannot be (err says so, and nvlive's message is on stderr) */
nv_host *nv_host_open_args(int argc, char **argv, char *err, int errlen);
/* the workers and the builder: before the first render */
void nv_host_start(nv_host *h);
/* the builder stopped (the host is not freed: its workers run to the end) */
void nv_host_close(nv_host *h);

int nv_host_rate(const nv_host *h);         /* 48000 */
int nv_host_block(const nv_host *h);        /* frames a render takes */
/* ONE BLOCK (the caller's audio callback): the MIDI queued, the builder's
   patches and room swapped in, the render -- into L, R. 0, or -1 if frames
   is not the block */
int nv_host_render(nv_host *h, float *L, float *R, int frames);
/* ...IN STEP (nvlive --test's, the host not started): the programs asked
   for built after the block, swapped in for the next -- live's builder in
   step (examples/patchsync.py) */
int nv_host_render_step(nv_host *h, float *L, float *R, int frames, int step);
/* MIDI bytes as they came (running status, an exclusive F0 ... F7), from any
   thread: heard at the next block */
void nv_host_midi(nv_host *h, const uint8_t *msg, int n);

typedef struct {
    long long n0, blocks, over, underruns;
    double ms_max, ms_mean, budget_ms;      /* since the last read */
    float peak[2];                          /* since the last read */
    double eng[15];                         /* nv_part_stats */
    int rt, rt_dropped, on_gpu;
    long efx_rev;                           /* the insertion effect's revision */
} nv_host_snap;
void nv_host_snapshot(nv_host *h, nv_host_snap *s);
/* what the builder has to say (a build's time, a refusal), oldest first: its
   length, 0 none; copied into buf */
int nv_host_message(nv_host *h, char *buf, int cap);

/* the rooms the export has ('\n'-separated), the room now ("" none), and a
   room switched to: every template built again in it on the builder, the
   tail crossfaded (live.set_room) */
int nv_host_rooms(nv_host *h, char *names, int cap);
const char *nv_host_room(const nv_host *h);
void nv_host_set_room(nv_host *h, const char *name);

/* ---- the globals (livetui.GLOBALS: the panel's) ----------------------------
   0 master dB, 1 headroom dB, 2 the limiter's knee, 3 the wheel's range
   (semitones), 4 the mod wheel's depth (cents), 5 aftertouch dB, 6 the GPU
   (1 on), 7 the room's tail (1 on), 8 the room (nv_host_rooms' index: built
   on the builder) -- changed between two blocks */
enum { NV_G_MASTER_DB, NV_G_HEADROOM_DB, NV_G_LIMITER, NV_G_BEND_RANGE, NV_G_MOD_CENTS, NV_G_PRESS_DB,
       NV_G_GPU, NV_G_ROOM_TAIL, NV_G_ROOM, NV_G_N };
int nv_host_global_count(void);
void nv_host_set_global(nv_host *h, int which, double v);
double nv_host_global(const nv_host *h, int which);

/* ---- the patches: every program, drum set and variation the export has ---- */
typedef struct {
    int program, variation, drums;          /* variation: its bank (0 the capital tone) */
    int native;                             /* playable here */
    int pick;                               /* what nv_host_pick takes */
    char name[64];
} nv_host_patch;
/* how many there are; up to cap of them copied into out (NULL: the count) */
int nv_host_patches(nv_host *h, nv_host_patch *out, int cap);
/* a patch for the part: built on the builder if new, swapped in between two
   blocks (live's change_patch) */
void nv_host_pick(nv_host *h, int pick);
/* the patch sounding now */
void nv_host_patch_now(const nv_host *h, int *program, int *variation, int *drums);
/* every note off, now (the panel's panic) */
void nv_host_panic(nv_host *h);
/* how much is still to land -- programs and a room asked for, building,
   built and not yet swapped in: a GUI's spinner (0 settled) */
int nv_host_building(nv_host *h);
/* the build under way, a progress bar's: templates done of its total, and
   what it is ("program 19 Church Organ"; cap bytes of it into name). 1 while
   one builds, 0 none */
int nv_host_progress(nv_host *h, long *done, long *total, char *name, int cap);
/* the live part it plays (native.py's nv_part_*: a check reads its slab) */
void *nv_host_part(nv_host *h);

#ifdef __cplusplus
}
#endif
#endif
