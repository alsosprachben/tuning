#!/usr/bin/env python3
"""The native UI's two libraries, fetched and built: SDL3 (zlib licence:
the window, touch, pen and graphics context on Linux, iOS, macOS, Windows)
and Dear ImGui (MIT: layout, text and input; every control drawn by us).
    python3 examples/third_party.py [fetch|build|all|ios]      (default all)
Each pinned to a release and its archive's SHA-256, downloaded into
third_party/downloads/ (git-ignored, as all of third_party/ but nothing of
ours is), unpacked into a fresh folder of its own. SDL3 built as a static
library for Linux, no audio, joystick, haptics, camera or
sensors -- the engine has its own audio and MIDI. Wayland natively (touch
and pen through its own protocols), X11 beside it (needs libwayland-dev,
libxkbcommon-dev, wayland-protocols, libdecor-0-dev, libegl-dev, libxss-dev,
libxtst-dev, libxi-dev). Installed into
third_party/sdl3-linux/ (include/, lib/libSDL3.a). On macOS the same, its
Cocoa window and OpenGL (Metal beside it), into third_party/sdl3-macos/."""
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TP = os.path.join(HERE, "third_party")
PINS = {
    "SDL3": ("https://github.com/libsdl-org/SDL/releases/download/release-3.4.20/SDL3-3.4.20.tar.gz",
             "f3bb06f55bed9557227a700af2ea62e49497ebdf58037732a731a5fb3ef8581f", "SDL3-3.4.20"),
    "imgui": ("https://github.com/ocornut/imgui/archive/refs/tags/v1.93.0.tar.gz",
              "f7bf6bc76e5d79d40d751096663e6c5d18daf08129dd52e7f7b09e4251c8eeee", "imgui-1.93.0"),
}


def fetch(name):
    url, sha, folder = PINS[name]
    dl = os.path.join(TP, "downloads")
    os.makedirs(dl, exist_ok=True)
    arc = os.path.join(dl, url.rsplit("/", 1)[1] if name != "imgui" else "imgui-v1.93.0.tar.gz")
    if not os.path.exists(arc):
        print("  fetching %s" % url)
        tmp = arc + ".part"
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, arc)
    got = hashlib.sha256(open(arc, "rb").read()).hexdigest()
    if got != sha:
        raise SystemExit("%s: SHA-256 %s, pinned %s -- not used" % (arc, got, sha))
    dest = os.path.join(TP, folder)
    if not os.path.isdir(dest):
        tmpd = dest + ".part"
        shutil.rmtree(tmpd, ignore_errors=True)
        os.makedirs(tmpd)
        with tarfile.open(arc) as t:
            t.extractall(tmpd, filter="data")
        inner = os.listdir(tmpd)
        os.replace(os.path.join(tmpd, inner[0]) if len(inner) == 1 else tmpd, dest)
        shutil.rmtree(tmpd, ignore_errors=True)
    print("  %s: %s" % (name, dest))
    return dest


def build_sdl3_linux():
    src = fetch("SDL3")
    prefix = os.path.join(TP, "sdl3-linux")
    if os.path.exists(os.path.join(prefix, "lib", "libSDL3.a")):
        print("  SDL3 built: %s" % prefix)
        return prefix
    bld = os.path.join(TP, "build-sdl3-linux")
    off = ["AUDIO", "JOYSTICK", "HAPTIC", "HIDAPI", "CAMERA", "SENSOR", "POWER", "TESTS", "EXAMPLES",
           "SHARED", "VULKAN", "KMSDRM", "DIALOG", "TRAY", "GPU"]
    cfg = ["cmake", "-S", src, "-B", bld, "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_INSTALL_PREFIX=" + prefix,
           "-DSDL_STATIC=ON", "-DSDL_WAYLAND=ON", "-DSDL_X11=ON", "-DSDL_X11_XINPUT=ON", "-DSDL_OPENGLES=ON", "-DSDL_OPENGL=ON",
           "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DSDL_X11_XSCRNSAVER=OFF"] + ["-DSDL_%s=OFF" % o for o in off]
    subprocess.check_call(cfg, stdout=subprocess.DEVNULL)
    subprocess.check_call(["cmake", "--build", bld, "-j", str(min(8, os.cpu_count() or 2))], stdout=subprocess.DEVNULL)
    subprocess.check_call(["cmake", "--install", bld], stdout=subprocess.DEVNULL)
    shutil.rmtree(bld, ignore_errors=True)
    print("  SDL3 built: %s" % prefix)
    return prefix


