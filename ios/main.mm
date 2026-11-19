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
    // ...supported: landscape alone (SDL's controller; iPadOS turns it so at
    // launch, and between its two landscapes) -- with sizes logged once the
    // window is up (the scene's, the window's, the view's: a mismatch shows)
    if (Class vc = NSClassFromString(@"SDL_uikitviewcontroller"))
        class_replaceMethod(vc, @selector(supportedInterfaceOrientations),
                            imp_implementationWithBlock(^NSUInteger(id) { return UIInterfaceOrientationMaskLandscape; }),
                            "Q@:");
    [[NSNotificationCenter defaultCenter]
        addObserverForName:UIWindowDidBecomeKeyNotification object:nil queue:[NSOperationQueue mainQueue]
                usingBlock:^(NSNotification *n) {
                    UIWindow *w = (UIWindow *)n.object;
                    for (double t : {0.5, 2.5})
                        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(t * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                            UIWindowScene *sc = w.windowScene;
                            fprintf(stderr, "clavitone: at %.1f s scene %d %.0fx%.0f, window %.0fx%.0f, view %.0fx%.0f, screen %.0fx%.0f\n",
                                    t, (int)sc.effectiveGeometry.interfaceOrientation,
                                    sc.effectiveGeometry.coordinateSpace.bounds.size.width,
                                    sc.effectiveGeometry.coordinateSpace.bounds.size.height, w.bounds.size.width,
                                    w.bounds.size.height, w.rootViewController.view.bounds.size.width,
                                    w.rootViewController.view.bounds.size.height, sc.screen.bounds.size.width,
                                    sc.screen.bounds.size.height);
                        });
                }];
                    UIViewController *rc = w.rootViewController;
                    [rc setNeedsUpdateOfSupportedInterfaceOrientations];
                    // (the lock once the turn is made: asked again after it)
                    for (double t : {0.3, 1.0, 2.5})
                        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(t * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                            [rc setNeedsUpdateOfPrefersInterfaceOrientationLocked];
                            fprintf(stderr, "clavitone: at %.1f s orientation %d, locked %d, %.0fx%.0f\n", t,
                                    (int)sc.effectiveGeometry.interfaceOrientation,
                                    (int)sc.effectiveGeometry.isInterfaceOrientationLocked,
                                    sc.effectiveGeometry.coordinateSpace.bounds.size.width,
                                    sc.effectiveGeometry.coordinateSpace.bounds.size.height);
                        });
                }];
    audio_session();
    NSString *docs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    const std::string d = docs.UTF8String;
    // THE LOG: the engine's stderr (its start, its notes, the counts it prints
    // at QUIT) into Documents/nvlive.log, the last run's beside it -- read
    // back by devicectl, the cable free for a keyboard meanwhile
    {
        const std::string lg = d + "/nvlive.log";
        rename(lg.c_str(), (d + "/nvlive.prev.log").c_str());
        if (FILE *f = freopen(lg.c_str(), "w", stderr))
            setvbuf(f, nullptr, _IOLBF, 0);
    }
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
