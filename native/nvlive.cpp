// nvlive.cpp -- the native live engine: a MIDI keyboard in, audio out, no
// Python at runtime.
//
//     nvlive EXPORT.nvx [--program=N [--drums]] [--port=NAME | --midi=/dev/snd/midiCxDy] [--device=default] [--latency-ms=10]
//                       [--cpu | --gpu[=cl|c]] [--no-pipeline] [--slots=N]
//                       [--drum-set=P | --no-drums] [--split=N [--split-channel=C] [--split-transpose=T]]
//                       [--no-register] [--pedal-key=N] [--press-db=DB] [--gpu[=cl|c]] [--gpu-min=N]
//                       [--no-rt] [--rt-prio=N] [--reg-sync] [--no-governor] [--dry] [--no-panel]
//                       [--tuner=NAME [--a=HZ | --c=HZ]] [--eastern=SPEC] [--eastern-at=S:SPEC]
//     nvlive EXPORT.nvx --test IN.mid OUT.wav [--program=N] [--seconds=S] [--no-register] [--pedal-key=N]
//                       [--rt] [--reg-async] [--async] [--govern] [--paced] [--build-async] [--tuner-at=S:NAME] [--preset-at=S:NAME] [--metronome=BPM[:RING]]
//
// EXPORT.nvx is examples/native_export.py --live's. At start the part's
// templates are built (live.Patch.warm: every key 21-108 at each velocity
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

#include <poll.h>
#include "hostlive.h"

