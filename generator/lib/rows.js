// Shared dataset schema + row assembly. Keeping this in one place guarantees
// every capture pass emits identical columns.
//
// The model is trained/evaluated on only three inputs — the element's HTML, its
// parent's HTML, and the screen-reader transcript — plus a label and a
// sample_id/source_file for traceability. Everything else (ARIA tree, axe-core,
// structural counts, CSS signals, raw cell structure) has been removed.
//
// One extra, status-only feature: `sr_status_announcement` — the WCAG 4.1.3
// interaction probe result (what the virtual reader announced after a simulated
// update to a live region). `[]` means the update was silent (a 4.1.3 failure
// signal); `null` means the row is not a status message and was not probed.
//
// One extra, control-only feature: `sr_role_state_value` — the WCAG 4.1.2
// interaction probe result (`{before, after}`, each `{phrase, html}`, from
// clicking the control). `null` means the row is not a role/state/value
// control and was not probed.
//
// One extra, form-only feature: `sr_label_instruction` — the WCAG 3.3.2
// interaction probe result: one `{field, before, after}` entry per form field,
// each side `{phrase, html}`, from entering a value. `null` means the row is not
// a form captured under `--sc 3.3.2` and was not probed.
//
// One extra, page-only feature: `sr_focus_order` — the WCAG 2.4.3 Tab sweep:
// `{stops, complete, truncated, stalled}`, where each stop carries the announced
// phrase plus its tabindex, DOM index and document-relative position. `null`
// means the row was not captured under `--sc 2.4.3` and was not swept.
//
// One extra, page-only feature: `sr_headings_labels` — the WCAG 2.4.6 rotor view:
// `{headings, labels, links}`, each entry carrying what the reader announces plus
// the context a rotor list strips away (a heading's section content, a label's
// control and section). `null` outside `--sc 2.4.6`.
//
// One extra, page-only feature: `sr_reading_order` — the WCAG 1.3.2 walk:
// `{steps, complete, truncated}`, each step pairing an announced phrase with the
// document-relative position it came from, which is what makes reading order and
// visual order comparable. `null` outside `--sc 1.3.2`.
//
// One extra, page-only feature: `sr_keyboard_trap` — the WCAG 2.1.2 escape ladder:
// `{stops, outcome, cycle, region, reverse, escape}`. `outcome` says how the
// forward Tab sweep ended (`escaped`/`stalled`/`cycled`/`cap`); `reverse` and
// `escape` record whether Shift+Tab and then the Escape key got focus back out
// again, which is the only thing that tells a keyboard trap apart from a modal
// dialog correctly containing focus. `null` outside `--sc 2.1.2`.
//
// One extra, page-only feature: `sr_focus_context` — the WCAG 3.2.1 on-focus probe:
// `{components, focusedVia, truncated}`, one entry per focusable component recording
// what changed when it received focus. The four UNAMBIGUOUS changes of context are
// recorded separately (`focusMovedTo`, `navigatedTo`, `opened`, `submitted`) from the
// ambiguous one (`mutations`, which carries the markup of what appeared), because
// content changing on focus is ordinary and context changing is not. `null` outside
// `--sc 3.2.1`.
//
// One extra, page-only feature: `sr_input_context` — the WCAG 3.2.2 on-input probe:
// `{components, changedVia, truncated}`. Same per-component shape as
// `sr_focus_context`, so the same evidence helpers render both, plus two fields this
// criterion needs: `settingChanged` (was the setting actually altered) and `advisory`
// (`describedBy`/`precedingText`/`hasAny`), because 3.2.2 permits a change of context
// on input when the user was warned of it beforehand. `null` outside `--sc 3.2.2`.

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
  // 4.1.3 status-message interaction probe (null for non-status rows)
  "sr_status_announcement",
  // 4.1.2 role/state/value interaction probe (null for non-control rows)
  "sr_role_state_value",
  // 3.3.2 labels/instructions interaction probe (null for non-form rows)
  "sr_label_instruction",
  // 2.4.3 focus-order Tab sweep (null for rows not captured under --sc 2.4.3)
  "sr_focus_order",
  // 2.4.6 headings/labels rotor view (null for rows not captured under --sc 2.4.6)
  "sr_headings_labels",
  // 1.3.2 reading-order walk (null for rows not captured under --sc 1.3.2)
  "sr_reading_order",
  // 2.1.2 keyboard-trap escape ladder (null for rows not captured under --sc 2.1.2)
  "sr_keyboard_trap",
  // 3.2.1 on-focus context probe (null for rows not captured under --sc 3.2.1)
  "sr_focus_context",
  // 3.2.2 on-input context probe (null for rows not captured under --sc 3.2.2)
  "sr_input_context",
];

