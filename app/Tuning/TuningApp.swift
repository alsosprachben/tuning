import AppKit
import SwiftUI

// the engine and MIDI started at launch (not on a window's appearing: a
// window restored away, or a second launch, left the engine unopened), and
// the app quit with its window, so no copy lingers holding the audio device
final class AppDelegate: NSObject, NSApplicationDelegate {
    let engine = Engine()
    let midi = MidiIn()

    func applicationDidFinishLaunching(_ notification: Notification) {
        engine.start()
        midi.onMessage = { [weak engine] bytes, stamp in engine?.midi(bytes, at: stamp) }
        midi.onMessenger = { [weak engine] on in engine?.messengerPlugged(on) }
        midi.start()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main
struct TuningApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var app

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(app.engine)
                .environmentObject(app.midi)
        }
        .defaultSize(width: 1080, height: 640)
    }
}
