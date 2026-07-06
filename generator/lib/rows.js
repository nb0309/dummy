// Shared dataset schema + row assembly. Keeping this in one place guarantees
// every capture pass emits identical columns. Scalable across WCAG criteria: the
// success criterion and label are supplied per run/sample rather than hardcoded.

import fs from "node:fs";
import path from "node:path";
import { normalizeHtml } from "./normalize.js";
import { violationsForSample, isWcag131 } from "./axe.js";
import { toCsv } from "./csv.js";

// Filename prefix -> (category is informational; the SC below drives wcag_sc
// when the caller doesn't pass an explicit one).
const CATEGORY_SC = {
  // 1.1.1 non-text content
  images: "1.1.1",
  buttons: "1.1.1",
  // 1.2.1 time-based media
  multimedia: "1.2.1",
  // 1.3.1 info & relationships
  tables: "1.3.1",
  lists: "1.3.1",
  forms: "1.3.1",
  headings: "1.3.1",
  html: "1.3.1",
  css: "1.3.1",
  links: "1.3.1",
};
const KNOWN_CATEGORIES = new Set(Object.keys(CATEGORY_SC));

/** Parse `tables-table-has-no-scope-attributes.html` -> category + technique. */
export function parseFilename(file) {
  const base = path.basename(file, ".html");
  const dash = base.indexOf("-");
  if (dash > 0) {
    const category = base.slice(0, dash);
    if (KNOWN_CATEGORIES.has(category)) {
      return { failure_category: category, failure_technique: base.slice(dash + 1) };
    }
  }
  return { failure_category: "other", failure_technique: base };
}

/**
 * Resolve the WCAG success criterion for a row. Priority:
 *   1. an explicit value passed for the run/suite (meta.wcagSc),
 *   2. inference from the filename category,
 *   3. "unknown" (never guess silently — surfaces as a value to fix).
 */
export function resolveSc(explicitSc, failure_category) {
  if (explicitSc && explicitSc !== "auto") return explicitSc;
  return CATEGORY_SC[failure_category] || "unknown";
}

// Column order for the flattened CSV view (nested fields are JSON-stringified).
// Provenance/label columns first, then feature columns, so the two groups stay
// visually separated (guards against training on the leaky filename).
export const COLUMNS = [
  // provenance / label
  "sample_id",
  "source_file",
  "source_suite",
  "wcag_sc",
  "failure_category",
  "failure_technique",
  "label",
  "label_source",
  "captured_at",
  "nvda_version",
  "nvda_locale",
  "nvda_verbosity",
  "browser",
  "browser_version",
  "axe_version",
  "capture_mode",
  // element (feature)
  "element_type",
  "element_tag",
  "element_selector",
  "element_text",
  "element_html_raw",
  "element_html_normalized",
  // parent context (feature)
  "parent_tag",
  "parent_tag_path",
  "parent_html",
  "ancestor_roles",
  // computed CSS effects invisible to a DOM/a11y capture (feature)
  "css_generated_content",
  "hidden_content",
  // screen reader (feature)
  "sr_nav_commands",
  "sr_transcript",
  "sr_reading_order",
  "sr_last_phrase",
  "sr_phrase_count",
  "sr_cell_walk",
  "sr_headers_announced",
  // a11y tree (feature)
  "ax_role",
  "ax_name",
  "ax_level",
  "ax_subtree",
  // raw table markup, bypassing the browser's inferred header roles (feature)
  "table_cell_structure",
  // axe-core (feature + weak label)
  "axe_violations",
  "axe_wcag131_violations",
];

// Phrases that look like a header association being announced during a cell
// walk (raw capture only — this is a hint column, not a verdict). Matches the
// virtual reader's vocabulary ("columnheader"/"rowheader") and NVDA's
// ("column"/"row").
const HEADER_HINT = /columnheader|rowheader|\b(column|row)\b/i;

/**
 * Assemble one dataset row.
 * @param {object} args
 */
export function buildRow({
  file,
  sample,
  aria,
  violations,
  meta,
  sr, // { navCommands, transcript, readingOrder, cellWalk, headersAnnounced }
}) {
  const { failure_category, failure_technique } = parseFilename(file);
  const wcag_sc = resolveSc(meta.wcagSc, failure_category);
  const sampleViolations = violationsForSample(violations, sample.elementId);
  const transcript = sr.transcript || sr.readingOrder || [];
  const cellWalk = sr.cellWalk || null;
  const headersAnnounced =
    sr.headersAnnounced ||
    (cellWalk ? cellWalk.filter((p) => HEADER_HINT.test(p || "")) : null);

  return {
    sample_id: `${path.basename(file, ".html")}::${sample.elementId}`,
    source_file: path.basename(file),
    source_suite: meta.sourceSuite || "GDS-accessibility-audit",
    wcag_sc,
    failure_category,
    failure_technique,
    label: meta.label || "inaccessible",
    label_source: meta.labelSource || "source-folder-ground-truth",
    captured_at: meta.capturedAt,
    nvda_version: meta.nvdaVersion,
    nvda_locale: meta.nvdaLocale,
    nvda_verbosity: meta.nvdaVerbosity,
    browser: meta.browser,
    browser_version: meta.browserVersion,
    axe_version: meta.axeVersion,
    capture_mode: meta.captureMode, // "virtual-screen-reader" | "nvda" | "no-sr"

    element_type: sample.elementType,
    element_tag: sample.elementTag,
    element_selector: sample.elementSelector,
    element_text: sample.elementText,
    element_html_raw: normalizeHtml(sample.elementHtmlRaw),
    element_html_normalized: normalizeHtml(sample.elementHtmlRaw),

    parent_tag: sample.parentTag,
    parent_tag_path: sample.parentTagPath,
    parent_html: normalizeHtml(sample.parentHtml),
    ancestor_roles: sample.ancestorRoles,

    css_generated_content: sample.cssGeneratedContent || [],
    hidden_content: sample.hiddenContent || [],

    sr_nav_commands: sr.navCommands || "",
    sr_transcript: transcript,
    sr_reading_order: sr.readingOrder || [],
    sr_last_phrase: transcript.length ? transcript[transcript.length - 1] : "",
    sr_phrase_count: transcript.length,
    sr_cell_walk: cellWalk,
    sr_headers_announced: headersAnnounced,

    ax_role: aria.role,
    ax_name: aria.name,
    ax_level: aria.level,
    ax_subtree: aria.subtree,
    table_cell_structure: sample.cellStructure || null,

    axe_violations: sampleViolations,
    axe_wcag131_violations: sampleViolations.filter(isWcag131),
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
