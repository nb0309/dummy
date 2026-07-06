// Scalable capture pass. Headless Chromium + @guidepup/virtual-screen-reader.
// For every HTML file in each --dir suite it captures, per element: HTML +
// parent context, computed a11y tree, axe results, and the virtual screen
// reader transcript — then writes <out>.jsonl + <out>.csv matching dataset.csv.
//
//   node capture.mjs
//   node capture.mjs --dir "tests/SC 1.3.1" --dir "tests/wcag 1.1.1"
//   node capture.mjs --out dataset_generated --sc auto --label inaccessible
//   node capture.mjs --no-sr        skip the screen reader (static features only)
//
// SC is inferred from the suite folder name (e.g. "SC 1.3.1" -> 1.3.1,
// "wcag 1.1.1" -> 1.1.1); with --sc auto and no folder match it falls back to
// per-filename-category inference in lib/rows.js. Paths are relative to the repo
// root (the parent of generator/), which is also the static server root so the
// fixtures' ../../assets/* references resolve.

import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";
import axe from "axe-core";

import { startServer } from "./lib/server.js";
import { extractSamples } from "./lib/extract.js";
import { ariaFor } from "./lib/aria.js";
import { runAxe } from "./lib/axe.js";
import { buildRow, writeOutputs } from "./lib/rows.js";
import { injectVsr, pageReadingOrder, elementTranscript } from "./lib/vsr.js";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, ".."); // generator/ -> repo root

// ---- tiny argv parser -------------------------------------------------------
function parseArgs(argv) {
  const opts = { dirs: [], out: "dataset_generated", sc: "auto", label: "inaccessible", noSr: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--no-sr") opts.noSr = true;
    else if (a === "--dir") opts.dirs.push(argv[++i]);
    else if (a === "--out") opts.out = argv[++i];
    else if (a === "--sc") opts.sc = argv[++i];
    else if (a === "--label") opts.label = argv[++i];
  }
  if (opts.dirs.length === 0) opts.dirs = ["tests/SC 1.3.1", "tests/wcag 1.1.1"];
  return opts;
}

/** Pull a WCAG success criterion (e.g. 1.3.1) out of a suite folder name. */
function scFromFolder(dir) {
  const m = path.basename(dir).match(/(\d+\.\d+\.\d+)/);
  return m ? m[1] : null;
}

/** Build an encoded URL path for a fixture relative to the server root. */
function toUrlPath(relDir, file) {
  const segments = relDir.split(/[\\/]/).filter(Boolean).map(encodeURIComponent);
  segments.push(encodeURIComponent(file));
  return "/" + segments.join("/");
}

const opts = parseArgs(process.argv.slice(2));

// Resolve each suite's files + effective SC up front.
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
  const suiteSc = opts.sc !== "auto" ? opts.sc : scFromFolder(dir) || "auto";
  suites.push({ dir, files, suiteSc });
  console.log(`suite "${dir}": ${files.length} file(s), wcag_sc=${suiteSc}`);
}
if (suites.length === 0) {
  console.error("No input suites found. Nothing to capture.");
  process.exit(1);
}

const server = await startServer(REPO_ROOT);
const browser = await chromium.launch();
const context = await browser.newContext();
const browserVersion = browser.version();
const page = await context.newPage();
const axeSource = axe.source;
const rows = [];

try {
  for (const { dir, files, suiteSc } of suites) {
    for (const file of files) {
      await page.goto(`${server.url}${toUrlPath(dir, file)}`, { waitUntil: "load" });

      // 1. DOM extraction (+ inject data-sample-id)
      const samples = await extractSamples(page);

      // 2. computed a11y tree per sample
      const ariaMap = {};
      for (const s of samples) ariaMap[s.elementId] = await ariaFor(page, s.elementId);

      // 3. axe-core (feature + weak second-opinion label)
      let axeResult = { version: "", violations: [] };
      try {
        axeResult = await runAxe(page, axeSource);
      } catch (e) {
        console.warn(`axe failed on ${file}: ${e.message}`);
      }

      // 4. virtual screen reader (page-level + per-element transcripts)
      let readingOrder = [];
      if (!opts.noSr) {
        await injectVsr(page);
        readingOrder = await pageReadingOrder(page);
      }

      // 5. assemble one row per element
      for (const s of samples) {
        const transcript = opts.noSr ? [] : await elementTranscript(page, s.elementId);
        const isTableLike = s.elementType === "table";
        const sr = {
          navCommands: opts.noSr
            ? "(no-sr: virtual reader skipped)"
            : "virtual-screen-reader: start(container=element) + next() to end",
          transcript,
          readingOrder,
          cellWalk: isTableLike ? transcript : null,
        };

        rows.push(
          buildRow({
            file,
            sample: s,
            aria: ariaMap[s.elementId],
            violations: axeResult.violations,
            sr,
            meta: {
              wcagSc: suiteSc,
              label: opts.label,
              sourceSuite: "GDS-accessibility-audit",
              capturedAt: new Date().toISOString(),
              nvdaVersion: null,
              nvdaLocale: opts.noSr ? null : "en",
              nvdaVerbosity: opts.noSr ? null : "virtual-default",
              browser: "chromium",
              browserVersion,
              axeVersion: axeResult.version || axe.version,
              captureMode: opts.noSr ? "no-sr" : "virtual-screen-reader",
            },
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
