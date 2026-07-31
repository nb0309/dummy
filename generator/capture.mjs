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
//   node capture.mjs --sc 3.3.2     same form sweep, plus the labels/instructions probe
//   node capture.mjs --sc 2.4.3     page-level sample + the focus-order Tab sweep
//   node capture.mjs --sc 2.4.4     page-level sample + the link-purpose/context probe
//   node capture.mjs --sc 2.4.6     page-level sample + the headings/labels rotor view
//   node capture.mjs --sc 1.3.2     page-level sample + the reading-order walk
//   node capture.mjs --sc 2.1.2     page-level sample + the keyboard-trap escape ladder
//   node capture.mjs --sc 3.2.1     page-level sample + the on-focus context probe
//   node capture.mjs --sc 3.2.2     page-level sample + the on-input context probe
//   node capture.mjs --sc 1.3.3     page-level sample + the sensory-characteristics probe
//   node capture.mjs --url https://example.com --max-pages 15   crawl a live site instead
//                                                                of local fixtures (same-origin
//                                                                BFS from the seed, repeatable,
//                                                                combinable with --dir)
//
// Paths given to --dir are relative to the repo root (the parent of generator/),
// which is also the static server root so the fixtures' ../../assets/* references
// resolve. --url targets are navigated to directly and never touch that server.

import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

import { startServer } from "./lib/server.js";
import { extractSamples } from "./lib/extract.js";
import { triggerErrors } from "./lib/interact.js";
import { buildRow, writeOutputs } from "./lib/rows.js";
import { discoverLinks, urlToFile } from "./lib/crawl.js";
import {
  injectVsr,
  elementTranscript,
  statusAnnouncementProbe,
  roleStateValueProbe,
  labelInstructionProbe,
  focusOrderProbe,
  linkPurposeProbe,
  headingLabelProbe,
  readingOrderProbe,
  keyboardTrapProbe,
  focusContextProbe,
  inputContextProbe,
  sensoryReferenceProbe,
} from "./lib/vsr.js";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, ".."); // generator/ -> repo root

// ---- tiny argv parser -------------------------------------------------------
function parseArgs(argv) {
  const opts = {
    dirs: [],
    urls: [],
    maxPages: 30,
    out: "dataset_generated",
    label: "inaccessible",
    noSr: false,
    sc: null,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--no-sr") opts.noSr = true;
    else if (a === "--dir") opts.dirs.push(argv[++i]);
    else if (a === "--url") opts.urls.push(argv[++i]);
    else if (a === "--max-pages") opts.maxPages = Number(argv[++i]);
    else if (a === "--out") opts.out = argv[++i];
    else if (a === "--label") opts.label = argv[++i];
    else if (a === "--sc") opts.sc = argv[++i];
  }
  // Default suites are the all-inaccessible defect fixtures (the --label default
  // is "inaccessible"). 4.1.3's and 4.1.2's pass fixtures live under their own
  // "pass" folders and are captured separately with --label accessible.
  // Only fall back to them when the caller gave neither --dir nor --url, so a
  // --url-only run doesn't silently also pull in the local fixture suites.
  if (opts.dirs.length === 0 && opts.urls.length === 0)
    opts.dirs = ["tests/SC 1.3.1", "tests/wcag 1.1.1", "tests/wcag 4.1.3/fail", "tests/wcag 4.1.2/fail"];
  return opts;
}

/** Build an encoded URL path for a fixture relative to the server root. */
function toUrlPath(relDir, file) {
  const segments = relDir.split(/[\\/]/).filter(Boolean).map(encodeURIComponent);
  segments.push(encodeURIComponent(file));
  return "/" + segments.join("/");
}

/**
 * Capture one page: navigate, extract samples, run the VSR probes, and push
 * one row per sample onto `rows`. Shared by the local --dir walk and the
 * --url crawl loop below -- everything past the initial page.goto() is
 * identical regardless of how the page was reached.
 *
 * `originFilter`, when given, discovers same-origin links right after the
 * initial navigation and before any probe runs -- several probes (2.1.2's
 * escape ladder, 3.2.1/3.2.2's context probes) deliberately mutate or
 * navigate the page, so link discovery has to happen before them or it would
 * miss links or read a torn-down page.
 *
 * @returns {Promise<{links: string[]}>}
 */
