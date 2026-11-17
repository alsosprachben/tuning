// nvroomtail.cpp -- roomtail.py natively: a render's diffuse tail (and the
// room's low modes, or a GS device's tail in the room's place) convolved onto
// its dry WAV, bit for bit as roomtail.py writes it.
//
//     nvroomtail IN.wav OUT.wav [--export=PATH] [--seed=N] [--no-modes]
//
// THE ROOM is the render's: IN.room.json's room_name (blockrender's and
// nvrender's sidecar; none, TUNING_ROOM, else the hall), its bands' measured
// directivity (band_q), a GS reverb's level, time and delay feedback
// (tail_gain, tail_time, delay_fb), and the reverb send -- IN.send.wav when
// the channels differ, else the sidecar's one value. The room's spec (its
// T60s, surfaces, the listener) comes from an export's LROOMS section
// (native_export.py --live: every room live can switch to, roomtail.tail_spec
// each; and roomtail.device_spec for the plate and delays) -- or a file
// export's rooms trailer (the same, found from its end): --export=PATH,
// else $TUNING_ROOM_EXPORT, else ~/nvx/live.nvx.
//
// THE IRs are native/roomtail.cpp's -- the very draws live makes (numpy's
// RandomState, pocketfft, its sums), composed as live.room_irs composes them,
// which is roomtail.main's composition. THE CONVOLUTION is roomtail's
// overlap_add -- its block (4x the IR's power of two), numpy's rfft/irfft
// (native/pocketfft.c), its complex products, its order of adding -- done in
// STREAM: each segment's output final once the next starts, so a long song
// needs a few blocks of memory, not the song twice over (roomtail.py holds the
// whole file). Its peak over full scale: the file written again, scaled as
// roomtail scales it (a second pass).
//
// IN THE LIBRARY (libnative: nv_roomtail_main, the program's whole; the
// nvroomtail program is its two-line main, nvroomtail_main.cpp): iOS runs no
// helper programs, so the Files card's best-quality render calls it in its
// own process -- everything it opens or draws freed on every way out.
//
// Exit 2 (refused): a device tail (plate, delays) at a rate other than the
// export's 48 kHz (its filters are drawn there), a --q other than 2.0,
// anything but stereo.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

#include "session.h"

extern "C" {
int nv_pocket_rfft(const double *x, int n, double *out);
int nv_pocket_irfft(const double *c, int n, double *out);
long nv_room_tail_ir(const double *sp, const double *bq, int has_bq, int sr, int seed, double **out);
long nv_room_tail_modes(const double *sp, const double *bq, int has_bq, int sr, double **out, int *nmodes);
long nv_room_tail_device(const double *sp, const double *dv, const double *bq, int has_bq, int sr, double **out,
                         double ts, double dfb);
void nv_room_spec_scale(double *sp, double ts);
void nv_room_tail_free(double *p);
}

