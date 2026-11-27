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
/* the room's body on the audio thread (1: set_realtime's) or its worker (0) */
void nv_host_room_inline(nv_host *h, int on);
/* macOS / iOS: the output unit's AUDIO WORKGROUP (CoreAudio's), which the
   host's helper threads then join -- the room's worker, the GPU setup's
   team, the free strings', the scanner's, the valve's -- so they wake
   promptly on fast cores, counted with the audio thread. 0, or -1 none.
   Again after the output device changes */
int nv_host_join_output_workgroup(nv_host *h, void *audio_unit);
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
/* RUBATO (off by default): the blocks rendered on their own thread, the
   callback (nv_host_pull) waiting for them at most wait_fraction of its own
   length -- what is not ready then is held (silence, for now) and heard when
   done, the device that many frames ahead of the render from then on (MIDI
   through nv_host_midi_at heard that much later, all alike). Turned on before
   the first callback. stats: [0] callbacks that held, [1] frames held ever,
   [2] frames owed now, [3] frames rendered, [4] frames handed out,
   [5] returns, [6] frames returned, [7] frames held by the partials ringing on
   (--gpu-span: nothing borrowed). What is held is the sound just heard
   going on (rubfill.h), crossed into the late block when it comes */
int nv_host_set_rubato(nv_host *h, int on, double wait_fraction);
void nv_host_rubato_stats(const nv_host *h, long long *stats);
/* RETURNING THE TIME (on by default): while frames are owed the render
   thread renders that far ahead, and they are cut from the stream -- crossed
   over XF frames -- once no event falls in them; off, they stay owed */
void nv_host_set_rubato_return(nv_host *h, int on);
/* MIDI stamped with its sample (counted from the first render: CoreMIDI's
   timestamp turned into the audio's sample time), from any thread: heard at
   the start of the block that sample falls in -- a callback of many blocks
   spreads a burst of notes over them as they were played (the next block's,
   if that one has gone) */
void nv_host_midi_at(nv_host *h, const uint8_t *msg, int n, long long frame);
/* A COLD START (an app's real time; blocks 0: off, the default): a note-on
   after cold_seconds with no MIDI begins a phrase whose events (through
   nv_host_midi_at) all come `blocks` blocks later -- one shift for the whole
   phrase, so its intervals stay as played -- and while the first note waits,
   nv_host_pull keeps the thread busy up to warm_fraction of each callback,
   so the core is up to speed when the note's first block comes */
void nv_host_set_cold_start(nv_host *h, int blocks, double cold_seconds, double warm_fraction);

typedef struct {
    long long n0, blocks, over, underruns;
    double ms_max, ms_mean, budget_ms;      /* since the last read */
    float peak[2];                          /* since the last read */
    double eng[15];                         /* nv_part_stats */
    int rt, rt_dropped, on_gpu;
    long efx_rev;                           /* the insertion effect's revision */
    double max_step_ms, max_out_ms;         /* the slowest block's split: before the output (the
                                               queued work, the MIDI, the slab's step), the output */
    double max_busy, max_gpu, max_gpu_setup_ms, max_gpu_samples_ms;  /* ...its busy slots, on the GPU (1),
                                               the GPU's setup and samples times */
    double max_split_ms[3];                 /* ...before its output: the queued work, the events, the
                                               engine's step (notes started, ended) */
    double max_cpu_user_ms, max_cpu_sys_ms; /* ...the CPU time its thread got in it, user and system
                                               (macOS, real time: much under its wall time -- not running) */
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
   on the builder), 9 the mod wheel's rate (+%: 0..1.5), 10 the metronome
   (bpm, 0 off), 11 its bell (every n beats, 0 none), 12 its level dB, 13 the
   standard program changes read (0 ours, 1 SC-55, 2 SC-88, 3 SC-88Pro, 4
   SC-8850) -- changed between two blocks */
enum { NV_G_MASTER_DB, NV_G_HEADROOM_DB, NV_G_LIMITER, NV_G_BEND_RANGE, NV_G_MOD_CENTS, NV_G_PRESS_DB,
       NV_G_GPU, NV_G_ROOM_TAIL, NV_G_ROOM, NV_G_MOD_RATE, NV_G_METRONOME, NV_G_METRO_RING, NV_G_METRO_DB,
       NV_G_STANDARD, NV_G_STAND_IN, NV_G_N };
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
/* THE STAMPED CHANNELS: a bit per channel whose parts are stamped per note
   (a muxed file's): CC7, CC11 and pan there set the next note's only */
