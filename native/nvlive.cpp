// nvlive.cpp -- the native live engine: a MIDI keyboard in, audio out, no
// Python at runtime.
//
//     nvlive EXPORT.nvx [--program=N [--drums]] [--midi=/dev/snd/midiCxDy] [--device=default] [--latency-ms=10]
//                       [--cpu | --gpu[=cl|c]] [--no-pipeline] [--slots=N]
//                       [--drum-set=P | --no-drums] [--split=N [--split-channel=C] [--split-transpose=T]]
//                       [--no-register] [--pedal-key=N] [--press-db=DB] [--gpu[=cl|c]] [--gpu-min=N]
//                       [--no-rt] [--rt-prio=N] [--reg-sync] [--no-governor] [--dry] [--no-panel]
//                       [--tuner=NAME [--a=HZ | --c=HZ]] [--eastern=SPEC]
//     nvlive EXPORT.nvx --test IN.mid OUT.wav [--program=N] [--seconds=S] [--no-register] [--pedal-key=N]
//                       [--rt] [--reg-async] [--async] [--govern]
//
// EXPORT.nvx is examples/native_export.py --live's. At start the part's
// templates are built (live.Patch.warm: every key 21-96 at each velocity
// bucket, natively), then live's callback runs block by block, 128 samples
// at 48 kHz: the block's MIDI applied at its start, the sweep, the reap,
// the render (native/slab.cpp: bit for bit live.Live's on the CPU), out to
// ALSA. MIDI is read raw from the keyboard's device file; ALSA's PCM is
// loaded at run time (libasound.so.2), so nothing needs its headers.
//
// --test: no devices. IN.mid's notes and controllers (native/midi.cpp, in
// message order) each applied at the start of the block its time falls in,
// each block's output (live's callback: the render, the room, the limiter)
// written to OUT.wav as float32 -- what examples/nvlive_check.py compares
// with live.Live fed the same events.
//
// THE REGISTER (the free strings answering, live's _reg_*) when the export
// has the program's (its LREG section), unless --no-register. Playing, its
// jobs are answered on a thread of their own, off the audio thread, and
// placed when ready -- as live's worker process does (--reg-sync: answered
// as they are sent, in the block); --test answers them in step, as the
// checks do, so its output is the same every run.
//
// REAL-TIME when playing (live's rtsched, its default): the audio thread
// SCHED_RR 18, directly or through rtkit, guarded against a runaway block
// (--no-rt or TUNING_RT=0: not). On Ctrl-C it reports its blocks over
// budget and ALSA's underruns.
//
// THE DAMPERS IN BETWEEN (live._damp_block): a pedal value in damper.py's
// band takes a pedalled key down by its level, through synth_voice_damp.
// THE ROUTES (live.Route): the session's, from the export, ahead of the
// part (slab.cpp's Router) -- and --pedal-key=N, MIDI key N as the sustain
// pedal, pushed into to lower the dampers: held, CC64 127; channel
// aftertouch while it is held, 127 - pressure; up, 0.
//
// THE GPU, by default (live's --gpu; --cpu: none): live.GpuRenderer's
// block -- its setup on the CPU (voice_block, from the export's LGPU
// builds), the samples on OpenCL (native/gpu.cpp, gpukernel.cl) -- for a
// block with 100 busy slots or more (--gpu-min; live's GPU_MIN is 1000, set
// for Python's costs). PIPELINED on OpenCL (live's TUNING_GPU_PIPELINE;
// --no-pipeline: not): every block a block late, the CPU's setup of the
// next while the GPU renders this one. --gpu=c runs the samples through the
// C reference (voice_samples) instead, to check the setup without a GPU.
//
// THE SLAB: --slots (65536, live's capacity: a vibraslap's strike is 16524
// rows).
//
// PRESSURE (channel aftertouch): the notes on its channel lifted by the
// export's press_db (tonelib.PRESS_DB; --press-db=DB for Ben's session's) at
// full, as live's Slab.press does a piano (no tilt: effort_tilt 0).
//
// THE GOVERNOR when playing (live's; --no-governor: none): when blocks run
// over 95% of their time (the second smallest of the last four), the
// highest tenth of what sounds is faded out over 5 ms; --test takes
// --govern to time it, its output then the machine's.
//
// THE WHEELS: the pitch wheel over GM's 2 semitones (live._repitch); the mod
// wheel on a honky-tonk picks its detune, and on the other pianos does
// nothing, as live's (a hammered string takes no vibrato).
//
// AFTER THE RENDER, as live's callback: the room's late tail on the send
// (the export's room, live's convolver; --dry: none) and the soft limiter.
// The export takes the session's room, master level, headroom, pressure,
// knee and wheel range, as live starts.
//
// THE RPNs as live reads them: the bend range, fine and coarse tuning (the
// notes sounding moved), the mod range; CC121; sostenuto (CC66).
//
// ALL SOUND OFF, ALL NOTES OFF and the channel modes (CC120, 123, 124-127):
// MONO (126) one voice a channel, handed over to each new key and back to
// the last one held, POLY (127) as many as are played.
//
// PORTAMENTO (CC5, 65, 84) is ignored, as live ignores it on a piano: a
// glide is a voice's mechanism (live._glide), and no piano class has one.
//
// THE PANEL (native/panel.h), playing on a terminal (--no-panel: none, and
// Ctrl-C to stop): live's for this piano -- the globals, the controls and
// routes (added and taken away here, kept beside the export in
// EXPORT.nvx.routes and read back next time), the output's meters, panic.
// The audio runs on its own thread; the panel's changes are done between
// two blocks.

