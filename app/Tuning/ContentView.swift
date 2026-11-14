// The window: what is playing and how hard the engine works, the patches
// (searchable: every program, variation and drum set the export has), the
// MIDI inputs, the master level, the GPU, panic.
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
            Header(status: engine.status, meters: engine.meters, panic: engine.panic)
            Divider()
            HStack(spacing: 0) {
                VStack(spacing: 0) {
                    TextField("Search patches", text: $query)
                        .textFieldStyle(.roundedBorder)
                        .padding(8)
                    // (the list's own selection; the pick after it has settled -- a
                    // pick inside the list's update was a reentrant table update)
                    // (built once the engine has its patches: a table filled
                    // during its first layout warned of a reentrant update)
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
                .frame(minWidth: 320)
                Divider()
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
                        Slider(value: $engine.masterDB, in: -40...6) {
                            Text("Master")
                        }
                        Text(String(format: "%+.1f dB", engine.masterDB)).monospacedDigit().foregroundStyle(.secondary)
                        Toggle("GPU (Metal)", isOn: $engine.gpu)
                    }
                }
                .formStyle(.grouped)
                .frame(width: 300)
            }
        }
        .frame(minWidth: 680, minHeight: 440)
    }
}

// the header: what plays, the meters and the load -- redrawn with the meters alone
struct Header: View {
    let status: String
    @ObservedObject var meters: Meters
    let panic: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Text(status).font(.headline)
            if !meters.building.isEmpty {
                Text(meters.building).foregroundStyle(.secondary)
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
