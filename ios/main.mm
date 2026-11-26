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
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <objc/runtime.h>
#include <mach/mach.h>
#include <os/proc.h>
#include <mutex>
#include <thread>

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <string>
#include <vector>

int nvlive_main(int argc, char **argv);         // (nvlive.cpp's main, renamed: C++ linkage)
extern "C" void nv_ui_files_dirs(const char *music, const char *tmp);

// THE FILES PICKER (the Files card's FILES..., nui's hooks): iOS's document
// picker for MIDI and audio files -- iCloud Drive, On My iPad, a USB drive --
// opened IN PLACE: a file already in the app's own Documents (its MIDI, its
// Renders) is used where it is; one from outside is copied into Documents/MIDI
// (the picker's access ends with its sandbox), a different file of the same
// name there given a new one ("song 2.mid") rather than replacing it. The last
// one's path left for the card to take, the UI woken
static std::mutex g_pick_mu;
static std::string g_picked;
@interface ClavitonePicker : NSObject <UIDocumentPickerDelegate>
@end
@implementation ClavitonePicker
- (void)documentPicker:(UIDocumentPickerViewController *)c didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls
{
    NSString *docs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSString *dir = [docs stringByAppendingPathComponent:@"MIDI"];
    NSFileManager *fm = [NSFileManager defaultManager];
    [fm createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:nil];
    std::string last;
    NSString *home = [[NSURL fileURLWithPath:docs] URLByResolvingSymlinksInPath].path;
    for (NSURL *u in urls) {
        NSString *src = [u URLByResolvingSymlinksInPath].path;
        if ([src hasPrefix:[home stringByAppendingString:@"/"]]) {     // (the app's own: used where it is)
            last = src.UTF8String;
            continue;
        }
        const BOOL scoped = [u startAccessingSecurityScopedResource];
        NSString *name = u.lastPathComponent, *to = [dir stringByAppendingPathComponent:name];
        // (a different file of that name already here: a new name, never replaced)
        for (int k = 2; [fm fileExistsAtPath:to] && ![fm contentsEqualAtPath:to andPath:src] && k < 1000; k++)
            to = [dir stringByAppendingPathComponent:[NSString stringWithFormat:@"%@ %d.%@",
                                                     name.stringByDeletingPathExtension, k, name.pathExtension]];
        NSError *e = nil;
        if ([fm fileExistsAtPath:to])                                // (the same file: already copied)
            last = to.UTF8String;
        else if ([fm copyItemAtURL:u toURL:[NSURL fileURLWithPath:to] error:&e])
            last = to.UTF8String;
        else
            fprintf(stderr, "clavitone: could not copy %s: %s\n", name.UTF8String, e.localizedDescription.UTF8String);
        if (scoped)
            [u stopAccessingSecurityScopedResource];
    }
    if (!last.empty()) {
        fprintf(stderr, "clavitone: picked %s\n", last.c_str());
        std::lock_guard<std::mutex> lk(g_pick_mu);
        g_picked = last;
    }
    SDL_Event ev{};
    ev.type = SDL_EVENT_USER;               // (the UI waits on events: woken to take it)
    SDL_PushEvent(&ev);
}
@end
static ClavitonePicker *g_picker = nil;
extern "C" int nui_pick_available(void) { return 1; }
extern "C" void nui_pick_midi(void)
{
    dispatch_async(dispatch_get_main_queue(), ^{
        NSMutableArray<UTType *> *types = [NSMutableArray array];
        for (NSString *x in @[ @"mid", @"midi", @"kar", @"smf", @"mp3", @"wav", @"flac" ])     // (audio too: the player's)
            if (UTType *t = [UTType typeWithFilenameExtension:x])
                [types addObject:t];
        UIDocumentPickerViewController *dp = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:types
                                                                                                         asCopy:NO];
        if (!g_picker)
            g_picker = [ClavitonePicker new];
        dp.delegate = g_picker;
        dp.allowsMultipleSelection = YES;
        UIViewController *top = nil;
        for (UIScene *sc in UIApplication.sharedApplication.connectedScenes)
            if ([sc isKindOfClass:[UIWindowScene class]])
                for (UIWindow *w in ((UIWindowScene *)sc).windows)
                    if (w.isKeyWindow)
                        top = w.rootViewController;
        while (top.presentedViewController)
            top = top.presentedViewController;
        [top presentViewController:dp animated:YES completion:nil];
    });
}
extern "C" int nui_pick_take(char *path, int cap)
{
    std::lock_guard<std::mutex> lk(g_pick_mu);
    if (g_picked.empty() || cap <= 0)
        return 0;
    snprintf(path, (size_t)cap, "%s", g_picked.c_str());
    g_picked.clear();
    return 1;
}

