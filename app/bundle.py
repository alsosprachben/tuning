#!/usr/bin/env python3
"""A self-contained Clavitone.app: python3 app/bundle.py [--out=DIR] [--no-exports]

Built from the repo as it stands (run on the Mac, after native.py has built
the engine and the exports are made -- ~/nvx/live.nvx, ~/nvx/file.nvx):

  the app        the native interface (2026-11-26; the SwiftUI app's
                 panels retired): MacOS/Clavitone is native.py's
                 build_mac_app -- nvlive --app-windowed behind app/mac/main.mm
                 -- its Info.plist written here, DIR/Clavitone.app (default
                 app/dist); ui/ (fonts, help, the library's words, the
                 default presets) in Resources
  Frameworks     the engine's libraries (libnative and the kernels, every
                 *.so the repo holds) and libomp, each one's links rewritten
                 to @rpath, found beside one another (@loader_path) -- the
                 engine takes a library its export records from beside
                 libnative (native/relocate.h), so the bundle never loads the
                 repo's
  MacOS          the helpers beside the app: nvlive (Render, as you hear it),
                 nvrender and nvroomtail (best quality)
  Resources      the GPU kernel's sources (gpukernel.metal, gpukernel.cl,
                 voicedesc.h) and the exports (cloned on APFS: no second copy
                 on disk; --no-exports: none, the app then reads ~/nvx)

Every link checked (nothing from Homebrew or the repo left), everything
signed ad hoc, and the bundled helpers run once from the bundle -- a short
render and its room -- with dyld's list of what they loaded checked against
the repo. Exits 1 if anything is wrong.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# (the Mac app's: its program, its name, a music app, Apple silicon and macOS 15 on)
INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>Clavitone</string>
  <key>CFBundleIdentifier</key><string>com.clavitone.app</string>
  <key>CFBundleName</key><string>Clavitone</string>
  <key>CFBundleDisplayName</key><string>Clavitone</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleIconFile</key><string>Clavitone</string>
  <key>LSMinimumSystemVersion</key><string>15.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.music</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSSupportsAutomaticGraphicsSwitching</key><true/>
</dict>
</plist>
"""
REPO = os.path.dirname(HERE)
HELPERS = ("nvlive", "nvrender", "nvroomtail")
KERNELS = ("gpukernel.metal", "gpukernel.cl", "voicedesc.h")
EXPORTS = (("live.nvx", "~/nvx/live.nvx"), ("file.nvx", "~/nvx/file.nvx"))


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def links(path):
    """the libraries path links (otool -L), its own id left out"""
    out = run(["otool", "-L", path]).splitlines()[1:]
    got = [ln.strip().split(" (")[0] for ln in out]
    return [g for g in got if not g.endswith("/" + os.path.basename(path)) and g != "@rpath/" + os.path.basename(path)]


def rpaths(path):
    out = run(["otool", "-l", path])
    return re.findall(r"cmd LC_RPATH\n\s+cmdsize \d+\n\s+path (\S+)", out)


def fix_rpaths(path, want):
    """path's run paths made exactly `want`: the others deleted (the repo's,
    an absolute one), each wanted added once"""
    for r in rpaths(path):
        if r not in want:
            subprocess.run(["install_name_tool", "-delete_rpath", r, path], check=True, capture_output=True)
    have = rpaths(path)
    for r in want:
        if r not in have:
            subprocess.run(["install_name_tool", "-add_rpath", r, path], check=True, capture_output=True)


