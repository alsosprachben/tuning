import SwiftUI

@main
struct TuningApp: App {
    @StateObject private var engine = Engine()
    @StateObject private var midi = MidiIn()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(engine)
                .environmentObject(midi)
                .onAppear {
                    engine.start()
                    midi.onMessage = { [weak engine] bytes, stamp in engine?.midi(bytes, at: stamp) }
                    midi.start()
                }
        }
        .defaultSize(width: 760, height: 560)
    }
}
