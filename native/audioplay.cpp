// THE FILES CARD's AUDIO PLAYER (Ben 2026-11-26: "allow choosing an mp3 file,
// and then the options change to mp3 controls"): an MP3, WAV or FLAC file --
// our renders among them -- played beside what the keyboard plays, at its own
// level, mixed into the engine's output after the part's (nv_host::render_block).
//
// THE FILE is decoded on a thread of its own (dr_libs: native/third/, public
// domain), resampled to the engine's rate when it differs (a windowed sinc, 32
// taps, the cutoff below both Nyquists), into a ring of two seconds; the audio
// thread takes from the ring without a lock, a wait or an allocation. A long
// file is never held whole: what plays is what was decoded a moment before.
//
// A SEEK or a new file goes through a generation: the audio thread plays only
// a ring its generation matches, and the decoder resets the ring only when the
// audio thread is out of it -- so neither waits on the other's lock.
#define DR_MP3_IMPLEMENTATION
#define DR_WAV_IMPLEMENTATION
#define DR_FLAC_IMPLEMENTATION
#include "third/dr_mp3.h"
#include "third/dr_wav.h"
#include "third/dr_flac.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {

// ONE FILE, decoded as float frames (interleaved, its own channels)
struct Src {
    int kind = 0;                       // 1 mp3, 2 wav, 3 flac
    drmp3 mp3;
    drwav wav;
    drflac *flac = nullptr;
    unsigned ch = 0;
    double sr = 0.0;
    unsigned long long frames = 0;
    static bool ends(const std::string &p, const char *x)
    {
        std::string l = p;
        for (char &c : l)
            c = (char)tolower((unsigned char)c);
        const size_t k = strlen(x);
        return l.size() > k && l.compare(l.size() - k, k, x) == 0;
    }
    bool open(const std::string &path, std::string &err)
    {
        close();
        if (ends(path, ".mp3")) {
            if (!drmp3_init_file(&mp3, path.c_str(), nullptr))
                return err = "not an MP3 it can read", false;
            kind = 1;
            ch = mp3.channels;
            sr = mp3.sampleRate;
            frames = drmp3_get_pcm_frame_count(&mp3);       // (a pass over the file: its length)
            drmp3_seek_to_pcm_frame(&mp3, 0);
        } else if (ends(path, ".wav")) {
            if (!drwav_init_file(&wav, path.c_str(), nullptr))
                return err = "not a WAV it can read", false;
            kind = 2;
            ch = wav.channels;
            sr = wav.sampleRate;
            frames = wav.totalPCMFrameCount;
        } else if (ends(path, ".flac")) {
            flac = drflac_open_file(path.c_str(), nullptr);
            if (!flac)
                return err = "not a FLAC it can read", false;
            kind = 3;
            ch = flac->channels;
            sr = flac->sampleRate;
            frames = flac->totalPCMFrameCount;
        } else
            return err = "not an audio file (MP3, WAV, FLAC)", false;
        if (!ch || sr <= 0.0) {
            close();
            return err = "no channels or rate", false;
        }
        return true;
    }
    unsigned long long read(unsigned long long n, float *out)
    {
        switch (kind) {
        case 1: return drmp3_read_pcm_frames_f32(&mp3, n, out);
        case 2: return drwav_read_pcm_frames_f32(&wav, n, out);
        case 3: return drflac_read_pcm_frames_f32(flac, n, out);
        }
        return 0;
    }
    bool seek(unsigned long long f)
    {
        switch (kind) {
        case 1: return drmp3_seek_to_pcm_frame(&mp3, f);
        case 2: return drwav_seek_to_pcm_frame(&wav, f);
        case 3: return drflac_seek_to_pcm_frame(flac, f);
        }
        return false;
    }
    void close()
    {
        if (kind == 1)
            drmp3_uninit(&mp3);
        else if (kind == 2)
            drwav_uninit(&wav);
        else if (kind == 3)
            drflac_close(flac);
        flac = nullptr;
        kind = 0;
    }
};

