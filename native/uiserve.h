// uiserve.h -- nvlive --ui's server: the touch interface (ui/) over HTTP, and
// its calls (uiapi.cpp) over a WebSocket, on 127.0.0.1 only. One thread, a
// poll() loop over the listener and its few clients; every ~33 ms each
// WebSocket viewer is sent what changed (nv_ui_poll). Small and plain: GET
// for the files, the WebSocket's text frames for the calls, nothing else.
//
// A WebSocket is refused unless its Origin is this server's own page: a page
// from anywhere else open in the browser could otherwise drive the engine.
#ifndef NV_UISERVE_H
#define NV_UISERVE_H

#include <arpa/inet.h>
#include <cerrno>
#include <strings.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include "host.h"

namespace uiserve {

// ---- SHA-1 and base64: the WebSocket handshake's accept key (RFC 6455)
inline std::string sha1(const std::string &msg)
{
    uint32_t h0 = 0x67452301, h1 = 0xEFCDAB89, h2 = 0x98BADCFE, h3 = 0x10325476, h4 = 0xC3D2E1F0;
    std::string m = msg;
    const uint64_t bits = (uint64_t)msg.size() * 8;
    m += (char)0x80;
    while (m.size() % 64 != 56)
        m += (char)0;
    for (int i = 7; i >= 0; i--)
        m += (char)((bits >> (8 * i)) & 0xFF);
    auto rol = [](uint32_t x, int n) { return (x << n) | (x >> (32 - n)); };
    for (size_t c = 0; c < m.size(); c += 64) {
        uint32_t w[80];
        for (int i = 0; i < 16; i++)
            w[i] = (uint32_t)(uint8_t)m[c + 4 * i] << 24 | (uint32_t)(uint8_t)m[c + 4 * i + 1] << 16
                   | (uint32_t)(uint8_t)m[c + 4 * i + 2] << 8 | (uint32_t)(uint8_t)m[c + 4 * i + 3];
        for (int i = 16; i < 80; i++)
            w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        uint32_t a = h0, b = h1, cc = h2, d = h3, e = h4;
        for (int i = 0; i < 80; i++) {
            uint32_t f, k;
            if (i < 20) { f = (b & cc) | (~b & d); k = 0x5A827999; }
            else if (i < 40) { f = b ^ cc ^ d; k = 0x6ED9EBA1; }
            else if (i < 60) { f = (b & cc) | (b & d) | (cc & d); k = 0x8F1BBCDC; }
            else { f = b ^ cc ^ d; k = 0xCA62C1D6; }
            uint32_t t = rol(a, 5) + f + e + k + w[i];
            e = d; d = cc; cc = rol(b, 30); b = a; a = t;
        }
        h0 += a; h1 += b; h2 += cc; h3 += d; h4 += e;
    }
    std::string out;
    for (uint32_t v : {h0, h1, h2, h3, h4})
        for (int i = 3; i >= 0; i--)
            out += (char)((v >> (8 * i)) & 0xFF);
    return out;
}

inline std::string base64(const std::string &s)
{
    static const char *T = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string o;
    size_t i = 0;
    for (; i + 2 < s.size(); i += 3) {
        uint32_t v = (uint8_t)s[i] << 16 | (uint8_t)s[i + 1] << 8 | (uint8_t)s[i + 2];
        o += T[v >> 18]; o += T[(v >> 12) & 63]; o += T[(v >> 6) & 63]; o += T[v & 63];
    }
    if (i + 1 == s.size()) {
        uint32_t v = (uint8_t)s[i] << 16;
        o += T[v >> 18]; o += T[(v >> 12) & 63]; o += "==";
    } else if (i + 2 == s.size()) {
        uint32_t v = (uint8_t)s[i] << 16 | (uint8_t)s[i + 1] << 8;
        o += T[v >> 18]; o += T[(v >> 12) & 63]; o += T[(v >> 6) & 63]; o += '=';
    }
    return o;
}

inline bool send_all(int fd, const char *p, size_t n)
{
    while (n > 0) {
        ssize_t k = ::send(fd, p, n, MSG_NOSIGNAL);
        if (k < 0 && errno == EINTR)
            continue;
        if (k <= 0)
            return false;
        p += k;
        n -= (size_t)k;
    }
    return true;
}

// a header's value (case-blind name), "" none
inline std::string header(const std::string &req, const char *name)
{
    const size_t nl = strlen(name);
    size_t p = req.find("\r\n");
    while (p != std::string::npos && p + 2 < req.size()) {
        size_t e = req.find("\r\n", p + 2);
        std::string line = req.substr(p + 2, (e == std::string::npos ? req.size() : e) - p - 2);
        if (line.size() > nl && strncasecmp(line.c_str(), name, nl) == 0 && line[nl] == ':') {
            size_t v = nl + 1;
            while (v < line.size() && line[v] == ' ')
                v++;
            return line.substr(v);
        }
        p = e;
    }
    return "";
}

struct Client {
    int fd = -1;
    bool ws = false;
    std::string in;                 // bytes not yet a request or a frame
    nv_ui_watch *watch = nullptr;
};

struct Server {
    nv_host *h = nullptr;
    std::string root;               // ui/'s directory
    int port = 0, lfd = -1;
    std::vector<Client> cs;