def build_sdl3_macos():
    """SDL3 for macOS (Part C's first step: the native UI in a Mac window
    before iOS): static, Cocoa, OpenGL and Metal, the same subsystems off."""
    src = fetch("SDL3")
    prefix = os.path.join(TP, "sdl3-macos")
    if os.path.exists(os.path.join(prefix, "lib", "libSDL3.a")):
        print("  SDL3 built: %s" % prefix)
        return prefix
    bld = os.path.join(TP, "build-sdl3-macos")
    off = ["AUDIO", "JOYSTICK", "HAPTIC", "HIDAPI", "CAMERA", "SENSOR", "POWER", "TESTS", "EXAMPLES",
           "SHARED", "VULKAN", "DIALOG", "TRAY", "GPU"]
    cfg = ["cmake", "-S", src, "-B", bld, "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_INSTALL_PREFIX=" + prefix,
           "-DSDL_STATIC=ON", "-DSDL_OPENGL=ON", "-DSDL_METAL=ON", "-DCMAKE_OSX_ARCHITECTURES=arm64",
           "-DCMAKE_POSITION_INDEPENDENT_CODE=ON"] + ["-DSDL_%s=OFF" % o for o in off]
    subprocess.check_call(cfg, stdout=subprocess.DEVNULL)
    subprocess.check_call(["cmake", "--build", bld, "-j", str(min(8, os.cpu_count() or 2))], stdout=subprocess.DEVNULL)
    subprocess.check_call(["cmake", "--install", bld], stdout=subprocess.DEVNULL)
    shutil.rmtree(bld, ignore_errors=True)
    print("  SDL3 built: %s" % prefix)
    return prefix


def build_sdl3_ios(sdk):
    """SDL3 for iOS (Part C): static, UIKit and Metal, arm64, iOS 17 and
    after -- the device's (iphoneos) or the simulator's (iphonesimulator) --
    into third_party/sdl3-ios-SDK/."""
    src = fetch("SDL3")
    prefix = os.path.join(TP, "sdl3-ios-" + sdk)
    if os.path.exists(os.path.join(prefix, "lib", "libSDL3.a")):
        print("  SDL3 built: %s" % prefix)
        return prefix
    bld = os.path.join(TP, "build-sdl3-ios-" + sdk)
    off = ["AUDIO", "JOYSTICK", "HAPTIC", "HIDAPI", "CAMERA", "SENSOR", "POWER", "TESTS", "EXAMPLES",
           "SHARED", "VULKAN", "DIALOG", "TRAY", "GPU", "OPENGLES"]
    cfg = ["cmake", "-S", src, "-B", bld, "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_INSTALL_PREFIX=" + prefix,
           "-DCMAKE_SYSTEM_NAME=iOS", "-DCMAKE_OSX_SYSROOT=" + sdk, "-DCMAKE_OSX_ARCHITECTURES=arm64",
           "-DCMAKE_OSX_DEPLOYMENT_TARGET=17.0", "-DSDL_STATIC=ON", "-DSDL_METAL=ON"] + ["-DSDL_%s=OFF" % o for o in off]
    subprocess.check_call(cfg, stdout=subprocess.DEVNULL)
    subprocess.check_call(["cmake", "--build", bld, "-j", str(min(8, os.cpu_count() or 2))], stdout=subprocess.DEVNULL)
    subprocess.check_call(["cmake", "--install", bld], stdout=subprocess.DEVNULL)
    shutil.rmtree(bld, ignore_errors=True)
    print("  SDL3 built: %s" % prefix)
    return prefix


def main(argv):
    what = argv[1] if len(argv) > 1 else "all"
    if what in ("fetch", "all"):
        for n in PINS:
            fetch(n)
    if what in ("build", "all"):
        build_sdl3_macos() if sys.platform == "darwin" else build_sdl3_linux()
    if what == "ios":                   # (on a Mac with Xcode: the device's and the simulator's)
        fetch("imgui")
        for sdk in ("iphoneos", "iphonesimulator"):
            build_sdl3_ios(sdk)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