void nv_host_stamped(nv_host *h, unsigned mask);
unsigned nv_host_stamp_rule(nv_host *h, void *midi);
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
/* A PRESET's SETUP MEASURE (live.preset_midi): what a MIDI file can say of
   preset NAME in PRESETS_PATH -- a GS Reset, its scene, each part's bank,
   program, cabinet (CC83), pickup (CC85), an organ's stops (H's organs;
   null none), level and pan -- written to OUT as a Standard MIDI File; 0,
   or -1 */
int nv_preset_midi_file(const nv_host *h, const char *presets_path, const char *name, const char *out);
/* the session read and applied (an app's start: 0, -1 none), written (its quit) */
int nv_host_session_load(nv_host *h);
int nv_host_session_save(nv_host *h);

/* ---- AN ORGAN's STOPS (livetui's stop rows: the first part's organ) ----
   program's ranks: how many (0 not an organ), their names '\n'-separated */
int nv_host_stop_names(nv_host *h, int program, char *names, int cap);
/* the panel's rows of them: rank indices, -2 a break within a row (the
   voice's groups), -1 a row's end -- how many ints (cap of them copied) */
int nv_host_stop_rows(nv_host *h, int program, int *out, int cap);
/* ...an organ VARIATION's (a bank's own organ; 0 the program's): its stops' names, or
   with labels its card words (the class's stop_labels), and its rows as above */
int nv_host_stop_names_v(nv_host *h, int program, int variation, char *names, int cap, int labels);
int nv_host_stop_rows_v(nv_host *h, int program, int variation, int *out, int cap);
/* each rank drawn (1) or not, now, on the first part's organ: how many; a
   rank drawn or retired between two blocks */
int nv_host_drawn(nv_host *h, char *out, int cap);
void nv_host_toggle_stop(nv_host *h, int rank);
/* ...on any part's (row as nv_host_parts lists them; 0 for a part with no
   organ); and its whole registration at once: want[rank] 1 drawn (none
   drawn: the first in the crescendo, as live.set_stops) -- a viewer's taps
   between two blocks all land, where toggles read the drawn as it stood */
int nv_host_part_drawn(nv_host *h, int row, char *out, int cap);
void nv_host_part_set_drawn(nv_host *h, int row, const char *want, int n);

/* ---- TUNING (livetui's t and E) ----
   every tuner: "name\twhat it is for" a line; the rig's now (or asked); one
   asked for (every patch built again in it, on the builder) */
int nv_host_tuners(char *out, int cap);
int nv_host_tuner(nv_host *h, char *out, int cap);
void nv_host_set_tuner(nv_host *h, const char *name);
/* the EASTERN tuning: a raga spec ("raga:<system>[/<raga>]@<sa>", "" off) for
   every Indian voice's part; its systems and ragas (NULL past the last) */
int nv_host_eastern(nv_host *h, char *out, int cap);
void nv_host_set_eastern(nv_host *h, const char *spec);
const char *nv_raga_system_name(int i);
const char *nv_raga_name(int i, int *n, const int **idx);

/* ---- THE INSERTION EFFECT (the Sound Canvas's EFX: livetui's x) ----
   its tables: Roland's numbered types, families, each type's parameters (the
   export's EFXU lines: "T num msb lsb name", "C first last family",
   "P msb lsb n name mark read fresh v,v,.. shown\x1fshown..") */
int nv_host_efx_tables(nv_host *h, char *out, int cap);
typedef struct {
    int has, msb, lsb;                      /* its type (0, 0: Thru) */
    int p[21];                              /* parameters 1-20 as set (-1: the type's own) */
    int send[3];                            /* to reverb, chorus, delay */
    int ctl[4];                             /* controller 1 source, depth; controller 2's */
    int nparts, parts[32];                  /* the channels on it (16-31: port B) */
    int status;
    char why[128];                          /* not native live: why */
} nv_host_efx;
/* as it stands (0; -1 none yet) */
int nv_host_efx_state(nv_host *h, nv_host_efx *s);
/* a setting, as the GS message a sequencer sends (gsefx.message): kind 't'
   a type (a msb, b lsb), 'p' parameter a = b, 's' address a = b (the sends
   0x17-0x19, the controllers 0x1B-0x1E), 'c' channel a on (b 1) or off */
void nv_host_efx_send(nv_host *h, int kind, int a, int b);

