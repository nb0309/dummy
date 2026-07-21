// Produce the "stored" HTML for a sample: strip irrelevant boilerplate that is
// pure noise for a structure/relationship model (the jquery / main.js / css
// asset references never appear inside a captured element, but the
// data-sample-id we inject would — so remove it here as a safety net so the
// marker can never leak into a feature column).

/**
 * @param {string} html raw outerHTML of a captured element
 * @returns {string} normalized HTML (marker removed, whitespace collapsed)
 */
export function normalizeHtml(html) {
  if (!html) return "";
  let out = html;
  // drop the injected correlation marker (with or without surrounding space)
  out = out.replace(/\s*data-sample-id="[^"]*"/g, "");
  // drop the 4.1.3 probe markers (present in fixtures, must not leak into the
  // stored HTML feature); each may be valueless (`data-status-target`) or
  // valued (`data-status-target="…"`).
  out = out.replace(/\s*data-status-(?:target|trigger)(?:="[^"]*")?/g, "");
  // drop the 3.3.1 interaction markers. These matter more than the 4.1.3 ones:
  // the DOM is snapshotted AFTER interact.js clicks, so the markers are sitting
  // inside the captured form, and data-error-fill's value would leak the very
  // input that provoked the error into a feature column.
  out = out.replace(/\s*data-error-(?:trigger|fill)(?:="[^"]*")?/g, "");
  // collapse runs of whitespace between tags / inside text to single spaces,
  // but keep it readable rather than fully minified.
  out = out.replace(/>\s+</g, "><");
  out = out.replace(/[ \t]*\r?\n[ \t]*/g, "\n").trim();
  return out;
}