def main(argv):
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--out=")), os.path.join(HERE, "dist"))
    bad = []

    # THE APP: the native interface's program, the bundle around it
    print("== the native interface (native.py build_mac_app)", flush=True)
    sys.path.insert(0, REPO)
    import native
    native.lib()
    for b in ("build_nvlive", "build_nvrender", "build_nvroomtail"):
        if hasattr(native, b):
            getattr(native, b)()
    prog = native.build_mac_app()
    app = os.path.join(out, "Clavitone.app")
    os.makedirs(out, exist_ok=True)
    if os.path.exists(app):
        shutil.rmtree(app)
    C = os.path.join(app, "Contents")
    fw, mac, res = os.path.join(C, "Frameworks"), os.path.join(C, "MacOS"), os.path.join(C, "Resources")
    for d in (fw, mac, res):
        os.makedirs(d, exist_ok=True)
    shutil.copy2(prog, os.path.join(mac, "Clavitone"))
    with open(os.path.join(C, "Info.plist"), "w") as fh:
        fh.write(INFO_PLIST)
    # (ui/: the interface's fonts, its help, the library's words; the default presets)
    shutil.copytree(os.path.join(REPO, "ui"), os.path.join(res, "ui"),
                    ignore=shutil.ignore_patterns("presets.json", "scenes.json", "*.tmp"))
    icon = os.path.join(REPO, "ios", "Assets.xcassets", "AppIcon.appiconset", "AppIcon-1024.png")
    if os.path.exists(icon):                # (the iPad's icon, as the Mac's .icns)
        iset = tempfile.mkdtemp(prefix="icon") + "/Clavitone.iconset"
        os.makedirs(iset)
        for sz in (16, 32, 128, 256, 512):
            for sc in (1, 2):
                run(["sips", "-z", str(sz * sc), str(sz * sc), icon, "--out",
                     os.path.join(iset, "icon_%dx%d%s.png" % (sz, sz, "@2x" if sc == 2 else ""))])
        run(["iconutil", "-c", "icns", iset, "-o", os.path.join(res, "Clavitone.icns")])

    # FRAMEWORKS: the engine's libraries and libomp
    libs = sorted(glob.glob(os.path.join(REPO, "*.so")))
    if not any(os.path.basename(p) == "libnative.so" for p in libs):
        print("no libnative.so in %s: build the engine first (native.py)" % REPO)
        return 1
    omp = None
    for p in libs:
        shutil.copy2(p, os.path.join(fw, os.path.basename(p)))
        for ln in links(p):
            if ln.endswith("/libomp.dylib") and not ln.startswith("@"):
                omp = ln
    if omp:
        shutil.copy2(os.path.realpath(omp), os.path.join(fw, "libomp.dylib"))
        os.chmod(os.path.join(fw, "libomp.dylib"), 0o755)
        run(["install_name_tool", "-id", "@rpath/libomp.dylib", os.path.join(fw, "libomp.dylib")])
    for p in glob.glob(os.path.join(fw, "*.so")):
        if omp:
            run(["install_name_tool", "-change", omp, "@rpath/libomp.dylib", p])
        fix_rpaths(p, ["@loader_path"])
    print("   %d libraries%s" % (len(libs), " and libomp" if omp else ""))

    # MACOS: the app's executable and the helpers, their libraries in ../Frameworks
    exe = os.path.join(mac, "Clavitone")
    for p in [exe] + glob.glob(os.path.join(mac, "*.dylib")):
        fix_rpaths(p, ["@executable_path/../Frameworks"])
    for h in HELPERS:
        hp = os.path.join(REPO, h)
        if not os.path.exists(hp):
            bad.append("no %s in the repo (native.py build_%s)" % (h, h))
            continue
        shutil.copy2(hp, os.path.join(mac, h))
        fix_rpaths(os.path.join(mac, h), ["@executable_path/../Frameworks"])

    # THE DEFAULT PRESETS (ui/presets_default.json): beside libnative, where the
    # engine looks for them (hostsession.cpp's presets_default_path)
    os.makedirs(os.path.join(fw, "ui"), exist_ok=True)
    shutil.copy2(os.path.join(REPO, "ui", "presets_default.json"), os.path.join(fw, "ui", "presets_default.json"))

    # RESOURCES: the kernel's sources and the exports
    for k in KERNELS:
        shutil.copy2(os.path.join(REPO, k), os.path.join(res, k))
    if "--no-exports" not in argv:
        for name, where in EXPORTS:
            p = os.path.expanduser(where)
            if not os.path.exists(p):
                bad.append("no export %s (native_export.py)" % where)
                continue
            if os.path.getmtime(p) < os.path.getmtime(os.path.join(REPO, "libnative.so")) - 1:
                print("   (note: %s is older than libnative.so -- made with this build?)" % where)
            # (a clone on APFS: the bundle's copy takes no space until one of them changes)
            r = subprocess.run(["cp", "-c", p, os.path.join(res, name)], capture_output=True)
            if r.returncode:
                shutil.copy2(p, os.path.join(res, name))
        print("   exports in Resources")

    # NOTHING LEFT OUTSIDE: no link to Homebrew or the repo, no run path out of the bundle
    machos = ([exe] + glob.glob(os.path.join(mac, "*.dylib")) + [os.path.join(mac, h) for h in HELPERS]
              + glob.glob(os.path.join(fw, "*")))
    for p in machos:
        if not os.path.isfile(p):       # (Frameworks/ui is the default presets' folder)
            continue
        for ln in links(p):
            if not (ln.startswith("@rpath/") or ln.startswith("/usr/lib/") or ln.startswith("/System/")):
                bad.append("%s links %s" % (os.path.relpath(p, app), ln))
        for rp in rpaths(p):
            if not rp.startswith("@"):
                bad.append("%s searches %s" % (os.path.relpath(p, app), rp))

    # SIGNED (ad hoc: the rewrites broke the build's signatures)
    for p in [q for q in glob.glob(os.path.join(fw, "*")) if os.path.isfile(q)] + \
             [os.path.join(mac, h) for h in HELPERS if os.path.exists(os.path.join(mac, h))]:
        run(["codesign", "--force", "--sign", "-", p])
    run(["codesign", "--force", "--sign", "-", app])

    # RUN FROM THE BUNDLE: a short render and its room, dyld's list of what
    # they loaded checked for the repo's
    if "--no-exports" not in argv and os.path.exists(os.path.join(res, "file.nvx")):
        tmp = tempfile.mkdtemp(prefix="bundlechk")
        mid = os.path.join(REPO, "tests", "live", "midi", "chords3.mid")
        env = dict(os.environ, DYLD_PRINT_LIBRARIES="1")
        r1 = subprocess.run([os.path.join(mac, "nvrender"), os.path.join(res, "file.nvx"), mid, os.path.join(tmp, "c.wav"),
                             "--stream", "--gpu"], capture_output=True, text=True, env=env, cwd=tmp)
        r2 = subprocess.run([os.path.join(mac, "nvroomtail"), os.path.join(tmp, "c.wav"), os.path.join(tmp, "f.wav"),
                             "--export=" + os.path.join(res, "file.nvx")], capture_output=True, text=True, env=env, cwd=tmp)
        loaded = [ln for ln in (r1.stderr + r2.stderr).splitlines()
                  if "dyld" in ln and REPO in ln and os.path.realpath(app) not in ln and app not in ln]
        nlib = len([ln for ln in (r1.stderr + r2.stderr).splitlines() if "dyld" in ln and app in ln])
        if r1.returncode or r2.returncode or not os.path.exists(os.path.join(tmp, "f.wav")):
            bad.append("the bundled helpers failed: %s" % (r1.stderr + r2.stderr)[-600:])
        if loaded:
            bad.append("the bundle loaded the repo's: %s" % loaded[:3])
        print("   a render and its room from the bundle: %s (%d images loaded from it, none from the repo)"
              % ("ok" if not (r1.returncode or r2.returncode or loaded) else "FAILED", nlib))
        shutil.rmtree(tmp, ignore_errors=True)

    du = run(["du", "-sh", app]).split()[0]
    for b in bad:
        print("  !", b)
    print("%s: %s (%s)" % ("FAILED" if bad else "built", app, du))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
