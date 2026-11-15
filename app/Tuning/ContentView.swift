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
                    .frame(width: 370)
            }
        }
        .frame(minWidth: 1010, minHeight: 560)
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
            if !engine.stopNames.isEmpty {
                Divider()
                StopsPane().padding(8)
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

// ---- AN ORGAN's STOPS (the first part's: livetui's stop rows) ----

struct StopsPane: View {
    @EnvironmentObject var engine: Engine

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Stops").font(.headline)
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(engine.stopRows.enumerated()), id: \.offset) { _, row in
                        // a row's groups, each its stops side by side
                        FlowRow(groups: row)
                    }
                }
            }
            .frame(maxHeight: 220)
        }
    }
}

struct FlowRow: View {
    @EnvironmentObject var engine: Engine
    let groups: [[Int]]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, g in
                HStack(spacing: 4) {
                    ForEach(g, id: \.self) { r in
                        let on = r < engine.drawn.count && engine.drawn[r]
                        Button(action: { engine.toggleStop(r) }) {
                            Text(r < engine.stopNames.count ? engine.stopNames[r] : "\(r)")
                                .font(.caption)
                                .lineLimit(1)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(RoundedRectangle(cornerRadius: 4)
                                    .fill(on ? Color.accentColor.opacity(0.85) : Color.gray.opacity(0.18)))
                                .foregroundStyle(on ? Color.white : Color.primary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

// ---- PRESETS, INPUTS, OUTPUT ----

struct SidePane: View {
    @State private var tab = 0

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                Text("Presets").tag(0)
                Text("Tuning").tag(1)
                Text("Effects").tag(3)
                Text("Synth").tag(4)
                Text("Setup").tag(2)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(8)
            switch tab {
            case 0: PresetsPane()
            case 1: TuningPane()
            case 3: EffectsPane()
            case 4: SynthPane()
            default: SetupPane()
            }
        }
    }
}

struct PresetsPane: View {
    @EnvironmentObject var engine: Engine
    @State private var newName = ""
    @State private var chosen: String? = nil

    var body: some View {
        Form {
            Section("Presets") {
                List(engine.presets, id: \.self, selection: $chosen) { name in
                    Text(name).tag(name)
                }
                .frame(minHeight: 180)
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
        }
        .formStyle(.grouped)
    }
}

// ---- TUNING: the rig's tuner, and the Eastern tuning for Indian voices ----

private let saKeys = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]

struct TuningPane: View {
    @EnvironmentObject var engine: Engine

    // the Eastern spec "raga:<system>[/<raga>]@<sa>" taken apart and put back
    private var parts: (system: String, raga: String, sa: String) {
        guard engine.eastern.hasPrefix("raga:") else { return ("", "", "c#") }
        var b = String(engine.eastern.dropFirst(5)), sa = "c#"
        if let at = b.firstIndex(of: "@") {
            sa = String(b[b.index(after: at)...]).split(separator: ":").first.map(String.init) ?? "c#"
            b = String(b[..<at])
        }
        let sr = b.split(separator: "/", maxSplits: 1).map(String.init)
        return (sr.first ?? "", sr.count > 1 ? sr[1] : "", sa)
    }

    private func spec(system: String, raga: String, sa: String) -> String {
        system.isEmpty ? "" : "raga:\(system)\(raga.isEmpty ? "" : "/" + raga)@\(sa)"
    }

    var body: some View {
        Form {
            Section("Tuner") {
                Picker("Tuner", selection: Binding(get: { engine.tuner }, set: { engine.setTuner($0) })) {
                    ForEach(engine.tuners, id: \.name) { t in Text(t.name).tag(t.name) }
                }
                if let t = engine.tuners.first(where: { $0.name == engine.tuner }) {
                    Text(t.note).font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("Eastern tuning (Indian voices)") {
                let p = parts
                Picker("System", selection: Binding(get: { p.system },
                                                    set: { engine.setEastern(spec(system: $0, raga: p.raga, sa: p.sa)) })) {
                    Text("off").tag("")
                    ForEach(engine.ragaSystems, id: \.self) { Text($0).tag($0) }
                }
                if !p.system.isEmpty {
                    Picker("Raga", selection: Binding(get: { p.raga },
                                                      set: { engine.setEastern(spec(system: p.system, raga: $0, sa: p.sa)) })) {
                        Text("none").tag("")
                        ForEach(engine.ragas, id: \.self) { Text($0).tag($0) }
                    }
                    Picker("Sa", selection: Binding(get: { p.sa },
                                                    set: { engine.setEastern(spec(system: p.system, raga: p.raga, sa: $0)) })) {
                        ForEach(saKeys, id: \.self) { Text($0.uppercased()).tag($0) }
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}

// ---- THE EFFECTS: the insertion effect (the Sound Canvas's EFX), the system effects ----

private let reverbNames = ["Room 1", "Room 2", "Room 3", "Hall 1", "Hall 2", "Plate", "Delay", "Panning Delay"]
private let chorusNames = ["Chorus 1", "Chorus 2", "Chorus 3", "Chorus 4", "Feedback Chorus", "Flanger",
                           "Short Delay", "Short Delay (FB)"]
private let delayNames = ["Delay 1", "Delay 2", "Delay 3", "Delay 4", "Pan Delay 1", "Pan Delay 2", "Pan Delay 3",
                          "Pan Delay 4", "Delay to Reverb", "Pan Repeat"]

struct EffectsPane: View {
    @EnvironmentObject var engine: Engine

    private func ival(_ v: Binding<Int>, _ lo: Int, _ hi: Int, _ label: String) -> some View {
        HStack {
            Text(label)
            Slider(value: Binding(get: { Double(v.wrappedValue) }, set: { v.wrappedValue = Int($0.rounded()) }),
                   in: Double(lo)...Double(hi))
            Text("\(v.wrappedValue)").monospacedDigit().frame(width: 34, alignment: .trailing)
        }
    }

    var body: some View {
        let e = engine.efx
        let key = "\(e.msb).\(e.lsb)"
        let cur = engine.efxTypes.first { $0.msb == e.msb && $0.lsb == e.lsb }
        Form {
            Section("Insertion effect") {
                Toggle("Selected part on it", isOn: Binding(get: { engine.selectedOnEfx }, set: { engine.setSelectedOnEfx($0) }))
                Picker("Type", selection: Binding(get: { cur ?? EfxType(num: 0, msb: 0, lsb: 0, name: "Thru") },
                                                  set: { engine.setEfxType($0) })) {
                    Text("00 Thru").tag(EfxType(num: 0, msb: 0, lsb: 0, name: "Thru"))
                    ForEach(engine.efxFamilies, id: \.self) { fam in
                        Section(fam.name) {
                            ForEach(engine.efxTypes.filter { $0.num >= fam.first && $0.num <= fam.last }, id: \.self) { t in
                                Text(String(format: "%02d %@", t.num, t.name)).tag(t)
                            }
                        }
                    }
                }
                let why = withUnsafeBytes(of: e.why) { String(cString: $0.bindMemory(to: CChar.self).baseAddress!) }
                if !why.isEmpty { Text("not played live: \(why)").font(.caption).foregroundStyle(.orange) }
            }
            if cur != nil, let ps = engine.efxParams[key] {
                Section("\(cur!.name): parameters") {
                    ForEach(ps, id: \.self) { p in
                        let v = withUnsafeBytes(of: e.p) { $0.bindMemory(to: Int32.self)[p.n] }
                        let now = v >= 0 ? Int(v) : p.fresh
                        Picker(p.name + (p.mark == "-" ? "" : "  " + p.mark),
                               selection: Binding(get: { now }, set: { engine.setEfxParam(p.n, $0) })) {
                            ForEach(p.vals, id: \.self) { x in Text(p.label(x)).tag(x) }
                        }
                    }
                }
                Section("Sends from it") {
                    ForEach([(0x17, "to reverb"), (0x18, "to chorus"), (0x19, "to delay")], id: \.0) { a, nm in
                        let sv = withUnsafeBytes(of: e.send) { Int($0.bindMemory(to: Int32.self)[a - 0x17]) }
                        ival(Binding(get: { sv }, set: { engine.setEfxAddress(a, $0) }), 0, 127, nm)
                    }
                }
            }
            let x = engine.sysfx
            Section("Reverb (CC91)") {
                Picker("Type", selection: Binding(get: { Int(x.rev_macro < 0 ? 4 : x.rev_macro) }, set: { engine.setSysfx(1, 0x30, $0) })) {
                    ForEach(0..<8, id: \.self) { Text(reverbNames[$0]).tag($0) }
                }
                if x.rev_macro < 0 {
                    let room = withUnsafeBytes(of: x.room) { String(cString: $0.bindMemory(to: CChar.self).baseAddress!) }
                    Text("the panel's room: \(room)").font(.caption).foregroundStyle(.secondary)
                }
                ival(Binding(get: { Int(x.rev_level) }, set: { engine.setSysfx(1, 0x33, $0) }), 0, 127, "Level")
                ival(Binding(get: { Int(x.rev_time) }, set: { engine.setSysfx(1, 0x34, $0) }), 0, 127, "Time")
                if x.rev_fb >= 0 {
                    ival(Binding(get: { Int(x.rev_fb) }, set: { engine.setSysfx(1, 0x35, $0) }), 0, 127, "Feedback")
                }
            }
            Section("Chorus (CC93)") {
                let c = withUnsafeBytes(of: x.cho) { Array($0.bindMemory(to: Int32.self)).map(Int.init) }
                Picker("Type", selection: Binding(get: { c[0] }, set: { engine.setSysfx(1, 0x38, $0) })) {
                    ForEach(0..<8, id: \.self) { Text(chorusNames[$0]).tag($0) }
                }
                ForEach([(1, 0x39, "Pre-LPF", 7), (2, 0x3A, "Level", 127), (3, 0x3B, "Feedback", 127),
                         (4, 0x3C, "Delay", 127), (5, 0x3D, "Rate", 127), (6, 0x3E, "Depth", 127)], id: \.0) { i, a, nm, hi in
                    ival(Binding(get: { c[i] }, set: { engine.setSysfx(1, a, $0) }), 0, hi, nm)
                }
            }
            Section("Delay (CC94)") {
                let dl = withUnsafeBytes(of: x.dly) { Array($0.bindMemory(to: Int32.self)).map(Int.init) }
                Picker("Type", selection: Binding(get: { dl[0] }, set: { engine.setSysfx(1, 0x50, $0) })) {
                    ForEach(0..<10, id: \.self) { Text(delayNames[$0]).tag($0) }
                }
                ForEach([(1, 0x51, "Pre-LPF", 0, 7), (2, 0x52, "Time", 1, 0x73), (3, 0x53, "Ratio L", 1, 0x78),
                         (4, 0x54, "Ratio R", 1, 0x78), (5, 0x55, "Level C", 0, 127), (6, 0x56, "Level L", 0, 127),
                         (7, 0x57, "Level R", 0, 127), (8, 0x58, "Level", 0, 127), (9, 0x59, "Feedback", 0, 127)],
                        id: \.0) { i, a, nm, lo, hi in
                    ival(Binding(get: { dl[i] }, set: { engine.setSysfx(1, a, $0) }), lo, hi, nm)
                }
            }
            Section("EQ") {
                let q = withUnsafeBytes(of: x.eq) { Array($0.bindMemory(to: Int32.self)).map(Int.init) }
                Picker("Low", selection: Binding(get: { q[0] }, set: { engine.setSysfx(2, 0, $0) })) {
                    Text("200 Hz").tag(0); Text("400 Hz").tag(1)
                }
                ival(Binding(get: { q[1] - 0x40 }, set: { engine.setSysfx(2, 1, $0 + 0x40) }), -12, 12, "Low gain dB")
                Picker("High", selection: Binding(get: { q[2] }, set: { engine.setSysfx(2, 2, $0) })) {
                    Text("3 kHz").tag(0); Text("6 kHz").tag(1)
                }
                ival(Binding(get: { q[3] - 0x40 }, set: { engine.setSysfx(2, 3, $0 + 0x40) }), -12, 12, "High gain dB")
            }
        }
        .formStyle(.grouped)
        .onAppear { engine.refreshEfx(); engine.refreshSysfx() }
    }
}

// ---- THE GLOBALS (livetui's GLOBALS pane, the master, GPU and tail above) ----
private let standardNames = ["ours", "SC-55", "SC-88", "SC-88Pro", "SC-8850"]

struct GlobalsSection: View {
    @EnvironmentObject var engine: Engine

    private func slider(_ i: Int32, _ name: String, _ lo: Double, _ hi: Double, _ step: Double,
                        _ fmt: @escaping (Double) -> String, help: String) -> some View {
        HStack {
            Text(name).frame(width: 110, alignment: .leading)
            Slider(value: Binding(get: { engine.g[Int(i)] },
                                  set: { engine.setG(i, (($0 - lo) / step).rounded() * step + lo) }),
                   in: lo...hi)
            Text(fmt(engine.g[Int(i)])).monospacedDigit().frame(width: 74, alignment: .trailing)
        }
        .help(help)
    }

    var body: some View {
        Section("Globals") {
            slider(Int32(NV_G_HEADROOM_DB), "Headroom", 0, 24, 0.5, { String(format: "%.1f dB", $0) },
                   help: "how far under full scale the mix sits before the limiter")
            slider(Int32(NV_G_LIMITER), "Limiter", 0.1, 1, 0.02, { String(format: "%.2f", $0) },
                   help: "the limiter's knee")
            slider(Int32(NV_G_BEND_RANGE), "Bend range", 0, 24, 0.5, { String(format: "%.1f st", $0) },
                   help: "the pitch wheel's range, in semitones")
            slider(Int32(NV_G_MOD_CENTS), "Mod depth", 0, 200, 5, { String(format: "%.0f c", $0) },
                   help: "the mod wheel's vibrato depth at full")
            slider(Int32(NV_G_MOD_RATE), "Mod rate", 0, 1.5, 0.05, { String(format: "+%.0f%%", $0 * 100) },
                   help: "the mod wheel's vibrato rate, faster with the wheel")
            slider(Int32(NV_G_PRESS_DB), "Aftertouch", 0, 24, 0.5, { String(format: "%.1f dB", $0) },
                   help: "how much louder full aftertouch makes a note")
            if !engine.rooms.isEmpty {
                Picker("Room", selection: Binding(get: { Int(engine.g[Int(NV_G_ROOM)]) },
                                                  set: { engine.setG(Int32(NV_G_ROOM), Double($0)) })) {
                    ForEach(engine.rooms.indices, id: \.self) { Text(engine.rooms[$0]).tag($0) }
                }
                .help("every patch built again in it, the tail crossfaded")
            }
            Picker("Standard", selection: Binding(get: { Int(engine.g[Int(NV_G_STANDARD)].rounded()) },
                                                  set: { engine.setG(Int32(NV_G_STANDARD), Double($0)) })) {
                ForEach(standardNames.indices, id: \.self) { Text(standardNames[$0]).tag($0) }
            }
            .help("which Sound Canvas's banks program changes read")
        }
        Section("Metronome") {
            HStack {
                Toggle("On", isOn: Binding(get: { engine.g[Int(NV_G_METRONOME)] > 0 },
                                           set: { engine.setG(Int32(NV_G_METRONOME), $0 ? max(20, engine.g[Int(NV_G_METRONOME)] == 0 ? 100 : engine.g[Int(NV_G_METRONOME)]) : 0) }))
                Spacer()
            }
            if engine.g[Int(NV_G_METRONOME)] > 0 {
                slider(Int32(NV_G_METRONOME), "Tempo", 20, 300, 1, { String(format: "%.0f bpm", $0) },
                       help: "beats a minute")
            }
            slider(Int32(NV_G_METRO_RING), "Bell", 0, 16, 1, { $0 <= 0 ? "no bell" : String(format: "every %.0f", $0) },
                   help: "the bell on every n-th beat")
            slider(Int32(NV_G_METRO_DB), "Level", -40, 12, 0.5, { String(format: "%+.1f dB", $0) },
                   help: "the metronome's level")
        }
    }
}

// ---- THE SYNTH (livetui's synth pane): a Moog part's knobs, an organ's drive ----
struct SynthPane: View {
    @EnvironmentObject var engine: Engine
    @State private var said = ""

    private var part: PartRow? { engine.parts.first { $0.row == engine.selectedPart } }

    private func knobRow(_ k: SynthKnob) -> some View {
        let own = k.knob >= 0 ? engine.synthOwn[k.knob] : 0
        let v = k.knob >= 0 ? engine.synthPN[k.knob] : 0
        return HStack {
            Text(k.label).frame(width: 84, alignment: .leading)
            if !k.steps.isEmpty {
                // (short words side by side; long ones a menu of one fixed width: no row wider than the pane)
                let words = k.steps.map { label(k, $0) }
                let pick = Picker("", selection: Binding(get: { k.steps.min { abs($0 - v) < abs($1 - v) } ?? v },
                                                         set: { engine.setKnob(k, $0) })) {
                    ForEach(k.steps.indices, id: \.self) { i in Text(words[i]).tag(k.steps[i]) }
                }
                .labelsHidden()
                if words.allSatisfy({ $0.count <= 6 }) {
                    pick.pickerStyle(.segmented).frame(maxWidth: .infinity)
                } else {
                    pick.pickerStyle(.menu).frame(width: 190, alignment: .leading)
                    Spacer(minLength: 0)
                }
            } else {
                Slider(value: Binding(get: { v }, set: { engine.setKnob(k, $0) }), in: 0...1)
                    .frame(maxWidth: .infinity)
                Text(engine.synthText(k)).monospacedDigit().lineLimit(1).frame(width: 76, alignment: .trailing)
            }
            Button { engine.forgetKnob(k) } label: { Image(systemName: "arrow.uturn.backward") }
                .buttonStyle(.borderless)
                .opacity(own != 0 ? 1 : 0)
                .disabled(own == 0)
                .help("back to the patch's setting")
        }
        .foregroundStyle(own == 2 ? Color.secondary : own == 1 ? Color.orange : Color.primary)
        .frame(maxWidth: .infinity)
    }

    // a switch's position in the panel's words (the knob's own law, the panel as it stands)
    private func label(_ k: SynthKnob, _ x: Double) -> String {
        var pn = engine.synthPN
        pn[k.knob] = x
        var out = [CChar](repeating: 0, count: 64)
        nv_host_synth_fmt(k.kind, x, pn, &out, 64)
        return String(cString: out)
    }

    var body: some View {
        let sections = engine.synthKnobs.reduce(into: [String]()) { if !$0.contains($1.section) { $0.append($1.section) } }
        Form {
            if engine.synthLayers > 0 {
                Section {
                    HStack {
                        Text("Moog Messenger").font(.headline).lineLimit(1)
                        Text(part.map { "part \($0.row + 1), \($0.name)" } ?? "").foregroundStyle(.secondary)
                            .lineLimit(1).truncationMode(.tail)
                        Spacer()
                        if engine.synthLayers > 1 {
                            Picker("Layer", selection: Binding(get: { engine.synthLayer },
                                                               set: { engine.synthLayer = $0; engine.refreshSynth() })) {
                                Text("A").tag(Int32(0)); Text("B").tag(Int32(1))
                            }
                            .pickerStyle(.segmented)
                            .frame(width: 70)
                        }
                    }
                    Button("All knobs back to the patch") { engine.forgetAllKnobs() }
                    if engine.synthOwn.contains(2) {
                        Text("grey: the part's, not heard natively (an MF-104M under a moved pitch or shape): kept, and saved")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                ForEach(sections, id: \.self) { sec in
                    Section(sec) {
                        ForEach(engine.synthKnobs.filter { $0.section == sec }, id: \.self) { knobRow($0) }
                    }
                }
            } else if engine.drive.0 == 1 {
                Section("Organ") {
                    HStack {
                        Text("Drive").frame(width: 84, alignment: .leading)
                        Slider(value: Binding(get: { engine.drive.1 }, set: { engine.setDrive(($0 * 20).rounded() / 20) }), in: 0...3)
                        Text(String(format: "%.2f", engine.drive.1)).monospacedDigit().frame(width: 50, alignment: .trailing)
                        Button("Voice's") { engine.setDrive(-1) }
                            .help(String(format: "the voice's own: %.2f", engine.drive.2))
                    }
                    Text("the valve before the rotors").font(.caption).foregroundStyle(.secondary)
                }
            } else {
                Section {
                    Text(part?.drums == true ? "a drum part: the synth panel is for a melodic part"
                         : engine.synthLayers < 0 ? "reading the part..."
                         : "\(part.map { "part \($0.row + 1), \($0.name)" } ?? "this part") is not a Moog: the synth panel turns a Moog's knobs")
                        .foregroundStyle(.secondary)
                }
            }
            Section("Messenger") {
                Toggle("Every part reads a Messenger's knobs (its CC chart)",
                       isOn: Binding(get: { engine.messengerReads }, set: { engine.setMessengerReads($0) }))
                Picker("Firmware chart", selection: Binding(get: { engine.messengerPre107 }, set: { engine.setMessengerPre107($0) })) {
                    Text("1.0.7 and later").tag(false); Text("before 1.0.7").tag(true)
                }
                HStack {
                    let ml = engine.messengerLine
                    Text(ml == "-" ? "no Messenger to set: plug one in" : ml.isEmpty ? "no Messenger to set" : "sets the Messenger on \(ml)")
                        .foregroundStyle(.secondary)
                    Spacer()
                    if engine.synthLayers > 0 {
                        Button("Send the panel") {
                            said = engine.sendToMessenger() ? "sent" : "no Messenger plugged in"
                        }
                        if !said.isEmpty { Text(said).font(.caption).foregroundStyle(.secondary) }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { engine.synthShown = true; engine.refreshSynth() }
        .onDisappear { engine.synthShown = false }
        .onChange(of: engine.selectedPart) { _, _ in engine.synthLayer = 0; engine.synthLayers = -1; engine.refreshSynth() }
        .onChange(of: engine.parts) { _, _ in engine.refreshSynth() }
    }
}

struct SetupPane: View {
    @EnvironmentObject var engine: Engine
    @EnvironmentObject var midi: MidiIn

    var body: some View {
        Form {
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
                Toggle("Room tail", isOn: $engine.roomTail)
            }
            GlobalsSection()
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
            Text(status).font(.headline).lineLimit(1).fixedSize()
            // (one line, cut short, taking what room is left: a message's length never moves the layout)
            Text(!meters.building.isEmpty ? meters.building : message)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .frame(maxWidth: .infinity, alignment: .leading)
                .layoutPriority(-1)
            Meter(level: meters.peakL)
            Meter(level: meters.peakR)
            // (fixed widths, right-aligned: the figures changing never move the meters)
            Text(String(format: "%3.0f%%", meters.load * 100))
                .monospacedDigit()
                .frame(width: 44, alignment: .trailing)
                .foregroundStyle(meters.load > 0.8 ? .red : .secondary)
                .help("the block's mean time over its budget")
            Text(String(format: "slowest %5.1f ms  over %5lld", meters.slowestMS, meters.over))
                .monospacedDigit()
                .frame(width: 190, alignment: .trailing)
                .foregroundStyle(meters.over > 0 ? .orange : .secondary)
                .help("the slowest block in the last second, and how many blocks have run past their budget (2.67 ms each) since the start")
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