namespace nvroomtail {

static const double OCTAVES[9] = {63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0};

// ---- a file mapped (the export, the WAVs) ----
struct Map {
    const uint8_t *p = nullptr;
    size_t n = 0;
    bool open(const std::string &path)
    {
        int fd = ::open(path.c_str(), O_RDONLY);
        if (fd < 0)
            return false;
        struct stat st;
        if (fstat(fd, &st) != 0 || st.st_size <= 0) {
            close(fd);
            return false;
        }
        void *m = mmap(nullptr, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
        close(fd);
        if (m == MAP_FAILED)
            return false;
        p = (const uint8_t *)m;
        n = (size_t)st.st_size;
        return true;
    }
    ~Map()
    {
        if (p)
            munmap((void *)p, n);
    }
};

// ---- THE ROOMS an export carries (its LROOMS section, as host.cpp reads it) ----
struct Room {
    std::string name;
    bool reflect = true;
    std::vector<double> spec;
};
// (the section parsed from its bytes: true where it parses whole)
static bool parse_rooms(const uint8_t *rb, size_t len, std::vector<Room> &rooms, std::vector<double> &dev)
{
    size_t k = 0;
    bool ok = true;
    auto i32 = [&]() {
        int v = 0;
        if (k + 4 <= len)
            memcpy(&v, rb + k, 4);
        else
            ok = false;
        k += 4;
        return v;
    };
    auto f64s = [&](int n) {
        std::vector<double> v(n > 0 ? n : 0);
        if (n < 0 || k + 8 * (size_t)v.size() > len)
            ok = false;
        else if (n > 0)
            memcpy(v.data(), rb + k, 8 * (size_t)n);
        k += 8 * v.size();
        return v;
    };
    int nf = i32(), per = 0;
    for (int q = 0; ok && q < nf; q++) {
        i32();
        per += i32();
    }
    const int ncls = i32();
    std::vector<double> dv = f64s(i32());
    const int nr = i32();
    std::vector<Room> rs;
    for (int q = 0; ok && q < nr; q++) {
        Room r;
        const int ln = i32();
        if (ln < 0 || k + (size_t)ln > len) {
            ok = false;
            break;
        }
        r.name.assign((const char *)rb + k, (size_t)ln);
        k += (size_t)ln;
        r.reflect = i32() != 0;
        r.spec = f64s(i32());
        if (r.reflect)
            k += (size_t)per * (size_t)ncls;
        rs.push_back(r);
    }
    if (!(ok && k == len))
        return false;
    rooms = rs;
    dev = dv;
    return true;
}

// THE ROOMS an export carries (its LROOMS section, as host.cpp reads it):
// found by its tag, read in chunks (the export is a gigabyte; only the
// section is kept), kept where it parses whole
static bool export_rooms(const std::string &path, std::vector<Room> &rooms, std::vector<double> &dev)
{
    FILE *f = fopen(path.c_str(), "rb");
    if (!f)
        return false;
    // A FILE EXPORT's rooms: its trailer (the body, its length, b"NVROOMS\0")
    {
        char tag[8];
        long long rl = 0;
        if (fseeko(f, -16, SEEK_END) == 0 && fread(&rl, 8, 1, f) == 1 && fread(tag, 1, 8, f) == 8
            && !memcmp(tag, "NVROOMS", 8) && rl > 0 && rl < (1LL << 31) && fseeko(f, -16 - rl, SEEK_END) == 0) {
            std::vector<uint8_t> rb((size_t)rl);
            if (fread(rb.data(), 1, rb.size(), f) == rb.size() && parse_rooms(rb.data(), rb.size(), rooms, dev)) {
                fclose(f);
                return true;
            }
        }
        fseeko(f, 0, SEEK_SET);
    }
    const size_t CH = 8u << 20;
    std::vector<uint8_t> buf(CH + 6);
    size_t keep = 0;
    long long base = 0;                         // (the file offset of buf[0])
    bool found = false;
    for (;;) {
        const size_t got = fread(buf.data() + keep, 1, CH, f);
        const size_t have = keep + got;
        if (have < 6)
            break;
        size_t at = 0;
        while (!found) {
            const uint8_t *t = (const uint8_t *)memmem(buf.data() + at, have - at, "LROOMS", 6);
            if (!t)
                break;
            const long long off = base + (t - buf.data()) + 6;
            at = (size_t)(t - buf.data()) + 1;
            long long rl = 0;
            if (fseeko(f, off, SEEK_SET) != 0 || fread(&rl, 8, 1, f) != 1 || rl <= 0 || rl > (1LL << 31)) {
                fseeko(f, base + (long long)have, SEEK_SET);
                continue;
            }
            std::vector<uint8_t> rb((size_t)rl);
            const bool read = fread(rb.data(), 1, rb.size(), f) == rb.size();
            found = read && parse_rooms(rb.data(), rb.size(), rooms, dev);
            fseeko(f, base + (long long)have, SEEK_SET);
        }
        if (found || got == 0)
            break;
        keep = std::min<size_t>(5, have);       // (a tag across two chunks)
        memmove(buf.data(), buf.data() + have - keep, keep);
        base += (long long)(have - keep);
    }
    fclose(f);
    return found;
}

// ---- A WAV (roomtail.read_wav: 16, 24 or 32-bit PCM over full scale; 32-bit
// float as written) ----
struct Wav {
    Map m;
    int ch = 0, sr = 0, bits = 0, fmt = 0;
    const uint8_t *data = nullptr;
    long frames = 0;
    bool open(const std::string &path, std::string &why)
    {
        if (!m.open(path)) {
            why = "cannot read " + path;
            return false;
        }
        if (m.n < 12 || memcmp(m.p, "RIFF", 4) || memcmp(m.p + 8, "WAVE", 4)) {
            why = path + ": not a WAV";
            return false;
        }
        size_t at = 12;
        bool fmt_ok = false;
        while (at + 8 <= m.n) {
            uint32_t sz;
            memcpy(&sz, m.p + at + 4, 4);
            const uint8_t *body = m.p + at + 8;
            if (!memcmp(m.p + at, "fmt ", 4) && sz >= 16) {
                uint16_t tag, nc, bps;
                uint32_t rate;
                memcpy(&tag, body, 2);
                memcpy(&nc, body + 2, 2);
                memcpy(&rate, body + 4, 4);
                memcpy(&bps, body + 14, 2);
                if (tag == 0xFFFE && sz >= 26)
                    memcpy(&tag, body + 24, 2);         // (WAVE_FORMAT_EXTENSIBLE: its subformat)
                fmt = tag;
                ch = nc;
                sr = (int)rate;
                bits = bps;
                fmt_ok = true;
            } else if (!memcmp(m.p + at, "data", 4) && fmt_ok) {
                data = body;
                const size_t avail = m.n - (at + 8);
                const size_t bytes = std::min((size_t)sz, avail);
                frames = (long)(bytes / ((size_t)ch * (size_t)(bits / 8)));
                break;
            }
            at += 8 + sz + (sz & 1);
        }
        if (!data || ch <= 0) {
            why = path + ": no audio";
            return false;
        }
        if (!((fmt == 1 && (bits == 16 || bits == 24 || bits == 32)) || (fmt == 3 && bits == 32))) {
            why = path + ": unsupported sample format";
            return false;
        }
        return true;
    }
    // frame f, channel c, as roomtail.read_wav reads it
    double at(long f, int c) const
    {
        const size_t i = (size_t)f * (size_t)ch + (size_t)c;
        if (fmt == 3) {
            float v;
            memcpy(&v, data + 4 * i, 4);
            return (double)v;
        }
        if (bits == 32) {
            int32_t v;
            memcpy(&v, data + 4 * i, 4);
            return (double)v / 2147483647.0;
        }
        if (bits == 16) {
            int16_t v;
            memcpy(&v, data + 2 * i, 2);
            return (double)v / 32767.0;
        }
        const uint8_t *b = data + 3 * i;
        const uint32_t v = ((uint32_t)b[0] << 8) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 24);
        return (double)(int32_t)v / 2147483647.0;
    }
};

// ---- THE OUTPUT (roomtail.write_wav: clipped, 32-bit over full scale) ----
struct Out {
    FILE *f = nullptr;
    ~Out()
    {
        if (f)
            fclose(f);
    }
    long frames = 0;
    int ch = 2, sr = 48000;
    std::vector<int32_t> buf;
    bool open(const std::string &path, int c, int rate)
    {
        f = fopen(path.c_str(), "wb");
        if (!f)
            return false;
        ch = c;
        sr = rate;
        frames = 0;                             // (a second pass writes the file again)
        buf.clear();
        uint8_t h[44] = {0};
        fwrite(h, 1, 44, f);                    // (sizes filled in at the close)
        return true;
    }
    void put(const double *v)                   // one frame
    {
        for (int c = 0; c < ch; c++) {
            const double x = std::min(1.0, std::max(-1.0, v[c])) * 2147483647.0;
            buf.push_back((int32_t)x);          // (astype: toward zero)
        }
        frames++;
        if (buf.size() >= 1 << 16) {
            fwrite(buf.data(), 4, buf.size(), f);
            buf.clear();
        }
    }
    bool close()
    {
        if (!buf.empty())
            fwrite(buf.data(), 4, buf.size(), f);
        buf.clear();
        const uint32_t data = (uint32_t)((size_t)frames * (size_t)ch * 4);
        uint8_t h[44];
        auto u32 = [&](int o, uint32_t v) { memcpy(h + o, &v, 4); };
        auto u16 = [&](int o, uint16_t v) { memcpy(h + o, &v, 2); };
        memcpy(h, "RIFF", 4);
        u32(4, 36 + data);
        memcpy(h + 8, "WAVEfmt ", 8);
        u32(16, 16);
        u16(20, 1);
        u16(22, (uint16_t)ch);
        u32(24, (uint32_t)sr);
        u32(28, (uint32_t)(sr * ch * 4));
        u16(32, (uint16_t)(ch * 4));
        u16(34, 32);
        memcpy(h + 36, "data", 4);
        u32(40, data);
        fseek(f, 0, SEEK_SET);
        fwrite(h, 1, 44, f);
        const bool ok = ferror(f) == 0;
        fclose(f);
        f = nullptr;
        return ok;
    }
};

// ---- roomtail.overlap_add, in stream: one channel's convolution with h ----
struct Ola {
    long n = 0, block = 0, step = 0, total = 0, emitted = 0, seg = 0;
    std::vector<double> H, acc, ready;          // (ready: final samples not yet taken)
    size_t ready_at = 0;
    void init(const double *h, long nh, long stride, long nx)
    {
        n = nh;
        const double lg = std::ceil(std::log2((double)std::max(n, 2L)));
        block = 1L << ((long)lg + 2);
        step = block - n + 1;
        total = nx + n - 1;
        std::vector<double> hv((size_t)block, 0.0);
        for (long i = 0; i < n; i++)
            hv[(size_t)i] = h[(size_t)(i * stride)];
        H.resize(2 * ((size_t)block / 2 + 1));
        nv_pocket_rfft(hv.data(), (int)block, H.data());
        acc.assign((size_t)(n - 1), 0.0);
    }
    // the next segment (x from its start, nx samples of it at most step);
    // its first step samples (or fewer, at the end) become final
    template <class F> void next(F x, long nx)
    {
        const long i0 = seg * step;
        std::vector<double> s((size_t)block, 0.0), S(2 * ((size_t)block / 2 + 1)), y((size_t)block);
        const long m = std::min(step, nx - i0);
        for (long i = 0; i < m; i++)
            s[(size_t)i] = x(i0 + i);
        nv_pocket_rfft(s.data(), (int)block, S.data());
        // (numpy's complex product, as its SIMD loop forms it -- fused: the
        // plain formula differs in the last bit on 1861 of 4097)
        for (size_t k = 0; k < S.size(); k += 2) {
            const double ar = S[k], ai = S[k + 1], br = H[k], bi = H[k + 1];
            S[k] = std::fma(ar, br, -(ai * bi));
            S[k + 1] = std::fma(ar, bi, ai * br);
        }
        nv_pocket_irfft(S.data(), (int)block, y.data());
        // out[i:i+m] += y: the last segment's overlap, then this one's
        for (long j = 0; j < n - 1; j++)
            y[(size_t)j] = acc[(size_t)j] + y[(size_t)j];
        for (long j = n - 1; j < block; j++)
            y[(size_t)j] = 0.0 + y[(size_t)j];
        const long fin = std::min(step, total - i0);
        for (long j = 0; j < fin; j++)
            ready.push_back(y[(size_t)j]);
        for (long j = 0; j < n - 1; j++)
            acc[(size_t)j] = y[(size_t)(step + j)];
        seg++;
        emitted = i0 + fin;
    }
    // the input spent: the last overlap final, to the convolution's end
    void flush()
    {
        const long i0 = seg * step;
        for (long j = 0; j < n - 1 && i0 + j < total; j++)
            ready.push_back(acc[(size_t)j]);
        emitted = total;
    }
    long have() const { return (long)(ready.size() - ready_at); }
    double take()
    {
        const double v = ready[ready_at++];
        if (ready_at > (1u << 16) && ready_at * 2 > ready.size()) {
            ready.erase(ready.begin(), ready.begin() + (long)ready_at);
            ready_at = 0;
        }
        return v;
    }
};

static std::string opt(int argc, char **argv, const char *name, const std::string &dflt)
{
    const size_t n = strlen(name);
    for (int i = 1; i < argc; i++)
        if (!strncmp(argv[i], "--", 2) && !strncmp(argv[i] + 2, name, n) && argv[i][2 + n] == '=')
            return argv[i] + 3 + n;
    return dflt;
}

// (the room's IRs, freed on every way out)
struct IrGuard {
    double *ir = nullptr, *mir = nullptr;
    ~IrGuard()
    {
        if (ir)
            nv_room_tail_free(ir);
        if (mir)
            nv_room_tail_free(mir);
    }
};

static int run(int argc, char **argv)
{
    std::vector<std::string> pos;
    bool no_modes = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--no-modes"))
            no_modes = true;
        else if (strncmp(argv[i], "--", 2))
            pos.push_back(argv[i]);
    }
    if (pos.size() < 2) {
        fprintf(stderr, "usage: nvroomtail IN.wav OUT.wav [--export=PATH] [--seed=N] [--no-modes]\n");
        return 2;
    }
    const std::string inp = pos[0], outp = pos[1];
    if (atof(opt(argc, argv, "q", "2.0").c_str()) != 2.0) {
        fprintf(stderr, "nvroomtail: refused: --q other than 2.0 (roomtail.py's)\n");
        return 2;
    }
    const int seed = atoi(opt(argc, argv, "seed", "0").c_str());
    const char *home = getenv("HOME");
    const char *envx = getenv("TUNING_ROOM_EXPORT");
    const std::string xp = opt(argc, argv, "export", envx ? envx : std::string(home ? home : ".") + "/nvx/live.nvx");