/* ---- THE SYSTEM EFFECTS (livetui's G): the reverb, chorus, delay, EQ ---- */
typedef struct {
    int rev_macro, rev_level, rev_time, rev_fb;    /* macro -1: the panel's room; fb -1: none */
    char room[64];
    int gs;                                 /* GS's chorus and delay (once a GS message is heard) */
    int cho[7];                             /* type, pre-LPF, level, feedback, delay, rate, depth */
    int dly[11];                            /* type, pre-LPF, time, ratio L, R, level C, L, R, level,
                                               feedback, to reverb */
    int eq[4];                              /* low freq, low gain, high freq, high gain */
} nv_host_sysfx_state;
int nv_host_sysfx(nv_host *h, nv_host_sysfx_state *s);
/* a setting as a sequencer's GS message: 40 hi lo v (hi 1 the reverb, chorus
   and delay, 2 the EQ) */
void nv_host_sysfx_send(nv_host *h, int hi, int lo, int v);

/* ---- A MOOG PART's KNOBS (livetui's synth pane) ----
   the panel's knobs, "section\tknob\tlabel\tkind\tsteps\tcentred\tcolumn\tgroup\t
   generic\twords\tat" a line (knob the index into pn, NV_MK_*; steps a switch's
   positions "32,16,8,4", empty a knob 0..1; centred 1 a centre detent; then
   the touch card's column, group, generic label, a switch's short words
   (comma-separated) and the knob's place in the card -- panel.h SYNTH_CARD) */
int nv_host_synth_knobs(char *out, int cap);
#define NV_HOST_NKNOBS 51
/* part `row`'s knobs on a layer: pn the positions, own 1 turned here, 2 kept
   but not heard natively, 0 the patch's; returns its layers (0 not a Moog, -1
   not read yet) */
int nv_host_synth_get(nv_host *h, int row, int layer, double *pn, char *own);
void nv_host_synth_set(nv_host *h, int row, int layer, int knob, double v);
void nv_host_synth_forget(nv_host *h, int row, int layer, int knob);     /* back to the patch's */
int nv_host_synth_send(nv_host *h, int row);            /* the panel to a Messenger: 0 none plugged in */
/* a knob's value in the panel's terms ("1.2 kHz", "8'", "saw"): pn the panel */
int nv_host_synth_fmt(const char *kind, double v, const double *pn, char *out, int cap);
/* the Messenger: its line ("" none set, "-" watched for), every part reading
   its chart (CCs as a Messenger's), its firmware's chart (1 pre-1.0.7) */
int nv_host_messenger_line(nv_host *h, char *out, int cap);
int nv_host_messenger_reads(nv_host *h);
void nv_host_set_messenger_reads(nv_host *h, int on);
int nv_host_messenger_pre107(nv_host *h);
void nv_host_set_messenger_pre107(nv_host *h, int on);
/* A TONEWHEEL ORGAN's DRIVE: out [now, the voice's, set (-1 the voice's)];
   1 an organ, 0 not, -1 unread; set v < 0: the voice's */
int nv_host_drive(nv_host *h, int row, double *out);
/* A PART's AMP (the AMP card): out[8] -- its valve's drive sounding (the mod
   wheel's scale on it), the voice's, the knob's (<0 none), the Leslie's
   half-moon (0 stop, 1 slow, 2 fast), a Leslie on it (1/0), the wheel's scale
   (1 untouched), its Spectra-Tone (1 the rotor, 2 Chorus, 0 none) and its
   rocker (1 up: Theater), its coupler switches (COUPLER_CC's bits, -1 none)
   and those its manual has (out[10]); 1 a tonewheel organ, 2 another
   amplified voice, 0 neither */
int nv_host_amp(nv_host *h, int row, double *out);
long nv_host_amp_seq(nv_host *h);           /* (the amp state's changes so far: the AMP card's push) */
/* a part's rotary heard (an organ's cabinet, a Rotary type): out[0] -1 its own
   way, 0 the cabinet in the room, 1 two mics; out[1] their spread in degrees
   (<0 the default); 0 no such row -- and set */
int nv_host_rotary(nv_host *h, int row, double *out);
void nv_host_set_rotary(nv_host *h, int row, int mode, double spread_deg);
/* a part's cabinet (live.set_cabinet): *chosen its choice (-1 none, its own),
   *now the one it plays through (0 its own), offer[] the CAB_CHOICES indices
   its voice offers -- how many; -1 no such row -- and set (-1 none) */
