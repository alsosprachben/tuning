#!/usr/bin/env python3
"""Render coverage.md's data as the published coverage page.

    python3 examples/coverage_html.py [out.html]

The artifact at claude.ai is a rendering of exactly the data in
examples/gm_coverage.py, so it is generated from that rather than hand-written
-- which is the standing rule about build scripts, and is also the only way the
page and the table can be trusted to agree. The hand-written first version had
drifted: its map grid still showed GM 1, 2 and 3 as rating 1 with a rating-2
colour class, months after those voices were built.

The design (Spectral / IBM Plex, the 16x8 map, the rating ramp) is carried over
from that first version deliberately -- it is the page's identity, and a
regenerated page that looked different would read as a different document.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gm_coverage as C
import percussion_map as PM

SCALE = [
    ("nothing", "no voice at all"),
    ("general class", "a shared base, or another instrument standing in"),
    ("specific, theory", "its own voice, derived from how the instrument works"),
    ("specific, theory + ear", "...and the numbers moved after listening"),
    ("specific, reference audio", "...and fitted against a recording of the instrument"),
]

CSS = """
:root{
  --paper:#f6f7f9; --card:#ffffff; --ink:#161a1f; --ink-2:#39424d; --muted:#5c6672;
  --rule:#dfe3e8; --rule-2:#eceff3;
  --accent:#1d4e6f;
  --r0:#d7dce2; --r1:#b8bfc8; --r2:#7f9cb5; --r3:#3d6f8f; --r4:#a8742a;
  --warn:#8c3b26;
  --shadow:0 1px 2px rgba(22,26,31,.05), 0 8px 24px -16px rgba(22,26,31,.25);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#11151a; --card:#171c23; --ink:#e8ecf1; --ink-2:#c3cbd4; --muted:#8e99a6;
    --rule:#28313b; --rule-2:#1f272f;
    --accent:#6fa8cc;
    --r0:#2c343d; --r1:#48525d; --r2:#5b7f9c; --r3:#6fa8cc; --r4:#d09a44;
    --warn:#e0885f;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --paper:#11151a; --card:#171c23; --ink:#e8ecf1; --ink-2:#c3cbd4; --muted:#8e99a6;
  --rule:#28313b; --rule-2:#1f272f;
  --accent:#6fa8cc;
  --r0:#2c343d; --r1:#48525d; --r2:#5b7f9c; --r3:#6fa8cc; --r4:#d09a44;
  --warn:#e0885f;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.8);
}
*{box-sizing:border-box}
body{
  background:var(--paper); color:var(--ink);
  font-family:"IBM Plex Sans","Helvetica Neue",Arial,sans-serif;
  font-size:15px; line-height:1.55; margin:0;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px; margin:0 auto; padding:56px 28px 96px}
header{display:flex; flex-direction:column; gap:14px; margin-bottom:40px}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--muted);
}
h1{
  font-family:Spectral,Georgia,serif; font-weight:600; font-size:clamp(34px,5vw,50px);
  line-height:1.06; letter-spacing:-.015em; margin:0; text-wrap:balance;
}
.standfirst{
  font-family:Spectral,Georgia,serif; font-size:19px; line-height:1.6;
  color:var(--ink-2); max-width:62ch; margin:0;
}
.standfirst em{color:var(--ink)}
h2{
  font-family:Spectral,Georgia,serif; font-weight:600; font-size:26px;
  letter-spacing:-.01em; margin:0; text-wrap:balance;
}
section{margin-top:52px; display:flex; flex-direction:column; gap:18px}
p{margin:0; max-width:66ch; color:var(--ink-2)}