// THE AUDIO ROUTE as iOS has it: its rate, its buffer, its latency, each
// output (a USB adapter's own rate shows here) -- at the start, and at each change
static void audio_route(const char *why)
{
    AVAudioSession *s = [AVAudioSession sharedInstance];
    fprintf(stderr, "clavitone: audio %s: %.0f Hz, buffer %.2f ms, output latency %.2f ms\n", why, s.sampleRate,
            s.IOBufferDuration * 1000.0, s.outputLatency * 1000.0);
    for (AVAudioSessionPortDescription *p in s.currentRoute.outputs)
        fprintf(stderr, "clavitone:   out %s (%s)\n", p.portName.UTF8String, p.portType.UTF8String);
}

// MEMORY as iOS counts it (Part C's measure): the footprint (task_vm_info's
// phys_footprint -- what iOS kills by), the most it has been, and what the
// system says is left to this process before its limit -- every 5 s
static void memory_watch()
{
    std::thread([] {
        unsigned long long peak = 0;
        for (;;) {
            task_vm_info_data_t vi{};
            mach_msg_type_number_t n = TASK_VM_INFO_COUNT;
            if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&vi, &n) == KERN_SUCCESS) {
                peak = std::max(peak, (unsigned long long)vi.phys_footprint);
                fprintf(stderr, "clavitone: memory %.0f MB (peak %.0f MB), %.0f MB left before iOS's limit\n",
                        vi.phys_footprint / 1048576.0, peak / 1048576.0, os_proc_available_memory() / 1048576.0);
            }
            std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }).detach();
}

