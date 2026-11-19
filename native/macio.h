// macio.h -- nvlive's devices on macOS: CoreMIDI and CoreAudio behind the
// interfaces the Linux host already uses (hostlive.h), so the engine loop,
// the MIDI reader and its parser, the Messenger's writer and its Device
// Inquiry all run unchanged:
//
//   MIDI   a device is "coremidi:N" (N its source's unique ID; the name is
//          CoreMIDI's display name, "Moog Messenger"). Opened, it is ONE END
//          OF A SOCKET PAIR, as a raw ALSA device is a file: what the source
//          sends arrives on it as MIDI bytes (CoreMIDI's UMP, MIDI 1.0
//          protocol, made bytes again), and bytes written to it go to the
//          destination of the same entity (or name), as UMP. close() lets
//          the source go.
//   AUDIO  Alsa's blocking writer over the default output unit: writei
//          puts a block into a ring the unit's render callback empties --
//          waiting while the ring is full, as snd_pcm_writei does -- so
//          nvlive's audio thread paces itself on the device exactly as on
//          Linux. The ring holds the latency asked (--latency-ms), at least
//          two blocks; a callback finding it short plays silence and counts
//          an underrun (writei returns -EPIPE once, as ALSA's xrun).
//
// Only included on __APPLE__ (hostlive.h). Linked with CoreMIDI,
// AudioToolbox, CoreAudio and CoreFoundation (toolchain.py).

#ifndef NV_MACIO_H
#define NV_MACIO_H

#include <TargetConditionals.h>
#include <AudioToolbox/AudioToolbox.h>
#if !TARGET_OS_IPHONE
#include <CoreAudio/CoreAudio.h>                // (macOS's: iOS has CoreAudioTypes alone, through AudioToolbox)
#endif
#include <CoreFoundation/CoreFoundation.h>
#include <CoreMIDI/CoreMIDI.h>
#include <algorithm>
#include <atomic>
#include <fcntl.h>
#include <cerrno>
#include <condition_variable>
#include <cstring>
#include <map>
#include <mutex>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace macio {

inline std::string cfstr(CFStringRef s)
{
    if (!s)
        return "";
    char b[512];
    if (!CFStringGetCString(s, b, sizeof b, kCFStringEncodingUTF8))
        b[0] = 0;
    return b;
}

inline std::string endpoint_name(MIDIEndpointRef e)
{
    CFStringRef s = nullptr;
    if (MIDIObjectGetStringProperty(e, kMIDIPropertyDisplayName, &s) != noErr || !s)
        MIDIObjectGetStringProperty(e, kMIDIPropertyName, &s);
    std::string r = cfstr(s);
    if (s)
        CFRelease(s);
    return r;
}

inline SInt32 unique_id(MIDIObjectRef o)
{
    SInt32 id = 0;
    MIDIObjectGetIntegerProperty(o, kMIDIPropertyUniqueID, &id);
    return id;
}

// ---- MIDI ----

