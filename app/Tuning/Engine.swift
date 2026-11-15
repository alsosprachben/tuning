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

    private var host: OpaquePointer?
    private let audio = AVAudioEngine()
    private var source: AVAudioSourceNode?
    private var timer: Timer?
    private var rate = 48000.0

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
            // THE GPU FROM 1500 BUSY SLOTS (nvlive's 100): in the app the GPU is
            // shared with the window's drawing and drops its clock between
            // blocks -- a held organ chord on it ran 2-2.7 ms a block with
            // spikes to 33 ms (a click every few seconds, Ben), on the CPU
            // 0.7-0.9 ms; the dense pedalled file (thousands of slots) still
            // goes to the GPU, where the CPU needs 3.5 ms a block
            let gmin = more.contains { $0.hasPrefix("--gpu-min") } ? [] : ["--gpu-min=1500"]
            let args = ["nvlive", path, "--program=0", "--messenger-out=none"] + gmin + more
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
                self.startAudio(h)
                self.refreshParts()
                self.refreshPresets()
                if restored { self.message = "the last session restored" }
                self.timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.poll() }
                // TUNING_TEST_NOTE: a note held from 2 s to 14 s, by itself (a test with no one playing)
                if ProcessInfo.processInfo.environment["TUNING_TEST_NOTE"] != nil {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.midi([0x90, 60, 100], at: 0) }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 14) { self.midi([0x80, 60, 0], at: 0) }
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
        }
        do {
            try audio.start()
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

    private func setGlobal(_ which: Int32, _ v: Double) {
        if let h = host, nv_host_global(h, which) != v { nv_host_set_global(h, which, v) }
    }

    private var pollTick = 0
    private var slowest = 0.0
    private var dbgMax = 0.0, dbgStep = 0.0, dbgOut = 0.0   // (TUNING_DEBUG: the second's slowest block and its split)

    private func poll() {
        guard let h = host else { return }
        pollTick += 1
        if pollTick % 5 == 0 { refreshParts() }     // (twice a second: a preset's parts landing)
        var s = nv_host_snap()
        nv_host_snapshot(h, &s)
        let m = meters
        if s.ms_max > dbgMax { dbgMax = s.ms_max; dbgStep = s.max_step_ms; dbgOut = s.max_out_ms }
        if debug && pollTick % 10 == 0 {
            FileHandle.standardError.write(String(format: "out: peak %.4f, load %.2f, slowest %.2f ms (before the output %.2f, the output %.2f), over %lld\n",
                                                  s.peak.0, m.load, dbgMax, dbgStep, dbgOut, s.over).data(using: .utf8)!)
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
            m.building = nv_host_building(h) > 0 ? "swapping in" : ""
        }
    }
}

extension String {
    var expandingTildeInPath: String { (self as NSString).expandingTildeInPath }
}
