// The window: the parts (each one's channel, keys, transpose, level, mute,
// solo; layer, split, remove), the patches for the selected part
// (searchable), the presets, the MIDI inputs and the output -- with what is
// playing, the meters and the load across the top.
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var engine: Engine
    @EnvironmentObject var midi: MidiIn
    @State private var query = ""
    @State private var selection: Int32? = nil

    private var shown: [PatchItem] {
        let words = query.lowercased().split(separator: " ")
        return engine.patches.filter { p in
            p.native && words.allSatisfy { p.label.lowercased().contains($0) }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            Header(status: engine.status, message: engine.message, meters: engine.meters, panic: engine.panic)
            Divider()
            HStack(spacing: 0) {
                PartsPane()
                    .frame(width: 330)
                Divider()
                VStack(spacing: 0) {
                    Text(partTitle).font(.subheadline).foregroundStyle(.secondary).padding(.top, 8)
                    TextField("Search patches", text: $query)
                        .textFieldStyle(.roundedBorder)
                        .padding(8)
                    if engine.ready {
                        List(shown, selection: $selection) { p in
                            Text(p.label).tag(p.id)
                        }
                        .onChange(of: selection) { _, id in
                            if let id, id != engine.current { DispatchQueue.main.async { engine.pick(id) } }
                        }
                        .onChange(of: engine.current) { _, id in
                            if selection != id { DispatchQueue.main.async { selection = id } }
                        }
                        .onAppear { selection = engine.current }
                    } else {
                        Spacer()
                    }
                }
                .frame(minWidth: 300)
                Divider()
                SidePane()
                    .frame(width: 290)
            }
        }
        .frame(minWidth: 980, minHeight: 560)
    }

    private var partTitle: String {
        guard let p = engine.parts.first(where: { $0.row == engine.selectedPart }) else { return "patches" }
        return "patch for part \(p.row + 1)"
    }
}

// ---- THE PARTS ----

private let noteNames = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
func noteName(_ n: Int32) -> String { "\(noteNames[Int(n) % 12])\(Int(n) / 12 - 1)" }

struct PartsPane: View {
    @EnvironmentObject var engine: Engine

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Parts").font(.headline)
                Spacer()
                Button("Layer") { engine.layer(engine.selectedPart) }
                    .help("a copy of this part over the same keys")
                Button("Split") { engine.split(engine.selectedPart) }
                    .help("this part's keys halved into two parts")
                Button("Remove") { engine.delete(engine.selectedPart) }
                    .disabled(engine.parts.count < 2)
            }
            .padding(8)
            ScrollView {
                VStack(spacing: 4) {
                    ForEach(engine.parts) { p in
                        PartRowView(part: p, selected: p.row == engine.selectedPart)
                            .contentShape(Rectangle())
                            .onTapGesture { engine.selectedPart = p.row; engine.refreshParts() }
                    }
                }
                .padding(.horizontal, 8)
            }
            Divider()
            if let p = engine.parts.first(where: { $0.row == engine.selectedPart }) {
                PartEditor(part: p).padding(8)
            }
        }
    }
}

struct PartRowView: View {
    let part: PartRow
    let selected: Bool

    var body: some View {
        HStack(spacing: 8) {
            Text("\(part.row + 1)").font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 16)
            VStack(alignment: .leading, spacing: 1) {
                Text(part.name).lineLimit(1)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if part.muted { Text("M").font(.caption.bold()).foregroundStyle(.orange) }
            if part.solo == 1 { Text("S").font(.caption.bold()).foregroundStyle(.yellow) }
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: 6).fill(selected ? Color.accentColor.opacity(0.25) : Color.clear))
        .opacity(part.solo == 2 || part.muted ? 0.5 : 1)
    }

    private var detail: String {
        var s = part.channel < 0 ? "all channels" : "ch \(part.channel + 1)"
        s += "  \(noteName(part.lo))–\(noteName(part.hi))"
        if part.transpose != 0 { s += String(format: "  %+d", part.transpose) }
        if part.levelDB != 0 { s += String(format: "  %+.1f dB", part.levelDB) }
        return s
    }
}