// UMP (MIDI 1.0 protocol) -> the bytes a raw device gives; sysex7 by its
// six-byte packets (F0 at the start, F7 at the end)
inline void ump_to_bytes(const uint32_t *w, int n, std::vector<uint8_t> &out)
{
    for (int i = 0; i < n;) {
        const uint32_t a = w[i];
        const int mt = a >> 28;
        const int len = mt <= 2 ? 1 : mt <= 4 ? 2 : 4;
        if (mt == 1) {                                  // system common / real time
            const uint8_t st = (a >> 16) & 0xFF;
            out.push_back(st);
            const int nd = st == 0xF1 || st == 0xF3 ? 1 : st == 0xF2 ? 2 : 0;
            if (nd >= 1)
                out.push_back((a >> 8) & 0x7F);
            if (nd >= 2)
                out.push_back(a & 0x7F);
        } else if (mt == 2) {                           // MIDI 1.0 channel voice
            const uint8_t st = (a >> 16) & 0xFF;
            out.push_back(st);
            out.push_back((a >> 8) & 0x7F);
            const int hi = st & 0xF0;
            if (hi != 0xC0 && hi != 0xD0)
                out.push_back(a & 0x7F);
        } else if (mt == 3 && i + 1 < n) {              // sysex7
            const int status = (a >> 20) & 0xF, cnt = (a >> 16) & 0xF;
            if (status == 0 || status == 1)
                out.push_back(0xF0);
            const uint8_t d[6] = {(uint8_t)((a >> 8) & 0x7F), (uint8_t)(a & 0x7F),
                                  (uint8_t)((w[i + 1] >> 24) & 0x7F), (uint8_t)((w[i + 1] >> 16) & 0x7F),
                                  (uint8_t)((w[i + 1] >> 8) & 0x7F), (uint8_t)(w[i + 1] & 0x7F)};
            for (int k = 0; k < cnt && k < 6; k++)
                out.push_back(d[k]);
            if (status == 0 || status == 3)
                out.push_back(0xF7);
        }
        i += len;
    }
}

// bytes (whole messages, running status allowed) -> UMP words, MIDI 1.0
// protocol, group 0
struct BytesToUmp {
    int status = 0, need = 0, got = 0;
    uint8_t d[2] = {0, 0};
    bool insx = false;
    std::vector<uint8_t> sx;
    void flush_sx(std::vector<uint32_t> &out, bool last)
    {
        // sysex7 packets of six: complete (0), start (1), continue (2), end (3)
        size_t at = 0;
        bool first = true;
        while (at < sx.size() || first) {
            const size_t n = std::min<size_t>(6, sx.size() - at);
            const bool fin = at + n >= sx.size();
            int st = first && fin && last ? 0 : first ? 1 : fin && last ? 3 : 2;
            uint8_t b[6] = {0, 0, 0, 0, 0, 0};
            for (size_t k = 0; k < n; k++)
                b[k] = sx[at + k];
            out.push_back(0x30000000u | (uint32_t)st << 20 | (uint32_t)n << 16 | (uint32_t)b[0] << 8 | b[1]);
            out.push_back((uint32_t)b[2] << 24 | (uint32_t)b[3] << 16 | (uint32_t)b[4] << 8 | b[5]);
            at += n;
            first = false;
            if (fin)
                break;
        }
        sx.clear();
    }
    void feed(const uint8_t *buf, size_t n, std::vector<uint32_t> &out)
    {
        for (size_t i = 0; i < n; i++) {
            const uint8_t b = buf[i];
            if (b >= 0xF8) {                            // real time: anywhere
                out.push_back(0x10000000u | (uint32_t)b << 16);
                continue;
            }
            if (b == 0xF0) {
                insx = true;
                sx.clear();
                continue;
            }
            if (b == 0xF7) {
                if (insx)
                    flush_sx(out, true);
                insx = false;
                continue;
            }
            if (insx) {
                if (b & 0x80) {                         // (an unterminated exclusive: ended)
                    flush_sx(out, true);
                    insx = false;
                } else {
                    sx.push_back(b);
                    continue;
                }
            }
            if (b & 0x80) {
                status = b;
                got = 0;
                const int hi = b & 0xF0;
                need = b >= 0xF0 ? (b == 0xF1 || b == 0xF3 ? 1 : b == 0xF2 ? 2 : 0)
                                 : (hi == 0xC0 || hi == 0xD0) ? 1 : 2;
                if (b >= 0xF0 && need == 0) {
                    out.push_back(0x10000000u | (uint32_t)b << 16);
                    status = 0;
                }
                continue;
            }
            if (!status)
                continue;
            d[got++] = b;
            if (got < need)
                continue;
            got = 0;
            const uint32_t w = (uint32_t)status << 16 | (uint32_t)d[0] << 8 | (need > 1 ? d[1] : 0);
            out.push_back((status >= 0xF0 ? 0x10000000u : 0x20000000u) | w);
            if (status >= 0xF0)
                status = 0;                             // (no running status for system common)
        }
    }
};