/* ---- the map: 16 families x 8 programs ---------------------------------- */
.map{
  background:var(--card); border:1px solid var(--rule); border-radius:4px;
  padding:26px 26px 22px; box-shadow:var(--shadow); overflow-x:auto;
}
.mapgrid{display:grid; grid-template-columns:132px repeat(8,1fr); gap:5px; min-width:640px}
.mapgrid .fam{
  font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--muted);
  display:flex; align-items:center; justify-content:flex-end; padding-right:10px;
  white-space:nowrap; letter-spacing:.01em;
}
.cell{
  aspect-ratio:1/1.08; border-radius:2px; position:relative; min-height:22px;
  display:flex; align-items:center; justify-content:center;
  font-family:"IBM Plex Mono",monospace; font-size:10px; color:#fff;
  opacity:.94;
}
.cell.r1,.cell.r0{color:var(--ink)}
.r0{background:var(--r0)} .r1{background:var(--r1)} .r2{background:var(--r2)}
.r3{background:var(--r3)} .r4{background:var(--r4)}
.cell.err::after{
  content:""; position:absolute; inset:2px; border:1.5px dashed var(--warn);
  border-radius:2px;
}
.maplegend{
  display:flex; flex-wrap:wrap; gap:18px; margin-top:20px; padding-top:16px;
  border-top:1px solid var(--rule-2);
}
.lg{display:flex; align-items:center; gap:7px; font-size:12.5px; color:var(--muted)}
.sw{width:13px; height:13px; border-radius:2px; flex:none}
.sw.err{border:1.5px dashed var(--warn); background:transparent}

/* ---- the proportion bar -------------------------------------------------- */
.bar{display:flex; height:34px; border-radius:3px; overflow:hidden; border:1px solid var(--rule)}
.bar span{
  display:flex; align-items:center; justify-content:center; color:#fff;
  font-family:"IBM Plex Mono",monospace; font-size:12px; font-weight:500;
}
.bar span.r1{color:var(--ink)}
.scalelist{list-style:none; padding:0; margin:0; display:grid; gap:1px;
  border:1px solid var(--rule); border-radius:4px; overflow:hidden; background:var(--rule)}
.scalelist li{
  background:var(--card); display:grid; grid-template-columns:38px 190px 1fr; gap:14px;
  align-items:baseline; padding:11px 16px;
}
.scalelist .n{
  font-family:"IBM Plex Mono",monospace; font-weight:500; font-size:15px;
  display:flex; align-items:center; gap:8px;
}
.scalelist .t{font-weight:600; color:var(--ink)}
.scalelist .d{color:var(--muted); font-size:13.5px}

/* ---- tables -------------------------------------------------------------- */
.fambox{border:1px solid var(--rule); border-radius:4px; background:var(--card); overflow:hidden}
.famhead{
  display:flex; align-items:baseline; justify-content:space-between; gap:16px;
  padding:14px 18px; border-bottom:1px solid var(--rule); flex-wrap:wrap;
}
.famhead h3{
  font-family:Spectral,Georgia,serif; font-weight:600; font-size:19px; margin:0;
}
.famhead .rng{font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--muted)}
.pips{display:flex; gap:3px}
.pip{width:11px; height:11px; border-radius:2px}
.tscroll{overflow-x:auto}
table{border-collapse:collapse; width:100%; min-width:620px}
td,th{text-align:left; padding:9px 18px; border-top:1px solid var(--rule-2); vertical-align:top}
tr:first-child td{border-top:none}
th{
  font-family:"IBM Plex Mono",monospace; font-size:10.5px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); font-weight:400; border-top:none;
  padding-top:11px; padding-bottom:9px;
}
td.num{font-family:"IBM Plex Mono",monospace; color:var(--muted); font-variant-numeric:tabular-nums; width:42px}
td.nm{font-weight:500; white-space:nowrap}
td.cls{font-family:"IBM Plex Mono",monospace; font-size:12.5px; color:var(--accent); white-space:nowrap}
td.rt{width:34px}
td.note{color:var(--muted); font-size:13.5px; min-width:260px}
.chip{
  display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:3px; color:#fff;
  font-family:"IBM Plex Mono",monospace; font-size:12px; font-weight:500;
}
.chip.r1,.chip.r0{color:var(--ink)}
.err-tag{color:var(--warn); font-weight:600}
footer{
  margin-top:64px; padding-top:20px; border-top:1px solid var(--rule);
  color:var(--muted); font-size:13px; max-width:70ch;
}
code{font-family:"IBM Plex Mono",monospace; font-size:.92em; color:var(--accent)}