int nv_host_cabinet(nv_host *h, int row, int *chosen, int *now, int *offer, int cap);
void nv_host_set_cabinet(nv_host *h, int row, int choice);
/* ...and its pickup (live.set_pickup), the same way: PICKUP_CHOICES indices */
int nv_host_pickup(nv_host *h, int row, int *chosen, int *now, int *offer, int cap);
void nv_host_set_pickup(nv_host *h, int row, int choice);
/* a part's knobs (a piano's, piano_knobs.py; NV_VK_N of them): the mask its
   voice offers (0 none, -1 no such row); v[] each one's value (its own where
   set, else the voice's), v0[] the voice's, cap[] its program's plain voice's
   (where the ranges sit), *own the mask set, *building its patch on its way;
   set one (in its units), or put it back to the voice's (knob -1: every one) */
int nv_host_voicing(nv_host *h, int row, double *v, double *v0, double *cap, int *own, int *building);
void nv_host_set_voicing(nv_host *h, int row, int knob, double v);
void nv_host_forget_voicing(nv_host *h, int row, int knob);
void nv_host_set_drive(nv_host *h, int row, double v);
/* a part's rotor speed (the AMP card's), v as CC80's value -- a Leslie's
   half-moon, a Spectra-Tone's rocker -- straight to its rotors */
void nv_host_set_rotor(nv_host *h, int row, int v);
/* a divider organ part's coupler switches (the AMP card's): COUPLER_CC's bits --
   1 its 8' Off, 2 16', 4 4', 8 2' */
void nv_host_set_couplers(nv_host *h, int row, int v);

/* ---- THE CONTROLLER MATRIX (livetui's C): a channel's sources to destinations ----
   sources 0 mod wheel, 1 pitch bend, 2 channel aftertouch, 3 poly aftertouch,
   4 CC1, 5 CC2 (assignable: their numbers cc1, cc2); destinations 0 pitch,
   1 filter cutoff, 2 amplitude, 3-6 LFO1 rate, pitch, filter, amp depth, 7-10
   LFO2's. depth[src][dest] in the destination's unit (semitones, cents, a
   fraction, Hz) as in effect; gm2 the cells a file's GM2 messages set (CC
   n -> dest), shown, not edited */
typedef struct { int cc, dest; double depth; } nv_host_cmx_gm2;
typedef struct {
    int cc1, cc2;
    double depth[6][11];
    int ngm2;
    nv_host_cmx_gm2 gm2[32];
} nv_host_cmx;
int nv_host_cmx_state(nv_host *h, int channel, nv_host_cmx *out);     /* 0; -1 not read */
/* a cell set to a GS byte (nv_host_cmx_raw's), or CC1/CC2's number (which 4
   or 5, 0-95), as a sequencer's GS message; channel -1 every channel */
void nv_host_cmx_cell(nv_host *h, int channel, int src, int dest, int raw);
void nv_host_cmx_assign(nv_host *h, int channel, int which, int cc);
/* a destination's GS byte range (lo, hi), a byte's depth, the byte nearest a
   depth, a depth as printed ("+2 semitones", "47 cents") */
void nv_host_cmx_range(int dest, int *lo, int *hi);
double nv_host_cmx_depth(int dest, int raw);
int nv_host_cmx_raw(int dest, double depth);
int nv_host_cmx_printed(int dest, double depth, char *out, int cap);
/* the last controller moved (its number, when: a steady-clock ns; 0 none) --
   CC1/CC2 learnt from it */
int nv_host_last_ctl(nv_host *h, long long *when_ns);
long long nv_host_now_ns(void);

/* ---- A PART's PAN AND SENDS (livetui's part columns): its channel's CC10
   (as the part was sent it), CC91 reverb, CC93 chorus, CC94 delay, and
   NV_HOST_VSENSE the velocity sense depth (GS 40 1p 1A: no CC carries it);
   set as a sequencer's message, channel -1 every channel */
#define NV_HOST_VSENSE 1000
int nv_host_chan_cc(nv_host *h, int channel, int cc);
void nv_host_chan_cc_send(nv_host *h, int channel, int cc, int v);

/* ---- ON-SCREEN CONTROLS (livetui's controls pane; the session's "controls") ----
   the controls one may add: "key\tlabel\tkind\tdefault" lines (key a CC, -1
   the pitch wheel, -2 aftertouch, -3 mono; kind switch, selector, bend,
   pressure or continuous) */
