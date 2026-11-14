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
    @Published var bufferFrames: Int = UserDefaults.standard.object(forKey: "bufferFrames") as? Int ?? 128 {
        didSet { UserDefaults.standard.set(bufferFrames, forKey: "bufferFrames"); applyBuffer() }
    }
    @Published var latencyMS = 0.0
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
            let args = ["nvlive", path, "--program=0", "--messenger-out=none"]
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
    func midi(_ bytes: [UInt8], at stamp: UInt64) {
        guard let h = host else { return }
        let c = clock.withLock { $0 }
        var frame: Int64 = 0
        if c.hostTime != 0 {
            let now = stamp != 0 ? stamp : mach_absolute_time()
            let dt = (Double(now) - Double(c.hostTime)) / ticksPerSecond
            frame = c.frame + c.frames + Int64((dt * rate).rounded())
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
    private func applyBuffer() {
        guard let au = audio.outputNode.audioUnit else { return }
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
        if selectedPart >= Int32(parts.count) { selectedPart = max(0, Int32(parts.count) - 1) }
        if let sel = parts.first(where: { $0.row == selectedPart }) {
            let id = patches.first { $0.program == sel.program && $0.variation == sel.variation && $0.drums == sel.drums }?.id ?? -1
            if id != current { current = id }
        }
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

    private func poll() {
        guard let h = host else { return }
        pollTick += 1
        if pollTick % 5 == 0 { refreshParts() }     // (twice a second: a preset's parts landing)
        var s = nv_host_snap()
        nv_host_snapshot(h, &s)
        let m = meters
        m.peakL = max(s.peak.0, m.peakL * 0.7)
        m.peakR = max(s.peak.1, m.peakR * 0.7)
        m.load = s.budget_ms > 0 ? s.ms_mean / s.budget_ms : 0
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
