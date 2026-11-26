#!/usr/bin/env python3
"""ui/help.json for the native interface (nui/help.h): help_text.py's topics and
contents, the credits topic's terms from ui/credits.json (credits.py, by
examples/gm_coverage.py --about) -- a heading per group, then each source's
title and maker, its licence, what was done and for which voices.
    python3 examples/help_json.py [UI_DIR]
native.build_nvlive runs it when help_text.py or credits.json is newer."""
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