struct PartEditor: View {
    @EnvironmentObject var engine: Engine
    let part: PartRow

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
            GridRow {
                Text("Channel")
                Picker("", selection: Binding(get: { part.channel }, set: { engine.setPart(part, channel: $0) })) {
                    Text("All").tag(Int32(-1))
                    ForEach(0..<16, id: \.self) { c in Text("\(c + 1)").tag(Int32(c)) }
                }
                .labelsHidden()
                .frame(width: 90)
            }
            GridRow {
                Text("Keys")
                HStack {
                    Stepper(noteName(part.lo), value: Binding(get: { Int(part.lo) },
                                                              set: { engine.setPart(part, lo: Int32(min($0, Int(part.hi)))) }),
                            in: 0...127)
                    Text("to")
                    Stepper(noteName(part.hi), value: Binding(get: { Int(part.hi) },
                                                              set: { engine.setPart(part, hi: Int32(max($0, Int(part.lo)))) }),
                            in: 0...127)
                }
            }
            GridRow {
                Text("Transpose")
                Stepper(String(format: "%+d", part.transpose),
                        value: Binding(get: { Int(part.transpose) }, set: { engine.setPart(part, transpose: Int32($0)) }),
                        in: -48...48)
            }
            GridRow {
                Text("Level")
                HStack {
                    Slider(value: Binding(get: { part.levelDB }, set: { engine.setPart(part, levelDB: ($0 * 2).rounded() / 2) }),
                           in: -40...12)
                    Text(String(format: "%+.1f dB", part.levelDB)).monospacedDigit().frame(width: 64, alignment: .trailing)
                }
            }
            GridRow {
                Text("")
                HStack {
                    Toggle("Mute", isOn: Binding(get: { part.muted }, set: { engine.setPart(part, muted: $0) }))
                    Button(part.solo == 1 ? "Unsolo" : "Solo") { engine.solo(part.row) }
                }
            }
        }
    }
}

// ---- PRESETS, INPUTS, OUTPUT ----

struct SidePane: View {
    @EnvironmentObject var engine: Engine
    @EnvironmentObject var midi: MidiIn
    @State private var newName = ""
    @State private var chosen: String? = nil

    var body: some View {
        Form {
            Section("Presets") {
                List(engine.presets, id: \.self, selection: $chosen) { name in
                    Text(name).tag(name)
                }
                .frame(minHeight: 120)
                HStack {
                    Button("Load") { if let c = chosen { engine.loadPreset(c) } }
                        .disabled(chosen == nil)
                    Spacer()
                }
                HStack {
                    TextField("Save as", text: $newName)
                    Button("Save") { engine.savePreset(newName); chosen = newName; newName = "" }
                        .disabled(newName.isEmpty)
                }
            }
            Section("MIDI inputs") {
                if midi.sources.isEmpty {
                    Text("none plugged in").foregroundStyle(.secondary)
                }
                ForEach(midi.sources) { s in
                    Toggle(s.name, isOn: Binding(get: { midi.on.contains(s.name) }, set: { _ in midi.toggle(s) }))
                }
            }
            Section("Output") {
                Slider(value: $engine.masterDB, in: -40...6) { Text("Master") }
                Text(String(format: "%+.1f dB", engine.masterDB)).monospacedDigit().foregroundStyle(.secondary)
                Picker("Buffer", selection: $engine.bufferFrames) {
                    ForEach([64, 128, 256, 512], id: \.self) { n in Text("\(n) frames").tag(n) }
                }
                Text(String(format: "output latency %.1f ms", engine.latencyMS)).foregroundStyle(.secondary)
                Toggle("GPU (Metal)", isOn: $engine.gpu)
            }
        }
        .formStyle(.grouped)
    }
}

// the header: what plays, the last message, the meters and the load --
// redrawn with the meters alone
struct Header: View {
    let status: String
    let message: String
    @ObservedObject var meters: Meters
    let panic: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Text(status).font(.headline)
            if !meters.building.isEmpty {
                Text(meters.building).foregroundStyle(.secondary)
            } else if !message.isEmpty {
                Text(message).foregroundStyle(.secondary)
            }
            Spacer()
            Meter(level: meters.peakL)
            Meter(level: meters.peakR)
            Text(String(format: "%3.0f%%", meters.load * 100))
                .monospacedDigit()
                .foregroundStyle(meters.load > 0.8 ? .red : .secondary)
                .help("the block's mean time over its budget")
            Button("Panic", action: panic)
                .keyboardShortcut(".", modifiers: .command)
        }
        .padding(10)
    }
}

struct Meter: View {
    let level: Float
    var body: some View {
        GeometryReader { g in
            let f = CGFloat(min(1, max(0, (20 * log10(max(level, 1e-5)) + 60) / 60)))
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 2).fill(.quaternary)
                RoundedRectangle(cornerRadius: 2).fill(level > 0.9 ? .red : .green).frame(width: g.size.width * f)
            }
        }
        .frame(width: 90, height: 8)
    }
}
