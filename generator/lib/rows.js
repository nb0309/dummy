// Shared dataset schema + row assembly. Keeping this in one place guarantees
// every capture pass emits identical columns.
//
// The model is trained/evaluated on only three inputs — the element's HTML, its
// parent's HTML, and the screen-reader transcript — plus a label and a
// sample_id/source_file for traceability. Everything else (ARIA tree, axe-core,
// structural counts, CSS signals, raw cell structure) has been removed.

import fs from "node:fs";
import path from "node:path";
import { normalizeHtml } from "./normalize.js";
import { toCsv } from "./csv.js";

// Column order for the flattened CSV view (nested fields are JSON-stringified).
// Provenance/label columns first, then the three feature columns.
export const COLUMNS = [
  // provenance / label
  "sample_id",
  "source_file",
  "label",
  // model inputs (features)
  "element_html",
  "parent_html",
  "sr_transcript",
];

/**
 * Assemble one dataset row.
 * @param {object} args
 * @param {string} args.file      source HTML filename (for sample_id/source_file)
 * @param {object} args.sample    a descriptor from extractSamples()
 * @param {object} args.meta      run metadata (label)
 * @param {string[]} args.transcript  the element-scoped screen-reader phrases
 */
export function buildRow({ file, sample, meta, transcript }) {
  return {
    sample_id: `${path.basename(file, ".html")}::${sample.elementId}`,
    source_file: path.basename(file),
    label: meta.label || "inaccessible",

    element_html: normalizeHtml(sample.elementHtmlRaw),
    parent_html: normalizeHtml(sample.parentHtml),
    sr_transcript: transcript || [],
  };
}

/** Write <base>.jsonl (lossless) + <base>.csv (flattened) as UTF-8. */
export function writeOutputs(rows, outDir, base = "dataset") {
  const jsonlPath = path.join(outDir, `${base}.jsonl`);
  const csvPath = path.join(outDir, `${base}.csv`);
  fs.writeFileSync(jsonlPath, rows.map((r) => JSON.stringify(r)).join("\n") + "\n", "utf8");
  // Prefix the CSV with a UTF-8 BOM so Excel on Windows renders £ / curly quotes
  // correctly. JSONL gets no BOM (consumers don't want one).
  fs.writeFileSync(csvPath, "﻿" + toCsv(rows, COLUMNS), "utf8");
  return { jsonlPath, csvPath };
}
