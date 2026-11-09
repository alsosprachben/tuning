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

#ifdef __cplusplus
}
#endif
#endif