async function captureFile(page, { file, fileUrl, originFilter }, opts, rows) {
  await page.goto(fileUrl, { waitUntil: "load" });
  const links = originFilter ? await discoverLinks(page, originFilter) : [];

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
  // 2.4.3 focus-order sweep: page-level like the status probe, and gated on
  // the flag so no other suite changes. It only presses Tab -- no clicks, no
  // DOM mutation -- so it cannot disturb the transcripts read below.
  let focusOrder = null;
  // 2.4.4 link purpose: every link with what the reader announces, where it
  // goes, and the sentence/block/table headers around it. Read-only.
  let linkPurpose = null;
  // 2.4.6 rotor view: every heading, control and link with what the reader
  // announces for it. Page-level and read-only -- no interaction at all.
  let headingsLabels = null;
  // 1.3.2 reading order: the reader's own cursor walk with a position per
  // step, so reading order and visual order become comparable.
  let readingOrder = null;
  // 1.3.3 sensory references: candidate sensory phrases in the prose, resolved
  // against measured geometry and computed colour. Read-only, so it belongs here
  // with the others rather than in the post-transcript slot below.
  let sensoryReference = null;
  if (!opts.noSr) {
    await injectVsr(page);
    statusAnnouncement = await statusAnnouncementProbe(page);
    if (opts.sc === "2.4.3") focusOrder = await focusOrderProbe(page);
    if (opts.sc === "2.4.4") linkPurpose = await linkPurposeProbe(page);
    if (opts.sc === "2.4.6") headingsLabels = await headingLabelProbe(page);
    if (opts.sc === "1.3.2") readingOrder = await readingOrderProbe(page);
    if (opts.sc === "1.3.3") sensoryReference = await sensoryReferenceProbe(page);
  }

  // 3. per-sample evidence. Buffered rather than turned into rows here,
  //    because the 2.1.2 probe below has to run AFTER every transcript is
  //    read: it presses Escape, which legitimately closes a dialog, so a
  //    transcript read after it would describe a different page. Every other
  //    page-level probe is read-only and stays above, where it was.
  const pending = [];
  for (const s of samples) {
    const transcript = opts.noSr ? [] : await elementTranscript(page, s.elementId);
    // 4.1.2 interaction probe: only for samples extract.js classified as a
    // role/state/value control (checkbox/switch/slider/etc). Cheap on every
    // other sample since it's simply skipped.
    const roleStateValue =
      !opts.noSr && s.elementType === "control"
        ? await roleStateValueProbe(page, s.elementId)
        : null;
    // 3.3.2 labels/instructions probe: form rows only, and only under
    // --sc 3.3.2. Gating on the flag rather than just the element type keeps
    // 3.3.1 captures byte-identical -- that pass has already submitted the
    // form, and typing into it afterwards would muddy its evidence.
    const labelInstruction =
      !opts.noSr && opts.sc === "3.3.2" && s.elementType === "form"
        ? await labelInstructionProbe(page, s.elementId)
        : null;
    pending.push({ sample: s, transcript, roleStateValue, labelInstruction });
  }

  // 4. The page-level probes that CHANGE the page, which is why they sit here
  //    rather than beside the read-only ones in step 2:
  //    - 2.1.2's escape ladder presses Escape, which closes a dialog;
  //    - 3.2.1's on-focus probe and 3.2.2's on-input probe both change the
  //      page by design, and may re-load the fixture when an interaction
  //      navigates away.
  //    Either would leave the transcripts above describing a different page.
  //    Both are --sc gated, so at most one runs per capture.
  const keyboardTrap =
    !opts.noSr && opts.sc === "2.1.2" ? await keyboardTrapProbe(page) : null;
  const focusContext =
    !opts.noSr && opts.sc === "3.2.1"
      ? await focusContextProbe(page, { url: fileUrl })
      : null;
  const inputContext =
    !opts.noSr && opts.sc === "3.2.2"
      ? await inputContextProbe(page, { url: fileUrl })
      : null;

  // 5. assemble one row per element
  for (const p of pending) {
    rows.push(
      buildRow({
        file,
        sample: p.sample,
        transcript: p.transcript,
        statusAnnouncement,
        roleStateValue: p.roleStateValue,
        labelInstruction: p.labelInstruction,
        focusOrder,
        linkPurpose,
        headingsLabels,
        readingOrder,
        keyboardTrap,
        focusContext,
        inputContext,
        sensoryReference,
        meta: { label: opts.label },
      })
    );
  }

  console.log(
    `${file}: ${samples.length} sample(s) [${samples.map((s) => s.elementType).join(", ")}]`
  );
  return { links };
}

const opts = parseArgs(process.argv.slice(2));

// Resolve each local suite's files up front.
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
if (suites.length === 0 && opts.urls.length === 0) {
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
      const fileUrl = `${server.url}${toUrlPath(dir, file)}`;
      await captureFile(page, { file, fileUrl }, opts, rows);
    }
  }

  // --url: same-origin BFS crawl from each seed, capped at --max-pages.
  // Bypasses the local static server entirely -- these are live, external
  // pages navigated to directly.
  for (const seedUrl of opts.urls) {
    await page.goto(seedUrl, { waitUntil: "load" }); // resolve redirects once
    const originFilter = new URL(page.url()).origin;
    const visited = new Set();
    const queue = [page.url()];
    let count = 0;
    while (queue.length && count < opts.maxPages) {
      const current = queue.shift();
      if (visited.has(current)) continue;
      visited.add(current);
      count++;
      const { links } = await captureFile(
        page,
        { file: urlToFile(current), fileUrl: current, originFilter },
        opts,
        rows
      );
      for (const link of links) {
        if (!visited.has(link) && !queue.includes(link)) queue.push(link);
      }
    }
    console.log(`crawl "${seedUrl}": ${count} page(s) captured (max ${opts.maxPages})`);
  }
} finally {
  await browser.close();
  await server.close();
}

const { jsonlPath, csvPath } = writeOutputs(rows, REPO_ROOT, opts.out);
console.log(`\nwrote ${rows.length} rows ->\n  ${jsonlPath}\n  ${csvPath}`);