#include "hostlive.h"

int nv_host::run(int argc, char **argv)
{
    int rc = open(argc, argv);
    if (rc != -1)
        return rc;
    // --programs (--test): the file's program changes followed, as live's
    // builder in step (examples/patchsync.py); else, as before, not
    follow = false;
    for (int i = 1; i < argc; i++)
        follow = follow || !strcmp(argv[i], "--programs");
    // --test: a file's events, block by block, to the dry blocks
    for (int i = 1; i + 2 < argc; i++)
        if (!strcmp(argv[i], "--test")) {
            FILE *mf = fopen(argv[i + 1], "rb");
            if (!mf) {
                fprintf(stderr, "nvlive: cannot read %s\n", argv[i + 1]);
                return 1;
            }
            std::vector<uint8_t> bytes;
            for (int c; (c = fgetc(mf)) != EOF;)
                bytes.push_back((uint8_t)c);
            fclose(mf);
            int err = 0;
            void *m = nv_midi_read(bytes.data(), (long long)bytes.size(), &err);
            if (!m) {
                fprintf(stderr, "nvlive: the reader refused %s (%d)\n", argv[i + 1], err);
                return 2;
            }
            if (nv_midi_banked(m) && !follow) {     // (followed, its banks are live's: bank select)
                fprintf(stderr, "nvlive: refused: %s selects a bank (only with --programs)\n", argv[i + 1]);
                return 2;
            }
            int ne = nv_midi_n_events(m);
            double secs = atof(opt(argc, argv, "seconds", "0").c_str());
            if (secs <= 0)
                secs = nv_midi_total(m) + 3.0;
            long long nb = (long long)(secs * SR) / BLK;
            // timing as played: --reg-async (the register off this thread; the
            // output then varies run to run) and --rt (this thread real-time)
            for (int q = 1; q < argc; q++) {
                if (!strcmp(argv[q], "--reg-async"))
                    nv_part_reg_async(part);
                if (!strcmp(argv[q], "--async")) {         // ...and the scanner's and valve's workers, as played
                    nv_part_scan_async(part);
                    nv_part_amp_async(part);
                }
                if (!strcmp(argv[q], "--rt")) {
                    std::string why = rt::promote(rt::PRIO);
                    fprintf(stderr, "nvlive: %s\n", why.empty() ? "real-time, SCHED_RR 18" : ("not real-time: " + why).c_str());
                }
            }
            bool tgov = false;
            for (int q = 1; q < argc; q++)
                tgov = tgov || !strcmp(argv[q], "--govern");
            govern = tgov;
            asks = follow;
            std::vector<float> out;
            std::vector<float> buf(2 * BLK);
            std::vector<double> ms, msr, mss, msg;      // each block's events, step and render, ms; its render;
                                                        // a GPU block's setup and samples
            std::vector<double> mstep, mcpu;            // the step (events, register, dampers); a CPU block's render
            int e = 0;
            for (long long b = 0; b < nb; b++) {
                auto t0 = std::chrono::steady_clock::now();
                long long n0 = b * BLK;
                g_msgr_blk = b;                         // (--messenger-log's block)
                const std::string *room_want = nullptr;     // (two in a block: the last, as live's queue)
                for (const auto &ra : room_at)
                    if (ra.first == b)
                        room_want = &ra.second;
                if (room_want) {
                    void *room_new = nullptr;
                    if (room_switch(*room_want, &room_new, [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                            swap(i_, p_, d_, v_, c_);
                        })) {
                        step_room = room_new;
                        fprintf(stderr, "nvlive: room %s at block %lld\n", room_want->c_str(), b);
                    } else {
                        fprintf(stderr, "nvlive: room %s: not this export's, or the room already\n", room_want->c_str());
                    }
                }
                // the block's events, to the queue the keyboard's go to
                {
                    std::lock_guard<std::mutex> lk(mu);
                    while (e < ne) {
                        int iv[4];
                        double et;
                        nv_midi_event(m, e, iv, &et);
                        if ((long long)(et * SR) / BLK > b)
                            break;                      // a later block's
                        Midi ev{iv[0], iv[1], iv[2], iv[3], {}};
                        bool keep = true;
                        if (iv[0] == 6) {               // an exclusive: its bytes
                            std::vector<uint8_t> xb(65536);
                            int xn = nv_midi_sysex(m, iv[2], xb.data(), (int)xb.size());
                            keep = xn > 0 && xn <= (int)xb.size();
                            if (keep)
                                ev.x.assign(xb.begin(), xb.begin() + xn);
                        }
                        if (keep)
                            q.push_back(std::move(ev));
                        e++;
                    }
                }
                render_block(n0, buf.data(), true);
                msr.push_back(last_out_ms);
                mstep.push_back(last_step_ms);
                if (!nv_part_on_gpu(part))
                    mcpu.push_back(msr.back());
                if (nv_part_on_gpu(part)) {
                    double g2[2];
                    nv_part_gpu_ms(part, g2);
                    mss.push_back(g2[0]);
                    msg.push_back(g2[1]);
                }
                ms.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count());
                out.insert(out.end(), buf.begin(), buf.end());
            }
            // the blocks' times against the block's own length
            if (!ms.empty()) {
                std::vector<double> o = ms;
                std::sort(o.begin(), o.end());
                double sum = 0.0, budget = 1000.0 * BLK / SR;
                long over = 0;
                for (double x : o) {
                    sum += x;
                    over += x > budget;
                }
                fprintf(stderr, "nvlive: blocks %.3f ms mean, %.3f p99, %.3f worst; %ld of %zu over %.2f ms\n",
                        sum / o.size(), o[o.size() * 99 / 100], o.back(), over, o.size(), budget);
                // ...the render's share, and a GPU block's two halves
                auto stat = [&](const char *what, std::vector<double> v) {
                    if (v.empty())
                        return;
                    std::sort(v.begin(), v.end());
                    double t = 0.0;
                    for (double x : v)
                        t += x;
                    fprintf(stderr, "nvlive:   %s %.3f ms mean, %.3f p99, %.3f worst (%zu blocks)\n", what,
                            t / v.size(), v[v.size() * 99 / 100], v.back(), v.size());
                };
                stat("render", msr);
                stat("step", mstep);
                stat("CPU render", mcpu);
                stat("GPU setup", mss);
                stat("GPU samples", msg);
                if (tgov)
                    fprintf(stderr, "nvlive:   the governor shed %ld partials\n", nv_part_partials_shed(part));
            }
            nv_midi_free(m);
            if (follow)
                fprintf(stderr, "nvlive: %ld program change(s) followed\n", step_swaps);
            FILE *wf = fopen(argv[i + 2], "wb");
            if (!wf)
                return 1;
            uint32_t data = (uint32_t)(out.size() * 4);
            auto u32 = [&](uint32_t v) { fwrite(&v, 4, 1, wf); };
            auto u16 = [&](uint16_t v) { fwrite(&v, 2, 1, wf); };
            fwrite("RIFF", 1, 4, wf); u32(36 + data); fwrite("WAVE", 1, 4, wf);
            fwrite("fmt ", 1, 4, wf); u32(16); u16(3); u16(2); u32((uint32_t)SR); u32((uint32_t)SR * 8); u16(8);
            u16(32);
            fwrite("data", 1, 4, wf); u32(data);
            fwrite(out.data(), 4, out.size(), wf);
            fclose(wf);
            fprintf(stderr, "nvlive: %lld blocks -> %s\n", nb, argv[i + 2]);
            return 0;
        }
    // LIVE: the keyboard in, ALSA out
    dev = opt(argc, argv, "midi", "");
    if (dev.empty()) {
        for (int c = 0; c < 8 && dev.empty(); c++)
            for (int d = 0; d < 4 && dev.empty(); d++) {
                char p[64];
                snprintf(p, sizeof p, "/dev/snd/midiC%dD%d", c, d);
                if (access(p, R_OK) == 0)
                    dev = p;
            }
    }
    fd = dev.empty() ? -1 : ::open(dev.c_str(), O_RDONLY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "nvlive: no MIDI input (%s); --midi=/dev/snd/midiCxDy\n", dev.c_str());
        return 1;
    }
    if (!A.load()) {
        fprintf(stderr, "nvlive: cannot load libasound.so.2\n");
        return 1;
    }
    pcmdev = opt(argc, argv, "device", "default");
    lat = (unsigned)(1000 * atof(opt(argc, argv, "latency-ms", "10").c_str()));
    r = A.open(&A.pcm, pcmdev.c_str(), 0 /* playback */, 0);
    if (r >= 0)
        r = A.set_params(A.pcm, 14 /* FLOAT_LE */, 3 /* RW_INTERLEAVED */, 2, (unsigned)SR, 1, lat);
    if (r < 0) {
        fprintf(stderr, "nvlive: ALSA %s: %s\n", pcmdev.c_str(), A.strerror(r));
        return 1;
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    reader = std::thread(midi_reader, fd, &mu, &q);
    // the register's jobs on their own thread, off the audio one (--reg-sync: in step)
    rsync = false; nort = getenv("TUNING_RT") && !strcmp(getenv("TUNING_RT"), "0"); nopanel = !isatty(1);
    for (int i = 1; i < argc; i++) {
        rsync = rsync || !strcmp(argv[i], "--reg-sync");
        nort = nort || !strcmp(argv[i], "--no-rt");
        nopanel = nopanel || !strcmp(argv[i], "--no-panel");
    }
    fprintf(stderr, "nvlive: playing (MIDI %s, audio %s, %u us); %s\n", dev.c_str(), pcmdev.c_str(), lat,
            nopanel ? "Ctrl-C to stop" : "the panel (q to stop)");
    start();                                      // the workers and the builder
    // THE AUDIO THREAD: real-time (--no-rt, TUNING_RT=0: not), block by block
    audio = [&]() {
        if (!nort) {
            int prio = atoi(opt(argc, argv, "rt-prio", std::to_string(rt::PRIO).c_str()).c_str());
            std::string why = rt::promote(prio);
            rt_on = why.empty();
            if (nopanel)
                fprintf(stderr, why.empty() ? "nvlive: real-time, SCHED_RR %d\n" : "nvlive: not real-time (%s)\n",
                        why.empty() ? prio : 0, why.c_str());
        }
        std::vector<float> buf(2 * BLK);
        long long n0 = 0;
        while (!g_stop) {
            render_block(n0, buf.data());
            long w = A.writei(A.pcm, buf.data(), (unsigned long)BLK);
            if (w < 0) {
                underruns += w == -32;                  // -EPIPE: the device ran dry
                // RECOVER AS PORTAUDIO DOES: the device prepared again, half
                // its buffer of silence ahead (a cushion, so one slow block in
                // a thick passage does not run it dry again, block after
                // block), and THIS block written after it rather than lost
                if (A.recover(A.pcm, (int)w, 1) >= 0) {
                    long half = std::max<long>(1, (long)((double)lat * 1e-6 * SR / 2.0 / BLK));
                    std::vector<float> zero(2 * BLK, 0.0f);
                    for (long q = 0; q < half; q++)
                        A.writei(A.pcm, zero.data(), (unsigned long)BLK);
                    A.writei(A.pcm, buf.data(), (unsigned long)BLK);
                }
                std::lock_guard<std::mutex> lk(pmu);
                snap.underruns = underruns;
            }
            n0 += BLK;
        }
    };
    player = std::thread(audio);
    if (nopanel) {
        while (!g_stop)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
    } else {
        // THE PANEL, on this thread
        panel::Host H;
        auto post = [&](std::function<void(long long)> f) {
            std::lock_guard<std::mutex> lk(pmu);
            posted.push_back(std::move(f));
        };
        H.take = [&]() {
            std::lock_guard<std::mutex> lk(pmu);
            panel::Snap s = snap;
            snap.ms_max = snap.ms_sum = 0.0;
            snap.ms_n = 0;
            snap.peak[0] = snap.peak[1] = 0.0f;
            return s;
        };
        H.learn = [&](bool on) {
            learnt_ch = learnt_note = -1;
            learning = on ? 1 : 0;
        };
        H.learnt = [&]() {
            return learning == 2 ? std::make_pair(learnt_ch.load(), learnt_note.load()) : std::make_pair(-1, -1);
        };
        H.rate = SR;
        H.frames = (int)BLK;
        H.budget_ms = budget;
        auto name_of = [&](int sp) {             // (sp: a program, or 128 + a drum set)
            const Export::Prog &pr = E.prog[sp & 127];
            return sp >= 128 ? (pr.kit.empty() ? "drum set" : pr.kit) : pr.name;
        };
        // ...a variation by its own name (VNAM), its program's otherwise
        auto shown_name = [&](int sp, int v) {
            for (size_t j = 0; j < E.vpv.size() && v && sp < 128; j++)
                if (E.vpv[j][0] == sp && E.vpv[j][1] == v)
                    return E.vnames[j];
            return name_of(sp);
        };
        H.program = program;
        H.program_name = shown_name(shown_program, shown_var);
        H.port = dev;
        H.room = E.room.empty() ? "-" : E.room;
        H.reg_modes = rg0->M > 0 && !noreg ? rg0->M : 0;
        double st[15];
        nv_part_stats(part, st);
        H.has_gpu = st[12] > 0.5;
        H.has_room = st[11] > 0.5;
        H.g[0] = 20.0 * log10(std::max(master, 1e-12));
        H.g[1] = -20.0 * log10(std::max(E.headroom, 1e-12));
        H.g[2] = E.k.size() > K_THRESH ? E.k[K_THRESH] : 0.70;
        H.g[3] = E.k.size() > K_BEND_RANGE ? E.k[K_BEND_RANGE] : 2.0;
        H.g[4] = 35.0;
        H.g[5] = E.k.size() > K_PRESS_DB ? E.k[K_PRESS_DB] : 8.0;
        H.g[6] = H.has_gpu ? 1.0 : 0.0;
        H.g[7] = H.has_room ? 1.0 : 0.0;
        for (const auto &r : E.rooms)
            H.rooms.push_back(r.name);
        H.g[8] = room_idx;
        H.set_global = [&](int i, double v) {
            if (i == 8) {                               // THE ROOM: the builder's (live.set_room)
                int k = (int)v;
                if (k >= 0 && k < (int)E.rooms.size()) {
                    std::lock_guard<std::mutex> lk(bmu);
                    room_req = E.rooms[k].name;
                }
                bcv.notify_one();
                return;
            }
            post([&, i, v](long long) {
                switch (i) {
                case 0: master_now = pow(10.0, v / 20.0); break;     // T.master_gain
                case 1: nv_part_set(part, 0, v); break;
                case 2: nv_part_set(part, 2, v); break;
                case 3: nv_part_set(part, 3, v); break;
                case 4: nv_part_set(part, 4, v); break;
                case 5: nv_part_set(part, 1, v); break;
                case 6: nv_part_set(part, 5, v); break;
                case 7: nv_part_set(part, 6, v); break;
                }
            });
        };
        H.routes = E.routes;
        if (!pks.empty())
            H.routes.push_back(pedal_route);
        H.add_route = [&](const std::array<int, 7> &a) {
            post([&, a](long long) { nv_rt_add(router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]); });
        };
        H.del_route = [&](int i) { post([&, i](long long) { nv_rt_del(router, i); }); };
        H.panic = [&]() { post([&](long long n) { nv_part_panic(part, n); }); };
        // AN ORGAN'S STOPS (live's panel): its ranks, drawn and put in between two blocks
        auto stops_of = [&](int sp) {
            H.stop_names.clear();
            H.stop_rows.clear();
            if (sp >= 128 || E.stops[sp].names.empty())
                return;
            H.stop_names = E.stops[sp].names;
            H.stop_rows = E.stops[sp].rows;
            H.drawn = [&, nr = (int)E.stops[sp].names.size()]() {
                std::vector<char> d(nr, 0);
                nv_part_drawn(part, d.data(), nr);
                return d;
            };
            H.toggle_stop = [&](int ri) { post([&, ri](long long n) { nv_part_toggle_stop(part, ri, n); }); };
        };
        stops_of(shown_program);
        // THE PICKER: every program and set, which are native, and one picked
        // asked for on the part (posted: live's change_patch, a set or not)
        H.names.assign(256, "");
        H.native.assign(256, 0);
        for (int sp = 0; sp < 256; sp++) {
            H.names[sp] = sp < 128 ? E.prog[sp].name : E.prog[sp & 127].kit;
            bool nat = false;
            for (int k = 0; k < 128 && !nat; k++)
                nat = E.cmap[(sp >= 128 ? NV_K_DRUMS : 0) + 128 * (sp & 127) + k] >= 0;
            H.native[sp] = nat && (sp >= 128 ? !H.names[sp].empty() : E.part[sp][0] != 0);
        }
        H.kit = shown_program >= 128;
        // ...the variations (VNAM), native where every key of their slots the
        // capital plays is one the engine plays too
        H.vpv = E.vpv;
        H.vnames = E.vnames;
        H.vnative.assign(E.vpv.size(), 0);
        for (size_t j = 0; j < E.vpv.size(); j++) {
            int p = E.vpv[j][0], en = var_entry_of(p, E.vpv[j][1]);
            bool nat = en > 0 && (j < E.vpart.size() ? E.vpart[j][0] : E.part[p][0]) != 0;
            for (const auto &l : en > 0 ? E.vents[en].ls : std::vector<std::array<int, 4>>())
                for (int k = 0; k < 128 && nat; k++)
                    nat = k + l[1] < 0 || k + l[1] > 127 || E.vmap[128 * (size_t)l[0] + k + l[1]] >= 0
                          || E.cmap[128 * p + k] < 0;
            H.vnative[j] = nat;
        }
        H.var = shown_var;
        H.channel = pats[0].channel;
        // THE INSERTION EFFECT: its tables, a setting sent as the GS exclusive
        // a file would carry (live.efx_send: into the block's events), the
        // controller last moved (the learn)
        panel::efx_tables(H, E.efxu);
        if (!H.efx_types.empty())
            H.efx_send = [&](const std::vector<uint8_t> &m) {
                post([&, m](long long) { nv_part_sysex(part, m.data(), (int)m.size()); });
            };
        H.last_ctl = [&]() { return std::make_pair(last_ctl_code.load(), last_ctl_ns.load()); };
        if (E.has_prog)
            H.pick = [&](int sp) {
                post([&, sp](long long) {
                    const PartAt &pa = pats[0];
                    if (sp >= 256) {            // (a variation: its program under its bank)
                        int p = E.vpv[sp - 256][0], v = E.vpv[sp - 256][1];
                        if (pa.program != p || pa.var != v || pa.drums)
                            reqs.push_back(Req{0, p, false, v});
                    } else if (pa.program != (sp & 127) || pa.drums != (sp >= 128) || pa.var) {
                        reqs.push_back(Req{0, sp & 127, sp >= 128});
                    }
                });
            };
        // ...A PROGRAM CHANGE FROM THE KEYBOARD: its name and its stops, and
        // what the builder said
        int shown = shown_program, shown_v = shown_var, shown_room = room_idx;
        H.refresh = [&]() {
            if (room_idx != shown_room) {               // (a room switched to: its name, its global)
                shown_room = room_idx;
                H.g[8] = shown_room;
                if (shown_room >= 0 && shown_room < (int)E.rooms.size())
                    H.room = E.rooms[shown_room].name;
            }
            int sp = shown_program, sv = sp >= 128 ? 0 : shown_var.load();
            std::string m;
            if (sp != shown || sv != shown_v) {
                shown = sp;
                shown_v = sv;
                H.program = sp & 127;
                H.kit = sp >= 128;
                H.var = sv;
                H.program_name = shown_name(sp, sv);
                stops_of(sp);
                m = (sp >= 128 ? "drum set " : "program ") + std::to_string(sp & 127)
                    + (sv ? "." + std::to_string(sv & 127) : "") + ": " + H.program_name;
            }
            std::lock_guard<std::mutex> lk(bmu);
            for (auto &x : notes)
                m = m.empty() ? x : m + "; " + x;
            notes.clear();
            return m;
        };
        bool edited = false;
        auto was = H.routes;
        panel::Panel P(H);
        P.run([&]() { return !g_stop.load(); });
        g_stop = true;
        edited = H.routes != was;
        // ROUTES ADDED OR TAKEN AWAY HERE are kept beside the export, and read
        // back the next time (--pedal-key's own not among them)
        if (edited) {
            if (FILE *wf = fopen(routes_file.c_str(), "w")) {
                bool skipped = pks.empty();
                for (auto &a : H.routes) {
                    if (!skipped && a == pedal_route) {
                        skipped = true;
                        continue;
                    }
                    fprintf(wf, "%d %d %d %d %d %d %d\n", a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
                }
                fclose(wf);
                fprintf(stderr, "nvlive: routes kept in %s\n", routes_file.c_str());
            }
        }
    }
    g_stop = true;
    player.join();
    bcv.notify_all();
    builder.join();
    fprintf(stderr, "nvlive: %ld blocks, %ld over %.2f ms (worst %.2f), %ld underruns, %ld partials shed%s\n", blocks,
            over, budget, worst, underruns, nv_part_partials_shed(part),
            rt::dropped ? ", real-time dropped by the guard" : "");
    if (nv_part_dropped(part))              // (the slab full: notes that never sounded)
        fprintf(stderr, "nvlive: %ld notes found the slab full (%ld slots) and did not sound: raise --slots\n",
                nv_part_dropped(part), slots);
    reader.join();
    A.close(A.pcm);
    ::close(fd);
    fprintf(stderr, "nvlive: stopped\n");
    return 0;
}

int main(int argc, char **argv)
{
    return (new nv_host())->run(argc, argv);    // (never freed: its threads run to the end)
}