struct Conn {
    int ours = -1, theirs = -1;                         // the socket pair: ours CoreMIDI's end
    MIDIEndpointRef src = 0, dst = 0;
    bool reading = false;
    std::thread writer;
};

struct Midi {
    std::mutex mu;
    MIDIClientRef client = 0;
    MIDIPortRef in = 0, out = 0;
    std::map<int, Conn *> by_fd;                        // the caller's fd -> its connection
    bool ok = false;
    bool start()
    {
        std::lock_guard<std::mutex> lk(mu);
        if (client)
            return ok;
        if (MIDIClientCreate(CFSTR("nvlive"), nullptr, nullptr, &client) != noErr)
            return false;
        // (MIDI 1.0 protocol: CoreMIDI translates any source to it)
        if (MIDIInputPortCreateWithProtocol(client, CFSTR("in"), kMIDIProtocol_1_0, &in,
                                            ^(const MIDIEventList *el, void *ref) {
                                                Conn *c = (Conn *)ref;
                                                std::vector<uint8_t> b;
                                                const MIDIEventPacket *p = &el->packet[0];
                                                for (UInt32 k = 0; k < el->numPackets; k++) {
                                                    ump_to_bytes(p->words, (int)p->wordCount, b);
                                                    p = MIDIEventPacketNext(p);
                                                }
                                                if (!b.empty() && c && c->ours >= 0)
                                                    (void)::send(c->ours, b.data(), b.size(), MSG_DONTWAIT);
                                            }) != noErr)
            return false;
        if (MIDIOutputPortCreate(client, CFSTR("out"), &out) != noErr)
            return false;
        ok = true;
        return true;
    }
};
inline Midi &M()
{
    static Midi m;
    return m;
}

// (path, name) of every source now: live.input_names', as hostlive's
// midi_devices lists ALSA's
inline std::vector<std::pair<std::string, std::string>> devices()
{
    std::vector<std::pair<std::string, std::string>> ds;
    M().start();
    const ItemCount n = MIDIGetNumberOfSources();
    for (ItemCount i = 0; i < n; i++) {
        MIDIEndpointRef e = MIDIGetSource(i);
        ds.push_back({"coremidi:" + std::to_string(unique_id(e)), endpoint_name(e)});
    }
    return ds;
}

inline MIDIEndpointRef source_of(const std::string &path)
{
    if (path.compare(0, 9, "coremidi:"))
        return 0;
    const SInt32 id = (SInt32)atol(path.c_str() + 9);
    const ItemCount n = MIDIGetNumberOfSources();
    for (ItemCount i = 0; i < n; i++)
        if (unique_id(MIDIGetSource(i)) == id)
            return MIDIGetSource(i);
    return 0;
}

// the destination beside a source: the same entity's, else the same name's
inline MIDIEndpointRef dest_of(MIDIEndpointRef src)
{
    MIDIEntityRef ent = 0;
    MIDIEndpointGetEntity(src, &ent);
    const std::string nm = endpoint_name(src);
    MIDIEndpointRef byname = 0;
    const ItemCount n = MIDIGetNumberOfDestinations();
    for (ItemCount i = 0; i < n; i++) {
        MIDIEndpointRef d = MIDIGetDestination(i);
        MIDIEntityRef de = 0;
        MIDIEndpointGetEntity(d, &de);
        if (ent && de == ent)
            return d;
        if (!byname && endpoint_name(d) == nm)
            byname = d;
    }
    return byname;
}

inline bool exists(const std::string &path) { return source_of(path) != 0; }

