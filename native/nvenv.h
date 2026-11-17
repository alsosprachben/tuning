// THE ENGINE's SETTINGS FROM THE ENVIRONMENT (TUNING_*), read through one
// door: nv_env(name) -- the calling thread's own overrides first (a render
// running inside the app: nv_env_set), else the process's environment.
// iOS runs no helper programs, so a render the app starts runs on a thread
// of its own process; its mode and settings (TUNING_MAP, TUNING_MT32 ...) are
// that thread's, set there, never the process's (setenv beside threads
// reading it is a race, and the live engine reads them too).
#pragma once

#ifdef __cplusplus
extern "C" {
#endif
// the setting NAME as this thread sees it (nullptr: not set)
const char *nv_env(const char *name);
// THIS THREAD's overrides: n pairs (names[i], values[i]); a value nullptr
// unsets it for this thread. Replaces any earlier set; n = 0 clears them
void nv_env_set(const char *const *names, const char *const *values, int n);
#ifdef __cplusplus
}
#endif
