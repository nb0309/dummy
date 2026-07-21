// Scalable capture pass. Headless Chromium + @guidepup/virtual-screen-reader.
// For every HTML file in each --dir suite it captures, per sample element, only
// the three model inputs: element HTML, parent HTML, and the virtual
// screen-reader transcript — then writes <out>.jsonl + <out>.csv.
//
//   node capture.mjs
//   node capture.mjs --dir "tests/SC 1.3.1" --dir "tests/wcag 1.1.1"
//   node capture.mjs --out dataset_generated --label inaccessible
//   node capture.mjs --no-sr        skip the screen reader (HTML-only capture)
//   node capture.mjs --sc 3.3.1     opt into that criterion's extra sample sweep
//
// Paths are relative to the repo root (the parent of generator/), which is also
// the static server root so the fixtures' ../../assets/* references resolve.

import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

import { startServer } from "./lib/server.js";
import { extractSamples } from "./lib/extract.js";
import { triggerErrors } from "./lib/interact.js";
import { buildRow, writeOutputs } from "./lib/rows.js";
import { injectVsr, elementTranscript, statusAnnouncementProbe } from "./lib/vsr.js";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, ".."); // generator/ -> repo root

// ---- tiny argv parser -------------------------------------------------------
function parseArgs(argv) {
  const opts = { dirs: [], out: "dataset_generated", label: "inaccessible", noSr: false, sc: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--no-sr") opts.noSr = true;
    else if (a === "--dir") opts.dirs.push(argv[++i]);
    else if (a === "--out") opts.out = argv[++i];
    else if (a === "--label") opts.label = argv[++i];
    else if (a === "--sc") opts.sc = argv[++i];
  }
  // Default suites are the all-inaccessible defect fixtures (the --label default
  // is "inaccessible"). 4.1.3's pass fixtures live in "tests/wcag 4.1.3/pass"
  // and are captured separately with --label accessible.
  if (opts.dirs.length === 0)
    opts.dirs = ["tests/SC 1.3.1", "tests/wcag 1.1.1", "tests/wcag 4.1.3/fail"];
  return opts;
}

/** Build an encoded URL path for a fixture relative to the server root. */
function toUrlPath(relDir, file) {
  const segments = relDir.split(/[\\/]/).filter(Boolean).map(encodeURIComponent);
  segments.push(encodeURIComponent(file));
  return "/" + segments.join("/");
}

const opts = parseArgs(process.argv.slice(2));

// Resolve each suite's files up front.
const suites = [];
for (const dir of opts.dirs) {
  const abs = path.join(REPO_ROOT, dir);
  if (!fs.existsSync(abs)) {
    console.warn(`skip: input dir not found -> ${dir}`);
    continue;
  }
  const files = fs
    .readdirSync(abs)
    .filter((f) => f.toLowerCase().endsWith(".html"))
    .sort();
  suites.push({ dir, files });
  console.log(`suite "${dir}": ${files.length} file(s)`);
}
if (suites.length === 0) {
  console.error("No input suites found. Nothing to capture.");
  process.exit(1);
}

const server = await startServer(REPO_ROOT);
const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
const rows = [];

try {
  for (const { dir, files } of suites) {
    for (const file of files) {
      await page.goto(`${server.url}${toUrlPath(dir, file)}`, { waitUntil: "load" });

      // 0. Drive the page's own validation so an error state exists before we
      //    snapshot the DOM below. Self-gates on [data-error-trigger], so pages
      //    without it (every pre-3.3.1 suite) are untouched.
      await triggerErrors(page);

      // 1. DOM extraction (+ inject data-sample-id)
      const samples = await extractSamples(page, { sc: opts.sc });

      // 2. virtual screen reader (per-element transcripts)
      //    + the 4.1.3 interaction probe. The probe self-gates: it returns null
      //    unless the page carries a [data-status-target], so it is cheap on
      //    non-status pages and the page-level result can be stamped on each row.
      let statusAnnouncement = null;
      if (!opts.noSr) {
        await injectVsr(page);
        statusAnnouncement = await statusAnnouncementProbe(page);
      }

      // 3. assemble one row per element
      for (const s of samples) {
        const transcript = opts.noSr ? [] : await elementTranscript(page, s.elementId);
        rows.push(
          buildRow({
            file,
            sample: s,
            transcript,
            statusAnnouncement,
            meta: { label: opts.label },
          })
        );
      }

      console.log(
        `${file}: ${samples.length} sample(s) [${samples.map((s) => s.elementType).join(", ")}]`
      );
    }
  }
} finally {
  await browser.close();
  await server.close();
}

const { jsonlPath, csvPath } = writeOutputs(rows, REPO_ROOT, opts.out);
console.log(`\nwrote ${rows.length} rows ->\n  ${jsonlPath}\n  ${csvPath}`);