// THE RATE CHANGE: a windowed sinc (Blackman), TAPS input frames a side,
// PHASES tabled, linear between two; the cutoff 0.95 of the lower Nyquist
struct Resampler {
    enum { TAPS = 16, PHASES = 512 };
    double step = 1.0;                  // (input frames an output frame)
    double t = 0.0;                     // (the next output's place, in the buffer's frames)
    std::vector<float> tab;             // [PHASES + 1][2 TAPS]
    std::vector<float> in;              // (stereo input frames kept: the window's reach)
    void init(double in_sr, double out_sr)
    {
        step = in_sr / out_sr;
        const double fc = 0.95 * std::min(1.0, out_sr / in_sr);      // (of the input's Nyquist)
        tab.assign((size_t)(PHASES + 1) * 2 * TAPS, 0.0f);
        for (int p = 0; p <= PHASES; p++) {
            const double frac = (double)p / PHASES;
            for (int k = 0; k < 2 * TAPS; k++) {
                const double x = (k - (TAPS - 1)) - frac;   // (taps at i - TAPS + 1 .. i + TAPS)
                const double s = std::fabs(x) < 1e-12 ? fc : std::sin(M_PI * fc * x) / (M_PI * x);
                const double u = (x + TAPS) / (2.0 * TAPS);
                const double w = u <= 0.0 || u >= 1.0 ? 0.0 : 0.42 - 0.5 * std::cos(2 * M_PI * u) + 0.08 * std::cos(4 * M_PI * u);
                tab[((size_t)p * 2 * TAPS) + k] = (float)(s * w);
            }
        }
        reset();
    }
    void reset()
    {
        in.assign((size_t)2 * (TAPS - 1), 0.0f);        // (silence before the first frame)
        t = TAPS - 1;
    }
    // input appended (stereo frames); outputs made while the window has them, into out
    void push(const float *x, size_t n) { in.insert(in.end(), x, x + 2 * n); }
    size_t pull(float *out, size_t cap)
    {
        size_t m = 0;
        const size_t nin = in.size() / 2;
        while (m < cap) {
            const double fi = std::floor(t);
            const long i = (long)fi;
            if (i + TAPS >= (long)nin)
                break;
            const double ph = (t - fi) * PHASES;
            const int p = (int)ph;
            const float a = (float)(ph - p);
            const float *h0 = &tab[(size_t)p * 2 * TAPS], *h1 = &tab[(size_t)(p + 1) * 2 * TAPS];
            float l = 0.0f, r = 0.0f;
            const float *s = &in[(size_t)(i - TAPS + 1) * 2];
            for (int k = 0; k < 2 * TAPS; k++) {
                const float h = h0[k] + a * (h1[k] - h0[k]);
                l += h * s[2 * k];
                r += h * s[2 * k + 1];
            }
            out[2 * m] = l;
            out[2 * m + 1] = r;
            m++;
            t += step;
        }
        // (what no later output reaches let go)
        const long drop = (long)std::floor(t) - (TAPS - 1);
        if (drop > 4096) {
            in.erase(in.begin(), in.begin() + 2 * drop);
            t -= drop;
        }
        return m;
    }
};

struct Player {
    double out_sr;
    // the ring: stereo frames at out_sr; positions counted, never wrapped
    std::vector<float> ring;
    size_t cap = 0;
    std::atomic<unsigned long long> rpos{0}, wpos{0};
    std::atomic<int> gen{0}, ready{-1};             // (the audio plays a ring whose generation is ready)
    std::atomic<bool> audio_in{false}, playing{false}, eof{false}, quit{false};
    std::atomic<long long> at_out{0};               // (output frames played from the file's start)
    std::atomic<float> gain{1.0f};
    std::atomic<double> seek_s{0.0};
    std::mutex mu;                                  // (the decoder's state: open, seek, close)
    std::condition_variable cv;
    std::thread th;
    Src src;
    Resampler rs;
    bool same_rate = true;
    std::string path, err;
    double len_s = 0.0;
    float level_db = 0.0f;