.strip{display:flex; flex-wrap:wrap; gap:4px}
.scell{
  width:38px; border-radius:2px; padding:5px 0 4px; text-align:center;
  font-family:"IBM Plex Mono",monospace; font-size:9.5px; line-height:1.25; color:#fff;
}
.scell.r1,.scell.r0{color:var(--ink)}
.scell b{display:block; font-size:11px; font-weight:500}
.scell.err{outline:1.5px dashed var(--warn); outline-offset:-2px}
.kitnote{display:flex; gap:10px; align-items:flex-start; font-size:13.5px; color:var(--muted)}
@media (max-width:720px){
  .scalelist li{grid-template-columns:38px 1fr; }
  .scalelist .d{grid-column:2}
}
"""


def e(s):
    return html.escape(str(s), quote=True)


def cells():
    """The 16x8 map: every program, coloured by rating."""
    out = []
    for start, fam in C.FAMILY:
        out.append('<div class="fam">%s</div>' % e(fam))
        for p in range(start, start + 8):
            r, note = C.RATED[p]
            err = " err" if "CATEGORY ERROR" in note else ""
            out.append('<div class="cell r%d%s" title="%s %s &mdash; %s">%d</div>'
                       % (r, err, p, e(C.GM[p]), e(SCALE[r][0]), r))
    return "\n".join(out)


def families():
    """One box per family: the pips, then the table."""
    out = []
    for start, fam in C.FAMILY:
        pips = "\n".join('<span class="pip r%d"></span>' % C.RATED[p][0]
                          for p in range(start, start + 8))
        rows = []
        for p in range(start, start + 8):
            r, note = C.RATED[p]
            rows.append('<tr><td class="num">%d</td><td class="nm">%s</td>'
                        '<td class="cls">%s</td>'
                        '<td class="rt"><span class="chip r%d">%d</span></td>'
                        '<td class="note">%s</td></tr>'
                        % (p, e(C.GM[p]), e(C._class_name(p)), r, r, e(note)))
        out.append(
            '<section>\n<div class="fambox">\n'
            '<div class="famhead"><h3>%s</h3><span class="rng">%d&ndash;%d</span>'
            '<span class="pips">\n%s\n</span></div>\n'
            '<div class="tscroll"><table><tr><th></th><th>Patch</th><th>Class</th>'
            '<th></th><th>Notes</th></tr>\n%s\n</table></div></div>\n</section>'
            % (e(fam), start, start + 7, pips, "\n".join(rows)))
    return "\n".join(out)


def percussion():
    strip = []
    for n in sorted(C.PERC_RATED):
        r, note = C.PERC_RATED[n]
        name = PM.PERCUSSION[n][0]
        err = " err" if "CATEGORY ERROR" in note else ""
        strip.append('<div class="scell r%d%s" title="%s %s &mdash; %s"><b>%s</b>%d</div>'
                     % (r, err, n, e(name), e(SCALE[r][0]), n, r))
    return "\n".join(strip)


def build():
    hist = [0, 0, 0, 0, 0]
    for p in range(128):
        hist[C.RATED[p][0]] += 1
    bar = "\n".join('<span class="r%d" style="flex:%d">%d</span>' % (i, hist[i], hist[i])
                     for i in range(5) if hist[i])
    scale = "\n".join(
        '<li><span class="n"><span class="sw r%d"></span>%d</span>'
        '<span class="t">%s</span><span class="d">%s</span></li>'
        % (i, i, e(t), e(d)) for i, (t, d) in enumerate(SCALE))
    cat = [p for p in range(128) if "CATEGORY ERROR" in C.RATED[p][1]]
    ph = [0, 0, 0, 0, 0]
    for n in C.PERC_RATED:
        ph[C.PERC_RATED[n][0]] += 1

    return TEMPLATE % {
        "css": CSS,
        "cells": cells(),
        "bar": bar,
        "scale": scale,
        "families": families(),
        "perc": percussion(),
        "ncat": len(cat),
        "cats": ", ".join("%d %s" % (p, e(C.GM[p])) for p in cat),
        "n4": hist[4], "n3": hist[3], "n2": hist[2], "n1": hist[1],
        "pn4": ph[4], "pnperc": len(C.PERC_RATED),
    }


TEMPLATE = """<title>GM Patch Coverage</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
%(css)s
</style>

