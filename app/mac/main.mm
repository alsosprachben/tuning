// THE MAC APP's ENTRY (Clavitone.app's own executable, app/bundle.py): the
// native interface -- nvlive --app-windowed, linked in (nvlive.cpp built with
// its main renamed, native.py build_mac_app) -- with the Mac's places:
//   the sound data    the bundle's Resources (live.nvx; file.nvx for best
//                     quality), else ~/nvx (a build run from the repo)
//   the session       ~/Library/Application Support/Clavitone/session.json
//                     (the player's presets beside it, as nvlive keeps them)
//   the log           ~/Library/Logs/Clavitone/nvlive.log, the last run's
//                     beside it (nvlive.prev.log)
//   the Files card    ~/Music (its renders folder: nvlive's ~/Music/renders)
// and the Files card's FILES...: the Mac's own open panel (nui's hooks),
// MIDI and audio files used where they are. Arguments given to the app are
// passed on to nvlive after these (a test's --device=null, --midi=...).
#import <AppKit/AppKit.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

#include <mutex>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

int nvlive_main(int argc, char **argv);         // (nvlive.cpp's main, renamed: C++ linkage)
extern "C" void nv_ui_files_dirs(const char *music, const char *tmp);

// THE FILES PICKER (nui's hooks, as iOS's): the open panel, modal on the
// interface's own thread (the main one); the file's path left for the card
static std::mutex g_pick_mu;
static std::string g_picked;
extern "C" int nui_pick_available(void) { return 1; }
extern "C" void nui_pick_midi(void)
{
    @autoreleasepool {
        NSOpenPanel *p = [NSOpenPanel openPanel];
        p.canChooseFiles = YES;
        p.canChooseDirectories = NO;
        p.allowsMultipleSelection = NO;
        NSMutableArray<UTType *> *types = [NSMutableArray array];
        for (NSString *x in @[ @"mid", @"midi", @"kar", @"smf", @"mp3", @"wav", @"flac" ])
            if (UTType *t = [UTType typeWithFilenameExtension:x])
                [types addObject:t];
        p.allowedContentTypes = types;
        p.message = @"A MIDI file to play or render, or an audio file to play";
        if ([p runModal] == NSModalResponseOK && p.URL) {
            std::lock_guard<std::mutex> lk(g_pick_mu);
            g_picked = p.URL.path.UTF8String;
        }
    }
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

static bool exists(const std::string &p) { return access(p.c_str(), R_OK) == 0; }

int main(int argc, char *argv[])
{
    @autoreleasepool {
        const std::string home = NSHomeDirectory().UTF8String;
        const std::string res = NSBundle.mainBundle.resourcePath.UTF8String;
        // (the data: the bundle's, else the repo build's ~/nvx)
        std::string nvx = res + "/live.nvx", fx = res + "/file.nvx";
        if (!exists(nvx))
            nvx = home + "/nvx/live.nvx";
        if (!exists(fx))
            fx = home + "/nvx/file.nvx";
        NSFileManager *fm = NSFileManager.defaultManager;
        NSString *sup = [[fm URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask].firstObject.path
            stringByAppendingPathComponent:@"Clavitone"];
        NSString *logs = [[fm URLsForDirectory:NSLibraryDirectory inDomains:NSUserDomainMask].firstObject.path
            stringByAppendingPathComponent:@"Logs/Clavitone"];
        [fm createDirectoryAtPath:sup withIntermediateDirectories:YES attributes:nil error:nil];
        [fm createDirectoryAtPath:logs withIntermediateDirectories:YES attributes:nil error:nil];
        // THE LOG: the engine's stderr (when not run from a terminal, where it is shown as it is)
        if (!isatty(2)) {
            const std::string lg = std::string(logs.UTF8String) + "/nvlive.log";
            rename(lg.c_str(), (std::string(logs.UTF8String) + "/nvlive.prev.log").c_str());
            if (FILE *f = freopen(lg.c_str(), "w", stderr))
                setvbuf(f, nullptr, _IOLBF, 0);
        }
        if (!exists(nvx)) {
            NSAlert *al = [[NSAlert alloc] init];
            al.messageText = @"Clavitone has no sound data";
            al.informativeText = @"Its live.nvx is neither in the app nor in ~/nvx.";
            [al runModal];
            return 1;
        }
        nv_ui_files_dirs((home + "/Music").c_str(), NSTemporaryDirectory().UTF8String);
        std::vector<std::string> a = {"nvlive", nvx, "--app-windowed", "--session=" + std::string(sup.UTF8String) + "/session.json"};
        if (exists(fx))
            a.push_back("--file-export=" + fx);
        for (int i = 1; i < argc; i++)                  // (the app's own arguments, after; Finder's -psn_ left out)
            if (strncmp(argv[i], "-psn_", 5) != 0)
                a.push_back(argv[i]);
        fprintf(stderr, "clavitone: %s", a[0].c_str());
        for (size_t i = 1; i < a.size(); i++)
            fprintf(stderr, " %s", a[i].c_str());
        fprintf(stderr, "\n");
        std::vector<char *> av;
        for (auto &s : a)
            av.push_back(&s[0]);
        av.push_back(nullptr);
        return nvlive_main((int)a.size(), av.data());
    }
}