    std::string why;
    Wav x;
    if (!x.open(inp, why)) {
        fprintf(stderr, "nvroomtail: %s\n", why.c_str());
        return 1;
    }
    if (x.ch != 2) {
        fprintf(stderr, "nvroomtail: refused: %d channels (stereo only)\n", x.ch);
        return 2;
    }
    const int sr = x.sr;
    const long nx = x.frames;
    const std::string base = inp.substr(0, inp.rfind('.') == std::string::npos ? inp.size() : inp.rfind('.'));

    // THE SIDECAR: the render's room, its directivity, its GS reverb, its send
    const char *troom = getenv("TUNING_ROOM");
    std::string room = troom && *troom ? troom : "hall";
    double tail_gain = 1.0, tail_time = 1.0, delay_fb = -1.0, side_send = NAN;
    double bq[9];
    int has_bq = 0;
    for (double &b : bq)
        b = NAN;
    sess::J side;
    const bool have_side = sess::load(base + ".room.json", side) && side.is(sess::J::OBJ);
    if (have_side) {
        if (const sess::J *r = side.get("room_name"); r && r->is(sess::J::STR) && !r->s.empty())
            room = r->s;
        if (const sess::J *g = side.get("tail_gain"))
            tail_gain = g->d(1.0);
        if (const sess::J *t = side.get("tail_time"))
            tail_time = t->d(1.0);
        if (const sess::J *d = side.get("delay_fb"); d && d->is(sess::J::NUM))
            delay_fb = d->d();
        if (const sess::J *bs = side.get("bands"); bs && bs->is(sess::J::ARR))
            for (const sess::J &b : bs->a) {
                const sess::J *hz = b.get("hz"), *q = b.get("q"), *e = b.get("energy");
                if (!hz || !q || !(e && e->d() > 0.0))
                    continue;
                for (int i = 0; i < 9; i++)
                    if (hz->d() == OCTAVES[i]) {
                        bq[i] = q->d();
                        has_bq = 1;
                    }
            }
        if (const sess::J *sd = side.get("send"); sd && sd->is(sess::J::OBJ) && !sd->o.empty()) {
            bool one = true;
            const double v0 = sd->o.begin()->second.d();
            for (const auto &kv : sd->o)
                one = one && kv.second.d() == v0;
            if (one)
                side_send = v0;
        }
    }

