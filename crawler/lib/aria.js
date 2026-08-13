// Computed accessibility-tree features per element via Playwright's
// locator.ariaSnapshot(). This is browser-agnostic (works in Firefox, where
// NVDA runs) so we avoid a separate Chromium pass. The snapshot is the ARIA
// role tree of the element; we keep the full string as `ax_subtree` and parse
// the first node for role / accessible name / heading level.

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} sampleId value of the injected data-sample-id
 */
export async function ariaFor(page, sampleId) {
  const empty = { role: null, name: null, level: null, subtree: "" };
  let snapshot = "";
  try {
    snapshot = await page.locator(`[data-sample-id="${sampleId}"]`).ariaSnapshot();
  } catch (e) {
    return empty;
  }
  if (!snapshot) return empty;

  // First non-empty line looks like: `- table "Caption":` or
  // `- heading "Title" [level=1]` or `- list:`
  const firstLine = snapshot
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.startsWith("- "));
  if (!firstLine) return { ...empty, subtree: snapshot };

  const body = firstLine.replace(/^-\s*/, "");
  const roleMatch = body.match(/^([a-zA-Z]+)/);
  const nameMatch = body.match(/"((?:[^"\\]|\\.)*)"/);
  const levelMatch = body.match(/\[level=(\d+)\]/);

  return {
    role: roleMatch ? roleMatch[1] : null,
    name: nameMatch ? nameMatch[1] : null,
    level: levelMatch ? Number(levelMatch[1]) : null,
    subtree: snapshot,
  };
}
