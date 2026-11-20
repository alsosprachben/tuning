// ui/help.js's topics as ui/help.json, for the native interface (nui/help.h):
// the web's help.js stays the source; native.build_nvlive runs this when
// help.js is newer. node examples/help_json.js [ui-dir]
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const dir = process.argv[2] || path.join(__dirname, '..', 'ui');
const src = fs.readFileSync(path.join(dir, 'help.js'), 'utf8');
// (the viewer's DOM work stubbed: only the tables are wanted)
const stub = new Proxy(function () {}, { get: () => stub, apply: () => stub, construct: () => stub });
const ctx = { document: { querySelectorAll: () => [], createElement: () => stub, body: stub }, MutationObserver: function () { return { observe() {} }; },
  requestAnimationFrame: () => 0, Kit: stub, esc: s => s, showCard: () => {} };
vm.createContext(ctx);
vm.runInContext(src + '\n;globalThis.__out = { help: HELP, toc: HELP_TOC }; globalThis.__creditTerms = creditTerms;', ctx);
const out = ctx.__out;
// (the credits topic's terms: credits.json's sources, by help.js's creditTerms)
try {
  const cr = JSON.parse(fs.readFileSync(path.join(dir, 'credits.json'), 'utf8'));
  out.help.credits.terms = ctx.__creditTerms(cr);
} catch (e) { /* no credits.json: the topic says so by its intro alone */ }
fs.writeFileSync(path.join(dir, 'help.json'), JSON.stringify(out));
console.log(`help.json: ${Object.keys(out.help).length} topics, ${out.toc.length} groups`);
