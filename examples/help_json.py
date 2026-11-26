#!/usr/bin/env python3
"""ui/help.json for the native interface (nui/help.h): help_text.py's topics and
contents, the credits topic's terms from ui/credits.json (credits.py, by
examples/gm_coverage.py --about) -- a heading per group, then each source's
title and maker, its licence, what was done and for which voices.
    python3 examples/help_json.py [UI_DIR] [--strings]
native.build_nvlive runs it when help_text.py or credits.json is newer.

THE HELP IN OTHER LANGUAGES: for each ui/lang/help_<code>.json, ui/help.<code>.json --
the English help with each text the translation has put in its place. A
translation is {"topic/title": {"en": ..., "t": ...}, "topic/terms/3/1": ...,
"toc/2": ...}: the English it was made from is kept, and where help_text.py's
English has changed since, the text stays English (and --strings reports it
stale). A term that names a label (PART, VOICES) takes the interface's own
translation (ui/lang/<code>.json), so the help and the screen agree. The
credits stay as they are (names, titles, licences). --strings writes
ui/lang/help_strings.json, every text by its path, for translators."""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def credit_terms(cr):
    out, g = [], None
    for c in cr:
        if c.get("group") != g:
            g = c.get("group")
            out.append(g)
        how = c.get("how")
        out.append([("%s, %s" % (c["title"], c["author"])) if c.get("author") else c["title"],
                    "%s%s %s%s" % (c.get("licence", ""), (" · " + how + ":") if how else " ·", c.get("voices", ""),
                                   (" · " + c["url"]) if c.get("url") else "")])
    return out


def main(argv):
    import help_text as H
    ui = argv[1] if len(argv) > 1 else os.path.join(HERE, "ui")
    help_ = json.loads(json.dumps(H.HELP))
    try:
        help_["credits"]["terms"] = credit_terms(json.load(open(os.path.join(ui, "credits.json"))))
    except OSError:
        pass                                # (no credits.json: the topic says so by its intro alone)
    with open(os.path.join(ui, "help.json"), "w") as f:
        f.write(json.dumps({"help": help_, "toc": H.HELP_TOC}, ensure_ascii=False, separators=(",", ":")))
    print("help.json: %d topics, %d groups" % (len(help_), len(H.HELP_TOC)))
    texts = help_texts(help_, H.HELP_TOC)
    if "--strings" in argv:
        os.makedirs(os.path.join(ui, "lang"), exist_ok=True)
        with open(os.path.join(ui, "lang", "help_strings.json"), "w") as f:
            json.dump(texts, f, ensure_ascii=False, indent=0)
        print("help_strings.json: %d texts" % len(texts))
    import glob
    for tp in sorted(glob.glob(os.path.join(ui, "lang", "help_*.json"))):
        code = os.path.basename(tp)[5:-5]
        if code == "strings":
            continue
        tr = json.load(open(tp))
        try:
            ui_tab = json.load(open(os.path.join(ui, "lang", code + ".json")))
        except OSError:
            ui_tab = {}
        h2, toc2, used, stale = translated(help_, H.HELP_TOC, texts, tr, ui_tab)
        with open(os.path.join(ui, "help.%s.json" % code), "w") as f:
            f.write(json.dumps({"help": h2, "toc": toc2}, ensure_ascii=False, separators=(",", ":")))
        print("help.%s.json: %d of %d texts translated, %d stale" % (code, used, len(texts), len(stale)))
        if "--strings" in argv:
            for k in stale[:10]:
                print("  stale", k)
    return 0


def help_texts(help_, toc):
    """Every translatable text of the help by its path (the credits' terms are names: left out)."""
    out = {}
    for topic, t in help_.items():
        for f in ("title", "intro"):
            if t.get(f):
                out["%s/%s" % (topic, f)] = t[f]
        if topic == "credits":
            continue
        for i, term in enumerate(t.get("terms", [])):
            if isinstance(term, str):
                out["%s/terms/%d" % (topic, i)] = term
            else:
                for j, x in enumerate(term):
                    out["%s/terms/%d/%d" % (topic, i, j)] = x
    for name, topics in toc:            # (a group by its first topic: inserting one moves no other)
        out["toc/%s" % topics[0]] = name
    return out


def translated(help_, toc, texts, tr, ui_tab):
    """The help with the translation's texts in place; English where it has none or is stale."""
    h2 = json.loads(json.dumps(help_))
    toc2 = json.loads(json.dumps(toc))
    used, stale = 0, []
    for path, en in texts.items():
        e = tr.get(path)
        t = None
        if isinstance(e, dict) and e.get("t"):
            if e.get("en") == en:
                t = e["t"]
            else:
                stale.append(path)
        # (a term that names a label: the interface's own word)
        if path.endswith("/0") and "/terms/" in path and ui_tab.get(en):
            t = ui_tab[en]
        if t is None:
            continue
        used += 1
        parts = path.split("/")
        if parts[0] == "toc":
            key = "/".join(parts[1:])
            for g in toc2:
                if g[1] and g[1][0] == key:
                    g[0] = t
        elif len(parts) == 2:
            h2[parts[0]][parts[1]] = t
        elif len(parts) == 3:
            h2[parts[0]]["terms"][int(parts[2])] = t
        else:
            h2[parts[0]]["terms"][int(parts[2])][int(parts[3])] = t
    return h2, toc2, used, stale


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