// open(2) for a "coremidi:N" path: O_RDONLY, O_WRONLY or O_RDWR (O_NONBLOCK
// as asked); -1 (errno ENOENT) where it is not there
inline int open(const std::string &path, int flags)
{
    if (!M().start()) {
        errno = ENODEV;
        return -1;
    }
    MIDIEndpointRef src = source_of(path);
    if (!src) {
        errno = ENOENT;
        return -1;
    }
    int sv[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) != 0)
        return -1;
    const int acc = flags & O_ACCMODE;
    Conn *c = new Conn;
    c->ours = sv[0];
    c->theirs = sv[1];
    c->src = src;
    if (flags & O_NONBLOCK)
        fcntl(sv[1], F_SETFL, fcntl(sv[1], F_GETFL) | O_NONBLOCK);
    if (acc == O_RDONLY || acc == O_RDWR) {
        if (MIDIPortConnectSource(M().in, src, c) == noErr)
            c->reading = true;
    }
    if (acc == O_WRONLY || acc == O_RDWR) {
        c->dst = dest_of(src);
        // the writer: bytes from the caller's end -> UMP -> the destination
        c->writer = std::thread([c] {
            BytesToUmp conv;
            uint8_t buf[512];
            for (;;) {
                ssize_t r = ::recv(c->ours, buf, sizeof buf, 0);
                if (r <= 0)
                    break;
                std::vector<uint32_t> w;
                conv.feed(buf, (size_t)r, w);
                if (w.empty() || !c->dst)
                    continue;
                // one event packet per message (a sysex7 run is several)
                Byte mem[4096];
                MIDIEventList *el = (MIDIEventList *)mem;
                MIDIEventPacket *p = MIDIEventListInit(el, kMIDIProtocol_1_0);
                for (size_t i = 0; i < w.size();) {
                    const int mt = w[i] >> 28;
                    const size_t len = mt <= 2 ? 1 : mt <= 4 ? 2 : 4;
                    p = MIDIEventListAdd(el, sizeof mem, p, 0, len, &w[i]);
                    if (!p) {                           // (full: send it, start again)
                        MIDISendEventList(M().out, c->dst, el);
                        p = MIDIEventListInit(el, kMIDIProtocol_1_0);
                        p = MIDIEventListAdd(el, sizeof mem, p, 0, len, &w[i]);
                    }
                    i += len;
                }
                MIDISendEventList(M().out, c->dst, el);
            }
        });
    }
    std::lock_guard<std::mutex> lk(M().mu);
    M().by_fd[sv[1]] = c;
    return sv[1];
}

// close(2) for what open gave: the source let go, the writer ended
inline int close(int fd)
{
    Conn *c = nullptr;
    {
        std::lock_guard<std::mutex> lk(M().mu);
        auto it = M().by_fd.find(fd);
        if (it == M().by_fd.end())
            return ::close(fd);
        c = it->second;
        M().by_fd.erase(it);
    }
    if (c->reading)
        MIDIPortDisconnectSource(M().in, c->src);
    ::shutdown(c->ours, SHUT_RDWR);
    ::close(c->theirs);
    if (c->writer.joinable())
        c->writer.join();
    ::close(c->ours);
    delete c;
    return 0;
}

// ---- AUDIO: Alsa's writer over the default output unit ----

struct Audio {
    AudioComponentInstance unit = nullptr;
    std::vector<float> ring;                            // interleaved stereo
    size_t cap = 0;                                     // (frames)
    std::atomic<size_t> rd{0}, wr{0};                   // frames written and read, ever
    std::atomic<long> underruns{0};
    std::atomic<bool> xrun{false};
    std::mutex mu;
    std::condition_variable cv;
    int channels = 2;

    static OSStatus render(void *ref, AudioUnitRenderActionFlags *, const AudioTimeStamp *, UInt32, UInt32 n,
                           AudioBufferList *io)
    {
        Audio *a = (Audio *)ref;
        float *out = (float *)io->mBuffers[0].mData;
        const size_t have = a->wr.load(std::memory_order_acquire) - a->rd.load(std::memory_order_relaxed);
        const size_t take = std::min<size_t>(have, n);
        size_t r = a->rd.load(std::memory_order_relaxed);
        for (size_t i = 0; i < take; i++, r++) {
            const size_t at = (r % a->cap) * 2;
            out[2 * i] = a->ring[at];
            out[2 * i + 1] = a->ring[at + 1];
        }
        if (take < n) {
            memset(out + 2 * take, 0, (n - take) * 2 * sizeof(float));
            if (a->wr.load() > 0) {
                a->underruns++;
                a->xrun = true;
            }
        }
        a->rd.store(r, std::memory_order_release);
        a->cv.notify_one();
        return noErr;
    }

