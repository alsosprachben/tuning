// The MIDI inputs: CoreMIDI's sources, any number on at once (merged, as
// nvlive's I), each message handed on as the bytes a keyboard sends with its
// CoreMIDI timestamp. MIDI 1.0 protocol: CoreMIDI translates any source.
// A source unplugged and plugged in again is connected again by its name.
import CoreMIDI
import Foundation

final class MidiIn: ObservableObject {
    struct Source: Identifiable, Hashable {
        let id: MIDIUniqueID
        let name: String
    }

    @Published var sources: [Source] = []
    @Published var on: Set<String> = []          // by name: kept across unplugging
    var onMessage: (([UInt8], MIDITimeStamp) -> Void)?

    private var client = MIDIClientRef()
    private var port = MIDIPortRef()
    private var connected: [MIDIUniqueID: MIDIEndpointRef] = [:]
    private var sysex: [UInt8] = []              // (an exclusive across packets)

    func start() {
        guard client == 0 else { return }
        MIDIClientCreateWithBlock("Tuning" as CFString, &client) { [weak self] _ in
            DispatchQueue.main.async { self?.refresh() }
        }
        MIDIInputPortCreateWithProtocol(client, "in" as CFString, ._1_0, &port) { [weak self] list, _ in
            self?.receive(list)
        }
        // every source but the IAC bus at first, as nvlive finds the keyboard by itself
        let first = Self.list().filter { !$0.name.localizedCaseInsensitiveContains("IAC") }
        on = Set(first.map { $0.name })
        refresh()
    }

    static func list() -> [Source] {
        (0..<MIDIGetNumberOfSources()).compactMap { i in
            let e = MIDIGetSource(i)
            var id: MIDIUniqueID = 0
            MIDIObjectGetIntegerProperty(e, kMIDIPropertyUniqueID, &id)
            var name: Unmanaged<CFString>?
            MIDIObjectGetStringProperty(e, kMIDIPropertyDisplayName, &name)
            return Source(id: id, name: (name?.takeRetainedValue() as String?) ?? "source \(i)")
        }
    }

    func refresh() {
        sources = Self.list()
        if ProcessInfo.processInfo.environment["TUNING_DEBUG"] != nil {
            FileHandle.standardError.write("midi sources: \(sources.map { $0.name }), on: \(on)\n".data(using: .utf8)!)
        }
        for i in 0..<MIDIGetNumberOfSources() {
            let e = MIDIGetSource(i)
            guard let s = sources.first(where: { src in
                var id: MIDIUniqueID = 0
                MIDIObjectGetIntegerProperty(e, kMIDIPropertyUniqueID, &id)
                return src.id == id
            }) else { continue }
            let want = on.contains(s.name)
            if want && connected[s.id] == nil {
                MIDIPortConnectSource(port, e, nil)
                connected[s.id] = e
            } else if !want, let c = connected[s.id] {
                MIDIPortDisconnectSource(port, c)
                connected[s.id] = nil
            }
        }
        let present = Set(sources.map { $0.id })
        for id in connected.keys where !present.contains(id) { connected[id] = nil }   // (unplugged)
    }

    func toggle(_ s: Source) {
        if on.contains(s.name) { on.remove(s.name) } else { on.insert(s.name) }
        refresh()
    }

    // UMP (MIDI 1.0 protocol) to the bytes a keyboard sends, message by message
    private func receive(_ list: UnsafePointer<MIDIEventList>) {
        for packet in list.unsafeSequence() {
            let stamp = packet.pointee.timeStamp
            let n = Int(packet.pointee.wordCount)
            let words: [UInt32] = withUnsafeBytes(of: packet.pointee.words) { raw in
                Array(raw.bindMemory(to: UInt32.self).prefix(n))
            }
            var i = 0
            while i < words.count {
                let w = words[i]
                let mt = Int(w >> 28)
                let len = mt <= 2 ? 1 : mt <= 4 ? 2 : 4
                switch mt {
                case 1:                                         // system common / real time
                    let st = UInt8((w >> 16) & 0xFF)
                    var b = [st]
                    let nd = st == 0xF1 || st == 0xF3 ? 1 : st == 0xF2 ? 2 : 0
                    if nd >= 1 { b.append(UInt8((w >> 8) & 0x7F)) }
                    if nd >= 2 { b.append(UInt8(w & 0x7F)) }
                    onMessage?(b, stamp)
                case 2:                                         // a channel voice message
                    let st = UInt8((w >> 16) & 0xFF)
                    var b = [st, UInt8((w >> 8) & 0x7F)]
                    let hi = st & 0xF0
                    if hi != 0xC0 && hi != 0xD0 { b.append(UInt8(w & 0x7F)) }
                    onMessage?(b, stamp)
                case 3 where i + 1 < words.count:               // an exclusive, six bytes a packet
                    let status = Int((w >> 20) & 0xF), cnt = Int((w >> 16) & 0xF)
                    let w1 = words[i + 1]
                    let d: [UInt8] = [UInt8((w >> 8) & 0x7F), UInt8(w & 0x7F), UInt8((w1 >> 24) & 0x7F),
                                      UInt8((w1 >> 16) & 0x7F), UInt8((w1 >> 8) & 0x7F), UInt8(w1 & 0x7F)]
                    if status == 0 || status == 1 { sysex = [0xF0] }
                    sysex += d.prefix(min(cnt, 6))
                    if status == 0 || status == 3 {
                        onMessage?(sysex + [0xF7], stamp)
                        sysex = []
                    }
                default:
                    break
                }
                i += len
            }
        }
    }
}