static void audio_session()
{
    AVAudioSession *s = [AVAudioSession sharedInstance];
    NSError *e = nil;
    [s setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault options:0 error:&e];
    [s setPreferredSampleRate:48000.0 error:&e];
    [s setPreferredIOBufferDuration:256.0 / 48000.0 error:&e];      // (rubato's callback: 256 frames)
    if (![s setActive:YES error:&e])
        NSLog(@"clavitone: the audio session would not start: %@", e);
    [[NSNotificationCenter defaultCenter] addObserverForName:AVAudioSessionRouteChangeNotification object:nil
                                                       queue:nil
                                                  usingBlock:^(NSNotification *n) {
                                                      const int why = [n.userInfo[AVAudioSessionRouteChangeReasonKey] intValue];
                                                      char b[48];
                                                      snprintf(b, sizeof b, "route changed (reason %d)", why);
                                                      audio_route(b);
                                                  }];
}

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    // LANDSCAPE ONLY: SDL lets a resizable window turn every way unless told
    // (its hint, over the Info.plist's iPad orientations)
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    // ...supported: landscape alone (SDL's controller; iPadOS turns it so at
    // launch, and between its two landscapes) -- with sizes logged once the
    // window is up (the scene's, the window's, the view's: a mismatch shows)
    // ...AND HELD in the landscape it opened in (Ben): iPadOS 26's lock
    // (prefersInterfaceOrientationLocked) preferred only once the scene is
    // landscape -- asked for again after the window is up, when iOS has turned it
    if (Class vc = NSClassFromString(@"SDL_uikitviewcontroller")) {
        class_replaceMethod(vc, @selector(supportedInterfaceOrientations),
                            imp_implementationWithBlock(^NSUInteger(id) { return UIInterfaceOrientationMaskLandscape; }),
                            "Q@:");
        class_replaceMethod(vc, @selector(prefersInterfaceOrientationLocked),
                            imp_implementationWithBlock(^BOOL(id me) {
                                UIWindowScene *sc = ((UIViewController *)me).view.window.windowScene;
                                return sc && UIInterfaceOrientationIsLandscape(sc.effectiveGeometry.interfaceOrientation);
                            }),
                            "B@:");
    }
    [[NSNotificationCenter defaultCenter]
        addObserverForName:UIWindowDidBecomeKeyNotification object:nil queue:[NSOperationQueue mainQueue]
                usingBlock:^(NSNotification *n) {
                    UIWindow *w = (UIWindow *)n.object;
                    for (double t : {0.4, 1.2})
                        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(t * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                            [w.rootViewController setNeedsUpdateOfPrefersInterfaceOrientationLocked];
                        });
                    for (double t : {0.5, 2.5})
                        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(t * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                            UIWindowScene *sc = w.windowScene;
                            fprintf(stderr, "clavitone: at %.1f s scene %d (locked %d) %.0fx%.0f, window %.0fx%.0f, view %.0fx%.0f, screen %.0fx%.0f\n",
                                    t, (int)sc.effectiveGeometry.interfaceOrientation,
                                    (int)sc.effectiveGeometry.isInterfaceOrientationLocked,
                                    sc.effectiveGeometry.coordinateSpace.bounds.size.width,
                                    sc.effectiveGeometry.coordinateSpace.bounds.size.height, w.bounds.size.width,
                                    w.bounds.size.height, w.rootViewController.view.bounds.size.width,
                                    w.rootViewController.view.bounds.size.height, sc.screen.bounds.size.width,
                                    sc.screen.bounds.size.height);
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
    audio_route("at the start");
    memory_watch();
    setenv("NV_PATCH_SIZES", "1", 1);               // (each patch built: its size, in the log)
    // (the Files card's MUSIC: Documents, which the Files app shows -- the
    //  picked files' MIDI folder and the renders inside it)
    nv_ui_files_dirs(d.c_str(), NSTemporaryDirectory().UTF8String);
    const std::string nvx = d + "/live.nvx";
    if (access(nvx.c_str(), R_OK) != 0) {
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Clavitone",
                                 "No sound data yet: put live.nvx in Clavitone's Documents (Finder, or devicectl).", nullptr);
        return 1;
    }
    // THE PATCHES' BUDGET from what iOS leaves this process (Part C): half of
    // it at the start -- the engine and its export mapped beside them, a
    // render's room -- 1.5 GB of an 11-inch iPad's 3 GB; a patch over it is
    // built from the middle octaves out, its other notes as they are played
    const long long left = (long long)os_proc_available_memory();
    const long budget_mb = left > 0 ? (long)(left / 2 / 1048576) : 0;
    fprintf(stderr, "clavitone: %.0f MB left by iOS: the patches' budget %ld MB\n", left / 1048576.0, budget_mb);
    std::vector<std::string> a = {"nvlive", nvx, "--app", "--session=" + d + "/session.json"};
    if (budget_mb > 0)
        a.push_back("--patch-budget-mb=" + std::to_string(budget_mb));
    // (the GPU from the first partial: an iPad's CPU is far weaker beside its
    //  GPU than a laptop's, where 100 busy slots was the threshold -- Mars
    //  had the governor shedding partials)
    a.push_back("--gpu-min=1");
    std::vector<char *> av;
    for (auto &s : a)
        av.push_back(&s[0]);
    av.push_back(nullptr);
    return nvlive_main((int)a.size(), av.data());
}
