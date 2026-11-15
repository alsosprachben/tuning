// The engine, as the app sees it: the host library (native/host.h) opened on
// the export, its audio pulled by AVAudioEngine's source node (nv_host_pull:
// any buffer size), its MIDI placed by sample (nv_host_midi_at), its state
// read for the window ten times a second.
import AppKit
import AVFoundation
import AudioToolbox
import Foundation
import os

struct PatchItem: Identifiable, Hashable {
    let id: Int32                // what nv_host_pick takes
    let program: Int32
    let variation: Int32
    let drums: Bool
    let native: Bool
    let name: String

    var label: String {
        drums ? "Drums \(program): \(name)"
              : variation != 0 ? "\(program).\(variation)  \(name)" : "\(program)  \(name)"
    }
}

// what changes ten times a second (the meters, the load, a build's
// progress): an object of its own, so only the header redraws with it --
// the patch list redrawn with every meter tick reentered its table's update
final class Meters: ObservableObject {
    @Published var peakL: Float = 0
    @Published var peakR: Float = 0
    @Published var load = 0.0                    // the block's mean time over its budget
    @Published var building = ""
    @Published var over: Int64 = 0               // blocks past their budget since the start
    @Published var slowestMS = 0.0               // the slowest block in the last second
}

// THE INSERTION EFFECT's TABLES (the export's EFXU): a type, a family, a parameter
struct EfxType: Hashable { let num: Int; let msb: Int; let lsb: Int; let name: String }
struct EfxFamily: Hashable { let first: Int; let last: Int; let name: String }
struct EfxParam: Hashable {
    let n: Int; let name: String; let mark: String; let fresh: Int
    let vals: [Int]; let shown: [String]
    func label(_ v: Int) -> String {
        if let i = vals.firstIndex(of: v), i < shown.count { return shown[i] }
        return "\(v)"
    }
}

// one part as the window shows it (host.h's nv_host_partinfo)
struct PartRow: Identifiable, Equatable {
    let row: Int32
    var id: Int32 { row }
    let program: Int32
    let variation: Int32
    let drums: Bool
    let channel: Int32           // -1 every channel
    let lo: Int32
    let hi: Int32
    let transpose: Int32
    let levelDB: Double
    let muted: Bool
    let solo: Int32              // 0 none, 1 this one, 2 another is
    let name: String
}

// a knob on a Moog part's panel (nv_host_synth_knobs)
struct SynthKnob: Hashable {
    let section: String; let knob: Int; let label: String; let kind: String
    let steps: [Double]; let centred: Bool
}

final class Engine: ObservableObject {
    let meters = Meters()
    @Published var parts: [PartRow] = []
    @Published var selectedPart: Int32 = 0
    @Published var presets: [String] = []
    @Published var message = ""
    @Published var bufferFrames: Int = UserDefaults.standard.object(forKey: "bufferFrames") as? Int ?? 256 {
        didSet { UserDefaults.standard.set(bufferFrames, forKey: "bufferFrames"); applyBuffer() }
    }
    @Published var latencyMS = 0.0
    // THE FIRST PART's ORGAN (livetui's stop rows): its ranks' names, the
    // panel's rows (each a list of groups, each group's ranks), what is drawn
    @Published var stopNames: [String] = []
    @Published var stopRows: [[[Int]]] = []
    @Published var drawn: [Bool] = []
    // TUNING (livetui's t and E): every tuner and what it is for, the rig's
    // now; the Eastern tuning's spec ("" off), its systems and ragas
    @Published var tuners: [(name: String, note: String)] = []
    @Published var tuner = ""
    @Published var eastern = ""
    @Published var ragaSystems: [String] = []
    @Published var ragas: [String] = []
    // THE EFFECTS: the insertion effect's tables and state, the system effects'
    @Published var efxTypes: [EfxType] = []
    @Published var efxFamilies: [EfxFamily] = []
    var efxParams: [String: [EfxParam]] = [:]       // "msb.lsb" -> its parameters
    @Published var efx = nv_host_efx()
    // THE GLOBALS (host.h's NV_G_*) and the rooms the export has
    @Published var g = [Double](repeating: 0, count: Int(NV_G_N))
    @Published var rooms: [String] = []
    // THE SYNTH: the selected part's Moog panel (its layers: 0 not a Moog, -1 unread), an organ's drive
    let synthKnobs: [SynthKnob] = Engine.readSynthKnobs()
    @Published var synthLayers: Int32 = -1
    @Published var synthLayer: Int32 = 0
    @Published var synthPN = [Double](repeating: 0, count: Int(NV_HOST_NKNOBS))
    @Published var synthOwn = [Int8](repeating: 0, count: Int(NV_HOST_NKNOBS))
    @Published var drive: (Int32, Double, Double, Double) = (0, 0, 0, -1)
    // THE CONTROLLER MATRIX of the selected part's channel (nil: not read)
    @Published var cmx: nv_host_cmx? = nil
    @Published var learning: Int32 = 0               // (4 or 5: CC1 or CC2 being learnt)
    var cmxShown = false
    private var cmxReading = false
    private var cmxTurned = Date.distantPast
    @Published var messengerLine = ""
    var synthShown = false                      // (the Synth tab open: its knobs read five times a second)
    private var synthReading = false            // (one read at a time)
    private var synthTurned = Date.distantPast  // (a knob turned here: a read posted before it is not shown)
    @Published var messengerReads = false
    @Published var messengerPre107 = false
    @Published var sysfx = nv_host_sysfx_state()
    private var stopsProgram: Int32 = -2
    // the session (and presets.json beside it): nvlive's on this Mac by
    // default, so the two share presets
    let sessionPath = (UserDefaults.standard.string(forKey: "session") ?? "~/repos/tuning-port/session.json").expandingTildeInPath
    @Published var status = "starting"
    @Published var ready = false
    @Published var patches: [PatchItem] = []
    @Published var current: Int32 = -1
    @Published var masterDB = 0.0 { didSet { setGlobal(Int32(NV_G_MASTER_DB), masterDB) } }
    @Published var gpu = true { didSet { setGlobal(Int32(NV_G_GPU), gpu ? 1 : 0) } }
    @Published var roomTail = true { didSet { setGlobal(Int32(NV_G_ROOM_TAIL), roomTail ? 1 : 0) } }

