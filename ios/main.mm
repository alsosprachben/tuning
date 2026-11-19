// main.mm -- CLAVITONE ON iOS (Part C): the app shell around the same
// nvlive the Mac and Linux run. SDL3's iOS entry (SDL_main.h: UIKit's run
// loop, the window full screen) calls this; it readies the audio session
// (playback, 48 kHz, a short buffer, kept on in the background), finds the
// export and the session in the app's Documents (the export put there by
// Finder or devicectl: 1.1 GB, not in the bundle), and runs nvlive's own
// main (nvlive.cpp compiled with -Dmain=nvlive_main) in --app mode: the
// engine, CoreMIDI in, RemoteIO out (macio.h), the native UI drawn on Metal.
#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <string>
#include <vector>

int nvlive_main(int argc, char **argv);         // (nvlive.cpp's main, renamed: C++ linkage)

static void audio_session()
{
    AVAudioSession *s = [AVAudioSession sharedInstance];
    NSError *e = nil;
    [s setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault options:0 error:&e];
    [s setPreferredSampleRate:48000.0 error:&e];
    [s setPreferredIOBufferDuration:256.0 / 48000.0 error:&e];      // (rubato's callback: 256 frames)
    if (![s setActive:YES error:&e])
        NSLog(@"clavitone: the audio session would not start: %@", e);
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    // LANDSCAPE ONLY: SDL lets a resizable window turn every way unless told
    // (its hint, over the Info.plist's iPad orientations) -- and iPadOS 26,
    // its every app's window resizable, keeps an orientation only for a view
    // controller that prefers it locked (prefersInterfaceOrientationLocked,
    // new in 26: SDL's controller is given it here, before its window is made)
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    if (Class vc = NSClassFromString(@"SDL_uikitviewcontroller")) {
        class_replaceMethod(vc, @selector(prefersInterfaceOrientationLocked),
                            imp_implementationWithBlock(^BOOL(id) { return YES; }), "B@:");
        class_replaceMethod(vc, @selector(supportedInterfaceOrientations),
                            imp_implementationWithBlock(^NSUInteger(id) { return UIInterfaceOrientationMaskLandscape; }),
                            "Q@:");
    }
    audio_session();
    NSString *docs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    const std::string d = docs.UTF8String;
    const std::string nvx = d + "/live.nvx";
    if (access(nvx.c_str(), R_OK) != 0) {
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Clavitone",
                                 "No sound data yet: put live.nvx in Clavitone's Documents (Finder, or devicectl).", nullptr);
        return 1;
    }
    std::vector<std::string> a = {"nvlive", nvx, "--app", "--session=" + d + "/session.json"};
    std::vector<char *> av;
    for (auto &s : a)
        av.push_back(&s[0]);
    av.push_back(nullptr);
    return nvlive_main((int)a.size(), av.data());
}
