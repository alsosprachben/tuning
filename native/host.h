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
/* REAL TIME (an app's audio callback, 1): the render never waits on a lock
   another thread holds -- what was queued for a block whose lock is busy is
   taken the next block (2.7 ms later). Off (the default, and a check's): it
   waits, so the blocks are the same whatever the threads' timing */
void nv_host_set_realtime(nv_host *h, int on);
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

/* ---- an app's audio callback (AVAudioEngine's source node, an Audio Unit) --
   ANY NUMBER OF FRAMES: whole blocks rendered as needed, the rest of the last
   kept for the next call -- the same samples as nv_host_render's blocks, in
   order, whatever sizes are asked (256, 512, 471 ...). The audio thread's,
   as nv_host_render (not both on one host) */
int nv_host_pull(nv_host *h, float *L, float *R, int frames);
/* ...in step (the host not started), as nv_host_render_step */
int nv_host_pull_step(nv_host *h, float *L, float *R, int frames, int step);
/* MIDI stamped with its sample (counted from the first render: CoreMIDI's
   timestamp turned into the audio's sample time), from any thread: heard at
   the start of the block that sample falls in -- a callback of many blocks
   spreads a burst of notes over them as they were played (the next block's,
   if that one has gone) */
void nv_host_midi_at(nv_host *h, const uint8_t *msg, int n, long long frame);

typedef struct {
    long long n0, blocks, over, underruns;
    double ms_max, ms_mean, budget_ms;      /* since the last read */
    float peak[2];                          /* since the last read */
    double eng[15];                         /* nv_part_stats */
    int rt, rt_dropped, on_gpu;
    long efx_rev;                           /* the insertion effect's revision */
    double max_step_ms, max_out_ms;         /* the slowest block's split: before the output (the
                                               queued work, the MIDI, the slab's step), the output */
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
/* ---- THE PARTS (livetui's PARTS pane; live.Part): each part a row, in order --
   its patch, channel (-1 every one), keys, transpose, level, mute, solo (0
   none, 1 this one soloed, 2 another is), fixed touch */
typedef struct {
    int row, program, variation, drums;
    int channel, lo, hi, transpose;
    double level_db;
    int muted, solo, touch_fixed;
    char name[64];
} nv_host_partinfo;
/* how many parts; up to cap of them copied into out (NULL: the count) */
int nv_host_parts(nv_host *h, nv_host_partinfo *out, int cap);
/* a part's channel, keys, transpose, level and mute (live's cheap edits) */
void nv_host_part_set(nv_host *h, int row, int channel, int lo, int hi, int transpose, double level_db, int muted);
/* a part's patch (nv_host_patches' pick), built on the builder */
void nv_host_part_pick(nv_host *h, int row, int pick);
/* LAYER (a copy over the same keys), SPLIT (its range halved into two),
   DELETE: 0, or -1 and why (cap bytes of it) */
int nv_host_part_layer(nv_host *h, int row);
int nv_host_part_split(nv_host *h, int row, char *why, int cap);
int nv_host_part_delete(nv_host *h, int row, char *why, int cap);
/* solo (again on a soloed part: out of it), fixed touch (1) or velocity (0) */
void nv_host_part_solo(nv_host *h, int row);
void nv_host_part_touch(nv_host *h, int row, int fixed);

/* ---- PRESETS AND THE SESSION (live's presets.json and session.json, the
   same files nvlive and live.py keep -- presets.json beside the session) ----
   the session's path (none set: no presets) */
void nv_host_set_session_path(nv_host *h, const char *path);
/* the presets' names ('\n'-separated, cap bytes of them): the whole length */
int nv_host_presets(nv_host *h, char *names, int cap);
/* the whole setup saved under name (live.save_preset), or loaded
   (live.apply_preset: the parts built again on the builder): 0, or -1; what
   happened in msg */
int nv_host_preset_save(nv_host *h, const char *name, char *msg, int cap);
int nv_host_preset_load(nv_host *h, const char *name, char *msg, int cap);
/* the session read and applied (an app's start: 0, -1 none), written (its quit) */
int nv_host_session_load(nv_host *h);
int nv_host_session_save(nv_host *h);

/* ---- AN ORGAN's STOPS (livetui's stop rows: the first part's organ) ----
   program's ranks: how many (0 not an organ), their names '\n'-separated */
int nv_host_stop_names(nv_host *h, int program, char *names, int cap);
/* the panel's rows of them: rank indices, -2 a break within a row (the
   voice's groups), -1 a row's end -- how many ints (cap of them copied) */
int nv_host_stop_rows(nv_host *h, int program, int *out, int cap);
/* each rank drawn (1) or not, now: how many; a rank drawn or retired
   between two blocks */
int nv_host_drawn(nv_host *h, char *out, int cap);
void nv_host_toggle_stop(nv_host *h, int rank);

/* the live part it plays (native.py's nv_part_*: a check reads its slab) */
void *nv_host_part(nv_host *h);

#ifdef __cplusplus
}
#endif
#endif