    // snd_pcm_set_params: float, interleaved, stereo, the rate; the ring the
    // latency asked (microseconds), at least two blocks of `frames`
    int set_params(unsigned rate, unsigned latency_us, unsigned frames)
    {
        AudioComponentDescription d{};
        d.componentType = kAudioUnitType_Output;
#if TARGET_OS_IPHONE
        d.componentSubType = kAudioUnitSubType_RemoteIO;        // (iOS: the session's output; its buffer the session's)
#else
        d.componentSubType = kAudioUnitSubType_DefaultOutput;
#endif
        d.componentManufacturer = kAudioUnitManufacturer_Apple;
        AudioComponent comp = AudioComponentFindNext(nullptr, &d);
        if (!comp || AudioComponentInstanceNew(comp, &unit) != noErr)
            return -ENODEV;
        AudioStreamBasicDescription f{};
        f.mSampleRate = rate;
        f.mFormatID = kAudioFormatLinearPCM;
        f.mFormatFlags = kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked;
        f.mChannelsPerFrame = 2;
        f.mBitsPerChannel = 32;
        f.mBytesPerFrame = 8;
        f.mFramesPerPacket = 1;
        f.mBytesPerPacket = 8;
        if (AudioUnitSetProperty(unit, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, &f, sizeof f) != noErr)
            return -EINVAL;
        // the device's own buffer at a block, where it allows
        UInt32 fr = frames;
#if !TARGET_OS_IPHONE
        AudioUnitSetProperty(unit, kAudioDevicePropertyBufferFrameSize, kAudioUnitScope_Global, 0, &fr, sizeof fr);
#else
        (void)fr;
#endif
        AURenderCallbackStruct cb{render, this};
        if (AudioUnitSetProperty(unit, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &cb, sizeof cb)
            != noErr)
            return -EINVAL;
        cap = std::max<size_t>(2 * frames, (size_t)((double)latency_us * 1e-6 * rate + frames - 1) / frames * frames);
        ring.assign(cap * 2, 0.0f);
        if (AudioUnitInitialize(unit) != noErr || AudioOutputUnitStart(unit) != noErr)
            return -EIO;
        return 0;
    }

    // snd_pcm_writei: n frames, waiting while the ring has no room; -EPIPE
    // once after an underrun (the caller's recover, as ALSA's)
    long writei(const float *buf, unsigned long n)
    {
        if (xrun.exchange(false))
            return -EPIPE;
        unsigned long done = 0;
        while (done < n) {
            {
                std::unique_lock<std::mutex> lk(mu);
                cv.wait_for(lk, std::chrono::milliseconds(20),
                            [&] { return wr.load() - rd.load() < cap; });
            }
            const size_t room = cap - (wr.load() - rd.load());
            const size_t k = std::min<size_t>(room, n - done);
            size_t w = wr.load(std::memory_order_relaxed);
            for (size_t i = 0; i < k; i++, w++) {
                const size_t at = (w % cap) * 2;
                ring[at] = buf[2 * (done + i)];
                ring[at + 1] = buf[2 * (done + i) + 1];
            }
            wr.store(w, std::memory_order_release);
            done += k;
        }
        return (long)n;
    }

    void close()
    {
        if (unit) {
            AudioOutputUnitStop(unit);
            AudioUnitUninitialize(unit);
            AudioComponentInstanceDispose(unit);
            unit = nullptr;
        }
    }
};

}  // namespace macio

#endif