    // THE ROOM's SPEC, from the export
    std::vector<Room> rooms;
    std::vector<double> dev;
    if (!export_rooms(xp, rooms, dev)) {
        fprintf(stderr, "nvroomtail: no rooms in %s (a native_export.py --live export: --export=PATH)\n", xp.c_str());
        return 1;
    }
    const Room *rd = nullptr;
    for (const Room &r : rooms)
        if (r.name == room)
            rd = &r;
    if (!rd) {
        fprintf(stderr, "nvroomtail: the export has no room '%s'\n", room.c_str());
        return 1;
    }
    printf("== %s -> %s\n   room %s%s\n", inp.c_str(), outp.c_str(), room.c_str(), have_side ? " (the render's)" : "");
    const int kind = rd->spec.empty() || !rd->reflect ? -1 : (int)rd->spec[1];

    Out o;
    if (kind < 0) {                             // (outdoors, dry: no diffuse field -- the render's own images)
        printf("   %s: no diffuse field, no tail\n", room.c_str());
        if (!o.open(outp, 2, sr)) {
            fprintf(stderr, "nvroomtail: cannot write %s\n", outp.c_str());
            return 1;
        }
        double v[2];
        for (long f = 0; f < nx; f++) {
            v[0] = x.at(f, 0);
            v[1] = x.at(f, 1);
            o.put(v);
        }
        return o.close() ? 0 : 1;
    }
    if (kind != 0 && sr != 48000) {
        fprintf(stderr, "nvroomtail: refused: a device's tail (%s) at %d Hz (its filters are the export's 48 kHz)\n",
                room.c_str(), sr);
        return 2;
    }

