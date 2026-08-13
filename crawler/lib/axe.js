// Run axe-core inside the page (works in any browser, incl. Firefox where NVDA
// runs) and attach each violation node to the nearest [data-sample-id] so the
// results can be filtered per sample. axe here is a *feature* + weak
// second-opinion label; it is not used to derive the ground-truth label.

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} axeSource contents of axe-core's `axe.source`
 * @returns {Promise<{version: string, violations: Array}>}
 */
export async function runAxe(page, axeSource) {
  await page.addScriptTag({ content: axeSource });
  return page.evaluate(async () => {
    // eslint-disable-next-line no-undef
    const results = await axe.run(document, { resultTypes: ["violations"] });
    for (const v of results.violations) {
      for (const node of v.nodes) {
        const ids = [];
        try {
          const sel = Array.isArray(node.target) ? node.target[0] : node.target;
          const el = typeof sel === "string" ? document.querySelector(sel) : null;
          const host = el && el.closest("[data-sample-id]");
          if (host) ids.push(host.getAttribute("data-sample-id"));
        } catch (e) {
          /* selector may not resolve (shadow/iframe); leave unmapped */
        }
        node.sampleIds = ids;
      }
    }
    // eslint-disable-next-line no-undef
    return { version: axe.version, violations: results.violations };
  });
}

const WCAG131_RULE_TAGS = new Set(["wcag131", "cat.structure", "cat.tables"]);

/**
 * Slim down a full violation to the fields worth storing per sample, keeping
 * only the nodes belonging to this sample id.
 */
export function violationsForSample(violations, sampleId) {
  const out = [];
  for (const v of violations) {
    const nodes = (v.nodes || []).filter(
      (n) => Array.isArray(n.sampleIds) && n.sampleIds.includes(sampleId)
    );
    if (!nodes.length) continue;
    out.push({
      id: v.id,
      impact: v.impact,
      help: v.help,
      tags: v.tags,
      nodes: nodes.map((n) => ({ html: n.html, target: n.target })),
    });
  }
  return out;
}

export function isWcag131(violation) {
  return (violation.tags || []).some((t) => WCAG131_RULE_TAGS.has(t));
}