    explicit Player(double sr) : out_sr(sr)
    {
        cap = (size_t)(2.0 * sr);
        ring.assign(2 * cap, 0.0f);
        th = std::thread([this] { loop(); });
    }
    ~Player()
    {
        quit = true;
        cv.notify_all();
        th.join();
        src.close();
    }
    // (the audio thread out of the ring: then the decoder may reset it)
    void wait_audio_out()
    {
        while (audio_in.load(std::memory_order_acquire))
            std::this_thread::yield();
    }
    void loop()
    {
        std::vector<float> dec, tmp, out;
        int done_gen = -1;
        std::unique_lock<std::mutex> lk(mu);
        while (!quit) {
            const int g = gen.load();
            if (g != done_gen) {        // A SEEK (or a new file): the ring anew from its place
                done_gen = g;
                wait_audio_out();
                rpos = 0;
                wpos = 0;
                eof = false;
                if (src.kind) {
                    const double s = std::max(0.0, seek_s.load());
                    const unsigned long long f = std::min((unsigned long long)(s * src.sr), src.frames);
                    src.seek(f);
                    rs.reset();
                    at_out = (long long)std::llround((double)f / src.sr * out_sr);
                }
                ready = g;
            }
            const size_t room = cap - (size_t)(wpos - rpos);
            if (!src.kind || eof || room < 2048) {
                cv.wait_for(lk, std::chrono::milliseconds(20));
                continue;
            }
            // decode a piece, as stereo, resampled where the rates differ
            const unsigned long long want = 1024;
            dec.resize((size_t)want * src.ch);
            const unsigned long long got = src.read(want, dec.data());
            if (!got) {
                eof = true;
                continue;
            }
            tmp.resize((size_t)got * 2);
            for (unsigned long long k = 0; k < got; k++) {
                const float *s = &dec[(size_t)k * src.ch];
                tmp[2 * k] = s[0];
                tmp[2 * k + 1] = src.ch > 1 ? s[1] : s[0];
            }
            const float *put = tmp.data();
            size_t np = (size_t)got;
            if (!same_rate) {
                rs.push(tmp.data(), (size_t)got);
                out.resize((size_t)(got * (1.0 / rs.step) + 64) * 2);
                np = rs.pull(out.data(), out.size() / 2);
                put = out.data();
            }
            for (size_t k = 0; k < np; k++) {           // (room is checked again: a piece is at most ~2400 frames)
                if (gen.load() != g)
                    break;
                while ((size_t)(wpos - rpos) >= cap && !quit && gen.load() == g) {
                    lk.unlock();
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                    lk.lock();
                }
                const size_t w = (size_t)(wpos % cap);
                ring[2 * w] = put[2 * k];
                ring[2 * w + 1] = put[2 * k + 1];
                wpos.fetch_add(1, std::memory_order_release);
            }
        }
    }
    bool open(const std::string &p)
    {
        std::lock_guard<std::mutex> lk(mu);
        playing = false;
        ready = -1;                     // (the audio thread out of the old ring from here)
        wait_audio_out();
        err.clear();
        if (!src.open(p, err)) {
            path.clear();
            len_s = 0.0;
            gen++;
            cv.notify_all();
            return false;
        }
        path = p;
        len_s = (double)src.frames / src.sr;
        same_rate = std::fabs(src.sr - out_sr) < 1e-6;
        if (!same_rate)
            rs.init(src.sr, out_sr);
        seek_s = 0.0;
        gen++;
        cv.notify_all();
        return true;
    }
    void close()
    {
        std::lock_guard<std::mutex> lk(mu);
        playing = false;
        ready = -1;
        wait_audio_out();
        src.close();
        path.clear();
        len_s = 0.0;
        gen++;
        cv.notify_all();
    }
    void seek(double s)
    {
        seek_s = std::max(0.0, std::min(s, len_s));
        gen++;
        cv.notify_all();
    }
    // THE AUDIO THREAD's: the ring's frames added to L and R, at the player's gain
    void mix(float *L, float *R, long n)
    {
        if (!playing.load(std::memory_order_relaxed))
            return;
        audio_in.store(true, std::memory_order_release);
        if (ready.load(std::memory_order_acquire) == gen.load(std::memory_order_acquire)) {
            const float g = gain.load(std::memory_order_relaxed);
            const unsigned long long r0 = rpos.load(std::memory_order_relaxed);
            const unsigned long long have = wpos.load(std::memory_order_acquire) - r0;
            const long m = (long)std::min<unsigned long long>(have, (unsigned long long)n);
            for (long k = 0; k < m; k++) {
                const size_t i = (size_t)((r0 + k) % cap);
                L[k] += g * ring[2 * i];
                R[k] += g * ring[2 * i + 1];
            }
            rpos.store(r0 + m, std::memory_order_release);
            at_out.fetch_add(m, std::memory_order_relaxed);
            if (m < n && eof.load(std::memory_order_acquire) && wpos.load() == rpos.load())
                playing.store(false, std::memory_order_relaxed);        // (the end: stopped there)
            cv.notify_one();
        }
        audio_in.store(false, std::memory_order_release);
    }
};

}  // namespace

extern "C" {

void *nv_aplay_new(double out_sr) { return new Player(out_sr); }
void nv_aplay_free(void *p) { delete (Player *)p; }
int nv_aplay_open(void *p, const char *path, char *err, int cap)
{
    Player *P = (Player *)p;
    const bool ok = P->open(path ? path : "");
    if (err && cap > 0)
        snprintf(err, (size_t)cap, "%s", ok ? "" : P->err.c_str());
    return ok ? 0 : -1;
}
void nv_aplay_close(void *p) { ((Player *)p)->close(); }
void nv_aplay_play(void *p, int on)
{
    Player *P = (Player *)p;
    if (on && P->len_s > 0.0 && !P->playing && P->at_out.load() >= (long long)(P->len_s * P->out_sr) - 1)
        P->seek(0.0);                   // (at its end: from the start again)
    P->playing = on != 0 && P->len_s > 0.0;
}
void nv_aplay_seek(void *p, double s) { ((Player *)p)->seek(s); }
void nv_aplay_level(void *p, double db)
{
    Player *P = (Player *)p;
    P->level_db = (float)db;
    P->gain = (float)std::pow(10.0, db / 20.0);
}
// its state: the place and length (s), playing, the file's rate and channels, the level (dB)
void nv_aplay_state(void *p, double *at, double *len, int *playing, double *sr, int *ch, double *level_db)
{
    Player *P = (Player *)p;
    *at = std::min((double)P->at_out.load() / P->out_sr, P->len_s);
    *len = P->len_s;
    *playing = P->playing ? 1 : 0;
    *sr = P->src.kind ? P->src.sr : 0.0;
    *ch = P->src.kind ? (int)P->src.ch : 0;
    *level_db = P->level_db;
}
// its file, its last error
const char *nv_aplay_path(void *p) { return ((Player *)p)->path.c_str(); }
void nv_aplay_mix(void *p, float *L, float *R, long n) { ((Player *)p)->mix(L, R, n); }

}  // extern "C"