    // THE IRs (live.room_irs's composition: roomtail.main's)
    std::vector<double> sp(rd->spec);
    nv_room_spec_scale(sp.data(), tail_time);
    IrGuard irs;
    double *&ir = irs.ir, *&mir = irs.mir;
    long n = kind == 0 ? nv_room_tail_ir(sp.data(), bq, has_bq, sr, seed, &ir)
                       : nv_room_tail_device(sp.data(), dev.data(), bq, has_bq, sr, &ir, tail_time, delay_fb);
    if (n <= 0) {
        fprintf(stderr, "nvroomtail: the room's tail could not be drawn (the export's rooms not this build's?)\n");
        return 1;
    }
    if (tail_gain != 1.0 || tail_time != 1.0) {
        for (long q = 0; q < 2 * n; q++)
            ir[q] = ir[q] * tail_gain;
        printf("   GS reverb: level x%.2f, time x%.2f\n", tail_gain, tail_time);
    }
    if (kind != 0)
        printf("   %s in the room's place%s\n", kind == 1 ? "plate" : kind == 2 ? "delay" : "pan_delay",
               delay_fb >= 0.0 ? (" (delay feedback " + std::to_string((int)delay_fb) + ")").c_str() : "");
    long nm = 0;
    int nmodes = 0;
    if (kind == 0) {
        nm = nv_room_tail_modes(sp.data(), bq, has_bq, sr, &mir, &nmodes);
        if (no_modes || !(nmodes > 0 && sp[6] > 25.0 && nm > 0)) {
            if (nmodes > 0)
                printf("   %d modes %s\n", nmodes, no_modes ? "suppressed (--no-modes)" : "inaudible (Schroeder under 25 Hz)");
            nm = 0;
        } else {
            printf("   %d modes below %.0f Hz (Schroeder %.1f Hz) -- the room rings\n", nmodes, 2 * sp[6], sp[6]);
        }
    }
    const long ring = std::max(n - 1, nm > 0 ? nm - 1 : 0);
    const long total = nx + ring;
    printf("   IR %.2f s; music %.2f s + %.2f s of room = %.2f s\n", (double)n / sr, (double)nx / sr,
           (double)ring / sr, (double)total / sr);