/**
 * Normalize the markup a context probe captured. Shared by the 3.2.1 and 3.2.2
 * columns, which have the same per-component shape; `null` passes straight through
 * for every row not captured under those criteria.
 */
function normalizeContextProbe(probe) {
  if (!probe) return null;
  return {
    ...probe,
    components: (probe.components || []).map((component) => ({
      ...component,
      mutations: {
        ...component.mutations,
        addedNodes: (component.mutations?.addedNodes || []).map(normalizeHtml),
      },
    })),
  };
}

/**
 * Assemble one dataset row.
 * @param {object} args
 * @param {string} args.file      source HTML filename (for sample_id/source_file)
 * @param {object} args.sample    a descriptor from extractSamples()
 * @param {object} args.meta      run metadata (label)
 * @param {string[]} args.transcript  the element-scoped screen-reader phrases
 * @param {string[]|null} [args.statusAnnouncement]  4.1.3 probe result, or null
 * @param {{before: object, after: object}|null} [args.roleStateValue]  4.1.2 probe result, or null
 * @param {Array<{field: string, before: object, after: object}>|null} [args.labelInstruction]  3.3.2 probe result, or null
 * @param {{stops: Array<object>, complete: boolean}|null} [args.focusOrder]  2.4.3 sweep result, or null
 * @param {{headings: Array<object>, labels: Array<object>, links: Array<object>}|null} [args.headingsLabels]  2.4.6 rotor view, or null
 * @param {{steps: Array<object>, complete: boolean}|null} [args.readingOrder]  1.3.2 reading-order walk, or null
 * @param {{stops: Array<object>, outcome: string}|null} [args.keyboardTrap]  2.1.2 escape ladder, or null
 * @param {{components: Array<object>, focusedVia: string}|null} [args.focusContext]  3.2.1 on-focus probe, or null
 * @param {{components: Array<object>, changedVia: string}|null} [args.inputContext]  3.2.2 on-input probe, or null
 */
export function buildRow({
  file,
  sample,
  meta,
  transcript,
  statusAnnouncement = null,
  roleStateValue = null,
  labelInstruction = null,
  focusOrder = null,
  headingsLabels = null,
  readingOrder = null,
  keyboardTrap = null,
  focusContext = null,
  inputContext = null,
}) {
  const normalizeSides = (entry) => ({
    ...entry,
    before: { ...entry.before, html: normalizeHtml(entry.before.html) },
    after: { ...entry.after, html: normalizeHtml(entry.after.html) },
  });
  return {
    sample_id: `${path.basename(file, ".html")}::${sample.elementId}`,
    source_file: path.basename(file),
    label: meta.label || "inaccessible",

    element_html: normalizeHtml(sample.elementHtmlRaw),
    parent_html: normalizeHtml(sample.parentHtml),
    sr_transcript: transcript || [],
    sr_status_announcement: statusAnnouncement,
    sr_role_state_value: roleStateValue && normalizeSides(roleStateValue),
    sr_label_instruction: labelInstruction && labelInstruction.map(normalizeSides),
    // No HTML in these four, so nothing to normalize.
    sr_focus_order: focusOrder,
    sr_headings_labels: headingsLabels,
    sr_reading_order: readingOrder,
    sr_keyboard_trap: keyboardTrap,
    // The two page columns that DO carry markup: the nodes an interaction added.
    // Delta HTML, but normalized like any other, so a fixture marker or an
    // annotating comment cannot ride into a feature column through this route.
    sr_focus_context: normalizeContextProbe(focusContext),
    sr_input_context: normalizeContextProbe(inputContext),
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