    bool listen_on(int p)
    {
        lfd = ::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);   // (not handed to the browser it opens: a window left from a crash kept the port)
        if (lfd < 0)
            return false;
        int one = 1;
        setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
        sockaddr_in a{};
        a.sin_family = AF_INET;
        a.sin_port = htons((uint16_t)p);
        a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (::bind(lfd, (sockaddr *)&a, sizeof a) < 0 || ::listen(lfd, 8) < 0) {
            ::close(lfd);
            lfd = -1;
            return false;
        }
        port = p;
        return true;
    }

    static const char *mime(const std::string &path)
    {
        auto ends = [&](const char *e) {
            size_t n = strlen(e);
            return path.size() >= n && path.compare(path.size() - n, n, e) == 0;
        };
        if (ends(".html")) return "text/html; charset=utf-8";
        if (ends(".js")) return "text/javascript; charset=utf-8";
        if (ends(".css")) return "text/css; charset=utf-8";
        if (ends(".svg")) return "image/svg+xml";
        if (ends(".woff2")) return "font/woff2";
        if (ends(".ttf")) return "font/ttf";
        if (ends(".json")) return "application/json";
        if (ends(".png")) return "image/png";
        return "application/octet-stream";
    }

    void reply(int fd, const char *status, const char *type, const std::string &body)
    {
        char hd[256];
        snprintf(hd, sizeof hd,
                 "HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\nCache-Control: no-cache\r\n"
                 "Connection: close\r\n\r\n",
                 status, type, body.size());
        send_all(fd, hd, strlen(hd)) && send_all(fd, body.data(), body.size());
    }

    void send_text(Client &c, const std::string &s)
    {
        std::string f;
        f += (char)0x81;
        if (s.size() < 126) {
            f += (char)s.size();
        } else if (s.size() < 65536) {
            f += (char)126;
            f += (char)(s.size() >> 8);
            f += (char)(s.size() & 0xFF);
        } else {
            f += (char)127;
            for (int i = 7; i >= 0; i--)
                f += (char)(((uint64_t)s.size() >> (8 * i)) & 0xFF);
        }
        f += s;
        if (!send_all(c.fd, f.data(), f.size()))
            drop(c, ": send failed");
    }

    bool debug = getenv("NV_UI_DEBUG") != nullptr;
    void drop(Client &c, const char *why = "")
    {
        if (debug && c.fd >= 0)
            fprintf(stderr, "uiserve: fd %d closed (%s%s)\n", c.fd, c.ws ? "socket" : "http", why);
        if (c.fd >= 0)
            ::close(c.fd);
        c.fd = -1;
        if (c.watch)
            nv_ui_watch_free(c.watch);
        c.watch = nullptr;
    }