    // WHAT FEEDS THE ROOM: the send bus, a uniform send, or the mix itself
    Wav send;
    const bool bus = access((base + ".send.wav").c_str(), R_OK) == 0;
    if (bus) {
        if (!send.open(base + ".send.wav", why) || send.ch != 2) {
            fprintf(stderr, "nvroomtail: the send bus: %s\n", why.empty() ? "not stereo" : why.c_str());
            return 1;
        }
        printf("   reverb send bus from %s.send.wav\n", base.substr(base.rfind('/') + 1).c_str());
    } else if (!std::isnan(side_send) && side_send != 1.0) {
        printf("   reverb send %.2f of nominal distance (CC91)\n", side_send);
    }
    auto wet = [&](long f, int c) {
        if (bus)
            return f < send.frames ? send.at(f, c) : 0.0;
        if (!std::isnan(side_send) && side_send != 1.0)
            return x.at(f, c) * side_send;
        return x.at(f, c);
    };

    // TWO PASSES AT MOST: written as it comes; a peak over full scale, again scaled
    double peak = 0.0, dpeak = 0.0, scale = 1.0;
    for (int pass = 0; pass < 2; pass++) {
        if (!o.open(outp, 2, sr)) {
            fprintf(stderr, "nvroomtail: cannot write %s\n", outp.c_str());
            return 1;
        }
        Ola yt[2], ym[2];
        for (int c = 0; c < 2; c++) {
            yt[c].init(ir + c, n, 2, nx);
            if (nm > 0)
                ym[c].init(mir + c, nm, 2, nx);
        }
        long f = 0;
        double pk = 0.0;
        // each output frame: x, then the tail's convolution, then the modes'
        // (roomtail: out[:len(x)] = x; out += y; out += modes)
        auto emit = [&](long upto) {
            for (; f < upto; f++) {
                double v[2];
                for (int c = 0; c < 2; c++) {
                    double s = f < nx ? x.at(f, c) : 0.0;
                    if (f < yt[c].total)
                        s = s + yt[c].take();
                    if (nm > 0 && f < ym[c].total)
                        s = s + ym[c].take();
                    if (pass == 0)
                        pk = std::max(pk, std::fabs(s));
                    v[c] = scale != 1.0 ? s / scale * 0.999 : s;
                }
                o.put(v);
            }
        };
        // each convolution advanced until its final samples reach the frame
        // to write (a segment at a time; the input spent, its last overlap)
        std::vector<Ola *> all;
        for (int c = 0; c < 2; c++) {
            all.push_back(&yt[c]);
            if (nm > 0)
                all.push_back(&ym[c]);
        }
        while (f < total) {
            long upto = total;
            for (size_t q = 0; q < all.size(); q++) {
                Ola *L = all[q];
                const int c = (int)(q / (nm > 0 ? 2 : 1));
                while (L->emitted <= f && L->emitted < L->total) {
                    if (L->seg * L->step < nx)
                        L->next([&](long i) { return wet(i, c); }, nx);
                    else
                        L->flush();
                }
                upto = std::min(upto, L->emitted >= L->total ? total : L->emitted);
            }
            emit(upto);
        }
        if (!o.close()) {
            fprintf(stderr, "nvroomtail: cannot write %s\n", outp.c_str());
            return 1;
        }
        if (pass == 0) {
            peak = pk;
            for (long g = 0; g < nx; g++)
                dpeak = std::max(dpeak, std::max(std::fabs(x.at(g, 0)), std::fabs(x.at(g, 1))));
            printf("   direct peak %.3f, with tail %.3f\n", dpeak, peak);
            if (peak <= 1.0)
                break;
            scale = peak;
            printf("   scaled by %.2f dB to fit; render %.1f dB quieter to keep the headroom in the mix instead\n",
                   -20 * log10(peak), 20 * log10(peak));
        }
    }
    printf("   written\n");
    return 0;
}

}  // namespace nvroomtail

// THE PROGRAM's WHOLE, as a library call (its arguments as the command line's, argv[0] its name)
extern "C" int nv_roomtail_main(int argc, char **argv) { return nvroomtail::run(argc, argv); }