int nv_host::run(int argc, char **argv)
{
    int rc = open(argc, argv);
    if (rc != -1)
        return rc;
    // --fixed-touch=0|1 (live's part.fixed_touch on the first part)
    {
        std::string ft = opt(argc, argv, "fixed-touch", "");
        if (!ft.empty())
            part_touch(0, atoi(ft.c_str()) ? 1 : 0);
    }
    // --metronome=BPM[:RING] (live's): its part built now, before the first
    // block -- so it strikes from beat one there, as live's set before its first callback
    {
        std::string mt = opt(argc, argv, "metronome", "");
        if (!mt.empty() && atof(mt.c_str()) > 0.0) {
            size_t c = mt.find(':');
            gval[10] = atof(mt.c_str());
            gval[11] = c == std::string::npos ? 0.0 : (double)atoi(mt.c_str() + c + 1);
            PartSpec sp;
            sp.drums = true;
            sp.channel = 9;
            sp.metro = true;
            part_added(sp, build(0, true, 0));
            fprintf(stderr, "nvlive: the metronome at %g bpm, the bell every %g\n", gval[10], gval[11]);
        }
    }
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
            // --paced: each block started at its time as played (a block's
            // length after the one before), not as soon as the last ends --
            // the machine idling between them, as it does under a keyboard
            bool paced = false;
            for (int q = 1; q < argc; q++)
                paced = paced || !strcmp(argv[q], "--paced");
            // --build-async (with --programs): the programs built on the
            // builder thread, as played -- swapped in when ready, the blocks
            // going on meanwhile (best --paced; the output then varies run to run)
            bool basync = false;
            for (int q = 1; q < argc; q++)
                basync = basync || !strcmp(argv[q], "--build-async");
            if (basync)
                start();
            if (session_on) {                   // (--session=PATH named: taken, and written at the end)
                globals_init();
                session_apply();
            }
            std::string trec = opt(argc, argv, "record", "");      // (--record: written at the end)
            recording = !trec.empty();
            const auto tstart = std::chrono::steady_clock::now();
            asks = follow;
            std::vector<float> out;
            std::vector<float> buf(2 * BLK);
            std::vector<double> ms, msr, mss, msg;      // each block's events, step and render, ms; its render;
                                                        // a GPU block's setup and samples
            std::vector<double> mstep, mcpu;            // the step (events, register, dampers); a CPU block's render
            int e = 0;
            for (long long b = 0; b < nb; b++) {
                if (paced)
                    std::this_thread::sleep_until(tstart + std::chrono::nanoseconds((long long)((double)(b * BLK) * 1e9 / SR)));
                auto t0 = std::chrono::steady_clock::now();
                long long n0 = b * BLK;
                g_msgr_blk = b;                         // (--messenger-log's block)
                const std::string *room_want = nullptr;     // (two in a block: the last, as live's queue)
                const double *room_want_tl = nullptr;
                for (const auto &ra : room_at)
                    if (ra.first == b)
                        room_want = &ra.second;
                // ...or a sequencer's GS reverb, heard in the block before
                // (gs_reverb): switched here, in step, as live's check does
                std::string gs_room;
                double gs_tl[3];
                if (!room_want && gs_want) {
                    gs_room = gs_want_room;
                    for (int q = 0; q < 3; q++)
                        gs_tl[q] = gs_want_tl[q];
                    room_want = &gs_room;
                    room_want_tl = gs_want_tl_on ? gs_tl : nullptr;
                    gs_want = false;
                } else if (room_want) {         // (a scripted room: the user's, over a sequencer's reverb)
                    user_room = *room_want;
                    gs_rev.clear();
                    gs_want = false;
                }
                {                                       // --preset-at=S:NAME: a preset loaded (presets.json beside the session)
                    std::string pa = opt(argc, argv, "preset-at", "");
                    size_t c = pa.find(':');
                    if (session_on && c != std::string::npos && (long long)(atof(pa.substr(0, c).c_str()) * SR) / BLK == b) {
                        sess::J d;
                        const sess::J *p = sess::load(presets_path(), d) ? d.get(pa.substr(c + 1)) : nullptr;
                        if (p && p->is(sess::J::OBJ)) {
                            apply_setup(*p, false);
                            fprintf(stderr, "nvlive: preset %s at block %lld\n", pa.substr(c + 1).c_str(), b);
                        }
                    }
                }
                {                                       // --tuner-at=S:NAME: a tuner switched to, in step
                    std::string ta = opt(argc, argv, "tuner-at", "");
                    size_t c = ta.find(':');
                    if (c != std::string::npos && (long long)(atof(ta.substr(0, c).c_str()) * SR) / BLK == b) {
                        int nb_ = 0;
                        tuner_switch(ta.substr(c + 1), [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                            swap(i_, p_, d_, v_, c_);
                            nb_++;
                        });
                        fprintf(stderr, "nvlive: tuner %s at block %lld (%d patch(es))\n", ta.substr(c + 1).c_str(), b, nb_);
                    }
                }
                {                                       // --eastern-at=S:SPEC: the Eastern tuning switched to, in step ("off": none)
                    std::string ea = opt(argc, argv, "eastern-at", "");
                    size_t c = ea.find(':');
                    if (c != std::string::npos && (long long)(atof(ea.substr(0, c).c_str()) * SR) / BLK == b) {
                        std::string sp = ea.substr(c + 1);
                        int nb_ = 0;
                        east_switch(sp == "off" ? std::string() : sp, [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                            swap(i_, p_, d_, v_, c_);
                            nb_++;
                        });
                        fprintf(stderr, "nvlive: eastern %s at block %lld (%d patch(es))\n", sp.c_str(), b, nb_);
                    }
                }
                if (room_want) {
                    void *room_new = nullptr;
                    if (room_switch(*room_want, room_want_tl, &room_new, [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                            swap(i_, p_, d_, v_, c_);
                        })) {
                        step_room = room_new;
                        step_room_go = true;
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
                        ev.v = nv_midi_event_x(m, e);       // (MIDI 2.0's: a Note On's Pitch 7.9, a per-note value)
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
                render_block(n0, buf.data(), !basync);
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
            if (session_on) {
                std::vector<std::array<int, 7>> rs(E.routes.begin(), E.routes.end());
                scene_inline = true;            // (the blocks are done: the scene read here)
                session_save(rs);
            }
            if (basync) {
                g_stop = true;
                bcv.notify_all();
                builder.join();
            }
            if (recording)
                if (FILE *rf = fopen(trec.c_str(), "w")) {
                    for (auto &l : recq)
                        fprintf(rf, "%s\n", l.c_str());
                    fclose(rf);
                }
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
    // THE KEYBOARD (live.pick_port): --midi=/dev/snd/midiCxDy, else the raw
    // MIDI device whose name (/proc/asound/cardC/midiD's first line, as ALSA
    // names it) holds --port=NAME, any case -- else the first that is not a
    // loopback; a --port that matches nothing says so
    dev = opt(argc, argv, "midi", "");
    std::string port_name;
    cli_port = !dev.empty() || !opt(argc, argv, "port", "").empty();
    if (dev.empty()) {
        const std::vector<std::pair<std::string, std::string>> ds = midi_devices();
        auto lower = [](std::string x) {
            for (char &ch : x)
                ch = (char)tolower((unsigned char)ch);
            return x;
        };
        const std::string want = lower(opt(argc, argv, "port", ""));
        for (const auto &d : ds)
            if (!want.empty() && lower(d.second).find(want) != std::string::npos) {
                dev = d.first;
                port_name = d.second;
                break;
            }
        if (dev.empty()) {
            for (const auto &d : ds)
                if (lower(d.second).find("midi through") == std::string::npos) {
                    dev = d.first;
                    port_name = d.second;
                    break;
                }
            if (dev.empty() && !ds.empty()) {
                dev = ds[0].first;
                port_name = ds[0].second;
            }
            if (!want.empty()) {
                std::string all;
                for (const auto &d : ds)
                    all += (all.empty() ? "" : ", ") + d.second;
                fprintf(stderr, "nvlive: no MIDI input matches '%s'; using %s (inputs: %s)\n",
                        opt(argc, argv, "port", "").c_str(), port_name.empty() ? "none" : port_name.c_str(), all.c_str());
            }
        }
    }
    // (none: the panel's I opens one once it is plugged in; no panel, nothing to play)
    bool no_panel = !isatty(1);
    for (int i = 1; i < argc; i++)
        no_panel = no_panel || !strcmp(argv[i], "--no-panel");
    if (dev.empty() || access(dev.c_str(), R_OK) != 0) {
        if (no_panel) {
            fprintf(stderr, "nvlive: no MIDI input (%s); --midi=/dev/snd/midiCxDy\n", dev.c_str());
            return 1;
        }
        fprintf(stderr, "nvlive: no MIDI input yet -- I on the panel opens one\n");
        dev.clear();
    } else {
        ins.set({std::make_pair(dev, port_name.empty() ? dev : port_name)});
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
    reader = std::thread(midi_reader_ins, &ins, &mu, &q);
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
    // MIDI 2.0 (live --midi2, --midi2-pitch, --midi2-play, --ump, --ump-from):
    // the bridge; a Clip File or raw UMP stream played in on a thread of its
    // own, each packet at its time; a MIDI 2.0 port in the ALSA sequencer,
    // read on another -- each decoded to the engine's events and queued as
    // the keyboard's are, past the routes and the bridge (live.on_ump)
    std::thread m2play, umpthr;
    nv::ump::AlsaUmp uc;
    {
        bool want_bridge = false, want_ump = false;
        for (int i = 1; i < argc; i++) {
            want_bridge = want_bridge || !strcmp(argv[i], "--midi2");
            want_ump = want_ump || !strcmp(argv[i], "--ump");
        }
        const std::string spec = opt(argc, argv, "midi2-pitch", "");
        if (want_bridge || !spec.empty()) {
            if (!spec.empty() && !m2b.pt.parse(spec)) {
                fprintf(stderr, "nvlive: --midi2-pitch: 'just:<tonic>' (just:C, just:Eb, ...) or 'et'\n");
                return 1;
            }
            m2b.on = true;
            midi2_label = "MIDI 2.0 (bridged" + (spec.empty() ? std::string() : ", " + spec) + ")";
            fprintf(stderr, "nvlive: %s\n", midi2_label.c_str());
        }
        auto queue_ump = [this](const std::vector<uint32_t> &pk, std::map<int, std::vector<uint8_t>> &sxb) {
            std::vector<nv::ump::Ev> evs;
            nv::ump::decode(pk.data(), sxb, evs, &m2b.ignored);
            std::lock_guard<std::mutex> lk(mu);
            for (auto &e : evs) {
                Midi m{e.type, e.ch, e.a, e.b, e.x};
                m.v = e.v;
                m.ump = true;
                q.push_back(std::move(m));
            }
        };
        const std::string playf = opt(argc, argv, "midi2-play", "");
        if (!playf.empty()) {
            std::vector<uint8_t> fb;
            if (FILE *f = fopen(playf.c_str(), "rb")) {
                uint8_t chunk[65536];
                size_t n;
                while ((n = fread(chunk, 1, sizeof chunk, f)) > 0)
                    fb.insert(fb.end(), chunk, chunk + n);
                fclose(f);
            }
            std::vector<std::pair<double, std::vector<uint32_t>>> tl;
            if (!nv::ump::read_timeline(fb, tl)) {
                fprintf(stderr, "nvlive: --midi2-play: %s is not a MIDI Clip File or raw UMP stream\n", playf.c_str());
                return 1;
            }
            m2play = std::thread([tl, playf, queue_ump]() {
                std::map<int, std::vector<uint8_t>> sxb;
                const auto t0 = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
                for (const auto &e : tl) {
                    const auto at = t0 + std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                                             std::chrono::duration<double>(e.first));
                    while (!g_stop && std::chrono::steady_clock::now() < at)
                        std::this_thread::sleep_for(std::min<std::chrono::steady_clock::duration>(
                            at - std::chrono::steady_clock::now(), std::chrono::milliseconds(50)));
                    if (g_stop)
                        return;
                    queue_ump(e.second, sxb);
                }
                fprintf(stderr, "nvlive: %s: played %zu UMPs\n", playf.c_str(), tl.size());
            });
        }
        const std::string from = opt(argc, argv, "ump-from", "");
        if (want_ump || !from.empty()) {
            if (!uc.open("tuning") || (!from.empty() && !uc.connect_from(from))) {
                fprintf(stderr, "nvlive: --ump: %s\n", uc.err.c_str());
                return 1;
            }
            if (!from.empty()) {
                ins.set({});                    // (the keyboard comes through the kernel, not opened as well)
                midi2_label = "MIDI 2.0 (kernel bridge from " + from + ")";
            } else if (midi2_label.empty()) {
                midi2_label = "MIDI 2.0 port " + std::to_string(uc.client) + ":" + std::to_string(uc.port);
            }
            fprintf(stderr, "nvlive: ALSA MIDI 2.0 port %d:%d%s\n", uc.client, uc.port,
                    from.empty() ? "" : (", from " + from).c_str());
            umpthr = std::thread([this, &uc, queue_ump]() {
                std::map<int, std::vector<uint8_t>> sxb;
                std::vector<int> fds = uc.fds();
                std::vector<pollfd> pf;
                for (int fd : fds)
                    pf.push_back(pollfd{fd, POLLIN, 0});
                while (!g_stop) {
                    if (poll(pf.data(), pf.size(), 100) <= 0)
                        continue;
                    std::vector<std::vector<uint32_t>> got;
                    uc.read_pending(got);
                    for (auto &pk : got)
                        queue_ump(pk, sxb);
                }
            });
        }
    }
    std::thread recorder;
    std::string recf = opt(argc, argv, "record", "");
    if (!recf.empty()) {
        if (FILE *rf = fopen(recf.c_str(), "w")) {
            recording = true;
            recorder = std::thread([this, rf]() {
                while (true) {
                    bool last = g_stop;
                    std::vector<std::string> got;
                    {
                        std::lock_guard<std::mutex> lk(rec_mu);
                        got.swap(recq);
                    }
                    for (auto &l : got)
                        fprintf(rf, "%s\n", l.c_str());
                    fflush(rf);
                    if (last)
                        break;
                    std::this_thread::sleep_for(std::chrono::milliseconds(200));
                }
                fclose(rf);
            });
        } else {
            fprintf(stderr, "nvlive: cannot write %s\n", recf.c_str());
        }
    }
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
        globals_init();
        session_apply();
        while (!g_stop)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        std::vector<std::array<int, 7>> rs;
        for (auto &a : E.routes)
            rs.push_back(a);
        session_save(rs);
    } else {
        // THE PANEL, on this thread
        panel::Host H;
        auto post = [&](std::function<void(long long)> f) { this->post(std::move(f)); };
        globals_init();
        session_apply();
        patches_init();
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
        H.slots = slots;
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
        H.port = port_name.empty() ? (dev.empty() ? std::string("no MIDI in") : dev) : port_name;
        // THE MIDI INPUTS (livetui.pick_inputs): those plugged in, each on or
        // off -- several at once, merged; the header names those open
        H.inputs = [&]() {
            std::vector<std::pair<std::string, bool>> out;
            std::vector<std::pair<std::string, std::string>> w;
            {
                std::lock_guard<std::mutex> lk(ins.mu);
                w = ins.want;
            }
            in_list = midi_devices();
            for (auto &x : w) {                 // (wanted, gone: shown, to turn off)
                bool here = false;
                for (auto &d : in_list)
                    here = here || d.first == x.first;
                if (!here)
                    in_list.push_back(x);
            }
            for (auto &d : in_list) {
                bool on = false;
                for (auto &x : w)
                    on = on || x.first == d.first;
                out.push_back(std::make_pair(d.second + "  (" + d.first.substr(5) + ")", on));
            }
            return out;
        };
        H.input_toggle = [&](int i) -> std::string {
            if (i < 0 || i >= (int)in_list.size())
                return "";
            std::vector<std::pair<std::string, std::string>> w;
            {
                std::lock_guard<std::mutex> lk(ins.mu);
                w = ins.want;
            }
            const auto d = in_list[i];
            auto it = std::find_if(w.begin(), w.end(), [&](const std::pair<std::string, std::string> &x) {
                return x.first == d.first;
            });
            const bool off = it != w.end();
            if (off)
                w.erase(it);
            else
                w.push_back(d);
            ins.set(w);
            return "MIDI in: " + d.second + (off ? " off" : " on");
        };
        H.port_label = [&]() {
            std::lock_guard<std::mutex> lk(ins.mu);
            std::string l;
            for (auto &x : ins.open)
                l += (l.empty() ? "" : ", ") + x.second;
            if (l.empty())
                l = midi2_label.empty() ? std::string("no MIDI in") : std::string();
            return midi2_label.empty() ? l : l + (l.empty() ? "" : "  ") + midi2_label;     // (livetui's midi2_label)
        };
        H.room = E.room.empty() ? "-" : E.room;
        H.reg_modes = rg0->M > 0 && !noreg ? rg0->M : 0;
        H.has_gpu = gval[6] > 0.5;
        H.has_room = gval[7] > 0.5;
        for (int i = 0; i < panel::NGLOBALS; i++)
            H.g[i] = gval[i];
        for (const auto &r : E.rooms)
            H.rooms.push_back(r.name);
        H.set_global = [&](int i, double v) { set_global(i, v); };
        H.routes = E.routes;
        if (!pks.empty())
            H.routes.push_back(pedal_route);
        H.add_route = [&](const std::array<int, 7> &a) {
            post([&, a](long long) { nv_rt_add(router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]); });
        };
        H.del_route = [&](int i) { post([&, i](long long) { nv_rt_del(router, i); }); };
        H.panic = [&]() { panic(); };
        H.part_solo = [&](int i) { part_solo((size_t)i); };
        H.mpe_zones = [&]() { return nv_part_mpe_zones(part); };
        H.meters = [&]() { return meter; };
        H.gs_reset = [&]() {                    // (as a sequencer sends it: through the queue, live.gs_reset)
            std::vector<uint8_t> x{0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41};
            std::lock_guard<std::mutex> lk(mu);
            q.push_back(Midi{6, 0, 0, 0, x});
        };
        // AN ORGAN'S STOPS (live's panel): its ranks, drawn and put in between two blocks
        auto stops_of = [&](int sp) {
            H.stop_names.clear();
            H.stop_rows.clear();
            H.stop_breaks.clear();
            if (sp >= 128 || E.stops[sp].names.empty())
                return;
            H.stop_names = E.stops[sp].names;
            H.stop_rows = E.stops[sp].rows;
            H.stop_breaks = E.stops[sp].breaks;
            H.drawn = [&, nr = (int)E.stops[sp].names.size()]() {
                std::vector<char> d(nr, 0);
                nv_part_drawn(part, d.data(), nr);
                return d;
            };
            H.toggle_stop = [&](int ri) {
                post([&, ri](long long n) {
                    pending_drawn_prog = -1;            // (a stop drawn by hand: a preset's no longer)
                    nv_part_toggle_stop(part, ri, n);
                });
            };
        };
        stops_of(shown_program);
        // THE PICKER: every program and set, which are native, and one picked
        // asked for on the part (posted: live's change_patch, a set or not)
        H.names = pnames;
        H.native.assign(pnative.begin(), pnative.end());
        H.kit = shown_program >= 128;
        // ...the variations (VNAM), native where every key of their slots the
        // capital plays is one the engine plays too
        H.vpv = E.vpv;
        H.vnames = E.vnames;
        H.vnative.assign(vnative.begin(), vnative.end());
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
        // THE SYSTEM EFFECTS (G): as in effect, and a setting sent as a
        // sequencer's GS message, into the block's events (live.inject)
        H.sysfx_get = [&]() {
            panel::Host::SysFx s;
            static const int TIME[8] = {80, 56, 64, 72, 64, 88, 32, 64};
            auto at = [&](const std::map<int, int> &m, int k, int d) {
                auto it = m.find(k);
                return it != m.end() ? it->second : d;
            };
            s.rev_macro = at(gs_rev, 0x30, -1);
            s.rev_level = at(gs_rev, 0x33, 64);
            s.rev_time = at(gs_rev, 0x34, TIME[s.rev_macro >= 0 && s.rev_macro < 8 ? s.rev_macro : 4]);
            s.rev_fb = s.rev_macro == 6 || s.rev_macro == 7 ? at(gs_rev, 0x35, s.rev_macro == 6 ? 40 : 32) : -1;
            s.room = room_now;
            s.gs = nv_part_gs_fx(part, s.cho, s.dly) != 0;
            for (int k = 0; k < 4; k++)
                s.eq[k] = at(gs_eq, k, k % 2 ? 0x40 : 0);
            return s;
        };
        H.chan_cc = [&](int ch, int cc) {
            const int c = ch < 0 ? 0 : ch;
            if (cc == 10) {                     // (as the part was sent it, before master pan)
                auto pr = gs_pan_raw.find(c);
                if (pr != gs_pan_raw.end())
                    return pr->second;
            }
            return nv_part_chan_cc(part, c, cc);
        };
        H.chan_cc_send = [&](int ch, int cc, int v) {
            v = std::max(0, std::min(127, v));
            std::lock_guard<std::mutex> lk(mu);
            for (int c = ch < 0 ? 0 : ch; c < (ch < 0 ? 16 : ch + 1); c++) {
                if (cc == panel::VSENSE_CC) {   // (velocity sense depth: GS's 40 1x 1A, as a sequencer sends it)
                    const int blk = c == 9 ? 0 : c < 9 ? c + 1 : c;
                    std::vector<uint8_t> x{0x41, 0x10, 0x42, 0x12, 0x40, (uint8_t)(0x10 | blk), 0x1A, (uint8_t)v};
                    x.push_back((uint8_t)((128 - (0x40 + x[5] + 0x1A + v) % 128) % 128));
                    q.push_back(Midi{6, 0, 0, 0, x});
                } else
                    q.push_back(Midi{2, c, cc, v, {}});
            }
        };
        H.sysfx_send = [&](int hi, int lo, int v) {
            std::vector<uint8_t> x{0x41, 0x10, 0x42, 0x12, 0x40, (uint8_t)hi, (uint8_t)lo,
                                   (uint8_t)std::max(0, std::min(127, v))};
            x.push_back((uint8_t)((128 - (0x40 + hi + lo + x[7]) % 128) % 128));
            std::lock_guard<std::mutex> lk(mu);
            q.push_back(Midi{6, 0, 0, 0, x});
        };
        if (E.has_prog)
            H.pick = [&](int sp) { pick(sp); };
        H.tuner = tuner_now;
        H.set_tuner = [&](const std::string &nm) { set_tuner(nm); };
        H.eastern = east_now;
        H.set_eastern = [&](const std::string &sp) { set_eastern(sp); };
        H.east_part = [&](int prog, bool dr) { return east_part(prog, dr); };
        // THE PARTS (livetui's PARTS pane)
        H.parts = [&]() { return part_rows(); };
        // THE SYNTH (livetui's synth pane)
        H.synth_get = [&](int i, int lay, double *pn, char *own) { return synth_state((size_t)i, lay, pn, own); };
        H.synth_set = [&](int i, int lay, int k, double v) { synth_set((size_t)i, lay, k, v); };
        H.synth_forget = [&](int i, int lay, int k) { synth_forget((size_t)i, lay, k); };
        H.synth_send = [&](int i) { return synth_send((size_t)i); };
        H.part_touch = [&](int i, bool fx) { part_touch((size_t)i, fx ? 1 : 0); };
        H.drive_get = [&](int i, double *o) { return drive_state((size_t)i, o); };
        H.drive_set = [&](int i, double v) { part_drive((size_t)i, v); };
        // THE ON-SCREEN CONTROLS (livetui's): the host's list, sent past the routes
        H.controls = &screen_controls;
        H.control_send = [&](int key, int v, int ch) { control_send(key, v, ch); };
        H.switch_on = [&](int key, int ch) {
            int sw[5];
            nv_part_switches(part, ch < 0 ? 0 : ch, sw);
            return key == 64 ? sw[0] != 0 : key == 66 ? sw[1] != 0 : key == 67 ? sw[2] != 0
                 : key == 65 ? sw[3] != 0 : key == -3 ? sw[4] != 0 : false;
        };
        H.messenger_reads = [&]() { return msgr_reads; };
        H.messenger_read = [&](bool on) { messenger_reading(on); };
        H.display = [&]() {
            // gsdisplay.text_window and half_blocks
            std::vector<std::string> dl;
            char text[33];
            double age = 0.0;
            int page = 0;
            unsigned char rows[256];
            if (!nv_part_display(part, text, &age, &page, rows))
                return dl;
            const std::string t = text;
            if (!t.empty()) {
                if (t.size() <= 16) {
                    dl.push_back(t);
                } else {
                    const std::string loop = t + "    ", two = loop + loop;
                    const size_t k = (size_t)(age / 0.3) % loop.size();
                    dl.push_back(two.substr(k, 16));
                }
            }
            if (page)
                for (int r = 0; r < 16; r += 2) {
                    std::string ln;
                    for (int c = 0; c < 16; c++) {
                        const bool tp = rows[16 * r + c], bt = rows[16 * (r + 1) + c];
                        ln += tp && bt ? "█" : tp ? "▀" : bt ? "▄" : " ";
                    }
                    dl.push_back(ln);
                }
            return dl;
        };
        H.messenger_line = [&]() {
            const std::string w = msgr && msgr->fd.load() >= 0 ? msgr->where() : msgr_out;
            if (w.empty())
                return std::string(msgr_auto ? "-" : "");      // ("-": none yet, watched for)
            return "sets the Messenger on " + w + ", " + (msgr_pre107 ? "pre-1.0.7" : "1.0.7+")
                   + " chart  (T: send the panel  F: firmware)";
        };
        H.messenger_firmware = [&]() {
            msgr_pre107 = !msgr_pre107;
            const double v = msgr_pre107 ? 1.0 : 0.0;
            post([this, v](long long) { nv_part_set(part, 9, v); });
            return std::string(msgr_pre107 ? "pre-1.0.7" : "1.0.7+");
        };
        H.part_set = [&](int i, int ch, int lo, int hi, int tr, double lv, bool mu) { part_set((size_t)i, ch, lo, hi, tr, lv, mu); };
        H.part_layer = [&](int i) { return part_layer((size_t)i); };
        H.part_split = [&](int i, std::string &why) { return part_split((size_t)i, why); };
        H.part_delete = [&](int i, std::string &why) { return part_delete((size_t)i, why); };
        if (E.has_prog)
            H.pick_part = [&](int i, int sp) { pick_row((size_t)i, sp); };
        H.progress = [&](long &d, long &t, std::string &nm) { return progress(&d, &t, &nm); };
        // ...A PROGRAM CHANGE FROM THE KEYBOARD: its name and its stops, and
        // what the builder said
        int shown = shown_program, shown_v = shown_var, shown_room = room_idx;
        auto routes_now = [&]() {               // (the panel's, --pedal-key's own not among them)
            std::vector<std::array<int, 7>> rs;
            bool skipped = pks.empty();
            for (auto &a : H.routes) {
                if (!skipped && a == pedal_route) {
                    skipped = true;
                    continue;
                }
                rs.push_back(a);
            }
            return rs;
        };
        // PRESETS AND SCENES (live's presets.json, scenes.json, beside the session)
        auto names_in = [](const std::string &path) {
            std::vector<std::string> ns;
            sess::J d;
            if (sess::load(path, d))
                for (const auto &kv : d.o)
                    ns.push_back(kv.first);
            return ns;
        };
        auto put = [](const std::string &path, const std::string &name, const sess::J &v) {
            sess::J d;
            if (!sess::load(path, d))
                d = sess::obj();
            d.o[name] = v;
            return sess::save(path, d);
        };
        auto base = [](const std::string &p) { return p.substr(p.rfind('/') + 1); };
        H.save_preset = [&, put, base](const std::string &name) {
            if (!put(presets_path(), name, session_state(routes_now())))
                return std::string("could not write ") + presets_path();
            return "saved '" + name + "' to " + base(presets_path());
        };
        H.preset_names = [&, names_in]() { return names_in(presets_path()); };
        H.load_preset = [&](const std::string &name) {
            sess::J d;
            const sess::J *p = sess::load(presets_path(), d) ? d.get(name) : nullptr;
            if (!p || !p->is(sess::J::OBJ))
                return "no preset '" + name + "'";
            routes_replaced = H.routes;
            apply_setup(*p, false);
            H.routes = routes_replaced;
            for (int i = 0; i < panel::NGLOBALS; i++)
                H.g[i] = gval[i];
            return "loading '" + name + "'";
        };
        H.save_scene = [&, put, base](const std::string &name) {
            std::vector<std::string> ev = scene_now();
            sess::J a = sess::arr();
            for (const auto &e : ev)
                a.a.push_back(sess::str(e));
            if (!put(scenes_path(), name, a))
                return std::string("could not write ") + scenes_path();
            return "scene '" + name + "': " + std::to_string(ev.size()) + " events -> " + base(scenes_path());
        };
        H.scene_names = [&, names_in]() { return names_in(scenes_path()); };
        H.recall_scene = [&](const std::string &name) {
            sess::J d;
            const sess::J *p = sess::load(scenes_path(), d) ? d.get(name) : nullptr;
            if (!p || !p->is(sess::J::ARR))
                return "no scene '" + name + "'";
            std::vector<std::string> ev;
            for (const auto &e : p->a)
                if (e.is(sess::J::STR))
                    ev.push_back(e.s);
            return "scene '" + name + "': " + std::to_string(scene_recall(ev)) + " events";
        };
        auto saved_at = std::chrono::steady_clock::now();
        H.refresh = [&]() {
            {                                           // (a tuner switched to: its name; the Eastern tuning's)
                std::lock_guard<std::mutex> lk(bmu);
                H.tuner = tuner_now;
                H.eastern = east_now;
            }
            // THE SESSION, saved as it changes: at most every 2 s, on this
            // thread (livetui's _loop)
            if (std::chrono::steady_clock::now() - saved_at >= std::chrono::seconds(2)) {
                saved_at = std::chrono::steady_clock::now();
                session_save(routes_now());
            }
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
        session_save(routes_now());             // (and once more on the way out)
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
    if (recorder.joinable())
        recorder.join();
    if (m2play.joinable())
        m2play.join();
    if (umpthr.joinable())
        umpthr.join();
    A.close(A.pcm);
    fprintf(stderr, "nvlive: stopped\n");
    return 0;
}

// ---- THE SESSION (session.h): live's session.json, shared with live.py ----

// a live.Route as Route.to_dict writes it, from nv_rt_add's seven; a null
// for one whose destination live has no name for (-99)
static sess::J route_dict(const std::array<int, 7> &a)
{
    static const char *HALF[3] = {"up", "down", "both"};
    sess::J src = sess::arr();
    switch (a[0]) {
    case 0: src.a = {sess::str("cc"), sess::integer(a[1])}; break;
    case 1: src.a = {sess::str("bend"), sess::str(HALF[std::max(0, std::min(2, a[1]))])}; break;
    case 2: src.a = {sess::str("pressure")}; break;
    default: src.a = {sess::str("note"), sess::integer(a[1])}; break;
    }
    if (a[2] == -99)
        return sess::null();
    sess::J d = sess::obj();
    d.o["src"] = src;
    d.o["dst"] = a[2] == -1 ? sess::str("bend") : a[2] == -2 ? sess::str("pressure") : a[2] == -3 ? sess::str("mono")
                                                                                    : sess::integer(a[2]);
    d.o["keep"] = sess::boolean(a[3] != 0);
    d.o["channel"] = a[4] < 0 ? sess::null() : sess::integer(a[4]);
    d.o["latch"] = sess::boolean(a[5] != 0);
    d.o["press"] = sess::boolean(a[6] != 0);
    return d;
}

// ...and back (native.route_args): false for one nvlive cannot take
static bool route_args(const sess::J &d, std::array<int, 7> &a)
{
    const sess::J *src = d.get("src"), *dst = d.get("dst");
    if (!src || !src->is(sess::J::ARR) || src->a.empty() || !src->a[0].is(sess::J::STR) || !dst)
        return false;
    const std::string k = src->a[0].s;
    const sess::J *arg = src->a.size() > 1 ? &src->a[1] : nullptr;
    if (k == "cc" && arg)
        a = {0, (int)arg->i(), 0, 0, -1, 0, 1};
    else if (k == "bend")
        a = {1, !arg || arg->s == "up" ? 0 : arg->s == "down" ? 1 : 2, 0, 0, -1, 0, 1};
    else if (k == "pressure")
        a = {2, 0, 0, 0, -1, 0, 1};
    else if (k == "note" && arg)
        a = {3, (int)arg->i(), 0, 0, -1, 0, 1};
    else
        return false;
    a[2] = dst->is(sess::J::STR) ? (dst->s == "bend" ? -1 : dst->s == "pressure" ? -2 : dst->s == "mono" ? -3 : -99)
                                 : (int)dst->i();
    const sess::J *x;
    a[3] = (x = d.get("keep")) && x->d() != 0.0;
    a[4] = (x = d.get("channel")) && x->is(sess::J::NUM) ? (int)x->i() : -1;
    a[5] = (x = d.get("latch")) && x->d() != 0.0;
    a[6] = (x = d.get("press")) ? x->d() != 0.0 : 1;
    return true;
}

// what the session holds that the part takes once playing (live.apply_preset):
// the globals, the room, the insertion effect (efx_recall's messages), the
// organ's drawn stops, and each channel's mix (the scene: recall_scene)
void nv_host::session_apply()
{
    if (session.is(sess::J::OBJ))
        apply_setup(session, true);
}

// ---- SCENES AND PRESETS (live's) ----

static std::string beside(const std::string &path, const char *name)
{
    size_t k = path.rfind('/');
    return (k == std::string::npos ? std::string(".") : path.substr(0, k)) + "/" + name;
}
std::string nv_host::presets_path() const { return beside(session_path, "presets.json"); }
std::string nv_host::scenes_path() const { return beside(session_path, "scenes.json"); }

static std::string cc_text(int ch, int c, int v)
{
    return "control_change channel=" + std::to_string(ch) + " control=" + std::to_string(c) + " value="
           + std::to_string(std::max(0, std::min(127, v))) + " time=0";
}

// live._rpn_events: an RPN set, then the null RPN
static void rpn_text(std::vector<std::string> &ev, int ch, int lsb, int msb_val, int lsb_val)
{
    ev.push_back(cc_text(ch, 101, 0));
    ev.push_back(cc_text(ch, 100, lsb));
    ev.push_back(cc_text(ch, 6, msb_val));
    if (lsb_val >= 0)
        ev.push_back(cc_text(ch, 38, lsb_val));
    ev.push_back(cc_text(ch, 101, 127));
    ev.push_back(cc_text(ch, 100, 127));
}

// THE SCENE NOW (live.scene_from), in mido's text form: the captured
// controls as they reached the part, then each channel's sound controllers,
// its tuning RPNs and mono, read from the engine between two blocks -- the
// last one taken when the audio is not running. An organ's mod wheel (the
// crescendo: its registration is the part's drawn stops) left out
std::vector<std::string> nv_host::scene_now()
{
    struct Got {
        std::vector<double> st = std::vector<double>(16 * 13, 0.0);
        std::map<std::pair<int, int>, int> latch;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got](long long) {
        nv_part_chanstate(part, got->st.data());
        got->latch = chanlatch;
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return scene_cached;
    const int sp = shown_program;
    const bool cres = sp < 128 && !E.stops[sp].names.empty();
    std::vector<std::string> ev;
    for (const auto &kv : got->latch) {
        const int ch = kv.first.first, c = kv.first.second;
        if (c == 1 && cres && (pats[0].channel < 0 || pats[0].channel == ch))
            continue;
        ev.push_back(cc_text(ch, c, kv.second));
    }
    static const int SND_BY_NAME[8] = {73, 74, 75, 72, 71, 78, 77, 76};    // (attack .. vib_rate: sorted by name)
    for (int ch = 0; ch < 16; ch++) {
        const double *o = got->st.data() + 13 * ch;
        for (int c : SND_BY_NAME)
            if (o[c - 71] != 0.0)
                ev.push_back(cc_text(ch, c, (int)std::nearbyint(o[c - 71] * 64.0 + 64.0)));
        if (o[8] >= 0.0) {
            int msb = (int)o[8], lsb = (int)std::nearbyint((o[8] - msb) * 100.0);
            rpn_text(ev, ch, 0, msb, lsb ? lsb : -1);
        }
        if (o[9] != 0.0) {
            int code = std::max(0, std::min(16383, (int)std::nearbyint(o[9] / 100.0 * 8192.0) + 8192));
            rpn_text(ev, ch, 1, code >> 7, code & 127);
        }
        if (o[10] != 0.0)
            rpn_text(ev, ch, 2, std::max(0, std::min(127, (int)std::nearbyint(o[10]) + 64)), -1);
        if (o[11] >= 0.0) {
            int msb = (int)std::floor(o[11] / 100.0), lsb = (int)std::nearbyint((o[11] - msb * 100.0) / (100.0 / 128.0));
            rpn_text(ev, ch, 5, msb, lsb ? lsb : -1);
        }
        if (o[12] != 0.0)
            ev.push_back(cc_text(ch, 126, 1));
    }
    scene_cached = ev;
    return ev;
}

// A SCENE PUT BACK (live.recall_scene): its events past the routes (they are
// already what the part received), mono changed only where it differs (both
// mode messages carry an All Sounds Off), a channel the scene leaves
// polyphonic put back to poly; an organ's mod wheel never replayed
int nv_host::scene_recall(const std::vector<std::string> &events)
{
    std::vector<std::array<int, 3>> cc;
    for (const auto &e : events) {
        int ch, c, v;
        if (sscanf(e.c_str(), "control_change channel=%d control=%d value=%d", &ch, &c, &v) == 3)
            cc.push_back({ch & 15, c, v});
    }
    const int sp = shown_program;
    const bool cres = sp < 128 && !E.stops[sp].names.empty();
    const int pch = pats[0].channel;
    post([this, cc, cres, pch](long long) {
        double st[16 * 13];
        nv_part_chanstate(part, st);
        bool want_mono[16] = {};
        for (const auto &m : cc)
            if (m[1] == 126)
                want_mono[m[0]] = true;
        for (const auto &m : cc) {
            if (m[1] == 1 && cres && (pch < 0 || pch == m[0]))
                continue;
            if (m[1] == 126 || m[1] == 127) {
                if ((m[1] == 126) != (st[13 * m[0] + 12] != 0.0))
                    engine_event(2, m[0], m[1], m[2]);
                continue;
            }
            engine_event(2, m[0], m[1], m[2]);
        }
        for (int ch = 0; ch < 16; ch++)
            if (st[13 * ch + 12] != 0.0 && !want_mono[ch])
                engine_event(2, ch, 127, 0);
    });
    int n = 0;
    for (const auto &m : cc)
        n += !(m[1] == 1 && cres && (pch < 0 || pch == m[0]));
    return n;
}

// A SETUP TAKEN (live.apply_preset): a session's at the start (the part's
// program already taken, the routes already the router's), or a preset's
// while playing -- then the parts set again (every one but the first and the
// drums nvlive keeps beside it taken away, the first's program asked for,
// the rest added), the routes replaced, the tuner switched; the stops for
// the first part's organ once it is in
void nv_host::apply_setup(const sess::J &setup, bool at_start)
{
    const sess::J *x;
    const sess::J &session = setup;         // (the code below reads it by the session's name)
    if (!at_start) {
        // THE PARTS AWAY: all but the first and the drums kept beside it
        std::vector<size_t> away;
        {
            std::lock_guard<std::mutex> lk(parts_mu);
            for (size_t i = 0; i < pats.size(); i++)
                if (!pats[i].gone && pats[i].pi != 0 && pats[i].pid != 2 && pats[i].pid != 3)
                    away.push_back(i);
        }
        std::string why;
        for (size_t i : away)
            part_delete(i, why);
        // ...THE ROUTES REPLACED (--pedal-key's own kept)
        if ((x = setup.get("routes")) && x->is(sess::J::ARR)) {
            std::vector<std::array<int, 7>> rs;
            for (const sess::J &r : x->a) {
                std::array<int, 7> a;
                if (route_args(r, a))
                    rs.push_back(a);
            }
            const size_t had = E.routes.size() + (pks.empty() ? 0 : 1);
            std::vector<std::array<int, 7>> all = rs;
            if (!pks.empty())
                all.push_back(pedal_route);
            post([this, had, all](long long) {
                for (size_t q = had; q-- > 0;)
                    nv_rt_del(router, (int)q);
                for (const auto &a : all)
                    nv_rt_add(router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
            });
            E.routes = rs;
            routes_replaced = all;
        }
        // ...THE EASTERN TUNING (live.apply_preset: before the parts it tunes)
        const sess::J *ea = setup.get("eastern");
        if (ea && (ea->is(sess::J::STR) || ea->is(sess::J::NUL))) {
            std::string want = ea->is(sess::J::STR) ? ea->s : std::string(), cur;
            {
                std::lock_guard<std::mutex> lk(bmu);
                cur = east_req_set ? east_asked : east_now;
            }
            if (want != cur)
                set_eastern(want);
        }
        // ...THE TUNER (the first part's, live's per part; nvlive's one)
        const sess::J *ps = setup.get("parts");
        const sess::J *tn = ps && ps->is(sess::J::ARR) && !ps->a.empty() ? ps->a[0].get("tuner") : nullptr;
        if (tn && tn->is(sess::J::STR) && !tn->s.empty()) {
            std::string cur;
            {
                std::lock_guard<std::mutex> lk(bmu);
                cur = tuner_now;
            }
            if (tn->s != cur)
                set_tuner(tn->s);
        }
    }
    static const char *KEYS[6] = {"master_db", "headroom_db", "thresh", "bend_range", "mod_cents", "press_db"};
    for (int i = 0; i < 6; i++)
        if ((x = session.get(KEYS[i])) && x->is(sess::J::NUM)) {
            double v = std::max(panel::GLOBAL_RANGE[i][0], std::min(panel::GLOBAL_RANGE[i][1], x->d()));
            if (v != gval[i])
                set_global(i, v);
        }
    if ((x = session.get("messenger_firmware")) && x->is(sess::J::STR)        // THE MESSENGER's CHART (live's)
        && (x->s == "pre-1.0.7") != msgr_pre107) {
        msgr_pre107 = x->s == "pre-1.0.7";
        const double v = msgr_pre107 ? 1.0 : 0.0;
        post([this, v](long long) { nv_part_set(part, 9, v); });
    }
    if ((x = session.get("controls")) && x->is(sess::J::ARR)) {        // THE ON-SCREEN CONTROLS (live's)
        screen_controls.clear();
        for (const sess::J &c : x->a) {
            const sess::J *k = c.get("key"), *ch = c.get("channel"), *v = c.get("value"), *hk = c.get("hotkey");
            if (!k)
                continue;
            int key;
            if (k->is(sess::J::NUM))
                key = (int)k->i();
            else if (k->is(sess::J::STR) && (k->s == "mono" || k->s == "bend" || k->s == "pressure"))
                key = k->s == "mono" ? -3 : k->s == "bend" ? -1 : -2;
            else
                continue;
            if (!panel::control_label(key))
                continue;                       // (not the catalogue's)
            panel::ScreenControl sc;
            sc.key = key;
            sc.channel = ch && ch->is(sess::J::NUM) ? (int)ch->i() & 15 : -1;
            sc.value = v && v->is(sess::J::NUM) ? (int)v->i() : panel::control_default(key);
            sc.hotkey = hk && hk->is(sess::J::STR) && hk->s.size() == 1 ? (unsigned char)hk->s[0] : 0;
            screen_controls.push_back(sc);
        }
    }
    if ((x = session.get("std_map")) && x->is(sess::J::NUM))           // THE STANDARD (live.std_map)
        set_global(13, x->d());
    if ((x = session.get("mod_rate")) && x->is(sess::J::NUM)) {       // (the host's ninth: live.mod_rate)
        double v = std::max(panel::GLOBAL_RANGE[9][0], std::min(panel::GLOBAL_RANGE[9][1], x->d()));
        if (v != gval[9])
            set_global(9, v);
    }
    // THE MIDI INPUTS (live.saved_inputs): the session's, those plugged in
    // now -- by device name, before any colon (live's "USB Midi:USB Midi MIDI
    // 1" is our "USB Midi") -- unless --port or --midi named one
    if (at_start && !cli_port && (x = session.get("midi_inputs")) && x->is(sess::J::ARR) && !x->a.empty()) {
        auto devname = [](std::string n) {
            n = n.substr(0, n.find(':'));
            while (!n.empty() && n.back() == ' ')
                n.pop_back();
            for (char &ch : n)
                ch = (char)tolower((unsigned char)ch);
            return n;
        };
        std::vector<std::pair<std::string, std::string>> w;
        for (const auto &d : midi_devices())
            for (const auto &j : x->a)
                if (j.is(sess::J::STR) && devname(j.s) == devname(d.second)) {
                    w.push_back(d);
                    break;
                }
        if (!w.empty())
            ins.set(w);
    }
    if ((x = session.get("room")) && x->is(sess::J::STR))
        for (size_t q = 0; q < E.rooms.size(); q++)
            if (E.rooms[q].name == x->s && (int)q != room_idx)
                set_global(8, (double)q);           // (the builder's: every patch built again in it)
    if ((x = session.get("efx")) && x->is(sess::J::OBJ)) {
        auto send = [&](char kind, int a, int b) {
            std::vector<uint8_t> m = panel::efx_message(kind, a, b);
            post([this, m](long long) { nv_part_sysex(part, m.data(), (int)m.size()); });
        };
        const sess::J *t = x->get("type");
        if (t && t->is(sess::J::ARR) && t->a.size() == 2)
            send('t', (int)t->a[0].i(), (int)t->a[1].i());
        for (const char *k : {"p", "send", "ctl"})
            if (const sess::J *l = x->get(k))
                for (const sess::J &kv : l->a)
                    if (kv.is(sess::J::ARR) && kv.a.size() == 2)
                        send(k[0] == 'p' ? 'p' : 's', (int)kv.a[0].i(), (int)kv.a[1].i());
        std::vector<int> want;
        if (const sess::J *l = x->get("parts"))
            for (const sess::J &c : l->a)
                want.push_back((int)c.i());
        for (int ch = 0; ch < 16; ch++)
            send('c', ch, std::find(want.begin(), want.end(), ch) != want.end());
    }
    // THE PARTS (live.Part.to_dict's): the first's place, level and mute on
    // the part; each after it added -- a drum set on channel 10 the drums
    // nvlive keeps beside the part (its own, not live's: never written back)
    const sess::J *parts = session.get("parts");
    if (parts && parts->is(sess::J::ARR))
        for (size_t k = 0; k < parts->a.size(); k++) {
            const sess::J &pd = parts->a[k];
            if (!pd.is(sess::J::OBJ))
                continue;
            auto num = [&](const char *key, double dflt) {
                const sess::J *v = pd.get(key);
                return v && v->is(sess::J::NUM) ? v->d() : dflt;
            };
            const sess::J *chv = pd.get("channel"), *dv = pd.get("drums"), *mv = pd.get("muted");
            PartSpec sp;
            sp.program = (int)num("program", 0) & 127;
            sp.var = (int)num("bank", 0);
            sp.drums = dv && dv->d() != 0.0;
            sp.channel = chv && chv->is(sess::J::NUM) ? (int)chv->i() & 15 : -1;
            sp.lo = std::max(0, std::min(127, (int)num("lo", 0)));
            sp.hi = std::max(sp.lo, std::min(127, (int)num("hi", 127)));
            sp.tr = std::max(-48, std::min(48, (int)num("transpose", 0)));
            sp.level = std::max(panel::LEVEL_DB_MIN, std::min(panel::LEVEL_DB_MAX, num("level_db", 0.0)));
            sp.muted = mv && mv->d() != 0.0;
            {                                   // its fixed touch (live's part.fixed_touch; absent, the patch's way)
                const sess::J *ft = pd.get("fixed_touch");
                sp.fixed = ft && (ft->is(sess::J::BOOL) || ft->is(sess::J::NUM)) ? (ft->d() != 0.0 ? 1 : 0) : -1;
                const sess::J *dr = pd.get("drive");    // (an organ's drive knob: live's Part.drive; absent, the voice's)
                sp.drive = dr && dr->is(sess::J::NUM) ? std::max(0.0, dr->d()) : -1.0;
                const sess::J *cm = pd.get("cc_map");   // (a Messenger read on it: nvlive reads one on every part)
                if (cm && cm->is(sess::J::STR) && cm->s == "messenger" && !msgr_reads)
                    messenger_reading(true);
            }
            // ITS KNOBS (live.Part's synth, synth_b): by moog.PANEL's names, in
            // the measured Messenger's units (synth_units 6) -- older ones live
            // converts once on load, which nvlive leaves to it
            {
                const sess::J *su = pd.get("synth_units");
                const int units = su && su->is(sess::J::NUM) ? (int)su->i() : 1;
                bool any = false;
                for (int lay = 0; lay < 2; lay++) {
                    const sess::J *sy = pd.get(lay ? "synth_b" : "synth");
                    if (!sy || !sy->is(sess::J::OBJ))
                        continue;
                    for (const auto &kv : sy->o) {
                        const int mk = panel::mk_index(kv.first.c_str());
                        if (mk >= 0 && (kv.second.is(sess::J::NUM) || kv.second.is(sess::J::BOOL))) {
                            sp.syn[lay][mk] = kv.second.d();
                            any = true;
                        }
                    }
                }
                if (any && units < 6) {
                    fprintf(stderr, "nvlive: part %zu's knobs are in older units (synth_units %d): left as the patch's "
                                    "-- open the session in live.py once to convert them\n", k + 1, units);
                    sp.syn[0].clear();
                    sp.syn[1].clear();
                }
            }
            if (k == 0) {                       // (its knobs, behind its program: posted after its swap)
                for (int lay = 0; lay < 2; lay++)
                    for (const auto &kv : sp.syn[lay]) {
                        const int mk = kv.first, l = lay;
                        const double v = kv.second;
                        post([this, l, mk, v](long long) { nv_part_synth_set_later(part, pats[0].pi, l, mk, v); });
                    }
            }
            if (k == 0) {                       // (at the start its program is the part's already)
                part_set(0, sp.channel, sp.lo, sp.hi, sp.tr, sp.level, sp.muted);
                part_touch(0, sp.fixed);
                if (at_start)                   // (else after the pick's swap, below: a new program clears it)
                    part_drive(0, sp.drive);
                if (!at_start) {
                    int code = (sp.drums ? 128 : 0) + sp.program;
                    for (size_t j = 0; j < E.vpv.size() && sp.var && !sp.drums; j++)
                        if (E.vpv[j][0] == sp.program && E.vpv[j][1] == sp.var)
                            code = 256 + (int)j;
                    pick_row(0, code);
                    if (sp.drive >= 0.0) {      // (its drive knob, behind the swap that brings its program in)
                        const double dv = sp.drive;
                        {
                            std::lock_guard<std::mutex> lk(parts_mu);
                            pats[0].drive = dv;
                        }
                        post([this, dv](long long) { nv_part_drive_later(part, pats[0].pi, dv); });
                    }
                }
                continue;
            }
            size_t beside = pats.size();
            for (size_t i = 0; i < pats.size(); i++)
                if (pats[i].pid == 2 && sp.drums && sp.channel == 9)
                    beside = i;
            if (beside < pats.size()) {
                part_set(beside, 9, sp.lo, sp.hi, sp.tr, sp.level, sp.muted);
                pick_row(beside, 128 + sp.program);
                continue;
            }
            sp.excl = sp.channel < 0 ? pats[0].excl : 0u;
            if (sp.drums)
                sp.var = 0;
            part_add(sp);
        }
    // THE ORGAN's STOPS: drawn as the part's were (parts[0].drawn, by name) --
    // now if the organ is in, else once it is swapped in (pending_drawn)
    if (parts && parts->is(sess::J::ARR) && !parts->a.empty()) {
        const sess::J *dn = parts->a[0].get("drawn"), *pg = parts->a[0].get("program"), *dv = parts->a[0].get("drums");
        const int want_p = pg && pg->is(sess::J::NUM) ? (int)pg->i() & 127 : -1;
        if (dn && dn->is(sess::J::ARR) && want_p >= 0 && !(dv && dv->d() != 0.0) && !E.stops[want_p].names.empty()) {
            const auto &names = E.stops[want_p].names;
            std::vector<char> want(names.size(), 0);
            for (size_t ri = 0; ri < names.size(); ri++)
                for (const sess::J &n : dn->a)
                    want[ri] = want[ri] || (n.is(sess::J::STR) && n.s == names[ri]);
            if (want_p == shown_program)
                post([this, want](long long) { nv_part_set_drawn(part, want.data(), (int)want.size()); });
            if (!at_start || want_p != shown_program) {
                std::vector<std::string> w;
                for (size_t ri = 0; ri < names.size(); ri++)
                    if (want[ri])
                        w.push_back(names[ri]);
                post([this, w, want_p](long long) {     // (the swap reads it, on this thread)
                    pending_drawn = w;
                    pending_drawn_prog = want_p;
                });
            }
        }
    }
    // EACH CHANNEL's MIX (live.recall_scene): past the routes
    if ((x = session.get("chanstate")) && x->is(sess::J::ARR)) {
        std::vector<std::string> ev;
        for (const sess::J &e : x->a)
            if (e.is(sess::J::STR))
                ev.push_back(e.s);
        scene_recall(ev);
    }
}

// the session as it stands: what nvlive owns set, every other key kept
sess::J nv_host::session_state(const std::vector<std::array<int, 7>> &routes)
{
    sess::J j = session.is(sess::J::OBJ) ? session : sess::obj();
    j.o["master_db"] = sess::real(std::round(gval[0] * 100.0) / 100.0);
    static const char *KEYS[6] = {"master_db", "headroom_db", "thresh", "bend_range", "mod_cents", "press_db"};
    for (int i = 1; i < 6; i++)
        j.o[KEYS[i]] = sess::real(gval[i]);
    j.o["mod_rate"] = sess::real(gval[9]);
    j.o["std_map"] = sess::integer(default_map);
    {                                           // the rig's Eastern tuning (live.preset_from's: "" off)
        std::lock_guard<std::mutex> lk(bmu);
        j.o["eastern"] = sess::str(east_req_set ? east_asked : east_now);
    }
    {                                           // the on-screen controls (live's screen_controls, as dicts)
        sess::J cs = sess::arr();
        for (const auto &c : screen_controls) {
            sess::J d = sess::obj();
            d.o["key"] = c.key >= 0 ? sess::integer(c.key) : sess::str(c.key == -3 ? "mono" : c.key == -1 ? "bend" : "pressure");
            d.o["channel"] = c.channel < 0 ? sess::null() : sess::integer(c.channel);
            d.o["value"] = sess::integer(c.value);
            d.o["hotkey"] = c.hotkey ? sess::str(std::string(1, (char)c.hotkey)) : sess::null();
            cs.a.push_back(d);
        }
        j.o["controls"] = cs;
    }
    const int rm = room_asked >= 0 ? (int)room_asked : (int)room_idx;    // (one asked for is the room, building or not)
    if (rm >= 0 && rm < (int)E.rooms.size())
        j.o["room"] = sess::str(E.rooms[rm].name);
    j.o["messenger_firmware"] = sess::str(msgr_pre107 ? "pre-1.0.7" : "1.0.7+");
    {                                           // the Messenger set (live's messenger_port): "none" off
        const std::string w = msgr && msgr->fd.load() >= 0 ? msgr->where() : "";
        j.o["messenger_port"] = !w.empty() ? sess::str(w) : msgr_auto || !msgr_out.empty() ? sess::null() : sess::str("none");
    }
    {                                           // the MIDI inputs open (live's midi_inputs), by name
        sess::J mi = sess::arr();
        std::lock_guard<std::mutex> lk(ins.mu);
        for (auto &d : ins.want)
            mi.a.push_back(sess::str(d.second));
        j.o["midi_inputs"] = mi;
    }
    sess::J ra = sess::arr();
    for (const auto &a : routes) {
        sess::J d = route_dict(a);
        if (d.is(sess::J::OBJ))
            ra.a.push_back(d);
    }
    j.o["routes"] = ra;
    // each channel's mix (live.scene_from)
    {
        sess::J cs = sess::arr();
        for (const auto &e : scene_now())
            cs.a.push_back(sess::str(e));
        j.o["chanstate"] = cs;
    }
    // the insertion effect (live.efx_from), as the audio thread last showed it
    std::vector<int> st;
    {
        std::lock_guard<std::mutex> lk(pmu);
        st = snap.efx;
    }
    panel::EfxView v(st);
    if (v.has) {
        sess::J e = sess::obj(), ps = sess::arr(), sd = sess::arr(), ct = sess::arr(), pa = sess::arr();
        e.o["type"] = sess::arr();
        e.o["type"].a = {sess::integer(v.msb), sess::integer(v.lsb)};
        auto pair = [](int k, int x) {
            sess::J p = sess::arr();
            p.a = {sess::integer(k), sess::integer(x)};
            return p;
        };
        for (int q = 1; q <= 20; q++)
            if (v.p[q] >= 0)
                ps.a.push_back(pair(q, v.p[q]));
        for (int q = 0; q < 3; q++)
            sd.a.push_back(pair(panel::EFX_SEND[q], v.snd[q]));
        for (int q = 0; q < 4; q++)
            ct.a.push_back(pair(panel::EFX_CTL_SRC1 + q, v.ctl[q]));
        std::vector<int> on = v.parts;
        std::sort(on.begin(), on.end());
        for (int c : on)
            pa.a.push_back(sess::integer(c));
        e.o["p"] = ps;
        e.o["send"] = sd;
        e.o["ctl"] = ct;
        e.o["parts"] = pa;
        j.o["efx"] = e;
    }
    // THE PARTS (live.Part.to_dict): each one's program, set or variation,
    // its place, level and mute, the first's stops; each one's other keys as
    // they were -- the drums nvlive keeps beside the part not among them
    // (its own: live's rig has none)
    sess::J &parts = j.o["parts"];
    if (!parts.is(sess::J::ARR))
        parts = sess::arr();
    std::vector<PartAt> rows;
    std::vector<size_t> at;                     // (each one's index: its knobs read by it)
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        for (size_t i = 0; i < pats.size(); i++)
            if (!pats[i].gone && pats[i].pid != 2 && pats[i].pid != 3) {
                rows.push_back(pats[i]);
                at.push_back(i);
            }
    }
    parts.a.resize(rows.size());
    for (size_t k = 0; k < rows.size(); k++) {
        sess::J &pd = parts.a[k];
        if (!pd.is(sess::J::OBJ)) {
            pd = sess::obj();
            pd.o["tuner"] = sess::str("hybrid");
            pd.o["drawn"] = sess::arr();
        }
        const PartAt &pa = rows[k];
        const int vk = pa.drums ? 0 : (k == 0 ? (shown_program >= 128 ? 0 : shown_var.load()) : pa.var);
        pd.o["program"] = sess::integer((k == 0 ? shown_program.load() : pa.program) & 127);
        pd.o["drums"] = sess::boolean(k == 0 ? shown_program >= 128 : pa.drums);
        if (vk)
            pd.o["bank"] = sess::integer(vk);
        else
            pd.o.erase("bank");
        pd.o["channel"] = pa.channel < 0 ? sess::null() : sess::integer(pa.channel);
        pd.o["lo"] = sess::integer(pa.lo);
        pd.o["hi"] = sess::integer(pa.hi);
        pd.o["transpose"] = sess::integer(pa.tr);
        pd.o["level_db"] = sess::real(pa.level);
        pd.o["muted"] = sess::boolean(pa.muted);
        if (pa.fixed >= 0)                      // (live writes it only when set)
            pd.o["fixed_touch"] = sess::boolean(pa.fixed != 0);
        else
            pd.o.erase("fixed_touch");
        if (pa.drive >= 0.0)                    // (an organ's drive knob, live's likewise)
            pd.o["drive"] = sess::real(pa.drive);
        else
            pd.o.erase("drive");
        if (msgr_reads && k == 0)               // (a Messenger read: the first part's cc_map, live's per part)
            pd.o["cc_map"] = sess::str("messenger");
        else if (!msgr_reads)
            pd.o.erase("cc_map");
        // ITS OWN KNOBS (live's synth, synth_b, synth_units 6), by moog.PANEL's
        // names: a switch as live keeps it (on/off a bool; an octave, a mode,
        // a shape an int), a knob a float -- a value already there kept as written
        bool anyk = false;
        for (int lay = 0; lay < 2; lay++) {
            double pn[42];
            char own[42];
            const char *key = lay ? "synth_b" : "synth";
            const int n = pa.drums ? 0 : synth_state(at[k], lay, pn, own);
            if (n < 0)                          // (never read, and the audio does not answer: as they were)
                continue;
            if (n <= lay) {                     // (not a Moog, or no layer B)
                pd.o.erase(key);
                continue;
            }
            sess::J sy = sess::obj();
            const sess::J *had = pd.get(key);
            for (int q = 0; q < 42; q++) {
                if (!own[q])
                    continue;
                const char *nm = panel::MK_NAMES[q];
                const sess::J *old = had ? had->get(nm) : nullptr;
                if (old && (old->is(sess::J::NUM) || old->is(sess::J::BOOL)) && old->d() == pn[q]) {
                    sy.o[nm] = *old;
                    continue;
                }
                std::string kind;
                for (int i = 0; i < panel::NSYNTH; i++)
                    if (!strcmp(panel::SYNTH_KNOBS[i][1], nm))
                        kind = panel::SYNTH_KNOBS[i][3];
                if (kind == "onoff")
                    sy.o[nm] = sess::boolean(pn[q] != 0.0);
                else if (kind == "foot" || kind == "mode" || kind == "lfoshape" || kind == "lfodest" || kind == "moddest"
                         || kind == "mfrange")
                    sy.o[nm] = sess::integer((long)pn[q]);
                else
                    sy.o[nm] = sess::real(pn[q]);
            }
            if (sy.o.empty()) {
                pd.o.erase(key);
            } else {
                pd.o[key] = sy;
                anyk = true;
            }
        }
        if (anyk)
            pd.o["synth_units"] = sess::integer(6);
        else if (!pd.get("synth") && !pd.get("synth_b"))
            pd.o.erase("synth_units");
    }
    if (parts.a.empty())
        return j;
    sess::J &p0 = parts.a[0];
    const int sp = shown_program, sv = sp >= 128 ? 0 : shown_var.load();
    p0.o["program"] = sess::integer(sp & 127);
    {                                           // (the tuner it plays: the session's, --tuner's, the panel's)
        std::lock_guard<std::mutex> lk(bmu);
        p0.o["tuner"] = sess::str(!tuner_asked.empty() ? tuner_asked : tuner_now);
    }
    p0.o["drums"] = sess::boolean(sp >= 128);
    if (sv)
        p0.o["bank"] = sess::integer(sv);
    else
        p0.o.erase("bank");
    sess::J dn = sess::arr();
    if (sp < 128 && !E.stops[sp].names.empty()) {
        const auto &names = E.stops[sp].names;
        std::vector<char> d(names.size(), 0);
        nv_part_drawn(part, d.data(), (int)names.size());
        std::vector<std::string> on;
        for (size_t ri = 0; ri < names.size(); ri++)
            if (d[ri])
                on.push_back(names[ri]);
        std::sort(on.begin(), on.end());
        for (auto &n : on)
            dn.a.push_back(sess::str(n));
    }
    p0.o["drawn"] = dn;
    return j;
}

// written when it changed (live.save_session: atomically; never raises). The
// first write over a session nvlive did not make keeps it beside, once.
bool nv_host::session_save(const std::vector<std::array<int, 7>> &routes)
{
    if (!session_on)
        return false;
    sess::J j = session_state(routes);
    std::string text = sess::dump(j);
    if (text == session_written)
        return true;
    if (session_written.empty() && access(session_path.c_str(), F_OK) == 0) {
        const std::string bak = session_path + ".before-nvlive";
        if (access(bak.c_str(), F_OK) != 0) {
            sess::J old;
            if (sess::load(session_path, old))
                sess::save(bak, old);
        }
    }
    if (!sess::save(session_path, j))
        return false;
    session_written = text;
    session = j;
    return true;
}

// THE SESSION before the part is built: its program (unless --program,
// --drums or --bank says otherwise) and its routes. --session=PATH, else
// session.json beside nvlive (live's: beside live.py); --fresh: not read
// (but written, as live's); --test: neither.
int main(int argc, char **argv)
{
    nv_host *h = new nv_host();                 // (never freed: its threads run to the end)
    std::vector<char *> args(argv, argv + argc);
    std::vector<std::string> extra;
    bool test = false, fresh = false, given = false, tuned = false;
    std::string sp;
    for (int i = 1; i < argc; i++) {
        test = test || !strcmp(argv[i], "--test");
        fresh = fresh || !strcmp(argv[i], "--fresh");
        given = given || !strncmp(argv[i], "--program=", 10) || !strcmp(argv[i], "--drums") || !strncmp(argv[i], "--bank=", 7);
        tuned = tuned || !strncmp(argv[i], "--tuner=", 8);
        if (!strncmp(argv[i], "--session=", 10))
            sp = argv[i] + 10;
    }
    if (!test || !sp.empty()) {                 // (--test: only a session named)
        if (sp.empty()) {
            char exe[4096];
            ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
            std::string d = n > 0 ? std::string(exe, (size_t)n) : std::string(".");
            sp = d.substr(0, d.rfind('/') == std::string::npos ? 0 : d.rfind('/'));
            sp = (sp.empty() ? "." : sp) + "/session.json";
        }
        h->session_path = sp;
        h->session_on = true;
        if (!fresh && access(sp.c_str(), F_OK) == 0) {
            if (!sess::load(sp, h->session)) {          // (live's: set aside as .bad)
                rename(sp.c_str(), (sp + ".bad").c_str());
                fprintf(stderr, "nvlive: %s would not parse: set aside as .bad\n", sp.c_str());
                h->session = sess::J();
            } else {
                fprintf(stderr, "nvlive: the session from %s\n", sp.c_str());
                const sess::J *parts = h->session.get("parts");
                const sess::J *p0 = parts && parts->is(sess::J::ARR) && !parts->a.empty() ? &parts->a[0] : nullptr;
                if (p0 && p0->is(sess::J::OBJ) && !given) {
                    const sess::J *pg = p0->get("program"), *dr = p0->get("drums"), *bk = p0->get("bank");
                    if (pg && pg->is(sess::J::NUM))
                        extra.push_back("--program=" + std::to_string(pg->i()));
                    if (dr && dr->d() != 0.0)
                        extra.push_back("--drums");
                    if (bk && bk->i())
                        extra.push_back("--bank=" + std::to_string(bk->i()));
                }
                // THE MESSENGER turned off ("none"), unless --messenger-out says
                const sess::J *mp = h->session.get("messenger_port");
                bool mo_given = false;
                for (int i = 1; i < argc; i++)
                    mo_given = mo_given || !strncmp(argv[i], "--messenger-out=", 16);
                if (mp && mp->is(sess::J::STR) && mp->s == "none" && !mo_given)
                    extra.push_back("--messenger-out=none");
                // THE PART's TUNER (live.Part's), unless --tuner says otherwise
                const sess::J *tn = p0 && p0->is(sess::J::OBJ) ? p0->get("tuner") : nullptr;
                if (tn && tn->is(sess::J::STR) && !tn->s.empty() && !tuned)
                    extra.push_back("--tuner=" + tn->s);
                if (const sess::J *rs = h->session.get("routes")) {
                    for (const sess::J &r : rs->a) {
                        std::array<int, 7> a;
                        if (route_args(r, a))
                            h->session_routes.push_back(a);
                    }
                    h->session_routes_set = true;
                }
            }
        }
    }
    for (auto &x : extra)
        args.push_back(&x[0]);
    return h->run((int)args.size(), args.data());
}