<div class="wrap">
<header>
<div class="eyebrow">Physically-modelled additive synthesiser &middot; General MIDI</div>
<h1>GM Patch Coverage</h1>
<p class="standfirst">All 128 programs, rated by <em>how much reality has been allowed to contradict the model</em> &mdash; from a shared base standing in, through a voice derived from how the instrument works, to one fitted against a recording of the thing itself.</p>
</header>

<section>
<h2>The whole set at once</h2>
<p>General MIDI&rsquo;s program list is exactly sixteen families of eight, so the whole of it fits in one grid. Each cell is a program, coloured by its rating; a dashed outline marks a patch played by a voice of the wrong physical kind. The rest of the specification is not a list of sounds but a list of behaviours &mdash; how many voices, which channel is percussion, which controllers must respond &mdash; and that half is documented in <code>midi.md</code> rather than here.</p>
<div class="map"><div class="mapgrid">
%(cells)s
</div>
<div class="legend">
<div class="lg"><span class="sw r1"></span>1 &nbsp;general class</div>
<div class="lg"><span class="sw r2"></span>2 &nbsp;specific, theory</div>
<div class="lg"><span class="sw r3"></span>3 &nbsp;specific, theory + ear</div>
<div class="lg"><span class="sw r4"></span>4 &nbsp;specific, reference audio</div>
<div class="lg"><span class="sw err"></span>wrong physical kind</div>
</div></div>
</section>

<section>
<h2>Where it stands</h2>
<div class="bar">
%(bar)s
</div>
<ul class="scalelist">
%(scale)s
</ul>
<p><strong>Nothing scores 0</strong>, because every program resolves to something &mdash; which is not the same as every program being served. The line that matters is the one at 4: audio of the instrument, analysed and fitted against. Published measurements that are not audio &mdash; the Rhodes&rsquo; high-speed-camera papers, the free reeds&rsquo; flow model &mdash; are better than theory, but they cannot contradict the model the way a recording can, so those voices sit at 2 and say why.</p>
<p><strong>The class column is what the ROUTER returns, not the program map.</strong> Several programs are a family routed per note &mdash; the bowed and pizzicato ensembles, the brass section, the solo winds whose bottom octave is a different instrument &mdash; and reading the program map instead reports the no-note fallback. That is how GM 61 came to be listed as a trombone standing in for a whole section long after it had been routed to trumpet, trombone and tuba sections.</p>
<p>Every one of the 128 programs now has a voice of its own kind; what remains is how much reality each has been allowed to contradict. The %(ncat)d patches on a voice of the wrong physical kind are %(cats)s.</p>
</section>

%(families)s

<section>
<h2>Channel 10: the percussion note map</h2>
<p>A separate specification from the 128 programs, and the place where the reference corpus divides most sharply. Iowa&rsquo;s percussion pages carry cymbals, crotales and hand percussion &mdash; and <strong>no drum kit at all</strong>: no snare, no bass drum, no toms, which is 9,630 of that collection&rsquo;s 12,781 percussion notes. %(pn4)d of the %(pnperc)d mapped notes are fitted against a recording.</p>
<div class="map">
<div class="strip">
%(perc)s
</div>
</div>
</section>

</div>
"""


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coverage.html")
    open(out, "w").write(build())
    print("  wrote %s (%d bytes)" % (out, os.path.getsize(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
