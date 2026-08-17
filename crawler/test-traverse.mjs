// Smoke checks for traverse(): consecutive duplicate phrases on different nodes
// must not abort the walk, a stuck leaf must still stop, and hitting maxSteps
// without a wrap must warn.
//
//   node test-traverse.mjs

import { chromium } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import url from "node:url";

import { startServer } from "./lib/server.js";
import { injectVsr, traverse } from "./lib/vsr.js";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(HERE, "..");
const HEADINGS_FIXTURE = path.join(
  REPO_ROOT,
  "tests",
  "wcag 2.4.6",
  "fail",
  "duplicate-headings-across-sections.html"
);

const PAGES = {
  "duplicate-cells.html": `<!DOCTYPE html>
<html lang="en"><body>
<table>
  <tr><td>0</td><td>0</td><td>0</td><td>unique-cell</td></tr>
</table>
</body></html>`,

  "duplicate-links.html": `<!DOCTYPE html>
<html lang="en"><body>
<a href="/a">Read more</a>
<a href="/b">Read more</a>
<a href="/c">Read more</a>
<a href="/d">Contact us</a>
</body></html>`,

  "stuck-leaf.html": `<!DOCTYPE html>
<html lang="en"><body>
<button>Save</button>
</body></html>`,
};

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

function countMatching(phrases, re) {
  return phrases.filter((p) => re.test(p || "")).length;
}

async function phrasesFor(page, serverUrl, file, maxSteps = 250) {
  await page.goto(`${serverUrl}/${file}`, { waitUntil: "load" });
  await injectVsr(page);
  return traverse(page, { maxSteps });
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "traverse-"));
for (const [name, html] of Object.entries(PAGES)) {
  fs.writeFileSync(path.join(tmp, name), html);
}
fs.copyFileSync(HEADINGS_FIXTURE, path.join(tmp, "duplicate-headings.html"));

const warnings = [];
const origWarn = console.warn;
console.warn = (...args) => {
  warnings.push(args.map(String).join(" "));
  origWarn.apply(console, args);
};

const server = await startServer(tmp);
const browser = await chromium.launch();
const page = await browser.newPage();
let failed = 0;

try {
  {
    const phrases = await phrasesFor(page, server.url, "duplicate-cells.html");
    const zeros = countMatching(phrases, /\b0\b/);
    const unique = phrases.some((p) => /unique-cell/i.test(p || ""));
    assert(zeros >= 3, `duplicate cells: expected >= 3 "0" phrases, got ${zeros} in ${JSON.stringify(phrases)}`);
    assert(unique, `duplicate cells: walk cut off before unique-cell: ${JSON.stringify(phrases)}`);
    console.log("ok  duplicate cells continue past identical td values");
  }

  {
    const phrases = await phrasesFor(page, server.url, "duplicate-links.html");
    const readMore = countMatching(phrases, /read more/i);
    const contact = phrases.some((p) => /contact us/i.test(p || ""));
    assert(readMore >= 3, `duplicate links: expected >= 3 "Read more", got ${readMore} in ${JSON.stringify(phrases)}`);
    assert(contact, `duplicate links: walk cut off before Contact us: ${JSON.stringify(phrases)}`);
    console.log("ok  duplicate links continue past identical link names");
  }

  {
    const phrases = await phrasesFor(page, server.url, "duplicate-headings.html");
    const overviews = countMatching(phrases, /overview/i);
    const afterLast = phrases.some((p) => /attendance allowance/i.test(p || ""));
    assert(overviews >= 3, `duplicate headings: expected >= 3 Overview, got ${overviews} in ${JSON.stringify(phrases)}`);
    assert(afterLast, `duplicate headings: walk cut off before last section: ${JSON.stringify(phrases)}`);
    console.log("ok  duplicate headings reach content after the last Overview");
  }

  {
    warnings.length = 0;
    const t0 = Date.now();
    const phrases = await phrasesFor(page, server.url, "stuck-leaf.html", 80);
    const elapsed = Date.now() - t0;
    assert(phrases.length > 0, "stuck leaf: expected at least one phrase");
    assert(phrases.length < 10, `stuck leaf: expected a short transcript, got ${phrases.length} ${JSON.stringify(phrases)}`);
    assert(
      !warnings.some((w) => /truncated/i.test(w)),
      `stuck leaf: should stop via the node-keyed net, not maxSteps (${warnings.join(" | ")})`
    );
    assert(elapsed < 15000, `stuck leaf: still spinning after ${elapsed}ms`);
    console.log("ok  stuck leaf stops before maxSteps");
  }

  {
    warnings.length = 0;
    await phrasesFor(page, server.url, "duplicate-cells.html", 2);
    assert(
      warnings.some((w) => /sr_transcript truncated at maxSteps=2/.test(w)),
      `maxSteps cap: expected a truncation warning, got ${JSON.stringify(warnings)}`
    );
    console.log("ok  maxSteps without wrap logs a truncation warning");
  }
} catch (err) {
  failed = 1;
  console.error(err instanceof Error ? err.message : err);
} finally {
  console.warn = origWarn;
  await browser.close();
  await server.close();
  fs.rmSync(tmp, { recursive: true, force: true });
}

process.exit(failed);