    // an HTTP request, whole: a file, or the WebSocket's handshake (true: kept open)
    bool http(Client &c, const std::string &req)
    {
        size_t sp = req.find(' '), sp2 = req.find(' ', sp + 1);
        if (sp == std::string::npos || sp2 == std::string::npos || req.compare(0, sp, "GET") != 0) {
            reply(c.fd, "405 Method Not Allowed", "text/plain", "GET only\n");
            return false;
        }
        std::string path = req.substr(sp + 1, sp2 - sp - 1);
        size_t qm = path.find('?');
        if (qm != std::string::npos)
            path = path.substr(0, qm);
        if (path == "/ws") {
            const std::string origin = header(req, "Origin"), key = header(req, "Sec-WebSocket-Key");
            const std::string mine1 = "http://127.0.0.1:" + std::to_string(port),
                              mine2 = "http://localhost:" + std::to_string(port);
            if (key.empty() || (origin != mine1 && origin != mine2)) {
                reply(c.fd, "403 Forbidden", "text/plain", "this server's own page only\n");
                return false;
            }
            const std::string acc = base64(sha1(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"));
            const std::string hs = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                                   "Sec-WebSocket-Accept: " + acc + "\r\n\r\n";
            if (!send_all(c.fd, hs.data(), hs.size()))
                return false;
            c.ws = true;
            c.watch = nv_ui_watch_new();
            return true;
        }
        if (path == "/")
            path = "/index.html";
        if (path.find("..") != std::string::npos || path.find("//") != std::string::npos) {
            reply(c.fd, "404 Not Found", "text/plain", "no\n");
            return false;
        }
        std::string body;
        if (FILE *f = fopen((root + path).c_str(), "rb")) {
            char b[65536];
            size_t n;
            while ((n = fread(b, 1, sizeof b, f)) > 0)
                body.append(b, n);
            fclose(f);
            reply(c.fd, "200 OK", mime(path), body);
        } else {
            reply(c.fd, "404 Not Found", "text/plain", "not found\n");
        }
        return false;
    }

    // the WebSocket's frames in c.in, each text frame a call
    void frames(Client &c)
    {
        while (c.fd >= 0 && c.in.size() >= 2) {
            const uint8_t b0 = (uint8_t)c.in[0], b1 = (uint8_t)c.in[1];
            const int op = b0 & 0x0F;
            uint64_t len = b1 & 0x7F;
            size_t at = 2;
            if (len == 126) {
                if (c.in.size() < 4)
                    return;
                len = (uint64_t)(uint8_t)c.in[2] << 8 | (uint8_t)c.in[3];
                at = 4;
            } else if (len == 127) {
                if (c.in.size() < 10)
                    return;
                len = 0;
                for (int i = 0; i < 8; i++)
                    len = len << 8 | (uint8_t)c.in[2 + i];
                at = 10;
            }
            if (len > (1u << 20)) {             // (a call is small: something else)
                drop(c);
                return;
            }
            const bool masked = b1 & 0x80;
            if (c.in.size() < at + (masked ? 4 : 0) + len)
                return;
            std::string pay = c.in.substr(at + (masked ? 4 : 0), (size_t)len);
            if (masked)
                for (size_t i = 0; i < pay.size(); i++)
                    pay[i] ^= c.in[at + (i & 3)];
            c.in.erase(0, at + (masked ? 4 : 0) + (size_t)len);
            if (op == 0x8) {                        // close
                drop(c, ": the viewer closed it");
                return;
            }
            if (op == 0x9) {                        // ping: pong
                std::string f;
                f += (char)0x8A;
                f += (char)pay.size();
                f += pay;
                send_all(c.fd, f.data(), f.size());
            } else if (op == 0x1) {
                char *ans = nv_ui_call(h, c.watch, pay.c_str());
                send_text(c, ans);
                nv_ui_free(ans);
            }
        }
    }

    void run(std::atomic<bool> &stop)
    {
        auto next = std::chrono::steady_clock::now();
        while (!stop) {
            std::vector<pollfd> pf;
            pf.push_back({lfd, POLLIN, 0});
            for (auto &c : cs)
                pf.push_back({c.fd, POLLIN, 0});
            const int wait = (int)std::max<long long>(
                0, std::chrono::duration_cast<std::chrono::milliseconds>(next - std::chrono::steady_clock::now()).count());
            int n = ::poll(pf.data(), pf.size(), std::min(wait, 100));
            if (n > 0 && (pf[0].revents & POLLIN)) {
                int fd = ::accept4(lfd, nullptr, nullptr, SOCK_CLOEXEC);
                if (fd >= 0) {
                    Client c;
                    c.fd = fd;
                    cs.push_back(c);
                }
            }
            for (size_t i = 1; n > 0 && i < pf.size(); i++) {
                if (!(pf[i].revents & (POLLIN | POLLHUP | POLLERR)))
                    continue;
                Client &c = cs[i - 1];
                char b[65536];
                ssize_t k = ::recv(c.fd, b, sizeof b, 0);
                if (k <= 0) {
                    drop(c, k == 0 ? ": the viewer hung up" : ": recv failed");
                    continue;
                }
                c.in.append(b, (size_t)k);
                if (c.ws) {
                    frames(c);
                } else if (c.in.find("\r\n\r\n") != std::string::npos) {
                    std::string req = c.in.substr(0, c.in.find("\r\n\r\n") + 2);
                    c.in.clear();
                    if (!http(c, req))
                        drop(c);
                } else if (c.in.size() > 16384) {
                    drop(c);
                }
            }
            // WHAT CHANGED, to each viewer
            if (std::chrono::steady_clock::now() >= next) {
                next += std::chrono::milliseconds(33);
                if (std::chrono::steady_clock::now() > next)
                    next = std::chrono::steady_clock::now() + std::chrono::milliseconds(33);
                for (auto &c : cs)
                    if (c.ws && c.fd >= 0) {
                        if (char *u = nv_ui_poll(h, c.watch)) {
                            send_text(c, u);
                            nv_ui_free(u);
                        }
                    }
            }
            std::vector<Client> keep;
            for (auto &c : cs)
                if (c.fd >= 0)
                    keep.push_back(c);
            cs.swap(keep);
        }
        for (auto &c : cs)
            drop(c);
        if (lfd >= 0)
            ::close(lfd);
    }
};

}  // namespace uiserve

#endif