int nv_host_control_kinds(char *out, int cap);
typedef struct { int key, channel, value, hotkey, on; } nv_host_control;   /* on: a switch's state now */
int nv_host_controls(nv_host *h, nv_host_control *out, int cap);          /* how many; up to cap copied */
/* added (at its default, sending nothing): its index */
int nv_host_control_add(nv_host *h, int key, int channel);
void nv_host_control_remove(nv_host *h, int index);
/* set to v and sent past the routes (every channel, or its own); a bend
   -8192..8191, the rest 0-127 */
void nv_host_control_set(nv_host *h, int index, int v);
void nv_host_control_hotkey(nv_host *h, int index, int key);              /* 0 none */

/* ---- ROUTES (livetui's routes): the keyboard's own controls rewritten before
   the engine sees them -- each nv_rt_add's seven: source kind (0 a CC, 1 the
   pitch wheel, 2 aftertouch, 3 a key), its number (the CC; the wheel 0 up, 1
   down, 2 either; the key), the destination (a control's key), keep the
   original (1), channel (-1 all), toggle (1, a key to a switch), on (1) */
int nv_host_routes(nv_host *h, int *out7, int cap);                       /* how many; cap routes copied */
int nv_host_route_text(const int *r7, char *out, int cap);                /* "key C1 -> sustain  held ..." */
void nv_host_route_add(nv_host *h, const int *r7);
void nv_host_route_remove(nv_host *h, int index);
/* a key learnt (a route from a key): armed, then the next note-on's channel
   and note (1 got one) */
void nv_host_learn_key(nv_host *h, int on);
int nv_host_learnt_key(nv_host *h, int *channel, int *note);

/* ---- SCENES (livetui's N, R: scenes.json beside the session): each
   channel's controls saved, recalled ---- */
int nv_host_scenes(nv_host *h, char *names, int cap);                     /* '\n'-separated */
int nv_host_scene_save(nv_host *h, const char *name, char *msg, int cap);
int nv_host_scene_recall(nv_host *h, const char *name, char *msg, int cap);

/* a GS Reset, as a sequencer sends it (every part to program 0, controllers,
   system effects and receive settings to power-on) */
void nv_host_gs_reset(nv_host *h);

/* ---- THE USER DRUM SETS (livetui's U): GS programs 65, 66 ----
   the sets a key may take its sound from and their keys' names: "S\tset\tname"
   and "K\tset\tkey\tname" lines (the export's DKEY) */
int nv_host_udrum_tables(nv_host *h, char *out, int cap);
/* user set `set` (0, 1) as set: out[key * 16 + code] for GS 21's codes (0x01
   play note, 0x02 level, 0x04 pan, 0x08 receive note on, 0x0B the source
   set, 0x0C its key), -1 not set; 0, -1 not read */
int nv_host_udrum_state(nv_host *h, int set, int *out);
/* one setting, as a sequencer's GS message */
void nv_host_udrum_send(nv_host *h, int set, int key, int code, int v);

/* the live part it plays (native.py's nv_part_*: a check reads its slab) */
void *nv_host_part(nv_host *h);

/* ---- THE TOUCH INTERFACE (uiapi.cpp; ui/) ----
   One viewer's watch (its selected part, what it was last sent); a request
   as JSON ({"call": ..., "id": ...}), its answer as JSON; and what changed
   since the viewer last asked (NULL: nothing) -- the meters while anything
   sounds, the parts and its part's knobs when they move. The strings are
   the caller's to free (nv_ui_free). Never on the audio thread. */
typedef struct nv_ui_watch nv_ui_watch;
nv_ui_watch *nv_ui_watch_new(void);
void nv_ui_watch_free(nv_ui_watch *w);
char *nv_ui_call(nv_host *h, nv_ui_watch *w, const char *request);
char *nv_ui_poll(nv_host *h, nv_ui_watch *w);
void nv_ui_free(char *s);
/* the interface's QUIT (call "quit"): set by a host that may be quit from
   it (nvlive); unset, the call is refused */
extern void (*nv_ui_quit)(void);
/* the Files card's: the file export best-quality renders use (nvrender's,
   not --live) and the folder renders go to; at the end, its player and
   render stopped */
void nv_ui_files_config(const char *file_export, const char *renders);
/* the app's folders: where MIDI files are browsed from and renders go (an iOS
   app's Documents), and a render's working files (its tmp); NULL the defaults
   (~/Music, $TMPDIR or /tmp) */
void nv_ui_files_dirs(const char *music, const char *tmp);
void nv_ui_files_shutdown(nv_host *h);

#ifdef __cplusplus
}
#endif
#endif