    private var host: OpaquePointer?
    private let audio = AVAudioEngine()
    private var source: AVAudioSourceNode?
    private var timer: Timer?
    private var rate = 48000.0
    // (a latency-critical, user-initiated activity while the app runs: no App
    // Nap, no timer coalescing -- what audio apps declare)
    private var activity: NSObjectProtocol?

    // THE SAMPLE TIMELINE (nv_host_midi_at's frames): the frames handed out
    // before the latest buffer, that buffer's first sample's host time, and
    // its length -- written by the audio thread, read by MIDI's
    private struct Clock { var frame: Int64 = 0; var hostTime: UInt64 = 0; var frames: Int64 = 512 }
    private let clock = OSAllocatedUnfairLock(initialState: Clock())
    private var framesOut: Int64 = 0             // (the audio thread's own)
    private let ticksPerSecond: Double = {
        var tb = mach_timebase_info_data_t()
        mach_timebase_info(&tb)
        return 1e9 * Double(tb.denom) / Double(tb.numer)
    }()

    func start() {
        guard host == nil else { return }
        let path = (UserDefaults.standard.string(forKey: "export") ?? "~/nvx/live.nvx").expandingTildeInPath
        status = "opening \(path)"
        DispatchQueue.global(qos: .userInitiated).async {
            guard FileManager.default.fileExists(atPath: path) else {
                DispatchQueue.main.async { self.status = "no export at \(path) (native_export.py --live)" }
                return
            }
            // (TUNING_ARGS: more of nvlive's options, for a test -- --cpu, --no-register ...)
            let more = (ProcessInfo.processInfo.environment["TUNING_ARGS"] ?? "").split(separator: " ").map(String.init)
            // THE GPU FROM MANY BUSY SLOTS (nvlive's 100): in the app the GPU is
            // shared with the window's drawing and drops its clock between
            // blocks -- a held organ chord on it ran 2-2.7 ms a block with
            // spikes to 33 ms (a click every few seconds, Ben), on the CPU
            // 0.7-0.9 ms; the dense pedalled file (thousands of slots) still
            // goes to the GPU, where the CPU needs 3.5 ms a block
            // ...and from 4500 since: a six-note organ chord (3348 slots) on
            // the CPU 1.3-1.6 ms a block, on the GPU 2-3 ms with spikes to 8;
            // the CPU near 75% of a block at ~4500. ONE SETUP THREAD (the
            // audio thread itself): its helpers, slow to wake, made 3-10 ms
            // setups; on one, a steady 0.7 ms
            var dflt: [String] = []
            // (2000 since: Ben's playing sat at ~4450 slots, on the CPU 2.4-3.8 ms
            // a block at the worst; from 2000 on the GPU, steady playing clean)
            if !more.contains(where: { $0.hasPrefix("--gpu-min") }) { dflt.append("--gpu-min=2000") }
            if !more.contains(where: { $0.hasPrefix("--gpu-threads") }) { dflt.append("--gpu-threads=1") }
            // TWO GPU BLOCKS IN FLIGHT (+2.7 ms, every note alike): in the app the
            // GPU took ~4 ms to answer a block; one deep, the audio thread waited
            if !more.contains(where: { $0.hasPrefix("--gpu-depth") }) { dflt.append("--gpu-depth=2") }
            // (the governor shedding once blocks pass ~2/3 of their time, not
            // at the limit: room left for the next burst)
            // (--govern-at: not by default -- in the app the governor did not shed;
            // to be looked into)
            let args = ["nvlive", path, "--program=0", "--messenger-out=none"] + dflt + more
            var cargs: [UnsafeMutablePointer<CChar>?] = args.map { strdup($0) }
            var err = [CChar](repeating: 0, count: 512)
            let h = cargs.withUnsafeMutableBufferPointer { nv_host_open_args(Int32(args.count), $0.baseAddress, &err, 512) }
            cargs.forEach { free($0) }
            guard let h else {
                let why = String(cString: err)
                DispatchQueue.main.async { self.status = "the engine would not open: \(why)" }
                return
            }
            nv_host_start(h)
            nv_host_set_realtime(h, 1)            // (the callback never waits on another thread's lock)
            if ProcessInfo.processInfo.environment["TUNING_ROOM_WORKER"] != nil { nv_host_room_inline(h, 0) }   // (a test's)
            // A COLD START: a phrase after a second's rest one block later, the
            // core warmed meanwhile (TUNING_COLD=n blocks for a test; 0 off)
            let cold = Int32(ProcessInfo.processInfo.environment["TUNING_COLD"] ?? "1") ?? 1
            nv_host_set_cold_start(h, cold, 1.0, 0.6)
            nv_host_set_session_path(h, self.sessionPath)
            let restored = nv_host_session_load(h) == 0
            let items = Engine.readPatches(h)
            DispatchQueue.main.async {
                self.host = h
                self.rate = Double(nv_host_rate(h))
                self.patches = items
                var p: Int32 = 0, v: Int32 = 0, d: Int32 = 0
                nv_host_patch_now(h, &p, &v, &d)
                self.current = items.first { $0.program == p && $0.variation == v && $0.drums == (d != 0) }?.id ?? -1
                self.masterDB = nv_host_global(h, Int32(NV_G_MASTER_DB))
                self.gpu = nv_host_global(h, Int32(NV_G_GPU)) != 0
                self.roomTail = nv_host_global(h, Int32(NV_G_ROOM_TAIL)) != 0
                if ProcessInfo.processInfo.environment["TUNING_NO_TAIL"] != nil { self.roomTail = false }   // (a test's)
                self.startAudio(h)
                self.refreshParts()
                self.refreshPresets()
                self.readTuning(h)
                self.readEfxTables(h)
                self.refreshEfx()
                self.readRooms(h)
                self.readGlobals()
                self.messengerReads = nv_host_messenger_reads(h) != 0
                if let m = self.messengerPending { self.messengerPending = nil; self.messengerPlugged(m) }
                if restored { self.message = "the last session restored" }
                self.timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.poll() }
                // TUNING_TEST_NOTE: a note held from 2 s to 14 s, by itself (a test with no one playing)
                // (=chord: six notes, closer to playing)
                // (=stab: a ten-note chord punched staccato, four times a second, 2 s to 14 s)
                // (=phrases: every 3 s from 2 s, four five-note chords a quarter
                // second apart, then silence -- each phrase starting cold)
                if ProcessInfo.processInfo.environment["TUNING_TEST_NOTE"] == "phrases" {
                    let keys: [UInt8] = [48, 55, 60, 64, 67]
                    for ph in 0..<4 {
                        for k in 0..<4 {
                            let t0 = 2.0 + Double(ph) * 3.0 + Double(k) * 0.25
                            let ks = keys.map { $0 + UInt8(k * 2) }
                            DispatchQueue.main.asyncAfter(deadline: .now() + t0) { ks.forEach { self.midi([0x90, $0, 100], at: 0) } }
                            DispatchQueue.main.asyncAfter(deadline: .now() + t0 + 0.2) { ks.forEach { self.midi([0x80, $0, 0], at: 0) } }
                        }
                    }
                } else if ProcessInfo.processInfo.environment["TUNING_TEST_NOTE"] == "stab" {
                    let keys: [UInt8] = [36, 43, 48, 52, 55, 60, 64, 67, 72, 76]
                    for k in 0..<48 {
                        let t0 = 2.0 + Double(k) * 0.25
                        DispatchQueue.main.asyncAfter(deadline: .now() + t0) { keys.forEach { self.midi([0x90, $0, 110], at: 0) } }
                        DispatchQueue.main.asyncAfter(deadline: .now() + t0 + 0.09) { keys.forEach { self.midi([0x80, $0, 0], at: 0) } }
                    }
                } else if let t = ProcessInfo.processInfo.environment["TUNING_TEST_NOTE"] {
                    let keys: [UInt8] = t == "chord" ? [48, 55, 60, 64, 67, 72] : [60]
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2) { keys.forEach { self.midi([0x90, $0, 100], at: 0) } }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 14) { keys.forEach { self.midi([0x80, $0, 0], at: 0) } }
                }
                NotificationCenter.default.addObserver(forName: NSApplication.willTerminateNotification, object: nil,
                                                       queue: .main) { [weak self] _ in self?.saveSession() }
            }
        }
    }

    private static func readPatches(_ h: OpaquePointer) -> [PatchItem] {
        let n = nv_host_patches(h, nil, 0)
        guard n > 0 else { return [] }
        var buf = [nv_host_patch](repeating: nv_host_patch(), count: Int(n))
        nv_host_patches(h, &buf, n)
        return buf.map { p in
            let name = withUnsafeBytes(of: p.name) { String(cString: $0.bindMemory(to: CChar.self).baseAddress!) }
            return PatchItem(id: p.pick, program: p.program, variation: p.variation, drums: p.drums != 0,
                             native: p.native != 0, name: name)
        }
    }

    // AVAudioEngine's source node asks for its buffer; the host fills it
    private func startAudio(_ h: OpaquePointer) {
        guard let fmt = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 2) else { return }
        let src = AVAudioSourceNode(format: fmt) { [unowned self] _, ts, frameCount, abl -> OSStatus in
            let list = UnsafeMutableAudioBufferListPointer(abl)
            guard list.count >= 2, let l = list[0].mData, let r = list[1].mData else { return noErr }
            let n = Int64(frameCount)
            let at = self.framesOut
            let ht = ts.pointee.mHostTime
            self.clock.withLock { $0 = Clock(frame: at, hostTime: ht, frames: n) }
            nv_host_pull(h, l.assumingMemoryBound(to: Float.self), r.assumingMemoryBound(to: Float.self), Int32(frameCount))
            self.framesOut = at + n
            return noErr
        }
        source = src
        audio.attach(src)
        audio.connect(src, to: audio.mainMixerNode, format: fmt)
        applyBuffer()
        // the device changed under it (another output chosen, its rate or
        // buffer): AVAudioEngine has stopped -- the buffer asked again, started
        NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: audio,
                                               queue: .main) { [weak self] _ in
            guard let self else { return }
            self.applyBuffer()
            if !self.audio.isRunning { try? self.audio.start() }
            self.joinWorkgroup()
        }
        activity = ProcessInfo.processInfo.beginActivity(options: [.userInitiated, .latencyCritical],
                                                         reason: "live audio")
        do {
            try audio.start()
            joinWorkgroup()
            status = "playing"
            ready = true
        } catch {
            status = "no audio: \(error.localizedDescription)"
        }
    }

    // A MIDI message at its CoreMIDI time (0: now), placed a buffer after
    // that moment in the engine's timeline -- each message keeps its distance
    // from the last, however many blocks a buffer holds
    let debug = ProcessInfo.processInfo.environment["TUNING_DEBUG"] != nil

    func midi(_ bytes: [UInt8], at stamp: UInt64) {
        guard let h = host else {
            if debug { FileHandle.standardError.write("midi before the engine opened: \(bytes)\n".data(using: .utf8)!) }
            return
        }
        let c = clock.withLock { $0 }
        var frame: Int64 = 0
        if c.hostTime != 0 {
            let now = stamp != 0 ? stamp : mach_absolute_time()
            let dt = (Double(now) - Double(c.hostTime)) / ticksPerSecond
            // the clock gone stale (no buffer asked for a while: the audio
            // stopped or stalled) -- the next block, not a place it predicts;
            // and never more than two buffers ahead, so nothing piles up
            let stale = (Double(mach_absolute_time()) - Double(c.hostTime)) / ticksPerSecond > 4.0 * Double(c.frames) / rate + 0.05
            if !stale {
                frame = min(c.frame + c.frames + Int64((dt * rate).rounded()), c.frame + 3 * c.frames)
            }
        }
        if debug {
            let line = String(format: "midi %@ at frame %lld (handed out %lld, buffer %lld, stamp %llu, buffer's host time %llu)\n",
                              bytes.map { String(format: "%02X", $0) }.joined(separator: " "), frame, c.frame, c.frames,
                              stamp, c.hostTime)
            FileHandle.standardError.write(line.data(using: .utf8)!)
        }
        bytes.withUnsafeBufferPointer { nv_host_midi_at(h, $0.baseAddress, Int32($0.count), frame) }
    }

    // a patch for the selected part (built on the builder, swapped in)
    func pick(_ id: Int32) {
        guard let h = host else { return }
        nv_host_part_pick(h, selectedPart, id)
        current = id
    }

    // ---- THE DEVICE's BUFFER: its frames asked of the output (a block's
    // 128 by default: AVAudioEngine's own 512 was ~10 ms more latency), the
    // latency it gives read back ----
    // (AVAudioEngine stops when its device is reconfigured under it -- a
    // buffer size set while it ran left it silent, the MIDI meanwhile placed
    // by a clock gone stale: so it is stopped, set, started again)
    private func applyBuffer() {
        guard let au = audio.outputNode.audioUnit else { return }
        let was = audio.isRunning
        if was { audio.stop() }
        defer {
            if was {
                do { try audio.start() } catch { status = "no audio: \(error.localizedDescription)" }
            }
        }
        var frames = UInt32(bufferFrames)
        AudioUnitSetProperty(au, kAudioDevicePropertyBufferFrameSize, kAudioUnitScope_Global, 0, &frames,
                             UInt32(MemoryLayout<UInt32>.size))
        var got: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        AudioUnitGetProperty(au, kAudioDevicePropertyBufferFrameSize, kAudioUnitScope_Global, 0, &got, &size)
        let device = audio.outputNode.presentationLatency
        latencyMS = 1000.0 * (2.0 * Double(got) / rate + device)
    }

    // ---- THE GLOBALS ----
    private func readRooms(_ h: OpaquePointer) {
        var buf = [CChar](repeating: 0, count: 8192)
        nv_host_rooms(h, &buf, 8192)
        rooms = String(cString: buf).split(separator: "\n").map(String.init)
    }

    func readGlobals() {
        guard let h = host else { return }
        let now = (0..<Int(NV_G_N)).map { nv_host_global(h, Int32($0)) }
        if now != g { g = now }
    }

    func setG(_ i: Int32, _ v: Double) {
        guard host != nil else { return }
        g[Int(i)] = v
        setGlobal(i, v)
    }

    // ---- THE SYNTH ----
    private static func readSynthKnobs() -> [SynthKnob] {
        var buf = [CChar](repeating: 0, count: 16384)
        nv_host_synth_knobs(&buf, 16384)
        return String(cString: buf).split(separator: "\n").compactMap { line in
            let f = line.split(separator: "\t", omittingEmptySubsequences: false).map(String.init)
            guard f.count >= 6 else { return nil }
            return SynthKnob(section: f[0], knob: Int(f[1]) ?? -1, label: f[2], kind: f[3],
                             steps: f[4].split(separator: ",").compactMap { Double($0) }, centred: f[5] == "1")
        }
    }

    func synthText(_ k: SynthKnob) -> String {
        guard k.knob >= 0 else { return "-" }
        var out = [CChar](repeating: 0, count: 64)
        nv_host_synth_fmt(k.kind, synthPN[k.knob], synthPN, &out, 64)
        return String(cString: out)
    }

    // the selected part's panel, read between two blocks (off the main thread: it waits for one)
    func refreshSynth() {
        guard let h = host else { return }
        if synthReading { return }
        synthReading = true
        let row = selectedPart, layer = synthLayer, asked = Date()
        DispatchQueue.global(qos: .userInitiated).async {
            var pn = [Double](repeating: 0, count: Int(NV_HOST_NKNOBS))
            var own = [CChar](repeating: 0, count: Int(NV_HOST_NKNOBS))
            var n = nv_host_synth_get(h, row, layer, &pn, &own)
            var lay = layer
            if n > 0 && layer >= n { lay = 0; n = nv_host_synth_get(h, row, 0, &pn, &own) }
            var dv = [Double](repeating: 0, count: 3)
            let dr = n > 0 ? 0 : nv_host_drive(h, row, &dv)
            var ml = [CChar](repeating: 0, count: 256)
            nv_host_messenger_line(h, &ml, 256)
            let line = String(cString: ml), reads = nv_host_messenger_reads(h) != 0, pre = nv_host_messenger_pre107(h) != 0
            DispatchQueue.main.async {
                self.synthReading = false
                guard row == self.selectedPart, layer == self.synthLayer else { return }
                if n != self.synthLayers { self.synthLayers = n }
                if lay != self.synthLayer { self.synthLayer = lay }
                // (only what changed is published -- and not a read asked before a knob turned here)
                if n > 0 && asked > self.synthTurned {
                    if pn != self.synthPN { self.synthPN = pn }
                    let o = own.map { Int8($0) }
                    if o != self.synthOwn { self.synthOwn = o }
                }
                let d = self.drive
                if asked > self.synthTurned, d.0 != dr || d.1 != dv[0] || d.2 != dv[1] || d.3 != dv[2] { self.drive = (dr, dv[0], dv[1], dv[2]) }
                if line != self.messengerLine { self.messengerLine = line }
                if reads != self.messengerReads { self.messengerReads = reads }
                if pre != self.messengerPre107 { self.messengerPre107 = pre }
            }
        }
    }

    func setKnob(_ k: SynthKnob, _ v: Double) {
        guard let h = host, k.knob >= 0 else { return }
        nv_host_synth_set(h, selectedPart, synthLayer, Int32(k.knob), v)
        synthTurned = Date()
        synthPN[k.knob] = v                       // (the part has it at once)
        synthOwn[k.knob] = 1
    }

    func forgetKnob(_ k: SynthKnob) {
        guard let h = host, k.knob >= 0 else { return }
        nv_host_synth_forget(h, selectedPart, synthLayer, Int32(k.knob))
        synthOwn[k.knob] = 0
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in self?.refreshSynth() }
    }

    func forgetAllKnobs() {
        for k in synthKnobs where k.knob >= 0 && synthOwn[k.knob] != 0 { forgetKnob(k) }
    }

    func sendToMessenger() -> Bool {
        guard let h = host else { return false }
        return nv_host_synth_send(h, selectedPart) != 0
    }

    func setMessengerReads(_ on: Bool) {
        guard let h = host else { return }
        messengerAuto = false                    // (by hand, or by messengerPlugged, which sets it again)
        nv_host_set_messenger_reads(h, on ? 1 : 0)
        messengerReads = on
    }

    // A MESSENGER PLUGGED IN (an input named so, on): every part reads its
    // knobs; unplugged, General MIDI controllers again -- unless the switch
    // was set by hand meanwhile. Before the engine opens, kept for it.
    private var messengerPending: Bool? = nil
    private var messengerAuto = false
    func messengerPlugged(_ on: Bool) {
        guard host != nil else { messengerPending = on; return }
        if on && !messengerReads {
            setMessengerReads(true)
            messengerAuto = true
            message = "a Moog Messenger: every part reads its knobs"
        } else if !on && messengerAuto && messengerReads {
            setMessengerReads(false)
            messengerAuto = false
            message = "the Messenger unplugged: General MIDI controllers again"
        }
    }

    func setMessengerPre107(_ on: Bool) {
        guard let h = host else { return }
        nv_host_set_messenger_pre107(h, on ? 1 : 0)
        messengerPre107 = on
    }

    func setDrive(_ v: Double) {            // (v < 0: the voice's)
        guard let h = host else { return }
        nv_host_set_drive(h, selectedPart, v)
        synthTurned = Date()
        drive.1 = v < 0 ? drive.2 : v
        drive.3 = v
    }

    // ---- THE CONTROLLER MATRIX ----
    var cmxChannel: Int32 { parts.first { $0.row == selectedPart }?.channel ?? 0 }   // (-1 every channel)

    func refreshCmx() {
        guard let h = host, !cmxReading else { return }
        cmxReading = true
        let ch = cmxChannel, asked = Date()
        DispatchQueue.global(qos: .userInitiated).async {
            var m = nv_host_cmx()
            let ok = nv_host_cmx_state(h, ch, &m) == 0
            DispatchQueue.main.async {
                self.cmxReading = false
                guard ok, ch == self.cmxChannel, asked > self.cmxTurned else { return }
                if var old = self.cmx, memcmp(&old, &m, MemoryLayout<nv_host_cmx>.size) == 0 { return }
                self.cmx = m
            }
        }
    }

    func cmxDepth(_ src: Int, _ dest: Int) -> Double {
        guard let m = cmx else { return 0 }
        return withUnsafeBytes(of: m.depth) { $0.bindMemory(to: Double.self)[src * 11 + dest] }
    }

    func setCmx(_ src: Int, _ dest: Int, raw: Int) {
        guard let h = host else { return }
        nv_host_cmx_cell(h, cmxChannel, Int32(src), Int32(dest), Int32(raw))
        cmxTurned = Date()
        if var m = cmx {                          // (shown at once; the read after confirms it)
            withUnsafeMutableBytes(of: &m.depth) { $0.bindMemory(to: Double.self)[src * 11 + dest] = nv_host_cmx_depth(Int32(dest), Int32(raw)) }
            cmx = m
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in self?.refreshCmx() }
    }

    func assignCmx(_ which: Int32, _ cc: Int) {
        guard let h = host else { return }
        nv_host_cmx_assign(h, cmxChannel, which, Int32(cc))
        cmxTurned = Date()
        if var m = cmx { if which == 4 { m.cc1 = Int32(cc) } else { m.cc2 = Int32(cc) }; cmx = m }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in self?.refreshCmx() }
    }

    // CC1 or CC2 learnt: the next controller moved (1-95) within eight seconds
    func learnCmx(_ which: Int32) {
        guard let h = host else { return }
        learning = which
        let t0 = nv_host_now_ns()
        var tries = 0
        Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] t in
            guard let self else { t.invalidate(); return }
            tries += 1
            var when: Int64 = 0
            let code = nv_host_last_ctl(h, &when)
            if code > 0 && code <= 95 && when > t0 {
                t.invalidate()
                self.learning = 0
                self.assignCmx(which, Int(code))
                self.message = "\(which == 4 ? "CC1" : "CC2") is CC\(code)"
            } else if tries > 160 || self.learning != which {
                t.invalidate()
                if self.learning == which { self.learning = 0; self.message = "nothing moved" }
            }
        }
    }

    // ---- THE EFFECTS ----
    private func readEfxTables(_ h: OpaquePointer) {
        let cap = 1 << 21
        var buf = [CChar](repeating: 0, count: cap)
        nv_host_efx_tables(h, &buf, Int32(cap))
        var types: [EfxType] = [], fams: [EfxFamily] = [], params: [String: [EfxParam]] = [:]
        for line in String(cString: buf).split(separator: "\n") {
            let f = line.split(separator: "\t", omittingEmptySubsequences: false).map(String.init)
            if f[0] == "T", f.count >= 5 {
                types.append(EfxType(num: Int(f[1]) ?? 0, msb: Int(f[2]) ?? 0, lsb: Int(f[3]) ?? 0, name: f[4]))
            } else if f[0] == "C", f.count >= 4 {
                fams.append(EfxFamily(first: Int(f[1]) ?? 0, last: Int(f[2]) ?? 0, name: f[3]))
            } else if f[0] == "P", f.count >= 10 {
                let p = EfxParam(n: Int(f[3]) ?? 0, name: f[4], mark: f[5], fresh: Int(f[7]) ?? 0,
                                 vals: f[8].split(separator: ",").compactMap { Int($0) },
                                 shown: f[9].split(separator: "\u{1f}", omittingEmptySubsequences: false).map(String.init))
                params["\(f[1]).\(f[2])", default: []].append(p)
            }
        }
        efxTypes = types
        efxFamilies = fams
        efxParams = params
    }

    func refreshEfx() {
        guard let h = host else { return }
        var e = nv_host_efx()
        nv_host_efx_state(h, &e)
        // (published only when it changed: a publish redraws every pane)
        var old = efx
        if memcmp(&old, &e, MemoryLayout<nv_host_efx>.size) != 0 { efx = e }
    }

    func refreshSysfx() {
        guard let h = host else { return }
        var s = nv_host_sysfx_state()
        DispatchQueue.global(qos: .userInitiated).async {
            nv_host_sysfx(h, &s)                  // (read between two blocks: not on the main thread)
            DispatchQueue.main.async { self.sysfx = s }
        }
    }

    // the channels a part listens on (all for -1)
    private func channels(of part: PartRow?) -> [Int32] {
        guard let p = part else { return [0] }
        return p.channel < 0 ? Array(0..<16) : [p.channel]
    }

    var selectedOnEfx: Bool {
        let p = parts.first { $0.row == selectedPart }
        let on = Set(withUnsafeBytes(of: efx.parts) { Array($0.bindMemory(to: Int32.self).prefix(Int(efx.nparts))) })
        return channels(of: p).allSatisfy { on.contains($0) }
    }

    func setSelectedOnEfx(_ on: Bool) {
        guard let h = host else { return }
        for c in channels(of: parts.first { $0.row == selectedPart }) {
            nv_host_efx_send(h, Int32(UInt8(ascii: "c")), c, on ? 1 : 0)
        }
        afterEfx()
    }

    func setEfxType(_ t: EfxType) {
        guard let h = host else { return }
        nv_host_efx_send(h, Int32(UInt8(ascii: "t")), Int32(t.msb), Int32(t.lsb))
        afterEfx()
    }

    func setEfxParam(_ n: Int, _ v: Int) {
        guard let h = host else { return }
        nv_host_efx_send(h, Int32(UInt8(ascii: "p")), Int32(n), Int32(v))
        afterEfx()
    }

    func setEfxAddress(_ a: Int, _ v: Int) {
        guard let h = host else { return }
        nv_host_efx_send(h, Int32(UInt8(ascii: "s")), Int32(a), Int32(v))
        afterEfx()
    }

    private func afterEfx() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in self?.refreshEfx() }
    }

    func setSysfx(_ hi: Int, _ lo: Int, _ v: Int) {
        guard let h = host else { return }
        nv_host_sysfx_send(h, Int32(hi), Int32(lo), Int32(v))
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in self?.refreshSysfx() }
    }

    // ---- TUNING ----
    private func readTuning(_ h: OpaquePointer) {
        var buf = [CChar](repeating: 0, count: 16384)
        nv_host_tuners(&buf, 16384)
        tuners = String(cString: buf).split(separator: "\n").map { line in
            let f = line.split(separator: "\t", maxSplits: 1).map(String.init)
            return (f[0], f.count > 1 ? f[1] : "")
        }
        nv_host_tuner(h, &buf, 16384)
        tuner = String(cString: buf)
        nv_host_eastern(h, &buf, 16384)
        eastern = String(cString: buf)
        var sys: [String] = [], rg: [String] = []
        var i: Int32 = 0
        while let p = nv_raga_system_name(i) { sys.append(String(cString: p)); i += 1 }
        i = 0
        while let p = nv_raga_name(i, nil, nil) { rg.append(String(cString: p)); i += 1 }
        ragaSystems = sys.sorted()
        ragas = rg.filter { !$0.hasPrefix("saraga_") }.sorted()
    }

    func setTuner(_ name: String) {
        guard let h = host, !name.isEmpty else { return }
        nv_host_set_tuner(h, name)
        tuner = name
        message = "tuner: \(name) (the patches built again in it)"
    }

    func setEastern(_ spec: String) {
        guard let h = host else { return }
        nv_host_set_eastern(h, spec)
        eastern = spec
        message = spec.isEmpty ? "Eastern tuning off" : "Eastern tuning: \(spec)"
    }

    // ---- THE PARTS ----
    func refreshParts() {
        guard let h = host else { return }
        let n = nv_host_parts(h, nil, 0)
        var buf = [nv_host_partinfo](repeating: nv_host_partinfo(), count: Int(max(n, 0)))
        if n > 0 { nv_host_parts(h, &buf, n) }
        let rows = buf.map { p in
            PartRow(row: p.row, program: p.program, variation: p.variation, drums: p.drums != 0, channel: p.channel,
                    lo: p.lo, hi: p.hi, transpose: p.transpose, levelDB: p.level_db, muted: p.muted != 0, solo: p.solo,
                    name: withUnsafeBytes(of: p.name) { String(cString: $0.bindMemory(to: CChar.self).baseAddress!) })
        }
        if rows != parts { parts = rows }
        let organ = rows.first.map { $0.drums ? -1 : $0.program } ?? -1
        if organ != stopsProgram { stopsProgram = organ; readStopLayout(h, organ) }
        readDrawn(h)
        if selectedPart >= Int32(parts.count) { selectedPart = max(0, Int32(parts.count) - 1) }
        if let sel = parts.first(where: { $0.row == selectedPart }) {
            let id = patches.first { $0.program == sel.program && $0.variation == sel.variation && $0.drums == sel.drums }?.id ?? -1
            if id != current { current = id }
        }
    }

    private func readStopLayout(_ h: OpaquePointer, _ program: Int32) {
        guard program >= 0 else { stopNames = []; stopRows = []; drawn = []; return }
        var buf = [CChar](repeating: 0, count: 16384)
        let n = nv_host_stop_names(h, program, &buf, 16384)
        stopNames = n > 0 ? String(cString: buf).split(separator: "\n", omittingEmptySubsequences: false).map(String.init) : []
        let k = nv_host_stop_rows(h, program, nil, 0)
        var ints = [Int32](repeating: 0, count: Int(max(k, 0)))
        if k > 0 { nv_host_stop_rows(h, program, &ints, k) }
        var rows: [[[Int]]] = [], row: [[Int]] = [], group: [Int] = []
        for x in ints {
            if x == -1 {
                if !group.isEmpty { row.append(group) }
                if !row.isEmpty { rows.append(row) }
                row = []; group = []
            } else if x == -2 {
                if !group.isEmpty { row.append(group) }
                group = []
            } else {
                group.append(Int(x))
            }
        }
        stopRows = rows
    }

    private func readDrawn(_ h: OpaquePointer) {
        guard !stopNames.isEmpty else { if !drawn.isEmpty { drawn = [] }; return }
        var d = [CChar](repeating: 0, count: stopNames.count)
        let n = nv_host_drawn(h, &d, Int32(d.count))
        let now = (0..<stopNames.count).map { $0 < Int(n) && d[$0] != 0 }
        if now != drawn { drawn = now }
    }

    func toggleStop(_ rank: Int) {
        guard let h = host else { return }
        nv_host_toggle_stop(h, Int32(rank))
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in self?.readDrawn(h) }
    }

    func setPart(_ p: PartRow, channel: Int32? = nil, lo: Int32? = nil, hi: Int32? = nil, transpose: Int32? = nil,
                 levelDB: Double? = nil, muted: Bool? = nil) {
        guard let h = host else { return }
        nv_host_part_set(h, p.row, channel ?? p.channel, lo ?? p.lo, hi ?? p.hi, transpose ?? p.transpose,
                         levelDB ?? p.levelDB, (muted ?? p.muted) ? 1 : 0)
        refreshParts()
    }

    func layer(_ row: Int32) {
        guard let h = host else { return }
        message = nv_host_part_layer(h, row) == 0 ? "layered part \(row + 1)" : "could not layer"
        refreshParts()
    }

    func split(_ row: Int32) {
        guard let h = host else { return }
        var why = [CChar](repeating: 0, count: 256)
        message = nv_host_part_split(h, row, &why, 256) == 0 ? "split part \(row + 1)" : String(cString: why)
        refreshParts()
    }

    func delete(_ row: Int32) {
        guard let h = host else { return }
        var why = [CChar](repeating: 0, count: 256)
        message = nv_host_part_delete(h, row, &why, 256) == 0 ? "removed part \(row + 1)" : String(cString: why)
        refreshParts()
    }

    func solo(_ row: Int32) {
        guard let h = host else { return }
        nv_host_part_solo(h, row)
        refreshParts()
    }

    // ---- PRESETS (presets.json beside the session: nvlive's and live.py's) ----
    func refreshPresets() {
        guard let h = host else { return }
        var buf = [CChar](repeating: 0, count: 65536)
        nv_host_presets(h, &buf, 65536)
        presets = String(cString: buf).split(separator: "\n").map(String.init).sorted {
            $0.localizedCaseInsensitiveCompare($1) == .orderedAscending
        }
    }

    func savePreset(_ name: String) {
        guard let h = host, !name.isEmpty else { return }
        var msg = [CChar](repeating: 0, count: 256)
        nv_host_preset_save(h, name, &msg, 256)
        message = String(cString: msg)
        refreshPresets()
    }

    func loadPreset(_ name: String) {
        guard let h = host else { return }
        var msg = [CChar](repeating: 0, count: 256)
        nv_host_preset_load(h, name, &msg, 256)
        message = String(cString: msg)
        selectedPart = 0
    }

    func saveSession() {
        if let h = host { nv_host_session_save(h) }
    }

    func panic() {
        if let h = host { nv_host_panic(h) }
    }

    // the output's audio workgroup, for the engine's helper threads to join
    // (Apple's way: they wake promptly on fast cores, counted with the audio)
    private func joinWorkgroup() {
        guard let h = host, let au = audio.outputNode.audioUnit else { return }
        let r = nv_host_join_output_workgroup(h, UnsafeMutableRawPointer(au))
        if debug { FileHandle.standardError.write("audio workgroup: \(r == 0 ? "joined" : "none")\n".data(using: .utf8)!) }
    }

    private func setGlobal(_ which: Int32, _ v: Double) {
        if let h = host, nv_host_global(h, which) != v { nv_host_set_global(h, which, v) }
    }

    private var pollTick = 0
    private var waiting = 0, messageTick = 0
    private var shownMessage = ""
    private var slowest = 0.0
    private var dbgMax = 0.0, dbgStep = 0.0, dbgOut = 0.0   // (TUNING_DEBUG: the second's slowest block and its split)
    private var dbgBusy = 0.0, dbgGpu = 0.0, dbgSetup = 0.0, dbgSamples = 0.0, dbgUser = 0.0, dbgSys = 0.0

    private func poll() {
        guard let h = host else { return }
        pollTick += 1
        if pollTick % 5 == 0 { refreshParts(); refreshEfx() }
        if pollTick % 10 == 3 { readGlobals() }
        if synthShown && pollTick % 2 == 0 { refreshSynth() }
        if cmxShown && pollTick % 10 == 5 { refreshCmx() }      // (a file's or a sequencer's messages: shown)    // (a Messenger's knobs turned: shown as they land)     // (twice a second: a preset's, a file's)
        var s = nv_host_snap()
        nv_host_snapshot(h, &s)
        let m = meters
        if s.ms_max > dbgMax {
            dbgMax = s.ms_max; dbgStep = s.max_step_ms; dbgOut = s.max_out_ms
            dbgBusy = s.max_busy; dbgGpu = s.max_gpu; dbgSetup = s.max_gpu_setup_ms; dbgSamples = s.max_gpu_samples_ms
            dbgUser = s.max_cpu_user_ms; dbgSys = s.max_cpu_sys_ms
        }
        if debug && pollTick % 10 == 0 {
            FileHandle.standardError.write(String(format: "out: peak %.4f, load %.2f, slowest %.2f ms [cpu user %.2f sys %.2f] (before the output %.2f, the output %.2f; %.0f busy, %@), over %lld\n",
                                                  s.peak.0, m.load, dbgMax, dbgUser, dbgSys, dbgStep, dbgOut, dbgBusy,
                                                  dbgGpu != 0 ? String(format: "GPU setup %.2f samples %.2f", dbgSetup, dbgSamples) : "CPU",
                                                  s.over).data(using: .utf8)!)
            dbgMax = 0; dbgStep = 0; dbgOut = 0
            var mb = [CChar](repeating: 0, count: 512)
            while nv_host_message(h, &mb, 512) > 0 {
                FileHandle.standardError.write("engine: \(String(cString: mb))\n".data(using: .utf8)!)
            }
        }
        m.peakL = max(s.peak.0, m.peakL * 0.7)
        m.peakR = max(s.peak.1, m.peakR * 0.7)
        m.load = s.budget_ms > 0 ? s.ms_mean / s.budget_ms : 0
        // (blocks past their budget, and the slowest of the last second: a
        // click matched to a number -- the engine's own, or the machine's load)
        if m.over != s.over { m.over = s.over }
        slowest = max(slowest, s.ms_max)
        if pollTick % 10 == 0 {
            m.slowestMS = slowest
            slowest = 0
        }
        var done = 0, total = 0
        var name = [CChar](repeating: 0, count: 128)
        if nv_host_progress(h, &done, &total, &name, 128) != 0 {
            m.building = "building \(String(cString: name)) \(total > 0 ? 100 * done / total : 0)%"
        } else {
            // ("swapping in" only when something has waited three polls: a knob's
            // read lands within a block, and the Synth tab asks five times a second)
            waiting = nv_host_building(h) > 0 ? waiting + 1 : 0
            let b = waiting >= 3 ? "swapping in" : ""
            if m.building != b { m.building = b }
        }
        // (a message shown six seconds, then gone)
        if message != shownMessage { shownMessage = message; messageTick = pollTick }
        if !message.isEmpty && pollTick - messageTick > 60 { message = ""; shownMessage = "" }
    }
}

extension String {
    var expandingTildeInPath: String { (self as NSString).expandingTildeInPath }
}
