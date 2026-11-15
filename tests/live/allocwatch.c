// allocwatch.c -- what the audio thread allocates, block by block (Linux,
// glibc: LD_PRELOAD=allocwatch.so; tests/live/alloc_check.py builds and uses it).
//
// nv_host::render_block looks this library's nv_rt_alloc_watch up once and
// calls it around each block (1 on entry, 0 on exit); without the preload the
// lookup finds nothing and costs nothing. While a block runs, every malloc,
// calloc, realloc and aligned allocation on that thread is counted by its call
// stack, and blamed on whoever asked: the first frame above the C and C++
// runtimes -- the engine's own code (libnative, nvlive, the kernels), or a
// runtime it calls: OpenMP (libgomp's team for a parallel region, even of
// one thread: the GPU setup's), the GPU's driver (an event a launch, its
// command buffers). Only the engine's own are its to remove.
//
//   NV_ALLOCWATCH_OUT=FILE     the totals and every stack, most first (stderr if unset)
//   NV_ALLOCWATCH_BLOCKS=FILE  one line a block: the engine's own allocations in it
//   NV_ALLOCWATCH_FREES=1      the stacks of the frees instead of the allocations
#define _GNU_SOURCE
#include <dlfcn.h>
#include <execinfo.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern void *__libc_malloc(size_t), *__libc_calloc(size_t, size_t), *__libc_realloc(void *, size_t);
extern void *__libc_memalign(size_t, size_t);
extern void __libc_free(void *);

// (initial-exec: a dynamic TLS lookup can itself call free -- recursion)
#define TLS __thread __attribute__((tls_model("initial-exec")))
static TLS int on, inside;

#define NS 4096
#define DEP 10
static struct {
    uint64_t h;
    long n, bytes;
    void *st[DEP];
    int d, own;
} tab[NS];
static long blocks, total, frees, blk_any, blk_anyfree;
static long blk_alloc, blk_free, blk_own;
static int *per_blk;
static long per_cap;
static int want_frees = -1;

void nv_rt_alloc_watch(int w)
{
    if (want_frees < 0) {
        inside = 1;
        want_frees = getenv("NV_ALLOCWATCH_FREES") != 0;
        inside = 0;
    }
    if (w) {
        blocks++;
        blk_alloc = blk_free = blk_own = 0;
    } else if (on) {
        blk_any += blk_alloc > 0;
        blk_anyfree += blk_free > 0;
        inside = 1;
        if (blocks > per_cap) {
            per_cap = per_cap ? 2 * per_cap : 65536;
            per_blk = (int *)__libc_realloc(per_blk, per_cap * sizeof(int));
        }
        per_blk[blocks - 1] = (int)blk_own;
        inside = 0;
    }
    on = w;
}

// is this object the engine's own? (libnative, nvlive, the kernels' libsynth*)
static int engine(const char *path)
{
    const char *nm = strrchr(path, '/');
    nm = nm ? nm + 1 : path;
    return !strncmp(nm, "libnative", 9) || !strncmp(nm, "nvlive", 6) || !strncmp(nm, "nvalloc", 7)
           || !strncmp(nm, "libsynth", 8);
}
// ...or the runtime under everything (frames passed over to find who asked)
static int runtime(const char *path)
{
    return strstr(path, "libc.so") || strstr(path, "libstdc++") || strstr(path, "allocwatch") || strstr(path, "ld-linux");
}

// the call stack's entry (found or made); 1 if the engine's own code asked
static int record(size_t sz)
{
    void *st[DEP + 2];
    int d = backtrace(st, DEP + 2);
    uint64_t h = 1469598103934665603ULL;
    for (int i = 2; i < d; i++)
        h = (h ^ (uint64_t)st[i]) * 1099511628211ULL;
    unsigned k = h % NS;
    while (tab[k].n && tab[k].h != h)
        k = (k + 1) % NS;
    if (!tab[k].n) {
        tab[k].h = h;
        tab[k].d = d - 2;
        memcpy(tab[k].st, st + 2, sizeof(void *) * (d - 2));
        tab[k].own = 0;
        for (int i = 2; i < d; i++) {
            Dl_info di;
            if (!dladdr(st[i], &di) || !di.dli_fname) {
                break;                      // (an unnamed frame: a runtime's, not ours)
            }
            if (runtime(di.dli_fname))
                continue;
            tab[k].own = engine(di.dli_fname);
            break;
        }
    }
    tab[k].n++;
    tab[k].bytes += (long)sz;
    return tab[k].own;
}

static void note(size_t sz)
{
    if (!on || inside)
        return;
    inside = 1;
    total++;
    blk_alloc++;
    if (!want_frees && record(sz))
        blk_own++;
    inside = 0;
}

void *malloc(size_t n) { note(n); return __libc_malloc(n); }
void *calloc(size_t a, size_t b) { note(a * b); return __libc_calloc(a, b); }
void *realloc(void *p, size_t n) { note(n); return __libc_realloc(p, n); }
void *aligned_alloc(size_t al, size_t n) { note(n); return __libc_memalign(al, n); }
void *memalign(size_t al, size_t n) { note(n); return __libc_memalign(al, n); }
int posix_memalign(void **r, size_t al, size_t n)
{
    note(n);
    void *p = __libc_memalign(al, n);
    if (!p)
        return 12;                      // ENOMEM
    *r = p;
    return 0;
}
void free(void *p)
{
    if (on && !inside && p) {
        inside = 1;
        frees++;
        blk_free++;
        if (want_frees)
            record(0);
        inside = 0;
    }
    __libc_free(p);
}

static int by_count(const void *a, const void *b)
{
    long x = *(const long *)((const char *)a + sizeof(uint64_t)), y = *(const long *)((const char *)b + sizeof(uint64_t));
    return (y > x) - (y < x);
}

__attribute__((destructor)) static void dump(void)
{
    inside = 1;
    on = 0;
    const char *bp = getenv("NV_ALLOCWATCH_BLOCKS");
    if (bp) {
        FILE *b = fopen(bp, "w");
        if (b) {
            for (long i = 0; i < blocks && i < per_cap; i++)
                fprintf(b, "%d\n", per_blk[i]);
            fclose(b);
        }
    }
    const char *out = getenv("NV_ALLOCWATCH_OUT");
    FILE *f = out ? fopen(out, "w") : stderr;
    if (!f)
        return;
    fprintf(f, "blocks %ld allocs %ld frees %ld; blocks allocating %ld, freeing %ld\n", blocks, total, frees, blk_any,
            blk_anyfree);
    qsort(tab, NS, sizeof tab[0], by_count);
    for (int i = 0; i < NS && tab[i].n; i++) {
        fprintf(f, "== %ld %s %ld bytes%s\n", tab[i].n, want_frees ? "frees" : "allocs", tab[i].bytes,
                tab[i].own ? "" : " (a runtime's: OpenMP, the GPU's driver)");
        for (int j = 0; j < tab[i].d; j++) {
            Dl_info di;
            if (dladdr(tab[i].st[j], &di) && di.dli_fname) {
                const char *nm = strrchr(di.dli_fname, '/');
                fprintf(f, "   %s+0x%lx %s\n", nm ? nm + 1 : di.dli_fname,
                        (unsigned long)((char *)tab[i].st[j] - (char *)di.dli_fbase), di.dli_sname ? di.dli_sname : "?");
            }
        }
    }
    if (out)
        fclose(f);
}
